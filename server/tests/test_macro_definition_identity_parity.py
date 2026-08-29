import hashlib
import json
import re
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "core/crates/inku-ddl/tests/fixtures/macro-definition-v1.json"
)
DOMAIN = b"inku.macro-definition.v1"
EXPECTED_VALID_IDS = {
    "all-operators-ja-component-reuse-bounded-vary-touch-surface",
    "input-key-order-whitespace-equivalence",
    "digest-sensitivity-version",
}
EXPECTED_INVALID_IDS = {
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
}


def test_rust_fixture_expected_canonical_bytes_have_independent_python_digests():
    raw = FIXTURE_PATH.read_bytes()
    assert raw.endswith(b"\n")
    fixture = json.loads(raw)
    assert fixture["schema"] == "inku.macro-definition-v1-fixture.v1"
    assert fixture["version"] == 1

    valid_ids = [case["id"] for case in fixture["valid_cases"]]
    invalid_ids = [case["id"] for case in fixture["invalid_cases"]]
    assert len(valid_ids + invalid_ids) == len(set(valid_ids + invalid_ids))
    assert set(valid_ids) == EXPECTED_VALID_IDS
    assert set(invalid_ids) == EXPECTED_INVALID_IDS

    digests = {}
    for case in fixture["valid_cases"]:
        canonical = case["expected_canonical_json"].encode()
        assert not canonical.endswith(b"\n")
        assert json.loads(canonical)["schema"] == "inku.macro-definition.v1"
        expected = case["expected_digest"]
        assert re.fullmatch(r"[0-9a-f]{64}", expected)
        framed = DOMAIN + len(canonical).to_bytes(8, "big") + canonical
        assert hashlib.sha256(framed).hexdigest() == expected
        digests[case["id"]] = expected

    assert (
        digests["all-operators-ja-component-reuse-bounded-vary-touch-surface"]
        != digests["digest-sensitivity-version"]
    )
