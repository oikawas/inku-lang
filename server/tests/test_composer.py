"""Stage 2 composer integration tests.

LLM fixture は当面 NVIDIA NIM のみを対象にする。
`INKU_LLM_BACKEND=openai`、`NVIDIA_API_KEY`、`OPENAI_MODEL` に `/` を含む
NVIDIA model ID が設定されている場合だけ実行する。

厳密比較軸:
- primitive / color / weight / style / variation: 完全一致
- 座標・サイズ・半径: ±0.05 tolerance (0-1 比率上 5%)
- variation.dimensions: 集合一致 (順序不問)
"""

from __future__ import annotations

import os
import json
from pathlib import Path

import pytest

from inku_server.composer import compose
from inku_server.schema import Instruction, Score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "stage2"

NUMERIC_TOL = 0.05


def _cases() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())


def _backend_available() -> bool:
    backend = os.getenv("INKU_LLM_BACKEND", "").lower()
    model = os.getenv("OPENAI_MODEL", "")
    return backend == "openai" and bool(os.getenv("NVIDIA_API_KEY")) and "/" in model


requires_api_key = pytest.mark.skipif(
    not _backend_available(),
    reason="NVIDIA NIM test backend is not configured",
)


def _approx_equal(a, b, tol: float = NUMERIC_TOL) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(
            _approx_equal(x, y, tol) for x, y in zip(a, b)
        )
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


def _diff_instruction(a: Instruction, e: Instruction) -> list[str]:
    errs: list[str] = []
    for field in ("primitive", "color", "weight", "style"):
        av, ev = getattr(a, field), getattr(e, field)
        if av != ev:
            errs.append(f"{field}: {av!r} vs {ev!r}")

    for field in ("center", "radius", "from_", "to", "position", "size", "rotation"):
        av, ev = getattr(a, field), getattr(e, field)
        if av is None and ev is None:
            continue
        if not _approx_equal(av, ev):
            label = "from" if field == "from_" else field
            errs.append(f"{label}: {av} vs {ev}")

    va, ev_var = a.variation, e.variation
    if (va is None) != (ev_var is None):
        errs.append(f"variation: {va} vs {ev_var}")
    elif va is not None and ev_var is not None:
        if va.amplitude != ev_var.amplitude:
            errs.append(f"variation.amplitude: {va.amplitude} vs {ev_var.amplitude}")
        if va.quality != ev_var.quality:
            errs.append(f"variation.quality: {va.quality} vs {ev_var.quality}")
        if set(va.dimensions) != set(ev_var.dimensions):
            errs.append(
                f"variation.dimensions: {va.dimensions} vs {ev_var.dimensions}"
            )

    aa, ea = a.arrangement, e.arrangement
    if (aa is None) != (ea is None):
        errs.append(f"arrangement: {aa} vs {ea}")
    elif aa is not None and ea is not None:
        if aa.count != ea.count:
            errs.append(f"arrangement.count: {aa.count} vs {ea.count}")
        if aa.layout != ea.layout:
            errs.append(f"arrangement.layout: {aa.layout} vs {ea.layout}")
        if aa.path != ea.path:
            errs.append(f"arrangement.path: {aa.path} vs {ea.path}")
        if aa.color_cycle != ea.color_cycle:
            errs.append(f"arrangement.color_cycle: {aa.color_cycle} vs {ea.color_cycle}")
        if not _approx_equal(aa.margin, ea.margin):
            errs.append(f"arrangement.margin: {aa.margin} vs {ea.margin}")
        if not _approx_equal(aa.center, ea.center):
            errs.append(f"arrangement.center: {aa.center} vs {ea.center}")
        if not _approx_equal(aa.radius, ea.radius):
            errs.append(f"arrangement.radius: {aa.radius} vs {ea.radius}")

    return errs


@requires_api_key
@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_compose_fixture(case_dir: Path):
    ddl = (case_dir / "input.txt").read_text(encoding="utf-8").strip()
    expected = Score.model_validate_json((case_dir / "expected.json").read_text())

    actual, _, _ = compose(ddl)

    if len(actual.instructions) != len(expected.instructions):
        raise AssertionError(
            f"{case_dir.name}: instruction count "
            f"{len(actual.instructions)} vs {len(expected.instructions)}"
        )

    all_errors: list[str] = []
    for i, (a, e) in enumerate(zip(actual.instructions, expected.instructions)):
        errs = _diff_instruction(a, e)
        if errs:
            all_errors.append(f"  [{i}] " + "; ".join(errs))

    if all_errors:
        raise AssertionError(
            f"\n{case_dir.name} ({len(all_errors)} instruction(s) with diffs):\n"
            + "\n".join(all_errors)
        )


def test_submit_tool_schema_is_valid():
    from inku_server.composer import _submit_tool

    tool = _submit_tool()
    assert tool["name"] == "submit_score"
    assert "input_schema" in tool
    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert "instructions" in schema["properties"]
    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)
    arrangement = schema["properties"]["instructions"]["items"]["properties"]["arrangement"]["anyOf"][0]
    assert "path" in arrangement["properties"]
    assert "density" in arrangement["properties"]
    assert "cluster_count" in arrangement["properties"]
    assert "fade" in arrangement["properties"]
    assert "preserve_space" in arrangement["properties"]
    assert "rhythm_spacing" in arrangement["properties"]
    assert arrangement["properties"]["path"]["enum"] == [
        "none",
        "diagonal",
        "wave",
        "top_to_bottom",
        "left_to_right",
        "right_half",
    ]
    assert arrangement["properties"]["rhythm_spacing"]["enum"] == [
        "none",
        "syncopated",
        "accelerando",
        "loose",
    ]


def test_modifier_targeting_drops_unrequested_support_lines():
    from inku_server.composer import _enforce_modifier_targeting

    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "color": "green",
                    "arrangement": {
                        "count": 111,
                        "layout": "vertical",
                        "path": "top_to_bottom",
                        "density": "high",
                        "cluster_count": 7,
                        "fade": "directional",
                        "preserve_space": True,
                    },
                },
                {
                    "primitive": "line",
                    "from": [0.25, 0.5],
                    "to": [0.75, 0.5],
                    "color": "black",
                    "arrangement": {"count": 3, "layout": "vertical"},
                },
            ]
        }
    )

    repaired = _enforce_modifier_targeting(score, "震えるペンの緑の直線を300本、上から下に引く。")

    assert len(repaired.instructions) == 1
    instruction = repaired.instructions[0]
    assert instruction.primitive == "line"
    assert instruction.color == "green"
    assert instruction.variation is not None
    assert instruction.variation.quality == "perlin"
    assert set(instruction.variation.dimensions) == {"position_x", "position_y"}


def test_modifier_targeting_leaves_multi_motif_scores_alone():
    from inku_server.composer import _enforce_modifier_targeting

    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5], "color": "green"},
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "red"},
            ]
        }
    )

    repaired = _enforce_modifier_targeting(score, "震える緑の線と赤い円を描く。")

    assert len(repaired.instructions) == 2


def test_composer_prompt_keeps_dynamic_quantity_guidance():
    from inku_server.composer import SYSTEM_PROMPT, SYSTEM_PROMPT_EN

    assert "40〜120" in SYSTEM_PROMPT
    assert "300〜800" in SYSTEM_PROMPT
    assert "700〜1000" in SYSTEM_PROMPT
    assert "六百十" in SYSTEM_PROMPT
    assert "instructions を空配列にしてはいけない" in SYSTEM_PROMPT
    assert "余白を残す" in SYSTEM_PROMPT
    assert "cluster_count" in SYSTEM_PROMPT
    assert "preserve_space" in SYSTEM_PROMPT
    assert "透明な膜" in SYSTEM_PROMPT
    assert "Score.presence" in SYSTEM_PROMPT
    assert "多角形語彙は polygon だけ" in SYSTEM_PROMPT
    assert '"primitive":"polygon"' in SYSTEM_PROMPT
    assert "目鼻口・頭身・四肢・耳・尻尾" in SYSTEM_PROMPT
    assert 'symmetry="bilateral" は' in SYSTEM_PROMPT
    assert "縦線+小楕円" in SYSTEM_PROMPT
    assert "涙・視線・屋根・雲" in SYSTEM_PROMPT
    assert '"symmetry":"none","gaze_pressure":"none"' in SYSTEM_PROMPT
    assert "待つ人の気配" in SYSTEM_PROMPT
    assert "反射" in SYSTEM_PROMPT
    assert "圧縮しすぎない" in SYSTEM_PROMPT
    assert "香り" in SYSTEM_PROMPT
    assert "五感" in SYSTEM_PROMPT
    assert "削りすぎ" in SYSTEM_PROMPT
    assert "柔らかな光と沈丁花の香り" in SYSTEM_PROMPT
    assert "実質的に見えない instruction" in SYSTEM_PROMPT
    assert "面積の少ない側" in SYSTEM_PROMPT
    assert "background=\"gray\"" in SYSTEM_PROMPT
    assert "background=\"gray\" を使ってはいけない" in SYSTEM_PROMPT
    assert "灰色の主題は background ではなく foreground" in SYSTEM_PROMPT
    assert "白い横線を中央に引く" in SYSTEM_PROMPT
    assert "白い線を可視化" in SYSTEM_PROMPT
    assert "白い短い線を上から下へ百三十七本" in SYSTEM_PROMPT
    assert "ゆっくり揺れる" in SYSTEM_PROMPT
    assert "形容語・動作語・質感語" in SYSTEM_PROMPT
    assert "DDL にない補助線・補助図形・別色の instruction を追加してはいけない" in SYSTEM_PROMPT
    assert "震えるペンの緑の直線" in SYSTEM_PROMPT
    assert 'quality":"wave"' in SYSTEM_PROMPT
    assert '"dimensions":["position_x","position_y"]' in SYSTEM_PROMPT
    assert "color\":\"blue" in SYSTEM_PROMPT
    assert "配置語を優先" in SYSTEM_PROMPT
    assert "上から下へ散らす" in SYSTEM_PROMPT
    assert 'path":"wave"' in SYSTEM_PROMPT
    assert 'path":"right_half"' in SYSTEM_PROMPT
    assert "三分割の交点" in SYSTEM_PROMPT
    assert "白銀比の位置" in SYSTEM_PROMPT
    assert "正五角形の頂点" in SYSTEM_PROMPT
    assert "対位法の反行" in SYSTEM_PROMPT
    assert "倍音列" in SYSTEM_PROMPT
    assert "輪唱のずれ" in SYSTEM_PROMPT
    assert "一点透視法" in SYSTEM_PROMPT
    assert "遠近法の奥行き" in SYSTEM_PROMPT
    assert "点描" in SYSTEM_PROMPT
    assert "rotation を付けて水平/垂直対称を崩す" in SYSTEM_PROMPT
    assert '"rotation":30' in SYSTEM_PROMPT
    assert '"rotation":-30' in SYSTEM_PROMPT
    assert "油絵の厚塗り" in SYSTEM_PROMPT
    assert "水彩" in SYSTEM_PROMPT
    assert "tears, gaze, roof, and cloud" in SYSTEM_PROMPT_EN
    assert "パッチワーク" in SYSTEM_PROMPT
    assert "フレスコの下地" in SYSTEM_PROMPT
    assert "水墨" in SYSTEM_PROMPT
    assert '"layout":"vertical"' in SYSTEM_PROMPT
    assert "ランダム" not in SYSTEM_PROMPT
    assert "20 程度" not in SYSTEM_PROMPT

    assert "40–120" in SYSTEM_PROMPT_EN
    assert "300–800" in SYSTEM_PROMPT_EN
    assert "700–1000" in SYSTEM_PROMPT_EN
    assert "six hundred ten" in SYSTEM_PROMPT_EN
    assert "instructions must not be empty" in SYSTEM_PROMPT_EN
    assert "Preserve negative space" in SYSTEM_PROMPT_EN
    assert "cluster_count" in SYSTEM_PROMPT_EN
    assert "preserve_space" in SYSTEM_PROMPT_EN
    assert "transparent membrane" in SYSTEM_PROMPT_EN
    assert "Score.presence" in SYSTEM_PROMPT_EN
    assert "Use only polygon for polygonal vocabulary" in SYSTEM_PROMPT_EN
    assert "eyes, mouth, body proportions, limbs, ears, or tails" in SYSTEM_PROMPT_EN
    assert 'symmetry="bilateral" only' in SYSTEM_PROMPT_EN
    assert "vertical-line + small-ellipse" in SYSTEM_PROMPT_EN
    assert "waiting person" in SYSTEM_PROMPT_EN
    assert "Reflection" in SYSTEM_PROMPT_EN
    assert "Do not over-compress" in SYSTEM_PROMPT_EN
    assert "scent" in SYSTEM_PROMPT_EN
    assert "bodily senses" in SYSTEM_PROMPT_EN
    assert "loses richness or playfulness" in SYSTEM_PROMPT_EN
    assert "Soft light and daphne fragrance" in SYSTEM_PROMPT_EN
    assert "effectively invisible instructions" in SYSTEM_PROMPT_EN
    assert "smaller visual area" in SYSTEM_PROMPT_EN
    assert 'background="gray"' in SYSTEM_PROMPT_EN
    assert 'Do not use background="gray"' in SYSTEM_PROMPT_EN
    assert 'Treat gray subjects as foreground color="gray"' in SYSTEM_PROMPT_EN
    assert "white line made visible" in SYSTEM_PROMPT_EN
    assert "short white lines from top to bottom" in SYSTEM_PROMPT_EN
    assert "Swaying slowly" in SYSTEM_PROMPT_EN
    assert "Apply adjectives, motion words, and texture words" in SYSTEM_PROMPT_EN
    assert "Do not add supporting lines, supporting shapes, or differently colored instructions" in SYSTEM_PROMPT_EN
    assert "three hundred trembling green pen lines" in SYSTEM_PROMPT_EN
    assert 'quality":"wave"' in SYSTEM_PROMPT_EN
    assert '"dimensions":["position_x","position_y"]' in SYSTEM_PROMPT_EN
    assert "color\":\"blue" in SYSTEM_PROMPT_EN
    assert "prioritize that placement phrase" in SYSTEM_PROMPT_EN
    assert "top to bottom" in SYSTEM_PROMPT_EN
    assert 'path":"wave"' in SYSTEM_PROMPT_EN
    assert 'path":"right_half"' in SYSTEM_PROMPT_EN
    assert "rule-of-thirds point" in SYSTEM_PROMPT_EN
    assert "silver-ratio position" in SYSTEM_PROMPT_EN
    assert "regular pentagon vertices" in SYSTEM_PROMPT_EN
    assert "contrapuntal contrary motion" in SYSTEM_PROMPT_EN
    assert "harmonic overtone series" in SYSTEM_PROMPT_EN
    assert "canon offset" in SYSTEM_PROMPT_EN
    assert "one-point perspective" in SYSTEM_PROMPT_EN
    assert "perspective depth" in SYSTEM_PROMPT_EN
    assert "pointillism" in SYSTEM_PROMPT_EN
    assert "add rotation to break axis symmetry" in SYSTEM_PROMPT_EN
    assert '"rotation":30' in SYSTEM_PROMPT_EN
    assert '"rotation":-30' in SYSTEM_PROMPT_EN
    assert "oil impasto" in SYSTEM_PROMPT_EN
    assert "watercolor" in SYSTEM_PROMPT_EN
    assert "patchwork" in SYSTEM_PROMPT_EN
    assert "fresco ground" in SYSTEM_PROMPT_EN
    assert "ink-wash value" in SYSTEM_PROMPT_EN
    assert '"layout":"vertical"' in SYSTEM_PROMPT_EN
    assert "random" not in SYSTEM_PROMPT_EN.lower()
    assert "≈ 20" not in SYSTEM_PROMPT_EN
