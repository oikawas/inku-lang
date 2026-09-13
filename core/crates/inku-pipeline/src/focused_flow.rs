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
    AuthoringInput, PipelineConfig, PipelineInput, PipelinePhase, PipelineSnapshot, StepOutput,
};
use crate::prompts::{HolePatchEditResponse, HolePatchResponse, PromptLimits};
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
    let edit_ack = envelope(Some(&state), ack(&state));
    outputs.push(run(Some(&state), &edit_ack));
    transcript.push(edit_ack);
    state = outputs.last().unwrap().snapshot.clone();
    assert_eq!(
        state.authority.authority(),
        AuthoringAuthority::DdlAuthoritative
    );
    assert!(
        state.action.is_none(),
        "holes never call an LLM by themselves"
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
    let hole = base.holes.first().expect("known quantity hole").clone();
    let complete = envelope(
        Some(&state),
        PipelineInput::CompleteHoles {
            expected_revision: DecimalU64::new(state.authority.revision()),
            hole_ids: vec![hole.id.clone()],
        },
    );
    outputs.push(run(Some(&state), &complete));
    transcript.push(complete);
    state = outputs.last().unwrap().snapshot.clone();
    let patch = HolePatchResponse {
        schema_id: inku_ddl::VISIBLE_DDL_PATCH_SCHEMA_ID.into(),
        base_source_digest: lock.visible_source_digest.clone(),
        base_compiler_lock_digest: lock.full_digest.clone(),
        edits: vec![HolePatchEditResponse {
            hole_id: hole.id,
            allowed_span: hole.allowed_span.into(),
            expected_range_digest: hole.expected_range_digest,
            replacement: "8".into(),
        }],
    };
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
    assert!(state.action.is_none() && state.delivery.is_none());
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
