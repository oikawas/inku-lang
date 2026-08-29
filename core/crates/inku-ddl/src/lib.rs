//! Host-neutral instruction-language foundation for inku.

#![forbid(unsafe_code)]

pub mod language;
pub mod prompt;
pub mod saijiki;

pub use language::{
    DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE, INSTRUCTION_LANGUAGE_REGISTRY_ID,
    InstructionLanguageError, REQUESTABLE_INSTRUCTION_LANGUAGE_CODES, RequestedInstructionLanguage,
    ResolvedInstructionLanguage, SUPPORTED_INSTRUCTION_LANGUAGE_CODES,
    normalize_instruction_language, resolve_instruction_language,
    resolve_instruction_language_for_ui,
};
pub use prompt::{
    PROMPT_BODY_TEMPLATE_ASSET_BYTES, PROMPT_BODY_TEMPLATE_ASSET_ID, PromptBodyTemplate,
    PromptBodyTemplateAsset, PromptBodyTemplateAssetError, PromptBodyTemplateRef,
    PromptBodyTemplateSlot, PromptBodyTemplateStage, PromptBodyTemplateStageAsset,
    prompt_body_template, prompt_body_template_asset, prompt_body_template_asset_from_bytes,
    prompt_body_template_asset_sha256_hex,
};
pub use saijiki::{
    DisplayCategoryProjection, MarkerClassProjection, MarkerOrder, ReferenceCategoryProjection,
    RelationAsset, RelationLiteralProjection, SAIJIKI_ASSET_BYTES, SAIJIKI_ASSET_ID, SaijikiAsset,
    SaijikiCategoryAsset, SaijikiDerivedProjection, SaijikiProjectionError, SaijikiScoreWireMaps,
    SaijikiSurfaceScoreProjection, SaijikiWordAsset, saijiki_asset, saijiki_asset_sha256_hex,
    saijiki_derived_projection, saijiki_derived_projection_from_asset, saijiki_marker_class_table,
    saijiki_relation_literal_table, saijiki_score_wire_maps,
};
