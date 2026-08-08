"""Android は作品を主に置く — 段 B が動かした配置と体系が戻らないことを守る (T-1..T-10)。

段 B の前、記述画面はこうなっていた: **キャンバスは 4 段目**で、その上には
**実行と関係なく回り続けるマスコット**が居た。キャンバスのすぐ上の 1 行には
☆ と hash（描き終わった作品の属性）と倍率（表示の属性）とキャンバス比
（これから描く絵の設定）が並び、**3 つの家族と 2 つの時制が同じ行に**あった。
**モデル選択の入口は 3 つ**あり、**書き出しは 2 つのドロップダウンと設定の 1 ペイン**に
割れていた。**全画面ではピンチが結線されず倍率は `1f` に固定**され、**同じ左右スワイプが
全画面と通常で逆の作品へ動いた**。

**この形は「直せば終わり」ではなく、画面を 1 つ足すたびに戻ってくる。** 新しい設定を
足すとき、いちばん近い行へ置くほうが「どの家族か」を考えるより速い。web 側で同じことが
起き、`RunStatus` から取り出されたマスコットが Android では状態と切り離されて置かれた。

**なぜ server の pytest に置くのか。** 段 A の受入 (`test_android_names_what_it_draws_with.py`)
と同じ理由である — **server の pytest は毎周の受け入れで必ず走る**が、Android の Gradle は
`android/` に差分がある周にしか走らない。退行を止める確率は、広く走る面に置いたほうが高い。

T-1..T-4 と T-9..T-10 は**配置と導線**（段 B-1）を、T-5..T-8 は**寸法と字の体系**（段 B-2）を見る。
**T-11 は実機の計装にある** — IME が出ている間に主操作が画面内にあることは、
ソースを読んでも分からない（`imePadding()` は下端を持ち上げるだけで、ボタンを連れてこない）。
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the whole tree is absent. Key the skip to
# the DIRECTORY, not to the files below: wherever `android/` exists -- every
# checkout, every developer machine, CI -- these assertions still run, and a file
# that was moved or renamed is a failure rather than a silent skip.
ANDROID_TREE = ROOT / "android"
android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(),
    reason="android/ is never synced to the server; the port is checked where the tree exists",
)

KOTLIN_SOURCE_ROOT = ANDROID_TREE / "app/src/main/java"
INKU_APP = KOTLIN_SOURCE_ROOT / "app/inku/mobile/ui/InkuApp.kt"
INKU_VIEW_MODEL = KOTLIN_SOURCE_ROOT / "app/inku/mobile/ui/InkuViewModel.kt"
DIMENS = KOTLIN_SOURCE_ROOT / "app/inku/mobile/ui/theme/Dimens.kt"
TYPE = KOTLIN_SOURCE_ROOT / "app/inku/mobile/ui/theme/Type.kt"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(text: str, signature: str) -> str:
    """`signature` で始まる関数の本文を、波括弧を数えて切り出す。

    **領域を切るなら、切った先に対象が居ることを先に数えること** — 段 B の契約が
    名指しした落とし穴である。発行側の試作では `ComposeScreen` の本文だけを切り出して
    モデル選択を数え、3 つの入口はどれも別の composable に居たので 0 件が出て、
    検査が恒真になった。ここで領域を切っているのは T-10 だけで、そこには
    「切る前は 3 件在った」という数が添えてある。
    """
    start = text.index(signature)
    open_brace = text.index("{", start)
    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace : index + 1]
    raise AssertionError(f"{signature} の波括弧が閉じていない")


# --- T-1..T-4, T-9..T-10: 配置と導線 (段 B-1) ---------------------------------


@android_only
def test_t1_the_model_has_one_entry() -> None:
    """モデル選択を開く呼び出しが `InkuApp.kt` に 1 件だけであること (段 B の前は 3 件)。

    **⚠ 領域を切らずにファイル全体で数える。** 3 つの入口は `ConditionChips` /
    `DrawPanel` / `InputSectionHeader` という**別々の composable に居た**ので、
    記述画面の本文だけを切り出すと 1 つも入らない。
    """
    hits = re.findall(r"viewModel(?:::|\.)openModelSelection\b", _read(INKU_APP))
    assert len(hits) == 1, (
        f"モデル選択の入口が {len(hits)} 件ある。1 つに畳むこと — "
        "同じ選択に行く入口が増えるほど、どれが「いま効いている設定」か読めなくなる"
    )


@android_only
def test_t2_the_mascot_is_drawn_only_while_something_runs() -> None:
    """`MascotWidget(` の呼び出しが 1 件で、囲みが実行状態の部品であること。

    **契約が要求するのは名前ではなく「囲みが実行状態の部品であること」。** web は
    `RunStatus.svelte` の中にマスコットを置き、走っているすべての操作がその部品を描く。
    Android は状態表示からマスコットだけを取り出して無条件に置いていたので、
    **回っている理由が画面のどこにも書いていなかった。**
    """
    text = _read(INKU_APP)
    calls = [
        match for match in re.finditer(r"\bMascotWidget\(", text)
        if not re.search(r"fun\s+MascotWidget\($", text[: match.end()])
    ]
    assert len(calls) == 1, (
        f"`MascotWidget(` の呼び出しが {len(calls)} 件ある (定義を除く)。"
        "実行状態の行 1 箇所からだけ描くこと"
    )

    # Which composable holds it: the last `fun name(` before the call.
    enclosing = None
    for match in re.finditer(r"fun\s+(\w+)\s*\(", text[: calls[0].start()]):
        enclosing = match.group(1)
    assert enclosing is not None, "`MascotWidget(` を囲む関数が読めない"
    body = _function_body(text, f"fun {enclosing}(")
    assert "isRunning" in body, (
        f"`MascotWidget(` を囲む `{enclosing}` が実行状態 (`isRunning`) を読んでいない。"
        "マスコットは状態表示の一部であって、置き物ではない"
    )


@android_only
def test_t3_the_swipe_means_one_thing_in_both_canvases() -> None:
    """`onSwipeRight` / `onSwipeLeft` に結ばれた関数がそれぞれ 1 種類であること。

    **⚠ 逆向きと対で据える。** 右だけを見ると、両方を同じ関数に結んだ実装
    （右も左も「次へ」）が通ってしまう。段 B の前は右が 2 種類あり、
    **同じ指の動きが全画面と通常で反対を意味していた。**
    """
    text = _read(INKU_APP)
    right = set(re.findall(r"onSwipeRight\s*=\s*viewModel::(\w+)", text))
    left = set(re.findall(r"onSwipeLeft\s*=\s*viewModel::(\w+)", text))
    assert len(right) == 1, f"`onSwipeRight` に {len(right)} 種類が結ばれている: {sorted(right)}"
    assert len(left) == 1, f"`onSwipeLeft` に {len(left)} 種類が結ばれている: {sorted(left)}"
    assert right != left, (
        f"左右が同じ関数 {sorted(right)} に結ばれている。1 種類ずつでも、"
        "同じ向きへ動くなら作品を移動できない"
    )


@android_only
def test_t4_magnification_reaches_the_drawing_in_the_full_screen() -> None:
    """全画面で倍率が描画へ届くこと。

    **⚠ 結線の有無ではなく、倍率が定数でないことを見る**（消費されない値は測れない）。
    段 B の前は `detectTransformGestures` が `!presentation` のときだけ付き、
    `graphicsLayer` は `scaleX = if (presentation) 1f else state.canvasZoom` だった —
    **拡大して見たいのは全画面のほうなのに、ズームが効くのは小さい通常表示のほうだった。**
    """
    text = _read(INKU_APP)
    assert "if (presentation) 1f else state.canvasZoom" not in text, (
        "全画面の倍率が `1f` に固定されている。定数は倍率ではない"
    )

    # The call, not the import: `detectTransformGestures` first appears at the
    # top of the file as an import line, and nothing at all precedes that.
    gesture = text.index("detectTransformGestures {")
    if_presentation = text.rfind("if (presentation)", 0, gesture)
    if_not_presentation = text.rfind("if (!presentation)", 0, gesture)
    assert if_presentation > if_not_presentation, (
        "transform gesture が `!presentation` の側に閉じている。"
        "ピンチは作品が画面いっぱいに出ている側へ結ぶこと"
    )

    assert re.search(r"scaleX\s*=\s*state\.canvasZoom", text), (
        "`graphicsLayer` の倍率が `state.canvasZoom` から来ていない。"
        "ジェスチャが state を動かしても、描画が読まなければ何も起きない"
    )


@android_only
def test_t9_the_bottom_bar_has_four_destinations() -> None:
    """下タブが 4 つで、`Demo` がその中に無いこと (段 B の前は 5 つ)。

    Material 3 の下タブは**常用する行き先**を並べる場所で、デモは常用ではない。
    """
    body = _function_body(_read(INKU_VIEW_MODEL), "enum class AppTab")
    entries = [
        line.strip().rstrip(",")
        for line in body.splitlines()
        if re.fullmatch(r"\s*\w+,?\s*", line) and line.strip() not in {"{", "}"}
    ]
    entries = [entry for entry in entries if entry]
    assert len(entries) == 4, f"下タブが {len(entries)} つある: {entries}"
    assert "Demo" not in entries, "デモが下タブに戻っている。設定の中へ畳むこと"


@android_only
def test_t10_the_export_does_not_hang_off_the_canvas_card() -> None:
    """`CanvasHeroCard` の本文に `SvgExportOption(` が無いこと (段 B の前は 3 件)。

    **⚠ 領域を切っているので、切る前と後の件数を添える** — ファイル全体では
    `SvgExportOption(` は定義 1 + 書き出しシートからの 4 件が在り、
    ここで 0 件になるのは「キャンバスカードから外れた」ことを意味する。
    """
    text = _read(INKU_APP)
    everywhere = len(re.findall(r"\bSvgExportOption\(", text))
    assert everywhere >= 2, (
        f"`SvgExportOption(` がファイル全体で {everywhere} 件しかない。"
        "書き出し自体が消えているなら、この検査は 0 件を恒真に見ているだけになる"
    )
    body = _function_body(text, "private fun CanvasHeroCard(")
    hits = re.findall(r"\bSvgExportOption\(", body)
    assert hits == [], (
        f"`CanvasHeroCard` の本文に書き出しが {len(hits)} 件直結している。"
        "書き出しは入口 1 つ (ボトムシート) に畳むこと"
    )


# --- T-5..T-8: 寸法と字の体系 (段 B-2) ----------------------------------------

DP_DECLARATION = re.compile(r"val\s+(\w+)\s*:\s*Dp\s*=\s*(.+)")
DP_LITERAL_VALUE = re.compile(r"^(\d+(?:\.\d+)?)\.dp$")
SP_DECLARATION = re.compile(r"val\s+(\w+)\s*:\s*TextUnit\s*=\s*(\d+(?:\.\d+)?)\.sp")

# The one distance allowed off the grid: a 1dp border is a line, not a distance.
OFF_GRID_EXEMPT = {"hairline"}
GRID_STEP = 4.0


def _dp_declarations() -> dict[str, str]:
    return {
        match.group(1): match.group(2).strip()
        for match in DP_DECLARATION.finditer(_read(DIMENS))
    }


@android_only
def test_t5_buttons_come_in_three_heights() -> None:
    """`buttonHeightMedium` (54dp) と `controlSizeMedium` (34dp) が消えていること。

    **54dp と 56dp・32dp と 34dp は、区別する理由が説明できなかった。** 主 56 / 副 40 /
    補助 32 の 3 段だけを残す。
    """
    declarations = _dp_declarations()
    for gone in ("buttonHeightMedium", "controlSizeMedium"):
        assert gone not in declarations, (
            f"`{gone}` が Dimens に戻っている。高さは 主56 / 副40 / 補助32 の 3 段"
        )
    for kept in ("buttonHeightLarge", "buttonHeightSmall", "controlSizeSmall"):
        assert kept in declarations, f"`{kept}` が無い。3 段のうち 1 段が欠けている"


@android_only
def test_t6_no_type_size_is_below_twelve_sp() -> None:
    """`Type.kt` の**字の大きさ**が全部 12sp 以上であること (段 B の前の最小は 11sp)。

    **⚠ 行送り (`lineHeight`) は対象外。** 17sp の行送りは 12sp の字と対で使うもので、
    ここに混ぜると「字が小さい」と「行が詰まっている」を 1 つの数字で見ることになる。
    12sp は Material 3 の下限で、11sp は規格外だった。
    """
    sizes = {
        name: float(value)
        for name, value in SP_DECLARATION.findall(_read(TYPE))
        if "LineHeight" not in name
    }
    assert sizes, "`Type.kt` から字の大きさが 1 つも読めない"
    too_small = {name: value for name, value in sizes.items() if value < 12.0}
    assert too_small == {}, (
        f"Material 3 の下限 12sp を割っている字がある: {too_small}"
    )


@android_only
def test_t7_every_dimension_sits_on_the_four_dp_grid() -> None:
    """`Dimens.kt` の `.dp` 直値が全部 4 の倍数であること (`hairline` の 1dp だけ例外)。

    段 A は 53 値のうち 22 値を格子の外に残した。**あれは意図して残した宿題で**、
    格子へ寄せると絵が動くから、画面を作り直す段まで待った。
    """
    off_grid = {}
    for name, expression in _dp_declarations().items():
        literal = DP_LITERAL_VALUE.match(expression)
        if literal is None:
            continue  # not a literal; T-8 is the one that reads those
        value = float(literal.group(1))
        if name not in OFF_GRID_EXEMPT and value % GRID_STEP != 0:
            off_grid[name] = value
    assert off_grid == {}, (
        f"4dp 格子から外れた寸法がある: {off_grid}。"
        f"例外は {sorted(OFF_GRID_EXEMPT)} だけ"
    )


# Which family a token belongs to, by what its name starts with. A token defined
# as another token must stay inside its own family: `radiusCard = spaceXxl` meant
# a corner silently followed a gap whenever the gap was retuned.
TOKEN_FAMILIES = (
    ("radius", ("radius",)),
    ("space", ("space", "hairline")),
)


def _family_of(name: str) -> str | None:
    for family, prefixes in TOKEN_FAMILIES:
        if any(name.startswith(prefix) for prefix in prefixes):
            return family
    return None


@android_only
def test_t8_no_token_borrows_from_another_family() -> None:
    """`radius*` が `space*` で定義されていないこと。

    **名前が別の用途を指すトークンを共有すると、片方を動かしたときにもう片方が黙って動く。**
    段 B の前は `radiusCard = spaceXxl` (14dp) と `radiusPill = space28` (28dp) で、
    余白を 4dp 格子へ寄せる作業が角丸を 2 つ道連れにするところだった。
    """
    borrowed = {}
    for name, expression in _dp_declarations().items():
        if DP_LITERAL_VALUE.match(expression):
            continue  # a literal borrows from nobody
        referenced = expression.strip()
        if not re.fullmatch(r"\w+", referenced):
            continue
        mine, theirs = _family_of(name), _family_of(referenced)
        if mine is not None and theirs is not None and mine != theirs:
            borrowed[name] = referenced
    assert borrowed == {}, (
        f"家族をまたいでトークンを借りている: {borrowed}。自分の値を持たせること"
    )

    # The same rule at the call site. `MiniPill` is the app's densest control and
    # took its width from a token named for the presentation caption's inset.
    # ⚠ 発行日 (`9a85d783`) には `heroCaptionMaxWidth` を使っており、段 B-1 が
    # その呼び出しごと消したので、ここは B-1 の完了時点で既に満たされていた。
    app = _read(INKU_APP)
    mini_pill = _function_body(app, "private fun MiniPill(")
    stolen = re.findall(r"Dimens\.((?:presentationCaption|hero)\w*)", mini_pill)
    assert stolen == [], (
        f"`MiniPill` が別用途のトークンを寸法に使っている: {sorted(set(stolen))}"
    )

    # **宣言だけを見ると素通りする。** トークンから `radiusXs` (3dp) を消しても、
    # 呼び出し側が `RoundedCornerShape(Dimens.spaceXs)` と書けば角丸は 4 種類に戻る。
    # 完了時の実測でこの形が 34 件残っていて、宣言側の T-8 は 1 件も見ていなかった。
    corners = re.findall(r"RoundedCornerShape\(\s*Dimens\.(space\w*)", app)
    assert corners == [], (
        f"角丸に余白のトークンを渡している: {sorted(set(corners))} ({len(corners)} 件)。"
        "角丸は radiusCard と pill の 2 種類"
    )
