"""Plugin example checks retain core diagnostics and resource omissions."""

from inku_server import pipeline_compat
from inku_server.plugins.packages import PackageWord


def test_example_reasons_keep_objects_and_ignore_entries_without_reasons(monkeypatch):
    diagnostics = {"type": "missing_place_action"}
    budget = {"kind": "budget_exceeded", "value": {"dimension": "object_templates"}}
    view = {"delivery": {"outcome": "stopped", "upstream_diagnostics": [{"reason": diagnostics}, {}],
                         "downstream_diagnostics": [{"reason": "legacy_reason"}],
                         "resource_omissions": [{"cause": {"reason": budget}}, {"cause": {}}]},
            "result": None}

    class Service:
        def start(self, *_args, **_kwargs):
            return view

    monkeypatch.setattr(pipeline_compat, "_service", lambda: Service())
    monkeypatch.setattr(pipeline_compat, "_wait", lambda _owner, result, _reader: result)
    result = pipeline_compat.draw_plugin_example("owner", "｛語｝。", "ja", [])
    assert result.reasons == (diagnostics, "legacy_reason", budget)


def test_default_examples_distinguish_objects_and_scenes():
    definition = {"id": "thing", "names": {"ja": ["物"], "en": ["thing"]}, "kind": "object"}
    word = PackageWord(definition=definition, note={}, example={})
    assert word.example_for("ja") == "｛物｝を置く。"
    assert word.example_for("en") == "Place {thing}."
    scene = PackageWord(definition={**definition, "kind": "scene"}, note={}, example={})
    assert scene.example_for("ja") == "｛物｝。"
    assert scene.example_for("en") == "{thing}."
    explicit = PackageWord(definition=definition, note={}, example={"ja": "｛物｝。"})
    assert explicit.example_for("ja") == "｛物｝。"
