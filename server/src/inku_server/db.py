"""Canonical SQLite models, queries, and compatibility façade."""
from __future__ import annotations

import json
import logging
import os
import secrets
import uuid
from contextlib import contextmanager, nullcontext
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path

from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session, sessionmaker

from .color_catalogs import RENAMED_COLOR_CATALOG_IDS
from .identity import description_hash
from .limits import normalize_limits
from .plugins import canvas_aspect_ratio_for_aspect, normalize_canvas_aspect_id
from .persistence import accounts as _accounts
from .persistence.backup import (
    DB_BACKUP_DEFAULT_SETTINGS as _DB_BACKUP_DEFAULT_SETTINGS,  # noqa: F401
    DB_BACKUP_LIST_LIMIT as _DB_BACKUP_LIST_LIMIT,
    DB_BACKUP_SETTINGS_KEY as _DB_BACKUP_SETTINGS_KEY,  # noqa: F401
    BackupService as _BackupService,
)
from .persistence import feedback as _feedback
from .persistence import groups as _groups
from .persistence import history as _history
from .persistence import identities as _identities
from .persistence import lineage as _lineage
from .persistence import access as _access
from .persistence import okugaki as _okugaki
from .persistence import sessions as _sessions
from .persistence import settings as _settings
from .persistence.config import CANONICAL_DB_ENV, PERSISTENCE_CONFIG, sqlite_database_path
from .persistence.engine import CANONICAL_SQLITE_PRAGMAS, create_sqlite_engine
from .persistence.legacy_schema import (
    HISTORY_COLUMN_MIGRATIONS as _HISTORY_COLUMN_MIGRATIONS,
    HISTORY_INDEX_MIGRATIONS as _HISTORY_INDEX_MIGRATIONS,
    LINEAGE_KIND_RENAMES as _LINEAGE_KIND_RENAMES,
    LINEAGE_NODE_COLUMN_MIGRATIONS as _LINEAGE_NODE_COLUMN_MIGRATIONS,
    LINEAGE_NODE_INDEX_MIGRATIONS as _LINEAGE_NODE_INDEX_MIGRATIONS,
    USER_ACCOUNT_COLUMN_MIGRATIONS as _USER_ACCOUNT_COLUMN_MIGRATIONS,
)
from .persistence.schema import (
    Base,
    CoerceTraceCatalogRow,
    HistoryAclRow,
    HistoryRow,
    LineageEdgeRow,
    LineageNodeRow,
    OkugakiRow,
    PermissionGroupRow,
    UnreadWordRow,  # noqa: F401 - compatibility re-export for direct integrity readers
    UserAccountRow,
    UserGroupRow,
    UserPermissionGroupRow,
    UserSessionRow,  # noqa: F401 - compatibility re-export for direct session readers
)
from .persistence.migrations import MigrationExecutionError, ensure_current_schema, install_history_fts
from .persistence import search as _history_search
from .persistence.search import HistorySearchService as _HistorySearchService
from .persistence.settings import AppSettingsStore

_SESSION_MAX_AGE_SECONDS = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))

engine = create_sqlite_engine(
    PERSISTENCE_CONFIG.canonical_url,
    setting=CANONICAL_DB_ENV,
    pragmas=CANONICAL_SQLITE_PRAGMAS,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
_logger = logging.getLogger(__name__)
_HISTORY_FTS_ENABLED = False
LINEAGE_DERIVATION_KINDS = _history.LINEAGE_DERIVATION_KINDS

# What a member may do.  Fixed on purpose: a user-extensible set would make the
# authorization branches resolve at runtime, and nothing could be asserted about
# them.  Per-object sharing is a different mechanism and does not live here.
PERMISSION_GROUPS = ("admins", "leaders", "users")
PERMISSION_GROUP_LABELS = {
    "admins": "管理者",
    "leaders": "リーダー",
    "users": "ユーザー",
}

# The legacy `user_accounts.role` column is kept as a derived mirror so a database
# taken after this change still starts on a build from before it.  Nothing reads
# it to decide anything; it is written from the permission groups and never the
# other way round.
_ROLE_MIRROR_BY_GROUP = {"admins": "admin", "leaders": "group_lead"}
# Groups that put a member above the ones a leader may administer.
_ELEVATED_PERMISSION_GROUPS = ("admins", "leaders")
_LEGACY_ROLE_TO_PERMISSION_GROUP = {
    "admin": "admins",
    "group_lead": "leaders",
    "user": "users",
}
_UNSET = object()
_BATCH_PROMPT_HISTORY_LIMIT = _settings.BATCH_PROMPT_HISTORY_LIMIT
_BATCH_PROMPT_HISTORY_MAX_TEXT = _settings.BATCH_PROMPT_HISTORY_MAX_TEXT
_SETTINGS_TABS = _settings.SETTINGS_TABS
_UI_MODES = _settings.UI_MODES
_UI_CUSTOM_KEYS = _settings.UI_CUSTOM_KEYS
_HISTORY_STRIP_FIELDS = _settings.HISTORY_STRIP_FIELDS
_HISTORY_STRIP_FIELD_LIMIT = _settings.HISTORY_STRIP_FIELD_LIMIT
_HISTORY_STRIP_FIELDS_DEFAULT = _settings.HISTORY_STRIP_FIELDS_DEFAULT


def _loads_or_none(raw: str | None):
    """The stored JSON, or None when there is nothing readable stored.

    None and a stored empty list have to stay apart: the first is an account
    that never answered and takes the default, the second is an account that
    asked for nothing.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def normalize_history_strip_fields(value) -> list[str]:
    return _settings.normalize_history_strip_fields(value)
_PLUGIN_STORAGE_MAX_BYTES = _settings.PLUGIN_STORAGE_MAX_BYTES
_OUTPUT_SAVE_SETTINGS_KEY = _settings.OUTPUT_SAVE_SETTINGS_KEY
_OUTPUT_SAVE_DEFAULT_SETTINGS = _settings.OUTPUT_SAVE_DEFAULT_SETTINGS
_THUMBNAIL_SETTINGS_KEY = _settings.THUMBNAIL_SETTINGS_KEY
_THUMBNAIL_DEFAULT_SETTINGS = _settings.THUMBNAIL_DEFAULT_SETTINGS
THUMBNAIL_WORKERS_MIN = _settings.THUMBNAIL_WORKERS_MIN
THUMBNAIL_WORKERS_MAX = _settings.THUMBNAIL_WORKERS_MAX
_RENDER_CONCURRENCY_SETTINGS_KEY = _settings.RENDER_CONCURRENCY_SETTINGS_KEY
_RENDER_CONCURRENCY_DEFAULT_SETTINGS = _settings.RENDER_CONCURRENCY_DEFAULT_SETTINGS
RENDER_CONCURRENCY_MIN = _settings.RENDER_CONCURRENCY_MIN
RENDER_CONCURRENCY_MAX = _settings.RENDER_CONCURRENCY_MAX
_RENDER_LIMIT_SETTINGS_KEY = _settings.RENDER_LIMIT_SETTINGS_KEY
_LOG_RETENTION_SETTINGS_KEY = _settings.LOG_RETENTION_SETTINGS_KEY
_LOG_RETENTION_DEFAULT_SETTINGS = _settings.LOG_RETENTION_DEFAULT_SETTINGS
_DEMO_DEFAULT_SETTINGS = _settings.DEMO_DEFAULT_SETTINGS
_EXPORT_TEMPLATE_LIMIT = _settings.EXPORT_TEMPLATE_LIMIT
_EXPORT_TEMPLATE_DEFAULTS = _settings.EXPORT_TEMPLATE_DEFAULTS
_DEFAULT_DB_BACKUP_DIR = Path.home() / ".local" / "share" / "inku" / "db-backups"
_DB_BACKUP_DIR = Path(os.getenv("INKU_DB_BACKUP_DIR", str(_DEFAULT_DB_BACKUP_DIR))).expanduser()
_MODEL_SETTINGS_KEY = _settings.MODEL_SETTINGS_KEY
def init_db() -> None:
    global _HISTORY_FTS_ENABLED

    db_path = sqlite_database_path(
        PERSISTENCE_CONFIG.canonical_url,
        setting=CANONICAL_DB_ENV,
    )
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        outcome = ensure_current_schema(
            engine=engine,
            database_path=db_path,
            create_schema=lambda connection: Base.metadata.create_all(bind=connection),
            seed_fresh=_seed_fresh_database,
            apply_legacy=_apply_legacy_baseline,
        )
    except MigrationExecutionError as exc:
        _logger.error("verified migration safety snapshot retained at %s", exc.snapshot.path)
        raise
    _HISTORY_FTS_ENABLED = outcome.fts_enabled


def _migration_session(connection) -> Session:
    return Session(bind=connection, autocommit=False, autoflush=False)


@contextmanager
def _session_scope(session: Session | None):
    """Reuse the migration session or own a normal short-lived session."""
    if session is not None:
        yield session, False
        return
    with SessionLocal() as owned_session:
        yield owned_session, True


def _finish_session(session: Session, owns_session: bool) -> None:
    if owns_session:
        session.commit()
    else:
        session.flush()


def _seed_fresh_database(connection) -> None:
    """Seed only rows required by a new, already-current database."""
    with _migration_session(connection) as session:
        _ensure_default_user_group(session)
        _ensure_permission_groups(session)
        _ensure_bootstrap_admin(session)
        session.flush()


def _apply_legacy_baseline(connection) -> None:
    """Run the reviewed legacy transforms inside the coordinator transaction."""
    _migrate_columns(connection, include_fts=False)
    with _migration_session(connection) as session:
        _ensure_default_user_group(session)
        _ensure_permission_groups(session)
        _ensure_bootstrap_admin(session)
        # The bootstrap account must exist before the legacy role mirror is
        # converted and before orphaned works resolve their canonical owner.
        _migrate_roles_to_permission_groups(session)
        _assign_unowned_history_to_admin(session)
        _backfill_history_identity_and_lineage(session)
        session.flush()


def _migrate_columns(connection=None, *, include_fts: bool = True) -> None:
    manager = engine.begin() if connection is None else nullcontext(connection)
    with manager as conn:
        try:
            CoerceTraceCatalogRow.__table__.create(bind=conn, checkfirst=True)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("failed to create coerce trace catalog table") from exc
        try:
            inspector = inspect(conn)
            existing_history_columns = {col["name"] for col in inspector.get_columns("history")}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("failed to inspect history table columns for migration") from exc

        # v2.8.0: `vary_seed` is the Stage 1.5 composition seed, not the
        # variation seed. Rename the column before additions so persisted values
        # move with it instead of becoming orphaned.
        if (
            "vary_seed" in existing_history_columns
            and "composition_seed" not in existing_history_columns
        ):
            try:
                conn.execute(text("ALTER TABLE history RENAME COLUMN vary_seed TO composition_seed"))
                existing_history_columns.discard("vary_seed")
                existing_history_columns.add("composition_seed")
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("failed to rename history.vary_seed to composition_seed") from exc

        adding_expanded_ddl = "expanded_ddl" not in existing_history_columns
        for column, ddl in _HISTORY_COLUMN_MIGRATIONS.items():
            if column in existing_history_columns:
                continue
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to migrate history.{column}") from exc

        if adding_expanded_ddl:
            # v1.98 redefined history.ddl as input-side DDL. Existing text is the
            # expanded DDL that reached Stage 2, so move it and leave input-side
            # DDL NULL because the original Stage 1 output was never persisted.
            # A few direct-DDL works move their source text as expanded DDL; the
            # author explicitly accepted that historical approximation on
            # 2026-07-20.
            try:
                conn.execute(text("UPDATE history SET expanded_ddl = ddl, ddl = NULL WHERE ddl IS NOT NULL"))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("failed to move legacy history.ddl into expanded_ddl") from exc

        try:
            existing_user_columns = {col["name"] for col in inspector.get_columns("user_accounts")}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("failed to inspect user_accounts table columns for migration") from exc

        has_lineage_nodes = inspector.has_table("lineage_nodes")
        existing_lineage_node_columns = (
            {col["name"] for col in inspector.get_columns("lineage_nodes")}
            if has_lineage_nodes else set()
        )
        if has_lineage_nodes:
            for column, ddl in _LINEAGE_NODE_COLUMN_MIGRATIONS.items():
                if column in existing_lineage_node_columns:
                    continue
                try:
                    conn.execute(text(ddl))
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"failed to migrate lineage_nodes.{column}") from exc

        for column, ddl in _USER_ACCOUNT_COLUMN_MIGRATIONS.items():
            if column in existing_user_columns:
                continue
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to migrate user_accounts.{column}") from exc

        # v2.8.0 moves persisted derivation kinds to the canonical vocabulary.
        # `variation` belongs only to the actual variation operation: four other
        # operations lose that suffix and `hensou` becomes `variation`. Rows are
        # rewritten in place and never removed.
        if inspector.has_table("lineage_edges"):
            for before, after in _LINEAGE_KIND_RENAMES:
                try:
                    conn.execute(
                        text("UPDATE lineage_edges SET derivation_kind = :after WHERE derivation_kind = :before"),
                        {"before": before, "after": after},
                    )
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"failed to rename derivation kind {before}") from exc

        for index_name, ddl in _HISTORY_INDEX_MIGRATIONS:
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to create migration index {index_name}") from exc
        if has_lineage_nodes:
            for index_name, ddl in _LINEAGE_NODE_INDEX_MIGRATIONS:
                try:
                    conn.execute(text(ddl))
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"failed to create migration index {index_name}") from exc
        _backfill_render_hashes(conn)
        _migrate_renamed_catalog_nameplates(conn)
        if include_fts:
            _migrate_history_search(conn)


def _migrate_renamed_catalog_nameplates(conn) -> None:
    """Point the display column at the id a renamed catalog answers to today.

    Only `catalog_id` moves. `render_color_catalog_id` is the id the work was
    DRAWN with, and the renderer hashes it into the seed that assigns each
    chromatic work color, so rewriting it would repaint the work out of its own
    unchanged snapshot -- the very silence this whole change exists to end
    (author's ruling 2026-08-09). `render_color_map` is never touched by
    anything here.

    Idempotent: after the first pass no row matches an old id any more.
    """
    for old_id, new_id in RENAMED_COLOR_CATALOG_IDS.items():
        try:
            conn.execute(
                text("UPDATE history SET catalog_id = :new_id WHERE catalog_id = :old_id"),
                {"new_id": new_id, "old_id": old_id},
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"failed to migrate renamed color catalog nameplate: {old_id} -> {new_id}"
            ) from exc


def _migrate_history_search(conn) -> None:
    global _HISTORY_FTS_ENABLED

    required_columns = {"input", "ddl", "stage1_model", "stage2_model", "catalog_id"}
    history_columns = {column["name"] for column in inspect(conn).get_columns("history")}
    if not required_columns <= history_columns:
        # Focused transform fixtures can predate columns that the historical
        # init_db baseline always had. They exercise the column transform only;
        # creating an unusable external-content FTS table would leave a partial
        # installation for the next startup to reject.
        _HISTORY_FTS_ENABLED = False
        return
    _HISTORY_FTS_ENABLED = install_history_fts(conn, rebuild=True)


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canvas_aspect_metadata(item: dict) -> tuple[str | None, float | None]:
    canvas_aspect_id = item.get("render_canvas_aspect_id") or item.get("render_canvas_aspect")
    if canvas_aspect_id is None:
        return None, None
    normalized = normalize_canvas_aspect_id(canvas_aspect_id)
    ratio = item.get("render_canvas_aspect_ratio")
    return normalized, ratio if ratio is not None else canvas_aspect_ratio_for_aspect(normalized)


def _canonical_seed(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _legacy_render_hash_for_item(item: dict) -> str:
    payload = {
        "version": "rh2",
        "score": item.get("score") or {},
        "render_seed": _canonical_seed(item.get("render_seed")),
        # Freeze the key as `vary_seed`: it is hash material, not a field label.
        # Renaming it would change every persisted rh2. The value still comes
        # from the renamed column; a v2.8.0 check caught this exact drift.
        "vary_seed": _canonical_seed(item.get("composition_seed")),
        "render_build_number": item.get("render_build_number"),
        "render_engine_id": item.get("render_engine_id"),
        "render_engine_version": item.get("render_engine_version"),
        "render_color_catalog_id": item.get("render_color_catalog_id") or item.get("catalog_id"),
    }
    return "rh2:" + sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def render_hash_for_item(item: dict) -> str:
    payload = {
        "version": "rh3",
        "score": item.get("score") or {},
        "render_seed": _canonical_seed(item.get("render_seed")),
        "render_wild": bool(item.get("render_wild")),
        "render_engine_id": item.get("render_engine_id"),
        "render_engine_version": item.get("render_engine_version"),
        "render_color_catalog_id": item.get("render_color_catalog_id") or item.get("catalog_id"),
    }
    return "rh3:" + sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def render_hash_short(render_hash: str | None) -> str | None:
    return _history.render_hash_short(render_hash)


def _row_hash_payload(row: HistoryRow) -> dict:
    canvas_aspect_id, canvas_aspect_ratio = _canvas_aspect_metadata({
        "render_canvas_aspect": row.render_canvas_aspect,
        "render_canvas_aspect_id": row.render_canvas_aspect_id,
        "render_canvas_aspect_ratio": row.render_canvas_aspect_ratio,
    })
    item = {
        "input": row.input,
        "ddl": row.ddl,
        "score": json.loads(row.score) if row.score else {},
        "svg": row.svg,
        "catalog_id": row.catalog_id,
        "render_build_number": row.render_build_number,
        "render_engine_id": row.render_engine_id,
        "render_engine_version": row.render_engine_version,
        "render_canvas_aspect": row.render_canvas_aspect or canvas_aspect_id,
        "render_canvas_aspect_id": canvas_aspect_id,
        "render_canvas_aspect_ratio": canvas_aspect_ratio,
        "render_color_catalog_id": row.render_color_catalog_id,
        "render_color_catalog_name": row.render_color_catalog_name,
        "render_color_catalog_sub": row.render_color_catalog_sub,
        "render_seed": row.render_seed,
        "render_wild": row.render_wild == "1",
        "composition_seed": row.composition_seed,
    }
    if row.render_color_map is not None:
        try:
            item["render_color_map"] = json.loads(row.render_color_map)
        except json.JSONDecodeError:
            item["render_color_map"] = None
    return item


def _backfill_render_hashes(conn) -> None:
    if engine.dialect.name != "sqlite":
        return
    rows = conn.execute(text(
        """
        SELECT id, input, ddl, score, svg, catalog_id, render_build_number,
               render_engine_id, render_engine_version,
               render_color_catalog_id, render_color_catalog_name,
               render_color_catalog_sub, render_color_map, render_canvas_aspect,
               render_canvas_aspect_id, render_canvas_aspect_ratio, render_seed,
               composition_seed
        FROM history
        WHERE render_hash IS NULL OR render_hash = ''
        """
    ))
    for row in rows.mappings():
        try:
            score = json.loads(row["score"]) if row["score"] else {}
        except (json.JSONDecodeError, TypeError):
            _logger.error("skipping render-hash backfill for corrupt score JSON: history_id=%s", row["id"])
            continue
        if not isinstance(score, dict):
            _logger.error("skipping render-hash backfill for non-object score JSON: history_id=%s", row["id"])
            continue
        item = {
            "input": row["input"],
            "ddl": row["ddl"],
            "score": score,
            "svg": row["svg"],
            "catalog_id": row["catalog_id"],
            "render_build_number": row["render_build_number"],
            "render_engine_id": row["render_engine_id"],
            "render_engine_version": row["render_engine_version"],
            "render_canvas_aspect": row["render_canvas_aspect"],
            "render_canvas_aspect_id": row["render_canvas_aspect_id"],
            "render_canvas_aspect_ratio": row["render_canvas_aspect_ratio"],
            "render_color_catalog_id": row["render_color_catalog_id"],
            "render_color_catalog_name": row["render_color_catalog_name"],
            "render_color_catalog_sub": row["render_color_catalog_sub"],
            "render_seed": row["render_seed"],
            "composition_seed": row["composition_seed"],
        }
        if row["render_color_map"] is not None:
            try:
                item["render_color_map"] = json.loads(row["render_color_map"])
            except json.JSONDecodeError:
                item["render_color_map"] = None
        conn.execute(
            text("UPDATE history SET render_hash = :render_hash WHERE id = :id"),
            {"id": row["id"], "render_hash": render_hash_for_item(item)},
        )


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


_DUMMY_PASSWORD_HASH = _hash_password("inku-nonexistent-account-timing-guard")


def _ensure_default_user_group(session: Session | None = None) -> None:
    with _session_scope(session) as (active_session, owns_session):
        exists = active_session.query(UserGroupRow).first()
        if exists:
            return
        active_session.add(UserGroupRow(id=str(uuid.uuid4()), name="default", at=_now_ms()))
        _finish_session(active_session, owns_session)


def has_permission_group(actor: dict, name: str) -> bool:
    return _access.has_permission_group(actor, name)


def _actor_of(user_id: str) -> dict:
    """The actor a scope decision is made against: identity plus what it holds.

    Read from the account rather than taken from the caller, because every public
    function in this module is handed a bare `user_id` and a scope that trusted
    what it was told would widen for anyone who could name an id.
    """
    with SessionLocal() as session:
        row = session.query(UserAccountRow).filter(UserAccountRow.id == user_id).first()
        if row is None:
            # No account, no groups: falls through to the owner-only branch of
            # every predicate. An unknown id must never widen anything.
            return {"id": user_id, "permission_groups": [], "group_id": None}
        return {
            "id": user_id,
            "permission_groups": _permission_groups_of(session, user_id),
            "group_id": row.group_id,
        }


def _owner_actor(user_id: str) -> dict:
    return _access._owner_actor(user_id)


ACL_SUBJECT_TYPES = _access.ACL_SUBJECT_TYPES
ACL_PERMISSIONS = _access.ACL_PERMISSIONS


def _acl_grants(actor: dict, permissions: tuple[str, ...]):
    return _access._acl_grants(actor, permissions)


def _shared_with_group(actor: dict):
    return _access._shared_with_group(actor)


def _same_org_group(actor: dict):
    return _access._same_org_group(actor)


def _readable_by(actor: dict, owner_column, acl_history_id=None):
    return _access._readable_by(actor, owner_column, acl_history_id)


def _writable_by(actor: dict, owner_column, acl_history_id=None):
    return _access._writable_by(actor, owner_column, acl_history_id)


def _owned_by(actor: dict, owner_column):
    return _access._owned_by(actor, owner_column)


def _readable_node(actor: dict):
    return _access._readable_node(actor)


def _readable_edge(actor: dict):
    return _access._readable_edge(actor)


def _readable_node_sql(actor: dict, alias: str = "n") -> tuple[str, dict]:
    return _access._readable_node_sql(actor, alias)


def _readable_sql(actor: dict, owner_column: str, acl_history_id: str | None = None) -> tuple[str, dict]:
    return _access._readable_sql(actor, owner_column, acl_history_id)


def _derived_role(names) -> str:
    """The legacy role column's value, derived from the groups a member holds."""
    for group, role in _ROLE_MIRROR_BY_GROUP.items():
        if group in names:
            return role
    return "user"


def _normalize_permission_groups(names) -> list[str]:
    """Requested group names, deduplicated and ordered by PERMISSION_GROUPS."""
    if isinstance(names, str):
        raise ValueError("permission_groups must be a list")
    requested = set(names or ())
    unknown = requested - set(PERMISSION_GROUPS)
    if unknown:
        raise ValueError(f"invalid permission group: {sorted(unknown)[0]}")
    if not requested:
        raise ValueError("at least one permission group is required")
    return [name for name in PERMISSION_GROUPS if name in requested]


def _permission_group_ids(session) -> dict[str, str]:
    return {row.name: row.id for row in session.query(PermissionGroupRow).all()}


def _permission_groups_of(session, user_id: str) -> list[str]:
    held = {
        name
        for (name,) in session.query(PermissionGroupRow.name)
        .join(UserPermissionGroupRow, UserPermissionGroupRow.permission_group_id == PermissionGroupRow.id)
        .filter(UserPermissionGroupRow.user_id == user_id)
        .all()
    }
    return [name for name in PERMISSION_GROUPS if name in held]


def _set_permission_groups(session, row: UserAccountRow, names) -> list[str]:
    """Replace a member's permission groups and refresh the derived role mirror.

    Writes the memberships that decide what the member may do, then the legacy
    role column that only exists so older builds can still read this database.
    """
    wanted = _normalize_permission_groups(names)
    by_name = _permission_group_ids(session)
    missing = [name for name in wanted if name not in by_name]
    if missing:
        raise ValueError(f"permission group not found: {missing[0]}")
    session.query(UserPermissionGroupRow).filter(
        UserPermissionGroupRow.user_id == row.id
    ).delete(synchronize_session=False)
    for name in wanted:
        session.add(
            UserPermissionGroupRow(
                id=str(uuid.uuid4()),
                user_id=row.id,
                permission_group_id=by_name[name],
                at=_now_ms(),
            )
        )
    row.role = _derived_role(wanted)
    return wanted


def _holds_no_elevated_group(session):
    """Filter for the members a leader may administer: no admins, no leaders.

    Asks the memberships rather than the role mirror, so an account whose legacy
    column still says `user` is judged by what it actually holds.
    """
    elevated = (
        session.query(UserPermissionGroupRow.user_id)
        .join(PermissionGroupRow, PermissionGroupRow.id == UserPermissionGroupRow.permission_group_id)
        .filter(PermissionGroupRow.name.in_(_ELEVATED_PERMISSION_GROUPS))
    )
    return ~UserAccountRow.id.in_(elevated)


def _ensure_permission_groups(session: Session | None = None) -> None:
    """Seed the three fixed permission groups. Idempotent."""
    with _session_scope(session) as (active_session, owns_session):
        existing = {row.name for row in active_session.query(PermissionGroupRow).all()}
        added = False
        for name in PERMISSION_GROUPS:
            if name in existing:
                continue
            active_session.add(PermissionGroupRow(id=str(uuid.uuid4()), name=name, at=_now_ms()))
            added = True
        if added:
            _finish_session(active_session, owns_session)


def _migrate_roles_to_permission_groups(session: Session | None = None) -> None:
    """Give every pre-existing account the one group its legacy role names.

    The mapping is one-to-one on purpose: an admin becomes `admins` and nothing
    else.  Reading it as "an admin is also a leader" would make the original role
    unrecoverable, and the many-to-many exists for accounts that are given both
    deliberately, not for accounts a migration guessed at.

    Idempotent by membership, not by role: an account that already holds any
    permission group is left alone, so a second run adds nothing and an account
    later given `admins` + `leaders` is not knocked back down to one.
    """
    with _session_scope(session) as (active_session, owns_session):
        by_name = _permission_group_ids(active_session)
        if not by_name:
            return
        assigned = {
            user_id
            for (user_id,) in active_session.query(UserPermissionGroupRow.user_id).distinct().all()
        }
        added = False
        for row in active_session.query(UserAccountRow).all():
            if row.id in assigned:
                continue
            name = _LEGACY_ROLE_TO_PERMISSION_GROUP.get(row.role, "users")
            active_session.add(
                UserPermissionGroupRow(
                    id=str(uuid.uuid4()),
                    user_id=row.id,
                    permission_group_id=by_name[name],
                    at=_now_ms(),
                )
            )
            added = True
        if added:
            _finish_session(active_session, owns_session)


def _bootstrap_admin_password() -> str | None:
    # An empty value means unset, not a zero-length password: compose interpolation
    # (${VAR:-}) and env-file templates hand one over whenever the operator left the
    # field blank. Raising there would fail startup on an empty database, where the
    # bootstrap admin is the only thing that reads this.
    password = os.getenv("INKU_BOOTSTRAP_ADMIN_PASSWORD")
    if password:
        if len(password) < 8:
            raise ValueError("INKU_BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters")
        return password

    allow_insecure = os.getenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", "").lower() in {"1", "true", "yes"}
    if allow_insecure:
        return "inku-admin"
    return None


def _ensure_bootstrap_admin(session: Session | None = None) -> None:
    with _session_scope(session) as (active_session, owns_session):
        if active_session.query(UserAccountRow).first():
            return
        group = active_session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).first()
        password = _bootstrap_admin_password()
        if password is None:
            return
        row = UserAccountRow(
            id=str(uuid.uuid4()),
            username=os.getenv("INKU_BOOTSTRAP_ADMIN_USERNAME", "admin"),
            email=os.getenv("INKU_BOOTSTRAP_ADMIN_EMAIL", "admin@local"),
            password_hash=_hash_password(password),
            role=_derived_role(["admins"]),
            group_id=group.id if group else None,
            at=_now_ms(),
        )
        active_session.add(row)
        active_session.flush()
        _set_permission_groups(active_session, row, ["admins"])
        _finish_session(active_session, owns_session)


def _backfill_history_identity_and_lineage(session: Session | None = None) -> None:
    with _session_scope(session) as (active_session, owns_session):
        rows = active_session.query(HistoryRow).filter(
            or_(
                HistoryRow.source_text.is_(None),
                HistoryRow.description_hash.is_(None),
                HistoryRow.lineage_node_id.is_(None),
            )
        ).all()
        changed = False
        for row in rows:
            source_text = row.source_text if row.source_text is not None else row.input
            if row.source_text is None:
                row.source_text = source_text
                changed = True
            expected_hash = description_hash(source_text)
            if not row.description_hash:
                row.description_hash = expected_hash
                changed = True
            if not row.history_visibility:
                row.history_visibility = "normal"
                changed = True
            node = None
            if row.lineage_node_id:
                node = active_session.get(LineageNodeRow, row.lineage_node_id)
            if node is None:
                node = active_session.query(LineageNodeRow).filter(LineageNodeRow.history_id == row.id).first()
            if node is None and row.user_id:
                node = LineageNodeRow(
                    id=str(uuid.uuid4()),
                    user_id=row.user_id,
                    history_id=row.id,
                    state="lineage_only" if row.history_visibility == "lineage_only" else "active",
                    description_hash=row.description_hash,
                    render_hash=row.render_hash,
                    at=row.at,
                    root_node_id=None,
                )
                active_session.add(node)
                changed = True
            if node is not None and row.lineage_node_id != node.id:
                row.lineage_node_id = node.id
                changed = True
        active_session.flush()
        nodes = active_session.query(LineageNodeRow).all()
        parent_by_child = {
            edge.child_node_id: edge.parent_node_id
            for edge in active_session.query(LineageEdgeRow).all()
        }
        node_by_id = {node.id: node for node in nodes}

        def resolve_root(node_id: str) -> str:
            seen: set[str] = set()
            current = node_id
            while current in parent_by_child and current not in seen:
                seen.add(current)
                parent_id = parent_by_child[current]
                if parent_id not in node_by_id:
                    break
                current = parent_id
            return current

        for node in nodes:
            expected_root = resolve_root(node.id)
            if node.root_node_id != expected_root:
                node.root_node_id = expected_root
                changed = True
        if changed:
            _finish_session(active_session, owns_session)


def _lineage_edge_to_dict(row: LineageEdgeRow) -> dict:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    )._lineage_edge_to_dict(row)


def _ancestor_edge_ids(session, actor: dict, focus_node_id: str, limit: int) -> list[str]:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    )._ancestor_edge_ids(session, actor, focus_node_id, limit)


def _descendant_edge_ids(
    session,
    actor: dict,
    focus_node_id: str,
    depth: int,
    limit: int,
) -> list[str]:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    )._descendant_edge_ids(session, actor, focus_node_id, depth, limit)


def _lineage_node_payload(
    node: LineageNodeRow,
    readable: bool,
    child_counts: dict,
    history_by_id: dict,
    generations: dict,
) -> dict:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    )._lineage_node_payload(node, readable, child_counts, history_by_id, generations)


def _lineage_generations(session, actor: dict, node_ids: list[str]) -> dict[str, int]:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    )._lineage_generations(session, actor, node_ids)


def get_lineage(user_id: str, focus_node_id: str, descendant_depth: int = 2, node_limit: int = 200) -> dict | None:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    ).get_lineage(user_id, focus_node_id, descendant_depth, node_limit)


def promote_lineage_node(user_id: str, node_id: str) -> dict | None:
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    ).promote_lineage_node(user_id, node_id)


def get_lineage_branch(user_id: str, target_node_id: str) -> dict | None:
    """Return the single primary-parent path from root through target."""
    return _lineage.LineageStore(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        row_to_dict_fn=_row_to_dict,
    ).get_lineage_branch(user_id, target_node_id)


def _okugaki_to_dict(row: OkugakiRow) -> dict:
    return _okugaki.okugaki_to_dict(row)


def _okugaki_store() -> _okugaki.OkugakiStore:
    return _okugaki.OkugakiStore(
        SessionLocal,
        _actor_of,
        _owner_actor,
        _canonical_json,
    )


def add_okugaki(user_id: str, item: dict, *, idempotency_key: str | None = None) -> dict:
    return _okugaki_store().add_okugaki(user_id, item, idempotency_key=idempotency_key)


def list_okugaki(user_id: str, target_node_id: str) -> list[dict]:
    return _okugaki_store().list_okugaki(user_id, target_node_id)


def get_okugaki_by_idempotency(user_id: str, idempotency_key: str) -> dict | None:
    return _okugaki_store().get_okugaki_by_idempotency(user_id, idempotency_key)


def delete_okugaki(user_id: str, okugaki_id: str) -> bool:
    return _okugaki_store().delete_okugaki(user_id, okugaki_id)



def _oldest_admin_id(session) -> str | None:
    """The administrator who has been here longest.

    Shared by the history-owner fallback and by single-user mode so the two
    can never drift into naming different people.
    """
    admin = (
        session.query(UserAccountRow)
        .join(UserPermissionGroupRow, UserPermissionGroupRow.user_id == UserAccountRow.id)
        .join(PermissionGroupRow, PermissionGroupRow.id == UserPermissionGroupRow.permission_group_id)
        .filter(PermissionGroupRow.name == "admins")
        .order_by(UserAccountRow.at.asc())
        .first()
    )
    return admin.id if admin else None


def _history_owner_user_id(session: Session | None = None) -> str | None:
    with _session_scope(session) as (active_session, _owns_session):
        admin_id = _oldest_admin_id(active_session)
        if admin_id:
            return admin_id
        user = active_session.query(UserAccountRow).order_by(UserAccountRow.at.asc()).first()
        return user.id if user else None


def admin_history_owner_id() -> str | None:
    return _history_owner_user_id()


# ---------------------------------------------------------------------------
# Single-user mode
#
# A server that belongs to one person still runs the whole multi-user
# machinery: nothing is removed, and turning the flag off puts the login
# screen back with every account and every work where it was.  What the flag
# changes is only who an unauthenticated request is taken to be.
# ---------------------------------------------------------------------------

_SINGLE_USER_SETTING_KEY = _settings.SINGLE_USER_SETTINGS_KEY


def single_user_mode_enabled() -> bool:
    """Whether this server runs as one person's own.

    Off unless explicitly asked for: a deployment that merely upgrades must
    not quietly lose its login screen.  The distribution turns it on in its
    own compose file, not here.

    An empty value reads as unset, matching how _bootstrap_admin_password
    treats a blank field handed over by compose interpolation.

    This is the only reader of the variable.  deps.py and the /api/info
    banner both come through here, so the guard and what the banner claims
    cannot disagree.
    """
    value = os.getenv("INKU_SINGLE_USER")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _create_single_user_account() -> str | None:
    """Make the one account an empty database is missing.

    Only ever reached when there is no account at all: with no bootstrap
    password set, _ensure_bootstrap_admin leaves the database empty and the
    first request would have nobody to be.
    """
    _ensure_default_user_group()
    _ensure_permission_groups()
    with SessionLocal() as session:
        if session.query(UserAccountRow).first():
            return None
        group = session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).first()
        # No bootstrap password means nobody chose one.  The account still
        # needs a hash, so it gets an unusable random one; the UI tells the
        # owner to set a password before they ever turn single-user mode off,
        # because that password is the only way back in.
        password = _bootstrap_admin_password() or secrets.token_urlsafe(32)
        row = UserAccountRow(
            id=str(uuid.uuid4()),
            username=os.getenv("INKU_BOOTSTRAP_ADMIN_USERNAME", "admin"),
            email=os.getenv("INKU_BOOTSTRAP_ADMIN_EMAIL", "admin@local"),
            password_hash=_hash_password(password),
            role=_derived_role(["admins"]),
            group_id=group.id if group else None,
            at=_now_ms(),
        )
        session.add(row)
        session.commit()
        # The one account owns the server, so it holds `admins`.  _oldest_admin_id
        # asks the permission groups now, and it is the same query that resolves
        # the history owner: leaving this to the role mirror would make the two
        # name different people.
        _set_permission_groups(session, row, ["admins"])
        session.commit()
        return row.id


def single_user_account() -> dict | None:
    """The account this server belongs to, or None when it has none.

    Resolution is pinned rather than derived on every call.  A derived answer
    moves the moment the oldest administrator is deleted, which would read as
    "my works disappeared"; a pinned one is a row in the same database, so a
    restored backup brings the same person back with it.

    The pin holds the account id, not its name, because the name can be
    changed from the settings screen.
    """
    pin_store = _single_user_pin_store()
    pinned = pin_store.get()
    if pinned:
        user = get_user(pinned)
        if user:
            return user
    with SessionLocal() as session:
        user_id = _oldest_admin_id(session)
        if user_id is None and session.query(UserAccountRow).first():
            # Accounts exist but none of them administers.  Single-user mode
            # has nobody to hand the server to, so the login screen stays.
            return None
    if user_id is None:
        user_id = _create_single_user_account()
    if user_id is None:
        return None
    user = get_user(user_id)
    if user is None:
        return None
    pin_store.update(user_id)
    return user


def single_user_pinned_id() -> str | None:
    """The pinned account id, without resolving or writing one."""
    return _single_user_pin_store().get()


def set_single_user_pin(user_id: str) -> dict:
    """Move the pin to another account. Raises ValueError when it may not move.

    Only an account holding `admins` may receive it. Anyone else would open the
    app to a settings screen they cannot reach, unable to change the LLM
    connection -- which is the whole point of a server that belongs to one
    person.

    Sessions already open are left alone deliberately. The pin decides who the
    NEXT automatic login becomes; revoking the current one would drop whoever is
    working right now, and the person moving the pin is usually that person.
    """
    if not single_user_mode_enabled():
        # Nothing reads the pin when the mode is off, so writing it would look
        # like it had taken effect and change nothing.
        raise ValueError("single-user mode is not enabled")
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if row is None:
            raise ValueError("user not found")
        if "admins" not in _permission_groups_of(session, user_id):
            raise ValueError("the single user must hold the admins permission group")
    _single_user_pin_store().update(user_id)
    return single_user_pin_status()


def single_user_pin_status() -> dict:
    """Who the app opens as, and who it could open as instead."""
    pinned_id = single_user_pinned_id()
    pinned = get_user(pinned_id) if pinned_id else None
    with SessionLocal() as session:
        eligible = [
            {"id": row.id, "username": row.username}
            for row in session.query(UserAccountRow).order_by(UserAccountRow.at.asc()).all()
            if "admins" in _permission_groups_of(session, row.id)
        ]
    return {
        "enabled": single_user_mode_enabled(),
        "user_id": pinned_id,
        "username": pinned["username"] if pinned else None,
        "eligible": eligible,
    }


def database_info() -> dict:
    url = engine.url
    db_path = _sqlite_db_path()
    file_size = db_path.stat().st_size if db_path and db_path.exists() else None
    return {
        "backend": url.get_backend_name(),
        "driver": url.get_driver_name(),
        "url": url.render_as_string(hide_password=True),
        "database": url.database,
        "is_default": PERSISTENCE_CONFIG.canonical_is_default,
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


def _app_settings_store() -> AppSettingsStore:
    return AppSettingsStore(SessionLocal, _now_ms)


def _single_user_pin_store() -> _settings.SingleUserPinStore:
    return _settings.SingleUserPinStore(_app_settings_store())


def _read_app_setting(key: str) -> dict | None:
    return _app_settings_store().read(key)


def _write_app_setting(key: str, value: dict) -> dict:
    return _app_settings_store().write(key, value)


def _backup_service() -> _BackupService:
    return _BackupService(
        backup_dir=_DB_BACKUP_DIR,
        dialect_name=engine.dialect.name,
        database_path=_sqlite_db_path,
        now_ms=_now_ms,
        read_setting=_read_app_setting,
        write_setting=_write_app_setting,
    )


def _normalize_db_backup_settings(settings: dict | None) -> dict:
    return _backup_service().normalize_settings(settings)


def get_db_backup_settings() -> dict:
    return _backup_service().get_settings()


def update_db_backup_settings(
    interval_days: int,
    max_generations: int,
    backup_hour: int | None = None,
    backup_minute: int | None = None,
) -> dict:
    return _backup_service().update_settings(
        interval_days,
        max_generations,
        backup_hour,
        backup_minute,
    )


def _normalize_output_save_settings(settings: dict | None) -> dict:
    return _settings.normalize_output_save_settings(settings)


def _normalize_render_concurrency_settings(settings: dict | None) -> dict:
    return _settings.normalize_render_concurrency_settings(settings)


def _clamped_concurrency(value: object, key: str) -> int:
    return _settings.clamped_concurrency(value, key)


def get_render_concurrency_settings() -> dict:
    return _render_concurrency_settings_store().get()


def _render_concurrency_settings_store() -> _settings.RenderConcurrencySettingsStore:
    return _settings.RenderConcurrencySettingsStore(_app_settings_store())


def update_render_concurrency_settings(server_limit: int, client_limit: int) -> dict:
    return _render_concurrency_settings_store().update(server_limit, client_limit)


def get_render_limit_settings() -> dict:
    return _render_limit_settings_store().get()


def _render_limit_settings_store() -> _settings.RenderLimitSettingsStore:
    return _settings.RenderLimitSettingsStore(_app_settings_store(), normalize_limits)


def update_render_limit_settings(settings: dict) -> dict:
    return _render_limit_settings_store().update(settings)


def get_output_save_settings() -> dict:
    return _output_save_settings_store().get()


def _output_save_settings_store() -> _settings.OutputSaveSettingsStore:
    return _settings.OutputSaveSettingsStore(_app_settings_store())


def update_output_save_settings(enabled: bool, output_dir: str, png_size: int) -> dict:
    return _output_save_settings_store().update(enabled, output_dir, png_size)


def _normalize_thumbnail_settings(settings: dict | None) -> dict:
    return _settings.normalize_thumbnail_settings(settings)


def get_thumbnail_settings() -> dict:
    return _thumbnail_settings_store().get()


def _thumbnail_settings_store() -> _settings.ThumbnailSettingsStore:
    return _settings.ThumbnailSettingsStore(_app_settings_store())


def update_thumbnail_settings(hidpi: bool, workers: int) -> dict:
    return _thumbnail_settings_store().update(hidpi, workers)


def _normalize_log_retention_settings(settings: dict | None) -> dict:
    return _settings.normalize_log_retention_settings(settings)


def get_log_retention_settings() -> dict:
    return _log_retention_settings_store().get()


def _log_retention_settings_store() -> _settings.LogRetentionSettingsStore:
    return _settings.LogRetentionSettingsStore(_app_settings_store())


def update_log_retention_settings(enabled: bool, retention_days: int, rotate: str, compress: bool) -> dict:
    return _log_retention_settings_store().update(
        enabled, retention_days, rotate, compress
    )


def _model_settings_store():
    from .model_settings import normalize_model_settings

    from .model_settings import storage_model_settings

    return _settings.ModelSettingsStore(
        _app_settings_store(), normalize_model_settings, storage_model_settings
    )


def get_model_settings() -> dict:
    return _model_settings_store().get()


def update_model_settings(settings: dict) -> dict:
    return _model_settings_store().update(settings)


_AUTH_SETTINGS_KEY = _settings.AUTH_SETTINGS_KEY
_AUTH_DEFAULT_SETTINGS = _settings.AUTH_DEFAULT_SETTINGS


def _normalize_auth_settings(settings: dict | None) -> dict:
    return _settings.normalize_auth_settings(settings)


def _auth_settings_store():
    return _settings.AuthSettingsStore(_app_settings_store(), os.getenv)


def get_auth_settings() -> dict:
    return _auth_settings_store().get()


def update_auth_settings(google_enabled: bool, local_enabled: bool) -> dict:
    return _auth_settings_store().update(google_enabled, local_enabled)


def _db_backup_file(kind: str, at_ms: int) -> Path:
    return _backup_service().backup_file(kind, at_ms)


def _copy_sqlite_database(destination: Path) -> None:
    _backup_service().copy_sqlite_database(destination)


def _prune_auto_backups(max_generations: int) -> None:
    _backup_service().prune_auto_backups(max_generations)


def create_db_backup(*, manual: bool = False) -> dict:
    return _backup_service().create_backup(manual=manual)


def next_scheduled_db_backup_at(settings: dict | None = None) -> int:
    return _backup_service().next_scheduled_at(settings)


def ensure_scheduled_db_backup() -> dict | None:
    return _backup_service().ensure_scheduled_backup()


def list_db_backups(limit: int = _DB_BACKUP_LIST_LIMIT) -> dict:
    return _backup_service().list_backups(limit)


def db_backup_status() -> dict:
    return _backup_service().status()


def _assign_unowned_history_to_admin(session: Session | None = None) -> None:
    with _session_scope(session) as (active_session, owns_session):
        owner_id = _history_owner_user_id(active_session)
        if not owner_id:
            return
        active_session.query(HistoryRow).filter(HistoryRow.user_id.is_(None)).update(
            {HistoryRow.user_id: owner_id},
            synchronize_session=False,
        )
        _finish_session(active_session, owns_session)


def _row_to_dict(row: HistoryRow) -> dict:
    return _history.row_to_dict(
        row,
        logger=_logger,
        render_hash_short_fn=render_hash_short,
        normalize_canvas_aspect_id_fn=normalize_canvas_aspect_id,
        canvas_aspect_ratio_for_aspect_fn=canvas_aspect_ratio_for_aspect,
    )


def _rows_to_dicts_with_lineage(session, rows: list[HistoryRow], actor: dict | None = None) -> list[dict]:
    """Compatibility façade for the lineage-aware history list projection."""
    return _history.HistoryListProjector(
        row_to_dict_fn=_row_to_dict,
        lineage_edge_to_dict_fn=_lineage_edge_to_dict,
    ).rows_to_dicts_with_lineage(session, rows, actor=actor)


def _group_to_dict(row: UserGroupRow) -> dict:
    return _groups.group_to_dict(row)


def _user_to_dict(row: UserAccountRow, group_name: str | None = None) -> dict:
    from sqlalchemy.orm import object_session
    from .model_settings import normalize_user_model_settings

    # Read the memberships through the row's own session rather than defaulting
    # to an empty list when there is none: an actor that silently came back with
    # no permission groups would be refused everywhere, and nothing would say why.
    session = object_session(row)
    if session is None:
        raise RuntimeError("_user_to_dict needs an attached row to read permission groups")
    permission_groups = _permission_groups_of(session, row.id)

    try:
        model_settings = json.loads(row.model_settings or "{}")
    except json.JSONDecodeError:
        model_settings = {}
    try:
        ui_custom_raw = json.loads(row.ui_custom or "{}")
    except json.JSONDecodeError:
        ui_custom_raw = {}
    ui_custom = {
        key: value
        for key, value in ui_custom_raw.items()
        if key in _UI_CUSTOM_KEYS and isinstance(value, bool)
    } if isinstance(ui_custom_raw, dict) else {}
    history_strip_fields = normalize_history_strip_fields(
        _loads_or_none(row.history_strip_fields)
    )
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "permission_groups": permission_groups,
        "permission_group_labels": [
            PERMISSION_GROUP_LABELS.get(name, name) for name in permission_groups
        ],
        "group_id": row.group_id,
        "group_name": group_name,
        "ui_theme": row.ui_theme if row.ui_theme in {"light", "dark"} else "light",
        "ui_mode": row.ui_mode if row.ui_mode in _UI_MODES else "simple",
        "ui_custom": ui_custom,
        "history_strip_fields": history_strip_fields,
        "tooltips_enabled": row.tooltips_enabled is not False,
        "download_folder_enabled": row.download_folder_enabled is True,
        "download_folder_name": row.download_folder_name,
        "settings_tab": row.settings_tab if row.settings_tab in _SETTINGS_TABS else "db",
        "model_settings": normalize_user_model_settings(model_settings),
        "image_generation_count": row.image_generation_count or 0,
        "at": row.at,
    }


def add_item(item: dict) -> dict:
    return _history.HistoryWriter(
        session_factory=SessionLocal,
        actor_of_fn=_actor_of,
        owned_by_fn=_owned_by,
        readable_node_fn=_readable_node,
        row_to_dict_fn=_row_to_dict,
        render_hash_for_item_fn=render_hash_for_item,
        description_hash_fn=description_hash,
        normalize_canvas_aspect_id_fn=normalize_canvas_aspect_id,
        canvas_aspect_ratio_for_aspect_fn=canvas_aspect_ratio_for_aspect,
        canonical_json_fn=_canonical_json,
    ).add_item(item)


def record_unread_words(user_id: str, words: list[str], context: str, *, at: int) -> None:
    return _feedback.UnreadWordStore(SessionLocal).record_unread_words(user_id, words, context, at=at)


def list_unread_words(user_id: str | None = None, *, limit: int = 100) -> list[dict]:
    return _feedback.UnreadWordStore(SessionLocal).list_unread_words(user_id, limit=limit)


def list_user_groups() -> list[dict]:
    return _groups.UserGroupStore(SessionLocal, uuid.uuid4, _now_ms).list_user_groups()


def add_user_group(name: str) -> dict:
    return _groups.UserGroupStore(SessionLocal, uuid.uuid4, _now_ms).add_user_group(name)


def update_user_group(group_id: str, name: str) -> dict | None:
    return _groups.UserGroupStore(SessionLocal, uuid.uuid4, _now_ms).update_user_group(group_id, name)


def delete_user_group(group_id: str) -> bool:
    return _groups.UserGroupStore(SessionLocal, uuid.uuid4, _now_ms).delete_user_group(group_id)


def _account_reader() -> _accounts.UserAccountReader:
    return _accounts.UserAccountReader(
        SessionLocal,
        _user_to_dict,
        verify_password,
        _DUMMY_PASSWORD_HASH,
    )


def list_users() -> list[dict]:
    return _account_reader().list_users()


def get_user(user_id: str) -> dict | None:
    return _account_reader().get_user(user_id)


def authenticate_user(username: str, password: str) -> dict | None:
    return _account_reader().authenticate_user(username, password)


def _session_store() -> _sessions.SessionStore:
    return _sessions.SessionStore(
        SessionLocal,
        secrets.token_urlsafe,
        _hash_token,
        _now_ms,
        _SESSION_MAX_AGE_SECONDS,
        _user_to_dict,
    )


def create_session(user_id: str) -> str:
    return _session_store().create_session(user_id)


def _session_expiry_cutoff_ms(now_ms: int | None = None) -> int | None:
    return _session_store().session_expiry_cutoff_ms(now_ms)


def _delete_expired_sessions(session) -> int:
    return _session_store().delete_expired_sessions(session)


def get_session_user(token: str) -> dict | None:
    return _session_store().get_session_user(token)


def delete_session(token: str) -> bool:
    return _session_store().delete_session(token)


def _external_identity_store() -> _identities.ExternalIdentityStore:
    return _identities.ExternalIdentityStore(SessionLocal, uuid.uuid4, _now_ms, _user_to_dict)


def link_external_identity(
    user_id: str,
    *,
    provider: str,
    subject: str,
    email: str | None = None,
) -> dict:
    return _external_identity_store().link_external_identity(
        user_id,
        provider=provider,
        subject=subject,
        email=email,
    )


def get_user_by_external_identity(provider: str, subject: str) -> dict | None:
    return _external_identity_store().get_user_by_external_identity(provider, subject)


def list_users_for_actor(actor: dict) -> list[dict]:
    return _account_reader().list_users_for_actor(actor)


def list_group_peers(user_id: str) -> list[dict]:
    return _account_reader().list_group_peers(user_id)


def _account_creator() -> _accounts.UserAccountCreator:
    return _accounts.UserAccountCreator(
        SessionLocal,
        uuid.uuid4,
        _now_ms,
        _hash_password,
        _normalize_permission_groups,
        _derived_role,
        _set_permission_groups,
        _user_to_dict,
    )


def add_user(username: str, email: str, password: str, permission_groups: list[str], group_id: str | None) -> dict:
    return _account_creator().add_user(username, email, password, permission_groups, group_id)


def _account_updater() -> _accounts.UserAccountUpdater:
    return _accounts.UserAccountUpdater(
        SessionLocal,
        _hash_password,
        _set_permission_groups,
        has_permission_group,
        _holds_no_elevated_group,
        _user_to_dict,
        _UNSET,
    )


def update_user(
    user_id: str,
    *,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
    permission_groups: list[str] | None = None,
    group_id: str | None | object = _UNSET,
    actor: dict | None = None,
) -> dict | None:
    return _account_updater().update_user(
        user_id,
        username=username,
        email=email,
        password=password,
        permission_groups=permission_groups,
        group_id=group_id,
        actor=actor,
    )


def _current_user_profile_updater() -> _accounts.CurrentUserProfileUpdater:
    return _accounts.CurrentUserProfileUpdater(
        SessionLocal,
        verify_password,
        _hash_password,
        _user_to_dict,
    )


def update_current_user_profile(
    user_id: str,
    *,
    email: str | None = None,
    password: str | None = None,
    current_password: str | None = None,
) -> dict | None:
    return _current_user_profile_updater().update_current_user_profile(
        user_id,
        email=email,
        password=password,
        current_password=current_password,
    )


def _user_generation_counter() -> _accounts.UserGenerationCounter:
    return _accounts.UserGenerationCounter(SessionLocal)


def increment_user_generation_count(user_id: str, amount: int = 1) -> int | None:
    return _user_generation_counter().increment_user_generation_count(user_id, amount=amount)


def _user_settings_updater() -> _settings.UserSettingsUpdater:
    return _settings.UserSettingsUpdater(SessionLocal, _user_to_dict)


def update_user_theme(user_id: str, ui_theme: str) -> dict | None:
    return _user_settings_updater().update_user_theme(user_id, ui_theme)


def update_user_settings(
    user_id: str,
    ui_theme: str | None = None,
    ui_mode: str | None = None,
    ui_custom: dict | None = None,
    tooltips_enabled: bool | None = None,
    download_folder_enabled: bool | None = None,
    download_folder_name: str | None = None,
    settings_tab: str | None = None,
    model_settings: dict | None = None,
    history_strip_fields: list | None = None,
) -> dict | None:
    return _user_settings_updater().update_user_settings(
        user_id,
        ui_theme=ui_theme,
        ui_mode=ui_mode,
        ui_custom=ui_custom,
        tooltips_enabled=tooltips_enabled,
        download_folder_enabled=download_folder_enabled,
        download_folder_name=download_folder_name,
        settings_tab=settings_tab,
        model_settings=model_settings,
        history_strip_fields=history_strip_fields,
    )


def _normalize_batch_prompt_history(items: list[str]) -> list[str]:
    return _settings.normalize_batch_prompt_history(items)


def _user_batch_prompt_history_store() -> _settings.UserBatchPromptHistoryStore:
    return _settings.UserBatchPromptHistoryStore(SessionLocal)


def get_user_batch_prompt_history(user_id: str) -> list[str]:
    return _user_batch_prompt_history_store().get(user_id)


def update_user_batch_prompt_history(user_id: str, items: list[str]) -> list[str] | None:
    return _user_batch_prompt_history_store().update(user_id, items)


def _normalize_demo_settings(settings: dict) -> dict:
    return _settings.normalize_demo_settings(settings)


def _user_demo_settings_store() -> _settings.UserDemoSettingsStore:
    return _settings.UserDemoSettingsStore(SessionLocal)


def get_user_demo_settings(user_id: str) -> dict:
    return _user_demo_settings_store().get(user_id)


def update_user_demo_settings(user_id: str, settings: dict) -> dict | None:
    return _user_demo_settings_store().update(user_id, settings)


def _normalize_export_templates(items: list[dict]) -> list[dict]:
    return _settings.normalize_export_templates(items)


def _user_export_template_store() -> _settings.UserExportTemplateStore:
    return _settings.UserExportTemplateStore(SessionLocal)


def get_user_export_templates(user_id: str) -> list[dict]:
    return _user_export_template_store().get(user_id)


def update_user_export_templates(user_id: str, items: list[dict]) -> list[dict] | None:
    return _user_export_template_store().update(user_id, items)


def _normalize_plugin_storage(storage: dict) -> dict:
    return _settings.normalize_plugin_storage(storage)


def _user_plugin_storage_store() -> _settings.UserPluginStorageStore:
    return _settings.UserPluginStorageStore(SessionLocal)


def get_user_plugin_storage(user_id: str) -> dict:
    return _user_plugin_storage_store().get(user_id)


def update_user_plugin_storage(user_id: str, storage: dict) -> dict | None:
    return _user_plugin_storage_store().update(user_id, storage)


def update_user_plugin_value(user_id: str, plugin_id: str, value: dict) -> dict | None:
    return _user_plugin_storage_store().update_value(user_id, plugin_id, value)


def _acl_to_dict(row: HistoryAclRow) -> dict:
    return _access.acl_to_dict(row)


def _may_share(actor: dict, session, item_id: str) -> bool:
    return _access.may_share(actor, session, item_id)


def _history_acl_service() -> _access.HistoryAclService:
    return _access.HistoryAclService(SessionLocal, _actor_of, _now_ms)


def list_history_acl(user_id: str, item_id: str) -> list[dict] | None:
    return _history_acl_service().list_history_acl(user_id, item_id)


def _validated_acl_entries(entries: list[dict]) -> list[tuple[str, str, str]]:
    return _access.validated_acl_entries(entries)


def replace_history_acl(user_id: str, item_id: str, entries: list[dict]) -> list[dict] | None:
    return _history_acl_service().replace_history_acl(user_id, item_id, entries)


def grant_history_acl(user_id: str, item_id: str, subject_type: str, subject_id: str, permission: str) -> list[dict] | None:
    return _history_acl_service().grant_history_acl(user_id, item_id, subject_type, subject_id, permission)


def revoke_history_acl(user_id: str, item_id: str, subject_type: str, subject_id: str) -> list[dict] | None:
    return _history_acl_service().revoke_history_acl(user_id, item_id, subject_type, subject_id)


def _delete_acl_for_histories(session, history_ids: list[str]) -> None:
    return _history_acl_service().delete_acl_for_histories(session, history_ids)


def _account_deleter() -> _accounts.UserAccountDeleter:
    return _accounts.UserAccountDeleter(
        SessionLocal,
        has_permission_group,
        _holds_no_elevated_group,
        _owner_actor,
        _owned_by,
        _delete_acl_for_histories,
    )


def delete_user(user_id: str, *, cascade: bool = False, actor: dict | None = None) -> bool:
    return _account_deleter().delete_user(user_id, cascade=cascade, actor=actor)


def _fts_match_query(search: str) -> str:
    return _history_search._fts_match_query(search)


_WHOLE_RENDER_HASH = _history_search._WHOLE_RENDER_HASH


def _is_render_hash_suffix_search(search: str) -> bool:
    return _history_search._is_render_hash_suffix_search(search)


def _history_search_clause(search: str):
    return _history_search._history_search_clause(search)


def _history_search_service() -> _HistorySearchService:
    return _HistorySearchService(
        fts_enabled=_HISTORY_FTS_ENABLED,
        dialect_name=engine.dialect.name,
        session_factory=SessionLocal,
        actor_of=_actor_of,
        readable_by=_readable_by,
        readable_sql=lambda actor, owner_column, acl_history_id=None: _readable_sql(
            actor, owner_column, acl_history_id
        ),
        rows_to_dicts_with_lineage=_rows_to_dicts_with_lineage,
    )


def _use_history_fts(search: str) -> bool:
    return _history_search_service().use_history_fts(search)


def _list_items_with_fts(
    session,
    actor: dict,
    offset: int,
    limit: int,
    trashed: bool,
    search: str,
    starred: bool,
    for_revision: bool = False,
    for_share: bool = False,
) -> tuple[list[dict], int]:
    return _history_search_service().list_items_with_fts(
        session,
        actor,
        offset,
        limit,
        trashed,
        search,
        starred,
        for_revision,
        for_share,
    )


def list_items(
    user_id: str,
    offset: int = 0,
    limit: int = 10,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
    for_revision: bool = False,
    for_share: bool = False,
) -> tuple[list[dict], int]:
    return _history_search_service().list_items(
        user_id,
        offset,
        limit,
        trashed,
        query_text,
        starred,
        for_revision,
        for_share,
    )


def list_state(user_id: str, trashed: bool = False) -> tuple[int, int | None, str | None]:
    return _history.HistoryListStateReader(SessionLocal, _actor_of).list_state(user_id, trashed)


def _history_lineage_group_reader() -> _history.HistoryLineageGroupReader:
    return _history.HistoryLineageGroupReader(
        SessionLocal,
        _actor_of,
        _rows_to_dicts_with_lineage,
        _history_search_clause,
    )


def list_lineage_groups(
    user_id: str,
    offset: int = 0,
    limit: int = 12,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
    for_revision: bool = False,
    for_share: bool = False,
    min_item_count: int = 1,
) -> tuple[list[dict], int]:
    return _history_lineage_group_reader().list_lineage_groups(
        user_id,
        offset,
        limit,
        trashed,
        query_text,
        starred,
        for_revision,
        for_share,
        min_item_count,
    )


def list_lineage_group_items(
    user_id: str,
    root_node_id: str,
    offset: int = 0,
    limit: int = 100,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
    for_revision: bool = False,
    for_share: bool = False,
) -> tuple[list[dict], int]:
    return _history_lineage_group_reader().list_lineage_group_items(
        user_id,
        root_node_id,
        offset,
        limit,
        trashed,
        query_text,
        starred,
        for_revision,
        for_share,
    )


def item_position(
    user_id: str,
    item_id: str,
    trashed: bool = False,
    starred: bool = False,
    for_revision: bool = False,
    for_share: bool = False,
) -> int | None:
    return _history.HistoryItemPositionReader(SessionLocal, _actor_of).item_position(
        user_id, item_id, trashed, starred, for_revision, for_share
    )


def set_item_starred(user_id: str, item_id: str, starred: bool, note: str | None = None) -> dict | None:
    return _history.HistoryMarkWriter(SessionLocal, _actor_of, _row_to_dict).set_item_starred(
        user_id, item_id, starred, note
    )


def set_item_for_revision(user_id: str, item_id: str, for_revision: bool) -> dict | None:
    return _history.HistoryMarkWriter(SessionLocal, _actor_of, _row_to_dict).set_item_for_revision(
        user_id, item_id, for_revision
    )


def set_item_for_share(
    user_id: str, item_id: str, for_share: bool, share_group_id: str | None = None
) -> dict | None:
    return _history.HistoryShareWriter(
        SessionLocal, _actor_of, _row_to_dict, has_permission_group
    ).set_item_for_share(user_id, item_id, for_share, share_group_id)


def history_render_hashes() -> list[tuple[str, str | None]]:
    return _history.HistoryThumbnailSourceReader(SessionLocal).history_render_hashes()


def history_svgs(ids: list[str]) -> dict[str, str]:
    return _history.HistoryThumbnailSourceReader(SessionLocal).history_svgs(ids)


def get_items(user_id: str, ids: list[str]) -> list[dict]:
    return _history.HistoryItemReader(
        SessionLocal,
        _actor_of,
        _rows_to_dicts_with_lineage,
    ).get_items(user_id, ids)


def _neighbor_score(raw: str | None) -> dict:
    return _history._neighbor_score(raw)


def list_neighbor_candidates(user_id: str, item_id: str, *, limit: int = 10_000) -> list[dict]:
    return _history.HistoryNeighborCandidateReader(
        SessionLocal,
        _actor_of,
        _history._neighbor_score,
    ).list_neighbor_candidates(user_id, item_id, limit=limit)


def delete_all(user_id: str) -> None:
    return _history.HistoryOwnedDataPurgeWriter(
        SessionLocal,
        _owner_actor,
        _delete_acl_for_histories,
    ).delete_all(user_id)


def trash_items(user_id: str, ids: list[str]) -> int:
    return _history.HistoryTrashStateWriter(SessionLocal, _actor_of).trash_items(user_id, ids)


def restore_items(user_id: str, ids: list[str]) -> int:
    return _history.HistoryTrashStateWriter(SessionLocal, _actor_of).restore_items(user_id, ids)


def delete_items(user_id: str, ids: list[str], *, require_trashed: bool = False) -> int:
    return _history.HistoryPermanentDeleteWriter(
        SessionLocal,
        _actor_of,
        _now_ms,
        _delete_acl_for_histories,
    ).delete_items(user_id, ids, require_trashed=require_trashed)


def delete_all_trashed_items(user_id: str) -> int:
    return _history.HistoryTrashPurgeWriter(
        SessionLocal,
        _owner_actor,
        delete_items,
    ).delete_all_trashed_items(user_id)
