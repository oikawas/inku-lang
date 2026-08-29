use std::collections::HashSet;

use inku_ddl::{
    MACRO_SEED_DOMAIN, MACRO_SEED_SCHEME_ID, MacroInvocation, MacroInvocationError,
    derive_macro_seed, macro_seed_hash_input,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/macro-seed-ddl-v1.json");

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    version: u32,
    cases: Vec<FixtureCase>,
}

#[derive(Deserialize)]
struct FixtureCase {
    id: String,
    canonical_ddl: String,
    namespace: String,
    heading: String,
    ordinal: String,
    composition_seed: Option<String>,
    expected: Expected,
}

#[derive(Deserialize)]
struct Expected {
    digest: String,
    resolved_seed: String,
}

#[test]
fn known_answers_match_the_public_ddl_v1_api() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("fixture must be valid JSON");
    assert_eq!(fixture.schema, "inku.macro-seed-ddl-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let mut ids = HashSet::new();
    for case in fixture.cases {
        assert!(
            ids.insert(case.id.clone()),
            "duplicate case ID: {}",
            case.id
        );
        assert_canonical_decimal(&case.ordinal, &case.id);
        if let Some(composition_seed) = &case.composition_seed {
            assert_canonical_decimal(composition_seed, &case.id);
        }
        assert_canonical_decimal(&case.expected.resolved_seed, &case.id);
        assert_lowercase_sha256_hex(&case.expected.digest, &case.id);

        let invocation = MacroInvocation::new(
            case.namespace,
            case.heading,
            case.ordinal.parse().expect("canonical u64 ordinal"),
        )
        .expect("fixture invocation must be valid");
        let seed = derive_macro_seed(
            &case.canonical_ddl,
            &invocation,
            case.composition_seed
                .as_deref()
                .map(|value| value.parse().expect("canonical u64 composition seed")),
        );

        assert_eq!(seed.scheme_id(), MACRO_SEED_SCHEME_ID, "{}", case.id);
        assert_eq!(
            seed.qualified_macro_name(),
            invocation.qualified_name(),
            "{}",
            case.id
        );
        assert_eq!(seed.ordinal(), invocation.ordinal(), "{}", case.id);
        assert_eq!(
            seed.effective_composition_seed().to_string(),
            case.composition_seed.unwrap_or_else(|| "0".to_owned()),
            "{}",
            case.id
        );
        assert_eq!(seed.full_digest_hex(), case.expected.digest, "{}", case.id);
        assert_eq!(
            seed.resolved_seed().to_string(),
            case.expected.resolved_seed,
            "{}",
            case.id
        );
        assert_eq!(
            hex_bytes(seed.full_digest_hex()),
            seed.full_digest_bytes(),
            "{}",
            case.id
        );
    }

    assert_required_case_coverage(&ids);
}

#[test]
fn framing_is_domain_then_five_length_prefixed_utf8_fields() {
    let invocation = MacroInvocation::new("kigo", "雲.輪", 9).unwrap();
    let bytes = macro_seed_hash_input("中央に雲を置く", &invocation, Some(4));
    let expected_fields = ["ddl-v1", "中央に雲を置く", "kigo.雲.輪", "9", "4"];

    assert!(bytes.starts_with(MACRO_SEED_DOMAIN));
    let mut remainder = &bytes[MACRO_SEED_DOMAIN.len()..];
    for field in expected_fields {
        let length = u64::from_be_bytes(remainder[..8].try_into().unwrap()) as usize;
        remainder = &remainder[8..];
        assert_eq!(length, field.len());
        assert_eq!(&remainder[..length], field.as_bytes());
        remainder = &remainder[length..];
    }
    assert!(remainder.is_empty());
    assert!(!FIXTURE.contains("\"render_seed\""));
    assert!(!FIXTURE.contains("\"source_text\""));
    assert!(!FIXTURE.contains("\"fires_on\""));
}

#[test]
fn omission_zero_and_each_explicit_input_boundary_are_distinct_as_required() {
    let invocation = MacroInvocation::new("weather", "halo", 2).unwrap();
    let omitted = derive_macro_seed("place a halo at center", &invocation, None);
    let explicit_zero = derive_macro_seed("place a halo at center", &invocation, Some(0));
    assert_eq!(omitted, explicit_zero);

    assert_ne!(
        derive_macro_seed("place a halo at center", &invocation, Some(1)),
        explicit_zero
    );
    assert_ne!(
        derive_macro_seed(
            "place a halo at center",
            &MacroInvocation::new("weather", "halo", 3).unwrap(),
            Some(0),
        ),
        explicit_zero
    );
    assert_ne!(
        derive_macro_seed(
            "place a halo at center",
            &MacroInvocation::new("sky", "halo", 2).unwrap(),
            Some(0),
        ),
        explicit_zero
    );
    assert_ne!(
        derive_macro_seed("first line\nsecond line", &invocation, Some(0)),
        derive_macro_seed("first line\r\nsecond line", &invocation, Some(0)),
    );
}

#[test]
fn invocation_validation_has_stable_error_kinds_without_normalization() {
    for namespace in ["", "1macro", "_macro", "macro/name", "日本語"] {
        assert_eq!(
            MacroInvocation::new(namespace, "heading", 0)
                .unwrap_err()
                .kind(),
            "invalid_namespace"
        );
    }
    for heading in [
        "",
        " leading",
        "trailing ",
        "line\nbreak",
        "control\u{0007}",
    ] {
        assert_eq!(
            MacroInvocation::new("macro", heading, 0)
                .unwrap_err()
                .kind(),
            "invalid_heading"
        );
    }

    let invocation = MacroInvocation::new("macro_name", "日本語.見出し", 0).unwrap();
    assert_eq!(invocation.namespace(), "macro_name");
    assert_eq!(invocation.heading(), "日本語.見出し");
    assert_eq!(invocation.qualified_name(), "macro_name.日本語.見出し");
    assert!(matches!(
        MacroInvocation::new("macro", " heading", 0),
        Err(MacroInvocationError::InvalidHeading { .. })
    ));
}

fn assert_canonical_decimal(value: &str, case_id: &str) {
    assert!(
        value == "0"
            || (!value.starts_with('0') && value.bytes().all(|byte| byte.is_ascii_digit())),
        "non-canonical decimal in {case_id}: {value}"
    );
}

fn assert_lowercase_sha256_hex(value: &str, case_id: &str) {
    assert!(
        value.len() == 64
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (byte as char).is_ascii_lowercase()),
        "invalid digest in {case_id}: {value}"
    );
}

fn hex_bytes(value: &str) -> Vec<u8> {
    (0..value.len())
        .step_by(2)
        .map(|offset| u8::from_str_radix(&value[offset..offset + 2], 16).unwrap())
        .collect()
}

fn assert_required_case_coverage(ids: &HashSet<String>) {
    for id in [
        "ja-omitted-composition",
        "ja-explicit-zero-composition",
        "en-nonzero-composition",
        "same-macro-different-ordinal",
        "different-qualified-macro",
        "unicode-exact-bytes",
        "newline-exact-bytes",
        "u64-boundary",
    ] {
        assert!(ids.contains(id), "missing required case: {id}");
    }
}
