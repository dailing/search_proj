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
	DatabaseProxy, DateField, BooleanField, TimestampField
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
	parent_id = IntegerField(default=0)
	created = TimestampField(default=datetime.datetime.now, utc=True)
	modified = TimestampField(default=datetime.datetime.now, utc=True)
	payload = BlobField(null=True)
	md5 = TextField(null=True)
	readable = BooleanField(default=True)
	writable = BooleanField(default=True)
	isDir = BooleanField()
	size = IntegerField(default=0)

	def save(self, *args, **kwargs):
		self.modified = datetime.datetime.now()
		if 'only' in kwargs:
			kwargs['only'] = [k for k in kwargs['only']] + ['modified']
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
			record = Folder.get(Folder.parent_id==record.id and Folder.name==f)
		return record

	@staticmethod
	def _get_or_create(path):
		logger.info(f'{path}')
		path, name = os.path.split(path)
		logger.info(f'{path, name}')
		record = FSModelSql._get_record(path)
		logger.info(record.id)
		folder, _ = Folder.get_or_create(name=name, parent_id=record.id, isDir=False)
		return folder

	@staticmethod
	def get_info(record, path=None):
		if isinstance(record, str):
			parent,_ = os.path.split(record)
			return FSModelSql.get_info(FSModelSql._get_record(record), parent)
		logger.info(record)
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
		logger.info(content)
		record = FSModelSql._get_or_create(file)
		logger.info(record)
		record.payload = content
		record.save(only=('payload', ))
		return record

	@staticmethod
	def move(source, target):
		s_record = FSModelSql._get_record(source)
		t_record = FSModelSql._get_record(target)
		s_record.parent_id=t_record.id
		s_record.save(only=('parent_id', ))
		_, fname = os.path.split(source)
		return FSModelSql.get_info(FSModelSql._get_record(os.path.join(target, fname)), target)


class FSModel():
	@staticmethod
	def init_fs():
		if Folder.select().where(Folder.parent_id==0).count() < 1:
			Folder.create(
				name='root',
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


class _FSModelNormalFile():
	base_path = '/storage'

	@staticmethod
	def get_path(path):
		if path.startswith('/'):
			path = path[1:]
		return os.path.join(FSModelNormalFile.base_path, path)

	@staticmethod
	def ls(path):
		result = []
		logger.info(FSModelNormalFile.get_path(path))
		for file in os.listdir(FSModelNormalFile.get_path(path)):
			logger.info(file)
			result.append(FSModelNormalFile.get_info(os.path.join(path, file)))
		result = dict(data=result)
		logger.info(result)
		return result

	@staticmethod
	def get_info(path):
		abs_path = FSModelNormalFile.get_path(path)
		fstat = os.stat(abs_path)
		mode = fstat.st_mode
		_, name = os.path.split(path)
		logger.info(fstat)
		return dict(
			id=os.path.join(path, path),
			type="folder" if stat.S_ISDIR(mode) else 'file',
			attributes=dict(
				name=name,
				path=abs_path,
				readable=int((stat.S_IREAD & mode) > 0),
				writable=int((stat.S_IWRITE & mode) > 0),
				created=int(fstat.st_ctime),
				modified=int(fstat.st_mtime),
				height=0,
				width=0,
				size=fstat.st_size
		))

	@staticmethod
	def mkdir(path, name):
		path = FSModelNormalFile.get_path(path)
		if not os.path.isdir(path):
			return False
		os.mkdir(os.path.join(path, name))
		return True
	
	@staticmethod
	def _delete(abs_file):
		if os.path.isdir(abs_file):
			for dirpath, dirnames, filenames in os.walk(abs_file):
				for dirname in dirnames:
					pp = os.path.join(dirpath, dirname)
					FSModelNormalFile._delete(pp)
					logger.info(f'deleting {pp}')
					os.rmdir(pp)
				for filename in filenames:
					pp = os.path.join(dirpath, filename)
					logger.info(f'deleting {pp}')
					os.remove(pp)
			os.rmdir(abs_file)
		else:
			os.remove(abs_file)

	@staticmethod
	def delete(file):
		abs_file = FSModelNormalFile.get_path(file)
		FSModelNormalFile._delete(abs_file)

	@staticmethod
	def read(file):
		abs_file = FSModelNormalFile.get_path(file)
		assert os.path.isfile(abs_file)
		return open(abs_file, 'rb').read()

	@staticmethod
	def write(file, content):
		mode = 'wb' if isinstance(content, bytes) else 'w'
		with open(FSModelNormalFile.get_path(file), mode=mode) as f:
			f.write(content)

	@staticmethod
	def move(source, target):
		shutil.move(FSModelNormalFile.get_path(source), FSModelNormalFile.get_path(target))
		_, fname = os.path.split(source)
		return FSModelNormalFile.get_info(os.path.join(target, fname))


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
	def move():
		source = request.args['old']
		target = request.args['new']
		return dict(data=FileManagerApi._model.move(source, target))

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
	)
	return handle_func[request.args['mode']]()


def init_db():
	try:
		psql_db.initialize(playhouse.db_url.connect(
		os.environ['DB_URL']))
		psql_db.connect()
		psql_db.create_tables([PaperRecord, Folder])
		FileManagerApi._model._init_fs()
	except Exception as e:
		logger.error(e)

init_db()

if __name__ == "__main__":
	app.run(host='0.0.0.0')
