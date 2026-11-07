//! The media of Saijiki v3 (the touch reorganisation, 2026-10-31): watercolour,
//! oil pastel, the painting knife and etching draw their own lines, edges and flat
//! fills here, and oil paint takes its mixing streaks. Each mark carries the few
//! definitions it needs (filters and clips) inside its own group, so the
//! document's shared definitions do not change; their ids name the mark
//! ([`MarkIds`]), and each filter is worked out over the mark's box only
//! ([`Region`]). The drawing is the prototypes the author judged (steps 3 B, 5
//! and 6, `topics/draw-task/tools-innvoation/DECIDED.ja.md`), with each choice
//! fixed: the knife and watercolour mix 30%, oil paint 12%, oil pastel none, and
//! etching is drawn with light and dark. Watercolour overlaps by plain opacity:
//! the display's Skia does not draw `mix-blend-mode`, and the author chose to
//! drop the multiply (2026-10-31).
//!
//! What each medium has to show (HANDOFF-STEP3 §6.3):
//! - watercolour: colour that lets the paper and the colour below through and
//!   darkens where washes overlap; pigment pooled inside the dried edge, fading
//!   inwards; granulation and pale blooms in the wash.
//! - oil pastel: broad, blunt, opaque strokes that cover a dark ground; the
//!   paper's tooth shows mostly along the edges; a face laid with directional
//!   strokes whose tracks stay visible.
//! - painting knife (named the palette knife until the author chose the precise
//!   name): flat planes of paint with sharp edges and no bristle marks; each
//!   plane a little lighter or darker; a raised ridge of paint along one edge
//!   and a lit lip on the other; planes turned and overlapped, with gaps.
//!
//! Step 5 (2026-10-31, after the author's judgement of step 3 B):
//! - an oil pastel face is laid in short, slightly bent strokes whose
//!   direction turns slowly across the face, not in long parallel bands (the
//!   author saw straight stripes);
//! - each pull of the palette knife is one mark: sides that waver, a ridge
//!   pressed out where the blade was set down, a lip where it was lifted and
//!   a thin tail dragged past it, lit and shadowed edges that break off (the
//!   author found the planes too digital and asked for the start and end);
//! - colour mixing (the author's note): a share of the knife's planes take,
//!   or streak in, another colour of the same Score;
//! - etching: an etched line, even in width, its edge a little bitten, its
//!   ends round, and a face as needle hatching;
//! - gouache: the fine brush whose thick and extra-thick steps widen to reach
//!   the thick brush's (`marks.rs`); it draws no medium of its own here.
//!
//! Step 6 (2026-10-31, after the author's judgement of step 5):
//! - the knife's pulls run longer and bend with a curved line; the paint is
//!   piled where the blade was set down and spread thinner from there, under
//!   one light from the upper left; some pulls run dry at the end and break
//!   into streaks (the author: longer strokes, piled then spread, a dry end
//!   on some, not all); the knife mixes 30% by default (the author's choice);
//! - colour mixing for oil paint, oil pastel and watercolour: a streak of
//!   another colour in an oil pass, another colour under and among an oil
//!   pastel's strokes (the author chose none), pigment of another colour
//!   separating at a wash's edge and blooming inside it;
//! - etching with light and dark: each line bitten to its own depth, and a
//!   face hatched at its own angle, its lines heavier towards one side,
//!   crossed only there (the author found a face of even parallel lines
//!   monotonous).

use std::cell::RefCell;

use inku_score::math::DetFloat;

use crate::determinism::hash01;
use crate::materials::bristle_tone;
use crate::svg::{Element, format_number};
use crate::types::{Point, Seed, Weight};

thread_local! {
    /// The resolved colours of the Score being drawn, once each, for the media's mixing.
    /// Set for one render by [`PaletteScope`]; outside one it is empty and nothing mixes.
    static PALETTE: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
    /// The id prefix of the mark being drawn and the next number under it. Set for one
    /// mark by [`MarkIds`]. The renderer draws a Score on one thread, mark after mark, so
    /// the same Score and seed give the same ids.
    static IDS: RefCell<(String, usize)> = const { RefCell::new((String::new(), 0)) };
}

/// The Score's colours for the media's mixing, for as long as the scope lives.
pub(crate) struct PaletteScope;

impl PaletteScope {
    /// Keep the Score's resolved colours, once each, until the scope is dropped.
    pub(crate) fn enter(colors: Vec<String>) -> Self {
        let mut unique = Vec::new();
        for color in colors {
            if !unique.contains(&color) {
                unique.push(color);
            }
        }
        PALETTE.with(|palette| *palette.borrow_mut() = unique);
        Self
    }
}

impl Drop for PaletteScope {
    fn drop(&mut self) {
        PALETTE.with(|palette| palette.borrow_mut().clear());
    }
}

/// The ids of one mark's definitions: `prefix` names the mark (the caller's role, the
/// instruction and the mark), and each definition takes the next number under it.
pub(crate) struct MarkIds;

impl MarkIds {
    pub(crate) fn enter(prefix: String) -> Self {
        IDS.with(|ids| *ids.borrow_mut() = (prefix, 0));
        Self
    }
}

impl Drop for MarkIds {
    fn drop(&mut self) {
        IDS.with(|ids| *ids.borrow_mut() = (String::new(), 0));
    }
}

/// Whether the medium draws its own marks here: the tools of Saijiki v3 that are not
/// a brush (gouache draws as the fine brush does).
pub(crate) const fn owns(weight: Weight) -> bool {
    matches!(
        weight,
        Weight::Watercolor | Weight::OilPastel | Weight::PaintingKnife | Weight::Etching
    )
}

/// The share of a medium's marks that take another colour of the Score (the author's
/// choices, てざわりの整理 step 5 and 6): the painting knife 30%, watercolour 30%, oil
/// paint 12%, oil pastel none.
const fn mix_share(weight: Weight) -> f64 {
    match weight {
        Weight::PaintingKnife | Weight::Watercolor => 0.3,
        Weight::OilPaint => 0.12,
        _ => 0.0,
    }
}

/// Towards the one light of the knife's relief and the etching's shading:
/// the upper left (pixels, y down).
fn light() -> Point {
    Point::new(-0.55, -0.835)
}

/// Relative luminance of an sRGB colour, 0 for black to 1 for white.
fn lightness(color: &str) -> f64 {
    rgb(color).map_or(0.0, |[r, g, b]| 0.2126 * r + 0.7152 * g + 0.0722 * b)
}

fn rgb(color: &str) -> Option<[f64; 3]> {
    let hex = color.strip_prefix('#')?;
    if hex.len() != 6 {
        return None;
    }
    let channel = |at: usize| {
        u8::from_str_radix(hex.get(at..at + 2)?, 16)
            .ok()
            .map(|value| f64::from(value) / 255.0)
    };
    Some([channel(0)?, channel(2)?, channel(4)?])
}

/// Another colour of the Score, far enough from `color` to be seen.
fn other_color(color: &str, pick: f64) -> Option<String> {
    let own = rgb(color)?;
    PALETTE.with(|palette| {
        let others = palette
            .borrow()
            .iter()
            .filter(|other| {
                rgb(other).is_some_and(|o| {
                    ((o[0] - own[0]).powi(2) + (o[1] - own[1]).powi(2) + (o[2] - own[2]).powi(2))
                        .sqrt()
                        > 0.12
                })
            })
            .cloned()
            .collect::<Vec<_>>();
        let index = ((pick * others.len() as f64) as usize).min(others.len().saturating_sub(1));
        others.get(index).cloned()
    })
}

/// `a` mixed towards `b` by `t`, in linear light.
fn mix(a: &str, b: &str, t: f64) -> String {
    let (Some(x), Some(y)) = (rgb(a), rgb(b)) else {
        return a.to_owned();
    };
    let linear = |c: f64| {
        if c <= 0.04045 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).dpowf(2.4)
        }
    };
    let encoded = |c: f64| {
        if c <= 0.003_130_8 {
            c * 12.92
        } else {
            1.055 * c.dpowf(1.0 / 2.4) - 0.055
        }
    };
    let channel = |i: usize| {
        (encoded(linear(x[i]) * (1.0 - t) + linear(y[i]) * t).clamp(0.0, 1.0) * 255.0).round() as u8
    };
    format!("#{:02x}{:02x}{:02x}", channel(0), channel(1), channel(2))
}

/// An open path through `points`, for strokes laid on top of a mark.
fn polyline_path(points: &[Point]) -> Element {
    Element::new("path")
        .attr("d", crate::svg::open_polyline_path(points))
        .attr("fill", "none")
        .attr("stroke-linecap", "round")
        .attr("stroke-linejoin", "round")
}

/// A new id for one of the current mark's definitions.
fn fresh(prefix: &str) -> String {
    IDS.with(|ids| {
        let mut ids = ids.borrow_mut();
        debug_assert!(
            !ids.0.is_empty(),
            "media ids are drawn inside a mark's MarkIds"
        );
        let number = ids.1;
        ids.1 += 1;
        format!("{prefix}-{}-{number}", ids.0)
    })
}

fn noise_seed(seed: Seed, salt: &str) -> String {
    format!("{}", 1 + (hash01(0, seed, salt) * 9_000.0) as u32)
}

fn n(value: f64) -> String {
    format_number(value)
}

fn closed_d(points: &[Point]) -> String {
    crate::svg::closed_polyline_path(points)
}

fn bounds(points: &[Point]) -> (f64, f64, f64, f64) {
    points.iter().fold(
        (f64::MAX, f64::MAX, f64::MIN, f64::MIN),
        |(x0, y0, x1, y1), p| (x0.min(p.x), y0.min(p.y), x1.max(p.x), y1.max(p.y)),
    )
}

/// The outline of a stroke between its two banks: one polygon for an open
/// stroke, two rings (filled even-odd) for a closed one.
fn banks_d(left: &[Point], right: &[Point], closed: bool) -> String {
    if closed {
        return format!("{} {}", closed_d(left), closed_d(right));
    }
    let outline = left
        .iter()
        .copied()
        .chain(right.iter().rev().copied())
        .collect::<Vec<_>>();
    closed_d(&outline)
}

/// The same stroke narrowed towards its centreline by `ratio`.
fn narrowed(left: &[Point], right: &[Point], ratio: f64) -> (Vec<Point>, Vec<Point>) {
    left.iter()
        .zip(right)
        .map(|(l, r)| {
            let c = Point::new((l.x + r.x) * 0.5, (l.y + r.y) * 0.5);
            (
                Point::new(c.x + (l.x - c.x) * ratio, c.y + (l.y - c.y) * ratio),
                Point::new(c.x + (r.x - c.x) * ratio, c.y + (r.y - c.y) * ratio),
            )
        })
        .unzip()
}

fn mean_width(left: &[Point], right: &[Point]) -> f64 {
    let count = left.len().min(right.len()).max(1);
    left.iter()
        .zip(right)
        .map(|(l, r)| (l.x - r.x).dhypot(l.y - r.y))
        .sum::<f64>()
        / count as f64
}

/// A band along part of a stroke, between its banks: across from `center` to
/// `center + width` (fractions of the way from the left bank to the right),
/// along from `start` to `end` (fractions of its length), fading in and out.
fn streak_band(
    left: &[Point],
    right: &[Point],
    closed: bool,
    center: f64,
    width: f64,
    start: f64,
    end: f64,
) -> Option<Vec<Point>> {
    let count = left.len().min(right.len());
    if count < 2 || end <= start {
        return None;
    }
    let span = (count - usize::from(!closed)) as f64;
    let (mut near, mut far) = (Vec::new(), Vec::new());
    for (sample, (a, b)) in left.iter().zip(right).enumerate() {
        let t = sample as f64 / span;
        if t < start || t > end {
            continue;
        }
        let along = (t - start) / (end - start);
        let fade = (along / 0.15).min((1.0 - along) / 0.15).clamp(0.0, 1.0);
        let at =
            |fraction: f64| Point::new(a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction);
        near.push(at(center));
        far.push(at(center + width * fade));
    }
    if near.len() < 2 {
        return None;
    }
    near.extend(far.into_iter().rev());
    Some(near)
}

/// Colour mixing in an oil pass (`INKU_PROTO_MIX`): a share of the passes,
/// lines and the passes of a face alike, carry two to four narrow streaks
/// mixed a third to a half of the way towards another colour of the Score
/// along most of their length, as if the brush had taken up two colours.
/// Nothing for the passes the share leaves alone.
pub(crate) fn oil_mix_streak(
    left: &[Point],
    right: &[Point],
    color: &str,
    seed: Seed,
    closed: bool,
    width_normal: Option<Point>,
) -> Option<Element> {
    let share = mix_share(Weight::OilPaint);
    if share <= 0.0 || hash01(0, seed, "oil-mix") >= share {
        return None;
    }
    let other = other_color(color, hash01(0, seed, "oil-mix-pick"))?;
    let mut group = Element::new("g").attr("class", "proto-oil-mix");
    for k in 0..2 + (hash01(0, seed, "oil-mix-bands") * 3.0) as i64 {
        let width = 0.04 + 0.06 * hash01(k, seed, "oil-mix-width");
        let center = 0.08 + (0.84 - width) * hash01(k, seed, "oil-mix-at");
        let start = 0.15 * hash01(k, seed, "oil-mix-start");
        let end = (0.65 + 0.35 * hash01(k, seed, "oil-mix-end")).min(1.0);
        if let Some(mut band) = streak_band(left, right, closed, center, width, start, end) {
            if width_normal.is_some() {
                let half = band.len() / 2;
                let (near, far) = band.split_at_mut(half);
                far.reverse();
                crate::materials::damp_oil_band(near, far, width_normal);
                far.reverse();
            }
            group.push(
                path(&closed_d(&band))
                    .attr(
                        "fill",
                        mix(
                            color,
                            &other,
                            0.35 + 0.2 * hash01(k, seed, "oil-mix-amount"),
                        ),
                    )
                    .attr("fill-opacity", "0.9")
                    .attr("stroke", "none"),
            );
        }
    }
    Some(group)
}

fn path(d: &str) -> Element {
    Element::new("path").attr("d", d)
}

/// Where one mark's filter is worked out, in user space: the mark's box grown
/// by what the filter adds around the mark (a stroke's half width, a blur's
/// reach, a displacement's shift) and a little more for antialiasing and the
/// raster's rounding.
#[derive(Clone, Copy, Debug)]
struct Region {
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
}

/// How far a blur of `deviation` spreads a mark, in user units: four
/// deviations, past which a gaussian keeps under a tenth of a level.
fn blur_reach(deviation: f64) -> f64 {
    4.0 * deviation.max(0.01)
}

impl Region {
    fn around(points: &[Point], reach: f64, unit: f64) -> Self {
        let (x0, y0, x1, y1) = bounds(points);
        if !(x0 <= x1 && y0 <= y1) {
            return Self {
                x0: 0.0,
                y0: 0.0,
                x1: 0.0,
                y1: 0.0,
            };
        }
        let grow = reach.max(0.0) + 2.0 + unit * 0.002;
        Self {
            x0: x0 - grow,
            y0: y0 - grow,
            x1: x1 + grow,
            y1: y1 + grow,
        }
    }
}

/// A displacement with the look the Server's PNG gave it (the author's choice,
/// てざわりの整理 2026-10-31), drawn alike by every renderer. resvg 0.48.1 (the
/// Server's and the CLI's PNG, Android's raster) multiplied a displacement's
/// scale in twice and read its map premultiplied: with scale `s` it moved a
/// pixel by `s * s` times the map's premultiplied channel less one half, where
/// Chrome and Skia (the screens) move it by `s` times the plain channel, so a
/// wash's edge wobbled eight times as much in the PNG as on the screen. The
/// filter now writes that look as the specification reads it: a scale of
/// `k = s * s` on a map made opaque (its colour is then its premultiplied
/// colour). Chrome, Skia and a resvg that follows the specification (the core's
/// vendored resvg with upstream's fix, and the Server's PNG drawn by it) move a
/// pixel by `k` times that channel. A resvg 0.48.1 would move it `k * k`: no
/// PNG may be drawn by one.
#[derive(Clone, Copy, Debug)]
struct Displacement {
    /// How far the filter moves a pixel per unit of the map's channel, in
    /// canvas units.
    k: f64,
}

impl Displacement {
    /// The PNG's look of the scale `scale`: `k = scale * scale`.
    fn of_scale(scale: f64) -> Self {
        Self { k: scale * scale }
    }

    /// How far it can move a pixel, in canvas units.
    fn reach(self) -> f64 {
        0.5 * self.k
    }

    /// `input` moved by the noise `noise`, made opaque first.
    fn primitives(self, input: &str, noise: &str, result: &str) -> [Element; 3] {
        let (ground, map) = (format!("{noise}-ground"), format!("{noise}-map"));
        [
            Element::new("feFlood")
                .attr("flood-color", "#000000")
                .attr("flood-opacity", "1")
                .attr("result", &ground),
            Element::new("feComposite")
                .attr("in", noise)
                .attr("in2", &ground)
                .attr("operator", "arithmetic")
                .attr("k1", "0")
                .attr("k2", "1")
                .attr("k3", "1")
                .attr("result", &map),
            Element::new("feDisplacementMap")
                .attr("in", input)
                .attr("in2", &map)
                .attr("scale", n(self.k))
                .attr("xChannelSelector", "R")
                .attr("yChannelSelector", "G")
                .attr("result", result),
        ]
    }
}

/// A filter worked out over `region` only, in user space. The prototype gave
/// every mark's filter the canvas (a region taken from a thin stroke's bounding
/// box, in percentages of it, cut its smudge off in a visible box), so each
/// mark's noise was worked out over the whole canvas: 48 times today's tools on
/// a work of 130 etched lines (てざわりの整理, 2026-10-31). In a turned group
/// that canvas turned with the mark and cut the part of it outside. The noise
/// is a function of the place, so a region that holds every pixel the mark
/// paints, spreads or pulls from gives the pixels of a region without bounds.
fn filter(id: &str, region: Region) -> Element {
    Element::new("filter")
        .attr("id", id)
        .attr("filterUnits", "userSpaceOnUse")
        .attr("x", n(region.x0))
        .attr("y", n(region.y0))
        .attr("width", n(region.x1 - region.x0))
        .attr("height", n(region.y1 - region.y0))
        .attr("color-interpolation-filters", "sRGB")
}

/// A filter whose region is the bounding box of each element that uses it,
/// for one shared by many small marks: a canvas-wide region would be worked
/// out again for every mark.
fn local_filter(id: &str) -> Element {
    Element::new("filter")
        .attr("id", id)
        .attr("x", "-5%")
        .attr("y", "-5%")
        .attr("width", "110%")
        .attr("height", "110%")
        .attr("color-interpolation-filters", "sRGB")
}

/// The ground's tooth through the paint of a dry end: holes where the noise
/// is high, the noise laid on the canvas, so every mark that uses the filter
/// shows the same tooth.
fn local_tooth_filter(id: &str, frequency: f64, share: f64, seed: &str) -> Element {
    let threshold = 0.5 + 0.12 * inverse_tail(share);
    let mut f = local_filter(id);
    f.push(turbulence(frequency, 2, seed, "tooth"));
    f.push(alpha_from_noise(
        "tooth",
        10.0,
        10.0 * (threshold + 0.05),
        "open",
    ));
    f.push(
        Element::new("feComposite")
            .attr("in", "SourceGraphic")
            .attr("in2", "open")
            .attr("operator", "in"),
    );
    f
}

fn turbulence(frequency: f64, octaves: u32, seed: &str, result: &str) -> Element {
    Element::new("feTurbulence")
        .attr("type", "fractalNoise")
        .attr("baseFrequency", n(frequency))
        .attr("numOctaves", octaves.to_string())
        .attr("seed", seed)
        .attr("result", result)
}

/// Alpha from the noise's red channel: `offset - slope * red`, clamped.
fn alpha_from_noise(input: &str, slope: f64, offset: f64, result: &str) -> Element {
    Element::new("feColorMatrix")
        .attr("in", input)
        .attr("type", "matrix")
        .attr(
            "values",
            format!(
                "0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  {} 0 0 0 {}",
                n(-slope),
                n(offset)
            ),
        )
        .attr("result", result)
}

/// Holes in a mark where the noise is high: the paper's tooth. `share` is
/// roughly the part of the mark left open. `region` holds the mark and the
/// roughening's reach. With `rough`, the filter also roughens the mark's edge
/// by that displacement.
fn tooth_filter(
    id: &str,
    frequency: f64,
    share: f64,
    seed: &str,
    rough: Option<Displacement>,
    region: Region,
) -> Element {
    // Fractal noise sits near 0.5 with a spread of about 0.12.
    let threshold = 0.5 + 0.12 * inverse_tail(share);
    let mut f = filter(id, region);
    f.push(turbulence(frequency, 2, seed, "tooth"));
    f.push(alpha_from_noise(
        "tooth",
        10.0,
        10.0 * (threshold + 0.05),
        "open",
    ));
    if let Some(displacement) = rough {
        for primitive in displacement.primitives("SourceGraphic", "tooth", "rough") {
            f.push(primitive);
        }
        f.push(
            Element::new("feComposite")
                .attr("in", "rough")
                .attr("in2", "open")
                .attr("operator", "in"),
        );
    } else {
        f.push(
            Element::new("feComposite")
                .attr("in", "SourceGraphic")
                .attr("in2", "open")
                .attr("operator", "in"),
        );
    }
    f
}

/// How many spreads above the middle a normal value must be to leave `share`
/// above it (a rough inverse for 0.02..0.6).
fn inverse_tail(share: f64) -> f64 {
    let share = share.clamp(0.01, 0.6);
    // A few points of the normal tail, interpolated.
    let table = [
        (0.01, 2.33),
        (0.02, 2.05),
        (0.05, 1.64),
        (0.1, 1.28),
        (0.2, 0.84),
        (0.3, 0.52),
        (0.4, 0.25),
        (0.5, 0.0),
        (0.6, -0.25),
    ];
    for pair in table.windows(2) {
        let (a, za) = pair[0];
        let (b, zb) = pair[1];
        if share >= a && share <= b {
            return za + (zb - za) * (share - a) / (b - a);
        }
    }
    0.0
}

/// A blur; `region` holds the blurred mark and three deviations around it.
fn blur_filter(id: &str, deviation: f64, region: Region) -> Element {
    let mut f = filter(id, region);
    f.push(Element::new("feGaussianBlur").attr("stdDeviation", n(deviation.max(0.01))));
    f
}

/// Straight segments of `contour` along lines at `angle`, `spacing` apart.
fn scan_segments(contour: &[Point], angle: f64, spacing: f64, phase: f64) -> Vec<(Point, Point)> {
    let (sin, cos) = angle.dsin_cos();
    let direction = Point::new(cos, sin);
    let normal = Point::new(-sin, cos);
    let along = |p: &Point| p.x * direction.x + p.y * direction.y;
    let across = |p: &Point| p.x * normal.x + p.y * normal.y;
    let (low, high) = contour
        .iter()
        .map(across)
        .fold((f64::MAX, f64::MIN), |(a, b), v| (a.min(v), b.max(v)));
    let mut result = Vec::new();
    let mut offset = low + spacing * phase.clamp(0.05, 0.95);
    while offset < high {
        let mut hits = Vec::new();
        for edge in 0..contour.len() {
            let a = contour[edge];
            let b = contour[(edge + 1) % contour.len()];
            let (da, db) = (across(&a) - offset, across(&b) - offset);
            if (da <= 0.0 && db > 0.0) || (db <= 0.0 && da > 0.0) {
                let t = da / (da - db);
                let p = Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
                hits.push(along(&p));
            }
        }
        hits.sort_by(f64::total_cmp);
        for pair in hits.chunks(2) {
            if let [s, e] = pair {
                result.push((
                    Point::new(
                        normal.x * offset + direction.x * s,
                        normal.y * offset + direction.y * s,
                    ),
                    Point::new(
                        normal.x * offset + direction.x * e,
                        normal.y * offset + direction.y * e,
                    ),
                ));
            }
        }
        let next = offset + spacing;
        if next == offset {
            break;
        }
        offset = next;
    }
    result
}

// ---------------------------------------------------------------------------
// Strokes: lines, arcs, free lines, and the edges of empty closed shapes.

fn finite(point: &Point) -> bool {
    point.x.is_finite() && point.y.is_finite()
}

/// A straight stroke's outline: closed polygons (left bank, then the right
/// bank backwards) for each run, runs separated by a non-finite point where
/// the paper's tooth cut the stroke.
pub(crate) fn stroke_outline(
    weight: Weight,
    outline: &[Point],
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
) -> Element {
    let mut group = Element::new("g").attr("class", "proto-stroke-runs");
    let mut order = 0_i128;
    for run in outline.split(|point| !finite(point)) {
        if run.len() < 4 {
            continue;
        }
        let middle = run.len() / 2;
        let right = run[middle..].iter().rev().copied().collect::<Vec<_>>();
        group.push(stroke(
            weight,
            &run[..middle],
            &right,
            false,
            color,
            opacity,
            seed.wrapping_add(order),
            unit,
        ));
        order += 1;
    }
    group
}

/// A stroke between two banks (pixels). `closed` for a ring. Where the banks
/// hold a non-finite point the stroke is cut there, and each piece is drawn
/// open.
#[allow(clippy::too_many_arguments)]
pub(crate) fn stroke(
    weight: Weight,
    left: &[Point],
    right: &[Point],
    closed: bool,
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
) -> Element {
    let count = left.len().min(right.len());
    let (left, right) = (&left[..count], &right[..count]);
    if left.iter().chain(right).any(|point| !finite(point)) {
        let mut group = Element::new("g").attr("class", "proto-stroke-runs");
        let mut start = 0;
        let mut order = 0_i128;
        for index in 0..=count {
            let cut = index == count || !finite(&left[index]) || !finite(&right[index]);
            if cut {
                if index - start >= 2 {
                    group.push(one_stroke(
                        weight,
                        &left[start..index],
                        &right[start..index],
                        false,
                        color,
                        opacity,
                        seed.wrapping_add(order),
                        unit,
                    ));
                    order += 1;
                }
                start = index + 1;
            }
        }
        return group;
    }
    one_stroke(weight, left, right, closed, color, opacity, seed, unit)
}

#[allow(clippy::too_many_arguments)]
fn one_stroke(
    weight: Weight,
    left: &[Point],
    right: &[Point],
    closed: bool,
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
) -> Element {
    match weight {
        Weight::Watercolor => watercolor_stroke(left, right, closed, color, opacity, seed, unit),
        Weight::OilPastel => oil_pastel_stroke(left, right, closed, color, seed, unit),
        Weight::PaintingKnife => knife_stroke(left, right, closed, color, seed, unit),
        Weight::Etching => etching_stroke(left, right, closed, color, opacity, seed, unit),
        other => {
            debug_assert!(!owns(other), "every medium draws its own stroke");
            Element::new("g")
        }
    }
}

fn watercolor_stroke(
    left: &[Point],
    right: &[Point],
    closed: bool,
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
) -> Element {
    let d = banks_d(left, right, closed);
    let width = mean_width(left, right);
    let banks = [left, right].concat();
    let rim_width = (width * 0.28).max(unit * 0.0012);
    let (grain, clip, rim_blur) = (fresh("wc-grain"), fresh("wc-clip"), fresh("wc-rim"));
    let mut defs = Element::new("defs");
    defs.push(wash_filter(
        &grain,
        seed,
        unit,
        (width * 6.0).max(unit * 0.02),
        Region::around(&banks, 0.0, unit),
    ));
    let mut clip_path = Element::new("clipPath").attr("id", &clip);
    clip_path.push(path(&d).attr("fill-rule", "evenodd"));
    defs.push(clip_path);
    defs.push(blur_filter(
        &rim_blur,
        width * 0.12,
        Region::around(&banks, rim_width * 0.5 + blur_reach(width * 0.12), unit),
    ));
    let mut group = Element::new("g").attr("class", "media-watercolor-stroke");
    group.push(defs);
    group.push(
        path(&d)
            .attr("fill-rule", "evenodd")
            .attr("fill", color)
            .attr("fill-opacity", n((opacity * 0.85).min(0.9)))
            .attr("filter", format!("url(#{grain})")),
    );
    let mut rim = Element::new("g").attr("clip-path", format!("url(#{clip})"));
    rim.push(
        path(&d)
            .attr("fill", "none")
            .attr("stroke", bristle_tone(color, -0.10))
            .attr("stroke-width", n(rim_width))
            .attr("stroke-opacity", n((opacity * 0.9).min(0.85)))
            .attr("filter", format!("url(#{rim_blur})")),
    );
    group.push(rim);
    // Colour mixing: along parts of the edge the pigment that dried there
    // separated into another colour of the Score.
    let share = mix_share(Weight::Watercolor);
    if share > 0.0
        && hash01(0, seed, "wc-line-mix") < (share * 2.5).min(1.0)
        && let Some(other) = other_color(color, hash01(0, seed, "wc-line-mix-pick"))
    {
        let run = |k: i64, salt: &str, low: f64, high: f64| {
            n(width * (low + (high - low) * hash01(k, seed, salt)))
        };
        let mut parted = Element::new("g").attr("clip-path", format!("url(#{clip})"));
        parted.push(
            path(&d)
                .attr("fill", "none")
                .attr("stroke", mix(&other, color, 0.35))
                .attr("stroke-width", n(rim_width))
                .attr("stroke-opacity", n((opacity * 0.9).min(0.85)))
                .attr(
                    "stroke-dasharray",
                    format!(
                        "{} {} {} {}",
                        run(0, "wc-line-run", 3.0, 9.0),
                        run(1, "wc-line-gap", 6.0, 16.0),
                        run(2, "wc-line-run", 3.0, 9.0),
                        run(3, "wc-line-gap", 6.0, 16.0)
                    ),
                )
                .attr(
                    "stroke-dashoffset",
                    n(width * 12.0 * hash01(0, seed, "wc-line-offset")),
                )
                .attr("filter", format!("url(#{rim_blur})")),
        );
        group.push(parted);
    }
    group
}

/// The body of a wash: soft pale blooms at `bloom` scale and a fine
/// granulation, both taken out of the colour's alpha (so `region` needs only
/// hold the wash).
fn wash_filter(id: &str, seed: Seed, unit: f64, bloom: f64, region: Region) -> Element {
    let mut f = filter(id, region);
    f.push(turbulence(
        1.0 / bloom.max(1.0),
        2,
        &noise_seed(seed, "wc-bloom"),
        "bloom",
    ));
    f.push(alpha_from_noise("bloom", 1.6, 1.55, "bloom-alpha"));
    f.push(turbulence(
        260.0 / unit.max(1.0),
        2,
        &noise_seed(seed, "wc-granule"),
        "granule",
    ));
    f.push(alpha_from_noise("granule", 0.85, 1.32, "granule-alpha"));
    f.push(
        Element::new("feComposite")
            .attr("in", "bloom-alpha")
            .attr("in2", "granule-alpha")
            .attr("operator", "arithmetic")
            .attr("k1", "1")
            .attr("k2", "0")
            .attr("k3", "0")
            .attr("k4", "0")
            .attr("result", "wash"),
    );
    f.push(
        Element::new("feComposite")
            .attr("in", "SourceGraphic")
            .attr("in2", "wash")
            .attr("operator", "in"),
    );
    f
}

fn oil_pastel_stroke(
    left: &[Point],
    right: &[Point],
    closed: bool,
    color: &str,
    seed: Seed,
    unit: f64,
) -> Element {
    let d = banks_d(left, right, closed);
    let (core_left, core_right) = narrowed(left, right, 0.62);
    let core = banks_d(&core_left, &core_right, closed);
    let (sheen_left, sheen_right) = narrowed(left, right, 0.16);
    let sheen = banks_d(&sheen_left, &sheen_right, closed);
    let frequency = 300.0 / unit.max(1.0);
    let (edge_tooth, core_tooth) = (fresh("op-edge"), fresh("op-core"));
    let rough = Displacement::of_scale(unit * 0.002);
    // Every part of the stroke lies between its banks.
    let region = Region::around(&[left, right].concat(), rough.reach(), unit);
    let mut defs = Element::new("defs");
    defs.push(tooth_filter(
        &edge_tooth,
        frequency,
        0.34,
        &noise_seed(seed, "op-edge"),
        Some(rough),
        region,
    ));
    defs.push(tooth_filter(
        &core_tooth,
        frequency,
        0.05,
        &noise_seed(seed, "op-core"),
        None,
        region,
    ));
    let mut group = Element::new("g").attr("class", "proto-oil-pastel-stroke");
    group.push(defs);
    group.push(
        path(&d)
            .attr("fill-rule", "evenodd")
            .attr("fill", color)
            .attr("filter", format!("url(#{edge_tooth})")),
    );
    group.push(
        path(&core)
            .attr("fill-rule", "evenodd")
            .attr("fill", color)
            .attr("filter", format!("url(#{core_tooth})")),
    );
    // A waxy sheen down the middle of the stroke, where it was pressed hardest.
    group.push(
        path(&sheen)
            .attr("fill-rule", "evenodd")
            .attr("fill", bristle_tone(color, 0.07))
            .attr("fill-opacity", "0.35")
            .attr("filter", format!("url(#{core_tooth})")),
    );
    // Colour mixing: a stick of another colour of the Score went over part
    // of the stroke, in a narrow streak (none: the author's choice).
    let share = mix_share(Weight::OilPastel);
    if share > 0.0 && hash01(0, seed, "op-line-mix") < (share * 2.0).min(1.0) {
        let width = 0.12 + 0.08 * hash01(0, seed, "op-line-mix-w");
        let center = 0.2 + (0.6 - width) * hash01(0, seed, "op-line-mix-at");
        let start = 0.3 * hash01(0, seed, "op-line-mix-start");
        let end = (start + 0.4 + 0.5 * hash01(0, seed, "op-line-mix-end")).min(1.0);
        if let (Some(other), Some(band)) = (
            other_color(color, hash01(0, seed, "op-line-mix-pick")),
            streak_band(left, right, closed, center, width, start, end),
        ) {
            group.push(
                path(&closed_d(&band))
                    .attr("fill", mix(&other, color, 0.3))
                    .attr("filter", format!("url(#{core_tooth})")),
            );
        }
    }
    group
}

/// One pull of the knife along `spine` (points, and the blade's half width
/// there), from where it was set down to where it came away.
/// - Set-down: the paint piled up there. The plane swells a little and its
///   back is rounded; across the pile a crest catches the light, and the
///   slope turned away from the light is in shadow.
/// - Spread: past the pile the paint thins (the plane's opacity falls
///   towards the end, so the colour below shows a little) and the blade's
///   edge drags fine streaks along it. The side facing the light carries a
///   lit ridge, the other a shadow, each over part of the plane.
/// - End: most pulls lift off in a lip with a few strands dragged past it;
///   some run out of paint (dry) and break into streaks that end at
///   different places, the ground's tooth showing through them (`tooth`, a
///   filter shared by the stroke or the face).
///
/// One light from the upper left lights every pull. With mixing, the plane
/// may streak in another colour of the Score, and a plane of a face (`whole`)
/// may take that colour; along a line a whole pull of another colour reads as
/// a dash, so a line only streaks.
#[allow(clippy::too_many_arguments)]
fn knife_pull(
    spine: &[(Point, f64)],
    color: &str,
    seed: Seed,
    order: i64,
    unit: f64,
    whole: bool,
    tooth: &str,
) -> Element {
    let mut mark = Element::new("g").attr("class", "proto-knife-mark");
    let count = spine.len();
    if count < 2 {
        return mark;
    }
    let mut lengths = vec![0.0];
    for pair in spine.windows(2) {
        let step = (pair[1].0.x - pair[0].0.x).dhypot(pair[1].0.y - pair[0].0.y);
        lengths.push(lengths.last().copied().unwrap_or(0.0) + step);
    }
    let length = lengths.last().copied().unwrap_or(0.0).max(1e-9);
    // At `t` (0 to 1) along the pull: the centre, the half width and the
    // direction there.
    let sample = |t: f64| -> (Point, f64, Point) {
        let s = t.clamp(0.0, 1.0) * length;
        let i = lengths
            .partition_point(|value| *value < s)
            .clamp(1, count - 1);
        let (a, b) = (spine[i - 1], spine[i]);
        let span = (lengths[i] - lengths[i - 1]).max(1e-9);
        let f = ((s - lengths[i - 1]) / span).clamp(0.0, 1.0);
        let (dx, dy) = (b.0.x - a.0.x, b.0.y - a.0.y);
        let d = dx.dhypot(dy).max(1e-9);
        (
            Point::new(a.0.x + dx * f, a.0.y + dy * f),
            a.1 + (b.1 - a.1) * f,
            Point::new(dx / d, dy / d),
        )
    };
    // `side` in half widths across the plane (+1 the left side), `ahead`
    // along it in pixels.
    let at = |t: f64, side: f64, ahead: f64| -> Point {
        let (c, half, u) = sample(t);
        Point::new(
            c.x - u.y * half * side + u.x * ahead,
            c.y + u.x * half * side + u.y * ahead,
        )
    };
    let h = |k: i64, salt: &str| hash01(order * 512 + k, seed, salt);
    let (half0, half1) = (sample(0.0).1, sample(1.0).1);
    let middle = sample(0.5).2;
    let towards_light = light();
    // +1 when the plane's left side faces the light; and whether the pull ran
    // towards the light, so that the pile's back slope is turned away from it.
    let lit = if -middle.y * towards_light.x + middle.x * towards_light.y > 0.0 {
        1.0
    } else {
        -1.0
    };
    let towards = middle.x * towards_light.x + middle.y * towards_light.y > 0.0;
    let share = mix_share(Weight::PaintingKnife);
    let other = if share > 0.0 {
        other_color(color, h(0, "pk-mix-pick"))
    } else {
        None
    };
    let mut base = bristle_tone(color, (h(0, "pk-tone") - 0.5) * 0.10);
    if let Some(other) = other.as_deref()
        && whole
        && h(0, "pk-mix") < share
    {
        base = mix(&base, other, 0.55 + 0.35 * h(0, "pk-mix-amount"));
    }
    let dry = h(0, "pk-dry") < 0.4;
    let head = 0.10 + 0.08 * h(0, "pk-head");
    let body_end = if dry {
        0.55 + 0.15 * h(0, "pk-dry-at")
    } else {
        1.0
    };
    // The pile swells the plane a little (less along a line, where every pull
    // would otherwise make a joint); a lifted end narrows a little over its
    // last fifth, where the paint ran out.
    let bulge = if whole { 0.13 } else { 0.06 };
    let swell = |t: f64| 1.0 + bulge * (-((t - head * 0.45) / (head * 0.7)).powi(2)).dexp();
    let thin = |t: f64| {
        if !dry && t > 0.78 {
            1.0 - (t - 0.78) / 0.22 * 0.12
        } else {
            1.0
        }
    };
    let steps = (count * 2).clamp(8, 24);
    let along = |k: usize| body_end * k as f64 / steps as f64;
    let mut outline = Vec::new();
    for k in 0..=steps {
        let t = along(k);
        outline.push(at(
            t,
            (1.0 + (h(k as i64, "pk-wave-l") - 0.5) * 0.12) * swell(t) * thin(t),
            0.0,
        ));
    }
    if dry {
        // A ragged edge across, where the plane gives way to streaks.
        for k in 1..6 {
            let across = 1.0 - 2.0 * f64::from(k) / 6.0;
            outline.push(at(
                body_end + (h(i64::from(k), "pk-dry-edge") - 0.5) * 0.06,
                across,
                0.0,
            ));
        }
    } else {
        // The lifted end: a ragged edge where the paint pulled off the blade.
        for k in 1..5 {
            let across = (1.0 - 2.0 * f64::from(k) / 5.0) * 0.8;
            outline.push(at(
                1.0,
                across,
                (h(i64::from(k), "pk-tooth") - 0.4) * 0.05 * length,
            ));
        }
    }
    for k in (0..=steps).rev() {
        let t = along(k);
        outline.push(at(
            t,
            -(1.0 + (h(k as i64, "pk-wave-r") - 0.5) * 0.12) * swell(t) * thin(t),
            0.0,
        ));
    }
    // The back of the pile, where the blade was set down: a little rounded
    // and uneven.
    for k in 1..6 {
        let angle = -std::f64::consts::FRAC_PI_2 + std::f64::consts::PI * f64::from(k) / 6.0;
        let depth = 0.24 * half0 * (0.6 + 0.8 * h(i64::from(k), "pk-back"));
        outline.push(at(0.0, angle.dsin() * swell(0.0), -angle.dcos() * depth));
    }
    // The paint thins from the pile to the end.
    let thinning = fresh("pk-thin");
    let (from, to) = (at(head, 0.0, 0.0), at(1.0, 0.0, 0.0));
    let mut gradient = Element::new("linearGradient")
        .attr("id", &thinning)
        .attr("gradientUnits", "userSpaceOnUse")
        .attr("x1", n(from.x))
        .attr("y1", n(from.y))
        .attr("x2", n(to.x))
        .attr("y2", n(to.y));
    gradient.push(
        Element::new("stop")
            .attr("offset", "0")
            .attr("stop-color", &base),
    );
    gradient.push(
        Element::new("stop")
            .attr("offset", "1")
            .attr("stop-color", &base)
            .attr(
                "stop-opacity",
                match (whole, dry) {
                    (true, true) => "0.72",
                    (true, false) => "0.8",
                    (false, true) => "0.8",
                    (false, false) => "0.9",
                },
            ),
    );
    let mut defs = Element::new("defs");
    defs.push(gradient);
    mark.push(defs);
    mark.push(path(&closed_d(&outline)).attr("fill", format!("url(#{thinning})")));
    if dry {
        // Run dry: streaks of thinning paint, each ending at its own place,
        // the ground's tooth showing through them.
        let lanes = 5 + (h(0, "pk-lanes") * 5.0) as i64;
        let slot = 1.84 / lanes as f64;
        let mut streaks = Element::new("g")
            .attr("fill", format!("url(#{thinning})"))
            .attr("filter", format!("url(#{tooth})"));
        for k in 0..lanes {
            let across = -0.92 + slot * (k as f64 + 0.5 + (h(k, "pk-lane-at") - 0.5) * 0.5);
            let band = slot * (0.45 + 0.4 * h(k, "pk-lane-w"));
            let (start, end) = (
                body_end - 0.06,
                body_end + (1.0 - body_end) * (0.3 + 0.7 * h(k, "pk-lane-end")),
            );
            let wobble = (0..=6)
                .map(|j| (h(k * 8 + j, "pk-lane-wobble") - 0.5) * 0.06)
                .collect::<Vec<_>>();
            let point = |j: usize, sign: f64| {
                let f = j as f64 / 6.0;
                at(
                    start + (end - start) * f,
                    across + wobble[j] + sign * band * 0.5 * (1.0 - 0.75 * f),
                    0.0,
                )
            };
            let mut lane = (0..=6).map(|j| point(j, 1.0)).collect::<Vec<_>>();
            lane.extend((0..=6).rev().map(|j| point(j, -1.0)));
            streaks.push(path(&closed_d(&lane)));
        }
        mark.push(streaks);
    }
    // The heap where the blade was set down: short lumps of paint, lit on the
    // side facing the light, a few in shadow on the other, and the heap's
    // back edge in shadow when the pull ran towards the light.
    if half0 > unit * 0.004 {
        let lump = |k: i64, salt: &str, side: f64, reach: f64| -> Vec<Point> {
            let from = head * reach * h(k, &format!("{salt}-a"));
            let to = (from + head * (0.35 + 0.5 * h(k, &format!("{salt}-b")))).min(head * 1.15);
            let lean = (h(k, &format!("{salt}-lean")) - 0.5) * 0.12;
            vec![
                at(from, side, 0.0),
                at((from + to) * 0.5, side + lean * 0.5, 0.0),
                at(to, side + lean, 0.0),
            ]
        };
        for k in 0..2 + (h(0, "pk-lumps") * 3.0) as i64 {
            let side = lit * (0.25 + 0.6 * h(k, "pk-lump-side"));
            mark.push(
                polyline_path(&lump(k, "pk-lump", side, 0.9))
                    .attr("stroke", bristle_tone(&base, 0.17))
                    .attr("stroke-width", n(half0 * (0.07 + 0.06 * h(k, "pk-lump-w"))))
                    .attr("stroke-opacity", "0.6"),
            );
        }
        for k in 0..1 + (h(0, "pk-hollows") * 2.0) as i64 {
            let side = -lit * (0.35 + 0.5 * h(k, "pk-hollow-side"));
            mark.push(
                polyline_path(&lump(k, "pk-hollow", side, 0.6))
                    .attr("stroke", bristle_tone(&base, -0.14))
                    .attr(
                        "stroke-width",
                        n(half0 * (0.08 + 0.06 * h(k, "pk-hollow-w"))),
                    )
                    .attr("stroke-opacity", "0.5"),
            );
        }
        if towards {
            let back_edge = (1..6)
                .map(|k| {
                    let angle =
                        -std::f64::consts::FRAC_PI_2 + std::f64::consts::PI * f64::from(k) / 6.0;
                    let depth = 0.24 * half0 * (0.6 + 0.8 * h(i64::from(k), "pk-back"));
                    at(
                        0.0,
                        angle.dsin() * swell(0.0) * 0.9,
                        -angle.dcos() * depth * 0.7,
                    )
                })
                .collect::<Vec<_>>();
            mark.push(
                polyline_path(&back_edge)
                    .attr("stroke", bristle_tone(&base, -0.12))
                    .attr("stroke-width", n(half0 * 0.10))
                    .attr("stroke-opacity", "0.45"),
            );
        }
    }
    let edge = |from: f64, to: f64, side: f64| -> Vec<Point> {
        (0..=8)
            .map(|k| at(from + (to - from) * f64::from(k) / 8.0, side, 0.0))
            .collect()
    };
    // The lit side and the shadowed side, each over only part of the plane.
    let (lit_from, lit_to) = (
        head * 0.8 + 0.15 * h(0, "pk-lit-a"),
        (0.55 + 0.40 * h(0, "pk-lit-b")).min(body_end),
    );
    mark.push(
        polyline_path(&edge(lit_from, lit_to, 0.92 * lit))
            .attr("stroke", bristle_tone(&base, 0.16))
            .attr("stroke-width", n((half0 * 0.14).max(unit * 0.0007)))
            .attr("stroke-opacity", "0.55"),
    );
    let (shade_from, shade_to) = (
        head + 0.2 * h(0, "pk-shade-a"),
        (0.60 + 0.35 * h(0, "pk-shade-b")).min(body_end),
    );
    mark.push(
        polyline_path(&edge(shade_from, shade_to, -0.92 * lit))
            .attr("stroke", bristle_tone(&base, -0.15))
            .attr("stroke-width", n((half0 * 0.18).max(unit * 0.0008)))
            .attr("stroke-opacity", "0.5"),
    );
    // Spread: fine streaks the blade's edge dragged through the thinning
    // paint, from past the pile towards the end.
    if half0 > unit * 0.006 {
        let drags = 3 + (h(0, "pk-drags") * 3.0) as i64;
        for k in 0..drags {
            let across = (h(k, "pk-drag-side") - 0.5) * 1.5;
            let from = head + 0.02 + 0.10 * h(k, "pk-drag-a");
            let to = (0.65 + 0.33 * h(k, "pk-drag-b")).min(body_end);
            if to <= from + 0.05 {
                continue;
            }
            let points = (0..=6)
                .map(|j| {
                    let t = from + (to - from) * f64::from(j) / 6.0;
                    at(
                        t,
                        across + (h(k * 8 + i64::from(j), "pk-drag-j") - 0.5) * 0.05,
                        0.0,
                    )
                })
                .collect::<Vec<_>>();
            mark.push(
                polyline_path(&points)
                    .attr(
                        "stroke",
                        bristle_tone(&base, if k % 2 == 0 { 0.08 } else { -0.08 }),
                    )
                    .attr(
                        "stroke-width",
                        n(half0 * (0.025 + 0.035 * h(k, "pk-drag-w"))),
                    )
                    .attr("stroke-opacity", n(0.22 + 0.13 * h(k, "pk-drag-o"))),
            );
        }
    }
    if !dry {
        // The lip across the end: lit above, its shadow just past it.
        let end_direction = sample(1.0).2;
        let lip_at = 0.80 + 0.06 * h(0, "pk-lip");
        let lip = (0..=4)
            .map(|k| {
                let across = 0.85 - 1.7 * f64::from(k) / 4.0;
                at(
                    lip_at + (h(i64::from(k), "pk-lip-j") - 0.5) * 0.04,
                    across,
                    0.0,
                )
            })
            .collect::<Vec<_>>();
        mark.push(
            polyline_path(&lip)
                .attr("stroke", bristle_tone(&base, 0.15))
                .attr("stroke-width", n((half1 * 0.14).max(unit * 0.0007)))
                .attr("stroke-opacity", "0.65"),
        );
        let lip_shadow = lip
            .iter()
            .map(|p| {
                Point::new(
                    p.x + end_direction.x * half1 * 0.16,
                    p.y + end_direction.y * half1 * 0.16,
                )
            })
            .collect::<Vec<_>>();
        mark.push(
            polyline_path(&lip_shadow)
                .attr("stroke", bristle_tone(&base, -0.14))
                .attr("stroke-width", n((half1 * 0.12).max(unit * 0.0007)))
                .attr("stroke-opacity", "0.4"),
        );
        // Strands dragged past the end as the blade came away.
        let strands = 2 + (h(0, "pk-strands") * 3.0) as i64;
        for k in 0..strands {
            let across = (h(k, "pk-strand-side") - 0.5) * 1.4;
            let reach = length * (0.04 + 0.12 * h(k, "pk-strand-reach"));
            let drift = (h(k, "pk-strand-drift") - 0.5) * half1 * 0.3;
            let start = at(0.92, across, 0.0);
            let end = Point::new(
                start.x + end_direction.x * reach - end_direction.y * drift,
                start.y + end_direction.y * reach + end_direction.x * drift,
            );
            mark.push(
                polyline_path(&[start, end])
                    .attr("stroke", bristle_tone(&base, -0.04))
                    .attr(
                        "stroke-width",
                        n(half1 * (0.05 + 0.06 * h(k, "pk-strand-w"))),
                    )
                    .attr("stroke-opacity", n(0.45 - 0.25 * h(k, "pk-strand-o"))),
            );
        }
    }
    // Another colour caught on the blade: a streak of it along the plane.
    if let Some(other) = other.as_deref()
        && h(1, "pk-mix-streak") < share
    {
        let across = (h(2, "pk-mix-side") - 0.5) * 1.2;
        let (from, to) = (
            0.08 + 0.2 * h(3, "pk-mix-a"),
            (0.6 + 0.3 * h(4, "pk-mix-b")).min(body_end),
        );
        mark.push(
            polyline_path(&edge(from, to, across))
                .attr("stroke", mix(other, &base, 0.2))
                .attr("stroke-width", n(half0 * (0.12 + 0.12 * h(5, "pk-mix-w"))))
                .attr("stroke-opacity", "0.75"),
        );
    }
    mark
}

fn knife_stroke(
    left: &[Point],
    right: &[Point],
    closed: bool,
    color: &str,
    seed: Seed,
    unit: f64,
) -> Element {
    let centre = left
        .iter()
        .zip(right)
        .map(|(l, r)| {
            (
                Point::new((l.x + r.x) * 0.5, (l.y + r.y) * 0.5),
                (l.x - r.x).dhypot(l.y - r.y),
            )
        })
        .collect::<Vec<_>>();
    let mut group = Element::new("g").attr("class", "proto-knife-stroke");
    if centre.len() < 2 {
        return group;
    }
    let mut cumulative = vec![0.0];
    for pair in centre.windows(2) {
        let step = (pair[1].0.x - pair[0].0.x).dhypot(pair[1].0.y - pair[0].0.y);
        cumulative.push(cumulative.last().copied().unwrap_or(0.0) + step);
    }
    let total = cumulative.last().copied().unwrap_or(0.0);
    let width = mean_width(left, right).max(unit * 0.002);
    // One pull of the blade runs about fourteen of its widths and bends with
    // the line, but no pull turns much more than 45 degrees.
    let turning = centre
        .windows(3)
        .map(|w| {
            let a = (w[1].0.y - w[0].0.y).datan2(w[1].0.x - w[0].0.x);
            let b = (w[2].0.y - w[1].0.y).datan2(w[2].0.x - w[1].0.x);
            let mut turn = (b - a).abs();
            if turn > std::f64::consts::PI {
                turn = 2.0 * std::f64::consts::PI - turn;
            }
            turn
        })
        .sum::<f64>()
        .to_degrees();
    let pulls = (turning / 45.0).max(1.0);
    let pull_length = (width * 14.0).max(unit * 0.08).min(total / pulls);
    let at = |s: f64| -> (Point, f64) {
        let s = s.clamp(0.0, total);
        let index = cumulative
            .partition_point(|value| *value < s)
            .clamp(1, centre.len() - 1);
        let (a, b) = (centre[index - 1], centre[index]);
        let span = (cumulative[index] - cumulative[index - 1]).max(1e-9);
        let t = (s - cumulative[index - 1]) / span;
        (
            Point::new(a.0.x + (b.0.x - a.0.x) * t, a.0.y + (b.0.y - a.0.y) * t),
            a.1 + (b.1 - a.1) * t,
        )
    };
    let tooth = fresh("pk-tooth");
    let mut defs = Element::new("defs");
    defs.push(local_tooth_filter(
        &tooth,
        260.0 / unit.max(1.0),
        0.28,
        &noise_seed(seed, "pk-tooth"),
    ));
    group.push(defs);
    let mut start = 0.0;
    let mut order = 0_i64;
    let _ = closed;
    while start < total {
        let length = pull_length * (0.8 + 0.4 * hash01(order, seed, "knife-length"));
        let end = (start + length).min(total);
        let (p0, _) = at(start);
        let (p1, _) = at(end);
        let (dx, dy) = (p1.x - p0.x, p1.y - p0.y);
        let len = dx.dhypot(dy).max(1e-9);
        let shift = (hash01(order, seed, "knife-shift") - 0.5) * 0.25 * width;
        let (w0, w1) = (
            0.92 + 0.16 * hash01(order, seed, "knife-w0"),
            0.85 + 0.16 * hash01(order, seed, "knife-w1"),
        );
        let samples = ((end - start) / (width * 0.8)).ceil().clamp(4.0, 16.0) as usize;
        let spine = (0..=samples)
            .map(|k| {
                let f = k as f64 / samples as f64;
                let (p, w) = at(start + (end - start) * f);
                (
                    Point::new(p.x - dy / len * shift, p.y + dx / len * shift),
                    0.5 * w.max(width * 0.7) * (w0 + (w1 - w0) * f),
                )
            })
            .collect::<Vec<_>>();
        group.push(knife_pull(&spine, color, seed, order, unit, false, &tooth));
        // Pulls overlap a little where the knife was set down again.
        start = end - (end - start) * 0.12;
        if end >= total {
            break;
        }
        order += 1;
    }
    group
}

// ---------------------------------------------------------------------------
// Flat fills of closed shapes (塗り).

/// The face of a closed shape (pixels). `stroke_width` is the tool's width.
pub(crate) fn fill(
    weight: Weight,
    contour: &[Point],
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
    stroke_width: f64,
) -> Element {
    match weight {
        Weight::Watercolor => watercolor_fill(contour, color, opacity, seed, unit),
        Weight::OilPastel => oil_pastel_fill(contour, color, seed, unit, stroke_width),
        Weight::PaintingKnife => knife_fill(contour, color, seed, unit),
        Weight::Etching => etching_fill(contour, color, opacity, seed, unit, stroke_width),
        other => {
            debug_assert!(!owns(other), "every medium lays its own face");
            Element::new("g")
        }
    }
}

fn watercolor_fill(contour: &[Point], color: &str, opacity: f64, seed: Seed, unit: f64) -> Element {
    let d = closed_d(contour);
    let (x0, y0, x1, y1) = bounds(contour);
    let size = (x1 - x0).min(y1 - y0).max(1.0);
    let (wash, clip, rim_blur, wobble) = (
        fresh("wc-wash"),
        fresh("wc-clip"),
        fresh("wc-rim"),
        fresh("wc-wobble"),
    );
    let mut defs = Element::new("defs");
    defs.push(wash_filter(
        &wash,
        seed,
        unit,
        size * 0.32,
        Region::around(contour, 0.0, unit),
    ));
    let mut clip_path = Element::new("clipPath").attr("id", &clip);
    clip_path.push(path(&d));
    defs.push(clip_path);
    // The rim's stroke (half of size * 0.08) and the blur's reach.
    defs.push(blur_filter(
        &rim_blur,
        size * 0.022,
        Region::around(contour, size * 0.04 + blur_reach(size * 0.022), unit),
    ));
    // The edge's wobble, with the look of the Server's PNG (`Displacement`).
    // Everything in the group is kept inside the shape; the wobble moves it by
    // the displacement's reach at most.
    let shake = Displacement::of_scale(size * 0.03);
    let mut wobble_filter = filter(&wobble, Region::around(contour, shake.reach(), unit));
    wobble_filter.push(turbulence(
        1.0 / (size * 0.12),
        2,
        &noise_seed(seed, "wc-wobble"),
        "edge",
    ));
    for primitive in shake.primitives("SourceGraphic", "edge", "wobbled") {
        wobble_filter.push(primitive);
    }
    defs.push(wobble_filter);
    let mut group = Element::new("g")
        .attr("class", "media-watercolor-wash")
        .attr("filter", format!("url(#{wobble})"));
    group.push(defs);
    group.push(
        path(&d)
            .attr("fill", color)
            .attr("fill-opacity", n((opacity * 0.62).min(0.62)))
            .attr("filter", format!("url(#{wash})")),
    );
    // Pigment carried to the edge as the wash dried: darker just inside the
    // edge, fading inwards. Drawn as a blurred ring kept inside the shape.
    let mut rim = Element::new("g").attr("clip-path", format!("url(#{clip})"));
    rim.push(
        path(&d)
            .attr("fill", "none")
            .attr("stroke", bristle_tone(color, -0.08))
            .attr("stroke-width", n(size * 0.08))
            .attr("stroke-opacity", n((opacity * 0.75).min(0.7)))
            .attr("filter", format!("url(#{rim_blur})")),
    );
    group.push(rim);
    // Colour mixing: the pigment that dried at the edge separated into
    // another colour of the Score along a share of it, in three runs of
    // uneven length, and pale blooms of that colour drift inside the wash.
    let share = mix_share(Weight::Watercolor);
    if share > 0.0
        && let Some(other) = other_color(color, hash01(0, seed, "wc-mix-pick"))
    {
        let perimeter = contour
            .iter()
            .zip(contour.iter().cycle().skip(1))
            .map(|(a, b)| (b.x - a.x).dhypot(b.y - a.y))
            .sum::<f64>();
        let part = (share * 1.5).min(0.6);
        let runs = [0_i64, 1, 2].map(|k| 0.4 + hash01(k, seed, "wc-mix-run"));
        let gaps = [0_i64, 1, 2].map(|k| 0.4 + hash01(k, seed, "wc-mix-gap"));
        let (run_sum, gap_sum) = (runs.iter().sum::<f64>(), gaps.iter().sum::<f64>());
        let dashes = (0..3)
            .flat_map(|k| {
                [
                    n(perimeter * part * runs[k] / run_sum),
                    n(perimeter * (1.0 - part) * gaps[k] / gap_sum),
                ]
            })
            .collect::<Vec<_>>()
            .join(" ");
        let soft = fresh("wc-mix-soft");
        let mut mix_defs = Element::new("defs");
        // The blooms are kept inside the shape: what reaches it lies
        // within the blur's reach of its box.
        mix_defs.push(blur_filter(
            &soft,
            size * 0.05,
            Region::around(contour, blur_reach(size * 0.05), unit),
        ));
        group.push(mix_defs);
        let mut parted = Element::new("g").attr("clip-path", format!("url(#{clip})"));
        parted.push(
            path(&d)
                .attr("fill", "none")
                .attr("stroke", mix(&other, color, 0.35))
                .attr("stroke-width", n(size * 0.08))
                .attr("stroke-opacity", n((opacity * 0.75).min(0.7)))
                .attr("stroke-dasharray", dashes)
                .attr(
                    "stroke-dashoffset",
                    n(perimeter * hash01(0, seed, "wc-mix-offset")),
                )
                .attr("filter", format!("url(#{rim_blur})")),
        );
        for k in 0..(share * 10.0).ceil() as i64 {
            let Some(bloom) = other_color(color, hash01(k, seed, "wc-bloom-pick")) else {
                continue;
            };
            let rx = size * (0.10 + 0.12 * hash01(k, seed, "wc-bloom-rx"));
            parted.push(
                Element::new("ellipse")
                    .attr(
                        "cx",
                        n(x0 + (x1 - x0) * (0.15 + 0.7 * hash01(k, seed, "wc-bloom-x"))),
                    )
                    .attr(
                        "cy",
                        n(y0 + (y1 - y0) * (0.15 + 0.7 * hash01(k, seed, "wc-bloom-y"))),
                    )
                    .attr("rx", n(rx))
                    .attr("ry", n(rx * (0.6 + 0.4 * hash01(k, seed, "wc-bloom-ry"))))
                    .attr("fill", bloom)
                    .attr(
                        "fill-opacity",
                        n(opacity * (0.18 + 0.12 * hash01(k, seed, "wc-bloom-o"))),
                    )
                    .attr("filter", format!("url(#{soft})")),
            );
        }
        group.push(parted);
    }
    group
}

fn oil_pastel_fill(
    contour: &[Point],
    color: &str,
    seed: Seed,
    unit: f64,
    stroke_width: f64,
) -> Element {
    let d = closed_d(contour);
    let (x0, y0, x1, y1) = bounds(contour);
    let size = (x1 - x0).min(y1 - y0).max(1.0);
    let width = (stroke_width * 1.5).max(size / 9.0).max(unit * 0.006);
    let frequency = 300.0 / unit.max(1.0);
    let (clip, base_tooth, stroke_tooth) =
        (fresh("op-clip"), fresh("op-base"), fresh("op-strokes"));
    let mut defs = Element::new("defs");
    let mut clip_path = Element::new("clipPath").attr("id", &clip);
    clip_path.push(path(&d));
    defs.push(clip_path);
    // The face is clipped to the shape, so only what lies within its box (and
    // the roughening's reach around it) is seen.
    let rough = Displacement::of_scale(unit * 0.0015);
    defs.push(tooth_filter(
        &base_tooth,
        frequency,
        0.18,
        &noise_seed(seed, "op-base"),
        None,
        Region::around(contour, 0.0, unit),
    ));
    defs.push(tooth_filter(
        &stroke_tooth,
        frequency,
        0.14,
        &noise_seed(seed, "op-strokes"),
        Some(rough),
        Region::around(contour, rough.reach(), unit),
    ));
    let mut group = Element::new("g").attr("class", "proto-oil-pastel-face");
    group.push(defs);
    let mut face = Element::new("g").attr("clip-path", format!("url(#{clip})"));
    // Colour mixing: patches of the Score's other colours laid first, showing
    // through the tooth and between the strokes; a share of the strokes lean
    // to another colour (below). None: the author's choice.
    let share = mix_share(Weight::OilPastel);
    if share > 0.0 {
        let patches = (5.0 * share * (x1 - x0) * (y1 - y0) / (width * width * 4.0)).ceil() as i64;
        for k in 0..patches.min(400) {
            if let Some(other) = other_color(color, hash01(k, seed, "op-under-pick")) {
                face.push(
                    Element::new("ellipse")
                        .attr("cx", n(x0 + (x1 - x0) * hash01(k, seed, "op-under-x")))
                        .attr("cy", n(y0 + (y1 - y0) * hash01(k, seed, "op-under-y")))
                        .attr(
                            "rx",
                            n(width * (0.8 + 1.2 * hash01(k, seed, "op-under-rx"))),
                        )
                        .attr(
                            "ry",
                            n(width * (0.5 + 0.7 * hash01(k, seed, "op-under-ry"))),
                        )
                        .attr("fill", mix(&other, color, 0.2)),
                );
            }
        }
    }
    face.push(
        path(&d)
            .attr("fill", color)
            .attr("filter", format!("url(#{base_tooth})")),
    );
    // Short, slightly bent strokes, scattered over the face; their direction
    // turns slowly across it, so no line of strokes runs straight through.
    let base = (hash01(0, seed, "op-angle") - 0.5) * 1.2 - 0.6;
    let (phase_x, phase_y) = (
        hash01(0, seed, "op-field-x") * std::f64::consts::TAU,
        hash01(0, seed, "op-field-y") * std::f64::consts::TAU,
    );
    let spacing = width * 0.85;
    let columns = ((x1 - x0) / spacing).ceil() as i64 + 2;
    let rows = ((y1 - y0) / spacing).ceil() as i64 + 2;
    let mut marks = Vec::new();
    for row in -1..rows {
        for column in -1..columns {
            let i = row * 10_000 + column;
            let cx = x0 + (column as f64 + 0.5 + (hash01(i, seed, "op-jx") - 0.5) * 0.9) * spacing;
            let cy = y0 + (row as f64 + 0.5 + (hash01(i, seed, "op-jy") - 0.5) * 0.9) * spacing;
            let field = 0.55 * ((cx - x0) / size * 2.4 + phase_x).dsin()
                + 0.45 * ((cy - y0) / size * 2.1 + phase_y).dcos();
            let angle = base + field * 0.7 + (hash01(i, seed, "op-ja") - 0.5) * 0.35;
            let length = width * (2.2 + 2.0 * hash01(i, seed, "op-len"));
            let bend = (hash01(i, seed, "op-bend") - 0.5) * 0.5 * length;
            let (sin, cos) = angle.dsin_cos();
            let a = Point::new(cx - cos * length * 0.5, cy - sin * length * 0.5);
            let b = Point::new(cx + cos * length * 0.5, cy + sin * length * 0.5);
            let control = Point::new(cx - sin * bend, cy + cos * bend);
            marks.push((hash01(i, seed, "op-order"), a, control, b, i));
        }
    }
    marks.sort_by(|p, q| p.0.total_cmp(&q.0));
    let mut strokes = Element::new("g").attr("filter", format!("url(#{stroke_tooth})"));
    for (_, a, control, b, i) in marks {
        let pigment = if share > 0.0 && hash01(i, seed, "op-mix") < share {
            other_color(color, hash01(i, seed, "op-mix-pick")).map_or_else(
                || color.to_owned(),
                |other| mix(color, &other, 0.35 + 0.3 * hash01(i, seed, "op-mix-amount")),
            )
        } else {
            color.to_owned()
        };
        strokes.push(
            path(&format!(
                "M {} {} Q {} {} {} {}",
                n(a.x),
                n(a.y),
                n(control.x),
                n(control.y),
                n(b.x),
                n(b.y)
            ))
            .attr("fill", "none")
            .attr(
                "stroke",
                bristle_tone(&pigment, (hash01(i, seed, "op-tone") - 0.5) * 0.10),
            )
            .attr(
                "stroke-width",
                n(width * (0.7 + 0.25 * hash01(i, seed, "op-width"))),
            )
            .attr("stroke-linecap", "round"),
        );
    }
    face.push(strokes);
    group.push(face);
    group
}

fn knife_fill(contour: &[Point], color: &str, seed: Seed, unit: f64) -> Element {
    let d = closed_d(contour);
    let (x0, y0, x1, y1) = bounds(contour);
    let size = (x1 - x0).min(y1 - y0).max(1.0);
    let cell = (size / 2.5).max(unit * 0.03);
    let (clip, tooth) = (fresh("pk-clip"), fresh("pk-tooth"));
    let mut defs = Element::new("defs");
    let mut clip_path = Element::new("clipPath").attr("id", &clip);
    clip_path.push(path(&d));
    defs.push(clip_path);
    defs.push(local_tooth_filter(
        &tooth,
        260.0 / unit.max(1.0),
        0.28,
        &noise_seed(seed, "pk-tooth"),
    ));
    let mut group = Element::new("g").attr("class", "proto-knife-face");
    group.push(defs);
    let mut face = Element::new("g").attr("clip-path", format!("url(#{clip})"));
    // A thin, darker first layer: what shows between the planes.
    face.push(
        path(&d)
            .attr("fill", bristle_tone(color, -0.06))
            .attr("fill-opacity", "0.8"),
    );
    // With mixing, patches of the Score's other colours lie under the planes
    // and show between them.
    let share = mix_share(Weight::PaintingKnife);
    if share > 0.0 {
        let patches = (6.0 * share * ((x1 - x0) * (y1 - y0)) / (cell * cell)).ceil() as i64;
        for k in 0..patches {
            if let Some(other) = other_color(color, hash01(k, seed, "pk-under-pick")) {
                face.push(
                    Element::new("ellipse")
                        .attr("cx", n(x0 + (x1 - x0) * hash01(k, seed, "pk-under-x")))
                        .attr("cy", n(y0 + (y1 - y0) * hash01(k, seed, "pk-under-y")))
                        .attr("rx", n(cell * (0.4 + 0.5 * hash01(k, seed, "pk-under-rx"))))
                        .attr(
                            "ry",
                            n(cell * (0.25 + 0.3 * hash01(k, seed, "pk-under-ry"))),
                        )
                        .attr("fill", mix(&other, color, 0.25))
                        .attr("fill-opacity", "0.7"),
                );
            }
        }
    }
    // Long planes laid in no grid: placed loosely, of mixed size, turned with
    // a direction that drifts across the face, each a little bent; the broad
    // ones first, the small ones over them.
    let base = hash01(0, seed, "pk-base") * std::f64::consts::PI;
    let (phase_x, phase_y) = (
        hash01(0, seed, "pk-field-x") * std::f64::consts::TAU,
        hash01(0, seed, "pk-field-y") * std::f64::consts::TAU,
    );
    let spacing = cell * 0.78;
    let mut planes = Vec::new();
    let columns = ((x1 - x0) / spacing).ceil() as i64 + 2;
    let rows = ((y1 - y0) / spacing).ceil() as i64 + 2;
    for row in -1..rows {
        for column in -1..columns {
            let i = row * 1_000 + column;
            if hash01(i, seed, "pk-skip") < 0.04 {
                continue;
            }
            let centre = Point::new(
                x0 + (column as f64 + 0.5 + (hash01(i, seed, "pk-jx") - 0.5) * 0.8) * spacing,
                y0 + (row as f64 + 0.5 + (hash01(i, seed, "pk-jy") - 0.5) * 0.8) * spacing,
            );
            let field = 0.6 * ((centre.x - x0) / size * 2.2 + phase_x).dsin()
                + 0.4 * ((centre.y - y0) / size * 1.9 + phase_y).dcos();
            let angle = base + field * 0.8 + (hash01(i, seed, "pk-angle") - 0.5) * 0.5;
            let scale = 0.8 + 0.45 * hash01(i, seed, "pk-scale");
            let breadth = cell * (0.55 + 0.25 * hash01(i, seed, "pk-breadth")) * scale;
            let length = breadth * (2.4 + 1.2 * hash01(i, seed, "pk-len"));
            let bend = (hash01(i, seed, "pk-bend") - 0.5) * 0.18 * length;
            let (sin, cos) = angle.dsin_cos();
            let p0 = Point::new(centre.x - cos * length * 0.5, centre.y - sin * length * 0.5);
            let p1 = Point::new(centre.x + cos * length * 0.5, centre.y + sin * length * 0.5);
            let control = Point::new(centre.x - sin * bend * 2.0, centre.y + cos * bend * 2.0);
            let (half0, half1) = (
                breadth * 0.5 * 1.05,
                breadth * 0.5 * (0.8 + 0.15 * hash01(i, seed, "pk-taper")),
            );
            let spine = (0..=8)
                .map(|k| {
                    let t = f64::from(k) / 8.0;
                    let (a, b, c) = ((1.0 - t) * (1.0 - t), 2.0 * (1.0 - t) * t, t * t);
                    (
                        Point::new(
                            a * p0.x + b * control.x + c * p1.x,
                            a * p0.y + b * control.y + c * p1.y,
                        ),
                        half0 + (half1 - half0) * t,
                    )
                })
                .collect::<Vec<_>>();
            planes.push((scale, hash01(i, seed, "pk-order"), spine, i));
        }
    }
    planes.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.total_cmp(&b.1)));
    for (_, _, spine, i) in planes {
        face.push(knife_pull(&spine, color, seed, i, unit, true, &tooth));
    }
    group.push(face);
    group
}

/// How the acid bites a line of `width`: the displacement of scale
/// `width * 0.45` with the look of the Server's PNG (`Displacement`).
fn bite(width: f64) -> Displacement {
    Displacement::of_scale(width * 0.45)
}

/// The acid's bite: an etched line's edge wavers a little at a fine grain.
/// `region` holds the line and the bite's reach.
fn bite_filter(id: &str, width: f64, seed: Seed, region: Region) -> Element {
    let mut f = filter(id, region);
    f.push(turbulence(
        1.0 / (width * 0.9).max(0.3),
        2,
        &noise_seed(seed, "et-bite"),
        "bite",
    ));
    for primitive in bite(width).primitives("SourceGraphic", "bite", "bitten") {
        f.push(primitive);
    }
    f
}

/// An etched line: the needle's line bitten into the plate, so even in
/// width, its edge a little ragged where the acid ate under the ground, its
/// ends round; now and then a pit of foul biting beside it.
fn etching_stroke(
    left: &[Point],
    right: &[Point],
    closed: bool,
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
) -> Element {
    let centre = left
        .iter()
        .zip(right)
        .map(|(l, r)| Point::new((l.x + r.x) * 0.5, (l.y + r.y) * 0.5))
        .collect::<Vec<_>>();
    let mut group = Element::new("g").attr("class", "proto-etching-stroke");
    if centre.len() < 2 {
        return group;
    }
    let mut width = mean_width(left, right).max(unit * 0.0006);
    let mut opacity = opacity;
    {
        // Each line bitten to its own depth, a deeper line wider and darker.
        // The Score gives a layer's lines one seed, so the line's place picks.
        let (first, last) = (centre[0], centre[centre.len() - 1]);
        let key = (first.x * 7.31 + first.y * 13.17 + last.x * 3.11 + last.y * 5.03) as i64;
        let depth = hash01(key, seed, "et-depth");
        width *= 0.72 + 0.62 * depth;
        opacity = (opacity * (0.82 + 0.18 * depth)).min(1.0);
    }
    let bitten = fresh("et-bite");
    let mut defs = Element::new("defs");
    // The line reaches half its width past the centre line (round caps and
    // joins), and the bite moves it by the displacement's reach at most.
    let region = Region::around(&centre, width * 0.5 + bite(width).reach(), unit);
    defs.push(bite_filter(&bitten, width, seed, region));
    group.push(defs);
    let mut line = polyline_path(&centre);
    if closed {
        let mut d = String::new();
        for (index, point) in centre.iter().enumerate() {
            d.push_str(if index == 0 { "M " } else { " L " });
            d.push_str(&n(point.x));
            d.push(' ');
            d.push_str(&n(point.y));
        }
        d.push_str(" Z");
        line = path(&d)
            .attr("fill", "none")
            .attr("stroke-linecap", "round")
            .attr("stroke-linejoin", "round");
    }
    group.push(
        line.attr("stroke", color)
            .attr("stroke-width", n(width))
            .attr("stroke-opacity", n(opacity))
            .attr("filter", format!("url(#{bitten})")),
    );
    // Pits of foul biting: a few dots beside the line.
    let gap = |k: i64, salt: &str| width * 18.0 * (0.5 + hash01(k, seed, salt));
    let (mut walked, mut next, mut order) = (0.0, gap(0, "et-pit-first"), 0_i64);
    for pair in centre.windows(2) {
        let (a, b) = (pair[0], pair[1]);
        let step = (b.x - a.x).dhypot(b.y - a.y).max(1e-9);
        while walked + step >= next {
            let t = (next - walked) / step;
            if hash01(order, seed, "et-pit") < 0.45 {
                let side = if hash01(order, seed, "et-pit-side") < 0.5 {
                    -1.0
                } else {
                    1.0
                };
                let off = width * (0.9 + 1.4 * hash01(order, seed, "et-pit-off")) * side;
                group.push(
                    Element::new("circle")
                        .attr("cx", n(a.x + (b.x - a.x) * t - (b.y - a.y) / step * off))
                        .attr("cy", n(a.y + (b.y - a.y) * t + (b.x - a.x) / step * off))
                        .attr(
                            "r",
                            n(width * (0.12 + 0.18 * hash01(order, seed, "et-pit-r"))),
                        )
                        .attr("fill", color)
                        .attr("fill-opacity", n(opacity * 0.55)),
                );
            }
            order += 1;
            next += gap(order, "et-pit-gap");
        }
        walked += step;
    }
    group
}

/// An etched face: the needle's lines hatched across it, with light and dark
/// (below; the author found a face of even parallel lines monotonous).
fn etching_fill(
    contour: &[Point],
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
    stroke_width: f64,
) -> Element {
    etching_fill_varied(contour, color, opacity, seed, unit, stroke_width)
}

/// An etched face with light and dark (てざわりの整理 step 6). Each face is
/// hatched at its own angle and spacing (a layer's faces share one seed, so
/// the face's place picks them) and each line is bitten to its own depth.
/// The lines grow heavier towards one side of the face, away from the light
/// for a dark ink, towards it for a pale ink on a dark ground, and are
/// crossed only on that side.
fn etching_fill_varied(
    contour: &[Point],
    color: &str,
    opacity: f64,
    seed: Seed,
    unit: f64,
    stroke_width: f64,
) -> Element {
    let d = closed_d(contour);
    let (x0, y0, x1, y1) = bounds(contour);
    let centre = Point::new((x0 + x1) * 0.5, (y0 + y1) * 0.5);
    let key = (centre.x * 3.7 + centre.y * 11.3) as i64;
    let line = (stroke_width * 0.55).max(unit * 0.0009);
    let spacing = line
        * if opacity < 0.7 { 3.9 } else { 2.6 }
        * (0.9 + 0.25 * hash01(key, seed, "et-face-spacing"));
    let angle = std::f64::consts::PI * hash01(key, seed, "et-face-angle");
    let towards_light = light();
    let heavy = if lightness(color) > 0.6 {
        towards_light
    } else {
        Point::new(-towards_light.x, -towards_light.y)
    };
    let reach = ((x1 - x0) * heavy.x.abs() + (y1 - y0) * heavy.y.abs()).max(1.0) * 0.5;
    let weight = |p: Point| -> f64 {
        (((p.x - centre.x) * heavy.x + (p.y - centre.y) * heavy.y) / reach * 0.5 + 0.5)
            .clamp(0.0, 1.0)
    };
    let (clip, bitten) = (fresh("et-clip"), fresh("et-fill-bite"));
    let mut defs = Element::new("defs");
    let mut clip_path = Element::new("clipPath").attr("id", &clip);
    clip_path.push(path(&d));
    defs.push(clip_path);
    // The face is clipped to the shape after the bite: what is seen lies in
    // its box, and the bite pulls from the displacement's reach away at most.
    defs.push(bite_filter(
        &bitten,
        line,
        seed,
        Region::around(contour, line * 1.5 + bite(line).reach(), unit),
    ));
    let mut group = Element::new("g").attr("class", "proto-etching-face");
    group.push(defs);
    let mut face = Element::new("g")
        .attr("clip-path", format!("url(#{clip})"))
        .attr("filter", format!("url(#{bitten})"))
        .attr("fill", color)
        .attr("fill-opacity", n(opacity.min(1.0)));
    let sets: &[(f64, bool)] = if opacity >= 0.7 {
        &[(0.0, false), (1.15, true)]
    } else {
        &[(0.0, false)]
    };
    for (set, (turn, crossing)) in sets.iter().enumerate() {
        let gap = spacing * if *crossing { 1.1 } else { 1.0 };
        let phase = hash01(key + set as i64, seed, "et-face-phase");
        for (index, (a, b)) in scan_segments(contour, angle + turn, gap, phase)
            .iter()
            .enumerate()
        {
            let i = key
                .wrapping_mul(31)
                .wrapping_add((set * 100_000 + index) as i64);
            let depth = 0.85 + 0.3 * hash01(i, seed, "et-line-depth");
            let lean = (hash01(i, seed, "et-lean") - 0.5) * line * 1.2;
            let (dx, dy) = (b.x - a.x, b.y - a.y);
            let len = dx.dhypot(dy).max(1e-9);
            let (nx, ny) = (-dy / len, dx / len);
            let count = ((len / (line * 8.0)).ceil() as usize).clamp(2, 24);
            let (mut near, mut far) =
                (Vec::with_capacity(count + 1), Vec::with_capacity(count + 1));
            let mut widest = 0.0_f64;
            for k in 0..=count {
                let f = k as f64 / count as f64;
                let bow = lean * 4.0 * f * (1.0 - f);
                let p = Point::new(a.x + dx * f + nx * bow, a.y + dy * f + ny * bow);
                let s = weight(p);
                let mut half = 0.5 * line * depth * (0.45 + s.dpowf(1.2));
                if *crossing {
                    let t = ((s - 0.5) / 0.4).clamp(0.0, 1.0);
                    half *= t * t * (3.0 - 2.0 * t);
                }
                widest = widest.max(half);
                near.push(Point::new(p.x + nx * half, p.y + ny * half));
                far.push(Point::new(p.x - nx * half, p.y - ny * half));
            }
            if widest < line * 0.04 {
                continue;
            }
            near.extend(far.into_iter().rev());
            face.push(path(&closed_d(&near)));
        }
    }
    group.push(face);
    group
}
