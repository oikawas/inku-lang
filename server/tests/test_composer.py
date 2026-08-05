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
    assert all(instruction.note is None for instruction in actual.instructions)

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


def test_explicit_regions_drop_stage2_support_instruction():
    from inku_server.composer import _enforce_explicit_region_instruction_count

    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.337, 0.498],
                    "radius": 0.09,
                    "at": {"region": [0.227, 0.411, 0.447, 0.584]},
                },
                {
                    "primitive": "arc",
                    "center": [0.651, 0.493],
                    "radius": 0.09,
                    "at": {"region": [0.541, 0.406, 0.761, 0.579]},
                },
                {
                    "primitive": "arc",
                    "center": [0.58, 0.52],
                    "radius": 0.11,
                    "color": "red",
                    "arrangement": {"count": 3, "layout": "scatter"},
                },
            ]
        }
    )
    ddl = (
        "細い弧を 一枚、中心の帯に置く 領域 [0.227, 0.411, 0.447, 0.584]に置き、回転は32度。"
        "細い弧を 一枚、中心の帯に置く 領域 [0.541, 0.406, 0.761, 0.579]に置き、回転は-11度。"
    )

    repaired = _enforce_explicit_region_instruction_count(score, ddl)

    assert len(repaired.instructions) == 2
    assert all(instruction.at is not None for instruction in repaired.instructions)


def test_explicit_regions_keep_model_output_when_count_does_not_exceed_regions():
    from inku_server.composer import _enforce_explicit_region_instruction_count

    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
            ]
        }
    )

    repaired = _enforce_explicit_region_instruction_count(
        score,
        "Place a line in region [0.2, 0.4, 0.8, 0.6].",
    )

    assert repaired is score


def test_relation_literal_gate_drops_narrative_inferred_relations():
    from inku_server.composer import _enforce_relation_literal_gate

    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.2], "radius": 0.03},
                {
                    "primitive": "line",
                    "from": [0.4, 0.2],
                    "to": [0.6, 0.2],
                    "relation": {"type": "along", "gap": "narrow"},
                },
            ]
        }
    )

    repaired = _enforce_relation_literal_gate(
        score,
        "上端に白い小さな円を置く。白い小さな円の周囲に短い線を八本、放射状に散らす。",
    )

    assert repaired.instructions[1].relation is None


def test_relation_literal_gate_keeps_exact_previous_phrase():
    from inku_server.composer import _enforce_relation_literal_gate

    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]},
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.04, 0.02],
                    "relation": {"type": "along", "gap": "narrow"},
                },
            ]
        }
    )

    repaired = _enforce_relation_literal_gate(score, "黒い横線を一本引く。赤い楕円を前の線に沿って三つ置く。")

    assert repaired.instructions[1].relation is not None
    assert repaired.instructions[1].relation.type == "along"


def test_ground_literal_gate_drops_ground_without_marker_and_keeps_aspect(caplog):
    from inku_server.composer import _enforce_ground_literal_gate

    score = Score.model_validate(
        {
            "canvas": {"aspect": "wide", "ground": {"material": "paper", "tone": "off_white"}},
            "instructions": [],
        }
    )

    repaired = _enforce_ground_literal_gate(score, "生成りの紙のような静かな情景。")

    assert repaired.canvas == "wide"
    assert "canvas ground dropped by literal gate" in caplog.text


def test_ground_literal_gate_keeps_japanese_ground_marker():
    from inku_server.composer import _enforce_ground_literal_gate

    score = Score.model_validate(
        {"canvas": {"aspect": "square", "ground": {"material": "ink_wash"}}, "instructions": []}
    )

    repaired = _enforce_ground_literal_gate(score, "地: 薄墨。")
    fullwidth = _enforce_ground_literal_gate(score, "地：生成りの紙、細かい紙目。")

    assert not isinstance(repaired.canvas, str)
    assert repaired.canvas.ground == score.canvas.ground
    assert fullwidth.canvas.ground == score.canvas.ground


def test_ground_literal_gate_handles_english_marker_case_insensitively():
    from inku_server.composer import _enforce_ground_literal_gate

    score = Score.model_validate(
        {"canvas": {"aspect": "golden", "ground": {"material": "ink_wash"}}, "instructions": []}
    )

    kept = _enforce_ground_literal_gate(score, "GROUND: ink wash.")
    dropped = _enforce_ground_literal_gate(score, "An ink-wash mood.")

    assert not isinstance(kept.canvas, str)
    assert kept.canvas.ground == score.canvas.ground
    assert dropped.canvas == "golden"


def test_ground_literal_gate_leaves_string_canvas_unchanged():
    from inku_server.composer import _enforce_ground_literal_gate

    score = Score.model_validate({"canvas": "square", "instructions": []})

    assert _enforce_ground_literal_gate(score, "No ground marker.") is score


def test_composer_prompt_keeps_dynamic_quantity_guidance():
    from inku_server.composer import SYSTEM_PROMPT, SYSTEM_PROMPT_EN

    assert "40〜120" in SYSTEM_PROMPT
    assert "300〜800" in SYSTEM_PROMPT
    assert "700〜1000" in SYSTEM_PROMPT
    assert "六百十" in SYSTEM_PROMPT
    assert "instructions を空配列にしてはいけない" in SYSTEM_PROMPT
    assert "240 未満なら literal" in SYSTEM_PROMPT
    assert "240 以上なら代表化" in SYSTEM_PROMPT
    assert "literal 合計が 400 以下" in SYSTEM_PROMPT
    # Score has no metadata field and every model forbids extras, so the prompt must not ask for one.
    assert "metadata" not in SYSTEM_PROMPT
    assert "metadata" not in SYSTEM_PROMPT_EN
    assert "110 / 64 / 48" in SYSTEM_PROMPT
    assert '"count":137' in SYSTEM_PROMPT
    assert "below 240 is literal" in SYSTEM_PROMPT_EN
    assert "quantity of 240 or more" in SYSTEM_PROMPT_EN
    assert "remaining literal sum is 400 or less" in SYSTEM_PROMPT_EN
    assert '"count":137' in SYSTEM_PROMPT_EN
    assert "Groups with different counts, placements, or positions use separate instructions" in SYSTEM_PROMPT_EN
    assert "Multiple instructions are absolutely forbidden" not in SYSTEM_PROMPT_EN
    assert "cluster_count" in SYSTEM_PROMPT
    assert "preserve_space" in SYSTEM_PROMPT
    assert "透明な膜" in SYSTEM_PROMPT
    assert "Score.presence" in SYSTEM_PROMPT
    assert "多角形語彙は polygon だけ" in SYSTEM_PROMPT
    assert '"primitive":"polygon"' in SYSTEM_PROMPT
    assert "目鼻口・頭身・四肢・耳・尻尾" in SYSTEM_PROMPT
    assert 'symmetry="bilateral" は' in SYSTEM_PROMPT
    assert "縦線+小楕円" in SYSTEM_PROMPT
    assert "涙・視線・屋根のような名詞" in SYSTEM_PROMPT
    assert "正規化DDLに雲形がある場合だけ" in SYSTEM_PROMPT
    assert "対象物化を避けた語は削除してはいけない" in SYSTEM_PROMPT
    assert "motion intent として扱う" in SYSTEM_PROMPT
    assert "車輪・フレーム・車体" in SYSTEM_PROMPT
    assert "屋根は triangle として対象物化せず" in SYSTEM_PROMPT
    assert "Mountain / roof / sharp peak" not in SYSTEM_PROMPT_EN
    assert "Do not objectify roof as a triangle" in SYSTEM_PROMPT_EN
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
    # 契約 background-color-openness (2026-08-02): 背景は抽象九色すべてを取る。
    # 旧表明「background="gray" を使ってはいけない」を裏返した
    assert "background=\"gray\" を使ってはいけない" not in SYSTEM_PROMPT
    assert "white/black/gray/red/orange/yellow/green/blue/purple の九色すべて" in SYSTEM_PROMPT
    assert "灰色の主題は background ではなく foreground" not in SYSTEM_PROMPT
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
    assert "Nouns such as tears, gaze, and roof" in SYSTEM_PROMPT_EN
    assert "Transcribe cloudform only when normalized DDL contains it" in SYSTEM_PROMPT_EN
    assert "Do not simply delete words that were not objectified" in SYSTEM_PROMPT_EN
    assert "are motion intents. Apply them" in SYSTEM_PROMPT_EN
    assert "must not become wheels, frames, or bodies" in SYSTEM_PROMPT_EN
    assert "パッチワーク" in SYSTEM_PROMPT
    assert "フレスコの下地" in SYSTEM_PROMPT
    assert "水墨" in SYSTEM_PROMPT
    assert "既に出力済みの輪郭 instruction" in SYSTEM_PROMPT
    assert "between は直前2つ" in SYSTEM_PROMPT
    assert "普通の配置語を relation にしない" in SYSTEM_PROMPT
    assert "少しでも順序・参照先・定型句一致に迷う場合" in SYSTEM_PROMPT
    assert "自然文由来" in SYSTEM_PROMPT
    assert "原則 relation を使わない" in SYSTEM_PROMPT
    assert "青い小さな円を一つ置く。白い小さな四角を前の二つの間に置く" in SYSTEM_PROMPT
    assert "黒い線を上下の異なる位置に一本ずつ置く。赤い小さな円を前の二つの間に置く" in SYSTEM_PROMPT
    assert '"layout":"vertical"' in SYSTEM_PROMPT
    assert "ランダム" not in SYSTEM_PROMPT
    assert "20 程度" not in SYSTEM_PROMPT

    assert "40–120" in SYSTEM_PROMPT_EN
    assert "300–800" in SYSTEM_PROMPT_EN
    assert "700–1000" in SYSTEM_PROMPT_EN
    assert "six hundred ten" in SYSTEM_PROMPT_EN
    assert "instructions must not be empty" in SYSTEM_PROMPT_EN
    assert "Sparse or minimal works are valid" in SYSTEM_PROMPT_EN
    assert "do not reduce it for density or negative space" in SYSTEM_PROMPT_EN
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
    # 契約 background-color-openness (2026-08-02): 英語側も同じく裏返す
    assert 'Do not use background="gray"' not in SYSTEM_PROMPT_EN
    assert "all nine abstract colors" in SYSTEM_PROMPT_EN
    assert 'Treat gray subjects as foreground color="gray"' not in SYSTEM_PROMPT_EN
    assert "white line made visible" in SYSTEM_PROMPT_EN
    assert "one gray line rising from the bottom-left to the upper-right" in SYSTEM_PROMPT_EN
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
    assert "syncopated city rhythm" in SYSTEM_PROMPT_EN
    assert "blue-note value" in SYSTEM_PROMPT_EN
    assert "subway-map pressure" in SYSTEM_PROMPT_EN
    assert "prairie horizon" in SYSTEM_PROMPT_EN
    assert '"rotation":30' in SYSTEM_PROMPT_EN
    assert '"rotation":-30' in SYSTEM_PROMPT_EN
    assert "oil impasto" in SYSTEM_PROMPT_EN
    assert "watercolor" in SYSTEM_PROMPT_EN
    assert "patchwork" in SYSTEM_PROMPT_EN
    assert "fresco ground" in SYSTEM_PROMPT_EN
    assert "ink-wash value" in SYSTEM_PROMPT_EN
    assert "already emitted drawable outline instructions" in SYSTEM_PROMPT_EN
    assert "Use between only when the previous two JSON instructions both have outlines" in SYSTEM_PROMPT_EN
    assert "Do not turn ordinary placement language into relation" in SYSTEM_PROMPT_EN
    assert "If there is any doubt about order, target validity, or exact fixed-phrase match" in SYSTEM_PROMPT_EN
    assert "Natural-language-derived phrases" in SYSTEM_PROMPT_EN
    assert "use no relation by default" in SYSTEM_PROMPT_EN
    assert "Place one small blue circle. Place one small white square between the previous two" in SYSTEM_PROMPT_EN
    assert "Draw one black line at each of two different vertical positions. Place a small red circle between the previous two" in SYSTEM_PROMPT_EN
    assert '"layout":"vertical"' in SYSTEM_PROMPT_EN
    assert "random" not in SYSTEM_PROMPT_EN.lower()
    assert "≈ 20" not in SYSTEM_PROMPT_EN


def _tool_count_property() -> dict:
    """The count node as the model receives it, after $defs are inlined."""
    from inku_server.composer import _score_tool_schema

    # Optional fields become anyOf wrappers once $defs are inlined, so the node
    # is found by its own description rather than by a fixed path.
    def walk(node):
        if isinstance(node, dict):
            if str(node.get("description", "")).startswith("配置数"):
                return node
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        return None

    node = walk(_score_tool_schema())
    assert node is not None, "arrangement.count is missing from the tool schema"
    return node


def test_grid_schema_and_prompts_expose_literal_tiling_contract():
    from inku_server.composer import SYSTEM_PROMPT, SYSTEM_PROMPT_EN

    arrangement = Score.model_json_schema()["$defs"]["Arrangement"]
    properties = arrangement["properties"]

    assert "grid" in properties["layout"]["enum"]
    # The ceiling is NOT a static field bound any more. A `le=` here would be a
    # second copy of schema_count_max that no setting can reach, and it would
    # still admit a value the configured ceiling forbids -- so its absence is
    # the assertion, and the number is checked where it actually reaches the
    # model: the tool schema.
    assert "maximum" not in properties["count"]
    assert _tool_count_property()["maximum"] == 2000
    assert properties["rows"]["anyOf"][0]["minimum"] == 1
    assert properties["rows"]["anyOf"][0]["maximum"] == 64
    assert properties["cols"]["anyOf"][0]["minimum"] == 1
    assert properties["cols"]["anyOf"][0]["maximum"] == 64
    assert properties["jitter"]["minimum"] == 0
    assert properties["jitter"]["maximum"] == 1
    assert properties["jitter"]["default"] == 0.12

    assert 'layout="grid"' in SYSTEM_PROMPT
    assert "文字どおり指定された時だけ" in SYSTEM_PROMPT
    assert "grid の count だけは1〜2000" in SYSTEM_PROMPT
    assert "代表数への縮小" in SYSTEM_PROMPT
    assert "最大4 instructions" in SYSTEM_PROMPT
    assert "margin=0.02〜0.08" in SYSTEM_PROMPT
    assert "0.12を超えるmarginを使わない" in SYSTEM_PROMPT
    assert '"count":400,"layout":"grid","rows":20,"cols":20' in SYSTEM_PROMPT

    assert 'layout="grid"' in SYSTEM_PROMPT_EN
    assert "only for literal tiling instructions" in SYSTEM_PROMPT_EN
    assert "Only grid may use count 1–2000" in SYSTEM_PROMPT_EN
    assert "at most four instructions" in SYSTEM_PROMPT_EN
    assert "margin=0.02–0.08" in SYSTEM_PROMPT_EN
    assert "never a margin above 0.12" in SYSTEM_PROMPT_EN
    assert '"count":400,"layout":"grid","rows":20,"cols":20' in SYSTEM_PROMPT_EN


def test_arrangement_grid_fields_clamp_to_schema_bounds():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "arrangement": {
                        "count": 9999,
                        "layout": "grid",
                        "rows": 999,
                        "cols": 0,
                        "jitter": 3,
                    },
                }
            ]
        }
    )
    arrangement = score.instructions[0].arrangement

    assert arrangement is not None
    assert arrangement.count == 2000
    assert arrangement.rows == 64
    assert arrangement.cols == 1
    assert arrangement.jitter == 1
