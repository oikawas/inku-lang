"""Old JSON is converted once; current history carries a single unchanged DDL."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from inku_server.api_core.models import HistoryItem, HistoryPostBody
from inku_server.persistence.ddl_source import select_ddl


ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "persistence/fixtures/ddl-selection.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_legacy_json_selects_the_shared_body_without_rewriting_it(case):
    assert select_ddl(case["ddl"], case["expanded_ddl"]) == (
        case["selected"], case["ddl_source_origin"],
    )
    item = HistoryItem.model_validate({
        "id": "work", "input": "description", "score": {}, "at": 1,
        "ddl": case["ddl"], "expanded_ddl": case["expanded_ddl"],
    })
    saved = item.model_dump(mode="json")
    assert saved["ddl"] == case["selected"]
    assert saved["ddl_source_origin"] == case["ddl_source_origin"]
    assert "expanded_ddl" not in saved
    assert "expanded_ddl" not in HistoryItem.model_json_schema()["properties"]


def test_current_json_preserves_origin_without_an_authority_claim():
    body = HistoryPostBody.model_validate({
        "input": "description", "score": {}, "at": 1,
        "ddl": "\nScene: Moon \n", "ddl_source_origin": "legacy_expanded",
        "authority": "ddl_authoritative",
    })
    assert body.ddl == "\nScene: Moon \n"
    assert body.ddl_source_origin == "legacy_expanded"
    assert "authority" not in body.model_dump()
    with pytest.raises(ValidationError):
        HistoryPostBody.model_validate({
            "input": "description", "score": {}, "at": 1,
            "ddl_source_origin": "user_authored_ddl",
        })
