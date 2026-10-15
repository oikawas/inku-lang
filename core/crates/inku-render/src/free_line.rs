//! The free line (I-715): a line whose path between its two ends the
//! performance decides, as a cloudform's contour is decided.
//!
//! The path is a short phrase of readable parts, after Kandinsky's line as the
//! trace of forces: a straight run (one force), a circular arc (two forces at
//! once) and a free curve whose curvature ramps, joined smoothly or at a clear
//! corner (two forces in turn). The point tools build the phrase from straight
//! runs and arcs; the brushes and the broad tools also use free curves. The
//! phrase is built on a unit length, checked, and mapped onto the chord. Each
//! bend then turns to the side that leaves the most room from the paper's
//! edges and from the marks drawn before it that are not lines; lines do not
//! avoid each other.
//!
//! These are the rules of the stage A2 to A4 prototypes the author chose. The
//! draw labels keep the prototype's names, so a seed builds the very phrase the
//! prototype built for it.

use std::collections::BTreeSet;

use sha2::{Digest, Sha256};

use crate::stroke::unit;
use crate::types::{Point, Seed, Weight};

/// The seed of one free line mark, from the mark's performance seed, the
/// instruction and the mark, in a domain of its own.
#[must_use]
pub(crate) fn free_line_seed(
    performance_seed: Seed,
    instruction_index: usize,
    mark_index: usize,
) -> Seed {
    let digest = Sha256::digest(
        format!("free-line-v1:{performance_seed}:{instruction_index}:{mark_index}").as_bytes(),
    );
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

/// How a free line combines its parts, chosen by the tool.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Build {
    /// Straight runs and circular arcs.
    Geometric,
    /// Straight runs, circular arcs and free curves.
    Mixed,
}

/// The fine point tools draw geometric free lines; the brushes and the broad
/// tools mix free curves in (the author's rule, I-715 stage A2).
#[must_use]
pub(crate) const fn build_for_tool(weight: Weight) -> Build {
    match weight {
        Weight::Silverpoint
        | Weight::Pencil
        | Weight::Pen
        | Weight::Rotring
        | Weight::Computer
        | Weight::Burin
        | Weight::Drypoint => Build::Geometric,
        Weight::Crayon
        | Weight::Chalk
        | Weight::BrushThin
        | Weight::BrushThick
        | Weight::OilPaint => Build::Mixed,
    }
}

/// The phrase's draws: `free-line-proto-a2-{try}`, the stage A2 prototype's.
const PHRASE_LABEL: &str = "free-line-proto-a2";
/// The bends' sides: `free-line-proto-a3-signs-{candidate}`, stage A3's.
const SIDES_LABEL: &str = "free-line-proto-a3-signs";
const MAX_TRIES: i64 = 64;
/// The chord over the path length, at least.
const MIN_CHORD_RATIO: f64 = 0.25;
/// The net and the total turn, at most, in degrees.
const MAX_NET_TURN: f64 = 450.0;
const MAX_TOTAL_TURN: f64 = 900.0;
/// An arc's and a free curve's radius, at least, in path lengths.
const ARC_RADIUS: f64 = 0.02;
const FREE_RADIUS: f64 = 0.015;
/// The candidates for the sides of the bends: the coin's and 31 more.
const SIDE_CANDIDATES: usize = 32;
/// The points of a drawn path, at most. Only a chord much longer than the
/// paper reaches it.
const MAX_POINTS: usize = 512;

/// Deterministic uniform draws from one seed and label.
struct Draw {
    seed: Seed,
    label: String,
    index: i64,
}

impl Draw {
    fn new(seed: Seed, label: String) -> Self {
        Self {
            seed,
            label,
            index: 0,
        }
    }

    fn next(&mut self) -> f64 {
        let value = unit(self.seed, &self.label, self.index);
        self.index += 1;
        value
    }

    fn range(&mut self, low: f64, high: f64) -> f64 {
        low + (high - low) * self.next()
    }

    fn sign(&mut self) -> f64 {
        if self.next() < 0.5 { -1.0 } else { 1.0 }
    }

    /// Pick an index by weights that sum to one.
    fn pick(&mut self, weights: &[f64]) -> usize {
        let value = self.next();
        let mut total = 0.0;
        for (index, weight) in weights.iter().enumerate() {
            total += weight;
            if value < total {
                return index;
            }
        }
        weights.len() - 1
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Kind {
    Straight,
    Arc,
    /// A curve whose curvature ramps linearly, from zero when `rising`.
    Free {
        rising: bool,
    },
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Part {
    kind: Kind,
    length: f64,
    /// Signed total turn in radians; zero for a straight run.
    turn: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Joint {
    Smooth,
    /// A corner turning by this signed exterior angle in radians.
    Corner(f64),
}

#[derive(Clone, Debug, PartialEq)]
struct Phrase {
    parts: Vec<Part>,
    joints: Vec<Joint>,
}

impl Phrase {
    fn total_length(&self) -> f64 {
        self.parts.iter().map(|part| part.length).sum()
    }

    fn turns(&self) -> impl Iterator<Item = f64> + '_ {
        self.parts
            .iter()
            .map(|part| part.turn)
            .chain(self.joints.iter().map(|joint| match joint {
                Joint::Smooth => 0.0,
                Joint::Corner(turn) => *turn,
            }))
    }
}

/// Draw one phrase: three to seven parts, one of them dominant, the others
/// alternating long and short.
fn phrase_draw(draw: &mut Draw, build: Build) -> Option<Phrase> {
    let count = [3usize, 4, 5, 6, 7][draw.pick(&[0.20, 0.25, 0.25, 0.15, 0.15])];
    let kinds: Vec<Kind> = (0..count)
        .map(|_| match build {
            Build::Geometric => {
                if draw.next() < 0.5 {
                    Kind::Straight
                } else {
                    Kind::Arc
                }
            }
            Build::Mixed => match draw.pick(&[0.40, 0.25, 0.35]) {
                0 => Kind::Straight,
                1 => Kind::Arc,
                _ => Kind::Free {
                    rising: draw.next() < 0.6,
                },
            },
        })
        .collect();
    let joints: Vec<Joint> = (0..count - 1)
        .map(|index| {
            let both_straight =
                kinds[index] == Kind::Straight && kinds[index + 1] == Kind::Straight;
            if both_straight || draw.next() < 0.3 {
                let interior = match draw.pick(&[0.3, 0.3, 0.4]) {
                    0 => draw.range(40.0, 60.0),
                    1 => draw.range(85.0, 95.0),
                    _ => draw.range(110.0, 150.0),
                };
                Joint::Corner(draw.sign() * (180.0 - interior).to_radians())
            } else {
                Joint::Smooth
            }
        })
        .collect();
    let dominant = (draw.next() * count as f64).floor().min(count as f64 - 1.0) as usize;
    let share = match count {
        3 => draw.range(0.40, 0.60),
        4 => draw.range(0.35, 0.55),
        _ => draw.range(0.30, 0.45),
    };
    // Minor parts alternate long and short: each is 1.6 to 2.4 times the
    // previous minor part, or its inverse.
    let weights: Vec<f64> = {
        let mut value = draw.range(0.6, 1.0);
        let mut shorter = draw.next() < 0.5;
        (0..count)
            .map(|index| {
                if index == dominant {
                    return 0.0;
                }
                let current = value;
                let factor = draw.range(1.6, 2.4);
                value = if shorter {
                    value / factor
                } else {
                    value * factor
                };
                shorter = !shorter;
                current
            })
            .collect()
    };
    let minor_total: f64 = weights
        .iter()
        .enumerate()
        .filter(|(index, _)| *index != dominant)
        .map(|(_, weight)| weight)
        .sum();
    let lengths: Vec<f64> = (0..count)
        .map(|index| {
            if index == dominant {
                share
            } else {
                (1.0 - share) * weights[index] / minor_total
            }
        })
        .collect();
    for pair in lengths.windows(2) {
        let ratio = pair[0].max(pair[1]) / pair[0].min(pair[1]);
        if ratio < 1.5 {
            return None;
        }
    }
    let parts = kinds
        .iter()
        .zip(&lengths)
        .map(|(kind, length)| {
            let turn = match kind {
                Kind::Straight => 0.0,
                Kind::Arc => {
                    let magnitude = match draw.pick(&[0.4, 0.45, 0.15]) {
                        0 => draw.range(30.0, 60.0),
                        1 => draw.range(90.0, 150.0),
                        _ => draw.range(180.0, 240.0),
                    };
                    draw.sign() * magnitude.to_radians()
                }
                Kind::Free { .. } => draw.sign() * draw.range(40.0, 150.0).to_radians(),
            };
            Part {
                kind: *kind,
                length: *length,
                turn,
            }
        })
        .collect();
    Some(Phrase { parts, joints })
}

/// Heading change from the start of a part to `fraction` of it.
fn heading_within(part: &Part, fraction: f64) -> f64 {
    match part.kind {
        Kind::Straight => 0.0,
        Kind::Arc => part.turn * fraction,
        // Curvature ramps linearly; the integral of a ramp from zero is
        // quadratic, and the falling ramp is its mirror image.
        Kind::Free { rising: true } => part.turn * fraction * fraction,
        Kind::Free { rising: false } => part.turn * (2.0 * fraction - fraction * fraction),
    }
}

/// Trace a phrase on its unit length: points, and the indices of corners.
/// `segments[i]` is the number of segments for part `i`.
fn trace(phrase: &Phrase, segments: &[usize]) -> (Vec<Point>, BTreeSet<usize>) {
    const SUBSTEPS: usize = 8;
    let mut points = vec![Point::new(0.0, 0.0)];
    let mut corners = BTreeSet::new();
    let mut heading = 0.0;
    let mut position = Point::new(0.0, 0.0);
    for (index, part) in phrase.parts.iter().enumerate() {
        if index > 0
            && let Joint::Corner(turn) = phrase.joints[index - 1]
        {
            corners.insert(points.len() - 1);
            heading += turn;
        }
        let count = segments[index].max(1);
        let start_heading = heading;
        for step in 0..count {
            for sub in 0..SUBSTEPS {
                let fraction = (step * SUBSTEPS + sub) as f64 / (count * SUBSTEPS) as f64;
                let next = (step * SUBSTEPS + sub + 1) as f64 / (count * SUBSTEPS) as f64;
                let middle = start_heading + heading_within(part, (fraction + next) / 2.0);
                let ds = part.length * (next - fraction);
                position = Point::new(
                    position.x + ds * middle.cos(),
                    position.y + ds * middle.sin(),
                );
            }
            points.push(position);
        }
        heading = start_heading + part.turn;
    }
    (points, corners)
}

fn distance(a: Point, b: Point) -> f64 {
    (b.x - a.x).hypot(b.y - a.y)
}

fn path_length(points: &[Point]) -> f64 {
    points
        .windows(2)
        .map(|pair| distance(pair[0], pair[1]))
        .sum()
}

/// Which whole-line condition a traced path breaks, if any. Crossing itself
/// is allowed.
fn whole_line_violation(
    points: &[Point],
    turns: impl Iterator<Item = f64>,
) -> Option<&'static str> {
    let first = points[0];
    let last = points[points.len() - 1];
    let chord = distance(first, last);
    let length = path_length(points);
    if chord / length < MIN_CHORD_RATIO {
        return Some("chord_ratio");
    }
    let ux = (last.x - first.x) / chord;
    let uy = (last.y - first.y) / chord;
    for point in points {
        let along = ((point.x - first.x) * ux + (point.y - first.y) * uy) / chord;
        let across = ((point.x - first.x) * -uy + (point.y - first.y) * ux).abs() / chord;
        if across > 0.6 {
            return Some("lateral");
        }
        if !(-0.25..=1.25).contains(&along) {
            return Some("overshoot");
        }
    }
    let (mut net, mut absolute) = (0.0_f64, 0.0);
    for turn in turns {
        net += turn;
        absolute += turn.abs();
    }
    if net.abs() > MAX_NET_TURN.to_radians() + 1.0e-9 {
        return Some("net_turn");
    }
    if absolute > MAX_TOTAL_TURN.to_radians() + 1.0e-9 {
        return Some("total_turn");
    }
    None
}

fn part_violation(phrase: &Phrase) -> Option<&'static str> {
    let total = phrase.total_length();
    for part in &phrase.parts {
        match part.kind {
            Kind::Straight => {}
            Kind::Arc => {
                if part.length / part.turn.abs() < ARC_RADIUS * total {
                    return Some("arc_radius");
                }
            }
            Kind::Free { .. } => {
                if part.length / (2.0 * part.turn.abs()) < FREE_RADIUS * total {
                    return Some("free_radius");
                }
            }
        }
    }
    None
}

/// Segments that resolve a part finely enough to check it.
fn check_segments(phrase: &Phrase) -> Vec<usize> {
    phrase
        .parts
        .iter()
        .map(|part| {
            let by_length = (part.length / 0.004).ceil();
            let by_turn = (part.turn.abs().to_degrees() / 2.0).ceil();
            by_length.max(by_turn).max(4.0) as usize
        })
        .collect()
}

fn phrase_violation(phrase: &Phrase) -> Option<&'static str> {
    if let Some(reason) = part_violation(phrase) {
        return Some(reason);
    }
    let (points, _) = trace(phrase, &check_segments(phrase));
    whole_line_violation(&points, phrase.turns())
}

/// The phrase a free line falls back to when no draw meets the conditions.
fn fallback_phrase() -> Phrase {
    Phrase {
        parts: vec![
            Part {
                kind: Kind::Straight,
                length: 0.65,
                turn: 0.0,
            },
            Part {
                kind: Kind::Arc,
                length: 0.35,
                turn: 45.0_f64.to_radians(),
            },
        ],
        joints: vec![Joint::Smooth],
    }
}

/// One phrase, the tries it took, and whether it fell back.
struct Built {
    phrase: Phrase,
    #[cfg_attr(not(test), allow(dead_code))]
    tries: i64,
    #[cfg_attr(not(test), allow(dead_code))]
    fell_back: bool,
}

fn build_phrase(seed: Seed, build: Build) -> Built {
    for attempt in 0..MAX_TRIES {
        let mut draw = Draw::new(seed, format!("{PHRASE_LABEL}-{attempt}"));
        if let Some(phrase) = phrase_draw(&mut draw, build)
            && phrase_violation(&phrase).is_none()
        {
            return Built {
                phrase,
                tries: attempt + 1,
                fell_back: false,
            };
        }
    }
    Built {
        phrase: fallback_phrase(),
        tries: MAX_TRIES,
        fell_back: true,
    }
}

/// Resample a polyline at `count` segments of equal arc length.
fn resample(points: &[Point], count: usize) -> Vec<Point> {
    let mut cumulative = vec![0.0];
    for pair in points.windows(2) {
        let last = *cumulative.last().expect("nonempty");
        cumulative.push(last + distance(pair[0], pair[1]));
    }
    let total = *cumulative.last().expect("nonempty");
    let mut out = Vec::with_capacity(count + 1);
    let mut cursor = 0;
    for index in 0..=count {
        let target = total * index as f64 / count as f64;
        while cursor + 1 < cumulative.len() - 1 && cumulative[cursor + 1] < target {
            cursor += 1;
        }
        let span = (cumulative[cursor + 1] - cumulative[cursor]).max(1.0e-12);
        let t = ((target - cumulative[cursor]) / span).clamp(0.0, 1.0);
        let a = points[cursor];
        let b = points[cursor + 1];
        out.push(Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t));
    }
    out
}

/// Map points so the first lands on `start` and the last on `end`, keeping shape.
fn onto_chord(points: &[Point], start: Point, end: Point) -> Vec<Point> {
    let first = points[0];
    let last = points[points.len() - 1];
    let (ax, ay) = (last.x - first.x, last.y - first.y);
    let (bx, by) = (end.x - start.x, end.y - start.y);
    let denominator = ax * ax + ay * ay;
    // The complex ratio b / a rotates and scales the phrase onto the chord.
    let (rx, ry) = (
        (bx * ax + by * ay) / denominator,
        (by * ax - bx * ay) / denominator,
    );
    points
        .iter()
        .map(|point| {
            let (dx, dy) = (point.x - first.x, point.y - first.y);
            Point::new(start.x + dx * rx - dy * ry, start.y + dx * ry + dy * rx)
        })
        .collect()
}

/// The paper a free line is drawn on, in pixels.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Sheet {
    pub(crate) width: f64,
    pub(crate) height: f64,
}

/// The box a drawn mark leaves for the free lines after it, in pixels:
/// `[min_x, min_y, max_x, max_y]`.
pub(crate) type Obstacle = [f64; 4];

fn box_distance(point: Point, obstacle: &Obstacle) -> f64 {
    let dx = (obstacle[0] - point.x).max(0.0).max(point.x - obstacle[2]);
    let dy = (obstacle[1] - point.y).max(0.0).max(point.y - obstacle[3]);
    dx.hypot(dy)
}

/// The weighted mean room along a path in pixels, and the share of its 64
/// points closer than 0.05 short sides to the edge or to a drawn mark.
///
/// The room at a point is its distance to the nearer of the paper's edges and
/// the obstacles, capped at 0.2 short sides. The last 30% of the path weighs
/// twice: where a line ends is what it opens into.
fn room(points: &[Point], sheet: Sheet, obstacles: &[Obstacle]) -> (f64, f64) {
    let short = sheet.width.min(sheet.height);
    let samples = resample(points, 63);
    let (mut total, mut weights, mut crowded) = (0.0, 0.0, 0usize);
    for (index, point) in samples.iter().enumerate() {
        let edge = point
            .x
            .min(sheet.width - point.x)
            .min(point.y)
            .min(sheet.height - point.y);
        let mut space = edge;
        for obstacle in obstacles {
            space = space.min(box_distance(*point, obstacle));
        }
        if space < 0.05 * short {
            crowded += 1;
        }
        let weight = if index as f64 / 63.0 >= 0.7 { 2.0 } else { 1.0 };
        total += weight * space.min(0.2 * short);
        weights += weight;
    }
    (total / weights, crowded as f64 / samples.len() as f64)
}

/// The phrase with the sides of its bends (arcs, free curves, corners) taken
/// from `signs`, in the order parts then corners.
fn with_signs(phrase: &Phrase, signs: &[f64]) -> Phrase {
    let mut next = signs.iter();
    let mut parts = phrase.parts.clone();
    for part in &mut parts {
        if part.kind != Kind::Straight {
            part.turn = part.turn.abs() * next.next().copied().unwrap_or(1.0);
        }
    }
    let joints = phrase
        .joints
        .iter()
        .map(|joint| match joint {
            Joint::Smooth => Joint::Smooth,
            Joint::Corner(turn) => Joint::Corner(turn.abs() * next.next().copied().unwrap_or(1.0)),
        })
        .collect();
    Phrase { parts, joints }
}

fn bend_count(phrase: &Phrase) -> usize {
    phrase
        .parts
        .iter()
        .filter(|part| part.kind != Kind::Straight)
        .count()
        + phrase
            .joints
            .iter()
            .filter(|joint| matches!(joint, Joint::Corner(_)))
            .count()
}

/// What choosing the sides did: the chosen phrase, its candidate's index
/// (0 is the coin's), and the coin's and the choice's room and crowding.
struct Sides {
    phrase: Phrase,
    #[cfg_attr(not(test), allow(dead_code))]
    index: usize,
    #[cfg_attr(not(test), allow(dead_code))]
    coin: (f64, f64),
    #[cfg_attr(not(test), allow(dead_code))]
    chosen: (f64, f64),
}

/// Choose the sides of the bends that open the line into the most room: the
/// coin's sides and 31 more draws, each kept only if it meets the conditions.
fn choose_sides(
    phrase: &Phrase,
    seed: Seed,
    start: Point,
    end: Point,
    sheet: Sheet,
    obstacles: &[Obstacle],
) -> Sides {
    let count = bend_count(phrase);
    let mut best: Option<(f64, usize, Phrase, (f64, f64))> = None;
    let mut coin = (0.0, 0.0);
    for index in 0..SIDE_CANDIDATES {
        let candidate = if index == 0 {
            phrase.clone()
        } else {
            let mut draw = Draw::new(seed, format!("{SIDES_LABEL}-{index}"));
            let signs: Vec<f64> = (0..count).map(|_| draw.sign()).collect();
            with_signs(phrase, &signs)
        };
        if index > 0 && phrase_violation(&candidate).is_some() {
            continue;
        }
        let (unit_points, _) = trace(&candidate, &check_segments(&candidate));
        let measured = room(&onto_chord(&unit_points, start, end), sheet, obstacles);
        if index == 0 {
            coin = measured;
        }
        if best.as_ref().is_none_or(|(score, ..)| measured.0 > *score) {
            best = Some((measured.0, index, candidate, measured));
        }
    }
    let (_, index, phrase, chosen) = best.expect("the coin's phrase is always a candidate");
    Sides {
        phrase,
        index,
        coin,
        chosen,
    }
}

/// What a free line mark needs to build its path.
#[derive(Clone, Copy, Debug)]
pub(crate) struct FreeLineRequest<'a> {
    pub(crate) weight: Weight,
    /// The mark's own seed, from [`free_line_seed`].
    pub(crate) seed: Seed,
    /// The ends in pixels, after the rotation and the group transform.
    pub(crate) start: Point,
    pub(crate) end: Point,
    pub(crate) sheet: Sheet,
    /// The boxes of the marks drawn before it that are not lines.
    pub(crate) obstacles: &'a [Obstacle],
    /// The distance between drawn points along the path, in pixels.
    pub(crate) spacing: f64,
}

/// A free line's path in pixels and the indices of its corners.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct FreeLinePath {
    pub(crate) points: Vec<Point>,
    pub(crate) corners: BTreeSet<usize>,
}

/// Build one free line's path from its start to its end.
///
/// The ends stay exactly where the request puts them. A degenerate chord
/// gives the two ends.
#[must_use]
pub(crate) fn free_line_path(request: FreeLineRequest<'_>) -> FreeLinePath {
    let FreeLineRequest {
        weight,
        seed,
        start,
        end,
        sheet,
        obstacles,
        spacing,
    } = request;
    let chord = distance(start, end);
    if !chord.is_finite() || chord <= 1.0e-9 || !spacing.is_finite() || spacing <= 0.0 {
        return FreeLinePath {
            points: vec![start, end],
            corners: BTreeSet::new(),
        };
    }
    let phrase = build_phrase(seed, build_for_tool(weight)).phrase;
    let phrase = choose_sides(&phrase, seed, start, end, sheet, obstacles).phrase;
    let (unit_points, _) = trace(&phrase, &check_segments(&phrase));
    let scale = chord / distance(unit_points[0], unit_points[unit_points.len() - 1]);
    let mut segments: Vec<usize> = phrase
        .parts
        .iter()
        .map(|part| {
            let by_length = (part.length * scale / spacing).ceil();
            let by_turn = (part.turn.abs().to_degrees() / 6.0).ceil();
            by_length.max(by_turn).max(1.0) as usize
        })
        .collect();
    let total: usize = segments.iter().sum();
    if total > MAX_POINTS {
        for count in &mut segments {
            *count = (*count * MAX_POINTS / total).max(1);
        }
    }
    let (points, corners) = trace(&phrase, &segments);
    let mut points = onto_chord(&points, start, end);
    // The similarity lands the last point on `end` up to rounding; pin both.
    points[0] = start;
    let last = points.len() - 1;
    points[last] = end;
    FreeLinePath { points, corners }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool {
        let cross =
            |a: Point, b: Point, c: Point| (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
        let d1 = cross(c, d, a);
        let d2 = cross(c, d, b);
        let d3 = cross(a, b, c);
        let d4 = cross(a, b, d);
        ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
            && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
    }

    fn self_crosses(points: &[Point]) -> bool {
        let count = points.len();
        (0..count.saturating_sub(1)).any(|first| {
            (first + 2..count.saturating_sub(1)).any(|second| {
                segments_cross(
                    points[first],
                    points[first + 1],
                    points[second],
                    points[second + 1],
                )
            })
        })
    }

    /// The prototype's record over seeds 0 to 999 (I-715 stage A2, `k3-a2.txt`):
    /// violations, fallbacks, mean tries, median total turn, crossing paths and
    /// the counts of 3 to 7 parts.
    fn statistics(build: Build) -> String {
        let (mut violations, mut fallbacks, mut tries, mut crossing) = (0, 0, 0i64, 0);
        let mut counts = [0usize; 8];
        let mut totals = Vec::new();
        for seed in 0..1000i128 {
            let built = build_phrase(seed, build);
            if !built.fell_back && phrase_violation(&built.phrase).is_some() {
                violations += 1;
            }
            fallbacks += usize::from(built.fell_back);
            tries += built.tries;
            totals.push(built.phrase.turns().map(f64::abs).sum::<f64>().to_degrees());
            counts[built.phrase.parts.len()] += 1;
            let (points, _) = trace(&built.phrase, &check_segments(&built.phrase));
            crossing += usize::from(self_crosses(&points));
        }
        totals.sort_by(f64::total_cmp);
        format!(
            "violations {violations} fallbacks {fallbacks} mean tries {:.2} median total turn {:.1} deg crossing {crossing}/1000 parts 3:{} 4:{} 5:{} 6:{} 7:{}",
            tries as f64 / 1000.0,
            totals[500],
            counts[3],
            counts[4],
            counts[5],
            counts[6],
            counts[7]
        )
    }

    #[test]
    fn free_line_phrases_match_the_prototype_over_a_thousand_seeds() {
        assert_eq!(
            statistics(Build::Geometric),
            "violations 0 fallbacks 0 mean tries 2.14 median total turn 361.8 deg crossing 160/1000 parts 3:178 4:267 5:255 6:162 7:138"
        );
        assert_eq!(
            statistics(Build::Mixed),
            "violations 0 fallbacks 0 mean tries 2.13 median total turn 377.9 deg crossing 150/1000 parts 3:168 4:276 5:261 6:171 7:124"
        );
    }

    /// The prototype's side choice on an empty sheet (stage A3, `k3-a3.txt`):
    /// a horizontal chord of 0.55 short sides near the bottom edge.
    #[test]
    fn free_line_sides_match_the_prototype_on_an_empty_sheet() {
        let sheet = Sheet {
            width: 1000.0,
            height: 1000.0,
        };
        let (start, end) = (Point::new(225.0, 850.0), Point::new(775.0, 850.0));
        for (build, expected) in [
            (
                Build::Geometric,
                "violations 0 changed 834/1000 mean crowd coin 0.145 chosen 0.003",
            ),
            (
                Build::Mixed,
                "violations 0 changed 858/1000 mean crowd coin 0.158 chosen 0.002",
            ),
        ] {
            let (mut violations, mut changed) = (0, 0);
            let (mut coin_crowd, mut chosen_crowd) = (0.0, 0.0);
            for seed in 0..1000i128 {
                let built = build_phrase(seed, build);
                let sides = choose_sides(&built.phrase, seed, start, end, sheet, &[]);
                violations +=
                    usize::from(phrase_violation(&sides.phrase).is_some() && !built.fell_back);
                changed += usize::from(sides.index != 0);
                coin_crowd += sides.coin.1;
                chosen_crowd += sides.chosen.1;
            }
            assert_eq!(
                format!(
                    "violations {violations} changed {changed}/1000 mean crowd coin {:.3} chosen {:.3}",
                    coin_crowd / 1000.0,
                    chosen_crowd / 1000.0
                ),
                expected
            );
        }
    }

    #[test]
    fn free_line_path_lands_on_its_ends_and_is_deterministic() {
        let request = FreeLineRequest {
            weight: Weight::BrushThin,
            seed: free_line_seed(7, 2, 0),
            start: Point::new(100.0, 200.0),
            end: Point::new(260.0, 180.0),
            sheet: Sheet {
                width: 1000.0,
                height: 1000.0,
            },
            obstacles: &[[400.0, 400.0, 600.0, 600.0]],
            spacing: 1000.0 / 49.0,
        };
        let path = free_line_path(request);
        assert_eq!(path.points.first(), Some(&request.start));
        assert_eq!(path.points.last(), Some(&request.end));
        assert!(path.points.len() > 2);
        assert_eq!(free_line_path(request), path);
        assert_ne!(
            free_line_path(FreeLineRequest {
                seed: free_line_seed(7, 2, 1),
                ..request
            }),
            path
        );
    }

    #[test]
    fn free_line_path_keeps_its_points_bounded() {
        let path = free_line_path(FreeLineRequest {
            weight: Weight::OilPaint,
            seed: free_line_seed(11, 0, 0),
            start: Point::new(-40_000.0, 500.0),
            end: Point::new(40_000.0, 500.0),
            sheet: Sheet {
                width: 1000.0,
                height: 1000.0,
            },
            obstacles: &[],
            spacing: 1000.0 / 49.0,
        });
        assert!(path.points.len() <= MAX_POINTS + 1, "{}", path.points.len());
    }

    #[test]
    fn free_line_tools_split_into_the_two_builds() {
        let geometric = Weight::ALL
            .iter()
            .filter(|weight| build_for_tool(**weight) == Build::Geometric)
            .count();
        assert_eq!((geometric, Weight::ALL.len() - geometric), (7, 5));
    }
}
