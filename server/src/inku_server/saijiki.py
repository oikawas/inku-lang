"""inku 歳時記 (Saijiki) — 語彙の単一情報源 (v1.92).

このテーブルが次の消費側の正である:

- Stage 1 プロンプトの語彙ブロックとてざわり列挙 (interpreter.py)
- プラグイン閉包マーカー (plugins/document_format.py)
- Stage 2 の relation 固定句テーブル (composer.py)
- reference §1〜§3 の歳時記・マーカー表 (reference.py)
- 歳時記表示の配信 (Phase 3: GET /api/saijiki と web スナップショット)

Score schema (schema.py) の enum は従来どおり Score 側の正であり、ここからは
導出しない。語彙から消えた語 (例: 髪) も保存済み Score の受理・Replay のため
schema からは削除しない。

フラグの意味:
- prompt:  Stage 1 語彙ブロック・列挙へ出す
- display: 歳時記表示 (web / API) へ出す
- marker:  プラグイン閉包マーカーにする (None = prompt に従う)

順序の扱い: words_* は Stage 1 プロンプトの表示順で持つ。閉包マーカーの順序が
プロンプト順と異なるカテゴリ (かたち・うごき・あいだ) は marker_order_* で
明示する。順序は表示・互換のための指定であり、所属 (membership) は常に語の
フラグから導出される。
"""

from __future__ import annotations

from dataclasses import dataclass

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
class SaijikiWord:
    surface: str
    default: bool = False  # プロンプトで「(既定)」/" (default)" を付ける
    prompt: bool = True  # Stage 1 語彙ブロック・列挙へ出す
    display: bool = True  # 歳時記表示 (web / API) へ出す
    marker: bool | None = None  # 閉包マーカー所属 (None = prompt に従う)
    # マーカー表面の上書き。例: en「line-up」は互換のため従来マーカー「arrange」を保つ。
    marker_surfaces: tuple[str, ...] | None = None

    @property
    def is_marker(self) -> bool:
        return self.prompt if self.marker is None else self.marker

    def marker_names(self) -> tuple[str, ...]:
        return self.marker_surfaces if self.marker_surfaces is not None else (self.surface,)


@dataclass(frozen=True)
class SaijikiCategory:
    key: str
    name_ja: str
    name_en: str
    # reference §3 のマーカー分類名。None はマーカーへ出さないカテゴリ (つらなり)。
    marker_class: str | None
    words_ja: tuple[SaijikiWord, ...]
    words_en: tuple[SaijikiWord, ...]
    # 閉包マーカーの順序がプロンプト順と異なる場合の明示順 (marker 表面名で指定)
    marker_order_ja: tuple[str, ...] | None = None
    marker_order_en: tuple[str, ...] | None = None

    def words(self, lang: str) -> tuple[SaijikiWord, ...]:
        return self.words_ja if lang == "ja" else self.words_en

    def marker_order(self, lang: str) -> tuple[str, ...] | None:
        return self.marker_order_ja if lang == "ja" else self.marker_order_en


@dataclass(frozen=True)
class RelationWord:
    relation_type: str  # relation.type (schema / composer と共通)
    surface_ja: str
    surface_en: str
    literals_ja: tuple[str, ...]  # 正規化DDLの固定 previous-object 句
    literals_en: tuple[str, ...]

    def surface(self, lang: str) -> str:
        return self.surface_ja if lang == "ja" else self.surface_en


def _w(surface: str, **kwargs: object) -> SaijikiWord:
    return SaijikiWord(surface, **kwargs)  # type: ignore[arg-type]


# 多角形/polygon は Score primitive としてマーカーに残すが、歳時記語彙ではない。
_HIDDEN_MARKER = {"prompt": False, "display": False, "marker": True}
# 削剪済みの語 (作者裁定 2026-07-18): 表示・プロンプト・マーカーすべてから外す。
_PRUNED = {"prompt": False, "display": False, "marker": False}

SAIJIKI: tuple[SaijikiCategory, ...] = (
    SaijikiCategory(
        key="katachi",
        name_ja="かたち",
        name_en="forms",
        marker_class="shape",
        words_ja=(
            _w("円"),
            _w("楕円"),
            _w("三角"),
            _w("四角"),
            _w("線"),
            _w("弧"),
            _w("雲形"),
            _w("多角形", **_HIDDEN_MARKER),
        ),
        words_en=(
            _w("circle"),
            _w("ellipse"),
            _w("triangle"),
            _w("square"),
            _w("line"),
            _w("arc"),
            _w("cloudform"),
            _w("polygon", **_HIDDEN_MARKER),
        ),
        marker_order_ja=("線", "円", "楕円", "三角", "四角", "多角形", "弧", "雲形"),
        marker_order_en=("line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform"),
    ),
    SaijikiCategory(
        key="katamuki",
        name_ja="かたむき",
        name_en="angles",
        marker_class="angle",
        words_ja=(_w("水平"), _w("垂直"), _w("斜め"), _w("右上がり"), _w("右下がり"), _w("回転")),
        words_en=(_w("horizontal"), _w("vertical"), _w("diagonal"), _w("rising"), _w("falling"), _w("rotated")),
    ),
    SaijikiCategory(
        key="tezawari",
        name_ja="てざわり",
        name_en="touches",
        marker_class="material",
        words_ja=(
            _w("髪", **_PRUNED),  # P0-3 削除 (Score Weight は互換のため維持)
            _w("鉛筆"),
            _w("ペン", default=True),
            _w("ロットリング"),
            _w("クレヨン"),
            _w("チョーク"),
            _w("細筆"),
            _w("太筆"),
            _w("ビュラン"),
            _w("ドライポイント"),
        ),
        words_en=(
            _w("hair", **_PRUNED),  # P0-3 削除
            _w("pencil"),
            _w("pen", default=True),
            _w("rotring"),
            _w("crayon"),
            _w("chalk"),
            _w("fine-brush"),
            _w("thick-brush"),
            _w("burin"),
            _w("drypoint"),
        ),
    ),
    SaijikiCategory(
        key="tsuranari",
        name_ja="つらなり",
        name_en="continuity",
        marker_class=None,  # 現行どおり閉包マーカーには出さない
        words_ja=(_w("実線", default=True), _w("破線"), _w("点線"), _w("一点鎖線")),
        words_en=(_w("solid", default=True), _w("dashed"), _w("dotted"), _w("dash-dot")),
    ),
    SaijikiCategory(
        key="iro",
        name_ja="いろ",
        name_en="colors",
        marker_class="color",
        words_ja=(_w("白"), _w("黒", default=True), _w("青"), _w("赤"), _w("緑"), _w("灰")),
        words_en=(_w("white"), _w("black", default=True), _w("blue"), _w("red"), _w("green"), _w("gray")),
    ),
    SaijikiCategory(
        key="yuragi",
        name_ja="ゆらぎ",
        name_en="movements",
        marker_class="variation",
        words_ja=(
            _w("細かく"),
            _w("大きく"),
            _w("ゆっくり"),
            _w("速く"),
            _w("揺れる"),
            _w("波打つ"),
            _w("震える"),
            _w("滲む"),
        ),
        words_en=(
            _w("fine"),
            _w("large"),
            _w("slowly"),
            _w("quickly"),
            _w("swaying"),
            _w("undulating"),
            _w("trembling"),
            _w("blurring"),
        ),
    ),
    SaijikiCategory(
        key="basho",
        name_ja="ばしょ",
        name_en="places",
        marker_class="place",
        words_ja=(
            _w("上"),
            _w("下"),
            _w("中央"),
            _w("左端"),
            _w("右端"),
            _w("上端"),
            _w("下端"),
            _w("中心"),
            _w("隅"),
        ),
        words_en=(
            _w("top"),
            _w("bottom"),
            _w("center"),
            _w("left-edge"),
            _w("right-edge"),
            _w("top-edge"),
            _w("bottom-edge"),
            _w("middle"),
            _w("corner"),
        ),
    ),
    SaijikiCategory(
        key="ugoki",
        name_ja="うごき",
        name_en="motions",
        marker_class="operation",
        words_ja=(
            _w("置く"),
            _w("並べる"),
            _w("引く"),
            _w("描く", **_PRUNED),  # P0-2b 削除
            _w("散らす"),
            _w("埋める"),
            _w("敷き詰める"),
        ),
        words_en=(
            _w("place"),
            # 従来の閉包マーカー「arrange」を互換のため保持する (語彙は line-up)。
            _w("line-up", marker_surfaces=("arrange",)),
            _w("fill"),
            _w("scatter"),
            _w("draw"),  # 引く の対訳。ja「描く」の削剪後も en マーカーとして残る
            _w("tile"),
        ),
        marker_order_ja=("置く", "引く", "並べる", "散らす", "敷き詰める", "描く", "埋める"),
        marker_order_en=("place", "draw", "arrange", "scatter", "tile", "fill"),
    ),
    SaijikiCategory(
        key="wariai",
        name_ja="わりあい",
        name_en="proportions",
        marker_class="ratio",
        words_ja=(
            _w("縦長"),
            _w("横長"),
            _w("全幅"),
            _w("半幅"),
            _w("半円"),
            _w("上弦"),
            _w("下弦"),
            _w("三日月"),
        ),
        words_en=(
            _w("tall"),
            _w("wide"),
            _w("full-width"),
            _w("half-width"),
            _w("semicircle"),
            _w("waxing"),
            _w("waning"),
            _w("crescent"),
        ),
    ),
)

# あいだ (関係)。プロンプトの語彙ブロックには出さず、関係節 (散文) が扱う。
# 表示順は SPEC §14.2 (沿う/触れない/切る/間に/触れる)、格納順は composer の
# relation テーブル順 (along/not_touching/touching/cutting/between) とする。
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
    ),
    RelationWord("cutting", "切る", "cutting", ("前の線を切る",), ("cutting the previous line",)),
    RelationWord("between", "間に", "between", ("前の二つの間に",), ("between the previous two",)),
)

_RELATION_MARKER_ORDER = {
    "ja": ("触れる", "沿う", "切る", "触れない", "間に"),
    "en": ("touching", "along", "cutting", "not touching", "between"),
}

_RELATION_DISPLAY_ORDER = ("along", "not_touching", "cutting", "between", "touching")


def _annotated(word: SaijikiWord, lang: str) -> str:
    if not word.default:
        return word.surface
    return f"{word.surface}(既定)" if lang == "ja" else f"{word.surface} (default)"


def _prompt_words(category: SaijikiCategory, lang: str) -> tuple[SaijikiWord, ...]:
    return tuple(word for word in category.words(lang) if word.prompt)


def prompt_block(lang: str) -> str:
    """Stage 1 プロンプトの歳時記カテゴリブロック (9 行)。"""
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
    surfaces = [word.surface for word in _prompt_words(category, lang)]
    if lang == "ja":
        return "・".join(surfaces)
    return ", ".join(surfaces[:-1]) + ", or " + surfaces[-1]


def _marker_surfaces(category: SaijikiCategory, lang: str) -> tuple[str, ...]:
    """カテゴリの有効マーカー表面。marker_order があればその順、なければ語順。"""
    enabled: list[str] = []
    for word in category.words(lang):
        if word.is_marker:
            enabled.extend(word.marker_names())
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
    """閉包マーカーの文法部 (図形 + 動詞 + 関係)。構造マーカー (anchor 等) は
    プラグイン層 (document_format) が所有し、この前に連結する。"""
    return shape_markers(lang) + _operation_markers(lang) + _relation_markers(lang)


# reference §3 と閉包マーカー表のクラス並び (Build 591 互換の歴史的順序)。
_MARKER_CLASS_ORDER = ("material", "color", "variation", "angle", "ratio", "place")


def saijiki_marker_table() -> dict[str, dict[str, tuple[str, ...]]]:
    """歳時記修飾カテゴリのマーカー表 (document_format._SAIJIKI_MARKERS の正)。"""
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
    """Stage 2 (composer) の relation 固定句テーブルの正。"""
    return {word.relation_type: word.literals_ja + word.literals_en for word in RELATIONS}


def reference_categories(lang: str) -> list[tuple[str, tuple[str, ...]]]:
    """reference §1 用: (カテゴリ名, 既定注記付き語列) の一覧。"""
    result: list[tuple[str, tuple[str, ...]]] = []
    for category in SAIJIKI:
        name = category.name_ja if lang == "ja" else category.name_en
        words = tuple(_annotated(word, lang) for word in _prompt_words(category, lang))
        result.append((name, words))
    return result


def display_categories(lang: str) -> list[dict[str, object]]:
    """歳時記表示 (Phase 3: API / web スナップショット) 用のカテゴリ一覧。"""
    result: list[dict[str, object]] = []
    for category in SAIJIKI:
        words = tuple(word.surface for word in category.words(lang) if word.display)
        result.append(
            {
                "key": category.key,
                "name_ja": category.name_ja,
                "name_en": category.name_en,
                "words": words,
            }
        )
    aida_by_type = {word.relation_type: word for word in RELATIONS}
    result.append(
        {
            "key": "aida",
            "name_ja": "あいだ",
            "name_en": "relations",
            "words": tuple(aida_by_type[t].surface(lang) for t in _RELATION_DISPLAY_ORDER),
        }
    )
    return result
