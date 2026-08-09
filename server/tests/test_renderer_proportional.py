"""v2.1: 揺らぎ・滲みの図形寸法比例化と、材質・display 層の canvas 相対化。

契約は no-git-sync/fable5/claude_code/tasks/opus-v2.1-proportional-render.md。
語彙 (fine/medium/broad) は不変で、語彙が指す物理量の定義だけが変わる。
"""

import math
import statistics
from xml.etree import ElementTree

import pytest

from inku_server import renderer
from inku_server.master_grid import fmt
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.renderer import (
    AMPLITUDE_CLAMP_RATIO,
    MATERIAL_INTENSITY,
    MATERIAL_INTENSITY_LEVEL,
    AMPLITUDE_WIDTHS,
    BLUR_RATIO,
    SEGMENT_COUNT_MAX,
    SEGMENT_COUNT_MIN,
    SPECK_COUNT_MIN,
    STYLE_TO_DASH,
    WEIGHT_TO_STROKE_WIDTH,
    _amplitude_px,
    _clamped_representative_px,
    _material_outline_profile,
    _performance_touch_filter,
    _segment_count,
    _speck_count,
    _speck_profile,
    _stroke_width_px,
    _texture_filter_xml,
    render,
)
from inku_server.schema import Score, Variation

SQUARE = canvas_size_for_aspect(None)
VERTICAL = canvas_size_for_aspect("vertical")  # 9:16 → unit = width < 1000


def _circle_score(radius: float, **variation) -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": radius,
                    "variation": variation or None,
                }
            ]
        }
    )


def _contour(svg: str) -> list[tuple[float, float]]:
    """揺らぎ適用後の polygon / polyline 頂点列を取り出す。"""
    root = ElementTree.fromstring(svg)
    for node in root.iter():
        if node.tag.endswith(("polygon", "polyline")):
            return [
                (float(p.split(",")[0]), float(p.split(",")[1]))
                for p in node.attrib["points"].split()
            ]
    raise AssertionError("contour not found")


def _max_radial_deviation(svg: str, r: float) -> float:
    return max(
        abs(math.hypot(x - 500.0, y - 500.0) - r) for x, y in _contour(svg)
    )


# --------------------------------------------------------------------------- #
# 1. 振幅が痕の線幅に比例する (engine 28)                                       #
# --------------------------------------------------------------------------- #
def test_amplitude_px_is_exactly_proportional_to_stroke_width():
    """振幅そのものは線幅に厳密比例し、図形の大きさでは動かない。

    engine 27 まで、この場所は「代表寸法への厳密比例」を守っていた
    (test_amplitude_px_is_exactly_proportional_to_representative_size)。物差しが
    入れ替わったことが記録に残るよう、同じ場所で逆向きの性質を見る。
    """
    variation = Variation(
        amplitude="medium", frequency="medium", quality="wave", dimensions=["radius"]
    )
    small = _circle_score(0.1).instructions[0]
    large = _circle_score(0.2).instructions[0]
    assert _amplitude_px(variation, small, SQUARE) == pytest.approx(
        AMPLITUDE_WIDTHS["medium"] * _stroke_width_px("pen", SQUARE)
    )
    # 図形が 2 倍になっても振幅は動かない (engine 27 ではここが 2 倍だった)。
    assert _amplitude_px(variation, large, SQUARE) == pytest.approx(
        _amplitude_px(variation, small, SQUARE)
    )


def test_amplitude_px_follows_the_tool_and_the_thinness():
    """同じ図形でも、道具が変われば・細く引けば振幅が変わる。

    線幅を決める 2 つの入力 (weight / thinness) の両方が振幅へ届いていることを
    見る。片方だけを配線しても通る検査にしない。
    """
    variation = Variation(
        amplitude="medium", frequency="medium", quality="wave", dimensions=["radius"]
    )

    def amp(**fields) -> float:
        ins = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "circle",
                        "center": [0.5, 0.5],
                        "radius": 0.2,
                        **fields,
                    }
                ]
            }
        ).instructions[0]
        return _amplitude_px(variation, ins, SQUARE)

    pen = amp(weight="pen")
    brush = amp(weight="brush_thick")
    pen_fine = amp(weight="pen", thinness="fine")
    assert brush == pytest.approx(
        pen
        * WEIGHT_TO_STROKE_WIDTH["brush_thick"]
        / WEIGHT_TO_STROKE_WIDTH["pen"]
    )
    assert pen_fine == pytest.approx(pen * 0.6)
    assert pen_fine < pen < brush


# perlin / white は seed が命令ごとに変わるため雑音の実現値が図形間で異なる。
# 振幅は厳密に等しくても観測される最大変位はばらつくので、決定的な wave だけ
# 狭く、雑音系は幅を持たせて検査する。
@pytest.mark.parametrize(
    ("quality", "tolerance"), [("wave", 0.02), ("perlin", 0.25), ("white", 0.25)]
)
def test_closed_contour_amplitude_does_not_scale_with_shape_size(
    quality: str, tolerance: float
):
    """図形サイズ 2 倍でも揺らぎオフセットの絶対量は変わらない (閉輪郭)。

    engine 27 まではここが「約 2 倍」だった。比は 1 回の演奏では決まらない
    (最大変位は包絡線の推定量にすぎず、雑音系は引きによって大きく振れる) ので、
    seed をまたいだ中央値で見る作法はそのまま残す。
    """
    variation = {
        "quality": quality,
        "amplitude": "medium",
        "frequency": "medium",
        "dimensions": ["radius"],
    }
    ratios = []
    for render_seed in (None, 1, 2, 3, 7, 11, 12345, 999):
        kwargs = {} if render_seed is None else {"render_seed": render_seed}
        small = _max_radial_deviation(
            render(_circle_score(0.1, **variation), **kwargs), 100.0
        )
        large = _max_radial_deviation(
            render(_circle_score(0.2, **variation), **kwargs), 200.0
        )
        ratios.append(large / small)
    assert statistics.median(ratios) == pytest.approx(1.0, rel=tolerance)


def test_open_curve_amplitude_does_not_scale_with_shape_size():
    """開曲線 (arc) でも図形サイズ 2 倍で振幅は変わらない。"""

    def deviation(radius: float) -> float:
        score = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "arc",
                        "center": [0.5, 0.5],
                        "radius": radius,
                        "angle_start": 0,
                        "angle_end": 180,
                        "variation": {
                            "quality": "wave",
                            "amplitude": "broad",
                            "frequency": "medium",
                            "dimensions": ["radius"],
                        },
                    }
                ]
            }
        )
        return _max_radial_deviation(render(score), radius * 1000.0)

    assert deviation(0.3) / deviation(0.15) == pytest.approx(1.0, rel=0.1)


@pytest.mark.parametrize("thinness", (None, "fine"))
@pytest.mark.parametrize("weight", ("pencil", "pen", "brush_thick", "crayon"))
def test_the_drawn_arc_leaves_its_line_by_its_ruled_share_of_its_own_width(
    weight: str, thinness: str | None
):
    """描いた絵の上で、ずれが「その道具自身の線幅の 0.6 倍」であること。

    ここだけが定数と絵を結びつける。`_amplitude_px` の単体検査は定数と関数の
    一致しか見ず、大きさ間の不変性を見る 2 本は「振幅を定数に落とした実装」でも
    通る (どちらの図形でも同じずれが出るため)。道具と thinness で線幅を振って
    絵の上の比を測ると、線幅を経由していない実装はここで初めて赤くなる。

    契約 the-mark-stays-on-its-line.md の T-1 (ずれ / 線幅 <= 1.2) と
    T-2 (>= 0.3) は「描いた絵で」測ることを求めていた。engine 27 ではこの比が
    半径の 7.9〜8.5% (2.88〜12.21 線幅) で、半径に比例していた。
    """
    variation = {
        "quality": "wave",
        "amplitude": "medium",
        "frequency": "medium",
        "dimensions": ["radius"],
    }

    def ratio(radius: float) -> float:
        instruction: dict = {
            "primitive": "arc",
            "center": [0.5, 0.5],
            "radius": radius,
            "angle_start": 0,
            "angle_end": 180,
            "weight": weight,
            "variation": variation,
        }
        if thinness is not None:
            instruction["thinness"] = thinness
        score = Score.model_validate({"instructions": [instruction]})
        # 雑音系ではなく wave なので 1 引きで決まるが、包絡線の推定量である
        # ことは変わらないので複数 seed の中央値を取る。
        deviations = [
            _max_radial_deviation(render(score, render_seed=seed), radius * 1000.0)
            for seed in (1, 2, 3, 7, 11)
        ]
        return statistics.median(deviations) / _stroke_width_px(weight, SQUARE, thinness)

    expected = AMPLITUDE_WIDTHS["medium"]
    for radius in (0.12, 0.36):
        assert ratio(radius) == pytest.approx(expected, rel=0.05)
    # 契約の両端。上限は「痕の上に戻ったこと」、下限は「揺らぎを消していないこと」。
    assert 0.3 <= ratio(0.24) <= 1.2


def test_amplitude_vocabulary_keeps_its_order():
    """fine < medium < broad の順序は比例化後も保たれる。"""
    devs = [
        _max_radial_deviation(
            render(
                _circle_score(
                    0.2,
                    quality="wave",
                    amplitude=amp,
                    frequency="medium",
                    dimensions=["radius"],
                )
            ),
            200.0,
        )
        for amp in ("fine", "medium", "broad")
    ]
    assert devs[0] < devs[1] < devs[2]


# --------------------------------------------------------------------------- #
# 2. 滲み (pink) も図形寸法比例                                                 #
# --------------------------------------------------------------------------- #
def test_blur_std_scales_with_shape_size():
    """stdDeviation が代表寸法に比例する (図形 2 倍 → 滲み 2 倍)。"""

    def std(radius: float) -> float:
        svg = render(_circle_score(radius, quality="pink", amplitude="medium"))
        root = ElementTree.fromstring(svg)
        for node in root.iter():
            if node.tag.endswith("feGaussianBlur"):
                return float(node.attrib["stdDeviation"])
        raise AssertionError("blur filter not found")

    assert std(0.1) == pytest.approx(BLUR_RATIO["medium"] * 100.0, rel=0.05)
    assert std(0.2) / std(0.1) == pytest.approx(2.0, rel=0.05)


def test_blur_filter_ids_separate_by_std_value():
    """同じ振幅語でも図形が違えば別 filter になる (id が値込みのため)。"""
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.3, 0.5],
                    "radius": 0.1,
                    "variation": {"quality": "pink", "amplitude": "medium"},
                },
                {
                    "primitive": "circle",
                    "center": [0.7, 0.5],
                    "radius": 0.3,
                    "variation": {"quality": "pink", "amplitude": "medium"},
                },
            ]
        }
    )
    svg = render(score)
    assert svg.count("<filter id=\"blur-medium-") == 2


# --------------------------------------------------------------------------- #
# 3. クランプ                                                                   #
# --------------------------------------------------------------------------- #
def test_tiny_shape_is_not_destroyed_by_wobble():
    """極小図形でも振幅が図形を壊さない (負半径・原点貫通なし)。"""
    r = 0.004 * 1000.0
    svg = render(
        _circle_score(
            0.004,
            quality="perlin",
            amplitude="broad",
            frequency="high",
            dimensions=["radius"],
        )
    )
    for x, y in _contour(svg):
        dist = math.hypot(x - 500.0, y - 500.0)
        assert dist > 0.0
        # 下限クランプで振幅は canvas.unit 基準になるが、暴走はしない
        assert dist < r + SQUARE.unit * 0.02 * AMPLITUDE_CLAMP_RATIO + 1e-6


def test_large_shape_amplitude_stays_within_clamp():
    """極大図形でも振幅は代表寸法比の上限を超えない。"""
    r = 450.0
    svg = render(
        _circle_score(
            0.45,
            quality="perlin",
            amplitude="broad",
            frequency="medium",
            dimensions=["radius"],
        )
    )
    assert _max_radial_deviation(svg, r) <= r * AMPLITUDE_CLAMP_RATIO + 1e-6


def test_the_clamp_spares_ordinary_figures_and_binds_on_tiny_ones():
    """クランプは異常値の保険であって、常用域では効かない。

    engine 27 まではここが `max(AMPLITUDE_RATIO) < AMPLITUDE_CLAMP_RATIO` の
    定数比較だった。物差しが線幅になった今、どちらが効くかは図形の大きさで
    決まるので、両側を実際に測る。片側だけだと、クランプが常時効いていても
    ・一度も効かなくても通ってしまう。
    """
    variation = Variation(
        amplitude="broad", frequency="medium", quality="wave", dimensions=["radius"]
    )

    def parts(radius: float) -> tuple[float, float, float]:
        ins = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "circle",
                        "center": [0.5, 0.5],
                        "radius": radius,
                        "weight": "brush_thick",
                    }
                ]
            }
        ).instructions[0]
        width = AMPLITUDE_WIDTHS["broad"] * _stroke_width_px("brush_thick", SQUARE)
        cap = AMPLITUDE_CLAMP_RATIO * _clamped_representative_px(ins, SQUARE)
        return _amplitude_px(variation, ins, SQUARE), width, cap

    # 常用域 (半径 200px): 線幅の側が効き、クランプには触れない。
    amp, width, cap = parts(0.2)
    assert amp == pytest.approx(width)
    assert width < cap

    # 自分の痕より小さい図形: クランプの側が効く。
    amp, width, cap = parts(0.004)
    assert amp == pytest.approx(cap)
    assert cap < width


# --------------------------------------------------------------------------- #
# 4. 分割数の長さ比例化                                                         #
# --------------------------------------------------------------------------- #
def test_segment_count_grows_with_length_and_saturates():
    target = SQUARE.unit * 0.01
    assert _segment_count(target * 50, SQUARE) == 50
    assert _segment_count(target * 100, SQUARE) == 100
    # 下限・上限で飽和する
    assert _segment_count(0.0, SQUARE) == SEGMENT_COUNT_MIN
    assert _segment_count(target * 10_000, SQUARE) == SEGMENT_COUNT_MAX


def test_longer_contour_gets_more_vertices():
    def vertices(radius: float) -> int:
        return len(
            _contour(
                render(
                    _circle_score(
                        radius,
                        quality="wave",
                        amplitude="fine",
                        frequency="medium",
                        dimensions=["radius"],
                    )
                )
            )
        )

    assert vertices(0.05) < vertices(0.15) < vertices(0.30)


def test_segment_count_is_deterministic():
    score = _circle_score(
        0.2, quality="perlin", amplitude="medium", frequency="high", dimensions=["radius"]
    )
    assert render(score, render_seed=7) == render(score, render_seed=7)


# --------------------------------------------------------------------------- #
# 5. speck の周長比例化                                                         #
# --------------------------------------------------------------------------- #
def test_speck_count_is_proportional_to_perimeter():
    """基準 (radius 0.2 の円) で表の個数 × 強度ゲイン、周長 2 倍で約 2 倍。"""
    anchor = 2 * math.pi * 0.2 * SQUARE.unit
    gain = MATERIAL_INTENSITY[MATERIAL_INTENSITY_LEVEL]["speck_count"]
    assert _speck_count(18, anchor, SQUARE) == round(18 * gain)
    # 上限 (基準の 4 倍) に触れない範囲で周長比例を見る
    assert _speck_count(18, anchor * 1.5, SQUARE) == round(27 * gain)
    # 下限と上限
    assert _speck_count(18, 0.0, SQUARE) == SPECK_COUNT_MIN
    assert _speck_count(18, anchor * 100, SQUARE) == 18 * 4


def test_speck_profile_is_deterministic():
    a = _speck_profile("chalk", 1600.0, SQUARE)
    b = _speck_profile("chalk", 1600.0, SQUARE)
    assert a == b
    assert _speck_profile("pen", 1600.0, SQUARE) is None


# --------------------------------------------------------------------------- #
# 6. unit=1000 でのバイト一致 (C 層・線幅・dasharray)                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("weight", sorted(WEIGHT_TO_STROKE_WIDTH))
def test_stroke_width_matches_the_table_at_unit_1000(weight: str):
    assert _stroke_width_px(weight, SQUARE) == WEIGHT_TO_STROKE_WIDTH[weight]


def test_dasharray_strings_are_unchanged_at_unit_1000():
    svg = render(
        Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "line",
                        "from": [0.0, 0.5],
                        "to": [1.0, 0.5],
                        "style": "dashed",
                        "weight": "rotring",
                    }
                ]
            }
        )
    )
    expected_dash = ",".join(
        fmt(float(value)) for value in STYLE_TO_DASH["dashed"].split(",")
    )
    assert f'stroke-dasharray="{expected_dash}"' in svg


def test_performance_touch_filter_is_unchanged_at_unit_1000():
    """C 層は機械的相対化のみ。unit=1000 で現行とバイト一致する。"""
    _, xml = _performance_touch_filter(4242, SQUARE)
    assert 'baseFrequency="0.01' in xml or 'baseFrequency="0.02' in xml
    scale = float(xml.split('scale="')[1].split('"')[0])
    assert 1.6 <= scale <= 3.0


def test_texture_filter_xml_is_unchanged_at_unit_1000(monkeypatch):
    """単位換算だけを見るため強度は起点 (m0) に固定する。"""
    monkeypatch.setattr(renderer, "MATERIAL_INTENSITY_LEVEL", "m0")
    assert _texture_filter_xml("pencil", SQUARE) == (
        '<filter id="texture-pencil" x="-12%" y="-12%" width="124%" height="124%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.900000" numOctaves="2" '
        'seed="11" result="noise"/>'
        '<feDisplacementMap in="SourceGraphic" in2="noise" scale="0.700000"/>'
        "</filter>"
    )
    assert _texture_filter_xml("drypoint", SQUARE) == (
        '<filter id="texture-drypoint" x="-35%" y="-35%" width="170%" height="170%">'
        '<feGaussianBlur stdDeviation="1.800000"/>'
        "</filter>"
    )


# --------------------------------------------------------------------------- #
# 7. 縦長 aspect (unit < 1000) で B 層が unit 比に縮む                          #
# --------------------------------------------------------------------------- #
def test_material_layer_shrinks_with_canvas_unit():
    assert VERTICAL.unit < SQUARE.unit
    ratio = VERTICAL.unit / SQUARE.unit

    assert _stroke_width_px("brush_thick", VERTICAL) == pytest.approx(
        WEIGHT_TO_STROKE_WIDTH["brush_thick"] * ratio
    )

    square_profile = _material_outline_profile("chalk", SQUARE)
    vertical_profile = _material_outline_profile("chalk", VERTICAL)
    for (s_off, s_w, s_op, _), (v_off, v_w, v_op, _) in zip(
        square_profile, vertical_profile
    ):
        assert v_off == pytest.approx(s_off * ratio)
        assert v_w == pytest.approx(s_w * ratio)
        assert v_op == s_op  # opacity は寸法ではないので不変

    _, s_spread, s_radius, _ = _speck_profile("chalk", 1600.0, SQUARE)
    _, v_spread, v_radius, _ = _speck_profile("chalk", 1600.0, VERTICAL)
    assert v_spread == pytest.approx(s_spread * ratio)
    assert v_radius == pytest.approx(s_radius * ratio)


def test_texture_base_frequency_is_inverse_to_unit():
    """feTurbulence の baseFrequency は 1/px なので unit に反比例する。"""

    def frequency(canvas) -> float:
        xml = _texture_filter_xml("crayon", canvas)
        return float(xml.split('baseFrequency="')[1].split('"')[0])

    assert frequency(VERTICAL) == pytest.approx(
        frequency(SQUARE) * SQUARE.unit / VERTICAL.unit, rel=1e-4
    )
