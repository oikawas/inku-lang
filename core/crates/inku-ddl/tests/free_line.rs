//! The free line (I-715, DDL 19, Score 0.21.0): the word reaches the Score as
//! its own primitive with a line's geometry, and joins another mark only at
//! its ends, as the current mark or as the previous one.

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreFieldGap, ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
};
use inku_render::checked_performance::resolve_checked_performance_with_resources;
use inku_render::performance::{PerformancePlan, PerformanceRequest};
use inku_render::types::{CanvasSize, ScoreExecutionReason};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, Primitive, RelationType, ResourceBudget,
    ResourceDemand, Score,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn hard_policy() -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "free-line-test.v1".into(),
        budget: ResourceBudget {
            maximum: ResourceDemand {
                logical_objects: 4096,
                primitive_marks: 400,
                object_templates: 64,
                maximum_per_template_primitive_marks: 240,
                maximum_resolved_count: 2000,
                template_nodes: 128,
                anchor_instances: 4096,
                transform_instances: 4096,
                placement_instances: 64,
                fill_instances: 64,
            },
        },
    }
}

struct Compiled {
    outcome: ScoreLoweringOutcome,
    score: Score,
    gaps: Vec<ScoreFieldGap>,
}

fn compile(source: &str, language: ResolvedInstructionLanguage) -> Compiled {
    let hard = hard_policy();
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(1),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    Compiled {
        outcome: result.outcome(),
        score: result.score().expect(source).clone(),
        gaps: result
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
    }
}

fn perform(score: &Score, seed: i128) -> PerformancePlan {
    let hard = hard_policy();
    resolve_checked_performance_with_resources(
        PerformanceRequest {
            score,
            performance_seed: Some(seed),
            composition_seed: None,
            canvas: Some(CanvasSize::new(1000.0, 1000.0)),
        },
        ScoreErrorPolicy::OmitAndContinue,
        &hard,
        OperationalResourceBudget(hard.budget),
    )
    .unwrap()
}

fn execution_reasons(plan: &PerformancePlan) -> Vec<ScoreExecutionReason> {
    plan.execution
        .as_ref()
        .map(|execution| {
            execution
                .diagnostics
                .iter()
                .map(|diagnostic| diagnostic.reason)
                .collect()
        })
        .unwrap_or_default()
}

#[test]
fn the_free_line_word_reaches_score_0_21_as_a_long_line() {
    for (source, language) in [
        (
            "中心に、黒の細筆の自由線を1個引く。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "place one black free line at center.",
            ResolvedInstructionLanguage::En,
        ),
    ] {
        let compiled = compile(source, language);
        assert_eq!(compiled.outcome, ScoreLoweringOutcome::Complete, "{source}");
        let score = compiled.score;
        assert_eq!(score.version, "0.21.0", "{source}");
        score.validate_schema_edition().unwrap();
        let free_line = &score.instructions[0];
        assert_eq!(free_line.primitive, Primitive::FreeLine, "{source}");
        let (from, to) = (free_line.from_.unwrap(), free_line.to.unwrap());
        // 11/20 of the short side by default, where a line has 6/25.
        assert!(
            ((to.x - from.x) - 0.55).abs() < 1.0e-9,
            "{source}: {from:?} {to:?}"
        );
        assert!((to.y - from.y).abs() < 1.0e-9, "{source}");
    }
    let line = compile(
        "中心に、黒の細筆の線を1個引く。",
        ResolvedInstructionLanguage::Ja,
    );
    assert_ne!(line.score.version, "0.21.0");
    let line = &line.score.instructions[0];
    assert!(((line.to.unwrap().x - line.from_.unwrap().x) - 0.24).abs() < 1.0e-9);
}

#[test]
fn a_size_word_and_an_angle_shape_the_free_line_as_they_shape_a_line() {
    let compiled = compile(
        "中心に、黒の細筆の右上がりの大きな自由線を1個引く。",
        ResolvedInstructionLanguage::Ja,
    );
    let free_line = &compiled.score.instructions[0];
    assert_eq!(free_line.primitive, Primitive::FreeLine);
    assert!(
        ((free_line.to.unwrap().x - free_line.from_.unwrap().x) - 0.825).abs() < 1.0e-9,
        "large is 3/2 of 11/20"
    );
    assert!(free_line.rotation.is_some_and(|rotation| rotation < 0.0));
}

#[test]
fn a_free_line_keeps_a_connection_and_a_touch_on_either_side() {
    for (source, current, kind) in [
        (
            "中心に、黒のペンの円を1個置く。\n前の形につながる黒の細筆の自由線を1個引く。",
            Primitive::FreeLine,
            RelationType::Connected,
        ),
        (
            "中心に、黒の細筆の自由線を1個引く。\n前の形につながる黒のペンの線を1個引く。",
            Primitive::Line,
            RelationType::Connected,
        ),
        (
            "上に、黒のペンの線を1個引く。\n前の線に触れる黒の細筆の自由線を1個引く。",
            Primitive::FreeLine,
            RelationType::Touching,
        ),
    ] {
        let compiled = compile(source, ResolvedInstructionLanguage::Ja);
        assert!(
            !compiled
                .gaps
                .iter()
                .any(|gap| matches!(gap, ScoreFieldGap::UnsupportedRelation { .. })),
            "{source}: {:?}",
            compiled.gaps
        );
        let instruction = &compiled.score.instructions[1];
        assert_eq!(instruction.primitive, current, "{source}");
        let relation = instruction.relation.as_ref().expect(source);
        assert_eq!(relation.kind, kind, "{source}");
        assert_eq!(relation.target_instruction_index, Some(0), "{source}");
        for seed in [1, 7, 42] {
            let plan = perform(&compiled.score, seed);
            assert!(
                execution_reasons(&plan).is_empty(),
                "{source} seed {seed}: {:?}",
                plan.execution
            );
        }
    }
}

#[test]
fn a_connection_moves_the_free_line_start_onto_the_end_of_the_previous_line() {
    let compiled = compile(
        "上に、黒のペンの線を1個引く。\n前の形につながる黒の細筆の自由線を1個引く。",
        ResolvedInstructionLanguage::Ja,
    );
    let plan = perform(&compiled.score, 7);
    assert!(execution_reasons(&plan).is_empty(), "{:?}", plan.execution);
    let line = &plan.score.instructions[0];
    let free_line = &plan.score.instructions[1];
    assert_eq!(free_line.primitive, Primitive::FreeLine);
    let (end, start) = (line.to.unwrap(), free_line.from_.unwrap());
    assert!(
        (end.x - start.x).abs() < 1.0e-9 && (end.y - start.y).abs() < 1.0e-9,
        "{end:?} {start:?}"
    );
}

#[test]
fn a_touch_lays_the_free_line_ends_on_the_ends_of_the_previous_line() {
    let compiled = compile(
        "上に、黒のペンの線を1個引く。\n前の線に触れる黒の細筆の自由線を1個引く。",
        ResolvedInstructionLanguage::Ja,
    );
    let plan = perform(&compiled.score, 7);
    assert!(execution_reasons(&plan).is_empty(), "{:?}", plan.execution);
    let line = &plan.score.instructions[0];
    let free_line = &plan.score.instructions[1];
    assert_eq!(free_line.primitive, Primitive::FreeLine);
    for (a, b) in [
        (line.from_.unwrap(), free_line.from_.unwrap()),
        (line.to.unwrap(), free_line.to.unwrap()),
    ] {
        assert!(
            (a.x - b.x).abs() < 1.0e-9 && (a.y - b.y).abs() < 1.0e-9,
            "{a:?} {b:?}"
        );
    }
}

#[test]
fn a_free_line_drops_every_other_relation_with_its_reason_and_is_drawn() {
    let circle = "中心に、黒のペンの円を1個置く。";
    let free_line = "黒の細筆の自由線を1個引く。";
    let line = "上に、黒のペンの線を1個引く。";
    let mut sources = Vec::new();
    for phrase in [
        "前の形に載る",
        "前の形の中に",
        "前の形に重なる",
        "前の形を横切る",
        "前の形に触れない",
    ] {
        // The free line as the current mark, and as the previous one.
        sources.push(format!("{circle}\n{phrase}{free_line}"));
        sources.push(format!(
            "中心に、{free_line}\n{phrase}黒のペンの円を1個置く。"
        ));
    }
    for phrase in ["前の線に沿って", "前の線を切る"] {
        sources.push(format!("{line}\n{phrase}{free_line}"));
    }
    sources.push(format!(
        "{circle}\n下に、黒のペンの円を1個置く。\n前の二つの間に{free_line}"
    ));
    for source in sources {
        let compiled = compile(&source, ResolvedInstructionLanguage::Ja);
        assert_eq!(
            compiled.outcome,
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{source}"
        );
        assert!(
            compiled
                .gaps
                .iter()
                .any(|gap| matches!(gap, ScoreFieldGap::UnsupportedRelation { .. })),
            "{source}: {:?}",
            compiled.gaps
        );
        assert!(
            compiled
                .score
                .instructions
                .iter()
                .all(|instruction| instruction.relation.is_none()),
            "{source}"
        );
        assert!(
            compiled
                .score
                .instructions
                .iter()
                .any(|instruction| instruction.primitive == Primitive::FreeLine),
            "{source}"
        );
    }
}

#[test]
fn a_mirror_of_a_free_line_is_dropped_with_its_reason_and_both_are_drawn() {
    let compiled = compile(
        "上に、黒の細筆の自由線を1個引く。\n下に、前の形と鏡写しの黒の細筆の自由線を1個引く。",
        ResolvedInstructionLanguage::Ja,
    );
    assert_eq!(
        compiled.score.mirror_relations.len(),
        1,
        "{:?}",
        compiled.gaps
    );
    let plan = perform(&compiled.score, 7);
    assert_eq!(
        execution_reasons(&plan),
        [ScoreExecutionReason::MirrorBodyMismatch],
        "{:?}",
        plan.execution
    );
    assert_eq!(
        plan.score
            .instructions
            .iter()
            .filter(|instruction| instruction.primitive == Primitive::FreeLine)
            .count(),
        2
    );
}
