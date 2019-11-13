from requests import put, get, post
import requests
import json

base_url = 'http://202.120.44.152:25088'


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
    result = put(f'{base_url}/api/paper_list', json=temp_record).json()
    assert 'id' in result
    record_id = result['id']
    retrieved_record = get(f'{base_url}/api/paper_record/{record_id}').json()
    print(type(retrieved_record))
    for k,v in temp_record.items():
        assert k in retrieved_record
        assert v == retrieved_record[k]
    
    modify = dict(title='test_title2')
    result = put(f'{base_url}/api/paper_record/{record_id}', json=modify)

    temp_record.update(modify)

    retrieved_record = get(f'{base_url}/api/paper_record/{record_id}').json()
    print(type(retrieved_record))
    for k,v in temp_record.items():
        assert k in retrieved_record
        assert v == retrieved_record[k]
