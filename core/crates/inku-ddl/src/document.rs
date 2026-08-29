//! Runtime-disconnected source-preserving DDL document foundation.

use std::fmt;

use crate::{
    MacroInvocation, ResolvedInstructionLanguage, validate_macro_definition_semantic_version,
};

/// Stable identity for the runtime-disconnected DDL document foundation.
pub const NORMALIZED_DDL_DOCUMENT_SCHEMA_ID: &str = "inku.normalized-ddl-document.v1";

/// A definition identity locked outside the visible DDL source.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroLock {
    qualified_name: String,
    version: String,
    digest: String,
}

impl MacroLock {
    /// Validate and retain one sidecar macro definition identity without rewriting it.
    pub fn new(
        qualified_name: impl Into<String>,
        version: impl Into<String>,
        digest: impl Into<String>,
    ) -> Result<Self, DdlDocumentDiagnostic> {
        let qualified_name = qualified_name.into();
        validate_qualified_name(&qualified_name)?;

        let version = version.into();
        if !validate_macro_definition_semantic_version(&version) {
            return Err(diagnostic("invalid_semantic_version"));
        }

        let digest = digest.into();
        if !is_full_sha256_digest(&digest) {
            return Err(diagnostic("invalid_digest"));
        }

        Ok(Self {
            qualified_name,
            version,
            digest,
        })
    }

    pub fn qualified_name(&self) -> &str {
        &self.qualified_name
    }

    pub fn version(&self) -> &str {
        &self.version
    }

    pub fn digest(&self) -> &str {
        &self.digest
    }
}

/// A typed document container that preserves the author's visible source bytes exactly.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NormalizedDdlDocument {
    source: String,
    language: ResolvedInstructionLanguage,
    macro_locks: Vec<MacroLock>,
}

impl NormalizedDdlDocument {
    /// Construct document metadata without parsing or normalizing visible DDL source.
    pub fn new(
        source: impl Into<String>,
        language: ResolvedInstructionLanguage,
        mut macro_locks: Vec<MacroLock>,
    ) -> Result<Self, DdlDocumentDiagnostic> {
        macro_locks.sort_by(|left, right| {
            left.qualified_name
                .as_bytes()
                .cmp(right.qualified_name.as_bytes())
        });

        for pair in macro_locks.windows(2) {
            if pair[0].qualified_name != pair[1].qualified_name {
                continue;
            }
            return Err(diagnostic(if pair[0] == pair[1] {
                "duplicate_macro_lock"
            } else {
                "conflicting_macro_lock"
            }));
        }

        Ok(Self {
            source: source.into(),
            language,
            macro_locks,
        })
    }

    /// Return the author-provided visible DDL source without canonicalization.
    pub fn source(&self) -> &str {
        &self.source
    }

    pub const fn language(&self) -> ResolvedInstructionLanguage {
        self.language
    }

    pub fn macro_locks(&self) -> &[MacroLock] {
        &self.macro_locks
    }
}

/// Stable metadata validation diagnostic.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DdlDocumentDiagnostic {
    code: &'static str,
}

impl DdlDocumentDiagnostic {
    pub const fn code(&self) -> &'static str {
        self.code
    }
}

impl fmt::Display for DdlDocumentDiagnostic {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code)
    }
}

impl std::error::Error for DdlDocumentDiagnostic {}

fn validate_qualified_name(value: &str) -> Result<(), DdlDocumentDiagnostic> {
    let Some((namespace, heading)) = value.split_once('.') else {
        return Err(diagnostic("invalid_qualified_name"));
    };
    MacroInvocation::new(namespace, heading, 0)
        .map(|_| ())
        .map_err(|_| diagnostic("invalid_qualified_name"))
}

fn is_full_sha256_digest(value: &str) -> bool {
    let Some(hex) = value.strip_prefix("sha256:") else {
        return false;
    };
    hex.len() == 64
        && hex
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

const fn diagnostic(code: &'static str) -> DdlDocumentDiagnostic {
    DdlDocumentDiagnostic { code }
}
