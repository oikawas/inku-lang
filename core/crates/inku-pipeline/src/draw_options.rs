//! Shared interpretation of saved draw options and per-tab defaults.
use crate::model_catalog::{draw_option_providers, qualify_ref, split_ref};
use serde_json::{Map, Value, json};
use std::sync::OnceLock;

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

/// The first drawing options a new user gets. The release decides them: the
/// release procedure shows this file to the author and records the version
/// it was reviewed for (`scripts/release-defaults.py`).
const RELEASE_DEFAULTS: &str = include_str!("../data/release-defaults.json");

/// The release file as shipped: `schema`, `reviewed_for_version` and `tabs`.
#[must_use]
pub fn release_defaults() -> &'static Value {
    static PARSED: OnceLock<Value> = OnceLock::new();
    PARSED
        .get_or_init(|| serde_json::from_str(RELEASE_DEFAULTS).expect("embedded release defaults"))
}

/// The release's per-tab defaults, before any user's own choices.
#[must_use]
pub fn release_draw_defaults() -> Value {
    release_defaults()["tabs"].clone()
}

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

/// The legacy model and color settings a release fills in for a user who
/// never chose them: the describe tab's drawing model and catalog and the
/// image tab's vision model.
#[must_use]
pub fn release_legacy_settings() -> Value {
    let tabs = release_draw_defaults();
    let providers = draw_option_providers(&Value::Null);
    let split = |reference: &str| {
        let (provider, model) = split_ref(reference, &providers);
        (provider.unwrap_or("").to_owned(), model.to_owned())
    };
    let (stage1_provider, stage1_model) =
        split(tabs["describe"]["models"]["stage1"].as_str().unwrap_or(""));
    let (vision_provider, vision_model) =
        split(tabs["image"]["models"]["vision"].as_str().unwrap_or(""));
    let catalog = &tabs["describe"]["catalog"];
    let color = if catalog["mode"] == "auto" {
        "auto"
    } else {
        catalog["id"].as_str().unwrap_or("default")
    };
    json!({"stage1_provider":stage1_provider, "stage1_model":stage1_model,
        "stage2_provider":stage1_provider, "stage2_model":stage1_model,
        "vision_provider":vision_provider, "vision_model":vision_model, "color_catalog_id":color})
}

/// The legacy model a user chose themselves, qualified. A value equal to the
/// release's fill-in is not a choice: older builds saved the filled value
/// whenever any setting was saved.
fn chosen_model(user: &Value, image: bool, providers: &Value) -> Option<String> {
    let (provider_key, model_key) = if image {
        ("vision_provider", "vision_model")
    } else {
        ("stage1_provider", "stage1_model")
    };
    let model = text(&user[model_key])?;
    let legacy = release_legacy_settings();
    // A stored model without its provider was read with the filled provider,
    // as `normalize_user` reads it.
    let provider = text(&user[provider_key]).unwrap_or(legacy[provider_key].as_str().unwrap_or(""));
    let reference = qualify_ref(provider, model, providers);
    split_ref(&reference, providers).0?;
    let fill = qualify_ref(
        legacy[provider_key].as_str().unwrap_or(""),
        legacy[model_key].as_str().unwrap_or(""),
        providers,
    );
    (reference != fill).then_some(reference)
}

/// Build defaults from the release, with the model and color catalog a user
/// saved themselves in the legacy settings laid over it. `user` is the stored
/// settings before normalization, so a value the normalizer filled in is not
/// taken for the user's choice.
#[must_use]
pub fn default_draw_defaults(user: &Value) -> Value {
    let mut tabs = release_draw_defaults();
    let providers = draw_option_providers(user);
    let stage1 = chosen_model(user, false, &providers);
    let vision = chosen_model(user, true, &providers);
    let color = text(&user["color_catalog_id"])
        .filter(|color| *color != release_legacy_settings()["color_catalog_id"]);
    for &tab in TABS {
        if image_tab(tab) {
            if let Some(vision) = &vision {
                tabs[tab]["models"] = json!({"vision":vision});
            }
        } else if let Some(stage1) = &stage1 {
            tabs[tab]["models"] = json!({"stage1":stage1,"stage2":stage1});
        }
        if let Some(color) = color {
            tabs[tab]["catalog"] = if color == "auto" {
                json!({"id":tabs[tab]["catalog"]["id"].clone(),"mode":"auto"})
            } else {
                json!({"id":color,"mode":"fixed"})
            };
        }
    }
    tabs
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
    let known = |id: &str| {
        id == "auto"
            || color_ids
                .as_array()
                .is_none_or(|ids| ids.iter().any(|v| v.as_str() == Some(id)))
    };
    let release = release_draw_defaults();
    for &tab in TABS {
        // A legacy catalog the server no longer has falls back to the release's.
        if !result[tab]["catalog"]["id"].as_str().is_some_and(known) {
            result[tab]["catalog"] = release[tab]["catalog"].clone();
        }
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
    options_for_recorded(&options_of_work(record), tab, defaults)
}

/// The same as [`options_for_tab`], from options already read with
/// [`options_of_work`] (what the history API returns as `draw_options`).
#[must_use]
pub fn options_for_recorded(work: &Value, tab: &str, defaults: &Value) -> Option<Value> {
    if !TABS.contains(&tab) {
        return None;
    }
    let defaults = if defaults.get(tab).is_some() {
        &defaults[tab]
    } else {
        defaults
    };
    let mut result = Map::new();
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
            assert_eq!(d["catalog"]["mode"], "auto");
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
    fn the_release_file_names_every_option_for_every_tab() {
        let release = release_defaults();
        assert_eq!(release["schema"], "inku.release-draw-defaults.v1");
        assert!(release["reviewed_for_version"].is_string());
        let tabs = release["tabs"].as_object().unwrap();
        assert_eq!(tabs.len(), TABS.len());
        for &tab in TABS {
            let options = tabs[tab].as_object().unwrap();
            let keys: Vec<&str> = options.keys().map(String::as_str).collect();
            for &(key, _) in DRAW_OPTIONS {
                assert!(keys.contains(&key), "{tab} lacks {key}");
            }
            assert_eq!(
                options.len(),
                DRAW_OPTIONS.len(),
                "{tab} has an unknown key"
            );
        }
        // The file survives the core's own validation unchanged.
        let ids = json!(["default"]);
        assert_eq!(
            normalize_draw_defaults(&release_draw_defaults(), &Value::Null, &ids),
            release_draw_defaults()
        );
    }

    #[test]
    fn a_new_user_gets_the_release_and_a_saved_choice_is_kept() {
        let ids = json!(["default", "ink"]);
        let new_user = call(json!({"action":"normalize_user","settings":{},"color_ids":ids}));
        assert_eq!(
            new_user["settings"]["draw_defaults"],
            release_draw_defaults()
        );
        // Older builds stored the filled values on any save; those are not choices.
        let legacy = release_legacy_settings();
        let filled = call(json!({"action":"normalize_user","settings":legacy,"color_ids":ids}));
        assert_eq!(filled["settings"]["draw_defaults"], release_draw_defaults());
        let chose = call(
            json!({"action":"normalize_user","settings":{"stage1_provider":"openai","stage1_model":"chosen","color_catalog_id":"ink"},"color_ids":ids}),
        );
        let d = &chose["settings"]["draw_defaults"];
        for &tab in TABS {
            assert_eq!(
                d[tab]["catalog"],
                json!({"id":"ink","mode":"fixed"}),
                "{tab}"
            );
            if image_tab(tab) {
                assert_eq!(
                    d[tab]["models"],
                    release_draw_defaults()[tab]["models"],
                    "{tab}"
                );
            } else {
                assert_eq!(
                    d[tab]["models"],
                    json!({"stage1":"openai:chosen","stage2":"openai:chosen"}),
                    "{tab}"
                );
            }
            assert_eq!(
                d[tab]["sketch"],
                release_draw_defaults()[tab]["sketch"],
                "{tab}"
            );
        }
        let retired = call(
            json!({"action":"normalize_user","settings":{"color_catalog_id":"retired"},"color_ids":ids}),
        );
        assert_eq!(
            retired["settings"]["draw_defaults"],
            release_draw_defaults()
        );
    }

    #[test]
    fn saving_one_setting_stores_no_defaults_and_a_partial_patch_keeps_the_rest() {
        let ids = json!(["default", "ink"]);
        let saved = call(
            json!({"action":"update_user","settings":{},"patch":{"ui_text_size":2},"color_ids":ids}),
        );
        let stored = saved["settings"].as_object().unwrap();
        assert!(!stored.contains_key("draw_defaults"));
        for key in [
            "stage1_model",
            "stage2_model",
            "vision_model",
            "color_catalog_id",
        ] {
            assert!(!stored.contains_key(key), "{key}");
        }
        assert_eq!(stored["ui_text_size"], 2);
        let mut defaults = release_draw_defaults();
        defaults["describe"]["wild"] = json!("on");
        let first = call(
            json!({"action":"update_user","settings":{},"patch":{"draw_defaults":defaults},"color_ids":ids}),
        );
        assert_eq!(first["settings"]["draw_defaults"]["describe"]["wild"], "on");
        let partial = call(
            json!({"action":"update_user","settings":first["settings"],"patch":{"draw_defaults":{"batch_text":{"composition":"on"}}},"color_ids":ids}),
        );
        let d = &partial["settings"]["draw_defaults"];
        assert_eq!(d["describe"]["wild"], "on");
        assert_eq!(d["batch_text"]["composition"], "on");
        assert_eq!(
            d["batch_text"]["wild"],
            release_draw_defaults()["batch_text"]["wild"]
        );
        let model = call(
            json!({"action":"update_user","settings":{},"patch":{"stage1_provider":"openai","stage1_model":"chosen"},"color_ids":ids}),
        );
        assert_eq!(model["settings"]["stage1_model"], "chosen");
        assert_eq!(model["settings"]["stage2_model"], "chosen");
        assert!(model["settings"].get("vision_model").is_none());
    }

    #[test]
    fn recorded_options_adopt_as_the_raw_record_does() {
        let record = json!({"draw_route":"stages", "sketch_requested":"0", "render_wild":"1", "catalog_id":"ink", "catalog_mode":"auto"});
        let defaults = release_draw_defaults();
        for &tab in TABS {
            assert_eq!(
                options_for_recorded(&options_of_work(&record), tab, &defaults),
                options_for_tab(&record, tab, &defaults),
                "{tab}"
            );
        }
        let answer = call(
            json!({"action":"options_for_recorded","options":options_of_work(&record),"tab":"describe","defaults":defaults}),
        );
        assert_eq!(answer["options"]["route"], "stages");
        assert_eq!(answer["options"]["composition"], "off");
        assert_eq!(
            call(json!({"action":"options_for_recorded","tab":"nope"}))["reason"],
            "invalid_tab"
        );
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
