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
)


def _split_sentences(text: str, *, lang: str) -> list[str]:
    if lang == "en":
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return [s.strip() for s in re.split(r"(?<=。)", text.strip()) if s.strip()]


def _join_sentences(sentences: list[str], *, lang: str) -> str:
    if lang == "en":
        return " ".join(s if s.endswith((".", "!", "?")) else f"{s}." for s in sentences)
    return "".join(s if s.endswith("。") else f"{s}。" for s in sentences)


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


@dataclass(frozen=True)
class _FilterCandidate:
    text: str
    tags: frozenset[str]


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _profile_ja(text: str) -> _FilterProfile:
    tags: set[str] = set()
    intensity = 2

    if _has_any(text, ("余白", "静か", "一滴", "一本", "ひとつ", "孤独", "ぽつん", "霧", "淡", "薄い")):
        intensity = 1
        tags.update(("quiet", "space"))
    if _has_any(text, ("満天", "無数", "密集", "びっしり", "埋め尽く", "嵐", "群れ", "祭", "都市", "複雑")):
        intensity = 3
        tags.add("dense")

    if _has_any(text, ("円", "粒", "星", "雪", "雨", "砂", "花びら", "散らす", "点々")):
        tags.add("particle")
    if _has_any(text, ("線", "糸", "水平", "垂直", "縦", "横", "斜め")):
        tags.add("line")
    if _has_any(text, ("水", "波", "月", "霧", "滲", "淡", "雲")):
        tags.update(("water", "soft"))
    if _has_any(text, ("音", "リズム", "歌", "輪唱", "響", "反復", "揺", "舞", "流")):
        tags.add("music")
    if _has_any(text, ("建物", "都市", "寺", "古刹", "部屋", "道", "遠く", "奥", "畑")):
        tags.add("space")
    if _has_any(text, ("黒", "白", "影", "明暗", "暗", "光", "灰")):
        tags.add("contrast")
    if _has_any(text, ("四角", "格子", "幾何", "均衡", "法則", "対称")):
        tags.add("geometry")

    return _FilterProfile(intensity=intensity, tags=frozenset(tags))


def _profile_en(text: str) -> _FilterProfile:
    lower = text.lower()
    tags: set[str] = set()
    intensity = 2

    if _has_any(lower, ("empty space", "quiet", "single", "one ", "alone", "solitary", "mist", "pale")):
        intensity = 1
        tags.update(("quiet", "space"))
    if _has_any(lower, ("starry", "countless", "dense", "packed", "fill", "storm", "crowd", "city", "complex")):
        intensity = 3
        tags.add("dense")

    if _has_any(lower, ("circle", "dot", "particle", "star", "snow", "rain", "sand", "petal", "scatter", "dotted")):
        tags.add("particle")
    if _has_any(lower, ("line", "thread", "horizontal", "vertical", "diagonal")):
        tags.add("line")
    if _has_any(lower, ("water", "wave", "moon", "mist", "blur", "pale", "cloud")):
        tags.update(("water", "soft"))
    if _has_any(lower, ("sound", "rhythm", "song", "canon", "echo", "repeat", "sway", "drift")):
        tags.add("music")
    if _has_any(lower, ("building", "city", "temple", "room", "road", "distant", "depth", "field")):
        tags.add("space")
    if _has_any(lower, ("black", "white", "shadow", "value", "dark", "light", "gray")):
        tags.add("contrast")
    if _has_any(lower, ("square", "grid", "geometric", "balance", "law", "symmetry")):
        tags.add("geometry")

    return _FilterProfile(intensity=intensity, tags=frozenset(tags))


def _select_category(
    candidates: list[_FilterCandidate],
    count: int,
    *,
    profile: _FilterProfile,
    text: str,
    salt: str,
) -> list[str]:
    if count <= 0:
        return []

    if profile.intensity <= 1:
        matched = [c for c in candidates if c.tags & {"quiet", "soft", "water"}]
    else:
        matched = [c for c in candidates if c.tags & profile.tags]
    pool = matched or candidates
    return _pick([c.text for c in pool], count, text=text, salt=salt)


def _category_plan(profile: _FilterProfile, *, has_structural: bool) -> tuple[int, int, int]:
    if profile.intensity <= 1:
        return (0, 0, 0)

    if profile.intensity >= 3:
        return (
            1 if has_structural else 0,
            1 if "music" in profile.tags else 0,
            1 if profile.tags & {"geometry", "space", "water"} else 0,
        )

    if "music" in profile.tags:
        return (1 if has_structural else 0, 1, 0)
    if profile.tags & {"geometry", "space"}:
        return (1 if has_structural else 0, 0, 1)
    return (1 if has_structural else 0, 0, 0)


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


def _dynamic_focus_ja(text: str) -> str:
    focuses = (
        "右上の焦点",
        "左上の焦点",
        "右下の焦点",
        "左下の焦点",
        "上端寄りの焦点",
        "右半分の焦点",
    )
    return focuses[_seed(text, "ja-focus") % len(focuses)]


def _dynamic_focus_en(text: str) -> str:
    focuses = (
        "upper-right focus",
        "upper-left focus",
        "lower-right focus",
        "lower-left focus",
        "upper-edge focus",
        "right-half focus",
    )
    return focuses[_seed(text, "en-focus") % len(focuses)]


def _reframe_static_center_ja(ddl: str) -> str:
    focus = _dynamic_focus_ja(ddl)
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


def _reframe_static_center_en(ddl: str) -> str:
    focus = _dynamic_focus_en(ddl)
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
    return "黒い"


def _contrast_ja_color(ddl: str) -> str:
    if "背景を黒" in ddl or "暗い背景" in ddl:
        return "白い"
    return "黒い"


def _dominant_en_color(ddl: str) -> str:
    body = re.sub(r"Fill background with \w+\.?", "", ddl, flags=re.IGNORECASE)
    lower = body.lower()
    for color in _EN_COLORS:
        if color in lower:
            return color
    return "black"


def _contrast_en_color(ddl: str) -> str:
    lower = ddl.lower()
    if "fill background with black" in lower:
        return "white"
    return "black"


def expand_intermediate_ddl(ddl: str, *, lang: str = "ja", context_text: str | None = None) -> str:
    """Add controlled complexity to normalized DDL before Stage 2.

    The filter favors visible mathematical structure over vague randomness:
    golden-ratio accents, rule-of-thirds anchors, silver-ratio counterpoints,
    Fibonacci-friendly counts, radial echoes, diagonal counter-lines,
    harmonic overtones, contrapuntal contrary motion, canon-like repetitions,
    painterly material techniques, perspective guides, value structure, and
    motion-derived wave traces.
    """

    sanitized = _sanitize_placement_words(ddl).strip()
    sanitized = _avoid_gray_background(sanitized, lang=lang)
    if not sanitized:
        return sanitized
    if lang == "en":
        return _expand_en(sanitized, context_text=context_text)
    return _expand_ja(sanitized, context_text=context_text)


def _expand_ja(ddl: str, *, context_text: str | None = None) -> str:
    if any(marker in ddl for marker in _JA_EXPANSION_MARKERS):
        return ddl
    ddl = _reframe_static_center_ja(ddl)

    sentences = _split_sentences(ddl, lang="ja")
    structural: list[str] = []
    main_color = _dominant_ja_color(ddl)
    contrast_color = _contrast_ja_color(ddl)
    context = f"{context_text or ''}\n{ddl}"
    profile = _profile_ja(context)

    if any(token in ddl for token in ("円", "点", "粒", "星", "楕円", "四角")):
        structural.append(f"{main_color}右上がりの小さな楕円を右半分の斜めの帯に三個並べる。横長にする。")
        structural.append(f"{main_color}短い線を左下から右上へ八本散らす。細かく震える。")

    if any(token in ddl for token in ("散らす", "点々", "舞", "漂", "雪", "雨")):
        structural.append(f"{main_color}右下がりの小さな楕円を波打つ軌跡に沿って十三個散らす。ゆっくり揺れる。")

    if "線" in ddl:
        structural.append(f"{contrast_color}細い斜め線を右上がりに三本並べる。細かく震える。")

    if any(token in ddl for token in ("弧", "円", "波", "水", "月", "中心")):
        structural.append(f"{contrast_color}細い弧を左下の焦点から三つ広げる。半径は0.11。")

    music = [
        _FilterCandidate(f"{contrast_color}細い線を対位法の反行として右下がりに二本並べる。細かく震える。", frozenset(("line", "music", "contrast"))),
        _FilterCandidate(f"{contrast_color}細い弧を倍音列として右下の焦点から三つ並べる。半径は0.07。", frozenset(("music", "water", "soft"))),
        _FilterCandidate(f"{main_color}短い線を輪唱のずれとして左から右へ四本並べる。ゆっくり揺れる。", frozenset(("particle", "music", "line"))),
    ]
    painting = [
        _FilterCandidate(f"{contrast_color}細い線を一点透視法として右上の焦点へ向けて三本引く。", frozenset(("space", "line", "geometry"))),
        _FilterCandidate(f"{contrast_color}細い横線を遠近法の奥行きとして上へ細かく三本並べる。", frozenset(("space", "line"))),
        _FilterCandidate("黒い細筆の細い線を素描の下線として左から右へ三本並べる。細かく震える。", frozenset(("line", "quiet"))),
        _FilterCandidate(f"{main_color}回転した小さな四角を点描として右半分の斜めの帯に十三個散らす。", frozenset(("particle", "dense", "geometry"))),
        _FilterCandidate(f"{main_color}太筆の短い線を油絵の厚塗りとして横に三本並べる。", frozenset(("dense", "contrast"))),
        _FilterCandidate(f"{contrast_color}薄い水彩の楕円を左上に二つ重ねる。境界が滲む。", frozenset(("water", "soft", "quiet"))),
        _FilterCandidate("赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に六個並べる。", frozenset(("geometry", "dense"))),
        _FilterCandidate(f"{contrast_color}チョークの横線をフレスコの下地として画面下に三本並べる。境界が滲む。", frozenset(("space", "line", "soft"))),
        _FilterCandidate("黒い細筆の縦線を水墨の濃淡として左から右へ三本並べる。境界が滲む。", frozenset(("water", "contrast", "quiet"))),
    ]
    structural_candidates = [_FilterCandidate(text, frozenset(("particle", "line", "water", "space"))) for text in structural]
    structural_count, music_count, painting_count = _category_plan(profile, has_structural=bool(structural_candidates))

    selected = (
        _select_category(structural_candidates, structural_count, profile=profile, text=context, salt="ja-structure")
        + _select_category(music, music_count, profile=profile, text=context, salt="ja-music")
        + _select_category(painting, painting_count, profile=profile, text=context, salt="ja-painting")
    )
    selected = _limit_centered(selected, centered_tokens=("中心", "中央", "放射状", "同心円状"))

    return _join_sentences(sentences + selected, lang="ja")


def _expand_en(ddl: str, *, context_text: str | None = None) -> str:
    lower = ddl.lower()
    if any(marker in lower for marker in _EN_EXPANSION_MARKERS):
        return ddl
    ddl = _reframe_static_center_en(ddl)
    lower = ddl.lower()

    sentences = _split_sentences(ddl, lang="en")
    structural: list[str] = []
    main_color = _dominant_en_color(ddl)
    contrast_color = _contrast_en_color(ddl)
    context = f"{context_text or ''}\n{ddl}"
    profile = _profile_en(context)

    if any(token in lower for token in ("circle", "dot", "particle", "star", "ellipse", "square")):
        structural.append(f"Line up three small {main_color} ellipses rising to the right along a diagonal band in the right half. Make them wide.")
        structural.append(f"Scatter eight short {main_color} lines from lower left to upper right. Fine trembling.")

    if any(token in lower for token in ("scatter", "dotted", "drift", "snow", "rain")):
        structural.append(
            f"Scatter thirteen small {main_color} ellipses falling to the right along an undulating trace. Swaying slowly."
        )

    if "line" in lower:
        structural.append(f"Line up three thin {contrast_color} diagonal lines rising to the right. Fine trembling.")

    if any(token in lower for token in ("arc", "circle", "wave", "water", "moon", "center")):
        structural.append(f"Line up three thin {contrast_color} arcs spreading from a lower-left focus. Radius 0.11.")

    music = [
        _FilterCandidate(f"Line up two thin {contrast_color} lines falling to the right as contrapuntal contrary motion. Fine trembling.", frozenset(("line", "music", "contrast"))),
        _FilterCandidate(f"Line up three thin {contrast_color} arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.", frozenset(("music", "water", "soft"))),
        _FilterCandidate(f"Line up four short {main_color} lines left to right as a canon offset. Swaying slowly.", frozenset(("particle", "music", "line"))),
    ]
    painting = [
        _FilterCandidate(f"Draw three thin {contrast_color} lines toward an upper-right focus as one-point perspective.", frozenset(("space", "line", "geometry"))),
        _FilterCandidate(f"Line up three thin {contrast_color} horizontal lines upward as perspective depth.", frozenset(("space", "line"))),
        _FilterCandidate("Line up three thin black fine-brush lines left to right as drawing underlines. Fine trembling.", frozenset(("line", "quiet"))),
        _FilterCandidate(f"Scatter thirteen small rotated {main_color} squares along a diagonal band in the right half as pointillism.", frozenset(("particle", "dense", "geometry"))),
        _FilterCandidate(f"Line up three short {main_color} thick-brush lines horizontally as oil impasto.", frozenset(("dense", "contrast"))),
        _FilterCandidate("Layer two pale watercolor ellipses in the upper left. Edges blurring.", frozenset(("water", "soft", "quiet"))),
        _FilterCandidate("Line up six small rotated squares in red, blue, green, gray as patchwork grid.", frozenset(("geometry", "dense"))),
        _FilterCandidate(f"Line up three {contrast_color} chalk horizontal lines at the bottom as fresco ground. Edges blurring.", frozenset(("space", "line", "soft"))),
        _FilterCandidate("Line up three black fine-brush vertical lines left to right as ink-wash value. Edges blurring.", frozenset(("water", "contrast", "quiet"))),
    ]
    structural_candidates = [_FilterCandidate(text, frozenset(("particle", "line", "water", "space"))) for text in structural]
    structural_count, music_count, painting_count = _category_plan(profile, has_structural=bool(structural_candidates))

    selected = (
        _select_category(structural_candidates, structural_count, profile=profile, text=context, salt="en-structure")
        + _select_category(music, music_count, profile=profile, text=context, salt="en-music")
        + _select_category(painting, painting_count, profile=profile, text=context, salt="en-painting")
    )
    selected = _limit_centered(
        selected,
        centered_tokens=("center", "radial", "concentric"),
    )

    return _join_sentences(sentences + selected, lang="en")
