# inku 語彙プラグイン作成ガイド

inkuにおけるプラグインは、データだけで記述する語彙マクロである。`Nature.雨`のような
目に見える修飾名は、版を持つ1つの`inku.macro-definition.v1`定義を呼び出し、
通常の型付きコア意味へ展開される。プラグインは実行可能コードでも、parserの拡張でも、
Rendererのhookでもない。

Canvasの選択は`inku.canvas-format-registry.v1`が所有するhost optionであり、
プラグインではない。Render Engine Packは描画coreを置き換える別の仕組みである。
プラグイン境界の規範は[SPEC §4](SPEC.ja.md#4-プラグイン設計原則)にある。

## 定義形式

宣言済みflat Emitの`movement`が`line_up` / `scatter` / `tile`なら、verified Stage 1.5後の共有plan APIで通常DDLと同じobject-size / placement resolverへ届く。Emitのcount省略は8、明示正整数はu32::MAXまで保持し、必須parameter不足やbad型をdefaultにしない。Sizeはcanvas短辺基準でcount非依存、9shapeのnormal / 大小倍率・外観・angleを保つ。Optionalな`layout_direction`は既存`angle` categoryのSemanticRefを要求し、literal・宣言済みparameter / localから展開する。Shapeの`angle`とは別fieldで、line_upだけへ横 / 縦 / 物理45度の配置を届ける。省略横一列と明示horizontalのidentityを区別し、bare diagonalは元meaning・attestされたoptional composition seed・元occurrenceの専用roleで二軸から選ぶ。未対応action / rotated等の方向や未宣言caller方向は元実行単位で停止・省略し、同category複数parameterを名前で推測しない。物理aspectのtile、後続performance seedを要求するscatter recipeとgenerated owner / binding / provenanceも保持し、未宣言caller overlayやfan-outを作らない。Stop / Continueのfield / Emit / invocation省略単位を保ち、Ready planは個体配列・Score・描画成功ではない。新fieldなしの既存place / count1のScore成功経路は変わらず、方向を持つEmitをScore入口で無音にdropしない。Whole Step10、Step11とruntime接続を含む拡張は未完了である。

形状は既存のtriangle / square / polygon identityを使う。Optional Emit fieldの`proportion_aspect`はratio categoryのtall / wide、`shape_form`は閉じたcore shape_form categoryのregular、`sides`は5〜8のIntegerである。定義literal、宣言済みparameter、localを同じconsumerへ運ぶ。Callerは`regular` / `正形`、`sides 6` / `辺数6`等の独立したfactを宣言へbindし、同型の複数Integer parameterは名前で解かない。未宣言factと必要引数の欠落を捨てたり補ったりしない。通常DDLと同じnormal、正形、2:1の省略aspectを解決し、place / count1はactual Score、反復はexact制約を保持するplanへ届く。三角・四角のbbox中心とpolygonの外接円を使い、regularとaspectの矛盾や範囲外sidesは元Emitの停止・省略とする。一般numeric geometryのEmit fieldは追加しない。

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

揺らぎは`{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`のように宣言できる。Optionalな`dimension`は`amplitude` / `frequency` / `quality`だけで、category=variationだけに許す。省略／Noneは旧category-only matchingとcanonical bytes / digestを保ち、指定した制約はdigestに含む。Parameter名からdimensionを推測しない。

Flat Emitのkeysは`fluctuation_amplitude` / `fluctuation_frequency` / `fluctuation_quality`で、expressionのcategoryは常に`variation`である。対応IDは順に`fine` / `large`、`slowly` / `quickly`、`swaying` / `trembling` / `undulating` / `blurring`。Definition-local `use`も同じ分類を検査し、遅れて決まる実値は実行境界で検査する。通常DDLと同じ写像／不足slotのdefault／対応shapeはSPEC §13.6に従う。

三parameterを宣言したら三値が必須であり、一値だけを渡す呼出しはbinding errorである。一振幅parameterだけを宣言して対応Emit fieldへ届ければ、周波数と質はMedium / Perlinになる。三slot全省略はvariationなし。誤値をNoneへ変えず、未宣言callerはinvocation、malformed EmitはEmit単位の既存診断・省略を保つ。この機能はruntime / UI / 保存へ未接続で、内部Variation JSONを書く方式ではない。

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

Runtime未接続のfinite flat Emit consumerは、明示movement:placeとcircle / ellipse / cloudform /
square / line / arc / pointを通常DDLと同じgeometryへ届ける。Placeはcenter（exact generated focus必須）と
top / bottom / left_edge / right_edge / top_edge / bottom_edge / cornerを受け入れ、SPEC §18の領域を使う。
Literal semantic_refと明示宣言した`{"type":"semantic_ref","category":"place"}` parameterは同じ経路を通る。
隅はStage 2がattested meaning / composition seed / 元occurrenceから選び、隅内anchorはRendererが選ぶ。
Sourceやprovenanceへ座標を挿入せず、未宣言callerの暗黙overlay、位置省略、count反復を追加しない。
隣接bound Emitのconnected / touchingは両者がexact centerの場合に限り、noncenter relationを黙って捨てない。
Stopは新Scoreなし、OmitAndContinueは元ownerと既存の最小省略単位を保ち、integrity不良は両mode停止とする。

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
