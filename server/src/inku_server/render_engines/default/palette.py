"""Color selection and hint resolution for the default render engine."""

from __future__ import annotations

import hashlib
import math
import re

from ...color_catalogs import DEFAULT_COLOR_CATALOG_ID
from .determinism import _WORK_COLOR_SEED_FIELDS

COLOR_MAP: dict[str, str] = {
    "white": "#ffffff",
    "black": "#111111",
    "blue": "#2c3e91",
    "red": "#a2342a",
    "green": "#2f6b3a",
    "gray": "#888888",
    # These neutral defaults keep all nine abstract colors renderable. Catalogs
    # may override them; band-based catalog resolution can still use them last.
    "yellow": "#a18308",
    "orange": "#a95a00",
    "purple": "#583a84",
}

HUE_HINTS: dict[str, tuple[str, ...]] = {
    "white": (
        "white",
        "ivory",
        "paper",
        "linen",
        "blanc",
        "bianco",
        "aspro",
        "白",
        "胡粉",
        "象牙",
        "生成",
    ),
    "black": (
        "black",
        "ink",
        "sumi",
        "obsidian",
        "basalt",
        "skotadi",
        "黒",
        "墨",
        "玄",
        "暗",
    ),
    "blue": (
        "blue",
        "cyan",
        "azure",
        "ultramarine",
        "cobalt",
        "lapis",
        "bleu",
        "azul",
        "青",
        "藍",
        "水色",
        "空色",
        "瑠璃",
    ),
    "green": (
        "green",
        "verd",
        "jade",
        "olive",
        "cactus",
        "緑",
        "青緑",
        "翡翠",
        "常磐",
        "玉",
        "草",
    ),
    "gray": (
        "gray",
        "grey",
        "silver",
        "ash",
        "stone",
        "granit",
        "petra",
        "灰",
        "鼠",
        "銀",
        "石",
    ),
    "red": (
        "red",
        "rose",
        "pink",
        "carmine",
        "cinnabar",
        "terra",
        "rosa",
        "vermilion",
        "赤",
        "朱",
        "紅",
        "桜",
        "桃",
        "薔薇",
    ),
    "yellow": (
        "yellow",
        "gold",
        "ochre",
        "ocra",
        "giallo",
        "jaune",
        "napoli",
        "kesar",
        "haldi",
        "sun",
        "ilios",
        "山吹",
        "金",
        "黄",
        "琉璃金",
    ),
    "orange": (
        "orange",
        "apricot",
        "terracotta",
        "cempasuchil",
        "ff4d00",
        "橙",
        "蜜柑",
    ),
    "purple": ("purple", "violet", "lilac", "murasaki", "宮廷紫", "藤", "紫"),
    "brown": (
        "brown",
        "sienna",
        "umber",
        "ombra",
        "chandan",
        "lera",
        "sepia",
        "茶",
        "土",
        "焦",
    ),
}

def _norm_label(value: str) -> str:
    return re.sub(r"[\s:_()'\".,/-]+", " ", value.lower()).strip()


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not m:
        return None
    raw = m.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _hue_from_hex(value: str) -> str | None:
    rgb = _hex_to_rgb(value)
    if rgb is None:
        return None
    r, g, b = [c / 255 for c in rgb]
    mx = max(r, g, b)
    mn = min(r, g, b)
    lightness = (mx + mn) / 2
    if mx - mn < 0.08:
        if lightness > 0.82:
            return "white"
        if lightness < 0.2:
            return "black"
        return "gray"
    if mx == r:
        hue = (60 * ((g - b) / (mx - mn)) + 360) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    if 15 <= hue < 45:
        return "orange"
    if 45 <= hue < 75:
        return "yellow"
    if 75 <= hue < 165:
        return "green"
    if 165 <= hue < 255:
        return "blue"
    if 255 <= hue < 315:
        return "purple"
    return "red"


_ASCII_HINT_TOKEN_RE = re.compile(r"^[a-z]+$")
_ASCII_HINT_WORD_RE = re.compile(r"[0-9a-z]+")
_ACHROMATIC_COLORS = ("black", "gray", "white")
_CHROMATIC_COLORS = ("red", "orange", "yellow", "green", "blue", "purple")
_CHROMATIC_BANDS = {
    "red": (345.0, 50.0),
    "orange": (50.0, 80.0),
    "yellow": (80.0, 137.0),
    "green": (137.0, 200.0),
    "blue": (200.0, 280.0),
    "purple": (280.0, 345.0),
}
_CHROMATIC_BAND_CENTERS = {
    "red": 27.5,
    "orange": 65.0,
    "yellow": 108.5,
    "green": 168.5,
    "blue": 240.0,
    "purple": 312.5,
}
_OKLCH_CHROMA_FLOOR = 0.035
_HINT_HUE_PRIORITY = (
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
    "white",
    "black",
    "gray",
)


def _oklch_from_hex(value: str) -> tuple[float, float, float] | None:
    rgb = _hex_to_rgb(value)
    if rgb is None:
        return None

    def linearize(component: int) -> float:
        channel = component / 255
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    r, g, b = (linearize(component) for component in rgb)
    l_channel = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_channel = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_channel = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_root, m_root, s_root = (
        value ** (1 / 3) if value >= 0 else -((-value) ** (1 / 3))
        for value in (l_channel, m_channel, s_channel)
    )
    lightness = (
        0.2104542553 * l_root
        + 0.7936177850 * m_root
        - 0.0040720468 * s_root
    )
    a = 1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root
    b_axis = 0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root
    return lightness, math.hypot(a, b_axis), math.degrees(math.atan2(b_axis, a)) % 360


def _chromatic_band(hue: float) -> str:
    for name, (lower, upper) in _CHROMATIC_BANDS.items():
        if lower > upper:
            if hue >= lower or hue < upper:
                return name
        elif lower <= hue < upper:
            return name
    return "red"


def _circular_hue_distance(left: float, right: float) -> float:
    distance = abs(left - right) % 360
    return min(distance, 360 - distance)


def _work_color_choice(
    candidates: list[str],
    render_seed: int | None,
    catalog_id: str,
    abstract_color: str,
) -> str:
    ordered = sorted(set(candidates))
    if len(ordered) == 1:
        return ordered[0]
    values = {
        "render_seed": render_seed,
        "catalog_id": catalog_id,
        "abstract_color": abstract_color,
    }
    payload = "|".join(str(values[field]) for field in _WORK_COLOR_SEED_FIELDS)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return ordered[int.from_bytes(digest[:8], "big") % len(ordered)]


def _work_color_assignment(
    cmap: dict[str, str],
    render_seed: int | None,
    catalog_id: str | None,
) -> dict[str, str]:
    resolved_catalog_id = catalog_id or DEFAULT_COLOR_CATALOG_ID
    achromatic: list[tuple[float, str]] = []
    chromatic: dict[str, list[str]] = {
        color: [] for color in _CHROMATIC_COLORS
    }
    chromatic_hues: list[tuple[float, str]] = []
    seen: set[str] = set()
    for key, hex_value in cmap.items():
        if not key.startswith("palette:") or hex_value in seen:
            continue
        oklch = _oklch_from_hex(hex_value)
        if oklch is None:
            continue
        seen.add(hex_value)
        lightness, chroma, hue = oklch
        if chroma < _OKLCH_CHROMA_FLOOR:
            achromatic.append((lightness, hex_value))
        else:
            chromatic[_chromatic_band(hue)].append(hex_value)
            chromatic_hues.append((hue, hex_value))

    assignment: dict[str, str] = {}
    remaining = sorted(achromatic)
    for color in _ACHROMATIC_COLORS:
        fallback = cmap.get(color, COLOR_MAP[color])
        exact = next(
            (
                candidate
                for candidate in remaining
                if candidate[1].lower() == fallback.lower()
            ),
            None,
        )
        if exact is not None:
            remaining.remove(exact)
            assignment[color] = exact[1]
    for color in _ACHROMATIC_COLORS:
        if color in assignment:
            continue
        fallback = cmap.get(color, COLOR_MAP[color])
        if not remaining:
            assignment[color] = fallback
            continue
        target = _oklch_from_hex(fallback)
        target_lightness = target[0] if target is not None else 0.0
        best = min(
            remaining,
            key=lambda candidate: (
                abs(candidate[0] - target_lightness),
                candidate[1],
            ),
        )
        remaining.remove(best)
        assignment[color] = best[1]

    for color in _CHROMATIC_COLORS:
        candidates = chromatic[color]
        if candidates:
            assignment[color] = _work_color_choice(
                candidates, render_seed, resolved_catalog_id, color
            )
        elif chromatic_hues:
            target = _CHROMATIC_BAND_CENTERS[color]
            assignment[color] = min(
                chromatic_hues,
                key=lambda candidate: (
                    _circular_hue_distance(candidate[0], target),
                    candidate[1],
                ),
            )[1]
        else:
            assignment[color] = cmap.get(color, COLOR_MAP[color])
    return assignment


def _hint_hues(hint: str) -> set[str]:
    normalized = _norm_label(hint)
    words = set(_ASCII_HINT_WORD_RE.findall(normalized))
    hues: set[str] = set()
    for hue, tokens in HUE_HINTS.items():
        for token in tokens:
            lowered = token.lower()
            if (
                lowered in words
                if _ASCII_HINT_TOKEN_RE.fullmatch(lowered)
                else token in hint
            ):
                hues.add(hue)
                break
    return hues


def _resolve_color(
    color: str,
    color_hint: str | None,
    cmap: dict[str, str],
    *,
    work_assignment: dict[str, str] | None = None,
    render_seed: int | None = None,
    catalog_id: str | None = None,
) -> str:
    assignment = work_assignment or _work_color_assignment(
        cmap, render_seed, catalog_id
    )
    fallback = assignment.get(color, cmap[color])
    if not color_hint:
        return fallback
    desired_hues = _hint_hues(color_hint)
    if desired_hues == {"brown"}:
        return assignment["orange"]
    desired_hues.discard("brown")
    for desired in _HINT_HUE_PRIORITY:
        if desired in desired_hues:
            return assignment[desired]
    return fallback


def _render_effect_hint(color_hint: str | None) -> str | None:
    """color_cycle 時も、色選択ではなく描画効果に関わるヒントだけは残す。"""
    if not color_hint:
        return None
    hint = _norm_label(color_hint)
    effect_tokens = (
        "membrane",
        "haze",
        "fog",
        "mist",
        "atmosphere",
        "膜",
        "霞",
        "霧",
        "靄",
        "soft light",
        "柔らかな光",
        "陽光",
        "日差し",
        "scent",
        "fragrance",
        "香り",
        "匂",
        "waiting buds",
        "開花を待つ蕾",
        "蕾",
        "つぼみ",
        "five-sense",
        "五感",
        "fade directional",
        "fade=directional",
        "fade outward",
        "fade=outward",
        "reflection",
        "反射",
        "映り",
    )
    kept = [token for token in effect_tokens if token in hint]
    return "; ".join(kept) if kept else None


