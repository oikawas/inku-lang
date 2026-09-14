use inku_render::determinism::instruction_seed;
use inku_render::render::render;
use inku_render::types::{
    CanvasSize, InkSpread, Instruction, RenderOptions, RenderRequest, Score, SvgProfile,
};

fn render_svg(json: &str) -> String {
    render_svg_with_profile(json, SvgProfile::Display)
}

fn render_svg_with_profile(json: &str, profile: SvgProfile) -> String {
    let score: Score = serde_json::from_str(json).unwrap();
    render(RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: Default::default(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: profile,
            render_seed: Some(2718),
            composition_seed: Some(2718),
            wild: false,
            error_policy: Default::default(),
        },
    })
    .unwrap()
    .svg
}

#[test]
fn ink_spread_reaches_open_and_closed_marks_and_coexists_with_other_effects() {
    let mut seeded: Instruction = serde_json::from_str(
        r#"{"primitive":"line","from":[0.1,0.15],"to":[0.9,0.15],
             "variation":{"quality":"wave","dimensions":["position_y"]}}"#,
    )
    .unwrap();
    let base_seed = instruction_seed(&seeded, Some(2718));
    seeded.ink_spread = Some(InkSpread::Bleed);
    assert_eq!(instruction_seed(&seeded, Some(2718)), base_seed);

    let svg = render_svg(
        r#"{"version":"0.12.0","instructions":[
          {"primitive":"line","from":[0.1,0.15],"to":[0.9,0.15],
           "ink_spread":"bleed",
           "variation":{"quality":"wave","dimensions":["position_y"]}},
          {"primitive":"arc","center":[0.25,0.42],"radius":0.12,
           "angle_start":15,"angle_end":165,"ink_spread":"bleed"},
          {"primitive":"circle","center":[0.72,0.42],"radius":0.13,
           "filled":true,"ink_spread":"bleed",
           "surface":{"texture":"stipple"}}
        ]}"#,
    );

    assert_eq!(svg.matches("class=\"ink-spread-v1\"").count(), 3);
    assert_eq!(svg.matches("result=\"inkSpreadOuter\"").count(), 3);
    assert!(svg.contains("surface_002_000_stipple"));
    assert!(svg.contains("stroke-engine-v1"));
}

#[test]
fn closed_arc_pair_gets_one_outer_spread_and_absent_field_adds_nothing() {
    let spread = render_svg(
        r#"{"version":"0.12.0","instructions":[
          {"primitive":"arc","center":[0.5,0.47],"radius":0.0833,
           "angle_start":-143.13,"angle_end":-36.87,"color":"green"},
          {"primitive":"arc","center":[0.5,0.53],"radius":0.0833,
           "angle_start":143.13,"angle_end":36.87,"color":"green",
           "filled":true,"ink_spread":"bleed",
           "relation":{"type":"touching","target_instruction_index":0,
                       "position_authority":"named_movable",
                       "touching_constraints":{"dimensions_fixed":true,
                                                "direction_fixed":false}}}
        ]}"#,
    );
    assert!(spread.contains("class=\"closed-arc-pair-fill-v1\""));
    assert_eq!(spread.matches("class=\"ink-spread-v1\"").count(), 1);

    let legacy = render_svg(
        r#"{"instructions":[{"primitive":"line","from":[0.1,0.5],
                                                "to":[0.9,0.5]}]}"#,
    );
    assert!(!legacy.contains("ink-spread"));
    assert!(!legacy.contains("inkSpread"));
}

#[test]
fn compat_keeps_the_mark_and_reports_omitted_ink_spread() {
    let json = r#"{"version":"0.12.0","instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"ink_spread":"bleed"}
    ]}"#;
    let score: Score = serde_json::from_str(json).unwrap();
    assert!(
        inku_render::render::build_render_metadata(&score, SvgProfile::Compat).texture_degraded
    );
    let svg = render_svg_with_profile(json, SvgProfile::Compat);
    assert!(svg.contains("<path"));
    assert!(!svg.contains("<filter"));
    assert!(!svg.contains("ink-spread"));
}
