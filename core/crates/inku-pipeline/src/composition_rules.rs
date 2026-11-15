//! Host-neutral composition ancestry and derivation decisions.
use std::collections::{BTreeMap, HashMap, HashSet};

use serde::Deserialize;
use serde_json::{Value, json};

const KEEPING: &[&str] = &[
    "replay",
    "tool_change",
    "ground_change",
    "catalog_change",
    "color_arrangement_change",
    "canvas_fit",
    "layout_change",
    "chunk_move",
    "touch_change",
];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Node {
    node_id: String,
    history_id: Option<String>,
    #[serde(default)]
    at: Value,
    #[serde(default)]
    state: Option<String>,
    readable: bool,
    edge_readable: bool,
    #[serde(default)]
    parent_node_id: Option<String>,
    #[serde(default)]
    derivation_kind: Option<String>,
    #[serde(default)]
    ddl: Option<String>,
    #[serde(default)]
    composition: Option<Value>,
    #[serde(default)]
    metadata: Value,
}
#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
enum Request {
    Walk {
        start: String,
        nodes: Vec<Node>,
    },
    Metadata {
        derivation_kind: String,
        settings: Value,
        parent_answer: Value,
        fork_kind: Option<String>,
        candidate: CandidateFacts,
    },
}

/// Host-supplied facts: I/O and ownership remain the host's responsibility.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CandidateFacts {
    ready: bool,
    parent_matches: bool,
    history_found: bool,
    description_locked: bool,
    requested_parent_node_id: String,
}

fn walk(start: &str, nodes: &[Node]) -> Value {
    let by_id: HashMap<&str, &Node> = nodes.iter().map(|n| (n.node_id.as_str(), n)).collect();
    if by_id
        .get(start)
        .and_then(|node| node.composition.as_ref())
        .is_some_and(Value::is_object)
    {
        return json!({"composition_inherited": null, "places": []});
    }
    let mut seen = HashSet::new();
    let mut places: BTreeMap<i128, (Value, String)> = BTreeMap::new();
    let mut current = start;
    let mut via: Vec<&str> = Vec::new();
    while seen.insert(current) {
        let Some(child) = by_id.get(current) else {
            break;
        };
        let Some(kind) = child.derivation_kind.as_deref() else {
            break;
        };
        if !child.edge_readable || !KEEPING.contains(&kind) {
            break;
        }
        let Some(parent) = child.parent_node_id.as_deref().and_then(|id| by_id.get(id)) else {
            break;
        };
        let Some(history_id) = parent.history_id.as_ref().filter(|id| !id.is_empty()) else {
            break;
        };
        if parent.state.as_deref() == Some("tombstone") || !parent.readable {
            break;
        }
        if kind == "replay" {
            let normalized = |s: &str| {
                s.split(crate::identity::is_python_space)
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>()
                    .join(" ")
            };
            let child_ddl = child
                .ddl
                .as_deref()
                .map(normalized)
                .filter(|s| !s.is_empty());
            let parent_ddl = parent
                .ddl
                .as_deref()
                .map(normalized)
                .filter(|s| !s.is_empty());
            if child_ddl.is_none() || child_ddl != parent_ddl {
                break;
            }
        }
        if kind == "layout_change" {
            let place = &child.metadata["place"];
            let number = &place["thing"];
            let thing = number
                .as_i64()
                .map(i128::from)
                .or_else(|| number.as_u64().map(i128::from))
                .or_else(|| number.as_bool().map(i128::from));
            if let (Some(thing), Some(at)) = (thing, place["at"].as_str()) {
                places
                    .entry(thing)
                    .or_insert_with(|| (number.clone(), at.to_owned()));
            }
        }
        via.push(kind);
        if let Some(record) = parent.composition.as_ref().filter(|v| v.is_object()) {
            let Some(answer) = record.get("answer").filter(|v| v.is_object()) else {
                break;
            };
            let mut inherited =
                json!({"history_id": history_id, "at": parent.at, "via": via, "answer": answer});
            for name in ["requested_form", "requested_main_law", "requested_thesis"] {
                if let Some(value) = record.get(name).filter(|v| !v.is_null()) {
                    inherited[name] = value.clone();
                }
            }
            let moved: Vec<Value> = places
                .values()
                .map(|(thing, at)| json!({"thing": thing, "at": at}))
                .collect();
            if !moved.is_empty() {
                inherited["places"] = json!(moved);
            }
            return json!({"composition_inherited": inherited, "places": moved});
        }
        current = &parent.node_id;
    }
    json!({"composition_inherited": null, "places": []})
}

fn metadata(
    kind: &str,
    settings: &Value,
    parent: &Value,
    fork_kind: Option<&str>,
    facts: &CandidateFacts,
) -> Result<Value, &'static str> {
    let get = |name: &str| settings.get(name).cloned().unwrap_or(Value::Null);
    if get("save_history") != Value::Bool(false) {
        return Err("execution_already_saved");
    }
    if !facts.ready {
        return Err("candidate_not_ready");
    }
    if get("derivation_kind").as_str() != Some(kind) {
        return Err("invalid_candidate");
    }
    if kind == "layout_change" {
        let place = get("derivation_metadata")
            .get("place")
            .cloned()
            .unwrap_or(Value::Null);
        if !matches!(fork_kind, Some("variation_ddl_fork" | "legacy_ddl_fork"))
            || !place.is_object()
        {
            return Err("invalid_candidate");
        }
    }
    if kind == "composition_form_change"
        && get("composition_form").is_null()
        && get("composition_main_law").is_null()
        && get("composition_thesis").is_null()
    {
        return Err("invalid_candidate");
    }
    if get("lineage_parent_node_id").as_str() != Some(facts.requested_parent_node_id.as_str()) {
        return Err("candidate_parent_mismatch");
    }
    if !facts.history_found {
        return Err("history_not_found");
    }
    if !facts.parent_matches {
        return Err("candidate_parent_mismatch");
    }
    if kind != "layout_change" && facts.description_locked {
        return Err("description_locked");
    }
    if kind == "layout_change" {
        let place = get("derivation_metadata")
            .get("place")
            .cloned()
            .unwrap_or(Value::Null);
        return Ok(
            json!({"place": {"title": place["title"], "thing": place["thing"], "at_from": place["at_from"], "at": place["at"]}}),
        );
    }
    if kind == "model_comparison" {
        return Ok(
            json!({"comparison_mode": "common", "compared_model": get("stage1_model"), "stage1_model": get("stage1_model"), "stage2_model": get("stage2_model")}),
        );
    }
    if kind != "composition_form_change"
        || (get("composition_form").is_null()
            && get("composition_main_law").is_null()
            && get("composition_thesis").is_null())
    {
        return Err("invalid_candidate");
    }
    if !get("composition_thesis").is_null() {
        let source = settings
            .get("composition_thesis_source")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .unwrap_or("author");
        let mut result = json!({"thesis_from": parent["thesis"], "thesis_to": get("composition_thesis"), "thesis_source": source});
        if source == "proposed" {
            result["thesis_prompt_digest"] = get("composition_thesis_prompt_digest");
        }
        return Ok(result);
    }
    if !get("composition_main_law").is_null() {
        return Ok(
            json!({"main_law_from": parent["main_law"], "main_law_to": get("composition_main_law"), "form": get("composition_form")}),
        );
    }
    Ok(json!({"form_from": parent["form"], "form_to": get("composition_form")}))
}

/// JSON entry for ancestry walks and candidate derivation metadata.
#[must_use]
pub fn composition_rules_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<Request>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let result = match request {
        Request::Walk { start, nodes } => Ok(walk(&start, &nodes)),
        Request::Metadata {
            derivation_kind,
            settings,
            parent_answer,
            fork_kind,
            candidate,
        } => metadata(
            &derivation_kind,
            &settings,
            &parent_answer,
            fork_kind.as_deref(),
            &candidate,
        )
        .map(|metadata| json!({"metadata": metadata})),
    };
    match result {
        Ok(value) => {
            json!({"schema": "inku.composition-rules.v1", "outcome": "ok", "result": value})
                .to_string()
                .into_bytes()
        }
        Err(reason) => {
            json!({"schema": "inku.composition-rules.v1", "outcome": "refused", "reason": reason})
                .to_string()
                .into_bytes()
        }
    }
}
