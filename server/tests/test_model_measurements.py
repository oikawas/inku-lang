"""Measured cost and mean speed travel with a model the way its levels do.

The author asked (2026-10-13) for the picker to print an approximate USD cost and
the measured mean seconds, for LLM and for Vision, beside each model. They are
stored on the shared model list like the levels, so every path that keeps a level
has to keep them too: the normalizer on a save, the set a live model-list fetch
carries over, and the release catalog, which hides measured speed for the
providers whose speed is a developer-only number.
"""

from __future__ import annotations

import math

import pytest

from inku_server.model_settings import MODEL_METADATA_KEYS, model_provider_catalog, normalize_model_settings

_MEASURED = {"cost_usd_llm": 0.007718, "cost_usd_vision": 0.001309, "speed_llm_seconds": 12.5, "speed_vision_seconds": 2.2}


def _stored(provider_id: str, model: dict) -> dict:
    return {"providers": {provider_id: {"models": [{"id": "measured-model", "label": "Measured", **model}]}}}


def _model(settings: dict, provider_id: str) -> dict:
    models = normalize_model_settings(settings)["providers"][provider_id]["models"]
    return next(model for model in models if model["id"] == "measured-model")


def test_measured_cost_and_speed_survive_a_save_and_a_model_list_fetch():
    # gemma-4-31b-it costs nothing on the free tier: 0 is a measurement, not an absence.
    model = _model(_stored("gemini", {**_MEASURED, "cost_usd_llm": 0}), "gemini")
    assert {key: model[key] for key in _MEASURED} == {**_MEASURED, "cost_usd_llm": 0.0}
    # A live fetch carries exactly MODEL_METADATA_KEYS over from the stored entry.
    assert set(_MEASURED) <= set(MODEL_METADATA_KEYS)


@pytest.mark.parametrize(("key", "value"), [
    ("speed_llm_seconds", 0), ("cost_usd_llm", -0.01), ("cost_usd_vision", True),
    ("speed_vision_seconds", math.nan), ("cost_usd_llm", math.inf), ("speed_llm_seconds", "12.5"),
])
def test_a_value_that_is_not_a_measurement_is_left_out(key, value):
    assert key not in _model(_stored("gemini", {key: value}), "gemini")


def test_release_hides_measured_speed_where_it_hides_the_speed_label():
    settings = _stored("ollama-cloud", {**_MEASURED, "speed_label": "中央値 11s"})

    def shown(include_developer: bool) -> dict:
        catalog = model_provider_catalog(settings, include_developer=include_developer)
        group = next(group for group in catalog if group["id"] == "ollama-cloud")
        return next(model for model in group["models"] if model["id"] == "measured-model")

    release = shown(False)
    assert not {"speed_label", "speed_llm_seconds", "speed_vision_seconds"} & set(release)
    assert (release["cost_usd_llm"], release["cost_usd_vision"]) == (0.007718, 0.001309)
    assert shown(True)["speed_llm_seconds"] == 12.5
