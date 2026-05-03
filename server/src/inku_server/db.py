"""DB layer — SQLite (default) or PostgreSQL via INKU_DB_URL.

  SQLite:     INKU_DB_URL=sqlite:///~/.local/share/inku/inku.db  (default)
  PostgreSQL: INKU_DB_URL=postgresql://user:pass@localhost/inku
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import sqlite3
import uuid
from datetime import datetime
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text, create_engine, func, inspect, or_, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DEFAULT_DB = "sqlite:///" + str(Path.home() / ".local" / "share" / "inku" / "inku.db")
_DB_URL = os.getenv("INKU_DB_URL", _DEFAULT_DB)
_SESSION_MAX_AGE_SECONDS = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))

_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
_logger = logging.getLogger(__name__)
_HISTORY_FTS_ENABLED = False


class Base(DeclarativeBase):
    pass


class HistoryRow(Base):
    __tablename__ = "history"

    id           = Column(String,     primary_key=True)
    user_id      = Column(String,     ForeignKey("user_accounts.id"), nullable=True, index=True)
    at           = Column(BigInteger, nullable=False, index=True)
    input        = Column(Text,       nullable=False, default="")
    ddl          = Column(Text,       nullable=True)
    score        = Column(Text,       nullable=False, default="{}")
    svg          = Column(Text,       nullable=False, default="")
    output_path  = Column(Text,       nullable=True)
    elapsed_ms   = Column(Integer,    nullable=False, default=0)
    stage1_model = Column(String,     nullable=True)
    stage2_model = Column(String,     nullable=True)
    tokens_in    = Column(Integer,    nullable=True)
    tokens_out   = Column(Integer,    nullable=True)
    catalog_id   = Column(String,     nullable=True)
    render_build_number = Column(String, nullable=True)
    render_color_catalog_id = Column(String, nullable=True)
    render_color_catalog_name = Column(String, nullable=True)
    render_color_catalog_sub = Column(String, nullable=True)
    render_color_catalog = Column(Text, nullable=True)
    render_color_map = Column(Text, nullable=True)
    trashed      = Column(Integer,    nullable=False, default=0)
    starred      = Column(Integer,    nullable=False, default=0)


class UserGroupRow(Base):
    __tablename__ = "user_groups"

    id   = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    at   = Column(BigInteger, nullable=False, index=True)


class UserAccountRow(Base):
    __tablename__ = "user_accounts"

    id            = Column(String, primary_key=True)
    username      = Column(String, nullable=False, unique=True, index=True)
    email         = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    role          = Column(String, nullable=False, index=True)
    group_id      = Column(String, ForeignKey("user_groups.id"), nullable=True, index=True)
    ui_theme      = Column(String, nullable=False, default="light")
    settings_tab  = Column(String, nullable=False, default="db")
    image_generation_count = Column(Integer, nullable=False, default=0)
    batch_prompt_history = Column(Text, nullable=False, default="[]")
    demo_settings = Column(Text, nullable=False, default="{}")
    export_templates = Column(Text, nullable=False, default="[]")
    plugin_storage = Column(Text, nullable=False, default="{}")
    at            = Column(BigInteger, nullable=False, index=True)


class UserSessionRow(Base):
    __tablename__ = "user_sessions"

    token_hash = Column(String, primary_key=True)
    user_id    = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    at         = Column(BigInteger, nullable=False, index=True)


class AppSettingRow(Base):
    __tablename__ = "app_settings"

    key   = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    at    = Column(BigInteger, nullable=False, index=True)


USER_ROLES = {"admin", "group_lead", "user"}
ROLE_LABELS = {
    "admin": "管理者",
    "group_lead": "グループリード",
    "user": "ユーザー",
}
_UNSET = object()
_HISTORY_COLUMN_MIGRATIONS = {
    "user_id": "ALTER TABLE history ADD COLUMN user_id VARCHAR",
    "catalog_id": "ALTER TABLE history ADD COLUMN catalog_id VARCHAR",
    "render_build_number": "ALTER TABLE history ADD COLUMN render_build_number VARCHAR",
    "render_color_catalog_id": "ALTER TABLE history ADD COLUMN render_color_catalog_id VARCHAR",
    "render_color_catalog_name": "ALTER TABLE history ADD COLUMN render_color_catalog_name VARCHAR",
    "render_color_catalog_sub": "ALTER TABLE history ADD COLUMN render_color_catalog_sub VARCHAR",
    "render_color_catalog": "ALTER TABLE history ADD COLUMN render_color_catalog TEXT",
    "render_color_map": "ALTER TABLE history ADD COLUMN render_color_map TEXT",
    "trashed": "ALTER TABLE history ADD COLUMN trashed INTEGER NOT NULL DEFAULT 0",
    "starred": "ALTER TABLE history ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
}
_USER_ACCOUNT_COLUMN_MIGRATIONS = {
    "ui_theme": "ALTER TABLE user_accounts ADD COLUMN ui_theme VARCHAR NOT NULL DEFAULT 'light'",
    "settings_tab": "ALTER TABLE user_accounts ADD COLUMN settings_tab VARCHAR NOT NULL DEFAULT 'db'",
    "image_generation_count": (
        "ALTER TABLE user_accounts ADD COLUMN image_generation_count INTEGER NOT NULL DEFAULT 0"
    ),
    "batch_prompt_history": "ALTER TABLE user_accounts ADD COLUMN batch_prompt_history TEXT NOT NULL DEFAULT '[]'",
    "demo_settings": "ALTER TABLE user_accounts ADD COLUMN demo_settings TEXT NOT NULL DEFAULT '{}'",
    "export_templates": "ALTER TABLE user_accounts ADD COLUMN export_templates TEXT NOT NULL DEFAULT '[]'",
    "plugin_storage": "ALTER TABLE user_accounts ADD COLUMN plugin_storage TEXT NOT NULL DEFAULT '{}'",
}
_BATCH_PROMPT_HISTORY_LIMIT = 20
_BATCH_PROMPT_HISTORY_MAX_TEXT = 20_000
_SETTINGS_TABS = {"db", "plugins", "users", "export", "misc"}
_PLUGIN_STORAGE_MAX_BYTES = 20_000
_DEMO_DEFAULT_SETTINGS = {
    "save_db": False,
    "save_files": False,
    "prompt_model": "google/gemma-4-31b-it",
    "seed_phrase": "日本の四季を感じさせる文章を40語以内で生成",
    "interval_seconds": 30,
    "random_color_catalog": False,
}
_EXPORT_TEMPLATE_LIMIT = 20
_EXPORT_TEMPLATE_DEFAULTS = [
    {
        "id": "png-1024",
        "name": "PNG 1024px",
        "description": "PNG / y-axis 1024px",
        "y_px": 1024,
    },
    {
        "id": "png-2048",
        "name": "PNG 2048px",
        "description": "PNG / y-axis 2048px",
        "y_px": 2048,
    },
]
_DEFAULT_DB_BACKUP_DIR = Path.home() / ".local" / "share" / "inku" / "db-backups"
_DB_BACKUP_DIR = Path(os.getenv("INKU_DB_BACKUP_DIR", str(_DEFAULT_DB_BACKUP_DIR))).expanduser()
_DB_BACKUP_SETTINGS_KEY = "db_backup_settings"
_DB_BACKUP_DEFAULT_SETTINGS = {
    "interval_days": 7,
    "max_generations": 4,
    "last_auto_backup_at": 0,
}
_HISTORY_INDEX_MIGRATIONS = (
    ("ix_history_user_id", "CREATE INDEX IF NOT EXISTS ix_history_user_id ON history (user_id)"),
    (
        "ix_history_user_trashed_at",
        "CREATE INDEX IF NOT EXISTS ix_history_user_trashed_at ON history (user_id, trashed, at)",
    ),
    (
        "ix_history_user_starred_trashed_at",
        "CREATE INDEX IF NOT EXISTS ix_history_user_starred_trashed_at ON history (user_id, starred, trashed, at)",
    ),
)


def init_db() -> None:
    if _DB_URL.startswith("sqlite:///"):
        db_path = Path(_DB_URL[len("sqlite:///"):]).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate_columns()
    _ensure_default_user_group()
    _ensure_bootstrap_admin()
    _assign_unowned_history_to_admin()


def _migrate_columns() -> None:
    with engine.begin() as conn:
        try:
            inspector = inspect(conn)
            existing_history_columns = {col["name"] for col in inspector.get_columns("history")}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("failed to inspect history table columns for migration") from exc

        for column, ddl in _HISTORY_COLUMN_MIGRATIONS.items():
            if column in existing_history_columns:
                continue
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to migrate history.{column}") from exc

        try:
            existing_user_columns = {col["name"] for col in inspector.get_columns("user_accounts")}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("failed to inspect user_accounts table columns for migration") from exc

        for column, ddl in _USER_ACCOUNT_COLUMN_MIGRATIONS.items():
            if column in existing_user_columns:
                continue
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to migrate user_accounts.{column}") from exc

        for index_name, ddl in _HISTORY_INDEX_MIGRATIONS:
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to create migration index {index_name}") from exc
        _migrate_history_search(conn)


def _migrate_history_search(conn) -> None:
    global _HISTORY_FTS_ENABLED

    _HISTORY_FTS_ENABLED = False
    if engine.dialect.name != "sqlite":
        return

    table_sql = (
        "CREATE VIRTUAL TABLE IF NOT EXISTS history_fts USING fts5("
        "input, ddl, stage1_model, stage2_model, catalog_id, "
        "content='history', content_rowid='rowid', tokenize='trigram'"
        ")"
    )
    try:
        conn.execute(text(table_sql))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("SQLite FTS5 trigram history search is unavailable; falling back to LIKE search: %s", exc)
        return

    trigger_sql = (
        """
        CREATE TRIGGER IF NOT EXISTS history_fts_ai AFTER INSERT ON history BEGIN
            INSERT INTO history_fts(rowid, input, ddl, stage1_model, stage2_model, catalog_id)
            VALUES (new.rowid, new.input, new.ddl, new.stage1_model, new.stage2_model, new.catalog_id);
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS history_fts_ad AFTER DELETE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, input, ddl, stage1_model, stage2_model, catalog_id)
            VALUES ('delete', old.rowid, old.input, old.ddl, old.stage1_model, old.stage2_model, old.catalog_id);
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS history_fts_au AFTER UPDATE OF input, ddl, stage1_model, stage2_model, catalog_id ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, input, ddl, stage1_model, stage2_model, catalog_id)
            VALUES ('delete', old.rowid, old.input, old.ddl, old.stage1_model, old.stage2_model, old.catalog_id);
            INSERT INTO history_fts(rowid, input, ddl, stage1_model, stage2_model, catalog_id)
            VALUES (new.rowid, new.input, new.ddl, new.stage1_model, new.stage2_model, new.catalog_id);
        END
        """,
    )
    try:
        for ddl in trigger_sql:
            conn.execute(text(ddl))
        conn.execute(text("INSERT INTO history_fts(history_fts) VALUES ('rebuild')"))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("SQLite FTS5 history search setup failed; falling back to LIKE search: %s", exc)
        return
    _HISTORY_FTS_ENABLED = True


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _hash_password(password: str) -> str:
    if not password:
        raise ValueError("password is required")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except Exception:  # noqa: BLE001
        return False
    actual = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


def _ensure_default_user_group() -> None:
    with SessionLocal() as session:
        exists = session.query(UserGroupRow).first()
        if exists:
            return
        session.add(UserGroupRow(id=str(uuid.uuid4()), name="default", at=_now_ms()))
        session.commit()


def _bootstrap_admin_password() -> str | None:
    password = os.getenv("INKU_BOOTSTRAP_ADMIN_PASSWORD")
    if password is not None:
        if len(password) < 8:
            raise ValueError("INKU_BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters")
        return password

    allow_insecure = os.getenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", "").lower() in {"1", "true", "yes"}
    if allow_insecure:
        return "inku-admin"
    return None


def _ensure_bootstrap_admin() -> None:
    with SessionLocal() as session:
        if session.query(UserAccountRow).first():
            return
        group = session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).first()
        password = _bootstrap_admin_password()
        if password is None:
            return
        session.add(
            UserAccountRow(
                id=str(uuid.uuid4()),
                username=os.getenv("INKU_BOOTSTRAP_ADMIN_USERNAME", "admin"),
                email=os.getenv("INKU_BOOTSTRAP_ADMIN_EMAIL", "admin@local"),
                password_hash=_hash_password(password),
                role="admin",
                group_id=group.id if group else None,
                at=_now_ms(),
            )
        )
        session.commit()


def _history_owner_user_id() -> str | None:
    with SessionLocal() as session:
        admin = session.query(UserAccountRow).filter(UserAccountRow.role == "admin").order_by(UserAccountRow.at.asc()).first()
        if admin:
            return admin.id
        user = session.query(UserAccountRow).order_by(UserAccountRow.at.asc()).first()
        return user.id if user else None


def admin_history_owner_id() -> str | None:
    return _history_owner_user_id()


def database_info() -> dict:
    url = engine.url
    db_path = _sqlite_db_path()
    file_size = db_path.stat().st_size if db_path and db_path.exists() else None
    return {
        "backend": url.get_backend_name(),
        "driver": url.get_driver_name(),
        "url": url.render_as_string(hide_password=True),
        "database": url.database,
        "is_default": _DB_URL == _DEFAULT_DB,
        "file_size_bytes": file_size,
        "file_path": str(db_path) if db_path else None,
    }


def _sqlite_db_path() -> Path | None:
    if engine.dialect.name != "sqlite":
        return None
    database = engine.url.database
    if not database or database == ":memory:":
        return None
    return Path(database).expanduser()


def _read_app_setting(key: str) -> dict | None:
    with SessionLocal() as session:
        row = session.get(AppSettingRow, key)
        if not row:
            return None
        try:
            value = json.loads(row.value or "{}")
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def _write_app_setting(key: str, value: dict) -> dict:
    with SessionLocal() as session:
        row = session.get(AppSettingRow, key)
        if row:
            row.value = json.dumps(value, ensure_ascii=False)
            row.at = _now_ms()
        else:
            row = AppSettingRow(key=key, value=json.dumps(value, ensure_ascii=False), at=_now_ms())
            session.add(row)
        session.commit()
        return value


def _normalize_db_backup_settings(settings: dict | None) -> dict:
    clean = dict(_DB_BACKUP_DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return clean
    if "interval_days" in settings:
        try:
            interval_days = int(settings["interval_days"])
        except (TypeError, ValueError) as exc:
            raise ValueError("backup interval days must be an integer") from exc
        if interval_days < 1 or interval_days > 365:
            raise ValueError("backup interval days must be between 1 and 365")
        clean["interval_days"] = interval_days
    if "max_generations" in settings:
        try:
            max_generations = int(settings["max_generations"])
        except (TypeError, ValueError) as exc:
            raise ValueError("backup max generations must be an integer") from exc
        if max_generations < 1 or max_generations > 100:
            raise ValueError("backup max generations must be between 1 and 100")
        clean["max_generations"] = max_generations
    if "last_auto_backup_at" in settings:
        try:
            clean["last_auto_backup_at"] = max(0, int(settings["last_auto_backup_at"]))
        except (TypeError, ValueError):
            clean["last_auto_backup_at"] = 0
    return clean


def get_db_backup_settings() -> dict:
    return _normalize_db_backup_settings(_read_app_setting(_DB_BACKUP_SETTINGS_KEY))


def update_db_backup_settings(interval_days: int, max_generations: int) -> dict:
    current = get_db_backup_settings()
    current["interval_days"] = interval_days
    current["max_generations"] = max_generations
    clean = _normalize_db_backup_settings(current)
    return _write_app_setting(_DB_BACKUP_SETTINGS_KEY, clean)


def _db_backup_file(kind: str, at_ms: int) -> Path:
    timestamp = datetime.fromtimestamp(at_ms / 1000).strftime("%Y%m%d-%H%M%S")
    return _DB_BACKUP_DIR / kind / f"inku-{kind}-{timestamp}.db"


def _copy_sqlite_database(destination: Path) -> None:
    source = _sqlite_db_path()
    if not source or not source.exists():
        raise ValueError("SQLite DB file is not available")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
    except sqlite3.Error:
        if destination.exists():
            destination.unlink(missing_ok=True)
        shutil.copy2(source, destination)


def _prune_auto_backups(max_generations: int) -> None:
    auto_dir = _DB_BACKUP_DIR / "auto"
    if not auto_dir.exists():
        return
    backups = sorted(auto_dir.glob("inku-auto-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in backups[max_generations:]:
        old.unlink(missing_ok=True)


def create_db_backup(*, manual: bool = False) -> dict:
    if engine.dialect.name != "sqlite":
        raise ValueError("DB backup replicas are supported only for SQLite file databases")
    at_ms = _now_ms()
    kind = "manual" if manual else "auto"
    path = _db_backup_file(kind, at_ms)
    _copy_sqlite_database(path)
    if manual:
        settings = get_db_backup_settings()
    else:
        settings = get_db_backup_settings()
        settings["last_auto_backup_at"] = at_ms
        _write_app_setting(_DB_BACKUP_SETTINGS_KEY, settings)
        _prune_auto_backups(settings["max_generations"])
    return {
        "path": str(path),
        "at": at_ms,
        "manual": manual,
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def ensure_scheduled_db_backup() -> dict | None:
    settings = get_db_backup_settings()
    last_at = int(settings.get("last_auto_backup_at") or 0)
    interval_ms = int(settings["interval_days"]) * 24 * 60 * 60 * 1000
    if last_at > 0 and _now_ms() - last_at < interval_ms:
        return None
    try:
        return create_db_backup(manual=False)
    except ValueError:
        return None


def db_backup_status() -> dict:
    settings = get_db_backup_settings()
    supported = engine.dialect.name == "sqlite" and _sqlite_db_path() is not None
    auto_dir = _DB_BACKUP_DIR / "auto"
    manual_dir = _DB_BACKUP_DIR / "manual"
    auto_count = len(list(auto_dir.glob("inku-auto-*.db"))) if auto_dir.exists() else 0
    manual_count = len(list(manual_dir.glob("inku-manual-*.db"))) if manual_dir.exists() else 0
    return {
        **settings,
        "supported": supported,
        "backup_dir": str(_DB_BACKUP_DIR),
        "auto_count": auto_count,
        "manual_count": manual_count,
    }


def _assign_unowned_history_to_admin() -> None:
    owner_id = _history_owner_user_id()
    if not owner_id:
        return
    with SessionLocal() as session:
        session.query(HistoryRow).filter(HistoryRow.user_id.is_(None)).update(
            {HistoryRow.user_id: owner_id},
            synchronize_session=False,
        )
        session.commit()


def _row_to_dict(row: HistoryRow) -> dict:
    item = {
        "id":           row.id,
        "user_id":      row.user_id,
        "at":           row.at,
        "input":        row.input,
        "ddl":          row.ddl,
        "score":        json.loads(row.score) if row.score else {},
        "svg":          row.svg,
        "output_path":  row.output_path,
        "elapsed_ms":   row.elapsed_ms,
        "stage1_model": row.stage1_model,
        "stage2_model": row.stage2_model,
        "tokens_in":    row.tokens_in,
        "tokens_out":   row.tokens_out,
        "catalog_id":   row.catalog_id,
        "trashed":      bool(row.trashed),
        "starred":      bool(row.starred),
    }
    if row.render_build_number is not None:
        item["render_build_number"] = row.render_build_number
    if row.render_color_catalog_id is not None:
        item["render_color_catalog_id"] = row.render_color_catalog_id
    if row.render_color_catalog_name is not None:
        item["render_color_catalog_name"] = row.render_color_catalog_name
    if row.render_color_catalog_sub is not None:
        item["render_color_catalog_sub"] = row.render_color_catalog_sub
    if row.render_color_catalog is not None:
        try:
            legacy_catalog = json.loads(row.render_color_catalog)
        except json.JSONDecodeError:
            legacy_catalog = None
        if isinstance(legacy_catalog, dict):
            item.setdefault("render_color_catalog_id", legacy_catalog.get("id"))
            item.setdefault("render_color_catalog_name", legacy_catalog.get("name"))
            item.setdefault("render_color_catalog_sub", legacy_catalog.get("sub"))
    if row.render_color_map is not None:
        try:
            item["render_color_map"] = json.loads(row.render_color_map)
        except json.JSONDecodeError:
            item["render_color_map"] = None
    return item


def _group_to_dict(row: UserGroupRow) -> dict:
    return {"id": row.id, "name": row.name, "at": row.at}


def _user_to_dict(row: UserAccountRow, group_name: str | None = None) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "role": row.role,
        "role_label": ROLE_LABELS.get(row.role, row.role),
        "group_id": row.group_id,
        "group_name": group_name,
        "ui_theme": row.ui_theme if row.ui_theme in {"light", "dark"} else "light",
        "settings_tab": row.settings_tab if row.settings_tab in _SETTINGS_TABS else "db",
        "image_generation_count": row.image_generation_count or 0,
        "at": row.at,
    }


def add_item(item: dict) -> dict:
    row = HistoryRow(
        id=item["id"],
        user_id=item["user_id"],
        at=item["at"],
        input=item.get("input", ""),
        ddl=item.get("ddl"),
        score=json.dumps(item.get("score", {})),
        svg=item.get("svg", ""),
        output_path=item.get("output_path"),
        elapsed_ms=item.get("elapsed_ms", 0),
        stage1_model=item.get("stage1_model"),
        stage2_model=item.get("stage2_model"),
        tokens_in=item.get("tokens_in"),
        tokens_out=item.get("tokens_out"),
        catalog_id=item.get("catalog_id"),
        render_build_number=item.get("render_build_number"),
        render_color_catalog_id=item.get("render_color_catalog_id"),
        render_color_catalog_name=item.get("render_color_catalog_name"),
        render_color_catalog_sub=item.get("render_color_catalog_sub"),
        render_color_map=json.dumps(item.get("render_color_map"), ensure_ascii=False) if item.get("render_color_map") is not None else None,
        trashed=0,
        starred=0,
    )
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def list_user_groups() -> list[dict]:
    with SessionLocal() as session:
        rows = session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).all()
        return [_group_to_dict(row) for row in rows]


def add_user_group(name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("group name is required")
    row = UserGroupRow(id=str(uuid.uuid4()), name=name, at=_now_ms())
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _group_to_dict(row)


def update_user_group(group_id: str, name: str) -> dict | None:
    name = name.strip()
    if not name:
        raise ValueError("group name is required")
    with SessionLocal() as session:
        row = session.get(UserGroupRow, group_id)
        if not row:
            return None
        row.name = name
        row.at = _now_ms()
        session.commit()
        session.refresh(row)
        return _group_to_dict(row)


def delete_user_group(group_id: str) -> bool:
    with SessionLocal() as session:
        if session.query(UserAccountRow).filter(UserAccountRow.group_id == group_id).first():
            raise ValueError("group has users")
        row = session.get(UserGroupRow, group_id)
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True


def list_users() -> list[dict]:
    with SessionLocal() as session:
        rows = (
            session.query(UserAccountRow, UserGroupRow.name)
            .outerjoin(UserGroupRow, UserAccountRow.group_id == UserGroupRow.id)
            .order_by(UserAccountRow.username.asc())
            .all()
        )
        return [_user_to_dict(row, group_name) for row, group_name in rows]


def get_user(user_id: str) -> dict | None:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def authenticate_user(username: str, password: str) -> dict | None:
    with SessionLocal() as session:
        row = session.query(UserAccountRow).filter(UserAccountRow.username == username.strip()).first()
        if not row or not verify_password(password, row.password_hash):
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as session:
        if not session.get(UserAccountRow, user_id):
            raise ValueError("user not found")
        _delete_expired_sessions(session)
        session.add(UserSessionRow(token_hash=_hash_token(token), user_id=user_id, at=_now_ms()))
        session.commit()
    return token


def _session_expiry_cutoff_ms(now_ms: int | None = None) -> int | None:
    if _SESSION_MAX_AGE_SECONDS <= 0:
        return None
    now = _now_ms() if now_ms is None else now_ms
    return now - (_SESSION_MAX_AGE_SECONDS * 1000)


def _delete_expired_sessions(session) -> int:
    cutoff = _session_expiry_cutoff_ms()
    if cutoff is None:
        return 0
    return (
        session.query(UserSessionRow)
        .filter(UserSessionRow.at < cutoff)
        .delete(synchronize_session=False)
    )


def get_session_user(token: str) -> dict | None:
    with SessionLocal() as session:
        session_row = session.get(UserSessionRow, _hash_token(token))
        if not session_row:
            return None
        cutoff = _session_expiry_cutoff_ms()
        if cutoff is not None and session_row.at < cutoff:
            session.delete(session_row)
            session.commit()
            return None
        row = session.get(UserAccountRow, session_row.user_id)
        if not row:
            session.delete(session_row)
            session.commit()
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def delete_session(token: str) -> bool:
    with SessionLocal() as session:
        row = session.get(UserSessionRow, _hash_token(token))
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True


def list_users_for_actor(actor: dict) -> list[dict]:
    if actor["role"] == "admin":
        return list_users()
    if actor["role"] == "group_lead" and actor.get("group_id"):
        with SessionLocal() as session:
            rows = (
                session.query(UserAccountRow, UserGroupRow.name)
                .outerjoin(UserGroupRow, UserAccountRow.group_id == UserGroupRow.id)
                .filter(UserAccountRow.group_id == actor["group_id"])
                .order_by(UserAccountRow.username.asc())
                .all()
            )
            return [_user_to_dict(row, group_name) for row, group_name in rows]
    return []


def add_user(username: str, email: str, password: str, role: str, group_id: str | None) -> dict:
    username = username.strip()
    email = email.strip()
    if not username:
        raise ValueError("username is required")
    if not email:
        raise ValueError("email is required")
    if role not in USER_ROLES:
        raise ValueError("invalid role")
    row = UserAccountRow(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        password_hash=_hash_password(password),
        role=role,
        group_id=group_id,
        at=_now_ms(),
    )
    with SessionLocal() as session:
        if group_id and not session.get(UserGroupRow, group_id):
            raise ValueError("group not found")
        session.add(row)
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def update_user(
    user_id: str,
    *,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
    role: str | None = None,
    group_id: str | None | object = _UNSET,
) -> dict | None:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        if username is not None:
            username = username.strip()
            if not username:
                raise ValueError("username is required")
            row.username = username
        if email is not None:
            email = email.strip()
            if not email:
                raise ValueError("email is required")
            row.email = email
        if password is not None and password:
            row.password_hash = _hash_password(password)
        if role is not None:
            if role not in USER_ROLES:
                raise ValueError("invalid role")
            row.role = role
        if group_id is not _UNSET:
            group_id = group_id if isinstance(group_id, str) else None
            if group_id and not session.get(UserGroupRow, group_id):
                raise ValueError("group not found")
            row.group_id = group_id or None
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def update_current_user_profile(
    user_id: str,
    *,
    email: str | None = None,
    password: str | None = None,
    current_password: str | None = None,
) -> dict | None:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        if email is not None:
            email = email.strip()
            if not email:
                raise ValueError("email is required")
            row.email = email
        if password is not None and password:
            if not current_password or not verify_password(current_password, row.password_hash):
                raise ValueError("current password is invalid")
            row.password_hash = _hash_password(password)
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def increment_user_generation_count(user_id: str, amount: int = 1) -> int | None:
    if amount <= 0:
        raise ValueError("amount must be positive")
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        row.image_generation_count = (row.image_generation_count or 0) + amount
        session.commit()
        session.refresh(row)
        return row.image_generation_count or 0


def update_user_theme(user_id: str, ui_theme: str) -> dict | None:
    if ui_theme not in {"light", "dark"}:
        raise ValueError("invalid ui theme")
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        row.ui_theme = ui_theme
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def update_user_settings(user_id: str, ui_theme: str | None = None, settings_tab: str | None = None) -> dict | None:
    if ui_theme is not None and ui_theme not in {"light", "dark"}:
        raise ValueError("invalid ui theme")
    if settings_tab is not None and settings_tab not in _SETTINGS_TABS:
        raise ValueError("invalid settings tab")
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        if ui_theme is not None:
            row.ui_theme = ui_theme
        if settings_tab is not None:
            row.settings_tab = settings_tab
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def _normalize_batch_prompt_history(items: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise ValueError("batch prompt history must contain strings")
        prompt = item.strip().replace("\r\n", "\n").replace("\r", "\n")
        if not prompt or prompt in seen:
            continue
        if len(prompt) > _BATCH_PROMPT_HISTORY_MAX_TEXT:
            raise ValueError("batch prompt history item is too long")
        normalized.append(prompt)
        seen.add(prompt)
        if len(normalized) >= _BATCH_PROMPT_HISTORY_LIMIT:
            break
    return normalized


def get_user_batch_prompt_history(user_id: str) -> list[str]:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return []
        try:
            parsed = json.loads(row.batch_prompt_history or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        try:
            return _normalize_batch_prompt_history(parsed)
        except ValueError:
            return []


def update_user_batch_prompt_history(user_id: str, items: list[str]) -> list[str] | None:
    prompts = _normalize_batch_prompt_history(items)
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        row.batch_prompt_history = json.dumps(prompts, ensure_ascii=False)
        session.commit()
        return prompts


def _normalize_demo_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("demo settings must be an object")
    clean = dict(_DEMO_DEFAULT_SETTINGS)
    if "save_db" in settings:
        clean["save_db"] = bool(settings["save_db"])
    if "save_files" in settings:
        clean["save_files"] = bool(settings["save_files"])
    if "random_color_catalog" in settings:
        clean["random_color_catalog"] = bool(settings["random_color_catalog"])
    if "prompt_model" in settings:
        model = settings["prompt_model"]
        if not isinstance(model, str) or not model.strip():
            raise ValueError("demo prompt model is required")
        clean["prompt_model"] = model.strip()
    if "seed_phrase" in settings:
        phrase = settings["seed_phrase"]
        if not isinstance(phrase, str):
            raise ValueError("demo seed phrase must be a string")
        phrase = phrase.strip()
        if not phrase:
            raise ValueError("demo seed phrase is required")
        if len(phrase) > 1000:
            raise ValueError("demo seed phrase is too long")
        clean["seed_phrase"] = phrase
    if "interval_seconds" in settings:
        try:
            interval = int(settings["interval_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError("demo interval must be an integer") from exc
        if interval < 1 or interval > 3600:
            raise ValueError("demo interval must be between 1 and 3600 seconds")
        clean["interval_seconds"] = interval
    return clean


def get_user_demo_settings(user_id: str) -> dict:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return dict(_DEMO_DEFAULT_SETTINGS)
        try:
            parsed = json.loads(row.demo_settings or "{}")
        except json.JSONDecodeError:
            return dict(_DEMO_DEFAULT_SETTINGS)
        if not isinstance(parsed, dict):
            return dict(_DEMO_DEFAULT_SETTINGS)
        try:
            return _normalize_demo_settings(parsed)
        except ValueError:
            return dict(_DEMO_DEFAULT_SETTINGS)


def update_user_demo_settings(user_id: str, settings: dict) -> dict | None:
    clean = _normalize_demo_settings(settings)
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        row.demo_settings = json.dumps(clean, ensure_ascii=False)
        session.commit()
        return clean


def _normalize_export_templates(items: list[dict]) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("export templates must be a list")
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("export template must be an object")
        template_id = item.get("id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError("export template id is required")
        template_id = template_id.strip()[:80]
        if template_id in seen:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("export template name is required")
        description = item.get("description", "")
        if not isinstance(description, str):
            raise ValueError("export template description must be a string")
        try:
            y_px = int(item.get("y_px"))
        except (TypeError, ValueError) as exc:
            raise ValueError("export template y_px must be an integer") from exc
        if y_px < 64 or y_px > 12000:
            raise ValueError("export template y_px must be between 64 and 12000")
        normalized.append(
            {
                "id": template_id,
                "name": name.strip()[:80],
                "description": description.strip()[:240],
                "y_px": y_px,
            }
        )
        seen.add(template_id)
        if len(normalized) >= _EXPORT_TEMPLATE_LIMIT:
            break
    return normalized or [dict(item) for item in _EXPORT_TEMPLATE_DEFAULTS]


def get_user_export_templates(user_id: str) -> list[dict]:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return [dict(item) for item in _EXPORT_TEMPLATE_DEFAULTS]
        try:
            parsed = json.loads(row.export_templates or "[]")
        except json.JSONDecodeError:
            return [dict(item) for item in _EXPORT_TEMPLATE_DEFAULTS]
        if not isinstance(parsed, list) or not parsed:
            return [dict(item) for item in _EXPORT_TEMPLATE_DEFAULTS]
        try:
            return _normalize_export_templates(parsed)
        except ValueError:
            return [dict(item) for item in _EXPORT_TEMPLATE_DEFAULTS]


def update_user_export_templates(user_id: str, items: list[dict]) -> list[dict] | None:
    clean = _normalize_export_templates(items)
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        row.export_templates = json.dumps(clean, ensure_ascii=False)
        session.commit()
        return clean


def _normalize_plugin_storage(storage: dict) -> dict:
    if not isinstance(storage, dict):
        raise ValueError("plugin storage must be an object")
    normalized: dict[str, dict] = {}
    for plugin_id, value in storage.items():
        if not isinstance(plugin_id, str) or not plugin_id:
            raise ValueError("plugin id must be a non-empty string")
        if len(plugin_id) > 80 or not all(ch.isalnum() or ch in "-_." for ch in plugin_id):
            raise ValueError("plugin id contains unsupported characters")
        if not isinstance(value, dict):
            raise ValueError("plugin storage values must be objects")
        normalized[plugin_id] = value
    raw = json.dumps(normalized, ensure_ascii=False)
    if len(raw.encode("utf-8")) > _PLUGIN_STORAGE_MAX_BYTES:
        raise ValueError("plugin storage is too large")
    return normalized


def get_user_plugin_storage(user_id: str) -> dict:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return {}
        try:
            parsed = json.loads(row.plugin_storage or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        try:
            return _normalize_plugin_storage(parsed)
        except ValueError:
            return {}


def update_user_plugin_storage(user_id: str, storage: dict) -> dict | None:
    clean = _normalize_plugin_storage(storage)
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        row.plugin_storage = json.dumps(clean, ensure_ascii=False)
        session.commit()
        return clean


def update_user_plugin_value(user_id: str, plugin_id: str, value: dict) -> dict | None:
    current = get_user_plugin_storage(user_id)
    current[plugin_id] = value
    return update_user_plugin_storage(user_id, current)


def delete_user(user_id: str) -> bool:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return False
        if session.query(HistoryRow).filter(HistoryRow.user_id == user_id).first():
            raise ValueError("user has history")
        session.delete(row)
        session.commit()
        return True


def _fts_match_query(search: str) -> str:
    return '"' + search.replace('"', '""') + '"'


def _use_history_fts(search: str) -> bool:
    return _HISTORY_FTS_ENABLED and engine.dialect.name == "sqlite" and len(search) >= 3


def _list_items_with_fts(
    session,
    user_id: str,
    offset: int,
    limit: int,
    trashed: bool,
    search: str,
    starred: bool,
) -> tuple[list[dict], int]:
    params = {
        "user_id": user_id,
        "trashed": 1 if trashed else 0,
        "match": _fts_match_query(search),
        "limit": limit,
        "offset": offset,
    }
    starred_clause = "AND h.starred = 1" if starred else ""
    total = session.execute(
        text(
            f"""
            SELECT count(h.id)
            FROM history h
            JOIN history_fts ON history_fts.rowid = h.rowid
            WHERE h.user_id = :user_id
              AND h.trashed = :trashed
              {starred_clause}
              AND history_fts MATCH :match
            """
        ),
        params,
    ).scalar() or 0
    ids = [
        row[0]
        for row in session.execute(
            text(
                f"""
                SELECT h.id
                FROM history h
                JOIN history_fts ON history_fts.rowid = h.rowid
                WHERE h.user_id = :user_id
                  AND h.trashed = :trashed
                  {starred_clause}
                  AND history_fts MATCH :match
                ORDER BY h.at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ]
    if not ids:
        return [], int(total)
    order = {item_id: index for index, item_id in enumerate(ids)}
    rows = session.query(HistoryRow).filter(HistoryRow.id.in_(ids)).all()
    return sorted((_row_to_dict(row) for row in rows), key=lambda item: order[item["id"]]), int(total)


def list_items(
    user_id: str,
    offset: int = 0,
    limit: int = 10,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as session:
        query = session.query(HistoryRow).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.trashed == (1 if trashed else 0),
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        search = query_text.strip()
        if search and _use_history_fts(search):
            return _list_items_with_fts(session, user_id, offset, limit, trashed, search, starred)
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(
                HistoryRow.input.ilike(pattern),
                HistoryRow.ddl.ilike(pattern),
                HistoryRow.stage1_model.ilike(pattern),
                HistoryRow.stage2_model.ilike(pattern),
                HistoryRow.catalog_id.ilike(pattern),
            ))
        total: int = query.with_entities(func.count(HistoryRow.id)).scalar() or 0
        rows = (
            query
            .order_by(HistoryRow.at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows], total


def set_item_starred(user_id: str, item_id: str, starred: bool) -> dict | None:
    with SessionLocal() as session:
        row = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id == item_id)
            .first()
        )
        if not row:
            return None
        row.starred = 1 if starred else 0
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def get_items(user_id: str, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    order = {item_id: index for index, item_id in enumerate(ids)}
    with SessionLocal() as session:
        rows = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id.in_(ids))
            .all()
        )
        return sorted((_row_to_dict(row) for row in rows), key=lambda item: order.get(item["id"], len(order)))


def delete_all(user_id: str) -> None:
    with SessionLocal() as session:
        session.query(HistoryRow).filter(HistoryRow.user_id == user_id).delete()
        session.commit()


def trash_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        count = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id.in_(ids), HistoryRow.trashed == 0)
            .update({HistoryRow.trashed: 1}, synchronize_session=False)
        )
        session.commit()
        return count


def restore_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        count = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id.in_(ids), HistoryRow.trashed == 1)
            .update({HistoryRow.trashed: 0}, synchronize_session=False)
        )
        session.commit()
        return count


def delete_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        count = session.query(HistoryRow).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.id.in_(ids),
        ).delete(synchronize_session=False)
        session.commit()
        return count
