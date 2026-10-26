# inku 語彙プラグイン作成ガイド

inkuのプラグインは、データだけで書く語彙マクロである。DDLに`Sky.星`のような名前を書くと、
その名前の`inku.macro-definition.v1`定義が呼ばれ、円・線・弧などの通常の指示へ展開されて描かれる。
プラグインは実行するコードでも、構文の拡張でも、Rendererのhookでもない。

このガイドは、人もAIも読んで、今の仕様で読み込める新しいプラグインを作れるように書いてある。
§1〜§9が作り方、付録Aが実装の詳細である。プラグイン境界の規範は[SPEC §4](SPEC.ja.md#4-プラグイン設計原則)にある。
Canvasの選択（`inku.canvas-format-registry.v1`）とRender Engine Packは、プラグインとは別の仕組みである。

## 1. 作る手順

1. 定義をJSONで書く（§2の手本、§3の形式）。
2. 定義と、要約（§6）・説明・例文をプラグインのファイル（`inku.plugin-package.v1`、§5.1）にまとめる。
3. Serverの管理者は、Webの設定「プラグイン」の「プラグインを追加」でファイルを選ぶ（§5.1）。
   Serverがすぐに検査し、駄目なところはファイルの中の場所と理由が語ごとに出る（§7）。
   通った語には歳時記に出る絵と例が出るので、確かめて「追加する」を押す。
4. DDLで名前を書いて呼ぶ（§4）。追加した語は、そのServerの全ての新しい作品で描け、歳時記にも出て、
   記述から描くときは下絵（Stage 1）が要約を読んで選ぶ。

Serverに入れずに自分の作品だけで試すなら、DDLの書き出しファイル（§5.2）に入れて読み込む。

## 2. 手本: `Sky.Stars`（別名 `Sky.星`）

空の上半分に黄色の星を散らす語である。書いた個数（1〜9個）を受け、書かなければ3〜5個を描く。
星の位置は表から順に取り、大きさは星ごとに「とても小さい」か「小さい」を選ぶ。

```json
{
  "schema": "inku.macro-definition.v1",
  "namespace": "Sky",
  "heading": "Stars",
  "aliases": ["星"],
  "version": "1.0.0",
  "parameters": {
    "star_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 9, "omitted": [3, 4, 5], "counter": "general"}
  },
  "components": {},
  "body": [
    {
      "op": "repeat",
      "count": {"expr": "parameter", "name": "star_count"},
      "maximum": 9,
      "index": "star_index",
      "body": [
        {
          "op": "vary",
          "binding": "star_size",
          "domain": "sky_stars_size",
          "choices": [
            {"expr": "semantic_ref", "category": "relative_scale", "id": "very_small"},
            {"expr": "semantic_ref", "category": "relative_scale", "id": "small"}
          ],
          "body": [
            {
              "op": "emit",
              "binding": null,
              "fields": {
                "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                "position_x": {"expr": "cycle", "index": {"expr": "local", "name": "star_index"}, "items": [
                  {"expr": "exact_decimal", "value": "0.170"}, {"expr": "exact_decimal", "value": "0.830"},
                  {"expr": "exact_decimal", "value": "0.500"}, {"expr": "exact_decimal", "value": "0.330"},
                  {"expr": "exact_decimal", "value": "0.670"}, {"expr": "exact_decimal", "value": "0.170"},
                  {"expr": "exact_decimal", "value": "0.830"}, {"expr": "exact_decimal", "value": "0.500"},
                  {"expr": "exact_decimal", "value": "0.330"}
                ]},
                "position_y": {"expr": "cycle", "index": {"expr": "local", "name": "star_index"}, "items": [
                  {"expr": "exact_decimal", "value": "0.100"}, {"expr": "exact_decimal", "value": "0.140"},
                  {"expr": "exact_decimal", "value": "0.280"}, {"expr": "exact_decimal", "value": "0.180"},
                  {"expr": "exact_decimal", "value": "0.080"}, {"expr": "exact_decimal", "value": "0.380"},
                  {"expr": "exact_decimal", "value": "0.340"}, {"expr": "exact_decimal", "value": "0.120"},
                  {"expr": "exact_decimal", "value": "0.420"}
                ]},
                "relative_scale": {"expr": "local", "name": "star_size"},
                "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
                "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
                "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
              }
            }
          ]
        }
      ]
    }
  ]
}
```

読み方:

- `star_count`は語に書いた個数を受ける引数である（§3.4）。`repeat`がその回数だけ中身を繰り返し、`star_index`に0から順の番号を入れる。
- `cycle`は番号で表から一つを取る。9つの位置は、何個でも上半分に偏らず広がる順に並べてある。
- `vary`は、決まった種から選択肢の一つを選ぶ。`repeat`の中にあるので、星ごとに選び直す。
- `emit`が1つの図形の指示になる。ここでは鉛筆の黄で塗った円を、数で決めた位置に置く。

この定義を書き出しファイルに入れたもの（§5.2）は次の形である。`ddl`は読み込んだときにDDL欄へ入る文である。

```json
{
  "schema": "inku.ddl-export.v1",
  "language": "ja",
  "ddl": "背景を黒で埋める。\n5個のSky.星。",
  "plugins": [
    {
      "definition": { "…": "上の定義をそのまま入れる" },
      "summary": "空の上半分に、黄色の星を散らす。星の数を書けばその数（1〜9個）、書かなければ3〜5個。星は鉛筆の黄で塗った小さな円で、大きさは星ごとにとても小さいか小さい。"
    }
  ],
  "exported_from": {}
}
```

2026-10-26に、この定義をServerの`/api/compose`へ書き出しファイルとして渡し、共有coreで確かめた結果:
`5個のSky.星。`と`5 Sky.Stars.`は5つ、`Sky.星。`は書かない個数の候補から3〜5つ、`9個のSky.星。`は9つの円を、
診断なしで描いた。`12個のSky.星。`は範囲の外なので、その語が外れた。

## 3. 定義の形式

### 3.1 最上位の欄

定義は次の欄だけを持つ。知らない欄があると定義全体が受け付けられない。

| 欄 | 必須 | 中身 |
|---|---|---|
| `schema` | 必須 | 正確に`inku.macro-definition.v1` |
| `namespace` | 必須 | 名前空間。英字で始まり、英数字・`_`・`-`だけ（例: `Sky`） |
| `heading` | 必須 | 見出し。空でなく、前後に空白が無く、制御文字を含まない。正式名は英語にする（例: `Stars`） |
| `aliases` | 任意 | 同じ名前空間で同じ定義を呼ぶ別名の配列（例: `["星"]`）。文字・数字・`_`・`-`だけで、見出しや他の別名と重ねない。空なら書かない |
| `version` | 必須 | `1.0.0`の形のsemantic version |
| `parameters` | 必須 | 呼出しから受ける引数（§3.4）。無ければ`{}` |
| `components` | 必須 | 定義の中だけで使う部品（§3.6の`use`）。無ければ`{}` |
| `body` | 必須 | 描く中身の文の並び（§3.6） |

DDLに書く名前は`namespace.heading`（例: `Sky.Stars`）か`namespace.別名`（例: `Sky.星`）である。
同じ名前空間の語は一つの名前を一つの定義だけが持てる。すでに読み込まれた定義と同じ正式名や別名を持つ定義は、
後から来た方が受け付けられない（§5.2の書き出しファイルの定義だけは、その作品で同名の定義より優先される）。
Webから追加するときは、ほかのプラグインがすでに持つ名前の語を検査が断る（§5.1）。
名前空間の考え方は[SPEC §4.10](SPEC.ja.md#410-名前空間の規約)、正式名と別名は[SPEC §4.13](SPEC.ja.md#413-正式名と別名)にある。

定義の中身を変えたら`version`を上げる。保存済みの作品は使った定義の実物とdigestを持つので、後から定義を変えても描き直しは変わらない。

### 3.2 識別子

引数・部品・`emit`の`binding`・`anchor`の`name`・`repeat`の`index`・`vary`の`binding`と`domain`は、
英字で始まり、英数字・`_`・`-`だけの名前にする。同じ定義の中で`binding`と`anchor`の名前、`repeat`と`vary`の名前は重ねない。

### 3.3 式

値はすべて、`expr`で種類を示すJSONで書く。

| `expr` | 他の欄 | 意味 |
|---|---|---|
| `semantic_ref` | `category`, `id` | 意味の語（§3.8）。例: `{"expr":"semantic_ref","category":"color","id":"red"}` |
| `exact_decimal` | `value`（文字列） | 正確な十進数。位置と寸法はこれで書く。例: `{"expr":"exact_decimal","value":"0.25"}` |
| `integer` | `value` | 整数 |
| `number` | `value` | 小数（f64）。`transform`の量などに使う |
| `boolean` | `value` | 真偽 |
| `list` | `items` | 固定長の並び |
| `cycle` | `items`, `index` | `index`（0以上の整数）番目の項を取る。端を越えると先頭へ戻る。`items`はすべて同じ種類にする |
| `parameter` | `name` | 宣言した引数の値 |
| `local` | `name` | `repeat`の`index`か`vary`の`binding`の値 |

算術（足し算・掛け算など）は無い。数を組み合わせたいときは、`cycle`の表や`vary`の選択肢として値を書き並べる。

### 3.4 引数（parameters）

引数は名前から型への表である。型は次に限られる。

| `type` | 他の欄 | 呼出しで結ばれるもの |
|---|---|---|
| `semantic_ref` | `category`、任意の`dimension` | 呼出しに書いたその分類の語。例: 色の引数は`赤いSky.色星。`の「赤い」を受ける |
| `exact_decimal` | 任意の`dimension` | 呼出しに書いた数。`dimension`は`radius`・`diameter`・`length`・`side`・`width`・`height`・`chord`・`sagitta`・`position_x`・`position_y` |
| `integer` | — | 呼出しに書いた数 |
| `integer`（個数） | `receives: "count"`, `minimum`, `maximum`, `omitted`, 任意の`counter` | 語に書いた個数（下の説明） |
| `number` | — | 呼出しに書いた数 |
| `boolean` | — | — |
| `list` | `length`, `items` | — |

- 宣言した引数は、個数の引数を除いてすべて必須である。呼出しに書かれないと、その呼出しは描かれない。
  黙って既定値を入れることはない。
- 同じ分類の引数を二つ宣言しても、引数の名前からどちらへ結ぶかを推測しない。分類ごとに一つにする。
- 宣言していない語を呼出しに書くと、その語だけが診断付きで外れる（例: `Sky.星を7個散らす。`の「散らす」）。
  定義の中の値は上書きされない。
- 揺らぎの引数は`{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`のように、
  `dimension`（`amplitude`・`frequency`・`quality`）で幅・速さ・質を分けられる。

**語の個数を受ける引数。** 語に書いた個数（`5個のSky.星。`、`5 Sky.Stars.`）は、受けると宣言しない限り、
語全体を外から繰り返す。中の個数として受けるには、整数の引数に`receives: "count"`と範囲を宣言し、
本体の`repeat`の`count`でその引数を読む。

```json
"star_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 9, "omitted": [3, 4, 5], "counter": "general"}
```

- 宣言できるのは定義の最上位の引数に一つだけで、部品の引数には置けない。
- `minimum`は1以上で`maximum`以下、`omitted`は空でなく、重複せず、範囲の中の整数だけを並べる。
- `repeat`の`maximum`は引数の`maximum`以上にする。
- 個数が書かれなければ、`omitted`の候補から呼出しの種で一つを決まった仕方で選ぶ。
- 範囲の外の個数は`macro_binding_count_out_of_range`の診断を出してその語だけを外し、ほかは描く。丸めない。
- `counter`（`flat`は枚、`long`は本、`general`は個）は、下絵が日本語のDDLに個数を書くときの助数詞だけを決める。

### 3.5 位置と大きさの決まり

- 位置の数は画面に対する割合である。`(0.0, 0.0)`が左上、`(1.0, 1.0)`が右下、`(0.5, 0.5)`が中央。
  正方形でない紙では、xは幅、yは高さに対する割合になる。
- 寸法の数も割合で、円・楕円・点の大きさは短い辺に対する割合である（`radius` 0.24は、短い辺が500pxなら半径120px）。
  紙の形が変わっても円は円のままである。中心と半径を足して1を超えると、画面の外へはみ出す。
- 大きさは`radius`などの寸法か`relative_scale`のどちらか一方で書く。
- 大きさを書かない図形は、通常のDDLと同じ普通の大きさになる。`relative_scale`の`normal`を明示したときと、書かないときは別の扱いである。
- 図形の種類は`line`・`circle`・`ellipse`・`triangle`・`square`・`polygon`・`arc`・`point`・`cloudform`の9つで、プラグインは10番目の図形を足せない。

### 3.6 本体の文（body）

文は`op`で種類を示す。

| `op` | 欄 | 意味 |
|---|---|---|
| `emit` | `binding`（名前か`null`）, `fields` | 図形1つの指示。`fields`は§3.7。`binding`に名前を付けると`relation`で指せる |
| `repeat` | `count`, `maximum`, `index`, `body` | `count`回（整数の式）`body`を繰り返す。`maximum`は1以上の上限で、`count`がそれを超えてはいけない。`index`に0からの番号が入る |
| `vary` | `binding`, `domain`, `choices`か`range`, `body` | 種から値を一つ選んで`binding`に入れ、`body`で使う。`choices`は同じ種類の式の並び、`range`は`{"start","end","step"}`。`domain`は選び方を他の`vary`と分ける名前 |
| `use` | `component`, `arguments` | 同じ定義の`components`の部品を呼ぶ。部品の引数はすべて渡す |
| `group` | `body` | 文をまとめる。配置は足さない |
| `transform` | `transform`, `body` | `body`の図形をまとめて動かす。`transform`は`translate_x`・`translate_y`・`scale_x`・`scale_y`・`rotate_degrees`のうち一つ以上（数）。拡大縮小と回転はまとまりの外接矩形の中心で行い、移動は画面の割合で行う |
| `anchor` | `name`, 任意の`fields` | 描かない目印の点。`fields`は`place`か、`position_x`と`position_y`の組のどちらか一方 |
| `relation` | `kind`, `from`, `to` | 二つの`emit`（`binding`）や`anchor`の関係。`kind`は§3.8の関係の語 |

- **`vary`は出会うたびに選び直す。** `repeat`の中の`vary`は繰り返しのたびに、x用とy用に分けた`vary`はそれぞれ別に選ぶ。
  二つの位置の表から一つを選ぶつもりでxとyを別の`vary`にすると、表が混ざって図形が重なることがある。
  位置は`cycle`の表で決め、`vary`は大きさや色など、混ざってよいものに使う。
- 選ぶ種は作品の構図の種から来る。同じ種なら同じ画になり、種が変わると選び方も変わる。
- 部品は自分自身を（間接的にも）呼べない。他の定義の部品も呼べない。
- `relation`は、同じ展開の中で隣り合う`emit`の間で働く。`connected`・`touching`・`not_touching`・`between`・`along`・`cutting`を使える。
  成り立たない関係は、その関係だけが診断付きで外れ、図形は描かれる。二つの弧を`touching`でつなぎ、
  後の弧を`surface: solid`で塗ると、二つの弧を一つの閉じた輪郭として内側を塗る（葉の形。[SPEC §4.11](SPEC.ja.md#411-自由度の境界)）。

### 3.7 `emit`の欄

`emit`は次の欄を持てる。これ以外の欄は受け付けられない。

| 欄 | 値 | 書くこと |
|---|---|---|
| `shape` | `shape`の語 | 必須。§3.5の9つの図形 |
| `movement` | `movement`の語 | 必須。今の描画に届くのは`place`。`line_up`・`scatter`・`tile`は付録Aの範囲 |
| `place` | `place`の語 | `position_x`と`position_y`の組とどちらか一方。`center`・`top`・`bottom`・`left_edge`・`right_edge`・`top_edge`・`bottom_edge`・`corner` |
| `position_x`, `position_y` | `exact_decimal` | 二つ組で書く。画面に対する割合 |
| `radius`, `diameter`, `length`, `side`, `width`, `height`, `chord`, `sagitta` | `exact_decimal` | 寸法。`width`と`height`、`chord`と`sagitta`は組で書く。線は`length`、弧は`chord`と`sagitta`、点は`radius`か`diameter` |
| `relative_scale` | `relative_scale`の語 | 普通の大きさに対する倍率 |
| `color` | `color`の語 | 色 |
| `touch` | `touch`の語 | 画材 |
| `continuity` | `continuity`の語 | 線の連なり（実線・破線など） |
| `surface` | `surface`の語 | 面の塗り。`none`は輪郭だけ、`solid`は塗りつぶし、ほかは質感の語 |
| `surface_intensity` | `handling`の語 | 面の質感の濃さ |
| `angle` | `angle`の語 | 傾き。点には書けない |
| `thinness` | `thinness`の語 | 線の細さ。閉じた形では輪郭の線に効く |
| `fluctuation_amplitude`, `fluctuation_frequency`, `fluctuation_quality`, `ink_spread` | `variation`の語 | 揺らぎの幅・速さ・質と、にじみ。幅だけを書くと速さは中、質は既定になる |
| `proportion_aspect` | `ratio`の`tall`・`wide` | 縦長・横長 |
| `proportion_width_extent`, `proportion_arc_form` | `ratio`の語 | 全幅・半幅、半円・上弦・下弦・三日月 |
| `shape_form` | `shape_form`の`regular` | 正形 |
| `sides` | 整数5〜8 | 多角形の辺の数 |
| `count`, `layout_direction` | 整数、`angle`の語 | 付録Aの範囲。個数は`repeat`で書く |

値の分類が欄と合わないと受け付けられない（例: `color`の欄に`touch`の語）。
書かない欄は、通常のDDLと同じ既定になる。

### 3.8 意味の語（semantic_ref）の調べ方

`semantic_ref`の`id`は、歳時記（`core/crates/inku-ddl/assets/saijiki-v2.json`）の語の英語の識別子である。
語の`score_value`があればそれ、無ければ`surface_en`の`-`と空白を`_`にしたものになる。表は製品とともに変わるので、
写さずに次のコマンドで今の一覧を出す。

```sh
python3 - <<'PY'
import json
names = {"katachi": "shape", "katamuki": "angle", "tezawari": "touch", "tsuranari": "continuity",
         "omote": "surface", "sabaki": "handling", "kime": "fineness", "shitaji": "underlayer",
         "ji": "ground", "iro": "color", "yuragi": "variation", "basho": "place",
         "ugoki": "movement", "jun": "sequence", "wariai": "ratio"}
asset = json.load(open("core/crates/inku-ddl/assets/saijiki-v2.json"))
for category in asset["categories"]:
    ids = []
    for word in category["words"]:
        wire = word.get("score_value") or (word.get("surface_en") or "").replace("-", "_").replace(" ", "_")
        if wire:
            ids.append(f"{wire}（{word['surface_ja']}）")
    print(names[category["key"]] + ": " + ", ".join(ids))
print("relation: " + ", ".join(r["relation_type"] for r in asset["relations"]))
PY
```

productのcheckoutの最上位で走らせる。出力の行頭が`category`、各項目が`id（日本語の語）`である。
`shape`の`free_line`は一覧にあるが、プラグインの図形には使えない（§3.5の9つだけ）。

歳時記の外にある三つの分類は、coreが決めた閉じた語である。

| 分類 | 語 |
|---|---|
| `thinness` | `fine`, `extra_fine` |
| `relative_scale` | `very_small`, `small`, `slightly_small`, `normal`, `slightly_large`, `large`, `very_large` |
| `shape_form` | `regular` |

## 4. DDLでの呼び方

| 書き方 | 意味 |
|---|---|
| `Sky.星。` / `Sky.Stars.` | 名前だけの文。個数の引数があれば`omitted`から選ぶ |
| `5個のSky.星。` / `5 Sky.Stars.` | 個数を付けた文。個数の引数があればその数を受ける |
| `赤いSky.色星。` / `red Sky.ColorStars.` | 引数の分類の語を前に書く（色の引数を宣言した定義の場合） |
| `中心に赤い円を置く。` と並べる | プラグインの文は、ほかの文と一緒に書ける |

- 日本語のDDLでも英語のDDLでも、正式名と別名のどちらで呼んでもよい。下絵は日本語のDDLでは別名、英語のDDLでは正式名を書く。
- 定義が受けない語（`置く`・`散らす`・`Place`など）を一緒に書くと、その語だけが診断付きで外れる。
  個数を受ける語には`5個のSky.星。`の形で書く。
- 名前が解決できない文（読み込んでいない、無効にしてある、名前の誤り、中身の違う定義）は、その文だけが外れ、
  残りは描かれる。理由は作品の診断に出る（[SPEC §4.12](SPEC.ja.md#412-未登録のプラグインとddlの書き出し)）。
  隠れたLLMで別の語に書き直すことはない。

## 5. 読み込ませる道

今の仕様で新しい定義を読み込める道は四つある。ふつうは§5.1を使う。

### 5.1 Webからプラグインのファイルを追加する（Serverの管理者）

定義と歳時記に出す情報を一つのJSONファイル（`inku.plugin-package.v1`）にまとめ、Webの設定「プラグイン」の
「プラグインを追加」で選ぶ。§2の`Sky.Stars`をファイルにしたものは次の形である。

```json
{
  "schema": "inku.plugin-package.v1",
  "namespace": "Sky",
  "name": "night",
  "version": "1.0.0",
  "description_ja": "夜空の語。",
  "description_en": "Night-sky words.",
  "words": [
    {
      "definition": { "…": "§2の定義をそのまま入れる" },
      "summary_ja": "空の上半分に、黄色の星を散らす。星の数を書けばその数（1〜9個）、書かなければ3〜5個。",
      "summary_en": "Scatters yellow stars over the upper half of the sky: the written count (1–9), or 3–5 when none is written.",
      "note_ja": "夜の空に小さな星。",
      "note_en": "Small stars in a night sky.",
      "example_ja": "5個のSky.星。",
      "example_en": "5 Sky.Stars."
    }
  ]
}
```

| 欄 | 必須 | 中身 |
|---|---|---|
| `schema` | 必須 | 正確に`inku.plugin-package.v1` |
| `namespace` | 必須 | 名前空間。各定義の`namespace`と同じにする（§3.1） |
| `name` | 必須 | プラグインの名前。英字で始まり、英数字・`_`・`-`だけ。`namespace.name`（例: `Sky.night`）がプラグインのid |
| `version` | 必須 | `1.0.0`の形 |
| `description_ja`・`description_en` | 任意 | 設定の画面に出す説明 |
| `authors`・`license` | 任意 | 作者（文字列の配列）と使用条件 |
| `words` | 必須 | 語の並び（1〜64個）。各語は下の欄を持つ |

各語の欄:

| 欄 | 必須 | 中身と、どこに出るか |
|---|---|---|
| `definition` | 必須 | `inku.macro-definition.v1`の定義（§3） |
| `summary_ja`・`summary_en` | どちらか一方 | 下絵（Stage 1）に渡す要約（§6）。片方だけなら、もう一方の言語にも使う |
| `note_ja`・`note_en` | 任意 | 歳時記の見本の説明の行（組み込みの語の「効果」の行に当たる）。何を描く語かを短く書く |
| `example_ja`・`example_en` | 任意 | 歳時記の見本の「例」に出すDDLの文。書かなければ`Sky.星。`（日本語は最初の別名）・`Sky.Stars.`を使う |

歳時記の見本は、題（正式名か別名）・説明（`note_*`）・例（`example_*`）・絵の四つでできている。絵は書かない。
追加するとき、Serverが日本語の例文を描き、描いたところを切り出して歳時記の枠（216×92と、その2倍）に収める。
例文は、語の見た目が分かる個数や書き方で書く（例: `Sky.星`なら`5個のSky.星。`）。

検査は三つを順に行い、全部通ったときだけ追加できる。

1. ファイルの形（知らない欄、必須の欄、`namespace`の食い違い、要約の有無など）。
2. 共有coreによる定義の検査（§7.2の誤り）と、ほかのプラグインがすでに持つ名前との重なり。
3. 各語の日本語と英語の例文を、共有pipelineでDDLとして実際に描く。何も描けない、または診断が出たら駄目になる。

駄目なところは、ファイルの中の場所（例: `words[0].definition.body[0].body[0].body[0].fields.color`）と理由で語ごとに出る。
JSONとして読めない、`namespace`・`name`が読めない、語が無いときだけは1で止まる。それ以外は、要約が無いなどの形の誤りがあっても
2と3を続けるので、一度に全部の直すところが分かる。定義に誤りのある語は、例文を描かない。

- 追加した語は、そのServerの全ての新しい作品で描け、歳時記とDDLエディタの補完に出て、記述から描くときは下絵に要約が渡る。
- 同じid（`namespace.name`）のプラグインが入っていると、「置き換える」になる。置き換えると、新しい作品は新しい定義で描く。
- 語ごとの「絵を差し替える」でPNGを上げると、歳時記の絵がその画像になる（枠に収めて縮める）。「自動の絵に戻す」で
  例文から描いた絵に戻る。置き換えても、差し替えた絵は残る。
- 無効にすると、新しい作品・歳時記・補完から外れる。削除もできる。
- 保存済みの作品は、使った定義の写しを持つので、後から置き換え・無効・削除をしても同じに描き直せる。
- ファイルはServerの`INKU_PLUGIN_PACKAGE_DIR`に置かれる（[Serverの設定 §2.5](manual/ja/server-configuration.md)）。
- APIは`POST /api/plugins/packages/validate`（検査だけ）と`POST /api/plugins/packages`（追加）。どちらも管理者だけが使える。
- Android・macOSはServerを呼ばないので、ここで追加した語はまだ使えない。

### 5.2 DDLの書き出しファイル（作者がすぐ使える）

§2の形のJSON（`inku.ddl-export.v1`）を作って読み込むと、`plugins`の定義がその新しい作品だけで使われる。

| 欄 | 中身 |
|---|---|
| `schema` | 正確に`inku.ddl-export.v1` |
| `language` | `ja`か`en` |
| `ddl` | 読み込んだときにDDL欄に入る文 |
| `plugins` | `{"definition": 定義, "summary": 要約}`の並び（64個まで） |
| `exported_from` | 書き出し元の情報。自分で作るときは`{}`でよい |

- Web: 記述タブの下の「指示書を新規作成」を開き、「読み込む」でファイルを選ぶ。読み込んだ定義の名前が表示される。
- CLI: `uv run inku-cli paint --input-mode ddl --file stars.ddl.json`のように渡す。
- Android・macOSも同じ形式を読む。
- 読み込んだ定義は導入されない。同名の登録済み定義より優先され、中身が違うときや未登録のときはcatalogの診断
  （`imported_plugin_differs_from_installed`・`imported_plugin_not_installed`）で知らせる。
- 描いた作品を書き出すと、DDLが名前を書く定義と要約が同じ形式で入るので、別の環境へ持ち運べる。

### 5.3 Serverのpipeline manifest（管理者が全ての新しい作品に入れる）

Serverの`INKU_PIPELINE_CONFIG`が指すmanifestの`pipeline.definitions`に定義を、`pipeline.macro_summaries`に
同じ順で要約を入れる。manifestの作り方は[Serverの設定 §2.4](manual/ja/server-configuration.md)にある。

```json
"definitions": [ { "schema": "inku.macro-definition.v1", "namespace": "Sky", "heading": "Stars", "…": "…" } ],
"macro_summaries": [ "空の上半分に、黄色の星を散らす。…" ]
```

- そのServerの新しい作品の全てで使える。記述から描くときは、下絵（Stage 1）に名前と要約が渡り、記述に語が書かれていれば下絵が選ぶ。
- 二つの並びの長さが違うと、新しい作品の実行が`macro_catalog_summary_mismatch`で失敗する。
- 設定の「プラグイン」画面と歳時記には出ず、そこで有効・無効を切り替えることはできない。§5.1の方が扱いやすい。

### 5.4 共有coreへの同梱（開発の変更）

`Nature.leaves`のように全てのhostへ同梱するには、共有coreの`core/crates/inku-ddl/assets/`に
`inku.bundled-macro-package.v1`のpackageを置き、`inku-pipeline-uniffi/src/macro_catalog.rs`の同梱の名前に足し、
Serverの`server/src/inku_server/plugins/__init__.py`の`_BUNDLED_DOCUMENTS`とAndroidの
`SharedPipelineConfigBuilder.kt`がそのpackageを名指すようにする。これは製品の変更で、buildと配備が要る。

### 5.5 今は使えない道

- `server/plugins/`（`INKU_DOCUMENT_PLUGIN_DIR`）へ新しい`.inku-plugin.md`を置いても、定義にはならない。
  同梱package以外の文書は「描画には使われない」と表示され、その語は外れる。
- 「読んで描く」と画像タブは、モデルにプラグインの一覧を渡さない。モデルがDDLに名前を書けば描けるが、
  一覧を知らないので選ばれることはまず無い。
- Android・macOSで利用者が定義を導入する道と、installできるpackageの公開の一覧はまだ無い。

## 6. 要約（summary）の書き方

要約は、記述から描くときに下絵（Stage 1）のLLMが受け取る唯一の説明である。定義の本体や展開したDDLは渡らない。
下絵は、記述にプラグインの見出しの語かその言い換えが書かれたときだけ、名前だけの文としてプラグインを選ぶ。
季節・場所・似た物からの連想では選ばない。

- 何を、画面のどこに、どんな画材・色・形で描くかを書く。
- 個数を受けるなら、範囲と書かないときの数を書く（例:「星の数を書けばその数（1〜9個）、書かなければ3〜5個」）。
- 日本語と英語の両方を用意する（プラグインのファイルは`summary_ja`と`summary_en`、同梱packageは`summaries.ja`と`summaries.en`を持つ。書き出しファイルとmanifestは一つの文字列）。
- 長さはServerの既定で8192 bytesまで。§2の要約と、同梱の`Nature.leaves`の要約が手本になる。

## 7. 検査と、うまくいかないとき

Serverの管理者は、Webの「プラグインを追加」でファイルを選ぶだけで、§5.1の三つの検査がまとめて走る。
理由の説明は§7.2の表と同じである。追加はしないで検査だけをしたいときも、結果を見て「キャンセル」を押せばよい。
下の§7.1は、Serverを使わずにproductのcheckoutで定義だけを確かめる道である。

### 7.1 定義だけを検査する

productのcheckoutで、次のコマンドに定義を渡す。定義が正しければ`definition_identities`に正式名・versionとdigestが出る。
誤りがあれば、`Error:`の行に診断のcodeと、どの欄か（`path`）が出る。

```sh
scripts/rust-toolchain.sh run -q -p inku-ddl --example compile-score --locked --offline <<'JSON'
[{"source": "Sky.Stars.", "language": "en", "definitions": [ここに定義のJSON]}]
JSON
```

このコマンドの`outcome`は、lockを渡さないので`Stopped`（`macro_resolution_missing_lock`）になる。
描けるかまで見るには、出た`definition_identities`を`"macro_locks"`に入れて同じコマンドを走らせる。
この道具は別名をlockに入れられないので、ここでは正式名で呼ぶ。製品では別名でも呼べる。

### 7.2 よくある誤り

| 診断のcode | 意味と直し方 |
|---|---|
| `unknown_semantic_id` | `id`が歳時記に無い（例: 色の`pink`）。§3.8の一覧から選ぶ |
| `unknown_semantic_category` | `category`の綴りが違う |
| `unknown_semantic_field` | `emit`の欄の名前が§3.7に無い |
| `semantic_field_requires_matching_reference` | 欄と語の分類が合わない |
| `geometry_field_requires_exact_decimal` | 位置・寸法を`exact_decimal`以外で書いた |
| `invalid_count_parameter` | 個数の引数の範囲・候補が§3.4の決まりに合わない |
| `invalid_repeat_count` / `unbounded_repeat` | `repeat`の`count`が整数でない・`maximum`を超える、または`maximum`が0 |
| `undefined_parameter` / `undefined_local` | 宣言していない引数、範囲の外の`index`・`binding`を読んだ |
| `undefined_anchor` | `relation`の`from`・`to`が`binding`や`anchor`の名前と合わない |
| `invalid_alias` / `duplicate_alias` | 別名に使えない文字がある、見出しや他の別名と重なる |
| `invalid_semantic_version` | `version`が`1.0.0`の形でない |
| `component_cycle` | 部品が自分自身を呼んでいる |

- 書き出しファイルの定義に誤りがあると、その定義は読まれず、その語の文は`macro_resolution_missing_lock`で外れる。
  描いた結果には定義の誤りのcodeが出ないので、読み込む前に§7.1で検査する。
- 名前は解決したのに何も描かれないときは、宣言した引数を呼出しに書いたか（§3.4）、個数が範囲の中か、
  展開の上限（§8）を超えていないかを見る。DDLにその語の文しか無いと、外れた結果、描くものが無くなり作品が作られない。

## 8. 上限

| 上限 | 既定 | 決める所 |
|---|---|---|
| 書き出しファイルの定義の数 | 64 | Web・Android・macOSの読み込み |
| 下絵に渡す定義の数 | 64 | Server manifestの`prompt_limits.max_catalog_entries` |
| 要約の長さ | 8192 bytes | Server manifestの`prompt_limits.max_summary_bytes` |
| 展開の上限 | 呼出し64、深さ16、評価8192歩、呼出しあたり128節、全体128節 | Server manifestの`compiler.macro_expansion_limits` |
| 作品の図形の指示の数 | 64 | 管理UIの制限値`max_instructions`（[Serverの設定 §5.1](manual/ja/server-configuration.md#51-制限値)） |

- 節は、展開で実際に通った文の数である。`repeat`の中の文は繰り返しの回数だけ数える。
  §2の手本は星1つが`vary`と`emit`の2節なので、2026-10-26の確かめでは、1つの呼出しで64個までは描け、65個で描けなかった。
- 1つの呼出しが展開の上限を超えると、その呼出しが診断（`expansion_node_budget`）付きで外れ、ほかの文は描かれる。
  図形の指示の数の上限を超えると、超えた呼出しが`resource_omissions`に記録されて外れる。
  作品全体の節の上限を超えると、作品が作られないことがある（2026-10-26の確かめでは、20個の呼出しを7つ並べたDDLが描けなかった）。
- 定義の検査は、`repeat`の`maximum`を掛け合わせた最悪の数を数え、桁があふれる定義を受け付けない。
  個数の範囲は、上限の中で描ける数に収める。

## 9. 作れないもの

定義はデータだけである。任意のcode、I/O、filesystem・network・時計・環境変数への接触、再帰、
他の定義への依存、生のSVGやScore、Rendererへの命令、プラグイン専用の構文・parser・rendererは書けない。
新しい図形の種類や、coreの語の意味を変えることもできない。自由度を広げるには、別の作者裁定とschemaのversionが要る
（[SPEC §4.11](SPEC.ja.md#411-自由度の境界)）。

---

## 付録A. 実装の詳細

ここから先は、作者の手順には要らない実装の細部である。

### A.1 解決と展開

Compilerは、明示された修飾付き呼出しをsidecar lockに照らして解決する。Lockは、定義名、version、canonical digest、
別名、documentとcompilerのidentity、および展開を再現するために必要なsourceとgenerated provenanceを証明する。
展開は型付きparameterをbindし、証明済みのcomposition seedとcaller所有の有限上限を使う。
副作用がなく決定的であり、その出力は通常のtyped loweringへ合流する。

定義のcanonical identityは、検査を通った定義を正準のJSON bytesにし、domain分離したSHA-256を取ったものである。
別名が空なら正準bytesに入らない。`exact_decimal`は`0.240`と`0.24`を同じ値に正規化し、元の表記は定義に残る。

共有Rust compiler基盤は、MacroDefinition v1の値をparse、validate、identify、lock、bindし、決定的に展開できる。
これはServerとAndroidの通常の描画に組み込まれている。新しい作品では、hostが定義からcatalogを解決して
Stage 1へ名前と要約を渡し、compilerが展開し、使った定義をlockとして作品に保存する。
定義を供給するのは、共有coreに同梱したpackage、Serverのpipeline manifestの`definitions`・`macro_summaries`、
および読み込んだ書き出しファイルである（§5）。

### A.2 Emitの配置と形の細部

宣言済みflat Emitの`movement`が`line_up` / `scatter` / `tile`なら、verified Stage 1.5後の共有plan APIで通常DDLと同じobject-size / placement resolverへ届く。Emitのcount省略は8、明示正整数はu32::MAXまで保持し、必須parameter不足やbad型をdefaultにしない。Sizeはcanvas短辺基準でcount非依存、9shapeのnormal / 大小倍率・外観・angleを保つ。Optionalな`layout_direction`は既存`angle` categoryのSemanticRefを要求し、literal・宣言済みparameter / localから展開する。Shapeの`angle`とは別fieldで、line_upだけへ横 / 縦 / 物理45度の配置を届ける。省略横一列と明示horizontalのidentityを区別し、bare diagonalは元meaning・attestされたoptional composition seed・元occurrenceの専用roleで二軸から選ぶ。未対応action / rotated等の方向や未宣言caller方向は元実行単位で停止・省略し、同category複数parameterを名前で推測しない。物理aspectのtile、後続performance seedを要求するscatter recipeとgenerated owner / binding / provenanceも保持し、未宣言caller overlayやfan-outを作らない。Stop / Continueのfield / Emit / invocation省略単位を保ち、Ready planは個体配列・Score・描画成功ではない。新fieldなしの既存place / count1のScore成功経路は変わらず、方向を持つEmitをScore入口で無音にdropしない。Whole Step10、Step11とruntime接続を含む拡張は未完了である。

形状は既存のtriangle / square / polygon identityを使う。Optional Emit fieldの`proportion_aspect`はratio categoryのtall / wide、`shape_form`は閉じたcore shape_form categoryのregular、`sides`は5〜8のIntegerである。定義literal、宣言済みparameter、localを同じconsumerへ運ぶ。Callerは`regular` / `正形`、`sides 6` / `辺数6`等の独立したfactを宣言へbindし、同型の複数Integer parameterは名前で解かない。未宣言factと必要引数の欠落を捨てたり補ったりしない。通常DDLと同じnormal、正形、2:1の省略aspectを解決し、place / count1はactual Score、反復はexact制約を保持するplanへ届く。三角・四角のbbox中心とpolygonの外接円を使い、regularとaspectの矛盾や範囲外sidesは元Emitの停止・省略とする。一般numeric geometryのEmit fieldは追加しない。

### A.3 揺らぎ

SemanticRefのoptionalな`dimension`は`amplitude` / `frequency` / `quality`だけで、category=variationだけに許す。省略／Noneは旧category-only matchingとcanonical bytes / digestを保ち、指定した制約はdigestに含む。Parameter名からdimensionを推測しない。

Flat Emitのkeysは`fluctuation_amplitude` / `fluctuation_frequency` / `fluctuation_quality`で、expressionのcategoryは常に`variation`である。対応IDは順に`narrowly` / `broadly`、`loosely` / `tightly`、`swaying` / `undulating`（歳時記 v2。v1の`fine`・`large`・`slowly`・`quickly`・`trembling`・`blurring`は、歳時記 v2 の移行で書き換えた）。`ink_spread`は`bleeding`を受ける。Definition-local `use`も同じ分類を検査し、遅れて決まる実値は実行境界で検査する。通常DDLと同じ写像／不足slotのdefault／対応shapeはSPEC §13.6に従う。

三parameterを宣言したら三値が必須であり、一値だけを渡す呼出しはbinding errorである。一振幅parameterだけを宣言して対応Emit fieldへ届ければ、周波数と質はMedium / Perlinになる。三slot全省略はvariationなし。誤値をNoneへ変えず、未宣言callerはinvocation、malformed EmitはEmit単位の既存診断・省略を保つ。揺らぎの欄はScoreの`variation`へ届く（2026-10-26に`broadly`・`undulating`のEmitが`broad`・`wave`、周波数`medium`になるのを確かめた）。内部Variation JSONを書く方式ではない。

### A.4 正確な数値の宣言と配送

正確な十進数は `{"expr":"exact_decimal","value":"0.240"}` のように記す閉じた型で、通常DDLと同じExactDecimalを使う。定義の元表記を保持し、canonical identityでは `0.240` と `0.24` を同じ値に正規化する。既存 `number` / `Number(f64)` の意味・定義bytesは変えず、f64からexact値を復元しない。Literal、宣言parameter、local、component、有限choicesはexact型を保つ。一般算術やexact値のrange / transformへの暗黙変換は追加しない。

Parameterは `{"type":"exact_decimal","dimension":"radius"}` のように宣言する。Optional dimensionは `radius` / `diameter` / `length` / `side` / `width` / `height` / `chord` / `sagitta` / `position_x` / `position_y` に限る。Callerの明示dimensionと値を一意かつ完全に束縛し、parameter名から意味を推測しない。Dimension省略はdimensionを持たない単独数値にだけ一致する。 同じclauseに通常primitiveとexact parameterを持つMacroが混在する場合は、既存の数値owner未対応境界を維持し、曖昧な割当として診断する。別clauseには影響しない。幅と高さ、弦長と矢高、XとYの複合factは全成分が同一呼出しへ束縛された場合だけ移管し、元keywordとdecimalの出典を保持する。

Flat Emitの同名fieldへexact値を渡す。`width`+`height`、`chord`+`sagitta`、`position_x`+`position_y`は両方が必要で、欠落・型不一致は診断する。数値位置はnamed `place`と別authorityで、両者を黙って上書きしない。寸法・位置は通常DDLと同じresolverへ届き、サイズ重複は診断付きで小さい候補を採る。Definition literalのownerは生成元のEmitであり、架空の原文spanを作らない。Count1/placeのactual Scoreと反復planを扱い、反復個体の生成は後続materializationに残す。

### A.5 Geometryと個数の境界

Macroが出力するのは最終geometryではなく、型付きcore meaningである。Sizeには、未指定、明示的なqualitative指定、明示的なnumeric geometryという3つの異なるauthorityがある。明示的なnormalは未指定ではない。Positionも同様に、名前付きcenter、qualitative region、正確なnumeric coordinateを区別する。Isotropic sizeは自身のallocationまたは短辺を使うため、circleは円を保ち、ellipseのaspectも保たれる。

Geometryは`inku.geometry-resolution-policy.v1`として識別される唯一の`inku-ddl` ownerだけが解決する。Pluginは別のownerや10番目のprimitiveを追加できない。正確な個数は、O(count)のallocationまたはmaterializationより前にStep 11のpure ceilingを通過するまで、損失のないsymbolic intentとして残る。

### A.6 個数・変形・配置groupの実装

語に書いた個数を定義が受けないときは、語全体の外側の繰り返しになる。その写しは同じ場所に重ねず、呼出しの動作で一度だけ置く。動作なし・置く・散らす・引くは、描いた写しの大きさの区画に1枚ずつseedで置き、並べる・敷き詰めるはその動作どおりに置く（I-708）。同梱の`Nature.leaves` 2.1.0では、紅葉を除く六語が個数を受ける。

| 語 | 受ける個数 | 範囲 | 書かないとき | 置き方 |
|---|---|---|---|---|
| 若葉 | 葉の枚数 | 1〜12枚 | 4〜6枚 | 上半分を6列2段の12区画に分け、1枚ずつ別の区画へ少しずらして置く |
| 下草・枯草 | 株（3〜5本の葉の組）の数 | 1〜3株 | 1〜2株 | 下端の3つの根元の位置へ。株ごとの本数と葉の並びはseedで決まる |
| 青葉 | 枝の上の葉の枚数 | 1〜12枚 | 6〜8枚 | 枝の12の付け位置へ散らし、付け位置で上下と大きさが決まる |
| 落葉 | 葉の枚数 | 1〜16枚 | 8〜12枚 | 斜めの帯を下ほど細かい8段×左右の16区画に分け、区画の中の位置はseedで選ぶ。赤と灰は区画の市松 |
| 枯葉 | 葉の枚数 | 1〜8枚 | 2〜4枚 | 葉ごとに左右の隅をseedで選び、隅の中の8つの区画の自分の区画へ、seedでずらして置く |

どの語も、位置の順はどの個数でも偏らないように決めてある。紅葉は一枚の葉の裂片を描く語なので宣言を持たず、書いた個数は紅葉の葉の数として語全体の繰り返しのままである。記述に書かれた個数は、Stage 1の下絵が`10枚のNature.若葉。`の形でプラグインへ渡す。

`transform`は透明な`group`のEmit連続範囲を内側から外側へ保ち、Count1ではScore 0.5.0の`transform_groups`へ、反復では個体を作らないsymbolic planへ届く。有限の`scale_x` / `scale_y`と`translate_x` / `translate_y`は、bbox中心でのscale、同中心でのrotate、normalized canvas軸のtranslateをgeneral affineとして合成する。geometryと間隔だけを変え、stroke幅とgrain pitchは保つ。Score 0.4.0の回転だけのgroupは互換として残る。外部のTouching / Along / Cuttingは変形後の形・向き・明示指定を保ち、group全体の平行移動で成立を試みる。失敗時はrelationだけをerrorとして外し、groupは元の変形後配置で描く。Step11 materializationとStep13 runtime / UI / 保存cutoverは未完了である。Anchorだけを含むTransformは、解決済みのAnchor全体の外接矩形中心を使う。

通常DDLのprimitiveだけからなる既存named位置のdirect coordinated groupはScore 0.8.0の`placement_groups`へ届く。内部配置を省略すると`overlap`でmemberのbbox中心を揃え、「並べて置く」は既存wire値の`horizontal_source_order`、「重ねて置く」は`overlap`、`散らす`と`敷き詰める`は新しいwire値の`scatter`と`tile`となる。一つのnamed regionをperformance seedで一度だけ解決し、group全体を移す。memberのowner、count、seed、geometryは保つ。line-upの省略countは各member 1 でactual Scoreへ届く。scatter / tileは明示countを保ち、合計8までの残りを省略したmemberへ均等配分し、余りはsource順で先の省略memberへ割り当てる。省略memberは最低1個とし、明示数と最低数だけで8を超える場合も減らさない。全省略も同じ規則で、9種類なら各1個になる。全明示なら合計8へ補わない。line-up / placeは省略memberだけ1とする。配分後の全countが1のときだけactual Scoreへ届き、それ以外は個体化せずsymbolic planに残る。このdirect carrierはMacro authoring operatorや個体materializationを追加しない。

AnchorはScore 0.6.0の非描画targetとして、明示したnamed位置または数値座標をConnectedへ届ける。`place:center`は画面中央の一点で、描画する図形の`center`が使う中央の領域とは別である。包含Transformへ追従し、描画instructionの順序とseed、旧版保存互換を保つ。

Placeはcenter（通常DDLと同じ中央の領域）とtop / bottom / left_edge / right_edge / top_edge / bottom_edge / cornerを受け入れ、SPEC §18の領域を使う。Literal semantic_refと明示宣言した`{"type":"semantic_ref","category":"place"}` parameterは同じ経路を通る。隅はStage 2がattested meaning / composition seed / 元occurrenceから選び、隅内anchorはRendererが選ぶ。生成した座標を原文出典として挿入せず、未宣言callerの暗黙overlayや位置省略のdefaultを追加しない。

隣接bound Emitのconnected / touchingは、通常DDLと同じnamed-movableまたはnumeric-fixedの位置authorityを保って共有checked performerへ届ける。not_touchingとbetweenはnamed／noncenter位置も通常DDLと同じchecked performerへ届け、数値位置はfixedのauthorityを保つ。NotTouchingは既存Medium gapを使い、Betweenはcurrent直前のEmitとさらに一つ前のEmitのbbox中心を使う既存recipeを保つ。Betweenのfromは直前Emitであり、その一つ前を第二参照として両方のownerを保持する。隣接性はunbound Emitを含む元順序で判定し、省略されたfromまたはBetweenの二参照を他のsurvivorへ付け替えない。along / cuttingも隣接bound LineのEmitを同じperformerへ届ける。そのほかのrelationは未対応で、errorとして関係だけを外す。

旧Stop入力も受けるが、recoverableなrelation失敗で新Score全体を止めない。relationだけをerrorとして外し、元ownerと変形後配置を保って描く。OmitAndContinueは既存の最小省略単位を保ち、integrity不良は両mode停止とする。

Score 0.9の`placement_groups.members`はMacro bodyを順序付きdrawable範囲とAnchor所有として原子的に運ぶ。Macro authoring operatorや反復個体化を追加せず、group head countと内部Emit countを分ける。個数を受けないstandalone Macroに2以上の個数を書いた呼出しは、呼出しの動作で置く成員1つの配置groupになる。動作なし・置く・散らす・引くは`cells`（Score 0.19.0）、並べる・敷き詰めるは`horizontal_source_order`・`tile`である（I-708）。個数1と、位置・埋める・順序・関係を持つ呼出し、鏡写しの対象になる呼出しは、外側反復をsymbolic planへ保持する。

memberの`transform_group_indices`はsource-owned内部transformを配置前に保つ。先行drawableの後にAnchor-only Transform memberが続く場合も、validなmember範囲はそのAnchorを含む。unlistedの同範囲transformはouterとして後に実行する。

`CompositionPlanResult.standalone_macro_repetitions`は既存body位置、range、Anchor、内部transform、source head repeat countをsymbolicに保持し、outer placementやactual Score instanceを作らない。ここに残るのは外側反復を保つ呼出しだけで、ほかの個数付きの呼出しは配置groupの成員になる（I-708）。

### A.7 同梱package・旧形式・互換

同梱の`Nature.leaves`（package 2.1.0）は実際に導入されたpackageで、`Nature.YoungLeaves`（別名`Nature.若葉`）など七語を持つ。定義の実体は共有coreが持つMacroDefinition v1である。Serverの`server/plugins/nature-leaves.inku-plugin.md`は、有効・無効の単位と、歳時記に出す語・note・previewの出典として使われ、その展開の散文は定義として解釈されない。同じ名前空間の任意の`.inku-plugin.md`が暗黙に定義へ翻訳されることもない。`Nature.雨`や`Bamboo`はSPECの説明用の名前で、official registryのentryではない。v1.70のhard-coded Nature展開は、現在のauthoring formatではない。

`plugin_storage["canvas-aspect"]`、`canvas_aspect` request alias、system/user plugin directoryは、退役作業が未完了の間のcompatibility surfaceである。Serverの設定画面は文書を作成・編集せず（2026-09-28）、定義を持たない文書を「描画には使われない」と示す。Serverの文書単位の有効・無効と、Androidの`Nature.leaves`の切り替えは、同梱packageを新しい作品で使うかどうかを決める。保存済みの作品はlockした定義を使うので、切り替えの影響を受けない。

Compatibility importerは`legacy_plugin_format`を報告し、macroごとに`Imported`または`Omitted` outcomeを返す。既存作品は、保存済みScoreまたは展開済みartifactを優先する。そのようなartifactを持たないomitted macroを、黙って部分描画したり、旧expanderへ永続的にfallbackしたり、別の図形へ変えたりしてはならない。
