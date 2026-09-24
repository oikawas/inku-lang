//! Structured Stage 1 work plan.
//!
//! A work plan is a flat list of standalone drawing sentences typed as closed
//! values. It is not a second meaning model: every accepted plan prints to
//! visible DDL in the existing grammar, and that DDL remains the only authority.
//! Every value is projected from the Saijiki asset, the parser's finite
//! modifier forms, the fluctuation classifier, or the Score schema, and the
//! per-form capability matrix is generated from the compiler itself. Values a
//! provider returns outside that projection become unspecified with a
//! diagnostic, so a readable plan never stops a drawing.

use std::collections::BTreeMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::ResolvedInstructionLanguage;
use crate::fluctuation::{FluctuationDimension, classify_fluctuation_dimension};
use crate::grammar_markers::MarkerId;
use crate::macro_definition::project_macro_semantic_ref;
use crate::parser::{CoreModifierValue, core_modifier_surface_forms};
use crate::saijiki::saijiki_asset;

pub const WORK_PLAN_SCHEMA_ID: &str = "inku.work-plan.v1";
pub const WORK_PLAN_CAPABILITIES_ASSET_ID: &str = "inku.work-plan-capabilities.v1";
pub const WORK_PLAN_CAPABILITIES_ASSET_BYTES: &[u8] =
    include_bytes!("../assets/work-plan-capabilities-v1.json");
pub const UNSPECIFIED: &str = "unspecified";
pub const MAX_WORK_PLAN_LAYERS: usize = 8;
pub const MAX_WORK_PLAN_COUNT: u32 = 60;

/// One closed plan slot. Slot names are the plan's JSON field names.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkPlanSlot {
    Shape,
    Proportion,
    Action,
    Place,
    Size,
    Color,
    Tool,
    Thinness,
    Continuity,
    Surface,
    SurfaceIntensity,
    Angle,
    LineUpDirection,
    MotionQuality,
    MotionAmplitude,
    MotionSpeed,
    Bleeding,
    Ground,
}

impl WorkPlanSlot {
    pub const LAYER_ATTRIBUTES: [Self; 15] = [
        Self::Place,
        Self::Size,
        Self::Color,
        Self::Tool,
        Self::Thinness,
        Self::Continuity,
        Self::Surface,
        Self::SurfaceIntensity,
        Self::Angle,
        Self::LineUpDirection,
        Self::MotionQuality,
        Self::MotionAmplitude,
        Self::MotionSpeed,
        Self::Bleeding,
        Self::Action,
    ];

    #[must_use]
    pub const fn field(self) -> &'static str {
        match self {
            Self::Shape => "shape",
            Self::Proportion => "proportion",
            Self::Action => "action",
            Self::Place => "place",
            Self::Size => "size",
            Self::Color => "color",
            Self::Tool => "tool",
            Self::Thinness => "thinness",
            Self::Continuity => "continuity",
            Self::Surface => "surface",
            Self::SurfaceIntensity => "surface_intensity",
            Self::Angle => "angle",
            Self::LineUpDirection => "line_up_direction",
            Self::MotionQuality => "motion_quality",
            Self::MotionAmplitude => "motion_amplitude",
            Self::MotionSpeed => "motion_speed",
            Self::Bleeding => "bleeding",
            Self::Ground => "ground",
        }
    }
}

/// One closed value with its visible surfaces.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkPlanTerm {
    pub id: String,
    pub ja: String,
    pub en: String,
}

/// The finite vocabulary a work plan may use, projected once from shared owners.
#[derive(Clone, Debug, Default)]
pub struct WorkPlanVocabulary {
    terms: BTreeMap<WorkPlanSlot, Vec<WorkPlanTerm>>,
}

impl WorkPlanVocabulary {
    #[must_use]
    pub fn terms(&self, slot: WorkPlanSlot) -> &[WorkPlanTerm] {
        self.terms.get(&slot).map_or(&[], Vec::as_slice)
    }

    #[must_use]
    pub fn term(&self, slot: WorkPlanSlot, id: &str) -> Option<&WorkPlanTerm> {
        self.terms(slot).iter().find(|term| term.id == id)
    }

    fn push(&mut self, slot: WorkPlanSlot, term: WorkPlanTerm) {
        self.terms.entry(slot).or_default().push(term);
    }
}

fn saijiki_terms(category_key: &str) -> Vec<WorkPlanTerm> {
    let Some(category) = saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == category_key)
    else {
        return Vec::new();
    };
    category
        .words
        .iter()
        .filter(|word| word.prompt)
        .filter_map(|word| {
            let id = project_macro_semantic_ref(category_key, &word.surface_ja)?.canonical_id;
            Some(WorkPlanTerm {
                id,
                ja: word.surface_ja.clone(),
                en: word.surface_en.clone()?,
            })
        })
        .collect()
}

fn core_terms(dimension: fn(CoreModifierValue) -> bool) -> Vec<WorkPlanTerm> {
    let ja = core_modifier_surface_forms(ResolvedInstructionLanguage::Ja);
    let en = core_modifier_surface_forms(ResolvedInstructionLanguage::En);
    let first = |forms: &[(&'static str, CoreModifierValue)], value: CoreModifierValue| {
        forms
            .iter()
            .find(|(_, candidate)| *candidate == value)
            .map(|(surface, _)| (*surface).to_owned())
    };
    let mut out: Vec<WorkPlanTerm> = Vec::new();
    for (_, value) in ja.thinness.iter().chain(ja.relative_scale) {
        let value = *value;
        if !dimension(value) || out.iter().any(|term| term.id == value.as_str()) {
            continue;
        }
        let forms_ja = if matches!(
            value,
            CoreModifierValue::Fine | CoreModifierValue::ExtraFine
        ) {
            ja.thinness
        } else {
            ja.relative_scale
        };
        let forms_en = if matches!(
            value,
            CoreModifierValue::Fine | CoreModifierValue::ExtraFine
        ) {
            en.thinness
        } else {
            en.relative_scale
        };
        if let (Some(ja), Some(en)) = (first(forms_ja, value), first(forms_en, value)) {
            out.push(WorkPlanTerm {
                id: value.as_str().to_owned(),
                ja,
                en,
            });
        }
    }
    out
}

/// Project the closed plan vocabulary from the Saijiki asset and parser owners.
#[must_use]
pub fn work_plan_vocabulary() -> &'static WorkPlanVocabulary {
    static VOCABULARY: OnceLock<WorkPlanVocabulary> = OnceLock::new();
    VOCABULARY.get_or_init(|| {
        let mut vocabulary = WorkPlanVocabulary::default();
        for (slot, key) in [
            (WorkPlanSlot::Shape, "katachi"),
            (WorkPlanSlot::Proportion, "wariai"),
            (WorkPlanSlot::Action, "ugoki"),
            (WorkPlanSlot::Place, "basho"),
            (WorkPlanSlot::Color, "iro"),
            (WorkPlanSlot::Tool, "tezawari"),
            (WorkPlanSlot::Continuity, "tsuranari"),
            (WorkPlanSlot::Angle, "katamuki"),
            (WorkPlanSlot::LineUpDirection, "katamuki"),
            (WorkPlanSlot::Ground, "ji"),
        ] {
            for term in saijiki_terms(key) {
                vocabulary.push(slot, term);
            }
        }
        let intensity_ids = [
            inku_score::SurfaceIntensity::Dense,
            inku_score::SurfaceIntensity::Faint,
        ]
        .map(|value| serde_json::to_value(value).unwrap_or_default());
        for term in saijiki_terms("omote") {
            let slot = if intensity_ids.iter().any(|id| id == term.id.as_str()) {
                WorkPlanSlot::SurfaceIntensity
            } else {
                WorkPlanSlot::Surface
            };
            vocabulary.push(slot, term);
        }
        for term in saijiki_terms("yuragi") {
            let slot = match classify_fluctuation_dimension(&term.id) {
                Some(FluctuationDimension::Amplitude) => WorkPlanSlot::MotionAmplitude,
                Some(FluctuationDimension::Frequency) => WorkPlanSlot::MotionSpeed,
                Some(FluctuationDimension::Quality) => WorkPlanSlot::MotionQuality,
                Some(FluctuationDimension::Spread) => WorkPlanSlot::Bleeding,
                None => continue,
            };
            vocabulary.push(slot, term);
        }
        for term in core_terms(|value| {
            matches!(
                value,
                CoreModifierValue::Fine | CoreModifierValue::ExtraFine
            )
        }) {
            vocabulary.push(WorkPlanSlot::Thinness, term);
        }
        for term in core_terms(|value| {
            !matches!(
                value,
                CoreModifierValue::Fine
                    | CoreModifierValue::ExtraFine
                    | CoreModifierValue::Regular
                    | CoreModifierValue::Sides(_)
            )
        }) {
            vocabulary.push(WorkPlanSlot::Size, term);
        }
        vocabulary
    })
}

/// Accepted values per form (`shape` or `shape/proportion`) and slot.
#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct WorkPlanCapabilities {
    pub asset_id: String,
    pub forms: BTreeMap<String, BTreeMap<WorkPlanSlot, Vec<String>>>,
}

impl WorkPlanCapabilities {
    #[must_use]
    pub fn accepts(&self, form: &str, slot: WorkPlanSlot, id: &str) -> bool {
        self.forms
            .get(form)
            .and_then(|slots| slots.get(&slot))
            .is_some_and(|values| values.iter().any(|value| value == id))
    }
}

/// The embedded capability matrix generated by `examples/work-plan-capabilities.rs`.
#[must_use]
pub fn work_plan_capabilities() -> &'static WorkPlanCapabilities {
    static CAPABILITIES: OnceLock<WorkPlanCapabilities> = OnceLock::new();
    CAPABILITIES.get_or_init(|| {
        serde_json::from_slice(WORK_PLAN_CAPABILITIES_ASSET_BYTES)
            .expect("embedded work plan capability asset must remain valid JSON")
    })
}

/// One drawing layer: a single standalone DDL sentence.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub struct WorkPlanLayer {
    pub shape: String,
    pub proportion: Option<String>,
    pub action: String,
    pub count: u32,
    /// Accepted optional attributes keyed by slot.
    pub attributes: BTreeMap<WorkPlanSlot, String>,
}

impl WorkPlanLayer {
    #[must_use]
    pub fn form(&self) -> String {
        match &self.proportion {
            Some(proportion) => format!("{}/{proportion}", self.shape),
            None => self.shape.clone(),
        }
    }

    fn attribute(&self, slot: WorkPlanSlot) -> Option<&str> {
        self.attributes.get(&slot).map(String::as_str)
    }
}

/// A normalized plan. Background and ground are optional document sentences.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub struct WorkPlan {
    pub ground: Option<String>,
    pub background: Option<String>,
    pub layers: Vec<WorkPlanLayer>,
}

/// A provider value that normalization replaced by unspecified or dropped.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct WorkPlanDiagnostic {
    pub layer: Option<usize>,
    pub field: String,
    pub value: String,
    pub reason: &'static str,
}

fn enum_schema(values: impl IntoIterator<Item = String>) -> Value {
    let mut all = vec![UNSPECIFIED.to_owned()];
    all.extend(values);
    json!({"type": "string", "enum": all})
}

fn ids(slot: WorkPlanSlot) -> Vec<String> {
    work_plan_vocabulary()
        .terms(slot)
        .iter()
        .map(|term| term.id.clone())
        .collect()
}

/// The provider response schema. It uses only object, array, string enum, and
/// integer so every structured-output transport can carry it unchanged.
#[must_use]
pub fn work_plan_response_schema() -> Value {
    let mut layer = Map::new();
    let capabilities = work_plan_capabilities();
    let shapes: Vec<String> = ids(WorkPlanSlot::Shape)
        .into_iter()
        .filter(|shape| capabilities.forms.contains_key(shape))
        .collect();
    layer.insert("shape".into(), json!({"type": "string", "enum": shapes}));
    layer.insert(
        "proportion".into(),
        enum_schema(ids(WorkPlanSlot::Proportion)),
    );
    layer.insert(
        "action".into(),
        json!({"type": "string", "enum": ids(WorkPlanSlot::Action)}),
    );
    layer.insert(
        "count".into(),
        json!({"type": "integer", "minimum": 1, "maximum": MAX_WORK_PLAN_COUNT}),
    );
    for slot in WorkPlanSlot::LAYER_ATTRIBUTES {
        if slot == WorkPlanSlot::Action {
            continue;
        }
        layer.insert(slot.field().into(), enum_schema(ids(slot)));
    }
    json!({
        "type": "object",
        "properties": {
            "background": enum_schema(ids(WorkPlanSlot::Color)),
            "ground": enum_schema(ids(WorkPlanSlot::Ground)),
            "layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": layer,
                    "required": [
                        "shape", "proportion", "action", "count", "place", "size",
                        "color", "tool", "surface", "motion_quality"
                    ]
                }
            }
        },
        "required": ["background", "ground", "layers"]
    })
}

fn text(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::String(text) if text != UNSPECIFIED && !text.is_empty() => Some(text.clone()),
        Value::Null => None,
        Value::String(_) => None,
        other => Some(other.to_string()),
    }
}

/// Normalize a provider plan. Values outside the projected vocabulary or the
/// form's accepted set become unspecified; a layer without a known shape is
/// dropped. Every change is reported, and nothing here can stop a drawing.
#[must_use]
pub fn normalize_work_plan(raw: &Value) -> (WorkPlan, Vec<WorkPlanDiagnostic>) {
    let vocabulary = work_plan_vocabulary();
    let capabilities = work_plan_capabilities();
    let mut diagnostics = Vec::new();
    let mut note = |layer: Option<usize>, field: &str, value: String, reason: &'static str| {
        diagnostics.push(WorkPlanDiagnostic {
            layer,
            field: field.to_owned(),
            value,
            reason,
        });
    };
    let mut plan = WorkPlan::default();
    for (field, slot) in [
        ("ground", WorkPlanSlot::Ground),
        ("background", WorkPlanSlot::Color),
    ] {
        if let Some(value) = text(raw.get(field)) {
            if vocabulary.term(slot, &value).is_some() {
                if field == "ground" {
                    plan.ground = Some(value);
                } else {
                    plan.background = Some(value);
                }
            } else {
                note(None, field, value, "unknown_value");
            }
        }
    }
    let layers = raw
        .get("layers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for (index, layer) in layers.iter().enumerate() {
        if plan.layers.len() >= MAX_WORK_PLAN_LAYERS {
            note(Some(index), "layers", String::new(), "over_layer_limit");
            continue;
        }
        let Some(shape) =
            text(layer.get("shape")).filter(|shape| capabilities.forms.contains_key(shape))
        else {
            note(
                Some(index),
                "shape",
                text(layer.get("shape")).unwrap_or_default(),
                "layer_without_known_shape",
            );
            continue;
        };
        let mut proportion = text(layer.get("proportion"));
        if let Some(value) = &proportion
            && !capabilities.forms.contains_key(&format!("{shape}/{value}"))
        {
            note(
                Some(index),
                "proportion",
                value.clone(),
                "unsupported_for_form",
            );
            proportion = None;
        }
        let form = proportion
            .as_ref()
            .map_or_else(|| shape.clone(), |value| format!("{shape}/{value}"));
        let mut out = WorkPlanLayer {
            shape,
            proportion,
            ..WorkPlanLayer::default()
        };
        out.action = match text(layer.get("action")) {
            Some(action) if capabilities.accepts(&form, WorkPlanSlot::Action, &action) => action,
            other => {
                let fallback = ["place", "draw"]
                    .into_iter()
                    .find(|action| capabilities.accepts(&form, WorkPlanSlot::Action, action))
                    .unwrap_or("place")
                    .to_owned();
                note(
                    Some(index),
                    "action",
                    other.unwrap_or_default(),
                    "unsupported_for_form",
                );
                fallback
            }
        };
        out.count = match layer.get("count").and_then(Value::as_u64) {
            Some(count) if count >= 1 => {
                let clamped = count.min(u64::from(MAX_WORK_PLAN_COUNT));
                if clamped != count {
                    note(Some(index), "count", count.to_string(), "over_count_limit");
                }
                u32::try_from(clamped).unwrap_or(MAX_WORK_PLAN_COUNT)
            }
            _ => {
                note(
                    Some(index),
                    "count",
                    text(layer.get("count")).unwrap_or_default(),
                    "invalid_count",
                );
                1
            }
        };
        for slot in WorkPlanSlot::LAYER_ATTRIBUTES {
            if slot == WorkPlanSlot::Action {
                continue;
            }
            let Some(value) = text(layer.get(slot.field())) else {
                continue;
            };
            if slot == WorkPlanSlot::MotionQuality && value == "still" {
                continue;
            }
            if vocabulary.term(slot, &value).is_none() {
                note(Some(index), slot.field(), value, "unknown_value");
            } else if capabilities.forms[&form].contains_key(&slot)
                && !capabilities.accepts(&form, slot, &value)
            {
                note(Some(index), slot.field(), value, "unsupported_for_form");
            } else {
                out.attributes.insert(slot, value);
            }
        }
        if out.attribute(WorkPlanSlot::SurfaceIntensity).is_some()
            && out.attribute(WorkPlanSlot::Surface) != Some("solid")
        {
            let value = out
                .attributes
                .remove(&WorkPlanSlot::SurfaceIntensity)
                .unwrap_or_default();
            note(
                Some(index),
                "surface_intensity",
                value,
                "requires_flat_surface",
            );
        }
        if out.action != "line_up"
            && let Some(value) = out.attributes.remove(&WorkPlanSlot::LineUpDirection)
        {
            note(Some(index), "line_up_direction", value, "requires_line_up");
        }
        if out.attribute(WorkPlanSlot::MotionQuality).is_none() {
            for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpeed] {
                if let Some(value) = out.attributes.remove(&slot) {
                    note(Some(index), slot.field(), value, "requires_motion_quality");
                }
            }
        }
        plan.layers.push(out);
    }
    (plan, diagnostics)
}

fn surface(slot: WorkPlanSlot, id: &str, language: ResolvedInstructionLanguage) -> String {
    work_plan_vocabulary()
        .term(slot, id)
        .map_or_else(String::new, |term| match language {
            ResolvedInstructionLanguage::Ja => term.ja.clone(),
            ResolvedInstructionLanguage::En => term.en.clone(),
        })
}

fn ja_modifier(surface: &str) -> String {
    // Adjectival core forms attach directly; noun forms take の.
    if surface.ends_with('な') || surface.ends_with('い') {
        surface.to_owned()
    } else {
        format!("{surface}{}", MarkerId::JaNo.surface())
    }
}

fn print_layer_ja(layer: &WorkPlanLayer) -> String {
    let ja = ResolvedInstructionLanguage::Ja;
    let no = MarkerId::JaNo.surface();
    let mut out = String::new();
    if let Some(place) = layer.attribute(WorkPlanSlot::Place) {
        out.push_str(&surface(WorkPlanSlot::Place, place, ja));
        out.push_str(MarkerId::JaNi.surface());
        out.push('、');
    }
    if let Some(quality) = layer.attribute(WorkPlanSlot::MotionQuality) {
        for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpeed] {
            if let Some(value) = layer.attribute(slot) {
                out.push_str(&surface(slot, value, ja));
            }
        }
        out.push_str(&surface(WorkPlanSlot::MotionQuality, quality, ja));
    }
    if let Some(bleeding) = layer.attribute(WorkPlanSlot::Bleeding) {
        out.push_str(&surface(WorkPlanSlot::Bleeding, bleeding, ja));
        out.push_str(no);
    }
    for slot in [
        WorkPlanSlot::Color,
        WorkPlanSlot::Thinness,
        WorkPlanSlot::Tool,
        WorkPlanSlot::Continuity,
        WorkPlanSlot::Surface,
        WorkPlanSlot::SurfaceIntensity,
        WorkPlanSlot::Angle,
    ] {
        if let Some(value) = layer.attribute(slot) {
            out.push_str(&ja_modifier(&surface(slot, value, ja)));
        }
    }
    if let Some(proportion) = &layer.proportion {
        out.push_str(&surface(WorkPlanSlot::Proportion, proportion, ja));
        out.push_str(no);
    }
    if let Some(size) = layer.attribute(WorkPlanSlot::Size) {
        out.push_str(&ja_modifier(&surface(WorkPlanSlot::Size, size, ja)));
    }
    out.push_str(&surface(WorkPlanSlot::Shape, &layer.shape, ja));
    out.push_str(MarkerId::JaWo.surface());
    if let Some(direction) = layer.attribute(WorkPlanSlot::LineUpDirection) {
        out.push_str(&surface(WorkPlanSlot::LineUpDirection, direction, ja));
        out.push_str(MarkerId::JaNi.surface());
    }
    out.push_str(&format!("{}個", layer.count));
    out.push_str(&surface(WorkPlanSlot::Action, &layer.action, ja));
    out.push('。');
    out
}

fn print_layer_en(layer: &WorkPlanLayer) -> String {
    let en = ResolvedInstructionLanguage::En;
    let mut words: Vec<String> = Vec::new();
    if let Some(quality) = layer.attribute(WorkPlanSlot::MotionQuality) {
        for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpeed] {
            if let Some(value) = layer.attribute(slot) {
                let base = surface(slot, value, en);
                // Amplitude is written as its adverb so it never reads as a size.
                words.push(if slot == WorkPlanSlot::MotionAmplitude {
                    format!("{base}ly")
                } else {
                    base
                });
            }
        }
        words.push(surface(WorkPlanSlot::MotionQuality, quality, en));
    }
    if let Some(bleeding) = layer.attribute(WorkPlanSlot::Bleeding) {
        words.push(surface(WorkPlanSlot::Bleeding, bleeding, en));
    }
    for slot in [
        WorkPlanSlot::Color,
        WorkPlanSlot::Thinness,
        WorkPlanSlot::Tool,
        WorkPlanSlot::Continuity,
        WorkPlanSlot::Surface,
        WorkPlanSlot::SurfaceIntensity,
        WorkPlanSlot::Angle,
    ] {
        if let Some(value) = layer.attribute(slot) {
            words.push(surface(slot, value, en));
        }
    }
    if let Some(proportion) = &layer.proportion {
        words.push(surface(WorkPlanSlot::Proportion, proportion, en));
    }
    if let Some(size) = layer.attribute(WorkPlanSlot::Size) {
        words.push(surface(WorkPlanSlot::Size, size, en));
    }
    let head = surface(WorkPlanSlot::Shape, &layer.shape, en);
    words.push(if layer.count > 1 {
        format!("{head}s")
    } else {
        head
    });
    let action = surface(WorkPlanSlot::Action, &layer.action, en);
    let mut action = action.replace('-', " ");
    if let Some(first) = action.get_mut(0..1) {
        first.make_ascii_uppercase();
    }
    let count = if layer.count > 1 {
        layer.count.to_string()
    } else {
        "one".to_owned()
    };
    let mut out = format!("{action} {count} {}", words.join(" "));
    if let Some(direction) = layer.attribute(WorkPlanSlot::LineUpDirection) {
        // Line-up direction is the direction word's adverb form.
        out.push_str(&format!(
            " {}ly",
            surface(WorkPlanSlot::LineUpDirection, direction, en)
        ));
    }
    if let Some(place) = layer.attribute(WorkPlanSlot::Place) {
        out.push_str(&format!(
            " at the {}",
            surface(WorkPlanSlot::Place, place, en)
        ));
    }
    out.push('.');
    out
}

/// Print a normalized plan as visible DDL in the requested language.
#[must_use]
pub fn print_work_plan(plan: &WorkPlan, language: ResolvedInstructionLanguage) -> String {
    let mut lines = Vec::new();
    if let Some(ground) = &plan.ground {
        let text = surface(WorkPlanSlot::Ground, ground, language);
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => format!("{text}。"),
            ResolvedInstructionLanguage::En => {
                let mut text = text;
                if let Some(first) = text.get_mut(0..1) {
                    first.make_ascii_uppercase();
                }
                format!("{text}.")
            }
        });
    }
    if let Some(background) = &plan.background {
        let color = surface(WorkPlanSlot::Color, background, language);
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => format!("背景を{color}で埋める。"),
            ResolvedInstructionLanguage::En => format!("Fill the background with {color}."),
        });
    }
    for layer in &plan.layers {
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => print_layer_ja(layer),
            ResolvedInstructionLanguage::En => print_layer_en(layer),
        });
    }
    lines.join("\n")
}

fn fixed_palette() -> inku_score::ResolvedPaletteContext {
    use inku_score::{Color, ResolvedPaletteColor};
    let observe = |color: Color, rgb: [u8; 3], lightness: f64| {
        ResolvedPaletteColor::new(color, rgb, lightness)
    };
    let observations = [
        observe(Color::White, [255, 255, 251], 0.99),
        observe(Color::Black, [20, 18, 16], 0.20),
        observe(Color::Blue, [22, 94, 131], 0.45),
        observe(Color::Red, [211, 56, 28], 0.58),
        observe(Color::Green, [0, 123, 67], 0.50),
        observe(Color::Gray, [89, 88, 87], 0.47),
        observe(Color::Yellow, [132, 122, 46], 0.57),
        observe(Color::Orange, [255, 182, 30], 0.82),
        observe(Color::Purple, [165, 145, 197], 0.68),
    ];
    inku_score::ResolvedPaletteContext::new(observations[0], observations[1], observations[0])
        .with_observations(observations)
}

/// Whether one printed DDL source compiles to a Score with no diagnostic
/// through the shared resource-aware compiler and the installation budget.
#[must_use]
pub fn work_plan_source_compiles_cleanly(
    source: &str,
    language: ResolvedInstructionLanguage,
) -> bool {
    use crate::{
        MacroExpansionLimits, NormalizedDdlDocument, ScoreErrorPolicy, ScoreLoweringContext,
        ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
    };
    let Ok(document) = NormalizedDdlDocument::new(source.to_owned(), language, Vec::new()) else {
        return false;
    };
    let Ok(context) = ScoreLoweringContext::resolve_with_palette(
        "square",
        inku_score::Color::White,
        fixed_palette(),
    ) else {
        return false;
    };
    let budget = json!({"maximum": {
        "logical_objects": 4096, "template_nodes": 128, "anchor_instances": 4096,
        "transform_instances": 4096, "placement_instances": 64, "fill_instances": 64,
        "primitive_marks": 400, "maximum_per_template_primitive_marks": 240,
        "maximum_resolved_count": 2000, "object_templates": 64
    }});
    let hard =
        serde_json::from_value(json!({"identity": "work-plan-capabilities", "budget": budget}))
            .expect("fixed hard policy");
    let operational = serde_json::from_value(budget).expect("fixed operational budget");
    let result = compile_ddl_to_score_with_resources(
        document,
        &[],
        Some(0),
        MacroExpansionLimits {
            max_invocations: 16,
            max_depth: 16,
            max_evaluation_steps: 1_000,
            max_nodes_per_invocation: 100,
            max_total_nodes: 500,
        },
        context,
        None,
        ScoreErrorPolicy::OmitAndContinue,
        hard,
        operational,
    );
    result.outcome() == ScoreLoweringOutcome::Complete
        && result.score().is_some()
        && result.upstream_diagnostics().is_empty()
        && result.downstream_diagnostics().is_empty()
}

/// Derive the per-form capability matrix by compiling one printed sentence per
/// value. The embedded asset must equal this derivation for the current
/// vocabulary and compiler.
#[must_use]
pub fn derive_work_plan_capabilities() -> WorkPlanCapabilities {
    let vocabulary = work_plan_vocabulary();
    let ja = ResolvedInstructionLanguage::Ja;
    let accepted = |layer: &WorkPlanLayer| {
        let plan = WorkPlan {
            layers: vec![layer.clone()],
            ..WorkPlan::default()
        };
        work_plan_source_compiles_cleanly(&print_work_plan(&plan, ja), ja)
    };
    let mut forms = BTreeMap::new();
    for shape in vocabulary.terms(WorkPlanSlot::Shape) {
        let proportions = std::iter::once(None).chain(
            vocabulary
                .terms(WorkPlanSlot::Proportion)
                .iter()
                .map(|term| Some(term.id.clone())),
        );
        for proportion in proportions {
            let base_action = vocabulary
                .terms(WorkPlanSlot::Action)
                .iter()
                .find_map(|action| {
                    let layer = WorkPlanLayer {
                        shape: shape.id.clone(),
                        proportion: proportion.clone(),
                        action: action.id.clone(),
                        count: 1,
                        attributes: BTreeMap::new(),
                    };
                    accepted(&layer).then_some(layer)
                });
            let Some(base) = base_action else {
                continue;
            };
            let mut slots = BTreeMap::new();
            for slot in WorkPlanSlot::LAYER_ATTRIBUTES {
                let mut values = Vec::new();
                for term in vocabulary.terms(slot) {
                    let mut layer = base.clone();
                    if slot == WorkPlanSlot::Action {
                        layer.action = term.id.clone();
                        layer.count = 5;
                    } else if slot == WorkPlanSlot::LineUpDirection {
                        // Direction exists only on line-up and must print in both languages.
                        layer.action = "line_up".to_owned();
                        layer.count = 5;
                        layer.attributes.insert(slot, term.id.clone());
                        let plan = WorkPlan {
                            layers: vec![layer.clone()],
                            ..WorkPlan::default()
                        };
                        let en = ResolvedInstructionLanguage::En;
                        if accepted(&layer)
                            && work_plan_source_compiles_cleanly(&print_work_plan(&plan, en), en)
                        {
                            values.push(term.id.clone());
                        }
                        continue;
                    } else {
                        if slot == WorkPlanSlot::SurfaceIntensity {
                            layer
                                .attributes
                                .insert(WorkPlanSlot::Surface, "solid".to_owned());
                        }
                        if matches!(
                            slot,
                            WorkPlanSlot::MotionAmplitude | WorkPlanSlot::MotionSpeed
                        ) {
                            let Some(quality) =
                                vocabulary.terms(WorkPlanSlot::MotionQuality).first()
                            else {
                                continue;
                            };
                            layer
                                .attributes
                                .insert(WorkPlanSlot::MotionQuality, quality.id.clone());
                        }
                        layer.attributes.insert(slot, term.id.clone());
                    }
                    if accepted(&layer) {
                        values.push(term.id.clone());
                    }
                }
                slots.insert(slot, values);
            }
            let key = proportion
                .map_or_else(|| shape.id.clone(), |value| format!("{}/{value}", shape.id));
            forms.insert(key, slots);
        }
    }
    WorkPlanCapabilities {
        asset_id: WORK_PLAN_CAPABILITIES_ASSET_ID.to_owned(),
        forms,
    }
}
