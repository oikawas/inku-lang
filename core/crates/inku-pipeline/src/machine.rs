//! Pure effect orchestration around the shared compiler and durable visible DDL.

use std::collections::{BTreeMap, BTreeSet};

use inku_ddl::work_plan::WorkPlan;
use inku_ddl::{
    CompilerLockState, CompilerResourceExecutionFailure, CompilerResourceExecutionResult,
    CompletionRangeRecord, MacroDefinition, MacroLock, NormalizedDdlDocument,
    RANGE_WORDS_CHANGED_HOLE_KIND, ResolvedInstructionLanguage, SAIJIKI_ASSET_ID,
    SAIJIKI_V1_ASSET_ID, ScoreDiagnosticOwner, ScoreFieldGap, ScoreInstructionOrigin,
    ScoreMaterializationError, TypedDdlCompilation, compile_typed_ddl,
    migrate_macro_definition_from_saijiki_v1, record_after_patch, record_keeping_numbers,
    settle_completion_record, validate_visible_ddl_patch, validate_visible_ddl_patch_detailed,
    visible_ddl_patch_available, with_completion_record,
};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::authority::{
    AuthorityTransitionOutcome, AuthorityTransitionProposal, AuthorityTransitionResult,
    VariationAuthorityState,
};
use crate::colors::{self, ColorsContext, LawsHandoff, PrintedPlan};
use crate::composition::{self, CheckedReading};
use crate::composition_reading::{
    build_composition_reading_prompt, parse_composition_reading_response,
};
use crate::core_boundary::CatalogMode;
use crate::core_boundary::{CompiledDelivery, CompilerOptions, ResolvedHostOptions};
use crate::laws::{self, ComposedPlan, LawsContext, LawsDirection};
use crate::laws_record::{LawsBasis, LawsLayerRecord};
use crate::prompts::{
    DescriptionCatalogEntry, HOLE_COMPLETION_PROMPT_ID, HoleCompletionResult,
    HolePatchEditResponse, HolePatchResponse, LEGACY_HOLE_COMPLETION_PROMPT_ID, LlmPrompt,
    LlmStage, MacroPromptEntry, PREVIOUS_HOLE_COMPLETION_PROMPT_IDS, PromptLimits, Stage1Context,
    build_catalog_selection_prompt, build_hole_completion_prompt, build_sketch_prompt,
    build_stage1_prompt_for_run, parse_catalog_selection_response, parse_hole_completion_response,
    parse_hole_patch_response, parse_sketch_response, parse_stage1_response_and_plan_with_plugins,
    with_hole_completion_feedback, with_stage1_background_feedback, with_stage1_compiler_feedback,
};
use crate::protocol::{
    ActionEcho, DecimalU64, EffectAction, EffectResult, Envelope, PROTOCOL_NAME, PROTOCOL_VERSION,
    PipelineEvent, ProtocolError, ProviderFailure, RetryPolicy, digest, value_digest,
};

fn stage1_compiler_failure_detail(compiled: &TypedDdlCompilation) -> &str {
    let kind = compiled
        .holes
        .first()
        .map(|item| item.kind.as_str())
        .or_else(|| compiled.conflicts.first().map(|item| item.kind.as_str()))
        .or_else(|| {
            compiled
                .blocking_diagnostics
                .first()
                .map(|item| item.kind.as_str())
        });
    match kind {
        Some(kind)
            if kind.len() <= 64
                && !kind.is_empty()
                && kind.bytes().all(|byte| {
                    byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_'
                }) =>
        {
            kind
        }
        Some(_) => "compiler_diagnostic_unclassified",
        None => "compiler_lock_unavailable",
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LockedDefinition {
    pub qualified_name: String,
    pub version: String,
    pub digest: String,
    /// Qualified aliases that also invoke this definition; omitted when empty.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub aliases: Vec<String>,
}

/// Exact visible source and its sidecar locks; no description or hidden reasoning.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VisibleDocument {
    pub source: String,
    pub language: ResolvedInstructionLanguage,
    pub macro_locks: Vec<LockedDefinition>,
    /// The Saijiki edition the source is written with (SPEC §3.3). A saved document without
    /// it was written with v1; it is kept without the field so its saved bytes still verify.
    #[serde(
        default = "retired_saijiki_edition",
        skip_serializing_if = "is_retired_saijiki_edition"
    )]
    pub saijiki: String,
}

fn retired_saijiki_edition() -> String {
    SAIJIKI_V1_ASSET_ID.to_owned()
}

fn is_retired_saijiki_edition(edition: &str) -> bool {
    edition == SAIJIKI_V1_ASSET_ID
}

/// Whether a definition that does not validate would validate once migrated from v1.
fn needs_saijiki_migration(definition: &MacroDefinition) -> bool {
    serde_json::to_value(definition)
        .ok()
        .and_then(|value| migrate_macro_definition_from_saijiki_v1(&value).ok())
        .is_some_and(|migration| migration.changed)
}

impl VisibleDocument {
    /// Refuse a document of another Saijiki edition; only the current one is read.
    pub fn require_current_saijiki(&self) -> Result<(), ProtocolError> {
        if self.saijiki == SAIJIKI_ASSET_ID {
            Ok(())
        } else if self.saijiki == SAIJIKI_V1_ASSET_ID {
            Err(ProtocolError::SaijikiMigrationRequired)
        } else {
            Err(ProtocolError::SchemaViolation)
        }
    }

    pub fn document(&self) -> Result<NormalizedDdlDocument, ProtocolError> {
        self.require_current_saijiki()?;
        let locks = self
            .macro_locks
            .iter()
            .map(|lock| {
                MacroLock::new(&lock.qualified_name, &lock.version, &lock.digest)
                    .and_then(|macro_lock| macro_lock.with_aliases(lock.aliases.iter().cloned()))
                    .map_err(|_| ProtocolError::SchemaViolation)
            })
            .collect::<Result<Vec<_>, _>>()?;
        NormalizedDdlDocument::new(&self.source, self.language, locks)
            .map_err(|_| ProtocolError::SchemaViolation)
    }

    fn from_document(document: &NormalizedDdlDocument) -> Self {
        Self {
            source: document.source().to_owned(),
            language: document.language(),
            macro_locks: document
                .macro_locks()
                .iter()
                .map(|lock| LockedDefinition {
                    qualified_name: lock.qualified_name().to_owned(),
                    version: lock.version().to_owned(),
                    digest: lock.digest().to_owned(),
                    aliases: lock.aliases().to_vec(),
                })
                .collect(),
            saijiki: SAIJIKI_ASSET_ID.to_owned(),
        }
    }

    pub fn source_digest(&self) -> String {
        // This is the compiler's exact visible-source SHA, not a new source normalization.
        use sha2::{Digest, Sha256};
        Sha256::digest(self.source.as_bytes())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogCandidate {
    pub prompt: DescriptionCatalogEntry,
    pub resolved: ResolvedHostOptions,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PipelineConfig {
    pub envelope_limits: crate::byte_envelope::EnvelopeLimits,
    pub language: ResolvedInstructionLanguage,
    pub compiler: CompilerOptions,
    pub definitions: Vec<MacroDefinition>,
    pub macro_summaries: Vec<String>,
    pub catalogs: Vec<CatalogCandidate>,
    pub prompt_limits: PromptLimits,
    pub catalog_retry: RetryPolicy,
    pub stage1_retry: RetryPolicy,
    pub hole_retry: RetryPolicy,
    /// Budget for the optional sketch; the catalog budget when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sketch_retry: Option<RetryPolicy>,
    /// The composition step after Stage 1. Absent, a run commits Stage 1 as it
    /// printed it (runs from before the step, and hosts that do not offer it).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub composition: Option<CompositionConfig>,
    /// Budget for the composition reading; the catalog budget when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub composition_retry: Option<RetryPolicy>,
    /// The laws stage after the composition (stage B-2c of the laws port): a
    /// reader chooses laws for the composed plan, and the core prints what they
    /// change in numbers before the commit. Absent, the composed document is
    /// committed as the composition printed it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub laws: Option<LawsConfig>,
    /// Budget for the laws; the catalog budget when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub laws_retry: Option<RetryPolicy>,
    /// The color stage after the laws (2026-10-20): a reader chooses color laws
    /// for the work, and the core prints the colors they change before the
    /// commit. Absent, the document the laws left is committed as it is.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub colors: Option<ColorsConfig>,
    /// Budget for the colors; the catalog budget when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub colors_retry: Option<RetryPolicy>,
}

/// How a run chooses its colors: present, the run asks `choose_colors` once
/// the laws are printed. The render seed is the one the host draws the work
/// with, so that the stage's estimate of the drawing places a scatter's marks
/// where the picture will.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ColorsConfig {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub render_seed: Option<DecimalU64>,
}

/// A document waiting for its colors: the plan it was printed from, the
/// document (committed as it is when the colors fail), the reason its commit
/// carries and what the laws handed on.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PendingColors {
    pub printed: PrintedPlan,
    pub document: VisibleDocument,
    pub reason: String,
    #[serde(default)]
    pub handoff: LawsHandoff,
}

/// How a run composes its Stage 1 plan: the layers whose place the description
/// does not state are placed on ranges of the thirds grid, from a reading of the
/// description or, without one, from the author's defaults.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CompositionConfig {
    /// Send the composition reading. When false (an on-device model), the default
    /// reading places the layers without a request.
    pub read: bool,
}

/// A settled Stage 1 result waiting for its composition reading: the plan, the
/// document as Stage 1 printed it (committed when the plan cannot be composed),
/// and the reason its commit carries.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PendingComposition {
    pub plan: WorkPlan,
    pub document: VisibleDocument,
    pub reason: String,
}

/// How a run applies laws to its composed plan: present, the run asks
/// `choose_laws` once the composition is printed.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LawsConfig {}

/// A composed document waiting for its laws: the composed plan it was printed
/// from, the document (committed as it is when the laws fail) and the reason
/// its commit carries.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PendingLaws {
    pub composed: ComposedPlan,
    pub document: VisibleDocument,
    pub reason: String,
    /// The reasons the stage refused the run's answers with, in order, which a
    /// request from the third on lists after the latest (2026-10-21).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub refused: Vec<laws::RefusedReason>,
}

/// A saved work as the laws stage from it reads it (2026-10-20).
struct SavedWork {
    source: String,
    description: String,
    completion_ranges: Option<CompletionRangeRecord>,
    laws_layers: Option<LawsLayerRecord>,
    laws_basis: Option<LawsBasis>,
}

/// Whether a description run sketches before Stage 1. The sketch only
/// supplements place and light beside the description; it runs only when the
/// author asks for it, never waits for approval, and never stops a run.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "mode", rename_all = "snake_case", deny_unknown_fields)]
pub enum SketchRequest {
    /// No sketch (the default).
    #[default]
    Off,
    /// The author asked to draw with a sketch.
    On,
    /// A sketch the author edited, or a saved one being replayed. No request is made.
    Supplied { text: String },
}

impl SketchRequest {
    fn is_off(&self) -> bool {
        matches!(self, Self::Off)
    }
}

/// What the sketch did for this run.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SketchState {
    /// The request is waiting to be made before Stage 1.
    Pending,
    /// The sketcher supplemented place or light.
    Supplemented,
    /// The sketcher found nothing to supplement.
    NotNeeded,
    /// The sketch request failed; Stage 1 read the description alone.
    Fallback,
    /// The author's or a saved sketch was used without a request.
    Supplied,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SketchRecord {
    pub state: SketchState,
    pub text: Option<String>,
}

impl SketchRecord {
    fn from_request(request: SketchRequest) -> Option<Self> {
        match request {
            SketchRequest::Off => None,
            SketchRequest::On => Some(Self {
                state: SketchState::Pending,
                text: None,
            }),
            SketchRequest::Supplied { text } => {
                let text = text.trim().to_owned();
                (!text.is_empty()).then_some(Self {
                    state: SketchState::Supplied,
                    text: Some(text),
                })
            }
        }
    }

    /// The text Stage 1 reads beside the description.
    fn stage1_text(&self) -> Option<&str> {
        match self.state {
            SketchState::Supplemented | SketchState::Supplied => self.text.as_deref(),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "tag", rename_all = "snake_case", deny_unknown_fields)]
pub enum AuthoringInput {
    DirectDdl {
        source: String,
        /// The record of the ranges completions wrote, kept with the work this
        /// DDL comes from (A3). A text alone, or a work without completions,
        /// has none.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        completion_ranges: Option<CompletionRangeRecord>,
        /// The record of the layers the laws placed, kept with the work this
        /// DDL comes from (2026-10-20). A text alone, or a work without laws,
        /// has none.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        laws_layers: Option<LawsLayerRecord>,
        /// What the laws of the work this DDL comes from were applied to
        /// (2026-10-20), kept with the work beside the record and given back
        /// unchanged with the snapshot.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        laws_basis: Option<LawsBasis>,
    },
    /// The laws stage from a saved work (the AI refinement's laws move,
    /// 2026-10-20): the work's DDL and description, the records kept with it,
    /// and the refinement's direction. The laws are applied to the composed
    /// document the work keeps, or to its DDL when it has no laws, and the
    /// run stops with a reason rather than commit a child like its parent.
    SavedLaws {
        source: String,
        description: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        completion_ranges: Option<CompletionRangeRecord>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        laws_layers: Option<LawsLayerRecord>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        laws_basis: Option<LawsBasis>,
        #[serde(default)]
        direction: LawsDirection,
    },
    Description {
        description: String,
        auto_catalog: bool,
        #[serde(default, skip_serializing_if = "SketchRequest::is_off")]
        sketch: SketchRequest,
    },
}

/// Strict pipeline wire shape for render canvas dimensions.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PipelineRenderCanvas {
    pub width: f64,
    pub height: f64,
}

/// Strict I-523 render options. Seeds remain canonical unsigned decimal strings on the wire.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PipelineRenderOptions {
    pub resolved_color_map: BTreeMap<String, String>,
    pub catalog_id: Option<String>,
    pub canvas: PipelineRenderCanvas,
    pub canvas_aspect_id: String,
    pub svg_profile: inku_render::types::SvgProfile,
    pub render_seed: Option<DecimalU64>,
    pub composition_seed: Option<DecimalU64>,
    pub wild: bool,
    pub error_policy: inku_score::ScoreErrorPolicy,
}

impl From<PipelineRenderOptions> for inku_render::types::RenderOptions {
    fn from(value: PipelineRenderOptions) -> Self {
        Self {
            resolved_color_map: value.resolved_color_map,
            catalog_id: value.catalog_id,
            canvas: inku_render::types::CanvasSize::new(value.canvas.width, value.canvas.height),
            canvas_aspect_id: value.canvas_aspect_id,
            svg_profile: value.svg_profile,
            render_seed: value.render_seed.map(|seed| i128::from(seed.get())),
            composition_seed: value.composition_seed.map(|seed| i128::from(seed.get())),
            wild: value.wild,
            error_policy: value.error_policy,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "tag", rename_all = "snake_case", deny_unknown_fields)]
pub enum PipelineInput {
    Start {
        variation_id: String,
        authoring_nonce: String,
        config: Box<PipelineConfig>,
        authority: VariationAuthorityState,
        authoring: AuthoringInput,
    },
    EffectResult {
        result: EffectResult,
    },
    CommitUserDdl {
        expected_revision: DecimalU64,
        source: String,
    },
    GenerateFromDescription {
        expected_revision: DecimalU64,
        description: String,
        auto_catalog: bool,
        #[serde(default, skip_serializing_if = "SketchRequest::is_off")]
        sketch: SketchRequest,
    },
    CompleteHoles {
        expected_revision: DecimalU64,
        hole_ids: Vec<String>,
    },
    ApprovePatch {
        expected_revision: DecimalU64,
        proposal_digest: String,
    },
    DeclinePatch {
        proposal_digest: String,
    },
    Render {
        options: PipelineRenderOptions,
        clip: crate::core_boundary::SerializableClipPolicy,
    },
    Cancel,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "tag", rename_all = "snake_case", deny_unknown_fields)]
pub enum PipelinePhase {
    AuthoringStarted,
    AwaitingLlm {
        stage: LlmStage,
        description: Option<String>,
        hole_ids: Vec<String>,
        elapsed_ms: DecimalU64,
    },
    AwaitingVisibleDdlCommit {
        document: VisibleDocument,
        authority: AuthorityTransitionProposal,
        reason: String,
        /// The completion record an approved patch leaves (A3), kept once the
        /// host acknowledges the commit.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        completion_ranges: Option<CompletionRangeRecord>,
    },
    AwaitingPatchApproval {
        patch: HolePatchResponse,
        candidate: VisibleDocument,
        proposal_digest: String,
        base_revision: DecimalU64,
    },
    ScoreReady,
    Completed,
    NeedsUserEdit {
        reason: String,
    },
    Failed {
        reason: String,
    },
    Cancelled,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PipelineSnapshot {
    pub protocol: String,
    pub version: String,
    pub execution_id: String,
    pub variation_id: String,
    pub sequence: DecimalU64,
    pub event_sequence: DecimalU64,
    pub action_ordinal: DecimalU64,
    pub authority: VariationAuthorityState,
    pub config: PipelineConfig,
    pub document: Option<VisibleDocument>,
    pub phase: PipelinePhase,
    pub action: Option<EffectAction>,
    pub delivery: Option<CompiledDelivery>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hole_completion_check: Option<serde_json::Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sketch: Option<SketchRecord>,
    /// A compiled Stage 1 candidate kept while the reader is asked once about
    /// its layers drawn only in the colour the canvas shows under them. It is
    /// committed when that request fails.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stage1_fallback: Option<VisibleDocument>,
    /// The plan of the kept candidate, composed when the candidate is committed.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stage1_fallback_plan: Option<WorkPlan>,
    /// A settled Stage 1 result waiting for its composition reading.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub composition: Option<PendingComposition>,
    /// A composed document waiting for its laws.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub laws: Option<PendingLaws>,
    /// A document waiting for its colors.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub colors: Option<PendingColors>,
    /// The record of the ranges completions wrote into this work's DDL (A3):
    /// a host keeps it with each saved work and brings it back with a direct
    /// DDL from that work. Absent when there is none.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub completion_ranges: Option<CompletionRangeRecord>,
    /// The record of the layers the laws stage placed in this work's DDL
    /// (2026-10-20): a host keeps it with each saved work, brings it back with
    /// a direct DDL from that work, and gives it to "change the layout".
    /// Absent when there is none.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub laws_layers: Option<LawsLayerRecord>,
    /// What this work's laws were applied to (2026-10-20): made when the laws
    /// stage applies its laws, its digest filled when the run commits, and
    /// given back as it came by a direct DDL run. A host keeps it with each
    /// saved work beside the layers record.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub laws_basis: Option<LawsBasis>,
    /// Present in a run of the laws stage from a saved work: the refinement's
    /// direction, which the laws read, and the mark that the run commits as a
    /// DDL edit and stops rather than commit its base unchanged.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub laws_move: Option<LawsMove>,
    pub snapshot_digest: String,
}

/// A run of the laws stage from a saved work (2026-10-20).
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LawsMove {
    #[serde(default)]
    pub direction: LawsDirection,
}

/// The provider attempt a host is running, for showing retry progress.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ProviderAttempt {
    /// The effect tag, such as `generate_normalized_ddl` for Stage 1.
    pub action: &'static str,
    /// One-based number of the running attempt.
    pub attempt: u32,
    /// The most attempts the stage's retry policy allows.
    pub max_attempts: u32,
    /// The wait before the attempt starts.
    pub delay_ms: DecimalU64,
    /// The time the attempt may take, already capped by the stage's total budget.
    pub timeout_ms: DecimalU64,
    /// Whether this attempt asks the completion once more because the check
    /// refused a proposal, rather than retrying after a failure (A1, 2026-10-06).
    /// Present only when true.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub asked_again: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StepOutput {
    pub snapshot: PipelineSnapshot,
    pub events: Vec<PipelineEvent>,
    pub rendered: Option<inku_render::types::RenderOutput>,
}

impl PipelineSnapshot {
    fn seal(&mut self) -> Result<(), ProtocolError> {
        self.snapshot_digest.clear();
        self.snapshot_digest = value_digest("inku.pipeline-snapshot.v1", self)?;
        Ok(())
    }

    fn validate(&self) -> Result<(), ProtocolError> {
        if self.protocol != PROTOCOL_NAME || self.version != PROTOCOL_VERSION {
            return Err(ProtocolError::ProtocolMismatch);
        }
        let mut copy = self.clone();
        copy.seal()?;
        if copy.snapshot_digest != self.snapshot_digest {
            return Err(ProtocolError::StaleResult);
        }
        // A saved document of a retired edition is migrated by its host before anything else.
        let phase_document = match &self.phase {
            PipelinePhase::AwaitingVisibleDdlCommit { document, .. } => Some(document),
            PipelinePhase::AwaitingPatchApproval { candidate, .. } => Some(candidate),
            _ => None,
        };
        for document in [
            self.document.as_ref(),
            self.stage1_fallback.as_ref(),
            self.composition.as_ref().map(|pending| &pending.document),
            self.laws.as_ref().map(|pending| &pending.document),
            self.colors.as_ref().map(|pending| &pending.document),
            phase_document,
        ]
        .into_iter()
        .flatten()
        {
            document.require_current_saijiki()?;
        }
        self.config.validate()?;
        if self.stage1_fallback_plan.is_some() && self.stage1_fallback.is_none() {
            return Err(ProtocolError::InvalidState);
        }
        if let Some(pending) = &self.composition {
            pending.document.document()?;
            if !matches!(
                self.phase,
                PipelinePhase::AwaitingLlm {
                    stage: LlmStage::ReadComposition,
                    ..
                }
            ) {
                return Err(ProtocolError::InvalidState);
            }
        }
        if let Some(pending) = &self.laws {
            pending.document.document()?;
            if !matches!(
                self.phase,
                PipelinePhase::AwaitingLlm {
                    stage: LlmStage::ChooseLaws,
                    ..
                }
            ) {
                return Err(ProtocolError::InvalidState);
            }
        }
        if let Some(pending) = &self.colors {
            pending.document.document()?;
            if !matches!(
                self.phase,
                PipelinePhase::AwaitingLlm {
                    stage: LlmStage::ChooseColors,
                    ..
                }
            ) {
                return Err(ProtocolError::InvalidState);
            }
        }
        if let Some(fallback) = &self.stage1_fallback {
            fallback.document()?;
            if !matches!(
                self.phase,
                PipelinePhase::AwaitingLlm {
                    stage: LlmStage::GenerateNormalizedDdl,
                    ..
                }
            ) {
                return Err(ProtocolError::InvalidState);
            }
        }
        if let Some(delivery) = &self.delivery {
            delivery
                .validate()
                .map_err(|_| ProtocolError::SemanticViolation)?;
            if delivery.compiler_options != self.config.compiler
                || self
                    .document
                    .as_ref()
                    .map(VisibleDocument::source_digest)
                    .as_deref()
                    != Some(delivery.source_digest.as_str())
                || !matches!(
                    self.phase,
                    PipelinePhase::AwaitingLlm {
                        stage: LlmStage::CompleteVisibleDdlHoles,
                        ..
                    } | PipelinePhase::AwaitingVisibleDdlCommit { .. }
                        | PipelinePhase::AwaitingPatchApproval { .. }
                        | PipelinePhase::ScoreReady
                        | PipelinePhase::Completed
                        | PipelinePhase::NeedsUserEdit { .. }
                        | PipelinePhase::Failed { .. }
                )
            {
                return Err(ProtocolError::StaleResult);
            }
        }
        if matches!(
            self.phase,
            PipelinePhase::ScoreReady | PipelinePhase::Completed
        ) && self
            .delivery
            .as_ref()
            .is_none_or(|delivery| delivery.score.is_none())
        {
            return Err(ProtocolError::InvalidState);
        }
        match (&self.phase, &self.action) {
            (PipelinePhase::AwaitingLlm { stage, .. }, Some(action))
                if action.tag == stage.action_name()
                    && action.identity.attempt > 0
                    && action.identity.attempt <= self.retry_policy(*stage).max_attempts => {}
            (
                PipelinePhase::AwaitingVisibleDdlCommit {
                    authority,
                    document,
                    ..
                },
                Some(action),
            ) if action.tag == "commit_visible_normalized_ddl"
                && action.identity.attempt == 1
                && authority.expected_revision == self.authority.revision()
                && action
                    .payload
                    .get("ddl_digest")
                    .and_then(serde_json::Value::as_str)
                    == Some(document.source_digest().as_str()) => {}
            (
                PipelinePhase::AwaitingLlm { .. } | PipelinePhase::AwaitingVisibleDdlCommit { .. },
                _,
            ) => return Err(ProtocolError::InvalidState),
            (_, None) => {}
            (_, Some(_)) => return Err(ProtocolError::InvalidState),
        }
        if let Some(action) = &self.action {
            let request_digest = value_digest("inku.pipeline-request.v1", &action.payload)?;
            let ordinal = self.action_ordinal.get().to_string();
            let action_id = digest(
                "inku.pipeline-action.v1",
                &[
                    self.execution_id.as_bytes(),
                    action.tag.as_bytes(),
                    ordinal.as_bytes(),
                    request_digest.as_bytes(),
                ],
            );
            if action.version != 1
                || action.identity.request_digest != request_digest
                || action.identity.action_id != action_id
            {
                return Err(ProtocolError::StaleResult);
            }
        }
        Ok(())
    }

    fn event(
        &mut self,
        events: &mut Vec<PipelineEvent>,
        tag: &str,
        payload: serde_json::Value,
    ) -> Result<(), ProtocolError> {
        self.event_sequence = self.event_sequence.checked_next()?;
        events.push(PipelineEvent {
            tag: tag.into(),
            version: 1,
            sequence: self.event_sequence,
            payload,
        });
        Ok(())
    }

    fn revision(&self, expected: DecimalU64) -> Result<(), ProtocolError> {
        if expected.get() == self.authority.revision() {
            Ok(())
        } else {
            Err(ProtocolError::AuthorityConflict)
        }
    }

    fn editable(&self) -> Result<(), ProtocolError> {
        match self.phase {
            PipelinePhase::AuthoringStarted
            | PipelinePhase::ScoreReady
            | PipelinePhase::Completed
            | PipelinePhase::NeedsUserEdit { .. }
            | PipelinePhase::Failed { .. } => Ok(()),
            _ => Err(ProtocolError::InvalidState),
        }
    }

    fn new_document(&self, source: String) -> Result<VisibleDocument, ProtocolError> {
        if source.len() > self.config.prompt_limits.max_source_bytes {
            return Err(ProtocolError::SchemaViolation);
        }
        let mut locks = Vec::new();
        for definition in &self.config.definitions {
            let identity = definition
                .identity()
                .map_err(|_| ProtocolError::SchemaViolation)?;
            locks.push(LockedDefinition {
                qualified_name: identity.qualified_name().to_owned(),
                version: identity.version().to_owned(),
                digest: format!("sha256:{}", identity.full_digest_hex()),
                aliases: definition.alias_qualified_names(),
            });
        }
        let wire = VisibleDocument {
            source,
            language: self.config.language,
            macro_locks: locks,
            saijiki: SAIJIKI_ASSET_ID.to_owned(),
        };
        Ok(VisibleDocument::from_document(&wire.document()?))
    }

    fn issue(
        &mut self,
        tag: &str,
        payload: serde_json::Value,
        timeout_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.issue_attempt(tag, payload, timeout_ms, 1, events)
    }

    fn issue_attempt(
        &mut self,
        tag: &str,
        payload: serde_json::Value,
        timeout_ms: u64,
        attempt: u32,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.action_ordinal = self.action_ordinal.checked_next()?;
        let request_digest = value_digest("inku.pipeline-request.v1", &payload)?;
        let ordinal = self.action_ordinal.get().to_string();
        let action_id = digest(
            "inku.pipeline-action.v1",
            &[
                self.execution_id.as_bytes(),
                tag.as_bytes(),
                ordinal.as_bytes(),
                request_digest.as_bytes(),
            ],
        );
        self.action = Some(EffectAction {
            tag: tag.into(),
            version: 1,
            identity: ActionEcho {
                action_id,
                attempt,
                request_digest,
            },
            timeout_ms: DecimalU64::new(timeout_ms),
            delay_ms: DecimalU64::new(0),
            payload,
        });
        self.event(
            events,
            "effect_requested",
            json!({"tag": tag, "identity": self.action.as_ref().unwrap().identity}),
        )
    }

    fn commit_document(
        &mut self,
        document: VisibleDocument,
        authority: AuthorityTransitionProposal,
        reason: &str,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if reason != "user_approved_patch" {
            self.hole_completion_check = None;
        }
        self.stage1_fallback = None;
        self.stage1_fallback_plan = None;
        self.composition = None;
        self.laws = None;
        self.colors = None;
        let payload = json!({
            "variation_id": self.variation_id,
            "document": document,
            "ddl_digest": document.source_digest(),
            "authority": authority,
            "authority_digest": value_digest("inku.variation-authority.v1", &authority.next_state)?,
            "reason": reason,
        });
        self.phase = PipelinePhase::AwaitingVisibleDdlCommit {
            document,
            authority,
            reason: reason.into(),
            completion_ranges: None,
        };
        // The proposed bytes are not authoritative until the host ACK. Keep
        // the last acknowledged delivery available if that compare-and-set
        // fails; the ACK branch replaces it from the newly committed source.
        self.event(events, "visible_ddl_ready", payload.clone())?;
        self.issue("commit_visible_normalized_ddl", payload, 0, events)
    }

    fn retry_policy(&self, stage: LlmStage) -> RetryPolicy {
        match stage {
            LlmStage::GenerateSketch => self
                .config
                .sketch_retry
                .unwrap_or(self.config.catalog_retry),
            LlmStage::SelectDescriptionCatalog => self.config.catalog_retry,
            LlmStage::GenerateNormalizedDdl => self.config.stage1_retry,
            LlmStage::CompleteVisibleDdlHoles => self.config.hole_retry,
            LlmStage::ReadComposition => self
                .config
                .composition_retry
                .unwrap_or(self.config.catalog_retry),
            LlmStage::ChooseLaws => self.config.laws_retry.unwrap_or(self.config.catalog_retry),
            LlmStage::ChooseColors => self
                .config
                .colors_retry
                .unwrap_or(self.config.catalog_retry),
        }
    }

    fn begin_llm(
        &mut self,
        prompt: LlmPrompt,
        description: Option<String>,
        hole_ids: Vec<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let stage = prompt.stage;
        let policy = self.retry_policy(stage);
        self.phase = PipelinePhase::AwaitingLlm {
            stage,
            description,
            hole_ids,
            elapsed_ms: DecimalU64::new(0),
        };
        if stage != LlmStage::CompleteVisibleDdlHoles {
            self.delivery = None;
        }
        self.issue(
            stage.action_name(),
            json!({"prompt": prompt, "policy": policy}),
            policy.remaining_attempt_timeout(0),
            events,
        )
    }
}

fn proposal(
    outcome: AuthorityTransitionOutcome,
) -> Result<Option<AuthorityTransitionProposal>, ProtocolError> {
    match outcome.result {
        AuthorityTransitionResult::Proposed { proposal, .. } => Ok(Some(proposal)),
        AuthorityTransitionResult::NoChange { .. } => Ok(None),
        AuthorityTransitionResult::Conflict { .. } => Err(ProtocolError::AuthorityConflict),
        AuthorityTransitionResult::Forbidden { .. } => Err(ProtocolError::DescriptionLocked),
        AuthorityTransitionResult::CompatibilityRequired { .. } => {
            Err(ProtocolError::CompatibilityRequired)
        }
        AuthorityTransitionResult::RevisionExhausted { .. } => {
            Err(ProtocolError::SequenceExhausted)
        }
    }
}

/// How much a compile diagnosed or left out: the document the laws printed is
/// committed only when it adds none to the composed document's.
fn shortfalls(compiled: &CompilerResourceExecutionResult) -> usize {
    compiled.upstream_diagnostics().len()
        + compiled.downstream_diagnostics().len()
        + compiled.resource_omissions().len()
        + compiled.relation_omissions().len()
}

/// The source instruction a compile could not hold on the canvas: a mark at a
/// numeric point lies wholly on it, where a named range lets the canvas cut it.
fn off_canvas_instruction(compiled: &CompilerResourceExecutionResult) -> Option<usize> {
    if let Some(CompilerResourceExecutionFailure::Materialization(
        ScoreMaterializationError::Geometry {
            owner,
            reason: ScoreFieldGap::GeometryExtentOutOfBounds,
        },
    )) = compiled.failure()
        && let ScoreInstructionOrigin::SourceInstruction { instruction_index } = **owner
    {
        return Some(instruction_index);
    }
    compiled
        .downstream_diagnostics()
        .iter()
        .find_map(|diagnostic| match (&diagnostic.reason, &diagnostic.owner) {
            (
                ScoreFieldGap::GeometryExtentOutOfBounds,
                ScoreDiagnosticOwner::SourceInstruction {
                    instruction_index, ..
                },
            ) => Some(*instruction_index),
            _ => None,
        })
}

impl PipelineSnapshot {
    /// The provider attempt in flight, or `None` while no provider effect runs.
    ///
    /// The core keeps no wall clock, so a host turns `delay_ms` and
    /// `timeout_ms` into a deadline from the time it started the attempt.
    pub fn provider_attempt(&self) -> Result<Option<ProviderAttempt>, ProtocolError> {
        self.validate()?;
        Ok(match (&self.phase, &self.action) {
            (PipelinePhase::AwaitingLlm { stage, .. }, Some(action))
                if action.tag == stage.action_name() =>
            {
                Some(ProviderAttempt {
                    action: stage.action_name(),
                    attempt: action.identity.attempt,
                    max_attempts: self.retry_policy(*stage).max_attempts,
                    delay_ms: action.delay_ms,
                    timeout_ms: action.timeout_ms,
                    asked_again: *stage == LlmStage::CompleteVisibleDdlHoles
                        && action.payload["prompt"]["message"]
                            .as_str()
                            .and_then(|message| {
                                serde_json::from_str::<serde_json::Value>(message).ok()
                            })
                            .is_some_and(|message| message.get("completion_feedback").is_some()),
                })
            }
            _ => None,
        })
    }
}

impl PipelineConfig {
    fn validate(&self) -> Result<(), ProtocolError> {
        self.envelope_limits.validate()?;
        self.compiler
            .validate()
            .map_err(|_| ProtocolError::InvalidPolicy)?;
        self.catalog_retry.validate()?;
        if let Some(policy) = self.sketch_retry {
            policy.validate()?;
        }
        if let Some(policy) = self.composition_retry {
            policy.validate()?;
        }
        if let Some(policy) = self.laws_retry {
            policy.validate()?;
        }
        if let Some(policy) = self.colors_retry {
            policy.validate()?;
        }
        self.stage1_retry.validate()?;
        self.hole_retry.validate()?;
        if self.definitions.len() != self.macro_summaries.len()
            || self.definitions.len() > self.prompt_limits.max_catalog_entries
            || self.catalogs.len() > self.prompt_limits.max_catalog_entries
        {
            return Err(ProtocolError::InvalidPolicy);
        }
        let mut names = std::collections::BTreeSet::new();
        for definition in &self.definitions {
            let identity = definition.identity().map_err(|_| {
                if needs_saijiki_migration(definition) {
                    ProtocolError::SaijikiMigrationRequired
                } else {
                    ProtocolError::SchemaViolation
                }
            })?;
            if !names.insert(identity.qualified_name().to_owned()) {
                return Err(ProtocolError::SchemaViolation);
            }
        }
        let mut catalog_ids = std::collections::BTreeSet::new();
        for candidate in &self.catalogs {
            if candidate.prompt.catalog_id != candidate.resolved.resolved_catalog_id()
                || candidate.resolved.canvas_format_id() != self.compiler.host.canvas_format_id()
                || !catalog_ids.insert(candidate.prompt.catalog_id.as_str())
            {
                return Err(ProtocolError::SchemaViolation);
            }
            candidate
                .resolved
                .lowering_context()
                .map_err(|_| ProtocolError::SchemaViolation)?;
        }
        Ok(())
    }
}

impl PipelineSnapshot {
    fn stage1(
        &mut self,
        description: String,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let _ = proposal(
            self.authority
                .propose_stage1_result_commit(self.authority.revision()),
        )?;
        if self
            .sketch
            .as_ref()
            .is_some_and(|record| record.state == SketchState::Pending)
        {
            let prompt = build_sketch_prompt(
                &description,
                self.config.language,
                self.config.prompt_limits,
            )
            .map_err(|_| ProtocolError::SchemaViolation)?;
            return self.begin_llm(prompt, Some(description), Vec::new(), events);
        }
        let prompt = self.stage1_prompt(&description)?;
        self.begin_llm(prompt, Some(description), Vec::new(), events)
    }

    /// Record what the sketch did and continue to Stage 1. A sketch never stops a run.
    fn finish_sketch(
        &mut self,
        state: SketchState,
        text: Option<String>,
        description: String,
        detail: serde_json::Value,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let record = self
            .sketch
            .as_mut()
            .ok_or(ProtocolError::InternalInvariant)?;
        record.state = state;
        record.text = text;
        let mut payload = json!({"state": state, "text": record.text});
        if !detail.is_null() {
            payload["detail"] = detail;
        }
        self.event(events, "sketch_ready", payload)?;
        self.stage1(description, events)
    }

    fn stage1_prompt(&self, description: &str) -> Result<LlmPrompt, ProtocolError> {
        let macros = self
            .config
            .definitions
            .iter()
            .zip(&self.config.macro_summaries)
            .map(|(definition, summary)| MacroPromptEntry {
                definition,
                localized_summary: summary.as_str(),
            })
            .collect::<Vec<_>>();
        let context = Stage1Context {
            canvas_format_id: self.config.compiler.host.canvas_format_id().to_owned(),
            canvas_format_registry_id: self
                .config
                .compiler
                .host
                .canvas_format_registry_id()
                .to_owned(),
            canvas_format_registry_digest: self
                .config
                .compiler
                .host
                .canvas_format_registry_digest()
                .to_owned(),
            catalog_id: self.config.compiler.host.resolved_catalog_id().to_owned(),
            catalog_mode: serde_json::from_value(
                serde_json::to_value(self.config.compiler.host.catalog_mode())
                    .map_err(|_| ProtocolError::SchemaViolation)?,
            )
            .map_err(|_| ProtocolError::SchemaViolation)?,
        };
        build_stage1_prompt_for_run(
            description,
            self.sketch.as_ref().and_then(SketchRecord::stage1_text),
            self.config.language,
            &context,
            &macros,
            self.config.prompt_limits,
            self.config.composition.is_some(),
        )
        .map_err(|_| ProtocolError::SchemaViolation)
    }

    fn correct_stage1(
        &mut self,
        compiled: &TypedDdlCompilation,
        description: String,
        elapsed_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<bool, ProtocolError> {
        let policy = self.config.stage1_retry;
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        let Some(next) = policy.next_budgeted_attempt(attempt, elapsed_ms) else {
            return Ok(false);
        };
        let Ok(prompt) = with_stage1_compiler_feedback(
            self.stage1_prompt(&description)?,
            compiled,
            self.config.prompt_limits,
        ) else {
            return Ok(false);
        };
        self.reissue_stage1(prompt, description, elapsed_ms, next, events)?;
        self.event(
            events,
            "retry_scheduled",
            json!({
                "identity": self.action.as_ref().unwrap().identity,
                "failure": ProviderFailure::SemanticViolation,
                "detail": stage1_compiler_failure_detail(compiled),
            }),
        )?;
        Ok(true)
    }

    /// Ask the reader once more when a compiled candidate draws layers only in
    /// the colour the canvas shows under them, which are not seen on the bare
    /// ground. The candidate is kept and committed if that request fails.
    fn return_ground_coloured_layers(
        &mut self,
        candidate: &VisibleDocument,
        plan: Option<&WorkPlan>,
        description: String,
        elapsed_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<bool, ProtocolError> {
        if self.stage1_fallback.is_some() {
            return Ok(false);
        }
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        let Some(next) = self
            .config
            .stage1_retry
            .next_budgeted_attempt(attempt, elapsed_ms)
        else {
            return Ok(false);
        };
        let Ok(Some(found)) = crate::core_boundary::ground_coloured_sentences(
            candidate.document()?,
            &self.config.definitions,
            &self.config.compiler,
        ) else {
            return Ok(false);
        };
        let Ok(prompt) = with_stage1_background_feedback(
            self.stage1_prompt(&description)?,
            &candidate.source,
            found.background,
            found.ground,
            &found.sentences,
            &found.mark_colours,
            self.config.compiler.host.background(),
            self.config.prompt_limits,
        ) else {
            return Ok(false);
        };
        self.reissue_stage1(prompt, description, elapsed_ms, next, events)?;
        self.stage1_fallback = Some(candidate.clone());
        self.stage1_fallback_plan = plan.cloned();
        let mut returned = json!({
            "identity": self.action.as_ref().unwrap().identity,
            "reason": "ground_coloured_layers",
            "background": found.background,
            "layers": found.sentences.len(),
        });
        // A support that covers the background is named; where the background
        // shows, the event is as before.
        if let Some(ground) = found.ground {
            returned["ground"] = json!(ground);
        }
        self.event(events, "stage1_returned", returned)?;
        Ok(true)
    }

    /// Send a changed Stage 1 request as the next attempt of the stage budget.
    fn reissue_stage1(
        &mut self,
        prompt: LlmPrompt,
        description: String,
        elapsed_ms: u64,
        attempt: u32,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.reissue(
            LlmStage::GenerateNormalizedDdl,
            prompt,
            description,
            elapsed_ms,
            attempt,
            events,
        )
    }

    /// Send a changed request of a stage as the next attempt of its budget.
    fn reissue(
        &mut self,
        stage: LlmStage,
        prompt: LlmPrompt,
        description: String,
        elapsed_ms: u64,
        attempt: u32,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let policy = self.retry_policy(stage);
        let total = elapsed_ms
            .checked_add(policy.retry_delay_ms.get())
            .ok_or(ProtocolError::InvalidPolicy)?;
        self.phase = PipelinePhase::AwaitingLlm {
            stage,
            description: Some(description),
            hole_ids: Vec::new(),
            elapsed_ms: DecimalU64::new(total),
        };
        // A changed request gets a new action identity but keeps the stage budget.
        self.issue_attempt(
            stage.action_name(),
            json!({"prompt": prompt, "policy": policy}),
            policy.remaining_attempt_timeout(total),
            attempt,
            events,
        )?;
        self.action.as_mut().unwrap().delay_ms = policy.retry_delay_ms;
        Ok(())
    }

    /// Commit the kept candidate after the returned request failed.
    fn commit_stage1_fallback(
        &mut self,
        detail: serde_json::Value,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let document = self
            .stage1_fallback
            .take()
            .ok_or(ProtocolError::InternalInvariant)?;
        let plan = self.stage1_fallback_plan.take();
        let description = match &self.phase {
            PipelinePhase::AwaitingLlm { description, .. } => description.clone(),
            _ => None,
        };
        self.event(events, "stage1_fallback", detail)?;
        self.settle_stage1(document, plan, "stage1_generated", description, events)
    }

    /// Commit a settled Stage 1 result. When the run composes, the plan's layers
    /// are placed first: from a composition reading when the run sends one,
    /// otherwise from the default reading.
    fn settle_stage1(
        &mut self,
        candidate: VisibleDocument,
        plan: Option<WorkPlan>,
        reason: &str,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        // A kept candidate answers only a returned Stage 1 request; once Stage 1
        // settles it ends, also when the composition reading comes next.
        self.stage1_fallback = None;
        self.stage1_fallback_plan = None;
        let (Some(config), Some(plan)) = (
            self.config.composition,
            plan.filter(|plan| !plan.layers.is_empty()),
        ) else {
            return self.commit_stage1(candidate, reason, events);
        };
        if config.read
            && let Some(description) = description.clone()
        {
            let plugins = crate::prompts::work_plan_plugins(&self.config.definitions);
            match build_composition_reading_prompt(
                &description,
                &plan,
                &plugins,
                self.config.language,
                self.config.prompt_limits,
            ) {
                Ok(prompt) => {
                    self.composition = Some(PendingComposition {
                        plan,
                        document: candidate,
                        reason: reason.to_owned(),
                    });
                    return self.begin_llm(prompt, Some(description), Vec::new(), events);
                }
                Err(_) => {
                    self.event(events, "composition_fallback", json!({"failure": "prompt"}))?;
                }
            }
        }
        let reading = composition::default_reading(&plan.layers);
        self.compose_and_commit(candidate, plan, reading, reason, description, events)
    }

    fn commit_stage1(
        &mut self,
        document: VisibleDocument,
        reason: &str,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if let Some(basis) = self
            .laws_basis
            .as_mut()
            .filter(|basis| basis.committed_digest.is_empty())
        {
            basis.committed_digest = document.source_digest();
        }
        // The laws stage from a saved work edits a DDL, as "change the layout" does.
        let outcome = if self.laws_move.is_some() {
            self.authority
                .propose_committed_user_ddl_mutation(self.authority.revision(), true)
        } else {
            self.authority
                .propose_stage1_result_commit(self.authority.revision())
        };
        let next = proposal(outcome)?.ok_or(ProtocolError::InternalInvariant)?;
        self.commit_document(document, next, reason, events)
    }

    /// Read the composition reply, check it against the plan and commit the
    /// composed document. A reply that cannot be read is a schema violation of
    /// the reading stage: retried within its budget, then the default reading.
    fn composition_response(
        &mut self,
        response: &str,
        spent_ms: u64,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let pending = self
            .composition
            .as_ref()
            .ok_or(ProtocolError::InternalInvariant)?;
        let Ok(parsed) = parse_composition_reading_response(
            response,
            pending.plan.layers.len(),
            self.config.prompt_limits,
        ) else {
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        };
        let text = description.clone().unwrap_or_default();
        let quoted = |_: usize, words: &str| text.contains(words);
        let Ok((reading, findings)) =
            composition::check(&parsed.reading, &pending.plan.layers, Some(&quoted))
        else {
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        };
        self.action = None;
        let pending = self
            .composition
            .take()
            .ok_or(ProtocolError::InternalInvariant)?;
        let codes: Vec<&str> = findings.iter().map(|finding| finding.code).collect();
        self.event(events, "composition_read", json!({"findings": codes}))?;
        self.compose_and_commit(
            pending.document,
            pending.plan,
            reading,
            &pending.reason,
            description,
            events,
        )
    }

    /// Place the plan's layers from a checked reading and commit the composed
    /// document. When the plan cannot be composed, Stage 1 is committed as it
    /// printed it and an event says why. A run with laws asks for them first.
    fn compose_and_commit(
        &mut self,
        candidate: VisibleDocument,
        plan: WorkPlan,
        reading: CheckedReading,
        reason: &str,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        match self.composed_document(&candidate, &plan, &reading) {
            Ok((document, composed)) if self.config.laws.is_some() => {
                self.ask_laws(document, composed, reason, description, events)
            }
            Ok((document, composed)) => self.after_laws(
                document,
                PrintedPlan::composed(&composed),
                LawsHandoff::default(),
                reason,
                description,
                events,
            ),
            Err(skipped) => {
                self.event(events, "composition_skipped", json!({"reason": skipped}))?;
                self.commit_stage1(candidate, reason, events)
            }
        }
    }

    fn composed_document(
        &self,
        candidate: &VisibleDocument,
        plan: &WorkPlan,
        reading: &CheckedReading,
    ) -> Result<(VisibleDocument, ComposedPlan), &'static str> {
        let background = plan.background.as_deref().unwrap_or("white");
        let searched =
            composition::search(&plan.layers, reading, background).map_err(|unsolved| {
                match unsolved {
                    composition::Unsolved::Combinations(_) => "combinations",
                    composition::Unsolved::NoRanges => "no_ranges",
                    composition::Unsolved::UnknownPlace(_) => "unknown_place",
                }
            })?;
        let composition_seed = self
            .config
            .compiler
            .composition_seed()
            .map_err(|_| "policy")?;
        let work_id = candidate.source_digest();
        let solution = composition::solve(
            &plan.layers,
            reading,
            background,
            &searched,
            composition_seed.unwrap_or(1),
            &work_id,
        )
        .map_err(|_| "unsolved")?;
        let jointed = composition::join(
            &plan.layers,
            reading,
            background,
            &solution,
            composition_seed.unwrap_or(1),
            &work_id,
        );
        // I-715 B2: a free line takes its direction from how the reading moves
        // it, by the layer numbers of the plan the reading saw.
        let plan = composition::with_free_line_angles(plan, reading);
        let (composed, ranges, joints) = composition::composed_plan_with_joints(&plan, &jointed);
        let composed = ComposedPlan {
            plan: composed,
            ranges,
            joints: joints
                .into_iter()
                .map(|joint| joint.map(str::to_owned))
                .collect(),
        };
        let plugins = crate::prompts::work_plan_plugins(&self.config.definitions);
        let source = composed.source(self.config.language, &plugins);
        let document = self.new_document(source).map_err(|_| "document")?;
        let compiled = compile_typed_ddl(
            document.document().map_err(|_| "document")?,
            &self.config.definitions,
            composition_seed,
            self.config.compiler.macro_limits().map_err(|_| "policy")?,
        );
        if !compiled
            .compiler_lock
            .as_ref()
            .is_some_and(|lock| lock.state == CompilerLockState::CanonicalReady)
        {
            return Err("compile");
        }
        Ok((document, composed))
    }

    /// Start the laws stage from a saved work (the AI refinement's laws move,
    /// 2026-10-20). Its base is the composed document the work keeps, while the
    /// work's DDL is still the one that run committed, else its DDL when it has
    /// no laws. The base is read back as the plan it was printed from, which
    /// must draw what the base draws, and the laws are asked for as a
    /// description run asks for them, with the refinement's direction. A work
    /// that cannot take them stops with the reason, before any request.
    fn saved_laws(
        &mut self,
        work: SavedWork,
        direction: LawsDirection,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if matches!(
            self.config.compiler.host.catalog_mode(),
            CatalogMode::AutoSelected | CatalogMode::AutoFallbackDefault
        ) {
            return Err(ProtocolError::InvalidPolicy);
        }
        direction
            .validate()
            .map_err(|_| ProtocolError::SchemaViolation)?;
        self.completion_ranges = work.completion_ranges.filter(|record| !record.is_empty());
        self.laws_move = Some(LawsMove { direction });
        if work.description.trim().is_empty() {
            return self.fail_laws_move("no_description", None, events);
        }
        let recorded = work.laws_layers.filter(|record| !record.is_empty());
        let base = match (work.laws_basis, recorded) {
            (Some(basis), _) => {
                if self.new_document(work.source)?.source_digest() != basis.committed_digest {
                    return self.fail_laws_move("laws_basis_stale", None, events);
                }
                basis.composed
            }
            (None, Some(_)) => return self.fail_laws_move("laws_without_basis", None, events),
            (None, None) => work.source,
        };
        let document = self.new_document(base)?;
        let plugins = crate::prompts::work_plan_plugins(&self.config.definitions);
        let limits = self
            .config
            .compiler
            .macro_limits()
            .map_err(|_| ProtocolError::InvalidPolicy)?;
        let composed = match crate::laws_entry::composed_plan_of(
            &document.source,
            self.config.language,
            &self.config.definitions,
            limits,
            &plugins,
        ) {
            Ok(composed) => composed,
            Err(reason) => return self.fail_laws_move(reason, None, events),
        };
        if !self.draws_alike(&document, composed.source(self.config.language, &plugins)) {
            return self.fail_laws_move("not_faithful", None, events);
        }
        self.ask_laws(
            document,
            composed,
            "saved_laws",
            Some(work.description),
            events,
        )
    }

    /// Whether a plan's print draws what the base draws: the same text, or the
    /// same Score as the run compiles both.
    fn draws_alike(&self, base: &VisibleDocument, printed: String) -> bool {
        if base.source == printed {
            return true;
        }
        let Ok(printed) = self.new_document(printed) else {
            return false;
        };
        match (self.compile_for_run(base), self.compile_for_run(&printed)) {
            (Some(base), Some(printed)) => {
                base.score().is_some() && base.score() == printed.score()
            }
            _ => false,
        }
    }

    /// Stop the laws stage from a saved work with its reason: such a run
    /// commits only a document its laws printed, never its base unchanged.
    fn fail_laws_move(
        &mut self,
        reason: &str,
        detail: Option<&str>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.action = None;
        self.laws = None;
        self.laws_basis = None;
        self.phase = PipelinePhase::Failed {
            reason: reason.to_owned(),
        };
        let mut payload = json!({"stage": LlmStage::ChooseLaws, "reason": reason});
        if let Some(detail) = detail {
            payload["detail"] = json!(detail);
        }
        self.event(events, "failed", payload)
    }

    /// Ask for the laws of a composed document (stage B-2c). When the request
    /// cannot be built (no description, a Score the laws cannot read, no law
    /// that takes a layer of the work), the composed document is committed;
    /// the laws stage from a saved work stops instead.
    fn ask_laws(
        &mut self,
        document: VisibleDocument,
        composed: ComposedPlan,
        reason: &str,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let context = description
            .as_ref()
            .and_then(|_| self.laws_context(&document, &composed))
            .map(|(context, _)| context);
        let prompt =
            description
                .as_deref()
                .zip(context.as_ref())
                .and_then(|(description, context)| {
                    laws::build_laws_prompt(
                        description,
                        context,
                        self.config.language,
                        self.config.prompt_limits,
                    )
                    .ok()
                });
        let Some(prompt) = prompt else {
            if self.laws_move.is_some() {
                let reason = if context.is_none() {
                    "laws_context"
                } else {
                    "no_law"
                };
                return self.fail_laws_move(reason, None, events);
            }
            self.event(events, "laws_fallback", json!({"failure": "prompt"}))?;
            let printed = PrintedPlan::composed(&composed);
            return self.after_laws(
                document,
                printed,
                LawsHandoff::default(),
                reason,
                description,
                events,
            );
        };
        self.laws = Some(PendingLaws {
            composed,
            document,
            reason: reason.to_owned(),
            refused: Vec::new(),
        });
        self.begin_llm(prompt, description, Vec::new(), events)
    }

    /// What the laws read of a composed document: its Score as the run compiles
    /// it, and how much that compile diagnosed or left out (`shortfalls`).
    fn laws_context(
        &self,
        document: &VisibleDocument,
        composed: &ComposedPlan,
    ) -> Option<(LawsContext, usize)> {
        let compiled = self.compile_for_run(document)?;
        let context = LawsContext::new(
            compiled.score()?.clone(),
            composed,
            self.config.compiler.host.palette(),
            self.config.compiler.host.canvas_format_id(),
        )?;
        let context = match &self.laws_move {
            Some(laws_move) => context.with_direction(laws_move.direction.clone()),
            None => context,
        };
        Some((context, shortfalls(&compiled)))
    }

    /// A document compiled as the run's commit compiles it.
    fn compile_for_run(
        &self,
        document: &VisibleDocument,
    ) -> Option<CompilerResourceExecutionResult> {
        crate::core_boundary::compile_with_resources(
            document.document().ok()?,
            &self.config.definitions,
            &self.config.compiler,
        )
        .ok()
    }

    /// Read the laws reply, apply it and commit the document the laws printed.
    /// A reply the tool refuses is asked again with the reply and the reason
    /// within the stage's budget, also when the printed document cannot hold
    /// a layer the laws changed on the canvas. When the budget is spent, or the
    /// printed document does not compile as the composed one did, the composed
    /// document is committed as it is.
    fn laws_response(
        &mut self,
        response: &str,
        spent_ms: u64,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let pending = self.laws.as_ref().ok_or(ProtocolError::InternalInvariant)?;
        let Some((context, composed_shortfalls)) =
            self.laws_context(&pending.document, &pending.composed)
        else {
            return self.laws_fallback(json!({"failure": "context"}), events);
        };
        let chosen = match laws::choose_laws(
            response,
            &context,
            &pending.composed,
            self.config.prompt_limits,
        ) {
            Ok(chosen) => chosen,
            Err(refusal) => {
                let description = description.ok_or(ProtocolError::InternalInvariant)?;
                return self.ask_laws_again(
                    &context,
                    &refusal,
                    response,
                    description,
                    spent_ms,
                    events,
                );
            }
        };
        let plugins = crate::prompts::work_plan_plugins(&self.config.definitions);
        let printed = chosen.print.source(self.config.language, &plugins);
        let composed = pending.composed.source(self.config.language, &plugins);
        // A saved work keeps its own words on the lines the laws did not change.
        let printed = if self.laws_move.is_some() && composed != pending.document.source {
            crate::laws_entry::spliced(
                &pending.document.source,
                &composed,
                pending.composed.plan.layers.len(),
                &printed,
                &chosen.print,
            )
        } else {
            Some(printed)
        };
        let Some((document, compiled)) = printed.and_then(|source| self.laws_document(source))
        else {
            return self.laws_fallback(json!({"failure": "compile"}), events);
        };
        let record = laws::layers_record(&chosen, &document.source, compiled.compilation());
        if let Some(refusal) = off_canvas_instruction(&compiled)
            .and_then(|instruction| laws::off_canvas(&chosen, &context, instruction))
        {
            let description = description.ok_or(ProtocolError::InternalInvariant)?;
            return self.ask_laws_again(
                &context,
                &refusal,
                response,
                description,
                spent_ms,
                events,
            );
        }
        if compiled.score().is_none() || shortfalls(&compiled) > composed_shortfalls {
            return self.laws_fallback(json!({"failure": "compile"}), events);
        }
        self.action = None;
        let pending = self.laws.take().ok_or(ProtocolError::InternalInvariant)?;
        self.event(
            events,
            "laws_chosen",
            json!({
                "laws": chosen.laws,
                "main_law": chosen.main_law,
                "main_layer": chosen.main_layer,
                "notes": chosen.notes,
                "reason": chosen.reason,
            }),
        )?;
        self.laws_layers = record.filter(|record| !record.is_empty());
        // What the laws were applied to; its digest is the committed document's.
        self.laws_basis = Some(LawsBasis {
            composed: pending.document.source.clone(),
            committed_digest: String::new(),
            main_layer: chosen.main_layer,
            main_law: chosen.main_law.clone(),
            laws: chosen
                .values
                .iter()
                .map(|(law, value)| ((*law).to_owned(), value.clone()))
                .collect(),
            reason: chosen.reason.clone(),
        });
        let printed = PrintedPlan::laws(&chosen.print);
        let handoff = LawsHandoff::of(&chosen, pending.composed.plan.plugins.len());
        self.after_laws(
            document,
            printed,
            handoff,
            &pending.reason,
            description,
            events,
        )
    }

    /// Ask for the laws again with the refused answer and the tool's reason for
    /// refusing it, and the reasons the answers before it were refused with, as
    /// the next attempt of the stage's budget; when it is spent, commit the
    /// composed document.
    fn ask_laws_again(
        &mut self,
        context: &LawsContext,
        refusal: &laws::Refusal,
        answer: &str,
        description: String,
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let PipelinePhase::AwaitingLlm { elapsed_ms, .. } = &self.phase else {
            return Err(ProtocolError::InvalidState);
        };
        let total = elapsed_ms
            .get()
            .checked_add(spent_ms)
            .ok_or(ProtocolError::InvalidPolicy)?;
        // An answer that does not read as the requested shape is a schema
        // violation; an answer the laws' rules refuse is a semantic one.
        let failure = if matches!(
            refusal.code,
            "too_long"
                | "not_json"
                | "not_object"
                | "missing"
                | "not_array"
                | "count"
                | "not_integer"
                | "not_string"
                | "not_boolean"
                | "not_a_choice"
                | "out_of_range"
        ) {
            ProviderFailure::SchemaViolation
        } else {
            ProviderFailure::SemanticViolation
        };
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        let next = self
            .retry_policy(LlmStage::ChooseLaws)
            .next_budgeted_attempt(attempt, total);
        let earlier = &self
            .laws
            .as_ref()
            .ok_or(ProtocolError::InternalInvariant)?
            .refused;
        let prompt = next.and_then(|_| {
            laws::build_laws_prompt(
                &description,
                context,
                self.config.language,
                self.config.prompt_limits,
            )
            .and_then(|prompt| {
                laws::with_laws_feedback(
                    prompt,
                    refusal,
                    Some(answer),
                    earlier,
                    self.config.prompt_limits,
                )
            })
            .ok()
        });
        let (Some(next), Some(prompt)) = (next, prompt) else {
            return self.laws_fallback(json!({"failure": failure, "detail": refusal.code}), events);
        };
        self.reissue(
            LlmStage::ChooseLaws,
            prompt,
            description,
            total,
            next,
            events,
        )?;
        self.laws
            .as_mut()
            .ok_or(ProtocolError::InternalInvariant)?
            .refused
            .push(refusal.into());
        self.event(
            events,
            "retry_scheduled",
            json!({
                "identity": self.action.as_ref().unwrap().identity,
                "failure": failure,
                "detail": refusal.code,
            }),
        )
    }

    /// The document the laws printed and the run's compile of it, when it reads
    /// as canonically as the composed one did.
    fn laws_document(
        &self,
        source: String,
    ) -> Option<(VisibleDocument, CompilerResourceExecutionResult)> {
        let document = self.new_document(source).ok()?;
        let compiled = self.compile_for_run(&document)?;
        compiled
            .compilation()
            .compiler_lock
            .as_ref()
            .is_some_and(|lock| lock.state == CompilerLockState::CanonicalReady)
            .then_some((document, compiled))
    }

    /// Commit the composed document without laws and say why. The laws stage
    /// from a saved work stops with a reason instead: its answers refused
    /// within the budget (`laws_refused`), a print that does not compile
    /// (`laws_compile`), or a provider that could not answer
    /// (`laws_unavailable`).
    fn laws_fallback(
        &mut self,
        payload: serde_json::Value,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if self.laws_move.is_some() {
            let failure = payload["failure"].as_str().unwrap_or_default();
            let reason = match failure {
                "compile" => "laws_compile",
                "context" => "laws_context",
                "schema_violation" | "semantic_violation" => "laws_refused",
                _ => "laws_unavailable",
            };
            let detail = payload["detail"].as_str().unwrap_or(failure).to_owned();
            return self.fail_laws_move(reason, Some(&detail), events);
        }
        self.action = None;
        let pending = self.laws.take().ok_or(ProtocolError::InternalInvariant)?;
        let description = match &self.phase {
            PipelinePhase::AwaitingLlm { description, .. } => description.clone(),
            _ => None,
        };
        self.event(events, "laws_fallback", payload)?;
        let printed = PrintedPlan::composed(&pending.composed);
        self.after_laws(
            pending.document,
            printed,
            LawsHandoff::default(),
            &pending.reason,
            description,
            events,
        )
    }

    /// Commit the document the laws stage left, or ask for its colors first
    /// when the run has the color stage. The color stage runs also when the
    /// laws fell back: colors are chosen apart from the places.
    fn after_laws(
        &mut self,
        document: VisibleDocument,
        printed: PrintedPlan,
        handoff: LawsHandoff,
        reason: &str,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if self.config.colors.is_none() {
            return self.commit_stage1(document, reason, events);
        }
        let prompt = description.as_deref().and_then(|description| {
            let (context, _) = self.colors_context(&document, &printed, &handoff, description)?;
            colors::build_colors_prompt(
                description,
                &context,
                self.config.language,
                self.config.prompt_limits,
            )
            .ok()
        });
        let Some(prompt) = prompt else {
            self.event(events, "colors_fallback", json!({"failure": "prompt"}))?;
            return self.commit_stage1(document, reason, events);
        };
        self.colors = Some(PendingColors {
            printed,
            document,
            reason: reason.to_owned(),
            handoff,
        });
        self.begin_llm(prompt, description, Vec::new(), events)
    }

    /// What the colors read of the document the laws left: its Score as the
    /// run compiles it, how it is drawn, and how much that compile diagnosed
    /// or left out (`shortfalls`).
    fn colors_context(
        &self,
        document: &VisibleDocument,
        printed: &PrintedPlan,
        handoff: &LawsHandoff,
        description: &str,
    ) -> Option<(ColorsContext, usize)> {
        let compiled = self.compile_for_run(document)?;
        let seeds = crate::appearance::Seeds {
            render: self
                .config
                .colors
                .and_then(|config| config.render_seed)
                .map(|seed| i128::from(seed.get())),
            composition: self
                .config
                .compiler
                .composition_seed()
                .ok()
                .flatten()
                .map(i128::from),
        };
        let context = ColorsContext::new(colors::ColorsInput {
            score: compiled.score()?,
            printed,
            handoff,
            palette: self.config.compiler.host.palette(),
            canvas_format_id: self.config.compiler.host.canvas_format_id(),
            seeds,
            error_policy: self.config.compiler.error_policy,
            description,
        })?;
        Some((context, shortfalls(&compiled)))
    }

    /// Read the colors reply, apply it and commit the document the colors
    /// printed. A reply the tool refuses is asked again with the reason within
    /// the stage's budget. When the budget is spent, or the printed document
    /// does not compile to the colors chosen as the document before did, the
    /// document the laws left is committed as it is.
    fn colors_response(
        &mut self,
        response: &str,
        spent_ms: u64,
        description: Option<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let pending = self
            .colors
            .as_ref()
            .ok_or(ProtocolError::InternalInvariant)?;
        let Some(text) = description.clone() else {
            return self.colors_fallback(json!({"failure": "context"}), events);
        };
        let Some((context, before_shortfalls)) =
            self.colors_context(&pending.document, &pending.printed, &pending.handoff, &text)
        else {
            return self.colors_fallback(json!({"failure": "context"}), events);
        };
        let chosen = match colors::choose_colors(response, &context, self.config.prompt_limits) {
            Ok(chosen) => chosen,
            Err(refusal) => {
                return self.ask_colors_again(&context, &refusal, text, spent_ms, events);
            }
        };
        let plugins = crate::prompts::work_plan_plugins(&self.config.definitions);
        let Some((document, compiled)) =
            self.laws_document(chosen.print.printed.source(self.config.language, &plugins))
        else {
            return self.colors_fallback(json!({"failure": "compile"}), events);
        };
        if compiled
            .score()
            .is_none_or(|score| !chosen.compiled_as_chosen(score))
            || shortfalls(&compiled) > before_shortfalls
        {
            return self.colors_fallback(json!({"failure": "compile"}), events);
        }
        self.action = None;
        let pending = self.colors.take().ok_or(ProtocolError::InternalInvariant)?;
        self.event(
            events,
            "colors_chosen",
            json!({
                "laws": chosen.laws,
                "main_law": chosen.main_law,
                "main_layer": chosen.main_layer,
                "notes": chosen.notes,
            }),
        )?;
        if let Some(record) = &self.laws_layers {
            let record = colors::reprinted_record(
                record,
                &chosen.print,
                &pending.document.source,
                &document.source,
            );
            self.laws_layers = Some(record).filter(|record| !record.is_empty());
        }
        self.commit_stage1(document, &pending.reason, events)
    }

    /// Ask for the colors again with the tool's reason for refusing the answer,
    /// as the next attempt of the stage's budget; when it is spent, commit the
    /// document the laws left.
    fn ask_colors_again(
        &mut self,
        context: &ColorsContext,
        refusal: &laws::Refusal,
        description: String,
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let PipelinePhase::AwaitingLlm { elapsed_ms, .. } = &self.phase else {
            return Err(ProtocolError::InvalidState);
        };
        let total = elapsed_ms
            .get()
            .checked_add(spent_ms)
            .ok_or(ProtocolError::InvalidPolicy)?;
        // An answer that does not read as the requested shape is a schema
        // violation; an answer the colors' rules refuse is a semantic one.
        let failure = if matches!(
            refusal.code,
            "too_long"
                | "not_json"
                | "not_object"
                | "missing"
                | "not_array"
                | "count"
                | "not_integer"
                | "not_string"
                | "not_boolean"
                | "not_a_choice"
                | "out_of_range"
        ) {
            ProviderFailure::SchemaViolation
        } else {
            ProviderFailure::SemanticViolation
        };
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        let next = self
            .retry_policy(LlmStage::ChooseColors)
            .next_budgeted_attempt(attempt, total);
        let prompt = next.and_then(|_| {
            colors::build_colors_prompt(
                &description,
                context,
                self.config.language,
                self.config.prompt_limits,
            )
            .and_then(|prompt| {
                colors::with_colors_feedback(prompt, refusal, self.config.prompt_limits)
            })
            .ok()
        });
        let (Some(next), Some(prompt)) = (next, prompt) else {
            return self
                .colors_fallback(json!({"failure": failure, "detail": refusal.code}), events);
        };
        self.reissue(
            LlmStage::ChooseColors,
            prompt,
            description,
            total,
            next,
            events,
        )?;
        self.event(
            events,
            "retry_scheduled",
            json!({
                "identity": self.action.as_ref().unwrap().identity,
                "failure": failure,
                "detail": refusal.code,
            }),
        )
    }

    /// Commit the document the laws left without colors and say why.
    fn colors_fallback(
        &mut self,
        payload: serde_json::Value,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.action = None;
        let pending = self.colors.take().ok_or(ProtocolError::InternalInvariant)?;
        self.event(events, "colors_fallback", payload)?;
        self.commit_stage1(pending.document, &pending.reason, events)
    }

    fn residual_execution_preflight(&self, candidate: &VisibleDocument) -> bool {
        let Ok(document) = candidate.document() else {
            return false;
        };
        crate::core_boundary::compile_committed(
            document,
            &self.config.definitions,
            &self.config.compiler,
        )
        .is_ok_and(|delivery| delivery.residual_execution_is_deliverable())
    }

    fn description(
        &mut self,
        description: String,
        auto_catalog: bool,
        sketch: SketchRequest,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let _ = proposal(
            self.authority
                .propose_stage1_result_commit(self.authority.revision()),
        )?;
        if let SketchRequest::Supplied { text } = &sketch
            && text.len() > self.config.prompt_limits.max_source_bytes
        {
            return Err(ProtocolError::SchemaViolation);
        }
        self.sketch = SketchRecord::from_request(sketch);
        if auto_catalog {
            if !self
                .config
                .catalogs
                .iter()
                .any(|candidate| candidate.prompt.catalog_id == "default")
            {
                return Err(ProtocolError::InvalidPolicy);
            }
            let candidates = self
                .config
                .catalogs
                .iter()
                .map(|candidate| candidate.prompt.clone())
                .collect::<Vec<_>>();
            let prompt = build_catalog_selection_prompt(
                &description,
                self.config.language,
                &candidates,
                self.config.prompt_limits,
            )
            .map_err(|_| ProtocolError::SchemaViolation)?;
            self.begin_llm(prompt, Some(description), Vec::new(), events)
        } else {
            self.stage1(description, events)
        }
    }

    fn select_catalog(&mut self, id: &str, mode: CatalogMode) -> Result<(), ProtocolError> {
        let selected = self
            .config
            .catalogs
            .iter()
            .find(|candidate| candidate.prompt.catalog_id == id)
            .ok_or(ProtocolError::SemanticViolation)?;
        self.config.compiler.host = selected
            .resolved
            .clone()
            .with_catalog_mode(mode)
            .map_err(|_| ProtocolError::SchemaViolation)?;
        Ok(())
    }

    /// The committed document compiled, with the work's completion record laid
    /// over it (A3): a range whose words alone changed is a hole there.
    fn compilation(&self) -> Result<inku_ddl::TypedDdlCompilation, ProtocolError> {
        let document = self
            .document
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .document()?;
        let compilation = compile_typed_ddl(
            document,
            &self.config.definitions,
            self.config
                .compiler
                .composition_seed()
                .map_err(|_| ProtocolError::InvalidPolicy)?,
            self.config
                .compiler
                .macro_limits()
                .map_err(|_| ProtocolError::InvalidPolicy)?,
        );
        Ok(match &self.completion_ranges {
            Some(record) => with_completion_record(compilation, record, &[]),
            None => compilation,
        })
    }

    /// Keep the record entries the committed document still has (A3). A record
    /// left empty is dropped.
    fn settle_completion_ranges(&mut self) -> Result<(), ProtocolError> {
        let Some(record) = self.completion_ranges.take() else {
            return Ok(());
        };
        let settled = settle_completion_record(&self.compilation()?, &record);
        self.completion_ranges = (!settled.is_empty()).then_some(settled);
        Ok(())
    }

    fn complete_holes(
        &mut self,
        hole_ids: Vec<String>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if matches!(
            self.authority.authority(),
            crate::authority::AuthoringAuthority::LegacyUnknown
        ) {
            return Err(ProtocolError::CompatibilityRequired);
        }
        let base = self.compilation()?;
        if !visible_ddl_patch_available(&base) || hole_ids.is_empty() {
            return Err(ProtocolError::SemanticViolation);
        }
        let mut ids = std::collections::BTreeSet::new();
        let mut selected = Vec::new();
        for id in &hole_ids {
            if !ids.insert(id.as_str()) {
                return Err(ProtocolError::SchemaViolation);
            }
            selected.push(
                base.holes
                    .iter()
                    .find(|hole| &hole.id == id)
                    .ok_or(ProtocolError::SemanticViolation)?
                    .clone(),
            );
        }
        selected.sort_by_key(|hole| hole.allowed_span.start_byte);
        self.hole_completion_check = None;
        let prompt = match build_hole_completion_prompt(&base, &selected, self.config.prompt_limits)
        {
            Ok(prompt) => prompt,
            Err(crate::prompts::PromptError::LimitExceeded { .. }) => {
                let lock = base
                    .compiler_lock
                    .as_ref()
                    .ok_or(ProtocolError::InternalInvariant)?;
                let report = json!({
                    "results":selected.iter().map(|hole| json!({"hole_id":hole.id,"status":"unresolved","reason":"context_limit","source":base.document.source().get(hole.allowed_span.start_byte..hole.allowed_span.end_byte)})).collect::<Vec<_>>(),
                    "base_source_digest":lock.visible_source_digest,
                    "base_compiler_lock_digest":lock.full_digest,
                });
                self.hole_completion_check = Some(report.clone());
                self.event(events, "hole_completion_checked", report)?;
                self.action = None;
                self.phase = PipelinePhase::NeedsUserEdit {
                    reason: "hole_completion_context_limit".into(),
                };
                return self.event(
                    events,
                    "needs_user_edit",
                    json!({"reason":"hole_completion_context_limit"}),
                );
            }
            Err(_) => return Err(ProtocolError::SchemaViolation),
        };
        self.begin_llm(prompt, None, hole_ids, events)
    }

    fn failure(
        &mut self,
        failure: ProviderFailure,
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.failure_with_detail(failure, spent_ms, None, events)
    }

    fn failure_with_detail(
        &mut self,
        failure: ProviderFailure,
        spent_ms: u64,
        detail: Option<&str>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let PipelinePhase::AwaitingLlm {
            stage,
            description,
            hole_ids,
            elapsed_ms,
        } = self.phase.clone()
        else {
            return Err(ProtocolError::InvalidState);
        };
        if stage == LlmStage::GenerateNormalizedDdl && self.stage1_fallback.is_some() {
            // The returned request is a second chance, not the run: keep the
            // compiled candidate rather than wait for another attempt.
            let mut payload = json!({"failure": failure});
            if let Some(detail) = detail {
                payload["detail"] = json!(detail);
            }
            return self.commit_stage1_fallback(payload, events);
        }
        let policy = self.retry_policy(stage);
        let total = elapsed_ms
            .get()
            .checked_add(spent_ms)
            .ok_or(ProtocolError::InvalidPolicy)?;
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        if let Some(next) = policy.next_attempt(attempt, total, failure) {
            let total = total
                .checked_add(policy.retry_delay_ms.get())
                .ok_or(ProtocolError::InvalidPolicy)?;
            let action = self.action.as_mut().ok_or(ProtocolError::InvalidState)?;
            action.identity.attempt = next;
            action.timeout_ms = DecimalU64::new(policy.remaining_attempt_timeout(total));
            action.delay_ms = policy.retry_delay_ms;
            self.phase = PipelinePhase::AwaitingLlm {
                stage,
                description,
                hole_ids,
                elapsed_ms: DecimalU64::new(total),
            };
            let mut payload = json!({
                "identity": self.action.as_ref().unwrap().identity,
                "failure": failure,
            });
            if let Some(detail) = detail {
                payload["detail"] = json!(detail);
            }
            return self.event(events, "retry_scheduled", payload);
        }
        self.action = None;
        match stage {
            LlmStage::GenerateSketch => self.finish_sketch(
                SketchState::Fallback,
                None,
                description.ok_or(ProtocolError::InternalInvariant)?,
                json!({"failure": failure}),
                events,
            ),
            LlmStage::SelectDescriptionCatalog => {
                self.select_catalog("default", CatalogMode::AutoFallbackDefault)?;
                self.event(events, "catalog_fallback", json!({"catalog_id": "default", "catalog_mode": "auto_fallback_default", "failure": failure}))?;
                self.stage1(description.ok_or(ProtocolError::InternalInvariant)?, events)
            }
            LlmStage::GenerateNormalizedDdl => {
                self.phase = PipelinePhase::Failed {
                    reason: "stage1_failed".into(),
                };
                let mut payload = json!({"stage": stage, "reason": failure});
                if let Some(detail) = detail {
                    payload["detail"] = json!(detail);
                }
                self.event(events, "failed", payload)
            }
            LlmStage::CompleteVisibleDdlHoles => {
                self.phase = PipelinePhase::NeedsUserEdit {
                    reason: "hole_completion_failed".into(),
                };
                let mut payload = json!({"stage": stage, "reason": failure});
                if let Some(detail) = detail {
                    payload["detail"] = json!(detail);
                }
                self.event(events, "needs_user_edit", payload)
            }
            LlmStage::ReadComposition => {
                let pending = self
                    .composition
                    .take()
                    .ok_or(ProtocolError::InternalInvariant)?;
                let mut payload = json!({"failure": failure});
                if let Some(detail) = detail {
                    payload["detail"] = json!(detail);
                }
                self.event(events, "composition_fallback", payload)?;
                let reading = composition::default_reading(&pending.plan.layers);
                self.compose_and_commit(
                    pending.document,
                    pending.plan,
                    reading,
                    &pending.reason,
                    description,
                    events,
                )
            }
            LlmStage::ChooseLaws => {
                let mut payload = json!({"failure": failure});
                if let Some(detail) = detail {
                    payload["detail"] = json!(detail);
                }
                self.laws_fallback(payload, events)
            }
            LlmStage::ChooseColors => {
                let mut payload = json!({"failure": failure});
                if let Some(detail) = detail {
                    payload["detail"] = json!(detail);
                }
                self.colors_fallback(payload, events)
            }
        }
    }

    /// Ask the completion once more when the check refused a proposal (A1,
    /// 2026-10-06, the author's decision Q3). The request keeps the stage's
    /// attempt budget, as the Stage 1 compiler feedback does; when the budget is
    /// spent the first answer stands.
    fn ask_holes_again(
        &mut self,
        prompt: &LlmPrompt,
        results: &[serde_json::Value],
        proposals: &[Option<String>],
        hole_ids: &[String],
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<bool, ProtocolError> {
        let PipelinePhase::AwaitingLlm { elapsed_ms, .. } = &self.phase else {
            return Err(ProtocolError::InvalidState);
        };
        let total = elapsed_ms
            .get()
            .checked_add(spent_ms)
            .ok_or(ProtocolError::InvalidPolicy)?;
        let policy = self.config.hole_retry;
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        let Some(next) = policy.next_budgeted_attempt(attempt, total) else {
            return Ok(false);
        };
        let feedback = results
            .iter()
            .zip(proposals)
            .enumerate()
            .map(|(index, (result, proposal))| {
                let mut entry =
                    json!({"id": format!("h{}", index + 1), "status": result["status"]});
                if let Some(proposal) = proposal {
                    entry["replacement"] = json!(proposal);
                }
                if !result["reason"].is_null() {
                    entry["reason"] = result["reason"].clone();
                }
                if result["status"] == "rejected"
                    && let Some(proposal) = proposal
                {
                    let unread = self.unread_in_proposal(index, proposal);
                    if !unread.is_empty() {
                        entry["unread"] = json!(unread);
                    }
                }
                entry
            })
            .collect::<Vec<_>>();
        let Ok(asked) = with_hole_completion_feedback(
            prompt.clone(),
            json!(feedback),
            self.config.prompt_limits,
        ) else {
            return Ok(false);
        };
        let detail = results
            .iter()
            .find(|result| result["status"] == "rejected")
            .and_then(|result| result["reason"].as_str())
            .unwrap_or("holes_unresolved")
            .to_owned();
        let total = total
            .checked_add(policy.retry_delay_ms.get())
            .ok_or(ProtocolError::InvalidPolicy)?;
        self.phase = PipelinePhase::AwaitingLlm {
            stage: LlmStage::CompleteVisibleDdlHoles,
            description: None,
            hole_ids: hole_ids.to_vec(),
            elapsed_ms: DecimalU64::new(total),
        };
        self.issue_attempt(
            LlmStage::CompleteVisibleDdlHoles.action_name(),
            json!({"prompt": asked, "policy": policy}),
            policy.remaining_attempt_timeout(total),
            next,
            events,
        )?;
        self.action
            .as_mut()
            .ok_or(ProtocolError::InternalInvariant)?
            .delay_ms = policy.retry_delay_ms;
        self.event(
            events,
            "retry_scheduled",
            json!({
                "identity": self.action.as_ref().unwrap().identity,
                "failure": ProviderFailure::SemanticViolation,
                "detail": detail,
            }),
        )?;
        Ok(true)
    }

    /// The words the compiler cannot read once a refused proposal replaces its
    /// hole alone (A1 stage 3), named in the second request. The holes are in
    /// the source order the short ids use.
    fn unread_in_proposal(&self, index: usize, proposal: &str) -> Vec<String> {
        let Ok(base) = self.compilation() else {
            return vec![];
        };
        let PipelinePhase::AwaitingLlm { hole_ids, .. } = &self.phase else {
            return vec![];
        };
        let mut holes = hole_ids
            .iter()
            .filter_map(|id| base.holes.iter().find(|hole| &hole.id == id))
            .collect::<Vec<_>>();
        holes.sort_by_key(|hole| (hole.allowed_span.start_byte, hole.allowed_span.end_byte));
        let Some(hole) = holes.get(index) else {
            return vec![];
        };
        let source = base.document.source();
        let span = hole.allowed_span;
        let candidate = format!(
            "{}{}{}",
            &source[..span.start_byte],
            proposal,
            &source[span.end_byte..]
        );
        let (Ok(seed), Ok(limits)) = (
            self.config.compiler.composition_seed(),
            self.config.compiler.macro_limits(),
        ) else {
            return vec![];
        };
        let Ok(document) = NormalizedDdlDocument::new(
            candidate,
            base.document.language(),
            base.document.macro_locks().to_vec(),
        ) else {
            return vec![];
        };
        let compiled = compile_typed_ddl(document, &self.config.definitions, seed, limits);
        crate::hole_completion::unread_words(
            &compiled,
            inku_ddl::SourceSpan {
                start_byte: span.start_byte,
                end_byte: span.start_byte + proposal.len(),
            },
        )
    }

    fn hole_response(
        &mut self,
        response: &str,
        hole_ids: &[String],
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let base = self.compilation()?;
        let lock = base
            .compiler_lock
            .as_ref()
            .ok_or(ProtocolError::InternalInvariant)?;
        let prompt: LlmPrompt = serde_json::from_value(
            self.action
                .as_ref()
                .ok_or(ProtocolError::InvalidState)?
                .payload["prompt"]
                .clone(),
        )
        .map_err(|_| ProtocolError::InvalidState)?;
        if prompt.base_source_digest.as_deref() != Some(&lock.visible_source_digest)
            || prompt.base_compiler_lock_digest.as_deref() != Some(&lock.full_digest)
        {
            return Err(ProtocolError::StaleResult);
        }
        let mut holes = hole_ids
            .iter()
            .map(|id| {
                base.holes
                    .iter()
                    .find(|hole| &hole.id == id)
                    .ok_or(ProtocolError::StaleResult)
            })
            .collect::<Result<Vec<_>, _>>()?;
        holes.sort_by_key(|hole| (hole.allowed_span.start_byte, hole.allowed_span.end_byte));
        let mut results = holes
            .iter()
            .map(|hole| json!({"hole_id":hole.id,"status":"rejected","reason":"schema_violation","source":base.document.source().get(hole.allowed_span.start_byte..hole.allowed_span.end_byte)}))
            .collect::<Vec<_>>();
        let mut patch = HolePatchResponse {
            schema_id: inku_ddl::VISIBLE_DDL_PATCH_SCHEMA_ID.into(),
            base_source_digest: lock.visible_source_digest.clone(),
            base_compiler_lock_digest: lock.full_digest.clone(),
            edits: vec![],
        };
        let current = prompt.prompt_id == HOLE_COMPLETION_PROMPT_ID
            || PREVIOUS_HOLE_COMPLETION_PROMPT_IDS.contains(&prompt.prompt_id.as_str());
        // A second request carries the first answer's check; what passed then stays.
        let previous = serde_json::from_str::<serde_json::Value>(&prompt.message)
            .ok()
            .and_then(|message| message.get("completion_feedback").cloned());
        let passed = previous
            .iter()
            .flat_map(|feedback| feedback.as_array().into_iter().flatten())
            .filter(|entry| entry["status"] == "validated")
            .filter_map(|entry| {
                Some((
                    entry["id"].as_str()?.to_owned(),
                    entry["replacement"].as_str()?.to_owned(),
                ))
            })
            .collect::<BTreeMap<_, _>>();
        let mut proposals = vec![None; holes.len()];
        let parsed = if current {
            parse_hole_completion_response(response, holes.len(), self.config.prompt_limits).map(
                |response| {
                    for result in response.results {
                        let index = result.id()[1..]
                            .parse::<usize>()
                            .expect("verified local ID")
                            - 1;
                        let hole = holes[index];
                        let result = match passed.get(result.id()) {
                            Some(replacement) => HoleCompletionResult::Proposed {
                                id: result.id().to_owned(),
                                replacement: replacement.clone(),
                            },
                            None => result,
                        };
                        match result {
                            HoleCompletionResult::Proposed { replacement, .. } => {
                                let replacement =
                                    crate::hole_completion::without_repeated_sentence_end(
                                        base.document.source(),
                                        hole.allowed_span,
                                        replacement,
                                    );
                                proposals[index] = Some(replacement.clone());
                                patch.edits.push(HolePatchEditResponse {
                                    hole_id: hole.id.clone(),
                                    allowed_span: hole.allowed_span.into(),
                                    expected_range_digest: hole.expected_range_digest.clone(),
                                    replacement,
                                });
                                results[index]["status"] = json!("validated");
                                results[index]["reason"] = serde_json::Value::Null;
                            }
                            HoleCompletionResult::Unresolved { reason, .. } => {
                                results[index]["status"] = json!("unresolved");
                                results[index]["reason"] = json!(reason);
                            }
                        }
                    }
                },
            )
        } else if prompt.prompt_id == LEGACY_HOLE_COMPLETION_PROMPT_ID {
            // An already persisted v2 request keeps its exact wire contract. Never
            // try this decoder after a v3 parse or semantic failure.
            parse_hole_patch_response(response, self.config.prompt_limits).and_then(|legacy| {
                let expected = hole_ids.iter().collect::<BTreeSet<_>>();
                let actual = legacy
                    .edits
                    .iter()
                    .map(|edit| &edit.hole_id)
                    .collect::<BTreeSet<_>>();
                if legacy.schema_id != inku_ddl::VISIBLE_DDL_PATCH_SCHEMA_ID
                    || actual != expected
                    || actual.len() != legacy.edits.len()
                {
                    return Err(crate::prompts::PromptError::ResponseIdentityMismatch {
                        field: "edits.hole_id",
                    });
                }
                patch = legacy;
                for result in &mut results {
                    result["status"] = json!("validated");
                    result["reason"] = serde_json::Value::Null;
                }
                Ok(())
            })
        } else {
            return Err(ProtocolError::SchemaViolation);
        };
        if parsed.is_err() {
            let report = json!({"results":results,"base_source_digest":lock.visible_source_digest,"base_compiler_lock_digest":lock.full_digest});
            self.hole_completion_check = Some(report.clone());
            self.event(events, "hole_completion_checked", report)?;
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        }
        patch.edits.sort_by_key(|edit| edit.allowed_span.start_byte);
        let units = if current {
            crate::hole_completion::independent_units(&base, &holes)
        } else {
            vec![hole_ids.to_vec()]
        };
        let seed = self
            .config
            .compiler
            .composition_seed()
            .map_err(|_| ProtocolError::InvalidPolicy)?;
        let limits = self
            .config
            .compiler
            .macro_limits()
            .map_err(|_| ProtocolError::InvalidPolicy)?;
        let source_limit = self.config.prompt_limits.max_source_bytes;
        let mut accepted = Vec::new();
        let mut accepted_units = 0;
        let mut candidate = None;
        for unit in units {
            let edits = patch
                .edits
                .iter()
                .filter(|edit| unit.contains(&edit.hole_id))
                .cloned()
                .collect::<Vec<_>>();
            if edits.len() != unit.len() {
                for result in &mut results {
                    if unit.iter().any(|id| result["hole_id"] == *id)
                        && result["status"] == "validated"
                    {
                        result["status"] = json!("rejected");
                        result["reason"] = json!("dependency_unresolved");
                    }
                }
                continue;
            }
            let mut unit_patch = patch.clone();
            unit_patch.edits = edits;
            let size = unit_patch
                .edits
                .iter()
                .fold(base.document.source().len(), |size, edit| {
                    size.saturating_sub(
                        edit.allowed_span
                            .end_byte
                            .saturating_sub(edit.allowed_span.start_byte),
                    )
                    .saturating_add(edit.replacement.len())
                });
            let checked = if size > source_limit {
                Err(("source_limit", None))
            } else {
                let visible = unit_patch
                    .clone()
                    .into_visible_ddl_patch()
                    .map_err(|_| ProtocolError::SchemaViolation)?;
                validate_visible_ddl_patch_detailed(
                    &base,
                    &visible,
                    &self.config.definitions,
                    seed,
                    limits,
                )
                .map_err(|failure| (failure.diagnostic.kind(), failure.hole_id))
                .and_then(|validated| {
                    if !current || unit.len() != 1 {
                        return Ok(validated);
                    }
                    if let Some(hole) = holes.iter().find(|hole| {
                        unit.contains(&hole.id)
                            && !crate::hole_completion::standalone_repair_preserves_namespace(
                                &base,
                                &validated.compilation,
                                hole,
                            )
                    }) {
                        Err(("owner_association_changed", Some(hole.id.clone())))
                    } else {
                        Ok(validated)
                    }
                })
            };
            match checked {
                Ok(validated) => {
                    accepted_units += 1;
                    accepted.extend(unit_patch.edits);
                    candidate = Some(validated);
                }
                Err((reason, failed_id)) => {
                    for result in &mut results {
                        if unit.iter().any(|id| result["hole_id"] == *id) {
                            result["status"] = json!("rejected");
                            result["reason"] = json!(if failed_id
                                .as_ref()
                                .is_some_and(|id| result["hole_id"] != *id)
                            {
                                "dependency_rejected"
                            } else {
                                reason
                            });
                        }
                    }
                }
            }
        }
        accepted.sort_by_key(|edit| edit.allowed_span.start_byte);
        patch.edits = accepted;
        // Recompile the union once. Never search for alternate passing subsets.
        if accepted_units > 1 {
            let visible = patch
                .clone()
                .into_visible_ddl_patch()
                .map_err(|_| ProtocolError::SchemaViolation)?;
            let size = patch
                .edits
                .iter()
                .fold(base.document.source().len(), |size, edit| {
                    size.saturating_sub(
                        edit.allowed_span
                            .end_byte
                            .saturating_sub(edit.allowed_span.start_byte),
                    )
                    .saturating_add(edit.replacement.len())
                });
            let checked = if size > source_limit {
                Err("source_limit")
            } else {
                validate_visible_ddl_patch_detailed(
                    &base,
                    &visible,
                    &self.config.definitions,
                    seed,
                    limits,
                )
                .map_err(|failure| failure.diagnostic.kind())
            };
            match checked {
                Ok(validated) => candidate = Some(validated),
                Err(reason) => {
                    candidate = None;
                    for result in &mut results {
                        if result["status"] == "validated" {
                            result["status"] = json!("rejected");
                            result["reason"] = json!(reason);
                        }
                    }
                }
            }
        }
        let report = json!({"results":results,"base_source_digest":lock.visible_source_digest,"base_compiler_lock_digest":lock.full_digest});
        self.hole_completion_check = Some(report.clone());
        self.event(events, "hole_completion_checked", report)?;
        if current
            && previous.is_none()
            && results.iter().any(|result| result["status"] == "rejected")
            && self.ask_holes_again(&prompt, &results, &proposals, hole_ids, spent_ms, events)?
        {
            return Ok(());
        }
        // A3: the completion may keep the numbers of a range whose words alone
        // changed (the new words say the same place). Such an edit changes no
        // text, so it is not asked for approval: the record takes the range's
        // new words. It is kept only when nothing failed or other edits go on
        // to approval, so a retry still finds the holes it asked for.
        let source = base.document.source();
        let unchanged = patch
            .edits
            .iter()
            .filter(|edit| {
                source.get(edit.allowed_span.start_byte..edit.allowed_span.end_byte)
                    == Some(edit.replacement.as_str())
            })
            .map(|edit| inku_ddl::SourceSpan::from(edit.allowed_span))
            .collect::<Vec<_>>();
        patch.edits.retain(|edit| {
            source.get(edit.allowed_span.start_byte..edit.allowed_span.end_byte)
                != Some(edit.replacement.as_str())
        });
        let all_passed = results.iter().all(|result| result["status"] == "validated");
        let settles = patch.edits.is_empty() && !unchanged.is_empty() && all_passed;
        let proposes = candidate.is_some() && !patch.edits.is_empty();
        if !unchanged.is_empty()
            && (settles || proposes)
            && let Some(record) = &self.completion_ranges
        {
            self.completion_ranges = Some(record_keeping_numbers(&base, record, &unchanged));
        }
        if settles {
            self.action = None;
            let has_score = self
                .delivery
                .as_ref()
                .is_some_and(|delivery| delivery.score.is_some());
            self.phase = if has_score {
                PipelinePhase::ScoreReady
            } else {
                PipelinePhase::NeedsUserEdit {
                    reason: "compiler_diagnostics".into(),
                }
            };
            return self.event(
                events,
                if has_score {
                    "score_finalized"
                } else {
                    "needs_user_edit"
                },
                json!({"has_score": has_score}),
            );
        }
        let Some(candidate) = candidate.filter(|_| !patch.edits.is_empty()) else {
            let detail = results
                .iter()
                .find_map(|result| result["reason"].as_str())
                .unwrap_or("holes_unresolved");
            return self.failure_with_detail(
                ProviderFailure::SemanticViolation,
                spent_ms,
                Some(detail),
                events,
            );
        };
        let candidate = VisibleDocument::from_document(&candidate.document);
        let proposal_digest = value_digest(
            "inku.pipeline-visible-patch-proposal.v1",
            &json!({"patch":patch,"candidate":candidate,"revision":DecimalU64::new(self.authority.revision())}),
        )?;
        self.event(events, "visible_patch_proposed", json!({"base":self.document,"candidate":candidate,"patch":patch,"proposal_digest":proposal_digest}))?;
        self.action = None;
        self.phase = PipelinePhase::AwaitingPatchApproval {
            patch,
            candidate,
            proposal_digest,
            base_revision: DecimalU64::new(self.authority.revision()),
        };
        Ok(())
    }

    fn llm_response(
        &mut self,
        stage: LlmStage,
        response: String,
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let PipelinePhase::AwaitingLlm {
            stage: expected,
            description,
            hole_ids,
            elapsed_ms,
        } = self.phase.clone()
        else {
            return Err(ProtocolError::StaleResult);
        };
        if stage != expected {
            return Err(ProtocolError::StaleResult);
        }
        let total = elapsed_ms
            .get()
            .checked_add(spent_ms)
            .ok_or(ProtocolError::InvalidPolicy)?;
        if spent_ms
            > self
                .action
                .as_ref()
                .ok_or(ProtocolError::InvalidState)?
                .timeout_ms
                .get()
            || total > self.retry_policy(stage).total_timeout_ms.get()
        {
            return self.failure(ProviderFailure::TransportTimeout, spent_ms, events);
        }
        match stage {
            LlmStage::GenerateSketch => {
                let Ok(parsed) = parse_sketch_response(&response, self.config.prompt_limits) else {
                    return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
                };
                let text = parsed.supplement().map(str::to_owned);
                let state = if text.is_some() {
                    SketchState::Supplemented
                } else {
                    SketchState::NotNeeded
                };
                self.action = None;
                self.finish_sketch(
                    state,
                    text,
                    description.ok_or(ProtocolError::InternalInvariant)?,
                    serde_json::Value::Null,
                    events,
                )
            }
            LlmStage::SelectDescriptionCatalog => {
                let selected =
                    match parse_catalog_selection_response(&response, self.config.prompt_limits) {
                        Ok(value) => value,
                        Err(_) => {
                            return self.failure(
                                ProviderFailure::SchemaViolation,
                                spent_ms,
                                events,
                            );
                        }
                    };
                if self
                    .select_catalog(&selected.catalog_id, CatalogMode::AutoSelected)
                    .is_err()
                {
                    return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
                }
                self.stage1(description.ok_or(ProtocolError::InternalInvariant)?, events)
            }
            LlmStage::GenerateNormalizedDdl => {
                let plugins = crate::prompts::work_plan_plugins(&self.config.definitions);
                let (generated, plan) = match parse_stage1_response_and_plan_with_plugins(
                    &response,
                    self.config.prompt_limits,
                    self.config.language,
                    &plugins,
                ) {
                    Ok(value) => value,
                    Err(_) => {
                        return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
                    }
                };
                let candidate = self.new_document(generated.normalized_ddl)?;
                let compiled = compile_typed_ddl(
                    candidate.document()?,
                    &self.config.definitions,
                    self.config
                        .compiler
                        .composition_seed()
                        .map_err(|_| ProtocolError::InvalidPolicy)?,
                    self.config
                        .compiler
                        .macro_limits()
                        .map_err(|_| ProtocolError::InvalidPolicy)?,
                );
                if !compiled
                    .compiler_lock
                    .as_ref()
                    .is_some_and(|lock| lock.state == CompilerLockState::CanonicalReady)
                {
                    if self.stage1_fallback.is_some() {
                        return self.commit_stage1_fallback(
                            json!({
                                "failure": ProviderFailure::SemanticViolation,
                                "detail": stage1_compiler_failure_detail(&compiled),
                            }),
                            events,
                        );
                    }
                    let retry_exhausted = self
                        .config
                        .stage1_retry
                        .next_budgeted_attempt(
                            self.action
                                .as_ref()
                                .ok_or(ProtocolError::InvalidState)?
                                .identity
                                .attempt,
                            total,
                        )
                        .is_none();
                    if self.correct_stage1(
                        &compiled,
                        description.ok_or(ProtocolError::InternalInvariant)?,
                        total,
                        events,
                    )? {
                        return Ok(());
                    }
                    if retry_exhausted && self.residual_execution_preflight(&candidate) {
                        let next = proposal(
                            self.authority
                                .propose_stage1_result_commit(self.authority.revision()),
                        )?
                        .ok_or(ProtocolError::InternalInvariant)?;
                        return self.commit_document(
                            candidate,
                            next,
                            "stage1_residual_execution",
                            events,
                        );
                    }
                    return self.failure_with_detail(
                        ProviderFailure::SemanticViolation,
                        spent_ms,
                        Some(stage1_compiler_failure_detail(&compiled)),
                        events,
                    );
                }
                if self.return_ground_coloured_layers(
                    &candidate,
                    plan.as_ref(),
                    description
                        .clone()
                        .ok_or(ProtocolError::InternalInvariant)?,
                    total,
                    events,
                )? {
                    return Ok(());
                }
                self.settle_stage1(candidate, plan, "stage1_generated", description, events)
            }
            LlmStage::ReadComposition => {
                self.composition_response(&response, spent_ms, description, events)
            }
            LlmStage::ChooseLaws => self.laws_response(&response, spent_ms, description, events),
            LlmStage::ChooseColors => {
                self.colors_response(&response, spent_ms, description, events)
            }
            LlmStage::CompleteVisibleDdlHoles => {
                self.hole_response(&response, &hole_ids, spent_ms, events)
            }
        }
    }
}

/// Advance a copied execution snapshot. The host serializes calls and persists
/// source/authority compare-and-set proposals; output events never drive this function.
pub fn advance(
    snapshot: Option<PipelineSnapshot>,
    input: Envelope<PipelineInput>,
) -> Result<StepOutput, ProtocolError> {
    advance_impl(snapshot, input, None)
}

/// A Server's allowance travels with this call, never with the sealed snapshot.
pub fn advance_with_svg_limit(
    snapshot: Option<PipelineSnapshot>,
    input: Envelope<PipelineInput>,
    max_svg_bytes: usize,
) -> Result<StepOutput, ProtocolError> {
    advance_impl(snapshot, input, Some(max_svg_bytes))
}

fn advance_impl(
    snapshot: Option<PipelineSnapshot>,
    input: Envelope<PipelineInput>,
    max_svg_bytes: Option<usize>,
) -> Result<StepOutput, ProtocolError> {
    input.validate("input")?;
    let mut events = Vec::new();
    let mut rendered = None;
    let mut state = if let Some(mut state) = snapshot {
        state.validate()?;
        if input.execution_id != state.execution_id
            || input.sequence != state.sequence.checked_next()?
        {
            return Err(ProtocolError::StaleResult);
        }
        state.sequence = input.sequence;
        if matches!(state.phase, PipelinePhase::Cancelled) {
            return Err(ProtocolError::StaleResult);
        }
        match input.payload {
            PipelineInput::Start { .. } => return Err(ProtocolError::InvalidState),
            PipelineInput::Cancel => {
                state.action = None;
                state.delivery = None;
                state.stage1_fallback = None;
                state.phase = PipelinePhase::Cancelled;
                state.event(&mut events, "cancelled", json!({}))?;
            }
            PipelineInput::CommitUserDdl {
                expected_revision,
                source,
            } => {
                state.editable()?;
                state.revision(expected_revision)?;
                let changed = state
                    .document
                    .as_ref()
                    .is_none_or(|document| document.source != source);
                if let Some(next) = proposal(
                    state
                        .authority
                        .propose_committed_user_ddl_mutation(expected_revision.get(), changed),
                )? {
                    let document = if let Some(current) = &state.document {
                        if source.len() > state.config.prompt_limits.max_source_bytes {
                            return Err(ProtocolError::SchemaViolation);
                        }
                        VisibleDocument {
                            source,
                            ..current.clone()
                        }
                    } else {
                        state.new_document(source)?
                    };
                    document.document()?;
                    state.commit_document(document, next, "user_ddl_mutation", &mut events)?;
                }
            }
            PipelineInput::GenerateFromDescription {
                expected_revision,
                description,
                auto_catalog,
                sketch,
            } => {
                state.editable()?;
                state.revision(expected_revision)?;
                state.description(description, auto_catalog, sketch, &mut events)?;
            }
            PipelineInput::CompleteHoles {
                expected_revision,
                hole_ids,
            } => {
                state.editable()?;
                state.revision(expected_revision)?;
                state.complete_holes(hole_ids, &mut events)?;
            }
            PipelineInput::ApprovePatch {
                expected_revision,
                proposal_digest,
            } => {
                state.revision(expected_revision)?;
                let PipelinePhase::AwaitingPatchApproval {
                    patch,
                    candidate,
                    proposal_digest: expected,
                    base_revision,
                } = state.phase.clone()
                else {
                    return Err(ProtocolError::InvalidState);
                };
                if expected != proposal_digest || base_revision != expected_revision {
                    return Err(ProtocolError::StaleResult);
                }
                let base = state.compilation()?;
                let visible_patch = patch
                    .into_visible_ddl_patch()
                    .map_err(|_| ProtocolError::SchemaViolation)?;
                let validated = validate_visible_ddl_patch(
                    &base,
                    &visible_patch,
                    &state.config.definitions,
                    state
                        .config
                        .compiler
                        .composition_seed()
                        .map_err(|_| ProtocolError::InvalidPolicy)?,
                    state
                        .config
                        .compiler
                        .macro_limits()
                        .map_err(|_| ProtocolError::InvalidPolicy)?,
                )
                .map_err(|_| ProtocolError::SemanticViolation)?;
                if VisibleDocument::from_document(&validated.document) != candidate {
                    return Err(ProtocolError::StaleResult);
                }
                let changed = base.document.source() != candidate.source;
                let next = proposal(
                    state
                        .authority
                        .propose_committed_user_ddl_mutation(expected_revision.get(), changed),
                )?
                .ok_or(ProtocolError::SemanticViolation)?;
                // The ranges this completion wrote join the work's record (A3).
                let empty = CompletionRangeRecord::default();
                let record = record_after_patch(
                    &base,
                    &validated,
                    state.completion_ranges.as_ref().unwrap_or(&empty),
                );
                state.commit_document(candidate, next, "user_approved_patch", &mut events)?;
                if let PipelinePhase::AwaitingVisibleDdlCommit {
                    completion_ranges, ..
                } = &mut state.phase
                {
                    *completion_ranges = (!record.is_empty()).then_some(record);
                }
            }
            PipelineInput::DeclinePatch { proposal_digest } => {
                let PipelinePhase::AwaitingPatchApproval {
                    proposal_digest: expected,
                    ..
                } = &state.phase
                else {
                    return Err(ProtocolError::InvalidState);
                };
                if *expected != proposal_digest {
                    return Err(ProtocolError::StaleResult);
                }
                state.phase = PipelinePhase::NeedsUserEdit {
                    reason: "patch_declined".into(),
                };
                state.action = None;
                state.event(
                    &mut events,
                    "needs_user_edit",
                    json!({"reason": "patch_declined"}),
                )?;
            }
            PipelineInput::EffectResult { result } => state.accept_result(result, &mut events)?,
            PipelineInput::Render { options, clip } => {
                let final_render = matches!(
                    state.phase,
                    PipelinePhase::ScoreReady | PipelinePhase::Completed
                );
                let current_safe_render = matches!(
                    state.phase,
                    PipelinePhase::AwaitingLlm {
                        stage: LlmStage::CompleteVisibleDdlHoles,
                        ..
                    } | PipelinePhase::AwaitingPatchApproval { .. }
                        | PipelinePhase::NeedsUserEdit { .. }
                        | PipelinePhase::Failed { .. }
                );
                if !final_render && !current_safe_render {
                    return Err(ProtocolError::InvalidState);
                }
                let delivery = state.delivery.as_ref().ok_or(ProtocolError::InvalidState)?;
                let output = match max_svg_bytes {
                    Some(maximum) => crate::core_boundary::render_delivery_with_svg_limit(
                        delivery,
                        options.into(),
                        &state.config.compiler,
                        clip,
                        maximum,
                    ),
                    None => crate::core_boundary::render_delivery(
                        delivery,
                        options.into(),
                        &state.config.compiler,
                        clip,
                    ),
                };
                rendered = Some(output.map_err(|_| ProtocolError::SemanticViolation)?);
                if final_render {
                    state.phase = PipelinePhase::Completed;
                    state.event(
                        &mut events,
                        "completed",
                        json!({"render_engine": inku_render::RENDER_ENGINE_VERSION}),
                    )?;
                }
            }
        }
        state
    } else {
        if input.sequence.get() != 0 {
            return Err(ProtocolError::StaleResult);
        }
        let PipelineInput::Start {
            variation_id,
            authoring_nonce,
            config,
            authority,
            authoring,
        } = input.payload
        else {
            return Err(ProtocolError::InvalidState);
        };
        if variation_id.is_empty() || authoring_nonce.is_empty() {
            return Err(ProtocolError::SchemaViolation);
        }
        config.validate()?;
        let execution_id = value_digest(
            "inku.pipeline-execution.v1",
            &json!({
                "variation_id": variation_id, "nonce": authoring_nonce,
                "config": config, "authority": authority,
                "request_kind": match &authoring { AuthoringInput::DirectDdl { .. } => "direct_ddl", AuthoringInput::SavedLaws { .. } => "saved_laws", AuthoringInput::Description { .. } => "description" },
            }),
        )?;
        let mut state = PipelineSnapshot {
            protocol: PROTOCOL_NAME.into(),
            version: PROTOCOL_VERSION.into(),
            execution_id,
            variation_id,
            sequence: input.sequence,
            event_sequence: DecimalU64::new(0),
            action_ordinal: DecimalU64::new(0),
            authority,
            config: *config,
            document: None,
            phase: PipelinePhase::AuthoringStarted,
            action: None,
            delivery: None,
            hole_completion_check: None,
            sketch: None,
            stage1_fallback: None,
            stage1_fallback_plan: None,
            composition: None,
            laws: None,
            colors: None,
            completion_ranges: None,
            laws_layers: None,
            laws_basis: None,
            laws_move: None,
            snapshot_digest: String::new(),
        };
        state.event(
            &mut events,
            "state_entered",
            json!({"state": "authoring_started"}),
        )?;
        match authoring {
            AuthoringInput::DirectDdl {
                source,
                completion_ranges,
                laws_layers,
                laws_basis,
            } => {
                state.completion_ranges = completion_ranges.filter(|record| !record.is_empty());
                state.laws_layers = laws_layers.filter(|record| !record.is_empty());
                state.laws_basis = laws_basis;
                if matches!(
                    state.config.compiler.host.catalog_mode(),
                    CatalogMode::AutoSelected | CatalogMode::AutoFallbackDefault
                ) {
                    return Err(ProtocolError::InvalidPolicy);
                }
                let document = state.new_document(source)?;
                let next = proposal(
                    state
                        .authority
                        .propose_committed_user_ddl_mutation(state.authority.revision(), true),
                )?
                .ok_or(ProtocolError::InternalInvariant)?;
                state.commit_document(document, next, "direct_ddl", &mut events)?;
            }
            AuthoringInput::SavedLaws {
                source,
                description,
                completion_ranges,
                laws_layers,
                laws_basis,
                direction,
            } => state.saved_laws(
                SavedWork {
                    source,
                    description,
                    completion_ranges,
                    laws_layers,
                    laws_basis,
                },
                direction,
                &mut events,
            )?,
            AuthoringInput::Description {
                description,
                auto_catalog,
                sketch,
            } => state.description(description, auto_catalog, sketch, &mut events)?,
        }
        state
    };
    state.seal()?;
    Ok(StepOutput {
        snapshot: state,
        events,
        rendered,
    })
}

impl PipelineSnapshot {
    fn accept_result(
        &mut self,
        result: EffectResult,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let action = self.action.as_ref().ok_or(ProtocolError::StaleResult)?;
        if *result.identity() != action.identity {
            return Err(ProtocolError::StaleResult);
        }
        match result {
            EffectResult::SketchGenerated {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(LlmStage::GenerateSketch, response, elapsed_ms.get(), events),
            EffectResult::DescriptionCatalogSelected {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(
                LlmStage::SelectDescriptionCatalog,
                response,
                elapsed_ms.get(),
                events,
            ),
            EffectResult::NormalizedDdlGenerated {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(
                LlmStage::GenerateNormalizedDdl,
                response,
                elapsed_ms.get(),
                events,
            ),
            EffectResult::VisibleDdlHolePatchGenerated {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(
                LlmStage::CompleteVisibleDdlHoles,
                response,
                elapsed_ms.get(),
                events,
            ),
            EffectResult::CompositionRead {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(
                LlmStage::ReadComposition,
                response,
                elapsed_ms.get(),
                events,
            ),
            EffectResult::LawsChosen {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(LlmStage::ChooseLaws, response, elapsed_ms.get(), events),
            EffectResult::ColorsChosen {
                response,
                elapsed_ms,
                ..
            } => self.llm_response(LlmStage::ChooseColors, response, elapsed_ms.get(), events),
            EffectResult::ProviderFailed {
                failure,
                elapsed_ms,
                ..
            } => self.failure(failure, elapsed_ms.get(), events),
            EffectResult::HostCommitFailed {
                actual_revision, ..
            } => {
                if !matches!(self.phase, PipelinePhase::AwaitingVisibleDdlCommit { .. }) {
                    return Err(ProtocolError::StaleResult);
                }
                self.action = None;
                self.phase = PipelinePhase::Failed {
                    reason: "host_commit_failed".into(),
                };
                self.event(
                    events,
                    "failed",
                    json!({"reason": "host_commit_failed", "actual_revision": actual_revision}),
                )
            }
            EffectResult::VisibleNormalizedDdlCommitted {
                ddl_digest,
                revision,
                authority_digest,
                ..
            } => {
                let PipelinePhase::AwaitingVisibleDdlCommit {
                    document,
                    authority,
                    reason,
                    completion_ranges,
                } = self.phase.clone()
                else {
                    return Err(ProtocolError::StaleResult);
                };
                if ddl_digest != document.source_digest()
                    || revision.get() != authority.next_state.revision()
                    || authority_digest
                        != value_digest("inku.variation-authority.v1", &authority.next_state)?
                    || self.authority.revision() != authority.expected_revision
                {
                    return Err(ProtocolError::StaleResult);
                }
                self.authority = authority.next_state;
                self.document = Some(document.clone());
                self.action = None;
                // An approved patch leaves the record its completion wrote (A3).
                if reason == "user_approved_patch" {
                    self.completion_ranges = completion_ranges;
                }
                // Only acknowledged visible bytes enter the actual Score compiler.
                let delivery = match crate::core_boundary::compile_committed(
                    document.document()?,
                    &self.config.definitions,
                    &self.config.compiler,
                ) {
                    Ok(delivery) => delivery,
                    Err(_) => {
                        // The source commit already happened. Retain its new revision
                        // even if compilation cannot produce a semantic artifact.
                        self.delivery = None;
                        self.phase = PipelinePhase::Failed {
                            reason: "compiler_boundary_failed".into(),
                        };
                        return self.event(
                            events,
                            "failed",
                            json!({"reason": "compiler_boundary_failed", "revision": revision}),
                        );
                    }
                };
                self.event(
                    events,
                    "typed_ddl_parsed",
                    json!({"source_digest": document.source_digest(), "revision": revision}),
                )?;
                // The record keeps only the ranges this document still has (A3).
                self.settle_completion_ranges()?;
                let compiler_holes = delivery.compiler_lock.as_ref().filter(|lock| {
                    lock.get("hole_identities")
                        .and_then(serde_json::Value::as_array)
                        .is_some_and(|identities| !identities.is_empty())
                });
                let completing =
                    reason != "user_approved_patch" && reason != "stage1_residual_execution";
                // A range whose words alone the author changed is a hole the
                // completion writes the numbers of again (A3).
                let words_changed = if completing && self.completion_ranges.is_some() {
                    self.compilation()?
                        .holes
                        .into_iter()
                        .filter(|hole| hole.kind == RANGE_WORDS_CHANGED_HOLE_KIND)
                        .map(|hole| hole.id)
                        .collect()
                } else {
                    Vec::new()
                };
                if reason == "user_approved_patch" {
                    if let Some(report) = self.hole_completion_check.clone() {
                        self.event(events, "hole_completion_checked", report)?;
                    }
                } else if completing && (compiler_holes.is_some() || !words_changed.is_empty()) {
                    let mut hole_ids = compiler_holes
                        .and_then(|lock| lock.get("hole_identities"))
                        .cloned()
                        .and_then(|ids| serde_json::from_value::<Vec<String>>(ids).ok())
                        .unwrap_or_default();
                    hole_ids.extend(words_changed);
                    // Known holes enter the shared completion policy without a
                    // separate user command. Declines and failures do not re-enter
                    // this commit-only branch; any retry is bounded by its action.
                    self.delivery = Some(delivery);
                    if let Err(error) = self.complete_holes(hole_ids, events) {
                        // This revision is already committed. Preserve it even if
                        // a completion prompt cannot be constructed within policy.
                        self.action = None;
                        self.phase = PipelinePhase::NeedsUserEdit {
                            reason: "hole_request_unavailable".into(),
                        };
                        return self.event(
                            events,
                            "needs_user_edit",
                            json!({
                                "reason": "hole_request_unavailable", "error": error,
                                "revision": revision,
                            }),
                        );
                    }
                    return Ok(());
                }
                let has_score = delivery.score.is_some();
                self.phase = if has_score {
                    PipelinePhase::ScoreReady
                } else {
                    PipelinePhase::NeedsUserEdit {
                        reason: "compiler_diagnostics".into(),
                    }
                };
                self.delivery = Some(delivery);
                self.event(
                    events,
                    if has_score {
                        "score_finalized"
                    } else {
                        "needs_user_edit"
                    },
                    json!({"has_score": has_score}),
                )
            }
        }
    }
}
