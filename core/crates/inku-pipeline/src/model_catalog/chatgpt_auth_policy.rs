//! Pure OIDC policy. Signature verification, randomness and I/O remain with hosts.
use super::*;
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use subtle::ConstantTimeEq;
const ISSUER: &str = "https://auth.openai.com";
const RESOURCE: &str = "https://api.openai.com/v1";
const SCOPES: &str =
    "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct";

fn fail(code: &str) -> Value {
    json!({"error":code})
}
fn valid_endpoint(url: &str) -> bool {
    let Some((scheme, rest)) = url.split_once("://") else {
        return false;
    };
    scheme.eq_ignore_ascii_case("https")
        && rest.split(['/', '?', '#']).next() == Some("auth.openai.com")
        && !rest
            .split_once('#')
            .is_some_and(|(_, fragment)| !fragment.is_empty())
}
fn constant_equal(left: &str, right: &str) -> bool {
    bool::from(left.as_bytes().ct_eq(right.as_bytes()))
}
fn encode(value: &str) -> String {
    let mut out = String::new();
    for c in value.bytes() {
        if c.is_ascii_alphanumeric() || b"_.-~".contains(&c) {
            out.push(char::from(c));
        } else if c == b' ' {
            out.push('+');
        } else {
            out.push_str(&format!("%{c:02X}"));
        }
    }
    out
}
fn authorization(request: &Value) -> Value {
    let previous = &request["previous"];
    let verifier = request["verifier"].as_str().unwrap_or("");
    let digest = Sha256::digest(verifier.as_bytes());
    let challenge = URL_SAFE_NO_PAD.encode(digest);
    let client = previous["client_id"]
        .as_str()
        .unwrap_or("dynamic_agent_client");
    let mut pairs = vec![
        ("client_id", client),
        (
            "ext_agent_host_id",
            request["host_id"].as_str().unwrap_or(""),
        ),
        ("response_type", "code"),
        (
            "redirect_uri",
            request["redirect_uri"].as_str().unwrap_or(""),
        ),
        ("scope", SCOPES),
        ("resource", RESOURCE),
        ("state", request["state"].as_str().unwrap_or("")),
        ("nonce", request["nonce"].as_str().unwrap_or("")),
        ("code_challenge_method", "S256"),
        ("code_challenge", challenge.as_str()),
    ];
    if let Some(email) = previous["email"].as_str().filter(|v| !v.is_empty()) {
        pairs.push(("login_hint", email));
    }
    if !truthy(previous) {
        pairs.push(("agent_name_hint", "inku"));
    }
    if request["consent"] == true {
        pairs.push(("prompt", "consent"));
    }
    json!({"url":format!("{ISSUER}/api/accounts/authorize?{}",pairs.iter().map(|(k,v)|format!("{}={}",encode(k),encode(v))).collect::<Vec<_>>().join("&"))})
}
fn token_fields(request: &Value) -> Value {
    let value = &request["value"];
    let previous = &request["previous"];
    if !value["token_type"]
        .as_str()
        .is_some_and(|s| s.eq_ignore_ascii_case("bearer"))
    {
        return fail("chatgpt_identity_invalid");
    }
    for key in ["access_token", "refresh_token"] {
        if !value[key]
            .as_str()
            .is_some_and(|s| (1..=65536).contains(&s.chars().count()))
        {
            return fail("chatgpt_identity_invalid");
        }
    }
    let number = |v: &Value| -> Option<f64> {
        v.as_f64()
            .or_else(|| v.as_bool().map(|v| if v { 1.0 } else { 0.0 }))
            .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
            .filter(|v: &f64| v.is_finite())
    };
    let Some(expiry) = number(&value["expires_in"]).filter(|v| *v > 0.0 && *v <= 86400.0) else {
        return fail("chatgpt_identity_invalid");
    };
    let earliest = match value.get("earliest_refresh_at") {
        None => Some(0.0),
        Some(Value::String(text)) => text
            .parse::<jiff::Timestamp>()
            .ok()
            .or_else(|| {
                let local = text.parse::<jiff::civil::DateTime>().ok().or_else(|| {
                    text.parse::<jiff::civil::Date>()
                        .ok()
                        .map(|date| date.at(0, 0, 0, 0))
                })?;
                let offset = r_local_offset(request)?;
                offset.to_timestamp(local).ok()
            })
            .map(|t| t.as_second() as f64 + t.subsec_nanosecond() as f64 / 1_000_000_000.0),
        Some(other) => number(other),
    };
    let Some(earliest) = earliest else {
        return fail("chatgpt_identity_invalid");
    };
    let scopes = match value.get("scope") {
        Some(Value::String(s)) => json!(s.split_whitespace().collect::<Vec<_>>()),
        Some(_) => return fail("chatgpt_identity_invalid"),
        None => previous.get("scopes").cloned().unwrap_or(json!([])),
    };
    json!({"tokens":{"access_token":value["access_token"],"refresh_token":value["refresh_token"],
        "id_token":value.get("id_token").cloned().unwrap_or_else(|| previous.get("id_token").cloned().unwrap_or(json!(""))),
        "scopes":scopes,"expires_at":request["now"].as_f64().unwrap_or(0.0)+expiry,"earliest_refresh_at":earliest}})
}
fn r_local_offset(request: &Value) -> Option<jiff::tz::Offset> {
    let seconds = request["local_offset_seconds"].as_i64()?;
    jiff::tz::Offset::from_seconds(i32::try_from(seconds).ok()?).ok()
}
pub(super) fn run(r: &Value) -> Value {
    let profile = &r["profile"];
    match r["action"].as_str().unwrap_or("") {
        "chatgpt_auth_constants" => {
            json!({"issuer":ISSUER,"authorize":format!("{ISSUER}/api/accounts/authorize"),"token":format!("{ISSUER}/api/accounts/oauth/token"),"resource":RESOURCE,"scopes":SCOPES})
        }
        "chatgpt_auth_callback_client" => {
            let issued = r["issued"].as_str().unwrap_or("");
            if issued.is_empty()
                || issued == "dynamic_agent_client"
                || (truthy(&r["previous"]) && r["previous"]["client_id"] != issued)
            {
                fail("chatgpt_registration_incomplete")
            } else {
                json!({"client_id":issued})
            }
        }
        "chatgpt_auth_select" => {
            if array(r.get("profile_ids")).contains(&r["profile_id"]) {
                json!({"active":r["profile_id"]})
            } else {
                fail("chatgpt_not_connected")
            }
        }
        "chatgpt_auth_url" => authorization(r),
        "chatgpt_auth_discovery" => {
            if r["discovery"]["issuer"] != ISSUER
                || !valid_endpoint(r["discovery"]["jwks_uri"].as_str().unwrap_or(""))
            {
                fail("chatgpt_identity_invalid")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_identity" => {
            if truthy(&r["previous"])
                && !truthy(&r["previous"]["pending"])
                && r["previous"]["sub"] != r["sub"]
            {
                fail("chatgpt_identity_mismatch")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_generation" => {
            let Some(generation) = r["previous"]["generation"]
                .as_u64()
                .unwrap_or(0)
                .checked_add(1)
            else {
                return fail("chatgpt_identity_invalid");
            };
            json!({"generation":generation})
        }
        "chatgpt_auth_endpoint" => {
            if valid_endpoint(r["url"].as_str().unwrap_or("")) {
                json!({"url":r["url"]})
            } else {
                fail("chatgpt_identity_invalid")
            }
        }
        "chatgpt_auth_tokens" => token_fields(r),
        "chatgpt_auth_callback" => {
            if !constant_equal(
                r["state"].as_str().unwrap_or(""),
                r["expected_state"].as_str().unwrap_or(""),
            ) {
                fail("chatgpt_callback_invalid")
            } else if truthy(&r["error"]) {
                fail("chatgpt_consent_declined")
            } else if !truthy(&r["code"]) {
                fail("chatgpt_auth_unavailable")
            } else {
                json!({"code":r["code"]})
            }
        }
        "chatgpt_auth_claims" => {
            let claims = &r["claims"];
            let client = r["client_id"].as_str().unwrap_or("");
            let aud = &claims["aud"];
            let ok_aud = aud.as_str() == Some(client)
                || (aud.is_array()
                    && array(Some(aud)).iter().all(Value::is_string)
                    && array(Some(aud)).iter().any(|v| v.as_str() == Some(client)));
            let now = r["now"].as_f64().unwrap_or(0.0);
            let exp = claims["exp"]
                .as_i64()
                .or_else(|| {
                    claims["exp"]
                        .as_f64()
                        .filter(|v| v.is_finite())
                        .map(|v| v.trunc() as i64)
                })
                .or_else(|| claims["exp"].as_str().and_then(|v| v.parse::<i64>().ok()))
                .or_else(|| claims["exp"].as_bool().map(i64::from));
            if claims["iss"] != ISSUER
                || !ok_aud
                || !exp.is_some_and(|v| (v as f64) > now)
                || !claims["sub"].as_str().is_some_and(|s| !s.is_empty())
                || (!r["nonce"].is_null()
                    && !constant_equal(
                        claims["nonce"].as_str().unwrap_or(""),
                        r["nonce"].as_str().unwrap_or(""),
                    ))
                || (array(Some(aud)).len() > 1 && claims["azp"] != client)
            {
                fail("chatgpt_identity_invalid")
            } else {
                json!({"claims":claims})
            }
        }
        "chatgpt_auth_access" => {
            let now = r["now"].as_f64().unwrap_or(0.0);
            let expiry = profile["expires_at"].as_f64().unwrap_or(0.0);
            let earliest = profile["earliest_refresh_at"].as_f64().unwrap_or(0.0);
            if profile["refresh_owner"] != "runtime" {
                fail("chatgpt_session_transferred")
            } else if expiry > now + 60.0 || (now < earliest && expiry > now) {
                json!({"decision":"use"})
            } else if now < earliest {
                fail("chatgpt_refresh_not_ready")
            } else {
                json!({"decision":"refresh"})
            }
        }
        "chatgpt_auth_session" => {
            if profile["generation"] != r["generation"] {
                fail("chatgpt_session_changed")
            } else if profile["state"] != "connected" {
                fail(&format!(
                    "chatgpt_{}",
                    profile["state"].as_str().unwrap_or("")
                ))
            } else if !contains(profile.get("scopes"), "chatgpt.tokens.use.direct") {
                fail("chatgpt_scope_required")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_transition" => {
            let mut result = profile.clone();
            let Some(generation) = profile["generation"]
                .as_u64()
                .and_then(|n| n.checked_add(1))
            else {
                return fail("chatgpt_identity_invalid");
            };
            result["generation"] = json!(generation);
            result["state"] = r["state"].clone();
            if let Some(obj) = result.as_object_mut() {
                for key in ["access_token", "refresh_token", "id_token", "catalog"] {
                    obj.remove(key);
                }
            }
            json!({"profile":result})
        }
        "chatgpt_auth_preserve" => {
            let mut result = profile.clone();
            let old = &r["previous"];
            if old.is_object() {
                for key in ["issuer", "sub", "client_id"] {
                    if old[key] != profile[key] {
                        return fail("chatgpt_identity_mismatch");
                    }
                }
                for (key, default) in [
                    ("published_models", json!([])),
                    ("model_purposes", json!({})),
                    ("model_metadata", json!({})),
                ] {
                    result[key] = old.get(key).cloned().unwrap_or(default);
                }
            }
            json!({"profile":result})
        }
        _ => fail("unknown_action"),
    }
}
