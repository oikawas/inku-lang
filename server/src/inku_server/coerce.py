"""Stage 2 出力の構造補修 (coerce layer).

設計原則 — primitive 個別コードを書かない:
  - PRIMITIVE_SPECS テーブルで「どの primitive に何が必要か」を宣言する
  - _coerce_instruction() は汎用ループで補修する
  - 新 primitive 追加 → PRIMITIVE_SPECS にエントリ追記のみ。ここは変えない
  - POST_COERCE で cross-field 制約を追加できる (arc 角度ゼロ補正など)

補修の優先順位:
  1. 型正規化 (coerce 関数で変換)
  2. cross-field fallback (center 欠損時に position を代用など)
  3. FieldSpec.default (上記すべて失敗時)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from .schema import Instruction, Score


# ── 型正規化ヘルパー ──────────────────────────────────────────────────────────────
# 各関数は「変換できなければ None を返す」契約。None → FieldSpec.default が使われる。

def _as_coord(v: Any) -> list[float] | None:
    """任意の値を [x, y] に正規化。"""
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return [float(v[0]), float(v[1])]
        except (TypeError, ValueError):
            return None
    if isinstance(v, (int, float)):
        f = float(v)
        return [f, f]
    return None


def _as_positive_float(v: Any) -> float | None:
    """正の float に変換。0以下は None。"""
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _as_positive_size(v: Any) -> list[float] | None:
    """[w, h] に変換。いずれかが 0以下なら None。"""
    c = _as_coord(v)
    if c is None:
        return None
    return c if (c[0] > 0 and c[1] > 0) else None


def _as_float(v: Any) -> float | None:
    """float に変換 (0を含む有効値)。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── フィールド補修仕様 ──────────────────────────────────────────────────────────

@dataclass
class FieldSpec:
    """1フィールドの補修ルール。

    name:      対象フィールド名 (JSON by_alias)
    default:   欠損・不正値のときに使うデフォルト
    fallbacks: name が欠損時、代替として試みるフィールド名リスト (cross-field)
    coerce:    値の型検証・正規化関数。None を返すと default にフォールバック
    """

    name: str
    default: Any
    fallbacks: list[str] = dc_field(default_factory=list)
    coerce: Callable[[Any], Any] | None = None


# primitive → 必須フィールドの補修仕様テーブル
# 新 primitive を追加するときはここにエントリを追記するだけ
PRIMITIVE_SPECS: dict[str, list[FieldSpec]] = {
    "line": [
        FieldSpec("from",   [0.1, 0.5], coerce=_as_coord),
        FieldSpec("to",     [0.9, 0.5], coerce=_as_coord),
    ],
    "circle": [
        FieldSpec("center", [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("radius", 0.15,                               coerce=_as_positive_float),
    ],
    "ellipse": [
        FieldSpec("center", [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("size",   [0.3, 0.3],                          coerce=_as_positive_size),
    ],
    "arc": [
        FieldSpec("center",      [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("radius",      0.15,                               coerce=_as_positive_float),
        FieldSpec("angle_start", 0.0,                                coerce=_as_float),
        FieldSpec("angle_end",   270.0,                              coerce=_as_float),
    ],
    "square": [
        FieldSpec("position", [0.35, 0.35], fallbacks=["center"], coerce=_as_coord),
        FieldSpec("size",     [0.3, 0.3],                          coerce=_as_positive_size),
    ],
    "triangle": [
        FieldSpec("position", [0.35, 0.35], fallbacks=["center"], coerce=_as_coord),
        FieldSpec("size",     [0.3, 0.3],                          coerce=_as_positive_size),
    ],
}


# ── cross-field 制約補正 ──────────────────────────────────────────────────────────
# フィールド間依存がある制約のみここに書く。

def _fix_arc_angles(data: dict) -> None:
    """arc: angle_start == angle_end → 270° 広げる。"""
    if abs(data.get("angle_start", 0) - data.get("angle_end", 0)) < 1e-6:
        data["angle_end"] = (data.get("angle_start", 0) + 270.0) % 360.0


POST_COERCE: dict[str, Callable[[dict], None]] = {
    "arc": _fix_arc_angles,
}


VISIBLE_ON_BACKGROUND: dict[str, str] = {
    "white": "black",
    "black": "white",
    "gray": "black",
    "blue": "white",
    "red": "white",
    "green": "white",
}

MATERIAL_WEIGHT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ロットリング", "rotring"), "rotring"),
    (("鉛筆", "pencil"), "pencil"),
    (("クレヨン", "crayon"), "crayon"),
    (("チョーク", "chalk"), "chalk"),
    (("細筆", "fine-brush", "fine brush"), "brush_thin"),
    (("太筆", "thick-brush", "thick brush", "厚塗り", "油絵"), "brush_thick"),
    (("水墨", "墨", "ink-wash", "ink wash"), "brush_thin"),
    (("縄", "ロープ", "rope"), "rope"),
)

MAX_EXPANDED_PRIMITIVES = 400


def _visible_background(background: str) -> str:
    if background == "gray":
        return "white"
    return background


def _shape_extent(ins: Instruction) -> float:
    if ins.primitive in ("circle", "arc"):
        return float(ins.radius or 0.0) * 2
    if ins.size:
        return max(float(ins.size[0]), float(ins.size[1]))
    if ins.from_ and ins.to:
        return max(abs(ins.from_[0] - ins.to[0]), abs(ins.from_[1] - ins.to[1]))
    return 0.0


def _is_tiny_unfilled_particle(ins: Instruction) -> bool:
    if ins.primitive not in ("circle", "ellipse", "square", "triangle"):
        return False
    if ins.filled:
        return False
    if not ins.arrangement or ins.arrangement.count < 40:
        return False
    return _shape_extent(ins) <= 0.012


def _with_visible_color(ins: Instruction, background: str) -> Instruction:
    if ins.color != background:
        return ins
    data = ins.model_dump(by_alias=True)
    data["color"] = VISIBLE_ON_BACKGROUND.get(background, "black")
    hint = data.get("color_hint")
    note = f"{background} foreground made visible"
    data["color_hint"] = f"{hint}; {note}" if hint else note
    return Instruction.model_validate(data)


def _with_visible_particle(ins: Instruction) -> Instruction:
    if not _is_tiny_unfilled_particle(ins):
        return ins
    data = ins.model_dump(by_alias=True)
    data["filled"] = True
    if ins.primitive == "circle":
        data["radius"] = max(float(ins.radius or 0.0), 0.006)
    elif ins.size:
        data["size"] = [max(float(ins.size[0]), 0.008), max(float(ins.size[1]), 0.008)]
    return Instruction.model_validate(data)


def _with_density_budget(ins: Instruction) -> Instruction:
    arr = ins.arrangement
    if arr is None or arr.layout != "scatter" or arr.count <= 240:
        return ins
    if _shape_extent(ins) > 0.018:
        return ins
    data = ins.model_dump(by_alias=True)
    arr_data = dict(data["arrangement"])
    arr_data["count"] = 240
    data["arrangement"] = arr_data
    hint = data.get("color_hint")
    note = "scatter density capped to preserve negative space"
    data["color_hint"] = f"{hint}; {note}" if hint else note
    return Instruction.model_validate(data)


def _with_material_hint(ins: Instruction, ddl: str | None) -> Instruction:
    if not ddl or ins.weight != "pen":
        return ins
    lower = ddl.lower()
    for markers, weight in MATERIAL_WEIGHT_HINTS:
        if any(marker.lower() in lower for marker in markers):
            data = ins.model_dump(by_alias=True)
            data["weight"] = weight
            hint = data.get("color_hint")
            note = f"material inferred from DDL: {weight}"
            data["color_hint"] = f"{hint}; {note}" if hint else note
            return Instruction.model_validate(data)
    return ins


def _with_variation_hint(ins: Instruction, ddl: str | None) -> Instruction:
    if not ddl or ins.variation is not None:
        return ins
    lower = ddl.lower()
    variation: dict[str, object] | None = None
    if any(marker in ddl for marker in ("ゆっくり揺れる", "ゆっくり波打つ")) or "slow" in lower:
        variation = {
            "amplitude": "medium",
            "frequency": "slow",
            "quality": "wave",
            "dimensions": ["position_x", "position_y"],
        }
    elif any(marker in ddl for marker in ("細かく揺れる", "細かく震える", "震える")) or "trembling" in lower:
        variation = {
            "amplitude": "fine",
            "frequency": "medium",
            "quality": "perlin",
            "dimensions": ["position_y"] if ins.primitive == "line" else ["position_x", "position_y"],
        }
    elif any(marker in ddl for marker in ("滲む", "にじむ", "境界が滲む")) or "blurring" in lower:
        variation = {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": "pink",
            "dimensions": ["position_x", "position_y"],
        }
    if variation is None:
        return ins
    data = ins.model_dump(by_alias=True)
    data["variation"] = variation
    return Instruction.model_validate(data)


def _dedupe_instructions(instructions: list[Instruction]) -> list[Instruction]:
    deduped: list[Instruction] = []
    seen: set[str] = set()
    for ins in instructions:
        key = json.dumps(ins.model_dump(by_alias=True, exclude_none=True), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ins)
    return deduped


def _expanded_count(ins: Instruction) -> int:
    if ins.arrangement is None:
        return 1
    return max(1, int(ins.arrangement.count))


def _with_arrangement_count(ins: Instruction, count: int, note: str) -> Instruction:
    if ins.arrangement is None or ins.arrangement.count == count:
        return ins
    data = ins.model_dump(by_alias=True)
    arrangement = dict(data["arrangement"])
    arrangement["count"] = max(1, int(count))
    data["arrangement"] = arrangement
    hint = data.get("color_hint")
    data["color_hint"] = f"{hint}; {note}" if hint else note
    return Instruction.model_validate(data)


def _with_total_density_budget(instructions: list[Instruction]) -> list[Instruction]:
    total = sum(_expanded_count(ins) for ins in instructions)
    if total <= MAX_EXPANDED_PRIMITIVES:
        return instructions

    remaining_budget = MAX_EXPANDED_PRIMITIVES
    remaining = list(instructions)
    adjusted: list[Instruction] = []
    for index, ins in enumerate(remaining):
        count = _expanded_count(ins)
        rest_minimum = len(remaining) - index - 1
        if ins.arrangement is None:
            adjusted.append(ins)
            remaining_budget -= 1
            continue
        if remaining_budget <= rest_minimum + 1:
            allowed = 1
        else:
            remaining_total = sum(_expanded_count(item) for item in remaining[index:])
            share = count / remaining_total if remaining_total > 0 else 0
            allowed = max(1, int((remaining_budget - rest_minimum) * share))
        adjusted_ins = _with_arrangement_count(ins, allowed, "expanded density capped to preserve negative space")
        adjusted.append(adjusted_ins)
        remaining_budget -= _expanded_count(adjusted_ins)
    return adjusted


_KANJI_NUMBERS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "百": 100,
}


def _parse_small_japanese_number(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "百":
        return 100
    if text.endswith("百") and len(text) == 2:
        return _KANJI_NUMBERS.get(text[0], 1) * 100
    if "百" in text:
        head, tail = text.split("百", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 100
        rest = _parse_small_japanese_number(tail)
        return value + (rest or 0)
    if text == "十":
        return 10
    if text.endswith("十") and len(text) == 2:
        return _KANJI_NUMBERS.get(text[0], 1) * 10
    if "十" in text:
        head, tail = text.split("十", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 10
        return value + (_KANJI_NUMBERS.get(tail, 0) if tail else 0)
    if len(text) == 1:
        return _KANJI_NUMBERS.get(text)
    return None


def count_hint_from_ddl(ddl: str) -> int | None:
    """Extract a conservative count hint from a normalized DDL fragment."""
    match = re.search(r"(\d{1,4}|[一二三四五六七八九十百]{1,8})(?:本|個|つ|点|枚)", ddl)
    if not match:
        return None
    value = _parse_small_japanese_number(match.group(1))
    if value is None:
        return None
    return min(max(value, 1), 1000)


def _repair_visibility(ins: Instruction, background: str) -> Instruction:
    repaired = _with_visible_color(ins, background)
    repaired = _with_visible_particle(repaired)
    return _with_density_budget(repaired)


def _coerce_and_repair_instruction(
    ins: Instruction,
    *,
    original_background: str,
    background: str,
    ddl: str | None,
) -> Instruction:
    coerced = _coerce_instruction(ins)
    coerced = _with_material_hint(coerced, ddl)
    coerced = _with_variation_hint(coerced, ddl)
    if original_background == "gray" and coerced.color == "gray":
        coerced = _with_visible_color(coerced, "gray")
    return _repair_visibility(coerced, background)


def ensure_renderable_score(score: Score) -> None:
    """Raise when Stage 2 returned no drawable instructions."""
    if not score.instructions:
        raise ValueError("Stage 2 returned no drawable instructions")


# ── 汎用補修ループ ────────────────────────────────────────────────────────────────

def _coerce_instruction(ins: Instruction) -> Instruction:
    """PRIMITIVE_SPECS テーブルを参照して 1 命令を補修する。

    補修の流れ:
      1. フィールドが None → fallbacks を順に試みる
      2. 値を coerce 関数で型正規化 (None なら default へ)
      3. POST_COERCE で cross-field 制約を適用
    """
    data = ins.model_dump(by_alias=True)

    for spec in PRIMITIVE_SPECS.get(ins.primitive, []):
        val = data.get(spec.name)

        # (1) None → fallback を順に試みる
        if val is None:
            for fb in spec.fallbacks:
                fb_val = data.get(fb)
                if fb_val is not None:
                    val = fb_val
                    break

        # (2) 型正規化。失敗 (None 返却) なら default を使う
        if val is not None and spec.coerce is not None:
            val = spec.coerce(val)

        if val is None:
            val = list(spec.default) if isinstance(spec.default, list) else spec.default

        data[spec.name] = val

    # (3) cross-field 補正
    if post := POST_COERCE.get(ins.primitive):
        post(data)

    return Instruction.model_validate(data)


def coerce_score(score: Score, *, ddl: str | None = None) -> Score:
    """LLM 生成 Score の欠損・不正フィールドを補修して Renderer が安全に描画できる状態にする。"""
    background = _visible_background(score.background)
    instructions = [
        _coerce_and_repair_instruction(ins, original_background=score.background, background=background, ddl=ddl)
        for ins in score.instructions
    ]
    instructions = _dedupe_instructions(instructions)
    instructions = _with_total_density_budget(instructions)
    data = score.model_dump(by_alias=True)
    data["background"] = background
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
    return Score.model_validate(data)
