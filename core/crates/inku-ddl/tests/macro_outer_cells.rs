//! A count written on a word that receives none repeats the whole word. The
//! copies become one placement group that the caller's action lays out once
//! (I-708): one copy per cell for no action, placing, scattering or drawing,
//! and the action's own layout for a line-up or a tile.

use inku_ddl::{
    CompilerResourceExecutionResult, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
};
use inku_render::checked_performance::resolve_checked_performance_with_resources;
use inku_render::performance::PerformanceRequest;
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, Point, Primitive,
    ResourceBudget, ResourceDemand, Score,
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

fn hard_policy() -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "macro-outer-cells-test.v1".into(),
        budget: budget(),
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
        ScoreErrorPolicy::OmitAndContinue,
        hard_policy(),
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
fn performed_copies_of_a_maple_leaf_take_separate_cells() {
    let source = "Nature.紅葉を3枚置く。";
    let score = complete_score(source, &execute(source));
    let plan = resolve_checked_performance_with_resources(
        PerformanceRequest {
            score: &score,
            performance_seed: Some(71),
            composition_seed: Some(37),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
        &hard_policy(),
        OperationalResourceBudget(budget()),
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
