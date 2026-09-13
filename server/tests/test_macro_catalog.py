from types import SimpleNamespace

from inku_server import macro_catalog


class _Binding:
    @staticmethod
    def resolve_macro_catalog(payload: bytes) -> bytes:
        import json

        source = json.loads(payload)
        canonical = source["canonical"]
        entries = [
            {
                "source_id": item["source_id"],
                "definition": json.loads(item["definition_json"]),
                "summary": item["summary"],
                "qualified_name": "Example.Quiet",
                "version": "1.0.0",
                "digest": "abc",
            }
            for item in canonical
        ]
        return json.dumps(
            {
                "schema": "inku.macro-catalog-resolution.v1",
                "entries": entries,
                "locks": [
                    {
                        "qualified_name": item["qualified_name"],
                        "version": item["version"],
                        "digest": item["digest"],
                    }
                    for item in entries
                ],
                "diagnostics": [
                    {
                        "source_id": item["source_id"],
                        "qualified_name": item["qualified_name"],
                        "disposition": "omitted",
                        "reason": "legacy_semantics_require_authored_canonical_definition",
                        "warnings": ["legacy_plugin_format"],
                        "findings": [],
                    }
                    for item in source["legacy"]
                ],
            }
        ).encode()


def test_only_enabled_installed_bundle_selects_shared_edition(monkeypatch):
    installed = SimpleNamespace(
        source_path=str(macro_catalog.Path(macro_catalog.__file__).resolve().parents[2]
                        / "plugins/nature-leaves.inku-plugin.md"),
        manifest=SimpleNamespace(namespace="Nature", name="leaves"),
        entries=(SimpleNamespace(qualified_name=lambda namespace: f"{namespace}.若葉"),),
    )
    custom = SimpleNamespace(
        source_path="/custom/nature-leaves.inku-plugin.md",
        manifest=SimpleNamespace(namespace="Nature", name="leaves"),
        entries=(SimpleNamespace(qualified_name=lambda namespace: f"{namespace}.若葉"),),
    )
    monkeypatch.setattr(macro_catalog.DOCUMENT_PLUGIN_MANAGER, "documents", lambda: (installed, custom))
    legacy, packages = macro_catalog._installed_candidates()
    assert packages == ["Nature.leaves"]
    assert legacy == [
        {"source_id": "bundled:Nature.leaves", "qualified_name": "Nature.若葉"},
        {"source_id": "nature-leaves.inku-plugin.md", "qualified_name": "Nature.若葉"},
    ]
    monkeypatch.setattr(macro_catalog.DOCUMENT_PLUGIN_MANAGER, "documents", lambda: ())
    assert macro_catalog._installed_candidates() == ([], [])


def test_new_work_catalog_keeps_canonical_entries_and_reports_legacy_omission(monkeypatch):
    definition = {
        "schema": "inku.macro-definition.v1",
        "namespace": "Example",
        "heading": "Quiet",
        "version": "1.0.0",
        "parameters": {},
        "components": {},
        "body": [],
    }
    document = SimpleNamespace(
        source_path="legacy.inku-plugin.md",
        manifest=SimpleNamespace(namespace="Nature", name="leaves"),
        entries=(SimpleNamespace(qualified_name=lambda namespace: f"{namespace}.若葉"),),
    )
    monkeypatch.setattr(
        macro_catalog.DOCUMENT_PLUGIN_MANAGER,
        "documents",
        lambda: (document,),
    )
    resolved = macro_catalog.resolve_new_work_macro_catalog(
        _Binding(),
        {
            "definitions": [definition],
            "macro_summaries": ["Quiet mark"],
            "prompt_limits": {"max_catalog_entries": 64},
        },
    )
    assert resolved["definitions"] == [definition]
    assert resolved["macro_summaries"] == ["Quiet mark"]
    assert resolved["definition_locks"] == [
        {"qualified_name": "Example.Quiet", "version": "1.0.0", "digest": "abc"}
    ]
    assert resolved["diagnostics"][0]["qualified_name"] == "Nature.若葉"
    assert resolved["diagnostics"][0]["warnings"] == ["legacy_plugin_format"]
