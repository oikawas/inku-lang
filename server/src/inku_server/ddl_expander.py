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
    "鉛筆の余白線",
    "クレヨンの擦れ",
    "ロットリングの均一線",
    "縄の撚り",
    "透明な膜",
    "薄い反射",
    "消える線",
    "柔らかな光",
    "香りの層",
    "開花を待つ蕾",
    "五感の気配",
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
    "rope twist",
    "transparent membrane",
    "faint reflection",
    "fading lines",
    "soft light",
    "scent layer",
    "waiting buds",
    "five-sense presence",
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
    mode: str


@dataclass(frozen=True)
class _FilterCandidate:
    text: str
    tags: frozenset[str]


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


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

    if profile.tags & {"atmosphere", "sensory", "presence"}:
        preferred_tags = profile.tags & {"atmosphere", "sensory", "presence"}
        matched = [c for c in candidates if c.tags & preferred_tags]
        if matched:
            return _pick([c.text for c in matched], count, text=text, salt=salt)

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
    if _has_any(lower, ("forest", "leaf", "grass", "scent", "fragrance", "field", "moss")):
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
        structural.append(f"{main_color}短い線を左下から右上へ三本散らす。細かく震える。")

    if any(token in ddl for token in ("散らす", "点々", "舞", "漂", "雪", "雨")):
        structural.append(f"{main_color}右下がりの小さな楕円を波打つ軌跡に沿って七個散らす。ゆっくり揺れる。")

    if "線" in ddl:
        structural.append(f"{contrast_color}細い斜め線を右上がりに三本並べる。細かく震える。")

    if any(token in ddl for token in ("弧", "円", "波", "水", "月", "中心")):
        structural.append(f"{contrast_color}細い弧を左下の焦点から三つ広げる。半径は0.11。")
    if any(token in context for token in ("山", "屋根", "尖", "針葉樹", "頂", "鋭")):
        structural.append(f"{main_color}細い三角を上端寄りの焦点に二つ置く。少し傾ける。")
    if any(token in context for token in ("葉", "花びら", "羽", "紙片", "破片", "舟")):
        structural.append(f"{main_color}細い右上がりの楕円を葉片として波打つ軌跡に沿って五個散らす。")
    if any(token in context for token in ("扉", "窓", "箱", "街", "部屋", "格子")):
        structural.append(f"{contrast_color}回転した細い四角を視線の切片として右半分に三つ散らす。")
    if any(token in context for token in ("膜", "透明", "霞", "霧", "靄", "気配", "余韻")):
        structural.append(f"{main_color}薄い水彩の楕円を透明な膜として右半分に三つ重ねる。境界が滲む。")
    if any(token in context for token in ("反射", "映り")):
        structural.append(f"{contrast_color}薄い反射の線を波打つ軌跡に沿って五本散らす。ゆっくり揺れる。")
    if any(token in context for token in ("消え", "薄れ", "遠ざか")):
        structural.append(f"{contrast_color}消える線を左下から右上へ五本散らす。細かく震える。")
    if any(token in context for token in ("陽光", "光", "日差し", "温", "柔ら")):
        structural.append("白い薄い水彩の横長の楕円を柔らかな光として上端寄りに三つ重ねる。境界が滲む。")
    if any(token in context for token in ("香", "匂", "沈丁花")):
        structural.append("緑の小さな楕円を香りの層として波打つ軌跡に沿って七個散らす。ゆっくり揺れる。")
    if any(token in context for token in ("蕾", "つぼみ", "開花", "春")):
        structural.append("赤い右上がりの小さな楕円を開花を待つ蕾として右半分の斜めの帯に五個散らす。")
    if any(token in context for token in ("五感", "気配", "訪れ")):
        structural.append("白い薄い弧を五感の気配として左下の焦点から三つ広げる。半径は0.14。")
    if any(token in context for token in ("人", "人物", "村人", "老人", "顔", "視線", "動物", "鳥", "魚", "熊", "群れ")):
        structural.append(f"{contrast_color}細い余白線を存在の重心として右上の焦点へ二本引く。細かく震える。")
        structural.append(f"{main_color}薄い弧を輪郭の密度として左下の焦点から二つ置く。半径は0.09。")

    music = [
        _FilterCandidate(f"{contrast_color}細い線を対位法の反行として右下がりに二本並べる。細かく震える。", frozenset(("line", "music", "contrast"))),
        _FilterCandidate(f"{contrast_color}細い弧を倍音列として右下の焦点から三つ並べる。半径は0.07。", frozenset(("music", "water", "soft"))),
        _FilterCandidate(f"{main_color}短い線を輪唱のずれとして左から右へ四本並べる。ゆっくり揺れる。", frozenset(("particle", "music", "line"))),
    ]
    painting = [
        _FilterCandidate(f"{contrast_color}細い線を一点透視法として右上の焦点へ向けて三本引く。", frozenset(("space", "line", "geometry"))),
        _FilterCandidate(f"{contrast_color}細い横線を遠近法の奥行きとして上へ細かく三本並べる。", frozenset(("space", "line"))),
        _FilterCandidate("黒い細筆の細い線を素描の下線として左から右へ三本並べる。細かく震える。", frozenset(("line", "quiet"))),
        _FilterCandidate(f"{contrast_color}鉛筆の細い線を余白線として上端寄りに二本並べる。細かく震える。", frozenset(("line", "quiet", "soft"))),
        _FilterCandidate(f"{main_color}クレヨンの短い線を擦れとして右半分の斜めの帯に七本散らす。", frozenset(("particle", "dense", "soft"))),
        _FilterCandidate(f"{contrast_color}ロットリングの細い線を均一線として左から右へ五本並べる。", frozenset(("line", "geometry", "contrast"))),
        _FilterCandidate(f"{contrast_color}縄の横線を撚りとして下端寄りに一本引く。ゆっくり揺れる。", frozenset(("line", "dense", "contrast"))),
        _FilterCandidate(f"{main_color}回転した小さな四角を点描として右半分の斜めの帯に十三個散らす。", frozenset(("particle", "dense", "geometry"))),
        _FilterCandidate(f"{main_color}太筆の短い線を油絵の厚塗りとして横に三本並べる。", frozenset(("dense", "contrast"))),
        _FilterCandidate(f"{contrast_color}薄い水彩の楕円を左上に二つ重ねる。境界が滲む。", frozenset(("water", "soft", "quiet"))),
        _FilterCandidate("赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に六個並べる。", frozenset(("geometry", "dense"))),
        _FilterCandidate(f"{contrast_color}チョークの横線をフレスコの下地として画面下に三本並べる。境界が滲む。", frozenset(("space", "line", "soft"))),
        _FilterCandidate("黒い細筆の縦線を水墨の濃淡として左から右へ三本並べる。境界が滲む。", frozenset(("water", "contrast", "quiet"))),
        _FilterCandidate("白い薄い水彩の楕円を五感の気配として右上に二つ重ねる。境界が滲む。", frozenset(("sensory", "soft", "quiet"))),
    ]
    structural_candidates = [_FilterCandidate(text, _structural_tags(text)) for text in structural]
    structural_count, music_count, painting_count = _category_plan(profile, has_structural=bool(structural_candidates))

    selected = (
        _select_category(structural_candidates, structural_count, profile=profile, text=context, salt=_mode_salt(profile, "ja-structure"))
        + _select_category(music, music_count, profile=profile, text=context, salt=_mode_salt(profile, "ja-music"))
        + _select_category(painting, painting_count, profile=profile, text=context, salt=_mode_salt(profile, "ja-painting"))
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
        structural.append(f"Scatter three short {main_color} lines from lower left to upper right. Fine trembling.")

    if any(token in lower for token in ("scatter", "dotted", "drift", "snow", "rain")):
        structural.append(
            f"Scatter seven small {main_color} ellipses falling to the right along an undulating trace. Swaying slowly."
        )

    if "line" in lower:
        structural.append(f"Line up three thin {contrast_color} diagonal lines rising to the right. Fine trembling.")

    if any(token in lower for token in ("arc", "circle", "wave", "water", "moon", "center")):
        structural.append(f"Line up three thin {contrast_color} arcs spreading from a lower-left focus. Radius 0.11.")
    if any(token in context.lower() for token in ("mountain", "roof", "sharp", "pine", "peak", "needle")):
        structural.append(f"Place two thin {main_color} triangles near the upper-edge focus. Tilt them slightly.")
    if any(token in context.lower() for token in ("leaf", "petal", "feather", "paper", "fragment", "boat")):
        structural.append(f"Scatter five thin {main_color} ellipses rising to the right along an undulating trace as leaf-like pieces.")
    if any(token in context.lower() for token in ("door", "window", "box", "city", "room", "grid")):
        structural.append(f"Scatter three thin rotated {contrast_color} squares in the right half as visual cuts.")
    if any(token in context.lower() for token in ("membrane", "transparent", "haze", "fog", "mist", "atmosphere", "presence")):
        structural.append(f"Layer three pale {main_color} watercolor ellipses in the right half as a transparent membrane. Edges blurring.")
    if any(token in context.lower() for token in ("reflection", "reflected")):
        structural.append(f"Scatter five thin {contrast_color} faint reflection lines along an undulating trace. Swaying slowly.")
    if any(token in context.lower() for token in ("fade", "fading", "vanish", "dissolve")):
        structural.append(f"Scatter five thin {contrast_color} fading lines from lower left to upper right. Fine trembling.")
    if any(token in context.lower() for token in ("sunlight", "light", "warm", "soft")):
        structural.append("Layer three pale white watercolor ellipses near the upper edge as soft light. Edges blurring.")
    if any(token in context.lower() for token in ("scent", "fragrance")):
        structural.append("Scatter seven small green ellipses along an undulating trace as a scent layer. Swaying slowly.")
    if any(token in context.lower() for token in ("spring", "bud", "bloom", "waiting")):
        structural.append("Scatter five small red ellipses rising to the right along a diagonal band in the right half as waiting buds.")
    if any(token in context.lower() for token in ("sense", "presence", "arrival")):
        structural.append("Line up three pale white arcs from a lower-left focus as five-sense presence. Radius 0.14.")
    if any(token in context.lower() for token in ("human", "person", "people", "figure", "face", "gaze", "animal", "bird", "fish", "bear", "flock", "herd")):
        structural.append(f"Draw two thin {contrast_color} negative-space lines toward an upper-right focus as presence weight. Fine trembling.")
        structural.append(f"Place two pale {main_color} arcs from a lower-left focus as contour density. Radius 0.09.")

    music = [
        _FilterCandidate(f"Line up two thin {contrast_color} lines falling to the right as contrapuntal contrary motion. Fine trembling.", frozenset(("line", "music", "contrast"))),
        _FilterCandidate(f"Line up three thin {contrast_color} arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.", frozenset(("music", "water", "soft"))),
        _FilterCandidate(f"Line up four short {main_color} lines left to right as a canon offset. Swaying slowly.", frozenset(("particle", "music", "line"))),
    ]
    painting = [
        _FilterCandidate(f"Draw three thin {contrast_color} lines toward an upper-right focus as one-point perspective.", frozenset(("space", "line", "geometry"))),
        _FilterCandidate(f"Line up three thin {contrast_color} horizontal lines upward as perspective depth.", frozenset(("space", "line"))),
        _FilterCandidate("Line up three thin black fine-brush lines left to right as drawing underlines. Fine trembling.", frozenset(("line", "quiet"))),
        _FilterCandidate(f"Line up two thin {contrast_color} pencil lines near the top edge as pencil negative-space line. Fine trembling.", frozenset(("line", "quiet", "soft"))),
        _FilterCandidate(f"Scatter seven short {main_color} crayon lines along a diagonal band in the right half as crayon rubbing.", frozenset(("particle", "dense", "soft"))),
        _FilterCandidate(f"Line up five thin {contrast_color} rotring uniform lines left to right.", frozenset(("line", "geometry", "contrast"))),
        _FilterCandidate(f"Draw one {contrast_color} rope horizontal line near the bottom edge as rope twist. Swaying slowly.", frozenset(("line", "dense", "contrast"))),
        _FilterCandidate(f"Scatter thirteen small rotated {main_color} squares along a diagonal band in the right half as pointillism.", frozenset(("particle", "dense", "geometry"))),
        _FilterCandidate(f"Line up three short {main_color} thick-brush lines horizontally as oil impasto.", frozenset(("dense", "contrast"))),
        _FilterCandidate("Layer two pale watercolor ellipses in the upper left. Edges blurring.", frozenset(("water", "soft", "quiet"))),
        _FilterCandidate("Line up six small rotated squares in red, blue, green, gray as patchwork grid.", frozenset(("geometry", "dense"))),
        _FilterCandidate(f"Line up three {contrast_color} chalk horizontal lines at the bottom as fresco ground. Edges blurring.", frozenset(("space", "line", "soft"))),
        _FilterCandidate("Line up three black fine-brush vertical lines left to right as ink-wash value. Edges blurring.", frozenset(("water", "contrast", "quiet"))),
        _FilterCandidate("Layer two pale white watercolor ellipses in the upper right as five-sense presence. Edges blurring.", frozenset(("sensory", "soft", "quiet"))),
    ]
    structural_candidates = [_FilterCandidate(text, _structural_tags(text)) for text in structural]
    structural_count, music_count, painting_count = _category_plan(profile, has_structural=bool(structural_candidates))

    selected = (
        _select_category(structural_candidates, structural_count, profile=profile, text=context, salt=_mode_salt(profile, "en-structure"))
        + _select_category(music, music_count, profile=profile, text=context, salt=_mode_salt(profile, "en-music"))
        + _select_category(painting, painting_count, profile=profile, text=context, salt=_mode_salt(profile, "en-painting"))
    )
    selected = _limit_centered(
        selected,
        centered_tokens=("center", "radial", "concentric"),
    )

    return _join_sentences(sentences + selected, lang="en")
