"""A run that writes new DDL from a saved work's description offers the plugins
enabled now, as a new work does; a run that keeps the work's DDL keeps the
definitions the work was drawn with (2026-11-05, the author: a disabled plugin
was written into a work drawn again from a selected work)."""

from copy import deepcopy
import json
from types import SimpleNamespace


def _effects(monkeypatch):
    from inku_server import db, pipeline_product
    from inku_server.api_core import common
    from inku_server.pipeline_defaults import default_manifest

    binding = SimpleNamespace(
        canvas_registry={"registry": {"schema": "fixture", "formats": []}, "digest": "fixture"},
        resolve_palette=lambda _request: json.dumps({"schema": "fixture-palette"}).encode(),
    )
    manifest = default_manifest(binding)
    monkeypatch.setattr(db, "get_user", lambda _owner: {"id": "author"})
    monkeypatch.setattr(db, "get_model_settings", lambda: {})
    monkeypatch.setattr(common, "_model_offered_to", lambda *_args, **_kwargs: True)
    enabled_now = {
        "definitions": [{"namespace": "Sky", "id": "enabled"}],
        "macro_summaries": [{"name": "enabled"}],
        "definition_locks": [{"definition": "Sky.enabled"}],
        "diagnostics": [],
    }
    monkeypatch.setattr(pipeline_product, "resolve_new_work_macro_catalog",
                        lambda _binding, _config, imported: deepcopy(enabled_now))
    saved = deepcopy(manifest["pipeline"])
    saved["definitions"] = [{"namespace": "Water", "id": "disabled_now"}]
    saved["macro_summaries"] = [{"name": "disabled_now"}]
    work = {
        "saved_config": saved,
        "macro_catalog": {"definition_locks": [{"definition": "Water.disabled_now"}], "diagnostics": []},
        "host_options": {},
        "metadata": {},
    }
    return pipeline_product.ProductPipelineEffects(binding, manifest), work, enabled_now


def test_description_fork_offers_the_plugins_enabled_now(monkeypatch):
    effects, work, enabled_now = _effects(monkeypatch)
    before = deepcopy(work)
    config, context = effects.prepare("author", "description", "大海の　磯もとどろに", {
        "instruction_lang": "ja", "stage1_model": "openai:fixture", "render_seed": 17,
    }, work)
    assert config["definitions"] == enabled_now["definitions"]
    assert config["macro_summaries"] == enabled_now["macro_summaries"]
    assert context["macro_catalog"] == {"definition_locks": enabled_now["definition_locks"], "diagnostics": []}
    assert work == before


def test_ddl_fork_keeps_the_definitions_the_work_was_drawn_with(monkeypatch):
    effects, work, _enabled_now = _effects(monkeypatch)
    config, context = effects.prepare("author", "direct_ddl", "｛海｝。", {
        "instruction_lang": "ja", "stage1_model": "openai:fixture", "render_seed": 17,
    }, work)
    assert config["definitions"] == work["saved_config"]["definitions"]
    assert config["macro_summaries"] == work["saved_config"]["macro_summaries"]
    assert context["macro_catalog"] == work["macro_catalog"]
