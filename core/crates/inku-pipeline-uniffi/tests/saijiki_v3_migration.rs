use serde_json::{Value, json};

fn migrate(f: fn(Vec<u8>) -> Vec<u8>, input: Value) -> Value {
    serde_json::from_slice(&f(serde_json::to_vec(&input).unwrap())).unwrap()
}
fn document(saijiki: Option<&str>, source: &str) -> Value {
    let mut result = json!({"source":source,"language":"ja","macro_locks":[]});
    if let Some(v) = saijiki {
        result["saijiki"] = json!(v);
    }
    result
}

#[test]
fn v2_entry_returns_v3_document_and_reports_unassociated_tool() {
    let value = migrate(
        inku_pipeline_uniffi::migrate_saijiki_v2,
        json!({"document":document(Some("inku.saijiki.v2"),"鉛筆と太筆を交互にして、線を五本並べる。"),"definitions":[]}),
    );
    assert_eq!(value["schema"], "inku.saijiki-v2-migration.v1");
    assert_eq!(value["saijiki"], "inku.saijiki.v3");
    assert_eq!(
        value["document"]["document"]["source"],
        "鉛筆とガッシュを交互にして、線を五本並べる。"
    );
    assert_eq!(value["document"]["document"]["saijiki"], "inku.saijiki.v3");
    assert_eq!(
        value["document"]["unassociated_tools"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    let wrong = migrate(
        inku_pipeline_uniffi::migrate_saijiki_v2,
        json!({"document":document(None,"太筆の線を引く。"),"definitions":[]}),
    );
    assert_eq!(wrong["document"]["error"]["code"], "other_edition");
}

#[test]
fn v1_entry_produces_v3_and_v2_definition_reports_unadjusted_thinness() {
    let input = json!({"document":document(None,"太筆の薄墨の線を引く。"),"definitions":[]});
    let value = migrate(inku_pipeline_uniffi::migrate_saijiki_v1, input);
    assert_eq!(value["document"]["document"]["saijiki"], "inku.saijiki.v3");
    assert_eq!(
        value["document"]["document"]["source"],
        "太いガッシュの薄い刷きの線を引く。"
    );
    let def = json!({"schema":"inku.macro-definition.v1","namespace":"Saved","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"touch":{"expr":"cycle","index":{"expr":"integer","value":0},"items":[{"expr":"semantic_ref","category":"touch","id":"pencil"},{"expr":"semantic_ref","category":"touch","id":"brush_thick"}]}}}]});
    let value = migrate(
        inku_pipeline_uniffi::migrate_saijiki_v2,
        json!({"definitions":[def]}),
    );
    assert_eq!(
        value["definitions"][0]["definition"]["body"][0]["fields"]["touch"]["items"][1]["id"],
        "gouache"
    );
    assert_eq!(
        value["definitions"][0]["unadjusted_thinness"],
        json!(["$.body[0].fields"])
    );
}
