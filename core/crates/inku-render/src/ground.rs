//! Portable canvas-ground patterns shared by every SVG profile.

use sha2::{Digest, Sha256};

use crate::ground_patterns::build_ground_plan;
use crate::svg::{Element, format_number};
use crate::types::{
    Canvas, CanvasGroundSpec, CanvasSize, Color, GroundMaterial, GroundTone, Score, Seed,
};

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
/// tone over the whole background, and the mezzotint plate or the charcoal
/// over that, so the background shows only without a ground, on the plain
/// material, or under a white tone of any other material but those two. The
/// ink wash's thin wash tints the background without hiding it. Other tones
/// paint colours no Score colour names, so they give `None`.
#[must_use]
pub fn shown_background(score: &Score) -> Option<Color> {
    let ground = match &score.canvas {
        Canvas::Spec(canvas) => canvas.ground.as_ref(),
        Canvas::Id(_) => None,
    };
    let covered = ground.is_some_and(|ground| {
        ground.material != GroundMaterial::Plain
            && (ground.material.covers_the_background() || ground.tone != GroundTone::White)
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
    let tone = tone_color(ground, background);
    group.push(rect(0.0, 0.0, canvas.width, canvas.height, &tone, 0.98));
    let plan = build_ground_plan(ground, seed, canvas, &tone);
    if let Some((colour, opacity)) = plan.body {
        group.push(rect(0.0, 0.0, canvas.width, canvas.height, colour, opacity));
    }
    for element in plan.broad {
        group.push(element);
    }
    let mut definitions = plan.definitions;
    for (index, layer) in plan.layers.into_iter().enumerate() {
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
            Element::new("rect")
                .attr("width", format_number(canvas.width))
                .attr("height", format_number(canvas.height))
                .attr("fill", format!("url(#{pattern_id})"))
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
    use crate::svg::{Document, Node};
    use crate::types::GroundGrain;

    const MATERIALS: [GroundMaterial; 7] = [
        GroundMaterial::Paper,
        GroundMaterial::Washi,
        GroundMaterial::InkWash,
        GroundMaterial::CharcoalGround,
        GroundMaterial::Canvas,
        GroundMaterial::DrawingPaper,
        GroundMaterial::Mezzotint,
    ];
    const TONES: [GroundTone; 6] = [
        GroundTone::White,
        GroundTone::OffWhite,
        GroundTone::Warm,
        GroundTone::Cool,
        GroundTone::Gray,
        GroundTone::Black,
    ];
    /// Square, the widest and the narrowest registered canvas, 1000 px high.
    const CANVASES: [(f64, f64); 3] = [(1000.0, 1000.0), (2350.0, 1000.0), (562.0, 1000.0)];

    fn rects(group: &Element) -> Vec<&Element> {
        group
            .children()
            .iter()
            .filter_map(|node| match node {
                Node::Element(element) if element.name() == "rect" => Some(element),
                _ => None,
            })
            .collect()
    }

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
                // The renderer draws no ground for the plain material. A rect
                // painting at half opacity or more hides the background; the
                // ink wash's thin wash and the patterns' rects do not.
                let fills = render_ground(&spec, CanvasSize::new(100.0, 100.0), "#abcdef", Some(1))
                    .map(|rendered| {
                        rects(&rendered.group)
                            .into_iter()
                            .filter(|rect| {
                                rect.attribute("opacity")
                                    .is_none_or(|opacity| opacity.parse::<f64>().unwrap() >= 0.5)
                            })
                            .filter_map(|rect| rect.attribute("fill"))
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

    #[test]
    fn every_ground_covers_the_canvas_without_a_transform() {
        // Engine 79 moved the whole mezzotint layer to set its plate off by a
        // few pixels, and the background showed along two edges.
        for material in MATERIALS {
            for tone in TONES {
                for (width, height) in CANVASES {
                    let canvas = CanvasSize::new(width, height);
                    let spec = CanvasGroundSpec {
                        tone,
                        ..ground(material)
                    };
                    let rendered = render_ground(&spec, canvas, "#abcdef", Some(431)).unwrap();
                    assert_eq!(rendered.group.attribute("transform"), None, "{material:?}");
                    let rects = rects(&rendered.group);
                    assert!(!rects.is_empty(), "{material:?}");
                    for rect in rects {
                        assert!(matches!(rect.attribute("x"), None | Some("0")), "{rect:?}");
                        assert!(matches!(rect.attribute("y"), None | Some("0")), "{rect:?}");
                        assert_eq!(rect.attribute("width"), Some(format_number(width).as_str()));
                        assert_eq!(
                            rect.attribute("height"),
                            Some(format_number(height).as_str())
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn every_ground_stays_within_its_byte_budget() {
        // The ground's cost is held by its bytes, not by its element count
        // (24 KB, the author's ruling of 2026-08-14). A light, a middle and a
        // dark background draw different marks, so all three are measured.
        for material in MATERIALS {
            for background in ["#f2f7f7", "#b2beb5", "#10141a"] {
                for (width, height) in CANVASES {
                    let canvas = CanvasSize::new(width, height);
                    let rendered =
                        render_ground(&ground(material), canvas, background, Some(431)).unwrap();
                    let empty = Document::new(canvas).serialize().len();
                    let mut document = Document::new(canvas);
                    for definition in rendered.definitions {
                        document.push_definition(definition);
                    }
                    document.push(rendered.group);
                    let bytes = document.serialize().len() - empty;
                    assert!(
                        bytes <= 24 * 1024,
                        "{material:?} {background} {width}x{height}: {bytes} bytes"
                    );
                }
            }
        }
    }
}
