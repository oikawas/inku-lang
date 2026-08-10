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
    ("lang", "expected_bytes", "expected_digest"),
    [
        # 契約 background-color-openness (2026-08-02): Stage 1 の背景 3 行が動いた。
        # 添景水準の 3 行 (v2.11.0 で廃止) が抜けたので、残るのは水準なしの 1 行ずつ。
        # 値は旧 auto と同一 — auto は規範文を足していなかった。
        ("ja", 18_981, "1430ea03025e3f8c"),
        ("en", 18_020, "b056eb26fc3748ef"),
    ],
)
def test_stage1_prompt_base_digest_expected_values(
    lang: str,
    expected_bytes: int,
    expected_digest: str,
):
    _, base_prompt = interpreter._build_system_prompt_parts(
        "入力文は不変部へ入らない。",
        lang=lang,
    )
    assert len(base_prompt.encode("utf-8")) == expected_bytes
    assert _digest(base_prompt) == expected_digest


@pytest.mark.usefixtures("empty_plugin_vocabulary")
@pytest.mark.parametrize(
    ("text", "lang", "expected_bytes", "expected_digest"),
    [
        ("中心に円を置く。", "ja", 19_668, "e1e1a3563ea0e35f"),
        ("雨上がりの水面に光が散る。", "ja", 19_837, "1f49d277ab509e0d"),
        ("Place one circle at the center.", "en", 18_694, "246ae8b96397bf7c"),
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
    assert _digest(first_base) == _digest(second_base) == "1430ea03025e3f8c"


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
    assert len(composer.SYSTEM_PROMPT.encode("utf-8")) == 44_589
    assert _digest(composer.SYSTEM_PROMPT) == "1612296fc2102f90"
    assert len(composer.SYSTEM_PROMPT_EN.encode("utf-8")) == 42_585
    assert _digest(composer.SYSTEM_PROMPT_EN) == "ffee4a72b70fbdee"
    # `hair` -> `silverpoint` の改名で、Stage 2 の素材語対応表 2 行と作例 8 件、
    # そして weight の enum と description が動いた。tool schema は 17_696 -> 17_713。
    # 色選択の一行が `palette` を捨てて `抽象色` / `the abstract colors` になった
    # (2026-07-27)。**日本語はバイト数が動かない**ので、長さだけを見る検査は素通りする。
    # プロンプト内部矛盾の解消で、Stage 2 の背景規則 2 行・作例 5 件と
    # background の description が動いた。tool schema は 17_713 -> 17_764 (2026-07-27)。
    # engine 16 段 3 (太さの軸) で、Stage 2 の変換表 2 つ (日英) と作例 4 件が入り、
    # `thinness` の enum + description が tool schema に出た。17_764 -> 18_257。
    # The nine-color enum and both color descriptions expand the tool schema.
    assert len(tool_json.encode("utf-8")) == 18_492
    assert _digest(tool_json) == "c1c12877ef486469"
    # `thinness` を `weight` の直後から末尾へ移し (搬送 18% -> 89%)、
    # `_stage2_prompt_digest` の `sort_keys=True` を外して指紋を並び順に開いた
    # (I-036 / I-038)。**上の 2 行はここで動かない** — この tool_json は
    # テスト側で `sort_keys=True` を掛けており、並びを潰しているため。
    # 動くのは並びを見るようになった下の 2 行だけ (2026-07-29)。
    # 契約 background-color-openness (2026-08-02): 背景規則 3 行 (日英) が九色へ開いた。
    # **tool schema は動いていない** (18_492 / c1c1... のまま) — enum は既に九色だった。
    # 契約 stage2-score-shrinkage (2026-08-03): `thinness` を末尾から `surface` の直前へ
    # 移し、末尾を `surface` へ返した (surface の搬送 42% -> 92%)。**ここでも上の 2 行は
    # 動かない** — sort_keys が並びを潰すため。動くのは並びを見る下の 2 行だけ。
    # 契約 one-color-named-is-one-color-drawn (2026-08-10, ddl-engine 10): 1 色の
    # 記述に color_cycle を作らない規則を、色とりどりの行の直後と場のトーンの行に
    # 日英で足した。**tool schema は動いていない** (18_492 / c1c1... のまま) —
    # 変わったのは散文だけで、スキーマには触れていない。**上の 4 行は動く** —
    # プロンプト本文そのもののバイト数と指紋だから。
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "c5f553c03edb2879"
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT_EN) == "fa2f5c7f35b96cc7"


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
        "ja": (19_017, "5509baecdfcf78d8"),
        "en": (18_038, "d7e2a61ee0fb116a"),
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
    # The temporary schema change must remain visible after the nine-color update.
    # The digest reads declaration order too, so moving `thinness` before `surface`
    # (contract stage2-score-shrinkage, 2026-08-03) moves this value as well.
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "be01ae6ed62cef7a"
    assert _digest(composer.SYSTEM_PROMPT) == system_only_digest == "1612296fc2102f90"


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
