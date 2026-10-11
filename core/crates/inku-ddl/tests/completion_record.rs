//! A3 (2026-10-11): the record of the ranges a completion wrote, how each range
//! of edited instructions stands against it, and the hole a range becomes when
//! the author changed only its words.

use inku_ddl::{
    CompilerLockState, CompletionRangeRecord, CompletionRangeState, MacroExpansionLimits,
    NormalizedDdlDocument, RANGE_WORDS_CHANGED_HOLE_KIND, RecordedRange,
    ResolvedInstructionLanguage, SemanticDeliveryOwner, compile_typed_ddl, match_completion_ranges,
    settle_completion_record, visible_ddl_patch_available, with_completion_record, written_ranges,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

/// Instructions as an approved completion left them: the first sentence is the
/// author's, the second a range the completion wrote.
const COMPLETED: &str =
    "白い四角を中心に置く。右下（横2/3〜1、縦2/3〜1）に橙色の小さな円を十個散らす。";

fn compiled(source: &str, language: ResolvedInstructionLanguage) -> inku_ddl::TypedDdlCompilation {
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    )
}

/// The record a completion leaves: every range with words it wrote.
fn record_of(source: &str, language: ResolvedInstructionLanguage) -> CompletionRangeRecord {
    CompletionRangeRecord {
        ranges: written_ranges(&compiled(source, language))
            .iter()
            .map(RecordedRange::from)
            .collect(),
    }
}

fn states(
    source: &str,
    language: ResolvedInstructionLanguage,
    record: &CompletionRangeRecord,
) -> Vec<(String, CompletionRangeState)> {
    match_completion_ranges(&written_ranges(&compiled(source, language)), record)
        .into_iter()
        .map(|found| (found.range.words, found.state))
        .collect()
}

/// T1: each edit of a recorded range stands as the author made it, including a
/// range the hosts renamed after its numbers were retyped.
#[test]
fn each_edited_range_stands_against_the_record() {
    use CompletionRangeState::{Completed, NumbersChanged, WordsChanged};
    let ja = ResolvedInstructionLanguage::Ja;
    let record = record_of(COMPLETED, ja);
    assert_eq!(record.ranges.len(), 1, "{record:?}");
    assert_eq!(record.ranges[0].words, "右下");
    assert!(record.ranges[0].sentence.contains('\u{FFFC}'));
    assert!(
        record.ranges[0]
            .sentence
            .contains("橙色の小さな円を十個散らす")
    );
    let mut mismatches = Vec::new();
    for (edited, expected) in [
        (COMPLETED.to_owned(), vec![("右下", Completed)]),
        (
            COMPLETED.replace("右下", "左上"),
            vec![("左上", WordsChanged)],
        ),
        (
            COMPLETED.replace("横2/3〜1", "横1/2〜1"),
            vec![("右下", NumbersChanged)],
        ),
        // The hosts rename a range whose numbers the author retyped.
        (
            COMPLETED.replace("右下（横2/3〜1", "指定の範囲（横1/2〜1"),
            vec![("指定の範囲", NumbersChanged)],
        ),
        // Another word of the sentence changed too.
        (
            COMPLETED.replace("右下", "左上").replace("十個", "五個"),
            vec![("左上", WordsChanged)],
        ),
        (
            COMPLETED
                .replace("横2/3〜1", "横1/2〜1")
                .replace("十個", "五個"),
            vec![("右下", NumbersChanged)],
        ),
        // Words, numbers and the sentence all changed: the author's own range.
        (
            COMPLETED
                .replace("右下（横2/3〜1、縦2/3〜1）", "左上（横0〜1/3、縦0〜1/3）")
                .replace("十個", "五個"),
            vec![],
        ),
        (
            COMPLETED.replace("右下（横2/3〜1、縦2/3〜1）に", "下に"),
            vec![],
        ),
    ] {
        let actual = states(&edited, ja, &record);
        let expected = expected
            .into_iter()
            .map(|(words, state)| (words.to_owned(), state))
            .collect::<Vec<_>>();
        if actual != expected {
            mismatches.push(format!("{edited}: {actual:?} != {expected:?}"));
        }
    }
    let en = ResolvedInstructionLanguage::En;
    let english = "scatter ten small orange circles at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1).";
    let english_record = record_of(english, en);
    let actual = states(
        &english.replace("the bottom right", "the top left"),
        en,
        &english_record,
    );
    if actual != vec![("the top left".to_owned(), WordsChanged)] {
        mismatches.push(format!("{english}: {actual:?}"));
    }
    assert!(mismatches.is_empty(), "{mismatches:#?}");
}

/// T1: a commit keeps only the recorded ranges the instructions still have, each
/// with the sentence it is in now and the words and numbers it was written with.
#[test]
fn a_commit_keeps_the_recorded_ranges_still_written() {
    let ja = ResolvedInstructionLanguage::Ja;
    let record = record_of(COMPLETED, ja);
    let edited = COMPLETED.replace("右下", "左上").replace("十個", "五個");
    let settled = settle_completion_record(&compiled(&edited, ja), &record);
    assert_eq!(settled.ranges.len(), 1);
    assert_eq!(settled.ranges[0].words, "右下");
    assert_eq!(settled.ranges[0].horizontal, record.ranges[0].horizontal);
    assert!(settled.ranges[0].sentence.contains("五個"));
    let removed = COMPLETED.replace("右下（横2/3〜1、縦2/3〜1）に", "下に");
    assert!(settle_completion_record(&compiled(&removed, ja), &record).is_empty());
}

/// T2: a range whose words alone changed becomes one hole over its source; the
/// compiler's own result does not change.
#[test]
fn a_range_whose_words_changed_is_a_hole_over_the_compilation() {
    let ja = ResolvedInstructionLanguage::Ja;
    let record = record_of(COMPLETED, ja);
    let edited = COMPLETED.replace("右下", "左上");
    let plain = compiled(&edited, ja);
    assert_eq!(
        plain.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    let laid = with_completion_record(plain.clone(), &record, &[]);
    assert_eq!(laid.compiler_lock, plain.compiler_lock);
    assert_eq!(laid.completion_record.as_ref(), Some(&record));
    let holes = laid
        .holes
        .iter()
        .filter(|hole| hole.kind == RANGE_WORDS_CHANGED_HOLE_KIND)
        .collect::<Vec<_>>();
    assert_eq!(holes.len(), 1, "{:?}", laid.holes);
    assert_eq!(laid.holes.len(), plain.holes.len() + 1);
    let hole = holes[0];
    assert_eq!(hole.allowed_span, hole.span);
    assert_eq!(hole.expected_owner, SemanticDeliveryOwner::NumericRange);
    assert_eq!(
        &edited[hole.span.start_byte..hole.span.end_byte],
        "左上（横2/3〜1、縦2/3〜1）"
    );
    assert!(visible_ddl_patch_available(&laid));
    assert!(!visible_ddl_patch_available(&plain));

    // Changed numbers are drawn as written: no hole.
    let numbers = COMPLETED.replace("横2/3〜1", "横1/2〜1");
    assert!(
        with_completion_record(compiled(&numbers, ja), &record, &[])
            .holes
            .is_empty()
    );
    // A range in a sentence the compiler cannot read stays inside that
    // sentence's hole.
    let unread = COMPLETED
        .replace("右下", "左上")
        .replace("散らす", "ランダムに散らす");
    let unread_plain = compiled(&unread, ja);
    assert!(!unread_plain.holes.is_empty(), "{unread}");
    let unread_laid = with_completion_record(unread_plain.clone(), &record, &[]);
    assert_eq!(unread_laid.holes, unread_plain.holes);
    // A range a patch wrote is not laid again.
    let skipped = with_completion_record(plain, &record, &[hole.span]);
    assert!(
        skipped
            .holes
            .iter()
            .all(|hole| hole.kind != RANGE_WORDS_CHANGED_HOLE_KIND)
    );
}
