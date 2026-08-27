"""Direct ownership coverage for startup migration baseline callbacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from inku_server import db
from inku_server.persistence import migrations


def _owner_type_or_fail():
    owner_type = getattr(migrations, "MigrationBaselineCallbacks", None)
    assert owner_type is not None
    return owner_type


def _owner(events):
    class Metadata:
        def create_all(self, **kwargs):
            events.append(("metadata", kwargs))

    class RecordingSession:
        def __enter__(self):
            events.append(("session.enter", self))
            return self

        def __exit__(self, *args):
            events.append(("session.exit", self))

        def flush(self):
            events.append(("flush", self))

    session = RecordingSession()

    def session_factory(**kwargs):
        events.append(("session", kwargs))
        return session

    def callback(name):
        return lambda received: events.append((name, received))

    def migrate_columns(connection, *, include_fts):
        events.append(("columns", connection, include_fts))

    return _owner_type_or_fail()(
        Metadata(),
        session_factory,
        callback("default_group"),
        callback("permission_groups"),
        callback("bootstrap_admin"),
        migrate_columns,
        callback("role_mirror"),
        callback("unowned_history"),
        callback("identity_lineage"),
    ), session


def test_owner_and_outcome_are_frozen_and_metadata_uses_exact_bind() -> None:
    events = []
    owner, _session = _owner(events)
    assert migrations.MigrationOutcome.__dataclass_params__.frozen
    assert type(owner).__dataclass_params__.frozen
    with pytest.raises(AttributeError):
        owner.metadata = object()
    connection = object()

    assert owner.create_schema(connection) is None
    assert events == [("metadata", {"bind": connection})]


def test_fresh_callback_uses_exact_session_kwargs_order_and_one_flush() -> None:
    events = []
    owner, session = _owner(events)
    connection = object()

    assert owner.seed_fresh(connection) is None
    assert events == [
        (
            "session",
            {"bind": connection, "autocommit": False, "autoflush": False},
        ),
        ("session.enter", session),
        ("default_group", session),
        ("permission_groups", session),
        ("bootstrap_admin", session),
        ("flush", session),
        ("session.exit", session),
    ]


def test_legacy_callback_preserves_columns_session_and_callback_order() -> None:
    events = []
    owner, session = _owner(events)
    connection = object()

    assert owner.apply_legacy(connection) is None
    assert events == [
        ("columns", connection, False),
        (
            "session",
            {"bind": connection, "autocommit": False, "autoflush": False},
        ),
        ("session.enter", session),
        ("default_group", session),
        ("permission_groups", session),
        ("bootstrap_admin", session),
        ("role_mirror", session),
        ("unowned_history", session),
        ("identity_lineage", session),
        ("flush", session),
        ("session.exit", session),
    ]


def test_init_db_builds_owner_from_live_dependencies_and_assigns_outcome(
    monkeypatch,
) -> None:
    created = []
    ensured = []
    metadata = object()
    engine = object()
    session_factory = object()
    callbacks = [object() for _ in range(7)]
    enabled = object()

    class RecordingOwner:
        def __init__(self, *args):
            created.append(args)

        def create_schema(self, connection):
            return connection

        def seed_fresh(self, connection):
            return connection

        def apply_legacy(self, connection):
            return connection

    class Outcome:
        fts_enabled = enabled

    def ensure_current_schema(**kwargs):
        ensured.append(kwargs)
        return Outcome()

    monkeypatch.setattr(migrations, "MigrationBaselineCallbacks", RecordingOwner, raising=False)
    monkeypatch.setattr(db, "Base", type("Base", (), {"metadata": metadata}))
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "Session", session_factory)
    monkeypatch.setattr(db, "sqlite_database_path", lambda *args, **kwargs: None)
    monkeypatch.setattr(db, "ensure_current_schema", ensure_current_schema)
    monkeypatch.setattr(db, "_HISTORY_FTS_ENABLED", object())
    callback_names = (
        "_ensure_default_user_group",
        "_ensure_permission_groups",
        "_ensure_bootstrap_admin",
        "_migrate_columns",
        "_migrate_roles_to_permission_groups",
        "_assign_unowned_history_to_admin",
        "_backfill_history_identity_and_lineage",
    )
    for name, callback in zip(callback_names, callbacks, strict=True):
        monkeypatch.setattr(db, name, callback)

    assert db.init_db() is None
    assert created == [(metadata, session_factory, *callbacks)]
    owner = ensured[0]
    assert owner["engine"] is engine
    assert owner["database_path"] is None
    instance = owner["create_schema"].__self__
    assert owner["create_schema"] == instance.create_schema
    assert owner["seed_fresh"] == instance.seed_fresh
    assert owner["apply_legacy"] == instance.apply_legacy
    assert db._HISTORY_FTS_ENABLED is enabled


def test_moved_private_helpers_no_longer_remain_in_db_module() -> None:
    source = Path(db.__file__).read_text()
    for helper_name in (
        "_migration_session",
        "_seed_fresh_database",
        "_apply_legacy_baseline",
    ):
        assert f"def {helper_name}(" not in source
