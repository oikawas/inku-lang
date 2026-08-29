//! Host-neutral Score value types for inku.

#![forbid(unsafe_code)]

pub mod canonical;
pub mod schema;
pub mod types;

pub use canonical::{CANONICAL_SCORE_DIGEST_DOMAIN, canonical_json_bytes, canonical_score_digest};
pub use schema::{SCORE_SCHEMA_DIGEST_DOMAIN, score_schema_bytes, score_schema_digest};
pub use types::*;
