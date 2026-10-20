//! The color stage's drawn-appearance estimate on pictures outside the
//! repository: each line of the JSON Lines file `INKU_COLOR_APPEARANCE_INPUT`
//! names a Score, its nine paints, its canvas and its render seed, and the
//! estimate of each layer is written, one line per Score, to
//! `INKU_COLOR_APPEARANCE_OUTPUT`. With `INKU_COLOR_APPEARANCE_SVG` (a
//! directory), each Score's editable SVG is written there too. The color
//! stage was calibrated this way on its prototype's pictures, which stay out
//! of the repository.

use std::fmt::Write as _;

use inku_pipeline::appearance::{Painter, Seeds, Shares};
use inku_score::{Color, Score, ScoreErrorPolicy};
use serde_json::{Map, Value, json};

#[test]
#[ignore = "reads pictures from outside the repository"]
fn estimates_the_drawn_appearance_of_the_given_pictures() {
    let input = std::env::var("INKU_COLOR_APPEARANCE_INPUT").expect("an input file");
    let output = std::env::var("INKU_COLOR_APPEARANCE_OUTPUT").expect("an output file");
    let svgs = std::env::var("INKU_COLOR_APPEARANCE_SVG").ok();
    let mut shares = Shares::default();
    let mut lines = String::new();
    for line in std::fs::read_to_string(input)
        .expect("readable input")
        .lines()
    {
        if line.trim().is_empty() {
            continue;
        }
        let item: Value = serde_json::from_str(line).expect("a JSON line");
        let score: Score = serde_json::from_value(item["score"].clone()).expect("a Score");
        let paints: Vec<(Color, [u8; 3])> = Color::ALL
            .iter()
            .map(|color| {
                let code = item["colors"][color.as_str()].as_str().expect("a paint");
                let channel = |k: usize| u8::from_str_radix(&code[k..k + 2], 16).expect("hex");
                (*color, [channel(1), channel(3), channel(5)])
            })
            .collect();
        let seeds = Seeds {
            render: item["render_seed"]
                .as_str()
                .map(|seed| seed.parse().expect("a seed")),
            composition: None,
        };
        let painter = Painter::new(
            &paints,
            item["canvas_format_id"].as_str().expect("a canvas"),
            seeds,
            ScoreErrorPolicy::OmitAndContinue,
        )
        .expect("a painter");
        if let Some(directory) = &svgs
            && let Ok((svg, layers)) = painter.editable(&score)
        {
            let name = item["id"].as_str().expect("an id");
            std::fs::write(format!("{directory}/{name}.svg"), svg).expect("writable SVG");
            let layers: Map<String, Value> = layers
                .iter()
                .map(|(group, layer)| (group.to_string(), json!(layer)))
                .collect();
            std::fs::write(
                format!("{directory}/{name}.layers.json"),
                Value::Object(layers).to_string(),
            )
            .expect("writable layers");
        }
        let row = match painter.try_drawing(&score, &mut shares) {
            Ok(drawing) => {
                let mut layers = Map::new();
                for (layer, look) in &drawing.looks {
                    layers.insert(
                        layer.to_string(),
                        json!({
                            "lab": look.lab,
                            "contrast": look.contrast,
                            "chroma": look.chroma,
                            "ink": look.ink,
                            "read": look.read,
                            "opacity": look.opacity,
                            "width": look.width,
                            "cover": look.cover,
                        }),
                    );
                }
                let neighbors: Map<String, Value> = drawing
                    .neighbors
                    .iter()
                    .map(|(layer, near)| (layer.to_string(), json!(near)))
                    .collect();
                json!({"id": item["id"], "layers": layers, "neighbors": neighbors})
            }
            Err(error) => json!({"id": item["id"], "error": error}),
        };
        writeln!(lines, "{row}").expect("a line");
    }
    std::fs::write(output, lines).expect("writable output");
}
