use super::*;

fn limits(value: &Value, id: &str) -> Value {
    let defaults = if id == "gemini" {
        [30, 16000, 14400]
    } else {
        [0, 0, 0]
    };
    let out: Map<String, Value> = ["rpm", "tpm", "rpd"]
        .into_iter()
        .zip(defaults)
        .map(|(k, d)| {
            (
                k.into(),
                json!(
                    value[k]
                        .as_i64()
                        .filter(|v| (0..=1_000_000_000).contains(v))
                        .unwrap_or(d)
                ),
            )
        })
        .collect();
    json!(out)
}
fn url(id: &str, value: &str, definitions: &[Value]) -> String {
    let value = value.trim().trim_end_matches('/');
    if id == "openai"
        && [
            "http://127.0.0.1:18000/v3",
            "http://localhost:18000/v3",
            "http://localhost:8000/v3",
        ]
        .contains(&value)
    {
        return definitions.iter().find(|p| p["id"] == "openai").unwrap()["default_base_url"]
            .as_str()
            .unwrap()
            .to_owned();
    }
    value.to_owned()
}
fn model_id(model: &Value) -> &str {
    model["id"].as_str().unwrap_or("")
}
fn merge_row(rows: &mut Vec<Value>, row: Value) {
    if let Some(pos) = rows
        .iter()
        .position(|item| model_id(item) == model_id(&row))
    {
        rows[pos] = row;
    } else {
        rows.push(row);
    }
}
fn chatgpt(stored: &Value, moved: bool) -> Vec<Value> {
    let mut known = normalize_models(&json!(
        array(catalog()["providers"]["chatgpt"].get("models"))
            .iter()
            .map(internal)
            .collect::<Vec<_>>()
    ));
    let mut own = normalize_models(stored);
    for row in known.iter_mut().chain(own.iter_mut()) {
        row.as_object_mut().unwrap().remove("purposes");
    }
    let (mut result, overlay) = if moved { (own, known) } else { (known, own) };
    for row in overlay {
        merge_row(&mut result, row);
    }
    result
}
fn definitions(host: &str) -> Vec<Value> {
    provider_definitions(host)
}
fn defaults(env: &Value, host: &str) -> (Value, Vec<String>) {
    let definitions = definitions(host);
    let mut providers = Map::new();
    let mut order = Vec::new();
    for definition in &definitions {
        let id = definition["id"].as_str().unwrap();
        order.push(id.to_owned());
        let mut out = Map::new();
        for key in [
            "id",
            "label",
            "kind",
            "api_key_env",
            "base_url_env",
            "default_base_url",
            "requires_api_key",
        ] {
            out.insert(key.into(), definition[key].clone());
        }
        out.insert("memo".into(), json!(""));
        out.insert("rate_limits".into(), limits(&Value::Null, id));
        out.insert(
            "models".into(),
            json!(normalize_models(&definition["models"])),
        );
        out.insert("builtin".into(), json!(true));
        out.insert("active".into(), json!(true));
        let base_key = definition["base_url_env"].as_str().unwrap();
        let raw_base = env
            .get(base_key)
            .and_then(Value::as_str)
            .unwrap_or(definition["default_base_url"].as_str().unwrap());
        out.insert("base_url".into(), json!(url(id, raw_base, &definitions)));
        out.insert(
            "api_key".into(),
            json!(
                env.get(definition["api_key_env"].as_str().unwrap())
                    .and_then(Value::as_str)
                    .unwrap_or("")
            ),
        );
        let enabled: Map<String, Value> = array(definition.get("models"))
            .iter()
            .map(|m| (model_id(m).to_owned(), json!(true)))
            .collect();
        out.insert("enabled_models".into(), json!(enabled));
        providers.insert(id.into(), Value::Object(out));
    }
    (
        json!({"model_catalog_version":info()["version"],"chatgpt_models":chatgpt(&Value::Null,true),"providers":providers}),
        order,
    )
}
fn sanitize_id(value: &str) -> String {
    value
        .trim()
        .to_lowercase()
        .chars()
        .filter(|c| c.is_alphanumeric() || *c == '_' || *c == '-')
        .collect()
}
fn kind<'a>(value: &'a Value, host: &str) -> &'a str {
    value
        .as_str()
        .filter(|v| {
            ["openai_compatible", "mlx", "anthropic", "gemini"].contains(v)
                || (host == "android" && *v == "litert_lm")
        })
        .unwrap_or("openai_compatible")
}
pub(super) const METADATA: &[&str] = &[
    "purposes",
    "unsupported_purposes",
    "not_supported",
    "legacy",
    "recommendation_llm",
    "recommendation_vision",
    "recommendation_stage1",
    "recommendation_stage2",
    "recommendation_level",
    "speed_class",
    "speed_label",
    "cost_usd_llm",
    "cost_usd_vision",
    "speed_llm_seconds",
    "speed_vision_seconds",
    "comment_ja",
    "comment_en",
    "eol",
    "eol_date",
    "notes",
];
fn normalize(input: &Value, env: &Value, input_order: &Value, host: &str) -> (Value, Vec<String>) {
    let definitions = definitions(host);
    let (mut clean, mut order) = defaults(env, host);
    if !input.is_object() {
        return (clean, order);
    }
    let moved = input["model_catalog_version"].as_str().unwrap_or("")
        != info()["version"].as_str().unwrap();
    clean["chatgpt_models"] = json!(chatgpt(&input["chatgpt_models"], moved));
    let incoming_providers = &input["providers"];
    for raw_id in array(Some(input_order)).iter().filter_map(Value::as_str) {
        let incoming = &incoming_providers[raw_id];
        let id = sanitize_id(raw_id);
        if id.is_empty()
            || !incoming.is_object()
            || retired_providers().iter().any(|p| p["id"] == id)
            || id == "chatgpt"
        {
            continue;
        }
        let builtin = definitions.iter().find(|d| d["id"] == id);
        let existed = clean["providers"].get(&id).is_some();
        let mut provider = clean["providers"].get(&id).cloned().unwrap_or_else(|| json!({"id":id,"label":id,"kind":"openai_compatible","api_key_env":"","base_url_env":"","default_base_url":"","requires_api_key":false,"memo":"","models":[],"builtin":false,"active":true,"base_url":"","api_key":"","enabled_models":{}}));
        if incoming["delete"] == true {
            if host == "android" && id == "local-litert-lm" {
                continue;
            }
            if truthy(&provider["builtin"]) {
                provider["active"] = json!(false);
                clean["providers"][&id] = provider;
            } else {
                clean["providers"].as_object_mut().unwrap().remove(&id);
                order.retain(|x| x != &id);
            }
            continue;
        }
        if !incoming["active"].is_null() {
            provider["active"] = json!(truthy(&incoming["active"]));
        } else if !existed {
            provider["active"] = json!(true);
        }
        if let Some(label) = incoming["label"]
            .as_str()
            .map(str::trim)
            .filter(|s| !s.is_empty())
        {
            provider["label"] = json!(label);
        } else if let Some(builtin) = builtin {
            provider["label"] = builtin["label"].clone();
        }
        if !incoming["kind"].is_null() {
            provider["kind"] = json!(kind(&incoming["kind"], host));
        }
        for key in ["api_key_env", "base_url_env", "memo"] {
            if let Some(v) = incoming[key].as_str() {
                provider[key] = json!(v.trim());
            }
        }
        if let Some(base) = incoming["default_base_url"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
        {
            provider["default_base_url"] = json!(url(&id, base, &definitions));
        }
        if !incoming["requires_api_key"].is_null() {
            provider["requires_api_key"] = json!(truthy(&incoming["requires_api_key"]));
        }
        provider["rate_limits"] = limits(&incoming["rate_limits"], &id);
        let models = normalize_models(&incoming["models"]);
        if !models.is_empty() {
            let builtin_models = array(provider.get("models")).to_vec();
            let in_catalog = catalog()["providers"].get(&id).is_some();
            if (builtin.is_some() || in_catalog) && (id == "nvidia" || moved) {
                let mut merged = if id == "nvidia" {
                    builtin_models.clone()
                } else {
                    Vec::new()
                };
                for model in models {
                    let model_id = model_id(&model);
                    let known_builtin = builtin_models
                        .iter()
                        .find(|m| super::provider_settings::model_id(m) == model_id);
                    let stored = array(incoming.get("models"))
                        .iter()
                        .find(|m| super::provider_settings::model_id(m).trim() == model_id);
                    let mut combined = known_builtin
                        .and_then(Value::as_object)
                        .cloned()
                        .unwrap_or_default();
                    combined.extend(model.as_object().unwrap().clone());
                    if let (Some(known), Some(stored)) = (known_builtin, stored)
                        && !stored["purposes"].is_array()
                    {
                        combined.insert("purposes".into(), known["purposes"].clone());
                    }
                    if moved {
                        let catalog_row = array(catalog()["providers"][&id].get("models"))
                            .iter()
                            .find(|m| super::provider_settings::model_id(m) == model_id);
                        if let Some(catalog_row) = catalog_row {
                            for key in METADATA {
                                combined.remove(*key);
                            }
                            for (key, val) in internal(catalog_row).as_object().unwrap() {
                                if key != "id" && key != "label" {
                                    combined.insert(key.clone(), val.clone());
                                }
                            }
                        }
                    }
                    merge_row(&mut merged, Value::Object(combined));
                }
                provider["models"] = json!(normalize_models(&json!(merged)));
            } else {
                provider["models"] = json!(models);
            }
        }
        if !truthy(&provider["default_base_url"]) && truthy(&provider["base_url"]) {
            provider["default_base_url"] = provider["base_url"].clone();
        }
        let mut enabled = Map::new();
        for model in array(provider.get("models")) {
            let mid = model_id(model);
            let previous = provider["enabled_models"]
                .get(mid)
                .map(truthy)
                .unwrap_or(true);
            let current = incoming["enabled_models"]
                .get(mid)
                .map(truthy)
                .unwrap_or(previous);
            let valid =
                model.get("purposes").map(truthy).unwrap_or(true) && model["not_supported"] != true;
            enabled.insert(mid.to_owned(), json!(current && valid));
        }
        provider["enabled_models"] = json!(enabled);
        if let Some(base) = incoming["base_url"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
        {
            provider["base_url"] = json!(url(&id, base, &definitions));
        }
        if incoming["api_key"].is_string() {
            provider["api_key"] = incoming["api_key"].clone();
        }
        if host == "android" && id == "local-litert-lm" {
            provider["kind"] = json!("litert_lm");
            provider["active"] = json!(true);
            provider["requires_api_key"] = json!(false);
            provider["default_base_url"] = json!("local://litert-lm");
            provider["base_url"] = json!("local://litert-lm");
        }
        clean["providers"][&id] = provider;
        if !existed {
            order.push(id);
        }
    }
    (clean, order)
}
fn update(
    current: &Value,
    patch: &Value,
    env: &Value,
    current_order: &Value,
    patch_order: &Value,
    host: &str,
) -> (Value, Vec<String>) {
    let (mut clean, mut order) = normalize(current, env, current_order, host);
    let providers = &patch["providers"];
    let incoming_chatgpt = if providers["chatgpt"].is_object() {
        &providers["chatgpt"]["models"]
    } else {
        &patch["chatgpt_models"]
    };
    if incoming_chatgpt.is_array() {
        let mut merged = array(clean.get("chatgpt_models")).to_vec();
        for mut model in normalize_models(incoming_chatgpt) {
            model.as_object_mut().unwrap().remove("purposes");
            merge_row(&mut merged, model);
        }
        clean["chatgpt_models"] = json!(merged);
    }
    for raw in array(Some(patch_order)).iter().filter_map(Value::as_str) {
        let id = sanitize_id(raw);
        let incoming = &providers[raw];
        if id == "chatgpt" || !incoming.is_object() {
            continue;
        }
        if incoming["delete"] == true {
            if host == "android" && id == "local-litert-lm" {
                continue;
            }
            if definitions(host).iter().any(|d| d["id"] == id)
                && clean["providers"].get(&id).is_some()
            {
                clean["providers"][&id]["active"] = json!(false);
            } else {
                clean["providers"].as_object_mut().unwrap().remove(&id);
                order.retain(|x| x != &id);
            }
            continue;
        }
        if clean["providers"].get(&id).is_none() {
            let get = |key: &str| {
                incoming
                    .get(key)
                    .filter(|v| truthy(v))
                    .cloned()
                    .unwrap_or(json!(""))
            };
            clean["providers"][&id] = json!({"id":id,"label":if truthy(&incoming["label"]) {incoming["label"].clone()} else {json!(id)},
                "kind":kind(&incoming["kind"], host),"api_key_env":get("api_key_env"),"base_url_env":get("base_url_env"),
                "default_base_url":if truthy(&incoming["default_base_url"]) {incoming["default_base_url"].clone()} else {get("base_url")},
                "requires_api_key":truthy(&incoming["requires_api_key"]),"memo":get("memo"),"models":normalize_models(&incoming["models"]),
                "builtin":false,"active":true,"base_url":if truthy(&incoming["base_url"]) {incoming["base_url"].clone()} else {get("default_base_url")},
                "api_key":"","enabled_models":{}});
            order.push(id.clone());
        } else {
            for key in [
                "label",
                "kind",
                "api_key_env",
                "base_url_env",
                "default_base_url",
                "requires_api_key",
                "memo",
                "models",
                "active",
            ] {
                if let Some(value) = incoming.get(key) {
                    clean["providers"][&id][key] = value.clone();
                }
            }
        }
        let provider = &mut clean["providers"][&id];
        if let Some(base) = incoming["base_url"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
        {
            provider["base_url"] = json!(url(&id, base, &definitions(host)));
        }
        if let Some(values) = incoming["rate_limits"].as_object() {
            let mut rates = provider["rate_limits"]
                .as_object()
                .cloned()
                .unwrap_or_default();
            rates.extend(values.clone());
            provider["rate_limits"] = json!(rates);
        }
        if incoming["clear_api_key"] == true {
            provider["api_key"] = json!("");
        } else if let Some(key) = incoming["api_key"].as_str().filter(|s| !s.is_empty()) {
            provider["api_key"] = json!(key);
        }
        if let Some(enabled) = incoming["enabled_models"].as_object() {
            let models = array(provider.get("models")).to_vec();
            if !provider["enabled_models"].is_object() {
                provider["enabled_models"] = json!({});
            }
            for (mid, value) in enabled {
                if let Some(model) = models.iter().find(|m| model_id(m) == mid) {
                    let callable =
                        !truthy(&model["eol"]) && !truthy(&model["requires_subscription"]);
                    provider["enabled_models"][mid] = json!(truthy(value) && callable);
                }
            }
        }
    }
    normalize(&clean, env, &json!(order), host)
}

pub(super) fn run(request: &Value) -> Value {
    let host = request["host"].as_str().unwrap_or("server");
    if request["action"] == "validate_settings" {
        let raw_id = request["provider"].as_str().unwrap_or("");
        let id = sanitize_id(raw_id);
        let base = request["base_url"].as_str().unwrap_or("");
        let normal_url = url(&id, base, &definitions(host));
        let url_valid =
            (host == "android" && id == "local-litert-lm" && normal_url == "local://litert-lm")
                || ["http://", "https://"].iter().any(|prefix| {
                    normal_url.strip_prefix(prefix).is_some_and(|rest| {
                        !rest.split(['/', '?', '#']).next().unwrap_or("").is_empty()
                            && !rest.chars().any(char::is_whitespace)
                    })
                });
        let mut seen = HashSet::new();
        let mut duplicates = Vec::new();
        for row in array(request.get("models")) {
            let mid = row["id"].as_str().unwrap_or("").trim();
            if !mid.is_empty() && !seen.insert(mid) && !duplicates.contains(&mid) {
                duplicates.push(mid);
            }
        }
        let rates = &request["rate_limits"];
        let rates_valid = ["rpm", "tpm", "rpd"].iter().all(|k| {
            rates[*k]
                .as_i64()
                .is_some_and(|n| (0..=1_000_000_000).contains(&n))
        });
        let provider_valid = !id.is_empty() && raw_id.trim().to_lowercase() == id;
        return json!({"normalized_provider":id,"normalized_url":normal_url,"provider_valid":provider_valid,
            "url_valid":url_valid,"rate_limits_valid":rates_valid,"duplicate_models":duplicates});
    }
    let (settings, order) = if request["action"] == "default_settings" {
        defaults(&request["env"], host)
    } else if request["action"] == "update_settings" {
        update(
            &request["settings"],
            &request["patch"],
            &request["env"],
            &request["order"],
            &request["patch_order"],
            host,
        )
    } else {
        normalize(
            &request["settings"],
            &request["env"],
            &request["order"],
            host,
        )
    };
    json!({"settings":settings,"order":order})
}
