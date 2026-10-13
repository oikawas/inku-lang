//! The joint relation phrases reach Score 0.20.0 (DDL 18).

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score,
};
use inku_render::types::Color;
use inku_score::{RelationType, Score};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn compile(
    source: &str,
    language: ResolvedInstructionLanguage,
) -> (ScoreLoweringOutcome, Option<Score>) {
    let execution = compile_ddl_to_score(
        NormalizedDdlDocument::new(source.to_owned(), language, Vec::new()).unwrap(),
        &[],
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        ScoreErrorPolicy::Stop,
    );
    (execution.outcome(), execution.score().cloned())
}

#[test]
fn every_joint_phrase_reaches_the_score_as_a_relation_to_the_previous_shape() {
    for (japanese, english, kind) in [
        (
            "前の形に載る",
            "resting on the previous shape",
            RelationType::RestingOn,
        ),
        (
            "前の形の中に",
            "inside the previous shape",
            RelationType::Inside,
        ),
        (
            "前の形に重なる",
            "overlapping the previous shape",
            RelationType::Overlapping,
        ),
        (
            "前の形を横切る",
            "crossing the previous shape",
            RelationType::Crossing,
        ),
    ] {
        for (source, language) in [
            (
                format!(
                    "place one red square at center. place one blue circle at center {english}."
                ),
                ResolvedInstructionLanguage::En,
            ),
            (
                format!("赤い四角を中心に置く。\n{japanese}\n青い円を中心に置く。"),
                ResolvedInstructionLanguage::Ja,
            ),
        ] {
            let (outcome, score) = compile(&source, language);
            assert_eq!(outcome, ScoreLoweringOutcome::Complete, "{source}");
            let score = score.expect("Score");
            assert_eq!(score.version, "0.20.0", "{source}");
            let relation = score.instructions[1].relation.as_ref().expect("relation");
            assert_eq!(relation.kind, kind, "{source}");
            assert_eq!(relation.target_instruction_index, Some(0), "{source}");
            assert!(score.instructions[0].relation.is_none());
            score.validate_schema_edition().unwrap();
        }
    }
}

#[test]
fn a_connection_from_a_closed_shape_reaches_score_0_20_and_a_line_keeps_its_edition() {
    let (outcome, score) = compile(
        "place one red square at center. place one blue line at center connected to the previous shape.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(outcome, ScoreLoweringOutcome::Complete);
    let score = score.expect("Score");
    assert_eq!(score.version, "0.20.0");
    assert_eq!(
        score.instructions[1]
            .relation
            .as_ref()
            .map(|relation| relation.kind),
        Some(RelationType::Connected)
    );
    let (outcome, score) = compile(
        "place one red line at center. place one blue arc at center connected to the previous shape.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(outcome, ScoreLoweringOutcome::Complete);
    assert_ne!(score.expect("Score").version, "0.20.0");
}

#[test]
fn the_group_layout_word_overlapping_keeps_its_meaning() {
    let (outcome, score) = compile(
        "place a red circle and a blue square overlapping at the center.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(outcome, ScoreLoweringOutcome::Complete);
    let score = score.expect("Score");
    assert!(
        score
            .instructions
            .iter()
            .all(|instruction| instruction.relation.is_none())
    );
    assert!(
        score
            .placement_groups
            .iter()
            .any(|group| group.layout == inku_score::GroupLayout::Overlap)
    );
    assert_ne!(score.version, "0.20.0");
}
