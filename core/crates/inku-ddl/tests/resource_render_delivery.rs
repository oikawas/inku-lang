//! Focused native SVG delivery check. Run on the Linux rendering lane only.

use std::collections::BTreeMap;

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreLoweringContext, compile_ddl_to_score_with_resources,
};
use inku_render::{
    compat_clip::ClipLimits,
    render::{CompatFillClipPolicy, render_with_resources},
    types::{CanvasSize, RenderOptions, RenderRequest, SvgProfile},
};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
    ScoreExecutionDisposition, ScoreExecutionReason,
};

#[test]
fn resource_fill_reaches_svg_and_local_clip_refusal_preserves_later_drawing() {
    // The original four limits are unchanged; the other fixture bounds are explicit.
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
    let hard = HardResourcePolicy {
        identity: "delivery-fixture.v1".into(),
        budget,
    };
    let operational = OperationalResourceBudget(budget);
    let document = NormalizedDdlDocument::new(
        "fill red point. fill a circle diameter 0.5 at horizontal 0.5 vertical 0.5 with 3 red points. place one blue line at center connected to the previous shape.",
        ResolvedInstructionLanguage::En, vec![],
    ).unwrap();
    let compiled = compile_ddl_to_score_with_resources(
        document,
        &[],
        Some(17),
        MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 128,
            max_nodes_per_invocation: 32,
            max_total_nodes: 64,
        },
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        operational,
    );
    assert!(compiled.failure().is_none(), "{:?}", compiled.failure());
    assert_eq!(compiled.resource_omissions().len(), 1);
    let score = compiled
        .score()
        .expect("later drawing survives resource omission");
    assert_eq!(score.instructions.len(), 2);
    assert_eq!(score.fill_groups[0].logical_count, 3);
    assert_eq!(
        score.instructions[1]
            .relation
            .as_ref()
            .unwrap()
            .target_instruction_index,
        Some(0)
    );
    let bytes = inku_score::canonical_json_bytes(score).unwrap();
    let restored = inku_score::read_saved_score_json(&bytes).unwrap();
    assert_eq!(&restored, score);
    let request = |profile| RenderRequest {
        score: restored.clone(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize {
                width: 256.0,
                height: 256.0,
            },
            canvas_aspect_id: "square".into(),
            svg_profile: profile,
            render_seed: Some(666010),
            composition_seed: Some(17),
            wild: false,
            error_policy: ScoreErrorPolicy::OmitAndContinue,
        },
    };
    let clip = CompatFillClipPolicy {
        tolerance_pixels: 0.1,
        limits: ClipLimits {
            max_nodes: 50_000,
            max_path_elements: 200_000,
            max_flattened_points: 200_000,
            max_work: 10_000_000,
            max_output_vertices: 200_000,
        },
    };
    let display =
        render_with_resources(request(SvgProfile::Display), &hard, operational, clip).unwrap();
    assert!(display.svg.contains("clip-path="));
    assert_eq!(
        display
            .metadata
            .resource_execution
            .as_ref()
            .unwrap()
            .demand
            .primitive_marks,
        4
    );
    assert_eq!(
        display
            .metadata
            .execution
            .as_ref()
            .unwrap()
            .rendered_instruction_indices,
        vec![0, 1]
    );
    let compat =
        render_with_resources(request(SvgProfile::Compat), &hard, operational, clip).unwrap();
    assert!(!compat.svg.contains("clip-path="));
    assert!(!compat.svg.contains("<filter"));
    assert_eq!(
        compat
            .metadata
            .execution
            .as_ref()
            .unwrap()
            .rendered_instruction_indices,
        vec![0, 1]
    );
    let mut constrained = clip;
    constrained.limits.max_nodes = 1;
    let refused =
        render_with_resources(request(SvgProfile::Compat), &hard, operational, constrained)
            .unwrap();
    let execution = refused.metadata.execution.as_ref().unwrap();
    assert_eq!(execution.rendered_instruction_indices, vec![1]);
    let resources = refused.metadata.resource_execution.as_ref().unwrap();
    assert_eq!(resources.demand.primitive_marks, 1);
    assert_eq!(resources.relation_omissions.len(), 1);
    assert!(execution.diagnostics.iter().any(|diagnostic| {
        diagnostic.instruction_index == 0
            && diagnostic.reason == ScoreExecutionReason::FillClipLimitExceeded
            && diagnostic.disposition == ScoreExecutionDisposition::Omitted
    }));
    assert_eq!(inku_score::canonical_json_bytes(&restored).unwrap(), bytes);
}
