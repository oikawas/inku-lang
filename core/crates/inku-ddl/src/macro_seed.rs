//! Typed macro identities and deterministic `ddl-v1` macro seed derivation.

use std::fmt;

use sha2::{Digest, Sha256};

/// ASCII domain prefix for macro seed hash inputs.
pub const MACRO_SEED_DOMAIN: &[u8] = b"inku.macro-seed";

/// Public identifier for this seed serialization scheme.
pub const MACRO_SEED_SCHEME_ID: &str = "ddl-v1";

/// An explicit macro occurrence in canonical normalized DDL.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroInvocation {
    namespace: String,
    heading: String,
    ordinal: u64,
}

impl MacroInvocation {
    /// Create an invocation without transforming its namespace or heading.
    pub fn new(
        namespace: impl Into<String>,
        heading: impl Into<String>,
        ordinal: u64,
    ) -> Result<Self, MacroInvocationError> {
        let namespace = namespace.into();
        let heading = heading.into();
        if !is_ascii_identifier(&namespace) {
            return Err(MacroInvocationError::InvalidNamespace { namespace });
        }
        if !is_valid_heading(&heading) {
            return Err(MacroInvocationError::InvalidHeading { heading });
        }
        Ok(Self {
            namespace,
            heading,
            ordinal,
        })
    }

    /// Canonical namespace supplied by the caller.
    pub fn namespace(&self) -> &str {
        &self.namespace
    }

    /// Entry heading supplied by the caller.
    pub fn heading(&self) -> &str {
        &self.heading
    }

    /// Zero-based occurrence ordinal supplied by the caller.
    pub const fn ordinal(&self) -> u64 {
        self.ordinal
    }

    /// The canonical qualified macro name.
    pub fn qualified_name(&self) -> String {
        format!("{}.{}", self.namespace, self.heading)
    }
}

/// Stable validation failures for [`MacroInvocation`].
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MacroInvocationError {
    InvalidNamespace { namespace: String },
    InvalidHeading { heading: String },
}

impl MacroInvocationError {
    /// Stable machine-readable error classification.
    pub const fn kind(&self) -> &'static str {
        match self {
            Self::InvalidNamespace { .. } => "invalid_namespace",
            Self::InvalidHeading { .. } => "invalid_heading",
        }
    }
}

impl fmt::Display for MacroInvocationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidNamespace { namespace } => {
                write!(formatter, "invalid macro namespace: {namespace}")
            }
            Self::InvalidHeading { heading } => {
                write!(formatter, "invalid macro heading: {heading}")
            }
        }
    }
}

impl std::error::Error for MacroInvocationError {}

/// Immutable result of a `ddl-v1` macro seed derivation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroSeed {
    qualified_macro_name: String,
    ordinal: u64,
    effective_composition_seed: u64,
    full_digest: [u8; 32],
    full_digest_hex: String,
    resolved_seed: u64,
}

impl MacroSeed {
    /// Seed serialization scheme ID.
    pub const fn scheme_id(&self) -> &'static str {
        MACRO_SEED_SCHEME_ID
    }

    /// Qualified macro name included in the hash input.
    pub fn qualified_macro_name(&self) -> &str {
        &self.qualified_macro_name
    }

    /// Zero-based macro occurrence ordinal included in the hash input.
    pub const fn ordinal(&self) -> u64 {
        self.ordinal
    }

    /// Explicit composition seed, with omitted input represented as zero.
    pub const fn effective_composition_seed(&self) -> u64 {
        self.effective_composition_seed
    }

    /// Complete SHA-256 digest bytes.
    pub const fn full_digest_bytes(&self) -> &[u8; 32] {
        &self.full_digest
    }

    /// Complete lowercase SHA-256 digest hex.
    pub fn full_digest_hex(&self) -> &str {
        &self.full_digest_hex
    }

    /// Deterministic u64 seed from the first eight digest bytes, big-endian.
    pub const fn resolved_seed(&self) -> u64 {
        self.resolved_seed
    }
}

/// Return the exact `ddl-v1` bytes hashed for a valid macro invocation.
pub fn macro_seed_hash_input(
    canonical_normalized_ddl: &str,
    invocation: &MacroInvocation,
    composition_seed: Option<u64>,
) -> Vec<u8> {
    let effective_composition_seed = composition_seed.unwrap_or(0);
    let qualified_name = invocation.qualified_name();
    let fields = [
        MACRO_SEED_SCHEME_ID,
        canonical_normalized_ddl,
        qualified_name.as_str(),
        &invocation.ordinal.to_string(),
        &effective_composition_seed.to_string(),
    ];

    let mut bytes = Vec::with_capacity(
        MACRO_SEED_DOMAIN.len() + fields.iter().map(|field| 8 + field.len()).sum::<usize>(),
    );
    bytes.extend_from_slice(MACRO_SEED_DOMAIN);
    for field in fields {
        bytes.extend_from_slice(&(field.len() as u64).to_be_bytes());
        bytes.extend_from_slice(field.as_bytes());
    }
    bytes
}

/// Derive the full digest and resolved u64 seed using exact `ddl-v1` framing.
pub fn derive_macro_seed(
    canonical_normalized_ddl: &str,
    invocation: &MacroInvocation,
    composition_seed: Option<u64>,
) -> MacroSeed {
    let effective_composition_seed = composition_seed.unwrap_or(0);
    let full_digest: [u8; 32] = Sha256::digest(macro_seed_hash_input(
        canonical_normalized_ddl,
        invocation,
        composition_seed,
    ))
    .into();
    let full_digest_hex = full_digest
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    let resolved_seed =
        u64::from_be_bytes(full_digest[..8].try_into().expect("digest is 32 bytes"));

    MacroSeed {
        qualified_macro_name: invocation.qualified_name(),
        ordinal: invocation.ordinal,
        effective_composition_seed,
        full_digest,
        full_digest_hex,
        resolved_seed,
    }
}

fn is_ascii_identifier(value: &str) -> bool {
    let mut characters = value.bytes();
    matches!(characters.next(), Some(first) if first.is_ascii_alphabetic())
        && characters
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, b'_' | b'-'))
}

fn is_valid_heading(value: &str) -> bool {
    !value.is_empty()
        && value == value.trim()
        && !value
            .chars()
            .any(|character| character.is_control() || matches!(character, '\u{2028}' | '\u{2029}'))
}
