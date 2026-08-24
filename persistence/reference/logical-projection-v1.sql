PRAGMA foreign_keys = ON;

CREATE TABLE history (
    id TEXT PRIMARY KEY NOT NULL,
    at INTEGER NOT NULL,
    input TEXT NOT NULL,
    source_text TEXT,
    ddl TEXT,
    expanded_ddl TEXT,
    score TEXT NOT NULL,
    svg TEXT NOT NULL,
    elapsed_ms INTEGER,
    stage1_model TEXT,
    stage2_model TEXT,
    catalog_id TEXT,
    render_engine_id TEXT,
    render_engine_version TEXT,
    render_color_catalog_id TEXT,
    render_color_catalog_name TEXT,
    render_color_catalog_sub TEXT,
    render_color_profile TEXT,
    render_color_map TEXT,
    render_canvas_aspect TEXT,
    render_canvas_aspect_id TEXT,
    render_canvas_aspect_ratio REAL,
    render_seed TEXT,
    render_wild INTEGER CHECK (render_wild IS NULL OR render_wild IN (0, 1)),
    composition_seed TEXT,
    interpretation_seed TEXT,
    variation_amplitude TEXT,
    variation_seed TEXT,
    seed_text TEXT,
    instruction_lang_requested TEXT,
    instruction_lang_resolved TEXT,
    interpret_fallback TEXT,
    compose_fallback TEXT,
    sketch_text TEXT,
    sketch_grain TEXT,
    sketch_state TEXT,
    render_limits TEXT,
    render_hash TEXT,
    description_hash TEXT,
    starred INTEGER NOT NULL DEFAULT 0 CHECK (starred IN (0, 1)),
    trashed INTEGER NOT NULL DEFAULT 0 CHECK (trashed IN (0, 1)),
    history_visibility TEXT NOT NULL DEFAULT 'normal',
    lineage_node_id TEXT UNIQUE
);
CREATE INDEX index_history_render_hash ON history (render_hash);

CREATE TABLE lineage_nodes (
    id TEXT PRIMARY KEY NOT NULL,
    history_id TEXT UNIQUE REFERENCES history(id),
    state TEXT NOT NULL,
    description_hash TEXT,
    render_hash TEXT,
    at INTEGER NOT NULL,
    deleted_at INTEGER,
    root_node_id TEXT REFERENCES lineage_nodes(id)
);

CREATE TABLE lineage_edges (
    id TEXT PRIMARY KEY NOT NULL,
    parent_node_id TEXT NOT NULL REFERENCES lineage_nodes(id),
    child_node_id TEXT NOT NULL UNIQUE REFERENCES lineage_nodes(id),
    derivation_kind TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    at INTEGER NOT NULL,
    CHECK (parent_node_id <> child_node_id)
);
