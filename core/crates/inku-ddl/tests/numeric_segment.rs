//! Two points written in numbers (stage B-2a, the author's decision of
//! 2026-10-19): a row puts its first and last mark on them in equal steps, and
//! a line or a free line runs from the first to the second.

use inku_ddl::{
    CompositionPlanOutcome, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreFieldGap,
    ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
    compile_typed_ddl, plan_verified_stage15_with_policy, stage15_transformation_input,
    transform_stage15,
};
use inku_render::{
    checked_performance::resolve_checked_performance_with_resources,
    performance::PerformanceRequest, types::CanvasSize,
};
use inku_score::{
    Color, HardResourcePolicy, Instruction, OperationalResourceBudget, Point,
    ResolvedPlacementAnchor, ResolvedPlacementRecipe, ResourceBudget, ResourceDemand, Score,
};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

const SQUARE: CanvasSize = CanvasSize::new(1000.0, 1000.0);
const WIDE: CanvasSize = CanvasSize::new(2350.0, 1000.0);

/// The budget of a row of at most `per_row` marks.
fn policy(per_row: u64) -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "numeric-segment-test.v1".into(),
        budget: ResourceBudget {
            maximum: ResourceDemand {
                logical_objects: 400,
                primitive_marks: 400,
                object_templates: 64,
                maximum_per_template_primitive_marks: per_row,
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
    outcome: ScoreLoweringOutcome,
    /// None when every instruction was left out.
    score: Option<Score>,
    gaps: Vec<ScoreFieldGap>,
}

fn compile(source: &str, canvas: &str, per_row: u64) -> Compiled {
    let hard = policy(per_row);
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language(source), Vec::new()).unwrap(),
        &[],
        Some(19),
        LIMITS,
        ScoreLoweringContext::resolve(canvas, Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    assert!(
        result.upstream_diagnostics().is_empty(),
        "{source}: {:?}",
        result.upstream_diagnostics()
    );
    Compiled {
        outcome: result.outcome(),
        score: result.score().cloned(),
        gaps: result
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
    }
}

/// The Score of a sentence that compiles whole, but for a count reduced to
/// the budget of `per_row` marks.
fn score(source: &str, canvas: &str, per_row: u64) -> Score {
    let compiled = compile(source, canvas, per_row);
    assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
    if per_row == 240 {
        assert_eq!(compiled.outcome, ScoreLoweringOutcome::Complete, "{source}");
    }
    compiled.score.unwrap_or_else(|| panic!("{source}"))
}

fn resolved(instruction: &Instruction) -> &inku_score::ResolvedArrangement {
    instruction
        .arrangement
        .as_ref()
        .and_then(|arrangement| arrangement.resolved.as_ref())
        .expect("resolved arrangement")
}

fn anchor_point(instruction: &Instruction) -> [f64; 2] {
    let ResolvedPlacementAnchor::Named { region } = resolved(instruction).anchor else {
        panic!("{:?}", resolved(instruction).anchor)
    };
    assert_eq!([region[0], region[1]], [region[2], region[3]]);
    [region[0], region[1]]
}

fn close(actual: f64, expected: f64) {
    assert!((actual - expected).abs() < 1e-9, "{actual} != {expected}");
}

/// The performed Score and where each of its instructions was moved.
fn perform(
    score: &Score,
    canvas: CanvasSize,
    per_row: u64,
) -> inku_render::performance::PerformancePlan {
    let hard = policy(per_row);
    resolve_checked_performance_with_resources(
        PerformanceRequest {
            score,
            performance_seed: Some(7),
            composition_seed: None,
            canvas: Some(canvas),
        },
        ScoreErrorPolicy::Stop,
        &hard,
        OperationalResourceBudget(hard.budget),
    )
    .unwrap()
}

/// Where the renderer puts every mark, in canvas fractions.
fn performed_centers(score: &Score, canvas: CanvasSize, per_row: u64) -> Vec<Point> {
    let performed = perform(score, canvas, per_row);
    performed
        .score
        .instructions
        .iter()
        .enumerate()
        .map(|(index, instruction)| {
            performed.instruction_transforms()[index].apply(instruction.center.unwrap())
        })
        .collect()
}

/// The performed ends of the only line, in canvas fractions.
fn performed_ends(score: &Score, canvas: CanvasSize) -> [Point; 2] {
    let performed = perform(score, canvas, 240);
    assert_eq!(performed.score.instructions.len(), 1);
    let line = &performed.score.instructions[0];
    let transform = performed.instruction_transforms()[0];
    [
        transform.apply(line.from_.unwrap()),
        transform.apply(line.to.unwrap()),
    ]
}

/// The marks of a row land on `from + i (to - from) / (n - 1)`.
fn assert_row(centers: &[Point], from: [f64; 2], to: [f64; 2]) {
    let intervals = (centers.len() - 1) as f64;
    for (index, center) in centers.iter().enumerate() {
        let t = index as f64 / intervals;
        close(center.x, from[0] + (to[0] - from[0]) * t);
        close(center.y, from[1] + (to[1] - from[1]) * t);
    }
}

#[test]
fn an_english_sentence_may_end_its_numbers_in_a_whole_number() {
    // The period right after a whole number ends the sentence (DDL engine 71);
    // it was taken for a decimal point and the numbers were not read.
    for (whole, decimal) in [
        (
            "draw one black thick line from horizontal 0.1, vertical 0.9 to horizontal 0.9, vertical 1.",
            "draw one black thick line from horizontal 0.1, vertical 0.9 to horizontal 0.9, vertical 1.0.",
        ),
        (
            "tile 30 green flat circles diameter 0.03 in the range horizontal 0.0 to 1.0, vertical 0.66 to 1.",
            "tile 30 green flat circles diameter 0.03 in the range horizontal 0.0 to 1.0, vertical 0.66 to 1.0.",
        ),
    ] {
        assert_eq!(
            compile(whole, "square", 240).score,
            compile(decimal, "square", 240).score,
            "{whole}"
        );
    }
}

#[test]
fn a_row_puts_its_first_and_last_mark_on_the_two_points() {
    let row = score(
        "画面の横0.118、縦0.5から横0.882、縦0.5まで、半径0.03の青のロットリングの空の円を5個並べる。",
        "square",
        240,
    );
    let instruction = &row.instructions[0];
    assert_eq!(instruction.arrangement.as_ref().unwrap().count, 5);
    let [x, y] = anchor_point(instruction);
    close(x, 0.5);
    close(y, 0.5);
    let arrangement = resolved(instruction);
    let ResolvedPlacementRecipe::HorizontalLine { cell_width } = arrangement.recipe else {
        panic!("{:?}", arrangement.recipe)
    };
    close(cell_width, 0.191);
    close(arrangement.domain.x, 0.955);
    close(arrangement.domain.y, 1.0);
    let centers = performed_centers(&row, SQUARE, 240);
    assert_eq!(centers.len(), 5);
    assert_row(&centers, [0.118, 0.5], [0.882, 0.5]);

    // The English sentence, with or without the comma, draws the same row.
    for english in [
        "Line up 5 blue rotring empty circles radius 0.03 from horizontal 0.118, vertical 0.5 to horizontal 0.882, vertical 0.5.",
        "line up 5 blue rotring empty circles radius 0.03 from Horizontal 0.118 Vertical 0.5 to horizontal 0.882 vertical 0.5.",
    ] {
        assert_eq!(
            score(english, "square", 240).instructions,
            row.instructions,
            "{english}"
        );
    }

    // A column, written top to bottom.
    let column = score(
        "横0.5、縦0.1から横0.5、縦0.9まで、黒い円を5個並べる。",
        "square",
        240,
    );
    let arrangement = resolved(&column.instructions[0]);
    let ResolvedPlacementRecipe::VerticalLine { cell_height } = arrangement.recipe else {
        panic!("{:?}", arrangement.recipe)
    };
    close(cell_height, 0.2);
    close(arrangement.domain.x, 1.0);
    close(arrangement.domain.y, 1.0);
    assert_row(
        &performed_centers(&column, SQUARE, 240),
        [0.5, 0.1],
        [0.5, 0.9],
    );
}

#[test]
fn a_row_on_any_slope_or_written_backwards_steps_from_the_first_point() {
    for (source, from, to, step) in [
        (
            "画面の横0.1、縦0.1から横0.9、縦0.9まで、黒い円を5個並べる。",
            [0.1, 0.1],
            [0.9, 0.9],
            [0.2, 0.2],
        ),
        (
            "画面の横0.1、縦0.2から横0.9、縦0.6まで、黒い円を4個並べる。",
            [0.1, 0.2],
            [0.9, 0.6],
            [0.8 / 3.0, 0.4 / 3.0],
        ),
        // Rising to the right: y decreases downwards.
        (
            "横1/10、縦9/10から横9/10、縦1/10まで、黒い円を3個並べる。",
            [0.1, 0.9],
            [0.9, 0.1],
            [0.4, -0.4],
        ),
        // Right to left: the first mark is still on the first point.
        (
            "横0.9、縦0.5から横0.1、縦0.5まで、黒い円を5個並べる。",
            [0.9, 0.5],
            [0.1, 0.5],
            [-0.2, 0.0],
        ),
    ] {
        let row = score(source, "square", 240);
        let instruction = &row.instructions[0];
        let arrangement = resolved(instruction);
        let ResolvedPlacementRecipe::DiagonalLine { step: actual } = arrangement.recipe else {
            panic!("{source}: {:?}", arrangement.recipe)
        };
        close(actual.x, step[0]);
        close(actual.y, step[1]);
        close(arrangement.domain.x, 1.0);
        close(arrangement.domain.y, 1.0);
        let [x, y] = anchor_point(instruction);
        close(x, (from[0] + to[0]) / 2.0);
        close(y, (from[1] + to[1]) / 2.0);
        assert_row(&performed_centers(&row, SQUARE, 240), from, to);
    }

    // English writes the same points with `from` and `to`.
    assert_eq!(
        score(
            "line up 4 black circles from horizontal 0.1, vertical 0.2 to horizontal 0.9, vertical 0.6.",
            "square",
            240,
        )
        .instructions,
        score(
            "画面の横0.1、縦0.2から横0.9、縦0.6まで、黒い円を4個並べる。",
            "square",
            240,
        )
        .instructions
    );
}

#[test]
fn on_a_wide_canvas_the_points_stay_canvas_fractions() {
    // Measured on the short side, the row is 0.8 x 2.35 long.
    let row = score(
        "横0.1、縦0.5から横0.9、縦0.5まで、黒い円を5個並べる。",
        "wide",
        240,
    );
    let ResolvedPlacementRecipe::HorizontalLine { cell_width } =
        resolved(&row.instructions[0]).recipe
    else {
        panic!()
    };
    close(cell_width, 0.47);
    assert_row(&performed_centers(&row, WIDE, 240), [0.1, 0.5], [0.9, 0.5]);

    let diagonal = score(
        "横0.1、縦0.1から横0.9、縦0.9まで、黒い円を5個並べる。",
        "wide",
        240,
    );
    let arrangement = resolved(&diagonal.instructions[0]);
    let ResolvedPlacementRecipe::DiagonalLine { step } = arrangement.recipe else {
        panic!()
    };
    close(step.x, 0.47);
    close(step.y, 0.2);
    close(arrangement.domain.x, 2.35);
    close(arrangement.domain.y, 1.0);
    assert_row(
        &performed_centers(&diagonal, WIDE, 240),
        [0.1, 0.1],
        [0.9, 0.9],
    );
}

#[test]
fn a_count_reduced_for_resources_keeps_both_ends() {
    for (source, from, to) in [
        (
            "横0.118、縦0.5から横0.882、縦0.5まで、黒い円を6個並べる。",
            [0.118, 0.5],
            [0.882, 0.5],
        ),
        (
            "横0.1、縦0.9から横0.9、縦0.3まで、黒い円を6個並べる。",
            [0.1, 0.9],
            [0.9, 0.3],
        ),
    ] {
        let row = score(source, "square", 4);
        let instruction = &row.instructions[0];
        assert_eq!(
            instruction.arrangement.as_ref().unwrap().count,
            4,
            "{source}"
        );
        let centers = performed_centers(&row, SQUARE, 4);
        assert_eq!(centers.len(), 4);
        assert_row(&centers, from, to);
    }
    // One mark left sits in the middle.
    let single = score(
        "横0.1、縦0.9から横0.9、縦0.3まで、黒い円を6個並べる。",
        "square",
        1,
    );
    let centers = performed_centers(&single, SQUARE, 1);
    assert_eq!(centers.len(), 1);
    close(centers[0].x, 0.5);
    close(centers[0].y, 0.6);
}

#[test]
fn a_line_and_a_free_line_run_from_the_first_point_to_the_second() {
    for (sources, canvas, size) in [
        (
            [
                "画面の横0.118、縦0.118から横0.882、縦0.882まで、灰の鉛筆の線を1本引く。",
                "draw one gray pencil line from horizontal 0.118, vertical 0.118 to horizontal 0.882, vertical 0.882.",
            ],
            "square",
            SQUARE,
        ),
        (
            [
                "横0.9、縦0.2から横0.3、縦0.7まで、黒い自由線を引く。",
                "draw a black free line from horizontal 0.9, vertical 0.2 to horizontal 0.3, vertical 0.7.",
            ],
            "wide",
            WIDE,
        ),
    ] {
        let japanese = score(sources[0], canvas, 240);
        let line = &japanese.instructions[0];
        assert!(line.rotation.is_none(), "{:?}", line.rotation);
        let english = score(sources[1], canvas, 240);
        assert_eq!(
            english.instructions, japanese.instructions,
            "{}",
            sources[1]
        );
        let numbers: Vec<f64> = sources[0]
            .split(|c: char| !(c.is_ascii_digit() || c == '.'))
            .filter_map(|word| word.parse().ok())
            .take(4)
            .collect();
        let [from, to] = performed_ends(&japanese, size);
        close(from.x, numbers[0]);
        close(from.y, numbers[1]);
        close(to.x, numbers[2]);
        close(to.y, numbers[3]);
    }
}

#[test]
fn what_two_points_cannot_do_is_left_out_with_its_reason() {
    let points = "横0.1、縦0.1から横0.9、縦0.9まで、";
    for (rest, reason) in [
        (
            "赤い円を1個置く。",
            ScoreFieldGap::UnsupportedNumericSegment,
        ),
        (
            "赤い円を1個並べる。",
            ScoreFieldGap::UnsupportedNumericSegment,
        ),
        (
            "赤い円を8個散らす。",
            ScoreFieldGap::UnsupportedNumericSegment,
        ),
        (
            "赤い円を敷き詰める。",
            ScoreFieldGap::UnsupportedNumericSegment,
        ),
        ("赤い円を埋める。", ScoreFieldGap::UnsupportedNumericSegment),
        (
            "赤い弧を1個引く。",
            ScoreFieldGap::UnsupportedNumericSegment,
        ),
        (
            "赤い線を3本引く。",
            ScoreFieldGap::UnsupportedNumericSegment,
        ),
        (
            "長さ0.5の赤い線を1本引く。",
            ScoreFieldGap::NumericSegmentConflict,
        ),
        (
            "全幅の赤い線を1本引く。",
            ScoreFieldGap::NumericSegmentConflict,
        ),
        (
            "斜めの赤い線を1本引く。",
            ScoreFieldGap::NumericSegmentConflict,
        ),
        (
            "赤い円を5個斜めに並べる。",
            ScoreFieldGap::NumericSegmentConflict,
        ),
        (
            "中心に、赤い円を5個並べる。",
            ScoreFieldGap::NamedAndNumericPositionConflict,
        ),
    ] {
        let source = format!("{points}{rest}");
        let compiled = compile(&source, "square", 240);
        assert_eq!(compiled.gaps, vec![reason], "{source}");
        assert!(
            compiled
                .score
                .is_none_or(|score| score.instructions.is_empty()),
            "{source}"
        );
    }
    // A group of marks has no single owner for the points, as for a range.
    for source in [
        "横0.1、縦0.5から横0.9、縦0.5まで、赤い円と青い円を並べる。",
        "赤い円と青い円を、横0.1、縦0.5から横0.9、縦0.5まで並べる。",
    ] {
        let hard = policy(240);
        let result = compile_ddl_to_score_with_resources(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new())
                .unwrap(),
            &[],
            Some(19),
            LIMITS,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            ScoreErrorPolicy::OmitAndContinue,
            hard.clone(),
            OperationalResourceBudget(hard.budget),
        );
        let segment = source.find("横0.1").unwrap();
        assert!(
            result.upstream_diagnostics().iter().any(|diagnostic| {
                diagnostic.reason == "ambiguous_entity_ownership"
                    && diagnostic
                        .span
                        .is_some_and(|span| span.start_byte <= segment && segment < span.end_byte)
            }),
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
    }
}

#[test]
fn points_off_the_canvas_or_one_point_twice_are_not_a_segment() {
    for source in [
        "横0.1、縦0.1から横1.2、縦0.9まで、赤い円を5個並べる。",
        "横0.4、縦0.4から横0.4、縦0.4まで、赤い円を5個並べる。",
        "from horizontal 0.4, vertical 0.4 to horizontal 0.4, vertical 0.4, line up 5 red circles.",
    ] {
        let compilation = compile_typed_ddl(
            NormalizedDdlDocument::new(source, language(source), Vec::new()).unwrap(),
            &[],
            Some(19),
            LIMITS,
        );
        assert!(
            compilation
                .blocking_diagnostics
                .iter()
                .any(|diagnostic| diagnostic.kind == "invalid_numeric_segment"),
            "{source}: {:?}",
            compilation.blocking_diagnostics
        );
    }
    // Two points and one point written for one mark are two positions.
    let source = "横0.1、縦0.1から横0.9、縦0.9まで、画面の横0.5、縦0.5の位置に赤い円を5個並べる。";
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(19),
        LIMITS,
    );
    assert!(
        compilation
            .conflicts
            .iter()
            .any(|conflict| conflict.kind == "conflicting_numeric_positions"),
        "{:?}",
        compilation.conflicts
    );
}

#[test]
fn a_macro_caller_has_nowhere_to_bind_two_points() {
    let definition = MacroDefinition::from_json(
        &json!({
            "schema":"inku.macro-definition.v1", "namespace":"Draw", "heading":"Row", "version":"1.0.0",
            "parameters":{}, "components":{}, "body":[{"op":"emit","binding":null,"fields":{
                "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
                "movement":{"expr":"semantic_ref","category":"movement","id":"line_up"},
                "place":{"expr":"semantic_ref","category":"place","id":"center"},
                "count":{"expr":"integer","value":3}
            }}]
        })
        .to_string(),
    )
    .unwrap();
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "Draw.Row from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5",
            ResolvedInstructionLanguage::En,
            vec![lock],
        )
        .unwrap(),
        std::slice::from_ref(&definition),
        Some(19),
        LIMITS,
    );
    let transformed = transform_stage15(
        stage15_transformation_input(&compilation)
            .unwrap_or_else(|error| panic!("{error:?}: {:?}", compilation.blocking_diagnostics)),
    )
    .unwrap();
    let result = plan_verified_stage15_with_policy(
        transformed.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(result.outcome(), CompositionPlanOutcome::Stopped);
    assert!(
        result
            .diagnostics()
            .iter()
            .any(|diagnostic| diagnostic.reason == ScoreFieldGap::UnboundMacroCallerMeaning),
        "{:?}",
        result.diagnostics()
    );
}
