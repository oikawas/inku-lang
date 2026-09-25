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

Parameter schemaは`number`、`exact_decimal`、`integer`、`boolean`、固定長`list`、`semantic_ref`に
閉じている。式は型付きのnumber、exact_decimal、integer、boolean、list、parameter、local、
semantic-reference形式に閉じている。未知のfield、type、expression、operator、
semantic referenceは拒否される。

揺らぎは`{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`のように宣言できる。SemanticRefのoptionalな`dimension`は`amplitude` / `frequency` / `quality`だけで、category=variationだけに許す。省略／Noneは旧category-only matchingとcanonical bytes / digestを保ち、指定した制約はdigestに含む。Parameter名からdimensionを推測しない。

Flat Emitのkeysは`fluctuation_amplitude` / `fluctuation_frequency` / `fluctuation_quality`で、expressionのcategoryは常に`variation`である。対応IDは順に`fine` / `large`、`slowly` / `quickly`、`swaying` / `trembling` / `undulating` / `blurring`。Definition-local `use`も同じ分類を検査し、遅れて決まる実値は実行境界で検査する。通常DDLと同じ写像／不足slotのdefault／対応shapeはSPEC §13.6に従う。

三parameterを宣言したら三値が必須であり、一値だけを渡す呼出しはbinding errorである。一振幅parameterだけを宣言して対応Emit fieldへ届ければ、周波数と質はMedium / Perlinになる。三slot全省略はvariationなし。誤値をNoneへ変えず、未宣言callerはinvocation、malformed EmitはEmit単位の既存診断・省略を保つ。この機能はruntime / UI / 保存へ未接続で、内部Variation JSONを書く方式ではない。

Bodyでは`emit`、`use`、`group`、`anchor`、`relation`、上限付き`repeat`、
型付き`transform`、決定的で上限付きの`vary`を使える。`components`は同じ定義内だけに
属する。定義には、任意code、I/O、filesystem、network、clock、environmentへのaccess、
再帰またはcomponent cycle、外部macro dependency、raw SVGまたはScore data、Renderer命令、
plugin固有のparser、grammar、rendererを含められない。

任意の`aliases`は、同じ名前空間で同じ定義を呼ぶ別の見出しの配列である（例: 正式名`YoungLeaves`に`["若葉"]`）。正式名は英語の見出しとし、日本語名は別名にする。別名は文字・数字・`_`・`-`だけで、見出しや他の別名と重ねない。空なら省略し、正準bytesとdigestに影響しない（[SPEC §4.13](SPEC.ja.md#413-正式名と別名)）。同梱プラグイン文書では語の節に`aliases: 若葉`と書く。

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
短いsummaryだけである。定義bodyや展開済みDDLは決して受け取らない。作品計画は、記述に
プラグイン名の見出しの語かその言い換えが書かれたときだけ、そのプラグインを名前だけの文
として選ぶ。summaryは、そのプラグインが何を描くかをLLMが判断できるように書く。
未知または曖昧な修飾語を含むdirect DDLは、隠れたLLM fallbackを発動しない。その文だけを
省略して残りを描き、未登録／無効化中／名前の誤り／版違いのどれかを作者に示す
（[SPEC §4.12](SPEC.ja.md#412-未登録のプラグインとddlの書き出し)）。

保存済み作品は使った定義の実物を持つ。別の環境へDDLを持ち運ぶときは、作品を
`inku.ddl-export.v1`（DDLと、DDLが名前を書く定義）として書き出し、新規DDLとして読み込む。
読み込んだ定義はその作品だけで使い、導入はしない。

## Geometryと個数の境界

Macroが出力するのは最終geometryではなく、型付きcore meaningである。Sizeには、未指定、
明示的なqualitative指定、明示的なnumeric geometryという3つの異なるauthorityがある。
明示的なnormalは未指定ではない。Positionも同様に、名前付きcenter、qualitative region、
正確なnumeric coordinateを区別する。正方形でないcanvasでは、Xは幅に対する比、Yは高さに
対する比である。Isotropic sizeは自身のallocationまたは短辺を使うため、circleは円を保ち、
ellipseのaspectも保たれる。`(0.0,0.0)`は左上、`(1.0,1.0)`は右下、
`(0.5,0.5)`は正確な中央である。

正確なcanonical primitive setは`line`、`circle`、`ellipse`、`triangle`、`square`、
`polygon`、`arc`、`point`、`cloudform`である。Geometryは`inku.geometry-resolution-policy.v1`として
識別される唯一の`inku-ddl` ownerだけが解決する。Pluginは別のownerや10番目のprimitiveを
追加できない。正確な個数は、O(count)のallocationまたはmaterializationより前にStep 11の
pure ceilingを通過するまで、損失のないsymbolic intentとして残る。

## 正確な数値の宣言と配送

正確な十進数は `{"expr":"exact_decimal","value":"0.240"}` のように記す閉じた型で、通常DDLと同じExactDecimalを使う。定義の元表記を保持し、canonical identityでは `0.240` と `0.24` を同じ値に正規化する。既存 `number` / `Number(f64)` の意味・定義bytesは変えず、f64からexact値を復元しない。Literal、宣言parameter、local、component、有限choicesはexact型を保つ。一般算術やexact値のrange / transformへの暗黙変換は追加しない。

Parameterは `{"type":"exact_decimal","dimension":"radius"}` のように宣言する。Optional dimensionは `radius` / `diameter` / `length` / `side` / `width` / `height` / `chord` / `sagitta` / `position_x` / `position_y` に限る。Callerの明示dimensionと値を一意かつ完全に束縛し、parameter名から意味を推測しない。Dimension省略はdimensionを持たない単独数値にだけ一致する。 同じclauseに通常primitiveとexact parameterを持つMacroが混在する場合は、既存の数値owner未対応境界を維持し、曖昧な割当として診断する。別clauseには影響しない。幅と高さ、弦長と矢高、XとYの複合factは全成分が同一呼出しへ束縛された場合だけ移管し、元keywordとdecimalの出典を保持する。

Flat Emitの同名fieldへexact値を渡す。`width`+`height`、`chord`+`sagitta`、`position_x`+`position_y`は両方が必要で、欠落・型不一致は診断する。数値位置はnamed `place`と別authorityで、両者を黙って上書きしない。寸法・位置は通常DDLと同じresolverへ届き、サイズ重複は診断付きで小さい候補を採る。Definition literalのownerは生成元のEmitであり、架空の原文spanを作らない。Count1/placeのactual Scoreと反復planを扱い、反復個体の生成は後続materializationに残す。

## 現在の実装状態

`transform`は透明な`group`のEmit連続範囲を内側から外側へ保ち、Count1ではScore 0.5.0の`transform_groups`へ、反復では個体を作らないsymbolic planへ届く。有限の`scale_x` / `scale_y`と`translate_x` / `translate_y`は、bbox中心でのscale、同中心でのrotate、normalized canvas軸のtranslateをgeneral affineとして合成する。geometryと間隔だけを変え、stroke幅とgrain pitchは保つ。Score 0.4.0の回転だけのgroupは互換として残る。外部のTouching / Along / Cuttingは変形後の形・向き・明示指定を保ち、group全体の平行移動で成立を試みる。失敗時はrelationだけをerrorとして外し、groupは元の変形後配置で描く。Step11 materializationとStep13 runtime / UI / 保存cutoverは未完了である。

通常DDLのprimitiveだけからなる既存named位置のdirect coordinated groupはScore 0.8.0の`placement_groups`へ届く。内部配置を省略すると`overlap`でmemberのbbox中心を揃え、「並べて置く」は既存wire値の`horizontal_source_order`、「重ねて置く」は`overlap`、`散らす`と`敷き詰める`は新しいwire値の`scatter`と`tile`となる。一つのnamed regionをperformance seedで一度だけ解決し、group全体を移す。memberのowner、count、seed、geometryは保つ。line-upの省略countは各member 1 でactual Scoreへ届く。scatter / tileは明示countを保ち、合計8までの残りを省略したmemberへ均等配分し、余りはsource順で先の省略memberへ割り当てる。省略memberは最低1個とし、明示数と最低数だけで8を超える場合も減らさない。全省略も同じ規則で、9種類なら各1個になる。全明示なら合計8へ補わない。line-up / placeは省略memberだけ1とする。配分後の全countが1のときだけactual Scoreへ届き、それ以外は個体化せずsymbolic planに残る。このdirect carrierはMacro authoring operatorや個体materializationを追加しない。

AnchorはScore 0.6.0の非描画targetとして、明示したnamed位置または数値座標をConnectedへ届ける。`place:center`は画面中央で、Emitのfocus依存配置を借用しない。包含Transformへ追従し、描画instructionの順序とseed、旧版保存互換を保つ。

Runtime未接続のfinite flat Emit consumerは、明示movement:placeとcircle / ellipse / cloudform /
square / triangle / polygon / line / arc / pointを通常DDLと同じgeometryへ届ける。Placeはcenter（exact generated focus必須）と
top / bottom / left_edge / right_edge / top_edge / bottom_edge / cornerを受け入れ、SPEC §18の領域を使う。
Literal semantic_refと明示宣言した`{"type":"semantic_ref","category":"place"}` parameterは同じ経路を通る。
隅はStage 2がattested meaning / composition seed / 元occurrenceから選び、隅内anchorはRendererが選ぶ。
生成した座標を原文出典として挿入せず、未宣言callerの暗黙overlayや位置省略のdefaultを追加しない。
隣接bound Emitのconnected / touchingは、通常DDLと同じnamed-movableまたはnumeric-fixedの位置authorityを保って共有checked performerへ届ける。
not_touchingとbetweenはnamed／noncenter位置も通常DDLと同じchecked performerへ届け、数値位置はfixedのauthorityを保つ。NotTouchingは既存Medium gapを使い、Betweenはcurrent直前のEmitとさらに一つ前のEmitのbbox中心を使う既存recipeを保つ。Betweenのfromは直前Emitであり、その一つ前を第二参照として両方のownerを保持する。
隣接性はunbound Emitを含む元順序で判定し、省略されたfromまたはBetweenの二参照を他のsurvivorへ付け替えない。
旧Stop入力も受けるが、recoverableなrelation失敗で新Score全体を止めない。relationだけをerrorとして外し、元ownerと変形後配置を保って描く。OmitAndContinueは既存の最小省略単位を保ち、integrity不良は両mode停止とする。

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

Score 0.9の`placement_groups.members`はMacro bodyを順序付きdrawable範囲とAnchor所有として原子的に運ぶ。Macro authoring operatorや反復個体化を追加せず、group head countと内部Emit countを分ける。standalone Macroの外側反復もsymbolic planへ保持し、個体化はStep11で行う。

memberの`transform_group_indices`はsource-owned内部transformを配置前に保つ。先行drawableの後にAnchor-only Transform memberが続く場合も、validなmember範囲はそのAnchorを含む。unlistedの同範囲transformはouterとして後に実行する。

`CompositionPlanResult.standalone_macro_repetitions`は既存body位置、range、Anchor、内部transform、source head repeat countをsymbolicに保持し、outer placementやactual Score instanceを作らない。

Compatibility importerは`legacy_plugin_format`を報告し、macroごとに`Imported`または
`Omitted` outcomeを返す。既存作品は、保存済みScoreまたは展開済みartifactを優先する。
そのようなartifactを持たないomitted macroを、黙って部分描画したり、旧expanderへ永続的に
fallbackしたり、別の図形へ変えたりしてはならない。
