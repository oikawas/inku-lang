"""I-328: an administrator who forgot the password has a way back.

The bootstrap password is read only while the database has no accounts, and the
web UI is the only other place a password changes.  An install with one
administrator who forgot theirs had no way in at all; `inku-admin
reset-password` is that way, and these tests drive it through its own entry
point rather than calling db.update_user, because the entry point is the thing
that has to exist inside the published image.
"""
from __future__ import annotations

import io
import sys
import tomllib
import uuid
from importlib import import_module
from pathlib import Path

import pytest

from inku_server import admin
from inku_server import db


@pytest.fixture
def account():
    """A throwaway account -- never the suite's own `admin`.

    conftest hands the whole session one database, and other files sign in as
    `admin` with the bootstrap password.  Resetting that account here would
    break them depending on the order the files happened to run in.
    """
    # This file imports no API module, so nothing else has built the schema
    # when it runs on its own.
    db.init_db()
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        username=f"forgot-{suffix}",
        email=f"forgot-{suffix}@example.test",
        password="first-password",
        permission_groups=["users"],
        group_id=None,
    )
    yield user
    db.delete_user(user["id"], cascade=True)


def _password_hash(user_id: str) -> str:
    with db.SessionLocal() as session:
        return session.get(db.UserAccountRow, user_id).password_hash


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_a_reset_password_signs_in_and_the_old_one_does_not(account, monkeypatch, capsys):
    """T-290"""
    _feed(monkeypatch, "second-password\n")

    code = admin.main(["reset-password", "--username", account["username"], "--password-stdin"])

    assert code == 0
    assert db.authenticate_user(account["username"], "second-password") is not None
    assert db.authenticate_user(account["username"], "first-password") is None
    assert account["username"] in capsys.readouterr().out


def test_a_short_password_is_refused_and_the_hash_does_not_move(account, monkeypatch, capsys):
    """T-291"""
    before = _password_hash(account["id"])
    _feed(monkeypatch, "short12\n")  # seven characters

    code = admin.main(["reset-password", "--username", account["username"], "--password-stdin"])

    assert code == 2
    assert "8" in capsys.readouterr().err
    assert _password_hash(account["id"]) == before
    assert db.authenticate_user(account["username"], "first-password") is not None


def test_an_unknown_username_lists_the_names_that_exist(account, monkeypatch, capsys):
    """T-292"""
    before = _password_hash(account["id"])
    _feed(monkeypatch, "second-password\n")

    code = admin.main(["reset-password", "--username", "nobody-by-that-name", "--password-stdin"])

    assert code == 1
    # The person who forgot the password may also have forgotten which name
    # they put in INKU_BOOTSTRAP_ADMIN_USERNAME.
    assert account["username"] in capsys.readouterr().err
    assert _password_hash(account["id"]) == before


def test_the_password_can_arrive_on_stdin_without_touching_argv(account, monkeypatch):
    """T-293"""
    secret = "two words and a trailing space "
    argv = ["reset-password", "--username", account["username"], "--password-stdin"]
    _feed(monkeypatch, secret + "\n")

    code = admin.main(argv)

    assert code == 0
    assert not any(secret in argument for argument in argv)
    # Only the newline comes off: the spaces are part of the password.
    assert db.authenticate_user(account["username"], secret) is not None


def test_the_declared_console_script_resolves_to_a_callable():
    """T-294

    The image runs `inku-admin`, which nothing else in the suite walks: a typo
    in the declaration would ship an entry point that cannot start, and every
    other test here would still be green.
    """
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    target = pyproject["project"]["scripts"]["inku-admin"]
    module_name, _, attribute = target.partition(":")

    resolved = getattr(import_module(module_name), attribute)

    assert callable(resolved)
