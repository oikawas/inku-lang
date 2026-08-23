//! Display-profile material filters kept outside portable mark geometry.

use crate::determinism::hash01;
use crate::svg::{Element, format_number};
use crate::types::{CanvasSize, Seed, Weight};

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
