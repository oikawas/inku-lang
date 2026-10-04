//! A count written on a word that receives none repeats the whole word. The
//! copies become one placement group that the caller's action lays out once
//! (I-708): one copy per cell for no action, placing, scattering or drawing,
//! and the action's own layout for a line-up or a tile.

use inku_ddl::{
    CompilerResourceExecutionResult, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
};
use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::PerformanceRequest;
use inku_score::{
    Color, GroupLayout, HardResourcePolicy, OperationalResourceBudget, Point, Primitive,
    ResolvedPlacementRecipe, ResourceBudget, ResourceDemand, Score,
};
use serde_json::Value;

const ASSET: &str = include_str!("../assets/nature-leaves-v1.json");
const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8_192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

fn budget() -> ResourceBudget {
    ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 400,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 512,
            anchor_instances: 400,
            transform_instances: 400,
            placement_instances: 400,
            fill_instances: 400,
        },
    }
}

fn execute(source: &str) -> CompilerResourceExecutionResult {
    let package: Value = serde_json::from_str(ASSET).expect("Nature package must be JSON");
    let definitions = package["entries"]
        .as_array()
        .expect("package entries")
        .iter()
        .map(|entry| MacroDefinition::from_json(&entry["definition"].to_string()).unwrap())
        .collect::<Vec<_>>();
    let locks = definitions
        .iter()
        .map(|definition| {
            let identity = definition.identity().unwrap();
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .unwrap()
            .with_aliases(definition.alias_qualified_names())
            .unwrap()
        })
        .collect::<Vec<_>>();
    compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, locks).unwrap(),
        &definitions,
        Some(37),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        HardResourcePolicy {
            identity: "macro-outer-cells-test.v1".into(),
            budget: budget(),
        },
        OperationalResourceBudget(budget()),
    )
}

fn complete_score(source: &str, result: &CompilerResourceExecutionResult) -> Score {
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::Complete,
        "{source}: upstream={:?} downstream={:?} failure={:?}",
        result.upstream_diagnostics(),
        result.downstream_diagnostics(),
        result.failure()
    );
    result.score().expect("complete result has Score").clone()
}

#[test]
fn a_count_on_a_word_without_one_becomes_a_one_member_group() {
    for (source, layout) in [
        ("Nature.紅葉を3枚置く。", GroupLayout::Cells),
        ("Nature.紅葉を3枚散らす。", GroupLayout::Cells),
        ("3枚のNature.紅葉。", GroupLayout::Cells),
        (
            "Nature.紅葉を3枚並べる。",
            GroupLayout::HorizontalSourceOrder,
        ),
        ("Nature.紅葉を3枚敷き詰める。", GroupLayout::Tile),
    ] {
        let score = complete_score(source, &execute(source));
        assert!(score.repetition_groups.is_empty(), "{source}");
        assert_eq!(score.placement_groups.len(), 1, "{source}");
        let group = &score.placement_groups[0];
        assert_eq!(group.layout, layout, "{source}");
        assert_eq!(group.members.len(), 1, "{source}");
        assert_eq!(
            group.members[0].symbolic.as_ref().unwrap().instance_count,
            3,
            "{source}"
        );
        let resolved = group.resolved.as_ref().unwrap();
        assert_eq!(resolved.logical_count, 3, "{source}");
        match layout {
            GroupLayout::Cells => {
                assert_eq!(resolved.recipe, ResolvedPlacementRecipe::Cells, "{source}");
                assert_eq!(score.version, "0.19.0", "{source}");
                assert_eq!(group.at.region, [0.0, 0.0, 1.0, 1.0], "{source}");
            }
            GroupLayout::HorizontalSourceOrder => assert!(
                matches!(
                    resolved.recipe,
                    ResolvedPlacementRecipe::HorizontalLine { .. }
                ),
                "{source}"
            ),
            GroupLayout::Tile => assert!(
                matches!(
                    resolved.recipe,
                    ResolvedPlacementRecipe::Grid {
                        columns: 2,
                        rows: 2,
                        filled_count: 3,
                        ..
                    }
                ),
                "{source}"
            ),
            _ => unreachable!(),
        }
    }
}

#[test]
fn one_copy_a_fill_and_a_word_that_takes_the_count_keep_their_paths() {
    for source in ["Nature.紅葉を1枚置く。", "Nature.若葉を10枚置く。"] {
        let result = execute(source);
        let score = result
            .score()
            .unwrap_or_else(|| panic!("{source}: {:?}", result.downstream_diagnostics()));
        assert!(score.placement_groups.is_empty(), "{source}");
        assert_eq!(score.repetition_groups.len(), 1, "{source}");
        assert_eq!(
            score.repetition_groups[0]
                .member
                .symbolic
                .as_ref()
                .unwrap()
                .instance_count,
            1,
            "{source}"
        );
    }
    let result = execute("Nature.紅葉を3枚埋める。");
    let score = result.score().unwrap();
    assert!(score.placement_groups.is_empty());
    assert_eq!(score.fill_groups.len(), 1);
}

#[test]
fn a_cells_group_and_a_later_coordinated_group_stay_in_source_order() {
    let source = "Nature.紅葉を2枚置く。赤い円と青い円を並べる。";
    let score = complete_score(source, &execute(source));
    assert_eq!(
        score
            .placement_groups
            .iter()
            .map(|group| group.layout)
            .collect::<Vec<_>>(),
        [GroupLayout::Cells, GroupLayout::HorizontalSourceOrder]
    );
    assert!(score.placement_groups[0].end <= score.placement_groups[1].start);
}

#[test]
fn performed_copies_of_a_maple_leaf_take_separate_cells() {
    let source = "Nature.紅葉を3枚置く。";
    let score = complete_score(source, &execute(source));
    let plan = resolve_checked_performance(
        PerformanceRequest {
            score: &score,
            performance_seed: Some(71),
            composition_seed: Some(37),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .unwrap();
    // Each leaf has one stem. The copies are the same body, so the difference
    // between two stems' transforms is the difference between their cells:
    // three columns by two rows, each about 0.33 by 0.5.
    let transforms = plan.instruction_transforms();
    let stems = plan
        .score
        .instructions
        .iter()
        .enumerate()
        .filter(|(_, instruction)| instruction.primitive == Primitive::Line)
        .map(|(index, _)| transforms[index].apply(Point::new(0.0, 0.0)))
        .collect::<Vec<_>>();
    assert_eq!(stems.len(), 3);
    for (index, stem) in stems.iter().enumerate() {
        for other in &stems[..index] {
            let (dx, dy) = ((stem.x - other.x).abs(), (stem.y - other.y).abs());
            assert!(dx > 0.25 || dy > 0.4, "{stem:?} and {other:?} share a cell");
        }
    }
}
