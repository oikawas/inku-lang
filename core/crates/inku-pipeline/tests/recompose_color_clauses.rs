//! "Change the layout" on a sentence that colors or fades its marks (DDL 23):
//! two colors in turn, colors repeating or shifting in order, and a fade say
//! nothing of where the marks go, so the sentence is read without them, its
//! range alone is written again, and the clauses stay as they are written. The
//! documents are the composed documents of two 5173 works (stage B-5, gpt-6-luna
//! ja-20 and en-04) with one sentence given the clauses.

use inku_ddl::{MacroExpansionLimits, ResolvedInstructionLanguage};
use inku_pipeline::recompose::{RecomposeMode, Recomposition, recompose};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8_192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

const JA: [&str; 4] = [
    "背景を黒で埋める。",
    "中央の縦（横1/3〜2/3、縦0〜1）に、白の細筆の程よい塗りの小さな円を5個並べる。",
    "中心（横1/3〜2/3、縦1/3〜2/3）に、黄の細筆の程よい塗りの大きな円を5個置く。",
    "画面全体（横0〜1、縦0〜1）に、白の鉛筆の薄いとても小さな点を30個散らす。",
];

const EN: [&str; 4] = [
    "Fill the background with black.",
    "Line up 12 white thin fine-brush temperate sweep diagonal large lines diagonally at the top (horizontal 0 to 1, vertical 0 to 1/3).",
    "Scatter 18 white thin fine-brush faint empty small ellipses at the upper right quarter (horizontal 1/2 to 1, vertical 0 to 1/2).",
    "Draw 8 yellow thin fine-brush temperate sweep horizontal normal-sized lines at the upper left quarter (horizontal 0 to 1/2, vertical 0 to 1/2).",
];

/// The document with one sentence written again.
fn document(sentences: &[&str], index: usize, sentence: &str) -> String {
    let mut lines = sentences.to_vec();
    lines[index] = sentence;
    lines.join("\n")
}

fn recomposed(
    source: &str,
    language: ResolvedInstructionLanguage,
    mode: RecomposeMode,
) -> Recomposition {
    recompose(
        source,
        language,
        &[],
        LIMITS,
        mode,
        7_871_133,
        "color-clauses-test",
    )
}

#[test]
fn a_sentence_that_colors_or_fades_its_marks_moves_and_keeps_its_clauses() {
    let ja = ResolvedInstructionLanguage::Ja;
    let en = ResolvedInstructionLanguage::En;
    let cases = [
        (
            document(
                &JA,
                1,
                "中央の縦（横1/3〜2/3、縦0〜1）に、白と黄を交互にして、細筆の程よい塗りの小さな円を5個並べる。",
            ),
            ja,
            "白と黄を交互にして、",
        ),
        (
            document(
                &JA,
                1,
                "中央の縦（横1/3〜2/3、縦0〜1）に、白・黄・橙の順に繰り返して、細筆の程よい塗りの小さな円を5個並べる。",
            ),
            ja,
            "白・黄・橙の順に繰り返して、",
        ),
        (
            document(
                &JA,
                1,
                "中央の縦（横1/3〜2/3、縦0〜1）に、白・黄・橙の順に段々に移して、上から下へ薄れさせて、細筆の程よい塗りの小さな円を5個並べる。",
            ),
            ja,
            "白・黄・橙の順に段々に移して、上から下へ薄れさせて、",
        ),
        (
            document(
                &JA,
                3,
                "画面全体（横0〜1、縦0〜1）に、白・黄・橙の順に繰り返して、中心から外へ薄れさせて、鉛筆の薄いとても小さな点を30個散らす。",
            ),
            ja,
            "白・黄・橙の順に繰り返して、中心から外へ薄れさせて、",
        ),
        (
            document(
                &EN,
                2,
                "Scatter 18 thin fine-brush faint empty small ellipses at the upper right quarter (horizontal 1/2 to 1, vertical 0 to 1/2), repeating white, yellow, and orange in order, fading outward from the center.",
            ),
            en,
            ", repeating white, yellow, and orange in order, fading outward from the center.",
        ),
    ];
    for (source, language, clauses) in cases {
        for mode in [RecomposeMode::Principled, RecomposeMode::Chance] {
            let Recomposition::Recomposed {
                source: rewritten,
                moves,
                ..
            } = recomposed(&source, language, mode)
            else {
                panic!("{mode:?}: {source}");
            };
            assert!(!moves.is_empty(), "{mode:?}: {source}");
            assert!(rewritten.contains(clauses), "{mode:?}: {rewritten}");
        }
    }
}

/// A layer read without its clauses takes the color of its first mark, so
/// colors in turn that start with its color word, or a fade, send every layer
/// where the sentence without them sends it.
#[test]
fn the_clauses_do_not_change_where_the_layers_go() {
    let ja = ResolvedInstructionLanguage::Ja;
    let plain = JA.join("\n");
    for sentence in [
        "中央の縦（横1/3〜2/3、縦0〜1）に、白と黄を交互にして、細筆の程よい塗りの小さな円を5個並べる。",
        "中央の縦（横1/3〜2/3、縦0〜1）に、上から下へ薄れさせて、白の細筆の程よい塗りの小さな円を5個並べる。",
    ] {
        let source = document(&JA, 1, sentence);
        for mode in [RecomposeMode::Principled, RecomposeMode::Chance] {
            let places = |source: &str| match recomposed(source, ja, mode) {
                Recomposition::Recomposed { moves, .. } => moves
                    .into_iter()
                    .map(|range| (range.layer, range.to_key))
                    .collect::<Vec<_>>(),
                other => panic!("{mode:?}: {other:?}"),
            };
            assert_eq!(places(&source), places(&plain), "{mode:?}: {sentence}");
        }
    }
}

/// A sequence of shapes is still a sentence a plan does not write.
#[test]
fn a_sequence_of_shapes_still_stays_as_it_is() {
    let source = document(
        &JA,
        1,
        "赤い円・青い線・灰の弧の順に繰り返して、八つ並べる。",
    );
    assert_eq!(
        recomposed(
            &source,
            ResolvedInstructionLanguage::Ja,
            RecomposeMode::Principled
        ),
        Recomposition::Unchanged {
            reason: "unsupported_sentence"
        }
    );
}
