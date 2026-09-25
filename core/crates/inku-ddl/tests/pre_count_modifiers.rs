//! Prenominal modifiers may stand before a Japanese count phrase, as in
//! `大きな四つの円` and `細い三本の線`. They reach the same head, with the same
//! Score, as when they follow the count.
use inku_ddl::*;
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand, Score,
};

fn score(source: &str) -> Score {
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
    assert!(
        compiled.holes.is_empty() && compiled.conflicts.is_empty() && compiled.blocking_diagnostics.is_empty(),
        "{source}: {:?}; {:?}; {:?}",
        compiled.holes,
        compiled.conflicts,
        compiled.blocking_diagnostics
    );
    let input = stage15_transformation_input(&compiled).unwrap();
    let transformed = transform_stage15(input, None).unwrap();
    let plan = plan_verified_stage15(
        transformed.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    // Explicit fixture budgets; this does not introduce installation defaults.
    let budget = ResourceBudget {
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
    };
    let selected = select_composition_plan_resources(
        &plan,
        HardResourcePolicy {
            identity: "pre-count-modifiers-test.v1".to_owned(),
            budget,
        },
        OperationalResourceBudget(budget),
    )
    .unwrap_or_else(|error| panic!("{source}: {error:?}; plan: {:?}", plan.diagnostics()));
    let delivered = materialize_selected_composition(&selected)
        .unwrap_or_else(|error| panic!("{source}: {error:?}"));
    assert!(delivered.diagnostics.is_empty(), "{source}: {:?}", delivered.diagnostics);
    assert!(delivered.resource_omissions.is_empty(), "{source}: {:?}", delivered.resource_omissions);
    delivered.score
}

fn assert_same_score(sources: &[&str]) {
    let expected = serde_json::to_value(score(sources[0])).unwrap();
    for source in &sources[1..] {
        assert_eq!(serde_json::to_value(score(source)).unwrap(), expected, "{source} vs {}", sources[0]);
    }
}

#[test]
fn a_scale_before_the_count_reaches_the_head() {
    assert_same_score(&[
        "四つの大きな赤い円を置く。",
        "大きな四つの赤い円を置く。",
        "赤い大きな四つの円を置く。",
        "大きな赤い円を四つ置く。",
    ]);
    assert_same_score(&["4個の大きな赤い円を置く。", "大きな4個の赤い円を置く。"]);
}

#[test]
fn a_thinness_before_a_counted_line_keeps_the_count_and_the_action() {
    assert_same_score(&[
        "三本の細い黒い線を引く。",
        "細い三本の黒い線を引く。",
        "黒い細い三本の線を引く。",
        "細い黒い線を三本引く。",
    ]);
    let lines = score("細い三本の黒い線を引く。");
    assert_eq!(lines.instructions.len(), 1);
    assert_eq!(lines.instructions[0].color, Color::Black);
    assert_eq!(lines.instructions[0].arrangement.as_ref().map(|arrangement| arrangement.count), Some(3));
}
