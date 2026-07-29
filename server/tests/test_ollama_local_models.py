"""The local Ollama model list carries what was measured, and the web copy agrees.

The list this guards replaced three names (`llama3.2`, `gpt-oss:20b`, `qwen3:8b`)
that were none of the eleven models the local-LLM track actually ran. Nothing failed
while they sat there, because a model list is only read by a dropdown -- which is why
the drift needs a test rather than a reviewer.
"""

from __future__ import annotations

import re
from pathlib import Path

from inku_server.model_settings import (
    PROVIDER_DEFINITIONS,
    model_provider_catalog,
    normalize_model_settings,
)
from inku_server.verified_model_catalog import (
    MODEL_CONFIG_VERSION,
    VERIFIED_OLLAMA_LOCAL_MODELS,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_MODELS_TS = _REPO_ROOT / "web" / "src" / "lib" / "models.ts"

_BY_ID = {str(provider["id"]): provider for provider in PROVIDER_DEFINITIONS}

# The pairing settled 2026-07-29: Stage 1 reads the description, Stage 2 writes the
# Score, and the model that wins is not the same one.
STAGE1_RECOMMENDED = "qwen3.5:4b-q4_K_M"
STAGE2_RECOMMENDED = "ministral-3:8b-instruct-2512-q4_K_M"

RETIRED_PLACEHOLDERS = {"llama3.2", "gpt-oss:20b", "qwen3:8b"}


def _local_model_ids() -> list[str]:
    return [str(model["id"]) for model in _BY_ID["ollama"]["models"]]


def test_provider_lists_the_measured_models() -> None:
    assert _BY_ID["ollama"]["models"] is VERIFIED_OLLAMA_LOCAL_MODELS
    ids = _local_model_ids()
    assert len(ids) == 10
    assert RETIRED_PLACEHOLDERS.isdisjoint(ids)


def test_both_recommended_stages_are_listed() -> None:
    ids = _local_model_ids()
    assert STAGE1_RECOMMENDED in ids
    assert STAGE2_RECOMMENDED in ids


def test_tags_name_the_quantization() -> None:
    # A bare tag is a moving target upstream, so it would not stay attached to the
    # measurement written beside it.
    for model_id in _local_model_ids():
        assert re.search(r"-q\d", model_id), model_id


def test_every_entry_carries_what_was_measured() -> None:
    for model in VERIFIED_OLLAMA_LOCAL_MODELS:
        assert model["purposes"] == ["llm"]
        assert str(model["speed_label"]).strip()
        for key in ("comment_ja", "comment_en"):
            comment = str(model[key])
            assert comment.strip()
            # Every number here came off one GPU-less machine, and a reader picking a
            # model needs to know that before reading the timing.
            assert ("機体" in comment) or ("machine" in comment)


def test_recommendation_levels_stay_absent() -> None:
    # SCORING-DESIGN.md defines the 1-5 scale on success rate, schema violations and
    # correction count over nine attempts against NIM. This track measured neither of
    # those axes, so a level here would be a number with no method behind it -- the
    # same reason the Ollama Cloud entries carry none. Measure those axes before
    # deleting this test.
    for model in VERIFIED_OLLAMA_LOCAL_MODELS:
        assert "recommendation_llm" not in model
        assert "recommendation_vision" not in model
        assert "recommendation_level" not in model


def test_web_fallback_list_matches_the_catalog() -> None:
    # The web list is what the settings pane shows until the API catalog arrives.
    # It holds no comments, so the only thing that can drift is the ids -- and it
    # drifts silently, since a stale fallback still renders.
    source = _WEB_MODELS_TS.read_text(encoding="utf-8")
    start = source.index("id: 'ollama',")
    end = source.index("id: 'ollama-cloud',")
    block = source[start:end]
    web_ids = [m.group(1) for m in re.finditer(r"id: 'ollama:([^']+)'", block)]
    assert web_ids == _local_model_ids()


# --------------------------------------------------------------------------
# A stored catalog must not outlive the measurements it was written against.
#
# pentala's saved settings held eleven Ollama ids carrying id, label and purposes and
# nothing else -- a list refreshed from the live endpoint, which has no comments to
# give. Since a stored list replaces the builtin one wholesale, every measurement
# written into the catalog would have been invisible on that installation.
# --------------------------------------------------------------------------

def _stored(catalog_version: str) -> dict:
    return {
        "model_catalog_version": catalog_version,
        "providers": {
            "ollama": {
                "active": True,
                "models": [
                    {"id": STAGE2_RECOMMENDED, "label": STAGE2_RECOMMENDED},
                    {"id": "some-model-only-this-machine-pulled", "label": "local pull"},
                ],
            }
        },
    }


def _ollama_models(settings: dict) -> dict[str, dict]:
    return {
        str(model["id"]): model
        for model in settings["providers"]["ollama"]["models"]
    }


def _stored_with_stale_metadata(catalog_version: str) -> dict:
    stored = _stored(catalog_version)
    stored["providers"]["ollama"]["models"][0].update({
        "speed_label": "計測前の古い値",
        "comment_ja": "計測前の古い説明",
        "comment_en": "a comment written before the measurements",
    })
    return stored


def test_version_bump_lays_measurements_back_over_a_bare_stored_list() -> None:
    models = _ollama_models(normalize_model_settings(_stored("2.2.0")))
    recommended = models[STAGE2_RECOMMENDED]
    assert recommended["speed_label"] == "1 件 50〜576s"
    assert "被覆 20/28" in str(recommended["comment_ja"])


def test_version_bump_replaces_stale_metadata_the_stored_entry_carries() -> None:
    # The bare-list case above passes on the merge order alone, since a stored entry
    # with no metadata cannot overwrite anything. The overlay earns its place here:
    # a stored entry that carries its own measurements from an older catalog.
    models = _ollama_models(normalize_model_settings(_stored_with_stale_metadata("2.2.0")))
    recommended = models[STAGE2_RECOMMENDED]
    assert recommended["speed_label"] == "1 件 50〜576s"
    assert "被覆 20/28" in str(recommended["comment_ja"])


def test_unchanged_version_keeps_the_metadata_the_stored_entry_carries() -> None:
    models = _ollama_models(
        normalize_model_settings(_stored_with_stale_metadata(MODEL_CONFIG_VERSION)))
    assert models[STAGE2_RECOMMENDED]["speed_label"] == "計測前の古い値"


def test_the_stored_list_still_decides_which_models_exist() -> None:
    # Refreshing metadata must not resurrect ids the installation dropped, nor discard
    # ids it pulled locally that no catalog knows.
    models = _ollama_models(normalize_model_settings(_stored("2.2.0")))
    assert set(models) == {STAGE2_RECOMMENDED, "some-model-only-this-machine-pulled"}


def test_an_unchanged_catalog_version_leaves_the_stored_entries_alone() -> None:
    models = _ollama_models(normalize_model_settings(_stored(MODEL_CONFIG_VERSION)))
    assert "speed_label" not in models[STAGE2_RECOMMENDED]


def test_nvidia_keeps_stored_metadata_while_the_version_holds() -> None:
    # NVIDIA takes the merge branch on every load, not only on a bump, so the "only
    # overwrite when the catalog moved" guard is the sole thing keeping an
    # installation's own edits. The Ollama tests cannot see this: for them the branch
    # is skipped entirely while the version matches.
    settings = normalize_model_settings({
        "model_catalog_version": MODEL_CONFIG_VERSION,
        "providers": {
            "nvidia": {
                "active": True,
                "models": [{
                    "id": "google/gemma-4-31b-it",
                    "label": "Google Gemma 4 31B Instruct",
                    "speed_label": "この設置での実測",
                }],
            }
        },
    })
    by_id = {str(m["id"]): m for m in settings["providers"]["nvidia"]["models"]}
    assert by_id["google/gemma-4-31b-it"]["speed_label"] == "この設置での実測"


def test_nvidia_fills_a_bare_stored_entry_from_the_catalog() -> None:
    # Without a bump the overlay does not run, so a stored entry that carries no
    # metadata gets it from the builtin entry underneath it in the merge.
    settings = normalize_model_settings({
        "model_catalog_version": MODEL_CONFIG_VERSION,
        "providers": {
            "nvidia": {"active": True, "models": [{"id": "google/gemma-4-31b-it"}]},
        },
    })
    by_id = {str(m["id"]): m for m in settings["providers"]["nvidia"]["models"]}
    assert by_id["google/gemma-4-31b-it"]["recommendation_llm"] == 4
    assert "Vision 再現率 1.00" in str(by_id["google/gemma-4-31b-it"]["comment_ja"])


def test_nvidia_still_keeps_builtin_models_the_stored_list_dropped() -> None:
    # Artworks name NVIDIA models, so an id missing from the stored list must not
    # vanish from the catalog -- that behaviour predates this change and stays.
    settings = normalize_model_settings({
        "model_catalog_version": "2.2.0",
        "providers": {"nvidia": {"active": True, "models": [{"id": "google/gemma-4-31b-it"}]}},
    })
    ids = {str(model["id"]) for model in settings["providers"]["nvidia"]["models"]}
    assert "meta/llama-3.3-70b-instruct" in ids
    assert len(ids) > 1


# --------------------------------------------------------------------------
# Speed is shown while experimenting and withheld from a release.
#
# Decided 2026-07-27: with no GPU here there is no speed to promise, so a release
# does not present one. Decided 2026-07-29: the numbers still help locally, so they
# survive in developer mode. The provider itself is never hidden -- running without
# an API key is the whole point of listing it.
# --------------------------------------------------------------------------

def _catalog_provider(*, include_developer: bool) -> dict:
    catalog = model_provider_catalog(None, include_developer=include_developer)
    return {str(provider["id"]): provider for provider in catalog}["ollama"]


def test_the_provider_is_listed_without_developer_mode() -> None:
    provider = _catalog_provider(include_developer=False)
    ids = [str(model["id"]) for model in provider["models"]]
    assert STAGE1_RECOMMENDED in ids
    assert STAGE2_RECOMMENDED in ids
    assert len(ids) == 10


def test_a_release_shows_no_speed_for_local_ollama() -> None:
    for model in _catalog_provider(include_developer=False)["models"]:
        assert "speed_label" not in model, model["id"]
        assert "speed_class" not in model, model["id"]
        # What was measured about quality still shows; only the timing is withheld.
        assert str(model["comment_ja"]).strip()


def test_developer_mode_shows_the_measured_timings() -> None:
    by_id = {str(m["id"]): m for m in _catalog_provider(include_developer=True)["models"]}
    assert by_id[STAGE2_RECOMMENDED]["speed_label"] == "1 件 50〜576s"


def test_other_providers_keep_their_speed() -> None:
    # The 2026-07-27 decision was about this track. Labels measured against providers
    # that fix their own ids are out of its scope and stay where they are.
    release = {
        str(provider["id"]): provider
        for provider in model_provider_catalog(None, include_developer=False)
    }
    cloud = {str(m["id"]): m for m in release["ollama-cloud"]["models"]}
    assert cloud["gemma4:31b"]["speed_label"] == "1〜110s"
    # NVIDIA is `developer_only`, so a release hides the provider outright -- there is
    # no release view of its labels to check.
    assert "nvidia" not in release
    developer = {
        str(provider["id"]): provider
        for provider in model_provider_catalog(None, include_developer=True)
    }
    nvidia = {str(m["id"]): m for m in developer["nvidia"]["models"]}
    assert nvidia["google/gemma-4-31b-it"]["speed_label"] == "昼 221s / 夕 114s / 深夜 199s"


def test_hiding_speed_does_not_touch_what_is_stored() -> None:
    # Developer mode changes what is shown, never what is saved. A release that
    # stripped the stored copy would lose the numbers for good on the next save.
    stored = normalize_model_settings(None)
    by_id = {str(m["id"]): m for m in stored["providers"]["ollama"]["models"]}
    assert by_id[STAGE2_RECOMMENDED]["speed_label"] == "1 件 50〜576s"
