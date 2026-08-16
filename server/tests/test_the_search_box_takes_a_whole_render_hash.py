"""The history search box accepts a whole render hash, not only its last four.

The UI prints four characters on a work's chip and its copy button puts the
whole hash on the clipboard. Only the four-character form was ever recognised,
so pasting back what the copy button gave you fell through to the full-text
path, which searches the description and the DDL and never the hash -- the
search came back empty for the one string the UI had just handed over.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)

DESCRIPTION = "しずかな円がひとつ"


def _item(user_id: str, at: int, label: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": at,
        "input": label,
        "source_text": label,
        "ddl": "背景を白で塗る。",
        "score": {"canvas": "square", "instructions": []},
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
        "history_visibility": "normal",
    }


def _user() -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"hash-search-group-{suffix}")
    user = db.add_user(
        username=f"hash-search-{suffix}",
        email=f"hash-search-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def _cleanup(user: dict, token: str, group_id: str) -> None:
    db.delete_all(user["id"])
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group_id)


def _found_ids(headers: dict[str, str], query: str) -> list[str]:
    response = client.get("/api/history", headers=headers, params={"limit": 100, "q": query})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


@pytest.fixture
def world():
    user, headers, token, group_id = _user()
    try:
        wanted = db.add_item(_item(user["id"], 1000, DESCRIPTION))
        db.add_item(_item(user["id"], 2000, "べつの記述"))
        stored = db.get_items(user["id"], [wanted["id"]])[0]
        render_hash = stored.get("render_hash") or db.render_hash_for_item(stored)
        assert render_hash, "the work under test has no render hash"
        yield {"headers": headers, "id": wanted["id"], "hash": render_hash}
    finally:
        _cleanup(user, token, group_id)


def test_t142_a_whole_render_hash_finds_the_work_it_names(world):
    """T-142  the whole hash finds the work, in every shape the UI hands over

    `rh3:<64 hex>` is what the copy button writes. The bare 64 hex is what a
    reader gets after trimming the prefix, and the upper-case form is what a
    reader gets after copying it out of a document that shouted it.
    """
    whole = world["hash"]
    bare = whole.split(":", 1)[1]
    for shape in (whole, bare, bare.upper()):
        assert world["id"] in _found_ids(world["headers"], shape), shape


def test_t143_the_last_four_characters_still_find_it(world):
    """T-143  the shape that already worked was not traded away for the new one"""
    short = db.render_hash_short(world["hash"])
    assert short and len(short) == 4
    assert world["id"] in _found_ids(world["headers"], short)


def test_t144_a_whole_hash_does_not_go_down_the_full_text_path(world):
    """T-144  the hash leaves the FTS path, which is where it used to be lost

    T-142 could be satisfied by a hash that happened to sit in the description,
    so the route matters as much as the result: the full-text index carries the
    description and the DDL and no hash at all.
    """
    whole = world["hash"]
    assert not db._use_history_fts(whole)
    assert not db._use_history_fts(whole.split(":", 1)[1])
    assert db._use_history_fts(DESCRIPTION), "this search should still use FTS"


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("0" * 63, id="one-short-of-a-hash"),
        pytest.param("0" * 65, id="one-over-a-hash"),
        pytest.param("g" * 64, id="right-length-but-not-hex"),
        pytest.param("rh3:" + "0" * 63, id="prefixed-but-one-short"),
    ],
)
def test_t145_text_that_is_not_a_hash_is_still_read_as_text(query):
    """T-145  widening the shape did not swallow ordinary searches

    Each of these is close to a hash and is not one. If any were treated as a
    hash it would stop matching descriptions, which is a quiet loss: the search
    would simply return less.
    """
    assert not db._is_render_hash_suffix_search(query)


def test_t146_the_description_still_finds_the_work(world):
    """T-146  the ordinary search was not disturbed by any of this"""
    assert world["id"] in _found_ids(world["headers"], DESCRIPTION)
