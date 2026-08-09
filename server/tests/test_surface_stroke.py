"""render engine 16 段 1: 面 (surface) を筆致へ通す。

engine 15 まで `synthesize_along` を通っていた surface は hatch / crosshatch の
2 語だけで、本番 562 instruction のうち 4 件 = 0.7% だった。残りは bbox の中に
一様乱数で置いた円 (bleed は bbox 中心の楕円 1 個) で、図形の形を見ていない。

このファイルは段 1 の判別テストである。陽性は texture ごとに分ける (まとめて 1 本
にすると 1 語だけ直っても通る)。陰性は engine 15 の凍結コーパスの digest を正本に
する — 「既に正しかった経路を壊していない」ことの担保は、実測された過去の版に
しか置けない。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import pathlib
import re

import pytest

import inku_server.renderer as renderer
import inku_server.stroke_engine as stroke_engine
from inku_server.render_engines import current_render_engine
from inku_server.renderer import (
    _point_in_polygon,
    _surface_contour,
    render,
)
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.schema import Instruction, Score

CANVAS = canvas_size_for_aspect(None)
ENGINE_15_MANIFEST = (
    pathlib.Path(__file__).resolve().parents[1]
    / "reference"
    / "render-engine-15"
    / "manifest.json"
)

BASE_SURFACE = {
    "texture": "stipple",
    "density": 0.55,
    "scale": 0.40,
    "opacity": 0.36,
    "bleed": 0.25,
    "direction": "diagonal_rising",
    "spacing_gradient": "none",
    "tone_steps": 3,
    "seed": 24680,
}
SQUARE = {"primitive": "square", "position": [0.28, 0.28], "size": [0.44, 0.44]}
TRIANGLE = {"primitive": "triangle", "position": [0.28, 0.28], "size": [0.44, 0.44]}

# 段 1 が触る 6 語。hatch / crosshatch は既に通っているので対象外。
PERFORMED_TEXTURES = ("stipple", "grain", "paper_grain", "wash", "aquatint", "bleed")


def _render(shape: dict, texture: str, *, weight: str = "pen", profile: str = "display",
            render_seed: int = 12345, **surface_changes) -> str:
    surface = {**BASE_SURFACE, "texture": texture, **surface_changes}
    score = Score.model_validate(
        {"instructions": [dict(shape, weight=weight, filled=False, surface=surface)]}
    )
    return render(score, render_seed=render_seed, svg_profile=profile)


def _normalized_digest(svg: str) -> str:
    normalized = re.sub(
        r"\d+\.\d+", lambda match: f"{round(float(match.group(0)), 6):.6f}", svg
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _engine_15_cases() -> dict[str, dict]:
    return json.loads(ENGINE_15_MANIFEST.read_text())["cases"]


def _current_cases() -> dict[str, dict]:
    path = (
        ENGINE_15_MANIFEST.parent.parent
        / f"render-engine-{current_render_engine().version}"
        / "manifest.json"
    )
    return json.loads(path.read_text())["cases"]


def _surface_body(svg: str) -> str:
    match = re.search(r'<g id="surface_000_000_[a-z_]+">(.*?)</g>', svg, flags=re.S)
    return match.group(1) if match else ""


def _ink_points(body: str) -> list[tuple[float, float]]:
    """surface 群が実際に墨を置いた座標。要素の種別に依らず数で見る。"""
    return [
        (float(x), float(y))
        for x, y in re.findall(r"([0-9]+\.[0-9]+) ([0-9]+\.[0-9]+)", body)
    ]


def _distance_outside(
    point: tuple[float, float], contour: list[tuple[float, float]]
) -> float:
    """輪郭の外なら輪郭までの距離、内なら 0。"""
    if _point_in_polygon(point[0], point[1], contour):
        return 0.0
    best = float("inf")
    for index in range(len(contour)):
        ax, ay = contour[index]
        bx, by = contour[(index + 1) % len(contour)]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0.0 else (
            (point[0] - ax) * dx + (point[1] - ay) * dy
        ) / length_sq
        t = max(0.0, min(1.0, t))
        best = min(best, math.hypot(point[0] - (ax + dx * t), point[1] - (ay + dy * t)))
    return best


@contextlib.contextmanager
def _engine_15_seed_material():
    """演奏 seed の材料を engine 15 の 19 フィールドへ戻す。

    段 3 が `thinness` を allowlist へ入れた (C-7) ので、値が既定の None でも
    seed 鍵の JSON が変わり、コーパス 358 件のうち 325 件が動いた (不変 33 件は
    rotring と computer = 機械の極)。ここで留めたいのは「この段がこの経路を
    触っていない」ことなので、比較は太さの軸を足す前の材料で行う。段 3 の側は
    `test_thinness_axis.py` が別に留めている。
    """
    original = renderer._SEED_INSTRUCTION_FIELDS
    reverted = tuple(name for name in original if name != "thinness")
    assert len(reverted) == len(original) - 1, "allowlist から thinness が消えている"
    renderer._SEED_INSTRUCTION_FIELDS = reverted
    original_resistance = stroke_engine.RESISTANCE
    # engine 19 (地の抵抗) はストローク合成そのものを動かすので、engine 15 との
    # バイト比較は抵抗を切った状態で行う。段 3 の `thinness` と同じ扱い。
    # engine 19 の側は `test_ground_resistance.py` が別に留めている。
    stroke_engine.RESISTANCE = stroke_engine.RESISTANCE_LEVELS["g0"]
    try:
        yield
    finally:
        renderer._SEED_INSTRUCTION_FIELDS = original
        stroke_engine.RESISTANCE = original_resistance


def _replay(case: dict) -> str:
    render_input = case["input"]
    return render(
        Score.model_validate(render_input["score"]),
        color_map=render_input["color_map"],
        render_seed=render_input["render_seed"],
        svg_profile=render_input["svg_profile"],
        wild=render_input["wild"],
    )


# --- S-1 陽性: 6 語それぞれが筆致を通ること -------------------------------- #


@pytest.mark.parametrize("texture", PERFORMED_TEXTURES)
def test_s1_every_grain_and_bleed_texture_is_performed(texture: str) -> None:
    """engine 15 では 0 件だったので、これが段 1 の赤である。"""
    svg = _render(SQUARE, texture)
    assert "surface-stroke-v1" in svg, texture


@pytest.mark.parametrize("texture", PERFORMED_TEXTURES)
def test_s1_performed_surface_reaches_every_hand_tool(texture: str) -> None:
    """道具を替えても筆致であること。rotring だけが機械の極で幾何のまま。"""
    for weight in ("brush_thick", "chalk", "silverpoint"):
        assert "surface-stroke-v1" in _render(SQUARE, texture, weight=weight)
    assert "surface-stroke-v1" not in _render(SQUARE, texture, weight="rotring")


# --- S-2 陰性: hatch / crosshatch は engine 15 と 1 バイトも変わらない ------ #


def test_s2_hatch_and_crosshatch_cases_are_not_touched_by_the_surface_stroke() -> None:
    """段 1 の帰属の担保。ここが動いたら既に正しかった経路を壊している。

    engine 28 で作り直した。ここは engine 15 の凍結バイトを物差しにし、後から載った
    層（太さの軸）を無効化して比べていた。engine 28 は材質層の作り方と揺らぎの
    物差しの両方を動かしたので、engine 15 のバイトは実演では二度と再現できない ——
    **同じやり方を続けるには engine 16〜27 を丸ごと作り直すことになる。**

    **⚠ この半分は検査ではなく焼き直される記録になった。** 帰属を留めていたのは
    「engine 15 の seed 材料へ戻せば engine 15 のバイトが出る」という装置で、
    その装置は engine 28 の変更まではカバーできない。engine 15 と 16 の manifest を
    直接比べても 8 件とも digest が違う（差は太さの軸で、surface のストロークでは
    ない）ので、版どうしの比較で帰属を言い直すこともできない。
    **失われた観測点として台帳へ起票すること。** ここは現行コーパスとの一致だけを
    見る（母集団 8 件の番人としては効く）。
    """
    cases = _engine_15_cases()
    pinned = sorted(
        case_id
        for case_id in cases
        if "surface-" in case_id and ("-hatch-" in case_id or "-crosshatch-" in case_id)
    )
    assert len(pinned) == 8, pinned
    current = _current_cases()
    for case_id in pinned:
        assert _normalized_digest(_replay(cases[case_id])) == current[case_id]["digest"], (
            case_id
        )


def test_s2_the_other_surface_cases_did_move() -> None:
    """判別力の実測。8 件が不変であることは、24 件が動いて初めて意味を持つ。"""
    cases = _engine_15_cases()
    surface_cases = sorted(
        case_id
        for case_id in cases
        if "surface-" in case_id
        and "-hatch-" not in case_id
        and "-crosshatch-" not in case_id
    )
    assert len(surface_cases) == 24, surface_cases
    moved = [
        case_id
        for case_id in surface_cases
        if _normalized_digest(_replay(cases[case_id])) != cases[case_id]["digest"]
    ]
    assert len(moved) == 24, sorted(set(surface_cases) - set(moved))


# --- S-3 形: 粒が図形の外に出ないこと -------------------------------------- #


@pytest.mark.parametrize("texture", ("stipple", "grain", "paper_grain", "aquatint"))
def test_s3_grains_stay_inside_a_triangle(texture: str) -> None:
    """bbox 一様乱数をやめた直接の証拠。三角形の bbox の半分は図形の外である。

    editable プロファイルで見る (display の clipPath が隠してくれないので、
    engine 15 の実装ではここが落ちる)。
    """
    svg = _render(TRIANGLE, texture, profile="editable")
    instruction = Instruction.model_validate(
        dict(TRIANGLE, weight="pen", filled=False, surface={**BASE_SURFACE, "texture": texture})
    )
    contour = _surface_contour(
        instruction, CANVAS, render_seed=12345, ins_idx=0, mark_idx=0
    )
    assert contour == [(500.0, 280.0), (720.0, 720.0), (280.0, 720.0)]
    points = _ink_points(_surface_body(svg))
    assert len(points) >= 200, len(points)

    # 三角形の外接矩形の左上 100x100 px は図形から 70px 以上離れた「外」である。
    # engine 15 はここへ一様に撒いていた (bbox の 51% が図形の外だった)。
    assert not [p for p in points if p[0] < 380.0 and p[1] < 380.0]

    # 縁をまたぐのは筆が幅と長さを持つからで、はみ出しは粒 1 つぶんに収まる。
    # 実測 7.1px。engine 15 は三角形の bbox 全面へ撒いており、最も遠い粒は輪郭から
    # 200px 以上 (キャンバスの 20%) 外にあった。
    excursion = max(_distance_outside(p, contour) for p in points)
    assert excursion <= CANVAS.unit * 0.02, excursion


# --- S-4 形: bleed が楕円 1 個ではないこと --------------------------------- #


def test_s4_bleed_is_not_a_single_ellipse() -> None:
    svg = _render(SQUARE, "bleed", profile="editable")
    group = re.search(r'<g id="surface_000_000_bleed">(.*?)</g>', svg, flags=re.S)
    assert group is not None
    body = group.group(1)
    assert "<ellipse" not in body
    assert body.count("surface-stroke-v1") > 1


def test_s4_bleed_follows_the_outline_of_a_triangle() -> None:
    """楕円なら図形が変わっても同じ絵が出る。輪郭に沿うなら変わる。"""
    square = _render(SQUARE, "bleed", profile="editable")
    triangle = _render(TRIANGLE, "bleed", profile="editable")
    assert _normalized_digest(square) != _normalized_digest(triangle)
    # 三角形の bleed の墨は、三角形の外接矩形の左上隅には無い。
    triangle_group = re.search(
        r'<g id="surface_000_000_bleed">(.*?)</g>', triangle, flags=re.S
    )
    assert triangle_group is not None
    points = [
        (float(x), float(y))
        for x, y in re.findall(r"([0-9]+\.[0-9]+) ([0-9]+\.[0-9]+)", triangle_group.group(1))
    ]
    assert points
    corner = [p for p in points if p[0] < 320.0 and p[1] < 320.0]
    assert not corner, corner[:4]


# --- S-5 profile: display と editable が同じ機構であること ------------------ #


@pytest.mark.parametrize("texture", PERFORMED_TEXTURES)
def test_s5_display_and_editable_use_the_same_mechanism(texture: str) -> None:
    """engine 15 は wash / bleed が display でだけフィルタ矩形になっていた。

    プロファイルの差は他の層と同じく材質フィルタの有無だけにする。要素の種別と
    数が一致することで「同じ機構から出ている」と言える (バイト一致は求めない)。
    """
    display = _render(SQUARE, texture, weight="pencil", profile="display")
    editable = _render(SQUARE, texture, weight="pencil", profile="editable")
    for svg in (display, editable):
        assert "feTurbulence" not in _surface_body(svg)
    assert _surface_body(display).count("<path") == _surface_body(editable).count("<path")
    assert _surface_body(display).count("<rect") == 0
    assert _surface_body(editable).count("<rect") == 0


# --- S-6 恒等: filled 側は段 1 で 1 件も動かない --------------------------- #


def test_s6_filled_cases_carry_no_surface_layer() -> None:
    """`_fills_interior` は surface があれば False を返すので両者は排他。

    engine 16 の時点でこれは「30 件が engine 15 とバイト一致」だった。
    **engine 22 は 30 件すべてを意図して動かした**ので、その形では段 1 の恒等性を
    もう測れない。排他そのものは frozen digest を経由しなくても測れるので、
    ここでは製品を直接叩く — 塗りの case に段 1 の要素が 1 つも出ないこと、
    および `surface` を足した同じ instruction では塗りが消えること。
    後者が無いと、`_fills_interior` が常に False を返す実装でも通る。
    """
    cases = _engine_15_cases()
    fill_cases = sorted(case_id for case_id in cases if "-fill-" in case_id)
    assert len(fill_cases) == 30, len(fill_cases)
    with _engine_15_seed_material():
        for case_id in fill_cases:
            assert "surface-stroke-v1" not in _replay(cases[case_id]), case_id

        # 判別力: 同じ instruction に surface を足すと塗りの側が消える。これが無いと、
        # `_fills_interior` が常に False を返す実装でも上の走査を通ってしまう。
        case = json.loads(json.dumps(cases["C-fill-circle-crayon"]))
        filled = _replay(case)
        case["input"]["score"]["instructions"][0]["surface"] = {
            "texture": "hatch",
            "density": 0.55,
            "scale": 0.40,
            "opacity": 0.36,
            "bleed": 0.25,
            "direction": "diagonal_rising",
            "spacing_gradient": "none",
            "tone_steps": 3,
            "seed": 24680,
        }
        surfaced = _replay(case)
    assert "fill-underlay-v1" in filled
    assert "fill-underlay-v1" not in surfaced
    assert "surface-stroke-v1" in surfaced
