use super::*;

const FIXTURE: &str = include_str!("../../../../../persistence/fixtures/workpack-minimal.inkupack");

fn as_json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).unwrap()
}

fn fixture_plan() -> Value {
    let lines = FIXTURE.lines();
    let mut records = Vec::new();
    let mut counts = Value::Null;
    for (index, line) in lines.enumerate() {
        let mut result = as_json(&read_line(line.as_bytes(), (index + 1) as u64));
        if index == 0 {
            assert_eq!(result["outcome"], "header");
            counts = result["counts"].take();
        } else {
            assert_eq!(result["outcome"], "record");
            result.as_object_mut().unwrap().remove("outcome");
            records.push(result);
        }
    }
    json!({"action":"plan","counts":counts,"records":records,"existing":{}})
}

fn encode(request: Value) -> (Option<Vec<u8>>, Option<Vec<u8>>) {
    encode_line(&serde_json::to_vec(&request).unwrap())
}

fn decide(request: &Value) -> Value {
    as_json(&plan(&serde_json::to_vec(request).unwrap()))
}

#[test]
fn fixture_rows_round_trip_in_canonical_key_order() {
    let mut originally_canonical = 0;
    for (index, raw) in FIXTURE.lines().enumerate() {
        let mut expected = as_json(raw.as_bytes());
        let request = if index == 0 {
            json!({"kind":"header","exported_at":expected["exported_at"],"producer":expected["producer"],"counts":expected["counts"]})
        } else {
            let mut record = expected.clone();
            let kind = record.as_object_mut().unwrap().remove("kind").unwrap();
            json!({"kind":kind,"record":record})
        };
        let (line, error) = encode(request);
        assert!(error.is_none(), "{error:?}");
        let line = line.unwrap();
        expected.sort_all_objects();
        assert_eq!(line, serde_json::to_vec(&expected).unwrap());
        assert_eq!(
            read_line(&line, (index + 1) as u64),
            read_line(raw.as_bytes(), (index + 1) as u64)
        );
        if index != 0 && line == raw.as_bytes() {
            originally_canonical += 1;
        }
    }
    // The checked-in fixture predates canonical ordering. Verify the known
    // byte difference without changing the interoperability input.
    assert_eq!(originally_canonical, 0);
}

#[test]
fn new_duplicate_and_partial_graphs_choose_records_in_file_order() {
    let mut request = fixture_plan();
    assert_eq!(
        decide(&request),
        json!({
            "outcome":"ok","works":["work-0","work-1","work-2"],
            "node_roots":{"node-0":"node-0","node-1":"node-0","node-2":"node-0"},
            "edges":["edge-1","edge-2"],"annotations":["work-1"],"colophons":["colophon-1"],"skipped":0
        })
    );
    request["existing"] = json!({"works":["work-0","work-1","work-2"],
        "node_roots":{"node-0":"node-0","node-1":"node-0","node-2":"node-0"}, "parents":{}});
    assert_eq!(
        decide(&request),
        json!({"outcome":"ok","works":[],"node_roots":{},
        "edges":[],"annotations":[],"colophons":[],"skipped":3})
    );

    request["existing"] =
        json!({"works":["work-0"],"node_roots":{"node-0":"existing-root"}, "parents":{}});
    let result = decide(&request);
    assert_eq!(
        result["node_roots"],
        json!({"node-1":"existing-root","node-2":"existing-root"})
    );
    assert_eq!(result["edges"], json!(["edge-1", "edge-2"]));
    request["existing"] = json!({"works":["work-0"],"node_roots":{},"parents":{}});
    let result = decide(&request);
    assert_eq!(
        result["node_roots"],
        json!({"node-1":"node-1","node-2":"node-1"})
    );
    assert_eq!(result["edges"], json!(["edge-2"]));
    request["existing"] =
        json!({"works":["work-0"],"node_roots":{"node-1":"existing-root"},"parents":{}});
    let result = decide(&request);
    assert_eq!(result["works"], json!(["work-2"]));
    assert_eq!(result["annotations"], json!([]));
    assert_eq!(result["colophons"], json!(["colophon-1"]));
}

#[test]
fn corrupt_pack_refuses_counts_order_duplicates_mismatches_and_cycles() {
    let original = fixture_plan();
    let mut request = original.clone();
    request["counts"]["history"] = json!(2);
    assert_eq!(decide(&request)["reason"], "counts");
    request = original.clone();
    request["records"].as_array_mut().unwrap().swap(0, 3);
    assert_eq!(decide(&request)["reason"], "record order");
    for (first, next, kind) in [
        (0, 1, "history"),
        (3, 4, "lineage_node"),
        (6, 7, "lineage_edge"),
        (8, 8, "annotation"),
        (9, 9, "colophon"),
    ] {
        request = original.clone();
        let duplicate = request["records"][first].clone();
        if first == next {
            request["records"]
                .as_array_mut()
                .unwrap()
                .insert(next, duplicate);
        } else {
            request["records"][next] = duplicate;
        }
        assert_eq!(decide(&request)["reason"], format!("duplicate {kind} id"));
    }
    request = original.clone();
    request["records"][3]["identity"]["history_id"] = json!("other");
    assert_eq!(decide(&request)["reason"], "work and node do not match");
    request = original.clone();
    request["records"][6]["identity"]["parent"] = json!("node-1");
    assert_eq!(decide(&request)["reason"], "self edge");
    request["records"][6]["identity"]["parent"] = json!("node-2");
    assert_eq!(decide(&request)["reason"], "lineage cycle");
    request["existing"] = json!({"works":["work-1"],"node_roots":{"node-1":"node-1"}});
    assert_eq!(decide(&request)["reason"], "lineage cycle");
}

#[test]
fn refuses_malformed_nested_json_types_and_newer_version() {
    let mut header = as_json(FIXTURE.lines().next().unwrap().as_bytes());
    header["format_version"] = json!(2);
    assert_eq!(
        as_json(&read_line(&serde_json::to_vec(&header).unwrap(), 1))["code"],
        "newer_version"
    );
    assert_eq!(as_json(&read_line(b"{", 2))["reason"], "line 2");
    assert_eq!(
        as_json(&read_line(br#"{"kind":"future","value":123}"#, 2))["outcome"],
        "unknown_kind"
    );
    let mut row = as_json(FIXTURE.lines().nth(1).unwrap().as_bytes());
    row.as_object_mut().unwrap().remove("score");
    assert_eq!(
        as_json(&read_line(&serde_json::to_vec(&row).unwrap(), 2))["reason"],
        "missing score"
    );
    row["score"] = json!("[]");
    assert_eq!(
        as_json(&read_line(&serde_json::to_vec(&row).unwrap(), 2))["reason"],
        "type score"
    );
    let bad = FIXTURE.lines().nth(1).unwrap().replace("work 0", r"\ud800");
    assert_eq!(
        as_json(&read_line(bad.as_bytes(), 2))["reason"],
        "type input"
    );
    row["score"] = json!("{}");
    row["render_wild"] = json!("1");
    assert_eq!(
        as_json(&read_line(&serde_json::to_vec(&row).unwrap(), 2))["reason"],
        "type render_wild"
    );
    row.as_object_mut().unwrap().remove("kind");
    let (line, _) = encode(json!({"kind":"history","record":row}));
    assert_eq!(as_json(&line.unwrap())["render_wild"], 1);
}

#[test]
fn normalizes_annotations_and_refuses_nonportable_fields() {
    let (line, error) = encode(
        json!({"kind":"annotation","record":{"history_id":"a","note":"  ","for_revision":0}}),
    );
    assert!(line.is_none());
    assert_eq!(as_json(&error.unwrap())["outcome"], "omit");
    let (line, _) = encode(
        json!({"kind":"annotation","record":{"history_id":"a","note":" 日本語 / ","for_revision":1}}),
    );
    assert_eq!(
        line.unwrap(),
        "{\"for_revision\":1,\"history_id\":\"a\",\"kind\":\"annotation\",\"note\":\"日本語 /\"}"
            .as_bytes()
    );
    let note = "👩‍🎨".repeat(240);
    assert!(
        encode(
            json!({"kind":"annotation","record":{"history_id":"a","note":note,"for_revision":1}})
        )
        .0
        .is_some()
    );
    assert_eq!(as_json(&encode(json!({"kind":"annotation","record":{"history_id":"a","note":"👩‍🎨".repeat(241),"for_revision":1}})).1.unwrap())["reason"], "annotation");
    assert_eq!(as_json(&encode(json!({"kind":"annotation","record":{"history_id":"a","note":null,"for_revision":1,"for_share":1}})).1.unwrap())["reason"], "unknown field for_share");
}

#[test]
fn embedded_common_fields_use_supported_encodings() {
    for kind in KINDS {
        if let Some(fields) = fields(kind) {
            for field in fields {
                assert!(
                    valid_encoding(&field.encoding, "0").is_some(),
                    "{kind}.{}",
                    field.name
                );
            }
        }
    }
}

#[test]
fn oversized_line_is_refused_before_decoding() {
    let oversized = vec![b'x'; MAX_LINE + 1];
    assert_eq!(
        as_json(&read_line(&oversized, 2)),
        json!({
            "outcome":"refused","code":"too_large","reason":"too_large","line":2
        })
    );
}
