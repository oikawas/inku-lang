"""v1.93: region (at) 配置と relation の共存回帰 (F-1 修正).

修正前は _resolve_at_region -> _move_anchor_to が relation を無警告で pop し、
at と relation を両持ちする instruction (プラグイン member 由来の双弧など) は
touching 解決に到達しなかった。修正後は region 配置後に relation が解決される。
演奏時に解決不能な relation は §14.4 に従い警告記録付きで drop する。
"""

import re

import pytest

from inku_server.renderer import render
from inku_server.schema import Score

SEED = 424242

_ARC_RE = re.compile(
    r"M ([\d.\-]+) ([\d.\-]+) A ([\d.\-]+) [\d.\-]+ [\d.\-]+ (\d) (\d) ([\d.\-]+) ([\d.\-]+)"
)


def _arc_paths(svg: str) -> list[tuple]:
    out = []
    for d in re.findall(r'd="(M [^"]*A [^"]*)"', svg):
        m = _ARC_RE.match(d)
        if m:
            x1, y1, r, laf, sf, x2, y2 = m.groups()
            out.append(
                (
                    round(float(x1)),
                    round(float(y1)),
                    round(float(x2)),
                    round(float(y2)),
                    int(laf),
                    int(sf),
                )
            )
    return out


def _double_arc_score(with_at: bool) -> Score:
    base = {
        "primitive": "arc",
        "weight": "pen",
        "color": "black",
        "center": [0.5, 0.5],
        "radius": 0.15,
        "angle_start": 0.0,
        "angle_end": 120.0,
    }
    second = {**base, "relation": {"type": "touching"}}
    if with_at:
        base = {**base, "at": {"region": [0.2, 0.2, 0.5, 0.5]}}
        second = {**second, "at": {"region": [0.5, 0.5, 0.8, 0.8]}}
    return Score.model_validate({"version": "0.1.0", "instructions": [base, second]})


def _assert_vesica(svg: str) -> None:
    arcs = _arc_paths(svg)
    assert len(arcs) == 2, f"expected 2 arc paths, got {len(arcs)}"
    (s1x, s1y, e1x, e1y, laf1, sf1), (s2x, s2y, e2x, e2y, laf2, sf2) = arcs
    # 両端一致 (touching)
    assert {(s1x, s1y), (e1x, e1y)} == {(s2x, s2y), (e2x, e2y)}
    # 双方とも劣弧 (§14.4: 掃引角 180° 未満)
    assert laf1 == 0 and laf2 == 0
    # 膨らみが対向 (同一方向に描かれた円弧の連続ではない)
    assert (sf1 != sf2) or ((s1x, s1y) != (s2x, s2y))


def test_touching_survives_region_placement() -> None:
    """F-1 修正の本体: at + relation 両持ちでも touching が解決される。"""
    svg = render(_double_arc_score(with_at=True), render_seed=SEED)
    _assert_vesica(svg)


def test_touching_without_region_still_works() -> None:
    svg = render(_double_arc_score(with_at=False), render_seed=SEED)
    _assert_vesica(svg)


def test_region_relation_render_is_deterministic() -> None:
    score = _double_arc_score(with_at=True)
    assert render(score, render_seed=SEED) == render(score, render_seed=SEED)


def test_region_only_instruction_stays_inside_region() -> None:
    score = Score.model_validate(
        {
            "version": "0.1.0",
            "instructions": [
                {
                    "primitive": "circle",
                    "weight": "pen",
                    "color": "black",
                    "center": [0.5, 0.5],
                    "radius": 0.05,
                    "at": {"region": [0.6, 0.6, 0.9, 0.9]},
                }
            ],
        }
    )
    svg = render(score, render_seed=SEED)
    m = re.search(r'<circle[^>]*cx="([\d.]+)" cy="([\d.]+)"', svg)
    assert m is not None
    cx, cy = float(m.group(1)) / 1000, float(m.group(2)) / 1000
    assert 0.6 <= cx <= 0.9 and 0.6 <= cy <= 0.9


def test_invalid_touching_primitive_drops_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """touching は line/arc 限定 (§14.4)。円への付与は警告記録付き drop。"""
    score = Score.model_validate(
        {
            "version": "0.1.0",
            "instructions": [
                {
                    "primitive": "line",
                    "weight": "pen",
                    "color": "black",
                    "from": [0.3, 0.5],
                    "to": [0.7, 0.5],
                },
                {
                    "primitive": "circle",
                    "weight": "pen",
                    "color": "black",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                    "relation": {"type": "touching"},
                },
            ],
        }
    )
    with caplog.at_level("WARNING", logger="inku_server.renderer"):
        render(score, render_seed=SEED)
    assert any("relation dropped at performance" in r.message for r in caplog.records)


def test_grid_relation_drops_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    score = Score.model_validate(
        {
            "version": "0.1.0",
            "instructions": [
                {
                    "primitive": "line",
                    "weight": "pen",
                    "color": "black",
                    "from": [0.3, 0.5],
                    "to": [0.7, 0.5],
                },
                {
                    "primitive": "circle",
                    "weight": "pen",
                    "color": "black",
                    "center": [0.5, 0.5],
                    "radius": 0.05,
                    "relation": {"type": "along"},
                    "arrangement": {"count": 4, "layout": "grid"},
                },
            ],
        }
    )
    with caplog.at_level("WARNING", logger="inku_server.renderer"):
        render(score, render_seed=SEED)
    assert any("reason=grid layout" in r.message for r in caplog.records)
