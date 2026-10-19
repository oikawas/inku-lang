//! A line-up of several marks over a range runs on the chord that the line
//! through the range's center, along the row, cuts across the canvas (the
//! author's decision of 2026-10-19). A row as long as the canvas around an
//! off-center range put marks off the canvas.

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreLoweringContext, compile_ddl_to_score_with_resources,
};
use inku_render::{
    checked_performance::resolve_checked_performance_with_resources,
    performance::PerformanceRequest, types::CanvasSize,
};
use inku_score::{
    Color, HardResourcePolicy, Instruction, OperationalResourceBudget, Point,
    ResolvedPlacementAnchor, ResolvedPlacementRecipe, ResourceBudget, ResourceDemand, Score,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

/// The budget of a row of at most `per_row` marks.
fn policy(per_row: u64) -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "line-up-chord-test.v1".into(),
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

fn score(source: &str, language: ResolvedInstructionLanguage, canvas: &str, per_row: u64) -> Score {
    let hard = policy(per_row);
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(19),
        LIMITS,
        ScoreLoweringContext::resolve(canvas, Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    assert!(
        result.failure().is_none(),
        "{source}: {:?}",
        result.failure()
    );
    result.score().unwrap_or_else(|| panic!("{source}")).clone()
}

fn ja(source: &str, canvas: &str) -> Score {
    score(source, ResolvedInstructionLanguage::Ja, canvas, 240)
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
    assert!((actual - expected).abs() < 1e-12, "{actual} != {expected}");
}

/// Where the renderer puts every mark, in canvas fractions, under the budget
/// the score was compiled with.
fn performed_centers(score: &Score, canvas: CanvasSize, per_row: u64) -> Vec<Point> {
    let hard = policy(per_row);
    let performed = resolve_checked_performance_with_resources(
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
    .unwrap();
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

fn assert_on_canvas(centers: &[Point]) {
    for center in centers {
        assert!(
            (0.0..=1.0).contains(&center.x) && (0.0..=1.0).contains(&center.y),
            "{center:?} in {centers:?}"
        );
    }
}

#[test]
fn a_row_at_a_corner_moves_to_the_canvas_center_along_itself() {
    let square = CanvasSize::new(1000.0, 1000.0);
    let row = ja(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を5個横に並べる。",
        "square",
    );
    let instruction = &row.instructions[0];
    let [x, y] = anchor_point(instruction);
    close(x, 0.5);
    close(y, 1.0 / 6.0);
    assert_eq!(
        resolved(instruction).recipe,
        ResolvedPlacementRecipe::HorizontalLine { cell_width: 0.2 }
    );
    let centers = performed_centers(&row, square, 240);
    for (center, expected) in centers.iter().zip([0.1, 0.3, 0.5, 0.7, 0.9]) {
        close(center.x, expected);
        close(center.y, 1.0 / 6.0);
    }

    let column = ja(
        "左下（横0〜1/3、縦2/3〜1）に、黒い円を4個縦に並べる。",
        "square",
    );
    let instruction = &column.instructions[0];
    let [x, y] = anchor_point(instruction);
    close(x, 1.0 / 6.0);
    close(y, 0.5);
    assert_eq!(
        resolved(instruction).recipe,
        ResolvedPlacementRecipe::VerticalLine { cell_height: 0.25 }
    );
    assert_on_canvas(&performed_centers(&column, square, 240));

    // The English sentence draws the same row.
    let english = score(
        "line up five black circles horizontally at the top right (horizontal 2/3 to 1, vertical 0 to 1/3).",
        ResolvedInstructionLanguage::En,
        "square",
        240,
    );
    assert_eq!(
        resolved(&english.instructions[0]),
        resolved(&row.instructions[0])
    );

    // On a wide canvas the row still spans the canvas width in equal cells.
    let wide = ja(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を5個横に並べる。",
        "wide",
    );
    let instruction = &wide.instructions[0];
    close(anchor_point(instruction)[0], 0.5);
    let ResolvedPlacementRecipe::HorizontalLine { cell_width } = resolved(instruction).recipe
    else {
        panic!()
    };
    close(cell_width, 47.0 / 100.0);
    let centers = performed_centers(&wide, CanvasSize::new(2350.0, 1000.0), 240);
    for (center, expected) in centers.iter().zip([0.1, 0.3, 0.5, 0.7, 0.9]) {
        close(center.x, expected);
    }
}

#[test]
fn a_diagonal_row_runs_its_chord_and_shortens_its_step() {
    let square = CanvasSize::new(1000.0, 1000.0);
    // Falling through the top-right cell's center, the chord runs from
    // (2/3, 0) to (1, 1/3): the center stays and the step is a third over 4.
    let falling = ja(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を4個右下がりに並べる。",
        "square",
    );
    let instruction = &falling.instructions[0];
    let [x, y] = anchor_point(instruction);
    close(x, 5.0 / 6.0);
    close(y, 1.0 / 6.0);
    let arrangement = resolved(instruction);
    close(arrangement.domain.x, 1.0 / 3.0);
    close(arrangement.domain.y, 1.0 / 3.0);
    let ResolvedPlacementRecipe::DiagonalLine { step } = arrangement.recipe else {
        panic!()
    };
    close(step.x, 1.0 / 12.0);
    close(step.y, 1.0 / 12.0);
    let centers = performed_centers(&falling, square, 240);
    for (index, center) in centers.iter().enumerate() {
        close(center.x, 2.0 / 3.0 + (index as f64 + 0.5) / 12.0);
        close(center.y, (index as f64 + 0.5) / 12.0);
    }

    // Rising through the same center, the chord is the whole other diagonal.
    let rising = ja(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を4個右上がりに並べる。",
        "square",
    );
    let instruction = &rising.instructions[0];
    let [x, y] = anchor_point(instruction);
    close(x, 0.5);
    close(y, 0.5);
    let ResolvedPlacementRecipe::DiagonalLine { step } = resolved(instruction).recipe else {
        panic!()
    };
    close(step.x, 0.25);
    close(step.y, -0.25);
    assert_on_canvas(&performed_centers(&rising, square, 240));

    // A position word: falling through the top third's center (1/2, 1/6).
    let top = ja("上に、黒い円を4個右下がりに並べる。", "square");
    let [x, y] = anchor_point(&top.instructions[0]);
    close(x, 2.0 / 3.0);
    close(y, 1.0 / 3.0);
    assert_on_canvas(&performed_centers(&top, square, 240));

    // On a wide canvas, measured on its short side, the rising chord through
    // (47/24, 1/6) is the short side long and its middle is (13/8, 1/2).
    let wide = ja(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を4個右上がりに並べる。",
        "wide",
    );
    let instruction = &wide.instructions[0];
    let [x, y] = anchor_point(instruction);
    close(x, 65.0 / 94.0);
    close(y, 0.5);
    close(resolved(instruction).domain.x, 47.0 / 20.0);
    close(resolved(instruction).domain.y, 1.0);
    assert_on_canvas(&performed_centers(
        &wide,
        CanvasSize::new(2350.0, 1000.0),
        240,
    ));
}

#[test]
fn a_row_through_the_canvas_center_and_a_single_mark_stay() {
    let row = ja("中心に、黒い円を5個横に並べる。", "square");
    assert_eq!(anchor_point(&row.instructions[0]), [0.5, 0.5]);
    assert_eq!(
        resolved(&row.instructions[0]).recipe,
        ResolvedPlacementRecipe::HorizontalLine { cell_width: 0.2 }
    );
    let diagonal = ja("中心に、黒い円を5個右下がりに並べる。", "square");
    let arrangement = resolved(&diagonal.instructions[0]);
    assert_eq!(anchor_point(&diagonal.instructions[0]), [0.5, 0.5]);
    assert_eq!((arrangement.domain.x, arrangement.domain.y), (1.0, 1.0));
    assert_eq!(
        arrangement.recipe,
        ResolvedPlacementRecipe::DiagonalLine {
            step: Point::new(0.2, 0.2)
        }
    );
    // A row of one mark anchors in the shrunk range around its center.
    let single = ja(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を1個並べる。",
        "square",
    );
    let ResolvedPlacementAnchor::Named { region } = resolved(&single.instructions[0]).anchor else {
        panic!()
    };
    assert!(region[0] < region[2] && region[1] < region[3]);
    close((region[0] + region[2]) / 2.0, 5.0 / 6.0);
    close((region[1] + region[3]) / 2.0, 1.0 / 6.0);
}

#[test]
fn a_count_reduced_for_resources_keeps_the_chord() {
    let square = CanvasSize::new(1000.0, 1000.0);
    let row = score(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を6個横に並べる。",
        ResolvedInstructionLanguage::Ja,
        "square",
        4,
    );
    let instruction = &row.instructions[0];
    assert_eq!(instruction.arrangement.as_ref().unwrap().count, 4);
    close(anchor_point(instruction)[0], 0.5);
    assert_eq!(
        resolved(instruction).recipe,
        ResolvedPlacementRecipe::HorizontalLine { cell_width: 0.25 }
    );
    assert_on_canvas(&performed_centers(&row, square, 4));

    let diagonal = score(
        "右上（横2/3〜1、縦0〜1/3）に、黒い円を6個右下がりに並べる。",
        ResolvedInstructionLanguage::Ja,
        "square",
        4,
    );
    let instruction = &diagonal.instructions[0];
    assert_eq!(instruction.arrangement.as_ref().unwrap().count, 4);
    let ResolvedPlacementRecipe::DiagonalLine { step } = resolved(instruction).recipe else {
        panic!()
    };
    close(step.x, 1.0 / 12.0);
    close(step.y, 1.0 / 12.0);
    assert_on_canvas(&performed_centers(&diagonal, square, 4));
}
