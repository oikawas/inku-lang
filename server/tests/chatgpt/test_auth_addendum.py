import json
from pathlib import Path

import pytest

from inku_server.verified_model_catalog import core_catalog


CASES = json.loads((Path(__file__).parents[1] / "data/chatgpt-auth-addendum-cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_auth_addendum_shared_fixture(case):
    request = dict(case["request"])
    answer = core_catalog(request.pop("action"), **request)
    assert {key: answer.get(key) for key in case["expect"]} == case["expect"]
