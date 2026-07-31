"""render engine 19: 地が描く手に抵抗する。

絵画で地が持つ役割は、描く手に抵抗することである。吸い込む地では線が滲み、
弾く地では掠れる。engine 18 まで地と描画は独立に合成されるだけで出会っておらず、
描画側が `canvas.ground` を読む箇所は `renderer.py` の mezzotint 判定 1 つだけ、
`canvas.ground` を持つ作品は本番 1847 件中 31 件 = 1.7%、凍結 SVG では 0 件だった。

engine 19 は到達 99.7% の側に既定の支持体を置く。紙は 1 種の定数で、吸う / 弾くは
道具の側の性質である (作者裁定 2026-07-31)。

ここで留める性質は 3 つ。どれも「同じでないこと」ではなく、対照の摂動で緑のまま
になることまで確かめる — 幅が変わったことや digest が動いたことはデータを変えれば
必ず動くので、性質を守らない。

  1. 機械 (rotring / computer) は 1 バイトも動かない。対照: 手の道具は動く
  2. 要素は 1 つも増えない。対照: subpath は増える
  3. 強い段ほど発火が増える。対照: 段の順を入れ替えると落ちる
"""

from __future__ import annotations

import contextlib
import re

import pytest

from inku_server import stroke_engine
from inku_server.renderer import render
from inku_server.schema import Score
from inku_server.stroke_engine import (
    DEFAULT_SUPPORT,
    RESISTANCE_LEVELS,
    Support,
    synthesize_stroke,
)

# `_at` は `stroke_engine` 側の表を引く。段を差し替える対照の摂動が届くように
# するためで、上の import は値の比較にだけ使う。

SEED = 20260731
ELEMENT = re.compile(r"<(path|polyline|polygon|circle|rect|line|ellipse)[ />]")

MACHINES = ("rotring", "computer")
ABSORBED = ("brush_thin", "brush_thick")
REFUSED = ("pencil", "crayon", "chalk")


@contextlib.contextmanager
def _at(level: str):
    original = stroke_engine.RESISTANCE
    stroke_engine.RESISTANCE = stroke_engine.RESISTANCE_LEVELS[level]
    try:
        yield
    finally:
        stroke_engine.RESISTANCE = original


def _score(weight: str) -> Score:
    """直線 5 本 + 弧 1 本。

    掠れは 1 ストロークにつき 1 度も起きないことがあるので、1 本では段の違いが
    運任せになる。契約の目視材料と同じ図柄・同じ seed。
    """
    lines = [
        {
            "primitive": "line",
            "from": [0.08, y],
            "to": [0.92, y],
            "weight": weight,
            "color": "black",
        }
        for y in (0.10, 0.20, 0.30, 0.40, 0.50)
    ]
    return Score.model_validate(
        {
            "version": "0.1.0",
            "canvas": "square",
            "background": "white",
            "instructions": lines
            + [
                {
                    "primitive": "arc",
                    "center": [0.50, 0.76],
                    "radius": 0.20,
                    "angle_start": 20.0,
                    "angle_end": 300.0,
                    "weight": weight,
                    "color": "black",
                }
            ],
        }
    )


def _svg(weight: str, level: str) -> str:
    with _at(level):
        return render(_score(weight), render_seed=SEED)


def _elements(svg: str) -> int:
    return len(ELEMENT.findall(svg))


def _subpaths(svg: str) -> int:
    return sum(d.count("M ") for d in re.findall(r'\sd="([^"]*)"', svg))


# --- 1. 機械は紙を受けない ------------------------------------------------- #


@pytest.mark.parametrize("weight", MACHINES)
def test_the_machines_are_byte_identical_at_every_level(weight: str) -> None:
    """製図ペンと計算機には紙との接触が無い。

    抵抗を最強の段まで上げても 1 バイトも動かないこと。ここが動くなら、
    抵抗が道具の性質でなく全体にかかる効果になっている。
    """
    baseline = _svg(weight, "g0")
    for level in ("g1", "g2", "g3"):
        assert _svg(weight, level) == baseline, (weight, level)


@pytest.mark.parametrize("weight", ABSORBED + REFUSED)
def test_the_hand_tools_do_move(weight: str) -> None:
    """上の対照。全部の道具が不変なら、機械が不変であることは何も言っていない。"""
    assert _svg(weight, "g2") != _svg(weight, "g0"), weight


def test_the_machines_would_move_if_they_were_given_a_bias(monkeypatch) -> None:
    """判別力の実測。

    機械が不変なのは紙を受けないからであって、機械がそもそも
    `stroke_engine` を通らないからではない — 通らないなら bias を与えても
    動かないので、この検査は恒真だったことになる。
    """
    biased = dict(stroke_engine.TOOL_SUPPORT_BIAS)
    biased["computer"] = (1.0, 1.0)
    monkeypatch.setattr(stroke_engine, "TOOL_SUPPORT_BIAS", biased)
    assert _svg("computer", "g2") != _svg("computer", "g0")


# --- 2. 要素は増えない。増えるのは subpath だけ ---------------------------- #


@pytest.mark.parametrize("weight", ABSORBED + REFUSED + MACHINES)
def test_no_level_adds_a_single_element(weight: str) -> None:
    """engine 15 の前例への恒久的な歯止め。

    地の描き分けを繊維で作ったとき、繊維 38 本で地が絵全体の 46% を占めた。
    支持体の違いは描画要素として積んではならない。SVG の 1 個の `path` は
    subpath を複数持てる (`ring_path` が既にそうしている) ので、墨を切っても
    要素は増えない。
    """
    expected = _elements(_svg(weight, "g0"))
    for level in ("g1", "g2", "g3"):
        assert _elements(_svg(weight, level)) == expected, (weight, level)


@pytest.mark.parametrize("weight", REFUSED)
def test_the_refused_tools_gain_subpaths(weight: str) -> None:
    """上の対照。要素数が不変なだけなら、何も起きていなくても通る。"""
    assert _subpaths(_svg(weight, "g2")) > _subpaths(_svg(weight, "g0")), weight


@pytest.mark.parametrize("weight", ABSORBED + MACHINES)
def test_the_tools_the_sheet_does_not_refuse_keep_their_subpaths(weight: str) -> None:
    """吸われる道具と機械では墨が切れない。切れているなら閾値が緩すぎる。"""
    assert _subpaths(_svg(weight, "g2")) == _subpaths(_svg(weight, "g0")), weight


# --- 3. 強い段ほど発火が増える -------------------------------------------- #


def _widest_ratio(weight: str, level: str, seeds: int = 200) -> tuple[float, float]:
    """段 g0 に対する per-sample 幅倍率の最小と最大。"""
    low, high = 1.0, 1.0
    for seed in range(seeds):
        with _at("g0"):
            base = synthesize_stroke((10.0, 10.0), (500.0, 10.0), 4.0, weight, seed)
        with _at(level):
            played = synthesize_stroke((10.0, 10.0), (500.0, 10.0), 4.0, weight, seed)
        for a, b in zip(played.samples, base.samples):
            ratio = a.width / b.width
            low, high = min(low, ratio), max(high, ratio)
    return low, high


def test_a_stronger_sheet_swells_the_absorbed_tool_further() -> None:
    """滲みの単調性。

    §5 の罠 2 がここで捕まる: 到着点の探索範囲を span の分だけ狭めると、span の
    大きい強い段ほど発火しなくなり、倍率が 1.00 のままになる。
    """
    highs = [_widest_ratio("brush_thin", level)[1] for level in ("g1", "g2", "g3")]
    assert highs[0] < highs[1] < highs[2], highs
    assert highs[0] > 1.0, highs


def test_a_stronger_sheet_cuts_the_refused_tool_further() -> None:
    """掠れの単調性。墨の切れ目 = subpath の数で測る。"""
    for weight in REFUSED:
        counts = [_subpaths(_svg(weight, level)) for level in ("g0", "g1", "g2", "g3")]
        assert counts[0] < counts[1] < counts[2] < counts[3], (weight, counts)


def test_the_monotonicity_check_fails_when_the_levels_are_swapped(monkeypatch) -> None:
    """上 2 つの対照。

    段を入れ替えても通るなら、単調性の検査は段の強さを見ていない。
    """
    plain = [_subpaths(_svg("pencil", level)) for level in ("g0", "g1", "g2", "g3")]
    swapped_levels = dict(RESISTANCE_LEVELS)
    swapped_levels["g1"], swapped_levels["g3"] = (
        RESISTANCE_LEVELS["g3"],
        RESISTANCE_LEVELS["g1"],
    )
    monkeypatch.setattr(stroke_engine, "RESISTANCE_LEVELS", swapped_levels)
    counts = [_subpaths(_svg("pencil", level)) for level in ("g0", "g1", "g2", "g3")]
    # 摂動が届いたこと自体を先に見る。届いていなければ下の否定は恒真になる。
    assert counts != plain, counts
    assert counts[1] > counts[3], counts
    assert not counts[0] < counts[1] < counts[2] < counts[3], counts


# --- 支持体の差し替え口 ----------------------------------------------------- #


def test_the_default_sheet_is_the_one_constant_paper() -> None:
    assert DEFAULT_SUPPORT == Support(absorb=1.0, tooth=1.0)


@pytest.mark.parametrize("weight", ABSORBED + REFUSED)
def test_a_sheet_that_neither_drinks_nor_refuses_leaves_the_tool_alone(
    weight: str,
) -> None:
    """`canvas.ground.material` ごとの表を次段で載せるための差し替え口。

    支持体の側を 0 にすると、道具の bias が何であれ engine 18 の演奏に戻る。
    """
    blank = Support(absorb=0.0, tooth=0.0)
    for seed in range(20):
        with _at("g0"):
            base = synthesize_stroke((10.0, 10.0), (500.0, 10.0), 4.0, weight, seed)
        with _at("g2"):
            played = synthesize_stroke(
                (10.0, 10.0), (500.0, 10.0), 4.0, weight, seed, support=blank
            )
        assert played.outline == base.outline, (weight, seed)


def test_the_retired_absorbency_field_did_not_come_back() -> None:
    """支持体はモジュール定数の表であって Score のフィールドではない。

    `ground.absorbency` は engine 15 で退役し、`schema.py` が保存済み Score から
    落とす。同じ名前を復活させると、その migration が意味を失う。
    """
    from inku_server.schema import CanvasGroundSpec

    assert "absorbency" not in CanvasGroundSpec.model_fields
    assert not hasattr(Support, "model_fields")


# --- 掠れは幅ではなく墨の有無で出る ---------------------------------------- #


def test_the_cut_leaves_bare_paper_rather_than_a_thinner_line() -> None:
    """§5 の罠 1。

    弾かれるべき道具はちょうど最も細い道具 (pencil 1.5px / chalk 3px /
    crayon 4px) なので、幅を 0.25 倍にしても 520px ラスタで 0.20〜0.52px にしか
    ならず、アンチエイリアスに沈む。掠れは「墨がつかない = 白が残る」現象であって
    「線が細くなる」ことではないので、1 本のストロークが複数の run に割れる。
    """
    cut = 0
    for seed in range(200):
        with _at("g2"):
            played = synthesize_stroke((10.0, 10.0), (500.0, 10.0), 1.5, "pencil", seed)
        if any(point[0] != point[0] for point in played.outline):
            cut += 1
    assert cut > 0
    # 全ストロークが切れていたら、それは地の抵抗ではなく点線である。
    assert cut < 200, cut
