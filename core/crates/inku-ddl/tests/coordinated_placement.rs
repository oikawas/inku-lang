use inku_ddl::*;
use inku_score::{Color, GroupLayout as ScoreGroupLayout, Score};
use serde_json::json;

const SOURCES: [&str; 3] = [
    "赤い円と青い四角を中央に置く",
    "赤い円と青い四角を中央に重ねて置く",
    "赤い円と青い四角を中央に並べて置く",
];

fn stage(source: &str) -> Stage15TransformationResult {
    let compiled = compile_typed_ddl(
        NormalizedDdlDocument::new(
            source,
            if source.is_ascii() {
                ResolvedInstructionLanguage::En
            } else {
                ResolvedInstructionLanguage::Ja
            },
            vec![],
        )
        .unwrap(),
        &[],
        Some(19),
        MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 64,
            max_nodes_per_invocation: 32,
            max_total_nodes: 64,
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
fn coordinated_placement_lowering_preserves_layout_source_owners_and_plan() {
    let mut default_and_explicit = Vec::new();
    for (index, source) in SOURCES.iter().enumerate() {
        let transformed = stage(source);
        let lower = lower_verified_stage15_score(transformed.verified_effective_view(), context());
        assert!(
            lower.diagnostics().is_empty(),
            "{source}: {:?}",
            lower.diagnostics()
        );
        let score = lower.score().unwrap();
        assert_eq!(score.instructions.len(), 2);
        assert_eq!(score.instructions[0].color, Color::Red);
        assert_eq!(score.instructions[1].color, Color::Blue);
        assert_eq!(score.placement_groups.len(), 1);
        let group = &score.placement_groups[0];
        assert_eq!((group.start, group.end), (0, 2));
        assert_eq!(
            group.layout,
            if index == 2 {
                ScoreGroupLayout::HorizontalSourceOrder
            } else {
                ScoreGroupLayout::Overlap
            }
        );
        assert_ne!(group.at.region, [0.5; 4]);
        assert_eq!(
            lower.instruction_origins(),
            [
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 0
                },
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 1
                }
            ]
        );
        let planned = plan_verified_stage15(transformed.verified_effective_view(), context());
        assert!(
            planned.diagnostics().is_empty(),
            "{:?}",
            planned.diagnostics()
        );
        assert_eq!(planned.objects().unwrap().len(), 2);
        assert_eq!(planned.placement_groups()[0].placement(), group);
        assert_eq!(planned.placement_groups()[0].group_index(), 0);
        assert_eq!(
            serde_json::from_value::<Score>(serde_json::to_value(score).unwrap()).unwrap(),
            *score
        );
        assert!(score.validate_schema_edition().is_ok());
        if index < 2 {
            default_and_explicit.push(score.clone());
        }
    }
    assert_eq!(default_and_explicit[0], default_and_explicit[1]);
    let invalid: Score = serde_json::from_value(json!({"version":"0.6.0","instructions":[{"primitive":"circle"}],"placement_groups":[{"start":0,"end":1,"layout":"overlap","at":{"region":[0.4,0.4,0.6,0.6]}}]})).unwrap();
    assert!(invalid.validate_schema_edition().is_err());
    let repeated = stage("place two red circle and one blue square at center.");
    let planned = plan_verified_stage15(repeated.verified_effective_view(), context());
    assert!(
        planned.diagnostics().is_empty(),
        "{:?}",
        planned.diagnostics()
    );
    assert_eq!(
        planned
            .objects()
            .unwrap()
            .iter()
            .map(|object| object.count())
            .collect::<Vec<_>>(),
        [2, 1]
    );
    assert_eq!(planned.placement_groups().len(), 1);
}

#[test]
fn coordinated_placement_reaches_geometry_once_and_preserves_outer_scope_relations() {
    use inku_render::{
        checked_performance::resolve_checked_performance, performance::PerformanceRequest,
    };
    use inku_score::{Point, ScoreErrorPolicy};
    let center = |plan: &inku_render::performance::PerformancePlan, index: usize| {
        let instruction = &plan.score.instructions[index];
        let anchor = instruction.center.unwrap_or_else(|| {
            let position = instruction.position.unwrap();
            let size = instruction.size.unwrap();
            Point::new(position.x + size.x / 2.0, position.y + size.y / 2.0)
        });
        plan.instruction_transforms[index].apply(anchor)
    };
    let resolve = |score: &Score| {
        resolve_checked_performance(
            PerformanceRequest {
                score,
                performance_seed: Some(71),
                composition_seed: Some(19),
                canvas: None,
            },
            ScoreErrorPolicy::Stop,
        )
        .unwrap()
    };
    for (index, source) in SOURCES.iter().enumerate() {
        let transformed = stage(source);
        let lower = lower_verified_stage15_score(transformed.verified_effective_view(), context());
        let score = lower.score().unwrap();
        let performed = resolve(score);
        assert!(performed.execution.is_none());
        assert_eq!(performed.original_instruction_indices, [0, 1]);
        assert!(performed.score.placement_groups.is_empty());
        assert!(
            performed
                .instruction_seed_overrides
                .iter()
                .all(Option::is_some)
        );
        let a = center(&performed, 0);
        let b = center(&performed, 1);
        assert!((a.y - b.y).abs() < 1e-9);
        assert!((b.x - a.x - if index == 2 { 0.5 } else { 0.0 }).abs() < 1e-9);
        let [x0, y0, x1, y1] = score.placement_groups[0].at.region;
        let target = Point::new(
            x0 + (x1 - x0) * inku_render::determinism::hash01(0, 71, "placement-group-x"),
            y0 + (y1 - y0) * inku_render::determinism::hash01(0, 71, "placement-group-y"),
        );
        assert!(((a.x + b.x) / 2.0 - target.x).abs() < 1e-9);
        assert!((a.y - target.y).abs() < 1e-9);
    }
    let input: Score = serde_json::from_value(json!({"version":"0.7.0","instructions":[
        {"primitive":"line","from":[0.1,0.1],"to":[0.3,0.1]},
        {"primitive":"line","from":[0.5,0.5],"to":[0.7,0.5],"relation":{"type":"connected","target_instruction_index":0,"position_authority":"named_movable"}},
        {"primitive":"line","from":[0.5,0.6],"to":[0.7,0.6]}
    ],"placement_groups":[{"start":1,"end":3,"layout":"overlap","at":{"region":[0.6,0.6,0.6,0.6]}}],
    "transform_groups":[{"start":1,"end":3,"rotation_degrees":90}]})).unwrap();
    let performed = resolve(&input);
    assert!(performed.execution.is_none(), "{:?}", performed.execution);
    let start =
        performed.instruction_transforms[1].apply(performed.score.instructions[1].from_.unwrap());
    assert!((start.x - 0.3).abs() < 1e-9 && (start.y - 0.1).abs() < 1e-9);
    let other =
        performed.instruction_transforms[2].apply(performed.score.instructions[2].from_.unwrap());
    assert!((start.x - other.x).abs() < 1e-9 && (start.y - other.y).abs() < 1e-9);
    let mut internal = input;
    internal.instructions[2].relation = Some(
        serde_json::from_value(json!({
            "type":"connected","target_instruction_index":1,"position_authority":"named_movable"
        }))
        .unwrap(),
    );
    let recovered = resolve(&internal);
    assert_eq!(recovered.original_instruction_indices, [0, 1, 2]);
    assert_eq!(
        recovered.instruction_transforms,
        performed.instruction_transforms
    );
    let diagnostics = &recovered.execution.as_ref().unwrap().diagnostics;
    assert_eq!(diagnostics.len(), 1);
    assert_eq!(diagnostics[0].instruction_index, 2);
    assert_eq!(
        diagnostics[0].disposition,
        inku_score::ScoreExecutionDisposition::RelationOmitted
    );
}
