//! Deterministic work-palette assignment and color-hint resolution.

use std::collections::{BTreeMap, BTreeSet, HashSet};

use inku_score::oklab_from_srgb;
use sha2::{Digest, Sha256};

use crate::types::{Color, ResolvedPaletteColor, ResolvedPaletteContext, Seed};

const ACHROMATIC_COLORS: [&str; 3] = ["black", "gray", "white"];
const CHROMATIC_COLORS: [&str; 6] = ["red", "orange", "yellow", "green", "blue", "purple"];
const HINT_HUE_PRIORITY: [&str; 9] = [
    "red", "orange", "yellow", "green", "blue", "purple", "white", "black", "gray",
];
const OKLCH_CHROMA_FLOOR: f64 = 0.035;

#[must_use]
pub fn default_color(color: Color) -> &'static str {
    match color {
        Color::White => "#ffffff",
        Color::Black => "#111111",
        Color::Blue => "#2c3e91",
        Color::Red => "#a2342a",
        Color::Green => "#2f6b3a",
        Color::Gray => "#888888",
        Color::Yellow => "#a18308",
        Color::Orange => "#a95a00",
        Color::Purple => "#583a84",
    }
}

/// Return the neutral nine-color map for hosts that did not supply a catalog snapshot.
#[must_use]
pub fn default_color_map() -> BTreeMap<String, String> {
    [
        Color::White,
        Color::Black,
        Color::Blue,
        Color::Red,
        Color::Green,
        Color::Gray,
        Color::Yellow,
        Color::Orange,
        Color::Purple,
    ]
    .into_iter()
    .map(|color| (color.as_str().to_owned(), default_color(color).to_owned()))
    .collect()
}

fn default_named_color(name: &str) -> &'static str {
    match name {
        "white" => "#ffffff",
        "black" => "#111111",
        "blue" => "#2c3e91",
        "red" => "#a2342a",
        "green" => "#2f6b3a",
        "gray" => "#888888",
        "yellow" => "#a18308",
        "orange" => "#a95a00",
        "purple" => "#583a84",
        _ => "#111111",
    }
}

/// The longest color name a warning repeats; a longer host key is cut here.
const WARNING_NAME_LIMIT: usize = 64;

/// Whether a host color value is exactly `#` and six hex digits.
fn is_hex_color(value: &str) -> bool {
    value.len() == 7
        && value.starts_with('#')
        && value.bytes().skip(1).all(|byte| byte.is_ascii_hexdigit())
}

/// Replace every host color value that is not `#rrggbb`, so drawing continues.
///
/// Values are written into SVG attributes as they are, so anything else (a
/// `url(...)`, a word, a bare hex) must not reach them. A named color falls
/// back to its default; a catalog entry (`palette:…`) or any other key is
/// left out. Returns the names replaced, for the render warnings.
pub(crate) fn sanitize_color_map(color_map: &mut BTreeMap<String, String>) -> Vec<String> {
    let invalid = color_map
        .iter()
        .filter(|(_, value)| !is_hex_color(value))
        .map(|(name, _)| name.clone())
        .collect::<Vec<_>>();
    for name in &invalid {
        // The hue list names every Score color, each with a default.
        if HINT_HUE_PRIORITY.contains(&name.as_str()) {
            color_map.insert(name.clone(), default_named_color(name).to_owned());
        } else {
            color_map.remove(name);
        }
    }
    invalid
        .into_iter()
        .map(|name| name.chars().take(WARNING_NAME_LIMIT).collect())
        .collect()
}

fn hex_to_rgb(value: &str) -> Option<(u8, u8, u8)> {
    let raw = value.trim().strip_prefix('#').unwrap_or(value.trim());
    if raw.len() != 6 || !raw.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    Some((
        u8::from_str_radix(&raw[0..2], 16).ok()?,
        u8::from_str_radix(&raw[2..4], 16).ok()?,
        u8::from_str_radix(&raw[4..6], 16).ok()?,
    ))
}

fn oklch_from_hex(value: &str) -> Option<(f64, f64, f64)> {
    let (red, green, blue) = hex_to_rgb(value)?;
    let [lightness, a, b] =
        oklab_from_srgb([red, green, blue].map(|component| f64::from(component) / 255.0));
    Some((
        lightness,
        a.hypot(b),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    ))
}

fn chromatic_band(hue: f64) -> &'static str {
    if !(50.0..345.0).contains(&hue) {
        "red"
    } else if hue < 80.0 {
        "orange"
    } else if hue < 137.0 {
        "yellow"
    } else if hue < 200.0 {
        "green"
    } else if hue < 280.0 {
        "blue"
    } else {
        "purple"
    }
}

fn band_center(name: &str) -> f64 {
    match name {
        "red" => 27.5,
        "orange" => 65.0,
        "yellow" => 108.5,
        "green" => 168.5,
        "blue" => 240.0,
        "purple" => 312.5,
        _ => 27.5,
    }
}

fn circular_hue_distance(left: f64, right: f64) -> f64 {
    let distance = (left - right).abs() % 360.0;
    distance.min(360.0 - distance)
}

fn work_color_choice(
    candidates: &[String],
    render_seed: Option<Seed>,
    catalog_id: &str,
    abstract_color: &str,
) -> String {
    let ordered = candidates.iter().cloned().collect::<BTreeSet<_>>();
    if ordered.len() == 1 {
        return ordered.into_iter().next().expect("one candidate");
    }
    let seed = render_seed.map_or_else(|| "None".to_owned(), |seed| seed.to_string());
    let payload = format!("{seed}|{catalog_id}|{abstract_color}");
    let digest = Sha256::digest(payload.as_bytes());
    let index = u64::from_be_bytes(digest[..8].try_into().expect("eight digest bytes"))
        % ordered.len() as u64;
    ordered
        .into_iter()
        .nth(index as usize)
        .expect("choice index is bounded")
}

/// Assign the resolved catalog palette to the nine abstract Score colors.
#[must_use]
pub fn work_color_assignment(
    color_map: &BTreeMap<String, String>,
    render_seed: Option<Seed>,
    catalog_id: Option<&str>,
) -> BTreeMap<String, String> {
    let mut achromatic = Vec::<(f64, String)>::new();
    let mut chromatic = CHROMATIC_COLORS
        .into_iter()
        .map(|name| (name, Vec::<String>::new()))
        .collect::<BTreeMap<_, _>>();
    let mut chromatic_hues = Vec::<(f64, String)>::new();
    let mut seen = HashSet::new();
    for (key, value) in color_map {
        if !key.starts_with("palette:") || !seen.insert(value.clone()) {
            continue;
        }
        let Some((lightness, chroma, hue)) = oklch_from_hex(value) else {
            continue;
        };
        if chroma < OKLCH_CHROMA_FLOOR {
            achromatic.push((lightness, value.clone()));
        } else {
            chromatic
                .get_mut(chromatic_band(hue))
                .expect("all chromatic bands are initialized")
                .push(value.clone());
            chromatic_hues.push((hue, value.clone()));
        }
    }
    achromatic.sort_by(|left, right| {
        left.0
            .total_cmp(&right.0)
            .then_with(|| left.1.cmp(&right.1))
    });
    let mut assignment = BTreeMap::new();
    let mut remaining = achromatic;
    for name in ACHROMATIC_COLORS {
        let fallback = color_map
            .get(name)
            .map_or(default_named_color(name), String::as_str);
        if let Some(index) = remaining
            .iter()
            .position(|candidate| candidate.1.eq_ignore_ascii_case(fallback))
        {
            assignment.insert(name.to_owned(), remaining.remove(index).1);
        }
    }
    for name in ACHROMATIC_COLORS {
        if assignment.contains_key(name) {
            continue;
        }
        let fallback = color_map
            .get(name)
            .map_or(default_named_color(name), String::as_str);
        if remaining.is_empty() {
            assignment.insert(name.to_owned(), fallback.to_owned());
            continue;
        }
        let target = oklch_from_hex(fallback).map_or(0.0, |value| value.0);
        let best = remaining
            .iter()
            .enumerate()
            .min_by(|(_, left), (_, right)| {
                (left.0 - target)
                    .abs()
                    .total_cmp(&(right.0 - target).abs())
                    .then_with(|| left.1.cmp(&right.1))
            })
            .map(|(index, _)| index)
            .expect("remaining is not empty");
        assignment.insert(name.to_owned(), remaining.remove(best).1);
    }
    for name in CHROMATIC_COLORS {
        let candidates = chromatic.get(name).expect("all bands are initialized");
        let value = if !candidates.is_empty() {
            work_color_choice(
                candidates,
                render_seed,
                catalog_id.unwrap_or("default"),
                name,
            )
        } else if !chromatic_hues.is_empty() {
            let target = band_center(name);
            chromatic_hues
                .iter()
                .min_by(|left, right| {
                    circular_hue_distance(left.0, target)
                        .total_cmp(&circular_hue_distance(right.0, target))
                        .then_with(|| left.1.cmp(&right.1))
                })
                .expect("chromatic hues are not empty")
                .1
                .clone()
        } else {
            color_map
                .get(name)
                .cloned()
                .unwrap_or_else(|| default_named_color(name).to_owned())
        };
        assignment.insert(name.to_owned(), value);
    }
    // Server-owned concrete recoloring follows palette/hue selection. Read
    // each original value once so swaps never cascade through another entry.
    let recolors = color_map
        .iter()
        .filter_map(|(key, value)| {
            let original = key.strip_prefix("recolor:")?;
            (is_hex_color(original) && is_hex_color(value))
                .then(|| (original.to_ascii_lowercase(), value.to_ascii_lowercase()))
        })
        .collect::<BTreeMap<_, _>>();
    for value in assignment.values_mut() {
        if let Some(recolored) = recolors.get(&value.to_ascii_lowercase()) {
            *value = recolored.clone();
        }
    }
    assignment
}

/// A work-palette value could not be observed through the existing hex/OKLCH path.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PaletteObservationError {
    InvalidResolvedColor { abstract_color: Color },
}

/// Observe all abstract colors from the actual assignment for one render request.
///
/// The returned DTO contains no selection policy. It only exposes the concrete
/// RGB and the same OKLCH lightness already used by palette assignment.
pub fn work_palette_context(
    color_map: &BTreeMap<String, String>,
    render_seed: Option<Seed>,
    catalog_id: Option<&str>,
    background: Color,
) -> Result<ResolvedPaletteContext, PaletteObservationError> {
    let assignment = work_color_assignment(color_map, render_seed, catalog_id);
    let observations = [
        Color::White,
        Color::Black,
        Color::Blue,
        Color::Red,
        Color::Green,
        Color::Gray,
        Color::Yellow,
        Color::Orange,
        Color::Purple,
    ]
    .map(|color| observe_resolved_color(color, color_map, &assignment))
    .into_iter()
    .collect::<Result<Vec<_>, _>>()?;
    Ok(ResolvedPaletteContext::new(
        observe_resolved_color(background, color_map, &assignment)?,
        observe_resolved_color(Color::Black, color_map, &assignment)?,
        observe_resolved_color(Color::White, color_map, &assignment)?,
    )
    .with_observations(observations.try_into().expect("nine abstract colors")))
}

fn observe_resolved_color(
    abstract_color: Color,
    color_map: &BTreeMap<String, String>,
    assignment: &BTreeMap<String, String>,
) -> Result<ResolvedPaletteColor, PaletteObservationError> {
    let concrete = resolve_color(abstract_color, None, color_map, assignment);
    let (red, green, blue) = hex_to_rgb(&concrete)
        .ok_or(PaletteObservationError::InvalidResolvedColor { abstract_color })?;
    let (lightness, _, _) = oklch_from_hex(&concrete)
        .ok_or(PaletteObservationError::InvalidResolvedColor { abstract_color })?;
    Ok(ResolvedPaletteColor::new(
        abstract_color,
        [red, green, blue],
        lightness,
    ))
}

pub(crate) fn normalized_label(value: &str) -> String {
    let mut result = String::new();
    let mut separator = true;
    for character in value.to_lowercase().chars() {
        let is_separator = character.is_whitespace()
            || matches!(
                character,
                ':' | '_' | '(' | ')' | '\'' | '"' | '.' | ',' | '/' | '-'
            );
        if is_separator {
            if !separator && !result.is_empty() {
                result.push(' ');
            }
            separator = true;
        } else {
            result.push(character);
            separator = false;
        }
    }
    result.trim().to_owned()
}

fn ascii_words(value: &str) -> BTreeSet<String> {
    let mut words = BTreeSet::new();
    let mut current = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_lowercase() || byte.is_ascii_digit() {
            current.push(char::from(byte));
        } else if !current.is_empty() {
            words.insert(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        words.insert(current);
    }
    words
}

fn hue_tokens(name: &str) -> &'static [&'static str] {
    match name {
        "white" => &[
            "white", "ivory", "paper", "linen", "blanc", "bianco", "aspro", "白", "胡粉", "象牙",
            "生成",
        ],
        "black" => &[
            "black", "ink", "sumi", "obsidian", "basalt", "skotadi", "黒", "墨", "玄", "暗",
        ],
        "blue" => &[
            "blue",
            "cyan",
            "azure",
            "ultramarine",
            "cobalt",
            "lapis",
            "bleu",
            "azul",
            "青",
            "藍",
            "水色",
            "空色",
            "瑠璃",
        ],
        "green" => &[
            "green", "verd", "jade", "olive", "cactus", "緑", "青緑", "翡翠", "常磐", "玉", "草",
        ],
        "gray" => &[
            "gray", "grey", "silver", "ash", "stone", "granit", "petra", "灰", "鼠", "銀", "石",
        ],
        "red" => &[
            "red",
            "rose",
            "pink",
            "carmine",
            "cinnabar",
            "terra",
            "rosa",
            "vermilion",
            "赤",
            "朱",
            "紅",
            "桜",
            "桃",
            "薔薇",
        ],
        "yellow" => &[
            "yellow",
            "gold",
            "ochre",
            "ocra",
            "giallo",
            "jaune",
            "napoli",
            "kesar",
            "haldi",
            "sun",
            "ilios",
            "山吹",
            "金",
            "黄",
            "琉璃金",
        ],
        "orange" => &[
            "orange",
            "apricot",
            "terracotta",
            "cempasuchil",
            "ff4d00",
            "橙",
            "蜜柑",
        ],
        "purple" => &[
            "purple",
            "violet",
            "lilac",
            "murasaki",
            "宮廷紫",
            "藤",
            "紫",
        ],
        "brown" => &[
            "brown", "sienna", "umber", "ombra", "chandan", "lera", "sepia", "茶", "土", "焦",
        ],
        _ => &[],
    }
}

#[derive(Clone, Copy)]
enum MachineColorNote {
    CycleRestored,
    ForegroundVisible,
    CoverageClause,
    PaperShardRestored,
    PrimaryStrokePromoted,
    SensoryLayerVisible,
}

const MACHINE_COLOR_NOTES: [MachineColorNote; 6] = [
    MachineColorNote::CycleRestored,
    MachineColorNote::ForegroundVisible,
    MachineColorNote::CoverageClause,
    MachineColorNote::PaperShardRestored,
    MachineColorNote::PrimaryStrokePromoted,
    MachineColorNote::SensoryLayerVisible,
];

fn abstract_colors(value: &str) -> bool {
    !value.is_empty()
        && value
            .split('/')
            .all(|color| HINT_HUE_PRIORITY.contains(&color))
}

fn machine_color_note(clause: &str) -> bool {
    let clause = clause.trim();
    MACHINE_COLOR_NOTES.iter().any(|pattern| match pattern {
        MachineColorNote::CycleRestored => clause
            .strip_suffix(" restored in color_cycle from DDL color intent")
            .is_some_and(abstract_colors),
        MachineColorNote::ForegroundVisible => clause
            .strip_suffix(" foreground made visible")
            .is_some_and(abstract_colors),
        MachineColorNote::CoverageClause => clause
            .strip_prefix("coverage from DDL clause: ")
            .is_some_and(|ddl| !ddl.trim().is_empty()),
        MachineColorNote::PaperShardRestored => {
            clause == "paper_shard motif restored from DDL intent"
        }
        MachineColorNote::PrimaryStrokePromoted => clause
            .strip_suffix(" promoted to primary stroke from DDL color intent")
            .is_some_and(abstract_colors),
        MachineColorNote::SensoryLayerVisible => clause
            .split_once(" sensory layer made visible as pale ")
            .is_some_and(|(first, second)| abstract_colors(first) && abstract_colors(second)),
    })
}

fn hint_hues(hint: &str) -> BTreeSet<&'static str> {
    let hint = hint
        .split([';', '；'])
        .filter(|clause| !machine_color_note(clause))
        .collect::<Vec<_>>()
        .join(";");
    let normalized = normalized_label(&hint);
    let words = ascii_words(&normalized);
    let mut hues = BTreeSet::new();
    for name in [
        "white", "black", "blue", "green", "gray", "red", "yellow", "orange", "purple", "brown",
    ] {
        if hue_tokens(name).iter().any(|token| {
            if token.bytes().all(|byte| byte.is_ascii_lowercase()) {
                words.contains(*token)
            } else {
                hint.contains(token)
            }
        }) {
            hues.insert(name);
        }
    }
    hues
}

/// Resolve an abstract color and optional nuance against one work assignment.
#[must_use]
pub fn resolve_color(
    color: Color,
    color_hint: Option<&str>,
    color_map: &BTreeMap<String, String>,
    assignment: &BTreeMap<String, String>,
) -> String {
    let name = color.as_str();
    let fallback = assignment
        .get(name)
        .or_else(|| color_map.get(name))
        .cloned()
        .unwrap_or_else(|| default_color(color).to_owned());
    let Some(hint) = color_hint.filter(|hint| !hint.is_empty()) else {
        return fallback;
    };
    let mut desired = hint_hues(hint);
    if desired.len() == 1 && desired.contains("brown") {
        return assignment
            .get("orange")
            .cloned()
            .unwrap_or_else(|| default_named_color("orange").to_owned());
    }
    desired.remove("brown");
    for name in HINT_HUE_PRIORITY {
        if desired.contains(name) {
            return assignment
                .get(name)
                .cloned()
                .unwrap_or_else(|| default_named_color(name).to_owned());
        }
    }
    fallback
}

#[cfg(test)]
mod i183_tests {
    use super::*;

    fn resolve(color: Color, hint: &str) -> String {
        let colors = default_color_map();
        resolve_color(color, Some(hint), &colors, &colors)
    }

    #[test]
    fn i183_foreground_machine_note_keeps_black() {
        assert_eq!(
            resolve(Color::Black, "white foreground made visible"),
            default_color(Color::Black)
        );
    }

    #[test]
    fn i183_promotion_note_keeps_authored_blue() {
        assert_eq!(
            resolve(
                Color::Gray,
                "red promoted to primary stroke from DDL color intent; 青い線"
            ),
            default_color(Color::Blue)
        );
    }

    #[test]
    fn i183_coverage_note_keeps_gray() {
        assert_eq!(
            resolve(
                Color::Gray,
                "coverage from DDL clause: 画面全体に黄色の細筆の小さな楕円を散らす"
            ),
            default_color(Color::Gray)
        );
    }

    #[test]
    fn i183_all_machine_note_patterns_require_complete_clauses() {
        for note in [
            "red/blue restored in color_cycle from DDL color intent",
            "white foreground made visible",
            "coverage from DDL clause: 黄色の弧",
            "paper_shard motif restored from DDL intent",
            "red promoted to primary stroke from DDL color intent",
            "blue sensory layer made visible as pale white",
        ] {
            assert!(machine_color_note(note), "{note}");
            assert_eq!(
                resolve(Color::Gray, note),
                default_color(Color::Gray),
                "{note}"
            );
        }
        assert_eq!(
            resolve(Color::Gray, "white foreground made visible；青い線"),
            default_color(Color::Blue)
        );
        for note in [
            "white foreground made visible today",
            "almost paper_shard motif restored from DDL intent",
            "brown foreground made visible",
            "white//red restored in color_cycle from DDL color intent",
            "withered grass kept as muted blue-gray",
        ] {
            assert!(!machine_color_note(note), "{note}");
        }
    }

    #[test]
    fn i183_authored_color_hints_remain_effective() {
        assert_eq!(resolve(Color::Green, "黄色"), default_color(Color::Yellow));
        assert_eq!(
            resolve(Color::Gray, "red restored flowers are visible"),
            default_color(Color::Red)
        );
        assert_eq!(
            resolve(Color::Gray, "white foreground made visible today"),
            default_color(Color::White)
        );
        assert_eq!(
            resolve(Color::Gray, "withered grass kept as muted blue-gray"),
            default_color(Color::Blue)
        );
    }
}
