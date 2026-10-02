"""Request model references reach the common provider resolver unchanged."""

import pytest

from inku_server import db
from inku_server.api_core import common as api_common
from inku_server.model_settings import default_model_settings, provider_for_model
from inku_server.pipeline_provider import resolved_drawing_model


@pytest.fixture(autouse=True)
def configured_model_catalog(monkeypatch):
    monkeypatch.setattr(db, "get_model_settings", default_model_settings)


@pytest.mark.parametrize(
    "resolve_model",
    [
        pytest.param(resolved_drawing_model, id="drawing"),
        pytest.param(api_common._resolved_vision_model, id="vision"),
    ],
)
def test_explicit_model_references_use_the_common_provider_resolver(resolve_model):
    model_id = "i014-explicit-model"
    actor = {
        "model_settings": {
            "stage1_provider": "openai",
            "stage1_model": model_id,
            "vision_provider": "openai",
            "vision_model": model_id,
        }
    }
    settings = default_model_settings()
    settings.update(actor["model_settings"])
    settings["providers"]["ollama"]["models"] = [{"id": model_id, "label": model_id}]

    # Sole ownership differs from the actor's default provider. Qualifying by
    # equality would turn this explicit bare request into rule 1, skipping rule 2.
    reference = resolve_model(f"  {model_id}  ", actor)
    assert reference == model_id
    assert provider_for_model(reference, stage="stage1", settings=settings) == ("ollama", model_id)

    qualified = resolve_model("  gemini:gemini-2.5-pro  ", actor)
    assert qualified == "gemini:gemini-2.5-pro"
    assert provider_for_model(qualified, stage="stage1", settings=settings) == ("gemini", "gemini-2.5-pro")
    assert resolve_model("  qwen-api  ", actor) == "qwen-api"


def test_default_models_use_the_users_provider():
    actor = {
        "model_settings": {
            "stage1_provider": "openai",
            "stage1_model": "gpt-5.2",
            "stage2_provider": "anthropic",
            "stage2_model": "claude-sonnet-4-6",
            "vision_provider": "nvidia",
            "vision_model": "meta/llama-3.2-90b-vision-instruct",
        }
    }

    assert resolved_drawing_model(None, actor) == "openai:gpt-5.2"
    assert resolved_drawing_model("", actor) == "openai:gpt-5.2"
    assert resolved_drawing_model("gpt-5.2", actor) == "gpt-5.2"
    # One model draws both stages (2026-09-30): the stored Stage 2 choice, which
    # still differs here, is not read -- neither as the default nor to qualify.
    assert resolved_drawing_model("claude-sonnet-4-6", actor) == "claude-sonnet-4-6"
    assert api_common._resolved_vision_model(None, actor) == "nvidia:meta/llama-3.2-90b-vision-instruct"
    assert api_common._resolved_vision_model("", actor) == "nvidia:meta/llama-3.2-90b-vision-instruct"

    actor["model_settings"]["stage1_model"] = "gemini:gemini-2.5-pro"
    actor["model_settings"]["vision_model"] = "openai:gpt-4.1"
    assert resolved_drawing_model(None, actor) == "gemini:gemini-2.5-pro"
    assert api_common._resolved_vision_model(None, actor) == "openai:gpt-4.1"
