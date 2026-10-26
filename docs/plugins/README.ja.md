<p align="center">
  <strong>日本語</strong> ｜ <a href="README.md">English</a>
</p>

# プラグインの作例

[PLUGIN.ja.md](../../PLUGIN.ja.md)の仕様で書いた語彙プラグインを、DDLの書き出しファイル（`inku.ddl-export.v1`）の形で置く。
どれも製品には同梱しない。読み込むと、その新しい作品だけで使える（[PLUGIN §5.1](../../PLUGIN.ja.md#51-ddlの書き出しファイル作者がすぐ使える)）。

| ファイル | 語 |
|---|---|
| [water-ripples.ja.ddl.json](water-ripples.ja.ddl.json) / [water-ripples.en.ddl.json](water-ripples.en.ddl.json) | `Water.Ripples`（別名`Water.波紋`） |

## `Water.Ripples`（別名 `Water.波紋`）

水面に波紋を一つ広げる語である。一点を中心に、灰色の細筆で輪郭だけの円を内から外へ同心に重ねる。

<img src="water-ripples.svg" width="360" alt="青い地の左下寄りに、灰色の細い同心円が五重に広がる。外の輪ほど線が細く、いちばん外の輪は破線">

日本語版の書き出しファイルの`ddl`をそのまま描いたもの（[water-ripples.svg](water-ripples.svg)）。

- 輪の数を受ける（`5個のWater.波紋。`、`5 Water.Ripples.`）。範囲は1〜6個で、書かなければ3〜4個。範囲の外の個数はその語だけが外れる。
- 中心は、画面の中央からやや下の五つの位置から、作品の構図の種で一つを選ぶ。全ての輪が同じ中心を持つ。

  | 候補 | x | y |
  |---|---|---|
  | 1 | 0.500 | 0.560 |
  | 2 | 0.380 | 0.620 |
  | 3 | 0.620 | 0.580 |
  | 4 | 0.440 | 0.680 |
  | 5 | 0.580 | 0.460 |

- 輪の半径は内から0.035・0.070・0.110・0.155・0.205・0.260（短い辺に対する割合）で、外ほど間が広がる。
- 線は内の三つが`fine`、外の三つが`extra_fine`。五つ目は破線、六つ目は点線で、外へほどける。
- 輪の線は細かく波打つ（`narrowly`・`undulating`）。
- 色は灰に決めてある。宣言した引数は全て必須になるので（PLUGIN §3.4）、色を引数にすると名前だけの呼出しが描けなくなるためである。

書き出しファイルの`ddl`は、日本語版が`背景を青で埋める。`と`5個のWater.波紋。`、英語版が同じ内容の英語である。

### 読み込み方

- Web: 記述タブの下の「指示書を新規作成」を開き、「読み込む」でファイルを選ぶ。
- CLI: `uv run inku-cli paint --input-mode ddl --file docs/plugins/water-ripples.ja.ddl.json`
- Serverの全ての新しい作品で使うには、`definition`を`pipeline.definitions`へ、`summary`を同じ順で`pipeline.macro_summaries`へ入れる（PLUGIN §5.2）。

### 確かめたこと（2026-10-26）

定義は`compile-score`（PLUGIN §7.1）の検査を通り、`Water.Ripples 1.0.0`、digest
`sha256:c33709784dddedb8ed7a8342794cab9c78315fe1a74a75007981d53dfa2e1b6c`になった。そのlockで個数を書かずに呼ぶと、種により3つか4つの輪になった。

二つの書き出しファイルの`plugins`をServerの`/api/compose`の`imported_plugins`へ渡し、共有coreで描いた結果:
`5個のWater.波紋。`と`5 Water.Ripples.`は5つ、`Water.波紋。`と`Water.Ripples.`は書かない個数の候補から3つ、
`6個のWater.波紋。`と`6 Water.Ripples.`は6つの同心円を診断なしで描き、6つのときは五つ目が破線、六つ目が点線になった。
作品ごとに中心が候補の間で変わった。`背景を黒で埋める。`・`3個のWater.波紋。`・`中心に白い小さな円を置く。`の並びも診断なしで描いた。
`7個のWater.波紋。`は範囲の外なので、その語が外れ、ほかに描くものが無いので作品は作られなかった（`score_not_ready`）。
