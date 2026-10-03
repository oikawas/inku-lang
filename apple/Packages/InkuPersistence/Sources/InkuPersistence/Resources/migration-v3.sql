CREATE TABLE provider_rate_state (
    provider_id TEXT PRIMARY KEY NOT NULL,
    state_json BLOB NOT NULL
);
INSERT INTO schema_migrations (identifier) VALUES ('swift-v3-provider-rate-state');
PRAGMA user_version = 3;
