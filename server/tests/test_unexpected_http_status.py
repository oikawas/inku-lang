import sqlite3

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from inku_server.api_core.routers import public, render, users


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
        assert error.value.detail == 'svg render failed'


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
        if status == 500:
            assert error.value.detail == 'group create failed'


def test_empty_paint_stream_hides_exception_details_in_development(monkeypatch, caplog):
    monkeypatch.setenv('INKU_ENV', 'development')
    monkeypatch.setattr(render._pipeline_compat, 'paint_events', lambda *_: iter(()))
    with pytest.raises(HTTPException) as error:
        render.api_paint_stream(render.PaintRequest(description='A circle'), actor={'id': 'owner'})
    assert error.value.status_code == 500
    assert error.value.detail == 'paint failed'
    assert any(record.exc_info and record.exc_info[0] is StopIteration for record in caplog.records)


def test_demo_instruction_hides_exception_details_in_development(monkeypatch, caplog):
    monkeypatch.setenv('INKU_ENV', 'development')
    monkeypatch.setattr(public._db, 'get_model_settings', lambda: {})
    monkeypatch.setattr(public, '_model_offered_to', lambda *args, **kwargs: True)

    def fail(*args, **kwargs):
        raise RuntimeError('secret provider detail')

    monkeypatch.setattr(public, '_generate_demo_instruction', fail)
    with pytest.raises(HTTPException) as error:
        public.api_demo_instruction(
            public.DemoInstructionBody(seed_phrase='A circle', instruction_lang='en'), {'id': 'owner'},
        )
    assert error.value.status_code == 502
    assert error.value.detail == 'demo instruction failed'
    assert 'secret provider detail' in caplog.text
