CREATE TABLE library_annotations (
    history_id TEXT PRIMARY KEY NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    note TEXT,
    for_revision INTEGER NOT NULL DEFAULT 0 CHECK (for_revision IN (0, 1)),
    for_share INTEGER NOT NULL DEFAULT 0 CHECK (for_share IN (0, 1))
);
CREATE TABLE auxiliary_colophons (
    id TEXT PRIMARY KEY NOT NULL,
    target_node_id TEXT NOT NULL REFERENCES lineage_nodes(id),
    branch_snapshot TEXT NOT NULL,
    model TEXT NOT NULL,
    at INTEGER NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('ja', 'en')),
    generated_body TEXT NOT NULL,
    adopted_body TEXT,
    signature TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    fact_sheet_json TEXT NOT NULL
);
CREATE INDEX index_auxiliary_colophons_target ON auxiliary_colophons (target_node_id, at DESC, id ASC);
CREATE TABLE unread_words (
    id TEXT PRIMARY KEY NOT NULL,
    word TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    frequency INTEGER NOT NULL DEFAULT 1 CHECK (frequency > 0),
    first_at INTEGER NOT NULL,
    last_at INTEGER NOT NULL,
    UNIQUE (word, context)
);
INSERT INTO schema_migrations (identifier) VALUES ('swift-v2-library-annotations');
PRAGMA user_version = 2;
