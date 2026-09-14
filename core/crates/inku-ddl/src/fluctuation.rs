//! Shared closed fluctuation vocabulary and source-to-Score resolution.

use inku_score::{Amplitude, Dimension, Frequency, Quality, Variation};
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FluctuationDimension {
    Amplitude,
    Frequency,
    Quality,
    Spread,
}

impl FluctuationDimension {
    pub fn from_field(field: &str) -> Option<Self> {
        match field {
            "fluctuation_amplitude" => Some(Self::Amplitude),
            "fluctuation_frequency" => Some(Self::Frequency),
            "fluctuation_quality" => Some(Self::Quality),
            "ink_spread" => Some(Self::Spread),
            _ => None,
        }
    }
}

#[derive(Clone, Copy)]
enum ResolvedValue {
    Amplitude(Amplitude),
    Frequency(Frequency),
    Quality(Quality),
    Spread(inku_score::InkSpread),
}

const WORDS: [(&str, ResolvedValue); 9] = [
    ("fine", ResolvedValue::Amplitude(Amplitude::Fine)),
    ("large", ResolvedValue::Amplitude(Amplitude::Broad)),
    ("slowly", ResolvedValue::Frequency(Frequency::Slow)),
    ("quickly", ResolvedValue::Frequency(Frequency::High)),
    ("swaying", ResolvedValue::Quality(Quality::Perlin)),
    // Saved MacroDefinitions retain their wire identity and lock digest. New
    // authoring and bundled definitions use `swaying` and `bleeding`.
    ("trembling", ResolvedValue::Quality(Quality::Perlin)),
    ("undulating", ResolvedValue::Quality(Quality::Wave)),
    ("blurring", ResolvedValue::Quality(Quality::Pink)),
    (
        "bleeding",
        ResolvedValue::Spread(inku_score::InkSpread::Bleed),
    ),
];

fn resolved_value(id: &str) -> Option<ResolvedValue> {
    WORDS
        .iter()
        .find(|(word, _)| *word == id)
        .map(|(_, value)| *value)
}

pub fn classify_fluctuation_dimension(id: &str) -> Option<FluctuationDimension> {
    resolved_value(id).map(|value| match value {
        ResolvedValue::Amplitude(_) => FluctuationDimension::Amplitude,
        ResolvedValue::Frequency(_) => FluctuationDimension::Frequency,
        ResolvedValue::Quality(_) => FluctuationDimension::Quality,
        ResolvedValue::Spread(_) => FluctuationDimension::Spread,
    })
}

pub(crate) fn matches_dimension(
    category: &str,
    id: &str,
    dimension: Option<FluctuationDimension>,
) -> bool {
    dimension.is_none_or(|dimension| {
        category == "variation" && classify_fluctuation_dimension(id) == Some(dimension)
    })
}

fn defaults() -> Variation {
    Variation {
        amplitude: Amplitude::Medium,
        frequency: Frequency::Medium,
        quality: Quality::Perlin,
        dimensions: vec![Dimension::PositionX, Dimension::PositionY],
    }
}

pub(crate) fn resolve_fluctuation(
    amplitude: Option<&str>,
    frequency: Option<&str>,
    quality: Option<&str>,
) -> Result<Option<Variation>, ()> {
    if amplitude.is_none() && frequency.is_none() && quality.is_none() {
        return Ok(None);
    }
    let mut variation = defaults();
    if let Some(id) = amplitude {
        let Some(ResolvedValue::Amplitude(value)) = resolved_value(id) else {
            return Err(());
        };
        variation.amplitude = value;
    }
    if let Some(id) = frequency {
        let Some(ResolvedValue::Frequency(value)) = resolved_value(id) else {
            return Err(());
        };
        variation.frequency = value;
    }
    if let Some(id) = quality {
        let Some(ResolvedValue::Quality(value)) = resolved_value(id) else {
            return Err(());
        };
        variation.quality = value;
    }
    Ok(Some(variation))
}

pub(crate) fn policy() -> serde_json::Value {
    let words: serde_json::Map<String, serde_json::Value> = WORDS.iter().map(|(id, value)| {
        let resolved = match value {
            ResolvedValue::Amplitude(value) => serde_json::to_value(value),
            ResolvedValue::Frequency(value) => serde_json::to_value(value),
            ResolvedValue::Quality(value) => serde_json::to_value(value),
            ResolvedValue::Spread(value) => serde_json::to_value(value),
        }.expect("closed Score enum serializes");
        ((*id).to_owned(), serde_json::json!({"dimension": classify_fluctuation_dimension(id), "value": resolved}))
    }).collect();
    serde_json::json!({"absent": "none", "partial": defaults(), "words": words})
}
