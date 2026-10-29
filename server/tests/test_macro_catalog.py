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


def test_only_enabled_bundled_package_selects_shared_edition(monkeypatch):
    monkeypatch.setattr(macro_catalog.PLUGIN_PACKAGE_MANAGER, "is_enabled", lambda _id: True)
    assert macro_catalog._installed_candidates() == ([], ["Nature.leaves"])
    monkeypatch.setattr(macro_catalog.PLUGIN_PACKAGE_MANAGER, "is_enabled", lambda _id: False)
    assert macro_catalog._installed_candidates() == ([], [])


def test_new_work_catalog_keeps_canonical_entries_before_packages(monkeypatch):
    definition = {
        "schema": "inku.macro-definition.v1",
        "namespace": "Example",
        "heading": "Quiet",
        "version": "1.0.0",
        "parameters": {},
        "components": {},
        "body": [],
    }
    monkeypatch.setattr(macro_catalog.PLUGIN_PACKAGE_MANAGER, "is_enabled", lambda _id: True)
    monkeypatch.setattr(macro_catalog.PLUGIN_PACKAGE_MANAGER, "catalog_candidates", lambda _lang: [])
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
    assert resolved["diagnostics"] == []
