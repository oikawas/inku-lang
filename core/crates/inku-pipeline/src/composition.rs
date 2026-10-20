//! The composition step: what a composition reading means for each kind of
//! work-plan layer, the check that keeps only the values a canvas can show, the
//! reading used when no reading can be used, and the solver that places layers on
//! ranges of the thirds grid.
//!
//! A reading names roles (field, focal, secondary, scattered, accent), relations
//! between layers, the tension of the whole picture and the places the
//! description states. It never names a place the description does not state:
//! the solver chooses every other range from the reading and the author's
//! defaults (dynamic balance, generous empty space, left and right alike).
//!
//! Ranges are exact fractions and become floating point exactly where the solver
//! weighs them. Sums, distances and the count weight follow fixed procedures (a
//! compensated sum, an error-free hypotenuse, a table of `n^0.7`), so every host
//! gives the same answer for the same plan, reading and seed.

use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};
use std::ops::{Add, Mul, Sub};
use std::sync::OnceLock;

use inku_ddl::work_plan::{
    ComposedRange, WorkPlan, WorkPlanLayer, WorkPlanSlot, work_plan_capabilities,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

/// Beyond this many combinations of ranges the exhaustive search does not solve.
pub const MAX_COMBINATIONS: u64 = 3_000_000;

// ---------------------------------------------------------------------------
// Exact fractions and ranges

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Frac {
    n: i64,
    d: i64,
}

fn gcd(a: i64, b: i64) -> i64 {
    let (mut a, mut b) = (a.abs(), b.abs());
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a.max(1)
}

impl Frac {
    const ZERO: Self = Self { n: 0, d: 1 };
    const ONE: Self = Self { n: 1, d: 1 };

    fn new(n: i64, d: i64) -> Self {
        let g = gcd(n, d);
        let (n, d) = (n / g, d / g);
        if d < 0 {
            Self { n: -n, d: -d }
        } else {
            Self { n, d }
        }
    }

    /// The nearest float: one correctly rounded division of two exact integers.
    #[allow(clippy::cast_precision_loss)]
    fn f(self) -> f64 {
        self.n as f64 / self.d as f64
    }

    fn half(self) -> Self {
        Self::new(self.n, self.d * 2)
    }
}

impl Ord for Frac {
    fn cmp(&self, other: &Self) -> Ordering {
        (i128::from(self.n) * i128::from(other.d)).cmp(&(i128::from(other.n) * i128::from(self.d)))
    }
}

impl PartialOrd for Frac {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Add for Frac {
    type Output = Self;
    fn add(self, other: Self) -> Self {
        Self::new(self.n * other.d + other.n * self.d, self.d * other.d)
    }
}

impl Sub for Frac {
    type Output = Self;
    fn sub(self, other: Self) -> Self {
        Self::new(self.n * other.d - other.n * self.d, self.d * other.d)
    }
}

impl Mul for Frac {
    type Output = Self;
    fn mul(self, other: Self) -> Self {
        Self::new(self.n * other.n, self.d * other.d)
    }
}

const fn frac(n: i64, d: i64) -> Frac {
    Frac { n, d }
}

/// A range on the canvas: left, top, right, bottom, with y = 0 at the top.
type Rect = [Frac; 4];

const THIRDS: [Frac; 4] = [frac(0, 1), frac(1, 3), frac(2, 3), frac(1, 1)];
const HALF: Frac = frac(1, 2);
const TENTH: Frac = frac(1, 10);
const TWELFTH: Frac = frac(1, 12);
const FIFTH: Frac = frac(1, 5);

fn cell(col: usize, row: usize) -> Rect {
    [THIRDS[col], THIRDS[row], THIRDS[col + 1], THIRDS[row + 1]]
}

fn area(r: &Rect) -> f64 {
    ((r[2] - r[0]) * (r[3] - r[1])).f()
}

fn center(r: &Rect) -> (f64, f64) {
    ((r[0] + r[2]).f() / 2.0, (r[1] + r[3]).f() / 2.0)
}

fn exact_center(r: &Rect) -> (Frac, Frac) {
    ((r[0] + r[2]).half(), (r[1] + r[3]).half())
}

fn inside(inner: &Rect, outer: &Rect) -> bool {
    outer[0] <= inner[0] && outer[1] <= inner[1] && inner[2] <= outer[2] && inner[3] <= outer[3]
}

fn intersection(a: &Rect, b: &Rect) -> f64 {
    let w = a[2].min(b[2]) - a[0].max(b[0]);
    let h = a[3].min(b[3]) - a[1].max(b[1]);
    if w > Frac::ZERO && h > Frac::ZERO {
        (w * h).f()
    } else {
        0.0
    }
}

// ---------------------------------------------------------------------------
// Fixed arithmetic procedures

/// `max(0, x)` as the solver means it: the value when positive, otherwise zero.
fn pos(x: f64) -> f64 {
    if x > 0.0 { x } else { 0.0 }
}

/// A compensated sum (Neumaier) that starts from the first item.
fn sum(items: impl IntoIterator<Item = f64>) -> f64 {
    let mut items = items.into_iter();
    let Some(first) = items.next() else {
        return 0.0;
    };
    let mut hi = 0.0 + first;
    let mut lo = 0.0;
    for x in items {
        let t = hi + x;
        if hi.abs() >= x.abs() {
            lo += (hi - t) + x;
        } else {
            lo += (x - t) + hi;
        }
        hi = t;
    }
    if lo != 0.0 && lo.is_finite() {
        hi + lo
    } else {
        hi
    }
}

fn dl_mul(x: f64, y: f64) -> (f64, f64) {
    let z = x * y;
    (z, x.mul_add(y, -z))
}

fn dl_fast_sum(a: f64, b: f64) -> (f64, f64) {
    let x = a + b;
    (x, (a - x) + b)
}

/// The exponent `e` of `x = m * 2^e` with `0.5 <= m < 1`, for a positive normal `x`.
#[allow(clippy::cast_possible_truncation, clippy::cast_possible_wrap)]
fn frexp_exponent(x: f64) -> i32 {
    ((x.to_bits() >> 52) & 0x7ff) as i32 - 1022
}

/// `2^k` for an exponent in the normal range.
#[allow(clippy::cast_sign_loss)]
fn power_of_two(k: i32) -> f64 {
    f64::from_bits(((k + 1023) as u64) << 52)
}

/// The length of `(x, y)`: lossless scaling, squaring and summation, then one
/// differential correction of the square root. The laws stage measures with it
/// too, as its prototype measured with Python's `math.hypot` and `math.dist`.
pub(crate) fn hypot(x: f64, y: f64) -> f64 {
    let (x, y) = (x.abs(), y.abs());
    let mut max = 0.0_f64;
    for v in [x, y] {
        if v > max {
            max = v;
        }
    }
    if max.is_infinite() || max == 0.0 {
        return max;
    }
    if max < f64::MIN_POSITIVE {
        return (x * x + y * y).sqrt();
    }
    let scale = power_of_two(-frexp_exponent(max));
    let (mut csum, mut frac1, mut frac2) = (1.0_f64, 0.0_f64, 0.0_f64);
    for v in [x, y] {
        let v = v * scale;
        let (hi, lo) = dl_mul(v, v);
        let (s_hi, s_lo) = dl_fast_sum(csum, hi);
        csum = s_hi;
        frac1 += lo;
        frac2 += s_lo;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let (hi, lo) = dl_mul(-h, h);
    let (s_hi, s_lo) = dl_fast_sum(csum, hi);
    csum = s_hi;
    frac1 += lo;
    frac2 += s_lo;
    let rest = csum - 1.0 + (frac1 + frac2);
    h += rest / (2.0 * h);
    h / scale
}

fn distance(p: (f64, f64), q: (f64, f64)) -> f64 {
    hypot(p.0 - q.0, p.1 - q.1)
}

/// `n^0.7` for a work-plan count (1 to 60), as fixed constants.
const COUNT_WEIGHT: [f64; 60] = [
    1.0,
    1.624504792712471,
    2.157669279974593,
    2.6390158215457884,
    3.0851693136000478,
    3.5051440864071925,
    3.9045287771227217,
    4.2870938501451725,
    4.655536721746079,
    5.011872336272722,
    5.357656669484113,
    5.69412336751626,
    6.022271719754773,
    6.342925711719625,
    6.656775051475125,
    6.964404506368992,
    7.26631540240041,
    7.56294171712541,
    7.85466234994081,
    8.141810630738087,
    8.424681795174461,
    8.703538937284877,
    8.97861780453415,
    9.25013070082624,
    9.518269693579391,
    9.783209271758404,
    10.045108566305139,
    10.304113218507691,
    10.560356962676234,
    10.813962975130146,
    11.065045030620489,
    11.31370849898476,
    11.560051208396862,
    11.804164196559913,
    12.046132367247342,
    12.286035066475314,
    12.523946590098141,
    12.759936632617045,
    12.994070685374634,
    13.226410390991369,
    13.45701385982374,
    13.685935953338415,
    13.91322853856461,
    14.138940717178889,
    14.363119032269166,
    14.58580765539925,
    14.807048556237302,
    15.026881656708994,
    15.245344971379456,
    15.462474735549584,
    15.678305522365587,
    15.892870350080608,
    16.106200780469578,
    16.318327009279795,
    16.52927794949702,
    16.73908130811767,
    16.94776365704033,
    17.155350498622056,
    17.361866326385883,
    17.567334681314133,
];

fn count_weight(count: u32) -> f64 {
    let count = count.max(1);
    COUNT_WEIGHT
        .get(count as usize - 1)
        .copied()
        .unwrap_or_else(|| f64::from(count).powf(0.7))
}

// ---------------------------------------------------------------------------
// Layers

/// How a layer is drawn fixes what a reading value can mean for it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LayerKind {
    /// Place or draw (and a single scattered or lined-up mark): drawn at one spot
    /// inside the range, which is shrunk to two thirds; several marks gather there.
    Bundle,
    /// Scatter, fill or tile: spread over the range.
    Area,
    /// Line up: a row from edge to edge through the range centre.
    Row,
    /// A full-width line: across the canvas at the height of the range centre.
    Line,
}

fn attribute(layer: &WorkPlanLayer, slot: WorkPlanSlot) -> Option<&str> {
    layer.attributes.get(&slot).map(String::as_str)
}

fn count_or_one(layer: &WorkPlanLayer) -> u32 {
    if layer.count == 0 { 1 } else { layer.count }
}

#[must_use]
pub fn layer_kind(layer: &WorkPlanLayer) -> LayerKind {
    let action = layer.action.as_str();
    if action == "draw" && layer.proportion.as_deref() == Some("full_width") {
        return LayerKind::Line;
    }
    if matches!(action, "scatter" | "line_up") && count_or_one(layer) <= 1 {
        return LayerKind::Bundle;
    }
    match action {
        "line_up" => LayerKind::Row,
        "scatter" | "fill" | "tile" => LayerKind::Area,
        _ => LayerKind::Bundle,
    }
}

/// The direction a band or an elongated area runs, when the plan fixes it.
fn orientation(layer: &WorkPlanLayer) -> Option<&str> {
    match layer_kind(layer) {
        LayerKind::Line => Some("horizontal"),
        LayerKind::Row => attribute(layer, WorkPlanSlot::LineUpDirection),
        LayerKind::Area if matches!(layer.action.as_str(), "fill" | "tile") => {
            match layer.proportion.as_deref() {
                Some("wide" | "full_width") => Some("horizontal"),
                Some("tall") => Some("vertical"),
                _ => None,
            }
        }
        _ => None,
    }
}

/// Fine marks strewn thinly: they neither hold empty space nor crowd another layer.
fn sparse(layer: &WorkPlanLayer) -> bool {
    layer.shape == "point"
        || (attribute(layer, WorkPlanSlot::Size) == Some("very_small") && layer.count >= 10)
}

fn fixed_band(layer: &WorkPlanLayer, direction: &str) -> bool {
    matches!(layer_kind(layer), LayerKind::Row | LayerKind::Line)
        && orientation(layer) == Some(direction)
}

const SIZE_ORDER: [&str; 9] = [
    "very_small",
    "slightly_small",
    "small",
    "normal",
    "slightly_large",
    "large",
    "very_large",
    "extra_large",
    "huge",
];

fn size_rank(layer: &WorkPlanLayer) -> usize {
    let size = match attribute(layer, WorkPlanSlot::Size) {
        Some("normal_sized") => "normal",
        Some(size) => size,
        None => "normal",
    };
    SIZE_ORDER.iter().position(|s| *s == size).unwrap_or(3)
}

/// How much a layer draws the eye before any range is chosen (size and count).
#[allow(clippy::cast_precision_loss)]
fn prominence(layer: &WorkPlanLayer) -> f64 {
    if matches!(layer.action.as_str(), "fill" | "tile") {
        return 1.0;
    }
    (size_rank(layer) + 1) as f64 * count_weight(count_or_one(layer))
}

/// The place a plan set on a layer.
fn position(layer: &WorkPlanLayer) -> Option<&str> {
    attribute(layer, WorkPlanSlot::Position)
}

// ---------------------------------------------------------------------------
// Reading values

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    /// The ground that holds the others: a large area, or a row or line across the canvas.
    Field,
    /// The one thing the eye goes to first. At most one layer.
    Focal,
    /// Supports the focal thing.
    Secondary,
    /// Many small marks spread over a range (scatter or tile only).
    Scattered,
    /// A small touch that completes the focal and secondary things.
    Accent,
}

impl Role {
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "field" => Self::Field,
            "focal" => Self::Focal,
            "secondary" => Self::Secondary,
            "scattered" => Self::Scattered,
            "accent" => Self::Accent,
            _ => return None,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RelationKind {
    Within,
    Around,
    Overlap,
    Near,
    Apart,
    Between,
    Above,
    Below,
    Piling,
    Rising,
    Falling,
    Flowing,
    Spreading,
    Isolated,
    Echo,
    Facing,
    Parallel,
    Deviation,
    Dividing,
}

impl RelationKind {
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "within" => Self::Within,
            "around" => Self::Around,
            "overlap" => Self::Overlap,
            "near" => Self::Near,
            "apart" => Self::Apart,
            "between" => Self::Between,
            "above" => Self::Above,
            "below" => Self::Below,
            "piling" => Self::Piling,
            "rising" => Self::Rising,
            "falling" => Self::Falling,
            "flowing" => Self::Flowing,
            "spreading" => Self::Spreading,
            "isolated" => Self::Isolated,
            "echo" => Self::Echo,
            "facing" => Self::Facing,
            "parallel" => Self::Parallel,
            "deviation" => Self::Deviation,
            "dividing" => Self::Dividing,
            _ => return None,
        })
    }

    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Within => "within",
            Self::Around => "around",
            Self::Overlap => "overlap",
            Self::Near => "near",
            Self::Apart => "apart",
            Self::Between => "between",
            Self::Above => "above",
            Self::Below => "below",
            Self::Piling => "piling",
            Self::Rising => "rising",
            Self::Falling => "falling",
            Self::Flowing => "flowing",
            Self::Spreading => "spreading",
            Self::Isolated => "isolated",
            Self::Echo => "echo",
            Self::Facing => "facing",
            Self::Parallel => "parallel",
            Self::Deviation => "deviation",
            Self::Dividing => "dividing",
        }
    }

    /// The names of the layers the relation relates, in order (a, b, c).
    #[must_use]
    pub fn arg_names(self) -> Vec<&'static str> {
        self.spec().0.iter().map(|(name, _)| *name).collect()
    }

    /// The layer arguments (name, required) and whether `side` or `toward` applies.
    fn spec(self) -> (&'static [(&'static str, bool)], bool, bool) {
        const AB: &[(&str, bool)] = &[("a", true), ("b", true)];
        const A: &[(&str, bool)] = &[("a", true)];
        const A_B: &[(&str, bool)] = &[("a", true), ("b", false)];
        const ABC: &[(&str, bool)] = &[("a", true), ("b", true), ("c", true)];
        match self {
            Self::Near | Self::Echo => (AB, true, false),
            Self::Between => (ABC, false, false),
            Self::Piling | Self::Rising | Self::Falling | Self::Isolated => (A, false, false),
            Self::Flowing => (A, false, true),
            Self::Spreading | Self::Dividing => (A_B, false, false),
            _ => (AB, false, false),
        }
    }
}

/// A relation the check kept: the layers it relates and, where it applies, a side.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Relation {
    #[serde(rename = "type")]
    pub kind: RelationKind,
    pub a: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub b: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub c: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub side: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub toward: Option<String>,
}

/// The words a reading joins two layers with: the DDL relations that join a
/// shape to the previous one (resting on, inside, overlapping, crossing and
/// connected).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum JointKind {
    RestsOn,
    Inside,
    Overlaps,
    Crosses,
    ContinuesFrom,
}

impl JointKind {
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "rests_on" => Self::RestsOn,
            "inside" => Self::Inside,
            "overlaps" => Self::Overlaps,
            "crosses" => Self::Crosses,
            "continues_from" => Self::ContinuesFrom,
            _ => return None,
        })
    }

    /// The Score relation the printed phrase makes.
    #[must_use]
    pub fn relation_type(self) -> &'static str {
        match self {
            Self::RestsOn => "resting_on",
            Self::Inside => "inside",
            Self::Overlaps => "overlapping",
            Self::Crosses => "crossing",
            Self::ContinuesFrom => "connected",
        }
    }
}

/// A joint the composition writes: layer `a` is printed right after layer `b`
/// and joined to it by the relation of `kind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Joint {
    #[serde(rename = "type")]
    pub kind: JointKind,
    pub a: usize,
    pub b: usize,
}

/// The roles a reading gives its layers, in the order the response schema lists them.
pub const ROLE_NAMES: [&str; 5] = ["field", "focal", "secondary", "scattered", "accent"];

/// The relations a reading may name, in the order the response schema lists them.
pub const RELATION_NAMES: [&str; 19] = [
    "within",
    "around",
    "overlap",
    "near",
    "apart",
    "between",
    "above",
    "below",
    "piling",
    "rising",
    "falling",
    "flowing",
    "spreading",
    "isolated",
    "echo",
    "facing",
    "parallel",
    "deviation",
    "dividing",
];

/// The joints a reading may name, in the order the response schema lists them.
pub const JOINT_NAMES: [&str; 5] = [
    "rests_on",
    "inside",
    "overlaps",
    "crosses",
    "continues_from",
];

pub const SIDES: [&str; 2] = ["above", "below"];
pub const TOWARD: [&str; 2] = ["left", "right"];

/// The tension axes and their values.
pub const TENSION: [(&str, &[&str]); 6] = [
    ("motion", &["still", "moving"]),
    ("focus", &["concentrated", "dispersed"]),
    ("vertical", &["rising", "falling"]),
    ("balance", &["static", "dynamic", "unbalanced"]),
    ("symmetry", &["symmetric", "asymmetric"]),
    ("void", &["strong", "medium", "weak"]),
];

/// The places a reading can name for a stated place: the places a work-plan layer
/// can take, then the four corners a description may name (I-712), which the plan
/// cannot say; `corner` alone leaves the choice to the composition.
pub const PLACES: [&str; 12] = [
    "top",
    "bottom",
    "center",
    "left_edge",
    "right_edge",
    "top_edge",
    "bottom_edge",
    "corner",
    "top_left_corner",
    "top_right_corner",
    "bottom_left_corner",
    "bottom_right_corner",
];

/// The corners a reading can name, with the corner range each is solved to.
pub const NAMED_CORNERS: [(&str, &str); 4] = [
    ("top_left_corner", "corner-tl"),
    ("top_right_corner", "corner-tr"),
    ("bottom_left_corner", "corner-bl"),
    ("bottom_right_corner", "corner-br"),
];

/// The plan places a named corner refines: `corner`, or a side the corner lies on.
/// Any other plan place stays, since a reading may tie the words to the wrong layer.
const CORNER_SIDES: [(&str, [&str; 4]); 4] = [
    (
        "top_left_corner",
        ["corner", "top", "top_edge", "left_edge"],
    ),
    (
        "top_right_corner",
        ["corner", "top", "top_edge", "right_edge"],
    ),
    (
        "bottom_left_corner",
        ["corner", "bottom", "bottom_edge", "left_edge"],
    ),
    (
        "bottom_right_corner",
        ["corner", "bottom", "bottom_edge", "right_edge"],
    ),
];

fn corner_refines(corner: &str, plan_place: Option<&str>) -> bool {
    plan_place.is_none_or(|plan| {
        CORNER_SIDES
            .iter()
            .any(|(name, sides)| *name == corner && sides.contains(&plan))
    })
}

fn named_corner(place: &str) -> Option<&'static str> {
    NAMED_CORNERS
        .iter()
        .find(|(name, _)| *name == place)
        .map(|(_, key)| *key)
}

/// Words of position, as the reading prompt lists them. A stated place must quote
/// one: the words of a scene or of a thing are not a place. Japanese is matched as
/// part of the quote, English as whole words.
const POSITION_WORDS_JA: [&str; 9] = ["上", "下", "中央", "中心", "真ん中", "左", "右", "隅", "端"];
const POSITION_WORDS_EN: [&str; 15] = [
    "top", "bottom", "center", "centre", "middle", "left", "right", "corner", "corners", "edge",
    "edges", "above", "below", "upper", "lower",
];

/// Whether quoted words contain a word of position (Japanese or English).
#[must_use]
pub fn names_a_position(words: &str) -> bool {
    if POSITION_WORDS_JA.iter().any(|word| words.contains(word)) {
        return true;
    }
    words
        .split(|c: char| !c.is_ascii_alphabetic())
        .filter(|token| !token.is_empty())
        .any(|token| POSITION_WORDS_EN.contains(&token.to_ascii_lowercase().as_str()))
}

/// A relation as the reading returned it, before the check.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct RawRelation {
    #[serde(rename = "type", default)]
    pub kind: Option<Value>,
    #[serde(default)]
    pub a: Option<Value>,
    #[serde(default)]
    pub b: Option<Value>,
    #[serde(default)]
    pub c: Option<Value>,
    #[serde(default)]
    pub side: Option<Value>,
    #[serde(default)]
    pub toward: Option<Value>,
}

impl RawRelation {
    fn arg(&self, name: &str) -> Option<&Value> {
        match name {
            "a" => self.a.as_ref(),
            "b" => self.b.as_ref(),
            "c" => self.c.as_ref(),
            _ => None,
        }
    }
}

/// A place the reading says the description states: the quoted words and,
/// optionally, the place they name.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct RawStatedPlace {
    #[serde(default)]
    pub words: Option<String>,
    #[serde(default)]
    pub place: Option<String>,
}

/// A reading as returned, before the check. Tension, stated places and joints
/// keep the reading's own order, which is the order of the findings.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct RawReading {
    pub roles: Vec<String>,
    #[serde(default)]
    pub relations: Vec<RawRelation>,
    #[serde(default)]
    pub tension: Vec<(String, Value)>,
    #[serde(default)]
    pub stated_places: Vec<(String, RawStatedPlace)>,
    /// Joints as the reply wrote them (type, layers and words); the check reads
    /// their shape.
    #[serde(default)]
    pub joints: Vec<Value>,
}

/// The reading the solver uses.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct CheckedReading {
    pub roles: Vec<Role>,
    pub relations: Vec<Relation>,
    pub tension: BTreeMap<String, String>,
    /// Places the description states, by layer: kept as they are.
    pub fixed: BTreeMap<usize, String>,
    /// Joints the composition writes as DDL relations (I-711 stage C): the
    /// reading's joints the check kept. A reading without joints keeps its
    /// stored form.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub joints: Vec<Joint>,
    /// Layers that stay where they are drawn, by layer: the boxes their marks
    /// are in, as exact bounds (left, top, right, bottom). A recomposition pins
    /// the layers the laws placed and the partners of the laws that place one
    /// layer by another (2026-10-20): each takes no range, and the others weigh
    /// with it where it is.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub pinned: BTreeMap<usize, Vec<[(u64, u64); 4]>>,
}

/// What the check dropped, changed or kept, and why (by code).
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub code: &'static str,
    pub item: String,
    pub action: &'static str,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CheckError {
    RoleCount { roles: usize, layers: usize },
    UnknownRole(String),
}

fn finding(code: &'static str, item: String, action: &'static str) -> Finding {
    Finding { code, item, action }
}

fn layer_index(value: &Value, count: usize) -> Option<usize> {
    let index = if value.is_i64() || value.is_u64() {
        value.as_i64()
    } else {
        None
    }?;
    usize::try_from(index).ok().filter(|index| *index < count)
}

/// Why a relation cannot be drawn with these layers (a finding code), or `None`.
fn relation_problem(relation: &Relation, layers: &[WorkPlanLayer]) -> Option<&'static str> {
    use LayerKind::{Area, Bundle, Line, Row};
    let a = relation.a;
    let ka = layer_kind(&layers[a]);
    let kb = relation.b.map(|b| layer_kind(&layers[b]));
    let band = |kind: LayerKind| matches!(kind, Row | Line);
    match relation.kind {
        RelationKind::Within if kb != Some(Area) => return Some("no_inside"),
        RelationKind::Around => {
            if band(ka) {
                return Some("band_cannot_surround");
            }
            if let Some(b) = relation.b
                && ka == Bundle
                && kb == Some(Bundle)
                && size_rank(&layers[a]) < size_rank(&layers[b])
            {
                return Some("bundle_too_small");
            }
            if kb.is_some_and(band) {
                return Some("band_cannot_be_surrounded");
            }
        }
        _ => {}
    }
    let kind = relation.kind;
    if matches!(
        kind,
        RelationKind::Above | RelationKind::Below | RelationKind::Piling
    ) && (fixed_band(&layers[a], "vertical")
        || relation
            .b
            .is_some_and(|b| fixed_band(&layers[b], "vertical")))
    {
        return Some("vertical_band");
    }
    if matches!(kind, RelationKind::Rising | RelationKind::Falling)
        && band(ka)
        && orientation(&layers[a]) == Some("horizontal")
    {
        return Some("horizontal_band");
    }
    if kind == RelationKind::Flowing && fixed_band(&layers[a], "vertical") {
        return Some("vertical_band");
    }
    if kind == RelationKind::Spreading && ka != Area {
        return Some("one_spot");
    }
    if kind == RelationKind::Isolated && band(ka) {
        return Some("band_touches_edges");
    }
    if kind == RelationKind::Echo {
        let kb = kb.unwrap_or(ka);
        let same = ka == kb || (band(ka) && band(kb));
        if !same {
            return Some("different_kinds");
        }
    }
    if kind == RelationKind::Facing {
        let kb = kb.unwrap_or(ka);
        if !matches!(ka, Bundle | Area) || !matches!(kb, Bundle | Area) {
            return Some("band_cannot_face");
        }
    }
    if kind == RelationKind::Parallel {
        if ka == Bundle || kb == Some(Bundle) {
            return Some("one_spot");
        }
        let directions: BTreeSet<&str> = [Some(a), relation.b]
            .into_iter()
            .flatten()
            .filter_map(|i| orientation(&layers[i]))
            .collect();
        if directions.len() > 1 {
            return Some("crossing");
        }
    }
    if kind == RelationKind::Deviation {
        if ka != Bundle {
            return Some("needs_single");
        }
        if !matches!(kb, Some(Area | Row)) {
            return Some("needs_group");
        }
    }
    if kind == RelationKind::Dividing {
        if ka == Bundle || (ka == Area && orientation(&layers[a]).is_none()) {
            return Some("not_long");
        }
        if kb.is_some_and(|kb| kb != Area) {
            return Some("no_inside");
        }
    }
    None
}

/// Pairs of relations that contradict; the later one is dropped.
const CONFLICTS: [(RelationKind, RelationKind, &str); 17] = [
    (RelationKind::Above, RelationKind::Below, "same"),
    (RelationKind::Above, RelationKind::Above, "swapped"),
    (RelationKind::Below, RelationKind::Below, "swapped"),
    (RelationKind::Within, RelationKind::Within, "swapped"),
    (RelationKind::Within, RelationKind::Apart, "either"),
    (RelationKind::Around, RelationKind::Within, "same"),
    (RelationKind::Around, RelationKind::Apart, "either"),
    (RelationKind::Rising, RelationKind::Falling, "same"),
    (RelationKind::Rising, RelationKind::Piling, "same"),
    (RelationKind::Isolated, RelationKind::Near, "a_in"),
    (RelationKind::Isolated, RelationKind::Overlap, "a_in"),
    (RelationKind::Isolated, RelationKind::Around, "a_in"),
    (RelationKind::Facing, RelationKind::Near, "either"),
    (RelationKind::Facing, RelationKind::Overlap, "either"),
    (RelationKind::Facing, RelationKind::Within, "either"),
    (RelationKind::Near, RelationKind::Apart, "either"),
    (RelationKind::Overlap, RelationKind::Apart, "either"),
];

fn conflicts(first: &Relation, second: &Relation, exempt: impl Fn(usize) -> bool) -> bool {
    for (x, y, how) in CONFLICTS {
        for (p, q) in [(first, second), (second, first)] {
            if p.kind != x || q.kind != y {
                continue;
            }
            let (pa, pb, qa, qb) = (Some(p.a), p.b, Some(q.a), q.b);
            let hit = match how {
                "same" => (pa, pb) == (qa, qb),
                "swapped" => (pa, pb) == (qb, qa),
                "either" => BTreeSet::from([pa, pb]) == BTreeSet::from([qa, qb]),
                _ => {
                    if pa == qa || pa == qb {
                        let other = if qa == pa { qb } else { qa };
                        other.is_none_or(|other| !exempt(other))
                    } else {
                        false
                    }
                }
            };
            if hit {
                return true;
            }
        }
    }
    false
}

/// Whether the description holds the words of the i-th quote: the stated places
/// in order, then the joints (with n stated places, the k-th joint is n + k).
pub type Quoted<'a> = &'a dyn Fn(usize, &str) -> bool;

/// A returned joint whose type is one of the five and whose two layers are two
/// different layers of the plan, or `None`.
fn read_joint(value: &Value, count: usize) -> Option<Joint> {
    let kind = JointKind::parse(value.get("type")?.as_str()?)?;
    let [a, b] = value.get("layers")?.as_array()?.as_slice() else {
        return None;
    };
    let (a, b) = (layer_index(a, count)?, layer_index(b, count)?);
    (a != b).then_some(Joint { kind, a, b })
}

/// Check a reading against the plan before the solver uses it.
///
/// `quoted(i, words)` says whether the description holds the words of the i-th
/// quote, a stated place or a joint; `None` skips that test. Values the canvas
/// cannot show are dropped or changed, with a finding. The joints are checked in
/// the reply's order once the stated places are fixed, and the ones a
/// composition cannot write are dropped as [`check_joints`] drops them.
pub fn check(
    reading: &RawReading,
    layers: &[WorkPlanLayer],
    quoted: Option<Quoted<'_>>,
) -> Result<(CheckedReading, Vec<Finding>), CheckError> {
    let count = layers.len();
    if reading.roles.len() != count {
        return Err(CheckError::RoleCount {
            roles: reading.roles.len(),
            layers: count,
        });
    }
    let mut findings = Vec::new();
    let mut roles = Vec::with_capacity(count);
    for (i, role) in reading.roles.iter().enumerate() {
        let mut role = Role::parse(role).ok_or_else(|| CheckError::UnknownRole(role.clone()))?;
        if role == Role::Scattered && !matches!(layers[i].action.as_str(), "scatter" | "tile") {
            role = Role::Secondary;
            findings.push(finding(
                "scattered_needs_spread",
                format!("roles[{i}]"),
                "changed",
            ));
        }
        roles.push(role);
    }
    let focal: Vec<usize> = (0..count).filter(|i| roles[*i] == Role::Focal).collect();
    if focal.len() > 1 {
        let mut keep = focal[0];
        for &i in &focal[1..] {
            if prominence(&layers[i]) > prominence(&layers[keep]) {
                keep = i;
            }
        }
        for &i in &focal {
            if i != keep {
                roles[i] = Role::Secondary;
            }
        }
        findings.push(finding("one_focal", "roles".to_owned(), "changed"));
    }

    let mut relations: Vec<Relation> = Vec::new();
    for (n, raw) in reading.relations.iter().enumerate() {
        let item = format!("relations[{n}]");
        let Some(kind) = raw
            .kind
            .as_ref()
            .and_then(Value::as_str)
            .and_then(RelationKind::parse)
        else {
            findings.push(finding("unknown_relation", item, "dropped"));
            continue;
        };
        let (args, side_applies, toward_applies) = kind.spec();
        let missing = args
            .iter()
            .any(|(name, required)| *required && raw.arg(name).is_none());
        let present: Vec<&Value> = args.iter().filter_map(|(name, _)| raw.arg(name)).collect();
        let indices: Vec<Option<usize>> = present
            .iter()
            .map(|value| layer_index(value, count))
            .collect();
        if missing || indices.iter().any(Option::is_none) {
            findings.push(finding("bad_layer", item, "dropped"));
            continue;
        }
        let indices: Vec<usize> = indices.into_iter().flatten().collect();
        if indices.iter().collect::<BTreeSet<_>>().len() != indices.len() {
            findings.push(finding("same_layer", item, "dropped"));
            continue;
        }
        let index_of = |name: &str| raw.arg(name).and_then(|value| layer_index(value, count));
        let mut clean = Relation {
            kind,
            a: index_of("a").unwrap_or_default(),
            b: args
                .iter()
                .any(|(name, _)| *name == "b")
                .then(|| index_of("b"))
                .flatten(),
            c: args
                .iter()
                .any(|(name, _)| *name == "c")
                .then(|| index_of("c"))
                .flatten(),
            side: None,
            toward: None,
        };
        if side_applies && let Some(side) = raw.side.as_ref() {
            match side.as_str().filter(|value| SIDES.contains(value)) {
                Some(value) => clean.side = Some(value.to_owned()),
                None => findings.push(finding("bad_side", item.clone(), "changed")),
            }
        }
        if toward_applies && let Some(toward) = raw.toward.as_ref() {
            match toward.as_str().filter(|value| TOWARD.contains(value)) {
                Some(value) => clean.toward = Some(value.to_owned()),
                None => findings.push(finding("bad_toward", item.clone(), "changed")),
            }
        }
        if clean.kind == RelationKind::Isolated && roles[clean.a] == Role::Field {
            findings.push(finding("field_isolated", item, "dropped"));
            continue;
        }
        if let Some(code) = relation_problem(&clean, layers) {
            findings.push(finding(code, item, "dropped"));
            continue;
        }
        if relations.contains(&clean) {
            findings.push(finding("duplicate", item, "dropped"));
            continue;
        }
        let exempt = |index: usize| roles[index] == Role::Field || sparse(&layers[index]);
        if relations.iter().any(|kept| conflicts(kept, &clean, exempt)) {
            findings.push(finding("conflict", item, "dropped"));
            continue;
        }
        relations.push(clean);
    }

    let mut tension: BTreeMap<String, String> = BTreeMap::new();
    for (axis, value) in &reading.tension {
        let allowed = TENSION
            .iter()
            .find(|(name, _)| name == axis)
            .map(|(_, values)| *values);
        match (allowed, value.as_str()) {
            (Some(values), Some(value)) if values.contains(&value) => {
                tension.insert(axis.clone(), value.to_owned());
            }
            _ => findings.push(finding(
                "unknown_tension",
                format!("tension.{axis}"),
                "dropped",
            )),
        }
    }
    if tension.get("symmetry").map(String::as_str) == Some("symmetric") {
        match tension.get("balance").map(String::as_str) {
            Some("dynamic" | "unbalanced") => {
                findings.push(finding(
                    "symmetry_needs_static",
                    "tension.symmetry".to_owned(),
                    "dropped",
                ));
                tension.remove("symmetry");
            }
            None => {
                tension.insert("balance".to_owned(), "static".to_owned());
                findings.push(finding(
                    "symmetry_sets_static",
                    "tension.balance".to_owned(),
                    "changed",
                ));
            }
            _ => {}
        }
    }
    if tension.get("focus").map(String::as_str) == Some("concentrated") {
        let outside: BTreeSet<usize> = relations
            .iter()
            .filter(|relation| {
                matches!(
                    relation.kind,
                    RelationKind::Isolated | RelationKind::Deviation
                )
            })
            .map(|relation| relation.a)
            .collect();
        let clash = relations.iter().any(|relation| {
            relation.kind == RelationKind::Apart
                && [Some(relation.a), relation.b]
                    .into_iter()
                    .flatten()
                    .all(|i| !outside.contains(&i) && roles[i] != Role::Field)
        });
        if clash {
            findings.push(finding(
                "concentrated_but_apart",
                "tension.focus".to_owned(),
                "dropped",
            ));
            tension.remove("focus");
        }
    }

    let mut fixed = BTreeMap::new();
    for (n, (key, stated)) in reading.stated_places.iter().enumerate() {
        let item = format!("stated_places.{key}");
        let index = key
            .parse::<i64>()
            .ok()
            .and_then(|index| usize::try_from(index).ok())
            .filter(|i| *i < count);
        let read_place = stated
            .place
            .as_deref()
            .filter(|place| PLACES.contains(place));
        let plan_place = index.and_then(|index| position(&layers[index]));
        let words = stated.words.as_deref().unwrap_or_default();
        if plan_place.is_none() && (read_place.is_none() || index.is_none()) {
            findings.push(finding("stated_place_missing", item, "dropped"));
        } else if quoted.is_some_and(|quoted| words.is_empty() || !quoted(n, words)) {
            findings.push(finding("stated_place_unquoted", item, "dropped"));
        } else if !names_a_position(words) {
            findings.push(finding("stated_place_not_positional", item, "dropped"));
        } else if let (Some(index), Some(place)) = (
            index,
            read_place
                .filter(|place| named_corner(place).is_some() && corner_refines(place, plan_place)),
        ) {
            // The plan cannot say which corner; the description's words do (I-712).
            fixed.insert(index, place.to_owned());
            findings.push(finding("stated_corner_from_reading", item, "kept"));
        } else if let (Some(index), Some(plan), Some(_)) = (
            index,
            plan_place,
            read_place.filter(|place| named_corner(place).is_some()),
        ) {
            // The corner is not on the plan place's side: the plan's place stays.
            fixed.insert(index, plan.to_owned());
            findings.push(finding("stated_corner_conflict", item, "dropped"));
        } else if let (Some(index), None, Some(place)) = (index, plan_place, read_place) {
            fixed.insert(index, place.to_owned());
            findings.push(finding("stated_place_from_reading", item, "kept"));
        } else if let (Some(index), Some(place)) = (index, plan_place) {
            fixed.insert(index, place.to_owned());
        }
    }

    let mut joints = Vec::new();
    for (k, raw) in reading.joints.iter().enumerate() {
        let item = format!("joints.{k}");
        let Some(joint) = read_joint(raw, count) else {
            findings.push(finding("joint_layer", item, "dropped"));
            continue;
        };
        let words = raw.get("words").and_then(Value::as_str).unwrap_or_default();
        let at = reading.stated_places.len() + k;
        if quoted.is_some_and(|quoted| words.is_empty() || !quoted(at, words)) {
            findings.push(finding("joint_unquoted", item, "dropped"));
            continue;
        }
        joints.push(joint);
    }
    let (joints, dropped) = check_joints(&joints, layers, &fixed);
    findings.extend(dropped);
    Ok((
        CheckedReading {
            roles,
            relations,
            tension,
            fixed,
            joints,
            pinned: BTreeMap::new(),
        },
        findings,
    ))
}

/// The joints a composition can write, in the given order, and a finding for
/// each one it drops: a layer number out of range, a layer whose place the
/// description states, a partner or a layer already joined, a joint that would
/// close a loop, a connection the joined shape cannot start (only a line, an
/// arc, a free line or a point connects, and not to a cloudform), or any other
/// joint with a free line on either side (I-715: a free line is joined only at
/// its ends).
#[must_use]
pub fn check_joints(
    joints: &[Joint],
    layers: &[WorkPlanLayer],
    fixed: &BTreeMap<usize, String>,
) -> (Vec<Joint>, Vec<Finding>) {
    let mut kept: Vec<Joint> = Vec::new();
    let mut findings = Vec::new();
    for joint in joints {
        let item = format!("{} {}->{}", joint.kind.relation_type(), joint.a, joint.b);
        let code = if joint.a >= layers.len() || joint.b >= layers.len() || joint.a == joint.b {
            Some("joint_layer")
        } else if fixed.contains_key(&joint.a) {
            Some("joint_stated")
        } else if !shapes_can_join(joint, layers) {
            Some("joint_not_writable")
        } else if kept.iter().any(|other| other.b == joint.b) {
            Some("joint_partner_taken")
        } else if kept.iter().any(|other| other.a == joint.a) {
            Some("joint_layer_taken")
        } else {
            // Following the partners from b must not come back to a.
            let mut step = joint.b;
            let mut closes = false;
            while let Some(next) = kept.iter().find(|other| other.a == step) {
                step = next.b;
                if step == joint.a {
                    closes = true;
                    break;
                }
            }
            closes.then_some("joint_cycle")
        };
        match code {
            Some(code) => findings.push(finding(code, item, "dropped")),
            None => kept.push(*joint),
        }
    }
    (kept, findings)
}

/// Whether the joint's relation can join its two shapes: a connection starts
/// only from a line, an arc, a free line or a point, and never reaches a
/// cloudform; a free line takes no other joint (I-715: it is joined only at its
/// ends).
fn shapes_can_join(joint: &Joint, layers: &[WorkPlanLayer]) -> bool {
    let (a, b) = (
        layers[joint.a].shape.as_str(),
        layers[joint.b].shape.as_str(),
    );
    if joint.kind == JointKind::ContinuesFrom {
        matches!(a, "line" | "arc" | "free_line" | "point") && b != "cloudform"
    } else {
        a != "free_line" && b != "free_line"
    }
}

/// The reading to solve when no reading can be used.
///
/// Roles are guessed from how each layer is drawn, never from the description's
/// words: the first fill or tile layer is the field, scatter and tile layers of
/// many or fine marks are scattered, the most prominent remaining bundle is focal,
/// and the rest are secondary. There are no relations and no tension, so the
/// author's defaults apply. Every place the plan set is kept.
#[must_use]
pub fn default_reading(layers: &[WorkPlanLayer]) -> CheckedReading {
    let mut roles = vec![Role::Secondary; layers.len()];
    let field = layers
        .iter()
        .position(|layer| matches!(layer.action.as_str(), "fill" | "tile"));
    if let Some(field) = field {
        roles[field] = Role::Field;
    }
    for (i, layer) in layers.iter().enumerate() {
        if Some(i) != field
            && matches!(layer.action.as_str(), "scatter" | "tile")
            && (sparse(layer) || count_or_one(layer) >= 10)
        {
            roles[i] = Role::Scattered;
        }
    }
    let mut focal: Option<usize> = None;
    for (i, layer) in layers.iter().enumerate() {
        if roles[i] == Role::Secondary && layer_kind(layer) == LayerKind::Bundle {
            match focal {
                Some(best) if prominence(layer) <= prominence(&layers[best]) => {}
                _ => focal = Some(i),
            }
        }
    }
    if let Some(focal) = focal {
        roles[focal] = Role::Focal;
    }
    let fixed = layers
        .iter()
        .enumerate()
        .filter_map(|(i, layer)| position(layer).map(|place| (i, place.to_owned())))
        .collect();
    CheckedReading {
        roles,
        relations: Vec::new(),
        tension: BTreeMap::new(),
        fixed,
        joints: Vec::new(),
        pinned: BTreeMap::new(),
    }
}

// ---------------------------------------------------------------------------
// Ranges the solver chooses from

struct Region {
    key: String,
    rect: Rect,
}

struct Regions {
    /// The 28 composition ranges, then the named places.
    all: Vec<Region>,
    composed: Vec<usize>,
    large: Vec<usize>,
    small: Vec<usize>,
    full_width: Vec<usize>,
    full_height: Vec<usize>,
}

fn regions() -> &'static Regions {
    static REGIONS: OnceLock<Regions> = OnceLock::new();
    REGIONS.get_or_init(|| {
        let mut all = Vec::new();
        let mut push = |key: String, rect: Rect| all.push(Region { key, rect });
        for (col, row) in [
            (0, 0),
            (1, 0),
            (2, 0),
            (0, 1),
            (1, 1),
            (2, 1),
            (0, 2),
            (1, 2),
            (2, 2),
        ] {
            push(format!("cell-{col}{row}"), cell(col, row));
        }
        for i in 0..3 {
            push(
                format!("hband-{i}"),
                [Frac::ZERO, THIRDS[i], Frac::ONE, THIRDS[i + 1]],
            );
        }
        for i in 0..3 {
            push(
                format!("vband-{i}"),
                [THIRDS[i], Frac::ZERO, THIRDS[i + 1], Frac::ONE],
            );
        }
        let (zero, one) = (Frac::ZERO, Frac::ONE);
        for (key, rect) in [
            ("half-top", [zero, zero, one, HALF]),
            ("half-bottom", [zero, HALF, one, one]),
            ("half-left", [zero, zero, HALF, one]),
            ("half-right", [HALF, zero, one, one]),
            ("twothirds-top", [zero, zero, one, THIRDS[2]]),
            ("twothirds-bottom", [zero, THIRDS[1], one, one]),
            ("twothirds-left", [zero, zero, THIRDS[2], one]),
            ("twothirds-right", [THIRDS[1], zero, one, one]),
            ("quarter-tl", [zero, zero, HALF, HALF]),
            ("quarter-tr", [HALF, zero, one, HALF]),
            ("quarter-bl", [zero, HALF, HALF, one]),
            ("quarter-br", [HALF, HALF, one, one]),
            ("whole", [zero, zero, one, one]),
            ("named-center", [THIRDS[1], THIRDS[1], THIRDS[2], THIRDS[2]]),
            ("named-top", [zero, zero, one, THIRDS[1]]),
            ("named-bottom", [zero, THIRDS[2], one, one]),
            ("named-left_edge", [zero, zero, TENTH, one]),
            ("named-right_edge", [frac(9, 10), zero, one, one]),
            ("named-top_edge", [zero, zero, one, TENTH]),
            ("named-bottom_edge", [zero, frac(9, 10), one, one]),
            // A stated corner: the composition chooses which of the compiler's four
            // corner cells (a fifth of the canvas on each side).
            ("corner-tl", [zero, zero, FIFTH, FIFTH]),
            ("corner-tr", [frac(4, 5), zero, one, FIFTH]),
            ("corner-bl", [zero, frac(4, 5), FIFTH, one]),
            ("corner-br", [frac(4, 5), frac(4, 5), one, one]),
        ] {
            push(key.to_owned(), rect);
        }
        let composed: Vec<usize> = (0..all.len())
            .filter(|i| !all[*i].key.starts_with("named-") && !all[*i].key.starts_with("corner-"))
            .collect();
        let pick = |test: &dyn Fn(&Region) -> bool| -> Vec<usize> {
            composed
                .iter()
                .copied()
                .filter(|i| test(&all[*i]))
                .collect()
        };
        let large = pick(&|r| {
            r.key == "whole"
                || ["half", "twothirds", "hband", "vband"]
                    .iter()
                    .any(|p| r.key.starts_with(p))
        });
        let small = pick(&|r| r.key.starts_with("cell") || r.key.starts_with("quarter"));
        let full_width = pick(&|r| r.rect[0] == Frac::ZERO && r.rect[2] == Frac::ONE);
        let full_height = pick(&|r| r.rect[1] == Frac::ZERO && r.rect[3] == Frac::ONE);
        Regions {
            all,
            composed,
            large,
            small,
            full_width,
            full_height,
        }
    })
}

fn named_region(place: &str) -> Option<usize> {
    let key = format!("named-{place}");
    regions().all.iter().position(|region| region.key == key)
}

/// The ranges a stated place allows: its named range, the four corners, or the one
/// corner the description names.
fn stated_regions(place: &str) -> Option<Vec<usize>> {
    if let Some(key) = named_corner(place) {
        return regions()
            .all
            .iter()
            .position(|region| region.key == key)
            .map(|index| vec![index]);
    }
    if place == "corner" {
        let all = &regions().all;
        return Some(
            (0..all.len())
                .filter(|i| all[*i].key.starts_with("corner-"))
                .collect(),
        );
    }
    named_region(place).map(|index| vec![index])
}

/// The keys of the ranges a layer can be composed into: the 28 composition ranges,
/// then the four corners a stated corner chooses from.
#[must_use]
pub fn placement_keys() -> Vec<&'static str> {
    regions()
        .all
        .iter()
        .filter(|region| !region.key.starts_with("named-"))
        .map(|region| region.key.as_str())
        .collect()
}

/// The index of a range by its key.
#[must_use]
pub fn region_index(key: &str) -> Option<usize> {
    regions().all.iter().position(|region| region.key == key)
}

/// The words that name a composition range in the visible DDL (Japanese, English).
fn region_words(key: &str) -> Option<(&'static str, &'static str)> {
    Some(match key {
        "cell-00" => ("左上", "top left"),
        "cell-10" => ("上中央", "top center"),
        "cell-20" => ("右上", "top right"),
        "cell-01" => ("左中央", "center left"),
        "cell-11" => ("中心", "center"),
        "cell-21" => ("右中央", "center right"),
        "cell-02" => ("左下", "bottom left"),
        "cell-12" => ("下中央", "bottom center"),
        "cell-22" => ("右下", "bottom right"),
        "hband-0" => ("上", "top"),
        "hband-1" => ("中ほど", "middle"),
        "hband-2" => ("下", "bottom"),
        "vband-0" => ("左", "left"),
        "vband-1" => ("中央の縦", "center column"),
        "vband-2" => ("右", "right"),
        "half-top" => ("上半分", "upper half"),
        "half-bottom" => ("下半分", "lower half"),
        "half-left" => ("左半分", "left half"),
        "half-right" => ("右半分", "right half"),
        "twothirds-top" => ("上の3分の2", "upper two thirds"),
        "twothirds-bottom" => ("下の3分の2", "lower two thirds"),
        "twothirds-left" => ("左の3分の2", "left two thirds"),
        "twothirds-right" => ("右の3分の2", "right two thirds"),
        "quarter-tl" => ("左上の四半分", "upper left quarter"),
        "quarter-tr" => ("右上の四半分", "upper right quarter"),
        "quarter-bl" => ("左下の四半分", "lower left quarter"),
        "quarter-br" => ("右下の四半分", "lower right quarter"),
        "whole" => ("画面全体", "whole canvas"),
        "corner-tl" => ("左上の隅", "top left corner"),
        "corner-tr" => ("右上の隅", "top right corner"),
        "corner-bl" => ("左下の隅", "bottom left corner"),
        "corner-br" => ("右下の隅", "bottom right corner"),
        _ => return None,
    })
}

/// The plan and the ranges to print for a solved placement. A layer placed on a
/// stated place keeps (or takes) that place word; every other layer is written with
/// its range (words and numbers), and loses any place the plan guessed.
#[must_use]
pub fn composed_plan(plan: &WorkPlan, chosen: &[usize]) -> (WorkPlan, Vec<Option<ComposedRange>>) {
    let table = regions();
    let mut plan = plan.clone();
    let mut ranges = Vec::with_capacity(plan.layers.len());
    for (layer, index) in plan.layers.iter_mut().zip(chosen) {
        let region = &table.all[*index];
        if let Some(place) = region.key.strip_prefix("named-") {
            layer
                .attributes
                .insert(WorkPlanSlot::Position, place.to_owned());
            ranges.push(None);
            continue;
        }
        layer.attributes.remove(&WorkPlanSlot::Position);
        let (words_ja, words_en) =
            region_words(&region.key).expect("every composition range has words");
        let bound = |value: Frac| {
            (
                u32::try_from(value.n).expect("a range lies on the canvas"),
                u32::try_from(value.d).expect("a positive denominator"),
            )
        };
        ranges.push(Some(ComposedRange {
            words_ja: words_ja.to_owned(),
            words_en: words_en.to_owned(),
            bounds: region.rect.map(bound),
        }));
    }
    (plan, ranges)
}

/// The key a pinned layer's only answer goes by: it takes no range.
pub const PINNED_KEY: &str = "pinned";

/// The answer a pinned layer takes, past the ranges: it stays where it is.
#[must_use]
pub fn pinned_answer() -> usize {
    regions().all.len()
}

/// The key of a range (`cell-22`, `named-bottom`, ...), or [`PINNED_KEY`] for
/// the answer a pinned layer takes.
#[must_use]
pub fn region_key(index: usize) -> &'static str {
    regions()
        .all
        .get(index)
        .map_or(PINNED_KEY, |region| region.key.as_str())
}

/// The range a written range is, by its exact bounds (left, top, right, bottom):
/// one of the 28 composition ranges, a named place or a corner.
#[must_use]
pub fn region_of_bounds(bounds: [(u64, u64); 4]) -> Option<usize> {
    let rect = rect_of_bounds(bounds)?;
    regions().all.iter().position(|region| region.rect == rect)
}

/// A written range's exact bounds (left, top, right, bottom) as a range.
fn rect_of_bounds(bounds: [(u64, u64); 4]) -> Option<Rect> {
    let mut rect = [Frac::ZERO; 4];
    for (slot, (numerator, denominator)) in rect.iter_mut().zip(bounds) {
        let (numerator, denominator) = (
            i64::try_from(numerator).ok()?,
            i64::try_from(denominator).ok()?,
        );
        if denominator == 0 {
            return None;
        }
        *slot = Frac::new(numerator, denominator);
    }
    Some(rect)
}

/// Whether a range is one of the 28 a composition chooses from.
#[must_use]
pub fn is_composition_range(index: usize) -> bool {
    regions().composed.contains(&index)
}

/// The corner a range is, as the place a reading names it with.
#[must_use]
pub fn corner_place(index: usize) -> Option<&'static str> {
    let key = regions().all.get(index)?.key.as_str();
    NAMED_CORNERS
        .iter()
        .find(|(_, corner)| *corner == key)
        .map(|(place, _)| *place)
}

/// The one range a fixed place keeps, when it keeps exactly one.
#[must_use]
pub fn fixed_region(place: &str) -> Option<usize> {
    match stated_regions(place)?.as_slice() {
        [index] => Some(*index),
        _ => None,
    }
}

/// The words and bounds a composition range or a corner is written with.
#[must_use]
pub fn written_range(index: usize) -> Option<ComposedRange> {
    let region = regions().all.get(index)?;
    let (words_ja, words_en) = region_words(&region.key)?;
    let bound = |value: Frac| Some((u32::try_from(value.n).ok()?, u32::try_from(value.d).ok()?));
    Some(ComposedRange {
        words_ja: words_ja.to_owned(),
        words_en: words_en.to_owned(),
        bounds: [
            bound(region.rect[0])?,
            bound(region.rect[1])?,
            bound(region.rect[2])?,
            bound(region.rect[3])?,
        ],
    })
}

/// One range a host shows by its name: one of the 28 composition ranges, or a
/// corner (which another composition keeps). Bounds are left, top, right, bottom,
/// each an exact fraction `(numerator, denominator)`, as `written_range` writes them.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct NamedRange {
    pub key: &'static str,
    pub words_ja: String,
    pub words_en: String,
    pub bounds: [(u32, u32); 4],
    pub corner: bool,
}

/// The ranges the composition writes by name, in the order of `placement_keys`:
/// the 28 composition ranges, then the four corners. A host folds a written range
/// whose words and numbers are one of these, and names numbers by them.
#[must_use]
pub fn named_ranges() -> Vec<NamedRange> {
    let all = &regions().all;
    (0..all.len())
        .filter(|index| !all[*index].key.starts_with("named-"))
        .filter_map(|index| {
            let range = written_range(index)?;
            let key = all[index].key.as_str();
            Some(NamedRange {
                key,
                words_ja: range.words_ja,
                words_en: range.words_en,
                bounds: range.bounds,
                corner: key.starts_with("corner-"),
            })
        })
        .collect()
}

/// How an answer other than the current one was found.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OtherAnswer {
    /// Another near-best answer, chosen as `solve` chooses.
    Near,
    /// The near-best held only the current answer: the best other one by score.
    Next,
    /// No other answer exists (every layer keeps its only range).
    None,
}

/// An answer other than `current` (the author's decision Q5, 2026-10-04): among the
/// near-best answers, chosen by the seed and the work as `solve` chooses; when the
/// near-best holds only the current answer, the best other combination by score,
/// then by range keys.
pub fn other_answer(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
    searched: &Searched,
    current: Option<&[usize]>,
    seed: u64,
    work_id: &str,
) -> Result<(Vec<usize>, OtherAnswer), Unsolved> {
    other_of(searched, current, seed, work_id, || {
        Work::new(layers, reading, background)
    })
}

/// [`other_answer`] for the solver's work, which `work` gives only when the
/// near-best hold no other answer.
fn other_of<'a>(
    searched: &Searched,
    current: Option<&[usize]>,
    seed: u64,
    work_id: &str,
    work: impl FnOnce() -> Result<Work<'a>, Unsolved>,
) -> Result<(Vec<usize>, OtherAnswer), Unsolved> {
    let near: Vec<&Vec<usize>> = searched
        .near
        .iter()
        .filter(|answer| Some(answer.as_slice()) != current)
        .collect();
    if !near.is_empty() {
        return Ok((
            near[pick_index(seed, work_id, near.len())].clone(),
            OtherAnswer::Near,
        ));
    }
    let Some(current) = current else {
        return Err(Unsolved::NoRanges);
    };
    let work = work()?;
    let sizes: Vec<usize> = work.options.iter().map(Vec::len).collect();
    let keys = |choice: &[usize]| -> Vec<&str> { choice.iter().map(|i| region_key(*i)).collect() };
    let mut best: Option<(f64, Vec<usize>)> = None;
    let mut terms = Terms::default();
    let mut digits = vec![0_usize; sizes.len()];
    loop {
        let choice: Vec<usize> = digits
            .iter()
            .enumerate()
            .map(|(layer, digit)| work.options[layer][*digit])
            .collect();
        if choice != current {
            let total = work.score(&choice, &mut terms).total;
            let better = match &best {
                None => true,
                Some((best_total, best_choice)) => {
                    total < *best_total
                        || (total == *best_total && keys(&choice) < keys(best_choice))
                }
            };
            if better {
                best = Some((total, choice));
            }
        }
        if !advance(&mut digits, &sizes) {
            break;
        }
    }
    Ok(match best {
        Some((_, choice)) => (choice, OtherAnswer::Next),
        None => (current.to_vec(), OtherAnswer::None),
    })
}

/// Ranges chosen by chance (automatism, the author's decision 2026-10-04): each
/// layer without a fixed place takes one of the ranges its kind allows (the
/// solver's own constraints, without a role's), by a hash of the seed, the work
/// and the layer. A fixed layer keeps its range.
pub fn chance_answer(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    seed: u64,
    work_id: &str,
) -> Result<Vec<usize>, Unsolved> {
    layers
        .iter()
        .enumerate()
        .map(|(index, layer)| {
            if reading.pinned.contains_key(&index) {
                return Ok(pinned_answer());
            }
            // Without joints no layer is on either side of one.
            let options =
                one_per_center(layer, chance_options(layer, &reading.fixed, index, false)?);
            Ok(chance_pick(&options, seed, work_id, index))
        })
        .collect()
}

/// The ranges chance chooses from for layer `index`; `edge_joint` says whether
/// the layer is on either side of a joint that rests on or crosses.
fn chance_options(
    layer: &WorkPlanLayer,
    fixed: &BTreeMap<usize, String>,
    index: usize,
    edge_joint: bool,
) -> Result<Vec<usize>, Unsolved> {
    candidates(
        layer,
        Role::Secondary,
        fixed.get(&index).map(String::as_str),
        edge_joint,
    )
    .filter(|options| !options.is_empty())
    .ok_or(Unsolved::NoRanges)
}

/// The range chance takes among `options` for layer `index`, by a hash of the
/// seed, the work and the layer.
fn chance_pick(options: &[usize], seed: u64, work_id: &str, index: usize) -> usize {
    let digest = Sha256::digest(format!("{seed}:{work_id}:{index}").as_bytes());
    let value = u64::from_be_bytes(
        digest[..8]
            .try_into()
            .expect("a SHA-256 digest has eight bytes"),
    );
    let count = u64::try_from(options.len()).expect("a range count fits u64");
    options[usize::try_from(value % count).expect("an index below the count")]
}

/// [`other_answer`] for instructions whose sentences carry joints (I-711 C6),
/// placed as [`join`] places a work: each joined layer keeps the range its
/// sentence writes (`bounds`, by layer), which sets how far it spreads, and the
/// other layers are placed again, a partner weighing with the layers joined to
/// it, keeping the ranges where its group lies on the canvas when there is one,
/// and scored as the group. The answer, like `current`, is the ranges of the
/// layers that are not joined, in their order.
pub fn other_joined_answer(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
    bounds: &[Option<[(u64, u64); 4]>],
    current: Option<&[usize]>,
    seed: u64,
    work_id: &str,
) -> Result<(Vec<usize>, OtherAnswer), Unsolved> {
    let group = grouped_by_bounds(layers, reading, background, bounds)?;
    let work = Work::with_edge_joints(
        &group.layers,
        &group.reading,
        background,
        &group.edge_joints,
        &group.jointed(),
    )?
    .with_joined(group.joined);
    let searched = search_work(&work)?;
    other_of(&searched, current, seed, work_id, || Ok(work))
}

/// [`chance_answer`] for instructions whose sentences carry joints (I-711 C6):
/// each joined layer keeps the range its sentence writes (`bounds`, by layer);
/// every other layer takes one of the ranges [`chance_answer`] gives it, by the
/// same hash (the seed, the work and the layer's own number), a partner only
/// among those where its group lies on the canvas when there is one. The
/// answer is the ranges of the layers that are not joined, in their order.
pub fn chance_joined_answer(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
    bounds: &[Option<[(u64, u64); 4]>],
    seed: u64,
    work_id: &str,
) -> Result<Vec<usize>, Unsolved> {
    let group = grouped_by_bounds(layers, reading, background, bounds)?;
    group
        .keep
        .iter()
        .zip(&group.joined)
        .zip(&group.edge_joints)
        .map(|((index, joined), edge_joint)| {
            if reading.pinned.contains_key(index) {
                return Ok(pinned_answer());
            }
            let mut options = chance_options(&layers[*index], &reading.fixed, *index, *edge_joint)?;
            if joined.is_empty() {
                options = one_per_center(&layers[*index], options);
            }
            let options = fitting(&layers[*index], options, joined);
            Ok(chance_pick(&options, seed, work_id, *index))
        })
        .collect()
}

/// Whether each of `count` layers is on either side of one of `joints` that rests
/// on or crosses: such a joint meets the layer at the edge of its range.
fn at_edge_joints<'a>(joints: impl IntoIterator<Item = &'a Joint>, count: usize) -> Vec<bool> {
    let mut edge = vec![false; count];
    for joint in joints {
        if matches!(joint.kind, JointKind::RestsOn | JointKind::Crosses) {
            for index in [joint.a, joint.b] {
                if let Some(slot) = edge.get_mut(index) {
                    *slot = true;
                }
            }
        }
    }
    edge
}

/// Whether each of `count` layers is on either side of one of `joints`.
fn in_joints<'a>(joints: impl IntoIterator<Item = &'a Joint>, count: usize) -> Vec<bool> {
    let mut jointed = vec![false; count];
    for joint in joints {
        for index in [joint.a, joint.b] {
            if let Some(slot) = jointed.get_mut(index) {
                *slot = true;
            }
        }
    }
    jointed
}

fn candidates(
    layer: &WorkPlanLayer,
    role: Role,
    fixed: Option<&str>,
    edge_joint: bool,
) -> Option<Vec<usize>> {
    let table = regions();
    if let Some(place) = fixed {
        return stated_regions(place);
    }
    // A fill cuts its marks at the edge of its range, so a range chosen here would
    // cut them: a fill without a fixed place keeps the whole canvas (the author's
    // decision of 2026-10-19). A fill on either side of a joint that rests on or
    // crosses still takes a range: the other layer stands on or crosses its edge,
    // and a joined fill as large as the canvas would leave the paper.
    if layer.action == "fill" && !edge_joint {
        return region_index("whole").map(|index| vec![index]);
    }
    let kind = layer_kind(layer);
    let direction = orientation(layer);
    if matches!(kind, LayerKind::Row | LayerKind::Line) && direction == Some("horizontal") {
        return Some(table.full_width.clone());
    }
    if kind == LayerKind::Row && direction == Some("vertical") {
        return Some(table.full_height.clone());
    }
    if layer.proportion.as_deref() == Some("full_width") {
        return Some(table.full_width.clone());
    }
    // A bundle puts its marks at one spot chosen inside the range, so only a small
    // range says where the bundle goes.
    if kind == LayerKind::Bundle {
        return Some(table.small.clone());
    }
    let options = match role {
        Role::Field => &table.large,
        Role::Focal => &table.small,
        _ => &table.composed,
    };
    // A fill or tile draws the whole range, so a tall or wide form keeps its proportion.
    let fills = matches!(layer.action.as_str(), "fill" | "tile");
    let keep = |index: &usize| {
        let r = &table.all[*index].rect;
        match layer.proportion.as_deref() {
            Some("tall") if fills => r[3] - r[1] > r[2] - r[0],
            Some("wide") if fills => r[2] - r[0] > r[3] - r[1],
            _ => true,
        }
    };
    Some(options.iter().copied().filter(keep).collect())
}

/// The canvas extent the compiler gives a layer placed in `rect`: a row runs the
/// full row or column through the range centre, a full-width line spans the width.
/// A diagonal row keeps its range here; the solver weighs it by its chord
/// ([`footprints`]) unless it is in a joint.
fn effective(layer: &WorkPlanLayer, rect: &Rect) -> Rect {
    let span = match layer_kind(layer) {
        LayerKind::Row => {
            let direction =
                orientation(layer).unwrap_or(if rect[2] - rect[0] >= rect[3] - rect[1] {
                    "horizontal"
                } else {
                    "vertical"
                });
            match direction {
                "horizontal" => Some(true),
                "vertical" => Some(false),
                _ => None,
            }
        }
        LayerKind::Line => Some(true),
        _ => None,
    };
    let (cx, cy) = exact_center(rect);
    match span {
        Some(true) => [Frac::ZERO, cy - TWELFTH, Frac::ONE, cy + TWELFTH],
        Some(false) => [cx - TWELFTH, Frac::ZERO, cx + TWELFTH, Frac::ONE],
        None => *rect,
    }
}

/// Where a layer's marks lie, as the solver weighs them: `extent`, the box of the
/// whole layer (where it sits and how far it spreads), and `cover`, the boxes its
/// marks are in, which do not overlap. For every layer but a diagonal row the
/// cover is the extent.
#[derive(Clone, Debug, PartialEq)]
struct Footprint {
    extent: Rect,
    cover: Vec<Rect>,
}

impl Footprint {
    fn whole(extent: Rect) -> Self {
        Self {
            extent,
            cover: vec![extent],
        }
    }

    /// The area its marks are in.
    fn area(&self) -> f64 {
        match self.cover.as_slice() {
            [only] => area(only),
            cover => sum(cover.iter().map(area)),
        }
    }
}

/// How much of two footprints' covers lie on each other.
fn cover_overlap(a: &Footprint, b: &Footprint) -> f64 {
    match (a.cover.as_slice(), b.cover.as_slice()) {
        ([p], [q]) => intersection(p, q),
        (p, q) => sum(p
            .iter()
            .flat_map(|p| q.iter().map(move |q| intersection(p, q)))),
    }
}

/// The gap between two footprints' covers.
fn cover_gap(a: &Footprint, b: &Footprint) -> f64 {
    match (a.cover.as_slice(), b.cover.as_slice()) {
        ([p], [q]) => box_gap(p, q),
        (p, q) => p
            .iter()
            .flat_map(|p| q.iter().map(move |q| box_gap(p, q)))
            .fold(f64::INFINITY, f64::min),
    }
}

/// The side of the squares a diagonal row's band is made of: a horizontal row's
/// band is as thick, a sixth of the canvas.
const SIXTH: Frac = frac(1, 6);

/// The footprint of a diagonal row of two or more marks placed in `rect`: the
/// compiler runs it on the chord that the line through the range's centre at 45
/// degrees cuts across the canvas (the author's decision of 2026-10-19), falling
/// to the right when `falling` and rising otherwise, on a square canvas. Its
/// extent is the box of the chord, and its cover the squares a sixth of the
/// canvas wide that the chord crosses corner to corner from its left end, the
/// last cut at its right end.
fn chord_footprint(rect: &Rect, falling: bool) -> Footprint {
    let (cx, cy) = exact_center(rect);
    let (zero, one) = (Frac::ZERO, Frac::ONE);
    // The chord is y = x + offset when it falls and y = offset - x when it rises.
    let (offset, start, end) = if falling {
        let offset = cy - cx;
        (offset, zero.max(zero - offset), one.min(one - offset))
    } else {
        let offset = cx + cy;
        (offset, zero.max(offset - one), one.min(offset))
    };
    let y = |x: Frac| if falling { x + offset } else { offset - x };
    let mut cover = Vec::new();
    let mut x = start;
    while x < end {
        let next = (x + SIXTH).min(end);
        let (from, to) = (y(x), y(next));
        cover.push([x, from.min(to), next, from.max(to)]);
        x = next;
    }
    let (from, to) = (y(start), y(end));
    Footprint {
        extent: [start, from.min(to), end, from.max(to)],
        cover,
    }
}

/// The ways a diagonal row of two or more marks can run (falling is `true`):
/// one for a falling or rising row, both for a bare diagonal row, whose
/// direction the compiler chooses from the printed instructions.
fn diagonal_directions(layer: &WorkPlanLayer) -> Option<&'static [bool]> {
    if layer_kind(layer) != LayerKind::Row {
        return None;
    }
    match orientation(layer) {
        Some("falling") => Some(&[true]),
        Some("rising") => Some(&[false]),
        Some("diagonal") => Some(&[true, false]),
        _ => None,
    }
}

/// The footprints a layer placed in `rect` can take, weighed alike: its extent,
/// or for a diagonal row the chord of each way it can run, falling first. A
/// diagonal row in a joint (`jointed`) keeps its range: a joint puts the joined
/// layer by its partner's box, and a chord does not say where on it.
fn footprints(layer: &WorkPlanLayer, rect: &Rect, jointed: bool) -> Vec<Footprint> {
    match diagonal_directions(layer) {
        Some(directions) if !jointed => directions
            .iter()
            .map(|falling| chord_footprint(rect, *falling))
            .collect(),
        _ => vec![Footprint::whole(effective(layer, rect))],
    }
}

/// A diagonal row runs on the chord through its range's centre, so ranges with
/// one centre draw it alike: it keeps the first range of each centre among
/// `options`. Every other layer keeps `options`.
fn one_per_center(layer: &WorkPlanLayer, options: Vec<usize>) -> Vec<usize> {
    if diagonal_directions(layer).is_none() {
        return options;
    }
    let table = regions();
    let mut centers = BTreeSet::new();
    options
        .into_iter()
        .filter(|index| centers.insert(exact_center(&table.all[*index].rect)))
        .collect()
}

// ---------------------------------------------------------------------------
// Weighing a placement

fn size_area(size: Option<&str>) -> f64 {
    match size {
        Some("very_small") => 0.0015,
        Some("slightly_small") => 0.006,
        Some("small") => 0.01,
        Some("slightly_large") => 0.06,
        Some("large") => 0.12,
        Some("very_large") => 0.25,
        Some("extra_large") => 0.35,
        Some("huge") => 0.5,
        _ => 0.03,
    }
}

/// The side of the square a mark of `layer` is taken to cover, from its size
/// word (the area the solver weighs it by).
#[must_use]
pub fn mark_side(layer: &WorkPlanLayer) -> f64 {
    size_area(attribute(layer, WorkPlanSlot::Size)).sqrt()
}

fn lightness(color: Option<&str>, default: f64) -> f64 {
    match color {
        Some("white") => 0.99,
        Some("black") => 0.20,
        Some("blue") => 0.45,
        Some("red") => 0.58,
        Some("green") => 0.50,
        Some("gray") => 0.47,
        Some("yellow") => 0.57,
        Some("orange") => 0.82,
        Some("purple") => 0.40,
        _ => default,
    }
}

fn surface_weight(surface: Option<&str>) -> f64 {
    match surface {
        Some("solid" | "flat") => 1.5,
        Some("aquatint") => 1.1,
        Some("grain" | "sweep" | "hatch") => 0.9,
        Some("stipple") => 0.8,
        Some("wash") => 0.7,
        Some("none" | "empty") => 0.6,
        _ => 1.0,
    }
}

fn band_direction(r: &Rect) -> Option<&'static str> {
    if r[0] == Frac::ZERO && r[2] == Frac::ONE && r[3] - r[1] < Frac::ONE {
        return Some("horizontal");
    }
    if r[1] == Frac::ZERO && r[3] == Frac::ONE && r[2] - r[0] < Frac::ONE {
        return Some("vertical");
    }
    None
}

fn box_gap(a: &Rect, b: &Rect) -> f64 {
    let dx = pos((a[0].max(b[0]) - a[2].min(b[2])).f());
    let dy = pos((a[1].max(b[1]) - a[3].min(b[3])).f());
    hypot(dx, dy)
}

/// Distance that matters on the canvas: across a band only its crossing axis counts.
fn separation(a: &Rect, b: &Rect) -> f64 {
    let (ca, cb) = (center(a), center(b));
    let directions = [band_direction(a), band_direction(b)];
    if directions.contains(&Some("horizontal")) {
        return (ca.1 - cb.1).abs();
    }
    if directions.contains(&Some("vertical")) {
        return (ca.0 - cb.0).abs();
    }
    distance(ca, cb)
}

/// How much of a range the other drawn layers' marks take (0 to 1).
fn occupied(region: &Rect, placed: &[&Footprint], obstacles: &[usize]) -> f64 {
    let size = area(region);
    if size <= 0.0 {
        return 0.0;
    }
    let share = sum(obstacles
        .iter()
        .flat_map(|i| placed[*i].cover.iter().map(|q| intersection(region, q))))
        / size;
    if share < 1.0 { share } else { 1.0 }
}

/// Open space ahead of a moving bundle, in the direction it moves (lead room).
fn lead_room(a: &Rect, direction: &str, placed: &[&Footprint], obstacles: &[usize]) -> f64 {
    let (zero, one) = (Frac::ZERO, Frac::ONE);
    let ahead = match direction {
        "up" => [a[0], zero, a[2], a[1]],
        "down" => [a[0], a[3], a[2], one],
        "left" => [zero, a[1], a[0], a[3]],
        _ => [a[2], a[1], one, a[3]],
    };
    let size = area(&ahead);
    let extent = if matches!(direction, "up" | "down") {
        (ahead[3] - ahead[1]).f()
    } else {
        (ahead[2] - ahead[0]).f()
    };
    let shortfall = pos(1.0 / 3.0 - extent) / (1.0 / 3.0);
    shortfall
        + if size != 0.0 {
            occupied(&ahead, placed, obstacles)
        } else {
            0.0
        }
}

fn drawn_area(placed: &[&Footprint], sparse_layers: &[bool]) -> f64 {
    let rects: Vec<&Rect> = placed
        .iter()
        .zip(sparse_layers)
        .filter(|(_, sparse)| !**sparse)
        .flat_map(|(p, _)| p.cover.iter())
        .collect();
    if rects.is_empty() {
        return 0.0;
    }
    let clip = |v: Frac| v.max(Frac::ZERO).min(Frac::ONE);
    let edges = |a: usize, b: usize| {
        let set: BTreeSet<Frac> = rects
            .iter()
            .flat_map(|r| [clip(r[a]), clip(r[b])])
            .collect();
        set.into_iter().collect::<Vec<_>>()
    };
    let (xs, ys) = (edges(0, 2), edges(1, 3));
    let mut covered = Frac::ZERO;
    for x in xs.windows(2) {
        for y in ys.windows(2) {
            if rects
                .iter()
                .any(|r| r[0] <= x[0] && x[1] <= r[2] && r[1] <= y[0] && y[1] <= r[3])
            {
                covered = covered + (x[1] - x[0]) * (y[1] - y[0]);
            }
        }
    }
    covered.f()
}

/// How far the weight on the thirds grid is from its left-right mirror image (0 to 1).
fn mirror_mismatch(placed: &[&Footprint], weights: &[f64]) -> f64 {
    let mut grid = [[0.0_f64; 3]; 3];
    for (p, w) in placed.iter().zip(weights) {
        // A layer weighs where its marks are.
        let size = p.area();
        for r in &p.cover {
            for (row, line) in grid.iter_mut().enumerate() {
                for (col, value) in line.iter_mut().enumerate() {
                    *value += w * intersection(&cell(col, row), r) / size;
                }
            }
        }
    }
    let mut total = sum(grid.iter().map(|line| sum(line.iter().copied())));
    if total == 0.0 {
        total = 1.0;
    }
    sum((0..3)
        .flat_map(|row| (0..3).map(move |col| (row, col)))
        .map(|(row, col)| (grid[row][col] - grid[row][2 - col]).abs()))
        / (2.0 * total)
}

/// Root mean square distance of the drawn extent from its middle, each layer alike.
#[allow(clippy::cast_precision_loss)]
fn spread_of(boxes: &[&Rect]) -> f64 {
    let n = boxes.len() as f64;
    let cx = sum(boxes.iter().map(|r| center(r).0)) / n;
    let cy = sum(boxes.iter().map(|r| center(r).1)) / n;
    let second = sum(boxes.iter().map(|r| {
        let (x, y) = center(r);
        let (w, h) = ((r[2] - r[0]).f(), (r[3] - r[1]).f());
        (x - cx) * (x - cx) + (y - cy) * (y - cy) + (w * w + h * h) / 12.0
    }));
    (second / n).sqrt()
}

/// The structural points of the thirds grid where a focal thing settles.
const STRUCTURE: [(f64, f64); 4] = [
    (1.0 / 3.0, 1.0 / 3.0),
    (2.0 / 3.0, 1.0 / 3.0),
    (1.0 / 3.0, 2.0 / 3.0),
    (2.0 / 3.0, 2.0 / 3.0),
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Term {
    Balance,
    Asymmetry,
    OffAxis,
    Vertical,
    MovingFocus,
    CenteredFocus,
    FocalLocus,
    Symmetry,
    Focus,
    Void,
    Relation(usize),
    Overlap,
    FieldSize,
    ScatterSize,
}

/// Terms in the order they were first added (the order they are summed in).
#[derive(Default)]
struct Terms(Vec<(Term, f64)>);

impl Terms {
    fn set(&mut self, term: Term, value: f64) {
        match self.0.iter_mut().find(|(t, _)| *t == term) {
            Some(entry) => entry.1 = value,
            None => self.0.push((term, value)),
        }
    }

    fn add(&mut self, term: Term, value: f64) {
        match self.0.iter_mut().find(|(t, _)| *t == term) {
            Some(entry) => entry.1 += value,
            None => self.0.push((term, value)),
        }
    }

    fn total(&self) -> f64 {
        sum(self.0.iter().map(|(_, value)| *value))
    }
}

/// Everything about a work that does not depend on the chosen ranges.
struct Work<'a> {
    layers: &'a [WorkPlanLayer],
    reading: &'a CheckedReading,
    kinds: Vec<LayerKind>,
    sparse: Vec<bool>,
    /// The weight of a layer whose weight does not depend on its range.
    fixed_weight: Vec<Option<f64>>,
    tone: Vec<f64>,
    surface: Vec<f64>,
    balance: String,
    tension: BTreeMap<String, String>,
    options: Vec<Vec<usize>>,
    /// The layers joined to each layer (I-711 stage C); empty without joints.
    joined: Vec<Vec<Joined>>,
    /// The footprints each layer can take, by range index.
    footprints: Vec<Vec<Vec<Footprint>>>,
}

/// A layer joined to a composed layer: the joint, the size of the range the
/// joined layer keeps, and what its weight is made of.
#[derive(Clone, Debug)]
struct Joined {
    kind: JointKind,
    width: Frac,
    height: Frac,
    fixed_weight: Option<f64>,
    fill: bool,
    tone: f64,
    surface: f64,
}

impl Joined {
    fn weight(&self, r: &Rect) -> f64 {
        match self.fixed_weight {
            Some(weight) => weight,
            None => {
                let scale = if self.fill { 4.0 } else { 2.0 };
                area(r) * scale * self.tone * self.surface
            }
        }
    }
}

const WHOLE: Rect = [Frac::ZERO, Frac::ZERO, Frac::ONE, Frac::ONE];

/// The box of a composed layer and the layers joined to it, each placed where
/// its joint moves it, with the size of its range: resting on sits centred on
/// the top edge, inside stays within the box, and the other joints centre on
/// the box.
fn joint_group(own: &Rect, joined: &[Joined]) -> Rect {
    let (cx, cy) = exact_center(own);
    joined.iter().fold(*own, |group, joint| {
        let (half_width, half_height) = (joint.width.half(), joint.height.half());
        let placed = match joint.kind {
            JointKind::Inside => return group,
            JointKind::RestsOn => [
                cx - half_width,
                own[1] - joint.height,
                cx + half_width,
                own[1],
            ],
            _ => [
                cx - half_width,
                cy - half_height,
                cx + half_width,
                cy + half_height,
            ],
        };
        [
            group[0].min(placed[0]),
            group[1].min(placed[1]),
            group[2].max(placed[2]),
            group[3].max(placed[3]),
        ]
    })
}

/// The ranges among `options` where a layer and the layers joined to it lie on
/// the canvas; all of them when the layer has none joined or none of them fits.
fn fitting(layer: &WorkPlanLayer, options: Vec<usize>, joined: &[Joined]) -> Vec<usize> {
    if joined.is_empty() {
        return options;
    }
    let table = regions();
    let fits: Vec<usize> = options
        .iter()
        .copied()
        .filter(|index| {
            let own = effective(layer, &table.all[*index].rect);
            inside(&joint_group(&own, joined), &WHOLE)
        })
        .collect();
    if fits.is_empty() { options } else { fits }
}

/// What a layer's weight is made of: its tone against the background, its
/// surface, and its weight when that does not depend on the range.
fn weight_parts(layer: &WorkPlanLayer, background_lightness: f64) -> (f64, f64, Option<f64>) {
    let tone =
        0.3 + (lightness(attribute(layer, WorkPlanSlot::Color), 0.5) - background_lightness).abs();
    let surface = surface_weight(attribute(layer, WorkPlanSlot::Surface));
    let fixed = if matches!(layer.action.as_str(), "fill" | "tile") {
        None
    } else {
        let shape = match layer.shape.as_str() {
            "line" | "arc" | "free_line" => 0.5,
            "point" => 0.3,
            _ => 1.0,
        };
        Some(
            size_area(attribute(layer, WorkPlanSlot::Size))
                * count_weight(layer.count)
                * 10.0
                * tone
                * surface
                * shape,
        )
    };
    (tone, surface, fixed)
}

/// Why a work is not solved.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Unsolved {
    /// A stated place the solver does not know.
    UnknownPlace(String),
    /// Too many combinations for the exhaustive search.
    Combinations(u64),
    /// A layer has no range to choose from.
    NoRanges,
}

impl<'a> Work<'a> {
    fn new(
        layers: &'a [WorkPlanLayer],
        reading: &'a CheckedReading,
        background: &str,
    ) -> Result<Self, Unsolved> {
        let (joints, _) = check_joints(&reading.joints, layers, &reading.fixed);
        Self::with_edge_joints(
            layers,
            reading,
            background,
            &at_edge_joints(&joints, layers.len()),
            &in_joints(&joints, layers.len()),
        )
    }

    /// [`Work::new`] told whether each layer is on either side of a joint that
    /// rests on or crosses (`edge_joints`, by layer) and of any joint
    /// (`jointed`), which the reading of a work taken apart at its joints no
    /// longer holds.
    fn with_edge_joints(
        layers: &'a [WorkPlanLayer],
        reading: &'a CheckedReading,
        background: &str,
        edge_joints: &[bool],
        jointed: &[bool],
    ) -> Result<Self, Unsolved> {
        if let Some(place) = reading
            .fixed
            .values()
            .find(|place| stated_regions(place).is_none())
        {
            return Err(Unsolved::UnknownPlace(place.clone()));
        }
        let background_lightness = lightness(Some(background), 0.99);
        let mut tension: BTreeMap<String, String> = [("balance", "dynamic"), ("void", "strong")]
            .into_iter()
            .map(|(k, v)| (k.to_owned(), v.to_owned()))
            .collect();
        tension.extend(reading.tension.clone());
        let balance = tension
            .get("balance")
            .cloned()
            .unwrap_or_else(|| "dynamic".to_owned());
        let mut work = Self {
            layers,
            reading,
            kinds: layers.iter().map(layer_kind).collect(),
            sparse: layers.iter().map(sparse).collect(),
            fixed_weight: Vec::with_capacity(layers.len()),
            tone: Vec::with_capacity(layers.len()),
            surface: Vec::with_capacity(layers.len()),
            balance,
            tension,
            options: Vec::with_capacity(layers.len()),
            joined: vec![Vec::new(); layers.len()],
            footprints: Vec::with_capacity(layers.len()),
        };
        let table = regions();
        for (i, layer) in layers.iter().enumerate() {
            let (tone, surface, fixed) = weight_parts(layer, background_lightness);
            work.tone.push(tone);
            work.surface.push(surface);
            work.fixed_weight.push(fixed);
            if let Some(boxes) = reading.pinned.get(&i) {
                // A pinned layer weighs where its marks are drawn and takes no range.
                let cover: Vec<Rect> = boxes
                    .iter()
                    .map(|bounds| rect_of_bounds(*bounds))
                    .collect::<Option<_>>()
                    .filter(|cover: &Vec<Rect>| !cover.is_empty())
                    .ok_or(Unsolved::NoRanges)?;
                let extent = cover.iter().skip(1).fold(cover[0], |box_, rect| {
                    [
                        box_[0].min(rect[0]),
                        box_[1].min(rect[1]),
                        box_[2].max(rect[2]),
                        box_[3].max(rect[3]),
                    ]
                });
                work.options.push(vec![table.all.len()]);
                let mut prints = vec![Vec::new(); table.all.len()];
                prints.push(vec![Footprint { extent, cover }]);
                work.footprints.push(prints);
                continue;
            }
            let options = candidates(
                layer,
                reading.roles[i],
                reading.fixed.get(&i).map(String::as_str),
                edge_joints[i],
            )
            .ok_or(Unsolved::NoRanges)?;
            work.options.push(if jointed[i] {
                options
            } else {
                one_per_center(layer, options)
            });
            work.footprints.push(
                table
                    .all
                    .iter()
                    .map(|region| footprints(layer, &region.rect, jointed[i]))
                    .collect(),
            );
        }
        Ok(work)
    }

    fn combinations(&self) -> u64 {
        self.options.iter().map(|o| o.len() as u64).product()
    }

    /// Keep the layers joined to each layer: a layer with joined layers keeps
    /// only the ranges where its group lies on the canvas, when there is one,
    /// and is scored as the box of its extent grown by the layers joined to it.
    fn with_joined(mut self, joined: Vec<Vec<Joined>>) -> Self {
        let table = regions();
        for (i, group) in joined.iter().enumerate() {
            let options = std::mem::take(&mut self.options[i]);
            self.options[i] = fitting(&self.layers[i], options, group);
            if !group.is_empty() {
                self.footprints[i] = table
                    .all
                    .iter()
                    .map(|region| {
                        let own = effective(&self.layers[i], &region.rect);
                        vec![Footprint::whole(joint_group(&own, group))]
                    })
                    .collect();
            }
        }
        self.joined = joined;
        self
    }

    fn weight(&self, i: usize, r: &Rect) -> f64 {
        let own = self.own_weight(i, r);
        if self.joined[i].is_empty() {
            return own;
        }
        let mut total = own;
        for joined in &self.joined[i] {
            total += joined.weight(r);
        }
        total
    }

    fn own_weight(&self, i: usize, r: &Rect) -> f64 {
        match self.fixed_weight[i] {
            Some(weight) => weight,
            None => {
                let scale = if self.layers[i].action == "fill" {
                    4.0
                } else {
                    2.0
                };
                area(r) * scale * self.tone[i] * self.surface[i]
            }
        }
    }

    fn tension(&self, axis: &str) -> Option<&str> {
        self.tension.get(axis).map(String::as_str)
    }

    /// A relation's penalty, measured on the layers' extents (`boxes`), and on
    /// where their marks are (`placed`) for overlapping, nearness, isolation,
    /// straying and the room ahead.
    #[allow(clippy::too_many_lines)]
    fn relation_penalty(&self, relation: &Relation, boxes: &[Rect], placed: &[&Footprint]) -> f64 {
        let roles = &self.reading.roles;
        let ia = relation.a;
        let a = &boxes[ia];
        let b = relation.b.map(|ib| &boxes[ib]);
        let ka = self.kinds[ia];
        let ca = center(a);
        let obstacles: Vec<usize> = (0..boxes.len())
            .filter(|i| *i != ia && roles[*i] != Role::Field && !self.sparse[*i])
            .collect();
        let side_penalty = |b: &Rect| {
            let cb = center(b);
            let mut pen = 0.0;
            if relation.side.as_deref() == Some("below") && ca.1 <= cb.1 + 0.05 {
                pen += 0.5;
            }
            if relation.side.as_deref() == Some("above") && ca.1 >= cb.1 - 0.05 {
                pen += 0.5;
            }
            pen
        };
        match relation.kind {
            RelationKind::Within => {
                let b = b.expect("within relates two layers");
                (if inside(a, b) { 0.0 } else { 1.0 })
                    + if area(a) > 0.6 * area(b) { 0.3 } else { 0.0 }
            }
            RelationKind::Around => {
                let b = b.expect("around relates two layers");
                if ka == LayerKind::Bundle {
                    // Both bundles at one spot: the larger marks gather around the smaller.
                    if a == b {
                        0.0
                    } else if intersection(a, b) == 0.0 {
                        0.5 + box_gap(a, b) / 0.2
                    } else {
                        0.5
                    }
                } else {
                    let (cx, cy) = exact_center(b);
                    let contains = (a[0]..=a[2]).contains(&cx) && (a[1]..=a[3]).contains(&cy);
                    (if contains { 0.0 } else { 1.0 })
                        + if area(a) >= 2.0 * area(b) { 0.0 } else { 0.5 }
                }
            }
            RelationKind::Overlap => {
                let ib = relation.b.expect("overlap relates two layers");
                if cover_overlap(placed[ia], placed[ib]) > 0.0 {
                    0.0
                } else {
                    1.0 + cover_gap(placed[ia], placed[ib]) / 0.2
                }
            }
            RelationKind::Near => {
                let ib = relation.b.expect("near relates two layers");
                pos(cover_gap(placed[ia], placed[ib]) - 0.1) / 0.2 + side_penalty(&boxes[ib])
            }
            RelationKind::Apart => {
                pos(0.45 - separation(a, b.expect("apart relates two layers"))) / 0.45
            }
            RelationKind::Between => {
                let p = b.expect("between relates three layers");
                let q = &boxes[relation.c.expect("between relates three layers")];
                if band_direction(p) == Some("horizontal")
                    && band_direction(q) == Some("horizontal")
                {
                    let (pc, qc) = (center(p).1, center(q).1);
                    let (low, high) = if pc <= qc { (pc, qc) } else { (qc, pc) };
                    return if low + 0.05 < ca.1 && ca.1 < high - 0.05 {
                        0.0
                    } else {
                        1.0
                    };
                }
                let (p, q) = (center(p), center(q));
                let length = distance(p, q);
                if length < 0.2 {
                    return 1.0;
                }
                let t =
                    ((ca.0 - p.0) * (q.0 - p.0) + (ca.1 - p.1) * (q.1 - p.1)) / (length * length);
                let foot = (p.0 + t * (q.0 - p.0), p.1 + t * (q.1 - p.1));
                pos((t - 0.5).abs() - 0.3) / 0.2 + pos(distance(ca, foot) - 0.15) / 0.15
            }
            RelationKind::Below => {
                pos(center(b.expect("below relates two layers")).1 - a[1].f()) / 0.3
            }
            RelationKind::Above => {
                pos(a[3].f() - center(b.expect("above relates two layers")).1) / 0.3
            }
            RelationKind::Piling => pos(2.0 / 3.0 - a[1].f()) / (1.0 / 3.0),
            RelationKind::Rising | RelationKind::Falling => {
                if band_direction(a) == Some("vertical") {
                    return 0.0;
                }
                if ka == LayerKind::Bundle {
                    // A bundle moving up or down sits on the side it comes from, with room ahead.
                    return if relation.kind == RelationKind::Rising {
                        pos(0.5 - ca.1) / 0.25 + 0.5 * lead_room(a, "up", placed, &obstacles)
                    } else {
                        pos(ca.1 - 0.5) / 0.25 + 0.5 * lead_room(a, "down", placed, &obstacles)
                    };
                }
                pos(2.0 / 3.0 - (a[3] - a[1]).f()) / (1.0 / 3.0)
            }
            RelationKind::Flowing => {
                if band_direction(a) == Some("horizontal") {
                    return 0.0;
                }
                if ka == LayerKind::Bundle {
                    // Left and right are alike: the open side is ahead, whichever side it takes.
                    let toward = relation.toward.as_deref().unwrap_or(if ca.0 < 0.5 {
                        "right"
                    } else {
                        "left"
                    });
                    let mut pen = pos(0.15 - (ca.0 - 0.5).abs()) / 0.15;
                    if (toward == "right") == (ca.0 > 0.5) && (ca.0 - 0.5).abs() > 1e-9 {
                        pen += 1.0;
                    }
                    return pen + 0.5 * lead_room(a, toward, placed, &obstacles);
                }
                let wide = (a[2] - a[0]).f() >= 2.0 / 3.0 - 1e-9 && (a[3] - a[1]).f() <= 0.5;
                if wide { 0.0 } else { 1.0 }
            }
            RelationKind::Spreading => {
                let mut pen = pos(0.4 - area(a)) / 0.4;
                if let Some(b) = b {
                    let (cx, cy) = exact_center(b);
                    let grown = [a[0] - TENTH, a[1] - TENTH, a[2] + TENTH, a[3] + TENTH];
                    let contains =
                        (grown[0]..=grown[2]).contains(&cx) && (grown[1]..=grown[3]).contains(&cy);
                    pen += if contains { 0.0 } else { 0.5 };
                }
                pen
            }
            RelationKind::Isolated => {
                let mut gap = 1.0;
                let mut first = true;
                for i in &obstacles {
                    let g = cover_gap(placed[ia], placed[*i]);
                    if first || g < gap {
                        gap = g;
                        first = false;
                    }
                }
                (if area(a) > 1.0 / 9.0 + 1e-9 { 0.5 } else { 0.0 }) + pos(0.25 - gap) / 0.25
            }
            RelationKind::Echo => {
                let b = b.expect("echo relates two layers");
                let d = separation(a, b);
                pos(0.3 - d) / 0.3 + pos(d - 0.75) / 0.25 + side_penalty(b)
            }
            RelationKind::Facing => {
                let cb = center(b.expect("facing relates two layers"));
                let middle = ((ca.0 + cb.0) / 2.0, (ca.1 + cb.1) / 2.0);
                pos(distance(middle, (0.5, 0.5)) - 0.12) / 0.15 + pos(0.4 - distance(ca, cb)) / 0.4
            }
            RelationKind::Parallel => {
                let b = b.expect("parallel relates two layers");
                let run = |r: &Rect| {
                    band_direction(r).or_else(|| {
                        if r[2] - r[0] >= frac(2, 1) * (r[3] - r[1]) {
                            Some("horizontal")
                        } else if r[3] - r[1] >= frac(2, 1) * (r[2] - r[0]) {
                            Some("vertical")
                        } else {
                            None
                        }
                    })
                };
                let (da, db) = (run(a), run(b));
                let mut pen = if da.is_some() && da == db { 0.0 } else { 1.0 };
                pen += if intersection(a, b) > 0.0 {
                    1.0
                } else {
                    pos(box_gap(a, b) - 0.35) / 0.2
                };
                pen
            }
            RelationKind::Deviation => {
                let ib = relation.b.expect("deviation relates two layers");
                cover_overlap(placed[ia], placed[ib]) / placed[ia].area()
                    + pos(cover_gap(placed[ia], placed[ib]) - 0.2) / 0.2
            }
            RelationKind::Dividing => {
                let direction = band_direction(a).unwrap_or(if a[2] - a[0] >= a[3] - a[1] {
                    "horizontal"
                } else {
                    "vertical"
                });
                let axis = usize::from(direction == "horizontal");
                let cut = if axis == 1 { center(a).1 } else { center(a).0 };
                let whole = b
                    .copied()
                    .unwrap_or([Frac::ZERO, Frac::ZERO, Frac::ONE, Frac::ONE]);
                let (low, high) = (whole[axis].f(), whole[axis + 2].f());
                let mut pen = if low + 0.1 < cut && cut < high - 0.1 {
                    0.0
                } else {
                    1.0
                };
                if self.balance != "static" && (cut - (low + high) / 2.0).abs() < 0.05 {
                    pen += 0.3; // dynamic balance divides unequally
                }
                pen
            }
        }
    }

    /// The score of one combination of ranges (lower is better), with its terms.
    /// A bare diagonal row runs either way, as the compiler chooses from the
    /// printed instructions, so a work with such rows scores the mean over
    /// every way they can run (the first row's way changing first): each term
    /// is the mean of its values, none where a way lacks it, in the order the
    /// ways first add them, and the total is their sum.
    #[allow(clippy::cast_precision_loss)]
    fn score(&self, choice: &[usize], terms: &mut Terms) -> Score {
        let ways: Vec<&[Footprint]> = choice
            .iter()
            .enumerate()
            .map(|(i, region)| self.footprints[i][*region].as_slice())
            .collect();
        let count: usize = ways.iter().map(|way| way.len()).product();
        let pick = |mut way: usize| -> Vec<&Footprint> {
            ways.iter()
                .map(|footprints| {
                    let chosen = &footprints[way % footprints.len()];
                    way /= footprints.len();
                    chosen
                })
                .collect()
        };
        if count == 1 {
            return self.score_placed(&pick(0), terms);
        }
        let mut scores = Vec::with_capacity(count);
        let mut each = Vec::with_capacity(count);
        for way in 0..count {
            let mut way_terms = Terms::default();
            scores.push(self.score_placed(&pick(way), &mut way_terms));
            each.push(way_terms);
        }
        let n = count as f64;
        terms.0.clear();
        for way_terms in &each {
            for (term, _) in &way_terms.0 {
                if terms.0.iter().all(|(seen, _)| seen != term) {
                    let values = each.iter().map(|other| {
                        other
                            .0
                            .iter()
                            .find(|(found, _)| found == term)
                            .map_or(0.0, |(_, value)| *value)
                    });
                    terms.0.push((*term, sum(values) / n));
                }
            }
        }
        let mean = |value: fn(&Score) -> f64| sum(scores.iter().map(value)) / n;
        Score {
            total: terms.total(),
            moment: mean(|score| score.moment),
            center: (mean(|score| score.center.0), mean(|score| score.center.1)),
            void_cells: mean(|score| score.void_cells),
            void_area: mean(|score| score.void_area),
        }
    }

    /// The score of one placement of every layer, with its terms: each layer's
    /// extent says where it sits and how far it spreads, and its cover where its
    /// marks are (the empty cells, the drawn area, the mirror, overlapping).
    #[allow(clippy::too_many_lines, clippy::cast_precision_loss)]
    fn score_placed(&self, placed: &[&Footprint], terms: &mut Terms) -> Score {
        let roles = &self.reading.roles;
        let n = self.layers.len();
        let boxes: Vec<Rect> = placed.iter().map(|footprint| footprint.extent).collect();
        terms.0.clear();
        let weights: Vec<f64> = (0..n).map(|i| self.weight(i, &boxes[i])).collect();
        // 計白当黒: every empty cell of the thirds grid weighs a ninth of the marks, so an
        // empty side can hold a mass on the other side.
        let mut voids = Vec::new();
        for row in 0..3 {
            for col in 0..3 {
                let c = cell(col, row);
                if !(0..n).any(|i| {
                    !self.sparse[i] && placed[i].cover.iter().any(|q| intersection(&c, q) > 0.0)
                }) {
                    voids.push(center(&c));
                }
            }
        }
        let blank = sum(weights.iter().copied()) / 9.0;
        let mut total = sum(weights.iter().copied()) + blank * voids.len() as f64;
        if total == 0.0 {
            total = 1.0;
        }
        let cx = (sum((0..n).map(|i| weights[i] * center(&boxes[i]).0))
            + sum(voids.iter().map(|p| blank * p.0)))
            / total;
        let cy = (sum((0..n).map(|i| weights[i] * center(&boxes[i]).1))
            + sum(voids.iter().map(|p| blank * p.1)))
            / total;
        let moment = hypot(cx - 0.5, cy - 0.5);
        let first_heaviest = |indices: &mut dyn Iterator<Item = usize>| {
            let mut best: Option<usize> = None;
            for i in indices {
                if best.is_none_or(|b| weights[i] > weights[b]) {
                    best = Some(i);
                }
            }
            best
        };
        let heavy = first_heaviest(&mut (0..n).filter(|i| roles[*i] != Role::Field));
        // The heaviest range that is not the whole canvas carries the side of the picture.
        let side = first_heaviest(&mut (0..n).filter(|i| {
            area(&boxes[*i]) < 1.0 && !(boxes[*i][0] == Frac::ZERO && boxes[*i][2] == Frac::ONE)
        }));
        let symmetric = self.tension("symmetry") == Some("symmetric");
        match self.balance.as_str() {
            "static" => terms.set(Term::Balance, (moment / 0.08) * (moment / 0.08)),
            "unbalanced" => terms.set(Term::Balance, pos(0.15 - moment) / 0.05),
            _ => {
                terms.set(
                    Term::Balance,
                    pos(0.02 - moment) / 0.05 + pos(moment - 0.12) / 0.05,
                );
                if let Some(heavy) = heavy {
                    terms.set(
                        Term::Asymmetry,
                        pos(0.18 - distance(center(&boxes[heavy]), (0.5, 0.5))) / 0.18,
                    );
                }
                // Dynamic balance is asymmetric across the vertical axis too, unless the reading is symmetric.
                if let Some(side) = side
                    && !symmetric
                {
                    terms.set(
                        Term::OffAxis,
                        pos(0.15 - (center(&boxes[side]).0 - 0.5).abs()) / 0.15,
                    );
                }
            }
        }
        match self.tension("vertical") {
            Some("rising") => terms.set(Term::Vertical, pos(cy - 0.42) / 0.1),
            Some("falling") => terms.set(Term::Vertical, pos(0.58 - cy) / 0.1),
            _ => {}
        }
        let motion = self.tension("motion");
        for i in (0..n).filter(|i| roles[*i] == Role::Focal) {
            let (fx, fy) = center(&boxes[i]);
            if motion == Some("moving") && (fx - 0.5).abs() < 0.12 && (fy - 0.5).abs() < 0.12 {
                terms.add(Term::MovingFocus, 1.0);
            }
            if !symmetric
                && self.balance != "static"
                && (fx - 0.5).abs() < 1e-9
                && (fy - 0.5).abs() < 1e-9
            {
                terms.add(Term::CenteredFocus, 1.0);
            }
            let mut near = f64::INFINITY;
            let loci = STRUCTURE
                .iter()
                .copied()
                .chain((motion == Some("still")).then_some((0.5, 0.5)));
            for point in loci {
                let d = distance((fx, fy), point);
                if d < near {
                    near = d;
                }
            }
            terms.add(Term::FocalLocus, if near <= 0.12 { 0.0 } else { 0.3 });
        }
        if symmetric {
            // The whole picture mirrors across the vertical axis, not only the focal thing.
            terms.set(Term::Symmetry, mirror_mismatch(placed, &weights) / 0.1);
        }
        if let Some(focus) = self.tension("focus") {
            // Everything drawn except the ground counts; a thing read as isolated or
            // straying stands outside a concentration by definition.
            let exceptions: BTreeSet<usize> = if focus == "concentrated" {
                self.reading
                    .relations
                    .iter()
                    .filter(|r| matches!(r.kind, RelationKind::Isolated | RelationKind::Deviation))
                    .map(|r| r.a)
                    .collect()
            } else {
                BTreeSet::new()
            };
            let members: Vec<&Rect> = (0..n)
                .filter(|i| roles[*i] != Role::Field && !exceptions.contains(i))
                .map(|i| &boxes[i])
                .collect();
            if !members.is_empty() {
                let spread = spread_of(&members);
                let value = if focus == "concentrated" {
                    pos(spread - 0.22) / 0.1
                } else {
                    pos(0.3 - spread) / 0.1
                };
                terms.set(Term::Focus, value);
            }
        }
        // 余白の割合: the area outside the drawn ranges, at the shares of five and three of the nine cells.
        let drawn = drawn_area(placed, &self.sparse);
        let need = match self.tension("void") {
            Some("strong") => 5.0 / 9.0,
            Some("medium") => 3.0 / 9.0,
            _ => 0.0,
        };
        if need != 0.0 {
            terms.set(Term::Void, pos(need - (1.0 - drawn)) * 9.0 / 2.0);
        }
        let mut related: BTreeSet<(usize, usize)> = BTreeSet::new();
        for (index, relation) in self.reading.relations.iter().enumerate() {
            terms.set(
                Term::Relation(index),
                2.0 * self.relation_penalty(relation, &boxes, placed),
            );
            if matches!(
                relation.kind,
                RelationKind::Within
                    | RelationKind::Overlap
                    | RelationKind::Around
                    | RelationKind::Spreading
            ) && let Some(b) = relation.b
            {
                related.insert((relation.a.min(b), relation.a.max(b)));
            }
        }
        for i in 0..n {
            for j in i + 1..n {
                if self.sparse[i] || self.sparse[j] || related.contains(&(i, j)) {
                    continue;
                }
                if roles[i] == Role::Field || roles[j] == Role::Field {
                    continue;
                }
                let shared = cover_overlap(placed[i], placed[j]);
                if shared != 0.0 {
                    let smaller = placed[i].area().min(placed[j].area());
                    terms.add(Term::Overlap, 0.5 * shared / smaller);
                }
            }
        }
        for (i, role) in roles.iter().enumerate() {
            match role {
                Role::Field => terms.add(
                    Term::FieldSize,
                    0.5 * pos(1.0 / 3.0 - area(&boxes[i])) * 3.0,
                ),
                Role::Scattered => {
                    terms.add(Term::ScatterSize, 0.5 * pos(0.25 - area(&boxes[i])) * 4.0)
                }
                _ => {}
            }
        }
        Score {
            total: terms.total(),
            moment,
            center: (cx, cy),
            void_cells: voids.len() as f64,
            void_area: 1.0 - drawn,
        }
    }
}

/// The score of one placement and what it shows. With a bare diagonal row each
/// value is the mean over the ways it can run, so the empty cells can be a
/// fraction.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Score {
    pub total: f64,
    pub moment: f64,
    pub center: (f64, f64),
    pub void_cells: f64,
    pub void_area: f64,
}

/// The near-best placements of a work.
#[derive(Clone, Debug, PartialEq)]
pub struct Searched {
    pub best: f64,
    /// Region indices per layer, sorted by their keys.
    pub near: Vec<Vec<usize>>,
    pub combinations: u64,
}

/// One chosen placement.
#[derive(Clone, Debug, PartialEq)]
pub struct Solution {
    pub regions: Vec<usize>,
    pub score: Score,
    /// The terms of the score, in the order they are summed.
    pub terms: Vec<(String, f64)>,
}

fn term_name(term: Term, reading: &CheckedReading) -> String {
    match term {
        Term::Balance => "balance".to_owned(),
        Term::Asymmetry => "asymmetry".to_owned(),
        Term::OffAxis => "off_axis".to_owned(),
        Term::Vertical => "vertical".to_owned(),
        Term::MovingFocus => "moving_focus".to_owned(),
        Term::CenteredFocus => "centered_focus".to_owned(),
        Term::FocalLocus => "focal_locus".to_owned(),
        Term::Symmetry => "symmetry".to_owned(),
        Term::Focus => "focus".to_owned(),
        Term::Void => "void".to_owned(),
        Term::Relation(index) => {
            format!("relation{index}:{}", reading.relations[index].kind.as_str())
        }
        Term::Overlap => "overlap".to_owned(),
        Term::FieldSize => "field_size".to_owned(),
        Term::ScatterSize => "scatter_size".to_owned(),
    }
}

/// Step to the next combination, the rightmost layer first (the order of a
/// cartesian product). Returns `false` after the last one.
fn advance(digits: &mut [usize], sizes: &[usize]) -> bool {
    for position in (0..sizes.len()).rev() {
        digits[position] += 1;
        if digits[position] < sizes[position] {
            return true;
        }
        digits[position] = 0;
    }
    false
}

/// Score every combination once; seeds then choose among the near-best.
pub fn search(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
) -> Result<Searched, Unsolved> {
    search_work(&Work::new(layers, reading, background)?)
}

fn search_work(work: &Work<'_>) -> Result<Searched, Unsolved> {
    let combinations = work.combinations();
    if combinations == 0 {
        return Err(Unsolved::NoRanges);
    }
    if combinations > MAX_COMBINATIONS {
        return Err(Unsolved::Combinations(combinations));
    }
    let sizes: Vec<usize> = work.options.iter().map(Vec::len).collect();
    let choice_of = |digits: &[usize]| -> Vec<usize> {
        digits
            .iter()
            .enumerate()
            .map(|(layer, digit)| work.options[layer][*digit])
            .collect()
    };
    let mut totals = Vec::with_capacity(usize::try_from(combinations).unwrap_or_default());
    let mut terms = Terms::default();
    let mut digits = vec![0_usize; sizes.len()];
    loop {
        totals.push(work.score(&choice_of(&digits), &mut terms).total);
        if !advance(&mut digits, &sizes) {
            break;
        }
    }
    let best = totals.iter().copied().fold(f64::INFINITY, f64::min);
    let threshold = best * 1.03 + 0.02;
    let mut near = Vec::new();
    let mut digits = vec![0_usize; sizes.len()];
    for total in &totals {
        if *total <= threshold {
            near.push(choice_of(&digits));
        }
        advance(&mut digits, &sizes);
    }
    near.sort_by(|x, y| {
        x.iter()
            .map(|i| region_key(*i))
            .cmp(y.iter().map(|i| region_key(*i)))
    });
    Ok(Searched {
        best,
        near,
        combinations,
    })
}

/// The answer a seed picks among `count`: the work's digest says where to start,
/// and consecutive seeds walk through the answers, so they differ when they can.
fn pick_index(seed: u64, work_id: &str, count: usize) -> usize {
    let digest = Sha256::digest(work_id.as_bytes());
    let start = u128::from(u64::from_be_bytes(
        digest[..8]
            .try_into()
            .expect("a SHA-256 digest has eight bytes"),
    ));
    let count = count as u128;
    let index = (start % count + u128::from(seed) % count + count - 1) % count;
    usize::try_from(index).expect("an index below the number of answers")
}

/// Choose one of the near-best placements: consecutive seeds walk through them.
pub fn solve(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
    searched: &Searched,
    seed: u64,
    work_id: &str,
) -> Result<Solution, Unsolved> {
    solve_work(
        &Work::new(layers, reading, background)?,
        searched,
        seed,
        work_id,
    )
}

fn solve_work(
    work: &Work<'_>,
    searched: &Searched,
    seed: u64,
    work_id: &str,
) -> Result<Solution, Unsolved> {
    let regions = searched.near[pick_index(seed, work_id, searched.near.len())].clone();
    let mut terms = Terms::default();
    let score = work.score(&regions, &mut terms);
    let terms = terms
        .0
        .iter()
        .map(|(term, value)| (term_name(*term, work.reading), *value))
        .collect();
    Ok(Solution {
        regions,
        score,
        terms,
    })
}

/// A placement with joints: every layer's range, the order to print the layers
/// in, and the joint each joined layer is printed with.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Jointed {
    pub regions: Vec<usize>,
    /// Each joined layer right after its partner; the other layers keep their order.
    pub order: Vec<usize>,
    /// The joint of each joined layer, by layer.
    pub joints: Vec<Option<JointKind>>,
}

/// Place a work's joints (I-711 stage C). A joined layer keeps its range in
/// `solution`, the placement without joints: the range sets how far the layer
/// spreads, and the joint moves it to its partner when the work is drawn. The
/// other layers are placed again without the joined layers: a partner weighs
/// with the layers joined to it, keeps only the ranges where its group (its
/// range and the joined ranges placed by their joints) lies on the canvas when
/// there is one, and is scored as the group. Without joints, or when that
/// placement cannot be solved, `solution` is kept as it is.
#[must_use]
pub fn join(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
    solution: &Solution,
    seed: u64,
    work_id: &str,
) -> Jointed {
    let count = layers.len();
    let plain = Jointed {
        regions: solution.regions.clone(),
        order: (0..count).collect(),
        joints: vec![None; count],
    };
    let (joints, _) = check_joints(&reading.joints, layers, &reading.fixed);
    if joints.is_empty() || solution.regions.len() != count {
        return plain;
    }
    let attached: BTreeMap<usize, Joint> = joints.iter().map(|joint| (joint.a, *joint)).collect();
    let table = regions();
    let Some(group) = grouped(layers, reading, &attached, background, |a| {
        Some(table.all[solution.regions[a]].rect)
    }) else {
        return plain;
    };
    let Ok(work) = Work::with_edge_joints(
        &group.layers,
        &group.reading,
        background,
        &group.edge_joints,
        &group.jointed(),
    ) else {
        return plain;
    };
    let work = work.with_joined(group.joined);
    let Ok(searched) = search_work(&work) else {
        return plain;
    };
    let Ok(placed) = solve_work(&work, &searched, seed, work_id) else {
        return plain;
    };
    let mut regions = solution.regions.clone();
    for (new, old) in group.keep.iter().enumerate() {
        regions[*old] = placed.regions[new];
    }
    Jointed {
        regions,
        order: print_order(count, &attached),
        joints: (0..count)
            .map(|i| attached.get(&i).map(|joint| joint.kind))
            .collect(),
    }
}

/// A work taken apart at its joints: the layers placed again (`keep`, in their
/// order) with their reading, the layers joined to each of them, and whether
/// each of them is the partner of a joint that rests on or crosses.
struct Grouped {
    keep: Vec<usize>,
    layers: Vec<WorkPlanLayer>,
    reading: CheckedReading,
    joined: Vec<Vec<Joined>>,
    edge_joints: Vec<bool>,
}

impl Grouped {
    /// Whether each layer placed again is in a joint: the partners, which the
    /// joined layers lead to.
    fn jointed(&self) -> Vec<bool> {
        self.joined
            .iter()
            .map(|joined| !joined.is_empty())
            .collect()
    }
}

/// Take a work apart at its joints (`attached`, by joined layer): a joined layer
/// joins the group of the layer its partners lead to, with the size of its
/// extent in the range `range` gives it. `None` when a joined layer has no range.
fn grouped(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    attached: &BTreeMap<usize, Joint>,
    background: &str,
    range: impl Fn(usize) -> Option<Rect>,
) -> Option<Grouped> {
    let keep: Vec<usize> = (0..layers.len())
        .filter(|i| !attached.contains_key(i))
        .collect();
    let position: BTreeMap<usize, usize> = keep
        .iter()
        .enumerate()
        .map(|(new, old)| (*old, new))
        .collect();
    let background_lightness = lightness(Some(background), 0.99);
    let mut joined = vec![Vec::new(); keep.len()];
    for (a, joint) in attached {
        let mut root = joint.b;
        while let Some(next) = attached.get(&root) {
            root = next.b;
        }
        let extent = effective(&layers[*a], &range(*a)?);
        let (tone, surface, fixed_weight) = weight_parts(&layers[*a], background_lightness);
        joined[position[&root]].push(Joined {
            kind: joint.kind,
            width: extent[2] - extent[0],
            height: extent[3] - extent[1],
            fixed_weight,
            fill: layers[*a].action == "fill",
            tone,
            surface,
        });
    }
    let edge_joints = at_edge_joints(attached.values(), layers.len());
    Some(Grouped {
        layers: keep.iter().map(|i| layers[*i].clone()).collect(),
        reading: reduce_reading(reading, &keep),
        edge_joints: keep.iter().map(|i| edge_joints[*i]).collect(),
        keep,
        joined,
    })
}

/// [`grouped`] for instructions read back (I-711 C6): the reading's joints the
/// composition can write, each joined layer with the range its sentence writes.
fn grouped_by_bounds(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    background: &str,
    bounds: &[Option<[(u64, u64); 4]>],
) -> Result<Grouped, Unsolved> {
    let (joints, _) = check_joints(&reading.joints, layers, &reading.fixed);
    let attached: BTreeMap<usize, Joint> = joints.iter().map(|joint| (joint.a, *joint)).collect();
    grouped(layers, reading, &attached, background, |a| {
        rect_of_bounds(bounds.get(a).copied().flatten()?)
    })
    .ok_or(Unsolved::NoRanges)
}

/// The reading of the layers in `keep`, renumbered: a relation that names a
/// layer outside `keep` is left out.
fn reduce_reading(reading: &CheckedReading, keep: &[usize]) -> CheckedReading {
    let position: BTreeMap<usize, usize> = keep
        .iter()
        .enumerate()
        .map(|(new, old)| (*old, new))
        .collect();
    let renumber = |index: Option<usize>| match index {
        None => Some(None),
        Some(index) => position.get(&index).map(|new| Some(*new)),
    };
    let relations = reading
        .relations
        .iter()
        .filter_map(|relation| {
            Some(Relation {
                a: *position.get(&relation.a)?,
                b: renumber(relation.b)?,
                c: renumber(relation.c)?,
                ..relation.clone()
            })
        })
        .collect();
    CheckedReading {
        roles: keep.iter().map(|i| reading.roles[*i]).collect(),
        relations,
        tension: reading.tension.clone(),
        fixed: reading
            .fixed
            .iter()
            .filter_map(|(index, place)| Some((*position.get(index)?, place.clone())))
            .collect(),
        joints: Vec::new(),
        pinned: reading
            .pinned
            .iter()
            .filter_map(|(index, boxes)| Some((*position.get(index)?, boxes.clone())))
            .collect(),
    }
}

/// Each joined layer right after its partner, in the order of the layers.
fn print_order(count: usize, attached: &BTreeMap<usize, Joint>) -> Vec<usize> {
    let mut children: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for (a, joint) in attached {
        children.entry(joint.b).or_default().push(*a);
    }
    let mut order = Vec::with_capacity(count);
    let mut stack: Vec<usize> = (0..count)
        .rev()
        .filter(|i| !attached.contains_key(i))
        .collect();
    while let Some(index) = stack.pop() {
        order.push(index);
        if let Some(joined) = children.get(&index) {
            stack.extend(joined.iter().rev());
        }
    }
    order
}

/// The plan with a direction on each free line the reading moves (I-715 B2):
/// rising for a layer that rises, falling for one that falls, horizontal for one
/// that flows. A free line has no set shape, so the way it moves is said by its
/// direction. Only a layer whose plan gave no direction is written, and only a
/// direction the capability table accepts for its form; the first motion the
/// reading names for a layer is the one written. The solver never reads a
/// direction, so the placement is the same before and after.
#[must_use]
pub fn with_free_line_angles(plan: &WorkPlan, reading: &CheckedReading) -> WorkPlan {
    let mut plan = plan.clone();
    for relation in &reading.relations {
        let angle = match relation.kind {
            RelationKind::Rising => "rising",
            RelationKind::Falling => "falling",
            RelationKind::Flowing => "horizontal",
            _ => continue,
        };
        let Some(layer) = plan.layers.get_mut(relation.a) else {
            continue;
        };
        if layer.shape == "free_line"
            && !layer.attributes.contains_key(&WorkPlanSlot::Angle)
            && work_plan_capabilities().accepts(&layer.form(), WorkPlanSlot::Angle, angle)
        {
            layer
                .attributes
                .insert(WorkPlanSlot::Angle, angle.to_owned());
        }
    }
    plan
}

/// [`composed_plan`] for a placement with joints: the layers and their ranges
/// in print order, with the Score relation each joined layer is printed with.
#[must_use]
pub fn composed_plan_with_joints(
    plan: &WorkPlan,
    jointed: &Jointed,
) -> (
    WorkPlan,
    Vec<Option<ComposedRange>>,
    Vec<Option<&'static str>>,
) {
    let (mut composed, ranges) = composed_plan(plan, &jointed.regions);
    let layers = std::mem::take(&mut composed.layers);
    composed.layers = jointed.order.iter().map(|i| layers[*i].clone()).collect();
    let ranges = jointed.order.iter().map(|i| ranges[*i].clone()).collect();
    let relations = jointed
        .order
        .iter()
        .map(|i| jointed.joints[*i].map(JointKind::relation_type))
        .collect();
    (composed, ranges, relations)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fractions_compare_exactly_and_round_once() {
        assert!(frac(1, 3) < frac(1, 2));
        assert_eq!(Frac::new(2, 6), frac(1, 3));
        assert_eq!(Frac::new(3, -6), frac(-1, 2));
        assert_eq!((frac(1, 3) + frac(1, 6)).f(), 0.5);
        assert_eq!(frac(1, 3).f(), 1.0 / 3.0);
    }

    #[test]
    fn the_sum_is_compensated() {
        assert_eq!(sum([0.1; 10]), 1.0);
        assert_eq!(sum(std::iter::empty()), 0.0);
    }

    #[test]
    fn the_hypotenuse_is_exact_for_whole_triangles() {
        assert_eq!(hypot(3.0, 4.0), 5.0);
        assert_eq!(hypot(0.0, 0.0), 0.0);
        assert_eq!(hypot(-0.6, 0.8), 1.0);
    }

    #[test]
    fn words_of_position_are_found_and_scene_words_are_not() {
        for words in [
            "右下の隅",
            "駅の壁の中央",
            "上に神社",
            "At the very top",
            "Above the field",
        ] {
            assert!(names_a_position(words), "{words}");
        }
        for words in [
            "from the chimney",
            "川面に",
            "香具山",
            "残り火がひとつ",
            "half buried in sand",
            "sits low",
        ] {
            assert!(!names_a_position(words), "{words}");
        }
    }

    fn plan_layer(action: &str, shape: &str, position: Option<&str>) -> WorkPlanLayer {
        let mut layer = WorkPlanLayer {
            shape: shape.into(),
            action: action.into(),
            count: 1,
            ..WorkPlanLayer::default()
        };
        if let Some(position) = position {
            layer
                .attributes
                .insert(WorkPlanSlot::Position, position.into());
        }
        layer
    }

    /// I-712: the plan can only say "corner"; a corner the description names is
    /// kept over it and solved to that corner, while "corner" alone still lets the
    /// composition choose among the four.
    #[test]
    fn a_named_corner_is_kept_over_the_plans_corner_and_solved_there() {
        let layers = [
            plan_layer("fill", "square", None),
            plan_layer("place", "ellipse", Some("corner")),
        ];
        let reading = |place: &str| RawReading {
            roles: vec!["field".into(), "focal".into()],
            stated_places: vec![(
                "1".into(),
                RawStatedPlace {
                    words: Some("右下の隅には".into()),
                    place: Some(place.into()),
                },
            )],
            ..RawReading::default()
        };
        let quoted = |_: usize, _: &str| true;
        let (named, findings) =
            check(&reading("bottom_right_corner"), &layers, Some(&quoted)).expect("checked");
        assert_eq!(
            named.fixed.get(&1).map(String::as_str),
            Some("bottom_right_corner")
        );
        let codes: Vec<&str> = findings.iter().map(|finding| finding.code).collect();
        assert!(codes.contains(&"stated_corner_from_reading"), "{codes:?}");
        let searched = search(&layers, &named, "white").expect("searched");
        for seed in [1, 2, 3] {
            let solution =
                solve(&layers, &named, "white", &searched, seed, "work").expect("solved");
            assert_eq!(region_key(solution.regions[1]), "corner-br", "seed {seed}");
        }
        let (plain, _) = check(&reading("corner"), &layers, Some(&quoted)).expect("checked");
        assert_eq!(plain.fixed.get(&1).map(String::as_str), Some("corner"));
        // A named corner off the plan place's side (a reading may tie the words to
        // the wrong layer) leaves the plan's place; one on its side refines it.
        for (plan, kept, code) in [
            ("center", "center", "stated_corner_conflict"),
            (
                "bottom_edge",
                "bottom_right_corner",
                "stated_corner_from_reading",
            ),
        ] {
            let layers = [
                plan_layer("fill", "square", None),
                plan_layer("place", "ellipse", Some(plan)),
            ];
            let (checked, findings) =
                check(&reading("bottom_right_corner"), &layers, Some(&quoted)).expect("checked");
            assert_eq!(
                checked.fixed.get(&1).map(String::as_str),
                Some(kept),
                "{plan}"
            );
            let codes: Vec<&str> = findings.iter().map(|finding| finding.code).collect();
            assert!(codes.contains(&code), "{plan}: {codes:?}");
        }
    }

    /// I-711 C5: the reading's joints are checked in the reply's order once the
    /// stated places are fixed, and each one dropped leaves a finding.
    #[test]
    fn the_joints_a_composition_cannot_write_are_dropped_with_a_finding() {
        let layers = [
            plan_layer("fill", "square", None),
            plan_layer("place", "circle", None),
            plan_layer("place", "ellipse", Some("bottom")),
        ];
        let joint = |kind: &str, layers: &[u64], words: &str| {
            let layers = Value::from(layers.to_vec());
            serde_json::json!({"type": kind, "layers": layers, "words": words})
        };
        let reading = RawReading {
            roles: vec!["field".into(), "focal".into(), "secondary".into()],
            stated_places: vec![(
                "2".into(),
                RawStatedPlace {
                    words: Some("at the bottom".into()),
                    place: Some("bottom".into()),
                },
            )],
            joints: vec![
                joint("rests_on", &[1, 0], "on the hill"),
                joint("touches", &[1, 0], "on the hill"),
                joint("inside", &[1], "on the hill"),
                joint("inside", &[1, 3], "on the hill"),
                joint("inside", &[1, 1], "on the hill"),
                Value::from("rests_on"),
                joint("overlaps", &[2, 0], ""),
                joint("overlaps", &[2, 0], "in the sky"),
                joint("overlaps", &[2, 0], "on the hill"),
            ],
            ..RawReading::default()
        };
        let description = "a circle on the hill and a stone at the bottom";
        let asked = std::cell::RefCell::new(Vec::new());
        let quoted = |i: usize, words: &str| {
            asked.borrow_mut().push(i);
            description.contains(words)
        };
        let (checked, findings) = check(&reading, &layers, Some(&quoted)).expect("checked");
        let rests_on = Joint {
            kind: JointKind::RestsOn,
            a: 1,
            b: 0,
        };
        assert_eq!(checked.joints, [rests_on]);
        let found: Vec<(&str, &str)> = findings
            .iter()
            .map(|finding| (finding.code, finding.item.as_str()))
            .collect();
        assert_eq!(
            found,
            [
                ("joint_layer", "joints.1"),
                ("joint_layer", "joints.2"),
                ("joint_layer", "joints.3"),
                ("joint_layer", "joints.4"),
                ("joint_layer", "joints.5"),
                ("joint_unquoted", "joints.6"),
                ("joint_unquoted", "joints.7"),
                ("joint_stated", "overlapping 2->0"),
            ]
        );
        // The stated place is quote 0; the k-th joint is quote 1 + k.
        assert_eq!(*asked.borrow(), [0, 1, 8, 9]);
        // Without a quote test the words are not looked at; the layers still are.
        let unquoted = RawReading {
            joints: vec![
                joint("crosses", &[1, 0], "in the sky"),
                joint("crosses", &[1, 9], "on the hill"),
            ],
            ..reading
        };
        let (checked, findings) = check(&unquoted, &layers, None).expect("checked");
        assert_eq!(
            checked.joints,
            [Joint {
                kind: JointKind::Crosses,
                ..rests_on
            }]
        );
        let codes: Vec<&str> = findings.iter().map(|finding| finding.code).collect();
        assert_eq!(codes, ["joint_layer"]);
    }

    /// I-711 C6: by chance, a partner that a layer a third of the canvas tall
    /// rests on takes only ranges where that layer, sitting on its top edge,
    /// stays on the canvas, so never a range at the top; without the joint the
    /// same partner takes one for some seeds.
    #[test]
    fn by_chance_a_partner_with_a_layer_resting_on_it_keeps_off_the_top() {
        let layers = [
            plan_layer("place", "square", None),
            plan_layer("place", "circle", None),
        ];
        let mut reading = default_reading(&layers);
        reading.joints = vec![Joint {
            kind: JointKind::RestsOn,
            a: 1,
            b: 0,
        }];
        // The circle keeps the top center its sentence writes.
        let bounds = [None, Some([(1, 3), (0, 1), (2, 3), (1, 3)])];
        let at_top = |index: usize| regions().all[index].rect[1] == Frac::ZERO;
        let mut alone_at_top = 0;
        for seed in 1..=20 {
            let joined = chance_joined_answer(&layers, &reading, "white", &bounds, seed, "work")
                .expect("chosen");
            assert_eq!(joined.len(), 1, "seed {seed}");
            assert!(!at_top(joined[0]), "seed {seed}: {}", region_key(joined[0]));
            let alone = chance_answer(&layers, &reading, seed, "work").expect("chosen");
            if at_top(alone[0]) {
                alone_at_top += 1;
            }
        }
        assert!(alone_at_top > 0, "{alone_at_top}");
    }

    #[test]
    fn the_regions_are_the_twenty_eight_ranges_seven_names_and_four_corners() {
        let table = regions();
        assert_eq!(table.composed.len(), 28);
        assert_eq!(table.all.len(), 39);
        assert_eq!(region_key(table.composed[0]), "cell-00");
        assert!(named_region("corner").is_none());
        let corners: Vec<&str> = stated_regions("corner")
            .expect("a corner is one of four cells")
            .into_iter()
            .map(region_key)
            .collect();
        assert_eq!(
            corners,
            ["corner-tl", "corner-tr", "corner-bl", "corner-br"]
        );
        for (name, key) in NAMED_CORNERS {
            let chosen: Vec<&str> = stated_regions(name)
                .expect("a named corner is one cell")
                .into_iter()
                .map(region_key)
                .collect();
            assert_eq!(chosen, [key], "{name}");
        }
    }

    const ROLES: [Role; 5] = [
        Role::Field,
        Role::Focal,
        Role::Secondary,
        Role::Scattered,
        Role::Accent,
    ];
    const PROPORTIONS: [Option<&str>; 4] = [None, Some("full_width"), Some("wide"), Some("tall")];

    fn shaped(action: &str, proportion: Option<&str>) -> WorkPlanLayer {
        let mut layer = plan_layer(action, "square", None);
        layer.count = 5;
        layer.proportion = proportion.map(str::to_owned);
        layer
    }

    /// The author's decision of 2026-10-19: a fill cuts its marks at the edge of
    /// its range, so a fill without a fixed place keeps the whole canvas, in any
    /// role and of any proportion. A stated place is kept.
    #[test]
    fn a_fill_without_a_fixed_place_keeps_the_whole_canvas() {
        let whole = Some(vec![region_index("whole").expect("the whole canvas")]);
        for proportion in PROPORTIONS {
            let fill = shaped("fill", proportion);
            for role in ROLES {
                assert_eq!(
                    candidates(&fill, role, None, false),
                    whole,
                    "{role:?} {proportion:?}"
                );
            }
            assert_eq!(
                candidates(&fill, Role::Field, Some("top"), false),
                stated_regions("top"),
                "{proportion:?}"
            );
        }
    }

    /// A fill on either side of a joint that rests on or crosses takes the
    /// ranges it took before (those of a tile of its proportion), both when the
    /// work is solved with its joints and when it is taken apart at them; a fill
    /// joined by another joint keeps the whole canvas.
    #[test]
    fn a_fill_on_either_side_of_a_joint_that_rests_on_or_crosses_keeps_its_ranges() {
        for proportion in PROPORTIONS {
            let (fill, tile) = (shaped("fill", proportion), shaped("tile", proportion));
            for role in ROLES {
                assert_eq!(
                    candidates(&fill, role, None, true),
                    candidates(&tile, role, None, false),
                    "{role:?} {proportion:?}"
                );
            }
        }
        let before = |role: Role| {
            candidates(&shaped("tile", Some("wide")), role, None, false).expect("ranges")
        };
        let joint = |kind: JointKind, a: usize, b: usize| Joint { kind, a, b };
        // A circle rests on the first band, the second band crosses a square and
        // the third overlaps an ellipse.
        let layers = [
            shaped("fill", Some("wide")),
            plan_layer("place", "circle", None),
            shaped("fill", Some("wide")),
            plan_layer("place", "square", None),
            shaped("fill", Some("wide")),
            plan_layer("place", "ellipse", None),
        ];
        let reading = CheckedReading {
            roles: vec![
                Role::Field,
                Role::Focal,
                Role::Secondary,
                Role::Secondary,
                Role::Secondary,
                Role::Secondary,
            ],
            joints: vec![
                joint(JointKind::RestsOn, 1, 0),
                joint(JointKind::Crosses, 2, 3),
                joint(JointKind::Overlaps, 4, 5),
            ],
            ..CheckedReading::default()
        };
        let work = Work::new(&layers, &reading, "white").expect("a work");
        assert_eq!(work.options[0], before(Role::Field));
        assert_eq!(work.options[2], before(Role::Secondary));
        assert_eq!(
            work.options[4],
            [region_index("whole").expect("the whole canvas")]
        );
        let attached: BTreeMap<usize, Joint> = reading
            .joints
            .iter()
            .map(|joint| (joint.a, *joint))
            .collect();
        let group =
            grouped(&layers, &reading, &attached, "white", |_| Some(WHOLE)).expect("grouped");
        assert_eq!(group.keep, [0, 3, 5]);
        assert_eq!(group.edge_joints, [true, true, false]);
        let work = Work::with_edge_joints(
            &group.layers,
            &group.reading,
            "white",
            &group.edge_joints,
            &group.jointed(),
        )
        .expect("a work");
        assert_eq!(work.options[0], before(Role::Field));
    }

    /// Every layer but a fill without a fixed place keeps its ranges: a joint
    /// changes none of them, a tile of the field keeps the large ranges and a
    /// scattered layer the composition ranges.
    #[test]
    fn every_other_layer_keeps_its_ranges() {
        for action in ["draw", "line_up", "place", "scatter", "tile"] {
            for proportion in PROPORTIONS {
                let layer = shaped(action, proportion);
                for role in ROLES {
                    assert_eq!(
                        candidates(&layer, role, None, true),
                        candidates(&layer, role, None, false),
                        "{action} {role:?} {proportion:?}"
                    );
                }
            }
        }
        let table = regions();
        assert_eq!(
            candidates(&shaped("tile", None), Role::Field, None, false),
            Some(table.large.clone())
        );
        assert_eq!(
            candidates(&shaped("scatter", None), Role::Scattered, None, false),
            Some(table.composed.clone())
        );
    }

    fn diagonal_row(direction: &str) -> WorkPlanLayer {
        let mut layer = plan_layer("line_up", "circle", None);
        layer.count = 5;
        layer
            .attributes
            .insert(WorkPlanSlot::LineUpDirection, direction.into());
        layer
    }

    fn range_rect(key: &str) -> Rect {
        regions().all[region_index(key).expect(key)].rect
    }

    /// The author's decision of 2026-10-19: the compiler runs a diagonal row on
    /// the chord through its range's centre at 45 degrees, so the solver weighs
    /// it by that chord: the chord's box, and the squares a sixth of the canvas
    /// wide that it crosses corner to corner.
    #[test]
    fn a_diagonal_row_is_weighed_by_its_chord() {
        let (zero, one) = (Frac::ZERO, Frac::ONE);
        // The top right cell: falling, the cell's own diagonal; rising, the canvas's.
        let falling = chord_footprint(&range_rect("cell-20"), true);
        assert_eq!(falling.extent, range_rect("cell-20"));
        assert_eq!(
            falling.cover,
            [
                [frac(2, 3), zero, frac(5, 6), frac(1, 6)],
                [frac(5, 6), frac(1, 6), one, frac(1, 3)],
            ]
        );
        let rising = chord_footprint(&range_rect("cell-20"), false);
        assert_eq!(rising.extent, WHOLE);
        assert_eq!(rising.cover.len(), 6);
        assert_eq!(rising.cover[0], [zero, frac(5, 6), frac(1, 6), one]);
        assert_eq!(rising.cover[5], [frac(5, 6), zero, one, frac(1, 6)]);
        // The top centre cell runs two thirds of the canvas either way.
        assert_eq!(
            chord_footprint(&range_rect("cell-10"), true).extent,
            [frac(1, 3), zero, one, frac(2, 3)]
        );
        assert_eq!(
            chord_footprint(&range_rect("cell-10"), false).extent,
            [zero, zero, frac(2, 3), frac(2, 3)]
        );
        // A stated corner, a fifth of the canvas: the last square is cut at the edge.
        assert_eq!(
            chord_footprint(&range_rect("corner-tr"), true).cover,
            [
                [frac(4, 5), zero, frac(29, 30), frac(1, 6)],
                [frac(29, 30), frac(1, 6), one, frac(1, 5)],
            ]
        );
        assert_eq!(
            chord_footprint(&range_rect("named-right_edge"), true).extent,
            [frac(9, 20), zero, one, frac(11, 20)]
        );
        // Every range, either way: the chord passes through the range's centre,
        // ends on the canvas's edges, and its squares follow it end to end.
        let on_edge = |x: Frac, y: Frac| x == zero || x == one || y == zero || y == one;
        for region in &regions().all {
            let (cx, cy) = exact_center(&region.rect);
            for falling in [true, false] {
                let footprint = chord_footprint(&region.rect, falling);
                let [left, top, right, bottom] = footprint.extent;
                let (start, end) = if falling {
                    ((left, top), (right, bottom))
                } else {
                    ((left, bottom), (right, top))
                };
                let through = if falling {
                    cy - start.1 == cx - start.0
                } else {
                    start.1 - cy == cx - start.0
                };
                assert!(through, "{} {falling}", region.key);
                assert!(
                    on_edge(start.0, start.1) && on_edge(end.0, end.1),
                    "{}",
                    region.key
                );
                assert!(zero <= left && right <= one && zero <= top && bottom <= one);
                let mut at = start;
                for square in &footprint.cover {
                    let width = square[2] - square[0];
                    assert!(
                        width <= SIXTH && square[3] - square[1] == width,
                        "{}",
                        region.key
                    );
                    let next = if falling {
                        (square[2], at.1 + width)
                    } else {
                        (square[2], at.1 - width)
                    };
                    assert_eq!(square[0], at.0, "{}", region.key);
                    assert_eq!((square[1], square[3]), (at.1.min(next.1), at.1.max(next.1)));
                    at = next;
                }
                assert_eq!(at, end, "{}", region.key);
            }
        }
    }

    /// A bare diagonal row runs either way, as the compiler chooses, so a
    /// placement with one scores the mean of its two ways: each term, the
    /// centre and the empty cells, with the total the sum of the terms.
    #[test]
    fn a_bare_diagonal_row_weighs_the_mean_of_its_two_ways() {
        let at = |key: &str| region_index(key).expect(key);
        // Alone in the top right cell: falling it keeps to the cell (eight empty
        // cells, two squares), rising it crosses the canvas (six, six squares).
        let alone = |direction: &str| {
            let layers = [diagonal_row(direction)];
            let reading = default_reading(&layers);
            let work = Work::new(&layers, &reading, "white").expect("a work");
            work.score(&[at("cell-20")], &mut Terms::default())
        };
        let (falling, rising, either) = (alone("falling"), alone("rising"), alone("diagonal"));
        assert_eq!(
            (falling.void_cells, rising.void_cells, either.void_cells),
            (8.0, 6.0, 7.0)
        );
        assert_eq!(falling.void_area, 1.0 - 2.0 / 36.0);
        assert_eq!(rising.void_area, 1.0 - 6.0 / 36.0);
        assert_eq!(
            either.void_area,
            sum([falling.void_area, rising.void_area]) / 2.0
        );
        // With another layer, relations on the row's marks and a symmetric
        // reading, every term is the mean of the two ways.
        let reading = CheckedReading {
            roles: vec![Role::Secondary, Role::Focal],
            relations: vec![
                Relation {
                    kind: RelationKind::Near,
                    a: 1,
                    b: Some(0),
                    c: None,
                    side: None,
                    toward: None,
                },
                Relation {
                    kind: RelationKind::Deviation,
                    a: 0,
                    b: Some(1),
                    c: None,
                    side: None,
                    toward: None,
                },
            ],
            tension: [("symmetry".to_owned(), "symmetric".to_owned())].into(),
            ..CheckedReading::default()
        };
        let scored = |direction: &str| {
            let layers = [diagonal_row(direction), plan_layer("place", "square", None)];
            let work = Work::new(&layers, &reading, "white").expect("a work");
            let mut terms = Terms::default();
            let score = work.score(&[at("cell-12"), at("cell-00")], &mut terms);
            (score, terms.0)
        };
        let ((falling, falling_terms), (rising, rising_terms), (either, either_terms)) =
            (scored("falling"), scored("rising"), scored("diagonal"));
        let mean = |a: f64, b: f64| sum([a, b]) / 2.0;
        let value = |terms: &[(Term, f64)], term: Term| {
            terms
                .iter()
                .find(|(found, _)| *found == term)
                .map_or(0.0, |(_, value)| *value)
        };
        let mut expected: Vec<(Term, f64)> = Vec::new();
        for (term, _) in falling_terms.iter().chain(&rising_terms) {
            if expected.iter().all(|(seen, _)| seen != term) {
                let both = mean(value(&falling_terms, *term), value(&rising_terms, *term));
                expected.push((*term, both));
            }
        }
        assert_ne!(falling_terms, rising_terms);
        assert_eq!(either_terms, expected);
        assert_eq!(either.total, Terms(expected).total());
        assert_eq!(
            either.center,
            (
                mean(falling.center.0, rising.center.0),
                mean(falling.center.1, rising.center.1)
            )
        );
        assert_eq!(either.moment, mean(falling.moment, rising.moment));
    }

    /// Ranges with one centre draw a diagonal row alike, so it keeps the first
    /// of each; a diagonal row in a joint keeps every range and its range's
    /// box, and every other layer keeps its ranges.
    #[test]
    fn a_diagonal_row_keeps_one_range_per_centre() {
        let table = regions();
        let kept = |layer: &WorkPlanLayer, role: Role| {
            one_per_center(layer, candidates(layer, role, None, false).expect("ranges"))
        };
        let centres = |options: &[usize]| {
            options
                .iter()
                .map(|index| exact_center(&table.all[*index].rect))
                .collect::<BTreeSet<_>>()
                .len()
        };
        for direction in ["diagonal", "falling", "rising"] {
            let row = diagonal_row(direction);
            for (role, count) in [(Role::Focal, 13), (Role::Field, 13), (Role::Secondary, 21)] {
                let options = kept(&row, role);
                assert_eq!(options.len(), count, "{direction} {role:?}");
                assert_eq!(centres(&options), count, "{direction} {role:?}");
            }
        }
        let keys = |role: Role| -> Vec<&str> {
            kept(&diagonal_row("diagonal"), role)
                .into_iter()
                .map(region_key)
                .collect()
        };
        let secondary = keys(Role::Secondary);
        assert!(secondary.contains(&"cell-11") && !secondary.contains(&"whole"));
        assert!(secondary.contains(&"cell-10") && !secondary.contains(&"hband-0"));
        let field = keys(Role::Field);
        assert!(field.contains(&"hband-1") && !field.contains(&"vband-1"));
        assert!(!field.contains(&"whole"));
        // Every other line-up, a diagonal row of one mark, and the other actions.
        let mut layers: Vec<WorkPlanLayer> = ["horizontal", "vertical"]
            .into_iter()
            .map(diagonal_row)
            .collect();
        let mut plain = diagonal_row("diagonal");
        plain.attributes.remove(&WorkPlanSlot::LineUpDirection);
        layers.push(plain);
        let mut one = diagonal_row("diagonal");
        one.count = 1;
        layers.push(one);
        for action in ["draw", "place", "scatter", "tile", "fill"] {
            layers.push(shaped(action, None));
        }
        for layer in &layers {
            for role in ROLES {
                let options = candidates(layer, role, None, false).expect("ranges");
                assert_eq!(one_per_center(layer, options.clone()), options);
            }
        }
        // In a joint, a diagonal row keeps every range and its range's box.
        let cell = region_index("cell-20").expect("a cell");
        let rect = table.all[cell].rect;
        let layers = [
            diagonal_row("diagonal"),
            plan_layer("place", "square", None),
        ];
        let jointed = CheckedReading {
            roles: vec![Role::Secondary, Role::Secondary],
            joints: vec![Joint {
                kind: JointKind::Overlaps,
                a: 1,
                b: 0,
            }],
            ..CheckedReading::default()
        };
        let work = Work::new(&layers, &jointed, "white").expect("a work");
        assert_eq!(work.options[0], table.composed);
        assert_eq!(work.footprints[0][cell], [Footprint::whole(rect)]);
        let alone = CheckedReading {
            joints: Vec::new(),
            ..jointed
        };
        let work = Work::new(&layers, &alone, "white").expect("a work");
        assert_eq!(work.options[0].len(), 21);
        assert_eq!(
            work.footprints[0][cell],
            [chord_footprint(&rect, true), chord_footprint(&rect, false)]
        );
    }
}
