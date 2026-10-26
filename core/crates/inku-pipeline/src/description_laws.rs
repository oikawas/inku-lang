//! What the tool does with the DDL of a composed read-and-draw work
//! (2026-10-26): it measures each thing against the laws its composition gave
//! it, fits a thing a little off by rewriting its sentences' numbers, names the
//! things far off for the writing request to be asked again, and builds a
//! card's thing as the laws stage builds it.
//!
//! The measure and the fit are the prototype's (read-draw-laws-20261026,
//! `tools/laws_core.py`): a thing's box is the union of its sentences' boxes,
//! read from the numbers the sentences write. Here the parser reads the
//! numbers, and each one is rewritten at its place in the sentence, so no
//! other character changes. A bundle of lines stacked across a proportion
//! law's line is placed by its center (the prototype placed each line on the
//! law's line).

use std::collections::BTreeMap;

use inku_ddl::work_plan::{WorkPlan, WorkPlanLayer, plan_layer, print_work_plan_with_numbers};
use inku_ddl::{
    ExactFraction, MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage,
    SemanticExplicitGeometry, SemanticGeometryValue, SemanticInstruction, SourceSpan,
    compile_typed_ddl,
};
use inku_score::Score;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::core_boundary::ResolvedPaletteDto;
use crate::description_composition::{
    At, CARDS, CompositionAnswer, GOLDEN, MARGIN, Takes, at_target, composition_targets,
    law_things, number, proportion, spot,
};
use crate::laws::{ComposedPlan, LawsContext, apply_cards, count_of, layers};

/// A place within this of its target is right (short-edge units).
pub const OK_PLACE: f64 = 0.02;
/// A ratio of size within this of its target is right.
pub const OK_RATIO: f64 = 0.05;
/// A move beyond this is far: asked again, not fitted.
pub const FAR_MOVE: f64 = 0.15;
/// A change of size beyond this factor is far.
pub const FAR_SCALE: f64 = 1.5;
/// A moved center stays this far inside the edges (the laws stage's).
const EDGE: f64 = 0.06;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8_192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

/// One sentence of a composed work's DDL and the thing it draws (0 for a
/// ground, a background or a sentence of no thing).
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ThingSentence {
    pub thing: u64,
    pub text: String,
}

/// How a law and thing measured.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MeasureState {
    /// Within the limit.
    Ok,
    /// Over the limit, measured without fitting.
    Off,
    /// Too far to fit: the writing request is asked again.
    Far,
    /// Fitted by rewriting the thing's numbers.
    Fitted,
    /// Fitted as far as the canvas's edge.
    Clamped,
    /// Fitting would put a mark off the canvas: left as it was.
    OffCanvas,
    /// Nothing to measure (no numeric place, too few parts, a grid of
    /// sentences).
    Unmeasurable,
    /// A law the drawer draws or the tool builds, not measured.
    NotMeasured,
}

/// One law and thing's measure: how far the thing was from its target (in
/// short-edge units for a place, as a fraction for a ratio of size) and what
/// was done.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LawMeasure {
    pub law: String,
    pub thing: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub deviation: Option<f64>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub unit: String,
    pub state: MeasureState,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub detail: String,
}

/// A thing the writing request is asked again about: a law it is far from, a
/// thing no sentence draws, or a card's thing not written in one sentence.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ThingProblem {
    pub thing: u64,
    pub law: String,
    pub measured: String,
    pub target: String,
}

// --- a sentence's numbers ----------------------------------------------------------------------

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PlaceKind {
    /// A point: horizontal, vertical.
    Point,
    /// A range as it is written: horizontal from, to, vertical from, to.
    Range,
    /// Two points: horizontal, vertical, then horizontal, vertical.
    Segment,
}

/// A sentence's numbers as the parser reads them, each with its place in the
/// sentence.
#[derive(Clone, Debug, PartialEq)]
struct Numbers {
    kind: PlaceKind,
    values: Vec<f64>,
    spans: Vec<(usize, usize)>,
    /// Each size written, by name, with its place.
    sizes: BTreeMap<&'static str, (f64, (usize, usize))>,
    rotation: f64,
    /// The sentence lines its marks up (one sentence's row).
    row: bool,
}

fn span_of(span: &SourceSpan) -> (usize, usize) {
    (span.start_byte, span.end_byte)
}

#[allow(clippy::cast_precision_loss)]
fn fraction(value: ExactFraction) -> f64 {
    value.numerator() as f64 / value.denominator() as f64
}

/// The numbers of one sentence, or `None` when it has no numeric place (a
/// ground, a background, a place in words) or when a number is not found
/// where the parser says it is.
fn parse(line: &str, language: ResolvedInstructionLanguage) -> Option<Numbers> {
    let document = NormalizedDdlDocument::new(line, language, Vec::new()).ok()?;
    let compilation = compile_typed_ddl(document, &[], None, LIMITS);
    let semantic = compilation.semantic_document.as_ref()?;
    let [instruction] = semantic.ast.instructions.as_slice() else {
        return None;
    };
    let numbers = numbers_of(instruction, line, language)?;
    let written = |(start, end): (usize, usize), value: f64| {
        line.get(start..end)
            .and_then(|text| text.parse::<f64>().ok())
            .is_some_and(|read| (read - value).abs() < 1e-9)
    };
    let found = numbers
        .spans
        .iter()
        .zip(&numbers.values)
        .all(|(span, value)| written(*span, *value))
        && numbers
            .sizes
            .values()
            .all(|(value, span)| written(*span, *value));
    found.then_some(numbers)
}

fn numbers_of(
    instruction: &SemanticInstruction,
    line: &str,
    language: ResolvedInstructionLanguage,
) -> Option<Numbers> {
    let entity = &instruction.entity;
    let (kind, values, spans) = if let Some(segment) = &entity.numeric_segment {
        (
            PlaceKind::Segment,
            segment.ends.map(fraction).to_vec(),
            segment.end_spans.iter().map(span_of).collect(),
        )
    } else if let Some(range) = &entity.numeric_range {
        // The bounds in region order (left, top, right, bottom), as written.
        let bounds = range.bounds.map(fraction);
        let at = &range.bound_spans;
        (
            PlaceKind::Range,
            vec![bounds[0], bounds[2], bounds[1], bounds[3]],
            vec![
                span_of(&at[0]),
                span_of(&at[2]),
                span_of(&at[1]),
                span_of(&at[3]),
            ],
        )
    } else if let Some(position) = &entity.numeric_position {
        (
            PlaceKind::Point,
            vec![
                position.x.decimal.value.to_f64().ok()?,
                position.y.decimal.value.to_f64().ok()?,
            ],
            vec![
                span_of(&position.x.decimal.provenance.span),
                span_of(&position.y.decimal.provenance.span),
            ],
        )
    } else {
        return None;
    };
    let mut sizes = BTreeMap::new();
    let mut size = |name: &'static str, value: &SemanticGeometryValue| -> Option<()> {
        sizes.insert(
            name,
            (
                value.decimal.value.to_f64().ok()?,
                span_of(&value.decimal.provenance.span),
            ),
        );
        Some(())
    };
    for geometry in entity
        .explicit_geometry
        .iter()
        .chain(&entity.additional_explicit_geometries)
    {
        match geometry {
            SemanticExplicitGeometry::Radius(value) => size("radius", value)?,
            SemanticExplicitGeometry::Diameter(value) => size("diameter", value)?,
            SemanticExplicitGeometry::Length(value) => size("length", value)?,
            SemanticExplicitGeometry::Side(value) => size("side", value)?,
            SemanticExplicitGeometry::WidthHeight { width, height } => {
                size("width", width)?;
                size("height", height)?;
            }
            SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
                size("chord", chord)?;
                size("sagitta", sagitta)?;
            }
        }
    }
    let rotation = entity
        .numeric_angle
        .as_ref()
        .map_or(0.0, |angle| fraction(angle.degrees));
    let row = match language {
        ResolvedInstructionLanguage::Ja => {
            let text = line.trim_end();
            text.ends_with("並べる。") || text.ends_with("並べる")
        }
        ResolvedInstructionLanguage::En => {
            let text = line.trim_start().to_lowercase();
            text.starts_with("line up") || text.starts_with("line-up")
        }
    };
    Some(Numbers {
        kind,
        values,
        spans,
        sizes,
        rotation,
        row,
    })
}

/// The width and height of one mark in short-edge units, before turning;
/// `None` when the sentence writes no size.
fn mark_size(numbers: &Numbers) -> Option<(f64, f64)> {
    let get = |name: &str| numbers.sizes.get(name).map(|(value, _)| *value);
    if get("width").is_some() || get("height").is_some() {
        let width = get("width").or(get("height"))?;
        let height = get("height").or(get("width"))?;
        return Some((width, height));
    }
    if let Some(diameter) = get("diameter") {
        return Some((diameter, diameter));
    }
    if let Some(radius) = get("radius") {
        return Some((2.0 * radius, 2.0 * radius));
    }
    if let Some(side) = get("side") {
        return Some((side, side));
    }
    if let Some(chord) = get("chord") {
        return Some((chord, get("sagitta").unwrap_or(0.0)));
    }
    get("length").map(|length| (length, 0.0))
}

/// The box (left, top, right, bottom, in canvas fractions) a sentence's marks
/// take, as the prototype measured it.
fn sentence_box(numbers: &Numbers, units: [f64; 2]) -> [f64; 4] {
    let [ux, uy] = units;
    let values = &numbers.values;
    let size = mark_size(numbers);
    match numbers.kind {
        PlaceKind::Range => [
            values[0].min(values[1]),
            values[2].min(values[3]),
            values[0].max(values[1]),
            values[2].max(values[3]),
        ],
        PlaceKind::Segment => {
            let (hx, hy) = match (numbers.row, size) {
                (true, Some((width, height))) => (width / 2.0 / ux, height / 2.0 / uy),
                _ => (0.0, 0.0),
            };
            [
                values[0].min(values[2]) - hx,
                values[1].min(values[3]) - hy,
                values[0].max(values[2]) + hx,
                values[1].max(values[3]) + hy,
            ]
        }
        PlaceKind::Point => {
            let (width, height) = size.unwrap_or((0.0, 0.0));
            let turn = numbers.rotation.to_radians();
            let hx = (width / 2.0 * turn.cos()).abs() + (height / 2.0 * turn.sin()).abs();
            let hy = (width / 2.0 * turn.sin()).abs() + (height / 2.0 * turn.cos()).abs();
            [
                values[0] - hx / ux,
                values[1] - hy / uy,
                values[0] + hx / ux,
                values[1] + hy / uy,
            ]
        }
    }
}

fn union(boxes: impl IntoIterator<Item = [f64; 4]>) -> Option<[f64; 4]> {
    boxes.into_iter().reduce(|a, b| {
        [
            a[0].min(b[0]),
            a[1].min(b[1]),
            a[2].max(b[2]),
            a[3].max(b[3]),
        ]
    })
}

fn center(b: [f64; 4]) -> [f64; 2] {
    [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]
}

/// A box's long side in short-edge units: the size the laws compare.
fn extent(b: [f64; 4], units: [f64; 2]) -> f64 {
    ((b[2] - b[0]) * units[0]).max((b[3] - b[1]) * units[1])
}

fn inside(b: [f64; 4]) -> bool {
    b[0] >= -1e-6 && b[1] >= -1e-6 && b[2] <= 1.0 + 1e-6 && b[3] <= 1.0 + 1e-6
}

/// The sentence with its place's numbers replaced and its sizes multiplied.
fn rewritten(line: &str, numbers: &Numbers, values: Option<&[f64]>, scale: Option<f64>) -> String {
    let mut edits: Vec<((usize, usize), String)> = Vec::new();
    if let Some(values) = values {
        edits.extend(
            numbers
                .spans
                .iter()
                .zip(values)
                .map(|(span, value)| (*span, number(*value))),
        );
    }
    if let Some(scale) = scale {
        edits.extend(
            numbers
                .sizes
                .values()
                .map(|(value, span)| (*span, number(value * scale))),
        );
    }
    edits.sort_by_key(|((start, _), _)| std::cmp::Reverse(*start));
    let mut line = line.to_owned();
    for ((start, end), text) in edits {
        line.replace_range(start..end, &text);
    }
    line
}

/// The place's numbers moved by `(dx, dy)` and scaled by `s` about a point.
fn moved_values(numbers: &Numbers, dx: f64, dy: f64, s: f64, about: [f64; 2]) -> Vec<f64> {
    let point = |x: f64, y: f64| {
        (
            about[0] + s * (x - about[0]) + dx,
            about[1] + s * (y - about[1]) + dy,
        )
    };
    let v = &numbers.values;
    match numbers.kind {
        PlaceKind::Point => {
            let (x, y) = point(v[0], v[1]);
            vec![x, y]
        }
        PlaceKind::Segment => {
            let (x1, y1) = point(v[0], v[1]);
            let (x2, y2) = point(v[2], v[3]);
            vec![x1, y1, x2, y2]
        }
        PlaceKind::Range => {
            let (x0, y0) = point(v[0], v[2]);
            let (x1, y1) = point(v[1], v[3]);
            vec![x0, x1, y0, y1]
        }
    }
}

// --- the document and its things ---------------------------------------------------------------

/// A composed work's DDL after its paper's ratio, each sentence with its thing
/// and its numbers, on a canvas of `units` (its width and height over its short
/// side).
#[derive(Clone, Debug)]
pub struct ThingDocument {
    lines: Vec<String>,
    things: Vec<u64>,
    parsed: Vec<Option<Numbers>>,
    language: ResolvedInstructionLanguage,
    units: [f64; 2],
}

impl ThingDocument {
    #[must_use]
    pub fn new(
        sentences: &[ThingSentence],
        language: ResolvedInstructionLanguage,
        units: [f64; 2],
    ) -> Self {
        Self {
            lines: sentences.iter().map(|item| item.text.clone()).collect(),
            things: sentences.iter().map(|item| item.thing).collect(),
            parsed: sentences
                .iter()
                .map(|item| parse(&item.text, language))
                .collect(),
            language,
            units,
        }
    }

    /// The sentences, each with its thing.
    #[must_use]
    pub fn sentences(&self) -> Vec<ThingSentence> {
        self.lines
            .iter()
            .zip(&self.things)
            .map(|(text, thing)| ThingSentence {
                thing: *thing,
                text: text.clone(),
            })
            .collect()
    }

    /// The indexes of the thing's sentences.
    fn sentences_of(&self, thing: u64) -> Vec<usize> {
        (0..self.lines.len())
            .filter(|index| self.things[*index] == thing)
            .collect()
    }

    /// The indexes of the thing's sentences that have a numeric place.
    fn members(&self, thing: u64) -> Vec<usize> {
        self.sentences_of(thing)
            .into_iter()
            .filter(|index| self.parsed[*index].is_some())
            .collect()
    }

    fn numbers(&self, index: usize) -> &Numbers {
        self.parsed[index]
            .as_ref()
            .expect("a member has a numeric place")
    }

    fn box_of(&self, indexes: &[usize]) -> Option<[f64; 4]> {
        union(
            indexes
                .iter()
                .map(|index| sentence_box(self.numbers(*index), self.units)),
        )
    }

    /// The thing's parts: its sentences joined where one's box holds
    /// another's center or their centers nearly meet (a book's spine and its
    /// light stay together), each part in the order its sentences come.
    fn parts_of(&self, thing: u64) -> Vec<Vec<usize>> {
        let members = self.members(thing);
        let boxes: Vec<[f64; 4]> = members
            .iter()
            .map(|index| sentence_box(self.numbers(*index), self.units))
            .collect();
        let mut parent: Vec<usize> = (0..members.len()).collect();
        fn root(parent: &mut [usize], mut i: usize) -> usize {
            while parent[i] != i {
                parent[i] = parent[parent[i]];
                i = parent[i];
            }
            i
        }
        let holds = |outer: [f64; 4], point: [f64; 2]| {
            (outer[2] - outer[0]) * (outer[3] - outer[1]) > 0.0
                && outer[0] - 1e-9 <= point[0]
                && point[0] <= outer[2] + 1e-9
                && outer[1] - 1e-9 <= point[1]
                && point[1] <= outer[3] + 1e-9
        };
        for a in 0..members.len() {
            for b in a + 1..members.len() {
                let (ca, cb) = (center(boxes[a]), center(boxes[b]));
                if holds(boxes[a], cb)
                    || holds(boxes[b], ca)
                    || (ca[0] - cb[0]).hypot(ca[1] - cb[1]) < 0.015
                {
                    let (ra, rb) = (root(&mut parent, a), root(&mut parent, b));
                    parent[rb] = ra;
                }
            }
        }
        let mut groups: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
        for (i, member) in members.iter().enumerate() {
            let r = root(&mut parent, i);
            groups.entry(r).or_default().push(*member);
        }
        let mut parts: Vec<Vec<usize>> = groups.into_values().collect();
        parts.sort_by_key(|part| part[0]);
        parts
    }

    /// Rewrite these sentences' numbers; `false`, leaving them as they were,
    /// when a rewritten sentence does not read back or a mark would leave the
    /// canvas.
    fn rewrite(&mut self, new: Vec<(usize, String)>) -> bool {
        let mut read = Vec::new();
        for (index, line) in new {
            let Some(numbers) = parse(&line, self.language) else {
                return false;
            };
            if !inside(sentence_box(&numbers, self.units)) {
                return false;
            }
            read.push((index, line, numbers));
        }
        for (index, line, numbers) in read {
            self.lines[index] = line;
            self.parsed[index] = Some(numbers);
        }
        true
    }

    /// Move (and scale) these sentences; `false` when a mark would leave the
    /// canvas.
    fn move_by(&mut self, indexes: &[usize], dx: f64, dy: f64, s: f64, about: [f64; 2]) -> bool {
        let new: Vec<(usize, String)> = indexes
            .iter()
            .map(|index| {
                let numbers = self.numbers(*index);
                let values = moved_values(numbers, dx, dy, s, about);
                let scale = ((s - 1.0).abs() > f64::EPSILON).then_some(s);
                (
                    *index,
                    rewritten(&self.lines[*index], numbers, Some(&values), scale),
                )
            })
            .collect();
        self.rewrite(new)
    }

    /// A step's length in short-edge units.
    fn length(&self, dx: f64, dy: f64) -> f64 {
        (dx * self.units[0]).hypot(dy * self.units[1])
    }
}

// --- measuring and fitting ----------------------------------------------------------------------

enum Fit {
    Done,
    Clamped,
    Refused,
}

/// A thing sized by a base thing: (thing, base) and (law, ratio).
type Sizing = ((u64, u64), (&'static str, f64));

struct Measurer<'a> {
    doc: &'a mut ThingDocument,
    answer: &'a CompositionAnswer,
    fit: bool,
    records: Vec<LawMeasure>,
}

impl Measurer<'_> {
    fn record(
        &mut self,
        law: &str,
        thing: u64,
        deviation: Option<f64>,
        unit: &str,
        state: MeasureState,
        detail: &str,
    ) {
        self.records.push(LawMeasure {
            law: law.to_owned(),
            thing,
            deviation: deviation.map(|value| (value * 10_000.0).round() / 10_000.0),
            unit: unit.to_owned(),
            state,
            detail: detail.to_owned(),
        });
    }

    /// Record a measure; fit when asked, the deviation is over the limit and
    /// the move is not far.
    #[allow(clippy::too_many_arguments)]
    fn settle(
        &mut self,
        law: &str,
        thing: u64,
        deviation: Option<f64>,
        unit: &str,
        limit: f64,
        far: bool,
        apply: impl FnOnce(&mut ThingDocument) -> Fit,
    ) {
        let Some(deviation) = deviation else {
            self.record(law, thing, None, unit, MeasureState::Unmeasurable, "");
            return;
        };
        if deviation <= limit {
            self.record(law, thing, Some(deviation), unit, MeasureState::Ok, "");
        } else if !self.fit {
            self.record(law, thing, Some(deviation), unit, MeasureState::Off, "");
        } else if far {
            self.record(law, thing, Some(deviation), unit, MeasureState::Far, "");
        } else {
            let before = (self.doc.lines.clone(), self.doc.parsed.clone());
            match apply(self.doc) {
                Fit::Done => {
                    self.record(law, thing, Some(deviation), unit, MeasureState::Fitted, "")
                }
                Fit::Clamped => self.record(
                    law,
                    thing,
                    Some(deviation),
                    unit,
                    MeasureState::Clamped,
                    "the move stopped at the canvas's edge",
                ),
                Fit::Refused => {
                    (self.doc.lines, self.doc.parsed) = before;
                    self.record(
                        law,
                        thing,
                        Some(deviation),
                        unit,
                        MeasureState::OffCanvas,
                        "",
                    );
                }
            }
        }
    }

    fn unmeasurable(&mut self, law: &str, thing: u64, detail: &str) {
        self.record(
            law,
            thing,
            None,
            "place",
            MeasureState::Unmeasurable,
            detail,
        );
    }

    fn kind(&self, thing: u64) -> &str {
        self.answer
            .thing(thing)
            .map_or("", |item| item.kind.as_str())
    }
}

/// Move a whole thing, stopping at the canvas's edge.
fn translate_thing(doc: &mut ThingDocument, thing: u64, dx: f64, dy: f64) -> Fit {
    let members = doc.members(thing);
    let Some(b) = doc.box_of(&members) else {
        return Fit::Refused;
    };
    let kept = (dx.max(-b[0]).min(1.0 - b[2]), dy.max(-b[1]).min(1.0 - b[3]));
    if !doc.move_by(&members, kept.0, kept.1, 1.0, [0.0, 0.0]) {
        return Fit::Refused;
    }
    if (kept.0 - dx).hypot(kept.1 - dy) > 1e-9 {
        Fit::Clamped
    } else {
        Fit::Done
    }
}

fn move_parts(doc: &mut ThingDocument, moves: &[(Vec<usize>, f64, f64)]) -> Fit {
    for (part, dx, dy) in moves {
        if !doc.move_by(part, *dx, *dy, 1.0, [0.0, 0.0]) {
            return Fit::Refused;
        }
    }
    Fit::Done
}

/// Measure each measurable law and thing of a composed work; with `fit`, move
/// the things a little off as the law says (in the laws stage's order) and
/// leave the far ones. A card's thing is the tool's, and only C1's place is
/// measured, never fitted.
#[allow(clippy::too_many_lines)]
pub fn measure(doc: &mut ThingDocument, answer: &CompositionAnswer, fit: bool) -> Vec<LawMeasure> {
    let mut m = Measurer {
        doc,
        answer,
        fit,
        records: Vec::new(),
    };
    let laws = &answer.laws;
    for law in ["B1", "B2", "B3", "B4"] {
        let Some(value) = laws.get(law) else {
            continue;
        };
        let cuts = proportion(law, value);
        for target in value["targets"].as_array().into_iter().flatten() {
            let thing = target["thing"].as_u64().unwrap_or_default();
            let members = m.doc.members(thing);
            let Some(b) = m.doc.box_of(&members) else {
                m.unmeasurable(law, thing, "no numeric place");
                continue;
            };
            let c = center(b);
            let (k, place) = match at_target(target["at"].as_str().unwrap_or_default(), cuts) {
                At::Point([x, y]) => {
                    let (dx, dy) = (x - c[0], y - c[1]);
                    let deviation = m.doc.length(dx, dy);
                    m.settle(
                        law,
                        thing,
                        Some(deviation),
                        "place",
                        OK_PLACE,
                        deviation > FAR_MOVE,
                        |doc| translate_thing(doc, thing, dx, dy),
                    );
                    continue;
                }
                At::Vertical(x) => (0, x),
                At::Horizontal(y) => (1, y),
            };
            let full = target["span"].as_str() == Some("full");
            let parts = m.doc.parts_of(thing);
            let first = m.doc.numbers(members[0]).clone();
            if members.len() == 1 && first.kind == PlaceKind::Segment && !first.row {
                // One line lies along the law's line: full from 0.118 to 0.882,
                // current keeping its length.
                let goal = along(&first.values, k, place, full);
                let deviation = deviation_of(&first.values, &goal);
                let index = members[0];
                m.settle(
                    law,
                    thing,
                    Some(deviation),
                    "place",
                    OK_PLACE,
                    deviation > FAR_MOVE,
                    |doc| {
                        let line =
                            rewritten(&doc.lines[index], doc.numbers(index), Some(&goal), None);
                        if doc.rewrite(vec![(index, line)]) {
                            Fit::Done
                        } else {
                            Fit::Refused
                        }
                    },
                );
                continue;
            }
            if matches!(m.kind(thing), "line" | "row") && parts.len() >= 2 {
                if let Some(goals) = stacked(m.doc, &members, k, place, c, full) {
                    // A bundle of lines stacked across the law's line: its
                    // center goes onto the line, each line kept in the bundle.
                    let deviation = goals
                        .iter()
                        .map(|(index, goal)| deviation_of(&m.doc.numbers(*index).values, goal))
                        .fold(0.0, f64::max);
                    m.settle(
                        law,
                        thing,
                        Some(deviation),
                        "place",
                        OK_PLACE,
                        deviation > FAR_MOVE,
                        |doc| {
                            let new = goals
                                .iter()
                                .map(|(index, goal)| {
                                    (
                                        *index,
                                        rewritten(
                                            &doc.lines[*index],
                                            doc.numbers(*index),
                                            Some(goal),
                                            None,
                                        ),
                                    )
                                })
                                .collect();
                            if doc.rewrite(new) {
                                Fit::Done
                            } else {
                                Fit::Refused
                            }
                        },
                    );
                    continue;
                }
                // Each part goes onto the line; with a full span the parts
                // spread from 0.118 to 0.882 in order.
                let centers: Vec<[f64; 2]> = parts
                    .iter()
                    .map(|part| center(m.doc.box_of(part).unwrap_or(b)))
                    .collect();
                let mut order: Vec<usize> = (0..parts.len()).collect();
                order.sort_by(|a, z| centers[*a][1 - k].total_cmp(&centers[*z][1 - k]));
                let mut moves = Vec::new();
                #[allow(clippy::cast_precision_loss)]
                let steps = (parts.len() - 1) as f64;
                for (rank, i) in order.iter().enumerate() {
                    let mut goal = centers[*i];
                    goal[k] = place;
                    if full {
                        #[allow(clippy::cast_precision_loss)]
                        let rank = rank as f64;
                        goal[1 - k] = MARGIN + rank * (1.0 - 2.0 * MARGIN) / steps;
                    }
                    moves.push((
                        parts[*i].clone(),
                        goal[0] - centers[*i][0],
                        goal[1] - centers[*i][1],
                    ));
                }
                let deviation = moves
                    .iter()
                    .map(|(_, dx, dy)| m.doc.length(*dx, *dy))
                    .fold(0.0, f64::max);
                m.settle(
                    law,
                    thing,
                    Some(deviation),
                    "place",
                    OK_PLACE,
                    deviation > FAR_MOVE,
                    |doc| move_parts(doc, &moves),
                );
                continue;
            }
            let mut delta = [0.0, 0.0];
            delta[k] = place - c[k];
            let deviation = m.doc.length(delta[0], delta[1]);
            m.settle(
                law,
                thing,
                Some(deviation),
                "place",
                OK_PLACE,
                deviation > FAR_MOVE,
                |doc| translate_thing(doc, thing, delta[0], delta[1]),
            );
        }
    }

    if let Some(value) = laws.get("B5") {
        for target in value["targets"].as_array().into_iter().flatten() {
            let thing = target["thing"].as_u64().unwrap_or_default();
            let parts = m.doc.parts_of(thing);
            if parts.is_empty() {
                m.unmeasurable("B5", thing, "no numeric place");
                continue;
            }
            let path = target["path"].as_str().unwrap_or_default().to_owned();
            let project = |[x, y]: [f64; 2]| -> [f64; 2] {
                match path.as_str() {
                    "diagonal_down" => {
                        let s = f64::midpoint(x, y);
                        [s, s]
                    }
                    "diagonal_up" => {
                        let s = (x - y + 1.0) / 2.0;
                        [s, 1.0 - s]
                    }
                    "center_vertical" => [0.5, y],
                    _ => [x, 0.5],
                }
            };
            let moves: Vec<(Vec<usize>, f64, f64)> = parts
                .iter()
                .filter_map(|part| {
                    let c = center(m.doc.box_of(part)?);
                    let q = project(c);
                    Some((part.clone(), q[0] - c[0], q[1] - c[1]))
                })
                .collect();
            let deviation = moves
                .iter()
                .map(|(_, dx, dy)| m.doc.length(*dx, *dy))
                .fold(0.0, f64::max);
            m.settle(
                "B5",
                thing,
                Some(deviation),
                "place",
                OK_PLACE,
                deviation > FAR_MOVE,
                |doc| move_parts(doc, &moves),
            );
        }
    }

    if let Some(value) = laws.get("B8") {
        for target in value["targets"].as_array().into_iter().flatten() {
            let thing = target["thing"].as_u64().unwrap_or_default();
            let parts = m.doc.parts_of(thing);
            if parts.is_empty() {
                m.unmeasurable("B8", thing, "no numeric place");
                continue;
            }
            let axis = target["axis"].as_str().unwrap_or_default();
            let moves: Vec<(Vec<usize>, f64, f64)> =
                if parts.len() == 2 && matches!(axis, "vertical" | "horizontal") {
                    let cs: Vec<[f64; 2]> = parts
                        .iter()
                        .filter_map(|part| m.doc.box_of(part).map(center))
                        .collect();
                    let k = usize::from(axis != "vertical");
                    let mut order = [0, 1];
                    order.sort_by(|a, z| cs[*a][k].total_cmp(&cs[*z][k]));
                    let mean = f64::midpoint(cs[0][1 - k], cs[1][1 - k]);
                    order
                        .iter()
                        .enumerate()
                        .map(|(rank, i)| {
                            let mut goal = [0.0, 0.0];
                            goal[k] = if rank == 0 { GOLDEN.0 } else { GOLDEN.1 };
                            goal[1 - k] = mean;
                            (parts[*i].clone(), goal[0] - cs[*i][0], goal[1] - cs[*i][1])
                        })
                        .collect()
                } else {
                    let members = m.doc.members(thing);
                    let c = center(m.doc.box_of(&members).unwrap_or([0.5; 4]));
                    let tx = if matches!(axis, "vertical" | "both") {
                        0.5
                    } else {
                        c[0]
                    };
                    let ty = if matches!(axis, "horizontal" | "both") {
                        0.5
                    } else {
                        c[1]
                    };
                    vec![(members, tx - c[0], ty - c[1])]
                };
            let deviation = moves
                .iter()
                .map(|(_, dx, dy)| m.doc.length(*dx, *dy))
                .fold(0.0, f64::max);
            m.settle(
                "B8",
                thing,
                Some(deviation),
                "place",
                OK_PLACE,
                deviation > FAR_MOVE,
                |doc| move_parts(doc, &moves),
            );
        }
    }

    // (thing, base) to (law, ratio): B6's secondary 0.618 and accent 0.382 of
    // its main; B7's thing 0.382 of its partner unless B6 sizes the pair.
    let mut ratio_of: Vec<Sizing> = Vec::new();
    if let Some(value) = laws.get("B6") {
        let main = value["main"].as_u64().unwrap_or_default();
        for (key, ratio) in [("secondary", GOLDEN.1), ("accent", GOLDEN.0)] {
            for thing in value[key]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(Value::as_u64)
            {
                if !ratio_of.iter().any(|(pair, _)| *pair == (thing, main)) {
                    ratio_of.push(((thing, main), ("B6", ratio)));
                }
            }
        }
    }
    if let Some(value) = laws.get("B7") {
        let thing = value["thing"].as_u64().unwrap_or_default();
        let against = value["against"].as_u64().unwrap_or_default();
        let partner = m.doc.members(against);
        let members = m.doc.members(thing);
        match (m.doc.box_of(&partner), m.doc.box_of(&members)) {
            (Some(pb), Some(tb)) => {
                let ca = center(pb);
                let d = [ca[0] - 0.5, ca[1] - 0.5];
                if d[0].hypot(d[1]) < 0.05 {
                    m.unmeasurable("B7", thing, "the partner is at the center");
                } else {
                    let goal = [
                        (0.5 - 2.618 * d[0]).clamp(EDGE, 1.0 - EDGE),
                        (0.5 - 2.618 * d[1]).clamp(EDGE, 1.0 - EDGE),
                    ];
                    let cl = center(tb);
                    let (dx, dy) = (goal[0] - cl[0], goal[1] - cl[1]);
                    let deviation = m.doc.length(dx, dy);
                    m.settle(
                        "B7",
                        thing,
                        Some(deviation),
                        "place",
                        OK_PLACE,
                        deviation > FAR_MOVE,
                        |doc| translate_thing(doc, thing, dx, dy),
                    );
                    if !ratio_of.iter().any(|(pair, _)| *pair == (thing, against)) {
                        ratio_of.push(((thing, against), ("B7", GOLDEN.0)));
                    }
                }
            }
            _ => m.unmeasurable("B7", thing, "no numeric place"),
        }
    }
    for ((thing, base), (law, ratio)) in ratio_of {
        let members = m.doc.members(thing);
        let based = m.doc.members(base);
        let (Some(tb), Some(bb)) = (m.doc.box_of(&members), m.doc.box_of(&based)) else {
            m.record(
                law,
                thing,
                None,
                "ratio",
                MeasureState::Unmeasurable,
                "no numeric place",
            );
            continue;
        };
        let (size, base_size) = (extent(tb, m.doc.units), extent(bb, m.doc.units));
        if size <= 0.0 || base_size <= 0.0 {
            m.record(
                law,
                thing,
                None,
                "ratio",
                MeasureState::Unmeasurable,
                "no size",
            );
            continue;
        }
        let factor = ratio * base_size / size;
        let deviation = (size / (ratio * base_size) - 1.0).abs();
        let far = !(1.0 / FAR_SCALE..=FAR_SCALE).contains(&factor);
        let about = center(tb);
        m.settle(law, thing, Some(deviation), "ratio", OK_RATIO, far, |doc| {
            if doc.move_by(&members, 0.0, 0.0, factor, about) {
                Fit::Done
            } else {
                Fit::Refused
            }
        });
    }

    for law in ["B9", "B10", "B12"] {
        let Some(value) = laws.get(law) else {
            continue;
        };
        for target in value["targets"].as_array().into_iter().flatten() {
            measure_row(&mut m, law, target);
        }
    }

    if let Some(value) = laws.get("C1") {
        // The dense place is the tool's: its distance from the spot is
        // recorded, never fitted.
        let [x, y] = spot(value["spot"].as_str().unwrap_or_default());
        for target in value["targets"].as_array().into_iter().flatten() {
            let thing = target["thing"].as_u64().unwrap_or_default();
            let members = m.doc.members(thing);
            let Some(b) = m.doc.box_of(&members) else {
                m.unmeasurable("C1", thing, "no numeric place");
                continue;
            };
            let c = center(b);
            let deviation = m.doc.length(x - c[0], y - c[1]);
            let state = if deviation <= OK_PLACE {
                MeasureState::Ok
            } else {
                MeasureState::Off
            };
            m.record(
                "C1",
                thing,
                Some(deviation),
                "place",
                state,
                "built by the tool",
            );
        }
    }
    for law in ["B15", "B21", "C2", "C3", "C4", "C5", "C6"] {
        if let Some(value) = laws.get(law) {
            let detail = if CARDS.contains(&law) {
                "built by the tool"
            } else {
                "drawn by the writer"
            };
            for (thing, _) in law_things(law, value) {
                m.record(law, thing, None, "", MeasureState::NotMeasured, detail);
            }
        }
    }
    m.records
}

/// A line's numbers laid along a law's line through `place` on axis `k`:
/// with `full`, from 0.118 to 0.882 the way it ran; else its length kept.
fn along(values: &[f64], k: usize, place: f64, full: bool) -> Vec<f64> {
    let (mut a, mut z) = if k == 0 {
        (values[1], values[3])
    } else {
        (values[0], values[2])
    };
    if full {
        (a, z) = if a <= z {
            (MARGIN, 1.0 - MARGIN)
        } else {
            (1.0 - MARGIN, MARGIN)
        };
    }
    if k == 0 {
        vec![place, a, place, z]
    } else {
        vec![a, place, z, place]
    }
}

fn deviation_of(values: &[f64], goal: &[f64]) -> f64 {
    values
        .iter()
        .zip(goal)
        .map(|(value, goal)| (value - goal).abs())
        .fold(0.0, f64::max)
}

/// The new numbers of a bundle of lines stacked across a law's line (each a
/// line, not a row, running along the law's line, the lines spread more across
/// it than along it): every line moved across by what brings the bundle's
/// center onto the line, and with `full` spanning 0.118 to 0.882 the way it
/// ran. `None` when the thing is not such a bundle.
fn stacked(
    doc: &ThingDocument,
    members: &[usize],
    k: usize,
    place: f64,
    c: [f64; 2],
    full: bool,
) -> Option<Vec<(usize, Vec<f64>)>> {
    let lines: Vec<&Numbers> = members.iter().map(|index| doc.numbers(*index)).collect();
    let runs_along = |numbers: &Numbers| {
        let v = &numbers.values;
        let (dx, dy) = ((v[2] - v[0]).abs(), (v[3] - v[1]).abs());
        if k == 0 { dy >= dx } else { dx >= dy }
    };
    if lines.len() < 2
        || !lines.iter().all(|numbers| {
            numbers.kind == PlaceKind::Segment && !numbers.row && runs_along(numbers)
        })
    {
        return None;
    }
    let centers: Vec<[f64; 2]> = lines
        .iter()
        .map(|numbers| center(sentence_box(numbers, doc.units)))
        .collect();
    let spread = |axis: usize| {
        let values = centers.iter().map(|point| point[axis]);
        values.clone().fold(f64::MIN, f64::max) - values.fold(f64::MAX, f64::min)
    };
    if spread(k) <= spread(1 - k) {
        return None;
    }
    let shift = place - c[k];
    Some(
        members
            .iter()
            .zip(&lines)
            .map(|(index, numbers)| {
                let mut goal = numbers.values.clone();
                goal[k] += shift;
                goal[k + 2] += shift;
                if full {
                    let (a, z) = (goal[1 - k], goal[3 - k]);
                    (goal[1 - k], goal[3 - k]) = if a <= z {
                        (MARGIN, 1.0 - MARGIN)
                    } else {
                        (1.0 - MARGIN, MARGIN)
                    };
                }
                (*index, goal)
            })
            .collect(),
    )
}

/// B9, B10 and B12 on one thing: its parts' centers along the row's long
/// side, at equal spacing, in progression or in beat groups.
#[allow(clippy::too_many_lines)]
fn measure_row(m: &mut Measurer<'_>, law: &str, target: &Value) {
    let thing = target["thing"].as_u64().unwrap_or_default();
    let parts = m.doc.parts_of(thing);
    if let [part] = parts.as_slice()
        && let [index] = part.as_slice()
    {
        let numbers = m.doc.numbers(*index);
        if law == "B9" && (numbers.row || numbers.kind == PlaceKind::Range) {
            m.record(
                law,
                thing,
                Some(0.0),
                "place",
                MeasureState::Ok,
                "one sentence the compiler spaces",
            );
            return;
        }
    }
    if law == "B9" && target["form"].as_str() == Some("grid") {
        m.unmeasurable(law, thing, "a grid of sentences");
        return;
    }
    let spacing = target["change"].as_str() == Some("spacing");
    let need = match law {
        "B9" => 3,
        "B10" if spacing => 3,
        "B12" => {
            target["group"]
                .as_str()
                .and_then(|group| group.parse::<usize>().ok())
                .unwrap_or(2)
                + 1
        }
        _ => 2,
    };
    if parts.len() < need {
        m.unmeasurable(law, thing, &format!("{} parts", parts.len()));
        return;
    }
    let cs: Vec<[f64; 2]> = parts
        .iter()
        .map(|part| center(m.doc.box_of(part).unwrap_or([0.5; 4])))
        .collect();
    let mut order: Vec<usize> = (0..parts.len()).collect();
    let k = if law == "B10" {
        let toward = target["toward"].as_str().unwrap_or_default();
        let k = usize::from(!matches!(toward, "left" | "right"));
        order.sort_by(|a, z| cs[*a][k].total_cmp(&cs[*z][k]));
        if matches!(toward, "left" | "top") {
            order.reverse();
        }
        k
    } else {
        let spread = |axis: usize| {
            let values = cs.iter().map(|point| point[axis]);
            values.clone().fold(f64::MIN, f64::max) - values.fold(f64::MAX, f64::min)
        };
        let k = usize::from(spread(0) < spread(1));
        order.sort_by(|a, z| cs[*a][k].total_cmp(&cs[*z][k]));
        k
    };
    let n = order.len();
    let positions: Vec<f64> = order.iter().map(|i| cs[*i][k]).collect();
    let (first, last) = (positions[0], positions[n - 1]);
    #[allow(clippy::cast_precision_loss)]
    let count = n as f64;
    if law == "B10" && !spacing {
        let sizes: Vec<f64> = order
            .iter()
            .map(|i| extent(m.doc.box_of(&parts[*i]).unwrap_or([0.0; 4]), m.doc.units))
            .collect();
        if sizes[0] <= 0.0 {
            m.record(
                law,
                thing,
                None,
                "ratio",
                MeasureState::Unmeasurable,
                "no size",
            );
            return;
        }
        let ratio: f64 = target["ratio"]
            .as_str()
            .and_then(|ratio| ratio.parse().ok())
            .unwrap_or(GOLDEN.1);
        let q = ratio.powf(1.0 / (count - 1.0));
        #[allow(clippy::cast_possible_truncation, clippy::cast_possible_wrap)]
        let goals: Vec<f64> = (0..n).map(|i| sizes[0] * q.powi(i as i32)).collect();
        let deviation = sizes
            .iter()
            .zip(&goals)
            .filter(|(size, _)| **size > 0.0)
            .map(|(size, goal)| (size / goal - 1.0).abs())
            .fold(0.0, f64::max);
        let factors: Vec<f64> = sizes
            .iter()
            .zip(&goals)
            .map(|(size, goal)| if *size > 0.0 { goal / size } else { 1.0 })
            .collect();
        let far = factors
            .iter()
            .any(|factor| !(1.0 / FAR_SCALE..=FAR_SCALE).contains(factor));
        let scaled: Vec<(Vec<usize>, f64)> = order
            .iter()
            .zip(&factors)
            .map(|(i, factor)| (parts[*i].clone(), *factor))
            .collect();
        m.settle(law, thing, Some(deviation), "ratio", OK_RATIO, far, |doc| {
            scale_parts(doc, &scaled)
        });
        return;
    }
    let goals: Vec<f64> = match law {
        "B9" => (0..n)
            .map(|i| {
                #[allow(clippy::cast_precision_loss)]
                let i = i as f64;
                first + (last - first) * i / (count - 1.0)
            })
            .collect(),
        "B10" => {
            let ratio: f64 = target["ratio"]
                .as_str()
                .and_then(|ratio| ratio.parse().ok())
                .unwrap_or(GOLDEN.1);
            let q = ratio.powf(1.0 / (count - 2.0));
            #[allow(clippy::cast_possible_truncation, clippy::cast_possible_wrap)]
            let gaps: Vec<f64> = (0..n - 1).map(|i| q.powi(i as i32)).collect();
            let total: f64 = gaps.iter().sum();
            let mut at = first;
            let mut goals = vec![first];
            for gap in gaps {
                at += (last - first) * gap / total;
                goals.push(at);
            }
            goals
        }
        _ => {
            let size = target["group"]
                .as_str()
                .and_then(|group| group.parse::<usize>().ok())
                .unwrap_or(2)
                .max(1);
            let rests = n.div_ceil(size) - 1;
            #[allow(clippy::cast_precision_loss)]
            let step = (last - first) / ((n - 1 + rests) as f64);
            #[allow(clippy::cast_precision_loss)]
            (0..n)
                .map(|i| first + step * ((i + i / size) as f64))
                .collect()
        }
    };
    let moves: Vec<(Vec<usize>, f64, f64)> = order
        .iter()
        .zip(&goals)
        .map(|(i, goal)| {
            let mut delta = [0.0, 0.0];
            delta[k] = goal - cs[*i][k];
            (parts[*i].clone(), delta[0], delta[1])
        })
        .collect();
    let deviation = moves
        .iter()
        .map(|(_, dx, dy)| m.doc.length(*dx, *dy))
        .fold(0.0, f64::max);
    m.settle(
        law,
        thing,
        Some(deviation),
        "place",
        OK_PLACE,
        deviation > FAR_MOVE,
        |doc| move_parts(doc, &moves),
    );
    if law == "B12" && target["strong"].as_str() == Some("first") {
        let size = target["group"]
            .as_str()
            .and_then(|group| group.parse::<usize>().ok())
            .unwrap_or(2)
            .max(1);
        let sizes: Vec<f64> = order
            .iter()
            .map(|i| extent(m.doc.box_of(&parts[*i]).unwrap_or([0.0; 4]), m.doc.units))
            .collect();
        let mut factors = Vec::new();
        let mut worst: f64 = 0.0;
        for rank in 0..n {
            let lead = sizes[rank - rank % size];
            let goal = if rank % size == 0 {
                lead
            } else {
                GOLDEN.1 * lead
            };
            factors.push(if sizes[rank] > 0.0 {
                goal / sizes[rank]
            } else {
                1.0
            });
            if sizes[rank] > 0.0 && goal > 0.0 {
                worst = worst.max((sizes[rank] / goal - 1.0).abs());
            }
        }
        let far = factors
            .iter()
            .any(|factor| !(1.0 / FAR_SCALE..=FAR_SCALE).contains(factor));
        let scaled: Vec<(Vec<usize>, f64)> = order
            .iter()
            .zip(&factors)
            .map(|(i, factor)| (parts[*i].clone(), *factor))
            .collect();
        m.settle("B12", thing, Some(worst), "ratio", OK_RATIO, far, |doc| {
            scale_parts(doc, &scaled)
        });
    }
}

fn scale_parts(doc: &mut ThingDocument, scaled: &[(Vec<usize>, f64)]) -> Fit {
    for (part, factor) in scaled {
        let Some(b) = doc.box_of(part) else {
            return Fit::Refused;
        };
        if !doc.move_by(part, 0.0, 0.0, *factor, center(b)) {
            return Fit::Refused;
        }
    }
    Fit::Done
}

/// The things the writing request is asked again about: each far measure
/// with its target's words, each thing of the composition no sentence draws,
/// and each card's thing not written in one sentence (C1's in one or two).
#[must_use]
pub fn thing_problems(
    doc: &ThingDocument,
    records: &[LawMeasure],
    answer: &CompositionAnswer,
    language: ResolvedInstructionLanguage,
) -> Vec<ThingProblem> {
    let ja = language == ResolvedInstructionLanguage::Ja;
    let words = composition_targets(answer, language);
    let name = |thing: u64| -> String {
        let what = answer.thing(thing).map_or("", |item| item.what.as_str());
        if ja {
            format!("物{thing}（{what}）")
        } else {
            format!("thing {thing} ({what})")
        }
    };
    let mut out = Vec::new();
    for record in records
        .iter()
        .filter(|record| record.state == MeasureState::Far)
    {
        let named = name(record.thing);
        let target = words
            .iter()
            .find(|line| line.contains(&named) && names_law(line, &record.law))
            .cloned()
            .unwrap_or_default();
        let deviation = record.deviation.unwrap_or_default();
        out.push(ThingProblem {
            thing: record.thing,
            law: record.law.clone(),
            measured: match (ja, record.unit.as_str()) {
                (true, "place") => format!("ずれ {deviation}（短辺の比）"),
                (true, _) => format!("大きさの比のずれ {deviation}"),
                (false, "place") => format!("off by {deviation} of the short side"),
                (false, _) => format!("size ratio off by {deviation}"),
            },
            target,
        });
    }
    for thing in &answer.things {
        if doc.sentences_of(thing.thing).is_empty() {
            out.push(ThingProblem {
                thing: thing.thing,
                law: String::new(),
                measured: if ja { "文が無い" } else { "no sentence" }.to_owned(),
                target: if ja {
                    format!("{}を描く。", name(thing.thing))
                } else {
                    format!("Draw {}.", name(thing.thing))
                },
            });
        }
    }
    for (law, value) in answer.chosen() {
        if !CARDS.contains(&law) {
            continue;
        }
        let most = if law == "C1" { 2 } else { 1 };
        for (thing, takes) in law_things(law, value) {
            let written = doc.sentences_of(thing).len();
            if takes != Takes::Card || written == 0 || written <= most {
                continue;
            }
            out.push(ThingProblem {
                thing,
                law: law.to_owned(),
                measured: if ja {
                    format!("{written} 文")
                } else {
                    format!("{written} sentences")
                },
                target: match (ja, most) {
                    (true, 1) => format!("{}を 1 文で書く。", name(thing)),
                    (true, _) => format!("{}を 1〜2 文で書く。", name(thing)),
                    (false, 1) => format!("Write {} in one sentence.", name(thing)),
                    (false, _) => format!("Write {} in one or two sentences.", name(thing)),
                },
            });
        }
    }
    out
}

/// Whether a target's words name the law (`B1` and not `B10`).
fn names_law(line: &str, law: &str) -> bool {
    line.match_indices(law).any(|(at, _)| {
        let before = line[..at].chars().next_back();
        let after = line[at + law.len()..].chars().next();
        !before.is_some_and(char::is_alphanumeric) && !after.is_some_and(char::is_alphanumeric)
    })
}

// --- the cards ---------------------------------------------------------------------------------

/// What became of one card: the law, its things, the sentences it was built
/// from, and whether the tool built it (and why not).
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CardRecord {
    pub law: String,
    pub things: Vec<u64>,
    pub motif: Vec<ThingSentence>,
    pub built: bool,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub reason: String,
}

/// What a card is built on: the work's Score as the run compiles it, its
/// palette and its paper.
pub struct CardGround<'a> {
    pub palette: &'a ResolvedPaletteDto,
    pub canvas_format_id: &'a str,
}

/// A sentence's instruction read as a plan layer without its numbers (a
/// numeric place, two points, a turn, sizes and a colour cycle): the words a
/// layer the laws stage prints again keeps.
fn layer_without_numbers(instruction: &SemanticInstruction) -> Option<WorkPlanLayer> {
    let mut cleared = SemanticInstruction {
        relation: None,
        sequence: None,
        ..instruction.clone()
    };
    let entity = &mut cleared.entity;
    entity.numeric_position = None;
    entity.numeric_segment = None;
    entity.numeric_angle = None;
    entity.explicit_geometry = None;
    entity.additional_explicit_geometries.clear();
    entity.additional_width_extents.clear();
    plan_layer(&cleared)
}

/// The composed plan the laws stage reads a work's DDL as: one layer for each
/// instruction, read without its numbers (a layer that does not read takes
/// another's words: the laws print only the layers they change), and the
/// sentence each instruction is written in. `None` when an instruction is not
/// one sentence's.
fn plan_of(
    source: &str,
    language: ResolvedInstructionLanguage,
) -> Option<(ComposedPlan, Vec<usize>, Vec<bool>)> {
    let document = NormalizedDdlDocument::new(source, language, Vec::new()).ok()?;
    let compilation = compile_typed_ddl(document, &[], None, LIMITS);
    let ast = &compilation.semantic_document.as_ref()?.ast;
    let starts: Vec<usize> = std::iter::once(0)
        .chain(source.match_indices('\n').map(|(at, _)| at + 1))
        .collect();
    let line_of = |at: usize| starts.iter().rposition(|start| *start <= at);
    let mut lines = Vec::new();
    let mut read = Vec::new();
    let mut layers: Vec<Option<WorkPlanLayer>> = Vec::new();
    for instruction in &ast.instructions {
        lines.push(line_of(instruction.entity.head.source().span.start_byte)?);
        let layer = layer_without_numbers(instruction);
        read.push(layer.is_some());
        layers.push(layer);
    }
    let any = layers.iter().flatten().next()?.clone();
    let layers: Vec<WorkPlanLayer> = layers
        .into_iter()
        .map(|layer| layer.unwrap_or_else(|| any.clone()))
        .collect();
    let count = layers.len();
    Some((
        ComposedPlan {
            plan: WorkPlan {
                ground: None,
                background: None,
                plugins: Vec::new(),
                layers,
            },
            ranges: vec![None; count],
            joints: vec![None; count],
        },
        lines,
        read,
    ))
}

/// A card's value with its things named as the layers of their sentences: one
/// layer a thing, or for C1 each sentence of a thing, and the layers whose
/// count stays (each sentence of a C1 thing written in two keeps its own
/// count, `counts`). `None` when a thing's sentences are not one (C1: one or
/// two) or a sentence's layer did not read.
fn card_value(
    law: &str,
    value: &Value,
    layers_of: &dyn Fn(u64) -> Vec<usize>,
    read: &[bool],
    counts: &BTreeMap<usize, u64>,
) -> Option<(Value, Vec<usize>)> {
    let layer = |thing: &Value| -> Option<usize> {
        match layers_of(thing.as_u64()?).as_slice() {
            [layer] if read[*layer] => Some(*layer),
            _ => None,
        }
    };
    let mut out: Map<String, Value> = value.as_object()?.clone();
    let mut kept = Vec::new();
    match law {
        "C1" => {
            let mut targets = Vec::new();
            for target in value["targets"].as_array()? {
                let layers = layers_of(target["thing"].as_u64()?);
                match layers.as_slice() {
                    [one] if read[*one] => {
                        targets.push(json!({"layer": one, "count": target["count"]}))
                    }
                    [_, _] if layers.iter().all(|layer| read[*layer]) => {
                        for layer in &layers {
                            targets.push(json!({"layer": layer, "count": counts.get(layer)?}));
                            kept.push(*layer);
                        }
                    }
                    _ => return None,
                }
            }
            out.insert("targets".to_owned(), Value::Array(targets));
        }
        "C3" => {
            let voices: Option<Vec<Value>> = value["voices"]
                .as_array()?
                .iter()
                .map(|thing| layer(thing).map(|layer| json!(layer)))
                .collect();
            out.insert("voices".to_owned(), Value::Array(voices?));
        }
        _ => {
            out.remove("thing");
            out.insert("layer".to_owned(), json!(layer(&value["thing"])?));
        }
    }
    Some((Value::Object(out), kept))
}

/// Build each card of a composed work as the laws stage builds it, one card
/// after another on the DDL the one before left: the DDL is read as the laws
/// stage's composed plan, the card's value names its things' layers, and the
/// layers the card changed are printed in numbers in place of the things'
/// sentences. `head` is the paper's ratio sentence; `compile` gives the Score
/// of a source as the run compiles it. A card the tool cannot build leaves its
/// sentences as written, with the reason.
pub fn build_cards(
    sentences: &[ThingSentence],
    head: &str,
    answer: &CompositionAnswer,
    ground: &CardGround<'_>,
    language: ResolvedInstructionLanguage,
    compile: &dyn Fn(&str) -> Option<Score>,
) -> (Vec<ThingSentence>, Vec<CardRecord>) {
    let mut sentences = sentences.to_vec();
    let mut records = Vec::new();
    for (law, value) in answer.chosen() {
        if !CARDS.contains(&law) {
            continue;
        }
        let things: Vec<u64> = law_things(law, value)
            .into_iter()
            .filter(|(_, takes)| *takes == Takes::Card)
            .map(|(thing, _)| thing)
            .collect();
        let motif: Vec<ThingSentence> = sentences
            .iter()
            .filter(|item| things.contains(&item.thing))
            .cloned()
            .collect();
        match build_card(&sentences, head, law, value, ground, language, compile) {
            Ok(built) => {
                sentences = built;
                records.push(CardRecord {
                    law: law.to_owned(),
                    things,
                    motif,
                    built: true,
                    reason: String::new(),
                });
            }
            Err(reason) => records.push(CardRecord {
                law: law.to_owned(),
                things,
                motif,
                built: false,
                reason,
            }),
        }
    }
    (sentences, records)
}

fn build_card(
    sentences: &[ThingSentence],
    head: &str,
    law: &'static str,
    value: &Value,
    ground: &CardGround<'_>,
    language: ResolvedInstructionLanguage,
    compile: &dyn Fn(&str) -> Option<Score>,
) -> Result<Vec<ThingSentence>, String> {
    let source = std::iter::once(head.to_owned())
        .chain(sentences.iter().map(|item| item.text.clone()))
        .collect::<Vec<_>>()
        .join("\n");
    let (composed, lines, read) = plan_of(&source, language).ok_or("unreadable")?;
    // The source's line of each layer, as an index of `sentences`.
    let sentence_of: Vec<Option<usize>> = lines.iter().map(|line| line.checked_sub(1)).collect();
    let layers_of = |thing: u64| -> Vec<usize> {
        sentence_of
            .iter()
            .enumerate()
            .filter(|(_, sentence)| sentence.is_some_and(|index| sentences[index].thing == thing))
            .map(|(layer, _)| layer)
            .collect()
    };
    let score = compile(&source).ok_or("not_compiled")?;
    let mut counts: BTreeMap<usize, u64> = BTreeMap::new();
    for (layer, positions) in layers(&score) {
        let marks = positions
            .iter()
            .map(|position| u64::from(count_of(&score.instructions[*position])))
            .sum();
        counts.insert(layer, marks);
    }
    let (value, kept) =
        card_value(law, value, &layers_of, &read, &counts).ok_or("not_one_sentence")?;
    let context = LawsContext::new(score, &composed, ground.palette, ground.canvas_format_id)
        .ok_or("laws_context")?;
    let kept: Vec<Value> = kept
        .into_iter()
        .map(|layer| json!({"layer": layer, "words": ""}))
        .collect();
    let answer = json!({
        "main_law": law,
        "description_counts": kept,
        "laws": {law: value},
        "reason": "",
    });
    let chosen =
        apply_cards(&answer, &context, &composed).map_err(|refusal| refusal.code.to_owned())?;
    let print = &chosen.print;
    // The printed layers of each changed composed layer, in print order.
    let mut printed: BTreeMap<usize, Vec<String>> = BTreeMap::new();
    for (at, composed_layer) in print.composed.iter().enumerate() {
        if !print.changed.contains(composed_layer) {
            continue;
        }
        let text = print_work_plan_with_numbers(
            &WorkPlan {
                ground: None,
                background: None,
                plugins: Vec::new(),
                layers: vec![print.plan.layers[at].clone()],
            },
            language,
            &[],
            &[print.ranges[at].clone()],
            &[None],
            &[print.numeric[at].clone()],
        );
        printed.entry(*composed_layer).or_default().push(text);
    }
    if printed.is_empty() {
        return Err("unchanged".to_owned());
    }
    let mut out = Vec::new();
    for (index, item) in sentences.iter().enumerate() {
        let layer = sentence_of
            .iter()
            .position(|sentence| *sentence == Some(index));
        match layer.and_then(|layer| printed.get(&layer)) {
            Some(lines) => out.extend(lines.iter().map(|text| ThingSentence {
                thing: item.thing,
                text: text.clone(),
            })),
            None => out.push(item.clone()),
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sentences(items: &[(u64, &str)]) -> Vec<ThingSentence> {
        items
            .iter()
            .map(|(thing, text)| ThingSentence {
                thing: *thing,
                text: (*text).to_owned(),
            })
            .collect()
    }

    #[test]
    fn a_sentence_is_read_with_the_places_of_its_numbers() {
        let line = "画面の横0.0〜0.3、縦0.2〜1.0の範囲に、直径0.05の黒の点を30個散らす。";
        let numbers = parse(line, ResolvedInstructionLanguage::Ja).expect("a numeric range");
        assert_eq!(numbers.kind, PlaceKind::Range);
        assert_eq!(numbers.values, vec![0.0, 0.3, 0.2, 1.0]);
        let texts: Vec<&str> = numbers.spans.iter().map(|(a, z)| &line[*a..*z]).collect();
        assert_eq!(texts, vec!["0.0", "0.3", "0.2", "1.0"]);
        assert_eq!(numbers.sizes["diameter"].0, 0.05);
        let point = parse(
            "画面の横0.5、縦0.4の位置に、直径0.3の紫の塗りの円を1個置く。",
            ResolvedInstructionLanguage::Ja,
        )
        .expect("a numeric point");
        assert_eq!(point.kind, PlaceKind::Point);
        assert_eq!(point.values, vec![0.5, 0.4]);
        assert!(parse("背景を白で埋める。", ResolvedInstructionLanguage::Ja).is_none());
    }

    #[test]
    fn a_thing_a_little_off_is_fitted_and_a_far_one_is_named() {
        let answer: CompositionAnswer = serde_json::from_value(json!({
            "thesis": "x", "form": "one_corner",
            "things": [{"thing": 1, "what": "円", "role": "focal", "kind": "cluster", "quote": "円"},
                       {"thing": 2, "what": "月", "role": "accent", "kind": "cluster", "quote": "月"}],
            "main_law": "B1",
            "laws": {"B1": {"targets": [{"thing": 1, "at": "point_ul"}, {"thing": 2, "at": "point_lr"}]}},
            "reason": "r"
        }))
        .unwrap();
        let written = sentences(&[
            (0, "背景を白で埋める。"),
            (
                1,
                "画面の横0.42、縦0.40の位置に、直径0.1の黒の塗りの円を1個置く。",
            ),
            (
                2,
                "画面の横0.2、縦0.2の位置に、直径0.1の黄の塗りの円を1個置く。",
            ),
        ]);
        let mut doc = ThingDocument::new(&written, ResolvedInstructionLanguage::Ja, [1.0, 1.0]);
        let records = measure(&mut doc, &answer, true);
        assert_eq!(records[0].state, MeasureState::Fitted);
        assert_eq!(records[1].state, MeasureState::Far);
        let fitted = doc.sentences();
        assert_eq!(
            fitted[1].text,
            "画面の横0.381966、縦0.381966の位置に、直径0.1の黒の塗りの円を1個置く。"
        );
        assert_eq!(fitted[2].text, written[2].text);
        let problems = thing_problems(&doc, &records, &answer, ResolvedInstructionLanguage::Ja);
        assert_eq!(problems.len(), 1);
        assert_eq!(problems[0].thing, 2);
        assert!(problems[0].target.contains("物2（月）"), "{problems:?}");
    }

    #[test]
    fn a_bundle_of_lines_goes_onto_the_law_line_by_its_center() {
        let answer: CompositionAnswer = serde_json::from_value(json!({
            "thesis": "x", "form": "bands",
            "things": [{"thing": 1, "what": "潮の線", "role": "field", "kind": "line", "quote": "潮"}],
            "main_law": "B1",
            "laws": {"B1": {"targets": [{"thing": 1, "at": "line_bottom", "span": "current"}]}},
            "reason": "r"
        }))
        .unwrap();
        let written = sentences(&[
            (
                1,
                "画面の横0.2、縦0.58から横0.8、縦0.58まで、黒の細い線を引く。",
            ),
            (
                1,
                "画面の横0.2、縦0.62から横0.8、縦0.62まで、黒の細い線を引く。",
            ),
            (
                1,
                "画面の横0.2、縦0.66から横0.8、縦0.66まで、黒の細い線を引く。",
            ),
        ]);
        let mut doc = ThingDocument::new(&written, ResolvedInstructionLanguage::Ja, [1.0, 1.0]);
        let records = measure(&mut doc, &answer, true);
        assert_eq!(records[0].state, MeasureState::Ok, "{records:?}");
        let mut low = ThingDocument::new(
            &sentences(&[
                (
                    1,
                    "画面の横0.2、縦0.62から横0.8、縦0.62まで、黒の細い線を引く。",
                ),
                (
                    1,
                    "画面の横0.2、縦0.66から横0.8、縦0.66まで、黒の細い線を引く。",
                ),
                (
                    1,
                    "画面の横0.2、縦0.70から横0.8、縦0.70まで、黒の細い線を引く。",
                ),
            ]),
            ResolvedInstructionLanguage::Ja,
            [1.0, 1.0],
        );
        let records = measure(&mut low, &answer, true);
        assert_eq!(records[0].state, MeasureState::Fitted, "{records:?}");
        let ys: Vec<String> = low
            .sentences()
            .iter()
            .map(|item| item.text.clone())
            .collect();
        assert!(ys[1].contains("縦0.618034から"), "{ys:?}");
    }
}
