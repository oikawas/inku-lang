use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::{PerformancePlan, PerformanceRequest};
use inku_render::planning::endpoint_geometry;
use inku_render::render::render;
use inku_render::types::{
    CanvasSize, Point, RenderOptions, RenderRequest, Score, ScoreErrorPolicy, ScoreExecutionReason,
    SvgProfile,
};

fn score(json: &str) -> Score {
    serde_json::from_str(json).expect("valid Anchor score")
}

fn request(score: &Score) -> PerformanceRequest<'_> {
    PerformanceRequest {
        score,
        performance_seed: Some(71),
        composition_seed: Some(71),
        canvas: None,
    }
}

fn start(plan: &PerformancePlan, index: usize) -> Point {
    let point = endpoint_geometry(&plan.score.instructions[index], None)
        .unwrap()
        .0;
    plan.instruction_transforms[index].apply(point)
}

fn endpoints(plan: &PerformancePlan, index: usize, canvas: Option<CanvasSize>) -> (Point, Point) {
    let (start, end, _, _) = endpoint_geometry(&plan.score.instructions[index], canvas).unwrap();
    (
        plan.instruction_transforms[index].apply(start),
        plan.instruction_transforms[index].apply(end),
    )
}

fn path_point(points: &[Point], position: f64) -> Point {
    let last = points.len() - 1;
    let scaled = position * last as f64;
    let lower = (scaled.floor() as usize).min(last);
    let upper = (lower + 1).min(last);
    let fraction = scaled - lower as f64;
    Point::new(
        points[lower].x + (points[upper].x - points[lower].x) * fraction,
        points[lower].y + (points[upper].y - points[lower].y) * fraction,
    )
}

fn near_point(actual: Point, expected: Point) {
    near(actual, expected.x, expected.y);
}

fn near(actual: Point, x: f64, y: f64) {
    assert!(
        (actual.x - x).hypot(actual.y - y) < 1.0e-9,
        "{actual:?} != ({x}, {y})"
    );
}

#[test]
fn forward_anchor_and_ordinary_dependent_use_final_position_without_extra_svg() {
    let input = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.2,0.8],"to":[0.3,0.8],
       "relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.4,0.4],"to":[0.6,0.4]}
    ],"anchors":[{"at":{"region":[0.5,0.5,0.5,0.5]}}],
    "transform_groups":[{"start":2,"end":3,"rotation_degrees":90,"anchor_indices":[0]}]}"#,
    );
    let performed = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(performed.original_instruction_indices, [0, 1, 2]);
    assert_eq!(performed.instruction_indices, [0, 1, 2]);
    near(start(&performed, 0), 0.4, 0.4);
    near(start(&performed, 1), 0.5, 0.4);
    assert!(
        performed
            .score
            .instructions
            .iter()
            .all(|instruction| instruction.relation.is_none())
    );
    let repeated = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(performed, repeated);
    let output = render(RenderRequest {
        score: input,
        options: RenderOptions {
            resolved_color_map: Default::default(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(71),
            composition_seed: Some(71),
            wild: false,
            error_policy: ScoreErrorPolicy::Stop,
        },
    })
    .unwrap();
    assert!(output.svg.contains("instruction_000_line"));
    assert!(output.svg.contains("instruction_001_line"));
    assert!(output.svg.contains("instruction_002_line"));
    assert!(!output.svg.contains("instruction_003"));
    assert!(!output.svg.contains("anchor_000"));
}

#[test]
fn local_and_nested_sibling_transforms_use_shape_or_anchor_only_pivots() {
    let local = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}}
    ],"anchors":[{"at":{"region":[0.5,0.5,0.5,0.5]}}],
    "transform_groups":[{"start":0,"end":1,"rotation_degrees":90,"anchor_indices":[0]}]}"#,
    );
    let local = resolve_checked_performance(request(&local), ScoreErrorPolicy::Stop).unwrap();
    near(start(&local, 0), 0.55, 0.45);
    near(start(&local, 1), 0.55, 0.55);

    let empty_siblings = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":1,"position_authority":"named_movable"}}
    ],"anchors":[{"position":[0.2,0.2]},{"position":[0.8,0.8]}],"transform_groups":[
      {"start":2,"end":2,"rotation_degrees":90,"translate_x":0.1,"anchor_indices":[0]},
      {"start":2,"end":2,"rotation_degrees":90,"translate_x":-0.1,"anchor_indices":[1]},
      {"start":2,"end":2,"rotation_degrees":90,"anchor_indices":[0,1]}
    ]}"#,
    );
    let siblings =
        resolve_checked_performance(request(&empty_siblings), ScoreErrorPolicy::Stop).unwrap();
    near(start(&siblings, 0), 0.8, 0.3);
    near(start(&siblings, 1), 0.2, 0.7);

    let nested = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.6,0.2],"to":[0.8,0.2],
       "relation":{"type":"connected","target_anchor_index":1,"position_authority":"named_movable"}}
    ],"anchors":[{"at":{"region":[0.7,0.3,0.7,0.3]}},{"at":{"region":[0.8,0.4,0.8,0.4]}}],
    "transform_groups":[
      {"start":0,"end":1,"rotation_degrees":90},
      {"start":1,"end":2,"rotation_degrees":90,"anchor_indices":[0]},
      {"start":0,"end":2,"rotation_degrees":90,"anchor_indices":[0,1]}
    ]}"#,
    );
    let nested = resolve_checked_performance(request(&nested), ScoreErrorPolicy::Stop).unwrap();
    near(start(&nested, 0), 0.75, 0.45);
    near(start(&nested, 1), 0.85, 0.55);
}

#[test]
fn numeric_conflicts_cycles_and_unsupported_anchor_relations_keep_original_dependents() {
    let pure_anchor =
        score(r#"{"version":"0.6.0","instructions":[],"anchors":[{"position":[0.5,0.5]}]}"#);
    let stopped =
        resolve_checked_performance(request(&pure_anchor), ScoreErrorPolicy::Stop).unwrap_err();
    assert_eq!(stopped.diagnostics.len(), 1);
    assert_eq!(
        stopped.diagnostics[0].reason,
        ScoreExecutionReason::NoDrawableInstructions
    );
    assert_eq!(stopped.diagnostics[0].anchor_index, Some(0));

    let anchor_only = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"point","center":[0.1,0.1],"radius":0.01},
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}}
    ],"anchors":[{"position":[0.9,0.9]}],"transform_groups":[
      {"start":2,"end":2,"rotation_degrees":0,"translate_x":0.5,"anchor_indices":[0]}
    ]}"#,
    );
    let anchor_only =
        resolve_checked_performance(request(&anchor_only), ScoreErrorPolicy::OmitAndContinue)
            .unwrap();
    assert_eq!(anchor_only.original_instruction_indices, [0, 1]);
    let diagnostics = &anchor_only.execution.as_ref().unwrap().diagnostics;
    assert_eq!(
        diagnostics[0].reason,
        ScoreExecutionReason::NumericTransformGroupPositionConflict
    );
    assert_eq!(diagnostics[0].anchor_index, Some(0));
    assert!(diagnostics.iter().any(|value| value.instruction_index == 1
        && value.reason == ScoreExecutionReason::ConnectedReferenceOmitted));

    let numeric = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"point","center":[0.1,0.1],"radius":0.01},
      {"primitive":"line","from":[0.6,0.6],"to":[0.7,0.6],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":1,"position_authority":"named_movable"}}
    ],"anchors":[{"at":{"region":[0.2,0.2,0.2,0.2]}},{"position":[0.7,0.7]}],
    "transform_groups":[{"start":1,"end":2,"rotation_degrees":0,"anchor_indices":[1]}]}"#,
    );
    let stopped = resolve_checked_performance(request(&numeric), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(
        stopped.execution.as_ref().unwrap().diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
    let omitted =
        resolve_checked_performance(request(&numeric), ScoreErrorPolicy::OmitAndContinue).unwrap();
    assert_eq!(omitted.original_instruction_indices, [0, 1, 2]);
    assert_eq!(stopped, omitted);
    let diagnostics = &omitted.execution.as_ref().unwrap().diagnostics;
    assert_eq!(diagnostics.len(), 1);
    near(start(&omitted, 2), 0.7, 0.7);

    let cycle = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":1,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.6,0.6],"to":[0.7,0.6],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"point","center":[0.3,0.3],"radius":0.01},
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}}
    ],"anchors":[{"at":{"region":[0.2,0.2,0.2,0.2]}},{"at":{"region":[0.7,0.7,0.7,0.7]}}],
    "transform_groups":[{"start":0,"end":1,"rotation_degrees":0,"anchor_indices":[0]},
                        {"start":1,"end":2,"rotation_degrees":0,"anchor_indices":[1]}]}"#,
    );
    let stopped = resolve_checked_performance(request(&cycle), ScoreErrorPolicy::Stop).unwrap();
    assert!(
        stopped
            .execution
            .as_ref()
            .unwrap()
            .diagnostics
            .iter()
            .all(|value| value.reason == ScoreExecutionReason::CyclicConnectedDependency)
    );
    let omitted =
        resolve_checked_performance(request(&cycle), ScoreErrorPolicy::OmitAndContinue).unwrap();
    assert_eq!(omitted.original_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(omitted.instruction_indices, [0, 1, 2, 3]);
    assert_eq!(stopped, omitted);
    near(start(&omitted, 3), 0.2, 0.2);
    assert!(
        omitted
            .execution
            .unwrap()
            .diagnostics
            .iter()
            .all(|value| value.instruction_index < 2
                && value.reason == ScoreExecutionReason::CyclicConnectedDependency)
    );

    let unsupported = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"point","center":[0.1,0.1],"radius":0.01},
      {"primitive":"line","from":[0.6,0.6],"to":[0.7,0.6],
       "relation":{"type":"along","target_anchor_index":0}}
    ],"anchors":[{"position":[0.2,0.2]}]}"#,
    );
    let omitted =
        resolve_checked_performance(request(&unsupported), ScoreErrorPolicy::OmitAndContinue)
            .unwrap();
    assert_eq!(omitted.original_instruction_indices, [0, 1]);
    assert_eq!(
        omitted.execution.unwrap().diagnostics[0].reason,
        ScoreExecutionReason::UnsupportedAnchorRelation
    );
}

#[test]
fn group_connections_require_one_compatible_translation() {
    let mut input = score(
        r#"{"version":"0.6.0","instructions":[
      {"primitive":"line","from":[0.4,0.4],"to":[0.5,0.4],
       "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.4,0.4],"to":[0.4,0.5],
       "relation":{"type":"connected","target_anchor_index":1,"position_authority":"named_movable"}},
      {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],
       "relation":{"type":"connected","target_anchor_index":2,"position_authority":"named_movable"}},
      {"primitive":"point","center":[0.8,0.8],"radius":0.01}
    ],"anchors":[{"position":[0.2,0.2]},{"position":[0.2,0.2]},
                  {"at":{"region":[0.5,0.5,0.5,0.5]}}],
    "transform_groups":[{"start":0,"end":2,"rotation_degrees":0,"anchor_indices":[2]}]}"#,
    );
    let performed = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    near(start(&performed, 0), 0.2, 0.2);
    near(start(&performed, 1), 0.2, 0.2);
    near(start(&performed, 2), 0.3, 0.3);
    input.anchors[1].position = Some(Point::new(0.3, 0.2));
    let stopped = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(
        stopped.execution.as_ref().unwrap().diagnostics[0].reason,
        ScoreExecutionReason::ConflictingRelationConstraints
    );
    let omitted =
        resolve_checked_performance(request(&input), ScoreErrorPolicy::OmitAndContinue).unwrap();
    assert_eq!(omitted.original_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(stopped, omitted);
    near(start(&omitted, 0), 0.4, 0.4);
    near(start(&omitted, 2), 0.5, 0.5);
    assert!(
        omitted
            .execution
            .unwrap()
            .diagnostics
            .iter()
            .all(|value| value.instruction_index < 2
                && value.reason == ScoreExecutionReason::ConflictingRelationConstraints)
    );
}

#[test]
fn path_connected_closed_leaves_follow_one_varied_branch_through_outer_affine() {
    let canvas = CanvasSize::new(1200.0, 800.0);
    let input = score(
        r#"{"version":"0.11.0","instructions":[
      {"primitive":"line","from":[0.18,0.5],"to":[0.82,0.5],
       "variation":{"amplitude":"broad","frequency":"slow","quality":"wave",
                    "dimensions":["position_x","position_y"]}},
      {"primitive":"arc","center":[0.3,0.3],"radius":0.07,
       "angle_start":0,"angle_end":180,
       "relation":{"type":"connected","target_instruction_index":0,
                   "target_path_position":0.25,"position_authority":"named_movable"}},
      {"primitive":"arc","center":[0.3,0.3],"radius":0.07,
       "angle_start":0,"angle_end":180,
       "relation":{"type":"touching","target_instruction_index":1,
                   "position_authority":"named_movable",
                   "touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}}},
      {"primitive":"arc","center":[0.65,0.3],"radius":0.06,
       "angle_start":0,"angle_end":180,
       "relation":{"type":"connected","target_instruction_index":0,
                   "target_path_position":0.72,"position_authority":"named_movable"}},
      {"primitive":"arc","center":[0.65,0.3],"radius":0.06,
       "angle_start":0,"angle_end":180,
       "relation":{"type":"touching","target_instruction_index":3,
                   "position_authority":"named_movable",
                   "touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}}}
    ],"transform_groups":[
      {"start":1,"end":3,"rotation_degrees":35},
      {"start":3,"end":5,"rotation_degrees":-28},
      {"start":0,"end":5,"rotation_degrees":27,"scale_x":1.35,"scale_y":0.68}
    ]}"#,
    );
    let performed = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(71),
            composition_seed: Some(71),
            canvas: Some(canvas),
        },
        ScoreErrorPolicy::Stop,
    )
    .unwrap();
    assert!(performed.execution.is_none());
    let centerline = performed.line_centerlines[0]
        .as_deref()
        .expect("the targeted varied branch fixes one performed centerline");
    assert!(centerline.len() > 2);
    let chord = Point::new(
        centerline.last().unwrap().x - centerline[0].x,
        centerline.last().unwrap().y - centerline[0].y,
    );
    assert!(centerline[1..centerline.len() - 1].iter().any(|point| {
        let offset = Point::new(point.x - centerline[0].x, point.y - centerline[0].y);
        (chord.x * offset.y - chord.y * offset.x).abs() > 1.0e-9
    }));

    let first = endpoints(&performed, 1, Some(canvas));
    let first_closure = endpoints(&performed, 2, Some(canvas));
    near_point(first.0, path_point(centerline, 0.25));
    near_point(first.0, first_closure.0);
    near_point(first.1, first_closure.1);

    let second = endpoints(&performed, 3, Some(canvas));
    let second_closure = endpoints(&performed, 4, Some(canvas));
    near_point(second.0, path_point(centerline, 0.72));
    near_point(second.0, second_closure.0);
    near_point(second.1, second_closure.1);

    let output = render(RenderRequest {
        score: input,
        options: RenderOptions {
            resolved_color_map: Default::default(),
            catalog_id: None,
            canvas,
            canvas_aspect_id: "landscape".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(71),
            composition_seed: Some(71),
            wild: false,
            error_policy: ScoreErrorPolicy::Stop,
        },
    })
    .unwrap();
    assert!(output.svg.contains("instruction_000_line"));
    assert!(output.svg.contains("instruction_004_arc"));
}
