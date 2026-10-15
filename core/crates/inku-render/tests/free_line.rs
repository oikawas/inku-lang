//! The free line (I-715, Score 0.21.0) in performance and drawing: its path
//! is built where its mark is drawn, it turns away from the marks drawn
//! before it, and it joins another mark only at its ends.

use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::{PerformancePlan, PerformanceRequest};
use inku_render::render::render;
use inku_render::types::{
    CanvasSize, RenderOptions, RenderRequest, Score, ScoreErrorPolicy, ScoreExecutionReason,
    SvgProfile,
};
use serde_json::{Value, json};

fn svg(value: &Value, seed: i128, wild: bool) -> String {
    render(RenderRequest {
        score: serde_json::from_value(value.clone()).unwrap(),
        options: RenderOptions {
            resolved_color_map: Default::default(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(seed),
            composition_seed: Some(seed),
            wild,
            error_policy: Default::default(),
        },
    })
    .unwrap()
    .svg
}

/// The whole element carrying `id`, to its own end tag: nested elements of
/// the same name are counted, not taken for its end.
fn element<'a>(svg: &'a str, id: &str) -> &'a str {
    let at = svg
        .find(&format!("id=\"{id}\""))
        .unwrap_or_else(|| panic!("{id} drawn"));
    let start = svg[..at].rfind('<').expect("tag start");
    let name_end = start
        + 1
        + svg[start + 1..]
            .find(|character: char| character.is_whitespace() || character == '>')
            .expect("tag name");
    let name = &svg[start + 1..name_end];
    let tag_end = name_end + svg[name_end..].find('>').expect("tag end");
    if svg[..tag_end].ends_with('/') {
        return &svg[start..=tag_end];
    }
    let (open, close) = (format!("<{name}"), format!("</{name}>"));
    let mut depth = 1;
    let mut cursor = tag_end + 1;
    loop {
        let next_open = svg[cursor..].find(&open).map(|offset| cursor + offset);
        let next_close = cursor + svg[cursor..].find(&close).expect("end tag");
        match next_open {
            Some(position) if position < next_close => {
                let end = position + svg[position..].find('>').expect("tag end");
                if !svg[..end].ends_with('/') {
                    depth += 1;
                }
                cursor = end + 1;
            }
            _ => {
                depth -= 1;
                cursor = next_close + close.len();
                if depth == 0 {
                    return &svg[start..cursor];
                }
            }
        }
    }
}

fn free_line(weight: &str) -> Value {
    json!({"primitive": "free_line", "from": [0.225, 0.5], "to": [0.775, 0.5], "weight": weight})
}

fn plan(value: &Value, seed: i128) -> PerformancePlan {
    let score: Score = serde_json::from_value(value.clone()).unwrap();
    score.validate_schema_edition().unwrap();
    resolve_checked_performance(
        PerformanceRequest {
            score: &score,
            performance_seed: Some(seed),
            composition_seed: Some(seed),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .unwrap()
}

fn reasons(plan: &PerformancePlan) -> Vec<(usize, ScoreExecutionReason)> {
    plan.execution
        .as_ref()
        .map(|execution| {
            execution
                .diagnostics
                .iter()
                .map(|diagnostic| (diagnostic.instruction_index, diagnostic.reason))
                .collect()
        })
        .unwrap_or_default()
}

#[test]
fn a_free_line_needs_score_0_21() {
    let mut value = json!({"version": "0.21.0", "instructions": [free_line("pen")]});
    let score: Score = serde_json::from_value(value.clone()).unwrap();
    score.validate_schema_edition().unwrap();
    value["version"] = json!("0.20.0");
    let score: Score = serde_json::from_value(value).unwrap();
    assert_eq!(
        score.validate_schema_edition(),
        Err("free_line requires Score version 0.21.0")
    );
}

#[test]
fn a_free_line_is_drawn_along_its_own_path_and_the_same_way_twice() {
    for (weight, drawn) in [
        ("brush_thin", "contour-stroke-v1"),
        ("pencil", "contour-stroke-v1"),
        ("rotring", "<path"),
    ] {
        let value = json!({"version": "0.21.0", "instructions": [free_line(weight)]});
        let first = svg(&value, 7, false);
        assert_eq!(first, svg(&value, 7, false), "{weight}");
        let mark = element(&first, "mark_000_000_free_line");
        assert!(mark.contains(drawn), "{weight}: {mark}");
        assert!(
            !mark.contains("stroke-engine-v1"),
            "{weight}: a line's stroke"
        );
        assert!(!mark.contains("<line"), "{weight}: a straight line");
        assert_ne!(first, svg(&value, 8, false), "{weight}: another seed");
    }
    let value = json!({"version": "0.21.0", "instructions": [free_line("brush_thin")]});
    assert_ne!(svg(&value, 7, false), svg(&value, 7, true), "wild");
}

#[test]
fn a_free_line_turns_away_from_a_mark_drawn_before_it() {
    let scene = |center: [f64; 2], radius: f64| {
        json!({"version": "0.21.0", "instructions": [
            {"primitive": "circle", "center": center, "radius": radius, "filled": true},
            free_line("brush_thin"),
        ]})
    };
    let near = scene([0.5, 0.42], 0.08);
    let far = scene([0.08, 0.92], 0.02);
    let mut turned = 0;
    for seed in 1..=8 {
        let near_svg = svg(&near, seed, false);
        let far_svg = svg(&far, seed, false);
        turned += usize::from(
            element(&near_svg, "mark_001_000_free_line")
                != element(&far_svg, "mark_001_000_free_line"),
        );
    }
    assert!(turned > 0, "the circle never moved the free line");
}

#[test]
fn a_free_line_takes_a_connection_and_a_touch_and_drops_the_rest_in_a_saved_score() {
    let relation = |kind: &str| json!({"type": kind, "target_instruction_index": 0, "position_authority": "named_movable"});
    let line = json!({"primitive": "line", "from": [0.2, 0.3], "to": [0.6, 0.3]});
    let circle = json!({"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1});
    for (prior, kind, expected) in [
        (
            circle.clone(),
            "resting_on",
            vec![(1, ScoreExecutionReason::UnsupportedJointGeometry)],
        ),
        (
            circle.clone(),
            "inside",
            vec![(1, ScoreExecutionReason::UnsupportedJointGeometry)],
        ),
        (
            circle.clone(),
            "not_touching",
            vec![(1, ScoreExecutionReason::UnsupportedNotTouchingGeometry)],
        ),
        (
            line.clone(),
            "along",
            vec![(1, ScoreExecutionReason::UnsupportedAlongPrimitive)],
        ),
        (
            line.clone(),
            "cutting",
            vec![(1, ScoreExecutionReason::UnsupportedCuttingPrimitive)],
        ),
        (circle.clone(), "connected", vec![]),
        (line.clone(), "connected", vec![]),
    ] {
        let mut current = free_line("pen");
        current["relation"] = relation(kind);
        let value = json!({"version": "0.21.0", "instructions": [prior, current]});
        let plan = plan(&value, 7);
        assert_eq!(reasons(&plan), expected, "{kind}");
        assert!(plan.score.instructions[1].relation.is_none(), "{kind}");
        assert!(
            svg(&value, 7, false).contains("mark_001_000_free_line"),
            "{kind}"
        );
    }
    // A touch: checked metadata with its constraints.
    let mut current = free_line("pen");
    current["relation"] = json!({
        "type": "touching", "target_instruction_index": 0, "position_authority": "named_movable",
        "touching_constraints": {"dimensions_fixed": false, "direction_fixed": false}
    });
    let value = json!({"version": "0.21.0", "instructions": [line.clone(), current]});
    let plan = plan(&value, 7);
    assert!(reasons(&plan).is_empty(), "{:?}", plan.execution);
    let performed = &plan.score.instructions[1];
    for (end, expected) in [(performed.from_, (0.2, 0.3)), (performed.to, (0.6, 0.3))] {
        let end = end.expect("a touched end");
        assert!(
            (end.x - expected.0).abs() < 1.0e-9 && (end.y - expected.1).abs() < 1.0e-9,
            "{end:?} {expected:?}"
        );
    }
    // The free line as the mark referred to.
    let mut circle_after = circle.clone();
    circle_after["relation"] = relation("overlapping");
    let value = json!({"version": "0.21.0", "instructions": [free_line("pen"), circle_after]});
    assert_eq!(
        reasons(&plan_of(&value)),
        [(1, ScoreExecutionReason::UnsupportedJointGeometry)]
    );
    let mut line_after = line.clone();
    line_after["relation"] = relation("connected");
    let value = json!({"version": "0.21.0", "instructions": [free_line("pen"), line_after]});
    let performed = plan_of(&value);
    assert!(reasons(&performed).is_empty(), "{:?}", performed.execution);
    let (end, start) = (
        performed.score.instructions[0].to.unwrap(),
        performed.score.instructions[1].from_.unwrap(),
    );
    assert!((end.x - start.x).abs() < 1.0e-9 && (end.y - start.y).abs() < 1.0e-9);
}

fn plan_of(value: &Value) -> PerformancePlan {
    plan(value, 7)
}

#[test]
fn a_connection_to_the_middle_of_a_free_line_is_refused_by_the_score() {
    let value = json!({"version": "0.21.0", "instructions": [
        free_line("pen"),
        {"primitive": "line", "from": [0.2, 0.3], "to": [0.6, 0.3], "relation": {
            "type": "connected", "target_instruction_index": 0,
            "target_path_position": "interior", "position_authority": "named_movable"
        }},
    ]});
    let score: Score = serde_json::from_value(value).unwrap();
    assert!(score.validate_schema_edition().is_err());
}
