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
    AuthoringInput, CompositionConfig, PipelineConfig, PipelineInput, PipelinePhase,
    PipelineSnapshot, SketchRequest, SketchState, StepOutput,
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
        composition: None,
        composition_retry: None,
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
fn a_saved_unit_of_the_retired_saijiki_waits_for_its_host_to_migrate_it() {
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "retired-saijiki".into(),
            authoring_nonce: "retired-saijiki-1".into(),
            config: Box::new(config()),
            authority: VariationAuthorityState::new_direct_ddl(),
            authoring: AuthoringInput::DirectDdl {
                source: "place one red circle at center.".into(),
            },
        },
    );
    let pending = run(None, &start).snapshot;
    let committed = run(Some(&pending), &envelope(Some(&pending), ack(&pending))).snapshot;
    let document = committed.document.as_ref().unwrap();
    // A new document names the edition it is written with.
    assert_eq!(document.saijiki, inku_ddl::SAIJIKI_ASSET_ID);
    assert_eq!(
        serde_json::to_value(document).unwrap()["saijiki"],
        inku_ddl::SAIJIKI_ASSET_ID
    );

    // A document saved before the field was written with v1 and keeps its saved bytes.
    let mut retired = committed.clone();
    retired.document.as_mut().unwrap().saijiki = inku_ddl::SAIJIKI_V1_ASSET_ID.into();
    assert!(
        serde_json::to_value(retired.document.as_ref().unwrap())
            .unwrap()
            .get("saijiki")
            .is_none()
    );
    retired.snapshot_digest.clear();
    retired.snapshot_digest =
        crate::protocol::value_digest("inku.pipeline-snapshot.v1", &retired).unwrap();
    let edit = PipelineInput::CommitUserDdl {
        expected_revision: DecimalU64::new(retired.authority.revision()),
        source: "place one blue circle at center.".into(),
    };
    let refused = run_error(Some(&retired), &envelope(Some(&retired), edit));
    assert_eq!(refused["payload"]["code"], "saijiki_migration_required");

    // A saved definition that only a migration makes valid is refused the same way.
    let definition = |amplitude: &str| {
        inku_ddl::MacroDefinition::from_json(
            &json!({
                "schema": "inku.macro-definition.v1", "namespace": "Saved", "heading": "Sway",
                "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
                    "op": "emit", "binding": null, "fields": {
                        "shape": {"expr": "semantic_ref", "category": "shape", "id": "line"},
                        "fluctuation_amplitude":
                            {"expr": "semantic_ref", "category": "variation", "id": amplitude}
                    }
                }]
            })
            .to_string(),
        )
        .unwrap()
    };
    for (amplitude, code) in [
        ("fine", "saijiki_migration_required"),
        ("unknown", "schema_violation"),
    ] {
        let mut saved = config();
        saved.definitions = vec![definition(amplitude)];
        saved.macro_summaries = vec!["A swaying line".into()];
        let start = envelope(
            None,
            PipelineInput::Start {
                variation_id: format!("retired-definition-{amplitude}"),
                authoring_nonce: "retired-definition-1".into(),
                config: Box::new(saved),
                authority: VariationAuthorityState::new_direct_ddl(),
                authoring: AuthoringInput::DirectDdl {
                    source: "Saved.Sway.".into(),
                },
            },
        );
        assert_eq!(
            run_error(None, &start)["payload"]["code"],
            code,
            "{amplitude}"
        );
    }
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
    assert!(rejected_output.events.iter().any(|event| {
        event.tag == "failed"
            && event.payload["reason"] == "semantic_violation"
            && event.payload["detail"] == "macro_resolution_missing_lock"
    }));
    assert!(
        rejected_output
            .events
            .iter()
            .all(|event| event.tag != "visible_ddl_ready"),
        "an all-omitted candidate must not enter the CAS path"
    );
}

#[test]
fn a_retrying_stage1_reports_its_attempt_and_budget() {
    // Hosts showed only elapsed time, so a timed-out first attempt looked
    // like a slow answer.
    let mut pipeline_config = config();
    pipeline_config.stage1_retry.max_attempts = 2;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "attempt-progress".into(),
            authoring_nonce: "attempt-progress-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "One quiet black circle".into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    let first = run(None, &start).snapshot;
    let failed = envelope(
        Some(&first),
        PipelineInput::EffectResult {
            result: EffectResult::ProviderFailed {
                identity: first.action.as_ref().unwrap().identity.clone(),
                failure: ProviderFailure::TransportTimeout,
                elapsed_ms: DecimalU64::new(1000),
            },
        },
    );
    let second = run(Some(&first), &failed).snapshot;
    let report: serde_json::Value = serde_json::from_slice(
        &crate::byte_envelope::provider_attempt_owned(&serde_json::to_vec(&second).unwrap()),
    )
    .unwrap();
    assert_eq!(
        report,
        json!({"provider_attempt": {
            "action": "generate_normalized_ddl",
            "attempt": 2,
            "max_attempts": 2,
            "delay_ms": "10",
            "timeout_ms": "1000",
        }})
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
                source: "出力: 黒い背景に、粗筆の黒い四角を中心に置く。面: 粗く塗りつぶす。".into(),
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
    let output = sketch_answer(
        &pending,
        json!({"sketch": "A wide marsh under a pale winter sky."}),
    );
    let state = output.snapshot;
    let record = state.sketch.as_ref().unwrap();
    assert_eq!(record.state, SketchState::Supplemented);
    let message = stage1_message(&state);
    assert_eq!(message["description"], "A crane stands alone");
    assert_eq!(message["sketch"], "A wide marsh under a pale winter sky.");
    assert!(
        output
            .events
            .iter()
            .any(|event| event.tag == "sketch_ready")
    );
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
    assert_eq!(
        stage1_message(&state)["sketch"],
        "Reeds in a row along the water."
    );
}

#[test]
fn a_run_without_a_sketch_keeps_its_previous_request_shape() {
    let state = sketch_start(SketchRequest::Off);
    assert!(state.sketch.is_none());
    assert!(stage1_message(&state).get("sketch").is_none());
    let wire = serde_json::to_value(&state).unwrap();
    assert!(wire.get("sketch").is_none());
}

fn ground_start(pipeline_config: PipelineConfig) -> PipelineSnapshot {
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "ground".into(),
            authoring_nonce: "ground-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: "A white circle beside a black square".into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    run(None, &start).snapshot
}

fn ground_answer(state: &PipelineSnapshot, ddl: &str) -> StepOutput {
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "generate_normalized_ddl");
    let result = PipelineInput::EffectResult {
        result: EffectResult::NormalizedDdlGenerated {
            identity: action.identity.clone(),
            response: json!({"normalized_ddl": ddl}).to_string(),
            elapsed_ms: DecimalU64::new(20),
        },
    };
    run(Some(state), &envelope(Some(state), result))
}

const WHITE_ON_WHITE: &str = "place one white circle at center.\nplace one black square at center.";

#[test]
fn stage1_returns_the_layers_drawn_only_in_the_background_colour() {
    // A white mark on the white ground it lies on is not seen. The reader
    // gets the compiled candidate back once, with the colour and the sentences.
    let answered = "Fill the background with gray.\nplace one white circle at center.\nplace one black square at center.";
    let first = ground_start(config());
    let first_action = first.action.as_ref().unwrap().identity.clone();
    let output = ground_answer(&first, WHITE_ON_WHITE);
    let state = output.snapshot;
    assert!(state.document.is_none() && state.delivery.is_none());
    assert_eq!(
        state.stage1_fallback.as_ref().unwrap().source,
        WHITE_ON_WHITE
    );
    let returned = output
        .events
        .iter()
        .find(|event| event.tag == "stage1_returned")
        .expect("the candidate goes back to the reader");
    assert_eq!(returned.payload["reason"], "ground_coloured_layers");
    assert_eq!(returned.payload["background"], "white");
    assert_eq!(returned.payload["layers"], 1);
    assert!(
        output
            .events
            .iter()
            .all(|event| { event.tag != "retry_scheduled" && event.tag != "visible_ddl_ready" })
    );
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.identity.attempt, 2);
    assert_ne!(action.identity.action_id, first_action.action_id);
    let feedback = &stage1_message(&state)["background_feedback"];
    assert_eq!(feedback["previous_ddl"], WHITE_ON_WHITE);
    assert_eq!(feedback["background"], "white");
    let layers = feedback["layers"].as_array().unwrap();
    assert_eq!(layers.len(), 1);
    assert_eq!(
        layers[0]["text"].as_str().unwrap().trim_end_matches('.'),
        "place one white circle at center"
    );
    let system = action.payload["prompt"]["system"].as_str().unwrap();
    assert!(
        system.contains(
            "choose again a background color that every mark of the plan can be told from"
        )
    );
    assert!(system.contains("leave out the colors of the previous plan's marks"));
    // The circle is white and the square black; an unspecified background is white.
    let choices = action.payload["prompt"]["response_schema"]["properties"]["background"]["enum"]
        .as_array()
        .unwrap();
    for colour in ["white", "black", "unspecified"] {
        assert!(!choices.iter().any(|choice| choice == colour), "{colour}");
    }
    assert!(choices.iter().any(|choice| choice == "gray"));

    let state = ground_answer(&state, answered).snapshot;
    assert!(state.stage1_fallback.is_none());
    let commit = state.action.as_ref().unwrap();
    assert_eq!(commit.tag, "commit_visible_normalized_ddl");
    assert_eq!(commit.payload["document"]["source"], answered);
    assert_eq!(commit.payload["reason"], "stage1_generated");
    let committed = run(Some(&state), &envelope(Some(&state), ack(&state))).snapshot;
    assert!(matches!(committed.phase, PipelinePhase::ScoreReady));
    let score = committed.delivery.unwrap().score.unwrap();
    assert_eq!(score.background, Color::Gray);
}

#[test]
fn a_failed_return_commits_the_kept_candidate() {
    let returned = ground_answer(&ground_start(config()), WHITE_ON_WHITE).snapshot;
    let identity = returned.action.as_ref().unwrap().identity.clone();
    let transport = PipelineInput::EffectResult {
        result: EffectResult::ProviderFailed {
            identity,
            failure: ProviderFailure::TransportUnavailable,
            elapsed_ms: DecimalU64::new(20),
        },
    };
    let failed = run(Some(&returned), &envelope(Some(&returned), transport));
    let uncompiled = ground_answer(&returned, "Unknown.Macro.");
    for output in [failed, uncompiled] {
        let state = output.snapshot;
        assert!(state.stage1_fallback.is_none());
        let commit = state.action.as_ref().unwrap();
        assert_eq!(commit.tag, "commit_visible_normalized_ddl");
        assert_eq!(commit.payload["document"]["source"], WHITE_ON_WHITE);
        assert_eq!(commit.payload["reason"], "stage1_generated");
        assert!(
            output
                .events
                .iter()
                .any(|event| event.tag == "stage1_fallback"
                    && event.payload["failure"].is_string())
        );
        assert!(output.events.iter().all(|event| event.tag != "failed"));
        let committed = run(Some(&state), &envelope(Some(&state), ack(&state))).snapshot;
        assert!(matches!(committed.phase, PipelinePhase::ScoreReady));
        assert_eq!(committed.document.unwrap().source, WHITE_ON_WHITE);
    }
    let cancelled = run(
        Some(&returned),
        &envelope(Some(&returned), PipelineInput::Cancel),
    )
    .snapshot;
    assert!(cancelled.stage1_fallback.is_none());
    assert!(matches!(cancelled.phase, PipelinePhase::Cancelled));
}

#[test]
fn the_return_is_asked_once_and_its_answer_is_kept() {
    // The reader keeps a colour the description states; a second return
    // would ask the same question again.
    let still_white = "place one white square at center.\nplace one black circle at center.";
    let mut pipeline_config = config();
    pipeline_config.stage1_retry.max_attempts = 4;
    let returned = ground_answer(&ground_start(pipeline_config), WHITE_ON_WHITE).snapshot;
    let output = ground_answer(&returned, still_white);
    assert!(
        output
            .events
            .iter()
            .all(|event| event.tag != "stage1_returned")
    );
    let commit = output.snapshot.action.as_ref().unwrap();
    assert_eq!(commit.tag, "commit_visible_normalized_ddl");
    assert_eq!(commit.payload["document"]["source"], still_white);
}

#[test]
fn stage1_keeps_its_candidate_without_budget_or_where_the_ground_covers_the_background() {
    let mut single = config();
    single.stage1_retry.max_attempts = 1;
    let without_budget = ground_answer(&ground_start(single), WHITE_ON_WHITE).snapshot;
    // The mezzotint plate covers the white background, so a white mark shows.
    let mezzotint =
        "Mezzotint.\nplace one white circle at center.\nplace one gray square at center.";
    let covered = ground_answer(&ground_start(config()), mezzotint).snapshot;
    let visible = "Fill the background with gray.\nplace one white circle at center.";
    let distinct = ground_answer(&ground_start(config()), visible).snapshot;
    for (state, source) in [
        (without_budget, WHITE_ON_WHITE),
        (covered, mezzotint),
        (distinct, visible),
    ] {
        assert!(state.stage1_fallback.is_none(), "{source}");
        let commit = state.action.as_ref().unwrap();
        assert_eq!(commit.tag, "commit_visible_normalized_ddl", "{source}");
        assert_eq!(commit.payload["document"]["source"], source);
        let wire = serde_json::to_value(&state).unwrap();
        assert!(wire.get("stage1_fallback").is_none(), "{source}");
    }
}

#[test]
fn the_background_choices_stay_whole_when_every_colour_is_a_mark() {
    let every_colour = [
        "white", "black", "blue", "red", "green", "gray", "yellow", "orange", "purple",
    ]
    .map(|colour| format!("place one {colour} circle at center."))
    .join("\n");
    let first = ground_start(config());
    let whole = first.action.as_ref().unwrap().payload["prompt"]["response_schema"]["properties"]
        ["background"]["enum"]
        .clone();
    let state = ground_answer(&first, &every_colour).snapshot;
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "generate_normalized_ddl");
    assert_eq!(
        action.payload["prompt"]["response_schema"]["properties"]["background"]["enum"],
        whole
    );
    assert!(
        action.payload["prompt"]["system"]
            .as_str()
            .unwrap()
            .contains("When the description states the background color")
    );
}

const COMPOSED_DESCRIPTION: &str = "A red circle above black dots scattered at the bottom";

fn plan_layer(
    action: &str,
    shape: &str,
    count: u32,
    position: &str,
    size: &str,
    color: &str,
) -> serde_json::Value {
    json!({
        "action": action, "angle": "unspecified", "bleeding": "unspecified", "color": color,
        "continuity": "unspecified", "count": count, "handling": "dense",
        "line_up_direction": "unspecified", "motion_amplitude": "unspecified",
        "motion_quality": "unspecified", "position": position, "proportion": "unspecified",
        "shape": shape, "size": size, "surface": if shape == "point" { "empty" } else { "flat" },
        "thinness": "unspecified", "tool": "pen"
    })
}

/// A plan as Stage 1 returns it: a field, a focal circle and dots the
/// description places at the bottom.
fn composed_plan_response() -> serde_json::Value {
    json!({"ground": "paper", "background": "white", "plugins": [], "layers": [
        plan_layer("fill", "square", 1, "unspecified", "large", "gray"),
        plan_layer("place", "circle", 1, "center", "small", "red"),
        plan_layer("scatter", "point", 12, "bottom", "very_small", "black"),
    ]})
}

fn composition_start(composition: Option<CompositionConfig>) -> PipelineSnapshot {
    let mut pipeline_config = config();
    pipeline_config.composition = composition;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "composition".into(),
            authoring_nonce: "composition-1".into(),
            config: Box::new(pipeline_config),
            authority: VariationAuthorityState::new_description(),
            authoring: AuthoringInput::Description {
                description: COMPOSED_DESCRIPTION.into(),
                auto_catalog: false,
                sketch: SketchRequest::Off,
            },
        },
    );
    run(None, &start).snapshot
}

fn stage1_system(state: &PipelineSnapshot) -> &str {
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "generate_normalized_ddl");
    action.payload["prompt"]["system"].as_str().unwrap()
}

fn plan_answer(state: &PipelineSnapshot) -> StepOutput {
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "generate_normalized_ddl");
    let result = PipelineInput::EffectResult {
        result: EffectResult::NormalizedDdlGenerated {
            identity: action.identity.clone(),
            response: composed_plan_response().to_string(),
            elapsed_ms: DecimalU64::new(20),
        },
    };
    run(Some(state), &envelope(Some(state), result))
}

fn committed_source(state: &PipelineSnapshot) -> String {
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "commit_visible_normalized_ddl");
    action.payload["document"]["source"]
        .as_str()
        .unwrap()
        .to_owned()
}

fn tags(output: &StepOutput) -> Vec<&str> {
    output
        .events
        .iter()
        .map(|event| event.tag.as_str())
        .collect()
}

#[test]
fn a_composing_run_reads_the_settled_plan_and_commits_marked_ranges() {
    let pending = composition_start(Some(CompositionConfig { read: true }));
    // A composing run asks Stage 1 for a place only where the description states one.
    assert!(stage1_system(&pending).contains("8. Choose a place only for a layer"));
    let reading_requested = plan_answer(&pending);
    let state = reading_requested.snapshot;
    let action = state.action.as_ref().unwrap();
    assert_eq!(action.tag, "read_composition");
    assert!(state.composition.is_some());
    let message = action.payload["prompt"]["message"].as_str().unwrap();
    assert!(
        message.starts_with("Description:\nA red circle above black dots"),
        "{message}"
    );
    assert!(
        message.contains("[place set by the work plan: bottom]"),
        "{message}"
    );
    let reading = json!({
        "thesis": "a lone circle above a floor of dots",
        "roles": ["field", "focal", "scattered"],
        "relations": [{"type": "above", "layers": [1, 2], "side": "unspecified", "toward": "unspecified"}],
        "tension": {"motion": "still", "focus": "unspecified", "vertical": "unspecified",
                    "balance": "unspecified", "symmetry": "unspecified", "void": "unspecified"},
        "stated_places": [{"layer": 2, "words": "at the bottom", "place": "bottom"}]
    });
    let result = PipelineInput::EffectResult {
        result: EffectResult::CompositionRead {
            identity: action.identity.clone(),
            response: reading.to_string(),
            elapsed_ms: DecimalU64::new(30),
        },
    };
    let read = run(Some(&state), &envelope(Some(&state), result));
    assert!(
        tags(&read).contains(&"composition_read"),
        "{:?}",
        tags(&read)
    );
    let source = committed_source(&read.snapshot);
    let lines: Vec<&str> = source.lines().collect();
    // The field and the circle are placed by the composition; the dots keep the
    // place the description states.
    assert!(lines[2].contains(" at the [composition] "), "{source}");
    assert!(lines[3].contains(" at the [composition] "), "{source}");
    assert!(lines[4].ends_with(" at the bottom."), "{source}");
    assert!(read.snapshot.composition.is_none());
    let committed = run(
        Some(&read.snapshot),
        &envelope(Some(&read.snapshot), ack(&read.snapshot)),
    )
    .snapshot;
    assert!(
        matches!(committed.phase, PipelinePhase::ScoreReady),
        "{:?}",
        committed.phase
    );
}

#[test]
fn a_run_that_does_not_read_composes_from_the_default_reading() {
    let pending = composition_start(Some(CompositionConfig { read: false }));
    let output = plan_answer(&pending);
    let source = committed_source(&output.snapshot);
    let lines: Vec<&str> = source.lines().collect();
    assert!(lines[2].contains(" at the [composition] "), "{source}");
    // Without a reading every place the plan set is kept.
    assert!(lines[3].ends_with(" at the center."), "{source}");
    assert!(lines[4].ends_with(" at the bottom."), "{source}");
}

#[test]
fn a_failed_reading_composes_from_the_default_reading() {
    let pending = composition_start(Some(CompositionConfig { read: true }));
    let mut state = plan_answer(&pending).snapshot;
    let mut last = None;
    for _ in 0..2 {
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "read_composition");
        let result = PipelineInput::EffectResult {
            result: EffectResult::ProviderFailed {
                identity: action.identity.clone(),
                failure: ProviderFailure::RateLimited,
                elapsed_ms: DecimalU64::new(10),
            },
        };
        let output = run(Some(&state), &envelope(Some(&state), result));
        state = output.snapshot.clone();
        last = Some(output);
    }
    let last = last.unwrap();
    assert!(
        tags(&last).contains(&"composition_fallback"),
        "{:?}",
        tags(&last)
    );
    assert!(committed_source(&state).contains(" at the [composition] "));
}

/// A white circle on the white ground sends the plan back to Stage 1 once,
/// keeping the candidate in case the returned request fails. The second plan
/// settles and is read for composition; the kept candidate belongs to the
/// returned request only (Pentala 2026-10-04: passing the reading failed with
/// invalid_state because the kept candidate outlived Stage 1).
#[test]
fn a_returned_stage1_settles_into_the_composition_reading() {
    let answer = |state: &PipelineSnapshot, plan: serde_json::Value| {
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "generate_normalized_ddl");
        let result = PipelineInput::EffectResult {
            result: EffectResult::NormalizedDdlGenerated {
                identity: action.identity.clone(),
                response: plan.to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        };
        run(Some(state), &envelope(Some(state), result))
    };
    let pending = composition_start(Some(CompositionConfig { read: true }));
    let white_on_white = json!({"ground": "paper", "background": "white", "plugins": [], "layers": [
        plan_layer("place", "circle", 1, "unspecified", "small", "white"),
        plan_layer("place", "square", 1, "unspecified", "small", "black"),
    ]});
    let returned = answer(&pending, white_on_white);
    assert!(
        tags(&returned).contains(&"stage1_returned"),
        "{:?}",
        tags(&returned)
    );
    assert!(returned.snapshot.stage1_fallback.is_some());
    let settled = answer(&returned.snapshot, composed_plan_response()).snapshot;
    let action = settled.action.as_ref().unwrap();
    assert_eq!(action.tag, "read_composition");
    assert!(settled.stage1_fallback.is_none() && settled.stage1_fallback_plan.is_none());
    let reading = json!({
        "thesis": "a lone circle above a floor of dots",
        "roles": ["field", "focal", "scattered"],
        "relations": [{"type": "above", "layers": [1, 2], "side": "unspecified", "toward": "unspecified"}],
        "tension": {"motion": "still", "focus": "unspecified", "vertical": "unspecified",
                    "balance": "unspecified", "symmetry": "unspecified", "void": "unspecified"},
        "stated_places": [{"layer": 2, "words": "at the bottom", "place": "bottom"}]
    });
    let result = PipelineInput::EffectResult {
        result: EffectResult::CompositionRead {
            identity: action.identity.clone(),
            response: reading.to_string(),
            elapsed_ms: DecimalU64::new(30),
        },
    };
    let read = run(Some(&settled), &envelope(Some(&settled), result));
    assert!(
        tags(&read).contains(&"composition_read"),
        "{:?}",
        tags(&read)
    );
    assert!(committed_source(&read.snapshot).contains(" at the [composition] "));
    let committed = run(
        Some(&read.snapshot),
        &envelope(Some(&read.snapshot), ack(&read.snapshot)),
    )
    .snapshot;
    assert!(
        matches!(committed.phase, PipelinePhase::ScoreReady),
        "{:?}",
        committed.phase
    );
}

#[test]
fn a_run_without_composition_commits_the_plan_as_printed() {
    let pending = composition_start(None);
    // Without the step Stage 1 keeps the principle that spreads the layers itself.
    let system = stage1_system(&pending);
    assert!(system.contains("8. Empty space is part of the composition. Do not gather"));
    assert!(!system.contains("8. Choose a place only"));
    let output = plan_answer(&pending);
    let source = committed_source(&output.snapshot);
    assert!(!source.contains("[composition]"), "{source}");
    assert!(
        !tags(&output)
            .iter()
            .any(|tag| tag.starts_with("composition"))
    );
}
