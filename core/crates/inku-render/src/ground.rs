//! Portable canvas-ground patterns shared by every SVG profile.

use sha2::{Digest, Sha256};

use crate::determinism::hash01;
use crate::svg::{Element, format_number};
use crate::types::{CanvasGroundSpec, CanvasSize, GroundGrain, GroundMaterial, GroundTone, Seed};

const GROUND_MM: f64 = 1000.0 / 210.0;
const GROUND_OPACITY_DEFAULT: f64 = 0.12;
const GROUND_DENSITY_DEFAULT: f64 = 0.20;
const MEZZOTINT_PLATE: &str = "#0d0d0d";

#[derive(Clone, Debug, PartialEq)]
pub struct GroundRender {
    pub group: Element,
    pub definitions: Vec<Element>,
}

#[derive(Clone)]
struct GroundLayer {
    width: f64,
    height: f64,
    rotation: f64,
    opacity: f64,
    body: Vec<Element>,
    definitions: Vec<Element>,
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

fn circle(cx: f64, cy: f64, radius: f64, fill: &str, opacity: f64) -> Element {
    Element::new("circle")
        .attr("cx", format_number(cx))
        .attr("cy", format_number(cy))
        .attr("r", format_number(radius))
        .attr("fill", fill)
        .attr("opacity", format_number(opacity))
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

fn paper_layers(ground: &CanvasGroundSpec, seed: Seed) -> Vec<GroundLayer> {
    let mut fine_random = GroundRandom::new(seed, "ground-paper");
    let radius = match ground.grain {
        GroundGrain::Fine => 0.7,
        GroundGrain::Medium => 1.1,
        GroundGrain::Coarse => 1.8,
        GroundGrain::None => 0.6,
    };
    let count = ((72.0 * ground.density.max(0.02) / GROUND_DENSITY_DEFAULT).round_ties_even()
        as usize)
        .max(8);
    let fine = (0..count)
        .map(|_| {
            let cx = fine_random.uniform(0.0, 80.0);
            let cy = fine_random.uniform(0.0, 80.0);
            let size = radius * fine_random.uniform(0.6, 1.4);
            let opacity = fine_random.uniform(0.35, 1.0);
            circle(cx, cy, size, "#777777", opacity)
        })
        .collect::<Vec<_>>();
    let mut layers = vec![GroundLayer {
        width: 80.0,
        height: 80.0,
        rotation: 23.0,
        opacity: 0.30,
        body: fine,
        definitions: Vec::new(),
    }];
    let mut coarse_random = GroundRandom::new(seed, "ground-paper-coarse");
    let tiles = [181.0, 231.0, 281.0, 341.0, 421.0, 522.0];
    let mut bands = [0_usize, 1, 2, 3, 4, 5];
    for index in (1..bands.len()).rev() {
        let other = coarse_random.range(index + 1);
        bands.swap(index, other);
    }
    let step = (6.2 - 3.0) / bands.len() as f64;
    for (tile, band) in tiles.into_iter().zip(bands) {
        let grain = 3.0 + step * (band as f64 + coarse_random.unit());
        let opacity = (0.92 * (3.0 / grain).powf(1.27)).clamp(0.30, 0.95);
        let rotation = coarse_random.uniform(0.0, 90.0);
        let cx = coarse_random.uniform(0.0, tile);
        let cy = coarse_random.uniform(0.0, tile);
        layers.push(GroundLayer {
            width: tile,
            height: tile,
            rotation,
            opacity: 0.18,
            body: vec![circle(cx, cy, grain, "#777777", opacity)],
            definitions: Vec::new(),
        });
    }
    layers
}

fn washi_layers(seed: Seed) -> Vec<GroundLayer> {
    let pitch = mm(1.05);
    let splint = mm(8.0);
    let chain_width = mm(60.0);
    let mut layers = vec![
        GroundLayer {
            width: pitch,
            height: splint,
            rotation: 0.0,
            opacity: 0.05,
            body: vec![rect(0.0, 0.0, pitch * 0.38, splint, "#8a8a8a", 0.5)],
            definitions: Vec::new(),
        },
        GroundLayer {
            width: chain_width,
            height: mm(32.0),
            rotation: 0.0,
            opacity: 0.05,
            body: vec![rect(0.0, 0.0, chain_width, mm(0.45), "#8a8a8a", 0.45)],
            definitions: Vec::new(),
        },
    ];
    let tile = mm(130.0);
    let mut random = GroundRandom::new(seed, "ground-washi");
    let mut fibres = Vec::new();
    for _ in 0..80 {
        let length = mm(random.uniform(5.0, 16.0));
        let angle = random.unit() * std::f64::consts::PI;
        let center_x = random.uniform(0.0, tile);
        let center_y = random.uniform(0.0, tile);
        let dx = angle.cos() * length / 2.0;
        let dy = angle.sin() * length / 2.0;
        let bow = random.uniform(-0.16, 0.16) * length;
        let width = random.uniform(0.35, 0.8);
        let opacity = random.uniform(0.10, 0.34);
        let middle_x = center_x - angle.sin() * bow;
        let middle_y = center_y + angle.cos() * bow;
        fibres.push(
            Element::new("path")
                .attr(
                    "d",
                    format!(
                        "M {} {} Q {} {} {} {}",
                        format_number(center_x - dx),
                        format_number(center_y - dy),
                        format_number(middle_x),
                        format_number(middle_y),
                        format_number(center_x + dx),
                        format_number(center_y + dy)
                    ),
                )
                .attr("stroke", "#8a8a8a")
                .attr("stroke-width", format_number(width))
                .attr("stroke-opacity", format_number(opacity))
                .attr("fill", "none"),
        );
    }
    layers.push(GroundLayer {
        width: tile,
        height: tile,
        rotation: 0.0,
        opacity: 0.62,
        body: fibres,
        definitions: Vec::new(),
    });
    layers
}

fn ink_wash_layers(seed: Seed) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-ink-wash");
    let band = mm(46.0);
    let tile_width = mm(210.0);
    let mut body = Vec::new();
    let mut definitions = Vec::new();
    for (index, top) in [0.0, band * 1.03].into_iter().enumerate() {
        let gradient_id = format!("ground_ink_wash_gradient_{index}");
        let head = random.uniform(0.05, 0.2);
        let tail = random.uniform(0.55, 0.8);
        let mut gradient = Element::new("linearGradient")
            .attr("id", &gradient_id)
            .attr("x1", "0")
            .attr("y1", "0")
            .attr("x2", "0")
            .attr("y2", "1");
        for (offset, opacity) in [(0.0, 0.04), (head, 0.30), (tail, 0.16), (1.0, 0.02)] {
            gradient.push(
                Element::new("stop")
                    .attr("offset", format_number(offset))
                    .attr("stop-color", "#6f6f6f")
                    .attr("stop-opacity", format_number(opacity)),
            );
        }
        definitions.push(gradient);
        let height = band * random.uniform(0.80, 0.93);
        let lower = (0..15)
            .map(|step| {
                (
                    tile_width * step as f64 / 14.0,
                    top + height + random.uniform(-mm(1.6), mm(1.6)),
                )
            })
            .collect::<Vec<_>>();
        let mut path = format!(
            "M 0 {} L {} {}",
            format_number(top),
            format_number(tile_width),
            format_number(top)
        );
        for (x, y) in lower.iter().rev() {
            path.push_str(&format!(" L {} {}", format_number(*x), format_number(*y)));
        }
        path.push_str(" Z");
        body.push(
            Element::new("path")
                .attr("d", path)
                .attr("fill", format!("url(#{gradient_id})")),
        );
        for _ in 0..40 {
            let y = top + random.uniform(0.08, 0.92) * height;
            let x = random.uniform(-tile_width * 0.1, tile_width * 0.8);
            let run = random.uniform(tile_width * 0.15, tile_width * 0.7);
            let thickness = random.uniform(0.6, 2.4);
            let opacity = random.uniform(0.08, 0.34);
            body.push(rect(x, y, run, thickness, "#6f6f6f", opacity));
        }
        let tide = lower
            .iter()
            .enumerate()
            .map(|(point_index, (x, y))| {
                format!(
                    "{} {} {}",
                    if point_index == 0 { "M" } else { "L" },
                    format_number(*x),
                    format_number(*y)
                )
            })
            .collect::<Vec<_>>()
            .join(" ");
        body.push(
            Element::new("path")
                .attr("d", tide)
                .attr("stroke", "#6f6f6f")
                .attr("stroke-width", format_number(random.uniform(0.9, 1.8)))
                .attr("stroke-opacity", "0.3")
                .attr("fill", "none"),
        );
    }
    vec![GroundLayer {
        width: tile_width,
        height: band * 2.0,
        rotation: 0.0,
        opacity: 0.34,
        body,
        definitions,
    }]
}

fn charcoal_layers(seed: Seed) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-charcoal");
    let pitch = mm(1.1);
    let mut layers = vec![GroundLayer {
        width: pitch,
        height: mm(10.0),
        rotation: 0.0,
        opacity: 0.10,
        body: vec![rect(0.0, 0.0, pitch * 0.45, mm(10.0), "#3a3a3a", 0.4)],
        definitions: Vec::new(),
    }];
    let tile = mm(17.0);
    let ridges = (tile / pitch) as usize;
    let ticks = (0..64)
        .map(|_| {
            let column = random.range(ridges);
            let y = random.uniform(0.0, tile);
            let height = mm(random.uniform(0.35, 1.6));
            let opacity = random.uniform(0.18, 0.62);
            rect(
                pitch * column as f64 + pitch * 0.1,
                y,
                pitch * 0.6,
                height,
                "#2a2a2a",
                opacity,
            )
        })
        .collect();
    layers.push(GroundLayer {
        width: tile,
        height: tile,
        rotation: 0.0,
        opacity: 0.55,
        body: ticks,
        definitions: Vec::new(),
    });
    let dust_tile = mm(53.0);
    let mut dust = (0..26)
        .map(|_| {
            let cx = random.uniform(0.0, dust_tile);
            let cy = random.uniform(0.0, dust_tile);
            let radius = random.uniform(0.4, 1.6);
            let opacity = random.uniform(0.14, 0.45);
            circle(cx, cy, radius, "#2a2a2a", opacity)
        })
        .collect::<Vec<_>>();
    for _ in 0..5 {
        dust.push(
            Element::new("ellipse")
                .attr("cx", format_number(random.uniform(0.0, dust_tile)))
                .attr("cy", format_number(random.uniform(0.0, dust_tile)))
                .attr("rx", format_number(mm(random.uniform(1.2, 3.5))))
                .attr("ry", format_number(mm(random.uniform(0.5, 1.4))))
                .attr("fill", "#2a2a2a")
                .attr("opacity", format_number(random.uniform(0.06, 0.16))),
        );
    }
    layers.push(GroundLayer {
        width: dust_tile,
        height: dust_tile,
        rotation: 0.0,
        opacity: 0.4,
        body: dust,
        definitions: Vec::new(),
    });
    layers
}

fn canvas_layers(seed: Seed) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-canvas");
    let pitch = mm(1000.0 / 14.0 / 100.0);
    let mut weave = Vec::new();
    for row in 0..2 {
        for column in 0..2 {
            let x = column as f64 * pitch;
            let y = row as f64 * pitch;
            let over = (row + column) % 2 == 0;
            let bar = pitch * 0.46;
            weave.push(rect(
                x,
                y + pitch * 0.27,
                pitch,
                bar,
                "#8f8f8f",
                if over { 0.5 } else { 0.3 },
            ));
            weave.push(rect(
                x + pitch * 0.27,
                y,
                bar,
                pitch,
                "#8f8f8f",
                if over { 0.3 } else { 0.5 },
            ));
        }
    }
    let mut layers = vec![GroundLayer {
        width: pitch * 2.0,
        height: pitch * 2.0,
        rotation: 0.0,
        opacity: 0.30,
        body: weave,
        definitions: Vec::new(),
    }];
    let slub_tile = mm(115.0);
    let mut slubs = Vec::new();
    for _ in 0..5 {
        let along = random.unit() < 0.5;
        let thickness = pitch * random.uniform(0.35, 0.75);
        let position = random.uniform(0.0, slub_tile);
        let opacity = random.uniform(0.10, 0.26);
        slubs.push(if along {
            rect(0.0, position, slub_tile, thickness, "#8f8f8f", opacity)
        } else {
            rect(position, 0.0, thickness, slub_tile, "#8f8f8f", opacity)
        });
    }
    layers.push(GroundLayer {
        width: slub_tile,
        height: slub_tile,
        rotation: 0.0,
        opacity: 0.30,
        body: slubs,
        definitions: Vec::new(),
    });
    layers.push(soft_cloud_layer(
        &mut random,
        "canvas",
        "#8f8f8f",
        5,
        160.0,
        0.5,
    ));
    layers
}

fn soft_cloud_layer(
    random: &mut GroundRandom,
    namespace: &str,
    color: &str,
    count: usize,
    tile_mm: f64,
    opacity: f64,
) -> GroundLayer {
    let tile = mm(tile_mm);
    let mut definitions = Vec::new();
    let mut clouds = Vec::new();
    for index in 0..count {
        let id = format!("ground_{namespace}_cloud_{index}");
        let mut gradient = Element::new("radialGradient").attr("id", &id);
        gradient.push(
            Element::new("stop")
                .attr("offset", "0")
                .attr("stop-color", color)
                .attr("stop-opacity", "0.14"),
        );
        gradient.push(
            Element::new("stop")
                .attr("offset", "1")
                .attr("stop-color", color)
                .attr("stop-opacity", "0"),
        );
        definitions.push(gradient);
        clouds.push(
            Element::new("ellipse")
                .attr("cx", format_number(random.uniform(0.0, tile)))
                .attr("cy", format_number(random.uniform(0.0, tile)))
                .attr("rx", format_number(mm(random.uniform(9.0, 30.0))))
                .attr("ry", format_number(mm(random.uniform(7.0, 24.0))))
                .attr("fill", format!("url(#{id})")),
        );
    }
    GroundLayer {
        width: tile,
        height: tile,
        rotation: 0.0,
        opacity,
        body: clouds,
        definitions,
    }
}

fn drawing_paper_layers(seed: Seed) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-drawing-paper");
    let mut layers = Vec::new();
    for (side, count) in [(5.0, 75), (3.7, 41)] {
        let tile = mm(side);
        let mut tooth = Vec::new();
        for _ in 0..count {
            let radius_x = random.uniform(0.30, 0.72);
            tooth.push(
                Element::new("ellipse")
                    .attr("cx", format_number(random.uniform(0.0, tile)))
                    .attr("cy", format_number(random.uniform(0.0, tile)))
                    .attr("rx", format_number(radius_x))
                    .attr("ry", format_number(radius_x * random.uniform(0.55, 0.8)))
                    .attr("fill", "#8a8a8a")
                    .attr("opacity", format_number(random.uniform(0.18, 0.62))),
            );
        }
        layers.push(GroundLayer {
            width: tile,
            height: tile,
            rotation: 0.0,
            opacity: 0.42,
            body: tooth,
            definitions: Vec::new(),
        });
    }
    layers.push(soft_cloud_layer(
        &mut random,
        "drawing_paper",
        "#8a8a8a",
        6,
        155.0,
        0.55,
    ));
    layers
}

fn mezzotint_layers(seed: Seed) -> Vec<GroundLayer> {
    let mut random = GroundRandom::new(seed, "ground-mezzotint");
    let mut layers = Vec::new();
    for (across, rotation, opacity) in [(12_usize, 0.0, 0.16), (9, 58.0, 0.13)] {
        let pitch = mm(25.4 / 65.0);
        let mut pits = Vec::new();
        for row in 0..across {
            for column in 0..across {
                let cx = (column as f64 + 0.5) * pitch + random.uniform(-0.22, 0.22) * pitch;
                let cy = (row as f64 + 0.5) * pitch + random.uniform(-0.22, 0.22) * pitch;
                let radius = pitch * random.uniform(0.17, 0.31);
                let pit_opacity = random.uniform(0.30, 0.95);
                pits.push(circle(cx, cy, radius, "#ffffff", pit_opacity));
            }
        }
        layers.push(GroundLayer {
            width: pitch * across as f64,
            height: pitch * across as f64,
            rotation,
            opacity,
            body: pits,
            definitions: Vec::new(),
        });
    }
    let tile = mm(46.0);
    let flecks = (0..18)
        .map(|_| {
            let cx = random.uniform(0.0, tile);
            let cy = random.uniform(0.0, tile);
            let radius = random.uniform(0.5, 2.1);
            let opacity = random.uniform(0.06, 0.22);
            circle(cx, cy, radius, "#ffffff", opacity)
        })
        .collect();
    layers.push(GroundLayer {
        width: tile,
        height: tile,
        rotation: 0.0,
        opacity: 0.5,
        body: flecks,
        definitions: Vec::new(),
    });
    layers
}

fn layers(ground: &CanvasGroundSpec, seed: Seed) -> Vec<GroundLayer> {
    match ground.material {
        GroundMaterial::Plain => Vec::new(),
        GroundMaterial::Paper => paper_layers(ground, seed),
        GroundMaterial::Washi => washi_layers(seed),
        GroundMaterial::InkWash => ink_wash_layers(seed),
        GroundMaterial::CharcoalGround => charcoal_layers(seed),
        GroundMaterial::Canvas => canvas_layers(seed),
        GroundMaterial::DrawingPaper => drawing_paper_layers(seed),
        GroundMaterial::Mezzotint => mezzotint_layers(seed),
    }
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
    for (index, layer) in layers(ground, seed).into_iter().enumerate() {
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
