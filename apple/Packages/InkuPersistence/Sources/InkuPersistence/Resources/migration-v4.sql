ALTER TABLE library_annotations DROP COLUMN for_share;
INSERT INTO schema_migrations (identifier) VALUES ('swift-v4-remove-export-mark');
PRAGMA user_version = 4;
