//! Display-profile material filters kept outside portable mark geometry.

use crate::determinism::hash01;
use crate::svg::{Element, format_number};
use crate::types::{CanvasSize, Point, Seed, SurfaceIntensity, Weight};

/// How far the ridges of an oil stroke step away from its pigment.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum OilTone {
    Normal,
    Dense,
}

/// One OKLCH step: lightness added, chroma multiplied, and the hue turned
/// towards a cool shadow or a warm light by at most `turn` degrees.
#[derive(Clone, Copy)]
struct ToneStep {
    lightness: f64,
    chroma: f64,
    turn: f64,
    target_hue: f64,
}

const COOL_HUE: f64 = 250.0;
const WARM_HUE: f64 = 75.0;
/// Below this chroma a pigment counts as neutral and is given a faint tint.
const NEUTRAL_CHROMA: f64 = 0.025;
const NEUTRAL_TINT: f64 = 0.008;

impl OilTone {
    fn dark(self) -> ToneStep {
        match self {
            Self::Normal => ToneStep {
                lightness: -0.045,
                chroma: 1.06,
                turn: 4.0,
                target_hue: COOL_HUE,
            },
            Self::Dense => ToneStep {
                lightness: -0.070,
                chroma: 1.08,
                turn: 5.0,
                target_hue: COOL_HUE,
            },
        }
    }

    fn light(self) -> ToneStep {
        match self {
            Self::Normal => ToneStep {
                lightness: 0.030,
                chroma: 0.94,
                turn: 4.0,
                target_hue: WARM_HUE,
            },
            Self::Dense => ToneStep {
                lightness: 0.045,
                chroma: 0.92,
                turn: 5.0,
                target_hue: WARM_HUE,
            },
        }
    }
}

pub(crate) struct OilPaintStyle<'a> {
    pub color: &'a str,
    pub opacity: f64,
    tone: OilTone,
    tolerance: f64,
    /// An open line or arc: its own marks stay wider and longer than a fill pass's.
    line: bool,
}

impl<'a> OilPaintStyle<'a> {
    pub fn plain(color: &'a str, opacity: f64) -> Self {
        Self {
            color,
            opacity,
            tone: OilTone::Dense,
            tolerance: 0.0,
            line: false,
        }
    }

    /// A drawn line, arc or the outline of an unfilled shape.
    pub fn stroke(color: &'a str, opacity: f64) -> Self {
        Self {
            line: true,
            ..Self::plain(color, opacity)
        }
    }

    pub fn filled(
        color: &'a str,
        opacity: f64,
        intensity: SurfaceIntensity,
        canvas: CanvasSize,
    ) -> Self {
        let dense = intensity == SurfaceIntensity::Dense;
        Self {
            color,
            opacity: opacity
                * if intensity == SurfaceIntensity::Faint {
                    0.54
                } else {
                    1.0
                },
            tone: if dense {
                OilTone::Dense
            } else {
                OilTone::Normal
            },
            tolerance: if dense { canvas.unit() * 0.00025 } else { 0.0 },
            line: false,
        }
    }
}

fn srgb_to_linear(channel: f64) -> f64 {
    if channel <= 0.04045 {
        channel / 12.92
    } else {
        ((channel + 0.055) / 1.055).powf(2.4)
    }
}

fn linear_to_srgb(channel: f64) -> f64 {
    if channel <= 0.003_130_8 {
        channel * 12.92
    } else {
        1.055 * channel.powf(1.0 / 2.4) - 0.055
    }
}

fn parse_pigment(color: &str) -> Option<[f64; 3]> {
    let raw = color.strip_prefix('#').unwrap_or(color);
    if raw.len() != 6 || !raw.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    let channel = |start: usize| {
        srgb_to_linear(f64::from(u8::from_str_radix(&raw[start..start + 2], 16).unwrap()) / 255.0)
    };
    Some([channel(0), channel(2), channel(4)])
}

fn oklab([r, g, b]: [f64; 3]) -> [f64; 3] {
    let l = (0.412_221_470_8 * r + 0.536_332_536_3 * g + 0.051_445_992_9 * b).cbrt();
    let m = (0.211_903_498_2 * r + 0.680_699_545_1 * g + 0.107_396_956_6 * b).cbrt();
    let s = (0.088_302_461_9 * r + 0.281_718_837_6 * g + 0.629_978_700_5 * b).cbrt();
    [
        0.210_454_255_3 * l + 0.793_617_785_0 * m - 0.004_072_046_8 * s,
        1.977_998_495_1 * l - 2.428_592_205_0 * m + 0.450_593_709_9 * s,
        0.025_904_037_1 * l + 0.782_771_766_2 * m - 0.808_675_766_0 * s,
    ]
}

fn linear_from_oklab([lightness, a, b]: [f64; 3]) -> [f64; 3] {
    let l = (lightness + 0.396_337_777_4 * a + 0.215_803_757_3 * b).powi(3);
    let m = (lightness - 0.105_561_345_8 * a - 0.063_854_172_8 * b).powi(3);
    let s = (lightness - 0.089_484_177_5 * a - 1.291_485_548_0 * b).powi(3);
    [
        4.076_741_662_1 * l - 3.307_711_591_3 * m + 0.230_969_929_2 * s,
        -1.268_438_004_6 * l + 2.609_757_401_1 * m - 0.341_319_396_5 * s,
        -0.004_196_086_3 * l - 0.703_418_614_7 * m + 1.707_614_701_0 * s,
    ]
}

/// The pigment moved in OKLCH. Lightness and hue are kept exactly; chroma gives
/// way until sRGB can hold the colour, so no channel is ever clipped.
fn adjust_pigment(color: &str, change: impl Fn(f64, f64, f64) -> (f64, f64, f64)) -> String {
    let Some(rgb) = parse_pigment(color) else {
        return color.to_owned();
    };
    let [lightness, a, b] = oklab(rgb);
    let (lightness, chroma, hue) = change(
        lightness,
        a.hypot(b),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    );
    let lightness = lightness.clamp(0.0, 1.0);
    let (sin, cos) = hue.to_radians().sin_cos();
    let at = |chroma: f64| linear_from_oklab([lightness, chroma * cos, chroma * sin]);
    let fits = |rgb: [f64; 3]| {
        rgb.iter()
            .all(|channel| (-1e-9..=1.0 + 1e-9).contains(channel))
    };
    let mut chroma = chroma.max(0.0);
    if !fits(at(chroma)) {
        let (mut low, mut high) = (0.0, chroma);
        for _ in 0..32 {
            let middle = (low + high) * 0.5;
            if fits(at(middle)) {
                low = middle;
            } else {
                high = middle;
            }
        }
        chroma = low;
    }
    let rgb = at(chroma).map(|channel| {
        (linear_to_srgb(channel.clamp(0.0, 1.0)) * 255.0)
            .round()
            .clamp(0.0, 255.0) as u8
    });
    format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2])
}

fn turn_towards(hue: f64, target: f64, limit: f64) -> f64 {
    let difference = (target - hue + 540.0).rem_euclid(360.0) - 180.0;
    (hue + difference.clamp(-limit, limit)).rem_euclid(360.0)
}

/// A ridge keeps the pigment's colour: it steps in lightness, keeps its chroma
/// and leans cool in shadow and warm in light, instead of greying towards black
/// or white. A neutral pigment gets a faint cool shadow and warm light.
fn ridge_tone(color: &str, step: ToneStep) -> String {
    adjust_pigment(color, |lightness, chroma, hue| {
        let lightness = (lightness + step.lightness).clamp(0.12, 0.97);
        if chroma < NEUTRAL_CHROMA {
            (lightness, chroma.max(NEUTRAL_TINT), step.target_hue)
        } else {
            (
                lightness,
                chroma * step.chroma,
                turn_towards(hue, step.target_hue, step.turn),
            )
        }
    })
}

/// The pigment of a flat brush's bristle streak: the same hue and chroma,
/// `step` lighter or darker in OKLCH.
pub(crate) fn bristle_tone(color: &str, step: f64) -> String {
    adjust_pigment(color, |lightness, chroma, hue| {
        ((lightness + step).clamp(0.0, 1.0), chroma, hue)
    })
}

/// The colour one loaded pass carries: the pigment varied a little in OKLCH,
/// never mixed with black or white.
pub(crate) fn oil_paint_load(color: &str, seed: Seed, order: i64) -> String {
    let lightness = (hash01(order, seed, "oil-fill-load") - 0.5) * 0.016;
    let chroma = 1.0 + (hash01(order, seed, "oil-fill-load-chroma") - 0.5) * 0.08;
    let hue = (hash01(order, seed, "oil-fill-load-hue") - 0.5) * 3.0;
    adjust_pigment(color, |l, c, h| (l + lightness, c * chroma, h + hue))
}

fn segment_distance(point: Point, start: Point, end: Point) -> f64 {
    let dx = end.x - start.x;
    let dy = end.y - start.y;
    let length = dx * dx + dy * dy;
    let t = if length == 0.0 {
        0.0
    } else {
        ((point.x - start.x) * dx + (point.y - start.y) * dy) / length
    }
    .clamp(0.0, 1.0);
    (point.x - start.x - t * dx).hypot(point.y - start.y - t * dy)
}

/// Select the same vertices on both banks, preserving loaded shoulders and width.
fn simplify_oil_ridge(left: &mut Vec<Point>, right: &mut Vec<Point>, closed: bool, tolerance: f64) {
    if tolerance <= 0.0 || left.len() < 3 {
        return;
    }
    let original_len = left.len();
    if closed {
        left.push(left[0]);
        right.push(right[0]);
    }
    let last = left.len() - 1;
    let mut keep = std::collections::BTreeSet::from([0, last]);
    if !closed {
        keep.insert(last.div_ceil(12));
        keep.insert(last * 11 / 12);
        let widest = (0..=last)
            .max_by(|&a, &b| {
                (left[a].x - right[a].x)
                    .hypot(left[a].y - right[a].y)
                    .total_cmp(&(left[b].x - right[b].x).hypot(left[b].y - right[b].y))
                    .then_with(|| (2 * b).abs_diff(last).cmp(&(2 * a).abs_diff(last)))
            })
            .unwrap();
        keep.insert(widest);
    }
    let anchors = keep.iter().copied().collect::<Vec<_>>();
    let mut pending = anchors
        .windows(2)
        .map(|pair| (pair[0], pair[1]))
        .collect::<Vec<_>>();
    while let Some((start, end)) = pending.pop() {
        let candidate = (start + 1..end)
            .map(|index| {
                let error = segment_distance(left[index], left[start], left[end])
                    .max(segment_distance(right[index], right[start], right[end]));
                (index, error)
            })
            .max_by(|a, b| a.1.total_cmp(&b.1).then(a.0.cmp(&b.0)));
        if let Some((index, _)) = candidate.filter(|(_, error)| *error > tolerance) {
            keep.insert(index);
            pending.extend([(start, index), (index, end)]);
        }
    }
    if closed && keep.len() < 4 {
        left.truncate(original_len);
        right.truncate(original_len);
        return;
    }
    if closed {
        keep.remove(&last);
    }
    *left = keep.iter().map(|&index| left[index]).collect();
    *right = keep.iter().map(|&index| right[index]).collect();
}

/// Bounded, filter-free bristle marks follow the performed banks in every
/// profile. A pass carries two to five marks of its own pigment, each a little
/// darker or lighter, set at seeded places across it and running only part of
/// its length, so neighbouring passes do not line up into a grain. Where the
/// pass pinches, a mark thins away instead of meeting the others in a point.
pub(crate) fn oil_paint_stroke(
    path: String,
    left: &[Point],
    right: &[Point],
    style: OilPaintStyle<'_>,
    seed: Seed,
    closed: bool,
) -> Element {
    let mut group = Element::new("g")
        .attr("class", "oil-paint-stroke-v1")
        .attr("opacity", format_number(style.opacity));
    group.push(
        Element::new("path")
            .attr("d", path)
            .attr("class", "oil-paint-body-v1")
            .attr("fill", style.color)
            .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
            .attr("stroke", "none"),
    );
    if left.len() < 2 || left.len() != right.len() {
        return group;
    }
    let dark = ridge_tone(style.color, style.tone.dark());
    let light = ridge_tone(style.color, style.tone.light());
    let widths = left
        .iter()
        .zip(right)
        .map(|(a, b)| (b.x - a.x).hypot(b.y - a.y))
        .collect::<Vec<_>>();
    let mut sorted = widths.clone();
    sorted.sort_by(f64::total_cmp);
    let median = sorted[sorted.len() / 2].max(f64::MIN_POSITIVE);
    let base = if style.tone == OilTone::Dense { 3 } else { 2 };
    let mut count = base + (hash01(0, seed, "oil-streak-count") * 3.0).floor().min(2.0) as usize;
    if closed {
        count = count.min(2);
    }
    // One light from the upper left: a pass painted the other way still
    // catches it on the same side of its ridge.
    let middle = left.len() / 2;
    let across = Point::new(
        right[middle].x - left[middle].x,
        right[middle].y - left[middle].y,
    );
    let lit_towards_right = -across.x - across.y > 0.0;
    let paired = style.tone == OilTone::Dense && hash01(0, seed, "oil-streak-pair") < 0.5;
    let span = (left.len() - usize::from(!closed)) as f64;
    let bin = 0.88 / count as f64;
    for streak in 0..count {
        let index = streak as i64;
        let center =
            0.06 + bin * (streak as f64 + 0.15 + 0.70 * hash01(index, seed, "oil-streak-position"));
        let line = style.line && !closed;
        let (narrowest, widest, latest_start, shortest) = if line {
            (0.024, 0.05, 0.15, 0.6)
        } else {
            (0.012, 0.03, 0.35, 0.4)
        };
        let width = narrowest + (widest - narrowest) * hash01(index, seed, "oil-streak-width");
        let start = latest_start * hash01(index, seed, "oil-streak-start");
        let end =
            start + shortest + (1.0 - shortest - start) * hash01(index, seed, "oil-streak-end");
        let phase = hash01(index, seed, "oil-ridge-phase") * std::f64::consts::TAU;
        let mut bands = vec![(center, width, hash01(index, seed, "oil-streak-dark") < 0.6)];
        if paired && streak == 0 {
            bands[0].2 = true;
            bands.push(if lit_towards_right {
                (center + width, width * 0.65, false)
            } else {
                (center - width * 0.65, width * 0.65, false)
            });
        }
        for (center, band_width, is_dark) in bands {
            let mut bank_a = Vec::new();
            let mut bank_b = Vec::new();
            for (sample, (a, b)) in left.iter().zip(right).enumerate() {
                let t = sample as f64 / span;
                if t < start || t > end {
                    continue;
                }
                let along = (t - start) / (end - start);
                let fade = (along / 0.15).min((1.0 - along) / 0.15).clamp(0.0, 1.0);
                let terminal = if closed {
                    1.0
                } else {
                    (t * 12.0).min((1.0 - t) * 12.0).min(1.0)
                };
                let neck = ((widths[sample] / median - 0.35) / 0.15).clamp(0.0, 1.0);
                let wave = (t * std::f64::consts::TAU * 2.0 + phase).sin() * 0.018;
                let at = |fraction: f64| {
                    Point::new(a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction)
                };
                bank_a.push(at(center + wave));
                bank_b.push(at(center + wave + band_width * fade * terminal * neck));
            }
            if bank_a.len() < 2 {
                continue;
            }
            simplify_oil_ridge(&mut bank_a, &mut bank_b, false, style.tolerance);
            bank_a.extend(bank_b.into_iter().rev());
            group.push(
                Element::new("path")
                    .attr("d", crate::mark_paths::polygon_path(&bank_a))
                    .attr(
                        "class",
                        if is_dark {
                            "oil-paint-ridge-shadow-v1"
                        } else {
                            "oil-paint-ridge-light-v1"
                        },
                    )
                    .attr(
                        "fill",
                        if is_dark {
                            dark.as_str()
                        } else {
                            light.as_str()
                        },
                    )
                    .attr("fill-rule", "nonzero")
                    .attr("stroke", "none"),
            );
        }
    }
    group
}

#[derive(Clone, Copy)]
struct TextureSpec {
    margin: u8,
    base_frequency: Option<f64>,
    octaves: u8,
    noise_seed: u16,
    displacement: Option<f64>,
    blur: Option<f64>,
}

fn texture_spec(weight: Weight) -> Option<TextureSpec> {
    match weight {
        Weight::Pencil => Some(TextureSpec {
            margin: 12,
            base_frequency: Some(0.9),
            octaves: 2,
            noise_seed: 11,
            displacement: Some(0.7),
            blur: None,
        }),
        Weight::Crayon => Some(TextureSpec {
            margin: 18,
            base_frequency: Some(0.55),
            octaves: 3,
            noise_seed: 17,
            displacement: Some(1.8),
            blur: None,
        }),
        Weight::Chalk => Some(TextureSpec {
            margin: 25,
            base_frequency: Some(0.75),
            octaves: 3,
            noise_seed: 23,
            displacement: Some(2.2),
            blur: Some(0.25),
        }),
        Weight::BrushThick => Some(TextureSpec {
            margin: 20,
            base_frequency: Some(0.2),
            octaves: 2,
            noise_seed: 31,
            displacement: Some(1.4),
            blur: Some(0.6),
        }),
        Weight::Drypoint => Some(TextureSpec {
            margin: 35,
            base_frequency: None,
            octaves: 0,
            noise_seed: 0,
            displacement: None,
            blur: Some(1.8),
        }),
        _ => None,
    }
}

#[must_use]
pub fn texture_filter_id(weight: Weight) -> Option<&'static str> {
    match weight {
        Weight::Pencil => Some("texture-pencil"),
        Weight::Crayon => Some("texture-crayon"),
        Weight::Chalk => Some("texture-chalk"),
        Weight::BrushThick => Some("texture-brush_thick"),
        Weight::Drypoint => Some("texture-drypoint"),
        _ => None,
    }
}

#[must_use]
pub fn texture_filter(weight: Weight, canvas: CanvasSize) -> Option<Element> {
    let spec = texture_spec(weight)?;
    let id = texture_filter_id(weight)?;
    let scale = canvas.unit() / 1000.0;
    let mut filter = Element::new("filter")
        .attr("id", id)
        .attr("x", format!("-{}%", spec.margin))
        .attr("y", format!("-{}%", spec.margin))
        .attr("width", format!("{}%", 100 + u16::from(spec.margin) * 2))
        .attr("height", format!("{}%", 100 + u16::from(spec.margin) * 2));
    if let Some(frequency) = spec.base_frequency {
        filter.push(
            Element::new("feTurbulence")
                .attr("type", "fractalNoise")
                .attr("baseFrequency", format_number(frequency / scale))
                .attr("numOctaves", spec.octaves.to_string())
                .attr("seed", spec.noise_seed.to_string())
                .attr("result", "noise"),
        );
        filter.push(
            Element::new("feDisplacementMap")
                .attr("in", "SourceGraphic")
                .attr("in2", "noise")
                .attr(
                    "scale",
                    format_number(spec.displacement.unwrap_or_default() * scale * 2.8),
                ),
        );
    }
    if let Some(blur) = spec.blur {
        filter.push(
            Element::new("feGaussianBlur").attr("stdDeviation", format_number(blur * scale * 1.6)),
        );
    }
    Some(filter)
}

#[must_use]
pub fn with_texture_filter(mut element: Element, weight: Weight, enabled: bool) -> Element {
    if enabled
        && weight != Weight::Drypoint
        && let Some(id) = texture_filter_id(weight)
    {
        element.set_attr("filter", format!("url(#{id})"));
    }
    element
}

/// The whole-drawing touch, a displacement sampled in user space.
///
/// Display applies it once, to the content group; live (and a Score with fill
/// scopes) to each instruction group, which a host may draw on its own. The
/// region is the canvas plus 2% on each side in user space. A region measured
/// from the group's bounding box would cut displaced pixels wherever 2% of the
/// box is narrower than the displacement (at most 3 units per 1,000 of the
/// short side): a thin drawing, a small group, or content that shrinks when
/// strokes off the canvas are left out. The groups it is applied to carry no
/// transform, so their user space is the canvas.
#[must_use]
pub fn performance_touch_filter(seed: Seed, canvas: CanvasSize) -> (String, Element) {
    let id = format!("performance_touch_{}", seed.rem_euclid(100_000));
    let scale = canvas.unit() / 1000.0;
    let frequency = (0.012 + hash01(0, seed, "performance-touch-frequency") * 0.008) / scale;
    let displacement = (1.6 + hash01(1, seed, "performance-touch-scale") * 1.4) * scale;
    let filter = Element::new("filter")
        .attr("id", &id)
        .attr("filterUnits", "userSpaceOnUse")
        .attr("x", format_number(-0.02 * canvas.width))
        .attr("y", format_number(-0.02 * canvas.height))
        .attr("width", format_number(1.04 * canvas.width))
        .attr("height", format_number(1.04 * canvas.height));
    let mut filter = filter.attr("color-interpolation-filters", "sRGB");
    filter.push(
        Element::new("feTurbulence")
            .attr("type", "fractalNoise")
            .attr("baseFrequency", format_number(frequency))
            .attr("numOctaves", "2")
            .attr("seed", seed.rem_euclid(9973).to_string())
            .attr("result", "touchNoise"),
    );
    filter.push(
        Element::new("feDisplacementMap")
            .attr("in", "SourceGraphic")
            .attr("in2", "touchNoise")
            .attr("scale", format_number(displacement))
            .attr("xChannelSelector", "R")
            .attr("yChannelSelector", "G"),
    );
    (id, filter)
}
