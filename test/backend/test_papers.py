from requests import put, get, post
import requests
import json
import os

base_url = os.environ['url']


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
    assert isinstance(result, list)

if __name__ == "__main__":
    test_put_get_record()
