"""inku 歳時記 (Saijiki) — 語彙の単一情報源 (v1.92).

このテーブルが次の消費側の正である:

- Stage 1 プロンプトの語彙ブロックとてざわり列挙 (interpreter.py)
- プラグイン閉包マーカー (plugins/document_format.py)
- Stage 2 の relation 固定句テーブル (composer.py)
- reference §1〜§3 の歳時記・マーカー表 (reference.py)
- 歳時記表示の配信 (Phase 3: GET /api/saijiki と web スナップショット)

Score schema (schema.py) の enum は従来どおり Score 側の正であり、ここからは
導出しない。語彙から消えた語 (例: 描く) も保存済み Score の受理・Replay のため
schema からは削除しない。

フラグの意味:
- prompt:  Stage 1 語彙ブロック・列挙へ出す
- display: 歳時記表示 (web / API) へ出す
- marker:  プラグイン閉包マーカーにする (None = prompt に従う)

順序の扱い: words は Stage 1 プロンプトの表示順で持つ。閉包マーカーの順序が
プロンプト順と異なるカテゴリ (かたち・うごき・あいだ) は marker_order_* で明示する。
順序は表示・互換のための指定であり、所属 (membership) は常に語の
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
    surface_ja: str
    surface_en: str | None
    default: bool = False  # プロンプトで「(既定)」/" (default)" を付ける
    prompt: bool = True  # Stage 1 語彙ブロック・列挙へ出す
    display: bool = True  # 歳時記表示 (web / API) へ出す
    marker: bool | None = None  # 閉包マーカー所属 (None = prompt に従う)
    score_value: str | None = None  # Weight / Color / SurfaceTexture の Score enum 値
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
    # 閉包マーカーの順序がプロンプト順と異なる場合の明示順 (marker 表面名で指定)
    marker_order_ja: tuple[str, ...] | None = None
    marker_order_en: tuple[str, ...] | None = None

    def words_for(self, lang: str) -> tuple[SaijikiWord, ...]:
        return tuple(word for word in self.words if word.surface(lang) is not None)

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


def _w(surface_ja: str, surface_en: str | None, **kwargs: object) -> SaijikiWord:
    return SaijikiWord(surface_ja, surface_en, **kwargs)  # type: ignore[arg-type]


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
        words=(
            _w("円", "circle"),
            _w("楕円", "ellipse"),
            _w("三角", "triangle"),
            _w("四角", "square"),
            _w("線", "line"),
            _w("弧", "arc"),
            _w("雲形", "cloudform"),
            _w("多角形", "polygon", **_HIDDEN_MARKER),
        ),
        marker_order_ja=("線", "円", "楕円", "三角", "四角", "多角形", "弧", "雲形"),
        marker_order_en=("line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform"),
    ),
    SaijikiCategory(
        key="katamuki",
        name_ja="かたむき",
        name_en="angles",
        marker_class="angle",
        words=(
            _w("水平", "horizontal"),
            _w("垂直", "vertical"),
            _w("斜め", "diagonal"),
            _w("右上がり", "rising"),
            _w("右下がり", "falling"),
            _w("回転", "rotated"),
        ),
    ),
    SaijikiCategory(
        key="tezawari",
        name_ja="てざわり",
        name_en="touches",
        marker_class="material",
        words=(
            _w("銀筆", "silverpoint", score_value="silverpoint"),
            _w("鉛筆", "pencil", score_value="pencil"),
            _w("ペン", "pen", default=True, score_value="pen"),
            _w("ロットリング", "rotring", score_value="rotring"),
            _w("クレヨン", "crayon", score_value="crayon"),
            _w("チョーク", "chalk", score_value="chalk"),
            _w("細筆", "fine-brush", score_value="brush_thin"),
            _w("太筆", "thick-brush", score_value="brush_thick"),
            _w("ビュラン", "burin", score_value="burin"),
            _w("ドライポイント", "drypoint", score_value="drypoint"),
            _w("コンピュータ", "computer", score_value="computer"),
        ),
    ),
    SaijikiCategory(
        key="tsuranari",
        name_ja="つらなり",
        name_en="continuity",
        marker_class=None,  # 現行どおり閉包マーカーには出さない
        words=(
            _w("実線", "solid", default=True),
            _w("破線", "dashed"),
            _w("点線", "dotted"),
            _w("一点鎖線", "dash-dot"),
        ),
    ),
    SaijikiCategory(
        key="omote",
        name_ja="おもて",
        name_en="surfaces",
        # No closure markers, exactly as つらなり has none: this category says how
        # an interior is, not what to place, so the plugin closure never quotes it.
        marker_class=None,
        words=(
            _w("空", "empty", default=True, score_value="none"),
            _w("塗り", "flat", score_value="solid"),
            _w("薄墨", "pale ink wash", score_value="wash"),
            _w("粒", "grain", score_value="grain"),
            _w("点", "stipple", score_value="stipple"),
            _w("平行線", "hatch", score_value="hatch"),
            _w("交差線", "crosshatch", score_value="crosshatch"),
            _w("にじみ", "bleeding", score_value="bleed"),
            _w("アクアチント", "aquatint", score_value="aquatint"),
            _w("濃い", "dense"),
            _w("薄い", "faint"),
        ),
    ),
    SaijikiCategory(
        key="ji",
        name_ja="じ",
        name_en="grounds",
        # No closure markers, for the same reason おもて has none: this category
        # says how the support is, not what to place on it, so the plugin
        # closure never quotes it.
        marker_class=None,
        words=(
            # `plain` is deliberately absent. Asking for no ground is not a word
            # you can say -- it is what you get by saying nothing.
            _w("紙", "paper", score_value="paper"),
            _w("和紙", "washi", score_value="washi"),
            _w("薄墨地", "ink wash ground", score_value="ink_wash"),
            _w("木炭地", "charcoal ground", score_value="charcoal_ground"),
            # 「カンバス」, not 「キャンバス」: the web already spells the sheet's
            # own proportion キャンバス, and one screen must not use one word for
            # two things.
            _w("カンバス", "canvas", score_value="canvas"),
            _w("画用紙", "drawing paper", score_value="drawing_paper"),
            _w("メゾチント", "mezzotint", score_value="mezzotint"),
        ),
    ),
    SaijikiCategory(
        key="iro",
        name_ja="いろ",
        name_en="colors",
        marker_class="color",
        words=(
            _w("白", "white", score_value="white"),
            _w("黒", "black", default=True, score_value="black"),
            _w("青", "blue", score_value="blue"),
            _w("赤", "red", score_value="red"),
            _w("緑", "green", score_value="green"),
            _w("灰", "gray", score_value="gray"),
            _w("黄", "yellow", score_value="yellow"),
            _w("橙", "orange", score_value="orange"),
            _w("紫", "purple", score_value="purple"),
        ),
    ),
    SaijikiCategory(
        key="yuragi",
        name_ja="ゆらぎ",
        name_en="movements",
        marker_class="variation",
        words=(
            _w("細かく", "fine"),
            _w("大きく", "large"),
            _w("ゆっくり", "slowly"),
            _w("速く", "quickly"),
            _w("揺れる", "swaying"),
            _w("波打つ", "undulating"),
            _w("震える", "trembling"),
            _w("滲む", "blurring"),
        ),
    ),
    SaijikiCategory(
        key="basho",
        name_ja="ばしょ",
        name_en="places",
        marker_class="place",
        words=(
            _w("上", "top"),
            _w("下", "bottom"),
            _w("中央", "center"),
            _w("左端", "left-edge"),
            _w("右端", "right-edge"),
            _w("上端", "top-edge"),
            _w("下端", "bottom-edge"),
            _w("中心", "middle"),
            _w("隅", "corner"),
        ),
    ),
    SaijikiCategory(
        key="ugoki",
        name_ja="うごき",
        name_en="motions",
        marker_class="operation",
        words=(
            _w("置く", "place"),
            # 従来の閉包マーカー「arrange」を互換のため保持する (語彙は line-up)。
            _w("並べる", "line-up", marker_surfaces_en=("arrange",)),
            _w("引く", "draw"),
            # 日本語だけに残す削剪済みの墓標。英語の draw は「引く」の対訳。
            _w("描く", None, **_PRUNED),
            _w("散らす", "scatter"),
            _w("埋める", "fill"),
            _w("敷き詰める", "tile"),
        ),
        marker_order_ja=("置く", "引く", "並べる", "散らす", "敷き詰める", "描く", "埋める"),
        marker_order_en=("place", "draw", "arrange", "scatter", "tile", "fill"),
    ),
    SaijikiCategory(
        key="wariai",
        name_ja="わりあい",
        name_en="proportions",
        marker_class="ratio",
        words=(
            _w("縦長", "tall"),
            _w("横長", "wide"),
            _w("全幅", "full-width"),
            _w("半幅", "half-width"),
            _w("半円", "semicircle"),
            _w("上弦", "waxing"),
            _w("下弦", "waning"),
            _w("三日月", "crescent"),
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
    """Stage 1 プロンプトの歳時記カテゴリブロック (10 行)。"""
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
        words = tuple(
            _surface(word, lang) for word in category.words_for(lang) if word.display
        )
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
