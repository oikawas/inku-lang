//! One representative authoring flow. This test never calls the native renderer.

use inku_score::{
    CANVAS_FORMAT_REGISTRY_ID, Color, HardResourcePolicy, OperationalResourceBudget,
    ResourceBudget, ResourceDemand, ScoreErrorPolicy, canvas_format_registry_digest,
};
use serde_json::json;

use crate::authority::{AuthoringAuthority, VariationAuthorityState};
use crate::byte_envelope::{EnvelopeLimits, step_owned};
use crate::core_boundary::{
    CatalogMode, CompilerOptions, MacroExpansionLimitsDto, ResolvedHostOptions,
    ResolvedPaletteColorDto, ResolvedPaletteDto,
};
use crate::machine::{
    AuthoringInput, PipelineConfig, PipelineInput, PipelinePhase, PipelineSnapshot,
    SketchRequest, SketchState, StepOutput,
};
use crate::prompts::PromptLimits;
use crate::protocol::{
    DecimalU64, EffectResult, Envelope, PROTOCOL_NAME, PROTOCOL_VERSION, ProviderFailure,
    RetryPolicy,
};

fn config() -> PipelineConfig {
    let white = ResolvedPaletteColorDto {
        abstract_color: Color::White,
        concrete_rgb: [255; 3],
        oklch_lightness: 1.0,
    };
    let black = ResolvedPaletteColorDto {
        abstract_color: Color::Black,
        concrete_rgb: [0; 3],
        oklch_lightness: 0.0,
    };
    let host = ResolvedHostOptions::new(
        "square",
        CANVAS_FORMAT_REGISTRY_ID,
        canvas_format_registry_digest().unwrap(),
        "default",
        CatalogMode::Default,
        Color::White,
        ResolvedPaletteDto {
            background: white,
            black,
            white,
            observations: None,
        },
    )
    .unwrap();
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 400,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 512,
            anchor_instances: 400,
            transform_instances: 400,
            placement_instances: 400,
            fill_instances: 400,
        },
    };
    let retry = RetryPolicy {
        max_attempts: 2,
        attempt_timeout_ms: DecimalU64::new(1000),
        total_timeout_ms: DecimalU64::new(3000),
        retry_delay_ms: DecimalU64::new(10),
    };
    PipelineConfig {
        envelope_limits: EnvelopeLimits {
            max_input_bytes: 1_000_000,
            max_snapshot_bytes: 1_000_000,
            max_output_bytes: 2_000_000,
        },
        language: inku_ddl::ResolvedInstructionLanguage::En,
        compiler: CompilerOptions {
            host,
            composition_seed: Some(DecimalU64::new(17)),
            macro_expansion_limits: MacroExpansionLimitsDto {
                max_invocations: DecimalU64::new(16),
                max_depth: DecimalU64::new(16),
                max_evaluation_steps: DecimalU64::new(1000),
                max_nodes_per_invocation: DecimalU64::new(100),
                max_total_nodes: DecimalU64::new(500),
            },
            stage15_variation: None,
            error_policy: ScoreErrorPolicy::OmitAndContinue,
            hard_resource_policy: HardResourcePolicy {
                identity: "pipeline-fixture.v1".into(),
                budget,
            },
            operational_resource_budget: OperationalResourceBudget(budget),
        },
        definitions: vec![],
        macro_summaries: vec![],
        catalogs: vec![],
        prompt_limits: PromptLimits {
            max_catalog_entries: 16,
            max_summary_bytes: 1024,
            max_catalog_serialized_bytes: 32768,
            max_source_bytes: 8192,
            max_response_bytes: 16384,
        },
        catalog_retry: retry,
        stage1_retry: retry,
        hole_retry: retry,
        sketch_retry: None,
    }
}

fn envelope(
    snapshot: Option<&PipelineSnapshot>,
    payload: PipelineInput,
) -> Envelope<PipelineInput> {
    let sequence = snapshot.map_or(0, |state| state.sequence.get() + 1);
    Envelope {
        protocol: PROTOCOL_NAME.into(),
        version: PROTOCOL_VERSION.into(),
        kind: "input".into(),
        execution_id: snapshot.map_or_else(|| "new".into(), |state| state.execution_id.clone()),
        message_id: format!("message-{sequence}"),
        sequence: DecimalU64::new(sequence),
        payload,
    }
}

fn run(snapshot: Option<&PipelineSnapshot>, input: &Envelope<PipelineInput>) -> StepOutput {
    let snapshot_bytes = snapshot
        .map(|state| serde_json::to_vec(state).unwrap())
        .unwrap_or_default();
    let mut wire = serde_json::to_value(input).unwrap();
    wire["payload"]["version"] = json!(1);
    let bytes = step_owned(&snapshot_bytes, &serde_json::to_vec(&wire).unwrap());
    let output: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(
        output["kind"], "output",
        "{output}; input={}",
        wire["payload"]["tag"]
    );
    serde_json::from_value(output["payload"]["result"].clone()).unwrap()
}

fn run_error(
    snapshot: Option<&PipelineSnapshot>,
    input: &Envelope<PipelineInput>,
) -> serde_json::Value {
    let snapshot_bytes = snapshot
        .map(|state| serde_json::to_vec(state).unwrap())
        .unwrap_or_default();
    let mut wire = serde_json::to_value(input).unwrap();
    wire["payload"]["version"] = json!(1);
    let bytes = step_owned(&snapshot_bytes, &serde_json::to_vec(&wire).unwrap());
    let output: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(output["kind"], "error", "{output}");
    output
}

fn ack(state: &PipelineSnapshot) -> PipelineInput {
    let action = state.action.as_ref().unwrap();
    PipelineInput::EffectResult {
        result: EffectResult::VisibleNormalizedDdlCommitted {
            identity: action.identity.clone(),
            ddl_digest: action.payload["ddl_digest"].as_str().unwrap().into(),
            revision: serde_json::from_value(
                action.payload["authority"]["next_state"]["revision"].clone(),
            )
            .unwrap(),
            authority_digest: action.payload["authority_digest"].as_str().unwrap().into(),
        },
    }
}

#[test]
fn canonical_macro_crosses_owned_start_and_commit() {
    let definition = inku_ddl::MacroDefinition::from_json(
        &json!({
            "schema": "inku.macro-definition.v1", "namespace": "Example", "heading": "Circle",
            "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
                "op": "emit", "binding": null, "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    "color": {"expr": "semantic_ref", "category": "color", "id": "black"},
                    "position_x": {"expr": "exact_decimal", "value": "0.5"},
                    "position_y": {"expr": "exact_decimal", "value": "0.5"},
                    "count": {"expr": "integer", "value": 1}
                }
            }]
        })
        .to_string(),
    )
    .unwrap();
    let mut selected = config();
    selected.definitions = vec![definition];
    selected.macro_summaries = vec!["A black circle at the center".into()];
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "canonical-macro".into(),
            authoring_nonce: "macro-1".into(),
            config: Box::new(selected),
            authority: VariationAuthorityState::new_direct_ddl(),
            authoring: AuthoringInput::DirectDdl {
                source: "Example.Circle.".into(),
            },
        },
    );
    let pending = run(None, &start).snapshot;
    let committed = run(Some(&pending), &envelope(Some(&pending), ack(&pending))).snapshot;
    assert!(
        matches!(committed.phase, PipelinePhase::ScoreReady),
        "{:?}; {:?}",
        committed.phase,
        committed.delivery
    );
    assert!(committed.delivery.unwrap().score.is_some());
}

#[test]
fn unresolved_qualified_macro_blocks_without_stage2_completion() {
    let mut pipeline_config = config();
    pipeline_config.language = inku_ddl::ResolvedInstructionLanguage::Ja;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "missing-macro".into(),
            authoring_nonce: "missing-macro-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_direct_ddl(),
            authoring: AuthoringInput::DirectDdl {
                source: "Nature.若葉 を置く".into(),
            },
        },
    );
    let pending = run(None, &start).snapshot;
    let committed = envelope(Some(&pending), ack(&pending));
    let state = run(Some(&pending), &committed).snapshot;

    assert!(
        matches!(
            state.phase,
            PipelinePhase::NeedsUserEdit { ref reason }
                if reason == "compiler_diagnostics"
        ),
        "{:?}",
        state.phase
    );
    assert!(
        state.action.is_none(),
        "unknown Macro must not start Stage 2"
    );
    let lock = state
        .delivery
        .as_ref()
        .and_then(|delivery| delivery.compiler_lock.as_ref())
        .expect("blocked compilation retains its compiler lock");
    assert_eq!(lock["state"], "blocked_diagnostic");
    assert!(
        lock["blocking_diagnostic_identities"]
            .as_array()
            .is_some_and(|identities| !identities.is_empty()),
        "MissingLock must be represented as a blocking diagnostic"
    );
}

#[test]
fn stage1_compiler_feedback_retries_before_the_corrected_ddl_commits() {
    let description = "One quiet black circle";
    // An unknown word is now a repairable clause hole; an ownerless shared
    // action still exercises the explicit action-owner feedback.
    let rejected_ddl = "place many red circle and white square at center.";
    let corrected_ddl = "place one black circle at center.";
    let mut pipeline_config = config();
    pipeline_config.stage1_retry.attempt_timeout_ms = DecimalU64::new(3_000);
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "compiler-feedback".into(),
            authoring_nonce: "compiler-feedback-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: description.into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    let mut state = run(None, &start).snapshot;
    let original_action = state.action.as_ref().unwrap().identity.clone();
    let rejected = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: original_action.clone(),
                response: json!({"normalized_ddl": rejected_ddl}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    let rejected_output = run(Some(&state), &rejected);
    state = rejected_output.snapshot;
    assert!(state.document.is_none() && state.delivery.is_none());
    assert!(
        rejected_output
            .events
            .iter()
            .all(|event| event.tag != "visible_ddl_ready")
    );
    assert!(rejected_output.events.iter().any(|event| {
        event.tag == "retry_scheduled" && event.payload["failure"] == "semantic_violation"
    }));
    let feedback_action = state.action.as_ref().unwrap();
    assert_eq!(feedback_action.tag, "generate_normalized_ddl");
    assert_ne!(
        feedback_action.identity.action_id,
        original_action.action_id
    );
    assert_ne!(
        feedback_action.identity.request_digest,
        original_action.request_digest
    );
    assert_eq!(feedback_action.identity.attempt, 2);
    assert_eq!(feedback_action.timeout_ms, DecimalU64::new(2_970));
    let feedback: serde_json::Value = serde_json::from_str(
        feedback_action.payload["prompt"]["message"]
            .as_str()
            .unwrap(),
    )
    .unwrap();
    assert_eq!(feedback["description"], description);
    assert_eq!(feedback["compiler_feedback"]["rejected_ddl"], rejected_ddl);
    assert!(
        feedback_action.payload["prompt"]["system"]
            .as_str()
            .unwrap()
            .contains("name its target shape in the same instruction")
    );
    let diagnostics = feedback["compiler_feedback"]["diagnostics"]
        .as_array()
        .expect("compiler feedback must contain diagnostics");
    assert!(!diagnostics.is_empty());
    assert!(
        diagnostics
            .iter()
            .all(|diagnostic| { diagnostic["kind"].is_string() && diagnostic["span"].is_object() })
    );

    let stale = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: original_action,
                response: json!({"normalized_ddl": corrected_ddl}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    assert_eq!(
        run_error(Some(&state), &stale)["payload"]["code"],
        "stale_result"
    );

    let corrected = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: feedback_action.identity.clone(),
                response: json!({"normalized_ddl": corrected_ddl}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    state = run(Some(&state), &corrected).snapshot;
    assert!(state.document.is_none());
    assert!(state.delivery.is_none());
    let commit = state.action.as_ref().unwrap();
    assert_eq!(commit.tag, "commit_visible_normalized_ddl");
    assert_eq!(commit.payload["document"]["source"], corrected_ddl);
    let committed = run(Some(&state), &envelope(Some(&state), ack(&state))).snapshot;
    assert!(matches!(committed.phase, PipelinePhase::ScoreReady));
    assert_eq!(committed.document.as_ref().unwrap().source, corrected_ddl);
    assert!(committed.delivery.as_ref().unwrap().score.is_some());
}

#[test]
fn stage1_compiler_feedback_uses_the_shared_attempt_budget() {
    let mut pipeline_config = config();
    pipeline_config.stage1_retry.max_attempts = 2;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "compiler-feedback-exhaustion".into(),
            authoring_nonce: "compiler-feedback-exhaustion-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "One quiet black circle".into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    let mut state = run(None, &start).snapshot;
    let original_action = state.action.as_ref().unwrap().identity.clone();
    let transport_retry = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::ProviderFailed {
                identity: original_action.clone(),
                failure: ProviderFailure::TransportUnavailable,
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    state = run(Some(&state), &transport_retry).snapshot;
    assert_eq!(
        state.action.as_ref().unwrap().identity.action_id,
        original_action.action_id
    );
    assert_eq!(state.action.as_ref().unwrap().identity.attempt, 2);
    let rejected = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: state.action.as_ref().unwrap().identity.clone(),
                response: json!({"normalized_ddl": "Unknown.Macro."}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    let rejected_output = run(Some(&state), &rejected);
    state = rejected_output.snapshot;
    assert!(
        matches!(state.phase, PipelinePhase::Failed { ref reason } if reason == "stage1_failed")
    );
    assert!(state.action.is_none() && state.document.is_none() && state.delivery.is_none());
    assert!(
        rejected_output.events.iter().any(|event| {
            event.tag == "failed"
                && event.payload["reason"] == "semantic_violation"
                && event.payload["detail"] == "macro_resolution_missing_lock"
        })
    );
    assert!(
        rejected_output
            .events
            .iter()
            .all(|event| event.tag != "visible_ddl_ready"),
        "an all-omitted candidate must not enter the CAS path"
    );
}

#[test]
fn exhausted_stage1_proposes_sealed_residual_only_after_visible_ack() {
    let source = "mystery. place one red square at center.";
    let mut pipeline_config = config();
    pipeline_config.stage1_retry.max_attempts = 1;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "sealed-residual".into(),
            authoring_nonce: "sealed-residual-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "One red square with an unresolved clause".into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    let state = run(None, &start).snapshot;
    let generated = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: state.action.as_ref().unwrap().identity.clone(),
                response: json!({"normalized_ddl": source}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    let proposed = run(Some(&state), &generated).snapshot;
    assert!(proposed.document.is_none() && proposed.delivery.is_none());
    let commit = proposed.action.as_ref().expect("residual CAS proposal");
    assert_eq!(commit.tag, "commit_visible_normalized_ddl");
    assert_eq!(commit.payload["document"]["source"], source);
    assert_eq!(commit.payload["reason"], "stage1_residual_execution");

    let committed = run(Some(&proposed), &envelope(Some(&proposed), ack(&proposed))).snapshot;
    assert!(matches!(committed.phase, PipelinePhase::ScoreReady));
    assert_eq!(committed.document.as_ref().unwrap().source, source);
    assert!(
        committed.action.is_none(),
        "residual adoption must not open known-hole completion"
    );
    let delivery = committed.delivery.as_ref().expect("ACKed delivery");
    assert!(delivery.semantic_digest.is_none());
    assert!(delivery.execution_pre_expansion_digest.is_some());
    assert!(delivery.effective_stage15_digest.is_some());
    assert_eq!(delivery.score.as_ref().unwrap().instructions.len(), 1);
    assert!(
        delivery.upstream_diagnostics.iter().any(|diagnostic| {
            diagnostic["reason"].is_string() && diagnostic["span"].is_object()
        })
    );
}

#[test]
fn stage1_does_not_correct_canonical_ddl_when_macro_expansion_exceeds_its_budget() {
    let definition = inku_ddl::MacroDefinition::from_json(
        &json!({
            "schema": "inku.macro-definition.v1", "namespace": "Example", "heading": "Circle",
            "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
                "op": "emit", "binding": null, "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    "color": {"expr": "semantic_ref", "category": "color", "id": "black"},
                    "position_x": {"expr": "exact_decimal", "value": "0.5"},
                    "position_y": {"expr": "exact_decimal", "value": "0.5"},
                    "count": {"expr": "integer", "value": 1}
                }
            }]
        })
        .to_string(),
    )
    .unwrap();
    let source = "Example.Circle. Example.Circle.";
    let identity = definition.identity().unwrap();
    let document = inku_ddl::NormalizedDdlDocument::new(
        source,
        inku_ddl::ResolvedInstructionLanguage::En,
        vec![
            inku_ddl::MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .unwrap(),
        ],
    )
    .unwrap();
    let mut pipeline_config = config();
    pipeline_config
        .compiler
        .macro_expansion_limits
        .max_invocations = DecimalU64::new(1);
    let compiled = inku_ddl::compile_typed_ddl(
        document,
        std::slice::from_ref(&definition),
        Some(17),
        pipeline_config.compiler.macro_limits().unwrap(),
    );
    assert!(compiled.pre_expansion_canonical_bytes().is_some());
    assert!(
        !compiled
            .compiler_lock
            .as_ref()
            .is_some_and(|lock| lock.state == inku_ddl::CompilerLockState::CanonicalReady)
    );
    pipeline_config.definitions = vec![definition];
    pipeline_config.macro_summaries = vec!["A black circle at the center".into()];
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "expansion-budget".into(),
            authoring_nonce: "expansion-budget-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "Two black circles at the center".into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    let state = run(None, &start).snapshot;
    let generated = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: state.action.as_ref().unwrap().identity.clone(),
                response: json!({"normalized_ddl": source}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    let output = run(Some(&state), &generated);
    assert!(
        matches!(output.snapshot.phase, PipelinePhase::Failed { ref reason } if reason == "stage1_failed")
    );
    assert!(
        output.snapshot.action.is_none()
            && output.snapshot.document.is_none()
            && output.snapshot.delivery.is_none()
    );
    assert!(
        output
            .events
            .iter()
            .all(|event| event.tag != "effect_requested")
    );
}

#[test]
fn committed_ddl_and_approved_hole_patch_share_one_replayable_path() {
    let source = "place one black circle at center.";
    let direct_start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "direct".into(),
            authoring_nonce: "direct-1".into(),
            config: Box::new(config()),
            authority: VariationAuthorityState::new_direct_ddl(),
            authoring: AuthoringInput::DirectDdl {
                source: source.into(),
            },
        },
    );
    let direct_pending = run(None, &direct_start).snapshot;
    assert!(direct_pending.delivery.is_none());
    assert_eq!(
        direct_pending.action.as_ref().unwrap().tag,
        "commit_visible_normalized_ddl"
    );
    let direct_ack = envelope(Some(&direct_pending), ack(&direct_pending));
    let direct = run(Some(&direct_pending), &direct_ack).snapshot;
    assert!(
        matches!(direct.phase, PipelinePhase::ScoreReady),
        "{:?}",
        direct.phase
    );

    let mut transcript = vec![envelope(
        None,
        PipelineInput::Start {
            variation_id: "described".into(),
            authoring_nonce: "description-1".into(),
            config: Box::new(config()),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "One quiet black circle".into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    )];
    let mut outputs = vec![run(None, &transcript[0])];
    let mut state = outputs.last().unwrap().snapshot.clone();
    let first_action = state.action.as_ref().unwrap().identity.clone();
    let retry = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::ProviderFailed {
                identity: first_action.clone(),
                failure: ProviderFailure::TransportUnavailable,
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    outputs.push(run(Some(&state), &retry));
    transcript.push(retry);
    state = outputs.last().unwrap().snapshot.clone();
    assert_eq!(
        state.action.as_ref().unwrap().identity.action_id,
        first_action.action_id
    );
    assert_eq!(state.action.as_ref().unwrap().identity.attempt, 2);
    let generated = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: state.action.as_ref().unwrap().identity.clone(),
                response: json!({"normalized_ddl": source}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    outputs.push(run(Some(&state), &generated));
    transcript.push(generated);
    state = outputs.last().unwrap().snapshot.clone();
    assert!(state.document.is_none() && state.delivery.is_none());
    assert_eq!(state.authority.revision(), 0);
    let committed = envelope(Some(&state), ack(&state));
    outputs.push(run(Some(&state), &committed));
    transcript.push(committed);
    state = outputs.last().unwrap().snapshot.clone();
    assert_eq!(
        state.delivery.as_ref().unwrap().score,
        direct.delivery.as_ref().unwrap().score
    );
    assert_eq!(
        state.authority.authority(),
        AuthoringAuthority::DescriptionAuthoritative
    );
    let acknowledged_delivery = state.delivery.clone().unwrap();

    let edit = envelope(
        Some(&state),
        PipelineInput::CommitUserDdl {
            expected_revision: DecimalU64::new(state.authority.revision()),
            source: "place one red circle at center. many square.".into(),
        },
    );
    outputs.push(run(Some(&state), &edit));
    transcript.push(edit);
    state = outputs.last().unwrap().snapshot.clone();
    assert_eq!(state.delivery.as_ref(), Some(&acknowledged_delivery));
    let edit_ack = envelope(Some(&state), ack(&state));
    outputs.push(run(Some(&state), &edit_ack));
    transcript.push(edit_ack);
    state = outputs.last().unwrap().snapshot.clone();
    assert_eq!(
        state.authority.authority(),
        AuthoringAuthority::DdlAuthoritative
    );
    assert_eq!(
        state.action.as_ref().unwrap().tag,
        "complete_visible_ddl_holes",
        "committed known holes request completion without another user operation"
    );
    let current_safe_delivery = state.delivery.clone().unwrap();
    assert!(
        !current_safe_delivery
            .score
            .as_ref()
            .unwrap()
            .instructions
            .is_empty(),
        "the acknowledged drawable survives while its known hole is completed"
    );
    let base = inku_ddl::compile_typed_ddl(
        state.document.as_ref().unwrap().document().unwrap(),
        &[],
        Some(17),
        config().compiler.macro_limits().unwrap(),
    );
    let lock = base.compiler_lock.as_ref().unwrap();
    assert_eq!(
        lock.state,
        inku_ddl::CompilerLockState::IncompleteKnownHole,
        "fixture must expose only known holes; holes={:?}; conflicts={:?}; blocking={:?}",
        base.holes,
        base.conflicts,
        base.blocking_diagnostics
    );
    let provider_retry = run(
        Some(&state),
        &envelope(
            Some(&state),
            PipelineInput::EffectResult {
                result: EffectResult::ProviderFailed {
                    identity: state.action.as_ref().unwrap().identity.clone(),
                    failure: ProviderFailure::TransportUnavailable,
                    elapsed_ms: DecimalU64::new(20),
                },
            },
        ),
    )
    .snapshot;
    assert_eq!(
        provider_retry.delivery.as_ref(),
        Some(&current_safe_delivery)
    );
    let provider_failed = run(
        Some(&provider_retry),
        &envelope(
            Some(&provider_retry),
            PipelineInput::EffectResult {
                result: EffectResult::ProviderFailed {
                    identity: provider_retry.action.as_ref().unwrap().identity.clone(),
                    failure: ProviderFailure::TransportUnavailable,
                    elapsed_ms: DecimalU64::new(20),
                },
            },
        ),
    )
    .snapshot;
    assert!(matches!(
        provider_failed.phase,
        PipelinePhase::NeedsUserEdit { .. }
    ));
    assert_eq!(
        provider_failed.delivery.as_ref(),
        Some(&current_safe_delivery)
    );
    let validation_retry = run(
        Some(&state),
        &envelope(
            Some(&state),
            PipelineInput::EffectResult {
                result: EffectResult::VisibleDdlHolePatchGenerated {
                    identity: state.action.as_ref().unwrap().identity.clone(),
                    response: "{}".into(),
                    elapsed_ms: DecimalU64::new(20),
                },
            },
        ),
    )
    .snapshot;
    let validation_failed = run(
        Some(&validation_retry),
        &envelope(
            Some(&validation_retry),
            PipelineInput::EffectResult {
                result: EffectResult::VisibleDdlHolePatchGenerated {
                    identity: validation_retry.action.as_ref().unwrap().identity.clone(),
                    response: "{}".into(),
                    elapsed_ms: DecimalU64::new(20),
                },
            },
        ),
    )
    .snapshot;
    assert!(matches!(
        validation_failed.phase,
        PipelinePhase::NeedsUserEdit { .. }
    ));
    assert_eq!(
        validation_failed.delivery.as_ref(),
        Some(&current_safe_delivery)
    );
    assert_eq!(
        validation_failed.hole_completion_check.as_ref().unwrap()["results"][0]["reason"],
        "schema_violation"
    );
    let hole = base.holes.first().expect("known quantity hole").clone();
    let unresolved_patch =
        json!({"results":[{"id":"h1","status":"proposed","replacement":"many square."}]});
    let unresolved = run(
        Some(&state),
        &envelope(
            Some(&state),
            PipelineInput::EffectResult {
                result: EffectResult::VisibleDdlHolePatchGenerated {
                    identity: state.action.as_ref().unwrap().identity.clone(),
                    response: serde_json::to_string(&unresolved_patch).unwrap(),
                    elapsed_ms: DecimalU64::new(20),
                },
            },
        ),
    );
    assert!(matches!(
        unresolved.snapshot.phase,
        PipelinePhase::NeedsUserEdit { .. }
    ));
    assert!(unresolved.events.iter().any(|event| {
        event.tag == "needs_user_edit"
            && event.payload["reason"] == "semantic_violation"
            && event.payload["detail"] == "target_unresolved"
    }));
    assert_eq!(
        unresolved.snapshot.delivery.as_ref(),
        Some(&current_safe_delivery)
    );
    assert!(
        unresolved
            .events
            .iter()
            .any(|event| event.tag == "hole_completion_checked"
                && event.payload["results"][0]["hole_id"] == hole.id
                && event.payload["results"][0]["reason"] == "target_unresolved")
    );
    let patch = json!({"results":[{"id":"h1","status":"proposed","replacement":"8"}]});
    let proposed = envelope(
        Some(&state),
        PipelineInput::EffectResult {
            result: EffectResult::VisibleDdlHolePatchGenerated {
                identity: state.action.as_ref().unwrap().identity.clone(),
                response: serde_json::to_string(&patch).unwrap(),
                elapsed_ms: DecimalU64::new(20),
            },
        },
    );
    outputs.push(run(Some(&state), &proposed));
    transcript.push(proposed);
    state = outputs.last().unwrap().snapshot.clone();
    let PipelinePhase::AwaitingPatchApproval {
        proposal_digest, ..
    } = &state.phase
    else {
        panic!("{:?}", state.phase);
    };
    assert!(state.document.as_ref().unwrap().source.contains("many"));
    assert!(state.action.is_none());
    assert_eq!(state.delivery.as_ref(), Some(&current_safe_delivery));
    let declined = run(
        Some(&state),
        &envelope(
            Some(&state),
            PipelineInput::DeclinePatch {
                proposal_digest: proposal_digest.clone(),
            },
        ),
    )
    .snapshot;
    assert!(matches!(
        declined.phase,
        PipelinePhase::NeedsUserEdit { .. }
    ));
    assert_eq!(declined.delivery.as_ref(), Some(&current_safe_delivery));
    let approve = envelope(
        Some(&state),
        PipelineInput::ApprovePatch {
            expected_revision: DecimalU64::new(state.authority.revision()),
            proposal_digest: proposal_digest.clone(),
        },
    );
    outputs.push(run(Some(&state), &approve));
    transcript.push(approve);
    state = outputs.last().unwrap().snapshot.clone();
    assert!(state.document.as_ref().unwrap().source.contains("many"));
    assert_eq!(state.delivery.as_ref(), Some(&current_safe_delivery));
    let commit_failed = run(
        Some(&state),
        &envelope(
            Some(&state),
            PipelineInput::EffectResult {
                result: EffectResult::HostCommitFailed {
                    identity: state.action.as_ref().unwrap().identity.clone(),
                    actual_revision: Some(DecimalU64::new(state.authority.revision())),
                },
            },
        ),
    )
    .snapshot;
    assert!(matches!(commit_failed.phase, PipelinePhase::Failed { .. }));
    assert_eq!(
        commit_failed.delivery.as_ref(),
        Some(&current_safe_delivery)
    );
    let patch_ack = envelope(Some(&state), ack(&state));
    outputs.push(run(Some(&state), &patch_ack));
    transcript.push(patch_ack);
    state = outputs.last().unwrap().snapshot.clone();
    assert_eq!(
        state.document.as_ref().unwrap().source,
        "place one red circle at center. 8 square."
    );
    assert!(
        matches!(state.phase, PipelinePhase::ScoreReady),
        "{:?}",
        state.phase
    );
    assert!(
        !state
            .delivery
            .as_ref()
            .unwrap()
            .score
            .as_ref()
            .unwrap()
            .instructions
            .is_empty(),
        "the completed source must retain a drawable instruction"
    );
    let replay = crate::replay::replay(None, &transcript).unwrap();
    assert_eq!(
        serde_json::to_value(&outputs).unwrap(),
        serde_json::to_value(&replay).unwrap()
    );
}

#[test]
fn committed_hole_with_local_diagnostics_still_requests_bounded_completion() {
    let mut pipeline_config = config();
    pipeline_config.language = inku_ddl::ResolvedInstructionLanguage::Ja;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "mixed-hole-diagnostic".into(),
            authoring_nonce: "mixed-hole-diagnostic-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_direct_ddl(),
            authoring: AuthoringInput::DirectDdl {
                source: "出力: 黒い背景に、粗筆の黒い四角を中央に置く。面: 粗く塗りつぶす。".into(),
            },
        },
    );
    let pending = run(None, &start).snapshot;
    let committed = envelope(Some(&pending), ack(&pending));
    let state = run(Some(&pending), &committed).snapshot;

    assert_eq!(
        state.action.as_ref().map(|action| action.tag.as_str()),
        Some("complete_visible_ddl_holes")
    );
    let lock = state
        .delivery
        .as_ref()
        .and_then(|delivery| delivery.compiler_lock.as_ref())
        .expect("mixed compilation retains its compiler lock");
    assert_eq!(lock["state"], "blocked_diagnostic");
    assert_eq!(
        lock["blocking_diagnostic_identities"]
            .as_array()
            .map(Vec::len),
        Some(2)
    );
    assert_eq!(lock["hole_identities"].as_array().map(Vec::len), Some(1));
}

#[test]
fn independent_hole_results_keep_valid_subset_without_retry_after_ack() {
    // One failure: an invalid second quantity used to discard the valid first
    // edit. The same boundary must stay atomic for coordinated owners.
    for (source, independent) in [
        (
            "ink wash ground. place one red circle at center. many square. many circle.",
            true,
        ),
        (
            "ink wash ground. place one red circle at center. many circles and many squares.",
            false,
        ),
    ] {
        let start = envelope(
            None,
            PipelineInput::Start {
                variation_id: "partial-holes".into(),
                authoring_nonce: "partial-holes-1".into(),
                config: Box::new(config()),
                authority: VariationAuthorityState::new_direct_ddl(),
                authoring: AuthoringInput::DirectDdl {
                    source: source.into(),
                },
            },
        );
        let pending = run(None, &start).snapshot;
        let state = run(Some(&pending), &envelope(Some(&pending), ack(&pending))).snapshot;
        let base = inku_ddl::compile_typed_ddl(
            state.document.as_ref().unwrap().document().unwrap(),
            &[],
            Some(17),
            config().compiler.macro_limits().unwrap(),
        );
        assert_eq!(base.holes.len(), 2, "{:?}", base.holes);
        assert_eq!(
            crate::hole_completion::independent_units(
                &base,
                &base.holes.iter().collect::<Vec<_>>()
            )
            .len(),
            if independent { 2 } else { 1 }
        );
        let retained = state.delivery.clone();
        let response = json!({"results":[
            {"id":"h1","status":"proposed","replacement":"8"},
            {"id":"h2","status":"proposed","replacement":"many"}
        ]});
        let checked = run(
            Some(&state),
            &envelope(
                Some(&state),
                PipelineInput::EffectResult {
                    result: EffectResult::VisibleDdlHolePatchGenerated {
                        identity: state.action.as_ref().unwrap().identity.clone(),
                        response: response.to_string(),
                        elapsed_ms: DecimalU64::new(20),
                    },
                },
            ),
        );
        assert_eq!(checked.snapshot.delivery, retained);
        let report = checked
            .events
            .iter()
            .find(|event| event.tag == "hole_completion_checked")
            .unwrap();
        assert_eq!(report.payload["results"][1]["status"], "rejected");
        if independent {
            assert_eq!(
                report.payload["results"][0]["status"], "validated",
                "{:?}",
                report.payload
            );
            let PipelinePhase::AwaitingPatchApproval {
                patch,
                proposal_digest,
                ..
            } = &checked.snapshot.phase
            else {
                panic!("{:?}; {:?}", checked.snapshot.phase, report.payload)
            };
            assert_eq!(patch.edits.len(), 1);
            let approved = run(
                Some(&checked.snapshot),
                &envelope(
                    Some(&checked.snapshot),
                    PipelineInput::ApprovePatch {
                        expected_revision: DecimalU64::new(checked.snapshot.authority.revision()),
                        proposal_digest: proposal_digest.clone(),
                    },
                ),
            )
            .snapshot;
            let committed = run(Some(&approved), &envelope(Some(&approved), ack(&approved)));
            assert!(
                committed.snapshot.action.is_none(),
                "remaining holes must not auto-retry after partial ACK"
            );
            assert!(
                committed
                    .snapshot
                    .delivery
                    .as_ref()
                    .unwrap()
                    .score
                    .is_some()
            );
            assert!(
                committed
                    .snapshot
                    .document
                    .as_ref()
                    .unwrap()
                    .source
                    .contains("8 square")
            );
            assert!(
                committed
                    .snapshot
                    .document
                    .as_ref()
                    .unwrap()
                    .source
                    .contains("many circle")
            );
            assert!(
                committed
                    .events
                    .iter()
                    .any(|event| event.tag == "hole_completion_checked")
            );
        } else {
            assert_eq!(report.payload["results"][0]["status"], "rejected");
            assert!(matches!(
                checked.snapshot.phase,
                PipelinePhase::NeedsUserEdit { .. }
            ));
            assert!(checked.snapshot.action.is_none());
        }
    }
}

#[test]
fn host_json_float_roundtrip_preserves_snapshot_number() {
    let parsed: f64 = serde_json::from_str("108.58661719879423").unwrap();
    assert_eq!(parsed.to_bits(), 108.58661719879423_f64.to_bits());
}

fn sketch_start(sketch: SketchRequest) -> PipelineSnapshot {
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "sketch".into(),
            authoring_nonce: "sketch-1".into(),
            config: Box::new(config()),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "A crane stands alone".into(),
                auto_catalog: false,
                sketch,
            },
        },
    );
    run(None, &start).snapshot
}

fn sketch_answer(state: &PipelineSnapshot, response: serde_json::Value) -> StepOutput {
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "generate_sketch");
    let result = PipelineInput::EffectResult {
        result: EffectResult::SketchGenerated {
            identity: action.identity.clone(),
            response: response.to_string(),
            elapsed_ms: DecimalU64::new(5),
        },
    };
    run(Some(state), &envelope(Some(state), result))
}

fn stage1_message(state: &PipelineSnapshot) -> serde_json::Value {
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "generate_normalized_ddl");
    serde_json::from_str(action.payload["prompt"]["message"].as_str().unwrap()).unwrap()
}

#[test]
fn a_supplementing_sketch_reaches_stage1_beside_the_description() {
    let pending = sketch_start(SketchRequest::On);
    let output = sketch_answer(&pending, json!({"sketch": "A wide marsh under a pale winter sky."}));
    let state = output.snapshot;
    let record = state.sketch.as_ref().unwrap();
    assert_eq!(record.state, SketchState::Supplemented);
    let message = stage1_message(&state);
    assert_eq!(message["description"], "A crane stands alone");
    assert_eq!(message["sketch"], "A wide marsh under a pale winter sky.");
    assert!(output.events.iter().any(|event| event.tag == "sketch_ready"));
}

#[test]
fn an_empty_sketch_draws_from_the_description_alone() {
    let pending = sketch_start(SketchRequest::On);
    let state = sketch_answer(&pending, json!({"sketch": "  "})).snapshot;
    assert_eq!(state.sketch.as_ref().unwrap().state, SketchState::NotNeeded);
    assert!(stage1_message(&state).get("sketch").is_none());
}

#[test]
fn a_failed_sketch_falls_back_to_the_description_without_stopping() {
    let mut state = sketch_start(SketchRequest::On);
    for _ in 0..2 {
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "generate_sketch");
        let failed = PipelineInput::EffectResult {
            result: EffectResult::ProviderFailed {
                identity: action.identity.clone(),
                failure: ProviderFailure::TransportUnavailable,
                elapsed_ms: DecimalU64::new(5),
            },
        };
        state = run(Some(&state), &envelope(Some(&state), failed)).snapshot;
    }
    assert_eq!(state.sketch.as_ref().unwrap().state, SketchState::Fallback);
    assert!(stage1_message(&state).get("sketch").is_none());
}

#[test]
fn an_edited_sketch_is_used_without_a_request() {
    let state = sketch_start(SketchRequest::Supplied {
        text: "Reeds in a row along the water.".into(),
    });
    assert_eq!(state.sketch.as_ref().unwrap().state, SketchState::Supplied);
    assert_eq!(stage1_message(&state)["sketch"], "Reeds in a row along the water.");
}

#[test]
fn a_run_without_a_sketch_keeps_its_previous_request_shape() {
    let state = sketch_start(SketchRequest::Off);
    assert!(state.sketch.is_none());
    assert!(stage1_message(&state).get("sketch").is_none());
    let wire = serde_json::to_value(&state).unwrap();
    assert!(wire.get("sketch").is_none());
}
