//! Typed, host-neutral LLM request construction.
//!
//! These builders expose only visible authoring text and validated, bounded
//! catalog projections. Provider transport, retry decisions, author approval,
//! persistence, compare-and-set, and compiler validation belong to the pipeline
//! state machine and host adapters.

use std::{collections::BTreeSet, fmt};

use inku_ddl::{
    CompilerLockState, MacroDefinition, ResolvedInstructionLanguage, SAIJIKI_ASSET_ID, SourceSpan,
    TYPED_DDL_COMPILER_LOCK_SCHEMA_ID, TypedDdlCompilerLock, TypedHole,
    VISIBLE_DDL_PATCH_SCHEMA_ID, VisibleDdlPatch, VisibleDdlPatchEdit, saijiki_asset_sha256_hex,
    saijiki_derived_projection,
};
use inku_score::{CANVAS_FORMAT_REGISTRY_ID, canvas_format_registry_digest, lookup_canvas_format};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

/// Stable envelope identity for typed prompts emitted by this module.
pub const LLM_PROMPT_SCHEMA_ID: &str = "inku.llm-prompt.v1";
/// Distinct typed catalog-selection prompt edition.
pub const CATALOG_SELECTION_PROMPT_ID: &str = "inku.description-catalog-selection-prompt.v1";
/// Distinct typed Stage 1 prompt edition. This is not the legacy runtime template.
pub const TYPED_STAGE1_PROMPT_ID: &str = "inku.typed-stage1-normalized-ddl-prompt.v1";
/// Distinct visible-hole completion prompt edition.
pub const HOLE_COMPLETION_PROMPT_ID: &str = "inku.visible-ddl-hole-completion-prompt.v1";

const PROMPT_DIGEST_DOMAIN: &[u8] = b"inku.llm-prompt.v1";
const CATALOG_DIGEST_DOMAIN: &[u8] = b"inku.prompt-catalog-projection.v1";

/// The three LLM effects accepted by I-523.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LlmStage {
    SelectDescriptionCatalog,
    GenerateNormalizedDdl,
    CompleteVisibleDdlHoles,
}

impl LlmStage {
    /// Exact I-523 effect tag.
    pub const fn action_name(self) -> &'static str {
        match self {
            Self::SelectDescriptionCatalog => "select_description_catalog",
            Self::GenerateNormalizedDdl => "generate_normalized_ddl",
            Self::CompleteVisibleDdlHoles => "complete_visible_ddl_holes",
        }
    }
}

/// Caller-supplied hard bounds. This module has no shipping defaults.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PromptLimits {
    pub max_catalog_entries: usize,
    pub max_summary_bytes: usize,
    pub max_catalog_serialized_bytes: usize,
    pub max_source_bytes: usize,
    pub max_response_bytes: usize,
}

/// One finite candidate that the host has admitted for description-based selection.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DescriptionCatalogEntry {
    pub catalog_id: String,
    pub label: String,
    pub description: String,
}

/// How the resolved catalog was obtained before Stage 1 starts.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ResolvedCatalogMode {
    Explicit,
    Default,
    AutoSelected,
    AutoFallbackDefault,
    Saved,
}

impl ResolvedCatalogMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Explicit => "explicit",
            Self::Default => "default",
            Self::AutoSelected => "auto_selected",
            Self::AutoFallbackDefault => "auto_fallback_default",
            Self::Saved => "saved",
        }
    }
}

/// Fully resolved host options that must be recorded in every Stage 1 prompt.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Stage1Context {
    pub catalog_id: String,
    pub catalog_mode: ResolvedCatalogMode,
    pub canvas_format_id: String,
    pub canvas_format_registry_id: String,
    pub canvas_format_registry_digest: String,
}

/// A validated definition paired with prose localized by the host.
#[derive(Clone, Copy, Debug)]
pub struct MacroPromptEntry<'a> {
    pub definition: &'a MacroDefinition,
    pub localized_summary: &'a str,
}

/// One fully constructed provider request. It carries no provider-specific fields.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LlmPrompt {
    pub schema_id: String,
    pub prompt_id: String,
    pub stage: LlmStage,
    pub action_name: String,
    pub instruction_language: ResolvedInstructionLanguage,
    pub system: String,
    pub message: String,
    pub response_schema: Value,
    pub prompt_digest: String,
    pub saijiki_asset_id: Option<String>,
    pub saijiki_asset_digest: Option<String>,
    pub macro_catalog_digest: Option<String>,
    pub base_source_digest: Option<String>,
    pub base_compiler_lock_digest: Option<String>,
}

/// Exact catalog-selection response shape.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogSelectionResponse {
    pub catalog_id: String,
}

/// Exact typed Stage 1 response shape. Only visible DDL can cross this boundary.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Stage1Response {
    pub normalized_ddl: String,
}

/// Owned JSON range used by the provider response schema.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HolePatchRange {
    pub start_byte: usize,
    pub end_byte: usize,
}

impl From<SourceSpan> for HolePatchRange {
    fn from(value: SourceSpan) -> Self {
        Self {
            start_byte: value.start_byte,
            end_byte: value.end_byte,
        }
    }
}

impl From<HolePatchRange> for SourceSpan {
    fn from(value: HolePatchRange) -> Self {
        Self {
            start_byte: value.start_byte,
            end_byte: value.end_byte,
        }
    }
}

/// One strict, owned edit returned for a selected typed hole.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HolePatchEditResponse {
    pub hole_id: String,
    pub allowed_span: HolePatchRange,
    pub expected_range_digest: String,
    pub replacement: String,
}

/// Strict provider representation of `VisibleDdlPatch`.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HolePatchResponse {
    pub schema_id: String,
    pub base_source_digest: String,
    pub base_compiler_lock_digest: String,
    pub edits: Vec<HolePatchEditResponse>,
}

impl HolePatchResponse {
    /// Convert the owned wire shape. Candidate semantics remain the caller's validation duty.
    pub fn into_visible_ddl_patch(self) -> Result<VisibleDdlPatch, PromptError> {
        if self.schema_id != VISIBLE_DDL_PATCH_SCHEMA_ID {
            return Err(PromptError::ResponseIdentityMismatch { field: "schema_id" });
        }
        Ok(VisibleDdlPatch::new(
            self.base_source_digest,
            self.base_compiler_lock_digest,
            self.edits
                .into_iter()
                .map(|edit| VisibleDdlPatchEdit {
                    hole_id: edit.hole_id,
                    allowed_span: edit.allowed_span.into(),
                    expected_range_digest: edit.expected_range_digest,
                    replacement: edit.replacement,
                })
                .collect(),
        ))
    }
}

/// Stable request-construction and response-decoding failures.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PromptError {
    EmptyField {
        field: &'static str,
    },
    LimitExceeded {
        field: &'static str,
        actual: usize,
        maximum: usize,
    },
    DuplicateCatalogId {
        catalog_id: String,
    },
    CatalogContextMismatch,
    InvalidMacroDefinition {
        qualified_name: String,
    },
    DuplicateMacroIdentity {
        qualified_name: String,
        version: String,
    },
    UnknownCanvasFormat {
        canvas_format_id: String,
    },
    CanvasRegistryIdentityMismatch,
    SaijikiProjection,
    Serialization,
    InvalidJson,
    ResponseIdentityMismatch {
        field: &'static str,
    },
    SourceDigestMismatch,
    CompilerLockUnavailable,
    EmptyHoleSelection,
    UnknownHole {
        hole_id: String,
    },
    DuplicateHole {
        hole_id: String,
    },
    InvalidHoleRange {
        hole_id: String,
    },
    HoleRangeDigestMismatch {
        hole_id: String,
    },
}

impl PromptError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::EmptyField { .. } => "empty_prompt_field",
            Self::LimitExceeded { .. } => "prompt_limit_exceeded",
            Self::DuplicateCatalogId { .. } => "duplicate_catalog_id",
            Self::CatalogContextMismatch => "catalog_context_mismatch",
            Self::InvalidMacroDefinition { .. } => "invalid_macro_definition",
            Self::DuplicateMacroIdentity { .. } => "duplicate_macro_identity",
            Self::UnknownCanvasFormat { .. } => "unknown_canvas_format",
            Self::CanvasRegistryIdentityMismatch => "canvas_registry_identity_mismatch",
            Self::SaijikiProjection => "saijiki_projection_failure",
            Self::Serialization => "prompt_serialization_failure",
            Self::InvalidJson => "invalid_json",
            Self::ResponseIdentityMismatch { .. } => "response_identity_mismatch",
            Self::SourceDigestMismatch => "source_digest_mismatch",
            Self::CompilerLockUnavailable => "compiler_lock_unavailable",
            Self::EmptyHoleSelection => "empty_hole_selection",
            Self::UnknownHole { .. } => "unknown_hole",
            Self::DuplicateHole { .. } => "duplicate_hole",
            Self::InvalidHoleRange { .. } => "invalid_hole_range",
            Self::HoleRangeDigestMismatch { .. } => "hole_range_digest_mismatch",
        }
    }
}

impl fmt::Display for PromptError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyField { field } => write!(formatter, "empty prompt field: {field}"),
            Self::LimitExceeded {
                field,
                actual,
                maximum,
            } => write!(
                formatter,
                "prompt limit exceeded for {field}: {actual} > {maximum}"
            ),
            Self::DuplicateCatalogId { catalog_id } => {
                write!(formatter, "duplicate catalog id: {catalog_id}")
            }
            Self::CatalogContextMismatch => formatter.write_str("catalog context mismatch"),
            Self::InvalidMacroDefinition { qualified_name } => {
                write!(formatter, "invalid macro definition: {qualified_name}")
            }
            Self::DuplicateMacroIdentity {
                qualified_name,
                version,
            } => write!(
                formatter,
                "duplicate macro identity: {qualified_name}@{version}"
            ),
            Self::UnknownCanvasFormat { canvas_format_id } => {
                write!(formatter, "unknown canvas format: {canvas_format_id}")
            }
            Self::CanvasRegistryIdentityMismatch => {
                formatter.write_str("canvas registry identity mismatch")
            }
            Self::SaijikiProjection => formatter.write_str("Saijiki projection failed"),
            Self::Serialization => formatter.write_str("prompt serialization failed"),
            Self::InvalidJson => formatter.write_str("invalid JSON response"),
            Self::ResponseIdentityMismatch { field } => {
                write!(formatter, "response identity mismatch: {field}")
            }
            Self::SourceDigestMismatch => formatter.write_str("source digest mismatch"),
            Self::CompilerLockUnavailable => formatter.write_str("compiler lock unavailable"),
            Self::EmptyHoleSelection => formatter.write_str("empty hole selection"),
            Self::UnknownHole { hole_id } => write!(formatter, "unknown hole: {hole_id}"),
            Self::DuplicateHole { hole_id } => write!(formatter, "duplicate hole: {hole_id}"),
            Self::InvalidHoleRange { hole_id } => {
                write!(formatter, "invalid hole range: {hole_id}")
            }
            Self::HoleRangeDigestMismatch { hole_id } => {
                write!(formatter, "hole range digest mismatch: {hole_id}")
            }
        }
    }
}

impl std::error::Error for PromptError {}

#[derive(Serialize)]
struct MacroCatalogProjection {
    qualified_name: String,
    version: String,
    definition_digest: String,
    parameters: Value,
    localized_summary: String,
}

#[derive(Serialize)]
struct CanvasPromptContext<'a> {
    format_id: &'a str,
    width_units: u32,
    height_units: u32,
    registry_id: &'a str,
    registry_digest: &'a str,
}

#[derive(Serialize)]
struct Stage1Message<'a> {
    description: &'a str,
    catalog_id: &'a str,
    catalog_mode: &'a str,
    canvas: CanvasPromptContext<'a>,
}

#[derive(Serialize)]
struct HoleDescriptor<'a> {
    hole_id: &'a str,
    kind: &'a str,
    allowed_span: HolePatchRange,
    expected_range_digest: &'a str,
    expected_owner: &'a str,
}

#[derive(Serialize)]
struct HoleMessage<'a> {
    original_source: &'a str,
    base_source_digest: &'a str,
    base_compiler_lock_schema_id: &'a str,
    base_compiler_lock_digest: &'a str,
    selected_holes: Vec<HoleDescriptor<'a>>,
}

/// Build the bounded `select_description_catalog` request.
pub fn build_catalog_selection_prompt(
    description: &str,
    language: ResolvedInstructionLanguage,
    candidates: &[DescriptionCatalogEntry],
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    require_nonempty("description", description)?;
    require_within("description", description.len(), limits.max_source_bytes)?;
    validate_catalog_candidates(candidates, limits)?;

    let mut sorted = candidates.to_vec();
    sorted.sort_by(|left, right| left.catalog_id.cmp(&right.catalog_id));
    let catalog_bytes = serde_json::to_vec(&sorted).map_err(|_| PromptError::Serialization)?;
    require_within(
        "catalog_serialized_bytes",
        catalog_bytes.len(),
        limits.max_catalog_serialized_bytes,
    )?;
    let catalog_digest = digest_bytes(CATALOG_DIGEST_DOMAIN, &catalog_bytes);
    let ids = sorted
        .iter()
        .map(|candidate| candidate.catalog_id.clone())
        .collect::<Vec<_>>();
    let message = serde_json::to_string(&json!({
        "description": description,
        "candidates": sorted,
    }))
    .map_err(|_| PromptError::Serialization)?;
    let system = match language {
        ResolvedInstructionLanguage::Ja => "作者の記述を読み、提示された有限の候補から最も合う色カタログを一つ選ぶ。候補にないIDを作らない。理由、思考過程、説明を返さず、指定されたJSONだけを返す。",
        ResolvedInstructionLanguage::En => "Read the author's description and select exactly one best-fitting color catalog from the finite candidates. Never invent an ID. Return only the specified JSON, without reasons, hidden reasoning, or explanation.",
    }
    .to_owned();
    finish_prompt(LlmPrompt {
        schema_id: LLM_PROMPT_SCHEMA_ID.to_owned(),
        prompt_id: CATALOG_SELECTION_PROMPT_ID.to_owned(),
        stage: LlmStage::SelectDescriptionCatalog,
        action_name: LlmStage::SelectDescriptionCatalog.action_name().to_owned(),
        instruction_language: language,
        system,
        message,
        response_schema: json!({
            "type": "object",
            "additionalProperties": false,
            "required": ["catalog_id"],
            "properties": {
                "catalog_id": { "type": "string", "enum": ids }
            }
        }),
        prompt_digest: String::new(),
        saijiki_asset_id: None,
        saijiki_asset_digest: None,
        macro_catalog_digest: Some(catalog_digest),
        base_source_digest: None,
        base_compiler_lock_digest: None,
    })
}

/// Build the typed `generate_normalized_ddl` request.
pub fn build_stage1_prompt(
    description: &str,
    language: ResolvedInstructionLanguage,
    context: &Stage1Context,
    macros: &[MacroPromptEntry<'_>],
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    require_nonempty("description", description)?;
    require_within("description", description.len(), limits.max_source_bytes)?;
    require_nonblank("catalog_id", &context.catalog_id)?;
    if matches!(
        context.catalog_mode,
        ResolvedCatalogMode::Default | ResolvedCatalogMode::AutoFallbackDefault
    ) && context.catalog_id != "default"
    {
        return Err(PromptError::CatalogContextMismatch);
    }
    validate_canvas_context(context)?;
    let canvas = lookup_canvas_format(&context.canvas_format_id).map_err(|_| {
        PromptError::UnknownCanvasFormat {
            canvas_format_id: context.canvas_format_id.clone(),
        }
    })?;
    let (macro_catalog_json, macro_catalog_digest) = project_macro_catalog(macros, limits)?;
    let saijiki =
        saijiki_derived_projection(language).map_err(|_| PromptError::SaijikiProjection)?;

    let rules = match language {
        ResolvedInstructionLanguage::Ja => TYPED_STAGE1_SYSTEM_JA,
        ResolvedInstructionLanguage::En => TYPED_STAGE1_SYSTEM_EN,
    };
    let system = format!(
        "{rules}\n\n# accepted_saijiki_vocabulary\n{}\n\n# installed_macro_signatures\n{macro_catalog_json}",
        saijiki.prompt_block
    );
    let message = serde_json::to_string(&Stage1Message {
        description,
        catalog_id: &context.catalog_id,
        catalog_mode: context.catalog_mode.as_str(),
        canvas: CanvasPromptContext {
            format_id: canvas.id,
            width_units: canvas.width_units,
            height_units: canvas.height_units,
            registry_id: &context.canvas_format_registry_id,
            registry_digest: &context.canvas_format_registry_digest,
        },
    })
    .map_err(|_| PromptError::Serialization)?;
    finish_prompt(LlmPrompt {
        schema_id: LLM_PROMPT_SCHEMA_ID.to_owned(),
        prompt_id: TYPED_STAGE1_PROMPT_ID.to_owned(),
        stage: LlmStage::GenerateNormalizedDdl,
        action_name: LlmStage::GenerateNormalizedDdl.action_name().to_owned(),
        instruction_language: language,
        system,
        message,
        response_schema: json!({
            "type": "object",
            "additionalProperties": false,
            "required": ["normalized_ddl"],
            "properties": {
                "normalized_ddl": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": limits.max_source_bytes
                }
            }
        }),
        prompt_digest: String::new(),
        saijiki_asset_id: Some(SAIJIKI_ASSET_ID.to_owned()),
        saijiki_asset_digest: Some(saijiki_asset_sha256_hex().to_owned()),
        macro_catalog_digest: Some(macro_catalog_digest),
        base_source_digest: None,
        base_compiler_lock_digest: None,
    })
}

/// Build a request that can propose edits only for the supplied selected holes.
pub fn build_hole_completion_prompt(
    source: &str,
    language: ResolvedInstructionLanguage,
    base_compiler_lock: &TypedDdlCompilerLock,
    selected_holes: &[TypedHole],
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    require_nonempty("source", source)?;
    require_within("source", source.len(), limits.max_source_bytes)?;
    if base_compiler_lock.schema_id != TYPED_DDL_COMPILER_LOCK_SCHEMA_ID
        || base_compiler_lock.state != CompilerLockState::IncompleteKnownHole
    {
        return Err(PromptError::CompilerLockUnavailable);
    }
    let base_source_digest = sha256_hex(source.as_bytes());
    if base_source_digest != base_compiler_lock.visible_source_digest {
        return Err(PromptError::SourceDigestMismatch);
    }
    if selected_holes.is_empty() {
        return Err(PromptError::EmptyHoleSelection);
    }
    let mut selected = selected_holes.iter().collect::<Vec<_>>();
    selected.sort_by_key(|hole| (hole.allowed_span.start_byte, hole.allowed_span.end_byte));
    let mut ids = BTreeSet::new();
    for hole in &selected {
        if !ids.insert(hole.id.as_str()) {
            return Err(PromptError::DuplicateHole {
                hole_id: hole.id.clone(),
            });
        }
        if !base_compiler_lock
            .hole_identities
            .iter()
            .any(|identity| identity == &hole.id)
        {
            return Err(PromptError::UnknownHole {
                hole_id: hole.id.clone(),
            });
        }
        validate_hole(source, hole)?;
    }

    let saijiki =
        saijiki_derived_projection(language).map_err(|_| PromptError::SaijikiProjection)?;
    let rules = match language {
        ResolvedInstructionLanguage::Ja => HOLE_SYSTEM_JA,
        ResolvedInstructionLanguage::En => HOLE_SYSTEM_EN,
    };
    let system = format!(
        "{rules}\n\n# accepted_saijiki_vocabulary\n{}",
        saijiki.prompt_block
    );
    let descriptors = selected
        .iter()
        .map(|hole| HoleDescriptor {
            hole_id: &hole.id,
            kind: &hole.kind,
            allowed_span: hole.allowed_span.into(),
            expected_range_digest: &hole.expected_range_digest,
            expected_owner: hole.expected_owner.as_str(),
        })
        .collect::<Vec<_>>();
    let message = serde_json::to_string(&HoleMessage {
        original_source: source,
        base_source_digest: &base_source_digest,
        base_compiler_lock_schema_id: base_compiler_lock.schema_id,
        base_compiler_lock_digest: &base_compiler_lock.full_digest,
        selected_holes: descriptors,
    })
    .map_err(|_| PromptError::Serialization)?;
    let response_schema = hole_response_schema(
        &selected,
        &base_source_digest,
        &base_compiler_lock.full_digest,
        limits.max_source_bytes,
    );
    finish_prompt(LlmPrompt {
        schema_id: LLM_PROMPT_SCHEMA_ID.to_owned(),
        prompt_id: HOLE_COMPLETION_PROMPT_ID.to_owned(),
        stage: LlmStage::CompleteVisibleDdlHoles,
        action_name: LlmStage::CompleteVisibleDdlHoles.action_name().to_owned(),
        instruction_language: language,
        system,
        message,
        response_schema,
        prompt_digest: String::new(),
        saijiki_asset_id: Some(SAIJIKI_ASSET_ID.to_owned()),
        saijiki_asset_digest: Some(saijiki_asset_sha256_hex().to_owned()),
        macro_catalog_digest: None,
        base_source_digest: Some(base_source_digest),
        base_compiler_lock_digest: Some(base_compiler_lock.full_digest.clone()),
    })
}

/// Parse and validate an exact finite-candidate catalog selection.
pub fn parse_catalog_selection_response(
    response_text: &str,
    limits: PromptLimits,
) -> Result<CatalogSelectionResponse, PromptError> {
    let response: CatalogSelectionResponse = parse_bounded(response_text, limits)?;
    require_nonblank("catalog_id", &response.catalog_id)?;
    Ok(response)
}

/// Parse the exact Stage 1 response and enforce both response and visible-source bounds.
pub fn parse_stage1_response(
    response_text: &str,
    limits: PromptLimits,
) -> Result<Stage1Response, PromptError> {
    let response: Stage1Response = parse_bounded(response_text, limits)?;
    require_nonempty("normalized_ddl", &response.normalized_ddl)?;
    require_within(
        "normalized_ddl",
        response.normalized_ddl.len(),
        limits.max_source_bytes,
    )?;
    Ok(response)
}

/// Parse the exact visible-patch response. The caller validates it against the compilation.
pub fn parse_hole_patch_response(
    response_text: &str,
    limits: PromptLimits,
) -> Result<HolePatchResponse, PromptError> {
    parse_bounded(response_text, limits)
}

fn parse_bounded<T: DeserializeOwned>(
    response_text: &str,
    limits: PromptLimits,
) -> Result<T, PromptError> {
    let bytes = response_text.as_bytes();
    require_within("response", bytes.len(), limits.max_response_bytes)?;
    serde_json::from_slice(bytes).map_err(|_| PromptError::InvalidJson)
}

fn validate_catalog_candidates(
    candidates: &[DescriptionCatalogEntry],
    limits: PromptLimits,
) -> Result<(), PromptError> {
    if candidates.is_empty() {
        return Err(PromptError::EmptyField {
            field: "catalog_candidates",
        });
    }
    require_within(
        "catalog_entries",
        candidates.len(),
        limits.max_catalog_entries,
    )?;
    let mut ids = BTreeSet::new();
    for candidate in candidates {
        require_nonblank("catalog_id", &candidate.catalog_id)?;
        require_nonempty("catalog_label", &candidate.label)?;
        require_nonempty("catalog_description", &candidate.description)?;
        require_within(
            "catalog_label",
            candidate.label.len(),
            limits.max_summary_bytes,
        )?;
        require_within(
            "catalog_description",
            candidate.description.len(),
            limits.max_summary_bytes,
        )?;
        if !ids.insert(candidate.catalog_id.as_str()) {
            return Err(PromptError::DuplicateCatalogId {
                catalog_id: candidate.catalog_id.clone(),
            });
        }
    }
    Ok(())
}

fn validate_canvas_context(context: &Stage1Context) -> Result<(), PromptError> {
    if context.canvas_format_registry_id != CANVAS_FORMAT_REGISTRY_ID {
        return Err(PromptError::CanvasRegistryIdentityMismatch);
    }
    let expected_digest =
        canvas_format_registry_digest().map_err(|_| PromptError::Serialization)?;
    if context.canvas_format_registry_digest != expected_digest {
        return Err(PromptError::CanvasRegistryIdentityMismatch);
    }
    lookup_canvas_format(&context.canvas_format_id).map_err(|_| {
        PromptError::UnknownCanvasFormat {
            canvas_format_id: context.canvas_format_id.clone(),
        }
    })?;
    Ok(())
}

fn project_macro_catalog(
    entries: &[MacroPromptEntry<'_>],
    limits: PromptLimits,
) -> Result<(String, String), PromptError> {
    require_within(
        "macro_catalog_entries",
        entries.len(),
        limits.max_catalog_entries,
    )?;
    let mut projected = Vec::with_capacity(entries.len());
    for entry in entries {
        require_nonempty("macro_summary", entry.localized_summary)?;
        require_within(
            "macro_summary",
            entry.localized_summary.len(),
            limits.max_summary_bytes,
        )?;
        let identity =
            entry
                .definition
                .identity()
                .map_err(|_| PromptError::InvalidMacroDefinition {
                    qualified_name: entry
                        .definition
                        .qualified_name()
                        .unwrap_or_else(|| "<invalid>".to_owned()),
                })?;
        let parameters = serde_json::to_value(&entry.definition.parameters)
            .map_err(|_| PromptError::Serialization)?;
        projected.push(MacroCatalogProjection {
            qualified_name: identity.qualified_name().to_owned(),
            version: identity.version().to_owned(),
            definition_digest: identity.full_digest_hex().to_owned(),
            parameters,
            localized_summary: entry.localized_summary.to_owned(),
        });
    }
    projected.sort_by(|left, right| {
        (&left.qualified_name, &left.version).cmp(&(&right.qualified_name, &right.version))
    });
    for pair in projected.windows(2) {
        if pair[0].qualified_name == pair[1].qualified_name && pair[0].version == pair[1].version {
            return Err(PromptError::DuplicateMacroIdentity {
                qualified_name: pair[1].qualified_name.clone(),
                version: pair[1].version.clone(),
            });
        }
    }
    let bytes = serde_json::to_vec(&projected).map_err(|_| PromptError::Serialization)?;
    require_within(
        "macro_catalog_serialized_bytes",
        bytes.len(),
        limits.max_catalog_serialized_bytes,
    )?;
    let digest = digest_bytes(CATALOG_DIGEST_DOMAIN, &bytes);
    let json = String::from_utf8(bytes).map_err(|_| PromptError::Serialization)?;
    Ok((json, digest))
}

fn validate_hole(source: &str, hole: &TypedHole) -> Result<(), PromptError> {
    let span = hole.allowed_span;
    if span.start_byte >= span.end_byte
        || span.end_byte > source.len()
        || !source.is_char_boundary(span.start_byte)
        || !source.is_char_boundary(span.end_byte)
    {
        return Err(PromptError::InvalidHoleRange {
            hole_id: hole.id.clone(),
        });
    }
    let actual = sha256_hex(source[span.start_byte..span.end_byte].as_bytes());
    if actual != hole.expected_range_digest {
        return Err(PromptError::HoleRangeDigestMismatch {
            hole_id: hole.id.clone(),
        });
    }
    Ok(())
}

fn hole_response_schema(
    holes: &[&TypedHole],
    base_source_digest: &str,
    base_compiler_lock_digest: &str,
    max_replacement_bytes: usize,
) -> Value {
    let variants = holes
        .iter()
        .map(|hole| {
            json!({
                "type": "object",
                "additionalProperties": false,
                "required": ["hole_id", "allowed_span", "expected_range_digest", "replacement"],
                "properties": {
                    "hole_id": { "const": hole.id },
                    "allowed_span": {
                        "type": "object",
                        "additionalProperties": false,
                        "required": ["start_byte", "end_byte"],
                        "properties": {
                            "start_byte": { "const": hole.allowed_span.start_byte },
                            "end_byte": { "const": hole.allowed_span.end_byte }
                        }
                    },
                    "expected_range_digest": { "const": hole.expected_range_digest },
                    "replacement": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": max_replacement_bytes
                    }
                }
            })
        })
        .collect::<Vec<_>>();
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": ["schema_id", "base_source_digest", "base_compiler_lock_digest", "edits"],
        "properties": {
            "schema_id": { "const": VISIBLE_DDL_PATCH_SCHEMA_ID },
            "base_source_digest": { "const": base_source_digest },
            "base_compiler_lock_digest": { "const": base_compiler_lock_digest },
            "edits": {
                "type": "array",
                "minItems": 1,
                "maxItems": holes.len(),
                "items": { "oneOf": variants }
            }
        }
    })
}

fn finish_prompt(mut prompt: LlmPrompt) -> Result<LlmPrompt, PromptError> {
    let schema_bytes =
        serde_json::to_vec(&prompt.response_schema).map_err(|_| PromptError::Serialization)?;
    let mut hasher = Sha256::new();
    hasher.update(PROMPT_DIGEST_DOMAIN);
    for field in [
        prompt.schema_id.as_bytes(),
        prompt.prompt_id.as_bytes(),
        prompt.stage.action_name().as_bytes(),
        prompt.action_name.as_bytes(),
        prompt.instruction_language.as_str().as_bytes(),
        prompt.system.as_bytes(),
        prompt.message.as_bytes(),
        &schema_bytes,
        prompt.saijiki_asset_id.as_deref().unwrap_or("").as_bytes(),
        prompt
            .saijiki_asset_digest
            .as_deref()
            .unwrap_or("")
            .as_bytes(),
        prompt
            .macro_catalog_digest
            .as_deref()
            .unwrap_or("")
            .as_bytes(),
        prompt
            .base_source_digest
            .as_deref()
            .unwrap_or("")
            .as_bytes(),
        prompt
            .base_compiler_lock_digest
            .as_deref()
            .unwrap_or("")
            .as_bytes(),
    ] {
        hasher.update((field.len() as u64).to_be_bytes());
        hasher.update(field);
    }
    prompt.prompt_digest = hex_digest(hasher.finalize());
    Ok(prompt)
}

fn require_nonempty(field: &'static str, value: &str) -> Result<(), PromptError> {
    if value.is_empty() {
        Err(PromptError::EmptyField { field })
    } else {
        Ok(())
    }
}

fn require_nonblank(field: &'static str, value: &str) -> Result<(), PromptError> {
    if value.trim().is_empty() {
        Err(PromptError::EmptyField { field })
    } else {
        Ok(())
    }
}

fn require_within(field: &'static str, actual: usize, maximum: usize) -> Result<(), PromptError> {
    if actual > maximum {
        Err(PromptError::LimitExceeded {
            field,
            actual,
            maximum,
        })
    } else {
        Ok(())
    }
}

fn digest_bytes(domain: &[u8], bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(domain);
    hasher.update((bytes.len() as u64).to_be_bytes());
    hasher.update(bytes);
    hex_digest(hasher.finalize())
}

fn sha256_hex(bytes: &[u8]) -> String {
    hex_digest(Sha256::digest(bytes))
}

fn hex_digest(bytes: impl AsRef<[u8]>) -> String {
    bytes
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

const TYPED_STAGE1_SYSTEM_JA: &str = r#"あなたは inku の typed Stage 1 正規化器。作者の記述を深く読み、決定的 compiler が再読できる、可視で編集可能な normalized DDL を作る。

返すJSONは normalized_ddl だけとし、Score、renderer命令、観測文、思考過程、説明、非表示metadataを出力しない。normalized DDL はそれ単独で意味を完結させ、後段のLLM補完を前提にholeや曖昧な代用語を残さない。

accepted_saijiki_vocabulary の有限語彙と、compilerが読む通常の数値・句読点・文法だけを使う。installed_macro_signatures のmacroを使う場合は qualified_name と列挙されたparameterだけを書く。version、digest、MacroDefinition本文、component、展開結果をDDLへ書かない。

作者が明示した対象、色、画材、太さ、個数、寸法、角度、座標、領域、関係、反復、配置を失わない。fill、scatter、tile、background は別の意味である。fillは作者が指定した図形を指定領域の内部へ、指定個数と寸法を保って充填する。scatterへ読み替えない。scatterは疎密を持つ散布、tileは規則的な敷き詰め、backgroundはキャンバス背景色だけに使う。『満天』『星空』『全面』を理由にfillへ変えず、『埋める』を全面scatterへ変えない。明示領域をcanvas全体へ広げない。

順序が明示された配置は「赤と灰を交互にして、円を五つ並べる。」「鉛筆と太筆を交互にして、線を五本並べる。」「赤い円・青い線・灰の弧の順に繰り返して、八つ並べる。」のように書く。まとまりは括弧内の命令にせず、「赤い円と青い線の組を、灰の弧と交互に5つ並べる。」のように名詞句で書く。組と単独図形を合わせた総数5なので、円と線の組3つ、弧2つになる。交互には2項、順には空でない有限列を使い、項の順序と重複を保つ。同じ有限列を散らす・敷き詰める・埋めるにも使える。総個数へ列長や組の中の図形数を掛けない。順序のない複数の指定から交互や循環を推測しない。

日本語の「つ」は1つから9つまでで、10つ・11つとは書かない。10は助数詞なしの10として書ける。「個」は1個・2個・10個・11個などにも使え、必要なら線の「本」など対象に合う既存助数詞を使う。表記の違いで明示した総数を変えない。

接続先の線や弧の両端以外を指定するには「前の線の途中につながる」「前の弧の途中につながる」と書く。途中の具体位置は演奏で決まるため、中心や数値位置へ置き換えない。始点・終点の明示もそのまま保つ。

二つの形の位置と向きが鏡像になる関係は「前の形と鏡写し」と書く。葉や組なら全体を指す。明示した位置・寸法・向きと後続の色・画材は保つ。

canvas format、catalog ID、catalog modeは解決済みhost contextであり、勝手に既定へ置換しない。返答は指定されたJSONだけにする。"#;

const TYPED_STAGE1_SYSTEM_EN: &str = r#"You are inku's typed Stage 1 normalizer. Deep-read the author's description and produce visible, editable normalized DDL that the deterministic compiler can parse again.

Return JSON containing only normalized_ddl. Do not output a Score, renderer instructions, observation text, chain of thought, explanation, or hidden metadata. The normalized DDL must be meaning-complete by itself; do not leave holes or vague placeholders for a later LLM.

Use the finite accepted_saijiki_vocabulary plus ordinary numeric literals, punctuation, and grammar accepted by the compiler. When invoking an installed macro, write only its qualified_name and listed parameters. Do not write versions, digests, MacroDefinition bodies, components, or expansions into DDL.

Preserve every explicit subject, color, material, thinness, count, size, angle, coordinate, region, relation, repetition, and placement. Fill, scatter, tile, and background are distinct meanings. Fill places the author's specified shape inside the specified region while preserving its explicit count and size; never normalize fill to scatter. Scatter is a distribution with spacing, tile is regular tessellation, and background means only the canvas background color. Do not infer fill merely from “starry sky”, “full”, or “whole area”, and do not turn “fill” into whole-canvas scatter. Never expand an explicit region to the whole canvas.

Write explicitly ordered placements as "Line up five circles, alternating red and gray." or "Line up eight, repeating a red circle, a blue line, and a gray arc in order." Describe a group as a noun phrase without parenthesized commands: "Line up five, alternating a group of a red circle and a blue line with a gray arc." Five is the total number of groups and individual shapes, producing three circle-and-line groups and two arcs. Alternating takes two entries; in order takes a nonempty finite list. Preserve entry order and duplicates. The same sequences apply to scatter, tile, and fill. Do not multiply the total count by the list length or the number of shapes inside a group. Do not infer alternation or cycling without an explicit order.

When writing Japanese DDL, use the counter つ only for one through nine, never 10つ or 11つ. Ten can be written without a counter. 個 works for one, two, ten, eleven, and other counts; use an existing shape-specific counter such as 本 for lines when appropriate. Counter spelling must not change the explicit total.

Write "connected partway along the previous line" or "connected partway along the previous arc" for contact excluding both ends. Its position is decided during performance, so do not replace partway with the center or a numeric position. Preserve an explicitly selected start or end as well.

Write "mirrored with the previous shape" for mirrored positions and orientations across the axis between two shapes. A leaf or group is referred to as a whole. Preserve explicit positions, dimensions, and directions and the follower’s color and tool.

The canvas format, catalog ID, and catalog mode are already resolved host context. Do not replace them with defaults. Return only the specified JSON."#;

const HOLE_SYSTEM_JA: &str = r#"あなたは inku の可視DDL hole patch提案器。original_source全体を書き直さず、selected_holesに列挙された各holeのallowed_spanだけへ、accepted_saijiki_vocabularyと通常の数値・文法からなる可視DDL replacementを提案する。

hole ID、range、range digest、source digest、compiler lock digestをそのまま返す。選択されていない範囲、明示済みの意味、MacroDefinition、Score、typed-only fieldを変更・生成しない。記述入力を推測せず、思考過程、説明、whole documentを返さない。指定されたpatch JSONだけを返す。"#;

const HOLE_SYSTEM_EN: &str = r#"You propose visible inku DDL hole patches. Do not rewrite original_source. Propose visible DDL replacement text, using accepted_saijiki_vocabulary and ordinary numeric/compiler grammar, only inside each allowed_span listed in selected_holes.

Return each hole ID, range, range digest, source digest, and compiler lock digest unchanged. Do not change an unselected range or explicit meaning, and do not generate MacroDefinition data, a Score, typed-only fields, a description, chain of thought, explanation, or a whole document. Return only the specified patch JSON."#;

#[cfg(test)]
mod tests {
    use super::*;

    const LIMITS: PromptLimits = PromptLimits {
        max_catalog_entries: 8,
        max_summary_bytes: 256,
        max_catalog_serialized_bytes: 8_192,
        max_source_bytes: 4_096,
        max_response_bytes: 8_192,
    };

    #[test]
    fn typed_prompts_preserve_meanings_expose_exact_holes_and_hide_macro_bodies() {
        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Studio","heading":"Mark","version":"1.0.0","parameters":{"count":{"type":"integer"}},"components":{},"body":[{"op":"anchor","name":"secret_macro_body"}]}"#,
        )
        .unwrap();
        let context = Stage1Context {
            catalog_id: "sumi".to_owned(),
            catalog_mode: ResolvedCatalogMode::AutoSelected,
            canvas_format_id: "wide".to_owned(),
            canvas_format_registry_id: CANVAS_FORMAT_REGISTRY_ID.to_owned(),
            canvas_format_registry_digest: canvas_format_registry_digest().unwrap(),
        };
        let stage1 = build_stage1_prompt(
            "Fill the right half with twelve small red squares.",
            ResolvedInstructionLanguage::En,
            &context,
            &[MacroPromptEntry {
                definition: &definition,
                localized_summary: "A bounded mark macro.",
            }],
            LIMITS,
        )
        .unwrap();
        assert_eq!(stage1.action_name, "generate_normalized_ddl");
        assert!(
            stage1
                .system
                .contains("Fill, scatter, tile, and background are distinct")
        );
        assert!(
            stage1
                .system
                .contains("count, size, angle, coordinate, region")
        );
        assert!(stage1.system.contains("Studio.Mark"));
        assert!(stage1.system.contains("\"count\""));
        assert!(!stage1.system.contains("secret_macro_body"));
        assert!(
            !serde_json::to_string(&stage1)
                .unwrap()
                .contains("secret_macro_body")
        );
        assert_eq!(
            parse_stage1_response(
                r#"{"normalized_ddl":"twelve small red squares fill the right half"}"#,
                LIMITS,
            )
            .unwrap()
            .normalized_ddl,
            "twelve small red squares fill the right half"
        );
        assert!(
            parse_stage1_response(
                r#"{"normalized_ddl":"ok","observation_text":"hidden"}"#,
                LIMITS
            )
            .is_err()
        );

        let source = "many";
        let hole = TypedHole {
            id: "hole-1".to_owned(),
            kind: "quantity".to_owned(),
            span: SourceSpan {
                start_byte: 0,
                end_byte: 4,
            },
            allowed_span: SourceSpan {
                start_byte: 0,
                end_byte: 4,
            },
            expected_range_digest: sha256_hex(source.as_bytes()),
            expected_owner: inku_ddl::SemanticDeliveryOwner::Quantity,
            upstream_diagnostic_identity: "diagnostic-1".to_owned(),
        };
        let lock = TypedDdlCompilerLock {
            schema_id: TYPED_DDL_COMPILER_LOCK_SCHEMA_ID,
            state: CompilerLockState::IncompleteKnownHole,
            visible_source_digest: sha256_hex(source.as_bytes()),
            structured_semantic_occurrence_digest: "semantic".to_owned(),
            canonical_pre_expansion_digest: None,
            semantic_source_provenance_digest: None,
            geometry_policy_id: "geometry-policy",
            geometry_policy_digest: "geometry-digest".to_owned(),
            composition_seed: None,
            definition_identities: Vec::new(),
            macro_seeds: Vec::new(),
            expanded_meaning_digest: None,
            expanded_generated_provenance_digest: None,
            hole_identities: vec![hole.id.clone()],
            conflict_identities: Vec::new(),
            blocking_diagnostic_identities: Vec::new(),
            full_digest: "compiler-lock-digest".to_owned(),
        };
        let prompt = build_hole_completion_prompt(
            source,
            ResolvedInstructionLanguage::En,
            &lock,
            std::slice::from_ref(&hole),
            LIMITS,
        )
        .unwrap();
        assert_eq!(prompt.action_name, "complete_visible_ddl_holes");
        assert_eq!(
            prompt.response_schema["properties"]["edits"]["items"]["oneOf"][0]["properties"]["allowed_span"]
                ["properties"]["start_byte"]["const"],
            0
        );
        assert_eq!(
            prompt.response_schema["properties"]["edits"]["items"]["oneOf"][0]["properties"]["hole_id"]
                ["const"],
            "hole-1"
        );
        assert!(!prompt.message.contains("description"));
    }
}
