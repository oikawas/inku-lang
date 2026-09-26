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
    plan.instruction_transforms()[index].apply(point)
}

fn endpoints(plan: &PerformancePlan, index: usize, canvas: Option<CanvasSize>) -> (Point, Point) {
    let (start, end, _, _) = endpoint_geometry(&plan.score.instructions[index], canvas).unwrap();
    (
        plan.instruction_transforms()[index].apply(start),
        plan.instruction_transforms()[index].apply(end),
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

fn filled_contour(svg: &str, occurrence: usize) -> Vec<Point> {
    let class_index = svg
        .match_indices("class=\"solid-base-fill-v1\"")
        .nth(occurrence)
        .expect("paired Arc solid fill")
        .0;
    let prefix = &svg[..class_index];
    let path_start = prefix.rfind(" d=\"").expect("fill path data") + 4;
    let path_end = svg[path_start..class_index]
        .find('"')
        .map(|offset| path_start + offset)
        .expect("fill path terminator");
    let coordinates = svg[path_start..path_end]
        .split_ascii_whitespace()
        .filter_map(|token| token.parse::<f64>().ok())
        .collect::<Vec<_>>();
    assert_eq!(coordinates.len() % 2, 0);
    coordinates
        .chunks_exact(2)
        .map(|pair| Point::new(pair[0], pair[1]))
        .collect()
}

fn assert_simple_filled_contour(points: &[Point]) {
    assert!(points.len() > 4);
    let area = (0..points.len())
        .map(|index| {
            let next = (index + 1) % points.len();
            points[index].x * points[next].y - points[next].x * points[index].y
        })
        .sum::<f64>()
        .abs()
        / 2.0;
    assert!(area > 1.0, "paired Arc contour has no interior: {area}");
    let orientation =
        |a: Point, b: Point, c: Point| (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
    for first in 0..points.len() {
        let first_next = (first + 1) % points.len();
        for second in first + 1..points.len() {
            let second_next = (second + 1) % points.len();
            if first_next == second || second_next == first {
                continue;
            }
            let ab_c = orientation(points[first], points[first_next], points[second]);
            let ab_d = orientation(points[first], points[first_next], points[second_next]);
            let cd_a = orientation(points[second], points[second_next], points[first]);
            let cd_b = orientation(points[second], points[second_next], points[first_next]);
            assert!(
                !(ab_c * ab_d < -1.0e-8 && cd_a * cd_b < -1.0e-8),
                "paired Arc contour crosses between edges {first} and {second}"
            );
        }
    }
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
    assert_eq!(performed.original_instruction_indices(), [0, 1, 2]);
    assert_eq!(performed.instruction_indices(), [0, 1, 2]);
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
    assert_eq!(anchor_only.original_instruction_indices(), [0, 1]);
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
    assert_eq!(omitted.original_instruction_indices(), [0, 1, 2]);
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
    assert_eq!(omitted.original_instruction_indices(), [0, 1, 2, 3]);
    assert_eq!(omitted.instruction_indices(), [0, 1, 2, 3]);
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
    assert_eq!(omitted.original_instruction_indices(), [0, 1]);
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
    assert_eq!(omitted.original_instruction_indices(), [0, 1, 2, 3]);
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
       "angle_start":0,"angle_end":120,
       "relation":{"type":"connected","target_instruction_index":0,
                   "target_path_position":0.25,"position_authority":"named_movable"}},
      {"primitive":"arc","center":[0.3,0.3],"radius":0.07,
       "angle_start":0,"angle_end":120,
       "relation":{"type":"touching","target_instruction_index":1,
                   "position_authority":"named_movable",
                   "touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}},
       "filled":true},
      {"primitive":"arc","center":[0.65,0.3],"radius":0.06,
       "angle_start":0,"angle_end":120,
       "relation":{"type":"connected","target_instruction_index":0,
                   "target_path_position":0.72,"position_authority":"named_movable"}},
      {"primitive":"arc","center":[0.65,0.3],"radius":0.06,
       "angle_start":0,"angle_end":120,
       "relation":{"type":"touching","target_instruction_index":3,
                   "position_authority":"named_movable",
                   "touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}},
       "surface":{"texture":"solid"}}
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
    assert!(performed.execution.is_none(), "{:?}", performed.execution);
    assert_eq!(
        performed
            .performed
            .iter()
            .map(|entry| entry.closed_arc_pair_follower)
            .collect::<Vec<_>>(),
        [None, Some(2), None, Some(4), None]
    );
    let centerline = performed.performed[0]
        .line_centerline
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
            svg_profile: SvgProfile::Display,
            render_seed: Some(71),
            composition_seed: Some(71),
            wild: false,
            error_policy: ScoreErrorPolicy::Stop,
        },
    })
    .unwrap();
    let fills = output
        .svg
        .match_indices("class=\"closed-arc-pair-fill-v1\"")
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    assert_eq!(fills.len(), 2);
    let outlines = output
        .svg
        .match_indices("class=\"contour-stroke-v1")
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    assert_eq!(outlines.len(), 4);
    assert!(fills[0] < outlines[0]);
    assert!(fills[1] < outlines[2]);
    assert_eq!(
        output.svg.matches("class=\"solid-base-fill-v1\"").count(),
        2
    );
    assert_simple_filled_contour(&filled_contour(&output.svg, 0));
    assert_simple_filled_contour(&filled_contour(&output.svg, 1));
}

#[test]
fn interior_path_connections_are_reproducible_and_follow_transformed_line_and_arc_centerlines() {
    let input = score(
        r#"{"version":"0.13.0","instructions":[
      {"primitive":"line","from":[0.15,0.4],"to":[0.85,0.4]},
      {"primitive":"line","from":[0.1,0.2],"to":[0.2,0.2],
       "relation":{"type":"connected","target_instruction_index":0,
                   "target_path_position":"interior","position_authority":"named_movable"}},
      {"primitive":"arc","center":[0.5,0.55],"radius":0.2,
       "angle_start":15,"angle_end":235,
       "variation":{"amplitude":"medium","frequency":"slow","quality":"wave",
                    "dimensions":["position_x","position_y"]}},
      {"primitive":"line","from":[0.2,0.2],"to":[0.3,0.2],
       "relation":{"type":"connected","target_instruction_index":2,
                   "target_path_position":"interior","position_authority":"named_movable"}}
    ],"transform_groups":[
      {"start":0,"end":4,"rotation_degrees":21,"scale_x":1.15,"scale_y":0.75,
       "translate_x":0.04,"translate_y":-0.03}
    ]}"#,
    );
    let performed = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    let repeated = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(performed, repeated);

    let (line_start, line_end) = endpoints(&performed, 0, None);
    let line_connection = start(&performed, 1);
    let line = Point::new(line_end.x - line_start.x, line_end.y - line_start.y);
    let line_offset = Point::new(
        line_connection.x - line_start.x,
        line_connection.y - line_start.y,
    );
    let line_position =
        (line.x * line_offset.x + line.y * line_offset.y) / (line.x * line.x + line.y * line.y);
    assert!((line.x * line_offset.y - line.y * line_offset.x).abs() < 1.0e-9);
    assert!((0.0..1.0).contains(&line_position));

    let arc_connection = start(&performed, 3);
    let arc_centerline = performed.performed[2]
        .line_centerline
        .as_deref()
        .expect("an interior Arc target fixes one rendered centerline");
    assert!(arc_centerline.windows(2).any(|segment| {
        let vector = Point::new(segment[1].x - segment[0].x, segment[1].y - segment[0].y);
        let offset = Point::new(
            arc_connection.x - segment[0].x,
            arc_connection.y - segment[0].y,
        );
        let length_squared = vector.x * vector.x + vector.y * vector.y;
        (vector.x * offset.y - vector.y * offset.x).abs() < 1.0e-9
            && (0.0..=length_squared).contains(&(vector.x * offset.x + vector.y * offset.y))
    }));
    assert_ne!(arc_connection, arc_centerline[0]);
    assert_ne!(arc_connection, *arc_centerline.last().unwrap());
}

#[test]
fn selected_line_and_arc_endpoints_keep_identity_through_outer_reflection_and_rotation() {
    let canvas = CanvasSize::new(1200.0, 800.0);
    let input = score(
        r#"{"version":"0.12.0","instructions":[
          {"primitive":"line","from":[0.2,0.3],"to":[0.65,0.3],
           "variation":{"amplitude":"broad","frequency":"slow","quality":"wave",
                        "dimensions":["position_x","position_y"]}},
          {"primitive":"point","center":[0.4,0.4],"radius":0.01,
           "relation":{"type":"connected","target_instruction_index":0,
                       "target_endpoint":"start","position_authority":"named_movable"}},
          {"primitive":"point","center":[0.4,0.4],"radius":0.01,
           "relation":{"type":"connected","target_instruction_index":0,
                       "target_endpoint":"end","position_authority":"named_movable"}},
          {"primitive":"arc","center":[0.5,0.65],"radius":0.15,
           "angle_start":25,"angle_end":145,"rotation":17},
          {"primitive":"point","center":[0.4,0.4],"radius":0.01,
           "relation":{"type":"connected","target_instruction_index":3,
                       "target_endpoint":"start","position_authority":"named_movable"}},
          {"primitive":"point","center":[0.4,0.4],"radius":0.01,
           "relation":{"type":"connected","target_instruction_index":3,
                       "target_endpoint":"end","position_authority":"named_movable"}}
        ],"transform_groups":[
          {"start":0,"end":6,"rotation_degrees":137,"scale_x":-1.2,"scale_y":0.7}
        ]}"#,
    );
    let performed = resolve_checked_performance(
        PerformanceRequest {
            canvas: Some(canvas),
            ..request(&input)
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .unwrap();
    assert!(performed.execution.is_none(), "{:?}", performed.execution);
    assert_eq!(performed.original_instruction_indices(), [0, 1, 2, 3, 4, 5]);
    let line = performed.performed[0].line_centerline.as_deref().unwrap();
    near_point(endpoints(&performed, 1, Some(canvas)).0, line[0]);
    near_point(
        endpoints(&performed, 2, Some(canvas)).0,
        *line.last().unwrap(),
    );
    let arc = endpoints(&performed, 3, Some(canvas));
    near_point(endpoints(&performed, 4, Some(canvas)).0, arc.0);
    near_point(endpoints(&performed, 5, Some(canvas)).0, arc.1);
    assert!((arc.0.x - arc.1.x).hypot(arc.0.y - arc.1.y) > 0.1);
}

#[test]
fn closed_arc_pair_fill_requires_solid_and_a_successful_checked_touching() {
    let render_svg = |input: Score, error_policy| {
        render(RenderRequest {
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
                error_policy,
            },
        })
        .unwrap()
        .svg
    };
    let wash = score(
        r#"{"version":"0.11.0","instructions":[
      {"primitive":"arc","center":[0.35,0.5],"radius":0.12,"angle_start":0,"angle_end":120},
      {"primitive":"arc","center":[0.65,0.5],"radius":0.12,"angle_start":0,"angle_end":120,
       "surface":{"texture":"wash"},
       "relation":{"type":"touching","target_instruction_index":0,
                   "position_authority":"named_movable",
                   "touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}}}
    ]}"#,
    );
    assert!(!render_svg(wash, ScoreErrorPolicy::Stop).contains("closed-arc-pair-fill-v1"));

    let failed = score(
        r#"{"version":"0.11.0","instructions":[
      {"primitive":"arc","center":[0.25,0.5],"radius":0.12,"angle_start":0,"angle_end":120},
      {"primitive":"arc","center":[0.75,0.5],"radius":0.12,"angle_start":0,"angle_end":120,
       "surface":{"texture":"solid"},
       "relation":{"type":"touching","target_instruction_index":0,
                   "position_authority":"numeric_fixed",
                   "touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}}}
    ]}"#,
    );
    assert!(
        !render_svg(failed, ScoreErrorPolicy::OmitAndContinue).contains("closed-arc-pair-fill-v1")
    );
}
