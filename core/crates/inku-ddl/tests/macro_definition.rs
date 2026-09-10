use std::collections::{BTreeMap, HashSet};

use inku_ddl::{
    LEGACY_PLUGIN_FORMAT_WARNING, LegacyImportOutcome, MACRO_DEFINITION_DIGEST_DOMAIN,
    MACRO_DEFINITION_SCHEMA_ID, MacroDefinition, project_macro_semantic_ref,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const FIXTURE: &str = include_str!("fixtures/macro-definition-v1.json");
const STEP10Z_SCORE_PARITY_FIXTURE: &str =
    include_str!("fixtures/step10z-macro-score-parity-v1.json");

#[test]
fn shape_emit_fields_validate_real_categories_and_integer_type() {
    let mut value = serde_json::json!({"schema":"inku.macro-definition.v1","namespace":"Shape","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{
        "proportion_aspect":{"expr":"semantic_ref","category":"ratio","id":"wide"},
        "proportion_width_extent":{"expr":"semantic_ref","category":"ratio","id":"full_width"},
        "proportion_arc_form":{"expr":"semantic_ref","category":"ratio","id":"crescent"},
        "shape_form":{"expr":"semantic_ref","category":"shape_form","id":"regular"},
        "sides":{"expr":"integer","value":6}
    }}]});
    assert!(
        MacroDefinition::from_json(&value.to_string())
            .unwrap()
            .identity()
            .is_ok()
    );
    for (field, bad) in [
        ("sides", serde_json::json!({"expr":"number","value":6.0})),
        (
            "shape_form",
            serde_json::json!({"expr":"semantic_ref","category":"shape_form","id":"equilateral"}),
        ),
        (
            "proportion_aspect",
            serde_json::json!({"expr":"semantic_ref","category":"color","id":"red"}),
        ),
        (
            "proportion_width_extent",
            serde_json::json!({"expr":"semantic_ref","category":"color","id":"red"}),
        ),
        (
            "proportion_arc_form",
            serde_json::json!({"expr":"semantic_ref","category":"color","id":"red"}),
        ),
    ] {
        let old = value["body"][0]["fields"][field].clone();
        value["body"][0]["fields"][field] = bad;
        assert!(
            MacroDefinition::from_json(&value.to_string())
                .unwrap()
                .identity()
                .is_err(),
            "{field}"
        );
        value["body"][0]["fields"][field] = old;
    }
}

#[test]
fn step10z_score_parity_fixture_definitions_are_valid_declared_macros() {
    let fixture: Value = serde_json::from_str(STEP10Z_SCORE_PARITY_FIXTURE).unwrap();
    assert_eq!(
        fixture["schema"],
        Value::String("inku.step10z-macro-score-parity-v1".to_owned())
    );
    assert_eq!(fixture["version"], Value::from(1));
    let cases = fixture["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 3);
    for case in cases {
        assert!(case["ordinary_source"].is_string());
        assert!(case["macro_source"].is_string());
        let definition = MacroDefinition::from_json(&case["macro_definition"].to_string())
            .unwrap_or_else(|error| panic!("{}: {error}", case["id"]));
        assert!(
            definition.identity().is_ok(),
            "{}: {:?}",
            case["id"],
            definition.validate().diagnostics()
        );
    }
}

#[test]
fn layout_direction_emit_maps_to_existing_angle_category_only() {
    let mut value = serde_json::json!({"schema":"inku.macro-definition.v1", "namespace":"Axis", "heading":"Line", "version":"1.0.0", "parameters":{}, "components":{}, "body":[{"op":"emit","binding":null,"fields":{
        "layout_direction":{"expr":"semantic_ref","category":"angle","id":"vertical"},
        "angle":{"expr":"semantic_ref","category":"angle","id":"horizontal"},
        "count":{"expr":"integer","value":3}
    }}]});
    let definition = MacroDefinition::from_json(&value.to_string()).unwrap();
    assert!(definition.identity().is_ok());
    value["body"][0]["fields"]["layout_direction"]["category"] = Value::String("color".to_owned());
    value["body"][0]["fields"]["layout_direction"]["id"] = Value::String("red".to_owned());
    assert!(
        MacroDefinition::from_json(&value.to_string())
            .unwrap()
            .identity()
            .is_err()
    );
}

#[test]
fn fluctuation_dimension_preserves_legacy_identity_and_checks_known_constraints() {
    let legacy = serde_json::json!({
        "schema":"inku.macro-definition.v1", "namespace":"Sway", "heading":"Mark", "version":"1.0.0",
        "parameters":{"token":{"type":"semantic_ref","category":"variation"}}, "components":{},
        "body":[{"op":"emit","binding":null,"fields":{"variation":{"expr":"parameter","name":"token"}}}]
    });
    let parse = |data: &Value| MacroDefinition::from_json(&data.to_string()).unwrap();
    let original = parse(&legacy);
    let original_bytes = original.canonical_json_bytes().unwrap();
    assert!(
        !std::str::from_utf8(&original_bytes)
            .unwrap()
            .contains("dimension")
    );
    let mut explicit_none = legacy.clone();
    explicit_none["parameters"]["token"]["dimension"] = Value::Null;
    assert_eq!(
        parse(&explicit_none).canonical_json_bytes().unwrap(),
        original_bytes
    );
    assert_eq!(
        parse(&explicit_none).identity().unwrap(),
        original.identity().unwrap()
    );
    let mut constrained = legacy.clone();
    constrained["parameters"]["token"]["dimension"] = serde_json::json!("amplitude");
    assert!(parse(&constrained).validate().is_valid());
    assert_ne!(
        parse(&constrained).identity().unwrap(),
        original.identity().unwrap()
    );
    constrained["parameters"]["token"]["category"] = serde_json::json!("color");
    assert!(!parse(&constrained).validate().is_valid());
    constrained["parameters"]["token"]["dimension"] = serde_json::json!("unknown");
    assert!(MacroDefinition::from_json(&constrained.to_string()).is_err());

    for (dimension, valid, invalid) in [
        ("amplitude", "large", "slowly"),
        ("frequency", "quickly", "trembling"),
        ("quality", "blurring", "fine"),
    ] {
        let field = format!("fluctuation_{dimension}");
        let mut data = legacy.clone();
        data["parameters"]["token"]["dimension"] = serde_json::json!(dimension);
        data["body"][0]["fields"] = serde_json::json!({&field:{"expr":"parameter","name":"token"}});
        assert!(parse(&data).validate().is_valid());
        for (id, expected) in [(valid, true), (invalid, false), ("unknown", false)] {
            data["body"][0]["fields"][&field] =
                serde_json::json!({"expr":"semantic_ref","category":"variation","id":id});
            assert_eq!(
                parse(&data).validate().is_valid(),
                expected,
                "{dimension}: {id}"
            );
        }
        data["body"][0]["fields"][&field] = serde_json::json!({"expr":"integer","value":1});
        assert!(!parse(&data).validate().is_valid());
        data["components"] = serde_json::json!({"part":{"parameters":{"other":{"type":"semantic_ref","category":"variation","dimension":dimension}}, "body":[]}});
        for (id, expected) in [(valid, true), (invalid, false)] {
            data["body"] = serde_json::json!([{"op":"use","component":"part","arguments":{"other":{"expr":"semantic_ref","category":"variation","id":id}}}]);
            assert_eq!(
                parse(&data).validate().is_valid(),
                expected,
                "use {dimension}: {id}"
            );
        }
    }
}

#[test]
fn all_finite_core_values_validate_only_their_own_category_and_field() {
    use inku_ddl::CoreModifierValue::*;
    for value in [
        Fine,
        ExtraFine,
        SlightlySmall,
        Small,
        VerySmall,
        Normal,
        SlightlyLarge,
        Large,
        VeryLarge,
    ] {
        let category = value.dimension().as_str();
        assert_eq!(
            inku_ddl::CoreModifierValue::from_semantic_ref(category, value.as_str()),
            Some(value)
        );
        let other = if category == "thinness" {
            "relative_scale"
        } else {
            "thinness"
        };
        assert_eq!(
            inku_ddl::CoreModifierValue::from_semantic_ref(other, value.as_str()),
            None
        );
        let mut data = serde_json::json!({
            "schema":"inku.macro-definition.v1", "namespace":"Core", "heading":"Value", "version":"1.0.0",
            "parameters":{"value":{"type":"semantic_ref","category":category}}, "components":{},
            "body":[{"op":"emit","binding":null,"fields":{category:{"expr":"semantic_ref","category":category,"id":value.as_str()}}},
                    {"op":"emit","binding":null,"fields":{category:{"expr":"parameter","name":"value"}}}]
        });
        assert!(
            MacroDefinition::from_json(&data.to_string())
                .unwrap()
                .validate()
                .is_valid()
        );
        data["body"][0]["fields"][category]["id"] = serde_json::json!("unknown");
        assert!(
            !MacroDefinition::from_json(&data.to_string())
                .unwrap()
                .validate()
                .is_valid()
        );
    }
    assert_eq!(
        inku_ddl::CoreModifierValue::from_semantic_ref("size", "normal"),
        None
    );
}

#[test]
fn central_place_rows_share_one_typed_semantic_identity() {
    let central = project_macro_semantic_ref("basho", "中央").unwrap();
    let middle = project_macro_semantic_ref("basho", "中心").unwrap();

    assert_eq!(central.category, "place");
    assert_eq!(middle.category, "place");
    assert_eq!(central.canonical_id, "center");
    assert_eq!(middle.canonical_id, "center");
}

#[test]
fn lexical_place_ids_remain_valid_inputs_but_share_canonical_definition_identity() {
    let definition = |id: &str| {
        MacroDefinition::from_json(
            &serde_json::json!({
                "schema": "inku.macro-definition.v1",
                "namespace": "Alias",
                "heading": "Place",
                "version": "1.0.0",
                "parameters": {},
                "components": {},
                "body": [{
                    "op": "emit",
                    "binding": null,
                    "fields": {
                        "place": {"expr": "semantic_ref", "category": "place", "id": id}
                    }
                }]
            })
            .to_string(),
        )
        .unwrap()
    };
    let center = definition("center");
    let middle = definition("middle");

    assert!(serde_json::to_string(&middle).unwrap().contains("middle"));
    assert_eq!(
        middle.canonical_json_bytes().unwrap(),
        center.canonical_json_bytes().unwrap()
    );
    assert_eq!(
        middle.identity().unwrap().full_digest_hex(),
        center.identity().unwrap().full_digest_hex()
    );
    assert!(
        !std::str::from_utf8(&middle.canonical_json_bytes().unwrap())
            .unwrap()
            .contains("middle")
    );
}

#[test]
fn closed_core_thinness_refs_validate_for_literals_and_component_parameters() {
    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"ThinnessPair","version":"1.0.0","parameters":{},"components":{"mark":{"parameters":{"width":{"type":"semantic_ref","category":"thinness"}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"thinness":{"expr":"parameter","name":"width"}}}]}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"thinness":{"expr":"semantic_ref","category":"thinness","id":"fine"}}},{"op":"use","component":"mark","arguments":{"width":{"expr":"semantic_ref","category":"thinness","id":"extra_fine"}}}]}"#,
    )
    .unwrap();
    let validation = definition.validate();
    assert!(validation.is_valid(), "{:?}", validation.diagnostics());
    assert_eq!(validation.symbolic_upper_bound(), Some(2));
    let canonical_bytes = definition.canonical_json_bytes().unwrap();
    let canonical = std::str::from_utf8(&canonical_bytes).unwrap();
    assert!(canonical.contains(r#""category":"thinness","id":"fine""#));
    assert!(canonical.contains(r#""category":"thinness","id":"extra_fine""#));

    for (category, id, expected_code) in [
        ("thinness", "normal", "unknown_semantic_id"),
        (
            "relative_scale",
            "small",
            "semantic_field_requires_matching_reference",
        ),
    ] {
        let invalid = MacroDefinition::from_json(
            &serde_json::json!({
                "schema": "inku.macro-definition.v1",
                "namespace": "Bad",
                "heading": "Thinness",
                "version": "1.0.0",
                "parameters": {},
                "components": {},
                "body": [{
                    "op": "emit",
                    "binding": null,
                    "fields": {
                        "thinness": {"expr": "semantic_ref", "category": category, "id": id}
                    }
                }]
            })
            .to_string(),
        )
        .unwrap();
        assert!(
            invalid.validate().has_code(expected_code),
            "{category}:{id}"
        );
    }
}

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    version: u32,
    definitions: BTreeMap<String, Value>,
    valid_cases: Vec<ValidCase>,
    invalid_cases: Vec<InvalidCase>,
}

#[derive(Deserialize)]
struct ValidCase {
    id: String,
    definition: String,
    alternate_input_json: Option<String>,
    expected_canonical_json: String,
    expected_digest: String,
    expected_qualified_name: String,
    expected_version: String,
    expected_upper_bound: u64,
}

#[derive(Deserialize)]
struct InvalidCase {
    id: String,
    input_json: String,
    expected_code: String,
}

#[test]
fn shared_known_answers_match_typed_canonical_identity_and_resource_bounds() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("fixture must be valid JSON");
    assert_eq!(fixture.schema, "inku.macro-definition-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));
    assert_eq!(MACRO_DEFINITION_SCHEMA_ID, "inku.macro-definition.v1");
    assert_eq!(MACRO_DEFINITION_DIGEST_DOMAIN, b"inku.macro-definition.v1");

    let mut ids = HashSet::new();
    let mut digests = BTreeMap::new();
    for case in &fixture.valid_cases {
        assert!(
            ids.insert(case.id.clone()),
            "duplicate case ID: {}",
            case.id
        );
        assert_lowercase_digest(&case.expected_digest, &case.id);
        let source = serde_json::to_string(
            fixture
                .definitions
                .get(&case.definition)
                .expect("known definition reference"),
        )
        .unwrap();
        assert_valid_case(case, &source);
        if let Some(alternate) = &case.alternate_input_json {
            assert_valid_case(case, alternate);
        }
        digests.insert(case.id.as_str(), case.expected_digest.as_str());
    }
    assert_ne!(
        digests["all-operators-ja-component-reuse-bounded-vary-touch-surface"],
        digests["digest-sensitivity-version"]
    );
}

#[test]
fn invalid_fixture_cases_are_rejected_with_stable_codes() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("fixture must be valid JSON");
    let mut ids = HashSet::new();
    for case in &fixture.invalid_cases {
        assert!(
            ids.insert(case.id.clone()),
            "duplicate case ID: {}",
            case.id
        );
        match MacroDefinition::from_json(&case.input_json) {
            Err(error) => assert_eq!(error.code(), case.expected_code, "{}", case.id),
            Ok(definition) => {
                let validation = definition.validate();
                assert!(
                    validation.has_code(&case.expected_code),
                    "{}: expected {}, got {:?}",
                    case.id,
                    case.expected_code,
                    validation
                        .diagnostics()
                        .iter()
                        .map(|diagnostic| (diagnostic.code(), diagnostic.path()))
                        .collect::<Vec<_>>()
                );
                assert!(definition.canonical_json_bytes().is_err(), "{}", case.id);
            }
        }
    }
    assert_required_invalid_coverage(&ids);
}

#[test]
fn legacy_import_and_omission_are_nonfatal_per_macro_warning_outcomes() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).unwrap();
    let source = serde_json::to_string(&fixture.definitions["key-order-whitespace"]).unwrap();
    let definition = MacroDefinition::from_json(&source).unwrap();
    let imported = LegacyImportOutcome::imported(definition).unwrap();
    let omitted = LegacyImportOutcome::omitted("legacy.unconvertible", "unsupported_entry");

    for outcome in [&imported, &omitted] {
        assert_eq!(outcome.warnings().len(), 1);
        assert_eq!(outcome.warnings()[0].code(), LEGACY_PLUGIN_FORMAT_WARNING);
    }
    assert!(matches!(imported, LegacyImportOutcome::Imported { .. }));
    assert!(matches!(omitted, LegacyImportOutcome::Omitted { .. }));
}

fn assert_valid_case(case: &ValidCase, source: &str) {
    let definition = MacroDefinition::from_json(source).unwrap_or_else(|error| {
        panic!("{} parse failed: {error}", case.id);
    });
    let validation = definition.validate();
    assert!(
        validation.is_valid(),
        "{}: {:?}",
        case.id,
        validation
            .diagnostics()
            .iter()
            .map(|diagnostic| (diagnostic.code(), diagnostic.path()))
            .collect::<Vec<_>>()
    );
    assert_eq!(
        validation.symbolic_upper_bound(),
        Some(case.expected_upper_bound),
        "{}",
        case.id
    );

    let identity = definition.identity().unwrap();
    assert_eq!(
        identity.canonical_json_bytes(),
        case.expected_canonical_json.as_bytes(),
        "{}",
        case.id
    );
    assert!(!identity.canonical_json_bytes().ends_with(b"\n"));
    assert_eq!(identity.qualified_name(), case.expected_qualified_name);
    assert_eq!(identity.version(), case.expected_version);
    assert_eq!(identity.full_digest_hex(), case.expected_digest);
    let expected_digest: [u8; 32] = Sha256::digest(
        [
            MACRO_DEFINITION_DIGEST_DOMAIN,
            &(identity.canonical_json_bytes().len() as u64).to_be_bytes(),
            identity.canonical_json_bytes(),
        ]
        .concat(),
    )
    .into();
    assert_eq!(identity.full_digest_bytes(), &expected_digest);
}

fn assert_lowercase_digest(value: &str, case_id: &str) {
    assert!(
        value.len() == 64
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f')),
        "invalid digest in {case_id}: {value}"
    );
}

fn assert_required_invalid_coverage(ids: &HashSet<String>) {
    for required in [
        "domain-specific-operator",
        "unknown-semantic-id",
        "filled-authoring-field",
        "wild-host-option",
        "wild-semantic-reference",
        "raw-score",
        "raw-svg",
        "renderer-instruction",
        "external-use",
        "component-cycle",
        "undefined-anchor",
        "undefined-parameter",
        "unbounded-repeat",
        "empty-vary",
        "non-finite-number",
        "duplicate-anchor",
    ] {
        assert!(
            ids.contains(required),
            "missing invalid coverage: {required}"
        );
    }
}
