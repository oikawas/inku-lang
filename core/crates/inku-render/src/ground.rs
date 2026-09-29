//! Portable canvas-ground patterns shared by every SVG profile.

use sha2::{Digest, Sha256};

use crate::determinism::hash01;
use crate::ground_patterns::build_ground_layers;
use crate::svg::{Element, format_number};
use crate::types::{
    Canvas, CanvasGroundSpec, CanvasSize, Color, GroundMaterial, GroundTone, Score, Seed,
};

const GROUND_OPACITY_DEFAULT: f64 = 0.12;
const MEZZOTINT_PLATE: &str = "#0d0d0d";

#[derive(Clone, Debug, PartialEq)]
pub struct GroundRender {
    pub group: Element,
    pub definitions: Vec<Element>,
}

fn ground_seed(ground: &CanvasGroundSpec, render_seed: Option<Seed>) -> Seed {
    if let Some(seed) = ground.seed {
        return seed;
    }
    let mut key = format!(
        "{{\"grain\":\"{}\",\"material\":\"{}\"}}",
        ground.grain.as_str(),
        ground.material.as_str()
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

/// The Score colour the canvas shows under the marks. The ground paints its
/// tone over the whole background, and the mezzotint plate over that, so the
/// background shows only without a ground, on the plain material, or under a
/// white tone of any other material but mezzotint. Other tones paint colours
/// no Score colour names, so they give `None`.
#[must_use]
pub fn shown_background(score: &Score) -> Option<Color> {
    let ground = match &score.canvas {
        Canvas::Spec(canvas) => canvas.ground.as_ref(),
        Canvas::Id(_) => None,
    };
    let covered = ground.is_some_and(|ground| {
        ground.material != GroundMaterial::Plain
            && (ground.material == GroundMaterial::Mezzotint || ground.tone != GroundTone::White)
    });
    (!covered).then_some(score.background)
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
                format!("canvas-ground-{}", ground.material.as_str()),
            ),
        );
    }
    Some(GroundRender { group, definitions })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::svg::Node;
    use crate::types::GroundGrain;

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

    #[test]
    fn the_shown_background_is_what_the_ground_rects_leave_showing() {
        // The pipeline returns marks in this colour to the reader, so it must
        // follow the whole-canvas rects the ground paints under the marks.
        for material in [
            GroundMaterial::Plain,
            GroundMaterial::Paper,
            GroundMaterial::Washi,
            GroundMaterial::InkWash,
            GroundMaterial::CharcoalGround,
            GroundMaterial::Canvas,
            GroundMaterial::DrawingPaper,
            GroundMaterial::Mezzotint,
        ] {
            for tone in [
                GroundTone::White,
                GroundTone::OffWhite,
                GroundTone::Warm,
                GroundTone::Cool,
                GroundTone::Gray,
                GroundTone::Black,
            ] {
                let spec = CanvasGroundSpec {
                    tone,
                    ..ground(material)
                };
                let score: Score = serde_json::from_value(serde_json::json!({
                    "background": "gray",
                    "canvas": {"aspect": "square", "ground": spec},
                    "instructions": [],
                }))
                .unwrap();
                // The renderer draws no ground for the plain material.
                let fills = render_ground(&spec, CanvasSize::new(100.0, 100.0), "#abcdef", Some(1))
                    .map(|rendered| {
                        rendered
                            .group
                            .children()
                            .iter()
                            .filter_map(|node| match node {
                                Node::Element(element) => element.attribute("fill"),
                                Node::Text(_) => None,
                            })
                            .filter(|fill| !fill.starts_with("url("))
                            .map(str::to_owned)
                            .collect::<Vec<_>>()
                    })
                    .unwrap_or_default();
                let shows = fills.iter().all(|fill| fill == "#abcdef");
                assert_eq!(
                    shown_background(&score),
                    shows.then_some(Color::Gray),
                    "{material:?} {tone:?} {fills:?}"
                );
            }
        }
        let without_ground: Score = serde_json::from_value(serde_json::json!({
            "background": "yellow", "canvas": "square", "instructions": [],
        }))
        .unwrap();
        assert_eq!(shown_background(&without_ground), Some(Color::Yellow));
    }
}
