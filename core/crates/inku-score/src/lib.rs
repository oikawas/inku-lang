//! Host-neutral Score value types for inku.

#![forbid(unsafe_code)]

pub mod canonical;
pub mod canvas_format;
pub mod compatibility;
pub mod schema;
pub mod types;

pub use canonical::{CANONICAL_SCORE_DIGEST_DOMAIN, canonical_json_bytes, canonical_score_digest};
pub use canvas_format::{
    CANVAS_FORMAT_REGISTRY, CANVAS_FORMAT_REGISTRY_DIGEST_DOMAIN, CANVAS_FORMAT_REGISTRY_ID,
    CanvasFormat, CanvasFormatRegistryValidationError, DEFAULT_CANVAS_FORMAT_ID,
    UNKNOWN_CANVAS_FORMAT_ERROR_CODE, UnknownCanvasFormatError, canvas_format_registry,
    canvas_format_registry_canonical_json_bytes, canvas_format_registry_digest,
    lookup_canvas_format, validate_canvas_format_id, validate_canvas_format_registry,
};
pub use compatibility::read_saved_score_json;
pub use schema::{SCORE_SCHEMA_DIGEST_DOMAIN, score_schema_bytes, score_schema_digest};
pub use types::*;
