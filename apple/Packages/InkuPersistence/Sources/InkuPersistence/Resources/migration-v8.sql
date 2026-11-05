ALTER TABLE history ADD COLUMN draw_route TEXT;
ALTER TABLE history ADD COLUMN sketch_requested TEXT;
ALTER TABLE history ADD COLUMN composition_requested TEXT;
ALTER TABLE history ADD COLUMN catalog_mode TEXT;
INSERT INTO schema_migrations (identifier) VALUES ('swift-v8-draw-options');
PRAGMA user_version = 8;
