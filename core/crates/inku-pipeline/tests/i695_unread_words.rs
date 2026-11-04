#![allow(dead_code, unused_imports)]
//! Exercise approval notices through the shared pipeline without a provider.

use inku_score::{
    CANVAS_FORMAT_REGISTRY_ID, Color, HardResourcePolicy, OperationalResourceBudget,
    ResourceBudget, ResourceDemand, ScoreErrorPolicy, canvas_format_registry_digest,
};
use serde_json::json;

use inku_pipeline::authority::{AuthoringAuthority, VariationAuthorityState};
use inku_pipeline::byte_envelope::{EnvelopeLimits, step_owned};
use inku_pipeline::core_boundary::{
    CatalogMode, CompilerOptions, MacroExpansionLimitsDto, ResolvedHostOptions,
    ResolvedPaletteColorDto, ResolvedPaletteDto,
};
use inku_pipeline::machine::{
    AuthoringInput, ColorsConfig, CompositionConfig, CompositionRequest, DescriptionRoute,
    LawsConfig, PipelineConfig, PipelineInput, PipelinePhase, PipelineSnapshot, SketchRequest,
    SketchState, StepOutput,
};
use inku_pipeline::prompts::PromptLimits;
use inku_pipeline::protocol::{
    DecimalU64, EffectResult, Envelope, PROTOCOL_NAME, PROTOCOL_VERSION, ProviderFailure,
    RetryPolicy,
};

/// A host's run configuration, also what a host sends with a recomposition.
pub(crate) fn config() -> PipelineConfig {
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
            paints: None,
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
        plugin_offers: Vec::new(),
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
        catalog_seed: None,
        prompt_limits: PromptLimits {
            max_offered_plugins: 8,
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
        laws: None,
        laws_retry: None,
        colors: None,
        colors_retry: None,
        image: None,
        image_retry: None,
        description_ddl: None,
    }
}

pub(crate) fn envelope(
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

pub(crate) fn run(
    snapshot: Option<&PipelineSnapshot>,
    input: &Envelope<PipelineInput>,
) -> StepOutput {
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

pub(crate) fn run_error(
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

pub(crate) fn ack(state: &PipelineSnapshot) -> PipelineInput {
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

fn proposed(
    lang: inku_ddl::ResolvedInstructionLanguage,
    source: &str,
    replacement: &str,
) -> StepOutput {
    let mut settings = config();
    settings.language = lang;
    let start = envelope(
        None,
        PipelineInput::Start {
            variation_id: "i695".into(),
            authoring_nonce: "i695-1".into(),
            config: Box::new(settings),
            authority: VariationAuthorityState::new_direct_ddl(),
            authoring: AuthoringInput::DirectDdl {
                source: source.into(),
                completion_ranges: None,
                laws_layers: None,
                laws_basis: None,
                declare_canvas: false,
            },
        },
    );
    let pending = run(None, &start).snapshot;
    let state = run(Some(&pending), &envelope(Some(&pending), ack(&pending))).snapshot;
    assert_eq!(
        state.action.as_ref().unwrap().tag,
        "complete_visible_ddl_holes"
    );
    let result = PipelineInput::EffectResult {
        result: EffectResult::VisibleDdlHolePatchGenerated {
            identity: state.action.as_ref().unwrap().identity.clone(),
            response:
                json!({"results":[{"id":"h1","status":"proposed","replacement":replacement}]})
                    .to_string(),
            elapsed_ms: DecimalU64::new(20),
        },
    };
    run(Some(&state), &envelope(Some(&state), result))
}

#[test]
fn i695_unread_words_are_attached_to_each_approval_and_event() {
    use inku_ddl::ResolvedInstructionLanguage::{En, Ja};
    let cases = [
        (
            Ja,
            "謎めいた青い線を中心に置く。",
            "青い線を中心に置く。",
            Some("謎めいた青い"),
        ),
        (
            En,
            "place one enigmatic blue line at center.",
            "place one blue line at center.",
            Some("enigmatic"),
        ),
        (
            Ja,
            "青い線を上から下へ散らす。",
            "青い線を下に散らす。",
            Some("上から"),
        ),
        (
            Ja,
            "点状に青い線を中心に置く。",
            "点線の青い線を中心に置く。",
            Some("点状に"),
        ),
        (
            En,
            "scatter blue lines in dots at center.",
            "scatter dotted blue lines at center.",
            Some("dots"),
        ),
        (
            Ja,
            "ちっちゃい青い円を中心に置く。",
            "小さい青い円を中心に置く。",
            Some("ちっちゃい青い"),
        ),
        (
            En,
            "place one tiny blue circle at center.",
            "place one small blue circle at center.",
            Some("tiny"),
        ),
        (
            Ja,
            "円 青い 小さい を中心に置く。",
            "小さい青い円を中心に置く。",
            None,
        ),
        (
            En,
            "place one circle blue small at center.",
            "place one small blue circle at center.",
            None,
        ),
    ];
    for (lang, source, replacement, expected) in cases {
        let output = proposed(lang, source, replacement);
        let phase = serde_json::to_value(&output.snapshot.phase).unwrap();
        assert_eq!(phase["tag"], "awaiting_patch_approval", "{source}: {phase}");
        let event = output
            .events
            .iter()
            .find(|e| e.tag == "visible_patch_proposed")
            .unwrap();
        if let Some(word) = expected {
            let list = phase["unread_words_not_kept"].as_array().unwrap();
            assert_eq!(list.len(), 1, "{source}");
            assert_eq!(list[0]["hole_id"], phase["patch"]["edits"][0]["hole_id"]);
            assert_eq!(list[0]["words"], json!([word]), "{source}");
            assert_eq!(
                event.payload["unread_words_not_kept"],
                phase["unread_words_not_kept"]
            );
        } else {
            assert!(phase.get("unread_words_not_kept").is_none(), "{source}");
            assert!(event.payload.get("unread_words_not_kept").is_none());
        }
    }
}

#[test]
fn i695_old_approval_snapshot_and_digest_remain_usable() {
    let output = proposed(
        inku_ddl::ResolvedInstructionLanguage::En,
        "place one enigmatic blue line at center.",
        "place one blue line at center.",
    );
    let state = output.snapshot;
    let digest = match &state.phase {
        PipelinePhase::AwaitingPatchApproval {
            proposal_digest, ..
        } => proposal_digest.clone(),
        _ => panic!("{:?}", state.phase),
    };
    let mut old = serde_json::to_value(&state).unwrap();
    old["phase"]
        .as_object_mut()
        .unwrap()
        .remove("unread_words_not_kept");
    let mut restored: PipelineSnapshot = serde_json::from_value(old).unwrap();
    restored.snapshot_digest.clear();
    restored.snapshot_digest =
        inku_pipeline::protocol::value_digest("inku.pipeline-snapshot.v1", &restored).unwrap();
    let old_phase = serde_json::to_value(&restored.phase).unwrap();
    assert!(old_phase.get("unread_words_not_kept").is_none());
    assert_eq!(old_phase["proposal_digest"], digest);
    for snapshot in [&state, &restored] {
        let approved = run(
            Some(snapshot),
            &envelope(
                Some(snapshot),
                PipelineInput::ApprovePatch {
                    expected_revision: DecimalU64::new(snapshot.authority.revision()),
                    proposal_digest: digest.clone(),
                },
            ),
        );
        assert!(matches!(
            approved.snapshot.phase,
            PipelinePhase::AwaitingVisibleDdlCommit { .. }
        ));
    }
}
