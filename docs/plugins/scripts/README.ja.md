<p align="center">
  <strong>日本語</strong> ｜ <a href="README.md">English</a>
</p>

# 作例の語を作るスクリプト

[水と空の作例](../README.ja.md)の九つの語の定義（`inku.macro-definition.v2`）を作るPythonのスクリプトである。
定義には算術が無いので、位置・寸法・角度の表は、このスクリプトが計算して書き出す。Python 3.10以降の標準ライブラリだけで動く。

| ファイル | 中身 |
|---|---|
| [helpers.py](helpers.py) | 式（`semantic_ref`・`exact_decimal`・`cycle`など）を作る小さな関数と、傾けた弧の円を求める計算 |
| [water_stream_ripples_rings.py](water_stream_ripples_rings.py) | `｛水流｝`（Stream 1.0.0）・`｛波紋｝`（Ripples 3.0.0）・`｛水輪｝`（Rings 2.0.0） |
| [river_sea_sky.py](river_sea_sky.py) | `｛川｝`（River）・`｛海｝`（Sea）・`｛雲｝`（Clouds）・`｛大空｝`（Heavens）・`｛雨｝`（Rain 2.0.0）・`｛雪｝`（Snow） |
| [build_v2.py](build_v2.py) | 二つのスクリプトの語をv2の定義（`id`・`names`・`kind: scene`）にし、作例のファイルと照らす、または書き込む |

## 使い方

このフォルダで実行する。

```sh
python3 build_v2.py            # 作例のファイルの定義と照らす。全て同じなら "all definitions match"
python3 build_v2.py --write    # 定義を作例のファイルへ書き込む
python3 build_v2.py --dump out.json
```

`--write`が書き換えるのは、`../water-nihonga/package.json`・`../sky-nihonga/package.json`と、その語を運ぶ`../*.ddl.json`の、各語の`definition`だけである。
note・例文・絵・欄の順は変えない。2026-10-30に、九つの語がリポジトリのファイルと全て一致することを確かめた。

## 語を直す手順

1. 語のスクリプトの表や値を直し、定義の`version`を上げる（`definition(..., version="2.1.0")`など）。
2. `python3 build_v2.py --write`で書き込み、`package.json`の`version`も上げる。noteや例文を変えるときは`package.json`を直接直す。
3. zipを作り直す（[作例のREADME](../README.ja.md)と同じ手順）。

   ```sh
   cd ../sky-nihonga   # 水は ../water-nihonga
   TZ=UTC touch -t 202610260000 package.json previews previews/*.png
   rm -f ../sky-nihonga.zip && zip -X -r ../sky-nihonga.zip package.json previews
   ```

4. Webの設定「プラグイン」の「プラグインを追加」で検査する（「キャンセル」で追加せずに終われる）。
   定義だけなら、リポジトリの最上位で`scripts/rust-toolchain.sh run -q -p inku-ddl --example compile-score --locked --offline`に定義を渡して検査できる（[PLUGIN §7](../../../PLUGIN.ja.md)）。

歳時記の絵（`previews/*.png`）は、このスクリプトでは作らない。各語の例文をServerで描き、枠（216×92の2倍）に切り出して置いた。

## 作るときの決まり

- **はみ出さない。** `transform`の後に図形が画面から出ると、そのまとまり全てが描かれない（`numeric_transform_group_position_conflict`）。
  長い弧は、まず画面の中心に作ってから`transform`で回して動かす。そのまま置くと、回す前に画面から出て外れる（`geometry_extent_out_of_bounds`）。
- **丸めに気をつける。** 半円の矢高は弦の半分で、丸めて半分を超えると描けない（`geometry_dimension_mismatch`）。寸法は千分の二の倍数にするなど、割り切れる値にする。
- **条件で分けない。** `repeat`の回数は0にできず、文を条件で選べない。輪や線ごとの違いは`cycle`の表で書く。
- **位置は`cycle`で。** xとyを別の`vary`で選ぶと表が混ざる。位置の候補は整数を`vary`で選び、その数でxとyの`cycle`の表を引く。
- **`散らす`は一つの指示。** `movement: scatter`と`count`で、一つの指示が多くの印を散らす（雨・雪）。`transform`で傾けられる。
