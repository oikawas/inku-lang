from __future__ import annotations

from pathlib import Path

import pytest

from inku_server.plugins.document_format import (
    PluginDocumentManager,
    PluginFormatError,
    parse_plugin_document,
)


FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "minimal-arcs.inku-plugin.md"


def fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parser_accepts_minimal_bilingual_document() -> None:
    document = parse_plugin_document(fixture_text())
    assert document.manifest.namespace == "Sketch"
    assert document.manifest.languages == ("ja", "en")
    assert document.entries[0].templates["ja"]
    assert document.entries[0].templates["en"]


def test_validator_rejects_recursive_plugin_reference() -> None:
    invalid = fixture_text().replace("細い弧を 2〜2枚", "Nature.葉を 2〜2枚")
    with pytest.raises(PluginFormatError, match="plugin references are forbidden"):
        parse_plugin_document(invalid)


def test_validator_rejects_oversize_and_stamp_templates() -> None:
    oversized = fixture_text().replace("2〜2枚", "49〜49枚")
    with pytest.raises(PluginFormatError, match="exceeds 48"):
        parse_plugin_document(oversized)
    stamped = fixture_text().replace(
        "中心の帯に置く", "中心の帯に [0.1, 0.2, 0.3, 0.4] で置く"
    )
    with pytest.raises(PluginFormatError, match="fixed coordinates"):
        parse_plugin_document(stamped)


def test_manager_rejects_namespace_and_word_collisions(tmp_path: Path) -> None:
    first = tmp_path / "a.inku-plugin.md"
    second = tmp_path / "b.inku-plugin.md"
    first.write_text(fixture_text(), encoding="utf-8")
    second.write_text(fixture_text().replace("name: twin-arcs", "name: other"), encoding="utf-8")
    items = PluginDocumentManager(tmp_path).reload()
    assert [item.status for item in items] == ["enabled", "rejected"]
    assert "qualified word collision" in items[1].reasons[0]
