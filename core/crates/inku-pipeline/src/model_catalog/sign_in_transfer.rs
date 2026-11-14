//! Importing a registration moved from another host (step 6): the checks of
//! the decrypted registration and how it joins the store. The envelope's
//! cryptography, its receipts and the locks stay with the Server; the
//! identity token is checked by the `identity` procedure before the merge.
//! The rules are the Server's (`chatgpt_transfer.py` at product 78d1963e3).

use super::sign_in::{chatgpt, count, text};
use super::*;

const INVALID: &str = "chatgpt_transfer_invalid";

fn fail(code: &str) -> Value {
    json!({"error":code})
}

/// Python's `uuid.UUID(text).version == 4`.
fn version_4(text: &str) -> bool {
    let hex = text.replace("urn:", "").replace("uuid:", "");
    let hex = hex.trim_matches(|c| c == '{' || c == '}').replace('-', "");
    let digits: Vec<char> = hex.chars().collect();
    digits.len() == 32
        && digits.iter().all(char::is_ascii_hexdigit)
        && digits[12] == '4'
        && matches!(digits[16].to_ascii_lowercase(), '8' | '9' | 'a' | 'b')
}

/// A text of 1 to 65536 characters.
fn bounded(value: &Value) -> bool {
    value
        .as_str()
        .is_some_and(|s| (1..=65536).contains(&s.chars().count()))
}

/// Python's `math.isfinite(float(value))`.
fn finite(value: &Value) -> bool {
    match value {
        Value::Number(n) => n.as_f64().is_some_and(f64::is_finite),
        Value::Bool(_) => true,
        Value::String(s) => s.trim().parse::<f64>().is_ok_and(f64::is_finite),
        _ => false,
    }
}

fn limit() -> usize {
    count(&chatgpt()["login"]["limits"]["registrations"]) as usize
}

/// The checks before the identity token is verified: the registration's
/// form, and the room for a new one among `profiles`.
fn check(request: &Value) -> Value {
    let profile = &request["profile"];
    let Some(id) = profile["id"].as_str() else {
        return fail(INVALID);
    };
    let login = &chatgpt()["login"];
    let issuer = text(&login["issuer"]);
    if !version_4(id) || profile["issuer"] != issuer {
        return fail(INVALID);
    }
    if [
        "client_id",
        "sub",
        "oidc_nonce",
        "access_token",
        "refresh_token",
        "id_token",
    ]
    .iter()
    .any(|key| !bounded(&profile[key]))
    {
        return fail(INVALID);
    }
    if profile["client_id"] == text(&login["provisional_client_id"])
        || profile["state"] != "connected"
        || profile["refresh_owner"] != "runtime"
    {
        return fail(INVALID);
    }
    let Some(scopes) = profile["scopes"].as_array() else {
        return fail(INVALID);
    };
    if scopes.len() > 32
        || scopes
            .iter()
            .any(|s| s.as_str().is_none_or(|s| s.chars().count() > 256))
    {
        return fail(INVALID);
    }
    if ["expires_at", "earliest_refresh_at"]
        .iter()
        .any(|key| !finite(&profile[key]))
    {
        return fail(INVALID);
    }
    let Some(profiles) = request["profiles"].as_object() else {
        return fail(INVALID);
    };
    if !profiles.contains_key(id) && profiles.len() >= limit() {
        return fail("chatgpt_profile_limit");
    }
    json!({"valid":true})
}

/// The store with the imported registration chosen: its kept fields, the
/// label from the verified claims, the next generation, and the
/// publication of the registration it replaces.
fn import(request: &Value) -> Value {
    let checked = check(&json!({"profile":request["profile"],
        "profiles":request["value"]["profiles"]}));
    if checked.get("error").is_some() {
        return checked;
    }
    let incoming = &request["profile"];
    let claims = &request["claims"];
    if !claims.is_object() || claims.get("sub").is_none() || claims["sub"] != incoming["sub"] {
        return fail(INVALID);
    }
    let mut profile = Map::new();
    for key in [
        "id",
        "issuer",
        "sub",
        "client_id",
        "oidc_nonce",
        "access_token",
        "refresh_token",
        "id_token",
        "scopes",
        "expires_at",
        "earliest_refresh_at",
    ] {
        profile.insert(key.into(), incoming[key].clone());
    }
    if bounded(&incoming["retained_id_token"]) {
        profile.insert(
            "retained_id_token".into(),
            incoming["retained_id_token"].clone(),
        );
    }
    let shown = chatgpt_auth_policy::run(&json!({"action":"chatgpt_auth_display",
        "claims":claims,"client_id":incoming["client_id"]}));
    profile.insert("email".into(), shown["email"].clone());
    profile.insert("label".into(), shown["label"].clone());
    let id = incoming["id"].as_str().unwrap_or("").to_owned();
    let mut value = request["value"].clone();
    let old = value["profiles"].get(&id).cloned().unwrap_or(Value::Null);
    if truthy(&old)
        && ["issuer", "sub", "client_id"]
            .iter()
            .any(|k| old[*k] != profile[*k])
    {
        return fail("chatgpt_identity_mismatch");
    }
    let generation = match old.get("generation") {
        None => json!(1),
        Some(n) if n.is_u64() => match n.as_u64().and_then(|n| n.checked_add(1)) {
            Some(next) => json!(next),
            None => return fail(INVALID),
        },
        Some(n) if n.is_f64() => json!(n.as_f64().unwrap_or(0.0) + 1.0),
        Some(_) => return fail(INVALID),
    };
    profile.insert("state".into(), json!("connected"));
    profile.insert("refresh_owner".into(), json!("runtime"));
    profile.insert("generation".into(), generation);
    for (key, default) in [
        ("published_models", json!([])),
        ("model_purposes", json!({})),
        ("model_metadata", json!({})),
    ] {
        let kept = if truthy(&old) {
            old.get(key).cloned()
        } else {
            None
        };
        profile.insert(key.into(), kept.unwrap_or(default));
    }
    value["profiles"][&id] = Value::Object(profile);
    value["active"] = json!(id);
    json!({"value":value,"profile_id":id})
}

pub(super) fn run(request: &Value) -> Value {
    match request["action"].as_str().unwrap_or("") {
        "chatgpt_transfer_check" => check(request),
        "chatgpt_transfer_import" => import(request),
        _ => fail("unknown_action"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile() -> Value {
        json!({"id":"6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b","issuer":"https://auth.openai.com",
            "sub":"user-1","client_id":"oaiapp_abcdefgh12345678","oidc_nonce":"n","access_token":"a",
            "refresh_token":"r","id_token":"i","scopes":["openid"],"expires_at":1800000000.0,
            "earliest_refresh_at":1799999000,"state":"connected","refresh_owner":"runtime",
            "retained_id_token":"old-i"})
    }

    fn ask(request: Value) -> Value {
        let mut request = request;
        request["schema"] = json!("inku.model-catalog-request.v1");
        request["service"] = json!("chatgpt");
        let bytes = crate::model_catalog::model_catalog_json(request.to_string().as_bytes());
        serde_json::from_slice(&bytes).unwrap()
    }

    /// The Server's checks before the identity token, in its order.
    #[test]
    fn a_moved_registration_is_checked_as_the_server_did() {
        let checked = |profile: Value, profiles: Value| {
            ask(json!({"action":"sign_in_transfer_check","profile":profile,"profiles":profiles}))
        };
        assert_eq!(checked(profile(), json!({}))["valid"], true);
        for (key, bad) in [
            ("id", json!("6f1c2a3b-4d5e-3f60-8a7b-9c0d1e2f3a4b")),
            ("id", json!(7)),
            ("issuer", json!("https://example.com")),
            ("client_id", json!("dynamic_agent_client")),
            ("sub", json!("")),
            ("id_token", json!("x".repeat(65537))),
            ("state", json!("quota")),
            ("refresh_owner", json!("helper")),
            ("scopes", json!(vec!["s"; 33])),
            ("expires_at", json!("inf")),
            ("earliest_refresh_at", Value::Null),
        ] {
            let mut moved = profile();
            moved[key] = bad.clone();
            assert_eq!(checked(moved, json!({}))["error"], INVALID, "{key} {bad}");
        }
        // Braces, a URN and no hyphens are a UUID to Python as well.
        let mut moved = profile();
        moved["id"] = json!("urn:uuid:{6F1C2A3B4D5E4F608A7B9C0D1E2F3A4B}");
        assert_eq!(checked(moved, json!({}))["valid"], true);
        let full: Map<String, Value> = (0..8).map(|n| (format!("p{n}"), json!({}))).collect();
        assert_eq!(
            checked(profile(), json!(full))["error"],
            "chatgpt_profile_limit"
        );
        let mut kept = full.clone();
        kept.remove("p0");
        kept.insert(profile()["id"].as_str().unwrap().into(), json!({}));
        assert_eq!(checked(profile(), json!(kept))["valid"], true);
    }

    /// The imported registration replaces one of the same account and keeps
    /// its publication; another account's is refused.
    #[test]
    fn an_import_joins_the_store_as_the_server_did() {
        let id = profile()["id"].as_str().unwrap().to_owned();
        let old = json!({"issuer":"https://auth.openai.com","sub":"user-1","client_id":"oaiapp_abcdefgh12345678",
            "generation":4,"published_models":["gpt-6.1-sol"],"model_purposes":{"gpt-6.1-sol":["llm"]},
            "catalog":{"models":[]}});
        let value =
            json!({"profiles":{(id.clone()):old},"active":null,"requests":{"q":1},"receipts":{}});
        let answer = ask(
            json!({"action":"sign_in_transfer_import","profile":profile(),
            "claims":{"sub":"user-1","email":"a@example.com"},"value":value}),
        );
        assert_eq!(answer["profile_id"], id.as_str());
        let stored = &answer["value"];
        assert_eq!(stored["active"], id.as_str());
        assert_eq!(stored["requests"], json!({"q":1}));
        let joined = &stored["profiles"][&id];
        assert_eq!(joined["generation"], 5);
        assert_eq!(joined["state"], "connected");
        assert_eq!(joined["label"], "a@example.com / 12345678");
        assert_eq!(joined["email"], "a@example.com");
        assert_eq!(joined["retained_id_token"], "old-i");
        assert_eq!(joined["published_models"], json!(["gpt-6.1-sol"]));
        assert_eq!(joined["model_metadata"], json!({}));
        assert!(joined.get("catalog").is_none());
        let fresh = ask(
            json!({"action":"sign_in_transfer_import","profile":profile(),
            "claims":{"sub":"user-1"},"value":{"profiles":{}}}),
        );
        let joined = &fresh["value"]["profiles"][&id];
        assert_eq!(joined["generation"], 1);
        assert_eq!(joined["label"], "ChatGPT / 12345678");
        assert_eq!(joined["email"], "");
        let mut other = old.clone();
        other["sub"] = json!("user-2");
        let refused = ask(
            json!({"action":"sign_in_transfer_import","profile":profile(),
            "claims":{"sub":"user-1"},"value":{"profiles":{(id.clone()):other}}}),
        );
        assert_eq!(refused["error"], "chatgpt_identity_mismatch");
        let refused = ask(
            json!({"action":"sign_in_transfer_import","profile":profile(),
            "claims":{"sub":"user-2"},"value":{"profiles":{}}}),
        );
        assert_eq!(refused["error"], INVALID);
    }
}
