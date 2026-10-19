//! The input of the experimental 3D viewer (`inku.ddl3d.v1`): Web's
//! `snapshot()` (`web/src/lib/features/experimental-3d/input.ts`) for the
//! native hosts, which hold a saved work as its stored Score and render
//! metadata texts.
//!
//! The viewer receives the Score and the saved drawing metadata, never
//! application state. Members keep Web's order. Each value keeps its stored
//! spelling with the insignificant white space removed, so a seed above 2^53
//! written as a string or as an integer arrives exactly as saved, and a stored
//! object keeps its member order (Web's `JSON.stringify` keeps the order it
//! received).

use serde_json::Value;

/// Web's fields, in its order.
pub const FIELDS: [&str; 14] = [
    "score",
    "render_seed",
    "composition_seed",
    "render_wild",
    "render_canvas_aspect_id",
    "render_canvas_aspect_ratio",
    "render_canvas_aspect",
    "render_color_map",
    "render_color_catalog_id",
    "render_engine_id",
    "render_engine_version",
    "render_build_number",
    "ddl_version",
    "ddl_engine_version",
];

/// Web's input budget.
pub const MAXIMUM_BYTES: usize = 16 * 1024 * 1024;

/// JavaScript's `Number.MAX_SAFE_INTEGER`.
const MAX_SAFE_INTEGER: u64 = (1 << 53) - 1;

/// The viewer input for a stored Score and its stored render metadata.
///
/// The Score wins over a `score` member of the metadata. A metadata text that
/// is empty or not an object contributes nothing, as a work without metadata
/// has none to give. Errors are Web's reasons.
pub fn snapshot(score: &str, metadata: &str) -> Result<String, &'static str> {
    let score = score.trim();
    match serde_json::from_str::<Value>(score) {
        Ok(Value::Object(_)) => {}
        _ => return Err("invalid_score_json"),
    }
    let saved = top_level_members(metadata.trim()).unwrap_or_default();
    let mut out = String::from("{");
    for field in FIELDS {
        let raw = if field == "score" {
            score
        } else {
            match saved.iter().find(|(key, _)| key == field) {
                Some((_, raw)) => raw,
                None => continue,
            }
        };
        // Web leaves out `undefined` and `null`.
        let value: Value = serde_json::from_str(raw).map_err(|_| "invalid_metadata_json")?;
        if value.is_null() {
            continue;
        }
        if (field == "render_seed" || field == "composition_seed")
            && let Value::Number(number) = &value
            && !is_safe_integer(number)
        {
            return Err("unsafe_numeric_seed");
        }
        if out.len() > 1 {
            out.push(',');
        }
        out.push_str(&serde_json::to_string(field).expect("a field name serialises"));
        out.push(':');
        minify_into(raw, &mut out);
    }
    out.push('}');
    if out.len() > MAXIMUM_BYTES {
        return Err("input_budget_exceeded");
    }
    Ok(out)
}

/// The host's call: `{"score": "<text>", "metadata": "<text>"}` in,
/// `{"json": "<input>"}` or `{"error": "<reason>"}` out.
pub fn snapshot_json(input: &[u8]) -> Vec<u8> {
    let answer = match serde_json::from_slice::<Value>(input) {
        Ok(Value::Object(request)) => match (request.get("score"), request.get("metadata")) {
            (Some(Value::String(score)), metadata) => {
                let metadata = match metadata {
                    Some(Value::String(text)) => text.as_str(),
                    _ => "",
                };
                match snapshot(score, metadata) {
                    Ok(json) => serde_json::json!({ "json": json }),
                    Err(reason) => serde_json::json!({ "error": reason }),
                }
            }
            _ => serde_json::json!({ "error": "invalid_request" }),
        },
        _ => serde_json::json!({ "error": "invalid_request" }),
    };
    serde_json::to_vec(&answer).expect("an answer serialises")
}

fn is_safe_integer(number: &serde_json::Number) -> bool {
    if let Some(value) = number.as_u64() {
        return value <= MAX_SAFE_INTEGER;
    }
    if let Some(value) = number.as_i64() {
        return value.unsigned_abs() <= MAX_SAFE_INTEGER;
    }
    // A fraction or an exponent is not an integer; Web's check is
    // `Number.isSafeInteger`, which answers false for it as well.
    number
        .as_f64()
        .is_some_and(|value| value.fract() == 0.0 && value.abs() <= MAX_SAFE_INTEGER as f64)
}

/// The members of a top-level object, each value as its stored text.
/// None when the text is not one object.
fn top_level_members(text: &str) -> Option<Vec<(String, String)>> {
    if !matches!(serde_json::from_str::<Value>(text), Ok(Value::Object(_))) {
        return None;
    }
    let bytes = text.as_bytes();
    let mut members = Vec::new();
    let mut at = skip_space(bytes, 0);
    debug_assert_eq!(bytes[at], b'{');
    at += 1;
    loop {
        at = skip_space(bytes, at);
        if bytes[at] == b'}' {
            return Some(members);
        }
        let key_end = string_end(bytes, at);
        let key: String = serde_json::from_str(&text[at..key_end]).ok()?;
        at = skip_space(bytes, key_end);
        debug_assert_eq!(bytes[at], b':');
        at = skip_space(bytes, at + 1);
        let value_end = value_end(bytes, at);
        // A repeated key: the last one is what a JSON reader keeps.
        members.retain(|(seen, _): &(String, String)| seen != &key);
        members.push((key, text[at..value_end].trim_end().to_owned()));
        at = skip_space(bytes, value_end);
        if bytes[at] == b',' {
            at += 1;
        }
    }
}

fn skip_space(bytes: &[u8], mut at: usize) -> usize {
    while at < bytes.len() && matches!(bytes[at], b' ' | b'\t' | b'\n' | b'\r') {
        at += 1;
    }
    at
}

/// The index after the string that starts at `at` (its opening quote).
fn string_end(bytes: &[u8], at: usize) -> usize {
    let mut index = at + 1;
    while bytes[index] != b'"' {
        index += if bytes[index] == b'\\' { 2 } else { 1 };
    }
    index + 1
}

/// The index after the value that starts at `at`, in a text already known to
/// be valid JSON.
fn value_end(bytes: &[u8], at: usize) -> usize {
    let mut depth = 0usize;
    let mut index = at;
    while index < bytes.len() {
        match bytes[index] {
            b'"' => {
                index = string_end(bytes, index);
                if depth == 0 {
                    return index;
                }
                continue;
            }
            b'{' | b'[' => depth += 1,
            b'}' | b']' => {
                if depth == 0 {
                    return index;
                }
                depth -= 1;
                if depth == 0 {
                    return index + 1;
                }
            }
            b',' if depth == 0 => return index,
            _ => {}
        }
        index += 1;
    }
    index
}

/// Appends `raw` without the white space outside its strings.
fn minify_into(raw: &str, out: &mut String) {
    let mut in_string = false;
    let mut escaped = false;
    for character in raw.chars() {
        if in_string {
            out.push(character);
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
        } else if character == '"' {
            in_string = true;
            out.push(character);
        } else if !matches!(character, ' ' | '\t' | '\n' | '\r') {
            out.push(character);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn web_fields_in_web_order_with_null_and_unknown_members_left_out() {
        let metadata = r##"{"render_engine_version":"14","render_seed":"9007199254740993","other":1,
            "render_color_map":{"white":"#f5f2eb","black":"#333333"},"render_wild":null,
            "render_canvas_aspect_ratio":1.4,"composition_seed":"9007199254740995"}"##;
        let json = snapshot(r#" {"version":"0.1.0", "items": [ ]} "#, metadata).unwrap();
        assert_eq!(
            json,
            r##"{"score":{"version":"0.1.0","items":[]},"render_seed":"9007199254740993","composition_seed":"9007199254740995","render_canvas_aspect_ratio":1.4,"render_color_map":{"white":"#f5f2eb","black":"#333333"},"render_engine_version":"14"}"##
        );
    }

    #[test]
    fn a_large_integer_seed_is_refused_and_a_safe_one_is_kept_as_written() {
        assert_eq!(
            snapshot("{}", r#"{"render_seed":9007199254740993}"#),
            Err("unsafe_numeric_seed")
        );
        assert_eq!(
            snapshot("{}", r#"{"render_seed":9007199254740991}"#).unwrap(),
            r#"{"score":{},"render_seed":9007199254740991}"#
        );
    }

    #[test]
    fn a_score_that_is_not_an_object_and_an_oversized_input_are_refused() {
        assert_eq!(snapshot("[]", "{}"), Err("invalid_score_json"));
        assert_eq!(snapshot("{", "{}"), Err("invalid_score_json"));
        let big = format!(r#"{{"text":"{}"}}"#, "a".repeat(MAXIMUM_BYTES));
        assert_eq!(snapshot(&big, "{}"), Err("input_budget_exceeded"));
    }

    #[test]
    fn strings_keep_their_spaces_and_escapes() {
        let json = snapshot(r#"{"a" : "x  \" y\\" , "b":[1, 2]}"#, "").unwrap();
        assert_eq!(json, r#"{"score":{"a":"x  \" y\\","b":[1,2]}}"#);
    }

    #[test]
    fn the_solids_fixture_projects_like_web() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../experiments/ddl-3d/fixtures/solids.json"
        ))
        .unwrap();
        let score = serde_json::to_string(&fixture["score"]).unwrap();
        let metadata = include_str!("../../../../experiments/ddl-3d/fixtures/solids.json");
        let json = snapshot(&score, metadata).unwrap();
        let read: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(read["score"], fixture["score"]);
        assert_eq!(read["render_seed"], "9007199254740993");
        let keys: Vec<&str> = json_keys(&json);
        let expected: Vec<&str> = FIELDS
            .iter()
            .copied()
            .filter(|field| !fixture[*field].is_null())
            .collect();
        assert_eq!(keys, expected);
    }

    #[test]
    fn the_host_call_answers_json_or_a_reason() {
        let answer: Value = serde_json::from_slice(&snapshot_json(
            br#"{"score":"{}","metadata":"{\"render_wild\":true}"}"#,
        ))
        .unwrap();
        assert_eq!(answer["json"], r#"{"score":{},"render_wild":true}"#);
        let answer: Value = serde_json::from_slice(&snapshot_json(br#"{"score":"1"}"#)).unwrap();
        assert_eq!(answer["error"], "invalid_score_json");
        let answer: Value = serde_json::from_slice(&snapshot_json(b"[]")).unwrap();
        assert_eq!(answer["error"], "invalid_request");
    }

    fn json_keys(json: &str) -> Vec<&'static str> {
        top_level_members(json)
            .unwrap()
            .into_iter()
            .map(|(key, _)| *FIELDS.iter().find(|field| **field == key).unwrap())
            .collect()
    }
}
