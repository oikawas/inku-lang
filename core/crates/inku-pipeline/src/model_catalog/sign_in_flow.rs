//! A sign-in's procedures, step for step (SIWC step 5, 2026-11-14): the host
//! starts a procedure, does the one thing each answer names (`todo`) and gives
//! back the answer's `state` with what came of it. The procedures are Server's
//! (`chatgpt_auth.py`, `chatgpt_provider.py`), with the disagreements among
//! the three hosts settled by the author's table (PLAN-STEP5 §5): the lengths
//! of the random values, the strict reading of the callback's request head,
//! the bilingual callback page, form bodies in their field order, reading the
//! store again under its lock before a model list is kept, and a sign-out of a
//! registration already signed out leaving its generation alone.
//!
//! What stays with the host: sockets, the browser and the sign-in window,
//! sending HTTP within the deadline each `http` names, verifying a signature,
//! randomness, the store's encryption and its locks, waiting, and when it may
//! send (Android sends the token exchange only once inku is in front). The
//! host owns the attempt's bookkeeping (how many are pending, cancelling one)
//! and gives the counts when it starts a sign-in; to stop a procedure it
//! stops asking and releases the locks the last answer lists in `held`.
//!
//! The store a host reads and writes is one JSON object: `profiles` by id,
//! `registrations_pending` by id, `active`, and any fields of its own, kept as
//! they are. Times are seconds on the clock the host gives as `now`.

use super::chatgpt_auth_policy;
use super::sign_in::{chatgpt, count, text};
use super::*;
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};

fn login() -> &'static Value {
    &chatgpt()["login"]
}
fn flow_limit(name: &str) -> f64 {
    count(&login()["flow_limits"][name]) as f64
}

/// A step's failure: a code, or a whole failure answer (an HTTP error's).
type Step = Result<Value, Value>;

fn code_failure(code: &str) -> Value {
    let answer = wire(json!({"action":"chatgpt_failure","code":code}));
    json!({"code":code,"failure":answer["failure"],"action":answer["action"]})
}

fn wire(request: Value) -> Value {
    let bytes = crate::provider_wire::provider_wire_json(request.to_string().as_bytes());
    serde_json::from_slice(&bytes).expect("the wire answers JSON")
}

/// A part of the sign-in policy (`chatgpt_auth_*`), its error as a failure.
fn part(action: &str, mut fields: Value) -> Step {
    fields["action"] = json!(format!("chatgpt_auth_{action}"));
    let answer = chatgpt_auth_policy::run(&fields);
    match answer.get("error").and_then(Value::as_str) {
        Some(code) => Err(code_failure(code)),
        None => Ok(answer),
    }
}

fn fail_code<T>(code: &str) -> Result<T, Value> {
    Err(code_failure(code))
}

/// The form body of a token request, in its field order, as httpx writes it.
fn form(fields: &[(&str, &str)]) -> String {
    fields
        .iter()
        .map(|(key, value)| format!("{}={}", form_encode(key), form_encode(value)))
        .collect::<Vec<_>>()
        .join("&")
}
fn form_encode(value: &str) -> String {
    let mut out = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || b"_.-~".contains(&byte) {
            out.push(char::from(byte));
        } else if byte == b' ' {
            out.push('+');
        } else {
            out.push_str(&format!("%{byte:02X}"));
        }
    }
    out
}

/// A UUID (version 4) from sixteen random bytes.
fn uuid4(bytes: &[u8]) -> Option<String> {
    let mut b: [u8; 16] = bytes.try_into().ok()?;
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    let hex: String = b.iter().map(|byte| format!("{byte:02x}")).collect();
    Some(format!(
        "{}-{}-{}-{}-{}",
        &hex[0..8],
        &hex[8..12],
        &hex[12..16],
        &hex[16..20],
        &hex[20..32]
    ))
}

/// The callback's request head (without its closing blank line): the target
/// of a `GET` to `127.0.0.1:<port>` that carries no body, or nothing.
fn callback_target(head: &[u8], port: u64) -> Option<String> {
    let limits = &login()["callback_head"];
    if head.len() > count(&limits["header_bytes"]) as usize
        || !head
            .iter()
            .all(|b| matches!(b, 9 | 10 | 13) || (32..=126).contains(b))
    {
        return None;
    }
    let text = std::str::from_utf8(head).ok()?;
    let lines: Vec<&str> = text.split("\r\n").collect();
    if lines.len() > count(&limits["lines"]) as usize {
        return None;
    }
    let parts: Vec<&str> = lines[0].split(' ').collect();
    if parts.len() != 3
        || parts[0] != "GET"
        || parts[1].len() > count(&limits["target_bytes"]) as usize
        || !matches!(parts[2], "HTTP/1.1" | "HTTP/1.0")
    {
        return None;
    }
    let mut headers = std::collections::BTreeMap::new();
    for line in &lines[1..] {
        let colon = line.find(':').filter(|at| *at > 0)?;
        let name = line[..colon].to_ascii_lowercase();
        if !name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            || headers.contains_key(&name)
        {
            return None;
        }
        headers.insert(name, line[colon + 1..].trim_matches([' ', '\t']).to_owned());
    }
    let length = headers.get("content-length").map(String::as_str);
    (headers.get("host").map(String::as_str) == Some(&format!("127.0.0.1:{port}"))
        && !headers.contains_key("transfer-encoding")
        && matches!(length, None | Some("0")))
    .then(|| parts[1].to_owned())
}

fn callback_page(language: &str, completed: bool) -> (u64, Value, String) {
    page(language, if completed { "completed" } else { "failed" })
}

/// The page a callback is answered with: `completed`, `failed`, or `received`
/// (the callback taken before the exchange, for a host that sends it only
/// once inku is in front again).
fn page(language: &str, kind: &str) -> (u64, Value, String) {
    let completed = kind != "failed";
    let page = &login()["callback_page"][if language == "ja" { "ja" } else { "en" }][kind];
    let (title, message) = (text(&page[0]), text(&page[1]));
    let language = if language == "ja" { "ja" } else { "en" };
    (
        if completed { 200 } else { 400 },
        json!({"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store",
            "Referrer-Policy":"no-referrer","Connection":"close"}),
        format!(
            r#"<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head><body><main><h1>{title}</h1><p>{message}</p></main></body></html>"#
        ),
    )
}

/// A registration signed out or waiting to sign in again keeps its last
/// id token as the hint its next sign-in sends (OpenAI's account
/// registrations: "a retained id_token" as `id_token_hint`).
fn retain_hint(next: &mut Value, previous: &Value) {
    if let Some(token) = previous["id_token"].as_str().filter(|t| !t.is_empty()) {
        next["retained_id_token"] = json!(token);
    }
}

/// A procedure in progress.
struct Flow {
    state: Value,
    now: f64,
}

impl Flow {
    fn data(&mut self) -> &mut Value {
        &mut self.state["data"]
    }
    fn get(&self, name: &str) -> &Value {
        &self.state["data"][name]
    }
    fn set(&mut self, name: &str, value: Value) {
        self.data()[name] = value;
    }
    fn input(&self, name: &str) -> &Value {
        &self.state["input"][name]
    }
    fn deadline(&self) -> f64 {
        self.state["deadline"].as_f64().unwrap_or(self.now)
    }
    fn go(&mut self, step: &str) {
        self.state["step"] = json!(step);
    }
    fn held(&mut self) -> &mut Vec<Value> {
        if !self.state["held"].is_array() {
            self.state["held"] = json!([]);
        }
        self.state["held"].as_array_mut().expect("held is a list")
    }

    fn answer(mut self, todo: Value) -> Value {
        let held = self.held().clone();
        json!({"state":self.state,"todo":todo,"held":held,"deadline":self.state["deadline"]})
    }
    fn todo(mut self, step: &str, todo: Value) -> Value {
        self.go(step);
        self.answer(todo)
    }

    fn acquire(mut self, step: &str, lock: &str, deadline: f64) -> Value {
        self.set("acquiring", json!(lock));
        self.todo(
            step,
            json!({"todo":"acquire","lock":lock,"deadline":deadline}),
        )
    }
    fn release(mut self, step: &str, lock: &str) -> Value {
        self.held().retain(|held| held != lock);
        self.todo(step, json!({"todo":"release","lock":lock}))
    }

    /// A step's failure: release what is held, answer the callback page if a
    /// sign-in had used its callback, then name the failure.
    fn failed(mut self, failure: Value) -> Value {
        if let Some(soft) = self.get("soft").as_str().map(str::to_owned) {
            self.set("soft", Value::Null);
            self.set("revocation_confirmed", json!(false));
            return self.resume(&soft, &Value::Null);
        }
        self.state["failing"] = failure;
        self.unwind()
    }
    fn unwind(mut self) -> Value {
        if let Some(lock) = self.held().pop() {
            return self.todo("unwind", json!({"todo":"release","lock":lock}));
        }
        if self.get("respond_failed") == true {
            self.set("respond_failed", json!(false));
            let (status, headers, body) =
                callback_page(self.input("language").as_str().unwrap_or("en"), false);
            return self.todo(
                "unwind",
                json!({"todo":"respond","status":status,"headers":headers,"body":body}),
            );
        }
        let mut failure = self.state["failing"].clone();
        failure["todo"] = json!("failed");
        self.answer(failure)
    }

    fn done(self, answer: Value) -> Value {
        let mut todo = answer;
        todo["todo"] = json!("done");
        self.answer(todo)
    }

    // -----------------------------------------------------------------------
    // HTTP.

    fn http(
        mut self,
        step: &str,
        purpose: &str,
        method: &str,
        url: &str,
        body: Option<String>,
        limit: f64,
    ) -> Value {
        let mut todo = json!({"todo":"http","purpose":purpose,"method":method,"url":url,
            "headers":{},"deadline":self.deadline(),"answer_limit":limit,"error_limit":limit});
        if let Some(body) = body {
            todo["headers"] = json!({"Content-Type":"application/x-www-form-urlencoded"});
            todo["body"] = json!(body);
        }
        self.set("http_purpose", json!(purpose));
        self.todo(step, todo)
    }

    /// An answer from the sign-in server, read as `auth_json` reads it.
    fn auth_json(result: &Value) -> Step {
        if let Some(kind) = result["transport"].as_str() {
            let answer = wire(json!({"action":"chatgpt_transport","kind":kind}));
            return Err(
                json!({"code":answer["code"],"failure":answer["failure"],"action":answer["action"]}),
            );
        }
        let status = result["status"].as_u64().unwrap_or(0);
        let parsed = result["body"]
            .as_str()
            .and_then(|body| serde_json::from_str::<Value>(body).ok());
        let Some(value) = parsed else {
            part("http", json!({"status":status,"json_valid":false}))?;
            return fail_code("chatgpt_auth_unavailable");
        };
        let checked = part(
            "http",
            json!({"status":status,"json_valid":true,"value":value}),
        )?;
        if checked["type_error"] == true {
            return fail_code("chatgpt_auth_unavailable");
        }
        Ok(value)
    }

    // -----------------------------------------------------------------------
    // The store.

    fn profile_of(&self, store: &Value) -> Value {
        let id = self.input("profile_id").as_str().unwrap_or("");
        store["profiles"][id].clone()
    }

    /// `check_session`: the registration this procedure is for, still the
    /// generation it was given, connected and allowed to use the plan.
    fn session(&self, store: &Value) -> Step {
        let profile = self.profile_of(store);
        if !profile.is_object() {
            return fail_code("chatgpt_not_connected");
        }
        part(
            "session",
            json!({"profile":profile,"generation":self.input("generation")}),
        )?;
        Ok(profile)
    }

    /// `save_profile`: the registration kept, its newer model choices kept.
    fn save(
        store: &mut Value,
        profile: Value,
        expected: Value,
        activate: bool,
    ) -> Result<(), Value> {
        let id = profile["id"].as_str().unwrap_or("").to_owned();
        let previous = store["profiles"][&id].clone();
        let count = store["profiles"].as_object().map_or(0, Map::len);
        part(
            "save_check",
            json!({"previous":if previous.is_null(){Value::Null}else{previous.clone()},
                "expected_generation":expected,"count":count}),
        )?;
        let profile = if truthy(&previous) {
            part("preserve", json!({"profile":profile,"previous":previous}))?["profile"].clone()
        } else {
            profile
        };
        if !store["profiles"].is_object() {
            store["profiles"] = json!({});
        }
        store["profiles"][&id] = profile;
        if activate {
            store["active"] = json!(id);
        }
        Ok(())
    }

    // -----------------------------------------------------------------------
    // The steps.

    fn resume(self, step: &str, result: &Value) -> Value {
        match self.step(step, result) {
            Ok(answer) => answer,
            Err((flow, failure)) => flow.failed(failure),
        }
    }

    fn step(mut self, step: &str, result: &Value) -> Result<Value, (Flow, Value)> {
        macro_rules! check {
            ($e:expr) => {
                match $e {
                    Ok(v) => v,
                    Err(f) => return Err((self, f)),
                }
            };
        }
        // The lock the last answer asked for: held, or not had by its deadline.
        if let Some(lock) = self.get("acquiring").as_str().map(str::to_owned) {
            self.set("acquiring", Value::Null);
            if result["acquired"] != true {
                let code = if self.state["flow"] == "login" {
                    "chatgpt_auth_unavailable"
                } else {
                    "chatgpt_transport_timeout"
                };
                return Err((self, code_failure(code)));
            }
            self.held().push(json!(lock));
        }
        let limit = flow_limit("auth_answer_limit");
        let issuer = text(&login()["issuer"]);
        let token_url = format!("{issuer}{}", text(&login()["token_path"]));
        let resource = text(&login()["resource"]);
        Ok(match step {
            "unwind" => self.unwind(),

            // ---- the identity: discovery, keys, signature, claims ----
            "id_begin" => {
                let url = format!("{issuer}{}", text(&login()["discovery_path"]));
                self.http("id_discovery", "discovery", "GET", &url, None, limit)
            }
            "id_discovery" => {
                let discovery = check!(Self::auth_json(result));
                check!(part("discovery", json!({"discovery":discovery})));
                let jwks = discovery["jwks_uri"].as_str().unwrap_or("").to_owned();
                check!(part("endpoint", json!({"url":jwks})));
                self.set("discovery", discovery);
                self.http("id_keys", "jwks", "GET", &jwks, None, limit)
            }
            "id_keys" => {
                let keys = check!(Self::auth_json(result));
                let token = self.get("id_token").as_str().unwrap_or("").to_owned();
                let parts: Vec<&str> = token.split('.').collect();
                let decoded = |part: &str| URL_SAFE_NO_PAD.decode(part).ok();
                let (Some(header), Some(payload), Some(_)) = (
                    parts.first().and_then(|p| decoded(p)),
                    parts.get(1).and_then(|p| decoded(p)),
                    parts.get(2).and_then(|p| decoded(p)),
                ) else {
                    return Err((self, code_failure("chatgpt_identity_invalid")));
                };
                if parts.len() != 3 {
                    return Err((self, code_failure("chatgpt_identity_invalid")));
                }
                let (Ok(header), Ok(payload)) = (
                    serde_json::from_slice::<Value>(&header),
                    String::from_utf8(payload),
                ) else {
                    return Err((self, code_failure("chatgpt_identity_invalid")));
                };
                let chosen = check!(part(
                    "key",
                    json!({"header":header,"discovery":self.get("discovery"),"keys":keys})
                ));
                self.set("payload", json!(payload));
                let signed = format!("{}.{}", parts[0], parts[1]);
                let signature = parts[2].to_owned();
                self.todo(
                    "id_verified",
                    json!({"todo":"verify","alg":chosen["alg"],"key":chosen["key"],
                        "signing_input":signed,"signature":signature}),
                )
            }
            "id_verified" => {
                if result["valid"] != true {
                    return Err((self, code_failure("chatgpt_identity_invalid")));
                }
                let payload = self.get("payload").as_str().unwrap_or("").to_owned();
                let Ok(claims) = serde_json::from_str::<Value>(&payload) else {
                    return Err((self, code_failure("chatgpt_identity_invalid")));
                };
                let email = serde_json::from_str::<
                    std::collections::HashMap<String, Box<serde_json::value::RawValue>>,
                >(&payload)
                .ok()
                .and_then(|members| members.get("email").map(|raw| raw.get().to_owned()));
                let nonce = self.get("nonce").clone();
                let client = self.get("client_id").clone();
                check!(part(
                    "claims",
                    json!({"claims":claims,"client_id":client,"nonce":nonce,"now":self.now})
                ));
                self.set("claims", claims);
                self.set("email_json", email.map_or(Value::Null, Value::String));
                let after = self.get("id_after").as_str().unwrap_or("").to_owned();
                return Ok(self.resume(&after, &Value::Null));
            }

            // ---- token fields, with the local offset a date may need ----
            "tokens_begin" => {
                let earliest = self.get("token_value")["earliest_refresh_at"].clone();
                if let Some(local) = earliest.as_str()
                    && local.parse::<jiff::Timestamp>().is_err()
                    && (local.parse::<jiff::civil::DateTime>().is_ok()
                        || local.parse::<jiff::civil::Date>().is_ok())
                {
                    let local = local.to_owned();
                    return Ok(self.todo("tokens_offset", json!({"todo":"offset","local":local})));
                }
                return Ok(self.resume("tokens_offset", &Value::Null));
            }
            "tokens_offset" => {
                let tokens = check!(part(
                    "tokens",
                    json!({"value":self.get("token_value"),"previous":self.get("token_previous"),
                        "now":self.now,"local_offset_seconds":result["seconds"]})
                ));
                self.set("tokens", tokens["tokens"].clone());
                let after = self.get("tokens_after").as_str().unwrap_or("").to_owned();
                return Ok(self.resume(&after, &Value::Null));
            }

            // ---- access: use the token or refresh it ----
            "ac_begin" => {
                let deadline = self.deadline();
                self.acquire("ac_got", "refresh", deadline)
            }
            "ac_got" => self.todo("ac_read", json!({"todo":"read"})),
            "ac_read" => {
                let profile = check!(self.session(&result["value"]));
                let decision = check!(part("access", json!({"profile":profile,"now":self.now})));
                if decision["decision"] == "use" {
                    self.set("access_token", profile["access_token"].clone());
                    return Ok(self.release("ac_done", "refresh"));
                }
                self.set("profile", profile.clone());
                let body = form(&[
                    ("grant_type", "refresh_token"),
                    ("client_id", profile["client_id"].as_str().unwrap_or("")),
                    (
                        "refresh_token",
                        profile["refresh_token"].as_str().unwrap_or(""),
                    ),
                    ("resource", resource),
                ]);
                self.http(
                    "ac_refreshed",
                    "token_refresh",
                    "POST",
                    &token_url,
                    Some(body),
                    limit,
                )
            }
            "ac_refreshed" => {
                let value = match Self::auth_json(result) {
                    Ok(value) => value,
                    Err(failure) if failure["code"] == "chatgpt_reauthentication_required" => {
                        self.set("reauth", failure);
                        let deadline = self.deadline();
                        return Ok(self.acquire("ac_reauth_got", "edit", deadline));
                    }
                    Err(failure) => return Err((self, failure)),
                };
                self.set("token_value", value.clone());
                self.set("token_previous", self.get("profile").clone());
                self.set("tokens_after", json!("ac_tokens"));
                if value["id_token"].as_str().is_some_and(|t| !t.is_empty()) {
                    self.set("id_token", value["id_token"].clone());
                    self.set("client_id", self.get("profile")["client_id"].clone());
                    self.set("nonce", Value::Null);
                    self.set("id_after", json!("ac_identity"));
                    return Ok(self.resume("id_begin", &Value::Null));
                }
                return Ok(self.resume("tokens_begin", &Value::Null));
            }
            "ac_identity" => {
                let sub = self.get("claims")["sub"].clone();
                check!(part(
                    "identity",
                    json!({"previous":self.get("profile"),"sub":sub})
                ));
                return Ok(self.resume("tokens_begin", &Value::Null));
            }
            "ac_tokens" => {
                let profile = check!(part(
                    "refresh_profile",
                    json!({"profile":self.get("profile"),"tokens":self.get("tokens")})
                ))["profile"]
                    .clone();
                self.set("profile", profile);
                let deadline = self.deadline();
                self.acquire("ac_save_got", "edit", deadline)
            }
            "ac_save_got" => self.todo("ac_save_read", json!({"todo":"read"})),
            "ac_save_read" => {
                let mut store = result["value"].clone();
                let profile = self.get("profile").clone();
                let generation = self.input("generation").clone();
                check!(Self::save(&mut store, profile.clone(), generation, false));
                self.set("access_token", profile["access_token"].clone());
                self.todo("ac_saved", json!({"todo":"write","value":store}))
            }
            "ac_saved" => {
                self.set("refreshed", json!(true));
                self.release("ac_released", "edit")
            }
            "ac_released" => self.release("ac_done", "refresh"),
            "ac_reauth_got" => self.todo("ac_reauth_read", json!({"todo":"read"})),
            "ac_reauth_read" => {
                let mut store = result["value"].clone();
                let mut profile = check!(part(
                    "transition",
                    json!({"profile":self.get("profile"),"state":"reauthentication_required"})
                ))["profile"]
                    .clone();
                retain_hint(&mut profile, self.get("profile"));
                let generation = self.input("generation").clone();
                check!(Self::save(&mut store, profile, generation, false));
                self.todo("ac_reauth_saved", json!({"todo":"write","value":store}))
            }
            "ac_reauth_saved" => {
                let failure = self.get("reauth").clone();
                return Err((self, failure));
            }
            "ac_done" => {
                // A refreshed registration is read again before it is used, as
                // Server's session check does before it sends: a refresh that
                // dropped the plan's scope stops here.
                if self.get("refreshed") == true {
                    self.set("refreshed", json!(false));
                    return Ok(self.todo("ac_checked", json!({"todo":"read"})));
                }
                return Ok(self.resume("ac_checked", &Value::Null));
            }
            "ac_checked" => {
                if result["value"].is_object() {
                    check!(self.session(&result["value"]));
                }
                let after = self.get("ac_after").as_str().unwrap_or("").to_owned();
                if after.is_empty() {
                    let token = self.get("access_token").clone();
                    return Ok(self.done(json!({"access_token":token})));
                }
                return Ok(self.resume(&after, &Value::Null));
            }

            // ---- the model list ----
            "ca_begin" => self.todo("ca_read", json!({"todo":"read"})),
            "ca_read" | "ca_wire_read" => {
                let profile = check!(self.session(&result["value"]));
                let cache = check!(part_policy(
                    "chatgpt_cache",
                    json!({"cache":profile["catalog"],"force":self.input("force"),"now":self.now})
                ));
                if cache["fresh"] == true && profile["catalog"].is_object() {
                    let models = profile["catalog"]["models"].clone();
                    self.set("models", models);
                    if step == "ca_wire_read" {
                        return Ok(self.release("ca_cached", "wire"));
                    }
                    return Ok(self.resume("ca_cached", &Value::Null));
                }
                if step == "ca_read" {
                    let deadline = self.deadline();
                    return Ok(self.acquire("ca_wire_got", "wire", deadline));
                }
                self.set("ac_after", json!("ca_fetch"));
                return Ok(self.resume("ac_begin", &Value::Null));
            }
            "ca_wire_got" => self.todo("ca_wire_read", json!({"todo":"read"})),
            "ca_cached" => {
                let models = self.get("models").clone();
                return Ok(self.done(json!({"models":models,"cached":true})));
            }
            "ca_fetch" => {
                let sent = wire(json!({"action":"chatgpt_models_request"}));
                let token = self.get("access_token").as_str().unwrap_or("").to_owned();
                let mut headers = sent["headers"].clone();
                headers[sent["auth"]["header"].as_str().unwrap_or("Authorization")] = json!(
                    format!("{}{token}", sent["auth"]["prefix"].as_str().unwrap_or(""))
                );
                let deadline = self.deadline();
                self.todo(
                    "ca_fetched",
                    json!({"todo":"http","purpose":"models","method":sent["method"],"url":sent["url"],
                        "headers":headers,"deadline":deadline,"answer_limit":sent["answer_limit"],
                        "error_limit":sent["error_limit"],"request_id_header":sent["request_id_header"]}),
                )
            }
            "ca_fetched" => {
                if let Some(kind) = result["transport"].as_str() {
                    let answer = wire(json!({"action":"chatgpt_transport","kind":kind}));
                    let failure = json!({"code":answer["code"],"failure":answer["failure"],"action":answer["action"]});
                    return Err((self, failure));
                }
                let status = result["status"].as_i64().unwrap_or(0);
                let body = result["body"].as_str().unwrap_or("").to_owned();
                if !(200..300).contains(&status) {
                    let mut error = wire(json!({"action":"chatgpt_error","status":status,
                        "body":body,"request_id":result["request_id"]}));
                    for name in ["schema", "outcome"] {
                        error.as_object_mut().map(|e| e.remove(name));
                    }
                    let pause = check!(part("quota_failure", json!({"code":error["code"]})));
                    if pause["pause"] == true {
                        self.set("ca_failure", error);
                        let deadline = self.deadline();
                        return Ok(self.acquire("ca_pause_got", "edit", deadline));
                    }
                    return Err((self, error));
                }
                let listed = wire(json!({"action":"chatgpt_catalog","body":body}));
                if listed["outcome"] != "ok" {
                    let failure = json!({"code":listed["code"],"failure":listed["failure"],"action":listed["action"]});
                    return Err((self, failure));
                }
                self.set("models", listed["models"].clone());
                let deadline = self.deadline();
                self.acquire("ca_save_got", "edit", deadline)
            }
            "ca_pause_got" => self.todo("ca_pause_read", json!({"todo":"read"})),
            "ca_pause_read" => {
                let mut store = result["value"].clone();
                let profile = self.profile_of(&store);
                let paused = check!(part(
                    "pause_quota",
                    json!({"profile":profile,"generation":self.input("generation")})
                ));
                if paused["changed"] == true {
                    let id = self.input("profile_id").as_str().unwrap_or("").to_owned();
                    store["profiles"][id] = paused["profile"].clone();
                    return Ok(self.todo("ca_pause_saved", json!({"todo":"write","value":store})));
                }
                return Ok(self.resume("ca_pause_saved", &Value::Null));
            }
            "ca_pause_saved" => {
                let failure = self.get("ca_failure").clone();
                return Err((self, failure));
            }
            "ca_save_got" => self.todo("ca_save_read", json!({"todo":"read"})),
            "ca_save_read" => {
                let mut store = result["value"].clone();
                let mut profile = check!(self.session(&store));
                let expires = check!(part_policy(
                    "chatgpt_cache",
                    json!({"cache":null,"force":true,"now":self.now})
                ))["expires_at"]
                    .clone();
                profile["catalog"] = json!({"expires_at":expires,"models":self.get("models")});
                let id = self.input("profile_id").as_str().unwrap_or("").to_owned();
                store["profiles"][id] = profile;
                self.todo("ca_saved", json!({"todo":"write","value":store}))
            }
            "ca_saved" => self.release("ca_released", "edit"),
            "ca_released" => self.release("ca_done", "wire"),
            "ca_done" => {
                let models = self.get("models").clone();
                return Ok(self.done(json!({"models":models,"cached":false})));
            }

            // ---- sign-out and revocation ----
            "so_begin" => {
                let deadline = self.now + flow_limit("edit_lock_seconds");
                self.acquire("so_got", "edit", deadline)
            }
            "so_got" => self.todo("so_read", json!({"todo":"read"})),
            "so_read" => {
                let mut store = result["value"].clone();
                let profile = self.profile_of(&store);
                if !truthy(&profile) {
                    return Err((self, code_failure("chatgpt_not_connected")));
                }
                self.set("old", profile.clone());
                if profile["state"] == "signed_out" {
                    return Ok(self.release("so_released", "edit"));
                }
                let mut next = check!(part(
                    "transition",
                    json!({"profile":profile,"state":"signed_out"})
                ))["profile"]
                    .clone();
                retain_hint(&mut next, &profile);
                let id = self.input("profile_id").as_str().unwrap_or("").to_owned();
                store["profiles"][id] = next;
                self.todo("so_saved", json!({"todo":"write","value":store}))
            }
            "so_saved" => self.release("so_released", "edit"),
            "so_released" => {
                let old = self.get("old").clone();
                self.set("revocation_confirmed", json!(false));
                let send = check!(part("revocation", json!({"profile":old})));
                if send["send"] != true {
                    return Ok(self.resume("so_done", &Value::Null));
                }
                self.state["deadline"] = json!(self.now + flow_limit("revocation_seconds"));
                self.set("soft", json!("so_done"));
                let url = format!("{issuer}{}", text(&login()["discovery_path"]));
                self.http("so_discovery", "discovery", "GET", &url, None, limit)
            }
            "so_discovery" => {
                let discovery = check!(Self::auth_json(result));
                check!(part("discovery", json!({"discovery":discovery})));
                let Some(url) = discovery["revocation_endpoint"].as_str().map(str::to_owned) else {
                    return Err((self, code_failure("chatgpt_auth_unavailable")));
                };
                check!(part("endpoint", json!({"url":url})));
                let old = self.get("old").clone();
                let body = form(&[
                    ("token", old["refresh_token"].as_str().unwrap_or("")),
                    ("token_type_hint", "refresh_token"),
                    ("client_id", old["client_id"].as_str().unwrap_or("")),
                ]);
                self.http(
                    "so_revoked",
                    "revocation",
                    "POST",
                    &url,
                    Some(body),
                    flow_limit("revocation_answer_limit"),
                )
            }
            "so_revoked" => {
                if result["transport"].is_string() {
                    return Err((self, code_failure("chatgpt_auth_unavailable")));
                }
                let confirmed = check!(part(
                    "revocation",
                    json!({"profile":self.get("old"),"status":result["status"]})
                ))["confirmed"]
                    .clone();
                self.set("soft", Value::Null);
                self.set("revocation_confirmed", confirmed);
                return Ok(self.resume("so_done", &Value::Null));
            }
            "so_done" => {
                let confirmed = self.get("revocation_confirmed").clone();
                return Ok(
                    self.done(json!({"status":"signed_out","revocation_confirmed":confirmed}))
                );
            }

            // ---- tidying to one registration, pause and resume ----
            "edit_begin" => {
                let deadline = self
                    .input("deadline")
                    .as_f64()
                    .unwrap_or(self.now + flow_limit("edit_lock_seconds"));
                self.acquire("edit_got", "edit", deadline)
            }
            "edit_got" => self.todo("edit_read", json!({"todo":"read"})),
            "edit_read" => {
                let mut store = result["value"].clone();
                let id = self.input("profile_id").as_str().unwrap_or("").to_owned();
                let profile = self.profile_of(&store);
                let answer = match self.state["flow"].as_str().unwrap_or("") {
                    "tidy" => {
                        // The author's choice (11-14): keep the chosen
                        // registration, else the newest connected one.
                        let profiles: Vec<Value> = store["profiles"]
                            .as_object()
                            .map_or_else(Vec::new, |p| p.values().cloned().collect());
                        let kept =
                            super::sign_in_view::kept_registration(&profiles, &store["active"])
                                .and_then(|p| p["id"].as_str().map(str::to_owned));
                        let pending_kept = if kept.is_none() {
                            store["registrations_pending"]
                                .as_object()
                                .and_then(|pending| {
                                    store["active"]
                                        .as_str()
                                        .filter(|id| pending.contains_key(*id))
                                        .map(str::to_owned)
                                        .or_else(|| pending.keys().next().cloned())
                                })
                        } else {
                            None
                        };
                        let mut removed = Vec::new();
                        if let Some(rows) = store["profiles"].as_object_mut() {
                            rows.retain(|key, _| {
                                let keep = Some(key) == kept.as_ref();
                                if !keep {
                                    removed.push(json!(key));
                                }
                                keep
                            });
                        }
                        if let Some(rows) = store["registrations_pending"].as_object_mut() {
                            rows.retain(|key, _| {
                                let keep = Some(key) == pending_kept.as_ref();
                                if !keep {
                                    removed.push(json!(key));
                                }
                                keep
                            });
                        }
                        let kept = kept.or(pending_kept);
                        store["active"] = kept.clone().map_or(Value::Null, Value::String);
                        let answer = json!({"kept":kept,"removed":removed});
                        if removed.is_empty() {
                            self.set("answer", answer);
                            return Ok(self.release("edit_done", "edit"));
                        }
                        answer
                    }
                    "resume" => {
                        let next =
                            check!(part("resume_quota", json!({"profile":profile})))["profile"]
                                .clone();
                        store["profiles"][&id] = next;
                        json!({"state":"connected"})
                    }
                    _ => {
                        let paused = check!(part(
                            "pause_quota",
                            json!({"profile":profile,"generation":self.input("generation")})
                        ));
                        if paused["changed"] != true {
                            self.set("answer", json!({"paused":false}));
                            return Ok(self.release("edit_done", "edit"));
                        }
                        store["profiles"][&id] = paused["profile"].clone();
                        json!({"paused":true})
                    }
                };
                self.set("answer", answer);
                self.todo("edit_saved", json!({"todo":"write","value":store}))
            }
            "edit_saved" => self.release("edit_done", "edit"),
            "edit_done" => {
                let answer = self.get("answer").clone();
                return Ok(self.done(answer));
            }

            // ---- sign-in ----
            "li_begin" => self.todo("li_read", json!({"todo":"read"})),
            "li_read" => {
                let store = &result["value"];
                // The host's one registration, signed in again with its own
                // client id; a new one only when there is none, or when the
                // author asks for a new registration after an account change.
                let chosen = if self.input("new_registration") == true {
                    None
                } else {
                    let profiles: Vec<Value> = store["profiles"]
                        .as_object()
                        .map_or_else(Vec::new, |p| p.values().cloned().collect());
                    super::sign_in_view::kept_registration(&profiles, &store["active"])
                        .and_then(|p| p["id"].as_str().map(str::to_owned))
                        .or_else(|| {
                            let pending = store["registrations_pending"].as_object()?;
                            store["active"]
                                .as_str()
                                .filter(|id| pending.contains_key(*id))
                                .map(str::to_owned)
                                .or_else(|| pending.keys().next().cloned())
                        })
                };
                self.state["input"]["profile_id"] = chosen.map_or(Value::Null, Value::String);
                let id = self.input("profile_id").clone();
                let key = id.as_str().unwrap_or("");
                let previous = check!(part(
                    "previous",
                    json!({"profile_id":id,"profile":store["profiles"][key],
                        "pending":store["registrations_pending"][key]})
                ))["previous"]
                    .clone();
                self.set("previous", previous);
                let mut sizes = login()["random_bytes"].clone();
                if self.input("profile_id").as_str().is_none_or(str::is_empty) {
                    sizes["profile_id"] = json!(16);
                }
                self.todo("li_random", json!({"todo":"random","bytes":sizes}))
            }
            "li_random" => {
                let values = &result["values"];
                for name in ["state", "nonce", "verifier"] {
                    let Some(value) = values[name].as_str() else {
                        return Err((self, code_failure("chatgpt_auth_unavailable")));
                    };
                    let value = value.to_owned();
                    self.set(name, json!(value));
                }
                let id = match self.input("profile_id").as_str().filter(|s| !s.is_empty()) {
                    Some(id) => id.to_owned(),
                    None => {
                        let bytes = values["profile_id"]
                            .as_str()
                            .and_then(|v| URL_SAFE_NO_PAD.decode(v).ok());
                        let Some(id) = bytes.as_deref().and_then(uuid4) else {
                            return Err((self, code_failure("chatgpt_auth_unavailable")));
                        };
                        id
                    }
                };
                self.state["input"]["profile_id"] = json!(id);
                self.todo("li_host", json!({"todo":"host_id"}))
            }
            "li_host" => {
                self.set("host_id", result["host_id"].clone());
                let path = text(&login()["callback_path"]);
                let deadline = self.deadline();
                self.todo(
                    "li_listen",
                    json!({"todo":"listen","path":path,"deadline":deadline}),
                )
            }
            "li_listen" => {
                let Some(port) = result["port"].as_u64().filter(|p| (1..=65535).contains(p)) else {
                    return Err((self, code_failure("chatgpt_auth_unavailable")));
                };
                let redirect =
                    format!("http://127.0.0.1:{port}{}", text(&login()["callback_path"]));
                self.set("port", json!(port));
                self.set("redirect_uri", json!(redirect));
                let url = check!(part(
                    "url",
                    json!({"previous":self.get("previous"),"consent":self.input("consent") == true,
                        "host_id":self.get("host_id"),"redirect_uri":redirect,"state":self.get("state"),
                        "nonce":self.get("nonce"),"verifier":self.get("verifier")})
                ))["url"]
                    .clone();
                let profile_id = self.input("profile_id").clone();
                self.todo(
                    "li_opened",
                    json!({"todo":"open","url":url,"profile_id":profile_id}),
                )
            }
            "li_opened" | "li_wait" => {
                let deadline = self.deadline();
                self.todo(
                    "li_callback",
                    json!({"todo":"await_callback","deadline":deadline}),
                )
            }
            "li_callback" => {
                let head = result["head_base64"]
                    .as_str()
                    .and_then(|h| base64::engine::general_purpose::STANDARD.decode(h).ok());
                let port = self.get("port").as_u64().unwrap_or(0);
                let target = head.as_deref().and_then(|h| callback_target(h, port));
                let refused = |flow: Flow| {
                    let (status, headers, body) =
                        callback_page(flow.input("language").as_str().unwrap_or("en"), false);
                    flow.todo(
                        "li_wait",
                        json!({"todo":"respond","status":status,"headers":headers,"body":body}),
                    )
                };
                let Some(target) = target else {
                    return Ok(refused(self));
                };
                let Ok(query) = part("callback_query", json!({"target":target})) else {
                    return Ok(refused(self));
                };
                let query = query["query"].clone();
                let first = |name: &str| query[name][0].clone();
                if part(
                    "callback",
                    json!({"state":first("state"),"expected_state":self.get("state"),"code":"state-check","error":null}),
                )
                .is_err()
                {
                    return Ok(refused(self));
                }
                let used = self.get("used") == true;
                let decision =
                    chatgpt_auth_policy::run(&json!({"action":"chatgpt_auth_callback_use",
                    "used":used,"cancelled":false,"expired":self.now >= self.deadline()}));
                self.set("used", decision["used"].clone());
                if let Some(code) = decision["error"].as_str() {
                    if decision["fail_attempt"] == true {
                        self.set("respond_failed", json!(true));
                        return Err((self, code_failure(code)));
                    }
                    return Ok(refused(self));
                }
                self.set("respond_failed", json!(true));
                let expected = self.get("state").clone();
                if matches!(
                    first("error").as_str(),
                    Some("invalid_client" | "unauthorized_client")
                ) && self.get("previous").is_object()
                {
                    return Err((self, code_failure("chatgpt_account_changed")));
                }
                if query.get("error").is_some() {
                    check!(part(
                        "callback",
                        json!({"state":expected,"expected_state":expected,"code":"error-check","error":first("error")})
                    ));
                }
                let previous = self.get("previous").clone();
                let issued = query["client_id"][0]
                    .as_str()
                    .map(str::to_owned)
                    .or_else(|| previous["client_id"].as_str().map(str::to_owned))
                    .unwrap_or_default();
                check!(part(
                    "callback_client",
                    json!({"issued":issued,"previous":previous})
                ));
                let code = check!(part(
                    "callback",
                    json!({"state":expected,"expected_state":expected,"code":first("code"),"error":null})
                ))["code"]
                    .clone();
                self.set("client_id", json!(issued));
                self.set("code", code);
                if self.input("respond_before_exchange") == true {
                    // Android sends the exchange only once inku is in front:
                    // the browser is told now, and a later failure is only named.
                    self.set("respond_failed", json!(false));
                    self.set("responded", json!(true));
                    let (status, headers, body) =
                        page(self.input("language").as_str().unwrap_or("en"), "received");
                    return Ok(self.todo(
                        "li_pending_begin",
                        json!({"todo":"respond","status":status,"headers":headers,"body":body}),
                    ));
                }
                return Ok(self.resume("li_pending_begin", &Value::Null));
            }
            "li_pending_begin" => {
                let deadline = self.deadline();
                self.acquire("li_pending_own", "refresh", deadline)
            }
            "li_pending_own" => {
                let deadline = self.deadline();
                self.acquire("li_pending_got", "edit", deadline)
            }
            "li_pending_got" => self.todo("li_pending_read", json!({"todo":"read"})),
            "li_pending_read" => {
                let mut store = result["value"].clone();
                let id = self.input("profile_id").as_str().unwrap_or("").to_owned();
                if !store["registrations_pending"].is_object() {
                    store["registrations_pending"] = json!({});
                }
                let pending = &store["registrations_pending"];
                check!(part(
                    "pending_check",
                    json!({"exists":pending.get(&id).is_some(),"count":pending.as_object().map_or(0, Map::len)})
                ));
                store["registrations_pending"][&id] = json!({"client_id":self.get("client_id")});
                self.todo("li_pending_saved", json!({"todo":"write","value":store}))
            }
            "li_pending_saved" => self.release("li_pending_released", "edit"),
            "li_pending_released" => self.release("li_exchange", "refresh"),
            "li_exchange" => {
                let body = form(&[
                    ("grant_type", "authorization_code"),
                    ("client_id", self.get("client_id").as_str().unwrap_or("")),
                    ("code", self.get("code").as_str().unwrap_or("")),
                    ("code_verifier", self.get("verifier").as_str().unwrap_or("")),
                    (
                        "redirect_uri",
                        self.get("redirect_uri").as_str().unwrap_or(""),
                    ),
                    ("resource", resource),
                ]);
                self.http(
                    "li_exchanged",
                    "token_exchange",
                    "POST",
                    &token_url,
                    Some(body),
                    limit,
                )
            }
            "li_exchanged" => {
                // A client id ChatGPT's settings removed is refused: the
                // registration has to be made again.
                let refused_client = result["body"]
                    .as_str()
                    .and_then(|b| serde_json::from_str::<Value>(b).ok())
                    .is_some_and(|v| {
                        v["error"] == "invalid_client" || v["error"]["code"] == "invalid_client"
                    });
                if refused_client && self.get("previous").is_object() {
                    return Err((self, code_failure("chatgpt_account_changed")));
                }
                let value = check!(Self::auth_json(result));
                let Some(token) = value["id_token"].as_str().map(str::to_owned) else {
                    return Err((self, code_failure("chatgpt_auth_unavailable")));
                };
                self.set("token_value", value);
                self.set("token_previous", Value::Null);
                self.set("id_token", json!(token));
                self.set("id_after", json!("li_identity"));
                return Ok(self.resume("id_begin", &Value::Null));
            }
            "li_identity" => {
                let sub = self.get("claims")["sub"].clone();
                if part(
                    "identity",
                    json!({"previous":self.get("previous"),"sub":sub}),
                )
                .is_err()
                {
                    return Err((self, code_failure("chatgpt_account_changed")));
                }
                self.set("tokens_after", json!("li_tokens"));
                return Ok(self.resume("tokens_begin", &Value::Null));
            }
            "li_tokens" => {
                let claims = self.get("claims").clone();
                let client = self.get("client_id").clone();
                let display = check!(part(
                    "display",
                    json!({"claims":claims,"client_id":client,"email_json":self.get("email_json")})
                ));
                let generation = check!(part(
                    "generation",
                    json!({"previous":self.get("previous")})
                ))["generation"]
                    .clone();
                let mut profile = json!({"id":self.input("profile_id"),"issuer":text(&login()["issuer"]),
                    "sub":claims["sub"],"client_id":client,"email":display["email"],"label":display["label"],
                    "generation":generation,"state":"connected","refresh_owner":"runtime","oidc_nonce":self.get("nonce")});
                if let (Some(fields), Some(tokens)) =
                    (profile.as_object_mut(), self.get("tokens").as_object())
                {
                    fields.extend(tokens.clone());
                }
                self.set("profile", profile);
                let deadline = self.deadline();
                self.acquire("li_save_own", "refresh", deadline)
            }
            "li_save_own" => {
                let deadline = self.deadline();
                self.acquire("li_save_got", "edit", deadline)
            }
            "li_save_got" => self.todo("li_save_read", json!({"todo":"read"})),
            "li_save_read" => {
                let mut store = result["value"].clone();
                let previous = self.get("previous");
                let expected = if previous.is_object() && !truthy(&previous["pending"]) {
                    previous["generation"].clone()
                } else {
                    Value::Null
                };
                check!(Self::save(
                    &mut store,
                    self.get("profile").clone(),
                    expected,
                    true
                ));
                // One registration for the host: the one just signed in.
                let id = self.input("profile_id").as_str().unwrap_or("").to_owned();
                if let Some(profiles) = store["profiles"].as_object_mut() {
                    profiles.retain(|key, _| *key == id);
                }
                store["registrations_pending"] = json!({});
                self.todo("li_saved", json!({"todo":"write","value":store}))
            }
            "li_saved" => self.release("li_save_released", "edit"),
            "li_save_released" => self.release("li_respond", "refresh"),
            "li_respond" => {
                self.set("respond_failed", json!(false));
                if self.get("responded") == true {
                    return Ok(self.resume("li_done", &Value::Null));
                }
                let (status, headers, body) =
                    callback_page(self.input("language").as_str().unwrap_or("en"), true);
                self.todo(
                    "li_done",
                    json!({"todo":"respond","status":status,"headers":headers,"body":body}),
                )
            }
            "li_done" => {
                let id = self.input("profile_id").clone();
                return Ok(self.done(json!({"status":"completed","profile_id":id})));
            }

            "tokens_answer" => {
                let tokens = self.get("tokens").clone();
                return Ok(self.done(json!({"tokens":tokens})));
            }

            // ---- the identity alone (Server's import of a registration) ----
            "identity_done" => {
                let claims = self.get("claims").clone();
                return Ok(self.done(json!({"claims":claims})));
            }

            _ => return Err((self, code_failure("chatgpt_auth_unavailable"))),
        })
    }
}

fn part_policy(action: &str, mut fields: Value) -> Step {
    fields["action"] = json!(action);
    let answer = super::chatgpt_policy::run(&fields);
    match answer.get("error").and_then(Value::as_str) {
        Some(code) => Err(code_failure(code)),
        None => Ok(answer),
    }
}

const FLOWS: [(&str, &str); 9] = [
    ("login", "li_begin"),
    ("access", "ac_begin"),
    ("catalog", "ca_begin"),
    ("sign_out", "so_begin"),
    ("tidy", "edit_begin"),
    ("pause", "edit_begin"),
    ("resume", "edit_begin"),
    ("identity", "id_begin"),
    ("tokens", "tokens_begin"),
];

/// `chatgpt_flow_start` and `chatgpt_flow_next`.
pub(super) fn run(r: &Value) -> Value {
    let Some(now) = r["now"].as_f64().filter(|n| n.is_finite()) else {
        return json!({"error":"chatgpt_flow_invalid"});
    };
    match r["action"].as_str().unwrap_or("") {
        "chatgpt_flow_start" => {
            let name = r["flow"].as_str().unwrap_or("");
            let Some((_, first)) = FLOWS.iter().find(|(flow, _)| *flow == name) else {
                return json!({"error":"chatgpt_flow_invalid"});
            };
            let input = if r["input"].is_object() {
                r["input"].clone()
            } else {
                json!({})
            };
            let deadline = match name {
                "login" => {
                    let limits = match part(
                        "attempt",
                        json!({"pending_count":input["pending_count"],"owner_count":input["owner_count"]}),
                    ) {
                        Ok(limits) => limits,
                        Err(failure) => {
                            let mut todo = failure;
                            todo["todo"] = json!("failed");
                            return json!({"state":null,"todo":todo,"held":[],"deadline":null});
                        }
                    };
                    json!(now + limits["deadline_seconds"].as_f64().unwrap_or(0.0))
                }
                "catalog" => json!(
                    input["deadline"]
                        .as_f64()
                        .unwrap_or(now + flow_limit("catalog_seconds"))
                ),
                _ => input
                    .get("deadline")
                    .cloned()
                    .unwrap_or(json!(now + flow_limit("edit_lock_seconds"))),
            };
            let mut data = json!({});
            if name == "identity" {
                data = json!({"id_token":input["id_token"],"client_id":input["client_id"],
                    "nonce":input["nonce"],"id_after":"identity_done"});
            }
            if name == "tokens" {
                data = json!({"token_value":input["value"],"token_previous":input["previous"],"tokens_after":"tokens_answer"});
            }
            let flow = Flow {
                state: json!({"flow":name,"step":first,"input":input,"data":data,"held":[],"deadline":deadline}),
                now,
            };
            flow.resume(first, &Value::Null)
        }
        "chatgpt_flow_next" => {
            let state = r["state"].clone();
            let Some(step) = state["step"].as_str().map(str::to_owned) else {
                return json!({"error":"chatgpt_flow_invalid"});
            };
            let flow = Flow { state, now };
            // A sign-in past its deadline is over, wherever it was.
            if step != "unwind" && flow.state["flow"] == "login" && now >= flow.deadline() {
                return flow.failed(code_failure("chatgpt_cancelled"));
            }
            flow.resume(&step, &r["result"])
        }
        _ => json!({"error":"unknown_action"}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::engine::general_purpose::STANDARD;

    const NOW: f64 = 1_800_000_000.0;
    const ISSUER: &str = "https://auth.openai.com";

    fn b64(value: &Value) -> String {
        URL_SAFE_NO_PAD.encode(value.to_string())
    }

    /// An id token whose signature the test host accepts.
    fn id_token(nonce: Option<&str>, client: &str) -> String {
        let mut claims = json!({"iss":ISSUER,"aud":client,"sub":"user-1","exp":NOW + 3600.0,
            "iat":NOW - 1.0,"email":"author@example.com"});
        if let Some(nonce) = nonce {
            claims["nonce"] = json!(nonce);
        }
        format!(
            "{}.{}.c2ln",
            b64(&json!({"alg":"RS256","kid":"k1"})),
            b64(&claims)
        )
    }

    /// A host that does what each answer names, from a script of HTTP answers.
    struct Host {
        store: Value,
        held: Vec<String>,
        http: Vec<Value>,
        sent: Vec<Value>,
        responses: Vec<Value>,
        callbacks: Vec<String>,
        writes: usize,
        steps: usize,
        now: f64,
        log: Vec<Value>,
    }

    impl Host {
        fn new(store: Value) -> Self {
            Self {
                store,
                held: vec![],
                http: vec![],
                sent: vec![],
                responses: vec![],
                callbacks: vec![],
                writes: 0,
                steps: 0,
                now: NOW,
                log: vec![],
            }
        }

        fn ask(&mut self, request: Value) -> Value {
            let mut request = request;
            request["schema"] = json!("inku.model-catalog-request.v1");
            let bytes = crate::model_catalog::model_catalog_json(request.to_string().as_bytes());
            let answer: Value = serde_json::from_slice(&bytes).unwrap();
            self.log.push(json!({"request":request,"expect":answer}));
            answer
        }

        fn run(&mut self, flow: &str, input: Value) -> Value {
            let mut answer = self.ask(
                json!({"action":"chatgpt_flow_start","flow":flow,"input":input,"now":self.now}),
            );
            loop {
                self.steps += 1;
                assert!(self.steps < 200, "the flow does not end: {answer}");
                let todo = answer["todo"].clone();
                let result = match todo["todo"].as_str().unwrap() {
                    "done" | "failed" => {
                        assert!(self.held.is_empty(), "{flow} ended holding {:?}", self.held);
                        return todo;
                    }
                    "acquire" => {
                        let lock = todo["lock"].as_str().unwrap().to_owned();
                        assert!(!self.held.contains(&lock), "{lock} taken twice");
                        self.held.push(lock);
                        json!({"acquired":true})
                    }
                    "release" => {
                        let lock = todo["lock"].as_str().unwrap();
                        assert_eq!(
                            self.held.pop().as_deref(),
                            Some(lock),
                            "locks released out of order"
                        );
                        json!({})
                    }
                    "read" => json!({"value":self.store}),
                    "write" => {
                        assert!(
                            self.held.iter().any(|l| l == "edit"),
                            "a write outside the edit lock"
                        );
                        self.store = todo["value"].clone();
                        self.writes += 1;
                        json!({})
                    }
                    "random" => {
                        let mut values = json!({});
                        for (name, size) in todo["bytes"].as_object().unwrap() {
                            let bytes = vec![7u8; size.as_u64().unwrap() as usize];
                            values[name] = json!(URL_SAFE_NO_PAD.encode(bytes));
                        }
                        json!({"values":values})
                    }
                    "host_id" => json!({"host_id":"urn:uuid:00000000-0000-4000-8000-000000000001"}),
                    "listen" => json!({"port":4321}),
                    "open" => json!({}),
                    "await_callback" => {
                        let head = self.callbacks.remove(0);
                        json!({"head_base64":STANDARD.encode(head)})
                    }
                    "respond" => {
                        self.responses.push(todo.clone());
                        json!({})
                    }
                    "verify" => json!({"valid":todo["signature"] == "c2ln"}),
                    "offset" => json!({"seconds":32400}),
                    "http" => {
                        self.sent.push(todo.clone());
                        self.http.remove(0)
                    }
                    other => panic!("unknown todo {other}"),
                };
                answer = self.ask(json!({"action":"chatgpt_flow_next","state":answer["state"],"result":result,"now":self.now}));
            }
        }
    }

    fn ok(value: Value) -> Value {
        json!({"status":200,"body":value.to_string()})
    }
    fn discovery() -> Value {
        ok(
            json!({"issuer":ISSUER,"jwks_uri":"https://auth.openai.com/jwks",
            "revocation_endpoint":"https://auth.openai.com/oauth/revoke"}),
        )
    }
    fn keys() -> Value {
        ok(json!({"keys":[{"kid":"k1","kty":"RSA","use":"sig","n":"AQAB","e":"AQAB"}]}))
    }
    fn tokens(id_token: &str) -> Value {
        ok(
            json!({"access_token":"access-2","refresh_token":"refresh-2","id_token":id_token,
            "token_type":"Bearer","expires_in":3600,"scope":"openid email chatgpt.tokens.use.direct"}),
        )
    }
    fn connected() -> Value {
        json!({"id":"p1","issuer":ISSUER,"sub":"user-1","client_id":"client-1","email":"author@example.com",
            "label":"author@example.com / client-1","generation":3,"state":"connected","refresh_owner":"runtime",
            "access_token":"access-1","refresh_token":"refresh-1","id_token":"old","oidc_nonce":"n",
            "scopes":["chatgpt.tokens.use.direct"],"expires_at":NOW + 3600.0,"earliest_refresh_at":0.0,
            "published_models":["gpt-6.1-sol"],"model_purposes":{"gpt-6.1-sol":["llm"]}})
    }
    fn store(profile: Value) -> Value {
        json!({"profiles":{"p1":profile},"registrations_pending":{},"active":"p1"})
    }
    fn callback(state: &str, extra: &str) -> String {
        format!(
            "GET /auth/callback?code=the-code&state={state}{extra} HTTP/1.1\r\nHost: 127.0.0.1:4321\r\nUser-Agent: test"
        )
    }
    fn state_value() -> String {
        URL_SAFE_NO_PAD.encode([7u8; 32])
    }

    #[test]
    fn a_new_sign_in_keeps_the_registration_as_server_did() {
        let mut host = Host::new(json!({"profiles":{},"registrations_pending":{}}));
        host.callbacks
            .push(callback("wrong", "&client_id=client-9"));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-9"));
        let nonce = state_value();
        host.http = vec![
            tokens(&id_token(Some(&nonce), "client-9")),
            discovery(),
            keys(),
        ];
        let done = host.run(
            "login",
            json!({"consent":false,"language":"ja","pending_count":0,"owner_count":0}),
        );
        assert_eq!(done["todo"], "done", "{done}");
        let id = done["profile_id"].as_str().unwrap();
        assert_eq!(id.len(), 36);
        // The wrong state is refused and the sign-in keeps waiting.
        assert_eq!(host.responses[0]["status"], 400);
        assert_eq!(host.responses[1]["status"], 200);
        assert!(
            host.responses[1]["body"]
                .as_str()
                .unwrap()
                .contains("ChatGPTの認証が完了しました")
        );
        // The exchange is the form Server sent, in its order.
        let verifier = URL_SAFE_NO_PAD.encode([7u8; 64]);
        assert_eq!(
            host.sent[0]["url"],
            "https://auth.openai.com/api/accounts/oauth/token"
        );
        assert_eq!(
            host.sent[0]["body"],
            format!(
                "grant_type=authorization_code&client_id=client-9&code=the-code&code_verifier={verifier}&redirect_uri=http%3A%2F%2F127.0.0.1%3A4321%2Fauth%2Fcallback&resource=https%3A%2F%2Fapi.openai.com%2Fv1"
            )
        );
        assert_eq!(
            host.sent[1]["url"],
            "https://auth.openai.com/.well-known/openid-configuration"
        );
        let profile = &host.store["profiles"][id];
        assert_eq!(profile["state"], "connected");
        assert_eq!(profile["generation"], 1);
        assert_eq!(profile["client_id"], "client-9");
        assert_eq!(profile["label"], "author@example.com / client-9");
        assert_eq!(profile["access_token"], "access-2");
        assert_eq!(profile["expires_at"], NOW + 3600.0);
        assert_eq!(host.store["active"], id);
        assert_eq!(host.store["registrations_pending"], json!({}));
    }

    #[test]
    fn a_sign_in_that_fails_after_its_callback_answers_the_failed_page() {
        let mut host = Host::new(json!({"profiles":{},"registrations_pending":{}}));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-9"));
        host.http = vec![json!({"status":400,"body":"{\"error\":\"invalid_grant\"}"})];
        let failed = host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0}),
        );
        assert_eq!(failed["todo"], "failed");
        assert_eq!(failed["code"], "chatgpt_reauthentication_required");
        assert_eq!(host.responses.last().unwrap()["status"], 400);
        // The issued client id stays for a retry with the same profile id.
        let pending = host.store["registrations_pending"].as_object().unwrap();
        assert_eq!(pending.len(), 1);
    }

    #[test]
    fn a_host_that_exchanges_later_answers_the_browser_first() {
        let mut host = Host::new(json!({"profiles":{},"registrations_pending":{}}));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-9"));
        host.http = vec![
            tokens(&id_token(Some(&state_value()), "client-9")),
            discovery(),
            keys(),
        ];
        let done = host.run(
            "login",
            json!({"language":"ja","pending_count":0,"owner_count":0,"respond_before_exchange":true}),
        );
        assert_eq!(done["todo"], "done", "{done}");
        assert_eq!(host.responses.len(), 1);
        assert_eq!(host.responses[0]["status"], 200);
        assert!(
            host.responses[0]["body"]
                .as_str()
                .unwrap()
                .contains("ChatGPTでの許可を受け取りました")
        );
        // A phone lays the page out at its own width (the author, 11-14: the
        // text was small in Chrome on Pixel 9).
        assert!(
            host.responses[0]["body"].as_str().unwrap().contains(
                r#"<meta name="viewport" content="width=device-width, initial-scale=1">"#
            )
        );

        let mut host = Host::new(json!({"profiles":{},"registrations_pending":{}}));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-9"));
        host.http = vec![json!({"transport":"unavailable"})];
        let failed = host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0,"respond_before_exchange":true}),
        );
        assert_eq!(failed["code"], "chatgpt_transport_unavailable");
        assert_eq!(
            host.responses.len(),
            1,
            "a failure after the answer is only named"
        );
    }

    #[test]
    fn the_callback_head_is_read_strictly() {
        let target = |head: &str| callback_target(head.as_bytes(), 4321);
        assert!(target("GET /auth/callback?a=1 HTTP/1.1\r\nHost: 127.0.0.1:4321").is_some());
        assert!(target("POST /auth/callback HTTP/1.1\r\nHost: 127.0.0.1:4321").is_none());
        assert!(target("GET /auth/callback HTTP/1.1\r\nHost: localhost:4321").is_none());
        assert!(
            target("GET /auth/callback HTTP/1.1\r\nHost: 127.0.0.1:4321\r\nhost: 127.0.0.1:4321")
                .is_none()
        );
        assert!(
            target("GET /auth/callback HTTP/1.1\r\nHost: 127.0.0.1:4321\r\nContent-Length: 3")
                .is_none()
        );
        assert!(
            target(
                "GET /auth/callback HTTP/1.1\r\nHost: 127.0.0.1:4321\r\nTransfer-Encoding: chunked"
            )
            .is_none()
        );
        assert!(
            target(&format!(
                "GET /{} HTTP/1.1\r\nHost: 127.0.0.1:4321",
                "a".repeat(8192)
            ))
            .is_none()
        );
        assert!(target("GET /auth/callback HTTP/2\r\nHost: 127.0.0.1:4321").is_none());
    }

    #[test]
    fn a_token_still_good_is_used_and_an_old_one_refreshed() {
        let mut host = Host::new(store(connected()));
        let done = host.run(
            "access",
            json!({"profile_id":"p1","generation":3,"deadline":NOW + 15.0}),
        );
        assert_eq!(done["access_token"], "access-1");
        assert_eq!(host.writes, 0);

        let mut old = connected();
        old["expires_at"] = json!(NOW + 10.0);
        let mut host = Host::new(store(old));
        host.http = vec![tokens(&id_token(None, "client-1")), discovery(), keys()];
        let done = host.run(
            "access",
            json!({"profile_id":"p1","generation":3,"deadline":NOW + 15.0}),
        );
        assert_eq!(done["access_token"], "access-2", "{done}");
        assert_eq!(
            host.sent[0]["body"],
            "grant_type=refresh_token&client_id=client-1&refresh_token=refresh-1&resource=https%3A%2F%2Fapi.openai.com%2Fv1"
        );
        let profile = &host.store["profiles"]["p1"];
        assert_eq!(profile["refresh_token"], "refresh-2");
        assert_eq!(profile["generation"], 3);
        assert_eq!(profile["model_purposes"], json!({"gpt-6.1-sol":["llm"]}));
    }

    #[test]
    fn a_refresh_that_drops_the_plan_scope_sends_no_model_list() {
        let mut old = connected();
        old["expires_at"] = json!(NOW + 10.0);
        let mut host = Host::new(store(old));
        let mut refreshed = tokens(&id_token(None, "client-1"));
        refreshed["body"] = json!(
            refreshed["body"]
                .as_str()
                .unwrap()
                .replace(" chatgpt.tokens.use.direct", "")
        );
        host.http = vec![refreshed, discovery(), keys()];
        let failed = host.run(
            "catalog",
            json!({"profile_id":"p1","generation":3,"force":true}),
        );
        assert_eq!(failed["code"], "chatgpt_scope_required", "{failed}");
        assert_eq!(
            host.sent.len(),
            3,
            "the refresh and its identity, no model list"
        );
        assert_eq!(host.store["profiles"]["p1"]["refresh_token"], "refresh-2");
    }

    #[test]
    fn a_refresh_the_server_refuses_asks_for_reauthentication() {
        let mut old = connected();
        old["expires_at"] = json!(NOW + 10.0);
        let mut host = Host::new(store(old));
        host.http = vec![json!({"status":400,"body":"{\"error\":\"invalid_grant\"}"})];
        let failed = host.run("access", json!({"profile_id":"p1","generation":3}));
        assert_eq!(failed["code"], "chatgpt_reauthentication_required");
        let profile = &host.store["profiles"]["p1"];
        assert_eq!(profile["state"], "reauthentication_required");
        assert_eq!(profile["generation"], 4);
        assert!(profile.get("refresh_token").is_none());
    }

    #[test]
    fn a_model_list_is_fetched_and_kept_under_the_edit_lock() {
        let mut host = Host::new(store(connected()));
        host.http = vec![ok(
            json!({"models":[{"slug":"gpt-6.1-sol","display_name":"GPT-6.1 Sol","visibility":"list"}]}),
        )];
        let done = host.run(
            "catalog",
            json!({"profile_id":"p1","generation":3,"force":true}),
        );
        assert_eq!(done["cached"], false, "{done}");
        assert_eq!(done["models"][0]["id"], "gpt-6.1-sol");
        assert_eq!(host.sent[0]["url"], "https://api.openai.com/v1/models");
        assert_eq!(host.sent[0]["headers"]["Authorization"], "Bearer access-1");
        assert_eq!(host.sent[0]["deadline"], NOW + 15.0);
        assert_eq!(
            host.store["profiles"]["p1"]["catalog"]["expires_at"],
            NOW + 300.0
        );

        let mut cached = Host::new(host.store.clone());
        let done = cached.run("catalog", json!({"profile_id":"p1","generation":3}));
        assert_eq!(done["cached"], true);
        assert!(cached.sent.is_empty());
    }

    #[test]
    fn a_usage_limit_pauses_the_registration() {
        let mut host = Host::new(store(connected()));
        host.http = vec![
            json!({"status":429,"body":"{\"error\":{\"code\":\"subscription_sharing_usage_limit_exceeded\"}}","request_id":"req_1"}),
        ];
        let failed = host.run(
            "catalog",
            json!({"profile_id":"p1","generation":3,"force":true}),
        );
        assert_eq!(failed["code"], "subscription_sharing_usage_limit_exceeded");
        assert_eq!(failed["action"], "usage");
        assert_eq!(failed["request_id"], "req_1");
        assert_eq!(host.store["profiles"]["p1"]["state"], "quota");

        let done = host.run("resume", json!({"profile_id":"p1"}));
        assert_eq!(done["state"], "connected");
        assert_eq!(host.store["profiles"]["p1"]["state"], "connected");
    }

    #[test]
    fn a_sign_out_revokes_and_a_second_keeps_the_generation() {
        let mut host = Host::new(store(connected()));
        host.http = vec![discovery(), json!({"status":200,"body":""})];
        let done = host.run("sign_out", json!({"profile_id":"p1"}));
        assert_eq!(done["revocation_confirmed"], true, "{done}");
        assert_eq!(host.sent[1]["url"], "https://auth.openai.com/oauth/revoke");
        assert_eq!(
            host.sent[1]["body"],
            "token=refresh-1&token_type_hint=refresh_token&client_id=client-1"
        );
        assert_eq!(host.sent[1]["deadline"], NOW + 10.0);
        assert_eq!(host.store["profiles"]["p1"]["generation"], 4);

        let done = host.run("sign_out", json!({"profile_id":"p1"}));
        assert_eq!(done["revocation_confirmed"], false);
        assert_eq!(host.store["profiles"]["p1"]["generation"], 4);

        assert_eq!(host.store["profiles"]["p1"]["client_id"], "client-1");
        assert_eq!(host.store["profiles"]["p1"]["retained_id_token"], "old");
    }

    #[test]
    fn a_revocation_that_fails_still_signs_out() {
        let mut host = Host::new(store(connected()));
        host.http = vec![json!({"transport":"timeout"})];
        let done = host.run("sign_out", json!({"profile_id":"p1"}));
        assert_eq!(done["todo"], "done", "{done}");
        assert_eq!(done["revocation_confirmed"], false);
        assert_eq!(host.store["profiles"]["p1"]["state"], "signed_out");
    }

    fn opened_url(host: &Host) -> String {
        host.log
            .iter()
            .find_map(|row| {
                (row["expect"]["todo"]["todo"] == "open")
                    .then(|| row["expect"]["todo"]["url"].as_str().unwrap().to_owned())
            })
            .unwrap()
    }

    #[test]
    fn a_sign_in_after_signing_out_keeps_the_registration() {
        let mut host = Host::new(store(connected()));
        host.http = vec![discovery(), json!({"status":200,"body":""})];
        host.run("sign_out", json!({"profile_id":"p1"}));
        host.log.clear();
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-1"));
        host.http = vec![
            tokens(&id_token(Some(&state_value()), "client-1")),
            discovery(),
            keys(),
        ];
        let done = host.run(
            "login",
            json!({"language":"ja","pending_count":0,"owner_count":0}),
        );
        assert_eq!(done["profile_id"], "p1", "{done}");
        let url = opened_url(&host);
        assert!(url.contains("client_id=client-1&"), "{url}");
        assert!(url.contains("&id_token_hint=old&"), "{url}");
        assert!(!url.contains("agent_name_hint"), "{url}");
        let profile = &host.store["profiles"]["p1"];
        assert_eq!(profile["state"], "connected");
        assert_eq!(profile["generation"], 5);
        assert_eq!(profile["published_models"], json!(["gpt-6.1-sol"]));
        assert_eq!(host.store["profiles"].as_object().unwrap().len(), 1);
    }

    #[test]
    fn tidying_keeps_the_chosen_registration_only() {
        let mut other = connected();
        other["id"] = json!("p2");
        other["generation"] = json!(9);
        let mut host = Host::new(json!({"profiles":{"p1":connected(),"p2":other},
            "registrations_pending":{"p3":{"client_id":"client-3"}},"active":"p1"}));
        let done = host.run("tidy", json!({}));
        assert_eq!(done["kept"], "p1", "{done}");
        assert_eq!(done["removed"], json!(["p2", "p3"]));
        assert_eq!(host.store["profiles"].as_object().unwrap().len(), 1);
        assert_eq!(host.store["registrations_pending"], json!({}));
        let again = host.run("tidy", json!({}));
        assert_eq!(again["removed"], json!([]));
        assert_eq!(host.writes, 1);
    }

    #[test]
    fn another_account_asks_for_a_new_registration() {
        let mut signed_out = connected();
        signed_out["state"] = json!("signed_out");
        let mut host = Host::new(store(signed_out));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-1"));
        let mut token = id_token(Some(&state_value()), "client-1");
        let claims = token.split('.').nth(1).unwrap().to_owned();
        let mut other: Value =
            serde_json::from_slice(&URL_SAFE_NO_PAD.decode(&claims).unwrap()).unwrap();
        other["sub"] = json!("user-2");
        token = token.replace(&claims, &b64(&other));
        host.http = vec![tokens(&token), discovery(), keys()];
        let failed = host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0}),
        );
        assert_eq!(failed["code"], "chatgpt_account_changed", "{failed}");

        host.log.clear();
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-7"));
        host.http = vec![
            tokens(&id_token(Some(&state_value()), "client-7")),
            discovery(),
            keys(),
        ];
        let done = host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0,"new_registration":true}),
        );
        assert_eq!(done["todo"], "done", "{done}");
        assert!(opened_url(&host).contains("client_id=dynamic_agent_client&"));
        let id = done["profile_id"].as_str().unwrap();
        assert_ne!(id, "p1");
        assert_eq!(host.store["profiles"].as_object().unwrap().len(), 1);
        assert_eq!(host.store["profiles"][id]["client_id"], "client-7");
        assert_eq!(host.store["active"], id);
    }

    #[test]
    fn a_client_removed_in_chatgpt_asks_for_a_new_registration() {
        let mut signed_out = connected();
        signed_out["state"] = json!("signed_out");
        let mut host = Host::new(store(signed_out));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-1"));
        host.http = vec![json!({"status":401,"body":"{\"error\":\"invalid_client\"}"})];
        let failed = host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0}),
        );
        assert_eq!(failed["code"], "chatgpt_account_changed", "{failed}");
    }

    #[test]
    fn the_flows_answer_under_the_general_name() {
        let start = |action: &str, service: Option<&str>| {
            let mut request = json!({"schema":"inku.model-catalog-request.v1","action":action,"flow":"tidy",
                "input":{},"now":NOW});
            if let Some(service) = service {
                request["service"] = json!(service);
            }
            String::from_utf8(crate::model_catalog::model_catalog_json(
                request.to_string().as_bytes(),
            ))
            .unwrap()
        };
        assert_eq!(
            start("sign_in_flow_start", Some("chatgpt")),
            start("chatgpt_flow_start", None)
        );
    }

    /// The rows every host replays through its own binding: each request of
    /// the flows above, and the answer the core gives it.
    fn shared_rows() -> Vec<Value> {
        let mut rows = Vec::new();
        let mut keep = |name: &str, host: Host| {
            for (index, row) in host.log.into_iter().enumerate() {
                let mut row = row;
                row["why"] = json!(format!("{name} {index}"));
                rows.push(row);
            }
        };
        let mut host = Host::new(json!({"profiles":{},"registrations_pending":{}}));
        host.callbacks
            .push(callback("wrong", "&client_id=client-9"));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-9"));
        host.http = vec![
            tokens(&id_token(Some(&state_value()), "client-9")),
            discovery(),
            keys(),
        ];
        host.run(
            "login",
            json!({"consent":false,"language":"ja","pending_count":0,"owner_count":0}),
        );
        keep("login", host);
        let mut host = Host::new(json!({"profiles":{},"registrations_pending":{}}));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-9"));
        host.http = vec![
            tokens(&id_token(Some(&state_value()), "client-9")),
            discovery(),
            keys(),
        ];
        host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0,"respond_before_exchange":true}),
        );
        keep("login answered before the exchange", host);
        let mut old = connected();
        old["expires_at"] = json!(NOW + 10.0);
        let mut host = Host::new(store(old));
        host.http = vec![tokens(&id_token(None, "client-1")), discovery(), keys()];
        host.run(
            "access",
            json!({"profile_id":"p1","generation":3,"deadline":NOW + 15.0}),
        );
        keep("access", host);
        let mut host = Host::new(store(connected()));
        host.http = vec![ok(
            json!({"models":[{"slug":"gpt-6.1-sol","display_name":"GPT-6.1 Sol","visibility":"list"}]}),
        )];
        host.run(
            "catalog",
            json!({"profile_id":"p1","generation":3,"force":true}),
        );
        keep("catalog", host);
        let mut host = Host::new(store(connected()));
        host.http = vec![discovery(), json!({"status":200,"body":""})];
        host.run("sign_out", json!({"profile_id":"p1"}));
        host.callbacks
            .push(callback(&state_value(), "&client_id=client-1"));
        host.http = vec![
            tokens(&id_token(Some(&state_value()), "client-1")),
            discovery(),
            keys(),
        ];
        host.run(
            "login",
            json!({"language":"en","pending_count":0,"owner_count":0}),
        );
        keep("sign_out and sign in again", host);
        let mut other = connected();
        other["id"] = json!("p2");
        let mut host = Host::new(
            json!({"profiles":{"p1":connected(),"p2":other},"registrations_pending":{},"active":"p1"}),
        );
        host.run("tidy", json!({}));
        host.run("pause", json!({"profile_id":"p1","generation":3,"code":"subscription_sharing_usage_limit_exceeded"}));
        host.run("resume", json!({"profile_id":"p1"}));
        keep("tidy, pause and resume", host);
        rows
    }

    #[test]
    fn the_shared_flow_rows_are_the_ones_the_core_answers() {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../../server/tests/data/sign-in-flow-cases.json"
        );
        let rows = Value::Array(shared_rows());
        if std::env::var_os("INKU_WRITE_SIGN_IN_FLOW_CASES").is_some() {
            let mut text = String::from("[\n");
            let items = rows.as_array().unwrap();
            for (index, row) in items.iter().enumerate() {
                text.push_str("  ");
                text.push_str(&row.to_string());
                text.push_str(if index + 1 < items.len() { ",\n" } else { "\n" });
            }
            text.push_str("]\n");
            std::fs::write(path, text).unwrap();
        }
        let saved: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        assert_eq!(saved, rows);
    }
}
