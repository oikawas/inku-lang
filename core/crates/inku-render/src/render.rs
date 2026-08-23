//! Coarse portable render boundary, SVG orchestration, and render metadata.

use std::fmt;

use crate::arrangement::{ArrangementRequest, expand_arrangement};
use crate::marks::{MarkContext, MarkError, render_instruction};
use crate::palette::{default_color, work_color_assignment};
use crate::performance::{PerformanceRequest, resolve_performance};
use crate::support::{DEFAULT_SUPPORT, support_for_ground};
use crate::svg::{Document, Element, format_number};
use crate::types::{
    Canvas, CanvasGroundSpec, Color, Instruction, InstructionMode, Primitive, RenderMetadata,
    RenderOutput, RenderRequest, Score, SurfaceTexture, SurfaceTextureMetadata, SvgProfile,
};
use crate::{RENDER_ENGINE_ID, RENDER_ENGINE_VERSION};

fn canvas_ground(score: &Score) -> Option<CanvasGroundSpec> {
    match &score.canvas {
        Canvas::Spec(canvas) => canvas
            .ground
            .as_ref()
            .filter(|ground| ground.material != crate::types::GroundMaterial::Plain)
            .cloned(),
        Canvas::Id(_) => None,
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RenderError {
    Mark(MarkError),
    NonFiniteSvg,
}

impl fmt::Display for RenderError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Mark(error) => error.fmt(formatter),
            Self::NonFiniteSvg => formatter.write_str("rendered SVG contains a non-finite value"),
        }
    }
}

impl std::error::Error for RenderError {}

impl From<MarkError> for RenderError {
    fn from(value: MarkError) -> Self {
        Self::Mark(value)
    }
}

fn owns_surface(primitive: Primitive) -> bool {
    matches!(
        primitive,
        Primitive::Circle
            | Primitive::Ellipse
            | Primitive::Square
            | Primitive::Triangle
            | Primitive::Polygon
            | Primitive::Cloudform
    )
}

/// Build the JSON-compatible render metadata carried beside the SVG.
#[must_use]
pub fn build_render_metadata(score: &Score, profile: SvgProfile) -> RenderMetadata {
    let render_surface_textures = score
        .instructions
        .iter()
        .enumerate()
        .filter_map(|(instruction_index, instruction)| {
            let surface = instruction.surface.as_ref()?;
            (owns_surface(instruction.primitive)
                && !matches!(
                    surface.texture,
                    SurfaceTexture::None | SurfaceTexture::Solid
                ))
            .then_some(SurfaceTextureMetadata {
                instruction_index,
                texture: surface.texture,
                density: surface.density,
                opacity: surface.opacity,
            })
        })
        .collect::<Vec<_>>();
    RenderMetadata {
        render_engine_id: RENDER_ENGINE_ID.to_owned(),
        render_engine_version: RENDER_ENGINE_VERSION.to_owned(),
        render_texture_version: "1".to_owned(),
        render_texture_profile: profile,
        texture_degraded: profile == SvgProfile::Compat && !render_surface_textures.is_empty(),
        render_canvas_ground: canvas_ground(score),
        render_surface_textures,
    }
}

fn color_name(color: Color) -> &'static str {
    match color {
        Color::White => "white",
        Color::Black => "black",
        Color::Blue => "blue",
        Color::Red => "red",
        Color::Green => "green",
        Color::Gray => "gray",
        Color::Yellow => "yellow",
        Color::Orange => "orange",
        Color::Purple => "purple",
    }
}

fn safe_svg_id(value: &str) -> String {
    let mut safe = String::with_capacity(value.len());
    let mut separator = false;
    for character in value.chars() {
        if character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | '-') {
            safe.push(character);
            separator = false;
        } else if !separator {
            safe.push('_');
            separator = true;
        }
    }
    let safe = safe.trim_matches(['.', '_', '-']);
    let safe = if safe.is_empty() { "item" } else { safe };
    if safe.starts_with(|character: char| character.is_ascii_alphabetic() || character == '_') {
        safe.to_owned()
    } else {
        format!("inku_{safe}")
    }
}

fn primitive_name(primitive: Primitive) -> &'static str {
    match primitive {
        Primitive::Line => "line",
        Primitive::Circle => "circle",
        Primitive::Ellipse => "ellipse",
        Primitive::Triangle => "triangle",
        Primitive::Square => "square",
        Primitive::Polygon => "polygon",
        Primitive::Arc => "arc",
        Primitive::Cloudform => "cloudform",
    }
}

fn instruction_id(instruction: &Instruction, index: usize) -> String {
    safe_svg_id(&format!(
        "instruction_{index:03}_{}_{}",
        primitive_name(instruction.primitive),
        color_name(instruction.color)
    ))
}

fn mark_id(instruction: &Instruction, instruction_index: usize, mark_index: usize) -> String {
    safe_svg_id(&format!(
        "mark_{instruction_index:03}_{mark_index:03}_{}",
        primitive_name(instruction.primitive)
    ))
}

fn background_color(
    request: &RenderRequest,
    assignment: &std::collections::BTreeMap<String, String>,
) -> String {
    let name = color_name(request.score.background);
    assignment
        .get(name)
        .or_else(|| request.options.resolved_color_map.get(name))
        .cloned()
        .unwrap_or_else(|| default_color(request.score.background).to_owned())
}

fn background_rect(request: &RenderRequest, color: &str) -> Element {
    Element::new("rect")
        .attr("id", "background")
        .attr("x", "0")
        .attr("y", "0")
        .attr("width", format_number(request.options.canvas.width))
        .attr("height", format_number(request.options.canvas.height))
        .attr("fill", color)
}

fn document_metadata(profile: SvgProfile) -> (String, String) {
    match profile {
        SvgProfile::Editable => (
            "inku render (editable SVG)".to_owned(),
            "Generated by inku. Groups and IDs are included for vector editing.".to_owned(),
        ),
        SvgProfile::Compat => (
            "inku render (compat SVG)".to_owned(),
            "Generated by inku. Portable SVG output.".to_owned(),
        ),
        SvgProfile::Display => (
            "inku render (display SVG)".to_owned(),
            "Generated by inku. Portable SVG output.".to_owned(),
        ),
    }
}

/// Render a canonical Score through the complete portable request boundary.
pub fn render(request: RenderRequest) -> Result<RenderOutput, RenderError> {
    let source_score = request.score.clone();
    let profile = request.options.svg_profile;
    let assignment = work_color_assignment(
        &request.options.resolved_color_map,
        request.options.render_seed,
        request.options.catalog_id.as_deref(),
    );
    let background = background_color(&request, &assignment);
    let performance = resolve_performance(PerformanceRequest {
        score: &request.score,
        performance_seed: request.options.render_seed,
        composition_seed: request.options.composition_seed,
        canvas: Some(request.options.canvas),
    });
    let support = canvas_ground(&performance.score).map_or(DEFAULT_SUPPORT, |ground| {
        support_for_ground(ground.material)
    });
    let mut ordered = performance
        .score
        .instructions
        .iter()
        .enumerate()
        .collect::<Vec<_>>();
    ordered.sort_by_key(|(_, instruction)| instruction.mode_ == InstructionMode::Carve);
    let placement_seed = request
        .options
        .composition_seed
        .or(request.options.render_seed);
    let structured = profile != SvgProfile::Display;
    let mut content = Element::new("g").attr("id", "layer_10_content");
    for (instruction_index, instruction) in ordered {
        let expanded = if instruction.arrangement.is_some() {
            expand_arrangement(ArrangementRequest {
                instruction,
                placement_seed,
                performance_seed: request.options.render_seed,
                canvas: Some(request.options.canvas),
            })
        } else {
            vec![instruction.clone()]
        };
        let mut instruction_group = Element::new("g");
        if structured {
            instruction_group.set_attr("id", instruction_id(instruction, instruction_index));
        }
        for (mark_index, single) in expanded.iter().enumerate() {
            let mut mark = render_instruction(
                single,
                MarkContext {
                    canvas: request.options.canvas,
                    color_map: &request.options.resolved_color_map,
                    work_assignment: &assignment,
                    render_seed: request.options.render_seed,
                    instruction_index,
                    mark_index,
                    wild: request.options.wild,
                    support,
                },
            )?;
            if structured {
                mark.set_attr("id", mark_id(single, instruction_index, mark_index));
                instruction_group.push(mark);
            } else {
                content.push(mark);
            }
        }
        if structured {
            content.push(instruction_group);
        }
    }
    let mut document = Document::new(request.options.canvas);
    if structured {
        let (title, description) = document_metadata(profile);
        let mut title_node = Element::new("title");
        title_node.push_text(title);
        document.push(title_node);
        let mut description_node = Element::new("desc");
        description_node.push_text(description);
        document.push(description_node);
        let mut metadata = Element::new("metadata").attr("id", "inku_metadata");
        metadata.push_text(format!(
            "{{\"generator\":\"inku\",\"svg_profile\":\"{}\"}}",
            match profile {
                SvgProfile::Display => "display",
                SvgProfile::Editable => "editable",
                SvgProfile::Compat => "compat",
            }
        ));
        document.push(metadata);
        let mut artboard = Element::new("g").attr("id", "inku_artboard");
        let mut background_layer = Element::new("g").attr("id", "layer_00_background");
        background_layer.push(background_rect(&request, &background));
        artboard.push(background_layer);
        artboard.push(content);
        artboard.push(Element::new("g").attr("id", "layer_20_presence"));
        document.push(artboard);
    } else {
        document.push(background_rect(&request, &background));
        document.push(content);
    }
    let svg = document.serialize();
    if svg.contains("NaN") || svg.contains("inf") || svg.contains("-inf") {
        return Err(RenderError::NonFiniteSvg);
    }
    Ok(RenderOutput {
        svg,
        metadata: build_render_metadata(&source_score, profile),
    })
}
