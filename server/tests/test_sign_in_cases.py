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
    assert len(CASES) == 48
