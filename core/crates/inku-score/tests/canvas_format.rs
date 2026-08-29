use std::collections::HashSet;

use inku_score::{
    CANVAS_FORMAT_REGISTRY, CANVAS_FORMAT_REGISTRY_DIGEST_DOMAIN, CANVAS_FORMAT_REGISTRY_ID,
    CanvasFormat, CanvasFormatRegistryValidationError, DEFAULT_CANVAS_FORMAT_ID,
    UNKNOWN_CANVAS_FORMAT_ERROR_CODE, canvas_format_registry,
    canvas_format_registry_canonical_json_bytes, canvas_format_registry_digest,
    lookup_canvas_format, validate_canvas_format_id, validate_canvas_format_registry,
};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Fixture {
    schema: String,
    version: u32,
    registry_id: String,
    default: String,
    formats: Vec<FixtureFormat>,
    expected_canonical_json: String,
    expected_digest: String,
    new_presentations: Vec<NewPresentation>,
}

#[derive(Debug, Deserialize)]
struct FixtureFormat {
    id: String,
    width_units: u32,
    height_units: u32,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
struct NewPresentation {
    id: String,
    label: String,
}

fn fixture() -> Fixture {
    serde_json::from_str(include_str!("fixtures/canvas-format-registry-v1.json"))
        .expect("canvas format fixture must parse")
}

#[test]
fn canonical_registry_has_exact_order_values_and_lookup_behavior() {
    let fixture = fixture();
    assert_eq!(fixture.schema, "inku.canvas-format-registry-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.registry_id, CANVAS_FORMAT_REGISTRY_ID);
    assert_eq!(fixture.default, DEFAULT_CANVAS_FORMAT_ID);
    assert_eq!(canvas_format_registry(), CANVAS_FORMAT_REGISTRY);
    assert_eq!(CANVAS_FORMAT_REGISTRY.len(), 11);
    assert_eq!(fixture.formats.len(), CANVAS_FORMAT_REGISTRY.len());

    let mut ids = HashSet::new();
    for (ordinal, (actual, expected)) in CANVAS_FORMAT_REGISTRY
        .iter()
        .zip(&fixture.formats)
        .enumerate()
    {
        assert_eq!(actual.id, expected.id, "ordinal {ordinal} ID");
        assert_eq!(
            actual.width_units, expected.width_units,
            "ordinal {ordinal} width"
        );
        assert_eq!(
            actual.height_units, expected.height_units,
            "ordinal {ordinal} height"
        );
        assert!(actual.width_units > 0 && actual.height_units > 0);
        assert!(ids.insert(actual.id));
        assert_eq!(lookup_canvas_format(actual.id), Ok(actual));
        assert_eq!(validate_canvas_format_id(actual.id), Ok(()));
    }

    assert_eq!(
        lookup_canvas_format(DEFAULT_CANVAS_FORMAT_ID).unwrap().id,
        "square"
    );
    for unknown in [
        "SQUARE",
        " square",
        "square ",
        "pixel9_landscape_safe",
        "unknown",
    ] {
        let error = lookup_canvas_format(unknown).unwrap_err();
        assert_eq!(error.code(), UNKNOWN_CANVAS_FORMAT_ERROR_CODE);
        assert_eq!(error.to_string(), "unknown_canvas_format");
    }
    assert_eq!(
        validate_canvas_format_registry(CANVAS_FORMAT_REGISTRY),
        Ok(())
    );

    let a4 = lookup_canvas_format("a4").unwrap();
    let b4 = lookup_canvas_format("b4").unwrap();
    assert_ne!(a4.id, b4.id);
    assert_eq!(a4.integer_ratio(), b4.integer_ratio());
}

#[test]
fn registry_validation_rejects_each_invalid_shape() {
    assert_eq!(
        validate_canvas_format_registry(&CANVAS_FORMAT_REGISTRY[..10]),
        Err(CanvasFormatRegistryValidationError::UnexpectedCount { actual: 10 })
    );

    let mut duplicate = CANVAS_FORMAT_REGISTRY.to_vec();
    duplicate[10] = CanvasFormat {
        id: "square",
        width_units: 16,
        height_units: 9,
    };
    assert_eq!(
        validate_canvas_format_registry(&duplicate),
        Err(CanvasFormatRegistryValidationError::DuplicateId { id: "square" })
    );

    let mut invalid_id = CANVAS_FORMAT_REGISTRY.to_vec();
    invalid_id[10] = CanvasFormat {
        id: "HD_monitor",
        width_units: 16,
        height_units: 9,
    };
    assert_eq!(
        validate_canvas_format_registry(&invalid_id),
        Err(CanvasFormatRegistryValidationError::InvalidId { id: "HD_monitor" })
    );

    let mut zero = CANVAS_FORMAT_REGISTRY.to_vec();
    zero[10] = CanvasFormat {
        id: "hd_monitor",
        width_units: 0,
        height_units: 9,
    };
    assert_eq!(
        validate_canvas_format_registry(&zero),
        Err(CanvasFormatRegistryValidationError::NonPositiveUnits { id: "hd_monitor" })
    );

    let mut non_coprime = CANVAS_FORMAT_REGISTRY.to_vec();
    non_coprime[10] = CanvasFormat {
        id: "hd_monitor",
        width_units: 32,
        height_units: 18,
    };
    assert_eq!(
        validate_canvas_format_registry(&non_coprime),
        Err(CanvasFormatRegistryValidationError::NonCoprimeUnits { id: "hd_monitor" })
    );

    let mut missing_default = CANVAS_FORMAT_REGISTRY.to_vec();
    missing_default[0] = CanvasFormat {
        id: "landscape",
        width_units: 1,
        height_units: 1,
    };
    assert_eq!(
        validate_canvas_format_registry(&missing_default),
        Err(CanvasFormatRegistryValidationError::MissingDefault)
    );

    let mut reordered = CANVAS_FORMAT_REGISTRY.to_vec();
    reordered.swap(2, 3);
    assert_eq!(
        validate_canvas_format_registry(&reordered),
        Err(CanvasFormatRegistryValidationError::UnexpectedEntry { ordinal: 2 })
    );
}

#[test]
fn canonical_json_and_digest_match_the_shared_known_answer() {
    let fixture = fixture();
    assert_eq!(
        CANVAS_FORMAT_REGISTRY_DIGEST_DOMAIN,
        "inku.canvas-format-registry.v1"
    );
    assert!(!fixture.expected_canonical_json.ends_with('\n'));
    assert_eq!(
        canvas_format_registry_canonical_json_bytes().unwrap(),
        fixture.expected_canonical_json.as_bytes()
    );
    assert_eq!(
        canvas_format_registry_digest().unwrap(),
        fixture.expected_digest
    );
    assert_eq!(fixture.expected_digest.len(), 64);
    assert!(
        fixture
            .expected_digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    );

    let canonical = fixture.expected_canonical_json;
    for presentation in &fixture.new_presentations {
        assert!(!canonical.contains(&presentation.label));
    }
    assert!(!canonical.contains("pixel9_landscape_safe"));
    assert_eq!(
        fixture.new_presentations,
        [
            NewPresentation {
                id: "sd_monitor".into(),
                label: "4:3 SD Monitor".into(),
            },
            NewPresentation {
                id: "hd_monitor".into(),
                label: "16:9 HD Monitor".into(),
            },
        ]
    );
}
