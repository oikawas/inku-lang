//! Host-neutral instruction-language foundation for inku.

#![forbid(unsafe_code)]

pub mod language;

pub use language::{
    DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE, INSTRUCTION_LANGUAGE_REGISTRY_ID,
    InstructionLanguageError, REQUESTABLE_INSTRUCTION_LANGUAGE_CODES, RequestedInstructionLanguage,
    ResolvedInstructionLanguage, SUPPORTED_INSTRUCTION_LANGUAGE_CODES,
    normalize_instruction_language, resolve_instruction_language,
    resolve_instruction_language_for_ui,
};
