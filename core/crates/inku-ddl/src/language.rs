//! Versioned instruction-language registry and resolution rules.

use std::fmt;

use serde::{Deserialize, Serialize};

/// Stable identity for this registry's semantics.
pub const INSTRUCTION_LANGUAGE_REGISTRY_ID: &str = "inku.instruction-language-registry.v1";

/// Canonical supported-code order.
pub const SUPPORTED_INSTRUCTION_LANGUAGE_CODES: [&str; 2] = ["ja", "en"];

/// Canonical requestable-code order.
pub const REQUESTABLE_INSTRUCTION_LANGUAGE_CODES: [&str; 3] = ["auto", "ja", "en"];

/// The resolved language used when neither input nor a valid fallback selects one.
pub const DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE: ResolvedInstructionLanguage =
    ResolvedInstructionLanguage::Ja;

/// A language that callers may request before script-based resolution.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum RequestedInstructionLanguage {
    Auto,
    Ja,
    En,
}

impl RequestedInstructionLanguage {
    /// Return the canonical wire code.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::Ja => "ja",
            Self::En => "en",
        }
    }
}

/// A language selected for instruction-language support.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ResolvedInstructionLanguage {
    Ja,
    En,
}

impl ResolvedInstructionLanguage {
    /// Return the canonical wire code.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Ja => "ja",
            Self::En => "en",
        }
    }
}

/// A stable failure for unsupported language codes.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum InstructionLanguageError {
    UnsupportedCode { code: String },
}

impl InstructionLanguageError {
    /// Stable machine-readable error classification.
    pub const fn kind(&self) -> &'static str {
        match self {
            Self::UnsupportedCode { .. } => "unsupported_code",
        }
    }
}

impl fmt::Display for InstructionLanguageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedCode { code } => {
                write!(formatter, "unsupported instruction language: {code}")
            }
        }
    }
}

impl std::error::Error for InstructionLanguageError {}

/// Normalize a request using Python `(value or default).strip().lower()` semantics.
pub fn normalize_instruction_language(
    value: Option<&str>,
    default: &str,
) -> Result<RequestedInstructionLanguage, InstructionLanguageError> {
    let source = match value {
        Some(value) if !value.is_empty() => value,
        Some(_) | None => default,
    };
    let normalized = source.trim().to_lowercase();
    match normalized.as_str() {
        "auto" => Ok(RequestedInstructionLanguage::Auto),
        "ja" => Ok(RequestedInstructionLanguage::Ja),
        "en" => Ok(RequestedInstructionLanguage::En),
        _ => Err(InstructionLanguageError::UnsupportedCode { code: normalized }),
    }
}

/// Resolve a request with Japanese-first script probing and a normalized fallback.
pub fn resolve_instruction_language(
    text: &str,
    requested: Option<&str>,
    fallback: &str,
) -> Result<ResolvedInstructionLanguage, InstructionLanguageError> {
    match normalize_instruction_language(requested, DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE.as_str())?
    {
        RequestedInstructionLanguage::Ja => Ok(ResolvedInstructionLanguage::Ja),
        RequestedInstructionLanguage::En => Ok(ResolvedInstructionLanguage::En),
        RequestedInstructionLanguage::Auto => {
            if text.chars().any(is_japanese_script) {
                return Ok(ResolvedInstructionLanguage::Ja);
            }
            if text.chars().any(is_ascii_latin) {
                return Ok(ResolvedInstructionLanguage::En);
            }
            match normalize_instruction_language(
                Some(fallback),
                DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE.as_str(),
            )? {
                RequestedInstructionLanguage::Auto => Ok(DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE),
                RequestedInstructionLanguage::Ja => Ok(ResolvedInstructionLanguage::Ja),
                RequestedInstructionLanguage::En => Ok(ResolvedInstructionLanguage::En),
            }
        }
    }
}

/// Resolve with the server-router UI fallback boundary.
pub fn resolve_instruction_language_for_ui(
    text: &str,
    requested: Option<&str>,
    ui_lang: Option<&str>,
) -> Result<ResolvedInstructionLanguage, InstructionLanguageError> {
    let fallback = match ui_lang {
        Some("ja") => "ja",
        Some("en") => "en",
        Some(_) | None => DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE.as_str(),
    };
    resolve_instruction_language(text, requested, fallback)
}

fn is_japanese_script(character: char) -> bool {
    matches!(
        character as u32,
        0x3040..=0x30ff | 0x3400..=0x9fff
    )
}

fn is_ascii_latin(character: char) -> bool {
    character.is_ascii_alphabetic()
}
