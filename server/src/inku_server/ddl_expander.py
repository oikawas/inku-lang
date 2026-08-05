"""Intermediate DDL expansion between Stage 1 and Stage 2.

The expander keeps Stage 1 deterministic and cheap while giving Stage 2
more compositional material: secondary structure, asymmetry, and controlled
variation. It intentionally emits ordinary normalized DDL sentences instead
of JSON so the existing Stage 2 compiler remains the single JSON authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .interpreter import _sanitize_placement_words


_JA_EXPANSION_MARKERS = (
    "右半分の斜めの帯",
    "左下から右上へ",
    "波打つ軌跡に沿って",
    "左下の焦点から三つ",
    "右下の焦点から三つ",
    "黄金比の位置",
    "三分割の交点",
    "白銀比の位置",
    "正五角形の頂点",
    "対位法の反行",
    "倍音列",
    "輪唱のずれ",
    "一点透視法",
    "遠近法の奥行き",
    "素描の下線",
    "点描",
    "油絵の厚塗り",
    "水彩",
    "パッチワーク",
    "フレスコの下地",
    "水墨の濃淡",
    "鉛筆の余白線",
    "クレヨンの擦れ",
    "ロットリングの均一線",
    "透明な膜",
    "薄い反射",
    "消える線",
    "柔らかな光",
    "香りの層",
    "開花を待つ蕾",
    "五感の気配",
    "前の線を切る",
    "前の線に沿って",
    "前の形に触れない",
    "前の二つの間に",
    "斜めの線を三本",
    "右下の焦点から外へ",
    "右下の焦点から放射状に",
    "全体の反復配置",
    "全体の揺らぎ",
)
_EN_EXPANSION_MARKERS = (
    "diagonal band in the right half",
    "lower left to upper right",
    "undulating trace",
    "lower-left focus",
    "golden-ratio position",
    "rule-of-thirds point",
    "silver-ratio position",
    "regular pentagon vertices",
    "contrapuntal contrary motion",
    "harmonic overtone series",
    "canon offset",
    "one-point perspective",
    "perspective depth",
    "drawing underlines",
    "pointillism",
    "oil impasto",
    "watercolor",
    "patchwork",
    "fresco ground",
    "ink-wash value",
    "pencil negative-space line",
    "crayon rubbing",
    "rotring uniform lines",
    "transparent membrane",
    "faint reflection",
    "fading lines",
    "soft light",
    "scent layer",
    "waiting buds",
    "five-sense presence",
    "cutting the previous line",
    "along the previous line",
    "not touching the previous shape",
    "between the previous two",
    "outward from a lower-right focus",
    "radiating from a lower-right focus",
    "set repeated placement",
    "use no variation",
)


def _has_explicit_numeric_regions(ddl: str, *, lang: str) -> bool:
    """Treat already region-resolved core DDL as structurally expanded.

    A numeric region is a composition decision, not a sparse semantic hint.
    Stage 1.5 may sanitize it, but must not append another finished-work recipe.
    This boundary is generic and has no knowledge of plugin namespaces.
    """

    marker = r"\bregion\s*\[" if lang == "en" else r"領域\s*\["
    return re.search(marker, ddl, flags=re.IGNORECASE) is not None


def _split_sentences(text: str, *, lang: str) -> list[str]:
    if lang == "en":
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return [s.strip() for s in re.split(r"(?<=。)", text.strip()) if s.strip()]


def _join_sentences(sentences: list[str], *, lang: str) -> str:
    if lang == "en":
        return " ".join(s if s.endswith((".", "!", "?")) else f"{s}." for s in sentences)
    return "".join(s if s.endswith("。") else f"{s}。" for s in sentences)


_NATURE_PLUGIN_RE = re.compile(r"Nature\.(風|うねり|無風|wind|undulation|stillness|calm)", re.IGNORECASE)


def _nature_plugin_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for match in _NATURE_PLUGIN_RE.finditer(text):
        term = match.group(1).lower()
        if term in {"風", "wind"}:
            terms.add("wind")
        elif term in {"うねり", "undulation"}:
            terms.add("undulation")
        elif term in {"無風", "stillness", "calm"}:
            terms.add("stillness")
    return terms


def _drop_nature_plugin_sentences(text: str, *, lang: str) -> str:
    sentences = _split_sentences(text, lang=lang)
    kept = [sentence for sentence in sentences if not _NATURE_PLUGIN_RE.search(sentence)]
    if kept:
        return _join_sentences(kept, lang=lang)
    return ""


def _apply_nature_plugin_macros(ddl: str, *, lang: str, enable_plugins: bool) -> str:
    if not enable_plugins:
        return ddl
    terms = _nature_plugin_terms(ddl)
    if not terms:
        return ddl
    base = _drop_nature_plugin_sentences(ddl, lang=lang)
    macro: list[str] = []
    if lang == "en":
        if "stillness" in terms:
            macro.append("Use no variation. Use no placement path; keep the repeated placement still.")
        else:
            if "wind" in terms:
                macro.append("Set repeated placement left to right in horizontal strata. Swaying slowly.")
            if "undulation" in terms:
                macro.append("Set repeated placement along an undulating trace. Broad slow swaying.")
    else:
        if "stillness" in terms:
            macro.append("全体の揺らぎをなしにする。配置軌跡は使わず静止させる。")
        else:
            if "wind" in terms:
                macro.append("全体の反復配置を左から右への横の帯に沿わせる。ゆっくり揺れる。")
            if "undulation" in terms:
                macro.append("全体の反復配置を波打つ軌跡に沿わせる。揺らぎは大きくゆっくり。")
    joined_macro = _join_sentences(macro, lang=lang) if macro else ""
    return _join_sentences([base, joined_macro], lang=lang) if base and joined_macro else (base or joined_macro or ddl)


def _seed(text: str, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _pick(items: list[str], count: int, *, text: str, salt: str) -> list[str]:
    if count <= 0 or not items:
        return []
    ranked = sorted(
        items,
        key=lambda item: _seed(f"{text}:{item}", salt),
    )
    return ranked[: min(count, len(ranked))]


@dataclass(frozen=True)
class _FilterProfile:
    intensity: int
    tags: frozenset[str]
    mode: str


@dataclass(frozen=True)
class _FilterCandidate:
    text: str
    tags: frozenset[str]
    # 変奏レポートに出す型の短い名前。内部シンボル名は出さない (契約 §3.5)。
    label: str = ""


# Canonical focus ids. The expander picks one from the DDL hash unless the
# caller names one explicitly (v1.98), which keeps every existing artwork
# reproducible while letting the refine tab move the focus on purpose.
FOCUS_IDS = (
    "upper_right",
    "upper_left",
    "lower_right",
    "lower_left",
    "upper_edge",
    "right_half",
)

_FOCUS_WORDS_JA = {
    "upper_right": "右上の焦点",
    "upper_left": "左上の焦点",
    "lower_right": "右下の焦点",
    "lower_left": "左下の焦点",
    "upper_edge": "上端寄りの焦点",
    "right_half": "右半分の焦点",
}

_FOCUS_WORDS_EN = {
    "upper_right": "upper-right focus",
    "upper_left": "upper-left focus",
    "lower_right": "lower-right focus",
    "lower_left": "lower-left focus",
    "upper_edge": "upper-edge focus",
    "right_half": "right-half focus",
}


# 変奏レポート (moved_axes) の from / to に載せる短い表示語。
# 内部シンボル名はカードに出さない (契約 §3.5)。
_FOCUS_SHORT_JA = {
    "upper_right": "右上",
    "upper_left": "左上",
    "lower_right": "右下",
    "lower_left": "左下",
    "upper_edge": "上端",
    "right_half": "右半分",
}
_FOCUS_SHORT_EN = {
    "upper_right": "upper right",
    "upper_left": "upper left",
    "lower_right": "lower right",
    "lower_left": "lower left",
    "upper_edge": "upper edge",
    "right_half": "right half",
}

def focus_word(focus: str | None, *, lang: str) -> str | None:
    words = _FOCUS_WORDS_EN if lang == "en" else _FOCUS_WORDS_JA
    return words.get(focus or "")


def _dynamic_focus_ja(text: str, focus: str | None = None) -> str:
    named = focus_word(focus, lang="ja")
    if named:
        return named
    focuses = tuple(_FOCUS_WORDS_JA[key] for key in FOCUS_IDS)
    return focuses[_seed(text, "ja-focus") % len(focuses)]


def _dynamic_focus_en(text: str, focus: str | None = None) -> str:
    named = focus_word(focus, lang="en")
    if named:
        return named
    focuses = tuple(_FOCUS_WORDS_EN[key] for key in FOCUS_IDS)
    return focuses[_seed(text, "en-focus") % len(focuses)]


def _reframe_static_center_ja(ddl: str, focus: str | None = None) -> str:
    focus = _dynamic_focus_ja(ddl, focus)
    result = ddl
    replacements = (
        "画面中央",
        "中央付近",
        "中心付近",
        "中央",
        "中心",
    )
    for word in replacements:
        result = result.replace(word, focus)
    return result


def _reframe_static_center_en(ddl: str, focus: str | None = None) -> str:
    focus = _dynamic_focus_en(ddl, focus)
    result = ddl
    replacements = (
        (r"\bnear the center\b", f"near the {focus}"),
        (r"\bat the center\b", f"at the {focus}"),
        (r"\bat center\b", f"at the {focus}"),
        (r"\btoward the center\b", f"toward the {focus}"),
        (r"\bfrom center\b", f"from the {focus}"),
        (r"\bfrom the center\b", f"from the {focus}"),
        (r"\bthe center\b", f"the {focus}"),
        (r"\bcenter\b", focus),
    )
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


# ---------------------------------------------------------------------------
# Stage 1.5 変奏 (v2.0)
#
# 変奏は「楽譜の変奏」であり決定的である。(amplitude, seed) が同じなら展開結果は
# 常に同一になる。Renderer 層の「揺らぎ」(演奏・非決定的) とは層も語も分ける。
# ---------------------------------------------------------------------------

VARIATION_AMPLITUDES = ("small", "medium", "large")

# Focus is the only axis. The six others (type swap, count, touch, colour,
# composition family, type family) all varied sentences Stage 1.5 appended on
# its own, and those went away with the staffage level (v2.11.0).
AXIS_FOCUS = "focus"  # 焦点


@dataclass(frozen=True)
class VariationPlan:
    """どの軸をどれだけずらすかの決定的な計画。

    offsets は (軸, オフセット) の並びで、オフセットは各決定点で「既定と異なる
    選択肢」を選ぶための添字として使う。軸選択・オフセットとも `_seed` の
    ハッシュのみから決まり、乱数源は使わない。
    """

    amplitude: str
    seed: int
    offsets: tuple[tuple[str, int], ...]

    @property
    def axes(self) -> tuple[str, ...]:
        return tuple(axis for axis, _ in self.offsets)

    def offset(self, axis: str) -> int | None:
        for name, value in self.offsets:
            if name == axis:
                return value
        return None

    def restricted_to(self, axis: str) -> VariationPlan:
        """1 軸だけを残した計画。moved_axes の軸別帰属に使う。"""
        return VariationPlan(
            amplitude=self.amplitude,
            seed=self.seed,
            offsets=tuple(item for item in self.offsets if item[0] == axis),
        )


def _variation_base_offset(amplitude: str, seed: int, axis: str) -> int:
    return 1 + _seed(f"{amplitude}:{int(seed)}:{axis}", "variation-offset") % 97


def build_variation_plan(amplitude: str | None, seed: int | None) -> VariationPlan | None:
    """(強度, seed) から変奏プランを 1 回だけ決定的に組む。

    どちらかが欠けていれば None を返し、展開は変奏前と完全に一致する。
    未知の強度も None に落とす (focus の `_validated_focus` と同じ防御)。

    Focus is the one axis left. The others -- type swap, count, touch, colour,
    composition family, type family -- all varied sentences Stage 1.5 invented,
    and those went away with the staffage level (v2.11.0). The amplitude still
    reaches the output: it is part of the offset key, so small / medium / large
    resolve the focus differently for the same seed.
    """
    if amplitude not in VARIATION_AMPLITUDES or seed is None:
        return None
    return VariationPlan(
        amplitude=amplitude,
        seed=int(seed),
        offsets=((AXIS_FOCUS, _variation_base_offset(amplitude, seed, AXIS_FOCUS)),),
    )


# 選んだ軸が既定と同じ出力に落ちたとき、隣のオフセットへ送る試行回数。
_VARIATION_OFFSET_TRIES = 8


def _effective_variation_plan(
    plan: VariationPlan, *, base_text: str, run: object
) -> VariationPlan | None:
    """「動かした軸は必ず目に見えて動く」を実際の出力で保証する (契約 §3.2)。

    値をずらしても出力に効かないことがある (例: 焦点語を持たない DDL)。
    その場合は隣のオフセットへ送る。解決は決定的なので再現性は保たれる。
    """
    resolved: list[tuple[str, int]] = []
    base_offset = _variation_base_offset(plan.amplitude, plan.seed, AXIS_FOCUS)
    for step in range(_VARIATION_OFFSET_TRIES):
        offset = base_offset + step
        trial = VariationPlan(
            amplitude=plan.amplitude, seed=plan.seed, offsets=((AXIS_FOCUS, offset),)
        )
        if run(trial, None) != base_text:  # type: ignore[operator]
            resolved.append((AXIS_FOCUS, offset))
            break
    if not resolved:
        return None
    return VariationPlan(
        amplitude=plan.amplitude, seed=plan.seed, offsets=tuple(resolved)
    )


def _shift_choice(default: str, pool: list[str], offset: int) -> str:
    """既定と異なる選択肢へ決定的に送る。

    候補が既定しかない場合だけ既定のまま返す (その軸は動かない)。
    """
    unique = list(dict.fromkeys(pool))
    others = [item for item in unique if item != default]
    if not others:
        return default
    return others[offset % len(others)]


def _resolve_focus_id(
    text: str, focus: str | None, plan: VariationPlan | None, *, lang: str
) -> str:
    """焦点の決定。明示指定 > 変奏 > DDL テキストのハッシュ (既定)。"""
    if focus in FOCUS_IDS:
        return focus  # type: ignore[return-value]
    salt = "en-focus" if lang == "en" else "ja-focus"
    default = FOCUS_IDS[_seed(text, salt) % len(FOCUS_IDS)]
    offset = plan.offset(AXIS_FOCUS) if plan else None
    if offset is None:
        return default
    return _shift_choice(default, list(FOCUS_IDS), offset)


def _axis_value(axis: str, decisions: dict, *, lang: str, joiner: str) -> str:
    value = decisions.get(axis)
    if axis == AXIS_FOCUS:
        words = _FOCUS_SHORT_EN if lang == "en" else _FOCUS_SHORT_JA
        return words.get(str(value), str(value))
    if isinstance(value, list):
        return joiner.join(item for item in value if item)
    return "" if value is None else str(value)


def _variation_moved_axes(
    plan: VariationPlan,
    base_text: str,
    base_decisions: dict,
    *,
    lang: str,
    expand: object,
) -> list[dict[str, str]]:
    """軸別の帰属。その軸だけを適用して出力が動いた軸のみを報告する。

    プランが動かすと決めただけでは載せない。展開は決定的で LLM を使わないため、
    軸ごとの単独適用を実際に走らせて差分を確かめるのが最も正確で安い。
    """
    joiner = ", " if lang == "en" else "・"
    moved: list[dict[str, str]] = []
    for axis in plan.axes:
        solo_decisions: dict = {}
        solo_text = expand(plan.restricted_to(axis), solo_decisions)  # type: ignore[operator]
        if solo_text == base_text:
            continue
        before = _axis_value(axis, base_decisions, lang=lang, joiner=joiner)
        after = _axis_value(axis, solo_decisions, lang=lang, joiner=joiner)
        moved.append({"axis": axis, "from": before, "to": after})
    return moved


def expand_intermediate_ddl(
    ddl: str,
    *,
    lang: str = "ja",
    context_text: str | None = None,
    composition_seed: int | None = None,
    enable_plugins: bool = True,
    plugin_instructions_present: bool = False,
    focus: str | None = None,
    variation_amplitude: str | None = None,
    variation_seed: int | None = None,
    variation_report: dict | None = None,
) -> str:
    """Add controlled complexity to normalized DDL before Stage 2.

    The filter favors visible mathematical structure over vague randomness:
    golden-ratio accents, rule-of-thirds anchors, silver-ratio counterpoints,
    Fibonacci-friendly counts, radial echoes, diagonal counter-lines,
    harmonic overtones, contrapuntal contrary motion, canon-like repetitions,
    painterly material techniques, perspective guides, value structure, and
    motion-derived wave traces.

    変奏 (v2.0): `variation_amplitude` と `variation_seed` が揃ったときだけ
    Stage 1.5 の決定点をずらす。片方でも欠ければ展開結果は変奏前と完全に一致する。
    `variation_report` を渡すと `moved_axes` と `resolved_focus` を書き込む。
    """

    sanitized = _sanitize_placement_words(ddl).strip()
    sanitized = _apply_nature_plugin_macros(sanitized, lang=lang, enable_plugins=enable_plugins)
    if not sanitized:
        return sanitized
    expander = _expand_en if lang == "en" else _expand_ja

    def run(plan: VariationPlan | None, decisions: dict | None) -> str:
        return expander(
            sanitized,
            context_text=context_text,
            composition_seed=composition_seed,
            plugin_instructions_present=plugin_instructions_present,
            focus=focus,
            plan=plan,
            decisions=decisions,
        )

    plan = build_variation_plan(variation_amplitude, variation_seed)
    base_decisions: dict = {}
    base_text = run(None, base_decisions)
    if variation_report is not None:
        variation_report["resolved_focus"] = base_decisions.get(AXIS_FOCUS)
        variation_report["moved_axes"] = []
        variation_report["category_counts"] = base_decisions.get(
            "category_counts", (0, 0, 0)
        )
    if plan is not None:
        plan = _effective_variation_plan(plan, base_text=base_text, run=run)
    if plan is None:
        return base_text
    decisions: dict = {}
    text = run(plan, decisions)
    if variation_report is not None:
        variation_report["resolved_focus"] = decisions.get(AXIS_FOCUS)
        variation_report["category_counts"] = decisions.get(
            "category_counts", (0, 0, 0)
        )
        variation_report["moved_axes"] = _variation_moved_axes(
            plan, base_text, base_decisions, lang=lang, expand=run
        )
    return text


def _expand_ja(
    ddl: str,
    *,
    context_text: str | None = None,
    composition_seed: int | None = None,
    plugin_instructions_present: bool = False,
    focus: str | None = None,
    plan: VariationPlan | None = None,
    decisions: dict | None = None,
) -> str:
    # v1.96 2a: 対 member 決定的転写 (§4.6) で領域文がテキストに残らない場合も
    # 数値 region ガードと同等に完成品レシピの追加を抑止する。
    if (
        plugin_instructions_present
        or _has_explicit_numeric_regions(ddl, lang="ja")
        or any(marker in ddl for marker in _JA_EXPANSION_MARKERS)
    ):
        return ddl
    focus_id = _resolve_focus_id(ddl, focus, plan, lang="ja")
    if decisions is not None:
        decisions[AXIS_FOCUS] = focus_id
    # Stage 1.5 reframes the focus and stops. The candidate pool that used to
    # append structural / musical / painterly sentences here was staffage: it
    # wrote lines the description never asked for (folded away in v2.11.0).
    return _reframe_static_center_ja(ddl, focus_id)


def _expand_en(
    ddl: str,
    *,
    context_text: str | None = None,
    composition_seed: int | None = None,
    plugin_instructions_present: bool = False,
    focus: str | None = None,
    plan: VariationPlan | None = None,
    decisions: dict | None = None,
) -> str:
    lower = ddl.lower()
    # v1.96 2a: mirror of the ja guard (§4.6 pair-transcription boundary).
    if (
        plugin_instructions_present
        or _has_explicit_numeric_regions(ddl, lang="en")
        or any(marker in lower for marker in _EN_EXPANSION_MARKERS)
    ):
        return ddl
    focus_id = _resolve_focus_id(ddl, focus, plan, lang="en")
    if decisions is not None:
        decisions[AXIS_FOCUS] = focus_id
    # Mirror of the ja expander: reframe the focus, add nothing.
    return _reframe_static_center_en(ddl, focus_id)
