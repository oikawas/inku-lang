"""Independent versions for deterministic DDL layers and the DDL language."""

# 3 (2026-07-29): `Instruction.thinness` の宣言を末尾へ移した。Stage 2 の tool schema は
# 並び順ごと LLM へ渡るので、振る舞いを 1 行も変えなくても Score の分布が変わる。
# 宣言順を変えたときに上げるのは、この層だけが持つ条件である (I-036 / I-038)。
DDL_ENGINE_VERSION = "3"
# 2 (2026-07-29): 太さが道具名から独立した語になり、「極細の黒い線」と書けるように
# なった。語彙が増えたら版を上げるという規約に従う。保存済みの作品は "1" のまま残る。
DDL_VERSION = "2"
