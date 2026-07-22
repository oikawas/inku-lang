"""v1.92 歳時記構造化の golden 検査 (allow-list 方式)。

fixture (tests/fixtures/prompts/) は構造化前 (Build 591 / v1.91 クローズ時点) の
Stage 1 プロンプト全文。許可差分は作者裁定による語彙削剪と語順修正のみ:

- ja: 「髪、」「髪・」の除去 (P0-3)、「描く、」×2 の除去 (P0-2b) — 2026-07-18
- en: "hair, " ×2 の除去 (P0-3) — 2026-07-18
- en: うごき の語順を words_ja と同順へ修正 (2026-07-22)。web の歳時記パネルは
  両言語の表示リストを位置で突き合わせるため、引く=draw / 埋める=fill の対応が
  位置で成立している必要がある

これ以外の差分 (空白・順序・行の脱落 = 組み立てバグ) はテスト失敗とする。
"""

from pathlib import Path

from inku_server import saijiki
from inku_server.composer import _RELATION_LITERAL_MARKERS
from inku_server.interpreter import SYSTEM_PROMPT_PREFIX, SYSTEM_PROMPT_PREFIX_EN
from inku_server.plugins.document_format import _CORE_MARKERS, _SAIJIKI_MARKERS, _SHAPE_MARKERS

_FIXTURES = Path(__file__).parent / "fixtures" / "prompts"

# (置換対象, 期待出現回数)。回数を固定して、意図しない箇所への波及を検出する。
_ALLOWED_JA = (("髪、", 1), ("髪・", 1), ("描く、", 2))
_ALLOWED_EN = (("hair, ", 2),)

# (置換対象, 置換後, 期待出現回数)。削剪では表せない許可差分 (語順修正)。
_REORDERED_JA: tuple[tuple[str, str, int], ...] = ()
_REORDERED_EN = (("line-up, fill, scatter, draw, tile", "line-up, draw, scatter, fill, tile", 1),)


def _expected(
    fixture_name: str,
    allowed: tuple[tuple[str, int], ...],
    reordered: tuple[tuple[str, str, int], ...] = (),
) -> str:
    text = (_FIXTURES / fixture_name).read_text(encoding="utf-8")
    for needle, count in allowed:
        assert text.count(needle) == count, f"fixture drift: {needle!r} x{text.count(needle)}"
        text = text.replace(needle, "")
    for needle, replacement, count in reordered:
        assert text.count(needle) == count, f"fixture drift: {needle!r} x{text.count(needle)}"
        text = text.replace(needle, replacement)
    return text


def test_stage1_prompt_ja_matches_golden_with_pruning() -> None:
    assert SYSTEM_PROMPT_PREFIX == _expected(
        "stage1_prefix_ja.golden.txt", _ALLOWED_JA, _REORDERED_JA
    )


def test_stage1_prompt_en_matches_golden_with_pruning() -> None:
    assert SYSTEM_PROMPT_PREFIX_EN == _expected(
        "stage1_prefix_en.golden.txt", _ALLOWED_EN, _REORDERED_EN
    )


# --- 閉包マーカーの golden (Build 591 の実表から削剪分のみを除いた期待値) ---

_EXPECTED_CORE_MARKERS = {
    "ja": (
        "anchor", "{領域:", "領域",
        "線", "円", "楕円", "三角", "四角", "多角形", "弧", "雲形",
        "置く", "引く", "並べる", "散らす", "敷き詰める", "埋める",  # 描く 削剪
        "触れる", "沿う", "切る", "触れない", "間に",
        "鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント",  # 髪 削剪
        "白", "黒", "青", "赤", "緑", "灰",
        "細かく", "大きく", "ゆっくり", "速く", "揺れる", "波打つ", "震える", "滲む",
        "水平", "垂直", "斜め", "右上がり", "右下がり", "回転",
        "縦長", "横長", "全幅", "半幅", "半円", "上弦", "下弦", "三日月",
        "上", "下", "中央", "左端", "右端", "上端", "下端", "中心", "隅",
    ),
    "en": (
        "anchor", "{region:", "region",
        "line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform",
        "place", "draw", "arrange", "scatter", "tile", "fill",
        "touching", "along", "cutting", "not touching", "between",
        "pencil", "pen", "rotring", "crayon", "chalk", "fine-brush", "thick-brush", "burin", "drypoint",  # hair 削剪
        "white", "black", "blue", "red", "green", "gray",
        "fine", "large", "slowly", "quickly", "swaying", "undulating", "trembling", "blurring",
        "horizontal", "vertical", "diagonal", "rising", "falling", "rotated",
        "tall", "wide", "full-width", "half-width", "semicircle", "waxing", "waning", "crescent",
        "top", "bottom", "center", "left-edge", "right-edge", "top-edge", "bottom-edge", "middle", "corner",
    ),
}


def test_core_markers_match_golden() -> None:
    assert _CORE_MARKERS == _EXPECTED_CORE_MARKERS


def test_shape_markers_match_golden() -> None:
    assert _SHAPE_MARKERS == {
        "ja": ("線", "円", "楕円", "三角", "四角", "多角形", "弧", "雲形"),
        "en": ("line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform"),
    }


def test_saijiki_marker_table_excludes_pruned_words() -> None:
    assert "髪" not in _SAIJIKI_MARKERS["material"]["ja"]
    assert "hair" not in _SAIJIKI_MARKERS["material"]["en"]
    assert _SAIJIKI_MARKERS["material"]["ja"][0] == "鉛筆"


def test_relation_literal_markers_match_golden() -> None:
    assert _RELATION_LITERAL_MARKERS == {
        "along": ("前の線に沿って", "along the previous line"),
        "not_touching": ("前の形に触れない", "not touching the previous shape"),
        "touching": (
            "前の線に触れる",
            "前の弧に両端で触れる",
            "touching the previous line",
            "touching the previous arc at both ends",
        ),
        "cutting": ("前の線を切る", "cutting the previous line"),
        "between": ("前の二つの間に", "between the previous two"),
    }
    assert list(_RELATION_LITERAL_MARKERS) == ["along", "not_touching", "touching", "cutting", "between"]


# --- 受け入れ②: パーサ経由 (A-1) とテーブル直接参照の同値 ---

def test_prompt_parse_equals_table_reference() -> None:
    from inku_server.reference import _parse_saijiki_block

    parsed_ja = _parse_saijiki_block(SYSTEM_PROMPT_PREFIX, "# Saijiki (歳時記)", "、")
    parsed_en = _parse_saijiki_block(SYSTEM_PROMPT_PREFIX_EN, "# Saijiki (Vocabulary)", ",")
    assert parsed_ja == {name: list(words) for name, words in saijiki.reference_categories("ja")}
    assert parsed_en == {name: list(words) for name, words in saijiki.reference_categories("en")}


# --- 表示系 (Phase 3 で配信する形) の削剪確認 ---

def test_display_categories_exclude_pruned_and_hidden_words() -> None:
    for lang, pruned, hidden in (("ja", {"髪", "描く"}, {"多角形"}), ("en", {"hair"}, {"polygon"})):
        categories = saijiki.display_categories(lang)
        words = {word for category in categories for word in category["words"]}
        assert not (pruned & words)
        assert not (hidden & words)
    aida = saijiki.display_categories("ja")[-1]
    assert aida["key"] == "aida"
    assert aida["words"] == ("沿う", "触れない", "切る", "間に", "触れる")
