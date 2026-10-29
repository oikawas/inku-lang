"""A plugin sentence the compiler withheld is explained with the host's lists.

The shared explainer needs the enabled names, the installed-but-disabled names,
and the names this work may use from its own saved or imported definitions.
"""

from __future__ import annotations

import json

from inku_server import macro_catalog


class _Binding:
    def __init__(self) -> None:
        self.received: dict | None = None

    def explain_plugin_diagnostics(self, payload: bytes) -> bytes:
        self.received = json.loads(payload)
        return json.dumps({"schema": "inku.plugin-diagnostics.v1", "plugins": [{"name": "Old.Mark"}]}).encode()


def test_work_plugins_count_as_enabled_and_disabled_documents_are_named(monkeypatch):
    monkeypatch.setattr(macro_catalog, "_installed_plugin_names", lambda: (["Nature.若葉"], ["Old.Mark"]))
    binding = _Binding()
    diagnostics = [{"reason": "macro_resolution_missing_lock", "span": {"start_byte": 0, "end_byte": 9}}]
    explained = macro_catalog.explain_plugin_diagnostics(binding, "Old.Mark。", diagnostics, ["Studio.Mark"])
    assert explained == [{"name": "Old.Mark"}]
    plugin_names = binding.received.pop("plugin_names")
    assert any(item["qualified_name"] == "Nature.YoungLeaves" and item["name"] == "若葉"
               and item["enabled"] for item in plugin_names)
    assert binding.received == {
        "source": "Old.Mark。",
        "upstream_diagnostics": diagnostics,
        "enabled": ["Nature.若葉", "Studio.Mark"],
        "disabled": ["Old.Mark"],
    }


def test_no_diagnostics_or_an_older_wheel_explains_nothing(monkeypatch):
    monkeypatch.setattr(macro_catalog, "_installed_plugin_names", lambda: ([], []))
    assert macro_catalog.explain_plugin_diagnostics(_Binding(), "x", []) == []
    assert macro_catalog.explain_plugin_diagnostics(object(), "x", [{"reason": "r"}]) == []


def test_work_v2_visible_names_reach_the_shared_explainer(monkeypatch):
    monkeypatch.setattr(macro_catalog, "_installed_plugin_names", lambda: ([], []))
    binding = _Binding()
    macro_catalog.explain_plugin_diagnostics(
        binding, "｛星｝。", [{"reason": "macro_resolution_missing_lock"}],
        [{"name": "星", "qualified_name": "Studio.Stars"}],
    )
    assert {"name": "星", "qualified_name": "Studio.Stars", "enabled": True} in binding.received["plugin_names"]
    assert "Studio.Stars" in binding.received["enabled"]


def test_retired_v2_identifier_is_explained_even_when_disabled(monkeypatch):
    from inku_server.pipeline_candidate import PipelineBinding

    manager = macro_catalog.PLUGIN_PACKAGE_MANAGER
    monkeypatch.setattr(manager, "packages", lambda: [])
    monkeypatch.setattr(manager, "is_enabled", lambda _package: False)
    source = "Nature.YoungLeaves。"
    diagnostics = [{"reason": "plugin_old_notation", "span": {"start_byte": 0, "end_byte": len("Nature.YoungLeaves".encode())}}]
    result = macro_catalog.explain_plugin_diagnostics(PipelineBinding(), source, diagnostics)
    assert result[0]["reason"] == "plugin_old_notation"


def test_run_offer_projection_uses_saved_names_and_includes_chunk_rewrite():
    definition = {"namespace": "Sky", "id": "Stars", "names": {"ja": ["星"], "en": ["stars"]}}
    offer = {"offered": [{"qualified_name": "Sky.Stars", "reason": "brace"}], "omitted": []}
    config = {"definitions": [definition], "plugin_offers": [{"stage": "generate_normalized_ddl", "offer": offer}]}
    records = macro_catalog.plugin_offer_records(config, [{"stage": "chunk_rewrite", "offer": {"offered": [], "omitted": []}}])
    assert records[0]["offered"] == [{"qualified_name": "Sky.Stars", "reason": "brace", "written_ja": "｛星｝", "written_en": "{stars}"}]
    assert records[1] == {"stage": "chunk_rewrite", "offered": [], "omitted": []}
    old = {"definitions": [{"namespace": "Nature", "heading": "YoungLeaves", "aliases": ["若葉"]}],
           "plugin_offers": [{"stage": "generate_normalized_ddl", "offer": {"offered": [{"qualified_name": "Nature.YoungLeaves", "reason": "name"}], "omitted": []}}]}
    item = macro_catalog.plugin_offer_records(old)[0]["offered"][0]
    assert (item["written_ja"], item["written_en"]) == ("Nature.YoungLeaves", "Nature.YoungLeaves")
    old["definitions"][0]["names"] = {"ja": ["若葉", "わかば"]}
    item = macro_catalog.plugin_offer_records(old)[0]["offered"][0]
    assert (item["written_ja"], item["written_en"]) == ("｛若葉｝", "Nature.YoungLeaves")
    old["definitions"] = []
    item = macro_catalog.plugin_offer_records(old)[0]["offered"][0]
    assert (item["written_ja"], item["written_en"]) == ("Nature.YoungLeaves", "Nature.YoungLeaves")
    old["plugin_offers"][0]["offer"]["offered"][0]["written_en"] = "{existing name}"
    assert macro_catalog.plugin_offer_records(old)[0]["offered"][0]["written_en"] == "{existing name}"
