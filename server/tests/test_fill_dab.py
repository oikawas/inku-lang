"""render engine 16 段 2: 微小な塗りは「塗る」のでなく「置く」。

内部を持つ本番 instruction 5748 のうち 4501 (78%) が短辺 2% 未満で、その 99.3% が
平坦だった。走査線の間隔が全 11 道具で 12px の定数なので、小さな図形は
`FILL_MIN_SCANLINES` = 3 本に届かず領域 fill へ縮退していた (意図的な縮退であり、
点のような粒子が輪郭だけになって消えるのを防ぐためのものだった)。

engine 16 はそこを打点にする。短辺 2% の円を「内部を走査して埋める」と考えるのが
誤りで、物としては筆を一度置いた跡である。

契約 §3.4 の F-1〜F-4。境界値は推測せず実測した (`test_f4_...` の docstring)。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import pathlib
import re

import pytest

import inku_server.renderer as renderer
import inku_server.stroke_engine as stroke_engine
from inku_server.renderer import render
from inku_server.schema import Score

ENGINE_15_MANIFEST = (
    pathlib.Path(__file__).resolve().parents[1]
    / "reference"
    / "render-engine-15"
    / "manifest.json"
)

# 実測した境界 (短辺 = キャンバス比)。下の F-4 を参照。
BELOW_BOUNDARY_RADIUS = 0.005   # 短辺 1.0%
ABOVE_BOUNDARY_RADIUS = 0.017   # 短辺 3.4%

HAND_TOOLS = (
    "brush_thick", "brush_thin", "burin", "chalk", "crayon",
    "drypoint", "pen", "pencil", "silverpoint",
)


def _render_circle(radius: float, weight: str, *, render_seed: int = 12345) -> str:
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": radius,
                    "filled": True,
                    "weight": weight,
                }
            ]
        }
    )
    return render(score, render_seed=render_seed, svg_profile="editable")


def _mechanism(svg: str) -> str:
    if "fill-stroke-v1" in svg:
        return "strokes"
    if "fill-texture-v1" in svg:
        return "texture"
    if "fill-dab-v1" in svg:
        return "dab"
    return "region"


# Render engine 22 split what goes on top of a fill into two, so "the interior
# was filled" is no longer one class name. These tests are about the dab
# boundary -- filled area against single touch -- so they ask the question that
# survived the split, and the branch itself is gated in
# `test_fill_underlay_and_branch.py`.
FILLED_AREA = frozenset({"strokes", "texture"})


def _normalized_digest(svg: str) -> str:
    normalized = re.sub(
        r"\d+\.\d+", lambda match: f"{round(float(match.group(0)), 6):.6f}", svg
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


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


# --- F-1 陽性: 微小な塗りが 1 筆の打点になる ------------------------------- #


def test_f1_a_tiny_filled_circle_is_placed_not_scanned() -> None:
    """engine 15 ではここが領域 fill だった。これが段 2 の赤である。"""
    svg = _render_circle(BELOW_BOUNDARY_RADIUS, "pen")
    assert _mechanism(svg) == "dab"


@pytest.mark.parametrize("weight", HAND_TOOLS)
def test_f1_the_dab_reaches_every_hand_tool(weight: str) -> None:
    assert _mechanism(_render_circle(BELOW_BOUNDARY_RADIUS, weight)) == "dab"


def test_f1_the_dab_is_one_stroke_not_a_scatter() -> None:
    """1 点 = 1 筆。打点が複数のパスに割れていたら「置いた」ことにならない。"""
    svg = _render_circle(BELOW_BOUNDARY_RADIUS, "pen")
    group = re.search(r'<g class="fill-dab-v1">(.*?)</g>', svg, flags=re.S)
    assert group is not None
    assert group.group(1).count("<path") == 1


def test_f1_the_dab_follows_the_long_axis_of_the_shape() -> None:
    """細長い図形は細長い一筆になる。円では運びが短くなる。

    幅を短い方の軸が決め、運びを長い方の軸が決めるので、図形の比が筆に出る。
    """

    def extent(size: list[float]) -> tuple[float, float]:
        score = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "square",
                        "position": [0.5 - size[0] / 2, 0.5 - size[1] / 2],
                        "size": size,
                        "filled": True,
                        "weight": "pen",
                    }
                ]
            }
        )
        svg = render(score, render_seed=12345, svg_profile="editable")
        group = re.search(r'<g class="fill-dab-v1">(.*?)</g>', svg, flags=re.S)
        assert group is not None, size
        points = [
            (float(x), float(y))
            for x, y in re.findall(r"([0-9]+\.[0-9]+) ([0-9]+\.[0-9]+)", group.group(1))
        ]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return max(xs) - min(xs), max(ys) - min(ys)

    # 両軸とも境界の下側にある比 4:1 の長方形。長い方が 24px なので、走査線は
    # どの角度でも 3 本に届かない (間隔は全道具で 12px の定数)。
    wide_w, wide_h = extent([0.024, 0.006])
    tall_w, tall_h = extent([0.006, 0.024])
    assert wide_w > wide_h * 2, (wide_w, wide_h)
    assert tall_h > tall_w * 2, (tall_w, tall_h)


# --- F-2 陰性: 境界の上側は engine 15 と 1 バイトも変わらない --------------- #


def test_f2_a_large_filled_circle_is_still_a_filled_area() -> None:
    """大きい塗りが打点へ落ちない。pen は engine 22 でテクスチャ枝へ移った。"""
    for radius in (0.05, 0.10, 0.30):
        assert _mechanism(_render_circle(radius, "pen")) in FILLED_AREA, radius


def test_f2_the_filled_cases_above_the_boundary_are_still_filled_areas() -> None:
    """段 2 の帰属の担保。短辺 2% 以上の塗りが打点や領域 fill へ落ちない。

    engine 16 の時点ではこれが「engine 15 と 1 バイトも変わらない」だった。
    **engine 22 は 31 件すべてを意図して動かしたので、バイト一致はもう主張ではない**
    (下地が入り、上層が枝分かれし、終端が変わる)。動いた先が正しいことは凍結コーパスの
    `changed_from_previous` が見る。ここに残る主張は、**この 31 件が塗られた面のまま
    である**こと — 打点へ落ちたり領域 fill へ縮退したりしていないこと — で、
    件数の 31 も併せて見るので case が消えれば落ちる。
    """
    cases = json.loads(ENGINE_15_MANIFEST.read_text())["cases"]
    above = sorted(
        case_id
        for case_id in cases
        if ("-fill-" in case_id and "tinyfill" not in case_id)
        or case_id == "D-size-large-filled-polygon"
    )
    assert len(above) == 31, above
    with _engine_15_seed_material():
        for case_id in above:
            svg = _replay(cases[case_id])
            assert _mechanism(svg) in FILLED_AREA, case_id
            assert "fill-underlay-v1" in svg, case_id


def test_f2_the_one_tiny_case_in_the_corpus_did_move() -> None:
    """判別力の実測。31 件が不変であることは、動くものが動いて初めて意味を持つ。

    契約 §3.3 は「コーパスに短辺 2% 未満のケースは 1 件も無い」と書いていたが、
    `D-size-tiny-filled-circle` (半径 0.003 = 短辺 0.6%) が実在する。
    """
    cases = json.loads(ENGINE_15_MANIFEST.read_text())["cases"]
    tiny = cases["D-size-tiny-filled-circle"]
    assert tiny["input"]["score"]["instructions"][0]["radius"] == 0.003
    assert _normalized_digest(_replay(tiny)) != tiny["digest"]
    assert _mechanism(_replay(tiny)) == "dab"


# --- F-3 陰性: rotring は領域 fill のまま ---------------------------------- #


def test_f3_the_drafting_pen_keeps_its_region_fill() -> None:
    """機械の極。engine 8 で輪郭を筆致から外したのと同じ理由で塗りも幾何のまま。"""
    for radius in (BELOW_BOUNDARY_RADIUS, ABOVE_BOUNDARY_RADIUS, 0.30):
        assert _mechanism(_render_circle(radius, "rotring")) == "region", radius


def test_f3_the_machine_pole_cases_are_byte_identical_to_engine_15() -> None:
    cases = json.loads(ENGINE_15_MANIFEST.read_text())["cases"]
    machine = sorted(
        case_id for case_id in cases if case_id.endswith("-filled-square-rotring")
    )
    assert len(machine) == 4, machine
    for case_id in machine:
        assert _normalized_digest(_replay(cases[case_id])) == cases[case_id]["digest"]


# --- F-4 境界: 直下と直上で機構が切り替わる -------------------------------- #


def test_f4_the_mechanism_switches_at_the_measured_boundary() -> None:
    """境界は実測値である。

    半径を 0.0005 刻みで掃いて機構が変わる点を探すと、全 5 道具・全 6 seed で
    **短辺 2.9%〜3.2%**（半径 0.0145〜0.0160）に 1 度だけ切り替わる。切り替わりは
    1 度きりで、行きつ戻りつしない。

        pen         2.9% .. 3.2%
        pencil      2.9% .. 3.1%
        brush_thick 2.9% .. 3.1%

    したがって短辺 1.0%（半径 0.005）は全条件で打点側、短辺 3.4%（半径 0.017）は
    全条件で走査側にある。コーパスの `C-tinyfill-*` はこの 2 つの値を使っている。
    """
    for weight in ("pen", "pencil", "brush_thick"):
        for seed in (1, 12345, 2**63 + 1):
            assert _mechanism(_render_circle(BELOW_BOUNDARY_RADIUS, weight, render_seed=seed)) == "dab"
            assert (
                _mechanism(_render_circle(ABOVE_BOUNDARY_RADIUS, weight, render_seed=seed))
                in FILLED_AREA
            )


def test_f4_the_boundary_is_crossed_exactly_once() -> None:
    """境界が 1 度しか現れないこと。行きつ戻りつするなら閾値とは呼べない。"""
    seen = []
    radius = 0.001
    while radius <= 0.060:
        seen.append(_mechanism(_render_circle(round(radius, 4), "pen")))
        radius += 0.001
    flips = [i for i in range(1, len(seen)) if seen[i] != seen[i - 1]]
    assert len(flips) == 1, [(i, seen[i - 1], seen[i]) for i in flips]
    assert seen[0] == "dab" and seen[-1] in FILLED_AREA
    boundary = 0.001 + flips[0] * 0.001
    assert 0.014 <= boundary <= 0.017, boundary
