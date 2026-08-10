"""A server that belongs to one person opens without asking who they are.

Every case runs in a subprocess against its own database file, because the
flag and the database URL are both read once at import: a test that flipped
them in place would be measuring the module the previous test left behind.

The negative cases matter as much as the positive ones.  "Still 401 with the
flag off" is what keeps an implementation that resolved to a constant from
passing, and it is checked against the same routes the positive case uses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


_SERVER_ROOT = Path(__file__).parents[1]


def _run(code: str, db_path: Path, *, single_user: str | None, bootstrap_password: str | None = None) -> dict:
    env = os.environ.copy()
    env["INKU_DB_URL"] = f"sqlite:///{db_path}"
    env.pop("INKU_SINGLE_USER", None)
    env.pop("INKU_BOOTSTRAP_ADMIN_PASSWORD", None)
    if single_user is not None:
        env["INKU_SINGLE_USER"] = single_user
    if bootstrap_password is not None:
        env["INKU_BOOTSTRAP_ADMIN_PASSWORD"] = bootstrap_password
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_SERVER_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


_CLIENT_PREAMBLE = """
import json
from fastapi.testclient import TestClient
from inku_server import db
from inku_server.api import app
client = TestClient(app)
"""


# --- T-1: single-user mode on, no credentials -------------------------------


def test_single_user_mode_answers_an_unauthenticated_request(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
me = client.get('/api/auth/me')
print(json.dumps({
    'me_status': me.status_code,
    'username': me.json().get('username'),
    'role': me.json().get('role'),
}))
""",
        tmp_path / "on.db",
        single_user="1",
    )
    assert payload["me_status"] == 200
    assert payload["role"] == "admin"
    assert payload["username"] == "admin"


def test_single_user_mode_answers_a_history_read(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
r = client.get('/api/history')
print(json.dumps({'status': r.status_code}))
""",
        tmp_path / "on-history.db",
        single_user="1",
    )
    assert payload["status"] == 200


def test_single_user_mode_answers_an_administrator_only_route(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
r = client.get('/api/users')
print(json.dumps({'status': r.status_code, 'count': len(r.json()) if r.status_code == 200 else None}))
""",
        tmp_path / "on-admin.db",
        single_user="1",
    )
    assert payload["status"] == 200
    assert payload["count"] == 1


# --- T-2: the flag off keeps every one of those routes at 401 ---------------


def test_without_the_flag_the_same_request_is_still_rejected(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
print(json.dumps({'status': client.get('/api/auth/me').status_code}))
""",
        tmp_path / "off.db",
        single_user=None,
        bootstrap_password="test-admin-password",
    )
    assert payload["status"] == 401


def test_without_the_flag_a_history_read_is_still_rejected(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
print(json.dumps({'status': client.get('/api/history').status_code}))
""",
        tmp_path / "off-history.db",
        single_user=None,
        bootstrap_password="test-admin-password",
    )
    assert payload["status"] == 401


# --- T-4: the banner tells the client, and tells it only this ---------------


def test_api_info_reports_the_mode_when_it_is_on(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
print(json.dumps(client.get('/api/info').json()))
""",
        tmp_path / "info-on.db",
        single_user="1",
    )
    assert payload["single_user_mode"] is True


def test_api_info_reports_the_mode_when_it_is_off(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
print(json.dumps(client.get('/api/info').json()))
""",
        tmp_path / "info-off.db",
        single_user=None,
        bootstrap_password="test-admin-password",
    )
    assert payload["single_user_mode"] is False


def test_app_info_gained_exactly_one_field():
    """A set difference, not a count.

    The API-surface baseline compares counts as well as content, and its three
    counts do not move when a field is added to an existing model -- a field
    that quietly vanished would leave 82/82/82 untouched.  So name what the
    model carries and diff it against the recorded shape.
    """
    from inku_server.api import app

    schema = app.openapi()["components"]["schemas"]["AppInfoResponse"]
    current = set(schema["properties"])
    before = {
        "name",
        "version",
        "release_version",
        "build_number",
        "developer_mode",
        "render_engine_id",
        "render_engine_version",
        "ddl_version",
        "ddl_engine_version",
    }
    assert current - before == {"single_user_mode"}
    assert before - current == set()


# --- T-5: who the single user is, and that it stops moving ------------------


def test_an_empty_database_gets_its_one_account_made(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
before = len(db.list_users())
me = client.get('/api/auth/me').json()
print(json.dumps({
    'before': before,
    'after': len(db.list_users()),
    'role': me['role'],
    'pinned': db.single_user_pinned_id() == me['id'],
}))
""",
        tmp_path / "empty.db",
        single_user="1",
    )
    assert payload["before"] == 0
    assert payload["after"] == 1
    assert payload["role"] == "admin"
    assert payload["pinned"] is True


def test_a_populated_database_picks_the_oldest_administrator(tmp_path: Path):
    payload = _run(
        _CLIENT_PREAMBLE + """
first = db.add_user('elder', 'elder@example.test', 'password-1', 'admin', None)
second = db.add_user('younger', 'younger@example.test', 'password-2', 'admin', None)
with db.SessionLocal() as session:
    row = session.get(db.UserAccountRow, second['id'])
    row.at = first['at'] + 1000
    session.commit()
me = client.get('/api/auth/me').json()
print(json.dumps({'chosen': me['username'], 'made_none': len(db.list_users())}))
""",
        tmp_path / "populated.db",
        single_user="1",
    )
    assert payload["chosen"] == "elder"
    assert payload["made_none"] == 2


def test_an_account_created_earlier_does_not_steal_the_pin(tmp_path: Path):
    """The pin is what makes a restored backup name the same person.

    Deriving "oldest administrator" on every call would move the answer the
    moment an older row appears -- or the moment the current one is deleted --
    and the owner would see their works vanish.
    """
    payload = _run(
        _CLIENT_PREAMBLE + """
first = client.get('/api/auth/me').json()
older = db.add_user('older', 'older@example.test', 'password-1', 'admin', None)
with db.SessionLocal() as session:
    row = session.get(db.UserAccountRow, older['id'])
    row.at = 1
    session.commit()
second = client.get('/api/auth/me').json()
print(json.dumps({'same': first['id'] == second['id'], 'username': second['username']}))
""",
        tmp_path / "pin.db",
        single_user="1",
    )
    assert payload["same"] is True
    assert payload["username"] == "admin"


# --- T-8: the machine default is off, the distribution turns it on ----------


def test_the_application_default_is_off():
    """No variable, no single-user mode.

    An existing deployment must not lose its login screen by upgrading.
    """
    from inku_server import db

    previous = os.environ.pop("INKU_SINGLE_USER", None)
    try:
        assert db.single_user_mode_enabled() is False
    finally:
        if previous is not None:
            os.environ["INKU_SINGLE_USER"] = previous


def test_the_distribution_turns_it_on():
    compose = (_SERVER_ROOT.parent / "compose.yaml").read_text(encoding="utf-8")
    assert "INKU_SINGLE_USER: ${INKU_SINGLE_USER:-1}" in compose


# --- T-9: the account can be renamed without losing itself ------------------


def test_renaming_the_single_user_does_not_move_the_pin(tmp_path: Path):
    """The pin holds an id, not a name, so the name is free to change."""
    payload = _run(
        _CLIENT_PREAMBLE + """
before = client.get('/api/auth/me').json()
renamed = client.patch(f"/api/users/{before['id']}", json={'username': 'oikawa'})
after = client.get('/api/auth/me').json()
print(json.dumps({
    'rename_status': renamed.status_code,
    'username': after['username'],
    'same_id': after['id'] == before['id'],
    'pin_holds_id': db.single_user_pinned_id() == before['id'],
}))
""",
        tmp_path / "rename.db",
        single_user="1",
    )
    assert payload["rename_status"] == 200
    assert payload["username"] == "oikawa"
    assert payload["same_id"] is True
    assert payload["pin_holds_id"] is True
