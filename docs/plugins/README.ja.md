# v2 プラグインの作例

[作成ガイド](../../PLUGIN.ja.md) の `inku.plugin-package.v2` に従う、Server へ追加できる二つの見本です。各 zip は最上位の `package.json` と歳時記の PNG を含みます。見本のファイルは製品には同梱しません。

- [水の五語（zip）](water-nihonga.zip)・[JSON](water-nihonga/package.json)
- [空の四語（zip）](sky-nihonga.zip)・[JSON](sky-nihonga/package.json)

| id | 日本語の主の名 | 英語の主の名 | note（日本語） | note（英語） |
|---|---|---|---|---|
| `Water.Stream` | 水流 | stream | 琳派の流水のように、渦を伴って流れるS字の水流。 | An S-shaped stream with eddies, like Rinpa flowing water. |
| `Water.Ripples` | 波紋 | ripples | 真上から見た波紋。滲む雫と、外ほど途切れる輪。 | A ripple seen from above: a bleeding drop and rings that break toward the outside. |
| `Water.Rings` | 水輪 | rings | 斜めから見た波紋。横長の輪と、水面の映り。 | A ripple seen at a low angle: flattened rings and reflections on the water. |
| `Water.River` | 川 | river | 遠くへ曲がりながら細まる川。 | A river bending as it narrows into the distance. |
| `Water.Sea` | 海 | sea | 水平線まで続く海原と波頭。 | Open sea to the horizon, with crests. |
| `Sky.Clouds` | 雲 | clouds | すやり霞の雲。金の芯を通した横長の帯。 | Suyari-gasumi clouds: long bands with gold cores. |
| `Sky.Heavens` | 大空 | heavens | 一文字ぼかしの空。上端から暈す群青。 | An ichimonji-bokashi sky: ultramarine shaded down from the top. |
| `Sky.Rain` | 雨 | rain | 広重の夕立のような、細い縦の雨脚。 | Thin vertical rain like Hiroshige's sudden shower. |
| `Sky.Snow` | 雪 | snow | 胡粉の牡丹雪。暗い地に向く。 | Gofun peony snow, for a dark ground. |

「空」は基本語と重なるので、`Sky.Heavens` の名を「大空」にしました。DDL は `｛水流｝。`、`｛大空｝。` のように括弧の主の名で書きます。名に名前空間を付ける旧形式は、保存済みの作品のために移行期間だけ読めます。

## DDL の書き出し見本

各 `*.ddl.json` は `inku.ddl-export.v2` です。`plugins` は `{definition,note}` の並びで、v2 の見える名を括弧で呼びます。Web の新しい指示書の「読み込む」か CLI の `paint --input-mode ddl --file` で、一つの新しい作品だけに定義を渡せます。

- 全語：[水・日本語](water.ja.ddl.json)／[英語](water.en.ddl.json)、[空・日本語](sky.ja.ddl.json)／[英語](sky.en.ddl.json)
- 単語：[水流](water-stream.ja.ddl.json)、[波紋](water-ripples.ja.ddl.json)、[水輪](water-rings.ja.ddl.json)（それぞれ `.en.ddl.json` もあります）

<img src="water.svg" width="420" alt="和紙の地に群青と淡墨の水の線、波紋、水輪を描いた見本">

水の線は琳派の流水、たらしこみ、近現代の日本画の間を参照しました。空はすやり霞、一文字ぼかし、雨脚、胡粉の牡丹雪を参照しました。これらは新しい図形や実行コードを足さず、core の `emit`、`repeat`、`vary`、`transform` と意味語で構成しています。preview は zip の PNG です。Web のパッケージ検査は定義だけでなく日英の例文を実際に描いて確かめます。
