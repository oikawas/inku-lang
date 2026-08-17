# 予測の凍結: 公開文書が木に追いつく

- **エージェント**: `claude-fable-5`（実装セッション）
- **契約**: `no-git-sync/fable5/claude_code/tasks/stock/the-published-documents-catch-up-with-the-tree.md`
- **枝**: `feat/the-published-documents-catch-up-with-the-tree` ／ 起点 `a69730d7`（clean を実測）
- **日付**: 2026-08-17。**この commit の時点で、文書もゲートも 1 行も書き換えていない。**

## 段 0 の実測（着手前）

1. **満点**: `testbox.sh --sync --server` → **3454 passed / 31 skipped**（コンテナ、84.01s）。契約の数字と一致。
2. **`check_docs.py`**: 起点で**緑**（既存 4 検査、内部参照 55・語彙検査 28 文書）。
3. **1-1 の表の測り直し**: 21 対 ／ **ja のみ 27 ／ en のみ 1**。契約と一致。
   SPEC の 18 件の内訳も契約と一字一句一致。
   - **測り直しで 2 度誤測した**: 正規表現に `\b` を付けると「Build 557では」（後端）も
     「をBuild 518」（前端）も不一致になる（かな・漢字は word 文字なので境界が立たない）。
     `\b` を両側とも外して契約の数字に到達した。**この罠は段 4 のゲート実装と受入テストに焼き込む。**
4. **契約の範囲外で見つけた非対称**（参考。触らない・ゲートから名指しで除外する）:
   `CHANGELOG.{ja,}.md` に ja のみ 6 件（`Build 0`・`Build 148084`・`Build 733`・`Build 756`・
   `Build 777`・`Build 793`）。台帳 inbox へ起票する。
   SETUP・ANDROID_SPEC・manual 7 対は**対称**（2026-08-17 実測）。

## 設計の要点（予測の前提）

- 段 4 の検査 `check_version_marks` は **PAIRS 全 31 対から `CHANGELOG.{ja,}.md` だけを
  名指しで除外した 30 対**を比べる（契約の 21 対はその部分集合。既存の
  `TERMINOLOGY_EXEMPT` と同じ「見ないと決めた」方式で、除外はテストが 1 件ずつ主張する）。
- 受入テストは新規 1 ファイル `server/tests/test_docs_version_marks_gate.py`。
  T-301（実木で非対称 0）・T-302（合成の非対称を検出＝判別力）・結線（AST）・
  かな隣接の回帰・除外の統制・T-304（README の Android 行の render engine ==
  `CompatibilityConstants.kt` の `renderEngineVersion`、日英で 2 本）・
  T-305（段 2 で直した記述を現物と突き合わせる。**本数は段 2 の読み込みで決まる。見積り 3 本**）・
  T-306（21 対の骨格一致、parametrize 21 本）。

## 摂動の予測（どのテストが何本赤くなるか）

| 摂動 | 赤くなると予測するもの | 本数 |
|---|---|---|
| **P-1** `SPEC.md` に `Build 999` | T-301 のテスト。**加えて `check_docs.py` の exit が 1 になる**（新検査の節が赤。既存 4 節の印字は緑のまま＝T-300 の主張自体は保たれる。契約は言及していないが、検査を main へ結線する以上必ず起きる） | **pytest 1 本** |
| **P-2** 比較を常に一致へ | T-302 のテスト。T-301 は緑のまま（契約の期待どおり）。かな隣接の回帰テストは抽出器だけを通す設計にするので緑のまま | **pytest 1 本** |
| **P-3** `docs/architecture/README.md` の見出しを 1 つ消す | T-306 の該当 parametrize 1 本。**加えて `check_docs.py` の第 1 検査（骨格）が赤 = T-300 が赤**（契約の期待どおり） | **pytest 1 本 + スクリプト赤** |
| **P-4** `README.md` の render engine の番号をずらす | T-304 の en 側 1 本（当て先は Android 行。見本画像の「Build 667・render engine 10」の行は凍結された記録でありゲートの外 — 当てても赤くならない。この非対称は報告に明記する）。T-301 は緑のまま（engine の番号は集合に入れない） | **pytest 1 本** |
| **P-5** `implementation-status.md` の直した記述を 1 つ戻す | T-305 の該当 1 本。**戻した記述が `vX.Y.Z` / `Build N` の印を含む場合だけ T-301 も赤くなる（+1）**。当てるときは印を含まない記述を選び、1 本に留める | **pytest 1 本** |

## 満点の予測（改修後）

- 新規テストは **28 + T-305 の本数（見積り 3）≒ 31 本**。
- 枝の先端の全走（コンテナ）は **3454 + 新規本数 passed / 31 skipped** を予測する。
  skip の増減は無し（新規テストのうち android/ を読む T-304 は skipif 付きだが、
  コンテナの走行木は全木なので skip しない）。
