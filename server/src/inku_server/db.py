"""Canonical SQLite models, queries, and compatibility façade."""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, time as clock_time, timedelta
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint, and_, case, func, inspect, or_, select, text, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .color_catalogs import RENAMED_COLOR_CATALOG_IDS
from .identity import description_hash
from .limits import normalize_limits
from .plugins import canvas_aspect_ratio_for_aspect, normalize_canvas_aspect_id
from .persistence.config import CANONICAL_DB_ENV, PERSISTENCE_CONFIG, sqlite_database_path
from .persistence.backup import create_sqlite_snapshot
from .persistence.engine import CANONICAL_SQLITE_PRAGMAS, create_sqlite_engine
from .persistence.migrations import MigrationExecutionError, ensure_current_schema, install_history_fts

_SESSION_MAX_AGE_SECONDS = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))

engine = create_sqlite_engine(
    PERSISTENCE_CONFIG.canonical_url,
    setting=CANONICAL_DB_ENV,
    pragmas=CANONICAL_SQLITE_PRAGMAS,
)

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
    "variation",  # Stage 1.5 variation, renamed from hensou in v2.8.0.
    # Sketching (Stage 0.5, v2.10). Fires when the grain differs from the parent's,
    # which includes switching the layer on or off (the grain is fine, coarse
    # or absent). The web client has sent this since v2.9.37; until v2.11.3 the
    # server did not know the name and the whole save was lost ([I-137]).
    "sketch_grain_change",
}

# v2.8.0 rename table. `_migrate_columns` rewrites persisted rows through this
# exact mapping; the private naming record preserves the historical rationale.
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
    # How the catalog was asked for, not which one came back: `auto` resolves to
    # a different catalog for every description, so the resolved id below cannot
    # say whether the author chose one or let the server read the words. Null on
    # every work saved before this column, which means "older than the field",
    # never "was not auto".
    # ⚠ Deliberately absent from the render-hash payloads: the hash is the
    # identity of a drawing, and adding a term would rebuild it for every work
    # already stored.
    catalog_mode = Column(String,     nullable=True)
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
    # v2.13.38: why Stage 2 fell back to the deterministic score. Unlike the
    # column above, NULL is not "it held": a writer that did not fall says so
    # with "none", so a row drawn before this column exists stays tellable
    # apart from one drawn after it. Backfilling would erase that difference.
    compose_fallback = Column(String, nullable=True)
    interpretation_seed = Column(String, nullable=True)
    seed_text = Column(Text, nullable=True)
    # Stage 0.5 (v2.10). Both NULL = the work was painted straight from the
    # description, which is every work made before the layer existed.
    # sketch_text is stored so a redraw does not have to call 0.5 again --
    # the layer is not deterministic, so re-running it would not replay.
    sketch_text = Column(Text, nullable=True)
    sketch_grain = Column(String, nullable=True)
    # What Stage 0.5 did for this work. NULL is not "off": it means the row
    # predates this column, i.e. the work was drawn before the layer recorded
    # what it did. Four separate events used to collapse into a NULL
    # sketch_text -- no layer yet, layer switched off, route that never calls
    # it, and a run that failed -- and could not be told apart afterwards.
    sketch_state = Column(String, nullable=True)
    # The limits that actually governed this work, as JSON. Per-install settings
    # would otherwise make the same description a different work with nothing to
    # say why -- the same problem the chosen model and the colour catalogue solve
    # by being recorded here. NULL means the row predates the column, not
    # "the defaults".
    render_limits = Column(Text, nullable=True)
    render_hash = Column(String, nullable=True, index=True)
    trashed      = Column(Integer,    nullable=False, default=0)
    starred      = Column(Integer,    nullable=False, default=0)
    # A second, independent mark: 'this one is worth working on again'. Kept
    # apart from starred so a work can be a favourite, a revision target, both
    # or neither.
    for_revision = Column(Integer,    nullable=False, default=0)
    # The share bit and the group it points at, together. A work is readable by a
    # group only when the bit is up AND the group matches: the bit alone is a
    # permission with no destination, and the group alone is a destination nobody
    # opened. Raising the bit without naming a group fills in the owner's own
    # organisation group, the way a new file takes the group of whoever made it.
    for_share      = Column(Integer, nullable=False, default=0)
    share_group_id = Column(String, ForeignKey("user_groups.id"), nullable=True)
    note         = Column(Text,       nullable=True)
    source_text = Column(Text, nullable=True)
    display_label = Column(String, nullable=True)
    batch_line_number = Column(Integer, nullable=True)
    batch_run_id = Column(String, nullable=True, index=True)
    description_hash = Column(String, nullable=True, index=True)
    history_visibility = Column(String, nullable=False, default="normal", index=True)
    lineage_node_id = Column(String, nullable=True, unique=True, index=True)
    idempotency_key = Column(String, nullable=True)
    score_pre_coerce = Column(Text, nullable=True)
    coerce_trace_version = Column(Integer, nullable=True)
    coerce_catalog_digest = Column(String, nullable=True)
    coerce_trace = Column(Text, nullable=True)


class CoerceTraceCatalogRow(Base):
    __tablename__ = "coerce_trace_catalogs"
    digest = Column(String, primary_key=True)
    trace_version = Column(Integer, nullable=False)
    snapshot_json = Column(Text, nullable=False)


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


class HistoryAclRow(Base):
    """Who else may see or change one work. Empty by default.

    A work carries its own guest list. The permission groups decide a default
    scope -- what an admin or a leader may reach without anyone naming them --
    and this table is the exception to it, one row per (work, subject) pair.
    Kept apart from the group scope on purpose: if the two were one mechanism, a
    change that broke either would be absorbed by the other and no test could
    tell them apart.
    """

    __tablename__ = "history_acl"
    __table_args__ = (
        UniqueConstraint("history_id", "subject_type", "subject_id", name="uq_history_acl_subject"),
    )

    id = Column(String, primary_key=True)
    history_id = Column(String, ForeignKey("history.id"), nullable=False, index=True)
    subject_type = Column(String, nullable=False)   # "user" | "org_group"
    subject_id = Column(String, nullable=False, index=True)
    permission = Column(String, nullable=False)     # "read" | "write"
    at = Column(BigInteger, nullable=False, index=True)


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
    history_strip_fields = Column(Text, nullable=False, default='["generation", "model"]')
    tooltips_enabled = Column(Boolean, nullable=False, default=True)
    # Whether this user asked downloads to go to a folder they picked. The
    # directory handle itself cannot come here -- it is a browser object that
    # only survives in IndexedDB -- so the server holds the intent and the
    # folder's display name, and the browser holds the permission.
    download_folder_enabled = Column(Boolean, nullable=False, default=False)
    download_folder_name = Column(String, nullable=True)
    settings_tab  = Column(String, nullable=False, default="db")
    model_settings = Column(Text, nullable=False, default="{}")
    image_generation_count = Column(Integer, nullable=False, default=0)
    batch_prompt_history = Column(Text, nullable=False, default="[]")
    demo_settings = Column(Text, nullable=False, default="{}")
    export_templates = Column(Text, nullable=False, default="[]")
    plugin_storage = Column(Text, nullable=False, default="{}")
    at            = Column(BigInteger, nullable=False, index=True)


class PermissionGroupRow(Base):
    """What a member may do. Fixed set of three; not user-creatable."""

    __tablename__ = "permission_groups"

    id   = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)   # admins / leaders / users
    at   = Column(BigInteger, nullable=False, index=True)


class UserPermissionGroupRow(Base):
    """Many-to-many: one member may hold several permission groups."""

    __tablename__ = "user_permission_groups"
    __table_args__ = (
        UniqueConstraint("user_id", "permission_group_id", name="uq_user_permission_group"),
    )

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    permission_group_id = Column(String, ForeignKey("permission_groups.id"), nullable=False, index=True)
    at = Column(BigInteger, nullable=False, index=True)


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
_HISTORY_COLUMN_MIGRATIONS = {
    "user_id": "ALTER TABLE history ADD COLUMN user_id VARCHAR",
    "catalog_id": "ALTER TABLE history ADD COLUMN catalog_id VARCHAR",
    "catalog_mode": "ALTER TABLE history ADD COLUMN catalog_mode VARCHAR",
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
    # No DEFAULT and no UPDATE, on purpose: a default would write "none" into
    # every existing row and claim their compose stage held, which nothing
    # recorded. They stay NULL, which is the true statement about them.
    "compose_fallback": "ALTER TABLE history ADD COLUMN compose_fallback VARCHAR",
    "expanded_ddl": "ALTER TABLE history ADD COLUMN expanded_ddl TEXT",
    "interpretation_seed": "ALTER TABLE history ADD COLUMN interpretation_seed VARCHAR",
    "seed_text": "ALTER TABLE history ADD COLUMN seed_text TEXT",
    "render_hash": "ALTER TABLE history ADD COLUMN render_hash VARCHAR",
    "trashed": "ALTER TABLE history ADD COLUMN trashed INTEGER NOT NULL DEFAULT 0",
    "starred": "ALTER TABLE history ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
    "for_revision": "ALTER TABLE history ADD COLUMN for_revision INTEGER NOT NULL DEFAULT 0",
    # The bit gets a DEFAULT and the destination does not, and the difference is
    # the point: every existing row is "not shared", which is a fact, while every
    # existing row's group is unknown rather than the migrating admin's own.
    "for_share": "ALTER TABLE history ADD COLUMN for_share INTEGER NOT NULL DEFAULT 0",
    "share_group_id": "ALTER TABLE history ADD COLUMN share_group_id VARCHAR",
    "note": "ALTER TABLE history ADD COLUMN note TEXT",
    "source_text": "ALTER TABLE history ADD COLUMN source_text TEXT",
    "display_label": "ALTER TABLE history ADD COLUMN display_label VARCHAR",
    "batch_line_number": "ALTER TABLE history ADD COLUMN batch_line_number INTEGER",
    "batch_run_id": "ALTER TABLE history ADD COLUMN batch_run_id VARCHAR",
    "description_hash": "ALTER TABLE history ADD COLUMN description_hash VARCHAR",
    "history_visibility": "ALTER TABLE history ADD COLUMN history_visibility VARCHAR NOT NULL DEFAULT 'normal'",
    "lineage_node_id": "ALTER TABLE history ADD COLUMN lineage_node_id VARCHAR",
    "idempotency_key": "ALTER TABLE history ADD COLUMN idempotency_key VARCHAR",
    "sketch_text": "ALTER TABLE history ADD COLUMN sketch_text TEXT",
    "sketch_grain": "ALTER TABLE history ADD COLUMN sketch_grain VARCHAR",
    # No DEFAULT and no backfill: existing rows keep NULL, which is what "drawn
    # before this column existed" means. Filling them with a guess would erase
    # the distinction the column was added to make.
    "sketch_state": "ALTER TABLE history ADD COLUMN sketch_state VARCHAR",
    # Same rule as sketch_state: no DEFAULT and no backfill. Filling old rows
    # with today's defaults would claim a configuration nobody recorded.
    "render_limits": "ALTER TABLE history ADD COLUMN render_limits TEXT",
    "score_pre_coerce": "ALTER TABLE history ADD COLUMN score_pre_coerce TEXT",
    "coerce_trace_version": "ALTER TABLE history ADD COLUMN coerce_trace_version INTEGER",
    "coerce_catalog_digest": "ALTER TABLE history ADD COLUMN coerce_catalog_digest VARCHAR",
    "coerce_trace": "ALTER TABLE history ADD COLUMN coerce_trace TEXT",
}
_LINEAGE_NODE_COLUMN_MIGRATIONS = {
    "root_node_id": "ALTER TABLE lineage_nodes ADD COLUMN root_node_id VARCHAR",
}
_USER_ACCOUNT_COLUMN_MIGRATIONS = {
    "ui_theme": "ALTER TABLE user_accounts ADD COLUMN ui_theme VARCHAR NOT NULL DEFAULT 'light'",
    "ui_mode": "ALTER TABLE user_accounts ADD COLUMN ui_mode VARCHAR NOT NULL DEFAULT 'simple'",
    "ui_custom": "ALTER TABLE user_accounts ADD COLUMN ui_custom TEXT NOT NULL DEFAULT '{}'",
    # The default is what the strip printed before it could be asked, so an
    # account that predates the column sees no change.
    "history_strip_fields": (
        "ALTER TABLE user_accounts ADD COLUMN history_strip_fields TEXT NOT NULL "
        "DEFAULT '[\"generation\", \"model\"]'"
    ),
    "tooltips_enabled": "ALTER TABLE user_accounts ADD COLUMN tooltips_enabled BOOLEAN NOT NULL DEFAULT 1",
    "download_folder_enabled": "ALTER TABLE user_accounts ADD COLUMN download_folder_enabled BOOLEAN NOT NULL DEFAULT 0",
    "download_folder_name": "ALTER TABLE user_accounts ADD COLUMN download_folder_name VARCHAR",
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
# How many past batch prompts a member keeps. Cut on the way in and on the way
# out, so lowering it later drops the tail of what is already stored. The web
# client holds the same number (BATCH_PROMPT_HISTORY_LIMIT in +page.svelte);
# raising one without the other changes nothing, because the shorter of the two
# is what reaches the picker.
_BATCH_PROMPT_HISTORY_LIMIT = 50
_BATCH_PROMPT_HISTORY_MAX_TEXT = 20_000
_SETTINGS_TABS = {"models", "db", "plugins", "users", "export", "misc", "server_misc", "logs", "limits"}
_UI_MODES = {"simple", "full", "custom"}
_UI_CUSTOM_KEYS = {
    "input_modes", "drawing_settings", "ddl_tools", "detail_status",
    "work_tools", "history", "auxiliary",
}
# What the history strip prints under each thumbnail. The order is the order the
# strip reads them in, so it is a list here rather than a set; at most
# _HISTORY_STRIP_FIELD_LIMIT of them, and an empty list is a choice, not an
# absence. The web half of this pair is web/src/lib/historyStripFields.ts.
_HISTORY_STRIP_FIELDS = ("generation", "model", "engine_version", "bytes")
_HISTORY_STRIP_FIELD_LIMIT = 2
_HISTORY_STRIP_FIELDS_DEFAULT = ["generation", "model"]


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
    """Which facts the strip prints, as a list this API can hand to the page.

    Anything that is not a list is an absence and takes the default. A list is
    taken at its word -- unknown names drop, repeats collapse, the declared
    order is restored, and at most two survive -- so an empty list comes back
    empty, which is how "print nothing under the picture" is stored at all.
    """
    if not isinstance(value, list):
        return list(_HISTORY_STRIP_FIELDS_DEFAULT)
    chosen = {item for item in value if item in _HISTORY_STRIP_FIELDS}
    ordered = [field for field in _HISTORY_STRIP_FIELDS if field in chosen]
    return ordered[:_HISTORY_STRIP_FIELD_LIMIT]
_PLUGIN_STORAGE_MAX_BYTES = 20_000
_OUTPUT_SAVE_SETTINGS_KEY = "output_save_settings"
_OUTPUT_SAVE_DEFAULT_SETTINGS = {
    "enabled": True,
    "output_dir": str(Path(os.getenv("INKU_OUTPUT_DIR", str(Path.home() / ".local" / "share" / "inku" / "outputs")))),
    "png_size": int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160")),
}
_THUMBNAIL_SETTINGS_KEY = "thumbnail_settings"
# Off by default: the second size doubles the rebuild and roughly quadruples the
# stored bytes, and is worth neither until someone is looking at the listing on
# a HiDPI screen.
# The parallelism is the administrator's to enter: nothing here reads the core
# count, and in a container the host's count is the wrong answer anyway.
_THUMBNAIL_DEFAULT_SETTINGS = {
    "hidpi": False,
    "workers": 4,
}
THUMBNAIL_WORKERS_MIN = 1
THUMBNAIL_WORKERS_MAX = 16
_RENDER_CONCURRENCY_SETTINGS_KEY = "render_concurrency_settings"
# INKU_RENDER_CONCURRENCY / INKU_CLIENT_FANOUT_LIMIT seed the first value only;
# once stored, the DB row is the source of truth (admin settings screen).
_RENDER_CONCURRENCY_DEFAULT_SETTINGS = {
    "server_limit": int(os.getenv("INKU_RENDER_CONCURRENCY", "2")),
    "client_limit": int(os.getenv("INKU_CLIENT_FANOUT_LIMIT", "4")),
}
RENDER_CONCURRENCY_MIN = 1
RENDER_CONCURRENCY_MAX = 16
_RENDER_LIMIT_SETTINGS_KEY = "render_limit_settings"
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
    (
        "ix_history_user_for_revision_trashed_at",
        "CREATE INDEX IF NOT EXISTS ix_history_user_for_revision_trashed_at ON history (user_id, for_revision, trashed, at)",
    ),
    (
        # Deliberately NOT led by user_id, unlike the three above. Those narrow a
        # reader down to their own works; this one is read when somebody looks at
        # OTHER people's, so leading with the owner would put the column the query
        # never constrains first and the index would go unused.
        "ix_history_for_share_group",
        "CREATE INDEX IF NOT EXISTS ix_history_for_share_group ON history (for_share, share_group_id, trashed, at)",
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


def _ensure_default_user_group(session: Session | None = None) -> None:
    with _session_scope(session) as (active_session, owns_session):
        exists = active_session.query(UserGroupRow).first()
        if exists:
            return
        active_session.add(UserGroupRow(id=str(uuid.uuid4()), name="default", at=_now_ms()))
        _finish_session(active_session, owns_session)


def has_permission_group(actor: dict, name: str) -> bool:
    """Membership test against the permission groups the actor holds."""
    if not actor:
        return False
    return name in (actor.get("permission_groups") or ())


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
    """Identity only, for paths that go through _owned_by and never widen.

    Cascades and idempotency-replay lookups do not read permissions, so resolving
    the account for them would be two queries spent on a decision nothing makes.
    Handing this to _readable_by by mistake narrows rather than widens.
    """
    return {"id": user_id, "permission_groups": [], "group_id": None}


ACL_SUBJECT_TYPES = ("user", "org_group")

# Two rights, not three. `delete` lives inside `write`: a third would multiply
# the acceptance surface for a need nobody has measured yet, and it can be added
# later without moving what is already here.
ACL_PERMISSIONS = ("read", "write")


def _acl_grants(actor: dict, permissions: tuple[str, ...]):
    """Works explicitly granted to this actor at one of `permissions`.

    The actor is reached as themselves and as a member of their organisation
    group. Permission groups are deliberately not subjects: a grant to `users`
    would mean "everyone", which is publication and needs a different design.
    """
    subjects = [and_(HistoryAclRow.subject_type == "user", HistoryAclRow.subject_id == actor["id"])]
    if actor.get("group_id"):
        subjects.append(
            and_(HistoryAclRow.subject_type == "org_group", HistoryAclRow.subject_id == actor["group_id"])
        )
    return select(HistoryAclRow.history_id).where(
        HistoryAclRow.permission.in_(permissions),
        or_(*subjects),
    )


def _shared_with_group(actor: dict):
    """Works whose owner opened them to the actor's organisation group.

    The third way in, after the group scope and an explicit grant. It differs
    from both by being a CONDITION rather than a list: one bit on the work names
    every reader at once, which is what an ACL row -- always one work, one
    subject -- cannot say.

    An actor with no group is not in any group, so nothing here reaches them.
    Returning a clause that matched a NULL share_group_id would hand every
    half-configured work to every groupless account.
    """
    return select(HistoryRow.id).where(
        HistoryRow.for_share == 1,
        HistoryRow.share_group_id == actor["group_id"],
    )


def _same_org_group(actor: dict):
    """Accounts sharing the actor's organisation group, as a subquery.

    A subquery rather than a resolved list of ids: the membership is read at the
    moment the outer query runs, so a member added between the actor being built
    and the query being issued is not briefly invisible.
    """
    return select(UserAccountRow.id).where(UserAccountRow.group_id == actor["group_id"])


def _readable_by(actor: dict, owner_column, acl_history_id=None):
    """Rows the actor may see: owner, or group scope, or an explicit grant.

    admins see everything, orphan rows included: `history.user_id` is nullable
    and a database restored from before the column was backfilled holds works
    owned by nobody. Showing them to no one reads as "the backup lost my work".

    leaders see their own organisation group. The range is the ORGANISATION
    group, not the permission group -- circle_a's leader sees circle_a, not every
    work on the server -- and a leader with no group_id sees only their own,
    which is the same defence delete_user and update_user already apply.

    `acl_history_id` is the column holding the work's id, where the caller has
    one. Rows that are not a work and carry no id to grant against (lineage
    edges, for now) pass nothing and are decided by scope alone. A `write` grant
    satisfies a read: someone trusted to change a work can obviously see it.

    The share bit (I-191) rides on that same branch and not on the scope, which
    is a ruling and not an accident: every caller that hands over a work id gets
    it -- the listing, the search, the lineage nodes -- and `list_okugaki`, the
    one caller that hands over none, does not. A colophon is somebody's writing
    ABOUT a work, and opening the work does not hand that over.
    """
    if has_permission_group(actor, "admins"):
        return true()
    if has_permission_group(actor, "leaders") and actor.get("group_id"):
        scope = or_(owner_column == actor["id"], owner_column.in_(_same_org_group(actor)))
    else:
        scope = owner_column == actor["id"]
    if acl_history_id is None:
        return scope
    ways = [scope, acl_history_id.in_(_acl_grants(actor, ACL_PERMISSIONS))]
    # The same guard the leaders branch above uses, and for the same reason: an
    # actor with no group is in no group. `actor.get("group_id") or ""` would
    # read as defensive and would quietly compare the destination against the
    # empty string instead.
    if actor.get("group_id"):
        ways.append(acl_history_id.in_(_shared_with_group(actor)))
    return or_(*ways)


def _writable_by(actor: dict, owner_column, acl_history_id=None):
    """Rows the actor may change: owner, or admin, or an explicit `write` grant.

    Deliberately narrower than _readable_by, in both halves. A leader reads their
    organisation's works but cannot star, trash, revise or delete them, and a
    `read` grant does not become a `write` one. Collapsing either would make
    every reader an editor.
    """
    if has_permission_group(actor, "admins"):
        return true()
    scope = owner_column == actor["id"]
    if acl_history_id is None:
        return scope
    return or_(scope, acl_history_id.in_(_acl_grants(actor, ("write",))))


def _owned_by(actor: dict, owner_column):
    """Rows the actor owns outright. Unlike the two above, this never widens.

    Cascades and bulk operations (deleting an account, emptying one's own
    history or trash) and idempotency-replay lookups select by ownership, not by
    permission. Routed through _writable_by they would reach every row an admin
    may change, and deleting one account would empty the server.
    """
    return owner_column == actor["id"]


def _readable_node(actor: dict):
    """A lineage node is visible exactly when the work behind it is."""
    return _readable_by(actor, LineageNodeRow.user_id, LineageNodeRow.history_id)


def _readable_edge(actor: dict):
    """An edge is visible exactly when its CHILD is -- never its parent.

    An edge belongs to the derivation, and `lineage_edges.user_id` holds the
    CHILD's owner, so the owner test alone almost says this already. It stops
    being enough once a work can be shared: the child may be visible through a
    grant while its owner column names someone else.

    Following the parent instead would leak the one thing a lineage must not
    disclose. If A's work has children by B and by C, an edge visible to whoever
    can see the PARENT puts C's edge in B's view -- B learns that somebody else
    derived from the same work, and how many did. Following the child, B sees
    A->B and nothing more.
    """
    return LineageEdgeRow.child_node_id.in_(
        select(LineageNodeRow.id).where(_readable_node(actor))
    )


def _readable_node_sql(actor: dict, alias: str = "n") -> tuple[str, dict]:
    """`_readable_node` for the recursive CTEs, which take no ORM expression."""
    return _readable_sql(actor, f"{alias}.user_id", f"{alias}.history_id")


def _readable_sql(actor: dict, owner_column: str, acl_history_id: str | None = None) -> tuple[str, dict]:
    """The _readable_by test as a SQL fragment and its bind parameters.

    The recursive lineage CTEs and the full-text history search are raw SQL and
    cannot take a SQLAlchemy expression, so they take this instead. The two forms
    have to say the same thing and move together; T-1 counts every filter that
    bypasses either, and the search-path test reads a shared work through this
    one specifically -- the failure it guards against is not a leak but a
    disagreement, where the listing shows a work and searching for it does not.
    """
    if has_permission_group(actor, "admins"):
        return "1 = 1", {}
    params = {"acl_owner_id": actor["id"]}
    clauses = [f"{owner_column} = :acl_owner_id"]
    if has_permission_group(actor, "leaders") and actor.get("group_id"):
        params["acl_group_id"] = actor["group_id"]
        clauses.append(f"{owner_column} IN (SELECT id FROM user_accounts WHERE group_id = :acl_group_id)")
    if acl_history_id is not None:
        subjects = ["(subject_type = 'user' AND subject_id = :acl_owner_id)"]
        if actor.get("group_id"):
            params["acl_group_id"] = actor["group_id"]
            subjects.append("(subject_type = 'org_group' AND subject_id = :acl_group_id)")
        clauses.append(
            f"{acl_history_id} IN (SELECT history_id FROM history_acl"
            f" WHERE permission IN ('read', 'write') AND ({' OR '.join(subjects)}))"
        )
        # The share bit (I-191), said here exactly as _readable_by says it. The
        # bind parameter is the same name and the same value the two branches
        # above already write, so a third writer of it is not a collision.
        if actor.get("group_id"):
            params["acl_group_id"] = actor["group_id"]
            clauses.append(
                f"{acl_history_id} IN (SELECT id FROM history"
                f" WHERE for_share = 1 AND share_group_id = :acl_group_id)"
            )
    if len(clauses) == 1:
        return clauses[0], params
    return "(" + " OR ".join(clauses) + ")", params


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


def _ancestor_edge_ids(session, actor: dict, focus_node_id: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    node_visible, params = _readable_node_sql(actor)
    visible = f"child_node_id IN (SELECT n.id FROM lineage_nodes n WHERE {node_visible})"
    step_visible = f"edge.{visible}"
    return list(session.execute(
        text(
            f"""
            WITH RECURSIVE ancestor_edges(id, parent_node_id, child_node_id) AS (
                SELECT id, parent_node_id, child_node_id
                FROM lineage_edges
                WHERE {visible} AND child_node_id = :focus_node_id
                UNION
                SELECT edge.id, edge.parent_node_id, edge.child_node_id
                FROM lineage_edges edge
                JOIN ancestor_edges ancestor
                  ON edge.child_node_id = ancestor.parent_node_id
                WHERE {step_visible}
            )
            SELECT id FROM ancestor_edges LIMIT :limit
            """
        ),
        {**params, "focus_node_id": focus_node_id, "limit": limit},
    ).scalars())


def _descendant_edge_ids(
    session,
    actor: dict,
    focus_node_id: str,
    depth: int,
    limit: int,
) -> list[str]:
    if depth <= 0 or limit <= 0:
        return []
    node_visible, params = _readable_node_sql(actor)
    seed_visible = f"child_node_id IN (SELECT n.id FROM lineage_nodes n WHERE {node_visible})"
    step_visible = f"edge.{seed_visible}"
    return list(session.execute(
        text(
            f"""
            WITH RECURSIVE descendant_edges(id, parent_node_id, child_node_id, depth) AS (
                SELECT id, parent_node_id, child_node_id, 1
                FROM lineage_edges
                WHERE {seed_visible} AND parent_node_id = :focus_node_id
                UNION ALL
                SELECT edge.id, edge.parent_node_id, edge.child_node_id, descendant.depth + 1
                FROM lineage_edges edge
                JOIN descendant_edges descendant
                  ON edge.parent_node_id = descendant.child_node_id
                WHERE {step_visible} AND descendant.depth < :depth
            )
            SELECT id
            FROM descendant_edges
            ORDER BY depth ASC, id ASC
            LIMIT :limit
            """
        ),
        {
            **params,
            "focus_node_id": focus_node_id,
            "depth": depth,
            "limit": limit,
        },
    ).scalars())


def _lineage_node_payload(
    node: LineageNodeRow,
    readable: bool,
    child_counts: dict,
    history_by_id: dict,
    generations: dict,
) -> dict:
    """One node as the lineage answer carries it.

    Three states, told apart by `redacted`, because "gone" and "not yours" mean
    different things to whoever is looking: a deleted parent is never coming
    back, an unreadable one comes back the moment its owner says so. Rendered
    the same way -- dashed card, dashed arrow -- but labelled differently, so
    nobody stops asking.

    A redacted node withholds one thing a tombstone does not: `child_count`. How
    many times somebody else's work has been derived from is itself information
    about that work, and a tombstone has no owner left to keep it from.
    """
    payload = {
        "id": node.id,
        "state": node.state,
        "at": node.at,
        "deleted_at": node.deleted_at,
    }
    if node.state == "tombstone":
        payload["redacted"] = "deleted"
        payload["child_count"] = int(child_counts.get(node.id, 0))
        return payload
    if not readable:
        payload["redacted"] = "not_permitted"
        return payload
    payload["redacted"] = None
    payload["child_count"] = int(child_counts.get(node.id, 0))
    payload["description_hash"] = node.description_hash
    payload["render_hash"] = node.render_hash
    history = history_by_id.get(node.history_id or "")
    if history is not None:
        payload["history"] = _row_to_dict(history)
        payload["history"]["lineage_generation"] = generations.get(node.id)
    return payload


def _lineage_generations(session, actor: dict, node_ids: list[str]) -> dict[str, int]:
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
                _readable_edge(actor),
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
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        focus = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == focus_node_id,
            _readable_node(actor),
        ).first()
        if focus is None:
            return None

        ancestor_ids = _ancestor_edge_ids(session, actor, focus.id, node_limit - 1)
        remaining = max(0, node_limit - 1 - len(ancestor_ids))
        descendant_ids = _descendant_edge_ids(
            session,
            actor,
            focus.id,
            descendant_depth,
            remaining,
        )
        selected_edge_ids = list(dict.fromkeys([*ancestor_ids, *descendant_ids]))
        selected_edges = (
            session.query(LineageEdgeRow)
            .filter(
                _readable_edge(actor),
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

        # Every node an edge reaches, readable or not. A lineage may now cross
        # owners, so dropping the ones the caller cannot read would cut the chain
        # and the child would appear to have no parent at all. They come back
        # redacted instead -- present, connected, empty.
        nodes = session.query(LineageNodeRow).filter(LineageNodeRow.id.in_(node_ids)).all()
        readable_ids = {
            node_id for node_id, in
            session.query(LineageNodeRow.id).filter(
                _readable_node(actor), LineageNodeRow.id.in_(node_ids)
            )
        }
        history_ids = [node.history_id for node in nodes if node.history_id and node.id in readable_ids]
        history_by_id = {
            row.id: row
            for row in session.query(HistoryRow).filter(
                _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                HistoryRow.id.in_(history_ids),
            ).all()
        }
        child_counts = dict(
            session.query(LineageEdgeRow.parent_node_id, func.count(LineageEdgeRow.id))
            .filter(
                _readable_edge(actor),
                LineageEdgeRow.parent_node_id.in_(node_ids),
            )
            .group_by(LineageEdgeRow.parent_node_id)
            .all()
        )
        generations = _lineage_generations(session, actor, sorted(readable_ids))
        node_payloads = [
            _lineage_node_payload(node, node.id in readable_ids, child_counts, history_by_id, generations)
            for node in nodes
        ]
        return {
            "focus_node_id": focus.id,
            "nodes": sorted(node_payloads, key=lambda item: (item["at"], item["id"])),
            "edges": [_lineage_edge_to_dict(edge) for edge in sorted(edges.values(), key=lambda item: (item.at, item.id))],
        }


def promote_lineage_node(user_id: str, node_id: str) -> dict | None:
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        node = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == node_id,
            _writable_by(actor, LineageNodeRow.user_id, LineageNodeRow.history_id),
            LineageNodeRow.state == "lineage_only",
        ).first()
        if node is None or not node.history_id:
            return None
        row = session.query(HistoryRow).filter(
            HistoryRow.id == node.history_id,
            _writable_by(actor, HistoryRow.user_id, HistoryRow.id),
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
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        target = session.query(LineageNodeRow).filter(
            LineageNodeRow.id == target_node_id,
            _readable_node(actor),
        ).first()
        if target is None:
            return None
        reversed_nodes = [target]
        reversed_edges: list[LineageEdgeRow] = []
        seen = {target.id}
        current = target
        while True:
            edge = session.query(LineageEdgeRow).filter(
                _readable_edge(actor),
                LineageEdgeRow.child_node_id == current.id,
            ).first()
            if edge is None or edge.parent_node_id in seen:
                break
            # Walk into the parent whether or not it can be read: the branch is
            # the path from the root, and stopping at the first unreadable
            # ancestor would silently shorten it.
            parent = session.get(LineageNodeRow, edge.parent_node_id)
            if parent is None:
                break
            reversed_edges.append(edge)
            reversed_nodes.append(parent)
            seen.add(parent.id)
            current = parent
        nodes = list(reversed(reversed_nodes))
        edges = list(reversed(reversed_edges))
        node_ids = [node.id for node in nodes]
        readable_ids = {
            node_id for node_id, in
            session.query(LineageNodeRow.id).filter(
                _readable_node(actor), LineageNodeRow.id.in_(node_ids)
            )
        }
        history_ids = [node.history_id for node in nodes if node.history_id and node.id in readable_ids]
        histories = {
            row.id: row
            for row in session.query(HistoryRow).filter(
                _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                HistoryRow.id.in_(history_ids),
            ).all()
        } if history_ids else {}
        child_counts = dict(
            session.query(LineageEdgeRow.parent_node_id, func.count(LineageEdgeRow.id))
            .filter(
                _readable_edge(actor),
                LineageEdgeRow.parent_node_id.in_(node_ids),
            )
            .group_by(LineageEdgeRow.parent_node_id)
            .all()
        )
        generations = _lineage_generations(session, actor, sorted(readable_ids))
        payload_nodes = [
            _lineage_node_payload(node, node.id in readable_ids, child_counts, histories, generations)
            for node in nodes
        ]
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
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        if idempotency_key:
            existing = session.query(OkugakiRow).filter(
                _owned_by(actor, OkugakiRow.user_id),
                OkugakiRow.idempotency_key == idempotency_key,
            ).first()
            if existing is not None:
                result = _okugaki_to_dict(existing)
                result["_idempotent_replay"] = True
                return result
        target = session.query(LineageNodeRow).filter(
            _readable_node(actor),
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
                _owned_by(actor, OkugakiRow.user_id),
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
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        rows = session.query(OkugakiRow).filter(
            _readable_by(actor, OkugakiRow.user_id),
            OkugakiRow.target_node_id == target_node_id,
        ).order_by(OkugakiRow.at.asc(), OkugakiRow.id.asc()).all()
        return [_okugaki_to_dict(row) for row in rows]


def get_okugaki_by_idempotency(user_id: str, idempotency_key: str) -> dict | None:
    owner = _owner_actor(user_id)
    with SessionLocal() as session:
        row = session.query(OkugakiRow).filter(
            _owned_by(owner, OkugakiRow.user_id),
            OkugakiRow.idempotency_key == idempotency_key,
        ).first()
        return _okugaki_to_dict(row) if row is not None else None


def delete_okugaki(user_id: str, okugaki_id: str) -> bool:
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        row = session.query(OkugakiRow).filter(
            OkugakiRow.id == okugaki_id,
            _writable_by(actor, OkugakiRow.user_id),
        ).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True



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

_SINGLE_USER_SETTING_KEY = "single_user"


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
    stored = _read_app_setting(_SINGLE_USER_SETTING_KEY) or {}
    pinned = stored.get("user_id")
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
    _write_app_setting(_SINGLE_USER_SETTING_KEY, {**stored, "user_id": user_id})
    return user


def single_user_pinned_id() -> str | None:
    """The pinned account id, without resolving or writing one."""
    return (_read_app_setting(_SINGLE_USER_SETTING_KEY) or {}).get("user_id")


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
    stored = _read_app_setting(_SINGLE_USER_SETTING_KEY) or {}
    _write_app_setting(_SINGLE_USER_SETTING_KEY, {**stored, "user_id": user_id})
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


def get_render_limit_settings() -> dict:
    return normalize_limits(_read_app_setting(_RENDER_LIMIT_SETTINGS_KEY))


def update_render_limit_settings(settings: dict) -> dict:
    """Merge a partial update over what is stored and normalize the result.

    Rounding happens before the write, so what comes back is what took effect --
    a caller that sent a self-contradicting set gets the corrected one, not its
    own input echoed.
    """
    current = get_render_limit_settings()
    if isinstance(settings, dict):
        current.update(
            {key: value for key, value in settings.items() if key in current}
        )
    clean = normalize_limits(current)
    return _write_app_setting(_RENDER_LIMIT_SETTINGS_KEY, clean)


def get_output_save_settings() -> dict:
    return _normalize_output_save_settings(_read_app_setting(_OUTPUT_SAVE_SETTINGS_KEY))


def update_output_save_settings(enabled: bool, output_dir: str, png_size: int) -> dict:
    clean = _normalize_output_save_settings({"enabled": enabled, "output_dir": output_dir, "png_size": png_size})
    return _write_app_setting(_OUTPUT_SAVE_SETTINGS_KEY, clean)


def _normalize_thumbnail_settings(settings: dict | None) -> dict:
    clean = dict(_THUMBNAIL_DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return clean
    if "hidpi" in settings:
        clean["hidpi"] = bool(settings["hidpi"])
    if "workers" in settings:
        try:
            workers = int(settings["workers"])
        except (TypeError, ValueError):
            workers = clean["workers"]
        clean["workers"] = max(THUMBNAIL_WORKERS_MIN, min(THUMBNAIL_WORKERS_MAX, workers))
    return clean


def get_thumbnail_settings() -> dict:
    return _normalize_thumbnail_settings(_read_app_setting(_THUMBNAIL_SETTINGS_KEY))


def update_thumbnail_settings(hidpi: bool, workers: int) -> dict:
    clean = _normalize_thumbnail_settings({"hidpi": hidpi, "workers": workers})
    return _write_app_setting(_THUMBNAIL_SETTINGS_KEY, clean)


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
    create_sqlite_snapshot(source, destination)


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
        "catalog_mode": row.catalog_mode,
        "render_hash":  row.render_hash,
        "render_hash_short": render_hash_short(row.render_hash),
        "trashed":      bool(row.trashed),
        "starred":      bool(row.starred),
        "for_revision": bool(row.for_revision),
        # bool(), not the stored integer: a client reading `0`/`1` as truth is
        # reading a value SQLite is free to hand back as a string, and `bool("0")`
        # is True. The two keys always ride together -- the bit says whether the
        # work is open, the group says to whom, and either alone is unreadable.
        "for_share":    bool(row.for_share),
        "share_group_id": row.share_group_id,
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
    # Absent, not null: no key means the work was drawn before the column
    # existed, and "none" means a writer said the stage held. A reader that got
    # NULL for both could not tell an unrecorded work from a sound one.
    if row.compose_fallback is not None:
        item["compose_fallback"] = row.compose_fallback
    if row.interpretation_seed is not None:
        item["interpretation_seed"] = row.interpretation_seed
    if row.seed_text is not None:
        item["seed_text"] = row.seed_text
    if row.sketch_text is not None:
        item["sketch_text"] = row.sketch_text
    if row.sketch_grain is not None:
        item["sketch_grain"] = row.sketch_grain
    # Absent, not null: a reader that receives no key is looking at a work drawn
    # before the column existed, and that is not the same as "off".
    if row.sketch_state is not None:
        item["sketch_state"] = row.sketch_state
    # Absent, not null, for the same reason: no key means "drawn before the
    # limits were recorded", which is not "drawn at the defaults".
    if row.render_limits is not None:
        try:
            stored = json.loads(row.render_limits)
        except json.JSONDecodeError:
            stored = None
        if isinstance(stored, dict):
            item["render_limits"] = stored
    return item


def _rows_to_dicts_with_lineage(session, rows: list[HistoryRow], actor: dict | None = None) -> list[dict]:
    """Attach edge provenance while keeping lineage_edges as the source of truth.

    `actor` marks the works that reached this listing through someone else's
    permission -- a group scope or a grant -- rather than by being the caller's
    own. Without the mark, another person's work sits in the listing looking
    exactly like one of yours, and the first thing anyone does with a listing is
    select and delete from it.

    Set only when true, so `response_model_exclude_none` keeps it off the wire
    for the ordinary case of a person looking at their own works.
    """
    items = [_row_to_dict(row) for row in rows]
    if actor is not None:
        for item, row in zip(items, rows):
            if row.user_id != actor["id"]:
                item["shared"] = True
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
        catalog_mode=item.get("catalog_mode"),
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
        # Carried through, never derived: an absent key means the writer said
        # nothing, and guessing "none" here would put a claim in the row that
        # nobody made.
        compose_fallback=item.get("compose_fallback"),
        interpretation_seed=str(item.get("interpretation_seed")) if item.get("interpretation_seed") is not None else None,
        seed_text=item.get("seed_text"),
        sketch_text=item.get("sketch_text"),
        sketch_grain=item.get("sketch_grain"),
        # Carried through, never derived here: an import restores what the
        # exporting database recorded, and an old export legitimately has none.
        sketch_state=item.get("sketch_state"),
        render_limits=json.dumps(item.get("render_limits"), ensure_ascii=False, sort_keys=True) if isinstance(item.get("render_limits"), dict) else None,
        # A new work is closed, and the destination stays NULL rather than being
        # filled with the author's group: a work nobody opened has no readers, and
        # writing the group here would make "closed" and "open to my own group"
        # look the same in the table.
        render_hash=render_hash, trashed=0, starred=0, for_revision=0, for_share=0, note=item.get("note"),
        score_pre_coerce=json.dumps(item.get("score_pre_coerce"), ensure_ascii=False) if item.get("score_pre_coerce") is not None else None,
        coerce_trace_version=item.get("coerce_trace_version"), coerce_catalog_digest=item.get("coerce_catalog_digest"),
        coerce_trace=json.dumps(item.get("coerce_trace"), ensure_ascii=False) if item.get("coerce_trace") is not None else None,
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
    actor = _actor_of(item["user_id"])
    with SessionLocal() as session:
        idempotency_key = item.get("idempotency_key")
        if idempotency_key:
            existing = session.query(HistoryRow).filter(
                _owned_by(actor, HistoryRow.user_id),
                HistoryRow.idempotency_key == idempotency_key,
            ).first()
            if existing is not None:
                result = _row_to_dict(existing)
                result["_idempotent_replay"] = True
                return result
        if parent_node_id:
            parent = session.query(LineageNodeRow).filter(
                LineageNodeRow.id == parent_node_id,
                _readable_node(actor),
                LineageNodeRow.state != "tombstone",
            ).first()
            if parent is None:
                raise ValueError("lineage parent not found")
            node.root_node_id = parent.root_node_id or parent.id
        row.idempotency_key = idempotency_key
        if item.get("coerce_catalog_digest") and item.get("coerce_catalog_snapshot") is not None:
            digest = item["coerce_catalog_digest"]
            trace_version = item.get("coerce_trace_version") or 1
            snapshot_json = json.dumps(
                item["coerce_catalog_snapshot"], ensure_ascii=False, separators=(",", ":")
            )
            if sha256(snapshot_json.encode("utf-8")).hexdigest() != digest:
                raise ValueError("coerce catalog digest does not match its snapshot bytes")
            catalog = session.get(CoerceTraceCatalogRow, digest)
            if catalog is None:
                session.add(
                    CoerceTraceCatalogRow(
                        digest=digest,
                        trace_version=trace_version,
                        snapshot_json=snapshot_json,
                    )
                )
            elif (
                catalog.trace_version != trace_version
                or catalog.snapshot_json != snapshot_json
            ):
                raise ValueError("coerce catalog digest does not match its immutable snapshot")
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
                _owned_by(actor, HistoryRow.user_id),
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
        # Grants naming this organisation outlive it otherwise, and a later group
        # created with the same id would inherit them.
        session.query(HistoryAclRow).filter(
            HistoryAclRow.subject_type == "org_group", HistoryAclRow.subject_id == group_id
        ).delete(synchronize_session=False)
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
    if has_permission_group(actor, "admins"):
        return list_users()
    if has_permission_group(actor, "leaders") and actor.get("group_id"):
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


def list_group_peers(user_id: str) -> list[dict]:
    """The caller's own organisation group, as names to share a work with.

    Id and display name only, and only the caller's own group. Sharing needs a
    way to name a person, and the account listing is a member manager's -- the
    owner of a work usually is not one, so before this they had to be told a raw
    id and paste it. Opening the whole listing instead would put every name on
    the server in front of everyone, to solve a problem that stops at the
    organisation boundary.

    An account with no organisation group gets an empty list, not everyone.
    """
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if row is None or not row.group_id:
            return []
        peers = (
            session.query(UserAccountRow)
            .filter(
                UserAccountRow.group_id == row.group_id,
                UserAccountRow.id != user_id,   # sharing with oneself is not a thing
            )
            .order_by(UserAccountRow.username.asc())
            .all()
        )
        return [{"id": peer.id, "username": peer.username} for peer in peers]


def add_user(username: str, email: str, password: str, permission_groups: list[str], group_id: str | None) -> dict:
    username = username.strip()
    email = email.strip()
    if not username:
        raise ValueError("username is required")
    if not email:
        raise ValueError("email is required")
    wanted = _normalize_permission_groups(permission_groups)
    row = UserAccountRow(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        password_hash=_hash_password(password),
        role=_derived_role(wanted),
        group_id=group_id,
        at=_now_ms(),
    )
    with SessionLocal() as session:
        if group_id and not session.get(UserGroupRow, group_id):
            raise ValueError("group not found")
        session.add(row)
        session.commit()
        _set_permission_groups(session, row, wanted)
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
    permission_groups: list[str] | None = None,
    group_id: str | None | object = _UNSET,
    actor: dict | None = None,
) -> dict | None:
    with SessionLocal() as session:
        query = session.query(UserAccountRow).filter(UserAccountRow.id == user_id)
        if actor is not None and not has_permission_group(actor, "admins"):
            if not has_permission_group(actor, "leaders") or not actor.get("group_id"):
                return None
            query = query.filter(
                UserAccountRow.group_id == actor["group_id"],
                _holds_no_elevated_group(session),
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
        if permission_groups is not None:
            _set_permission_groups(session, row, permission_groups)
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
    tooltips_enabled: bool | None = None,
    download_folder_enabled: bool | None = None,
    download_folder_name: str | None = None,
    settings_tab: str | None = None,
    model_settings: dict | None = None,
    history_strip_fields: list | None = None,
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
    if tooltips_enabled is not None and not isinstance(tooltips_enabled, bool):
        raise ValueError("invalid tooltips enabled setting")
    if download_folder_enabled is not None and not isinstance(download_folder_enabled, bool):
        raise ValueError("invalid download folder setting")
    if download_folder_name is not None and len(download_folder_name) > 240:
        raise ValueError("download folder name is too long")
    if settings_tab is not None and settings_tab not in _SETTINGS_TABS:
        raise ValueError("invalid settings tab")
    # Refused rather than quietly trimmed: a caller asking for a fifth field or
    # for three at once has misread the control, and silently storing two of the
    # three would put a choice on screen that nobody made.
    if history_strip_fields is not None and (
        not isinstance(history_strip_fields, list)
        or any(field not in _HISTORY_STRIP_FIELDS for field in history_strip_fields)
        or len(set(history_strip_fields)) != len(history_strip_fields)
        or len(history_strip_fields) > _HISTORY_STRIP_FIELD_LIMIT
    ):
        raise ValueError("invalid history strip fields")
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
        if history_strip_fields is not None:
            # Stored in the declared order, not the order they were ticked, so
            # the strip reads the same however the reader got there.
            row.history_strip_fields = json.dumps(
                normalize_history_strip_fields(history_strip_fields), ensure_ascii=False
            )
        if tooltips_enabled is not None:
            row.tooltips_enabled = tooltips_enabled
        if download_folder_enabled is not None:
            row.download_folder_enabled = download_folder_enabled
        if download_folder_name is not None:
            # An empty name clears it: the user dropped the folder.
            row.download_folder_name = download_folder_name.strip() or None
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


def _acl_to_dict(row: HistoryAclRow) -> dict:
    return {
        "id": row.id,
        "history_id": row.history_id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "permission": row.permission,
        "at": row.at,
    }


def _may_share(actor: dict, session, item_id: str) -> bool:
    """Only the owner and an admin may hand a work to someone else.

    Not everyone who can READ it: a leader reads their organisation's works, and
    if reading were enough to grant, the leader could pass any of them outside
    the organisation and the scope would stop meaning anything.
    """
    if has_permission_group(actor, "admins"):
        return session.query(HistoryRow).filter(HistoryRow.id == item_id).first() is not None
    return (
        session.query(HistoryRow)
        .filter(HistoryRow.id == item_id, _owned_by(actor, HistoryRow.user_id))
        .first()
        is not None
    )


def list_history_acl(user_id: str, item_id: str) -> list[dict] | None:
    """The guest list of one work, or None when the caller may not see it."""
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        if not _may_share(actor, session, item_id):
            return None
        rows = (
            session.query(HistoryAclRow)
            .filter(HistoryAclRow.history_id == item_id)
            .order_by(HistoryAclRow.at.asc(), HistoryAclRow.id.asc())
            .all()
        )
        return [_acl_to_dict(row) for row in rows]


def _validated_acl_entries(entries: list[dict]) -> list[tuple[str, str, str]]:
    clean: dict[tuple[str, str], tuple[str, str, str]] = {}
    for entry in entries:
        subject_type = str(entry.get("subject_type") or "")
        subject_id = str(entry.get("subject_id") or "")
        permission = str(entry.get("permission") or "")
        if subject_type not in ACL_SUBJECT_TYPES:
            raise ValueError(f"invalid subject_type: {subject_type}")
        if permission not in ACL_PERMISSIONS:
            raise ValueError(f"invalid permission: {permission}")
        if not subject_id:
            raise ValueError("subject_id is required")
        # Last entry wins rather than raising: a caller that names the same
        # subject twice is stating one intention clumsily, not two.
        clean[(subject_type, subject_id)] = (subject_type, subject_id, permission)
    return list(clean.values())


def replace_history_acl(user_id: str, item_id: str, entries: list[dict]) -> list[dict] | None:
    """Set the whole guest list at once. Absent subjects lose their access.

    A whole-list write rather than a patch: the caller sends what the list should
    be, so revoking is expressible. A patch API would need a separate delete verb
    and a client that forgot it would silently never revoke anything.
    """
    wanted = _validated_acl_entries(entries)
    actor = _actor_of(user_id)
    now = _now_ms()
    with SessionLocal() as session:
        if not _may_share(actor, session, item_id):
            return None
        existing = {
            (row.subject_type, row.subject_id): row
            for row in session.query(HistoryAclRow).filter(HistoryAclRow.history_id == item_id).all()
        }
        for subject_type, subject_id, permission in wanted:
            row = existing.pop((subject_type, subject_id), None)
            if row is None:
                session.add(HistoryAclRow(
                    id=str(uuid.uuid4()), history_id=item_id, subject_type=subject_type,
                    subject_id=subject_id, permission=permission, at=now,
                ))
            elif row.permission != permission:
                row.permission = permission
                row.at = now
        for row in existing.values():
            session.delete(row)
        session.commit()
    return list_history_acl(user_id, item_id)


def grant_history_acl(user_id: str, item_id: str, subject_type: str, subject_id: str, permission: str) -> list[dict] | None:
    """Add or raise one entry, leaving the rest of the list alone."""
    current = list_history_acl(user_id, item_id)
    if current is None:
        return None
    entries = [
        entry for entry in current
        if not (entry["subject_type"] == subject_type and entry["subject_id"] == subject_id)
    ]
    entries.append({"subject_type": subject_type, "subject_id": subject_id, "permission": permission})
    return replace_history_acl(user_id, item_id, entries)


def revoke_history_acl(user_id: str, item_id: str, subject_type: str, subject_id: str) -> list[dict] | None:
    """Drop one entry, leaving the rest of the list alone."""
    current = list_history_acl(user_id, item_id)
    if current is None:
        return None
    entries = [
        entry for entry in current
        if not (entry["subject_type"] == subject_type and entry["subject_id"] == subject_id)
    ]
    return replace_history_acl(user_id, item_id, entries)


def _delete_acl_for_histories(session, history_ids: list[str]) -> None:
    """Drop the guest lists of works that are going away.

    An orphaned row is not merely untidy. Ids are handed out by uuid4 here, but
    an import or a restore can reintroduce one, and a stale grant would then
    attach to whatever took the id -- someone else's work, shared with someone
    who was never told.
    """
    if not history_ids:
        return
    session.query(HistoryAclRow).filter(HistoryAclRow.history_id.in_(history_ids)).delete(
        synchronize_session=False
    )


def delete_user(user_id: str, *, cascade: bool = False, actor: dict | None = None) -> bool:
    with SessionLocal() as session:
        query = session.query(UserAccountRow).filter(UserAccountRow.id == user_id)
        if actor is not None and not has_permission_group(actor, "admins"):
            if not has_permission_group(actor, "leaders") or not actor.get("group_id"):
                return False
            query = query.filter(
                UserAccountRow.group_id == actor["group_id"],
                _holds_no_elevated_group(session),
            )
        row = query.first()
        if not row:
            return False
        # The account being deleted, not the one doing the deleting: the cascade
        # selects by ownership so that widening what an admin may write never
        # widens what one deletion removes.
        target_owner = _owner_actor(user_id)
        if not cascade:
            if session.query(HistoryRow).filter(_owned_by(target_owner, HistoryRow.user_id)).first():
                raise ValueError("user has history")
        else:
            _delete_acl_for_histories(session, [
                item_id for item_id, in
                session.query(HistoryRow.id).filter(_owned_by(target_owner, HistoryRow.user_id))
            ])
            session.query(HistoryRow).filter(_owned_by(target_owner, HistoryRow.user_id)).delete()
        # Both directions: the works this account owned, above, and the grants
        # that named this account as a guest, here. Only the first is a cascade;
        # the second would otherwise survive on other people's works.
        session.query(HistoryAclRow).filter(
            HistoryAclRow.subject_type == "user", HistoryAclRow.subject_id == user_id
        ).delete(synchronize_session=False)
        session.query(OkugakiRow).filter(_owned_by(target_owner, OkugakiRow.user_id)).delete()
        session.query(UserSessionRow).filter(UserSessionRow.user_id == user_id).delete()
        session.query(ExternalIdentityRow).filter(ExternalIdentityRow.user_id == user_id).delete()
        session.query(UnreadWordRow).filter(UnreadWordRow.user_id == user_id).delete()
        session.query(LineageEdgeRow).filter(_owned_by(target_owner, LineageEdgeRow.user_id)).delete()
        session.query(LineageNodeRow).filter(_owned_by(target_owner, LineageNodeRow.user_id)).delete()
        session.query(UserPermissionGroupRow).filter(UserPermissionGroupRow.user_id == user_id).delete()
        session.delete(row)
        session.commit()
        return True


def _fts_match_query(search: str) -> str:
    return '"' + search.replace('"', '""') + '"'


# A whole render hash, with the version prefix (`rh3:`) or without it: a reader
# who trims the prefix off still means the same work. The prefix is matched
# loosely rather than spelled `rh3` so that a later version does not silently
# stop being searchable.
_WHOLE_RENDER_HASH = re.compile(r"(?:[a-z0-9]+:)?[0-9a-f]{64}", re.IGNORECASE)


def _is_render_hash_suffix_search(search: str) -> bool:
    """Text that can only be a render hash, and so is matched against the end of one.

    Two shapes arrive here. The four characters the UI prints on a work's chip,
    and the whole hash its copy button puts on the clipboard -- which is what a
    reader pastes back into the search box, and which used to reach the
    full-text path instead and find nothing.

    Both are matched as a suffix: that is what the short form is, and the long
    form is trivially one.
    """
    if len(search) == 4 and search.isascii() and search.isalnum():
        return True
    return bool(_WHOLE_RENDER_HASH.fullmatch(search))


def _history_search_clause(search: str):
    pattern = f"%{search}%"
    clauses = [
        HistoryRow.input.ilike(pattern),
        HistoryRow.ddl.ilike(pattern),
        HistoryRow.stage1_model.ilike(pattern),
        HistoryRow.stage2_model.ilike(pattern),
        HistoryRow.catalog_id.ilike(pattern),
    ]
    if _is_render_hash_suffix_search(search):
        clauses.append(HistoryRow.render_hash.ilike(f"%{search}"))
    return or_(*clauses)


def _use_history_fts(search: str) -> bool:
    return (
        _HISTORY_FTS_ENABLED
        and engine.dialect.name == "sqlite"
        and len(search) >= 3
        and not _is_render_hash_suffix_search(search)
    )


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
    visible, visible_params = _readable_sql(actor, "h.user_id", "h.id")
    params = {
        **visible_params,
        "trashed": 1 if trashed else 0,
        "match": _fts_match_query(search),
        "limit": limit,
        "offset": offset,
    }
    starred_clause = "AND h.starred = 1" if starred else ""
    # Both marks filter at once and independently: asking for starred and for
    # for_revision means both, not either.
    for_revision_clause = "AND h.for_revision = 1" if for_revision else ""
    # The third mark narrows the same way: AND, not OR. Asking for the bundle
    # asks for the works in it, not for the works in it plus one's own.
    for_share_clause = "AND h.for_share = 1" if for_share else ""
    total = session.execute(
        text(
            f"""
            SELECT count(h.id)
            FROM history h
            JOIN history_fts ON history_fts.rowid = h.rowid
            WHERE {visible}
              AND h.trashed = :trashed
              AND h.history_visibility = 'normal'
              {starred_clause}
              {for_revision_clause}
              {for_share_clause}
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
                WHERE {visible}
                  AND h.trashed = :trashed
                  AND h.history_visibility = 'normal'
                  {starred_clause}
                  {for_revision_clause}
                  {for_share_clause}
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
    items = _rows_to_dicts_with_lineage(session, rows, actor)
    return sorted(items, key=lambda item: order[item["id"]]), int(total)


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
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        query = session.query(HistoryRow).filter(
            _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
            HistoryRow.trashed == (1 if trashed else 0),
            HistoryRow.history_visibility == "normal",
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        if for_revision:
            query = query.filter(HistoryRow.for_revision == 1)
        if for_share:
            query = query.filter(HistoryRow.for_share == 1)
        search = query_text.strip()
        if search and _use_history_fts(search):
            return _list_items_with_fts(
                session, actor, offset, limit, trashed, search, starred, for_revision, for_share
            )
        if search:
            query = query.filter(_history_search_clause(search))
        total: int = query.with_entities(func.count(HistoryRow.id)).scalar() or 0
        rows = (
            query
            .order_by(HistoryRow.at.desc(), HistoryRow.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return _rows_to_dicts_with_lineage(session, rows, actor), total


def list_state(user_id: str, trashed: bool = False) -> tuple[int, int | None, str | None]:
    """How many works the caller may see, and which one is newest.

    This is what a client polls when it only wants to know whether the listing
    it already holds is still current. It reads no drawing: the count comes from
    the database and the newest work is fetched as two columns, so a caller
    asking every twelve seconds costs a few hundred bytes rather than the whole
    gallery.

    The three filters are `list_items`' three, in its order. Sharing decides who
    may see a work, so a state that judged visibility its own way would let
    somebody else's private work move the count and pull the whole listing back
    across the wire.

    The newest work is the listing's first row, not `max(id)`: the listing is
    ordered by `at DESC, id ASC`, so when two works share a millisecond the one
    the listing shows first is the one reported here. Reporting `max(at)` alone
    would miss a second save inside the same millisecond entirely.
    """
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        query = session.query(HistoryRow).filter(
            _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
            HistoryRow.trashed == (1 if trashed else 0),
            HistoryRow.history_visibility == "normal",
        )
        total: int = query.with_entities(func.count(HistoryRow.id)).scalar() or 0
        newest = (
            query
            .with_entities(HistoryRow.id, HistoryRow.at)
            .order_by(HistoryRow.at.desc(), HistoryRow.id.asc())
            .first()
        )
        if newest is None:
            return int(total), None, None
        return int(total), int(newest.at), str(newest.id)


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
    """List deterministic history groups, paginated by lineage rather than artwork.

    `min_item_count` drops lineages with fewer members than that. The filter has
    to run here rather than on the returned page: a caller that threw away the
    one-work groups after the fact would show fewer than `limit` cards per page
    and would disagree with `total`.
    """
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        query = (
            session.query(HistoryRow)
            .join(LineageNodeRow, LineageNodeRow.id == HistoryRow.lineage_node_id)
            .filter(
                _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                _readable_node(actor),
                HistoryRow.trashed == (1 if trashed else 0),
                HistoryRow.history_visibility == "normal",
            )
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        if for_revision:
            query = query.filter(HistoryRow.for_revision == 1)
        if for_share:
            query = query.filter(HistoryRow.for_share == 1)
        search = query_text.strip()
        if search:
            query = query.filter(_history_search_clause(search))
        root_id = func.coalesce(LineageNodeRow.root_node_id, LineageNodeRow.id)
        grouped = query.with_entities(
            root_id.label("root_node_id"),
            func.count(HistoryRow.id).label("item_count"),
            func.sum(case((HistoryRow.starred == 1, 1), else_=0)).label("starred_count"),
            func.sum(case((HistoryRow.for_revision == 1, 1), else_=0)).label("for_revision_count"),
            func.max(HistoryRow.at).label("latest_at"),
        ).group_by(root_id)
        if min_item_count > 1:
            grouped = grouped.having(func.count(HistoryRow.id) >= min_item_count)
        aggregates = grouped.subquery()
        # total counts the same subquery, so the page and the count cannot disagree.
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
            for item in _rows_to_dicts_with_lineage(session, representative_rows, actor)
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
                "for_revision_count": int(row.for_revision_count or 0),
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
    for_revision: bool = False,
    for_share: bool = False,
) -> tuple[list[dict], int]:
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        # The root is looked up without a readability test, and the members
        # below are filtered with one. A lineage started by someone else and
        # continued here has THEIR work as its root: requiring the root to be
        # readable would close the group on its own later members, who would see
        # a card in the listing that opens onto nothing. Nothing about the root
        # is returned from this lookup -- only the fact that the id names a root.
        root = session.get(LineageNodeRow, root_node_id)
        if root is None or (root.root_node_id or root.id) != root_node_id:
            return [], 0
        query = (
            session.query(HistoryRow)
            .join(LineageNodeRow, LineageNodeRow.id == HistoryRow.lineage_node_id)
            .filter(
                _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                _readable_node(actor),
                # coalesce, not a bare ==, and the same expression list_lineage_groups
                # groups by: the root_node_id column was added by migration without a
                # backfill, so a root node created before it holds NULL and would not
                # match its own id. Such a lineage counted its own root in the group
                # aggregate but dropped it from the member list.
                func.coalesce(LineageNodeRow.root_node_id, LineageNodeRow.id) == root_node_id,
                HistoryRow.trashed == (1 if trashed else 0),
                HistoryRow.history_visibility == "normal",
            )
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        if for_revision:
            query = query.filter(HistoryRow.for_revision == 1)
        if for_share:
            query = query.filter(HistoryRow.for_share == 1)
        search = query_text.strip()
        if search:
            query = query.filter(_history_search_clause(search))
        total: int = query.with_entities(func.count(HistoryRow.id)).scalar() or 0
        rows = query.order_by(HistoryRow.at.desc(), HistoryRow.id.asc()).offset(offset).limit(limit).all()
        return _rows_to_dicts_with_lineage(session, rows, actor), total


def item_position(
    user_id: str,
    item_id: str,
    trashed: bool = False,
    starred: bool = False,
    for_revision: bool = False,
    for_share: bool = False,
) -> int | None:
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        target = session.query(HistoryRow).filter(
            _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
            HistoryRow.id == item_id,
            HistoryRow.trashed == (1 if trashed else 0),
            HistoryRow.history_visibility == "normal",
        ).first()
        if target is None or (starred and not target.starred):
            return None
        if for_revision and not target.for_revision:
            return None
        if for_share and not target.for_share:
            return None
        query = session.query(func.count(HistoryRow.id)).filter(
            _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
            HistoryRow.trashed == (1 if trashed else 0),
            HistoryRow.history_visibility == "normal",
            or_(
                HistoryRow.at > target.at,
                and_(HistoryRow.at == target.at, HistoryRow.id < target.id),
            ),
        )
        if starred:
            query = query.filter(HistoryRow.starred == 1)
        if for_revision:
            query = query.filter(HistoryRow.for_revision == 1)
        if for_share:
            query = query.filter(HistoryRow.for_share == 1)
        return int(query.scalar() or 0)


def set_item_starred(user_id: str, item_id: str, starred: bool, note: str | None = None) -> dict | None:
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        row = (
            session.query(HistoryRow)
            .filter(_writable_by(actor, HistoryRow.user_id, HistoryRow.id), HistoryRow.id == item_id)
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


def set_item_for_revision(user_id: str, item_id: str, for_revision: bool) -> dict | None:
    """Raise or drop the revision mark. Independent of starred: neither reads the other."""
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        row = (
            session.query(HistoryRow)
            .filter(_writable_by(actor, HistoryRow.user_id, HistoryRow.id), HistoryRow.id == item_id)
            .first()
        )
        if not row:
            return None
        row.for_revision = 1 if for_revision else 0
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def set_item_for_share(
    user_id: str, item_id: str, for_share: bool, share_group_id: str | None = None
) -> dict | None:
    """Open a work to an organisation group, or close it again.

    Who may do it is `_writable_by`, the same test starring uses -- opening a
    work is an act of its owner, not of everyone who can read it. `None` means
    the caller may not write this work, and the route answers 404 rather than
    403: telling a caller that a work they may not touch exists is itself a
    disclosure.

    Raising the bit with no destination names the owner's own organisation
    group, the way a new file takes the group of whoever made it. Naming
    somebody else's group is an administrator's act, because a member who could
    do it would be able to hand their organisation's work to any other.

    Dropping the bit leaves the destination where it is: `chmod g-r` does not
    forget the group, and clearing it would silently re-aim the work the next
    time the bit went up.
    """
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        row = (
            session.query(HistoryRow)
            .filter(_writable_by(actor, HistoryRow.user_id, HistoryRow.id), HistoryRow.id == item_id)
            .first()
        )
        if not row:
            return None
        if not for_share:
            row.for_share = 0
            session.commit()
            session.refresh(row)
            return _row_to_dict(row)
        # Only a NAMED group is checked, not the one already on the row. `chmod
        # g+r` asks nothing of the group the file is in; re-opening a work its
        # owner had opened before is the same act, and requiring administrator
        # rights for it would make the destination unrepeatable by the one person
        # who chose it.
        if share_group_id and share_group_id != actor.get("group_id") and not has_permission_group(actor, "admins"):
            raise PermissionError("only administrators may share a work outside their own group")
        owner_group_id = _actor_of(row.user_id)["group_id"] if row.user_id else None
        # The destination the work already carries wins over the owner's own: it
        # is what "the bit went down and came back up" has to mean, and a fresh
        # work has none, so the owner's group is what fills the blank.
        target_group = share_group_id or row.share_group_id or owner_group_id
        if not target_group:
            raise ValueError("this work has no organisation group to be shared with")
        if session.get(UserGroupRow, target_group) is None:
            raise ValueError(f"no such organisation group: {target_group}")
        row.for_share = 1
        row.share_group_id = target_group
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def history_render_hashes() -> list[tuple[str, str | None]]:
    """Every stored work and the render hash of the SVG it holds.

    Unscoped, unlike get_items(): the only caller is the thumbnail rebuild,
    which the settings screen runs for the whole installation and which returns
    no work to anybody -- it writes pictures into the derived store, and every
    read of that store goes back through the ordinary visibility rules.
    """
    with SessionLocal() as session:
        rows = session.execute(select(HistoryRow.id, HistoryRow.render_hash)).all()
    return [(str(item_id), render_hash) for item_id, render_hash in rows]


def history_svgs(ids: list[str]) -> dict[str, str]:
    """The stored SVG of each id, for the thumbnail rebuild. Unscoped, as above.

    Taken in batches by the caller: one work's SVG averages about a megabyte,
    so the whole table at once is the very cost this exists to remove.
    """
    if not ids:
        return {}
    with SessionLocal() as session:
        rows = session.execute(
            select(HistoryRow.id, HistoryRow.svg).where(HistoryRow.id.in_(ids))
        ).all()
    return {str(item_id): (svg or "") for item_id, svg in rows}


def get_items(user_id: str, ids: list[str]) -> list[dict]:
    """Fetch works by id, in the order asked for, skipping the trash.

    Trashed works are addressable by id but are not a thing to act on: every
    caller here exports, rebuilds, or inspects a work. The trash view has its
    own listing (`list_items(trashed=True)`) and cannot load a work onto the
    canvas, so nothing legitimate is lost by not answering for them here.
    Without this filter an id sent straight to the export endpoints put a
    trashed work into the output (ledger I-094).
    """
    if not ids:
        return []
    order = {item_id: index for index, item_id in enumerate(ids)}
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        rows = (
            session.query(HistoryRow)
            .filter(
                _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                HistoryRow.id.in_(ids),
                HistoryRow.trashed == 0,
            )
            .all()
        )
        items = _rows_to_dicts_with_lineage(session, rows, actor)
        return sorted(items, key=lambda item: order.get(item["id"], len(order)))


def _neighbor_score(raw: str | None) -> dict:
    try:
        score = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    return score if isinstance(score, dict) else {}


def list_neighbor_candidates(user_id: str, item_id: str, *, limit: int = 10_000) -> list[dict]:
    """Load only fields used by similarity ranking, avoiding SVG and lineage hydration."""
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        rows = (
            session.query(HistoryRow.id, HistoryRow.at, HistoryRow.score)
            .filter(
                _readable_by(actor, HistoryRow.user_id, HistoryRow.id),
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
    # Ownership, not write permission: "erase everything of mine" must keep
    # meaning one account's works however wide writing becomes.
    owner = _owner_actor(user_id)
    with SessionLocal() as session:
        _delete_acl_for_histories(session, [
            item_id for item_id, in
            session.query(HistoryRow.id).filter(_owned_by(owner, HistoryRow.user_id))
        ])
        session.query(OkugakiRow).filter(_owned_by(owner, OkugakiRow.user_id)).delete()
        session.query(LineageEdgeRow).filter(_owned_by(owner, LineageEdgeRow.user_id)).delete()
        session.query(LineageNodeRow).filter(_owned_by(owner, LineageNodeRow.user_id)).delete()
        session.query(HistoryRow).filter(_owned_by(owner, HistoryRow.user_id)).delete()
        session.commit()


def trash_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        count = (
            session.query(HistoryRow)
            .filter(_writable_by(actor, HistoryRow.user_id, HistoryRow.id), HistoryRow.id.in_(ids), HistoryRow.trashed == 0)
            .update({HistoryRow.trashed: 1}, synchronize_session=False)
        )
        session.commit()
        return count


def restore_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        count = (
            session.query(HistoryRow)
            .filter(_writable_by(actor, HistoryRow.user_id, HistoryRow.id), HistoryRow.id.in_(ids), HistoryRow.trashed == 1)
            .update({HistoryRow.trashed: 0}, synchronize_session=False)
        )
        session.commit()
        return count


def delete_items(user_id: str, ids: list[str], *, require_trashed: bool = False) -> int:
    if not ids:
        return 0
    actor = _actor_of(user_id)
    with SessionLocal() as session:
        query = session.query(HistoryRow).filter(
            _writable_by(actor, HistoryRow.user_id, HistoryRow.id),
            HistoryRow.id.in_(ids),
        )
        if require_trashed:
            query = query.filter(HistoryRow.trashed == 1)
        rows = query.all()
        now = _now_ms()
        node_ids = [row.lineage_node_id for row in rows if row.lineage_node_id]
        if node_ids:
            # No owner test on these two. They follow `rows`, which the filter
            # above already authorised, and the nodes and edges belong to the
            # WORK's owner -- who is not the actor once a write grant lets
            # someone else delete it. Re-testing against the actor would match
            # nothing and quietly leave the deleted work's node un-tombstoned,
            # its child still pointing at a parent whose history is gone.
            nodes = session.query(LineageNodeRow).filter(
                LineageNodeRow.id.in_(node_ids),
            ).all()
            for node in nodes:
                node.state = "tombstone"
                node.history_id = None
                node.description_hash = None
                node.render_hash = None
                node.deleted_at = now
            touching = session.query(LineageEdgeRow).filter(
                or_(LineageEdgeRow.parent_node_id.in_(node_ids), LineageEdgeRow.child_node_id.in_(node_ids)),
            ).all()
            for edge in touching:
                edge.metadata_json = "{}"
        _delete_acl_for_histories(session, [row.id for row in rows])
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


def delete_all_trashed_items(user_id: str) -> int:
    # Same reason as delete_all: emptying the trash empties one's own trash.
    owner = _owner_actor(user_id)
    with SessionLocal() as session:
        ids = [
            item_id
            for item_id, in session.query(HistoryRow.id).filter(
                _owned_by(owner, HistoryRow.user_id),
                HistoryRow.trashed == 1,
            )
        ]
    return delete_items(user_id, ids, require_trashed=True)
