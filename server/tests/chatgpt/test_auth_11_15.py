"""Shared policy boundaries and the Server HTTP input contract."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from inku_server.api_core.routers.chatgpt import PublishedModelsBody
from inku_server.verified_model_catalog import core_catalog


CASES = json.loads((Path(__file__).parents[1] / "data/chatgpt-auth-11-15-cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_cases(case):
    request = dict(case["request"])
    answer = core_catalog(request.pop("action"), **request)
    assert {key: answer.get(key) for key in case["expect"]} == case["expect"]


@pytest.mark.parametrize("target", [
    row["request"]["target"] for row in CASES
    if row["request"]["action"] == "chatgpt_auth_callback_query"
])
def test_callback_against_python_urlsplit(target):
    parsed = urlsplit(target)
    query = parse_qs(parsed.query)
    valid = parsed.path == "/auth/callback" and all(len(v) == 1 for v in query.values())
    result = core_catalog("chatgpt_auth_callback_query", target=target)
    assert result.get("query") == (query if valid else None)
    if not valid:
        assert result["error"] == "chatgpt_callback_invalid"


@pytest.mark.parametrize("field,length,valid", [
    ("profile_id", 0, False), ("profile_id", 1, True),
    ("profile_id", 128, True), ("profile_id", 129, False),
    ("selected_id", 0, False), ("selected_id", 1, True),
    ("selected_id", 256, True), ("selected_id", 257, False),
    ("purpose_key", 0, False), ("purpose_key", 1, True),
    ("purpose_key", 256, True), ("purpose_key", 257, False),
    ("count", 1024, True), ("count", 1025, False),
])
def test_publication_boundaries_and_http(field, length, valid):
    body = {"profile_id": "p", "generation": 1, "published_models": None, "model_purposes": None}
    if field == "profile_id":
        body[field] = "x" * length
    elif field == "selected_id":
        body["published_models"] = ["x" * length]
    elif field == "purpose_key":
        body["model_purposes"] = {"x" * length: ["llm"]}
    else:
        body["published_models"] = ["x"] * length
    result = core_catalog("chatgpt_auth_publication_input", profile_id=body["profile_id"],
                          generation=body["generation"], selected=body["published_models"],
                          model_purposes=body["model_purposes"])
    assert ("error" not in result) is valid
    if valid:
        PublishedModelsBody.model_validate(body)
    else:
        assert result["error"] == ("chatgpt_session_changed" if field == "profile_id" else "chatgpt_model_not_offered")
        with pytest.raises(ValidationError):
            PublishedModelsBody.model_validate(body)
