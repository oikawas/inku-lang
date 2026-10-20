//! A fade written in words (DDL 23): `左から右へ薄れさせて` / `fading from left to
//! right` and the other three directions make the marks of a row fade from the
//! named end, and `中心から外へ薄れさせて` / `fading outward from the center` makes
//! the marks of a row or a scatter fade outward. Colors written in order may
//! shift once through the marks (`黄・橙・赤の順に段々に移して` / `shifting
//! through yellow, orange, and red in order`) instead of repeating.

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreFieldGap, ScoreLoweringContext, compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, Fade, HardResourcePolicy, Instruction, OperationalResourceBudget, Point,
    ResolvedPlacementRecipe, ResourceBudget, ResourceDemand, Score,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn policy() -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "fade-and-shift-test.v1".into(),
        budget: ResourceBudget {
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
        },
    }
}

fn language(source: &str) -> ResolvedInstructionLanguage {
    if source.is_ascii() {
        ResolvedInstructionLanguage::En
    } else {
        ResolvedInstructionLanguage::Ja
    }
}

struct Compiled {
    /// None when every instruction was left out.
    score: Option<Score>,
    gaps: Vec<ScoreFieldGap>,
    upstream: Vec<String>,
}

fn compile(source: &str) -> Compiled {
    let hard = policy();
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language(source), Vec::new()).unwrap(),
        &[],
        Some(19),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    Compiled {
        score: result.score().cloned(),
        gaps: result
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
        upstream: result
            .upstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
    }
}

/// The one instruction of a document that compiles whole.
fn instruction(source: &str) -> Instruction {
    let compiled = compile(source);
    assert!(
        compiled.upstream.is_empty(),
        "{source}: {:?}",
        compiled.upstream
    );
    assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
    let score = compiled.score.unwrap_or_else(|| panic!("{source}"));
    assert_eq!(score.instructions.len(), 1, "{source}");
    score.instructions[0].clone()
}

fn fade(instruction: &Instruction) -> Fade {
    instruction.arrangement.as_ref().unwrap().fade
}

fn recipe(instruction: &Instruction) -> ResolvedPlacementRecipe {
    instruction
        .arrangement
        .as_ref()
        .unwrap()
        .resolved
        .as_ref()
        .unwrap()
        .recipe
        .clone()
}

fn colors(instruction: &Instruction) -> Vec<Color> {
    instruction
        .arrangement
        .as_ref()
        .unwrap()
        .color_cycle
        .clone()
}

/// The same instruction with its fade and its recipe set aside, for comparing
/// a sentence with a fade to the same sentence without one.
fn without_fade(mut instruction: Instruction) -> Instruction {
    let arrangement = instruction.arrangement.as_mut().unwrap();
    arrangement.fade = Fade::None;
    arrangement.resolved.as_mut().unwrap().recipe = ResolvedPlacementRecipe::Place;
    instruction
}

const HORIZONTAL: &str = "画面の横0.1〜0.9、縦0.45〜0.55の範囲に、";
const VERTICAL: &str = "画面の横0.45〜0.55、縦0.1〜0.9の範囲に、";
const MARKS: &str = "赤い小さな円を5個並べる。";

fn row(place: &str, fade: &str) -> String {
    format!("{place}{fade}{MARKS}")
}

/// A horizontal row is numbered from the left and a vertical row from the top,
/// so a fade from the left or the top keeps the row's recipe, and a fade from
/// the other end numbers the same marks from that end: a row stepping back.
#[test]
fn a_fade_runs_from_the_named_end_of_a_row() {
    let plain = instruction(&row(HORIZONTAL, ""));
    let ResolvedPlacementRecipe::HorizontalLine { cell_width } = recipe(&plain) else {
        panic!("{:?}", recipe(&plain));
    };
    assert_eq!(fade(&plain), Fade::None);

    let left = instruction(&row(HORIZONTAL, "左から右へ薄れさせて、"));
    assert_eq!(fade(&left), Fade::Directional);
    assert_eq!(recipe(&left), recipe(&plain));
    let right = instruction(&row(HORIZONTAL, "右から左へ薄れさせて、"));
    assert_eq!(fade(&right), Fade::Directional);
    assert_eq!(
        recipe(&right),
        ResolvedPlacementRecipe::DiagonalLine {
            step: Point::new(-cell_width, 0.0)
        }
    );
    // Only the fade and the numbering differ from the sentence without it.
    assert_eq!(without_fade(left), without_fade(plain.clone()));
    assert_eq!(without_fade(right), without_fade(plain));

    let plain = instruction(&row(VERTICAL, ""));
    let ResolvedPlacementRecipe::VerticalLine { cell_height } = recipe(&plain) else {
        panic!("{:?}", recipe(&plain));
    };
    let top = instruction(&row(VERTICAL, "上から下へ薄れさせて、"));
    assert_eq!(fade(&top), Fade::Directional);
    assert_eq!(recipe(&top), recipe(&plain));
    let bottom = instruction(&row(VERTICAL, "下から上へ薄れさせて、"));
    assert_eq!(
        recipe(&bottom),
        ResolvedPlacementRecipe::DiagonalLine {
            step: Point::new(0.0, -cell_height)
        }
    );
}

/// A row between two points is numbered from the first point it writes, so a
/// fade numbers it again only when it names the other end, along either axis
/// of a diagonal row.
#[test]
fn a_fade_numbers_a_row_between_two_points_from_its_named_end() {
    let leftward = "画面の横0.882、縦0.5から横0.118、縦0.5まで、";
    let plain = instruction(&row(leftward, ""));
    let ResolvedPlacementRecipe::DiagonalLine { step } = recipe(&plain) else {
        panic!("{:?}", recipe(&plain));
    };
    assert!(step.x < 0.0 && step.y == 0.0, "{step:?}");
    let right = instruction(&row(leftward, "右から左へ薄れさせて、"));
    assert_eq!(recipe(&right), recipe(&plain));
    let left = instruction(&row(leftward, "左から右へ薄れさせて、"));
    assert_eq!(
        recipe(&left),
        ResolvedPlacementRecipe::DiagonalLine {
            step: Point::new(-step.x, 0.0)
        }
    );

    let falling = "画面の横0.1、縦0.1から横0.9、縦0.9まで、";
    let plain = recipe(&instruction(&row(falling, "")));
    let ResolvedPlacementRecipe::DiagonalLine { step } = plain.clone() else {
        panic!("{plain:?}");
    };
    let reversed = ResolvedPlacementRecipe::DiagonalLine {
        step: Point::new(-step.x, -step.y),
    };
    for (words, expected) in [
        ("左から右へ薄れさせて、", &plain),
        ("上から下へ薄れさせて、", &plain),
        ("右から左へ薄れさせて、", &reversed),
        ("下から上へ薄れさせて、", &reversed),
    ] {
        assert_eq!(
            &recipe(&instruction(&row(falling, words))),
            expected,
            "{words}"
        );
    }
}

/// Outward, the marks nearest the center are the darkest, in a row or in a
/// scatter, and the marks keep their order.
#[test]
fn a_fade_outward_takes_a_row_or_a_scatter() {
    let row_outward = instruction(&row(HORIZONTAL, "中心から外へ薄れさせて、"));
    assert_eq!(fade(&row_outward), Fade::Outward);
    assert_eq!(
        recipe(&row_outward),
        recipe(&instruction(&row(HORIZONTAL, "")))
    );
    let scatter = instruction(
        "画面全体（横0〜1、縦0〜1）に、中心から外へ薄れさせて、赤いとても小さな点を30個散らす。",
    );
    assert_eq!(fade(&scatter), Fade::Outward);
    assert_eq!(
        recipe(&scatter),
        ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation
    );
}

/// English writes the fade at the end, as an alternation, and reads as the
/// Japanese does.
#[test]
fn an_english_fade_reads_as_the_japanese_one() {
    let place = "in the range horizontal 0.1 to 0.9, vertical 0.45 to 0.55";
    for (english, japanese) in [
        ("fading from left to right", "左から右へ薄れさせて、"),
        ("fading from right to left", "右から左へ薄れさせて、"),
        ("fading outward from the center", "中心から外へ薄れさせて、"),
    ] {
        let en = instruction(&format!("Line up 5 small red circles {place}, {english}."));
        let ja = instruction(&row(HORIZONTAL, japanese));
        assert_eq!(fade(&en), fade(&ja), "{english}");
        assert_eq!(recipe(&en), recipe(&ja), "{english}");
    }
}

/// A fade where the marks cannot fade so is left out with its reason, never
/// dropped in silence: a tile, one mark, a direction on a scatter, a
/// direction across a row, and two fades in one sentence.
#[test]
fn marks_that_cannot_fade_so_are_left_out_with_a_reason() {
    for (source, gap) in [
        (
            "下の3分の2（横0〜1、縦1/3〜1）に、左から右へ薄れさせて、赤い小さな四角を16個敷き詰める。",
            ScoreFieldGap::UnsupportedFade,
        ),
        (
            "画面の横0.5、縦0.5の位置に、中心から外へ薄れさせて、赤い半径0.1の円を1個置く。",
            ScoreFieldGap::UnsupportedFade,
        ),
        (
            "画面全体（横0〜1、縦0〜1）に、左から右へ薄れさせて、赤いとても小さな点を30個散らす。",
            ScoreFieldGap::UnsupportedFade,
        ),
        (
            &row(VERTICAL, "左から右へ薄れさせて、"),
            ScoreFieldGap::FadeDirectionOffAxis,
        ),
        (
            &row(HORIZONTAL, "上から下へ薄れさせて、"),
            ScoreFieldGap::FadeDirectionOffAxis,
        ),
    ] {
        let compiled = compile(source);
        assert_eq!(compiled.gaps, vec![gap], "{source}");
        assert!(
            compiled
                .score
                .is_none_or(|score| score.instructions.is_empty()),
            "{source}"
        );
    }
    let twice = compile(&row(
        HORIZONTAL,
        "左から右へ薄れさせて、中心から外へ薄れさせて、",
    ));
    assert!(
        twice
            .upstream
            .iter()
            .any(|reason| reason == "conflicting_fades"),
        "{:?}",
        twice.upstream
    );
}

/// The handling word 薄い is still read as it was, next to a fade.
#[test]
fn a_fade_leaves_the_handling_word_faint_as_it_is() {
    let marks = "赤の細筆の薄い小さな円を5個並べる。";
    let faint = instruction(&format!("{HORIZONTAL}{marks}"));
    let faded = instruction(&format!("{HORIZONTAL}左から右へ薄れさせて、{marks}"));
    assert_eq!(without_fade(faded), without_fade(faint));
}

/// Colors in order that shift give each run of marks one color, in the written
/// order from the first mark; repeating still repeats.
#[test]
fn colors_in_order_shift_once_through_a_row() {
    use Color::{Orange, Red, Yellow};
    let shift = |count: u32| {
        instruction(&format!(
            "{HORIZONTAL}黄・橙・赤の順に段々に移して、小さな円を{count}個並べる。"
        ))
    };
    let nine = shift(9);
    assert_eq!(
        colors(&nine),
        vec![
            Yellow, Yellow, Yellow, Orange, Orange, Orange, Red, Red, Red
        ]
    );
    assert_eq!(nine.color, Yellow);
    assert_eq!(
        colors(&shift(10)),
        vec![
            Yellow, Yellow, Yellow, Yellow, Orange, Orange, Orange, Red, Red, Red
        ]
    );
    assert_eq!(colors(&shift(3)), vec![Yellow, Orange, Red]);
    let english = instruction(
        "Line up 9 small circles in the range horizontal 0.1 to 0.9, vertical 0.45 to 0.55, shifting through yellow, orange, and red in order.",
    );
    assert_eq!(colors(&english), colors(&nine));
    let two = instruction(
        "Line up 4 small circles in the range horizontal 0.1 to 0.9, vertical 0.45 to 0.55, shifting through yellow and red in order.",
    );
    assert_eq!(colors(&two), vec![Yellow, Yellow, Red, Red]);
    let tile = instruction(
        "下の3分の2（横0〜1、縦1/3〜1）に、黄・橙・赤の順に段々に移して、小さな四角を6個敷き詰める。",
    );
    assert_eq!(
        colors(&tile),
        vec![Yellow, Yellow, Orange, Orange, Red, Red]
    );
    let repeating = instruction(&format!(
        "{HORIZONTAL}黄・橙・赤の順に繰り返して、小さな円を9個並べる。"
    ));
    assert_eq!(colors(&repeating), vec![Yellow, Orange, Red]);
}

/// Colors shift along a row or a tile only, and over no fewer marks than
/// colors; a sequence of shapes does not shift.
#[test]
fn colors_that_shift_need_a_row_or_a_tile_and_enough_marks() {
    let scatter = compile(
        "画面全体（横0〜1、縦0〜1）に、黄・橙・赤の順に段々に移して、とても小さな点を30個散らす。",
    );
    assert_eq!(scatter.gaps, vec![ScoreFieldGap::UnsupportedColorShift]);
    let short = compile(&format!(
        "{HORIZONTAL}黄・橙・赤の順に段々に移して、小さな円を2個並べる。"
    ));
    assert_eq!(short.gaps, vec![ScoreFieldGap::ColorShiftLongerThanCount]);
    for source in [
        "赤い円・青い線・灰の弧の順に段々に移して、八つ並べる。",
        "Line up eight, shifting through a red circle, a blue line, and a gray arc in order.",
    ] {
        let shapes = compile(source);
        assert!(
            shapes
                .upstream
                .iter()
                .any(|reason| reason == "shift_needs_colors"),
            "{source}: {:?}",
            shapes.upstream
        );
    }
}

/// A row numbered from its other end for its fade keeps its colors where the
/// row's own order puts them.
#[test]
fn a_reversed_row_keeps_its_colors_where_its_own_order_puts_them() {
    use Color::{Gray, Orange, Red, Yellow};
    let alternating = instruction(&format!(
        "{HORIZONTAL}赤と灰を交互にして、右から左へ薄れさせて、小さな円を4個並べる。"
    ));
    assert_eq!(colors(&alternating), vec![Gray, Red, Gray, Red]);
    let unreversed = instruction(&format!(
        "{HORIZONTAL}赤と灰を交互にして、左から右へ薄れさせて、小さな円を4個並べる。"
    ));
    assert_eq!(colors(&unreversed), vec![Red, Gray]);
    let shifting = instruction(&format!(
        "{HORIZONTAL}黄・橙・赤の順に段々に移して、右から左へ薄れさせて、小さな円を6個並べる。"
    ));
    assert_eq!(
        colors(&shifting),
        vec![Red, Red, Orange, Orange, Yellow, Yellow]
    );
}
