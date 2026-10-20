//! Refinements that change one part of a saved Score and draw it again
//! (the author, 2026-10-14): the touches (てざわり), the support (じ) and the
//! color arrangement.
//!
//! Server, Android and Swift each wrote these rules by hand, and the copies
//! drifted (integer widths, the default tool, the language of an added ground
//! sentence, the saved metadata). The rules are Server's, moved here
//! (`tool_variants.py`, `ground_variants.py`, `color_arrangements.py`), and every
//! host asks this one copy. Two rulings changed them on the way (2026-10-17):
//! an added ground sentence takes its language from the shared
//! instruction-language rule, and the color arrangement's metadata is
//! `{color_arrangement_index, catalog_id}`, which Server rebuilds on saving.
//!
//! Every action is pure: the host reads the saved work, calls one action, and
//! draws the returned Score with the parent's seed.

use std::collections::{BTreeMap, BTreeSet};

use inku_ddl::{ResolvedInstructionLanguage, resolve_instruction_language, saijiki_asset};
use serde::Deserialize;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

use crate::identity::python_strip;
use crate::laws_record::LawsLayerRecord;
use crate::retouch::{Retouch, retouch, retouch_with_record, tools};

pub const SAVED_VARIANTS_SCHEMA_ID: &str = "inku.saved-variants.v1";

const OPTION_COUNT: usize = 4;
const PAGE_SIZE: u128 = 8;
const GROUND_CATEGORY: &str = "ji";
const TOUCH_CATEGORY: &str = "tezawari";
const PAINT_ATTRIBUTES: [&str; 6] = [
    "fill",
    "stroke",
    "stop-color",
    "flood-color",
    "lighting-color",
    "color",
];

/// Why an action gave no answer. `detail` is the message Server has always
/// answered with, so a host can show it unchanged.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Refusal {
    pub reason: &'static str,
    pub detail: String,
}

fn refuse(reason: &'static str, detail: impl Into<String>) -> Refusal {
    Refusal {
        reason,
        detail: detail.into(),
    }
}

// ---------------------------------------------------------------------------
// Touches (てざわり)
// ---------------------------------------------------------------------------

/// The tool the saijiki marks as the default: the one a sentence without a
/// written tool is drawn with.
fn default_tool() -> String {
    saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == TOUCH_CATEGORY)
        .and_then(|category| category.words.iter().find(|word| word.default))
        .and_then(|word| word.score_value.clone())
        .unwrap_or_else(|| "pen".to_owned())
}

fn tool_values() -> Vec<String> {
    tools().into_iter().map(|tool| tool.value).collect()
}

/// The source instruction an instruction of the Score was drawn for.
fn owner_index(instruction: &Value) -> Option<i64> {
    let owner = instruction
        .get("arrangement")?
        .get("resolved")?
        .get("owner")?;
    if owner.get("kind")?.as_str()? != "source_instruction" {
        return None;
    }
    owner.get("instruction_index")?.as_i64()
}

fn score_instructions(score: &Value) -> &[Value] {
    score
        .get("instructions")
        .and_then(Value::as_array)
        .map_or(&[], Vec::as_slice)
}

/// The tool each sentence was drawn with, read from the saved Score
/// (`tool_variants.drawn_tools`).
#[must_use]
pub fn drawn_tools(score: &Value, sentences: &[usize]) -> BTreeMap<usize, String> {
    let known = tool_values();
    let default = default_tool();
    let mut drawn = BTreeMap::new();
    for instruction in score_instructions(score) {
        let Some(index) = owner_index(instruction).and_then(|index| usize::try_from(index).ok())
        else {
            continue;
        };
        if sentences.contains(&index) && !drawn.contains_key(&index) {
            let weight = instruction.get("weight").and_then(Value::as_str);
            let tool = weight
                .filter(|weight| known.iter().any(|tool| tool == weight))
                .map_or_else(|| default.clone(), str::to_owned);
            drawn.insert(index, tool);
        }
    }
    sentences
        .iter()
        .map(|index| {
            (
                *index,
                drawn.get(index).cloned().unwrap_or_else(|| default.clone()),
            )
        })
        .collect()
}

/// The saved Score with each asked sentence's instructions drawn with its tool
/// (`tool_variants.score_with_tools`).
#[must_use]
pub fn score_with_tools(score: &Value, asked: &BTreeMap<usize, String>) -> Value {
    let mut changed = score.clone();
    if let Some(instructions) = changed
        .get_mut("instructions")
        .and_then(Value::as_array_mut)
    {
        for instruction in instructions {
            let index = owner_index(instruction).and_then(|index| usize::try_from(index).ok());
            if let (Some(tool), Some(object)) = (
                index.and_then(|index| asked.get(&index)),
                instruction.as_object_mut(),
            ) {
                object.insert("weight".to_owned(), Value::String(tool.clone()));
            }
        }
    }
    changed
}

/// A small seeded generator (SplitMix64): the host passes a new seed each time
/// the author asks for options, so the options change from one press to the next.
struct Draw(u64);

impl Draw {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut value = self.0;
        value = (value ^ (value >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        value ^ (value >> 31)
    }

    fn below(&mut self, bound: usize) -> usize {
        // Bounds here are a dozen tools; the modulo bias is far below a
        // difference anyone could see between offered options.
        (self.next() % bound as u64) as usize
    }
}

/// Up to four tool assignments, each changing at least one sentence
/// (`tool_variants.options`). `uniform` gives every sentence one tool, a
/// different one per option, never a tool every sentence already has;
/// `per_sentence` draws for each sentence a tool other than the one it has.
fn tool_options(
    drawn: &BTreeMap<usize, String>,
    mode: &str,
    seed: u64,
) -> Vec<BTreeMap<usize, String>> {
    let known = tool_values();
    let mut draw = Draw(seed);
    if drawn.is_empty() {
        return Vec::new();
    }
    if mode == "uniform" {
        let mut offered: Vec<&String> = known
            .iter()
            .filter(|tool| drawn.values().any(|current| current != *tool))
            .collect();
        let mut chosen = Vec::new();
        while chosen.len() < OPTION_COUNT && !offered.is_empty() {
            let tool = offered.remove(draw.below(offered.len()));
            chosen.push(drawn.keys().map(|index| (*index, tool.clone())).collect());
        }
        return chosen;
    }
    let mut chosen: Vec<BTreeMap<usize, String>> = Vec::new();
    for _ in 0..OPTION_COUNT * 8 {
        let option: BTreeMap<usize, String> = drawn
            .iter()
            .map(|(index, current)| {
                let others: Vec<&String> = known.iter().filter(|tool| *tool != current).collect();
                (*index, others[draw.below(others.len())].clone())
            })
            .collect();
        if !chosen.contains(&option) {
            chosen.push(option);
        }
        if chosen.len() == OPTION_COUNT {
            break;
        }
    }
    chosen
}

fn changes(drawn: &BTreeMap<usize, String>, asked: &BTreeMap<usize, String>) -> Value {
    Value::Array(
        asked
            .iter()
            .filter(|(index, tool)| drawn.get(index) != Some(tool))
            .map(|(index, tool)| json!({"index": index, "from": drawn[index], "to": tool}))
            .collect(),
    )
}

fn keyed(asked: &BTreeMap<usize, String>) -> Value {
    Value::Object(
        asked
            .iter()
            .map(|(index, tool)| (index.to_string(), Value::String(tool.clone())))
            .collect(),
    )
}

struct TouchWork<'a> {
    config: &'a crate::machine::PipelineConfig,
    source: &'a str,
    score: &'a Value,
}

impl TouchWork<'_> {
    fn limits(&self) -> Result<inku_ddl::MacroExpansionLimits, Refusal> {
        self.config.compiler.macro_limits().map_err(|_| {
            refuse(
                "touch_cannot_change",
                "touch cannot change: invalid_request",
            )
        })
    }

    fn retouch(&self, asked: &BTreeMap<usize, String>) -> Result<Retouch, Refusal> {
        Ok(retouch(
            self.source,
            self.config.language,
            &self.config.definitions,
            self.limits()?,
            asked,
        ))
    }

    fn retouch_with_record(
        &self,
        asked: &BTreeMap<usize, String>,
        record: &LawsLayerRecord,
    ) -> Result<(Retouch, LawsLayerRecord), Refusal> {
        Ok(retouch_with_record(
            self.source,
            self.config.language,
            &self.config.definitions,
            self.limits()?,
            asked,
            record,
        ))
    }

    /// The Score's tool for each sentence whose tool can change.
    fn drawn(&self) -> Result<BTreeMap<usize, String>, Refusal> {
        if !self.score.is_object() {
            return Err(refuse("no_score", "saved work has no Score to redraw"));
        }
        match self.retouch(&BTreeMap::new())? {
            Retouch::Read { sentences } => {
                let indices: Vec<usize> = sentences.iter().map(|sentence| sentence.index).collect();
                Ok(drawn_tools(self.score, &indices))
            }
            Retouch::Unchanged { reason } => Err(refuse(
                "touch_cannot_change",
                format!("touch cannot change: {reason}"),
            )),
            Retouch::Retouched { .. } => Err(refuse(
                "touch_cannot_change",
                "touch cannot change: unknown",
            )),
        }
    }
}

fn tool_labels() -> Value {
    Value::Array(
        tools()
            .into_iter()
            .map(|tool| json!({"value": tool.value, "ja": tool.ja, "en": tool.en}))
            .collect(),
    )
}

fn tool_plan(work: &TouchWork<'_>, mode: &str, seed: u64) -> Result<Value, Refusal> {
    check_mode(mode)?;
    let drawn = work.drawn()?;
    let mut entries = Vec::new();
    for asked in tool_options(&drawn, mode, seed) {
        if let Retouch::Retouched { source, .. } = work.retouch(&asked)? {
            entries.push(json!({
                "tools": keyed(&asked),
                "changes": changes(&drawn, &asked),
                "ddl": source,
            }));
        }
    }
    Ok(json!({
        "mode": mode,
        "tool_labels": tool_labels(),
        "sentences": drawn.iter().map(|(index, tool)| json!({"index": index, "tool": tool})).collect::<Vec<_>>(),
        "entries": entries,
    }))
}

fn tool_render(
    work: &TouchWork<'_>,
    mode: &str,
    asked: &BTreeMap<String, String>,
    record: Option<&LawsLayerRecord>,
) -> Result<Value, Refusal> {
    check_mode(mode)?;
    let drawn = work.drawn()?;
    let mut tools_asked = BTreeMap::new();
    for (index, tool) in asked {
        // Python's `int()` reads the key; a negative index names no sentence.
        let index: i128 = index
            .trim_matches(crate::identity::is_python_space)
            .parse()
            .map_err(|_| refuse("not_indexed", "tools are keyed by sentence index"))?;
        let Ok(index) = usize::try_from(index) else {
            return Err(refuse(
                "unknown_sentence_or_tool",
                "tools must name changeable sentences and known tools",
            ));
        };
        tools_asked.insert(index, tool.clone());
    }
    let known = tool_values();
    if tools_asked.is_empty()
        || tools_asked
            .iter()
            .any(|(index, tool)| !drawn.contains_key(index) || !known.contains(tool))
    {
        return Err(refuse(
            "unknown_sentence_or_tool",
            "tools must name changeable sentences and known tools",
        ));
    }
    if tools_asked
        .iter()
        .all(|(index, tool)| drawn[index] == *tool)
    {
        return Err(refuse(
            "no_change",
            "tools must change at least one sentence",
        ));
    }
    let (answer, record) = match record {
        Some(record) => {
            let (answer, record) = work.retouch_with_record(&tools_asked, record)?;
            (answer, Some(record))
        }
        None => (work.retouch(&tools_asked)?, None),
    };
    let source = match answer {
        Retouch::Retouched { source, .. } => source,
        Retouch::Unchanged { reason } => {
            return Err(refuse(
                "touch_cannot_change",
                format!("touch cannot change: {reason}"),
            ));
        }
        Retouch::Read { .. } => {
            return Err(refuse(
                "touch_cannot_change",
                "touch cannot change: unknown",
            ));
        }
    };
    let mut answer = json!({
        "score": score_with_tools(work.score, &tools_asked),
        "ddl": source,
        "derivation_metadata": {
            "tool_mode": mode,
            "tools": keyed(&tools_asked),
            "changes": changes(&drawn, &tools_asked),
        },
    });
    // A host that keeps the parent's laws record keeps the child's (2026-10-20).
    if let Some(record) = record {
        answer["laws_layers"] = json!(record);
    }
    Ok(answer)
}

fn check_mode(mode: &str) -> Result<(), Refusal> {
    if matches!(mode, "uniform" | "per_sentence") {
        Ok(())
    } else {
        Err(refuse("unknown_mode", format!("unknown mode: {mode}")))
    }
}

// ---------------------------------------------------------------------------
// Support (じ)
// ---------------------------------------------------------------------------

struct Ground {
    material: String,
    ja: String,
    en: String,
}

fn grounds() -> Vec<Ground> {
    saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == GROUND_CATEGORY)
        .map(|category| {
            category
                .words
                .iter()
                .filter_map(|word| {
                    Some(Ground {
                        material: word.score_value.clone()?,
                        ja: word.surface_ja.clone(),
                        en: word.surface_en.clone()?,
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

/// The material of the saved Score's ground, `plain` when it names none.
#[must_use]
pub fn current_material(score: &Value) -> String {
    score
        .get("canvas")
        .and_then(|canvas| canvas.get("ground"))
        .and_then(|ground| ground.get("material"))
        .and_then(Value::as_str)
        .unwrap_or("plain")
        .to_owned()
}

fn ground_sentence(ground: &Ground, language: ResolvedInstructionLanguage) -> String {
    match language {
        ResolvedInstructionLanguage::Ja => format!("{}。", ground.ja),
        ResolvedInstructionLanguage::En => {
            let mut characters = ground.en.chars();
            let first: String = characters
                .next()
                .map(char::to_uppercase)
                .into_iter()
                .flatten()
                .collect();
            format!("{first}{}.", characters.as_str())
        }
    }
}

/// The language of a line that is one ground sentence, or `None`.
fn ground_line(line: &str, all: &[Ground]) -> Option<ResolvedInstructionLanguage> {
    let text = python_strip(line);
    for ground in all {
        if text == ground_sentence(ground, ResolvedInstructionLanguage::Ja) {
            return Some(ResolvedInstructionLanguage::Ja);
        }
        if text.to_lowercase()
            == ground_sentence(ground, ResolvedInstructionLanguage::En).to_lowercase()
        {
            return Some(ResolvedInstructionLanguage::En);
        }
    }
    None
}

/// The instructions with their ground sentence replaced, or one placed first.
/// Without a written ground sentence or a saved language, the language is the
/// shared instruction-language rule's (the author, 2026-10-17).
#[must_use]
pub fn ddl_with_ground(ddl: &str, material: &str, language: Option<&str>) -> Option<String> {
    let all = grounds();
    let ground = all.iter().find(|ground| ground.material == material)?;
    let mut lines: Vec<String> = ddl.split('\n').map(str::to_owned).collect();
    for line in &mut lines {
        if let Some(line_language) = ground_line(line, &all) {
            *line = ground_sentence(ground, line_language);
            return Some(lines.join("\n"));
        }
    }
    let language = match language {
        Some("ja") => ResolvedInstructionLanguage::Ja,
        Some("en") => ResolvedInstructionLanguage::En,
        _ => resolve_instruction_language(ddl, Some("auto"), "ja")
            .unwrap_or(ResolvedInstructionLanguage::Ja),
    };
    let sentence = ground_sentence(ground, language);
    Some(if ddl.is_empty() {
        sentence
    } else {
        format!("{sentence}\n{ddl}")
    })
}

/// The saved Score drawn on another material (`ground_variants.score_with_ground`).
#[must_use]
pub fn score_with_ground(score: &Value, material: &str) -> Value {
    let mut changed = score.clone();
    let Some(object) = changed.as_object_mut() else {
        return changed;
    };
    match object.get_mut("canvas") {
        Some(Value::Object(canvas)) => {
            let mut ground = match canvas.get("ground") {
                Some(Value::Object(ground)) => ground.clone(),
                _ => Map::new(),
            };
            ground.insert("material".to_owned(), Value::String(material.to_owned()));
            canvas.insert("ground".to_owned(), Value::Object(ground));
        }
        other => {
            let aspect = other
                .cloned()
                .unwrap_or_else(|| Value::String("square".to_owned()));
            object.insert(
                "canvas".to_owned(),
                json!({"aspect": aspect, "ground": {"material": material}}),
            );
        }
    }
    changed
}

fn ground_labels(material: &str, key: &str, all: &[Ground]) -> Map<String, Value> {
    let named = all.iter().find(|ground| ground.material == material);
    let mut labels = Map::new();
    labels.insert(
        format!("{key}_ja"),
        named.map_or(Value::Null, |ground| Value::String(ground.ja.clone())),
    );
    labels.insert(
        format!("{key}_en"),
        named.map_or(Value::Null, |ground| Value::String(ground.en.clone())),
    );
    labels
}

fn ground_plan(score: &Value) -> Value {
    let all = grounds();
    let current = current_material(score);
    let mut plan = Map::new();
    plan.insert("current".to_owned(), Value::String(current.clone()));
    plan.extend(ground_labels(&current, "current_label", &all));
    let entries: Vec<Value> = all
        .iter()
        .filter(|ground| ground.material != current)
        .map(|ground| {
            let mut entry = Map::new();
            entry.insert(
                "material".to_owned(),
                Value::String(ground.material.clone()),
            );
            entry.extend(ground_labels(&ground.material, "label", &all));
            Value::Object(entry)
        })
        .collect();
    plan.insert("entries".to_owned(), Value::Array(entries));
    Value::Object(plan)
}

fn ground_render(
    score: &Value,
    source: &str,
    material: &str,
    language: Option<&str>,
) -> Result<Value, Refusal> {
    if !score.is_object() {
        return Err(refuse("no_score", "saved work has no Score to redraw"));
    }
    let current = current_material(score);
    if material == current || !grounds().iter().any(|ground| ground.material == material) {
        return Err(refuse(
            "unknown_ground",
            "ground must be a named support the work is not on",
        ));
    }
    let ddl = ddl_with_ground(source, material, language).ok_or_else(|| {
        refuse(
            "unknown_ground",
            "ground must be a named support the work is not on",
        )
    })?;
    Ok(json!({
        "score": score_with_ground(score, material),
        "ddl": ddl,
        "derivation_metadata": {"ground_material": material, "parent_ground_material": current},
    }))
}

// ---------------------------------------------------------------------------
// Color arrangement
// ---------------------------------------------------------------------------

/// `#rgb` or `#rrggbb` as lower-case `#rrggbb`, or `None`.
#[must_use]
pub fn normalized_hex(value: &str) -> Option<String> {
    let value = python_strip(value).to_lowercase();
    let digits = value.strip_prefix('#')?;
    if !digits.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    match digits.len() {
        3 => Some(format!(
            "#{}",
            digits
                .chars()
                .flat_map(|digit| [digit, digit])
                .collect::<String>()
        )),
        6 => Some(value),
        _ => None,
    }
}

fn perm(n: usize, k: usize) -> Option<u128> {
    if k > n {
        return Some(0);
    }
    (0..k).try_fold(1u128, |product, step| {
        product.checked_mul((n - step) as u128)
    })
}

fn mul_mod(mut left: u128, mut right: u128, modulus: u128) -> u128 {
    left %= modulus;
    let mut result = 0u128;
    while right > 0 {
        if right & 1 == 1 {
            result = (result + left) % modulus;
        }
        left = (left << 1) % modulus;
        right >>= 1;
    }
    result
}

fn gcd(mut left: u128, mut right: u128) -> u128 {
    while right != 0 {
        (left, right) = (right, left % right);
    }
    left
}

/// The distinct concrete-color assignments of a saved work, ranked without
/// listing them (`color_arrangements.ColorArrangements`).
struct ColorArrangements {
    palette: Vec<String>,
    used: Vec<String>,
    identity_rank: u128,
    start: u128,
    total: u128,
}

const TOO_LARGE: &str = "color arrangement space is too large";

impl ColorArrangements {
    fn from_saved(svg: &str, color_map: &Map<String, Value>, key: &str) -> Result<Self, Refusal> {
        let no_palette = || refuse("no_palette", "saved color catalog has no usable palette");
        let colors: Vec<Option<String>> = color_map
            .iter()
            .filter(|(name, _)| name.starts_with("palette:"))
            .map(|(_, value)| value.as_str().and_then(normalized_hex))
            .collect();
        if colors.is_empty() || colors.iter().any(Option::is_none) {
            return Err(no_palette());
        }
        let palette: Vec<String> = colors
            .into_iter()
            .flatten()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let document = roxmltree::Document::parse(svg)
            .map_err(|_| refuse("no_svg", "saved work has no usable SVG"))?;
        let mut paints = BTreeSet::new();
        for element in document.descendants().filter(roxmltree::Node::is_element) {
            let mut attributes: Vec<(String, String)> = element
                .attributes()
                .filter(|attribute| attribute.namespace().is_none())
                .map(|attribute| (attribute.name().to_owned(), attribute.value().to_owned()))
                .collect();
            let style = attributes
                .iter()
                .find(|(name, _)| name == "style")
                .map(|(_, value)| value.clone())
                .unwrap_or_default();
            for declaration in style.split(';') {
                if let Some((name, value)) = declaration.split_once(':') {
                    let name = python_strip(name).to_owned();
                    let value = python_strip(value).to_owned();
                    attributes.retain(|(existing, _)| *existing != name);
                    attributes.push((name, value));
                }
            }
            for (name, value) in attributes {
                if PAINT_ATTRIBUTES.contains(&name.as_str())
                    && let Some(color) = normalized_hex(&value)
                    && palette.contains(&color)
                {
                    paints.insert(color);
                }
            }
        }
        let used: Vec<String> = paints.into_iter().collect();
        let mut remaining = palette.clone();
        let mut identity_rank = 0u128;
        for (position, color) in used.iter().enumerate() {
            let digit = remaining
                .iter()
                .position(|candidate| candidate == color)
                .expect("used color is in the palette");
            let block = perm(remaining.len() - 1, used.len() - position - 1)
                .ok_or_else(|| refuse("too_large", TOO_LARGE))?;
            identity_rank = (digit as u128)
                .checked_mul(block)
                .and_then(|step| identity_rank.checked_add(step))
                .ok_or_else(|| refuse("too_large", TOO_LARGE))?;
            remaining.remove(digit);
        }
        let digest = Sha256::digest(key.as_bytes());
        let start = u128::from(u64::from_be_bytes(
            digest[..8].try_into().expect("eight bytes"),
        ));
        let total =
            perm(palette.len(), used.len()).ok_or_else(|| refuse("too_large", TOO_LARGE))? - 1;
        Ok(Self {
            palette,
            used,
            identity_rank,
            start,
            total,
        })
    }

    fn page(&self, cursor: u128) -> Value {
        let end = (cursor.saturating_add(PAGE_SIZE)).min(self.total);
        let entries: Vec<Value> = (cursor..end)
            .map(|index| json!({"index": index_value(index)}))
            .collect();
        json!({
            "entries": entries,
            "next_cursor": if end < self.total { index_value(end) } else { Value::Null },
            "total": index_value(self.total),
        })
    }

    /// `round(total * (sqrt(5) - 1) / 2)` as Python computes it, then the first
    /// stride coprime with the count.
    fn stride(&self) -> u128 {
        let scaled = (self.total as f64 * (5f64.sqrt() - 1.0)) / 2.0;
        let mut stride = (scaled.round_ties_even() as u128).max(1);
        while gcd(stride, self.total) != 1 {
            stride += 1;
        }
        stride
    }

    fn substitution(&self, index: u128) -> Result<BTreeMap<String, String>, Refusal> {
        if index >= self.total {
            return Err(refuse(
                "bad_index",
                "color arrangement index is exhausted or invalid",
            ));
        }
        let spread =
            (self.start % self.total + mul_mod(index, self.stride(), self.total)) % self.total;
        let mut rank = spread + u128::from(spread >= self.identity_rank);
        let mut remaining = self.palette.clone();
        let mut chosen = Vec::new();
        for position in 0..self.used.len() {
            let block = perm(remaining.len() - 1, self.used.len() - position - 1)
                .ok_or_else(|| refuse("too_large", TOO_LARGE))?;
            let digit = (rank / block) as usize;
            rank %= block;
            chosen.push(remaining.remove(digit));
        }
        Ok(self.used.iter().cloned().zip(chosen).collect())
    }

    /// The parent's one-pass substitutions composed with this assignment.
    fn color_map(
        &self,
        parent: &Map<String, Value>,
        index: u128,
    ) -> Result<Map<String, Value>, Refusal> {
        let substitution = self.substitution(index)?;
        let invalid = || {
            refuse(
                "invalid_arrangement",
                "saved work has an invalid color arrangement",
            )
        };
        let mut previous = BTreeMap::new();
        for (name, value) in parent {
            if let Some(source) = name.strip_prefix("recolor:") {
                let source = normalized_hex(source).ok_or_else(invalid)?;
                let target = value
                    .as_str()
                    .and_then(normalized_hex)
                    .ok_or_else(invalid)?;
                previous.insert(source, target);
            }
        }
        let mut result: Map<String, Value> = parent
            .iter()
            .filter(|(name, _)| !name.starts_with("recolor:"))
            .map(|(name, value)| (name.clone(), value.clone()))
            .collect();
        let mut originals: BTreeSet<String> = result
            .values()
            .filter_map(|value| value.as_str().and_then(normalized_hex))
            .collect();
        originals.extend(previous.keys().cloned());
        for original in originals {
            let current = previous.get(&original).unwrap_or(&original);
            let target = substitution.get(current).unwrap_or(current);
            if *target != original {
                result.insert(format!("recolor:{original}"), Value::String(target.clone()));
            }
        }
        Ok(result)
    }
}

/// An index as a JSON number when it fits, so hosts read ordinary integers.
fn index_value(index: u128) -> Value {
    u64::try_from(index).map_or_else(|_| Value::String(index.to_string()), |index| json!(index))
}

fn read_index(value: &Value) -> Option<u128> {
    match value {
        Value::Number(number) => number.as_u64().map(u128::from),
        Value::String(text) => text.parse().ok(),
        _ => None,
    }
}

// ---------------------------------------------------------------------------
// The JSON boundary
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
enum Request {
    ToolPlan {
        config: Box<crate::machine::PipelineConfig>,
        source: String,
        score: Value,
        mode: String,
        seed: u64,
    },
    ToolRender {
        config: Box<crate::machine::PipelineConfig>,
        source: String,
        score: Value,
        mode: String,
        tools: BTreeMap<String, String>,
        /// The parent's laws record, when the host keeps one.
        #[serde(default)]
        laws_layers: Option<LawsLayerRecord>,
    },
    GroundPlan {
        score: Value,
    },
    GroundRender {
        score: Value,
        source: String,
        material: String,
        #[serde(default)]
        language: Option<String>,
    },
    ColorPlan {
        svg: String,
        color_map: Map<String, Value>,
        work_id: String,
        cursor: Value,
    },
    ColorRender {
        svg: String,
        color_map: Map<String, Value>,
        work_id: String,
        index: Value,
        catalog_id: String,
    },
}

fn answer(request: Request) -> Result<Value, Refusal> {
    match request {
        Request::ToolPlan {
            config,
            source,
            score,
            mode,
            seed,
        } => tool_plan(
            &TouchWork {
                config: &config,
                source: &source,
                score: &score,
            },
            &mode,
            seed,
        ),
        Request::ToolRender {
            config,
            source,
            score,
            mode,
            tools,
            laws_layers,
        } => tool_render(
            &TouchWork {
                config: &config,
                source: &source,
                score: &score,
            },
            &mode,
            &tools,
            laws_layers.as_ref(),
        ),
        Request::GroundPlan { score } => Ok(ground_plan(&score)),
        Request::GroundRender {
            score,
            source,
            material,
            language,
        } => ground_render(&score, &source, &material, language.as_deref()),
        Request::ColorPlan {
            svg,
            color_map,
            work_id,
            cursor,
        } => {
            let cursor = read_index(&cursor).ok_or_else(|| {
                refuse("bad_cursor", "color arrangement cursor must be nonnegative")
            })?;
            Ok(ColorArrangements::from_saved(&svg, &color_map, &work_id)?.page(cursor))
        }
        Request::ColorRender {
            svg,
            color_map,
            work_id,
            index,
            catalog_id,
        } => {
            let index = read_index(&index).ok_or_else(|| {
                refuse(
                    "bad_index",
                    "color arrangement index is exhausted or invalid",
                )
            })?;
            let arrangements = ColorArrangements::from_saved(&svg, &color_map, &work_id)?;
            let map = arrangements.color_map(&color_map, index)?;
            Ok(json!({
                "color_map": map,
                "derivation_metadata": {"color_arrangement_index": index_value(index), "catalog_id": catalog_id},
            }))
        }
    }
}

/// JSON in, JSON out, for the hosts' bindings. An answer is
/// `{"schema", "outcome": "ok", ...}` or `{"schema", "outcome": "refused",
/// "reason", "detail"}`; a request that cannot be read answers
/// `{"error": "invalid_request"}`.
#[must_use]
pub fn saved_variants_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<Request>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let mut body = match answer(request) {
        Ok(Value::Object(fields)) => {
            let mut body = Map::new();
            body.insert("outcome".to_owned(), json!("ok"));
            body.extend(fields);
            body
        }
        Ok(_) => return br#"{"error":"internal"}"#.to_vec(),
        Err(refusal) => {
            let mut body = Map::new();
            body.insert("outcome".to_owned(), json!("refused"));
            body.insert("reason".to_owned(), json!(refusal.reason));
            body.insert("detail".to_owned(), json!(refusal.detail));
            body
        }
    };
    body.insert("schema".to_owned(), json!(SAVED_VARIANTS_SCHEMA_ID));
    serde_json::to_vec(&Value::Object(body)).unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cases() -> Value {
        serde_json::from_str(include_str!(
            "../../../../server/tests/data/saved-variant-cases.json"
        ))
        .expect("saved variant cases")
    }

    fn ask(value: Value) -> Value {
        serde_json::from_slice(&saved_variants_json(&serde_json::to_vec(&value).unwrap())).unwrap()
    }

    fn asked(value: &Value) -> BTreeMap<usize, String> {
        value
            .as_object()
            .unwrap()
            .iter()
            .map(|(index, tool)| (index.parse().unwrap(), tool.as_str().unwrap().to_owned()))
            .collect()
    }

    #[test]
    fn the_tools_the_default_and_the_grounds_are_the_saijiki_server_reads() {
        let conditions = &cases()["conditions"];
        assert_eq!(json!(tool_values()), conditions["tools"]);
        assert_eq!(json!(default_tool()), conditions["default_tool"]);
        let materials: Vec<String> = grounds()
            .into_iter()
            .map(|ground| ground.material)
            .collect();
        assert_eq!(json!(materials), conditions["ground_materials"]);
    }

    #[test]
    fn every_shared_tool_case_reads_and_redraws_as_server_does() {
        let table = cases();
        let rows = table["tools"].as_array().unwrap();
        assert!(!rows.is_empty());
        for row in rows {
            let sentences: Vec<usize> = serde_json::from_value(row["sentences"].clone()).unwrap();
            let drawn = drawn_tools(&row["score"], &sentences);
            assert_eq!(keyed(&drawn), row["drawn"], "{}", row["why"]);
            let changed = score_with_tools(&row["score"], &asked(&row["asked"]));
            assert_eq!(changed, row["score_with_tools"], "{}", row["why"]);
        }
    }

    #[test]
    fn every_option_changes_a_sentence_and_follows_its_mode() {
        let count = cases()["conditions"]["count"].as_u64().unwrap() as usize;
        let drawn: BTreeMap<usize, String> = [(0, "pen".to_owned()), (3, "chalk".to_owned())]
            .into_iter()
            .collect();
        for seed in 0..64 {
            let uniform = tool_options(&drawn, "uniform", seed);
            assert_eq!(uniform.len(), count);
            let picked: BTreeSet<&String> = uniform.iter().map(|option| &option[&0]).collect();
            assert_eq!(picked.len(), count, "uniform options use different tools");
            for option in &uniform {
                assert!(option.values().all(|tool| tool == &option[&0]));
                assert!(option.iter().any(|(index, tool)| drawn[index] != *tool));
            }
            let each = tool_options(&drawn, "per_sentence", seed);
            assert_eq!(each.len(), count);
            for option in &each {
                assert!(option.iter().all(|(index, tool)| drawn[index] != *tool));
            }
        }
        assert_ne!(
            tool_options(&drawn, "per_sentence", 1),
            tool_options(&drawn, "per_sentence", 2),
            "another press offers other options"
        );
    }

    #[test]
    fn a_touch_change_is_planned_and_drawn_through_the_json_boundary() {
        let mut config = crate::focused_flow::config();
        config.language = ResolvedInstructionLanguage::Ja;
        let source = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。";
        let score = json!({"instructions": [
            {"weight": "brush_thin", "arrangement": {"resolved": {"owner": {"kind": "source_instruction", "instruction_index": 0}}}},
            {"arrangement": {"resolved": {"owner": {"kind": "source_instruction", "instruction_index": 1}}}},
        ]});
        let plan = ask(
            json!({"action": "tool_plan", "config": config, "source": source,
            "score": score, "mode": "uniform", "seed": 7}),
        );
        assert_eq!(plan["outcome"], "ok", "{plan}");
        assert_eq!(
            plan["sentences"],
            json!([{"index": 0, "tool": "brush_thin"}, {"index": 1, "tool": "pen"}])
        );
        assert_eq!(plan["entries"].as_array().unwrap().len(), 4);
        let drawn = ask(
            json!({"action": "tool_render", "config": config, "source": source,
            "score": score, "mode": "uniform", "tools": {"1": "chalk"}}),
        );
        assert_eq!(drawn["outcome"], "ok", "{drawn}");
        assert_eq!(
            drawn["ddl"],
            "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きなチョークの円を1個置く。"
        );
        assert_eq!(drawn["score"]["instructions"][1]["weight"], "chalk");
        assert_eq!(
            drawn["derivation_metadata"],
            json!({"tool_mode": "uniform", "tools": {"1": "chalk"},
            "changes": [{"index": 1, "from": "pen", "to": "chalk"}]})
        );
        let same = ask(
            json!({"action": "tool_render", "config": config, "source": source,
            "score": score, "mode": "uniform", "tools": {"1": "pen"}}),
        );
        assert_eq!(same["detail"], "tools must change at least one sentence");
        let negative = ask(
            json!({"action": "tool_render", "config": config, "source": source,
            "score": score, "mode": "uniform", "tools": {"-1": "chalk"}}),
        );
        assert_eq!(
            negative["detail"],
            "tools must name changeable sentences and known tools"
        );
    }

    #[test]
    fn a_touch_change_writes_the_laws_record_for_the_child_source() {
        let mut config = crate::focused_flow::config();
        config.language = ResolvedInstructionLanguage::Ja;
        let source = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。";
        let score = json!({"instructions": [
            {"weight": "brush_thin", "arrangement": {"resolved": {"owner": {"kind": "source_instruction", "instruction_index": 0}}}},
            {"arrangement": {"resolved": {"owner": {"kind": "source_instruction", "instruction_index": 1}}}},
        ]});
        // The second layer is no longer in the source (an author's edit): it stays as recorded.
        let record = json!({"schema": "inku.laws-layers.v1", "layers": [
            {"sentences": ["赤の大きな円を1個置く。"], "kind": "laws", "laws": ["B1"]},
            {"sentences": ["緑の点を1個置く。"], "kind": "partner"},
        ]});
        let drawn = ask(
            json!({"action": "tool_render", "config": config, "source": source, "score": score,
            "mode": "per_sentence", "tools": {"0": "chalk", "1": "oil_paint"}, "laws_layers": record}),
        );
        assert_eq!(drawn["outcome"], "ok", "{drawn}");
        assert_eq!(
            drawn["ddl"],
            "背景を白で埋める。\n青のチョークの線を3個引く。\n赤の大きな油彩の円を1個置く。"
        );
        assert_eq!(
            drawn["laws_layers"],
            json!({"schema": "inku.laws-layers.v1", "layers": [
                {"sentences": ["赤の大きな油彩の円を1個置く。"], "kind": "laws", "laws": ["B1"]},
                {"sentences": ["緑の点を1個置く。"], "kind": "partner"},
            ]})
        );
        // A tool changed only before the recorded sentence moves it without changing it.
        let before = ask(
            json!({"action": "tool_render", "config": config, "source": source, "score": score,
            "mode": "per_sentence", "tools": {"0": "chalk"}, "laws_layers": record}),
        );
        assert_eq!(before["laws_layers"], record, "{before}");
        // Without a record the answer is as before.
        let plain = ask(
            json!({"action": "tool_render", "config": config, "source": source, "score": score,
            "mode": "per_sentence", "tools": {"1": "oil_paint"}}),
        );
        assert!(plain.get("laws_layers").is_none(), "{plain}");
    }

    #[test]
    fn every_shared_ground_case_plans_and_redraws_as_server_does() {
        let table = cases();
        let rows = table["grounds"].as_array().unwrap();
        assert!(!rows.is_empty());
        for row in rows {
            let plan = ask(json!({"action": "ground_plan", "score": row["score"]}));
            assert_eq!(plan["current"], row["current"], "{}", row["why"]);
            let entries: Vec<&Value> = plan["entries"]
                .as_array()
                .unwrap()
                .iter()
                .map(|entry| &entry["material"])
                .collect();
            assert_eq!(json!(entries), row["entries"], "{}", row["why"]);
            for (material, expected) in row["score_with_ground"].as_object().unwrap() {
                assert_eq!(
                    &score_with_ground(&row["score"], material),
                    expected,
                    "{}",
                    row["why"]
                );
            }
        }
        let sentences = table["ground_sentences"].as_array().unwrap();
        assert!(!sentences.is_empty());
        for row in sentences {
            for (material, expected) in row["results"].as_object().unwrap() {
                let got = ddl_with_ground(
                    row["ddl"].as_str().unwrap(),
                    material,
                    row["language"].as_str(),
                );
                assert_eq!(json!(got), *expected, "{}", row["why"]);
            }
        }
    }

    #[test]
    fn every_shared_color_case_pages_and_recolors_as_server_does() {
        let table = cases();
        let rows = table["colors"].as_array().unwrap();
        assert!(!rows.is_empty());
        for row in rows {
            let base = json!({"svg": row["svg"], "color_map": row["color_map"], "work_id": row["work_id"]});
            for (cursor, expected) in row["pages"].as_object().unwrap() {
                let mut request = base.clone();
                request["action"] = json!("color_plan");
                request["cursor"] = json!(cursor.parse::<u64>().unwrap());
                let page = ask(request);
                assert_eq!(page["outcome"], "ok", "{page}");
                for key in ["entries", "next_cursor", "total"] {
                    assert_eq!(
                        page[key], expected[key],
                        "{} cursor {cursor} {key}",
                        row["why"]
                    );
                }
            }
            for (index, expected) in row["color_maps"].as_object().unwrap() {
                let mut request = base.clone();
                request["action"] = json!("color_render");
                request["index"] = json!(index.parse::<u64>().unwrap());
                request["catalog_id"] = json!("ink_season");
                let drawn = ask(request);
                assert_eq!(
                    drawn["color_map"], *expected,
                    "{} index {index}",
                    row["why"]
                );
                assert_eq!(
                    drawn["derivation_metadata"],
                    json!({"color_arrangement_index": index.parse::<u64>().unwrap(), "catalog_id": "ink_season"})
                );
            }
        }
        for row in table["color_refusals"].as_array().unwrap() {
            let refused = ask(
                json!({"action": "color_render", "svg": row["svg"], "color_map": row["color_map"],
                "work_id": row["work_id"], "index": row["index"], "catalog_id": "x"}),
            );
            assert_eq!(refused["outcome"], "refused", "{}", row["why"]);
            assert_eq!(refused["detail"], row["detail"], "{}", row["why"]);
        }
    }

    #[test]
    fn an_unreadable_request_is_refused_as_such() {
        assert_eq!(
            saved_variants_json(b"{}"),
            br#"{"error":"invalid_request"}"#
        );
        assert_eq!(
            ask(json!({"action": "ground_plan"}))["error"],
            "invalid_request"
        );
    }
}
