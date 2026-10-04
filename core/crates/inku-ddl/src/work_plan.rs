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
use crate::saijiki::{canonical_wire_id, saijiki_asset};

pub const WORK_PLAN_SCHEMA_ID: &str = "inku.work-plan.v2";
pub const WORK_PLAN_CAPABILITIES_ASSET_ID: &str = "inku.work-plan-capabilities.v2";
pub const WORK_PLAN_CAPABILITIES_ASSET_BYTES: &[u8] =
    include_bytes!("../assets/work-plan-capabilities-v2.json");
pub const UNSPECIFIED: &str = "unspecified";
pub const MAX_WORK_PLAN_LAYERS: usize = 8;
pub const MAX_WORK_PLAN_COUNT: u32 = 60;
pub const MAX_WORK_PLAN_PLUGINS: usize = 4;

/// One closed plan slot. Slot names are the plan's JSON field names, and each
/// names what its words mean (the Saijiki's one word, one meaning).
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkPlanSlot {
    Shape,
    Proportion,
    Action,
    Position,
    Size,
    Color,
    Tool,
    Thinness,
    Continuity,
    Surface,
    Handling,
    Angle,
    LineUpDirection,
    MotionQuality,
    MotionAmplitude,
    MotionSpacing,
    Bleeding,
    Ground,
}

impl WorkPlanSlot {
    pub const LAYER_ATTRIBUTES: [Self; 15] = [
        Self::Position,
        Self::Size,
        Self::Color,
        Self::Tool,
        Self::Thinness,
        Self::Continuity,
        Self::Surface,
        Self::Handling,
        Self::Angle,
        Self::LineUpDirection,
        Self::MotionQuality,
        Self::MotionAmplitude,
        Self::MotionSpacing,
        Self::Bleeding,
        Self::Action,
    ];

    #[must_use]
    pub const fn field(self) -> &'static str {
        match self {
            Self::Shape => "shape",
            Self::Proportion => "proportion",
            Self::Action => "action",
            Self::Position => "position",
            Self::Size => "size",
            Self::Color => "color",
            Self::Tool => "tool",
            Self::Thinness => "thinness",
            Self::Continuity => "continuity",
            Self::Surface => "surface",
            Self::Handling => "handling",
            Self::Angle => "angle",
            Self::LineUpDirection => "line_up_direction",
            Self::MotionQuality => "motion_quality",
            Self::MotionAmplitude => "motion_amplitude",
            Self::MotionSpacing => "motion_spacing",
            Self::Bleeding => "bleeding",
            Self::Ground => "ground",
        }
    }
}

/// One closed value with its visible surfaces. The value a provider reads and
/// writes is the word's own English, so a word that keeps one meaning in the
/// Saijiki keeps it in the plan too.
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

/// Each prompt word of one category with its canonical semantic ID, which
/// decides the slot of a word whose category spans several slots.
fn saijiki_terms(category_key: &str) -> Vec<(String, WorkPlanTerm)> {
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
            let canonical =
                project_macro_semantic_ref(category_key, &word.surface_ja)?.canonical_id;
            let en = word.surface_en.clone()?;
            Some((
                canonical,
                WorkPlanTerm {
                    id: canonical_wire_id(&en),
                    ja: word.surface_ja.clone(),
                    en,
                },
            ))
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
    let mut seen: Vec<CoreModifierValue> = Vec::new();
    for (_, value) in ja.thinness.iter().chain(ja.relative_scale) {
        let value = *value;
        if !dimension(value) || seen.contains(&value) {
            continue;
        }
        seen.push(value);
        let forms_ja = if matches!(
            value,
            CoreModifierValue::Fine
                | CoreModifierValue::ExtraFine
                | CoreModifierValue::Thick
                | CoreModifierValue::ExtraThick
        ) {
            ja.thinness
        } else {
            ja.relative_scale
        };
        let forms_en = if matches!(
            value,
            CoreModifierValue::Fine
                | CoreModifierValue::ExtraFine
                | CoreModifierValue::Thick
                | CoreModifierValue::ExtraThick
        ) {
            en.thinness
        } else {
            en.relative_scale
        };
        if let (Some(ja), Some(en)) = (first(forms_ja, value), first(forms_en, value)) {
            out.push(WorkPlanTerm {
                id: canonical_wire_id(&en),
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
            (WorkPlanSlot::Position, "basho"),
            (WorkPlanSlot::Color, "iro"),
            (WorkPlanSlot::Tool, "tezawari"),
            (WorkPlanSlot::Continuity, "tsuranari"),
            (WorkPlanSlot::Angle, "katamuki"),
            (WorkPlanSlot::LineUpDirection, "katamuki"),
            (WorkPlanSlot::Ground, "ji"),
            (WorkPlanSlot::Surface, "omote"),
            (WorkPlanSlot::Handling, "sabaki"),
        ] {
            for (_, term) in saijiki_terms(key) {
                vocabulary.push(slot, term);
            }
        }
        for (canonical, term) in saijiki_terms("yuragi") {
            let slot = match classify_fluctuation_dimension(&canonical) {
                Some(FluctuationDimension::Amplitude) => WorkPlanSlot::MotionAmplitude,
                Some(FluctuationDimension::Frequency) => WorkPlanSlot::MotionSpacing,
                Some(FluctuationDimension::Quality) => WorkPlanSlot::MotionQuality,
                Some(FluctuationDimension::Spread) => WorkPlanSlot::Bleeding,
                None => continue,
            };
            vocabulary.push(slot, term);
        }
        for term in core_terms(|value| {
            matches!(
                value,
                CoreModifierValue::Fine
                    | CoreModifierValue::ExtraFine
                    | CoreModifierValue::Thick
                    | CoreModifierValue::ExtraThick
            )
        }) {
            vocabulary.push(WorkPlanSlot::Thinness, term);
        }
        for term in core_terms(|value| {
            !matches!(
                value,
                CoreModifierValue::Fine
                    | CoreModifierValue::ExtraFine
                    | CoreModifierValue::Thick
                    | CoreModifierValue::ExtraThick
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
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
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

/// One installed plugin a plan may choose: its canonical qualified name, its
/// qualified aliases (the first alias is the Japanese display name), and, when
/// its definition receives the word's count, what that count counts.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct WorkPlanPlugin {
    pub name: String,
    pub aliases: Vec<String>,
    pub counter: Option<crate::CountCounter>,
}

impl WorkPlanPlugin {
    fn answers_to(&self, value: &str) -> bool {
        self.name == value || self.aliases.iter().any(|alias| alias == value)
    }

    /// The name a sentence in `language` is written with.
    fn written(&self, language: ResolvedInstructionLanguage) -> &str {
        match language {
            ResolvedInstructionLanguage::Ja => self.aliases.first().unwrap_or(&self.name),
            ResolvedInstructionLanguage::En => &self.name,
        }
    }
}

/// A normalized plan. Background and ground are optional document sentences.
/// Plugins are installed qualified macro names, each printed as its own sentence.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub struct WorkPlan {
    pub ground: Option<String>,
    pub background: Option<String>,
    pub plugins: Vec<WorkPlanPluginCall>,
    pub layers: Vec<WorkPlanLayer>,
}

/// One chosen plugin and the count the description wrote for it. A count is
/// kept only for a plugin whose definition receives it.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub struct WorkPlanPluginCall {
    pub name: String,
    pub count: Option<u64>,
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
    work_plan_response_schema_with_plugins(&[])
}

/// The response schema with an optional `plugins` list closed over the
/// installed qualified names. Each entry also carries the count the
/// description wrote, 0 when it wrote none. Without installed plugins it equals
/// [`work_plan_response_schema`] byte for byte.
#[must_use]
pub fn work_plan_response_schema_with_plugins(plugins: &[String]) -> Value {
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
    // Every mark is laid with some handling, as it has a surface. Left optional,
    // providers skipped the field on about half of the layers and dropped the
    // faintness a description stated with it.
    let mut schema = json!({
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
                        "shape", "proportion", "action", "count", "position", "size",
                        "color", "tool", "surface", "handling", "motion_quality"
                    ]
                }
            }
        },
        "required": ["background", "ground", "layers"]
    });
    if !plugins.is_empty() {
        // The count has no maximum: a count past the word's range is left
        // to the compiler, which reports it instead of clamping it.
        schema["properties"]["plugins"] = json!({
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": plugins},
                    "count": {"type": "integer", "minimum": 0}
                },
                "required": ["name", "count"]
            },
            "maxItems": MAX_WORK_PLAN_PLUGINS
        });
    }
    schema
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
    normalize_work_plan_with_plugins(raw, &[])
}

/// Normalize a provider plan against the installed plugins. A plugin named by
/// its canonical name or an alias is kept under its canonical name; one that
/// is not installed, repeated, or over the limit is dropped and reported. An
/// entry is an object with `name` and `count`, or a bare name as plans had it
/// before counts. A positive count is kept for a plugin that receives one and
/// is otherwise dropped and reported; 0 means the description wrote none.
#[must_use]
pub fn normalize_work_plan_with_plugins(
    raw: &Value,
    plugins: &[WorkPlanPlugin],
) -> (WorkPlan, Vec<WorkPlanDiagnostic>) {
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
    for value in raw
        .get("plugins")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let (written, count) = match value {
            Value::Object(entry) => (text(entry.get("name")), entry.get("count")),
            other => (text(Some(other)), None),
        };
        let Some(written) = written else {
            continue;
        };
        let Some(plugin) = plugins.iter().find(|plugin| plugin.answers_to(&written)) else {
            note(None, "plugins", written, "unknown_plugin");
            continue;
        };
        let name = plugin.name.clone();
        let count = match count {
            None | Some(Value::Null) => None,
            Some(value) => match value.as_u64() {
                Some(0) => None,
                Some(count) if plugin.counter.is_some() => Some(count),
                Some(count) => {
                    note(
                        None,
                        "plugins",
                        format!("{name}:{count}"),
                        "plugin_takes_no_count",
                    );
                    None
                }
                None => {
                    note(
                        None,
                        "plugins",
                        format!("{name}:{value}"),
                        "invalid_plugin_count",
                    );
                    None
                }
            },
        };
        if plan.plugins.iter().any(|call| call.name == name) {
            note(None, "plugins", name, "repeated_plugin");
        } else if plan.plugins.len() >= MAX_WORK_PLAN_PLUGINS {
            note(None, "plugins", name, "over_plugin_limit");
        } else {
            plan.plugins.push(WorkPlanPluginCall { name, count });
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
        if out.action != "line_up"
            && let Some(value) = out.attributes.remove(&WorkPlanSlot::LineUpDirection)
        {
            note(Some(index), "line_up_direction", value, "requires_line_up");
        }
        if out.attribute(WorkPlanSlot::MotionQuality).is_none() {
            for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpacing] {
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
    // Adjectival core forms attach directly; noun forms take の, which a form
    // such as 特大の already carries (I-709).
    let no = MarkerId::JaNo.surface();
    if surface.ends_with('な') || surface.ends_with('い') || surface.ends_with(no) {
        surface.to_owned()
    } else {
        format!("{surface}{no}")
    }
}

/// The mark that says the composition step chose a range, before the words that
/// name it. The compiler keeps these words unread, so removing the mark makes the
/// range the author's own.
pub const COMPOSITION_MARK_JA: &str = "［構図］";
pub const COMPOSITION_MARK_EN: &str = "[composition]";

/// A range the composition step placed a layer in: the words that name it in each
/// language and its bounds (left, top, right, bottom; y = 0 at the top), each an
/// exact fraction `(numerator, denominator)`.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ComposedRange {
    pub words_ja: String,
    pub words_en: String,
    pub bounds: [(u32, u32); 4],
}

impl ComposedRange {
    /// The range as the visible DDL writes it, from the composition mark to the
    /// closing parenthesis (the printer writes the same text).
    #[must_use]
    pub fn written(&self, language: ResolvedInstructionLanguage) -> String {
        match language {
            ResolvedInstructionLanguage::Ja => format!(
                "{COMPOSITION_MARK_JA}{}（横{}〜{}、縦{}〜{}）",
                self.words_ja,
                self.bound(0),
                self.bound(2),
                self.bound(1),
                self.bound(3)
            ),
            ResolvedInstructionLanguage::En => format!(
                "{COMPOSITION_MARK_EN} {} (horizontal {} to {}, vertical {} to {})",
                self.words_en,
                self.bound(0),
                self.bound(2),
                self.bound(1),
                self.bound(3)
            ),
        }
    }

    fn bound(&self, index: usize) -> String {
        let (numerator, denominator) = self.bounds[index];
        if denominator == 1 {
            numerator.to_string()
        } else {
            format!("{numerator}/{denominator}")
        }
    }
}

fn print_layer_ja(layer: &WorkPlanLayer, range: Option<&ComposedRange>) -> String {
    let ja = ResolvedInstructionLanguage::Ja;
    let no = MarkerId::JaNo.surface();
    let mut out = String::new();
    if let Some(range) = range {
        out.push_str(&format!(
            "{COMPOSITION_MARK_JA}{}（横{}〜{}、縦{}〜{}）",
            range.words_ja,
            range.bound(0),
            range.bound(2),
            range.bound(1),
            range.bound(3)
        ));
        out.push_str(MarkerId::JaNi.surface());
        out.push('、');
    } else if let Some(place) = layer.attribute(WorkPlanSlot::Position) {
        out.push_str(&surface(WorkPlanSlot::Position, place, ja));
        out.push_str(MarkerId::JaNi.surface());
        out.push('、');
    }
    if let Some(quality) = layer.attribute(WorkPlanSlot::MotionQuality) {
        for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpacing] {
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
        WorkPlanSlot::Handling,
        WorkPlanSlot::Surface,
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

fn print_layer_en(layer: &WorkPlanLayer, range: Option<&ComposedRange>) -> String {
    let en = ResolvedInstructionLanguage::En;
    let mut words: Vec<String> = Vec::new();
    if let Some(quality) = layer.attribute(WorkPlanSlot::MotionQuality) {
        // Amplitude and wave spacing words are adverbs (narrowly, loosely).
        for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpacing] {
            if let Some(value) = layer.attribute(slot) {
                words.push(surface(slot, value, en));
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
        WorkPlanSlot::Handling,
        WorkPlanSlot::Surface,
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
    if let Some(range) = range {
        out.push_str(&format!(
            " at the {COMPOSITION_MARK_EN} {} (horizontal {} to {}, vertical {} to {})",
            range.words_en,
            range.bound(0),
            range.bound(2),
            range.bound(1),
            range.bound(3)
        ));
    } else if let Some(place) = layer.attribute(WorkPlanSlot::Position) {
        out.push_str(&format!(
            " at the {}",
            surface(WorkPlanSlot::Position, place, en)
        ));
    }
    out.push('.');
    out
}

/// The plan words a printed value came from, keyed by the semantic ID the
/// compiler reads back, for the slots an alternate composition reads.
fn plan_ids_by_semantic_id() -> &'static BTreeMap<WorkPlanSlot, BTreeMap<String, String>> {
    static TABLES: OnceLock<BTreeMap<WorkPlanSlot, BTreeMap<String, String>>> = OnceLock::new();
    TABLES.get_or_init(|| {
        let mut tables = BTreeMap::new();
        for (slot, key) in [
            (WorkPlanSlot::Shape, "katachi"),
            (WorkPlanSlot::Proportion, "wariai"),
            (WorkPlanSlot::Action, "ugoki"),
            (WorkPlanSlot::Position, "basho"),
            (WorkPlanSlot::Color, "iro"),
            (WorkPlanSlot::Surface, "omote"),
            (WorkPlanSlot::LineUpDirection, "katamuki"),
        ] {
            let table: &mut BTreeMap<String, String> = tables.entry(slot).or_default();
            for (canonical, term) in saijiki_terms(key) {
                table.insert(canonical, term.id);
            }
        }
        tables
    })
}

fn plan_id(slot: WorkPlanSlot, term: &crate::SemanticTerm) -> Option<String> {
    plan_ids_by_semantic_id()
        .get(&slot)?
        .get(&term.identity.id)
        .cloned()
}

/// The plan's size word for a parsed relative scale (its English surface).
fn plan_size_id(value: CoreModifierValue) -> Option<String> {
    core_modifier_surface_forms(ResolvedInstructionLanguage::En)
        .relative_scale
        .iter()
        .find(|(_, candidate)| *candidate == value)
        .map(|(surface, _)| canonical_wire_id(surface))
        .filter(|id| {
            work_plan_vocabulary()
                .terms(WorkPlanSlot::Size)
                .iter()
                .any(|term| term.id == *id)
        })
}

/// The layer a compiled instruction was printed from, limited to what the
/// composition reads: form, action, count, place, size, colour, surface and
/// line-up direction. An alternate composition reads these from the visible
/// instructions alone (draw-system05, 2026-10-04). `None` for an instruction a
/// plan does not write: a Macro word, a relation, a sequence, a fill of a
/// shape, a numeric point, or a value outside the plan's words.
#[must_use]
pub fn composition_layer(instruction: &crate::SemanticInstruction) -> Option<WorkPlanLayer> {
    let entity = &instruction.entity;
    let crate::SemanticHead::Primitive(head) = &entity.head else {
        return None;
    };
    if instruction.relation.is_some()
        || instruction.sequence.is_some()
        || instruction.fill_target.is_some()
        || entity.numeric_position.is_some()
        || !entity.additional_relative_scales.is_empty()
    {
        return None;
    }
    let shape = plan_id(WorkPlanSlot::Shape, head)?;
    let action = plan_id(WorkPlanSlot::Action, instruction.action.as_ref()?)?;
    let proportions: Vec<&crate::SemanticTerm> = [
        entity.proportion.aspect.as_ref(),
        entity.proportion.width_extent.as_ref(),
        entity.proportion.arc_form.as_ref(),
    ]
    .into_iter()
    .flatten()
    .collect();
    let proportion = match proportions.as_slice() {
        [] => None,
        [term] => Some(plan_id(WorkPlanSlot::Proportion, term)?),
        _ => return None,
    };
    let count = match &entity.quantity {
        Some(quantity) => u32::try_from(quantity.value).ok()?,
        None => 1,
    };
    let mut attributes = BTreeMap::new();
    if let Some(place) = &instruction.position {
        attributes.insert(
            WorkPlanSlot::Position,
            plan_id(WorkPlanSlot::Position, place)?,
        );
    }
    if let Some(scale) = &entity.relative_scale {
        attributes.insert(WorkPlanSlot::Size, plan_size_id(scale.value)?);
    }
    if let Some(color) = &entity.color {
        attributes.insert(WorkPlanSlot::Color, plan_id(WorkPlanSlot::Color, color)?);
    }
    if let Some(surface) = &entity.surface.quality {
        attributes.insert(
            WorkPlanSlot::Surface,
            plan_id(WorkPlanSlot::Surface, surface)?,
        );
    }
    if let Some(direction) = &instruction.layout_direction {
        attributes.insert(
            WorkPlanSlot::LineUpDirection,
            plan_id(WorkPlanSlot::LineUpDirection, direction)?,
        );
    }
    Some(WorkPlanLayer {
        shape,
        proportion,
        action,
        count,
        attributes,
    })
}

/// The plan's colour word for a compiled background (the field a composition
/// weighs marks against).
#[must_use]
pub fn composition_background(background: &crate::SemanticBackground) -> Option<String> {
    plan_id(WorkPlanSlot::Color, &background.color)
}

/// Print a normalized plan as visible DDL in the requested language.
#[must_use]
pub fn print_work_plan(plan: &WorkPlan, language: ResolvedInstructionLanguage) -> String {
    print_work_plan_with_plugins(plan, language, &[])
}

/// Print a plan, writing each plugin by the name its language reads: the
/// Japanese alias in Japanese DDL, the canonical name in English DDL.
#[must_use]
pub fn print_work_plan_with_plugins(
    plan: &WorkPlan,
    language: ResolvedInstructionLanguage,
    plugins: &[WorkPlanPlugin],
) -> String {
    print_work_plan_composed(plan, language, plugins, &[])
}

/// Print a plan whose layers the composition step placed: a layer with a range is
/// written with the composition mark and the range instead of a place word. Layers
/// past the end of `ranges`, or with `None`, keep their own place.
#[must_use]
pub fn print_work_plan_composed(
    plan: &WorkPlan,
    language: ResolvedInstructionLanguage,
    plugins: &[WorkPlanPlugin],
    ranges: &[Option<ComposedRange>],
) -> String {
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
    // A plugin sentence is the qualified name, the one form every definition
    // expands without caller-meaning diagnostics, with the count before it
    // when the description wrote one. No action word follows it.
    for call in &plan.plugins {
        let plugin = plugins.iter().find(|plugin| plugin.name == call.name);
        let written = plugin.map_or(call.name.as_str(), |plugin| plugin.written(language));
        let counter = plugin
            .and_then(|plugin| plugin.counter)
            .unwrap_or_default()
            .japanese();
        lines.push(match (language, call.count) {
            (ResolvedInstructionLanguage::Ja, Some(count)) => {
                format!("{count}{counter}の{written}。")
            }
            (ResolvedInstructionLanguage::En, Some(count)) => format!("{count} {written}."),
            (ResolvedInstructionLanguage::Ja, None) => format!("{written}。"),
            (ResolvedInstructionLanguage::En, None) => format!("{written}."),
        });
    }
    for (index, layer) in plan.layers.iter().enumerate() {
        let range = ranges.get(index).and_then(Option::as_ref);
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => print_layer_ja(layer, range),
            ResolvedInstructionLanguage::En => print_layer_en(layer, range),
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
        ScoreErrorPolicy::OmitAndContinue,
        hard,
        operational,
    );
    result.outcome() == ScoreLoweringOutcome::Complete
        && result.score().is_some()
        && result.upstream_diagnostics().is_empty()
        && result.downstream_diagnostics().is_empty()
}

/// Proportion and angle pairs a plan never takes although they compile. An
/// angle turns the shape, so `vertical` turns a `tall` shape 90° and the two
/// words that each say upright draw it lying down (I-710).
const AVOIDED_ANGLES: [(&str, &str); 1] = [("tall", "vertical")];

/// Derive the per-form capability matrix by compiling one printed sentence per
/// value, leaving out the angles in [`AVOIDED_ANGLES`]. The embedded asset must
/// equal this derivation for the current vocabulary and compiler.
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
                    if slot == WorkPlanSlot::Angle
                        && proportion.as_deref().is_some_and(|value| {
                            AVOIDED_ANGLES.contains(&(value, term.id.as_str()))
                        })
                    {
                        continue;
                    }
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
                        if matches!(
                            slot,
                            WorkPlanSlot::MotionAmplitude | WorkPlanSlot::MotionSpacing
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
