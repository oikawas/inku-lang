"""The installed native wheel exposes the saved-work plugin migration."""

import json
from pathlib import Path

import inku_render


def test_native_plugin_name_migration_keeps_saved_lock_and_is_idempotent():
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "core/crates/inku-ddl/assets/nature-leaves-v1.json").read_text())
    definition = package["entries"][0]["definition"]
    catalog = json.loads(inku_render.pipeline_resolve_macro_catalog(json.dumps({
        "maximum_entries": 1,
        "canonical": [{"source_id": "word", "definition_json": json.dumps(definition), "summary": "leaves"}],
    }).encode()))
    entry = catalog["entries"][0]
    lock = {"qualified_name": entry["qualified_name"], "version": entry["version"], "digest": "sha256:" + entry["digest"]}
    request = {"document": {"source": "Nature.若葉。", "language": "ja", "macro_locks": [lock]}, "definitions": [definition]}
    first = json.loads(inku_render.pipeline_migrate_plugin_names(json.dumps(request, ensure_ascii=False).encode()))
    assert first["document"]["source"] == "｛若葉｝。"
    assert first["document"]["macro_locks"] == [lock]
    assert first["definitions"][0]["changed"] is False
    second = json.loads(inku_render.pipeline_migrate_plugin_names(json.dumps({
        "document": first["document"], "definitions": [first["definitions"][0]["definition"]],
    }, ensure_ascii=False).encode()))
    assert second["edits"] == []
    assert second["document"] == first["document"]
