use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::{PerformancePlan, PerformanceRequest};
use inku_render::planning::endpoint_geometry;
use inku_render::types::{
    CanvasSize, Point, Score, ScoreErrorPolicy, ScoreExecutionDisposition, ScoreExecutionReason,
};
use serde_json::{Value, json};

fn plan(value: Value, canvas: Option<CanvasSize>, policy: ScoreErrorPolicy) -> PerformancePlan {
    let score: Score = serde_json::from_value(value).unwrap();
    resolve_checked_performance(
        PerformanceRequest {
            score: &score,
            performance_seed: Some(71),
            composition_seed: Some(71),
            canvas,
        },
        policy,
    )
    .unwrap()
}

fn endpoints(plan: &PerformancePlan, index: usize, canvas: Option<CanvasSize>) -> (Point, Point) {
    let (start, end, _, _) = endpoint_geometry(&plan.score.instructions[index], canvas).unwrap();
    (
        plan.instruction_transforms[index].apply(start),
        plan.instruction_transforms[index].apply(end),
    )
}

fn near(left: Point, right: Point) {
    assert!(
        (left.x - right.x).hypot(left.y - right.y) < 1e-9,
        "{left:?} != {right:?}"
    );
}

fn baseline(mut value: Value, canvas: Option<CanvasSize>) -> PerformancePlan {
    for instruction in value["instructions"].as_array_mut().unwrap() {
        instruction.as_object_mut().unwrap().remove("relation");
    }
    plan(value, canvas, ScoreErrorPolicy::Stop)
}

fn common_translation(
    before: &PerformancePlan,
    after: &PerformancePlan,
    members: std::ops::Range<usize>,
    canvas: Option<CanvasSize>,
) {
    let first = members.start;
    let (a, _) = endpoints(before, first, canvas);
    let (b, _) = endpoints(after, first, canvas);
    let delta = Point::new(b.x - a.x, b.y - a.y);
    for member in members {
        let (start, end) = endpoints(before, member, canvas);
        let (moved_start, moved_end) = endpoints(after, member, canvas);
        near(
            moved_start,
            Point::new(start.x + delta.x, start.y + delta.y),
        );
        near(moved_end, Point::new(end.x + delta.x, end.y + delta.y));
    }
    assert_eq!(
        before.instruction_seed_overrides,
        after.instruction_seed_overrides
    );
    assert_eq!(before.instruction_indices, after.instruction_indices);
    assert_eq!(
        before.original_instruction_indices,
        after.original_instruction_indices
    );
}

#[test]
fn touching_translates_complete_transformed_line_and_arc_groups() {
    let canvas = Some(CanvasSize::new(2000.0, 1000.0));
    let line = json!({"version":"0.6.0", "instructions":[
        {"primitive":"line", "from":[0.2,0.15], "to":[0.2,0.35]},
        {"primitive":"line", "from":[0.55,0.5], "to":[0.65,0.5], "relation":{
            "type":"touching", "target_instruction_index":0, "position_authority":"named_movable",
            "touching_constraints":{"dimensions_fixed":true,"direction_fixed":true}}},
        {"primitive":"line", "from":[0.55,0.55], "to":[0.65,0.55]},
        {"primitive":"line", "from":[0.1,0.9], "to":[0.2,0.9]}
    ], "transform_groups":[{"start":1,"end":3,"rotation_degrees":90,"scale_y":0.5}]});
    let before = baseline(line.clone(), canvas);
    let after = plan(line, canvas, ScoreErrorPolicy::Stop);
    assert!(after.execution.is_none());
    let target = endpoints(&after, 0, canvas);
    let source = endpoints(&after, 1, canvas);
    near(source.0, target.0);
    near(source.1, target.1);
    common_translation(&before, &after, 1..3, canvas);

    let arc = json!({"version":"0.6.0", "instructions":[
        {"primitive":"arc","center":[0.2,0.2],"radius":0.1,"angle_start":0,"angle_end":180},
        {"primitive":"arc","center":[0.6,0.6],"radius":0.1,"angle_start":0,"angle_end":180,
         "relation":{"type":"touching","target_instruction_index":0,"position_authority":"named_movable",
         "touching_constraints":{"dimensions_fixed":true,"direction_fixed":true}}},
        {"primitive":"line","from":[0.5,0.7],"to":[0.7,0.7]}
    ],"transform_groups":[{"start":1,"end":3,"rotation_degrees":0}]});
    let before = baseline(arc.clone(), None);
    let after = plan(arc, None, ScoreErrorPolicy::Stop);
    assert!(after.execution.is_none());
    let target = endpoints(&after, 0, None);
    let source = endpoints(&after, 1, None);
    near(source.0, target.0);
    near(source.1, target.1);
    common_translation(&before, &after, 1..3, None);
}

#[test]
fn along_and_cutting_preserve_rigid_geometry_and_omit_only_impossible_relations() {
    for kind in ["along", "cutting", "touching"] {
        let from = if kind == "cutting" {
            json!([0.5, 0.6])
        } else {
            json!([0.4, 0.6])
        };
        let to = if kind == "cutting" {
            json!([0.5, 0.8])
        } else {
            json!([0.6, 0.6])
        };
        let target_to = if kind == "touching" {
            json!([0.4, 0.2])
        } else {
            json!([0.7, 0.2])
        };
        let mut input = json!({"version":"0.6.0","instructions":[
            {"primitive":"line","from":[0.2,0.2],"to":target_to},
            {"primitive":"line","from":from,"to":to,"relation":{
                "type":kind,"target_instruction_index":0,"position_authority":"named_movable","gap":"medium",
                "touching_constraints":{"dimensions_fixed":true,"direction_fixed":true}}},
            {"primitive":"line","from":[0.6,0.6],"to":[0.7,0.7]},
            {"primitive":"line","from":[0.1,0.9],"to":[0.2,0.9]}
        ],"transform_groups":[{"start":1,"end":3,"rotation_degrees":0}]});
        let before = baseline(input.clone(), None);
        let after = plan(input.clone(), None, ScoreErrorPolicy::Stop);
        assert!(after.execution.is_none(), "{kind}: {:?}", after.execution);
        common_translation(&before, &after, 1..3, None);
        let (start, end) = endpoints(&after, 1, None);
        if kind == "along" {
            assert!((start.y - end.y).abs() < 1e-9);
            let gap = (start.y - 0.2).abs();
            assert!((0.06 - 1e-9..=0.12 + 1e-9).contains(&gap));
        } else if kind == "cutting" {
            assert!(start.y < 0.2 && end.y > 0.2);
        }

        input["instructions"][1]["relation"]["position_authority"] = json!("numeric_fixed");
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let failed = plan(input.clone(), None, policy);
            assert_eq!(failed.original_instruction_indices, [0, 1, 2, 3]);
            assert_eq!(failed.instruction_transforms, before.instruction_transforms);
            assert_eq!(
                failed.execution.as_ref().unwrap().diagnostics[0].disposition,
                ScoreExecutionDisposition::RelationOmitted
            );
        }
        input["instructions"][1]["relation"]["position_authority"] = json!("named_movable");
        input["transform_groups"][0]["rotation_degrees"] = json!(90);
        let failed = plan(input.clone(), None, ScoreErrorPolicy::Stop);
        let before = baseline(input, None);
        assert_eq!(failed.instruction_transforms, before.instruction_transforms);
        assert_eq!(failed.execution.as_ref().unwrap().diagnostics.len(), 1);
    }
}

#[test]
fn common_candidate_uses_relation_predicates_and_conflicts_restore_original_group() {
    let mut input = json!({"version":"0.6.0","instructions":[
        {"primitive":"line","from":[0.2,0.2],"to":[0.7,0.2]},
        {"primitive":"line","from":[0.4,0.6],"to":[0.6,0.6],"relation":{
            "type":"along","target_instruction_index":0,"position_authority":"named_movable","gap":"medium"}},
        {"primitive":"line","from":[0.5,0.65],"to":[0.6,0.65],"relation":{
            "type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.6,0.65],"to":[0.7,0.65]}
    ],"anchors":[{"position":[0.5,0.32]},{"position":[0.6,0.4]}],
    "transform_groups":[{"start":1,"end":4,"rotation_degrees":0}]});
    let before = baseline(input.clone(), None);
    let after = plan(input.clone(), None, ScoreErrorPolicy::Stop);
    assert!(after.execution.is_none());
    near(endpoints(&after, 2, None).0, Point::new(0.5, 0.32));
    common_translation(&before, &after, 1..4, None);

    input["instructions"][3]["relation"] =
        json!({"type":"connected","target_anchor_index":1,"position_authority":"named_movable"});
    input["anchors"][0]["position"] = json!([0.5, 0.65]);
    let failed = plan(input, None, ScoreErrorPolicy::Stop);
    assert_eq!(failed.instruction_transforms, before.instruction_transforms);
    let diagnostics = &failed.execution.as_ref().unwrap().diagnostics;
    assert_eq!(
        diagnostics
            .iter()
            .map(|d| d.instruction_index)
            .collect::<Vec<_>>(),
        [1, 3]
    );
    assert!(
        diagnostics
            .iter()
            .all(|d| d.reason == ScoreExecutionReason::ConflictingRelationConstraints)
    );
    near(endpoints(&failed, 2, None).0, Point::new(0.5, 0.65));
}

#[test]
fn missing_references_and_cycles_keep_sources_and_downstream_targets_for_both_policies() {
    let missing = json!({"version":"0.6.0","instructions":[
        {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],"relation":{
            "type":"connected","target_instruction_index":999,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.3,0.3],"to":[0.4,0.3],"relation":{
            "type":"connected","target_instruction_index":0,"position_authority":"named_movable"}}
    ]});
    let cycle = json!({"version":"0.6.0","instructions":[
        {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],"relation":{
            "type":"connected","target_anchor_index":1,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.6,0.6],"to":[0.7,0.6],"relation":{
            "type":"connected","target_anchor_index":0,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.1,0.1],"to":[0.2,0.1],"relation":{
            "type":"connected","target_anchor_index":0,"position_authority":"named_movable"}}
    ],"anchors":[{"at":{"region":[0.2,0.2,0.2,0.2]}},{"at":{"region":[0.7,0.7,0.7,0.7]}}],
    "transform_groups":[{"start":0,"end":1,"rotation_degrees":0,"anchor_indices":[0]},
        {"start":1,"end":2,"rotation_degrees":0,"anchor_indices":[1]}]});
    for input in [missing, cycle] {
        let stop = plan(input.clone(), None, ScoreErrorPolicy::Stop);
        let continued = plan(input, None, ScoreErrorPolicy::OmitAndContinue);
        assert_eq!(stop, continued);
        assert!(
            stop.execution
                .as_ref()
                .unwrap()
                .diagnostics
                .iter()
                .all(|d| d.disposition == ScoreExecutionDisposition::RelationOmitted)
        );
        assert_eq!(
            stop.original_instruction_indices,
            (0..stop.score.instructions.len()).collect::<Vec<_>>()
        );
        near(endpoints(&stop, 0, None).0, Point::new(0.1, 0.1));
        near(
            endpoints(&stop, stop.score.instructions.len() - 1, None).0,
            Point::new(
                0.2,
                if stop.score.instructions.len() == 2 {
                    0.1
                } else {
                    0.2
                },
            ),
        );
    }
}

#[test]
fn not_touching_uses_final_bounds_and_keeps_already_separated_numeric_groups() {
    let canvas = Some(CanvasSize::new(2000.0, 1000.0));
    let mut input = json!({"version":"0.6.0","instructions":[
        {"primitive":"line","from":[0.4,0.45],"to":[0.5,0.45]},
        {"primitive":"line","from":[0.42,0.5],"to":[0.52,0.5],"relation":{
            "type":"not_touching","target_instruction_index":0,"position_authority":"named_movable","gap":"medium"}},
        {"primitive":"line","from":[0.42,0.55],"to":[0.52,0.55]},
        {"primitive":"point","position":[0.9,0.9]}
    ],"transform_groups":[{"start":1,"end":3,"rotation_degrees":90,"scale_x":0.5}]});
    let before = baseline(input.clone(), canvas);
    let after = plan(input.clone(), canvas, ScoreErrorPolicy::Stop);
    assert!(after.execution.is_none(), "{:?}", after.execution);
    common_translation(&before, &after, 1..3, canvas);
    let (a, b) = endpoints(&after, 0, canvas);
    let (c, d) = endpoints(&after, 1, canvas);
    let distance = ((a.x + b.x - c.x - d.x) / 2.0).hypot((a.y + b.y - c.y - d.y) / 2.0);
    let radii = (a.x - b.x).hypot(a.y - b.y) / 2.0 + (c.x - d.x).hypot(c.y - d.y) / 2.0;
    assert!(distance >= radii + 0.06 - 1e-9);

    input["instructions"][1]["relation"]["position_authority"] = json!("numeric_fixed");
    let failed = plan(input.clone(), canvas, ScoreErrorPolicy::Stop);
    assert_eq!(failed.original_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(failed.instruction_transforms, before.instruction_transforms);
    assert_eq!(
        failed.execution.unwrap().diagnostics[0].reason,
        ScoreExecutionReason::NumericNotTouchingPositionConflict
    );
    input["instructions"][0]["from"] = json!([0.05, 0.1]);
    input["instructions"][0]["to"] = json!([0.15, 0.1]);
    let before = baseline(input.clone(), canvas);
    let far = plan(input, canvas, ScoreErrorPolicy::Stop);
    assert!(far.execution.is_none());
    assert_eq!(far.instruction_transforms, before.instruction_transforms);

    let standalone = json!({"version":"0.6.0","instructions":[
        {"primitive":"circle","center":[0.2,0.2],"radius":0.03},
        {"primitive":"circle","center":[0.8,0.8],"radius":0.03,"relation":{
            "type":"not_touching","target_instruction_index":0,"position_authority":"numeric_fixed"}}
    ]});
    let resolved = plan(standalone, None, ScoreErrorPolicy::Stop);
    assert!(resolved.execution.is_none());
    assert!(resolved.instruction_transforms[1].is_identity());
}

#[test]
fn between_waits_for_both_final_targets_and_moves_an_internal_target_with_its_group() {
    let input = json!({"version":"0.6.0","instructions":[
        {"primitive":"line","from":[0.25,0.3],"to":[0.35,0.3]},
        {"primitive":"line","from":[0.55,0.5],"to":[0.65,0.5]},
        {"primitive":"line","from":[0.6,0.65],"to":[0.7,0.65],"relation":{
            "type":"between","target_instruction_index":1,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.7,0.7],"to":[0.8,0.7]}
    ],"transform_groups":[
        {"start":0,"end":1,"rotation_degrees":90,"translate_x":0.1,"translate_y":0.1},
        {"start":1,"end":4,"rotation_degrees":0}
    ]});
    let before = baseline(input.clone(), None);
    let after = plan(input.clone(), None, ScoreErrorPolicy::Stop);
    assert!(after.execution.is_none(), "{:?}", after.execution);
    common_translation(&before, &after, 1..4, None);
    let center = |index| {
        let (a, b) = endpoints(&after, index, None);
        Point::new((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
    };
    let a = center(0);
    let b = center(1);
    let c = center(2);
    near(a, Point::new(0.4, 0.4));
    let jitter_x = c.x - (a.x + b.x) / 2.0;
    let jitter_y = c.y - (a.y + b.y) / 2.0;
    assert!((jitter_x + jitter_y).abs() < 1e-9);
    assert!(jitter_x.abs() <= 0.04 + 1e-9);
    let mut fixed = input;
    fixed["instructions"][2]["relation"]["position_authority"] = json!("numeric_fixed");
    let failed = plan(fixed, None, ScoreErrorPolicy::Stop);
    assert_eq!(failed.instruction_transforms, before.instruction_transforms);
    assert_eq!(failed.original_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(
        failed.execution.unwrap().diagnostics[0].reason,
        ScoreExecutionReason::NumericBetweenPositionConflict
    );

    let standalone = json!({"version":"0.6.0","instructions":[
        {"primitive":"circle","center":[0.2,0.2],"radius":0.03},
        {"primitive":"circle","center":[0.8,0.8],"radius":0.03},
        {"primitive":"circle","center":[0.3,0.3],"radius":0.03,"relation":{
            "type":"between","target_instruction_index":1,"position_authority":"numeric_fixed"}}
    ]});
    let resolved = plan(standalone, None, ScoreErrorPolicy::Stop);
    assert!(resolved.execution.is_none());
    assert!(resolved.instruction_transforms[2].is_identity());
}
