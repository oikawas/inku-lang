"""Canonical SQLAlchemy ORM schema for Server persistence."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class HistoryRow(Base):
    __tablename__ = "history"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_history_user_idempotency"),)

    id           = Column(String,     primary_key=True)
    user_id      = Column(String,     ForeignKey("user_accounts.id"), nullable=True, index=True)
    at           = Column(BigInteger, nullable=False, index=True)
    input        = Column(Text,       nullable=False, default="")
    ddl          = Column(Text,       nullable=True)  # v1.98: input-side DDL (Stage 1 output / original user text)
    expanded_ddl = Column(Text,       nullable=True)  # v1.98: expanded DDL (Stage 1.5 output = Stage 2 input)
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
    render_wild = Column(String, nullable=True)  # engine 12: "1"/"0"; NULL = recorded before the flag (not OFF)
    composition_seed = Column(String, nullable=True)
    tenkei = Column(String, nullable=True)  # v1.97 scenery level; NULL = recorded before the field
    focus = Column(String, nullable=True)  # v1.98 focus; NULL = selected deterministically from DDL text
    # v2.0 variation. Both NULL means expansion without variation. moved_axes
    # can be recomputed deterministically, so it does not need a column.
    variation_amplitude = Column(String, nullable=True)
    variation_seed = Column(String, nullable=True)
    # v1.98: why Stage 1 used fallback DDL for the work. NULL means normal interpretation.
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

