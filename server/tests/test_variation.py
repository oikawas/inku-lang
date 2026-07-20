"""Stage 1.5 変奏 (v2.0) の契約テスト。

展開層は LLM を使わず決定的なので、変奏の契約はここで完結して検証できる。
"""

from __future__ import annotations

import pytest

from inku_server.ddl_expander import (
    AXIS_COLOR,
    AXIS_COMPOSITION,
    AXIS_COUNT,
    AXIS_FOCUS,
    AXIS_TOUCH,
    AXIS_TYPE_FAMILY,
    AXIS_TYPE_SWAP,
    VARIATION_AMPLITUDES,
    _split_sentences,
    build_variation_plan,
    expand_intermediate_ddl,
)


_JA_TEXTS = (
    "中心に黒い四角を置く。白い横線を三本引く。",
    "満天の星空に白い小さな円を画面全体に点々と六百十個散らす。",
    "霧の中に一本の線を静かに引く。",
    "人が歩く道に低い雲が押し沈む。細い線を引く。",
)
_EN_TEXTS = (
    "Place one white circle near the center. Draw three black lines.",
    "Scatter countless small white dots across the whole canvas.",
)
# 小では絵の骨格が動かない。中では系統と構図族が動かない (契約 §3.2)。
_FROZEN_AXES = {
    "small": {AXIS_COMPOSITION, AXIS_FOCUS, AXIS_TOUCH, AXIS_TYPE_FAMILY},
    "medium": {AXIS_COMPOSITION, AXIS_TYPE_FAMILY},
    "large": set(),
}
_SWEEP = range(200)


def _expand(text: str, *, lang: str = "ja", report: dict | None = None, **kwargs) -> str:
    return expand_intermediate_ddl(
        text, lang=lang, variation_report=report, **kwargs
    )


def _added_sentence_count(text: str, expanded: str, *, lang: str) -> int:
    return len(_split_sentences(expanded, lang=lang)) - len(
        _split_sentences(text, lang=lang)
    )


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_same_amplitude_and_seed_reproduce_the_same_expansion(amplitude: str) -> None:
    for text in _JA_TEXTS + _EN_TEXTS:
        lang = "en" if text in _EN_TEXTS else "ja"
        for seed in (0, 7, 4242):
            first_report: dict = {}
            second_report: dict = {}
            first = _expand(
                text,
                lang=lang,
                report=first_report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            second = _expand(
                text,
                lang=lang,
                report=second_report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert first == second
            assert first_report == second_report


def test_variation_off_is_byte_identical_to_the_pre_variation_expansion() -> None:
    """片方でも欠ければ現行挙動と完全一致する (既存作品の再現性維持)。"""
    for text in _JA_TEXTS + _EN_TEXTS:
        lang = "en" if text in _EN_TEXTS else "ja"
        baseline = expand_intermediate_ddl(text, lang=lang)
        assert _expand(text, lang=lang) == baseline
        assert _expand(text, lang=lang, variation_amplitude="large") == baseline
        assert _expand(text, lang=lang, variation_seed=3) == baseline
        # 未知の強度は None に落ちる (focus の _validated_focus と同じ防御)
        assert (
            _expand(text, lang=lang, variation_amplitude="huge", variation_seed=3)
            == baseline
        )


def test_variation_off_reports_the_default_focus_and_no_moved_axes() -> None:
    report: dict = {}
    _expand(_JA_TEXTS[0], report=report)
    assert report["moved_axes"] == []
    assert report["resolved_focus"] is not None


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_amplitude_releases_axes_in_weight_order(amplitude: str) -> None:
    frozen = _FROZEN_AXES[amplitude]
    for text in _JA_TEXTS:
        for seed in _SWEEP:
            report: dict = {}
            _expand(
                text,
                report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            moved = {entry["axis"] for entry in report["moved_axes"]}
            assert not moved & frozen


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_amplitude_releases_axes_in_weight_order_for_english(amplitude: str) -> None:
    frozen = _FROZEN_AXES[amplitude]
    for text in _EN_TEXTS:
        for seed in _SWEEP:
            report: dict = {}
            _expand(
                text,
                lang="en",
                report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            moved = {entry["axis"] for entry in report["moved_axes"]}
            assert not moved & frozen


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_a_moved_axis_always_shows_a_real_difference(amplitude: str) -> None:
    """レポートが空でないなら出力は必ず動いており、その逆も成り立つ。"""
    for text in _JA_TEXTS + _EN_TEXTS:
        lang = "en" if text in _EN_TEXTS else "ja"
        baseline = expand_intermediate_ddl(text, lang=lang)
        for seed in range(60):
            report: dict = {}
            varied = _expand(
                text,
                lang=lang,
                report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert bool(report["moved_axes"]) == (varied != baseline)
            for entry in report["moved_axes"]:
                assert entry["from"] != entry["to"]


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_tenkei_none_moves_only_the_focus(amplitude: str) -> None:
    for text in _JA_TEXTS:
        for seed in _SWEEP:
            report: dict = {}
            _expand(
                text,
                report=report,
                tenkei="none",
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert {entry["axis"] for entry in report["moved_axes"]} <= {AXIS_FOCUS}


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_variation_never_exceeds_the_tenkei_cap(amplitude: str) -> None:
    """採用本数は cap 適用後の値に対して振り、cap を越えない (契約 §3.3)。"""
    for text in _JA_TEXTS:
        for seed in range(60):
            sparse: dict = {}
            _expand(
                text,
                report=sparse,
                tenkei="sparse",
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert sum(sparse["category_counts"]) <= 1
            none: dict = {}
            expanded = _expand(
                text,
                report=none,
                tenkei="none",
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert sum(none["category_counts"]) == 0
            assert _added_sentence_count(text, expanded, lang="ja") == 0


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_the_report_names_every_axis_that_moved_and_no_other(amplitude: str) -> None:
    """レポートにある軸は単独で動き、レポートにない軸は単独では動かない。"""
    for text in _JA_TEXTS:
        baseline = expand_intermediate_ddl(text)
        for seed in range(40):
            report: dict = {}
            _expand(
                text,
                report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            reported = {entry["axis"] for entry in report["moved_axes"]}
            plan = build_variation_plan(amplitude, seed)
            assert plan is not None
            for axis in reported:
                solo_report: dict = {}
                solo = expand_intermediate_ddl(
                    text,
                    variation_report=solo_report,
                    variation_amplitude=amplitude,
                    variation_seed=seed,
                )
                assert solo != baseline
                assert axis in {item["axis"] for item in solo_report["moved_axes"]}


def test_focus_axis_reports_the_focus_it_landed_on() -> None:
    """history.focus の供給源。変奏なしでも既定のハッシュ選択が記録される。"""
    text = "中心に黒い四角を置く。白い横線を三本引く。"
    default_report: dict = {}
    expand_intermediate_ddl(text, variation_report=default_report)
    default_focus = default_report["resolved_focus"]
    for seed in _SWEEP:
        report: dict = {}
        expand_intermediate_ddl(
            text,
            variation_report=report,
            variation_amplitude="large",
            variation_seed=seed,
        )
        moved = {entry["axis"] for entry in report["moved_axes"]}
        if AXIS_FOCUS in moved:
            assert report["resolved_focus"] != default_focus
        else:
            assert report["resolved_focus"] == default_focus


def test_explicit_focus_still_wins_over_the_variation_axis() -> None:
    text = "中心に黒い四角を置く。白い横線を三本引く。"
    for seed in range(40):
        report: dict = {}
        expand_intermediate_ddl(
            text,
            focus="upper_left",
            variation_report=report,
            variation_amplitude="large",
            variation_seed=seed,
        )
        assert report["resolved_focus"] == "upper_left"


def test_plan_is_none_unless_both_amplitude_and_seed_are_given() -> None:
    assert build_variation_plan(None, 3) is None
    assert build_variation_plan("small", None) is None
    assert build_variation_plan("huge", 3) is None
    assert build_variation_plan("small", 3) is not None


@pytest.mark.parametrize(
    ("amplitude", "low", "high"),
    [("small", 1, 1), ("medium", 1, 2), ("large", 2, 4)],
)
def test_plan_moves_the_documented_number_of_axes(
    amplitude: str, low: int, high: int
) -> None:
    for seed in _SWEEP:
        plan = build_variation_plan(amplitude, seed)
        assert plan is not None
        assert low <= len(plan.axes) <= high
        assert len(set(plan.axes)) == len(plan.axes)


def test_plan_axis_pool_respects_the_tier_order() -> None:
    tier_one = {AXIS_TYPE_SWAP, AXIS_COUNT}
    tier_two = tier_one | {AXIS_TOUCH, AXIS_FOCUS, AXIS_COLOR}
    for seed in _SWEEP:
        assert set(build_variation_plan("small", seed).axes) <= tier_one
        assert set(build_variation_plan("medium", seed).axes) <= tier_two
    assert build_variation_plan("small", 1, tenkei="none").axes == (AXIS_FOCUS,)
    assert build_variation_plan("large", 1, tenkei="none").axes == (AXIS_FOCUS,)
