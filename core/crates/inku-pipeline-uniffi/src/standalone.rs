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

// Keep Latin words and numeric expressions intact, and keep contiguous
// Japanese text together. Punctuation stays with what precedes it.
fn ddl_tokens(line: &str) -> Vec<String> {
    fn class(ch: char) -> u8 {
        if ch.is_whitespace() {
            0
        } else if ch.is_ascii_alphanumeric()
            || matches!(
                ch,
                '.' | '-' | '+' | '~' | '〜' | '～' | '−' | '/' | '_' | '\''
            )
            || ('０'..='９').contains(&ch)
        {
            1
        } else if ('\u{3040}'..='\u{30ff}').contains(&ch)
            || ('\u{3400}'..='\u{9fff}').contains(&ch)
            || matches!(ch, '々' | 'ー')
        {
            2
        } else {
            3
        }
    }
    let mut tokens: Vec<String> = Vec::new();
    let mut previous = None;
    for ch in line.chars() {
        let kind = class(ch);
        let count_unit = kind == 2
            && previous == Some(1)
            && matches!(ch, '本' | '個' | '枚' | 'つ' | '度' | '倍' | '段')
            && tokens
                .last()
                .and_then(|token| token.chars().last())
                .is_some_and(|last| last.is_ascii_digit() || ('０'..='９').contains(&last));
        if count_unit {
            tokens.last_mut().expect("numeric token").push(ch);
            previous = Some(kind);
        } else if kind == 3 && !tokens.is_empty() {
            tokens.last_mut().expect("nonempty tokens").push(ch);
            previous = None;
        } else if previous == Some(kind) {
            tokens.last_mut().expect("previous token").push(ch);
        } else {
            tokens.push(ch.to_string());
            previous = Some(kind);
        }
    }
    tokens
}

fn text_units(text: &str) -> f64 {
    text.chars()
        .map(|ch| if ch.is_ascii() { 0.6 } else { 1.0 })
        .sum()
}

fn wrapped_ddl(source: &str, capacity: f64) -> Vec<(usize, String)> {
    let mut rows = Vec::new();
    for (index, line) in source.split('\n').enumerate() {
        let mut row = String::new();
        for token in ddl_tokens(line) {
            if !row.is_empty() && text_units(&row) + text_units(&token) > capacity {
                rows.push((index + 1, std::mem::take(&mut row)));
            }
            if !row.is_empty() || !token.trim().is_empty() {
                row.push_str(&token);
            }
        }
        if !row.is_empty() || line.is_empty() {
            rows.push((index + 1, row));
        }
    }
    rows
}

/// The DDL panel of a line animation: the same for every frame, so it is laid
/// out once (I-732, 2026-11-07).
struct DdlPanel {
    panel_width: f64,
    rows: Vec<(usize, String)>,
}

impl DdlPanel {
    fn new(source: &str, height: f64) -> Self {
        let font_size = height / 22.0 * 0.77;
        let margin = height * 0.03;
        let widest_token = source
            .lines()
            .flat_map(ddl_tokens)
            .map(|token| text_units(&token))
            .fold(0.0_f64, f64::max);
        let panel_width = (height * 0.90).max(widest_token * font_size + 2.0 * margin);
        let rows = wrapped_ddl(source, (panel_width - 2.0 * margin) / font_size);
        Self { panel_width, rows }
    }
}

fn composed_frame(
    panel: &DdlPanel,
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
    let line_height = height / 22.0;
    let font_size = line_height * 0.77;
    let margin = height * 0.03;
    let panel_width = panel.panel_width;
    let rows = &panel.rows;
    let visible_rows = 21_usize;
    let focus = if frame == 0 {
        0
    } else {
        ranges
            .get(frame - 1)
            .and_then(|spans| spans.first())
            .and_then(|&(first_line, last_line)| {
                let mut matching = rows.iter().enumerate().filter_map(|(index, (line, _))| {
                    (first_line <= *line && *line <= last_line).then_some(index)
                });
                let first = matching.next()?;
                let last = matching.next_back().unwrap_or(first);
                Some(first + (last - first) / 2)
            })
            .unwrap_or(0)
    };
    let first = if frame == 0 {
        0
    } else {
        focus.saturating_sub(visible_rows / 2)
    };
    let mut text = String::new();
    for (row, (line, value)) in rows.iter().skip(first).take(visible_rows).enumerate() {
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
            "<text x=\"{}\" y=\"{}\" font-size=\"{}\" fill=\"{}\" font-weight=\"{}\">{}</text>",
            margin,
            (row as f64 + 1.0) * line_height,
            font_size,
            color,
            weight,
            xml_escape(value)
        ));
    }
    Ok(format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{}\" height=\"{}\" viewBox=\"0 0 {} {}\"><rect width=\"{}\" height=\"{}\" fill=\"#ffffff\"/><g font-family=\"{}\">{}</g><g transform=\"translate({} 0)\">{}</g></svg>",
        panel_width + width,
        height,
        panel_width + width,
        height,
        panel_width + width,
        height,
        xml_escape(family),
        text,
        panel_width,
        &svg[start + 1..end]
    ))
}

/// Compile a saved visible document and return a frame for each Score instruction.
#[uniffi::export]
pub fn line_animation(input_bytes: Vec<u8>) -> Vec<u8> {
    line_animation_bytes(&input_bytes)
}

/// [`line_animation`] over borrowed bytes, for a binding that need not copy them.
pub fn line_animation_bytes(input_bytes: &[u8]) -> Vec<u8> {
    owned_call(|| {
        let input: AnimationInput = parse(input_bytes, "invalid_animation_input")?;
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
        // The delivery is checked once and each frame draws its prefix; a
        // frame carries only the SVG a host reads (I-732, 2026-11-07).
        let checked = inku_pipeline::core_boundary::CheckedDeliveryRender::new(
            &delivery,
            input.options.clone().into(),
            &input.compiler,
            input.clip,
        )
        .map_err(|error| refusal("render_refused", &error.to_string()))?;
        let panel = input
            .show_ddl
            .then(|| DdlPanel::new(&input.document.source, input.options.canvas.height));
        let mut frames = Vec::with_capacity(ranges.len() + 1);
        let mut matches_saved = false;
        for index in 0..=ranges.len() {
            let output = checked
                .render((index < ranges.len()).then_some(index))
                .map_err(|error| refusal("render_refused", &error.to_string()))?;
            if index == ranges.len() {
                matches_saved = output.svg == input.saved_svg;
            }
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
            let svg = match &panel {
                Some(panel) => composed_frame(
                    panel,
                    &output.svg,
                    &input.font_family,
                    &ranges,
                    index,
                    input.options.canvas.width,
                    input.options.canvas.height,
                )?,
                None => output.svg,
            };
            frames.push(serde_json::json!({"instruction_count": index, "lines": selected, "svg": svg}));
        }
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
        // One call gives the bytes the two calls give (I-732).
        let compile_input = serde_json::json!({"document": input["document"], "definitions": input["definitions"], "compiler": input["compiler"]});
        let delivery = compile_document(serde_json::to_vec(&compile_input).unwrap());
        let render_input = serde_json::json!({"delivery": serde_json::from_slice::<serde_json::Value>(&delivery).unwrap(), "options": input["options"], "compiler": input["compiler"], "clip": input["clip"]});
        let two = render_compiled_svg_limited(serde_json::to_vec(&render_input).unwrap(), 32 << 20);
        let mut one_input = compile_input.clone();
        one_input["options"] = input["options"].clone();
        one_input["clip"] = input["clip"].clone();
        let one = compile_and_render_svg_limited(serde_json::to_vec(&one_input).unwrap(), 32 << 20);
        let mut expected = b"{\"delivery\":".to_vec();
        expected.extend_from_slice(&delivery);
        expected.extend_from_slice(b",\"rendered\":");
        expected.extend_from_slice(&two.json_bytes);
        expected.push(b'}');
        assert!(two.svg.is_some(), "{}", String::from_utf8_lossy(&two.json_bytes));
        assert_eq!(one.json_bytes, expected);
        assert_eq!(one.svg, two.svg);
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
        assert!(frames.iter().all(|frame| frame.get("art_svg").is_none()));
        input["saved_svg"] = frames[2]["svg"].clone();
        let same: serde_json::Value =
            serde_json::from_slice(&line_animation(serde_json::to_vec(&input).unwrap())).unwrap();
        assert_eq!(same["matches_saved_svg"], true);
        // Each frame is the drawing the delivery's own prefix makes, checked
        // once rather than per frame (I-732).
        let parsed: AnimationInput = serde_json::from_value(input.clone()).unwrap();
        let (delivery, ranges) = inku_pipeline::core_boundary::compile_committed_with_line_ranges(
            parsed.document.document().unwrap(),
            &parsed.definitions,
            &parsed.compiler,
        )
        .unwrap();
        for index in 0..=ranges.len() {
            let expected = if index == ranges.len() {
                inku_pipeline::core_boundary::render_delivery(
                    &delivery,
                    parsed.options.clone().into(),
                    &parsed.compiler,
                    parsed.clip,
                )
            } else {
                inku_pipeline::core_boundary::render_delivery_instruction_prefix(
                    &delivery,
                    parsed.options.clone().into(),
                    &parsed.compiler,
                    parsed.clip,
                    index,
                )
            }
            .unwrap();
            assert_eq!(same["frames"][index]["svg"], expected.svg.as_str());
        }
        input["show_ddl"] = true.into();
        let composed: serde_json::Value =
            serde_json::from_slice(&line_animation(serde_json::to_vec(&input).unwrap())).unwrap();
        assert_eq!(composed["matches_saved_svg"], same["matches_saved_svg"]);
        for index in 0..3 {
            let art = same["frames"][index]["svg"].as_str().unwrap();
            let body = &art[art.find('>').unwrap() + 1..art.rfind("</svg>").unwrap()];
            assert!(
                composed["frames"][index]["svg"]
                    .as_str()
                    .unwrap()
                    .contains(body)
            );
            assert_eq!(
                composed["frames"][index]["lines"],
                same["frames"][index]["lines"]
            );
        }
    }

    #[test]
    fn composed_frame_scrolls_without_shrinking_or_splitting_words() {
        let source = (1..=45)
            .map(|i| format!("行{i:02} 長い文章と<記号>"))
            .collect::<Vec<_>>()
            .join("\n");
        let svg =
            "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"10\" height=\"20\"/></svg>";
        let ranges = vec![vec![(30, 30)]];
        let panel = DdlPanel::new(&source, 20.0);
        let first = composed_frame(&panel, svg, "Font & Family", &ranges, 0, 10.0, 20.0).unwrap();
        let middle = composed_frame(&panel, svg, "Font & Family", &ranges, 1, 10.0, 20.0).unwrap();
        assert!(first.contains("行01") && !first.contains("行45"));
        assert!(middle.contains("行30") && !middle.contains("行01"));
        assert_eq!(first.matches("font-size=").count(), 21);
        assert!(middle.contains("Font &amp; Family"));
        assert!(middle.contains("<rect width=\"10\" height=\"20\"/>"));
        assert!(middle.contains("width=\"28\" height=\"20\""));
        assert!(middle.contains("translate(18 0)"));
        let last = composed_frame(
            &panel,
            svg,
            "Font & Family",
            &[vec![(45, 45)]],
            1,
            10.0,
            20.0,
        )
        .unwrap();
        let last_line = last
            .split("<text ")
            .find(|element| element.contains("行45"))
            .unwrap();
        assert!(last_line.contains("y=\"10\""), "{last_line}");
        let distant = composed_frame(
            &panel,
            svg,
            "Font & Family",
            &[vec![(1, 1), (45, 45)]],
            1,
            10.0,
            20.0,
        )
        .unwrap();
        assert!(distant.contains("行01") && !distant.contains("行45"));
        let rows = wrapped_ddl(
            "縦0.118、縦0.296666。直径0.25。 Place a horizontal line.",
            8.0,
        );
        assert!(rows.iter().any(|(_, row)| row.contains("0.296666")));
        assert!(rows.iter().any(|(_, row)| row.contains("直径")));
        assert!(rows.iter().any(|(_, row)| row.contains("horizontal")));
        assert!(rows.iter().any(|(_, row)| row.contains("0.118")));
        let range_rows = wrapped_ddl("横0.05〜0.23、縦0.2～0.3。", 6.0);
        assert!(range_rows.iter().any(|(_, row)| row.contains("0.05〜0.23")));
        assert!(range_rows.iter().any(|(_, row)| row.contains("0.2～0.3")));
        let count_rows = wrapped_ddl("円を1個置く。線を100本引く。", 5.0);
        assert!(count_rows.iter().any(|(_, row)| row.contains("1個")));
        assert!(count_rows.iter().any(|(_, row)| row.contains("100本")));
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CompileRenderInput {
    document: VisibleDocument,
    definitions: Vec<inku_ddl::MacroDefinition>,
    compiler: CompilerOptions,
    options: PipelineRenderOptions,
    clip: ClipPolicy,
}

/// [`compile_document`] and then [`render_compiled_svg_limited`] in one call,
/// so the host does not read the delivery and hand it back (I-732,
/// 2026-11-07). The input is the compile input with the render `options` and
/// `clip`. The answer is `{"delivery": <the compiled delivery>, "rendered":
/// <render_compiled_svg_limited's JSON>}` with the SVG apart, `"rendered":
/// null` for a delivery without a Score, or the refusal either call gives.
#[uniffi::export]
pub fn compile_and_render_svg_limited(
    input_bytes: Vec<u8>,
    max_svg_bytes: u64,
) -> super::NativeSvgOutput {
    let limit = match super::native_svg_limit(max_svg_bytes) {
        Ok(limit) => limit,
        Err(refusal) => return refusal,
    };
    catch_unwind(AssertUnwindSafe(|| {
        let refused = |bytes: Vec<u8>| -> super::NativeSvgOutput { (bytes, None).into() };
        let input: CompileRenderInput = match parse(&input_bytes, "invalid_compile_input") {
            Ok(input) => input,
            Err(bytes) => return refused(bytes),
        };
        let document = match input.document.document() {
            Ok(document) => document,
            Err(error) => {
                let code = serde_json::to_value(error).expect("protocol error serializes");
                return refused(refusal(
                    code.as_str().expect("protocol error is a string"),
                    &format!("{error:?}"),
                ));
            }
        };
        let delivery = match inku_pipeline::core_boundary::compile_committed(
            document,
            &input.definitions,
            &input.compiler,
        ) {
            Ok(delivery) => delivery,
            Err(error) => return refused(refusal("compile_refused", &error.to_string())),
        };
        // Each part keeps the bytes its own call gives.
        let Ok(delivery_bytes) = serde_json::to_vec(&delivery) else {
            return refused(refusal("invalid_compiled_delivery", "delivery serialization"));
        };
        let joined = |rendered: &[u8]| -> Vec<u8> {
            let mut bytes = b"{\"delivery\":".to_vec();
            bytes.extend_from_slice(&delivery_bytes);
            bytes.extend_from_slice(b",\"rendered\":");
            bytes.extend_from_slice(rendered);
            bytes.push(b'}');
            bytes
        };
        if delivery.score.is_none() {
            return refused(joined(b"null"));
        }
        let output = match inku_pipeline::core_boundary::render_delivery_with_svg_limit(
            &delivery,
            input.options.into(),
            &input.compiler,
            input.clip,
            limit,
        ) {
            Ok(output) => output,
            Err(error) => {
                return refused(refusal(
                    super::saved_render_error_code(&error),
                    &error.to_string(),
                ));
            }
        };
        let (rendered, svg) =
            super::separated_saved_output(output, super::MAX_SAVED_RENDER_METADATA_BYTES);
        let Some(svg) = svg else {
            return refused(rendered);
        };
        (joined(&rendered), Some(svg)).into()
    }))
    .unwrap_or_else(|_| (refusal("internal_invariant", "the core panicked"), None).into())
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
