use inku_render::checked_performance::resolve_checked_performance;
use inku_render::cloudform::{CloudformRequest, generate_cloudform_contour};
use inku_render::performance::{PerformanceRequest, resolve_performance};
use inku_render::planning::{endpoint_geometry, instruction_anchor_on_canvas};
use inku_render::types::Point;
use inku_render::types::{
    CanvasSize, Score, ScoreErrorPolicy, ScoreExecutionDisposition, ScoreExecutionReason,
};

fn score(json: &str) -> Score {
    serde_json::from_str(json).unwrap()
}

#[test]
fn affine_groups_scale_geometry_spacing_and_compose_in_physical_order() {
    let input = score(
        r#"{"version":"0.5.0","instructions":[
      {"primitive":"circle","center":[0.3,0.5],"radius":0.05},
      {"primitive":"circle","center":[0.6,0.5],"radius":0.05}
    ],"transform_groups":[{"start":0,"end":2,"rotation_degrees":90,
      "scale_x":1.5,"scale_y":0.5,"translate_x":0.1,"translate_y":-0.1}]}"#,
    );
    let canvas = CanvasSize::new(2000.0, 1000.0);
    let request = |score| PerformanceRequest {
        score,
        performance_seed: Some(71),
        composition_seed: Some(71),
        canvas: Some(canvas),
    };
    let result = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(
        result.score.instructions, input.instructions,
        "primitive identity and pre-transform dimensions stay intact"
    );
    let first = result.instruction_transforms()[0].apply(Point::new(0.6, 0.5));
    let second = result.instruction_transforms()[1].apply(Point::new(1.2, 0.5));
    assert!((first.x - 1.1).abs() < 1e-9 && (first.y + 0.05).abs() < 1e-9);
    assert!((second.x - first.x).abs() < 1e-9 && (second.y - first.y - 0.9).abs() < 1e-9);
    let mut fixed = input.clone();
    fixed.transform_groups[0].fixed_position_indices = vec![0];
    assert_eq!(
        resolve_checked_performance(request(&fixed), ScoreErrorPolicy::Stop)
            .unwrap_err()
            .diagnostics[0]
            .reason,
        ScoreExecutionReason::NumericTransformGroupPositionConflict
    );

    let nested = score(
        r#"{"version":"0.5.0","instructions":[
      {"primitive":"ellipse","center":[0.5,0.5],"size":[0.2,0.1]}
    ],"transform_groups":[
      {"start":0,"end":1,"rotation_degrees":45},
      {"start":0,"end":1,"rotation_degrees":0,"scale_x":2,"scale_y":0.5}
    ]}"#,
    );
    let nested = resolve_checked_performance(request(&nested), ScoreErrorPolicy::Stop).unwrap();
    let transform = nested.instruction_transforms()[0];
    let diagonal = 0.5_f64.sqrt();
    assert!((transform.a - 2.0 * diagonal).abs() < 1e-9);
    assert!((transform.b - 0.5 * diagonal).abs() < 1e-9);
    assert!((transform.c + 2.0 * diagonal).abs() < 1e-9);
    assert!((transform.d - 0.5 * diagonal).abs() < 1e-9);
    assert_eq!(
        nested.score.instructions[0].primitive,
        inku_render::types::Primitive::Ellipse
    );
}

#[test]
fn affine_groups_connect_whole_geometry_and_keep_fixed_omission_indices() {
    let input = score(
        r#"{"version":"0.5.0","instructions":[
      {"primitive":"line","from":[0.1,0.1],"to":[0.1,0.3]},
      {"primitive":"line","from":[0.3,0.5],"to":[0.4,0.5],
        "relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}},
      {"primitive":"point","center":[0.6,0.5],"radius":0.02},
      {"primitive":"line","from":[0.7,0.7],"to":[0.8,0.7],
        "relation":{"type":"connected","target_instruction_index":2,"position_authority":"named_movable"}}
    ],"transform_groups":[{"start":1,"end":3,"rotation_degrees":90,
      "scale_x":2,"scale_y":0.5,"translate_x":0.1}]}"#,
    );
    let request = |score| PerformanceRequest {
        score,
        performance_seed: Some(71),
        composition_seed: Some(71),
        canvas: None,
    };
    let result = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop).unwrap();
    let start = result.instruction_transforms()[1].apply(Point::new(0.3, 0.5));
    let end = result.instruction_transforms()[1].apply(Point::new(0.4, 0.5));
    let point = result.instruction_transforms()[2].apply(Point::new(0.6, 0.5));
    assert!((start.x - 0.1).abs() < 1e-9 && (start.y - 0.3).abs() < 1e-9);
    assert!((end.x - start.x).abs() < 1e-9 && (end.y - start.y - 0.2).abs() < 1e-9);
    assert!((point.y - start.y - 0.6).abs() < 1e-9);
    let follow_start = endpoint_geometry(&result.score.instructions[3], None)
        .unwrap()
        .0;
    assert!((follow_start.x - point.x).hypot(follow_start.y - point.y) < 1e-9);
    assert_eq!(result.instruction_transforms().len(), 4);
    let mut legacy = input.clone();
    let relation = legacy.instructions[3].relation.as_mut().unwrap();
    relation.kind = inku_render::types::RelationType::NotTouching;
    relation.target_instruction_index = None;
    relation.position_authority = None;
    // A legacy not-touching relation against a transformed group member is
    // resolved against that member's transformed bounds, without omission.
    let legacy_plan =
        resolve_checked_performance(request(&legacy), ScoreErrorPolicy::Stop).unwrap();
    assert!(legacy_plan.execution.is_none());
    assert_eq!(legacy_plan.original_instruction_indices(), vec![0, 1, 2, 3]);
    assert!(legacy_plan.score.instructions[3].relation.is_none());
    let mut fixed = input.clone();
    fixed.transform_groups[0].fixed_position_indices = vec![2];
    let continued =
        resolve_checked_performance(request(&fixed), ScoreErrorPolicy::OmitAndContinue).unwrap();
    assert_eq!(continued.original_instruction_indices(), vec![0, 1, 2, 3]);
    assert_eq!(continued.instruction_transforms().len(), 4);
    let reasons = continued
        .execution
        .unwrap()
        .diagnostics
        .into_iter()
        .map(|d| d.reason)
        .collect::<Vec<_>>();
    assert_eq!(
        reasons,
        vec![ScoreExecutionReason::NumericConnectedPositionConflict]
    );
}

#[test]
fn checked_touching_preserves_numeric_final_bounds_and_never_drops_partial_metadata() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"arc","center":[0.5,-0.07],"position":[0.5,0.03],"radius":0.2,"angle_start":210,"angle_end":330},
        {"primitive":"arc","center":[0.5,-0.07],"position":[0.5,0.03],"radius":0.2,"angle_start":210,"angle_end":330,
         "relation":{"type":"touching","target_instruction_index":0,"position_authority":"numeric_fixed","touching_constraints":{"dimensions_fixed":true,"direction_fixed":false}}}
    ]}"#,
    );
    let request = |score| PerformanceRequest {
        score,
        composition_seed: Some(23),
        performance_seed: Some(23),
        canvas: None,
    };
    let own_bounds = inku_render::planning::instruction_bounds(&input.instructions[1]).unwrap();
    assert!(own_bounds.min.y >= 0.0);
    let stopped = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop)
        .unwrap()
        .execution
        .unwrap();
    assert_eq!(
        stopped.diagnostics[0].reason,
        ScoreExecutionReason::NumericTouchingBoundsConflict
    );
    let continued =
        resolve_checked_performance(request(&input), ScoreErrorPolicy::OmitAndContinue).unwrap();
    assert_eq!(continued.original_instruction_indices(), [0, 1]);
    let mut partial = input.clone();
    partial.instructions[1]
        .relation
        .as_mut()
        .unwrap()
        .touching_constraints = None;
    assert_eq!(
        resolve_checked_performance(request(&partial), ScoreErrorPolicy::Stop)
            .unwrap()
            .execution
            .unwrap()
            .diagnostics[0]
            .reason,
        ScoreExecutionReason::MissingTouchingConstraints
    );
    let mut legacy = input.clone();
    let relation = legacy.instructions[1].relation.as_mut().unwrap();
    relation.target_instruction_index = None;
    relation.position_authority = None;
    relation.touching_constraints = None;
    assert_eq!(
        resolve_checked_performance(request(&legacy), ScoreErrorPolicy::Stop)
            .unwrap()
            .score,
        resolve_performance(request(&legacy)).score
    );
}

#[test]
fn absent_performance_seed_preserves_unresolved_fields() {
    let input = score(
        r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,
        "at":{"region":[0.1,0.1,0.3,0.3]},"relation":{"type":"along"}}]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: None,
        composition_seed: None,
        canvas: None,
    });
    assert!(result.score.instructions[0].at.is_some());
    assert!(result.score.instructions[0].relation.is_some());
}

#[test]
fn typed_along_derives_only_an_omitted_line_direction_and_preserves_fixed_position() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.15,0.3],"to":[0.85,0.5]},
        {"primitive":"line","from":[0.35,0.7],"to":[0.55,0.7],
         "relation":{"type":"along","target_instruction_index":0,"position_authority":"named_movable"}}
        ]}"#,
    );
    let result = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(23),
            composition_seed: Some(23),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("typed Along lines perform");
    let prior = endpoint_geometry(&result.score.instructions[0], None).unwrap();
    let along = endpoint_geometry(&result.score.instructions[1], None).unwrap();
    let original_along = endpoint_geometry(&input.instructions[1], None).unwrap();
    let prior_direction = (prior.1.x - prior.0.x, prior.1.y - prior.0.y);
    let along_direction = (along.1.x - along.0.x, along.1.y - along.0.y);
    assert!(
        (prior_direction.0 * along_direction.1 - prior_direction.1 * along_direction.0).abs()
            < 1.0e-9
    );
    assert!(
        ((along.1.x - along.0.x).hypot(along.1.y - along.0.y)
            - (original_along.1.x - original_along.0.x)
                .hypot(original_along.1.y - original_along.0.y))
        .abs()
            < 1.0e-9
    );

    let fixed = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"line","from":[0.4,0.58],"to":[0.6,0.58],
         "relation":{"type":"along","target_instruction_index":0,"position_authority":"numeric_fixed"}}
        ]}"#,
    );
    let fixed = resolve_checked_performance(
        PerformanceRequest {
            score: &fixed,
            performance_seed: Some(23),
            composition_seed: Some(23),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("fixed Along within its band performs");
    let fixed_prior = endpoint_geometry(&fixed.score.instructions[0], None).unwrap();
    let fixed_line = endpoint_geometry(&fixed.score.instructions[1], None).unwrap();
    let fixed_direction = (
        fixed_line.1.x - fixed_line.0.x,
        fixed_line.1.y - fixed_line.0.y,
    );
    let fixed_prior_direction = (
        fixed_prior.1.x - fixed_prior.0.x,
        fixed_prior.1.y - fixed_prior.0.y,
    );
    assert!(
        (fixed_prior_direction.0 * fixed_direction.1 - fixed_prior_direction.1 * fixed_direction.0)
            .abs()
            < 1.0e-9
    );
    let fixed_center = (
        (fixed_line.0.x + fixed_line.1.x) / 2.0,
        (fixed_line.0.y + fixed_line.1.y) / 2.0,
    );
    assert!((fixed_center.0 - 0.5).abs() < 1.0e-9);
    assert!((fixed_center.1 - 0.58).abs() < 1.0e-9);

    let explicit = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"line","from":[0.4,0.2],"to":[0.6,0.2],"rotation":90,
         "relation":{"type":"along","target_instruction_index":0,"position_authority":"named_movable"}}
        ]}"#,
    );
    let explicit = resolve_checked_performance(
        PerformanceRequest {
            score: &explicit,
            performance_seed: Some(23),
            composition_seed: Some(23),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("explicit Along direction performs without parallelization");
    let explicit_line = endpoint_geometry(&explicit.score.instructions[1], None).unwrap();
    assert_eq!(explicit.score.instructions[1].rotation, Some(90.0));
    assert!((explicit_line.1.x - explicit_line.0.x).abs() < 1.0e-9);

    let edge = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.0,0.1],"to":[0.01,0.1]},
        {"primitive":"line","from":[0.4,0.7],"to":[0.8,0.7],
         "relation":{"type":"along","target_instruction_index":0,"position_authority":"named_movable"}}
        ]}"#,
    );
    let edge_original = endpoint_geometry(&edge.instructions[1], None).unwrap();
    let edge = resolve_checked_performance(
        PerformanceRequest {
            score: &edge,
            performance_seed: Some(23),
            composition_seed: Some(23),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("named Along keeps its line length at the edge");
    let edge_line = endpoint_geometry(&edge.score.instructions[1], None).unwrap();
    assert!(
        ((edge_line.1.x - edge_line.0.x).hypot(edge_line.1.y - edge_line.0.y)
            - (edge_original.1.x - edge_original.0.x).hypot(edge_original.1.y - edge_original.0.y))
        .abs()
            < 1.0e-9
    );

    let fixed_outside = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.1],"to":[0.9,0.1]},
        {"primitive":"line","from":[0.01,0.02],"to":[0.01,0.18],
         "relation":{"type":"along","target_instruction_index":0,"position_authority":"numeric_fixed"}}
        ]}"#,
    );
    let fixed_outside = resolve_checked_performance(
        PerformanceRequest {
            score: &fixed_outside,
            performance_seed: Some(23),
            composition_seed: Some(23),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("relation failure preserves geometry")
    .execution
    .expect("relation diagnostic");
    assert_eq!(
        fixed_outside.diagnostics[0].reason,
        ScoreExecutionReason::NumericAlongPositionConflict
    );
}

#[test]
fn typed_cutting_rejects_an_explicit_parallel_direction() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"line","from":[0.4,0.2],"to":[0.6,0.2],"rotation":0,
         "relation":{"type":"cutting","target_instruction_index":0,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.4,0.7],"to":[0.6,0.7],
         "relation":{"type":"along","target_instruction_index":1,"position_authority":"named_movable"}},
        {"primitive":"point","center":[0.8,0.8],"radius":0.006}
        ]}"#,
    );
    let stopped = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(29),
            composition_seed: Some(29),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("relation failure preserves geometry")
    .execution
    .expect("relation diagnostic");
    assert_eq!(
        stopped.diagnostics[0].reason,
        ScoreExecutionReason::CuttingDirectionConflict
    );
    let fixed_collinear = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"line","from":[0.4,0.5],"to":[0.6,0.5],"rotation":0,
         "relation":{"type":"cutting","target_instruction_index":0,"position_authority":"numeric_fixed"}}
        ]}"#,
    );
    let fixed_collinear = resolve_checked_performance(
        PerformanceRequest {
            score: &fixed_collinear,
            performance_seed: Some(29),
            composition_seed: Some(29),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("relation failure preserves geometry")
    .execution
    .expect("relation diagnostic");
    assert_eq!(
        fixed_collinear.diagnostics[0].reason,
        ScoreExecutionReason::CuttingDirectionConflict
    );
    let continued = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(29),
            composition_seed: Some(29),
            canvas: None,
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("independent instruction survives typed relation omissions");
    assert_eq!(continued.original_instruction_indices(), [0, 1, 2, 3]);
    let execution = continued
        .execution
        .expect("typed omissions remain recorded");
    assert_eq!(execution.rendered_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(
        execution
            .diagnostics
            .iter()
            .map(|diagnostic| diagnostic.reason)
            .collect::<Vec<_>>(),
        [ScoreExecutionReason::CuttingDirectionConflict]
    );
}

#[test]
fn typed_cutting_keeps_line_length_while_legacy_cutting_keeps_its_raw_recipe() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"line","from":[0.4,0.2],"to":[0.6,0.2],
         "relation":{"type":"cutting","target_instruction_index":0,"position_authority":"named_movable"}}
        ]}"#,
    );
    let original = endpoint_geometry(&input.instructions[1], None).unwrap();
    let original_length = (original.1.x - original.0.x).hypot(original.1.y - original.0.y);
    let result = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(29),
            composition_seed: Some(29),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("typed Cutting performs");
    let cut = endpoint_geometry(&result.score.instructions[1], None).unwrap();
    let cut_length = (cut.1.x - cut.0.x).hypot(cut.1.y - cut.0.y);
    assert!((cut_length - original_length).abs() < 1.0e-9);
    assert!(
        (cut.0.y - 0.5) * (cut.1.y - 0.5) <= 1.0e-9,
        "typed Cutting crosses the prior line"
    );

    let mut legacy = input.clone();
    let relation = legacy.instructions[1].relation.as_mut().unwrap();
    relation.target_instruction_index = None;
    relation.position_authority = None;
    assert_eq!(
        resolve_checked_performance(
            PerformanceRequest {
                score: &legacy,
                performance_seed: Some(29),
                composition_seed: Some(29),
                canvas: None,
            },
            ScoreErrorPolicy::Stop,
        )
        .expect("metadata-free Cutting remains legacy")
        .score,
        resolve_performance(PerformanceRequest {
            score: &legacy,
            performance_seed: Some(29),
            composition_seed: Some(29),
            canvas: None,
        })
        .score
    );
}

#[test]
fn performance_resolves_regions_then_relations_in_sequence() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"circle","center":[0.5,0.5],"radius":0.05,
         "at":{"region":[0.2,0.2,0.4,0.4]},"relation":{"type":"along"}}
        ]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: Some(431),
        composition_seed: Some(17),
        canvas: Some(CanvasSize::new(1000.0, 500.0)),
    });
    assert!(result.warnings.is_empty());
    assert!(result.score.instructions[1].at.is_none());
    assert!(result.score.instructions[1].relation.is_none());
}

#[test]
fn composite_arrangement_copies_the_ordered_instruction_unit() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"circle","center":[0.4,0.5],"radius":0.08,"weight":"pencil",
         "arrangement":{"count":3,"group_size":2,"layout":"horizontal"}},
        {"primitive":"line","from":[0.35,0.5],"to":[0.45,0.5],"weight":"pencil"}
        ]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: None,
        composition_seed: Some(17),
        canvas: None,
    });
    assert_eq!(result.score.instructions.len(), 6);
    assert!(
        result
            .score
            .instructions
            .iter()
            .all(|instruction| instruction.arrangement.is_none())
    );
}

#[test]
fn composite_square_members_keep_their_physical_offset_on_a_wide_canvas() {
    let canvas = CanvasSize::new(1_000.0, 500.0);
    let input = score(
        r#"{"instructions":[
        {"primitive":"square","position":[0.35,0.4],"size":[0.2,0.2],
         "arrangement":{"count":2,"group_size":2,"layout":"horizontal"}},
        {"primitive":"circle","center":[0.45,0.5],"radius":0.03}
        ]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: None,
        composition_seed: Some(17),
        canvas: Some(canvas),
    });
    assert_eq!(result.score.instructions.len(), 4);
    for pair in result.score.instructions.chunks_exact(2) {
        let square = &pair[0];
        let circle = &pair[1];
        let position = square.position.unwrap();
        let size = square.size.unwrap();
        let square_center_x = position.x * canvas.width + size.x * canvas.unit() / 2.0;
        let square_center_y = position.y * canvas.height + size.y * canvas.unit() / 2.0;
        let circle_center = circle.center.unwrap();
        let offset_x = circle_center.x * canvas.width - square_center_x;
        let offset_y = circle_center.y * canvas.height - square_center_y;
        let physical_offset = offset_x.hypot(offset_y);
        assert!(
            (physical_offset - 50.0).abs() < 1.0e-5,
            "physical offset was {physical_offset}"
        );
    }
}

#[test]
fn connected_elsewhere_preserves_legacy_composite_member_expansion_and_owner_indices() {
    let canvas = CanvasSize::new(1_000.0, 500.0);
    let composite = score(
        r#"{"instructions":[
        {"primitive":"square","position":[0.35,0.4],"size":[0.2,0.2],"weight":"pencil",
         "arrangement":{"count":2,"group_size":2,"layout":"radial","center":[0.5,0.5],
                        "radius":0.25,"color_cycle":["blue","red"]}},
        {"primitive":"circle","center":[0.45,0.5],"radius":0.03,"weight":"pencil"}
        ]}"#,
    );
    let legacy = resolve_performance(PerformanceRequest {
        score: &composite,
        performance_seed: Some(41),
        composition_seed: Some(17),
        canvas: Some(canvas),
    });
    assert_eq!(legacy.score.instructions.len(), 4);

    let mut connected_input = composite;
    connected_input.instructions.extend(
        score(
            r#"{"instructions":[
            {"primitive":"line","from":[0.1,0.8],"to":[0.3,0.8]},
            {"primitive":"line","from":[0.6,0.8],"to":[0.8,0.8],
             "relation":{"type":"connected","target_instruction_index":2,
                         "position_authority":"named_movable"}}
            ]}"#,
        )
        .instructions,
    );
    let checked = resolve_checked_performance(
        PerformanceRequest {
            score: &connected_input,
            performance_seed: Some(41),
            composition_seed: Some(17),
            canvas: Some(canvas),
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("Connected outside the composite remains performable");

    assert_eq!(&checked.score.instructions[..4], &legacy.score.instructions);
    assert_eq!(checked.instruction_indices(), [0, 1, 2, 3, 4, 5]);
    assert_eq!(checked.original_instruction_indices(), [0, 1, 0, 1, 2, 3]);

    let mut continued_input = connected_input;
    continued_input.instructions[3]
        .relation
        .as_mut()
        .unwrap()
        .position_authority = Some(inku_render::types::ConnectedPositionAuthority::NumericFixed);
    continued_input.instructions.extend(
        score(r#"{"instructions":[{"primitive":"point","center":[0.8,0.2],"radius":0.006}]}"#)
            .instructions,
    );
    let continued = resolve_checked_performance(
        PerformanceRequest {
            score: &continued_input,
            performance_seed: Some(41),
            composition_seed: Some(17),
            canvas: Some(canvas),
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("independent instruction remains after the failed Connected current");
    assert_eq!(continued.instruction_indices(), [0, 1, 2, 3, 4, 5, 6]);
    assert_eq!(
        continued.original_instruction_indices(),
        [0, 1, 0, 1, 2, 3, 4]
    );
    assert_eq!(
        continued
            .execution
            .expect("omission summary")
            .rendered_instruction_indices,
        [0, 1, 0, 1, 2, 3, 4]
    );
}

#[test]
fn grid_relation_is_dropped_with_structured_warning() {
    let input = score(
        r#"{"instructions":[{"primitive":"square","position":[0.4,0.4],"size":[0.1,0.1],
        "arrangement":{"count":4,"layout":"grid"},"relation":{"type":"between"}}]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: Some(9),
        composition_seed: None,
        canvas: None,
    });
    assert!(result.score.instructions[0].relation.is_none());
    assert_eq!(result.warnings[0].reason, "grid layout consumes relation");
}

#[test]
fn connected_chain_uses_one_endpoint_consumer_for_all_five_required_pairs() {
    let canvas = CanvasSize::new(1200.0, 700.0);
    let input = score(
        r#"{"canvas":"wide","instructions":[
        {"primitive":"line","from":[0.12,0.2],"to":[0.32,0.2],"rotation":25},
        {"primitive":"line","from":[0.4,0.3],"to":[0.64,0.3],"rotation":-10,
         "relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}},
        {"primitive":"arc","center":[0.52,0.5],"position":[0.52,0.43],"radius":0.13,
         "angle_start":150,"angle_end":30,"rotation":20,
         "relation":{"type":"connected","target_instruction_index":1,"position_authority":"named_movable"}},
        {"primitive":"arc","center":[0.65,0.64],"position":[0.65,0.57],"radius":0.11,
         "angle_start":145,"angle_end":35,"rotation":-15,
         "relation":{"type":"connected","target_instruction_index":2,"position_authority":"named_movable"}},
        {"primitive":"point","center":[0.75,0.7],"radius":0.006,
         "relation":{"type":"connected","target_instruction_index":3,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.2,0.8],"to":[0.44,0.8],"rotation":35,
         "relation":{"type":"connected","target_instruction_index":4,"position_authority":"named_movable"}}
        ]}"#,
    );
    let original_lengths = input
        .instructions
        .iter()
        .map(|instruction| {
            endpoint_geometry(instruction, Some(canvas))
                .map(|(start, end, _, _)| (end.x - start.x).hypot(end.y - start.y))
        })
        .collect::<Vec<_>>();

    let result = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: None,
            composition_seed: Some(19),
            canvas: Some(canvas),
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("all required Connected pairs perform");

    assert!(result.execution.is_none());
    assert_eq!(result.instruction_indices(), [0, 1, 2, 3, 4, 5]);
    assert_eq!(result.score.instructions[0], input.instructions[0]);
    // Three sequences are read at each index, and the output also at the one before.
    #[allow(clippy::needless_range_loop)]
    for index in 1..result.score.instructions.len() {
        let prior = endpoint_geometry(&result.score.instructions[index - 1], Some(canvas)).unwrap();
        let current = endpoint_geometry(&result.score.instructions[index], Some(canvas)).unwrap();
        assert!((prior.1.x - current.0.x).abs() < 1.0e-9, "pair {index} x");
        assert!((prior.1.y - current.0.y).abs() < 1.0e-9, "pair {index} y");
        assert_eq!(
            result.score.instructions[index].rotation,
            input.instructions[index].rotation
        );
        if let Some(original_length) = original_lengths[index] {
            let current_length = (current.1.x - current.0.x).hypot(current.1.y - current.0.y);
            assert!(
                (original_length - current_length).abs() < 1.0e-9,
                "pair {index} length"
            );
        }
    }
}

#[test]
fn numeric_connected_position_succeeds_only_when_the_fixed_endpoint_already_matches() {
    let compatible = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.4,0.5]},
        {"primitive":"line","from":[0.4,0.5],"to":[0.7,0.5],
         "relation":{"type":"connected","target_instruction_index":0,"position_authority":"numeric_fixed"}}
        ]}"#,
    );
    assert!(
        resolve_checked_performance(
            PerformanceRequest {
                score: &compatible,
                performance_seed: None,
                composition_seed: None,
                canvas: None,
            },
            ScoreErrorPolicy::Stop,
        )
        .is_ok()
    );

    let mut conflicting = compatible.clone();
    conflicting.instructions[1].from_ = Some(inku_render::types::Point::new(0.5, 0.5));
    conflicting.instructions[1].to = Some(inku_render::types::Point::new(0.8, 0.5));
    let stopped = resolve_checked_performance(
        PerformanceRequest {
            score: &conflicting,
            performance_seed: None,
            composition_seed: None,
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("relation failure preserves geometry")
    .execution
    .expect("relation diagnostic");
    assert_eq!(
        stopped.diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
}

#[test]
fn continue_omits_the_failed_relation_and_keeps_original_indices_and_dependencies() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.2],"to":[0.4,0.2]},
        {"primitive":"line","from":[0.5,0.2],"to":[0.8,0.2],
         "relation":{"type":"connected","target_instruction_index":0,"position_authority":"numeric_fixed"}},
        {"primitive":"point","center":[0.7,0.5],"radius":0.006,
         "relation":{"type":"connected","target_instruction_index":1,"position_authority":"named_movable"}},
        {"primitive":"point","center":[0.8,0.8],"radius":0.006}
        ]}"#,
    );
    let result = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(31),
            composition_seed: None,
            canvas: None,
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("independent survivor remains");

    assert_eq!(result.instruction_indices(), [0, 1, 2, 3]);
    assert_eq!(result.score.instructions.len(), 4);
    let execution = result.execution.expect("omissions stay typed");
    assert_eq!(execution.rendered_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(execution.diagnostics.len(), 1);
    assert_eq!(
        execution.diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
    assert_eq!(
        execution.diagnostics[0].disposition,
        ScoreExecutionDisposition::RelationOmitted
    );
}

#[test]
fn continue_resolves_a_legacy_relation_against_the_preserved_connected_source() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.2],"to":[0.4,0.2]},
        {"primitive":"line","from":[0.5,0.2],"to":[0.8,0.2],
         "relation":{"type":"connected","target_instruction_index":0,"position_authority":"numeric_fixed"}},
        {"primitive":"point","center":[0.7,0.5],"radius":0.006,
         "relation":{"type":"along"}},
        {"primitive":"point","center":[0.8,0.8],"radius":0.006}
        ]}"#,
    );
    let result = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(31),
            composition_seed: None,
            canvas: None,
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("independent survivor remains");

    assert_eq!(result.instruction_indices(), [0, 1, 2, 3]);
    let execution = result.execution.expect("both omissions stay typed");
    assert_eq!(execution.rendered_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(execution.diagnostics.len(), 1);
    assert_eq!(
        execution.diagnostics[0].disposition,
        ScoreExecutionDisposition::RelationOmitted
    );
}

#[test]
fn a_missing_relation_keeps_the_only_drawable_instruction() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.2],"to":[0.4,0.2],
         "relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}}
        ]}"#,
    );
    let stopped = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: None,
            composition_seed: None,
            canvas: None,
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("the only shape survives its missing relation");

    assert_eq!(stopped.original_instruction_indices(), [0]);
    let diagnostics = stopped.execution.unwrap().diagnostics;
    assert_eq!(diagnostics.len(), 1);
    assert_eq!(
        diagnostics[0].reason,
        ScoreExecutionReason::CyclicConnectedDependency
    );
    assert_eq!(
        diagnostics[0].disposition,
        ScoreExecutionDisposition::RelationOmitted
    );
}

#[test]
fn transform_groups_use_physical_precise_bounds_nested_rotation_and_stable_cloudform_seed() {
    let input = score(
        r#"{"version":"0.4.0","instructions":[
        {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],"arrangement":{"count":2,"group_size":2,"layout":"horizontal"}},
        {"primitive":"point","center":[0.2,0.2],"radius":0.01},
        {"primitive":"polygon","center":[0.18,0.50],"radius":0.11,"sides":5},
        {"primitive":"arc","center":[0.44,0.50],"position":[0.44,0.50],"radius":0.18,"angle_start":18,"angle_end":71},
        {"primitive":"cloudform","center":[0.70,0.50],"size":[0.20,0.12],"weight":"pencil"}
        ],"transform_groups":[
          {"start":3,"end":5,"rotation_degrees":31},
          {"start":2,"end":5,"rotation_degrees":90}
        ]}"#,
    );
    let result = resolve_checked_performance(
        PerformanceRequest {
            score: &input,
            performance_seed: Some(71),
            composition_seed: Some(71),
            canvas: Some(CanvasSize::new(2000.0, 1000.0)),
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("nested transform groups perform");
    assert!(result.score.transform_groups.is_empty());
    assert_eq!(result.instruction_seed_overrides().len(), 7);
    for (index, angle) in [(4, 90.0_f64), (5, 121.0), (6, 121.0)] {
        assert_eq!(result.score.instructions[index].rotation, None);
        let transform = result.instruction_transforms()[index];
        assert!((transform.a - angle.to_radians().cos()).abs() < 1e-9);
        assert!((transform.b - angle.to_radians().sin()).abs() < 1e-9);
    }
    assert_eq!(result.instruction_indices()[6], 6);
    assert_eq!(
        result.instruction_seed_overrides()[6],
        Some(inku_render::determinism::instruction_seed(
            &input.instructions[4],
            Some(71)
        ))
    );
    let before_center = inku_render::types::Point::new(1400.0, 500.0);
    let after_center = result.instruction_transforms()[6].apply(Point::new(
        result.score.instructions[6].center.unwrap().x * 2.0,
        result.score.instructions[6].center.unwrap().y,
    ));
    let after_center = Point::new(after_center.x * 1000.0, after_center.y * 1000.0);
    let before_contour = generate_cloudform_contour(CloudformRequest {
        center: before_center,
        size: inku_render::types::Point::new(200.0, 120.0),
        performance_seed: result.instruction_seed_overrides()[6],
        instruction_index: result.instruction_indices()[6],
        mark_index: 0,
        variation: input.instructions[4].variation.as_ref(),
        weight: input.instructions[4].weight,
        point_count: 49,
    });
    let after_contour = generate_cloudform_contour(CloudformRequest {
        center: after_center,
        size: inku_render::types::Point::new(200.0, 120.0),
        performance_seed: result.instruction_seed_overrides()[6],
        instruction_index: result.instruction_indices()[6],
        mark_index: 0,
        variation: result.score.instructions[6].variation.as_ref(),
        weight: result.score.instructions[6].weight,
        point_count: 49,
    });
    assert!(
        before_contour
            .iter()
            .zip(&after_contour)
            .all(|(before, after)| {
                ((before.x - before_center.x) - (after.x - after_center.x)).abs() < 1.0e-9
                    && ((before.y - before_center.y) - (after.y - after_center.y)).abs() < 1.0e-9
            })
    );

    let precise = score(
        r#"{"version":"0.4.0","instructions":[
        {"primitive":"line","from":[0.10,0.20],"to":[0.30,0.20]},
        {"primitive":"arc","center":[0.50,0.50],"radius":0.20,"angle_start":0,"angle_end":90},
        {"primitive":"polygon","center":[0.40,0.50],"radius":0.10,"sides":5}
        ],"transform_groups":[{"start":0,"end":3,"rotation_degrees":90}]}"#,
    );
    let precise_canvas = CanvasSize::new(2000.0, 1000.0);
    let precise_result = resolve_checked_performance(
        PerformanceRequest {
            score: &precise,
            performance_seed: Some(71),
            composition_seed: Some(71),
            canvas: Some(precise_canvas),
        },
        ScoreErrorPolicy::Stop,
    )
    .expect("precise group geometry performs");
    let line_anchor =
        instruction_anchor_on_canvas(&precise_result.score.instructions[0], Some(precise_canvas));
    let line_anchor = precise_result.instruction_transforms()[0]
        .apply(Point::new(line_anchor.x * 2.0, line_anchor.y));
    let line_anchor = Point::new(line_anchor.x / 2.0, line_anchor.y);
    // The upright pentagon's lower vertices have y = cy + r * cos(36 degrees).
    // In short-side units the combined bounds are x=[0.2, 1.2], y=[0.2, bottom].
    let bottom = 0.5 + 0.1 * (1.0 + 5.0_f64.sqrt()) / 4.0;
    let pivot_x = 0.7;
    let pivot_y = (0.2 + bottom) / 2.0;
    let expected_line_x = (pivot_x + pivot_y - 0.2) / 2.0;
    let expected_line_y = pivot_y + 0.4 - pivot_x;
    assert!(
        (line_anchor.x - expected_line_x).abs() < 1.0e-9,
        "{line_anchor:?}"
    );
    assert!(
        (line_anchor.y - expected_line_y).abs() < 1.0e-9,
        "{line_anchor:?}"
    );
    let arc = endpoint_geometry(&precise_result.score.instructions[1], Some(precise_canvas))
        .expect("group arc retains endpoint geometry");
    let arc = (
        precise_result.instruction_transforms()[1].apply(arc.0),
        precise_result.instruction_transforms()[1].apply(arc.1),
    );
    assert!(
        (arc.0.x - (pivot_x + pivot_y - 0.5)).abs() < 1.0e-9,
        "{arc:?}"
    );
    assert!(
        (arc.0.y - (pivot_y + 1.2 - pivot_x)).abs() < 1.0e-9,
        "{arc:?}"
    );
}

#[test]
fn external_connected_moves_its_whole_group_and_fixed_member_conflicts_preserve_the_range() {
    let input = score(
        r#"{"version":"0.4.0","instructions":[
        {"primitive":"line","from":[0.10,0.20],"to":[0.30,0.20]},
        {"primitive":"line","from":[0.50,0.45],"to":[0.70,0.45],"relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}},
        {"primitive":"point","center":[0.82,0.55],"radius":0.01},
        {"primitive":"point","center":[0.80,0.80],"radius":0.01}
        ],"transform_groups":[
          {"start":1,"end":3,"rotation_degrees":0},
          {"start":1,"end":3,"rotation_degrees":90}
        ]}"#,
    );
    let request = |score| PerformanceRequest {
        score,
        performance_seed: Some(91),
        composition_seed: Some(91),
        canvas: None,
    };
    let moved = resolve_checked_performance(request(&input), ScoreErrorPolicy::Stop)
        .expect("external Connected translates the enclosing group");
    let prior = endpoint_geometry(&moved.score.instructions[0], None).unwrap();
    let member = endpoint_geometry(&moved.score.instructions[1], None).unwrap();
    let member = (
        moved.instruction_transforms()[1].apply(member.0),
        moved.instruction_transforms()[1].apply(member.1),
    );
    assert!((prior.1.x - member.0.x).hypot(prior.1.y - member.0.y) < 1.0e-9);
    let center =
        moved.instruction_transforms()[2].apply(moved.score.instructions[2].center.unwrap());
    assert!((center.x - 0.20).abs() < 1.0e-9);
    assert!((center.y - 0.52).abs() < 1.0e-9);

    let mut fixed = input.clone();
    for group in &mut fixed.transform_groups {
        group.fixed_position_indices = vec![2];
    }
    let stopped = resolve_checked_performance(request(&fixed), ScoreErrorPolicy::Stop)
        .expect("relation failure preserves geometry")
        .execution
        .expect("relation diagnostic");
    assert_eq!(
        stopped.diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
    let continued = resolve_checked_performance(request(&fixed), ScoreErrorPolicy::OmitAndContinue)
        .expect("independent sibling survives group omission");
    assert_eq!(continued.original_instruction_indices(), [0, 1, 2, 3]);
}

#[test]
fn transform_group_integrity_stops_both_policies_and_empty_groups_preserve_legacy_execution() {
    let malformed = score(
        r#"{"version":"0.4.0","instructions":[{"primitive":"point","center":[0.5,0.5],"radius":0.01}],"transform_groups":[{"start":1,"end":1,"rotation_degrees":0}]}"#,
    );
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let stopped = resolve_checked_performance(
            PerformanceRequest {
                score: &malformed,
                performance_seed: Some(11),
                composition_seed: Some(11),
                canvas: None,
            },
            policy,
        )
        .expect_err("malformed transform groups are whole-score integrity errors");
        assert_eq!(
            stopped.diagnostics[0].reason,
            ScoreExecutionReason::InvalidTransformGroup
        );
        assert_eq!(
            stopped.diagnostics[0].disposition,
            ScoreExecutionDisposition::Stopped
        );
    }
    let failed_member = score(
        r#"{"version":"0.4.0","instructions":[
        {"primitive":"line","from":[0.1,0.2],"to":[0.3,0.2]},
        {"primitive":"point","center":[0.5,0.5],"radius":0.01},
        {"primitive":"line","from":[0.5,0.4],"to":[0.7,0.4],"relation":{"type":"connected","target_instruction_index":1,"position_authority":"numeric_fixed"}},
        {"primitive":"point","center":[0.8,0.7],"radius":0.01,"relation":{"type":"connected","target_instruction_index":2,"position_authority":"named_movable"}},
        {"primitive":"point","center":[0.8,0.8],"radius":0.01}
        ],"transform_groups":[{"start":1,"end":3,"rotation_degrees":0}]}"#,
    );
    let continued = resolve_checked_performance(
        PerformanceRequest {
            score: &failed_member,
            performance_seed: Some(11),
            composition_seed: Some(11),
            canvas: None,
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("failed final member omits its full group while independent work remains");
    assert_eq!(continued.original_instruction_indices(), [0, 1, 2, 3, 4]);
    let execution = continued
        .execution
        .expect("omission diagnostics remain typed");
    assert_eq!(
        execution.diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
    assert_eq!(
        execution.diagnostics[0].disposition,
        ScoreExecutionDisposition::RelationOmitted
    );
    let legacy = score(
        r#"{"instructions":[{"primitive":"line","from":[0.1,0.2],"to":[0.3,0.2]}],"transform_groups":[]}"#,
    );
    let request = PerformanceRequest {
        score: &legacy,
        performance_seed: Some(11),
        composition_seed: Some(11),
        canvas: None,
    };
    assert_eq!(
        resolve_checked_performance(request, ScoreErrorPolicy::Stop)
            .expect("empty groups preserve legacy execution")
            .score,
        resolve_performance(request).score
    );
}
