"""Parity for the bounded saved-Score compatibility fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from inku_server.schema import Score


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "core/crates/inku-score/tests/fixtures/saved-score-compatibility.json"
)
CANONICAL_DIGEST_DOMAIN = b"inku.score.canonical-json.v1"


def _canonical_identity(score: Score) -> tuple[bytes, str]:
    canonical = json.dumps(
        score.model_dump(by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    digest = hashlib.sha256(
        CANONICAL_DIGEST_DOMAIN + b"\0" + len(canonical).to_bytes(8, "big") + canonical
    ).hexdigest()
    return canonical, digest


def test_saved_score_fixture_matches_server_canonical_identity() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    ids = [case["id"] for case in fixture["cases"] + fixture["invalid_cases"]]
    assert len(ids) == len(set(ids))

    for case in fixture["cases"]:
        canonical, digest = _canonical_identity(Score.model_validate(case["input"]))
        assert canonical == case["canonical_json"].encode(), case["id"]
        assert digest == case["digest"], case["id"]


def test_saved_score_fixture_invalid_cases_remain_invalid() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    for case in fixture["invalid_cases"]:
        with pytest.raises(ValidationError):
            Score.model_validate(case["input"])
