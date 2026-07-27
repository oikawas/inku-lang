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
        ("ja", "auto", 17_971, "3000bee8a2e241d6"),
        ("ja", "sparse", 18_281, "194d36c765218595"),
        ("ja", "none", 18_353, "0f4495440b181fce"),
        ("en", "auto", 16_850, "e680f73ee6fab57a"),
        ("en", "sparse", 17_079, "ec03b0fbdd7e70ae"),
        ("en", "none", 17_215, "65932837ce9e6c9e"),
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
        ("中心に円を置く。", "ja", 18_658, "373b7cbf3134c8d5"),
        ("雨上がりの水面に光が散る。", "ja", 18_806, "43b077215a31f374"),
        ("Place one circle at the center.", "en", 17_524, "204745e66dcef798"),
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
    assert _digest(first_base) == _digest(second_base) == "3000bee8a2e241d6"


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
    assert len(composer.SYSTEM_PROMPT.encode("utf-8")) == 42_795
    assert _digest(composer.SYSTEM_PROMPT) == "1dd998b61016daf0"
    assert len(composer.SYSTEM_PROMPT_EN.encode("utf-8")) == 40_947
    assert _digest(composer.SYSTEM_PROMPT_EN) == "f7f202b29f16392a"
    # render engine 15 で `ground.absorbency` を退役させた分だけ tool schema が縮む
    # (18_021 -> 17_696)。系統プロンプト本文の 2 件は動いていない。
    assert len(tool_json.encode("utf-8")) == 17_696
    assert _digest(tool_json) == "c1f0297268da2bd2"
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "d33cd2269158e84f"
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT_EN) == "2665585415fec6df"


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
        "ja": (18_007, "7671738818af4a48"),
        "en": (16_868, "75f2108fbcd9b4f2"),
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
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "a9196f95581a9098"
    assert _digest(composer.SYSTEM_PROMPT) == system_only_digest == "1dd998b61016daf0"


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
