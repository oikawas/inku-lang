//! Portable canvas-ground patterns shared by every SVG profile.

use sha2::{Digest, Sha256};

use crate::determinism::hash01;
use crate::ground_patterns::build_ground_layers;
use crate::svg::{Element, format_number};
use crate::types::{CanvasGroundSpec, CanvasSize, GroundGrain, GroundMaterial, GroundTone, Seed};

const GROUND_OPACITY_DEFAULT: f64 = 0.12;
const MEZZOTINT_PLATE: &str = "#0d0d0d";

#[derive(Clone, Debug, PartialEq)]
pub struct GroundRender {
    pub group: Element,
    pub definitions: Vec<Element>,
}

fn material_name(material: GroundMaterial) -> &'static str {
    match material {
        GroundMaterial::Plain => "plain",
        GroundMaterial::Paper => "paper",
        GroundMaterial::Washi => "washi",
        GroundMaterial::InkWash => "ink_wash",
        GroundMaterial::CharcoalGround => "charcoal_ground",
        GroundMaterial::Canvas => "canvas",
        GroundMaterial::DrawingPaper => "drawing_paper",
        GroundMaterial::Mezzotint => "mezzotint",
    }
}

fn grain_name(grain: GroundGrain) -> &'static str {
    match grain {
        GroundGrain::None => "none",
        GroundGrain::Fine => "fine",
        GroundGrain::Medium => "medium",
        GroundGrain::Coarse => "coarse",
    }
}

fn ground_seed(ground: &CanvasGroundSpec, render_seed: Option<Seed>) -> Seed {
    if let Some(seed) = ground.seed {
        return seed;
    }
    let mut key = format!(
        "{{\"grain\":\"{}\",\"material\":\"{}\"}}",
        grain_name(ground.grain),
        material_name(ground.material)
    );
    if let Some(seed) = render_seed {
        key.push_str(&format!(":render:{seed}"));
    }
    key.push_str(":texture:canvas-ground:0");
    let digest = Sha256::digest(key.as_bytes());
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn tone_color(ground: &CanvasGroundSpec, background: &str) -> String {
    match ground.tone {
        GroundTone::White => background.to_owned(),
        GroundTone::OffWhite => "#f7f3e8".to_owned(),
        GroundTone::Warm => "#f3ead8".to_owned(),
        GroundTone::Cool => "#eef3f4".to_owned(),
        GroundTone::Gray => "#e4e2dc".to_owned(),
        GroundTone::Black => "#151515".to_owned(),
    }
}

fn rect(x: f64, y: f64, width: f64, height: f64, fill: &str, opacity: f64) -> Element {
    Element::new("rect")
        .attr("x", format_number(x))
        .attr("y", format_number(y))
        .attr("width", format_number(width))
        .attr("height", format_number(height))
        .attr("fill", fill)
        .attr("opacity", format_number(opacity))
}

/// Render the named physical support as reusable patterns and one ground layer.
#[must_use]
pub fn render_ground(
    ground: &CanvasGroundSpec,
    canvas: CanvasSize,
    background: &str,
    render_seed: Option<Seed>,
) -> Option<GroundRender> {
    if ground.material == GroundMaterial::Plain {
        return None;
    }
    let seed = ground_seed(ground, render_seed);
    let mut group = Element::new("g").attr("id", "layer_01_canvas_ground");
    if ground.material == GroundMaterial::Mezzotint {
        let shift = canvas.unit() * (0.001 + hash01(0, seed, "register-shift") * 0.003);
        let angle = hash01(1, seed, "register-angle") * std::f64::consts::TAU;
        group.set_attr(
            "transform",
            format!(
                "translate({} {})",
                format_number(angle.cos() * shift),
                format_number(angle.sin() * shift)
            ),
        );
    }
    group.push(rect(
        0.0,
        0.0,
        canvas.width,
        canvas.height,
        &tone_color(ground, background),
        0.98,
    ));
    if ground.material == GroundMaterial::Mezzotint {
        group.push(rect(
            0.0,
            0.0,
            canvas.width,
            canvas.height,
            MEZZOTINT_PLATE,
            1.0,
        ));
    }
    let opacity_scale = ground.opacity.max(0.0) / GROUND_OPACITY_DEFAULT;
    let mut definitions = Vec::new();
    for (index, layer) in build_ground_layers(ground, seed).into_iter().enumerate() {
        definitions.extend(layer.definitions);
        let pattern_id = format!("ground_pattern_{index}");
        let mut pattern = Element::new("pattern")
            .attr("id", &pattern_id)
            .attr("patternUnits", "userSpaceOnUse")
            .attr("width", format_number(layer.width))
            .attr("height", format_number(layer.height));
        if layer.rotation != 0.0 {
            pattern.set_attr(
                "patternTransform",
                format!("rotate({})", format_number(layer.rotation)),
            );
        }
        for element in layer.body {
            pattern.push(element);
        }
        definitions.push(pattern);
        group.push(
            rect(
                0.0,
                0.0,
                canvas.width,
                canvas.height,
                &format!("url(#{pattern_id})"),
                (layer.opacity * opacity_scale).min(1.0),
            )
            .attr(
                "class",
                format!("canvas-ground-{}", material_name(ground.material)),
            ),
        );
    }
    Some(GroundRender { group, definitions })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ground(material: GroundMaterial) -> CanvasGroundSpec {
        CanvasGroundSpec {
            material,
            tone: GroundTone::Warm,
            grain: GroundGrain::Medium,
            density: 0.20,
            opacity: 0.12,
            seed: None,
        }
    }

    #[test]
    fn every_named_support_has_finite_pattern_definitions() {
        for material in [
            GroundMaterial::Paper,
            GroundMaterial::Washi,
            GroundMaterial::InkWash,
            GroundMaterial::CharcoalGround,
            GroundMaterial::Canvas,
            GroundMaterial::DrawingPaper,
            GroundMaterial::Mezzotint,
        ] {
            let rendered = render_ground(
                &ground(material),
                CanvasSize::new(1000.0, 1000.0),
                "#ffffff",
                Some(431),
            )
            .unwrap();
            assert!(!rendered.definitions.is_empty());
            let debug = format!("{:?}", rendered);
            assert!(!debug.contains("NaN"));
            assert!(!debug.contains("inf"));
            assert!(!debug.contains("filter"));
            assert!(!debug.contains("clipPath"));
        }
    }

    #[test]
    fn tone_and_opacity_do_not_change_ground_identity() {
        let base = ground(GroundMaterial::Paper);
        let mut changed = base.clone();
        changed.tone = GroundTone::Cool;
        changed.opacity = 0.8;
        assert_eq!(ground_seed(&base, Some(9)), ground_seed(&changed, Some(9)));
    }
}
