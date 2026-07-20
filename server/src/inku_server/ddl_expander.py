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


_JA_COLORS = ("赤", "青", "緑", "白", "黒", "灰")
_JA_COLOR_WORD = {
    "赤": "赤い",
    "青": "青い",
    "緑": "緑の",
    "白": "白い",
    "黒": "黒い",
    "灰": "灰色の",
}
_EN_COLORS = ("red", "blue", "green", "white", "black", "gray")
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


def _avoid_gray_background(text: str, *, lang: str) -> str:
    if lang == "en":
        return re.sub(
            r"Fill background with gr[ae]y\.?",
            "Fill background with white.",
            text,
            flags=re.IGNORECASE,
        )
    return re.sub(r"背景を灰(?:色)?で塗りつぶす。?", "背景を白で塗りつぶす。", text)


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


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _has_en_terms(text: str, tokens: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", text) for token in tokens)


def _profile_ja(text: str) -> _FilterProfile:
    tags: set[str] = set()
    intensity = 2
    mode = "asymmetric_rhythm"

    if _has_any(text, ("余白", "静か", "一滴", "一本", "ひとつ", "孤独", "ぽつん", "霧", "淡", "薄い")):
        intensity = 1
        tags.update(("quiet", "space"))
        mode = "single_tension"
    if _has_any(text, ("満天", "無数", "密集", "びっしり", "埋め尽く", "嵐", "群れ", "祭", "都市", "複雑")):
        intensity = 3
        tags.add("dense")
        mode = "layered_trace"

    if _has_any(text, ("円", "粒", "星", "雪", "雨", "砂", "花びら", "散らす", "点々")):
        tags.add("particle")
    if _has_any(text, ("線", "糸", "水平", "垂直", "縦", "横", "斜め")):
        tags.add("line")
        mode = "asymmetric_rhythm" if mode != "single_tension" else mode
    if _has_any(text, ("水", "波", "月", "霧", "滲", "淡", "雲")):
        tags.update(("water", "soft"))
    if _has_any(text, ("膜", "透明", "霞", "霧", "靄", "気配", "余韻", "反射", "映り", "消え", "薄れ")):
        tags.update(("soft", "atmosphere"))
    if _has_any(text, ("香", "匂", "陽光", "光", "春", "蕾", "つぼみ", "開花", "待つ", "五感", "温", "柔ら")):
        tags.update(("soft", "sensory"))
    if _has_any(text, ("音", "リズム", "歌", "輪唱", "響", "反復", "揺", "舞", "流")):
        tags.add("music")
    if _has_any(text, ("建物", "都市", "寺", "古刹", "部屋", "道", "遠く", "奥", "畑")):
        tags.add("space")
        mode = "edge_focus" if mode != "single_tension" else mode
    if _has_any(text, ("黒", "白", "影", "明暗", "暗", "光", "灰")):
        tags.add("contrast")
    if _has_any(text, ("四角", "格子", "幾何", "均衡", "法則", "対称")):
        tags.add("geometry")
    if _has_any(text, ("人", "人物", "村人", "老人", "顔", "視線", "動物", "鳥", "魚", "熊", "群れ")):
        tags.update(("presence", "space"))
        mode = "field_and_interruption" if mode != "single_tension" else mode

    if _has_any(text, ("影", "痕跡", "埃", "足跡", "残", "冷え", "錆")) and mode != "single_tension":
        mode = "field_and_interruption"

    return _FilterProfile(intensity=intensity, tags=frozenset(tags), mode=mode)


def _profile_en(text: str) -> _FilterProfile:
    lower = text.lower()
    tags: set[str] = set()
    intensity = 2
    mode = "asymmetric_rhythm"

    if _has_any(lower, ("empty space", "quiet", "single", "one ", "alone", "solitary", "mist", "pale")):
        intensity = 1
        tags.update(("quiet", "space"))
        mode = "single_tension"
    if _has_any(lower, ("starry", "countless", "dense", "packed", "fill", "storm", "crowd", "city", "complex")):
        intensity = 3
        tags.add("dense")
        mode = "layered_trace"

    if _has_any(lower, ("circle", "dot", "particle", "star", "snow", "rain", "sand", "petal", "scatter", "dotted")):
        tags.add("particle")
    if _has_any(lower, ("line", "thread", "horizontal", "vertical", "diagonal")):
        tags.add("line")
        mode = "asymmetric_rhythm" if mode != "single_tension" else mode
    if _has_any(lower, ("water", "wave", "moon", "mist", "blur", "pale", "cloud")):
        tags.update(("water", "soft"))
    if _has_any(lower, ("membrane", "transparent", "haze", "fog", "mist", "atmosphere", "presence", "reflection", "fade", "fading")):
        tags.update(("soft", "atmosphere"))
    if _has_any(lower, ("scent", "fragrance", "sunlight", "light", "spring", "bud", "bloom", "waiting", "sense", "warm", "soft")):
        tags.update(("soft", "sensory"))
    if _has_any(lower, ("sound", "rhythm", "song", "canon", "echo", "repeat", "sway", "drift")):
        tags.add("music")
    if _has_any(lower, ("building", "city", "temple", "room", "road", "distant", "depth", "field")):
        tags.add("space")
        mode = "edge_focus" if mode != "single_tension" else mode
    if _has_any(lower, ("black", "white", "shadow", "value", "dark", "light", "gray")):
        tags.add("contrast")
    if _has_any(lower, ("square", "grid", "geometric", "balance", "law", "symmetry")):
        tags.add("geometry")
    if _has_any(lower, ("human", "person", "people", "figure", "face", "gaze", "animal", "bird", "fish", "bear", "flock", "herd")):
        tags.update(("presence", "space"))
        mode = "field_and_interruption" if mode != "single_tension" else mode

    if _has_any(lower, ("shadow", "trace", "dust", "footprint", "remains", "cold", "rust")) and mode != "single_tension":
        mode = "field_and_interruption"

    return _FilterProfile(intensity=intensity, tags=frozenset(tags), mode=mode)


def _category_pool(
    candidates: list[_FilterCandidate], *, profile: _FilterProfile
) -> list[_FilterCandidate]:
    if profile.tags & {"atmosphere", "sensory", "presence"}:
        preferred_tags = profile.tags & {"atmosphere", "sensory", "presence"}
        matched = [c for c in candidates if c.tags & preferred_tags]
        if matched:
            return matched

    if profile.intensity <= 1:
        matched = [c for c in candidates if c.tags & {"quiet", "soft", "water"}]
    else:
        matched = [c for c in candidates if c.tags & profile.tags]
    return matched or candidates


def _select_category(
    candidates: list[_FilterCandidate],
    count: int,
    *,
    profile: _FilterProfile,
    text: str,
    salt: str,
    swap_offset: int | None = None,
) -> list[str]:
    if count <= 0:
        return []
    pool = [c.text for c in _category_pool(candidates, profile=profile)]
    default = _pick(pool, count, text=text, salt=salt)
    if swap_offset is None:
        return default
    # 型の差し替え: 既定と同じ結果に落ちた場合は隣の選択肢へ送る (契約 §3.2)。
    for step in range(len(pool) + 1):
        alternate = _pick(pool, count, text=text, salt=f"{salt}#hensou{swap_offset + step}")
        if alternate != default:
            return alternate
    return default


def _category_plan(profile: _FilterProfile, *, has_structural: bool) -> tuple[int, int, int]:
    if profile.intensity <= 1:
        return (0, 0, 0)

    if profile.intensity >= 3:
        if "music" in profile.tags:
            return (1 if has_structural else 0, 1, 0)
        return (1 if has_structural else 0, 0, 1 if profile.tags & {"geometry", "space", "water"} else 0)

    if "music" in profile.tags:
        return (0, 1, 0)
    if "sensory" in profile.tags:
        return (2 if has_structural else 0, 0, 1)
    if "atmosphere" in profile.tags:
        return (2 if has_structural else 0, 0, 0)
    if "presence" in profile.tags:
        return (1 if has_structural else 0, 0, 1)
    if profile.tags & {"geometry", "space"}:
        return (0, 0, 1)
    return (1 if has_structural else 0, 0, 0)


def _mode_salt(profile: _FilterProfile, category: str) -> str:
    return f"{profile.mode}:{category}"


def _structural_tags(text: str) -> frozenset[str]:
    tags = {"particle", "line", "water", "space"}
    lower = text.lower()
    if any(token in text or token in lower for token in ("透明な膜", "薄い反射", "消える線", "transparent membrane", "faint reflection", "fading lines")):
        tags.add("atmosphere")
        tags.add("soft")
    if any(token in text or token in lower for token in ("柔らかな光", "香りの層", "開花を待つ蕾", "五感の気配", "soft light", "scent layer", "waiting buds", "five-sense presence")):
        tags.add("sensory")
        tags.add("soft")
    if any(token in text or token in lower for token in ("存在の重心", "輪郭の密度", "presence weight", "contour density")):
        tags.add("presence")
        tags.add("space")
    return frozenset(tags)


def _limit_centered(items: list[str], *, centered_tokens: tuple[str, ...], max_count: int = 1) -> list[str]:
    result: list[str] = []
    centered_count = 0
    for item in items:
        is_centered = any(token in item for token in centered_tokens)
        if is_centered:
            if centered_count >= max_count:
                continue
            centered_count += 1
        result.append(item)
    return result


def _composition_pool(profile: _FilterProfile) -> list[str]:
    if profile.mode == "single_tension":
        return ["edge_retreat", "one_sided_focus", "central_stillness"]
    if "music" in profile.tags or "line" in profile.tags:
        return ["vertical_rhythm", "horizontal_strata", "dispersal", "radial_concentric", "edge_retreat"]
    if "particle" in profile.tags or "dense" in profile.tags:
        return ["dispersal", "horizontal_strata", "vertical_rhythm", "radial_concentric"]
    if "space" in profile.tags or "presence" in profile.tags:
        return ["edge_retreat", "one_sided_focus", "horizontal_strata", "central_stillness"]
    if "water" in profile.tags or "soft" in profile.tags:
        return ["horizontal_strata", "radial_concentric", "edge_retreat", "dispersal"]
    return ["diagonal_band", "vertical_rhythm", "horizontal_strata", "radial_concentric", "one_sided_focus", "central_stillness", "edge_retreat", "dispersal"]


def _composition_family(profile: _FilterProfile, text: str, *, lang: str) -> str:
    pool = _composition_pool(profile)
    return pool[_seed(text, f"{lang}-composition-family") % len(pool)]


def _rewrite_by_map(items: list[str], replacements: tuple[tuple[str, str], ...]) -> list[str]:
    result: list[str] = []
    for item in items:
        changed = item
        for before, after in replacements:
            changed = changed.replace(before, after)
        result.append(changed)
    return result


def _apply_composition_family_ja(
    items: list[str], *, profile: _FilterProfile, text: str, family: str | None = None
) -> list[str]:
    family = family or _composition_family(profile, text, lang="ja")
    maps: dict[str, tuple[tuple[str, str], ...]] = {
        "vertical_rhythm": (("右半分の斜めの帯", "上から下への縦の帯"), ("左下から右上へ", "上から下へ"), ("右上の焦点", "上端寄りの焦点"), ("左下の焦点", "上端寄りの焦点")),
        "horizontal_strata": (("右半分の斜めの帯", "左から右への横の帯"), ("左下から右上へ", "左から右へ"), ("右上の焦点", "右半分の焦点"), ("左下の焦点", "右半分の焦点")),
        "radial_concentric": (("右半分の斜めの帯", "右下の焦点から放射状に"), ("左下から右上へ", "右下の焦点から外へ"), ("左下の焦点", "右下の焦点")),
        "one_sided_focus": (("左下の焦点", "右半分の焦点"), ("上端寄りの焦点", "右半分の焦点")),
        "central_stillness": (("右半分の斜めの帯", "中央静止の周囲に"), ("左下から右上へ", "中央静止の周囲へ"), ("右上の焦点", "中央静止の周囲"), ("左下の焦点", "中央静止の周囲")),
        "edge_retreat": (("右半分の斜めの帯", "上端寄りに"), ("左下から右上へ", "上端寄りへ"), ("右上の焦点", "上端寄りの焦点"), ("左下の焦点", "上端寄りの焦点")),
        "dispersal": (("右半分の斜めの帯", "画面全体に点々と"), ("左下から右上へ", "画面全体へ")),
    }
    return _rewrite_by_map(items, maps.get(family, ()))


def _apply_composition_family_en(
    items: list[str], *, profile: _FilterProfile, text: str, family: str | None = None
) -> list[str]:
    family = family or _composition_family(profile, text, lang="en")
    maps: dict[str, tuple[tuple[str, str], ...]] = {
        "vertical_rhythm": (("along a diagonal band in the right half", "from top to bottom in a vertical band"), ("from lower left to upper right", "from top to bottom"), ("upper-right focus", "upper-edge focus"), ("lower-left focus", "upper-edge focus")),
        "horizontal_strata": (("along a diagonal band in the right half", "left to right in horizontal strata"), ("from lower left to upper right", "left to right"), ("upper-right focus", "right-half focus"), ("lower-left focus", "right-half focus")),
        "radial_concentric": (("along a diagonal band in the right half", "radiating from a lower-right focus"), ("from lower left to upper right", "outward from a lower-right focus"), ("lower-left focus", "lower-right focus")),
        "one_sided_focus": (("lower-left focus", "right-half focus"), ("upper-edge focus", "right-half focus")),
        "central_stillness": (("along a diagonal band in the right half", "around a central stillness"), ("from lower left to upper right", "around a central stillness"), ("upper-right focus", "central stillness"), ("lower-left focus", "central stillness")),
        "edge_retreat": (("along a diagonal band in the right half", "near the upper edge"), ("from lower left to upper right", "toward the upper edge"), ("upper-right focus", "upper-edge focus"), ("lower-left focus", "upper-edge focus")),
        "dispersal": (("along a diagonal band in the right half", "dotted across the whole canvas"), ("from lower left to upper right", "across the whole canvas")),
    }
    return _rewrite_by_map(items, maps.get(family, ()))


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

_JA_TOUCHES = ("鉛筆の", "ペンの", "細筆の", "クレヨンの", "ロットリングの")
_EN_TOUCHES = ("pencil", "pen", "fine-brush", "crayon", "rotring")
_TOUCH_SHORT_JA = {
    "鉛筆の": "鉛筆",
    "ペンの": "ペン",
    "細筆の": "細筆",
    "クレヨンの": "クレヨン",
    "ロットリングの": "ロットリング",
}

_COMPOSITION_SHORT_JA = {
    "vertical_rhythm": "縦のリズム",
    "horizontal_strata": "横の層",
    "radial_concentric": "放射",
    "one_sided_focus": "片寄せ",
    "central_stillness": "中央静止",
    "edge_retreat": "端への退き",
    "dispersal": "分散",
    "diagonal_band": "斜めの帯",
}
_COMPOSITION_SHORT_EN = {
    "vertical_rhythm": "vertical rhythm",
    "horizontal_strata": "horizontal strata",
    "radial_concentric": "radial",
    "one_sided_focus": "one-sided focus",
    "central_stillness": "central stillness",
    "edge_retreat": "edge retreat",
    "dispersal": "dispersal",
    "diagonal_band": "diagonal band",
}

_CATEGORY_SHORT_JA = ("構造", "音楽", "絵画")
_CATEGORY_SHORT_EN = ("structure", "music", "painting")


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


def _dominant_ja_color(ddl: str) -> str:
    body = re.sub(r"背景を[^\u3002。]*。?", "", ddl)
    for color in _JA_COLORS:
        if color in body:
            return _JA_COLOR_WORD[color]
    if _has_any(body, ("春", "桜", "花", "蕾", "夕", "温", "陽光", "祝", "祭")):
        return "赤い"
    if _has_any(body, ("森", "葉", "草", "香", "匂", "畑", "苔")):
        return "緑の"
    if _has_any(body, ("夜", "月", "水", "雨", "霧", "冷", "海", "空")):
        return "青い"
    return "黒い"


def _contrast_ja_color(ddl: str) -> str:
    if "背景を黒" in ddl or "暗い背景" in ddl:
        return "白い"
    if _has_any(ddl, ("春", "桜", "花", "蕾", "温", "陽光")):
        return "緑の"
    if _has_any(ddl, ("夜", "月", "水", "雨", "霧", "冷")):
        return "白い"
    return "黒い"


def _dominant_en_color(ddl: str) -> str:
    body = re.sub(r"Fill background with \w+\.?", "", ddl, flags=re.IGNORECASE)
    lower = body.lower()
    for color in _EN_COLORS:
        if color in lower:
            return color
    if _has_any(lower, ("spring", "cherry", "flower", "bud", "sunset", "warm", "sunlight", "festival")):
        return "red"
    if _has_en_terms(lower, ("forest", "leaf", "grass", "scent", "fragrance", "field", "moss")):
        return "green"
    if _has_any(lower, ("night", "moon", "water", "rain", "mist", "cold", "sea", "sky")):
        return "blue"
    return "black"


def _contrast_en_color(ddl: str) -> str:
    lower = ddl.lower()
    if "fill background with black" in lower:
        return "white"
    if _has_any(lower, ("spring", "cherry", "flower", "bud", "warm", "sunlight")):
        return "green"
    if _has_any(lower, ("night", "moon", "water", "rain", "mist", "cold")):
        return "white"
    return "black"


def _vary_context(text: str, vary_seed: int | None) -> str:
    if vary_seed is None:
        return text
    return f"{text}#vary{int(vary_seed)}"


def _cap_category_plan(plan: tuple[int, int, int], tenkei: str) -> tuple[int, int, int]:
    """添景水準による候補数の決定的な縮約 (v1.96)。

    none はプール追加なし。sparse は合計 1 文まで（構造 > 音楽 > 絵画の優先で
    最初の非ゼロカテゴリを 1 に縮約）。auto は現行のまま。
    """
    if tenkei == "none":
        return (0, 0, 0)
    if tenkei != "sparse":
        return plan
    structural, music, painting = plan
    if structural:
        return (1, 0, 0)
    if music:
        return (0, 1, 0)
    if painting:
        return (0, 0, 1)
    return plan


# ---------------------------------------------------------------------------
# Stage 1.5 変奏 (v2.0)
#
# 変奏は「楽譜の変奏」であり決定的である。(amplitude, seed) が同じなら展開結果は
# 常に同一になる。Renderer 層の「揺らぎ」(演奏・非決定的) とは層も語も分ける。
# ---------------------------------------------------------------------------

VARIATION_AMPLITUDES = ("small", "medium", "large")

AXIS_TYPE_SWAP = "type_swap"  # 型の差し替え (同じ系統の中で別の型を選ぶ)
AXIS_COUNT = "count"  # 採用本数 ±1
AXIS_TOUCH = "touch"  # タッチ材質
AXIS_FOCUS = "focus"  # 焦点
AXIS_COLOR = "color"  # 主色・対比色
AXIS_COMPOSITION = "composition"  # 構図族
AXIS_TYPE_FAMILY = "type_family"  # 型の系統 (構造・音楽・絵画の配分)

VARIATION_AXES = (
    AXIS_TYPE_SWAP,
    AXIS_COUNT,
    AXIS_TOUCH,
    AXIS_FOCUS,
    AXIS_COLOR,
    AXIS_COMPOSITION,
    AXIS_TYPE_FAMILY,
)

# 重い軸ほど高い強度でしか解放されない。小では絵の骨格 (構図族・焦点) は動かない。
_AXIS_TIER = {
    AXIS_TYPE_SWAP: 1,
    AXIS_COUNT: 1,
    AXIS_TOUCH: 2,
    AXIS_FOCUS: 2,
    AXIS_COLOR: 2,
    AXIS_COMPOSITION: 3,
    AXIS_TYPE_FAMILY: 3,
}
_AMPLITUDE_RANK = {"small": 1, "medium": 2, "large": 3}
_AMPLITUDE_AXIS_RANGE = {"small": (1, 1), "medium": (1, 2), "large": (2, 4)}


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


def _variation_ranked_axes(amplitude: str, seed: int, tenkei: str) -> list[str]:
    """強度と添景水準が許す軸を、seed が決める優先順に並べる。"""
    if tenkei == "none":
        # ⑤⑥ が停止しているため Tier 1 / Tier 3 の軸は存在しない。強度によらず焦点のみ。
        return [AXIS_FOCUS]
    rank = _AMPLITUDE_RANK[amplitude]
    pool = [axis for axis in VARIATION_AXES if _AXIS_TIER[axis] <= rank]
    key = f"{amplitude}:{int(seed)}"
    return sorted(pool, key=lambda axis: _seed(f"{key}:{axis}", "variation-axis"))


def _variation_base_offset(amplitude: str, seed: int, axis: str) -> int:
    return 1 + _seed(f"{amplitude}:{int(seed)}:{axis}", "variation-offset") % 97


def build_variation_plan(
    amplitude: str | None, seed: int | None, *, tenkei: str = "auto"
) -> VariationPlan | None:
    """(強度, seed) から変奏プランを 1 回だけ決定的に組む。

    どちらかが欠けていれば None を返し、展開は変奏前と完全に一致する。
    未知の強度も None に落とす (focus の `_validated_focus` と同じ防御)。
    """
    if amplitude not in VARIATION_AMPLITUDES or seed is None:
        return None
    ranked = _variation_ranked_axes(amplitude, seed, tenkei)
    low, high = (1, 1) if tenkei == "none" else _AMPLITUDE_AXIS_RANGE[amplitude]
    high = min(high, len(ranked))
    low = min(low, high)
    if high <= 0:
        return None
    key = f"{amplitude}:{int(seed)}"
    count = low + (_seed(key, "variation-count") % (high - low + 1))
    chosen = set(ranked[:count])
    offsets = tuple(
        (axis, _variation_base_offset(amplitude, seed, axis))
        for axis in VARIATION_AXES
        if axis in chosen
    )
    return VariationPlan(amplitude=amplitude, seed=int(seed), offsets=offsets)


# 選んだ軸が既定と同じ出力に落ちたとき、隣のオフセットへ送る試行回数。
_VARIATION_OFFSET_TRIES = 8


def _effective_variation_plan(
    plan: VariationPlan, *, tenkei: str, base_text: str, run: object
) -> VariationPlan | None:
    """「動かした軸は必ず目に見えて動く」を実際の出力で保証する (契約 §3.2)。

    値をずらしても出力に効かない軸がある (例: 採用文が 1 つもタッチ語を含まない
    ときのタッチ材質)。そのような軸は隣のオフセットへ送り、それでも動かなければ
    同じ強度で許された別の軸へ置き換える。解決は決定的なので再現性は保たれる。
    """
    wanted = len(plan.offsets)
    resolved: list[tuple[str, int]] = []
    for axis in _variation_ranked_axes(plan.amplitude, plan.seed, tenkei):
        if len(resolved) >= wanted:
            break
        base_offset = _variation_base_offset(plan.amplitude, plan.seed, axis)
        for step in range(_VARIATION_OFFSET_TRIES):
            offset = base_offset + step
            trial = VariationPlan(
                amplitude=plan.amplitude, seed=plan.seed, offsets=((axis, offset),)
            )
            if run(trial, None) != base_text:  # type: ignore[operator]
                resolved.append((axis, offset))
                break
    if not resolved:
        return None
    # 個々の軸は既定と違っても、組み合わせが既定へ戻ることがある (例: 本数 -1 と
    # 系統移動が打ち消し合う)。その場合は軸を減らす。単独では必ず動くので停止する。
    while len(resolved) > 1:
        ordered = [item for axis in VARIATION_AXES for item in resolved if item[0] == axis]
        combined = VariationPlan(
            amplitude=plan.amplitude, seed=plan.seed, offsets=tuple(ordered)
        )
        if run(combined, None) != base_text:  # type: ignore[operator]
            return combined
        resolved.pop()
    ordered = [item for axis in VARIATION_AXES for item in resolved if item[0] == axis]
    return VariationPlan(
        amplitude=plan.amplitude, seed=plan.seed, offsets=tuple(ordered)
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


def _recap_after_variation(counts: tuple[int, int, int], tenkei: str) -> tuple[int, int, int]:
    """変奏で振った本数へ添景水準の上限を再適用する (cap を越えない)。"""
    if tenkei == "none":
        return (0, 0, 0)
    if tenkei != "sparse":
        return counts
    if sum(counts) <= 1:
        return counts
    for index, value in enumerate(counts):
        if value:
            reduced = [0, 0, 0]
            reduced[index] = 1
            return (reduced[0], reduced[1], reduced[2])
    return counts


def _shift_category_count(
    counts: tuple[int, int, int],
    *,
    offset: int,
    tenkei: str,
    available: tuple[int, int, int],
) -> tuple[int, int, int]:
    """採用本数 ±1。cap 適用後の値に対して振り、cap を越えない (下限 0)。"""
    pool = [index for index in range(3) if counts[index] > 0]
    if not pool:
        pool = [index for index in range(3) if available[index] > 0]
    if not pool:
        return counts
    index = pool[offset % len(pool)]
    delta = 1 if (offset // len(pool)) % 2 == 0 else -1
    shifted = list(counts)
    shifted[index] = max(0, min(available[index], shifted[index] + delta))
    return _recap_after_variation((shifted[0], shifted[1], shifted[2]), tenkei)


def _shift_category_family(
    counts: tuple[int, int, int],
    *,
    offset: int,
    available: tuple[int, int, int],
) -> tuple[int, int, int]:
    """型の系統。合計を保ったまま 1 本を別カテゴリへ移す (cap は自動的に保たれる)。"""
    sources = [index for index in range(3) if counts[index] > 0]
    if not sources:
        return counts
    source = sources[offset % len(sources)]
    targets = [
        index
        for index in range(3)
        if index != source and available[index] > counts[index]
    ]
    if not targets:
        return counts
    target = targets[(offset // len(sources)) % len(targets)]
    shifted = list(counts)
    shifted[source] -= 1
    shifted[target] += 1
    return (shifted[0], shifted[1], shifted[2])


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


def _apply_count_axes(
    counts: tuple[int, int, int],
    *,
    plan: VariationPlan | None,
    tenkei: str,
    profile: _FilterProfile,
    categories: tuple[list[_FilterCandidate], ...],
    decisions: dict | None,
    category_words: tuple[str, str, str],
) -> tuple[int, int, int]:
    """採用本数と型の系統を順に適用する。どちらも実プールの大きさを越えない。"""
    available = tuple(
        len(_category_pool(items, profile=profile)) if items else 0 for items in categories
    )
    if plan is not None:
        family_offset = plan.offset(AXIS_TYPE_FAMILY)
        if family_offset is not None:
            counts = _shift_category_family(
                counts, offset=family_offset, available=available
            )
        count_offset = plan.offset(AXIS_COUNT)
        if count_offset is not None:
            counts = _shift_category_count(
                counts, offset=count_offset, tenkei=tenkei, available=available
            )
    if decisions is not None:
        decisions["category_counts"] = counts
        decisions[AXIS_COUNT] = str(sum(counts))
        decisions[AXIS_TYPE_FAMILY] = [
            category_words[index] for index in range(3) for _ in range(counts[index])
        ]
    return counts


def _selected_labels(
    selected: list[str], categories: tuple[list[_FilterCandidate], ...]
) -> list[str]:
    labels: dict[str, str] = {}
    for items in categories:
        for candidate in items:
            labels[candidate.text] = candidate.label
    return [labels.get(text, "") for text in selected]


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
        if axis == AXIS_TYPE_SWAP and before == after:
            # 順序だけが動いた場合は差集合が空になる。全体を並べて示す。
            before = joiner.join(base_decisions.get(axis) or [])
            after = joiner.join(solo_decisions.get(axis) or [])
        elif axis == AXIS_TYPE_SWAP:
            base_labels = base_decisions.get(axis) or []
            solo_labels = solo_decisions.get(axis) or []
            dropped = [item for item in base_labels if item not in solo_labels]
            gained = [item for item in solo_labels if item not in base_labels]
            if dropped or gained:
                before = joiner.join(dropped) or before
                after = joiner.join(gained) or after
        moved.append({"axis": axis, "from": before, "to": after})
    return moved


def expand_intermediate_ddl(
    ddl: str,
    *,
    lang: str = "ja",
    context_text: str | None = None,
    vary_seed: int | None = None,
    enable_plugins: bool = True,
    plugin_instructions_present: bool = False,
    tenkei: str = "auto",
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
    sanitized = _avoid_gray_background(sanitized, lang=lang)
    sanitized = _apply_nature_plugin_macros(sanitized, lang=lang, enable_plugins=enable_plugins)
    if not sanitized:
        return sanitized
    expander = _expand_en if lang == "en" else _expand_ja

    def run(plan: VariationPlan | None, decisions: dict | None) -> str:
        return expander(
            sanitized,
            context_text=context_text,
            vary_seed=vary_seed,
            plugin_instructions_present=plugin_instructions_present,
            tenkei=tenkei,
            focus=focus,
            plan=plan,
            decisions=decisions,
        )

    plan = build_variation_plan(variation_amplitude, variation_seed, tenkei=tenkei)
    base_decisions: dict = {}
    base_text = run(None, base_decisions)
    if variation_report is not None:
        variation_report["resolved_focus"] = base_decisions.get(AXIS_FOCUS)
        variation_report["moved_axes"] = []
        variation_report["category_counts"] = base_decisions.get(
            "category_counts", (0, 0, 0)
        )
    if plan is not None:
        plan = _effective_variation_plan(
            plan, tenkei=tenkei, base_text=base_text, run=run
        )
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
    vary_seed: int | None = None,
    plugin_instructions_present: bool = False,
    tenkei: str = "auto",
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
    ddl = _reframe_static_center_ja(ddl, focus_id)
    if tenkei == "none":
        return ddl

    sentences = _split_sentences(ddl, lang="ja")
    structural: list[_FilterCandidate] = []
    main_color = _dominant_ja_color(ddl)
    contrast_color = _contrast_ja_color(ddl)
    color_offset = plan.offset(AXIS_COLOR) if plan else None
    if color_offset is not None:
        palette = list(_JA_COLOR_WORD.values())
        main_color = _shift_choice(main_color, palette, color_offset)
        contrast_color = _shift_choice(
            contrast_color, [item for item in palette if item != main_color], color_offset
        )
    if decisions is not None:
        decisions[AXIS_COLOR] = f"{main_color}・{contrast_color}"
    context = f"{context_text or ''}\n{ddl}"
    seed_context = _vary_context(context, vary_seed)
    profile = _profile_ja(context)
    if "geometry" in profile.tags:
        touch = "ロットリングの"
    elif "dense" in profile.tags:
        touch = "クレヨンの"
    elif profile.tags & {"water", "soft", "sensory", "atmosphere"}:
        touch = "細筆の"
    elif "contrast" in profile.tags:
        touch = "ペンの"
    else:
        touch = "鉛筆の"
    touch_offset = plan.offset(AXIS_TOUCH) if plan else None
    if touch_offset is not None:
        touch = _shift_choice(touch, list(_JA_TOUCHES), touch_offset)
    if decisions is not None:
        decisions[AXIS_TOUCH] = _TOUCH_SHORT_JA.get(touch, touch)

    def add(label: str, text: str) -> None:
        structural.append(_FilterCandidate(text, _structural_tags(text), label))

    if any(token in ddl for token in ("円", "点", "粒", "星", "楕円", "四角")):
        add("楕円の帯", f"{main_color}右上がりの小さな楕円を右半分の斜めの帯に三個並べる。横長にする。")
        add("斜めの短線", f"{main_color}{touch}短い線を左下から右上へ三本散らす。細かく震える。")

    if any(token in ddl for token in ("散らす", "点々", "舞", "漂", "雪", "雨")):
        add("波の楕円", f"{main_color}右下がりの小さな楕円を波打つ軌跡に沿って七個散らす。ゆっくり揺れる。")

    if "線" in ddl:
        add("斜線の反復", f"{contrast_color}{touch}細い斜め線を右上がりに三本並べる。細かく震える。")

    if any(token in ddl for token in ("弧", "円", "波", "水", "月", "中心")):
        add("広がる弧", f"{contrast_color}{touch}細い弧を左下の焦点から三つ広げる。半径は0.11。")
    roof_pressure_context = any(token in context for token in ("低い雲", "押し沈", "屋根"))
    if any(token in context for token in ("山", "尖", "針葉樹", "頂", "鋭")):
        add("尖りの三角", f"{main_color}細い三角を上端寄りの焦点に二つ置く。少し傾ける。")
    if any(token in context for token in ("葉", "花びら", "羽", "紙片", "破片", "舟")):
        add("葉片", f"{main_color}細い右上がりの楕円を葉片として波打つ軌跡に沿って五個散らす。")
    if not roof_pressure_context and any(token in context for token in ("扉", "窓", "箱", "街", "部屋", "格子")):
        add("余白の切片", f"{contrast_color}回転した細い四角を余白の切片として右半分に三つ散らす。")
    if roof_pressure_context:
        add("低い重さ", f"{contrast_color}{touch}薄い斜め線を上端から下へ三本置く。低い重さとしてゆっくり揺れる。")
    if any(token in context for token in ("膜", "透明", "霞", "霧", "靄", "気配", "余韻")):
        add("透明な膜", f"{main_color}薄い水彩の楕円を透明な膜として右半分に三つ重ねる。境界が滲む。")
    if any(token in context for token in ("反射", "映り")):
        add("反射の線", f"{contrast_color}{touch}薄い反射の線を波打つ軌跡に沿って五本散らす。ゆっくり揺れる。")
    if any(token in context for token in ("消え", "薄れ", "遠ざか")):
        add("消える線", f"{contrast_color}{touch}消える線を左下から右上へ五本散らす。細かく震える。")
    if any(token in context for token in ("陽光", "光", "日差し", "温", "柔ら")):
        add("柔らかな光", "白い薄い水彩の横長の楕円を柔らかな光として上端寄りに三つ重ねる。境界が滲む。")
    if any(token in context for token in ("香", "匂", "沈丁花")):
        add("香りの層", "緑の小さな楕円を香りの層として波打つ軌跡に沿って七個散らす。ゆっくり揺れる。")
    if any(token in context for token in ("蕾", "つぼみ", "開花", "春")):
        add("蕾", "赤い右上がりの小さな楕円を開花を待つ蕾として右半分の斜めの帯に五個散らす。")
    if any(token in context for token in ("五感", "気配", "訪れ")):
        add("五感の気配", "白い細筆の薄い弧を五感の気配として左下の焦点から三つ広げる。半径は0.14。")
    if any(token in context for token in ("人", "人物", "村人", "老人", "顔", "視線", "動物", "鳥", "魚", "熊", "群れ")):
        add("存在の重心", f"{contrast_color}{touch}細い余白線を存在の重心として右上の焦点へ二本引く。細かく震える。")
        add("輪郭の密度", f"{main_color}{touch}薄い弧を輪郭の密度として左下の焦点から二つ置く。半径は0.09。")

    music = [
        _FilterCandidate(f"{contrast_color}{touch}細い線を前の線を切るように二本置く。細かく震える。", frozenset(("line", "music", "contrast")), "対位法"),
        _FilterCandidate(f"{contrast_color}{touch}細い弧を倍音列として右下の焦点から三つ並べる。半径は0.07。", frozenset(("music", "water", "soft")), "倍音列"),
        _FilterCandidate(f"{main_color}{touch}短い線を前の線に沿って左から右へ四本並べる。ゆっくり揺れる。", frozenset(("particle", "music", "line")), "輪唱"),
    ]
    painting = [
        _FilterCandidate(f"{contrast_color}{touch}細い線を前の線に沿って右上の焦点へ三本引く。", frozenset(("space", "line", "geometry")), "一点透視"),
        _FilterCandidate(f"{contrast_color}{touch}細い横線を遠近法の奥行きとして上へ細かく三本並べる。", frozenset(("space", "line")), "遠近法"),
        _FilterCandidate("黒い細筆の細い線を素描の下線として左から右へ三本並べる。細かく震える。", frozenset(("line", "quiet")), "素描"),
        _FilterCandidate(f"{contrast_color}鉛筆の細い線を余白線として上端寄りに二本並べる。細かく震える。", frozenset(("line", "quiet", "soft")), "鉛筆の余白線"),
        _FilterCandidate(f"{main_color}クレヨンの短い線を擦れとして右半分の斜めの帯に七本散らす。", frozenset(("particle", "dense", "soft")), "クレヨンの擦れ"),
        _FilterCandidate(f"{contrast_color}ロットリングの細い線を均一線として左から右へ五本並べる。", frozenset(("line", "geometry", "contrast")), "ロットリング"),
        _FilterCandidate(f"{main_color}回転した小さな四角を前の形に触れないように右半分の斜めの帯に十三個散らす。", frozenset(("particle", "dense", "geometry")), "点描の四角"),
        _FilterCandidate(f"{main_color}太筆の短い線を油絵の厚塗りとして横に三本並べる。", frozenset(("dense", "contrast")), "油絵"),
        _FilterCandidate(f"{contrast_color}薄い水彩の楕円を左上に二つ重ねる。境界が滲む。", frozenset(("water", "soft", "quiet")), "水彩"),
        _FilterCandidate("赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に六個並べる。", frozenset(("geometry", "dense")), "パッチワーク"),
        _FilterCandidate(f"{contrast_color}チョークの横線をフレスコの下地として画面下に三本並べる。境界が滲む。", frozenset(("space", "line", "soft")), "フレスコ"),
        _FilterCandidate("黒い細筆の縦線を水墨の濃淡として左から右へ三本並べる。境界が滲む。", frozenset(("water", "contrast", "quiet")), "水墨"),
        _FilterCandidate("白い薄い水彩の楕円を五感の気配として右上に二つ重ねる。境界が滲む。", frozenset(("sensory", "soft", "quiet")), "五感の水彩"),
    ]
    structural_candidates = structural
    counts = _cap_category_plan(
        _category_plan(profile, has_structural=bool(structural_candidates)), tenkei
    )
    counts = _apply_count_axes(
        counts,
        plan=plan,
        tenkei=tenkei,
        profile=profile,
        categories=(structural_candidates, music, painting),
        decisions=decisions,
        category_words=_CATEGORY_SHORT_JA,
    )
    structural_count, music_count, painting_count = counts

    swap_offset = plan.offset(AXIS_TYPE_SWAP) if plan else None
    selected = (
        _select_category(structural_candidates, structural_count, profile=profile, text=seed_context, salt=_mode_salt(profile, "ja-structure"), swap_offset=swap_offset)
        + _select_category(music, music_count, profile=profile, text=seed_context, salt=_mode_salt(profile, "ja-music"), swap_offset=swap_offset)
        + _select_category(painting, painting_count, profile=profile, text=seed_context, salt=_mode_salt(profile, "ja-painting"), swap_offset=swap_offset)
    )
    if decisions is not None:
        decisions[AXIS_TYPE_SWAP] = _selected_labels(
            selected, (structural_candidates, music, painting)
        )
    selected = _limit_centered(selected, centered_tokens=("中心", "中央", "放射状", "同心円状"))
    family = _composition_family(profile, seed_context, lang="ja")
    family_offset = plan.offset(AXIS_COMPOSITION) if plan else None
    if family_offset is not None:
        family = _shift_choice(family, _composition_pool(profile), family_offset)
    if decisions is not None:
        decisions[AXIS_COMPOSITION] = _COMPOSITION_SHORT_JA.get(family, family)
    selected = _apply_composition_family_ja(
        selected, profile=profile, text=seed_context, family=family
    )

    return _join_sentences(sentences + selected, lang="ja")


def _expand_en(
    ddl: str,
    *,
    context_text: str | None = None,
    vary_seed: int | None = None,
    plugin_instructions_present: bool = False,
    tenkei: str = "auto",
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
    ddl = _reframe_static_center_en(ddl, focus_id)
    if tenkei == "none":
        return ddl
    lower = ddl.lower()

    sentences = _split_sentences(ddl, lang="en")
    structural: list[_FilterCandidate] = []
    main_color = _dominant_en_color(ddl)
    contrast_color = _contrast_en_color(ddl)
    color_offset = plan.offset(AXIS_COLOR) if plan else None
    if color_offset is not None:
        palette = list(_EN_COLORS)
        main_color = _shift_choice(main_color, palette, color_offset)
        contrast_color = _shift_choice(
            contrast_color, [item for item in palette if item != main_color], color_offset
        )
    if decisions is not None:
        decisions[AXIS_COLOR] = f"{main_color}/{contrast_color}"
    context = f"{context_text or ''}\n{ddl}"
    seed_context = _vary_context(context, vary_seed)
    profile = _profile_en(context)
    if "geometry" in profile.tags:
        touch = "rotring"
    elif "dense" in profile.tags:
        touch = "crayon"
    elif profile.tags & {"water", "soft", "sensory", "atmosphere"}:
        touch = "fine-brush"
    elif "contrast" in profile.tags:
        touch = "pen"
    else:
        touch = "pencil"
    touch_offset = plan.offset(AXIS_TOUCH) if plan else None
    if touch_offset is not None:
        touch = _shift_choice(touch, list(_EN_TOUCHES), touch_offset)
    if decisions is not None:
        decisions[AXIS_TOUCH] = touch

    def add(label: str, text: str) -> None:
        structural.append(_FilterCandidate(text, _structural_tags(text), label))

    if any(token in lower for token in ("circle", "dot", "particle", "star", "ellipse", "square")):
        add("ellipse band", f"Line up three small {main_color} ellipses rising to the right along a diagonal band in the right half. Make them wide.")
        add("diagonal strokes", f"Scatter three short {main_color} {touch} lines from lower left to upper right. Fine trembling.")

    if any(token in lower for token in ("scatter", "dotted", "drift", "snow", "rain")):
        add(
            "wave ellipses",
            f"Scatter seven small {main_color} ellipses falling to the right along an undulating trace. Swaying slowly.",
        )

    if "line" in lower:
        add("diagonal repetition", f"Line up three thin {contrast_color} {touch} diagonal lines rising to the right. Fine trembling.")

    if any(token in lower for token in ("arc", "circle", "wave", "water", "moon", "center")):
        add("spreading arcs", f"Line up three thin {contrast_color} {touch} arcs spreading from a lower-left focus. Radius 0.11.")
    roof_pressure_context = any(token in context.lower() for token in ("low cloud", "pressing down", "roof"))
    if any(token in context.lower() for token in ("mountain", "sharp", "pine", "peak", "needle")):
        add("sharp triangles", f"Place two thin {main_color} triangles near the upper-edge focus. Tilt them slightly.")
    if any(token in context.lower() for token in ("leaf", "petal", "feather", "paper", "fragment", "boat")):
        add("leaf pieces", f"Scatter five thin {main_color} ellipses rising to the right along an undulating trace as leaf-like pieces.")
    if not roof_pressure_context and any(token in context.lower() for token in ("door", "window", "box", "city", "room", "grid")):
        add("visual cuts", f"Scatter three thin rotated {contrast_color} squares in the right half as visual cuts.")
    if roof_pressure_context:
        add("overhead weight", f"Place three pale {contrast_color} {touch} diagonal lines from the upper edge downward as slow overhead weight.")
    if any(token in context.lower() for token in ("membrane", "transparent", "haze", "fog", "mist", "atmosphere", "presence")):
        add("transparent membrane", f"Layer three pale {main_color} watercolor ellipses in the right half as a transparent membrane. Edges blurring.")
    if any(token in context.lower() for token in ("reflection", "reflected")):
        add("reflection lines", f"Scatter five thin {contrast_color} {touch} faint reflection lines along an undulating trace. Swaying slowly.")
    if any(token in context.lower() for token in ("fade", "fading", "vanish", "dissolve")):
        add("fading lines", f"Scatter five thin {contrast_color} {touch} fading lines from lower left to upper right. Fine trembling.")
    if any(token in context.lower() for token in ("sunlight", "light", "warm", "soft")):
        add("soft light", "Layer three pale white watercolor ellipses near the upper edge as soft light. Edges blurring.")
    if _has_en_terms(context.lower(), ("scent", "fragrance")):
        add("scent layer", "Scatter seven small green ellipses along an undulating trace as a scent layer. Swaying slowly.")
    if any(token in context.lower() for token in ("spring", "bud", "bloom", "waiting")):
        add("waiting buds", "Scatter five small red ellipses rising to the right along a diagonal band in the right half as waiting buds.")
    if any(token in context.lower() for token in ("sense", "presence", "arrival")):
        add("five-sense presence", "Line up three pale white fine-brush arcs from a lower-left focus as five-sense presence. Radius 0.14.")
    if any(token in context.lower() for token in ("human", "person", "people", "figure", "face", "gaze", "animal", "bird", "fish", "bear", "flock", "herd")):
        add("presence weight", f"Draw two thin {contrast_color} {touch} negative-space lines toward an upper-right focus as presence weight. Fine trembling.")
        add("contour density", f"Place two pale {main_color} {touch} arcs from a lower-left focus as contour density. Radius 0.09.")

    music = [
        _FilterCandidate(f"Place two thin {contrast_color} {touch} lines cutting the previous line. Fine trembling.", frozenset(("line", "music", "contrast")), "counterpoint"),
        _FilterCandidate(f"Line up three thin {contrast_color} {touch} arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.", frozenset(("music", "water", "soft")), "overtone series"),
        _FilterCandidate(f"Line up four short {main_color} {touch} lines left to right along the previous line. Swaying slowly.", frozenset(("particle", "music", "line")), "canon"),
    ]
    painting = [
        _FilterCandidate(f"Draw three thin {contrast_color} {touch} lines toward an upper-right focus along the previous line.", frozenset(("space", "line", "geometry")), "one-point perspective"),
        _FilterCandidate(f"Line up three thin {contrast_color} {touch} horizontal lines upward as perspective depth.", frozenset(("space", "line")), "perspective depth"),
        _FilterCandidate("Line up three thin black fine-brush lines left to right as drawing underlines. Fine trembling.", frozenset(("line", "quiet")), "drawing underline"),
        _FilterCandidate(f"Line up two thin {contrast_color} pencil lines near the top edge as pencil negative-space line. Fine trembling.", frozenset(("line", "quiet", "soft")), "pencil negative space"),
        _FilterCandidate(f"Scatter seven short {main_color} crayon lines along a diagonal band in the right half as crayon rubbing.", frozenset(("particle", "dense", "soft")), "crayon rubbing"),
        _FilterCandidate(f"Line up five thin {contrast_color} rotring uniform lines left to right.", frozenset(("line", "geometry", "contrast")), "rotring uniform"),
        _FilterCandidate(f"Scatter thirteen small rotated {main_color} squares not touching the previous shape along a diagonal band in the right half.", frozenset(("particle", "dense", "geometry")), "pointillist squares"),
        _FilterCandidate(f"Line up three short {main_color} thick-brush lines horizontally as oil impasto.", frozenset(("dense", "contrast")), "oil impasto"),
        _FilterCandidate("Layer two pale watercolor ellipses in the upper left. Edges blurring.", frozenset(("water", "soft", "quiet")), "watercolor"),
        _FilterCandidate("Line up six small rotated squares in red, blue, green, gray as patchwork grid.", frozenset(("geometry", "dense")), "patchwork"),
        _FilterCandidate(f"Line up three {contrast_color} chalk horizontal lines at the bottom as fresco ground. Edges blurring.", frozenset(("space", "line", "soft")), "fresco"),
        _FilterCandidate("Line up three black fine-brush vertical lines left to right as ink-wash value. Edges blurring.", frozenset(("water", "contrast", "quiet")), "ink wash"),
        _FilterCandidate("Layer two pale white watercolor ellipses in the upper right as five-sense presence. Edges blurring.", frozenset(("sensory", "soft", "quiet")), "five-sense watercolor"),
    ]
    structural_candidates = structural
    counts = _cap_category_plan(
        _category_plan(profile, has_structural=bool(structural_candidates)), tenkei
    )
    counts = _apply_count_axes(
        counts,
        plan=plan,
        tenkei=tenkei,
        profile=profile,
        categories=(structural_candidates, music, painting),
        decisions=decisions,
        category_words=_CATEGORY_SHORT_EN,
    )
    structural_count, music_count, painting_count = counts

    swap_offset = plan.offset(AXIS_TYPE_SWAP) if plan else None
    selected = (
        _select_category(structural_candidates, structural_count, profile=profile, text=seed_context, salt=_mode_salt(profile, "en-structure"), swap_offset=swap_offset)
        + _select_category(music, music_count, profile=profile, text=seed_context, salt=_mode_salt(profile, "en-music"), swap_offset=swap_offset)
        + _select_category(painting, painting_count, profile=profile, text=seed_context, salt=_mode_salt(profile, "en-painting"), swap_offset=swap_offset)
    )
    if decisions is not None:
        decisions[AXIS_TYPE_SWAP] = _selected_labels(
            selected, (structural_candidates, music, painting)
        )
    selected = _limit_centered(
        selected,
        centered_tokens=("center", "radial", "concentric"),
    )
    family = _composition_family(profile, seed_context, lang="en")
    family_offset = plan.offset(AXIS_COMPOSITION) if plan else None
    if family_offset is not None:
        family = _shift_choice(family, _composition_pool(profile), family_offset)
    if decisions is not None:
        decisions[AXIS_COMPOSITION] = _COMPOSITION_SHORT_EN.get(family, family)
    selected = _apply_composition_family_en(
        selected, profile=profile, text=seed_context, family=family
    )

    return _join_sentences(sentences + selected, lang="en")
