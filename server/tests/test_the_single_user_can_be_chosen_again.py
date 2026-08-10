"""Stage H: the account a single-user server opens as can be moved.

Single-user mode pins one account and logs in as it automatically. Until now the
pin was only ever written by resolution -- oldest administrator, or the account
created for an empty database -- and there was no way to say "it should be this
person instead".

Deliberately in this stage and not with single-user mode itself. Before the
permission-group scope landed, not even an administrator could see another
account's work, so moving the pin emptied the screen: the same database, the
same works, and nothing on it. Moving it is only safe once someone can still see
what was there.

Two refusals, both 400:

* The receiving account must hold `admins`. Anyone else opens the app to a
  settings screen they cannot reach and cannot change the LLM connection, which
  is the whole point of a server that belongs to one person.
* The mode must be on. Nothing reads the pin when it is off, so a write would
  look like it had taken effect and change nothing.

And one thing that must NOT happen: sessions already open are left alone. The
pin decides who the NEXT automatic login becomes. Revoking the current session
would drop whoever is working right now -- usually the person moving the pin.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


def _member(prefix: str, groups: list[str]) -> tuple[dict, dict[str, str], str]:
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=groups,
        group_id=None,
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token


@pytest.fixture
def single_user_mode(monkeypatch):
    """Turn the mode on for one test and put the pin back afterwards."""
    monkeypatch.setenv("INKU_SINGLE_USER", "1")
    before = db.single_user_pinned_id()
    yield
    stored = db._read_app_setting(db._SINGLE_USER_SETTING_KEY) or {}
    db._write_app_setting(db._SINGLE_USER_SETTING_KEY, {**stored, "user_id": before})


@pytest.fixture
def people():
    admin, admin_headers, admin_token = _member("pin-admin", ["admins"])
    successor, _headers, successor_token = _member("pin-successor", ["admins"])
    plain, _plain_headers, plain_token = _member("pin-plain", ["users"])
    try:
        yield admin, admin_headers, successor, plain
    finally:
        for user, token in ((admin, admin_token), (successor, successor_token), (plain, plain_token)):
            db.delete_session(token)
            db.delete_user(user["id"], cascade=True)


# --- T-24: the pin moves, and open sessions survive --------------------------


def test_t24_the_pin_moves_to_the_named_account(single_user_mode, people) -> None:
    _admin, headers, successor, _plain = people
    response = client.put(
        "/api/settings/single-user", headers=headers, json={"user_id": successor["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == successor["id"]
    assert db.single_user_pinned_id() == successor["id"]
    # And the next automatic login resolves to the new account.
    assert db.single_user_account()["id"] == successor["id"]


def test_t24_the_session_that_moved_the_pin_still_works(single_user_mode, people) -> None:
    _admin, headers, successor, _plain = people
    client.put("/api/settings/single-user", headers=headers, json={"user_id": successor["id"]})
    still_there = client.get("/api/settings/single-user", headers=headers)
    assert still_there.status_code == 200, "moving the pin logged out the caller"
    assert still_there.json()["user_id"] == successor["id"]


# --- T-25: and refuses the two cases it must (control) -----------------------


def test_t25_the_pin_will_not_move_to_an_account_without_admins(single_user_mode, people) -> None:
    _admin, headers, _successor, plain = people
    before = db.single_user_pinned_id()
    response = client.put("/api/settings/single-user", headers=headers, json={"user_id": plain["id"]})
    assert response.status_code == 400, response.text
    assert db.single_user_pinned_id() == before, "the pin moved despite the refusal"


def test_t25_the_pin_will_not_move_while_the_mode_is_off(people, monkeypatch) -> None:
    monkeypatch.delenv("INKU_SINGLE_USER", raising=False)
    _admin, headers, successor, _plain = people
    before = db.single_user_pinned_id()
    response = client.put(
        "/api/settings/single-user", headers=headers, json={"user_id": successor["id"]}
    )
    assert response.status_code == 400, response.text
    assert db.single_user_pinned_id() == before


def test_the_status_lists_only_accounts_that_could_receive_the_pin(single_user_mode, people) -> None:
    _admin, headers, successor, plain = people
    body = client.get("/api/settings/single-user", headers=headers).json()
    eligible = {candidate["id"] for candidate in body["eligible"]}
    assert successor["id"] in eligible
    assert plain["id"] not in eligible, "an account that cannot hold the pin is offered anyway"
