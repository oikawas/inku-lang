"""A purpose a model was measured not to answer is left out unless chosen against it.

The author's instruction (2026-10-13): a model the benchmark found without an LLM
or Vision response cannot be selected for that purpose, and a model with neither
cannot be selected at all. The measurement is stored as `unsupported_purposes`,
apart from the purposes an operator ticks, so ticking cannot bring a purpose back.

Changed at the author's instruction (2026-10-26): an administrator can choose such
a purpose, and publish a model answering neither, as not recommended. The choice is
stored as `allowed_unsupported_purposes`; the catalog and a plain tick still leave
the purpose out, so publishing everything never chooses one.
"""

from __future__ import annotations

from inku_server.model_settings import (
    MODEL_METADATA_KEYS,
    model_provider_catalog,
    normalize_model_settings,
    update_model_settings,
)


def _settings(model: dict, *, enabled: bool = True) -> dict:
    return {"providers": {"gemini": {"models": [{"id": "measured-model", "label": "Measured", **model}],
                                     "enabled_models": {"measured-model": enabled}}}}


def _offered(settings: dict, purpose: str) -> bool:
    catalog = model_provider_catalog(settings, include_disabled=False, purpose=purpose)
    gemini = next(group for group in catalog if group["id"] == "gemini")
    return any(model["id"] == "measured-model" for model in gemini["models"])


def test_a_purpose_measured_without_a_response_is_not_offered():
    # gemini-3.1-flash-lite-image answered its drawings with a picture only.
    settings = _settings({"purposes": ["llm", "vision"], "unsupported_purposes": ["llm"]})
    model = normalize_model_settings(settings)["providers"]["gemini"]["models"][0]
    assert (model["purposes"], model["unsupported_purposes"]) == (["vision"], ["llm"])
    assert (_offered(settings, "llm"), _offered(settings, "vision")) == (False, True)
    # A live model-list fetch carries exactly MODEL_METADATA_KEYS over.
    assert "unsupported_purposes" in MODEL_METADATA_KEYS


def test_a_model_answering_neither_purpose_is_offered_for_nothing_and_cannot_be_published():
    # The 2.5 models answered 404 to this key; Omni answers only the Interactions API.
    settings = _settings({"purposes": ["llm"], "unsupported_purposes": ["llm", "vision"]})
    provider = normalize_model_settings(settings)["providers"]["gemini"]
    assert (provider["models"][0]["purposes"], provider["enabled_models"]["measured-model"]) == ([], False)
    published = update_model_settings(settings, {"providers": {"gemini": {"enabled_models": {"measured-model": True}}}})
    assert published["providers"]["gemini"]["enabled_models"]["measured-model"] is False
    assert (_offered(settings, "llm"), _offered(settings, "vision")) == (False, False)


def test_a_purpose_chosen_against_the_measurement_is_offered_as_not_recommended():
    settings = _settings({"purposes": ["llm", "vision"], "unsupported_purposes": ["vision"],
                          "allowed_unsupported_purposes": ["vision"], "recommendation_llm": 3})
    model = normalize_model_settings(settings)["providers"]["gemini"]["models"][0]
    assert (model["purposes"], model["allowed_unsupported_purposes"]) == (["llm", "vision"], ["vision"])
    assert (_offered(settings, "llm"), _offered(settings, "vision")) == (True, True)
    # An allowance for a purpose it answers, or one not ticked, keeps nothing.
    plain = normalize_model_settings(_settings({"purposes": ["llm"], "unsupported_purposes": ["vision"],
                                                "allowed_unsupported_purposes": ["llm", "vision"]}))
    assert "allowed_unsupported_purposes" not in plain["providers"]["gemini"]["models"][0]


def test_a_model_answering_neither_purpose_is_published_once_a_purpose_is_chosen_for_it():
    settings = _settings({"purposes": ["llm"], "unsupported_purposes": ["llm", "vision"],
                          "allowed_unsupported_purposes": ["llm"]})
    published = update_model_settings(settings, {"providers": {"gemini": {"enabled_models": {"measured-model": True}}}})
    gemini = published["providers"]["gemini"]
    assert (gemini["models"][0]["purposes"], gemini["enabled_models"]["measured-model"]) == (["llm"], True)
    assert (_offered(published, "llm"), _offered(published, "vision")) == (True, False)
    shown = model_provider_catalog(published, include_disabled=False, purpose="llm")
    labels = next(group for group in shown if group["id"] == "gemini")["models"][0]["labels"]
    assert labels == ["no_response"]


def test_a_model_left_out_of_the_benchmark_is_not_supported_and_cannot_be_published():
    # gemini-2.5-flash-preview-tts and the other kinds inku does not draw with.
    settings = _settings({"purposes": ["llm"], "not_supported": True})
    provider = normalize_model_settings(settings)["providers"]["gemini"]
    assert (provider["models"][0]["not_supported"], provider["enabled_models"]["measured-model"]) == (True, False)
    assert (_offered(settings, "llm"), _offered(settings, "vision")) == (False, False)
    assert "not_supported" in MODEL_METADATA_KEYS


def test_an_older_model_keeps_its_mark_and_can_still_be_published():
    # The OpenAI API models up to GPT-5.4 are folded away, not withdrawn.
    settings = _settings({"purposes": ["llm"], "legacy": True})
    provider = normalize_model_settings(settings)["providers"]["gemini"]
    assert (provider["models"][0]["legacy"], provider["enabled_models"]["measured-model"]) == (True, True)
    assert (_offered(settings, "llm"), _offered(settings, "vision")) == (True, False)
    assert "legacy" in MODEL_METADATA_KEYS


def test_an_unmeasured_model_with_no_purpose_still_reads_as_an_llm():
    model = normalize_model_settings(_settings({"purposes": []}))["providers"]["gemini"]["models"][0]
    assert model["purposes"] == ["llm"] and "unsupported_purposes" not in model
