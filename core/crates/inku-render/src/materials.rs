//! Display-profile material filters kept outside portable mark geometry.

use crate::determinism::hash01;
use crate::svg::{Element, format_number};
use crate::types::{CanvasSize, Point, Seed, Weight};

/// Preserve the selected pigment while shading the sides of a raised paint ridge.
pub(crate) fn oil_paint_shade(color: &str, amount: f64) -> String {
    let raw = color.strip_prefix('#').unwrap_or(color);
    if raw.len() != 6 || !raw.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return color.to_owned();
    }
    let channel = |start| {
        let value = f64::from(u8::from_str_radix(&raw[start..start + 2], 16).unwrap());
        let shaded = if amount >= 0.0 {
            value + (255.0 - value) * amount
        } else {
            value * (1.0 + amount)
        };
        shaded.round().clamp(0.0, 255.0) as u8
    };
    format!("#{:02x}{:02x}{:02x}", channel(0), channel(2), channel(4))
}

/// Bounded, filter-free bristle relief follows the performed banks in every profile.
pub(crate) fn oil_paint_stroke(
    path: String,
    left: &[Point],
    right: &[Point],
    color: &str,
    opacity: f64,
    seed: Seed,
    closed: bool,
) -> Element {
    let mut group = Element::new("g")
        .attr("class", "oil-paint-stroke-v1")
        .attr("opacity", format_number(opacity));
    group.push(
        Element::new("path")
            .attr("d", path)
            .attr("class", "oil-paint-body-v1")
            .attr("fill", color)
            .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
            .attr("stroke", "none"),
    );
    if left.len() < 2 || left.len() != right.len() {
        return group;
    }
    for ridge in 0..4 {
        let phase = hash01(ridge, seed, "oil-ridge-phase") * std::f64::consts::TAU;
        let width = 0.025 + hash01(ridge, seed, "oil-ridge-width") * 0.025;
        for (offset, band_width, shade, class) in [
            (0.0, width, -0.23, "oil-paint-ridge-shadow-v1"),
            (width, width * 0.65, 0.20, "oil-paint-ridge-light-v1"),
        ] {
            let mut bank_a = Vec::with_capacity(left.len());
            let mut bank_b = Vec::with_capacity(left.len());
            for (index, (a, b)) in left.iter().zip(right).enumerate() {
                let t = index as f64 / (left.len() - usize::from(!closed)) as f64;
                let wave = (t * std::f64::consts::TAU * 2.0 + phase).sin() * 0.018;
                let center = 0.13 + ridge as f64 * 0.21 + wave + offset;
                let end = if closed {
                    1.0
                } else {
                    (t * 12.0).min((1.0 - t) * 12.0).min(1.0)
                };
                let at = |fraction: f64| {
                    Point::new(a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction)
                };
                bank_a.push(at(center));
                bank_b.push(at(center + band_width * end));
            }
            let d = if closed {
                format!(
                    "{} {}",
                    crate::mark_paths::polygon_path(&bank_a),
                    crate::mark_paths::polygon_path(&bank_b)
                )
            } else {
                bank_a.extend(bank_b.into_iter().rev());
                crate::mark_paths::polygon_path(&bank_a)
            };
            group.push(
                Element::new("path")
                    .attr("d", d)
                    .attr("class", class)
                    .attr("fill", oil_paint_shade(color, shade))
                    .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
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
                .attr("numOctaves", spec.octaves)
                .attr("seed", spec.noise_seed)
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

#[must_use]
pub fn performance_touch_filter(seed: Seed, canvas: CanvasSize) -> (String, Element) {
    let id = format!("performance_touch_{}", seed.rem_euclid(100_000));
    let scale = canvas.unit() / 1000.0;
    let frequency = (0.012 + hash01(0, seed, "performance-touch-frequency") * 0.008) / scale;
    let displacement = (1.6 + hash01(1, seed, "performance-touch-scale") * 1.4) * scale;
    let mut filter = Element::new("filter")
        .attr("id", &id)
        .attr("x", "-2%")
        .attr("y", "-2%")
        .attr("width", "104%")
        .attr("height", "104%")
        .attr("color-interpolation-filters", "sRGB");
    filter.push(
        Element::new("feTurbulence")
            .attr("type", "fractalNoise")
            .attr("baseFrequency", format_number(frequency))
            .attr("numOctaves", "2")
            .attr("seed", seed.rem_euclid(9973))
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
