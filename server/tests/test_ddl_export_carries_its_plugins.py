"""A DDL export carries the plugin definitions its DDL names, and reading it
back uses those definitions for the new work ahead of the installed ones."""

from __future__ import annotations

import json

import pytest

from inku_server import macro_catalog
from inku_server.ddl_export import DDL_EXPORT_SCHEMA, build_ddl_export
from inku_server.pipeline_candidate import CandidateHostError
from inku_server.pipeline_product import RunOptions


def _definition(heading: str, version: str = "1.0.0") -> dict:
    return {"schema": "inku.macro-definition.v1", "namespace": "Nature", "heading": heading,
            "version": version, "parameters": {}, "components": {}, "body": []}


def test_export_keeps_only_the_named_definitions_with_their_summaries():
    exported = build_ddl_export(
        "背景を白で埋める。\nNature.若葉。",
        "ja",
        [_definition("紅葉"), _definition("若葉"), _definition("若葉", "2.0.0")],
        ["紅葉の要約", "若葉の要約", "重複"],
        {"build_number": "1104"},
    )
    assert exported["schema"] == DDL_EXPORT_SCHEMA
    assert exported["ddl"].endswith("Nature.若葉。")
    assert exported["plugins"] == [{"definition": _definition("若葉"), "summary": "若葉の要約"}]
    assert build_ddl_export("中央に赤い円を置く。", "ja")["plugins"] == []


class _FirstWins:
    """The shared resolver's contract: the first candidate of a name wins."""

    def resolve_macro_catalog(self, payload: bytes) -> bytes:
        source = json.loads(payload)
        entries, diagnostics, seen = [], [], set()
        for item in source["canonical"]:
            definition = json.loads(item["definition_json"])
            name = f"{definition['namespace']}.{definition['heading']}"
            if name in seen:
                diagnostics.append({"source_id": item["source_id"], "qualified_name": name,
                                    "disposition": "omitted", "reason": "duplicate_qualified_name"})
                continue
            seen.add(name)
            entries.append({"source_id": item["source_id"], "definition": definition, "summary": item["summary"],
                            "qualified_name": name, "version": definition["version"], "digest": definition["version"]})
        locks = [{"qualified_name": e["qualified_name"], "version": e["version"], "digest": e["digest"]} for e in entries]
        return json.dumps({"schema": "inku.macro-catalog-resolution.v1", "entries": entries,
                           "locks": locks, "diagnostics": diagnostics}).encode()


def _config(*definitions: dict) -> dict:
    return {"prompt_limits": {"max_catalog_entries": 64}, "language": "ja",
            "definitions": list(definitions), "macro_summaries": ["installed"] * len(definitions)}


def test_imported_definitions_win_and_say_when_they_differ_or_are_new(monkeypatch):
    monkeypatch.setattr(macro_catalog, "_installed_candidates", lambda: ([], []))
    imported = [
        {"definition": _definition("若葉", "9.0.0"), "summary": "持ち込んだ若葉"},
        {"definition": _definition("紅葉"), "summary": ""},
        {"definition": _definition("青葉"), "summary": "持ち込んだ青葉"},
    ]
    catalog = macro_catalog.resolve_new_work_macro_catalog(
        _FirstWins(), _config(_definition("若葉"), _definition("紅葉")), imported
    )
    assert [d["version"] for d in catalog["definitions"] if d["heading"] == "若葉"] == ["9.0.0"]
    assert catalog["macro_summaries"][:3] == ["持ち込んだ若葉", "Nature.紅葉", "持ち込んだ青葉"]
    reasons = {(d["qualified_name"], d["reason"]) for d in catalog["diagnostics"]}
    assert reasons == {
        ("Nature.若葉", "imported_plugin_differs_from_installed"),
        ("Nature.青葉", "imported_plugin_not_installed"),
    }


def test_imported_plugins_are_bounded_options_for_a_new_work_only():
    assert RunOptions.model_validate({"imported_plugins": [{"definition": _definition("若葉")}]}).imported_plugins
    with pytest.raises(ValueError):
        RunOptions.model_validate({"imported_plugins": [{"definition": {}, "extra": 1}]})
    assert CandidateHostError("imported_plugins_require_new_work")
