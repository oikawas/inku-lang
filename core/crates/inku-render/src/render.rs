//! Coarse portable render boundary and render-specific metadata.

use crate::types::{
    Canvas, CanvasGroundSpec, Primitive, RenderMetadata, Score, SurfaceTexture,
    SurfaceTextureMetadata, SvgProfile,
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
