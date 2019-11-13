
from flask import Flask, request, make_response, redirect, abort, Response
from flask_restful import Resource, Api
import os
from util.logs import get_logger
# import cv2
# import numpy as np
import json
import hashlib
from peewee import PostgresqlDatabase, Model, TextField,\
	BlobField, DateTimeField, IntegerField, IntegrityError,\
	DatabaseProxy, DateField
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


logger = get_logger('search project learning')


app = Flask(__name__, static_folder='statics', static_url_path='/static')
api = Api(app)
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
				abort(300, "request field error")
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
		return "OK"


class PaperRecord(BaseModel):
	title = TextField()
	author = ArrayField(TextField, null=True)
	journal = TextField()
	field = TextField()
	institute = TextField()
	publish_time = DateField()
	funds = ArrayField(TextField)
	publisher = TextField()
	added_time = DateTimeField(default=datetime.datetime.now)


class PaperRecordList(Resource):

	@response_json
	def get(self):
		return list(PaperRecord.select().dicts())
	
	@response_json
	def put(self):
		logger.info(request.json)
		result = PaperRecord.create(**request.json)
		logger.info(result)
		return dict(id=result.id)


try:
	psql_db.initialize(playhouse.db_url.connect(
	'postgresql://db_user:123456@db:5432/fuckdb'))
	psql_db.connect()
	psql_db.create_tables([PaperRecord])
except Exception as e:
	logger.error(e)

try:
	api.add_resource(
		CRUD, '/api/paper_record/<int:record_id>', 
		resource_class_kwargs=dict(model=PaperRecord))
	api.add_resource(PaperRecordList, '/api/paper_list')
except Exception as e:
	logger.error(e)


@app.route('/')
def serve_index():
	return redirect('/static/index.html')


@app.route('/api/document/<string:index>', methods=['PUT'])
def add_document_to_elastic_search(index):
	logger.info(request.json)
	result = es.index(index=index, body=request.json)
	logger.info(result)
	return "OK"

@app.route('/api/document/<string:index>', methods=['GET'])
def get_document_from_elasticsearch(index):
	result = es.search(index = index, body={})
	logger.info(result)
	return "OK"


@app.route('/api/add_img', methods=['POST'])
def serve_add_img():
	session_name = request.form['session_name']
	for fname, file in request.files.items():
		xx = file.read()
		md5_val = hashlib.md5(xx).hexdigest()
		app.logger.info(len(xx))
		try:
			result = ImageStorage.create(
				payload=xx, md5=md5_val, session_name=session_name)
			app.logger.info(result)
		except IntegrityError as e:
			psql_db.rollback()
			app.logger.info(e)
	return "OK"


@app.route('/api/image_length')
def serve_imageLength():
	length = ImageStorage.select().count()
	app.logger.info(length)
	return dict(length=length)

if __name__ == "__main__":
	app.run(host='0.0.0.0')
