//! Shared interpretation of saved draw options and per-tab defaults.
use crate::model_catalog::{draw_option_providers, qualify_ref, split_ref};
use serde_json::{Map, Value, json};

/// The complete set of draw options and whether each has an off state.
pub const DRAW_OPTIONS: &[(&str, bool)] = &[
    ("route", false),
    ("sketch", true),
    ("composition", true),
    ("wild", true),
    ("catalog", false),
    ("canvas_aspect", false),
    ("models", false),
];
const TABS: &[&str] = &["describe", "image", "batch_text", "batch_image"];

fn image_tab(tab: &str) -> bool {
    matches!(tab, "image" | "batch_image")
}
fn text(value: &Value) -> Option<&str> {
    value.as_str().map(str::trim).filter(|s| !s.is_empty())
}
fn field<'a>(record: &'a Value, first: &str, fallback: &str) -> &'a Value {
    record
        .get(first)
        .filter(|v| !v.is_null())
        .unwrap_or(&record[fallback])
}
fn toggle(value: &Value) -> Value {
    match value.as_str() {
        Some("1") => json!("on"),
        Some("0") => json!("off"),
        _ => Value::Null,
    }
}

/// Read only recorded facts; do not infer missing options from the DDL.
#[must_use]
pub fn options_of_work(record: &Value) -> Value {
    let mut out: Map<String, Value> = DRAW_OPTIONS
        .iter()
        .map(|(key, _)| ((*key).into(), Value::Null))
        .collect();
    out.insert(
        "route".into(),
        record["draw_route"]
            .as_str()
            .filter(|s| ["read_and_draw", "stages"].contains(s))
            .map_or(Value::Null, |s| json!(s)),
    );
    for (key, source) in [
        ("sketch", "sketch_requested"),
        ("composition", "composition_requested"),
        ("wild", "render_wild"),
    ] {
        out.insert(key.into(), toggle(&record[source]));
    }
    let id = text(field(record, "render_color_catalog_id", "catalog_id"));
    let mode = record["catalog_mode"]
        .as_str()
        .filter(|s| ["fixed", "auto", "random"].contains(s));
    if id.is_some() || mode.is_some() {
        out.insert("catalog".into(), json!({"id":id,"mode":mode}));
    }
    if let Some(aspect) = text(field(
        record,
        "render_canvas_aspect_id",
        "render_canvas_aspect",
    )) {
        out.insert("canvas_aspect".into(), json!(aspect));
    }
    let stage1 = text(&record["stage1_model"]);
    let stage2 = text(&record["stage2_model"]);
    if !record["image_ddl"].is_null() {
        if stage1.is_some() {
            out.insert("models".into(), json!({"vision":stage1}));
        }
    } else if stage1.is_some() || stage2.is_some() {
        out.insert("models".into(), json!({"stage1":stage1,"stage2":stage2}));
    }
    Value::Object(out)
}

/// Build defaults from existing user model and color settings.
#[must_use]
pub fn default_draw_defaults(user: &Value) -> Value {
    let providers = draw_option_providers(user);
    let stage1 = qualify_ref(
        text(&user["stage1_provider"]).unwrap_or("nvidia"),
        text(&user["stage1_model"]).unwrap_or("google/gemma-4-31b-it"),
        &providers,
    );
    let vision = qualify_ref(
        text(&user["vision_provider"]).unwrap_or("nvidia"),
        text(&user["vision_model"]).unwrap_or("meta/llama-3.2-90b-vision-instruct"),
        &providers,
    );
    let color = text(&user["color_catalog_id"]).unwrap_or("default");
    let mut tabs = Map::new();
    for &tab in TABS {
        let image = image_tab(tab);
        tabs.insert(tab.into(), json!({"route":"read_and_draw", "sketch":"on", "composition":"off", "wild":"off",
            "catalog":{"id":color,"mode":if color == "auto" {"auto"} else {"fixed"}},
            "canvas_aspect":if image {"image"} else {"square"},
            "models":if image {json!({"vision":vision})} else {json!({"stage1":stage1,"stage2":stage1})}}));
    }
    Value::Object(tabs)
}

fn valid_string<'a>(value: &'a Value, valid: &[&str]) -> Option<&'a str> {
    value.as_str().filter(|s| valid.contains(s))
}

fn model_ref(value: &Value, user: &Value, image: bool, providers: &Value) -> Option<String> {
    let candidate = text(value)?;
    if split_ref(candidate, providers).0.is_some() {
        return Some(candidate.to_owned());
    }
    let (model_key, provider_key) = if image {
        ("vision_model", "vision_provider")
    } else {
        ("stage1_model", "stage1_provider")
    };
    if text(&user[model_key]) == Some(candidate) {
        return text(&user[provider_key])
            .map(|provider| qualify_ref(provider, candidate, providers));
    }
    let owners: Vec<&str> = providers
        .as_object()?
        .iter()
        .filter(|(_, row)| {
            row["models"].as_array().is_some_and(|models| {
                models
                    .iter()
                    .any(|model| model["id"].as_str() == Some(candidate))
            })
        })
        .map(|(id, _)| id.as_str())
        .collect();
    if owners.len() == 1 {
        Some(qualify_ref(owners[0], candidate, providers))
    } else {
        None
    }
}

/// Normalize each field separately, using the provided existing user settings as fallback.
#[must_use]
pub fn normalize_draw_defaults(input: &Value, user: &Value, color_ids: &Value) -> Value {
    let mut result = default_draw_defaults(user);
    let providers = draw_option_providers(user);
    for &tab in TABS {
        let source = &input[tab];
        for &(key, on_off) in DRAW_OPTIONS {
            let value = &source[key];
            if on_off {
                if let Some(v) = valid_string(value, &["on", "off"]) {
                    result[tab][key] = json!(v);
                }
            } else {
                match key {
                    "route" => {
                        if let Some(v) = valid_string(value, &["read_and_draw", "stages"]) {
                            result[tab][key] = json!(v);
                        }
                    }
                    "canvas_aspect" => {
                        if let Some(v) = text(value).filter(|v| {
                            *v == "image" || inku_score::validate_canvas_format_id(v).is_ok()
                        }) {
                            result[tab][key] = json!(v);
                        }
                    }
                    "catalog" => {
                        let id = text(&value["id"]).filter(|id| {
                            *id == "auto"
                                || color_ids
                                    .as_array()
                                    .is_none_or(|ids| ids.iter().any(|v| v.as_str() == Some(id)))
                        });
                        let mode = valid_string(&value["mode"], &["auto", "fixed"]);
                        if let (Some(id), Some(mode)) = (id, mode) {
                            result[tab][key] = json!({"id":id,"mode":mode});
                        }
                    }
                    "models" => {
                        let model = if image_tab(tab) { "vision" } else { "stage1" };
                        if let Some(v) = model_ref(&value[model], user, image_tab(tab), &providers)
                        {
                            result[tab][key][model] = json!(v);
                        }
                        if !image_tab(tab) {
                            result[tab][key]["stage2"] = result[tab][key]["stage1"].clone();
                        }
                    }
                    _ => {}
                }
            }
        }
    }
    result
}

/// Combine recorded values with the specified tab's defaults without changing them.
#[must_use]
pub fn options_for_tab(record: &Value, tab: &str, defaults: &Value) -> Option<Value> {
    if !TABS.contains(&tab) {
        return None;
    }
    let defaults = if defaults.get(tab).is_some() {
        &defaults[tab]
    } else {
        defaults
    };
    let mut result = Map::new();
    let work = options_of_work(record);
    for &(key, on_off) in DRAW_OPTIONS {
        let value = &work[key];
        let mut selected = if value.is_null() {
            if on_off {
                json!("off")
            } else {
                defaults[key].clone()
            }
        } else {
            value.clone()
        };
        if key == "catalog" || key == "models" {
            let names: &[&str] = if key == "catalog" {
                &["id", "mode"]
            } else if image_tab(tab) {
                &["vision"]
            } else {
                &["stage1", "stage2"]
            };
            let mut fields = Map::new();
            for name in names {
                let v = selected
                    .get(*name)
                    .filter(|v| !v.is_null())
                    .unwrap_or(&defaults[key][*name]);
                fields.insert((*name).into(), v.clone());
            }
            selected = Value::Object(fields);
        }
        if key == "catalog" && selected["mode"] == "random" {
            selected["mode"] = json!("fixed");
        }
        result.insert(key.into(), selected);
    }
    Some(Value::Object(result))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model_catalog::model_catalog_json;

    fn call(mut request: Value) -> Value {
        request["schema"] = json!("inku.model-catalog-request.v1");
        serde_json::from_slice(&model_catalog_json(&serde_json::to_vec(&request).unwrap())).unwrap()
    }

    #[test]
    fn all_registered_options_distinguish_recorded_missing_and_tab_defaults() {
        let record = json!({"draw_route":"stages", "sketch_requested":"1", "composition_requested":"0", "render_wild":"1",
            "render_color_catalog_id":"ink", "catalog_mode":"random", "render_canvas_aspect_id":"a4",
            "stage1_model":"first", "stage2_model":"second"});
        let expected = json!({"route":"stages", "sketch":"on", "composition":"off", "wild":"on",
            "catalog":{"id":"ink","mode":"random"}, "canvas_aspect":"a4", "models":{"stage1":"first","stage2":"second"}});
        let defaults = call(json!({"action":"default_draw_defaults"}))["draw_defaults"].clone();
        let actual = call(json!({"action":"options_of_work","record":record}));
        let missing = call(json!({"action":"options_of_work","record":{}}));
        let adopted = call(
            json!({"action":"options_for_tab","record":{},"tab":"describe","defaults":defaults}),
        );
        let present = call(
            json!({"action":"options_for_tab","record":record,"tab":"describe","defaults":defaults}),
        );
        assert_eq!(
            actual["options"].as_object().unwrap().len(),
            DRAW_OPTIONS.len()
        );
        for &(key, on_off) in DRAW_OPTIONS {
            assert!(!expected[key].is_null(), "test fixture missing {key}");
            assert_eq!(actual["options"][key], expected[key], "{key}");
            assert!(missing["options"][key].is_null(), "{key}");
            assert_eq!(
                adopted["options"][key],
                if on_off {
                    json!("off")
                } else {
                    defaults["describe"][key].clone()
                },
                "{key}"
            );
            assert_eq!(
                present["options"][key],
                if key == "catalog" {
                    json!({"id":"ink","mode":"fixed"})
                } else {
                    expected[key].clone()
                },
                "{key}"
            );
        }
        let image = json!({"image_ddl":"image", "stage1_model":"vision-model", "catalog_id":"ink", "catalog_mode":"fixed", "render_canvas_aspect":"wide"});
        assert_eq!(
            options_of_work(&image)["models"],
            json!({"vision":"vision-model"})
        );
        assert_eq!(
            options_for_tab(&image, "batch_image", &defaults).unwrap()["models"],
            json!({"vision":"vision-model"})
        );
        assert_eq!(options_of_work(&image)["canvas_aspect"], "wide");
        assert_eq!(
            options_of_work(&image)["catalog"],
            json!({"id":"ink","mode":"fixed"})
        );
        let partial = options_for_tab(
            &json!({"stage1_model":"kept", "catalog_id":"ink"}),
            "describe",
            &defaults,
        )
        .unwrap();
        assert_eq!(partial["models"]["stage1"], "kept");
        assert_eq!(
            partial["models"]["stage2"],
            defaults["describe"]["models"]["stage2"]
        );
        assert_eq!(partial["catalog"]["id"], "ink");
        assert_eq!(
            partial["catalog"]["mode"],
            defaults["describe"]["catalog"]["mode"]
        );
        assert_eq!(
            call(json!({"action":"options_for_tab","tab":"unknown"}))["reason"],
            "invalid_tab"
        );
    }

    #[test]
    fn user_migration_normalization_and_update_keep_tab_defaults() {
        let legacy = json!({"stage1_model":"first", "stage2_model":"second", "vision_model":"vision", "color_catalog_id":"auto"});
        let normalized = call(
            json!({"action":"normalize_user","settings":legacy,"color_ids":["default","ink"]}),
        );
        for &tab in TABS {
            let d = &normalized["settings"]["draw_defaults"][tab];
            assert_eq!(d.as_object().unwrap().len(), DRAW_OPTIONS.len());
            assert_eq!(d["catalog"], json!({"id":"auto","mode":"auto"}));
            assert_eq!(
                d["models"],
                if image_tab(tab) {
                    json!({"vision":"nvidia:vision"})
                } else {
                    json!({"stage1":"nvidia:first","stage2":"nvidia:first"})
                }
            );
            assert_eq!(
                d["canvas_aspect"],
                if image_tab(tab) { "image" } else { "square" }
            );
        }
        let custom = json!({"describe":{"route":"stages", "sketch":"bad", "composition":"on", "wild":"on", "catalog":{"id":"ink","mode":"fixed"}, "canvas_aspect":"a4", "models":{"stage1":"openai:custom", "stage2":""}}, "image":{"canvas_aspect":"not-a-format"}});
        let clean = call(
            json!({"action":"normalize_draw_defaults","draw_defaults":custom,"color_ids":["default","ink"]}),
        );
        let d = &clean["draw_defaults"]["describe"];
        assert_eq!(d["route"], "stages");
        assert_eq!(d["sketch"], "on");
        assert_eq!(d["composition"], "on");
        assert_eq!(d["catalog"]["id"], "ink");
        assert_eq!(d["canvas_aspect"], "a4");
        assert_eq!(d["models"]["stage1"], "openai:custom");
        assert_eq!(d["models"]["stage2"], "openai:custom");
        assert_eq!(clean["draw_defaults"]["image"]["canvas_aspect"], "image");
        let updated = call(
            json!({"action":"update_user","settings":normalized["settings"],"color_ids":["default","ink"],"patch":{"draw_defaults":clean["draw_defaults"]}}),
        );
        assert_eq!(updated["settings"]["draw_defaults"], clean["draw_defaults"]);
    }

    #[test]
    fn models_are_qualified_and_unresolvable_names_fall_back() {
        let user = json!({"stage1_provider":"openai","stage1_model":"same", "vision_provider":"gemini", "vision_model":"same"});
        let defaults = default_draw_defaults(&user);
        assert_eq!(
            defaults["describe"]["models"],
            json!({"stage1":"openai:same","stage2":"openai:same"})
        );
        assert_eq!(defaults["image"]["models"], json!({"vision":"gemini:same"}));
        let input = json!({"describe":{"models":{"stage1":"same", "stage2":"gemini:other"}}, "image":{"models":{"vision":"unresolvable-model"}}, "batch_text":{"models":{"stage1":"ollama:chosen","stage2":"broken"}}});
        let normalized = normalize_draw_defaults(&input, &user, &Value::Null);
        assert_eq!(
            normalized["describe"]["models"],
            json!({"stage1":"openai:same","stage2":"openai:same"})
        );
        assert_eq!(
            normalized["image"]["models"],
            json!({"vision":"gemini:same"})
        );
        assert_eq!(
            normalized["batch_text"]["models"],
            json!({"stage1":"ollama:chosen","stage2":"ollama:chosen"})
        );
    }
}
