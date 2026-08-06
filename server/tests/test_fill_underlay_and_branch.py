"""render engine 22: a fill gets an underlay, and what sits on it gets a branch.

Thirteen gates over the four stages of the contract
`no-git-sync/fable5/claude_code/tasks/fill-underlay-and-branch.md`:

    T-1 .. T-3   stage 1, the underlay
    T-4 .. T-6   stage 2, the branch
    T-7 .. T-11  stage 3, the variation and the terminal
    T-12 .. T-13 stage 4, the corpus

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
    FILL_REACH_MIN,
    FILL_REACH_SPAN,
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
    return captured


def _stroke_angles_deg(centerlines) -> list[float]:
    angles = []
    for line in centerlines:
        dx = line[-1][0] - line[0][0]
        dy = line[-1][1] - line[0][1]
        angles.append(math.degrees(math.atan2(dy, dx)) % 180.0)
    return angles


def _reach_fractions(centerlines, contour) -> list[float]:
    """Signed reach of each end, as a fraction of the span across the shape.

    Positive is past the contour, negative is short of it. The stroke's own
    line is cut against the contour the renderer filled -- the polygon, not the
    ideal circle, or the 92-gon's 0.17px of inset would read as a reach -- and
    the span between those two crossings is the denominator, which is what
    "10-15% of the stroke length" means.
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
        out.append((t0 - s0) / span)
        out.append((s1 - t1) / span)
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
    assert 'class="fill-underlay-v1"' in scan
    assert 'class="fill-underlay-v1"' in texture


def test_t2_the_underlay_survives_the_non_display_profiles():
    """T-2 下地は display 以外でも残る。

    `use_filters = profile == "display"` なので、フィルタで作った下地は
    `compat` と `editable` で塗りそのものを消す (設計 §5-1)。
    """
    for profile in ("compat", "editable", "display"):
        for payload in (SCAN_CASE, TEXTURE_CASE):
            svg = _svg(payload, svg_profile=profile)
            assert 'class="fill-underlay-v1"' in svg, (profile, payload["weight"])
            underlay = re.search(r'<polygon class="fill-underlay-v1"[^>]*>', svg)
            assert underlay is not None
            assert "filter" not in underlay.group(0), profile


def test_t3_a_rotring_fill_is_still_a_region_fill_and_byte_identical():
    """T-3 T-1 の対照。製図ペンの塗りは領域 fill のままで engine 21 と一致する。"""
    frozen = json.loads(ENGINE_21_MANIFEST.read_text())["cases"]
    generator_digest = _digest
    for case_id in ("C-tinyfill-circle-rotring", "D-canvas-wide-filled-square-rotring"):
        case = frozen[case_id]
        svg = _replay(case)
        assert "fill-underlay-v1" not in svg, case_id
        assert "fill-stroke-v1" not in svg, case_id
        assert "fill-texture-v1" not in svg, case_id
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
    svg = _svg(SCAN_CASE)
    assert re.search(r'<g class="fill-stroke-v1 strokes-\d+">', svg)
    assert "fill-texture-v1" not in svg


def test_t5_coverage_below_the_threshold_gets_the_texture_branch():
    """T-5 被覆率 0.2 未満は走査線をやめてテクスチャへ行く。"""
    svg = _svg(TEXTURE_CASE)
    assert "fill-stroke-v1" not in svg
    assert re.search(r'<g class="fill-texture-v1 marks-\d+">', svg)


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
    assert "fill-stroke-v1" in _svg(bare)
    assert "fill-texture-v1" in _svg(thin)

    # 対照: 細さ指定そのものが枝を決めているのではない。brush_thick は
    # extra_fine でも被覆 0.233 で走査線側に残る。
    thick_thin = dict(CIRCLE, weight="brush_thick", filled=True, thinness="extra_fine")
    assert _fill_coverage(
        Instruction.model_validate(thick_thin), CANVAS
    ) == pytest.approx(0.233, abs=0.001)
    assert "fill-stroke-v1" in _svg(thick_thin)


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


def test_t8_the_endpoints_leave_the_contour_in_both_directions(monkeypatch):
    """T-8 端点が輪郭を離れる。**はみ出しと届かなさの両方**が出る。

    片側だけを見ると、内側へ寄せるだけの実装が通る。engine 21 は交点で切って
    いたので距離は厳密に 0 だった — それが第 3 の規則性である (設計 §3.2)。
    """
    fractions = _reach_fractions(_centerlines(SCAN_CASE, monkeypatch), _contour(SCAN_CASE))
    assert fractions
    assert any(f > 0 for f in fractions), "no endpoint overshoots the contour"
    assert any(f < 0 for f in fractions), "no endpoint falls short of the contour"
    worst = max(abs(f) for f in fractions)
    least = min(abs(f) for f in fractions)
    assert FILL_REACH_MIN - 0.01 <= least, least
    assert worst <= FILL_REACH_MIN + FILL_REACH_SPAN + 0.01, worst


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
    """
    machine = dict(CIRCLE, weight="computer", filled=True)
    assert GRAMMARS["computer"].periodic
    assert GRAMMARS["computer"].fill_hand == 0.0
    lines = _centerlines(machine, monkeypatch)
    assert len(lines) >= 20
    angles = _stroke_angles_deg(lines)
    assert statistics.pstdev(angles) == pytest.approx(0.0, abs=1e-9)
    fractions = _reach_fractions(lines, _contour(machine))
    assert fractions
    assert max(abs(f) for f in fractions) == pytest.approx(0.0, abs=1e-9)


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


# --- stage 4: the corpus ---------------------------------------------------

NEW_CASES = {
    "C-fill-circle-computer": "fill-stroke-v1",
    "C-fill-circle-silverpoint": "fill-texture-v1",
    "C-fill-circle-crayon-extra_fine": "fill-texture-v1",
    "C-fill-circle-brush_thick-extra_fine": "fill-stroke-v1",
}


def test_t12_the_new_cases_exist_and_traverse_the_layer_they_were_added_for():
    """T-12 足した 4 case が、足した目的の層を実際に通る。

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
        assert f'class="{expected_class}' in svg, (case_id, expected_class)
        assert 'class="fill-underlay-v1"' in svg, case_id


def test_t13_the_frozen_corpus_moved_exactly_the_cases_the_contract_predicted():
    """T-13 コーパスの差分が予測と一致する。

    予測は既存 32 件（走査線・被覆 0.2 以上 21 ＋ 0.2 未満 11）。**打点 3 件には
    下地を置かない**と決めたので 35 ではない。`changed_from_previous` はこれに
    新規 4 件を足した 36 になる — 生成器は新規 case も changed に数えるからである。

    決定性そのものは `check_frozen_corpora.py` が見る（CI が走らせるものと同一）。
    """
    manifest = json.loads(ENGINE_22_MANIFEST.read_text())
    before = json.loads(ENGINE_21_MANIFEST.read_text())["cases"]
    changed = manifest["changed_from_previous"]
    moved = sorted(case_id for case_id in changed if case_id in before)
    added = sorted(case_id for case_id in changed if case_id not in before)
    assert len(moved) == 32, moved
    assert len(added) == 4, added
    assert len(changed) == 36
    assert len(manifest["cases"]) == 529
    assert manifest["engine_version"] == "22"

    # 動いたものが「塗りの走査線を通る case」であること。打点と rotring は不動。
    for case_id in ("C-tinyfill-circle-pen", "C-tinyfill-square-brush_thick",
                    "D-size-tiny-filled-circle", "C-tinyfill-circle-rotring"):
        assert case_id not in changed, case_id
