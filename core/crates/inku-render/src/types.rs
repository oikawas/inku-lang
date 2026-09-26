//! Renderer-owned transport and output types.
//!
//! Score value types are owned by `inku-score` and re-exported here to
//! preserve the existing `inku_render::types` source API.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub use inku_score::types::*;
pub use inku_score::{
    ScoreErrorPolicy, ScoreExecutionDiagnostic, ScoreExecutionDisposition, ScoreExecutionReason,
    ScoreExecutionSummary,
};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct CanvasSize {
    pub width: f64,
    pub height: f64,
}

impl CanvasSize {
    #[must_use]
    pub const fn new(width: f64, height: f64) -> Self {
        Self { width, height }
    }

    #[must_use]
    pub fn unit(self) -> f64 {
        self.width.min(self.height)
    }
}

macro_rules! string_enum {
    ($name:ident { $($variant:ident),+ $(,)? }) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
        #[serde(rename_all = "snake_case")]
        pub enum $name { $($variant),+ }
    };
}
string_enum!(SvgProfile {
    Display,
    Editable,
    Compat,
    // Editable's groups and IDs with display's appearance, so that a host can
    // draw each instruction group on its own, in time.
    Live,
});

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderOptions {
    pub resolved_color_map: BTreeMap<String, String>,
    pub catalog_id: Option<String>,
    pub canvas: CanvasSize,
    pub canvas_aspect_id: String,
    pub svg_profile: SvgProfile,
    pub render_seed: Option<Seed>,
    pub composition_seed: Option<Seed>,
    pub wild: bool,
    #[serde(default)]
    pub error_policy: ScoreErrorPolicy,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderRequest {
    pub score: Score,
    pub options: RenderOptions,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SurfaceTextureMetadata {
    pub instruction_index: usize,
    pub texture: SurfaceTexture,
    pub density: f64,
    pub opacity: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RenderResourceFailure {
    BudgetExceeded {
        exceeded: inku_score::ResourceBudgetExceeded,
    },
    ArithmeticOverflow {
        dimension: inku_score::ResourceDimension,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderResourceOmission {
    pub owner: inku_score::SavedScoreResourceOwner,
    pub cause_owner: inku_score::SavedScoreResourceOwner,
    pub failure: RenderResourceFailure,
    pub disposition: inku_score::SavedScoreResourceDisposition,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderResourceExecution {
    pub accounting_id: String,
    pub demand: inku_score::ResourceDemand,
    pub omissions: Vec<RenderResourceOmission>,
    pub relation_omissions: Vec<inku_score::SavedScoreRelationDiagnostic>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderMetadata {
    pub render_engine_id: String,
    pub render_engine_version: String,
    pub render_texture_version: String,
    pub render_texture_profile: SvgProfile,
    pub texture_degraded: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub render_canvas_ground: Option<CanvasGroundSpec>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub render_surface_textures: Vec<SurfaceTextureMetadata>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub execution: Option<ScoreExecutionSummary>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resource_execution: Option<RenderResourceExecution>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderOutput {
    pub svg: String,
    pub metadata: RenderMetadata,
}
