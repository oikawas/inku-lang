from __future__ import annotations

from inku_server.ddl_expander import expand_intermediate_ddl


def test_expand_intermediate_ddl_adds_mathematical_layers():
    ddl = "背景を灰で塗りつぶす。赤い小さな円をランダムに十二個散らす。青い小さな円をランダムに八個散らす。白い細筆の細い線を水平に三本引く。"

    expanded = expand_intermediate_ddl(ddl)

    assert "ランダム" not in expanded
    assert "画面全体に点々と十二個" in expanded
    assert "正五角形の頂点に五個" in expanded
    assert "放射状に十三個" in expanded
    assert "波打つ軌跡に沿って二十一個" in expanded
    assert "右上の黄金比の位置" in expanded
    assert "左上の三分割の交点" in expanded
    assert "左下の白銀比の位置" in expanded
    assert "対位法の反行" in expanded
    assert "倍音列" in expanded
    assert "輪唱のずれ" in expanded


def test_expand_intermediate_ddl_is_idempotent_after_expansion():
    ddl = "赤い小さな円を中央付近に五つ散らす。灰色の小さな円を右上の黄金比の位置に一点置く。半径は0.025。"

    assert expand_intermediate_ddl(ddl) == ddl


def test_expand_intermediate_ddl_en_adds_mathematical_layers():
    ddl = "Scatter five small red circles randomly. Draw three thin white horizontal lines."

    expanded = expand_intermediate_ddl(ddl, lang="en")

    assert "random" not in expanded.lower()
    assert "dotted across the whole canvas" in expanded
    assert "regular pentagon vertices" in expanded
    assert "thirteen small red circles radially" in expanded
    assert "upper-right golden-ratio position" in expanded
    assert "upper-left rule-of-thirds point" in expanded
    assert "lower-left silver-ratio position" in expanded
    assert "contrapuntal contrary motion" in expanded
    assert "harmonic overtone series" in expanded
    assert "canon offset" in expanded
