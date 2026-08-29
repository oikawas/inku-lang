"""Independent known-answer verification for the host-neutral `ddl-v1` seed framing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "core/crates/inku-ddl/tests/fixtures/macro-seed-ddl-v1.json"
DOMAIN = b"inku.macro-seed"
SCHEME_ID = "ddl-v1"
REQUIRED_CASE_IDS = {
    "ja-omitted-composition",
    "ja-explicit-zero-composition",
    "en-nonzero-composition",
    "same-macro-different-ordinal",
    "different-qualified-macro",
    "unicode-exact-bytes",
    "newline-exact-bytes",
    "u64-boundary",
}


def _canonical_decimal(value: str) -> bool:
    return value == "0" or (value[:1] != "0" and value.isascii() and value.isdecimal())


def _hash_input(case: dict[str, object]) -> bytes:
    composition_seed = case["composition_seed"] or "0"
    fields = (
        SCHEME_ID,
        case["canonical_ddl"],
        f"{case['namespace']}.{case['heading']}",
        case["ordinal"],
        composition_seed,
    )
    assert all(isinstance(field, str) for field in fields)
    return DOMAIN + b"".join(
        len(field.encode("utf-8")).to_bytes(8, "big") + field.encode("utf-8")
        for field in fields
    )


def test_macro_seed_fixture_is_an_independent_ddl_v1_known_answer_set():
    raw = FIXTURE.read_bytes()
    assert raw.endswith(b"\n")
    fixture = json.loads(raw)
    assert fixture["schema"] == "inku.macro-seed-ddl-v1-fixture.v1"
    assert fixture["version"] == 1

    cases = fixture["cases"]
    assert isinstance(cases, list)
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert set(ids) >= REQUIRED_CASE_IDS

    for case in cases:
        assert set(case) == {
            "id",
            "canonical_ddl",
            "namespace",
            "heading",
            "ordinal",
            "composition_seed",
            "expected",
        }
        assert _canonical_decimal(case["ordinal"])
        if case["composition_seed"] is not None:
            assert _canonical_decimal(case["composition_seed"])
        assert case["namespace"].isascii()
        assert case["namespace"][:1].isalpha()
        assert all(character.isalnum() or character in "_-" for character in case["namespace"])
        assert case["heading"] and case["heading"] == case["heading"].strip()
        assert not any(character.isspace() and character in "\r\n" for character in case["heading"])

        expected = case["expected"]
        assert set(expected) == {"digest", "resolved_seed"}
        assert len(expected["digest"]) == 64
        assert all(character in "0123456789abcdef" for character in expected["digest"])
        assert _canonical_decimal(expected["resolved_seed"])

        digest = hashlib.sha256(_hash_input(case)).digest()
        assert digest.hex() == expected["digest"], case["id"]
        assert str(int.from_bytes(digest[:8], "big")) == expected["resolved_seed"], case["id"]
