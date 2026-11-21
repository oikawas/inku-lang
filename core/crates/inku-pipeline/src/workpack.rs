//! Portable work pack v1. The host owns the file and database transaction.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::LazyLock;

use serde::Deserialize;
use serde_json::{Value, json, value::RawValue};
use unicode_segmentation::UnicodeSegmentation;

const MAX_LINE: usize = 64 * 1024 * 1024;
const KINDS: [&str; 5] = [
    "history",
    "lineage_node",
    "lineage_edge",
    "annotation",
    "colophon",
];
const CONTRACT_JSON: &str = include_str!("../../../../persistence/contract.json");

#[derive(Deserialize)]
struct Contract {
    contract_version: u64,
    records: BTreeMap<String, RecordFields>,
}

#[derive(Deserialize)]
struct RecordFields {
    fields: Vec<Field>,
}

#[derive(Deserialize)]
struct Field {
    name: String,
    classification: String,
    encoding: String,
    nullable: bool,
}

static CONTRACT: LazyLock<Contract> =
    LazyLock::new(|| serde_json::from_str(CONTRACT_JSON).expect("embedded persistence contract"));

fn fields(kind: &str) -> Option<impl Iterator<Item = &'static Field>> {
    let name = match kind {
        "history" => "history",
        "lineage_node" => "lineage_nodes",
        "lineage_edge" => "lineage_edges",
        _ => return None,
    };
    Some(CONTRACT.records[name].fields.iter().filter(|field| {
        matches!(
            field.classification.as_str(),
            "required_common" | "optional_common"
        )
    }))
}

type RawObject<'a> = BTreeMap<String, &'a RawValue>;
type Check<T> = Result<T, Refusal>;

struct Refusal {
    code: &'static str,
    reason: String,
}

fn invalid(reason: impl Into<String>) -> Refusal {
    Refusal {
        code: "invalid",
        reason: reason.into(),
    }
}

fn too_large() -> Refusal {
    Refusal {
        code: "too_large",
        reason: "too_large".into(),
    }
}

fn answer(result: Check<Value>, line: Option<u64>) -> Vec<u8> {
    let value = result.unwrap_or_else(|failure| {
        let mut response = json!({"outcome":"refused","code":failure.code,"reason":failure.reason});
        if let Some(line) = line {
            response["line"] = json!(line);
        }
        response
    });
    serde_json::to_vec(&value).expect("work pack metadata serializes")
}

fn raw_object(bytes: &[u8]) -> Check<RawObject<'_>> {
    serde_json::from_slice(bytes).map_err(|_| invalid("invalid JSON object"))
}

fn read<T: serde::de::DeserializeOwned>(row: &RawObject<'_>, field: &str) -> Option<T> {
    serde_json::from_str(row.get(field)?.get()).ok()
}

fn integer(raw: &str) -> Option<i64> {
    if let Ok(value) = serde_json::from_str::<i64>(raw) {
        return Some(value);
    }
    // The Swift reader also accepts integral JSON floats.
    let n = serde_json::from_str::<f64>(raw).ok()?;
    (n.fract() == 0.0 && n >= i64::MIN as f64 && n < i64::MAX as f64).then_some(n as i64)
}

// RawValue checks the JSON grammar without decoding escapes. Validate UTF-16
// pairs without allocating a decoded copy of a large SVG or text field.
fn valid_string(raw: &str) -> bool {
    if !raw.starts_with('"') {
        return false;
    }
    let mut rest = &raw[1..];
    while let Some((_, tail)) = rest.split_once('\\') {
        if let Some(hex) = tail.strip_prefix('u') {
            let unit = u16::from_str_radix(&hex[..4], 16).expect("validated JSON escape");
            rest = &hex[4..];
            if (0xd800..=0xdbff).contains(&unit) {
                let Some(low) = rest.strip_prefix("\\u").and_then(|s| s.get(..4)) else {
                    return false;
                };
                if !u16::from_str_radix(low, 16).is_ok_and(|n| (0xdc00..=0xdfff).contains(&n)) {
                    return false;
                }
                rest = &rest[6..];
            } else if (0xdc00..=0xdfff).contains(&unit) {
                return false;
            }
        } else {
            rest = &tail[1..];
        }
    }
    true
}

fn valid_encoding(name: &str, raw: &str) -> Option<bool> {
    Some(match name {
        "text" | "utf8_text" | "utf8_svg" | "rh3_or_legacy_text" | "dh1_or_legacy_text" => {
            valid_string(raw)
        }
        "null_or_legacy_expanded" => {
            serde_json::from_str::<String>(raw).is_ok_and(|s| s == "legacy_expanded")
        }
        "canonical_json_object" => serde_json::from_str::<String>(raw)
            .is_ok_and(|s| serde_json::from_str::<RawObject<'_>>(&s).is_ok()),
        "unsigned_decimal_text" => serde_json::from_str::<String>(raw)
            .is_ok_and(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())),
        "boolean_0_1" => matches!(integer(raw), Some(0 | 1)),
        "unix_epoch_milliseconds" | "integer_milliseconds" => integer(raw).is_some(),
        "finite_number" => serde_json::from_str::<f64>(raw).is_ok_and(f64::is_finite),
        _ => return None,
    })
}

fn check_header(row: &RawObject<'_>) -> Check<Value> {
    let version = row.get("format_version").and_then(|raw| integer(raw.get()));
    if read::<String>(row, "format").as_deref() != Some("inku.workpack")
        || !version.is_some_and(|n| n >= 1)
    {
        return Err(invalid("header"));
    }
    if version > Some(1) {
        return Err(Refusal {
            code: "newer_version",
            reason: "header".into(),
        });
    }
    let producer: BTreeMap<String, Value> =
        read(row, "producer").ok_or_else(|| invalid("header"))?;
    if ["persistence_contract_version", "exported_at"]
        .iter()
        .any(|key| {
            !row.get(*key)
                .is_some_and(|raw| integer(raw.get()).is_some())
        })
        || ["host", "app_version"]
            .iter()
            .any(|key| !producer.get(*key).is_some_and(Value::is_string))
        || ["build", "schema_version"].iter().any(|key| {
            !producer
                .get(*key)
                .is_some_and(|value| integer(&value.to_string()).is_some())
        })
    {
        return Err(invalid("header"));
    }
    let counts: BTreeMap<String, Value> = read(row, "counts").ok_or_else(|| invalid("header"))?;
    let counts = checked_counts(&counts)?;
    Ok(json!({"outcome":"header","format_version":1,"counts":counts,"producer":producer}))
}

fn checked_counts(counts: &BTreeMap<String, Value>) -> Check<BTreeMap<&'static str, usize>> {
    KINDS
        .into_iter()
        .map(|kind| {
            let count = counts
                .get(kind)
                .and_then(|value| integer(&value.to_string()))
                .and_then(|n| usize::try_from(n).ok())
                .ok_or_else(|| invalid("counts"))?;
            Ok((kind, count))
        })
        .collect()
}

const ANNOTATION_FIELDS: [&str; 3] = ["history_id", "note", "for_revision"];
const COLOPHON_REQUIRED: [&str; 9] = [
    "id",
    "target_node_id",
    "branch_snapshot",
    "model",
    "language",
    "body",
    "warnings_json",
    "fact_sheet_json",
    "at",
];
const COLOPHON_OPTIONAL: [&str; 3] = ["generated_body", "adopted_body", "signature"];

fn validate_record(kind: &str, row: &RawObject<'_>) -> Check<()> {
    if let Some(fields) = fields(kind) {
        for field in fields {
            let Some(raw) = row.get(&field.name).map(|raw| raw.get()) else {
                if field.classification == "optional_common" {
                    continue;
                }
                return Err(invalid(format!("missing {}", field.name)));
            };
            if raw == "null" {
                if !field.nullable {
                    return Err(invalid(format!("null {}", field.name)));
                }
            } else if !valid_encoding(&field.encoding, raw)
                .ok_or_else(|| invalid(format!("unknown encoding {}", field.encoding)))?
            {
                return Err(invalid(format!("type {}", field.name)));
            }
        }
        if kind == "lineage_edge"
            && read::<String>(row, "parent_node_id") == read::<String>(row, "child_node_id")
        {
            return Err(invalid("self edge"));
        }
    } else if kind == "annotation" {
        if !read::<String>(row, "history_id").is_some_and(|s| !s.is_empty())
            || !read::<Option<String>>(row, "note")
                .is_some_and(|note| note.is_none_or(|s| s.graphemes(true).nth(240).is_none()))
            || !row
                .get("for_revision")
                .is_some_and(|raw| matches!(integer(raw.get()), Some(0 | 1)))
        {
            return Err(invalid("annotation"));
        }
    } else {
        for name in COLOPHON_REQUIRED.into_iter().filter(|name| *name != "at") {
            if !row
                .get(name)
                .is_some_and(|raw| valid_string(raw.get()) && raw.get() != "\"\"")
            {
                return Err(invalid(format!("colophon {name}")));
            }
        }
        if !row
            .get("at")
            .is_some_and(|raw| integer(raw.get()).is_some())
            || !matches!(
                read::<String>(row, "language").as_deref(),
                Some("ja" | "en")
            )
        {
            return Err(invalid("colophon"));
        }
        let branch = read::<String>(row, "branch_snapshot")
            .and_then(|s| serde_json::from_str::<Vec<String>>(&s).ok());
        let target = read::<String>(row, "target_node_id");
        if branch.as_ref().and_then(|ids| ids.last()) != target.as_ref()
            || target.is_none()
            || !read::<String>(row, "warnings_json")
                .is_some_and(|s| serde_json::from_str::<Vec<String>>(&s).is_ok())
            || !read::<String>(row, "fact_sheet_json")
                .is_some_and(|s| serde_json::from_str::<RawObject<'_>>(&s).is_ok())
        {
            return Err(invalid("colophon JSON"));
        }
        for name in COLOPHON_OPTIONAL {
            if row
                .get(name)
                .is_some_and(|raw| raw.get() != "null" && !valid_string(raw.get()))
            {
                return Err(invalid(format!("colophon {name}")));
            }
        }
    }
    Ok(())
}

fn read_line_inner(line: &[u8], line_number: u64) -> Check<Value> {
    if line.len() > MAX_LINE {
        return Err(too_large());
    }
    if line_number == 0 || line.contains(&b'\n') || std::str::from_utf8(line).is_err() {
        return Err(invalid(format!("line {line_number}")));
    }
    let row = raw_object(line).map_err(|_| invalid(format!("line {line_number}")))?;
    if line_number == 1 {
        return check_header(&row);
    }
    let kind: String = read(&row, "kind").ok_or_else(|| invalid("kind"))?;
    if !KINDS.contains(&kind.as_str()) {
        return Ok(json!({"outcome":"unknown_kind"}));
    }
    validate_record(&kind, &row)?;
    let key_field = if kind == "annotation" {
        "history_id"
    } else {
        "id"
    };
    let key: String = read(&row, key_field).ok_or_else(|| invalid(format!("type {key_field}")))?;
    let identity = match kind.as_str() {
        "history" => json!({"id":key,"node_id":read::<String>(&row,"lineage_node_id")}),
        "lineage_node" => json!({"id":key,"history_id":read::<String>(&row,"history_id")}),
        "lineage_edge" => {
            json!({"id":key,"parent":read::<String>(&row,"parent_node_id"),"child":read::<String>(&row,"child_node_id")})
        }
        "annotation" => json!({"history_id":key}),
        _ => json!({"id":key,"target_node_id":read::<String>(&row,"target_node_id")}),
    };
    Ok(json!({"outcome":"record","kind":kind,"key":key,"identity":identity}))
}

pub fn read_line(line: &[u8], line_number: u64) -> Vec<u8> {
    answer(read_line_inner(line, line_number), Some(line_number))
}

#[derive(Deserialize)]
struct PlanRequest {
    action: String,
    counts: BTreeMap<String, Value>,
    records: Vec<Record>,
    existing: Existing,
}

#[derive(Default, Deserialize)]
struct Existing {
    #[serde(default)]
    works: HashSet<String>,
    #[serde(default)]
    node_roots: HashMap<String, String>,
    #[serde(default)]
    parents: HashMap<String, String>,
}

#[derive(Deserialize)]
struct Record {
    key: String,
    #[serde(flatten)]
    entry: Entry,
}

#[derive(Deserialize)]
#[serde(tag = "kind", content = "identity", rename_all = "snake_case")]
enum Entry {
    History {
        id: String,
        node_id: Option<String>,
    },
    LineageNode {
        id: String,
        history_id: Option<String>,
    },
    LineageEdge {
        id: String,
        parent: String,
        child: String,
    },
    Annotation {
        history_id: String,
    },
    Colophon {
        id: String,
        target_node_id: String,
    },
}

impl Entry {
    fn rank_and_key(&self) -> (usize, &str) {
        match self {
            Self::History { id, .. } => (0, id),
            Self::LineageNode { id, .. } => (1, id),
            Self::LineageEdge { id, .. } => (2, id),
            Self::Annotation { history_id } => (3, history_id),
            Self::Colophon { id, .. } => (4, id),
        }
    }
}

fn plan_inner(input: &[u8]) -> Check<Value> {
    let req: PlanRequest = serde_json::from_slice(input).map_err(|_| invalid("plan"))?;
    if req.action != "plan" {
        return Err(invalid("plan"));
    }
    let expected = checked_counts(&req.counts)?;
    let mut seen: [HashSet<&str>; KINDS.len()] = Default::default();
    let mut last_rank = 0;
    let mut node_history = HashMap::new();
    for record in &req.records {
        let (rank, id) = record.entry.rank_and_key();
        if rank < last_rank {
            return Err(invalid("record order"));
        }
        last_rank = rank;
        if id != record.key || (rank <= 3 && id.is_empty()) {
            return Err(invalid(format!("invalid {} id", KINDS[rank])));
        }
        if !seen[rank].insert(id) {
            return Err(invalid(format!("duplicate {} id", KINDS[rank])));
        }
        if let Entry::LineageNode { id, history_id } = &record.entry {
            node_history.insert(id.as_str(), history_id.as_deref());
        }
    }
    if KINDS
        .iter()
        .enumerate()
        .any(|(rank, kind)| seen[rank].len() != expected[kind])
    {
        return Err(invalid("counts"));
    }

    if !(req.existing.works.is_empty()
        && req.existing.node_roots.is_empty()
        && req.existing.parents.is_empty())
    {
        // Validate the file before destination duplicates can hide a cycle.
        decide(
            &req.records,
            &Existing::default(),
            &node_history,
            expected["history"],
        )?;
    }
    decide(
        &req.records,
        &req.existing,
        &node_history,
        expected["history"],
    )
}

fn decide(
    records: &[Record],
    existing: &Existing,
    node_history: &HashMap<&str, Option<&str>>,
    history_count: usize,
) -> Check<Value> {
    let mut works = Vec::new();
    let mut accepted = HashSet::new();
    let mut imported = HashSet::new();
    for record in records {
        if let Entry::History { id, node_id } = &record.entry {
            if let Some(node) = node_id
                && node_history.get(node.as_str()) != Some(&Some(id.as_str()))
            {
                return Err(invalid("work and node do not match"));
            }
            if existing.works.contains(id)
                || node_id
                    .as_ref()
                    .is_some_and(|node| existing.node_roots.contains_key(node))
            {
                continue;
            }
            works.push(id.as_str());
            accepted.insert(id.as_str());
            imported.extend(node_id.as_deref());
        }
    }
    let mut edges = Vec::new();
    let mut parents: HashMap<&str, &str> = existing
        .parents
        .iter()
        .map(|(child, parent)| (child.as_str(), parent.as_str()))
        .collect();
    for record in records {
        if let Entry::LineageEdge { id, parent, child } = &record.entry {
            if parent == child {
                return Err(invalid("self edge"));
            }
            if imported.contains(child.as_str())
                && !parents.contains_key(child.as_str())
                && (imported.contains(parent.as_str()) || existing.node_roots.contains_key(parent))
            {
                parents.insert(child, parent);
                edges.push(id.as_str());
            }
        }
    }
    let mut roots = BTreeMap::new();
    for record in records {
        let Entry::LineageNode { id, .. } = &record.entry else {
            continue;
        };
        if !imported.contains(id.as_str()) || roots.contains_key(id.as_str()) {
            continue;
        }
        let mut path = Vec::new();
        let mut path_set = HashSet::new();
        let mut current = id.as_str();
        let root = loop {
            if let Some(&root) = roots.get(current) {
                break root;
            }
            if let Some(root) = existing.node_roots.get(current) {
                break root.as_str();
            }
            if !path_set.insert(current) {
                return Err(invalid("lineage cycle"));
            }
            path.push(current);
            let Some(&parent) = parents.get(current) else {
                break current;
            };
            current = parent;
        };
        roots.extend(
            path.into_iter()
                .filter(|node| imported.contains(node))
                .map(|node| (node, root)),
        );
    }
    let mut annotations = Vec::new();
    let mut colophons = Vec::new();
    for record in records {
        match &record.entry {
            Entry::Annotation { history_id } if accepted.contains(history_id.as_str()) => {
                annotations.push(history_id)
            }
            Entry::Colophon { id, target_node_id }
                if imported.contains(target_node_id.as_str()) =>
            {
                colophons.push(id)
            }
            _ => {}
        }
    }
    Ok(
        json!({"outcome":"ok","works":works,"node_roots":roots,"edges":edges,"annotations":annotations,
              "colophons":colophons,"skipped":history_count-works.len()}),
    )
}

pub fn plan(request: &[u8]) -> Vec<u8> {
    answer(plan_inner(request), None)
}

fn checked_encoded(value: &mut Value) -> Check<Vec<u8>> {
    // serde_json's preserve_order feature can be enabled by another host crate.
    value.sort_all_objects();
    let bytes = serde_json::to_vec(value).map_err(|_| invalid("invalid JSON object"))?;
    if bytes.len() > MAX_LINE {
        return Err(too_large());
    }
    Ok(bytes)
}

fn encode_inner(request: &[u8]) -> Check<Option<Vec<u8>>> {
    let envelope = raw_object(request)?;
    let kind: String = read(&envelope, "kind").ok_or_else(|| invalid("kind"))?;
    if kind == "header" {
        let mut line = json!({"format":"inku.workpack","format_version":1,
            "persistence_contract_version":CONTRACT.contract_version});
        for name in ["exported_at", "producer", "counts"] {
            let value: Value = read(&envelope, name).ok_or_else(|| invalid("header"))?;
            line[name] = value;
        }
        check_header(&raw_object(
            &serde_json::to_vec(&line).expect("header serializes"),
        )?)?;
        return checked_encoded(&mut line).map(Some);
    }
    if !KINDS.contains(&kind.as_str()) {
        return Err(invalid("kind"));
    }
    let record = envelope.get("record").ok_or_else(|| invalid("record"))?;
    let row = raw_object(record.get().as_bytes()).map_err(|_| invalid("record"))?;
    let common = fields(&kind).map(|fields| fields.collect::<Vec<_>>());
    for name in row.keys() {
        let allowed = match &common {
            Some(fields) => fields.iter().any(|field| field.name == *name),
            None if kind == "annotation" => ANNOTATION_FIELDS.contains(&name.as_str()),
            None => {
                COLOPHON_REQUIRED.contains(&name.as_str())
                    || COLOPHON_OPTIONAL.contains(&name.as_str())
            }
        };
        if !allowed {
            return Err(invalid(format!("unknown field {name}")));
        }
    }
    let values: serde_json::Map<String, Value> = row
        .iter()
        .map(|(name, raw)| {
            let value =
                serde_json::from_str(raw.get()).map_err(|_| invalid(format!("type {name}")))?;
            Ok((name.clone(), value))
        })
        .collect::<Check<_>>()?;
    let mut value = Value::Object(values);
    let object = value.as_object_mut().expect("validated record object");
    if let Some(fields) = common {
        for field in fields
            .iter()
            .filter(|field| field.encoding == "boolean_0_1")
        {
            if let Some(value) = object.get_mut(&field.name) {
                match value.as_str() {
                    Some("0") => *value = json!(0),
                    Some("1") => *value = json!(1),
                    _ => {}
                }
            }
        }
    }
    if kind == "annotation"
        && let Some(note) = object.get_mut("note")
        && let Some(text) = note.as_str()
    {
        let text = text.trim();
        *note = if text.is_empty() {
            Value::Null
        } else {
            json!(text)
        };
    }
    object.insert("kind".into(), json!(kind));
    let bytes = checked_encoded(&mut value)?;
    let normalized = raw_object(&bytes)?;
    validate_record(&kind, &normalized)?;
    if kind == "annotation"
        && value["note"].is_null()
        && integer(normalized["for_revision"].get()) == Some(0)
    {
        return Ok(None);
    }
    Ok(Some(bytes))
}

/// The success channel is the raw line. The other channel carries omit/refusal JSON.
pub fn encode_line(request: &[u8]) -> (Option<Vec<u8>>, Option<Vec<u8>>) {
    match encode_inner(request) {
        Ok(Some(line)) => (Some(line), None),
        Ok(None) => (None, Some(br#"{"outcome":"omit"}"#.to_vec())),
        Err(refusal) => (None, Some(answer(Err(refusal), None))),
    }
}

#[cfg(test)]
mod tests;
