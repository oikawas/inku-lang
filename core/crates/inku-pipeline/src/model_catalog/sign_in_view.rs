//! What a host shows for a sign-in connection (step 2): the connection's
//! state and actions, and the editing of the models it publishes. The answers
//! follow the Web's settings (the author's decision); the hosts keep the
//! wording tables and the windows.

use super::sign_in;
use super::{ASSESSMENT, array, truthy};
use serde_json::{Map, Value, json};

fn action(name: &str, enabled: bool) -> Value {
    json!({"action": name, "enabled": enabled})
}

fn confirmed(name: &str, enabled: bool) -> Value {
    json!({"action": name, "enabled": enabled, "confirm": true})
}

fn profile_status(profile: &Value, scope: &str) -> String {
    let state = profile["state"]
        .as_str()
        .filter(|s| !s.is_empty())
        .unwrap_or("reauthentication_required");
    if state == "connected" && !array(profile.get("scopes")).contains(&json!(scope)) {
        "chatgpt_scope_required".into()
    } else {
        format!("chatgpt_{state}")
    }
}

fn connection_view(request: &Value, service: &Value) -> Value {
    let scope = service["use_scope"].as_str().unwrap_or("");
    let connection = &request["connection"];
    let busy = truthy(&request["busy"]);
    let attempt = &request["attempt"];
    let active_id = &connection["active_profile_id"];
    let status = match request["code"].as_str().filter(|s| !s.is_empty()) {
        Some(code) => json!(code),
        None => {
            let operation = request["last_operation"].as_str().unwrap_or("");
            if (operation == "sign_out" || operation == "delete")
                && request["revocation_confirmed"] == json!(false)
            {
                json!("chatgpt_revocation_unconfirmed")
            } else {
                Value::Null
            }
        }
    };
    let mut actions = vec![
        action("sign_in", !busy),
        action("check_connection", !busy),
        json!({"action":"manage_usage","enabled":true,"url":service["usage_url"]}),
    ];
    if truthy(&attempt["can_reopen"]) {
        actions.push(action("reopen_sign_in", true));
    }
    if truthy(&attempt["active"]) && !truthy(&attempt["helper"]) {
        actions.push(action("cancel", true));
    }
    if truthy(&attempt["helper"]) {
        actions.push(action("reopen_helper", true));
    }
    let pending: Vec<Value> = array(connection.get("pending_registrations"))
        .iter()
        .map(|row| {
            json!({"id": row["id"], "client_id": row.get("client_id").cloned().unwrap_or(Value::Null),
                "actions": [action("reconnect", !busy)]})
        })
        .collect();
    let profiles: Vec<Value> = array(connection.get("profiles"))
        .iter()
        .map(|profile| {
            let allowed = array(profile.get("scopes")).contains(&json!(scope));
            let mut row = vec![action("select", !busy), action("reauthenticate", !busy)];
            if !allowed {
                row.push(action("grant_plan", !busy));
            }
            if profile["state"] == "quota" {
                row.push(action("retry", !busy));
            }
            row.push(confirmed("sign_out", !busy));
            row.push(confirmed("delete", !busy));
            json!({"id": profile["id"], "label": profile["label"],
                "active": !active_id.is_null() && &profile["id"] == active_id,
                "status": profile_status(profile, scope), "actions": row})
        })
        .collect();
    let guide = array(connection.get("profiles")).iter().any(|profile| {
        !active_id.is_null()
            && &profile["id"] == active_id
            && profile["state"] == "connected"
            && array(profile.get("scopes")).contains(&json!(scope))
    });
    json!({"status": status, "actions": actions, "pending": pending, "profiles": profiles, "guide": guide})
}

fn unselectable(row: &Value) -> bool {
    truthy(&row["selection"]["unselectable"])
}

fn locked(row: &Value, purpose: &str) -> bool {
    truthy(&row["selection"]["unsupported"][purpose])
}

fn ordered(purposes: &[Value]) -> Vec<Value> {
    ["llm", "vision"]
        .iter()
        .map(|p| json!(p))
        .filter(|p| purposes.contains(p))
        .collect()
}

fn publication_draft(request: &Value) -> Value {
    let publication = &request["publication"];
    let Some(rows) = publication["models"].as_array() else {
        return json!({"outcome":"refused","reason":"invalid_publication"});
    };
    let mut initial_selected = Map::new();
    let mut initial_purposes = Map::new();
    for row in rows {
        let id = row["id"].as_str().unwrap_or("").to_owned();
        initial_selected.insert(
            id.clone(),
            json!(truthy(&publication["enabled_models"][id.as_str()])),
        );
        initial_purposes.insert(id, json!(array(row.get("purposes"))));
    }
    let draft = &request["draft"];
    let mut selected = draft["selected"]
        .as_object()
        .cloned()
        .unwrap_or_else(|| initial_selected.clone());
    let mut purposes = draft["purposes"]
        .as_object()
        .cloned()
        .unwrap_or_else(|| initial_purposes.clone());
    let row_of = |id: &str| rows.iter().find(|row| row["id"] == id);
    let purposes_of = |purposes: &Map<String, Value>, id: &str| -> Vec<Value> {
        array(purposes.get(id)).to_vec()
    };
    let edit = &request["edit"];
    match edit["kind"].as_str().unwrap_or("") {
        "" => {}
        "toggle_model" => {
            let id = edit["id"].as_str().unwrap_or("");
            if let Some(row) = row_of(id)
                && !unselectable(row)
                && !purposes_of(&purposes, id).is_empty()
            {
                selected.insert(id.into(), json!(truthy(&edit["selected"])));
            }
        }
        "toggle_purpose" => {
            let id = edit["id"].as_str().unwrap_or("");
            let purpose = edit["purpose"].as_str().unwrap_or("");
            if let Some(row) = row_of(id)
                && (purpose == "llm" || purpose == "vision")
                && !locked(row, purpose)
            {
                let mut current = purposes_of(&purposes, id);
                if current.contains(&json!(purpose)) {
                    current.retain(|p| p != purpose);
                } else {
                    current.push(json!(purpose));
                }
                selected.insert(id.into(), json!(!current.is_empty()));
                purposes.insert(id.into(), json!(current));
            }
        }
        "select_all" => {
            let on = truthy(&edit["selected"]);
            for id in array(edit.get("ids")).iter().filter_map(Value::as_str) {
                if let Some(row) = row_of(id) {
                    let value = on && !unselectable(row) && !purposes_of(&purposes, id).is_empty();
                    selected.insert(id.into(), json!(value));
                }
            }
        }
        _ => return json!({"outcome":"refused","reason":"invalid_edit"}),
    }
    let shown: Vec<Value> = rows
        .iter()
        .map(|row| {
            let id = row["id"].as_str().unwrap_or("");
            let chosen = purposes_of(&purposes, id);
            let locked_purposes: Vec<&str> = ["llm", "vision"]
                .into_iter()
                .filter(|p| locked(row, p))
                .collect();
            json!({"id": id, "selected": !unselectable(row) && truthy(&selected[id]),
                "can_toggle": !unselectable(row) && !chosen.is_empty(), "purposes": chosen,
                "locked_purposes": locked_purposes})
        })
        .collect();
    let dirty = selected != initial_selected || purposes != initial_purposes;
    let published: Vec<Value> = rows
        .iter()
        .filter(|row| truthy(&selected[row["id"].as_str().unwrap_or("")]))
        .map(|row| row["id"].clone())
        .collect();
    let model_purposes: Map<String, Value> = rows
        .iter()
        .map(|row| {
            let id = row["id"].as_str().unwrap_or("");
            let chosen = purposes
                .get(id)
                .map(|v| array(Some(v)).to_vec())
                .unwrap_or_else(|| vec![json!("llm"), json!("vision")]);
            (id.to_owned(), json!(ordered(&chosen)))
        })
        .collect();
    let assessments: Vec<Value> = if truthy(&request["administrator"]) {
        rows.iter()
            .filter_map(|row| {
                let id = row["id"].as_str().unwrap_or("");
                let draft = request["assessment_drafts"].get(id)?;
                if ASSESSMENT.iter().all(|key| {
                    draft.get(*key).unwrap_or(&Value::Null) == row.get(*key).unwrap_or(&Value::Null)
                }) {
                    return None;
                }
                let mut out = Map::new();
                out.insert("id".into(), row["id"].clone());
                out.insert("label".into(), row["label"].clone());
                for key in ASSESSMENT {
                    if let Some(value) = draft.get(key)
                        && !value.is_null()
                        && value != ""
                    {
                        out.insert(key.into(), value.clone());
                    }
                }
                Some(Value::Object(out))
            })
            .collect()
    } else {
        Vec::new()
    };
    json!({"draft": {"selected": selected, "purposes": purposes}, "rows": shown,
        "dirty": dirty, "can_refresh": !dirty, "can_save": true,
        "save": {"profile_id": publication["profile_id"], "generation": publication["generation"],
            "published_models": published, "model_purposes": model_purposes},
        "assessments": assessments})
}

pub(super) fn run(request: &Value) -> Value {
    let Some(service) = request["service"].as_str().and_then(sign_in::service) else {
        return json!({"outcome":"refused","reason":"unknown_sign_in_service"});
    };
    match request["action"].as_str().unwrap_or("") {
        "sign_in_connection_view" => connection_view(request, service),
        "sign_in_publication_draft" => publication_draft(request),
        _ => json!({"outcome":"refused","reason":"unknown_action"}),
    }
}
