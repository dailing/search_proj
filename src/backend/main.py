from flask import Flask, request, make_response, redirect, abort, Response
from flask_restful import Resource, Api
import os
from util.logs import get_logger
import json
import hashlib
from peewee import PostgresqlDatabase, Model, TextField,\
	BlobField, DateTimeField, IntegerField, IntegrityError,\
	DatabaseProxy, DateField, BooleanField
import playhouse.db_url
from playhouse.postgres_ext import JSONField, ArrayField
import datetime
import psycopg2
import math
import base64
import uuid
from peewee import fn, DoesNotExist
import time
from elasticsearch import Elasticsearch
from playhouse.shortcuts import model_to_dict
import six
import math
import zerorpc


logger = get_logger('search project learning')


app = Flask(__name__, static_folder='statics', static_url_path='/static')
api = Api(app)
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024
es = Elasticsearch(['es01:9200'])
psql_db = DatabaseProxy()


def json_encoder_default(obj):
	datetime_format = "%Y/%m/%d %H:%M:%S"
	date_format = "%Y/%m/%d"
	time_format = "%H:%M:%S"
	# if isinstance(obj, Decimal):
	#     return str(obj)
	if isinstance(obj, datetime.datetime):
		return obj.strftime(datetime_format)
	if isinstance(obj, datetime.date):
		return obj.strftime(date_format)
	if isinstance(obj, datetime.time):
		return obj.strftime(time_format)
	raise TypeError("%r is not JSON serializable" % obj)


def response_json(func):
	def wrapper(*args, **kwargs):
		result = func(*args, **kwargs)
		if isinstance(result, Response):
			logger.info('response obj, exit!')
			return result
		if isinstance(result, Model):
			result = model_to_dict(result)
		if isinstance(result, dict) or isinstance(result, list):
			result = json.dumps(result, default=json_encoder_default)
		resp = make_response(result, 200)
		resp.headers['Content-Type'] = 'application/json'
		return resp
	return wrapper


class BaseModel(Model):
	"""A base model that will use our Postgresql database"""
	class Meta:
		database = psql_db


class RestfulCRUD(type):
	def __new__(cls, clsname, superclasses, attributedict, model=None):
		if model is None:
			raise Exception('Please define model')
		# superclasses = superclasses + (Resource, )
		@response_json
		def get(self, record_id):
			try:
				result = model.get_by_id(record_id)
			except DoesNotExist as e:
				abort(400, "no such record")
			return result

		@response_json
		def put(self, record_id):
			field = request.json
			if field is None:
				abort(400, "request field error")
			logger.info(field)
			result = model.update(field).where(model.id == record_id).execute()
			return "OK"

		attributedict.update(dict(
			get=get,
			put=put
		))
		return type.__new__(cls, clsname, superclasses, attributedict)

class CRUD(Resource):
	def __init__(self, model=None):
		self.model = model
		super(CRUD, self).__init__()

	@response_json
	def get(self, record_id):
		try:
			result = self.model.get_by_id(record_id)
		except DoesNotExist as e:
			abort(400, "no such record")
		return result

	@response_json
	def put(self, record_id):
		field = request.json
		if field is None:
			abort(300, "request field error")
		logger.info(field)
		result = self.model.update(field).where(self.model.id == record_id).execute()
		logger.info(result)
		return dict(status='OK')

	@response_json
	def post(self, record_id=None):
		field = request.json
		if field is None:
			abort(300, "request error")
		logger.info(field)
		try:
			result = self.model.create(**field)
		except Exception as e:
			logger.error("error create data", exc_info=e)
			abort(500, 'Error create item')
		return result

	@response_json
	def delete(self, record_id):
		try:
			query = self.model.delete().where(self.model.id == record_id)
			result = query.execute()
		except Exception as e:
			logger.error('delete error', exc_info=e)


class ListApi(Resource):
	def __init__(self, model):
		self.model = model
		super(ListApi, self).__init__()

	@response_json
	def get(self):
		count = self.model.select().count()
		page = request.args.get('page', 1, int)
		n_item_per_page = request.args.get('item_per_page', 10, int)
		if n_item_per_page <= 0:
			abort(400, "fuck you!")
		return dict(
			num_items=count,
			num_pages=math.ceil(count / n_item_per_page),
			current_page=page,
			item_per_page=n_item_per_page,
			items=list(self.model.select().paginate(page, n_item_per_page).dicts()))

class PaperRecord(BaseModel):
	title = TextField()
	author = ArrayField(TextField, null=True)
	journal = TextField()
	field = TextField()
	institute = TextField()
	publish_time = DateField()
	funds = ArrayField(TextField)
	publisher = TextField()
	checked = BooleanField(default=False)
	created = DateTimeField(default=datetime.datetime.now)
	modified = DateTimeField(default=datetime.datetime.now)
	
	def save(self, *args, **kwargs):
		self.modified = datetime.datetime.now()
		return super(PaperRecord, self).save(*args, **kwargs)


class Folder(BaseModel):
	name = TextField()
	created = DateTimeField(default=datetime.datetime.now)
	parent_id = IntegerField(default=0)
	modified = DateTimeField(default=datetime.datetime.now)
	
	def save(self, *args, **kwargs):
		self.modified = datetime.datetime.now()
		return super(Folder, self).save(*args, **kwargs)


class File(BaseModel):
	name = TextField()
	created = DateTimeField()
	payload = BlobField()
	md5 = TextField()
	parent_id = IntegerField()
	modified = DateTimeField(default=datetime.datetime.now)
	
	def save(self, *args, **kwargs):
		self.modified = datetime.datetime.now()
		return super(File, self).save(*args, **kwargs)


class FSModel():

	def init_fs():
		if Folder.select().where(Folder.parent_id==0).count() < 1:
			Folder.create(
				name=root,
				parent_id=0,
			)

	def __init__(self, path="/"):
		self.current_path = path
		self.current_node = self._root()
		self.cd(path)

	def _root(self):
		return Folder.select().where(Folder.parent_id==0).get()

	def _get_folder_record(self, path):
		node = self.current_node
		if path.startswith('/'):
			node = self._root()
		for f in path.split('/'):
			if f == ".":
				pass
			elif f == '..':
				if node.parent_id == 0:
					return None
				else:
					node = Folder.get_by_id(node.parent_id)
			else:
				folder = Folder.select().where(Folder.id==node.parent_id and Folder.name == folder).get()
				if folder is not None:
					node = folder
				else:
					return None
		return node

	def cd(self, path):
		nn = self._get_folder_record(path)
		if nn is not None:
			self.current_node = nn
			return True
		return False
	
	def _ls(self, folder_id):
		folders = [
			f.name for f in Folder.select(Folder.name).\
				where(Folder.parent_id==self.current_node.id).execure()]
		files = [
			f.name for f in File.select(File.name).where(File.parent_id==self.current_node.id).execute()]
		return folders, files

	def ls(self, path=None):
		if path is not None:
			nn = self._get_folder_record(path)
			if nn is None:
				return
		else:
			nn = self.current_node
		return self._ls(nn.parent_id)

	def get_record(self, name):
		folder, file_name = os.path.split()
		nn = None
		if folder != "":
			nn = self._get_folder_record(folder)
		if nn is None:
			nn = self.current_node
		record = File.select().where(File.parent_id==nn.id and File.name==file_name).get()
		return record
			


try:
	psql_db.initialize(playhouse.db_url.connect(
	'postgresql://db_user:123456@db:5432/fuckdb'))
	psql_db.connect()
	psql_db.create_tables([PaperRecord])
except Exception as e:
	logger.error(e)

try:
	api.add_resource(
		CRUD,
		'/api/item/paper/<int:record_id>',
		'/api/item/paper',
		resource_class_kwargs=dict(model=PaperRecord))
	api.add_resource(
		ListApi,
		'/api/list/paper',
		resource_class_kwargs=dict(model=PaperRecord))
except Exception as e:
	logger.error(e)


@app.route('/')
def serve_index():
	return redirect('/static/index.html')

@app.route('/api/search', methods=["POST"])
def search_query():
	query = request.get_data().decode('utf-8')
	logger.info(query)
	logger.info(type(query))
	rpc_client = zerorpc.Client()
	logger.info(rpc_client.connect("tcp://search:4242"))
	result = rpc_client.hello(query)
	logger.info(result)
	return result

@app.route('/upload', methods=["POST"])
def upload():
	logger.info(request.files)
	logger.info(request.form)
	for k,v in request.files.items():
		logger.info(f'{k}::{v.filename}')
		logger.info(v.__dir__())
	return "OK"


if __name__ == "__main__":
	app.run(host='0.0.0.0')
