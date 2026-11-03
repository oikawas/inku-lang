//! Thin byte facades for the existing checked compile-once/render boundary.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_pipeline::core_boundary::{ClipPolicy, CompiledDelivery, CompilerOptions};
use inku_pipeline::machine::{PipelineRenderOptions, VisibleDocument};
use serde::Deserialize;

const MAX_INPUT_BYTES: usize = 16 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CompileInput {
    document: VisibleDocument,
    definitions: Vec<inku_ddl::MacroDefinition>,
    compiler: CompilerOptions,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RenderInput {
    delivery: CompiledDelivery,
    options: PipelineRenderOptions,
    compiler: CompilerOptions,
    clip: ClipPolicy,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AnimationInput {
    document: VisibleDocument,
    definitions: Vec<inku_ddl::MacroDefinition>,
    compiler: CompilerOptions,
    options: PipelineRenderOptions,
    clip: ClipPolicy,
    saved_svg: String,
    show_ddl: bool,
    font_family: String,
    #[serde(default)]
    font_files: Vec<String>,
}

fn xml_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn composed_frame(
    source: &str,
    svg: &str,
    family: &str,
    ranges: &[Vec<(usize, usize)>],
    frame: usize,
    width: f64,
    height: f64,
) -> Result<String, Vec<u8>> {
    let start = svg
        .find('>')
        .ok_or_else(|| refusal("invalid_svg", "missing SVG root"))?;
    let end = svg
        .rfind("</svg>")
        .ok_or_else(|| refusal("invalid_svg", "missing SVG end"))?;
    let mut rows = Vec::new();
    for (index, line) in source.split('\n').enumerate() {
        let mut part = String::new();
        for ch in line.chars() {
            part.push(ch);
            if part.chars().count() >= 28 {
                rows.push((index + 1, std::mem::take(&mut part)));
            }
        }
        if !part.is_empty() || line.is_empty() {
            rows.push((index + 1, part));
        }
    }
    let font_size = (960.0 / rows.len().max(1) as f64).min(17.0);
    let mut text = String::new();
    for (row, (line, value)) in rows.iter().enumerate() {
        let last = ranges
            .iter()
            .enumerate()
            .filter(|(_, spans)| spans.iter().any(|&(a, b)| a <= *line && *line <= b))
            .map(|(i, _)| i + 1)
            .max()
            .unwrap_or(0);
        let color = if last == frame {
            "#1c1c1c"
        } else if last < frame {
            "#444444"
        } else {
            "#aaaaaa"
        };
        let weight = if last == frame { "bold" } else { "normal" };
        text.push_str(&format!(
            "<text x=\"20\" y=\"{}\" font-size=\"{}\" fill=\"{}\" font-weight=\"{}\">{}</text>",
            20.0 + (row + 1) as f64 * font_size,
            font_size * 0.85,
            color,
            weight,
            xml_escape(value)
        ));
    }
    let scale = (490.0 / width).min(960.0 / height);
    Ok(format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1000\" height=\"1000\" viewBox=\"0 0 1000 1000\"><rect width=\"1000\" height=\"1000\" fill=\"#ffffff\"/><g font-family=\"{}\">{}</g><g transform=\"translate(500 20) scale({})\">{}</g></svg>",
        xml_escape(family),
        text,
        scale,
        &svg[start + 1..end]
    ))
}

/// Compile a saved visible document and return a frame for each Score instruction.
#[uniffi::export]
pub fn line_animation(input_bytes: Vec<u8>) -> Vec<u8> {
    owned_call(|| {
        let input: AnimationInput = parse(&input_bytes, "invalid_animation_input")?;
        let document = input
            .document
            .document()
            .map_err(|error| refusal("invalid_document", &format!("{error:?}")))?;
        let (delivery, ranges) = inku_pipeline::core_boundary::compile_committed_with_line_ranges(
            document,
            &input.definitions,
            &input.compiler,
        )
        .map_err(|error| refusal("compile_refused", &error.to_string()))?;
        let mut frames = Vec::with_capacity(ranges.len() + 1);
        for index in 0..=ranges.len() {
            let output = inku_pipeline::core_boundary::render_delivery_instruction_prefix(
                &delivery,
                input.options.clone().into(),
                &input.compiler,
                input.clip,
                index,
            )
            .map_err(|error| refusal("render_refused", &error.to_string()))?;
            let selected = if index == 0 {
                (1..=input.document.source.split('\n').count())
                    .filter(|line| {
                        !ranges
                            .iter()
                            .flatten()
                            .any(|&(first, last)| first <= *line && *line <= last)
                    })
                    .map(|line| (line, line))
                    .collect()
            } else {
                ranges[index - 1]
                    .iter()
                    .copied()
                    .filter(|range| !ranges[index..].iter().any(|later| later.contains(range)))
                    .collect::<Vec<_>>()
            };
            let svg = if input.show_ddl {
                composed_frame(
                    &input.document.source,
                    &output.svg,
                    &input.font_family,
                    &ranges,
                    index,
                    input.options.canvas.width,
                    input.options.canvas.height,
                )?
            } else {
                output.svg.clone()
            };
            frames.push(serde_json::json!({"instruction_count": index, "lines": selected, "svg": svg, "art_svg": output.svg}));
        }
        let matches_saved = frames.last().and_then(|frame| frame["art_svg"].as_str())
            == Some(input.saved_svg.as_str());
        serde_json::to_vec(&serde_json::json!({"frames": frames, "matches_saved_svg": matches_saved, "font_files": input.font_files, "outcome": delivery.outcome, "upstream_diagnostics": delivery.upstream_diagnostics, "downstream_diagnostics": delivery.downstream_diagnostics, "resource_omissions": delivery.resource_omissions, "relation_omissions": delivery.relation_omissions})).map_err(|error| refusal("invalid_output", &error.to_string()))
    })
}

#[cfg(test)]
mod line_animation_tests {
    use super::*;

    #[test]
    fn animation_compiles_the_source_and_reports_each_frame() {
        use inku_score::{CANVAS_FORMAT_REGISTRY_ID, Color, canvas_format_registry_digest};
        let map = std::collections::BTreeMap::new();
        let palette = inku_render::palette::work_palette_context(
            &map,
            Some(5),
            Some("default"),
            Color::White,
        )
        .unwrap();
        let dto = |p: inku_score::ResolvedPaletteColor| serde_json::json!({"abstract_color":p.abstract_color(),"concrete_rgb":p.concrete_rgb(),"oklch_lightness":p.oklch_lightness()});
        let maximum = serde_json::json!({"logical_objects":400,"primitive_marks":400,"object_templates":64,"maximum_per_template_primitive_marks":240,"maximum_resolved_count":2000,"template_nodes":512,"anchor_instances":400,"transform_instances":400,"placement_instances":400,"fill_instances":400});
        let mut input = serde_json::json!({
            "document":{"source":"Place one thin pencil line at the center.\nThe line sways narrowly.\nPlace a circle.","language":"en","macro_locks":[],"saijiki":inku_ddl::SAIJIKI_ASSET_ID},"definitions":[],
            "compiler":{"host":{"canvas_format_id":"square","canvas_format_registry_id":CANVAS_FORMAT_REGISTRY_ID,"canvas_format_registry_digest":canvas_format_registry_digest().unwrap(),"resolved_catalog_id":"default","catalog_mode":"default","background":"white","palette":{"background":dto(palette.background()),"black":dto(palette.black()),"white":dto(palette.white()),"observations":palette.observations().unwrap().iter().copied().map(dto).collect::<Vec<_>>() }},"composition_seed":"17","macro_expansion_limits":{"max_invocations":"16","max_depth":"16","max_evaluation_steps":"1000","max_nodes_per_invocation":"100","max_total_nodes":"500"},"error_policy":"omit_and_continue","hard_resource_policy":{"identity":"animation-test.v1","budget":{"maximum":maximum}},"operational_resource_budget":{"maximum":maximum}},
            "options":{"resolved_color_map":map,"catalog_id":"default","canvas":{"width":1000.0,"height":1000.0},"canvas_aspect_id":"square","svg_profile":"display","render_seed":"5","composition_seed":"17","wild":false,"error_policy":"omit_and_continue"},
            "clip":{"tolerance_pixels":0.25,"max_nodes":"50000","max_path_elements":"200000","max_flattened_points":"200000","max_work":"10000000","max_output_vertices":"200000"},"saved_svg":"older","show_ddl":false,"font_family":"Noto Serif JP","font_files":[]
        });
        let result: serde_json::Value =
            serde_json::from_slice(&line_animation(serde_json::to_vec(&input).unwrap())).unwrap();
        assert!(result.get("error").is_none(), "{result}");
        let frames = result["frames"].as_array().unwrap();
        assert_eq!(frames.len(), 3);
        assert!(
            frames[1]["lines"]
                .as_array()
                .unwrap()
                .contains(&serde_json::json!([1, 1]))
        );
        assert!(
            frames[1]["lines"]
                .as_array()
                .unwrap()
                .contains(&serde_json::json!([2, 2]))
        );
        assert_eq!(result["matches_saved_svg"], false);
        input["saved_svg"] = frames[2]["art_svg"].clone();
        let same: serde_json::Value =
            serde_json::from_slice(&line_animation(serde_json::to_vec(&input).unwrap())).unwrap();
        assert_eq!(same["matches_saved_svg"], true);
        assert_eq!(same["frames"][2]["svg"], same["frames"][2]["art_svg"]);
    }

    #[test]
    fn composed_frame_keeps_all_long_lines_and_escapes_text() {
        let source = std::iter::repeat_n("長い文章と<記号>", 45)
            .collect::<Vec<_>>()
            .join("\n");
        let svg =
            "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"10\" height=\"20\"/></svg>";
        let output = composed_frame(
            &source,
            svg,
            "Font & Family",
            &[vec![(1, 1)]],
            1,
            10.0,
            20.0,
        )
        .unwrap();
        assert_eq!(output.matches("長い文章と&lt;記号&gt;").count(), 45);
        assert!(output.contains("Font &amp; Family"));
        assert!(output.contains("<rect width=\"10\" height=\"20\"/>"));
    }
}

fn refusal(code: &str, message: &str) -> Vec<u8> {
    serde_json::to_vec(&serde_json::json!({ "error": code, "message": message }))
        .expect("two strings serialize")
}

fn owned_call(operation: impl FnOnce() -> Result<Vec<u8>, Vec<u8>>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(operation))
        .unwrap_or_else(|_| Err(refusal("internal_invariant", "the core panicked")))
        .unwrap_or_else(|error| error)
}

fn parse<T: serde::de::DeserializeOwned>(bytes: &[u8], code: &str) -> Result<T, Vec<u8>> {
    if bytes.len() > MAX_INPUT_BYTES {
        return Err(refusal(code, "input is larger than 16 MiB"));
    }
    serde_json::from_slice(bytes).map_err(|error| refusal(code, &error.to_string()))
}

/// Compile a current VisibleDocument without changing source or choosing authority.
#[uniffi::export]
pub fn compile_document(input_bytes: Vec<u8>) -> Vec<u8> {
    owned_call(|| {
        let input: CompileInput = parse(&input_bytes, "invalid_compile_input")?;
        let document = input.document.document().map_err(|error| {
            let code = serde_json::to_value(error).expect("protocol error serializes");
            refusal(
                code.as_str().expect("protocol error is a string"),
                &format!("{error:?}"),
            )
        })?;
        let delivery = inku_pipeline::core_boundary::compile_committed(
            document,
            &input.definitions,
            &input.compiler,
        )
        .map_err(|error| refusal("compile_refused", &error.to_string()))?;
        serde_json::to_vec(&delivery)
            .map_err(|error| refusal("invalid_compiled_delivery", &error.to_string()))
    })
}

/// Draw only a validated delivery with its independently supplied matching options.
#[uniffi::export]
pub fn render_compiled(input_bytes: Vec<u8>) -> Vec<u8> {
    owned_call(|| {
        let input: RenderInput = parse(&input_bytes, "invalid_render_input")?;
        let output = inku_pipeline::core_boundary::render_delivery(
            &input.delivery,
            input.options.into(),
            &input.compiler,
            input.clip,
        )
        .map_err(|error| refusal(super::saved_render_error_code(&error), &error.to_string()))?;
        serde_json::to_vec(&output)
            .map_err(|error| refusal("invalid_render_output", &error.to_string()))
    })
}

/// Native replay keeps raw SVG outside the bounded metadata envelope.
#[uniffi::export]
pub fn render_compiled_svg_limited(
    input_bytes: Vec<u8>,
    max_svg_bytes: u64,
) -> super::NativeSvgOutput {
    let limit = match super::native_svg_limit(max_svg_bytes) {
        Ok(limit) => limit,
        Err(refusal) => return refusal,
    };
    catch_unwind(AssertUnwindSafe(|| {
        let input: RenderInput = match parse(&input_bytes, "invalid_render_input") {
            Ok(input) => input,
            Err(bytes) => return (bytes, None).into(),
        };
        match inku_pipeline::core_boundary::render_delivery_with_svg_limit(
            &input.delivery,
            input.options.into(),
            &input.compiler,
            input.clip,
            limit,
        ) {
            Ok(output) => {
                super::separated_saved_output(output, super::MAX_SAVED_RENDER_METADATA_BYTES).into()
            }
            Err(error) => (
                refusal(super::saved_render_error_code(&error), &error.to_string()),
                None,
            )
                .into(),
        }
    }))
    .unwrap_or_else(|_| (refusal("internal_invariant", "the core panicked"), None).into())
}
