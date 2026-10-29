# inku 語彙プラグイン作成ガイド

プラグインは実行コードを持たない語彙マクロです。定義は通常の DDL の形へ展開されます。新しく作るファイルは `inku.plugin-package.v2` だけです。旧 `v1` ファイルを読み込んだり自動変換したりはしません。境界は [SPEC §4](SPEC.ja.md) を参照してください。

## 1. 作る手順

1. 物か情景の語の定義を `inku.macro-definition.v2` で書きます（§2、§3）。
2. 定義、日英の note、任意の例文と絵を `inku.plugin-package.v2` にまとめます（§5.1）。
3. 管理者が Web の設定から JSON または PNG を含む zip を選ぶと、Server が形、定義、例文の描画を検査します。通ったファイルだけ追加できます。
4. DDL では見える名を括弧で呼びます。例：`｛星｝。`、`{stars}.`。旧形式では識別子による `Sky.Stars` も読めます。

## 2. 物の語の手本

この定義は一個の黄色い星を描きます。`id` は保存と lock の識別子で、`names` が DDL に書く名です。物の語は縦横比 `aspect` を持ち、受ける欄を明示し、個数を受ける `receives: count` は宣言しません。

```json
{
  "schema": "inku.macro-definition.v2",
  "namespace": "Sky",
  "id": "Stars",
  "names": {"ja": ["星"], "en": ["stars"]},
  "kind": "object",
  "aspect": "1:1",
  "counter": "general",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": [{
    "op": "emit",
    "fields": {
      "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
      "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
      "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
      "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
      "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
      "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
    }
  }]
}
```

物の語の使用例は、位置と数を含めて `中心に、｛星｝を3個置く。` のように書くことを勧めます。外側の個数は物全体を繰り返します。

## 3. 定義の決まり

### 3.1 最上位の欄と情景の語の手本

`schema`、`namespace`、`id`、`names`、`kind`、`version`、`parameters`、`components`、`body` を書きます。`kind` は `object` または `scene`。物には `aspect`（1〜16 の整数二つを `:` でつなぐ）と任意の `counter`（`flat`・`long`・`general`）を使えます。情景には両方書けません。情景の語は差し込む形として描きます。

```json
{
  "schema": "inku.macro-definition.v2",
  "namespace": "Sky",
  "id": "StarField",
  "names": {"ja": ["星原"], "en": ["star field"]},
  "kind": "scene",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": [{"op": "emit", "fields": {
    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
    "position_x": {"expr": "exact_decimal", "value": "0.500"},
    "position_y": {"expr": "exact_decimal", "value": "0.250"},
    "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
    "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
    "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
    "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
  }}]
}
```

### 3.2 名と識別子

`namespace` と `id` は英字で始まる英数字、`_`、`-` だけの識別子です。`names.ja/en` は見える名の配列で、最初が主の名です。空の名、制御文字、括弧、`.`、名前空間を含む名は使えません。照合は NFKC・小文字化・連続空白を一つにする正規化で行います。基本語と同じ名は名乗れません。一つの目録で同じ名を二つの語が持つと曖昧になります。別のプラグインが同じ名を持つファイルは追加できません。

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

情景の語が受けない位置・大きさ・傾きなどを呼出しに書いた場合、その欄だけを診断付きで外し、定義の本体は描く。
物の語では位置・寸法・傾き・数・動き・関係は外側の箱に働く。色などの見た目の語は定義が引数で受けるときだけ中身に働く。

引数は名前から型への表である。型は次に限られる。

| `type` | 他の欄 | 呼出しで結ばれるもの |
|---|---|---|
| `semantic_ref` | `category`、任意の`dimension` | 呼出しに書いたその分類の語。例: 色の引数は`赤い｛色星｝。`の「赤い」を受ける |
| `exact_decimal` | 任意の`dimension` | 呼出しに書いた数。`dimension`は`radius`・`diameter`・`length`・`side`・`width`・`height`・`chord`・`sagitta`・`position_x`・`position_y` |
| `integer` | — | 呼出しに書いた数 |
| `integer`（個数） | `receives: "count"`, `minimum`, `maximum`, `omitted`, 任意の`counter` | 語に書いた個数（下の説明） |
| `number` | — | 呼出しに書いた数 |
| `boolean` | — | — |
| `list` | `length`, `items` | — |

- 宣言した引数は、個数の引数を除いてすべて必須である。呼出しに書かれないと、その呼出しは描かれない。
  黙って既定値を入れることはない。
- 同じ分類の引数を二つ宣言しても、引数の名前からどちらへ結ぶかを推測しない。分類ごとに一つにする。
- 物の語には色の引数を宣言しなくても色の語を添えられ、定義の主の色がその色に替わる。主の色は、本体の emit に literal の `color` semantic_ref で書いた色を数え、最も多い色とする。使用した部品・repeat・vary・transform の中も数え、同数なら本体の順で先の色とする。引数・cycle・vary で色を決める emit は数えない。替わるのは主の色の痕だけで、差し色は残る。主の色が無ければ、結ばれない色の語は診断付きで外れる。
- 色の引数を宣言した定義は従来どおり引数に結ぶ。色以外の宣言していない見た目の語、または情景の語の宣言していない色は、その語だけが診断付きで外れ、定義の値を上書きしない。
- 揺らぎの引数は`{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`のように、
  `dimension`（`amplitude`・`frequency`・`quality`）で幅・速さ・質を分けられる。

**情景の語の個数を受ける引数。** 語に書いた個数（`5個の｛星原｝。`、`5 {star field}.`）は、受けると宣言しない限り、
語全体を外から繰り返す。中の個数として受けるには、整数の引数に`receives: "count"`と範囲を宣言し、
本体の`repeat`の`count`でその引数を読む。

```json
"star_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 9, "omitted": [3, 4, 5], "counter": "general"}
```

- 情景の語の最上位の引数に一つだけ宣言できる。物の語にも部品の引数にも置けない。
- `minimum`は1以上で`maximum`以下、`omitted`は空でなく、重複せず、範囲の中の整数だけを並べる。
- `repeat`の`maximum`は引数の`maximum`以上にする。
- 個数が書かれなければ、`omitted`の候補から呼出しの種で一つを決まった仕方で選ぶ。
- 範囲の外の個数は`macro_binding_count_out_of_range`の診断を出してその語だけを外し、ほかは描く。丸めない。
- `counter`（`flat`は枚、`long`は本、`general`は個）は、下絵が日本語のDDLに個数を書くときの助数詞だけを決める。

### 3.5 位置と大きさの決まり

- 情景の語の位置は画面に対する割合、物の語の中身の位置は見えない箱に対する割合である。どちらも
  `(0.0, 0.0)`が左上、`(1.0, 1.0)`が右下、`(0.5, 0.5)`が中央。xは幅、yは高さに対する割合になる。
  物の語の名の位置（`place`）も箱の中の領域を指す。
- 情景の語の寸法は画面の短い辺、物の語の中身の寸法は箱の短い辺に対する割合である。
  たとえば`radius` 0.24は、その短い辺が500pxなら半径120px。紙や箱が正方形でなくても円は円のまま。
  中心と半径が端を超えると外へはみ出す。
- `transform`の`translate_x`・`translate_y`は情景では画面の単位、物の語の中身では箱の単位である。
  箱を大きくしても線の太さと質感の細かさは変えない。
- 呼出しの物全体は`aspect`の見えない四角として通常の四角と同じ位置・数・動き・大きさ・傾き・関係を解く。
  普通の大きさと一辺の指定は箱の長い辺に合わせ、幅と高さを両方指定したときはその値を使う。
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
| `transform` | `transform`, `body` | `body`の図形をまとめて動かす。`transform`は`translate_x`・`translate_y`・`scale_x`・`scale_y`・`rotate_degrees`のうち一つ以上（数）。拡大縮小と回転はまとまりの外接矩形の中心で行い、移動は§3.5の単位で行う |
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
| `place` | `place`の語 | `position_x`と`position_y`の組とどちらか一方。`center`・`top`・`bottom`・`left_edge`・`right_edge`・`top_edge`・`bottom_edge`・`corner`。物の語の中身では箱の領域 |
| `position_x`, `position_y` | `exact_decimal` | 二つ組で書く。情景では画面、物の語の中身では箱に対する割合 |
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

## 4. DDL での呼び方

Web の歳時記と設定には日英の名・種類・note・例と絵が出る。編集欄は括弧から名を補完し、共有 core が調べた語の印と理由、hover の見本を出す。note は下絵への提示と語の説明に使う。

主の名を波括弧に入れます。日本語 `｛星｝。`、英語 `{stars}.`。修飾は呼出しに添えます。物は構図・法則では縦横比の四角として置き場と数を扱い、形自体は保ちます。情景は差し込みの形として保ちます。保存済みの作品は定義と lock の写しを持ち、導入済みのファイルを後で替えても再演できます。

## 5. 読み込ませる道

### 5.1 Web からプラグインのファイルを追加する

§2 の定義を一語のファイルにした例です。この JSON を `package.json` として保存し、Web の設定から選べます。絵を指定する場合は、最上位に `package.json` を置いた zip に PNG を入れ、語に `"preview":"previews/stars.png"` を書きます。

```json
{
  "schema": "inku.plugin-package.v2",
  "namespace": "Sky",
  "name": "night",
  "version": "1.0.0",
  "description_ja": "夜空の語。",
  "description_en": "Words of the night sky.",
  "words": [{
    "definition": {
      "schema": "inku.macro-definition.v2",
      "namespace": "Sky",
      "id": "Stars",
      "names": {"ja": ["星"], "en": ["stars"]},
      "kind": "object",
      "aspect": "1:1",
      "counter": "general",
      "version": "1.0.0",
      "parameters": {},
      "components": {},
      "body": [{"op": "emit", "fields": {
        "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
        "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
        "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
        "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
        "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
        "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
      }}]
    },
    "note_ja": "夜空に黄色い星を描く。",
    "note_en": "Draws a yellow star in the night sky.",
    "example_ja": "｛星｝を置く。",
    "example_en": "Place {stars}."
  }]
}
```

ファイルの欄は `schema`、`namespace`、`name`、`version`、任意の `description_ja/en`、`authors`、`license`、`words`。語の欄は `definition`、`note_ja/en`、`example_ja/en`、`preview` だけです。`note` は少なくとも一言語に必要で、100 字まで。無い言語にはもう一方を使います。例文を省くと `｛主の名｝。`／`{primary name}.` を使います。明示した例文には括弧の主の名を入れてください。絵は zip 内の PNG です。

検査はファイルの形、共有 core の定義、日英の例文の描画の三段階です。すべて通るまで導入できません。管理者は追加・置換・無効化・削除・絵の差し替え・zip 書き出しができます。導入した語は新しい作品の目録と歳時記に入り、note が下絵の提示にも使われます。`Nature.leaves` は core 同梱の v2 ファイルで、設定から無効化できますが削除と絵の差し替えはできません。API は `POST /api/plugins/packages/validate`、`POST /api/plugins/packages`、`GET /api/plugins/{id}/export` などです。

### 5.2 DDL の書き出しファイル

作品の `GET /api/pipeline/history/{id}/ddl-export` は `inku.ddl-export.v2` を返します。`plugins` は保存された lock が選んだ定義を `{definition,note}` で運び、DDL の文字列に定義名があるかは問いません。読み込むと、その新しい作品だけで使い、Server へ導入はしません。同名の導入済み定義より優先され、差があれば診断が出ます。v1 の書き出しは読み込めないため、v2 で書き出し直してください。

### 5.3 Server の manifest

管理者は `pipeline.definitions` に定義、同じ順の `pipeline.macro_summaries` に note 相当の短い文を置けます。長さが違うと `macro_catalog_summary_mismatch` で止まります。

### 5.4 同梱

七つの葉は `core/crates/inku-ddl/assets/nature-leaves-v2/` に JSON と PNG を置きます。共有 core の `plugin_package` 入口 `bundled_nature` が Server へ内容を渡します。macOS と Android の既存の画面・資源は次の改修で新しい名へ追従します。

## 6. note の書き方

何の物かを一文で、日英それぞれ 100 字までに書きます。下絵（Stage 1）に見せる一行と歳時記の説明の両方になります。位置・画材・色など、描く物の事実を書き、季節や似た物からの連想に頼らないでください。

## 7. 検査と問題 code

### 7.1 三段階の検査

形の問題があっても、読める定義と例文の検査は続け、場所と code をまとめて返します。定義に問題があればその例文は描きません。問題の詳細は Web の検査画面に日英で出ます。

### 7.2 定義の問題

`invalid_canonical_definition`、`unknown_json_field`、`duplicate_qualified_name`、`name_taken`、`name_is_core_word`、`invalid_plugin_kind`、`invalid_plugin_aspect`、`invalid_plugin_counter`、`scene_has_aspect`、`scene_has_counter`、`object_count_parameter`、`unknown_semantic_id`、`unknown_semantic_category`、`unknown_semantic_field`、`semantic_field_requires_matching_reference`、`geometry_field_requires_exact_decimal`、`invalid_count_parameter`、`invalid_repeat_count`、`unbounded_repeat`、`undefined_parameter`、`undefined_local`、`undefined_anchor`、`component_cycle` が出ます。場所と定義の欄を照らしてください。

その他の定義 code: `anchor_requires_one_explicit_position`, `argument_type_mismatch`, `count_parameter_in_component`, `duplicate_alias`, `duplicate_anchor_or_binding`, `duplicate_count_parameter`, `duplicate_local_binding`, `duplicate_plugin_name`, `empty_cycle`, `empty_transform`, `empty_vary`, `external_component_reference`, `heterogeneous_cycle`, `invalid_alias`, `invalid_anchor_or_binding_id`, `invalid_component_id`, `invalid_cycle_index`, `invalid_emit_count_type`, `invalid_endpoint_target`, `invalid_local_binding_id`, `invalid_parameter_id`, `invalid_plugin_id`, `invalid_plugin_name`, `invalid_semantic_dimension`, `invalid_vary_domain`, `invalid_vary_range`, `invalid_vary_source`, `missing_argument`, `non_finite_number`, `path_position_requires_connected`, `path_position_requires_number`, `resource_bound_overflow`, `transform_requires_number`, `undefined_component`, `unknown_anchor_field`, `unknown_argument`, `unknown_schema`, `vary_choice_type_mismatch`.

### 7.3 ファイル・例文・絵の問題

ファイル: `invalid_json`、`package_too_large`、`not_an_object`、`unknown_field`、`wrong_schema`、`rewrite_as_v2`、`definition_requires_v2`、`invalid_identifier`、`invalid_semantic_version`、`not_a_string`、`not_a_list_of_strings`、`text_too_long`、`no_words`、`too_many_words`、`namespace_differs_from_package`、`id_differs_from_directory`、`invalid_package_id`、`bundled_package_id`、`no_note`、`example_without_name`。`rewrite_as_v2` は v1 ファイルを v2 で書き直して入れ直す意味です。

例文: `macro_binding_count_out_of_range`、`macro_resolution_missing_lock`、`compiler_diagnostics`、`example_draws_nothing`、`example_not_drawn`。

絵と zip: `not_a_png`、`image_too_large`、`preview_needs_zip`、`preview_not_found`、`invalid_preview_path`、`invalid_zip`、`not_base64`、`archive_too_large`、`too_many_archive_members`、`archive_without_package_json`、`not_utf8`。`not_base64` は Server の受け取り時に出ます。

## 8. 上限

ファイル 1,000,000 bytes、語 64、`description_*` 2000 字、`note_*` 100 字、`example_*` 500 字、`license` 200 字。PNG は一枚 2 MiB・4096×4096 画素、zip は 16 MiB・256 ファイル、PNG 合計 64 MiB までです。プレビューは 216×92 とその二倍の枠に収めます。

## 9. 作れないもの

プラグインは core の語や図形の意味を変更できず、実行 hook・任意のコード・新しい構文を持てません。v1 パッケージは読み込めません。
