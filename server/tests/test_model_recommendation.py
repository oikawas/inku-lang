"""Recommendation levels: per stage where the measurement was per stage.

The expectation table lives in web/scripts/model-recommendation-expectations.json
and is read by this file and by web/scripts/model-recommendation-check.mjs. The
server owns the values; the web owns what the picker does with them.

The local Ollama models are the reason the stage keys exist. Every other provider
was measured end to end and has one number, so this file also pins that they were
not migrated: a model with only recommendation_llm must answer the same for both
stages, or the eight Ollama Cloud entries and the thirty-two NVIDIA ones are broken.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inku_server.model_settings import (
    MODEL_METADATA_KEYS,
    MODEL_RECOMMENDATION_KEYS,
    default_model_settings,
    normalize_model_settings,
)
from inku_server.verified_model_catalog import (
    MODEL_CONFIG_VERSION,
    VERIFIED_OLLAMA_CLOUD_MODELS,
    VERIFIED_OLLAMA_LOCAL_MODELS,
)

_EXPECTATIONS_PATH = (
    Path(__file__).resolve().parents[2] / "web" / "scripts" / "model-recommendation-expectations.json"
)
EXPECTATIONS = json.loads(_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
_OLLAMA_BY_ID = {str(model["id"]): model for model in VERIFIED_OLLAMA_LOCAL_MODELS}


def test_the_shared_table_still_lists_every_local_model():
    """If the Ollama catalog gains or loses a model, the shared table must be redone."""
    assert [case["id"] for case in EXPECTATIONS["ollama"]] != []
    assert set(case["id"] for case in EXPECTATIONS["ollama"]) == set(_OLLAMA_BY_ID)


@pytest.mark.parametrize("case", EXPECTATIONS["ollama"], ids=lambda case: case["id"])
def test_the_shipped_catalog_carries_the_expected_levels(case):
    model = _OLLAMA_BY_ID[case["id"]]
    assert model.get("recommendation_stage1") == case["stage1"]
    # None in the table means the stage was not measured. Absent, not zero: the
    # picker renders an em dash, and 1 is reserved for "measured and poor".
    if case["stage2"] is None:
        assert "recommendation_stage2" not in model
    else:
        assert model.get("recommendation_stage2") == case["stage2"]


def test_the_two_stages_disagree_which_is_why_the_keys_exist():
    """A single number could not describe the pair inku recommends.

    If this ever passes trivially -- because every model's two stages ended up
    equal -- the stage keys stopped earning their place and the arrangement should
    be reconsidered rather than kept out of habit.
    """
    staged = [
        model for model in VERIFIED_OLLAMA_LOCAL_MODELS
        if "recommendation_stage1" in model and "recommendation_stage2" in model
    ]
    disagreeing = [
        model for model in staged
        if model["recommendation_stage1"] != model["recommendation_stage2"]
    ]
    assert len(disagreeing) >= 5, "the stage split no longer distinguishes anything"
    # The two halves of the recommended configuration, each strong at one stage.
    stage1_pick = _OLLAMA_BY_ID["qwen3.5:4b-q4_K_M"]
    stage2_pick = _OLLAMA_BY_ID["ministral-3:8b-instruct-2512-q4_K_M"]
    assert stage1_pick["recommendation_stage1"] > stage1_pick["recommendation_stage2"]
    assert stage2_pick["recommendation_stage2"] > stage2_pick["recommendation_stage1"]


def test_models_measured_end_to_end_keep_their_single_number():
    """Nothing was migrated. Ollama Cloud's eight carry recommendation_llm alone."""
    scored = [model for model in VERIFIED_OLLAMA_CLOUD_MODELS if "recommendation_llm" in model]
    assert len(scored) == 8
    for model in scored:
        assert "recommendation_stage1" not in model
        assert "recommendation_stage2" not in model


@pytest.mark.parametrize("key", ["recommendation_stage1", "recommendation_stage2"])
def test_a_stage_level_survives_normalisation_and_is_clamped(key):
    clean = normalize_model_settings(
        {
            "providers": {
                "ollama": {
                    "models": [
                        {"id": "a", "label": "a", key: 4},
                        {"id": "b", "label": "b", key: 99},
                        {"id": "c", "label": "c", key: -3},
                        {"id": "d", "label": "d", key: "4"},
                        {"id": "e", "label": "e", key: True},
                    ]
                }
            }
        }
    )
    by_id = {str(model["id"]): model for model in clean["providers"]["ollama"]["models"]}
    assert by_id["a"][key] == 4
    assert by_id["b"][key] == 5
    assert by_id["c"][key] == 1
    # A string and a bool are not levels. Absent beats guessing at one.
    assert key not in by_id["d"]
    assert key not in by_id["e"]


def test_a_stage_level_is_not_filled_in_from_the_legacy_key():
    """recommendation_level feeds the purpose keys, not the stage keys.

    Reading it here would turn "not measured for this stage" into a number nobody
    measured, which is the distinction the em dash exists to keep.
    """
    clean = normalize_model_settings(
        {"providers": {"ollama": {"models": [{"id": "a", "label": "a", "recommendation_level": 3}]}}}
    )
    model = clean["providers"]["ollama"]["models"][0]
    assert model["recommendation_llm"] == 3
    assert "recommendation_stage1" not in model
    assert "recommendation_stage2" not in model


def test_a_stored_list_without_the_keys_gets_them_from_the_builtin_base():
    """pentala's stored Ollama entries hold id, label and purposes only.

    This path is the plain merge -- `{**builtin, **stored}` -- and not the metadata
    refresh, so it says nothing about MODEL_METADATA_KEYS. Written separately from
    the test below so neither is mistaken for the other: measured 2026-07-30, this
    one passes with the stage keys removed from MODEL_METADATA_KEYS entirely.
    """
    stored = {
        "model_catalog_version": "2.4.0",
        "providers": {
            "ollama": {
                "models": [
                    {"id": model["id"], "label": model["label"], "purposes": ["llm"]}
                    for model in VERIFIED_OLLAMA_LOCAL_MODELS
                ]
            }
        },
    }
    clean = normalize_model_settings(stored)
    by_id = {str(model["id"]): model for model in clean["providers"]["ollama"]["models"]}
    for case in EXPECTATIONS["ollama"]:
        assert by_id[case["id"]].get("recommendation_stage1") == case["stage1"], case["id"]
        if case["stage2"] is None:
            assert "recommendation_stage2" not in by_id[case["id"]], case["id"]
        else:
            assert by_id[case["id"]].get("recommendation_stage2") == case["stage2"], case["id"]


def test_a_stale_stored_level_is_overwritten_only_because_the_key_is_refreshed():
    """This is the one that tests MODEL_METADATA_KEYS, and it needs a stale value.

    A stored copy wins the merge. The refresh a catalog version bump triggers is the
    only thing that takes the value back, and it only takes back the keys it is told
    about -- so a sample whose stored entry simply *lacks* the key proves nothing.
    Here the stored entry claims 1 where the catalog says 5.
    """
    stored = {
        "model_catalog_version": "2.4.0",
        "providers": {
            "ollama": {
                "models": [
                    {
                        "id": "qwen3.5:4b-q4_K_M",
                        "label": "qwen3.5:4b-q4_K_M (3.4GB)",
                        "purposes": ["llm"],
                        "recommendation_stage1": 1,
                        "recommendation_stage2": 1,
                    }
                ]
            }
        },
    }
    model = normalize_model_settings(stored)["providers"]["ollama"]["models"][0]
    assert model["recommendation_stage1"] == 5
    assert model["recommendation_stage2"] == 2


def test_a_stale_stored_level_survives_at_the_current_version():
    """The counterpart: the refresh is what the version gates.

    Without this pair, a refresh that ran unconditionally would pass the test above
    and the version would be doing nothing.
    """
    stored = {
        "model_catalog_version": MODEL_CONFIG_VERSION,
        "providers": {
            "ollama": {
                "models": [
                    {"id": "qwen3.5:4b-q4_K_M", "label": "x", "purposes": ["llm"], "recommendation_stage1": 1}
                ]
            }
        },
    }
    model = normalize_model_settings(stored)["providers"]["ollama"]["models"][0]
    assert model["recommendation_stage1"] == 1


def test_every_place_that_lists_metadata_keys_knows_the_recommendation_keys():
    """Three lists have to agree, and a key added to only some is lost silently.

    The normalizer receives them, MODEL_METADATA_KEYS refreshes them on a version
    bump, and api.py's `carried` keeps them across a live model-list fetch -- which
    is the path an operator actually takes when they press the fetch button.

    The keys are written out here rather than read from the constant. Looping over
    MODEL_RECOMMENDATION_KEYS to check that MODEL_METADATA_KEYS contains them is a
    statement about a list and itself: measured 2026-07-30, deleting the two stage
    keys from the constant left the earlier version of this test green.
    """
    import inspect

    from inku_server import api as api_module
    from inku_server import model_settings as ms

    expected = (
        "recommendation_llm",
        "recommendation_vision",
        "recommendation_stage1",
        "recommendation_stage2",
        "recommendation_level",
    )
    assert MODEL_RECOMMENDATION_KEYS == expected

    for key in expected:
        assert key in MODEL_METADATA_KEYS, key

    normaliser = inspect.getsource(ms._normalize_models)
    for key in expected:
        assert key in normaliser, f"{key} is not read on the way in"

    fetch = inspect.getsource(api_module.api_settings_fetch_provider_models)
    assert "MODEL_METADATA_KEYS" in fetch, "the live fetch no longer carries the shared key list"


def test_the_release_view_keeps_no_measured_duration_in_a_comment():
    """The 2026-07-29 adjudication took speed out of the release.

    It was applied to speed_class and speed_label only, and the comments went on
    stating the same seconds; hiding two fields while the prose repeats them is not
    hiding it. The timeout that excluded a run is a different thing and stays.
    """
    import re

    duration = re.compile(r"中央値\s*\d+|\d+\s*秒\s*\(|median of \d+|took \d+ second", re.IGNORECASE)
    for model in VERIFIED_OLLAMA_CLOUD_MODELS + VERIFIED_OLLAMA_LOCAL_MODELS:
        text = f"{model.get('comment_ja', '')} {model.get('comment_en', '')}"
        assert not duration.search(text), model["id"]


def test_speed_label_carries_a_timing_or_nothing():
    """It was carrying "第二段階は未計測" for four models -- a measurement status in a
    speed field, and one that vanishes in the release view along with the field."""
    for model in VERIFIED_OLLAMA_LOCAL_MODELS:
        label = str(model.get("speed_label", ""))
        assert "未計測" not in label, model["id"]
        assert "計測" not in label, model["id"]


def test_the_builtin_ollama_catalog_reaches_the_default_settings():
    """The values are only worth anything if they arrive through the real path."""
    models = default_model_settings()["providers"]["ollama"]["models"]
    by_id = {str(model["id"]): model for model in models}
    assert by_id["qwen3.5:4b-q4_K_M"]["recommendation_stage1"] == 5
    assert by_id["qwen3.5:4b-q4_K_M"]["recommendation_stage2"] == 2
    assert "recommendation_stage2" not in by_id["qwen3.5:0.8b-q8_0"]
