DROP TABLE effect_acknowledgements;
ALTER TABLE effect_acknowledgements_v9 RENAME TO effect_acknowledgements;
DELETE FROM execution_snapshots WHERE NOT EXISTS (
    SELECT 1 FROM effect_acknowledgements WHERE execution_id = execution_snapshots.id
);
CREATE INDEX lineage_edges_parent_node_id ON lineage_edges(parent_node_id);
INSERT INTO schema_migrations (identifier) VALUES ('swift-v9-effect-digests');
PRAGMA user_version = 9;
