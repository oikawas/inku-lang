//! Host-neutral input types consumed by the render core.
//!
//! Python remains the schema authority. These types receive only a canonical,
//! already validated Score and resolved host data; they are not a second tool
//! schema and deliberately contain no Python or server-registry concepts.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// Integer seed domain accepted at the canonical JSON boundary.
///
/// `i128` covers serde_json's signed and unsigned integer range while leaving
/// room for the small deterministic offsets used inside the render engine.
pub type Seed = i128;

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(from = "[f64; 2]", into = "[f64; 2]")]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    #[must_use]
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }
}

impl From<[f64; 2]> for Point {
    fn from(value: [f64; 2]) -> Self {
        Self::new(value[0], value[1])
    }
}

impl From<(f64, f64)> for Point {
    fn from(value: (f64, f64)) -> Self {
        Self::new(value.0, value.1)
    }
}

impl From<Point> for [f64; 2] {
    fn from(value: Point) -> Self {
        [value.x, value.y]
    }
}

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

string_enum!(Primitive {
    Line,
    Circle,
    Ellipse,
    Triangle,
    Square,
    Polygon,
    Arc,
    Cloudform,
});
string_enum!(LineStyle {
    Solid,
    Dashed,
    Dotted,
    DashDot,
});
string_enum!(Weight {
    Silverpoint,
    Pencil,
    Pen,
    Rotring,
    Crayon,
    Chalk,
    BrushThin,
    BrushThick,
    Burin,
    Drypoint,
    Computer,
});
string_enum!(Thinness { Fine, ExtraFine });
string_enum!(Color {
    White,
    Black,
    Blue,
    Red,
    Green,
    Gray,
    Yellow,
    Orange,
    Purple,
});
string_enum!(SurfaceTexture {
    None,
    Solid,
    Stipple,
    Hatch,
    Crosshatch,
    Aquatint,
    Grain,
    Wash,
    Bleed,
    PaperGrain,
});
string_enum!(SurfaceDirection {
    None,
    Horizontal,
    Vertical,
    DiagonalRising,
    DiagonalFalling,
});
string_enum!(SurfaceSpacingGradient {
    None,
    CoarseToDense,
    DenseToCoarse,
});
string_enum!(GroundMaterial {
    Plain,
    Paper,
    Washi,
    InkWash,
    CharcoalGround,
    Canvas,
    DrawingPaper,
    Mezzotint,
});
string_enum!(GroundTone {
    White,
    OffWhite,
    Warm,
    Cool,
    Gray,
    Black,
});
string_enum!(GroundGrain {
    None,
    Fine,
    Medium,
    Coarse,
});
string_enum!(Amplitude {
    Fine,
    Medium,
    Broad,
});
string_enum!(Frequency { Slow, Medium, High });
string_enum!(Quality {
    None,
    White,
    Perlin,
    Pink,
    Wave,
});
string_enum!(Dimension {
    PositionX,
    PositionY,
    Angle,
    Length,
    Rotation,
    Radius,
});
string_enum!(Layout {
    Horizontal,
    Vertical,
    Radial,
    Scatter,
    Grid,
});
string_enum!(ArrangementPath {
    None,
    Diagonal,
    Wave,
    TopToBottom,
    LeftToRight,
    RightHalf,
});
string_enum!(Density {
    None,
    Low,
    Medium,
    High,
});
string_enum!(Fade {
    None,
    Outward,
    Directional,
});
string_enum!(RhythmSpacing {
    None,
    Syncopated,
    Accelerando,
    Loose,
});
string_enum!(RelationType {
    Along,
    NotTouching,
    Cutting,
    Between,
    Touching,
});
string_enum!(RelationGap {
    Narrow,
    Medium,
    Wide,
});
string_enum!(InstructionMode { Additive, Carve });
string_enum!(CarveDepth {
    Light,
    Half,
    Bright,
});
string_enum!(PresenceKind {
    None,
    FigureLike,
    CreatureLike,
    GroupLike,
});
string_enum!(PresenceIntensity { Low, Medium, High });
string_enum!(PresenceSymmetry {
    None,
    Bilateral,
    Radial,
});
string_enum!(GazePressure {
    None,
    Low,
    Medium,
    High,
});
string_enum!(ContourDensity { Low, Medium, High });
string_enum!(SvgProfile {
    Display,
    Editable,
    Compat,
});

const fn default_line_style() -> LineStyle {
    LineStyle::Solid
}
const fn default_weight() -> Weight {
    Weight::Pen
}
const fn default_color() -> Color {
    Color::Black
}
const fn default_background() -> Color {
    Color::White
}
const fn default_mode() -> InstructionMode {
    InstructionMode::Additive
}
const fn default_amplitude() -> Amplitude {
    Amplitude::Medium
}
const fn default_frequency() -> Frequency {
    Frequency::Medium
}
const fn default_quality() -> Quality {
    Quality::None
}
const fn default_surface_texture() -> SurfaceTexture {
    SurfaceTexture::None
}
const fn default_surface_direction() -> SurfaceDirection {
    SurfaceDirection::None
}
const fn default_spacing_gradient() -> SurfaceSpacingGradient {
    SurfaceSpacingGradient::None
}
const fn default_ground_material() -> GroundMaterial {
    GroundMaterial::Plain
}
const fn default_ground_tone() -> GroundTone {
    GroundTone::White
}
const fn default_ground_grain() -> GroundGrain {
    GroundGrain::None
}
const fn default_layout() -> Layout {
    Layout::Horizontal
}
const fn default_arrangement_path() -> ArrangementPath {
    ArrangementPath::None
}
const fn default_density() -> Density {
    Density::None
}
const fn default_fade() -> Fade {
    Fade::None
}
const fn default_rhythm_spacing() -> RhythmSpacing {
    RhythmSpacing::None
}
const fn default_relation_gap() -> RelationGap {
    RelationGap::Medium
}

fn default_score_version() -> String {
    "0.1.0".to_owned()
}

fn default_canvas() -> Canvas {
    Canvas::Id("square".to_owned())
}

fn default_surface_density() -> f64 {
    0.35
}
fn default_surface_scale() -> f64 {
    0.35
}
fn default_surface_opacity() -> f64 {
    0.28
}
fn default_tone_steps() -> u8 {
    3
}
fn default_ground_density() -> f64 {
    0.20
}
fn default_ground_opacity() -> f64 {
    0.12
}
fn default_count() -> u32 {
    1
}
fn default_group_size() -> u32 {
    1
}
fn default_jitter() -> f64 {
    0.12
}
fn default_margin() -> f64 {
    0.1
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SurfaceSpec {
    #[serde(default = "default_surface_texture")]
    pub texture: SurfaceTexture,
    #[serde(default = "default_surface_density")]
    pub density: f64,
    #[serde(default = "default_surface_scale")]
    pub scale: f64,
    #[serde(default = "default_surface_opacity")]
    pub opacity: f64,
    #[serde(default)]
    pub bleed: f64,
    #[serde(default = "default_surface_direction")]
    pub direction: SurfaceDirection,
    #[serde(default = "default_spacing_gradient")]
    pub spacing_gradient: SurfaceSpacingGradient,
    #[serde(default = "default_tone_steps")]
    pub tone_steps: u8,
    #[serde(default)]
    pub seed: Option<Seed>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CanvasGroundSpec {
    #[serde(default = "default_ground_material")]
    pub material: GroundMaterial,
    #[serde(default = "default_ground_tone")]
    pub tone: GroundTone,
    #[serde(default = "default_ground_grain")]
    pub grain: GroundGrain,
    #[serde(default = "default_ground_density")]
    pub density: f64,
    #[serde(default = "default_ground_opacity")]
    pub opacity: f64,
    #[serde(default)]
    pub seed: Option<Seed>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CanvasSpec {
    #[serde(default = "default_canvas_aspect")]
    pub aspect: String,
    #[serde(default)]
    pub ground: Option<CanvasGroundSpec>,
}

fn default_canvas_aspect() -> String {
    "square".to_owned()
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Canvas {
    Id(String),
    Spec(CanvasSpec),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Variation {
    #[serde(default = "default_amplitude")]
    pub amplitude: Amplitude,
    #[serde(default = "default_frequency")]
    pub frequency: Frequency,
    #[serde(default = "default_quality")]
    pub quality: Quality,
    #[serde(default)]
    pub dimensions: Vec<Dimension>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Arrangement {
    #[serde(default = "default_count")]
    pub count: u32,
    #[serde(default = "default_group_size")]
    pub group_size: u32,
    #[serde(default = "default_layout")]
    pub layout: Layout,
    #[serde(default)]
    pub rows: Option<u32>,
    #[serde(default)]
    pub cols: Option<u32>,
    #[serde(default = "default_jitter")]
    pub jitter: f64,
    #[serde(default = "default_arrangement_path")]
    pub path: ArrangementPath,
    #[serde(default)]
    pub color_cycle: Vec<Color>,
    #[serde(default = "default_margin")]
    pub margin: f64,
    #[serde(default)]
    pub center: Option<Point>,
    #[serde(default)]
    pub radius: Option<f64>,
    #[serde(default = "default_density")]
    pub density: Density,
    #[serde(default)]
    pub cluster_count: Option<u32>,
    #[serde(default = "default_fade")]
    pub fade: Fade,
    #[serde(default)]
    pub preserve_space: bool,
    #[serde(default = "default_rhythm_spacing")]
    pub rhythm_spacing: RhythmSpacing,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AtRegion {
    pub region: [f64; 4],
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Relation {
    #[serde(rename = "type")]
    pub kind: RelationType,
    #[serde(default = "default_relation_gap")]
    pub gap: RelationGap,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Instruction {
    pub primitive: Primitive,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default, rename = "from")]
    pub from_: Option<Point>,
    #[serde(default)]
    pub to: Option<Point>,
    #[serde(default)]
    pub center: Option<Point>,
    #[serde(default)]
    pub radius: Option<f64>,
    #[serde(default)]
    pub sides: Option<u8>,
    #[serde(default)]
    pub position: Option<Point>,
    #[serde(default)]
    pub size: Option<Point>,
    #[serde(default)]
    pub angle_start: Option<f64>,
    #[serde(default)]
    pub angle_end: Option<f64>,
    #[serde(default)]
    pub rotation: Option<f64>,
    #[serde(default)]
    pub filled: bool,
    #[serde(default = "default_line_style")]
    pub style: LineStyle,
    #[serde(default = "default_weight")]
    pub weight: Weight,
    #[serde(default = "default_mode", rename = "mode")]
    pub mode_: InstructionMode,
    #[serde(default)]
    pub carve_depth: Option<CarveDepth>,
    #[serde(default = "default_color")]
    pub color: Color,
    #[serde(default)]
    pub color_hint: Option<String>,
    #[serde(default)]
    pub variation: Option<Variation>,
    #[serde(default)]
    pub arrangement: Option<Arrangement>,
    #[serde(default)]
    pub at: Option<AtRegion>,
    #[serde(default)]
    pub relation: Option<Relation>,
    #[serde(default)]
    pub thinness: Option<Thinness>,
    #[serde(default)]
    pub surface: Option<SurfaceSpec>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Presence {
    #[serde(default = "default_presence_kind")]
    pub kind: PresenceKind,
    #[serde(default = "default_presence_intensity")]
    pub intensity: PresenceIntensity,
    #[serde(default)]
    pub center: Option<Point>,
    #[serde(default = "default_presence_symmetry")]
    pub symmetry: PresenceSymmetry,
    #[serde(default = "default_gaze_pressure")]
    pub gaze_pressure: GazePressure,
    #[serde(default = "default_contour_density")]
    pub contour_density: ContourDensity,
}

const fn default_presence_kind() -> PresenceKind {
    PresenceKind::None
}
const fn default_presence_intensity() -> PresenceIntensity {
    PresenceIntensity::Medium
}
const fn default_presence_symmetry() -> PresenceSymmetry {
    PresenceSymmetry::None
}
const fn default_gaze_pressure() -> GazePressure {
    GazePressure::None
}
const fn default_contour_density() -> ContourDensity {
    ContourDensity::Low
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Score {
    #[serde(default = "default_score_version")]
    pub version: String,
    #[serde(default = "default_canvas")]
    pub canvas: Canvas,
    #[serde(default = "default_background")]
    pub background: Color,
    #[serde(default)]
    pub presence: Option<Presence>,
    pub instructions: Vec<Instruction>,
}

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
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RenderOutput {
    pub svg: String,
    pub metadata: RenderMetadata,
}
