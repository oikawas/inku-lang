"""Stage 1.5 変奏 (v2.0) の契約テスト。

展開層は LLM を使わず決定的なので、変奏の契約はここで完結して検証できる。

**v2.11.0 で軸は焦点ひとつになった。**それ以前の 7 軸のうち 6 つ（型の差し替え・
採用本数・タッチ材質・主色/対比色・構図族・型の系統）は、いずれも Stage 1.5 が
自分で足した文を振っていた。その候補プールは添景であり、添景水準を畳んだときに
一緒に落ちた。**残る焦点は「記述をどこへ寄せて読むか」であって、足す文ではない。**
強度は今も出力へ届く（オフセットの鍵の一部なので、同じ seed でも小・中・大で
別の焦点に落ちる）。
"""

from __future__ import annotations

import pytest

from inku_server.ddl_expander import (
    AXIS_FOCUS,
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
def test_the_focus_is_the_only_axis_left(amplitude: str) -> None:
    """どの強度・どの seed でも、動く軸は焦点だけ (v2.11.0)。

    以前は強度が軸のプールを開けていた。開ける先の 6 軸は Stage 1.5 が自分で
    足した文を振るものだったので、候補プールと一緒に落ちている。
    """
    for text in _JA_TEXTS:
        for seed in _SWEEP:
            report: dict = {}
            _expand(
                text,
                report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert {entry["axis"] for entry in report["moved_axes"]} <= {AXIS_FOCUS}


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_variation_never_adds_a_sentence(amplitude: str) -> None:
    """対照。**軸が焦点だけであることと、文が増えないことは別の主張である。**

    焦点は既存の文を書き換えるだけで、足さない。ここが赤くなるのは、展開層が
    また自分の文を書き始めたときである。
    """
    for text in _JA_TEXTS:
        for seed in range(60):
            report: dict = {}
            expanded = _expand(
                text,
                report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            assert _added_sentence_count(text, expanded, lang="ja") == 0
            assert tuple(report["category_counts"]) == (0, 0, 0)


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


def test_the_amplitude_still_reaches_the_output() -> None:
    """強度は今も効く。**「軸が一つ」は「強度が死んだ」ではない。**

    オフセットの鍵は `強度:seed:軸` なので、同じ seed でも強度が違えば別の焦点に
    落ちる。ここが赤くなるのは、強度を鍵から外して選択が seed だけで決まる形へ
    退行したときである。
    """
    text = "中心に黒い四角を置く。白い横線を三本引く。"
    differing = 0
    for seed in range(40):
        resolved = set()
        for amplitude in VARIATION_AMPLITUDES:
            report: dict = {}
            expand_intermediate_ddl(
                text,
                variation_report=report,
                variation_amplitude=amplitude,
                variation_seed=seed,
            )
            resolved.add(report["resolved_focus"])
        if len(resolved) > 1:
            differing += 1
    assert differing >= 20, f"強度が焦点を動かした seed が {differing} / 40 しかない"


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


@pytest.mark.parametrize("amplitude", VARIATION_AMPLITUDES)
def test_the_plan_carries_the_focus_axis_and_nothing_else(amplitude: str) -> None:
    for seed in _SWEEP:
        plan = build_variation_plan(amplitude, seed)
        assert plan is not None
        assert plan.axes == (AXIS_FOCUS,)
        assert plan.offset(AXIS_FOCUS) is not None
