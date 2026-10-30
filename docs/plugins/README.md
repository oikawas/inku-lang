# V2 plugin examples

These two installable examples follow the [authoring guide](../../PLUGIN.md) for `inku.plugin-package.v2`. Each zip holds `package.json` at its root and Saijiki PNGs. The examples are not bundled with the product.

- [Five water words (zip)](water-nihonga.zip) and [JSON](water-nihonga/package.json)
- [Four sky words (zip)](sky-nihonga.zip) and [JSON](sky-nihonga/package.json)
- [Scripts that make the word definitions](scripts/README.md) (Python; they build the nine words' v2 definitions and check them against the files above)

| id | Primary Japanese name | Primary English name | Japanese note | English note |
|---|---|---|---|---|
| `Water.Stream` | 水流 | stream | 琳派の流水のように、渦を伴って流れるS字の水流。 | An S-shaped stream with eddies, like Rinpa flowing water. |
| `Water.Ripples` | 波紋 | ripples | 真上から見た波紋。滲む雫と、外ほど途切れる輪。 | A ripple seen from above: a bleeding drop and rings that break toward the outside. |
| `Water.Rings` | 水輪 | rings | 斜めから見た波紋。横長の輪と、水面の映り。 | A ripple seen at a low angle: flattened rings and reflections on the water. |
| `Water.River` | 川 | river | 遠くへ曲がりながら細まる川。 | A river bending as it narrows into the distance. |
| `Water.Sea` | 海 | sea | 水平線まで続く海原と波頭。 | Open sea to the horizon, with crests. |
| `Sky.Clouds` | 雲 | clouds | すやり霞の雲。金の芯を通した横長の帯。 | Suyari-gasumi clouds: long bands with gold cores. |
| `Sky.Heavens` | 大空 | heavens | 一文字ぼかしの空。上端から暈す群青。 | An ichimonji-bokashi sky: ultramarine shaded down from the top. |
| `Sky.Rain` | 雨 | rain | 風に斜めに降る夕立。三層の雨脚に雨雲と雨霞を添える。 | A sudden shower slanting on the wind: three layers of rain with a rain cloud and mist. |
| `Sky.Snow` | 雪 | snow | 胡粉の牡丹雪。暗い地に向く。 | Gofun peony snow, for a dark ground. |

The name `空` conflicts with a core word, so `Sky.Heavens` now uses `大空`. DDL calls the braced primary name, such as `{stream}.` or `{heavens}.` The old qualified spelling remains readable during the saved-work migration period.

## DDL export examples

Every `*.ddl.json` is `inku.ddl-export.v2`. Its `plugins` carry `{definition,note}` and its DDL calls visible names in braces. Import through Web's new DDL dialog or CLI `paint --input-mode ddl --file`; definitions apply to that one new work without installation.

- All words: [water in Japanese](water.ja.ddl.json) / [English](water.en.ddl.json), [sky in Japanese](sky.ja.ddl.json) / [English](sky.en.ddl.json)
- Single words: [stream](water-stream.en.ddl.json), [ripples](water-ripples.en.ddl.json), [rings](water-rings.en.ddl.json) (Japanese counterparts are also present)

<img src="water.svg" width="420" alt="Ultramarine and pale-ink water lines, ripples, and rings on washi ground">

The water words refer to Rinpa flowing water, bleeding ink, and the gaps in modern Japanese painting. The sky words refer to suyari-gasumi bands, ichimonji bokashi, rain strokes, and gofun snow. They use the core's `emit`, `repeat`, `vary`, `transform`, and meaning words rather than new primitives or executable code. The zip supplies each preview PNG. The Web package check draws both Japanese and English examples as well as validating definitions.
