ALTER TABLE execution_snapshots ADD COLUMN updated_at INTEGER;
UPDATE execution_snapshots SET updated_at = CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER);
INSERT INTO schema_migrations (identifier) VALUES ('swift-v11-execution-updated-at');
PRAGMA user_version = 11;
