//! Host-neutral Score value types.
//!
//! Python remains the schema authority. These types receive only a canonical,
//! already validated Score and resolved host data; they are not a second tool
//! schema and deliberately contain no Python or server-registry concepts.

use std::fmt;

use serde::de::{MapAccess, Visitor, value::MapAccessDeserializer};
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
    Point,
    Cloudform,
});
string_enum!(ArcForm { Crescent });

/// The three cubic Bézier segments of the author-approved Saijiki crescent.
///
/// The values stay in the source SVG coordinate space so every host can derive
/// the same physical contour rather than approximating a crescent from an arc.
pub const CRESCENT_REFERENCE_CUBICS: [[Point; 4]; 3] = [
    [
        Point::new(106.0, 18.0),
        Point::new(76.0, 24.0),
        Point::new(62.0, 52.0),
        Point::new(82.0, 74.0),
    ],
    [
        Point::new(82.0, 74.0),
        Point::new(52.0, 63.0),
        Point::new(50.0, 27.0),
        Point::new(82.0, 14.0),
    ],
    [
        Point::new(82.0, 14.0),
        Point::new(92.0, 12.0),
        Point::new(100.0, 14.0),
        Point::new(106.0, 18.0),
    ],
];

/// Actual Bézier extrema of [`CRESCENT_REFERENCE_CUBICS`], not its control box.
pub const CRESCENT_REFERENCE_MIN: Point = Point::new(58.743_954_756_148_575, 13.215_390_309_173_47);
pub const CRESCENT_REFERENCE_MAX: Point = Point::new(106.0, 74.0);
pub const CRESCENT_REFERENCE_WIDTH: f64 = CRESCENT_REFERENCE_MAX.x - CRESCENT_REFERENCE_MIN.x;
pub const CRESCENT_REFERENCE_HEIGHT: f64 = CRESCENT_REFERENCE_MAX.y - CRESCENT_REFERENCE_MIN.y;
pub const CRESCENT_REFERENCE_ASPECT_RATIO: f64 =
    CRESCENT_REFERENCE_WIDTH / CRESCENT_REFERENCE_HEIGHT;

/// The fixed physical width-to-height ratio of the approved crescent contour.
#[must_use]
pub const fn crescent_reference_aspect_ratio() -> f64 {
    CRESCENT_REFERENCE_ASPECT_RATIO
}

/// Physical bounds of the reference crescent after fitting it into `size` about `center`.
///
/// `size` is the unrotated physical bounding box. The returned bounds include
/// the exact cubic extrema after clockwise SVG-space rotation.
#[must_use]
pub fn crescent_contour_bounds(
    center: Point,
    size: Point,
    rotation_degrees: f64,
) -> (Point, Point) {
    let mut min = Point::new(f64::INFINITY, f64::INFINITY);
    let mut max = Point::new(f64::NEG_INFINITY, f64::NEG_INFINITY);
    for cubic in CRESCENT_REFERENCE_CUBICS {
        let points =
            cubic.map(|point| crescent_transform_point(point, center, size, rotation_degrees));
        for t in cubic_extrema(points) {
            let point = cubic_point(points, t);
            min.x = min.x.min(point.x);
            min.y = min.y.min(point.y);
            max.x = max.x.max(point.x);
            max.y = max.y.max(point.y);
        }
    }
    (min, max)
}

/// Map a reference SVG coordinate to the centered physical crescent box.
#[must_use]
pub fn crescent_transform_point(
    reference: Point,
    center: Point,
    size: Point,
    rotation_degrees: f64,
) -> Point {
    let local = Point::new(
        (reference.x - CRESCENT_REFERENCE_MIN.x) / CRESCENT_REFERENCE_WIDTH * size.x - size.x / 2.0,
        (reference.y - CRESCENT_REFERENCE_MIN.y) / CRESCENT_REFERENCE_HEIGHT * size.y
            - size.y / 2.0,
    );
    let angle = rotation_degrees.to_radians();
    Point::new(
        center.x + local.x * angle.cos() - local.y * angle.sin(),
        center.y + local.x * angle.sin() + local.y * angle.cos(),
    )
}

fn cubic_point(points: [Point; 4], t: f64) -> Point {
    let inverse = 1.0 - t;
    Point::new(
        inverse.powi(3) * points[0].x
            + 3.0 * inverse.powi(2) * t * points[1].x
            + 3.0 * inverse * t.powi(2) * points[2].x
            + t.powi(3) * points[3].x,
        inverse.powi(3) * points[0].y
            + 3.0 * inverse.powi(2) * t * points[1].y
            + 3.0 * inverse * t.powi(2) * points[2].y
            + t.powi(3) * points[3].y,
    )
}

fn cubic_extrema(points: [Point; 4]) -> Vec<f64> {
    let mut roots = vec![0.0, 1.0];
    for values in [
        [points[0].x, points[1].x, points[2].x, points[3].x],
        [points[0].y, points[1].y, points[2].y, points[3].y],
    ] {
        let a = -values[0] + 3.0 * values[1] - 3.0 * values[2] + values[3];
        let b = 2.0 * (values[0] - 2.0 * values[1] + values[2]);
        let c = values[1] - values[0];
        if a.abs() <= 1.0e-12 {
            if b.abs() > 1.0e-12 {
                let root = -c / b;
                if (0.0..1.0).contains(&root) {
                    roots.push(root);
                }
            }
        } else {
            let discriminant = b * b - 4.0 * a * c;
            if discriminant >= 0.0 {
                let root = discriminant.sqrt();
                for value in [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)] {
                    if (0.0..1.0).contains(&value) {
                        roots.push(value);
                    }
                }
            }
        }
    }
    roots
}
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
    OilPaint,
    Burin,
    Drypoint,
    Computer,
});
string_enum!(Thinness { Fine, ExtraFine });
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SurfaceIntensity {
    #[default]
    Normal,
    Dense,
    Faint,
}

impl SurfaceIntensity {
    const fn is_normal(&self) -> bool {
        matches!(self, Self::Normal)
    }
}

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

/// One concrete work-palette observation used before Score materialization.
///
/// This is a non-wire DTO: Score keeps abstract colors, while the DDL resolver
/// needs the exact resolved RGB and the renderer's existing OKLCH lightness.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ResolvedPaletteColor {
    abstract_color: Color,
    concrete_rgb: [u8; 3],
    oklch_lightness: f64,
}

impl ResolvedPaletteColor {
    #[must_use]
    pub const fn new(abstract_color: Color, concrete_rgb: [u8; 3], oklch_lightness: f64) -> Self {
        Self {
            abstract_color,
            concrete_rgb,
            oklch_lightness,
        }
    }

    #[must_use]
    pub const fn abstract_color(self) -> Color {
        self.abstract_color
    }

    #[must_use]
    pub const fn concrete_rgb(self) -> [u8; 3] {
        self.concrete_rgb
    }

    #[must_use]
    pub const fn oklch_lightness(self) -> f64 {
        self.oklch_lightness
    }
}

/// The resolved background, black, and white observations for one work palette.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ResolvedPaletteContext {
    background: ResolvedPaletteColor,
    black: ResolvedPaletteColor,
    white: ResolvedPaletteColor,
}

impl ResolvedPaletteContext {
    #[must_use]
    pub const fn new(
        background: ResolvedPaletteColor,
        black: ResolvedPaletteColor,
        white: ResolvedPaletteColor,
    ) -> Self {
        Self {
            background,
            black,
            white,
        }
    }

    #[must_use]
    pub const fn background(self) -> ResolvedPaletteColor {
        self.background
    }

    #[must_use]
    pub const fn black(self) -> ResolvedPaletteColor {
        self.black
    }

    #[must_use]
    pub const fn white(self) -> ResolvedPaletteColor {
        self.white
    }
}
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
    Connected,
});
string_enum!(RelationGap {
    Narrow,
    Medium,
    Wide,
});
string_enum!(ConnectedPositionAuthority {
    NamedMovable,
    NumericFixed,
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
    "0.2.0".to_owned()
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

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Canvas {
    Id(String),
    Spec(CanvasSpec),
}

impl<'de> Deserialize<'de> for Canvas {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct CanvasVisitor;

        impl<'de> Visitor<'de> for CanvasVisitor {
            type Value = Canvas;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a canvas aspect string or canvas specification")
            }

            fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                Ok(Canvas::Id(value.to_owned()))
            }

            fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                Ok(Canvas::Id(value))
            }

            fn visit_map<A>(self, map: A) -> Result<Self::Value, A::Error>
            where
                A: MapAccess<'de>,
            {
                // Serde's derived untagged enum buffers the map before choosing
                // a variant. That buffer cannot carry the i128 seed domain, so
                // a valid ground seed made the whole Canvas look invalid.
                CanvasSpec::deserialize(MapAccessDeserializer::new(map)).map(Canvas::Spec)
            }
        }

        deserializer.deserialize_any(CanvasVisitor)
    }
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_instruction_index: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub position_authority: Option<ConnectedPositionAuthority>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub touching_constraints: Option<TouchingConstraints>,
}

/// Authoritative explicit facts; omitted normal geometry remains adjustable.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct TouchingConstraints {
    pub dimensions_fixed: bool,
    pub direction_fixed: bool,
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub arc_form: Option<ArcForm>,
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
    #[serde(default, skip_serializing_if = "SurfaceIntensity::is_normal")]
    pub surface_intensity: SurfaceIntensity,
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

impl Score {
    /// Reject descriptors introduced after the declared Score edition or with
    /// geometry that belongs to an open arc.
    pub fn validate_schema_edition(&self) -> Result<(), &'static str> {
        for instruction in &self.instructions {
            if instruction.surface_intensity != SurfaceIntensity::Normal {
                let closed = matches!(
                    instruction.primitive,
                    Primitive::Circle
                        | Primitive::Ellipse
                        | Primitive::Square
                        | Primitive::Triangle
                        | Primitive::Polygon
                        | Primitive::Cloudform
                        | Primitive::Point
                ) || instruction.arc_form == Some(ArcForm::Crescent);
                let solid = instruction.surface.as_ref().is_none_or(|surface| {
                    matches!(
                        surface.texture,
                        SurfaceTexture::None | SurfaceTexture::Solid
                    )
                });
                let filled = instruction.filled
                    || instruction
                        .surface
                        .as_ref()
                        .is_some_and(|surface| surface.texture == SurfaceTexture::Solid);
                if !closed || !solid || !filled {
                    return Err("surface_intensity requires a closed solid fill");
                }
            }
            if instruction.arc_form != Some(ArcForm::Crescent) {
                continue;
            }
            if self.version != "0.2.0" {
                return Err("arc_form requires Score version 0.2.0");
            }
            if instruction.primitive != Primitive::Arc {
                return Err("arc_form=crescent requires primitive=arc");
            }
            if !instruction.filled {
                return Err("arc_form=crescent requires filled=true");
            }
            if instruction.center.is_none() && instruction.at.is_none() {
                return Err("arc_form=crescent requires center or at");
            }
            if !matches!(instruction.size, Some(size) if size.x > 0.0 && size.y > 0.0) {
                return Err("arc_form=crescent requires a positive size");
            }
            if instruction.radius.is_some()
                || instruction.position.is_some()
                || instruction.angle_start.is_some()
                || instruction.angle_end.is_some()
            {
                return Err("arc_form=crescent cannot carry open-arc geometry");
            }
            if matches!(instruction.surface, Some(ref surface) if surface.texture != SurfaceTexture::None)
            {
                return Err("arc_form=crescent uses filled instead of a surface texture");
            }
        }
        Ok(())
    }
}
