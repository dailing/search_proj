from requests import put, get, post
import requests
import json
import os
import sys
from main import FSModelSql

base_url = os.environ['url']

def setup_module(module):
    """ setup any state specific to the execution of the given module."""
    FSModelSql._flush_all()


def teardown_module(module):
    """ teardown any state that was previously setup with a setup_module
    method.
    """
    # FSModelSql._flush_all()


def test_put_get_record():
    temp_record = dict(
        title='test_title',
        author=['a','b'],
        journal='test_journal',
        field='test_field',
        institute='test_institute',
        publish_time='2019/11/11',
        funds=['f1', 'f2'],
        publisher='test_publisher',
    )
    result = post(f'{base_url}/api/item/paper', json=temp_record).json()
    assert 'id' in result
    record_id = result['id']
    retrieved_record = get(f'{base_url}/api/item/paper/{record_id}').json()
    for k,v in temp_record.items():
        assert k in retrieved_record
        assert v == retrieved_record[k]
    
    modify = dict(title='test_title2')
    result = put(f'{base_url}/api/item/paper/{record_id}', json=modify)
    print('32', type(result), result, result.text)

    temp_record.update(modify)

    retrieved_record = get(f'{base_url}/api/item/paper/{record_id}').json()
    print(type(retrieved_record))
    for k,v in temp_record.items():
        assert k in retrieved_record
        assert v == retrieved_record[k]


def test_paper_list():
    result = get(f'{base_url}/api/list/paper').json()
    assert isinstance(result, dict)
    assert min(10, result["num_items"]) == len(result['items'])



def test_folder_init():
    FSModelSql._init_fs()
    record = FSModelSql._root()
    assert record.name == '/'
    assert record.id == 1

def test_folder_create():
    assert FSModelSql.mkdir('/', 'test') == None
    assert type(FSModelSql.mkdir('/', 'test')) is Exception
    root = FSModelSql._get_record('/')
    assert root.id == 1
    assert root.name == "/"
    rec = FSModelSql._get_record('/test')
    assert rec.name == 'test'
    assert rec.parent_id == root.id

    FSModelSql.mkdir('/test', 'fuck')
    rec2 = FSModelSql._get_record('/test/fuck')
    assert rec2.name == 'fuck'
    assert rec2.parent_id == rec.id

    xx = FSModelSql.ls('/')
    print(xx)
    assert len(xx) == 1
    assert xx[0]['attributes']['name'] == 'test'

    FSModelSql.delete('/test/fuck')
    xx = FSModelSql.ls('/')
    assert len(xx) == 1

    FSModelSql.delete('/test')
    xx = FSModelSql.ls('/')
    assert len(xx) == 0

def test_move():
    FSModelSql.mkdir('/', 'a')
    FSModelSql.mkdir('/a', 'b')
    FSModelSql.move('/a/b', '/')
    xx = FSModelSql.ls('/')
    assert (len(xx)) == 2
    FSModelSql.delete('/a')
    FSModelSql.delete('/b')

def test_write():
    FSModelSql.write('/fuck.txt', b'FUCK')
    xx = FSModelSql.ls('/')
    assert (len(xx)) == 1
    xx = FSModelSql.read('/fuck.txt')
    assert xx == b'FUCK'
    

if __name__ == "__main__":
    pass

