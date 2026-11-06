CREATE TABLE effect_acknowledgements_v9 (
    execution_id TEXT NOT NULL REFERENCES execution_snapshots(id),
    effect_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 0),
    snapshot_sha256 BLOB NOT NULL CHECK (length(snapshot_sha256) = 32),
    acknowledgement BLOB NOT NULL,
    save_payload_sha256 BLOB NOT NULL CHECK (length(save_payload_sha256) = 32),
    PRIMARY KEY (execution_id, effect_id)
);
