# 作品パック v1

`.inkupack` は UTF-8、LF 区切りの JSON Lines。最初の行に `format: "inku.workpack"`、`format_version: 1`、`persistence_contract_version: 2`、`exported_at`（Unix ミリ秒）、`producer`（host、app_version、build、schema_version）、`counts` を置く。続く行は `kind` を持ち、history、lineage_node、lineage_edge、annotation、colophon の順に置く。counts はこれらの種類ごとの件数で、食い違えば不完全なファイルとして断る。同じ版の未知の欄と kind は無視し、より大きな format_version は断る。

history、lineage_node、lineage_edge の欄は [contract.json](contract.json) の対応する records の `required_common` と `optional_common` の論理名を使う。required は null も明示し、host_only は運ばない。保存済み SVG、JSON 文字列、ハッシュは書き換えない。

## encoding と JSON の型

| encoding | JSON の型 |
| --- | --- |
| text、utf8_text、utf8_svg | 文字列 |
| unix_epoch_milliseconds、integer_milliseconds | 整数 |
| unsigned_decimal_text | 十進の文字列 |
| canonical_json_object | JSON オブジェクトを表す文字列 |
| boolean_0_1 | 整数 0 または 1 |
| finite_number | 有限の数 |
| null_or_legacy_expanded | null または文字列 `legacy_expanded` |
| rh3_or_legacy_text、dh1_or_legacy_text | 文字列 |

新しい encoding はこの表を更新してから使う。null を許す欄は null も書ける。Server の文字列の 0/1 は整数に変える。

annotation は `history_id`、`note`（null または前後の空白を除く 240 字以内の文字列）、`for_revision`（0/1）。旧 `for_share` は運ばない。colophon は `id`、`target_node_id`、`branch_snapshot`（JSON 文字列）、`model`、`at`、`language`（ja/en）、`body`、`warnings_json`、`fact_sheet_json`。Swift は任意で `generated_body`、`adopted_body`、`signature` を追加できる。body は採用文があればそれ、無ければ生成文。読めない host は annotation と colophon を飛ばせる。

同じ作品または節点の ID が既存なら作品を飛ばし、既存の印とコメントを保持する。作品のない節点は入れない。両端が存在し子に親がない辺だけを入れ、起点は取り込み先で決め直す。全行の検証後、取り込みは一つの transaction で行う。暫定上限はファイル 256 MiB、行 64 MiB。書き出しにはごみ箱の作品を含めない。取り込みは `trashed` を保存する。接続情報、設定、実行記録、サムネイルは含めない。

共通 fixture は [workpack-minimal.inkupack](fixtures/workpack-minimal.inkupack)。
