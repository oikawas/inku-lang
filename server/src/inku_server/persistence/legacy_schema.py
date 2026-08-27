"""Legacy SQLite schema declarations used by the compatibility migration façade."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

# v2.8.0 rename table. `_migrate_columns` rewrites persisted rows through this
# exact mapping; the private naming record preserves the historical rationale.
LINEAGE_KIND_RENAMES = (
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

HISTORY_COLUMN_MIGRATIONS = {
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
LINEAGE_NODE_COLUMN_MIGRATIONS = {
    "root_node_id": "ALTER TABLE lineage_nodes ADD COLUMN root_node_id VARCHAR",
}
USER_ACCOUNT_COLUMN_MIGRATIONS = {
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

HISTORY_INDEX_MIGRATIONS = (
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
LINEAGE_NODE_INDEX_MIGRATIONS = (
    ("ix_lineage_nodes_root_node_id", "CREATE INDEX IF NOT EXISTS ix_lineage_nodes_root_node_id ON lineage_nodes (root_node_id)"),
)


@dataclass(frozen=True)
class LegacyColumnMigrationManifest:
    """Exact declarations consumed by the legacy column coordinator."""

    lineage_kind_renames: tuple[tuple[str, str], ...]
    history_column_migrations: Mapping[str, str]
    lineage_node_column_migrations: Mapping[str, str]
    user_account_column_migrations: Mapping[str, str]
    history_index_migrations: tuple[tuple[str, str], ...]
    lineage_node_index_migrations: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LegacyColumnMigrator:
    """Apply the exact legacy column, row, and index transforms in order."""

    engine: object
    nullcontext_fn: Callable[[object], object]
    inspect_fn: Callable[[object], object]
    text_fn: Callable[[str], object]
    coerce_trace_catalog_table: object
    manifest: LegacyColumnMigrationManifest
    backfill_render_hashes: Callable[[object], object]
    migrate_renamed_catalog_nameplates: Callable[[object], object]
    migrate_history_search: Callable[[object], object]

    def migrate(self, connection=None, *, include_fts: bool = True) -> None:
        manager = self.engine.begin() if connection is None else self.nullcontext_fn(connection)
        with manager as conn:
            try:
                self.coerce_trace_catalog_table.create(bind=conn, checkfirst=True)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("failed to create coerce trace catalog table") from exc
            try:
                inspector = self.inspect_fn(conn)
                existing_history_columns = {
                    col["name"] for col in inspector.get_columns("history")
                }
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
                    conn.execute(
                        self.text_fn(
                            "ALTER TABLE history RENAME COLUMN vary_seed TO composition_seed"
                        )
                    )
                    existing_history_columns.discard("vary_seed")
                    existing_history_columns.add("composition_seed")
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "failed to rename history.vary_seed to composition_seed"
                    ) from exc

            adding_expanded_ddl = "expanded_ddl" not in existing_history_columns
            for column, ddl in self.manifest.history_column_migrations.items():
                if column in existing_history_columns:
                    continue
                try:
                    conn.execute(self.text_fn(ddl))
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
                    conn.execute(
                        self.text_fn(
                            "UPDATE history SET expanded_ddl = ddl, ddl = NULL "
                            "WHERE ddl IS NOT NULL"
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "failed to move legacy history.ddl into expanded_ddl"
                    ) from exc

            try:
                existing_user_columns = {
                    col["name"] for col in inspector.get_columns("user_accounts")
                }
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "failed to inspect user_accounts table columns for migration"
                ) from exc

            has_lineage_nodes = inspector.has_table("lineage_nodes")
            existing_lineage_node_columns = (
                {col["name"] for col in inspector.get_columns("lineage_nodes")}
                if has_lineage_nodes
                else set()
            )
            if has_lineage_nodes:
                for column, ddl in self.manifest.lineage_node_column_migrations.items():
                    if column in existing_lineage_node_columns:
                        continue
                    try:
                        conn.execute(self.text_fn(ddl))
                    except Exception as exc:  # noqa: BLE001
                        raise RuntimeError(
                            f"failed to migrate lineage_nodes.{column}"
                        ) from exc

            for column, ddl in self.manifest.user_account_column_migrations.items():
                if column in existing_user_columns:
                    continue
                try:
                    conn.execute(self.text_fn(ddl))
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"failed to migrate user_accounts.{column}") from exc

            # v2.8.0 moves persisted derivation kinds to the canonical vocabulary.
            # `variation` belongs only to the actual variation operation: four other
            # operations lose that suffix and `hensou` becomes `variation`. Rows are
            # rewritten in place and never removed.
            if inspector.has_table("lineage_edges"):
                for before, after in self.manifest.lineage_kind_renames:
                    try:
                        conn.execute(
                            self.text_fn(
                                "UPDATE lineage_edges SET derivation_kind = :after "
                                "WHERE derivation_kind = :before"
                            ),
                            {"before": before, "after": after},
                        )
                    except Exception as exc:  # noqa: BLE001
                        raise RuntimeError(
                            f"failed to rename derivation kind {before}"
                        ) from exc

            for index_name, ddl in self.manifest.history_index_migrations:
                try:
                    conn.execute(self.text_fn(ddl))
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"failed to create migration index {index_name}"
                    ) from exc
            if has_lineage_nodes:
                for index_name, ddl in self.manifest.lineage_node_index_migrations:
                    try:
                        conn.execute(self.text_fn(ddl))
                    except Exception as exc:  # noqa: BLE001
                        raise RuntimeError(
                            f"failed to create migration index {index_name}"
                        ) from exc
            self.backfill_render_hashes(conn)
            self.migrate_renamed_catalog_nameplates(conn)
            if include_fts:
                self.migrate_history_search(conn)
