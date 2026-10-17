//! A work's identities: the description hash `dh1` and the render hash `rh3`.
//!
//! Both were defined by Server in Python and are stored in every history row,
//! so they are reproduced here exactly, character for character, as Server
//! computed them: `identity.py` for `dh1`, and `HistoryRenderHashService` over
//! `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`
//! for `rh3`. Android and Swift kept their own copies of the same rules, and
//! the copies drifted (Kotlin's `trim()` keeps U+0085, which Python strips).
//! Every host now asks this one copy. A stored identity must not change, so a
//! rule here follows Python even where Python is surprising.

use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

/// Why a value could not be given an identity.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IdentityError {
    /// The text is not JSON as Python's `json.loads` reads it.
    InvalidJson { at: usize, reason: &'static str },
    /// A render identity was asked of something that is not a JSON object.
    NotAnObject,
    /// A seed Python would have refused to convert (an infinite float).
    UnconvertibleSeed,
}

impl std::fmt::Display for IdentityError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidJson { at, reason } => write!(formatter, "invalid JSON at {at}: {reason}"),
            Self::NotAnObject => formatter.write_str("render identity input must be a JSON object"),
            Self::UnconvertibleSeed => formatter.write_str("render seed cannot be converted"),
        }
    }
}

impl std::error::Error for IdentityError {}

/// Python's `str.isspace()`: Unicode White_Space plus the four information
/// separators U+001C..U+001F, which Rust's `char::is_whitespace` leaves out.
pub fn is_python_space(character: char) -> bool {
    character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
}

/// Python's `str.strip()` with no argument.
pub fn python_strip(text: &str) -> &str {
    text.trim_matches(is_python_space)
}

/// `identity.canonicalize_description`: NFC, one kind of line break, stripped.
pub fn canonicalize_description(text: &str) -> String {
    let normalized: String = text.nfc().collect();
    let normalized = normalized.replace("\r\n", "\n").replace('\r', "\n");
    python_strip(&normalized).to_owned()
}

/// `identity.description_hash`: a deterministic identity, not a secret.
pub fn description_hash(text: &str) -> String {
    format!(
        "dh1:{}",
        sha256_hex(canonicalize_description(text).as_bytes())
    )
}

/// The text Server's `_canonical_json` writes for the JSON value `json_text`.
pub fn canonical_json(json_text: &str) -> Result<String, IdentityError> {
    let value = Parser::new(json_text).parse_document()?;
    let mut out = String::new();
    write_value(&value, &mut out);
    Ok(out)
}

/// `HistoryRenderHashService.render_hash_for_item` for one history item.
///
/// The item is a JSON object carrying `score`, `render_seed`, `render_wild`,
/// `render_engine_id`, `render_engine_version`, `render_color_catalog_id` and
/// `catalog_id`; other members are ignored, as Server ignores them.
pub fn render_hash(item_json: &str) -> Result<String, IdentityError> {
    let Value::Object(item) = Parser::new(item_json).parse_document()? else {
        return Err(IdentityError::NotAnObject);
    };
    let get = |key: &str| {
        item.iter()
            .rev()
            .find(|(name, _)| name == key)
            .map(|(_, value)| value)
    };
    let or = |first: Option<&Value>, second: Option<&Value>| match first {
        Some(value) if value.is_truthy() => value.clone(),
        _ => second.cloned().unwrap_or(Value::Null),
    };
    let payload = Value::Object(vec![
        ("version".to_owned(), Value::String("rh3".to_owned())),
        (
            "score".to_owned(),
            or(get("score"), Some(&Value::Object(Vec::new()))),
        ),
        (
            "render_seed".to_owned(),
            canonical_seed(get("render_seed"))?,
        ),
        (
            "render_wild".to_owned(),
            Value::Bool(get("render_wild").is_some_and(Value::is_truthy)),
        ),
        (
            "render_engine_id".to_owned(),
            get("render_engine_id").cloned().unwrap_or(Value::Null),
        ),
        (
            "render_engine_version".to_owned(),
            get("render_engine_version").cloned().unwrap_or(Value::Null),
        ),
        (
            "render_color_catalog_id".to_owned(),
            or(get("render_color_catalog_id"), get("catalog_id")),
        ),
    ]);
    let mut text = String::new();
    write_value(&payload, &mut text);
    Ok(format!("rh3:{}", sha256_hex(text.as_bytes())))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// `HistoryRenderHashService._canonical_seed`: `int(value)`, or the value as
/// it was when Python's `int()` raises `TypeError` or `ValueError`.
fn canonical_seed(value: Option<&Value>) -> Result<Value, IdentityError> {
    let Some(value) = value else {
        return Ok(Value::Null);
    };
    Ok(match value {
        Value::Null => Value::Null,
        Value::Bool(flag) => Value::Integer(if *flag { "1" } else { "0" }.to_owned()),
        Value::Integer(_) => value.clone(),
        Value::Float(number) if number.is_nan() => value.clone(),
        Value::Float(number) if number.is_infinite() => {
            return Err(IdentityError::UnconvertibleSeed);
        }
        Value::Float(number) => {
            let whole = number.trunc();
            if whole.abs() >= 2f64.powi(127) {
                return Err(IdentityError::UnconvertibleSeed);
            }
            Value::Integer((whole as i128).to_string())
        }
        Value::String(text) => python_int(text).map_or_else(|| value.clone(), Value::Integer),
        Value::Array(_) | Value::Object(_) => value.clone(),
    })
}

/// Python's `int(text)` for a decimal string, or `None` where it raises.
///
/// Surrounding whitespace, one sign, ASCII or full-width digits, and single
/// underscores between digits are accepted. Python also accepts the decimal
/// digits of other scripts; those are not seeds anyone writes, and are read
/// here as a string.
fn python_int(text: &str) -> Option<String> {
    let body = python_strip(text);
    let (negative, digits) = match body.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, body.strip_prefix('+').unwrap_or(body)),
    };
    let mut value = String::new();
    let mut previous_was_digit = false;
    for character in digits.chars() {
        match character {
            '0'..='9' => {
                value.push(character);
                previous_was_digit = true;
            }
            '０'..='９' => {
                value.push(char::from(b'0' + (character as u32 - '０' as u32) as u8));
                previous_was_digit = true;
            }
            '_' if previous_was_digit => previous_was_digit = false,
            _ => return None,
        }
    }
    if value.is_empty() || !previous_was_digit {
        return None;
    }
    Some(canonical_integer(negative, &value))
}

fn canonical_integer(negative: bool, digits: &str) -> String {
    let trimmed = digits.trim_start_matches('0');
    if trimmed.is_empty() {
        "0".to_owned()
    } else if negative {
        format!("-{trimmed}")
    } else {
        trimmed.to_owned()
    }
}

/// A JSON value as Python's `json.loads` holds it: integers keep every digit,
/// and an object keeps its members in order, the last duplicate winning.
#[derive(Debug, Clone, PartialEq)]
enum Value {
    Null,
    Bool(bool),
    Integer(String),
    Float(f64),
    String(String),
    Array(Vec<Value>),
    Object(Vec<(String, Value)>),
}

impl Value {
    /// Python's truth value of the decoded value.
    fn is_truthy(&self) -> bool {
        match self {
            Self::Null => false,
            Self::Bool(flag) => *flag,
            Self::Integer(digits) => digits != "0",
            Self::Float(number) => *number != 0.0,
            Self::String(text) => !text.is_empty(),
            Self::Array(items) => !items.is_empty(),
            Self::Object(members) => !members.is_empty(),
        }
    }
}

fn write_value(value: &Value, out: &mut String) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Integer(digits) => out.push_str(digits),
        Value::Float(number) => out.push_str(&python_float_repr(*number)),
        Value::String(text) => write_string(text, out),
        Value::Array(items) => {
            out.push('[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                write_value(item, out);
            }
            out.push(']');
        }
        Value::Object(members) => {
            // `json.loads` keeps the last of duplicate names; `sort_keys` orders by
            // code point, which is the byte order of UTF-8.
            let mut kept: Vec<&(String, Value)> = Vec::with_capacity(members.len());
            for member in members {
                if let Some(slot) = kept.iter_mut().find(|existing| existing.0 == member.0) {
                    *slot = member;
                } else {
                    kept.push(member);
                }
            }
            kept.sort_by(|left, right| left.0.cmp(&right.0));
            out.push('{');
            for (index, (name, item)) in kept.into_iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                write_string(name, out);
                out.push(':');
                write_value(item, out);
            }
            out.push('}');
        }
    }
}

/// `json.dumps(..., ensure_ascii=False)` string escaping.
fn write_string(text: &str, out: &mut String) {
    out.push('"');
    for character in text.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            '\u{0}'..='\u{1f}' => out.push_str(&format!("\\u{:04x}", character as u32)),
            _ => out.push(character),
        }
    }
    out.push('"');
}

/// Python's `float.__repr__`, which `json.dumps` writes for every float.
///
/// The digits are the shortest that read back to the same float. They are
/// written in positional form when the decimal point falls within
/// (-4, 16] of the first digit, and otherwise as `d.ddde±XX`.
fn python_float_repr(number: f64) -> String {
    if number.is_nan() {
        return "NaN".to_owned();
    }
    if number.is_infinite() {
        return if number > 0.0 {
            "Infinity"
        } else {
            "-Infinity"
        }
        .to_owned();
    }
    let sign = if number.is_sign_negative() { "-" } else { "" };
    if number == 0.0 {
        return format!("{sign}0.0");
    }
    // `{:e}` writes the shortest round-trip digits as `d.ddde<exp>`.
    let scientific = format!("{:e}", number.abs());
    let (mantissa, exponent) = scientific.split_once('e').expect("scientific float form");
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let exponent: i32 = exponent.parse().expect("scientific float exponent");
    let point = exponent + 1;
    let body = if -4 < point && point <= 16 {
        let length = digits.len() as i32;
        if point <= 0 {
            format!("0.{}{digits}", "0".repeat((-point) as usize))
        } else if point >= length {
            format!("{digits}{}.0", "0".repeat((point - length) as usize))
        } else {
            let (whole, fraction) = digits.split_at(point as usize);
            format!("{whole}.{fraction}")
        }
    } else {
        let (first, rest) = digits.split_at(1);
        let mantissa = if rest.is_empty() {
            first.to_owned()
        } else {
            format!("{first}.{rest}")
        };
        let exponent_sign = if exponent < 0 { '-' } else { '+' };
        format!("{mantissa}e{exponent_sign}{:02}", exponent.abs())
    };
    format!("{sign}{body}")
}

/// A reader for the JSON Python's `json.loads` accepts, including its
/// `NaN`, `Infinity` and `-Infinity` extensions.
struct Parser<'a> {
    text: &'a str,
    at: usize,
}

impl<'a> Parser<'a> {
    fn new(text: &'a str) -> Self {
        Self { text, at: 0 }
    }

    fn error(&self, reason: &'static str) -> IdentityError {
        IdentityError::InvalidJson {
            at: self.at,
            reason,
        }
    }

    fn parse_document(mut self) -> Result<Value, IdentityError> {
        self.skip_space();
        let value = self.parse_value()?;
        self.skip_space();
        if self.at != self.text.len() {
            return Err(self.error("extra data"));
        }
        Ok(value)
    }

    fn rest(&self) -> &'a str {
        &self.text[self.at..]
    }

    fn skip_space(&mut self) {
        let rest = self.rest();
        let kept = rest.trim_start_matches([' ', '\t', '\n', '\r']);
        self.at += rest.len() - kept.len();
    }

    fn eat(&mut self, literal: &str) -> bool {
        if self.rest().starts_with(literal) {
            self.at += literal.len();
            true
        } else {
            false
        }
    }

    fn parse_value(&mut self) -> Result<Value, IdentityError> {
        match self.rest().chars().next() {
            Some('{') => self.parse_object(),
            Some('[') => self.parse_array(),
            Some('"') => self.parse_string().map(Value::String),
            Some('-' | '0'..='9') => {
                if self.eat("-Infinity") {
                    Ok(Value::Float(f64::NEG_INFINITY))
                } else {
                    self.parse_number()
                }
            }
            _ if self.eat("null") => Ok(Value::Null),
            _ if self.eat("true") => Ok(Value::Bool(true)),
            _ if self.eat("false") => Ok(Value::Bool(false)),
            _ if self.eat("NaN") => Ok(Value::Float(f64::NAN)),
            _ if self.eat("Infinity") => Ok(Value::Float(f64::INFINITY)),
            _ => Err(self.error("expecting value")),
        }
    }

    fn parse_object(&mut self) -> Result<Value, IdentityError> {
        self.at += 1;
        let mut members = Vec::new();
        self.skip_space();
        if self.eat("}") {
            return Ok(Value::Object(members));
        }
        loop {
            self.skip_space();
            if !self.rest().starts_with('"') {
                return Err(self.error("expecting property name"));
            }
            let name = self.parse_string()?;
            self.skip_space();
            if !self.eat(":") {
                return Err(self.error("expecting ':'"));
            }
            self.skip_space();
            let value = self.parse_value()?;
            members.push((name, value));
            self.skip_space();
            if self.eat("}") {
                return Ok(Value::Object(members));
            }
            if !self.eat(",") {
                return Err(self.error("expecting ',' or '}'"));
            }
        }
    }

    fn parse_array(&mut self) -> Result<Value, IdentityError> {
        self.at += 1;
        let mut items = Vec::new();
        self.skip_space();
        if self.eat("]") {
            return Ok(Value::Array(items));
        }
        loop {
            self.skip_space();
            items.push(self.parse_value()?);
            self.skip_space();
            if self.eat("]") {
                return Ok(Value::Array(items));
            }
            if !self.eat(",") {
                return Err(self.error("expecting ',' or ']'"));
            }
        }
    }

    fn parse_number(&mut self) -> Result<Value, IdentityError> {
        let start = self.at;
        let bytes = self.text.as_bytes();
        let mut end = start;
        let negative = bytes.get(end) == Some(&b'-');
        if negative {
            end += 1;
        }
        let integer_start = end;
        match bytes.get(end) {
            Some(b'0') => end += 1,
            Some(b'1'..=b'9') => {
                while bytes.get(end).is_some_and(u8::is_ascii_digit) {
                    end += 1;
                }
            }
            _ => return Err(self.error("expecting value")),
        }
        let integer_end = end;
        let mut is_float = false;
        if bytes.get(end) == Some(&b'.') && bytes.get(end + 1).is_some_and(u8::is_ascii_digit) {
            is_float = true;
            end += 1;
            while bytes.get(end).is_some_and(u8::is_ascii_digit) {
                end += 1;
            }
        }
        if matches!(bytes.get(end), Some(b'e' | b'E')) {
            let mut exponent = end + 1;
            if matches!(bytes.get(exponent), Some(b'+' | b'-')) {
                exponent += 1;
            }
            if bytes.get(exponent).is_some_and(u8::is_ascii_digit) {
                is_float = true;
                end = exponent;
                while bytes.get(end).is_some_and(u8::is_ascii_digit) {
                    end += 1;
                }
            }
        }
        self.at = end;
        if is_float {
            let number: f64 = self.text[start..end]
                .parse()
                .map_err(|_| self.error("bad number"))?;
            Ok(Value::Float(number))
        } else {
            Ok(Value::Integer(canonical_integer(
                negative,
                &self.text[integer_start..integer_end],
            )))
        }
    }

    fn parse_string(&mut self) -> Result<String, IdentityError> {
        self.at += 1;
        let mut out = String::new();
        loop {
            let rest = self.rest();
            let Some(character) = rest.chars().next() else {
                return Err(self.error("unterminated string"));
            };
            match character {
                '"' => {
                    self.at += 1;
                    return Ok(out);
                }
                '\\' => {
                    self.at += 1;
                    let Some(escape) = self.rest().chars().next() else {
                        return Err(self.error("unterminated string"));
                    };
                    self.at += 1;
                    match escape {
                        '"' => out.push('"'),
                        '\\' => out.push('\\'),
                        '/' => out.push('/'),
                        'b' => out.push('\u{8}'),
                        'f' => out.push('\u{c}'),
                        'n' => out.push('\n'),
                        'r' => out.push('\r'),
                        't' => out.push('\t'),
                        'u' => out.push(self.parse_unicode_escape()?),
                        _ => return Err(self.error("invalid escape")),
                    }
                }
                '\u{0}'..='\u{1f}' => return Err(self.error("invalid control character")),
                _ => {
                    out.push(character);
                    self.at += character.len_utf8();
                }
            }
        }
    }

    fn parse_hex4(&mut self) -> Result<u32, IdentityError> {
        let digits = self
            .rest()
            .get(..4)
            .ok_or_else(|| self.error("invalid \\uXXXX escape"))?;
        if !digits.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(self.error("invalid \\uXXXX escape"));
        }
        self.at += 4;
        Ok(u32::from_str_radix(digits, 16).expect("four hex digits"))
    }

    /// A `\uXXXX` escape. A lone surrogate is refused: Python would decode it
    /// and then fail to encode the canonical text as UTF-8 for the hash.
    fn parse_unicode_escape(&mut self) -> Result<char, IdentityError> {
        let first = self.parse_hex4()?;
        let code = if (0xd800..0xdc00).contains(&first) {
            if !self.eat("\\u") {
                return Err(self.error("lone surrogate"));
            }
            let second = self.parse_hex4()?;
            if !(0xdc00..0xe000).contains(&second) {
                return Err(self.error("lone surrogate"));
            }
            0x10000 + ((first - 0xd800) << 10) + (second - 0xdc00)
        } else {
            first
        };
        char::from_u32(code).ok_or_else(|| self.error("lone surrogate"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cases() -> serde_json::Value {
        serde_json::from_str(include_str!(
            "../../../../server/tests/data/identity-cases.json"
        ))
        .expect("identity cases")
    }

    #[test]
    fn every_shared_description_case_hashes_as_server_does() {
        let table = cases();
        let rows = table["description_hash"]
            .as_array()
            .expect("description cases");
        assert!(!rows.is_empty());
        for row in rows {
            let text = row["text"].as_str().expect("text");
            assert_eq!(
                description_hash(text),
                row["dh1"].as_str().expect("dh1"),
                "{}",
                row["why"]
            );
        }
    }

    #[test]
    fn every_shared_canonical_json_case_writes_what_python_writes() {
        let table = cases();
        let rows = table["canonical_json"].as_array().expect("canonical cases");
        assert!(!rows.is_empty());
        for row in rows {
            let input = row["input"].as_str().expect("input");
            assert_eq!(
                canonical_json(input).expect("canonical json"),
                row["canonical"].as_str().expect("canonical"),
                "{}",
                row["why"]
            );
        }
    }

    #[test]
    fn every_shared_render_case_hashes_as_server_does() {
        let table = cases();
        let rows = table["render_hash"].as_array().expect("render cases");
        assert!(!rows.is_empty());
        for row in rows {
            let item = row["item"].as_str().expect("item");
            assert_eq!(
                render_hash(item).expect("rh3"),
                row["rh3"].as_str().expect("rh3"),
                "{}",
                row["why"]
            );
        }
    }

    #[test]
    fn python_space_is_unicode_white_space_and_the_information_separators() {
        let python: Vec<u32> = cases()["python_space"]
            .as_array()
            .expect("python space")
            .iter()
            .map(|code| code.as_u64().expect("code point") as u32)
            .collect();
        let rust: Vec<u32> = (0..=0x10ffff_u32)
            .filter_map(char::from_u32)
            .filter(|character| is_python_space(*character))
            .map(|character| character as u32)
            .collect();
        assert_eq!(rust, python);
    }

    #[test]
    fn invalid_json_is_refused_rather_than_guessed() {
        assert!(canonical_json("{\"a\":}").is_err());
        assert!(canonical_json("\"\\ud800\"").is_err());
        assert!(canonical_json("[1,]").is_err());
        assert_eq!(render_hash("[]"), Err(IdentityError::NotAnObject));
    }
}
