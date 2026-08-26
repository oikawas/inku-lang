"""Direct authority and transaction coverage for current-user profile updates."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _updater_or_skip():
    updater = getattr(accounts, "CurrentUserProfileUpdater", None)
    if updater is None:
        pytest.skip("current-user profile updater is intentionally absent during fail-first")
    return updater


def test_accounts_owns_current_profile_updater_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    updater = getattr(accounts, "CurrentUserProfileUpdater", None)
    assert updater is not None, "persistence.accounts must own current-user profile updates"
    assert is_dataclass(updater) and updater.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        updater(*([None] * 4)).session_factory = None

    for name in ("_current_user_profile_updater", "update_current_user_profile"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], tuple[object, ...], dict[str, object]]] = []

    class RecordingUpdater:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def update_current_user_profile(self, *args: object, **kwargs: object) -> str:
            calls.append((self.dependencies, args, kwargs))
            return "sentinel"

    monkeypatch.setattr(db._accounts, "CurrentUserProfileUpdater", RecordingUpdater)
    dependencies = tuple(object() for _ in range(4))
    monkeypatch.setattr(db, "SessionLocal", dependencies[0])
    monkeypatch.setattr(db, "verify_password", dependencies[1])
    monkeypatch.setattr(db, "_hash_password", dependencies[2])
    monkeypatch.setattr(db, "_user_to_dict", dependencies[3])

    assert db.update_current_user_profile("u", email=" mail ") == "sentinel"
    assert calls == [
        (
            dependencies,
            ("u",),
            {"email": " mail ", "password": None, "current_password": None},
        )
    ]


class _Session:
    def __init__(self, row: object | None) -> None:
        self.row = row
        self.events: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, row_type: object, key: object) -> object | None:
        self.events.append(("get", getattr(row_type, "__tablename__", "unknown"), key))
        if getattr(row_type, "__tablename__", "") == "user_accounts":
            return self.row
        return SimpleNamespace(name="Group")

    def commit(self) -> None:
        self.events.append("commit")

    def refresh(self, row: object) -> None:
        self.events.append(("refresh", row))


def _build(session: _Session, *, password_matches: bool = True):
    updater_type = _updater_or_skip()

    def project(row: object, group_name: str | None = None) -> dict:
        session.events.append(("project", row, group_name))
        return {"id": row.id, "email": row.email, "group_name": group_name}

    return updater_type(
        lambda: session,
        lambda current, stored: password_matches and current == "old-password" and stored == "old-hash",
        lambda password: f"hash:{password}",
        project,
    )


def test_current_profile_updater_preserves_missing_email_and_projection() -> None:
    missing = _Session(None)
    assert _build(missing).update_current_user_profile("missing", email="x@example.test") is None
    assert "commit" not in missing.events

    row = SimpleNamespace(id="u", email="old@example.test", password_hash="old-hash", group_id="g")
    invalid = _Session(row)
    with pytest.raises(ValueError, match="email is required"):
        _build(invalid).update_current_user_profile("u", email=" ")
    assert "commit" not in invalid.events

    session = _Session(row)
    result = _build(session).update_current_user_profile("u", email=" new@example.test ")
    assert row.email == "new@example.test"
    assert session.events == [
        ("get", "user_accounts", "u"),
        "commit",
        ("refresh", row),
        ("get", "user_groups", "g"),
        ("project", row, "Group"),
    ]
    assert result == {"id": "u", "email": "new@example.test", "group_name": "Group"}


def test_current_profile_updater_preserves_password_verification_and_hashing() -> None:
    row = SimpleNamespace(id="u", email="u@example.test", password_hash="old-hash", group_id=None)

    for current, matches in ((None, True), ("wrong", False)):
        session = _Session(row)
        with pytest.raises(ValueError, match="current password is invalid"):
            _build(session, password_matches=matches).update_current_user_profile(
                "u", password="new-password", current_password=current
            )
        assert "commit" not in session.events
        assert row.password_hash == "old-hash"

    session = _Session(row)
    _build(session).update_current_user_profile(
        "u", password="new-password", current_password="old-password"
    )
    assert row.password_hash == "hash:new-password"
    assert "commit" in session.events


def test_current_profile_updater_propagates_session_errors() -> None:
    class BrokenSession(_Session):
        def get(self, _row_type: object, _key: object) -> object:
            raise RuntimeError("get failed")

    with pytest.raises(RuntimeError, match="get failed"):
        _build(BrokenSession(None)).update_current_user_profile("u")
