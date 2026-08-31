//! Host-neutral instruction-language foundation for inku.

#![forbid(unsafe_code)]

pub mod attachment;
pub mod clause;
pub mod compiler_lock;
pub mod composition;
pub mod document;
pub mod language;
pub mod macro_definition;
pub mod macro_expansion;
pub mod macro_parameter_binding;
pub mod macro_resolution;
pub mod macro_seed;
pub mod noun_phrase;
pub mod opaque_head;
pub mod parser;
pub mod phrase;
pub mod phrase_topology;
pub mod prompt;
pub mod relation_reference;
pub mod saijiki;
pub mod semantic_association;
pub mod semantic_instruction;
pub mod visible_patch;

pub use attachment::{
    ATTACHMENT_EVIDENCE_SCHEMA_ID, AttachmentEvidenceDiagnostic, AttachmentEvidenceDiagnosticKind,
    AttachmentEvidenceResult, AttachmentMarkerEvidence, AttachmentMarkerKind,
    EnglishAttachmentMarkerKind, JapaneseAttachmentMarkerKind, collect_attachment_evidence,
};
pub use clause::{
    CLAUSE_STREAM_SCHEMA_ID, ClauseAtom, ClauseSegment, ClauseSeparator, ClauseSeparatorKind,
    ClauseStream, ClauseStreamError, parse_clause_stream,
};

pub use compiler_lock::{
    CANONICAL_SEMANTIC_DDL_SCHEMA_ID, COMPILER_LOCK_DIGEST_DOMAIN, CompilerBlockingDiagnostic,
    CompilerConflict, CompilerDefinitionIdentity, CompilerLockState, CompilerSeedIdentity,
    DeliverySummary, SemanticDelivery, SemanticDeliveryKind, TYPED_DDL_COMPILATION_SCHEMA_ID,
    TYPED_DDL_COMPILER_LOCK_SCHEMA_ID, TypedDdlCompilation, TypedDdlCompilerLock, TypedHole,
    compile_typed_ddl, compiler_lock_hash_input, expanded_meaning_canonical_bytes,
};
pub use composition::{
    CORE_ROLE_COMPOSITION_SCHEMA_ID, CoreRoleComposition, CoreRoleKind, CoreRoleTerm,
    REMAINING_ROLE_COMPOSITION_SCHEMA_ID, RemainingRoleComposition, RemainingRoleKind,
    RemainingRoleTerm, UnattachedExactNumber, compose_core_roles, compose_remaining_roles,
};

pub use document::{
    DdlDocumentDiagnostic, MacroLock, NORMALIZED_DDL_DOCUMENT_SCHEMA_ID, NormalizedDdlDocument,
};

pub use language::{
    DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE, INSTRUCTION_LANGUAGE_REGISTRY_ID,
    InstructionLanguageError, REQUESTABLE_INSTRUCTION_LANGUAGE_CODES, RequestedInstructionLanguage,
    ResolvedInstructionLanguage, SUPPORTED_INSTRUCTION_LANGUAGE_CODES,
    normalize_instruction_language, resolve_instruction_language,
    resolve_instruction_language_for_ui,
};
pub use macro_definition::{
    ComponentDefinition, Expression, LEGACY_PLUGIN_FORMAT_WARNING, LegacyImportOutcome,
    LegacyWarning, MACRO_DEFINITION_DIGEST_DOMAIN, MACRO_DEFINITION_SCHEMA_ID, MacroDefinition,
    MacroDefinitionDiagnostic, MacroDefinitionIdentity, MacroDefinitionParseError,
    MacroDefinitionValidation, MacroSemanticRefProjection, NumericRange, ParameterSchema,
    SemanticMap, Statement, TransformExpression, project_macro_semantic_ref,
    validate_macro_definition_semantic_version,
};
pub use macro_expansion::{
    ExpandedMacroInvocation, ExpandedMacroNode, ExpandedMacroValue, ExpandedTransform,
    ExpansionPathSegment, GeneratedNodeProvenance, GeneratedTargetId, MACRO_EXPANSION_SCHEMA_ID,
    MACRO_VARY_CHOICE_SCHEME_ID, MacroExpansionDiagnostic, MacroExpansionDiagnosticKind,
    MacroExpansionLimits, MacroExpansionResult, MacroInvocationProvenance, expand_macros,
    macro_vary_choice_hash_input, typed_expansion_path_bytes,
};
pub use macro_parameter_binding::{
    BoundMacroParameterValue, CompleteMacroParameterBinding, MACRO_PARAMETER_BINDING_SCHEMA_ID,
    MacroParameterBinding, MacroParameterBindingDiagnostic, MacroParameterBindingDiagnosticKind,
    MacroParameterBindingResult, bind_macro_parameters,
};
pub use macro_resolution::{
    MACRO_INVOCATION_LOCK_RESOLUTION_SCHEMA_ID, MacroInvocationLockResolutionResult,
    MacroInvocationResolutionDiagnostic, MacroInvocationResolutionDiagnosticKind,
    MacroLockResolutionIdentity, ResolvedMacroInvocation, resolve_macro_invocations,
};
pub use macro_seed::{
    MACRO_SEED_DOMAIN, MACRO_SEED_SCHEME_ID, MacroInvocation, MacroInvocationError, MacroSeed,
    derive_macro_seed, macro_seed_hash_input,
};
pub use noun_phrase::{
    CanonicalHeadCandidate, EnglishDeterminerEvidence, EnglishDeterminerKind,
    EnglishNounPhraseCandidateEvidence, EnglishNounPhraseEvidenceResult,
    NOUN_PHRASE_EVIDENCE_SCHEMA_ID, NounPhraseEvidenceDiagnostic, NounPhraseEvidenceDiagnosticKind,
    collect_english_noun_phrase_evidence,
};
pub use opaque_head::{
    EnglishOpaqueHeadCandidateEvidenceResult, OPAQUE_HEAD_CANDIDATE_EVIDENCE_SCHEMA_ID,
    OpaqueHeadCandidateEvidence, OpaqueHeadCandidateEvidenceDiagnostic,
    OpaqueHeadCandidateEvidenceDiagnosticKind, collect_english_opaque_head_candidate_evidence,
};
pub use parser::{
    NEUTRAL_LEXEME_PARSER_SCHEMA_ID, NeutralDiagnostic, NeutralDiagnosticKind, NeutralParseResult,
    NeutralToken, NeutralTokenKind, SourceSpan, parse_neutral_lexemes,
};
pub use phrase::{
    DETERMINER_PHRASE_EVIDENCE_SCHEMA_ID, DeterminerPhraseEvidenceAvailability,
    DeterminerPhraseOpaqueCandidateRun, EnglishDeterminerPhraseEvidence,
    EnglishDeterminerPhraseEvidenceResult, collect_english_determiner_phrase_evidence,
};
pub use phrase_topology::{
    EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult,
    UNRESOLVED_DETERMINER_PHRASE_TOPOLOGY_EVIDENCE_SCHEMA_ID,
    UnresolvedDeterminerPhraseOpaqueCandidateRun, UnresolvedDeterminerPhraseTopologyEvidence,
    collect_english_unresolved_determiner_phrase_topology_evidence,
};
pub use prompt::{
    PROMPT_BODY_TEMPLATE_ASSET_BYTES, PROMPT_BODY_TEMPLATE_ASSET_ID, PromptBodyTemplate,
    PromptBodyTemplateAsset, PromptBodyTemplateAssetError, PromptBodyTemplateRef,
    PromptBodyTemplateSlot, PromptBodyTemplateStage, PromptBodyTemplateStageAsset,
    prompt_body_template, prompt_body_template_asset, prompt_body_template_asset_from_bytes,
    prompt_body_template_asset_sha256_hex,
};
pub use relation_reference::{
    RELATION_REFERENCE_EVIDENCE_SCHEMA_ID, RelationReferenceCandidateEnvelope,
    RelationReferenceEvidenceAvailability, RelationReferenceEvidenceDiagnostic,
    RelationReferenceEvidenceDiagnosticKind, RelationReferenceEvidenceResult,
    RelationReferenceOccurrence, RelationReferenceOccurrenceKind,
    collect_relation_reference_evidence,
};
pub use saijiki::{
    DisplayCategoryProjection, MarkerClassProjection, MarkerOrder, ReferenceCategoryProjection,
    RelationAsset, RelationLiteralProjection, SAIJIKI_ASSET_BYTES, SAIJIKI_ASSET_ID, SaijikiAsset,
    SaijikiCategoryAsset, SaijikiDerivedProjection, SaijikiProjectionError, SaijikiScoreWireMaps,
    SaijikiSurfaceScoreProjection, SaijikiWordAsset, saijiki_asset, saijiki_asset_sha256_hex,
    saijiki_derived_projection, saijiki_derived_projection_from_asset, saijiki_marker_class_table,
    saijiki_relation_literal_table, saijiki_score_wire_maps,
};
pub use semantic_association::{
    OwnedSemanticOccurrence, SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID, SemanticAssociationIssue,
    SemanticAssociationIssueKind, SemanticAssociationResult, SemanticEntity,
    SemanticEntityAssociationAst, SemanticFluctuation, SemanticIdentity, SemanticQuantity,
    SemanticSurface, SemanticTerm, SemanticTermProvenance, SourceOccurrence,
    associate_semantic_entities,
};
pub use semantic_instruction::{
    SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID, SemanticInstruction,
    SemanticInstructionAssociationAst, SemanticInstructionAssociationResult,
    SemanticInstructionIssue, SemanticInstructionIssueKind, associate_semantic_instructions,
};
pub use visible_patch::{
    VISIBLE_DDL_PATCH_SCHEMA_ID, ValidatedVisibleDdlCandidate, VisibleDdlPatch,
    VisibleDdlPatchEdit, VisiblePatchDiagnostic, validate_visible_ddl_patch,
};
