# 共通保存契約

このディレクトリはServer、Android、将来のiOS adapterが共有する論理SQLite保存境界を定義する。全hostが同じDBファイルを開くという意味ではない。

正本の優先順は、製品の意味を定義する`SPEC.ja.md`、論理項目・encoding・host mappingを定義する`contract.json`、制約を実行できる`reference/logical-projection-v2.sql`、小さい言語非依存の`fixtures/`、各hostの物理adapterである。v1のreference SQLは旧入力の歴史的定義として残す。

`fixtures/history-minimal.json`は現行v2、`fixtures/history-legacy-v1.json`は旧二本文JSONの入力例であり、新形式の出力ではない。

## 論理保存と物理保存

論理recordは`history`、`lineage_nodes`、`lineage_edges`。Serverの`history`に対しAndroidは`history_items`、`at`に対し`created_at`、`input`に対し`original_input`、`ddl`に対し`normalized_ddl`、`score`に対し`score_json`、`svg`に対し`display_svg`を使う。物理名の一致でなく、意味・NULL区別・encoding・制約が一致することを要求する。

Androidの現行物理正本は生成済み[Room schema 14](../android/app/schemas/app.inku.mobile.data.db.InkuDatabase/14.json)。`history_items.normalized_ddl`と`ddl_source_origin`はともにNULL可のTEXTであり、旧`expanded_ddl`列を持たない。共通checkerはこのschemaとServerの現行schemaを契約v2へ照合する。

`required_common`は両hostが保存または決定的に公開する事実、`optional_common`は共通の意味を予約しproducerのないhostによる省略を許す項目。認証・管理・端末固有のprovider/model/cacheはhost拡張である。

Androidの`render_seed`、`composition_seed`、`render_wild`は専用列が正本。`render_metadata_json`の一致値はrender identity用の整合性echoであり第二の書込authorityではない。専用列のない色map等は既存JSON pathで対応付ける。

## 契約v2の指示書

保存・表示・編集・再描画の本文は`ddl`だけ。旧JSONの入力境界と明示的なDB移行では、本文のある`ddl`を優先し、本文がない場合だけ旧`expanded_ddl`の本文を移す。両方に本文がなければ元の`ddl`のNULL・空文字・空白を保持する。採用した文字列をtrim、Unicode正規化、改行変換、compile、再描画しない。

本文なしの判定に使う空白は、U+0009–000D、0020、0085、00A0、1680、2000–200A、2028、2029、202F、205F、3000の固定集合だけ。`contract.json`のcodepoint一覧と`fixtures/ddl-selection.json`がServer・Android・旧JSONで共有する境界を定める。U+001CやU+200Bは本文あり。

`ddl_source_origin`はoptional commonで、NULLまたは`legacy_expanded`。旧expanded本文を移した事実だけを記録し、第二の本文やauthoring authorityではない。NULLから作者・工程を推測しない。export/importで由来を保持し、旧作品のauthorityは`legacy_unknown`のまま。過去の親子input DDL比較では`legacy_expanded`を入力不明として扱う。通常のfork/replayは統合`ddl`を使用し、新作品は現在のpipelineで確定したdocumentとauthorityを保存する。

## NULLとidentity

- NULLの`source_text`は独立したsource記録より古い作品を意味する。readerは`input`を返せるが保存NULLを書き換えない。
- NULLの`sketch_state`は`off`、NULLの`compose_fallback`は記録済みの`none`と異なる。
- `render_hash`は非unique。同じ描画を2回保存すれば2作品である。history主キー衝突は置換せず拒否する。
- 保存移行は`rh3`、`dh1`、Score、canonical SVGを再計算しない。

## 現行runtimeと確認の順序

ServerはSQLAlchemy/SQLite、AndroidはRoom/SQLiteの物理schemaを所有する。Serverの`db.init_db()`はcomposition façadeであり、新規DBを現行schemaで作り、旧二本文DBは明示的な手動DDL移行が必要として通常起動を拒否する。移行後の起動でもregistry/checksum、必要列、廃止列の不存在、FTSを確認する。凍結した旧schema/adapterは旧backupの隔離復元に使い、新規DBの定義で旧schemaを代用しない。

Serverの`db.add_item()`とAndroidの`InkuRepository.saveResult()`はhistory・lineage node・任意edgeを1 transactionで保存する。thumbnailはcanonical保存後の派生物。両hostはhistory/nodeの一対一、childごとの親1つ、self-edge拒否、非unique render hash、主キー衝突拒否を保存境界で強制する。Androidのv1–9だけの一度きりresetと、v10以降の非破壊移行を区別する。

## Serverの手動移行

新規DBはregistry v4 `single_history_ddl`、既存v3からの移行はv3行を保持してv4行を追加する。`server/scripts/migrate_history_ddl.py`は通常APIを起動せず、明示したcanonicalな既存DBだけを扱う。SQLite 3.35以降の`DROP COLUMN`が必要。既知の元schema fingerprintとregistry/checksumを照合し、未知・部分状態を拒否する。

Serverの`server/`から、まず読み取り専用で確認する。SHAには選択したproduct commitの40桁を指定する。

```sh
uv run python scripts/migrate_history_ddl.py \
  --database /absolute/path/inku.db --source-commit '<exact-product-sha>' --dry-run
```

本番でのapplyは書き込みをロックし、処理中の保存を終え、APIを停止した後に行う。確認したfingerprintと、新規のprivate report pathを指定する。

```sh
uv run python scripts/migrate_history_ddl.py \
  --database /absolute/path/inku.db --source-commit '<exact-product-sha>' \
  --expect-fingerprint '<verified-source-fingerprint>' \
  --report /absolute/private/path/migration-report.json --apply
```

SQLite Backup APIでWALを含む写しを作り、DB隣の`migration-backups/`へowner-onlyで保持する。writer lock取得後、schema・registry・全persistent値がその写しと一致することを確認する。不一致は変更前に拒否する。本文選択・由来列の追加・旧列削除・全保存値とrowid/link/FTS/integrityの照合・registry更新は一つのtransactionで行う。reportは準備済み・commit中・成功またはrollbackの状態を記録する。移行済みDBへの二度目のapplyは変更せず終了する。

旧v1/v2や受入済みpre-registry backupは、`--database`に原本、`--restore-copy`に存在しないcanonicalな保存先を指定して`--apply`する。凍結した旧schema/coordinatorで新コピーをv3へ復元し、その検証済みpostimageを統合する。原本を変更しない。登録済み旧DBも既知の物理schemaだけを受け入れ、未登録の形を旧版と推定しない。復元とDDL統合は別phaseであり、reportに双方の識別を残す。

コピー・backup・失敗reportを自動削除しない。不明な終了状態から自動再送・再起動しない。commit前の失敗はrollbackを確認し、commit後の切り戻しは新DBを保全して移行前backupと旧コードを組で復元する。新版を起動する前にregistryと物理schemaと成功reportの一致を確認する。

## 旧Server schema fingerprint

`sha256-canonical-sqlite-master-v1`は行でなくschema objectをfingerprintする。`sqlite_master`のtable/index/trigger/viewを読み、`sqlite_`と派生`history_fts` prefixを除き、identifier/literalを変えずSQLの空白を折り畳み、type/name/table順のcanonical UTF-8 JSONをSHA-256でhashする。FTSの存在は別に確認する。明示的に受入済みのfingerprintだけ移行を許し、registryがないだけでは対応版と見なさない。

本番fingerprintの実行証拠はprivate記録に置き、公開ファイルにhost path、行本文、credential、配備構成を含めない。

## 検証

`server/`から実行する。checkerはsourceとexport済みschemaだけを読み、開発・本番DBを開かない。宣言したhost mappingと実際のschemaが違う状態を成功としない。

```sh
uv run python scripts/check_portable_persistence_contract.py
uv run pytest tests/test_portable_persistence_contract.py -q
```
