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
from datetime import datetime, time as clock_time, timedelta
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path

from sqlalchemy import BigInteger, CheckConstraint, Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint, and_, case, create_engine, event, func, inspect, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .identity import description_hash
from .plugins import canvas_aspect_ratio_for_aspect, normalize_canvas_aspect_id

_DEFAULT_DB = "sqlite:///" + str(Path.home() / ".local" / "share" / "inku" / "inku.db")
_DB_URL = os.getenv("INKU_DB_URL", _DEFAULT_DB)
_SESSION_MAX_AGE_SECONDS = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))

_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, echo=False, future=True, connect_args=_connect_args)


if _DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_integrity(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
_logger = logging.getLogger(__name__)
_HISTORY_FTS_ENABLED = False
LINEAGE_DERIVATION_KINDS = {
    "touch_change",
    "layout_change",
    "catalog_change",
    "reinterpretation",
    "model_comparison",
    "language_comparison",
    "ddl_edit",
    "description_edit",
    "replay",
    "render_engine_change",
    "age_change",
    "hacho_change",
    "renga_reply",
    "external_seed_change",
    "canvas_aspect_change",
    "variation",  # v2.0 変奏 (Stage 1.5 の展開をまとめて振る)。v2.8.0 で hensou から改名
}

# v2.8.0 の改名表。**保存済みの行はこの表で書き換える**（`_migrate_columns`）。
# 新旧の対応は `no-git-sync/opus5/name_convantion/` にも記録がある。
_LINEAGE_KIND_RENAMES = (
    ("hensou", "variation"),
    ("touch_variation", "touch_change"),
    ("layout_variation", "layout_change"),
    ("model_variation", "model_comparison"),
    ("language_variation", "language_comparison"),
    ("render_engine_variation", "render_engine_change"),
    ("age_variation", "age_change"),
    ("hacho_variation", "hacho_change"),
    ("external_seed_variation", "external_seed_change"),
)


class Base(DeclarativeBase):
    pass


class HistoryRow(Base):
    __tablename__ = "history"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_history_user_idempotency"),)

    id           = Column(String,     primary_key=True)
    user_id      = Column(String,     ForeignKey("user_accounts.id"), nullable=True, index=True)
    at           = Column(BigInteger, nullable=False, index=True)
    input        = Column(Text,       nullable=False, default="")
    ddl          = Column(Text,       nullable=True)  # v1.98: 入力側 DDL (Stage 1 出力 / ユーザー原文)
    expanded_ddl = Column(Text,       nullable=True)  # v1.98: 展開後 DDL (Stage 1.5 出力 = Stage 2 入力)
    score        = Column(Text,       nullable=False, default="{}")
    svg          = Column(Text,       nullable=False, default="")
    output_path  = Column(Text,       nullable=True)
    elapsed_ms   = Column(Integer,    nullable=False, default=0)
    stage1_model = Column(String,     nullable=True)
    stage2_model = Column(String,     nullable=True)
    stage1_prompt_digest = Column(String, nullable=True)
    stage1_prompt_base_digest = Column(String, nullable=True)
    stage2_prompt_digest = Column(String, nullable=True)
    tokens_in    = Column(Integer,    nullable=True)
    tokens_out   = Column(Integer,    nullable=True)
    catalog_id   = Column(String,     nullable=True)
    ddl_version = Column(String, nullable=True)
    ddl_engine_version = Column(String, nullable=True)
    render_build_number = Column(String, nullable=True)
    render_color_profile = Column(Text, nullable=True)
    render_engine_id = Column(String, nullable=True)
    render_engine_version = Column(String, nullable=True)
    render_color_catalog_id = Column(String, nullable=True)
    render_color_catalog_name = Column(String, nullable=True)
    render_color_catalog_sub = Column(String, nullable=True)
    render_color_catalog = Column(Text, nullable=True)
    render_color_map = Column(Text, nullable=True)
    render_canvas_aspect = Column(String, nullable=True)
    render_canvas_aspect_id = Column(String, nullable=True)
    render_canvas_aspect_ratio = Column(Float, nullable=True)
    instruction_lang_requested = Column(String, nullable=True)
    instruction_lang_resolved = Column(String, nullable=True)
    ui_lang = Column(String, nullable=True)
    render_seed = Column(String, nullable=True)
    render_wild = Column(String, nullable=True)  # engine 12: "1"/"0"。NULL = 記録前の作品（OFF と区別する）
    composition_seed = Column(String, nullable=True)
    tenkei = Column(String, nullable=True)  # v1.97 添景水準 (none/sparse/auto)。NULL = 保存開始前の作品
    focus = Column(String, nullable=True)  # v1.98 焦点。NULL = DDL テキストから決定的に選択
    # v2.0 変奏。両方 NULL = 変奏なしの展開。moved_axes は決定的に再計算できるので列を作らない。
    variation_amplitude = Column(String, nullable=True)
    variation_seed = Column(String, nullable=True)
    # v1.98: Stage 1 がフォールバック DDL で描かれた作品の理由。NULL = 通常の解釈。
    interpret_fallback = Column(String, nullable=True)
    interpretation_seed = Column(String, nullable=True)
    seed_text = Column(Text, nullable=True)
    render_hash = Column(String, nullable=True, index=True)
    trashed      = Column(Integer,    nullable=False, default=0)
    starred      = Column(Integer,    nullable=False, default=0)
    note         = Column(Text,       nullable=True)
    source_text = Column(Text, nullable=True)
    display_label = Column(String, nullable=True)
    batch_line_number = Column(Integer, nullable=True)
    batch_run_id = Column(String, nullable=True, index=True)
    description_hash = Column(String, nullable=True, index=True)
    history_visibility = Column(String, nullable=False, default="normal", index=True)
    lineage_node_id = Column(String, nullable=True, unique=True, index=True)
    idempotency_key = Column(String, nullable=True)


class LineageNodeRow(Base):
    __tablename__ = "lineage_nodes"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    history_id = Column(String, nullable=True, unique=True, index=True)
    state = Column(String, nullable=False, default="active", index=True)
    description_hash = Column(String, nullable=True, index=True)
    render_hash = Column(String, nullable=True, index=True)
    at = Column(BigInteger, nullable=False, index=True)
    deleted_at = Column(BigInteger, nullable=True)
    root_node_id = Column(String, nullable=True, index=True)


class LineageEdgeRow(Base):
    __tablename__ = "lineage_edges"
    __table_args__ = (
        UniqueConstraint("child_node_id", name="uq_lineage_primary_parent"),
        CheckConstraint("parent_node_id <> child_node_id", name="ck_lineage_no_self_edge"),
    )

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    parent_node_id = Column(String, ForeignKey("lineage_nodes.id"), nullable=False, index=True)
    child_node_id = Column(String, ForeignKey("lineage_nodes.id"), nullable=False, index=True)
    derivation_kind = Column(String, nullable=False, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    at = Column(BigInteger, nullable=False, index=True)


class OkugakiRow(Base):
    __tablename__ = "okugaki"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_okugaki_user_idempotency"),)

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    target_node_id = Column(String, ForeignKey("lineage_nodes.id"), nullable=False, index=True)
    branch_snapshot_json = Column(Text, nullable=False, default="[]")
    model = Column(String, nullable=False)
    at = Column(BigInteger, nullable=False, index=True)
    language = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    warnings_json = Column(Text, nullable=False, default="[]")
    fact_sheet_json = Column(Text, nullable=False, default="{}")
    idempotency_key = Column(String, nullable=True)


class UnreadWordRow(Base):
    __tablename__ = "unread_words"
    __table_args__ = (UniqueConstraint("user_id", "word", "context", name="uq_unread_word_context"),)

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    word = Column(String, nullable=False, index=True)
    context = Column(Text, nullable=False, default="")
    frequency = Column(Integer, nullable=False, default=1)
    first_at = Column(BigInteger, nullable=False, index=True)
    last_at = Column(BigInteger, nullable=False, index=True)


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
    ui_theme      = Column(String, nullable=False, default="dark")
    ui_mode       = Column(String, nullable=False, default="simple")
    ui_custom     = Column(Text, nullable=False, default="{}")
    settings_tab  = Column(String, nullable=False, default="db")
    model_settings = Column(Text, nullable=False, default="{}")
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


class ExternalIdentityRow(Base):
    """Provider-neutral identity link; OAuth/OIDC token handling stays outside the DB layer."""

    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_identity_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_external_identity_user_provider"),
    )

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    email = Column(String, nullable=True)
    at = Column(BigInteger, nullable=False, index=True)


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
    "ddl_version": "ALTER TABLE history ADD COLUMN ddl_version VARCHAR",
    "ddl_engine_version": "ALTER TABLE history ADD COLUMN ddl_engine_version VARCHAR",
    "stage1_prompt_digest": "ALTER TABLE history ADD COLUMN stage1_prompt_digest VARCHAR",
    "stage1_prompt_base_digest": "ALTER TABLE history ADD COLUMN stage1_prompt_base_digest VARCHAR",
    "stage2_prompt_digest": "ALTER TABLE history ADD COLUMN stage2_prompt_digest VARCHAR",
    "render_build_number": "ALTER TABLE history ADD COLUMN render_build_number VARCHAR",
    "render_color_profile": "ALTER TABLE history ADD COLUMN render_color_profile TEXT",
    "render_engine_id": "ALTER TABLE history ADD COLUMN render_engine_id VARCHAR",
    "render_engine_version": "ALTER TABLE history ADD COLUMN render_engine_version VARCHAR",
    "render_color_catalog_id": "ALTER TABLE history ADD COLUMN render_color_catalog_id VARCHAR",
    "render_color_catalog_name": "ALTER TABLE history ADD COLUMN render_color_catalog_name VARCHAR",
    "render_color_catalog_sub": "ALTER TABLE history ADD COLUMN render_color_catalog_sub VARCHAR",
    "render_color_catalog": "ALTER TABLE history ADD COLUMN render_color_catalog TEXT",
    "render_color_map": "ALTER TABLE history ADD COLUMN render_color_map TEXT",
    "render_canvas_aspect": "ALTER TABLE history ADD COLUMN render_canvas_aspect VARCHAR",
    "render_canvas_aspect_id": "ALTER TABLE history ADD COLUMN render_canvas_aspect_id VARCHAR",
    "render_canvas_aspect_ratio": "ALTER TABLE history ADD COLUMN render_canvas_aspect_ratio FLOAT",
    "instruction_lang_requested": "ALTER TABLE history ADD COLUMN instruction_lang_requested VARCHAR",
    "instruction_lang_resolved": "ALTER TABLE history ADD COLUMN instruction_lang_resolved VARCHAR",
    "ui_lang": "ALTER TABLE history ADD COLUMN ui_lang VARCHAR",
    "render_seed": "ALTER TABLE history ADD COLUMN render_seed VARCHAR",
    "render_wild": "ALTER TABLE history ADD COLUMN render_wild VARCHAR",
    "composition_seed": "ALTER TABLE history ADD COLUMN composition_seed VARCHAR",
    "tenkei": "ALTER TABLE history ADD COLUMN tenkei VARCHAR",
    "focus": "ALTER TABLE history ADD COLUMN focus VARCHAR",
    "variation_amplitude": "ALTER TABLE history ADD COLUMN variation_amplitude VARCHAR",
    "variation_seed": "ALTER TABLE history ADD COLUMN variation_seed VARCHAR",
    "interpret_fallback": "ALTER TABLE history ADD COLUMN interpret_fallback VARCHAR",
    "expanded_ddl": "ALTER TABLE history ADD COLUMN expanded_ddl TEXT",
    "interpretation_seed": "ALTER TABLE history ADD COLUMN interpretation_seed VARCHAR",
    "seed_text": "ALTER TABLE history ADD COLUMN seed_text TEXT",
    "render_hash": "ALTER TABLE history ADD COLUMN render_hash VARCHAR",
    "trashed": "ALTER TABLE history ADD COLUMN trashed INTEGER NOT NULL DEFAULT 0",
    "starred": "ALTER TABLE history ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
    "note": "ALTER TABLE history ADD COLUMN note TEXT",
    "source_text": "ALTER TABLE history ADD COLUMN source_text TEXT",
    "display_label": "ALTER TABLE history ADD COLUMN display_label VARCHAR",
    "batch_line_number": "ALTER TABLE history ADD COLUMN batch_line_number INTEGER",
    "batch_run_id": "ALTER TABLE history ADD COLUMN batch_run_id VARCHAR",
    "description_hash": "ALTER TABLE history ADD COLUMN description_hash VARCHAR",
    "history_visibility": "ALTER TABLE history ADD COLUMN history_visibility VARCHAR NOT NULL DEFAULT 'normal'",
    "lineage_node_id": "ALTER TABLE history ADD COLUMN lineage_node_id VARCHAR",
    "idempotency_key": "ALTER TABLE history ADD COLUMN idempotency_key VARCHAR",
}
_LINEAGE_NODE_COLUMN_MIGRATIONS = {
    "root_node_id": "ALTER TABLE lineage_nodes ADD COLUMN root_node_id VARCHAR",
}
_USER_ACCOUNT_COLUMN_MIGRATIONS = {
    "ui_theme": "ALTER TABLE user_accounts ADD COLUMN ui_theme VARCHAR NOT NULL DEFAULT 'light'",
    "ui_mode": "ALTER TABLE user_accounts ADD COLUMN ui_mode VARCHAR NOT NULL DEFAULT 'simple'",
    "ui_custom": "ALTER TABLE user_accounts ADD COLUMN ui_custom TEXT NOT NULL DEFAULT '{}'",
    "settings_tab": "ALTER TABLE user_accounts ADD COLUMN settings_tab VARCHAR NOT NULL DEFAULT 'db'",
    "model_settings": "ALTER TABLE user_accounts ADD COLUMN model_settings TEXT NOT NULL DEFAULT '{}'",
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
_SETTINGS_TABS = {"models", "db", "plugins", "users", "export", "misc", "server_misc", "logs"}
_UI_MODES = {"simple", "full", "custom"}
_UI_CUSTOM_KEYS = {
    "input_modes", "drawing_settings", "ddl_tools", "detail_status",
    "work_tools", "history", "auxiliary",
}
_PLUGIN_STORAGE_MAX_BYTES = 20_000
_OUTPUT_SAVE_SETTINGS_KEY = "output_save_settings"
_OUTPUT_SAVE_DEFAULT_SETTINGS = {
    "enabled": True,
    "output_dir": str(Path(os.getenv("INKU_OUTPUT_DIR", str(Path.home() / ".local" / "share" / "inku" / "outputs")))),
    "png_size": int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160")),
}
_RENDER_CONCURRENCY_SETTINGS_KEY = "render_concurrency_settings"
# INKU_RENDER_CONCURRENCY / INKU_CLIENT_FANOUT_LIMIT seed the first value only;
# once stored, the DB row is the source of truth (admin settings screen).
_RENDER_CONCURRENCY_DEFAULT_SETTINGS = {
    "server_limit": int(os.getenv("INKU_RENDER_CONCURRENCY", "2")),
    "client_limit": int(os.getenv("INKU_CLIENT_FANOUT_LIMIT", "4")),
}
RENDER_CONCURRENCY_MIN = 1
RENDER_CONCURRENCY_MAX = 16
_LOG_RETENTION_SETTINGS_KEY = "log_retention_settings"
_LOG_RETENTION_DEFAULT_SETTINGS = {
    "enabled": True,
    "retention_days": int(os.getenv("INKU_LOG_RETENTION_DAYS", "90")),
    "rotate": os.getenv("INKU_LOG_ROTATE", "daily"),
    "compress": True,
}
_DEMO_DEFAULT_SETTINGS = {
    "save_db": False,
    "save_files": False,
    # v2.9.1: the provider is kept beside the model, as every stage does. The
    # picker used to hand over a provider that was thrown away here.
    "prompt_provider": "nvidia",
    "prompt_model": "google/gemma-4-31b-it",
    "seed_phrase": "日本の四季を感じさせる文章を40語以内で生成",
    "interval_seconds": 30,
    "timeout_seconds": 3600,
    "random_color_catalog": False,
}
_EXPORT_TEMPLATE_LIMIT = 20
_EXPORT_TEMPLATE_DEFAULTS = [
    {
        "id": "png-1080",
        "name": "PNG 1080px",
        "description": "PNG / Y軸 1080px",
        "y_px": 1080,
    },
    {
        "id": "png-2160",
        "name": "PNG 2160px",
        "description": "PNG / Y軸 2160px",
        "y_px": 2160,
    },
    {
        "id": "png-4320",
        "name": "PNG 4320px",
        "description": "PNG / Y軸 4320px",
        "y_px": 4320,
    },
]
_DEFAULT_DB_BACKUP_DIR = Path.home() / ".local" / "share" / "inku" / "db-backups"
_DB_BACKUP_DIR = Path(os.getenv("INKU_DB_BACKUP_DIR", str(_DEFAULT_DB_BACKUP_DIR))).expanduser()
_DB_BACKUP_SETTINGS_KEY = "db_backup_settings"
_MODEL_SETTINGS_KEY = "model_connection_settings"
_DB_BACKUP_DEFAULT_SETTINGS = {
    "interval_days": 7,
    "max_generations": 4,
    "backup_hour": 3,
    "backup_minute": 0,
    "last_auto_backup_at": 0,
}
# How many entries the status payload carries. The counts and the total size are
# reported for every file, so a truncated list never hides how much disk is used.
_DB_BACKUP_LIST_LIMIT = 50
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
    ("ix_history_render_hash", "CREATE INDEX IF NOT EXISTS ix_history_render_hash ON history (render_hash)"),
    ("ix_history_user_description_hash", "CREATE INDEX IF NOT EXISTS ix_history_user_description_hash ON history (user_id, description_hash)"),
    ("ix_history_visibility", "CREATE INDEX IF NOT EXISTS ix_history_visibility ON history (history_visibility)"),
    ("ix_history_lineage_node_id", "CREATE UNIQUE INDEX IF NOT EXISTS ix_history_lineage_node_id ON history (lineage_node_id)"),
    (
        "uq_history_user_idempotency",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_history_user_idempotency "
        "ON history (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
    ),
)
_LINEAGE_NODE_INDEX_MIGRATIONS = (
    ("ix_lineage_nodes_root_node_id", "CREATE INDEX IF NOT EXISTS ix_lineage_nodes_root_node_id ON lineage_nodes (root_node_id)"),
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
    _backfill_history_identity_and_lineage()


def _migrate_columns() -> None:
    with engine.begin() as conn:
        try:
            inspector = inspect(conn)
            existing_history_columns = {col["name"] for col in inspector.get_columns("history")}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("failed to inspect history table columns for migration") from exc

        # v2.8.0: 変奏の語を辞書へ揃えた。`vary_seed` は変奏ではなく Stage 1.5 の
        # **構図** seed なので `composition_seed` へ移す。列を足すだけだと既存の値が
        # 孤児になるので、**足す前に中身を移す**。
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
            # v1.98: history.ddl の意味を「入力側」に定義し直したため、既存行が持つ
            # テキスト (Stage 2 に渡った展開後 DDL) を expanded_ddl へ移し、入力側は
            # NULL = 記録なしとする。Stage 1 出力は保存されたことがないので復元できない。
            # DDL から直接作られた少数の作品では原文が expanded_ddl 側に入るが、
            # 作者裁定 (2026-07-20) によりその誤差は許容する。
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

        # v2.8.0: 保存済みの derivation kind を辞書の語へ移す。
        # **`variation` は変奏だけの語である** — 変奏でない 4 種が名乗っていたのを外し、
        # 本物の変奏 (`hensou`) をローマ字から戻した。**行は消さずに書き換える。**
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
        # **鍵名は `vary_seed` のまま凍結する。** これは名前ではなく hash の材料であり、
        # 文字を変えると保存済み作品の rh2 が全部作り直しになる。値は新しい列から取る。
        # (v2.8.0 の改名で実際に全件動いたのを検査が捕まえた)
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
    return render_hash[-4:].upper() if render_hash else None


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


def _ensure_default_user_group() -> None:
    with SessionLocal() as session:
        exists = session.query(UserGroupRow).first()
        if exists:
            return
        session.add(UserGroupRow(id=str(uuid.uuid4()), name="default", at=_now_ms()))
        session.commit()


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


def _backfill_history_identity_and_lineage() -> None:
    with SessionLocal() as session:
        rows = session.query(HistoryRow).filter(
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
                node = session.get(LineageNodeRow, row.lineage_node_id)
            if node is None:
                node = session.query(LineageNodeRow).filter(LineageNodeRow.history_id == row.id).first()
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
                session.add(node)
                changed = True
            if node is not None and row.lineage_node_id != node.id:
                row.lineage_node_id = node.id
                changed = True
        session.flush()
        nodes = session.query(LineageNodeRow).all()
        parent_by_child = {edge.child_node_id: edge.parent_node_id for edge in session.query(LineageEdgeRow).all()}
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
            session.commit()


def _lineage_edge_to_dict(row: LineageEdgeRow) -> dict:
    try:
        metadata = json.loads(row.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {
        "id": row.id,
        "parent_node_id": row.parent_node_id,
        "child_node_id": row.child_node_id,
        "derivation_kind": row.derivation_kind,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "at": row.at,
    }


def _ancestor_edge_ids(session, user_id: str, focus_node_id: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    return list(session.execute(
        text(
            """
            WITH RECURSIVE ancestor_edges(id, parent_node_id, child_node_id) AS (
                SELECT id, parent_node_id, child_node_id
                FROM lineage_edges
                WHERE user_id = :user_id AND child_node_id = :focus_node_id
                UNION
                SELECT edge.id, edge.parent_node_id, edge.child_node_id
                FROM lineage_edges edge
                JOIN ancestor_edges ancestor
                  ON edge.child_node_id = ancestor.parent_node_id
                WHERE edge.user_id = :user_id
            )
            SELECT id FROM ancestor_edges LIMIT :limit
            """
        ),
        {"user_id": user_id, "focus_node_id": focus_node_id, "limit": limit},
    ).scalars())


def _descendant_edge_ids(
    session,
    user_id: str,
    focus_node_id: str,
    depth: int,
    limit: int,
) -> list[str]:
    if depth <= 0 or limit <= 0:
        return []
    return list(session.execute(
        text(
            """
            WITH RECURSIVE descendant_edges(id, parent_node_id, child_node_id, depth) AS (
                SELECT id, parent_node_id, child_node_id, 1
                FROM lineage_edges
                WHERE user_id = :user_id AND parent_node_id = :focus_node_id
                UNION ALL
                SELECT edge.id, edge.parent_node_id, edge.child_node_id, descendant.depth + 1
                FROM lineage_edges edge
                JOIN descendant_edges descendant
                  ON edge.parent_node_id = descendant.child_node_id
                WHERE edge.user_id = :user_id AND descendant.depth < :depth
            )
            SELECT id
            FROM descendant_edges
            ORDER BY depth ASC, id ASC
            LIMIT :limit
            """
        ),
        {
            "user_id": user_id,
            "focus_node_id": focus_node_id,
            "depth": depth,
            "limit": limit,
        },
    ).scalars())


def tenkei_for_node(user_id: str, node_id: str) -> str | None:
    """派生元 lineage ノードの作品に記録された添景水準を返す (v1.97 継承)。

    未記録 (保存開始前の作品・renderer 専用派生の欠損) は None。呼び出し側が
    既定 "auto" へ落とす。
    """
    with SessionLocal() as session:
        node = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == node_id,
            LineageNodeRow.user_id == user_id,
        ).first()
        if node is None or not node.history_id:
            return None
        row = session.query(HistoryRow).filter(
            HistoryRow.id == node.history_id,
            HistoryRow.user_id == user_id,
        ).first()
        if row is None:
            return None
        return row.tenkei


def _lineage_generations(session, user_id: str, node_ids: list[str]) -> dict[str, int]:
    """世代 (root=1, 主親エッジを辿って +1) をノード集合分まとめて計算する。

    履歴リスト側 (_rows_to_dicts_with_lineage) と同じ意味論。lineage_generation は
    DB カラムではなく計算値のため、lineage 応答へ載せる際もここを単一の真実源とする。
    """
    memo: dict[str, int] = {}

    def resolve(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        chain: list[str] = []
        seen: set[str] = set()
        current = node_id
        while current not in memo:
            if current in seen:
                break  # cycle guard: treat the repeated node as a root
            seen.add(current)
            chain.append(current)
            edge = session.query(LineageEdgeRow).filter(
                LineageEdgeRow.user_id == user_id,
                LineageEdgeRow.child_node_id == current,
            ).first()
            if edge is None:
                break
            current = edge.parent_node_id
        base = memo.get(current, 0)
        for offset, nid in enumerate(reversed(chain), start=1):
            memo[nid] = base + offset
        return memo[node_id]

    for node_id in node_ids:
        resolve(node_id)
    return memo


def get_lineage(user_id: str, focus_node_id: str, descendant_depth: int = 2, node_limit: int = 200) -> dict | None:
    descendant_depth = max(0, min(descendant_depth, 200))
    node_limit = max(1, min(node_limit, 200))
    with SessionLocal() as session:
        focus = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == focus_node_id,
            LineageNodeRow.user_id == user_id,
        ).first()
        if focus is None:
            return None

        ancestor_ids = _ancestor_edge_ids(session, user_id, focus.id, node_limit - 1)
        remaining = max(0, node_limit - 1 - len(ancestor_ids))
        descendant_ids = _descendant_edge_ids(
            session,
            user_id,
            focus.id,
            descendant_depth,
            remaining,
        )
        selected_edge_ids = list(dict.fromkeys([*ancestor_ids, *descendant_ids]))
        selected_edges = (
            session.query(LineageEdgeRow)
            .filter(
                LineageEdgeRow.user_id == user_id,
                LineageEdgeRow.id.in_(selected_edge_ids),
            )
            .all()
            if selected_edge_ids
            else []
        )
        edges = {edge.id: edge for edge in selected_edges}
        node_ids = {focus.id}
        for edge in selected_edges:
            node_ids.add(edge.parent_node_id)
            node_ids.add(edge.child_node_id)

        nodes = session.query(LineageNodeRow).filter(
            LineageNodeRow.user_id == user_id,
            LineageNodeRow.id.in_(node_ids),
        ).all()
        history_ids = [node.history_id for node in nodes if node.history_id]
        history_by_id = {
            row.id: row
            for row in session.query(HistoryRow).filter(
                HistoryRow.user_id == user_id,
                HistoryRow.id.in_(history_ids),
            ).all()
        }
        child_counts = dict(
            session.query(LineageEdgeRow.parent_node_id, func.count(LineageEdgeRow.id))
            .filter(
                LineageEdgeRow.user_id == user_id,
                LineageEdgeRow.parent_node_id.in_(node_ids),
            )
            .group_by(LineageEdgeRow.parent_node_id)
            .all()
        )
        generations = _lineage_generations(session, user_id, [node.id for node in nodes])
        node_payloads = []
        for node in nodes:
            payload = {
                "id": node.id,
                "state": node.state,
                "at": node.at,
                "deleted_at": node.deleted_at,
                "child_count": int(child_counts.get(node.id, 0)),
            }
            if node.state != "tombstone":
                payload["description_hash"] = node.description_hash
                payload["render_hash"] = node.render_hash
                history = history_by_id.get(node.history_id or "")
                if history is not None:
                    payload["history"] = _row_to_dict(history)
                    payload["history"]["lineage_generation"] = generations.get(node.id)
            node_payloads.append(payload)
        return {
            "focus_node_id": focus.id,
            "nodes": sorted(node_payloads, key=lambda item: (item["at"], item["id"])),
            "edges": [_lineage_edge_to_dict(edge) for edge in sorted(edges.values(), key=lambda item: (item.at, item.id))],
        }


def promote_lineage_node(user_id: str, node_id: str) -> dict | None:
    with SessionLocal() as session:
        node = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == node_id,
            LineageNodeRow.user_id == user_id,
            LineageNodeRow.state == "lineage_only",
        ).first()
        if node is None or not node.history_id:
            return None
        row = session.query(HistoryRow).filter(
            HistoryRow.id == node.history_id,
            HistoryRow.user_id == user_id,
        ).first()
        if row is None:
            return None
        node.state = "active"
        row.history_visibility = "normal"
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def get_lineage_branch(user_id: str, target_node_id: str) -> dict | None:
    """Return the single primary-parent path from root through target."""
    with SessionLocal() as session:
        target = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == target_node_id,
            LineageNodeRow.user_id == user_id,
        ).first()
        if target is None:
            return None
        reversed_nodes = [target]
        reversed_edges: list[LineageEdgeRow] = []
        seen = {target.id}
        current = target
        while True:
            edge = session.query(LineageEdgeRow).filter(
                LineageEdgeRow.user_id == user_id,
                LineageEdgeRow.child_node_id == current.id,
            ).first()
            if edge is None or edge.parent_node_id in seen:
                break
            parent = session.query(LineageNodeRow).filter(
                LineageNodeRow.user_id == user_id,
                LineageNodeRow.id == edge.parent_node_id,
            ).first()
            if parent is None:
                break
            reversed_edges.append(edge)
            reversed_nodes.append(parent)
            seen.add(parent.id)
            current = parent
        nodes = list(reversed(reversed_nodes))
        edges = list(reversed(reversed_edges))
        history_ids = [node.history_id for node in nodes if node.history_id]
        histories = {
            row.id: row
            for row in session.query(HistoryRow).filter(
                HistoryRow.user_id == user_id,
                HistoryRow.id.in_(history_ids),
            ).all()
        } if history_ids else {}
        child_counts = dict(
            session.query(LineageEdgeRow.parent_node_id, func.count(LineageEdgeRow.id))
            .filter(
                LineageEdgeRow.user_id == user_id,
                LineageEdgeRow.parent_node_id.in_([node.id for node in nodes]),
            )
            .group_by(LineageEdgeRow.parent_node_id)
            .all()
        )
        generations = _lineage_generations(session, user_id, [node.id for node in nodes])
        payload_nodes = []
        for node in nodes:
            payload = {
                "id": node.id,
                "state": node.state,
                "at": node.at,
                "deleted_at": node.deleted_at,
                "child_count": int(child_counts.get(node.id, 0)),
            }
            history = histories.get(node.history_id or "")
            if node.state != "tombstone" and history is not None:
                payload["history"] = _row_to_dict(history)
                payload["history"]["lineage_generation"] = generations.get(node.id)
            payload_nodes.append(payload)
        return {
            "target_node_id": target.id,
            "nodes": payload_nodes,
            "edges": [_lineage_edge_to_dict(edge) for edge in edges],
        }


def _okugaki_to_dict(row: OkugakiRow) -> dict:
    def load(value: str, fallback):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    return {
        "id": row.id,
        "target_node_id": row.target_node_id,
        "branch_snapshot": load(row.branch_snapshot_json, []),
        "model": row.model,
        "at": row.at,
        "language": row.language,
        "body": row.body,
        "warnings": load(row.warnings_json, []),
        "fact_sheet": load(row.fact_sheet_json, {}),
    }


def add_okugaki(user_id: str, item: dict, *, idempotency_key: str | None = None) -> dict:
    with SessionLocal() as session:
        if idempotency_key:
            existing = session.query(OkugakiRow).filter(
                OkugakiRow.user_id == user_id,
                OkugakiRow.idempotency_key == idempotency_key,
            ).first()
            if existing is not None:
                result = _okugaki_to_dict(existing)
                result["_idempotent_replay"] = True
                return result
        target = session.query(LineageNodeRow).filter(
            LineageNodeRow.user_id == user_id,
            LineageNodeRow.id == item["target_node_id"],
        ).first()
        if target is None:
            raise ValueError("lineage target not found")
        row = OkugakiRow(
            id=item.get("id") or str(uuid.uuid4()),
            user_id=user_id,
            target_node_id=item["target_node_id"],
            branch_snapshot_json=_canonical_json(item["branch_snapshot"]),
            model=item["model"],
            at=item["at"],
            language=item["language"],
            body=item["body"],
            warnings_json=_canonical_json(item.get("warnings") or []),
            fact_sheet_json=_canonical_json(item.get("fact_sheet") or {}),
            idempotency_key=idempotency_key,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if not idempotency_key:
                raise
            existing = session.query(OkugakiRow).filter(
                OkugakiRow.user_id == user_id,
                OkugakiRow.idempotency_key == idempotency_key,
            ).first()
            if existing is None:
                raise
            result = _okugaki_to_dict(existing)
            result["_idempotent_replay"] = True
            return result
        session.refresh(row)
        return _okugaki_to_dict(row)


def list_okugaki(user_id: str, target_node_id: str) -> list[dict]:
    with SessionLocal() as session:
        rows = session.query(OkugakiRow).filter(
            OkugakiRow.user_id == user_id,
            OkugakiRow.target_node_id == target_node_id,
        ).order_by(OkugakiRow.at.asc(), OkugakiRow.id.asc()).all()
        return [_okugaki_to_dict(row) for row in rows]


def get_okugaki_by_idempotency(user_id: str, idempotency_key: str) -> dict | None:
    with SessionLocal() as session:
        row = session.query(OkugakiRow).filter(
            OkugakiRow.user_id == user_id,
            OkugakiRow.idempotency_key == idempotency_key,
        ).first()
        return _okugaki_to_dict(row) if row is not None else None


def delete_okugaki(user_id: str, okugaki_id: str) -> bool:
    with SessionLocal() as session:
        row = session.query(OkugakiRow).filter(
            OkugakiRow.id == okugaki_id,
            OkugakiRow.user_id == user_id,
        ).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True



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
    for key, limit in (("backup_hour", 23), ("backup_minute", 59)):
        if key not in settings:
            continue
        try:
            value = int(settings[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"backup {key} must be an integer") from exc
        if value < 0 or value > limit:
            raise ValueError(f"backup {key} must be between 0 and {limit}")
        clean[key] = value
    if "last_auto_backup_at" in settings:
        try:
            clean["last_auto_backup_at"] = max(0, int(settings["last_auto_backup_at"]))
        except (TypeError, ValueError):
            clean["last_auto_backup_at"] = 0
    return clean


def get_db_backup_settings() -> dict:
    return _normalize_db_backup_settings(_read_app_setting(_DB_BACKUP_SETTINGS_KEY))


def update_db_backup_settings(
    interval_days: int,
    max_generations: int,
    backup_hour: int | None = None,
    backup_minute: int | None = None,
) -> dict:
    current = get_db_backup_settings()
    current["interval_days"] = interval_days
    current["max_generations"] = max_generations
    if backup_hour is not None:
        current["backup_hour"] = backup_hour
    if backup_minute is not None:
        current["backup_minute"] = backup_minute
    clean = _normalize_db_backup_settings(current)
    return _write_app_setting(_DB_BACKUP_SETTINGS_KEY, clean)


def _normalize_output_save_settings(settings: dict | None) -> dict:
    clean = dict(_OUTPUT_SAVE_DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return clean
    if "enabled" in settings:
        clean["enabled"] = bool(settings["enabled"])
    if "output_dir" in settings:
        raw_path = str(settings["output_dir"] or "").strip()
        if not raw_path:
            raise ValueError("output directory must not be empty")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValueError("output directory must be an absolute path")
        clean["output_dir"] = str(path)
    if "png_size" in settings:
        try:
            png_size = int(settings["png_size"])
        except (TypeError, ValueError) as exc:
            raise ValueError("PNG size must be 1080 or 2160") from exc
        if png_size not in {1080, 2160}:
            raise ValueError("PNG size must be 1080 or 2160")
        clean["png_size"] = png_size
    return clean


def _normalize_render_concurrency_settings(settings: dict | None) -> dict:
    clean = dict(_RENDER_CONCURRENCY_DEFAULT_SETTINGS)
    for key in ("server_limit", "client_limit"):
        clean[key] = _clamped_concurrency(clean[key], key)
    if not isinstance(settings, dict):
        return clean
    for key in ("server_limit", "client_limit"):
        if key in settings:
            clean[key] = _clamped_concurrency(settings[key], key)
    return clean


def _clamped_concurrency(value: object, key: str) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if number < RENDER_CONCURRENCY_MIN or number > RENDER_CONCURRENCY_MAX:
        raise ValueError(f"{key} must be between {RENDER_CONCURRENCY_MIN} and {RENDER_CONCURRENCY_MAX}")
    return number


def get_render_concurrency_settings() -> dict:
    return _normalize_render_concurrency_settings(_read_app_setting(_RENDER_CONCURRENCY_SETTINGS_KEY))


def update_render_concurrency_settings(server_limit: int, client_limit: int) -> dict:
    clean = _normalize_render_concurrency_settings({"server_limit": server_limit, "client_limit": client_limit})
    return _write_app_setting(_RENDER_CONCURRENCY_SETTINGS_KEY, clean)


def get_output_save_settings() -> dict:
    return _normalize_output_save_settings(_read_app_setting(_OUTPUT_SAVE_SETTINGS_KEY))


def update_output_save_settings(enabled: bool, output_dir: str, png_size: int) -> dict:
    clean = _normalize_output_save_settings({"enabled": enabled, "output_dir": output_dir, "png_size": png_size})
    return _write_app_setting(_OUTPUT_SAVE_SETTINGS_KEY, clean)


def _normalize_log_retention_settings(settings: dict | None) -> dict:
    clean = dict(_LOG_RETENTION_DEFAULT_SETTINGS)
    if clean["rotate"] not in {"daily", "weekly", "monthly"}:
        clean["rotate"] = "daily"
    if clean["retention_days"] < 1:
        clean["retention_days"] = 90
    if not isinstance(settings, dict):
        return clean
    if "enabled" in settings:
        clean["enabled"] = bool(settings["enabled"])
    if "retention_days" in settings:
        try:
            retention_days = int(settings["retention_days"])
        except (TypeError, ValueError) as exc:
            raise ValueError("log retention days must be an integer") from exc
        if retention_days < 1 or retention_days > 3650:
            raise ValueError("log retention days must be between 1 and 3650")
        clean["retention_days"] = retention_days
    if "rotate" in settings:
        rotate = str(settings["rotate"] or "").strip().lower()
        if rotate not in {"daily", "weekly", "monthly"}:
            raise ValueError("log rotate must be daily, weekly, or monthly")
        clean["rotate"] = rotate
    if "compress" in settings:
        clean["compress"] = bool(settings["compress"])
    return clean


def get_log_retention_settings() -> dict:
    return _normalize_log_retention_settings(_read_app_setting(_LOG_RETENTION_SETTINGS_KEY))


def update_log_retention_settings(enabled: bool, retention_days: int, rotate: str, compress: bool) -> dict:
    clean = _normalize_log_retention_settings(
        {"enabled": enabled, "retention_days": retention_days, "rotate": rotate, "compress": compress}
    )
    return _write_app_setting(_LOG_RETENTION_SETTINGS_KEY, clean)


def get_model_settings() -> dict:
    from .model_settings import normalize_model_settings

    return normalize_model_settings(_read_app_setting(_MODEL_SETTINGS_KEY))


def update_model_settings(settings: dict) -> dict:
    from .model_settings import normalize_model_settings, storage_model_settings

    stored = storage_model_settings(settings)
    _write_app_setting(_MODEL_SETTINGS_KEY, stored)
    return normalize_model_settings(stored)


_AUTH_SETTINGS_KEY = "auth_settings"
_AUTH_DEFAULT_SETTINGS = {
    "google_enabled": False,
    "local_enabled": True,
}


def _normalize_auth_settings(settings: dict | None) -> dict:
    clean = dict(_AUTH_DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return clean
    if "google_enabled" in settings:
        clean["google_enabled"] = bool(settings["google_enabled"])
    if "local_enabled" in settings:
        clean["local_enabled"] = bool(settings["local_enabled"])
    return clean


def get_auth_settings() -> dict:
    env_google = os.getenv("INKU_AUTH_GOOGLE_ENABLED", "false").lower() in ("true", "1", "yes")
    env_local = os.getenv("INKU_AUTH_LOCAL_ENABLED", "true").lower() in ("true", "1", "yes")

    defaults = {
        "google_enabled": env_google,
        "local_enabled": env_local
    }

    stored = _read_app_setting(_AUTH_SETTINGS_KEY)
    if stored is None:
        return defaults

    merged = dict(defaults)
    if "google_enabled" in stored:
        merged["google_enabled"] = bool(stored["google_enabled"])
    if "local_enabled" in stored:
        merged["local_enabled"] = bool(stored["local_enabled"])
    return merged


def update_auth_settings(google_enabled: bool, local_enabled: bool) -> dict:
    clean = {
        "google_enabled": bool(google_enabled),
        "local_enabled": bool(local_enabled),
    }
    return _write_app_setting(_AUTH_SETTINGS_KEY, clean)


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


def next_scheduled_db_backup_at(settings: dict | None = None) -> int:
    """Wall-clock instant the next automatic backup is due, in ms.

    The interval picks the day and the configured time picks the moment within
    it, so a copy taken late in the evening does not drag every later one along
    with it. 0 means "no automatic backup has ever run", which is due at once.
    """
    settings = settings or get_db_backup_settings()
    last_at = int(settings.get("last_auto_backup_at") or 0)
    if last_at <= 0:
        return 0
    due_date = (datetime.fromtimestamp(last_at / 1000) + timedelta(days=int(settings["interval_days"]))).date()
    due = datetime.combine(due_date, clock_time(hour=int(settings["backup_hour"]), minute=int(settings["backup_minute"])))
    return int(due.timestamp() * 1000)


def ensure_scheduled_db_backup() -> dict | None:
    settings = get_db_backup_settings()
    due_at = next_scheduled_db_backup_at(settings)
    if due_at > 0 and _now_ms() < due_at:
        return None
    try:
        return create_db_backup(manual=False)
    except ValueError:
        return None


def list_db_backups(limit: int = _DB_BACKUP_LIST_LIMIT) -> dict:
    """Every retained copy, newest first, with the generation the prune counts by."""
    entries: list[dict] = []
    total_size = 0
    for kind in ("auto", "manual"):
        directory = _DB_BACKUP_DIR / kind
        if not directory.exists():
            continue
        for path in directory.glob(f"inku-{kind}-*.db"):
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append({
                "kind": kind,
                "name": path.name,
                "at": int(stat.st_mtime * 1000),
                "size_bytes": stat.st_size,
            })
            total_size += stat.st_size
    entries.sort(key=lambda entry: entry["at"], reverse=True)
    # Generation 1 is the newest automatic copy, matching the order
    # _prune_auto_backups walks: the highest number is the one dropped next.
    # Manual copies are never pruned, so they are outside the numbering.
    generation = 0
    for entry in entries:
        if entry["kind"] == "auto":
            generation += 1
            entry["generation"] = generation
        else:
            entry["generation"] = None
    return {
        "entries": entries[:limit],
        "total_count": len(entries),
        "total_size_bytes": total_size,
    }


def db_backup_status() -> dict:
    settings = get_db_backup_settings()
    supported = engine.dialect.name == "sqlite" and _sqlite_db_path() is not None
    auto_dir = _DB_BACKUP_DIR / "auto"
    manual_dir = _DB_BACKUP_DIR / "manual"
    auto_count = len(list(auto_dir.glob("inku-auto-*.db"))) if auto_dir.exists() else 0
    manual_count = len(list(manual_dir.glob("inku-manual-*.db"))) if manual_dir.exists() else 0
    listing = list_db_backups()
    return {
        **settings,
        "supported": supported,
        "backup_dir": str(_DB_BACKUP_DIR),
        "auto_count": auto_count,
        "manual_count": manual_count,
        "next_auto_backup_at": next_scheduled_db_backup_at(settings),
        "backups": listing["entries"],
        "backups_total_count": listing["total_count"],
        "backups_total_size_bytes": listing["total_size_bytes"],
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
    data_warnings: list[str] = []
    try:
        score = json.loads(row.score) if row.score else {}
    except (json.JSONDecodeError, TypeError):
        score = {}
        data_warnings.append("score_json_invalid")
        _logger.error("history score JSON is corrupt: history_id=%s", row.id)
    if not isinstance(score, dict):
        score = {}
        data_warnings.append("score_json_not_object")
        _logger.error("history score JSON is not an object: history_id=%s", row.id)
    item = {
        "id":           row.id,
        "user_id":      row.user_id,
        "at":           row.at,
        "input":        row.input,
        "ddl":          row.ddl,
        "expanded_ddl": row.expanded_ddl,
        "score":        score,
        "svg":          row.svg,
        "output_path":  row.output_path,
        "elapsed_ms":   row.elapsed_ms,
        "stage1_model": row.stage1_model,
        "stage2_model": row.stage2_model,
        "tokens_in":    row.tokens_in,
        "tokens_out":   row.tokens_out,
        "catalog_id":   row.catalog_id,
        "render_hash":  row.render_hash,
        "render_hash_short": render_hash_short(row.render_hash),
        "trashed":      bool(row.trashed),
        "starred":      bool(row.starred),
    "note":         row.note,
    "source_text": row.source_text if row.source_text is not None else row.input,
    "display_label": row.display_label,
    "batch_line_number": row.batch_line_number,
    "batch_run_id": row.batch_run_id,
    "description_hash": row.description_hash,
    "history_visibility": row.history_visibility or "normal",
    "lineage_node_id": row.lineage_node_id,
}
    if data_warnings:
        item["data_warnings"] = data_warnings
    if row.stage1_prompt_digest is not None:
        item["stage1_prompt_digest"] = row.stage1_prompt_digest
    if row.stage1_prompt_base_digest is not None:
        item["stage1_prompt_base_digest"] = row.stage1_prompt_base_digest
    if row.stage2_prompt_digest is not None:
        item["stage2_prompt_digest"] = row.stage2_prompt_digest
    if row.ddl_version is not None:
        item["ddl_version"] = row.ddl_version
    if row.ddl_engine_version is not None:
        item["ddl_engine_version"] = row.ddl_engine_version
    if row.render_build_number is not None:
        item["render_build_number"] = row.render_build_number
    if row.render_color_profile is not None:
        try:
            item["render_color_profile"] = json.loads(row.render_color_profile)
        except json.JSONDecodeError:
            item["render_color_profile"] = None
    if row.render_engine_id is not None:
        item["render_engine_id"] = row.render_engine_id
    if row.render_engine_version is not None:
        item["render_engine_version"] = row.render_engine_version
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
    if row.render_canvas_aspect is not None:
        item["render_canvas_aspect"] = row.render_canvas_aspect
    canvas_aspect_id = row.render_canvas_aspect_id or row.render_canvas_aspect
    if canvas_aspect_id is not None:
        normalized_canvas_aspect_id = normalize_canvas_aspect_id(canvas_aspect_id)
        item["render_canvas_aspect_id"] = normalized_canvas_aspect_id
        item.setdefault("render_canvas_aspect", normalized_canvas_aspect_id)
        item["render_canvas_aspect_ratio"] = (
            row.render_canvas_aspect_ratio
            if row.render_canvas_aspect_ratio is not None
            else canvas_aspect_ratio_for_aspect(normalized_canvas_aspect_id)
        )
    if row.instruction_lang_requested is not None:
        item["instruction_lang_requested"] = row.instruction_lang_requested
    if row.instruction_lang_resolved is not None:
        item["instruction_lang_resolved"] = row.instruction_lang_resolved
    if row.ui_lang is not None:
        item["ui_lang"] = row.ui_lang
    if row.render_seed is not None:
        try:
            item["render_seed"] = int(row.render_seed)
        except ValueError:
            item["render_seed"] = row.render_seed
    if row.render_wild is not None:
        item["render_wild"] = row.render_wild == "1"
    if row.composition_seed is not None:
        try:
            item["composition_seed"] = int(row.composition_seed)
        except ValueError:
            item["composition_seed"] = row.composition_seed
    if row.tenkei is not None:
        item["tenkei"] = row.tenkei
    if row.focus is not None:
        item["focus"] = row.focus
    if row.variation_amplitude is not None:
        item["variation_amplitude"] = row.variation_amplitude
    if row.variation_seed is not None:
        item["variation_seed"] = row.variation_seed
    if row.interpret_fallback is not None:
        item["interpret_fallback"] = row.interpret_fallback
    if row.interpretation_seed is not None:
        item["interpretation_seed"] = row.interpretation_seed
    if row.seed_text is not None:
        item["seed_text"] = row.seed_text
    return item


def _rows_to_dicts_with_lineage(session, rows: list[HistoryRow]) -> list[dict]:
    """Attach edge provenance while keeping lineage_edges as the source of truth."""
    items = [_row_to_dict(row) for row in rows]
    node_ids = [row.lineage_node_id for row in rows if row.lineage_node_id]
    if not node_ids:
        return items
    nodes = session.query(LineageNodeRow).filter(LineageNodeRow.id.in_(node_ids)).all()
    node_by_id = {node.id: node for node in nodes}
    user_ids = {row.user_id for row in rows}
    edges = session.query(LineageEdgeRow).filter(
        LineageEdgeRow.user_id.in_(user_ids),
        LineageEdgeRow.child_node_id.in_(node_ids),
    ).all()
    edge_by_child = {edge.child_node_id: edge for edge in edges}
    generation_by_node = {node_id: 1 for node_id in node_ids}
    ancestor_by_target = {node_id: node_id for node_id in node_ids}
    seen_by_target = {node_id: {node_id} for node_id in node_ids}
    frontier = set(node_ids)
    while frontier:
        ancestor_edges = session.query(LineageEdgeRow).filter(
            LineageEdgeRow.user_id.in_(user_ids),
            LineageEdgeRow.child_node_id.in_(frontier),
        ).all()
        parent_by_child = {edge.child_node_id: edge.parent_node_id for edge in ancestor_edges}
        next_frontier: set[str] = set()
        for target_id, ancestor_id in ancestor_by_target.items():
            parent_id = parent_by_child.get(ancestor_id)
            if parent_id is None or parent_id in seen_by_target[target_id]:
                continue
            seen_by_target[target_id].add(parent_id)
            ancestor_by_target[target_id] = parent_id
            generation_by_node[target_id] += 1
            next_frontier.add(parent_id)
        frontier = next_frontier

    for row, item in zip(rows, items, strict=True):
        node = node_by_id.get(row.lineage_node_id)
        if node is not None and node.user_id == row.user_id:
            item["lineage_root_node_id"] = node.root_node_id or node.id
            item["lineage_generation"] = generation_by_node[node.id]
            item["lineage_state"] = node.state
        edge = edge_by_child.get(row.lineage_node_id)
        if edge is None or edge.user_id != row.user_id:
            continue
        item["lineage_parent_node_id"] = edge.parent_node_id
        item["derivation_kind"] = edge.derivation_kind
        item["derivation_metadata"] = _lineage_edge_to_dict(edge)["metadata"]
    return items


def _group_to_dict(row: UserGroupRow) -> dict:
    return {"id": row.id, "name": row.name, "at": row.at}


def _user_to_dict(row: UserAccountRow, group_name: str | None = None) -> dict:
    from .model_settings import normalize_user_model_settings

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
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "role": row.role,
        "role_label": ROLE_LABELS.get(row.role, row.role),
        "group_id": row.group_id,
        "group_name": group_name,
        "ui_theme": row.ui_theme if row.ui_theme in {"light", "dark"} else "light",
        "ui_mode": row.ui_mode if row.ui_mode in _UI_MODES else "simple",
        "ui_custom": ui_custom,
        "settings_tab": row.settings_tab if row.settings_tab in _SETTINGS_TABS else "db",
        "model_settings": normalize_user_model_settings(model_settings),
        "image_generation_count": row.image_generation_count or 0,
        "at": row.at,
    }


def add_item(item: dict) -> dict:
    canvas_aspect_id = item.get("render_canvas_aspect_id") or item.get("render_canvas_aspect")
    if canvas_aspect_id is not None:
        canvas_aspect_id = normalize_canvas_aspect_id(canvas_aspect_id)
        item.setdefault("render_canvas_aspect", canvas_aspect_id)
        item["render_canvas_aspect_id"] = canvas_aspect_id
        item.setdefault("render_canvas_aspect_ratio", canvas_aspect_ratio_for_aspect(canvas_aspect_id))
    render_hash = render_hash_for_item(item)
    source_text = item.get("source_text")
    if source_text is None:
        source_text = item.get("input", "")
    desc_hash = description_hash(source_text)
    visibility = item.get("history_visibility") or "normal"
    if visibility not in {"normal", "lineage_only"}:
        raise ValueError("invalid history visibility")
    parent_node_id = item.get("lineage_parent_node_id")
    derivation_kind = item.get("derivation_kind")
    derivation_metadata = item.get("derivation_metadata") or {}
    if parent_node_id and derivation_kind not in LINEAGE_DERIVATION_KINDS:
        raise ValueError("invalid lineage derivation kind")
    if not parent_node_id and derivation_kind:
        raise ValueError("lineage parent is required for a derivation")
    if not isinstance(derivation_metadata, dict):
        raise ValueError("lineage derivation metadata must be an object")

    node_id = str(uuid.uuid4())
    row = HistoryRow(
        id=item["id"], user_id=item["user_id"], at=item["at"], input=item.get("input", ""),
        ddl=item.get("ddl"), expanded_ddl=item.get("expanded_ddl"),
        score=json.dumps(item.get("score", {})), svg=item.get("svg", ""),
        output_path=item.get("output_path"), elapsed_ms=item.get("elapsed_ms", 0),
        stage1_model=item.get("stage1_model"), stage2_model=item.get("stage2_model"),
        stage1_prompt_digest=item.get("stage1_prompt_digest"),
        stage1_prompt_base_digest=item.get("stage1_prompt_base_digest"),
        stage2_prompt_digest=item.get("stage2_prompt_digest"),
        tokens_in=item.get("tokens_in"), tokens_out=item.get("tokens_out"), catalog_id=item.get("catalog_id"),
        ddl_version=item.get("ddl_version"), ddl_engine_version=item.get("ddl_engine_version"),
        render_build_number=item.get("render_build_number"),
        render_color_profile=json.dumps(item.get("render_color_profile"), ensure_ascii=False) if item.get("render_color_profile") is not None else None,
        render_engine_id=item.get("render_engine_id"), render_engine_version=item.get("render_engine_version"),
        render_color_catalog_id=item.get("render_color_catalog_id"),
        render_color_catalog_name=item.get("render_color_catalog_name"),
        render_color_catalog_sub=item.get("render_color_catalog_sub"),
        render_color_map=json.dumps(item.get("render_color_map"), ensure_ascii=False) if item.get("render_color_map") is not None else None,
        render_canvas_aspect=item.get("render_canvas_aspect"),
        render_canvas_aspect_id=item.get("render_canvas_aspect_id") or item.get("render_canvas_aspect"),
        render_canvas_aspect_ratio=item.get("render_canvas_aspect_ratio"),
        instruction_lang_requested=item.get("instruction_lang_requested"),
        instruction_lang_resolved=item.get("instruction_lang_resolved"), ui_lang=item.get("ui_lang"),
        render_seed=str(item.get("render_seed")) if item.get("render_seed") is not None else None,
        render_wild=("1" if item.get("render_wild") else "0") if item.get("render_wild") is not None else None,
        composition_seed=str(item.get("composition_seed")) if item.get("composition_seed") is not None else None,
        tenkei=item.get("tenkei"), focus=item.get("focus"),
        variation_amplitude=item.get("variation_amplitude"),
        variation_seed=str(item.get("variation_seed")) if item.get("variation_seed") is not None else None,
        interpret_fallback=item.get("interpret_fallback"),
        interpretation_seed=str(item.get("interpretation_seed")) if item.get("interpretation_seed") is not None else None,
        seed_text=item.get("seed_text"),
        render_hash=render_hash, trashed=0, starred=0, note=item.get("note"),
        source_text=source_text, display_label=item.get("display_label"),
        batch_line_number=item.get("batch_line_number"), batch_run_id=item.get("batch_run_id"),
        description_hash=desc_hash, history_visibility=visibility, lineage_node_id=node_id,
    )
    node = LineageNodeRow(
        id=node_id, user_id=item["user_id"], history_id=item["id"],
        state="lineage_only" if visibility == "lineage_only" else "active",
        description_hash=desc_hash, render_hash=render_hash, at=item["at"],
        root_node_id=node_id,
    )
    with SessionLocal() as session:
        idempotency_key = item.get("idempotency_key")
        if idempotency_key:
            existing = session.query(HistoryRow).filter(
                HistoryRow.user_id == item["user_id"],
                HistoryRow.idempotency_key == idempotency_key,
            ).first()
            if existing is not None:
                result = _row_to_dict(existing)
                result["_idempotent_replay"] = True
                return result
        if parent_node_id:
            parent = session.query(LineageNodeRow).filter(
                LineageNodeRow.id == parent_node_id,
                LineageNodeRow.user_id == item["user_id"],
                LineageNodeRow.state != "tombstone",
            ).first()
            if parent is None:
                raise ValueError("lineage parent not found")
            node.root_node_id = parent.root_node_id or parent.id
        row.idempotency_key = idempotency_key
        session.add(row)
        session.add(node)
        # SQLite foreign-key enforcement requires the new child node to exist
        # before its edge is inserted. Both writes remain in one transaction.
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            if not idempotency_key:
                raise
            existing = session.query(HistoryRow).filter(
                HistoryRow.user_id == item["user_id"],
                HistoryRow.idempotency_key == idempotency_key,
            ).first()
            if existing is None:
                raise
            result = _row_to_dict(existing)
            result["_idempotent_replay"] = True
            return result
        if parent_node_id:
            session.add(LineageEdgeRow(
                id=str(uuid.uuid4()), user_id=item["user_id"], parent_node_id=parent_node_id,
                child_node_id=node_id, derivation_kind=derivation_kind,
                metadata_json=_canonical_json(derivation_metadata), at=item["at"],
            ))
        session.commit()
        session.refresh(row)
        result = _row_to_dict(row)
        if parent_node_id:
            result["lineage_parent_node_id"] = parent_node_id
            result["derivation_kind"] = derivation_kind
            result["derivation_metadata"] = derivation_metadata
        return result


def record_unread_words(user_id: str, words: list[str], context: str, *, at: int) -> None:
    clean_words = sorted({word.strip()[:120] for word in words if word and word.strip()})
    clean_context = context.strip()[:1000]
    if not clean_words:
        return
    with SessionLocal() as session:
        for word in clean_words:
            row = session.query(UnreadWordRow).filter(
                UnreadWordRow.user_id == user_id,
                UnreadWordRow.word == word,
                UnreadWordRow.context == clean_context,
            ).first()
            if row is None:
                session.add(UnreadWordRow(
                    id=str(uuid.uuid4()), user_id=user_id, word=word, context=clean_context,
                    frequency=1, first_at=at, last_at=at,
                ))
            else:
                row.frequency += 1
                row.last_at = at
        session.commit()


def list_unread_words(user_id: str | None = None, *, limit: int = 100) -> list[dict]:
    with SessionLocal() as session:
        query = session.query(UnreadWordRow)
        if user_id is not None:
            query = query.filter(UnreadWordRow.user_id == user_id)
        rows = query.all()
        aggregate: dict[str, dict] = {}
        users_by_word: dict[str, set[str]] = {}
        for row in rows:
            item = aggregate.setdefault(row.word, {
                "word": row.word,
                "frequency": 0,
                "first_at": row.first_at,
                "last_at": row.last_at,
                "contexts": [],
            })
            item["frequency"] += row.frequency
            item["first_at"] = min(item["first_at"], row.first_at)
            item["last_at"] = max(item["last_at"], row.last_at)
            if row.context and row.context not in item["contexts"] and len(item["contexts"]) < 3:
                item["contexts"].append(row.context)
            users_by_word.setdefault(row.word, set()).add(row.user_id)
        items = sorted(aggregate.values(), key=lambda item: (-item["frequency"], -item["last_at"], item["word"]))
        for item in items:
            item["context"] = item["contexts"][0] if item["contexts"] else ""
            if user_id is None:
                item["user_count"] = len(users_by_word[item["word"]])
        return items[:limit]


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
        stored_hash = row.password_hash if row is not None else _DUMMY_PASSWORD_HASH
        password_matches = verify_password(password, stored_hash)
        if row is None or not password_matches:
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


def link_external_identity(
    user_id: str,
    *,
    provider: str,
    subject: str,
    email: str | None = None,
) -> dict:
    clean_provider = provider.strip().lower()
    clean_subject = subject.strip()
    if not clean_provider or len(clean_provider) > 64:
        raise ValueError("invalid identity provider")
    if not clean_subject or len(clean_subject) > 512:
        raise ValueError("invalid external subject")
    with SessionLocal() as session:
        if session.get(UserAccountRow, user_id) is None:
            raise ValueError("user not found")
        row = ExternalIdentityRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            provider=clean_provider,
            subject=clean_subject,
            email=(email or "").strip() or None,
            at=_now_ms(),
        )
        session.add(row)
        session.commit()
        return {
            "id": row.id,
            "user_id": row.user_id,
            "provider": row.provider,
            "subject": row.subject,
            "email": row.email,
            "at": row.at,
        }


def get_user_by_external_identity(provider: str, subject: str) -> dict | None:
    with SessionLocal() as session:
        identity = session.query(ExternalIdentityRow).filter(
            ExternalIdentityRow.provider == provider.strip().lower(),
            ExternalIdentityRow.subject == subject.strip(),
        ).first()
        if identity is None:
            return None
        row = session.get(UserAccountRow, identity.user_id)
        if row is None:
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


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
    actor: dict | None = None,
) -> dict | None:
    with SessionLocal() as session:
        query = session.query(UserAccountRow).filter(UserAccountRow.id == user_id)
        if actor is not None and actor.get("role") != "admin":
            if actor.get("role") != "group_lead" or not actor.get("group_id"):
                return None
            query = query.filter(
                UserAccountRow.group_id == actor["group_id"],
                UserAccountRow.role == "user",
            )
        row = query.first()
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
        result = session.execute(
            text(
                """
                UPDATE user_accounts
                SET image_generation_count = COALESCE(image_generation_count, 0) + :amount
                WHERE id = :user_id
                """
            ),
            {"amount": amount, "user_id": user_id},
        )
        if result.rowcount == 0:
            session.rollback()
            return None
        session.commit()
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
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


def update_user_settings(
    user_id: str,
    ui_theme: str | None = None,
    ui_mode: str | None = None,
    ui_custom: dict | None = None,
    settings_tab: str | None = None,
    model_settings: dict | None = None,
) -> dict | None:
    from .model_settings import update_user_model_settings

    if ui_theme is not None and ui_theme not in {"light", "dark"}:
        raise ValueError("invalid ui theme")
    if ui_mode is not None and ui_mode not in _UI_MODES:
        raise ValueError("invalid ui mode")
    if ui_custom is not None and (
        not isinstance(ui_custom, dict)
        or any(key not in _UI_CUSTOM_KEYS or not isinstance(value, bool) for key, value in ui_custom.items())
    ):
        raise ValueError("invalid custom ui settings")
    if settings_tab is not None and settings_tab not in _SETTINGS_TABS:
        raise ValueError("invalid settings tab")
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        if ui_theme is not None:
            row.ui_theme = ui_theme
        if ui_mode is not None:
            row.ui_mode = ui_mode
        if ui_custom is not None:
            row.ui_custom = json.dumps(ui_custom, ensure_ascii=False, sort_keys=True)
        if settings_tab is not None:
            row.settings_tab = settings_tab
        if model_settings is not None:
            try:
                current_model_settings = json.loads(row.model_settings or "{}")
            except json.JSONDecodeError:
                current_model_settings = {}
            row.model_settings = json.dumps(
                update_user_model_settings(current_model_settings, model_settings),
                ensure_ascii=False,
            )
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
    if "prompt_provider" in settings:
        provider = settings["prompt_provider"]
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("demo prompt provider is required")
        clean["prompt_provider"] = provider.strip()
    if "prompt_model" in settings:
        model = settings["prompt_model"]
        if not isinstance(model, str) or not model.strip():
            raise ValueError("demo prompt model is required")
        clean["prompt_model"] = model.strip()
    # Values stored before prompt_provider existed carry the provider inside
    # prompt_model. Read both shapes, write the pair.
    from .model_settings import split_model_ref

    prompt_prefix, prompt_bare = split_model_ref(str(clean["prompt_model"]), None)
    if prompt_prefix:
        clean["prompt_provider"] = prompt_prefix
        clean["prompt_model"] = prompt_bare
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
    if "timeout_seconds" in settings:
        try:
            timeout = int(settings["timeout_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError("demo timeout must be an integer") from exc
        if timeout < 60 or timeout > 86400:
            raise ValueError("demo timeout must be between 60 and 86400 seconds")
        clean["timeout_seconds"] = timeout
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
    if (
        len(items) == 2
        and items[0].get("id") == "png-1024"
        and items[0].get("y_px") == 1024
        and items[1].get("id") == "png-2048"
        and items[1].get("y_px") == 2048
    ):
        return [dict(item) for item in _EXPORT_TEMPLATE_DEFAULTS]
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


def delete_user(user_id: str, *, cascade: bool = False, actor: dict | None = None) -> bool:
    with SessionLocal() as session:
        query = session.query(UserAccountRow).filter(UserAccountRow.id == user_id)
        if actor is not None and actor.get("role") != "admin":
            if actor.get("role") != "group_lead" or not actor.get("group_id"):
                return False
            query = query.filter(
                UserAccountRow.group_id == actor["group_id"],
                UserAccountRow.role == "user",
            )
        row = query.first()
        if not row:
            return False
        if not cascade:
            if session.query(HistoryRow).filter(HistoryRow.user_id == user_id).first():
                raise ValueError("user has history")
        else:
            session.query(HistoryRow).filter(HistoryRow.user_id == user_id).delete()
        session.query(OkugakiRow).filter(OkugakiRow.user_id == user_id).delete()
        session.query(UserSessionRow).filter(UserSessionRow.user_id == user_id).delete()
        session.query(ExternalIdentityRow).filter(ExternalIdentityRow.user_id == user_id).delete()
        session.query(UnreadWordRow).filter(UnreadWordRow.user_id == user_id).delete()
        session.query(LineageEdgeRow).filter(LineageEdgeRow.user_id == user_id).delete()
        session.query(LineageNodeRow).filter(LineageNodeRow.user_id == user_id).delete()
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
              AND h.history_visibility = 'normal'
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
                  AND h.history_visibility = 'normal'
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
    items = _rows_to_dicts_with_lineage(session, rows)
    return sorted(items, key=lambda item: order[item["id"]]), int(total)


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
            HistoryRow.history_visibility == "normal",
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
            .order_by(HistoryRow.at.desc(), HistoryRow.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return _rows_to_dicts_with_lineage(session, rows), total


def list_lineage_groups(
    user_id: str,
    offset: int = 0,
    limit: int = 12,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
) -> tuple[list[dict], int]:
    """List deterministic history groups, paginated by lineage rather than artwork."""
    with SessionLocal() as session:
        query = (
            session.query(HistoryRow)
            .join(LineageNodeRow, LineageNodeRow.id == HistoryRow.lineage_node_id)
            .filter(
                HistoryRow.user_id == user_id,
                LineageNodeRow.user_id == user_id,
                HistoryRow.trashed == (1 if trashed else 0),
                HistoryRow.history_visibility == "normal",
            )
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        search = query_text.strip()
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(
                HistoryRow.input.ilike(pattern),
                HistoryRow.ddl.ilike(pattern),
                HistoryRow.stage1_model.ilike(pattern),
                HistoryRow.stage2_model.ilike(pattern),
                HistoryRow.catalog_id.ilike(pattern),
            ))
        root_id = func.coalesce(LineageNodeRow.root_node_id, LineageNodeRow.id)
        aggregates = (
            query.with_entities(
                root_id.label("root_node_id"),
                func.count(HistoryRow.id).label("item_count"),
                func.sum(case((HistoryRow.starred == 1, 1), else_=0)).label("starred_count"),
                func.max(HistoryRow.at).label("latest_at"),
            )
            .group_by(root_id)
            .subquery()
        )
        total = int(session.query(func.count()).select_from(aggregates).scalar() or 0)
        page_rows = (
            session.query(aggregates)
            .order_by(aggregates.c.latest_at.desc(), aggregates.c.root_node_id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        if not page_rows:
            return [], total

        ranked = (
            query.with_entities(
                HistoryRow.id.label("history_id"),
                root_id.label("root_node_id"),
                func.row_number().over(
                    partition_by=root_id,
                    order_by=(HistoryRow.at.desc(), HistoryRow.id.asc()),
                ).label("row_number"),
            )
            .subquery()
        )
        selected_roots = [row.root_node_id for row in page_rows]
        representative_pairs = (
            session.query(ranked.c.root_node_id, ranked.c.history_id)
            .filter(ranked.c.root_node_id.in_(selected_roots), ranked.c.row_number == 1)
            .all()
        )
        representative_id_by_root = {root: history_id for root, history_id in representative_pairs}
        representative_ids = list(representative_id_by_root.values())
        representative_rows = session.query(HistoryRow).filter(HistoryRow.id.in_(representative_ids)).all()
        representative_by_id = {
            item["id"]: item
            for item in _rows_to_dicts_with_lineage(session, representative_rows)
        }
        groups = []
        for row in page_rows:
            representative_id = representative_id_by_root.get(row.root_node_id)
            representative = representative_by_id.get(representative_id or "")
            if representative is None:
                continue
            groups.append({
                "root_node_id": row.root_node_id,
                "representative": representative,
                "item_count": int(row.item_count or 0),
                "starred_count": int(row.starred_count or 0),
                "latest_at": int(row.latest_at or 0),
            })
        return groups, total


def list_lineage_group_items(
    user_id: str,
    root_node_id: str,
    offset: int = 0,
    limit: int = 100,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as session:
        root = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == root_node_id,
            LineageNodeRow.user_id == user_id,
        ).first()
        if root is None or (root.root_node_id or root.id) != root_node_id:
            return [], 0
        query = (
            session.query(HistoryRow)
            .join(LineageNodeRow, LineageNodeRow.id == HistoryRow.lineage_node_id)
            .filter(
                HistoryRow.user_id == user_id,
                LineageNodeRow.user_id == user_id,
                LineageNodeRow.root_node_id == root_node_id,
                HistoryRow.trashed == (1 if trashed else 0),
                HistoryRow.history_visibility == "normal",
            )
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        search = query_text.strip()
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
        rows = query.order_by(HistoryRow.at.desc(), HistoryRow.id.asc()).offset(offset).limit(limit).all()
        return _rows_to_dicts_with_lineage(session, rows), total


def item_position(user_id: str, item_id: str, trashed: bool = False, starred: bool = False) -> int | None:
    with SessionLocal() as session:
        target = session.query(HistoryRow).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.id == item_id,
            HistoryRow.trashed == (1 if trashed else 0),
            HistoryRow.history_visibility == "normal",
        ).first()
        if target is None or (starred and not target.starred):
            return None
        query = session.query(func.count(HistoryRow.id)).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.trashed == (1 if trashed else 0),
            HistoryRow.history_visibility == "normal",
            or_(
                HistoryRow.at > target.at,
                and_(HistoryRow.at == target.at, HistoryRow.id < target.id),
            ),
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        return int(query.scalar() or 0)


def set_item_starred(user_id: str, item_id: str, starred: bool, note: str | None = None) -> dict | None:
    with SessionLocal() as session:
        row = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id == item_id)
            .first()
        )
        if not row:
            return None
        row.starred = 1 if starred else 0
        if note is not None:
            clean_note = note.strip()[:240]
            row.note = clean_note or None
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
        items = _rows_to_dicts_with_lineage(session, rows)
        return sorted(items, key=lambda item: order.get(item["id"], len(order)))


def _neighbor_score(raw: str | None) -> dict:
    try:
        score = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    return score if isinstance(score, dict) else {}


def list_neighbor_candidates(user_id: str, item_id: str, *, limit: int = 10_000) -> list[dict]:
    """Load only fields used by similarity ranking, avoiding SVG and lineage hydration."""
    with SessionLocal() as session:
        rows = (
            session.query(HistoryRow.id, HistoryRow.at, HistoryRow.score)
            .filter(
                HistoryRow.user_id == user_id,
                HistoryRow.id != item_id,
                HistoryRow.trashed == 0,
                HistoryRow.history_visibility == "normal",
            )
            .order_by(HistoryRow.at.desc(), HistoryRow.id.asc())
            .limit(limit)
            .all()
        )
        return [{"id": row.id, "at": row.at, "score": _neighbor_score(row.score)} for row in rows]


def delete_all(user_id: str) -> None:
    with SessionLocal() as session:
        session.query(OkugakiRow).filter(OkugakiRow.user_id == user_id).delete()
        session.query(LineageEdgeRow).filter(LineageEdgeRow.user_id == user_id).delete()
        session.query(LineageNodeRow).filter(LineageNodeRow.user_id == user_id).delete()
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


def delete_items(user_id: str, ids: list[str], *, require_trashed: bool = False) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        query = session.query(HistoryRow).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.id.in_(ids),
        )
        if require_trashed:
            query = query.filter(HistoryRow.trashed == 1)
        rows = query.all()
        now = _now_ms()
        node_ids = [row.lineage_node_id for row in rows if row.lineage_node_id]
        if node_ids:
            nodes = session.query(LineageNodeRow).filter(
                LineageNodeRow.user_id == user_id,
                LineageNodeRow.id.in_(node_ids),
            ).all()
            for node in nodes:
                node.state = "tombstone"
                node.history_id = None
                node.description_hash = None
                node.render_hash = None
                node.deleted_at = now
            touching = session.query(LineageEdgeRow).filter(
                LineageEdgeRow.user_id == user_id,
                or_(LineageEdgeRow.parent_node_id.in_(node_ids), LineageEdgeRow.child_node_id.in_(node_ids)),
            ).all()
            for edge in touching:
                edge.metadata_json = "{}"
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


def delete_all_trashed_items(user_id: str) -> int:
    with SessionLocal() as session:
        ids = [
            item_id
            for item_id, in session.query(HistoryRow.id).filter(
                HistoryRow.user_id == user_id,
                HistoryRow.trashed == 1,
            )
        ]
    return delete_items(user_id, ids, require_trashed=True)
