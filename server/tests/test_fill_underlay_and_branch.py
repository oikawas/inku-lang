"""render engine 22: a fill gets an underlay, and what sits on it gets a branch.

Thirteen gates over the four stages of the contract
`no-git-sync/fable5/claude_code/tasks/fill-underlay-and-branch.md`:

    T-1 .. T-3   stage 1, the underlay
    T-4 .. T-6   stage 2, the branch
    T-7 .. T-11  stage 3, the variation and the terminal
    T-12 .. T-13 stage 4, the corpus

and nine more for the rulings the author made while the contract was running,
which arrive without gates of their own:

    T-14 .. T-16 the texture branch's direction, its contrast, the machine's raster
    T-17 .. T-19 its count, how its marks end, and chalk's own contrast
    T-20 .. T-22 the per-mark tone, the reserve, and chalk's bare paper

Three of these measure the geometry the renderer INTENDED, not the path string
it emitted. That is not a shortcut around the product: the intended centreline
is captured by wrapping the renderer's own `synthesize_along`, so the whole
product path -- the branch decision, the pitch, the per-stroke angle, the reach
past the contour -- runs exactly as it does in production, and only the
observation point moves. Reading angles back off the SVG cannot work: the
computer quantises its coordinates onto an 18px lattice (engine 18), which
tilts a fitted axis by about a degree and would make T-10's "the machine is
still exactly regular" unmeasurable.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import statistics

import pytest

import inku_server.renderer as renderer
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.renderer import (
    FILL_COVERAGE_BRANCH,
    FILL_COVERAGE_TARGET,
    FILL_MIN_SCANLINES,
    FILL_RASTER_HALO_STEP,
    FILL_REACH_WIDTHS_MIN,
    FILL_REACH_WIDTHS_SPAN,
    FILL_SCAN_CONTRAST,
    FILL_TEXTURE_CONTRAST,
    _fill_coverage,
    _fill_scan_spacing,
    _line_spans,
    _stroke_width_px,
    render,
)
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS, synthesize_along

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE_21_MANIFEST = SERVER_ROOT / "reference" / "render-engine-21" / "manifest.json"
ENGINE_22_MANIFEST = SERVER_ROOT / "reference" / "render-engine-22" / "manifest.json"

CANVAS = canvas_size_for_aspect(None)
RADIUS = 0.3
CIRCLE = {"primitive": "circle", "center": [0.5, 0.5], "radius": RADIUS}
SEED = 11

# The two sides of the threshold, as the corpus states them. crayon carries the
# deciding pair because it is the one tool whose thinness alone crosses the
# line: 0.333 bare, 0.117 at extra_fine.
SCAN_CASE = dict(CIRCLE, weight="crayon", filled=True)
TEXTURE_CASE = dict(CIRCLE, weight="pencil", filled=True)


def _render(payload: dict, **extra) -> str:
    return render(
        Score.model_validate({"instructions": [dict(payload, **extra)]}),
        render_seed=SEED,
        **{k: v for k, v in extra.items() if k == "svg_profile"},
    )


def _svg(payload: dict, *, svg_profile: str | None = None) -> str:
    return render(
        Score.model_validate({"instructions": [payload]}),
        render_seed=SEED,
        svg_profile=svg_profile,
    )


def _contour(payload: dict) -> list[tuple[float, float]]:
    """The polygon the renderer fills, built the way the renderer builds it."""
    r = payload["radius"] * CANVAS.unit
    return renderer._circle_points(
        500.0, 500.0, r, r, renderer._stroke_sample_count(2 * math.pi * r, CANVAS)
    )


def _centerlines(payload: dict, monkeypatch) -> list[list[tuple[float, float]]]:
    """Every centreline the renderer handed to the stroke synthesizer.

    The contour band goes through the same call, so the fill strokes are the
    ones taken while `_interior_fill` is on the stack -- identified by the
    `terminal` the fill branch asks for, which no other caller uses.
    """
    captured: list[list[tuple[float, float]]] = []

    def recording(centerline, *args, **kwargs):
        if kwargs.get("terminal") == "loaded":
            captured.append(list(centerline))
        return synthesize_along(centerline, *args, **kwargs)

    monkeypatch.setattr(renderer, "synthesize_along", recording)
    _svg(payload)
    # A copy: the patch is still in place for the rest of the test, so a caller
    # that renders again would silently see its own strokes appended to this.
    return list(captured)


def _raster_lines(payload: dict, monkeypatch) -> list[tuple[tuple, tuple, float]]:
    """The straight bands the machine's raster asked for, before quantisation.

    Same technique as `_centerlines`: wrap the renderer's own helper so the
    whole product path runs and only the observation point moves. It has to be
    read here rather than off the path string because the computer rounds its
    corners onto an 18px lattice, which tilts a band's measured direction by
    about a degree and makes "exactly one direction" unmeasurable.
    """
    captured: list[tuple[tuple, tuple, float]] = []
    original = renderer._raster_band

    def recording(start, end, width):
        captured.append((tuple(start), tuple(end), width))
        return original(start, end, width)

    monkeypatch.setattr(renderer, "_raster_band", recording)
    _svg(payload)
    return list(captured)


def _classes(svg: str) -> set[str]:
    """The class names in the document, so an assertion never carries the SVG.

    `assert "fill-stroke-v1" not in svg` is correct and unusable: when it fails,
    pytest's introspection formats a 400KB string and the run stops answering
    for minutes. A perturbation run makes every one of these fail on purpose,
    so "the gate is red" and "the gate has not come back" become the same
    thing to look at. Assertions here compare small sets.
    """
    return set(re.findall(r'class="([^"]+)"', svg))


def _has(svg: str, prefix: str) -> bool:
    return any(name.startswith(prefix) for name in _classes(svg))


def _stroke_angles_deg(centerlines) -> list[float]:
    angles = []
    for line in centerlines:
        dx = line[-1][0] - line[0][0]
        dy = line[-1][1] - line[0][1]
        angles.append(math.degrees(math.atan2(dy, dx)) % 180.0)
    return angles


def _reach_pixels(centerlines, contour) -> list[float]:
    """Signed reach of each end, **in pixels**.

    Positive is past the contour, negative is short of it. The stroke's own
    line is cut against the contour the renderer filled -- the polygon, not the
    ideal circle, or the 92-gon's 0.17px of inset would read as a reach.

    Pixels, not a fraction of the stroke: the reach belongs to the tool, so the
    quantity that has to hold is how far it strays relative to its OWN width,
    not relative to how big the shape happens to be.
    """
    out: list[float] = []
    for line in centerlines:
        ux = line[-1][0] - line[0][0]
        uy = line[-1][1] - line[0][1]
        norm = math.hypot(ux, uy)
        if norm <= 0:
            continue
        ux, uy = ux / norm, uy / norm
        mid = ((line[0][0] + line[-1][0]) / 2, (line[0][1] + line[-1][1]) / 2)
        spans = [s for s in _line_spans(contour, mid, (ux, uy)) if s[0] <= 0.0 <= s[1]]
        if not spans:
            continue
        t0, t1 = spans[0]
        span = t1 - t0
        if span <= 0:
            continue
        # Where the endpoints sit on the same parameter axis.
        s0 = (line[0][0] - mid[0]) * ux + (line[0][1] - mid[1]) * uy
        s1 = (line[-1][0] - mid[0]) * ux + (line[-1][1] - mid[1]) * uy
        out.append(t0 - s0)
        out.append(s1 - t1)
    return out


def test_the_line_cutter_agrees_with_shapes_whose_answer_is_known():
    """T-8 と T-10 は `_line_spans` に載っているので、まずそれを検算する。

    向きを逆に持った多角形でも同じ答えを出すこと、凹形で穴を跨がないこと。
    engine 22 の最初の実装は交点の媒介変数の符号が逆で、**凸形でも 2 交点が
    返るので絵は成立し**、はみ出しの分母だけが数 % ずれていた。
    """
    ccw = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for square in (ccw, list(reversed(ccw))):
        assert _line_spans(square, (0.5, 0.5), (1.0, 0.0)) == [(-0.5, 0.5)]
        assert _line_spans(square, (0.5, 0.5), (0.0, 1.0)) == [(-0.5, 0.5)]
    # 凹形 (C 字)。y=1.5 の内部は x in [0, 1] だけ。
    c_shape = [
        (0.0, 0.0), (3.0, 0.0), (3.0, 1.0), (1.0, 1.0),
        (1.0, 2.0), (3.0, 2.0), (3.0, 3.0), (0.0, 3.0),
    ]
    assert _line_spans(c_shape, (0.5, 1.5), (1.0, 0.0)) == [(-0.5, 0.5)]


# --- stage 1: the underlay -------------------------------------------------


def test_t1_both_branches_lay_an_underlay():
    """T-1 両枝に下地が出る。

    片側だけを見ると、下地を太い枝にだけ置いた実装が通る — それはこの契約が
    訂正した当の設計である。作者が縞と名指しした 3 組は pen (0.167)・
    crayon (0.333)・pencil (0.125) で、太い筆は 1 つも無い (run 857 §1)。
    """
    scan = _svg(SCAN_CASE)
    texture = _svg(TEXTURE_CASE)
    assert _fill_coverage(Instruction.model_validate(SCAN_CASE), CANVAS) >= FILL_COVERAGE_BRANCH
    assert _fill_coverage(Instruction.model_validate(TEXTURE_CASE), CANVAS) < FILL_COVERAGE_BRANCH
    assert _has(scan, "fill-underlay-v1")
    assert _has(texture, "fill-underlay-v1")


def test_t2_the_underlay_survives_the_non_display_profiles():
    """T-2 下地は display 以外でも残る。

    `use_filters = profile == "display"` なので、フィルタで作った下地は
    `compat` と `editable` で塗りそのものを消す (設計 §5-1)。
    """
    for profile in ("compat", "editable", "display"):
        for payload in (SCAN_CASE, TEXTURE_CASE):
            svg = _svg(payload, svg_profile=profile)
            assert _has(svg, "fill-underlay-v1"), (profile, payload["weight"])
            # A `polygon` without reserves, a `path` with holes in it when the
            # tool left the ground bare. Either way a real element, never a
            # filter.
            underlay = re.search(
                r'<(?:polygon|path)[^>]*class="fill-underlay-v1[^"]*"[^>]*>', svg
            )
            assert underlay is not None, (profile, payload["weight"])
            assert "filter" not in underlay.group(0), profile


def test_t3_a_rotring_fill_is_still_a_region_fill_and_byte_identical():
    """T-3 T-1 の対照。製図ペンの塗りは領域 fill のままで engine 21 と一致する。"""
    frozen = json.loads(ENGINE_21_MANIFEST.read_text())["cases"]
    generator_digest = _digest
    for case_id in ("C-tinyfill-circle-rotring", "D-canvas-wide-filled-square-rotring"):
        case = frozen[case_id]
        svg = _replay(case)
        classes = _classes(svg)
        assert not any(name.startswith("fill-") for name in classes), (case_id, classes)
        assert generator_digest(svg) == case["digest"], case_id


def _digest(svg: str) -> str:
    import hashlib

    normalized = re.sub(
        r"\d+\.\d+", lambda match: f"{round(float(match.group(0)), 6):.6f}", svg
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _replay(case: dict) -> str:
    render_input = case["input"]
    return render(
        Score.model_validate(render_input["score"]),
        color_map=render_input["color_map"],
        catalog_id=render_input["catalog_id"],
        render_seed=render_input["render_seed"],
        svg_profile=render_input["svg_profile"],
        wild=render_input["wild"],
    )


# --- stage 2: the branch ---------------------------------------------------


def test_t4_coverage_at_or_above_the_threshold_gets_scan_lines():
    """T-4 被覆率 0.2 以上は走査線。**クラスは `<g>` にあって `<path>` には無い。**"""
    classes = _classes(_svg(SCAN_CASE))
    assert any(re.fullmatch(r"fill-stroke-v1 strokes-\d+", n) for n in classes), classes
    assert not any(n.startswith("fill-texture-v1") for n in classes), classes


def test_t5_coverage_below_the_threshold_gets_the_texture_branch():
    """T-5 被覆率 0.2 未満は走査線をやめてテクスチャへ行く。"""
    classes = _classes(_svg(TEXTURE_CASE))
    assert not any(n.startswith("fill-stroke-v1") for n in classes), classes
    assert any(re.fullmatch(r"fill-texture-v1 marks-\d+", n) for n in classes), classes


def test_t6_the_same_tool_crosses_the_branch_on_thinness_alone():
    """T-6 **決定的なゲート。**同じ道具が細さ指定だけで枝を移る。

    これが無いと、被覆率を一度も読まず道具名を `if` で並べただけの実装が
    T-4 と T-5 を満点で通る。engine 21 のコーパスには `thinness` を持つ塗りの
    命令が 0 件で、被覆率で切る規則と道具名で切る規則がまったく同じに割るからである。
    `crayon` + `fine` は被覆 0.200 でちょうど閾値に乗るので使わない。
    """
    bare = dict(CIRCLE, weight="crayon", filled=True)
    thin = dict(bare, thinness="extra_fine")
    assert _fill_coverage(Instruction.model_validate(bare), CANVAS) == pytest.approx(
        0.333, abs=0.001
    )
    assert _fill_coverage(Instruction.model_validate(thin), CANVAS) == pytest.approx(
        0.117, abs=0.001
    )
    assert _has(_svg(bare), "fill-stroke-v1")
    assert _has(_svg(thin), "fill-texture-v1")

    # 対照: 細さ指定そのものが枝を決めているのではない。brush_thick は
    # extra_fine でも被覆 0.233 で走査線側に残る。
    thick_thin = dict(CIRCLE, weight="brush_thick", filled=True, thinness="extra_fine")
    assert _fill_coverage(
        Instruction.model_validate(thick_thin), CANVAS
    ) == pytest.approx(0.233, abs=0.001)
    assert _has(_svg(thick_thin), "fill-stroke-v1")


# --- stage 3: variation and the terminal -----------------------------------


def test_t7_the_scan_angle_varies_within_one_shape(monkeypatch):
    """T-7 走査角が 1 図形の中で振れる。**区間で断定する。**

    「0 より大きい」では 0.5 度の一定オフセットでも通る。engine 21 の実測は
    標準偏差 0.1 度で、目がパターンとして掴むのはここである (設計 §1)。
    """
    angles = _stroke_angles_deg(_centerlines(SCAN_CASE, monkeypatch))
    assert len(angles) >= 20
    sd = statistics.pstdev(angles)
    assert 2.0 <= sd <= 4.0, sd


def test_t8_the_endpoints_leave_the_contour_by_a_multiple_of_the_tools_width(monkeypatch):
    """T-8 端点が輪郭を離れる。**はみ出しと届かなさの両方**が、道具の幅に比例して。

    片側だけを見ると、内側へ寄せるだけの実装が通る。engine 21 は交点で切って
    いたので距離は厳密に 0 だった — それが第 3 の規則性である (設計 §3.2)。

    **単位は弦長の比ではなく道具の幅である**（作者裁定 2026-08-07）。弦長の比だと
    誤差が「図形の大きさ」に依ってしまい、同じ pen が大きい形では 17px、小さい形では
    2px 外す。「この道具はどれだけ狙ったところで止まれるか」は道具の性質なので、
    幅に比例させる。契約の 10〜15%（弦長）は現物を見て却下されている。
    """
    for payload in (SCAN_CASE, dict(CIRCLE, weight="brush_thick", filled=True)):
        ins = Instruction.model_validate(payload)
        width = _stroke_width_px(ins.weight, CANVAS, ins.thinness)
        reaches = _reach_pixels(_centerlines(payload, monkeypatch), _contour(payload))
        assert reaches, payload["weight"]
        assert any(r > 0 for r in reaches), f"{payload['weight']}: nothing overshoots"
        assert any(r < 0 for r in reaches), f"{payload['weight']}: nothing falls short"
        in_widths = [abs(r) / width for r in reaches]
        assert FILL_REACH_WIDTHS_MIN - 0.05 <= min(in_widths), (payload, min(in_widths))
        assert max(in_widths) <= FILL_REACH_WIDTHS_MIN + FILL_REACH_WIDTHS_SPAN + 0.05, (
            payload,
            max(in_widths),
        )


def test_t9_a_fill_stroke_ends_loaded_not_tapered():
    """T-9 塗りの筆の幅の包絡は `loaded`。**SVG のパス文字列ではなく合成器で測る。**

    着地側が中央より太く (約 1.45 倍)、細るのは離し際だけ。輪郭を引く筆の既定は
    `taper` のまま — 終端は道具の属性ではなく役割の属性である (設計 §4.5)。
    """
    line = [(100.0 + i * 8.0, 500.0) for i in range(61)]

    def ratios(**kwargs) -> tuple[float, float]:
        """着地 / 中央 と 離し際 / 中央 を seed 40 本の中央値で。

        1 本の幅は latent energy と地の抵抗 (g2) で 1 サンプルごとに大きく振れる
        ので、1 seed の 1 点で比を取ると 0.6〜2.5 に散る。**中央は帯の中央値、
        seed は 40 本の中央値**にして初めて包絡が読める。
        """
        landing, release = [], []
        for seed in range(1, 41):
            result = synthesize_along(
                line, 4.0, "crayon", seed * 7919, closed=False, **kwargs
            )
            middle = statistics.median(
                s.width for s in result.samples if 0.4 <= s.t <= 0.6
            )
            landing.append(result.samples[0].width / middle)
            release.append(
                statistics.median(
                    s.width for s in result.samples if s.t >= 0.95
                )
                / middle
            )
        return statistics.median(landing), statistics.median(release)

    loaded_landing, loaded_release = ratios(terminal="loaded")
    taper_landing, _ = ratios()
    assert loaded_landing == pytest.approx(1.45, abs=0.10), loaded_landing
    assert loaded_release < 1.0, loaded_release
    # 対照: 既定の終端は着地側を太らせない。これが無いと、`terminal` を無視する
    # 実装でも 1.45 倍が道具の側から出ていれば通ってしまう。
    assert taper_landing < 1.0, taper_landing


def test_t10_a_computer_fill_stays_regular(monkeypatch):
    """T-10 T-7・T-8・T-9 の対照。機械の塗りは規則的なまま。

    `periodic=True` は「寸分たがわぬ繰り返しは computer のもの」という署名で、
    手を人間らしくする改修がそれを潰してはならない (設計 §5-4)。

    engine 22 では機械の線は演奏されず直線の帯として置かれるので、測る先は
    `_raster_band` が受け取った 2 点である。
    """
    machine = dict(CIRCLE, weight="computer", filled=True)
    assert GRAMMARS["computer"].periodic
    assert GRAMMARS["computer"].fill_hand == 0.0
    bands = _raster_lines(machine, monkeypatch)
    assert len(bands) >= 2 * FILL_MIN_SCANLINES
    lines = [[start, end] for start, end, _width in bands]
    angles = _stroke_angles_deg(lines)
    assert statistics.pstdev(angles) == pytest.approx(0.0, abs=1e-9)
    reaches = _reach_pixels(lines, _contour(machine))
    assert reaches
    assert max(abs(r) for r in reaches) == pytest.approx(0.0, abs=1e-9)


def test_t11_the_scan_branch_reaches_the_coverage_the_author_set(monkeypatch):
    """T-11 走査線枝は被覆 0.9 に届く。**対照: テクスチャ枝は引き直さない。**"""
    ins = Instruction.model_validate(SCAN_CASE)
    width = _stroke_width_px(ins.weight, CANVAS, ins.thinness)
    lines = _centerlines(SCAN_CASE, monkeypatch)
    # The pitch the branch packed to, read back from the strokes it produced.
    normal = _scan_normal(lines)
    offsets = sorted(
        {round(p[0][0] * normal[0] + p[0][1] * normal[1], 4) for p in lines}
    )
    gaps = [b - a for a, b in zip(offsets, offsets[1:]) if b - a > 1e-6]
    pitch = statistics.mean(gaps)
    assert width / pitch == pytest.approx(FILL_COVERAGE_TARGET, rel=0.2)

    texture = Instruction.model_validate(TEXTURE_CASE)
    texture_width = _stroke_width_px(texture.weight, CANVAS, texture.thinness)
    texture_pitch = _fill_scan_spacing(texture, CANVAS)
    assert texture_width / texture_pitch < FILL_COVERAGE_BRANCH


def _scan_normal(lines) -> tuple[float, float]:
    dx = lines[0][-1][0] - lines[0][0][0]
    dy = lines[0][-1][1] - lines[0][0][1]
    norm = math.hypot(dx, dy)
    return (-dy / norm, dx / norm)


# --- the rulings taken while the contract was running (2026-08-07) ----------
# The contract did not carry gates for these; they were decided off the drawn
# picture, so the gates are written here with the same rule as the rest -- a
# production-side revert has to redden each one.


TEXTURE_TOOLS = ("silverpoint", "pen", "pencil")  # 手の緩さの昇順 (0.05 / 0.25 / 0.60)


def test_t14_the_texture_branch_runs_one_direction_with_a_few_degrees_of_wobble(
    monkeypatch,
):
    """T-14 テクスチャ枝の向きは、走査線枝と同じ数度の帯である。

    「テクスチャについては、線の長さ、向きについては engine21 に戻すが、向きの
    角度に数度レベルの揺らぎを与える」（作者裁定 2026-08-07）。**前巡の ±45° の
    散りはこの裁定で取り消された。**engine 21 の向きは領域に 1 つだったので、
    残るのは走査線枝と同じ手の帯である。

    **上下の両方で挟む。**上限だけなら向きを定数にした実装が通り、下限だけなら
    ±45° の散りが通る。**さらに手の緩さへ順序で結びつける** — 帯を道具に依らない
    定数へ落とした実装は、3 道具が同じ標準偏差を返して落ちる。

    T-7 と同じ観測点（合成器へ渡った中心線）で測る。SVG のパス文字列から読むと
    筆致自身の横揺れが乗り、数度の量には効いてしまう。
    """
    sds = []
    for tool in TEXTURE_TOOLS:
        payload = dict(CIRCLE, weight=tool, filled=True)
        assert _has(_svg(payload), "fill-texture-v1"), tool
        angles = _stroke_angles_deg(_centerlines(payload, monkeypatch))
        assert len(angles) >= 20, tool
        sd = statistics.pstdev(angles)
        # 契約 §3 の帯。走査線枝の T-7 と同じ数字で、同じ量だからである。
        assert 2.0 <= sd <= 4.0, (tool, sd)
        # ±45° の散りは全開き 90° を返していた。数度の帯はその 1/4 にも届かない。
        assert max(angles) - min(angles) <= 20.0, (tool, max(angles) - min(angles))
        sds.append(sd)
    assert sds[0] < sds[1] < sds[2], dict(zip(TEXTURE_TOOLS, sds))


def test_t17_the_texture_branch_lays_the_ink_one_classic_scan_pass_laid(monkeypatch):
    """T-17 テクスチャ枝の本数は、従来の走査線 1 パスと同量である。

    「倍にする」（作者裁定 2026-08-07）。痕が形の幅を渡るようになった時点で、
    半分の本数では面が痩せて見えていた。倍にした先がちょうど「engine 21 の
    走査線 1 パスが置いた墨」で、この枝が何に錨を下ろしているかもそこである。

    **期待値を `FILL_TEXTURE_DENSITY` から作らない。**定数を読む受入は、その定数を
    戻す摂動で緑のままになる。面積・間隔・平均弦長という製品の量だけから
    「1 パスぶん」を建てて、出てきた痕の本数と突き合わせる。
    """
    for tool in TEXTURE_TOOLS:
        payload = dict(CIRCLE, weight=tool, filled=True)
        contour = _contour(payload)
        ins = Instruction.model_validate(payload)
        pitch = _fill_scan_spacing(ins, CANVAS)
        xs = [point[0] for point in contour]
        ys = [point[1] for point in contour]
        short_side = min(max(xs) - min(xs), max(ys) - min(ys))
        area = renderer._polygon_area(contour)
        one_pass = area / (pitch * max(pitch, area / short_side))
        marks = int(
            re.search(r'class="fill-texture-v1 marks-(\d+)"', _svg(payload)).group(1)
        )
        assert 0.8 * one_pass <= marks <= 1.2 * one_pass, (tool, marks, one_pass)
        # **描いたものからも数える。**上の数は renderer が「何本置くと決めたか」で、
        # これは実際に合成器へ渡った本数である。塗り残しで割れた痕があるので
        # 断片の方が多いが、痕より少なくなることはない（割れたことそのものは
        # T-21 が見る。ここは「決めた本数のものが実際に描かれた」だけ）。
        drawn = len(_centerlines(payload, monkeypatch))
        assert marks <= drawn <= 2.5 * marks, (tool, drawn, marks)


def test_t18_a_texture_mark_ends_the_way_a_scan_stroke_does(monkeypatch):
    """T-18 テクスチャ枝の痕も、輪郭で切られ、道具の幅ぶんだけ両符号で外す。

    「線の長さは engine21 に戻す」（作者裁定 2026-08-07）の長さ側。痕は形が
    与える弦を渡り、端は走査線枝と同じ作法で処理される — **T-8 の断定を、
    もう一方の枝に対してそのまま置く**。

    片側だけ出す実装は、輪郭の片側を engine 21 の交点切りと同じ整い方で残す。
    枝が違うだけで同じ欠陥なので、同じ形で挟む。

    **塗り残しで切られた端は対象外である。**これは「痕が形の縁でどう終わるか」の
    受入で、抜きの縁で終わった端はそもそも縁に居ない。落とした端が半分を超えたら
    落とし方の側を疑うので、残った割合も見る。
    """
    for tool in TEXTURE_TOOLS:
        payload = dict(CIRCLE, weight=tool, filled=True)
        ins = Instruction.model_validate(payload)
        width = _stroke_width_px(ins.weight, CANVAS, ins.thinness)
        every = _reach_pixels(_centerlines(payload, monkeypatch), _contour(payload))
        reaches = [r for r in every if abs(r) <= 4 * width]
        assert len(reaches) >= 20, (tool, len(reaches))
        assert len(reaches) >= 0.5 * len(every), (tool, len(reaches), len(every))
        assert any(r > 0 for r in reaches), f"{tool}: nothing overshoots"
        assert any(r < 0 for r in reaches), f"{tool}: nothing falls short"
        in_widths = [abs(r) / width for r in reaches]
        assert FILL_REACH_WIDTHS_MIN - 0.05 <= min(in_widths), (tool, min(in_widths))
        assert max(in_widths) <= FILL_REACH_WIDTHS_MIN + FILL_REACH_WIDTHS_SPAN + 0.05, (
            tool,
            max(in_widths),
        )


def test_t19_chalk_stands_further_out_of_its_field_than_crayon_does():
    """T-19 chalk の痕は、crayon より下地から離れて見える。

    「chalk については、crayon よりコントラストを付ける」（作者裁定 2026-08-07）。
    2 つは被覆率 0.250 と 0.333 で枝の同じ側に居り、幅以外はほとんど同じに読める。

    **道具について回ることを枝をまたいで見る。**renderer 側で道具名を並べた実装は
    細い chalk がテクスチャ枝へ移った瞬間に効かなくなる — 被覆率だけが枝を決める
    という engine 22 の唯一の閾値（T-6）を、この裁定が黙って壊さないこと。
    """
    ratios = {}
    for tool, thinness in (
        ("crayon", None),
        ("chalk", None),
        ("chalk", "extra_fine"),
    ):
        payload = dict(CIRCLE, weight=tool, filled=True)
        if thinness:
            payload["thinness"] = thinness
        svg = _svg(payload)
        under = _underlay_opacity(svg)
        klass = "fill-texture-v1" if _has(svg, "fill-texture-v1") else "fill-stroke-v1"
        # テクスチャ枝は 1 本ごとに濃さが違うので平均で見る（走査線枝は 1 値）。
        ratios[(tool, thinness)] = statistics.fmean(_mark_opacities(svg, klass)) / under

    # 走査線枝の同士討ち。crayon は枝の値のまま、chalk はその上。
    assert ratios[("crayon", None)] == pytest.approx(FILL_SCAN_CONTRAST, abs=0.02)
    assert ratios[("chalk", None)] > ratios[("crayon", None)] + 0.10, ratios

    # 枝をまたいでも道具について回る。細い chalk はテクスチャ枝に居る。
    assert _has(_svg(dict(CIRCLE, weight="chalk", filled=True, thinness="extra_fine")), "fill-texture-v1")
    assert ratios[("chalk", "extra_fine")] > FILL_TEXTURE_CONTRAST + 0.10, ratios


def test_t15_a_texture_mark_sits_close_to_the_field_it_rises_from():
    """T-15 テクスチャ枝の痕は、下地とのコントラストが近い。

    「線と背景のコントラストを近づける。あくまで塗りつぶしの中から、一部筆致が
    浮いて見えるという程度」（作者裁定 2026-08-07）。**下地の濃度に対する比で持つ**
    ので、記述が淡さを求めた作品でも関係は変わらない。

    対照: 走査線枝の筆は下地に寄せない。**枝を問わず寄せる実装では、面を作る
    筆致まで見えなくなる。**
    """
    texture = _svg(TEXTURE_CASE)
    under = _underlay_opacity(texture)
    marks = _mark_opacities(texture, "fill-texture-v1")
    # 痕は 1 本ごとに濃さが違う（T-20）。**平均で見る** — 個々の値で断定すると、
    # 濃淡を足した時点でこのゲートが「動かしていない量」まで赤くする。
    mean = statistics.fmean(marks)
    assert mean / under == pytest.approx(FILL_TEXTURE_CONTRAST, abs=0.05), (mean, under)

    # 対照: 走査線枝も下地に寄せるが、**寄せ方が違う**。両枝が同じ定数を読む
    # 実装は、片方の裁定を動かしたときにもう片方も黙って動く。
    scan = _svg(SCAN_CASE)
    scan_under = _underlay_opacity(scan)
    scan_marks = set(_mark_opacities(scan, "fill-stroke-v1"))
    assert len(scan_marks) == 1
    scan_ratio = scan_marks.pop() / scan_under
    assert scan_ratio == pytest.approx(FILL_SCAN_CONTRAST, abs=0.02)
    assert mean / under < scan_ratio, (mean / under, scan_ratio)


def test_t20_every_texture_mark_takes_its_own_tone():
    """T-20 テクスチャ枝の痕は 1 本ごとに濃さが違う。**平均は動かない。**

    「塗りつぶしの色むらを、テクスチャで使われる細い道具でも表現したい」
    （作者裁定 2026-08-07）。engine 22 の 5 巡目まで、この枝の痕は全部同じ濃さの
    1 値だった。

    **平均を据えるのが要点である。**幅だけを足して平均を動かさない、という裁定
    なので、上下に振っただけの実装と「全部濃くした」実装を分けるにはここを見る。
    帯の下限が 1.0 なのは、下地より淡い痕も合成では下地を濃くするからで、
    淡い側へ広げても明るい斑は 1 つも生まれない（明るさは塗り残しが作る）。
    """
    for tool in TEXTURE_TOOLS:
        payload = dict(CIRCLE, weight=tool, filled=True)
        svg = _svg(payload)
        under = _underlay_opacity(svg)
        marks = _mark_opacities(svg, "fill-texture-v1")
        assert len(marks) >= 20, tool
        distinct = sorted(set(marks))
        assert len(distinct) >= 10, (tool, len(distinct))
        # 幅がある。1 値の実装との差はここで、2 つの値がたまたま違うだけの
        # 実装は通らない（四分位で見る）。
        low = statistics.quantiles(marks, n=4)[0]
        high = statistics.quantiles(marks, n=4)[2]
        assert (high - low) / statistics.fmean(marks) >= 0.05, (tool, low, high)
        # どの痕も下地より薄くはならず、記述が求めた墨より濃くもならない。
        assert min(marks) >= under * 0.98, (tool, min(marks), under)
        ink = under / renderer.FILL_UNDERLAY_OPACITY_RATIO
        assert max(marks) <= ink + 1e-9, (tool, max(marks), ink)


def test_t21_the_tool_leaves_the_ground_bare_along_its_own_strokes(monkeypatch):
    """T-21 塗り残し。**地が出る場所には下地も痕も無く、その形は筆致に沿う。**

    「逆に塗り残しで地が出る表現を追加する」（作者裁定 2026-08-07）、そして
    **「塗り残しは筆致の軌跡に応じるべきだ。線の軌跡に被っており、ロジックとして
    おかしい」**（同 2026-08-07、等方の塊で出したものへの差し戻し）。道具は自分の
    ストロークを横切って消したりしない。

    **3 つを同時に見る。**下地に穴が開いていても痕が素通りしていれば地は出ず、
    痕だけ避けても下地が残っていれば出ず、**向きが筆致と無関係なら「破れ」に戻る。**
    片方だけのゲートは、もう片方が抜けた実装を通す。

    対照: 走査線枝には塗り残しを置かない。
    """
    for tool in TEXTURE_TOOLS:
        payload = dict(CIRCLE, weight=tool, filled=True)
        svg = _svg(payload)
        count = re.search(r'class="fill-underlay-v1 reserves-(\d+)"', svg)
        assert count is not None, tool
        assert 3 <= int(count.group(1)) <= 7, (tool, count.group(1))
        underlay = re.search(
            r'<path[^>]*class="fill-underlay-v1 reserves-[^"]*"[^>]*>', svg
        ).group(0)
        assert 'fill-rule="evenodd"' in underlay, tool
        d = re.search(r'\sd="([^"]+)"', underlay).group(1)
        assert d.count("M ") == int(count.group(1)) + 1, (tool, d.count("M "))

        contour = _contour(payload)
        reserves, _ = renderer._texture_field(
            Instruction.model_validate(payload), contour, CANVAS, SEED
        )
        assert len(reserves) == int(count.group(1)), tool
        lines = _centerlines(payload, monkeypatch)

        # 1. 向き。抜きの長軸が痕の走る向きと揃っていること。
        marks_angle = statistics.fmean(_stroke_angles_deg(lines))
        for reserve in reserves:
            axis, elongation = _principal_axis(reserve)
            # 細長いこと。等方の塊へ戻した実装は、長軸の向き自体が意味を持たない。
            assert elongation >= 2.0, (tool, elongation)
            gap = abs(axis - marks_angle) % 180.0
            assert min(gap, 180.0 - gap) <= 10.0, (tool, axis, marks_angle)

        # 2. 痕が入っていないこと。**深さで見る。件数比では分からない** — 抜きは
        # 形の数 % しか占めないので、素通りする実装でも「抜きの中の標本」は同じ
        # 数 % にしかならず、ずれ幅ぶんと見分けがつかない。深さなら、切っていれば
        # 道具の幅の数倍まで、切っていなければ抜きの半幅ぶん入る。
        width = _stroke_width_px(
            Instruction.model_validate(payload).weight, CANVAS, None
        )
        deepest = 0.0
        for line in lines:
            for point in line:
                for reserve in reserves:
                    if _point_in_polygon(point, reserve):
                        deepest = max(deepest, _depth_in_polygon(point, reserve))
        assert deepest <= 2.0 * width, (tool, deepest, width)

        # 3. 実際に切られたこと。抜きが形の外に落ちていれば上の 2 つは恒真になる。
        marks = int(re.search(r'class="fill-texture-v1 marks-(\d+)"', svg).group(1))
        assert len(lines) > marks, (tool, len(lines), marks)


def test_t23_the_field_itself_carries_more_than_one_tone(monkeypatch):
    """T-23 下地は 1 枚の平らな面ではない。**それでいて面の濃度は動かない。**

    「塗りつぶしの色むらを、テクスチャで使われる細い道具でも表現したい」に対して
    痕の濃さを振ったが、**4 倍に広げても絵は変わらなかった**（run 859 6 巡目）。
    面の明るさを決めているのは一様な下地なので、むらは下地の側にしか作れない。

    **合成が元の平らな値と一致することを見る。**むらを足したついでに面が濃く
    （淡く）なる実装は、作者が承認済みのコントラストを黙って動かしている。
    """
    for tool in TEXTURE_TOOLS:
        payload = dict(CIRCLE, weight=tool, filled=True)
        svg = _svg(payload)
        layers = _underlay_layers(svg)
        assert len(layers) >= 2, (tool, layers)
        # 一番下の層は、元の平らな面より淡い。ここが「薄いところ」である。
        composite = _underlay_opacity(svg)
        assert layers[0] < composite, (tool, layers[0], composite)
        # 濃淡の層は穴を持っている。穴が無ければ層が何枚あっても一様である。
        tone_layers = re.findall(r'class="fill-underlay-v1 tones-(\d+)"', svg)
        assert len(tone_layers) >= 1, tool
        assert all(int(value) >= 3 for value in tone_layers), (tool, tone_layers)

    # そして重なった先が、むらを持たない面ちょうどであること。**同じ製品を
    # 層 0 枚で 1 度描いて突き合わせる** — 記述が求めた墨を受入の側で建て直すと、
    # 建て直しの側が間違っていても気づけない。
    with monkeypatch.context() as patched:
        patched.setattr(renderer, "FILL_FIELD_TONE_LAYERS", 0)
        flat = {tool: _underlay_opacity(_svg(dict(CIRCLE, weight=tool, filled=True)))
                for tool in TEXTURE_TOOLS}
    for tool in TEXTURE_TOOLS:
        mottled = _underlay_opacity(_svg(dict(CIRCLE, weight=tool, filled=True)))
        assert mottled == pytest.approx(flat[tool], abs=1e-6), (tool, mottled, flat[tool])

    # 対照: 走査線枝は 1 枚の平らな polygon のまま。
    scan = _svg(SCAN_CASE)
    assert len(_underlay_layers(scan)) == 1
    assert "tones-" not in scan


def _principal_axis(polygon) -> tuple[float, float]:
    """多角形の長軸の向き（度・0〜180）と、長短の比。"""
    cx = statistics.fmean(point[0] for point in polygon)
    cy = statistics.fmean(point[1] for point in polygon)
    sxx = syy = sxy = 0.0
    for x, y in polygon:
        dx, dy = x - cx, y - cy
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    n = len(polygon)
    sxx, syy, sxy = sxx / n, syy / n, sxy / n
    angle = 0.5 * math.atan2(2 * sxy, sxx - syy)
    trace = sxx + syy
    root = math.sqrt(max(0.0, (sxx - syy) ** 2 + 4 * sxy * sxy))
    major, minor = (trace + root) / 2, (trace - root) / 2
    ratio = math.sqrt(major / minor) if minor > 1e-9 else float("inf")
    return math.degrees(angle) % 180.0, ratio

    # 対照。
    assert "reserves-" not in _svg(SCAN_CASE)


def _depth_in_polygon(point: tuple[float, float], polygon) -> float:
    """How far inside the polygon the point sits: its distance to the nearest edge."""
    x, y = point
    best = float("inf")
    for index in range(len(polygon)):
        ax, ay = polygon[index]
        bx, by = polygon[(index + 1) % len(polygon)]
        ex, ey = bx - ax, by - ay
        length2 = ex * ex + ey * ey
        t = 0.0 if length2 == 0 else ((x - ax) * ex + (y - ay) * ey) / length2
        t = max(0.0, min(1.0, t))
        best = min(best, math.hypot(x - (ax + ex * t), y - (ay + ey * t)))
    return best


def _point_in_polygon(point: tuple[float, float], polygon) -> bool:
    x, y = point
    inside = False
    for index in range(len(polygon)):
        ax, ay = polygon[index]
        bx, by = polygon[(index + 1) % len(polygon)]
        if (ay > y) != (by > y):
            crossing = ax + (y - ay) / (by - ay) * (bx - ax)
            if x < crossing:
                inside = not inside
    return inside


def test_t22_chalk_shows_more_bare_paper_than_the_other_waxy_tools():
    """T-22 chalk の掠れは crayon・pencil より多い。

    「chalk については線の側の掠れの量を増加」（作者裁定 2026-08-07）。3 つとも
    紙が拒む量 1.00 で、同じ 4.8% の紙しか出していなかった。

    **道具の側で測る。**掠れは合成器の機構なので、そこへ直接 widths を渡して
    切れた標本を数える。片方の道具だけでは「全部増えた」実装が通るので、
    動かしていない 2 つが動いていないことも見る。
    """
    from inku_server.stroke_engine import DEFAULT_SUPPORT, _support_response

    bare = {}
    for tool in ("chalk", "crayon", "pencil", "pen"):
        cuts = 0
        total = 0
        for seed in range(40):
            _, marks = _support_response([2.0] * 220, tool, seed, DEFAULT_SUPPORT)
            cuts += sum(marks)
            total += len(marks)
        bare[tool] = cuts / total

    assert bare["chalk"] >= bare["crayon"] * 1.5, bare
    assert bare["chalk"] >= bare["pencil"] * 1.5, bare
    # 動かしていない側。crayon と pencil は同じ紙のままで、pen は元から出さない。
    assert bare["crayon"] == pytest.approx(bare["pencil"], abs=1e-9), bare
    assert bare["pen"] == 0.0, bare


def _underlay_layers(svg: str) -> list[float]:
    """下地の各層の濃度。**要素は `polygon` とは限らず、1 枚とも限らない** —
    塗り残しがあれば穴を持つ `path` になり、色むらがあれば複数枚になる。
    要素名や 1 枚を前提に引くゲートは、そこで黙って見失う。"""
    layers = [
        float(value)
        for value in re.findall(
            r'class="fill-underlay-v1[^"]*"[^>]*fill-opacity="([\d.]+)"', svg
        )
    ]
    assert layers
    return layers


def _underlay_opacity(svg: str) -> float:
    """痕が乗る面の濃度。層が複数あるところでは、その合成である。"""
    rest = 1.0
    for layer in _underlay_layers(svg):
        rest *= 1.0 - layer
    return 1.0 - rest


def _mark_opacities(svg: str, klass: str) -> list[float]:
    group = re.search(rf'<g class="{klass}[^"]*">(.*?)</g>', svg, flags=re.S)
    assert group is not None, klass
    return [float(v) for v in re.findall(r'fill-opacity="([\d.]+)"', group.group(1))]


def test_t16_the_machines_fill_is_a_straight_raster_line(monkeypatch):
    """T-16 機械の塗りは走査線である。**直線・1 領域 1 方向・間隔を残す・芯と滲み。**

    「ブラウン管の走査線のような表現。線のセンターの輝度が高く周囲が滲む。
    走査線の間には薄く影が見える」（作者裁定 2026-08-07）。続けて
    「線の途中のゆがみが余分。直線に見えるレベルを維持。主潰し方向は水平・垂直に
    限らず自由な角度を許容。ただし単体の領域の塗りつぶしの中では向きが揃っている
    必要がある」。**間隔を被覆 0.9 まで詰めると線の間が閉じ、線として読めなくなる。**
    """
    machine = dict(CIRCLE, weight="computer", filled=True)
    bands = _raster_lines(machine, monkeypatch)
    assert bands

    # 1 領域 1 方向。水平とは限らないが、揃っていること。
    angles = _stroke_angles_deg([[start, end] for start, end, _ in bands])
    assert len(set(round(a, 9) for a in angles)) == 1, sorted(set(angles))[:4]

    # 間隔が残る。被覆率が閾値を下回っていれば、線の間に下地が見える。
    ins = Instruction.model_validate(machine)
    width = _stroke_width_px(ins.weight, CANVAS, ins.thinness)
    pitch = _fill_scan_spacing(ins, CANVAS)
    assert width / pitch < FILL_COVERAGE_BRANCH, width / pitch

    # 直線。演奏された帯は中心線が振れるので輪郭の点が多数になる。
    svg = _svg(machine)
    group = re.search(r'<g class="fill-stroke-v1[^"]*">(.*?)</g>', svg, flags=re.S).group(1)
    shapes = re.findall(r'd="([^"]+)"', group)
    assert shapes
    for path_d in shapes:
        assert path_d.count(" L ") == 3, path_d[:80]

    # 幅が一定であること。**出てきた帯から測る** — `_raster_band` に渡した引数を
    # 見ても、量子化は関数の中で起きるので何も測れない。engine 22 の最初の帯は
    # 4 隅を 18px の格子へ丸めていて、1 本ごとに幅が揺れ、端が輪郭に対して
    # 階段状になっていた。滲みと芯の 2 値だけが出ること。
    realized = sorted(_band_width(path_d) for path_d in shapes)
    split = max(range(1, len(realized)), key=lambda i: realized[i] - realized[i - 1])
    core_widths, halo_widths = realized[:split], realized[split:]
    # Two groups, each flat to within the 2-decimal rounding the path carries.
    # Under quantisation the spread inside a group was several pixels.
    assert max(core_widths) - min(core_widths) <= 0.05, (min(core_widths), max(core_widths))
    assert max(halo_widths) - min(halo_widths) <= 0.05, (min(halo_widths), max(halo_widths))

    # 1 本が 2 枚。広くて薄い滲みの上に、狭くて濃い芯。
    opacities = [float(value) for value in re.findall(r'fill-opacity="([\d.]+)"', group)]
    assert len(opacities) == len(bands), (len(opacities), len(bands))
    assert len(opacities) % 2 == 0 and len(opacities) >= 2 * FILL_MIN_SCANLINES
    halo, core = opacities[0], opacities[1]
    # 濃さの振れは 0.1 まで。比で持つと 2 枚が 0.56 離れ、線は「淡い帯の中の
    # 細い濃い罫線」に見えた (作者裁定 2026-08-07)。
    assert core - halo == pytest.approx(FILL_RASTER_HALO_STEP, abs=0.005), (halo, core)
    assert opacities[0::2] == [halo] * (len(opacities) // 2)
    assert opacities[1::2] == [core] * (len(opacities) // 2)
    # 対照: 濃さだけでなく幅も違うこと。同じ幅を 2 度置いても濃くなるだけで、
    # 縁は柔らかくならない。
    assert min(halo_widths) > max(core_widths) * 2, (max(core_widths), min(halo_widths))


def _band_width(path_d: str) -> float:
    """The width of a straight raster band, taken across one end."""
    points = [
        (float(x), float(y))
        for x, y in re.findall(r"(-?\d+\.\d+) (-?\d+\.\d+)", path_d)
    ]
    assert len(points) == 4, len(points)
    return math.hypot(points[0][0] - points[3][0], points[0][1] - points[3][1])


# --- stage 4: the corpus ---------------------------------------------------

NEW_CASES = {
    "C-fill-circle-computer": "fill-stroke-v1",
    "C-fill-circle-silverpoint": "fill-texture-v1",
    "C-fill-circle-crayon-extra_fine": "fill-texture-v1",
    "C-fill-circle-brush_thick-extra_fine": "fill-stroke-v1",
    # 走行中の裁定（chalk のコントラスト）ぶん。コーパスは塗った chalk を
    # 1 件も持っていなかったので、裁定の全部がどこにも記録されずに済んでいた。
    "C-fill-circle-chalk": "fill-stroke-v1",
    "C-fill-circle-chalk-extra_fine": "fill-texture-v1",
}


def test_t12_the_new_cases_exist_and_traverse_the_layer_they_were_added_for():
    """T-12 足した 6 case が、足した目的の層を実際に通る。

    **足されたがレンダラに素通りされる case は、検査ではなく記録である。**
    """
    manifest = json.loads(ENGINE_22_MANIFEST.read_text())
    cases = manifest["cases"]
    before = json.loads(ENGINE_21_MANIFEST.read_text())["cases"]
    for case_id, expected_class in NEW_CASES.items():
        assert case_id in cases, case_id
        assert case_id not in before, case_id
        # **描き直して見る。**manifest の `classes` は生成器が焼き直す記録なので、
        # そこだけを読むゲートは製品を壊しても赤くならない。case が「足された」
        # ことは manifest が、「その層を通る」ことは製品が答える。
        svg = _replay(cases[case_id])
        assert _has(svg, expected_class), (case_id, expected_class, _classes(svg))
        assert _has(svg, "fill-underlay-v1"), case_id


def test_t13_the_frozen_corpus_moved_exactly_the_cases_the_contract_predicted():
    """T-13 コーパスの差分が予測と一致する。

    契約の予測は塗りの既存 32 件（走査線・被覆 0.2 以上 21 ＋ 0.2 未満 11）だった。
    **打点 3 件には下地を置かない**と決めたので 35 ではない。

    そこへ走行中の裁定が 2 つ乗って 46 件になっている:

    - **新規 6 件**（契約は 4 件）。塗った chalk がコーパスに 1 件も無く、
      「chalk は crayon よりコントラストを付ける」がどこにも記録されなかった
    - **既存 +14 件はすべて chalk**。「chalk は線の側の掠れを増やす」は紙が
      道具を拒む量を動かすので、**塗っていない chalk の輪郭まで動く**。
      塗りの裁定ではないものが塗りのコーパスを動かした、という記録である

    `changed_from_previous` は 46 + 6 = 52。生成器は新規 case も changed に数える。

    決定性そのものは `check_frozen_corpora.py` が見る（CI が走らせるものと同一）。
    """
    manifest = json.loads(ENGINE_22_MANIFEST.read_text())
    before = json.loads(ENGINE_21_MANIFEST.read_text())["cases"]
    changed = manifest["changed_from_previous"]
    moved = sorted(case_id for case_id in changed if case_id in before)
    added = sorted(case_id for case_id in changed if case_id not in before)
    assert len(moved) == 46, moved
    assert len(added) == 6, added
    assert len(changed) == 52
    assert len([case_id for case_id in moved if "chalk" in case_id]) == 14, moved
    assert len(manifest["cases"]) == 531
    assert manifest["engine_version"] == "22"

    # 動いたものが「塗りの走査線を通る case」であること。打点と rotring は不動。
    for case_id in ("C-tinyfill-circle-pen", "C-tinyfill-square-brush_thick",
                    "D-size-tiny-filled-circle", "C-tinyfill-circle-rotring"):
        assert case_id not in changed, case_id
