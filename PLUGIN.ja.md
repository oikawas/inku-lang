# inku 語彙プラグイン作成ガイド

プラグインは実行コードを持たない語彙マクロです。定義は通常の DDL の形へ展開されます。新しく作るファイルは `inku.plugin-package.v2` だけです。旧 `v1` ファイルを読み込んだり自動変換したりはしません。境界は [SPEC §4](SPEC.ja.md) を参照してください。

## 1. 作る手順

1. 物か情景の語の定義を `inku.macro-definition.v2` で書きます（§2、§3）。
2. 定義、日英の note、任意の例文と絵を `inku.plugin-package.v2` にまとめます（§5.1）。
3. 管理者が Web の設定から JSON または PNG を含む zip を選ぶと、Server が形、定義、例文の描画を検査します。通ったファイルだけ追加できます。
4. DDL では見える名を括弧で呼びます。例：`｛星｝。`、`{stars}.`。移行期間中は旧 `Sky.星` も読めます。

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

物の語の使用例は、位置と数を含めて `左上に3個の｛星｝。` のように書くことを勧めます。外側の個数は物全体を繰り返します。

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

### 3.3 引数と本体

`parameters` は型の表です。`semantic_ref`（分類と任意の dimension）、`exact_decimal`（任意の dimension）、`integer`、`number`、`boolean`、`list` を使います。呼出しに書かれない必須の引数は補いません。情景の語に宣言されていない修飾を添えたときは、語全体ではなく修飾だけを診断付きで外します。物の語は位置・寸法・傾き・数を構図と法則で扱い、定義の形は替えません。配色が変えるのは定義が色を受けるときだけです。

情景だけが最上位の整数引数一つに `{"type":"integer","receives":"count","minimum":1,"maximum":9,"omitted":[3,4,5],"counter":"general"}` を書けます。省略時は候補から seed で決まり、範囲外は `macro_binding_count_out_of_range` でその呼出しだけ外れます。宣言しなければ外側の反復です。

式は `expr` で種類を示し、`semantic_ref`、位置・寸法の `exact_decimal`、`integer`、`number`、`boolean`、`list`、`cycle`、`parameter`、`local` を使います。算術はありません。本体は `emit`、`repeat`、`vary`、`use`、`transform`、`anchor`、`relation` 等の有限な文です。詳細な値と意味語は [DDL の手引き](manual/ja/ddl-reference.md) と [共有 core](core/crates/inku-ddl/src/macro_definition.rs) を参照してください。新しい図形や実行 hook は追加できません。

## 4. DDL での呼び方

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
