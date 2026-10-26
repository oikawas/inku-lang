//! How a Score's layers look when drawn, for the color stage (2026-10-20).
//!
//! The core draws no pixels (the author's answer of 2026-10-20: the drawn
//! difference is estimated). The renderer writes the Score's editable SVG, and
//! this module reads what each layer drew there: every filled outline and
//! stroked line, with its paint, its opacity (the renderer's tool weight, the
//! handling and any fill mask over it) and its width. It then estimates the
//! picture the color stage's prototype measured, each layer drawn alone on its
//! ground at 500 pixels across: a pixel at least ΔE76 12 from the ground is
//! ink, and the ink pixel of median L* is the layer's drawn color. A band
//! covers the pixels it crosses by the shares of a coverage table, a stroke
//! thinner than a pixel is a hairline whose strength its width scales, and a
//! point is a disc. On the prototype's 25 pictures this estimate came within
//! 0.05 of the measured lightness difference for 48 of the 56 layers it read.
//!
//! The SVG numbers each instruction group by the renderer's performed order;
//! the renderer's performance plan names the Score instruction each one draws.

use std::collections::{BTreeMap, BTreeSet};

use inku_render::checked_performance::{
    resolve_checked_performance, resolve_checked_performance_with_resources,
};
use inku_render::compat_clip::ClipLimits;
use inku_render::performance::PerformanceRequest;
use inku_render::render::{CompatFillClipPolicy, render, render_with_resources};
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, SvgProfile};
use inku_score::{Color, Primitive, Score, ScoreErrorPolicy, lookup_canvas_format};

use crate::laws::layer_of;

/// The clip limits the Server draws with (its default manifest). The editable
/// SVG clips no fill by them; the renderer takes them with a resource policy.
const CLIP: CompatFillClipPolicy = CompatFillClipPolicy {
    tolerance_pixels: 0.1,
    limits: ClipLimits {
        max_nodes: 50_000,
        max_path_elements: 200_000,
        max_flattened_points: 200_000,
        max_work: 10_000_000,
        max_output_vertices: 200_000,
    },
};

/// The pixels across the picture the prototype measured.
const PICTURE_WIDTH: f64 = 500.0;
/// A pixel this far from the ground (CIE ΔE76) is ink.
const INK: f64 = 12.0;
/// The canvas height the Server draws a work at.
const CANVAS_HEIGHT: f64 = 1000.0;
/// A band at least this many pixels wide covers its inside whole.
const WIDE_BAND: f64 = 6.0;
/// A disc at least this many pixels across covers its inside whole.
const WIDE_DISC: f64 = 12.0;
/// Two layers touch when their marks come this many pixels near (each grown by
/// three pixels, as the prototype's measure grew them).
const TOUCH_CELL: f64 = 3.0;

/// How one layer looks when drawn alone on its ground.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Look {
    /// The CIELAB of the layer's median ink pixel; `None` when no pixel is ink.
    pub lab: Option<[f64; 3]>,
    /// The lightness difference of the drawn color from the ground (0 to 1).
    pub contrast: f64,
    /// The drawn color's CIELAB chroma.
    pub chroma: f64,
    /// The share of the picture the layer's ink covers.
    pub ink: f64,
    /// Whether the SVG showed marks in the layer's own paint. A layer it did
    /// not is taken as its paint itself.
    pub read: bool,
    /// What the estimate read: the opacity the own paint is mostly drawn
    /// with, the marks' width in the picture's pixels and how they cover
    /// (`band`, `stroke` or `disc`; `none` for a layer not read).
    pub opacity: f64,
    pub width: f64,
    pub cover: &'static str,
}

/// The layers of one drawing: how each looks and which touch.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Drawing {
    pub looks: BTreeMap<usize, Look>,
    pub neighbors: BTreeMap<usize, BTreeSet<usize>>,
}

/// What a run draws with: its nine paints, its canvas and its seeds.
#[derive(Clone, Debug)]
pub struct Painter {
    codes: BTreeMap<String, String>,
    rgb: BTreeMap<&'static str, [u8; 3]>,
    canvas: CanvasSize,
    canvas_format_id: String,
    render_seed: Option<i128>,
    composition_seed: Option<i128>,
    error_policy: ScoreErrorPolicy,
}

/// The seeds a run draws its picture with: the render seed, and the
/// composition seed that places its marks when it has one (else the render
/// seed places them).
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct Seeds {
    pub render: Option<i128>,
    pub composition: Option<i128>,
}

impl Painter {
    /// A painter for the nine colors' sRGB on a registered canvas; `None`
    /// when a color has no paint or the canvas is not registered.
    #[must_use]
    pub fn new(
        rgb: &[(Color, [u8; 3])],
        canvas_format_id: &str,
        seeds: Seeds,
        error_policy: ScoreErrorPolicy,
    ) -> Option<Self> {
        let format = lookup_canvas_format(canvas_format_id).ok()?;
        let rgb: BTreeMap<&'static str, [u8; 3]> = rgb
            .iter()
            .map(|(color, paint)| (color.as_str(), *paint))
            .collect();
        if Color::ALL
            .iter()
            .any(|color| !rgb.contains_key(color.as_str()))
        {
            return None;
        }
        let width = (CANVAS_HEIGHT * f64::from(format.width_units)
            / f64::from(format.height_units))
        .round_ties_even();
        let codes = rgb
            .iter()
            .map(|(color, [r, g, b])| ((*color).to_owned(), format!("#{r:02x}{g:02x}{b:02x}")))
            .collect();
        Some(Self {
            codes,
            rgb,
            canvas: CanvasSize::new(width, CANVAS_HEIGHT),
            canvas_format_id: canvas_format_id.to_owned(),
            render_seed: seeds.render,
            composition_seed: seeds.composition,
            error_policy,
        })
    }

    /// The sRGB a color is drawn with.
    #[must_use]
    pub fn rgb(&self, color: Color) -> [u8; 3] {
        self.rgb[color.as_str()]
    }

    /// How the Score's layers look, or `None` when the renderer does not draw it.
    #[must_use]
    pub fn drawing(&self, score: &Score, shares: &mut Shares) -> Option<Drawing> {
        self.try_drawing(score, shares).ok()
    }

    /// [`Self::drawing`], with the step that did not draw.
    ///
    /// # Errors
    ///
    /// The step the renderer stopped at: `performance`, `render` or `svg`.
    pub fn try_drawing(&self, score: &Score, shares: &mut Shares) -> Result<Drawing, String> {
        let (svg, layer_of_ordinal) = self.editable(score)?;
        let groups = read_svg(&svg).ok_or_else(|| "svg".to_owned())?;
        let mut drawn: BTreeMap<usize, Vec<Mark>> = BTreeMap::new();
        for (ordinal, elements) in groups {
            if let Some(layer) = layer_of_ordinal.get(&ordinal) {
                drawn.entry(*layer).or_default().push(elements);
            }
        }
        let ground = self.rgb(score.background);
        let scale = PICTURE_WIDTH / self.canvas.width;
        let canvas_area = self.canvas.width * self.canvas.height;
        let mut looks = BTreeMap::new();
        for (layer, positions) in crate::laws::layers(score) {
            let first = &score.instructions[positions[0]];
            let points = positions
                .iter()
                .all(|position| score.instructions[*position].primitive == Primitive::Point);
            let marks = drawn.get(&layer).map_or(&[][..], Vec::as_slice);
            let look = layer_look(
                marks,
                self.rgb(first.color),
                ground,
                points,
                scale,
                canvas_area,
                shares,
            );
            looks.insert(layer, look);
        }
        let neighbors = touching(&drawn, self.canvas, scale);
        Ok(Drawing { looks, neighbors })
    }

    /// The Score's editable SVG as this painter draws it, and the layer each
    /// of its instruction groups draws, by the group's performed number.
    ///
    /// # Errors
    ///
    /// The step the renderer stopped at: `performance` or `render`.
    pub fn editable(&self, score: &Score) -> Result<(String, BTreeMap<usize, usize>), String> {
        let options = RenderOptions {
            resolved_color_map: self.codes.clone(),
            catalog_id: None,
            canvas: self.canvas,
            canvas_aspect_id: self.canvas_format_id.clone(),
            svg_profile: SvgProfile::Editable,
            render_seed: self.render_seed,
            composition_seed: self.composition_seed,
            wild: false,
            error_policy: self.error_policy,
        };
        let request = PerformanceRequest {
            score,
            performance_seed: self.render_seed,
            composition_seed: self.composition_seed,
            canvas: Some(self.canvas),
        };
        // A compiled Score carries the resource policy it was compiled under;
        // the renderer performs and draws it under that policy.
        let plan = match &score.resource_policy {
            Some(policy) => resolve_checked_performance_with_resources(
                request,
                self.error_policy,
                &policy.hard_policy,
                policy.operational_budget,
            )
            .map_err(|error| format!("performance: {error:?}"))?,
            None => resolve_checked_performance(request, self.error_policy)
                .map_err(|error| format!("performance: {error:?}"))?,
        };
        let layer_of_ordinal: BTreeMap<usize, usize> = plan
            .performed
            .iter()
            .filter_map(|performed| {
                let instruction = score
                    .instructions
                    .get(performed.original_instruction_index)?;
                Some((performed.instruction_index, layer_of(instruction)?.0))
            })
            .collect();
        let request = RenderRequest {
            score: score.clone(),
            options,
        };
        let rendered = match &score.resource_policy {
            Some(policy) => render_with_resources(
                request,
                &policy.hard_policy,
                policy.operational_budget,
                CLIP,
            ),
            None => render(request),
        }
        .map_err(|error| format!("render: {error}"))?;
        Ok((rendered.svg, layer_of_ordinal))
    }
}

// --- colors ---------------------------------------------------------------------------------------

/// CIELAB (D65) of an sRGB color with channels from 0 to 1, as the prototype's
/// measure converts it.
fn lab_of_unit(rgb: [f64; 3]) -> [f64; 3] {
    let linear = |c: f64| {
        if c <= 0.04045 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    };
    let lin = rgb.map(linear);
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
    [
        116.0 * f(y) - 16.0,
        500.0 * (f(x) - f(y)),
        200.0 * (f(y) - f(z)),
    ]
}

/// CIELAB (D65) of an sRGB color.
#[must_use]
pub fn lab_of(rgb: [u8; 3]) -> [f64; 3] {
    lab_of_unit(rgb.map(|channel| f64::from(channel) / 255.0))
}

fn unit(rgb: [u8; 3]) -> [f64; 3] {
    rgb.map(|channel| f64::from(channel) / 255.0)
}

fn distance(a: [f64; 3], b: [f64; 3]) -> f64 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

/// Python's `round(value, 3)`.
fn round3(value: f64) -> f64 {
    format!("{value:.3}").parse().unwrap_or(value)
}

/// Python's `round(value, 4)`.
fn round4(value: f64) -> f64 {
    format!("{value:.4}").parse().unwrap_or(value)
}

// --- coverage -------------------------------------------------------------------------------------

/// The shape a layer's marks cover pixels with.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Cover {
    /// A filled outline of a width.
    Band,
    /// A stroked line: thinner than a pixel, a hairline.
    Stroke,
    /// A point of a diameter.
    Disc,
}

/// The coverage tables: for a width in pixels, the shares of the pixels a
/// long straight band (or a hairline, or a disc) touches by how much of each
/// it covers. The tables are found by sampling, once per width.
#[derive(Clone, Debug, Default)]
pub struct Shares {
    bands: BTreeMap<u64, Vec<(f64, f64)>>,
    discs: BTreeMap<u64, Vec<(f64, f64)>>,
}

/// Coverage counts by thousandths, as shares of all touched pixels.
fn shares_of(counts: &BTreeMap<i64, u64>) -> Vec<(f64, f64)> {
    let total: u64 = counts.values().sum();
    counts
        .iter()
        .map(|(thousandths, count)| (*thousandths as f64 / 1000.0, *count as f64 / total as f64))
        .collect()
}

impl Shares {
    /// A long straight band of this width, sampled at ten angles from 0 to 45
    /// degrees and ten offsets across a pixel, each pixel's covered part found
    /// with 8 by 8 points.
    fn band(&mut self, width: f64) -> Vec<(f64, f64)> {
        if width >= WIDE_BAND {
            return vec![(1.0, 1.0)];
        }
        self.bands
            .entry(width.to_bits())
            .or_insert_with(|| {
                let steps = 8;
                let mut counts: BTreeMap<i64, u64> = BTreeMap::new();
                for angle_step in 0..10 {
                    let angle = (f64::from(angle_step) * 4.5).to_radians();
                    let (nx, ny) = (-angle.sin(), angle.cos());
                    for offset_step in 0..10 {
                        let offset = f64::from(offset_step) / 10.0;
                        #[allow(clippy::cast_possible_truncation)]
                        let reach = (width / 2.0 + 2.0).ceil() as i64;
                        for py in -reach..=reach {
                            for px in 0..6 {
                                let mut inside = 0;
                                for sy in 0..steps {
                                    for sx in 0..steps {
                                        let x =
                                            px as f64 + (f64::from(sx) + 0.5) / f64::from(steps);
                                        let y =
                                            py as f64 + (f64::from(sy) + 0.5) / f64::from(steps);
                                        if (x * nx + y * ny - offset).abs() <= width / 2.0 {
                                            inside += 1;
                                        }
                                    }
                                }
                                if inside > 0 {
                                    let covered = round3(f64::from(inside) / 64.0);
                                    #[allow(clippy::cast_possible_truncation)]
                                    let key = (covered * 1000.0).round() as i64;
                                    *counts.entry(key).or_insert(0) += 1;
                                }
                            }
                        }
                    }
                }
                shares_of(&counts)
            })
            .clone()
    }

    /// A stroke thinner than a pixel is drawn as a hairline whose strength its
    /// width scales: each column's two pixels share the coverage by where the
    /// line runs.
    fn hairline(width: f64) -> Vec<(f64, f64)> {
        let levels = 40;
        (0..levels)
            .map(|k| {
                (
                    round4(width * (f64::from(k) + 0.5) / f64::from(levels)),
                    1.0 / f64::from(levels),
                )
            })
            .collect()
    }

    /// A disc of this diameter, sampled at 5 by 5 centers inside a pixel.
    fn disc(&mut self, diameter: f64) -> Vec<(f64, f64)> {
        if diameter >= WIDE_DISC {
            return vec![(1.0, 1.0)];
        }
        self.discs
            .entry(diameter.to_bits())
            .or_insert_with(|| {
                let steps = 8;
                let radius = diameter / 2.0;
                #[allow(clippy::cast_possible_truncation)]
                let reach = (radius + 1.0).ceil() as i64;
                let mut counts: BTreeMap<i64, u64> = BTreeMap::new();
                for oy in 0..5 {
                    for ox in 0..5 {
                        let cx = (f64::from(ox) + 0.5) / 5.0;
                        let cy = (f64::from(oy) + 0.5) / 5.0;
                        for py in -reach..=reach {
                            for px in -reach..=reach {
                                let mut inside = 0;
                                for sy in 0..steps {
                                    for sx in 0..steps {
                                        let x = px as f64
                                            + (f64::from(sx) + 0.5) / f64::from(steps)
                                            - cx;
                                        let y = py as f64
                                            + (f64::from(sy) + 0.5) / f64::from(steps)
                                            - cy;
                                        if x * x + y * y <= radius * radius {
                                            inside += 1;
                                        }
                                    }
                                }
                                if inside > 0 {
                                    let covered = round3(f64::from(inside) / 64.0);
                                    #[allow(clippy::cast_possible_truncation)]
                                    let key = (covered * 1000.0).round() as i64;
                                    *counts.entry(key).or_insert(0) += 1;
                                }
                            }
                        }
                    }
                }
                shares_of(&counts)
            })
            .clone()
    }

    fn of(&mut self, cover: Cover, width: f64) -> Vec<(f64, f64)> {
        match cover {
            Cover::Stroke if width < 1.0 => Self::hairline(width),
            Cover::Disc => self.disc(width),
            Cover::Band | Cover::Stroke => self.band(width),
        }
    }
}

/// The Lab of the median ink pixel (by L*) among touched pixels drawn with
/// these strengths (each a share of the touched pixels), and the share of the
/// touched pixels that are ink; `None` when no pixel is.
fn median_ink(paint: [u8; 3], ground: [u8; 3], pixels: &[(f64, f64)]) -> Option<([f64; 3], f64)> {
    let (paint, ground) = (unit(paint), unit(ground));
    let ground_lab = lab_of_unit(ground);
    let mut kept: Vec<([f64; 3], f64)> = Vec::new();
    for &(alpha, weight) in pixels {
        let alpha = alpha.min(1.0);
        let mixed =
            [0, 1, 2].map(|k| (alpha * paint[k] + (1.0 - alpha) * ground[k]).clamp(0.0, 1.0));
        let lab = lab_of_unit(mixed);
        if distance(lab, ground_lab) >= INK {
            kept.push((lab, weight));
        }
    }
    if kept.is_empty() {
        return None;
    }
    kept.sort_by(|a, b| a.0[0].total_cmp(&b.0[0]));
    let total: f64 = kept.iter().map(|(_, weight)| weight).sum();
    let mut sum = 0.0;
    for (lab, weight) in &kept {
        sum += weight;
        if sum >= total / 2.0 {
            return Some((*lab, total));
        }
    }
    kept.last().map(|(lab, _)| (*lab, total))
}

/// The spread of one fractal noise's alpha in the renderer's grain filters
/// (two octaves of Perlin noise about one half): an assumption of this
/// estimate, not a value the SVG carries. With it the silverpoint grain came
/// within 0.02 of both silverpoint layers the prototype measured.
const NOISE_SPREAD: f64 = 0.11;

/// The elements of this name inside a node.
fn named<'a, 'input>(
    node: roxmltree::Node<'a, 'input>,
    name: &'static str,
) -> impl Iterator<Item = roxmltree::Node<'a, 'input>> {
    node.descendants()
        .filter(move |child| child.tag_name().name() == name)
}

/// A tool's grain filter: two fractal noises mixed by weights, whose alpha a
/// linear transfer turns into how much paint each pixel keeps.
#[derive(Clone, Copy, Debug, PartialEq)]
struct Grain {
    mean: f64,
    spread: f64,
    slope: f64,
    intercept: f64,
}

impl Grain {
    /// A filter's grain, when it is one this estimate reads: fractal noise
    /// mixed arithmetically and transferred linearly, with no morphology (a
    /// dilated noise, the pencil's, keeps nearly all the paint).
    fn of(filter: roxmltree::Node<'_, '_>) -> Option<Self> {
        if named(filter, "feMorphology").next().is_some()
            || named(filter, "feTurbulence").next().is_none()
        {
            return None;
        }
        let mix = named(filter, "feComposite")
            .find(|node| node.attribute("operator") == Some("arithmetic"))?;
        let transfer =
            named(filter, "feFuncA").find(|node| node.attribute("type") == Some("linear"))?;
        let (fine, coarse) = (attribute(mix, "k2")?, attribute(mix, "k3")?);
        Some(Self {
            mean: 0.5 * (fine + coarse),
            spread: NOISE_SPREAD * (fine * fine + coarse * coarse).sqrt(),
            slope: attribute(transfer, "slope")?,
            intercept: attribute(transfer, "intercept").unwrap_or(0.0),
        })
    }

    /// How much paint the grain leaves, at 40 even quantiles of its noise.
    fn deposits(self) -> Vec<f64> {
        (0..40)
            .map(|k| {
                let noise = self.mean + self.spread * normal_quantile((f64::from(k) + 0.5) / 40.0);
                (self.slope * noise + self.intercept).clamp(0.0, 1.0)
            })
            .collect()
    }
}

/// The standard normal quantile (Acklam's rational approximation).
fn normal_quantile(p: f64) -> f64 {
    const A: [f64; 6] = [
        -3.969_683_028_665_376e1,
        2.209_460_984_245_205e2,
        -2.759_285_104_469_687e2,
        1.383_577_518_672_69e2,
        -3.066_479_806_614_716e1,
        2.506_628_277_459_239,
    ];
    const B: [f64; 5] = [
        -5.447_609_879_822_406e1,
        1.615_858_368_580_409e2,
        -1.556_989_798_598_866e2,
        6.680_131_188_771_972e1,
        -1.328_068_155_288_572e1,
    ];
    const C: [f64; 6] = [
        -7.784_894_002_430_293e-3,
        -3.223_964_580_411_365e-1,
        -2.400_758_277_161_838,
        -2.549_732_539_343_734,
        4.374_664_141_464_968,
        2.938_163_982_698_783,
    ];
    const D: [f64; 4] = [
        7.784_695_709_041_462e-3,
        3.224_671_290_700_398e-1,
        2.445_134_137_142_996,
        3.754_408_661_907_416,
    ];
    let tail = |q: f64| {
        (((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    };
    if p < 0.024_25 {
        tail((-2.0 * p.ln()).sqrt())
    } else if p <= 1.0 - 0.024_25 {
        let q = p - 0.5;
        let r = q * q;
        (((((A[0] * r + A[1]) * r + A[2]) * r + A[3]) * r + A[4]) * r + A[5]) * q
            / (((((B[0] * r + B[1]) * r + B[2]) * r + B[3]) * r + B[4]) * r + 1.0)
    } else {
        -tail((-2.0 * (1.0 - p).ln()).sqrt())
    }
}

// --- reading the SVG ------------------------------------------------------------------------------

/// One drawn element of a mark: a filled outline or a stroked line.
#[derive(Clone, Debug, PartialEq)]
struct Element {
    filled: bool,
    /// `#rrggbb`, lower case.
    paint: String,
    /// The element's opacity with its groups' and any mask's over it.
    opacity: f64,
    class: Option<String>,
    /// Canvas points: closed rings for an outline, runs for a line.
    runs: Vec<Vec<[f64; 2]>>,
    /// An outline's area (rings inside rings are holes) and its rings' length;
    /// a line's length.
    area: f64,
    length: f64,
    /// A line's width.
    width: f64,
    /// The share of a line's length its dashes draw (1 for a solid line).
    dash: f64,
    /// The grain filter that deposits the paint, if any (silverpoint).
    grain: Option<Grain>,
    /// The group whose opacity the element takes, when one lowers it: two
    /// elements of one such group do not lay their paint twice where they
    /// overlap.
    holder: Option<roxmltree::NodeId>,
}

/// The elements of one instruction group.
type Mark = Vec<Element>;

#[derive(Clone, Copy, Debug, PartialEq)]
struct Affine([f64; 6]);

impl Affine {
    const IDENTITY: Self = Self([1.0, 0.0, 0.0, 1.0, 0.0, 0.0]);

    fn then(self, inner: Self) -> Self {
        let [a, b, c, d, e, f] = self.0;
        let [g, h, i, j, k, l] = inner.0;
        Self([
            a * g + c * h,
            b * g + d * h,
            a * i + c * j,
            b * i + d * j,
            a * k + c * l + e,
            b * k + d * l + f,
        ])
    }

    fn apply(self, [x, y]: [f64; 2]) -> [f64; 2] {
        let [a, b, c, d, e, f] = self.0;
        [a * x + c * y + e, b * x + d * y + f]
    }

    fn scale(self) -> f64 {
        let [a, b, c, d, ..] = self.0;
        (a * d - b * c).abs().sqrt()
    }

    /// An SVG transform list.
    fn parse(text: &str) -> Self {
        let mut out = Self::IDENTITY;
        for part in text.split(')') {
            let Some((name, arguments)) = part.split_once('(') else {
                continue;
            };
            let values = numbers(arguments);
            let one = match (name.trim(), values.as_slice()) {
                ("matrix", [a, b, c, d, e, f]) => Self([*a, *b, *c, *d, *e, *f]),
                ("translate", [x]) => Self([1.0, 0.0, 0.0, 1.0, *x, 0.0]),
                ("translate", [x, y]) => Self([1.0, 0.0, 0.0, 1.0, *x, *y]),
                ("scale", [s]) => Self([*s, 0.0, 0.0, *s, 0.0, 0.0]),
                ("scale", [sx, sy]) => Self([*sx, 0.0, 0.0, *sy, 0.0, 0.0]),
                ("rotate", [angle]) => rotation(*angle),
                ("rotate", [angle, cx, cy]) => Self([1.0, 0.0, 0.0, 1.0, *cx, *cy])
                    .then(rotation(*angle))
                    .then(Self([1.0, 0.0, 0.0, 1.0, -cx, -cy])),
                _ => Self::IDENTITY,
            };
            out = out.then(one);
        }
        out
    }
}

fn rotation(degrees: f64) -> Affine {
    let (sin, cos) = degrees.to_radians().sin_cos();
    Affine([cos, sin, -sin, cos, 0.0, 0.0])
}

/// The numbers of an attribute or a path, in order.
fn numbers(text: &str) -> Vec<f64> {
    path_tokens(text)
        .into_iter()
        .filter_map(|token| match token {
            Token::Number(value) => Some(value),
            Token::Command(_) => None,
        })
        .collect()
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Token {
    Command(char),
    Number(f64),
}

fn path_tokens(text: &str) -> Vec<Token> {
    let mut tokens = Vec::new();
    let chars: Vec<char> = text.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c.is_ascii_alphabetic() {
            tokens.push(Token::Command(c));
            i += 1;
        } else if c.is_ascii_digit() || c == '.' || c == '-' || c == '+' {
            let start = i;
            let mut seen_dot = false;
            let mut seen_exponent = false;
            if c == '-' || c == '+' {
                i += 1;
            }
            while i < chars.len() {
                let d = chars[i];
                if d.is_ascii_digit() {
                    i += 1;
                } else if d == '.' && !seen_dot && !seen_exponent {
                    seen_dot = true;
                    i += 1;
                } else if (d == 'e' || d == 'E') && !seen_exponent {
                    seen_exponent = true;
                    i += 1;
                    if i < chars.len() && (chars[i] == '-' || chars[i] == '+') {
                        i += 1;
                    }
                } else {
                    break;
                }
            }
            let text: String = chars[start..i].iter().collect();
            if let Ok(value) = text.parse::<f64>() {
                tokens.push(Token::Number(value));
            }
        } else {
            i += 1;
        }
    }
    tokens
}

/// Points in a run, and whether the run closes.
type Runs = Vec<(Vec<[f64; 2]>, bool)>;

/// The runs of a path's data: each subpath its points, closed or not. Curves
/// are followed by eight straight steps; an arc goes straight to its end.
fn path_runs(d: &str) -> Runs {
    let tokens = path_tokens(d);
    let mut runs = Vec::new();
    let mut current: Vec<[f64; 2]> = Vec::new();
    let mut pen = [0.0, 0.0];
    let mut start = [0.0, 0.0];
    let mut command = 'M';
    let mut i = 0;
    let take = |i: &mut usize, n: usize| -> Option<Vec<f64>> {
        let values: Vec<f64> = tokens
            .get(*i..*i + n)?
            .iter()
            .map(|token| match token {
                Token::Number(value) => Some(*value),
                Token::Command(_) => None,
            })
            .collect::<Option<Vec<f64>>>()?;
        *i += n;
        Some(values)
    };
    let finish = |current: &mut Vec<[f64; 2]>, runs: &mut Vec<(Vec<[f64; 2]>, bool)>, closed| {
        if current.len() >= 2 {
            runs.push((std::mem::take(current), closed));
        } else {
            current.clear();
        }
    };
    while i < tokens.len() {
        if let Token::Command(c) = tokens[i] {
            command = c;
            i += 1;
            if matches!(c, 'Z' | 'z') {
                finish(&mut current, &mut runs, true);
                pen = start;
                continue;
            }
        }
        let relative = command.is_ascii_lowercase();
        let origin = if relative { pen } else { [0.0, 0.0] };
        match command.to_ascii_uppercase() {
            'M' => {
                let Some(v) = take(&mut i, 2) else { break };
                finish(&mut current, &mut runs, false);
                pen = [origin[0] + v[0], origin[1] + v[1]];
                start = pen;
                current.push(pen);
                // The pairs after a move are lines.
                command = if relative { 'l' } else { 'L' };
            }
            'L' | 'T' => {
                let Some(v) = take(&mut i, 2) else { break };
                pen = [origin[0] + v[0], origin[1] + v[1]];
                current.push(pen);
            }
            'H' => {
                let Some(v) = take(&mut i, 1) else { break };
                pen = [if relative { pen[0] + v[0] } else { v[0] }, pen[1]];
                current.push(pen);
            }
            'V' => {
                let Some(v) = take(&mut i, 1) else { break };
                pen = [pen[0], if relative { pen[1] + v[0] } else { v[0] }];
                current.push(pen);
            }
            'Q' => {
                let Some(v) = take(&mut i, 4) else { break };
                let control = [origin[0] + v[0], origin[1] + v[1]];
                let end = [origin[0] + v[2], origin[1] + v[3]];
                for k in 1..=8 {
                    let t = f64::from(k) / 8.0;
                    let u = 1.0 - t;
                    current.push([
                        u * u * pen[0] + 2.0 * u * t * control[0] + t * t * end[0],
                        u * u * pen[1] + 2.0 * u * t * control[1] + t * t * end[1],
                    ]);
                }
                pen = end;
            }
            'S' => {
                let Some(v) = take(&mut i, 4) else { break };
                pen = [origin[0] + v[2], origin[1] + v[3]];
                current.push(pen);
            }
            'C' => {
                let Some(v) = take(&mut i, 6) else { break };
                let first = [origin[0] + v[0], origin[1] + v[1]];
                let second = [origin[0] + v[2], origin[1] + v[3]];
                let end = [origin[0] + v[4], origin[1] + v[5]];
                for k in 1..=8 {
                    let t = f64::from(k) / 8.0;
                    let u = 1.0 - t;
                    current.push([
                        u * u * u * pen[0]
                            + 3.0 * u * u * t * first[0]
                            + 3.0 * u * t * t * second[0]
                            + t * t * t * end[0],
                        u * u * u * pen[1]
                            + 3.0 * u * u * t * first[1]
                            + 3.0 * u * t * t * second[1]
                            + t * t * t * end[1],
                    ]);
                }
                pen = end;
            }
            'A' => {
                let Some(v) = take(&mut i, 7) else { break };
                pen = [origin[0] + v[5], origin[1] + v[6]];
                current.push(pen);
            }
            _ => break,
        }
    }
    finish(&mut current, &mut runs, false);
    runs
}

fn ring_area(points: &[[f64; 2]]) -> f64 {
    let mut sum = 0.0;
    for (k, p) in points.iter().enumerate() {
        let q = points[(k + 1) % points.len()];
        sum += p[0] * q[1] - q[0] * p[1];
    }
    sum / 2.0
}

fn run_length(points: &[[f64; 2]], closed: bool) -> f64 {
    let mut total = 0.0;
    for pair in points.windows(2) {
        total += ((pair[1][0] - pair[0][0]).powi(2) + (pair[1][1] - pair[0][1]).powi(2)).sqrt();
    }
    if closed && points.len() > 2 {
        let (first, last) = (points[0], points[points.len() - 1]);
        total += ((first[0] - last[0]).powi(2) + (first[1] - last[1]).powi(2)).sqrt();
    }
    total
}

fn inside(point: [f64; 2], ring: &[[f64; 2]]) -> bool {
    let mut found = false;
    let mut j = ring.len() - 1;
    for i in 0..ring.len() {
        let (a, b) = (ring[i], ring[j]);
        if (a[1] > point[1]) != (b[1] > point[1])
            && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            found = !found;
        }
        j = i;
    }
    found
}

/// The area the rings fill when a ring inside an odd number of others is a
/// hole (the renderer draws a closed outline as two rings, even-odd).
fn filled_area(rings: &[Vec<[f64; 2]>]) -> f64 {
    let mut total = 0.0;
    for (k, ring) in rings.iter().enumerate() {
        if ring.len() < 3 {
            continue;
        }
        let depth = rings
            .iter()
            .enumerate()
            .filter(|(other, outer)| *other != k && outer.len() >= 3 && inside(ring[0], outer))
            .count();
        let area = ring_area(ring).abs();
        total += if depth % 2 == 0 { area } else { -area };
    }
    total.max(0.0)
}

/// A circle or an ellipse as a ring of points.
fn ellipse_ring(cx: f64, cy: f64, rx: f64, ry: f64) -> Vec<[f64; 2]> {
    (0..32)
        .map(|k| {
            let (sin, cos) = (f64::from(k) * std::f64::consts::TAU / 32.0).sin_cos();
            [cx + rx * cos, cy + ry * sin]
        })
        .collect()
}

fn attribute(node: roxmltree::Node<'_, '_>, name: &str) -> Option<f64> {
    node.attribute(name)?.trim().parse().ok()
}

fn paint_of(value: Option<&str>) -> Option<String> {
    let value = value?.trim();
    (value.starts_with('#') && value.len() == 7).then(|| value.to_ascii_lowercase())
}

/// The geometry of a shape element: its runs (closed or not) before any
/// transform, and the exact area of a circle or an ellipse.
fn geometry(node: roxmltree::Node<'_, '_>) -> Option<(Runs, Option<f64>)> {
    let number = |name: &str| attribute(node, name).unwrap_or(0.0);
    Some(match node.tag_name().name() {
        "path" => (path_runs(node.attribute("d")?), None),
        "circle" => {
            let r = number("r");
            (
                vec![(ellipse_ring(number("cx"), number("cy"), r, r), true)],
                Some(std::f64::consts::PI * r * r),
            )
        }
        "ellipse" => {
            let (rx, ry) = (number("rx"), number("ry"));
            (
                vec![(ellipse_ring(number("cx"), number("cy"), rx, ry), true)],
                Some(std::f64::consts::PI * rx * ry),
            )
        }
        "rect" => {
            let (x, y, w, h) = (number("x"), number("y"), number("width"), number("height"));
            (
                vec![(vec![[x, y], [x + w, y], [x + w, y + h], [x, y + h]], true)],
                None,
            )
        }
        "line" => (
            vec![(
                vec![[number("x1"), number("y1")], [number("x2"), number("y2")]],
                false,
            )],
            None,
        ),
        "polyline" | "polygon" => {
            let values = numbers(node.attribute("points")?);
            let points: Vec<[f64; 2]> = values.as_chunks::<2>().0.to_vec();
            (vec![(points, node.tag_name().name() == "polygon")], None)
        }
        _ => return None,
    })
}

struct Walk<'a> {
    masks: &'a BTreeMap<String, f64>,
    grains: &'a BTreeMap<String, Grain>,
}

/// The id an attribute's `url(#id)` names.
fn reference(value: Option<&str>) -> Option<&str> {
    value?
        .trim()
        .strip_prefix("url(#")
        .and_then(|rest| rest.strip_suffix(')'))
}

impl Walk<'_> {
    /// The grain a node's filter deposits its paint with, else the one around it.
    fn grain(&self, node: roxmltree::Node<'_, '_>, around: Option<Grain>) -> Option<Grain> {
        match reference(node.attribute("filter")) {
            Some(id) if id.starts_with("tool-fill") => self.grains.get(id).copied(),
            _ => around,
        }
    }

    fn node(&self, node: roxmltree::Node<'_, '_>, around: Around, out: &mut Vec<Element>) {
        let own = attribute(node, "opacity").unwrap_or(1.0);
        let here = around.opacity * own;
        // The first group that lowers the opacity holds it for all it holds:
        // its marks are composed first and lowered together.
        let holder = match around.holder {
            None if own < 1.0 && node.tag_name().name() == "g" => Some(node.id()),
            holder => holder,
        };
        let grain = self.grain(node, around.grain);
        let mask = match node.attribute("mask") {
            Some(value) => {
                around.mask
                    * reference(Some(value))
                        .and_then(|id| self.masks.get(id))
                        .copied()
                        .unwrap_or(1.0)
            }
            None => around.mask,
        };
        let transform = match node.attribute("transform") {
            Some(text) => around.transform.then(Affine::parse(text)),
            None => around.transform,
        };
        if let Some((runs, exact_area)) = geometry(node) {
            let runs: Vec<(Vec<[f64; 2]>, bool)> = runs
                .into_iter()
                .map(|(points, closed)| {
                    (
                        points.into_iter().map(|p| transform.apply(p)).collect(),
                        closed,
                    )
                })
                .collect();
            let class = node.attribute("class").map(str::to_owned);
            let mask = round4(mask);
            // A fill drawn with a pattern (the computer's screen) has no paint
            // to read; it is kept so the layer is known to have it.
            let paint = match node.attribute("fill") {
                Some(fill) if fill.trim().starts_with("url(") => Some(PATTERN.to_owned()),
                fill => paint_of(fill),
            };
            if let Some(paint) = paint {
                let rings: Vec<Vec<[f64; 2]>> = runs
                    .iter()
                    .filter(|(points, _)| points.len() >= 3)
                    .map(|(points, _)| points.clone())
                    .collect();
                let area = exact_area.map_or_else(
                    || filled_area(&rings),
                    |area| area * transform.scale() * transform.scale(),
                );
                let length = rings.iter().map(|ring| run_length(ring, true)).sum();
                let fill = round4(here * attribute(node, "fill-opacity").unwrap_or(1.0));
                out.push(Element {
                    filled: true,
                    paint,
                    opacity: round4(fill * mask),
                    class: class.clone(),
                    runs: rings,
                    area,
                    length,
                    width: 0.0,
                    dash: 1.0,
                    grain,
                    holder,
                });
            }
            if let Some(paint) = paint_of(node.attribute("stroke")) {
                let stroke = round4(here * attribute(node, "stroke-opacity").unwrap_or(1.0));
                let length = runs
                    .iter()
                    .map(|(points, closed)| run_length(points, *closed))
                    .sum();
                out.push(Element {
                    filled: false,
                    paint,
                    opacity: round4(stroke * mask),
                    class,
                    runs: runs.into_iter().map(|(points, _)| points).collect(),
                    area: 0.0,
                    length,
                    width: attribute(node, "stroke-width").unwrap_or(1.0) * transform.scale(),
                    dash: node.attribute("stroke-dasharray").map_or(1.0, dash_share),
                    grain,
                    holder,
                });
            }
        }
        let around = Around {
            opacity: here,
            mask,
            transform,
            grain,
            holder,
        };
        for child in node.children().filter(roxmltree::Node::is_element) {
            self.node(child, around, out);
        }
    }
}

/// What the groups around an element give it.
#[derive(Clone, Copy, Debug)]
struct Around {
    opacity: f64,
    mask: f64,
    transform: Affine,
    grain: Option<Grain>,
    holder: Option<roxmltree::NodeId>,
}

/// The paint an element filled with a pattern is read as.
const PATTERN: &str = "pattern";

/// The share of a line a dash array draws: its dashes over its period (an odd
/// list is repeated, as SVG reads it).
fn dash_share(text: &str) -> f64 {
    let mut values = numbers(text);
    if values.len() % 2 == 1 {
        values.extend(values.clone());
    }
    let period: f64 = values.iter().sum();
    if values.is_empty() || period <= 0.0 {
        return 1.0;
    }
    values.iter().step_by(2).sum::<f64>() / period
}

/// The instruction groups of an editable SVG, by their performed number, and
/// what each drew.
fn read_svg(svg: &str) -> Option<BTreeMap<usize, Mark>> {
    let document = roxmltree::Document::parse(svg).ok()?;
    let mut masks = BTreeMap::new();
    for mask in document
        .descendants()
        .filter(|node| node.tag_name().name() == "mask")
    {
        // The renderer writes a mask's content in one group with its opacity.
        let opacity = mask
            .children()
            .find(|child| child.tag_name().name() == "g")
            .and_then(|group| attribute(group, "opacity"))
            .unwrap_or(1.0);
        if let Some(id) = mask.attribute("id") {
            masks.insert(id.to_owned(), opacity);
        }
    }
    let grains: BTreeMap<String, Grain> = document
        .descendants()
        .filter(|node| node.tag_name().name() == "filter")
        .filter_map(|filter| Some((filter.attribute("id")?.to_owned(), Grain::of(filter)?)))
        .collect();
    let content = document
        .descendants()
        .find(|node| node.attribute("id") == Some("layer_10_content"))?;
    let walk = Walk {
        masks: &masks,
        grains: &grains,
    };
    let mut groups = BTreeMap::new();
    // A fill group wraps its instructions in a clipped group, so instruction
    // groups are found at any depth; one never holds another.
    for group in content
        .descendants()
        .filter(|node| node.tag_name().name() == "g")
    {
        let Some(number) = group
            .attribute("id")
            .and_then(|id| id.strip_prefix("instruction_"))
            .and_then(|rest| rest.split('_').next())
            .and_then(|digits| digits.parse::<usize>().ok())
        else {
            continue;
        };
        // The groups around it may move it (a fill group's clip, a rigid
        // group); their opacity is not the mark's own.
        let mut transform = Affine::IDENTITY;
        let mut grain = None;
        for ancestor in group
            .ancestors()
            .skip(1)
            .filter(roxmltree::Node::is_element)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
        {
            if let Some(text) = ancestor.attribute("transform") {
                transform = transform.then(Affine::parse(text));
            }
            grain = walk.grain(ancestor, grain);
        }
        let mut elements = Vec::new();
        walk.node(
            group,
            Around {
                opacity: 1.0,
                mask: 1.0,
                transform,
                grain,
                holder: None,
            },
            &mut elements,
        );
        groups.insert(number, elements);
    }
    Some(groups)
}

// --- one layer ------------------------------------------------------------------------------------

/// The opacity the layer's own paint is mostly drawn with, the width of its
/// marks (the area-weighted median of its outlines, else the median of its
/// lines) and whether a line drew the most of it.
fn own_marks(marks: &[Mark], paint: &str) -> Option<(f64, f64, bool)> {
    // The (filled, class, opacity, width) of each element, counted in the
    // order first met.
    type Key<'a> = (bool, Option<&'a str>, u64, u64);
    let mut counted: Vec<(Key<'_>, usize)> = Vec::new();
    let mut outlines: Vec<(f64, f64)> = Vec::new();
    let mut lines: Vec<f64> = Vec::new();
    for element in marks
        .iter()
        .flatten()
        .filter(|element| element.paint == paint)
    {
        let key = (
            element.filled,
            element.class.as_deref(),
            element.opacity.to_bits(),
            if element.filled {
                0
            } else {
                element.width.to_bits()
            },
        );
        match counted.iter_mut().find(|(found, _)| *found == key) {
            Some((_, count)) => *count += 1,
            None => counted.push((key, 1)),
        }
        if element.filled {
            if element.area > 0.0 && element.length > 0.0 {
                outlines.push((2.0 * element.area / element.length, element.area));
            }
        } else {
            lines.push(element.width);
        }
    }
    let mut top: Option<(Key<'_>, usize)> = None;
    for (key, count) in &counted {
        if top.is_none_or(|(_, best)| *count > best) {
            top = Some((*key, *count));
        }
    }
    let ((filled, _, opacity, _), _) = top?;
    let width = if outlines.is_empty() {
        lines.sort_by(f64::total_cmp);
        *lines.get(lines.len() / 2)?
    } else {
        outlines.sort_by(|a, b| a.0.total_cmp(&b.0));
        let half = outlines.iter().map(|(_, area)| area).sum::<f64>() / 2.0;
        let mut sum = 0.0;
        let mut found = outlines[outlines.len() - 1].0;
        for (width, area) in &outlines {
            sum += area;
            if sum >= half {
                found = *width;
                break;
            }
        }
        found
    };
    Some((f64::from_bits(opacity), width, !filled))
}

/// The pixels a layer's own paint touches, in canvas units: a band its length
/// times its width and a pixel, a wide outline its area (the base fill and the
/// hand's bands; a fill's tiled overlay covers the same pixels). A layer with
/// no such outline counts its lines, each its length times its width and a
/// pixel.
fn touched_area(marks: &[Mark], paint: &str, scale: f64) -> f64 {
    let pixel = 1.0 / scale;
    let (mut outlines, mut lines) = (0.0, 0.0);
    for element in marks
        .iter()
        .flatten()
        .filter(|element| element.paint == paint)
    {
        if element.filled {
            let counted = element
                .class
                .as_deref()
                .is_none_or(|class| class == "solid-base-fill-v1" || class.contains("brush"));
            if !counted || element.area <= 0.0 || element.length <= 0.0 {
                continue;
            }
            let width = 2.0 * element.area / element.length;
            outlines += if width * scale < WIDE_BAND {
                element.length / 2.0 * (width + pixel)
            } else {
                element.area
            };
        } else {
            lines += element.length * (element.width.max(pixel) + pixel);
        }
    }
    if outlines > 0.0 { outlines } else { lines }
}

/// Whether an outline is one the touched area counts: a base fill or the
/// hand's band, not a fill's tiled overlay over the same pixels.
fn counted_outline(element: &Element) -> bool {
    element.filled
        && element.area > 0.0
        && element.length > 0.0
        && element
            .class
            .as_deref()
            .is_none_or(|class| class == "solid-base-fill-v1" || class.contains("brush"))
}

/// Left, top, right and bottom of an element's points, a line's grown by half
/// its width.
fn bounds(element: &Element) -> Option<[f64; 4]> {
    let grow = if element.filled {
        0.0
    } else {
        element.width / 2.0
    };
    let mut found: Option<[f64; 4]> = None;
    for [x, y] in element.runs.iter().flatten().copied() {
        found = Some(match found {
            None => [x, y, x, y],
            Some([l, t, r, b]) => [l.min(x), t.min(y), r.max(x), b.max(y)],
        });
    }
    found.map(|[l, t, r, b]| [l - grow, t - grow, r + grow, b + grow])
}

/// The median diameter of a layer's points: each mark's own paint across,
/// the mean of its width and height.
fn disc_diameter(marks: &[Mark], paint: &str) -> Option<f64> {
    let mut diameters: Vec<f64> = marks
        .iter()
        .filter_map(|mark| {
            let mut all: Option<[f64; 4]> = None;
            for element in mark.iter().filter(|element| element.paint == paint) {
                let Some([l, t, r, b]) = bounds(element) else {
                    continue;
                };
                all = Some(match all {
                    None => [l, t, r, b],
                    Some([l0, t0, r0, b0]) => [l0.min(l), t0.min(t), r0.max(r), b0.max(b)],
                });
            }
            all.map(|[l, t, r, b]| ((r - l) + (b - t)) / 2.0)
        })
        .collect();
    diameters.sort_by(f64::total_cmp);
    diameters.get(diameters.len() / 2).copied()
}

/// Whether a point lies inside an outline's rings (even-odd).
fn holds(element: &Element, point: [f64; 2]) -> bool {
    element
        .runs
        .iter()
        .filter(|ring| ring.len() >= 3 && inside(point, ring))
        .count()
        % 2
        == 1
}

/// The strengths of a layer of wide outlines that overlap one another: a
/// point under `k` of them takes the paint `k` times. The points are 64 by 64
/// over the outlines' bounds; the outlines of one group that holds their
/// opacity are composed before it lowers them, so they count once. `None`
/// when no two overlap.
fn overlapped(marks: &[Mark], paint: &str, opacity: f64) -> Option<Vec<(f64, f64)>> {
    let outlines: Vec<(&Element, [f64; 4])> = marks
        .iter()
        .flatten()
        .filter(|element| element.paint == paint && counted_outline(element))
        .filter_map(|element| Some((element, bounds(element)?)))
        .collect();
    let [left, top, right, bottom] = outlines
        .iter()
        .map(|(_, bounds)| *bounds)
        .reduce(|[l0, t0, r0, b0], [l, t, r, b]| [l0.min(l), t0.min(t), r0.max(r), b0.max(b)])?;
    let steps = 64;
    let mut counts: BTreeMap<usize, u32> = BTreeMap::new();
    for row in 0..steps {
        for column in 0..steps {
            let point = [
                left + (f64::from(column) + 0.5) / f64::from(steps) * (right - left),
                top + (f64::from(row) + 0.5) / f64::from(steps) * (bottom - top),
            ];
            let mut units: Vec<Option<roxmltree::NodeId>> = Vec::new();
            let mut alone = 0;
            for (element, [l, t, r, b]) in &outlines {
                if point[0] < *l
                    || point[0] > *r
                    || point[1] < *t
                    || point[1] > *b
                    || !holds(element, point)
                {
                    continue;
                }
                match element.holder {
                    Some(holder) if units.contains(&Some(holder)) => {}
                    Some(holder) => units.push(Some(holder)),
                    None => alone += 1,
                }
            }
            let under = units.len() + alone;
            if under > 0 {
                *counts.entry(under).or_insert(0) += 1;
            }
        }
    }
    let covered: u32 = counts.values().sum();
    if covered == 0 || counts.keys().all(|under| *under == 1) {
        return None;
    }
    let left_over = 1.0 - opacity.min(1.0);
    Some(
        counts
            .into_iter()
            .map(|(under, count)| {
                #[allow(clippy::cast_possible_truncation, clippy::cast_possible_wrap)]
                let laid = 1.0 - left_over.powi(under as i32);
                (laid, f64::from(count) / f64::from(covered))
            })
            .collect(),
    )
}

/// A dashed line drawn along a layer's thin bands (the pencil's grain): the
/// share of the bands' pixels its dashes cross and the strength it adds there.
/// `None` when the layer has no such line along its bands.
fn dashed_over(marks: &[Mark], paint: &str, scale: f64) -> Option<(f64, f64)> {
    let own = || {
        marks
            .iter()
            .flatten()
            .filter(|element| element.paint == paint)
    };
    let bands: f64 = own()
        .filter(|element| counted_outline(element))
        .filter(|element| 2.0 * element.area / element.length * scale < WIDE_BAND)
        .map(|element| element.length / 2.0)
        .sum();
    let dashed: Vec<&Element> = own()
        .filter(|element| !element.filled && element.dash < 1.0 && element.length > 0.0)
        .collect();
    let length: f64 = dashed.iter().map(|element| element.length).sum();
    if bands <= 0.0 || length < bands / 2.0 {
        return None;
    }
    let share = dashed
        .iter()
        .map(|element| element.dash * element.length)
        .sum::<f64>()
        / length;
    let strength = dashed
        .iter()
        .map(|element| element.opacity * (element.width * scale).min(1.0) * element.length)
        .sum::<f64>()
        / length;
    Some((share, strength.min(1.0)))
}

#[allow(clippy::too_many_arguments)]
fn layer_look(
    marks: &[Mark],
    paint: [u8; 3],
    ground: [u8; 3],
    points: bool,
    scale: f64,
    canvas_area: f64,
    shares: &mut Shares,
) -> Look {
    let code = format!("#{:02x}{:02x}{:02x}", paint[0], paint[1], paint[2]);
    let ground_lab = lab_of(ground);
    let pattern: f64 = marks
        .iter()
        .flatten()
        .filter(|element| element.paint == PATTERN)
        .map(|element| element.area)
        .sum();
    let own = own_marks(marks, &code);
    let (Some((opacity, width, line)), false) = (own, pattern > 0.0) else {
        // Nothing in its own paint, or a pattern fill whose colors are not
        // read (the computer's screen): the paint as it is, over the largest
        // outline each mark fills.
        let lab = lab_of(paint);
        let filled: f64 = marks
            .iter()
            .map(|mark| {
                mark.iter()
                    .filter(|element| element.filled && element.paint != PATTERN)
                    .map(|element| element.area)
                    .fold(0.0, f64::max)
            })
            .sum();
        return Look {
            lab: Some(lab),
            contrast: (lab[0] - ground_lab[0]).abs() / 100.0,
            chroma: lab[1].hypot(lab[2]),
            ink: (filled / canvas_area).min(1.0),
            read: false,
            opacity: 1.0,
            width: 0.0,
            cover: "none",
        };
    };
    let (cover, width) = if line {
        (Cover::Stroke, width)
    } else if points {
        // A point's disc and the hand's ring around it cover one disc out to
        // the ring's outer edge.
        (
            Cover::Disc,
            disc_diameter(marks, &code).unwrap_or(2.0 * width),
        )
    } else {
        (Cover::Band, width)
    };
    let mut pixels: Vec<(f64, f64)> = shares
        .of(cover, width * scale)
        .into_iter()
        .map(|(covered, weight)| (opacity * covered, weight))
        .collect();
    if cover == Cover::Band && width * scale >= WIDE_BAND {
        pixels = overlapped(marks, &code, opacity).unwrap_or(pixels);
    } else if cover == Cover::Band
        && let Some((share, strength)) = dashed_over(marks, &code, scale)
    {
        // A dashed line drawn over the band deepens the pixels it crosses.
        pixels = pixels
            .into_iter()
            .flat_map(|(alpha, weight)| {
                [
                    (alpha, (1.0 - share) * weight),
                    (
                        1.0 - (1.0 - alpha.min(1.0)) * (1.0 - strength),
                        share * weight,
                    ),
                ]
            })
            .collect();
    }
    if let Some(grain) = marks
        .iter()
        .flatten()
        .filter(|element| element.paint == code)
        .find_map(|element| element.grain)
    {
        let deposits = grain.deposits();
        let part = 1.0 / deposits.len() as f64;
        pixels = pixels
            .into_iter()
            .flat_map(|(alpha, weight)| {
                deposits
                    .iter()
                    .map(move |deposit| (alpha * deposit, weight * part))
            })
            .collect();
    }
    let found = median_ink(paint, ground, &pixels);
    let ink = found.map_or(0.0, |(_, kept)| {
        (touched_area(marks, &code, scale) / canvas_area).min(1.0) * kept
    });
    let name = match cover {
        Cover::Band => "band",
        Cover::Stroke => "stroke",
        Cover::Disc => "disc",
    };
    match found {
        Some((lab, _)) => Look {
            lab: Some(lab),
            contrast: (lab[0] - ground_lab[0]).abs() / 100.0,
            chroma: lab[1].hypot(lab[2]),
            ink,
            read: true,
            opacity,
            width: width * scale,
            cover: name,
        },
        None => Look {
            lab: None,
            contrast: 0.0,
            chroma: 0.0,
            ink: 0.0,
            read: true,
            opacity,
            width: width * scale,
            cover: name,
        },
    }
}

// --- touching layers ------------------------------------------------------------------------------

/// The cells of a grid of `TOUCH_CELL` pixels a layer's marks lie on.
struct Cells {
    columns: i64,
    rows: i64,
    size: f64,
}

impl Cells {
    #[allow(clippy::cast_possible_truncation)]
    fn of(&self, [x, y]: [f64; 2]) -> Option<(i64, i64)> {
        let (column, row) = (
            (x / self.size).floor() as i64,
            (y / self.size).floor() as i64,
        );
        ((0..self.columns).contains(&column) && (0..self.rows).contains(&row))
            .then_some((column, row))
    }

    fn mark(&self, element: &Element, cells: &mut BTreeSet<(i64, i64)>) {
        for run in &element.runs {
            // Along the run, every half cell.
            let closed = element.filled;
            let count = run.len();
            let segments = if closed {
                count
            } else {
                count.saturating_sub(1)
            };
            for k in 0..segments {
                let (a, b) = (run[k], run[(k + 1) % count]);
                let length = ((b[0] - a[0]).powi(2) + (b[1] - a[1]).powi(2)).sqrt();
                #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
                let steps = (length / (self.size / 2.0)).ceil().max(1.0) as usize;
                for step in 0..=steps {
                    let t = step as f64 / steps as f64;
                    if let Some(cell) =
                        self.of([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
                    {
                        cells.insert(cell);
                    }
                }
            }
        }
        if element.filled && element.area > self.size * self.size {
            // The cells whose centers the outline holds.
            let points = element.runs.iter().flatten();
            let (mut left, mut top, mut right, mut bottom) =
                (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
            for p in points {
                left = left.min(p[0]);
                top = top.min(p[1]);
                right = right.max(p[0]);
                bottom = bottom.max(p[1]);
            }
            #[allow(clippy::cast_possible_truncation)]
            let (c0, c1, r0, r1) = (
                (left / self.size).floor().max(0.0) as i64,
                ((right / self.size).ceil() as i64).min(self.columns - 1),
                (top / self.size).floor().max(0.0) as i64,
                ((bottom / self.size).ceil() as i64).min(self.rows - 1),
            );
            for column in c0..=c1 {
                for row in r0..=r1 {
                    let center = [
                        (column as f64 + 0.5) * self.size,
                        (row as f64 + 0.5) * self.size,
                    ];
                    let depth = element
                        .runs
                        .iter()
                        .filter(|ring| ring.len() >= 3 && inside(center, ring))
                        .count();
                    if depth % 2 == 1 {
                        cells.insert((column, row));
                    }
                }
            }
        }
    }
}

/// Which layers touch: their marks' cells, each grown by a cell, meet.
fn touching(
    drawn: &BTreeMap<usize, Vec<Mark>>,
    canvas: CanvasSize,
    scale: f64,
) -> BTreeMap<usize, BTreeSet<usize>> {
    let size = TOUCH_CELL / scale;
    #[allow(clippy::cast_possible_truncation)]
    let grid = Cells {
        columns: (canvas.width / size).ceil() as i64,
        rows: (canvas.height / size).ceil() as i64,
        size,
    };
    let mut grown: BTreeMap<usize, BTreeSet<(i64, i64)>> = BTreeMap::new();
    for (layer, marks) in drawn {
        let mut cells = BTreeSet::new();
        for element in marks.iter().flatten() {
            if element.opacity > 0.0 {
                grid.mark(element, &mut cells);
            }
        }
        let mut wide = cells.clone();
        for (column, row) in cells {
            for (dc, dr) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                wide.insert((column + dc, row + dr));
            }
        }
        grown.insert(*layer, wide);
    }
    let mut out: BTreeMap<usize, BTreeSet<usize>> = grown
        .keys()
        .map(|layer| (*layer, BTreeSet::new()))
        .collect();
    let layers: Vec<usize> = grown.keys().copied().collect();
    for (k, a) in layers.iter().enumerate() {
        for b in &layers[k + 1..] {
            if !grown[a].is_disjoint(&grown[b]) {
                out.get_mut(a).expect("layer").insert(*b);
                out.get_mut(b).expect("layer").insert(*a);
            }
        }
    }
    out
}
