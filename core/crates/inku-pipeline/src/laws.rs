//! The laws stage (`choose_laws`), stages B-2c and B-3 of the laws port (the
//! author's decisions of 2026-10-19: the laws are written in numbers, after the
//! composition, and stay off until every law is in).
//!
//! After the composition places a plan's layers, a reader chooses laws of
//! painting, design and music for the work and the values each law takes; it
//! writes no coordinates. The core applies the laws to a copy of the composed
//! document's Score as the prototype did, and prints the layers the laws
//! changed again in numbers: a numeric point, the two ends of a row or a line,
//! a numeric range, a numeric size. Every other layer keeps the bytes the
//! composition printed. A layer progression or beat groups open into marks is
//! printed one sentence per mark. The prototype let the canvas cut a mark; a
//! mark at a numeric point lies wholly on it, so a line is printed by the ends
//! the canvas shows, a pair as a row of two (whose marks the canvas may cut),
//! and another mark that leaves the canvas is refused ([`off_canvas`]).
//!
//! This stage holds the placement, size, arrangement and hand laws (B1 to B10,
//! B12, B15, B21) and the cards (C1 to C6, stage B-4b). The computation is the
//! prototype's, function by function and in its order, with two departures: a
//! grid takes the columns and rows the core tiles its range with (the printed
//! tile is drawn so), and a layer an arrangement law spaces that would need a
//! shrink below the floor keeps its size (the author's dense layer). The cards
//! come after the fit to spacing and rebuild their layers, which are printed
//! one sentence per instruction, with the departures the DDL needs: a pattern's
//! cells are exact squares on the canvas's micro-lattice (so the core tiles the
//! printed range as counted), seigaiha's grids and kikko's one-row tiles stay
//! inside their range, one grid draws at most what one instruction may, each
//! polyrhythm voice is drawn where its layer is, and a jo-ha-kyu row keeps its
//! direction. A pair B8 opens whose marks turn is printed as two marks with
//! their mirrored turns. On a square canvas it is otherwise the prototype's to
//! the bit; on another canvas, places stay canvas fractions and lengths compared
//! with mark sizes are taken in short-edge units (the prototype ran on square
//! canvases only).

use std::collections::{BTreeMap, BTreeSet};

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{
    ComposedRange, NumericPlace, NumericSize, NumericWriting, WorkPlan, WorkPlanPlugin,
    WorkPlanSlot, print_work_plan_with_numbers,
};
use inku_score::{
    Amplitude, Color, Frequency, Instruction, Primitive, ResolvedPlacementAnchor,
    ResolvedPlacementRecipe, RhythmSpacing, Score, ScoreSourceOwner, lookup_canvas_format,
};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::composition::hypot;
use crate::core_boundary::ResolvedPaletteDto;
use crate::prompts::{LlmPrompt, LlmStage, PromptError, PromptLimits};

/// The laws request edition.
pub const LAWS_PROMPT_ID: &str = "inku.laws-prompt.v1";

/// The laws this core applies, in the order the request lists them.
pub const LAWS: [&str; 19] = [
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B12", "B15", "B21", "C1", "C2",
    "C3", "C4", "C5", "C6",
];

/// The cards, which rebuild a layer's place and arrangement: a layer they take
/// takes no other placement or arrangement law and no other card.
const REBUILD: [&str; 6] = ["C1", "C2", "C3", "C4", "C5", "C6"];

/// One instruction draws this many marks at most (the shipping hard policy's
/// marks per instruction); a pattern's unit widens until each grid fits.
const MAX_PER_INSTRUCTION: u64 = 240;

/// The laws that set a layer's place; a layer takes one of them at most.
const PLACEMENT: [&str; 7] = ["B1", "B2", "B3", "B4", "B5", "B7", "B8"];

/// The laws that arrange a layer's marks; a layer takes one of them at most,
/// and its marks are kept apart (R1).
const ARRANGEMENT: [&str; 3] = ["B9", "B10", "B12"];

/// The Score the laws leave holds this many instructions and marks at most.
const MAX_INSTRUCTIONS: usize = 60;
const MAX_MARKS: u64 = 380;

/// The prototype's values of `PHI = (1 + 5 ** 0.5) / 2`, as Python computed them.
const PHI: f64 = 1.618_033_988_749_895;
const SQRT_PHI: f64 = 1.272_019_649_514_069;
const PHI_SQUARED: f64 = 2.618_033_988_749_895;
const INVERSE_PHI: f64 = 0.618_033_988_749_894_8;
/// The golden section `1 / PHI ** 2`.
const GOLDEN: f64 = 0.381_966_011_250_105_15;
/// The silver section `1 / (1 + 2 ** 0.5)`.
const SILVER: f64 = 0.414_213_562_373_095_1;
/// Aerial perspective's shrink `PHI ** -0.5`.
const AERIAL: f64 = 0.786_151_377_757_423_3;
/// A full-width line keeps this margin from the edges.
const MARGIN: f64 = 0.118;
/// A moved center stays this far inside the canvas.
const EDGE: f64 = 0.06;
/// A shrunk mark is this ratio of its spacing, and never below the floor.
const FIT_TARGET: f64 = 0.8;
const FIT_FLOOR: f64 = 0.25;
/// A stretched arrangement stays inside this frame.
const INNER: (f64, f64) = (0.118, 0.882);
/// A recolored layer and the ground must differ this much in lightness.
const VISIBLE: f64 = 0.15;
/// Aerial perspective keeps a cool color or gray this far from the ground.
const AERIAL_DIFFERENCE: f64 = 0.2;
/// The cool colors and gray aerial perspective chooses from, in its order.
const AERIAL_COLORS: [Color; 4] = [Color::Blue, Color::Green, Color::Purple, Color::Gray];
/// `2 ** 0.5` (std's), `3 ** 0.5` and `3 ** 0.5 / 2`, as Python computed them.
const SQRT_2: f64 = std::f64::consts::SQRT_2;
const SQRT_3: f64 = 1.732_050_807_568_877_2;
const HALF_SQRT_3: f64 = 0.866_025_403_784_438_6;
/// The nine colors in the order the request's table lists them.
pub(crate) const COLORS: [Color; 9] = [
    Color::White,
    Color::Black,
    Color::Blue,
    Color::Red,
    Color::Green,
    Color::Gray,
    Color::Yellow,
    Color::Orange,
    Color::Purple,
];

const LINE: [Primitive; 2] = [Primitive::Line, Primitive::FreeLine];
/// The closed shapes and the arc: what subordination sizes.
pub(crate) const SIZED: [Primitive; 7] = [
    Primitive::Circle,
    Primitive::Ellipse,
    Primitive::Triangle,
    Primitive::Square,
    Primitive::Polygon,
    Primitive::Cloudform,
    Primitive::Arc,
];

pub(crate) fn is_line(primitive: Primitive) -> bool {
    LINE.contains(&primitive)
}

/// Python's `max(a, b)` and `min(a, b)`: the first argument unless the second
/// is strictly larger (smaller). A signed zero is kept as Python keeps it.
pub(crate) fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

pub(crate) fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

pub(crate) fn clamp_between(value: f64, low: f64, high: f64) -> f64 {
    py_max(low, py_min(high, value))
}

/// A moved center stays inside the canvas by `EDGE`.
fn clamp(value: f64) -> f64 {
    clamp_between(value, EDGE, 1.0 - EDGE)
}

/// Python's `round(value, 3)`: the binary value correctly rounded to three
/// decimals, a tie to even (Rust's fixed-precision formatting does the same).
pub(crate) fn round3(value: f64) -> f64 {
    format!("{value:.3}").parse().unwrap_or(value)
}

/// Python's `round(value, 2)`.
pub(crate) fn round2(value: f64) -> f64 {
    format!("{value:.2}").parse().unwrap_or(value)
}

/// Python's `round(value)`: the nearest integer, a tie to even.
#[allow(clippy::cast_possible_truncation)]
pub(crate) fn round_int(value: f64) -> i64 {
    value.round_ties_even() as i64
}

/// The canvas in short-edge units: the width and height over the short edge,
/// with the canvas's integer ratio.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Units {
    pub(crate) x: f64,
    pub(crate) y: f64,
    width: u32,
    height: u32,
}

impl Units {
    pub(crate) fn of(canvas_format_id: &str) -> Option<Self> {
        let format = lookup_canvas_format(canvas_format_id).ok()?;
        let short = f64::from(format.width_units.min(format.height_units));
        Some(Self {
            x: f64::from(format.width_units) / short,
            y: f64::from(format.height_units) / short,
            width: format.width_units,
            height: format.height_units,
        })
    }

    /// The micro-lattice an exact square cell lies on: `t` x-steps of a
    /// millionth by `t` y-steps measure `t` physical steps of a millionth of
    /// the short edge each way. Returns the x step, the y step and the
    /// physical step.
    fn lattice(self) -> (u64, u64, u64) {
        let (mut a, mut b) = (u64::from(self.width), u64::from(self.height));
        while b != 0 {
            (a, b) = (b, a % b);
        }
        let g = a.max(1);
        (
            u64::from(self.height) / g,
            u64::from(self.width) / g,
            u64::from(self.width.max(self.height)) / g,
        )
    }

    /// The length of a step in canvas fractions, in short-edge units.
    fn length(self, dx: f64, dy: f64) -> f64 {
        hypot(dx * self.x, dy * self.y)
    }

    fn distance(self, p: [f64; 2], q: [f64; 2]) -> f64 {
        self.length(q[0] - p[0], q[1] - p[1])
    }
}

// --- reading a Score ---------------------------------------------------------------------------

/// How an instruction belongs to its layer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Belongs {
    Source,
    Plugin,
}

/// The source layer an instruction draws: its own sentence, or the sentence of
/// the plugin word that emitted it.
pub(crate) fn layer_of(instruction: &Instruction) -> Option<(usize, Belongs)> {
    match &resolved(instruction)?.owner {
        ScoreSourceOwner::MacroEmit {
            source_instruction_index,
            ..
        } => Some((*source_instruction_index, Belongs::Plugin)),
        ScoreSourceOwner::SourceInstruction { instruction_index } => {
            Some((*instruction_index, Belongs::Source))
        }
        ScoreSourceOwner::OrdinaryGroup { .. } => None,
    }
}

/// Layer index to the positions of its instructions, in drawing order.
pub(crate) fn layers(score: &Score) -> BTreeMap<usize, Vec<usize>> {
    let mut found: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for (position, instruction) in score.instructions.iter().enumerate() {
        if let Some((index, _)) = layer_of(instruction) {
            found.entry(index).or_default().push(position);
        }
    }
    found
}

pub(crate) fn resolved(instruction: &Instruction) -> Option<&inku_score::ResolvedArrangement> {
    instruction.arrangement.as_ref()?.resolved.as_ref()
}

pub(crate) fn recipe(instruction: &Instruction) -> Option<&ResolvedPlacementRecipe> {
    resolved(instruction).map(|resolved| &resolved.recipe)
}

pub(crate) fn count_of(instruction: &Instruction) -> u32 {
    match instruction
        .arrangement
        .as_ref()
        .map(|arrangement| arrangement.count)
    {
        None | Some(0) => 1,
        Some(count) => count,
    }
}

pub(crate) fn is_row_recipe(instruction: &Instruction) -> bool {
    matches!(
        recipe(instruction),
        Some(
            ResolvedPlacementRecipe::HorizontalLine { .. }
                | ResolvedPlacementRecipe::VerticalLine { .. }
                | ResolvedPlacementRecipe::DiagonalLine { .. }
        )
    )
}

pub(crate) fn is_row(instruction: &Instruction) -> bool {
    is_row_recipe(instruction) && count_of(instruction) >= 2
}

pub(crate) fn is_scatter(instruction: &Instruction) -> bool {
    matches!(
        recipe(instruction),
        Some(ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation)
    )
}

/// The named region of the anchor, else the instruction's region.
pub(crate) fn anchor_region(instruction: &Instruction) -> Option<[f64; 4]> {
    match resolved(instruction).map(|resolved| &resolved.anchor) {
        Some(ResolvedPlacementAnchor::Named { region }) => Some(*region),
        _ => instruction.at.as_ref().map(|at| at.region),
    }
}

fn region_or_center(instruction: &Instruction) -> [f64; 4] {
    anchor_region(instruction).unwrap_or([0.5; 4])
}

pub(crate) fn center_of(instruction: &Instruction) -> [f64; 2] {
    let region = region_or_center(instruction);
    [(region[0] + region[2]) / 2.0, (region[1] + region[3]) / 2.0]
}

fn domain_of(instruction: &Instruction) -> Option<[f64; 2]> {
    resolved(instruction).map(|resolved| [resolved.domain.x, resolved.domain.y])
}

/// Half the width and height of one mark, in short-edge units.
pub(crate) fn extent(instruction: &Instruction, units: Units) -> (f64, f64) {
    if let Some(size) = instruction.size {
        return (size.x / 2.0, size.y / 2.0);
    }
    if let Some(radius) = instruction.radius {
        return (radius, radius);
    }
    if let (Some(from), Some(to)) = (instruction.from_, instruction.to) {
        return (
            (to.x - from.x).abs() / 2.0 * units.x,
            (to.y - from.y).abs() / 2.0 * units.y,
        );
    }
    (0.01, 0.01)
}

pub(crate) fn largest_extent(instruction: &Instruction, units: Units) -> f64 {
    let (x, y) = extent(instruction, units);
    py_max(x, y)
}

/// The box an instruction's marks cover, in canvas fractions (approximate:
/// the anchor, the arrangement's spread and one mark's extent).
fn mark_box(instruction: &Instruction, units: Units) -> [f64; 4] {
    let [mut x0, mut y0, mut x1, mut y1] = region_or_center(instruction);
    let (hx, hy) = extent(instruction, units);
    let spread = match recipe(instruction) {
        Some(ResolvedPlacementRecipe::DiagonalLine { step }) => {
            let steps = f64::from(count_of(instruction) - 1);
            Some([step.x.abs() * steps, step.y.abs() * steps])
        }
        Some(
            ResolvedPlacementRecipe::HorizontalLine { .. }
            | ResolvedPlacementRecipe::VerticalLine { .. }
            | ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation,
        ) => Some(domain_of(instruction).unwrap_or([0.0, 0.0])),
        _ => None,
    };
    if let Some([dx, dy]) = spread {
        let (dx, dy) = (dx / units.x, dy / units.y);
        let (cx, cy) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
        (x0, x1, y0, y1) = (cx - dx / 2.0, cx + dx / 2.0, cy - dy / 2.0, cy + dy / 2.0);
    }
    [
        py_max(0.0, x0 - hx / units.x),
        py_max(0.0, y0 - hy / units.y),
        py_min(1.0, x1 + hx / units.x),
        py_min(1.0, y1 + hy / units.y),
    ]
}

/// Where an instruction's marks are, in canvas fractions; `None` for a seeded
/// arrangement (a scatter).
pub(crate) fn mark_centers(instruction: &Instruction, units: Units) -> Option<Vec<[f64; 2]>> {
    let [x0, y0, x1, y1] = region_or_center(instruction);
    let (cx, cy) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    let count = count_of(instruction);
    let n = f64::from(count);
    match recipe(instruction)? {
        ResolvedPlacementRecipe::Place => Some(vec![[cx, cy]]),
        ResolvedPlacementRecipe::Grid {
            columns,
            rows,
            filled_count,
            ..
        } => {
            let (cw, ch) = ((x1 - x0) / *columns as f64, (y1 - y0) / *rows as f64);
            let mut cells = Vec::new();
            for j in 0..*rows {
                for i in 0..*columns {
                    cells.push([x0 + cw * (i as f64 + 0.5), y0 + ch * (j as f64 + 0.5)]);
                }
            }
            cells.truncate(usize::try_from(*filled_count).unwrap_or(usize::MAX));
            Some(cells)
        }
        ResolvedPlacementRecipe::HorizontalLine { .. } => {
            let width = domain_of(instruction)?[0] / units.x;
            Some(
                (0..count)
                    .map(|j| [cx - width / 2.0 + width / n * (f64::from(j) + 0.5), cy])
                    .collect(),
            )
        }
        ResolvedPlacementRecipe::VerticalLine { .. } => {
            let height = domain_of(instruction)?[1] / units.y;
            Some(
                (0..count)
                    .map(|j| [cx, cy - height / 2.0 + height / n * (f64::from(j) + 0.5)])
                    .collect(),
            )
        }
        ResolvedPlacementRecipe::DiagonalLine { step } => {
            let (sx, sy) = (step.x / units.x, step.y / units.y);
            let middle = (n - 1.0) / 2.0;
            Some(
                (0..count)
                    .map(|j| {
                        [
                            cx + (f64::from(j) - middle) * sx,
                            cy + (f64::from(j) - middle) * sy,
                        ]
                    })
                    .collect(),
            )
        }
        _ => None,
    }
}

/// The two ends of the line an arrangement lies along now, in canvas fractions:
/// a row's first and last centers, else the long side of its region (or a
/// scatter's spread) through its center.
fn current_span(instruction: &Instruction, units: Units) -> ([f64; 2], [f64; 2]) {
    if is_row(instruction)
        && let Some(centers) = mark_centers(instruction, units)
        && let (Some(first), Some(last)) = (centers.first(), centers.last())
    {
        return (*first, *last);
    }
    let region = region_or_center(instruction);
    let (cx, cy) = ((region[0] + region[2]) / 2.0, (region[1] + region[3]) / 2.0);
    let (w, h) = if is_scatter(instruction) {
        let [w, h] = domain_of(instruction).unwrap_or([0.5, 0.5]);
        (w / units.x, h / units.y)
    } else if region[2] - region[0] > 1e-6 || region[3] - region[1] > 1e-6 {
        (region[2] - region[0], region[3] - region[1])
    } else {
        let run = f64::from(count_of(instruction)) * 1.6 * 2.0 * largest_extent(instruction, units);
        (py_min(1.0 - 2.0 * MARGIN, run / units.x), 0.0)
    };
    if w * units.x >= h * units.y {
        ([clamp(cx - w / 2.0), cy], [clamp(cx + w / 2.0), cy])
    } else {
        ([cx, clamp(cy - h / 2.0)], [cx, clamp(cy + h / 2.0)])
    }
}

/// A line's length in short-edge units, or a mark's width when it has no ends.
fn line_length(instruction: &Instruction, units: Units) -> f64 {
    match (instruction.from_, instruction.to) {
        (Some(from), Some(to)) => units.distance([from.x, from.y], [to.x, to.y]),
        _ => 2.0 * largest_extent(instruction, units),
    }
}

// --- writing a Score copy, as the prototype's tools wrote theirs ------------------------------

pub(crate) fn resolved_mut(
    instruction: &mut Instruction,
) -> Option<&mut inku_score::ResolvedArrangement> {
    instruction.arrangement.as_mut()?.resolved.as_mut()
}

pub(crate) fn set_point_region(instruction: &mut Instruction, x: f64, y: f64) {
    let region = [x, y, x, y];
    instruction.at = Some(inku_score::AtRegion { region });
    if let Some(resolved) = resolved_mut(instruction) {
        resolved.anchor = ResolvedPlacementAnchor::Named { region };
    }
}

/// A law decides the position; a relation would move it again when drawn.
fn moved(instruction: &mut Instruction) {
    instruction.relation = None;
}

/// Lay a row's marks from the first center to the last on a line recipe.
fn apply_row(instruction: &mut Instruction, from: [f64; 2], to: [f64; 2], units: Units) {
    let count = count_of(instruction);
    let n = f64::from(count);
    let ([x0, y0], [x1, y1]) = (from, to);
    let (mx, my) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    set_point_region(instruction, mx, my);
    let (domain, row) = if (y1 - y0).abs() < 1e-9 {
        let width = (x1 - x0).abs() * n / (n - 1.0) * units.x;
        (
            inku_score::Point::new(width, units.y),
            ResolvedPlacementRecipe::HorizontalLine {
                cell_width: width / n,
            },
        )
    } else if (x1 - x0).abs() < 1e-9 {
        let height = (y1 - y0).abs() * n / (n - 1.0) * units.y;
        (
            inku_score::Point::new(units.x, height),
            ResolvedPlacementRecipe::VerticalLine {
                cell_height: height / n,
            },
        )
    } else {
        (
            inku_score::Point::new(units.x, units.y),
            ResolvedPlacementRecipe::DiagonalLine {
                step: inku_score::Point::new(
                    (x1 - x0) * units.x / (n - 1.0),
                    (y1 - y0) * units.y / (n - 1.0),
                ),
            },
        )
    };
    if let Some(resolved) = resolved_mut(instruction) {
        resolved.domain = domain;
        resolved.recipe = row;
    }
    if let Some(arrangement) = instruction.arrangement.as_mut() {
        arrangement.rhythm_spacing = RhythmSpacing::None;
    }
}

/// Lay one line along a segment: its anchor at the middle, its ends about it.
fn apply_line(instruction: &mut Instruction, from: [f64; 2], to: [f64; 2]) {
    let ([x0, y0], [x1, y1]) = (from, to);
    let (mx, my) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    set_point_region(instruction, mx, my);
    instruction.from_ = Some(inku_score::Point::new(0.5 + x0 - mx, 0.5 + y0 - my));
    instruction.to = Some(inku_score::Point::new(0.5 + x1 - mx, 0.5 + y1 - my));
    instruction.rotation = Some(0.0);
}

pub(crate) fn scale_geometry(instruction: &mut Instruction, factor: f64) {
    #[allow(clippy::float_cmp)]
    if factor == 1.0 {
        return;
    }
    if let Some(size) = instruction.size.as_mut() {
        size.x *= factor;
        size.y *= factor;
    }
    if let Some(radius) = instruction.radius.as_mut() {
        *radius *= factor;
    }
    if instruction.primitive == Primitive::Arc
        && let Some(center) = instruction.center.as_mut()
    {
        let origin = instruction
            .position
            .unwrap_or(inku_score::Point::new(0.5, 0.5));
        center.x = origin.x + (center.x - origin.x) * factor;
        center.y = origin.y + (center.y - origin.y) * factor;
    }
    for end in [instruction.from_.as_mut(), instruction.to.as_mut()]
        .into_iter()
        .flatten()
    {
        end.x = 0.5 + (end.x - 0.5) * factor;
        end.y = 0.5 + (end.y - 0.5) * factor;
    }
}

/// The hand B21 chooses for a layer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Hand {
    Still,
    Fine,
    Keep,
}

impl Hand {
    fn parse(value: &str) -> Option<Self> {
        match value {
            "still" => Some(Self::Still),
            "fine" => Some(Self::Fine),
            "keep" => Some(Self::Keep),
            _ => None,
        }
    }
}

fn set_hand(instruction: &mut Instruction, hand: Hand) {
    match hand {
        Hand::Keep => {}
        Hand::Still => {
            instruction.variation = None;
            if let Some(arrangement) = instruction.arrangement.as_mut() {
                arrangement.jitter = 0.0;
            }
        }
        Hand::Fine => {
            if let Some(variation) = instruction.variation.as_mut() {
                variation.amplitude = Amplitude::Fine;
                variation.frequency = Frequency::Slow;
            }
            if let Some(arrangement) = instruction.arrangement.as_mut() {
                arrangement.jitter = py_min(arrangement.jitter, 0.05);
            }
        }
    }
}

/// Move an arrangement's center to a point, keeping its recipe: a grid keeps
/// its cells, a scatter its spread as far as the canvas allows.
fn translate(instruction: &mut Instruction, point: [f64; 2], units: Units) {
    moved(instruction);
    if let Some(ResolvedPlacementRecipe::Grid { columns, rows, .. }) = recipe(instruction).cloned()
    {
        let [x0, y0, x1, y1] = region_or_center(instruction);
        let (w, h) = (x1 - x0, y1 - y0);
        let cx = if w < 1.0 {
            clamp_between(point[0], w / 2.0, 1.0 - w / 2.0)
        } else {
            0.5
        };
        let cy = if h < 1.0 {
            clamp_between(point[1], h / 2.0, 1.0 - h / 2.0)
        } else {
            0.5
        };
        let region = [cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0];
        build_grid(instruction, region, columns, rows, units);
        return;
    }
    let (x, y) = (clamp(point[0]), clamp(point[1]));
    set_point_region(instruction, x, y);
    if is_scatter(instruction)
        && let Some(resolved) = resolved_mut(instruction)
    {
        let (w, h) = (resolved.domain.x, resolved.domain.y);
        resolved.domain = inku_score::Point::new(
            py_min(w, 2.0 * py_min(x, 1.0 - x) * units.x),
            py_min(h, 2.0 * py_min(y, 1.0 - y) * units.y),
        );
    }
}

/// A grid recipe over a region; the last row may be partly filled. Its cells
/// and centroid are in short-edge units, the centroid measured from the
/// domain's corner, as the core tiles them (`score_lowering.rs`).
fn build_grid(
    instruction: &mut Instruction,
    region: [f64; 4],
    columns: u64,
    rows: u64,
    units: Units,
) {
    let count = count_of(instruction);
    let [x0, y0, x1, y1] = region;
    let domain = inku_score::Point::new((x1 - x0) * units.x, (y1 - y0) * units.y);
    let (cw, ch) = (domain.x / columns as f64, domain.y / rows as f64);
    let mut cells = Vec::new();
    for j in 0..rows {
        for i in 0..columns {
            cells.push([cw * (i as f64 + 0.5), ch * (j as f64 + 0.5)]);
        }
    }
    cells.truncate(count as usize);
    let n = f64::from(count);
    let centroid = inku_score::Point::new(
        cells.iter().fold(0.0, |sum, cell| sum + cell[0]) / n,
        cells.iter().fold(0.0, |sum, cell| sum + cell[1]) / n,
    );
    instruction.at = Some(inku_score::AtRegion { region });
    if let Some(resolved) = resolved_mut(instruction) {
        resolved.anchor = ResolvedPlacementAnchor::Named { region };
        resolved.domain = domain;
        resolved.recipe = ResolvedPlacementRecipe::Grid {
            columns,
            rows,
            filled_count: u64::from(count),
            cell_width: cw,
            cell_height: ch,
            centroid,
            translate_to_numeric_anchor: false,
        };
    }
}

/// The columns and rows the core tiles a range of `w` by `h` short-edge units
/// with (`score_lowering.rs`, `PlacementAction::Tile`): the long side takes the
/// least `k` whose square is at least the count times the long side over the
/// short one, the short side the count over `k`, rounded up.
fn tile(count: u32, w: f64, h: f64) -> (u64, u64) {
    let n = u64::from(count.max(1));
    let landscape = h <= w;
    let long = if w == 0.0 || h == 0.0 {
        n
    } else {
        let target = n as f64 * if landscape { w / h } else { h / w };
        (1..=n).find(|k| (k * k) as f64 >= target).unwrap_or(n)
    };
    let short = n.div_ceil(long);
    if landscape {
        (long, short)
    } else {
        (short, long)
    }
}

/// A grid over a region with the columns and rows the core tiles it with.
fn build_tiled_grid(instruction: &mut Instruction, region: [f64; 4], units: Units) -> (u64, u64) {
    let [x0, y0, x1, y1] = region;
    let (columns, rows) = tile(
        count_of(instruction),
        (x1 - x0) * units.x,
        (y1 - y0) * units.y,
    );
    build_grid(instruction, region, columns, rows, units);
    (columns, rows)
}

/// R2: the part of the run `p0` to `p1` inside the canvas less `EDGE`, in the
/// same direction (Liang-Barsky). A run already inside, or one that never
/// enters, is returned as it is.
#[allow(clippy::float_cmp)]
fn inside_frame(p0: [f64; 2], p1: [f64; 2]) -> ([f64; 2], [f64; 2]) {
    let (low, high) = (EDGE, 1.0 - EDGE);
    let (dx, dy) = (p1[0] - p0[0], p1[1] - p0[1]);
    let (mut t0, mut t1) = (0.0_f64, 1.0_f64);
    for (p, q) in [
        (-dx, p0[0] - low),
        (dx, high - p0[0]),
        (-dy, p0[1] - low),
        (dy, high - p0[1]),
    ] {
        if p.abs() < 1e-12 {
            if q < 0.0 {
                return (p0, p1);
            }
            continue;
        }
        if p < 0.0 {
            t0 = py_max(t0, q / p);
        } else {
            t1 = py_min(t1, q / p);
        }
    }
    if t0 > t1 || (t0 == 0.0 && t1 == 1.0) {
        return (p0, p1);
    }
    (
        [p0[0] + dx * t0, p0[1] + dy * t0],
        [p0[0] + dx * t1, p0[1] + dy * t1],
    )
}

/// The width and height an arrangement covers now, in canvas fractions: a
/// row's run, a scatter's spread or a region; else the line it lies along.
fn extent_now(instruction: &Instruction, units: Units) -> (f64, f64) {
    let span = || {
        let ([ax, ay], [bx, by]) = current_span(instruction, units);
        ((bx - ax).abs(), (by - ay).abs())
    };
    if is_row(instruction) {
        return span();
    }
    if is_scatter(instruction) {
        let [w, h] = domain_of(instruction).unwrap_or([0.5, 0.5]);
        return (w / units.x, h / units.y);
    }
    let region = region_or_center(instruction);
    if region[2] - region[0] > 1e-6 || region[3] - region[1] > 1e-6 {
        return (region[2] - region[0], region[3] - region[1]);
    }
    span()
}

/// The smallest step between neighbouring fractions of a run.
fn min_gap(ts: &[f64]) -> f64 {
    ts.windows(2)
        .map(|pair| pair[1] - pair[0])
        .fold(f64::INFINITY, py_min)
}

/// One mark of a layer opened into marks: the layer's instruction alone at a
/// point, `scale` times its size, placed by the laws.
fn single(template: &Instruction, point: [f64; 2], scale: f64) -> Instruction {
    let mut mark = template.clone();
    if let Some(arrangement) = mark.arrangement.as_mut() {
        arrangement.count = 1;
        arrangement.color_cycle = Vec::new();
        if let Some(resolved) = arrangement.resolved.as_mut() {
            resolved.recipe = ResolvedPlacementRecipe::Place;
            resolved.domain = inku_score::Point::new(1.0, 1.0);
        }
    }
    set_point_region(&mut mark, clamp(point[0]), clamp(point[1]));
    scale_geometry(&mut mark, scale);
    moved(&mut mark);
    mark
}

// --- the cards' marks, as the prototype's card tool wrote them --------------------------------

/// One mark a card places: the template alone at a point (not moved inside the
/// canvas's edge, as the card tool placed it), `scale` times its size, turned
/// to `rotation` when one is given.
fn card_single(
    template: &Instruction,
    point: [f64; 2],
    scale: f64,
    rotation: Option<f64>,
) -> Instruction {
    let mut mark = template.clone();
    if let Some(arrangement) = mark.arrangement.as_mut() {
        arrangement.count = 1;
        arrangement.color_cycle = Vec::new();
        if let Some(resolved) = arrangement.resolved.as_mut() {
            resolved.recipe = ResolvedPlacementRecipe::Place;
            resolved.domain = inku_score::Point::new(1.0, 1.0);
        }
    }
    moved(&mut mark);
    set_point_region(&mut mark, point[0], point[1]);
    scale_geometry(&mut mark, scale);
    if rotation.is_some() {
        mark.rotation = rotation;
    }
    mark
}

/// The template's tool, color and stroke with another primitive's geometry,
/// unturned and still (the card tool's `shaped`), without the template's arc
/// form: a crescent or a waxing arc is not the pattern's shape.
fn shaped(template: &Instruction, primitive: Primitive) -> Instruction {
    let mut mark = template.clone();
    mark.from_ = None;
    mark.to = None;
    mark.center = None;
    mark.position = None;
    mark.radius = None;
    mark.size = None;
    mark.sides = None;
    mark.angle_start = None;
    mark.angle_end = None;
    mark.arc_form = None;
    mark.primitive = primitive;
    mark.rotation = Some(0.0);
    set_hand(&mut mark, Hand::Still);
    mark
}

/// A row from its first mark to its last, kept in that order, with the recipe
/// the core gives a row written by these numeric ends: a horizontal row from
/// left to right, a vertical row from top to bottom, and a diagonal row
/// otherwise (right to left and bottom to top included).
fn apply_directed_row(instruction: &mut Instruction, from: [f64; 2], to: [f64; 2], units: Units) {
    let ([x0, y0], [x1, y1]) = (from, to);
    if ((y1 - y0).abs() < 1e-9 && x0 < x1) || ((x1 - x0).abs() < 1e-9 && y0 < y1) {
        apply_row(instruction, from, to, units);
        return;
    }
    let n = f64::from(count_of(instruction));
    set_point_region(instruction, (x0 + x1) / 2.0, (y0 + y1) / 2.0);
    if let Some(resolved) = resolved_mut(instruction) {
        resolved.domain = inku_score::Point::new(units.x, units.y);
        resolved.recipe = ResolvedPlacementRecipe::DiagonalLine {
            step: inku_score::Point::new(
                (x1 - x0) * units.x / (n - 1.0),
                (y1 - y0) * units.y / (n - 1.0),
            ),
        };
    }
    if let Some(arrangement) = instruction.arrangement.as_mut() {
        arrangement.rhythm_spacing = RhythmSpacing::None;
    }
}

/// The marks a layer's instructions draw.
fn total_marks(instructions: &[Instruction]) -> u64 {
    instructions
        .iter()
        .map(|instruction| u64::from(count_of(instruction)))
        .sum()
}

/// One part of a pattern: a grid over a range, or (kikko) one hexagon.
#[derive(Clone, Copy, Debug, PartialEq)]
enum Part {
    Grid([f64; 4], u64, u64),
    Point([f64; 2]),
}

impl Part {
    fn marks(self) -> u64 {
        match self {
            Self::Grid(_, columns, rows) => columns * rows,
            Self::Point(_) => 1,
        }
    }
}

/// A count of millionths as the float the printer writes.
#[allow(clippy::cast_precision_loss)]
fn micro(value: i64) -> f64 {
    value as f64 / 1e6
}

/// The first millionth of a run of `length` millionths centered at `middle`.
#[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
fn centered(middle: f64, length: i64) -> i64 {
    (middle * 1e6 - length as f64 / 2.0 + 1e-6).floor() as i64
}

/// An even number of lattice steps whose square cell is no wider than `side`
/// short-edge units (2 at least).
#[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
fn square_side(side: f64, physical: i64) -> i64 {
    (2 * ((side * 1e6 / (2.0 * physical as f64) + 1e-9).floor() as i64)).max(2)
}

/// The parts of a pattern over a region and the physical side of its cell: the
/// prototype's count of columns and rows, and exact square cells on the
/// canvas's micro-lattice (`lattice`), centered in the region. Seigaiha's two
/// grids stay inside it, and so do kikko's one-row tiles (a row's marks would
/// take the brush's member sway, which a tile does not).
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_possible_wrap,
    clippy::cast_precision_loss,
    clippy::cast_sign_loss
)]
fn pattern_plan(region: [f64; 4], unit: f64, pattern: &str, units: Units) -> (Vec<Part>, f64) {
    let [x0, y0, x1, y1] = region;
    let (w, h) = (x1 - x0, y1 - y0);
    let row_factor = match pattern {
        "seigaiha" => 0.5,
        "kikko" => HALF_SQRT_3,
        _ => 1.0,
    };
    let mut columns = ((w * units.x / unit).round_ties_even() as i64).max(1);
    let rows = ((h * units.y / (unit * row_factor)).round_ties_even() as i64).max(1);
    let (xs, ys, physical) = units.lattice();
    let (xs, ys, physical) = (xs as i64, ys as i64, physical as i64);
    let (middle_x, middle_y) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    if pattern == "kikko" {
        let t = square_side(py_min(w * units.x / columns as f64, h * units.y), physical);
        let (sx, sy) = (t * xs, t * ys);
        let pitch = sy as f64 * HALF_SQRT_3;
        let fit = ((h * 1e6 - sy as f64) / pitch + 1e-9).floor() as i64 + 1;
        let kept = rows.min(fit).max(1);
        let width = columns * sx;
        let left = centered(middle_x, width);
        let top = centered(
            middle_y,
            sy + ((kept - 1) as f64 * pitch).round_ties_even() as i64,
        );
        let mut parts = Vec::new();
        for parity in [0_i64, 1] {
            if parity == 1 && columns <= 1 {
                continue;
            }
            let (a, b) = (left + parity * sx / 2, left + width - parity * sx / 2);
            let mut k = parity;
            while k < kept {
                let y = top + (k as f64 * pitch).round_ties_even() as i64;
                if columns - parity == 1 {
                    parts.push(Part::Point([micro((a + b) / 2), micro(y + sy / 2)]));
                } else {
                    let row = [micro(a), micro(y), micro(b), micro(y + sy)];
                    parts.push(Part::Grid(row, (columns - parity) as u64, 1));
                }
                k += 2;
            }
        }
        return (parts, micro(t * physical));
    }
    let (cw, ch) = (w * units.x / columns as f64, h * units.y / rows as f64);
    let side = if pattern == "seigaiha" {
        py_min(cw, 2.0 * ch)
    } else {
        py_min(cw, ch)
    };
    let t = square_side(side, physical);
    let (sx, sy) = (t * xs, t * ys);
    let side = micro(t * physical);
    if matches!(pattern, "ichimatsu" | "uroko") && columns % 2 == 0 && columns > 1 {
        // A color cycle in reading order alternates both ways only over an odd row length.
        columns -= 1;
    }
    if pattern != "seigaiha" {
        let (width, height) = (columns * sx, rows * sy);
        let (left, top) = (centered(middle_x, width), centered(middle_y, height));
        let region = [
            micro(left),
            micro(top),
            micro(left + width),
            micro(top + height),
        ];
        return (vec![Part::Grid(region, columns as u64, rows as u64)], side);
    }
    let kept = (rows - 1).max(1);
    let (even, odd) = ((kept + 1) / 2, kept / 2);
    let (width, height) = (columns * sx, (kept + 1) * sy / 2);
    let (left, top) = (centered(middle_x, width), centered(middle_y, height));
    let mut parts = vec![Part::Grid(
        [
            micro(left),
            micro(top),
            micro(left + width),
            micro(top + even * sy),
        ],
        columns as u64,
        even as u64,
    )];
    if odd > 0 && columns > 1 {
        parts.push(Part::Grid(
            [
                micro(left + sx / 2),
                micro(top + sy / 2),
                micro(left + width - sx / 2),
                micro(top + sy / 2 + odd * sy),
            ],
            (columns - 1) as u64,
            odd as u64,
        ));
    }
    (parts, side)
}

/// Where a layer's instructions put their marks; `None` for a seeded scatter.
fn layer_centers(instructions: &[Instruction], units: Units) -> Option<Vec<[f64; 2]>> {
    let mut centers = Vec::new();
    for instruction in instructions {
        centers.extend(mark_centers(instruction, units)?);
    }
    Some(centers)
}

/// C4's repeats: each one's size, the turn it adds to the one before and
/// whether an echo follows it.
fn motif_sizes(sequence: &[&str], repeats: usize) -> Vec<(f64, f64, bool)> {
    let mut size = 1.0;
    let mut steps = Vec::new();
    for m in 0..repeats {
        let (mut turn, mut echo) = (0.0, false);
        if m > 0 {
            match sequence[(m - 1) % sequence.len()] {
                "grow" => size *= SQRT_PHI,
                "shrink" => size /= SQRT_PHI,
                "rotate" => turn = 30.0,
                "mirror" => turn = 180.0,
                _ => echo = true,
            }
        }
        steps.push((size, turn, echo));
    }
    steps
}

/// The golden spiral's places, its radius in short-edge units.
fn spiral_points(count: usize, radius: f64, units: Units) -> Vec<[f64; 2]> {
    (0..count)
        .map(|m| {
            #[allow(clippy::cast_precision_loss)]
            let m = m as f64;
            let angle = (200.0 + 90.0 * m).to_radians();
            let r = radius / PHI.powf(m / 1.5);
            [
                clamp_between(0.5 + r * angle.cos() / units.x, 0.06, 0.94),
                clamp_between(0.5 + r * angle.sin() / units.y, 0.06, 0.94),
            ]
        })
        .collect()
}

/// C4's places along its path; `stretch` lengthens the path about its middle.
#[allow(clippy::cast_precision_loss, clippy::float_cmp)]
fn motif_points(path: &str, repeats: usize, cy: f64, units: Units, stretch: f64) -> Vec<[f64; 2]> {
    let last = (repeats - 1) as f64;
    if stretch == 1.0 {
        return match path {
            "row" => (0..repeats)
                .map(|m| [0.14 + 0.72 * m as f64 / last, cy])
                .collect(),
            "diagonal" => (0..repeats)
                .map(|m| [0.16 + 0.68 * m as f64 / last, 0.84 - 0.68 * m as f64 / last])
                .collect(),
            _ => spiral_points(repeats, 0.34, units),
        };
    }
    match path {
        "row" => (0..repeats)
            .map(|m| [0.5 + (-0.36 + 0.72 * m as f64 / last) * stretch, cy])
            .collect(),
        "diagonal" => (0..repeats)
            .map(|m| {
                [
                    0.5 + (-0.34 + 0.68 * m as f64 / last) * stretch,
                    0.5 + (0.34 - 0.68 * m as f64 / last) * stretch,
                ]
            })
            .collect(),
        _ => spiral_points(repeats, 0.34 * stretch, units),
    }
}

/// The largest overlap of two neighbouring repeats: their mean width over the
/// distance between them, in short-edge units (an echo is left out).
fn motif_crowding(
    points: &[[f64; 2]],
    sizes: &[(f64, f64, bool)],
    width: f64,
    units: Units,
) -> f64 {
    let mut worst = 0.0_f64;
    for k in 1..points.len().min(sizes.len()) {
        let distance = units.distance(points[k - 1], points[k]);
        let crowding = if distance > 0.0 {
            (sizes[k - 1].0 + sizes[k].0) / 2.0 * width / distance
        } else {
            f64::INFINITY
        };
        worst = py_max(worst, crowding);
    }
    worst
}

/// How far each of C4's paths may lengthen inside the inner frame.
fn motif_stretch(path: &str) -> f64 {
    if path == "row" {
        (0.5 - INNER.0) / 0.36
    } else {
        (0.5 - INNER.0) / 0.34
    }
}

/// The hands C6 draws its degrees with: shin's stillness, gyo's fine and slow
/// wave, and so's sway in three degrees, each with the turn it adds.
fn c6_hand(level: &str, degree: &str) -> (Option<inku_score::Variation>, f64) {
    let variation = |amplitude, frequency, quality| {
        Some(inku_score::Variation {
            amplitude,
            frequency,
            quality,
            dimensions: vec![
                inku_score::Dimension::PositionX,
                inku_score::Dimension::PositionY,
            ],
        })
    };
    match (level, degree) {
        ("shin", _) => (None, 0.0),
        ("gyo", _) => (
            variation(Amplitude::Fine, Frequency::Slow, inku_score::Quality::Wave),
            8.0,
        ),
        (_, "small") => (
            variation(
                Amplitude::Fine,
                Frequency::Medium,
                inku_score::Quality::Perlin,
            ),
            14.0,
        ),
        (_, "medium") => (
            variation(
                Amplitude::Medium,
                Frequency::Medium,
                inku_score::Quality::Perlin,
            ),
            24.0,
        ),
        _ => (
            variation(
                Amplitude::Broad,
                Frequency::Medium,
                inku_score::Quality::Perlin,
            ),
            36.0,
        ),
    }
}

/// How far the origin's own arrangement overlapped its marks: one mark's width
/// over the spacing (a bundle at one spot without limit, a single mark not at all).
fn origin_ratio(instruction: &Instruction, units: Units) -> f64 {
    let count = count_of(instruction);
    let width = 2.0 * largest_extent(instruction, units);
    if count < 2 || width <= 0.0 {
        return 0.0;
    }
    let n = f64::from(count);
    let domain = domain_of(instruction).unwrap_or([1.0, 1.0]);
    let spacing = match recipe(instruction) {
        Some(ResolvedPlacementRecipe::Place) => return f64::INFINITY,
        Some(ResolvedPlacementRecipe::HorizontalLine { cell_width }) => {
            if *cell_width != 0.0 {
                *cell_width
            } else {
                domain[0] / n
            }
        }
        Some(ResolvedPlacementRecipe::VerticalLine { cell_height }) => {
            if *cell_height != 0.0 {
                *cell_height
            } else {
                domain[1] / n
            }
        }
        Some(ResolvedPlacementRecipe::DiagonalLine { step }) => hypot(step.x, step.y),
        Some(ResolvedPlacementRecipe::Grid {
            cell_width,
            cell_height,
            ..
        }) => py_min(*cell_width, *cell_height),
        Some(ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation) => {
            (domain[0] * domain[1] / n).sqrt()
        }
        _ => return 0.0,
    };
    if spacing > 0.0 {
        width / spacing
    } else {
        f64::INFINITY
    }
}

/// `(allowed, target)`: marks overlapping past `allowed` times their spacing
/// are fitted to `target` times it.
fn fit_ratio(origin: f64) -> (f64, f64) {
    (py_max(1.0, origin), py_max(FIT_TARGET, origin))
}

/// The ends of a run stretched along its own line toward `length` (canvas
/// fractions along the run), inside the inner frame. The run never gets
/// shorter; a pinned run grows about its middle, a free one as far as the
/// frame allows on either side.
fn stretch_span(p0: [f64; 2], p1: [f64; 2], length: f64, pinned: bool) -> ([f64; 2], [f64; 2]) {
    let ([x0, y0], [x1, y1]) = (p0, p1);
    let now = hypot(x1 - x0, y1 - y0);
    if now <= 0.0 || length <= now {
        return (p0, p1);
    }
    let (ux, uy) = ((x1 - x0) / now, (y1 - y0) / now);
    let (mx, my) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    let (mut back, mut ahead) = (f64::INFINITY, f64::INFINITY);
    for (c, u) in [(mx, ux), (my, uy)] {
        if u.abs() > 1e-9 {
            let (low, high) = ((INNER.0 - c) / u, (INNER.1 - c) / u);
            back = py_min(back, -py_min(low, high));
            ahead = py_min(ahead, py_max(low, high));
        }
    }
    // An end already past the frame stays where it is.
    back = py_max(back, now / 2.0);
    ahead = py_max(ahead, now / 2.0);
    let mut behind = py_min(py_min(length / 2.0, back), ahead);
    let mut before = behind;
    if !pinned {
        behind = py_min(back, py_max(behind, length - py_min(ahead, length / 2.0)));
        before = py_min(ahead, length - behind);
    }
    // An end that does not move keeps its own coordinates.
    let start = if behind <= now / 2.0 {
        p0
    } else {
        [mx - ux * behind, my - uy * behind]
    };
    let end = if before <= now / 2.0 {
        p1
    } else {
        [mx + ux * before, my + uy * before]
    };
    (start, end)
}

/// Canvas fractions along a run per short-edge unit of its length.
fn along_per_unit(units: Units, row: Row) -> f64 {
    let along = hypot(row.to[0] - row.from[0], row.to[1] - row.from[1]);
    let physical = units.distance(row.from, row.to);
    if physical > 0.0 {
        along / physical
    } else {
        1.0
    }
}

// --- what the reader is told -------------------------------------------------------------------

/// One layer as the request shows it.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct LayerSummary {
    pub layer: usize,
    pub shape: &'static str,
    pub tool: &'static str,
    pub count: u64,
    pub color: &'static str,
    pub filled: bool,
    pub arranged: Option<&'static str>,
    #[serde(rename = "box")]
    pub covered: [f64; 4],
    pub mark_size: [f64; 2],
}

fn weight_name(weight: inku_score::Weight) -> &'static str {
    weight.as_str()
}

fn arranged_name(recipe: Option<&ResolvedPlacementRecipe>) -> Option<&'static str> {
    Some(match recipe? {
        ResolvedPlacementRecipe::Place => "place",
        ResolvedPlacementRecipe::HorizontalLine { .. } => "row_horizontal",
        ResolvedPlacementRecipe::VerticalLine { .. } => "row_vertical",
        ResolvedPlacementRecipe::DiagonalLine { .. } => "row_diagonal",
        ResolvedPlacementRecipe::Grid { .. } => "grid",
        ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation => "scatter",
        ResolvedPlacementRecipe::Cells => "cells",
    })
}

pub(crate) fn summaries(score: &Score, units: Units) -> Vec<LayerSummary> {
    let mut out = Vec::new();
    for (index, positions) in layers(score) {
        let instructions: Vec<&Instruction> =
            positions.iter().map(|p| &score.instructions[*p]).collect();
        let first = instructions[0];
        let plugin = instructions
            .iter()
            .any(|item| layer_of(item).is_some_and(|(_, how)| how == Belongs::Plugin));
        let arranged = if plugin {
            Some("plugin")
        } else if resolved(first).is_some_and(|resolved| {
            matches!(
                resolved.count_origin,
                inku_score::CountOrigin::TemplateSingle
            )
        }) {
            Some("fill")
        } else {
            arranged_name(recipe(first))
        };
        let count = instructions
            .iter()
            .map(|item| u64::from(count_of(item)))
            .sum();
        let boxes: Vec<[f64; 4]> = instructions
            .iter()
            .map(|item| mark_box(item, units))
            .collect();
        let covered = boxes.iter().skip(1).fold(boxes[0], |all, b| {
            [
                py_min(all[0], b[0]),
                py_min(all[1], b[1]),
                py_max(all[2], b[2]),
                py_max(all[3], b[3]),
            ]
        });
        let (hx, hy) = extent(first, units);
        out.push(LayerSummary {
            layer: index,
            shape: first.primitive.as_str(),
            tool: weight_name(first.weight),
            count,
            color: first.color.as_str(),
            filled: first.filled,
            arranged,
            covered: covered.map(round3),
            mark_size: [round3(2.0 * hx), round3(2.0 * hy)],
        });
    }
    out
}

/// The composed plan the laws are applied to: the plan in print order, the
/// ranges the composition wrote and the joint each layer is printed with.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ComposedPlan {
    pub plan: WorkPlan,
    pub ranges: Vec<Option<ComposedRange>>,
    pub joints: Vec<Option<String>>,
}

impl ComposedPlan {
    /// The composed document's source, as the composition printed it.
    #[must_use]
    pub fn source(
        &self,
        language: ResolvedInstructionLanguage,
        plugins: &[WorkPlanPlugin],
    ) -> String {
        let joints: Vec<Option<&str>> = self.joints.iter().map(Option::as_deref).collect();
        print_work_plan_with_numbers(&self.plan, language, plugins, &self.ranges, &joints, &[])
    }
}

/// The direction the AI refinement gives the laws stage of a saved work
/// (2026-10-20): the laws it leaves out (the parent's, so that the child takes
/// other laws), whether the cards are offered, and the author's sentence. Empty,
/// the request is the one a description run sends.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LawsDirection {
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub exclude: Vec<String>,
    #[serde(default, skip_serializing_if = "CardsOffer::is_as_usual")]
    pub cards: CardsOffer,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// Whether a refinement's request offers the cards (C1 to C6).
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CardsOffer {
    /// As a description run offers them.
    #[default]
    AsUsual,
    /// Offered, and the request invites one as the main law.
    Invite,
    /// Not offered.
    None,
}

impl CardsOffer {
    fn is_as_usual(&self) -> bool {
        *self == Self::AsUsual
    }
}

/// The longest direction sentence, in characters.
pub const DIRECTION_NOTE_LIMIT: usize = 1000;

impl LawsDirection {
    /// Whether every law named is one of the laws and the sentence is within
    /// [`DIRECTION_NOTE_LIMIT`]; `Err` names what is wrong.
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.exclude.iter().any(|law| !LAWS.contains(&law.as_str())) {
            return Err("unknown_law");
        }
        if self.note.as_ref().is_some_and(|note| {
            note.trim().is_empty() || note.chars().count() > DIRECTION_NOTE_LIMIT
        }) {
            return Err("note");
        }
        Ok(())
    }
}

/// What a work's layers allow, read from the composed document's Score.
#[derive(Clone, Debug)]
pub struct LawsContext {
    score: Score,
    units: Units,
    /// The CIELAB lightness of each of the nine colors the run's palette draws.
    lightness: Option<BTreeMap<&'static str, f64>>,
    /// The nine colors as the request's table shows them.
    colors: Option<Vec<ColorRow>>,
    summaries: Vec<LayerSummary>,
    /// The layer index of the plan's first layer: plugin sentences come first.
    first_plan_layer: usize,
    /// The refinement's direction; empty in a description run.
    direction: LawsDirection,
}

/// One of the nine colors as the request shows it: the lightness the
/// prototype measured (0 to 1, two decimals), the chroma and the hue angle.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ColorRow {
    pub name: &'static str,
    pub lightness: f64,
    pub chroma: i64,
    pub hue: i64,
}

/// The CIELAB lightness (0 to 1), chroma and hue angle (degrees) of an sRGB
/// color under D65, as the prototype measured it (`model.lch`).
pub(crate) fn lch_of([r, g, b]: [u8; 3]) -> (f64, f64, f64) {
    let linear = |channel: u8| {
        let c = f64::from(channel) / 255.0;
        if c <= 0.04045 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    };
    let lin = [linear(r), linear(g), linear(b)];
    let x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047;
    let y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
    let z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883;
    let f = |t: f64| {
        if t > 0.008856 {
            t.powf(1.0 / 3.0)
        } else {
            7.787 * t + 16.0 / 116.0
        }
    };
    let (a, b) = (500.0 * (f(x) - f(y)), 200.0 * (f(y) - f(z)));
    (
        (116.0 * f(y) - 16.0) / 100.0,
        hypot(a, b),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    )
}

/// The CIELAB lightness (0 to 1) of an sRGB color, as the prototype measured it.
fn lightness_of(rgb: [u8; 3]) -> f64 {
    lch_of(rgb).0
}

impl LawsContext {
    /// The context of a composed document: its Score, the composed plan it was
    /// printed from, the run's palette and canvas. `None` when the Score does
    /// not have one layer per printed sentence.
    #[must_use]
    pub fn new(
        score: Score,
        composed: &ComposedPlan,
        palette: &ResolvedPaletteDto,
        canvas_format_id: &str,
    ) -> Option<Self> {
        let units = Units::of(canvas_format_id)?;
        let lightness = palette.observations.map(|observations| {
            observations
                .iter()
                .map(|color| {
                    (
                        color.abstract_color.as_str(),
                        lightness_of(color.concrete_rgb),
                    )
                })
                .collect()
        });
        let colors = palette.observations.and_then(|observations| {
            COLORS
                .iter()
                .map(|color| {
                    let observed = observations
                        .iter()
                        .find(|observed| observed.abstract_color == *color)?;
                    let (lightness, chroma, hue) = lch_of(observed.concrete_rgb);
                    Some(ColorRow {
                        name: color.as_str(),
                        lightness: round2(lightness),
                        chroma: round_int(chroma),
                        hue: round_int(hue),
                    })
                })
                .collect::<Option<Vec<ColorRow>>>()
        });
        let summaries = summaries(&score, units);
        let plan_layers = composed.plan.layers.len();
        let first_plan_layer = composed.plan.plugins.len();
        let expected: Vec<usize> = (0..first_plan_layer + plan_layers).collect();
        let found: Vec<usize> = summaries.iter().map(|summary| summary.layer).collect();
        if found != expected
            || composed.ranges.len() != plan_layers
            || composed.joints.len() != plan_layers
        {
            return None;
        }
        Some(Self {
            score,
            units,
            lightness,
            colors,
            summaries,
            first_plan_layer,
            direction: LawsDirection::default(),
        })
    }

    /// The context with a refinement's direction: the laws it leaves out take
    /// no layer, and the request says so.
    #[must_use]
    pub fn with_direction(mut self, direction: LawsDirection) -> Self {
        self.direction = direction;
        self
    }

    /// Whether the refinement's direction leaves a law out.
    fn excluded(&self, law: &str) -> bool {
        self.direction.exclude.iter().any(|left| left == law)
            || (self.direction.cards == CardsOffer::None && REBUILD.contains(&law))
    }

    #[must_use]
    pub fn summaries(&self) -> &[LayerSummary] {
        &self.summaries
    }

    fn summary(&self, layer: usize) -> Option<&LayerSummary> {
        self.summaries.iter().find(|summary| summary.layer == layer)
    }

    fn arranged(&self, layer: usize) -> Option<&'static str> {
        self.summary(layer).and_then(|summary| summary.arranged)
    }

    fn movable(&self) -> Vec<usize> {
        self.summaries
            .iter()
            .filter(|summary| !matches!(summary.arranged, Some("plugin" | "fill")))
            .map(|summary| summary.layer)
            .collect()
    }

    fn shape(&self, layer: usize) -> Option<Primitive> {
        let positions = layers(&self.score).remove(&layer)?;
        Some(self.score.instructions[*positions.first()?].primitive)
    }

    /// The layers each law may take in this work (the prototype's narrowing).
    fn candidates(&self, law: &str) -> Vec<usize> {
        if self.excluded(law) {
            return Vec::new();
        }
        let movable = self.movable();
        match law {
            "B1" | "B2" | "B3" | "B4" | "B7" | "B8" => movable,
            "B5" => movable
                .into_iter()
                .filter(|layer| {
                    self.shape(*layer).is_some_and(is_line)
                        || self
                            .summary(*layer)
                            .is_some_and(|summary| summary.count >= 2)
                })
                .collect(),
            "B6" => movable
                .into_iter()
                .filter(|layer| {
                    self.shape(*layer)
                        .is_some_and(|shape| SIZED.contains(&shape))
                })
                .collect(),
            "B9" | "B10" | "B12" => movable
                .into_iter()
                .filter(|layer| {
                    self.summary(*layer)
                        .is_some_and(|summary| summary.count >= 2)
                })
                .collect(),
            "B15" | "B21" => self
                .summaries
                .iter()
                .filter(|summary| summary.arranged != Some("plugin"))
                .map(|summary| summary.layer)
                .collect(),
            "C1" | "C2" | "C3" | "C4" => movable,
            "C5" => movable
                .into_iter()
                .filter(|layer| {
                    self.summary(*layer)
                        .is_some_and(|summary| summary.count >= 6)
                })
                .collect(),
            // C6 draws each mark of a row or a grid apart: a bundle's marks share
            // one spot, a scatter's are seeded, and a point cannot sway.
            "C6" => movable
                .into_iter()
                .filter(|layer| {
                    self.summary(*layer).is_some_and(|summary| {
                        summary.count >= 3
                            && summary.shape != Primitive::Point.as_str()
                            && matches!(
                                summary.arranged,
                                Some("row_horizontal" | "row_vertical" | "row_diagonal" | "grid")
                            )
                    })
                })
                .collect(),
            _ => Vec::new(),
        }
    }

    /// The largest count of a layer a law may move (C4's repeats go up to it).
    fn max_count(&self) -> u64 {
        self.movable()
            .into_iter()
            .filter_map(|layer| self.summary(layer).map(|summary| summary.count))
            .fold(1, u64::max)
    }

    /// A layer's count in the composed document's Score.
    fn count(&self, layer: usize) -> u64 {
        self.summary(layer).map_or(0, |summary| summary.count)
    }

    /// The laws a reader may choose for this work: those with a layer to take.
    fn offered(&self) -> Vec<&'static str> {
        LAWS.into_iter()
            .filter(|law| !self.candidates(law).is_empty())
            .collect()
    }
}

// --- the request ---------------------------------------------------------------------------------

struct LawText {
    name: [&'static str; 2],
    family: [&'static str; 2],
    source: [&'static str; 2],
    law: [&'static str; 2],
    choose: [&'static str; 2],
    /// The value example, as the prototype printed it (`json.dumps`, its key order).
    example: &'static str,
}

const LAW_TEXTS: [(&str, LawText); 19] = [
    (
        "B1",
        LawText {
            name: ["黄金分割", "Golden section"],
            family: ["比例", "proportion"],
            source: [
                "Pacioli『神聖比例論』(1509)、Zeising (1854)",
                "Pacioli, De divina proportione (1509); Zeising (1854)",
            ],
            law: [
                "画面の辺を 0.382 : 0.618 で分ける線と、その4つの交点に、主な物と線を置く。",
                "Place the main things and lines on the lines that divide the canvas's sides 0.382 : 0.618 and on their four crossings.",
            ],
            choose: [
                "層ごとに at（と線なら span）。",
                "for each layer, at (and span for a line).",
            ],
            example: r#"{"targets":[{"layer":0,"at":"point_ur"},{"layer":1,"at":"line_bottom","span":"full"}]}"#,
        },
    ),
    (
        "B2",
        LawText {
            name: ["白銀分割", "Silver section"],
            family: ["比例", "proportion"],
            source: [
                "Hambidge『Dynamic Symmetry』(1920) の √2 の矩形",
                "Hambidge, Dynamic Symmetry (1920): the √2 rectangle",
            ],
            law: [
                "辺を 1 : √2 で分ける線（0.414・0.586）と交点に置く。",
                "Place on the lines that divide the sides 1 : √2 (0.414 and 0.586) and on their crossings.",
            ],
            choose: ["B1 と同じ。", "as for B1."],
            example: r#"{"targets":[{"layer":0,"at":"point_ll"}]}"#,
        },
    ),
    (
        "B3",
        LawText {
            name: ["三分割", "Rule of thirds"],
            family: ["比例", "proportion"],
            source: [
                "J. T. Smith『Remarks on Rural Scenery』(1797)",
                "J. T. Smith, Remarks on Rural Scenery (1797)",
            ],
            law: [
                "辺を三つに分ける線（1/3・2/3）と交点に置く。",
                "Place on the lines that divide the sides in three (1/3 and 2/3) and on their crossings.",
            ],
            choose: ["B1 と同じ。", "as for B1."],
            example: r#"{"targets":[{"layer":0,"at":"line_top","span":"current"}]}"#,
        },
    ),
    (
        "B4",
        LawText {
            name: ["調和の比", "Harmonic ratio"],
            family: ["比例", "proportion"],
            source: [
                "Alberti『建築論』(1452)（音の協和の比）",
                "Alberti, De re aedificatoria (1452) (the consonant ratios of sound)",
            ],
            law: [
                "辺を音の協和の比 2:3（0.4・0.6）か 3:4（0.429・0.571）で分ける線と交点に置く。",
                "Place on the lines that divide the sides by a consonant ratio of sound, 2:3 (0.4 and 0.6) or 3:4 (0.429 and 0.571), and on their crossings.",
            ],
            choose: [
                "比と、B1 と同じ層ごとの at・span。",
                "the ratio, and at and span for each layer as for B1.",
            ],
            example: r#"{"ratio":"2:3","targets":[{"layer":0,"at":"point_lr"}]}"#,
        },
    ),
    (
        "B5",
        LawText {
            name: ["骨組み", "Armature"],
            family: ["比例", "proportion"],
            source: [
                "Bouleau『画家の秘密の幾何学』(1963)",
                "Bouleau, The Painter's Secret Geometry (1963)",
            ],
            law: [
                "画面の対角線・中心の縦の線・中心の横の線を骨組みにして、線の層と複数の物の列をその上に置く。",
                "Take the canvas's diagonals, its central vertical line and its central horizontal line as the armature, and place line layers and rows of several things on them.",
            ],
            choose: [
                "線の層か複数の物の層ごとに、通り道（diagonal_down 左上→右下、diagonal_up 左下→右上、center_vertical、center_horizontal）。",
                "for each line layer or layer of several things, a path (diagonal_down from upper left to lower right, diagonal_up from lower left to upper right, center_vertical, center_horizontal).",
            ],
            example: r#"{"targets":[{"layer":1,"path":"diagonal_up"}]}"#,
        },
    ),
    (
        "B6",
        LawText {
            name: ["主従", "Subordination"],
            family: ["均衡", "balance"],
            source: [
                "Dow『Composition』(1899) の Subordination",
                "Dow, Composition (1899): Subordination",
            ],
            law: [
                "主は一つ。従と添えの痕の大きさを、主を 1 として 0.618・0.382 にする（主は今の大きさ）。",
                "One thing is main. The marks of the secondary and accent layers are 0.618 and 0.382 of the main's (the main keeps its size).",
            ],
            choose: [
                "従の層と添えの層（閉じた形か弧の層。主の層 main_layer も閉じた形か弧でなければ使えない）。",
                "the secondary layers and the accent layers (layers of closed shapes or arcs; usable only when the main layer main_layer is a closed shape or an arc too).",
            ],
            example: r#"{"secondary":[1],"accent":[2]}"#,
        },
    ),
    (
        "B7",
        LawText {
            name: ["天秤の均衡", "Steelyard balance"],
            family: ["均衡", "balance"],
            source: [
                "Poore『Pictorial Composition』(1903) の steelyard、Arnheim『美術と視覚』(1954)",
                "Poore, Pictorial Composition (1903): the steelyard; Arnheim, Art and Visual Perception (1954)",
            ],
            law: [
                "大きな主は中心寄りに、小さな従は中心をはさんだ反対側の遠くに置き、重さ×距離を釣り合わせる。道具が、主の反対側に主の 2.618 倍遠く置き、閉じた形なら主の 0.382 の大きさ（主従があればその比）にする。",
                "Keep a large main near the center and place a small secondary far away on the other side of the center, balancing weight × distance. The tool places it opposite the main, 2.618 times as far from the center, and, for a closed shape, at 0.382 of the main's size (subordination's ratio when it is used).",
            ],
            choose: [
                "釣り合わせる層（主でない層。主が中心にある時は使えない）。",
                "the layer to balance (not the main layer; not usable when the main is at the center).",
            ],
            example: r#"{"layer":1}"#,
        },
    ),
    (
        "B8",
        LawText {
            name: ["対称の均衡", "Symmetrical balance"],
            family: ["均衡", "balance"],
            source: ["Dow の Symmetry", "Dow: Symmetry"],
            law: [
                "中心線に対して対に置く。層の中心を軸に置き、二つの物は軸の両側（0.382 と 0.618）に鏡に置く。",
                "Place in pairs about a central line. The layer's center goes on the axis, and two things are mirrored on either side of it (at 0.382 and 0.618).",
            ],
            choose: [
                "層ごとに軸（vertical 縦の中心線・horizontal 横の中心線・both 中心の点）。",
                "for each layer, the axis (vertical the central vertical line, horizontal the central horizontal line, both the central point).",
            ],
            example: r#"{"targets":[{"layer":0,"axis":"vertical"}]}"#,
        },
    ),
    (
        "B9",
        LawText {
            name: ["等間隔の反復", "Equal repetition"],
            family: ["律動", "rhythm"],
            source: [
                "Dow の Repetition、Ross『A Theory of Pure Design』(1907)",
                "Dow: Repetition; Ross, A Theory of Pure Design (1907)",
            ],
            law: [
                "同じ形を同じ間隔で並べる。列は置き場の線（無ければ今の長い向き）に沿って等しい間隔、格子は数を列×行に割った等しいます目。",
                "Repeat the same shape at equal intervals. A row runs at equal spacing along the placement law's line (or the current long side); a grid divides the count into equal cells of columns × rows.",
            ],
            choose: [
                "複数の物の層ごとに、形（row 列・grid 格子）。",
                "for each layer of several things, the form (row, grid).",
            ],
            example: r#"{"targets":[{"layer":1,"form":"grid"}]}"#,
        },
    ),
    (
        "B10",
        LawText {
            name: ["漸進", "Progression"],
            family: ["律動", "rhythm"],
            source: [
                "Ross の尺度の漸進、Dow の Transition",
                "Ross: the progression of scale; Dow: Transition",
            ],
            law: [
                "物を一つずつに開いて列にし、大きさか間隔を、隣どうし同じ比で変える。端から端までの比は 0.618 か 0.382。",
                "Open the things one by one into a row and change their size or their spacing by the same ratio between neighbours. The ratio from one end to the other is 0.618 or 0.382.",
            ],
            choose: [
                "複数の物の層ごとに、変えるもの（size・spacing）、比、小さく・詰まっていく向き（toward: left・right・top・bottom）。",
                "for each layer of several things, what changes (size, spacing), the ratio, and the side they get smaller or closer toward (toward: left, right, top, bottom).",
            ],
            example: r#"{"targets":[{"layer":1,"change":"size","ratio":"0.618","toward":"right"}]}"#,
        },
    ),
    (
        "B12",
        LawText {
            name: ["拍の群", "Beat groups"],
            family: ["律動", "rhythm"],
            source: [
                "Klee『教育スケッチブック』(1925)、音楽の拍子と強弱",
                "Klee, Pedagogical Sketchbook (1925); the meter and accents of music",
            ],
            law: [
                "物を 2・3・4 個ずつの群にして、群の間に間（並びの間隔の2倍）をおいて列に並べる。強拍を選ぶと、群の初めが大きく、ほかは 0.618 になる。",
                "Group the things by 2, 3 or 4 and line them up with a rest (twice the row's spacing) between the groups. With a strong beat, the first of each group is large and the others are 0.618.",
            ],
            choose: [
                "複数の物の層ごとに、群の大きさ（\"2\"・\"3\"・\"4\"）と強拍（first・none）。",
                "for each layer of several things, the group size (\"2\", \"3\", \"4\") and the strong beat (first, none).",
            ],
            example: r#"{"targets":[{"layer":1,"group":"3","strong":"first"}]}"#,
        },
    ),
    (
        "B15",
        LawText {
            name: ["空気遠近", "Aerial perspective"],
            family: ["階調", "gradation"],
            source: ["Leonardo『絵画論』", "Leonardo, Treatise on Painting"],
            law: [
                "遠くの物を、地との明るさの差が小さい寒色か灰（差 0.2 以上は残す）に替え、0.786 倍に小さくする。",
                "Turn distant things to the cool color or gray closest to the ground in lightness (keeping a difference of 0.2 or more) and make them 0.786 times as large.",
            ],
            choose: ["遠くの層。", "the distant layers."],
            example: r#"{"layers":[0]}"#,
        },
    ),
    (
        "B21",
        LawText {
            name: ["統一と変化", "Unity and variety"],
            family: ["統一と変化", "unity and variety"],
            source: [
                "Hogarth『美の解析』(1753)",
                "Hogarth, The Analysis of Beauty (1753)",
            ],
            law: [
                "法則が位置・間隔・大きさ・色を決め、手の揺らぎはその規則を壊さない幅に収める。記述が揺れ・波・震えを言う層だけ揺らぎを保つ。主の法則にはしない。",
                "The laws decide places, spacing, sizes and colors, and the hand's fluctuation stays within what keeps their rules. Only a layer whose description speaks of swaying, waves or trembling keeps its fluctuation. Never the main law.",
            ],
            choose: [
                "層ごとに手（still 揺らぎ無し・fine 細かく遅く・keep 今のまま）。",
                "for each layer, the hand (still no fluctuation, fine fine and slow, keep as it is).",
            ],
            example: r#"{"targets":[{"layer":0,"hand":"still"},{"layer":1,"hand":"fine"}]}"#,
        },
    ),
    (
        "C1",
        LawText {
            name: ["疎密", "Sparse and dense"],
            family: ["カード", "card"],
            source: [
                "中国の画論の疎密・聚散（「疎処は馬を走らすべく、密処は風を透さしめず」、鄧石如の言として伝わる）",
                "the sparse and dense, gathering and scattering of Chinese painting theory (“where it is sparse, a horse may run; where it is dense, no wind passes”, told as Deng Shiru's words)",
            ],
            law: [
                "画面の中に、物が隙間なく詰まる密の所を一つ作り、ほかを大きく空ける。密の所は黄金分割か三分割の交点か中心に置く。",
                "Make one dense place in the picture where things crowd without a gap, and leave the rest wide open. Put the dense place on a crossing of the golden section or the thirds, or at the center.",
            ],
            choose: [
                "密にする層（1〜2、数の多い物や群れ・粒の物）と、それぞれの数（記述が数を書いた層は今の数のまま。ほかは今の1〜6倍まで）、密の場所、密の広さ（画面の短辺に対する比）。",
                "the layers to make dense (1 or 2: things of many, flocks or grains), the count of each (a layer whose count the description writes keeps it; another takes 1 to 6 times its count), the dense place, and how wide it is (a ratio of the canvas's short side).",
            ],
            example: r#"{"targets":[{"layer":1,"count":60}],"spot":"golden_lr","extent":"0.25"}"#,
        },
    ),
    (
        "C2",
        LawText {
            name: ["文様", "Patterns"],
            family: ["カード", "card"],
            source: [
                "日本の文様（青海波・七宝・市松・鱗・亀甲）",
                "the patterns of Japan (seigaiha, shippo, ichimatsu, uroko, kikko)",
            ],
            law: [
                "一つの単位の形を、規則で敷き詰める。青海波は重なる同心の半円、七宝は重なる円、市松は二色の四角の交互、鱗は三角の交互、亀甲は六角の連なり。記述の面や群れ（水面・畑・屋根・窓・雨・雪など）を描く形として使い、単体の物には使わない。",
                "Tile the canvas with one unit shape by a rule: seigaiha is overlapping concentric semicircles, shippo overlapping circles, ichimatsu squares alternating in two colors, uroko alternating triangles, and kikko a run of hexagons. Use it as the shape that draws a surface or a crowd the description names (a water surface, fields, roofs, windows, rain, snow), not for one thing alone.",
            ],
            choose: [
                "対象の層（その層を文様の単位で描き直す）、文様、範囲（上・中・下の帯、全面、その層の今の範囲）、単位の大きさ（画面の短辺に対する比）、色（1〜2。地と明るさが 0.15 以上違う色。市松と鱗は2色で交互）。",
                "the layer (drawn again in the pattern's unit), the pattern, the area (the top, middle or bottom band, the whole canvas, the layer's current area), the unit's size (a ratio of the canvas's short side), and the colors (1 or 2, each differing from the ground in lightness by 0.15 or more; ichimatsu and uroko alternate two).",
            ],
            example: r#"{"layer":0,"pattern":"seigaiha","area":"bottom_band","unit":"1/8","colors":["white"]}"#,
        },
    ),
    (
        "C3",
        LawText {
            name: ["ポリリズム", "Polyrhythm"],
            family: ["カード", "card"],
            source: [
                "音楽の複合リズム（2対3・3対4・3対5）、Klee の多声の画",
                "the compound rhythms of music (2 against 3, 3 against 4, 3 against 5); Klee's polyphonic pictures",
            ],
            law: [
                "二つの声部を、同じ長さに違う数で等間隔に並べて重ねる。二つの拍が合う所と外れる所が、画の中に周期を作る。",
                "Lay two voices over each other, each lined up at equal spacing along the same length with a different count. Where the two beats meet and where they part makes a period in the picture.",
            ],
            choose: [
                "二つの声部にする層（1〜2。1つなら同じ物を二つの声部に分ける）、比、基の数（声部の数は 基×比 になる）、軸（横・縦・斜め）、帯の位置（画面の縦か横の比）。",
                "the layers of the two voices (1 or 2; with one, the same thing is split into two voices), the ratio, the base count (a voice's count is the base times its term of the ratio), the axis (horizontal, vertical, diagonal), and the band's place (a ratio of the canvas's height or width).",
            ],
            example: r#"{"voices":[0,1],"ratio":"2:3","base":4,"axis":"horizontal","band":"0.618"}"#,
        },
    ),
    (
        "C4",
        LawText {
            name: ["動機と変奏", "Motif and variation"],
            family: ["カード", "card"],
            source: [
                "主題と変奏、フーガの拡大・縮小・反行、カノンのずらした重ね",
                "theme and variations; the fugue's augmentation, diminution and inversion; the canon's staggered entries",
            ],
            law: [
                "一つの形（動機）を、大きさ・向き・鏡映・ずらした重ねを順に変えながら繰り返す。",
                "Repeat one shape (the motif), changing its size, its turn, its mirror image and a staggered overlap in turn.",
            ],
            choose: [
                "動機にする層、回数（記述が数を書いた層は今の数。ほかは今の数から、今の数と 9 の大きいほうまで。3以上）、変奏の列（拡大・縮小・回転・鏡映・ずらした重ねから1〜4。順に繰り返し当てる）、道筋（横の列・斜め・黄金の渦）。",
                "the motif's layer, the repeats (a layer whose count the description writes keeps it; another goes from its count up to the larger of its count and 9, 3 at least), the variations (1 to 4 of grow, shrink, rotate, mirror, echo, applied in turn and again), and the path (a horizontal row, a diagonal, the golden spiral).",
            ],
            example: r#"{"layer":0,"repeats":6,"sequence":["shrink","rotate"],"path":"golden_spiral"}"#,
        },
    ),
    (
        "C5",
        LawText {
            name: ["序破急", "Jo-ha-kyū"],
            family: ["カード", "card"],
            source: [
                "雅楽、世阿弥（能の構成）",
                "gagaku; Zeami (the structure of noh)",
            ],
            law: [
                "一つの流れを三段にする。序は静かに広い間隔で始まり、破で崩れて変わり、急で間隔が詰まって終わる。画面では、ある向きに沿って、まばら→変化→密になる。",
                "Make one flow in three stages: jo begins quiet at wide spacing, ha breaks and changes, and kyu ends with the spacing closing in. On the canvas it runs from sparse to changing to dense along one direction.",
            ],
            choose: [
                "対象の層（6個以上の物）、向き、三段の長さの比（序:破:急）、破での変化（向き・大きさ・色。色なら破の色）、急の密度（序の何倍か）。数は今のまま。",
                "the layer (6 things or more), the direction, the stages' lengths (jo:ha:kyu), the change at ha (turn, size, color; for color, ha's color), and kyu's density (how many times jo's). The count stays.",
            ],
            example: r#"{"layer":1,"direction":"bottom_to_top","lengths":"3:2:1","break_change":"size","break_color":"orange","kyu_density":"3"}"#,
        },
    ),
    (
        "C6",
        LawText {
            name: ["真・行・草", "Shin, gyō and sō"],
            family: ["カード", "card"],
            source: [
                "書の楷行草、庭・いけばな・茶の真行草",
                "the regular, running and cursive scripts of calligraphy; the shin, gyō and sō of gardens, ikebana and tea",
            ],
            law: [
                "同じ形を、厳格（真）・半ば崩す（行）・自在（草）の三つの度合いで描き分ける。",
                "Draw the same shape in three degrees: strict (shin), half loosened (gyo) and free (so).",
            ],
            choose: [
                "対象の層（3つ以上の同じ物の列か格子。束と散らす層は使えない）、分け方（三つの帯に分ける・並びの順に移る）、並びの順（真→行→草 か 草→行→真）、草の崩しの度合い。数は今のまま。",
                "the layer (a row or a grid of 3 or more of the same thing; a bundle or a scatter cannot be used), the split (into three bands, or moving along the order), the order (shin to gyo to so, or so to gyo to shin), and how far so loosens. The count stays.",
            ],
            example: r#"{"layer":0,"split":"three_bands","order":"shin_gyo_so","so_degree":"medium"}"#,
        },
    ),
];

const SYSTEM_JA: &str = "あなたは、絵画・意匠・音楽の法則を組み合わせて、作品の記述を一枚の画にする係です。
作品は、記述（作者の文）から作った楽譜です。楽譜の層（物）は、まだ法則なしで置かれています。
法則の一覧（19）から、この作品に使う法則を選び、法則ごとの値を選択肢から選んでください。座標は書きません。座標と大きさは、道具が法則から計算します。

決まり:
1. 主の法則（main_law）を一つ決めます。画を見た人が最初に読み取る、画の骨組みになる法則です。B21 は主にしません。主の層（main_layer）も一つ決めます。
2. 法則の数は、送る文の最後の「この答えの決まり」に従います。法則は、層をいくつに当てても1つと数えます。
3. 一つの層に、置き場の法則（B1〜B5・B7・B8）は一つ、並びの法則（B9・B10・B12）は一つまで。C1〜C6 は置き場と並びを作り直すので、同じ層に、ほかの置き場・並びの法則や、ほかの C1〜C6 を重ねません。大きさの法則（B6・B10・B12・B15・C4）は掛け合わせます。
4. 記述が名指した物の種類と道具は変えません。記述そのものが数を書いた物（「一羽」「三度」など）は数を変えず、その層の番号を description_counts に入れます。
5. 道具は、置き場 → 大きさ → 並び → C1〜C6 → 空気遠近 → 手 の順に当てます。決まりに合わない答えは、理由を添えて返されます。
6. 1作品の痕は 380、指示は 60 までです。
7. reason には、記述の言葉を「」で引いて、主の法則を選んだ理由を1〜2行で書きます。
答えは決まった形の JSON で返します。laws には、使う法則の番号を鍵にして、法則ごとの値を書きます。";

const SYSTEM_EN: &str = "You combine laws of painting, design and music to make a work's description into one picture.
The work is a Score made from the description (the author's words). The Score's layers (things) are placed without laws yet.
From the list of laws (19), choose the laws this work uses and, for each law, its values from the choices. Write no coordinates: the tool computes coordinates and sizes from the laws.

Rules:
1. Choose one main law (main_law): the law a viewer reads first, the framework of the picture. B21 is never the main law. Choose one main layer (main_layer) too.
2. The number of laws follows \"The rule of this answer\" at the end of the message. A law counts as one however many layers it takes.
3. A layer takes one placement law (B1 to B5, B7, B8) and one arrangement law (B9, B10, B12) at most. C1 to C6 rebuild a layer's place and arrangement, so a layer that takes one of them takes no other placement or arrangement law and no other of C1 to C6. The size laws (B6, B10, B12, B15, C4) multiply.
4. Keep the kinds of things and the tools the description names. Keep the count of a thing the description itself counts (\"one heron\", \"three times\"), and put that layer's number in description_counts.
5. The tool applies placement, then size, then arrangement, then C1 to C6, then aerial perspective, then the hand. An answer that breaks the rules comes back with the reason.
6. A work holds 380 marks and 60 instructions at most.
7. In reason, quote the description's words in “ ” and say in one or two lines why you chose the main law.
Return the answer as JSON of the given shape. In laws, key each law you use by its number and write its values.";

const LAYER_NOTE: [&str; 2] = [
    "box は層の痕が占める矩形 [x0, y0, x1, y1]（画面を 0〜1 とする）、mark_size は痕1つの幅と高さ。arranged は並べ方: place は1か所に置く（数が2以上なら同じ所に重ねた束）、row_horizontal・row_vertical・row_diagonal は列、grid は格子、scatter は散らす、fill はほかの形の中に塗り込める形（置き場と並びを変えられない）、plugin は差し込みの形（法則を当てられない）。",
    "box is the rectangle [x0, y0, x1, y1] the layer's marks cover (the canvas is 0 to 1); mark_size is the width and height of one mark. arranged is how the layer is arranged: place puts it at one spot (with a count of 2 or more, a bundle at that spot), row_horizontal, row_vertical and row_diagonal are rows, grid is a grid, scatter scatters, fill is a shape filled inside another shape (its place and arrangement cannot change), and plugin is a plugged-in shape (no law takes it).",
];

const AT_NOTE: [&str; 2] = [
    "比例（B1〜B4）の at: point_ul・point_ur・point_ll・point_lr は4つの交点（左上・右上・左下・右下）、line_left・line_right は左と右の縦の線、line_top・line_bottom は上と下の横の線。span（線に置く時だけ）: full は全幅（端から 0.118 の余白）、current は今の長さ。線の層は線に沿わせ、複数の物は線の上に並ぶ。交点に置くと、閉じた形は中心がそこに来て、複数の物は今の並びのまま寄る。",
    "at for the proportion laws (B1 to B4): point_ul, point_ur, point_ll and point_lr are the four crossings (upper left, upper right, lower left, lower right); line_left and line_right are the left and right vertical lines; line_top and line_bottom are the upper and lower horizontal lines. span (only when placing on a line): full is the full width (a margin of 0.118 from the edges), current keeps the current length. A line layer is laid along the line, and several things are lined up on it. At a crossing, a closed shape is centered there and several things move there in their current arrangement.",
];

const EXAMPLE_DESCRIPTION: [&str; 2] = [
    "冬の朝、雪の野に、赤い実をつけた一本の木が立っていた。",
    "On a winter morning, a single tree hung with red berries stood in a snowy field.",
];

/// The example's layers, as the prototype printed them.
const EXAMPLE_LAYERS: [&str; 3] = [
    r#"{"layer":0,"shape":"line","tool":"brush_thick","count":1,"color":"black","filled":false,"arranged":"place","box":[0.3,0.2,0.7,0.9],"mark_size":[0.7,0.0]}"#,
    r#"{"layer":1,"shape":"circle","tool":"brush_thin","count":7,"color":"red","filled":true,"arranged":"place","box":[0.4,0.2,0.6,0.4],"mark_size":[0.03,0.03]}"#,
    r#"{"layer":2,"shape":"point","tool":"chalk","count":40,"color":"white","filled":true,"arranged":"scatter","box":[0.0,0.0,1.0,1.0],"mark_size":[0.004,0.004]}"#,
];

/// The prototype's example answer with the laws of this stage only.
const EXAMPLE_ANSWER: [&str; 2] = [
    r#"{"main_layer":0,"main_law":"B1","description_counts":[0],"laws":{"B1":{"targets":[{"layer":0,"at":"line_left","span":"full"}]},"C1":{"targets":[{"layer":1,"count":21}],"spot":"golden_ul","extent":"0.15"},"B21":{"targets":[{"layer":2,"hand":"fine"}]}},"reason":"「一本の木が立っていた」の木を画の骨にするため、幹を黄金分割の左の線に全幅で立てた。"}"#,
    r#"{"main_layer":0,"main_law":"B1","description_counts":[0],"laws":{"B1":{"targets":[{"layer":0,"at":"line_left","span":"full"}]},"C1":{"targets":[{"layer":1,"count":21}],"spot":"golden_ul","extent":"0.15"},"B21":{"targets":[{"layer":2,"hand":"fine"}]}},"reason":"To make the tree of “a single tree … stood” the bone of the picture, its trunk stands at full length on the golden section's left line."}"#,
];

/// The head of the table of the work's nine colors, shown when the run's
/// palette has observations.
const COLOR_HEAD: [&str; 2] = [
    "## この作品のカタログの色（9つの色名と、それが描く色。lightness は明るさ 0〜1、chroma は鮮やかさ、hue は色相の角度）",
    "## The colors of this work's catalog (the nine color names and the colors they draw; lightness is the lightness from 0 to 1, chroma the vividness and hue the hue angle)",
];

const COUNT_RULE: [&str; 2] = [
    "## この答えの決まり（V2）\n主の法則を支える法則を1つか2つだけ選ぶ。laws は主を含めて2〜3にする。",
    "## The rule of this answer (V2)\nChoose only one or two laws that support the main law. laws holds two or three laws, the main law included.",
];

const ABSENT_MARK: [&str; 2] = [
    "（この作品では当てる層が無い）",
    " (no layer of this work can take it)",
];
const EXCLUDED_MARK: [&str; 2] = ["（この推敲では使わない）", " (not used in this refinement)"];
const DIRECTION_HEAD: [&str; 2] = ["## 推敲の向き", "## The direction of this refinement"];
const CARDS_INVITED: [&str; 2] = [
    "カード（C1〜C6）を主の法則に選ぶことを考える。カードは層を作り直し、画を大きく変える。",
    "Consider a card (C1 to C6) as the main law. A card rebuilds a layer and changes the picture a lot.",
];
const NOTE_HEAD: [&str; 2] = ["## 作者の方向性", "## The author's direction"];

pub(crate) fn language_index(language: ResolvedInstructionLanguage) -> usize {
    match language {
        ResolvedInstructionLanguage::Ja => 0,
        ResolvedInstructionLanguage::En => 1,
    }
}

fn message(
    description: &str,
    context: &LawsContext,
    language: ResolvedInstructionLanguage,
) -> String {
    let at = language_index(language);
    let ground = context.score.background.as_str();
    let mut lines: Vec<String> = Vec::new();
    let heads = match language {
        ResolvedInstructionLanguage::Ja => [
            "## 記述",
            "## 楽譜の層（法則を当てる前）",
            "## 地: ",
            "## 法則の一覧（19）",
            "## 答え全体の例（この作品と別の記述）",
        ],
        ResolvedInstructionLanguage::En => [
            "## Description",
            "## The Score's layers (before the laws)",
            "## Ground: ",
            "## The laws (19)",
            "## A whole answer (for another description)",
        ],
    };
    lines.push(heads[0].to_owned());
    lines.push(description.to_owned());
    lines.push(String::new());
    // A refinement's direction (2026-10-20); a description run has none.
    let offered = context.offered();
    if context.direction.cards == CardsOffer::Invite
        && REBUILD.iter().any(|card| offered.contains(card))
    {
        lines.push(DIRECTION_HEAD[at].to_owned());
        lines.push(CARDS_INVITED[at].to_owned());
        lines.push(String::new());
    }
    if let Some(note) = &context.direction.note {
        lines.push(NOTE_HEAD[at].to_owned());
        lines.push(note.trim().to_owned());
        lines.push(String::new());
    }
    lines.push(heads[1].to_owned());
    lines.push(LAYER_NOTE[at].to_owned());
    for summary in &context.summaries {
        lines.push(serde_json::to_string(summary).unwrap_or_default());
    }
    lines.push(String::new());
    lines.push(format!("{}{ground}", heads[2]));
    lines.push(String::new());
    // The colors' lightness, so that a reader sees which of them the ground hides.
    if let Some(colors) = &context.colors {
        lines.push(COLOR_HEAD[at].to_owned());
        for color in colors {
            lines.push(serde_json::to_string(color).unwrap_or_default());
        }
        lines.push(String::new());
    }
    lines.push(heads[3].to_owned());
    lines.push(AT_NOTE[at].to_owned());
    for (law, text) in &LAW_TEXTS {
        let mark = if context.excluded(law) {
            EXCLUDED_MARK[at]
        } else if !offered.contains(law) {
            ABSENT_MARK[at]
        } else {
            ""
        };
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => {
                format!("### {law} {}（{}）{mark}", text.name[0], text.family[0])
            }
            ResolvedInstructionLanguage::En => {
                format!("### {law} {} ({}){mark}", text.name[1], text.family[1])
            }
        });
        let labels = match language {
            ResolvedInstructionLanguage::Ja => ["典拠: ", "法則: ", "選ぶもの: ", "例: "],
            ResolvedInstructionLanguage::En => ["Source: ", "Law: ", "Choose: ", "Example: "],
        };
        lines.push(format!("{}{}", labels[0], text.source[at]));
        lines.push(format!("{}{}", labels[1], text.law[at]));
        lines.push(format!("{}{}", labels[2], text.choose[at]));
        lines.push(format!("{}{}", labels[3], text.example));
    }
    lines.push(String::new());
    lines.push(heads[4].to_owned());
    let labels = match language {
        ResolvedInstructionLanguage::Ja => ["記述: ", "層:", "答え: "],
        ResolvedInstructionLanguage::En => ["Description: ", "Layers:", "Answer: "],
    };
    lines.push(format!("{}{}", labels[0], EXAMPLE_DESCRIPTION[at]));
    lines.push(labels[1].to_owned());
    lines.extend(EXAMPLE_LAYERS.iter().map(|layer| (*layer).to_owned()));
    lines.push(format!("{}{}", labels[2], EXAMPLE_ANSWER[at]));
    lines.push(String::new());
    lines.push(COUNT_RULE[at].to_owned());
    lines.join("\n")
}

fn layer_enum(layers: &[usize]) -> Value {
    json!({"type": "integer", "enum": layers})
}

fn targets(item: Value) -> Value {
    json!({"type": "array", "minItems": 1, "items": item})
}

/// The schema of one law's values in this work, or `None` when no layer can
/// take it. Each object names its property order, the prototype's.
fn law_schema(law: &str, context: &LawsContext) -> Option<Value> {
    let layers = context.candidates(law);
    if layers.is_empty() {
        return None;
    }
    let layer = layer_enum(&layers);
    let proportion = json!({
        "type": "object",
        "propertyOrdering": ["layer", "at", "span"],
        "properties": {
            "layer": layer,
            "at": {"type": "string", "enum": ["point_ul", "point_ur", "point_ll", "point_lr", "line_left", "line_right", "line_top", "line_bottom"]},
            "span": {"type": "string", "enum": ["full", "current"]}
        },
        "required": ["layer", "at"]
    });
    Some(match law {
        "B1" | "B2" | "B3" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(proportion)},
            "required": ["targets"]
        }),
        "B4" => json!({
            "type": "object",
            "propertyOrdering": ["ratio", "targets"],
            "properties": {
                "ratio": {"type": "string", "enum": ["2:3", "3:4"]},
                "targets": targets(proportion)
            },
            "required": ["ratio", "targets"]
        }),
        "B5" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(json!({
                "type": "object",
                "propertyOrdering": ["layer", "path"],
                "properties": {
                    "layer": layer,
                    "path": {"type": "string", "enum": ["diagonal_down", "diagonal_up", "center_vertical", "center_horizontal"]}
                },
                "required": ["layer", "path"]
            }))},
            "required": ["targets"]
        }),
        "B6" => json!({
            "type": "object",
            "propertyOrdering": ["secondary", "accent"],
            "properties": {
                "secondary": {"type": "array", "items": layer},
                "accent": {"type": "array", "items": layer}
            }
        }),
        "B7" => json!({
            "type": "object",
            "propertyOrdering": ["layer"],
            "properties": {"layer": layer},
            "required": ["layer"]
        }),
        "B8" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(json!({
                "type": "object",
                "propertyOrdering": ["layer", "axis"],
                "properties": {
                    "layer": layer,
                    "axis": {"type": "string", "enum": ["vertical", "horizontal", "both"]}
                },
                "required": ["layer", "axis"]
            }))},
            "required": ["targets"]
        }),
        "B9" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(json!({
                "type": "object",
                "propertyOrdering": ["layer", "form"],
                "properties": {
                    "layer": layer,
                    "form": {"type": "string", "enum": ["row", "grid"]}
                },
                "required": ["layer", "form"]
            }))},
            "required": ["targets"]
        }),
        "B10" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(json!({
                "type": "object",
                "propertyOrdering": ["layer", "change", "ratio", "toward"],
                "properties": {
                    "layer": layer,
                    "change": {"type": "string", "enum": ["size", "spacing"]},
                    "ratio": {"type": "string", "enum": ["0.618", "0.382"]},
                    "toward": {"type": "string", "enum": ["left", "right", "top", "bottom"]}
                },
                "required": ["layer", "change", "ratio", "toward"]
            }))},
            "required": ["targets"]
        }),
        "B12" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(json!({
                "type": "object",
                "propertyOrdering": ["layer", "group", "strong"],
                "properties": {
                    "layer": layer,
                    "group": {"type": "string", "enum": ["2", "3", "4"]},
                    "strong": {"type": "string", "enum": ["first", "none"]}
                },
                "required": ["layer", "group", "strong"]
            }))},
            "required": ["targets"]
        }),
        "B15" => json!({
            "type": "object",
            "propertyOrdering": ["layers"],
            "properties": {"layers": {"type": "array", "minItems": 1, "items": layer}},
            "required": ["layers"]
        }),
        "B21" => json!({
            "type": "object",
            "propertyOrdering": ["targets"],
            "properties": {"targets": targets(json!({
                "type": "object",
                "propertyOrdering": ["layer", "hand"],
                "properties": {
                    "layer": layer,
                    "hand": {"type": "string", "enum": ["still", "fine", "keep"]}
                },
                "required": ["layer", "hand"]
            }))},
            "required": ["targets"]
        }),
        "C1" => json!({
            "type": "object",
            "propertyOrdering": ["targets", "spot", "extent"],
            "properties": {
                "targets": {"type": "array", "minItems": 1, "maxItems": 2, "items": {
                    "type": "object",
                    "propertyOrdering": ["layer", "count"],
                    "properties": {
                        "layer": layer,
                        "count": {"type": "integer", "minimum": 1, "maximum": 240}
                    },
                    "required": ["layer", "count"]
                }},
                "spot": {"type": "string", "enum": SPOTS.map(|(name, _)| name)},
                "extent": {"type": "string", "enum": ["0.15", "0.25", "0.35"]}
            },
            "required": ["targets", "spot", "extent"]
        }),
        "C2" => json!({
            "type": "object",
            "propertyOrdering": ["layer", "pattern", "area", "unit", "colors"],
            "properties": {
                "layer": layer,
                "pattern": {"type": "string", "enum": ["seigaiha", "shippo", "ichimatsu", "uroko", "kikko"]},
                "area": {"type": "string", "enum": ["top_band", "middle_band", "bottom_band", "whole", "current"]},
                "unit": {"type": "string", "enum": ["1/12", "1/8", "1/5"]},
                "colors": {"type": "array", "minItems": 1, "maxItems": 2, "items": color_enum()}
            },
            "required": ["layer", "pattern", "area", "unit", "colors"]
        }),
        "C3" => json!({
            "type": "object",
            "propertyOrdering": ["voices", "ratio", "base", "axis", "band"],
            "properties": {
                "voices": {"type": "array", "minItems": 1, "maxItems": 2, "items": layer},
                "ratio": {"type": "string", "enum": ["2:3", "3:4", "3:5"]},
                "base": {"type": "integer", "minimum": 2, "maximum": 8},
                "axis": {"type": "string", "enum": ["horizontal", "vertical", "diagonal"]},
                "band": {"type": "string", "enum": ["0.382", "0.5", "0.618"]}
            },
            "required": ["voices", "ratio", "base", "axis", "band"]
        }),
        "C4" => json!({
            "type": "object",
            "propertyOrdering": ["layer", "repeats", "sequence", "path"],
            "properties": {
                "layer": layer,
                "repeats": {"type": "integer", "minimum": 3, "maximum": context.max_count().max(9)},
                "sequence": {"type": "array", "minItems": 1, "maxItems": 4,
                             "items": {"type": "string", "enum": ["grow", "shrink", "rotate", "mirror", "echo"]}},
                "path": {"type": "string", "enum": ["row", "diagonal", "golden_spiral"]}
            },
            "required": ["layer", "repeats", "sequence", "path"]
        }),
        "C5" => json!({
            "type": "object",
            "propertyOrdering": ["layer", "direction", "lengths", "break_change", "break_color", "kyu_density"],
            "properties": {
                "layer": layer,
                "direction": {"type": "string", "enum": ["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"]},
                "lengths": {"type": "string", "enum": ["3:2:1", "2:2:1", "1:1:1"]},
                "break_change": {"type": "string", "enum": ["rotate", "size", "color"]},
                "break_color": color_enum(),
                "kyu_density": {"type": "string", "enum": ["2", "3", "4"]}
            },
            "required": ["layer", "direction", "lengths", "break_change", "break_color", "kyu_density"]
        }),
        "C6" => json!({
            "type": "object",
            "propertyOrdering": ["layer", "split", "order", "so_degree"],
            "properties": {
                "layer": layer,
                "split": {"type": "string", "enum": ["three_bands", "sequence"]},
                "order": {"type": "string", "enum": ["shin_gyo_so", "so_gyo_shin"]},
                "so_degree": {"type": "string", "enum": ["small", "medium", "large"]}
            },
            "required": ["layer", "split", "order", "so_degree"]
        }),
        _ => return None,
    })
}

fn color_enum() -> Value {
    json!({"type": "string", "enum": COLORS.map(|color| color.as_str())})
}

/// The places C1 may make dense: the golden section's and the thirds'
/// crossings (as the prototype wrote them) and the center.
const SPOTS: [(&str, [f64; 2]); 9] = [
    ("golden_ul", [0.382, 0.382]),
    ("golden_ur", [0.618, 0.382]),
    ("golden_ll", [0.382, 0.618]),
    ("golden_lr", [0.618, 0.618]),
    ("third_ul", [1.0 / 3.0, 1.0 / 3.0]),
    ("third_ur", [2.0 / 3.0, 1.0 / 3.0]),
    ("third_ll", [1.0 / 3.0, 2.0 / 3.0]),
    ("third_lr", [2.0 / 3.0, 2.0 / 3.0]),
    ("center", [0.5, 0.5]),
];

/// The answer's schema for this work, its choices narrowed to the work's layers.
#[must_use]
pub fn laws_response_schema(context: &LawsContext) -> Value {
    let all: Vec<usize> = context
        .summaries
        .iter()
        .map(|summary| summary.layer)
        .collect();
    let layer = layer_enum(&all);
    let mut laws = Map::new();
    let mut order = Vec::new();
    for law in LAWS {
        if let Some(schema) = law_schema(law, context) {
            laws.insert(law.to_owned(), schema);
            order.push(law);
        }
    }
    let main: Vec<&str> = order.iter().copied().filter(|law| *law != "B21").collect();
    json!({
        "type": "object",
        "propertyOrdering": ["main_layer", "main_law", "description_counts", "laws", "reason"],
        "properties": {
            "main_layer": layer,
            "main_law": {"type": "string", "enum": main},
            "description_counts": {"type": "array", "items": layer},
            "laws": {"type": "object", "propertyOrdering": order, "properties": laws},
            "reason": {"type": "string"}
        },
        "required": ["main_layer", "main_law", "description_counts", "laws", "reason"]
    })
}

/// Build the `choose_laws` request for a composed work. It fails when no law
/// but the hand's can take a layer of the work: there is nothing to choose.
pub fn build_laws_prompt(
    description: &str,
    context: &LawsContext,
    language: ResolvedInstructionLanguage,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    crate::prompts::require_nonempty("description", description)?;
    crate::prompts::require_within("description", description.len(), limits.max_source_bytes)?;
    if !context.offered().iter().any(|law| *law != "B21") {
        return Err(PromptError::EmptyField { field: "laws" });
    }
    let system = match language {
        ResolvedInstructionLanguage::Ja => SYSTEM_JA,
        ResolvedInstructionLanguage::En => SYSTEM_EN,
    }
    .to_owned();
    crate::prompts::finish_prompt(LlmPrompt {
        schema_id: crate::prompts::LLM_PROMPT_SCHEMA_ID.to_owned(),
        prompt_id: LAWS_PROMPT_ID.to_owned(),
        stage: LlmStage::ChooseLaws,
        action_name: LlmStage::ChooseLaws.action_name().to_owned(),
        instruction_language: language,
        system,
        message: message(description, context, language),
        response_schema: laws_response_schema(context),
        prompt_digest: String::new(),
        saijiki_asset_id: None,
        saijiki_asset_digest: None,
        macro_catalog_digest: None,
        base_source_digest: None,
        base_compiler_lock_digest: None,
    })
}

/// The request again with the tool's reply to the answer it refused: the
/// original message, the refused answer as it was written and the latest
/// reason only. An answer too long to read is not repeated; without an answer
/// (the color stage) the reply is the reason only, as the prototype resent it.
pub(crate) fn with_laws_feedback(
    mut prompt: LlmPrompt,
    refusal: &Refusal,
    answer: Option<&str>,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    let answer = answer.filter(|_| refusal.code != "too_long");
    let shown = |label: &str| {
        answer
            .map(|answer| format!("{label}\n{}\n", answer.trim()))
            .unwrap_or_default()
    };
    let reply = match prompt.instruction_language {
        ResolvedInstructionLanguage::Ja => format!(
            "\n\n## 前の答えへの道具の返事\n{}前の答えは使えなかった: {}\n直した答えを返す。",
            shown("前の答え:"),
            refusal.ja
        ),
        ResolvedInstructionLanguage::En => format!(
            "\n\n## The tool's reply to the previous answer\n{}The previous answer could not be used: {}\nReturn a corrected answer.",
            shown("The previous answer:"),
            refusal.en
        ),
    };
    prompt.message.push_str(&reply);
    crate::prompts::require_within(
        "message",
        prompt.message.len(),
        limits.max_source_bytes.saturating_mul(4),
    )?;
    prompt.prompt_digest = String::new();
    crate::prompts::finish_prompt(prompt)
}

// --- the answer ----------------------------------------------------------------------------------

/// Why the tool refused an answer: a stable code and the reason in both
/// languages, which the next request carries.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Refusal {
    pub code: &'static str,
    pub ja: String,
    pub en: String,
}

pub(crate) fn refusal(code: &'static str, ja: String, en: String) -> Refusal {
    Refusal { code, ja, en }
}

pub(crate) fn shown(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        other => other.to_string(),
    }
}

/// The answer against its schema: the transport may not hold a reply to it.
pub(crate) fn conform(value: &Value, schema: &Value, path: &str) -> Result<(), Refusal> {
    match schema.get("type").and_then(Value::as_str) {
        Some("object") => {
            let Some(object) = value.as_object() else {
                return Err(refusal(
                    "not_object",
                    format!("{path} はオブジェクトでない"),
                    format!("{path} is not an object"),
                ));
            };
            for key in schema["required"].as_array().into_iter().flatten() {
                let key = key.as_str().unwrap_or_default();
                if !object.contains_key(key) {
                    return Err(refusal(
                        "missing",
                        format!("{path}.{key} が無い"),
                        format!("{path}.{key} is missing"),
                    ));
                }
            }
            if let Some(properties) = schema.get("properties").and_then(Value::as_object) {
                let order: Vec<&str> = schema["propertyOrdering"]
                    .as_array()
                    .map(|keys| keys.iter().filter_map(Value::as_str).collect())
                    .unwrap_or_else(|| properties.keys().map(String::as_str).collect());
                for key in order {
                    if let (Some(item), Some(sub)) = (object.get(key), properties.get(key))
                        && !item.is_null()
                    {
                        conform(item, sub, &format!("{path}.{key}"))?;
                    }
                }
            }
        }
        Some("array") => {
            let Some(items) = value.as_array() else {
                return Err(refusal(
                    "not_array",
                    format!("{path} は配列でない"),
                    format!("{path} is not an array"),
                ));
            };
            let minimum = schema["minItems"].as_u64().unwrap_or(0);
            let maximum = schema["maxItems"].as_u64();
            let length = items.len() as u64;
            if length < minimum || maximum.is_some_and(|maximum| length > maximum) {
                let most = maximum.map_or_else(String::new, |maximum| maximum.to_string());
                return Err(refusal(
                    "count",
                    format!("{path} の数が {minimum}〜{most} の外"),
                    format!("{path} has a length outside {minimum} to {most}"),
                ));
            }
            for (index, item) in items.iter().enumerate() {
                conform(item, &schema["items"], &format!("{path}[{index}]"))?;
            }
        }
        Some("integer") if !(value.is_u64() || value.is_i64()) => {
            return Err(refusal(
                "not_integer",
                format!("{path} は整数でない"),
                format!("{path} is not an integer"),
            ));
        }
        Some("integer") => {
            let number = value.as_i64().unwrap_or(i64::MAX);
            let minimum = schema["minimum"].as_i64();
            let maximum = schema["maximum"].as_i64();
            if minimum.is_some_and(|minimum| number < minimum)
                || maximum.is_some_and(|maximum| number > maximum)
            {
                let shown =
                    |bound: Option<i64>| bound.map_or("None".to_owned(), |bound| bound.to_string());
                return Err(refusal(
                    "out_of_range",
                    format!(
                        "{path} = {} は {}〜{} の外",
                        shown(Some(number)),
                        shown(minimum),
                        shown(maximum)
                    ),
                    format!(
                        "{path} = {} is outside {} to {}",
                        shown(Some(number)),
                        shown(minimum),
                        shown(maximum)
                    ),
                ));
            }
        }
        Some("string") if !value.is_string() => {
            return Err(refusal(
                "not_string",
                format!("{path} は文字列でない"),
                format!("{path} is not a string"),
            ));
        }
        Some("boolean") if !value.is_boolean() => {
            return Err(refusal(
                "not_boolean",
                format!("{path} は真偽でない"),
                format!("{path} is not a boolean"),
            ));
        }
        _ => {}
    }
    if let Some(choices) = schema.get("enum").and_then(Value::as_array)
        && !choices.contains(value)
    {
        let listed: Vec<String> = choices.iter().map(shown).collect();
        return Err(refusal(
            "not_a_choice",
            format!(
                "{path} = {} は選択肢 {} に無い",
                shown(value),
                listed.join("・")
            ),
            format!(
                "{path} = {} is not one of {}",
                shown(value),
                listed.join(", ")
            ),
        ));
    }
    Ok(())
}

pub(crate) fn layer_number(value: &Value) -> usize {
    value
        .as_u64()
        .and_then(|layer| usize::try_from(layer).ok())
        .unwrap_or(usize::MAX)
}

/// The layers a law names, as the prototype collected them.
fn law_targets(law: &str, value: &Value) -> Vec<usize> {
    let list = |key: &str| -> Vec<usize> {
        value[key]
            .as_array()
            .into_iter()
            .flatten()
            .map(layer_number)
            .collect()
    };
    match law {
        "B1" | "B2" | "B3" | "B4" | "B5" | "B8" | "B9" | "B10" | "B12" | "B21" => value["targets"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|target| layer_number(&target["layer"]))
            .collect(),
        "B6" => {
            let mut layers = list("secondary");
            layers.extend(list("accent"));
            layers
        }
        "B7" | "C2" | "C4" | "C5" | "C6" => vec![layer_number(&value["layer"])],
        "B15" => list("layers"),
        "C1" => value["targets"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|target| layer_number(&target["layer"]))
            .collect(),
        "C3" => list("voices"),
        _ => Vec::new(),
    }
}

/// A conformed answer: the laws in the order this stage applies them.
struct Answer {
    main_layer: usize,
    main_law: String,
    laws: BTreeMap<&'static str, Value>,
    /// The layers whose count the description itself writes.
    fixed: BTreeSet<usize>,
    /// The reader's reason, kept to [`REASON_LIMIT`] characters.
    reason: String,
}

/// The most characters of the reader's reason a work keeps.
const REASON_LIMIT: usize = 2000;

/// Read an answer and check it against the schema and the prototype's rules.
/// `count_rule` checks that the laws are two or three (the request's V2 rule).
fn check(answer: &Value, context: &LawsContext, count_rule: bool) -> Result<Answer, Refusal> {
    conform(answer, &laws_response_schema(context), "answer")?;
    let offered = context.offered();
    let laws_value = answer["laws"].as_object().cloned().unwrap_or_default();
    let mut laws = BTreeMap::new();
    for (law, value) in &laws_value {
        let Some(known) = LAWS.into_iter().find(|candidate| candidate == law) else {
            return Err(refusal(
                "unknown_law",
                format!("laws の {law} は法則の一覧に無い"),
                format!("{law} in laws is not in the list of laws"),
            ));
        };
        if context.excluded(known) {
            return Err(refusal(
                "excluded_law",
                format!("{law} はこの推敲では使わない"),
                format!("{law} is not used in this refinement"),
            ));
        }
        if !offered.contains(&known) {
            return Err(refusal(
                "law_without_layer",
                format!("{law} はこの作品では当てる層が無い"),
                format!("no layer of this work can take {law}"),
            ));
        }
        laws.insert(known, value.clone());
    }
    if laws.is_empty() {
        return Err(refusal(
            "no_laws",
            "laws が空。主の法則を入れる".to_owned(),
            "laws is empty; put the main law in it".to_owned(),
        ));
    }
    let main_law = answer["main_law"].as_str().unwrap_or_default().to_owned();
    if !laws.contains_key(main_law.as_str()) {
        return Err(refusal(
            "main_law_missing",
            format!("主の法則 {main_law} が laws に無い"),
            format!("the main law {main_law} is not in laws"),
        ));
    }
    if main_law == "B21" {
        return Err(refusal(
            "hand_as_main",
            "B21 は主の法則にしない".to_owned(),
            "B21 is never the main law".to_owned(),
        ));
    }
    if count_rule && !(2..=3).contains(&laws.len()) {
        let names: Vec<&str> = laws.keys().copied().collect();
        return Err(refusal(
            "law_count",
            format!(
                "V2 では法則は主を含めて2〜3（今は {}: {}）",
                laws.len(),
                names.join(", ")
            ),
            format!(
                "V2 takes two or three laws with the main law (now {}: {})",
                laws.len(),
                names.join(", ")
            ),
        ));
    }
    let mut placed: BTreeMap<usize, Vec<&str>> = BTreeMap::new();
    let mut arranging: BTreeMap<usize, Vec<&str>> = BTreeMap::new();
    // The placement, arrangement and card laws that name each layer.
    let mut roles: BTreeMap<usize, Vec<&str>> = BTreeMap::new();
    for (law, value) in &laws {
        let seen = law_targets(law, value);
        if seen.iter().collect::<BTreeSet<_>>().len() != seen.len() {
            return Err(refusal(
                "layer_twice",
                format!("{law} が同じ層を二度名指している"),
                format!("{law} names a layer twice"),
            ));
        }
        for layer in seen {
            if context.summary(layer).is_none() {
                return Err(refusal(
                    "no_such_layer",
                    format!("{law}: layer {layer} は楽譜に無い"),
                    format!("{law}: the Score has no layer {layer}"),
                ));
            }
            if PLACEMENT.contains(law) {
                placed.entry(layer).or_default().push(law);
            }
            if ARRANGEMENT.contains(law) {
                arranging.entry(layer).or_default().push(law);
            }
            if PLACEMENT.contains(law) || ARRANGEMENT.contains(law) || REBUILD.contains(law) {
                roles.entry(layer).or_default().push(law);
            }
        }
    }
    for (layer, found) in &placed {
        if found.len() > 1 {
            return Err(refusal(
                "two_placements",
                format!(
                    "layer {layer} に置き場の法則が二つ（{}）。一つにする",
                    found.join("・")
                ),
                format!(
                    "layer {layer} takes two placement laws ({}); keep one",
                    found.join(", ")
                ),
            ));
        }
    }
    for (layer, found) in &mut arranging {
        if found.len() > 1 {
            // In the order of the list of laws (the answer's keys sort as text).
            found.sort_by_key(|law| LAWS.iter().position(|known| known == law));
            return Err(refusal(
                "arrangement_twice",
                format!(
                    "layer {layer} に並びの法則が二つ（{}）。一つにする",
                    found.join("・")
                ),
                format!(
                    "layer {layer} takes two arrangement laws ({}); keep one",
                    found.join(", ")
                ),
            ));
        }
    }
    for (layer, found) in &mut roles {
        if found.len() > 1 && found.iter().any(|law| REBUILD.contains(law)) {
            found.sort_by_key(|law| LAWS.iter().position(|known| known == law));
            return Err(refusal(
                "rebuild_shared",
                format!(
                    "layer {layer} は C1〜C6 が置き場と並びを作り直すので、ほかの置き場・並びの法則や C1〜C6 と重ねられない（{}）",
                    found.join("・")
                ),
                format!(
                    "C1 to C6 rebuild layer {layer}'s place and arrangement, so it takes no other placement or arrangement law and no other of C1 to C6 ({})",
                    found.join(", ")
                ),
            ));
        }
    }
    let main_layer = layer_number(&answer["main_layer"]);
    if let Some(value) = laws.get("B6") {
        let shape = context.shape(main_layer);
        if !shape.is_some_and(|shape| SIZED.contains(&shape))
            || !context.movable().contains(&main_layer)
        {
            let shape = shape.map_or("", Primitive::as_str);
            let arranged = context.arranged(main_layer).unwrap_or_default();
            return Err(refusal(
                "subordination_main",
                format!(
                    "主の層 {main_layer} は {shape}（{arranged}）で、大きさの主従の基にならない。B6 を外すか主の層を変える"
                ),
                format!(
                    "the main layer {main_layer} is {shape} ({arranged}) and cannot lead subordination; drop B6 or change the main layer"
                ),
            ));
        }
        let named = law_targets("B6", value);
        if named.contains(&main_layer) {
            return Err(refusal(
                "subordination_of_main",
                "B6 の従・添えに主の層を入れない".to_owned(),
                "B6 does not take the main layer as secondary or accent".to_owned(),
            ));
        }
        if named.is_empty() {
            return Err(refusal(
                "subordination_empty",
                "B6 は従か添えの層を一つ以上名指す".to_owned(),
                "B6 names one secondary or accent layer at least".to_owned(),
            ));
        }
    }
    if let Some(value) = laws.get("B7")
        && layer_number(&value["layer"]) == main_layer
    {
        return Err(refusal(
            "balance_main",
            "B7 は主でない層を釣り合わせる".to_owned(),
            "B7 balances a layer that is not the main layer".to_owned(),
        ));
    }
    if let (Some(hands), Some(c6)) = (laws.get("B21"), laws.get("C6"))
        && law_targets("B21", hands).contains(&layer_number(&c6["layer"]))
    {
        return Err(refusal(
            "hand_on_c6",
            "C6 の層の手は C6 が決めるので、B21 を重ねない".to_owned(),
            "C6 sets its layer's hand, so B21 does not take that layer".to_owned(),
        ));
    }
    let fixed: BTreeSet<usize> = answer["description_counts"]
        .as_array()
        .into_iter()
        .flatten()
        .map(layer_number)
        .collect();
    for (law, ja, en) in [("C2", "文様", "a pattern"), ("C3", "声部", "voices")] {
        let Some(value) = laws.get(law) else {
            continue;
        };
        if let Some(layer) = law_targets(law, value)
            .into_iter()
            .find(|layer| fixed.contains(layer))
        {
            return Err(refusal(
                "counted_layer",
                format!("layer {layer} は記述が数を書いた物なので、数の変わる{ja}にできない"),
                format!(
                    "the description writes the count of layer {layer}, so it cannot become {en}, whose count changes"
                ),
            ));
        }
    }
    if let Some(value) = laws.get("C1") {
        for target in value["targets"].as_array().into_iter().flatten() {
            let layer = layer_number(&target["layer"]);
            let count = context.count(layer);
            let wanted = target["count"].as_u64().unwrap_or(0);
            if fixed.contains(&layer) && wanted != count {
                return Err(refusal(
                    "count_kept",
                    format!("layer {layer} は記述が数を書いた物なので {count} のまま"),
                    format!(
                        "the description writes the count of layer {layer}, so it stays {count}"
                    ),
                ));
            }
            if wanted > 6 * count && !fixed.contains(&layer) {
                return Err(refusal(
                    "count_six_times",
                    format!("layer {layer} の数は今の6倍（{}）まで", 6 * count),
                    format!(
                        "layer {layer} takes up to six times its count ({})",
                        6 * count
                    ),
                ));
            }
        }
    }
    Ok(Answer {
        main_layer,
        main_law,
        laws,
        fixed,
        reason: answer["reason"]
            .as_str()
            .unwrap_or_default()
            .chars()
            .take(REASON_LIMIT)
            .collect(),
    })
}

// --- applying the laws -----------------------------------------------------------------------------

/// A note the tool keeps about how it applied the laws.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Note {
    pub code: &'static str,
    pub layer: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value: Option<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Row {
    from: [f64; 2],
    to: [f64; 2],
}

/// How a law arranged a layer, as the fit to spacing reads it.
#[derive(Clone, Debug, PartialEq)]
enum Arranged {
    /// A row from its first mark's center to its last.
    Row(Row),
    /// A grid's cell width and height, in canvas fractions.
    Grid([f64; 2]),
    /// Marks opened along a run, at these fractions of it.
    Opened(Row, Vec<f64>),
}

struct Compiler<'a> {
    context: &'a LawsContext,
    score: Score,
    laws: &'a BTreeMap<&'static str, Value>,
    main: usize,
    notes: Vec<Note>,
    /// The layers a law arranged, in the order the laws arranged them.
    arranged: Vec<(usize, Arranged)>,
    arranged_by: BTreeMap<usize, &'static str>,
    /// The line a placement law laid each layer along.
    rows: BTreeMap<usize, Row>,
    pinned: BTreeSet<usize>,
    /// The layers B8 opened into a pair.
    paired: BTreeSet<usize>,
    /// The layers progression or beat groups opened into marks.
    opened: BTreeSet<usize>,
    /// The layers whose count the description itself writes.
    fixed: &'a BTreeSet<usize>,
    /// The layers a card rebuilt.
    rebuilt: BTreeSet<usize>,
}

/// What the laws left: the Score, the notes, the pairs, the opened layers and
/// the rebuilt ones.
struct Applied {
    score: Score,
    notes: Vec<Note>,
    paired: BTreeSet<usize>,
    opened: BTreeSet<usize>,
    rebuilt: BTreeSet<usize>,
}

impl Compiler<'_> {
    fn units(&self) -> Units {
        self.context.units
    }

    fn instructions_of(&self, layer: usize) -> Vec<usize> {
        layers(&self.score).remove(&layer).unwrap_or_default()
    }

    fn only(&self, layer: usize, law: &str) -> Result<usize, Refusal> {
        let found = self.instructions_of(layer);
        match found.as_slice() {
            [position] => Ok(*position),
            _ => Err(refusal(
                "layer_split",
                format!(
                    "{law}: layer {layer} はすでに {} 個の指示に分かれていて、この法則を当てられない",
                    found.len()
                ),
                format!(
                    "{law}: layer {layer} is already {} instructions and this law cannot take it",
                    found.len()
                ),
            )),
        }
    }

    fn note(&mut self, code: &'static str, layer: Option<usize>, value: Option<f64>) {
        self.notes.push(Note { code, layer, value });
    }

    fn arrange(&mut self, layer: usize, arranged: Arranged, law: &'static str) {
        if let Some(entry) = self.arranged.iter_mut().find(|(found, _)| *found == layer) {
            entry.1 = arranged;
        } else {
            self.arranged.push((layer, arranged));
        }
        self.arranged_by.insert(layer, law);
    }

    /// The ends of a run along a guide line: the full width (the margin from the
    /// edges) or the current length, centered where the arrangement is now.
    fn span_on(
        &self,
        axis: Axis,
        value: f64,
        current: bool,
        instruction: &Instruction,
    ) -> ([f64; 2], [f64; 2]) {
        let units = self.units();
        let (start, end) = if current {
            let length = if is_row(instruction) || count_of(instruction) >= 2 {
                let (a, b) = current_span(instruction, units);
                units.distance(a, b)
            } else {
                line_length(instruction, units)
            };
            // The run lies along the guide: vertical on an x line, horizontal on a y line.
            let length = length
                / match axis {
                    Axis::X => units.y,
                    Axis::Y => units.x,
                };
            let length = py_min(length, 1.0 - 2.0 * MARGIN);
            let [cx, cy] = center_of(instruction);
            let middle = clamp_between(
                match axis {
                    Axis::X => cy,
                    Axis::Y => cx,
                },
                MARGIN + length / 2.0,
                1.0 - MARGIN - length / 2.0,
            );
            (middle - length / 2.0, middle + length / 2.0)
        } else {
            (MARGIN, 1.0 - MARGIN)
        };
        match axis {
            Axis::X => ([value, start], [value, end]),
            Axis::Y => ([start, value], [end, value]),
        }
    }

    fn place_on(
        &mut self,
        layer: usize,
        law: &'static str,
        guide: Guide,
        current: bool,
    ) -> Result<(), Refusal> {
        let position = self.only(layer, law)?;
        let units = self.units();
        let instruction = self.score.instructions[position].clone();
        let (shape, count) = (instruction.primitive, count_of(&instruction));
        match guide {
            Guide::Point(x, y) => {
                self.pinned.insert(layer);
                let target = &mut self.score.instructions[position];
                if is_line(shape) && count == 1 {
                    moved(target);
                    set_point_region(target, clamp(x), clamp(y));
                } else {
                    translate(target, [x, y], units);
                }
            }
            Guide::Line(axis, value) => {
                if count >= 2 {
                    let (p0, p1) = self.span_on(axis, value, current, &instruction);
                    let target = &mut self.score.instructions[position];
                    moved(target);
                    apply_row(target, p0, p1, units);
                    let row = Row { from: p0, to: p1 };
                    self.rows.insert(layer, row);
                    self.arrange(layer, Arranged::Row(row), law);
                } else if is_line(shape) {
                    let (p0, p1) = self.span_on(axis, value, current, &instruction);
                    let target = &mut self.score.instructions[position];
                    moved(target);
                    apply_line(target, p0, p1);
                    self.rows.insert(layer, Row { from: p0, to: p1 });
                } else {
                    let [cx, cy] = center_of(&instruction);
                    let point = match axis {
                        Axis::X => [value, cy],
                        Axis::Y => [cx, value],
                    };
                    translate(&mut self.score.instructions[position], point, units);
                }
            }
        }
        Ok(())
    }

    fn proportion(&mut self, law: &'static str) -> Result<(), Refusal> {
        let value = self.laws[law].clone();
        let d = match law {
            "B1" => GOLDEN,
            "B2" => SILVER,
            "B3" => 1.0 / 3.0,
            _ => match value["ratio"].as_str() {
                Some("3:4") => 3.0 / 7.0,
                _ => 0.4,
            },
        };
        for target in value["targets"].as_array().into_iter().flatten() {
            let guide = match target["at"].as_str().unwrap_or_default() {
                "point_ul" => Guide::Point(d, d),
                "point_ur" => Guide::Point(1.0 - d, d),
                "point_ll" => Guide::Point(d, 1.0 - d),
                "point_lr" => Guide::Point(1.0 - d, 1.0 - d),
                "line_left" => Guide::Line(Axis::X, d),
                "line_right" => Guide::Line(Axis::X, 1.0 - d),
                "line_top" => Guide::Line(Axis::Y, d),
                _ => Guide::Line(Axis::Y, 1.0 - d),
            };
            let current = target["span"].as_str() == Some("current");
            self.place_on(layer_number(&target["layer"]), law, guide, current)?;
        }
        Ok(())
    }

    fn armature(&mut self) -> Result<(), Refusal> {
        let units = self.units();
        let value = self.laws["B5"].clone();
        for target in value["targets"].as_array().into_iter().flatten() {
            let layer = layer_number(&target["layer"]);
            let position = self.only(layer, "B5")?;
            let (p0, p1) = match target["path"].as_str().unwrap_or_default() {
                "diagonal_down" => ([MARGIN, MARGIN], [1.0 - MARGIN, 1.0 - MARGIN]),
                "diagonal_up" => ([MARGIN, 1.0 - MARGIN], [1.0 - MARGIN, MARGIN]),
                "center_vertical" => ([0.5, MARGIN], [0.5, 1.0 - MARGIN]),
                _ => ([MARGIN, 0.5], [1.0 - MARGIN, 0.5]),
            };
            let target = &mut self.score.instructions[position];
            moved(target);
            let row = Row { from: p0, to: p1 };
            if count_of(target) >= 2 {
                apply_row(target, p0, p1, units);
                self.arrange(layer, Arranged::Row(row), "B5");
            } else if is_line(target.primitive) {
                apply_line(target, p0, p1);
            } else {
                return Err(refusal(
                    "armature_single_shape",
                    format!("B5: layer {layer} は1つの閉じた形で、骨組みの線に並べられない"),
                    format!("B5: layer {layer} is one closed shape and cannot lie on the armature"),
                ));
            }
            self.rows.insert(layer, row);
        }
        Ok(())
    }

    fn symmetry(&mut self) -> Result<(), Refusal> {
        let units = self.units();
        let d = 0.5 - GOLDEN;
        let value = self.laws["B8"].clone();
        for target in value["targets"].as_array().into_iter().flatten() {
            let layer = layer_number(&target["layer"]);
            let axis = target["axis"].as_str().unwrap_or_default();
            let position = self.only(layer, "B8")?;
            self.pinned.insert(layer);
            let instruction = self.score.instructions[position].clone();
            let count = count_of(&instruction);
            let [cx, cy] = center_of(&instruction);
            if count == 2 {
                let points = match axis {
                    "vertical" => {
                        let y = clamp_between(cy, 0.12, 0.88);
                        [[0.5 - d, y], [0.5 + d, y]]
                    }
                    "horizontal" => {
                        let x = clamp_between(cx, 0.12, 0.88);
                        [[x, 0.5 - d], [x, 0.5 + d]]
                    }
                    _ => [[0.5 - d, 0.5 - d], [0.5 + d, 0.5 + d]],
                };
                // The pair mirrors: the second mark turns the other way. A pair
                // that turns is printed as its two marks with their numeric
                // angles, and an unturned one as a row of two.
                let mut marks = points.map(|point| single(&instruction, point, 1.0));
                if let Some(turn) = marks[1].rotation.filter(|turn| *turn != 0.0) {
                    marks[1].rotation = Some(-turn);
                }
                self.score.instructions.splice(position..=position, marks);
                self.paired.insert(layer);
                continue;
            }
            let point = match axis {
                "vertical" => [0.5, cy],
                "horizontal" => [cx, 0.5],
                _ => [0.5, 0.5],
            };
            let target = &mut self.score.instructions[position];
            if is_line(target.primitive) && count == 1 {
                moved(target);
                set_point_region(target, point[0], point[1]);
            } else {
                translate(target, point, units);
            }
            if count >= 3 {
                // The line a later arrangement lays the layer along: its run now,
                // moved to the axis.
                let (a, b) = current_span(&self.score.instructions[position], units);
                let shift = [
                    point[0] - (a[0] + b[0]) / 2.0,
                    point[1] - (a[1] + b[1]) / 2.0,
                ];
                self.rows.insert(
                    layer,
                    Row {
                        from: [a[0] + shift[0], a[1] + shift[1]],
                        to: [b[0] + shift[0], b[1] + shift[1]],
                    },
                );
            }
        }
        Ok(())
    }

    fn layer_center(&self, layer: usize) -> [f64; 2] {
        let units = self.units();
        let found: Vec<&Instruction> = self
            .instructions_of(layer)
            .into_iter()
            .map(|position| &self.score.instructions[position])
            .collect();
        let centers: Option<Vec<[f64; 2]>> = found.iter().try_fold(Vec::new(), |mut all, item| {
            all.extend(mark_centers(item, units)?);
            Some(all)
        });
        let points = match centers {
            Some(centers) if !centers.is_empty() => centers,
            _ => found.iter().map(|item| center_of(item)).collect(),
        };
        let n = points.len() as f64;
        [
            points.iter().fold(0.0, |sum, point| sum + point[0]) / n,
            points.iter().fold(0.0, |sum, point| sum + point[1]) / n,
        ]
    }

    fn balance(&mut self) -> Result<(), Refusal> {
        let units = self.units();
        let layer = layer_number(&self.laws["B7"]["layer"]);
        let main = self.layer_center(self.main);
        let (dx, dy) = (main[0] - 0.5, main[1] - 0.5);
        if hypot(dx, dy) < 0.05 {
            return Err(refusal(
                "balance_main_centered",
                format!(
                    "主の層 {} が画面の中心にあり、天秤の反対側が決まらない。主を置き場の法則で中心から外すか B7 を外す",
                    self.main
                ),
                format!(
                    "the main layer {} is at the canvas's center, so the balance has no other side; move the main off the center with a placement law or drop B7",
                    self.main
                ),
            ));
        }
        let (x, y) = (0.5 - PHI_SQUARED * dx, 0.5 - PHI_SQUARED * dy);
        if !((EDGE..=1.0 - EDGE).contains(&x) && (EDGE..=1.0 - EDGE).contains(&y)) {
            self.note("balance_stopped_at_edge", Some(layer), None);
        }
        let position = self.only(layer, "B7")?;
        self.pinned.insert(layer);
        let target = &mut self.score.instructions[position];
        if is_line(target.primitive) && count_of(target) == 1 {
            moved(target);
            set_point_region(target, clamp(x), clamp(y));
        } else {
            translate(target, [x, y], units);
        }
        Ok(())
    }

    fn mark_size(&self, layer: usize) -> f64 {
        self.instructions_of(layer).first().map_or(0.0, |position| {
            2.0 * largest_extent(&self.score.instructions[*position], self.units())
        })
    }

    fn resize(&mut self, layer: usize, size: f64) {
        let current = self.mark_size(layer);
        if current <= 0.0 {
            return;
        }
        for position in self.instructions_of(layer) {
            scale_geometry(&mut self.score.instructions[position], size / current);
        }
    }

    fn sizes(&mut self) {
        let mut ratios: Vec<(usize, f64)> = Vec::new();
        if let Some(value) = self.laws.get("B6") {
            for layer in value["secondary"].as_array().into_iter().flatten() {
                ratios.push((layer_number(layer), INVERSE_PHI));
            }
            for layer in value["accent"].as_array().into_iter().flatten() {
                ratios.push((layer_number(layer), GOLDEN));
            }
        }
        if let Some(value) = self.laws.get("B7") {
            let layer = layer_number(&value["layer"]);
            if !ratios.iter().any(|(found, _)| *found == layer) {
                let sized = |layer: usize| {
                    self.context
                        .shape(layer)
                        .is_some_and(|shape| SIZED.contains(&shape))
                };
                if sized(layer) && sized(self.main) && self.context.movable().contains(&self.main) {
                    ratios.push((layer, GOLDEN));
                } else {
                    self.note("balance_size_kept", Some(layer), None);
                }
            }
        }
        if ratios.is_empty() {
            return;
        }
        let reference = self.mark_size(self.main);
        for (layer, ratio) in ratios {
            self.resize(layer, ratio * reference);
        }
    }

    /// The line an arrangement lays a layer along: the one a placement law laid
    /// it on, else its current long side.
    fn row_of(&self, layer: usize, position: usize) -> Row {
        self.rows.get(&layer).copied().unwrap_or_else(|| {
            let (from, to) = current_span(&self.score.instructions[position], self.units());
            Row { from, to }
        })
    }

    /// B9: the same shape at equal intervals, a row along the layer's line or a
    /// grid over its extent (widened to 0.382 of its long side and at least 0.3,
    /// inside the canvas less `EDGE`). The grid's columns and rows are the
    /// core's, which the printed tile is drawn with.
    fn repetition(&mut self) -> Result<(), Refusal> {
        let units = self.units();
        let value = self.laws["B9"].clone();
        for target in value["targets"].as_array().into_iter().flatten() {
            let layer = layer_number(&target["layer"]);
            let position = self.only(layer, "B9")?;
            moved(&mut self.score.instructions[position]);
            if target["form"].as_str() == Some("row") {
                let row = self.row_of(layer, position);
                apply_row(
                    &mut self.score.instructions[position],
                    row.from,
                    row.to,
                    units,
                );
                self.arrange(layer, Arranged::Row(row), "B9");
                continue;
            }
            let instruction = &self.score.instructions[position];
            let count = count_of(instruction);
            let [mut cx, mut cy] = center_of(instruction);
            if let Some(row) = self.rows.get(&layer) {
                cx = (row.from[0] + row.to[0]) / 2.0;
                cy = (row.from[1] + row.to[1]) / 2.0;
            }
            let (w, h) = extent_now(instruction, units);
            let side = py_max(py_max(w, h), 0.3);
            let (w, h) = (py_max(w, side * GOLDEN), py_max(h, side * GOLDEN));
            let (w, h) = (py_min(w, 1.0 - 2.0 * EDGE), py_min(h, 1.0 - 2.0 * EDGE));
            let x0 = clamp_between(cx - w / 2.0, EDGE, 1.0 - EDGE - w);
            let y0 = clamp_between(cy - h / 2.0, EDGE, 1.0 - EDGE - h);
            let (columns, rows) = build_tiled_grid(
                &mut self.score.instructions[position],
                [x0, y0, x0 + w, y0 + h],
                units,
            );
            if columns * rows != u64::from(count) {
                let last = u64::from(count) % columns;
                let last = if last == 0 { columns } else { last };
                self.note("grid_last_row", Some(layer), Some(last as f64));
            }
            self.arrange(
                layer,
                Arranged::Grid([w / columns as f64, h / rows as f64]),
                "B9",
            );
        }
        Ok(())
    }

    /// A run's ends ordered so that the second lies toward the given side.
    fn oriented(row: Row, toward: &str) -> Result<Row, Refusal> {
        let (dx, dy) = (row.to[0] - row.from[0], row.to[1] - row.from[1]);
        let component = if matches!(toward, "left" | "right") {
            dx
        } else {
            dy
        };
        if component.abs() < 1e-6 {
            return Err(refusal(
                "row_direction",
                format!(
                    "B10: 列の向きに {toward} が無い（横の列には left・right、縦の列には top・bottom）"
                ),
                format!(
                    "B10: the row does not run toward {toward} (a horizontal row takes left or right, a vertical row top or bottom)"
                ),
            ));
        }
        let positive = matches!(toward, "right" | "bottom");
        Ok(if (component > 0.0) == positive {
            row
        } else {
            Row {
                from: row.to,
                to: row.from,
            }
        })
    }

    /// R2: a run opened into marks is cut to its part inside the canvas less `EDGE`.
    fn inside(&mut self, layer: usize, row: Row) -> Row {
        let (from, to) = inside_frame(row.from, row.to);
        if (from, to) != (row.from, row.to) {
            self.note(
                "run_inside",
                Some(layer),
                Some(self.units().distance(from, to)),
            );
        }
        Row { from, to }
    }

    /// Open a layer into one mark per point, each `scale` times its size.
    fn unroll(&mut self, layer: usize, position: usize, points: &[[f64; 2]], scales: &[f64]) {
        let template = self.score.instructions[position].clone();
        let marks: Vec<Instruction> = points
            .iter()
            .zip(scales)
            .map(|(point, scale)| single(&template, *point, *scale))
            .collect();
        self.score.instructions.splice(position..=position, marks);
        self.opened.insert(layer);
    }

    /// B10: the marks opened along the row, their size or the gaps between them
    /// changing by one ratio between neighbours (the given ratio end to end).
    fn progression(&mut self) -> Result<(), Refusal> {
        let value = self.laws["B10"].clone();
        for target in value["targets"].as_array().into_iter().flatten() {
            let layer = layer_number(&target["layer"]);
            let position = self.only(layer, "B10")?;
            let count = count_of(&self.score.instructions[position]);
            let ratio: f64 = target["ratio"]
                .as_str()
                .and_then(|ratio| ratio.parse().ok())
                .unwrap_or(INVERSE_PHI);
            let row = Self::oriented(
                self.row_of(layer, position),
                target["toward"].as_str().unwrap_or_default(),
            )?;
            let row = self.inside(layer, row);
            let (ts, scales): (Vec<f64>, Vec<f64>) = if target["change"].as_str() == Some("size") {
                let ts: Vec<f64> = (0..count)
                    .map(|k| f64::from(k) / f64::from(count - 1))
                    .collect();
                let scales = ts.iter().map(|t| ratio.powf(*t)).collect();
                (ts, scales)
            } else {
                if count < 3 {
                    return Err(refusal(
                        "progression_count",
                        format!("B10: layer {layer} は {count} 個で、間隔の漸進には3個以上要る"),
                        format!(
                            "B10: layer {layer} has {count} things; a progression of spacing takes three or more"
                        ),
                    ));
                }
                let q = ratio.powf(1.0 / f64::from(count - 2));
                let mut ts = vec![0.0];
                for k in 0..count - 1 {
                    let last = ts[ts.len() - 1];
                    ts.push(last + q.powf(f64::from(k)));
                }
                let end = ts[ts.len() - 1];
                (
                    ts.iter().map(|t| t / end).collect(),
                    vec![1.0; count as usize],
                )
            };
            let points: Vec<[f64; 2]> = ts
                .iter()
                .map(|t| {
                    [
                        row.from[0] + (row.to[0] - row.from[0]) * t,
                        row.from[1] + (row.to[1] - row.from[1]) * t,
                    ]
                })
                .collect();
            self.unroll(layer, position, &points, &scales);
            self.arrange(layer, Arranged::Opened(row, ts), "B10");
        }
        Ok(())
    }

    /// B12: the marks in groups of two to four along the row, a rest of one more
    /// step between groups; with a strong beat, a group's later marks are 0.618
    /// of its first.
    fn beats(&mut self) -> Result<(), Refusal> {
        let value = self.laws["B12"].clone();
        for target in value["targets"].as_array().into_iter().flatten() {
            let layer = layer_number(&target["layer"]);
            let position = self.only(layer, "B12")?;
            let count = count_of(&self.score.instructions[position]);
            let group: u32 = target["group"]
                .as_str()
                .and_then(|group| group.parse().ok())
                .unwrap_or(2);
            if count <= group {
                return Err(refusal(
                    "beat_count",
                    format!("B12: layer {layer} は {count} 個で、{group} 個ずつの群が二つできない"),
                    format!(
                        "B12: layer {layer} has {count} things, too few for two groups of {group}"
                    ),
                ));
            }
            let row = self.row_of(layer, position);
            let row = self.inside(layer, row);
            let steps = (count - 1) + (count.div_ceil(group) - 1);
            let ts: Vec<f64> = (0..count)
                .map(|k| f64::from(k + k / group) / f64::from(steps))
                .collect();
            let strong = target["strong"].as_str() != Some("none");
            let scales: Vec<f64> = (0..count)
                .map(|k| {
                    if !strong || k % group == 0 {
                        1.0
                    } else {
                        INVERSE_PHI
                    }
                })
                .collect();
            let points: Vec<[f64; 2]> = ts
                .iter()
                .map(|t| {
                    [
                        row.from[0] + (row.to[0] - row.from[0]) * t,
                        row.from[1] + (row.to[1] - row.from[1]) * t,
                    ]
                })
                .collect();
            self.unroll(layer, position, &points, &scales);
            self.arrange(layer, Arranged::Opened(row, ts), "B12");
        }
        Ok(())
    }

    /// The spacing of an arrangement in short-edge units: a row's step, a
    /// grid's smaller cell side, an opened run's smallest gap.
    fn spacing(&self, arranged: &Arranged, count: u32) -> f64 {
        let units = self.units();
        match arranged {
            Arranged::Row(row) => {
                units.distance(row.from, row.to) / f64::from(count.saturating_sub(1).max(1))
            }
            Arranged::Grid([w, h]) => py_min(w * units.x, h * units.y),
            Arranged::Opened(row, ts) => units.distance(row.from, row.to) * min_gap(ts),
        }
    }

    /// Stretch an arrangement toward the inner frame until its spacing is
    /// `spacing`, as far as the frame allows: a row along its own line, a
    /// grid's region side by side (the stretched region tiled anew), opened
    /// marks along their run. A layer set on a point keeps its center.
    fn stretch(&mut self, layer: usize, arranged: &Arranged, found: &[usize], spacing: f64) -> f64 {
        let units = self.units();
        let pinned = self.pinned.contains(&layer);
        let count = count_of(&self.score.instructions[found[0]]);
        let now = match arranged {
            Arranged::Grid(_) => {
                let position = found[0];
                let Some(ResolvedPlacementRecipe::Grid { columns, rows, .. }) =
                    recipe(&self.score.instructions[position]).cloned()
                else {
                    return self.spacing(arranged, count);
                };
                let [x0, y0, x1, y1] = region_or_center(&self.score.instructions[position]);
                let (cx, cy) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
                let ([nx0, _], [nx1, _]) = stretch_span(
                    [x0, cy],
                    [x1, cy],
                    spacing * columns as f64 / units.x,
                    pinned,
                );
                let ([_, ny0], [_, ny1]) =
                    stretch_span([cx, y0], [cx, y1], spacing * rows as f64 / units.y, pinned);
                let region = [nx0, ny0, nx1, ny1];
                if region == [x0, y0, x1, y1] {
                    return self.spacing(arranged, count);
                }
                let (columns, rows) =
                    build_tiled_grid(&mut self.score.instructions[position], region, units);
                self.note("grid_stretched", Some(layer), None);
                Arranged::Grid([(nx1 - nx0) / columns as f64, (ny1 - ny0) / rows as f64])
            }
            Arranged::Row(row) => {
                let length = spacing * f64::from(count - 1) * along_per_unit(units, *row);
                let (q0, q1) = stretch_span(row.from, row.to, length, pinned);
                if (q0, q1) == (row.from, row.to) {
                    return self.spacing(arranged, count);
                }
                apply_row(&mut self.score.instructions[found[0]], q0, q1, units);
                self.note("row_stretched", Some(layer), Some(units.distance(q0, q1)));
                Arranged::Row(Row { from: q0, to: q1 })
            }
            Arranged::Opened(row, ts) => {
                let length = spacing / min_gap(ts) * along_per_unit(units, *row);
                let (q0, q1) = stretch_span(row.from, row.to, length, pinned);
                if (q0, q1) == (row.from, row.to) {
                    return self.spacing(arranged, count);
                }
                for (position, t) in found.iter().zip(ts) {
                    set_point_region(
                        &mut self.score.instructions[*position],
                        clamp(q0[0] + (q1[0] - q0[0]) * t),
                        clamp(q0[1] + (q1[1] - q0[1]) * t),
                    );
                }
                self.note("run_stretched", Some(layer), Some(units.distance(q0, q1)));
                Arranged::Opened(Row { from: q0, to: q1 }, ts.clone())
            }
        };
        self.arrange(layer, now.clone(), self.arranged_by[&layer]);
        self.spacing(&now, count)
    }

    /// A1 and R1: an arrangement a law set closer than allowed is first
    /// stretched toward the inner frame; what is still missing is shrunk. A
    /// placement law's row is allowed its origin's overlap and is never shrunk
    /// below the floor (A1). An arrangement law's layer is allowed no overlap
    /// (R1), and one that would need a shrink below the floor keeps its size:
    /// the author's dense layer. Lines keep their length.
    fn fit(&mut self) {
        let units = self.units();
        for (layer, arranged) in self.arranged.clone() {
            let found = self.instructions_of(layer);
            let Some(&first) = found.first() else {
                continue;
            };
            if is_line(self.score.instructions[first].primitive) {
                continue;
            }
            let width = found
                .iter()
                .map(|position| 2.0 * largest_extent(&self.score.instructions[*position], units))
                .fold(f64::NEG_INFINITY, py_max);
            let separate = self
                .arranged_by
                .get(&layer)
                .is_some_and(|law| ARRANGEMENT.contains(law));
            let (allowed, target) = if separate {
                (1.0, FIT_TARGET)
            } else {
                let origin = layers(&self.context.score)
                    .remove(&layer)
                    .and_then(|positions| positions.first().copied())
                    .map_or(0.0, |position| {
                        origin_ratio(&self.context.score.instructions[position], units)
                    });
                fit_ratio(origin)
            };
            let count = count_of(&self.score.instructions[first]);
            let spacing = self.spacing(&arranged, count);
            if width <= 0.0 || spacing <= 0.0 || width <= allowed * spacing {
                continue;
            }
            let spacing = self.stretch(layer, &arranged, &found, width / target);
            if width <= allowed * spacing {
                continue;
            }
            let mut factor = target * spacing / width;
            if factor < FIT_FLOOR {
                if separate {
                    self.note("dense_kept", Some(layer), Some(factor));
                    continue;
                }
                self.note("shrink_floor", Some(layer), Some(factor));
                factor = FIT_FLOOR;
            }
            for position in found {
                scale_geometry(&mut self.score.instructions[position], factor);
            }
            self.note("shrunk_to_spacing", Some(layer), Some(factor));
        }
    }

    /// The Score the laws leave holds at most `MAX_INSTRUCTIONS` instructions
    /// and `MAX_MARKS` marks.
    fn check_limits(&self) -> Result<(), Refusal> {
        let instructions = self.score.instructions.len();
        if instructions > MAX_INSTRUCTIONS {
            return Err(refusal(
                "too_many_instructions",
                format!(
                    "指示が {instructions} になり上限 {MAX_INSTRUCTIONS} を超える。数や回数を小さくするか法則を減らす"
                ),
                format!(
                    "the laws leave {instructions} instructions, over the limit of {MAX_INSTRUCTIONS}; take smaller counts or fewer laws"
                ),
            ));
        }
        let marks: u64 = self
            .score
            .instructions
            .iter()
            .map(|instruction| u64::from(count_of(instruction)))
            .sum();
        if marks > MAX_MARKS {
            return Err(refusal(
                "too_many_marks",
                format!("痕が {marks} になり上限 {MAX_MARKS} を超える。数を小さくする"),
                format!(
                    "the laws leave {marks} marks, over the limit of {MAX_MARKS}; take smaller counts"
                ),
            ));
        }
        Ok(())
    }

    fn aerial_size(&mut self) {
        if let Some(value) = self.laws.get("B15") {
            for layer in value["layers"].as_array().into_iter().flatten() {
                for position in self.instructions_of(layer_number(layer)) {
                    scale_geometry(&mut self.score.instructions[position], AERIAL);
                }
            }
        }
    }

    fn lightness(&self, color: Color) -> Option<f64> {
        self.context
            .lightness
            .as_ref()?
            .get(color.as_str())
            .copied()
    }

    fn aerial_color(&mut self) {
        let Some(value) = self.laws.get("B15") else {
            return;
        };
        let Some(ground) = self.lightness(self.score.background) else {
            self.note("aerial_color_without_palette", None, None);
            return;
        };
        for layer in value["layers"].as_array().into_iter().flatten() {
            let layer = layer_number(layer);
            let mut chosen: Option<(Color, f64)> = None;
            for color in AERIAL_COLORS {
                let Some(lightness) = self.lightness(color) else {
                    continue;
                };
                let difference = (lightness - ground).abs();
                if difference >= AERIAL_DIFFERENCE
                    && chosen.is_none_or(|(_, best)| difference < best)
                {
                    chosen = Some((color, difference));
                }
            }
            let Some((color, _)) = chosen else {
                self.note("aerial_color_kept", Some(layer), None);
                continue;
            };
            for position in self.instructions_of(layer) {
                let instruction = &mut self.score.instructions[position];
                instruction.color = color;
                if let Some(arrangement) = instruction.arrangement.as_mut() {
                    arrangement.color_cycle = Vec::new();
                }
            }
        }
    }

    fn hands(&mut self) {
        let Some(value) = self.laws.get("B21") else {
            return;
        };
        for target in value["targets"].as_array().into_iter().flatten() {
            let Some(hand) = target["hand"].as_str().and_then(Hand::parse) else {
                continue;
            };
            for position in self.instructions_of(layer_number(&target["layer"])) {
                set_hand(&mut self.score.instructions[position], hand);
            }
        }
    }

    fn layer_colors(score: &Score, positions: &[usize]) -> BTreeSet<&'static str> {
        let mut found = BTreeSet::new();
        for position in positions {
            let instruction = &score.instructions[*position];
            found.insert(instruction.color.as_str());
            for color in instruction
                .arrangement
                .iter()
                .flat_map(|arrangement| arrangement.color_cycle.iter())
            {
                found.insert(color.as_str());
            }
        }
        found
    }

    /// A layer whose colors changed must differ from the ground in lightness.
    fn check_colors(&self) -> Result<(), Refusal> {
        let Some(ground) = self.lightness(self.score.background) else {
            return Ok(());
        };
        let origin = layers(&self.context.score);
        let now = layers(&self.score);
        for summary in &self.context.summaries {
            if summary.arranged == Some("plugin") {
                continue;
            }
            let layer = summary.layer;
            let before: BTreeSet<&str> = origin
                .get(&layer)
                .into_iter()
                .flatten()
                .map(|position| self.context.score.instructions[*position].color.as_str())
                .collect();
            let after = Self::layer_colors(&self.score, now.get(&layer).map_or(&[], Vec::as_slice));
            if after == before && self.score.background == self.context.score.background {
                continue;
            }
            for name in after {
                let Some(color) = Color::ALL.iter().find(|color| color.as_str() == name) else {
                    continue;
                };
                if self
                    .lightness(*color)
                    .is_some_and(|lightness| (lightness - ground).abs() < VISIBLE)
                {
                    let ground_name = self.score.background.as_str();
                    return Err(refusal(
                        "invisible_color",
                        format!(
                            "layer {layer} の {name} は地 {ground_name} と明るさが {VISIBLE} 未満しか違わず見えない"
                        ),
                        format!(
                            "layer {layer} in {name} differs from the ground {ground_name} by less than {VISIBLE} in lightness and is not seen"
                        ),
                    ));
                }
            }
        }
        Ok(())
    }

    // --- the cards (stage B-4b): after the fit to spacing, in their order ---------------------

    /// A layer's marks in the Score the laws have left so far.
    fn marks_of(&self, layer: usize) -> u64 {
        self.instructions_of(layer)
            .into_iter()
            .map(|position| u64::from(count_of(&self.score.instructions[position])))
            .sum()
    }

    /// Take a layer's instructions out of the Score: where they began, and them.
    fn take_layer(
        &mut self,
        layer: usize,
        law: &str,
    ) -> Result<(usize, Vec<Instruction>), Refusal> {
        let positions = self.instructions_of(layer);
        let Some(&first) = positions.first() else {
            return Err(refusal(
                "no_such_layer",
                format!("{law}: layer {layer} は楽譜に無い"),
                format!("{law}: the Score has no layer {layer}"),
            ));
        };
        let mut taken: Vec<Instruction> = positions
            .iter()
            .rev()
            .map(|position| self.score.instructions.remove(*position))
            .collect();
        taken.reverse();
        Ok((first, taken))
    }

    fn rebuild(&mut self) -> Result<(), Refusal> {
        for law in REBUILD {
            let Some(value) = self.laws.get(law).cloned() else {
                continue;
            };
            match law {
                "C1" => self.dense(&value)?,
                "C2" => self.pattern(&value)?,
                "C3" => self.polyrhythm(&value)?,
                "C4" => self.motif(&value)?,
                "C5" => self.jo_ha_kyu(&value)?,
                _ => self.shin_gyo_so(&value)?,
            }
            self.rebuilt.extend(law_targets(law, &value));
        }
        Ok(())
    }

    /// C1: one or two layers scattered densely at one spot, their counts raised
    /// (a count the description writes stays; past the marks' limit, the raise
    /// shrinks by one ratio).
    #[allow(
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap,
        clippy::cast_precision_loss,
        clippy::cast_sign_loss
    )]
    fn dense(&mut self, value: &Value) -> Result<(), Refusal> {
        let spot = value["spot"]
            .as_str()
            .and_then(|name| SPOTS.iter().find(|(spot, _)| *spot == name))
            .map_or([0.5, 0.5], |(_, at)| *at);
        let extent: f64 = value["extent"]
            .as_str()
            .and_then(|extent| extent.parse().ok())
            .unwrap_or(0.25);
        let targets: Vec<(usize, u64)> = value["targets"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|target| {
                (
                    layer_number(&target["layer"]),
                    target["count"].as_u64().unwrap_or(1),
                )
            })
            .collect();
        let current: Vec<u64> = targets
            .iter()
            .map(|(layer, _)| self.marks_of(*layer))
            .collect();
        let others =
            total_marks(&self.score.instructions) as i64 - current.iter().sum::<u64>() as i64;
        let wanted: u64 = targets.iter().map(|(_, count)| count).sum();
        let factor = if wanted > 0 {
            py_min(1.0, (MAX_MARKS as i64 - others) as f64 / wanted as f64)
        } else {
            1.0
        };
        for (k, ((layer, asked), now)) in targets.iter().zip(&current).enumerate() {
            let fixed = self.fixed.contains(layer);
            let mut count = if fixed { *now } else { *asked };
            if factor < 1.0 && !fixed {
                count = (*now).max((count as f64 * factor) as u64);
                self.note("dense_count_limited", Some(*layer), Some(count as f64));
            }
            let (position, taken) = self.take_layer(*layer, "C1")?;
            let mut mark = taken[0].clone();
            moved(&mut mark);
            let k = k as f64;
            set_point_region(&mut mark, spot[0] + 0.02 * k, spot[1] + 0.02 * k);
            if let Some(arrangement) = mark.arrangement.as_mut() {
                arrangement.count = u32::try_from(count).unwrap_or(u32::MAX);
                if let Some(resolved) = arrangement.resolved.as_mut() {
                    // The extent is a side in short-edge units: the scatter's domain.
                    resolved.domain = inku_score::Point::new(extent, extent);
                    resolved.recipe =
                        ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation;
                }
            }
            self.score.instructions.insert(position, mark);
        }
        Ok(())
    }

    /// C2: a layer drawn again as a pattern of one unit shape over a band, the
    /// whole canvas or its own area grown by one and a half units.
    #[allow(
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap,
        clippy::float_cmp
    )]
    fn pattern(&mut self, value: &Value) -> Result<(), Refusal> {
        let units = self.units();
        let layer = layer_number(&value["layer"]);
        let (position, taken) = self.take_layer(layer, "C2")?;
        let template = taken[0].clone();
        let first_unit = match value["unit"].as_str() {
            Some("1/12") => 1.0 / 12.0,
            Some("1/5") => 1.0 / 5.0,
            _ => 1.0 / 8.0,
        };
        let region = match value["area"].as_str() {
            Some("current") => {
                let boxes: Vec<[f64; 4]> = taken.iter().map(|item| mark_box(item, units)).collect();
                let [x0, y0, x1, y1] = boxes.iter().skip(1).fold(boxes[0], |all, b| {
                    [
                        py_min(all[0], b[0]),
                        py_min(all[1], b[1]),
                        py_max(all[2], b[2]),
                        py_max(all[3], b[3]),
                    ]
                });
                let grow = first_unit * 1.5;
                [
                    clamp_between(x0 - grow / units.x, 0.0, 1.0),
                    clamp_between(y0 - grow / units.y, 0.0, 1.0),
                    clamp_between(x1 + grow / units.x, 0.0, 1.0),
                    clamp_between(y1 + grow / units.y, 0.0, 1.0),
                ]
            }
            Some("top_band") => [0.0, 0.0, 1.0, 0.382],
            Some("middle_band") => [0.0, 0.309, 1.0, 0.691],
            Some("bottom_band") => [0.0, 0.618, 1.0, 1.0],
            _ => [0.0, 0.0, 1.0, 1.0],
        };
        let colors: Vec<Color> = value["colors"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|color| {
                Color::ALL
                    .iter()
                    .copied()
                    .find(|known| Some(known.as_str()) == color.as_str())
            })
            .collect();
        let Some(&first) = colors.first() else {
            return Err(refusal(
                "missing",
                "C2: colors が無い".to_owned(),
                "C2: colors is missing".to_owned(),
            ));
        };
        let ground = self.score.background;
        if let Some(ground_lightness) = self.lightness(ground) {
            for color in &colors {
                if self
                    .lightness(*color)
                    .is_some_and(|lightness| (lightness - ground_lightness).abs() < VISIBLE)
                {
                    return Err(refusal(
                        "invisible_color",
                        format!(
                            "文様の色 {} は地 {} と明るさが 0.15 未満しか違わず見えない",
                            color.as_str(),
                            ground.as_str()
                        ),
                        format!(
                            "the pattern's color {} differs from the ground {} by less than 0.15 in lightness and is not seen",
                            color.as_str(),
                            ground.as_str()
                        ),
                    ));
                }
            }
        }
        let second = colors.get(1).copied().unwrap_or(ground);
        let pattern = value["pattern"].as_str().unwrap_or("seigaiha");
        let rings: u64 = if pattern == "seigaiha" { 3 } else { 1 };
        let budget = MAX_MARKS as i64 - total_marks(&self.score.instructions) as i64;
        let mut unit = first_unit;
        let (parts, side) = loop {
            let (parts, side) = pattern_plan(region, unit, pattern, units);
            let marks = rings * parts.iter().map(|part| part.marks()).sum::<u64>();
            // One instruction draws MAX_PER_INSTRUCTION marks at most.
            if (marks as i64 <= budget
                && parts.iter().all(|part| part.marks() <= MAX_PER_INSTRUCTION))
                || unit > 0.5
            {
                break (parts, side);
            }
            unit *= 1.15;
        };
        if unit != first_unit {
            self.note("pattern_unit_widened", Some(layer), Some(unit));
        }
        let cycle = (matches!(pattern, "ichimatsu" | "uroko") && second != first)
            .then_some([first, second]);
        let mut built = Vec::new();
        for part in parts {
            let shapes: Vec<Instruction> = match pattern {
                "seigaiha" => {
                    let half = (side * 1e6 / 2.0).round_ties_even();
                    [1.0, 0.66, 0.33]
                        .iter()
                        .map(|ring| {
                            let mut mark = shaped(&template, Primitive::Arc);
                            mark.center = Some(inku_score::Point::new(0.5, 0.5));
                            mark.position = Some(inku_score::Point::new(0.5, 0.5));
                            mark.radius = Some(micro((half * ring).round_ties_even() as i64));
                            mark.angle_start = Some(180.0);
                            mark.angle_end = Some(0.0);
                            mark.filled = false;
                            mark.color = first;
                            mark
                        })
                        .collect()
                }
                "shippo" => {
                    let mut mark = shaped(&template, Primitive::Circle);
                    mark.radius = Some(side / 2.0 * SQRT_2);
                    mark.filled = false;
                    mark.color = first;
                    vec![mark]
                }
                "ichimatsu" | "uroko" => {
                    let primitive = if pattern == "ichimatsu" {
                        Primitive::Square
                    } else {
                        Primitive::Triangle
                    };
                    let mut mark = shaped(&template, primitive);
                    mark.size = Some(inku_score::Point::new(side, side));
                    mark.filled = true;
                    mark.color = first;
                    vec![mark]
                }
                // Kikko: pointy-top hexagons whose width is the cell width.
                _ => {
                    let mut mark = shaped(&template, Primitive::Polygon);
                    mark.sides = Some(6);
                    mark.radius = Some(side / SQRT_3);
                    mark.filled = false;
                    mark.color = first;
                    vec![mark]
                }
            };
            for mut mark in shapes {
                moved(&mut mark);
                if let Some(arrangement) = mark.arrangement.as_mut() {
                    arrangement.color_cycle = Vec::new();
                    arrangement.count = u32::try_from(part.marks()).unwrap_or(u32::MAX);
                }
                match part {
                    Part::Grid(region, columns, rows) => {
                        build_grid(&mut mark, region, columns, rows, units);
                        if let Some(cycle) = cycle {
                            if let Some(arrangement) = mark.arrangement.as_mut() {
                                arrangement.color_cycle = cycle.to_vec();
                            }
                            mark.color = cycle[0];
                        }
                    }
                    Part::Point([x, y]) => {
                        if let Some(resolved) = resolved_mut(&mut mark) {
                            resolved.recipe = ResolvedPlacementRecipe::Place;
                            resolved.domain = inku_score::Point::new(1.0, 1.0);
                        }
                        set_point_region(&mut mark, x, y);
                    }
                }
                built.push(mark);
            }
        }
        self.score.instructions.splice(position..position, built);
        Ok(())
    }

    /// C3: two voices lined up across the same length with counts in a ratio,
    /// side by side about a band; one layer is split into the two voices. Each
    /// voice is drawn where its own layer is drawn.
    #[allow(clippy::cast_precision_loss)]
    fn polyrhythm(&mut self, value: &Value) -> Result<(), Refusal> {
        let units = self.units();
        let (p, q) = value["ratio"]
            .as_str()
            .and_then(|ratio| ratio.split_once(':'))
            .and_then(|(p, q)| Some((p.parse::<u64>().ok()?, q.parse::<u64>().ok()?)))
            .unwrap_or((2, 3));
        let base = value["base"].as_u64().unwrap_or(2);
        let counts = [base * p, base * q];
        let band: f64 = value["band"]
            .as_str()
            .and_then(|band| band.parse().ok())
            .unwrap_or(0.5);
        let gap = 0.05;
        let mut voices: Vec<usize> = Vec::new();
        for voice in value["voices"].as_array().into_iter().flatten() {
            let voice = layer_number(voice);
            if !voices.contains(&voice) {
                voices.push(voice);
            }
        }
        let others = total_marks(&self.score.instructions)
            - voices
                .iter()
                .map(|voice| self.marks_of(*voice))
                .sum::<u64>();
        if others + counts[0] + counts[1] > MAX_MARKS {
            return Err(refusal(
                "too_many_marks",
                "二つの声部の数が痕の上限 380 を超える。基の数を小さくする".to_owned(),
                "the two voices take the marks past the limit of 380; take a smaller base"
                    .to_owned(),
            ));
        }
        let mut templates = Vec::new();
        for voice in &voices {
            let position = self.only(*voice, "C3")?;
            templates.push(self.score.instructions[position].clone());
        }
        let plan: Vec<(usize, &Instruction)> = if voices.len() == 1 {
            vec![(voices[0], &templates[0]), (voices[0], &templates[0])]
        } else {
            voices.iter().copied().zip(templates.iter()).collect()
        };
        let mut built: BTreeMap<usize, Vec<Instruction>> = BTreeMap::new();
        for (k, ((layer, template), count)) in plan.into_iter().zip(counts).enumerate() {
            let mut mark = template.clone();
            moved(&mut mark);
            if let Some(arrangement) = mark.arrangement.as_mut() {
                arrangement.count = u32::try_from(count).unwrap_or(u32::MAX);
            }
            let offset = if k == 0 { -gap } else { gap };
            let (from, to) = match value["axis"].as_str() {
                Some("horizontal") => (
                    [0.1, band + offset / units.y],
                    [0.9, band + offset / units.y],
                ),
                Some("vertical") => (
                    [band + offset / units.x, 0.1],
                    [band + offset / units.x, 0.9],
                ),
                _ => {
                    let d = offset / SQRT_2;
                    (
                        [0.12 + d / units.x, 0.88 + d / units.y],
                        [0.88 + d / units.x, 0.12 + d / units.y],
                    )
                }
            };
            let spacing = units.distance(from, to) / (count - 1) as f64;
            let width = 2.0 * largest_extent(&mark, units);
            if width > 0.8 * spacing {
                scale_geometry(&mut mark, 0.8 * spacing / width);
            }
            apply_row(&mut mark, from, to, units);
            built.entry(layer).or_default().push(mark);
        }
        for voice in &voices {
            let position = self.only(*voice, "C3")?;
            let marks = built.remove(voice).unwrap_or_default();
            self.score.instructions.splice(position..=position, marks);
        }
        Ok(())
    }

    /// C4: one shape repeated along a row, a diagonal or the golden spiral,
    /// growing, shrinking, turning, mirrored or echoed in turn; repeats that
    /// crowd more than the origin drew them first lengthen the path, then
    /// shrink (A3).
    #[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
    fn motif(&mut self, value: &Value) -> Result<(), Refusal> {
        let units = self.units();
        let layer = layer_number(&value["layer"]);
        let repeats = value["repeats"].as_u64().unwrap_or(3);
        let count = self.marks_of(layer);
        let most = count.max(9);
        let fixed = self.fixed.contains(&layer);
        if fixed && repeats != count {
            return Err(refusal(
                "repeats_kept",
                format!("layer {layer} の数は記述が書いた数 {count} のままにする"),
                format!("layer {layer} keeps the count the description writes, {count}"),
            ));
        }
        if repeats > most {
            return Err(refusal(
                "repeats_most",
                format!("layer {layer} の回数は {most} まで（今の数と 9 の大きいほう）"),
                format!(
                    "layer {layer} repeats {most} times at most (the larger of its count and 9)"
                ),
            ));
        }
        if !fixed && repeats < count {
            return Err(refusal(
                "repeats_least",
                format!(
                    "layer {layer} は今 {count} 個。記述が数を書いていない層は減らさない（回数は {count}〜{most}）"
                ),
                format!(
                    "layer {layer} has {count} things now, and a layer whose count the description does not write keeps at least that many (repeats {count} to {most})"
                ),
            ));
        }
        let origin = layers(&self.context.score)
            .remove(&layer)
            .and_then(|positions| positions.first().copied())
            .map_or(0.0, |position| {
                origin_ratio(&self.context.score.instructions[position], units)
            });
        let (position, taken) = self.take_layer(layer, "C4")?;
        let mut template = taken[0].clone();
        let centers = layer_centers(&taken, units)
            .filter(|centers| !centers.is_empty())
            .unwrap_or_else(|| vec![[0.5, 0.5]]);
        let cy = clamp_between(
            centers.iter().fold(0.0, |sum, center| sum + center[1]) / centers.len() as f64,
            0.25,
            0.75,
        );
        let sequence: Vec<&str> = value["sequence"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .collect();
        let repeats = repeats as usize;
        let sizes = motif_sizes(&sequence, repeats);
        let path = value["path"].as_str().unwrap_or("row");
        let mut points = motif_points(path, repeats, cy, units, 1.0);
        let width = 2.0 * largest_extent(&template, units);
        let (allowed, target) = fit_ratio(origin);
        let mut crowding = motif_crowding(&points, &sizes, width, units);
        if width > 0.0 && crowding > allowed {
            let stretch = py_min(crowding / target, motif_stretch(path));
            if stretch > 1.0 {
                points = motif_points(path, repeats, cy, units, stretch);
                crowding = motif_crowding(&points, &sizes, width, units);
                self.note("motif_stretched", Some(layer), Some(stretch));
            }
            if crowding > allowed {
                let mut factor = target / crowding;
                if factor < FIT_FLOOR {
                    self.note("shrink_floor", Some(layer), Some(factor));
                    factor = FIT_FLOOR;
                }
                scale_geometry(&mut template, factor);
                self.note("shrunk_to_spacing", Some(layer), Some(factor));
            }
        }
        let mut rotation = template.rotation.unwrap_or(0.0);
        let mut built = Vec::new();
        for (point, (size, turn, echo)) in points.iter().zip(&sizes) {
            if *turn != 0.0 {
                rotation += turn;
            }
            built.push(card_single(&template, *point, *size, Some(rotation)));
            if *echo {
                let offset = 0.035 * size;
                built.push(card_single(
                    &template,
                    [point[0] + offset / units.x, point[1] + offset / units.y],
                    size / PHI,
                    Some(rotation),
                ));
            }
        }
        self.score.instructions.splice(position..position, built);
        Ok(())
    }

    /// C5: a layer of six or more in three stages along one direction, sparse,
    /// broken (turned, larger or recolored) and dense; every stage shrinks by
    /// the tightest one, and a stage of one is one mark at its middle.
    #[allow(
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap,
        clippy::cast_precision_loss,
        clippy::cast_sign_loss
    )]
    fn jo_ha_kyu(&mut self, value: &Value) -> Result<(), Refusal> {
        let units = self.units();
        let layer = layer_number(&value["layer"]);
        let count = self.marks_of(layer);
        let too_few = |count: u64| {
            refusal(
                "jo_ha_kyu_count",
                format!(
                    "layer {layer} は {count} 個で、三段の間隔が見えない。数の多い層を選ぶか C5 を外す"
                ),
                format!(
                    "layer {layer} has {count} things, too few to see three stages' spacing; choose a layer of more or drop C5"
                ),
            )
        };
        if count < 6 {
            return Err(too_few(count));
        }
        let (position, taken) = self.take_layer(layer, "C5")?;
        let mut template = taken[0].clone();
        let centers = layer_centers(&taken, units);
        let direction = value["direction"].as_str().unwrap_or("left_to_right");
        let horizontal = matches!(direction, "left_to_right" | "right_to_left");
        let reverse = matches!(direction, "right_to_left" | "bottom_to_top");
        let cross = match &centers {
            Some(centers) if !centers.is_empty() => {
                centers.iter().fold(0.0, |sum, center| {
                    sum + if horizontal { center[1] } else { center[0] }
                }) / centers.len() as f64
            }
            _ => 0.5,
        };
        let cross = clamp_between(cross, 0.2, 0.8);
        let lengths: Vec<f64> = value["lengths"]
            .as_str()
            .unwrap_or("1:1:1")
            .split(':')
            .map(|length| length.parse().unwrap_or(1.0))
            .collect();
        let dense: f64 = value["kyu_density"]
            .as_str()
            .and_then(|dense| dense.parse().ok())
            .unwrap_or(2.0);
        let densities = [1.0, (1.0 + dense) / 2.0, dense];
        let weights: Vec<f64> = lengths
            .iter()
            .zip(densities)
            .map(|(length, density)| length * density)
            .collect();
        let total = weights.iter().fold(0.0, |sum, weight| sum + weight);
        let mut counts: Vec<i64> = weights
            .iter()
            .map(|weight| ((count as f64 * weight / total).round_ties_even() as i64).max(1))
            .collect();
        counts[2] += count as i64 - counts.iter().sum::<i64>();
        if counts[2] < 1 {
            counts[1] += counts[2] - 1;
            counts[2] = 1;
        }
        if counts.iter().any(|stage| *stage < 1) {
            return Err(too_few(count));
        }
        let all = lengths.iter().fold(0.0, |sum, length| sum + length);
        let mut cuts = vec![0.08];
        for length in &lengths {
            let last = cuts[cuts.len() - 1];
            cuts.push(last + (0.92 - 0.08) * length / all);
        }
        let point = |s: f64| {
            let s = if reverse { 1.0 - s } else { s };
            if horizontal { [s, cross] } else { [cross, s] }
        };
        let change = value["break_change"].as_str().unwrap_or("size");
        let width = 2.0 * largest_extent(&template, units);
        if width > 0.0 {
            let along = if horizontal { units.x } else { units.y };
            let least = (0..3)
                .map(|k| {
                    0.8 * (cuts[k + 1] - cuts[k]) * along
                        / counts[k] as f64
                        / (width
                            * if k == 1 && change == "size" {
                                1.45
                            } else {
                                1.0
                            })
                })
                .fold(f64::INFINITY, py_min);
            if least < 1.0 {
                scale_geometry(&mut template, least);
            }
        }
        let break_color = value["break_color"]
            .as_str()
            .and_then(|name| {
                Color::ALL
                    .iter()
                    .copied()
                    .find(|color| color.as_str() == name)
            })
            .unwrap_or(template.color);
        let mut built = Vec::new();
        for k in 0..3 {
            let (start, end, n) = (cuts[k], cuts[k + 1], counts[k]);
            let step = (end - start) / n as f64;
            let (first, last) = (start + step / 2.0, end - step / 2.0);
            let mut mark = template.clone();
            moved(&mut mark);
            if k == 1 {
                match change {
                    "rotate" => mark.rotation = Some(mark.rotation.unwrap_or(0.0) + 25.0),
                    "size" => scale_geometry(&mut mark, 1.45),
                    _ => {
                        mark.color = break_color;
                        if let Some(arrangement) = mark.arrangement.as_mut() {
                            arrangement.color_cycle = Vec::new();
                        }
                    }
                }
            }
            if n == 1 {
                built.push(card_single(&mark, point((start + end) / 2.0), 1.0, None));
                continue;
            }
            if let Some(arrangement) = mark.arrangement.as_mut() {
                arrangement.count = n as u32;
            }
            apply_directed_row(&mut mark, point(first), point(last), units);
            built.push(mark);
        }
        self.score.instructions.splice(position..position, built);
        Ok(())
    }

    /// C6: a row or a grid of three or more opened one mark each and drawn in
    /// three degrees, strict (shin), half loosened (gyo) and free (so), by
    /// three bands along its long side or along its order.
    #[allow(clippy::cast_precision_loss)]
    fn shin_gyo_so(&mut self, value: &Value) -> Result<(), Refusal> {
        let units = self.units();
        let layer = layer_number(&value["layer"]);
        let marks = self.marks_of(layer);
        let (position, taken) = self.take_layer(layer, "C6")?;
        let centers = layer_centers(&taken, units).filter(|centers| !centers.is_empty());
        let count = centers
            .as_ref()
            .map_or(marks, |centers| centers.len() as u64);
        if count < 3 {
            return Err(refusal(
                "shin_gyo_so_count",
                format!("layer {layer} は {count} 個で、三つの度合いに分けられない"),
                format!("layer {layer} has {count} things, too few for three degrees"),
            ));
        }
        let Some(centers) = centers.filter(|_| count <= 54) else {
            return Err(refusal(
                "c6_unopenable",
                format!(
                    "layer {layer} は並べ方（散らす・{count} 個）のため一つずつに分けられない。別の層を選ぶか C6 を外す"
                ),
                format!(
                    "layer {layer} cannot be opened one by one for how it is arranged (scattered, or {count} things); choose another layer or drop C6"
                ),
            ));
        };
        let order: Vec<usize> = if value["split"].as_str() == Some("three_bands") {
            let spread = |axis: usize| {
                let values = centers.iter().map(|center| center[axis]);
                values.clone().fold(f64::NEG_INFINITY, py_max) - values.fold(f64::INFINITY, py_min)
            };
            let axis = usize::from(spread(0) * units.x < spread(1) * units.y);
            let mut order: Vec<usize> = (0..centers.len()).collect();
            order.sort_by(|a, b| {
                centers[*a][axis]
                    .partial_cmp(&centers[*b][axis])
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            order
        } else {
            (0..centers.len()).collect()
        };
        let levels = if value["order"].as_str() == Some("shin_gyo_so") {
            ["shin", "gyo", "so"]
        } else {
            ["so", "gyo", "shin"]
        };
        let degree = value["so_degree"].as_str().unwrap_or("medium");
        let template = &taken[0];
        let base = template.rotation.unwrap_or(0.0);
        let total = centers.len();
        let mut built = Vec::new();
        for (rank, k) in order.into_iter().enumerate() {
            let level = levels[(rank * 3 / total).min(2)];
            let (variation, turn) = c6_hand(level, degree);
            let sign = if (rank * 7919) % 3 == 0 { -1.0 } else { 1.0 };
            let unfixed = if level == "shin" { 0.0 } else { 1.0 };
            let rotation = base + sign * turn * ((rank % 3) as f64 / 2.0 + 0.5) * unfixed;
            let mut mark = card_single(template, centers[k], 1.0, Some(rotation));
            mark.variation = variation;
            if let Some(arrangement) = mark.arrangement.as_mut() {
                arrangement.jitter = 0.0;
            }
            built.push(mark);
        }
        self.score.instructions.splice(position..position, built);
        Ok(())
    }

    fn run(mut self) -> Result<Applied, Refusal> {
        for law in ["B1", "B2", "B3", "B4"] {
            if self.laws.contains_key(law) {
                self.proportion(law)?;
            }
        }
        if self.laws.contains_key("B5") {
            self.armature()?;
        }
        if self.laws.contains_key("B8") {
            self.symmetry()?;
        }
        if self.laws.contains_key("B7") {
            self.balance()?;
        }
        self.sizes();
        if self.laws.contains_key("B9") {
            self.repetition()?;
        }
        if self.laws.contains_key("B10") {
            self.progression()?;
        }
        if self.laws.contains_key("B12") {
            self.beats()?;
        }
        self.fit();
        self.rebuild()?;
        self.aerial_size();
        self.aerial_color();
        self.hands();
        self.check_colors()?;
        self.check_limits()?;
        Ok(Applied {
            score: self.score,
            notes: self.notes,
            paired: self.paired,
            opened: self.opened,
            rebuilt: self.rebuilt,
        })
    }
}

#[derive(Clone, Copy, Debug)]
enum Axis {
    /// A vertical guide line at an x.
    X,
    /// A horizontal guide line at a y.
    Y,
}

#[derive(Clone, Copy, Debug)]
enum Guide {
    Point(f64, f64),
    Line(Axis, f64),
}

// --- printing what the laws changed ------------------------------------------------------------------

/// The laws a reader chose and the composed plan printed with what they changed.
#[derive(Clone, Debug, PartialEq)]
pub struct Chosen {
    pub laws: Vec<&'static str>,
    pub main_law: String,
    pub main_layer: usize,
    pub notes: Vec<Note>,
    pub print: LawsPrint,
    /// The laws that name each layer of the Score.
    pub named: BTreeMap<usize, Vec<&'static str>>,
    /// The values the answer gave each of its laws, as it wrote them.
    pub values: BTreeMap<&'static str, Value>,
    /// The reader's reason.
    pub reason: String,
}

/// The record a work keeps of the layers its laws placed (2026-10-20): each
/// printed layer of a composed layer a law places or arranges (B1 to B5, B7 to
/// B10, B12, C1 to C6) or that the laws wrote at a numeric point, ends or angle,
/// and of the main layer when a law places other layers by it (B6, B7), as the
/// sentences `source` prints it with (one line each, the line of its
/// instruction in `compilation`). A layer the laws changed only in size, hand
/// or colour keeps its range and moves with the others. `None` when the printed
/// layers and the instructions do not match one to one.
#[must_use]
pub fn layers_record(
    chosen: &Chosen,
    source: &str,
    compilation: &inku_ddl::TypedDdlCompilation,
) -> Option<crate::laws_record::LawsLayerRecord> {
    use crate::laws_record::{LawsLayer, LawsLayerKind, LawsLayerRecord};
    let instructions = &compilation.semantic_document.as_ref()?.ast.instructions;
    let print = &chosen.print;
    if instructions.len() != print.composed.len() {
        return None;
    }
    let line_of = |at: usize| -> Option<&str> {
        let start = source.get(..at)?.rfind('\n').map_or(0, |i| i + 1);
        let end = source
            .get(at..)?
            .find('\n')
            .map_or(source.len(), |i| at + i);
        Some(source[start..end].trim()).filter(|line| !line.is_empty())
    };
    let partner = chosen
        .laws
        .iter()
        .any(|law| matches!(*law, "B6" | "B7"))
        .then_some(chosen.main_layer);
    let mut layers: Vec<(usize, LawsLayer)> = Vec::new();
    for (instruction, composed) in instructions.iter().zip(&print.composed) {
        let placing = chosen.named.get(composed).is_some_and(|laws| {
            laws.iter().any(|law| {
                PLACEMENT.contains(law) || ARRANGEMENT.contains(law) || REBUILD.contains(law)
            })
        });
        let entity = &instruction.entity;
        let numeric = entity.numeric_position.is_some()
            || entity.numeric_segment.is_some()
            || entity.numeric_angle.is_some();
        let kind = if print.changed.contains(composed) && (placing || numeric) {
            LawsLayerKind::Laws
        } else if partner == Some(*composed) {
            LawsLayerKind::Partner
        } else {
            continue;
        };
        let sentence = line_of(instruction.entity.head.source().span.start_byte)?.to_owned();
        match layers.last_mut() {
            Some((last, layer)) if *last == *composed => {
                if !layer.sentences.contains(&sentence) {
                    layer.sentences.push(sentence);
                }
            }
            _ => layers.push((
                *composed,
                LawsLayer {
                    sentences: vec![sentence],
                    kind,
                    laws: chosen
                        .named
                        .get(composed)
                        .map(|laws| laws.iter().map(|law| (*law).to_owned()).collect())
                        .unwrap_or_default(),
                },
            )),
        }
    }
    Some(LawsLayerRecord {
        layers: layers.into_iter().map(|(_, layer)| layer).collect(),
    })
}

/// The composed plan as the laws print it: the layers they changed are edited
/// and carry what they write in numbers, a layer for each composed layer and
/// one for each mark of a layer opened into marks.
#[derive(Clone, Debug, PartialEq)]
pub struct LawsPrint {
    pub plan: WorkPlan,
    pub ranges: Vec<Option<ComposedRange>>,
    pub joints: Vec<Option<String>>,
    pub numeric: Vec<Option<NumericWriting>>,
    /// The plan layers the laws changed (their place in the composed plan).
    pub changed: Vec<usize>,
    /// The composed plan layer each printed layer comes from.
    pub composed: Vec<usize>,
}

impl LawsPrint {
    #[must_use]
    pub fn source(
        &self,
        language: ResolvedInstructionLanguage,
        plugins: &[WorkPlanPlugin],
    ) -> String {
        let joints: Vec<Option<&str>> = self.joints.iter().map(Option::as_deref).collect();
        print_work_plan_with_numbers(
            &self.plan,
            language,
            plugins,
            &self.ranges,
            &joints,
            &self.numeric,
        )
    }
}

/// Where an instruction is placed, as the prototype compared it: its anchor,
/// recipe and domain, its count, its turn and its region.
type Placement<'a> = (
    Option<&'a ResolvedPlacementAnchor>,
    Option<&'a ResolvedPlacementRecipe>,
    Option<inku_score::Point>,
    u32,
    Option<f64>,
    Option<[f64; 4]>,
);

fn place_of(instruction: &Instruction) -> Placement<'_> {
    let resolved = resolved(instruction);
    (
        resolved.map(|resolved| &resolved.anchor),
        resolved.map(|resolved| &resolved.recipe),
        resolved.map(|resolved| resolved.domain),
        instruction
            .arrangement
            .as_ref()
            .map_or(0, |arrangement| arrangement.count),
        instruction.rotation,
        instruction.at.as_ref().map(|at| at.region),
    )
}

/// A row's first and last mark centers, from its anchor and its step.
pub(crate) fn row_ends(instruction: &Instruction, units: Units) -> Option<NumericPlace> {
    let [cx, cy] = center_of(instruction);
    let n = f64::from(count_of(instruction));
    let (sx, sy) = match recipe(instruction)? {
        ResolvedPlacementRecipe::HorizontalLine { cell_width } => (*cell_width / units.x, 0.0),
        ResolvedPlacementRecipe::VerticalLine { cell_height } => (0.0, *cell_height / units.y),
        ResolvedPlacementRecipe::DiagonalLine { step } => (step.x / units.x, step.y / units.y),
        _ => return None,
    };
    let half = (n - 1.0) / 2.0;
    Some(NumericPlace::Segment {
        from: [cx - half * sx, cy - half * sy],
        to: [cx + half * sx, cy + half * sy],
    })
}

/// A line's two ends where it is drawn: its ends about their middle, turned by
/// its rotation (clockwise, y down) in short-edge units, at its anchor, and
/// cut where the canvas cuts it.
pub(crate) fn line_ends(instruction: &Instruction, units: Units) -> Option<NumericPlace> {
    let (from, to) = (instruction.from_?, instruction.to?);
    let (mx, my) = ((from.x + to.x) / 2.0, (from.y + to.y) / 2.0);
    let [cx, cy] = center_of(instruction);
    let turn = instruction.rotation.unwrap_or(0.0).to_radians();
    let (c, s) = (turn.cos(), turn.sin());
    // The prototype's order of operations: `cx + dx * c - dy * s`.
    let end = |x: f64, y: f64| {
        let (dx, dy) = ((x - mx) * units.x, (y - my) * units.y);
        [
            cx + dx * c / units.x - dy * s / units.x,
            cy + dx * s / units.y + dy * c / units.y,
        ]
    };
    let (from, to) = on_canvas(end(from.x, from.y), end(to.x, to.y))?;
    Some(NumericPlace::Segment { from, to })
}

/// The part of a segment (canvas fractions) the canvas shows. The prototype
/// drew a line past the canvas and the canvas cut it, where numeric ends lie
/// on the canvas (a full-width line moved off the middle). Ends already on it
/// are kept as they are; `None` when none of the line is on it.
#[allow(clippy::float_cmp)]
fn on_canvas(from: [f64; 2], to: [f64; 2]) -> Option<([f64; 2], [f64; 2])> {
    let inside = |[x, y]: [f64; 2]| (0.0..=1.0).contains(&x) && (0.0..=1.0).contains(&y);
    if inside(from) && inside(to) {
        return Some((from, to));
    }
    let (dx, dy) = (to[0] - from[0], to[1] - from[1]);
    let (mut start, mut end) = (0.0_f64, 1.0_f64);
    // Liang and Barsky: each side of the canvas bounds the segment's parameter.
    for (p, q) in [
        (-dx, from[0]),
        (dx, 1.0 - from[0]),
        (-dy, from[1]),
        (dy, 1.0 - from[1]),
    ] {
        if p == 0.0 {
            if q < 0.0 {
                return None;
            }
        } else if p < 0.0 {
            start = start.max(q / p);
        } else {
            end = end.min(q / p);
        }
    }
    if start >= end {
        return None;
    }
    let at = |t: f64| {
        [
            (from[0] + t * dx).clamp(0.0, 1.0),
            (from[1] + t * dy).clamp(0.0, 1.0),
        ]
    };
    Some((
        if start > 0.0 { at(start) } else { from },
        if end < 1.0 { at(end) } else { to },
    ))
}

/// The range a grid or a scatter covers after a law moved it.
pub(crate) fn moved_range(instruction: &Instruction, units: Units) -> Option<NumericPlace> {
    let [x0, y0, x1, y1] = anchor_region(instruction)?;
    if is_scatter(instruction) {
        let [w, h] = domain_of(instruction)?;
        let (cx, cy) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
        let (w, h) = (w / units.x, h / units.y);
        return Some(NumericPlace::Range {
            bounds: [cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0],
        });
    }
    Some(NumericPlace::Range {
        bounds: [x0, y0, x1, y1],
    })
}

/// The size an instruction is drawn at, in the form its shape reads.
pub(crate) fn numeric_size(instruction: &Instruction, units: Units) -> Option<NumericSize> {
    Some(match instruction.primitive {
        Primitive::Circle | Primitive::Point | Primitive::Polygon => NumericSize::Radius {
            radius: instruction.radius?,
        },
        Primitive::Ellipse | Primitive::Cloudform | Primitive::Triangle => {
            let size = instruction.size?;
            NumericSize::WidthHeight {
                width: size.x,
                height: size.y,
            }
        }
        Primitive::Square => {
            let size = instruction.size?;
            #[allow(clippy::float_cmp)]
            if size.x == size.y {
                NumericSize::Side { side: size.x }
            } else {
                NumericSize::WidthHeight {
                    width: size.x,
                    height: size.y,
                }
            }
        }
        Primitive::Arc => {
            let radius = instruction.radius?;
            let half = ((instruction.angle_start? - instruction.angle_end?) / 2.0).to_radians();
            NumericSize::ChordSagitta {
                chord: 2.0 * radius * half.sin(),
                sagitta: radius * (1.0 - half.cos()),
            }
        }
        Primitive::Line | Primitive::FreeLine => {
            let (from, to) = (instruction.from_?, instruction.to?);
            NumericSize::Length {
                length: units.distance([from.x, from.y], [to.x, to.y]),
            }
        }
    })
}

/// What the laws changed in one layer, printed as the prototype printed it.
struct Edit {
    layer: inku_ddl::work_plan::WorkPlanLayer,
    numeric: NumericWriting,
    keep_joint: bool,
}

fn edit_layer(
    layer: &inku_ddl::work_plan::WorkPlanLayer,
    before: &Instruction,
    marks: &[&Instruction],
    hand: Option<Hand>,
    units: Units,
) -> Option<Edit> {
    let mut layer = layer.clone();
    let mut numeric = NumericWriting::default();
    let after = *marks.first()?;
    // A pair B8 opened is its two marks; it is written as one sentence, so the
    // layers after it keep their source instructions (and the seeds they draw with).
    let paired = marks.len() == 2;
    let moved = paired || place_of(before) != place_of(after);
    let count = count_of(after);
    // One line is written by its ends: a mark placed at a numeric point must lie
    // wholly on the canvas, a line by its ends may have been cut by it.
    let single_line = is_line(after.primitive) && count == 1 && !paired;
    if moved {
        numeric.place = Some(if paired {
            // The pair's marks are the two ends of a row of two.
            layer.action = "line_up".to_owned();
            layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
            NumericPlace::Segment {
                from: center_of(after),
                to: center_of(marks[1]),
            }
        } else if is_row_recipe(after) && count >= 2 {
            layer.action = "line_up".to_owned();
            layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
            row_ends(after, units)?
        } else if single_line {
            layer.attributes.remove(&WorkPlanSlot::Angle);
            layer.attributes.remove(&WorkPlanSlot::Size);
            layer.proportion = None;
            line_ends(after, units)?
        } else {
            match recipe(after)? {
                ResolvedPlacementRecipe::Place => {
                    let [x, y] = center_of(after);
                    NumericPlace::Point { at: [x, y] }
                }
                ResolvedPlacementRecipe::Grid { .. } => {
                    // A grid is a tile over its range (B9 lays one over any layer).
                    layer.action = "tile".to_owned();
                    layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
                    moved_range(after, units)?
                }
                ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation => {
                    moved_range(after, units)?
                }
                _ => return None,
            }
        });
    }
    if let Some(size) = resized(before, after, units, moved && single_line) {
        numeric.size = Some(size?);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
    }
    retouch(&mut layer, before, after, hand);
    // A pair is placed in numbers; a relation would move its marks again.
    let dropped = before.relation.is_some() && after.relation.is_none();
    let keep_joint = !(paired || dropped);
    Some(Edit {
        layer,
        numeric,
        keep_joint,
    })
}

/// The numeric size of a mark the laws resized (`Some(None)` when its shape
/// has none to write); `None` when it keeps its size or its ends write its
/// length (`by_ends`).
fn resized(
    before: &Instruction,
    after: &Instruction,
    units: Units,
    by_ends: bool,
) -> Option<Option<NumericSize>> {
    let size = |instruction: &Instruction| 2.0 * largest_extent(instruction, units);
    let factor = if size(before) != 0.0 {
        size(after) / size(before)
    } else {
        1.0
    };
    ((factor - 1.0).abs() > 1e-9 && !by_ends).then(|| numeric_size(after, units))
}

/// The hand B21 gives a layer and the color the laws changed.
fn retouch(
    layer: &mut inku_ddl::work_plan::WorkPlanLayer,
    before: &Instruction,
    after: &Instruction,
    hand: Option<Hand>,
) {
    match hand {
        Some(Hand::Still) => {
            for slot in [
                WorkPlanSlot::MotionAmplitude,
                WorkPlanSlot::MotionSpacing,
                WorkPlanSlot::MotionQuality,
            ] {
                layer.attributes.remove(&slot);
            }
        }
        Some(Hand::Fine) if layer.attributes.contains_key(&WorkPlanSlot::MotionQuality) => {
            layer
                .attributes
                .insert(WorkPlanSlot::MotionAmplitude, "narrowly".to_owned());
            layer
                .attributes
                .insert(WorkPlanSlot::MotionSpacing, "loosely".to_owned());
        }
        _ => {}
    }
    if after.color != before.color {
        layer
            .attributes
            .insert(WorkPlanSlot::Color, after.color.as_str().to_owned());
    }
}

/// One mark of a layer progression or beat groups opened, as its own sentence:
/// one of it, placed (or drawn, when the layer draws), without a line-up
/// direction or a joint; a closed shape at a numeric point and a line by the
/// ends the canvas shows; a numeric size when the laws resized it.
fn edit_opened(
    layer: &inku_ddl::work_plan::WorkPlanLayer,
    before: &Instruction,
    mark: &Instruction,
    hand: Option<Hand>,
    units: Units,
) -> Option<Edit> {
    let mut layer = layer.clone();
    layer.count = 1;
    if !matches!(layer.action.as_str(), "place" | "draw") {
        layer.action = "place".to_owned();
    }
    layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
    let line = is_line(mark.primitive);
    let place = if line {
        layer.attributes.remove(&WorkPlanSlot::Angle);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
        line_ends(mark, units)?
    } else {
        NumericPlace::Point {
            at: center_of(mark),
        }
    };
    let mut numeric = NumericWriting {
        place: Some(place),
        ..NumericWriting::default()
    };
    if let Some(size) = resized(before, mark, units, line) {
        numeric.size = Some(size?);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
    }
    retouch(&mut layer, before, mark, hand);
    Some(Edit {
        layer,
        numeric,
        keep_joint: false,
    })
}

/// The numeric angle a turn is written with (0 up to 360), or `None` when the
/// mark does not turn as printed.
fn turn_of(rotation: Option<f64>) -> Option<f64> {
    let turn = rotation.unwrap_or(0.0).rem_euclid(360.0);
    let text = inku_ddl::work_plan::number(turn);
    (text != "0" && text != "360").then_some(turn)
}

/// The motion words the Score's variation draws (stage B-4's §3.2): an
/// amplitude other than medium, a spacing other than medium and the sway's
/// quality; no variation drops them. A quality the plan has no word for keeps
/// the layer's words.
fn write_hand(
    layer: &mut inku_ddl::work_plan::WorkPlanLayer,
    variation: Option<&inku_score::Variation>,
) {
    let quality = match variation.map(|variation| variation.quality) {
        Some(inku_score::Quality::Perlin) => Some("swaying"),
        Some(inku_score::Quality::Wave) => Some("undulating"),
        Some(_) => return,
        None => None,
    };
    for slot in [
        WorkPlanSlot::MotionAmplitude,
        WorkPlanSlot::MotionSpacing,
        WorkPlanSlot::MotionQuality,
    ] {
        layer.attributes.remove(&slot);
    }
    let (Some(variation), Some(quality)) = (variation, quality) else {
        return;
    };
    match variation.amplitude {
        Amplitude::Fine => {
            layer
                .attributes
                .insert(WorkPlanSlot::MotionAmplitude, "narrowly".to_owned());
        }
        Amplitude::Broad => {
            layer
                .attributes
                .insert(WorkPlanSlot::MotionAmplitude, "broadly".to_owned());
        }
        Amplitude::Medium => {}
    }
    match variation.frequency {
        Frequency::Slow => {
            layer
                .attributes
                .insert(WorkPlanSlot::MotionSpacing, "loosely".to_owned());
        }
        Frequency::High => {
            layer
                .attributes
                .insert(WorkPlanSlot::MotionSpacing, "tightly".to_owned());
        }
        Frequency::Medium => {}
    }
    layer
        .attributes
        .insert(WorkPlanSlot::MotionQuality, quality.to_owned());
}

/// One instruction of a layer a card rebuilt, as its own sentence: one mark at
/// a numeric point (a line by the ends the canvas shows), a row by its numeric
/// ends, a grid as a numeric range it tiles, a scatter as a numeric range. The
/// sentence writes the instruction's count, its shape (C2's; a polygon as its
/// noun), a numeric size when its size or shape changed (and for an arc that
/// turns in numbers), its color when it changed (two alternating colors as a
/// cycle), C2's surface and the hand its variation draws; a turn the card
/// changed is written in numbers instead of an angle word.
fn edit_rebuilt(
    layer: &inku_ddl::work_plan::WorkPlanLayer,
    before: &Instruction,
    mark: &Instruction,
    turned: bool,
    pattern: bool,
    units: Units,
) -> Option<Edit> {
    let mut layer = layer.clone();
    layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
    let count = count_of(mark);
    layer.count = count;
    let line = is_line(mark.primitive) && count == 1;
    let place = match recipe(mark)? {
        ResolvedPlacementRecipe::Place => {
            if !matches!(layer.action.as_str(), "place" | "draw") {
                layer.action = "place".to_owned();
            }
            if line {
                line_ends(mark, units)?
            } else {
                NumericPlace::Point {
                    at: center_of(mark),
                }
            }
        }
        ResolvedPlacementRecipe::HorizontalLine { .. }
        | ResolvedPlacementRecipe::VerticalLine { .. }
        | ResolvedPlacementRecipe::DiagonalLine { .. }
            if count >= 2 =>
        {
            layer.action = "line_up".to_owned();
            row_ends(mark, units)?
        }
        ResolvedPlacementRecipe::Grid { .. } => {
            layer.action = "tile".to_owned();
            moved_range(mark, units)?
        }
        ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation => {
            layer.action = "scatter".to_owned();
            moved_range(mark, units)?
        }
        _ => return None,
    };
    let mut numeric = NumericWriting {
        place: Some(place),
        ..NumericWriting::default()
    };
    let reshaped = mark.primitive != before.primitive || mark.sides != before.sides;
    if reshaped && mark.primitive != Primitive::Polygon {
        mark.primitive.as_str().clone_into(&mut layer.shape);
    }
    if mark.primitive == Primitive::Polygon {
        numeric.sides = mark.sides;
    }
    if line {
        layer.attributes.remove(&WorkPlanSlot::Angle);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
    } else {
        let was = largest_extent(before, units);
        let factor = if was == 0.0 {
            1.0
        } else {
            (2.0 * largest_extent(mark, units)) / (2.0 * was)
        };
        let arc_turned = mark.primitive == Primitive::Arc && turned;
        if reshaped || (factor - 1.0).abs() > 1e-9 || arc_turned {
            numeric.size = Some(numeric_size(mark, units)?);
            layer.attributes.remove(&WorkPlanSlot::Size);
            layer.proportion = None;
        }
        if turned {
            layer.attributes.remove(&WorkPlanSlot::Angle);
            numeric.turn = turn_of(mark.rotation);
        }
    }
    let cycle = mark
        .arrangement
        .as_ref()
        .map_or(&[][..], |arrangement| arrangement.color_cycle.as_slice());
    match cycle {
        [] => {
            if mark.color != before.color {
                layer
                    .attributes
                    .insert(WorkPlanSlot::Color, mark.color.as_str().to_owned());
            }
        }
        [first, second] if first != second => numeric.cycle = Some(vec![*first, *second]),
        _ => return None,
    }
    if pattern {
        if !mark.filled {
            layer
                .attributes
                .insert(WorkPlanSlot::Surface, "empty".to_owned());
        } else if layer
            .attributes
            .get(&WorkPlanSlot::Surface)
            .is_none_or(|surface| surface == "empty")
        {
            layer
                .attributes
                .insert(WorkPlanSlot::Surface, "flat".to_owned());
        }
    }
    write_hand(&mut layer, mark.variation.as_ref());
    Some(Edit {
        layer,
        numeric,
        keep_joint: false,
    })
}

/// One mark of a pair B8 opened whose marks turn: one of it at a numeric point
/// (a line by its ends) with its own turn in numbers.
fn edit_pair_mark(
    layer: &inku_ddl::work_plan::WorkPlanLayer,
    before: &Instruction,
    mark: &Instruction,
    hand: Option<Hand>,
    units: Units,
) -> Option<Edit> {
    let mut layer = layer.clone();
    layer.count = 1;
    if !matches!(layer.action.as_str(), "place" | "draw") {
        layer.action = "place".to_owned();
    }
    layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
    let line = is_line(mark.primitive);
    let mut numeric = NumericWriting::default();
    if line {
        layer.attributes.remove(&WorkPlanSlot::Angle);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
        numeric.place = Some(line_ends(mark, units)?);
    } else {
        layer.attributes.remove(&WorkPlanSlot::Angle);
        numeric.place = Some(NumericPlace::Point {
            at: center_of(mark),
        });
        numeric.turn = turn_of(mark.rotation);
    }
    if let Some(size) = resized(before, mark, units, line) {
        numeric.size = Some(size?);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
    }
    retouch(&mut layer, before, mark, hand);
    Some(Edit {
        layer,
        numeric,
        keep_joint: false,
    })
}

/// The composed plan printed with what the laws changed, or `None` when a
/// changed layer is one the printer cannot write in numbers.
fn print_changes(
    composed: &ComposedPlan,
    context: &LawsContext,
    applied: &Applied,
    hands: &BTreeMap<usize, Hand>,
    pattern: Option<usize>,
) -> Option<LawsPrint> {
    let after = &applied.score;
    let before = layers(&context.score);
    let now = layers(after);
    let mut print = LawsPrint {
        plan: WorkPlan {
            layers: Vec::new(),
            ..composed.plan.clone()
        },
        ranges: Vec::new(),
        joints: Vec::new(),
        numeric: Vec::new(),
        changed: Vec::new(),
        composed: Vec::new(),
    };
    for (k, layer) in composed.plan.layers.iter().enumerate() {
        let index = context.first_plan_layer + k;
        let was: Vec<&Instruction> = before
            .get(&index)?
            .iter()
            .map(|position| &context.score.instructions[*position])
            .collect();
        let is: Vec<&Instruction> = now
            .get(&index)?
            .iter()
            .map(|position| &after.instructions[*position])
            .collect();
        if was == is {
            print.plan.layers.push(layer.clone());
            print.ranges.push(composed.ranges[k].clone());
            print.joints.push(composed.joints[k].clone());
            print.numeric.push(None);
            print.composed.push(k);
            continue;
        }
        print.changed.push(k);
        let [before] = was.as_slice() else {
            return None;
        };
        let hand = hands.get(&index).copied();
        let edits = if applied.rebuilt.contains(&index) {
            // A card that turns any of the layer's marks writes every turn in numbers.
            #[allow(clippy::float_cmp)]
            let turned = is
                .iter()
                .any(|mark| mark.rotation.unwrap_or(0.0) != before.rotation.unwrap_or(0.0));
            is.iter()
                .map(|mark| {
                    edit_rebuilt(
                        layer,
                        before,
                        mark,
                        turned,
                        pattern == Some(index),
                        context.units,
                    )
                })
                .collect::<Option<Vec<Edit>>>()?
        } else if applied.opened.contains(&index) {
            is.iter()
                .map(|mark| edit_opened(layer, before, mark, hand, context.units))
                .collect::<Option<Vec<Edit>>>()?
        } else if applied.paired.contains(&index)
            && is.iter().any(|mark| turn_of(mark.rotation).is_some())
        {
            if is.len() != 2 {
                return None;
            }
            is.iter()
                .map(|mark| edit_pair_mark(layer, before, mark, hand, context.units))
                .collect::<Option<Vec<Edit>>>()?
        } else {
            let marks = if applied.paired.contains(&index) {
                2
            } else {
                1
            };
            if is.len() != marks {
                return None;
            }
            vec![edit_layer(layer, before, &is, hand, context.units)?]
        };
        for edit in edits {
            print.ranges.push(if edit.numeric.place.is_some() {
                None
            } else {
                composed.ranges[k].clone()
            });
            print.joints.push(if edit.keep_joint {
                composed.joints[k].clone()
            } else {
                None
            });
            print.plan.layers.push(edit.layer);
            print.numeric.push(Some(edit.numeric));
            print.composed.push(k);
        }
    }
    Some(print)
}

/// Apply a conformed answer to the context (the computation and the print).
fn apply(
    answer: &Answer,
    context: &LawsContext,
    composed: &ComposedPlan,
) -> Result<Chosen, Refusal> {
    let compiler = Compiler {
        context,
        score: context.score.clone(),
        laws: &answer.laws,
        main: answer.main_layer,
        notes: Vec::new(),
        arranged: Vec::new(),
        arranged_by: BTreeMap::new(),
        rows: BTreeMap::new(),
        pinned: BTreeSet::new(),
        paired: BTreeSet::new(),
        opened: BTreeSet::new(),
        fixed: &answer.fixed,
        rebuilt: BTreeSet::new(),
    };
    let applied = compiler.run()?;
    let mut hands = BTreeMap::new();
    if let Some(value) = answer.laws.get("B21") {
        for target in value["targets"].as_array().into_iter().flatten() {
            if let Some(hand) = target["hand"].as_str().and_then(Hand::parse) {
                hands.insert(layer_number(&target["layer"]), hand);
            }
        }
    }
    let pattern = answer
        .laws
        .get("C2")
        .map(|value| layer_number(&value["layer"]));
    let print = print_changes(composed, context, &applied, &hands, pattern).ok_or_else(|| {
        refusal(
            "unprintable",
            "法則が変えた層を数の形で書けない".to_owned(),
            "a layer the laws changed cannot be written in numbers".to_owned(),
        )
    })?;
    let laws: Vec<&'static str> = LAWS
        .into_iter()
        .filter(|law| answer.laws.contains_key(law))
        .collect();
    let mut named: BTreeMap<usize, Vec<&'static str>> = BTreeMap::new();
    for &law in &laws {
        for layer in law_targets(law, &answer.laws[law]) {
            named.entry(layer).or_default().push(law);
        }
    }
    Ok(Chosen {
        laws,
        main_law: answer.main_law.clone(),
        main_layer: answer.main_layer,
        notes: applied.notes,
        print,
        named,
        values: answer.laws.clone(),
        reason: answer.reason.clone(),
    })
}

/// The reason to ask again when the printed document cannot hold a layer the
/// laws changed on the canvas: a mark the laws place at a point is drawn whole,
/// where the prototype let the canvas cut it. `instruction` is the source
/// instruction of the printed document, where a layer opened into marks takes
/// one per mark; the reason names the layer as the request numbered it. `None`
/// when it is not a changed layer.
#[must_use]
pub fn off_canvas(chosen: &Chosen, context: &LawsContext, instruction: usize) -> Option<Refusal> {
    let printed = instruction.checked_sub(context.first_plan_layer)?;
    let k = *chosen.print.composed.get(printed)?;
    if !chosen.print.changed.contains(&k) {
        return None;
    }
    let layer = context.first_plan_layer + k;
    // A hand neither places nor sizes a mark.
    let laws: Vec<&str> = chosen
        .named
        .get(&layer)?
        .iter()
        .copied()
        .filter(|law| *law != "B21")
        .collect();
    if laws.is_empty() {
        return None;
    }
    Some(refusal(
        "off_canvas",
        format!(
            "layer {layer} は、当てた法則（{}）の置き場と大きさでは画面に収まらない。その層の法則を変えるか外す",
            laws.join("・")
        ),
        format!(
            "layer {layer} does not fit on the canvas where the laws on it ({}) place and size it; change or drop those laws",
            laws.join(", ")
        ),
    ))
}

/// Read a reply to the laws request, check it and apply it.
pub fn choose_laws(
    response: &str,
    context: &LawsContext,
    composed: &ComposedPlan,
    limits: PromptLimits,
) -> Result<Chosen, Refusal> {
    if response.len() > limits.max_response_bytes {
        return Err(refusal(
            "too_long",
            "答えが長すぎる".to_owned(),
            "the answer is too long".to_owned(),
        ));
    }
    let Ok(answer) = serde_json::from_str::<Value>(response) else {
        return Err(refusal(
            "not_json",
            "答えが JSON として読めない".to_owned(),
            "the answer does not read as JSON".to_owned(),
        ));
    };
    let answer = check(&answer, context, true)?;
    apply(&answer, context, composed)
}

/// Apply an answer without the count rule: the prototype's answers measured
/// with one law (the port's fixture) are applied as it applied them.
pub fn apply_laws_without_count_rule(
    answer: &Value,
    context: &LawsContext,
    composed: &ComposedPlan,
) -> Result<Chosen, Refusal> {
    let answer = check(answer, context, false)?;
    apply(&answer, context, composed)
}

#[cfg(test)]
mod tests {
    use inku_ddl::NormalizedDdlDocument;

    use super::*;
    use crate::core_boundary::{CompilerOptions, compile_committed};

    /// A grid the laws lay anew carries its cells and centroid as the core
    /// tiles them: short-edge units, the centroid from the domain's corner.
    #[test]
    fn a_grid_laid_anew_carries_the_cells_the_core_tiles() {
        let fixture: Value =
            serde_json::from_str(include_str!("../tests/data/laws-port-v1.json")).unwrap();
        let case = fixture["cases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|case| case["id"] == "ja-12-wide")
            .unwrap();
        let mut compiler = case["compiler"].clone();
        compiler["host"]["canvas_format_id"] = json!("wide");
        let compiler: CompilerOptions = serde_json::from_value(compiler).unwrap();
        let document = NormalizedDdlDocument::new(
            case["source"].as_str().unwrap(),
            ResolvedInstructionLanguage::Ja,
            Vec::new(),
        )
        .unwrap();
        let score = compile_committed(document, &[], &compiler)
            .unwrap()
            .score
            .unwrap();
        let units = Units::of(compiler.host.canvas_format_id()).unwrap();
        let compiled = score
            .instructions
            .iter()
            .find(|instruction| {
                matches!(
                    recipe(instruction),
                    Some(ResolvedPlacementRecipe::Grid { .. })
                )
            })
            .unwrap();
        let Some(ResolvedPlacementRecipe::Grid { columns, rows, .. }) = recipe(compiled).cloned()
        else {
            unreachable!("a grid was found");
        };
        let region = compiled.at.as_ref().unwrap().region;
        let mut laid = compiled.clone();
        build_grid(&mut laid, region, columns, rows, units);
        let (want, got) = (resolved(compiled).unwrap(), resolved(&laid).unwrap());
        let near = |a: f64, b: f64| assert!((a - b).abs() < 1e-12, "{a} != {b}");
        near(got.domain.x, want.domain.x);
        near(got.domain.y, want.domain.y);
        let (
            ResolvedPlacementRecipe::Grid {
                cell_width: want_width,
                cell_height: want_height,
                centroid: want_centroid,
                ..
            },
            ResolvedPlacementRecipe::Grid {
                cell_width,
                cell_height,
                centroid,
                ..
            },
        ) = (&want.recipe, &got.recipe)
        else {
            unreachable!("both are grids");
        };
        near(*cell_width, *want_width);
        near(*cell_height, *want_height);
        near(centroid.x, want_centroid.x);
        near(centroid.y, want_centroid.y);
    }
}
