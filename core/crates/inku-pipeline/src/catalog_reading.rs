//! Description color reading and anonymous selection from resolved catalog colors.

use serde::{Deserialize, Serialize, ser::SerializeMap};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use crate::{
    catalog_reading_text,
    description_ddl::folded,
    image_ddl::{color_word, finish_image_prompt},
    machine::CatalogCandidate,
    prompts::{LlmPrompt, LlmStage, PromptError, PromptLimits},
    protocol::DecimalU64,
};
use inku_ddl::ResolvedInstructionLanguage as Language;
use inku_score::Color;

pub const READING_ID: &str = "inku.description-color-reading-prompt.v1";
pub const CHOICE_ID: &str = "inku.description-catalog-choice-prompt.v1";
const COLORS: [Color; 9] = [
    Color::White,
    Color::Black,
    Color::Gray,
    Color::Red,
    Color::Orange,
    Color::Yellow,
    Color::Green,
    Color::Blue,
    Color::Purple,
];

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Axis {
    pub value: String,
    pub quote: String,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ColorItem {
    pub word: String,
    pub lightness: String,
    pub vividness: String,
    pub quote: String,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ColorReading {
    pub note: String,
    pub brightness: Axis,
    pub vividness: Axis,
    pub warmth: Axis,
    pub colors: Vec<ColorItem>,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogReadingRecord {
    pub reading: ColorReading,
    pub dropped_axes: usize,
    pub dropped_colors: usize,
    pub reading_text: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub method: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub candidate_order: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selected_position: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub catalog_id: Option<String>,
}

impl ColorReading {
    pub fn empty(&self) -> bool {
        self.brightness.value == "none"
            && self.vividness.value == "none"
            && self.warmth.value == "none"
            && self.colors.is_empty()
    }
}

fn words(lang: Language) -> Vec<String> {
    COLORS
        .into_iter()
        .map(|color| color_word(color, lang))
        .collect()
}
fn axis_schema(values: &[&str]) -> Value {
    json!({"type":"object","additionalProperties":false,"required":["value","quote"],"properties":{"value":{"type":"string","enum":values},"quote":{"type":"string"}}})
}
pub fn reading_schema(lang: Language) -> Value {
    json!({"type":"object","additionalProperties":false,"required":["note","brightness","vividness","warmth","colors"],"properties":{
        "note":{"type":"string"}, "brightness":axis_schema(&["bright","middle","dark","none"]),
        "vividness":axis_schema(&["vivid","muted","none"]), "warmth":axis_schema(&["warm","cool","none"]),
        "colors":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["word","lightness","vividness","quote"],"properties":{
            "word":{"type":"string","enum":words(lang)},"lightness":{"type":"string","enum":["light","deep","none"]},"vividness":{"type":"string","enum":["vivid","muted","none"]},"quote":{"type":"string"}}}}}})
}

pub fn reading_prompt(
    description: &str,
    lang: Language,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    crate::prompts::require_nonempty("description", description)?;
    crate::prompts::require_within("description", description.len(), limits.max_source_bytes)?;
    let message = serde_json::to_string(&json!({"description":description}))
        .map_err(|_| PromptError::Serialization)?;
    let system = match lang {
        Language::Ja => catalog_reading_text::READING_JA,
        Language::En => catalog_reading_text::READING_EN,
    };
    finish_image_prompt(
        READING_ID,
        LlmStage::SelectDescriptionCatalog,
        lang,
        system.into(),
        message,
        reading_schema(lang),
        vec![],
    )
}

pub fn parse_reading(
    response: &str,
    description: &str,
    lang: Language,
    limits: PromptLimits,
) -> Result<CatalogReadingRecord, PromptError> {
    if response.len() > limits.max_response_bytes {
        return Err(PromptError::Serialization);
    }
    let mut reading: ColorReading =
        serde_json::from_str(response).map_err(|_| PromptError::Serialization)?;
    let valid = |value: &str, allowed: &[&str]| allowed.contains(&value);
    if !valid(
        &reading.brightness.value,
        &["bright", "middle", "dark", "none"],
    ) || !valid(&reading.vividness.value, &["vivid", "muted", "none"])
        || !valid(&reading.warmth.value, &["warm", "cool", "none"])
        || reading.colors.iter().any(|item| {
            !words(lang).contains(&item.word)
                || !valid(&item.lightness, &["light", "deep", "none"])
                || !valid(&item.vividness, &["vivid", "muted", "none"])
        })
    {
        return Err(PromptError::Serialization);
    }
    let source = folded(description);
    let anchored = |quote: &str| {
        let q = folded(quote);
        !q.is_empty() && source.contains(&q)
    };
    let mut dropped_axes = 0;
    for axis in [
        &mut reading.brightness,
        &mut reading.vividness,
        &mut reading.warmth,
    ] {
        if axis.value == "none" {
            axis.quote.clear();
        } else if !anchored(&axis.quote) {
            axis.value = "none".into();
            axis.quote.clear();
            dropped_axes += 1;
        }
    }
    let before = reading.colors.len();
    reading.colors.retain(|item| anchored(&item.quote));
    reading.colors.truncate(6);
    let dropped_colors = before - reading.colors.len();
    let reading_text = display_reading(&reading, lang);
    Ok(CatalogReadingRecord {
        reading,
        dropped_axes,
        dropped_colors,
        reading_text,
        method: None,
        candidate_order: vec![],
        selected_position: None,
        catalog_id: None,
    })
}

fn translate(value: &str) -> &str {
    match value {
        "bright" => "明るい",
        "middle" => "中ほど",
        "dark" => "暗い",
        "vivid" => "鮮やか",
        "muted" => "くすんだ",
        "warm" => "暖かい",
        "cool" => "冷たい",
        "light" => "淡い",
        "deep" => "深い",
        _ => value,
    }
}
pub fn display_reading(reading: &ColorReading, lang: Language) -> String {
    let ja = lang == Language::Ja;
    if reading.empty() {
        return if ja {
            "光と色: 記述から読めるものが無い"
        } else {
            "Light and color: nothing could be read from the description"
        }
        .into();
    }
    let mut lines = vec![format!(
        "{}: {}",
        if ja { "光と色" } else { "Light and color" },
        reading.note
    )];
    for (name, axis) in [
        (
            if ja { "明るさ" } else { "brightness" },
            &reading.brightness,
        ),
        (if ja { "冴え" } else { "vividness" }, &reading.vividness),
        (if ja { "温度" } else { "warmth" }, &reading.warmth),
    ] {
        if axis.value != "none" {
            lines.push(if ja {
                format!(
                    "- {name}: {}（「{}」から）",
                    translate(&axis.value),
                    axis.quote
                )
            } else {
                format!("- {name}: {} (from \"{}\")", axis.value, axis.quote)
            });
        }
    }
    for item in &reading.colors {
        let mut props = vec![item.word.as_str()];
        if item.lightness != "none" {
            props.push(if ja {
                translate(&item.lightness)
            } else {
                &item.lightness
            });
        }
        if item.vividness != "none" {
            props.push(if ja {
                translate(&item.vividness)
            } else {
                &item.vividness
            });
        }
        lines.push(if ja {
            format!("- 色: {}（「{}」から）", props.join("、"), item.quote)
        } else {
            format!("- color: {} (from \"{}\")", props.join(", "), item.quote)
        });
    }
    lines.join("\n")
}

fn hash_key(domain: &str, material: &str, id: &str) -> [u8; 32] {
    let mut hash = Sha256::new();
    hash.update(domain.as_bytes());
    hash.update([0]);
    hash.update(material.as_bytes());
    hash.update([0]);
    hash.update(id.as_bytes());
    hash.finalize().into()
}
pub fn ordered_ids(candidates: &[CatalogCandidate], material: &str, domain: &str) -> Vec<String> {
    let mut ids: Vec<_> = candidates
        .iter()
        .map(|candidate| candidate.prompt.catalog_id.clone())
        .collect();
    ids.sort_by_key(|id| (hash_key(domain, material, id), id.clone()));
    ids
}
pub fn seed_choice(candidates: &[CatalogCandidate], seed: DecimalU64) -> Option<String> {
    ordered_ids(
        candidates,
        &seed.get().to_string(),
        "inku.catalog-seed-choice.v1",
    )
    .into_iter()
    .next()
}

#[derive(Serialize)]
struct ChoiceMessage<'a> {
    description: &'a str,
    reading: &'a ColorReading,
    candidates: Vec<ChoiceCandidate>,
}
#[derive(Serialize)]
struct ChoiceCandidate {
    id: String,
    colors: OrderedColors,
}
#[derive(Serialize)]
struct CandidateEnvelope<'a> {
    candidates: &'a [ChoiceCandidate],
}
struct OrderedColors(Vec<(String, String)>);
impl Serialize for OrderedColors {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(Some(self.0.len()))?;
        for (key, value) in &self.0 {
            map.serialize_entry(key, value)?;
        }
        map.end()
    }
}

pub fn choice_prompt(
    description: &str,
    record: &CatalogReadingRecord,
    candidates: &[CatalogCandidate],
    seed: Option<DecimalU64>,
    lang: Language,
    limits: PromptLimits,
) -> Result<(LlmPrompt, Vec<String>), PromptError> {
    if candidates.is_empty() {
        return Err(PromptError::EmptyField {
            field: "catalog_candidates",
        });
    }
    crate::prompts::require_within(
        "catalog_entries",
        candidates.len(),
        limits.max_catalog_entries,
    )?;
    let material = seed.map(|s| s.get().to_string()).unwrap_or_else(|| {
        Sha256::digest(description.as_bytes())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    });
    let ids = ordered_ids(candidates, &material, "inku.catalog-choice-order.v1");
    let mut anonymous = Vec::new();
    for (index, id) in ids.iter().enumerate() {
        let candidate = candidates
            .iter()
            .find(|item| item.prompt.catalog_id == *id)
            .ok_or(PromptError::Serialization)?;
        let mut colors = Vec::new();
        for color in COLORS {
            let rgb = candidate
                .resolved
                .palette()
                .observations
                .iter()
                .flatten()
                .find(|observation| observation.abstract_color == color)
                .ok_or(PromptError::Serialization)?
                .concrete_rgb;
            colors.push((
                color_word(color, lang),
                format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2]),
            ));
        }
        anonymous.push(ChoiceCandidate {
            id: format!("k{:02}", index + 1),
            colors: OrderedColors(colors),
        });
    }
    let serialized = serde_json::to_vec(&CandidateEnvelope {
        candidates: &anonymous,
    })
    .map_err(|_| PromptError::Serialization)?;
    crate::prompts::require_within(
        "catalog_serialized_bytes",
        serialized.len(),
        limits.max_catalog_serialized_bytes,
    )?;
    let anonymous_ids: Vec<_> = anonymous
        .iter()
        .map(|candidate| candidate.id.clone())
        .collect();
    let message = serde_json::to_string(&ChoiceMessage {
        description,
        reading: &record.reading,
        candidates: anonymous,
    })
    .map_err(|_| PromptError::Serialization)?;
    let schema = json!({"type":"object","additionalProperties":false,"required":["catalog_id"],"properties":{"catalog_id":{"type":"string","enum":anonymous_ids}}});
    let system = match lang {
        Language::Ja => catalog_reading_text::CHOICE_JA,
        Language::En => catalog_reading_text::CHOICE_EN,
    };
    Ok((
        finish_image_prompt(
            CHOICE_ID,
            LlmStage::SelectDescriptionCatalog,
            lang,
            system.into(),
            message,
            schema,
            vec![],
        )?,
        ids,
    ))
}
