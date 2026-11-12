import uuid

from inku_server import db
from .test_api import auth_context, client  # noqa: F401


def test_batch_filter_only_returns_the_callers_works(auth_context):  # noqa: F811 - the pytest fixture imported above
    headers, user, group = auth_context
    suffix = uuid.uuid4().hex
    other = db.add_user('batch-' + suffix, suffix + '@example.test', 'password-123', ['users'], group['id'])
    batch = 'batch-' + suffix
    def save(owner, run, index):
        return db.add_item({'id': str(uuid.uuid4()), 'user_id': owner, 'input': 'batch filter example',
            'score': {'instructions': []}, 'svg': '<svg/>', 'at': 1700000000000 + index,
            'batch_run_id': run, 'batch_line_number': index})
    try:
        mine = save(user['id'], batch, 1)
        save(user['id'], batch + '-other', 2)
        foreign = save(other['id'], batch, 3)
        db.set_item_for_share(other['id'], foreign['id'], True, group['id'])
        for query in ({'batch_run_id': batch}, {'batch_run_id': batch, 'q': 'batch filter'}):
            response = client.get('/api/history', params=query, headers=headers)
            assert response.status_code == 200
            assert [row['id'] for row in response.json()['items']] == [mine['id']]
            assert response.json()['total'] == 1
        ordinary = client.get('/api/history', headers=headers).json()
        assert foreign['id'] in {row['id'] for row in ordinary['items']}
    finally:
        db.delete_user(other['id'], cascade=True)
