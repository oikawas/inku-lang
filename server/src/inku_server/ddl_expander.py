"""Intermediate DDL expansion between Stage 1 and Stage 2.

The expander keeps Stage 1 deterministic and cheap while giving Stage 2
more compositional material: secondary structure, asymmetry, and controlled
variation. It intentionally emits ordinary normalized DDL sentences instead
of JSON so the existing Stage 2 compiler remains the single JSON authority.
"""

from __future__ import annotations

import hashlib
import re

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
    if "背景を黒" in ddl or "背景を灰" in ddl or "暗い背景" in ddl:
        return "白い"
    return "灰色の"


def _dominant_en_color(ddl: str) -> str:
    body = re.sub(r"Fill background with \w+\.?", "", ddl, flags=re.IGNORECASE)
    lower = body.lower()
    for color in _EN_COLORS:
        if color in lower:
            return color
    return "black"


def _contrast_en_color(ddl: str) -> str:
    lower = ddl.lower()
    if "fill background with black" in lower or "fill background with gray" in lower:
        return "white"
    return "gray"


def expand_intermediate_ddl(ddl: str, *, lang: str = "ja") -> str:
    """Add controlled complexity to normalized DDL before Stage 2.

    The filter favors visible mathematical structure over vague randomness:
    golden-ratio accents, rule-of-thirds anchors, silver-ratio counterpoints,
    Fibonacci-friendly counts, radial echoes, diagonal counter-lines,
    harmonic overtones, contrapuntal contrary motion, canon-like repetitions,
    painterly material techniques, perspective guides, value structure, and
    motion-derived wave traces.
    """

    sanitized = _sanitize_placement_words(ddl).strip()
    if not sanitized:
        return sanitized
    if lang == "en":
        return _expand_en(sanitized)
    return _expand_ja(sanitized)


def _expand_ja(ddl: str) -> str:
    if any(marker in ddl for marker in _JA_EXPANSION_MARKERS):
        return ddl
    ddl = _reframe_static_center_ja(ddl)

    sentences = _split_sentences(ddl, lang="ja")
    structural: list[str] = []
    main_color = _dominant_ja_color(ddl)
    contrast_color = _contrast_ja_color(ddl)

    if any(token in ddl for token in ("円", "点", "粒", "星")):
        structural.append(f"{main_color}小さな円を右半分の斜めの帯に三個並べる。半径は0.022。")
        structural.append(f"{main_color}小さな円を左下から右上へ八個散らす。半径は0.018。細かく震える。")

    if any(token in ddl for token in ("散らす", "点々", "舞", "漂", "雪", "雨")):
        structural.append(f"{main_color}小さな円を波打つ軌跡に沿って十三個散らす。半径は0.012。ゆっくり揺れる。")

    if "線" in ddl:
        structural.append(f"{contrast_color}細い斜め線を右上がりに三本並べる。細かく震える。")

    if any(token in ddl for token in ("弧", "円", "波", "水", "月", "中心")):
        structural.append(f"{contrast_color}細い弧を左下の焦点から三つ広げる。半径は0.11。")

    music = [
        f"{contrast_color}細い線を対位法の反行として右下がりに二本並べる。細かく震える。",
        f"{contrast_color}細い弧を倍音列として右下の焦点から三つ並べる。半径は0.07。",
        f"{main_color}小さな円を輪唱のずれとして左から右へ四個並べる。半径は0.014。ゆっくり揺れる。",
    ]
    painting = [
        f"{contrast_color}細い線を一点透視法として右上の焦点へ向けて三本引く。",
        "灰色の細い横線を遠近法の奥行きとして上へ細かく三本並べる。",
        "黒い細筆の細い線を素描の下線として左から右へ三本並べる。細かく震える。",
        f"{main_color}小さな円を点描として画面全体に点々と十三個散らす。半径は0.006。",
        f"{main_color}太筆の短い線を油絵の厚塗りとして横に三本並べる。",
        f"{contrast_color}薄い水彩の楕円を左上に二つ重ねる。境界が滲む。",
        "赤・青・緑・灰の小さな四角をパッチワークとして格子状に六個並べる。",
        "灰色のチョークの横線をフレスコの下地として画面下に三本並べる。境界が滲む。",
        "黒い細筆の縦線を水墨の濃淡として左から右へ三本並べる。境界が滲む。",
    ]

    selected = (
        _pick(structural, 1, text=ddl, salt="ja-structure")
        + _pick(music, 1, text=ddl, salt="ja-music")
        + _pick(painting, 1, text=ddl, salt="ja-painting")
    )
    selected = _limit_centered(selected, centered_tokens=("中心", "中央", "放射状", "同心円状"))

    return _join_sentences(sentences + selected, lang="ja")


def _expand_en(ddl: str) -> str:
    lower = ddl.lower()
    if any(marker in lower for marker in _EN_EXPANSION_MARKERS):
        return ddl
    ddl = _reframe_static_center_en(ddl)
    lower = ddl.lower()

    sentences = _split_sentences(ddl, lang="en")
    structural: list[str] = []
    main_color = _dominant_en_color(ddl)
    contrast_color = _contrast_en_color(ddl)

    if any(token in lower for token in ("circle", "dot", "particle", "star")):
        structural.append(f"Line up three small {main_color} circles along a diagonal band in the right half. Radius 0.022.")
        structural.append(f"Scatter eight small {main_color} circles from lower left to upper right. Radius 0.018. Fine trembling.")

    if any(token in lower for token in ("scatter", "dotted", "drift", "snow", "rain")):
        structural.append(
            f"Scatter thirteen small {main_color} circles along an undulating trace. Radius 0.012. Swaying slowly."
        )

    if "line" in lower:
        structural.append(f"Line up three thin {contrast_color} diagonal lines rising to the right. Fine trembling.")

    if any(token in lower for token in ("arc", "circle", "wave", "water", "moon", "center")):
        structural.append(f"Line up three thin {contrast_color} arcs spreading from a lower-left focus. Radius 0.11.")

    music = [
        f"Line up two thin {contrast_color} lines falling to the right as contrapuntal contrary motion. Fine trembling.",
        f"Line up three thin {contrast_color} arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.",
        f"Line up four small {main_color} circles left to right as a canon offset. Radius 0.014. Swaying slowly.",
    ]
    painting = [
        f"Draw three thin {contrast_color} lines toward an upper-right focus as one-point perspective.",
        "Line up three thin gray horizontal lines upward as perspective depth.",
        "Line up three thin black fine-brush lines left to right as drawing underlines. Fine trembling.",
        f"Scatter thirteen small {main_color} circles dotted across the whole canvas as pointillism. Radius 0.006.",
        f"Line up three short {main_color} thick-brush lines horizontally as oil impasto.",
        "Layer two pale watercolor ellipses in the upper left. Edges blurring.",
        "Line up six small squares in red, blue, green, gray as patchwork grid.",
        "Line up three gray chalk horizontal lines at the bottom as fresco ground. Edges blurring.",
        "Line up three black fine-brush vertical lines left to right as ink-wash value. Edges blurring.",
    ]

    selected = (
        _pick(structural, 1, text=ddl, salt="en-structure")
        + _pick(music, 1, text=ddl, salt="en-music")
        + _pick(painting, 1, text=ddl, salt="en-painting")
    )
    selected = _limit_centered(
        selected,
        centered_tokens=("center", "radial", "concentric"),
    )

    return _join_sentences(sentences + selected, lang="en")
