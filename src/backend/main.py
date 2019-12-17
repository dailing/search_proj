from flask import Flask, request, make_response, redirect, abort, Response, send_file
from io import BytesIO
from flask_restful import Resource, Api
import shutil
import os
import stat
from util.logs import get_logger
import json
import hashlib
from peewee import PostgresqlDatabase, Model, TextField,\
	BlobField, DateTimeField, IntegerField, IntegrityError,\
	DatabaseProxy, DateField, BooleanField, TimestampField,\
	ForeignKeyField, CharField
import playhouse.db_url
from playhouse.postgres_ext import JSONField, ArrayField
import datetime
import psycopg2
import math
import base64
from hashlib import md5
import uuid
from peewee import fn, DoesNotExist
import time
from elasticsearch import Elasticsearch
from playhouse.shortcuts import model_to_dict
from playhouse.postgres_ext import Match
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
	if isinstance(obj, memoryview):
		return "Binary Value"
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


class CRUD(Resource):
	_model=None
	def __init__(self):
		super(CRUD, self).__init__()
		self.model = self.__class__._model
		assert self.model is not None
		logger.info(self.model)

	@response_json
	def get(self, record_id):
		logger.info(record_id)
		try:
			result = self.model.get_by_id(record_id)
		except DoesNotExist as e:
			logger.info(self.model)
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
	title = TextField(null=True)
	author = ArrayField(TextField, null=True)
	journal = TextField(null=True)
	field = TextField(null=True)
	institute = TextField(null=True)
	publish_time = DateField(null=True)
	funds = ArrayField(TextField, null=True)
	publisher = TextField(null=True)
	checked = BooleanField(default=False)
	created = DateTimeField(default=datetime.datetime.now)
	modified = DateTimeField(default=datetime.datetime.now)
	abstract = TextField(null=True)
	full_text = TextField(null=True)
	
	def save(self, *args, **kwargs):
		self.modified = datetime.datetime.now()
		return super(PaperRecord, self).save(*args, **kwargs)


class Folder(BaseModel):
	name = TextField()
	parent_id = IntegerField(default=0)
	created = TimestampField(default=datetime.datetime.now, utc=True)
	modified = TimestampField(default=datetime.datetime.now, utc=True)
	payload = BlobField(null=True)
	md5 = TextField(null=True)
	readable = BooleanField(default=True)
	writable = BooleanField(default=True)
	isDir = BooleanField()
	size = IntegerField(default=0)
	meta_info = ForeignKeyField(PaperRecord, null=True)

	def save(self, *args, **kwargs):
		self.modified = datetime.datetime.now()
		if self.payload is not None:
			self.md5 = md5(bytes(self.payload)).hexdigest()
		if 'only' in kwargs:
			kwargs['only'] = [k for k in kwargs['only']] + ['modified', 'md5']
		return super(Folder, self).save(*args, **kwargs)
	
	class Meta:
		indexes = (
			# create a unique constraint
			(('parent_id', 'name',), True),
		)


class FSModelSql():

	@staticmethod
	def _init_fs():
		with psql_db.atomic():
			if Folder.select().where(Folder.parent_id==0).count() < 1:
				Folder.create(name='/', parent_id=0, isDir=True)
	
	@staticmethod
	def _flush_all():
		try:
			psql_db.execute_sql('drop table folder;')
		except Exception:
			pass
		try:
			psql_db.execute_sql('drop table paperrecord;')
		except Exception:
			pass
		init_db()

	@staticmethod
	def _root():
		return Folder.get_by_id(1)

	@staticmethod
	def _get_record(path):
		fields = path.split('/')
		record = FSModelSql._root()
		for f in fields:
			if f == '':
				continue
			logger.info(f'{record.id},, {f}')
			try:
				record = Folder.get(Folder.parent_id==record.id and Folder.name==f)
			except:
				return record
		return record

	@staticmethod
	def _get_or_create(path):
		logger.info(f'{path}')
		path, name = os.path.split(path)
		logger.info(f'{path, name}')
		record = FSModelSql._get_record(path)
		logger.info(record.id)
		folder, succ = Folder.get_or_create(name=name, parent_id=record.id, isDir=False)
		if succ:
			pap = PaperRecord.create()
			folder.meta_info = pap.id
			folder.save(only=('meta_info', ))
		return folder

	@staticmethod
	def find_path(record):
		path=""
		while(record.parent_id != 0):
			if path != '':
				path = record.name + '/' + path
			else:
				path = record.name
			record = Folder.get_by_id(record.parent_id)
		return '/' + path

	@staticmethod
	def get_info(record, path=None):
		if isinstance(record, str):
			parent,_ = os.path.split(record)
			return FSModelSql.get_info(FSModelSql._get_record(record), parent)
		logger.info(record)
		if path is None:
			path = FSModelSql.find_path(record)
		return dict(
			id=os.path.join(path, record.name),
			type="folder" if record.isDir else 'file',
			attributes=dict(
				name=record.name,
				path=os.path.join(path, record.name),
				readable=int(record.readable),
				writable=int(record.writable),
				created=int(datetime.datetime.timestamp(record.created)),
				modified=int(datetime.datetime.timestamp(record.modified)),
				height=0,
				width=0,
				size=record.size,
				meta=model_to_dict(record.meta_info) if record.meta_info else None,
				dbid=record.id,
		))


	@staticmethod
	def _ls(record):
		result = []
		logger.info(f'_ls {record}, {type(record)}')
		for file in Folder.select(
					Folder.id,
					Folder.name,
					Folder.parent_id,
					Folder.created,
					Folder.modified,
					Folder.md5,
					Folder.readable,
					Folder.writable,
					Folder.isDir,
					Folder.size,
				).where(Folder.parent_id==record.id).execute():
			result.append(file)
			logger.info(file)
		return result


	@staticmethod
	def ls(path):
		record = FSModelSql._get_record(path)
		result = [FSModelSql.get_info(file, path) for file in FSModelSql._ls(record)]
		return result

	@staticmethod
	def mkdir(path, name):
		try:
			with psql_db.atomic():
				record = FSModelSql._get_record(path)
				Folder.create(name=name, parent_id=record.id, isDir=True)
		except IntegrityError as e:
			psql_db.rollback()
			return Exception("Folder exists")
	
	@staticmethod
	def _delete(record):
		for rec in FSModelSql._ls(record):
			if rec.isDir:
				FSModelSql._delete(rec)
			Folder.delete().where(Folder.parent_id == record.id)
		record.delete_instance()

	@staticmethod
	def delete(file):
		rec = FSModelSql._get_record(file)
		FSModelSql._delete(rec)

	@staticmethod
	def read(file):
		abs_file = FSModelSql._get_record(file)
		assert not abs_file.isDir
		return bytes(abs_file.payload)

	@staticmethod
	def write(file, content):
		# logger.info(content)
		record = FSModelSql._get_or_create(file)
		logger.info(record)
		record.payload = content
		record.size = len(content)
		record.save(only=('payload', 'size'))
		return record

	@staticmethod
	def move(source, target):
		s_record = FSModelSql._get_record(source)
		t_record = FSModelSql._get_record(target)
		s_record.parent_id=t_record.id
		s_record.save(only=('parent_id', ))
		_, fname = os.path.split(source)
		return FSModelSql.get_info(FSModelSql._get_record(os.path.join(target, fname)), target)

	@staticmethod
	def rename(source, target):
		logger.info(source)
		logger.info(target)
		s_record = FSModelSql._get_record(source)
		s_record.name = target
		logger.info(s_record.save(only=['name']))
		return FSModelSql.get_info(s_record)
	
	@staticmethod
	def search(kw):
		kw = kw.split()
		logger.info(f'search {kw}')
		query_pattern = '%' + "%".join(kw) + '%'
		logger.info(f'pattern: {query_pattern}')
		result = Folder.select(
			Folder.id,
			Folder.name,
			Folder.parent_id,
			Folder.created,
			Folder.modified,
			Folder.md5,
			Folder.readable,
			Folder.writable,
			Folder.isDir,
			Folder.size,
		).where(Folder.isDir == False and Folder.name % query_pattern).execute()
		logger.info(result)
		res_dict = []
		for i in result:
			record_dict = model_to_dict(i)
			record_dict['path'] = FSModelSql.find_path(i)
			res_dict.append(record_dict)
		logger.info(res_dict)
		return res_dict



class CRUD_paper(CRUD):
	_model=PaperRecord

class CRUD_folder(CRUD):
	_model=Folder

try:
	api.add_resource(
		CRUD_paper,
		'/api/item/paper/<int:record_id>',
		'/api/item/paper')

	api.add_resource(
		CRUD_folder,
		'/api/item/file/<int:record_id>',
		'/api/item/file')
except Exception as e:
	logger.error(e)


@app.route('/')
def serve_index():
	return redirect('/static/index.html')

@app.route('/api/search', methods=["GET"])
def search_query():
	query = request.args['query']
	logger.info(query)
	logger.info(type(query))
	rpc_client = zerorpc.Client()
	logger.info(rpc_client.connect("tcp://search:4242"))
	result = rpc_client.hello(query)
	logger.info(result)
	return result


class FileManagerApi():
	_model = FSModelSql
	@staticmethod
	@response_json
	def seek_folder():
		# TODO implement this
		path = request.args['path']
		keyword = request.args['string']
		# os.walk()
		pass

	@staticmethod
	@response_json
	def search():
		return FileManagerApi._model.search(request.args['kw'])

	@staticmethod
	@response_json
	def move():
		source = request.args['old']
		target = request.args['new']
		return dict(data=FileManagerApi._model.move(source, target))

	@staticmethod
	@response_json
	def rename():
		logger.info(request.args)
		source = request.args['old']
		target = request.args['new']
		return dict(data=FileManagerApi._model.rename(source, target))

	@staticmethod
	@response_json
	def getimage():
		# path = request.args['path']
		return FileManagerApi.download()
	
	@staticmethod
	# @response_json
	def download():
		print(request.cookies)
		logger.info(request.is_xhr)
		path = request.args['path']
		if request.is_xhr:
			return dict(data=FileManagerApi._model.get_info(path))
		else:
			ff = BytesIO(FileManagerApi._model.read(path))
			return send_file(ff, as_attachment=True, attachment_filename=path)


	@staticmethod
	@response_json
	def readfile():
		path = request.args['path']
		return FileManagerApi._model.read(path)

	@staticmethod
	@response_json
	def delete():
		path = request.args['path']
		resp = dict(data=FileManagerApi._model.get_info(path))
		FileManagerApi._model.delete(path)
		return resp

	@staticmethod
	@response_json
	def addfolder():
		path = request.args['path']
		folder = request.args['name']
		FileManagerApi._model.mkdir(path, folder)
		return dict(data=FileManagerApi._model.get_info(os.path.join(path, folder), path))


	@staticmethod
	@response_json
	def readfolder():
		path = request.args['path']
		return dict(data=FileManagerApi._model.ls(path))

	@staticmethod
	@response_json
	def getinfo():
		path = request.args['path']
		return FileManagerApi._model.get_info(path)

	@staticmethod
	@response_json
	def initiate():
		resp = {
			"data": {
				"id": "/",
				"type": "initiate",
				"attributes": {
					"config": {
						"security": {
							"readOnly": False,
							"extensions": {
								"policy": "DISALLOW_LIST",
								"ignoreCase": False,
								"restrictions": []
							}
						},
					}
				}
			}
		}
		return resp


@app.route('/filemanager/api', methods=["POST"])
def filemanager_savefile():
	if request.form['mode'] == 'savefile':
		path = request.form['path']
		logger.info(request.form['content'])
		FileManagerApi._model.write(path, request.form['content'].encode('utf-8'))
		return dict(data=FileManagerApi._model.get_info(path))
	elif request.form['mode'] == 'upload':
		path = request.form['path']
		logger.info(request.files)
		result = []
		for f in request.files.getlist('files'):
			file = os.path.join(path, f.filename)
			logger.info(f.__dict__)
			FileManagerApi._model.write(file, f.stream.read())
			result.append(FileManagerApi._model.get_info(file))
		return dict(data=result)


@app.route('/filemanager/api')
def filemanager_handler():
	logger.info(request.args)
	logger.info(request.data)
	handle_func = dict(
		initiate=FileManagerApi.initiate,
		readfolder=FileManagerApi.readfolder,
		getinfo=FileManagerApi.getinfo,
		addfolder=FileManagerApi.addfolder,
		delete=FileManagerApi.delete,
		readfile=FileManagerApi.readfile,
		download=FileManagerApi.download,
		getimage=FileManagerApi.getimage,
		move=FileManagerApi.move,
		rename=FileManagerApi.rename,
		search=FileManagerApi.search,
	)
	return handle_func[request.args['mode']]()


def init_db():
	for i in range(3):
		logger.info(f'Try to connect to db, {i+1} of 3 ...')
		try:
			psql_db.initialize(playhouse.db_url.connect(
			os.environ['DB_URL']))
			psql_db.connect()
			psql_db.create_tables([PaperRecord, Folder])
			FileManagerApi._model._init_fs()
			logger.info('we are good now ...')
			return
		except Exception as e:
			pass
			# logger.error(e)
		time.sleep(3)

init_db()

if __name__ == "__main__":
	app.run(host='0.0.0.0')
