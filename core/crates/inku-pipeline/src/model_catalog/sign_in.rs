//! Sign-in services: connections where the user signs in with their own
//! account and its subscription allowance pays for the models (for now,
//! "Sign in with ChatGPT"). The descriptor file names each service and its
//! labels; the hosts keep only the sign-in transport.

use serde_json::{Map, Value, json};
use std::sync::OnceLock;

const SERVICES: &str = include_str!("../../data/sign-in-services.json");

pub(super) fn services() -> &'static [Value] {
    static SERVICES_JSON: OnceLock<Vec<Value>> = OnceLock::new();
    SERVICES_JSON.get_or_init(|| serde_json::from_str(SERVICES).expect("sign-in services"))
}

pub(super) fn service(id: &str) -> Option<&'static Value> {
    services().iter().find(|s| s["id"] == id)
}

/// The language of an answer: `ja` or `en`, English when absent.
pub(super) fn language(request: &Value) -> Result<&str, Value> {
    match request.get("language") {
        None | Some(Value::Null) => Ok("en"),
        Some(Value::String(s)) if s == "ja" || s == "en" => Ok(s.as_str()),
        Some(_) => Err(json!({"outcome":"refused","reason":"invalid_language"})),
    }
}

/// The label of a service in a language.
pub(super) fn label<'a>(service: &'a Value, language: &str) -> &'a Value {
    &service["label"][language]
}

fn public(service: &Value, language: &str) -> Map<String, Value> {
    let mut row = Map::new();
    row.insert("id".into(), service["id"].clone());
    row.insert("label".into(), label(service, language).clone());
    row.insert("labels".into(), service["label"].clone());
    row.insert("abbreviation".into(), service["abbreviation"].clone());
    row.insert("usage_url".into(), service["usage_url"].clone());
    row.insert("kind".into(), service["kind"].clone());
    row.insert(
        "requires_api_key".into(),
        service["requires_api_key"].clone(),
    );
    row
}

fn provider_groups(request: &Value, language: &str) -> Value {
    let Some(groups) = request["groups"].as_array() else {
        return json!({"outcome":"refused","reason":"invalid_groups"});
    };
    let signed_in = match &request["sign_in"] {
        Value::Null => Vec::new(),
        Value::Array(rows) => rows.clone(),
        _ => return json!({"outcome":"refused","reason":"invalid_sign_in"}),
    };
    let mut seen: Vec<&str> = Vec::new();
    for row in &signed_in {
        let Some(id) = row["service"].as_str() else {
            return json!({"outcome":"refused","reason":"invalid_sign_in"});
        };
        if service(id).is_none() {
            return json!({"outcome":"refused","reason":"unknown_sign_in_service"});
        }
        if seen.contains(&id) {
            return json!({"outcome":"refused","reason":"duplicate_sign_in_service"});
        }
        if !row["models"].is_array() {
            return json!({"outcome":"refused","reason":"invalid_sign_in"});
        }
        seen.push(id);
    }
    let mut result: Vec<Value> = Vec::new();
    for service in services() {
        let id = service["id"].as_str().unwrap_or("");
        if let Some(row) = signed_in.iter().find(|row| row["service"] == id) {
            let mut group = public(service, language);
            group.insert("models".into(), row["models"].clone());
            result.push(Value::Object(group));
        }
    }
    result.extend(
        groups
            .iter()
            .filter(|group| group["id"].as_str().is_none_or(|id| !seen.contains(&id)))
            .cloned(),
    );
    json!({"groups":result})
}

pub(super) fn run(request: &Value) -> Value {
    let language = match language(request) {
        Ok(language) => language,
        Err(refused) => return refused,
    };
    match request["action"].as_str().unwrap_or("") {
        "sign_in_services" => {
            let rows: Vec<Value> = services()
                .iter()
                .map(|s| Value::Object(public(s, language)))
                .collect();
            json!({"services":rows})
        }
        "provider_groups" => provider_groups(request, language),
        _ => json!({"outcome":"refused","reason":"unknown_action"}),
    }
}

/// The sign-in actions that carry their own name (step 1 and 2). The others
/// a host sends as `sign_in_<rest>` with a `service`, and the core runs them
/// inside as `<code_prefix>_<rest>` (step 3; the old names closed in step 6).
pub(crate) const NATIVE: [&str; 4] = [
    "sign_in_services",
    "provider_groups",
    "sign_in_connection_view",
    "sign_in_publication_draft",
];

/// The actions a host may send under `sign_in_<rest>` with a `service`
/// (step 6). The others (`auth_tokens`, `auth_select`, `catalog`, ...) are
/// parts the core's own procedures use; no host sends them.
pub(crate) const PUBLIC: [&str; 23] = [
    "flow_start",
    "flow_next",
    "publication",
    "publication_update",
    "offered",
    "usable",
    "transfer_check",
    "transfer_import",
    "auth_constants",
    "auth_session",
    "auth_publication_input",
    "auth_publication_active",
    "auth_operation",
    "auth_quota_failure",
    "auth_attempt",
    "auth_endpoint",
    "request",
    "vision_request",
    "stream",
    "error",
    "transport",
    "failure",
    "limits",
];

/// Why an entry refuses an action name.
pub(crate) enum Refused {
    /// A name no host may send (an old `chatgpt_*` name, or a part).
    UnknownAction,
    /// `sign_in_*` without a known `service`.
    UnknownService,
}

/// The inside name (`chatgpt_<rest>`) of an action a host sends to an entry,
/// or `None` when the action is not a sign-in service's. An old `chatgpt_*`
/// name and a part no host sends are refused (step 6).
pub(crate) fn gate(action: &str, service_id: Option<&str>) -> Result<Option<String>, Refused> {
    if services().iter().any(|s| {
        s["code_prefix"]
            .as_str()
            .is_some_and(|prefix| action.starts_with(&format!("{prefix}_")))
    }) {
        return Err(Refused::UnknownAction);
    }
    let Some(rest) = action.strip_prefix("sign_in_") else {
        return Ok(None);
    };
    if NATIVE.contains(&action) {
        return Ok(None);
    }
    let Some(found) = service_id.and_then(service) else {
        return Err(Refused::UnknownService);
    };
    if !PUBLIC.contains(&rest) {
        return Err(Refused::UnknownAction);
    }
    let prefix = found["code_prefix"].as_str().unwrap_or("chatgpt");
    Ok(Some(format!("{prefix}_{rest}")))
}

/// Whether an id names a sign-in service (its group and models are the
/// service's, not a provider's).
pub(crate) fn is_service(id: &str) -> bool {
    service(id).is_some()
}

/// The descriptor the `chatgpt_*` handlers read (step 3): the alias names
/// them by the service's code prefix, so they always serve `chatgpt`.
pub(crate) fn chatgpt() -> &'static Value {
    service("chatgpt").expect("the chatgpt sign-in descriptor")
}

/// A descriptor text.
pub(crate) fn text(value: &'static Value) -> &'static str {
    value.as_str().expect("a descriptor text")
}

/// A descriptor list of texts.
pub(crate) fn texts(value: &'static Value) -> Vec<&'static str> {
    value
        .as_array()
        .expect("a descriptor list")
        .iter()
        .map(text)
        .collect()
}

/// A descriptor whole number.
pub(crate) fn count(value: &'static Value) -> u64 {
    value.as_u64().expect("a descriptor number")
}
