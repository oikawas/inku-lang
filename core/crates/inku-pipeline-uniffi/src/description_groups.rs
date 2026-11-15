//! The saved-work grouping decision, using the shared description key.
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Item {
    id: String,
    #[serde(default, deserialize_with = "present_key")]
    key: Option<String>,
    #[serde(default)]
    source_text: Option<String>,
    #[serde(default)]
    input: String,
    #[serde(default)]
    image_provenance: Option<Value>,
    #[serde(default)]
    at: Option<i64>,
    #[serde(default)]
    starred: bool,
    #[serde(default)]
    for_revision: bool,
}

fn present_key<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<Option<String>, D::Error> {
    String::deserialize(deserializer).map(Some)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    action: String,
    items: Vec<Item>,
    #[serde(default = "one")]
    min_items: usize,
    #[serde(default)]
    include_item_id: Option<String>,
    #[serde(default)]
    offset: usize,
    #[serde(default)]
    limit: Option<usize>,
}
const fn one() -> usize {
    1
}

pub fn description_groups_json(input: &[u8]) -> Vec<u8> {
    let Ok(mut request) = serde_json::from_slice::<Request>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    if request.action != "group" {
        return br#"{"error":"invalid_request"}"#.to_vec();
    }
    request
        .items
        .sort_by(|a, b| b.at.cmp(&a.at).then(a.id.cmp(&b.id)));
    let mut groups: BTreeMap<String, Vec<Item>> = BTreeMap::new();
    for item in request.items {
        if item.image_provenance.is_some() {
            continue;
        }
        let key = item.key.clone().unwrap_or_else(|| {
            super::description_labels::description_group_key(
                item.source_text.as_deref().unwrap_or(&item.input),
            )
        });
        if !key.is_empty() {
            groups.entry(key).or_default().push(item);
        }
    }
    let mut groups: Vec<Value> = groups.into_iter().filter_map(|(key, items)| {
        if items.len() < request.min_items && !items.iter().any(|item| Some(&item.id) == request.include_item_id.as_ref()) { return None; }
        Some(json!({"key": key, "anchor_id": items[0].id, "item_count": items.len(), "latest_at": items[0].at.unwrap_or(0),
            "starred_count": items.iter().filter(|item| item.starred).count(), "for_revision_count": items.iter().filter(|item| item.for_revision).count(),
            "member_ids": items.iter().map(|item| &item.id).collect::<Vec<_>>() }))
    }).collect();
    groups.sort_by(|a, b| {
        b["latest_at"]
            .as_i64()
            .cmp(&a["latest_at"].as_i64())
            .then(a["key"].as_str().cmp(&b["key"].as_str()))
    });
    let total = groups.len();
    let page: Vec<Value> = groups
        .into_iter()
        .skip(request.offset)
        .take(request.limit.unwrap_or(usize::MAX))
        .collect();
    json!({"schema": "inku.description-groups.v1", "outcome": "ok", "groups": page, "total": total})
        .to_string()
        .into_bytes()
}

#[cfg(test)]
mod tests {
    use serde_json::Value;
    #[test]
    fn names_and_description_groups_match_server_fixture() {
        let cases: Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/composition-rules-server-cases.json"
        ))
        .unwrap();
        let names: Value = serde_json::from_str(&super::super::composition_names()).unwrap();
        assert_eq!(names, cases["names"]);
        for case in cases["groups"].as_array().unwrap() {
            let result: Value = serde_json::from_slice(&super::description_groups_json(
                &serde_json::to_vec(&case["input"]).unwrap(),
            ))
            .unwrap();
            assert_eq!(result["outcome"], "ok", "{result}");
            assert_eq!(result["groups"], case["expected"]["groups"]);
            assert_eq!(result["total"], case["expected"]["total"]);
        }
        // Reuse Server's sample: b's text is snow, but its supplied rain key
        // joins c; a's explicitly empty key excludes it from grouping.
        let mut input = cases["groups"][0]["input"].clone();
        let rain_key = cases["groups"][0]["expected"]["groups"][1]["key"].clone();
        input["items"][0]["key"] = rain_key.clone();
        input["items"][1]["key"] = Value::String(String::new());
        let result: Value = serde_json::from_slice(&super::description_groups_json(
            &serde_json::to_vec(&input).unwrap(),
        ))
        .unwrap();
        assert_eq!(result["outcome"], "ok");
        assert_eq!(result["total"], 1);
        assert_eq!(result["groups"][0]["key"], rain_key);
        assert_eq!(
            result["groups"][0]["member_ids"],
            serde_json::json!(["b", "c"])
        );
        assert_eq!(result["groups"][0]["item_count"], 2);
    }
}
