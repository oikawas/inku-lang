UPDATE history SET history_visibility = 'normal' WHERE history_visibility = 'lineage_only';
UPDATE lineage_nodes SET state = 'active' WHERE state = 'lineage_only';
INSERT INTO schema_migrations (identifier) VALUES ('swift-v5-show-lineage-works');
PRAGMA user_version = 5;
