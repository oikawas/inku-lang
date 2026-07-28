"""Prompt provenance digest contract tests."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import replace

import pytest

from inku_server import composer, db, interpreter, saijiki
from inku_server.plugins import DOCUMENT_PLUGIN_MANAGER
from inku_server.schema import Score


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@pytest.fixture
def empty_plugin_vocabulary(monkeypatch):
    monkeypatch.setattr(DOCUMENT_PLUGIN_MANAGER, "prompt_vocabulary", lambda lang: ())


@pytest.mark.usefixtures("empty_plugin_vocabulary")
@pytest.mark.parametrize(
    ("lang", "tenkei", "expected_bytes", "expected_digest"),
    [
        ("ja", "auto", 18_945, "a50ceaa1138ac8f4"),
        ("ja", "sparse", 19_255, "0952e40f3a8dc757"),
        ("ja", "none", 19_327, "11f2d6d206fca1cb"),
        ("en", "auto", 17_932, "7a1ea18f2685b944"),
        ("en", "sparse", 18_161, "54e0c4f0f935d2ac"),
        ("en", "none", 18_297, "1e26f874069f08ae"),
    ],
)
def test_stage1_prompt_base_digest_expected_values(
    lang: str,
    tenkei: str,
    expected_bytes: int,
    expected_digest: str,
):
    _, base_prompt = interpreter._build_system_prompt_parts(
        "入力文は不変部へ入らない。",
        lang=lang,
        tenkei=tenkei,
    )
    assert len(base_prompt.encode("utf-8")) == expected_bytes
    assert _digest(base_prompt) == expected_digest


@pytest.mark.usefixtures("empty_plugin_vocabulary")
@pytest.mark.parametrize(
    ("text", "lang", "expected_bytes", "expected_digest"),
    [
        ("中心に円を置く。", "ja", 19_632, "cb7bde41b09ae905"),
        ("雨上がりの水面に光が散る。", "ja", 19_801, "19918391c0beee87"),
        ("Place one circle at the center.", "en", 18_606, "7231fea935d1c2a5"),
    ],
)
def test_stage1_actual_prompt_digest_expected_values(
    text: str,
    lang: str,
    expected_bytes: int,
    expected_digest: str,
):
    prompt, _ = interpreter._build_system_prompt_parts(text, lang=lang)
    assert len(prompt.encode("utf-8")) == expected_bytes
    assert _digest(prompt) == expected_digest


@pytest.mark.usefixtures("empty_plugin_vocabulary")
def test_stage1_base_digest_excludes_input_dependent_examples():
    first_prompt, first_base = interpreter._build_system_prompt_parts("中心に円を置く。")
    second_prompt, second_base = interpreter._build_system_prompt_parts(
        "雨上がりの水面に光が散る。"
    )
    assert _digest(first_prompt) != _digest(second_prompt)
    assert _digest(first_base) == _digest(second_base) == "a50ceaa1138ac8f4"


@pytest.mark.usefixtures("empty_plugin_vocabulary")
def test_stage1_digest_uses_the_actual_prefix_override(monkeypatch):
    metadata: dict[str, str] = {}
    monkeypatch.setattr(interpreter, "_current_model_settings", lambda: {})
    monkeypatch.setattr(
        interpreter,
        "provider_for_model",
        lambda model, stage, settings: ("openai", "test-model"),
    )
    monkeypatch.setattr(
        interpreter,
        "_interpret_openai_detail",
        lambda *args, **kwargs: ("黒い円を置く。", None, 1, 2),
    )
    interpreter.interpret_detail(
        "中心に円を置く。",
        model="test-model",
        system_prompt_prefix="override-prefix",
        prompt_metadata=metadata,
    )
    actual_prompt, actual_base = interpreter._build_system_prompt_parts(
        "中心に円を置く。",
        prefix_override="override-prefix",
    )
    assert metadata == {
        "stage1_prompt_digest": _digest(actual_prompt),
        "stage1_prompt_base_digest": _digest(actual_base),
    }
    assert metadata["stage1_prompt_base_digest"] != "611c81f7023ae43c"


def test_stage2_prompt_and_tool_expected_values():
    tool_json = json.dumps(composer._submit_tool(), ensure_ascii=False, sort_keys=True)
    assert len(composer.SYSTEM_PROMPT.encode("utf-8")) == 43_822
    assert _digest(composer.SYSTEM_PROMPT) == "1169084a389f8a08"
    assert len(composer.SYSTEM_PROMPT_EN.encode("utf-8")) == 41_887
    assert _digest(composer.SYSTEM_PROMPT_EN) == "e02fe62bc805b9b3"
    # `hair` -> `silverpoint` の改名で、Stage 2 の素材語対応表 2 行と作例 8 件、
    # そして weight の enum と description が動いた。tool schema は 17_696 -> 17_713。
    # 色選択の一行が `palette` を捨てて `抽象色` / `the abstract colors` になった
    # (2026-07-27)。**日本語はバイト数が動かない**ので、長さだけを見る検査は素通りする。
    # プロンプト内部矛盾の解消で、Stage 2 の背景規則 2 行・作例 5 件と
    # background の description が動いた。tool schema は 17_713 -> 17_764 (2026-07-27)。
    # engine 16 段 3 (太さの軸) で、Stage 2 の変換表 2 つ (日英) と作例 4 件が入り、
    # `thinness` の enum + description が tool schema に出た。17_764 -> 18_064。
    assert len(tool_json.encode("utf-8")) == 18_064
    assert _digest(tool_json) == "0e4021f1b0a3a1f9"
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "32e65db9dcb68e99"
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT_EN) == "31d357f591d4cf9b"


def test_stage2_digest_uses_the_actual_prompt_override(monkeypatch):
    metadata: dict[str, str] = {}
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                }
            ]
        }
    )
    monkeypatch.setattr(composer, "_current_model_settings", lambda: {})
    monkeypatch.setattr(
        composer,
        "provider_for_model",
        lambda model, stage, settings: ("openai", "test-model"),
    )
    monkeypatch.setattr(
        composer,
        "_compose_openai",
        lambda *args, **kwargs: (score, 1, 2),
    )
    composer.compose(
        "中央に円を置く。",
        model="test-model",
        system_prompt="override-stage2",
        prompt_metadata=metadata,
    )
    assert metadata == {
        "stage2_prompt_digest": composer._stage2_prompt_digest("override-stage2")
    }
    assert metadata["stage2_prompt_digest"] != "4c26278bb95621b2"


@pytest.mark.usefixtures("empty_plugin_vocabulary")
def test_saijiki_word_changes_both_stage1_base_digests(monkeypatch):
    original_categories = saijiki.SAIJIKI
    changed_categories = tuple(
        replace(
            category,
            words=category.words
                + (saijiki.SaijikiWord("プロッター", "plotter"),),
        )
        if category.key == "tezawari"
        else category
        for category in original_categories
    )
    expected = {
        "ja": (18_981, "0396c02e15cd4c3f"),
        "en": (17_950, "e774099a8eea2e40"),
    }
    for lang, prefix in (
        ("ja", interpreter.SYSTEM_PROMPT_PREFIX),
        ("en", interpreter.SYSTEM_PROMPT_PREFIX_EN),
    ):
        monkeypatch.setattr(saijiki, "SAIJIKI", original_categories)
        old_block = saijiki.prompt_block(lang)
        old_enumeration = saijiki.texture_material_enumeration(lang)
        monkeypatch.setattr(saijiki, "SAIJIKI", changed_categories)
        changed_prefix = prefix.replace(
            old_enumeration,
            saijiki.texture_material_enumeration(lang),
        ).replace(
            old_block,
            saijiki.prompt_block(lang),
        )
        _, base_prompt = interpreter._build_system_prompt_parts(
            "中心に円を置く。",
            prefix_override=changed_prefix,
            lang=lang,
        )
        expected_bytes, expected_digest = expected[lang]
        assert len(base_prompt.encode("utf-8")) == expected_bytes
        assert _digest(base_prompt) == expected_digest


def test_schema_description_changes_stage2_but_not_system_prompt(monkeypatch):
    original_tool = composer._submit_tool()
    changed_tool = json.loads(json.dumps(original_tool, ensure_ascii=False))

    def replace_description(value):
        if isinstance(value, dict):
            return {
                key: (
                    "質感密度 0.0-1.0（測定用の一時変更）"
                    if key == "description" and item == "質感密度 0.0-1.0"
                    else replace_description(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [replace_description(item) for item in value]
        return value

    changed_tool = replace_description(changed_tool)
    system_only_digest = _digest(composer.SYSTEM_PROMPT)
    monkeypatch.setattr(composer, "_submit_tool", lambda: changed_tool)
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "9d17d02965345445"
    assert _digest(composer.SYSTEM_PROMPT) == system_only_digest == "1169084a389f8a08"


def test_prompt_digest_history_columns_are_nullable_and_not_backfilled():
    fields = (
        "stage1_prompt_digest",
        "stage1_prompt_base_digest",
        "stage2_prompt_digest",
    )
    for field in fields:
        assert db.HistoryRow.__table__.c[field].nullable is True
        assert db._HISTORY_COLUMN_MIGRATIONS[field] == (
            f"ALTER TABLE history ADD COLUMN {field} VARCHAR"
        )
    backfill_source = inspect.getsource(db._backfill_render_hashes)
    assert all(field not in backfill_source for field in fields)
