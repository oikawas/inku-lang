//! Deterministic work-palette assignment and color-hint resolution.

use std::collections::{BTreeMap, BTreeSet, HashSet};

use sha2::{Digest, Sha256};

use crate::types::{Color, Seed};

const ACHROMATIC_COLORS: [&str; 3] = ["black", "gray", "white"];
const CHROMATIC_COLORS: [&str; 6] = ["red", "orange", "yellow", "green", "blue", "purple"];
const HINT_HUE_PRIORITY: [&str; 9] = [
    "red", "orange", "yellow", "green", "blue", "purple", "white", "black", "gray",
];
const OKLCH_CHROMA_FLOOR: f64 = 0.035;

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
    let linearize = |component: u8| {
        let channel = f64::from(component) / 255.0;
        if channel <= 0.04045 {
            channel / 12.92
        } else {
            ((channel + 0.055) / 1.055).powf(2.4)
        }
    };
    let (red, green, blue) = (linearize(red), linearize(green), linearize(blue));
    let light_channel = 0.412_221_470_8 * red + 0.536_332_536_3 * green + 0.051_445_992_9 * blue;
    let medium_channel = 0.211_903_498_2 * red + 0.680_699_545_1 * green + 0.107_396_956_6 * blue;
    let short_channel = 0.088_302_461_9 * red + 0.281_718_837_6 * green + 0.629_978_700_5 * blue;
    let (light_root, medium_root, short_root) = (
        light_channel.cbrt(),
        medium_channel.cbrt(),
        short_channel.cbrt(),
    );
    let lightness =
        0.210_454_255_3 * light_root + 0.793_617_785 * medium_root - 0.004_072_046_8 * short_root;
    let a =
        1.977_998_495_1 * light_root - 2.428_592_205 * medium_root + 0.450_593_709_9 * short_root;
    let b =
        0.025_904_037_1 * light_root + 0.782_771_766_2 * medium_root - 0.808_675_766 * short_root;
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
    assignment
}

fn normalized_label(value: &str) -> String {
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

fn hint_hues(hint: &str) -> BTreeSet<&'static str> {
    let normalized = normalized_label(hint);
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
    let name = color_name(color);
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

/// Retain only color-hint terms that affect mark rendering after a color cycle.
#[must_use]
pub fn render_effect_hint(color_hint: Option<&str>) -> Option<String> {
    let normalized = normalized_label(color_hint.filter(|hint| !hint.is_empty())?);
    let tokens = [
        "membrane",
        "haze",
        "fog",
        "mist",
        "atmosphere",
        "膜",
        "霞",
        "霧",
        "靄",
        "soft light",
        "柔らかな光",
        "陽光",
        "日差し",
        "scent",
        "fragrance",
        "香り",
        "匂",
        "waiting buds",
        "開花を待つ蕾",
        "蕾",
        "つぼみ",
        "five-sense",
        "五感",
        "fade directional",
        "fade=directional",
        "fade outward",
        "fade=outward",
        "reflection",
        "反射",
        "映り",
    ];
    let kept = tokens
        .into_iter()
        .filter(|token| normalized.contains(token))
        .collect::<Vec<_>>();
    (!kept.is_empty()).then(|| kept.join("; "))
}
