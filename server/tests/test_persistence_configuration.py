from __future__ import annotations

import re
from pathlib import Path

import pytest

from inku_server.persistence import config
from inku_server.persistence import engine as persistence_engine

ROOT = Path(__file__).resolve().parents[2]


def test_defaults_and_overrides_keep_the_existing_locations(tmp_path):
    expected_directory = Path.home() / ".local" / "share" / "inku"
    defaults = config.resolve_persistence_config({})

    assert defaults.canonical_url == "sqlite:///" + str(expected_directory / "inku.db")
    assert defaults.thumbnail_url == "sqlite:///" + str(expected_directory / "thumbs.db")
    assert defaults.canonical_is_default is True

    canonical_url = f"sqlite:///{tmp_path / 'works.db'}"
    derived = config.resolve_persistence_config({config.CANONICAL_DB_ENV: canonical_url})
    assert derived.canonical_url == canonical_url
    assert derived.thumbnail_url == f"sqlite:///{tmp_path / 'thumbs.db'}"

    thumbnail_url = f"sqlite:///{tmp_path / 'derived.db'}"
    explicit = config.resolve_persistence_config(
        {
            config.CANONICAL_DB_ENV: canonical_url,
            config.THUMBNAIL_DB_ENV: thumbnail_url,
        }
    )
    assert explicit.thumbnail_url == thumbnail_url


@pytest.mark.parametrize(
    ("values", "setting"),
    [
        ({config.CANONICAL_DB_ENV: "postgresql://example.invalid/inku"}, config.CANONICAL_DB_ENV),
        (
            {
                config.CANONICAL_DB_ENV: "sqlite:///:memory:",
                config.THUMBNAIL_DB_ENV: "mysql://example.invalid/thumbs",
            },
            config.THUMBNAIL_DB_ENV,
        ),
    ],
)
def test_non_sqlite_configuration_is_rejected_without_echoing_the_url(values, setting):
    with pytest.raises(config.PersistenceConfigurationError, match=setting) as raised:
        config.resolve_persistence_config(values)

    assert "example.invalid" not in str(raised.value)


@pytest.mark.parametrize(
    ("url", "setting"),
    [
        ("postgresql://example.invalid/inku", config.CANONICAL_DB_ENV),
        ("mysql://example.invalid/thumbs", config.THUMBNAIL_DB_ENV),
    ],
)
def test_invalid_backend_never_reaches_sqlalchemy_engine_factory(monkeypatch, url, setting):
    calls = []

    def forbidden_factory(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("engine factory must not be called")

    monkeypatch.setattr(persistence_engine, "_sqlalchemy_create_engine", forbidden_factory)

    with pytest.raises(config.PersistenceConfigurationError, match=setting):
        persistence_engine.create_sqlite_engine(
            url,
            setting=setting,
            pragmas=persistence_engine.CANONICAL_SQLITE_PRAGMAS,
        )

    assert calls == []


def test_file_engines_install_the_existing_pragmas(tmp_path):
    canonical = persistence_engine.create_sqlite_engine(
        f"sqlite:///{tmp_path / 'canonical.db'}",
        setting=config.CANONICAL_DB_ENV,
        pragmas=persistence_engine.CANONICAL_SQLITE_PRAGMAS,
    )
    thumbnails = persistence_engine.create_sqlite_engine(
        f"sqlite:///{tmp_path / 'thumbs.db'}",
        setting=config.THUMBNAIL_DB_ENV,
        pragmas=persistence_engine.THUMBNAIL_SQLITE_PRAGMAS,
    )
    try:
        with canonical.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 10_000
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
        with thumbnails.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
    finally:
        canonical.dispose()
        thumbnails.dispose()


def test_memory_database_has_no_filesystem_path():
    assert config.sqlite_database_path(
        "sqlite:///:memory:",
        setting=config.CANONICAL_DB_ENV,
    ) is None


def test_runtime_consumers_use_the_resolved_sqlite_engines():
    from inku_server import db, thumbs_db

    assert db.engine.dialect.name == "sqlite"
    assert thumbs_db.engine.dialect.name == "sqlite"
    assert str(db.engine.url) == config.PERSISTENCE_CONFIG.canonical_url
    assert str(thumbs_db.engine.url) == config.PERSISTENCE_CONFIG.thumbnail_url
    assert db.database_info()["is_default"] is False
    assert thumbs_db.thumbs_db_path() == str(
        config.sqlite_database_path(
            config.PERSISTENCE_CONFIG.thumbnail_url,
            setting=config.THUMBNAIL_DB_ENV,
        )
    )

    with db.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 10_000


def test_existing_consumers_use_the_public_persistence_owners():
    package = ROOT / "server/src/inku_server"
    db_source = (package / "db.py").read_text(encoding="utf-8")
    thumbnail_source = (package / "thumbs_db.py").read_text(encoding="utf-8")
    migration_source = (package / "migrate_history.py").read_text(encoding="utf-8")
    runtime_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(package.rglob("*.py"))
    )

    assert "from .persistence.config import" in db_source
    assert "from .persistence.engine import" in db_source
    assert "from .persistence.config import" in thumbnail_source
    assert "from .persistence.engine import" in thumbnail_source
    assert "from .db import _DB_URL" not in thumbnail_source
    assert re.search(r"\b_DB_URL\b", runtime_sources) is None
    assert "PostgreSQL" not in db_source
    assert "PostgreSQL" not in migration_source
