"""Intermediate DDL expansion between Stage 1 and Stage 2.

The expander keeps Stage 1 deterministic and cheap while giving Stage 2
more compositional material: secondary structure, asymmetry, and controlled
variation. It intentionally emits ordinary normalized DDL sentences instead
of JSON so the existing Stage 2 compiler remains the single JSON authority.
"""

from __future__ import annotations

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


def _split_sentences(text: str, *, lang: str) -> list[str]:
    if lang == "en":
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return [s.strip() for s in re.split(r"(?<=。)", text.strip()) if s.strip()]


def _join_sentences(sentences: list[str], *, lang: str) -> str:
    if lang == "en":
        return " ".join(s if s.endswith((".", "!", "?")) else f"{s}." for s in sentences)
    return "".join(s if s.endswith("。") else f"{s}。" for s in sentences)


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
    and motion-derived wave traces.
    """

    sanitized = _sanitize_placement_words(ddl).strip()
    if not sanitized:
        return sanitized
    if lang == "en":
        return _expand_en(sanitized)
    return _expand_ja(sanitized)


def _expand_ja(ddl: str) -> str:
    if any(marker in ddl for marker in ("黄金比の位置", "三分割の交点", "白銀比の位置", "正五角形の頂点")):
        return ddl

    sentences = _split_sentences(ddl, lang="ja")
    structural: list[str] = []
    main_color = _dominant_ja_color(ddl)
    contrast_color = _contrast_ja_color(ddl)

    if any(token in ddl for token in ("円", "点", "粒", "星")):
        structural.append(f"{main_color}小さな円を正五角形の頂点に五個並べる。半径は0.022。")
        structural.append(f"{main_color}小さな円を放射状に十三個並べる。半径は0.018。細かく震える。")

    if any(token in ddl for token in ("散らす", "点々", "舞", "漂", "雪", "雨")):
        structural.append(f"{main_color}小さな円を波打つ軌跡に沿って二十一個散らす。半径は0.012。ゆっくり揺れる。")

    if "線" in ddl:
        structural.append(f"{contrast_color}細い斜め線を右上がりに八本並べる。細かく震える。")

    if any(token in ddl for token in ("弧", "円", "波", "水", "月", "中心")):
        structural.append(f"{contrast_color}細い弧を中心に五つ同心円状に並べる。半径は0.11。")

    anchors = [
        f"{contrast_color}小さな円を右上の黄金比の位置に一点置く。半径は0.025。",
        f"{contrast_color}小さな円を左上の三分割の交点に一点置く。半径は0.018。",
        f"{contrast_color}小さな円を左下の白銀比の位置に一点置く。半径は0.016。",
    ]
    music = [
        f"{contrast_color}細い線を対位法の反行として右下がりに三本並べる。細かく震える。",
        f"{contrast_color}細い弧を倍音列として中心から放射状に四つ並べる。半径は0.07。",
        f"{main_color}小さな円を輪唱のずれとして左から右へ七個並べる。半径は0.014。ゆっくり揺れる。",
    ]

    return _join_sentences(sentences + structural[:3] + music + anchors, lang="ja")


def _expand_en(ddl: str) -> str:
    lower = ddl.lower()
    if any(marker in lower for marker in ("golden-ratio position", "rule-of-thirds point", "silver-ratio position", "regular pentagon vertices")):
        return ddl

    sentences = _split_sentences(ddl, lang="en")
    structural: list[str] = []
    main_color = _dominant_en_color(ddl)
    contrast_color = _contrast_en_color(ddl)

    if any(token in lower for token in ("circle", "dot", "particle", "star")):
        structural.append(f"Line up five small {main_color} circles on regular pentagon vertices. Radius 0.022.")
        structural.append(f"Line up thirteen small {main_color} circles radially. Radius 0.018. Fine trembling.")

    if any(token in lower for token in ("scatter", "dotted", "drift", "snow", "rain")):
        structural.append(
            f"Scatter twenty-one small {main_color} circles along an undulating trace. Radius 0.012. Swaying slowly."
        )

    if "line" in lower:
        structural.append(f"Line up eight thin {contrast_color} diagonal lines rising to the right. Fine trembling.")

    if any(token in lower for token in ("arc", "circle", "wave", "water", "moon", "center")):
        structural.append(f"Line up five thin {contrast_color} arcs concentrically at center. Radius 0.11.")

    anchors = [
        f"Place one small {contrast_color} circle at the upper-right golden-ratio position. Radius 0.025.",
        f"Place one small {contrast_color} circle at the upper-left rule-of-thirds point. Radius 0.018.",
        f"Place one small {contrast_color} circle at the lower-left silver-ratio position. Radius 0.016.",
    ]
    music = [
        f"Line up three thin {contrast_color} lines falling to the right as contrapuntal contrary motion. Fine trembling.",
        f"Line up four thin {contrast_color} arcs radially from center as a harmonic overtone series. Radius 0.07.",
        f"Line up seven small {main_color} circles left to right as a canon offset. Radius 0.014. Swaying slowly.",
    ]

    return _join_sentences(sentences + structural[:3] + music + anchors, lang="en")
