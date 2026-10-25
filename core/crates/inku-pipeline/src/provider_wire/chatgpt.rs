//! The ChatGPT plan's request bodies, the reading of its SSE stream, and what
//! its failures and model list say.
//!
//! The plan reaches OpenAI's Responses API with the subscriber's OAuth token
//! and answers as a server-sent event stream. Server, Android and Swift each
//! read that stream with their own incremental decoder. Here the host receives
//! the whole stream, holding it to the wire limit this module names, and the
//! stream is read once: event for event as Server's `SSEDecoder` and
//! `TextSSEDecoder` read it, which gives the same answer however the bytes had
//! arrived. The token, the registration, its locks, cancellation and the pause
//! on a usage limit stay with the host.

use sha2::{Digest, Sha256};

use super::{
    Refusal, Value, as_str, dumps, get, image_parts, object, ordered_schema, python_eq,
    python_loads, responses_parts, set, string, truthy,
};
use crate::identity::canonical_json;

const NAMESPACE: &str = "inku";
const FUNCTION: &str = "submit_pipeline_response";

/// The failure codes a ChatGPT error may name in public; any other is replaced
/// by one that says only what the status says.
const PUBLIC_CODES: [&str; 9] = [
    "subscription_sharing_usage_limit_exceeded",
    "subscription_sharing_user_not_eligible",
    "subscription_sharing_unsupported_capability",
    "subscription_sharing_route_not_supported",
    "subscription_sharing_invalid_user",
    "chatpass_v2_scope_not_authorized",
    "chatpass_v2_invalid_authorization_context",
    "subscription_sharing_usage_unavailable",
    "subscription_sharing_user_unavailable",
];

/// The codes whose failure is temporary however they arrive.
const TEMPORARY_CODES: [&str; 5] = [
    "subscription_sharing_usage_unavailable",
    "subscription_sharing_user_unavailable",
    "chatgpt_transport_unavailable",
    "chatgpt_auth_unavailable",
    "chatgpt_refresh_not_ready",
];

/// The next action, by code. A code in none of these lists is diagnosed.
const USAGE_CODES: [&str; 2] = ["subscription_sharing_usage_limit_exceeded", "chatgpt_quota"];
/// Asking again is enough; the pipeline does not ask again by itself.
const RETRY_CODES: [&str; 3] = [
    "chatgpt_cancelled",
    "chatgpt_attempt_busy",
    "chatgpt_session_changed",
];
const CONSENT_CODES: [&str; 3] = [
    "chatgpt_scope_required",
    "chatgpt_consent_declined",
    "chatpass_v2_scope_not_authorized",
];
const SETTINGS_CODES: [&str; 4] = [
    "chatgpt_disabled",
    "chatgpt_mode_not_allowed",
    "chatgpt_startup_unverified",
    "chatgpt_owner_not_allowed",
];
const MODELS_CODES: [&str; 3] = [
    "chatgpt_model_not_offered",
    "chatgpt_model_unavailable",
    "chatgpt_catalog_required",
];
/// Signing in again mends these. `chatgpt_exported` is a registration's
/// state, raised as `chatgpt_<state>`, once it moved to another device.
const RECONNECT_CODES: [&str; 14] = [
    "chatgpt_not_connected",
    "chatgpt_exported",
    "chatgpt_signed_out",
    "chatgpt_reauthentication_required",
    "chatgpt_identity_invalid",
    "chatgpt_identity_mismatch",
    "chatgpt_credentials_unavailable",
    "chatgpt_auth_rejected",
    "chatgpt_session_transferred",
    "chatgpt_session_stale",
    "chatgpt_session_required",
    "chatgpt_profile_required",
    "chatgpt_registration_incomplete",
    "chatpass_v2_invalid_authorization_context",
];

/// The pipeline failure and the next action for a code, the one table every
/// host reads. `temporary` says the failure was temporary as it arrived: a 5xx,
/// or an answer that never finished; a code in `TEMPORARY_CODES` always is.
pub(super) fn classify(code: &str, temporary: bool) -> (&'static str, &'static str) {
    let temporary = temporary || TEMPORARY_CODES.contains(&code);
    let failure = if code == "chatgpt_transport_timeout" {
        "transport_timeout"
    } else if temporary {
        "transport_unavailable"
    } else {
        "provider_rejected"
    };
    let action = if USAGE_CODES.contains(&code) {
        "usage"
    } else if temporary || code == "chatgpt_transport_timeout" || RETRY_CODES.contains(&code) {
        "retry"
    } else if CONSENT_CODES.contains(&code) {
        "consent"
    } else if SETTINGS_CODES.contains(&code) {
        "settings"
    } else if MODELS_CODES.contains(&code) {
        "models"
    } else if code == "chatgpt_refused" {
        "edit"
    } else if RECONNECT_CODES.contains(&code) {
        "reconnect"
    } else {
        "diagnose"
    };
    (failure, action)
}

/// The answer to `chatgpt_failure`: what a host raises for a code of its own.
/// Without `temporary`, only an answer that never finished is temporary.
pub(super) fn failure_answer(code: &str, temporary: Option<bool>) -> Value {
    let (failure, action) = classify(
        code,
        temporary.unwrap_or(code == "chatgpt_response_incomplete"),
    );
    object(vec![
        ("code", string(code)),
        ("failure", string(failure)),
        ("action", string(action)),
    ])
}

/// The stream as a whole, one event, and one answer are each bounded.
struct Limits {
    answer: usize,
    event: usize,
    wire: usize,
}

impl Limits {
    fn for_answer(answer: usize) -> Self {
        Self {
            answer,
            event: (64 * 1024).max(answer * 2 + 64 * 1024),
            wire: (1024 * 1024).max(answer * 6 + 512 * 1024),
        }
    }
}

/// The limits a host holds a stream to while it receives it.
pub(super) fn limits_answer(answer_limit: usize) -> Value {
    let limits = Limits::for_answer(answer_limit);
    object(vec![
        ("wire_limit", super::integer(limits.wire as i64)),
        ("event_limit", super::integer(limits.event as i64)),
    ])
}

// ---------------------------------------------------------------------------
// Requests.

fn request_answer(body: &Value, limits: &Limits) -> Value {
    let text = dumps(body);
    let canonical = canonical_json(&text).expect("a body this module wrote reads back");
    object(vec![
        ("body", Value::String(text)),
        // The observation record keeps the canonical form, as it did.
        ("canonical", Value::String(canonical)),
        ("wire_limit", super::integer(limits.wire as i64)),
        ("event_limit", super::integer(limits.event as i64)),
    ])
}

/// The Responses API's cache routing hint: the digest of the system text and
/// the schema, which every request of one stage and language shares (the laws
/// and colors requests since v2). In the efficiency send of 2026-10-25 the
/// plan then read most of those requests' shared part from its cache.
fn cache_key(system: &str, schema: &Value) -> String {
    let digest = Sha256::new()
        .chain_update(system.as_bytes())
        .chain_update(b"\n")
        .chain_update(dumps(schema).as_bytes())
        .finalize();
    let hex: String = digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    format!("inku-{hex}")
}

/// `chatgpt_provider.request_body`: the one function, in the `inku` namespace,
/// required; streamed and not stored, with the cache routing hint last. The
/// images the prompt names follow its message as the Vision request sends
/// them; without images the body is as it was.
pub(super) fn pipeline_request(
    model: &str,
    prompt: &Value,
    answer_limit: usize,
    images: &[String],
) -> Result<Value, Refusal> {
    let field = |name: &str| {
        as_str(get(prompt, name))
            .ok_or_else(|| Refusal::invalid(&format!("prompt.{name} must be a string")))
    };
    let schema = get(prompt, "response_schema")
        .ok_or_else(|| Refusal::invalid("prompt.response_schema is required"))?;
    let message = field("message")?;
    let system = field("system")?;
    let content = if images.is_empty() {
        string(message)
    } else {
        responses_parts(message, images)
    };
    let body = object(vec![
        ("model", string(model)),
        ("store", Value::Bool(false)),
        ("stream", Value::Bool(true)),
        ("instructions", string(system)),
        (
            "input",
            Value::Array(vec![object(vec![
                ("role", string("user")),
                ("content", content),
            ])]),
        ),
        (
            "tools",
            Value::Array(vec![object(vec![
                ("type", string("namespace")),
                ("name", string(NAMESPACE)),
                (
                    "description",
                    string("Return data for the inku drawing pipeline."),
                ),
                (
                    "tools",
                    Value::Array(vec![object(vec![
                        ("type", string("function")),
                        ("name", string(FUNCTION)),
                        ("description", string("Return the requested drawing data.")),
                        ("parameters", ordered_schema(schema, false)),
                        ("strict", Value::Bool(false)),
                    ])]),
                ),
            ])]),
        ),
        ("tool_choice", string("required")),
        ("parallel_tool_calls", Value::Bool(false)),
        ("prompt_cache_key", string(&cache_key(system, schema))),
    ]);
    Ok(request_answer(&body, &Limits::for_answer(answer_limit)))
}

/// `chatgpt_provider.vision_request_body`: text and images, no tools, no
/// temperature, no output limit. Every image is a base64 `data:` URL.
pub(super) fn vision_request(
    model: &str,
    system: &str,
    text: &str,
    images: &[String],
    answer_limit: usize,
) -> Result<Value, Refusal> {
    for image in images {
        image_parts(image)?;
    }
    let body = object(vec![
        ("model", string(model)),
        ("store", Value::Bool(false)),
        ("stream", Value::Bool(true)),
        ("instructions", string(system)),
        (
            "input",
            Value::Array(vec![object(vec![
                ("role", string("user")),
                ("content", responses_parts(text, images)),
            ])]),
        ),
    ]);
    Ok(request_answer(&body, &Limits::for_answer(answer_limit)))
}

// ---------------------------------------------------------------------------
// Failures.

/// `safe_identifier`: an identifier that may be logged, or nothing.
fn safe_identifier(value: Option<&Value>) -> Value {
    match value {
        Some(Value::String(text))
            if (1..=160).contains(&text.chars().count())
                && text.chars().all(|c| {
                    c.is_ascii_alphanumeric() || matches!(c, '_' | '.' | ':' | '[' | ']' | '-')
                }) =>
        {
            Value::String(text.clone())
        }
        _ => Value::Null,
    }
}

/// A failure the host raises as `ChatGPTError(code, failure=, action=)`.
struct Failure {
    code: String,
    failure: &'static str,
    action: &'static str,
    /// Set for a failure the provider itself reported (`ResponseFailure`).
    reported: Option<(Value, Value, Value)>,
    /// The tool shapes logged for an unexpected tool, and the call counts.
    shapes: Option<(Vec<Value>, usize, usize)>,
}

impl Failure {
    /// A failure that is not temporary, classified by its code.
    fn plain(code: &str) -> Self {
        Self::of(code, false)
    }

    fn of(code: &str, temporary: bool) -> Self {
        let (failure, action) = classify(code, temporary);
        Self {
            code: code.to_owned(),
            failure,
            action,
            reported: None,
            shapes: None,
        }
    }

    fn incomplete_retry() -> Self {
        Self::of("chatgpt_response_incomplete", true)
    }

    fn answer(&self) -> Vec<(String, Value)> {
        let mut members = vec![
            ("code".to_owned(), string(&self.code)),
            ("failure".to_owned(), string(self.failure)),
            ("action".to_owned(), string(self.action)),
        ];
        if let Some((status, request_id, param)) = &self.reported {
            members.push(("reported".to_owned(), Value::Bool(true)));
            members.push(("status".to_owned(), status.clone()));
            members.push(("request_id".to_owned(), request_id.clone()));
            members.push(("param".to_owned(), param.clone()));
        }
        if let Some((shapes, streamed, finalized)) = &self.shapes {
            members.push(("tool_shapes".to_owned(), Value::Array(shapes.clone())));
            members.push((
                "streamed_calls".to_owned(),
                super::integer(*streamed as i64),
            ));
            members.push((
                "finalized_calls".to_owned(),
                super::integer(*finalized as i64),
            ));
        }
        members
    }
}

/// `response_error`: what an HTTP error body, a `response.failed` event or a
/// stream's `error` event says. An HTTP body nests the error under `error`,
/// `response.failed` under `response`, and an `error` event carries it itself.
fn response_error(value: &Value, status: Option<i64>, request_id: Option<&Value>) -> Failure {
    let empty = Value::Object(Vec::new());
    let value = if matches!(value, Value::Object(_)) {
        value
    } else {
        &empty
    };
    let response = get(value, "response")
        .filter(|item| matches!(item, Value::Object(_)))
        .unwrap_or(&empty);
    let error = [get(value, "error"), get(response, "error")]
        .into_iter()
        .find(|item| truthy(*item))
        .flatten()
        .or_else(|| (as_str(get(value, "type")) == Some("error")).then_some(value))
        .filter(|item| matches!(item, Value::Object(_)))
        .unwrap_or(&empty);
    let named = as_str(get(error, "code")).filter(|code| PUBLIC_CODES.contains(code));
    let code = match named {
        Some(code) => code,
        None if matches!(status, Some(401 | 403)) => "chatgpt_admission_rejected",
        None if status.is_some_and(|status| status >= 500) => "chatgpt_transport_unavailable",
        None => "chatgpt_response_failed",
    };
    let mut failure = Failure::of(code, status.is_some_and(|status| status >= 500));
    failure.reported = Some((
        status.map_or(Value::Null, super::integer),
        safe_identifier(request_id),
        safe_identifier(get(error, "param")),
    ));
    failure
}

/// The answer to an HTTP error from the ChatGPT backend.
pub(super) fn error_answer(
    value: &Value,
    status: Option<i64>,
    request_id: Option<&Value>,
) -> Value {
    let mut members = vec![("outcome".to_owned(), string("failed"))];
    members.extend(response_error(value, status, request_id).answer());
    Value::Object(members)
}

// ---------------------------------------------------------------------------
// The stream.

/// Why reading stopped: a failure the host raises as it is, or a shape Python
/// raised a `TypeError`/`KeyError`/`JSONDecodeError` for (`shape`, `json`), or
/// bytes that were not UTF-8 (`utf8`, a `ValueError` there).
enum Stop {
    Failure(Box<Failure>),
    Malformed(&'static str),
}

impl From<Failure> for Stop {
    fn from(failure: Failure) -> Self {
        Stop::Failure(Box::new(failure))
    }
}

type Step<T> = Result<T, Stop>;

fn shape<T>() -> Step<T> {
    Err(Stop::Malformed("shape"))
}

fn fail<T>(code: &str) -> Step<T> {
    Err(Failure::plain(code).into())
}

/// A JSON value used as a `dict` key: hashable values only.
fn key_of(value: Option<&Value>) -> Step<String> {
    match value {
        None => shape(),
        Some(Value::Array(_) | Value::Object(_)) => shape(),
        Some(Value::Float(number)) if number.fract() == 0.0 && number.is_finite() => {
            // 1.0 and 1 are one key in a dict.
            Ok(format!("{}", *number as i128))
        }
        Some(Value::Bool(flag)) => Ok(if *flag { "1" } else { "0" }.to_owned()),
        Some(other) => Ok(dumps(other)),
    }
}

/// A `dict` from hashed key to value, in insertion order.
struct Ordered<T> {
    members: Vec<(String, T)>,
}

impl<T> Default for Ordered<T> {
    fn default() -> Self {
        Self {
            members: Vec::new(),
        }
    }
}

impl<T> Ordered<T> {
    fn get(&self, key: &str) -> Option<&T> {
        self.members
            .iter()
            .find(|(name, _)| name == key)
            .map(|(_, item)| item)
    }

    fn contains(&self, key: &str) -> bool {
        self.get(key).is_some()
    }

    fn insert(&mut self, key: String, item: T) {
        if let Some(slot) = self.members.iter_mut().find(|(name, _)| *name == key) {
            slot.1 = item;
        } else {
            self.members.push((key, item));
        }
    }

    fn len(&self) -> usize {
        self.members.len()
    }

    fn values(&self) -> impl Iterator<Item = &T> {
        self.members.iter().map(|(_, item)| item)
    }
}

/// `str(tag)` holds "refusal", for the scalar tags a stream sends.
fn names_refusal(tag: Option<&Value>) -> bool {
    match tag {
        None | Some(Value::Null) => false,
        Some(Value::String(text)) => text.contains("refusal"),
        Some(other) => dumps(other).contains("refusal"),
    }
}

fn str_of(tag: Option<&Value>) -> String {
    match tag {
        None | Some(Value::Null) => "None".to_owned(),
        Some(Value::String(text)) => text.clone(),
        Some(other) => dumps(other),
    }
}

/// `x.get(name)` on a value Python called `.get` on: a dict, or a stop.
fn field<'a>(value: &'a Value, name: &str) -> Step<Option<&'a Value>> {
    match value {
        Value::Object(_) => Ok(get(value, name)),
        _ => shape(),
    }
}

/// `x[name]`.
fn index<'a>(value: &'a Value, name: &str) -> Step<&'a Value> {
    field(value, name)?.map_or_else(shape, Ok)
}

fn is(value: Option<&Value>, text: &str) -> bool {
    as_str(value) == Some(text)
}

/// `len(text.encode())` of a value Python called `.encode()` on.
fn utf8_len(value: &Value) -> Step<usize> {
    match value {
        Value::String(text) => Ok(text.len()),
        _ => shape(),
    }
}

/// An identifier the stream carries: a non-empty string of at most 160 bytes.
fn short_id(value: Option<&Value>) -> bool {
    matches!(value, Some(Value::String(text)) if !text.is_empty() && text.len() <= 160)
}

/// Two sightings of one call name the same `call_id`, when both name one.
fn same_call(seen: &Value, item: &Value) -> bool {
    match (get(seen, "call_id"), get(item, "call_id")) {
        (None | Some(Value::Null), _) | (_, None | Some(Value::Null)) => true,
        (Some(left), Some(right)) => python_eq(left, right),
    }
}

struct Decoder {
    text: bool,
    limits: Limits,
    /// The response every event names, once one has named it.
    response_id: Option<String>,
    items: Ordered<Value>,
    finalized: Ordered<Value>,
    arguments: Ordered<Value>,
    completed: Option<String>,
    terminal: Option<Value>,
}

impl Decoder {
    fn new(text: bool, answer_limit: usize) -> Self {
        Self {
            text,
            limits: Limits::for_answer(answer_limit),
            items: Ordered::default(),
            finalized: Ordered::default(),
            arguments: Ordered::default(),
            response_id: None,
            completed: None,
            terminal: None,
        }
    }

    /// `SSEDecoder.feed` over the whole stream, then `finish`.
    fn read(&mut self, wire: &[u8]) -> Step<String> {
        if wire.len() > self.limits.wire {
            return fail("chatgpt_response_too_large");
        }
        let mut rest = wire;
        while let Some((start, end)) = event_boundary(rest) {
            let raw = &rest[..start];
            rest = &rest[end..];
            if raw.len() > self.limits.event {
                return fail("chatgpt_response_too_large");
            }
            let data = event_data(raw);
            if !data.is_empty() && data != b"[DONE]" {
                let text = std::str::from_utf8(&data).map_err(|_| Stop::Malformed("utf8"))?;
                let event = python_loads(text).map_err(|_| Stop::Malformed("json"))?;
                if self.text {
                    self.text_event(&event)?;
                } else {
                    self.event(&event)?;
                }
            }
        }
        if rest.len() > self.limits.event {
            return fail("chatgpt_response_too_large");
        }
        let leftover = rest
            .iter()
            .any(|byte| !matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c));
        match (&self.completed, leftover) {
            (Some(answer), false) => Ok(answer.clone()),
            _ => Err(Failure::incomplete_retry().into()),
        }
    }

    fn unexpected<T>(&self, items: &[&Value]) -> Step<T> {
        let mut shapes = Vec::new();
        for item in items.iter().take(4) {
            let mut members = Vec::new();
            for name in ["type", "name", "namespace"] {
                members.push((name.to_owned(), safe_identifier(field(item, name)?)));
            }
            shapes.push(Value::Object(members));
        }
        let mut failure = Failure::plain("chatgpt_unexpected_tool");
        failure.shapes = Some((shapes, self.items.len(), self.finalized.len()));
        Err(failure.into())
    }

    fn function(&self, item: &Value) -> Step<()> {
        if !is(field(item, "type")?, "function_call")
            || !is(field(item, "name")?, FUNCTION)
            || !is(field(item, "namespace")?, NAMESPACE)
        {
            return self.unexpected(&[item]);
        }
        if !short_id(get(item, "id")) {
            return fail("chatgpt_response_invalid");
        }
        Ok(())
    }

    /// A stream answers for one response: an id it names is short, and the same
    /// in every event that names one.
    fn same_response(&mut self, event: &Value) -> Step<()> {
        let Some(response @ Value::Object(_)) = get(event, "response") else {
            return Ok(());
        };
        let id = get(response, "id");
        if matches!(id, None | Some(Value::Null)) {
            return Ok(());
        }
        let Some(id) = as_str(id).filter(|_| short_id(id)) else {
            return fail("chatgpt_response_invalid");
        };
        match &self.response_id {
            Some(seen) if seen != id => fail("chatgpt_response_invalid"),
            Some(_) => Ok(()),
            None => {
                self.response_id = Some(id.to_owned());
                Ok(())
            }
        }
    }

    /// Assistant text can accompany the required call, but is never the result.
    fn auxiliary(&self, item: &Value) -> Step<()> {
        if is(field(item, "type")?, "reasoning") {
            return Ok(());
        }
        if !is(field(item, "type")?, "message") || !is(field(item, "role")?, "assistant") {
            return self.unexpected(&[item]);
        }
        for part in content_parts(item)? {
            if is(field(part, "type")?, "refusal") {
                return fail("chatgpt_refused");
            }
            if !is(field(part, "type")?, "output_text") {
                return self.unexpected(&[part]);
            }
        }
        Ok(())
    }

    /// `SSEDecoder.event`.
    fn event(&mut self, event: &Value) -> Step<()> {
        let tag = field(event, "type")?;
        if is(tag, "error") || is(tag, "response.failed") {
            self.terminal = get(event, "response")
                .filter(|item| !matches!(item, Value::Null))
                .cloned();
            return Err(response_error(event, None, None).into());
        }
        if is(tag, "response.incomplete") {
            return Err(Failure::incomplete_retry().into());
        }
        if names_refusal(tag) {
            return fail("chatgpt_refused");
        }
        if truthy(self.terminal.as_ref()) {
            return fail("chatgpt_response_invalid");
        }
        self.same_response(event)?;
        let tag = str_of(tag);
        match tag.as_str() {
            "response.output_item.added" | "response.output_item.done" => {
                let item = index(event, "item")?;
                if is(field(item, "type")?, "function_call") {
                    self.function(item)?;
                    let key = key_of(get(item, "id"))?;
                    if !self.items.contains(&key) && self.items.len() > 0 {
                        let mut seen: Vec<&Value> = self.items.values().collect();
                        seen.push(item);
                        return self.unexpected(&seen);
                    }
                    if self
                        .items
                        .get(&key)
                        .is_some_and(|seen| !same_call(seen, item))
                    {
                        return fail("chatgpt_response_invalid");
                    }
                    self.items.insert(key.clone(), item.clone());
                    if tag == "response.output_item.done" {
                        let status = get(item, "status");
                        if !matches!(status, None | Some(Value::Null)) && !is(status, "completed") {
                            return fail("chatgpt_response_incomplete");
                        }
                        let arguments = get(item, "arguments");
                        let Some(arguments @ Value::String(_)) = arguments else {
                            return fail("chatgpt_response_invalid");
                        };
                        if self
                            .arguments
                            .get(&key)
                            .is_some_and(|streamed| !python_eq(streamed, arguments))
                        {
                            return fail("chatgpt_response_invalid");
                        }
                        if utf8_len(arguments)? > self.limits.answer {
                            return fail("chatgpt_response_too_large");
                        }
                        self.finalized.insert(key, item.clone());
                    }
                } else {
                    self.auxiliary(item)?;
                }
            }
            "response.function_call_arguments.delta" => {
                let key = key_of(Some(index(event, "item_id")?))?;
                if !self.items.contains(&key) {
                    return fail("chatgpt_response_invalid");
                }
                let mut value = match self.arguments.get(&key) {
                    None => String::new(),
                    Some(Value::String(text)) => text.clone(),
                    Some(_) => return shape(),
                };
                match index(event, "delta")? {
                    Value::String(delta) => value.push_str(delta),
                    _ => return shape(),
                }
                if value.len() > self.limits.answer {
                    return fail("chatgpt_response_too_large");
                }
                self.arguments.insert(key, Value::String(value));
            }
            "response.function_call_arguments.done" => {
                let key = key_of(Some(index(event, "item_id")?))?;
                if !self.items.contains(&key) {
                    return fail("chatgpt_response_invalid");
                }
                if let Some(streamed) = self.arguments.get(&key)
                    && !python_eq(streamed, index(event, "arguments")?)
                {
                    return fail("chatgpt_response_invalid");
                }
                let arguments = index(event, "arguments")?;
                if utf8_len(arguments)? > self.limits.answer {
                    return fail("chatgpt_response_too_large");
                }
                self.arguments.insert(key, arguments.clone());
            }
            "response.completed" => {
                let response = index(event, "response")?;
                if !is(field(response, "status")?, "completed") {
                    return fail("chatgpt_response_incomplete");
                }
                // Some streams finish with an empty summary. The finalized item
                // events contain the result; deltas alone never count.
                let finalized: Vec<Value> = self.finalized.values().cloned().collect();
                let output: Vec<Value> = match get(response, "output") {
                    None | Some(Value::Null) => finalized,
                    Some(Value::Array(items)) if items.is_empty() => finalized,
                    Some(Value::Array(items)) => items.clone(),
                    Some(_) => return fail("chatgpt_response_invalid"),
                };
                let mut calls = Vec::new();
                for item in &output {
                    if is(field(item, "type")?, "function_call") {
                        calls.push(item);
                    } else {
                        self.auxiliary(item)?;
                    }
                }
                if calls.len() != 1 {
                    let all: Vec<&Value> = output.iter().collect();
                    return self.unexpected(&all);
                }
                let item = calls[0];
                self.function(item)?;
                let arguments = index(item, "arguments")?;
                let key = key_of(get(item, "id"))?;
                let finalized = self.finalized.get(&key);
                if self
                    .items
                    .get(&key)
                    .is_none_or(|seen| !same_call(seen, item))
                    || self
                        .arguments
                        .get(&key)
                        .is_some_and(|streamed| !python_eq(streamed, arguments))
                    || finalized.is_some_and(|done| {
                        get(done, "arguments").is_none_or(|kept| !python_eq(kept, arguments))
                    })
                {
                    return fail("chatgpt_response_invalid");
                }
                if utf8_len(arguments)? > self.limits.answer {
                    return fail("chatgpt_response_too_large");
                }
                let Value::String(text) = arguments else {
                    return shape();
                };
                match python_loads(text) {
                    Ok(Value::Object(_)) => {}
                    Ok(_) => return fail("chatgpt_response_invalid"),
                    Err(_) => return Err(Stop::Malformed("json")),
                }
                self.completed = Some(text.clone());
                self.terminal = Some(response.clone());
            }
            _ => {}
        }
        Ok(())
    }

    /// `TextSSEDecoder._text`: a completed assistant message's text.
    fn text_of(&self, item: &Value) -> Step<String> {
        if is(field(item, "type")?, "reasoning") {
            return Ok(String::new());
        }
        if !is(field(item, "type")?, "message") || !is(field(item, "role")?, "assistant") {
            return self.unexpected(&[item]);
        }
        let status = get(item, "status");
        if !matches!(status, None | Some(Value::Null)) && !is(status, "completed") {
            return fail("chatgpt_response_incomplete");
        }
        let mut text = String::new();
        for part in content_parts(item)? {
            if is(field(part, "type")?, "refusal") {
                return fail("chatgpt_refused");
            }
            match (is(field(part, "type")?, "output_text"), get(part, "text")) {
                (true, Some(Value::String(piece))) => text.push_str(piece),
                _ => return fail("chatgpt_response_invalid"),
            }
        }
        if text.len() > self.limits.answer {
            return fail("chatgpt_response_too_large");
        }
        Ok(text)
    }

    /// `TextSSEDecoder.event`: Vision takes completed assistant text, never
    /// partial text or tool calls.
    fn text_event(&mut self, event: &Value) -> Step<()> {
        let tag = field(event, "type")?;
        if is(tag, "error")
            || is(tag, "response.failed")
            || is(tag, "response.incomplete")
            || names_refusal(tag)
        {
            return self.event(event);
        }
        if self.terminal.is_some() {
            return fail("chatgpt_response_invalid");
        }
        self.same_response(event)?;
        let tag = str_of(tag);
        match tag.as_str() {
            "response.output_item.added" | "response.output_item.done" => {
                let item = index(event, "item")?;
                let kind = field(item, "type")?;
                if !is(kind, "message") && !is(kind, "reasoning") {
                    return self.unexpected(&[item]);
                }
                if tag == "response.output_item.done" {
                    self.text_of(item)?;
                    let key = key_of(get(item, "id"))?;
                    self.finalized.insert(key, item.clone());
                }
            }
            "response.completed" => {
                let response = index(event, "response")?;
                if !is(field(response, "status")?, "completed") {
                    return fail("chatgpt_response_incomplete");
                }
                let finalized: Vec<Value> = self.finalized.values().cloned().collect();
                let output: Vec<Value> = match get(response, "output") {
                    None | Some(Value::Null) => finalized,
                    Some(Value::Array(items)) if items.is_empty() => finalized,
                    Some(Value::Array(items)) => items.clone(),
                    Some(_) => return fail("chatgpt_response_invalid"),
                };
                let mut text = String::new();
                for item in &output {
                    text.push_str(&self.text_of(item)?);
                }
                if text.len() > self.limits.answer {
                    return fail("chatgpt_response_too_large");
                }
                if text.is_empty() {
                    return fail("chatgpt_response_invalid");
                }
                self.completed = Some(text);
                self.terminal = Some(response.clone());
            }
            _ if tag.starts_with("response.function_call") => {
                return fail("chatgpt_unexpected_tool");
            }
            "response.output_text.delta" | "response.output_text.done" => {
                let name = if tag.ends_with("delta") {
                    "delta"
                } else {
                    "text"
                };
                match get(event, name) {
                    Some(Value::String(piece)) if piece.len() > self.limits.answer => {
                        return fail("chatgpt_response_too_large");
                    }
                    Some(Value::String(_)) => {}
                    _ => return fail("chatgpt_response_invalid"),
                }
            }
            _ => {}
        }
        Ok(())
    }
}

/// `item.get("content", [])`, iterated.
fn content_parts(item: &Value) -> Step<Vec<&Value>> {
    match field(item, "content")? {
        None => Ok(Vec::new()),
        Some(Value::Array(parts)) => Ok(parts.iter().collect()),
        // Iterating a dict or a string yields keys or characters, on which
        // `.get` fails; an empty one yields nothing.
        Some(Value::Object(members)) if members.is_empty() => Ok(Vec::new()),
        Some(Value::String(text)) if text.is_empty() => Ok(Vec::new()),
        Some(_) => shape(),
    }
}

/// The first `\r?\n\r?\n` in `bytes`: CRLF and LF both end a line.
fn event_boundary(bytes: &[u8]) -> Option<(usize, usize)> {
    let newline = |at: usize| -> Option<usize> {
        match (bytes.get(at), bytes.get(at + 1)) {
            (Some(b'\r'), Some(b'\n')) => Some(at + 2),
            (Some(b'\n'), _) => Some(at + 1),
            _ => None,
        }
    };
    (0..bytes.len()).find_map(|start| {
        let middle = newline(start)?;
        newline(middle).map(|end| (start, end))
    })
}

/// The `data:` lines of one event joined, each with its leading spaces dropped.
fn event_data(raw: &[u8]) -> Vec<u8> {
    let mut lines: Vec<&[u8]> = Vec::new();
    let mut start = 0;
    let mut at = 0;
    while at < raw.len() {
        match raw[at] {
            b'\r' => {
                lines.push(&raw[start..at]);
                at += if raw.get(at + 1) == Some(&b'\n') {
                    2
                } else {
                    1
                };
                start = at;
            }
            b'\n' => {
                lines.push(&raw[start..at]);
                at += 1;
                start = at;
            }
            _ => at += 1,
        }
    }
    if start < raw.len() {
        lines.push(&raw[start..]);
    }
    let mut data = Vec::new();
    let mut first = true;
    for line in lines {
        if let Some(rest) = line.strip_prefix(b"data:") {
            if !first {
                data.push(b'\n');
            }
            first = false;
            let kept = rest
                .iter()
                .position(|byte| *byte != b' ')
                .unwrap_or(rest.len());
            data.extend_from_slice(&rest[kept..]);
        }
    }
    data
}

/// The answer to a whole stream.
pub(super) fn stream_answer(text: bool, answer_limit: usize, wire: &[u8]) -> Value {
    let mut decoder = Decoder::new(text, answer_limit);
    let read = decoder.read(wire);
    let mut members: Vec<(String, Value)> = Vec::new();
    match read {
        Ok(answer) => {
            members.push(("outcome".to_owned(), string("answer")));
            members.push(("text".to_owned(), Value::String(answer)));
        }
        Err(Stop::Failure(failure)) => {
            members.push(("outcome".to_owned(), string("failed")));
            members.extend(failure.answer());
        }
        Err(Stop::Malformed(kind)) => {
            members.push(("outcome".to_owned(), string("malformed")));
            members.push(("kind".to_owned(), string(kind)));
        }
    }
    // The observation keeps the last response and whether an answer completed.
    members.push((
        "completed".to_owned(),
        Value::Bool(decoder.completed.is_some()),
    ));
    members.push((
        "terminal".to_owned(),
        decoder.terminal.unwrap_or(Value::Null),
    ));
    Value::Object(members)
}

// ---------------------------------------------------------------------------
// The model list.

/// The longest slug and display name a listed model may have, in UTF-8 bytes.
const SLUG_BYTES: usize = 256;
const LABEL_BYTES: usize = 512;

/// The models the backend lists for the subscriber: `visibility == "list"`,
/// with a slug and a display name. A row that cannot be published is dropped
/// rather than losing the list, and a slug listed twice keeps its first row;
/// `dropped` counts the listed rows left out.
pub(super) fn catalog_answer(value: &Value) -> Value {
    let Some(Value::Array(entries)) = get(value, "models") else {
        return object(vec![("outcome", string("malformed"))]);
    };
    let mut models = Vec::new();
    let mut slugs: Vec<&str> = Vec::new();
    let mut dropped = 0;
    for entry in entries {
        if matches!(entry, Value::Object(_)) && !is(get(entry, "visibility"), "list") {
            continue;
        }
        let named = |name: &str, limit: usize| {
            as_str(get(entry, name)).filter(|text| !text.is_empty() && text.len() <= limit)
        };
        let (Some(slug), Some(label)) = (
            named("slug", SLUG_BYTES),
            named("display_name", LABEL_BYTES),
        ) else {
            dropped += 1;
            continue;
        };
        if slugs.contains(&slug) {
            dropped += 1;
            continue;
        }
        slugs.push(slug);
        {
            let mut model = Vec::new();
            set(&mut model, "id", string(slug));
            set(&mut model, "label", string(label));
            set(
                &mut model,
                "purposes",
                Value::Array(vec![string("llm"), string("vision")]),
            );
            models.push(Value::Object(model));
        }
    }
    object(vec![
        ("outcome", string("ok")),
        ("models", Value::Array(models)),
        ("dropped", super::integer(dropped)),
    ])
}

/// Standard base64, as the host sends the stream's bytes.
pub(super) fn base64_decode(text: &str) -> Option<Vec<u8>> {
    let value = |byte: u8| -> Option<u32> {
        Some(match byte {
            b'A'..=b'Z' => byte - b'A',
            b'a'..=b'z' => byte - b'a' + 26,
            b'0'..=b'9' => byte - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => return None,
        } as u32)
    };
    let bytes = text.trim_end_matches('=').as_bytes();
    if !text.len().is_multiple_of(4) || text.len() - bytes.len() > 2 {
        return None;
    }
    let mut out = Vec::with_capacity(bytes.len() * 3 / 4);
    for chunk in bytes.chunks(4) {
        let mut acc = 0u32;
        for (index, byte) in chunk.iter().enumerate() {
            acc |= value(*byte)? << (18 - 6 * index);
        }
        let produced = match chunk.len() {
            4 => 3,
            3 => 2,
            2 => 1,
            _ => return None,
        };
        for index in 0..produced {
            out.push((acc >> (16 - 8 * index)) as u8);
        }
    }
    Some(out)
}
