//! Pure OIDC policy. Signature verification, randomness and I/O remain with hosts.
use super::*;
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use icu_properties::{CodePointMapData, props::GeneralCategory};
use serde::de::{Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use std::fmt;
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

fn decimal_digit(c: char) -> Option<u32> {
    if c.is_ascii_digit() {
        return c.to_digit(10);
    }
    let categories = CodePointMapData::<GeneralCategory>::new();
    if categories.get(c) != GeneralCategory::DecimalNumber {
        return None;
    }
    let mut first = c as u32;
    while first > 0
        && char::from_u32(first - 1)
            .is_some_and(|ch| categories.get(ch) == GeneralCategory::DecimalNumber)
    {
        first -= 1;
    }
    Some((c as u32 - first) % 10)
}

fn python_int(value: &Value) -> Option<f64> {
    value
        .as_i64()
        .map(|v| v as f64)
        .or_else(|| value.as_f64().filter(|v| v.is_finite()).map(|v| v.trunc()))
        .or_else(|| value.as_bool().map(|v| if v { 1.0 } else { 0.0 }))
        .or_else(|| {
            value.as_str().and_then(|s| {
                let s = s.trim();
                let chars: Vec<_> = s.chars().collect();
                if chars.iter().enumerate().any(|(i, c)| {
                    *c == '_'
                        && (i == 0
                            || i + 1 == chars.len()
                            || decimal_digit(chars[i - 1]).is_none()
                            || decimal_digit(chars[i + 1]).is_none())
                }) {
                    return None;
                }
                let normalized: String = s
                    .chars()
                    .filter(|c| *c != '_')
                    .map(|c| decimal_digit(c).map_or(c, |v| char::from_digit(v, 10).unwrap()))
                    .collect();
                let digits = normalized.strip_prefix(['+', '-']).unwrap_or(&normalized);
                if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
                    return None;
                }
                normalized.parse().ok()
            })
        })
}

// Keep object insertion order from the host's JSON when reproducing Python's
// display of an unusual non-string email claim.
struct Ordered(String);
fn ordered_repr(raw: &str) -> Result<String, serde_json::Error> {
    let raw = raw.trim();
    // The host serializes this value from its decoded JSON, so number text is
    // already Python's exact representation, including large integers.
    if raw.starts_with(|c: char| c == '-' || c.is_ascii_digit()) {
        return Ok(raw.to_owned());
    }
    serde_json::from_str::<Ordered>(raw).map(|value| value.0)
}
impl<'de> Deserialize<'de> for Ordered {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Ordered;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON value")
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Ordered, E> {
                Ok(Ordered("None".into()))
            }
            fn visit_bool<E: serde::de::Error>(self, v: bool) -> Result<Ordered, E> {
                Ok(Ordered(if v { "True" } else { "False" }.into()))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> Result<Ordered, E> {
                Ok(Ordered(v.to_string()))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> Result<Ordered, E> {
                Ok(Ordered(v.to_string()))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> Result<Ordered, E> {
                let s = format!("{v:?}");
                let s = if let Some((mantissa, exponent)) = s.split_once('e') {
                    let n: i32 = exponent.parse().unwrap_or(0);
                    format!(
                        "{mantissa}e{}{num:02}",
                        if n >= 0 { '+' } else { '-' },
                        num = n.abs()
                    )
                } else {
                    s
                };
                Ok(Ordered(s))
            }
            fn visit_str<E: serde::de::Error>(self, v: &str) -> Result<Ordered, E> {
                Ok(Ordered(python_repr(&json!(v), true)))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<Ordered, A::Error> {
                let mut values = Vec::new();
                while let Some(v) = a.next_element::<Box<serde_json::value::RawValue>>()? {
                    values.push(ordered_repr(v.get()).map_err(serde::de::Error::custom)?);
                }
                Ok(Ordered(format!("[{}]", values.join(", "))))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<Ordered, A::Error> {
                let mut values = Vec::new();
                while let Some((k, v)) =
                    a.next_entry::<String, Box<serde_json::value::RawValue>>()?
                {
                    values.push(format!(
                        "{}: {}",
                        python_repr(&json!(k), true),
                        ordered_repr(v.get()).map_err(serde::de::Error::custom)?
                    ));
                }
                Ok(Ordered(format!("{{{}}}", values.join(", "))))
            }
        }
        d.deserialize_any(V)
    }
}

fn python_repr(value: &Value, nested: bool) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(v) => if *v { "True" } else { "False" }.into(),
        Value::String(s) if !nested => s.clone(),
        Value::String(s) => {
            let quote = if s.contains('\'') && !s.contains('"') {
                '"'
            } else {
                '\''
            };
            let mut out = String::from(quote);
            for ch in s.chars() {
                if ch == quote || ch == '\\' {
                    out.push('\\');
                    out.push(ch);
                } else if ch == '\n' {
                    out.push_str("\\n");
                } else if ch == '\r' {
                    out.push_str("\\r");
                } else if ch == '\t' {
                    out.push_str("\\t");
                } else if ch != ' '
                    && matches!(
                        CodePointMapData::<GeneralCategory>::new().get(ch),
                        GeneralCategory::Unassigned
                            | GeneralCategory::SpaceSeparator
                            | GeneralCategory::LineSeparator
                            | GeneralCategory::ParagraphSeparator
                            | GeneralCategory::Control
                            | GeneralCategory::Format
                            | GeneralCategory::PrivateUse
                            | GeneralCategory::Surrogate
                    )
                {
                    let value = ch as u32;
                    if value <= 0xff {
                        out.push_str(&format!("\\x{value:02x}"));
                    } else if value <= 0xffff {
                        out.push_str(&format!("\\u{value:04x}"));
                    } else {
                        out.push_str(&format!("\\U{value:08x}"));
                    }
                } else {
                    out.push(ch);
                }
            }
            out.push(quote);
            out
        }
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(|v| python_repr(v, true))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(k, v)| format!("{}: {}", python_repr(&json!(k), true), python_repr(v, true)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Number(_) => value.to_string(),
    }
}
pub(super) fn run(r: &Value) -> Value {
    let profile = &r["profile"];
    match r["action"].as_str().unwrap_or("") {
        "chatgpt_auth_http" => {
            if r["json_valid"] == false {
                return fail("chatgpt_auth_unavailable");
            }
            let status = r["status"].as_u64().unwrap_or(0);
            let value = &r["value"];
            if !(200..300).contains(&status) {
                let mut code = &value["error"];
                if code.is_object() {
                    code = &code["code"];
                }
                if code.is_array() || code.is_object() {
                    return json!({"type_error":true});
                }
                if [
                    "invalid_grant",
                    "invalid_refresh_token",
                    "token_expired",
                    "refresh_token_expired",
                    "refresh_token_invalidated",
                    "refresh_token_reused",
                ]
                .iter()
                .any(|s| code == *s)
                {
                    return fail("chatgpt_reauthentication_required");
                }
                return fail(if status >= 500 {
                    "chatgpt_auth_unavailable"
                } else {
                    "chatgpt_auth_rejected"
                });
            }
            if !value.is_object() {
                fail("chatgpt_identity_invalid")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_key" => {
            let header = &r["header"];
            let metadata = &r["discovery"];
            let defaults = json!(["RS256"]);
            let allowed = metadata
                .get("id_token_signing_alg_values_supported")
                .unwrap_or(&defaults);
            let alg = &header["alg"];
            if !(alg == "RS256" || alg == "ES256") || !array(Some(allowed)).contains(alg) {
                return fail("chatgpt_identity_invalid");
            }
            let Some(keys) = r["keys"]["keys"].as_array() else {
                return fail("chatgpt_identity_invalid");
            };
            if keys.iter().any(|key| !key.is_object()) {
                return fail("chatgpt_identity_invalid");
            }
            let matches: Vec<_> = keys
                .iter()
                .filter(|key| {
                    key["kid"] == header["kid"] && key.get("use").unwrap_or(&json!("sig")) == "sig"
                })
                .collect();
            if matches.len() != 1 {
                fail("chatgpt_identity_invalid")
            } else {
                json!({"key":matches[0], "alg":alg})
            }
        }
        "chatgpt_auth_publication_active" => {
            if r["active"] != r["profile_id"] {
                fail("chatgpt_session_changed")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_resume_quota" => {
            if !truthy(profile) || profile["state"] != "quota" {
                fail("chatgpt_not_connected")
            } else {
                let mut next = profile.clone();
                next["state"] = json!("connected");
                json!({"profile":next})
            }
        }
        "chatgpt_auth_quota_failure" => {
            json!({"pause":r["code"] == "subscription_sharing_usage_limit_exceeded"})
        }
        "chatgpt_auth_save_check" => {
            let previous = &r["previous"];
            let expected = &r["expected_generation"];
            if !expected.is_null() && (!truthy(previous) || previous["generation"] != *expected) {
                fail("chatgpt_session_changed")
            } else if !truthy(previous) && r["count"].as_u64().unwrap_or(0) >= 8 {
                fail("chatgpt_profile_limit")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_pending_check" => {
            if r["exists"] != true && r["count"].as_u64().unwrap_or(0) >= 8 {
                fail("chatgpt_profile_limit")
            } else {
                json!({"valid":true})
            }
        }
        "chatgpt_auth_display" => {
            let claims = &r["claims"];
            let shown = |fallback: &str| {
                if let Some(raw) = r["email_json"].as_str()
                    && let Ok(value) = serde_json::from_str::<Value>(raw)
                {
                    if let Some(s) = value.as_str() {
                        return s.to_owned();
                    }
                    if let Ok(value) = ordered_repr(raw) {
                        return value;
                    }
                }
                python_repr(claims.get("email").unwrap_or(&json!(fallback)), false)
            };
            let email = shown("").chars().take(254).collect::<String>();
            let label = shown("ChatGPT").chars().take(254).collect::<String>();
            let issued = r["client_id"].as_str().unwrap_or("");
            let tail: String = issued
                .chars()
                .rev()
                .take(8)
                .collect::<String>()
                .chars()
                .rev()
                .collect();
            json!({"email":email,"label":format!("{label} / {tail}")})
        }
        "chatgpt_auth_refresh_profile" => {
            let mut next = profile.clone();
            if let (Some(dst), Some(tokens)) = (next.as_object_mut(), r["tokens"].as_object()) {
                dst.extend(tokens.clone());
                dst.remove("catalog");
            }
            json!({"profile":next})
        }
        "chatgpt_auth_revocation" => {
            json!({"send":truthy(&profile["refresh_token"]) && profile["refresh_owner"] == "runtime", "confirmed":r["status"] == 200})
        }
        "chatgpt_auth_pause_quota" => {
            if !profile.is_object()
                || profile["generation"] != r["generation"]
                || profile["state"] == "quota"
            {
                json!({"changed":false})
            } else {
                let mut next = profile.clone();
                next["state"] = json!("quota");
                next.as_object_mut().unwrap().remove("catalog");
                json!({"changed":true,"profile":next})
            }
        }
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
            if ["iat", "nbf"].iter().any(|key| {
                claims
                    .get(*key)
                    .is_some_and(|v| !python_int(v).is_some_and(|i| i <= now))
            }) || claims.get("jti").is_some_and(|v| !v.is_string())
                || claims["iss"] != ISSUER
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
