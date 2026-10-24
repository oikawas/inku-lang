//! Build the image requests and read their answers with the shared core, for
//! trying a Vision model's DDL outside a host.
//!
//! ```sh
//! scripts/rust-toolchain.sh run -q -p inku-pipeline --example image-ddl --locked --offline -- write-prompt <<'JSON'
//! {"language":"ja","original":[883,1277],"image":{"media_type":"image/png","width":883,"height":1277,"sha256":"<64 hex>","byte_len":1234}}
//! JSON
//! ```
//!
//! Commands, each reading one JSON object on stdin and writing one on stdout:
//! `write-prompt` (`language`, `original`, `image`), `review-prompt` (also
//! `drawing` and `current_ddl`), `feedback` (`prompt`, `rejected_ddl`,
//! `problems`), `finish` (`language`, `original`, `sent`, `response`: the
//! model's answer as sent back) and `render` (`language`, `source`, `paper`,
//! optional `long_side`). They use the default catalog, the installation's
//! default resource limits, render seed 1, and the paper nearest the image
//! with the drawing fitted into it.

use std::io::{self, Read};

use inku_ddl::ResolvedInstructionLanguage;
use inku_pipeline::core_boundary::{
    CatalogMode, ClipPolicy, CompilerOptions, MacroExpansionLimitsDto, ResolvedHostOptions,
    ResolvedPaletteColorDto, ResolvedPaletteDto,
};
use inku_pipeline::image_ddl::{
    ImageCanvas, ImageDdlContext, ImageDdlLimits, ImageDdlProblem, build_image_ddl_prompt,
    build_image_ddl_review_prompt, check_image_ddl, image_ddl_source, parse_image_ddl_response,
    render_image_ddl, review_canvas_size, with_image_ddl_feedback,
};
use inku_pipeline::machine::{PipelineRenderCanvas, PipelineRenderOptions};
use inku_pipeline::prompts::{LlmPrompt, PromptImage, PromptLimits};
use inku_pipeline::protocol::DecimalU64;
use inku_score::{
    CANVAS_FORMAT_REGISTRY_ID, CanvasFit, Color, HardResourcePolicy, OperationalResourceBudget,
    ResourceBudget, ResourceDemand, ScoreErrorPolicy, canvas_format_registry_digest,
};
use serde::Deserialize;
use serde_json::{Value, json};

const LIMITS: PromptLimits = PromptLimits {
    max_catalog_entries: 64,
    max_summary_bytes: 8192,
    max_catalog_serialized_bytes: 1024 * 1024,
    max_source_bytes: 400_000,
    max_response_bytes: 1024 * 1024,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PromptInput {
    language: ResolvedInstructionLanguage,
    original: (u32, u32),
    image: PromptImage,
    #[serde(default)]
    drawing: Option<PromptImage>,
    #[serde(default)]
    current_ddl: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FeedbackInput {
    prompt: LlmPrompt,
    rejected_ddl: String,
    problems: Vec<ImageDdlProblem>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FinishInput {
    language: ResolvedInstructionLanguage,
    original: (u32, u32),
    sent: (u32, u32),
    response: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RenderInput {
    language: ResolvedInstructionLanguage,
    source: String,
    paper: String,
    #[serde(default)]
    long_side: Option<f64>,
}

fn main() -> Result<(), String> {
    let command = std::env::args().nth(1).ok_or("missing command")?;
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|error| format!("read stdin: {error}"))?;
    let output = match command.as_str() {
        "write-prompt" | "review-prompt" => prompt(&command, &input)?,
        "feedback" => {
            let input: FeedbackInput = parse(&input)?;
            let prompt =
                with_image_ddl_feedback(input.prompt, &input.rejected_ddl, &input.problems, LIMITS)
                    .map_err(|error| error.to_string())?;
            serde_json::to_value(prompt).map_err(|error| error.to_string())?
        }
        "finish" => finish(&input)?,
        "render" => {
            let input: RenderInput = parse(&input)?;
            let svg = render(&input)?;
            json!({ "svg": svg })
        }
        other => return Err(format!("unknown command: {other}")),
    };
    println!("{output}");
    Ok(())
}

fn parse<T: for<'de> Deserialize<'de>>(input: &str) -> Result<T, String> {
    serde_json::from_str(input).map_err(|error| format!("parse input: {error}"))
}

fn prompt(command: &str, input: &str) -> Result<Value, String> {
    let input: PromptInput = parse(input)?;
    let canvas = ImageCanvas::of(input.original, (input.image.width, input.image.height))
        .ok_or("image has no ratio")?;
    let palette = palette();
    let compiler = compiler(canvas.nearest_format_id);
    let context = ImageDdlContext {
        image: &input.image,
        canvas,
        palette: &palette,
        limits: ImageDdlLimits::of(&compiler),
    };
    let prompt = if command == "write-prompt" {
        build_image_ddl_prompt(&context, input.language, LIMITS)
    } else {
        build_image_ddl_review_prompt(
            &context,
            input.drawing.as_ref().ok_or("review needs drawing")?,
            input
                .current_ddl
                .as_deref()
                .ok_or("review needs current_ddl")?,
            input.language,
            LIMITS,
        )
    }
    .map_err(|error| error.to_string())?;
    serde_json::to_value(prompt).map_err(|error| error.to_string())
}

fn finish(input: &str) -> Result<Value, String> {
    let input: FinishInput = parse(input)?;
    let canvas = ImageCanvas::of(input.original, input.sent).ok_or("image has no ratio")?;
    let ddl = match parse_image_ddl_response(&input.response, LIMITS) {
        Ok(ddl) => ddl,
        Err(error) => return Ok(json!({ "error": error.code() })),
    };
    let source = image_ddl_source(&ddl, canvas, input.language);
    let check = check_image_ddl(&source, input.language, &compiler(canvas.nearest_format_id))
        .map_err(|error| error.to_string())?;
    Ok(json!({
        "ddl": ddl,
        "source": source,
        "paper": canvas.nearest_format_id,
        "check": check,
    }))
}

fn render(input: &RenderInput) -> Result<String, String> {
    let compiler = compiler(&input.paper);
    let (width, height) = review_canvas_size(&input.paper).ok_or("unknown paper")?;
    let scale = input.long_side.map_or(1.0, |long| long / width.max(height));
    let options = PipelineRenderOptions {
        resolved_color_map: inku_render::palette::default_color_map(),
        catalog_id: Some("default".into()),
        canvas: PipelineRenderCanvas {
            width: width * scale,
            height: height * scale,
        },
        canvas_aspect_id: input.paper.clone(),
        svg_profile: inku_render::types::SvgProfile::Display,
        render_seed: Some(DecimalU64::new(1)),
        composition_seed: None,
        wild: false,
        error_policy: ScoreErrorPolicy::OmitAndContinue,
    };
    let clip = ClipPolicy {
        tolerance_pixels: 0.1,
        max_nodes: DecimalU64::new(50_000),
        max_path_elements: DecimalU64::new(200_000),
        max_flattened_points: DecimalU64::new(200_000),
        max_work: DecimalU64::new(10_000_000),
        max_output_vertices: DecimalU64::new(200_000),
    };
    render_image_ddl(&input.source, input.language, &compiler, options, clip)
        .map_err(|error| error.to_string())
}

/// The default catalog's palette, resolved as a host resolves it.
fn palette() -> ResolvedPaletteDto {
    let palette = inku_render::palette::work_palette_context(
        &inku_render::palette::default_color_map(),
        None,
        Some("default"),
        Color::White,
    )
    .expect("the default color map resolves");
    let dto = |color: inku_score::ResolvedPaletteColor| ResolvedPaletteColorDto {
        abstract_color: color.abstract_color(),
        concrete_rgb: color.concrete_rgb(),
        oklch_lightness: color.oklch_lightness(),
    };
    ResolvedPaletteDto {
        background: dto(palette.background()),
        black: dto(palette.black()),
        white: dto(palette.white()),
        observations: palette.observations().map(|colors| colors.map(dto)),
        paints: None,
    }
}

/// The installation's default compile authority on `paper`, fitting a
/// declared ratio into it.
fn compiler(paper: &str) -> CompilerOptions {
    let host = ResolvedHostOptions::new(
        paper,
        CANVAS_FORMAT_REGISTRY_ID,
        canvas_format_registry_digest().expect("the registry digests"),
        "default",
        CatalogMode::Default,
        Color::White,
        palette(),
    )
    .expect("the default host options are valid")
    .with_canvas_fit(Some(CanvasFit::Contain));
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 4096,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 128,
            anchor_instances: 4096,
            transform_instances: 4096,
            placement_instances: 64,
            fill_instances: 64,
        },
    };
    CompilerOptions {
        host,
        composition_seed: None,
        macro_expansion_limits: MacroExpansionLimitsDto {
            max_invocations: DecimalU64::new(64),
            max_depth: DecimalU64::new(16),
            max_evaluation_steps: DecimalU64::new(8192),
            max_nodes_per_invocation: DecimalU64::new(128),
            max_total_nodes: DecimalU64::new(128),
        },
        error_policy: ScoreErrorPolicy::OmitAndContinue,
        hard_resource_policy: HardResourcePolicy {
            identity: "installation-default.v1".into(),
            budget,
        },
        operational_resource_budget: OperationalResourceBudget(budget),
    }
}
