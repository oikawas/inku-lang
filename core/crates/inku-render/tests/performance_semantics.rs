use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::{PerformanceRequest, resolve_performance};
use inku_render::planning::endpoint_geometry;
use inku_render::types::{
    CanvasSize, Score, ScoreErrorPolicy, ScoreExecutionDisposition, ScoreExecutionReason,
};

fn score(json: &str) -> Score {
    serde_json::from_str(json).unwrap()
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
    assert_eq!(result.instruction_indices, [0, 1, 2, 3, 4, 5]);
    assert_eq!(result.score.instructions[0], input.instructions[0]);
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
    .expect_err("fixed numeric mismatch stops");
    assert_eq!(
        stopped.diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
}

#[test]
fn continue_omits_the_failed_current_and_keeps_original_indices_and_dependencies() {
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

    assert_eq!(result.instruction_indices, [0, 3]);
    assert_eq!(result.score.instructions.len(), 2);
    let execution = result.execution.expect("omissions stay typed");
    assert_eq!(execution.rendered_instruction_indices, [0, 3]);
    assert_eq!(execution.diagnostics.len(), 2);
    assert_eq!(
        execution.diagnostics[0].reason,
        ScoreExecutionReason::NumericConnectedPositionConflict
    );
    assert_eq!(
        execution.diagnostics[1].reason,
        ScoreExecutionReason::ConnectedReferenceOmitted
    );
}

#[test]
fn continue_does_not_retarget_a_legacy_relation_across_a_connected_omission() {
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

    assert_eq!(result.instruction_indices, [0, 3]);
    let execution = result.execution.expect("both omissions stay typed");
    assert_eq!(execution.rendered_instruction_indices, [0, 3]);
    assert_eq!(execution.diagnostics.len(), 2);
    assert_eq!(
        execution.diagnostics[1].reason,
        ScoreExecutionReason::ConnectedReferenceOmitted
    );
}

#[test]
fn continue_stops_instead_of_returning_an_all_omitted_work() {
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
    .expect_err("an all-omitted work is never successful");

    assert_eq!(stopped.diagnostics.len(), 2);
    assert_eq!(
        stopped.diagnostics[1].reason,
        ScoreExecutionReason::NoDrawableInstructions
    );
    assert_eq!(
        stopped.diagnostics[1].disposition,
        ScoreExecutionDisposition::Stopped
    );
}
