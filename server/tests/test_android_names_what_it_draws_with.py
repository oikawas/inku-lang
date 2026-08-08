"""Android の描画材は名前で呼ぶ — 直書きが戻ってこないことを守る (T-4..T-9)。

`ui/theme/` を切り出す前、Android の描画材は**全部 `InkuApp.kt` の中に literal で
座っていた** — 色 89 箇所 (57 値)・`.dp` 429 箇所 (53 値・`0.dp` を除く)・`.sp` 8 箇所
(5 値)。5,773 行のファイルに散った 526 個の数字には、役割の名前が 1 つも無い。
`Color(0xFF34302B)` はカードの罫線として 4 度現れるが、そう名乗る場所がどこにも無かった。

**抽出は 1 度きりだが、直書きは毎周戻ってくる。** 新しい画面を 1 つ足すたび、
その場で `12.dp` と書くほうが `Dimens.spaceXl` を探すより速い。web 側で同じことが起き、
`--btn-sm-*` を作った後も px 直書きが戻り、`#fff` 直書きがダークで白地に白文字を出した。
守るものが無ければ、トークン層は作った日がいちばん揃っている。

**なぜ server の pytest に置くのか。** この repo には server の pytest から Kotlin
ソースを読む構造検査の前例が 4 本ある (`test_background_governor.py`,
`test_thinness_declaration_position.py`, `test_limits_are_settings.py`,
`test_android_reference_fixtures_are_current.py`)。**server の pytest は毎周の
受け入れで必ず走る**が、Android の Gradle は `android/` に差分がある周にしか走らない。
退行を止める確率は、広く走る面に置いたほうが高い。

T-4..T-7 は「直書きが戻ってこないこと」を、T-8..T-9 は「Claude Design へ出す
プレビューが腐らないこと」を見る。**どちらか片方では守れない** — T-8 は焼き直される
記録であって性質の検査ではないので、トークンが正しいかは何も見ていない。逆に
T-4..T-7 は、プレビューが古いまま置き去りにされても緑のままになる。
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

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
THEME_DIR = KOTLIN_SOURCE_ROOT / "app/inku/mobile/ui/theme"

DESIGN_DIR = ANDROID_TREE / "design"
PREVIEW_DIR = DESIGN_DIR / "preview"
GENERATOR = DESIGN_DIR / "gen_design_preview.py"

# The same three patterns the contract counts with. `.dp` and `.sp` need the
# leading digits so that `Dimens.spaceXl` -- which contains no digits -- does not
# match, and so that a token named `...2.dp` could not hide inside an identifier.
COLOR_LITERAL = re.compile(r"Color\(0x[0-9A-Fa-f]+\)")
DP_LITERAL = re.compile(r"(?<![\w.])\d+\.?\d*\.dp\b")
SP_LITERAL = re.compile(r"(?<![\w.])\d+\.?\d*\.sp\b")

# Zero is the one exception. "No padding" is not a measurement, so
# `PaddingValues(0.dp)` stays literal and gets no token.
ZERO_DP = re.compile(r"^0(\.0*)?\.dp$")


def _hits(pattern: re.Pattern[str], text: str) -> list[str]:
    return pattern.findall(text)


def _non_zero_dp(text: str) -> list[str]:
    """Every `.dp` literal except the ones that ask for zero.

    Counting zeros by substring is the trap the contract calls out: a plain
    `grep -c '0\\.dp'` also matches the tail of `10.dp` and `20.dp`, which in this
    file is 68 false hits against 20 real ones. Match the whole literal instead.
    """
    return [hit for hit in _hits(DP_LITERAL, text) if not ZERO_DP.match(hit)]


# --- T-4..T-6: the file the tokens were pulled out of ------------------------


@android_only
def test_t4_inku_app_holds_no_color_literals() -> None:
    """`InkuApp.kt` に `Color(0x…)` の直書きが 1 つも無いこと。

    移行前は 89 箇所・57 値。色は用途で名前を持つべきもので、値の写しではない。
    """
    hits = _hits(COLOR_LITERAL, INKU_APP.read_text(encoding="utf-8"))
    assert hits == [], (
        f"{INKU_APP.name} に色の直書きが {len(hits)} 件戻っている: "
        f"{sorted(set(hits))}。ui/theme/Color.kt に用途の名前で足すこと"
    )


@android_only
def test_t5_inku_app_holds_no_sp_literals() -> None:
    """`InkuApp.kt` に `.sp` の直書きが 1 つも無いこと (移行前は 8 箇所・5 値)。"""
    hits = _hits(SP_LITERAL, INKU_APP.read_text(encoding="utf-8"))
    assert hits == [], (
        f"{INKU_APP.name} に活字寸法の直書きが {len(hits)} 件戻っている: "
        f"{sorted(set(hits))}。ui/theme/Type.kt の TypeScale に足すこと"
    )


@android_only
def test_t6_inku_app_holds_no_dp_literals_except_zero() -> None:
    """`InkuApp.kt` に `.dp` の直書きが `0.dp` を除いて 1 つも無いこと。

    移行前は 429 箇所・54 値。うち `0.dp` が 20 箇所で、これだけが例外である。
    """
    text = INKU_APP.read_text(encoding="utf-8")
    hits = _non_zero_dp(text)
    assert hits == [], (
        f"{INKU_APP.name} に寸法の直書きが {len(hits)} 件戻っている: "
        f"{sorted(set(hits))}。ui/theme/Dimens.kt に足すこと"
    )

    # The exception is an exception, not an open door: zero must still be the
    # only literal that survives. If this ever reads 0 the file stopped using
    # `PaddingValues(0.dp)` and the carve-out can go.
    zeros = [hit for hit in _hits(DP_LITERAL, text) if ZERO_DP.match(hit)]
    assert zeros, (
        "`0.dp` が 1 つも無い。例外を残す理由が消えたので、T-6 の carve-out ごと外せる"
    )


# --- T-7: everything else ----------------------------------------------------


@android_only
def test_t7_no_other_kotlin_source_holds_a_literal() -> None:
    """`theme/` を除く全 Kotlin で 3 種の直書きが 0 件であること。

    発行日 (`1b734abc`) の実測で、`InkuApp.kt` 以外の 68 ファイルは 3 種とも 0 件だった。
    **その 0 を凍らせる。** T-4..T-6 が `InkuApp.kt` だけを見ていると、新しい画面を
    別ファイルで作った周に直書きが素通りする — 守っているのは 1 ファイルであって
    規律ではない、という形の穴になる。
    """
    offenders: dict[str, list[str]] = {}
    for path in sorted(KOTLIN_SOURCE_ROOT.rglob("*.kt")):
        if THEME_DIR in path.parents:
            continue  # the token layer is where the literals are supposed to live
        text = path.read_text(encoding="utf-8")
        hits = _hits(COLOR_LITERAL, text) + _non_zero_dp(text) + _hits(SP_LITERAL, text)
        if hits:
            offenders[str(path.relative_to(ANDROID_TREE))] = sorted(set(hits))
    assert offenders == {}, (
        f"theme/ の外に直書きが戻っている: {offenders}。"
        "ui/theme/ の Color.kt / Dimens.kt / Type.kt に用途の名前で足すこと"
    )


# --- T-8..T-9: what goes to Claude Design ------------------------------------


@android_only
def test_t8_design_preview_is_what_the_generator_bakes() -> None:
    """生成器を回した出力が repo の HTML とバイト一致すること。

    **これは焼き直される記録であって、性質の検査ではない。** トークンが正しいかは
    何も見ていない — 見ているのは「Claude Design へ渡す形が現物と同期しているか」だけ。
    だから T-4..T-7 と対で置いている。
    """
    assert GENERATOR.is_file(), f"{GENERATOR} が無い"
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "preview"
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--out", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"生成器が落ちた:\n{result.stdout}\n{result.stderr}"

        baked = {p.name: p.read_bytes() for p in sorted(out.glob("*.html"))}
        stored = {p.name: p.read_bytes() for p in sorted(PREVIEW_DIR.glob("*.html"))}

        assert baked, "生成器が 1 枚も書き出していない"
        assert set(baked) == set(stored), (
            f"プレビューの顔ぶれがずれている: 生成器のみ={sorted(set(baked) - set(stored))} / "
            f"repo のみ={sorted(set(stored) - set(baked))}。"
            f"`python {GENERATOR.relative_to(ROOT)}` を回して commit すること"
        )
        stale = sorted(name for name, body in baked.items() if stored[name] != body)
        assert stale == [], (
            f"プレビューが古い: {stale}。"
            f"`python {GENERATOR.relative_to(ROOT)}` を回して commit すること"
        )


@android_only
def test_t9_every_preview_declares_a_design_system_card() -> None:
    """全プレビューの 1 行目に `@dsCard` マーカーが在ること。

    Claude Design の Design System ペインはこのマーカーからカード索引を組む。
    無いファイルは push しても索引に出ないので、**壊れるのではなく黙って消える**。
    """
    pages = sorted(PREVIEW_DIR.glob("*.html"))
    assert pages, f"{PREVIEW_DIR} に HTML が 1 枚も無い"

    marker = re.compile(r'^<!--\s*@dsCard\s+group="[^"]+"\s*-->\s*$')
    missing = [
        p.name
        for p in pages
        if not marker.match(p.read_text(encoding="utf-8").splitlines()[0])
    ]
    assert missing == [], (
        f'1 行目の `<!-- @dsCard group="…" -->` が欠けている: {missing}'
    )
