//! Canonical JSON serialization and digest identity for accepted Scores.

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::Score;

/// ASCII domain separator for canonical Score JSON digests.
pub const CANONICAL_SCORE_DIGEST_DOMAIN: &str = "inku.score.canonical-json.v1";

/// Returns the canonical, compact UTF-8 JSON bytes for an accepted [`Score`].
///
/// Object keys are ordered recursively by Unicode scalar lexical order while
/// array order, string escaping, and number formatting come from `serde_json`.
pub fn canonical_json_bytes(score: &Score) -> serde_json::Result<Vec<u8>> {
    let mut value = serde_json::to_value(score)?;
    sort_object_keys(&mut value);
    serde_json::to_vec(&value)
}

/// Returns the lowercase hexadecimal SHA-256 digest for an accepted [`Score`].
///
/// The hash input is the ASCII domain, one NUL byte, the canonical JSON byte
/// length as an unsigned 64-bit big-endian integer, then the canonical bytes.
pub fn canonical_score_digest(score: &Score) -> serde_json::Result<String> {
    let canonical_json = canonical_json_bytes(score)?;
    let mut hasher = Sha256::new();
    hasher.update(CANONICAL_SCORE_DIGEST_DOMAIN.as_bytes());
    hasher.update([0]);
    hasher.update((canonical_json.len() as u64).to_be_bytes());
    hasher.update(canonical_json);
    let digest = hasher.finalize();
    let mut hexadecimal = String::with_capacity(digest.len() * 2);
    for byte in digest {
        hexadecimal.push(hexadecimal_digit(byte >> 4));
        hexadecimal.push(hexadecimal_digit(byte & 0x0f));
    }
    Ok(hexadecimal)
}

const fn hexadecimal_digit(value: u8) -> char {
    match value {
        0..=9 => (b'0' + value) as char,
        10..=15 => (b'a' + value - 10) as char,
        _ => unreachable!(),
    }
}

fn sort_object_keys(value: &mut Value) {
    match value {
        Value::Array(values) => values.iter_mut().for_each(sort_object_keys),
        Value::Object(object) => {
            let mut entries = std::mem::take(object).into_iter().collect::<Vec<_>>();
            entries.sort_unstable_by(|(left, _), (right, _)| left.cmp(right));
            for (key, mut child) in entries {
                sort_object_keys(&mut child);
                object.insert(key, child);
            }
        }
        _ => {}
    }
}
