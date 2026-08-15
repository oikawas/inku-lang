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
    _line_spans,
    _point_in_polygon,
    _surface_contour,
    _surface_line_angle,
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


# --- S-2 母集団: engine 15 の hatch / crosshatch 8 件が現行と一致すること ---- #


def test_s2_the_engine_15_hatch_cases_replay_to_the_current_corpus() -> None:
    """engine 15 の入力 8 件を現行の renderer で描き直し、現行コーパスと突き合わせる。

    **⚠ 名前が変わった。engine 35 まではここは
    `test_s2_hatch_and_crosshatch_cases_are_not_touched_by_the_surface_stroke` で、
    「ハッチは engine 15 から 1 バイトも変わらない」と名乗っていた。engine 35 が
    ハッチの行を輪郭で切ったので、その名前と docstring は偽になった** ——
    検査の中身は 1 行も変えていない。**⚠ 中身は engine 28 の時点で既に
    「engine 15 のバイトとの比較」ではなくなっていた**（下記）。

    engine 28 で作り直した。ここは engine 15 の凍結バイトを物差しにし、後から載った
    層（太さの軸）を無効化して比べていた。engine 28 は材質層の作り方と揺らぎの
    物差しの両方を動かしたので、engine 15 のバイトは実演では二度と再現できない ——
    **同じやり方を続けるには engine 16〜27 を丸ごと作り直すことになる。**

    **⚠ これは検査ではなく焼き直される記録である。** 帰属を留めていたのは
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


@pytest.mark.parametrize(
    "texture", ("stipple", "grain", "paper_grain", "aquatint", "hatch", "crosshatch")
)
def test_s3_grains_stay_inside_a_triangle(texture: str) -> None:
    """bbox 一様乱数をやめた直接の証拠。三角形の bbox の半分は図形の外である。

    editable プロファイルで見る (display の clipPath が隠してくれないので、
    engine 15 の実装ではここが落ちる)。

    engine 35 が `hatch` と `crosshatch` をこの一覧へ入れた。この 2 語だけは粒系と
    違う理由で外へ出ていた —— 行が bbox の対角の 1.3 倍という固定長で、輪郭との
    交点を 1 度も取っていなかった。起点 `189fedc7` の実測は 413.9px / 423.3px で、
    ここの限度 20.0px の 20 倍である。
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


# --- S-7 面: 平行線・交差線が図形の中に収まること (engine 35) --------------- #
#
# 起点 `189fedc7` の実測: 三角形 413.9px / 四角 353.5px (hatch)、423.3px / 353.5px
# (crosshatch)。限度は `CANVAS.unit * 0.02` = 20.0px なので 20 倍だった。行の長さが
# bbox の対角の 1.3 倍という固定値で、輪郭との交点を 1 度も取っていなかった。


# 凹んだ雲形。`primitive` で凹形を名乗れるのは `cloudform` だけで、輪郭は演奏 seed
# から生えるので「凹んでいる個体」は掃引で選ぶしかない。この組は 30 行のうち 2 行が
# 空洞をまたぎ、2 本目の区間はどちらも 78px 以上ある (2026-08-15 実測)。判別力は
# テスト自身が数える (`multi_span_rows >= 2`) ので、選んだ値が腐れば赤くなる。
CONCAVE = {"primitive": "cloudform", "center": [0.5, 0.5], "size": [0.7, 0.5]}
CONCAVE_SEED = 99
CONCAVE_SURFACE = {"direction": "horizontal", "density": 0.8}


def _hatch_spacings(body: str) -> list[str]:
    """描かれた順の `hatch-spacing-*` の値。製品が自分で書いた間隔である。"""
    return re.findall(r"hatch-spacing-([0-9.]+)", body)


def _hatch_axes(surface: dict) -> tuple[tuple[float, float], tuple[float, float]]:
    """行の向き `u` と行を並べる向き `n`。"""
    instruction = Instruction.model_validate(
        dict(SQUARE, weight="pen", filled=False, surface=surface)
    )
    assert instruction.surface is not None
    angle = _surface_line_angle(instruction.surface)
    return (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))


def _row_offsets(
    points: list[tuple[float, float]],
    normal: tuple[float, float],
    spacing: float,
) -> list[float]:
    """墨そのものから行を数える。

    行の位置を製品の式から引き写すと、式を壊した実装でも同じ答えが出る。墨を
    `n` へ射影して間隔の 0.4 倍より広い切れ目で割ると、行は墨だけから出る。
    """
    projected = sorted(p[0] * normal[0] + p[1] * normal[1] for p in points)
    clusters: list[list[float]] = [[projected[0]]]
    for value in projected[1:]:
        if value - clusters[-1][-1] > spacing * 0.4:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [(cluster[0] + cluster[-1]) / 2 for cluster in clusters]


@pytest.mark.parametrize("texture", ("hatch", "crosshatch"))
def test_s7_hatch_stays_inside_a_square(texture: str) -> None:
    """T-2。三角形 (S-3) だけで測ると図形が 1 つしかない。

    engine 25 の摂動 4 本が空振りしたのは 5 つの layout を全部 `circle` で測って
    いたからで、形の主張は形を替えて 2 度測らないと担保にならない。
    起点の実測はどちらの語も 353.5px。
    """
    svg = _render(SQUARE, texture, profile="editable")
    instruction = Instruction.model_validate(
        dict(SQUARE, weight="pen", filled=False, surface={**BASE_SURFACE, "texture": texture})
    )
    contour = _surface_contour(
        instruction, CANVAS, render_seed=12345, ins_idx=0, mark_idx=0
    )
    assert contour == [(280.0, 280.0), (720.0, 280.0), (720.0, 720.0), (280.0, 720.0)]
    points = _ink_points(_surface_body(svg))
    assert len(points) >= 200, len(points)
    excursion = max(_distance_outside(p, contour) for p in points)
    assert excursion <= CANVAS.unit * 0.02, excursion


def test_s7_no_row_crosses_the_void_of_a_concave_form() -> None:
    """T-3。輪郭の外に出ないことと、内側の空洞に入らないことは別の主張である。

    凸形なら交点は 2 つしかないので、「最初と最後の交点で切る」実装でも T-1/T-2 は
    緑になる。空洞をまたぐ行があって初めて、区間ごとに描いているかが測れる。
    ここは 3 つを測る —— 空洞をまたぐ行が実在すること (判別力)、墨が自分の行の
    区間の中にあること (またいでいない)、長い区間に墨があること (捨てていない)。
    """
    surface = {**BASE_SURFACE, "texture": "hatch", **CONCAVE_SURFACE}
    svg = _render(
        CONCAVE, "hatch", profile="editable", render_seed=CONCAVE_SEED, **CONCAVE_SURFACE
    )
    body = _surface_body(svg)
    instruction = Instruction.model_validate(
        dict(CONCAVE, weight="pen", filled=False, surface=surface)
    )
    contour = _surface_contour(
        instruction, CANVAS, render_seed=CONCAVE_SEED, ins_idx=0, mark_idx=0
    )
    assert contour is not None and len(contour) > 3
    spacings = {float(value) for value in _hatch_spacings(body)}
    assert len(spacings) == 1, spacings
    spacing = spacings.pop()
    unit, normal = _hatch_axes(surface)
    points = _ink_points(body)
    assert len(points) >= 200, len(points)

    multi_span_rows = 0
    for offset in _row_offsets(points, normal, spacing):
        spans = _line_spans(
            contour, (normal[0] * offset, normal[1] * offset), unit
        )
        assert spans, offset
        if len(spans) > 1:
            multi_span_rows += 1
        on_this_row = [
            p[0] * unit[0] + p[1] * unit[1]
            for p in points
            if abs(p[0] * normal[0] + p[1] * normal[1] - offset) <= spacing * 0.4
        ]
        # またいでいない: 墨は自分の行のどれかの区間の中にある。1 本で空洞を
        # またぐと、空洞のぶんだけどの区間からも外れる。
        for along in on_this_row:
            assert min(
                max(start - along, 0.0, along - end) for start, end in spans
            ) <= 1.0, (offset, along, spans)
        # 捨てていない: 長い区間には墨がある。2 本目以降を落とす実装はここで落ちる
        # (この個体の 2 本目はどちらも 78px 以上ある)。
        for start, end in spans:
            if end - start > 40.0:
                assert [
                    along for along in on_this_row if start + 2.0 <= along <= end - 2.0
                ], (offset, start, end)
    assert multi_span_rows >= 2, multi_span_rows


def test_s7_spacing_gradient_still_leans_the_pitch() -> None:
    """T-4。切る書き換えで濃さの傾きを落としていないことの担保。

    **⚠ コーパスの hatch / crosshatch 9 件は全部 `spacing_gradient="none"` なので、
    入力はここに書く**(2026-08-15 実測)。コーパスの焼き直しでは緑にならない。
    `_scanline_segments` へ置き換える実装はここで落ちる —— あれは一様間隔しか
    作れない。
    """
    for gradient, rising in (("coarse_to_dense", False), ("dense_to_coarse", True)):
        body = _surface_body(
            _render(SQUARE, "hatch", profile="editable", spacing_gradient=gradient)
        )
        values = [float(value) for value in _hatch_spacings(body)]
        assert len(set(values)) >= 2, (gradient, set(values))
        ordered = (
            all(a <= b for a, b in zip(values, values[1:]))
            if rising
            else all(a >= b for a, b in zip(values, values[1:]))
        )
        assert ordered, (gradient, values[:8], values[-8:])
        assert max(values) / min(values) > 1.5, (gradient, min(values), max(values))


def test_s7_spacing_gradient_none_keeps_the_pitch_of_the_branch_point() -> None:
    """T-5。裁定 3 の担保 —— 間隔は動かしていない。

    作者は「図形の中に収めたとき、線の引き方は規則的なまま残す」と裁定した
    (2026-08-14)。1 本ごとの揺らぎを足す改良はここで落ちる。21.250 は起点
    `189fedc7` のコーパス `C-surface-hatch-pen` が持っていた値そのものである。
    """
    for texture in ("hatch", "crosshatch"):
        body = _surface_body(_render(SQUARE, texture, profile="editable"))
        assert set(_hatch_spacings(body)) == {"21.250"}, texture


def test_s7_every_row_that_meets_the_contour_is_drawn() -> None:
    """T-6。「外を消す」だけで「中を減らす」をしていないことの担保。

    行は輪郭の端から端まで、自分が名乗った間隔で並んでいる。輪郭と交わる行を
    落とす実装 (短い区間を閾値で捨てる、など) はここで落ちる。間隔は製品が書いた
    `hatch-spacing-*` から読む —— 製品の式を書き写すと、式を壊した実装でも同じ
    答えが出る。
    """
    body = _surface_body(_render(SQUARE, "hatch", profile="editable"))
    spacings = {float(value) for value in _hatch_spacings(body)}
    assert len(spacings) == 1, spacings
    spacing = spacings.pop()
    instruction = Instruction.model_validate(
        dict(SQUARE, weight="pen", filled=False, surface={**BASE_SURFACE, "texture": "hatch"})
    )
    contour = _surface_contour(
        instruction, CANVAS, render_seed=12345, ins_idx=0, mark_idx=0
    )
    unit, normal = _hatch_axes({**BASE_SURFACE, "texture": "hatch"})
    offsets = _row_offsets(_ink_points(body), normal, spacing)
    # 1 行 = 1 本。凸形は交点が 2 つしかないので、行と描かれた要素は 1 対 1 である。
    assert len(offsets) == body.count("surface-stroke-v1"), len(offsets)
    projected = [p[0] * normal[0] + p[1] * normal[1] for p in contour]
    low, high = min(projected), max(projected)
    assert offsets[0] - low <= spacing * 1.4, offsets[0] - low
    assert high - offsets[-1] <= spacing * 1.4, high - offsets[-1]
    gaps = [b - a for a, b in zip(offsets, offsets[1:])]
    assert max(gaps) <= spacing * 1.4, max(gaps)


@pytest.mark.parametrize("texture", ("hatch", "crosshatch"))
def test_s7_hatch_stays_inside_in_the_compat_profile(texture: str) -> None:
    """T-7。`clipPath` で切った実装はここで落ちる。

    `compat` は clip-path を 1 つも出せない (SPEC §1180)。display だけで測る受入は
    clip の実装を素通りさせるので、同じ物差しを profile を替えてもう 1 度当てる。
    """
    for shape in (SQUARE, TRIANGLE):
        svg = _render(shape, texture, profile="compat")
        body = _surface_body(svg)
        assert "clip-path" not in body
        instruction = Instruction.model_validate(
            dict(shape, weight="pen", filled=False, surface={**BASE_SURFACE, "texture": texture})
        )
        contour = _surface_contour(
            instruction, CANVAS, render_seed=12345, ins_idx=0, mark_idx=0
        )
        points = _ink_points(body)
        assert len(points) >= 200, len(points)
        excursion = max(_distance_outside(p, contour) for p in points)
        assert excursion <= CANVAS.unit * 0.02, (texture, excursion)
