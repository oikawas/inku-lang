//! Chunk titles (DDL 27): a title line draws nothing, so a titled DDL lowers
//! to the Score its sentences lower to without the titles, with no diagnostic
//! of its own; and the chunks it names hold the instructions after each title.
//! Lowers the Score; draws no SVG.

use inku_ddl::{
    CompilerResourceExecutionResult, DdlChunk, MacroExpansionLimits, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

fn hard_policy() -> HardResourcePolicy {
    let budget = ResourceBudget {
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
    };
    HardResourcePolicy {
        identity: "chunk-titles-test.v1".into(),
        budget,
    }
}

fn compile(source: &str, language: ResolvedInstructionLanguage) -> CompilerResourceExecutionResult {
    let hard = hard_policy();
    compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(1),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    )
}

/// The titled source's chunks, after checking that it lowers as its untitled
/// sentences do.
fn chunks_of(
    titled: &str,
    untitled: &str,
    language: ResolvedInstructionLanguage,
) -> Vec<(String, Vec<usize>)> {
    let with = compile(titled, language);
    let without = compile(untitled, language);
    assert!(without.score().is_some(), "{untitled}");
    assert_eq!(with.score(), without.score(), "{titled}");
    assert_eq!(with.outcome(), without.outcome(), "{titled}");
    let reasons = |result: &CompilerResourceExecutionResult| {
        result
            .upstream_diagnostics()
            .iter()
            .map(|diagnostic| format!("{:?}", diagnostic.reason))
            .chain(
                result
                    .downstream_diagnostics()
                    .iter()
                    .map(|diagnostic| format!("{:?}", diagnostic.reason)),
            )
            .collect::<Vec<_>>()
    };
    assert_eq!(reasons(&with), reasons(&without), "{titled}");
    with.compilation()
        .semantic_document
        .as_ref()
        .expect("a titled DDL reads")
        .ast
        .chunks
        .iter()
        .map(
            |DdlChunk {
                 name,
                 instruction_indices,
             }| (name.clone(), instruction_indices.clone()),
        )
        .collect()
}

fn untitled(titled: &str) -> String {
    titled
        .split('\n')
        .filter(|line| !line.trim().is_empty() && inku_ddl::ddl_title_name(line).is_none())
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn titles_with_drawing_words_draw_nothing_and_name_their_chunks() {
    // A name with a shape word, one with a sentence end in it, a title that
    // ends a chunk, and a name used again for the same chunk.
    let titled = "画面比1:1。\n背景を黒で埋める。\n\n「黒い水面」\n\
        画面の横0.5、縦0.691の位置に、幅1.0、高さ0.618の青の薄い塗りの四角を1個置く。\n\n\
        「光の線」\n画面の横0.118、縦0.381966から横0.882、縦0.381966まで、白の太い線を1本引く。\n\n\
        「灯台の白い円。」\n画面の横0.618034、縦0.499466の位置に、直径0.1の白の塗りの円を1個置く。\n\n\
        「」\n画面の横0.3、縦0.618034の位置に、幅0.12、高さ0.03の黒の塗りの四角を1個置く。\n\n\
        「光の線」\n画面の横0.1、縦0.78から横0.9、縦0.78まで、灰の細い線を1本引く。";
    assert_eq!(
        chunks_of(titled, &untitled(titled), ResolvedInstructionLanguage::Ja),
        [
            ("黒い水面".to_owned(), vec![0]),
            ("光の線".to_owned(), vec![1, 4]),
            ("灯台の白い円。".to_owned(), vec![2]),
        ]
    );
}

#[test]
fn a_title_does_not_part_a_shape_from_its_continuation() {
    let titled = "中心に円を1個置く。\n「円」\n円は赤い。";
    assert_eq!(
        chunks_of(titled, &untitled(titled), ResolvedInstructionLanguage::Ja),
        []
    );
}

#[test]
fn english_titles_quote_with_straight_or_curly_quotes() {
    let titled = "Aspect ratio 1:1.\nfill the background with white.\n\n\"upon a hill\"\n\
        place one gray flat ellipse width 0.72, height 0.4 at horizontal 0.5, vertical 0.76.\n\n\
        “the slovenly wilderness”\n\
        scatter 150 green pencil thin diagonal lines length 0.07 in the range horizontal 0.04 to 0.96, vertical 0.59 to 0.96.\n\n\
        \"a jar in “Tennessee.”\"\n\
        place one red flat circle diameter 0.17 at horizontal 0.5, vertical 0.5.";
    assert_eq!(
        chunks_of(titled, &untitled(titled), ResolvedInstructionLanguage::En),
        [
            ("upon a hill".to_owned(), vec![0]),
            ("the slovenly wilderness".to_owned(), vec![1]),
            ("a jar in “Tennessee.”".to_owned(), vec![2]),
        ]
    );
}

#[test]
fn a_quoted_phrase_inside_a_sentence_is_no_title() {
    let source = "「赤い円」を中心に置く。";
    assert!(inku_ddl::ddl_title_lines(source).is_empty());
    let result = compile(source, ResolvedInstructionLanguage::Ja);
    assert!(
        result
            .compilation()
            .semantic_document
            .as_ref()
            .is_some_and(|document| document.ast.chunks.is_empty())
    );
}
