"""Model reference resolution: three rules, no guessing.

The expectation table lives in web/scripts/model-ref-expectations.json and is
read by this file and by web/scripts/model-ref-check.mjs, so "Python and
JavaScript answer the same" is a property of the arrangement rather than of two
tables that happen to agree today.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from inku_server.db import _normalize_demo_settings
from inku_server.model_settings import (
    default_model_settings,
    normalize_user_model_settings,
    provider_for_model,
    qualify_model_ref,
    split_model_ref,
    update_user_model_settings,
)

_EXPECTATIONS_PATH = Path(__file__).resolve().parents[2] / "web" / "scripts" / "model-ref-expectations.json"
EXPECTATIONS = json.loads(_EXPECTATIONS_PATH.read_text(encoding="utf-8"))


def _settings(stage_defaults: dict[str, str] | None = None) -> dict:
    """The catalog plus the stage keys, the way the product hands them over.

    provider_for_model() reads the catalog for rules 1 and 2 and the stage keys
    for rule 3, and both come out of the one dict it is given.
    """
    settings = default_model_settings()
    settings.update(stage_defaults or EXPECTATIONS["stage_defaults"])
    return settings


def test_the_shared_table_still_describes_the_shipped_catalog():
    """If a provider gains or loses a model, the shared table must be redone."""
    shipped = {
        provider_id: [str(model["id"]) for model in provider["models"]]
        for provider_id, provider in default_model_settings()["providers"].items()
    }
    assert EXPECTATIONS["catalog"] == shipped


@pytest.mark.parametrize("case", EXPECTATIONS["cases"], ids=lambda case: case["ref"])
@pytest.mark.parametrize("stage", ["stage1", "stage2"])
def test_the_expectation_table(case, stage):
    provider, model = provider_for_model(case["ref"], stage=stage, settings=_settings())
    assert (provider, model) == (case["provider"], case["model"])


def test_qualified_references_are_taken_at_their_word():
    """Rule 1. These four answered correctly before the change and still do."""
    explicit = [case for case in EXPECTATIONS["cases"] if case["rule"] == "explicit"]
    assert len(explicit) == 4
    for case in explicit:
        assert provider_for_model(case["ref"], stage="stage1", settings=_settings()) == (
            case["provider"],
            case["model"],
        )


def test_sole_ownership_decides_and_ambiguity_does_not():
    ambiguity = EXPECTATIONS["ambiguity"]
    settings = _settings()
    # The shipped catalog no longer contains a model two providers both list --
    # replacing the Ollama list on 2026-07-29 removed the last one -- so the
    # second owner is added here. Without it this rule would go untested.
    settings["providers"][ambiguity["added_owner"]]["models"].append(
        {"id": ambiguity["ref"], "label": ambiguity["ref"]}
    )
    owners = [
        provider_id
        for provider_id, provider in settings["providers"].items()
        if any(str(model["id"]) == ambiguity["ref"] for model in provider["models"])
    ]
    assert sorted(owners) == sorted(ambiguity["owners"]), "the ambiguity this rule exists for is gone"

    provider, model = provider_for_model(ambiguity["ref"], stage="stage1", settings=settings)
    assert provider == settings["stage1_provider"]
    assert model == ambiguity["ref"]

    # Take one owner away and rule 2 decides again -- this is what proves rule 2
    # runs at all rather than everything falling through to the stage default.
    narrowed = deepcopy(settings)
    narrowed["providers"][ambiguity["deactivate"]]["active"] = False
    assert provider_for_model(ambiguity["ref"], stage="stage1", settings=narrowed) == (
        ambiguity["provider_when_deactivated"],
        ambiguity["ref"],
    )


@pytest.mark.parametrize("case", EXPECTATIONS["stage_dependent"]["cases"], ids=lambda case: case["ref"])
def test_rule_three_reads_the_stage(case):
    settings = _settings(EXPECTATIONS["stage_dependent"]["stage_defaults"])
    assert provider_for_model(case["ref"], stage="stage1", settings=settings)[0] == case["stage1"]
    assert provider_for_model(case["ref"], stage="stage2", settings=settings)[0] == case["stage2"]


@pytest.mark.parametrize("ref", EXPECTATIONS["never_ovms"]["refs"])
@pytest.mark.parametrize("stage", ["stage1", "stage2"])
def test_nothing_unrecognised_lands_on_ovms(ref, stage):
    """ovms was the old default landing provider and its endpoint is stopped."""
    settings = _settings({"stage1_provider": "ollama", "stage2_provider": "anthropic"})
    assert provider_for_model(ref, stage=stage, settings=settings)[0] != "ovms"


@pytest.mark.parametrize("case", EXPECTATIONS["qualify"], ids=lambda case: case["ref"])
def test_qualify_does_not_qualify_twice(case):
    assert qualify_model_ref(case["provider"], case["ref"], _settings()) == case["expected"]


@pytest.mark.parametrize(
    "case", EXPECTATIONS["round_trip"], ids=lambda case: f"{case['provider']}:{case['model']}"
)
def test_a_model_id_carrying_colons_survives_the_round_trip(case):
    settings = _settings()
    qualified = qualify_model_ref(case["provider"], case["model"], settings)
    assert qualified == f"{case['provider']}:{case['model']}"
    assert split_model_ref(qualified, settings) == (case["provider"], case["model"])


def test_an_unqualified_reference_splits_to_itself():
    settings = _settings()
    assert split_model_ref("gpt-oss:20b", settings) == (None, "gpt-oss:20b")
    assert split_model_ref("qwen3.5:4b-q4_K_M", settings) == (None, "qwen3.5:4b-q4_K_M")
    assert split_model_ref("my-model", settings) == (None, "my-model")
    assert split_model_ref(":leading", settings) == (None, ":leading")
    assert split_model_ref("ollama:", settings) == (None, "ollama:")


def test_the_okugaki_pair_reads_the_single_string_it_replaced():
    clean = normalize_user_model_settings({"okugaki_model": "openai:gpt-4.1-mini"})
    assert clean["okugaki_provider"] == "openai"
    assert clean["okugaki_model"] == "gpt-4.1-mini"


def test_the_okugaki_pair_is_written_back_as_a_pair():
    stored = update_user_model_settings({}, {"okugaki_model": "ollama-cloud:gemma4:31b"})
    assert stored["okugaki_provider"] == "ollama-cloud"
    assert stored["okugaki_model"] == "gemma4:31b"
    # Re-reading the pair leaves it alone: the colon inside the model id is not
    # mistaken for a provider prefix a second time.
    assert normalize_user_model_settings(stored)["okugaki_model"] == "gemma4:31b"


def test_the_okugaki_pair_survives_a_provider_only_patch():
    stored = update_user_model_settings(
        {"okugaki_provider": "ollama", "okugaki_model": "gpt-oss:20b"},
        {"okugaki_provider": "ollama-cloud"},
    )
    assert (stored["okugaki_provider"], stored["okugaki_model"]) == ("ollama-cloud", "gpt-oss:20b")


def test_the_demo_prompt_pair_reads_the_single_string_it_replaced():
    clean = _normalize_demo_settings({"prompt_model": "ollama:llama3.2"})
    assert clean["prompt_provider"] == "ollama"
    assert clean["prompt_model"] == "llama3.2"


def test_the_demo_prompt_model_keeps_its_own_colons():
    clean = _normalize_demo_settings({"prompt_provider": "ollama", "prompt_model": "gpt-oss:20b"})
    assert (clean["prompt_provider"], clean["prompt_model"]) == ("ollama", "gpt-oss:20b")
