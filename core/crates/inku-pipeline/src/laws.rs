//! The laws stage (`choose_laws`), stage B-2c of the laws port (the author's
//! decisions of 2026-10-19: the laws are written in numbers, after the
//! composition, and stay off until every law is in).
//!
//! After the composition places a plan's layers, a reader chooses laws of
//! painting, design and music for the work and the values each law takes; it
//! writes no coordinates. The core applies the laws to a copy of the composed
//! document's Score as the prototype did, and prints the layers the laws
//! changed again in numbers: a numeric point, the two ends of a row or a line,
//! a numeric range, a numeric size. Every other layer keeps the bytes the
//! composition printed. The prototype let the canvas cut a mark; a mark at a
//! numeric point lies wholly on it, so a line is printed by the ends the canvas
//! shows, a pair as a row of two (whose marks the canvas may cut), and another
//! mark that leaves the canvas is refused ([`off_canvas`]).
//!
//! This stage holds the placement, size and hand laws (B1 to B8, B15, B21). The
//! computation is the prototype's, function by function and in its order. On a
//! square canvas it is the prototype's to the bit; on another canvas, places
//! stay canvas fractions and lengths compared with mark sizes are taken in
//! short-edge units (the prototype ran on square canvases only).

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
pub const LAWS: [&str; 10] = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B15", "B21"];

/// The laws that set a layer's place; a layer takes one of them at most.
const PLACEMENT: [&str; 7] = ["B1", "B2", "B3", "B4", "B5", "B7", "B8"];

/// The prototype's values of `PHI = (1 + 5 ** 0.5) / 2`, as Python computed them.
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

const LINE: [Primitive; 2] = [Primitive::Line, Primitive::FreeLine];
/// The closed shapes and the arc: what subordination sizes.
const SIZED: [Primitive; 7] = [
    Primitive::Circle,
    Primitive::Ellipse,
    Primitive::Triangle,
    Primitive::Square,
    Primitive::Polygon,
    Primitive::Cloudform,
    Primitive::Arc,
];

fn is_line(primitive: Primitive) -> bool {
    LINE.contains(&primitive)
}

/// Python's `max(a, b)` and `min(a, b)`: the first argument unless the second
/// is strictly larger (smaller). A signed zero is kept as Python keeps it.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

fn clamp_between(value: f64, low: f64, high: f64) -> f64 {
    py_max(low, py_min(high, value))
}

/// A moved center stays inside the canvas by `EDGE`.
fn clamp(value: f64) -> f64 {
    clamp_between(value, EDGE, 1.0 - EDGE)
}

/// Python's `round(value, 3)`: the binary value correctly rounded to three
/// decimals, a tie to even (Rust's fixed-precision formatting does the same).
fn round3(value: f64) -> f64 {
    format!("{value:.3}").parse().unwrap_or(value)
}

/// The canvas in short-edge units: the width and height over the short edge.
#[derive(Clone, Copy, Debug, PartialEq)]
struct Units {
    x: f64,
    y: f64,
}

impl Units {
    fn of(canvas_format_id: &str) -> Option<Self> {
        let format = lookup_canvas_format(canvas_format_id).ok()?;
        let short = f64::from(format.width_units.min(format.height_units));
        Some(Self {
            x: f64::from(format.width_units) / short,
            y: f64::from(format.height_units) / short,
        })
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
enum Belongs {
    Source,
    Plugin,
}

/// The source layer an instruction draws: its own sentence, or the sentence of
/// the plugin word that emitted it.
fn layer_of(instruction: &Instruction) -> Option<(usize, Belongs)> {
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
fn layers(score: &Score) -> BTreeMap<usize, Vec<usize>> {
    let mut found: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for (position, instruction) in score.instructions.iter().enumerate() {
        if let Some((index, _)) = layer_of(instruction) {
            found.entry(index).or_default().push(position);
        }
    }
    found
}

fn resolved(instruction: &Instruction) -> Option<&inku_score::ResolvedArrangement> {
    instruction.arrangement.as_ref()?.resolved.as_ref()
}

fn recipe(instruction: &Instruction) -> Option<&ResolvedPlacementRecipe> {
    resolved(instruction).map(|resolved| &resolved.recipe)
}

fn count_of(instruction: &Instruction) -> u32 {
    match instruction
        .arrangement
        .as_ref()
        .map(|arrangement| arrangement.count)
    {
        None | Some(0) => 1,
        Some(count) => count,
    }
}

fn is_row_recipe(instruction: &Instruction) -> bool {
    matches!(
        recipe(instruction),
        Some(
            ResolvedPlacementRecipe::HorizontalLine { .. }
                | ResolvedPlacementRecipe::VerticalLine { .. }
                | ResolvedPlacementRecipe::DiagonalLine { .. }
        )
    )
}

fn is_row(instruction: &Instruction) -> bool {
    is_row_recipe(instruction) && count_of(instruction) >= 2
}

fn is_scatter(instruction: &Instruction) -> bool {
    matches!(
        recipe(instruction),
        Some(ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation)
    )
}

/// The named region of the anchor, else the instruction's region.
fn anchor_region(instruction: &Instruction) -> Option<[f64; 4]> {
    match resolved(instruction).map(|resolved| &resolved.anchor) {
        Some(ResolvedPlacementAnchor::Named { region }) => Some(*region),
        _ => instruction.at.as_ref().map(|at| at.region),
    }
}

fn region_or_center(instruction: &Instruction) -> [f64; 4] {
    anchor_region(instruction).unwrap_or([0.5; 4])
}

fn center_of(instruction: &Instruction) -> [f64; 2] {
    let region = region_or_center(instruction);
    [(region[0] + region[2]) / 2.0, (region[1] + region[3]) / 2.0]
}

fn domain_of(instruction: &Instruction) -> Option<[f64; 2]> {
    resolved(instruction).map(|resolved| [resolved.domain.x, resolved.domain.y])
}

/// Half the width and height of one mark, in short-edge units.
fn extent(instruction: &Instruction, units: Units) -> (f64, f64) {
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

fn largest_extent(instruction: &Instruction, units: Units) -> f64 {
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
fn mark_centers(instruction: &Instruction, units: Units) -> Option<Vec<[f64; 2]>> {
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

fn resolved_mut(instruction: &mut Instruction) -> Option<&mut inku_score::ResolvedArrangement> {
    instruction.arrangement.as_mut()?.resolved.as_mut()
}

fn set_point_region(instruction: &mut Instruction, x: f64, y: f64) {
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

fn scale_geometry(instruction: &mut Instruction, factor: f64) {
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

/// A grid recipe over a region; the last row may be partly filled.
fn build_grid(
    instruction: &mut Instruction,
    region: [f64; 4],
    columns: u64,
    rows: u64,
    units: Units,
) {
    let count = count_of(instruction);
    let [x0, y0, x1, y1] = region;
    let (cw, ch) = ((x1 - x0) / columns as f64, (y1 - y0) / rows as f64);
    let mut cells = Vec::new();
    for j in 0..rows {
        for i in 0..columns {
            cells.push([x0 + cw * (i as f64 + 0.5), y0 + ch * (j as f64 + 0.5)]);
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
        resolved.domain = inku_score::Point::new((x1 - x0) * units.x, (y1 - y0) * units.y);
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

/// One mark of a layer opened into marks: the layer's instruction alone at a point.
fn single(template: &Instruction, point: [f64; 2]) -> Instruction {
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
    mark
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

fn summaries(score: &Score, units: Units) -> Vec<LayerSummary> {
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

/// What a work's layers allow, read from the composed document's Score.
#[derive(Clone, Debug)]
pub struct LawsContext {
    score: Score,
    units: Units,
    /// The CIELAB lightness of each of the nine colors the run's palette draws.
    lightness: Option<BTreeMap<&'static str, f64>>,
    summaries: Vec<LayerSummary>,
    /// The layer index of the plan's first layer: plugin sentences come first.
    first_plan_layer: usize,
}

/// The CIELAB lightness (0 to 1) of an sRGB color, as the prototype measured it.
fn lightness_of([r, g, b]: [u8; 3]) -> f64 {
    let linear = |channel: u8| {
        let c = f64::from(channel) / 255.0;
        if c <= 0.04045 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    };
    let lin = [linear(r), linear(g), linear(b)];
    let y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
    let f = |t: f64| {
        if t > 0.008856 {
            t.powf(1.0 / 3.0)
        } else {
            7.787 * t + 16.0 / 116.0
        }
    };
    (116.0 * f(y) - 16.0) / 100.0
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
            summaries,
            first_plan_layer,
        })
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
            "B15" | "B21" => self
                .summaries
                .iter()
                .filter(|summary| summary.arranged != Some("plugin"))
                .map(|summary| summary.layer)
                .collect(),
            _ => Vec::new(),
        }
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

const LAW_TEXTS: [(&str, LawText); 10] = [
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
];

const SYSTEM_JA: &str = "あなたは、絵画・意匠・音楽の法則を組み合わせて、作品の記述を一枚の画にする係です。
作品は、記述（作者の文）から作った楽譜です。楽譜の層（物）は、まだ法則なしで置かれています。
法則の一覧（10）から、この作品に使う法則を選び、法則ごとの値を選択肢から選んでください。座標は書きません。座標と大きさは、道具が法則から計算します。

決まり:
1. 主の法則（main_law）を一つ決めます。画を見た人が最初に読み取る、画の骨組みになる法則です。B21 は主にしません。主の層（main_layer）も一つ決めます。
2. 法則の数は、送る文の最後の「この答えの決まり」に従います。法則は、層をいくつに当てても1つと数えます。
3. 一つの層に、置き場の法則（B1〜B5・B7・B8）は一つまで。大きさの法則（B6・B15）は掛け合わせます。
4. 記述が名指した物の種類と道具は変えません。記述そのものが数を書いた物（「一羽」「三度」など）は数を変えず、その層の番号を description_counts に入れます。
5. 道具は、置き場 → 大きさ → 空気遠近 → 手 の順に当てます。決まりに合わない答えは、理由を添えて返されます。
6. reason には、記述の言葉を「」で引いて、主の法則を選んだ理由を1〜2行で書きます。
答えは決まった形の JSON で返します。laws には、使う法則の番号を鍵にして、法則ごとの値を書きます。";

const SYSTEM_EN: &str = "You combine laws of painting, design and music to make a work's description into one picture.
The work is a Score made from the description (the author's words). The Score's layers (things) are placed without laws yet.
From the list of laws (10), choose the laws this work uses and, for each law, its values from the choices. Write no coordinates: the tool computes coordinates and sizes from the laws.

Rules:
1. Choose one main law (main_law): the law a viewer reads first, the framework of the picture. B21 is never the main law. Choose one main layer (main_layer) too.
2. The number of laws follows \"The rule of this answer\" at the end of the message. A law counts as one however many layers it takes.
3. A layer takes one placement law (B1 to B5, B7, B8) at most. The size laws (B6, B15) multiply.
4. Keep the kinds of things and the tools the description names. Keep the count of a thing the description itself counts (\"one heron\", \"three times\"), and put that layer's number in description_counts.
5. The tool applies placement, then size, then aerial perspective, then the hand. An answer that breaks the rules comes back with the reason.
6. In reason, quote the description's words in “ ” and say in one or two lines why you chose the main law.
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
    r#"{"main_layer":0,"main_law":"B1","description_counts":[0],"laws":{"B1":{"targets":[{"layer":0,"at":"line_left","span":"full"}]},"B21":{"targets":[{"layer":2,"hand":"fine"}]}},"reason":"「一本の木が立っていた」の木を画の骨にするため、幹を黄金分割の左の線に全幅で立てた。"}"#,
    r#"{"main_layer":0,"main_law":"B1","description_counts":[0],"laws":{"B1":{"targets":[{"layer":0,"at":"line_left","span":"full"}]},"B21":{"targets":[{"layer":2,"hand":"fine"}]}},"reason":"To make the tree of “a single tree … stood” the bone of the picture, its trunk stands at full length on the golden section's left line."}"#,
];

const COUNT_RULE: [&str; 2] = [
    "## この答えの決まり（V2）\n主の法則を支える法則を1つか2つだけ選ぶ。laws は主を含めて2〜3にする。",
    "## The rule of this answer (V2)\nChoose only one or two laws that support the main law. laws holds two or three laws, the main law included.",
];

fn language_index(language: ResolvedInstructionLanguage) -> usize {
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
            "## 法則の一覧（10）",
            "## 答え全体の例（この作品と別の記述）",
        ],
        ResolvedInstructionLanguage::En => [
            "## Description",
            "## The Score's layers (before the laws)",
            "## Ground: ",
            "## The laws (10)",
            "## A whole answer (for another description)",
        ],
    };
    lines.push(heads[0].to_owned());
    lines.push(description.to_owned());
    lines.push(String::new());
    lines.push(heads[1].to_owned());
    lines.push(LAYER_NOTE[at].to_owned());
    for summary in &context.summaries {
        lines.push(serde_json::to_string(summary).unwrap_or_default());
    }
    lines.push(String::new());
    lines.push(format!("{}{ground}", heads[2]));
    lines.push(String::new());
    lines.push(heads[3].to_owned());
    lines.push(AT_NOTE[at].to_owned());
    let offered = context.offered();
    for (law, text) in &LAW_TEXTS {
        let absent = !offered.contains(law);
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => format!(
                "### {law} {}（{}）{}",
                text.name[0],
                text.family[0],
                if absent {
                    "（この作品では当てる層が無い）"
                } else {
                    ""
                }
            ),
            ResolvedInstructionLanguage::En => format!(
                "### {law} {} ({}){}",
                text.name[1],
                text.family[1],
                if absent {
                    " (no layer of this work can take it)"
                } else {
                    ""
                }
            ),
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
        _ => return None,
    })
}

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
/// original message and the latest reason only, as the prototype resent it.
pub(crate) fn with_laws_feedback(
    mut prompt: LlmPrompt,
    refusal: &Refusal,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    let reply = match prompt.instruction_language {
        ResolvedInstructionLanguage::Ja => format!(
            "\n\n## 前の答えへの道具の返事\n前の答えは使えなかった: {}\n直した答えを返す。",
            refusal.ja
        ),
        ResolvedInstructionLanguage::En => format!(
            "\n\n## The tool's reply to the previous answer\nThe previous answer could not be used: {}\nReturn a corrected answer.",
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

fn refusal(code: &'static str, ja: String, en: String) -> Refusal {
    Refusal { code, ja, en }
}

fn shown(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        other => other.to_string(),
    }
}

/// The answer against its schema: the transport may not hold a reply to it.
fn conform(value: &Value, schema: &Value, path: &str) -> Result<(), Refusal> {
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

fn layer_number(value: &Value) -> usize {
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
        "B1" | "B2" | "B3" | "B4" | "B5" | "B8" | "B21" => value["targets"]
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
        "B7" => vec![layer_number(&value["layer"])],
        "B15" => list("layers"),
        _ => Vec::new(),
    }
}

/// A conformed answer: the laws in the order this stage applies them.
struct Answer {
    main_layer: usize,
    main_law: String,
    laws: BTreeMap<&'static str, Value>,
}

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
    Ok(Answer {
        main_layer,
        main_law,
        laws,
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

#[derive(Clone, Copy, Debug)]
struct Row {
    from: [f64; 2],
    to: [f64; 2],
}

struct Compiler<'a> {
    context: &'a LawsContext,
    score: Score,
    laws: &'a BTreeMap<&'static str, Value>,
    main: usize,
    notes: Vec<Note>,
    /// The layers a law laid in a row, in the order the laws arranged them.
    arranged: Vec<(usize, Row)>,
    arranged_by: BTreeMap<usize, &'static str>,
    pinned: BTreeSet<usize>,
    /// The layers B8 opened into a pair.
    paired: BTreeSet<usize>,
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

    fn arrange(&mut self, layer: usize, row: Row, law: &'static str) {
        if let Some(entry) = self.arranged.iter_mut().find(|(found, _)| *found == layer) {
            entry.1 = row;
        } else {
            self.arranged.push((layer, row));
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
                    self.arrange(layer, Row { from: p0, to: p1 }, law);
                } else if is_line(shape) {
                    let (p0, p1) = self.span_on(axis, value, current, &instruction);
                    let target = &mut self.score.instructions[position];
                    moved(target);
                    apply_line(target, p0, p1);
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
            if count_of(target) >= 2 {
                apply_row(target, p0, p1, units);
                self.arrange(layer, Row { from: p0, to: p1 }, "B5");
            } else if is_line(target.primitive) {
                apply_line(target, p0, p1);
            } else {
                return Err(refusal(
                    "armature_single_shape",
                    format!("B5: layer {layer} は1つの閉じた形で、骨組みの線に並べられない"),
                    format!("B5: layer {layer} is one closed shape and cannot lie on the armature"),
                ));
            }
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
                // The pair mirrors: the second mark turns the other way. The
                // pair is printed as a row of two, whose marks share one turn;
                // the mirrored one waits for a numeric angle.
                let mut marks = points.map(|point| single(&instruction, point));
                let turned = marks[1].rotation.filter(|turn| *turn != 0.0);
                if let Some(turn) = turned {
                    marks[1].rotation = Some(-turn);
                    self.note("pair_mirror_unwritten", Some(layer), None);
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

    fn spacing(&self, row: Row, count: u32) -> f64 {
        self.units().distance(row.from, row.to) / f64::from(count.saturating_sub(1).max(1))
    }

    /// Stretch a row toward the inner frame until its spacing is `spacing`, as
    /// far as the frame allows; a layer set on a point keeps its center.
    fn stretch(&mut self, layer: usize, row: Row, position: usize, spacing: f64) -> f64 {
        let units = self.units();
        let count = count_of(&self.score.instructions[position]);
        let pinned = self.pinned.contains(&layer);
        let along = hypot(row.to[0] - row.from[0], row.to[1] - row.from[1]);
        let physical = units.distance(row.from, row.to);
        let per = if physical > 0.0 {
            along / physical
        } else {
            1.0
        };
        let length = spacing * f64::from(count - 1) * per;
        let (q0, q1) = stretch_span(row.from, row.to, length, pinned);
        let mut now = row;
        if (q0, q1) != (row.from, row.to) {
            apply_row(&mut self.score.instructions[position], q0, q1, units);
            now = Row { from: q0, to: q1 };
            self.arrange(layer, now, self.arranged_by[&layer]);
            self.note("row_stretched", Some(layer), Some(units.distance(q0, q1)));
        }
        self.spacing(now, count)
    }

    /// A1: a row a law set closer than its origin drew its marks (and closer
    /// than touching) is first stretched toward the inner frame; what is still
    /// missing is shrunk, never below the floor. Lines keep their length.
    fn fit(&mut self) {
        let units = self.units();
        for (layer, row) in self.arranged.clone() {
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
            let origin = layers(&self.context.score)
                .remove(&layer)
                .and_then(|positions| positions.first().copied())
                .map_or(0.0, |position| {
                    origin_ratio(&self.context.score.instructions[position], units)
                });
            let (allowed, target) = fit_ratio(origin);
            let count = count_of(&self.score.instructions[first]);
            let spacing = self.spacing(row, count);
            if width <= 0.0 || spacing <= 0.0 || width <= allowed * spacing {
                continue;
            }
            let spacing = self.stretch(layer, row, first, width / target);
            if width <= allowed * spacing {
                continue;
            }
            let mut factor = target * spacing / width;
            if factor < FIT_FLOOR {
                self.note("shrink_floor", Some(layer), Some(factor));
                factor = FIT_FLOOR;
            }
            for position in found {
                scale_geometry(&mut self.score.instructions[position], factor);
            }
            self.note("shrunk_to_spacing", Some(layer), Some(factor));
        }
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

    fn run(mut self) -> Result<(Score, Vec<Note>, BTreeSet<usize>), Refusal> {
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
        self.fit();
        self.aerial_size();
        self.aerial_color();
        self.hands();
        self.check_colors()?;
        Ok((self.score, self.notes, self.paired))
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
}

/// The composed plan as the laws print it: the layers they changed are edited
/// and carry what they write in numbers, a layer for each composed layer.
#[derive(Clone, Debug, PartialEq)]
pub struct LawsPrint {
    pub plan: WorkPlan,
    pub ranges: Vec<Option<ComposedRange>>,
    pub joints: Vec<Option<String>>,
    pub numeric: Vec<Option<NumericWriting>>,
    /// The plan layers the laws changed (their place in the composed plan).
    pub changed: Vec<usize>,
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
fn row_ends(instruction: &Instruction, units: Units) -> Option<NumericPlace> {
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
fn line_ends(instruction: &Instruction, units: Units) -> Option<NumericPlace> {
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
fn moved_range(instruction: &Instruction, units: Units) -> Option<NumericPlace> {
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
fn numeric_size(instruction: &Instruction, units: Units) -> Option<NumericSize> {
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
                ResolvedPlacementRecipe::Grid { .. }
                | ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation => {
                    moved_range(after, units)?
                }
                _ => return None,
            }
        });
    }
    let size = |instruction: &Instruction| 2.0 * largest_extent(instruction, units);
    let factor = if size(before) != 0.0 {
        size(after) / size(before)
    } else {
        1.0
    };
    if (factor - 1.0).abs() > 1e-9 && !(moved && single_line) {
        numeric.size = Some(numeric_size(after, units)?);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
    }
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
    // A pair is placed in numbers; a relation would move its marks again.
    let dropped = before.relation.is_some() && after.relation.is_none();
    let keep_joint = !(paired || dropped);
    Some(Edit {
        layer,
        numeric,
        keep_joint,
    })
}

/// The composed plan printed with what the laws changed, or `None` when a
/// changed layer is one the printer cannot write in numbers.
fn print_changes(
    composed: &ComposedPlan,
    context: &LawsContext,
    after: &Score,
    hands: &BTreeMap<usize, Hand>,
    paired: &BTreeSet<usize>,
) -> Option<LawsPrint> {
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
            continue;
        }
        print.changed.push(k);
        let [before] = was.as_slice() else {
            return None;
        };
        if is.len() != if paired.contains(&index) { 2 } else { 1 } {
            return None;
        }
        let edit = edit_layer(
            layer,
            before,
            &is,
            hands.get(&index).copied(),
            context.units,
        )?;
        print.plan.layers.push(edit.layer);
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
        print.numeric.push(Some(edit.numeric));
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
        pinned: BTreeSet::new(),
        paired: BTreeSet::new(),
    };
    let (after, notes, paired) = compiler.run()?;
    let mut hands = BTreeMap::new();
    if let Some(value) = answer.laws.get("B21") {
        for target in value["targets"].as_array().into_iter().flatten() {
            if let Some(hand) = target["hand"].as_str().and_then(Hand::parse) {
                hands.insert(layer_number(&target["layer"]), hand);
            }
        }
    }
    let print = print_changes(composed, context, &after, &hands, &paired).ok_or_else(|| {
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
        notes,
        print,
        named,
    })
}

/// The reason to ask again when the printed document cannot hold a layer the
/// laws changed on the canvas: a mark the laws place at a point is drawn whole,
/// where the prototype let the canvas cut it. `instruction` is the source
/// instruction of the printed document; `None` when it is not a changed layer.
#[must_use]
pub fn off_canvas(chosen: &Chosen, context: &LawsContext, instruction: usize) -> Option<Refusal> {
    let k = instruction.checked_sub(context.first_plan_layer)?;
    if !chosen.print.changed.contains(&k) {
        return None;
    }
    let layer = instruction;
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
