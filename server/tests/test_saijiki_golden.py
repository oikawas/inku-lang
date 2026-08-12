"""v1.92 歳時記構造化の golden 検査 (allow-list 方式)。

fixture (tests/fixtures/prompts/) は構造化前 (Build 591 / v1.91 クローズ時点) の
Stage 1 プロンプト全文。許可差分は作者裁定による語彙削剪と語順修正のみ:

- ja: 「描く、」×2 の除去 (P0-2b) — 2026-07-18
- ja/en: 「髪」→「銀筆」/ "hair" -> "silverpoint" の改名 (2026-07-27)。P0-3 で削剪した
  語だが、画材として存在しない名前だったのが理由なので、改名して語彙へ戻した
- en: うごき の語順を日本語と同順へ修正 (2026-07-22)。web の歳時記パネルは
  両言語の表示リストを位置で突き合わせるため、引く=draw / 埋める=fill の対応が
  二言語語エントリから同順で導出される必要がある
- ja/en: プロンプト内部矛盾の解消 (2026-07-27)。原則が禁じる語を後段の規則や
  語彙表が要求していた 6 件を、作者裁定に沿って整合させた:
  背景の定型を許可動詞へ (塗りつぶす→埋める)、てざわり必須規則の例外の明記、
  原則5 を実態 (語彙 + 本書が定める定型) へ、未知対象の近似先から多角形を削除
  (saijiki.py が歳時記語彙ではないと定めているため)、許可動詞へ 敷き詰める/tile を
  追加 (うごき の語彙表と 1 語ずれていた)、en の rise/fall を運動語として書き分け
  (かたむきの rising/falling は語彙)、ペン(既定) を既定値であって推奨値ではないと明示
- ja/en: 背景色を抽象九色へ開放 (2026-08-02・契約 background-color-openness)。
  背景の色集合を 5 色に限る記述と gray の名指しの禁止を落とした。本番 DB 2,061 作品で
  背景に出ていたのは白・黒・青の 3 色だけで、黄・橙は全期間 0 件だった
- ja/en: 歳時記に おもて / surfaces カテゴリを新設 (2026-08-12・契約
  a-shape-can-say-how-its-surface-is・裁定 RULING-omote-surface-category-20260812)。
  差分は 2 箇所ずつある。① 語彙ブロックに つらなり の直後の 1 行が増える。
  ② 面の定型が状態の名詞へ揃い、「面: 塗り。」と「面: 濃い。」/「面: 薄い。」が加わる。
  ②の中に段 4 (欠陥 A) の実体がある: Stage 1 は「面: 斜めに埋める。」と書き
  Stage 2 の対応表は「平行線」を読んでいて、その語は表に無かった (DDL に 4 件出て
  Score に 0 件)。両側を 平行線 / hatch へ揃えた。fixture は再生成していない

これ以外の差分 (空白・順序・行の脱落 = 組み立てバグ) はテスト失敗とする。
"""

from pathlib import Path

from inku_server import saijiki
from inku_server.composer import _RELATION_LITERAL_MARKERS
from inku_server.interpreter import SYSTEM_PROMPT_PREFIX, SYSTEM_PROMPT_PREFIX_EN
from inku_server.plugins.document_format import _CORE_MARKERS, _SAIJIKI_MARKERS, _SHAPE_MARKERS

_FIXTURES = Path(__file__).parent / "fixtures" / "prompts"

# (置換対象, 期待出現回数)。回数を固定して、意図しない箇所への波及を検出する。
_ALLOWED_JA = (("描く、", 2),)
_ALLOWED_EN: tuple[tuple[str, int], ...] = ()

# (置換対象, 置換後, 期待出現回数)。削剪では表せない許可差分 (語順修正)。
_REORDERED_JA = (
    ("髪、", "銀筆、", 1),
    ("髪・", "銀筆・", 1),
    ("ビュラン・ドライポイントのいずれか", "ビュラン・ドライポイント・コンピュータのいずれか", 1),
    ("ビュラン、ドライポイント\n", "ビュラン、ドライポイント、コンピュータ\n", 1),
    # --- 2026-07-27: 内部矛盾の解消 ---
    (
        "使える動作動詞: 置く、並べる、引く、散らす、埋める\n",
        "使える動作動詞: 置く、並べる、引く、散らす、埋める、敷き詰める\n",
        1,
    ),
    (
        "5. 使えるのは Saijiki の語彙のみ\n",
        "5. 使えるのは Saijiki の語彙と、本書が定める次の定型だけ: "
        "「面: ...」「地: ...」の質感句、版画技法の固定句、関係の previous-object 句、色とりどりの色列挙\n",
        1,
    ),
    (
        "最も近いてざわりを選ぶ。毎回ペンに寄せない。",
        "最も近いてざわりを選ぶ。ペンは未指定時の既定値であって推奨値ではない。機械的にペンへ寄せない。",
        1,
    ),
    (
        "てざわりのない線・弧の文を出力してはいけない。\n",
        "てざわりのない線・弧の文を出力してはいけない。\n"
        "ただし、関係（あいだ）の定型句・わりあい（半円・上弦・下弦・三日月）・かたむきだけを示す最小の文は、"
        "てざわりを省いてよい。\n",
        1,
    ),
    ("→ 「背景を○色で塗りつぶす。」", "→ 「背景を○色で埋める。」", 1),
    (
        "→ 「背景を黒で塗りつぶす。白い横線を中央に引く。」",
        "→ 「背景を黒で埋める。白い横線を中央に引く。」",
        1,
    ),
    ("「背景を灰で塗りつぶす」を出力してはいけない。", "「背景を灰で埋める」を出力してはいけない。", 1),
    ("・線・弧・多角形で近似する。", "・線・弧で近似する。", 1),
    # --- 2026-07-28: engine 16 段 3 = 太さの軸 ---
    # 太さを道具から独立した寸法として書く節。てざわりの節を変えずに足す
    # (太さを理由にてざわりを変えさせないため)。
    (
        "# 数量表現\n",
        "# 太さ — てざわりとは別に書く\n"
        "\n"
        "線の太さは、てざわりとは別に書く。既定より細いときだけ書く（太い指定は無い）。\n"
        "\n"
        "- 細い、細線、糸のような、髪のような → 「細い」と明記する\n"
        "- 極細、きわめて細い、引っかき傷のような → 「極細」と明記する\n"
        "\n"
        "太さは DDL に明示する: 「極細の黒い線」「細いペンの横線」。\n"
        "太さを理由にてざわりを変えない。細さの語があってもてざわりは質感から選ぶ。\n"
        "\n"
        "# 数量表現\n",
        1,
    ),
    # --- 2026-08-02: 契約 background-color-openness = 背景を抽象九色へ開放 ---
    # 背景色の集合を 5 色に限る記述と、gray の名指しの禁止を落とす。
    # 前の 2026-07-27 の項が「塗りつぶす」→「埋める」を済ませた後に当てる。
    (
        "強い単色背景（黒・赤・青・緑）は、",
        "強い単色背景（黒・灰・赤・橙・黄・緑・青・紫）は、",
        1,
    ),
    (
        "- 「背景を灰で埋める」を出力してはいけない。"
        "入力が灰色背景を求めても、背景は白・黒・青・赤・緑の文脈に合う色へ置き換える\n"
        "- 灰色は背景ではなく、必要なときだけ前景の線・点・四角の色として使う。",
        "- 入力が灰色背景を求めたら「背景を灰で埋める」と出力してよい。"
        "背景は白・黒・灰・赤・橙・黄・緑・青・紫の抽象九色から文脈に合う色を選ぶ\n"
        "- 灰色は背景にも、前景の線・点・四角の色にも使える。",
        1,
    ),
    # --- 2026-08-12: 契約 a-shape-can-say-how-its-surface-is = おもての新設 ---
    # 面の定型を状態の名詞へ揃え、「面: 塗り。」と濃さの 2 語を足す。
    # 「面: 斜めに埋める。」→「面: 平行線。」が段 4 (欠陥 A) の実体。
    (
        "- 点で埋める、点描の面 → 「面: 点で埋める。」\n"
        "- 斜線で埋める、ハッチ → 「面: 斜めに埋める。」\n"
        "- 粒立つ、かすれ → 「面: 粒立つ。」\n"
        "- 薄墨で満たす、水彩の面 → 「面: 薄墨。」\n"
        "- 端が滲む → 「面: 滲む。」\n",
        "- 塗る、塗りつぶす、ベタ、中を塗る、面で満たす → 「面: 塗り。」\n"
        "- 点で埋める、点描の面 → 「面: 点。」\n"
        "- 斜線で埋める、ハッチ → 「面: 平行線。」\n"
        "- 粒立つ、かすれ → 「面: 粒。」\n"
        "- 薄墨で満たす、水彩の面 → 「面: 薄墨。」\n"
        "- 端が滲む → 「面: にじみ。」\n"
        "- 面の中身が濃い、密、深い → 「面: 濃い。」。面の中身が薄い、淡い、かすか → 「面: 薄い。」。"
        "他の面の語と併せるときは「面: 塗り（濃い）。」「面: 薄墨（薄い）。」の形にする\n"
        "- 「面: ...」の語は状態の名詞であって動作ではない。"
        "「面: 塗る。」「面: 埋める。」のように動詞では書かない\n",
        1,
    ),
    # 語彙ブロックの 1 行。つらなり (線の在り方) の直後が おもて (面の在り方)。
    (
        "つらなり: 実線(既定)、破線、点線、一点鎖線\n",
        "つらなり: 実線(既定)、破線、点線、一点鎖線\n"
        "おもて: 空(既定)、塗り、薄墨、粒、点、平行線、交差線、にじみ、アクアチント、濃い、薄い\n",
        1,
    ),
)
_REORDERED_EN = (
    ("hair, ", "silverpoint, ", 2),
    ("line-up, fill, scatter, draw, tile", "line-up, draw, scatter, fill, tile", 1),
    ("burin, or drypoint.", "burin, drypoint, or computer.", 1),
    ("burin, drypoint\n", "burin, drypoint, computer\n", 1),
    # --- 2026-07-27: 内部矛盾の解消 ---
    (
        "Forbidden: move, spread, flow, extend, rise, fall, scatter (as motion), sink, paint\n",
        "Forbidden: move, spread, flow, extend, rise (as motion), fall (as motion), "
        "scatter (as motion), sink, paint\n",
        1,
    ),
    (
        "Allowed action verbs: place, line up, draw, scatter (as arrangement), fill\n",
        "Allowed action verbs: place, line up, draw, scatter (as arrangement), fill, tile\n"
        '   - "rising" / "falling" as angle words (rising to the right / falling to the right) '
        "are Saijiki vocabulary, not motion\n",
        1,
    ),
    (
        "5. Use only Saijiki vocabulary\n",
        "5. Use only Saijiki vocabulary and the fixed phrases this document defines: "
        '"Surface: ..." / "Ground: ..." texture phrases, printmaking phrases, '
        "previous-object relation phrases, and the colorful color list\n",
        1,
    ),
    (
        "context. Do not default everything to pen.",
        "context. Pen is the fallback default, not the recommended choice; "
        "do not default everything to pen.",
        1,
    ),
    (
        'or "draw radial lines".\n',
        'or "draw radial lines".\n'
        "The only exception is a minimal sentence that states nothing but a relation phrase, "
        "a proportion (semicircle, waxing, waning, crescent), or an angle.\n",
        1,
    ),
    ("square, line, arc, or polygon.", "square, line, or arc.", 1),
    # --- 2026-07-28: engine 16 段 3 = 太さの軸 ---
    (
        "# Quantity\n",
        "# Thinness — written separately from the touch\n"
        "\n"
        "Line thinness is written separately from the touch. "
        "Write it only when the line is thinner than the tool's default; "
        "there is no thicker side.\n"
        "\n"
        "- thin, fine line, threadlike, hairlike \u2192 write \"thin\"\n"
        "- extra fine, extremely thin, scratchlike \u2192 write \"extra fine\"\n"
        "\n"
        "Write the thinness explicitly in normalized DDL: "
        '"extra fine black line", "thin pen horizontal line".\n'
        "Never change the touch because of thinness. "
        "Choose the touch from texture even when a thinness word is present.\n"
        "\n"
        "# Quantity\n",
        1,
    ),
    # --- 2026-08-02: 契約 background-color-openness = 背景を抽象九色へ開放 ---
    (
        "Strong solid backgrounds such as black, red, blue, or green are allowed",
        "Strong solid backgrounds such as black, gray, red, orange, yellow, green, blue, "
        "or purple are allowed",
        1,
    ),
    # --- 2026-08-12: 契約 a-shape-can-say-how-its-surface-is = おもての新設 ---
    (
        '- stippled or dotted fill → "Surface: stippled."\n'
        '- hatch or crosshatch → "Surface: hatched diagonally."\n',
        '- fill, paint, solid fill, filled interior → "Surface: flat."\n'
        '- stippled or dotted fill → "Surface: stipple."\n'
        '- hatch, hatched, hatching → "Surface: hatch."\n',
        1,
    ),
    (
        '- bleeding edge → "Surface: bleeding."\n',
        '- bleeding edge → "Surface: bleeding."\n'
        "- a dense, deep, or heavy interior → \"Surface: dense.\"; "
        'a faint, pale, or thin interior → "Surface: faint." '
        'Combine with another surface word as "Surface: flat (dense)." '
        'or "Surface: pale ink wash (faint)."\n'
        '- The "Surface: ..." words are state nouns, never actions. '
        'Never write "Surface: paint." or "Surface: fill."\n',
        1,
    ),
    (
        "continuity: solid (default), dashed, dotted, dash-dot\n",
        "continuity: solid (default), dashed, dotted, dash-dot\n"
        "surfaces: empty (default), flat, pale ink wash, grain, stipple, hatch, "
        "crosshatch, bleeding, aquatint, dense, faint\n",
        1,
    ),
    (
        '- Do not output "Fill background with gray". Even if the input asks for a gray '
        "background, replace the background with contextual white, black, blue, red, or green\n"
        "- Use gray only as a foreground color for lines, dots, or shapes when needed.",
        '- If the input asks for a gray background, output "Fill background with gray". '
        "Choose the background from the nine abstract colors: "
        "white, black, gray, red, orange, yellow, green, blue, purple\n"
        "- Gray works as a background and as a foreground color for lines, dots, or shapes.",
        1,
    ),
)


def test_saijiki_categories_store_one_bilingual_word_sequence() -> None:
    fields = saijiki.SaijikiCategory.__dataclass_fields__
    assert "words" in fields
    assert "words_ja" not in fields
    assert "words_en" not in fields

    ugoki = next(category for category in saijiki.SAIJIKI if category.key == "ugoki")
    pairs = tuple((word.surface_ja, word.surface_en) for word in ugoki.words)
    assert ("引く", "draw") in pairs
    assert ("描く", None) in pairs


def test_score_values_are_attached_to_bilingual_words() -> None:
    for category_key in ("tezawari", "iro"):
        category = next(category for category in saijiki.SAIJIKI if category.key == category_key)
        assert all(word.score_value is not None for word in category.words)


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
        "銀筆", "鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント", "コンピュータ",
        "白", "黒", "青", "赤", "緑", "灰", "黄", "橙", "紫",
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
        "silverpoint", "pencil", "pen", "rotring", "crayon", "chalk", "fine-brush", "thick-brush", "burin", "drypoint", "computer",
        "white", "black", "blue", "red", "green", "gray", "yellow", "orange", "purple",
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
    # 銀筆 は 2026-07-27 に語彙へ戻したので、材質マーカーの先頭に立つ。
    assert _SAIJIKI_MARKERS["material"]["ja"][0] == "銀筆"
    assert _SAIJIKI_MARKERS["material"]["en"][0] == "silverpoint"


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
        # 「髪」/"hair" はどの表面としても残らない — 改名であって併存ではない。
        categories = saijiki.display_categories(lang)
        words = {word for category in categories for word in category["words"]}
        assert not (pruned & words)
        assert not (hidden & words)
    aida = saijiki.display_categories("ja")[-1]
    assert aida["key"] == "aida"
    assert aida["words"] == ("沿う", "触れない", "切る", "間に", "触れる")
