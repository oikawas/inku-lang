//! Pure effect orchestration around the shared compiler and durable visible DDL.

use std::collections::{BTreeMap, BTreeSet};

use inku_ddl::{
    CompilerLockState, MacroDefinition, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, TypedDdlCompilation, compile_typed_ddl,
    validate_visible_ddl_patch, validate_visible_ddl_patch_detailed, visible_ddl_patch_available,
};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::authority::{
    AuthorityTransitionOutcome, AuthorityTransitionProposal, AuthorityTransitionResult,
    VariationAuthorityState,
};
use crate::core_boundary::CatalogMode;
use crate::core_boundary::{CompiledDelivery, CompilerOptions, ResolvedHostOptions};
use crate::prompts::{
    DescriptionCatalogEntry, HOLE_COMPLETION_PROMPT_ID, HoleCompletionResult,
    HolePatchEditResponse, HolePatchResponse, LEGACY_HOLE_COMPLETION_PROMPT_ID, LlmPrompt,
    LlmStage, MacroPromptEntry, PromptLimits, Stage1Context, build_catalog_selection_prompt,
    build_hole_completion_prompt, build_sketch_prompt, build_stage1_prompt_with_sketch,
    parse_catalog_selection_response, parse_hole_completion_response, parse_hole_patch_response,
    parse_sketch_response, parse_stage1_response_with_plugins, with_stage1_compiler_feedback,
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
}

/// Exact visible source and its sidecar locks; no description or hidden reasoning.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VisibleDocument {
    pub source: String,
    pub language: ResolvedInstructionLanguage,
    pub macro_locks: Vec<LockedDefinition>,
}

impl VisibleDocument {
    pub fn document(&self) -> Result<NormalizedDdlDocument, ProtocolError> {
        let locks = self
            .macro_locks
            .iter()
            .map(|lock| {
                MacroLock::new(&lock.qualified_name, &lock.version, &lock.digest)
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
                })
                .collect(),
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
    pub snapshot_digest: String,
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
        self.config.validate()?;
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
        ) && !self
            .delivery
            .as_ref()
            .is_some_and(|delivery| delivery.score.is_some())
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
            });
        }
        let wire = VisibleDocument {
            source,
            language: self.config.language,
            macro_locks: locks,
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
            let identity = definition
                .identity()
                .map_err(|_| ProtocolError::SchemaViolation)?;
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
        build_stage1_prompt_with_sketch(
            description,
            self.sketch.as_ref().and_then(SketchRecord::stage1_text),
            self.config.language,
            &context,
            &macros,
            self.config.prompt_limits,
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
        let total = elapsed_ms
            .checked_add(policy.retry_delay_ms.get())
            .ok_or(ProtocolError::InvalidPolicy)?;
        self.phase = PipelinePhase::AwaitingLlm {
            stage: LlmStage::GenerateNormalizedDdl,
            description: Some(description),
            hole_ids: Vec::new(),
            elapsed_ms: DecimalU64::new(total),
        };
        // A changed request gets a new action identity but keeps the stage budget.
        self.issue_attempt(
            LlmStage::GenerateNormalizedDdl.action_name(),
            json!({"prompt": prompt, "policy": policy}),
            policy.remaining_attempt_timeout(total),
            next,
            events,
        )?;
        self.action.as_mut().unwrap().delay_ms = policy.retry_delay_ms;
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
        if let SketchRequest::Supplied { text } = &sketch {
            if text.len() > self.config.prompt_limits.max_source_bytes {
                return Err(ProtocolError::SchemaViolation);
            }
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

    fn compilation(&self) -> Result<inku_ddl::TypedDdlCompilation, ProtocolError> {
        let document = self
            .document
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .document()?;
        Ok(compile_typed_ddl(
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
        ))
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
                    "results":selected.iter().map(|hole| json!({"hole_id":hole.id,"status":"unresolved","reason":"context_limit"})).collect::<Vec<_>>(),
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
        }
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
            .map(|hole| json!({"hole_id":hole.id,"status":"rejected","reason":"schema_violation"}))
            .collect::<Vec<_>>();
        let mut patch = HolePatchResponse {
            schema_id: inku_ddl::VISIBLE_DDL_PATCH_SCHEMA_ID.into(),
            base_source_digest: lock.visible_source_digest.clone(),
            base_compiler_lock_digest: lock.full_digest.clone(),
            edits: vec![],
        };
        let parsed = if prompt.prompt_id == HOLE_COMPLETION_PROMPT_ID {
            parse_hole_completion_response(response, holes.len(), self.config.prompt_limits).map(|response| {
                for result in response.results {
                    let index = result.id()[1..].parse::<usize>().expect("verified local ID") - 1;
                    let hole = holes[index];
                    match result {
                        HoleCompletionResult::Proposed { replacement, .. } => {
                            patch.edits.push(HolePatchEditResponse { hole_id:hole.id.clone(), allowed_span:hole.allowed_span.into(), expected_range_digest:hole.expected_range_digest.clone(), replacement });
                            results[index] = json!({"hole_id":hole.id,"status":"validated","reason":null});
                        }
                        HoleCompletionResult::Unresolved { reason, .. } => {
                            results[index] = json!({"hole_id":hole.id,"status":"unresolved","reason":reason});
                        }
                    }
                }
            })
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
        let units = if prompt.prompt_id == HOLE_COMPLETION_PROMPT_ID {
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
                    if prompt.prompt_id != HOLE_COMPLETION_PROMPT_ID || unit.len() != 1 {
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
                let mut plugins = self
                    .config
                    .definitions
                    .iter()
                    .filter_map(MacroDefinition::qualified_name)
                    .collect::<Vec<_>>();
                plugins.sort();
                plugins.dedup();
                let generated = match parse_stage1_response_with_plugins(
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
                let next = proposal(
                    self.authority
                        .propose_stage1_result_commit(self.authority.revision()),
                )?
                .ok_or(ProtocolError::InternalInvariant)?;
                self.commit_document(candidate, next, "stage1_generated", events)
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
                state.commit_document(candidate, next, "user_approved_patch", &mut events)?;
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
                rendered = Some(
                    crate::core_boundary::render_delivery(
                        delivery,
                        options.into(),
                        &state.config.compiler,
                        clip,
                    )
                    .map_err(|_| ProtocolError::SemanticViolation)?,
                );
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
                "request_kind": match &authoring { AuthoringInput::DirectDdl { .. } => "direct_ddl", AuthoringInput::Description { .. } => "description" },
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
            snapshot_digest: String::new(),
        };
        state.event(
            &mut events,
            "state_entered",
            json!({"state": "authoring_started"}),
        )?;
        match authoring {
            AuthoringInput::DirectDdl { source } => {
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
                if reason == "user_approved_patch" {
                    if let Some(report) = self.hole_completion_check.clone() {
                        self.event(events, "hole_completion_checked", report)?;
                    }
                } else if reason != "stage1_residual_execution" {
                    if let Some(lock) = delivery.compiler_lock.as_ref().filter(|lock| {
                        lock.get("hole_identities")
                            .and_then(serde_json::Value::as_array)
                            .is_some_and(|identities| !identities.is_empty())
                    }) {
                        let hole_ids = lock
                            .get("hole_identities")
                            .cloned()
                            .and_then(|ids| serde_json::from_value::<Vec<String>>(ids).ok())
                            .unwrap_or_default();
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
