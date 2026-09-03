# inku 語彙プラグイン作成ガイド

inkuにおけるプラグインは、データだけで記述する語彙マクロである。`Nature.雨`のような
目に見える修飾名は、版を持つ1つの`inku.macro-definition.v1`定義を呼び出し、
通常の型付きコア意味へ展開される。プラグインは実行可能コードでも、parserの拡張でも、
Rendererのhookでもない。

Canvasの選択は`inku.canvas-format-registry.v1`が所有するhost optionであり、
プラグインではない。Render Engine Packは描画coreを置き換える別の仕組みである。
プラグイン境界の規範は[SPEC §4](SPEC.ja.md#4-プラグイン設計原則)にある。

## 定義形式

定義は、次のtop-level fieldだけを正確に持つ。

- `schema`: 正確に`inku.macro-definition.v1`
- `namespace`と`heading`: 合わせて目に見える`Namespace.Heading`名を作る
- `version`: canonical digestとともにlockされる定義version
- `parameters`: 型付きinput schemaの閉じたmap
- `components`: 定義内だけで再利用するcomponent
- `body`: 上限を持つdata-onlyのstatement list

Parameter schemaは`number`、`integer`、`boolean`、固定長`list`、`semantic_ref`に
閉じている。式は型付きのnumber、integer、boolean、list、parameter、local、
semantic-reference形式に閉じている。未知のfield、type、expression、operator、
semantic referenceは拒否される。

Bodyでは`emit`、`use`、`group`、`anchor`、`relation`、上限付き`repeat`、
型付き`transform`、決定的で上限付きの`vary`を使える。`components`は同じ定義内だけに
属する。定義には、任意code、I/O、filesystem、network、clock、environmentへのaccess、
再帰またはcomponent cycle、外部macro dependency、raw SVGまたはScore data、Renderer命令、
plugin固有のparser、grammar、rendererを含められない。

受け入れられる最小の定義は次である。

```json
{
  "schema": "inku.macro-definition.v1",
  "namespace": "Example",
  "heading": "QuietMark",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": []
}
```

## 解決・展開・LLM境界

Compilerは、明示された修飾付き呼出しをsidecar lockに照らして解決する。Lockは、
定義名、version、canonical digest、documentとcompilerのidentity、および展開を再現するために
必要なsourceとgenerated provenanceを証明する。展開は型付きparameterをbindし、証明済みの
composition seedとcaller所有の有限上限を使う。副作用がなく決定的であり、その出力は
通常のtyped loweringへ合流する。

Description requestでは、Stage 1が受け取れるのは上限付きsignature、parameter schema、
短いsummaryだけである。定義bodyや展開済みDDLは決して受け取らない。未知または曖昧な
修飾語を含むdirect DDLは明示的に失敗し、隠れたLLM fallbackを発動しない。

## Geometryと個数の境界

Macroが出力するのは最終geometryではなく、型付きcore meaningである。Sizeには、未指定、
明示的なqualitative指定、明示的なnumeric geometryという3つの異なるauthorityがある。
明示的なnormalは未指定ではない。Positionも同様に、名前付きcenter、qualitative region、
正確なnumeric coordinateを区別する。正方形でないcanvasでは、Xは幅に対する比、Yは高さに
対する比である。Isotropic sizeは自身のallocationまたは短辺を使うため、circleは円を保ち、
ellipseのaspectも保たれる。`(0.0,0.0)`は左上、`(1.0,1.0)`は右下、
`(0.5,0.5)`は正確な中央である。

正確なcanonical primitive setは`line`、`circle`、`ellipse`、`triangle`、`square`、
`polygon`、`arc`、`cloudform`である。Geometryは`inku.geometry-resolution-policy.v1`として
識別される唯一の`inku-ddl` ownerだけが解決する。Pluginは別のownerや9番目のprimitiveを
追加できない。正確な個数は、O(count)のallocationまたはmaterializationより前にStep 11の
pure ceilingを通過するまで、損失のないsymbolic intentとして残る。

## 現在の実装状態

共有Rust compiler基盤は、MacroDefinition v1の値をparse、validate、identify、lock、bindし、
決定的に展開できる。Production runtimeへの統合、install可能なpackage catalog、preview、
legacy cutover、汎用user-package loaderは完了していない。したがって本ガイドは、任意のpackageを
現在installまたはloadできるとは主張しない。

`Nature`と`Bamboo`は将来用または説明用のreference-vocabulary名であり、install済みpackageでも
official registryのentryでもない。v1.70のhard-coded Nature展開とlegacy
`.inku-plugin.md` / `fires_on` fixtureは、現在のauthoring formatではない。

現在の`plugin_storage["canvas-aspect"]`、`canvas_aspect` request alias、system/user plugin
directory、plugin statusまたはenable controlは、退役作業が未完了の間のcompatibility surfaceである。
語彙macroのauthoring APIまたはloading APIではない。

Compatibility importerは`legacy_plugin_format`を報告し、macroごとに`Imported`または
`Omitted` outcomeを返す。既存作品は、保存済みScoreまたは展開済みartifactを優先する。
そのようなartifactを持たないomitted macroを、黙って部分描画したり、旧expanderへ永続的に
fallbackしたり、別の図形へ変えたりしてはならない。
