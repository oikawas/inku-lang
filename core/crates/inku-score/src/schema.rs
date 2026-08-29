//! Canonical identity for the Python-owned raw Score JSON Schema.

use crate::canonical::domain_separated_sha256_digest;

/// ASCII domain separator for canonical Score schema digests.
pub const SCORE_SCHEMA_DIGEST_DOMAIN: &str = "inku.score.schema.v1";

const SCORE_SCHEMA_BYTES: &[u8] = include_bytes!("../schema/score.schema.json");

/// Returns the checked-in canonical raw Score JSON Schema bytes.
#[must_use]
pub const fn score_schema_bytes() -> &'static [u8] {
    SCORE_SCHEMA_BYTES
}

/// Returns the lowercase hexadecimal SHA-256 digest for the raw Score schema.
///
/// The hash input is the ASCII domain, one NUL byte, the schema byte length as
/// an unsigned 64-bit big-endian integer, then the schema bytes.
#[must_use]
pub fn score_schema_digest() -> String {
    domain_separated_sha256_digest(SCORE_SCHEMA_DIGEST_DOMAIN, SCORE_SCHEMA_BYTES)
}
