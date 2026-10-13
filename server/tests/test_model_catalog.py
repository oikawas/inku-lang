"""One catalog of model information in a common format (the author, 2026-10-13).

model_catalog.json holds every provider's model information, the ChatGPT plan's included, and
the label table that files a model into a fold. These check the file itself, the rules that
label a model (the same cases the Web, macOS and Android read), and how an installation's copy
follows the catalog.
"""

from __future__ import annotations

import json
from pathlib import Path

from inku_server.api_core.routers import settings as settings_routes
from inku_server.model_catalog import MODEL_LABELS, catalog_models, catalog_problems, model_fold, model_labels
from inku_server.model_settings import (
    chatgpt_assessments,
    default_model_settings,
    model_provider_catalog,
    normalize_chatgpt_models,
    normalize_model_settings,
    update_model_settings,
)
from inku_server.verified_model_catalog import MODEL_CATALOG, MODEL_CONFIG_VERSION, STORED_LABEL_KEYS

CASES = json.loads((Path(__file__).parent / "data/model-catalog-cases.json").read_text(encoding="utf-8"))
_PUBLISHABLE = {label["id"]: label["publishable"] for label in MODEL_LABELS}


def _kept_by_the_server(model: dict) -> dict:
    """A model in the common format as the Server keeps it: each stored label as its boolean."""
    kept = {key: value for key, value in model.items() if key != "labels"}
    for label in model.get("labels", []):
        kept[STORED_LABEL_KEYS[label]] = True
    return kept


def test_the_catalog_file_is_well_formed():
    assert catalog_problems() == []
    assert [label["id"] for label in MODEL_LABELS] == [
        "unmeasured", "legacy", "subscription", "no_response", "not_supported", "eol"]
    assert set(MODEL_CATALOG["providers"]) == {"openai", "anthropic", "gemini", "nvidia", "ollama", "ollama-cloud", "chatgpt"}


def test_a_model_is_labelled_and_filed_as_the_shared_cases_say():
    for case in CASES["cases"]:
        labels = model_labels(_kept_by_the_server(case["model"]))
        assert (labels, model_fold(labels), all(_PUBLISHABLE[label] for label in labels)) == (
            case["labels"], case["fold"], case["publishable"]), case["name"]
    assert len(CASES["cases"]) == 15


def test_a_changed_catalog_replaces_the_model_information_an_installation_kept():
    # An installation stored gpt-6-sol under the catalog before this one, with a stale comment,
    # a speed label the catalog no longer carries, its own name and its probe's paid-plan mark.
    stored = {"model_catalog_version": "2.5.0", "providers": {"openai": {"models": [
        {"id": "gpt-6-sol", "label": "shown here", "purposes": ["llm"], "comment_ja": "古い", "speed_label": "古い",
         "requires_subscription": True}]}}}
    model = normalize_model_settings(stored)["providers"]["openai"]["models"][0]
    catalog = catalog_models("openai")["gpt-6-sol"]
    assert {key: value for key, value in model.items() if key not in ("label", "requires_subscription")} == {
        key: value for key, value in catalog.items() if key != "label"}
    assert (model["label"], model["requires_subscription"]) == ("shown here", True)


def test_an_administrators_change_lasts_until_the_catalog_changes():
    stored = {"model_catalog_version": MODEL_CONFIG_VERSION, "providers": {"openai": {"models": [
        {"id": "gpt-6-sol", "label": "gpt-6-sol", "purposes": ["llm"], "comment_ja": "手直し"}]}}}
    assert normalize_model_settings(stored)["providers"]["openai"]["models"][0]["comment_ja"] == "手直し"
    moved = normalize_model_settings({**stored, "model_catalog_version": "2.5.0"})
    assert moved["providers"]["openai"]["models"][0]["comment_ja"] == catalog_models("openai")["gpt-6-sol"]["comment_ja"]


def test_the_chatgpt_plan_is_kept_in_the_same_format():
    catalog = catalog_models("chatgpt")
    assert len(catalog) == 7 and set(chatgpt_assessments(default_model_settings())) == set(catalog)
    model_id = "gpt-6-luna"
    saved = update_model_settings(default_model_settings(), {"providers": {"chatgpt": {"models": [
        {"id": model_id, "label": "GPT-6-Luna", "comment_ja": "手直し", "labels": ["not_supported"]}]}}})
    assessment = chatgpt_assessments(saved)[model_id]
    assert (assessment["comment_ja"], assessment.get("not_supported")) == ("手直し", True)
    older_client = update_model_settings(default_model_settings(), {"chatgpt_models": [
        {"id": model_id, "label": "GPT-6-Luna", "comment_ja": "古い形"}]})
    assert chatgpt_assessments(older_client)[model_id]["comment_ja"] == "古い形"
    expected = normalize_chatgpt_models([catalog[model_id]])[0]
    assert chatgpt_assessments({**saved, "model_catalog_version": "2.5.0"})[model_id] == expected


def test_every_listed_model_carries_its_labels_its_fold_and_the_old_marks():
    stored = {"model_catalog_version": "2.5.0", "providers": {"openai": {"models": [
        {"id": "gpt-4o", "label": "gpt-4o"}, {"id": "dall-e-3", "label": "dall-e-3"}, {"id": "brand-new", "label": "brand-new"}]}}}
    openai = next(group for group in model_provider_catalog(stored) if group["id"] == "openai")
    shown = {model["id"]: model for model in openai["models"]}
    assert (shown["gpt-4o"]["labels"], shown["gpt-4o"]["fold"], shown["gpt-4o"]["legacy"]) == (["legacy"], "legacy", True)
    assert (shown["dall-e-3"]["fold"], shown["dall-e-3"]["eol"]) == ("eol", True)
    assert (shown["brand-new"]["labels"], shown["brand-new"]["fold"]) == (["unmeasured"], "unmeasured")


def test_a_model_first_met_in_a_fetched_list_takes_what_the_catalog_knows(monkeypatch):
    saved = {}

    class Store:
        def get_model_settings(self):
            return default_model_settings()

        def update_model_settings(self, settings):
            saved.update(settings)
            return settings

    monkeypatch.setattr(settings_routes, "_db", Store())
    monkeypatch.setattr(settings_routes, "_fetch_provider_model_list",
                        lambda provider_id, current: [{"id": "gpt-6-sol", "label": "gpt-6-sol"}, {"id": "dall-e-3", "label": "dall-e-3"}])
    settings_routes.api_settings_fetch_provider_models("openai")
    fetched = {model["id"]: model for model in saved["providers"]["openai"]["models"]}
    catalog = catalog_models("openai")
    assert fetched["gpt-6-sol"]["comment_ja"] == catalog["gpt-6-sol"]["comment_ja"]
    # Listed again means offered: the catalog's end-of-life mark is not taken.
    assert not fetched["dall-e-3"].get("eol")
