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
