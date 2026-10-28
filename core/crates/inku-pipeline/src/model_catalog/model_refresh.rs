use super::*;

fn id(row: &Value) -> &str {
    row["id"].as_str().unwrap_or("")
}
fn prepare(provider: &str, rows: &Value, previous: &Value) -> Vec<Value> {
    let old = array(previous.get("models"));
    let known = array(catalog()["providers"][provider].get("models"));
    array(Some(rows))
        .iter()
        .map(|row| {
            let mut model = row.clone();
            if let Some(previous) = old.iter().find(|p| id(p) == id(row)) {
                for key in provider_settings::METADATA[..19]
                    .iter()
                    .chain(["allowed_unsupported_purposes", "requires_subscription"].iter())
                {
                    if let Some(value) = previous.get(*key) {
                        model[*key] = value.clone();
                    }
                }
                let old_label = previous["label"].as_str().unwrap_or("").trim();
                if !old_label.is_empty()
                    && old_label != id(previous)
                    && model["label"].as_str().unwrap_or("") == id(row)
                {
                    model["label"] = json!(old_label);
                }
                model.as_object_mut().unwrap().remove("eol");
                model.as_object_mut().unwrap().remove("eol_date");
            } else if let Some(known) = known.iter().find(|p| id(p) == id(row)) {
                for (key, value) in internal(known).as_object().unwrap() {
                    if !["id", "label", "eol", "eol_date"].contains(&key.as_str()) {
                        model[key] = value.clone();
                    }
                }
            }
            model
        })
        .collect()
}
fn finish(rows: &Value, previous: &Value, today: &str) -> Value {
    let mut models = array(Some(rows)).to_vec();
    let old = array(previous.get("models"));
    let ids: HashSet<String> = models.iter().map(|m| id(m).to_owned()).collect();
    let mut retired: Vec<Value> = old
        .iter()
        .filter(|p| !ids.contains(id(p)))
        .map(|p| {
            let mut p = p.clone();
            p["eol"] = json!(true);
            if p.get("eol_date").is_none() {
                p["eol_date"] = json!(today);
            }
            p
        })
        .collect();
    retired.sort_by(|a, b| id(a).cmp(id(b)));
    models.extend(retired);
    let enabled: Map<String, Value> = models
        .iter()
        .map(|m| {
            let mid = id(m);
            let enabled = !truthy(&m["eol"])
                && !truthy(&m["requires_subscription"])
                && old.iter().any(|p| id(p) == mid)
                && previous["enabled_models"].get(mid).is_some_and(truthy);
            (mid.into(), json!(enabled))
        })
        .collect();
    json!({"models":models,"enabled_models":enabled})
}
pub(super) fn run(request: &Value) -> Value {
    if request["action"] == "access_enabled" {
        json!({"enabled":request["provider"] == "ollama-cloud"})
    } else if request["action"] == "access_targets" {
        let models: Vec<Value> = array(request.get("models"))
            .iter()
            .filter(|m| !truthy(&m["eol"]))
            .cloned()
            .collect();
        json!({"models":models})
    } else if request["action"] == "access_apply" {
        let mut models = array(request.get("models")).to_vec();
        let mut answers = array(request.get("answers")).iter();
        for model in models.iter_mut().filter(|m| !truthy(&m["eol"])) {
            let Some(answer) = answers.next() else {
                break;
            };
            if let Some(date) = answer.get("retired") {
                model["eol"] = json!(true);
                model["eol_date"] = date.clone();
            } else if answer["subscription"] == true {
                model["requires_subscription"] = json!(true);
            } else if answer["subscription"] == false {
                model
                    .as_object_mut()
                    .unwrap()
                    .remove("requires_subscription");
            }
        }
        json!({"models":models})
    } else if request["action"] == "access_probe" {
        let status = request["status"].as_i64().unwrap_or(0);
        let answer = if request["stage"] == "show" && status == 410 {
            let text = request["text"].as_str().unwrap_or("");
            let date = text
                .split("retired at ")
                .skip(1)
                .find_map(|tail| {
                    let date = tail.get(..10)?;
                    let bytes = date.as_bytes();
                    (bytes.iter().enumerate().all(|(i, b)| {
                        if i == 4 || i == 7 {
                            *b == b'-'
                        } else {
                            b.is_ascii_digit()
                        }
                    }))
                    .then_some(date)
                })
                .unwrap_or(request["today"].as_str().unwrap_or(""));
            json!({"retired":date})
        } else if request["stage"] == "call" && [402, 403].contains(&status) {
            json!({"subscription":true})
        } else if request["stage"] == "call" && status == 200 {
            json!({"subscription":false})
        } else {
            json!({})
        };
        json!({"answer":answer})
    } else if request["action"] == "refresh_prepare" {
        json!({"models":prepare(request["provider"].as_str().unwrap_or(""), &request["models"], &request["previous"])})
    } else {
        finish(
            &request["models"],
            &request["previous"],
            request["today"].as_str().unwrap_or(""),
        )
    }
}
