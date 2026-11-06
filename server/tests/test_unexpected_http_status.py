import sqlite3

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from inku_server.api_core.routers import render, users


@pytest.mark.parametrize('failure,status', [(ValueError('bad input'), 422), (RuntimeError('secret engine details'), 500)])
def test_render_distinguishes_invalid_input_from_unexpected_errors(monkeypatch, failure, status):
    monkeypatch.setenv('INKU_ENV', 'development')
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(render, '_render_score_svg', fail)
    with pytest.raises(HTTPException) as error:
        render.api_render_svg(render.RenderSvgRequest(score={}), {'id': 'owner'})
    assert error.value.status_code == status
    if status == 500:
        assert 'secret engine details' not in str(error.value.detail)


def test_group_create_preserves_unique_conflicts_but_redacts_other_failures(monkeypatch):
    monkeypatch.setenv('INKU_ENV', 'development')
    monkeypatch.setattr(users._db, 'has_permission_group', lambda *_: True)
    duplicate = sqlite3.IntegrityError('duplicate')
    duplicate.sqlite_errorcode = 2067
    for cause, status in [(IntegrityError('insert', {}, duplicate), 409), (RuntimeError('secret db detail'), 500)]:
        def fail(*args, **kwargs):
            raise cause
        monkeypatch.setattr(users._db, 'add_user_group', fail)
        with pytest.raises(HTTPException) as error:
            users.api_user_groups_create(users.UserGroupCreateBody(name='group'), {'id': 'owner'})
        assert error.value.status_code == status
        assert 'secret db detail' not in str(error.value.detail)
