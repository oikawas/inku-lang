"""inku 歳時記 (Saijiki) — Server 表示・保存互換 projection.

生成語彙の正は共有 core の ``assets/saijiki-v4.json`` にある。このテーブルは
その内容と同期し、Server 側の次の読み取り用途へ投影する:

- reference の旧マーカー表（保存された説明との照合用）
- reference §1〜§3 の歳時記・マーカー表 (reference.py)
- 歳時記表示の配信 (Phase 3: GET /api/saijiki と web スナップショット)
- 保存済み Score の受理に使う互換語彙

Score schema (schema.py) の enum は従来どおり Score 側の正であり、ここからは
導出しない。語彙から消えた語 (例: 描く) も保存済み Score の受理・Replay のため
schema からは削除しない。

フラグの意味:
- prompt: 共有 asset との同期確認用ブロック・列挙へ出す
- display: 歳時記表示 (web / API) へ出す
- marker: 旧マーカー表に含める (None = prompt に従う)

順序の扱い: words は共有 asset の表示順で持つ。閉包マーカーの順序が
表示順と異なるカテゴリ (かたち・うごき・あいだ) は marker_order_* で明示する。
順序は表示・互換のための指定であり、所属 (membership) は常に語の
フラグから導出される。
"""

from __future__ import annotations

from dataclasses import dataclass
from .saijiki_generated import BUNDLES, CATEGORIES

__all__ = [
    "SaijikiWord",
    "SaijikiCategory",
    "RelationWord",
    "SAIJIKI",
    "RELATIONS",
    "prompt_block",
    "texture_material_enumeration",
    "core_grammar_markers",
    "shape_markers",
    "saijiki_marker_table",
    "relation_literal_markers",
    "reference_categories",
]

_LANGS = ("ja", "en")


@dataclass(frozen=True)
class _EnglishGrammar:
    lemma: str
    lexical_class: str
    canonical_form: str
    permitted_forms: tuple[str, ...]


@dataclass(frozen=True)
class SaijikiWord:
    surface_ja: str
    surface_en: str | None
    id: str = ""
    facet: str | None = None
    description: dict[str, str] | None = None
    default: bool = False  # プロンプトで「(既定)」/" (default)" を付ける
    prompt: bool = True  # 共有 asset 同期用ブロック・列挙へ出す
    display: bool = True  # 歳時記表示 (web / API) へ出す
    marker: bool | None = None  # 閉包マーカー所属 (None = prompt に従う)
    score_value: str | None = None  # Weight / Color / SurfaceTexture の Score enum 値
    semantic_alias: str | None = None  # localized wire IDとは別のtyped semantic identity
    english_grammar: _EnglishGrammar | None = None  # Rust assetと同期する非公開metadata
    # Compiler-only aliases never enter prompt, display, or marker projections.
    parser_surfaces_ja: tuple[str, ...] | None = None
    parser_surfaces_en: tuple[str, ...] | None = None
    # マーカー表面の言語別上書き。en「line-up」は従来マーカー「arrange」を保つ。
    marker_surfaces_ja: tuple[str, ...] | None = None
    marker_surfaces_en: tuple[str, ...] | None = None

    def surface(self, lang: str) -> str | None:
        return self.surface_ja if lang == "ja" else self.surface_en

    @property
    def is_marker(self) -> bool:
        return self.prompt if self.marker is None else self.marker

    def marker_names(self, lang: str) -> tuple[str, ...]:
        override = self.marker_surfaces_ja if lang == "ja" else self.marker_surfaces_en
        if override is not None:
            return override
        surface = self.surface(lang)
        return () if surface is None else (surface,)


@dataclass(frozen=True)
class SaijikiCategory:
    key: str
    name_ja: str
    name_en: str
    # reference §3 のマーカー分類名。None はマーカーへ出さないカテゴリ (つらなり)。
    marker_class: str | None
    words: tuple[SaijikiWord, ...]
    bundle: str = ""
    # 閉包マーカーの順序がプロンプト順と異なる場合の明示順 (marker 表面名で指定)
    marker_order_ja: tuple[str, ...] | None = None
    marker_order_en: tuple[str, ...] | None = None

    def words_for(self, lang: str) -> tuple[SaijikiWord, ...]:
        return tuple(word for word in self.words if word.surface(lang) is not None)

    def marker_order(self, lang: str) -> tuple[str, ...] | None:
        return self.marker_order_ja if lang == "ja" else self.marker_order_en


@dataclass(frozen=True)
class RelationWord:
    relation_type: str  # relation.type (共有 asset / schema と共通)
    surface_ja: str
    surface_en: str
    literals_ja: tuple[str, ...]  # 正規化DDLの固定 previous-object 句
    literals_en: tuple[str, ...]
    literal_targets: tuple[tuple[str, str], ...] = ()

    def surface(self, lang: str) -> str:
        return self.surface_ja if lang == "ja" else self.surface_en


def _category_from_asset(data: dict) -> SaijikiCategory:
    words = []
    for item in data["words"]:
        fields = {key: item[key] for key in (
            "surface_ja", "surface_en", "default", "prompt", "display", "marker",
            "score_value", "parser_surfaces_ja", "parser_surfaces_en",
            "marker_surfaces_ja", "marker_surfaces_en", "id", "facet", "description"
        ) if key in item}
        for key in ("parser_surfaces_ja", "parser_surfaces_en", "marker_surfaces_ja", "marker_surfaces_en"):
            if fields.get(key) is not None:
                fields[key] = tuple(fields[key])
        grammar = item.get("english_grammar")
        if grammar:
            fields["english_grammar"] = _EnglishGrammar(
                grammar["lemma"], grammar["lexical_class"], grammar["canonical_form"],
                tuple(grammar["permitted_forms"]),
            )
        words.append(SaijikiWord(**fields))
    return SaijikiCategory(
        key=data["key"], name_ja=data["name_ja"], name_en=data["name_en"],
        marker_class=data["marker_class"], bundle=data["bundle"], words=tuple(words),
        marker_order_ja=tuple(data["marker_order_ja"]) if data.get("marker_order_ja") is not None else None,
        marker_order_en=tuple(data["marker_order_en"]) if data.get("marker_order_en") is not None else None,
    )


SAIJIKI: tuple[SaijikiCategory, ...] = tuple(_category_from_asset(item) for item in CATEGORIES)

# あいだ (関係)。プロンプトの語彙ブロックには出さず、関係節 (散文) が扱う。
# 表示順は SPEC §14.2、格納順は共有 asset の relation テーブル順とする。
RELATIONS: tuple[RelationWord, ...] = (
    RelationWord("along", "沿う", "along", ("前の線に沿って",), ("along the previous line",)),
    RelationWord(
        "not_touching",
        "触れない",
        "not touching",
        ("前の形に触れない",),
        ("not touching the previous shape",),
    ),
    RelationWord(
        "touching",
        "触れる",
        "touching",
        ("前の線に触れる", "前の弧に両端で触れる"),
        ("touching the previous line", "touching the previous arc at both ends"),
        (("前の線に触れる", "line"), ("前の弧に両端で触れる", "arc"),
         ("touching the previous line", "line"), ("touching the previous arc at both ends", "arc")),
    ),
    RelationWord("cutting", "切る", "cutting", ("前の線を切る",), ("cutting the previous line",)),
    RelationWord("between", "間に", "between", ("前の二つの間に",), ("between the previous two",)),
    RelationWord(
        "connected",
        "つながる",
        "connected",
        ("前の形につながる",),
        ("connected to the previous shape",),
    ),
    RelationWord("resting_on", "載る", "resting on", ("前の形に載る",), ("resting on the previous shape",)),
    RelationWord("inside", "中に", "inside", ("前の形の中に",), ("inside the previous shape",)),
    RelationWord(
        "overlapping",
        "重なる",
        "overlaps",
        ("前の形に重なる",),
        ("overlapping the previous shape",),
    ),
    RelationWord("crossing", "横切る", "crossing", ("前の形を横切る",), ("crossing the previous shape",)),
    RelationWord(
        "mirrored",
        "鏡写し",
        "mirrored",
        ("前の形と鏡写し",),
        ("mirrored with the previous shape",),
    ),
)

_RELATION_MARKER_ORDER = {
    "ja": ("触れる", "つながる", "沿う", "横切る", "切る", "触れない", "間に", "載る", "中に", "重なる", "鏡写し"),
    "en": (
        "touching",
        "connected",
        "along",
        "crossing",
        "cutting",
        "not touching",
        "between",
        "resting on",
        "inside",
        "overlaps",
        "mirrored",
    ),
}

_RELATION_DISPLAY_ORDER = (
    "along",
    "not_touching",
    "cutting",
    "between",
    "touching",
    "connected",
    "resting_on",
    "inside",
    "overlapping",
    "crossing",
    "mirrored",
)


def _surface(word: SaijikiWord, lang: str) -> str:
    surface = word.surface(lang)
    if surface is None:
        raise ValueError(f"saijiki word has no {lang} surface: {word.surface_ja}")
    return surface


def _annotated(word: SaijikiWord, lang: str) -> str:
    surface = _surface(word, lang)
    if not word.default:
        return surface
    return f"{surface}(既定)" if lang == "ja" else f"{surface} (default)"


def _prompt_words(category: SaijikiCategory, lang: str) -> tuple[SaijikiWord, ...]:
    return tuple(word for word in category.words_for(lang) if word.prompt)


def prompt_block(lang: str) -> str:
    """共有 asset と同期する歳時記カテゴリブロック (10 行)。"""
    lines = []
    joiner = "、" if lang == "ja" else ", "
    for category in SAIJIKI:
        name = category.name_ja if lang == "ja" else category.name_en
        words = joiner.join(_annotated(word, lang) for word in _prompt_words(category, lang))
        lines.append(f"{name}: {words}")
    return "\n".join(lines)


def texture_material_enumeration(lang: str) -> str:
    """てざわり選択則の素材列挙。ja は「・」結び、en は ', ' + ', or ' 結び。"""
    category = next(c for c in SAIJIKI if c.key == "tezawari")
    surfaces = [_surface(word, lang) for word in _prompt_words(category, lang)]
    if lang == "ja":
        return "・".join(surfaces)
    return ", ".join(surfaces[:-1]) + ", or " + surfaces[-1]


def _marker_surfaces(category: SaijikiCategory, lang: str) -> tuple[str, ...]:
    """カテゴリの有効マーカー表面。marker_order があればその順、なければ語順。"""
    enabled: list[str] = []
    for word in category.words_for(lang):
        if word.is_marker:
            enabled.extend(word.marker_names(lang))
    order = category.marker_order(lang)
    if order is None:
        return tuple(enabled)
    enabled_set = set(enabled)
    ordered = tuple(name for name in order if name in enabled_set)
    # marker_order は膜ではなく順序指定: 所属はフラグが決める。過不足は整合バグ。
    if set(ordered) != enabled_set:
        missing = enabled_set - set(ordered)
        raise ValueError(f"saijiki marker order out of sync for {category.key}/{lang}: {missing}")
    return ordered


def shape_markers(lang: str) -> tuple[str, ...]:
    category = next(c for c in SAIJIKI if c.key == "katachi")
    return _marker_surfaces(category, lang)


def _operation_markers(lang: str) -> tuple[str, ...]:
    category = next(c for c in SAIJIKI if c.key == "ugoki")
    return _marker_surfaces(category, lang)


def _relation_markers(lang: str) -> tuple[str, ...]:
    surfaces = {word.surface(lang) for word in RELATIONS}
    ordered = tuple(name for name in _RELATION_MARKER_ORDER[lang] if name in surfaces)
    if len(ordered) != len(surfaces):
        raise ValueError(f"relation marker order out of sync for {lang}")
    return ordered


def core_grammar_markers(lang: str) -> tuple[str, ...]:
    """旧マーカー表の文法部（図形・動詞・関係）。"""
    return shape_markers(lang) + _operation_markers(lang) + _relation_markers(lang)


# reference §3 と閉包マーカー表のクラス並び (Build 591 互換の歴史的順序)。
_MARKER_CLASS_ORDER = ("material", "color", "variation", "angle", "ratio", "place")


def saijiki_marker_table() -> dict[str, dict[str, tuple[str, ...]]]:
    """reference に残す歳時記修飾カテゴリの旧マーカー表。"""
    by_class = {
        category.marker_class: category
        for category in SAIJIKI
        if category.marker_class not in (None, "shape", "operation")
    }
    if set(by_class) != set(_MARKER_CLASS_ORDER):
        raise ValueError(f"marker class order out of sync: {set(by_class) ^ set(_MARKER_CLASS_ORDER)}")
    return {
        marker_class: {lang: _marker_surfaces(by_class[marker_class], lang) for lang in _LANGS}
        for marker_class in _MARKER_CLASS_ORDER
    }


def relation_literal_markers() -> dict[str, tuple[str, ...]]:
    """共有 asset と同期する relation 固定句の Server projection。"""
    return {word.relation_type: word.literals_ja + word.literals_en for word in RELATIONS}


def reference_categories(lang: str) -> list[tuple[str, tuple[str, ...]]]:
    """reference §1 用: (カテゴリ名, 既定注記付き語列) の一覧。"""
    result: list[tuple[str, tuple[str, ...]]] = []
    for category in SAIJIKI:
        name = category.name_ja if lang == "ja" else category.name_en
        words = tuple(_annotated(word, lang) for word in _prompt_words(category, lang))
        result.append((name, words))
    return result


# おもての「質」9 語だけが SurfaceTexture へ写る。濃い / 薄い は濃さの語であって質では
# なく、Score では surface.density / opacity を動かす。名指しで除くのは、値の無い語を
# 「無いから除く」で拾うと、値を付け忘れた質の語まで静かに通ってしまうため。
_OMOTE_NON_QUALITY_WORDS: tuple[str, ...] = ("濃い", "薄い")


# てざわり語・いろ語・おもての質語 → Score enum 値。値は各二言語語エントリに付属する。
def _surface_value_map(category_key: str, skip: tuple[str, ...] = ()) -> dict[str, str]:
    category = next(c for c in SAIJIKI if c.key == category_key)
    mapping: dict[str, str] = {}
    for word in category.words:
        if word.surface_ja in skip:
            continue
        if word.score_value is None:
            raise ValueError(f"saijiki {category_key} に Score 値のない語がある: {word.surface_ja}")
        for lang in _LANGS:
            surface = word.surface(lang)
            if surface is not None:
                mapping[surface] = word.score_value
    return mapping


def weight_for_surface() -> dict[str, str]:
    """てざわり表層語（日英・削剪語含む）→ Weight 値の対応表。"""
    return _surface_value_map("tezawari")


def color_for_surface() -> dict[str, str]:
    """いろ表層語（日英）→ Color 値の対応表。"""
    return _surface_value_map("iro")


def texture_for_surface() -> dict[str, str]:
    """おもての質 9 語（日英）→ SurfaceTexture 値の対応表。

    てざわり・いろ には同じ形の表が前からあり、おもてだけがそこへ繋がっていなかった。
    塗り が別の真偽値へ行っていたのがその現れで、2026-08-13 の裁定で 1 つの語彙へ戻した。
    """
    return _surface_value_map("omote", skip=_OMOTE_NON_QUALITY_WORDS)


def display_categories(lang: str) -> list[dict[str, object]]:
    """歳時記表示 (Phase 3: API / web スナップショット) 用のカテゴリ一覧。"""
    result: list[dict[str, object]] = []
    for category in SAIJIKI:
        selected = tuple(word for word in category.words_for(lang) if word.display)
        words = tuple(_surface(word, lang) for word in selected)
        ids = tuple(word.id for word in selected)
        facets = tuple(word.facet for word in selected)
        descriptions = tuple((word.description or {}).get(lang) for word in selected)
        # じ の末尾に画面比の宣言（「画面比16:9。」、DDL 26）を置く。地と同じくキャンバス
        # そのものについての文だから。アプリが書く文で、語より先に読まれるので歳時記の
        # 語ではない。表示するが、語として読まず、依頼文にも出さない。
        if category.key == "ji":
            words += ("画面比",) if lang == "ja" else ("aspect ratio",)
            ids += ("aspect_ratio",)
            facets += (None,)
            descriptions += (None,)
        result.append(
            {
                "key": category.key,
                "name_ja": category.name_ja,
                "name_en": category.name_en,
                "bundle": category.bundle,
                "words": words,
                "ids": ids,
                "facets": facets,
                "descriptions": descriptions,
            }
        )
    aida_by_type = {word.relation_type: word for word in RELATIONS}
    result.append(
        {
            "key": "aida",
            "name_ja": "あいだ",
            "name_en": "relations",
            "bundle": "where",
            "words": tuple(aida_by_type[t].surface(lang) for t in _RELATION_DISPLAY_ORDER),
            "ids": _RELATION_DISPLAY_ORDER,
            "facets": (None,) * len(_RELATION_DISPLAY_ORDER),
            "descriptions": (None,) * len(_RELATION_DISPLAY_ORDER),
        }
    )
    return result
