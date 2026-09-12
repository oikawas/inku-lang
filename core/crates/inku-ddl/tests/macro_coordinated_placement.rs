use inku_ddl::*;
use inku_score::{Color, Point, Score};
use serde_json::{Value, json};

fn definition(body: Value) -> MacroDefinition {
    MacroDefinition::from_json(
        &json!({
            "schema":"inku.macro-definition.v1", "namespace":"Draw", "heading":"Pair",
            "version":"1.0.0", "parameters":{}, "components":{}, "body":body,
        })
        .to_string(),
    )
    .unwrap()
}

fn emit(shape: &str, color: &str, x: &str, count: u32) -> Value {
    json!({"op":"emit", "binding":null, "fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":shape},
        "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
        "color":{"expr":"semantic_ref","category":"color","id":color},
        "position_x":{"expr":"exact_decimal","value":x},
        "position_y":{"expr":"exact_decimal","value":"0.5"},
        "count":{"expr":"integer","value":count},
    }})
}

fn stage(source: &str, definition: &MacroDefinition) -> Stage15TransformationResult {
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let compiled = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, vec![lock]).unwrap(),
        std::slice::from_ref(definition),
        Some(19),
        MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 128,
            max_nodes_per_invocation: 64,
            max_total_nodes: 128,
        },
    );
    let input = stage15_transformation_input(&compiled).unwrap_or_else(|error| {
        panic!(
            "{source}: {error:?}; {:?}; {:?}",
            compiled.conflicts, compiled.blocking_diagnostics
        )
    });
    transform_stage15(input, None).unwrap()
}

fn context() -> ScoreLoweringContext {
    ScoreLoweringContext::resolve("square", Color::White).unwrap()
}

fn relation_body(kind: &str, numeric: bool, constrained: bool, count: u32) -> MacroDefinition {
    let mut first = emit("line", "red", "0.2", 1);
    let mut second = emit("line", "blue", "0.7", count);
    first["binding"] = json!("first");
    second["binding"] = json!("second");
    first["fields"]["position_y"]["value"] = json!("0.3");
    second["fields"]["position_y"]["value"] = json!("0.7");
    if !numeric {
        for node in [&mut first, &mut second] {
            let fields = node["fields"].as_object_mut().unwrap();
            fields.remove("position_x");
            fields.remove("position_y");
            fields.insert(
                "place".to_owned(),
                json!({"expr":"semantic_ref","category":"place","id":"top"}),
            );
        }
    }
    if constrained {
        second["fields"]["length"] = json!({"expr":"exact_decimal","value":"0.2"});
        second["fields"]["angle"] =
            json!({"expr":"semantic_ref","category":"angle","id":"vertical"});
    }
    definition(json!([first, second, {"op":"relation","kind":kind,"from":"first","to":"second"}]))
}

#[test]
fn checked_relation_delivery_preserves_direct_macro_score_and_symbolic_meaning() {
    use inku_score::{ConnectedPositionAuthority, RelationType, TouchingConstraints};
    // Each case exercises a distinct consumer rule, without a position/count matrix.
    for (kind, phrase, numeric, constrained, expected) in [
        (
            "connected",
            "connected to the previous shape",
            false,
            false,
            RelationType::Connected,
        ),
        (
            "touching",
            "touching the previous line",
            true,
            true,
            RelationType::Touching,
        ),
        (
            "along",
            "along the previous line",
            true,
            true,
            RelationType::Along,
        ),
        (
            "cutting",
            "cutting the previous line",
            false,
            false,
            RelationType::Cutting,
        ),
    ] {
        let shape = if constrained {
            "vertical line of length 0.2"
        } else {
            "line"
        };
        let (first_position, second_position) = if numeric {
            (
                "horizontal 0.2, vertical 0.3",
                "horizontal 0.7, vertical 0.7",
            )
        } else {
            ("top", "top")
        };
        let source = |count| {
            format!(
                "place one red line at {first_position}. place {count} blue {shape} at {second_position} {phrase}."
            )
        };
        let single_body = relation_body(kind, numeric, constrained, 1);
        let direct_stage = stage(&source(1), &single_body);
        let macro_stage = stage("Draw.Pair", &single_body);
        let direct =
            lower_verified_stage15_score(direct_stage.verified_effective_view(), context());
        let generated =
            lower_verified_stage15_score(macro_stage.verified_effective_view(), context());
        assert!(
            direct.diagnostics().is_empty(),
            "{kind}: {:?}",
            direct.diagnostics()
        );
        assert!(
            generated.diagnostics().is_empty(),
            "{kind}: {:?}",
            generated.diagnostics()
        );
        let a = &direct.score().unwrap().instructions[1];
        let b = &generated.score().unwrap().instructions[1];
        assert_eq!(a.relation, b.relation, "{kind}");
        assert_eq!(a.rotation, b.rotation);
        if numeric {
            assert_eq!((a.from_, a.to), (b.from_, b.to));
        }
        let relation = a.relation.as_ref().unwrap();
        assert_eq!(relation.kind, expected);
        assert_eq!(relation.target_instruction_index, Some(0));
        assert_eq!(
            relation.position_authority,
            Some(if numeric {
                ConnectedPositionAuthority::NumericFixed
            } else {
                ConnectedPositionAuthority::NamedMovable
            })
        );
        if kind == "touching" {
            assert_eq!(
                relation.touching_constraints,
                Some(TouchingConstraints {
                    dimensions_fixed: true,
                    direction_fixed: true
                })
            );
        }
        let repeated_body = relation_body(kind, numeric, constrained, 2);
        let repeated_direct = stage(&source(2), &repeated_body);
        let repeated_macro = stage("Draw.Pair", &repeated_body);
        let mut plans = Vec::new();
        for transformed in [
            &direct_stage,
            &macro_stage,
            &repeated_direct,
            &repeated_macro,
        ] {
            let plan = plan_verified_stage15(transformed.verified_effective_view(), context());
            assert!(
                plan.diagnostics().is_empty(),
                "{kind}: {:?}",
                plan.diagnostics()
            );
            let objects = plan.objects().unwrap();
            assert_eq!(objects.len(), 2);
            let intent = objects[1].relation().unwrap();
            assert_eq!(intent.kind(), relation.kind);
            assert_eq!(
                intent.target_object_index(),
                relation.target_instruction_index
            );
            assert_eq!(intent.position_authority(), relation.position_authority);
            assert_eq!(intent.touching_constraints(), relation.touching_constraints);
            assert_eq!(objects[1].angle(), a.rotation);
            plans.push(plan);
        }
        assert_eq!(plans[0].objects().unwrap()[1].count(), 1);
        assert_eq!(plans[2].objects().unwrap()[1].count(), 2);
        assert_eq!(plans[3].objects().unwrap()[1].count(), 2);
        assert_eq!(
            plans[2].objects().unwrap()[1].dimensions(),
            plans[3].objects().unwrap()[1].dimensions()
        );
        assert_eq!(
            plans[0].objects().unwrap()[1].dimensions(),
            plans[2].objects().unwrap()[1].dimensions()
        );
    }
    let mut omitted = emit("line", "blue", "0.5", 0);
    omitted["binding"] = json!("missing");
    let mut survivor = emit("line", "green", "0.7", 2);
    survivor["binding"] = json!("survivor");
    let body = definition(json!([emit("line", "red", "0.2", 1), omitted, survivor,
        {"op":"relation","kind":"connected","from":"missing","to":"survivor"}]));
    for source in [
        "Draw.Pair",
        "place one red line at center. place 0 blue line at center. place 2 green line at center connected to the previous shape.",
    ] {
        let transformed = stage(source, &body);
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context());
        let objects = plan.objects().unwrap();
        assert_eq!(objects.len(), 2);
        assert_eq!(objects[1].count(), 2);
        assert!(objects[1].relation().is_none());
        assert!(plan.diagnostics().iter().any(|diagnostic| matches!(
            diagnostic.disposition,
            ScoreDiagnosticDisposition::RelationOmitted
        )));
        if source == "Draw.Pair" {
            assert!(matches!(
                objects[1].origin(),
                ScoreInstructionOrigin::MacroEmit {
                    source_instruction_index: 0,
                    binding: Some(_),
                    ..
                }
            ));
        } else {
            assert!(matches!(
                objects[1].origin(),
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 2
                }
            ));
        }
    }
}

fn anchor_only_transform_body() -> MacroDefinition {
    definition(
        json!([{"op":"transform","transform":{"rotate_degrees":{"expr":"number","value":90.0}},"body":[
            {"op":"anchor","name":"pivot","fields":{"position_x":{"expr":"exact_decimal","value":"0.2"},"position_y":{"expr":"exact_decimal","value":"0.5"}}}
        ]}]),
    )
}

#[test]
fn checked_relation_delivery_anchor_member_uses_source_body_cursor() {
    let body = anchor_only_transform_body();
    let transformed = stage("arrange one green circle and Draw.Pair at center.", &body);
    let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context());
    let plan = plan_verified_stage15(transformed.verified_effective_view(), context());
    assert!(lowered.diagnostics().is_empty());
    assert!(plan.diagnostics().is_empty());
    let score = lowered.score().unwrap();
    assert!(score.validate_transform_groups().is_ok());
    let member = &score.placement_groups[0].members[1];
    assert_eq!((member.start, member.end), (1, 1));
    assert_eq!(member.anchor_indices, [0]);
    assert_eq!(member.transform_group_indices, [0]);
    assert_eq!(
        (
            score.transform_groups[0].start,
            score.transform_groups[0].end
        ),
        (1, 1)
    );
    assert_eq!(plan.placement_groups()[0].members()[1].member(), member);
    let transform = &plan.transform_groups()[0];
    assert_eq!((transform.start(), transform.end()), (1, 1));
    assert_eq!(transform.anchor_indices(), [0]);
    // The unchanged validator still rejects the original malformed containment.
    let mut invalid = score.clone();
    invalid.transform_groups[0].start = 0;
    invalid.transform_groups[0].end = 0;
    assert!(invalid.validate_transform_groups().is_err());
}

#[test]
fn checked_relation_numeric_recovery_and_anchor_member_reach_native_performer() {
    use inku_render::{
        checked_performance::resolve_checked_performance, performance::PerformanceRequest,
    };
    use inku_score::{ScoreExecutionDisposition, ScoreExecutionReason};
    let resolve = |score: &Score| {
        resolve_checked_performance(
            PerformanceRequest {
                score,
                performance_seed: Some(71),
                composition_seed: Some(19),
                canvas: None,
            },
            inku_score::ScoreErrorPolicy::Stop,
        )
        .unwrap()
    };
    let body = relation_body("along", true, false, 1);
    let transformed = stage("Draw.Pair", &body);
    let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context());
    assert!(lowered.diagnostics().is_empty());
    let score = lowered.score().unwrap();
    let mut baseline = score.clone();
    baseline.instructions[1].relation = None;
    let before = resolve(&baseline);
    let after = resolve(score);
    assert_eq!(after.score.instructions.len(), 2);
    assert_eq!(after.score.instructions, before.score.instructions);
    assert_eq!(after.instruction_transforms, before.instruction_transforms);
    assert_eq!(
        after.original_instruction_indices,
        before.original_instruction_indices
    );
    assert_eq!(
        after.instruction_seed_overrides,
        before.instruction_seed_overrides
    );
    let diagnostics = &after.execution.as_ref().unwrap().diagnostics;
    assert_eq!(diagnostics.len(), 1);
    assert_eq!(diagnostics[0].instruction_index, 1);
    assert_eq!(
        diagnostics[0].reason,
        ScoreExecutionReason::NumericAlongPositionConflict
    );
    assert_eq!(
        diagnostics[0].disposition,
        ScoreExecutionDisposition::RelationOmitted
    );

    let body = anchor_only_transform_body();
    let transformed = stage("arrange one green circle and Draw.Pair at center.", &body);
    let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context());
    let score = lowered.score().unwrap();
    assert!(score.validate_transform_groups().is_ok());
    let performed = resolve(score);
    assert!(performed.execution.is_none(), "{:?}", performed.execution);
    assert_eq!(performed.score.instructions.len(), 1);
    assert_eq!(performed.score.anchors.len(), 1);
}

#[test]
fn macro_members_preserve_complete_bodies_and_source_quantity_authority() {
    let single = definition(json!([emit("circle", "red", "0.5", 1)]));
    let mixed = stage("arrange Draw.Pair and one blue square at center.", &single);
    let direct = stage(
        "arrange one red circle and one blue square at center.",
        &single,
    );
    let mixed_plan = plan_verified_stage15(mixed.verified_effective_view(), context());
    let direct_plan = plan_verified_stage15(direct.verified_effective_view(), context());
    assert!(
        mixed_plan.diagnostics().is_empty(),
        "{:?}",
        mixed_plan.diagnostics()
    );
    for (a, b) in mixed_plan
        .objects()
        .unwrap()
        .iter()
        .zip(direct_plan.objects().unwrap())
    {
        assert_eq!(a.primitive(), b.primitive());
        assert_eq!(a.count(), b.count());
        assert_eq!(a.dimensions(), b.dimensions());
        assert_eq!(a.appearance(), b.appearance());
    }
    assert_eq!(mixed_plan.placement_groups()[0].logical_count(), 2);
    let body = definition(json!([
        emit("circle", "red", "0.3", 2),
        emit("square", "blue", "0.6", 1)
    ]));
    let standalone = stage("Draw.Pair", &body);
    let grouped = stage("scatter three Draw.Pair and green triangle at top.", &body);
    let baseline = plan_verified_stage15(standalone.verified_effective_view(), context());
    let plan = plan_verified_stage15(grouped.verified_effective_view(), context());
    assert!(plan.diagnostics().is_empty(), "{:?}", plan.diagnostics());
    assert_eq!(plan.objects().unwrap().len(), 3);
    assert_eq!(
        plan.objects()
            .unwrap()
            .iter()
            .map(|object| object.count())
            .collect::<Vec<_>>(),
        [2, 1, 5]
    );
    for (a, b) in plan.objects().unwrap()[..2]
        .iter()
        .zip(baseline.objects().unwrap())
    {
        assert_eq!(a.anchor(), b.anchor());
        assert_eq!(a.recipe(), b.recipe());
        assert_eq!(a.dimensions(), b.dimensions());
        assert_eq!(a.appearance(), b.appearance());
    }
    let group = &plan.placement_groups()[0];
    assert_eq!(group.logical_count(), 8);
    let members = group.members();
    assert_eq!(members[0].kind(), PlacementMemberKind::Macro);
    assert_eq!(members[0].logical_count(), 3);
    assert_eq!(members[0].body_repeat_count(), 3);
    assert!(!members[0].count_was_omitted());
    assert_eq!((members[0].member().start, members[0].member().end), (0, 2));
    assert_eq!(members[1].kind(), PlacementMemberKind::Primitive);
    assert_eq!(members[1].logical_count(), 5);
    assert_eq!(members[1].body_repeat_count(), 1);
    assert!(members[1].count_was_omitted());
    assert_eq!(members[1].source_instruction_index(), 1);
    assert!(matches!(
        plan.objects().unwrap()[0].origin(),
        ScoreInstructionOrigin::MacroEmit {
            source_instruction_index: 0,
            ..
        }
    ));
    assert!(plan.standalone_macro_repetitions().is_empty());
    let repeated = stage("three Draw.Pair", &body);
    let repeated = plan_verified_stage15(repeated.verified_effective_view(), context());
    assert!(
        repeated.diagnostics().is_empty(),
        "{:?}",
        repeated.diagnostics()
    );
    assert_eq!(
        repeated
            .objects()
            .unwrap()
            .iter()
            .map(|object| object.count())
            .collect::<Vec<_>>(),
        [2, 1]
    );
    assert!(repeated.placement_groups().is_empty());
    let envelope = &repeated.standalone_macro_repetitions()[0];
    assert_eq!(envelope.logical_count(), 3);
    assert_eq!(envelope.body_repeat_count(), 3);
    assert_eq!((envelope.member().start, envelope.member().end), (0, 2));
}

#[test]
fn macro_members_keep_generated_recovery_and_anchor_only_source_heads() {
    let body = definition(json!([
        emit("circle", "red", "0.3", 1),
        {"op":"emit","binding":null,"fields":{"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},
    ]));
    let transformed = stage(
        "place Draw.Pair and one green triangle at center. place one blue square at top.",
        &body,
    );
    let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context());
    let score = lowered.score().unwrap();
    assert_eq!(score.instructions.len(), 3);
    assert_eq!(score.placement_groups[0].members.len(), 2);
    assert_eq!(
        (
            score.placement_groups[0].members[0].start,
            score.placement_groups[0].members[0].end
        ),
        (0, 1)
    );
    assert!(!lowered.diagnostics().is_empty());
    assert!(
        lowered.diagnostics().iter().all(|diagnostic| matches!(
            diagnostic.owner,
            ScoreDiagnosticOwner::GeneratedNode { .. }
        ))
    );
    assert!(score.validate_transform_groups().is_ok());
    let anchors = definition(json!([{"op":"anchor","name":"pivot","fields":{
        "position_x":{"expr":"exact_decimal","value":"0.2"},
        "position_y":{"expr":"exact_decimal","value":"0.5"},
    }}]));
    let transformed = stage(
        "arrange Draw.Pair and one green circle at center.",
        &anchors,
    );
    let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context());
    assert!(
        lowered.diagnostics().is_empty(),
        "{:?}",
        lowered.diagnostics()
    );
    let score = lowered.score().unwrap();
    let member = &score.placement_groups[0].members[0];
    assert_eq!((member.start, member.end), (0, 0));
    assert_eq!(member.anchor_indices, [0]);
    assert_eq!(score.instructions.len(), 1);
    assert!(score.validate_transform_groups().is_ok());
    let mut old = score.clone();
    old.version = "0.8.0".to_owned();
    assert!(old.validate_transform_groups().is_err());
    let mut invalid = score.clone();
    invalid.placement_groups[0].members[1]
        .anchor_indices
        .push(0);
    assert!(invalid.validate_transform_groups().is_err());
}

fn transformed_body() -> MacroDefinition {
    let mut line = emit("line", "red", "0.5", 1);
    line["binding"] = json!("line");
    line["fields"].as_object_mut().unwrap().remove("position_x");
    line["fields"].as_object_mut().unwrap().remove("position_y");
    line["fields"]["place"] = json!({"expr":"semantic_ref","category":"place","id":"center"});
    definition(
        json!([{"op":"transform","transform":{"rotate_degrees":{"expr":"number","value":90.0}},"body":[
            {"op":"anchor","name":"pivot","fields":{"position_x":{"expr":"exact_decimal","value":"0.3"},"position_y":{"expr":"exact_decimal","value":"0.5"}}},
            line,
            {"op":"relation","kind":"connected","from":"pivot","to":"line"},
            emit("line", "blue", "0.6", 1),
        ]}]),
    )
}

#[test]
fn macro_member_geometry_finishes_internal_scopes_before_outer_placement() {
    use inku_render::{
        checked_performance::resolve_checked_performance, performance::PerformanceRequest,
    };
    let resolve = |score: &Score| {
        resolve_checked_performance(
            PerformanceRequest {
                score,
                performance_seed: Some(71),
                composition_seed: Some(19),
                canvas: None,
            },
            inku_score::ScoreErrorPolicy::Stop,
        )
        .unwrap()
    };
    let body = transformed_body();
    let standalone = stage("Draw.Pair", &body);
    let mixed = stage("arrange Draw.Pair and one green circle at center.", &body);
    let base_lower = lower_verified_stage15_score(standalone.verified_effective_view(), context());
    let mixed_lower = lower_verified_stage15_score(mixed.verified_effective_view(), context());
    assert!(
        mixed_lower.diagnostics().is_empty(),
        "{:?}",
        mixed_lower.diagnostics()
    );
    let score = mixed_lower.score().unwrap();
    assert_eq!(score.placement_groups[0].members[0].anchor_indices, [0]);
    assert_eq!(
        score.placement_groups[0].members[0].transform_group_indices,
        [0]
    );
    assert_eq!(
        (
            score.transform_groups[0].start,
            score.transform_groups[0].end
        ),
        (0, 2)
    );
    assert!(score.validate_transform_groups().is_ok());
    let base = resolve(base_lower.score().unwrap());
    let placed = resolve(score);
    assert!(placed.execution.is_none(), "{:?}", placed.execution);
    let endpoints = |plan: &inku_render::performance::PerformancePlan| {
        (0..2)
            .flat_map(|index| {
                let instruction = &plan.score.instructions[index];
                [instruction.from_.unwrap(), instruction.to.unwrap()]
                    .map(|point| plan.instruction_transforms[index].apply(point))
            })
            .collect::<Vec<_>>()
    };
    let a = endpoints(&base);
    let b = endpoints(&placed);
    let delta = Point::new(b[0].x - a[0].x, b[0].y - a[0].y);
    for (a, b) in a.iter().zip(&b) {
        assert!((b.x - a.x - delta.x).abs() < 1e-9 && (b.y - a.y - delta.y).abs() < 1e-9);
    }
    let macro_x = (b.iter().map(|p| p.x).fold(f64::INFINITY, f64::min)
        + b.iter().map(|p| p.x).fold(f64::NEG_INFINITY, f64::max))
        / 2.0;
    let circle =
        placed.instruction_transforms[2].apply(placed.score.instructions[2].center.unwrap());
    assert!((circle.x - macro_x - 0.5).abs() < 1e-9);
    // Omission can make an internal transform equal the remaining placement range.
    // Its explicit source ownership still puts it before placement; an unowned
    // transform over that same range remains an outer operation.
    let recovered = stage("arrange Draw.Pair and 0 green circle at center.", &body);
    let recovered = lower_verified_stage15_score(recovered.verified_effective_view(), context());
    let mut recovered_score = recovered.score().unwrap().clone();
    recovered_score.placement_groups[0].at.region = [0.5; 4];
    assert_eq!(recovered_score.placement_groups[0].members.len(), 1);
    assert_eq!(
        recovered_score.placement_groups[0].members[0].transform_group_indices,
        [0]
    );
    let sole = resolve(&recovered_score);
    let mut outer_score = recovered_score.clone();
    let mut outer = outer_score.transform_groups[0].clone();
    outer.rotation_degrees = 0.0;
    outer.translate_x = 0.125;
    outer_score.transform_groups.push(outer);
    assert!(outer_score.validate_transform_groups().is_ok());
    let outer = resolve(&outer_score);
    for (before, after) in endpoints(&sole).iter().zip(endpoints(&outer)) {
        assert!((after.x - before.x - 0.125).abs() < 1e-9 && (after.y - before.y).abs() < 1e-9);
    }
    let anchors = definition(json!([{"op":"anchor","name":"pivot","fields":{
        "position_x":{"expr":"exact_decimal","value":"0.2"},
        "position_y":{"expr":"exact_decimal","value":"0.5"},
    }}]));
    let anchored = stage(
        "arrange Draw.Pair and one green circle at center.",
        &anchors,
    );
    let anchored = lower_verified_stage15_score(anchored.verified_effective_view(), context());
    let mut anchored_score = anchored.score().unwrap().clone();
    anchored_score.instructions.push(serde_json::from_value(json!({
        "primitive":"line", "from":[0.2,0.5], "to":[0.3,0.5],
        "relation":{"type":"connected","target_anchor_index":0,"position_authority":"named_movable"},
    })).unwrap());
    let anchored = resolve(&anchored_score);
    assert!(anchored.execution.is_none(), "{:?}", anchored.execution);
    let circle =
        anchored.instruction_transforms[0].apply(anchored.score.instructions[0].center.unwrap());
    let line_start =
        anchored.instruction_transforms[1].apply(anchored.score.instructions[1].from_.unwrap());
    assert!((circle.x - line_start.x - 0.5).abs() < 1e-9 && (circle.y - line_start.y).abs() < 1e-9);
    let [x0, y0, x1, y1] = anchored_score.placement_groups[0].at.region;
    let target = Point::new(
        x0 + (x1 - x0) * inku_render::determinism::hash01(0, 71, "placement-group-x"),
        y0 + (y1 - y0) * inku_render::determinism::hash01(0, 71, "placement-group-y"),
    );
    assert!((circle.x - target.x).abs() < 1e-9 && (circle.y - target.y).abs() < 1e-9);
}
