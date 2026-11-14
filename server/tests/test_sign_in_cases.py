"""The Server's core answers every shared sign-in case exactly as the case file says.

Sign in with ChatGPT is named, abbreviated and placed first by the shared core
(the author, 2026-11-14). Every host reads the same rows of
core/crates/inku-pipeline/data/sign-in-cases.json; here each request goes through
the same Python binding the Server's routes call.
"""

import json
import pathlib

import inku_render
import pytest

CASES = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "core/crates/inku-pipeline/data/sign-in-cases.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_the_core_answers_each_shared_sign_in_case(case):
    request = json.dumps(case["request"], ensure_ascii=False).encode("utf-8")
    assert json.loads(inku_render.pipeline_model_catalog(request)) == case["answer"]


def test_the_shared_cases_are_all_read():
    assert len(CASES) == 49


# The sign-in's procedures, step for step (SIWC step 5): each request a host sends and the
# core's answer, as the core's own test host recorded them.
FLOW_CASES = json.loads((pathlib.Path(__file__).resolve().parent / "data/sign-in-flow-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FLOW_CASES, ids=[case["why"] for case in FLOW_CASES])
def test_the_core_answers_each_step_of_the_shared_procedures(case):
    request = json.dumps(case["request"], ensure_ascii=False).encode("utf-8")
    assert json.loads(inku_render.pipeline_model_catalog(request)) == case["expect"]


def test_the_shared_procedure_steps_are_all_read():
    assert len(FLOW_CASES) == 106


# The two routes of step 2 pass what the screen holds to the core and return its answer.
VIEW_FIELDS = ("connection", "attempt", "busy", "code", "last_operation", "revocation_confirmed")
DRAFT_FIELDS = ("publication", "draft", "edit", "administrator", "assessment_drafts")


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from inku_server.api_core.routers import chatgpt

    app = FastAPI()
    app.include_router(chatgpt.router)
    app.dependency_overrides[chatgpt.owner] = lambda: "owner"
    return TestClient(app)


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["request"].get("service") == "chatgpt"
     and case["request"]["action"] in ("sign_in_connection_view", "sign_in_publication_draft")
     and case["answer"]["outcome"] == "ok"],
    ids=lambda case: case["name"],
)
def test_the_view_and_draft_routes_return_the_core_answer(case):
    request = case["request"]
    view = request["action"] == "sign_in_connection_view"
    fields = VIEW_FIELDS if view else DRAFT_FIELDS
    body = {key: request[key] for key in fields if key in request}
    answer = _client().post("/api/me/chatgpt/view" if view else "/api/me/chatgpt/models/draft", json=body)
    assert answer.status_code == 200
    assert answer.json() == case["answer"]


def test_an_unknown_draft_edit_is_refused_by_the_route():
    case = next(case for case in CASES if case["name"] == "draft: refuses an unknown edit")
    body = {key: case["request"][key] for key in DRAFT_FIELDS if key in case["request"]}
    answer = _client().post("/api/me/chatgpt/models/draft", json=body)
    assert (answer.status_code, answer.json()["detail"]["code"]) == (422, "chatgpt_invalid_draft")


# The Web tests answer /models/draft from answers recorded from the core for their requests
# (web/src/lib/features/settings/chatgpt-draft-answers.json); the core must still give them.
WEB_DRAFTS = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "web/src/lib/features/settings/chatgpt-draft-answers.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("row", WEB_DRAFTS, ids=lambda row: f"web-draft-{WEB_DRAFTS.index(row)}")
def test_the_web_tests_recorded_draft_answers_are_the_cores(row):
    answer = _client().post("/api/me/chatgpt/models/draft", json=row["request"])
    assert answer.json() == row["answer"]
