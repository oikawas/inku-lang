//! The shared model catalog, labels, and model-picker decisions.
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::sync::OnceLock;
mod chatgpt_auth_policy;
mod chatgpt_policy;
mod model_refresh;
mod provider_settings;

const SOURCE: &str = include_str!("../data/model_catalog.json");
const PROVIDERS: &str = include_str!("../data/provider-definitions.json");
const RETIRED_PROVIDERS: &str = include_str!("../data/retired-providers.json");
const STORED: [(&str, &str); 4] = [
    ("legacy", "legacy"),
    ("subscription", "requires_subscription"),
    ("not_supported", "not_supported"),
    ("eol", "eol"),
];
const MEASUREMENTS: [&str; 14] = [
    "recommendation_llm",
    "recommendation_vision",
    "recommendation_stage1",
    "recommendation_stage2",
    "recommendation_level",
    "speed_class",
    "speed_label",
    "speed_llm_seconds",
    "speed_vision_seconds",
    "cost_usd_llm",
    "cost_usd_vision",
    "comment_ja",
    "comment_en",
    "unsupported_purposes",
];
const ASSESSMENT: [&str; 14] = [
    "unsupported_purposes",
    "not_supported",
    "recommendation_llm",
    "recommendation_stage1",
    "recommendation_stage2",
    "recommendation_vision",
    "speed_class",
    "speed_label",
    "cost_usd_llm",
    "cost_usd_vision",
    "speed_llm_seconds",
    "speed_vision_seconds",
    "comment_ja",
    "comment_en",
];

fn catalog() -> &'static Value {
    static CATALOG: OnceLock<Value> = OnceLock::new();
    CATALOG.get_or_init(|| serde_json::from_str(SOURCE).expect("embedded model catalog"))
}
fn retired_providers() -> &'static Vec<Value> {
    static RETIRED: OnceLock<Vec<Value>> = OnceLock::new();
    RETIRED.get_or_init(|| {
        serde_json::from_str(RETIRED_PROVIDERS).expect("embedded retired providers")
    })
}
fn array(value: Option<&Value>) -> &[Value] {
    value.and_then(Value::as_array).map_or(&[], Vec::as_slice)
}
fn contains(value: Option<&Value>, text: &str) -> bool {
    array(value).iter().any(|v| v.as_str() == Some(text))
}
fn purposes(model: &Value) -> Vec<&str> {
    match model.get("purposes") {
        None => vec!["llm"],
        present => array(present).iter().filter_map(Value::as_str).collect(),
    }
}
fn labels(model: &Value, source: &Value) -> Vec<String> {
    let mut names: HashSet<&str> = STORED
        .iter()
        .filter_map(|(label, key)| (model.get(*key) == Some(&Value::Bool(true))).then_some(*label))
        .collect();
    if !purposes(model)
        .iter()
        .any(|p| !contains(model.get("unsupported_purposes"), p))
    {
        names.insert("no_response");
    }
    let table = array(source.get("labels"));
    let publishable = table
        .iter()
        .filter_map(|l| {
            l.get("id")
                .and_then(Value::as_str)
                .map(|id| (id, l["publishable"] == true))
        })
        .collect::<std::collections::HashMap<_, _>>();
    if !MEASUREMENTS.iter().any(|key| model.get(*key).is_some())
        && names.iter().all(|id| publishable.get(id) == Some(&true))
    {
        names.insert("unmeasured");
    }
    table
        .iter()
        .filter_map(|l| l.get("id").and_then(Value::as_str))
        .filter(|id| names.contains(id))
        .map(str::to_owned)
        .collect()
}
fn number(model: &Value, key: &str) -> Option<f64> {
    model.get(key).and_then(Value::as_f64)
}
fn level(model: &Value, purpose: &str, stage: &str) -> f64 {
    let llm = number(model, "recommendation_llm")
        .or_else(|| number(model, "recommendation_level"))
        .unwrap_or(0.0);
    let vision = number(model, "recommendation_vision")
        .or_else(|| number(model, "recommendation_level"))
        .unwrap_or(0.0);
    let s1 = number(model, "recommendation_stage1");
    let s2 = number(model, "recommendation_stage2");
    let llm = match stage {
        "stage1" => s1.unwrap_or(llm),
        "stage2" => s2.unwrap_or(llm),
        "both" => match (s1, s2) {
            (Some(a), Some(b)) => a.min(b),
            (Some(a), None) | (None, Some(a)) => a,
            _ => llm,
        },
        _ => llm,
    };
    let p = purposes(model);
    let result = match purpose {
        "llm" => llm,
        "vision" => vision,
        _ => (if p.contains(&"llm") { llm } else { 0.0 }).max(if p.contains(&"vision") {
            vision
        } else {
            0.0
        }),
    };
    result.clamp(0.0, 5.0)
}
fn sort_name(model: &Value) -> String {
    let name = model
        .get("label")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .or_else(|| model.get("id").and_then(Value::as_str))
        .unwrap_or("");
    static COLLATOR: OnceLock<icu_collator::CollatorBorrowed<'static>> = OnceLock::new();
    let collator = COLLATOR.get_or_init(|| {
        icu_collator::Collator::try_new(Default::default(), Default::default())
            .expect("compiled Unicode collation data")
    });
    let mut key = Vec::new();
    collator
        .write_sort_key_to(name, &mut key)
        .expect("a vector cannot reject a collation key");
    key.iter().map(|byte| format!("{byte:02x}")).collect()
}
fn labelled(model: &Value, source: &Value) -> Value {
    let mut object = model.as_object().cloned().unwrap_or_default();
    let tags = labels(model, source);
    let blocked = array(source.get("labels"))
        .iter()
        .any(|row| row["publishable"] == false && tags.iter().any(|tag| row["id"] == *tag));
    let mut levels = Map::new();
    let mut sort_keys = Map::new();
    let name_key = sort_name(model);
    for p in ["none", "llm", "vision"] {
        let mut stages = Map::new();
        let mut keys = Map::new();
        for s in ["none", "stage1", "stage2", "both"] {
            let value = level(model, p, s);
            let unsupported = p != "none" && contains(model.get("unsupported_purposes"), p);
            stages.insert(s.to_owned(), json!(value));
            keys.insert(
                s.to_owned(),
                json!(format!(
                    "{}{}{:016x}{}",
                    u8::from(blocked),
                    u8::from(unsupported),
                    (5.0 - value).to_bits(),
                    name_key
                )),
            );
        }
        levels.insert(p.to_owned(), Value::Object(stages));
        sort_keys.insert(p.to_owned(), Value::Object(keys));
    }
    object.insert("fold".into(), tags.last().map_or(Value::Null, |s| json!(s)));
    object.insert("labels".into(), json!(tags));
    object.insert("selection".into(), json!({"unselectable": blocked,
        "unsupported": {"llm": contains(model.get("unsupported_purposes"), "llm"), "vision": contains(model.get("unsupported_purposes"), "vision")},
        "levels": levels, "sort_keys": sort_keys}));
    Value::Object(object)
}
fn internal(record: &Value) -> Value {
    let mut out = record.as_object().cloned().unwrap_or_default();
    for (label, key) in STORED {
        if contains(record.get("labels"), label) {
            out.insert(key.into(), json!(true));
        }
    }
    out.remove("labels");
    Value::Object(out)
}
fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().is_some_and(|number| number != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}
fn python_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::String(text) => {
            let quote = if text.contains('\'') && !text.contains('"') {
                '"'
            } else {
                '\''
            };
            let mut out = String::from(quote);
            for c in text.chars() {
                match c {
                    '\\' => out.push_str("\\\\"),
                    '\n' => out.push_str("\\n"),
                    '\r' => out.push_str("\\r"),
                    '\t' => out.push_str("\\t"),
                    c if c == quote => {
                        out.push('\\');
                        out.push(c);
                    }
                    c if c.is_control() && (c as u32) < 256 => {
                        out.push_str(&format!("\\x{:02x}", c as u32))
                    }
                    c => out.push(c),
                }
            }
            out.push(quote);
            out
        }
        value => value.to_string(),
    }
}
fn python_str(value: &Value) -> String {
    value
        .as_str()
        .map_or_else(|| python_repr(value), str::to_owned)
}
fn problems(source: &Value, provider_order: &[String]) -> Vec<String> {
    let mut out = Vec::new();
    if source.get("schema").and_then(Value::as_str) != Some("inku.model-catalog.v2") {
        let shown = python_repr(source.get("schema").unwrap_or(&Value::Null));
        out.push(format!("schema {shown}"));
    }
    let table = array(source.get("labels"));
    let ids: Vec<Value> = table
        .iter()
        .map(|row| row.get("id").cloned().unwrap_or(Value::Null))
        .collect();
    if ids
        .iter()
        .map(Value::to_string)
        .collect::<HashSet<_>>()
        .len()
        != ids.len()
        || table.iter().any(|row| {
            !row["publishable"].is_boolean() || !truthy(&row["ja"]) || !truthy(&row["en"])
        })
    {
        out.push("label table".into());
    }
    for (label, _) in STORED {
        if !ids.contains(&json!(label)) {
            out.push(format!("stored label {label} missing from the table"));
        }
    }
    if let Some(providers) = source.get("providers").and_then(Value::as_object) {
        let order: Vec<&str> = if provider_order.is_empty() {
            providers.keys().map(String::as_str).collect()
        } else {
            provider_order.iter().map(String::as_str).collect()
        };
        for provider_id in order {
            let Some(provider) = providers.get(provider_id) else {
                continue;
            };
            let records = array(provider.get("models"));
            let ids: Vec<Value> = records
                .iter()
                .map(|row| row.get("id").cloned().unwrap_or(Value::Null))
                .collect();
            if ids.iter().any(|id| id.as_str().is_none_or(str::is_empty))
                || ids
                    .iter()
                    .map(Value::to_string)
                    .collect::<HashSet<_>>()
                    .len()
                    != ids.len()
            {
                out.push(format!("{provider_id}: model ids"));
            }
            for id in array(provider.get("defaults")) {
                if !ids.contains(id) {
                    out.push(format!(
                        "{provider_id}: default {} has no entry",
                        python_str(id)
                    ));
                }
            }
            for record in records {
                let id = python_str(&record["id"]);
                let mut unknown: Vec<_> = record
                    .as_object()
                    .into_iter()
                    .flat_map(|o| o.keys())
                    .filter(|key| {
                        !["id", "label", "notes", "purposes", "labels", "eol_date"]
                            .contains(&key.as_str())
                            && !MEASUREMENTS.contains(&key.as_str())
                    })
                    .collect();
                unknown.sort();
                if !unknown.is_empty() {
                    out.push(format!(
                        "{provider_id}/{id}: unknown keys [{}]",
                        unknown
                            .iter()
                            .map(|s| python_repr(&json!(s)))
                            .collect::<Vec<_>>()
                            .join(", ")
                    ));
                }
                for label in array(record.get("labels")) {
                    if !STORED.iter().any(|(name, _)| label.as_str() == Some(*name)) {
                        out.push(format!(
                            "{provider_id}/{id}: label {} is not written in the catalog",
                            python_str(label)
                        ));
                    }
                }
                for key in ["purposes", "unsupported_purposes"] {
                    if record.get(key).is_some()
                        && array(record.get(key))
                            .iter()
                            .any(|v| !matches!(v.as_str(), Some("llm" | "vision")))
                    {
                        out.push(format!("{provider_id}/{id}: {key}"));
                    }
                }
            }
        }
    }
    out
}
fn provider_order(input: &[u8]) -> Vec<String> {
    use crate::identity::{Value as PythonValue, python_loads};
    fn member<'a>(value: &'a PythonValue, key: &str) -> Option<&'a PythonValue> {
        match value {
            PythonValue::Object(entries) => entries
                .iter()
                .find(|(name, _)| name == key)
                .map(|(_, value)| value),
            _ => None,
        }
    }
    let Some(request) = std::str::from_utf8(input)
        .ok()
        .and_then(|text| python_loads(text).ok())
    else {
        return vec![];
    };
    let Some(PythonValue::Object(providers)) =
        member(&request, "catalog").and_then(|value| member(value, "providers"))
    else {
        return vec![];
    };
    providers.iter().map(|(name, _)| name.clone()).collect()
}
fn info() -> Value {
    static INFO: OnceLock<Value> = OnceLock::new();
    INFO.get_or_init(|| {
    let source = catalog();
    let canonical = crate::identity::canonical_json(SOURCE).expect("canonical model catalog");
    let hash: String = Sha256::digest(canonical.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    let mut defaults = Map::new();
    if let Some(providers) = source["providers"].as_object() {
        for (id, provider) in providers {
            let models = array(provider.get("models"));
            let rows: Vec<Value> = array(provider.get("defaults"))
                .iter()
                .filter_map(|wanted| {
                    models
                        .iter()
                        .find(|item| item.get("id") == Some(wanted))
                        .map(internal)
                })
                .collect();
            defaults.insert(id.clone(), json!(rows));
        }
    }
    json!({"catalog":source, "version":format!("{}+{}", catalog()["version"].as_str().unwrap_or(""), &hash[..12]),
        "defaults":defaults, "stored_label_keys":STORED.into_iter().collect::<std::collections::BTreeMap<_, _>>(),
        "measurement_keys":MEASUREMENTS, "assessment_keys":ASSESSMENT})

    }).clone()
}

fn provider_definitions(host: &str) -> Vec<Value> {
    let mut definitions: Vec<Value> =
        serde_json::from_str(PROVIDERS).expect("embedded provider definitions");
    let defaults = info()["defaults"].clone();
    definitions.retain(|provider| host != "android" || provider["id"] != "ollama");
    for provider in &mut definitions {
        let id = provider["id"].as_str().expect("provider id").to_owned();
        provider["models"] = defaults[&id].clone();
    }
    if host == "android" {
        definitions.insert(
            0,
            json!({"id":"local-litert-lm","label":"LiteRT-LM / Local",
            "kind":"litert_lm","api_key_env":"","base_url_env":"",
            "default_base_url":"local://litert-lm","requires_api_key":false,"models":[]}),
        );
    }
    definitions
}

fn split_ref<'a>(reference: &'a str, providers: &Value) -> (Option<&'a str>, &'a str) {
    if let Some((head, rest)) = reference.split_once(':')
        && !head.is_empty()
        && !rest.is_empty()
        && (head == "chatgpt"
            || retired_providers().iter().any(|p| p["id"] == head)
            || providers.get(head).is_some())
    {
        return (Some(head), rest);
    }
    (None, reference)
}

fn user_defaults() -> Value {
    json!({"stage1_provider":"nvidia", "stage1_model":"google/gemma-4-31b-it",
        "stage2_provider":"nvidia", "stage2_model":"google/gemma-4-31b-it",
        "vision_provider":"nvidia", "vision_model":"meta/llama-3.2-90b-vision-instruct",
        "okugaki_provider":"nvidia", "okugaki_model":"meta/llama-3.2-90b-vision-instruct",
        "model_inspection_selected_models":[], "instruction_caption_visible":true,
        "instruction_caption_writing_mode":"horizontal", "instruction_caption_position":"left",
        "color_catalog_id":"default", "ui_text_size":1, "sketch_open":true,
        "generation_info_follows_selection":true, "generation_info_token_detail":false})
}

fn normalize_user(input: &Value, color_ids: &Value, default_color: &str) -> Value {
    let mut clean = user_defaults();
    if !input.is_object() {
        return clean;
    }
    for key in [
        "stage1_provider",
        "stage2_provider",
        "vision_provider",
        "okugaki_provider",
    ] {
        if let Some(text) = input[key].as_str().filter(|s| !s.trim().is_empty()) {
            clean[key] = json!(text);
        }
    }
    for key in [
        "stage1_model",
        "stage2_model",
        "vision_model",
        "okugaki_model",
    ] {
        if let Some(text) = input[key].as_str().map(str::trim).filter(|s| !s.is_empty()) {
            clean[key] = json!(text);
        }
    }
    let definitions: Vec<Value> =
        serde_json::from_str(PROVIDERS).expect("embedded provider definitions");
    let providers: Map<String, Value> = definitions
        .iter()
        .filter_map(|p| p["id"].as_str().map(|id| (id.to_owned(), json!({}))))
        .collect();
    let okugaki = clean["okugaki_model"].as_str().unwrap().to_owned();
    let (prefix, bare) = split_ref(&okugaki, &Value::Object(providers));
    if let Some(prefix) = prefix {
        clean["okugaki_provider"] = json!(prefix);
        clean["okugaki_model"] = json!(bare);
    }
    clean["stage2_provider"] = clean["stage1_provider"].clone();
    clean["stage2_model"] = clean["stage1_model"].clone();
    let mut seen = HashSet::new();
    let selected: Vec<&str> = array(input.get("model_inspection_selected_models"))
        .iter()
        .filter_map(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty() && seen.insert(*s))
        .take(4)
        .collect();
    clean["model_inspection_selected_models"] = json!(selected);
    for key in [
        "instruction_caption_visible",
        "sketch_open",
        "generation_info_follows_selection",
    ] {
        clean[key] = json!(input.get(key) != Some(&Value::Bool(false)));
    }
    clean["generation_info_token_detail"] =
        json!(input.get("generation_info_token_detail") == Some(&Value::Bool(true)));
    for (key, valid, fallback) in [
        (
            "instruction_caption_writing_mode",
            &["horizontal", "vertical"][..],
            "horizontal",
        ),
        (
            "instruction_caption_position",
            &["left", "right"][..],
            "left",
        ),
    ] {
        clean[key] = json!(
            input[key]
                .as_str()
                .filter(|s| valid.contains(s))
                .unwrap_or(fallback)
        );
    }
    let choice = input["color_catalog_id"].as_str().unwrap_or("").trim();
    clean["color_catalog_id"] = json!(if choice == "auto" || contains(Some(color_ids), choice) {
        choice
    } else {
        default_color
    });
    clean["ui_text_size"] = json!(
        input["ui_text_size"]
            .as_i64()
            .filter(|v| (0..5).contains(v))
            .unwrap_or(1)
    );
    clean
}

fn update_user(current: &Value, patch: &Value, colors: &Value, default_color: &str) -> Value {
    let mut clean = normalize_user(current, colors, default_color);
    for key in [
        "stage1_provider",
        "stage2_provider",
        "vision_provider",
        "okugaki_provider",
        "stage1_model",
        "stage2_model",
        "vision_model",
        "okugaki_model",
    ] {
        if let Some(text) = patch[key].as_str().filter(|s| !s.trim().is_empty()) {
            clean[key] = json!(if key.ends_with("_model") {
                text.trim()
            } else {
                text
            });
        }
    }
    for key in [
        "instruction_caption_visible",
        "sketch_open",
        "generation_info_follows_selection",
        "generation_info_token_detail",
    ] {
        if let Some(value) = patch.get(key) {
            clean[key] = json!(truthy(value));
        }
    }
    for key in [
        "instruction_caption_writing_mode",
        "instruction_caption_position",
        "model_inspection_selected_models",
        "color_catalog_id",
        "ui_text_size",
    ] {
        if let Some(value) = patch.get(key) {
            clean[key] = value.clone();
        }
    }
    normalize_user(&clean, colors, default_color)
}

fn model_rows(payload: &Value) -> Result<Vec<Value>, &'static str> {
    let rows = payload
        .get("data")
        .filter(|v| !v.is_null())
        .or_else(|| payload.get("models"));
    let Some(rows) = rows.and_then(Value::as_array) else {
        return Err("model list response did not contain models");
    };
    let mut result = Vec::new();
    for row in rows.iter().filter(|row| row.is_object()) {
        let text = |keys: &[&str]| {
            keys.iter()
                .filter_map(|k| row.get(*k))
                .find(|v| truthy(v))
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| python_repr(v))
                })
                .unwrap_or_default()
        };
        let id = text(&["id", "name"]);
        let id = id.trim().strip_prefix("models/").unwrap_or(id.trim());
        if id.is_empty() {
            continue;
        }
        let label = text(&["display_name", "displayName"]);
        let label = if label.trim().is_empty() {
            id
        } else {
            label.trim()
        };
        result.push(json!({"id":id,"label":label}));
    }
    if result.is_empty() {
        return Err("model list response was empty");
    }
    Ok(result)
}

fn masked_secret(secret: &str) -> Value {
    let chars: Vec<char> = secret.chars().collect();
    if chars.is_empty() {
        Value::Null
    } else if chars.len() <= 8 {
        json!("****")
    } else {
        json!(format!(
            "{}...{}",
            chars[..4].iter().collect::<String>(),
            chars[chars.len() - 4..].iter().collect::<String>()
        ))
    }
}

fn normalize_models(models: &Value) -> Vec<Value> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for model in array(Some(models)).iter().filter(|m| m.is_object()) {
        let id = model
            .get("id")
            .filter(|v| truthy(v))
            .map(|v| {
                v.as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| python_repr(v))
            })
            .unwrap_or_default();
        let id = id.trim().to_owned();
        if id.is_empty() || !seen.insert(id.clone()) {
            continue;
        }
        let label = model
            .get("label")
            .filter(|v| truthy(v))
            .map(|v| {
                v.as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| python_repr(v))
            })
            .unwrap_or_else(|| id.clone());
        let label = if label.trim().is_empty() {
            id.clone()
        } else {
            label.trim().to_owned()
        };
        let mut out = Map::new();
        out.insert("id".into(), json!(id));
        out.insert("label".into(), json!(label));
        if let Some(text) = model["notes"]
            .as_str()
            .map(str::trim)
            .filter(|s| !s.is_empty())
        {
            out.insert("notes".into(), json!(text));
        }
        let mut purposes: Vec<&str> = if model["purposes"].is_array() {
            ["llm", "vision"]
                .into_iter()
                .filter(|p| contains(model.get("purposes"), p))
                .collect()
        } else if format!(
            "{} {}",
            id,
            out.get("notes").and_then(Value::as_str).unwrap_or("")
        )
        .to_lowercase()
        .contains("vision")
        {
            vec!["vision"]
        } else {
            vec!["llm"]
        };
        let unsupported: Vec<&str> = ["llm", "vision"]
            .into_iter()
            .filter(|p| contains(model.get("unsupported_purposes"), p))
            .collect();
        let allowed: Vec<&str> = unsupported
            .iter()
            .copied()
            .filter(|p| contains(model.get("allowed_unsupported_purposes"), p))
            .collect();
        purposes.retain(|p| !unsupported.contains(p) || allowed.contains(p));
        if purposes.is_empty() && unsupported.is_empty() {
            purposes.push("llm");
        }
        out.insert("purposes".into(), json!(purposes));
        if !unsupported.is_empty() {
            out.insert("unsupported_purposes".into(), json!(unsupported));
        }
        let allowed: Vec<&str> = allowed
            .into_iter()
            .filter(|p| purposes.contains(p))
            .collect();
        if !allowed.is_empty() {
            out.insert("allowed_unsupported_purposes".into(), json!(allowed));
        }
        for (key, purpose) in [
            ("recommendation_llm", "llm"),
            ("recommendation_vision", "vision"),
        ] {
            let level = model[key].as_i64().or_else(|| {
                if purposes.contains(&purpose) {
                    model["recommendation_level"].as_i64()
                } else {
                    None
                }
            });
            if let Some(n) = level {
                out.insert(key.into(), json!(n.clamp(1, 5)));
            }
        }
        for key in ["recommendation_stage1", "recommendation_stage2"] {
            if let Some(n) = model[key].as_i64() {
                out.insert(key.into(), json!(n.clamp(1, 5)));
            }
        }
        for key in [
            "speed_class",
            "speed_label",
            "comment_ja",
            "comment_en",
            "eol_date",
        ] {
            if let Some(text) = model[key].as_str().map(str::trim).filter(|s| !s.is_empty()) {
                out.insert(key.into(), json!(text));
            }
        }
        for key in [
            "cost_usd_llm",
            "cost_usd_vision",
            "speed_llm_seconds",
            "speed_vision_seconds",
        ] {
            if let Some(n) = model[key].as_f64().filter(|n| {
                n.is_finite()
                    && if key.starts_with("speed_") {
                        *n > 0.0
                    } else {
                        *n >= 0.0
                    }
            }) {
                out.insert(key.into(), json!(n));
            }
        }
        for key in ["eol", "requires_subscription", "not_supported", "legacy"] {
            if model[key] == true {
                out.insert(key.into(), json!(true));
            }
        }
        for (label, key) in STORED {
            if contains(model.get("labels"), label) {
                out.insert(key.into(), json!(true));
            }
        }
        result.push(Value::Object(out));
    }
    result
}

fn provider_catalog(
    settings: &Value,
    order: &Value,
    include_disabled: bool,
    include_developer: bool,
    purpose: &str,
) -> Vec<Value> {
    let providers = &settings["providers"];
    let definitions: Vec<Value> =
        serde_json::from_str(PROVIDERS).expect("embedded provider definitions");
    let mut result = Vec::new();
    for id in array(Some(order)).iter().filter_map(Value::as_str) {
        let provider = &providers[id];
        if provider.get("active").is_some_and(|v| !truthy(v)) {
            continue;
        }
        let builtin = definitions.iter().find(|d| d["id"] == id);
        if !include_developer && builtin.is_some_and(|d| truthy(&d["developer_only"])) {
            continue;
        }
        let hide_speed =
            !include_developer && builtin.is_some_and(|d| truthy(&d["speed_developer_only"]));
        let mut models = Vec::new();
        for model in array(provider.get("models")) {
            let model_id = model["id"].as_str().unwrap_or("");
            let enabled = provider["enabled_models"]
                .get(model_id)
                .map(truthy)
                .unwrap_or(true);
            let purposes = model
                .get("purposes")
                .cloned()
                .unwrap_or_else(|| json!(["llm"]));
            if !purpose.is_empty() && !contains(Some(&purposes), purpose) {
                continue;
            }
            if include_disabled || enabled {
                let mut row = model.clone();
                row["enabled"] = json!(enabled);
                let mut shown = labelled(&row, catalog());
                if hide_speed {
                    for key in [
                        "speed_class",
                        "speed_label",
                        "speed_llm_seconds",
                        "speed_vision_seconds",
                    ] {
                        shown.as_object_mut().unwrap().remove(key);
                    }
                }
                models.push(shown);
            }
        }
        let mut row = Map::new();
        for key in [
            "id",
            "label",
            "kind",
            "api_key_env",
            "base_url_env",
            "default_base_url",
            "requires_api_key",
        ] {
            row.insert(key.into(), provider[key].clone());
        }
        row.insert(
            "builtin".into(),
            provider.get("builtin").cloned().unwrap_or(json!(false)),
        );
        row.insert(
            "active".into(),
            provider.get("active").cloned().unwrap_or(json!(true)),
        );
        row.insert("models".into(), json!(models));
        if include_disabled {
            row.insert(
                "memo".into(),
                json!(provider["memo"].as_str().unwrap_or("")),
            );
        }
        result.push(Value::Object(row));
    }
    result
}

fn resolve_ref(
    reference: &str,
    providers: &Value,
    default_provider: &str,
    default_model: &str,
) -> Value {
    if reference.is_empty() {
        return json!({"provider":default_provider, "model":default_model});
    }
    let (qualified, model) = split_ref(reference, providers);
    if let Some(provider) = qualified {
        return json!({"provider":provider, "model":model});
    }
    let owners: Vec<&str> = providers
        .as_object()
        .into_iter()
        .flat_map(|entries| entries.iter())
        .filter(|(id, _)| id.as_str() != "chatgpt")
        .filter(|(_, provider)| {
            provider
                .get("active")
                .and_then(Value::as_bool)
                .unwrap_or(true)
        })
        .filter(|(_, provider)| {
            array(provider.get("models"))
                .iter()
                .any(|model| model["id"].as_str() == Some(reference))
        })
        .map(|(id, _)| id.as_str())
        .collect();
    json!({"provider":if owners.len() == 1 { owners[0] } else { default_provider }, "model":reference})
}

/// One host-neutral JSON request and answer.
#[must_use]
pub fn model_catalog_json(input: &[u8]) -> Vec<u8> {
    let request: Value = match serde_json::from_slice(input) { Ok(v) => v, Err(_) => return br#"{"schema":"inku.model-catalog.v1","outcome":"refused","reason":"invalid_json"}"#.to_vec() };
    let source = catalog();
    if request.get("schema").and_then(Value::as_str) != Some("inku.model-catalog-request.v1") {
        return br#"{"schema":"inku.model-catalog.v1","outcome":"refused","reason":"invalid_schema"}"#.to_vec();
    }
    let result = match request.get("action").and_then(Value::as_str) {
        Some("catalog") => info(),
        Some("provider_metadata") => {
            json!({"recommendation":&provider_settings::METADATA[4..9], "measurement":&provider_settings::METADATA[11..15],
            "metadata":&provider_settings::METADATA[..17], "catalog":provider_settings::METADATA})
        }
        Some("retired_providers") => json!({"providers":retired_providers()}),
        Some(
            "chatgpt_publication"
            | "chatgpt_publication_update"
            | "chatgpt_usable"
            | "chatgpt_offered"
            | "chatgpt_cache",
        ) => chatgpt_policy::run(&request),
        Some(
            "chatgpt_auth_url"
            | "chatgpt_auth_endpoint"
            | "chatgpt_auth_claims"
            | "chatgpt_auth_callback"
            | "chatgpt_auth_tokens"
            | "chatgpt_auth_access"
            | "chatgpt_auth_session"
            | "chatgpt_auth_transition"
            | "chatgpt_auth_preserve"
            | "chatgpt_auth_discovery"
            | "chatgpt_auth_identity"
            | "chatgpt_auth_generation"
            | "chatgpt_auth_constants"
            | "chatgpt_auth_callback_client"
            | "chatgpt_auth_select",
        ) => chatgpt_auth_policy::run(&request),
        Some("reference_batch") => {
            let results: Vec<Value> = array(request.get("queries"))
                .iter()
                .map(|query| {
                    if ![
                        "split_ref",
                        "qualify_ref",
                        "resolve_ref",
                        "resolve_display",
                        "resolve_stage_default",
                    ]
                    .contains(&query["action"].as_str().unwrap_or(""))
                    {
                        return json!({"outcome":"refused","reason":"unknown_action"});
                    }
                    let mut input = query.as_object().cloned().unwrap_or_default();
                    input.insert("schema".into(), json!("inku.model-catalog-request.v1"));
                    input.insert("providers".into(), request["providers"].clone());
                    serde_json::from_slice(&model_catalog_json(
                        &serde_json::to_vec(&input).expect("reference query"),
                    ))
                    .expect("reference answer")
                })
                .collect();
            json!({"results":results})
        }
        Some("mask_secret") => {
            let secret = request["secret"].as_str().unwrap_or("");
            json!({"masked":masked_secret(secret)})
        }
        Some("public_settings") => {
            let mut providers = Map::new();
            let defs: Vec<Value> =
                serde_json::from_str(PROVIDERS).expect("embedded provider definitions");
            for id in array(request.get("order")).iter().filter_map(Value::as_str) {
                let p = &request["settings"]["providers"][id];
                if p.get("active").is_some_and(|v| !truthy(v)) {
                    continue;
                }
                if request["include_developer"] == false
                    && defs
                        .iter()
                        .find(|d| d["id"] == id)
                        .is_some_and(|d| truthy(&d["developer_only"]))
                {
                    continue;
                }
                let key = request["keys"][id].as_str().unwrap_or("");
                providers.insert(id.into(), json!({"base_url":if truthy(&p["base_url"]) {p["base_url"].clone()} else {p["default_base_url"].clone()},
                    "api_key_set":!key.is_empty(), "api_key_hint":masked_secret(key), "enabled_models":p["enabled_models"], "rate_limits":p["rate_limits"]}));
            }
            json!({"settings":{"providers":providers}})
        }
        Some("provider_concurrency") => {
            let id = request["provider"].as_str().unwrap_or("");
            let definitions: Vec<Value> =
                serde_json::from_str(PROVIDERS).expect("embedded provider definitions");
            let limit = definitions
                .iter()
                .find(|d| d["id"] == id)
                .and_then(|d| d["max_concurrency"].as_u64())
                .unwrap_or(0);
            json!({"limit":limit})
        }
        Some("connection") => {
            let id = request["provider"].as_str().unwrap_or("");
            let provider = &request["settings"]["providers"][id];
            if !provider.is_object() {
                json!({"error":format!("unknown model provider: {id}")})
            } else {
                json!({"connection":{"id":id,"kind":if provider["kind"] == "mlx" {json!("openai_compatible")} else {provider["kind"].clone()},
                "api_profile":provider["kind"], "base_url":if truthy(&provider["base_url"]) {provider["base_url"].clone()} else {provider["default_base_url"].clone()},
                "requires_api_key":provider["requires_api_key"],"rate_limits":provider["rate_limits"]}})
            }
        }
        Some(
            "default_settings" | "normalize_settings" | "update_settings" | "validate_settings",
        ) => provider_settings::run(&request),
        Some(
            "refresh_prepare" | "refresh_finish" | "access_probe" | "access_enabled"
            | "access_targets" | "access_apply",
        ) => model_refresh::run(&request),
        Some("normalize_models") => json!({"models":normalize_models(&request["models"])}),
        Some("provider_catalog") => {
            json!({"providers":provider_catalog(&request["settings"], &request["order"],
            request["include_disabled"].as_bool().unwrap_or(true), request["include_developer"].as_bool().unwrap_or(true),
            request["purpose"].as_str().unwrap_or(""))})
        }
        Some("model_offered") => {
            let groups = provider_catalog(
                &request["settings"],
                &request["order"],
                false,
                true,
                request["purpose"].as_str().unwrap_or(""),
            );
            let offered = groups
                .iter()
                .find(|group| group["id"] == request["provider"])
                .is_some_and(|group| {
                    array(group.get("models"))
                        .iter()
                        .any(|model| model["id"] == request["model"])
                });
            json!({"offered":offered})
        }
        Some("model_rows") => match model_rows(&request["payload"]) {
            Ok(models) => json!({"models": models}),
            Err(reason) => json!({"error":reason}),
        },
        Some("model_list_start") => {
            let kind = request["kind"].as_str().unwrap_or("");
            let base = request["base_url"]
                .as_str()
                .unwrap_or("")
                .trim_end_matches('/');
            let key = request["api_key"].as_str().unwrap_or("");
            let mut headers = Map::new();
            headers.insert("Accept".into(), json!("application/json"));
            let (path, items, query) = match kind {
                "anthropic" => {
                    if !key.is_empty() {
                        headers.insert("x-api-key".into(), json!(key));
                    }
                    headers.insert("anthropic-version".into(), json!("2023-06-01"));
                    ("/v1/models", "data", json!({"limit":"1000"}))
                }
                "gemini" => {
                    if !key.is_empty() {
                        headers.insert("x-goog-api-key".into(), json!(key));
                    }
                    ("/v1beta/models", "models", json!({"pageSize":"1000"}))
                }
                _ => {
                    if !key.is_empty() {
                        headers.insert("Authorization".into(), json!(format!("Bearer {key}")));
                    }
                    ("/models", "", Value::Null)
                }
            };
            json!({"url":format!("{base}{path}"), "headers":headers, "items_key":items, "query":query, "page_limit":20})
        }
        Some("model_list_next") => {
            let page = &request["page"];
            let next = match request["kind"].as_str().unwrap_or("") {
                "anthropic" if truthy(&page["has_more"]) && truthy(&page["last_id"]) => {
                    json!({"after_id":page["last_id"]})
                }
                "gemini" if truthy(&page["nextPageToken"]) => {
                    json!({"pageToken":page["nextPageToken"]})
                }
                _ => Value::Null,
            };
            json!({"query":next})
        }
        Some("user_defaults") => json!({"settings":user_defaults()}),
        Some("normalize_user") => {
            json!({"settings":normalize_user(&request["settings"], &request["color_ids"], request["default_color"].as_str().unwrap_or("default"))})
        }
        Some("update_user") => {
            json!({"settings":update_user(&request["settings"], &request["patch"], &request["color_ids"], request["default_color"].as_str().unwrap_or("default"))})
        }
        Some("rate_limits") => {
            let gemini = request["provider"].as_str() == Some("gemini");
            let incoming = &request["value"];
            let defaults = if gemini {
                [30, 16000, 14400]
            } else {
                [0, 0, 0]
            };
            let values: Map<String, Value> = ["rpm", "tpm", "rpd"]
                .into_iter()
                .zip(defaults)
                .map(|(key, default)| {
                    let value = incoming
                        .get(key)
                        .and_then(Value::as_i64)
                        .filter(|value| (0..=1_000_000_000).contains(value))
                        .unwrap_or(default);
                    (key.to_owned(), json!(value))
                })
                .collect();
            json!({"rate_limits":values})
        }
        Some("providers") => {
            json!({"providers": provider_definitions(request["host"].as_str().unwrap_or("server"))})
        }
        Some("split_ref") => {
            let (provider, model) =
                split_ref(request["ref"].as_str().unwrap_or(""), &request["providers"]);
            json!({"provider":provider, "model":model})
        }
        Some("qualify_ref") => {
            let provider = request["provider"].as_str().unwrap_or("").trim();
            let reference = request["ref"].as_str().unwrap_or("").trim();
            let qualified = if provider.is_empty()
                || reference.is_empty()
                || split_ref(reference, &request["providers"]).0.is_some()
            {
                reference.to_owned()
            } else {
                format!("{provider}:{reference}")
            };
            json!({"ref":qualified})
        }
        Some("resolve_ref") => {
            let defaults = user_defaults();
            let fallback = request["default_provider"]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or(defaults["stage1_provider"].as_str().unwrap());
            resolve_ref(
                request["ref"].as_str().unwrap_or(""),
                &request["providers"],
                fallback,
                request["default_model"].as_str().unwrap_or(""),
            )
        }
        Some("resolve_stage_default") => {
            let settings = &request["user_settings"];
            let stage = request["stage"].as_str().unwrap_or("stage1");
            let model_key = if stage == "vision" {
                "vision_model"
            } else {
                "stage1_model"
            };
            let provider_key = if stage == "vision" {
                "vision_provider"
            } else {
                "stage1_provider"
            };
            let defaults = user_defaults();
            let default_model = defaults[model_key].as_str().unwrap();
            let model = settings[model_key]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or(default_model);
            let provider = settings[provider_key]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or(defaults[provider_key].as_str().unwrap());
            let reference = if split_ref(model, &request["providers"]).0.is_some() {
                model.to_owned()
            } else {
                format!("{provider}:{model}")
            };
            json!({"ref":reference})
        }
        Some("resolve_display") => {
            let reference = request["ref"].as_str().unwrap_or("");
            let providers = &request["providers"];
            let defaults = user_defaults();
            let fallback = request["default_provider"]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or(defaults["stage1_provider"].as_str().unwrap());
            let retired = retired_providers();
            let mut resolved = resolve_ref(reference, providers, fallback, "");
            let explicit = split_ref(reference, providers).0.is_some();
            let owners: Vec<&str> = providers
                .as_object()
                .into_iter()
                .flat_map(|p| p.iter())
                .filter(|(id, _)| id.as_str() != "chatgpt")
                .filter(|(_, p)| p.get("active").map(truthy).unwrap_or(true))
                .filter(|(_, p)| array(p.get("models")).iter().any(|m| m["id"] == reference))
                .map(|(id, _)| id.as_str())
                .collect();
            if !explicit && owners.len() != 1 {
                let previous: Vec<&str> = retired
                    .iter()
                    .filter(|p| array(p.get("models")).iter().any(|m| m["id"] == reference))
                    .filter_map(|p| p["id"].as_str())
                    .collect();
                if previous.len() == 1 {
                    resolved["provider"] = json!(previous[0]);
                }
            }
            let provider = resolved["provider"].as_str().unwrap_or("");
            let model = resolved["model"].as_str().unwrap_or("");
            let selected = providers
                .get(provider)
                .filter(|p| p.is_object())
                .or_else(|| retired.iter().find(|p| p["id"] == provider));
            let provider_label = selected
                .and_then(|p| p["label"].as_str())
                .filter(|s| !s.is_empty())
                .unwrap_or(provider);
            let model_label = selected
                .and_then(|p| array(p.get("models")).iter().find(|m| m["id"] == model))
                .and_then(|m| m["label"].as_str())
                .filter(|s| !s.is_empty())
                .unwrap_or(model);
            json!({"provider":provider,"model":model,"provider_label":provider_label,"model_label":model_label})
        }
        Some("internal") => json!({"model": internal(&request["model"])}),
        Some("label") => json!({"model": labelled(&request["model"], source)}),
        Some("problems") => {
            json!({"problems": problems(request.get("catalog").unwrap_or(source), &provider_order(input))})
        }
        Some("fold") => {
            let selected = array(source.get("labels"))
                .iter()
                .filter_map(|label| label["id"].as_str())
                .rfind(|id| contains(request.get("labels"), id));
            json!({"fold":selected})
        }
        Some("sort") => {
            let purpose = request["purpose"].as_str().unwrap_or("none");
            let stage = request["stage"].as_str().unwrap_or("none");
            if !["none", "llm", "vision"].contains(&purpose)
                || !["none", "stage1", "stage2", "both"].contains(&stage)
            {
                json!({"outcome":"refused", "reason":"invalid_selection"})
            } else {
                let mut models: Vec<_> = array(request.get("models"))
                    .iter()
                    .map(|m| labelled(m, source))
                    .collect();
                models.sort_by_key(|m| {
                    m["selection"]["sort_keys"][purpose][stage]
                        .as_str()
                        .unwrap()
                        .to_owned()
                });
                json!({"models":models})
            }
        }
        _ => json!({"outcome":"refused", "reason":"unknown_action"}),
    };
    let mut output = result.as_object().cloned().unwrap_or_default();
    output.insert("schema".into(), json!("inku.model-catalog.v1"));
    output.entry("outcome").or_insert(json!("ok"));
    serde_json::to_vec(&output).expect("model catalog answer")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chatgpt_policy_matches_frozen_server() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/provider-wire-cases.json"
        ))
        .unwrap();
        for row in array(fixture.get("chatgpt"))
            .iter()
            .filter(|row| row["request"]["schema"] == "inku.model-catalog-request.v1")
        {
            let actual: Value = serde_json::from_slice(&model_catalog_json(
                &serde_json::to_vec(&row["request"]).unwrap(),
            ))
            .unwrap();
            for (key, expected) in row["expect"].as_object().unwrap() {
                assert_eq!(&actual[key], expected, "{}: {key}", row["why"]);
            }
        }
    }

    #[test]
    fn provider_definitions_match_server_baseline() {
        let cases: Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/provider-settings-cases.json"
        ))
        .unwrap();
        assert_eq!(json!(provider_definitions("server")), cases["definitions"]);
        assert_eq!(json!(provider_definitions("macos")), cases["definitions"]);
        assert!(
            provider_definitions("android")
                .iter()
                .all(|provider| provider["id"] != "ollama")
        );
        let android = &cases["android_local"];
        let android_defs = provider_definitions("android");
        assert_eq!(android_defs[0], android["definition"]);
        assert_eq!(android_defs.len(), provider_definitions("server").len());
        let local = json!({"providers":{"local-litert-lm":{"kind":"litert_lm","active":false,
            "models":[android["model"]],"base_url":android["url"],"requires_api_key":true}}});
        let normalized =
            provider_settings::run(&json!({"action":"normalize_settings","host":"android",
            "settings":local,"order":["local-litert-lm"],"env":{}}));
        let row = &normalized["settings"]["providers"]["local-litert-lm"];
        assert_eq!(row["kind"], android["kind"]);
        assert_eq!(row["base_url"], android["url"]);
        assert_eq!(row["active"], true);
        assert_eq!(row["builtin"], true);
        assert_eq!(row["requires_api_key"], false);
        let resolved = resolve_ref(
            android["reference"].as_str().unwrap(),
            &normalized["settings"]["providers"],
            "nvidia",
            "",
        );
        assert_eq!(resolved["provider"], "local-litert-lm");
        assert_eq!(resolved["model"], "gemma-4-e2b");
        let updated = provider_settings::run(&json!({"action":"update_settings","host":"android",
            "settings":normalized["settings"],"order":normalized["order"],"env":{},
            "patch":{"providers":{"local-litert-lm":{"delete":true}}},"patch_order":["local-litert-lm"]}));
        assert_eq!(
            updated["settings"]["providers"]["local-litert-lm"]["active"],
            true
        );
        let connection: Value = serde_json::from_slice(&model_catalog_json(&serde_json::to_vec(&json!({
            "schema":"inku.model-catalog-request.v1","action":"connection","provider":"local-litert-lm","settings":updated["settings"]
        })).unwrap())).unwrap();
        assert_eq!(connection["connection"]["kind"], android["kind"]);
        assert_eq!(connection["connection"]["base_url"], android["url"]);
        let providers = &cases["reference_settings"]["providers"];
        for row in array(cases.get("references")) {
            let reference = row["ref"].as_str().unwrap();
            let (provider, model) = split_ref(reference, providers);
            assert_eq!(json!([provider, model]), row["split"]);
            let resolved = resolve_ref(reference, providers, "nvidia", "google/gemma-4-31b-it");
            assert_eq!(
                json!([resolved["provider"], resolved["model"]]),
                row["stage1"]
            );
        }
        for row in array(cases.get("user_normalization")) {
            assert_eq!(
                normalize_user(&row["input"], &json!(["default"]), "default"),
                row["result"]
            );
        }
        for row in array(cases.get("user_updates")) {
            assert_eq!(
                update_user(&row["input"], &row["patch"], &json!(["default"]), "default"),
                row["result"]
            );
        }
        for row in array(cases.get("models_normalization")) {
            assert_eq!(json!(normalize_models(&row["input"])), row["result"]);
        }
        for row in array(cases.get("normalization")) {
            let order: Vec<String> = row["input"]["providers"]
                .as_object()
                .map(|v| v.keys().cloned().collect())
                .unwrap_or_default();
            let request = json!({"action":"normalize_settings", "settings":row["input"],"order":order,"env":{}});
            assert_eq!(provider_settings::run(&request)["settings"], row["result"]);
            let mut macos = request;
            macos["host"] = json!("macos");
            assert_eq!(provider_settings::run(&macos)["settings"], row["result"]);
        }
        for row in array(cases.get("updates")) {
            let order: Vec<String> = row["patch"]["providers"]
                .as_object()
                .map(|v| v.keys().cloned().collect())
                .unwrap_or_default();
            let request = json!({"action":"update_settings", "settings":row["input"],"patch":row["patch"],"order":[],"patch_order":order,"env":{}});
            assert_eq!(provider_settings::run(&request)["settings"], row["result"]);
            let mut macos = request;
            macos["host"] = json!("macos");
            assert_eq!(provider_settings::run(&macos)["settings"], row["result"]);
        }
        for row in array(cases.get("refresh_cases")) {
            let prepared = model_refresh::run(
                &json!({"action":"refresh_prepare","provider":row["provider"],"models":row["models"],"previous":row["previous"]}),
            );
            let finished = model_refresh::run(
                &json!({"action":"refresh_finish","models":prepared["models"],"previous":row["previous"],"today":row["today"]}),
            );
            assert_eq!(finished, row["result"]);
        }
        for row in array(cases.get("access_cases")) {
            let answer = model_refresh::run(
                &json!({"action":"access_probe", "stage":row["stage"],"status":row["status"],"text":row["text"],"today":row["today"]}),
            );
            assert_eq!(answer["answer"], row["answer"]);
        }
        let rows =
            json!([{"id":"a","requires_subscription":true},{"id":"b"},{"id":"old","eol":true}]);
        let targets = model_refresh::run(&json!({"action":"access_targets","models":rows}));
        assert_eq!(targets["models"].as_array().unwrap().len(), 2);
        let applied = model_refresh::run(
            &json!({"action":"access_apply","models":rows,"answers":[{"subscription":false},{"retired":"2026-10-28"}]}),
        );
        assert!(applied["models"][0].get("requires_subscription").is_none());
        assert_eq!(applied["models"][1]["eol_date"], "2026-10-28");
        for row in array(cases.get("validation_cases")) {
            let mut request = row["input"].as_object().unwrap().clone();
            request.insert("action".into(), json!("validate_settings"));
            assert_eq!(
                provider_settings::run(&Value::Object(request)),
                row["result"]
            );
        }
        for row in array(cases.get("resolution_cases")) {
            let result = resolve_ref(
                row["ref"].as_str().unwrap(),
                &row["settings"]["providers"],
                row["settings"]["stage1_provider"].as_str().unwrap(),
                row["settings"]["stage1_model"].as_str().unwrap(),
            );
            assert_eq!(json!([result["provider"], result["model"]]), row["result"]);
        }
        for row in array(cases.get("fetch_plan_cases")) {
            let request = json!({"schema":"inku.model-catalog-request.v1","action":"model_list_start","kind":row["kind"],"base_url":row["base_url"],"api_key":row["api_key"]});
            let actual: Value =
                serde_json::from_slice(&model_catalog_json(&serde_json::to_vec(&request).unwrap()))
                    .unwrap();
            for key in ["url", "headers", "items_key", "query"] {
                assert_eq!(actual[key], row[key]);
            }
            let request = json!({"schema":"inku.model-catalog-request.v1","action":"model_list_next","kind":row["kind"],"page":row["next_page"]});
            let actual: Value =
                serde_json::from_slice(&model_catalog_json(&serde_json::to_vec(&request).unwrap()))
                    .unwrap();
            assert_eq!(actual["query"], row["next_query"]);
        }
    }

    #[test]
    fn shared_catalog_cases_keep_labels_and_picker_decisions() {
        let cases: Value =
            serde_json::from_str(include_str!("../data/model-catalog-cases.json")).unwrap();
        let source = catalog();
        assert_eq!(array(cases.get("cases")).len(), 15);
        for row in array(cases.get("cases")) {
            let model = internal(&row["model"]);
            let result = labelled(&model, source);
            assert_eq!(result["labels"], row["labels"], "{}", row["name"]);
            assert_eq!(result["fold"], row["fold"], "{}", row["name"]);
            assert_eq!(
                !result["selection"]["unselectable"].as_bool().unwrap(),
                row["publishable"]
            );
        }
        for row in array(cases.get("selection_cases")) {
            let result = labelled(&row["model"], source);
            let p = row["purpose"].as_str().unwrap();
            let s = row["stage"].as_str().unwrap();
            assert_eq!(result["selection"]["unselectable"], row["unselectable"]);
            assert_eq!(result["selection"]["unsupported"][p], row["unsupported"]);
            assert_eq!(
                result["selection"]["levels"][p][s].as_f64(),
                row["level"].as_f64()
            );
        }
        for row in array(cases.get("sort_cases")) {
            let mut models: Vec<_> = array(row.get("models"))
                .iter()
                .map(|m| labelled(m, source))
                .collect();
            models.sort_by_key(|m| {
                m["selection"]["sort_keys"]["llm"]["none"]
                    .as_str()
                    .unwrap()
                    .to_owned()
            });
            let ids: Vec<_> = models.iter().map(|m| m["id"].as_str().unwrap()).collect();
            assert_eq!(json!(ids), row["order"]);
        }
        for row in array(cases.get("problem_cases")) {
            let order: Vec<String> = array(row.get("provider_order"))
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect();
            assert_eq!(json!(problems(&row["catalog"], &order)), row["problems"]);
        }
        assert!(problems(source, &[]).is_empty());
    }
}
