//! Pure ChatGPT plan publication policy; the host owns storage and HTTP.
use super::*;

fn usable(profile: &Value, id: &str, assessment: &Value) -> Vec<Value> {
    let default = json!(["llm", "vision"]);
    let chosen = profile["model_purposes"].get(id).unwrap_or(&default);
    array(Some(chosen))
        .iter()
        .filter(|p| !array(assessment.get("unsupported_purposes")).contains(p))
        .cloned()
        .collect()
}

fn publication(profile: &Value, input_models: &Value, assessments: &Value) -> Value {
    let rows = if input_models.is_array() {
        input_models
    } else {
        &profile["catalog"]["models"]
    };
    let selected = array(profile.get("published_models"));
    let mut annotated = Vec::new();
    for model in array(Some(rows)) {
        let id = model["id"].as_str().unwrap_or("");
        let assessment = &assessments[id];
        let purposes = usable(profile, id, assessment);
        let mut shared = assessment.as_object().cloned().unwrap_or_default();
        shared.remove("id");
        shared.remove("label");
        let mut label_input = shared.clone();
        label_input.insert(
            "purposes".into(),
            json!(
                ["llm", "vision"]
                    .iter()
                    .filter(|p| !contains(assessment.get("unsupported_purposes"), p))
                    .collect::<Vec<_>>()
            ),
        );
        let tags = labels(&Value::Object(label_input), catalog());
        let mut shown = model.as_object().cloned().unwrap_or_default();
        shown.extend(shared);
        shown.insert("purposes".into(), json!(purposes));
        shown.insert(
            "enabled".into(),
            json!(
                selected.contains(&json!(id))
                    && !purposes.is_empty()
                    && !truthy(&assessment["not_supported"])
            ),
        );
        let mut annotated_row = labelled(&Value::Object(shown), catalog());
        annotated_row["labels"] = json!(tags);
        annotated_row["fold"] = tags.last().map_or(Value::Null, |tag| json!(tag));
        annotated.push(annotated_row);
    }
    let enabled: Map<String, Value> = annotated
        .iter()
        .map(|m| {
            (
                m["id"].as_str().unwrap_or("").to_owned(),
                m["enabled"].clone(),
            )
        })
        .collect();
    json!({"profile_id":profile["id"],"generation":profile["generation"],"models":annotated,
        "enabled_models":enabled,"model_labels":catalog()["labels"],"assessment_keys":ASSESSMENT})
}

pub(super) fn run(request: &Value) -> Value {
    let profile = &request["profile"];
    match request["action"].as_str().unwrap_or("") {
        "chatgpt_usable" => {
            json!({"purposes":usable(profile,request["model"].as_str().unwrap_or(""),&request["assessment"])})
        }
        "chatgpt_publication" => {
            json!({"publication":publication(profile, &request["models"], &request["assessments"])})
        }
        "chatgpt_offered" => {
            let model = &request["model"];
            let purpose = &request["purpose"];
            json!({"offered":array(request.get("models")).iter().any(|m| &m["id"] == model && truthy(&m["enabled"]) && array(m.get("purposes")).contains(purpose))})
        }
        "chatgpt_cache" => {
            let now = request["now"].as_f64().unwrap_or(0.0);
            json!({"fresh": !truthy(&request["force"]) && truthy(&request["cache"]) && request["cache"]["expires_at"].as_f64().is_some_and(|expiry| expiry > now), "expires_at":now + 300.0})
        }
        "chatgpt_publication_update" => {
            let mut profile = profile.clone();
            let rows = array(profile["catalog"].get("models"));
            let offered: Vec<Value> = rows.iter().map(|m| m["id"].clone()).collect();
            let selected = &request["selected"];
            let choices = &request["model_purposes"];
            if !selected.is_null()
                && (!selected.is_array()
                    || array(Some(selected)).iter().any(|m| !offered.contains(m)))
            {
                return json!({"error":"chatgpt_model_not_offered"});
            }
            if !choices.is_null() {
                let Some(choices) = choices.as_object() else {
                    return json!({"error":"chatgpt_model_not_offered"});
                };
                let mut purposes = profile["model_purposes"]
                    .as_object()
                    .cloned()
                    .unwrap_or_default();
                for (id, selected) in choices {
                    if !offered.contains(&json!(id))
                        || !selected.is_array()
                        || array(Some(selected))
                            .iter()
                            .any(|v| v != "llm" && v != "vision")
                    {
                        return json!({"error":"chatgpt_model_not_offered"});
                    }
                    purposes.insert(
                        id.clone(),
                        json!(
                            ["llm", "vision"]
                                .iter()
                                .filter(|p| array(Some(selected)).contains(&json!(p)))
                                .collect::<Vec<_>>()
                        ),
                    );
                }
                profile["model_purposes"] = json!(purposes);
            }
            let chosen = if selected.is_null() {
                &profile["published_models"]
            } else {
                selected
            };
            for id in array(Some(chosen)) {
                if offered.contains(id) {
                    let id = id.as_str().unwrap_or("");
                    let purposes = profile["model_purposes"]
                        .get(id)
                        .cloned()
                        .unwrap_or(json!(["llm", "vision"]));
                    if array(Some(&purposes)).is_empty()
                        || (!selected.is_null()
                            && (usable(&profile, id, &request["assessments"][id]).is_empty()
                                || truthy(&request["assessments"][id]["not_supported"])))
                    {
                        return json!({"error":"chatgpt_model_not_offered"});
                    }
                }
            }
            if !selected.is_null() {
                let mut unique = Vec::new();
                for id in array(Some(selected)) {
                    if !unique.contains(id) {
                        unique.push(id.clone());
                    }
                }
                profile["published_models"] = json!(unique);
            }
            json!({"profile":profile})
        }
        _ => json!({"error":"unknown_action"}),
    }
}
