//! Runtime-disconnected visible normalized DDL document envelope.

use std::{collections::BTreeMap, fmt};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    MacroInvocation, ResolvedInstructionLanguage, SemanticMap,
    validate_macro_definition_semantic_version,
};

/// Stable identity for the visible normalized DDL document format.
pub const NORMALIZED_DDL_DOCUMENT_SCHEMA_ID: &str = "inku.normalized-ddl-document.v1";

/// A locked macro definition identity in the document preamble.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroLock {
    qualified_name: String,
    version: String,
    digest: String,
}

impl MacroLock {
    pub fn qualified_name(&self) -> &str {
        &self.qualified_name
    }

    pub fn version(&self) -> &str {
        &self.version
    }

    pub fn digest(&self) -> &str {
        &self.digest
    }
}

/// The closed argument value syntax accepted before definition resolution.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum MacroArgumentValue {
    Number(serde_json::Number),
    Boolean(bool),
    String(String),
    List(Vec<MacroArgumentValue>),
}

/// One structural macro invocation in document-body order.
#[derive(Clone, Debug, PartialEq)]
pub struct NormalizedDdlInvocation {
    invocation: MacroInvocation,
    arguments: SemanticMap<MacroArgumentValue>,
}

impl NormalizedDdlInvocation {
    pub fn invocation(&self) -> &MacroInvocation {
        &self.invocation
    }

    pub fn arguments(&self) -> &SemanticMap<MacroArgumentValue> {
        &self.arguments
    }
}

/// A lossless body line or a structural macro invocation.
#[derive(Clone, Debug, PartialEq)]
pub enum DdlDocumentBodyNode {
    Text(String),
    Invocation(NormalizedDdlInvocation),
}

/// A validated visible normalized DDL v1 document.
#[derive(Clone, Debug, PartialEq)]
pub struct NormalizedDdlDocument {
    language: ResolvedInstructionLanguage,
    canvas_id: String,
    macro_locks: Vec<MacroLock>,
    body: Vec<DdlDocumentBodyNode>,
}

impl NormalizedDdlDocument {
    pub const fn language(&self) -> ResolvedInstructionLanguage {
        self.language
    }

    pub fn canvas_id(&self) -> &str {
        &self.canvas_id
    }

    pub fn macro_locks(&self) -> &[MacroLock] {
        &self.macro_locks
    }

    pub fn body(&self) -> &[DdlDocumentBodyNode] {
        &self.body
    }

    /// Serialize in canonical directive, lock, body, and JSON order.
    pub fn canonical_string(&self) -> String {
        let mut lines = vec![
            "@inku-ddl v1".to_owned(),
            format!("@language {}", self.language.as_str()),
            format!("@canvas {}", self.canvas_id),
        ];
        let mut locks = self.macro_locks.iter().collect::<Vec<_>>();
        locks.sort_by(|left, right| {
            left.qualified_name
                .as_bytes()
                .cmp(right.qualified_name.as_bytes())
        });
        for macro_lock in locks {
            lines.push(format!(
                "@macro-lock {} {} {}",
                serde_json::to_string(&macro_lock.qualified_name)
                    .expect("a Rust string must serialize as JSON"),
                macro_lock.version,
                macro_lock.digest,
            ));
        }
        lines.push(String::new());
        for node in &self.body {
            match node {
                DdlDocumentBodyNode::Text(text) => lines.push(text.clone()),
                DdlDocumentBodyNode::Invocation(invocation) => lines.push(format!(
                    "@invoke {} {}",
                    serde_json::to_string(&invocation.invocation.qualified_name())
                        .expect("a Rust string must serialize as JSON"),
                    serde_json::to_string(&invocation.arguments)
                        .expect("validated macro arguments must serialize"),
                )),
            }
        }
        lines.join("\n")
    }
}

/// Headerless prose identified without choosing language or canvas defaults.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LegacyProse {
    prose: String,
}

impl LegacyProse {
    pub fn prose(&self) -> &str {
        &self.prose
    }
}

/// Explicit parse classification for v1 documents and legacy prose.
#[derive(Clone, Debug, PartialEq)]
pub enum DdlDocumentParseOutcome {
    Document(NormalizedDdlDocument),
    LegacyProse(LegacyProse),
}

/// Stable source diagnostic. Code, line, and column are the semantic identity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DdlDocumentDiagnostic {
    code: &'static str,
    line: usize,
    column: usize,
}

impl DdlDocumentDiagnostic {
    pub const fn code(&self) -> &'static str {
        self.code
    }

    pub const fn line(&self) -> usize {
        self.line
    }

    pub const fn column(&self) -> usize {
        self.column
    }
}

impl fmt::Display for DdlDocumentDiagnostic {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}:{}", self.code, self.line, self.column)
    }
}

impl std::error::Error for DdlDocumentDiagnostic {}

/// Parse a visible normalized DDL input without inferring language or canvas.
pub fn parse_normalized_ddl_document(
    input: &str,
) -> Result<DdlDocumentParseOutcome, DdlDocumentDiagnostic> {
    let normalized = normalize_newlines(input)?;
    if normalized.lines().next() != Some("@inku-ddl v1") {
        if normalized.starts_with("@inku-ddl ") {
            return Err(diagnostic("unknown_document_version", 1, 1));
        }
        let prose = canonicalize_legacy_prose(&normalized)?;
        return Ok(DdlDocumentParseOutcome::LegacyProse(LegacyProse { prose }));
    }
    parse_v1_document(&normalized).map(DdlDocumentParseOutcome::Document)
}

/// Wrap headerless prose with caller-resolved language and canonical canvas ID.
pub fn wrap_legacy_prose(
    prose: &str,
    language: ResolvedInstructionLanguage,
    canvas_id: &str,
) -> Result<NormalizedDdlDocument, DdlDocumentDiagnostic> {
    if inku_score::validate_canvas_format_id(canvas_id).is_err() {
        return Err(diagnostic("invalid_canvas", 1, 1));
    }
    let normalized = normalize_newlines(prose)?;
    let body = canonicalize_legacy_prose(&normalized)?;
    let synthetic = format!(
        "@inku-ddl v1\n@language {}\n@canvas {}\n\n{}",
        language.as_str(),
        canvas_id,
        body,
    );
    parse_v1_document(&synthetic)
}

fn parse_v1_document(input: &str) -> Result<NormalizedDdlDocument, DdlDocumentDiagnostic> {
    let lines = input.split('\n').collect::<Vec<_>>();
    let language_line = required_line(&lines, 1, "missing_language_directive")?;
    let language = match language_line.strip_prefix("@language ") {
        Some("ja") => ResolvedInstructionLanguage::Ja,
        Some("en") => ResolvedInstructionLanguage::En,
        Some(_) => return Err(diagnostic("invalid_language", 2, 1)),
        None => return Err(diagnostic("missing_language_directive", 2, 1)),
    };

    let canvas_line = required_line(&lines, 2, "missing_canvas_directive")?;
    let canvas_id = canvas_line
        .strip_prefix("@canvas ")
        .ok_or_else(|| diagnostic("missing_canvas_directive", 3, 1))?;
    if canvas_id.is_empty()
        || canvas_id.contains(' ')
        || inku_score::validate_canvas_format_id(canvas_id).is_err()
    {
        return Err(diagnostic("invalid_canvas", 3, 1));
    }

    let mut macro_locks = Vec::new();
    let mut lock_lines = BTreeMap::<String, usize>::new();
    let mut index = 3;
    while let Some(line) = lines.get(index) {
        if line.is_empty() {
            break;
        }
        if !line.starts_with("@macro-lock ") {
            return Err(diagnostic("missing_body_separator", index + 1, 1));
        }
        let macro_lock = parse_macro_lock(line, index + 1)?;
        if let Some(previous) = macro_locks
            .iter()
            .find(|existing: &&MacroLock| existing.qualified_name == macro_lock.qualified_name)
        {
            let code = if previous == &macro_lock {
                "duplicate_macro_lock"
            } else {
                "conflicting_macro_lock"
            };
            return Err(diagnostic(code, index + 1, 1));
        }
        lock_lines.insert(macro_lock.qualified_name.clone(), index + 1);
        macro_locks.push(macro_lock);
        index += 1;
    }

    if lines.get(index) != Some(&"") {
        return Err(diagnostic("missing_body_separator", index + 1, 1));
    }
    index += 1;

    let body_lines = canonical_body_lines(&lines, index);
    if body_lines.is_empty() {
        return Err(diagnostic("blank_body", index + 1, 1));
    }

    let mut body = Vec::with_capacity(body_lines.len());
    let mut invocation_lines = BTreeMap::<String, usize>::new();
    let mut invocation_ordinal = 0_u64;
    for (line_number, line) in body_lines {
        if line.starts_with("@invoke ") {
            let invocation = parse_invocation(&line, line_number, invocation_ordinal)?;
            let qualified_name = invocation.invocation.qualified_name();
            invocation_lines
                .entry(qualified_name)
                .or_insert(line_number);
            body.push(DdlDocumentBodyNode::Invocation(invocation));
            invocation_ordinal += 1;
        } else if line.starts_with('@') {
            return Err(diagnostic("unknown_body_directive", line_number, 1));
        } else {
            body.push(DdlDocumentBodyNode::Text(line));
        }
    }

    for (qualified_name, line_number) in &invocation_lines {
        if !lock_lines.contains_key(qualified_name) {
            return Err(diagnostic("missing_macro_lock", *line_number, 1));
        }
    }
    for (qualified_name, line_number) in &lock_lines {
        if !invocation_lines.contains_key(qualified_name) {
            return Err(diagnostic("unused_macro_lock", *line_number, 1));
        }
    }

    macro_locks.sort_by(|left, right| {
        left.qualified_name
            .as_bytes()
            .cmp(right.qualified_name.as_bytes())
    });

    Ok(NormalizedDdlDocument {
        language,
        canvas_id: canvas_id.to_owned(),
        macro_locks,
        body,
    })
}

fn parse_macro_lock(line: &str, line_number: usize) -> Result<MacroLock, DdlDocumentDiagnostic> {
    let source = line
        .strip_prefix("@macro-lock ")
        .ok_or_else(|| diagnostic("invalid_macro_lock", line_number, 1))?;
    let (qualified_name, rest) = parse_qualified_name_prefix(source, line_number, 13)?;
    let Some(rest) = rest.strip_prefix(' ') else {
        return Err(diagnostic(
            "invalid_macro_lock",
            line_number,
            line.len() + 1,
        ));
    };
    if rest.starts_with(' ') {
        return Err(diagnostic("invalid_macro_lock", line_number, 1));
    }
    let Some((version, digest)) = rest.split_once(' ') else {
        return Err(diagnostic("invalid_macro_lock", line_number, 1));
    };
    if version.is_empty() || digest.is_empty() || digest.contains(' ') {
        return Err(diagnostic("invalid_macro_lock", line_number, 1));
    }
    if !validate_macro_definition_semantic_version(version) {
        return Err(diagnostic("invalid_semantic_version", line_number, 1));
    }
    if !is_full_sha256_digest(digest) {
        return Err(diagnostic("invalid_digest", line_number, 1));
    }
    Ok(MacroLock {
        qualified_name,
        version: version.to_owned(),
        digest: digest.to_owned(),
    })
}

fn parse_invocation(
    line: &str,
    line_number: usize,
    ordinal: u64,
) -> Result<NormalizedDdlInvocation, DdlDocumentDiagnostic> {
    let source = line
        .strip_prefix("@invoke ")
        .ok_or_else(|| diagnostic("invalid_invocation", line_number, 1))?;
    let (qualified_name, rest) = parse_qualified_name_prefix(source, line_number, 9)?;
    let Some(arguments_source) = rest.strip_prefix(' ') else {
        return Err(diagnostic(
            "invalid_invocation",
            line_number,
            line.len() + 1,
        ));
    };
    if arguments_source.starts_with(' ') || !arguments_source.starts_with('{') {
        return Err(diagnostic("invalid_arguments", line_number, 1));
    }
    let value: Value = serde_json::from_str(arguments_source)
        .map_err(|_| diagnostic("invalid_arguments", line_number, 1))?;
    validate_argument_value(&value, true).map_err(|code| diagnostic(code, line_number, 1))?;
    let arguments: SemanticMap<MacroArgumentValue> = serde_json::from_str(arguments_source)
        .map_err(|error| {
            let code = if error.to_string().contains("duplicate key") {
                "duplicate_argument_key"
            } else {
                "invalid_arguments"
            };
            diagnostic(code, line_number, 1)
        })?;
    let invocation = macro_invocation(&qualified_name, ordinal)
        .map_err(|code| diagnostic(code, line_number, 9))?;
    Ok(NormalizedDdlInvocation {
        invocation,
        arguments,
    })
}

fn parse_qualified_name_prefix<'a>(
    source: &'a str,
    line_number: usize,
    column: usize,
) -> Result<(String, &'a str), DdlDocumentDiagnostic> {
    if !source.starts_with('"') {
        return Err(diagnostic("invalid_qualified_name", line_number, column));
    }
    let mut values = serde_json::Deserializer::from_str(source).into_iter::<String>();
    let qualified_name = values
        .next()
        .ok_or_else(|| diagnostic("invalid_qualified_name", line_number, column))?
        .map_err(|error| {
            diagnostic(
                "invalid_qualified_name",
                line_number,
                column + error.column().saturating_sub(1),
            )
        })?;
    let offset = values.byte_offset();
    macro_invocation(&qualified_name, 0).map_err(|code| diagnostic(code, line_number, column))?;
    Ok((qualified_name, &source[offset..]))
}

fn macro_invocation(qualified_name: &str, ordinal: u64) -> Result<MacroInvocation, &'static str> {
    let Some((namespace, heading)) = qualified_name.split_once('.') else {
        return Err("invalid_qualified_name");
    };
    MacroInvocation::new(namespace, heading, ordinal).map_err(|_| "invalid_qualified_name")
}

fn validate_argument_value(value: &Value, top_level: bool) -> Result<(), &'static str> {
    match value {
        Value::Object(values) if top_level => {
            for value in values.values() {
                validate_argument_value(value, false)?;
            }
            Ok(())
        }
        Value::Object(_) => Err("nested_argument_object"),
        Value::Null => Err("null_argument"),
        Value::Array(values) => {
            for value in values {
                validate_argument_value(value, false)?;
            }
            Ok(())
        }
        Value::Bool(_) | Value::Number(_) | Value::String(_) if !top_level => Ok(()),
        _ => Err("invalid_arguments"),
    }
}

fn is_full_sha256_digest(value: &str) -> bool {
    let Some(hex) = value.strip_prefix("sha256:") else {
        return false;
    };
    hex.len() == 64
        && hex
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn normalize_newlines(input: &str) -> Result<String, DdlDocumentDiagnostic> {
    let bytes = input.as_bytes();
    let mut output = String::with_capacity(input.len());
    let mut index = 0;
    let mut line = 1;
    let mut column = 1;
    while index < bytes.len() {
        match bytes[index] {
            b'\r' if bytes.get(index + 1) == Some(&b'\n') => {
                output.push('\n');
                index += 2;
                line += 1;
                column = 1;
            }
            b'\r' => return Err(diagnostic("bare_carriage_return", line, column)),
            b'\n' => {
                output.push('\n');
                index += 1;
                line += 1;
                column = 1;
            }
            _ => {
                let character = input[index..]
                    .chars()
                    .next()
                    .expect("index remains on a UTF-8 boundary");
                output.push(character);
                index += character.len_utf8();
                column += 1;
            }
        }
    }
    Ok(output)
}

fn canonicalize_legacy_prose(input: &str) -> Result<String, DdlDocumentDiagnostic> {
    let raw_lines = input.split('\n').collect::<Vec<_>>();
    let lines = canonical_body_lines(&raw_lines, 0);
    if lines.is_empty() {
        return Err(diagnostic("blank_body", 1, 1));
    }
    Ok(lines
        .into_iter()
        .map(|(_, line)| line)
        .collect::<Vec<_>>()
        .join("\n"))
}

fn canonical_body_lines(lines: &[&str], start: usize) -> Vec<(usize, String)> {
    let mut body = lines[start..]
        .iter()
        .enumerate()
        .map(|(offset, line)| {
            (
                start + offset + 1,
                line.trim_end_matches([' ', '\t']).to_owned(),
            )
        })
        .collect::<Vec<_>>();
    while body.first().is_some_and(|(_, line)| line.is_empty()) {
        body.remove(0);
    }
    while body.last().is_some_and(|(_, line)| line.is_empty()) {
        body.pop();
    }
    body
}

fn required_line<'a>(
    lines: &'a [&str],
    index: usize,
    code: &'static str,
) -> Result<&'a str, DdlDocumentDiagnostic> {
    lines
        .get(index)
        .copied()
        .ok_or_else(|| diagnostic(code, index + 1, 1))
}

const fn diagnostic(code: &'static str, line: usize, column: usize) -> DdlDocumentDiagnostic {
    DdlDocumentDiagnostic { code, line, column }
}
