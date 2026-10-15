//! Deterministic builders for named physical supports.
//!
//! A support is drawn in three parts: the tone of the material itself (only the toned grounds),
//! a broad layer of soft lighter and darker shapes drawn once over the whole canvas, and fine
//! textures laid as tiles. The broad layer is never tiled, so it cannot repeat. Each texture is
//! split over several tiles whose sizes never line up on the canvas (and dots' tiles are turned
//! to different angles), so no one tile's repeat stands out. Every mark says how many L* it moves
//! the support under it, and its ink and opacity follow from that support's lightness, so a
//! texture stays visible on a dark background.

use inku_score::{shown_support, srgb_channels};

use crate::determinism::hash01;
use crate::svg::{Element, format_number};
use crate::types::{CanvasGroundSpec, CanvasSize, GroundGrain, GroundMaterial, Seed};

const GROUND_MM: f64 = 1000.0 / 210.0;
const GROUND_DENSITY_DEFAULT: f64 = 0.20;
const GROUND_OPACITY_DEFAULT: f64 = 0.12;
/// How strongly the broad layer and the textures move the lightness. The author chose 0.6 of
/// the first prototype's steps on the comparison sheet (2026-10-15).
const GROUND_STRENGTH: f64 = 0.6;
/// How far the mezzotint's burnish and rocker marks lift the plate. At 1.0 the plate's grain
/// was hard to see; the author chose 1.5 (2026-10-15).
const MEZZOTINT_LIFT: f64 = 1.5;
/// A darker mark needs a support at least this light; a paler one, at most this light.
const DARKEST_SUPPORT: f64 = 18.0;
const LIGHTEST_SUPPORT: f64 = 88.0;
const SOFT_DARK: &str = "ground_soft_dark";
const SOFT_LIGHT: &str = "ground_soft_light";
const RING_DARK: &str = "ground_ring_dark";
const RING_LIGHT: &str = "ground_ring_light";

#[derive(Clone)]
pub(crate) struct GroundLayer {
    pub(crate) width: f64,
    pub(crate) height: f64,
    pub(crate) rotation: f64,
    pub(crate) body: Vec<Element>,
}

pub(crate) struct GroundPlan {
    /// The material's own tone over the background: colour and opacity.
    pub(crate) body: Option<(&'static str, f64)>,
    pub(crate) broad: Vec<Element>,
    pub(crate) definitions: Vec<Element>,
    pub(crate) layers: Vec<GroundLayer>,
}

struct GroundRandom {
    seed: Seed,
    salt: &'static str,
    index: i64,
}

impl GroundRandom {
    fn new(seed: Seed, salt: &'static str) -> Self {
        Self {
            seed,
            salt,
            index: 0,
        }
    }

    fn unit(&mut self) -> f64 {
        let value = hash01(self.index, self.seed, self.salt);
        self.index += 1;
        value
    }

    fn uniform(&mut self, low: f64, high: f64) -> f64 {
        low + (high - low) * self.unit()
    }

    fn range(&mut self, stop: usize) -> usize {
        ((self.unit() * stop as f64) as usize).min(stop.saturating_sub(1))
    }
}

fn mm(value: f64) -> f64 {
    value * GROUND_MM
}

/// Whole pixels, for soft shapes whose edges fade over tens of pixels.
fn n0(value: f64) -> String {
    format_number(value.round())
}

/// Two decimals: a hundredth of a pixel is not seen, and short numbers keep the ground small.
fn n2(value: f64) -> String {
    format_number((value * 100.0).round() / 100.0)
}

fn n3(value: f64) -> String {
    format_number((value * 1000.0).round() / 1000.0)
}

#[derive(Clone, Copy)]
struct Rgb([f64; 3]);

impl Rgb {
    /// CIE L* of the colour.
    fn lightness(self) -> f64 {
        let linear = self.0.map(|channel| {
            if channel <= 0.04045 {
                channel / 12.92
            } else {
                ((channel + 0.055) / 1.055).powf(2.4)
            }
        });
        let y = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
        let edge = 6.0_f64 / 29.0;
        let f = if y > edge.powi(3) {
            y.cbrt()
        } else {
            y / (3.0 * edge * edge) + 4.0 / 29.0
        };
        116.0 * f - 16.0
    }
}

/// What a mark does when its support is too dark for a darker mark, or too light for a paler one.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Unseen {
    /// Turn the other way: a fibre on black paper catches the light.
    Turn,
    /// Leave it out: a bump's shadow is not seen on black.
    Omit,
}

#[derive(Clone, Copy)]
struct Shade {
    support: f64,
    strength: f64,
}

impl Shade {
    /// The ink and opacity that move the support by `step` L* (below zero, darker).
    fn paint(self, step: f64, unseen: Unseen) -> Option<(&'static str, f64)> {
        let darker = step < 0.0;
        let seen = if darker {
            self.support >= DARKEST_SUPPORT
        } else {
            self.support <= LIGHTEST_SUPPORT
        };
        let darker = match (seen, unseen) {
            (true, _) => darker,
            (false, Unseen::Turn) => !darker,
            (false, Unseen::Omit) => return None,
        };
        let (ink, ink_lightness) = if darker {
            ("#000", 0.0)
        } else {
            ("#fff", 100.0)
        };
        let room = (ink_lightness - self.support).abs().max(1.0);
        Some((ink, (step.abs() * self.strength / room).min(1.0)))
    }
}

#[derive(Clone, Copy)]
struct Style {
    step: f64,
    width: f64,
    round: bool,
    unseen: Unseen,
    /// Dash, gap and offset along each subpath.
    dash: Option<(f64, f64, f64)>,
}

fn style(step: f64, width: f64, round: bool, unseen: Unseen) -> Style {
    Style {
        step,
        width,
        round,
        unseen,
        dash: None,
    }
}

/// One tile of marks; each style becomes one stroked path.
struct Tile {
    width: f64,
    height: f64,
    rotation: f64,
    styles: Vec<Style>,
    paths: Vec<String>,
}

fn wraps(low: f64, high: f64, size: f64) -> Vec<f64> {
    let mut shifts = vec![0.0];
    if low < 0.0 {
        shifts.push(size);
    }
    if high > size {
        shifts.push(-size);
    }
    shifts
}

impl Tile {
    fn new(width: f64, height: f64, styles: Vec<Style>) -> Self {
        let paths = vec![String::new(); styles.len()];
        Self {
            width: (width * 100.0).round() / 100.0,
            height: (height * 100.0).round() / 100.0,
            rotation: 0.0,
            styles,
            paths,
        }
    }

    fn square(side: f64, styles: Vec<Style>) -> Self {
        Self::new(side, side, styles)
    }

    fn rotated(mut self, rotation: f64) -> Self {
        self.rotation = rotation;
        self
    }

    /// Add a mark starting at (x, y). `extent` is its box from the start and `pad` how far its
    /// stroke reaches past that box across and down. A mark crossing an edge is written again
    /// one tile over, so no tile cuts a mark.
    fn mark(
        &mut self,
        style: usize,
        x: f64,
        y: f64,
        extent: [f64; 4],
        pad: (f64, f64),
        segment: &str,
    ) {
        let [left, top, right, bottom] = extent;
        let across = wraps(x + left - pad.0, x + right + pad.0, self.width);
        let down = wraps(y + top - pad.1, y + bottom + pad.1, self.height);
        let path = &mut self.paths[style];
        for dx in &across {
            for dy in &down {
                path.push('M');
                path.push_str(&n2(x + dx));
                path.push(' ');
                path.push_str(&n2(y + dy));
                path.push_str(segment);
            }
        }
    }

    fn dot(&mut self, style: usize, x: f64, y: f64) {
        let half = self.styles[style].width / 2.0;
        self.mark(style, x, y, [0.0; 4], (half, half), "h0");
    }

    /// A vertical stroke with square ends cut flat.
    fn tick(&mut self, style: usize, x: f64, y: f64, length: f64) {
        let half = self.styles[style].width / 2.0;
        let length = (length * 100.0).round() / 100.0;
        self.mark(
            style,
            x,
            y,
            [0.0, 0.0, 0.0, length],
            (half, 0.0),
            &format!("v{}", n2(length)),
        );
    }

    /// A horizontal stroke with square ends cut flat.
    fn run(&mut self, style: usize, x: f64, y: f64, length: f64) {
        let half = self.styles[style].width / 2.0;
        let length = (length * 100.0).round() / 100.0;
        self.mark(
            style,
            x,
            y,
            [0.0, 0.0, length, 0.0],
            (0.0, half),
            &format!("h{}", n2(length)),
        );
    }

    fn line(&mut self, style: usize, x: f64, y: f64, dx: f64, dy: f64) {
        let half = self.styles[style].width / 2.0;
        self.mark(
            style,
            x,
            y,
            [dx.min(0.0), dy.min(0.0), dx.max(0.0), dy.max(0.0)],
            (half, half),
            &format!("l{} {}", n2(dx), n2(dy)),
        );
    }

    fn curve(&mut self, style: usize, x: f64, y: f64, control: (f64, f64), end: (f64, f64)) {
        let half = self.styles[style].width / 2.0;
        let extent = [
            control.0.min(end.0).min(0.0),
            control.1.min(end.1).min(0.0),
            control.0.max(end.0).max(0.0),
            control.1.max(end.1).max(0.0),
        ];
        self.mark(
            style,
            x,
            y,
            extent,
            (half, half),
            &format!(
                "q{} {} {} {}",
                n2(control.0),
                n2(control.1),
                n2(end.0),
                n2(end.1)
            ),
        );
    }

    fn finish(self, shade: Shade) -> Option<GroundLayer> {
        let mut body = Vec::new();
        for (style, d) in self.styles.iter().zip(self.paths) {
            if d.is_empty() {
                continue;
            }
            let Some((ink, opacity)) = shade.paint(style.step, style.unseen) else {
                continue;
            };
            let mut path = Element::new("path")
                .attr("d", d)
                .attr("fill", "none")
                .attr("stroke", ink)
                .attr("stroke-width", n2(style.width))
                .attr("stroke-opacity", n3(opacity));
            if style.round {
                path = path.attr("stroke-linecap", "round");
            }
            if let Some((dash, gap, offset)) = style.dash {
                path = path
                    .attr("stroke-dasharray", format!("{} {}", n2(dash), n2(gap)))
                    .attr("stroke-dashoffset", n2(offset));
            }
            body.push(path);
        }
        (!body.is_empty()).then_some(GroundLayer {
            width: self.width,
            height: self.height,
            rotation: self.rotation,
            body,
        })
    }
}

/// The soft shapes drawn once over the whole canvas, grouped by their gradient.
struct Broad {
    shade: Shade,
    groups: Vec<(&'static str, Vec<Element>)>,
    strokes: Vec<Element>,
}

impl Broad {
    fn new(shade: Shade) -> Self {
        Self {
            shade,
            groups: Vec::new(),
            strokes: Vec::new(),
        }
    }

    fn add(&mut self, gradient: &'static str, element: Element) {
        match self.groups.iter_mut().find(|(id, _)| *id == gradient) {
            Some((_, elements)) => elements.push(element),
            None => self.groups.push((gradient, vec![element])),
        }
    }

    fn ellipse(&mut self, centre: (f64, f64), radii: (f64, f64), angle: f64, step: f64) {
        let Some((ink, opacity)) = self.shade.paint(step, Unseen::Turn) else {
            return;
        };
        let gradient = if ink == "#000" { SOFT_DARK } else { SOFT_LIGHT };
        let mut ellipse = Element::new("ellipse")
            .attr("cx", n0(centre.0))
            .attr("cy", n0(centre.1))
            .attr("rx", n0(radii.0))
            .attr("ry", n0(radii.1))
            .attr("opacity", n3(opacity));
        if angle.round() % 180.0 != 0.0 {
            ellipse = ellipse.attr(
                "transform",
                format!("rotate({} {} {})", n0(angle), n0(centre.0), n0(centre.1)),
            );
        }
        self.add(gradient, ellipse);
    }

    /// A pool of wash: a closed smooth outline through `points`, darkest just inside its edge,
    /// as a dried pool leaves its tide line.
    fn pool(&mut self, points: &[(f64, f64)], step: f64) {
        let Some((ink, opacity)) = self.shade.paint(step, Unseen::Turn) else {
            return;
        };
        let gradient = if ink == "#000" { RING_DARK } else { RING_LIGHT };
        let count = points.len();
        let middle = |a: (f64, f64), b: (f64, f64)| ((a.0 + b.0) / 2.0, (a.1 + b.1) / 2.0);
        let start = middle(points[count - 1], points[0]);
        let start = (start.0.round(), start.1.round());
        let mut at = start;
        let mut d = format!("M{} {}", n0(start.0), n0(start.1));
        for index in 0..count {
            let control = points[index];
            let end = middle(points[index], points[(index + 1) % count]);
            let control = ((control.0 - at.0).round(), (control.1 - at.1).round());
            let end = ((end.0 - at.0).round(), (end.1 - at.1).round());
            d.push_str(&format!(
                "q{} {} {} {}",
                n0(control.0),
                n0(control.1),
                n0(end.0),
                n0(end.1)
            ));
            at = (at.0 + end.0, at.1 + end.1);
        }
        d.push('z');
        self.add(
            gradient,
            Element::new("path")
                .attr("d", d)
                .attr("opacity", n3(opacity)),
        );
    }

    /// Straight lines across the canvas, written as one path.
    fn lines(&mut self, d: String, width: f64, step: f64) {
        let Some((ink, opacity)) = self.shade.paint(step, Unseen::Turn) else {
            return;
        };
        self.strokes.push(
            Element::new("path")
                .attr("d", d)
                .attr("fill", "none")
                .attr("stroke", ink)
                .attr("stroke-width", n2(width))
                .attr("stroke-opacity", n3(opacity)),
        );
    }

    /// Soft ellipses scattered over the canvas: `count` per square of the short side.
    #[allow(clippy::too_many_arguments)]
    fn scatter(
        &mut self,
        random: &mut GroundRandom,
        canvas: CanvasSize,
        count: f64,
        size: (f64, f64),
        roundness: (f64, f64),
        angle: Option<(f64, f64)>,
        steps: &[f64],
    ) {
        let unit = canvas.unit();
        let total = (count * canvas.width * canvas.height / (unit * unit)).round() as usize;
        for index in 0..total {
            let cx = random.uniform(-0.08, 1.08) * canvas.width;
            let cy = random.uniform(-0.08, 1.08) * canvas.height;
            let mut rx = unit * random.uniform(size.0, size.1);
            let mut ry = rx * random.uniform(roundness.0, roundness.1);
            let turn = match angle {
                // Upright: no turn to write, but half of them stand the other way.
                Some((centre, spread)) if centre == 0.0 && spread == 0.0 => {
                    if random.unit() < 0.5 {
                        std::mem::swap(&mut rx, &mut ry);
                    }
                    0.0
                }
                Some((centre, spread)) => centre + random.uniform(-spread, spread),
                None => random.uniform(0.0, 180.0),
            };
            let step = steps[index % steps.len()] * random.uniform(0.7, 1.3);
            self.ellipse((cx, cy), (rx, ry), turn, step);
        }
    }

    fn finish(self) -> (Vec<Element>, Vec<Element>) {
        let mut definitions = Vec::new();
        let mut elements = Vec::new();
        for (gradient, shapes) in self.groups {
            let (colour, stops): (&str, &[(&str, &str)]) = match gradient {
                SOFT_DARK => ("#000", &[("0", "1"), ("0.55", "0.55"), ("1", "0")]),
                SOFT_LIGHT => ("#fff", &[("0", "1"), ("0.55", "0.55"), ("1", "0")]),
                RING_DARK => (
                    "#000",
                    &[("0", "0.55"), ("0.9", "0.8"), ("0.97", "1"), ("1", "0")],
                ),
                _ => (
                    "#fff",
                    &[("0", "0.55"), ("0.9", "0.8"), ("0.97", "1"), ("1", "0")],
                ),
            };
            let mut definition = Element::new("radialGradient").attr("id", gradient);
            for (offset, opacity) in stops {
                definition.push(
                    Element::new("stop")
                        .attr("offset", *offset)
                        .attr("stop-color", colour)
                        .attr("stop-opacity", *opacity),
                );
            }
            definitions.push(definition);
            let mut group = Element::new("g").attr("fill", format!("url(#{gradient})"));
            for shape in shapes {
                group.push(shape);
            }
            elements.push(group);
        }
        elements.extend(self.strokes);
        (elements, definitions)
    }
}

/// Dots of `styles` scattered over a square tile turned by `rotation`, `count` of them, each
/// drawn in a style picked at random.
fn dots(
    seed: Seed,
    salt: &'static str,
    side: f64,
    rotation: f64,
    count: usize,
    styles: Vec<Style>,
    shade: Shade,
) -> Option<GroundLayer> {
    let mut random = GroundRandom::new(seed, salt);
    let kinds = styles.len();
    let mut tile = Tile::square(side, styles).rotated(rotation);
    for _ in 0..count {
        let kind = random.range(kinds);
        tile.dot(kind, random.uniform(0.0, side), random.uniform(0.0, side));
    }
    tile.finish(shade)
}

fn paper(
    ground: &CanvasGroundSpec,
    seed: Seed,
    shade: Shade,
    broad: &mut Broad,
    canvas: CanvasSize,
) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-paper-broad");
    broad.scatter(
        &mut random,
        canvas,
        12.0,
        (0.10, 0.26),
        (0.6, 1.0),
        Some((0.0, 0.0)),
        &[-2.6, 2.6],
    );
    let size = match ground.grain {
        GroundGrain::Fine => 0.64,
        GroundGrain::Medium => 1.0,
        GroundGrain::Coarse => 1.64,
        GroundGrain::None => 0.55,
    };
    let density = ground.density.max(0.02) / GROUND_DENSITY_DEFAULT;
    let mut layers = Vec::new();
    for (side, rotation, salt, fibres) in [
        (109.0, 0.0, "ground-paper-a", 6),
        (149.0, 23.0, "ground-paper-b", 10),
        (193.0, 61.0, "ground-paper-c", 14),
    ] {
        let mut random = GroundRandom::new(seed, salt);
        let mut tile = Tile::square(
            side,
            vec![
                style(-11.0, 1.4 * size, true, Unseen::Turn),
                style(-8.0, 2.2 * size, true, Unseen::Turn),
                style(-8.0, 0.5, false, Unseen::Turn),
            ],
        )
        .rotated(rotation);
        let count = (side * side * 0.0016 * density).round() as usize;
        for _ in 0..count {
            let kind = random.range(2);
            tile.dot(kind, random.uniform(0.0, side), random.uniform(0.0, side));
        }
        for _ in 0..fibres {
            let length = random.uniform(3.0, 8.0);
            let angle = random.uniform(0.0, std::f64::consts::PI);
            tile.line(
                2,
                random.uniform(0.0, side),
                random.uniform(0.0, side),
                angle.cos() * length,
                angle.sin() * length,
            );
        }
        layers.extend(tile.finish(shade));
    }
    layers
}

fn washi(seed: Seed, shade: Shade, broad: &mut Broad, canvas: CanvasSize) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-washi-broad");
    broad.scatter(
        &mut random,
        canvas,
        22.0,
        (0.06, 0.18),
        (0.5, 1.0),
        Some((0.0, 0.0)),
        &[-3.0, 4.0, 4.0],
    );
    let mut chains = String::new();
    let mut y = random.uniform(0.0, mm(28.0));
    while y < canvas.height {
        chains.push_str(&format!("M0 {}h{}", n2(y), n0(canvas.width)));
        y += mm(random.uniform(26.0, 32.0));
    }
    broad.lines(chains, 1.1, -2.6);
    let mut layers = Vec::new();
    let pitch = mm(1.05);
    let mut laid = Tile::new(
        pitch * 20.0,
        250.0,
        vec![style(-2.2, 0.7, false, Unseen::Turn)],
    );
    for index in 0..20 {
        laid.tick(0, pitch * (index as f64 + 0.5), 0.0, 250.0);
    }
    layers.extend(laid.finish(shade));
    for (side, salt, count) in [
        (255.0, "ground-washi-a", 24),
        (329.0, "ground-washi-b", 38),
        (415.0, "ground-washi-c", 56),
    ] {
        let mut random = GroundRandom::new(seed, salt);
        let mut tile = Tile::square(
            side,
            vec![
                style(-9.0, 0.45, false, Unseen::Turn),
                style(-6.0, 0.75, false, Unseen::Turn),
                style(7.0, 0.6, false, Unseen::Omit),
            ],
        );
        for _ in 0..count {
            let kind = random.range(3);
            let length = mm(random.uniform(5.0, 16.0));
            let angle = random.uniform(0.0, std::f64::consts::PI);
            let bow = random.uniform(-0.16, 0.16) * length;
            let (dx, dy) = (angle.cos() * length, angle.sin() * length);
            tile.curve(
                kind,
                random.uniform(0.0, side),
                random.uniform(0.0, side),
                (dx / 2.0 - angle.sin() * bow, dy / 2.0 + angle.cos() * bow),
                (dx, dy),
            );
        }
        layers.extend(tile.finish(shade));
    }
    layers
}

fn ink_wash(seed: Seed, shade: Shade, broad: &mut Broad, canvas: CanvasSize) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-ink-wash-broad");
    let unit = canvas.unit();
    let area = canvas.width * canvas.height / (unit * unit);
    let flow = random.uniform(-20.0, 20.0);
    for _ in 0..(4.0 * area).round() as usize {
        let centre = (
            random.uniform(-0.1, 1.1) * canvas.width,
            random.uniform(0.0, 1.0) * canvas.height,
        );
        let rx = unit * random.uniform(0.3, 0.6);
        let ry = unit * random.uniform(0.03, 0.07);
        let angle = flow + random.uniform(-8.0, 8.0);
        broad.ellipse(centre, (rx, ry), angle, -2.0 * random.uniform(0.7, 1.3));
    }
    // Pools: wide and few, their edges wavering as a drying wash's do.
    for _ in 0..(5.0 * area).round() as usize {
        let cx = random.uniform(-0.1, 1.1) * canvas.width;
        let cy = random.uniform(-0.1, 1.1) * canvas.height;
        let radius = unit * random.uniform(0.2, 0.45);
        let squash = random.uniform(0.55, 0.85);
        let turn = (flow + random.uniform(-25.0, 25.0)).to_radians();
        let waves = [
            (
                3.0,
                random.uniform(0.10, 0.18),
                random.uniform(0.0, std::f64::consts::TAU),
            ),
            (
                5.0,
                random.uniform(0.05, 0.10),
                random.uniform(0.0, std::f64::consts::TAU),
            ),
            (
                8.0,
                random.uniform(0.03, 0.06),
                random.uniform(0.0, std::f64::consts::TAU),
            ),
        ];
        let points = (0..14)
            .map(|corner| {
                let angle = std::f64::consts::TAU * corner as f64 / 14.0;
                let swell: f64 = waves
                    .iter()
                    .map(|(count, depth, phase)| depth * (count * angle + phase).sin())
                    .sum();
                let reach = radius * (1.0 + swell);
                let (x, y) = (angle.cos() * reach, angle.sin() * reach * squash);
                (
                    cx + x * turn.cos() - y * turn.sin(),
                    cy + x * turn.sin() + y * turn.cos(),
                )
            })
            .collect::<Vec<_>>();
        broad.pool(&points, -3.5 * random.uniform(0.75, 1.25));
    }
    broad.scatter(
        &mut random,
        canvas,
        4.0,
        (0.12, 0.28),
        (0.5, 1.0),
        Some((0.0, 0.0)),
        &[3.0],
    );
    let mut layers = Vec::new();
    for (side, rotation, salt, count) in [
        (125.0, 0.0, "ground-ink-wash-a", 22),
        (171.0, 29.0, "ground-ink-wash-b", 40),
        (211.0, 67.0, "ground-ink-wash-c", 60),
    ] {
        layers.extend(dots(
            seed,
            salt,
            side,
            rotation,
            count,
            vec![
                style(-6.0, 1.0, true, Unseen::Turn),
                style(-4.5, 1.3, true, Unseen::Turn),
            ],
            shade,
        ));
    }
    layers
}

fn charcoal(seed: Seed, shade: Shade, broad: &mut Broad, canvas: CanvasSize) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-charcoal-broad");
    let rubbing = if random.unit() < 0.5 {
        random.uniform(20.0, 70.0)
    } else {
        random.uniform(110.0, 160.0)
    };
    broad.scatter(
        &mut random,
        canvas,
        16.0,
        (0.12, 0.34),
        (0.25, 0.5),
        Some((rubbing, 18.0)),
        &[-8.0, 10.0],
    );
    let pitch = mm(1.1);
    let mut layers = Vec::new();
    let mut laid = Tile::new(
        pitch * 12.0,
        250.0,
        vec![style(3.0, 1.7, false, Unseen::Turn)],
    );
    for index in 0..12 {
        laid.tick(0, pitch * index as f64, 0.0, 250.0);
    }
    layers.extend(laid.finish(shade));
    for (side, rotation, salt, count) in [
        (59.0, 0.0, "ground-charcoal-tooth-a", 12),
        (97.0, 33.0, "ground-charcoal-tooth-b", 30),
        (157.0, 71.0, "ground-charcoal-tooth-c", 74),
    ] {
        layers.extend(dots(
            seed,
            salt,
            side,
            rotation,
            count,
            vec![
                style(9.0, 1.0, true, Unseen::Turn),
                style(6.0, 1.6, true, Unseen::Turn),
            ],
            shade,
        ));
    }
    for (ridges, height, salt, count) in [
        (12_usize, 85.0, "ground-charcoal-ticks-a", 14),
        (19, 139.0, "ground-charcoal-ticks-b", 36),
    ] {
        let mut random = GroundRandom::new(seed, salt);
        let mut tile = Tile::new(
            pitch * ridges as f64,
            height,
            vec![
                style(-7.0, pitch * 0.5, false, Unseen::Turn),
                style(-4.5, pitch * 0.5, false, Unseen::Turn),
            ],
        );
        for _ in 0..count {
            let kind = random.range(2);
            let column = random.range(ridges);
            tile.tick(
                kind,
                pitch * (column as f64 + 0.5),
                random.uniform(0.0, height),
                mm(random.uniform(0.35, 1.4)),
            );
        }
        layers.extend(tile.finish(shade));
    }
    layers
}

fn canvas_cloth(
    seed: Seed,
    shade: Shade,
    broad: &mut Broad,
    canvas: CanvasSize,
) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-canvas-broad");
    broad.scatter(
        &mut random,
        canvas,
        10.0,
        (0.12, 0.3),
        (0.6, 1.0),
        Some((0.0, 0.0)),
        &[-2.4, 2.4],
    );
    let pitch = mm(1000.0 / 14.0 / 100.0);
    let threads = 8;
    let side = pitch * threads as f64;
    let over = |offset: f64| Style {
        dash: Some((pitch * 0.76, pitch * 1.24, offset)),
        ..style(-3.5, pitch * 0.42, false, Unseen::Turn)
    };
    let mut weave = Tile::square(
        side,
        vec![
            over(pitch * 1.88),
            over(pitch * 0.88),
            style(-2.0, pitch * 0.25, false, Unseen::Turn),
        ],
    );
    for index in 0..threads {
        let middle = pitch * (index as f64 + 0.5);
        weave.run(index % 2, 0.0, middle, side);
        weave.tick(1 - index % 2, middle, 0.0, side);
        weave.run(2, 0.0, pitch * index as f64, side);
        weave.tick(2, pitch * index as f64, 0.0, side);
    }
    let mut layers = Vec::new();
    layers.extend(weave.finish(shade));
    for (across, down, salt, count) in [
        (36_usize, 39_usize, "ground-canvas-slub-a", 2),
        (55, 62, "ground-canvas-slub-b", 6),
        (87, 94, "ground-canvas-slub-c", 15),
        (132, 142, "ground-canvas-slub-d", 34),
    ] {
        let mut random = GroundRandom::new(seed, salt);
        let (width, height) = (pitch * across as f64, pitch * down as f64);
        let mut tile = Tile::new(
            width,
            height,
            vec![
                style(-3.0, pitch * 0.55, false, Unseen::Turn),
                style(2.5, pitch * 0.55, false, Unseen::Turn),
            ],
        );
        for _ in 0..count {
            let kind = random.range(2);
            let length = random.uniform(12.0, 40.0);
            if random.unit() < 0.5 {
                let row = random.range(down);
                tile.run(
                    kind,
                    random.uniform(0.0, width),
                    pitch * (row as f64 + 0.5),
                    length,
                );
            } else {
                let column = random.range(across);
                tile.tick(
                    kind,
                    pitch * (column as f64 + 0.5),
                    random.uniform(0.0, height),
                    length,
                );
            }
        }
        layers.extend(tile.finish(shade));
    }
    layers
}

fn drawing_paper(
    seed: Seed,
    shade: Shade,
    broad: &mut Broad,
    canvas: CanvasSize,
) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-drawing-paper-broad");
    broad.scatter(
        &mut random,
        canvas,
        10.0,
        (0.12, 0.3),
        (0.6, 1.0),
        Some((0.0, 0.0)),
        &[-2.0, 2.0],
    );
    let mut layers = Vec::new();
    for (side, rotation, salt, count) in [
        (60.0, 0.0, "ground-drawing-paper-a", 24),
        (102.0, 37.0, "ground-drawing-paper-b", 69),
        (158.0, 71.0, "ground-drawing-paper-c", 166),
    ] {
        layers.extend(dots(
            seed,
            salt,
            side,
            rotation,
            count,
            vec![
                style(-10.0, 1.1, true, Unseen::Turn),
                style(-7.0, 1.6, true, Unseen::Turn),
                style(8.0, 1.2, true, Unseen::Omit),
            ],
            shade,
        ));
    }
    layers
}

fn mezzotint(seed: Seed, shade: Shade, broad: &mut Broad, canvas: CanvasSize) -> Vec<GroundLayer> {
    let lift = MEZZOTINT_LIFT;
    let mut random = GroundRandom::new(seed, "ground-mezzotint-broad");
    // Burnished places, where the plate holds less ink.
    broad.scatter(
        &mut random,
        canvas,
        10.0,
        (0.10, 0.30),
        (0.5, 1.0),
        Some((0.0, 0.0)),
        &[7.0 * lift, 4.5 * lift],
    );
    let mut layers = Vec::new();
    // The rocker's marks and the grain, spread evenly over five tiles turned to five directions:
    // each tile's short strokes run along it, so the strokes cross as the rocker's passes do.
    for (side, rotation, salt) in [
        (41.0, 15.0, "ground-mezzotint-rocker-a"),
        (53.0, 105.0, "ground-mezzotint-rocker-b"),
        (67.0, 75.0, "ground-mezzotint-rocker-c"),
        (89.0, 41.0, "ground-mezzotint-rocker-d"),
        (109.0, 135.0, "ground-mezzotint-rocker-e"),
    ] {
        let mut random = GroundRandom::new(seed, salt);
        let mut tile = Tile::square(
            side,
            vec![
                style(9.0 * lift, 0.7, true, Unseen::Turn),
                style(6.0 * lift, 0.9, true, Unseen::Turn),
                style(5.0 * lift, 0.9, true, Unseen::Turn),
                style(3.5 * lift, 1.2, true, Unseen::Turn),
            ],
        )
        .rotated(rotation);
        for _ in 0..(side * side * 0.0072).round() as usize {
            let kind = random.range(2);
            let length = random.uniform(2.5, 5.0);
            tile.line(
                kind,
                random.uniform(0.0, side),
                random.uniform(0.0, side),
                length,
                0.0,
            );
        }
        for _ in 0..(side * side * 0.008).round() as usize {
            let kind = 2 + random.range(2);
            tile.dot(kind, random.uniform(0.0, side), random.uniform(0.0, side));
        }
        layers.extend(tile.finish(shade));
    }
    layers.extend(dots(
        seed,
        "ground-mezzotint-flecks",
        263.0,
        0.0,
        12,
        vec![
            style(10.0, 1.6, true, Unseen::Turn),
            style(7.0, 2.8, true, Unseen::Turn),
        ],
        shade,
    ));
    layers
}

/// Build the ground of `material` over `tone` (the colour the tone rect paints).
pub(crate) fn build_ground_plan(
    ground: &CanvasGroundSpec,
    seed: Seed,
    canvas: CanvasSize,
    tone: &str,
) -> GroundPlan {
    // The material's own tone (inku-score's table, which the DDL lowering and the
    // pipeline read too) laid over the tone.
    let body = ground.material.body();
    let support = Rgb(shown_support(
        ground.material,
        srgb_channels(tone).unwrap_or([0.95; 3]),
    ));
    let shade = Shade {
        support: support.lightness(),
        strength: GROUND_STRENGTH * ground.opacity.max(0.0) / GROUND_OPACITY_DEFAULT,
    };
    let mut broad = Broad::new(shade);
    let layers = match ground.material {
        GroundMaterial::Plain => Vec::new(),
        GroundMaterial::Paper => paper(ground, seed, shade, &mut broad, canvas),
        GroundMaterial::Washi => washi(seed, shade, &mut broad, canvas),
        GroundMaterial::InkWash => ink_wash(seed, shade, &mut broad, canvas),
        GroundMaterial::CharcoalGround => charcoal(seed, shade, &mut broad, canvas),
        GroundMaterial::Canvas => canvas_cloth(seed, shade, &mut broad, canvas),
        GroundMaterial::DrawingPaper => drawing_paper(seed, shade, &mut broad, canvas),
        GroundMaterial::Mezzotint => mezzotint(seed, shade, &mut broad, canvas),
    };
    let (broad, definitions) = broad.finish();
    GroundPlan {
        body,
        broad,
        definitions,
        layers,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_mark_crossing_a_tile_edge_is_written_again_one_tile_over() {
        // A pattern clips its tile, so a mark cut at the edge left a seam.
        let mut tile = Tile::square(10.0, vec![style(-5.0, 1.0, true, Unseen::Turn)]);
        tile.dot(0, 9.8, 5.0);
        tile.dot(0, 5.0, 0.2);
        tile.dot(0, 5.0, 5.0);
        assert_eq!(tile.paths[0], "M9.8 5h0M-0.2 5h0M5 0.2h0M5 10.2h0M5 5h0");
    }

    #[test]
    fn a_mark_turns_or_stays_out_where_its_support_hides_it() {
        let light = Shade {
            support: 96.0,
            strength: 1.0,
        };
        let dark = Shade {
            support: 6.0,
            strength: 1.0,
        };
        assert_eq!(
            light.paint(-8.0, Unseen::Turn).map(|(ink, _)| ink),
            Some("#000")
        );
        assert_eq!(
            dark.paint(-8.0, Unseen::Turn).map(|(ink, _)| ink),
            Some("#fff")
        );
        assert_eq!(dark.paint(-8.0, Unseen::Omit), None);
        assert_eq!(light.paint(8.0, Unseen::Omit), None);
        // The opacity moves the support by the step, as far as the ink allows.
        let (_, opacity) = dark.paint(8.0, Unseen::Turn).unwrap();
        assert!((opacity - 8.0 / 94.0).abs() < 1e-12);
    }
}
