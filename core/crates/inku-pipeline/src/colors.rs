//! The color stage (`choose_colors`), after the laws stage (2026-10-20).
//!
//! Once the laws have placed a work's layers, a reader chooses laws of color
//! for the work and the values each takes, from eighteen: the eleven color
//! laws the laws stage gave up (B11, B13, B14, B16 to B20, C7 to C9) and seven
//! more (D1 to D7). The core applies them to a copy of the Score and prints the
//! layers they change again: a color word, colors in turn or shifting, a fade,
//! a handling, a numeric size, and the copies a kasane lays under a layer.
//!
//! The computation is the color stage prototype's (color-stage2-20261019) with
//! the author's decisions of 2026-10-19 and 2026-10-20. The tool decides the
//! colors the description states and never changes them (F0). Hue relations
//! go by the places the actual paints take on Itten's wheel (F1). A law that
//! already holds in the picture is not offered as the main law (F2). Where the
//! tool chooses colors, it takes the combination that recolors the main layer
//! first, and among those the one of the highest harmony (F3). The ground
//! stays as it is (V1), so C8 takes no ground and C9 only enlarges the main
//! layer. The lightness laws (B19, D7) and whether a layer is seen are checked
//! with the drawn difference from the ground, which the core estimates from
//! the renderer's SVG ([`crate::appearance`]); the prototype checked B19 and D7
//! with the table's lightness. A plugin sentence prints no color, so its layer
//! keeps its own.

use std::collections::{BTreeMap, BTreeSet};

use inku_ddl::work_plan::{
    ComposedRange, NumericPlace, NumericWriting, WorkPlan, WorkPlanPlugin, WorkPlanSlot,
    print_work_plan_with_numbers,
};
use inku_ddl::{FadeDirection, ResolvedInstructionLanguage};
use inku_score::{Color, Fade, Instruction, Primitive, Score, SurfaceIntensity};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::appearance::{Drawing, Look, Painter, Seeds, Shares, lab_of};
use crate::core_boundary::ResolvedPaletteDto;
use crate::laws::{
    self, COLORS, Chosen, ComposedPlan, LawsPrint, Refusal, Units, conform, count_of, layer_number,
    refusal,
};
use crate::prompts::{LlmPrompt, LlmStage, PromptError, PromptLimits};

/// The color request edition.
pub const COLORS_PROMPT_ID: &str = "inku.colors-prompt.v1";

/// The color laws, in the order the request lists them.
pub const COLOR_LAWS: [&str; 18] = [
    "B11", "B13", "B14", "B16", "B17", "B18", "B19", "B20", "C7", "C8", "C9", "D1", "D2", "D3",
    "D4", "D5", "D6", "D7",
];

/// The laws whose layer colors the answer's `colors` gives.
const SOURCE_LAWS: [&str; 4] = ["B17", "B18", "B19", "B20"];
/// The laws whose layer colors the tool decides.
const TOOL_LAWS: [&str; 3] = ["D1", "D5", "D7"];

/// A drawn lightness difference from the ground at least this is seen.
const VISIBLE: f64 = 0.15;
/// B19: the main layer's drawn difference from the ground at least this.
const B19_MAIN: f64 = 0.35;
/// A drawn color of at least this chroma reads as chromatic.
const CHROMATIC: f64 = 15.0;
/// D1, D2: a vivid color's table chroma at least this.
const VIVID_CHROMA: f64 = 25.0;
/// D2: another colored layer's chroma at most this share of the vivid one.
const MUTED_SHARE: f64 = 0.5;
/// B15: a distant layer the colors change stands at least this far from the
/// ground in drawn lightness (and less far than the main layer).
const AERIAL_FAR: f64 = 0.2;
/// B13, B14: a gradation runs through at least this many marks.
const GRADED_MARKS: u64 = 3;
/// D6: a scattered layer of at least this many marks, each at most this wide.
const MIX_COUNT: u64 = 6;
const MIX_SIZE: f64 = 0.08;
/// D7: neighbouring levels at least this apart, one level within this.
const LEVEL_GAP: f64 = 0.25;
const LEVEL_SPREAD: f64 = 0.10;
/// D3: a partner drawn under this chroma is gray.
const GRAY_PARTNER: f64 = 10.0;
/// B17: a color covering at least this share of the picture counts.
const SHARE_COUNTED: f64 = 0.01;
/// F3: a layer with less ink than this share of the canvas is left out.
const MIN_INK: f64 = 0.0005;
/// The hue relations on the wheel (degrees).
const APART_FAR: f64 = 90.0;
const ANALOGOUS_ARC: f64 = 120.0;
const COMPLEMENT: f64 = 150.0;
const CHORD_TOLERANCE: f64 = 30.0;
const WARM_FROM: f64 = 345.0;
const WARM_TO: f64 = 165.0;
const SAME_PLACE: f64 = 0.5;
/// A paint of OKLCH chroma under this has no place on the wheel.
const ACHROMATIC: f64 = 0.035;
/// C7: the offsets of a kasane's lower colors, in canvas fractions.
const KASANE_SMALL: f64 = 0.008;
const KASANE_MEDIUM: f64 = 0.016;
/// C9: the main layer's target areas and the largest size it may take; the
/// other layers' lightness from the ground under which they turn neutral.
const C9_SMALL: f64 = 0.22;
const C9_LARGE: f64 = 0.40;
const C9_CAP: f64 = 0.92;
const C9_NEUTRAL: f64 = 0.25;
/// B18: the scale is kept between 1/φ² and φ².
const PHI_SQUARED: f64 = 2.618_033_988_749_895;
/// The limits a Score the stage leaves keeps (the laws stage's).
const MAX_INSTRUCTIONS: usize = 60;
const MAX_MARKS: u64 = 380;
/// The tool tries every combination of the colors of the layers it decides up
/// to this many, and decides them one by one past it.
const SEARCH_LIMIT: usize = 20_000;

/// Itten's wheel in the catalog's six chromatic names.
const WHEEL: [Color; 6] = [
    Color::Yellow,
    Color::Orange,
    Color::Red,
    Color::Purple,
    Color::Blue,
    Color::Green,
];
const NEUTRAL: [Color; 3] = [Color::White, Color::Gray, Color::Black];
/// B18: the light values of Goethe, by name.
const LIGHT_VALUE: [(Color, f64); 6] = [
    (Color::Yellow, 9.0),
    (Color::Orange, 8.0),
    (Color::Red, 6.0),
    (Color::Green, 6.0),
    (Color::Blue, 4.0),
    (Color::Purple, 3.0),
];
/// The area of a closed shape over its width times its height.
const AREA: [(Primitive, f64); 6] = [
    (Primitive::Circle, std::f64::consts::FRAC_PI_4),
    (Primitive::Ellipse, std::f64::consts::FRAC_PI_4),
    (Primitive::Square, 1.0),
    (Primitive::Triangle, 0.5),
    (Primitive::Polygon, 0.65),
    (Primitive::Cloudform, 0.6),
];

fn index_of(color: Color) -> usize {
    COLORS
        .iter()
        .position(|found| *found == color)
        .expect("one of the nine colors")
}

fn color_named(name: &str) -> Option<Color> {
    COLORS.iter().copied().find(|color| color.as_str() == name)
}

fn light_value(color: Color) -> Option<f64> {
    LIGHT_VALUE
        .iter()
        .find(|(found, _)| *found == color)
        .map(|(_, value)| *value)
}

fn area_factor(primitive: Primitive) -> Option<f64> {
    AREA.iter()
        .find(|(found, _)| *found == primitive)
        .map(|(_, factor)| *factor)
}

/// Python's `round(value, 1)`.
fn round1(value: f64) -> f64 {
    format!("{value:.1}").parse().unwrap_or(value)
}

/// Python's `round(value, 9)`.
fn round9(value: f64) -> f64 {
    format!("{value:.9}").parse().unwrap_or(value)
}

// --- what the laws stage hands on --------------------------------------------------------------

/// A plan as printed before the color stage: the laws' print, or the composed
/// plan as the composition printed it. One entry in each list per printed
/// layer.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrintedPlan {
    pub plan: WorkPlan,
    pub ranges: Vec<Option<ComposedRange>>,
    pub joints: Vec<Option<String>>,
    pub numeric: Vec<Option<NumericWriting>>,
}

impl PrintedPlan {
    /// The composed plan, which prints the composed document.
    #[must_use]
    pub fn composed(composed: &ComposedPlan) -> Self {
        Self {
            plan: composed.plan.clone(),
            ranges: composed.ranges.clone(),
            joints: composed.joints.clone(),
            numeric: vec![None; composed.plan.layers.len()],
        }
    }

    /// The laws' print, which prints the laws document.
    #[must_use]
    pub fn laws(print: &LawsPrint) -> Self {
        Self {
            plan: print.plan.clone(),
            ranges: print.ranges.clone(),
            joints: print.joints.clone(),
            numeric: print.numeric.clone(),
        }
    }

    /// The document's source.
    #[must_use]
    pub fn source(
        &self,
        language: ResolvedInstructionLanguage,
        plugins: &[WorkPlanPlugin],
    ) -> String {
        let joints: Vec<Option<&str>> = self.joints.iter().map(Option::as_deref).collect();
        print_work_plan_with_numbers(
            &self.plan,
            language,
            plugins,
            &self.ranges,
            &joints,
            &self.numeric,
        )
    }

    fn first_plan_layer(&self) -> usize {
        self.plan.plugins.len()
    }
}

/// What the laws stage hands the color stage, numbered as the Score of the
/// document it printed numbers its layers: the main layer, and the layers whose
/// color it decided (aerial perspective `B15`, a pattern `C2`).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LawsHandoff {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub main_layer: Option<usize>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub fixed: BTreeMap<usize, String>,
}

impl LawsHandoff {
    /// What the chosen laws hand on: each composed layer stands for every
    /// printed layer the laws printed of it (a layer opened into marks is one
    /// sentence a mark), the main layer for the first of them.
    #[must_use]
    pub fn of(chosen: &Chosen, first_plan_layer: usize) -> Self {
        let printed = |composed: usize| {
            chosen
                .print
                .composed
                .iter()
                .enumerate()
                .filter(move |(_, k)| first_plan_layer + **k == composed)
                .map(move |(p, _)| first_plan_layer + p)
        };
        let mut fixed = BTreeMap::new();
        for (layer, laws) in &chosen.named {
            for law in laws {
                if matches!(*law, "B15" | "C2") {
                    for p in printed(*layer) {
                        fixed.insert(p, (*law).to_owned());
                    }
                }
            }
        }
        Self {
            main_layer: printed(chosen.main_layer).next(),
            fixed,
        }
    }
}

// --- the paints (F1) ---------------------------------------------------------------------------

/// The centers of the core's hue bands (OKLCH hue) and the place each takes on
/// Itten's wheel.
const BAND_CENTERS: [(f64, f64); 6] = [
    (27.5, 120.0),  // red
    (65.0, 60.0),   // orange
    (108.5, 0.0),   // yellow
    (168.5, 300.0), // green
    (240.0, 240.0), // blue
    (312.5, 180.0), // purple
];

/// The place of each chromatic name on the wheel.
fn own_place(color: Color) -> Option<f64> {
    Some(match color {
        Color::Yellow => 0.0,
        Color::Orange => 60.0,
        Color::Red => 120.0,
        Color::Purple => 180.0,
        Color::Blue => 240.0,
        Color::Green => 300.0,
        _ => return None,
    })
}

/// The twelve hues of the wheel at 30 degrees, from yellow.
const TWELVE: [[&str; 2]; 12] = [
    ["黄", "yellow"],
    ["黄橙", "yellow-orange"],
    ["橙", "orange"],
    ["赤橙", "red-orange"],
    ["赤", "red"],
    ["赤紫", "red-purple"],
    ["紫", "purple"],
    ["青紫", "blue-purple"],
    ["青", "blue"],
    ["青緑", "blue-green"],
    ["緑", "green"],
    ["黄緑", "yellow-green"],
];

/// OKLCH (L from 0 to 1, C, h in degrees) of an sRGB color.
fn oklch(rgb: [u8; 3]) -> (f64, f64, f64) {
    let linear = |channel: u8| {
        let c = f64::from(channel) / 255.0;
        if c <= 0.04045 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    };
    let lin = rgb.map(linear);
    let l = 0.412_221_470_8 * lin[0] + 0.536_332_536_3 * lin[1] + 0.051_445_992_9 * lin[2];
    let m = 0.211_903_498_2 * lin[0] + 0.680_699_545_1 * lin[1] + 0.107_396_956_6 * lin[2];
    let s = 0.088_302_461_9 * lin[0] + 0.281_718_837_6 * lin[1] + 0.629_978_700_5 * lin[2];
    let cube = |v: f64| v.abs().powf(1.0 / 3.0).copysign(v);
    let (l, m, s) = (cube(l), cube(m), cube(s));
    let big_l = 0.210_454_255_3 * l + 0.793_617_785 * m - 0.004_072_046_8 * s;
    let a = 1.977_998_495_1 * l - 2.428_592_205 * m + 0.450_593_709_9 * s;
    let b = 0.025_904_037_1 * l + 0.782_771_766_2 * m - 0.808_675_766 * s;
    (
        big_l,
        crate::composition::hypot(a, b),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    )
}

/// The place on Itten's wheel of an OKLCH hue: a hue between two band centers
/// lies between their places.
fn place_of_hue(hue: f64) -> f64 {
    let first = BAND_CENTERS[0].0;
    let h = if hue >= first { hue } else { hue + 360.0 };
    for k in 0..BAND_CENTERS.len() {
        let (start, place) = BAND_CENTERS[k];
        let end = if k + 1 < BAND_CENTERS.len() {
            BAND_CENTERS[k + 1].0
        } else {
            first + 360.0
        };
        if start <= h && h < end {
            return (place - 60.0 * (h - start) / (end - start)).rem_euclid(360.0);
        }
    }
    0.0
}

/// A paint's place on the wheel, or `None` for an achromatic paint.
fn place_of(rgb: [u8; 3]) -> Option<f64> {
    let (_, chroma, hue) = oklch(rgb);
    (chroma >= ACHROMATIC).then(|| round1(place_of_hue(hue)))
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn twelve(degrees: f64) -> usize {
    ((degrees / 30.0).round_ties_even() as i64).rem_euclid(12) as usize
}

/// The angle between two places (0 to 180).
fn apart(a: f64, b: f64) -> f64 {
    ((a - b + 180.0).rem_euclid(360.0) - 180.0).abs()
}

/// One of the nine colors as the run's palette draws it.
#[derive(Clone, Debug, PartialEq)]
struct Paint {
    color: Color,
    rgb: [u8; 3],
    lab: [f64; 3],
    /// CIELAB lightness, from 0 to 1.
    lightness: f64,
    chroma: f64,
    place: Option<f64>,
    /// The catalog's name of the paint, when the host sent it.
    name: Option<String>,
}

impl Paint {
    fn new(color: Color, rgb: [u8; 3], name: Option<String>) -> Self {
        let lab = lab_of(rgb);
        Self {
            color,
            rgb,
            lab,
            lightness: lab[0] / 100.0,
            chroma: crate::composition::hypot(lab[1], lab[2]),
            place: place_of(rgb),
            name,
        }
    }

    /// The color a paint is seen as when that is not its name (the prototype's
    /// `paints.seen_as`), in both languages.
    fn seen_as(&self) -> Option<[String; 2]> {
        let (light, chroma, _) = oklch(self.rgb);
        let Some(place) = self.place else {
            return (!NEUTRAL.contains(&self.color)).then(|| ["灰".to_owned(), "gray".to_owned()]);
        };
        let family = twelve(place);
        let named = |words: [&str; 2]| Some(words.map(str::to_owned));
        if NEUTRAL.contains(&self.color) {
            return named(TWELVE[family]);
        }
        let is = |names: &[usize]| names.contains(&family);
        // 0 yellow, 1 yellow-orange, 2 orange, 3 red-orange, 4 red, 5 red-purple,
        // 6 purple, 7 blue-purple, 8 blue, 11 yellow-green.
        if is(&[0, 11, 1]) && light < 0.62 && chroma < 0.135 {
            return named(["オリーブ", "olive"]);
        }
        if is(&[2, 3, 1]) && ((light < 0.62 && chroma < 0.14) || (light < 0.75 && chroma < 0.07)) {
            return named(["茶", "brown"]);
        }
        if is(&[4, 5, 6])
            && ((light >= 0.72 && self.color != Color::Purple)
                || (family == 5 && chroma >= 0.18 && light >= 0.6))
        {
            return named(["桃色", "pink"]);
        }
        if is(&[8, 7]) && light < 0.33 {
            return named(["紺", "navy"]);
        }
        let own = own_place(self.color)?;
        #[allow(clippy::cast_precision_loss)]
        let slot = family as f64 * 30.0;
        let near = [-30.0, 0.0, 30.0]
            .iter()
            .any(|d: &f64| apart((own + d).rem_euclid(360.0), slot) < 1e-9);
        if near { None } else { named(TWELVE[family]) }
    }

    /// The words for how a paint looks (the prototype's `paints.looks`).
    fn looks(&self, at: usize) -> String {
        let (light, chroma, _) = oklch(self.rgb);
        let Some(place) = self.place else {
            let words = [
                (0.93, ["白に近い", "near white"]),
                (0.75, ["明るい灰", "light gray"]),
                (0.50, ["灰", "gray"]),
                (0.30, ["暗い灰", "dark gray"]),
                (0.0, ["黒に近い", "near black"]),
            ];
            return words
                .iter()
                .find(|(bound, _)| light >= *bound)
                .map_or(String::new(), |(_, word)| word[at].to_owned());
        };
        let light_words = [
            (0.80, ["明るい", "light"]),
            (0.55, ["中ほどの明るさの", "medium-light"]),
            (0.0, ["暗い", "dark"]),
        ];
        let vivid_words = [
            (0.13, ["鮮やかな", "vivid"]),
            (0.07, ["中ほどの鮮やかさの", "moderately vivid"]),
            (0.0, ["くすんだ", "dull"]),
        ];
        let lw = light_words
            .iter()
            .find(|(bound, _)| light >= *bound)
            .map_or("", |(_, word)| word[at]);
        let vw = vivid_words
            .iter()
            .find(|(bound, _)| chroma >= *bound)
            .map_or("", |(_, word)| word[at]);
        let hue = TWELVE[twelve(place)][at];
        let words = if at == 0 {
            format!("{lw}{vw}{hue}")
        } else {
            format!("{lw} {vw} {hue}")
        };
        match self.seen_as() {
            Some(other) if at == 0 => format!("{words}（{}に見える）", other[0]),
            Some(other) => format!("{words} (seen as {})", other[1]),
            None => words,
        }
    }
}

// --- hue relations on the wheel ----------------------------------------------------------------

/// The places counted once: two paints within half a degree are one color.
fn distinct_places(places: &[f64]) -> Vec<f64> {
    let mut out: Vec<f64> = Vec::new();
    for place in places {
        if out.iter().all(|found| apart(*place, *found) > SAME_PLACE) {
            out.push(*place);
        }
    }
    out
}

fn hue_contrast(places: &[f64]) -> bool {
    let found = distinct_places(places);
    found.len() >= 3
        && found
            .iter()
            .enumerate()
            .all(|(k, a)| found[k + 1..].iter().all(|b| apart(*a, *b) >= APART_FAR))
}

fn analogous(places: &[f64]) -> bool {
    let mut found: Vec<f64> = distinct_places(places)
        .into_iter()
        .map(|place| place.rem_euclid(360.0))
        .collect();
    if found.len() < 2 {
        return false;
    }
    found.sort_by(f64::total_cmp);
    let mut gaps: Vec<f64> = found.windows(2).map(|pair| pair[1] - pair[0]).collect();
    gaps.push(found[0] + 360.0 - found[found.len() - 1]);
    gaps.iter().copied().fold(f64::MIN, f64::max) >= 360.0 - ANALOGOUS_ARC
}

fn complement(a: Option<f64>, b: Option<f64>) -> bool {
    matches!((a, b), (Some(a), Some(b)) if apart(a, b) >= COMPLEMENT)
}

/// The voices of a chord: complement 2, triad 3, tetrad 4.
fn voices(chord: &str) -> Option<usize> {
    Some(match chord {
        "complement" => 2,
        "triad" => 3,
        "tetrad" => 4,
        _ => return None,
    })
}

/// Whether the chromatic places fit a chord: as many distinct paints as its
/// voices, each voice of some rotation of evenly spaced places with a paint
/// near it, and every paint near a voice.
fn chord(kind: &str, places: &[f64]) -> bool {
    let Some(need) = voices(kind) else {
        return false;
    };
    let found = distinct_places(places);
    if found.len() < need {
        return false;
    }
    #[allow(clippy::cast_precision_loss)]
    let step = 360.0 / need as f64;
    found.iter().any(|start| {
        #[allow(clippy::cast_precision_loss)]
        let voiced: Vec<f64> = (0..need)
            .map(|k| (start + k as f64 * step).rem_euclid(360.0))
            .collect();
        voiced
            .iter()
            .all(|v| found.iter().any(|p| apart(*v, *p) <= CHORD_TOLERANCE))
            && found
                .iter()
                .all(|p| voiced.iter().any(|v| apart(*v, *p) <= CHORD_TOLERANCE))
    })
}

/// True for warm, false for cool.
fn warm(place: f64) -> bool {
    !(WARM_TO..WARM_FROM).contains(&place)
}

// --- the colors the description states (F0) -----------------------------------------------------

/// The Japanese color words, found anywhere, and the names each is drawn with.
const JA_WORDS: [(&str, &[Color]); 23] = [
    ("白", &[Color::White]),
    ("黒", &[Color::Black]),
    ("灰", &[Color::Gray]),
    ("鼠", &[Color::Gray]),
    ("赤", &[Color::Red]),
    ("紅", &[Color::Red]),
    ("朱", &[Color::Red]),
    ("緋", &[Color::Red]),
    ("茜", &[Color::Red]),
    ("くれな", &[Color::Red]),
    ("橙", &[Color::Orange]),
    ("茶", &[Color::Orange]),
    ("黄", &[Color::Yellow]),
    ("金", &[Color::Yellow, Color::Orange]),
    ("緑", &[Color::Green]),
    ("翠", &[Color::Green]),
    ("青", &[Color::Blue]),
    ("蒼", &[Color::Blue]),
    ("藍", &[Color::Blue]),
    ("紺", &[Color::Blue]),
    ("紫", &[Color::Purple]),
    ("銀", &[Color::White, Color::Gray]),
    ("桃", &[Color::Red, Color::Purple]),
];

/// The English color words, found as whole words in any case.
const EN_WORDS: [(&str, &[Color]); 19] = [
    ("white", &[Color::White]),
    ("black", &[Color::Black]),
    ("gray", &[Color::Gray]),
    ("grey", &[Color::Gray]),
    ("red", &[Color::Red]),
    ("crimson", &[Color::Red]),
    ("scarlet", &[Color::Red]),
    ("orange", &[Color::Orange]),
    ("brown", &[Color::Orange]),
    ("yellow", &[Color::Yellow]),
    ("gold", &[Color::Yellow, Color::Orange]),
    ("golden", &[Color::Yellow, Color::Orange]),
    ("green", &[Color::Green]),
    ("blue", &[Color::Blue]),
    ("navy", &[Color::Blue]),
    ("purple", &[Color::Purple]),
    ("violet", &[Color::Purple]),
    ("silver", &[Color::White, Color::Gray]),
    ("pink", &[Color::Red, Color::Purple]),
];

fn word_character(character: char) -> bool {
    character.is_alphanumeric() || character == '_'
}

/// The color words of a description in its order, each with the names it can
/// be drawn with.
fn color_terms(description: &str) -> Vec<(String, &'static [Color])> {
    let mut found: Vec<(usize, String, &'static [Color])> = Vec::new();
    for (word, names) in JA_WORDS {
        for (at, _) in description.match_indices(word) {
            found.push((at, word.to_owned(), names));
        }
    }
    let lower = description.to_ascii_lowercase();
    for (word, names) in EN_WORDS {
        for (at, _) in lower.match_indices(word) {
            let before = description[..at].chars().next_back();
            let after = description[at + word.len()..].chars().next();
            if before.is_none_or(|c| !word_character(c)) && after.is_none_or(|c| !word_character(c))
            {
                found.push((at, description[at..at + word.len()].to_owned(), names));
            }
        }
    }
    found.sort_by(|a, b| (a.0, &a.1).cmp(&(b.0, &b.1)));
    found
        .into_iter()
        .map(|(_, word, names)| (word, names))
        .collect()
}

/// Every color a layer draws: its instructions' colors and colors in turn.
fn layer_colors(score: &Score, positions: &[usize]) -> BTreeSet<&'static str> {
    let mut found = BTreeSet::new();
    for position in positions {
        let instruction = &score.instructions[*position];
        found.insert(instruction.color.as_str());
        for color in instruction
            .arrangement
            .iter()
            .flat_map(|arrangement| arrangement.color_cycle.iter())
        {
            found.insert(color.as_str());
        }
    }
    found
}

/// The layers and the ground whose color a word of the description states: a
/// layer whose colors are all names of one word, the ground when its color is.
fn stated(description: &str, score: &Score) -> (BTreeMap<usize, String>, Option<String>) {
    let words = color_terms(description);
    let mut layers = BTreeMap::new();
    for (layer, positions) in laws::layers(score) {
        let colors = layer_colors(score, &positions);
        if colors.is_empty() {
            continue;
        }
        if let Some((word, _)) = words.iter().find(|(_, names)| {
            colors
                .iter()
                .all(|color| names.iter().any(|name| name.as_str() == *color))
        }) {
            layers.insert(layer, word.clone());
        }
    }
    let ground = words
        .iter()
        .find(|(_, names)| names.contains(&score.background))
        .map(|(word, _)| word.clone());
    (layers, ground)
}

// --- harmony (F3) ------------------------------------------------------------------------------

/// Lightness, chroma and hue (degrees) of a CIELAB color.
fn lch([l, a, b]: [f64; 3]) -> (f64, f64, f64) {
    (
        l,
        crate::composition::hypot(a, b),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    )
}

fn deltas(one: [f64; 3], two: [f64; 3]) -> (f64, f64, f64, f64, f64, f64, f64, f64) {
    let (l1, c1, h1) = lch(one);
    let (l2, c2, h2) = lch(two);
    let dh = ((h2 - h1 + 180.0).rem_euclid(360.0) - 180.0).to_radians();
    let big_dh = 2.0 * (c1 * c2).sqrt() * (dh / 2.0).sin();
    (l1, c1, h1, l2, c2, h2, big_dh, c1 - c2)
}

fn h_sy(big_l: f64, chroma: f64, hue: f64) -> f64 {
    let e_c = 0.5 + 0.5 * (-2.0 + 0.5 * chroma).tanh();
    let h_s = -0.08
        - 0.14 * (hue + 50.0).to_radians().sin()
        - 0.07 * (2.0 * hue + 90.0).to_radians().sin();
    let x = (90.0 - hue) / 10.0;
    let e_y = if x < 50.0 {
        ((0.22 * big_l - 12.8) / 10.0) * (x - x.exp()).exp()
    } else {
        0.0
    };
    e_c * (h_s + e_y)
}

/// The harmony of two colors that touch (Ou, Chong, Luo and Minchew, US9134179B2 eq. 13-15).
fn touching_harmony(one: [f64; 3], two: [f64; 3]) -> f64 {
    let (l1, c1, h1, l2, c2, h2, big_dh, dc) = deltas(one, two);
    let d = crate::composition::hypot(big_dh, dc / 1.46);
    let h_c = 0.04 + 0.53 * (0.8 - 0.045 * d).tanh();
    let h_lsum = 0.3 + 0.5 * (-4.0 + 0.029 * (l1 + l2)).tanh();
    let h_dl = 0.14 + 0.15 * (-2.0 + 0.2 * (l1 - l2).abs()).tanh();
    h_c + h_lsum + h_dl + h_sy(l1, c1, h1) + h_sy(l2, c2, h2)
}

/// The harmony of two colors apart.
fn apart_harmony(one: [f64; 3], two: [f64; 3]) -> f64 {
    let (.., big_dh, dc) = deltas(one, two);
    0.2 + 0.65 * (1.7 - 0.045 * crate::composition::hypot(big_dh, dc / 1.30)).tanh()
}

/// A picture's harmony: the mean over the ground with each layer and over
/// each pair of layers, touching or apart.
fn harmony(
    ground: [f64; 3],
    layers: &BTreeMap<usize, [f64; 3]>,
    neighbors: &BTreeMap<usize, BTreeSet<usize>>,
) -> Option<f64> {
    let mut pairs: Vec<f64> = layers
        .values()
        .map(|lab| touching_harmony(ground, *lab))
        .collect();
    let keys: Vec<&usize> = layers.keys().collect();
    for (k, a) in keys.iter().enumerate() {
        for b in &keys[k + 1..] {
            let near = neighbors.get(a).is_some_and(|near| near.contains(b))
                || neighbors.get(b).is_some_and(|near| near.contains(a));
            pairs.push(if near {
                touching_harmony(layers[a], layers[b])
            } else {
                apart_harmony(layers[a], layers[b])
            });
        }
    }
    #[allow(clippy::cast_precision_loss)]
    (!pairs.is_empty()).then(|| pairs.iter().sum::<f64>() / pairs.len() as f64)
}

// --- the levels of D7 --------------------------------------------------------------------------

/// D7's levels of lightness: each value joins the level it is within
/// `LEVEL_SPREAD` of (of its first and its last value).
fn levels_of(values: &BTreeSet<u64>) -> Vec<Vec<f64>> {
    let mut levels: Vec<Vec<f64>> = Vec::new();
    for value in values.iter().map(|bits| f64::from_bits(*bits)) {
        match levels.last_mut() {
            Some(level)
                if value - level[level.len() - 1] <= LEVEL_SPREAD
                    && value - level[0] <= LEVEL_SPREAD =>
            {
                level.push(value);
            }
            _ => levels.push(vec![value]),
        }
    }
    levels
}

/// Lightness values, rounded to three decimals, in order (a set of their bits:
/// a non-negative float orders as its bits).
fn level_values(values: impl IntoIterator<Item = f64>) -> BTreeSet<u64> {
    values
        .into_iter()
        .map(|value| laws::round3(value).max(0.0).to_bits())
        .collect()
}

/// The rank (0 dark, 1 middle, 2 light) of the level a value lies in, when
/// the values form exactly three levels at least `LEVEL_GAP` apart.
fn three_levels(values: &BTreeSet<u64>, of: f64) -> Option<usize> {
    let levels = levels_of(values);
    if levels.len() != 3 {
        return None;
    }
    let gaps_hold = levels
        .windows(2)
        .all(|pair| pair[1][0] - pair[0][pair[0].len() - 1] >= LEVEL_GAP);
    if !gaps_hold {
        return None;
    }
    let of = laws::round3(of);
    #[allow(clippy::float_cmp)]
    levels.iter().position(|level| level.contains(&of))
}

const LEVELS: [&str; 3] = ["dark", "middle", "light"];

// --- the context -------------------------------------------------------------------------------

/// One layer as the request shows it: the laws stage's summary and how it is
/// drawn now.
#[derive(Clone, Debug, PartialEq, Serialize)]
struct ColorLayer {
    #[serde(flatten)]
    summary: laws::LayerSummary,
    handling: &'static str,
    area: f64,
    contrast: f64,
    chroma: i64,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    unseen: Vec<&'static str>,
    neighbors: Vec<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    fixed: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stated: Option<String>,
}

/// One of the nine colors as the request's table shows it.
#[derive(Clone, Debug, PartialEq, Serialize)]
struct ColorRow {
    name: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    paint: Option<String>,
    looks: String,
    wheel: &'static str,
    place: Option<f64>,
    lightness: f64,
    chroma: i64,
    ground_diff: f64,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    same_paint_as: Vec<&'static str>,
}

/// What a work's layers allow the color laws, read from the Score of the
/// document the laws stage printed and from how it is drawn.
#[derive(Clone, Debug)]
pub struct ColorsContext {
    score: Score,
    printed: PrintedPlan,
    units: Units,
    paints: Vec<Paint>,
    main: usize,
    /// The layers whose color the laws stage decided, by the law.
    fixed: BTreeMap<usize, String>,
    /// The layers and ground whose color the description states, by the word.
    stated: BTreeMap<usize, String>,
    stated_ground: Option<String>,
    plugins: BTreeSet<usize>,
    summaries: Vec<laws::LayerSummary>,
    /// How the Score is drawn now, and how each layer is drawn in each of the
    /// nine colors (the layers that may be recolored drawn in it, the others
    /// as they are).
    now: Drawing,
    by_color: Vec<Drawing>,
    painter: Painter,
    colorable: Vec<usize>,
    multi: Vec<usize>,
    /// The layers of enough marks for a gradation to run through them.
    graded: Vec<usize>,
    deterministic: Vec<usize>,
    scatter_small: Vec<usize>,
    pairs: Vec<(usize, usize)>,
    vivid: Vec<Color>,
    already: BTreeSet<&'static str>,
    feasible: BTreeMap<&'static str, Vec<&'static str>>,
}

/// What the color stage reads to build its context.
#[derive(Clone, Copy, Debug)]
pub struct ColorsInput<'a> {
    /// The Score of the document the laws stage left, as the run compiles it.
    pub score: &'a Score,
    pub printed: &'a PrintedPlan,
    pub handoff: &'a LawsHandoff,
    pub palette: &'a ResolvedPaletteDto,
    pub canvas_format_id: &'a str,
    pub seeds: Seeds,
    pub error_policy: inku_score::ScoreErrorPolicy,
    pub description: &'a str,
}

impl ColorsContext {
    /// The context of the document the laws stage left. `None` when its
    /// Score does not have one layer per printed sentence, the palette does
    /// not observe the nine colors, or the renderer does not draw it.
    #[must_use]
    pub fn new(input: ColorsInput<'_>) -> Option<Self> {
        let units = Units::of(input.canvas_format_id)?;
        let observations = input.palette.observations?;
        let names = input.palette.paints.as_ref();
        let paints = COLORS
            .iter()
            .map(|color| {
                let (k, observed) = observations
                    .iter()
                    .enumerate()
                    .find(|(_, observed)| observed.abstract_color == *color)?;
                let name = names.and_then(|names| names.get(k).cloned().flatten());
                Some(Paint::new(*color, observed.concrete_rgb, name))
            })
            .collect::<Option<Vec<Paint>>>()?;
        let rgb: Vec<(Color, [u8; 3])> = paints
            .iter()
            .map(|paint| (paint.color, paint.rgb))
            .collect();
        let painter = Painter::new(
            &rgb,
            input.canvas_format_id,
            input.seeds,
            input.error_policy,
        )?;
        let score = input.score.clone();
        let summaries = laws::summaries(&score, units);
        let printed = input.printed.clone();
        let first = printed.first_plan_layer();
        let count = printed.plan.layers.len();
        let expected: Vec<usize> = (0..first + count).collect();
        let found: Vec<usize> = summaries.iter().map(|summary| summary.layer).collect();
        if found != expected
            || printed.ranges.len() != count
            || printed.joints.len() != count
            || printed.numeric.len() != count
        {
            return None;
        }
        let plugins: BTreeSet<usize> = summaries
            .iter()
            .filter(|summary| summary.arranged == Some("plugin"))
            .map(|summary| summary.layer)
            .collect();
        let (stated, stated_ground) = stated(input.description, &score);
        let fixed: BTreeMap<usize, String> = input
            .handoff
            .fixed
            .iter()
            .filter(|(layer, _)| found.contains(layer))
            .map(|(layer, law)| (*layer, law.clone()))
            .collect();
        let main = input
            .handoff
            .main_layer
            .filter(|layer| found.contains(layer) && !plugins.contains(layer))
            .unwrap_or(first);
        // The layers whose color the laws stage decided may be recolored as
        // long as its laws still hold (the author's answer, 2026-10-20).
        let colorable: Vec<usize> = found
            .iter()
            .copied()
            .filter(|layer| !stated.contains_key(layer) && !plugins.contains(layer))
            .collect();
        let mut shares = Shares::default();
        let now = painter.drawing(&score, &mut shares)?;
        let positions = laws::layers(&score);
        let by_color = COLORS
            .iter()
            .map(|color| {
                let mut recolored = score.clone();
                for layer in &colorable {
                    for position in positions.get(layer).into_iter().flatten() {
                        paint_instruction(&mut recolored.instructions[*position], *color);
                    }
                }
                painter.drawing(&recolored, &mut shares)
            })
            .collect::<Option<Vec<Drawing>>>()?;
        let by = |layer: usize| summaries.iter().find(|summary| summary.layer == layer);
        let movable = |layer: &usize| {
            by(*layer).is_some_and(|summary| !matches!(summary.arranged, Some("plugin" | "fill")))
        };
        let multi: Vec<usize> = colorable
            .iter()
            .copied()
            .filter(|layer| movable(layer) && by(*layer).is_some_and(|summary| summary.count >= 2))
            .collect();
        let graded: Vec<usize> = multi
            .iter()
            .copied()
            .filter(|layer| by(*layer).is_some_and(|summary| summary.count >= GRADED_MARKS))
            .collect();
        let deterministic: Vec<usize> = colorable
            .iter()
            .copied()
            .filter(|layer| {
                movable(layer)
                    && by(*layer).is_some_and(|summary| summary.arranged != Some("scatter"))
            })
            .collect();
        let scatter_small: Vec<usize> = colorable
            .iter()
            .copied()
            .filter(|layer| {
                by(*layer).is_some_and(|summary| {
                    summary.arranged == Some("scatter")
                        && summary.count >= MIX_COUNT
                        && laws::py_max(summary.mark_size[0], summary.mark_size[1]) <= MIX_SIZE
                })
            })
            .collect();
        let mut pairs: Vec<(usize, usize)> = Vec::new();
        for a in &found {
            for b in &colorable {
                if a != b && now.neighbors.get(a).is_some_and(|near| near.contains(b)) {
                    pairs.push((*a, *b));
                }
            }
        }
        pairs.sort_unstable();
        let mut ranked: Vec<&Paint> = paints.iter().collect();
        ranked.sort_by_key(|paint| -laws::round_int(paint.chroma));
        let vivid: Vec<Color> = ranked.iter().take(3).map(|paint| paint.color).collect();
        let mut context = Self {
            score,
            printed,
            units,
            paints,
            main,
            fixed,
            stated,
            stated_ground,
            plugins,
            summaries,
            now,
            by_color,
            painter,
            colorable,
            multi,
            graded,
            deterministic,
            scatter_small,
            pairs,
            vivid,
            already: BTreeSet::new(),
            feasible: BTreeMap::new(),
        };
        context.already = context.find_already();
        context.feasible = context.find_feasible();
        Some(context)
    }

    fn first_plan_layer(&self) -> usize {
        self.printed.first_plan_layer()
    }

    fn paint(&self, color: Color) -> &Paint {
        &self.paints[index_of(color)]
    }

    fn ground(&self) -> Color {
        self.score.background
    }

    fn summary(&self, layer: usize) -> Option<&laws::LayerSummary> {
        self.summaries.iter().find(|summary| summary.layer == layer)
    }

    fn layers(&self) -> impl Iterator<Item = usize> + '_ {
        self.summaries.iter().map(|summary| summary.layer)
    }

    fn movable(&self, layer: usize) -> bool {
        self.summary(layer)
            .is_some_and(|summary| !matches!(summary.arranged, Some("plugin" | "fill")))
    }

    /// How a layer looks drawn in a color (a layer the stage may not recolor
    /// as it is).
    fn look(&self, layer: usize, color: Color) -> Option<&Look> {
        self.by_color[index_of(color)].looks.get(&layer)
    }

    /// The drawn lightness difference of a layer in a color from the ground.
    /// A layer the estimate does not read (a computer's screen) is taken as
    /// seen.
    fn seen(&self, layer: usize, color: Color) -> f64 {
        match self.look(layer, color) {
            Some(look) if look.read => look.contrast,
            _ => 1.0,
        }
    }

    /// The table lightness difference of a color from the ground.
    fn table_difference(&self, color: Color) -> f64 {
        (self.paint(color).lightness - self.paint(self.ground()).lightness).abs()
    }

    /// The place a drawn color takes on the wheel: its paint's, when the
    /// drawing reads as chromatic.
    fn drawn_place(&self, look: Option<&Look>, color: Color) -> Option<f64> {
        let look = look?;
        (look.lab.is_some() && look.chroma >= CHROMATIC)
            .then(|| self.paint(color).place)
            .flatten()
    }

    fn ground_place(&self) -> Option<f64> {
        let ground = self.paint(self.ground());
        (ground.chroma >= CHROMATIC)
            .then_some(ground.place)
            .flatten()
    }

    /// The paint nearest a drawn color.
    fn nearest(&self, lab: [f64; 3]) -> Color {
        let distance = |paint: &Paint| (0..3).map(|k| (paint.lab[k] - lab[k]).powi(2)).sum::<f64>();
        let mut best = &self.paints[0];
        for paint in &self.paints[1..] {
            if distance(paint) < distance(best) {
                best = paint;
            }
        }
        best.color
    }

    /// The share of the picture each paint covers now: each layer's ink at the
    /// paint nearest its drawn color, the ground the rest.
    fn picture_shares(&self) -> BTreeMap<&'static str, f64> {
        let mut shares: BTreeMap<&'static str, f64> = BTreeMap::new();
        let mut ink = 0.0;
        for look in self.now.looks.values() {
            if let Some(lab) = look.lab {
                *shares.entry(self.nearest(lab).as_str()).or_insert(0.0) += look.ink;
                ink += look.ink;
            }
        }
        *shares.entry(self.ground().as_str()).or_insert(0.0) += (1.0 - ink).max(0.0);
        shares
    }

    fn first_color(&self, layer: usize) -> Option<Color> {
        let positions = laws::layers(&self.score).remove(&layer)?;
        Some(self.score.instructions[*positions.first()?].color)
    }

    // --- the laws that already hold (F2) --------------------------------------------------------

    /// The laws that already hold in the picture as it is drawn: a law holds
    /// when some value it may take holds, read as the prototype's measure read
    /// the input pictures (here from the estimate). A law that marks each mark
    /// holds only when the Score already carries its mark.
    fn find_already(&self) -> BTreeSet<&'static str> {
        COLOR_LAWS
            .iter()
            .copied()
            .filter(|law| self.holds(law))
            .collect()
    }

    #[allow(clippy::too_many_lines)]
    fn holds(&self, law: &str) -> bool {
        let positions = laws::layers(&self.score);
        let instructions = |layer: &usize| {
            positions
                .get(layer)
                .into_iter()
                .flatten()
                .map(|position| &self.score.instructions[*position])
        };
        // The prototype read these over every layer the laws stage left open,
        // the stated ones included; the layers whose color the laws stage
        // decided are open too, since the colors may change them.
        let open: Vec<usize> = self.layers().collect();
        let marked = |test: &dyn Fn(&Instruction) -> bool| {
            open.iter().any(|layer| instructions(layer).any(test))
        };
        let drawn: BTreeMap<usize, (&Look, [f64; 3])> = self
            .now
            .looks
            .iter()
            .filter_map(|(layer, look)| Some((*layer, (look, look.lab?))))
            .collect();
        let places: BTreeMap<usize, Option<f64>> = drawn
            .iter()
            .map(|(layer, (look, _))| {
                (
                    *layer,
                    self.first_color(*layer)
                        .and_then(|color| self.drawn_place(Some(look), color)),
                )
            })
            .collect();
        let mut chromatic: Vec<f64> = places.values().flatten().copied().collect();
        if let Some(place) = self.ground_place() {
            chromatic.push(place);
        }
        let colorable_drawn: Vec<usize> = open
            .iter()
            .copied()
            .filter(|layer| drawn.contains_key(layer))
            .collect();
        match law {
            "B11" | "B16" | "D6" => marked(&|instruction| {
                instruction.arrangement.as_ref().is_some_and(|arrangement| {
                    arrangement
                        .color_cycle
                        .iter()
                        .map(|color| color.as_str())
                        .collect::<BTreeSet<_>>()
                        .len()
                        >= 2
                })
            }),
            "B13" => marked(&|instruction| {
                instruction
                    .arrangement
                    .as_ref()
                    .is_some_and(|arrangement| arrangement.fade == Fade::Directional)
            }),
            "B14" => marked(&|instruction| {
                instruction
                    .arrangement
                    .as_ref()
                    .is_some_and(|arrangement| arrangement.fade == Fade::Outward)
            }),
            "C7" => false,
            "B19" => {
                let main = self
                    .now
                    .looks
                    .get(&self.main)
                    .map_or(0.0, |look| look.contrast);
                main >= B19_MAIN
                    && self
                        .now
                        .looks
                        .iter()
                        .filter(|(layer, _)| **layer != self.main)
                        .all(|(_, look)| look.contrast >= VISIBLE)
            }
            "B17" => {
                let counted = self
                    .picture_shares()
                    .into_iter()
                    .filter(|(_, share)| *share >= SHARE_COUNTED)
                    .count();
                counted > 0 && counted <= 3
            }
            "B18" => {
                let chromatic: Vec<(f64, f64)> = drawn
                    .iter()
                    .filter_map(|(_, (look, lab))| {
                        let value = light_value(self.nearest(*lab))?;
                        (look.chroma >= CHROMATIC).then_some((value, look.ink))
                    })
                    .collect();
                // Each pair of a lighter and a darker color: the lighter covers less.
                let mut pairs = 0;
                let mut holds = true;
                for a in &chromatic {
                    for b in chromatic.iter().filter(|b| a.0 > b.0) {
                        pairs += 1;
                        holds &= a.1 < b.1;
                    }
                }
                chromatic.len() >= 2 && pairs > 0 && holds
            }
            "C9" => {
                let shares = self.picture_shares();
                self.vivid.iter().any(|color| {
                    let share = shares.get(color.as_str()).copied().unwrap_or(0.0);
                    (0.15..=0.30).contains(&share) || (0.30..=0.50).contains(&share)
                })
            }
            "D2" => {
                let mine = drawn.get(&self.main).map_or(0.0, |(look, _)| look.chroma);
                let others: Vec<f64> = drawn
                    .iter()
                    .filter(|(layer, _)| **layer != self.main)
                    .map(|(_, (look, _))| look.chroma)
                    .collect();
                !others.is_empty()
                    && others.iter().all(|other| mine >= 2.0 * other)
                    && mine >= CHROMATIC
            }
            "D4" => colorable_drawn.iter().enumerate().any(|(k, a)| {
                colorable_drawn[k + 1..].iter().any(|b| {
                    let (look_a, lab_a) = drawn[a];
                    let (look_b, lab_b) = drawn[b];
                    let hues: Vec<f64> = [(look_a, lab_a), (look_b, lab_b)]
                        .iter()
                        .filter(|(look, _)| look.chroma >= CHROMATIC)
                        .map(|(_, lab)| lch(*lab).2)
                        .collect();
                    let spread = if hues.len() == 2 {
                        apart(hues[0], hues[1])
                    } else {
                        0.0
                    };
                    spread <= 30.0 && (look_a.contrast - look_b.contrast).abs() >= 0.1
                })
            }),
            "D7" => {
                let mut values: Vec<f64> = vec![self.paint(self.ground()).lightness];
                values.extend(drawn.values().map(|(_, lab)| lab[0] / 100.0));
                values.sort_by(f64::total_cmp);
                let mut levels: Vec<Vec<f64>> = Vec::new();
                for value in values {
                    match levels.last_mut() {
                        Some(level) if value - level[0] <= LEVEL_SPREAD => level.push(value),
                        _ => levels.push(vec![value]),
                    }
                }
                levels.len() == 3
                    && levels
                        .windows(2)
                        .all(|pair| pair[1][0] - pair[0][pair[0].len() - 1] >= LEVEL_GAP)
            }
            "D1" => hue_contrast(&chromatic),
            "D5" => analogous(&chromatic),
            "C8" => ["complement", "triad", "tetrad"]
                .iter()
                .any(|kind| chord(kind, &chromatic)),
            "D3" => colorable_drawn.iter().any(|a| {
                colorable_drawn.iter().any(|b| {
                    a != b
                        && self
                            .now
                            .neighbors
                            .get(a)
                            .is_some_and(|near| near.contains(b))
                        && ((places.get(a).copied().flatten().is_some()
                            && drawn[b].0.chroma < GRAY_PARTNER)
                            || complement(
                                places.get(a).copied().flatten(),
                                places.get(b).copied().flatten(),
                            ))
                })
            }),
            "B20" => {
                let base = self
                    .ground_place()
                    .or_else(|| places.get(&self.main).copied().flatten());
                colorable_drawn.iter().any(|layer| {
                    matches!((places.get(layer).copied().flatten(), base), (Some(accent), Some(base)) if warm(accent) != warm(base))
                })
            }
            _ => false,
        }
    }

    // --- the values the tool can realize ------------------------------------------------------

    /// The hues D1 and D5 can take and the levels D7 can, each tried as the
    /// only law.
    fn find_feasible(&self) -> BTreeMap<&'static str, Vec<&'static str>> {
        let mut found = BTreeMap::new();
        if self.colorable.is_empty() {
            return found;
        }
        for law in ["D1", "D5"] {
            let hues: Vec<&'static str> = WHEEL
                .iter()
                .map(|hue| hue.as_str())
                .filter(|hue| self.trial(law, json!({"hue": hue})))
                .collect();
            found.insert(law, hues);
        }
        let levels: Vec<&'static str> = ["light", "middle", "dark"]
            .into_iter()
            .filter(|level| self.trial("D7", json!({"level": level})))
            .collect();
        found.insert("D7", levels);
        found
    }

    fn trial(&self, law: &'static str, value: Value) -> bool {
        let answer = Answer {
            main_law: law.to_owned(),
            laws: BTreeMap::from([(law, value)]),
            colors: None,
        };
        Painting::new(self, &answer, true).run().is_ok()
    }
}

/// An instruction drawn in one color: its colors in turn are dropped.
fn paint_instruction(instruction: &mut Instruction, color: Color) {
    instruction.color = color;
    if let Some(arrangement) = instruction.arrangement.as_mut() {
        arrangement.color_cycle = Vec::new();
    }
}

// --- the request -------------------------------------------------------------------------------

/// What the request says of one law, in Japanese and English.
struct LawText {
    name: [&'static str; 2],
    family: [&'static str; 2],
    source: [&'static str; 2],
    law: [&'static str; 2],
    choose: [&'static str; 2],
    example: [&'static str; 2],
}

const RHYTHM: [&str; 2] = ["律動", "rhythm"];
const GRADATION: [&str; 2] = ["階調", "gradation"];
const SCHEME: [&str; 2] = ["配色", "color scheme"];
const CARD: [&str; 2] = ["カード", "card"];

const fn both(text: &'static str) -> [&'static str; 2] {
    [text, text]
}

/// The color laws as the request lists them: the laws stage prototype's texts
/// for the eleven moved laws and the color stage prototype's for D1 to D7,
/// with what the ground kept as it is (V1) and the drawn lightness change.
const LAW_TEXTS: [(&str, LawText); 18] = [
    (
        "B11",
        LawText {
            name: ["交替", "Alternation"],
            family: RHYTHM,
            source: [
                "Dow の Repetition・Opposition",
                "Dow's repetition and opposition",
            ],
            law: [
                "列か格子の物に、二つの色を ABAB と交互に巡らせる。",
                "Two colors take the marks of a row or a grid in turn, ABAB.",
            ],
            choose: [
                "列か格子の層と、2色（違う色）。",
                "A row or grid layer, and two different colors.",
            ],
            example: both(r#"{"targets":[{"layer":1,"colors":["white","orange"]}]}"#),
        },
    ),
    (
        "B13",
        LawText {
            name: ["一方向の推移", "Gradation in one direction"],
            family: GRADATION,
            source: ["Dow の Transition", "Dow's transition"],
            law: [
                "列の物を、一方の端から他方へ、濃さを順に下げる。痕が3つ以上の列に使う。格子・1個の層・一つずつに開いた層には使えない。",
                "The marks of a row lose density in order from one end to the other. A row of three marks or more takes it; a grid, a single mark and a layer opened into marks cannot.",
            ],
            choose: [
                "列の層ごとに、薄れる向き。",
                "For each row layer, the direction it fades.",
            ],
            example: both(r#"{"targets":[{"layer":1,"direction":"bottom_to_top"}]}"#),
        },
    ),
    (
        "B14",
        LawText {
            name: ["中心からの推移", "Gradation from the center"],
            family: GRADATION,
            source: [
                "Leonardo『絵画論』の陰影",
                "Leonardo, Treatise on Painting: shading",
            ],
            law: [
                "散らした物か列の物を、中心から外へ薄れさせる。痕が3つ以上の層に使う。",
                "Scattered marks or the marks of a row fade from the center outward. A layer of three marks or more takes it.",
            ],
            choose: ["散らす層か列の層。", "A scattered layer or a row layer."],
            example: both(r#"{"layers":[2]}"#),
        },
    ),
    (
        "B16",
        LawText {
            name: ["色の推移", "Color shift"],
            family: GRADATION,
            source: [
                "Dow の Transition、Itten の明暗の対比",
                "Dow's transition; Itten's light-dark contrast",
            ],
            law: [
                "列か格子の物の色を、明るさの順に並べた 2〜4 色で、端から端へ段々に移り変わらせる。",
                "The marks of a row or a grid shift step by step from end to end through two to four colors put in order of lightness.",
            ],
            choose: [
                "列か格子の層ごとに、色（2〜4。道具が明るさの順に並べる）。",
                "For each row or grid layer, its colors (two to four; the tool puts them in order of lightness).",
            ],
            example: both(r#"{"targets":[{"layer":1,"colors":["yellow","orange","red"]}]}"#),
        },
    ),
    (
        "B17",
        LawText {
            name: ["主調・従調・強調", "Dominant, subordinate and accent"],
            family: SCHEME,
            source: [
                "Chevreul『色彩の同時対比の法則』(1839)、Itten『色彩の芸術』(1961)",
                "Chevreul, The Principles of Harmony and Contrast of Colours (1839); Itten, The Art of Color (1961)",
            ],
            law: [
                "地を主調、主を従調、面積のいちばん小さい層を強調の色にし、地を含めて3色までにする。",
                "The ground is the dominant color, the main layer the subordinate one, and the layer of the smallest area takes the accent color; three colors at most, the ground included.",
            ],
            choose: [
                "強調の色（各層の色は colors に書く。地は今のまま。二つの名が同じ絵具なら一つの色と数える）。",
                "The accent color (each layer's color goes in colors; the ground stays as it is; two names that draw one paint count as one color).",
            ],
            example: both(r#"{"accent":"orange"}"#),
        },
    ),
    (
        "B18",
        LawText {
            name: ["量の対比", "Contrast of extension"],
            family: SCHEME,
            source: [
                "Itten の量の対比（Goethe の光の値）",
                "Itten's contrast of extension (Goethe's light values)",
            ],
            law: [
                "色の付いた層の面積を、色の光の値（黄 9・橙 8・赤 6・緑 6・青 4・紫 3）の逆比にする。明るい色ほど小さく。白・黒・灰は数えない。道具が閉じた形の大きさを変える。",
                "The colored layers' areas follow the inverse of their colors' light values (yellow 9, orange 8, red 6, green 6, blue 4, purple 3): the lighter the color, the smaller. White, black and gray do not count. The tool resizes the closed shapes.",
            ],
            choose: [
                "use に true（色は colors に書く。色の付いた閉じた形か弧の層が2つ以上要る）。",
                "use: true (the colors go in colors; it needs two or more colored layers of closed shapes or arcs).",
            ],
            example: both(r#"{"use":true}"#),
        },
    ),
    (
        "B19",
        LawText {
            name: ["明暗の対比", "Light-dark contrast"],
            family: SCHEME,
            source: ["Dow の濃淡（Notan）、Itten", "Dow's notan; Itten"],
            law: [
                "主と地を明るさで大きく離し（描いた差 0.35 以上）、ほかの層も地と 0.15 以上離す。",
                "The main layer stands far from the ground in lightness (a drawn difference of 0.35 or more), and every other layer 0.15 or more.",
            ],
            choose: [
                "use に true（各層の色は colors に書く。地は今のまま。描いた明るさで確かめる）。",
                "use: true (each layer's color goes in colors; the ground stays as it is; it is checked by the drawn lightness).",
            ],
            example: both(r#"{"use":true}"#),
        },
    ),
    (
        "B20",
        LawText {
            name: ["寒暖の対比", "Warm-cool contrast"],
            family: SCHEME,
            source: ["Itten", "Itten"],
            law: [
                "主の色（地か主の層）と反対の温度の色を、小さな強調に置く。温度は色相環の位置で見る（暖＝黄から赤紫まで、寒＝紫から黄緑まで）。",
                "A small accent takes a color of the temperature opposite to the main color (the ground, or the main layer when the ground is achromatic). Temperature goes by the place on the wheel (warm from yellow to red-purple, cool from purple to yellow-green).",
            ],
            choose: [
                "強調の層（色は colors に書く）。",
                "The accent layer (its color goes in colors).",
            ],
            example: both(r#"{"accent_layer":2}"#),
        },
    ),
    (
        "C7",
        LawText {
            name: ["襲の色目", "Kasane no irome"],
            family: CARD,
            source: [
                "平安の装束の襲の色目（季節と名のある色の組）",
                "The layered colors of Heian robes (pairs of colors with seasons and names)",
            ],
            law: [
                "色を重ねて、縁に下の色が覗くようにする。表・裏（・中）の色の組には季節と名がある（例: 紅梅は表が紅で裏が淡い紅、紅葉は表が紅で裏が濃い紅、卯の花は表が白で裏が青み）。作品の季節と題に合う組を、このカタログの色から選ぶ。",
                "Layer colors so that the lower color shows at the edge. Pairs of an outer and an inner color (and a middle one) have seasons and names (kōbai: a crimson outer and a pale crimson inner; momiji: a crimson outer and a deep crimson inner; u-no-hana: a white outer and a bluish inner). Choose a pair from this catalog's colors that fits the work's season and subject.",
            ],
            choose: [
                "表・裏（・中）の色、その組が思わせる襲の名、組を当てる層（1〜2、散らす層は使えない）、重ねのずれ（小・中）。",
                "The outer and inner (and middle) colors, the kasane name the pair calls up, the layers it takes (one or two, not a scattered one), and how far the colors are offset (small, medium).",
            ],
            example: [
                r#"{"targets":[2],"omote":"red","ura":"orange","naka":"none","kasane_name":"紅葉","offset":"small"}"#,
                r#"{"targets":[2],"omote":"red","ura":"orange","naka":"none","kasane_name":"momiji","offset":"small"}"#,
            ],
        },
    ),
    (
        "C8",
        LawText {
            name: ["色の和音", "Color chord"],
            family: CARD,
            source: [
                "Itten の色の和音（2・3・4色）、Chevreul の対比の調和",
                "Itten's color chords (two, three, four colors); Chevreul's harmony of contrast",
            ],
            law: [
                "色相環の上で等しく離れた色（補色の2色、三和音の3色、四和音の4色）を組み、地と層に当てる。色の表の place（色相環の位置）を見て選ぶ。色の元になるので colors と一緒には使わない。",
                "Colors evenly spaced on the wheel (two complements, a triad of three, a tetrad of four) go on the ground and the layers. Look at place in the color table (the place on the wheel). It is a source of colors, so it does not go with colors.",
            ],
            choose: [
                "和音の型と、層の色（地と描いた明るさの差が 0.15 以上）。地は今のままで、和音に数える。",
                "The chord, and the layers' colors (each 0.15 or more from the ground in drawn lightness). The ground stays as it is and counts in the chord.",
            ],
            example: both(
                r#"{"chord":"triad","assignments":[{"layer":0,"color":"orange"},{"layer":1,"color":"blue"}]}"#,
            ),
        },
    ),
    (
        "C9",
        LawText {
            name: ["強い色の面積", "Area of the strong color"],
            family: CARD,
            source: [
                "Itten の量の対比（Goethe の光の値）",
                "Itten's contrast of extension (Goethe's light values)",
            ],
            law: [
                "最も強い色に、画面の大きな面積を与える。主の物を大きくして、その色で塗る。",
                "The strongest color takes a large area of the canvas: the main layer is enlarged and filled with it.",
            ],
            choose: [
                "強い色（表の chroma の高い色から）、面積の目安、ほかの層の色（無彩に寄せる・そのまま）。",
                "The strong color (among the table's most vivid), the area it takes, and the other layers' colors (turn them neutral, or keep them).",
            ],
            example: both(r#"{"color":"red","area":"30-50","others":"neutral"}"#),
        },
    ),
    (
        "D1",
        LawText {
            name: ["色相の対比", "Contrast of hue"],
            family: SCHEME,
            source: [
                "Itten『色彩の芸術』(1961) の色相の対比",
                "Itten, The Art of Color (1961): contrast of hue",
            ],
            law: [
                "混ぜない鮮やかな色を3色以上並べ、色相の違いそのもので画を強くする。三原色（黄・赤・青）がいちばん強く、三間色（橙・紫・緑）が次に強い。",
                "Three or more unmixed vivid colors side by side make the picture strong by the difference of hue itself. The primaries (yellow, red, blue) are the strongest, the secondaries (orange, purple, green) next.",
            ],
            choose: [
                "主の色相（hue。主の層の色になる、この作品の有彩色の名）を一つ選ぶ。道具が、色相環の位置で、主の色相と互いに 90° 以上離れた鮮やかな色（表の chroma 25 以上）を、ほかの層に当て、有彩色を3色以上にする。白・黒・灰はほかに使ってよい。",
                "One main hue (hue: a chromatic name of this work, which the main layer takes). The tool gives the other layers vivid colors (table chroma 25 or more) 90° or more apart from it and from each other on the wheel, three chromatic colors or more. White, black and gray may be used besides.",
            ],
            example: both(r#"{"hue":"red"}"#),
        },
    ),
    (
        "D2",
        LawText {
            name: ["彩度の対比", "Contrast of saturation"],
            family: SCHEME,
            source: [
                "Itten『色彩の芸術』(1961) の彩度の対比",
                "Itten, The Art of Color (1961): contrast of saturation",
            ],
            law: [
                "主の層だけを最も鮮やかな色にし、ほかの色の層をくすんだ色か無彩にする。くすんだ色の中に置くと、鮮やかな色がいっそう鮮やかに見える。全ての法則を当てた後に、主の層の描いた鮮やかさが、ほかの全ての層（記述の色の層など、替えない層も含む）の2倍以上であること。",
                "Only the main layer takes the most vivid color; the other colored layers turn dull or achromatic. Among dull colors a vivid one looks more vivid still. Once every law is applied, the main layer, drawn, is at least twice as vivid as every other layer (a layer that keeps a stated color included).",
            ],
            choose: [
                "主の層の色。選べるのは、この作品の有彩色のうち表の chroma が 25 以上の色だけ（白・黒・灰は選べない）。ほかの層のうち、その色の半分より鮮やかな層は、道具が白・灰・黒のうち、描いて地から見え、組み合わせの調和の高いものに替える。",
                "The main layer's color: only chromatic colors of this work with a table chroma of 25 or more (not white, black or gray). Any other layer more vivid than half of it is turned by the tool to white, gray or black, whichever is seen against the ground when drawn and harmonizes best.",
            ],
            example: both(r#"{"vivid":"red"}"#),
        },
    ),
    (
        "D3",
        LawText {
            name: [
                "補色の対比・同時対比",
                "Complementary and simultaneous contrast",
            ],
            family: SCHEME,
            source: [
                "Itten の補色の対比、Chevreul『色彩の同時対比の法則』(1839)",
                "Itten's complementary contrast; Chevreul, The Principles of Harmony and Contrast of Colours (1839)",
            ],
            law: [
                "隣り合う二つの層を補色（色相環の向かい。位置が 150° 以上離れた色）にして、互いを強める。または、強い色の層の隣を灰にして、灰をその補色の側に見せる。",
                "Two neighbouring layers take complementary colors (opposite on the wheel, 150° or more apart) and strengthen each other. Or the neighbour of a strongly colored layer turns gray, and the gray looks tinted toward its complement.",
            ],
            choose: [
                "接する層の組（pair。\"強い色の層-隣の層\" の形で、選べる組だけが並ぶ。強い色の層は一色の有彩色の層）と、隣の層の色（色の表の位置が強い色の向かいにある色か gray）。",
                "A pair of touching layers (pair, as \"strong layer-neighbour\"; only the pairs offered; the strong layer is one chromatic color) and the neighbour's color (a color opposite the strong one in the table's places, or gray).",
            ],
            example: both(r#"{"pair":"1-0","partner_color":"green"}"#),
        },
    ),
    (
        "D4",
        LawText {
            name: ["濃淡の調和", "Harmony of shades"],
            family: SCHEME,
            source: [
                "トーン・オン・トーンとカマイユ（Chevreul の類似の調和）",
                "Ton sur ton and camaïeu (Chevreul's harmony of analogy)",
            ],
            law: [
                "色の付いた層を一つの色にまとめ、層ごとに濃さ（さばき）を変えて、同じ色の濃淡だけで画を組む。",
                "The colored layers share one color, and each takes its own handling, so that the picture is made of the shades of one color.",
            ],
            choose: [
                "一つの色（地と明るさが 0.15 以上違う色）と、その色にする層（2つ以上）ごとの濃さ（dense 濃い・temperate 程よい・faint 薄い。2種以上を使う）。",
                "One color (0.15 or more from the ground in lightness) and, for each layer that takes it (two or more), its handling (dense, temperate, faint; two kinds or more).",
            ],
            example: both(
                r#"{"color":"blue","layers":[{"layer":0,"handling":"dense"},{"layer":1,"handling":"faint"}]}"#,
            ),
        },
    ),
    (
        "D5",
        LawText {
            name: ["類似色の調和", "Harmony of analogous colors"],
            family: SCHEME,
            source: [
                "Chevreul の類似の調和、Itten",
                "Chevreul's harmony of analogy; Itten",
            ],
            law: [
                "色相環で隣り合う色（位置が 120° の弧に収まる色）だけで画をまとめ、穏やかなつながりを作る。",
                "Only neighbouring colors on the wheel (inside a 120° arc) make up the picture, a quiet continuity.",
            ],
            choose: [
                "主の色相（hue。主の層の色になる、この作品の有彩色の名）を一つ選ぶ。道具が、色相環の位置で、主の色相と同じ 120° の弧に収まる色を、ほかの層に当てる（有彩色は2色以上）。白・黒・灰はほかに使ってよい。",
                "One main hue (hue: a chromatic name of this work, which the main layer takes). The tool gives the other layers colors inside the same 120° arc on the wheel (two chromatic colors or more). White, black and gray may be used besides.",
            ],
            example: both(r#"{"hue":"blue"}"#),
        },
    ),
    (
        "D6",
        LawText {
            name: ["視覚混合", "Optical mixing"],
            family: SCHEME,
            source: [
                "Chevreul、Seurat の点描（分割主義）",
                "Chevreul; Seurat's pointillism (divisionism)",
            ],
            law: [
                "散らした小さな物の色を 2〜3 色で順に巡らせ、混ぜずに並べた色を目の中で混ぜる。",
                "Small scattered marks take two or three colors in turn, so that colors laid side by side unmixed mix in the eye.",
            ],
            choose: [
                "散らす層（scatter、物が6つ以上、物の幅 0.08 以下）と、巡らせる 2〜3 色（どれも地と明るさが 0.15 以上違う、違う色）。",
                "A scattered layer (scatter, six marks or more, each 0.08 wide at most) and the two or three colors it takes in turn (different colors, each 0.15 or more from the ground in lightness).",
            ],
            example: both(r#"{"targets":[{"layer":2,"colors":["yellow","orange"]}]}"#),
        },
    ),
    (
        "D7",
        LawText {
            name: ["明暗の塊", "Masses of light and dark"],
            family: SCHEME,
            source: [
                "Dow『Composition』(1899) の濃淡（Notan）",
                "Dow, Composition (1899): notan",
            ],
            law: [
                "地と層を、明・中・暗の三つの明るさの段にまとめ、画面を少数の大きな明暗の塊で組む。",
                "The ground and the layers come together in three levels of lightness, light, middle and dark, so that the canvas is built of a few large masses of light and dark.",
            ],
            choose: [
                "いちばん大きな面積（地）の段（level。light 明・middle 中・dark 暗）を一つ選ぶ。地は今のまま。道具が、各層の色の描いた明るさを、地と合わせてちょうど三つの段（隣の段とは 0.25 以上、同じ段の中は 0.10 以内）に分け、地がその段に入るようにする。",
                "The level of the largest area, the ground (level: light, middle, dark). The ground stays as it is. The tool chooses the layers' colors so that their drawn lightness and the ground's fall in exactly three levels (0.25 or more apart from the next, within 0.10 inside one), with the ground in that level.",
            ],
            example: both(r#"{"level":"dark"}"#),
        },
    ),
];

const SYSTEM_JA: &str = "あなたは、作品の配色を決める係です。
作品は、記述（作者の文）から作った楽譜です。楽譜の層（物）の置き場・並び・大きさは、前の段（法則の段）がすでに決めました。
配色の法則の一覧（18）から、この作品に使う法則を選び、法則ごとの値を選択肢から選んでください。明るさ・面積・濃さの計算と、決まりの検査は、道具がします。

決まり:
1. 主の配色の法則（main_law）を一つ決めます。画を見た人が最初に感じ取る、色の骨組みになる法則です。支える法則の数は決めません。この画ですでに成り立っている法則（一覧に印がある）は、主には選べません。支えには使えます。主には、画の色を変える法則を選びます。画を何も変えない答えは退けられます。
2. 主の層は、前の段が決めた層です（「主の層」に書いた番号）。変えません。
3. 記述が色の言葉で言った層と地は、道具が決めました（「記述の色」に書いたもの）。その色は、どの法則でも替えません（替える答えは退けられます）。
4. 層の要約に fixed がある層は、前の段が色を決めた層です。色を替えてかまいませんが、空気遠近 B15 の遠い層は、地との描いた明るさの差を 0.2 以上で、主の層より小さく保ちます（遠い物ほど地に溶けます）。文様 C2 の層は、地から見えるように保ちます。差し込みの形の層（arranged が plugin）は、色を替えられません。
5. 色の元は一つです: colors（各層の色。B17〜B20 のどれかを使う時だけ書く）か、C8 か、どちらも無し（楽譜の色のまま）。D1・D5・D7 は値を一つ選ぶだけで、ほかの層の色は道具が色相環の位置と描いた明るさで決めます。その上に、B11・B13・B14・B16・C7・C9・D2・D3・D4・D6 が重なります。
6. 地（背景）は画面の大部分を占め、画の色の印象をほとんど決めます（「画面」に割合を書きました）。地の色は今のままです。層の色は、この地の上で選びます。
7. 色の表の looks（見え方）と wheel・place（色相環の位置）は、その名が実際に描く絵具のものです。名と違う色に見える絵具があります（暗い黄がオリーブに見える、など）。補色・類似色・色相の対比・色の和音・寒暖は、名でなく、この位置で決まります。二つの名が同じ絵具の時は、一つの色と数えます。
8. 描いた痕は、表の色より地に近く見えます。細い線ほど、明るさの差も鮮やかさも消えます。層の要約の contrast と chroma は、その層を今の色で描いた時の、地との明るさの差と鮮やかさです。unseen は、その層をその色で描くと地から見えない（描いた明るさの差が 0.15 未満の）色です。答えが名指した層の色が見えない時は、退けられます。名指さない層が見えない時は、道具が、主の法則の色の考えに合う、見える色に替えます。
9. 道具は、濃さ（B13・B14）→ 色（colors か C8 → B11・B16・C9・C7・B18）→ D1〜D7 → 見え方 → 検査 の順に当てます。明るさの決まり（B19・D7）は、描いた明るさで確かめます。決まりに合わない答えは、理由を添えて返されます。
10. reason には、記述の言葉を「」で引いて、主の配色の法則を選んだ理由を1〜2行で書きます。
答えは決まった形の JSON で返します。laws には、使う法則の番号を鍵にして、法則ごとの値を書きます。";

const SYSTEM_EN: &str = "You decide the colors of a work.
The work is a Score made from the description (the author's words). The previous stage (the laws stage) has already decided where the Score's layers (things) are, how they are arranged and how large they are.
From the list of color laws (18), choose the laws this work uses and, for each law, its values from the choices. The tool computes lightness, area and handling and checks the rules.

Rules:
1. Choose one main color law (main_law): the color framework a viewer feels first. The number of laws that support it is not fixed. A law that already holds in this picture (marked in the list) cannot be the main law; it can support. As the main law, choose a law that changes the picture's colors. An answer that changes nothing in the picture is refused.
2. The main layer is the one the previous stage decided (the number under “Main layer”). Keep it.
3. The tool has decided the layers and the ground whose colors the description states in color words (listed under “Stated colors”). No law changes those colors; an answer that does is refused.
4. A layer with fixed in its summary got its color from the previous stage. It may be recolored, but a distant layer of aerial perspective B15 keeps a drawn lightness difference from the ground of 0.2 or more and less than the main layer's (distant things melt into the ground), and a pattern layer of C2 stays seen against the ground. A plugged-in layer (arranged plugin) cannot change its color.
5. The colors come from one source: colors (each layer's color, written only with one of B17 to B20), or C8, or neither (the Score's colors stay). D1, D5 and D7 take one value, and the tool decides the other layers' colors by their places on the color wheel and their drawn lightness. B11, B13, B14, B16, C7, C9, D2, D3, D4 and D6 come on top.
6. The ground (the background) covers most of the canvas and decides most of the picture's impression of color (its share is under “Canvas”). The ground keeps its color; choose the layers' colors on it.
7. In the color table, looks (how it looks) and wheel and place (its place on the color wheel) describe the paint the name actually draws. Some paints look like another color than their name (a dark yellow looks olive, for one). Complements, analogous colors, hue contrast, chords and warm and cool go by these places, not by the names. Two names that draw one paint count as one color.
8. A drawn mark looks closer to the ground than the table says; the thinner the line, the more of its lightness difference and vividness it loses. In a layer's summary, contrast and chroma are the drawn lightness difference from the ground and the drawn vividness of the layer in its current color; unseen lists the colors in which the layer, drawn, would not be seen against the ground (a drawn lightness difference under 0.15). An answer that names a layer in a color that is not seen is refused. A layer the answer does not name that is not seen is recolored by the tool, to a seen color that keeps to the main law's idea of color.
9. The tool applies handling (B13, B14), then color (colors or C8, then B11, B16, C9, C7, B18), then D1 to D7, then what is seen, then the checks. The lightness laws (B19, D7) are checked by the drawn lightness. An answer that breaks the rules comes back with the reason.
10. In reason, quote the description's words in “ ” and say in one or two lines why you chose the main color law.
Return the answer as JSON of the given shape. In laws, key each law you use by its number and write its values.";

const LAYER_NOTE: [&str; 2] = [
    "box は層の痕が占める矩形 [x0, y0, x1, y1]（画面を 0〜1 とする）、mark_size は痕1つの幅と高さ。arranged は並べ方: place は1か所に置く（数が2以上なら同じ所に重ねた束）、row_horizontal・row_vertical・row_diagonal は列、grid は格子、scatter は散らす、fill はほかの形の中に塗り込める形、plugin は差し込みの形（色を替えられない）。",
    "box is the rectangle [x0, y0, x1, y1] the layer's marks cover (the canvas is 0 to 1); mark_size is the width and height of one mark. arranged is how the layer is arranged: place puts it at one spot (with a count of 2 or more, a bundle at that spot), row_horizontal, row_vertical and row_diagonal are rows, grid is a grid, scatter scatters, fill is a shape filled inside another shape, and plugin is a plugged-in shape (its color cannot change).",
];

const FACTS_NOTE: [&str; 2] = [
    "handling は濃さ（さばき: dense 濃い・temperate 程よい・faint 薄い）。area は層の痕が画面に占める割合（%）。contrast は今の色で描いた層の痕と地の明るさの差（0〜1）、chroma はその鮮やかさ。unseen は、その層をその色で描くと地から見えない色。neighbors は痕が接する層。fixed は前の段が色を決めた層（B15 空気遠近・C2 文様。決まり4）。stated は記述が色を言った層。",
    "handling is how densely the marks are laid (dense, temperate, faint). area is the share of the canvas the layer's marks cover (%). contrast is the lightness difference of the layer's marks from the ground, drawn in its current color (0 to 1), and chroma their vividness. unseen lists the colors in which the layer, drawn, would not be seen against the ground. neighbors are the layers its marks touch. fixed is a layer whose color the previous stage decided (B15 aerial perspective, C2 pattern; rule 4). stated is a layer whose color the description states.",
];

const TABLE_NOTE: [&str; 2] = [
    "## この作品の色の表（9つの名が描く絵具。paint は絵具の名、looks は見え方、wheel は色相環の12色の名、place は色相環の位置（度）、lightness は明るさ 0〜1、chroma は鮮やかさ、ground_diff は今の地との明るさの差（表の値）、same_paint_as は同じ絵具を描く名）",
    "## This work's color table (the paints the nine names draw: paint is the paint's name, looks how it looks, wheel its hue among the wheel's twelve, place its place on the wheel in degrees, lightness its lightness from 0 to 1, chroma its vividness, ground_diff its lightness difference from the ground in the table, same_paint_as the names that draw the same paint)",
];

const WHEEL_NOTE: [&str; 2] = [
    "## 色相環（イッテンの12色）\n黄 0°・黄橙 30°・橙 60°・赤橙 90°・赤 120°・赤紫 150°・紫 180°・青紫 210°・青 240°・青緑 270°・緑 300°・黄緑 330° の順に並ぶ。向かい（150° 以上離れた位置）が補色（黄と紫、橙と青、赤と緑）。120° の弧に収まる色が類似色。互いに 90° 以上離れた3色は色相の対比（三原色 黄・赤・青、三間色 橙・紫・緑）。暖は黄から赤紫まで、寒は紫から黄緑まで。白・黒・灰（wheel が無彩）は位置を持たない。",
    "## The color wheel (Itten's twelve hues)\nYellow 0°, yellow-orange 30°, orange 60°, red-orange 90°, red 120°, red-purple 150°, purple 180°, blue-purple 210°, blue 240°, blue-green 270°, green 300° and yellow-green 330°, in this order. Opposite places (150° or more apart) are complements (yellow and purple, orange and blue, red and green). Colors inside a 120° arc are analogous. Three colors each 90° or more apart make a hue contrast (the primaries yellow, red and blue; the secondaries orange, purple and green). Warm runs from yellow to red-purple, cool from purple to yellow-green. White, black and gray (wheel achromatic) have no place.",
];

const ACHROMATIC_WHEEL: [&str; 2] = ["無彩", "achromatic"];

const EXAMPLE_DESCRIPTION: [&str; 2] = [
    "冬の朝、雪の野に一本の木が立ち、枝の実だけが光っていた。",
    "On a winter morning a single tree stood in a snowy field, and only the berries on its branches shone.",
];

/// The example's layers (the prototype's, with what the product shows).
const EXAMPLE_LAYERS: [&str; 3] = [
    r#"{"layer":0,"shape":"line","tool":"brush_thick","count":1,"color":"black","filled":false,"arranged":"place","box":[0.3,0.2,0.7,0.9],"mark_size":[0.7,0.0],"handling":"dense","area":2.1,"contrast":0.31,"chroma":1,"unseen":["gray"],"neighbors":[1]}"#,
    r#"{"layer":1,"shape":"circle","tool":"brush_thin","count":7,"color":"orange","filled":true,"arranged":"place","box":[0.4,0.2,0.6,0.4],"mark_size":[0.03,0.03],"handling":"temperate","area":0.6,"contrast":0.12,"chroma":38,"unseen":["white","yellow","orange"],"neighbors":[0]}"#,
    r#"{"layer":2,"shape":"point","tool":"chalk","count":40,"color":"white","filled":true,"arranged":"scatter","box":[0.0,0.0,1.0,1.0],"mark_size":[0.004,0.004],"handling":"faint","area":0.3,"contrast":0.35,"chroma":2,"unseen":["yellow"],"neighbors":[]}"#,
];

const EXAMPLE_ANSWER: [&str; 2] = [
    r#"{"main_law":"D2","laws":{"D2":{"vivid":"red"},"B19":{"use":true}},"colors":{"layers":[{"layer":0,"color":"black"},{"layer":2,"color":"white"}]},"reason":"「実だけが光っていた」を見せるため、実だけを鮮やかな赤にし、幹と雪は無彩のまま、明暗で地から離した。"}"#,
    r#"{"main_law":"D2","laws":{"D2":{"vivid":"red"},"B19":{"use":true}},"colors":{"layers":[{"layer":0,"color":"black"},{"layer":2,"color":"white"}]},"reason":"To show “only the berries shone”, only the berries take a vivid red; the trunk and the snow stay achromatic and stand apart from the ground in lightness."}"#,
];

const RULE: [&str; 2] = [
    "## この答えの決まり\n主の配色の法則を1つと、それを支える法則を選ぶ（数は決めない）。主には、「この画ですでに成り立っている」の印の無い法則を選ぶ。",
    "## The rule of this answer\nChoose one main color law and the laws that support it (their number is not fixed). As the main law, choose a law without the mark “already holds in this picture”.",
];

fn color_enum() -> Value {
    json!({"type": "string", "enum": COLORS.iter().map(|color| color.as_str()).collect::<Vec<_>>()})
}

fn layer_enum(layers: &[usize]) -> Value {
    json!({"type": "integer", "enum": layers})
}

fn targets(item: Value) -> Value {
    json!({"type": "array", "minItems": 1, "items": item})
}

impl ColorsContext {
    /// The schema of one law's values in this work, or `None` when the work
    /// cannot take it.
    #[allow(clippy::too_many_lines)]
    fn law_schema(&self, law: &str) -> Option<Value> {
        if self.colorable.is_empty() {
            return None;
        }
        let color = color_enum();
        let colors = |least: usize, most: usize| json!({"type": "array", "minItems": least, "maxItems": most, "items": color_enum()});
        let multi = (!self.multi.is_empty()).then(|| layer_enum(&self.multi));
        let graded = (!self.graded.is_empty()).then(|| layer_enum(&self.graded));
        Some(match law {
            "B11" | "B16" => {
                let (least, most) = if law == "B11" { (2, 2) } else { (2, 4) };
                json!({
                    "type": "object",
                    "properties": {"targets": targets(json!({
                        "type": "object",
                        "properties": {"layer": multi?, "colors": colors(least, most)},
                        "required": ["layer", "colors"]
                    }))},
                    "required": ["targets"]
                })
            }
            "B13" => json!({
                "type": "object",
                "properties": {"targets": targets(json!({
                    "type": "object",
                    "properties": {
                        "layer": graded?,
                        "direction": {"type": "string", "enum": ["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"]}
                    },
                    "required": ["layer", "direction"]
                }))},
                "required": ["targets"]
            }),
            "B14" => json!({
                "type": "object",
                "properties": {"layers": {"type": "array", "minItems": 1, "items": graded?}},
                "required": ["layers"]
            }),
            "B17" => {
                json!({"type": "object", "properties": {"accent": color}, "required": ["accent"]})
            }
            "B18" | "B19" => json!({
                "type": "object",
                "properties": {"use": {"type": "boolean"}},
                "required": ["use"]
            }),
            "B20" => json!({
                "type": "object",
                "properties": {"accent_layer": layer_enum(&self.colorable)},
                "required": ["accent_layer"]
            }),
            "C7" => {
                let layers = self.kasane_layers();
                if layers.is_empty() {
                    return None;
                }
                let mut under: Vec<&str> = COLORS.iter().map(|color| color.as_str()).collect();
                under.push("none");
                json!({
                    "type": "object",
                    "properties": {
                        "targets": {"type": "array", "minItems": 1, "maxItems": 2, "items": layer_enum(&layers)},
                        "omote": color,
                        "ura": color_enum(),
                        "naka": {"type": "string", "enum": under},
                        "kasane_name": {"type": "string"},
                        "offset": {"type": "string", "enum": ["small", "medium"]}
                    },
                    "required": ["targets", "omote", "ura", "naka", "kasane_name", "offset"]
                })
            }
            "C8" => json!({
                "type": "object",
                "properties": {
                    "chord": {"type": "string", "enum": ["complement", "triad", "tetrad"]},
                    "assignments": targets(json!({
                        "type": "object",
                        "properties": {"layer": layer_enum(&self.colorable), "color": color},
                        "required": ["layer", "color"]
                    }))
                },
                "required": ["chord", "assignments"]
            }),
            "C9" => {
                // The ground stays (V1), so the strong color takes the main layer.
                let closed = self
                    .first_primitive(self.main)
                    .and_then(area_factor)
                    .is_some();
                if !self.colorable.contains(&self.main) || !self.movable(self.main) || !closed {
                    return None;
                }
                json!({
                    "type": "object",
                    "properties": {
                        "color": {"type": "string", "enum": self.vivid.iter().map(|color| color.as_str()).collect::<Vec<_>>()},
                        "area": {"type": "string", "enum": ["15-30", "30-50"]},
                        "others": {"type": "string", "enum": ["neutral", "keep"]}
                    },
                    "required": ["color", "area", "others"]
                })
            }
            "D1" | "D5" | "D7" => {
                let values = self.feasible.get(law).filter(|values| !values.is_empty())?;
                let key = if law == "D7" { "level" } else { "hue" };
                json!({
                    "type": "object",
                    "properties": {key: {"type": "string", "enum": values}},
                    "required": [key]
                })
            }
            "D2" => {
                let vivid = self.d2_choices();
                if vivid.is_empty() {
                    return None;
                }
                json!({
                    "type": "object",
                    "properties": {"vivid": {"type": "string", "enum": vivid}},
                    "required": ["vivid"]
                })
            }
            "D3" => {
                if self.pairs.is_empty() {
                    return None;
                }
                let pairs: Vec<String> =
                    self.pairs.iter().map(|(a, b)| format!("{a}-{b}")).collect();
                let mut partners: Vec<&str> = WHEEL.iter().map(|color| color.as_str()).collect();
                partners.push("gray");
                json!({
                    "type": "object",
                    "properties": {
                        "pair": {"type": "string", "enum": pairs},
                        "partner_color": {"type": "string", "enum": partners}
                    },
                    "required": ["pair", "partner_color"]
                })
            }
            "D4" => {
                if self.colorable.len() < 2 {
                    return None;
                }
                json!({
                    "type": "object",
                    "properties": {
                        "color": color,
                        "layers": {"type": "array", "minItems": 2, "items": {
                            "type": "object",
                            "properties": {
                                "layer": layer_enum(&self.colorable),
                                "handling": {"type": "string", "enum": ["dense", "temperate", "faint"]}
                            },
                            "required": ["layer", "handling"]
                        }}
                    },
                    "required": ["color", "layers"]
                })
            }
            "D6" => {
                if self.scatter_small.is_empty() {
                    return None;
                }
                json!({
                    "type": "object",
                    "properties": {"targets": targets(json!({
                        "type": "object",
                        "properties": {"layer": layer_enum(&self.scatter_small), "colors": colors(2, 3)},
                        "required": ["layer", "colors"]
                    }))},
                    "required": ["targets"]
                })
            }
            _ => return None,
        })
    }

    /// The layers a kasane may take: deterministic ones whose sentence has no
    /// joint (the copies printed before a sentence would become the previous
    /// shape its joint names).
    fn kasane_layers(&self) -> Vec<usize> {
        let first = self.first_plan_layer();
        self.deterministic
            .iter()
            .copied()
            .filter(|layer| {
                layer
                    .checked_sub(first)
                    .and_then(|k| self.printed.joints.get(k))
                    .is_some_and(Option::is_none)
            })
            .collect()
    }

    fn first_primitive(&self, layer: usize) -> Option<Primitive> {
        let positions = laws::layers(&self.score).remove(&layer)?;
        Some(self.score.instructions[*positions.first()?].primitive)
    }

    /// D2's vivid colors: the chromatic names of a table chroma of 25 or more
    /// whose half the ground is not more vivid than (the ground stays); a
    /// stated main layer only its own.
    fn d2_choices(&self) -> Vec<&'static str> {
        let ground = self.paint(self.ground());
        let ground_allows = |vivid: Color| {
            ground.place.is_none() || ground.chroma <= MUTED_SHARE * self.paint(vivid).chroma
        };
        if self.stated.contains_key(&self.main) {
            let Some(own) = self.first_color(self.main) else {
                return Vec::new();
            };
            if WHEEL.contains(&own) && self.paint(own).chroma >= VIVID_CHROMA && ground_allows(own)
            {
                return vec![own.as_str()];
            }
            return Vec::new();
        }
        if !self.colorable.contains(&self.main) || self.colorable.len() < 2 {
            return Vec::new();
        }
        WHEEL
            .iter()
            .copied()
            .filter(|color| self.paint(*color).chroma >= VIVID_CHROMA && ground_allows(*color))
            .map(Color::as_str)
            .collect()
    }

    /// The laws this work can take, in the request's order.
    fn offered(&self) -> Vec<&'static str> {
        COLOR_LAWS
            .iter()
            .copied()
            .filter(|law| self.law_schema(law).is_some())
            .collect()
    }

    fn handling_of(&self, layer: usize) -> &'static str {
        let positions = laws::layers(&self.score).remove(&layer).unwrap_or_default();
        match positions
            .first()
            .map(|position| self.score.instructions[*position].surface_intensity)
        {
            Some(SurfaceIntensity::Dense) => "dense",
            Some(SurfaceIntensity::Faint) => "faint",
            _ => "temperate",
        }
    }

    fn layer_lines(&self) -> Vec<String> {
        self.summaries
            .iter()
            .map(|summary| {
                let layer = summary.layer;
                let look = self.now.looks.get(&layer);
                let unseen = if self.colorable.contains(&layer) {
                    COLORS
                        .iter()
                        .filter(|color| self.seen(layer, **color) < VISIBLE)
                        .map(|color| color.as_str())
                        .collect()
                } else {
                    Vec::new()
                };
                let line = ColorLayer {
                    summary: summary.clone(),
                    handling: self.handling_of(layer),
                    area: round1(100.0 * look.map_or(0.0, |look| look.ink)),
                    contrast: laws::round3(look.map_or(0.0, |look| look.contrast)),
                    chroma: laws::round_int(look.map_or(0.0, |look| look.chroma)),
                    unseen,
                    neighbors: self
                        .now
                        .neighbors
                        .get(&layer)
                        .map(|near| near.iter().copied().collect())
                        .unwrap_or_default(),
                    fixed: self.fixed.get(&layer).cloned(),
                    stated: self.stated.get(&layer).cloned(),
                };
                serde_json::to_string(&line).unwrap_or_default()
            })
            .collect()
    }

    fn table(&self, at: usize) -> Vec<ColorRow> {
        let ground = self.paint(self.ground()).lightness;
        self.paints
            .iter()
            .map(|paint| ColorRow {
                name: paint.color.as_str(),
                paint: paint.name.clone(),
                looks: paint.looks(at),
                wheel: paint
                    .place
                    .map_or(ACHROMATIC_WHEEL[at], |place| TWELVE[twelve(place)][at]),
                place: paint.place,
                lightness: laws::round2(paint.lightness),
                chroma: laws::round_int(paint.chroma),
                ground_diff: laws::round2((paint.lightness - ground).abs()),
                same_paint_as: self
                    .paints
                    .iter()
                    .filter(|other| other.color != paint.color && other.rgb == paint.rgb)
                    .map(|other| other.color.as_str())
                    .collect(),
            })
            .collect()
    }

    fn message(&self, description: &str, language: ResolvedInstructionLanguage) -> String {
        let at = laws::language_index(language);
        let ja = at == 0;
        let ground = self.ground().as_str();
        let mut lines: Vec<String> = Vec::new();
        lines.push(if ja { "## 記述" } else { "## Description" }.to_owned());
        lines.push(description.to_owned());
        lines.push(String::new());
        lines.push(if ja {
            format!("## 主の層（前の段が決めた）: layer {}", self.main)
        } else {
            format!(
                "## Main layer (decided by the previous stage): layer {}",
                self.main
            )
        });
        lines.push(String::new());
        lines.push(
            if ja {
                "## 記述の色（道具が決めた。替えない）"
            } else {
                "## Stated colors (decided by the tool; they do not change)"
            }
            .to_owned(),
        );
        let positions = laws::layers(&self.score);
        let mut stated: Vec<String> = self
            .stated
            .iter()
            .map(|(layer, word)| {
                let names: Vec<&str> = layer_colors(
                    &self.score,
                    positions.get(layer).map_or(&[][..], Vec::as_slice),
                )
                .into_iter()
                .collect();
                if ja {
                    format!("- layer {layer}: 「{word}」（{}）", names.join("・"))
                } else {
                    format!("- layer {layer}: “{word}” ({})", names.join(", "))
                }
            })
            .collect();
        if let Some(word) = &self.stated_ground {
            stated.push(if ja {
                format!("- 地: 「{word}」（{ground}）")
            } else {
                format!("- ground: “{word}” ({ground})")
            });
        }
        if stated.is_empty() {
            stated.push(if ja { "- なし" } else { "- none" }.to_owned());
        }
        lines.extend(stated);
        lines.push(String::new());
        let ink: f64 = self
            .now
            .looks
            .values()
            .map(|look| look.ink)
            .sum::<f64>()
            .min(1.0);
        lines.push(if ja {
            format!(
                "## 画面（今の画の見積もり）: 層の痕が {}%、地が {}%",
                round1(100.0 * ink),
                round1(100.0 * (1.0 - ink))
            )
        } else {
            format!(
                "## Canvas (estimated from the picture now): the layers' marks {}%, the ground {}%",
                round1(100.0 * ink),
                round1(100.0 * (1.0 - ink))
            )
        });
        lines.push(String::new());
        lines.push(
            if ja {
                "## 楽譜の層（配色の前）"
            } else {
                "## The Score's layers (before the colors)"
            }
            .to_owned(),
        );
        lines.push(if ja {
            format!("{}{}", LAYER_NOTE[at], FACTS_NOTE[at])
        } else {
            format!("{} {}", LAYER_NOTE[at], FACTS_NOTE[at])
        });
        lines.extend(self.layer_lines());
        lines.push(String::new());
        let table = self.table(at);
        let row = table.iter().find(|row| row.name == ground);
        let paint = row.and_then(|row| row.paint.clone());
        let looks = row.map_or(String::new(), |row| row.looks.clone());
        lines.push(match (ja, paint) {
            (true, Some(paint)) => format!("## 地: {ground}（{paint}、{looks}）"),
            (true, None) => format!("## 地: {ground}（{looks}）"),
            (false, Some(paint)) => format!("## Ground: {ground} ({paint}, {looks})"),
            (false, None) => format!("## Ground: {ground} ({looks})"),
        });
        lines.push(String::new());
        lines.push(TABLE_NOTE[at].to_owned());
        lines.extend(
            table
                .iter()
                .map(|row| serde_json::to_string(row).unwrap_or_default()),
        );
        lines.push(String::new());
        lines.push(WHEEL_NOTE[at].to_owned());
        lines.push(String::new());
        lines.push(
            if ja {
                "## 配色の法則の一覧（18）"
            } else {
                "## The color laws (18)"
            }
            .to_owned(),
        );
        let offered = self.offered();
        let labels = if ja {
            ["典拠: ", "法則: ", "選ぶもの: ", "例: "]
        } else {
            ["Source: ", "Law: ", "Choose: ", "Example: "]
        };
        for (law, text) in &LAW_TEXTS {
            if !offered.contains(law) {
                lines.push(if ja {
                    format!(
                        "### {law} {}（{}）（この作品では当てられない）",
                        text.name[0], text.family[0]
                    )
                } else {
                    format!(
                        "### {law} {} ({}) (this work cannot take it)",
                        text.name[1], text.family[1]
                    )
                });
                continue;
            }
            let held = self.already.contains(law);
            lines.push(match (ja, held) {
                (true, true) => format!(
                    "### {law} {}（{}）（この画ですでに成り立っている。主には選べない）",
                    text.name[0], text.family[0]
                ),
                (true, false) => format!("### {law} {}（{}）", text.name[0], text.family[0]),
                (false, true) => format!(
                    "### {law} {} ({}) (already holds in this picture; it cannot be the main law)",
                    text.name[1], text.family[1]
                ),
                (false, false) => format!("### {law} {} ({})", text.name[1], text.family[1]),
            });
            lines.push(format!("{}{}", labels[0], text.source[at]));
            lines.push(format!("{}{}", labels[1], text.law[at]));
            lines.push(format!("{}{}", labels[2], text.choose[at]));
            lines.push(format!("{}{}", labels[3], text.example[at]));
        }
        lines.push(String::new());
        lines.push(
            if ja {
                "## 答え全体の例（この作品と別の記述）"
            } else {
                "## A whole answer (for another description)"
            }
            .to_owned(),
        );
        let labels = if ja {
            ["記述: ", "主の層: layer 1", "層:", "答え: "]
        } else {
            [
                "Description: ",
                "Main layer: layer 1",
                "Layers:",
                "Answer: ",
            ]
        };
        lines.push(format!("{}{}", labels[0], EXAMPLE_DESCRIPTION[at]));
        lines.push(labels[1].to_owned());
        lines.push(labels[2].to_owned());
        lines.extend(EXAMPLE_LAYERS.iter().map(|layer| (*layer).to_owned()));
        lines.push(format!("{}{}", labels[3], EXAMPLE_ANSWER[at]));
        lines.push(String::new());
        lines.push(RULE[at].to_owned());
        lines.join("\n")
    }
}

/// The answer's schema for this work: the main law among the laws that do not
/// already hold, the laws, the layers' colors for B17 to B20 and the reason.
#[must_use]
pub fn colors_response_schema(context: &ColorsContext) -> Value {
    let mut laws = Map::new();
    let mut order = Vec::new();
    for law in COLOR_LAWS {
        if let Some(schema) = context.law_schema(law) {
            laws.insert(law.to_owned(), schema);
            order.push(law);
        }
    }
    let main: Vec<&str> = order
        .iter()
        .copied()
        .filter(|law| !context.already.contains(law))
        .collect();
    let mut properties = Map::new();
    properties.insert(
        "main_law".to_owned(),
        json!({"type": "string", "enum": main}),
    );
    properties.insert(
        "laws".to_owned(),
        json!({"type": "object", "propertyOrdering": order, "properties": laws}),
    );
    let mut ordering = vec!["main_law", "laws"];
    if order.iter().any(|law| SOURCE_LAWS.contains(law)) {
        properties.insert(
            "colors".to_owned(),
            json!({
                "type": "object",
                "properties": {"layers": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"layer": layer_enum(&context.colorable), "color": color_enum()},
                    "required": ["layer", "color"]
                }}},
                "required": ["layers"]
            }),
        );
        ordering.push("colors");
    }
    properties.insert("reason".to_owned(), json!({"type": "string"}));
    ordering.push("reason");
    json!({
        "type": "object",
        "propertyOrdering": ordering,
        "properties": properties,
        "required": ["main_law", "laws", "reason"]
    })
}

/// Build the `choose_colors` request for a work. It fails when the work has
/// no law to take as the main law: there is nothing to choose.
pub fn build_colors_prompt(
    description: &str,
    context: &ColorsContext,
    language: ResolvedInstructionLanguage,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    crate::prompts::require_nonempty("description", description)?;
    crate::prompts::require_within("description", description.len(), limits.max_source_bytes)?;
    let schema = colors_response_schema(context);
    if schema["properties"]["main_law"]["enum"]
        .as_array()
        .is_none_or(Vec::is_empty)
    {
        return Err(PromptError::EmptyField { field: "colors" });
    }
    let system = match language {
        ResolvedInstructionLanguage::Ja => SYSTEM_JA,
        ResolvedInstructionLanguage::En => SYSTEM_EN,
    }
    .to_owned();
    crate::prompts::finish_prompt(LlmPrompt {
        schema_id: crate::prompts::LLM_PROMPT_SCHEMA_ID.to_owned(),
        prompt_id: COLORS_PROMPT_ID.to_owned(),
        stage: LlmStage::ChooseColors,
        action_name: LlmStage::ChooseColors.action_name().to_owned(),
        instruction_language: language,
        system,
        message: context.message(description, language),
        response_schema: schema,
        prompt_digest: String::new(),
        saijiki_asset_id: None,
        saijiki_asset_digest: None,
        macro_catalog_digest: None,
        base_source_digest: None,
        base_compiler_lock_digest: None,
    })
}

/// The request again with the tool's reply to the answer it refused: the
/// original message and the latest reason only, as the prototype resent it
/// (the laws stage also repeats the refused answer; this stage does not).
pub(crate) fn with_colors_feedback(
    prompt: LlmPrompt,
    refusal: &Refusal,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    laws::with_laws_feedback(prompt, refusal, None, &[], limits)
}

// --- the answer --------------------------------------------------------------------------------

/// A note the tool keeps about how it applied the color laws.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ColorNote {
    pub code: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub layer: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub color: Option<&'static str>,
}

/// A conformed answer.
#[derive(Clone, Debug, PartialEq)]
struct Answer {
    main_law: String,
    laws: BTreeMap<&'static str, Value>,
    /// The layers' colors, read only with one of B17 to B20.
    colors: Option<Vec<(usize, Color)>>,
}

fn law_key(law: &str) -> Option<&'static str> {
    COLOR_LAWS.iter().copied().find(|found| *found == law)
}

fn color_of(value: &Value) -> Option<Color> {
    value.as_str().and_then(color_named)
}

fn list_layers(value: &Value) -> Vec<usize> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .map(layer_number)
        .collect()
}

fn target_layers(value: &Value) -> Vec<usize> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .map(|target| layer_number(&target["layer"]))
        .collect()
}

/// The layers a law names, as the prototype collected them for a law that
/// names one layer twice; D4 and D6 too, which it did not check.
fn law_layers(law: &str, value: &Value) -> Vec<usize> {
    match law {
        "B11" | "B13" | "B16" | "D6" => target_layers(&value["targets"]),
        "B14" => list_layers(&value["layers"]),
        "B20" => vec![layer_number(&value["accent_layer"])],
        "C7" => list_layers(&value["targets"]),
        "C8" => target_layers(&value["assignments"]),
        "D4" => target_layers(&value["layers"]),
        _ => Vec::new(),
    }
}

/// The two layers of a D3 pair, `"strong-partner"`.
fn pair_of(value: &Value) -> Option<(usize, usize)> {
    let (strong, partner) = value["pair"].as_str()?.split_once('-')?;
    Some((strong.parse().ok()?, partner.parse().ok()?))
}

/// The layers an answer recolors, each by the first law that names it.
fn named(answer: &Answer, main: usize) -> BTreeMap<usize, &'static str> {
    let mut out: BTreeMap<usize, &'static str> = BTreeMap::new();
    for (layer, _) in answer.colors.iter().flatten() {
        out.entry(*layer).or_insert("colors");
    }
    for law in ["B11", "B16", "D6"] {
        if let Some(value) = answer.laws.get(law) {
            for layer in target_layers(&value["targets"]) {
                out.entry(layer).or_insert(law);
            }
        }
    }
    if let Some(value) = answer.laws.get("C8") {
        for layer in target_layers(&value["assignments"]) {
            out.entry(layer).or_insert("C8");
        }
    }
    if let Some(value) = answer.laws.get("C7") {
        for layer in list_layers(&value["targets"]) {
            out.entry(layer).or_insert("C7");
        }
    }
    if let Some((_, partner)) = answer.laws.get("D3").and_then(pair_of) {
        out.entry(partner).or_insert("D3");
    }
    if let Some(value) = answer.laws.get("D4") {
        for layer in target_layers(&value["layers"]) {
            out.entry(layer).or_insert("D4");
        }
    }
    if answer.laws.contains_key("D2") {
        out.entry(main).or_insert("D2");
    } else if answer.laws.contains_key("C9") {
        out.entry(main).or_insert("C9");
    }
    out
}

/// Why a layer's color is kept, in both languages.
fn kept_because(context: &ColorsContext, layer: usize) -> Option<(String, String)> {
    if let Some(word) = context.stated.get(&layer) {
        return Some((
            format!("記述が言った色（「{word}」）"),
            format!("in a color the description states (“{word}”)"),
        ));
    }
    context.plugins.contains(&layer).then(|| {
        (
            "差し込みの形の色".to_owned(),
            "a plugged-in shape whose color cannot change".to_owned(),
        )
    })
}

/// A gradation (B13, B14) runs through three marks or more.
fn few_marks(law: &str, layer: usize, instruction: &Instruction) -> Result<(), Refusal> {
    let count = count_of(instruction);
    if u64::from(count) >= GRADED_MARKS {
        return Ok(());
    }
    Err(refusal(
        "few_marks",
        format!("{law}: layer {layer} の痕は {count} 個。薄れの推移には3個以上の痕が要る"),
        format!("{law}: layer {layer} has {count} marks; a gradation needs three or more"),
    ))
}

/// Read an answer and check it against the schema and the prototype's rules.
fn check(answer: &Value, context: &ColorsContext) -> Result<(Answer, Vec<ColorNote>), Refusal> {
    let schema = colors_response_schema(context);
    conform(answer, &schema, "answer")?;
    let allowed = &schema["properties"]["laws"]["properties"];
    let given = answer["laws"].as_object().cloned().unwrap_or_default();
    let main_law = answer["main_law"].as_str().unwrap_or_default().to_owned();
    let mut notes = Vec::new();
    let mut laws: BTreeMap<&'static str, Value> = BTreeMap::new();
    if given.is_empty() {
        return Err(refusal(
            "no_laws",
            "laws が空。主の配色の法則を入れる".to_owned(),
            "laws is empty; put the main color law in it".to_owned(),
        ));
    }
    for (law, value) in &given {
        let Some(key) = law_key(law).filter(|key| allowed.get(*key).is_some()) else {
            return Err(refusal(
                "unknown_law",
                format!(
                    "{law} はこの作品の配色の段では使えない（当てる層が無いか、配色の段の法則でない）"
                ),
                format!(
                    "{law} cannot be used in this work's color stage (no layer can take it, or it is no color law)"
                ),
            ));
        };
        laws.insert(key, value.clone());
    }
    if !laws.keys().any(|law| *law == main_law) {
        return Err(refusal(
            "main_absent",
            format!("主の配色の法則 {main_law} が laws に無い"),
            format!("the main color law {main_law} is not in laws"),
        ));
    }
    for law in ["B18", "B19"] {
        if laws
            .get(law)
            .is_some_and(|value| value["use"] != Value::Bool(true))
        {
            return Err(refusal(
                "use_false",
                format!("{law} の use は true にする（使わないなら laws から外す）"),
                format!("{law}'s use is true (drop it from laws to leave it out)"),
            ));
        }
    }
    let colors: Option<Vec<(usize, Color)>> =
        answer["colors"]["layers"].as_array().map(|entries| {
            entries
                .iter()
                .filter_map(|entry| {
                    Some((layer_number(&entry["layer"]), color_of(&entry["color"])?))
                })
                .collect()
        });
    // The layers' colors are read only with a law that takes them.
    let colors = if colors.is_some() && !laws.keys().any(|law| SOURCE_LAWS.contains(law)) {
        notes.push(ColorNote {
            code: "colors_unread",
            layer: None,
            color: None,
        });
        None
    } else {
        colors
    };
    if colors.is_some() && laws.contains_key("C8") {
        return Err(refusal(
            "two_sources",
            "色の元は一つ。colors と C8 を両方は使えない".to_owned(),
            "one source of colors: colors and C8 cannot both be used".to_owned(),
        ));
    }
    for (law, value) in &laws {
        let layers = law_layers(law, value);
        let distinct: BTreeSet<&usize> = layers.iter().collect();
        if distinct.len() != layers.len() {
            return Err(refusal(
                "named_twice",
                format!("{law} が同じ層を二度名指している"),
                format!("{law} names the same layer twice"),
            ));
        }
    }
    if let (Some(d1), Some(d5)) = (laws.get("D1"), laws.get("D5"))
        && d1["hue"] != d5["hue"]
    {
        return Err(refusal(
            "two_hues",
            "D1 と D5 の主の色相が違う。主の色相は一つ".to_owned(),
            "D1 and D5 name different main hues; the main hue is one".to_owned(),
        ));
    }
    let answer = Answer {
        main_law,
        laws,
        colors,
    };
    // A layer named with exactly the one color it has keeps it.
    let mut keeps: BTreeMap<usize, Color> = BTreeMap::new();
    for (layer, color) in answer.colors.iter().flatten() {
        keeps.entry(*layer).or_insert(*color);
    }
    if let Some(vivid) = answer
        .laws
        .get("D2")
        .and_then(|value| color_of(&value["vivid"]))
    {
        keeps.entry(context.main).or_insert(vivid);
    }
    let positions = laws::layers(&context.score);
    for (layer, law) in named(&answer, context.main) {
        let Some((ja, en)) = kept_because(context, layer) else {
            continue;
        };
        let now = layer_colors(
            &context.score,
            positions.get(&layer).map_or(&[][..], Vec::as_slice),
        );
        let same = keeps
            .get(&layer)
            .is_some_and(|color| now.len() == 1 && now.contains(color.as_str()));
        if !same {
            return Err(refusal(
                "kept_color",
                format!("layer {layer} は{ja}なので、{law} で色を替えない"),
                format!("layer {layer} is {en}, so {law} does not recolor it"),
            ));
        }
    }
    Ok((answer, notes))
}

/// What the color laws left: the Score and what the print writes of it.
#[derive(Clone, Debug)]
struct Painted {
    score: Score,
    notes: Vec<ColorNote>,
    /// Colors in turn (the colors, and whether they shift once).
    cycles: BTreeMap<usize, (Vec<Color>, bool)>,
    fades: BTreeMap<usize, FadeDirection>,
    handled: BTreeSet<usize>,
    resized: BTreeSet<usize>,
    filled: BTreeSet<usize>,
    moved: BTreeSet<usize>,
    /// The colors a kasane lays under a layer, from the lowest.
    kasane: BTreeMap<usize, Vec<Color>>,
}

/// How the tool ranks colors it chooses: whether the main layer is recolored,
/// the estimated harmony (nine decimals) and how many layers change.
type SearchKey = (bool, f64, usize);

/// The tool applying one answer to a copy of the Score.
struct Painting<'a> {
    context: &'a ColorsContext,
    answer: &'a Answer,
    /// A trial of a value the tool decides: no layer is drawn again.
    trial: bool,
    out: Painted,
    tool_assigned: BTreeSet<usize>,
    chosen_by_answer: BTreeSet<usize>,
    /// The layers whose handling, size or surface changed, drawn again, and
    /// the first color of each layer it was drawn with.
    redrawn: Option<Drawing>,
    redrawn_first: BTreeMap<usize, Color>,
}

impl<'a> Painting<'a> {
    fn new(context: &'a ColorsContext, answer: &'a Answer, trial: bool) -> Self {
        Self {
            context,
            answer,
            trial,
            out: Painted {
                score: context.score.clone(),
                notes: Vec::new(),
                cycles: BTreeMap::new(),
                fades: BTreeMap::new(),
                handled: BTreeSet::new(),
                resized: BTreeSet::new(),
                filled: BTreeSet::new(),
                moved: BTreeSet::new(),
                kasane: BTreeMap::new(),
            },
            tool_assigned: BTreeSet::new(),
            chosen_by_answer: BTreeSet::new(),
            redrawn: None,
            redrawn_first: BTreeMap::new(),
        }
    }

    fn law(&self, law: &str) -> Option<&'a Value> {
        self.answer.laws.get(law)
    }

    fn positions(&self, layer: usize) -> Vec<usize> {
        laws::layers(&self.out.score)
            .remove(&layer)
            .unwrap_or_default()
    }

    /// A layer's colors, by name.
    fn colors_of(&self, layer: usize) -> Vec<Color> {
        layer_colors(&self.out.score, &self.positions(layer))
            .into_iter()
            .filter_map(color_named)
            .collect()
    }

    fn first_color(&self, layer: usize) -> Option<Color> {
        Some(self.out.score.instructions[*self.positions(layer).first()?].color)
    }

    fn protected(&self, layer: usize) -> bool {
        kept_because(self.context, layer).is_some()
    }

    fn note(&mut self, code: &'static str, layer: Option<usize>, color: Option<Color>) {
        self.out.notes.push(ColorNote {
            code,
            layer,
            color: color.map(Color::as_str),
        });
    }

    fn set_layer_color(&mut self, layer: usize, color: Color) {
        for position in self.positions(layer) {
            paint_instruction(&mut self.out.score.instructions[position], color);
        }
        self.out.cycles.remove(&layer);
    }

    fn only(&self, layer: usize, law: &str) -> Result<usize, Refusal> {
        let found = self.positions(layer);
        match found.as_slice() {
            [position] => Ok(*position),
            _ => Err(refusal(
                "layer_split",
                format!(
                    "{law}: layer {layer} はすでに {} 個の指示に分かれていて、この法則を当てられない",
                    found.len()
                ),
                format!(
                    "{law}: layer {layer} is already {} instructions and this law cannot take it",
                    found.len()
                ),
            )),
        }
    }

    /// Whether a layer's handling, size or surface changed, so that it is
    /// drawn again. A faded layer is not: the estimate reads a layer's marks
    /// by one opacity, which a fade's faintest marks would set.
    fn reshaped(&self, layer: usize) -> bool {
        self.out.handled.contains(&layer)
            || self.out.resized.contains(&layer)
            || self.out.filled.contains(&layer)
    }

    /// Draw the Score as painted so far, for the layers it reshaped.
    fn redraw(&mut self) {
        let mut shares = Shares::default();
        self.redrawn = self.context.painter.drawing(&self.out.score, &mut shares);
        self.redrawn_first = self.colors_now();
    }

    /// How a layer drawn again looks in a color: when it was reshaped and the
    /// color is the one it was drawn again in.
    fn redrawn_look(&self, layer: usize, color: Color) -> Option<&Look> {
        if !self.reshaped(layer) || self.redrawn_first.get(&layer) != Some(&color) {
            return None;
        }
        self.redrawn
            .as_ref()
            .and_then(|drawing| drawing.looks.get(&layer))
    }

    /// How far a layer drawn in a color stands from the ground: drawn again
    /// when its handling, size or surface changed.
    fn seen(&self, layer: usize, color: Color) -> f64 {
        if let Some(look) = self.redrawn_look(layer, color) {
            return if look.read { look.contrast } else { 1.0 };
        }
        self.context.seen(layer, color)
    }

    /// The drawn chroma of a layer in a color.
    fn chroma(&self, layer: usize, color: Color) -> f64 {
        match self.context.look(layer, color) {
            Some(look) if look.read => look.chroma,
            _ => self.context.paint(color).chroma,
        }
    }

    /// The drawn chroma of a layer's most vivid color, from the picture drawn
    /// again when the layer was.
    fn drawn_chroma(&self, layer: usize) -> f64 {
        self.colors_of(layer)
            .into_iter()
            .map(|color| match self.redrawn_look(layer, color) {
                Some(look) if look.read => look.chroma,
                _ => self.chroma(layer, color),
            })
            .fold(0.0, f64::max)
    }

    fn ground(&self) -> Color {
        self.out.score.background
    }

    /// A refusal for a color that is not seen.
    fn unseen(&self, layer: usize, color: Color) -> Refusal {
        let ground = self.ground().as_str();
        let drawn = self.seen(layer, color);
        let table = self.context.table_difference(color);
        let name = color.as_str();
        refusal(
            "invisible_color",
            format!(
                "layer {layer} の {name} は、描くと地 {ground} からの明るさの差がおよそ {drawn:.2} で見えない（表の差 {table:.2}）。地と明るさがもっと違う色にする"
            ),
            format!(
                "layer {layer} in {name}, drawn, stands about {drawn:.2} from the ground {ground} in lightness and is not seen (the table says {table:.2}); take a color farther from the ground"
            ),
        )
    }

    fn run(mut self) -> Result<Painted, Refusal> {
        self.gradation()?;
        self.color()?;
        self.d_laws()?;
        let layers: Vec<usize> = self.context.layers().collect();
        if !self.trial && layers.iter().any(|layer| self.reshaped(*layer)) {
            self.redraw();
        }
        self.visible_fix()?;
        // A reshaped layer the tool recolored to be seen is drawn again in
        // its new color before the checks read it.
        if self.redrawn.is_some()
            && layers.iter().any(|layer| {
                self.reshaped(*layer)
                    && self.redrawn_first.get(layer) != self.first_color(*layer).as_ref()
            })
        {
            self.redraw();
        }
        self.check_kept()?;
        self.check_colors()?;
        self.check_aerial()?;
        self.check_d2()?;
        self.check_limits()?;
        if !self.trial && self.out.score == self.context.score {
            return Err(refusal(
                "no_change",
                "答えは画を何も変えない。画の色か濃さを変える法則と値にする".to_owned(),
                "the answer changes nothing in the picture; choose laws and values that change its colors or handling".to_owned(),
            ));
        }
        Ok(self.out)
    }

    // --- handling (B13, B14) --------------------------------------------------------------------

    fn gradation(&mut self) -> Result<(), Refusal> {
        let units = self.context.units;
        if let Some(value) = self.law("B13") {
            for target in value["targets"].as_array().into_iter().flatten() {
                let layer = layer_number(&target["layer"]);
                let direction = target["direction"].as_str().unwrap_or_default();
                let position = self.only(layer, "B13")?;
                let instruction = &self.out.score.instructions[position];
                if !laws::is_row(instruction) {
                    return Err(refusal(
                        "not_row",
                        format!(
                            "B13: layer {layer} は列でない（格子・1個・散らす・一つずつに開いた層には使えない）"
                        ),
                        format!(
                            "B13: layer {layer} is not a row (a grid, a single mark, a scatter or a layer opened into marks cannot take it)"
                        ),
                    ));
                }
                few_marks("B13", layer, instruction)?;
                let centers = laws::mark_centers(instruction, units).unwrap_or_default();
                let (Some(first), Some(last)) = (centers.first(), centers.last()) else {
                    return Err(refusal(
                        "not_row",
                        format!("B13: layer {layer} は列でない"),
                        format!("B13: layer {layer} is not a row"),
                    ));
                };
                let (toward, along) = match direction {
                    "left_to_right" => ("right", last[0] - first[0]),
                    "right_to_left" => ("left", last[0] - first[0]),
                    "top_to_bottom" => ("bottom", last[1] - first[1]),
                    _ => ("top", last[1] - first[1]),
                };
                if along.abs() < 1e-6 {
                    return Err(refusal(
                        "no_direction",
                        format!(
                            "B13: 列の向きに {toward} が無い（横の列には left・right、縦の列には top・bottom）"
                        ),
                        format!(
                            "B13: the row does not run toward {toward} (a horizontal row takes left or right, a vertical one top or bottom)"
                        ),
                    ));
                }
                let fade = FadeDirection::ALL
                    .into_iter()
                    .find(|fade| fade.as_str() == direction)
                    .unwrap_or(FadeDirection::LeftToRight);
                if let Some(arrangement) =
                    self.out.score.instructions[position].arrangement.as_mut()
                {
                    arrangement.fade = Fade::Directional;
                }
                self.out.fades.insert(layer, fade);
            }
        }
        if let Some(value) = self.law("B14") {
            for layer in list_layers(&value["layers"]) {
                let position = self.only(layer, "B14")?;
                let instruction = &self.out.score.instructions[position];
                if !(laws::is_row(instruction) || laws::is_scatter(instruction))
                    || count_of(instruction) < 2
                {
                    return Err(refusal(
                        "not_row_or_scatter",
                        format!("B14: layer {layer} は散らす層か列でない"),
                        format!("B14: layer {layer} is neither a scattered layer nor a row"),
                    ));
                }
                few_marks("B14", layer, instruction)?;
                if let Some(arrangement) =
                    self.out.score.instructions[position].arrangement.as_mut()
                {
                    arrangement.fade = Fade::Outward;
                }
                self.out.fades.insert(layer, FadeDirection::Outward);
            }
        }
        Ok(())
    }

    // --- color --------------------------------------------------------------------------------

    fn row_or_grid(instruction: &Instruction) -> bool {
        laws::is_row(instruction)
            || matches!(
                laws::recipe(instruction),
                Some(inku_score::ResolvedPlacementRecipe::Grid { .. })
            ) && count_of(instruction) >= 2
    }

    fn color(&mut self) -> Result<(), Refusal> {
        if let Some(colors) = &self.answer.colors {
            let mut seen = BTreeSet::new();
            for (layer, color) in colors {
                if !seen.insert(*layer) {
                    return Err(refusal(
                        "colored_twice",
                        format!("colors で layer {layer} に色を二度当てている"),
                        format!("colors gives layer {layer} a color twice"),
                    ));
                }
                self.set_layer_color(*layer, *color);
            }
        } else if let Some(value) = self.law("C8") {
            let mut assigned: Vec<(usize, Color)> = Vec::new();
            for entry in value["assignments"].as_array().into_iter().flatten() {
                let layer = layer_number(&entry["layer"]);
                let Some(color) = color_of(&entry["color"]) else {
                    continue;
                };
                if assigned.iter().any(|(found, _)| *found == layer) {
                    return Err(refusal(
                        "colored_twice",
                        format!("layer {layer} に色を二度当てている"),
                        format!("layer {layer} takes a color twice"),
                    ));
                }
                if self.seen(layer, color) < VISIBLE {
                    return Err(self.unseen(layer, color));
                }
                assigned.push((layer, color));
            }
            for (layer, color) in assigned {
                self.set_layer_color(layer, color);
            }
        }
        if let Some(value) = self.law("B11") {
            for target in value["targets"].as_array().into_iter().flatten() {
                let layer = layer_number(&target["layer"]);
                let position = self.only(layer, "B11")?;
                if !Self::row_or_grid(&self.out.score.instructions[position]) {
                    let arranged = self
                        .context
                        .summary(layer)
                        .and_then(|summary| summary.arranged)
                        .unwrap_or("");
                    return Err(refusal(
                        "not_row_or_grid",
                        format!(
                            "B11: layer {layer} は列か格子でない（{arranged}）。ほかの層を選ぶ"
                        ),
                        format!(
                            "B11: layer {layer} is not a row or a grid ({arranged}); choose another layer"
                        ),
                    ));
                }
                let colors: Vec<Color> = target["colors"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(color_of)
                    .collect();
                let [first, second] = colors.as_slice() else {
                    continue;
                };
                if first == second {
                    return Err(refusal(
                        "same_colors",
                        "B11 の2色は違う色にする".to_owned(),
                        "B11's two colors are different colors".to_owned(),
                    ));
                }
                let instruction = &mut self.out.score.instructions[position];
                instruction.color = *first;
                if let Some(arrangement) = instruction.arrangement.as_mut() {
                    arrangement.color_cycle = vec![*first, *second];
                }
                self.out
                    .cycles
                    .insert(layer, (vec![*first, *second], false));
            }
        }
        if let Some(value) = self.law("B16") {
            for target in value["targets"].as_array().into_iter().flatten() {
                let layer = layer_number(&target["layer"]);
                let position = self.only(layer, "B16")?;
                if !Self::row_or_grid(&self.out.score.instructions[position]) {
                    return Err(refusal(
                        "not_row_or_grid",
                        format!(
                            "B16: layer {layer} は列か格子でない（散らす層では色の順が画面の順にならない）"
                        ),
                        format!(
                            "B16: layer {layer} is not a row or a grid (a scatter's colors do not follow the canvas)"
                        ),
                    ));
                }
                let mut ordered: Vec<Color> = Vec::new();
                for color in target["colors"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(color_of)
                {
                    if !ordered.contains(&color) {
                        ordered.push(color);
                    }
                }
                // Light to dark (a stable sort keeps the answer's order of equals).
                ordered.sort_by(|a, b| {
                    self.context
                        .paint(*b)
                        .lightness
                        .total_cmp(&self.context.paint(*a).lightness)
                });
                if ordered.len() < 2 {
                    if let Some(color) = ordered.first() {
                        self.set_layer_color(layer, *color);
                    }
                    continue;
                }
                let count = count_of(&self.out.score.instructions[position]) as usize;
                let n = ordered.len();
                let blocks: Vec<Color> = (0..count)
                    .map(|k| ordered[(k * n / count.max(1)).min(n - 1)])
                    .collect();
                let instruction = &mut self.out.score.instructions[position];
                instruction.color = blocks[0];
                if let Some(arrangement) = instruction.arrangement.as_mut() {
                    arrangement.color_cycle = blocks;
                }
                self.out.cycles.insert(layer, (ordered, true));
            }
        }
        if self.law("C9").is_some() {
            self.c9()?;
        }
        if self.law("C7").is_some() {
            self.c7()?;
        }
        if self.law("B18").is_some() {
            self.b18()?;
        }
        Ok(())
    }

    /// The area of a layer's marks in short-edge units squared, as the
    /// prototype counted it: a closed shape its width by its height by its
    /// shape's factor, a line a hundredth of its length, a point a little.
    fn area(&self, layer: usize) -> f64 {
        let units = self.context.units;
        self.positions(layer)
            .into_iter()
            .map(|position| {
                let instruction = &self.out.score.instructions[position];
                let (hx, hy) = laws::extent(instruction, units);
                let one = match area_factor(instruction.primitive) {
                    Some(factor) => factor * (2.0 * hx) * (2.0 * hy),
                    None if laws::is_line(instruction.primitive) => {
                        laws::py_max(2.0 * hx, 2.0 * hy) * 0.01
                    }
                    None => 0.0001,
                };
                f64::from(count_of(instruction)) * one
            })
            .sum()
    }

    /// The neutral farthest from the ground in lightness.
    fn neutral_for_ground(&self) -> Color {
        let ground = self.context.paint(self.ground()).lightness;
        let mut best = Color::White;
        for color in [Color::White, Color::Black, Color::Gray] {
            let far = |c: Color| (self.context.paint(c).lightness - ground).abs();
            if far(color) > far(best) {
                best = color;
            }
        }
        best
    }

    fn c9(&mut self) -> Result<(), Refusal> {
        let value = self.law("C9").cloned().unwrap_or_default();
        let Some(color) = color_of(&value["color"]) else {
            return Ok(());
        };
        let units = self.context.units;
        let main = self.context.main;
        let positions = self.positions(main);
        let Some(first) = positions.first() else {
            return Err(refusal(
                "no_main",
                "C9: 主の層が無い".to_owned(),
                "C9: there is no main layer".to_owned(),
            ));
        };
        let primitive = self.out.score.instructions[*first].primitive;
        let Some(_) = area_factor(primitive) else {
            return Err(refusal(
                "not_closed",
                format!("C9: 主の層は {} で塗れない", primitive.as_str()),
                format!(
                    "C9: the main layer is a {} and cannot be filled",
                    primitive.as_str()
                ),
            ));
        };
        let target = if value["area"] == "15-30" {
            C9_SMALL
        } else {
            C9_LARGE
        };
        let area = self.area(main);
        let canvas = units.x * units.y;
        let wanted = if area > 0.0 {
            (target * canvas / area).sqrt()
        } else {
            1.0
        };
        let largest = positions
            .iter()
            .map(|position| {
                2.0 * laws::largest_extent(&self.out.score.instructions[*position], units)
            })
            .fold(0.0, f64::max);
        let factor = if largest > 0.0 {
            wanted.min(C9_CAP / largest)
        } else {
            wanted
        };
        for position in &positions {
            let instruction = &mut self.out.score.instructions[*position];
            paint_instruction(instruction, color);
            instruction.filled = true;
            laws::scale_geometry(instruction, factor);
            if let Some(region) = laws::anchor_region(instruction) {
                #[allow(clippy::float_cmp)]
                if region[0] == region[2] {
                    let half = laws::largest_extent(instruction, units);
                    let (hx, hy) = (half / units.x, half / units.y);
                    let x = laws::clamp_between(region[0], hx, 1.0 - hx);
                    let y = laws::clamp_between(region[1], hy, 1.0 - hy);
                    #[allow(clippy::float_cmp)]
                    if x != region[0] || y != region[1] {
                        laws::set_point_region(instruction, x, y);
                        self.out.moved.insert(main);
                    }
                }
            }
        }
        self.out.cycles.remove(&main);
        self.out.filled.insert(main);
        #[allow(clippy::float_cmp)]
        if factor != 1.0 {
            self.out.resized.insert(main);
        }
        if factor < wanted {
            self.note("c9_capped", Some(main), Some(color));
        }
        let ground = self.context.paint(self.ground()).lightness;
        let neutral = self.neutral_for_ground();
        let neutralize = value["others"] == "neutral";
        let others: Vec<usize> = self
            .context
            .layers()
            .filter(|layer| *layer != main)
            .collect();
        for layer in others {
            // A layer whose color is kept keeps it (the prototype turned a stated
            // color neutral and then refused the answer for it).
            if self.protected(layer) {
                continue;
            }
            let mut changed = false;
            for position in self.positions(layer) {
                let instruction = &mut self.out.score.instructions[position];
                let lightness = self.context.paints[index_of(instruction.color)].lightness;
                if neutralize || (lightness - ground).abs() < C9_NEUTRAL {
                    paint_instruction(instruction, neutral);
                    changed = true;
                }
            }
            if changed {
                self.out.cycles.remove(&layer);
            }
        }
        Ok(())
    }

    fn c7(&mut self) -> Result<(), Refusal> {
        let value = self.law("C7").cloned().unwrap_or_default();
        let offset = if value["offset"] == "medium" {
            KASANE_MEDIUM
        } else {
            KASANE_SMALL
        };
        let (Some(omote), Some(ura)) = (color_of(&value["omote"]), color_of(&value["ura"])) else {
            return Ok(());
        };
        let mut under: Vec<(Color, f64)> = vec![(ura, offset)];
        if let Some(naka) = color_of(&value["naka"]) {
            under.push((naka, offset / 2.0));
        }
        let mut targets: Vec<usize> = Vec::new();
        for layer in list_layers(&value["targets"]) {
            if !targets.contains(&layer) {
                targets.push(layer);
            }
        }
        let marks = |painting: &Self, layer: usize| -> u64 {
            painting
                .positions(layer)
                .into_iter()
                .map(|position| u64::from(count_of(&painting.out.score.instructions[position])))
                .sum()
        };
        let total: u64 = self
            .out
            .score
            .instructions
            .iter()
            .map(|instruction| u64::from(count_of(instruction)))
            .sum();
        let layers_under = under.len() as u64;
        let added: u64 = targets
            .iter()
            .map(|layer| marks(self, *layer) * layers_under)
            .sum();
        if total + added > MAX_MARKS {
            targets.truncate(1);
            self.note("c7_first_only", targets.first().copied(), None);
            let first = targets.first().map_or(0, |layer| marks(self, *layer));
            if total + first * layers_under > MAX_MARKS {
                return Err(refusal(
                    "too_many_marks",
                    format!("C7: 重ねると痕の上限 {MAX_MARKS} を超える。数の少ない層を選ぶ"),
                    format!(
                        "C7: the layered copies pass the limit of {MAX_MARKS} marks; choose a layer of fewer marks"
                    ),
                ));
            }
        }
        for layer in targets {
            let position = self.only(layer, "C7")?;
            let top = &mut self.out.score.instructions[position];
            paint_instruction(top, omote);
            let top = top.clone();
            let clones: Vec<Instruction> = under
                .iter()
                .map(|(color, d)| {
                    let mut clone = top.clone();
                    if let Some(region) = laws::anchor_region(&clone) {
                        let moved = [region[0] + d, region[1] + d, region[2] + d, region[3] + d];
                        clone.at = Some(inku_score::AtRegion { region: moved });
                        if let Some(resolved) = laws::resolved_mut(&mut clone) {
                            resolved.anchor =
                                inku_score::ResolvedPlacementAnchor::Named { region: moved };
                        }
                    }
                    paint_instruction(&mut clone, *color);
                    clone
                })
                .collect();
            self.out
                .score
                .instructions
                .splice(position..position, clones);
            self.out.cycles.remove(&layer);
            self.out
                .kasane
                .insert(layer, under.iter().map(|(color, _)| *color).collect());
        }
        Ok(())
    }

    fn b18(&mut self) -> Result<(), Refusal> {
        let mut chromatic: Vec<(usize, Color)> = Vec::new();
        let layers: Vec<usize> = self.context.layers().collect();
        for layer in layers {
            let colors = self.colors_of(layer);
            let shape = self.context.summary(layer).map(|summary| summary.shape);
            if let [color] = colors.as_slice()
                && light_value(*color).is_some()
                && shape
                    .is_some_and(|shape| laws::SIZED.iter().any(|sized| sized.as_str() == shape))
                && self.context.movable(layer)
            {
                chromatic.push((layer, *color));
            }
        }
        if chromatic.len() < 2 {
            return Err(refusal(
                "b18_two",
                "B18 は、色の付いた閉じた形か弧の層が2つ以上ある時に使う".to_owned(),
                "B18 takes two or more colored layers of closed shapes or arcs".to_owned(),
            ));
        }
        let mut reference = chromatic[0];
        for entry in &chromatic[1..] {
            if self.area(entry.0) > self.area(reference.0) {
                reference = *entry;
            }
        }
        let base = self.area(reference.0) * light_value(reference.1).unwrap_or(1.0);
        for (layer, color) in chromatic {
            if layer == reference.0 {
                continue;
            }
            let want = base / light_value(color).unwrap_or(1.0);
            let area = self.area(layer);
            let mut factor = if area > 0.0 {
                (want / area).sqrt()
            } else {
                1.0
            };
            if !(1.0 / PHI_SQUARED..=PHI_SQUARED).contains(&factor) {
                self.note("b18_clamped", Some(layer), None);
                factor = factor.clamp(1.0 / PHI_SQUARED, PHI_SQUARED);
            }
            for position in self.positions(layer) {
                laws::scale_geometry(&mut self.out.score.instructions[position], factor);
            }
            #[allow(clippy::float_cmp)]
            if factor != 1.0 {
                self.out.resized.insert(layer);
            }
        }
        Ok(())
    }

    // --- D1 to D7 -----------------------------------------------------------------------------

    /// Each layer's first color now.
    fn colors_now(&self) -> BTreeMap<usize, Color> {
        self.context
            .layers()
            .filter_map(|layer| Some((layer, self.first_color(layer)?)))
            .collect()
    }

    /// The harmony of the drawing estimated for these layer colors.
    fn harmony_of(&self, colors: &BTreeMap<usize, Color>) -> f64 {
        let layers: BTreeMap<usize, [f64; 3]> = colors
            .iter()
            .filter(|(layer, _)| {
                self.context
                    .now
                    .looks
                    .get(layer)
                    .is_some_and(|look| look.ink >= MIN_INK)
            })
            .filter_map(|(layer, color)| Some((*layer, self.context.look(*layer, *color)?.lab?)))
            .collect();
        harmony(
            self.context.paint(self.ground()).lab,
            &layers,
            &self.context.now.neighbors,
        )
        .unwrap_or(f64::MIN)
    }

    fn d_laws(&mut self) -> Result<(), Refusal> {
        let main = self.context.main;
        if let Some(value) = self.law("D2") {
            let Some(vivid) = color_of(&value["vivid"]) else {
                return Ok(());
            };
            let chroma = self.context.paint(vivid).chroma;
            if !WHEEL.contains(&vivid) || chroma < VIVID_CHROMA {
                return Err(refusal(
                    "not_vivid",
                    format!(
                        "D2: {} は鮮やかな色でない（表の chroma {chroma:.0}、{VIVID_CHROMA} 以上の有彩色にする）",
                        vivid.as_str()
                    ),
                    format!(
                        "D2: {} is not vivid (table chroma {chroma:.0}; take a chromatic color of {VIVID_CHROMA} or more)",
                        vivid.as_str()
                    ),
                ));
            }
            self.set_layer_color(main, vivid);
            let layers: Vec<usize> = self.context.layers().collect();
            for layer in layers {
                if layer == main || self.protected(layer) {
                    continue;
                }
                let colors = self.colors_of(layer);
                if !colors
                    .iter()
                    .any(|color| self.context.paint(*color).chroma > MUTED_SHARE * chroma)
                {
                    continue;
                }
                let seen: Vec<Color> = NEUTRAL
                    .iter()
                    .copied()
                    .filter(|neutral| self.seen(layer, *neutral) >= VISIBLE)
                    .collect();
                if seen.is_empty() {
                    return Err(refusal(
                        "no_neutral",
                        format!("D2: layer {layer} を無彩にすると、描いた時に地から見えない"),
                        format!(
                            "D2: layer {layer} would not be seen against the ground in any neutral"
                        ),
                    ));
                }
                // A distant layer of the laws stage's aerial perspective keeps
                // its order (B15).
                let all: BTreeMap<usize, Vec<Color>> = self
                    .context
                    .layers()
                    .map(|other| (other, self.colors_of(other)))
                    .collect();
                let choices: Vec<Color> = seen
                    .into_iter()
                    .filter(|neutral| {
                        let mut trial = all.clone();
                        trial.insert(layer, vec![*neutral]);
                        self.aerial_broken(&trial).is_none()
                    })
                    .collect();
                if choices.is_empty() {
                    return Err(refusal(
                        "aerial_order",
                        format!(
                            "D2: 遠い layer {layer} を無彩にすると、空気遠近（B15）の明るさの順（地との差 {AERIAL_FAR} 以上で主の層より小さい）が崩れる"
                        ),
                        format!(
                            "D2: turning the distant layer {layer} neutral breaks the aerial perspective's order (B15: {AERIAL_FAR} or more from the ground and less than the main layer)"
                        ),
                    ));
                }
                let now = self.colors_now();
                let mut best: Option<(f64, Color)> = None;
                for neutral in choices {
                    let mut trial = now.clone();
                    trial.insert(layer, neutral);
                    let value = self.harmony_of(&trial);
                    if best.is_none_or(|(found, _)| value > found) {
                        best = Some((value, neutral));
                    }
                }
                if let Some((_, neutral)) = best {
                    self.set_layer_color(layer, neutral);
                    self.tool_assigned.insert(layer);
                    self.note("d2_neutral", Some(layer), Some(neutral));
                }
            }
            let ground = self.context.paint(self.ground());
            if ground.place.is_some() && ground.chroma > MUTED_SHARE * chroma {
                return Err(refusal(
                    "ground_vivid",
                    format!(
                        "D2: 地 {} が {} の半分より鮮やか。地は替えないので、もっと鮮やかな色にする",
                        self.ground().as_str(),
                        vivid.as_str()
                    ),
                    format!(
                        "D2: the ground {} is more vivid than half of {}; the ground stays, so take a more vivid color",
                        self.ground().as_str(),
                        vivid.as_str()
                    ),
                ));
            }
        }
        if let Some(value) = self.law("D3") {
            let Some((strong, partner)) = pair_of(value) else {
                return Ok(());
            };
            if !self.context.pairs.contains(&(strong, partner)) {
                return Err(refusal(
                    "not_touching",
                    format!(
                        "D3: layer {strong} と layer {partner} は接していない（pair の選択肢から選ぶ）"
                    ),
                    format!(
                        "D3: layer {strong} and layer {partner} do not touch (choose pair from its choices)"
                    ),
                ));
            }
            let found = self.colors_of(strong);
            let strong_color = match found.as_slice() {
                [color]
                    if self.context.paint(*color).place.is_some()
                        && self.chroma(strong, *color) >= CHROMATIC =>
                {
                    Some(*color)
                }
                _ => None,
            };
            let Some(strong_color) = strong_color else {
                let names: Vec<&str> = found.iter().map(|color| color.as_str()).collect();
                return Err(refusal(
                    "strong_not_chromatic",
                    format!(
                        "D3: 強い色の layer {strong} が、描いて一色の有彩色に見える層でない（{}）",
                        names.join(", ")
                    ),
                    format!(
                        "D3: the strong layer {strong} does not read as one chromatic color when drawn ({})",
                        names.join(", ")
                    ),
                ));
            };
            let place = self.context.paint(strong_color).place;
            let partner_color = value["partner_color"].as_str().and_then(color_named);
            if let Some(partner_color) = partner_color {
                if partner_color != Color::Gray
                    && !complement(place, self.context.paint(partner_color).place)
                {
                    let opposite: Vec<&str> = WHEEL
                        .iter()
                        .filter(|color| complement(place, self.context.paint(**color).place))
                        .map(|color| color.as_str())
                        .collect();
                    let degrees = place.unwrap_or(0.0);
                    let name = strong_color.as_str();
                    return Err(refusal(
                        "not_complement",
                        format!(
                            "D3: {name}（色相環の位置 {degrees:.0}°）の向かいの色は {}。partner_color をそのどれかか gray にする",
                            if opposite.is_empty() {
                                "この作品には無い".to_owned()
                            } else {
                                opposite.join("・")
                            }
                        ),
                        format!(
                            "D3: the colors opposite {name} (at {degrees:.0}° on the wheel) are {}; make partner_color one of them or gray",
                            if opposite.is_empty() {
                                "none in this work".to_owned()
                            } else {
                                opposite.join(", ")
                            }
                        ),
                    ));
                }
                self.set_layer_color(partner, partner_color);
            }
        }
        if let Some(value) = self.law("D4") {
            let entries: Vec<(usize, &str)> = value["layers"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|entry| {
                    (
                        layer_number(&entry["layer"]),
                        entry["handling"].as_str().unwrap_or("temperate"),
                    )
                })
                .collect();
            let handlings: BTreeSet<&str> = entries.iter().map(|(_, handling)| *handling).collect();
            if handlings.len() < 2 {
                return Err(refusal(
                    "one_handling",
                    "D4: 濃さは2種以上にする（dense・temperate・faint）".to_owned(),
                    "D4: take two kinds of handling or more (dense, temperate, faint)".to_owned(),
                ));
            }
            let Some(color) = color_of(&value["color"]) else {
                return Ok(());
            };
            for (layer, handling) in entries {
                self.set_layer_color(layer, color);
                let intensity = match handling {
                    "dense" => SurfaceIntensity::Dense,
                    "faint" => SurfaceIntensity::Faint,
                    _ => SurfaceIntensity::Normal,
                };
                for position in self.positions(layer) {
                    self.out.score.instructions[position].surface_intensity = intensity;
                }
                self.out.handled.insert(layer);
            }
        }
        if let Some(value) = self.law("D6") {
            for target in value["targets"].as_array().into_iter().flatten() {
                let layer = layer_number(&target["layer"]);
                let colors: Vec<Color> = target["colors"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(color_of)
                    .collect();
                let distinct: BTreeSet<&str> = colors.iter().map(|color| color.as_str()).collect();
                if distinct.len() != colors.len() {
                    return Err(refusal(
                        "same_colors",
                        "D6: 巡らせる色は違う色にする".to_owned(),
                        "D6: the colors in turn are different colors".to_owned(),
                    ));
                }
                let position = self.only(layer, "D6")?;
                let Some(first) = colors.first() else {
                    continue;
                };
                let instruction = &mut self.out.score.instructions[position];
                instruction.color = *first;
                if let Some(arrangement) = instruction.arrangement.as_mut() {
                    arrangement.color_cycle = colors.clone();
                }
                self.out.cycles.insert(layer, (colors, false));
            }
        }
        if TOOL_LAWS
            .iter()
            .any(|law| self.answer.laws.contains_key(law))
        {
            self.assign_by_tool()?;
        }
        Ok(())
    }

    fn tool_names(&self) -> String {
        TOOL_LAWS
            .iter()
            .filter(|law| self.answer.laws.contains_key(*law))
            .copied()
            .collect::<Vec<_>>()
            .join("・")
    }

    /// Whether these colors keep the rules of the laws whose colors the tool
    /// decides: hue relations by the drawn places, D7's levels by the drawn
    /// lightness with the ground at the level chosen.
    fn tool_predicate(&self, colors: &BTreeMap<usize, Vec<Color>>) -> bool {
        let mut places: Vec<f64> = Vec::new();
        let mut dull = false;
        for (layer, found) in colors {
            for color in found {
                let paint = self.context.paint(*color);
                if let Some(place) = paint.place
                    && self.chroma(*layer, *color) >= CHROMATIC
                {
                    places.push(place);
                    dull |= paint.chroma < VIVID_CHROMA;
                }
            }
        }
        let ground = self.context.paint(self.ground());
        if let Some(place) = self.context.ground_place() {
            places.push(place);
            dull |= ground.chroma < VIVID_CHROMA;
        }
        if self.answer.laws.contains_key("D1") && (dull || !hue_contrast(&places)) {
            return false;
        }
        if self.answer.laws.contains_key("D5") && !analogous(&places) {
            return false;
        }
        if let Some(value) = self.law("D7") {
            let mut values = vec![ground.lightness];
            for (layer, found) in colors {
                for color in found {
                    values.push(match self.context.look(*layer, *color) {
                        Some(look) if look.read => {
                            look.lab.map_or(ground.lightness, |lab| lab[0] / 100.0)
                        }
                        _ => self.context.paint(*color).lightness,
                    });
                }
            }
            let rank = three_levels(&level_values(values), ground.lightness);
            if rank.is_none_or(|rank| Some(LEVELS[rank]) != value["level"].as_str()) {
                return false;
            }
        }
        true
    }

    /// The colors of the free layers that keep the tool's laws with every one
    /// of them seen: the combination that recolors the main layer first, then
    /// the one of the highest estimated harmony, then the one that changes the
    /// most layers (the first of equals). `None` when no combination does.
    fn search(
        &self,
        free: &[usize],
        fixed: &BTreeMap<usize, Vec<Color>>,
        candidates: Option<&[Color]>,
    ) -> Option<BTreeMap<usize, Color>> {
        let before = self.colors_now();
        let input_main = self.context.first_color(self.context.main);
        let options: Vec<Vec<Color>> = free
            .iter()
            .map(|layer| {
                candidates
                    .unwrap_or(&COLORS)
                    .iter()
                    .copied()
                    .filter(|color| self.seen(*layer, *color) >= VISIBLE)
                    .collect()
            })
            .collect();
        if options.iter().any(Vec::is_empty) {
            return None;
        }
        let evaluate = |chosen: &BTreeMap<usize, Color>| -> Option<SearchKey> {
            let mut colors = fixed.clone();
            for (layer, color) in chosen {
                colors.insert(*layer, vec![*color]);
            }
            if !self.tool_predicate(&colors) || self.aerial_broken(&colors).is_some() {
                return None;
            }
            let mut all = before.clone();
            all.extend(chosen.iter().map(|(layer, color)| (*layer, *color)));
            let main = all.get(&self.context.main).copied();
            let changed = chosen
                .iter()
                .filter(|(layer, color)| before.get(layer) != Some(color))
                .count();
            Some((main != input_main, round9(self.harmony_of(&all)), changed))
        };
        // Strictly better: the main layer recolored, then the harmony, then
        // the changed layers; an equal key keeps the first found.
        let better = |key: SearchKey, best: Option<SearchKey>| {
            best.is_none_or(|best| {
                if key.0 != best.0 {
                    return key.0;
                }
                match key.1.total_cmp(&best.1) {
                    std::cmp::Ordering::Greater => true,
                    std::cmp::Ordering::Less => false,
                    std::cmp::Ordering::Equal => key.2 > best.2,
                }
            })
        };
        let combinations = options
            .iter()
            .try_fold(1usize, |product, option| product.checked_mul(option.len()))
            .unwrap_or(usize::MAX);
        if combinations <= SEARCH_LIMIT {
            let mut best: Option<(SearchKey, BTreeMap<usize, Color>)> = None;
            let mut digits = vec![0usize; free.len()];
            loop {
                let chosen: BTreeMap<usize, Color> = free
                    .iter()
                    .zip(&digits)
                    .enumerate()
                    .map(|(k, (layer, digit))| (*layer, options[k][*digit]))
                    .collect();
                if let Some(key) = evaluate(&chosen)
                    && better(key, best.as_ref().map(|(key, _)| *key))
                {
                    best = Some((key, chosen));
                }
                // The next combination, the last layer turning fastest.
                let mut k = free.len();
                loop {
                    if k == 0 {
                        return best.map(|(_, chosen)| chosen);
                    }
                    k -= 1;
                    digits[k] += 1;
                    if digits[k] < options[k].len() {
                        break;
                    }
                    digits[k] = 0;
                }
            }
        }
        // Too many to try: each layer in turn takes its best color with the
        // ones before it chosen and the ones after it as they are.
        let mut chosen: BTreeMap<usize, Color> = BTreeMap::new();
        for (k, layer) in free.iter().enumerate() {
            let mut best: Option<(SearchKey, Color)> = None;
            for color in &options[k] {
                let mut trial = chosen.clone();
                trial.insert(*layer, *color);
                let all_free: BTreeMap<usize, Color> = free
                    .iter()
                    .map(|other| {
                        (
                            *other,
                            trial
                                .get(other)
                                .copied()
                                .or_else(|| before.get(other).copied())
                                .unwrap_or(*color),
                        )
                    })
                    .collect();
                let key = evaluate(&all_free).unwrap_or((false, f64::MIN, 0));
                if better(key, best.map(|(key, _)| key)) {
                    best = Some((key, *color));
                }
            }
            chosen.insert(*layer, best.map_or(options[k][0], |(_, color)| color));
        }
        evaluate(&chosen).map(|_| chosen)
    }

    fn assign_by_tool(&mut self) -> Result<(), Refusal> {
        let main = self.context.main;
        let tool = self.tool_names();
        let hue = ["D1", "D5"]
            .iter()
            .find_map(|law| self.law(law).and_then(|value| color_of(&value["hue"])));
        let named = named(self.answer, main);
        let mut free: Vec<usize> = self
            .context
            .colorable
            .iter()
            .copied()
            .filter(|layer| !named.contains_key(layer))
            .collect();
        let mut fixed: BTreeMap<usize, Vec<Color>> = self
            .context
            .layers()
            .filter(|layer| !free.contains(layer))
            .map(|layer| (layer, self.colors_of(layer)))
            .collect();
        if let Some(hue) = hue {
            if free.contains(&main) {
                let seen = self.seen(main, hue);
                if seen < VISIBLE {
                    let ground = self.ground().as_str();
                    let name = hue.as_str();
                    return Err(refusal(
                        "hue_unseen",
                        format!(
                            "{tool}: 主の色相 {name} は、主の層 {main} に描くと地 {ground} から見えない（見積もりの差 {seen:.2}）。別の色相にする"
                        ),
                        format!(
                            "{tool}: the main hue {name}, drawn on the main layer {main}, is not seen against the ground {ground} (an estimated difference of {seen:.2}); take another hue"
                        ),
                    ));
                }
                free.retain(|layer| *layer != main);
                fixed.insert(main, vec![hue]);
                self.set_layer_color(main, hue);
                self.tool_assigned.insert(main);
                self.chosen_by_answer.insert(main);
            } else if self.colors_of(main) != vec![hue] {
                let names: Vec<&str> = self
                    .colors_of(main)
                    .iter()
                    .map(|color| color.as_str())
                    .collect();
                return Err(refusal(
                    "main_kept",
                    format!(
                        "{tool}: 主の層 {main} の色は {} のまま（記述が言った色か、ほかの法則の色）なので、主の色相（hue）をその色にする",
                        names.join("・")
                    ),
                    format!(
                        "{tool}: the main layer {main} keeps {} (a stated color, or another law's), so make the main hue that color",
                        names.join(", ")
                    ),
                ));
            }
        }
        let Some(found) = self.search(&free, &fixed, None) else {
            return Err(refusal(
                "no_combination",
                format!(
                    "{tool}: 決まりを満たし、どの層も描いた時に地から見える色の組が、この作品の色に無い"
                ),
                format!(
                    "{tool}: no combination of this work's colors keeps the rule with every layer seen against the ground when drawn"
                ),
            ));
        };
        for (layer, color) in found {
            if self.colors_of(layer) != vec![color] {
                self.note("tool_color", Some(layer), Some(color));
                self.set_layer_color(layer, color);
            }
            self.tool_assigned.insert(layer);
        }
        Ok(())
    }

    // --- every layer seen ---------------------------------------------------------------------

    /// The colors the tool may give a layer it recolors to be seen, after the
    /// main law's idea of color.
    fn idea(&self) -> Vec<Color> {
        let mut used: Vec<Color> = vec![self.ground()];
        for layer in self.context.layers() {
            used.extend(self.colors_of(layer));
        }
        let main_law = self.answer.main_law.as_str();
        let all = COLORS.to_vec();
        match main_law {
            "D2" => {
                let vivid = self.law("D2").and_then(|value| color_of(&value["vivid"]));
                let limit =
                    vivid.map_or(0.0, |vivid| MUTED_SHARE * self.context.paint(vivid).chroma);
                all.into_iter()
                    .filter(|color| {
                        NEUTRAL.contains(color) || self.context.paint(*color).chroma <= limit
                    })
                    .collect()
            }
            "D4" => {
                let color = self.law("D4").and_then(|value| color_of(&value["color"]));
                all.into_iter()
                    .filter(|found| NEUTRAL.contains(found) || Some(*found) == color)
                    .collect()
            }
            "B17" => {
                let paints: BTreeSet<[u8; 3]> = used
                    .iter()
                    .map(|color| self.context.paint(*color).rgb)
                    .collect();
                all.into_iter()
                    .filter(|color| paints.contains(&self.context.paint(*color).rgb))
                    .collect()
            }
            "C8" => all
                .into_iter()
                .filter(|color| used.contains(color) || NEUTRAL.contains(color))
                .collect(),
            "B18" => NEUTRAL.to_vec(),
            "C9" if self
                .law("C9")
                .is_some_and(|value| value["others"] == "neutral") =>
            {
                NEUTRAL.to_vec()
            }
            _ => all,
        }
    }

    fn visible_fix(&mut self) -> Result<(), Refusal> {
        let named = named(self.answer, self.context.main);
        let layers: Vec<usize> = self.context.layers().collect();
        for layer in layers {
            if self.protected(layer) {
                continue;
            }
            let mut colors = self.colors_of(layer);
            colors.sort_by_key(|color| color.as_str());
            let Some(unseen) = colors
                .into_iter()
                .find(|color| self.seen(layer, *color) < VISIBLE)
            else {
                continue;
            };
            if named.contains_key(&layer) || self.chosen_by_answer.contains(&layer) {
                return Err(self.unseen(layer, unseen));
            }
            let fixed: BTreeMap<usize, Vec<Color>> = self
                .context
                .layers()
                .filter(|other| *other != layer)
                .map(|other| (other, self.colors_of(other)))
                .collect();
            let idea = self.idea();
            match self.search(&[layer], &fixed, Some(&idea)) {
                Some(found) => {
                    let color = found[&layer];
                    self.set_layer_color(layer, color);
                    self.tool_assigned.insert(layer);
                    self.note("seen_recolored", Some(layer), Some(color));
                }
                None => self.note("unseen_kept", Some(layer), Some(unseen)),
            }
        }
        Ok(())
    }

    // --- the checks ---------------------------------------------------------------------------

    fn check_kept(&self) -> Result<(), Refusal> {
        let positions = laws::layers(&self.context.score);
        for (layer, word) in &self.context.stated {
            let before = layer_colors(
                &self.context.score,
                positions.get(layer).map_or(&[][..], Vec::as_slice),
            );
            let after = layer_colors(&self.out.score, &self.positions(*layer));
            if before != after {
                let names: Vec<&str> = after.into_iter().collect();
                return Err(refusal(
                    "stated_changed",
                    format!(
                        "layer {layer} は記述が言った色（「{word}」）なのに、色が替わった（{}）",
                        names.join(", ")
                    ),
                    format!(
                        "layer {layer} is in a color the description states (“{word}”) and its color changed ({})",
                        names.join(", ")
                    ),
                ));
            }
        }
        Ok(())
    }

    /// The colors each layer had before the colors.
    fn colors_before(&self, layer: usize) -> Vec<Color> {
        let positions = laws::layers(&self.context.score);
        layer_colors(
            &self.context.score,
            positions.get(&layer).map_or(&[][..], Vec::as_slice),
        )
        .into_iter()
        .filter_map(color_named)
        .collect()
    }

    /// The first distant layer of the laws stage's aerial perspective (B15)
    /// these colors take out of its order, with its drawn difference from
    /// the ground and the main layer's: a distant layer stands 0.2 or more
    /// from the ground and less far than the main layer. Only a distant
    /// layer whose colors or the main layer's colors changed is read, and a
    /// layer the estimate does not read is not.
    fn aerial_broken(&self, colors: &BTreeMap<usize, Vec<Color>>) -> Option<(usize, f64, f64)> {
        let main = self.context.main;
        let main_colors = colors.get(&main)?;
        let main_changed = *main_colors != self.colors_before(main);
        let near = main_colors
            .iter()
            .map(|color| self.seen(main, *color))
            .fold(f64::INFINITY, f64::min);
        for (layer, law) in &self.context.fixed {
            if law != "B15" || *layer == main {
                continue;
            }
            let Some(found) = colors.get(layer) else {
                continue;
            };
            if !main_changed && *found == self.colors_before(*layer) {
                continue;
            }
            for color in found {
                if !self
                    .context
                    .look(*layer, *color)
                    .is_some_and(|look| look.read)
                {
                    continue;
                }
                let far = self.seen(*layer, *color);
                if far < AERIAL_FAR || far >= near {
                    return Some((*layer, far, near));
                }
            }
        }
        None
    }

    /// The laws stage's aerial perspective still holds where the colors
    /// changed a distant layer or the main layer (the author's answer,
    /// 2026-10-20).
    fn check_aerial(&self) -> Result<(), Refusal> {
        let main = self.context.main;
        let colors: BTreeMap<usize, Vec<Color>> = self
            .context
            .layers()
            .map(|layer| (layer, self.colors_of(layer)))
            .collect();
        match self.aerial_broken(&colors) {
            None => Ok(()),
            Some((layer, far, near)) => Err(refusal(
                "aerial_order",
                format!(
                    "B15: 遠い layer {layer} は、地との描いた明るさの差を {AERIAL_FAR} 以上で、主の layer {main}（{near:.2}）より小さくする（今は {far:.2}）"
                ),
                format!(
                    "B15: the distant layer {layer} stands {AERIAL_FAR} or more from the ground in drawn lightness and less than the main layer {main} ({near:.2}); it stands {far:.2}"
                ),
            )),
        }
    }

    /// D2 once every law is applied: the main layer, drawn, at least twice as
    /// vivid as every other layer, a kept one included (the prototype's
    /// measure of D2).
    fn check_d2(&self) -> Result<(), Refusal> {
        if self.law("D2").is_none() {
            return Ok(());
        }
        let main = self.context.main;
        let mine = self.drawn_chroma(main);
        for layer in self.context.layers() {
            let theirs = self.drawn_chroma(layer);
            if layer != main && theirs > MUTED_SHARE * mine {
                return Err(refusal(
                    "d2_not_held",
                    format!(
                        "D2: 主の layer {main} の描いた彩度 {mine:.0} が、layer {layer} の {theirs:.0} の2倍に届かない"
                    ),
                    format!(
                        "D2: the main layer {main}, drawn, has a chroma of {mine:.0}, not twice the {theirs:.0} of layer {layer}"
                    ),
                ));
            }
        }
        Ok(())
    }

    /// The distinct chromatic places of the ground and the layers, as drawn.
    fn drawn_places(&self) -> Vec<f64> {
        let mut places: Vec<f64> = Vec::new();
        if let Some(place) = self.context.ground_place() {
            places.push(place);
        }
        for layer in self.context.layers() {
            for color in self.colors_of(layer) {
                if let Some(place) = self.context.paint(color).place
                    && self.chroma(layer, color) >= CHROMATIC
                {
                    places.push(place);
                }
            }
        }
        distinct_places(&places)
    }

    #[allow(clippy::too_many_lines)]
    fn check_colors(&self) -> Result<(), Refusal> {
        let ground = self.ground();
        let positions = laws::layers(&self.context.score);
        let layers: Vec<usize> = self.context.layers().collect();
        for layer in &layers {
            let before = layer_colors(
                &self.context.score,
                positions.get(layer).map_or(&[][..], Vec::as_slice),
            );
            let after = layer_colors(&self.out.score, &self.positions(*layer));
            if before == after || self.protected(*layer) {
                continue;
            }
            for color in self.colors_of(*layer) {
                if self.seen(*layer, color) < VISIBLE {
                    return Err(self.unseen(*layer, color));
                }
            }
        }
        let mut used: Vec<Color> = vec![ground];
        for layer in &layers {
            used.extend(self.colors_of(*layer));
        }
        let mut distinct: Vec<Color> = Vec::new();
        for color in COLORS {
            if used.contains(&color)
                && !distinct
                    .iter()
                    .any(|found| self.context.paint(*found).rgb == self.context.paint(color).rgb)
            {
                distinct.push(color);
            }
        }
        if let Some(value) = self.law("B17") {
            if distinct.len() > 3 {
                let names: Vec<&str> = distinct.iter().map(|color| color.as_str()).collect();
                return Err(refusal(
                    "b17_colors",
                    format!(
                        "B17: 地を含めて3色まで（今は {} 色: {}）",
                        distinct.len(),
                        names.join(", ")
                    ),
                    format!(
                        "B17: three colors at most, the ground included (now {}: {})",
                        distinct.len(),
                        names.join(", ")
                    ),
                ));
            }
            if let Some(accent) = color_of(&value["accent"]) {
                let ink = |layer: &usize| {
                    self.context
                        .now
                        .looks
                        .get(layer)
                        .map_or(0.0, |look| look.ink)
                };
                let mut smallest = layers[0];
                for layer in &layers[1..] {
                    if ink(layer) < ink(&smallest) {
                        smallest = *layer;
                    }
                }
                let holders: Vec<usize> = layers
                    .iter()
                    .copied()
                    .filter(|layer| self.colors_of(*layer).contains(&accent))
                    .collect();
                if holders != vec![smallest] {
                    let held = if holders.is_empty() {
                        ["どの層にも無い".to_owned(), "no layer".to_owned()]
                    } else {
                        let list = format!("{holders:?}");
                        [list.clone(), list]
                    };
                    return Err(refusal(
                        "b17_accent",
                        format!(
                            "B17: 強調の色 {} は、面積のいちばん小さい layer {smallest} だけに当てる（今は {}）",
                            accent.as_str(),
                            held[0]
                        ),
                        format!(
                            "B17: the accent color {} goes on the layer of the smallest area, layer {smallest}, alone (now {})",
                            accent.as_str(),
                            held[1]
                        ),
                    ));
                }
            }
        }
        if self.law("B19").is_some() {
            for layer in &layers {
                let need = if *layer == self.context.main {
                    B19_MAIN
                } else {
                    VISIBLE
                };
                for color in self.colors_of(*layer) {
                    if self.seen(*layer, color) < need {
                        return Err(refusal(
                            "b19",
                            format!(
                                "B19: layer {layer} の {} と地 {} の描いた明るさの差が {need} 未満",
                                color.as_str(),
                                ground.as_str()
                            ),
                            format!(
                                "B19: layer {layer} in {} stands less than {need} from the ground {} in drawn lightness",
                                color.as_str(),
                                ground.as_str()
                            ),
                        ));
                    }
                }
            }
        }
        if let Some(value) = self.law("B20") {
            let layer = layer_number(&value["accent_layer"]);
            let found = self.colors_of(layer);
            let accent = match found.as_slice() {
                [color]
                    if self.context.paint(*color).place.is_some()
                        && self.chroma(layer, *color) >= CHROMATIC =>
                {
                    Some(*color)
                }
                _ => None,
            };
            let Some(accent) = accent else {
                let names: Vec<&str> = found.iter().map(|color| color.as_str()).collect();
                return Err(refusal(
                    "b20_accent",
                    format!(
                        "B20: 強調の layer {layer} の色が、描いて一色の有彩色に見えない（{}）",
                        names.join(", ")
                    ),
                    format!(
                        "B20: the accent layer {layer} does not read as one chromatic color when drawn ({})",
                        names.join(", ")
                    ),
                ));
            };
            let base = if self.context.ground_place().is_some() {
                Some(ground)
            } else {
                self.first_color(self.context.main)
            };
            let base_place = base.and_then(|base| self.context.paint(base).place);
            let accent_place = self.context.paint(accent).place.unwrap_or(0.0);
            if base_place.is_none_or(|place| warm(place) == warm(accent_place)) {
                let base_name = base.map_or("", Color::as_str);
                return Err(refusal(
                    "b20_temperature",
                    format!(
                        "B20: 強調の {} は {base_name}（地か主）と反対の温度にする（色相環の位置で、暖＝黄から赤紫、寒＝紫から黄緑）",
                        accent.as_str()
                    ),
                    format!(
                        "B20: the accent {} takes the temperature opposite to {base_name} (the ground or the main layer; on the wheel, warm runs from yellow to red-purple, cool from purple to yellow-green)",
                        accent.as_str()
                    ),
                ));
            }
        }
        if let Some(value) = self.law("C8") {
            let kind = value["chord"].as_str().unwrap_or_default();
            let places = self.drawn_places();
            if !chord(kind, &places) {
                let shown: Vec<String> =
                    places.iter().map(|place| format!("{place:.0}°")).collect();
                return Err(refusal(
                    "c8_chord",
                    format!(
                        "C8: 地と層の有彩色の位置（{}）が {kind} の和音にならない",
                        shown.join(", ")
                    ),
                    format!(
                        "C8: the chromatic places of the ground and the layers ({}) do not make a {kind} chord",
                        shown.join(", ")
                    ),
                ));
            }
        }
        Ok(())
    }

    fn check_limits(&self) -> Result<(), Refusal> {
        let instructions = self.out.score.instructions.len();
        if instructions > MAX_INSTRUCTIONS {
            return Err(refusal(
                "too_many_instructions",
                format!(
                    "指示が {instructions} になり上限 {MAX_INSTRUCTIONS} を超える。重ねる層を減らす"
                ),
                format!(
                    "the colors leave {instructions} instructions, over the limit of {MAX_INSTRUCTIONS}; layer fewer layers"
                ),
            ));
        }
        let marks: u64 = self
            .out
            .score
            .instructions
            .iter()
            .map(|instruction| u64::from(count_of(instruction)))
            .sum();
        if marks > MAX_MARKS {
            return Err(refusal(
                "too_many_marks",
                format!("痕が {marks} になり上限 {MAX_MARKS} を超える。重ねる層を減らす"),
                format!(
                    "the colors leave {marks} marks, over the limit of {MAX_MARKS}; layer fewer layers"
                ),
            ));
        }
        Ok(())
    }
}

// --- printing what the colors changed ----------------------------------------------------------

/// The printed plan with what the color laws changed: each layer they changed
/// is edited, and the lower colors of a kasane are printed before it.
#[derive(Clone, Debug, PartialEq)]
pub struct ColorsPrint {
    pub printed: PrintedPlan,
    /// The layer of the plan before the colors each printed layer comes from.
    pub from: Vec<usize>,
    /// The printed layers that are a kasane's lower colors.
    pub under: BTreeSet<usize>,
    /// The printed layers the colors changed.
    pub changed: BTreeSet<usize>,
}

/// The place a kasane's lower copy is printed at, and the action it takes.
fn copy_place(
    copy: &Instruction,
    units: Units,
    layer: &mut inku_ddl::work_plan::WorkPlanLayer,
) -> Option<NumericPlace> {
    let count = count_of(copy);
    if laws::is_line(copy.primitive) && count == 1 {
        layer.attributes.remove(&WorkPlanSlot::Angle);
        layer.attributes.remove(&WorkPlanSlot::Size);
        layer.proportion = None;
        return laws::line_ends(copy, units);
    }
    match laws::recipe(copy)? {
        inku_score::ResolvedPlacementRecipe::Place => Some(NumericPlace::Point {
            at: laws::center_of(copy),
        }),
        inku_score::ResolvedPlacementRecipe::Grid { .. } => {
            layer.action = "tile".to_owned();
            layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
            laws::moved_range(copy, units)
        }
        _ if laws::is_row(copy) => {
            layer.action = "line_up".to_owned();
            layer.attributes.remove(&WorkPlanSlot::LineUpDirection);
            laws::row_ends(copy, units)
        }
        _ => None,
    }
}

/// Print what the colors changed, or `None` when a changed layer is one the
/// printer cannot write.
#[allow(clippy::too_many_lines)]
fn print_colors(context: &ColorsContext, painted: &Painted) -> Option<ColorsPrint> {
    let printed = &context.printed;
    let units = context.units;
    let first = context.first_plan_layer();
    let before = laws::layers(&context.score);
    let after = laws::layers(&painted.score);
    let mut out = ColorsPrint {
        printed: PrintedPlan {
            plan: WorkPlan {
                layers: Vec::new(),
                ..printed.plan.clone()
            },
            ranges: Vec::new(),
            joints: Vec::new(),
            numeric: Vec::new(),
        },
        from: Vec::new(),
        under: BTreeSet::new(),
        changed: BTreeSet::new(),
    };
    for (k, plan_layer) in printed.plan.layers.iter().enumerate() {
        let layer = first + k;
        let was: Vec<&Instruction> = before
            .get(&layer)?
            .iter()
            .map(|p| &context.score.instructions[*p])
            .collect();
        let is: Vec<&Instruction> = after
            .get(&layer)?
            .iter()
            .map(|p| &painted.score.instructions[*p])
            .collect();
        if was == is {
            out.printed.plan.layers.push(plan_layer.clone());
            out.printed.ranges.push(printed.ranges[k].clone());
            out.printed.joints.push(printed.joints[k].clone());
            out.printed.numeric.push(printed.numeric[k].clone());
            out.from.push(k);
            continue;
        }
        let [before_mark] = was.as_slice() else {
            return None;
        };
        let lower = painted.kasane.get(&layer).map_or(0, Vec::len);
        let (copies, top) = is.split_at(is.len().checked_sub(1)?);
        if copies.len() != lower {
            return None;
        }
        let top = top[0];
        let mut edited = plan_layer.clone();
        let mut numeric = printed.numeric[k].clone().unwrap_or_default();
        let colors_changed = layer_colors(&context.score, &before[&layer])
            != layer_colors(&painted.score, &after[&layer])
            || lower > 0;
        match painted.cycles.get(&layer) {
            Some((colors, shift)) => {
                numeric.cycle = Some(colors.clone());
                numeric.shift = *shift;
                edited
                    .attributes
                    .insert(WorkPlanSlot::Color, colors[0].as_str().to_owned());
            }
            None => {
                if colors_changed || numeric.cycle.is_some() {
                    numeric.cycle = None;
                    numeric.shift = false;
                    edited
                        .attributes
                        .insert(WorkPlanSlot::Color, top.color.as_str().to_owned());
                }
            }
        }
        if let Some(fade) = painted.fades.get(&layer) {
            numeric.fade = Some(*fade);
        }
        if painted.handled.contains(&layer) {
            match top.surface_intensity {
                SurfaceIntensity::Dense => {
                    edited
                        .attributes
                        .insert(WorkPlanSlot::Handling, "dense".to_owned());
                }
                SurfaceIntensity::Faint => {
                    edited
                        .attributes
                        .insert(WorkPlanSlot::Handling, "faint".to_owned());
                }
                SurfaceIntensity::Normal => {
                    edited.attributes.remove(&WorkPlanSlot::Handling);
                }
            }
        }
        if painted.resized.contains(&layer) {
            numeric.size = Some(laws::numeric_size(top, units)?);
            edited.attributes.remove(&WorkPlanSlot::Size);
            edited.proportion = None;
        }
        if painted.filled.contains(&layer) && !before_mark.filled {
            edited
                .attributes
                .insert(WorkPlanSlot::Surface, "flat".to_owned());
        }
        let mut range = printed.ranges[k].clone();
        if painted.moved.contains(&layer) {
            numeric.place = Some(NumericPlace::Point {
                at: laws::center_of(top),
            });
            range = None;
        }
        // A kasane's lower colors, printed first so that they are drawn under it.
        for copy in copies {
            let mut under = edited.clone();
            under
                .attributes
                .insert(WorkPlanSlot::Color, copy.color.as_str().to_owned());
            let place = copy_place(copy, units, &mut under)?;
            let written = NumericWriting {
                place: Some(place),
                size: numeric.size,
                turn: numeric.turn,
                sides: numeric.sides,
                ..NumericWriting::default()
            };
            out.under.insert(out.printed.plan.layers.len());
            out.changed.insert(out.printed.plan.layers.len());
            out.printed.plan.layers.push(under);
            out.printed.ranges.push(None);
            out.printed.joints.push(None);
            out.printed.numeric.push(Some(written));
            out.from.push(k);
        }
        out.changed.insert(out.printed.plan.layers.len());
        out.printed.plan.layers.push(edited);
        out.printed.ranges.push(range);
        out.printed.joints.push(printed.joints[k].clone());
        out.printed.numeric.push(Some(numeric));
        out.from.push(k);
    }
    Some(out)
}

/// The laws a reader chose for the colors and the plan printed with them.
#[derive(Clone, Debug, PartialEq)]
pub struct ColorsChosen {
    pub laws: Vec<&'static str>,
    pub main_law: String,
    pub main_layer: usize,
    pub notes: Vec<ColorNote>,
    pub print: ColorsPrint,
    /// For each printed layer of the plan after the colors, the colors its
    /// instructions should compile to and its fade.
    expected: Vec<(BTreeSet<&'static str>, Option<FadeDirection>)>,
}

impl ColorsChosen {
    /// Whether a compiled Score of the printed document draws what the colors
    /// chose: each printed layer's colors and fade.
    #[must_use]
    pub fn compiled_as_chosen(&self, score: &Score) -> bool {
        let layers = laws::layers(score);
        let first = self.print.printed.first_plan_layer();
        self.expected.iter().enumerate().all(|(k, (colors, fade))| {
            let Some(positions) = layers.get(&(first + k)) else {
                return false;
            };
            let compiled_fade = positions
                .iter()
                .find_map(|position| {
                    score.instructions[*position]
                        .arrangement
                        .as_ref()
                        .map(|arrangement| arrangement.fade)
                })
                .unwrap_or(Fade::None);
            let wanted_fade = match fade {
                None => Fade::None,
                Some(FadeDirection::Outward) => Fade::Outward,
                Some(_) => Fade::Directional,
            };
            layer_colors(score, positions) == *colors && compiled_fade == wanted_fade
        })
    }
}

/// Read a reply to the color request, check it and apply it.
pub fn choose_colors(
    response: &str,
    context: &ColorsContext,
    limits: PromptLimits,
) -> Result<ColorsChosen, Refusal> {
    if response.len() > limits.max_response_bytes {
        return Err(refusal(
            "too_long",
            "答えが長すぎる".to_owned(),
            "the answer is too long".to_owned(),
        ));
    }
    let Ok(answer) = serde_json::from_str::<Value>(response) else {
        return Err(refusal(
            "not_json",
            "答えが JSON として読めない".to_owned(),
            "the answer does not read as JSON".to_owned(),
        ));
    };
    apply_colors(&answer, context)
}

/// Check an answer value and paint the Score with it.
fn painted(answer: &Value, context: &ColorsContext) -> Result<(Answer, Painted), Refusal> {
    let (answer, mut notes) = check(answer, context)?;
    let mut painted = Painting::new(context, &answer, false).run()?;
    notes.append(&mut painted.notes);
    painted.notes = notes;
    Ok((answer, painted))
}

/// The Score an answer value paints, before it is printed, and the tool's
/// notes (the recorded answers' replay compares it with the prototype's
/// Score).
pub fn paint_colors(
    answer: &Value,
    context: &ColorsContext,
) -> Result<(Score, Vec<ColorNote>), Refusal> {
    let (_, painted) = painted(answer, context)?;
    Ok((painted.score, painted.notes))
}

/// Apply an answer value and print what it changed.
pub fn apply_colors(answer: &Value, context: &ColorsContext) -> Result<ColorsChosen, Refusal> {
    let (answer, painted) = painted(answer, context)?;
    let notes = painted.notes.clone();
    let print = print_colors(context, &painted).ok_or_else(|| {
        refusal(
            "unprintable",
            "配色が変えた層を書けない".to_owned(),
            "a layer the colors changed cannot be written".to_owned(),
        )
    })?;
    let first = context.first_plan_layer();
    let after = laws::layers(&painted.score);
    let mut expected = Vec::new();
    for (j, k) in print.from.iter().enumerate() {
        let layer = first + k;
        let positions = after.get(&layer).cloned().unwrap_or_default();
        let colors = if print.under.contains(&j) {
            // A lower copy is the instruction before the top of its layer.
            let lower: Vec<usize> = print
                .from
                .iter()
                .enumerate()
                .filter(|(other, from)| *from == k && print.under.contains(other))
                .map(|(other, _)| other)
                .collect();
            let index = lower.iter().position(|other| *other == j).unwrap_or(0);
            positions
                .get(index)
                .map(|position| layer_colors(&painted.score, &[*position]))
                .unwrap_or_default()
        } else {
            positions
                .last()
                .map(|position| layer_colors(&painted.score, &[*position]))
                .unwrap_or_default()
        };
        let fade = if print.under.contains(&j) {
            None
        } else {
            painted.fades.get(&layer).copied()
        };
        expected.push((colors, fade));
    }
    let laws: Vec<&'static str> = COLOR_LAWS
        .iter()
        .copied()
        .filter(|law| answer.laws.contains_key(law))
        .collect();
    Ok(ColorsChosen {
        laws,
        main_law: answer.main_law.clone(),
        main_layer: context.main,
        notes,
        print,
        expected,
    })
}

/// The laws record with the sentences the colors printed again: a recorded
/// sentence of a layer the colors changed becomes its new sentence, and a
/// kasane's lower copies join their layer. `old` and `new` are the documents'
/// sources before and after the colors.
#[must_use]
pub fn reprinted_record(
    record: &crate::laws_record::LawsLayerRecord,
    print: &ColorsPrint,
    old: &str,
    new: &str,
) -> crate::laws_record::LawsLayerRecord {
    let tail = |source: &str, count: usize| -> Vec<String> {
        let lines: Vec<&str> = source.lines().collect();
        lines[lines.len().saturating_sub(count)..]
            .iter()
            .map(|line| line.trim().to_owned())
            .collect()
    };
    let before_count = print.from.iter().copied().max().map_or(0, |k| k + 1);
    let old_lines = tail(old, before_count);
    let new_lines = tail(new, print.from.len());
    let mut out = record.clone();
    for layer in &mut out.layers {
        let mut sentences: Vec<String> = Vec::new();
        for sentence in &layer.sentences {
            let Some(k) = old_lines.iter().position(|line| line == sentence) else {
                sentences.push(sentence.clone());
                continue;
            };
            for (j, from) in print.from.iter().enumerate() {
                if *from == k
                    && let Some(line) = new_lines.get(j)
                    && !sentences.contains(line)
                {
                    sentences.push(line.clone());
                }
            }
        }
        layer.sentences = sentences;
    }
    out
}
