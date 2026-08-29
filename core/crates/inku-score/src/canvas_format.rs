//! Host-neutral canonical canvas format registry and identity.

use serde::Serialize;

use crate::canonical::domain_separated_sha256_digest;

/// Stable registry identifier used as the canonical JSON schema value.
pub const CANVAS_FORMAT_REGISTRY_ID: &str = "inku.canvas-format-registry.v1";

/// Domain separator for canonical canvas format registry digests.
pub const CANVAS_FORMAT_REGISTRY_DIGEST_DOMAIN: &str = "inku.canvas-format-registry.v1";

/// Canonical format selected explicitly by host boundaries when no choice exists.
pub const DEFAULT_CANVAS_FORMAT_ID: &str = "square";

/// Stable machine-readable code for exact lookup failures.
pub const UNKNOWN_CANVAS_FORMAT_ERROR_CODE: &str = "unknown_canvas_format";

/// One immutable semantic canvas format.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct CanvasFormat {
    pub id: &'static str,
    pub width_units: u32,
    pub height_units: u32,
}

impl CanvasFormat {
    /// Returns the canonical positive integer ratio pair.
    pub const fn integer_ratio(self) -> (u32, u32) {
        (self.width_units, self.height_units)
    }

    /// Returns a derived display ratio without changing semantic identity.
    pub fn ratio_f64(self) -> f64 {
        f64::from(self.width_units) / f64::from(self.height_units)
    }
}

/// The canonical ordered registry. IDs, ordinals, and integer ratios are wire identity.
pub const CANVAS_FORMAT_REGISTRY: &[CanvasFormat] = &[
    CanvasFormat {
        id: "square",
        width_units: 1,
        height_units: 1,
    },
    CanvasFormat {
        id: "golden",
        width_units: 809,
        height_units: 500,
    },
    CanvasFormat {
        id: "a4",
        width_units: 500,
        height_units: 707,
    },
    CanvasFormat {
        id: "b4",
        width_units: 500,
        height_units: 707,
    },
    CanvasFormat {
        id: "pillar",
        width_units: 1,
        height_units: 5,
    },
    CanvasFormat {
        id: "oban",
        width_units: 2,
        height_units: 3,
    },
    CanvasFormat {
        id: "wide",
        width_units: 47,
        height_units: 20,
    },
    CanvasFormat {
        id: "byobu",
        width_units: 11,
        height_units: 5,
    },
    CanvasFormat {
        id: "vertical",
        width_units: 9,
        height_units: 16,
    },
    CanvasFormat {
        id: "sd_monitor",
        width_units: 4,
        height_units: 3,
    },
    CanvasFormat {
        id: "hd_monitor",
        width_units: 16,
        height_units: 9,
    },
];

/// Exact lookup error. Hosts decide whether and when to apply an explicit default.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct UnknownCanvasFormatError;

impl UnknownCanvasFormatError {
    pub const fn code(self) -> &'static str {
        UNKNOWN_CANVAS_FORMAT_ERROR_CODE
    }
}

impl std::fmt::Display for UnknownCanvasFormatError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(UNKNOWN_CANVAS_FORMAT_ERROR_CODE)
    }
}

impl std::error::Error for UnknownCanvasFormatError {}

/// Stable validation failures for a candidate registry.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanvasFormatRegistryValidationError {
    UnexpectedCount { actual: usize },
    DuplicateId { id: &'static str },
    InvalidId { id: &'static str },
    NonPositiveUnits { id: &'static str },
    NonCoprimeUnits { id: &'static str },
    MissingDefault,
    UnexpectedEntry { ordinal: usize },
}

impl CanvasFormatRegistryValidationError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::UnexpectedCount { .. } => "unexpected_canvas_format_count",
            Self::DuplicateId { .. } => "duplicate_canvas_format_id",
            Self::InvalidId { .. } => "invalid_canvas_format_id",
            Self::NonPositiveUnits { .. } => "non_positive_canvas_format_units",
            Self::NonCoprimeUnits { .. } => "non_coprime_canvas_format_units",
            Self::MissingDefault => "missing_default_canvas_format",
            Self::UnexpectedEntry { .. } => "unexpected_canvas_format_entry",
        }
    }
}

impl std::fmt::Display for CanvasFormatRegistryValidationError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for CanvasFormatRegistryValidationError {}

/// Returns the canonical ordered registry.
pub const fn canvas_format_registry() -> &'static [CanvasFormat] {
    CANVAS_FORMAT_REGISTRY
}

/// Performs exact, case-sensitive lookup without trimming, aliases, or fallback.
pub fn lookup_canvas_format(id: &str) -> Result<&'static CanvasFormat, UnknownCanvasFormatError> {
    CANVAS_FORMAT_REGISTRY
        .iter()
        .find(|format| format.id == id)
        .ok_or(UnknownCanvasFormatError)
}

/// Validates that an ID is known without selecting a default.
pub fn validate_canvas_format_id(id: &str) -> Result<(), UnknownCanvasFormatError> {
    lookup_canvas_format(id).map(|_| ())
}

/// Validates exact count/order/value identity and all registry invariants.
pub fn validate_canvas_format_registry(
    registry: &[CanvasFormat],
) -> Result<(), CanvasFormatRegistryValidationError> {
    if registry.len() != CANVAS_FORMAT_REGISTRY.len() {
        return Err(CanvasFormatRegistryValidationError::UnexpectedCount {
            actual: registry.len(),
        });
    }

    for (ordinal, format) in registry.iter().enumerate() {
        if registry[..ordinal]
            .iter()
            .any(|previous| previous.id == format.id)
        {
            return Err(CanvasFormatRegistryValidationError::DuplicateId { id: format.id });
        }
        if !is_canonical_id(format.id) {
            return Err(CanvasFormatRegistryValidationError::InvalidId { id: format.id });
        }
        if format.width_units == 0 || format.height_units == 0 {
            return Err(CanvasFormatRegistryValidationError::NonPositiveUnits { id: format.id });
        }
        if greatest_common_divisor(format.width_units, format.height_units) != 1 {
            return Err(CanvasFormatRegistryValidationError::NonCoprimeUnits { id: format.id });
        }
    }

    if !registry
        .iter()
        .any(|format| format.id == DEFAULT_CANVAS_FORMAT_ID)
    {
        return Err(CanvasFormatRegistryValidationError::MissingDefault);
    }

    for (ordinal, (actual, expected)) in registry
        .iter()
        .zip(CANVAS_FORMAT_REGISTRY.iter())
        .enumerate()
    {
        if actual != expected {
            return Err(CanvasFormatRegistryValidationError::UnexpectedEntry { ordinal });
        }
    }

    Ok(())
}

#[derive(Serialize)]
struct CanonicalRegistry<'a> {
    schema: &'static str,
    formats: &'a [CanvasFormat],
}

/// Returns compact UTF-8 canonical JSON with no terminal line feed.
pub fn canvas_format_registry_canonical_json_bytes() -> serde_json::Result<Vec<u8>> {
    serde_json::to_vec(&CanonicalRegistry {
        schema: CANVAS_FORMAT_REGISTRY_ID,
        formats: CANVAS_FORMAT_REGISTRY,
    })
}

/// Returns the full lowercase domain-separated SHA-256 registry digest.
pub fn canvas_format_registry_digest() -> serde_json::Result<String> {
    let canonical_json = canvas_format_registry_canonical_json_bytes()?;
    Ok(domain_separated_sha256_digest(
        CANVAS_FORMAT_REGISTRY_DIGEST_DOMAIN,
        &canonical_json,
    ))
}

fn is_canonical_id(id: &str) -> bool {
    let bytes = id.as_bytes();
    !bytes.is_empty()
        && bytes[0].is_ascii_lowercase()
        && (bytes[bytes.len() - 1].is_ascii_lowercase() || bytes[bytes.len() - 1].is_ascii_digit())
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'_')
        && !bytes.windows(2).any(|pair| pair == b"__")
}

const fn greatest_common_divisor(mut left: u32, mut right: u32) -> u32 {
    while right != 0 {
        let remainder = left % right;
        left = right;
        right = remainder;
    }
    left
}
