//! The bytes a provider request carries and what its answer says.
//!
//! The core never talks to a provider: it returns a `CallLlm` effect and a host
//! sends it. How that prompt becomes a request body for each provider dialect
//! (the thinking level a model takes, the room left for thinking it does
//! unasked, whether a temperature may be sent, the tool's shape, the order a
//! schema's properties are written in), and how the answer is taken back out of
//! the response, were written three times, in Server, Android and Swift. Every
//! provider change landed three times, Server first, and the copies drifted.
//! Server's rules are the ones kept here, byte for byte: Server's observation
//! records must not change, so a body is written as Python's
//! `json.dumps(body, ensure_ascii=False, separators=(",", ":"))` wrote it, with
//! its keys in the order Server inserted them.
//!
//! The host keeps everything that touches the outside: the key, which it adds
//! under the header this module names; the HTTP exchange and its deadline; the
//! provider's concurrency slot and rate budget; the observation store; logging.

use crate::identity::{Value, python_dumps, python_float_repr, python_loads, python_strip};

mod chatgpt;

pub const PROVIDER_WIRE_SCHEMA_ID: &str = "inku.provider-wire.v1";

const RESPONSE_NAME: &str = "submit_pipeline_response";
const TOOL_DESCRIPTION: &str = "Submit the requested pipeline response.";
/// Claude 5 and Mythos Preview think unasked, and Gemini counts thoughts within
/// `maxOutputTokens`; both are left this much room beside the answer.
const THINKING_ROOM_TOKENS: i64 = 8192;
/// OpenAI recommends reserving at least 25,000 tokens for reasoning and output.
const OPENAI_REASONING_ROOM_TOKENS: i64 = 25000;
const OLLAMA_THINKING_ROOM_TOKENS: i64 = 8192;
const OPENAI_API_HOST: &str = "api.openai.com";
/// The composition reading is sent as the prototype measured it, with Stage 1's
/// sampling (COMPOSITION-PRODUCT-DESIGN section 12), and so are the laws, the
/// colors and the three stages that read and draw a description (their
/// prototypes' requests went as Stage 1's).
const STAGE1_SAMPLED_ACTIONS: [&str; 7] = [
    "generate_normalized_ddl",
    "read_composition",
    "choose_laws",
    "choose_colors",
    "read_description",
    "write_description_ddl",
    "review_description_ddl",
];
/// A refusal body is read only this far, as Server read it.
const REFUSAL_READ_BYTES: usize = 16384;

// ---------------------------------------------------------------------------
// Model names.

/// Python's `$` in a `re.match` pattern: the end, or a final newline.
fn at_end(rest: &str) -> bool {
    rest.is_empty() || rest == "\n"
}

/// `(?:-|$)` after a matched prefix.
fn dash_or_end(rest: &str) -> bool {
    rest.starts_with('-') || at_end(rest)
}

/// `^claude-(?:(?:opus|sonnet|haiku|fable|mythos)-5(?:-|$)|mythos-preview(?:-|$))`:
/// the models that think adaptively when a request sends no `thinking` field
/// (per-model table, platform.claude.com, read 2026-10-13).
fn anthropic_thinks_by_default(model: &str) -> bool {
    let Some(rest) = model.strip_prefix("claude-") else {
        return false;
    };
    let five = ["opus", "sonnet", "haiku", "fable", "mythos"]
        .iter()
        .any(|family| {
            rest.strip_prefix(family)
                .and_then(|after| after.strip_prefix("-5"))
                .is_some_and(dash_or_end)
        });
    five || rest.strip_prefix("mythos-preview").is_some_and(dash_or_end)
}

fn anthropic_max_tokens(model: &str, answer_tokens: i64) -> i64 {
    answer_tokens
        + if anthropic_thinks_by_default(model) {
            THINKING_ROOM_TOKENS
        } else {
            0
        }
}

/// The models known to take Gemini's `minimal` thinking level: those the
/// thinking-levels table lists it for and the ids that answered with it in the
/// draw session's 2026-10-12 runs. Every other thinking model is sent `low`.
const GEMINI_MINIMAL: [&str; 13] = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3.1-flash-lite-image",
    "gemini-robotics-er-2-preview",
    "nano-banana-pro-preview",
    "gemini-nano-banana-2.1",
];

/// The thinking level a Gemini model is sent; `None` sends no level, for the
/// models that think only when asked or refuse a level
/// (`^(?:gemini-2\.5-flash-(?:lite|image)(?:-|$)|antigravity-)`).
fn gemini_level(model: &str) -> Option<&'static str> {
    let name = model.strip_prefix("models/").unwrap_or(model);
    let no_level = name
        .strip_prefix("gemini-2.5-flash-")
        .and_then(|rest| {
            rest.strip_prefix("lite")
                .or_else(|| rest.strip_prefix("image"))
        })
        .is_some_and(dash_or_end)
        || name.starts_with("antigravity-");
    if no_level {
        None
    } else if GEMINI_MINIMAL.contains(&name) || name.starts_with("gemma-") {
        Some("minimal")
    } else {
        Some("low")
    }
}

fn gemini_max_output_tokens(model: &str, answer_tokens: i64) -> i64 {
    answer_tokens
        + if gemini_level(model).is_some() {
            THINKING_ROOM_TOKENS
        } else {
            0
        }
}

/// `^(gpt-5|gpt-6|o\d)`: OpenAI's reasoning families, which refuse any
/// temperature but the default.
fn openai_reasoning(model: &str) -> bool {
    model.starts_with("gpt-5")
        || model.starts_with("gpt-6")
        || model
            .strip_prefix('o')
            .is_some_and(|rest| rest.starts_with(|c: char| c.is_ascii_digit()))
}

/// `^(gpt-5\.\d|gpt-6-(?:sol|luna)(?:-|$))`: the reasoning models that take
/// `reasoning_effort` "none" (reasoning and latest-model guides, read 2026-10-13).
fn openai_reasoning_can_stop(model: &str) -> bool {
    model
        .strip_prefix("gpt-5.")
        .is_some_and(|rest| rest.starts_with(|c: char| c.is_ascii_digit()))
        || model
            .strip_prefix("gpt-6-")
            .and_then(|rest| {
                rest.strip_prefix("sol")
                    .or_else(|| rest.strip_prefix("luna"))
            })
            .is_some_and(dash_or_end)
}

/// `^gemma[-_]?4(?:[-_]|$)`, ignoring case, on the last path segment.
fn gemma4(model: &str) -> bool {
    let name = model.rsplit('/').next().unwrap_or(model);
    let lower = name.to_ascii_lowercase();
    let Some(rest) = lower.strip_prefix("gemma") else {
        return false;
    };
    let rest = rest.strip_prefix(['-', '_']).unwrap_or(rest);
    rest.strip_prefix('4')
        .is_some_and(|after| after.starts_with(['-', '_']) || at_end(after))
}

/// `^gpt-oss(?:[:-]|$)`: on Ollama, gpt-oss lists only low, medium and high, so
/// it cannot be asked not to think.
fn ollama_levels_only(model: &str) -> bool {
    model
        .strip_prefix("gpt-oss")
        .is_some_and(|rest| rest.starts_with([':', '-']) || at_end(rest))
}

// ---------------------------------------------------------------------------
// Connections.

struct Connection {
    id: String,
    kind: String,
    api_profile: String,
    base_url: String,
}

impl Connection {
    /// `httpx.URL(base_url).host == "api.openai.com"`.
    fn is_openai_api(&self) -> bool {
        url_host(&self.base_url) == OPENAI_API_HOST
    }

    /// The base URL as Server joined a path to it, `rstrip("/")`.
    fn base(&self) -> &str {
        self.base_url.trim_end_matches('/')
    }
}

/// The host of an absolute URL, lowercased, as httpx reads it; empty for a URL
/// without an authority.
fn url_host(url: &str) -> String {
    let Some((_, rest)) = url.split_once("://") else {
        return String::new();
    };
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    let host_port = authority
        .rsplit_once('@')
        .map_or(authority, |(_, host)| host);
    let host = if let Some(bracketed) = host_port.strip_prefix('[') {
        bracketed.split(']').next().unwrap_or("")
    } else {
        host_port.split(':').next().unwrap_or("")
    };
    host.to_ascii_lowercase()
}

/// `urllib.parse.quote(model, safe="")`: the model id as one path segment.
fn quote_segment(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for byte in text.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'-' | b'~') {
            out.push(byte as char);
        } else {
            out.push_str(&format!("%{byte:02X}"));
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Values as Python holds them.

fn string(text: &str) -> Value {
    Value::String(text.to_owned())
}

fn integer(number: i64) -> Value {
    Value::Integer(number.to_string())
}

fn float(number: f64) -> Value {
    Value::Float(number)
}

fn object(members: Vec<(&str, Value)>) -> Value {
    Value::Object(
        members
            .into_iter()
            .map(|(name, item)| (name.to_owned(), item))
            .collect(),
    )
}

fn get<'a>(value: &'a Value, name: &str) -> Option<&'a Value> {
    match value {
        Value::Object(members) => members
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, item)| item),
        _ => None,
    }
}

fn as_str(value: Option<&Value>) -> Option<&str> {
    match value {
        Some(Value::String(text)) => Some(text),
        _ => None,
    }
}

fn as_object(value: Option<&Value>) -> Option<&Vec<(String, Value)>> {
    match value {
        Some(Value::Object(members)) => Some(members),
        _ => None,
    }
}

fn as_array(value: Option<&Value>) -> Option<&Vec<Value>> {
    match value {
        Some(Value::Array(items)) => Some(items),
        _ => None,
    }
}

/// `dict[name] = item`: replaced in place when present, appended otherwise.
fn set(members: &mut Vec<(String, Value)>, name: &str, item: Value) {
    if let Some(slot) = members.iter_mut().find(|(key, _)| key == name) {
        slot.1 = item;
    } else {
        members.push((name.to_owned(), item));
    }
}

/// Python's truth value.
fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Integer(digits)) => digits != "0",
        Some(Value::Float(number)) => *number != 0.0,
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Object(members)) => !members.is_empty(),
    }
}

/// A non-negative integer that is not a bool, as `isinstance(x, int)` read it.
fn count(value: Option<&Value>) -> Option<Value> {
    match value {
        Some(Value::Integer(digits)) if !digits.starts_with('-') => {
            Some(Value::Integer(digits.clone()))
        }
        _ => None,
    }
}

/// The number Python compared a numeric JSON value as, when it is one.
fn numeric(value: &Value) -> Option<f64> {
    match value {
        Value::Bool(flag) => Some(f64::from(u8::from(*flag))),
        Value::Integer(digits) => digits.parse().ok(),
        Value::Float(number) => Some(*number),
        _ => None,
    }
}

/// Python's `==` on decoded JSON: a dict compares without regard to order, and
/// `True`, `1` and `1.0` are equal.
fn python_eq(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Integer(a), Value::Integer(b)) => a == b,
        (Value::Null, Value::Null) => true,
        (Value::String(a), Value::String(b)) => a == b,
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(x, y)| python_eq(x, y))
        }
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter().all(|(name, item)| {
                    b.iter()
                        .find(|(other, _)| other == name)
                        .is_some_and(|(_, theirs)| python_eq(item, theirs))
                })
        }
        _ => match (numeric(left), numeric(right)) {
            (Some(a), Some(b)) => a == b,
            _ => false,
        },
    }
}

/// `str(value)` for the scalar values an answer's text parts hold.
fn python_str(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.clone()),
        Value::Null => Some("None".to_owned()),
        Value::Bool(true) => Some("True".to_owned()),
        Value::Bool(false) => Some("False".to_owned()),
        Value::Integer(digits) => Some(digits.clone()),
        Value::Float(number) => Some(match python_float_repr(*number).as_str() {
            "NaN" => "nan".to_owned(),
            "Infinity" => "inf".to_owned(),
            "-Infinity" => "-inf".to_owned(),
            other => other.to_owned(),
        }),
        Value::Array(_) | Value::Object(_) => None,
    }
}

fn dumps(value: &Value) -> String {
    let mut out = String::new();
    python_dumps(value, &mut out);
    out
}

// ---------------------------------------------------------------------------
// Schemas.

/// Keys whose value maps names to schemas rather than being a schema itself.
const NAMED_SCHEMA_MAPS: [&str; 4] = ["properties", "$defs", "definitions", "patternProperties"];

/// Properties written first in the order `propertyOrdering` names them, the
/// rest after in their present order.
fn apply_property_ordering(members: &mut [(String, Value)]) {
    let Some(Value::Array(ordering)) = members
        .iter()
        .find(|(key, _)| key == "propertyOrdering")
        .map(|(_, item)| item.clone())
    else {
        return;
    };
    let Some((_, Value::Object(properties))) =
        members.iter_mut().find(|(key, _)| key == "properties")
    else {
        return;
    };
    let mut ordered: Vec<(String, Value)> = Vec::with_capacity(properties.len());
    for name in ordering.iter().filter_map(|item| match item {
        Value::String(name) => Some(name),
        _ => None,
    }) {
        if ordered.iter().any(|(key, _)| key == name) {
            continue;
        }
        if let Some(member) = properties.iter().find(|(key, _)| key == name) {
            ordered.push(member.clone());
        }
    }
    for member in properties.iter() {
        if !ordered.iter().any(|(key, _)| key == &member.0) {
            ordered.push(member.clone());
        }
    }
    *properties = ordered;
}

/// `schema_order.ordered_schema`: each object's properties in its
/// `propertyOrdering`, nested ones too. Nothing is dropped.
fn ordered_schema(value: &Value, named: bool) -> Value {
    match value {
        Value::Array(items) => Value::Array(
            items
                .iter()
                .map(|item| ordered_schema(item, false))
                .collect(),
        ),
        Value::Object(members) if named => Value::Object(
            members
                .iter()
                .map(|(name, item)| (name.clone(), ordered_schema(item, false)))
                .collect(),
        ),
        Value::Object(members) => {
            let mut result: Vec<(String, Value)> = members
                .iter()
                .map(|(key, item)| {
                    (
                        key.clone(),
                        ordered_schema(item, NAMED_SCHEMA_MAPS.contains(&key.as_str())),
                    )
                })
                .collect();
            apply_property_ordering(&mut result);
            Value::Object(result)
        }
        other => other.clone(),
    }
}

/// The stages whose system text and schema are the same for every work
/// (2026-10-25). Anthropic is asked to keep them (`cache_control`): the next
/// work's request and a request asked again read them at the cache's price.
/// Another stage's system text or schema changes with the work, and a mark
/// would only write a new entry each time.
const CACHED_ACTIONS: [&str; 2] = ["choose_laws", "choose_colors"];

/// Anthropic's system: the text, as one block the cache keeps for the stages
/// that send the same system text and schema to every work.
fn anthropic_system(system: &str, action_name: &str) -> Value {
    if CACHED_ACTIONS.contains(&action_name) {
        Value::Array(vec![object(vec![
            ("type", string("text")),
            ("text", string(system)),
            ("cache_control", object(vec![("type", string("ephemeral"))])),
        ])])
    } else {
        string(system)
    }
}

/// The JSON Schema keywords Gemini's function declarations take.
const GEMINI_SCHEMA_KEYS: [&str; 21] = [
    "$anchor",
    "$defs",
    "$id",
    "$ref",
    "additionalProperties",
    "anyOf",
    "description",
    "enum",
    "format",
    "items",
    "maxItems",
    "maximum",
    "minItems",
    "minimum",
    "oneOf",
    "prefixItems",
    "properties",
    "propertyOrdering",
    "required",
    "title",
    "type",
];

fn gemini_project(value: &Value, named: bool) -> Value {
    match value {
        Value::Array(items) => Value::Array(
            items
                .iter()
                .map(|item| gemini_project(item, false))
                .collect(),
        ),
        Value::Object(members) if named => Value::Object(
            members
                .iter()
                .map(|(name, item)| (name.clone(), gemini_project(item, false)))
                .collect(),
        ),
        Value::Object(members) => {
            let mut projected: Vec<(String, Value)> = Vec::new();
            for (key, item) in members {
                if key == "const" {
                    set(&mut projected, "enum", Value::Array(vec![item.clone()]));
                } else if GEMINI_SCHEMA_KEYS.contains(&key.as_str()) {
                    let item = gemini_project(item, key == "$defs" || key == "properties");
                    set(&mut projected, key, item);
                }
            }
            apply_property_ordering(&mut projected);
            Value::Object(projected)
        }
        other => other.clone(),
    }
}

/// `_merge_gemini_variant_values`: one value standing for every variant, or
/// `None` when they cannot be written as one.
fn merge_variant_values(values: &[&Value]) -> Option<Value> {
    let first = values[0];
    if values[1..].iter().all(|value| python_eq(value, first)) {
        return Some(first.clone());
    }
    let objects: Vec<&Vec<(String, Value)>> = values
        .iter()
        .map(|value| match value {
            Value::Object(members) => Some(members),
            _ => None,
        })
        .collect::<Option<_>>()?;
    let keys: Vec<&String> = objects[0].iter().map(|(key, _)| key).collect();
    if !objects[1..]
        .iter()
        .all(|members| members.iter().map(|(key, _)| key).eq(keys.iter().copied()))
    {
        return None;
    }
    if keys.len() == 1
        && keys[0] == "enum"
        && objects
            .iter()
            .all(|members| matches!(&members[0].1, Value::Array(items) if items.len() == 1))
    {
        let values = objects
            .iter()
            .map(|members| match &members[0].1 {
                Value::Array(items) => items[0].clone(),
                _ => unreachable!("checked above"),
            })
            .collect();
        return Some(object(vec![("enum", Value::Array(values))]));
    }
    let mut merged = Vec::with_capacity(keys.len());
    for (index, key) in keys.iter().enumerate() {
        let items: Vec<&Value> = objects.iter().map(|members| &members[index].1).collect();
        merged.push(((*key).clone(), merge_variant_values(&items)?));
    }
    Some(Value::Object(merged))
}

/// `_compact_gemini_hole_variants`: Gemini receives the hole edits as one flat
/// object. The core still validates each returned edit against the full schema.
fn compact_gemini_hole_variants(schema: &mut Value) {
    let Value::Object(members) = schema else {
        return;
    };
    let Some((_, Value::Object(properties))) =
        members.iter_mut().find(|(key, _)| key == "properties")
    else {
        return;
    };
    let name = if truthy(
        properties
            .iter()
            .find(|(key, _)| key == "results")
            .map(|(_, item)| item),
    ) {
        "results"
    } else {
        "edits"
    };
    let Some((_, Value::Object(collection))) = properties.iter_mut().find(|(key, _)| key == name)
    else {
        return;
    };
    let items = collection
        .iter()
        .find(|(key, _)| key == "items")
        .map(|(_, item)| item);
    let Some(variants) = as_array(get(items.unwrap_or(&Value::Null), "oneOf"))
        .filter(|variants| !variants.is_empty())
    else {
        return;
    };
    let variants = variants.clone();
    let references: Vec<&Value> = variants.iter().collect();
    if let Some(merged) = merge_variant_values(&references)
        && as_str(get(&merged, "type")) == Some("object")
    {
        set(collection, "items", merged);
        return;
    }
    // A result requires either `replacement` or `reason`; Gemini's schema cannot
    // say so compactly, so both are offered and Rust keeps the exact one-of check.
    let Some(variant_properties) = variants
        .iter()
        .map(|variant| as_object(get(variant, "properties")))
        .collect::<Option<Vec<_>>>()
    else {
        return;
    };
    let required_of = |variant: &Value| -> Vec<String> {
        as_array(get(variant, "required"))
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| as_str(Some(item)).map(str::to_owned))
                    .collect()
            })
            .unwrap_or_default()
    };
    let mut shared: Vec<String> = required_of(&variants[0]);
    for variant in &variants[1..] {
        let theirs = required_of(variant);
        shared.retain(|name| theirs.contains(name));
    }
    shared.sort();
    shared.dedup();
    let mut names: Vec<&String> = variant_properties
        .iter()
        .flat_map(|members| members.iter().map(|(key, _)| key))
        .collect();
    names.sort();
    names.dedup();
    let mut merged_properties = Vec::with_capacity(names.len());
    for name in names {
        let candidates: Vec<&Value> = variant_properties
            .iter()
            .filter_map(|members| {
                members
                    .iter()
                    .find(|(key, _)| key == name)
                    .map(|(_, item)| item)
            })
            .collect();
        let Some(merged) = merge_variant_values(&candidates) else {
            return;
        };
        merged_properties.push((name.clone(), merged));
    }
    set(
        collection,
        "items",
        object(vec![
            ("type", string("object")),
            ("additionalProperties", Value::Bool(false)),
            (
                "required",
                Value::Array(shared.iter().map(|name| string(name)).collect()),
            ),
            ("properties", Value::Object(merged_properties)),
        ]),
    );
}

/// `_gemini_json_schema`: the core's schema in Gemini's supported subset.
fn gemini_schema(schema: &Value, compact_hole_edits: bool) -> Result<Value, Refusal> {
    let mut result = gemini_project(schema, false);
    if as_str(get(&result, "type")) != Some("object") {
        return Err(Refusal::rejected(
            "Gemini function schema must describe an object",
        ));
    }
    if compact_hole_edits {
        compact_gemini_hole_variants(&mut result);
    }
    Ok(result)
}

// ---------------------------------------------------------------------------
// Requests.

/// Why a request cannot be built. `rejected` is what Server answered with a
/// `ValueError` before sending: the attempt fails as `provider_rejected`.
struct Refusal {
    reason: &'static str,
    detail: String,
}

impl Refusal {
    fn rejected(detail: &str) -> Self {
        Self {
            reason: "provider_rejected",
            detail: detail.to_owned(),
        }
    }

    fn invalid(detail: &str) -> Self {
        Self {
            reason: "invalid_request",
            detail: detail.to_owned(),
        }
    }
}

/// `openai_request.openai_sampling`: the length and temperature fields an
/// OpenAI-compatible chat request carries. OpenAI's own API takes
/// `max_completion_tokens`, refuses a temperature for its reasoning families,
/// and its reasoning models are asked not to reason where they can stop, or for
/// their lowest level with room for it. Other servers keep `max_tokens` and the
/// temperature; MLX turns thinking off in the chat template (Gemma 4 with its
/// model card's sampling), NIM's Gemma 4 has thinking turned off in its chat
/// template, and Ollama is asked for no thinking, or gpt-oss for its lowest.
fn openai_sampling(
    connection: &Connection,
    model: &str,
    max_tokens: i64,
    temperature: &Value,
) -> Vec<(String, Value)> {
    let mut fields: Vec<(String, Value)> = Vec::new();
    if !connection.is_openai_api() {
        set(&mut fields, "max_tokens", integer(max_tokens));
        set(&mut fields, "temperature", temperature.clone());
        if connection.api_profile == "mlx" {
            set(&mut fields, "enable_thinking", Value::Bool(false));
            if gemma4(model) {
                set(&mut fields, "temperature", float(1.0));
                set(&mut fields, "top_p", float(0.95));
                set(&mut fields, "top_k", integer(64));
            }
        }
        if connection.id == "nvidia" && gemma4(model) {
            set(
                &mut fields,
                "chat_template_kwargs",
                object(vec![("enable_thinking", Value::Bool(false))]),
            );
        }
        if connection.id == "ollama" || connection.id == "ollama-cloud" {
            if ollama_levels_only(model) {
                set(
                    &mut fields,
                    "max_tokens",
                    integer(max_tokens + OLLAMA_THINKING_ROOM_TOKENS),
                );
                set(&mut fields, "reasoning_effort", string("low"));
            } else {
                set(&mut fields, "reasoning_effort", string("none"));
            }
        }
        return fields;
    }
    set(&mut fields, "max_completion_tokens", integer(max_tokens));
    if !openai_reasoning(model) {
        set(&mut fields, "temperature", temperature.clone());
    } else if openai_reasoning_can_stop(model) {
        set(&mut fields, "reasoning_effort", string("none"));
    } else {
        set(
            &mut fields,
            "max_completion_tokens",
            integer(max_tokens + OPENAI_REASONING_ROOM_TOKENS),
        );
        set(&mut fields, "reasoning_effort", string("low"));
    }
    fields
}

fn gemini_generation_config(model: &str, answer_tokens: i64) -> Value {
    let mut config = vec![(
        "maxOutputTokens".to_owned(),
        integer(gemini_max_output_tokens(model, answer_tokens)),
    )];
    if let Some(level) = gemini_level(model) {
        config.push((
            "thinkingConfig".to_owned(),
            object(vec![("thinkingLevel", string(level))]),
        ));
    }
    Value::Object(config)
}

/// A built request: where it goes, the headers that carry no secret, where the
/// key goes, and the body.
struct Built {
    url: String,
    headers: Vec<(&'static str, &'static str)>,
    /// The header the key is sent under, the text before it, and what is sent
    /// in its place when there is no key.
    auth: (&'static str, &'static str, &'static str),
    format: &'static str,
    body: Value,
}

impl Built {
    /// The answer budget the body asks for, as Server logged it.
    fn output_budget(&self) -> Value {
        if self.format == "gemini" {
            return get(&self.body, "generationConfig")
                .and_then(|config| get(config, "maxOutputTokens"))
                .cloned()
                .unwrap_or(Value::Null);
        }
        ["max_tokens", "max_completion_tokens", "max_output_tokens"]
            .iter()
            .find_map(|name| get(&self.body, name))
            .cloned()
            .unwrap_or(Value::Null)
    }

    fn answer(self, count_tokens: bool, model: &str) -> Value {
        let mut members = vec![
            ("url", string(&self.url)),
            (
                "headers",
                Value::Object(
                    self.headers
                        .iter()
                        .map(|(name, item)| ((*name).to_owned(), string(item)))
                        .collect(),
                ),
            ),
            (
                "auth",
                object(vec![
                    ("header", string(self.auth.0)),
                    ("prefix", string(self.auth.1)),
                    ("missing", string(self.auth.2)),
                ]),
            ),
            ("format", string(self.format)),
            ("output_budget", self.output_budget()),
        ];
        if count_tokens && self.format == "gemini" {
            // Gemini's countTokens counts the exact system, content and function
            // schema the request will carry.
            let mut request = vec![("model".to_owned(), string(&format!("models/{model}")))];
            if let Value::Object(body) = &self.body {
                for (name, item) in body {
                    set(&mut request, name, item.clone());
                }
            }
            let url = self
                .url
                .strip_suffix(":generateContent")
                .unwrap_or(&self.url)
                .to_owned()
                + ":countTokens";
            members.push((
                "count_tokens",
                object(vec![
                    ("url", string(&url)),
                    (
                        "body",
                        string(&dumps(&object(vec![(
                            "generateContentRequest",
                            Value::Object(request),
                        )]))),
                    ),
                ]),
            ));
        }
        members.push(("body", string(&dumps(&self.body))));
        object(members)
    }
}

fn bearer() -> (&'static str, &'static str, &'static str) {
    ("Authorization", "Bearer ", "none")
}

/// The images a pipeline request carries: the `data:` URLs the host sends,
/// each the image the prompt names in its place by type, length and SHA-256
/// (the image stages, 2026-10-24). A prompt without images takes none.
fn prompt_images(request: &Value, prompt: &Value) -> Result<Vec<String>, Refusal> {
    let sent = match get(request, "images") {
        None => Vec::new(),
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| as_str(Some(item)).map(str::to_owned))
            .collect::<Option<_>>()
            .ok_or_else(|| Refusal::invalid("images must be strings"))?,
        Some(_) => return Err(Refusal::invalid("images must be a list")),
    };
    let named: &[Value] = match get(prompt, "images") {
        None => &[],
        Some(Value::Array(items)) => items,
        Some(_) => return Err(Refusal::invalid("prompt.images must be a list")),
    };
    if sent.len() != named.len() {
        return Err(Refusal::invalid("images do not match the prompt"));
    }
    for (url, image) in sent.iter().zip(named) {
        let (media, data) = image_parts(url)?;
        let bytes = chatgpt::base64_decode(&data)
            .ok_or_else(|| Refusal::invalid("images must be base64"))?;
        let length = match get(image, "byte_len") {
            Some(Value::Integer(digits)) => digits.parse::<usize>().ok(),
            _ => None,
        };
        use sha2::{Digest, Sha256};
        let digest: String = Sha256::digest(&bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        if as_str(get(image, "media_type")) != Some(media.as_str())
            || length != Some(bytes.len())
            || as_str(get(image, "sha256")) != Some(digest.as_str())
        {
            return Err(Refusal::invalid("images do not match the prompt"));
        }
    }
    Ok(sent)
}

/// OpenAI Responses parts: the text, then each image.
fn responses_parts(text: &str, images: &[String]) -> Value {
    let mut parts = vec![object(vec![
        ("type", string("input_text")),
        ("text", string(text)),
    ])];
    parts.extend(images.iter().map(|image| {
        object(vec![
            ("type", string("input_image")),
            ("image_url", string(image)),
        ])
    }));
    Value::Array(parts)
}

/// OpenAI-compatible chat parts: the text, then each image.
fn chat_parts(text: &str, images: &[String]) -> Value {
    let mut parts = vec![object(vec![
        ("type", string("text")),
        ("text", string(text)),
    ])];
    parts.extend(images.iter().map(|image| {
        object(vec![
            ("type", string("image_url")),
            ("image_url", object(vec![("url", string(image))])),
        ])
    }));
    Value::Array(parts)
}

/// Anthropic blocks: each image, then the text.
fn anthropic_blocks(text: &str, images: &[String]) -> Result<Value, Refusal> {
    let mut blocks = Vec::with_capacity(images.len() + 1);
    for image in images {
        let (media, data) = image_parts(image)?;
        blocks.push(object(vec![
            ("type", string("image")),
            (
                "source",
                object(vec![
                    ("type", string("base64")),
                    ("media_type", string(&media)),
                    ("data", string(&data)),
                ]),
            ),
        ]));
    }
    blocks.push(object(vec![
        ("type", string("text")),
        ("text", string(text)),
    ]));
    Ok(Value::Array(blocks))
}

/// Gemini parts: the text, then each image inline.
fn gemini_parts(text: &str, images: &[String]) -> Result<Value, Refusal> {
    let mut parts = vec![object(vec![("text", string(text))])];
    for image in images {
        let (media, data) = image_parts(image)?;
        parts.push(object(vec![(
            "inlineData",
            object(vec![("mimeType", string(&media)), ("data", string(&data))]),
        )]));
    }
    Ok(Value::Array(parts))
}

/// `SingleAttemptProvider._request`'s body for one pipeline effect. The
/// images the prompt names follow its message in each dialect's Vision parts;
/// a request without images is written as it was.
fn pipeline_request(
    connection: &Connection,
    model: &str,
    prompt: &Value,
    max_tokens: i64,
    images: &[String],
) -> Result<Built, Refusal> {
    let field = |name: &str| {
        as_str(get(prompt, name))
            .ok_or_else(|| Refusal::invalid(&format!("prompt.{name} must be a string")))
    };
    let system = field("system")?;
    let message = field("message")?;
    let action_name = field("action_name")?;
    let schema = get(prompt, "response_schema")
        .ok_or_else(|| Refusal::invalid("prompt.response_schema is required"))?;
    let temperature = float(if STAGE1_SAMPLED_ACTIONS.contains(&action_name) {
        0.3
    } else {
        0.0
    });
    let base = connection.base();
    let user = |parts: Value| {
        let content = if images.is_empty() {
            string(message)
        } else {
            parts
        };
        object(vec![("role", string("user")), ("content", content)])
    };
    match connection.kind.as_str() {
        // OpenAI's own API draws through Responses, the only route that takes
        // function tools from every current model; the request is not stored.
        "openai_compatible" if connection.is_openai_api() => {
            let sampling = openai_sampling(connection, model, max_tokens, &temperature);
            let find = |name: &str| {
                sampling
                    .iter()
                    .find(|(key, _)| key == name)
                    .map(|(_, item)| item.clone())
            };
            let mut body = vec![
                ("model".to_owned(), string(model)),
                ("store".to_owned(), Value::Bool(false)),
                ("instructions".to_owned(), string(system)),
                (
                    "input".to_owned(),
                    Value::Array(vec![user(responses_parts(message, images))]),
                ),
                (
                    "tools".to_owned(),
                    Value::Array(vec![object(vec![
                        ("type", string("function")),
                        ("name", string(RESPONSE_NAME)),
                        ("description", string(TOOL_DESCRIPTION)),
                        ("parameters", ordered_schema(schema, false)),
                        ("strict", Value::Bool(false)),
                    ])]),
                ),
                ("tool_choice".to_owned(), string("required")),
                ("parallel_tool_calls".to_owned(), Value::Bool(false)),
                (
                    "max_output_tokens".to_owned(),
                    find("max_completion_tokens").unwrap_or(Value::Null),
                ),
            ];
            if let Some(temperature) = find("temperature") {
                body.push(("temperature".to_owned(), temperature));
            }
            if let Some(effort) = find("reasoning_effort") {
                body.push(("reasoning".to_owned(), object(vec![("effort", effort)])));
            }
            Ok(Built {
                url: format!("{base}/responses"),
                headers: vec![("Content-Type", "application/json")],
                auth: bearer(),
                format: "openai_responses",
                body: Value::Object(body),
            })
        }
        "openai_compatible" => {
            let mut body = vec![
                ("model".to_owned(), string(model)),
                ("stream".to_owned(), Value::Bool(false)),
            ];
            for (name, item) in openai_sampling(connection, model, max_tokens, &temperature) {
                set(&mut body, &name, item);
            }
            set(
                &mut body,
                "messages",
                Value::Array(vec![
                    object(vec![
                        ("role", string("system")),
                        ("content", string(system)),
                    ]),
                    user(chat_parts(message, images)),
                ]),
            );
            // Ollama and MLX take the schema as grammar-constrained JSON output:
            // Gemma 4 on mlx-vlm loops on thought-channel markers when given the
            // forced function tool (2026-10-02).
            if connection.id == "ollama" || connection.api_profile == "mlx" {
                set(
                    &mut body,
                    "response_format",
                    object(vec![
                        ("type", string("json_schema")),
                        (
                            "json_schema",
                            object(vec![
                                ("name", string(RESPONSE_NAME)),
                                ("schema", ordered_schema(schema, false)),
                                ("strict", Value::Bool(true)),
                            ]),
                        ),
                    ]),
                );
            } else {
                set(
                    &mut body,
                    "tools",
                    Value::Array(vec![object(vec![
                        ("type", string("function")),
                        (
                            "function",
                            object(vec![
                                ("name", string(RESPONSE_NAME)),
                                ("description", string(TOOL_DESCRIPTION)),
                                ("parameters", ordered_schema(schema, false)),
                            ]),
                        ),
                    ])]),
                );
                set(
                    &mut body,
                    "tool_choice",
                    object(vec![
                        ("type", string("function")),
                        ("function", object(vec![("name", string(RESPONSE_NAME))])),
                    ]),
                );
            }
            Ok(Built {
                url: format!("{base}/chat/completions"),
                headers: vec![("Content-Type", "application/json")],
                auth: bearer(),
                format: "openai_chat",
                body: Value::Object(body),
            })
        }
        "anthropic" => Ok(Built {
            url: format!("{base}/v1/messages"),
            headers: vec![
                ("Content-Type", "application/json"),
                ("anthropic-version", "2023-06-01"),
            ],
            auth: ("x-api-key", "", ""),
            format: "anthropic",
            body: object(vec![
                ("model", string(model)),
                (
                    "max_tokens",
                    integer(anthropic_max_tokens(model, max_tokens)),
                ),
                ("system", anthropic_system(system, action_name)),
                (
                    "messages",
                    Value::Array(vec![user(anthropic_blocks(message, images)?)]),
                ),
                (
                    "tools",
                    Value::Array(vec![object(vec![
                        ("name", string(RESPONSE_NAME)),
                        ("description", string(TOOL_DESCRIPTION)),
                        ("input_schema", ordered_schema(schema, false)),
                    ])]),
                ),
                // Left to the model: claude-opus-5-5 refuses a forced tool
                // (Pentala 2026-09-28). An answer given as text is read too.
                ("tool_choice", object(vec![("type", string("auto"))])),
            ]),
        }),
        "gemini" => Ok(Built {
            url: format!(
                "{base}/v1beta/models/{}:generateContent",
                quote_segment(model)
            ),
            headers: vec![("Content-Type", "application/json")],
            auth: ("x-goog-api-key", "", ""),
            format: "gemini",
            body: object(vec![
                (
                    "systemInstruction",
                    object(vec![(
                        "parts",
                        Value::Array(vec![object(vec![("text", string(system))])]),
                    )]),
                ),
                (
                    "contents",
                    Value::Array(vec![object(vec![
                        ("role", string("user")),
                        ("parts", gemini_parts(message, images)?),
                    ])]),
                ),
                (
                    "generationConfig",
                    gemini_generation_config(model, max_tokens),
                ),
                (
                    "tools",
                    Value::Array(vec![object(vec![(
                        "functionDeclarations",
                        Value::Array(vec![object(vec![
                            ("name", string(RESPONSE_NAME)),
                            ("description", string(TOOL_DESCRIPTION)),
                            (
                                "parametersJsonSchema",
                                gemini_schema(schema, action_name == "complete_visible_ddl_holes")?,
                            ),
                        ])]),
                    )])]),
                ),
                (
                    "toolConfig",
                    object(vec![(
                        "functionCallingConfig",
                        object(vec![
                            ("mode", string("ANY")),
                            (
                                "allowedFunctionNames",
                                Value::Array(vec![string(RESPONSE_NAME)]),
                            ),
                        ]),
                    )]),
                ),
            ]),
        }),
        _ => Err(Refusal::rejected("unsupported provider kind")),
    }
}

/// `vision_client._image_parts`: (media type, base64 data) of a `data:` URL.
fn image_parts(image: &str) -> Result<(String, String), Refusal> {
    let (head, data) = image.split_once(',').unwrap_or((image, ""));
    if !head.starts_with("data:") || !head.contains(";base64") || data.is_empty() {
        return Err(Refusal::rejected("Vision images must be base64 data URLs"));
    }
    let media = head["data:".len()..].split(';').next().unwrap_or("");
    Ok((
        if media.is_empty() { "image/png" } else { media }.to_owned(),
        data.to_owned(),
    ))
}

/// One text answer, with images when there are any: the colophon and the
/// Vision advice (`vision_client._request`), and the demo instruction. The
/// user's text is one string when no image goes with it, as the demo sent it.
fn text_request(
    connection: &Connection,
    model: &str,
    system: &str,
    text: &str,
    images: &[String],
    temperature: &Value,
    max_tokens: i64,
) -> Result<Built, Refusal> {
    let base = connection.base();
    match connection.kind.as_str() {
        "openai_compatible" => {
            let content = if images.is_empty() {
                string(text)
            } else {
                chat_parts(text, images)
            };
            let mut body = vec![
                ("model".to_owned(), string(model)),
                ("stream".to_owned(), Value::Bool(false)),
            ];
            for (name, item) in openai_sampling(connection, model, max_tokens, temperature) {
                set(&mut body, &name, item);
            }
            set(
                &mut body,
                "messages",
                Value::Array(vec![
                    object(vec![
                        ("role", string("system")),
                        ("content", string(system)),
                    ]),
                    object(vec![("role", string("user")), ("content", content)]),
                ]),
            );
            Ok(Built {
                url: format!("{base}/chat/completions"),
                headers: vec![("Content-Type", "application/json")],
                auth: bearer(),
                format: "openai_chat",
                body: Value::Object(body),
            })
        }
        // No temperature, as the pipeline sends Anthropic: claude-sonnet-5
        // refused the colophon with a 400 while one was sent (2026-09-28).
        "anthropic" => {
            let content = if images.is_empty() {
                string(text)
            } else {
                anthropic_blocks(text, images)?
            };
            Ok(Built {
                url: format!("{base}/v1/messages"),
                headers: vec![
                    ("Content-Type", "application/json"),
                    ("anthropic-version", "2023-06-01"),
                ],
                auth: ("x-api-key", "", ""),
                format: "anthropic",
                body: object(vec![
                    ("model", string(model)),
                    (
                        "max_tokens",
                        integer(anthropic_max_tokens(model, max_tokens)),
                    ),
                    ("system", string(system)),
                    (
                        "messages",
                        Value::Array(vec![object(vec![
                            ("role", string("user")),
                            ("content", content),
                        ])]),
                    ),
                ]),
            })
        }
        // The lowest thinking level and no temperature: Gemini 3 is tuned for
        // its default of 1.0 and below it can loop (Gemini 3 developer guide).
        "gemini" => {
            let parts = gemini_parts(text, images)?;
            Ok(Built {
                url: format!(
                    "{base}/v1beta/models/{}:generateContent",
                    quote_segment(model)
                ),
                headers: vec![("Content-Type", "application/json")],
                auth: ("x-goog-api-key", "", ""),
                format: "gemini",
                body: object(vec![
                    (
                        "systemInstruction",
                        object(vec![(
                            "parts",
                            Value::Array(vec![object(vec![("text", string(system))])]),
                        )]),
                    ),
                    (
                        "contents",
                        Value::Array(vec![object(vec![
                            ("role", string("user")),
                            ("parts", parts),
                        ])]),
                    ),
                    (
                        "generationConfig",
                        gemini_generation_config(model, max_tokens),
                    ),
                ]),
            })
        }
        other => Err(Refusal::rejected(&format!(
            "unsupported provider kind for Vision: {other}"
        ))),
    }
}

// ---------------------------------------------------------------------------
// Responses.

/// Keys shaped like a provider key: `\b(?:sk|key|AIza)[-_A-Za-z0-9*]{6,}`.
fn mask_key_like(message: &str) -> String {
    let characters: Vec<char> = message.chars().collect();
    let word = |c: char| c.is_alphanumeric() || c == '_';
    let tail = |c: char| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '*';
    let mut out = String::with_capacity(message.len());
    let mut at = 0;
    while at < characters.len() {
        let boundary = word(characters[at]) && (at == 0 || !word(characters[at - 1]));
        let matched = boundary
            .then(|| {
                ["sk", "key", "AIza"].iter().find_map(|prefix| {
                    let prefix: Vec<char> = prefix.chars().collect();
                    if !characters[at..].starts_with(&prefix) {
                        return None;
                    }
                    let start = at + prefix.len();
                    let run = characters[start..].iter().take_while(|c| tail(**c)).count();
                    (run >= 6).then_some(start + run)
                })
            })
            .flatten();
        if let Some(end) = matched {
            out.push_str("***");
            at = end;
        } else {
            out.push(characters[at]);
            at += 1;
        }
    }
    out
}

/// `provider_refusal.provider_error`: what a refusal says, without anything
/// that could carry a key. OpenAI, Anthropic and Gemini all answer
/// `{"error": {...}}`; a 401 echoes part of the key in its message.
fn provider_error(body: &str) -> Value {
    let bytes = body.as_bytes();
    let read = &bytes[..bytes.len().min(REFUSAL_READ_BYTES)];
    let Ok(text) = std::str::from_utf8(read) else {
        return Value::Object(Vec::new());
    };
    let Ok(document) = python_loads(text) else {
        return Value::Object(Vec::new());
    };
    let Some(Value::Object(error)) = get(&document, "error") else {
        return Value::Object(Vec::new());
    };
    let error = Value::Object(error.clone());
    let mut found = Vec::new();
    for name in ["code", "type", "param", "status"] {
        match get(&error, name) {
            Some(Value::String(text)) if !text.is_empty() => {
                found.push((name.to_owned(), string(text)))
            }
            Some(item @ (Value::Integer(_) | Value::Bool(_))) => {
                found.push((name.to_owned(), item.clone()))
            }
            _ => {}
        }
    }
    if let Some(message) = as_str(get(&error, "message")).filter(|text| !text.is_empty()) {
        let masked: String = mask_key_like(message).chars().take(240).collect();
        found.push(("message".to_owned(), Value::String(masked)));
    }
    Value::Object(found)
}

fn http_failure(status: i64) -> &'static str {
    if status == 429 {
        "rate_limited"
    } else if status >= 500 {
        "transport_unavailable"
    } else {
        "provider_rejected"
    }
}

fn blocks_of(value: Option<&Value>) -> Vec<&Value> {
    as_array(value)
        .map(|items| {
            items
                .iter()
                .filter(|item| matches!(item, Value::Object(_)))
                .collect()
        })
        .unwrap_or_default()
}

fn first_object(value: Option<&Value>) -> &Value {
    static EMPTY: Value = Value::Object(Vec::new());
    as_array(value)
        .and_then(|items| items.first())
        .filter(|item| matches!(item, Value::Object(_)))
        .unwrap_or(&EMPTY)
}

fn object_or_empty(value: Option<&Value>) -> &Value {
    static EMPTY: Value = Value::Object(Vec::new());
    value
        .filter(|item| matches!(item, Value::Object(_)))
        .unwrap_or(&EMPTY)
}

fn number_or_null(value: Option<&Value>) -> Value {
    value.cloned().unwrap_or(Value::Null)
}

fn type_is(block: &Value, kind: &str) -> bool {
    as_str(get(block, "type")) == Some(kind)
}

/// What an answer cut off at its output limit spent its budget on; `None` when
/// it was not cut off (`*_output_limit_record` in Server).
fn output_limit_record(format: &str, data: &Value) -> Option<Value> {
    match format {
        "anthropic" => {
            if as_str(get(data, "stop_reason")) != Some("max_tokens") {
                return None;
            }
            let usage = object_or_empty(get(data, "usage"));
            let blocks = blocks_of(get(data, "content"));
            Some(object(vec![
                ("stop_reason", string("max_tokens")),
                ("output_tokens", number_or_null(get(usage, "output_tokens"))),
                (
                    "thinking_blocks",
                    integer(
                        blocks
                            .iter()
                            .filter(|block| {
                                type_is(block, "thinking") || type_is(block, "redacted_thinking")
                            })
                            .count() as i64,
                    ),
                ),
                (
                    "has_text",
                    Value::Bool(
                        blocks
                            .iter()
                            .any(|block| type_is(block, "text") && truthy(get(block, "text"))),
                    ),
                ),
                (
                    "has_tool_use",
                    Value::Bool(blocks.iter().any(|block| type_is(block, "tool_use"))),
                ),
            ]))
        }
        "gemini" => {
            let first = first_object(get(data, "candidates"));
            if as_str(get(first, "finishReason")) != Some("MAX_TOKENS") {
                return None;
            }
            let usage = object_or_empty(get(data, "usageMetadata"));
            let content = object_or_empty(get(first, "content"));
            let parts = blocks_of(get(content, "parts"));
            Some(object(vec![
                ("finish_reason", string("MAX_TOKENS")),
                (
                    "output_tokens",
                    number_or_null(get(usage, "candidatesTokenCount")),
                ),
                (
                    "thought_tokens",
                    number_or_null(get(usage, "thoughtsTokenCount")),
                ),
                (
                    "has_text",
                    Value::Bool(
                        parts
                            .iter()
                            .any(|part| truthy(get(part, "text")) && !truthy(get(part, "thought"))),
                    ),
                ),
                (
                    "has_function_call",
                    Value::Bool(parts.iter().any(|part| get(part, "functionCall").is_some())),
                ),
            ]))
        }
        "openai_responses" => {
            let details = object_or_empty(get(data, "incomplete_details"));
            if as_str(get(data, "status")) != Some("incomplete")
                || as_str(get(details, "reason")) != Some("max_output_tokens")
            {
                return None;
            }
            let usage = object_or_empty(get(data, "usage"));
            let usage_details = object_or_empty(get(usage, "output_tokens_details"));
            let output = blocks_of(get(data, "output"));
            Some(object(vec![
                ("incomplete_reason", string("max_output_tokens")),
                ("output_tokens", number_or_null(get(usage, "output_tokens"))),
                (
                    "reasoning_tokens",
                    number_or_null(get(usage_details, "reasoning_tokens")),
                ),
                (
                    "has_text",
                    Value::Bool(output.iter().any(|item| type_is(item, "message"))),
                ),
                (
                    "has_function_call",
                    Value::Bool(output.iter().any(|item| type_is(item, "function_call"))),
                ),
            ]))
        }
        "openai_chat" => {
            let first = first_object(get(data, "choices"));
            if as_str(get(first, "finish_reason")) != Some("length") {
                return None;
            }
            let usage = object_or_empty(get(data, "usage"));
            let details = object_or_empty(get(usage, "completion_tokens_details"));
            let message = object_or_empty(get(first, "message"));
            Some(object(vec![
                ("finish_reason", string("length")),
                (
                    "output_tokens",
                    number_or_null(get(usage, "completion_tokens")),
                ),
                (
                    "reasoning_tokens",
                    number_or_null(get(details, "reasoning_tokens")),
                ),
                (
                    "has_reasoning",
                    Value::Bool(
                        truthy(get(message, "reasoning"))
                            || truthy(get(message, "reasoning_content")),
                    ),
                ),
                ("has_text", Value::Bool(truthy(get(message, "content")))),
                (
                    "has_tool_call",
                    Value::Bool(truthy(get(message, "tool_calls"))),
                ),
            ]))
        }
        _ => None,
    }
}

/// The prompt tokens a response reports, as the rate budget settles them.
fn input_tokens(format: &str, data: &Value) -> Option<Value> {
    let (usage, name) = match format {
        "gemini" => ("usageMetadata", "promptTokenCount"),
        "anthropic" | "openai_responses" => ("usage", "input_tokens"),
        _ => ("usage", "prompt_tokens"),
    };
    count(get(object_or_empty(get(data, usage)), name))
}

/// The tokens one send used, counted alike for every dialect so a work's total
/// means one thing: input is everything read, cache reads and writes included
/// (Claude's `input_tokens` leaves both out), and output is everything written,
/// thinking included (Gemini's `candidatesTokenCount` leaves thoughts out).
/// `None` when the response reports no usage; a count it leaves out is null.
fn usage(format: &str, data: &Value) -> Option<Value> {
    let number = |value: Option<&Value>| match count(value) {
        Some(Value::Integer(digits)) => digits.parse::<i64>().ok(),
        _ => None,
    };
    let sum = |base: Option<i64>, more: &[Option<i64>]| {
        base.map(|first| first + more.iter().flatten().sum::<i64>())
    };
    let source = object_or_empty(get(
        data,
        if format == "gemini" {
            "usageMetadata"
        } else {
            "usage"
        },
    ));
    let field = |name: &str| number(get(source, name));
    let detail =
        |details: &str, name: &str| number(get(object_or_empty(get(source, details)), name));
    let (input, output, cached) = match format {
        "anthropic" => {
            let cache_read = field("cache_read_input_tokens");
            (
                sum(
                    field("input_tokens"),
                    &[cache_read, field("cache_creation_input_tokens")],
                ),
                field("output_tokens"),
                cache_read,
            )
        }
        "openai_responses" => (
            field("input_tokens"),
            field("output_tokens"),
            detail("input_tokens_details", "cached_tokens"),
        ),
        "gemini" => {
            let written = match (field("candidatesTokenCount"), field("thoughtsTokenCount")) {
                (None, None) => None,
                (candidates, thoughts) => Some(candidates.unwrap_or(0) + thoughts.unwrap_or(0)),
            };
            (
                field("promptTokenCount"),
                written,
                field("cachedContentTokenCount"),
            )
        }
        _ => (
            field("prompt_tokens"),
            field("completion_tokens"),
            detail("prompt_tokens_details", "cached_tokens"),
        ),
    };
    if input.is_none() && output.is_none() {
        return None;
    }
    let or_null = |value: Option<i64>| value.map_or(Value::Null, integer);
    Some(object(vec![
        ("input_tokens", or_null(input)),
        ("output_tokens", or_null(output)),
        ("cached_input_tokens", or_null(cached)),
    ]))
}

/// The object an answer given as text carries, fenced or not.
fn json_object_in(text: &str) -> Option<Value> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end <= start {
        return None;
    }
    match python_loads(&text[start..=end]) {
        Ok(value @ Value::Object(_)) => Some(value),
        _ => None,
    }
}

/// The one tool call's arguments, or the text a model answered with instead.
/// `None` is a malformed answer.
fn pipeline_answer(format: &str, data: &Value) -> Option<String> {
    let text = match format {
        "openai_responses" => {
            if as_str(get(data, "status")) != Some("completed") {
                return None;
            }
            let output = blocks_of(Some(
                get(data, "output").filter(|item| matches!(item, Value::Array(_)))?,
            ));
            let calls: Vec<&&Value> = output
                .iter()
                .filter(|item| type_is(item, "function_call"))
                .collect();
            if !calls.is_empty() {
                if calls.len() != 1 || as_str(get(calls[0], "name")) != Some(RESPONSE_NAME) {
                    return None;
                }
                as_str(get(calls[0], "arguments"))?.to_owned()
            } else {
                let mut joined = String::new();
                for item in output.iter().filter(|item| type_is(item, "message")) {
                    for part in blocks_of(get(item, "content")) {
                        if type_is(part, "output_text") {
                            joined.push_str(&python_str(get(part, "text").unwrap_or(&string("")))?);
                        }
                    }
                }
                joined
            }
        }
        "openai_chat" => {
            let message = get(as_array(get(data, "choices"))?.first()?, "message")?;
            if !matches!(message, Value::Object(_)) {
                return None;
            }
            let calls = get(message, "tool_calls");
            if truthy(calls) {
                let calls = as_array(calls)?;
                let function = get(calls.first()?, "function")?;
                if calls.len() != 1 || as_str(get(function, "name")) != Some(RESPONSE_NAME) {
                    return None;
                }
                as_str(get(function, "arguments"))?.to_owned()
            } else {
                as_str(get(message, "content"))?.to_owned()
            }
        }
        "anthropic" => {
            let content = as_array(get(data, "content"))?;
            if content
                .iter()
                .any(|block| !matches!(block, Value::Object(_)))
            {
                return None;
            }
            let calls: Vec<&Value> = content
                .iter()
                .filter(|block| type_is(block, "tool_use"))
                .collect();
            let arguments = if !calls.is_empty() {
                if calls.len() != 1 || as_str(get(calls[0], "name")) != Some(RESPONSE_NAME) {
                    return None;
                }
                get(calls[0], "input")
                    .filter(|input| matches!(input, Value::Object(_)))?
                    .clone()
            } else {
                let mut texts = Vec::new();
                for block in content.iter().filter(|block| type_is(block, "text")) {
                    texts.push(python_str(get(block, "text").unwrap_or(&string("")))?);
                }
                json_object_in(&texts.join("\n"))?
            };
            dumps(&arguments)
        }
        "gemini" => {
            let parts = as_array(get(
                get(as_array(get(data, "candidates"))?.first()?, "content")?,
                "parts",
            ))?;
            let mut calls = Vec::new();
            // `"functionCall" in part`: a text part is searched, a list is
            // looked through, and anything else cannot be asked.
            for part in parts {
                match part {
                    Value::Object(_) => {
                        if let Some(call) = get(part, "functionCall") {
                            calls.push(call);
                        }
                    }
                    Value::String(text) if !text.contains("functionCall") => {}
                    Value::Array(items)
                        if !items
                            .iter()
                            .any(|item| as_str(Some(item)) == Some("functionCall")) => {}
                    _ => return None,
                }
            }
            if calls.len() != 1 || as_str(get(calls[0], "name")) != Some(RESPONSE_NAME) {
                return None;
            }
            dumps(get(calls[0], "args").filter(|args| matches!(args, Value::Object(_)))?)
        }
        _ => return None,
    };
    (!text.is_empty()).then_some(text)
}

/// `vision_client._answer`: the answer's text, stripped. `None` is a malformed
/// answer.
fn text_answer(format: &str, data: &Value) -> Option<String> {
    let text = match format {
        "openai_chat" => {
            let message = get(as_array(get(data, "choices"))?.first()?, "message")?;
            let content = get(message, "content");
            if truthy(content) {
                python_str(content?)?
            } else {
                String::new()
            }
        }
        "anthropic" => {
            let mut texts = Vec::new();
            let blocks = match get(data, "content") {
                None => &[][..],
                Some(Value::Array(items)) => items.as_slice(),
                Some(Value::String(text)) if text.is_empty() => &[][..],
                Some(Value::Object(members)) if members.is_empty() => &[][..],
                Some(_) => return None,
            };
            for block in blocks {
                if !matches!(block, Value::Object(_)) {
                    return None;
                }
                if type_is(block, "text") {
                    texts.push(python_str(get(block, "text").unwrap_or(&string("")))?);
                }
            }
            texts.join("\n")
        }
        "gemini" => {
            let empty = Value::Object(Vec::new());
            let candidates = get(data, "candidates");
            let first = match candidates {
                None => &empty,
                Some(Value::Array(items)) => items.first()?,
                Some(_) => return None,
            };
            if !matches!(first, Value::Object(_)) {
                return None;
            }
            let content = get(first, "content").unwrap_or(&empty);
            if !matches!(content, Value::Object(_)) {
                return None;
            }
            let parts = match get(content, "parts") {
                None => &[][..],
                Some(Value::Array(items)) => items.as_slice(),
                Some(_) => return None,
            };
            let mut texts = Vec::new();
            for part in parts {
                if !matches!(part, Value::Object(_)) {
                    return None;
                }
                if let Some(text) = get(part, "text")
                    && !truthy(get(part, "thought"))
                {
                    texts.push(python_str(text)?);
                }
            }
            texts.join("\n")
        }
        _ => return None,
    };
    Some(python_strip(&text).to_owned())
}

/// The answer to a response: an HTTP failure, a malformed body, a cut-off
/// answer, or the answer's text.
fn read_response(format: &str, status: i64, body: &str, text: bool) -> Value {
    // httpx's raise_for_status refuses every status outside 2xx; only a 4xx or
    // 5xx body was read for the reason.
    if !(200..300).contains(&status) {
        let refusal = if status >= 400 {
            provider_error(body)
        } else {
            Value::Object(Vec::new())
        };
        return object(vec![
            ("outcome", string("http_error")),
            ("failure", string(http_failure(status))),
            ("refusal", refusal),
        ]);
    }
    let malformed = |detail: &str| {
        object(vec![
            ("outcome", string("malformed")),
            ("detail", string(detail)),
        ])
    };
    let data = match python_loads(body) {
        Ok(data @ Value::Object(_)) => data,
        Ok(_) => return malformed("provider response is not an object"),
        Err(_) => return malformed("provider response is not JSON"),
    };
    let tokens = input_tokens(format, &data).unwrap_or(Value::Null);
    let cut = output_limit_record(format, &data);
    if text {
        // A cut colophon is still prose, and cut advice JSON fails where it is
        // parsed, so the text is returned with the record beside it.
        let Some(answer) = text_answer(format, &data) else {
            return malformed("provider returned an unexpected answer");
        };
        let mut members = vec![
            ("outcome", string("answer")),
            ("text", Value::String(answer)),
        ];
        if let Some(cut) = cut {
            members.push(("cut", cut));
        }
        return object(members);
    }
    // A response stopped at the output limit is cut off whatever it holds: a
    // tool input or JSON text that ends there is not the whole answer.
    if let Some(cut) = cut {
        return object(vec![
            ("outcome", string("cut")),
            ("cut", cut),
            ("input_tokens", tokens),
        ]);
    }
    match pipeline_answer(format, &data) {
        Some(answer) => object(vec![
            ("outcome", string("answer")),
            ("text", Value::String(answer)),
            ("input_tokens", tokens),
        ]),
        None => {
            let mut answer = malformed("provider returned an unexpected answer");
            if let Value::Object(members) = &mut answer {
                members.push(("input_tokens".to_owned(), tokens));
            }
            answer
        }
    }
}

// ---------------------------------------------------------------------------
// The binding.

fn connection_of(request: &Value) -> Result<Connection, Refusal> {
    let connection =
        get(request, "connection").ok_or_else(|| Refusal::invalid("connection is required"))?;
    let field = |name: &str| as_str(get(connection, name)).map(str::to_owned);
    Ok(Connection {
        id: field("id").ok_or_else(|| Refusal::invalid("connection.id must be a string"))?,
        kind: field("kind").ok_or_else(|| Refusal::invalid("connection.kind must be a string"))?,
        api_profile: field("api_profile").unwrap_or_default(),
        base_url: field("base_url")
            .ok_or_else(|| Refusal::invalid("connection.base_url must be a string"))?,
    })
}

fn tokens_of(request: &Value, name: &str) -> Result<i64, Refusal> {
    match get(request, name) {
        Some(Value::Integer(digits)) => digits
            .parse::<i64>()
            .ok()
            .filter(|tokens| *tokens > 0 && *tokens < i64::MAX / 2)
            .ok_or_else(|| Refusal::invalid("max_tokens must be a positive integer")),
        _ => Err(Refusal::invalid("max_tokens must be a positive integer")),
    }
}

/// A positive byte count the host reads an answer up to.
fn limit_of(request: &Value) -> Result<usize, Refusal> {
    match get(request, "answer_limit") {
        Some(Value::Integer(digits)) => digits
            .parse::<usize>()
            .ok()
            .filter(|limit| *limit > 0 && *limit < usize::MAX / 8)
            .ok_or_else(|| Refusal::invalid("answer_limit must be a positive integer")),
        _ => Err(Refusal::invalid("answer_limit must be a positive integer")),
    }
}

fn answer(request: &Value) -> Result<Value, Refusal> {
    let action = as_str(get(request, "action"))
        .ok_or_else(|| Refusal::invalid("action must be a string"))?;
    let model =
        || as_str(get(request, "model")).ok_or_else(|| Refusal::invalid("model must be a string"));
    match action {
        "pipeline_request" => {
            let connection = connection_of(request)?;
            let model = model()?;
            let prompt = get(request, "prompt")
                .filter(|prompt| matches!(prompt, Value::Object(_)))
                .ok_or_else(|| Refusal::invalid("prompt must be an object"))?;
            let built = pipeline_request(
                &connection,
                model,
                prompt,
                tokens_of(request, "max_tokens")?,
                &prompt_images(request, prompt)?,
            )?;
            Ok(built.answer(true, model))
        }
        "text_request" => {
            let connection = connection_of(request)?;
            let model = model()?;
            let field = |name: &str| {
                as_str(get(request, name))
                    .ok_or_else(|| Refusal::invalid(&format!("{name} must be a string")))
            };
            let images = match get(request, "images") {
                None => Vec::new(),
                Some(Value::Array(items)) => items
                    .iter()
                    .map(|item| as_str(Some(item)).map(str::to_owned))
                    .collect::<Option<_>>()
                    .ok_or_else(|| Refusal::invalid("images must be strings"))?,
                Some(_) => return Err(Refusal::invalid("images must be a list")),
            };
            let temperature = get(request, "temperature")
                .filter(|item| matches!(item, Value::Integer(_) | Value::Float(_)))
                .ok_or_else(|| Refusal::invalid("temperature must be a number"))?;
            let built = text_request(
                &connection,
                model,
                field("system")?,
                field("text")?,
                &images,
                temperature,
                tokens_of(request, "max_tokens")?,
            )?;
            Ok(built.answer(false, model))
        }
        "pipeline_response" | "text_response" => {
            let format = as_str(get(request, "format"))
                .filter(|format| {
                    ["openai_responses", "openai_chat", "anthropic", "gemini"].contains(format)
                })
                .ok_or_else(|| Refusal::invalid("format is unknown"))?;
            let status = match get(request, "status") {
                Some(Value::Integer(digits)) => digits
                    .parse::<i64>()
                    .map_err(|_| Refusal::invalid("status must be an integer"))?,
                _ => return Err(Refusal::invalid("status must be an integer")),
            };
            let body = as_str(get(request, "body"))
                .ok_or_else(|| Refusal::invalid("body must be a string"))?;
            Ok(read_response(
                format,
                status,
                body,
                action == "text_response",
            ))
        }
        "usage" => {
            // The ChatGPT plan's terminal response is read as `openai_responses`.
            let format = as_str(get(request, "format"))
                .filter(|format| {
                    ["openai_responses", "openai_chat", "anthropic", "gemini"].contains(format)
                })
                .ok_or_else(|| Refusal::invalid("format is unknown"))?;
            let body = as_str(get(request, "body"))
                .ok_or_else(|| Refusal::invalid("body must be a string"))?;
            let read = match python_loads(body) {
                Ok(data @ Value::Object(_)) => usage(format, &data),
                _ => None,
            };
            Ok(object(vec![("usage", read.unwrap_or(Value::Null))]))
        }
        "chatgpt_request" => {
            let model = model()?;
            let prompt = get(request, "prompt")
                .filter(|prompt| matches!(prompt, Value::Object(_)))
                .ok_or_else(|| Refusal::invalid("prompt must be an object"))?;
            chatgpt::pipeline_request(
                model,
                prompt,
                limit_of(request)?,
                &prompt_images(request, prompt)?,
            )
        }
        "chatgpt_vision_request" => {
            let model = model()?;
            let field = |name: &str| {
                as_str(get(request, name))
                    .ok_or_else(|| Refusal::invalid(&format!("{name} must be a string")))
            };
            let images = as_array(get(request, "images"))
                .ok_or_else(|| Refusal::invalid("images must be a list"))?
                .iter()
                .map(|item| as_str(Some(item)).map(str::to_owned))
                .collect::<Option<Vec<_>>>()
                .ok_or_else(|| Refusal::invalid("images must be strings"))?;
            chatgpt::vision_request(
                model,
                field("system")?,
                field("text")?,
                &images,
                limit_of(request)?,
            )
        }
        "chatgpt_limits" => Ok(chatgpt::limits_answer(limit_of(request)?)),
        "chatgpt_stream" => {
            let text = match as_str(get(request, "mode")) {
                Some("pipeline") => false,
                Some("text") => true,
                _ => return Err(Refusal::invalid("mode must be pipeline or text")),
            };
            let wire = as_str(get(request, "wire_base64"))
                .and_then(chatgpt::base64_decode)
                .ok_or_else(|| Refusal::invalid("wire_base64 must be base64"))?;
            Ok(chatgpt::stream_answer(text, limit_of(request)?, &wire))
        }
        "chatgpt_error" => {
            let status = match get(request, "status") {
                None | Some(Value::Null) => None,
                Some(Value::Integer(digits)) => Some(
                    digits
                        .parse::<i64>()
                        .map_err(|_| Refusal::invalid("status must be an integer"))?,
                ),
                Some(_) => return Err(Refusal::invalid("status must be an integer")),
            };
            let empty = Value::Null;
            Ok(chatgpt::error_answer(
                get(request, "value").unwrap_or(&empty),
                status,
                get(request, "request_id"),
            ))
        }
        "chatgpt_failure" => {
            let code = as_str(get(request, "code"))
                .ok_or_else(|| Refusal::invalid("code must be a string"))?;
            let temporary = match get(request, "temporary") {
                None | Some(Value::Null) => None,
                Some(Value::Bool(flag)) => Some(*flag),
                Some(_) => return Err(Refusal::invalid("temporary must be a boolean")),
            };
            Ok(chatgpt::failure_answer(code, temporary))
        }
        "chatgpt_catalog" => {
            let empty = Value::Null;
            Ok(chatgpt::catalog_answer(
                get(request, "value").unwrap_or(&empty),
            ))
        }
        _ => Err(Refusal::invalid("action is unknown")),
    }
}

/// JSON in, JSON out, for the hosts' bindings. A request answers
/// `{"schema", "outcome": "ok", "url", "headers", "auth", "format",
/// "output_budget", "body"}`; a response answers `{"schema", "outcome":
/// "answer" | "cut" | "malformed" | "http_error", ...}`; a response's `usage`
/// answers `{"schema", "outcome": "ok", "usage"}`; a request that cannot be
/// built answers `{"schema", "outcome": "refused", "reason", "detail"}`.
#[must_use]
pub fn provider_wire_json(input: &[u8]) -> Vec<u8> {
    let parsed = std::str::from_utf8(input)
        .ok()
        .and_then(|text| python_loads(text).ok());
    let answered = match parsed {
        Some(request @ Value::Object(_)) => answer(&request),
        _ => Err(Refusal::invalid("the request is not a JSON object")),
    };
    let mut members = vec![("schema".to_owned(), string(PROVIDER_WIRE_SCHEMA_ID))];
    match answered {
        Ok(Value::Object(fields)) => {
            if !fields.iter().any(|(name, _)| name == "outcome") {
                members.push(("outcome".to_owned(), string("ok")));
            }
            members.extend(fields);
        }
        Ok(_) => unreachable!("answers are objects"),
        Err(refusal) => {
            members.push(("outcome".to_owned(), string("refused")));
            members.push(("reason".to_owned(), string(refusal.reason)));
            members.push(("detail".to_owned(), Value::String(refusal.detail)));
        }
    }
    dumps(&Value::Object(members)).into_bytes()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cases() -> serde_json::Value {
        serde_json::from_str(include_str!(
            "../../../../server/tests/data/provider-wire-cases.json"
        ))
        .expect("provider wire cases")
    }

    fn ask(request: &serde_json::Value) -> serde_json::Value {
        let answer = provider_wire_json(&serde_json::to_vec(request).unwrap());
        serde_json::from_slice(&answer).expect("the answer is JSON")
    }

    /// The headers the host sends: the plain ones and the key under its header.
    fn sent_headers(answer: &serde_json::Value) -> BTreeMap<String, String> {
        let mut headers: BTreeMap<String, String> = answer["headers"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(name, item)| (name.to_ascii_lowercase(), item.as_str().unwrap().to_owned()))
            .collect();
        let auth = &answer["auth"];
        headers.insert(
            auth["header"].as_str().unwrap().to_ascii_lowercase(),
            format!("{}KEY", auth["prefix"].as_str().unwrap()),
        );
        headers
    }

    use std::collections::BTreeMap;

    fn check_requests(name: &str) -> usize {
        let cases = cases();
        let mut compared = 0;
        for case in cases[name].as_array().unwrap() {
            let (why, expect) = (&case["why"], &case["expect"]);
            let answer = ask(&case["request"]);
            assert_eq!(answer["schema"], PROVIDER_WIRE_SCHEMA_ID);
            assert_eq!(answer["outcome"], expect["outcome"], "{why}: {answer}");
            if expect["outcome"] == "refused" {
                assert_eq!(answer["reason"], expect["reason"], "{why}");
                assert_eq!(answer["detail"], expect["detail"], "{why}");
            } else {
                assert_eq!(answer["url"], expect["url"], "{why}");
                assert_eq!(answer["body"], expect["body"], "{why}");
                let expected: BTreeMap<String, String> =
                    serde_json::from_value(expect["headers"].clone()).unwrap();
                assert_eq!(sent_headers(&answer), expected, "{why}");
            }
            compared += 1;
        }
        compared
    }

    #[test]
    fn every_shared_pipeline_request_is_written_as_server_wrote_it() {
        // 246 rows as Server wrote them, and the laws and colors stages' two
        // Anthropic rows the core wrote when it marked their system text for
        // the cache (2026-10-25).
        assert_eq!(check_requests("requests"), 248);
    }

    #[test]
    fn every_shared_text_request_is_written_as_server_wrote_it() {
        assert_eq!(check_requests("text_requests"), 81);
    }

    #[test]
    fn every_shared_response_is_read_as_server_read_it() {
        let cases = cases();
        let mut compared = 0;
        for case in cases["responses"].as_array().unwrap() {
            let (why, expect) = (&case["why"], &case["expect"]);
            let answer = ask(&case["request"]);
            for (name, item) in expect.as_object().unwrap() {
                assert_eq!(&answer[name], item, "{why}: {name} in {answer}");
            }
            compared += 1;
        }
        assert_eq!(compared, 97);
    }

    #[test]
    fn every_shared_chatgpt_row_is_written_and_read_as_server_did() {
        let cases = cases();
        let mut compared = 0;
        for case in cases["chatgpt"].as_array().unwrap() {
            let (why, expect) = (&case["why"], &case["expect"]);
            let answer = ask(&case["request"]);
            for (name, item) in expect.as_object().unwrap() {
                assert_eq!(&answer[name], item, "{why}: {name} in {answer}");
            }
            compared += 1;
        }
        assert_eq!(compared, 162);
    }

    #[test]
    fn a_body_keeps_the_order_and_numbers_python_wrote() {
        let request = serde_json::json!({
            "action": "text_request",
            "connection": {"id": "local-mlx", "kind": "openai_compatible", "api_profile": "mlx", "base_url": "http://127.0.0.1:8080/v1/"},
            "model": "mlx-community/gemma-4-e4b-it",
            "system": "s",
            "text": "t\u{1f}",
            "images": [],
            "temperature": 0.35,
            "max_tokens": 320,
        });
        let answer = ask(&request);
        assert_eq!(answer["url"], "http://127.0.0.1:8080/v1/chat/completions");
        assert_eq!(
            answer["body"],
            r#"{"model":"mlx-community/gemma-4-e4b-it","stream":false,"max_tokens":320,"temperature":1.0,"enable_thinking":false,"top_p":0.95,"top_k":64,"messages":[{"role":"system","content":"s"},{"role":"user","content":"t\u001f"}]}"#
        );
        assert_eq!(answer["output_budget"], 320);
    }

    /// A prompt that names one image, and the `data:` URL of that image.
    fn image_prompt() -> (serde_json::Value, &'static str) {
        use sha2::{Digest, Sha256};
        let digest: String = Sha256::digest(b"inku")
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        let prompt = serde_json::json!({
            "system": "s", "message": "m", "action_name": "write_image_ddl",
            "response_schema": {"type": "object"},
            "images": [{"media_type": "image/png", "width": 1, "height": 1, "sha256": digest, "byte_len": 4}],
        });
        (prompt, "data:image/png;base64,aW5rdQ==")
    }

    fn sent_body(answer: &serde_json::Value) -> serde_json::Value {
        assert_eq!(answer["outcome"], "ok", "{answer}");
        serde_json::from_str(answer["body"].as_str().unwrap()).unwrap()
    }

    #[test]
    fn the_images_a_prompt_names_follow_its_message_in_each_dialect() {
        let (prompt, url) = image_prompt();
        let request = |kind: &str, base_url: &str| {
            ask(&serde_json::json!({
                "action": "pipeline_request",
                "connection": {"id": "x", "kind": kind, "base_url": base_url},
                "model": "m", "prompt": prompt, "max_tokens": 64, "images": [url],
            }))
        };
        let anthropic = sent_body(&request("anthropic", "https://api.anthropic.com"));
        assert_eq!(
            anthropic["messages"][0]["content"],
            serde_json::json!([
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "aW5rdQ=="}},
                {"type": "text", "text": "m"},
            ])
        );
        let responses = sent_body(&request("openai_compatible", "https://api.openai.com/v1"));
        assert_eq!(
            responses["input"][0]["content"],
            serde_json::json!([
                {"type": "input_text", "text": "m"},
                {"type": "input_image", "image_url": url},
            ])
        );
        let chat = sent_body(&request("openai_compatible", "http://127.0.0.1:8080/v1"));
        assert_eq!(
            chat["messages"][1]["content"],
            serde_json::json!([
                {"type": "text", "text": "m"},
                {"type": "image_url", "image_url": {"url": url}},
            ])
        );
        let gemini = request("gemini", "https://generativelanguage.googleapis.com");
        let parts = serde_json::json!([
            {"text": "m"},
            {"inlineData": {"mimeType": "image/png", "data": "aW5rdQ=="}},
        ]);
        assert_eq!(sent_body(&gemini)["contents"][0]["parts"], parts);
        let counted: serde_json::Value =
            serde_json::from_str(gemini["count_tokens"]["body"].as_str().unwrap()).unwrap();
        assert_eq!(
            counted["generateContentRequest"]["contents"][0]["parts"],
            parts
        );
        let chatgpt = sent_body(&ask(&serde_json::json!({
            "action": "chatgpt_request", "model": "m", "prompt": prompt,
            "answer_limit": 65536, "images": [url],
        })));
        assert_eq!(
            chatgpt["input"][0]["content"],
            serde_json::json!([
                {"type": "input_text", "text": "m"},
                {"type": "input_image", "image_url": url},
            ])
        );
    }

    /// The stages that read and draw a description are sampled as Stage 1 is,
    /// as their prototype sent them; the image stages are not (2026-10-25).
    #[test]
    fn the_description_stages_are_sampled_as_stage1() {
        let temperature = |action_name: &str| {
            let answer = ask(&serde_json::json!({
                "action": "pipeline_request",
                "connection": {"id": "openai", "kind": "openai_compatible", "api_profile": "openai_compatible", "base_url": "https://api.openai.com/v1"},
                "model": "gpt-4o",
                "prompt": {"system": "s", "message": "m", "action_name": action_name,
                           "response_schema": {"type": "object"}},
                "max_tokens": 1024,
            }));
            sent_body(&answer)["temperature"].clone()
        };
        let stage1 = temperature("generate_normalized_ddl");
        assert_eq!(stage1, serde_json::json!(0.3));
        for action_name in [
            "read_description",
            "write_description_ddl",
            "review_description_ddl",
        ] {
            assert_eq!(temperature(action_name), stage1, "{action_name}");
        }
        assert_eq!(temperature("write_image_ddl"), serde_json::json!(0.0));
    }

    /// The ChatGPT body ends with a cache routing hint, the same for the
    /// requests that share a system text and a schema (2026-10-25).
    #[test]
    fn chatgpt_requests_that_share_a_system_and_schema_share_a_cache_key() {
        let key = |system: &str, message: &str| {
            let answer = ask(&serde_json::json!({
                "action": "chatgpt_request", "model": "m", "answer_limit": 65536,
                "prompt": {"system": system, "message": message, "response_schema":
                    {"type": "object", "properties": {"reason": {"type": "string"}}}},
            }));
            let text = answer["body"].as_str().unwrap().to_owned();
            assert!(
                text.find("\"prompt_cache_key\"") > text.find("\"parallel_tool_calls\""),
                "{text}"
            );
            sent_body(&answer)["prompt_cache_key"]
                .as_str()
                .unwrap()
                .to_owned()
        };
        let shared = key("rules", "one work");
        assert_eq!(shared, key("rules", "another work"));
        assert_ne!(shared, key("other rules", "one work"));
        assert!(
            shared.starts_with("inku-") && shared.len() == 21,
            "{shared}"
        );
    }

    #[test]
    fn images_that_are_not_the_ones_the_prompt_names_are_refused() {
        let (prompt, url) = image_prompt();
        let mut unnamed = prompt.clone();
        unnamed.as_object_mut().unwrap().remove("images");
        for (prompt, images) in [
            (prompt.clone(), serde_json::json!([])),
            (
                prompt.clone(),
                serde_json::json!(["data:image/png;base64,aW5rZQ=="]),
            ),
            (
                prompt.clone(),
                serde_json::json!(["data:image/jpeg;base64,aW5rdQ=="]),
            ),
            (unnamed, serde_json::json!([url])),
        ] {
            let answer = ask(&serde_json::json!({
                "action": "pipeline_request",
                "connection": {"id": "x", "kind": "anthropic", "base_url": "https://api.anthropic.com"},
                "model": "m", "prompt": prompt, "max_tokens": 64, "images": images,
            }));
            assert_eq!(answer["outcome"], "refused", "{images}");
            assert_eq!(
                answer["detail"], "images do not match the prompt",
                "{images}"
            );
        }
    }

    #[test]
    fn a_request_that_cannot_be_read_is_refused_by_name() {
        for (request, detail) in [
            (serde_json::json!([]), "the request is not a JSON object"),
            (serde_json::json!({"action": "send"}), "action is unknown"),
            (
                serde_json::json!({"action": "pipeline_request", "connection": {"id": "x", "kind": "gemini", "base_url": "u"},
                                   "model": "m", "prompt": {"system": "s"}, "max_tokens": 1}),
                "prompt.message must be a string",
            ),
            (
                serde_json::json!({"action": "pipeline_response", "format": "gemini", "status": 200}),
                "body must be a string",
            ),
        ] {
            let answer = ask(&request);
            assert_eq!(answer["outcome"], "refused");
            assert_eq!(answer["reason"], "invalid_request");
            assert_eq!(answer["detail"], detail);
        }
    }

    #[test]
    fn usage_counts_cache_and_thinking_alike_in_every_dialect() {
        let read = |format: &str, body: serde_json::Value| {
            let answer = ask(
                &serde_json::json!({"action": "usage", "format": format, "body": body.to_string()}),
            );
            assert_eq!(answer["outcome"], "ok", "{format}");
            answer["usage"].clone()
        };
        // Claude leaves cache reads and writes out of input_tokens.
        assert_eq!(
            read(
                "anthropic",
                serde_json::json!({"usage": {"input_tokens": 10, "cache_read_input_tokens": 300,
                                                             "cache_creation_input_tokens": 40, "output_tokens": 7}})
            ),
            serde_json::json!({"input_tokens": 350, "output_tokens": 7, "cached_input_tokens": 300})
        );
        assert_eq!(
            read(
                "openai_responses",
                serde_json::json!({"usage": {"input_tokens": 120, "output_tokens": 30,
                "input_tokens_details": {"cached_tokens": 100}, "output_tokens_details": {"reasoning_tokens": 20}}})
            ),
            serde_json::json!({"input_tokens": 120, "output_tokens": 30, "cached_input_tokens": 100})
        );
        assert_eq!(
            read(
                "openai_chat",
                serde_json::json!({"usage": {"prompt_tokens": 50, "completion_tokens": 9}})
            ),
            serde_json::json!({"input_tokens": 50, "output_tokens": 9, "cached_input_tokens": null})
        );
        // Gemini leaves thoughts out of candidatesTokenCount.
        assert_eq!(
            read(
                "gemini",
                serde_json::json!({"usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 12,
                                                                 "thoughtsTokenCount": 200, "cachedContentTokenCount": 64}})
            ),
            serde_json::json!({"input_tokens": 80, "output_tokens": 212, "cached_input_tokens": 64})
        );
        assert_eq!(
            read("gemini", serde_json::json!({"candidates": []})),
            serde_json::Value::Null
        );
        assert_eq!(
            ask(
                &serde_json::json!({"action": "usage", "format": "openai_chat", "body": "not json"})
            )["usage"],
            serde_json::Value::Null
        );
    }
}
