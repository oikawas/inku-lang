//! Host-neutral instruction-language foundation for inku.

#![forbid(unsafe_code)]

pub mod language;
pub mod saijiki;

pub use language::{
    DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE, INSTRUCTION_LANGUAGE_REGISTRY_ID,
    InstructionLanguageError, REQUESTABLE_INSTRUCTION_LANGUAGE_CODES, RequestedInstructionLanguage,
    ResolvedInstructionLanguage, SUPPORTED_INSTRUCTION_LANGUAGE_CODES,
    normalize_instruction_language, resolve_instruction_language,
    resolve_instruction_language_for_ui,
};
pub use saijiki::{
    MarkerOrder, RelationAsset, SAIJIKI_ASSET_BYTES, SAIJIKI_ASSET_ID, SaijikiAsset,
    SaijikiCategoryAsset, SaijikiWordAsset, saijiki_asset, saijiki_asset_sha256_hex,
};
