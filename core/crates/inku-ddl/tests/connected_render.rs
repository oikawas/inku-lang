use std::collections::BTreeMap;

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score,
    map_compiler_render_execution,
};
use inku_render::render::render;
use inku_render::types::{CanvasSize, Color, RenderOptions, RenderRequest, SvgProfile};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

#[test]
fn actual_compiler_score_reaches_checked_connected_render_and_exact_owner_join() {
    let source = concat!(
        "place one red line at center. ",
        "place one blue arc at center connected to the previous shape."
    );
    let execution = compile_ddl_to_score(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap(),
        &[],
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::Stop,
    );
    assert_eq!(execution.outcome(), ScoreLoweringOutcome::Complete);
    let score = execution.score().expect("actual compiler Score").clone();
    let output = render(RenderRequest {
        score: score.clone(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1200.0, 700.0),
            canvas_aspect_id: "wide".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(23),
            composition_seed: Some(23),
            wild: false,
            error_policy: ScoreErrorPolicy::Stop,
        },
    })
    .expect("Connected compiler Score renders");

    assert!(output.svg.contains("instruction_000_line_red"));
    assert!(output.svg.contains("instruction_001_arc_blue"));
    assert!(output.metadata.execution.is_none());
    let joined =
        map_compiler_render_execution(&execution, &score, output.metadata.execution.as_ref())
            .expect("renderer result joins to the exact compilation owners");
    assert_eq!(joined.rendered_origins, execution.instruction_origins());
}
