from __future__ import annotations

from pathlib import Path

import pytest

from inku_server.plugins.document_format import (
    PluginDocumentManager,
    PluginFormatError,
    expand_plugin_ddl,
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


def test_expansion_is_deterministic_and_assigns_distinct_member_regions() -> None:
    document = parse_plugin_document(fixture_text())
    first = expand_plugin_ddl(
        "Sketch.双弧を描く。",
        source_text="Sketch.双弧を描く",
        lang="ja",
        documents=[document],
        seed_text="same",
    )
    second = expand_plugin_ddl(
        "Sketch.双弧を描く。",
        source_text="Sketch.双弧を描く",
        lang="ja",
        documents=[document],
        seed_text="same",
    )
    assert first == second
    assert first.ddl.count("領域 [") == 2
    regions = [part.split("]", 1)[0] for part in first.ddl.split("領域 [")[1:]]
    assert len(set(regions)) == 2
    assert first.provenance[0]["plugin_term"] == "Sketch.双弧"


def test_anchor_seven_members_expand_to_separate_bands() -> None:
    document = parse_plugin_document(fixture_text().replace("2〜2枚", "7〜7枚"))
    result = expand_plugin_ddl(
        "Sketch.双弧を描く。",
        source_text="Sketch.双弧を描く",
        lang="ja",
        documents=[document],
        seed_text="seven",
    )
    assert result.ddl.count("領域 [") == 7
    regions = [part.split("]", 1)[0] for part in result.ddl.split("領域 [")[1:]]
    assert len(set(regions)) == 7


def test_natural_trigger_and_metaphor_negative_case() -> None:
    document = parse_plugin_document(fixture_text())
    natural = expand_plugin_ddl(
        "中央に形を置く。", source_text="双弧を中央に置く", lang="ja", documents=[document]
    )
    metaphor = expand_plugin_ddl(
        "中央に形を置く。", source_text="双弧のような静けさ", lang="ja", documents=[document]
    )
    ordinary = expand_plugin_ddl(
        "中央に円を置く。", source_text="静かな円", lang="ja", documents=[document]
    )
    assert natural.provenance
    assert not metaphor.provenance
    assert ordinary.ddl == "中央に円を置く。"
    assert "Sketch." not in ordinary.ddl


def test_delete_and_reinstall_does_not_change_saved_replay_artifact(tmp_path: Path) -> None:
    plugin = tmp_path / "minimal.inku-plugin.md"
    plugin.write_text(fixture_text(), encoding="utf-8")
    manager = PluginDocumentManager(tmp_path)
    expanded = manager.expand(
        "Sketch.双弧を描く。", source_text="Sketch.双弧を描く", lang="ja"
    )
    saved_svg = "<svg><metadata>" + expanded.ddl + "</metadata></svg>"
    plugin.unlink()
    assert manager.reload() == ()
    assert saved_svg == "<svg><metadata>" + expanded.ddl + "</metadata></svg>"
    plugin.write_text(fixture_text(), encoding="utf-8")
    manager.reload()
    assert manager.expand(
        "Sketch.双弧を描く。", source_text="Sketch.双弧を描く", lang="ja"
    ).ddl == expanded.ddl


def test_stage15_and_coerce_have_no_plugin_injection_path() -> None:
    package = Path(__file__).parents[1] / "src" / "inku_server"
    for module in ("ddl_expander.py", "coerce.py"):
        source = (package / module).read_text(encoding="utf-8")
        assert "DOCUMENT_PLUGIN_MANAGER" not in source
        assert "expand_plugin_ddl" not in source


def test_pipeline_expands_before_stage15_and_stage2(monkeypatch, tmp_path: Path) -> None:
    from inku_server import api as api_module
    from inku_server.schema import Score

    plugin = tmp_path / "minimal.inku-plugin.md"
    plugin.write_text(fixture_text(), encoding="utf-8")
    manager = PluginDocumentManager(tmp_path)
    captured: list[str] = []

    def fake_compose(ddl: str, **kwargs):
        captured.append(ddl)
        return Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "arc",
                        "center": [0.5, 0.5],
                        "radius": 0.2,
                        "angle_start": 0,
                        "angle_end": 150,
                        "weight": "rotring",
                    }
                ]
            }
        )

    monkeypatch.setattr(api_module, "DOCUMENT_PLUGIN_MANAGER", manager)
    monkeypatch.setattr(api_module, "compose", fake_compose)
    explicit = api_module._call_compose_detail(
        "Sketch.双弧を描く。", original_text="Sketch.双弧を描く", lang="ja"
    )
    natural = api_module._call_compose_detail(
        "中央に形を置く。", original_text="双弧を中央に置く", lang="ja"
    )
    ordinary = api_module._call_compose_detail(
        "中央に円を置く。", original_text="静かな円", lang="ja"
    )
    assert explicit.plugin_provenance and natural.plugin_provenance
    assert not ordinary.plugin_provenance
    assert all("Sketch." not in ddl for ddl in captured)
    assert all("楕円" not in ddl for ddl in captured[:2])
    assert all(ddl.count("細い弧を 一枚") == 2 for ddl in captured[:2])
    assert explicit.score.instructions[0].primitive == "arc"


def test_thirty_general_inputs_never_emit_plugin_terms() -> None:
    document = parse_plugin_document(fixture_text())
    prompts = [f"静かな円を中央に置く {index}" for index in range(30)]
    for prompt in prompts:
        result = expand_plugin_ddl(
            "中央に黒い円を置く。", source_text=prompt, lang="ja", documents=[document]
        )
        assert not result.provenance
        assert "Sketch." not in result.ddl
