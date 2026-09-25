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


def test_the_shipped_nature_document_loads_with_its_seven_words_and_previews():
    """Every expansion line of the bundled document must stay in core vocabulary,
    or the manager rejects the whole document at load."""
    from pathlib import Path

    from inku_server.plugins.document_format import MAX_PREVIEW_BYTES, entry_preview_path

    path = Path(__file__).resolve().parents[1] / "plugins" / "nature-leaves.inku-plugin.md"
    document = parse_plugin_document(path.read_text(encoding="utf-8"), source_path=str(path))
    assert [(entry.heading, entry.aliases) for entry in document.entries] == [
        ("YoungLeaves", ("若葉",)),
        ("Undergrowth", ("下草",)),
        ("SummerLeaves", ("青葉",)),
        ("AutumnLeaves", ("紅葉",)),
        ("FallenLeaves", ("落葉",)),
        ("WitheredGrass", ("枯草",)),
        ("WitheredLeaves", ("枯葉",)),
    ]
    assert document.entries[0].visible_qualified_names("Nature") == ["Nature.YoungLeaves", "Nature.若葉"]
    for entry in document.entries:
        preview = entry_preview_path(document, entry)
        assert preview is not None and 0 < preview.stat().st_size <= MAX_PREVIEW_BYTES


def test_an_alias_must_be_spellable_and_unique_in_its_document():
    base = (
        "---\nnamespace: Probe\nname: probe\nversion: 0.1.0\nauthors: [test]\nlanguages: [ja]\n"
        "license: MIT\ndescription_ja: probe\ndescription_en: probe\n---\n\n"
    )
    word = "## 語: {heading}\n\naliases: {aliases}\nsurface_ja: 円\nfires_on_ja: 円\nnote_ja: n\n\n### 展開 (ja)\n\n中心に円を置く。\n\n"
    good = base + word.format(heading="Round", aliases="円い形")
    assert parse_plugin_document(good).entries[0].aliases == ("円い形",)
    for bad in (
        base + word.format(heading="Round", aliases="円 い"),
        base + word.format(heading="Round", aliases="Round"),
        base + word.format(heading="Round", aliases="丸") + word.format(heading="Ball", aliases="丸"),
    ):
        with pytest.raises(PluginFormatError):
            parse_plugin_document(bad)

