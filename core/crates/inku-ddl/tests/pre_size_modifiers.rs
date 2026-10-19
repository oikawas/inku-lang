//! Prenominal modifiers may stand before a Japanese numeric size, as in
//! `赤い太筆の長さ0.6の線` and `赤い半径0.1の円`. They reach the same head, with
//! the same Score, as when they follow the size.
use inku_ddl::*;
use inku_score::Color;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn document(source: &str) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(
        source,
        if source.is_ascii() {
            ResolvedInstructionLanguage::En
        } else {
            ResolvedInstructionLanguage::Ja
        },
        vec![],
    )
    .unwrap()
}

fn execute(source: &str) -> CompilerExecutionResult {
    compile_ddl_to_score(
        document(source),
        &[],
        Some(19),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    )
}

/// The Score and its downstream reasons, once nothing upstream was omitted.
fn performed(source: &str) -> (serde_json::Value, Vec<String>) {
    let execution = execute(source);
    assert!(
        execution.upstream_diagnostics().is_empty(),
        "{source}: {:?}",
        execution.upstream_diagnostics()
    );
    assert_eq!(
        execution.outcome(),
        ScoreLoweringOutcome::Complete,
        "{source}: {:?}",
        execution.downstream_diagnostics()
    );
    (
        serde_json::to_value(execution.score().unwrap()).unwrap(),
        execution
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| format!("{:?}", diagnostic.reason))
            .collect(),
    )
}

fn assert_same_score(sources: &[&str]) {
    let expected = performed(sources[0]);
    for source in &sources[1..] {
        assert_eq!(performed(source), expected, "{source} vs {}", sources[0]);
    }
}

#[test]
fn a_modifier_before_a_size_reaches_the_head() {
    assert_same_score(&[
        "長さ0.6の赤い太筆の線を1本引く。",
        "赤い太筆の長さ0.6の線を1本引く。",
        "赤い長さ0.6の太筆の線を1本引く。",
    ]);
    assert_same_score(&["長さ0.6の赤の線を1本引く。", "赤の長さ0.6の線を1本引く。"]);
    assert_same_score(&[
        "画面の横0.5、縦0.5の位置に、長さ0.6の細かくゆるやかに揺れる赤の太い太筆の薄い刷きの線を1個引く。",
        "画面の横0.5、縦0.5の位置に、細かくゆるやかに揺れる赤の太い太筆の薄い刷きの長さ0.6の線を1個引く。",
    ]);
    let (line, _) = performed("赤い太筆の長さ0.6の線を1本引く。");
    assert_eq!(line["instructions"][0]["color"], "red");
    assert_eq!(line["instructions"][0]["weight"], "brush_thick");
}

#[test]
fn an_adjective_right_before_a_size_is_read() {
    assert_same_score(&[
        "長さ0.6の赤い線を1本引く。",
        "赤い長さ0.6の線を1本引く。",
        "赤い 長さ0.6の線を1本引く。",
    ]);
    assert_same_score(&[
        "長さ0.6の細い黒い線を1本引く。",
        "細い長さ0.6の黒い線を1本引く。",
    ]);
    // The scale and the explicit length meet as they do after the size.
    assert_same_score(&[
        "長さ0.6の大きな赤い線を1本引く。",
        "大きな長さ0.6の赤い線を1本引く。",
    ]);
    assert_same_score(&[
        "一辺0.2の赤い四角を1個置く。",
        "赤い一辺0.2の四角を1個置く。",
    ]);
    assert_same_score(&[
        "半径0.1の赤い円を1個置く。",
        "赤い半径0.1の円を1個置く。",
        "赤い半径 0.1の円を1個置く。",
    ]);
}

#[test]
fn a_pair_of_sizes_keeps_the_modifier() {
    assert_same_score(&[
        "幅0.3、高さ0.2の赤い四角を1個置く。",
        "赤い幅0.3、高さ0.2の四角を1個置く。",
    ]);
    assert_same_score(&[
        "幅0.3、高さ0.2の赤の四角を1個置く。",
        "赤の幅0.3、高さ0.2の四角を1個置く。",
    ]);
    assert_same_score(&[
        "幅0.3、高さ0.2の大きな赤い四角を1個置く。",
        "大きな幅0.3、高さ0.2の赤い四角を1個置く。",
    ]);
    assert_same_score(&[
        "弦長0.4、矢高0.1の赤い弧を1個置く。",
        "赤い弦長0.4、矢高0.1の弧を1個置く。",
    ]);
}

#[test]
fn a_position_word_still_needs_a_particle_before_it() {
    // Only a size may directly follow a word; `横` after `赤い` is not an axis.
    let parsed = parse_neutral_lexemes(&document("赤い横0.5、縦0.5の位置に円を1個置く。"));
    assert!(
        parsed.tokens.iter().all(|token| token.surface != "横"
            || !matches!(token.kind, NeutralTokenKind::GeometryKeyword { .. })),
        "{:?}",
        parsed.tokens
    );
}

#[test]
fn a_size_does_not_carry_a_modifier_past_another_head() {
    // `赤い` belongs to 円: the walk back from 線 stops at 円, so 赤い is
    // neither given to 線 nor omitted as ambiguous.
    let execution = execute("赤い円の長さ0.6の線を1本引く。");
    assert!(
        execution
            .upstream_diagnostics()
            .iter()
            .all(|diagnostic| diagnostic
                .span
                .is_none_or(|span| span.start_byte >= "赤い".len())),
        "{:?}",
        execution.upstream_diagnostics()
    );
}

#[test]
fn an_english_count_before_a_size_reaches_the_noun() {
    assert_same_score(&[
        "place one red circle radius 0.12 at horizontal 0.5, vertical 0.5.",
        "place one radius 0.12 red circle at horizontal 0.5, vertical 0.5.",
    ]);
}
