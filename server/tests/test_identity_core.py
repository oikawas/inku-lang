"""Server's identities and language rule come from the shared core.

The rows in data/identity-cases.json and data/instruction-language-cases.json
were written by the Python rules these modules used to hold. Every stored
``dh1``/``rh3`` was computed by those rules, so the core must give the same
answer on every row; Android and Swift read the same files.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_server.db import render_hash_for_item
from inku_server.identity import canonical_json, description_hash
from inku_server.language_support.registry import normalize_instruction_lang, resolve_instruction_lang

DATA = pathlib.Path(__file__).parent / "data"
IDENTITY = json.loads((DATA / "identity-cases.json").read_text(encoding="utf-8"))
LANGUAGE = json.loads((DATA / "instruction-language-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", IDENTITY["description_hash"], ids=[r["why"] for r in IDENTITY["description_hash"]])
def test_the_description_hash_is_the_one_every_saved_work_carries(row):
    assert description_hash(row["text"]) == row["dh1"]


@pytest.mark.parametrize("row", IDENTITY["canonical_json"], ids=[r["why"] for r in IDENTITY["canonical_json"]])
def test_the_canonical_json_is_what_python_wrote(row):
    assert canonical_json(json.loads(row["input"])) == row["canonical"]


@pytest.mark.parametrize("row", IDENTITY["render_hash"], ids=[r["why"] for r in IDENTITY["render_hash"]])
def test_the_render_hash_is_the_one_every_saved_work_carries(row):
    assert render_hash_for_item(json.loads(row["item"])) == row["rh3"]


@pytest.mark.parametrize("row", LANGUAGE["normalize"], ids=[r["why"] for r in LANGUAGE["normalize"]])
def test_a_requested_language_is_normalized_as_before(row):
    if row["language"] is None:
        with pytest.raises(ValueError):
            normalize_instruction_lang(row["value"], default=row["default"])
    else:
        assert normalize_instruction_lang(row["value"], default=row["default"]) == row["language"]


@pytest.mark.parametrize("row", LANGUAGE["resolve"], ids=[r["why"] for r in LANGUAGE["resolve"]])
def test_the_instruction_language_is_resolved_as_before(row):
    call = lambda: resolve_instruction_lang(row["text"], row["requested"], fallback=row["fallback"])  # noqa: E731
    if row["language"] is None:
        with pytest.raises(ValueError):
            call()
    else:
        assert call() == row["language"]
