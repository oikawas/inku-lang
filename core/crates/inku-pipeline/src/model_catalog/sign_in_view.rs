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

/// The one registration a host keeps: the chosen one, else the newest
/// connected one, else the newest of any (the author's choice, 11-14).
pub(super) fn kept_registration(profiles: &[Value], active: &Value) -> Option<Value> {
    if let Some(chosen) = profiles
        .iter()
        .find(|p| !active.is_null() && &p["id"] == active)
    {
        return Some(chosen.clone());
    }
    let newest = |rows: Vec<&Value>| {
        rows.into_iter()
            .max_by_key(|p| p["generation"].as_u64().unwrap_or(0))
            .cloned()
    };
    newest(
        profiles
            .iter()
            .filter(|p| p["state"] == "connected")
            .collect(),
    )
    .or_else(|| newest(profiles.iter().collect()))
}

/// What a host shows for its one sign-in connection (the author, 11-14:
/// one registration, and one action for each state). Signing out stands
/// apart, for a registration that holds tokens, with the note that ChatGPT's
/// settings can remove inku's connection; nothing is deleted here.
fn connection_view(request: &Value, service: &Value) -> Value {
    let scope = service["use_scope"].as_str().unwrap_or("");
    let connection = &request["connection"];
    let busy = truthy(&request["busy"]);
    let attempt = &request["attempt"];
    let profiles = array(connection.get("profiles"));
    let profile = kept_registration(profiles, &connection["active_profile_id"]);
    let state = profile
        .as_ref()
        .and_then(|p| p["state"].as_str())
        .filter(|s| !s.is_empty())
        .unwrap_or(if profile.is_some() {
            "reauthentication_required"
        } else {
            "signed_out"
        });
    let allowed = profile
        .as_ref()
        .is_some_and(|p| array(p.get("scopes")).contains(&json!(scope)));
    let code = request["code"].as_str().filter(|s| !s.is_empty());
    let changed = matches!(
        code,
        Some("chatgpt_identity_mismatch" | "chatgpt_account_changed")
    );
    let revocation_unconfirmed =
        request["last_operation"] == "sign_out" && request["revocation_confirmed"] == json!(false);
    let own_status = if state == "connected" && !allowed {
        "chatgpt_scope_required".to_owned()
    } else {
        format!("chatgpt_{state}")
    };
    let status = if changed {
        "chatgpt_account_changed".to_owned()
    } else if let Some(code) = code {
        code.to_owned()
    } else if revocation_unconfirmed {
        "chatgpt_revocation_unconfirmed".to_owned()
    } else {
        own_status.clone()
    };
    let signing_in = truthy(&attempt["active"]);
    let primary = if signing_in {
        Value::Null
    } else if changed {
        action("new_sign_in", !busy)
    } else {
        match own_status.as_str() {
            "chatgpt_scope_required" => action("grant_plan", !busy),
            "chatgpt_quota" => action("retry", !busy),
            "chatgpt_connected" | "chatgpt_exported" => Value::Null,
            _ => action("sign_in", !busy),
        }
    };
    let mut attempt_actions = Vec::new();
    if signing_in && !truthy(&attempt["helper"]) {
        attempt_actions.push(action("cancel", true));
    }
    if truthy(&attempt["can_reopen"]) {
        attempt_actions.push(action("reopen_sign_in", true));
    }
    if truthy(&attempt["helper"]) {
        attempt_actions.push(action("reopen_helper", true));
    }
    let holds_tokens = matches!(state, "connected" | "quota");
    let sign_out = if holds_tokens && !signing_in {
        json!({"action":"sign_out","enabled":!busy,"confirm":true})
    } else {
        Value::Null
    };
    let notice = if holds_tokens || revocation_unconfirmed || changed {
        json!("chatgpt_disconnect_in_settings")
    } else {
        Value::Null
    };
    json!({"status": status,
        "label": profile.as_ref().map_or(Value::Null, |p| p["label"].clone()),
        "primary": primary,
        "attempt_actions": attempt_actions,
        "sign_out": sign_out,
        "notice": notice,
        "manage_usage": {"url": service["usage_url"]},
        "guide": state == "connected" && allowed && !changed})
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
    // The assessments an administrator changed (the Web's model settings: a
    // key left out or empty is not sent; null is).
    let administrator = truthy(&request["administrator"]);
    let changed: Vec<Value> = rows
        .iter()
        .filter(|_| administrator)
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
                    && value != ""
                {
                    out.insert(key.into(), value.clone());
                }
            }
            Some(Value::Object(out))
        })
        .collect();
    // A changed assessment is unsaved too, as on the Web (its draft signature);
    // only an administrator edits them.
    let dirty = dirty || !changed.is_empty();
    json!({"draft": {"selected": selected, "purposes": purposes}, "rows": shown,
        "dirty": dirty, "can_refresh": !dirty, "can_save": true,
        "save": {"profile_id": publication["profile_id"], "generation": publication["generation"],
            "published_models": published, "model_purposes": model_purposes},
        "assessments": changed})
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
