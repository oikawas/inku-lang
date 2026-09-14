//! Host-neutral Score value types.
//!
//! Python remains the schema authority. These types receive only a canonical,
//! already validated Score and resolved host data; they are not a second tool
//! schema and deliberately contain no Python or server-registry concepts.

use std::{collections::HashSet, fmt};

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

/// Area of the shared closed cubic contour divided by its reference bbox area.
/// Integrate x dy - y dx analytically, without another sampled approximation.
#[must_use]
pub fn crescent_reference_area_ratio() -> f64 {
    let coefficients = |p: [f64; 4]| {
        [
            p[0],
            3.0 * (p[1] - p[0]),
            3.0 * (p[2] - 2.0 * p[1] + p[0]),
            p[3] - 3.0 * p[2] + 3.0 * p[1] - p[0],
        ]
    };
    let mut twice_area = 0.0;
    for cubic in CRESCENT_REFERENCE_CUBICS {
        let x = coefficients(cubic.map(|p| p.x));
        let y = coefficients(cubic.map(|p| p.y));
        for i in 0..4 {
            for j in 1..4 {
                twice_area += (x[i] * y[j] - y[i] * x[j]) * j as f64 / (i + j) as f64;
            }
        }
    }
    twice_area.abs() / (2.0 * CRESCENT_REFERENCE_WIDTH * CRESCENT_REFERENCE_HEIGHT)
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

/// Observations from one work palette, including the legacy three-color view.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ResolvedPaletteContext {
    background: ResolvedPaletteColor,
    black: ResolvedPaletteColor,
    white: ResolvedPaletteColor,
    observations: Option<[ResolvedPaletteColor; 9]>,
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
            observations: None,
        }
    }

    /// Retain the nine abstract-color observations from the same work assignment.
    #[must_use]
    pub const fn with_observations(mut self, observations: [ResolvedPaletteColor; 9]) -> Self {
        self.observations = Some(observations);
        self
    }

    #[must_use]
    pub const fn observations(&self) -> Option<&[ResolvedPaletteColor; 9]> {
        self.observations.as_ref()
    }

    /// Change only the selected role; never synthesize an unobserved color.
    #[must_use]
    pub fn select_background(mut self, color: Color) -> Option<Self> {
        self.background = [self.background, self.black, self.white]
            .into_iter()
            .chain(self.observations.into_iter().flatten())
            .find(|observation| observation.abstract_color() == color)?;
        Some(self)
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
string_enum!(InkSpread { Bleed });
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
    "0.9.0".to_owned()
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

/// Compact identity of the source object that owns one saved template.
///
/// Macro source text and expansion paths stay in the compiler. The two stable
/// ordinals are sufficient to distinguish emitted object templates in a Score.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScoreSourceOwner {
    SourceInstruction {
        instruction_index: usize,
    },
    MacroEmit {
        source_instruction_index: usize,
        invocation_ordinal: u64,
        generated_ordinal: u64,
    },
}

/// Why the compiler selected the saved logical instance count.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum CountOrigin {
    Explicit,
    OmittedDefault,
    /// One stored template instance; the owning group retains the author count.
    TemplateSingle,
    OmittedRegionExtent {
        reference_extent: f64,
    },
    OmittedBalancedGroup {
        reference_extents: Vec<f64>,
        explicit_counts: Vec<Option<u32>>,
    },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InstanceOrdinalScheme {
    SourceMemberThenInstanceV1,
}

/// Resolved placement math retained without materializing performance positions.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ResolvedPlacementRecipe {
    Place,
    HorizontalLine {
        cell_width: f64,
    },
    VerticalLine {
        cell_height: f64,
    },
    DiagonalLine {
        step: Point,
    },
    Grid {
        columns: u64,
        rows: u64,
        filled_count: u64,
        cell_width: f64,
        cell_height: f64,
        centroid: Point,
        translate_to_numeric_anchor: bool,
    },
    ScatterUniformWithCentroidTranslation,
}

/// Placement authority retained independently from sampled performance points.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ResolvedPlacementAnchor {
    Numeric {
        point: Point,
    },
    GeneratedNumeric {
        point: Point,
    },
    Named {
        region: [f64; 4],
    },
    /// The enclosing placement or fill group owns the actual target.
    EnclosingGroup,
}

/// Score 0.10 symbolic contract for one standalone arrangement.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ResolvedArrangement {
    pub owner: ScoreSourceOwner,
    pub first_instance_ordinal: u64,
    pub count_origin: CountOrigin,
    /// Physical domain in canvas-short-edge units.
    pub domain: Point,
    pub anchor: ResolvedPlacementAnchor,
    pub recipe: ResolvedPlacementRecipe,
    pub ordinal_scheme: InstanceOrdinalScheme,
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolved: Option<ResolvedArrangement>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AtRegion {
    pub region: [f64; 4],
}

/// A non-drawing explicit point that Relations may target.
///
/// Exactly one placement authority is required: `position` retains a numeric
/// point while `at` retains a named region for deterministic performance-time
/// resolution.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AnchorPoint {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub position: Option<Point>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub at: Option<AtRegion>,
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
    pub target_anchor_index: Option<usize>,
    /// Normalized position on a connected target Line's performed centerline.
    ///
    /// This is valid only with `Connected` and `target_instruction_index`.
    /// Zero is the Line start and one is the Line end.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_path_position: Option<f64>,
    /// An explicit endpoint on a connected target Line or Arc.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_endpoint: Option<Endpoint>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub position_authority: Option<ConnectedPositionAuthority>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub touching_constraints: Option<TouchingConstraints>,
}

string_enum!(Endpoint { Start, End });

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
    /// Irregular outward ink spread around the performed mark boundary.
    ///
    /// This is independent from contour variation and surface texture.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ink_spread: Option<InkSpread>,
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

/// One postorder Macro transform over a contiguous Score instruction range.
///
/// The renderer rotates the range about its pre-transform bounding-box center.
/// `fixed_position_indices` names the absolute Score members that cannot move
/// when a connected member would otherwise translate this group.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TransformGroup {
    pub start: usize,
    pub end: usize,
    pub rotation_degrees: f64,
    #[serde(
        default = "default_transform_scale",
        skip_serializing_if = "is_identity_scale"
    )]
    pub scale_x: f64,
    #[serde(
        default = "default_transform_scale",
        skip_serializing_if = "is_identity_scale"
    )]
    pub scale_y: f64,
    #[serde(default, skip_serializing_if = "is_zero_translation")]
    pub translate_x: f64,
    #[serde(default, skip_serializing_if = "is_zero_translation")]
    pub translate_y: f64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub fixed_position_indices: Vec<usize>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub anchor_indices: Vec<usize>,
}

/// Whether `outer` lexically contains `inner` for postorder transform validation.
///
/// Empty instruction ranges are only meaningful for Anchor-only groups. Two such
/// groups are siblings unless the outer group explicitly lists every inner
/// anchor; their empty instruction boundary does not locate them in a parent.
pub fn transform_group_contains(outer: &TransformGroup, inner: &TransformGroup) -> bool {
    let range_contains =
        inner.start == inner.end || (outer.start <= inner.start && inner.end <= outer.end);
    let anchors_contained = inner
        .anchor_indices
        .iter()
        .all(|index| outer.anchor_indices.contains(index));
    range_contains && anchors_contained
}

fn transform_groups_have_drawable_overlap(left: &TransformGroup, right: &TransformGroup) -> bool {
    left.start < left.end
        && right.start < right.end
        && left.start < right.end
        && right.start < left.end
}

const fn default_transform_scale() -> f64 {
    1.0
}

fn is_identity_scale(value: &f64) -> bool {
    *value == 1.0
}

fn is_zero_translation(value: &f64) -> bool {
    *value == 0.0
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GroupLayout {
    Overlap,
    HorizontalSourceOrder,
    Scatter,
    Tile,
}

/// One source head's complete body, placed without changing its internal geometry.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PlacementMember {
    pub start: usize,
    pub end: usize,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub anchor_indices: Vec<usize>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub transform_group_indices: Vec<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub symbolic: Option<SymbolicMember>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SymbolicMemberKind {
    Primitive,
    Macro,
}

/// Logical instances of one complete primitive or Macro body template.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SymbolicMember {
    pub owner: ScoreSourceOwner,
    pub kind: SymbolicMemberKind,
    pub member_ordinal: u64,
    pub first_instance_ordinal: u64,
    pub instance_count: u64,
    pub count_origin: CountOrigin,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PlacementGroupOwner {
    CoordinatedGroup { group_index: usize },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ResolvedPlacementGroup {
    pub owner: PlacementGroupOwner,
    pub logical_count: u64,
    /// Physical domain in canvas-short-edge units.
    pub domain: Point,
    pub anchor: ResolvedPlacementAnchor,
    pub recipe: ResolvedPlacementRecipe,
    pub ordinal_scheme: InstanceOrdinalScheme,
}

/// Repeats one complete Macro body without replacing arrangements inside it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RepetitionGroup {
    pub member: PlacementMember,
    pub ordinal_scheme: InstanceOrdinalScheme,
}

/// One coordinated arrangement and named placement, distinct from affine transforms.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PlacementGroup {
    pub start: usize,
    pub end: usize,
    pub layout: GroupLayout,
    pub at: AtRegion,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub members: Vec<PlacementMember>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolved: Option<ResolvedPlacementGroup>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum FillGroupOwner {
    CoordinatedGroup { group_index: usize },
    Instruction { source_instruction_index: usize },
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ScoreSourceSite {
    pub region_index: usize,
    pub clause_index: usize,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum FillTargetOwner {
    OmittedCanvas,
    ExplicitCanvas {
        source: ScoreSourceSite,
    },
    Named {
        category: String,
        id: String,
    },
    InlineShape {
        source_instruction_index: usize,
        source: ScoreSourceSite,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ResolvedShapeDimensions {
    Bbox { width: f64, height: f64 },
    RegularTriangle { side: f64 },
    Polygon { radius: f64, sides: u8 },
    Line { length: f64 },
    Circle { radius: f64 },
    Arc { chord: f64, sagitta: f64 },
    Point { radius: f64 },
    CenteredSize { width: f64, height: f64 },
    Square { side: f64 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum FillTargetAnchor {
    Numeric { point: Point },
    GeneratedNumeric { point: Point },
    Named { region: [f64; 4] },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum FillTargetGeometry {
    Rectangle {
        bounds: [f64; 4],
    },
    Shape {
        primitive: Primitive,
        dimensions: ResolvedShapeDimensions,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        arc_form: Option<ArcForm>,
        anchor: FillTargetAnchor,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        rotation_degrees: Option<f64>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        contour_variation: Option<Variation>,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FillTarget {
    pub owner: FillTargetOwner,
    pub geometry: FillTargetGeometry,
    /// Stable geometry reference area in canvas-short-edge units squared.
    pub reference_area: f64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FillRecipe {
    UniformInRegion,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FillBoundary {
    ClipToTarget,
}

/// Score 0.10 compact fill: templates and counts, never sampled positions.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FillGroup {
    pub start: usize,
    pub end: usize,
    pub owner: FillGroupOwner,
    pub logical_count: u64,
    pub recipe: FillRecipe,
    pub target: FillTarget,
    pub boundary: FillBoundary,
    pub ordinal_scheme: InstanceOrdinalScheme,
    pub members: Vec<PlacementMember>,
}

/// Resource authorities captured with a Score for deterministic replay.
/// Demand is deliberately absent and must be recomputed from the Score.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ScoreResourcePolicy {
    pub accounting_id: String,
    pub hard_policy: crate::resource::HardResourcePolicy,
    pub operational_budget: crate::resource::OperationalResourceBudget,
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
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub anchors: Vec<AnchorPoint>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub transform_groups: Vec<TransformGroup>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub placement_groups: Vec<PlacementGroup>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub repetition_groups: Vec<RepetitionGroup>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub fill_groups: Vec<FillGroup>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resource_policy: Option<ScoreResourcePolicy>,
}

impl Score {
    fn validate_count_origin(origin: &CountOrigin) -> Result<(), &'static str> {
        match origin {
            CountOrigin::Explicit | CountOrigin::OmittedDefault | CountOrigin::TemplateSingle => {
                Ok(())
            }
            CountOrigin::OmittedRegionExtent { reference_extent }
                if reference_extent.is_finite() && *reference_extent > 0.0 =>
            {
                Ok(())
            }
            CountOrigin::OmittedBalancedGroup {
                reference_extents,
                explicit_counts,
            } if !reference_extents.is_empty()
                && reference_extents.len() == explicit_counts.len()
                && reference_extents
                    .iter()
                    .all(|extent| extent.is_finite() && *extent > 0.0)
                && explicit_counts
                    .iter()
                    .all(|count| count.is_none_or(|count| count > 0)) =>
            {
                Ok(())
            }
            _ => Err("count origin requires finite positive and aligned inputs"),
        }
    }

    fn validate_resolved_recipe(
        recipe: &ResolvedPlacementRecipe,
        logical_count: u64,
    ) -> Result<(), &'static str> {
        let positive = |value: f64| value.is_finite() && value > 0.0;
        match recipe {
            ResolvedPlacementRecipe::Place
            | ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation => Ok(()),
            ResolvedPlacementRecipe::HorizontalLine { cell_width } if positive(*cell_width) => {
                Ok(())
            }
            ResolvedPlacementRecipe::VerticalLine { cell_height } if positive(*cell_height) => {
                Ok(())
            }
            ResolvedPlacementRecipe::DiagonalLine { step }
                if step.x.is_finite() && step.y.is_finite() && (step.x != 0.0 || step.y != 0.0) =>
            {
                Ok(())
            }
            ResolvedPlacementRecipe::Grid {
                columns,
                rows,
                filled_count,
                cell_width,
                cell_height,
                centroid,
                ..
            } if *columns > 0
                && *rows > 0
                && *filled_count == logical_count
                && columns
                    .checked_mul(*rows)
                    .is_some_and(|capacity| capacity >= *filled_count)
                && positive(*cell_width)
                && positive(*cell_height)
                && centroid.x.is_finite()
                && centroid.y.is_finite() =>
            {
                Ok(())
            }
            _ => Err("resolved placement recipe is inconsistent or non-finite"),
        }
    }

    fn validate_symbolic_member(
        member: &PlacementMember,
        expected_member_ordinal: u64,
        expected_first_instance_ordinal: u64,
    ) -> Result<u64, &'static str> {
        let Some(symbolic) = &member.symbolic else {
            return Err("Score 0.10 symbolic member metadata is required");
        };
        if symbolic.member_ordinal != expected_member_ordinal
            || symbolic.first_instance_ordinal != expected_first_instance_ordinal
            || symbolic.instance_count == 0
            || matches!(symbolic.count_origin, CountOrigin::TemplateSingle)
        {
            return Err(
                "symbolic member ordinals and count must form a nonempty source-order prefix",
            );
        }
        Self::validate_count_origin(&symbolic.count_origin)?;
        expected_first_instance_ordinal
            .checked_add(symbolic.instance_count)
            .ok_or("symbolic member instance ordinal overflows")
    }

    fn validate_placement_anchor(anchor: &ResolvedPlacementAnchor) -> Result<(), &'static str> {
        match anchor {
            ResolvedPlacementAnchor::Numeric { point }
            | ResolvedPlacementAnchor::GeneratedNumeric { point }
                if point.x.is_finite() && point.y.is_finite() =>
            {
                Ok(())
            }
            ResolvedPlacementAnchor::Named { region }
                if region.iter().all(|value| value.is_finite())
                    && region[0] <= region[2]
                    && region[1] <= region[3] =>
            {
                Ok(())
            }
            ResolvedPlacementAnchor::EnclosingGroup => Ok(()),
            _ => Err("resolved placement anchor must be finite and ordered"),
        }
    }

    fn validate_fill_target(target: &FillTarget) -> Result<(), &'static str> {
        if !target.reference_area.is_finite() || target.reference_area <= 0.0 {
            return Err("fill target reference_area must be finite and positive");
        }
        let ordered_region = |region: [f64; 4]| {
            region.into_iter().all(f64::is_finite)
                && region[0] <= region[2]
                && region[1] <= region[3]
        };
        match &target.geometry {
            FillTargetGeometry::Rectangle { bounds }
                if ordered_region(*bounds) && bounds[0] < bounds[2] && bounds[1] < bounds[3] =>
            {
                Ok(())
            }
            FillTargetGeometry::Shape {
                primitive,
                dimensions,
                arc_form,
                anchor,
                rotation_degrees,
                ..
            } => {
                let closed = matches!(
                    primitive,
                    Primitive::Circle
                        | Primitive::Ellipse
                        | Primitive::Square
                        | Primitive::Triangle
                        | Primitive::Polygon
                        | Primitive::Cloudform
                ) || (*primitive == Primitive::Arc
                    && *arc_form == Some(ArcForm::Crescent));
                if !closed || rotation_degrees.is_some_and(|value| !value.is_finite()) {
                    return Err("fill target shape requires closed finite geometry");
                }
                let positive = |value: f64| value.is_finite() && value > 0.0;
                let dimensions_valid = match dimensions {
                    ResolvedShapeDimensions::Bbox { width, height }
                    | ResolvedShapeDimensions::CenteredSize { width, height } => {
                        positive(*width) && positive(*height)
                    }
                    ResolvedShapeDimensions::RegularTriangle { side }
                    | ResolvedShapeDimensions::Square { side } => positive(*side),
                    ResolvedShapeDimensions::Polygon { radius, sides } => {
                        positive(*radius) && (5..=8).contains(sides)
                    }
                    ResolvedShapeDimensions::Circle { radius }
                    | ResolvedShapeDimensions::Point { radius } => positive(*radius),
                    ResolvedShapeDimensions::Line { length } => positive(*length),
                    ResolvedShapeDimensions::Arc { chord, sagitta } => {
                        positive(*chord) && positive(*sagitta)
                    }
                };
                let anchor_valid = match anchor {
                    FillTargetAnchor::Numeric { point }
                    | FillTargetAnchor::GeneratedNumeric { point } => {
                        point.x.is_finite() && point.y.is_finite()
                    }
                    FillTargetAnchor::Named { region } => ordered_region(*region),
                };
                if !dimensions_valid || !anchor_valid {
                    return Err("fill target dimensions and anchor must be finite and positive");
                }
                Ok(())
            }
            _ => Err("fill target rectangle must have finite positive area"),
        }
    }

    fn source_owner_index(owner: &ScoreSourceOwner) -> usize {
        match owner {
            ScoreSourceOwner::SourceInstruction { instruction_index } => *instruction_index,
            ScoreSourceOwner::MacroEmit {
                source_instruction_index,
                ..
            } => *source_instruction_index,
        }
    }

    fn synthetic_fill_source(&self, group: &FillGroup) -> Option<usize> {
        let FillGroupOwner::Instruction {
            source_instruction_index,
        } = group.owner
        else {
            return None;
        };
        let [member] = group.members.as_slice() else {
            return None;
        };
        let symbolic = member.symbolic.as_ref()?;
        let instruction_owner = &self
            .instructions
            .get(member.start)?
            .arrangement
            .as_ref()?
            .resolved
            .as_ref()?
            .owner;
        (symbolic.kind == SymbolicMemberKind::Primitive
            && member.start == group.start
            && member.end == group.end
            && group.end - group.start == 1
            && member.anchor_indices.is_empty()
            && member.transform_group_indices.is_empty()
            && Self::source_owner_index(&symbolic.owner) == source_instruction_index
            && instruction_owner == &symbolic.owner)
            .then_some(source_instruction_index)
    }

    fn fill_parent_contains_source(
        parent: &FillGroup,
        child: &FillGroup,
        child_source: usize,
    ) -> bool {
        let owner_allows_nesting = match parent.owner {
            FillGroupOwner::Instruction {
                source_instruction_index,
            } => {
                source_instruction_index == child_source
                    && matches!(
                        parent.members.as_slice(),
                        [PlacementMember {
                            symbolic: Some(SymbolicMember {
                                kind: SymbolicMemberKind::Macro,
                                ..
                            }),
                            ..
                        }]
                    )
            }
            FillGroupOwner::CoordinatedGroup { .. } => true,
        };
        owner_allows_nesting
            && parent.members.iter().any(|member| {
                member.start <= child.start
                    && child.end <= member.end
                    && member.symbolic.as_ref().is_some_and(|symbolic| {
                        Self::source_owner_index(&symbolic.owner) == child_source
                    })
            })
    }

    fn validate_compact_score_0_10(&self) -> Result<(), &'static str> {
        let is_compact_edition = matches!(self.version.as_str(), "0.10.0" | "0.11.0" | "0.12.0");
        let has_0_10_fields = !self.fill_groups.is_empty()
            || !self.repetition_groups.is_empty()
            || self.resource_policy.is_some()
            || self.placement_groups.iter().any(|group| {
                group.resolved.is_some()
                    || group.members.iter().any(|member| member.symbolic.is_some())
            })
            || self.instructions.iter().any(|instruction| {
                instruction
                    .arrangement
                    .as_ref()
                    .is_some_and(|arrangement| arrangement.resolved.is_some())
            });
        if has_0_10_fields && !is_compact_edition {
            return Err("compact symbolic fields require Score version 0.10.0");
        }
        let is_compact = self.version == "0.10.0" || has_0_10_fields;
        if !is_compact {
            return Ok(());
        }

        let Some(policy) = &self.resource_policy else {
            return Err("Score 0.10 requires a resource_policy snapshot");
        };
        if policy.accounting_id != crate::resource::RESOURCE_ACCOUNTING_ID
            || policy.hard_policy.identity.is_empty()
        {
            return Err("Score 0.10 resource policy identity is invalid");
        }

        for instruction in &self.instructions {
            let Some(arrangement) = instruction.arrangement.as_ref() else {
                return Err("Score 0.10 instruction templates require an arrangement");
            };
            let Some(resolved) = arrangement.resolved.as_ref() else {
                return Err("Score 0.10 arrangements require resolved metadata");
            };
            if arrangement.count == 0 || arrangement.group_size == 0 {
                return Err("Score 0.10 arrangements require nonzero count and group_size");
            }
            if resolved.first_instance_ordinal != 0 {
                return Err("standalone arrangement instance ordinals must start at zero");
            }
            if !resolved.domain.x.is_finite()
                || !resolved.domain.y.is_finite()
                || resolved.domain.x <= 0.0
                || resolved.domain.y <= 0.0
            {
                return Err("resolved arrangement domain must be finite and positive");
            }
            Self::validate_count_origin(&resolved.count_origin)?;
            Self::validate_placement_anchor(&resolved.anchor)?;
            if matches!(resolved.count_origin, CountOrigin::TemplateSingle)
                != (arrangement.count == 1
                    && matches!(resolved.anchor, ResolvedPlacementAnchor::EnclosingGroup))
            {
                return Err("template_single requires one enclosing-group-owned template");
            }
            Self::validate_resolved_recipe(&resolved.recipe, u64::from(arrangement.count))?;
        }

        let mut repetition_end = 0;
        for group in &self.repetition_groups {
            let member = &group.member;
            if member.start < repetition_end
                || member.start > member.end
                || (member.start == member.end && member.anchor_indices.is_empty())
                || member.end > self.instructions.len()
            {
                return Err("repetition groups must be nonempty, disjoint and in source order");
            }
            let Some(symbolic) = &member.symbolic else {
                return Err("repetition group requires symbolic member metadata");
            };
            if symbolic.kind != SymbolicMemberKind::Macro {
                return Err("repetition group must own one complete Macro body");
            }
            Self::validate_symbolic_member(member, 0, 0)?;
            repetition_end = member.end;
        }

        let mut previous_fill_start = 0;
        let mut fill_ancestors = Vec::<usize>::new();
        for (group_index, group) in self.fill_groups.iter().enumerate() {
            if (group_index > 0 && group.start < previous_fill_start)
                || group.start >= group.end
                || group.end > self.instructions.len()
                || group.members.is_empty()
            {
                return Err("fill groups must be nonempty and in source order");
            }
            while fill_ancestors
                .last()
                .is_some_and(|&parent_index| group.start >= self.fill_groups[parent_index].end)
            {
                fill_ancestors.pop();
            }
            if let Some(&parent_index) = fill_ancestors.last() {
                let parent = &self.fill_groups[parent_index];
                let Some(child_source) = self.synthetic_fill_source(group) else {
                    return Err(
                        "nested fill must be a singleton primitive descriptor inside its owner",
                    );
                };
                if group.end > parent.end
                    || !Self::fill_parent_contains_source(parent, group, child_source)
                {
                    return Err("fill group ranges cannot cross or cross source ownership");
                }
            }
            let mut member_end = group.start;
            let mut first_instance = 0;
            for (ordinal, member) in group.members.iter().enumerate() {
                if member.start != member_end
                    || member.start > member.end
                    || member.end > group.end
                    || (member.start == member.end && member.anchor_indices.is_empty())
                {
                    return Err("fill members must partition the group in source order");
                }
                first_instance = Self::validate_symbolic_member(
                    member,
                    u64::try_from(ordinal).map_err(|_| "fill member ordinal overflows")?,
                    first_instance,
                )?;
                member_end = member.end;
            }
            if member_end != group.end || first_instance != group.logical_count {
                return Err("fill members must cover the group and its logical count");
            }
            Self::validate_fill_target(&group.target)?;
            previous_fill_start = group.start;
            fill_ancestors.push(group_index);
        }
        Ok(())
    }

    pub fn validate_placement_groups(&self) -> Result<(), &'static str> {
        let is_compact = self.version == "0.10.0"
            || (matches!(self.version.as_str(), "0.11.0" | "0.12.0")
                && self.resource_policy.is_some());
        let mut previous_end = 0;
        for group in &self.placement_groups {
            match group.layout {
                GroupLayout::Overlap | GroupLayout::HorizontalSourceOrder
                    if !matches!(
                        self.version.as_str(),
                        "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0"
                    ) =>
                {
                    return Err("placement_groups requires Score version 0.7.0");
                }
                GroupLayout::Scatter | GroupLayout::Tile
                    if !matches!(
                        self.version.as_str(),
                        "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0"
                    ) =>
                {
                    return Err("scatter and tile placement_groups require Score version 0.8.0");
                }
                _ => {}
            }
            if group.start < previous_end
                || group.start > group.end
                || (group.start == group.end && group.members.is_empty())
                || group.end > self.instructions.len()
            {
                return Err(
                    "placement group ranges must be nonempty, disjoint and in source order",
                );
            }
            previous_end = group.end;
            if !group.members.is_empty()
                && !matches!(
                    self.version.as_str(),
                    "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0"
                )
            {
                return Err("placement members require Score version 0.9.0");
            }
            if is_compact {
                let Some(resolved) = &group.resolved else {
                    return Err("Score 0.10 placement groups require resolved metadata");
                };
                if group.members.is_empty()
                    || !resolved.domain.x.is_finite()
                    || !resolved.domain.y.is_finite()
                    || resolved.domain.x <= 0.0
                    || resolved.domain.y <= 0.0
                {
                    return Err("resolved placement group requires members and a positive domain");
                }
                Self::validate_resolved_recipe(&resolved.recipe, resolved.logical_count)?;
                Self::validate_placement_anchor(&resolved.anchor)?;
            }
            let mut member_end = group.start;
            let mut anchors = HashSet::new();
            let mut owned_transforms = HashSet::new();
            let mut first_instance = 0;
            for (ordinal, member) in group.members.iter().enumerate() {
                if member.start != member_end
                    || member.start > member.end
                    || member.end > group.end
                    || (member.start == member.end && member.anchor_indices.is_empty())
                {
                    return Err("placement members must partition the group in source order");
                }
                if is_compact {
                    first_instance = Self::validate_symbolic_member(
                        member,
                        u64::try_from(ordinal).map_err(|_| "placement member ordinal overflows")?,
                        first_instance,
                    )?;
                }
                member_end = member.end;
                for &anchor in &member.anchor_indices {
                    if anchor >= self.anchors.len() || !anchors.insert(anchor) {
                        return Err("placement member anchors must be valid and unique");
                    }
                }
                for &index in &member.transform_group_indices {
                    let Some(affine) = self.transform_groups.get(index) else {
                        return Err("placement member transform index exceeds transform groups");
                    };
                    if !owned_transforms.insert(index)
                        || affine.start < member.start
                        || affine.end > member.end
                        || !affine
                            .anchor_indices
                            .iter()
                            .all(|anchor| member.anchor_indices.contains(anchor))
                    {
                        return Err(
                            "placement member transforms must be unique and contained by their owner",
                        );
                    }
                }
            }
            if !group.members.is_empty() && member_end != group.end {
                return Err("placement members must cover the group");
            }
            if let Some(resolved) = &group.resolved
                && first_instance != resolved.logical_count
            {
                return Err("placement member counts must equal the resolved logical count");
            }
            for prior in &self.placement_groups {
                if std::ptr::eq(prior, group) {
                    break;
                }
                if prior
                    .members
                    .iter()
                    .flat_map(|member| &member.anchor_indices)
                    .any(|anchor| anchors.contains(anchor))
                {
                    return Err("placement groups cannot share anchors");
                }
                if prior
                    .members
                    .iter()
                    .flat_map(|member| &member.transform_group_indices)
                    .any(|index| owned_transforms.contains(index))
                {
                    return Err("placement groups cannot share owned transforms");
                }
            }
            let [x0, y0, x1, y1] = group.at.region;
            if ![x0, y0, x1, y1].into_iter().all(f64::is_finite) || x0 > x1 || y0 > y1 {
                return Err("placement group at region must be finite and ordered");
            }
            if self.instructions[group.start..group.end]
                .iter()
                .any(|instruction| {
                    instruction
                        .arrangement
                        .as_ref()
                        .is_some_and(|arrangement| arrangement.resolved.is_none())
                })
            {
                return Err("placement group members cannot carry arrangements");
            }
            for (affine_index, affine) in self.transform_groups.iter().enumerate() {
                let drawable_overlap = group.start < affine.end && affine.start < group.end;
                let anchor_overlap = affine
                    .anchor_indices
                    .iter()
                    .any(|anchor| anchors.contains(anchor));
                let outer = affine.start <= group.start
                    && group.end <= affine.end
                    && anchors
                        .iter()
                        .all(|anchor| affine.anchor_indices.contains(anchor));
                let inner = owned_transforms.contains(&affine_index);
                if (drawable_overlap || anchor_overlap) && !outer && !inner {
                    return Err(
                        "an overlapping affine group must contain the placement group or fit one member",
                    );
                }
            }
        }
        Ok(())
    }

    /// Reject descriptors introduced after the declared Score edition or with
    /// geometry that belongs to an open arc.
    pub fn validate_schema_edition(&self) -> Result<(), &'static str> {
        self.validate_compact_score_0_10()?;
        if !self.anchors.is_empty()
            && !matches!(
                self.version.as_str(),
                "0.6.0" | "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0"
            )
        {
            return Err("anchors requires Score version 0.6.0");
        }
        for anchor in &self.anchors {
            if anchor.position.is_some() == anchor.at.is_some() {
                return Err("anchors require exactly one position or at");
            }
            if let Some(position) = anchor.position
                && (!position.x.is_finite()
                    || !position.y.is_finite()
                    || !(0.0..=1.0).contains(&position.x)
                    || !(0.0..=1.0).contains(&position.y))
            {
                return Err("anchor position must be finite and within the unit canvas");
            }
            if let Some(at) = &anchor.at {
                let [x0, y0, x1, y1] = at.region;
                if ![x0, y0, x1, y1].into_iter().all(f64::is_finite) || x0 > x1 || y0 > y1 {
                    return Err("anchor at region must be finite and ordered");
                }
            }
        }
        self.validate_transform_groups()?;
        for instruction in &self.instructions {
            if let Some(relation) = &instruction.relation {
                if relation.target_instruction_index.is_some()
                    && relation.target_anchor_index.is_some()
                {
                    return Err("relation target instruction and anchor are exclusive");
                }
                if let Some(position) = relation.target_path_position {
                    if !matches!(self.version.as_str(), "0.11.0" | "0.12.0") {
                        return Err("relation target_path_position requires Score version 0.11.0");
                    }
                    if relation.kind != RelationType::Connected
                        || relation.target_instruction_index.is_none()
                        || relation.target_anchor_index.is_some()
                    {
                        return Err(
                            "relation target_path_position requires a connected instruction target",
                        );
                    }
                    if !position.is_finite() || !(0.0..=1.0).contains(&position) {
                        return Err(
                            "relation target_path_position must be finite and within 0 to 1",
                        );
                    }
                }
                if relation.target_path_position.is_some() && relation.target_endpoint.is_some() {
                    return Err("relation target path position and endpoint are exclusive");
                }
                if relation.target_endpoint.is_some() {
                    if self.version != "0.12.0" {
                        return Err("relation target_endpoint requires Score version 0.12.0");
                    }
                    if relation.kind != RelationType::Connected
                        || relation.target_instruction_index.is_none()
                        || relation.target_anchor_index.is_some()
                    {
                        return Err(
                            "relation target_endpoint requires a connected instruction target",
                        );
                    }
                }
                if let Some(anchor_index) = relation.target_anchor_index {
                    if !matches!(
                        self.version.as_str(),
                        "0.6.0" | "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0"
                    ) {
                        return Err("relation target_anchor_index requires Score version 0.6.0");
                    }
                    if anchor_index >= self.anchors.len() {
                        return Err("relation target_anchor_index exceeds anchors");
                    }
                }
            }
            if instruction.surface_intensity != SurfaceIntensity::Normal {
                if self.version != "0.3.0"
                    && self.version != "0.4.0"
                    && self.version != "0.5.0"
                    && self.version != "0.6.0"
                    && self.version != "0.7.0"
                    && self.version != "0.8.0"
                    && self.version != "0.9.0"
                    && self.version != "0.10.0"
                    && self.version != "0.11.0"
                    && self.version != "0.12.0"
                {
                    return Err("surface_intensity requires Score version 0.3.0");
                }
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
            if instruction.ink_spread.is_some() && self.version != "0.12.0" {
                return Err("ink_spread requires Score version 0.12.0");
            }
            if instruction.arc_form != Some(ArcForm::Crescent) {
                continue;
            }
            if self.version != "0.2.0"
                && self.version != "0.3.0"
                && self.version != "0.4.0"
                && self.version != "0.5.0"
                && self.version != "0.6.0"
                && self.version != "0.7.0"
                && self.version != "0.8.0"
                && self.version != "0.9.0"
                && self.version != "0.10.0"
                && self.version != "0.11.0"
                && self.version != "0.12.0"
            {
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

    /// Validates the structural contract shared by Score-producing hosts and
    /// the renderer before it performs any transform.
    pub fn validate_transform_groups(&self) -> Result<(), &'static str> {
        self.validate_placement_groups()?;
        if self.transform_groups.is_empty() {
            return Ok(());
        }
        if !matches!(
            self.version.as_str(),
            "0.4.0"
                | "0.5.0"
                | "0.6.0"
                | "0.7.0"
                | "0.8.0"
                | "0.9.0"
                | "0.10.0"
                | "0.11.0"
                | "0.12.0"
        ) {
            return Err("transform_groups requires Score version 0.4.0");
        }

        for (group_index, group) in self.transform_groups.iter().enumerate() {
            if group.start > group.end
                || (group.start == group.end && group.anchor_indices.is_empty())
            {
                return Err("transform group range must be nonempty unless it owns anchors");
            }
            if group.end > self.instructions.len() {
                return Err("transform group range exceeds the instruction list");
            }
            if !group.rotation_degrees.is_finite() {
                return Err("transform group rotation_degrees must be finite");
            }
            if !group.scale_x.is_finite() || !group.scale_y.is_finite() {
                return Err("transform group scale must be finite");
            }
            if !group.translate_x.is_finite() || !group.translate_y.is_finite() {
                return Err("transform group translation must be finite");
            }
            if self.version != "0.5.0"
                && self.version != "0.6.0"
                && self.version != "0.7.0"
                && self.version != "0.8.0"
                && self.version != "0.9.0"
                && self.version != "0.10.0"
                && self.version != "0.11.0"
                && self.version != "0.12.0"
                && (group.scale_x != 1.0
                    || group.scale_y != 1.0
                    || group.translate_x != 0.0
                    || group.translate_y != 0.0)
            {
                return Err("scale or translation requires Score version 0.5.0");
            }
            if self.instructions[group.start..group.end]
                .iter()
                .any(|instruction| {
                    instruction
                        .arrangement
                        .as_ref()
                        .is_some_and(|arrangement| arrangement.resolved.is_none())
                })
            {
                return Err("transform group members cannot carry arrangements");
            }

            let mut fixed_indices = HashSet::new();
            for &fixed_index in &group.fixed_position_indices {
                if fixed_index < group.start || fixed_index >= group.end {
                    return Err("transform group fixed_position_indices must be within its range");
                }
                if !fixed_indices.insert(fixed_index) {
                    return Err("transform group fixed_position_indices must be unique");
                }
            }

            let mut anchor_indices = HashSet::new();
            for &anchor_index in &group.anchor_indices {
                if anchor_index >= self.anchors.len() {
                    return Err("transform group anchor_indices exceeds anchors");
                }
                if !anchor_indices.insert(anchor_index) {
                    return Err("transform group anchor_indices must be unique");
                }
            }
            if !group.anchor_indices.is_empty()
                && !matches!(
                    self.version.as_str(),
                    "0.6.0" | "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0"
                )
            {
                return Err("transform group anchor_indices requires Score version 0.6.0");
            }

            for prior in &self.transform_groups[..group_index] {
                let current_contains_prior = transform_group_contains(group, prior);
                let prior_contains_current = transform_group_contains(prior, group);
                let anchor_overlap = prior
                    .anchor_indices
                    .iter()
                    .any(|index| anchor_indices.contains(index));
                if !transform_groups_have_drawable_overlap(group, prior) && !anchor_overlap {
                    continue;
                }
                if !current_contains_prior {
                    if prior_contains_current {
                        return Err("transform groups must be stored inner-before-outer");
                    }
                    return Err("transform group ranges cannot cross");
                }
                if !prior
                    .fixed_position_indices
                    .iter()
                    .all(|index| fixed_indices.contains(index))
                {
                    return Err(
                        "outer transform groups must include descendant fixed_position_indices",
                    );
                }
                if !prior
                    .anchor_indices
                    .iter()
                    .all(|index| anchor_indices.contains(index))
                {
                    return Err("outer transform groups must include descendant anchor_indices");
                }
            }
        }
        Ok(())
    }
}
