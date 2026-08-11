# inku-cli AI自律運転・テスト用リファレンス

本ドキュメントは、AIエージェントが `inku-server` をコマンドラインから操作し、自律的に作品の生成、評価、および「系譜（Lineage）」を駆使した「推敲（Refine/Vary）」の品質向上プロセスをテスト・実行するためのガイドラインです。

対象はinku v2.13.5（Web Build 890）です。旗の全一覧は`inku-cli リファレンス`が持ちます。

---

## AI自律・品質向上ワークフロー（テスト手順）

AIエージェントが作品を漸近的に改善していくための標準的な実行手順です。

### ステップ 1: セッションの確立と接続確認
API接続が正常に行えるか、現在ログインしているユーザーの権限グループを確認します。

```sh
uv run inku-cli me
```
* **期待される出力 (JSON)**: `permission_groups` が `["admins"]` や `["users"]` のような文字列の配列であるオブジェクト。
* **AIの判断ロジック**: 応答に `id` と `username` が含まれていれば接続成功。

### ステップ 2: 新規作品の作成（起点 / Root）
指示文（詞書）をもとに最初の作品を生成し、サーバーの履歴に保存します。

```sh
uv run inku-cli paint "白い余白に、黒い太筆の波線を一本引く。" -o ./test_output --png --save-history
```
* **期待される出力 (JSON)**:
  生成された作品のメタデータを含む JSON オブジェクト。
  * `history_id`: `"d5989732-9f3a-4dd2-82df-c49c50761119"` (例)
  * `render_hash`: 作品固有のレンダリングハッシュ
  * `paths.json`, `paths.svg`, `paths.png`: 各種出力ファイルのローカルパス
* **AIの判断ロジック**: 出力から `"history_id"` を抽出して `PARENT_ID` として変数に保持します。

### ステップ 3: 派生作品の自動生成（推敲 / Refine）
作成した作品を親ノードとし、特定の要素（タッチ・構図・解釈・色）を変動させた推敲作品を生成して系譜に繋げます。

```sh
# 親ID: PARENT_ID (例: d5989732-9f3a-4dd2-82df-c49c50761119) に対して構図のバリエーションを生成
uv run inku-cli refine perform PARENT_ID --kind layout -o ./test_output --png
```
* **パラメータ `--kind` の選択基準**:
  * `touch`: 画の質感（筆圧や掠れ）のみを変更したいとき。新しい `render_seed` だけを置き、他のseedは親から引き継ぐ（LLM呼び出しなし / 高速）
  * `layout`: 線の位置や大きさを再構築したいとき。新しい `composition_seed` を置き、Stage 2が再配置する
  * `reading`: 記述の解釈からやり直したいとき。新しい `interpretation_seed` を置き、**Stage 1** が読み直す
  * `color`: 他の色カタログを適用したいとき（LLM呼び出しなし）
* **期待される出力**: 新しい派生作品の JSON メタデータ。

`--kind` はサーバーへ `derivation_kind` として記録されます（順に `touch_change` / `layout_change` / `reinterpretation` / `catalog_change`）。系譜のedgeを検証するときはこの値を読みます。

### ステップ 4: 作品系譜の探索と状態確認
追加した派生作品が、親作品のツリーに対して正しくエッジ（派生タイプ）で連結されているかをコンソール上で探索します。

```sh
uv run inku-cli lineage show PARENT_ID
```
* **期待される出力 (ツリー表示の例)**:
  ```text
  Work lineage:
  - (Root) dfced380 [Displayed] : 白い余白に、黒い太筆の波線を一本引く。
    - (layout_variation) b91ae625  : 白い余白に、黒い太筆の波線を一本引く。
  ```
* **AIの判断ロジック**: 親ノード（`dfced380`）の配下に、指定した `derivation_kind`（例: `layout_variation`）のエッジで子ノード（`b91ae625`）がネストされていることをパースし、系譜が正しく成長していることを検証します。

### ステップ 5: 視覚的評価（review）による選定
生成された派生作品の画像（PNG）を Vision LLM に送信し、画の出来栄えや美的整合性を評価させます。

```sh
uv run inku-cli review evaluate ./test_output/refine-layout-xxxx.png --model nvidia/neva-22b
```
* **期待される出力 (JSON)**:
  ```json
  {
    "image": "refine-layout-xxxx.png",
    "model": "nvidia/neva-22b",
    "evaluation": "The drawing exhibits high color resonance... (評価文)"
  }
  ```
* **AIの判断ロジック**: 評価テキストをパースし、美的スコアが向上しているかを判定します。品質が不十分な場合、ステップ 3 に戻り、別の `--kind` を試すか、過去の祖先ノード（親やルート）まで遡って別のブランチを成長させます（系譜のフォーク）。

---

## コマンド API リファレンス（AI高速参照用）

### 0.5 `plugin`

* **`plugin list`** — サーバーの宣言的プラグイン文書について、ロード済み／拒否、namespace、version、拒否理由をJSONで取得します。
* **`plugin validate <FILE.inku-plugin.md>`** — ローカルのUTF-8文書本文を管理APIへ送り、コードや外部ファイルを実行せず構文検証します。
* **`plugin reload`** — サーバーを再起動せず `server/plugins/` を明示再読込します。
* これらは管理者セッションを必要とします。プラグイン試験で生成するファイルは `cli/out2/<build>-<version>-<benchmark>/` の一つのrunディレクトリにまとめ、Git追跡しません。

### 0.6 `reference`

* **`reference [--md | --json] [-o FILE]`** — 実装内の語彙・定数テーブルの機械生成ダンプを取得します。既定は Markdown、`--json` で構造化 JSON。`-o` でファイルへ保存します。
* 冒頭に APP_VERSION / BUILD_NUMBER / git short hash / 生成日時 / ロード中プラグインの namespace+version を付けます。
* 収録は8節（歳時記、正規化DDL定型句、展開層、Score schema、色解決、weight 特性、演奏、検証規約）で、すべて実装モジュールから取得します。値をどこにも手書きしない「鏡」であり、生成・受理・coerce のいかなる判定にも接続しません。
* 設計・執筆セッションの冒頭資料として、生成した Markdown 一枚を添付する運用に使います。ログイン済みセッションで実行できます。

### 0.7 `paint --trace`（RAW trace）

* **`paint <TEXT> --trace [-o DIR --prefix P]`** — 1 回の生成で各層の RAW 中間生成物を持ち帰ります。リクエストに `include_trace` を付与し、応答の `trace` を `<prefix>-trace.json` として出力ディレクトリへ保存します（`--full-json` と独立）。
* trace 収録: `stage1_raw`／`stage1_thinking`／`stage1_ddl`（プラグイン展開前）、`plugin_expanded_ddl`、`stage15_ddl`（= Stage 2 入力）、`stage2_raw_attempts`（retry・fallback を含む全試行の生テキストと parse 可否）、`score_pre_coerce`、coerce／plugin 集約値。利き目監査（境界逐次検証）とベンチの精度向上に使う「鏡」であり、生成挙動は一切変えません。
* 旧サーバ（trace 非対応）では警告のみでエラーにしません。`include_trace` 未指定時の応答は現行と完全同一です。

### 0.8 沈黙する送り手に注意する

**`paint` / `batch` は、書かなかった旗についてサーバーの既定で描きます。**そしてサーバーの既定はWeb UIの既定と同じとは限りません。自律運転の結果をWeb UIの結果と比べる場合は、次の三つを明示してください。

| 旗 | サーバー既定 | Web UI既定 |
|---|---|---|
| `--sketch` / `--sketch-grain` | 切 | 細かく（`fine`） |
| `--wild` | 切 | ユーザー設定（既定は切） |
| `--catalog-mode` | `fixed` | ユーザー設定 |

```sh
uv run inku-cli paint "TEXT" --sketch --sketch-grain fine --catalog-mode auto -o ./out --png
```

変奏は `--variation-amplitude` と `--variation-seed` の**両方が揃ったときだけ**効きます。片方だけ渡しても展開層の軸は動かず、応答は既定のまま返るので、旗を渡したこと自体は成功の証拠になりません。**動いたかどうかは作品の`variation`と`variation_seed`を読んで確かめてください。**

### 1. `lineage`
* **`lineage show <ITEM_ID> [--depth D] [--limit L] [--json]`**
  * 指定したIDを基点とする系譜ツリーを表示します。
  * `--json` を指定すると、ツリーに含まれる全ノードとエッジの接続情報（`parent_node_id`, `child_node_id`）を取得できます。
* **`lineage promote <NODE_ID>`**
  * 中間ノード（通常履歴に表示されない `lineage_only`）を通常履歴に昇格させます。

### 2. `refine`
* **`refine perform <ITEM_ID> --kind {touch|layout|reading|color} [-o DIR] [--png] [--description TEXT]`**
  * 対象作品から局所的な別案を自動生成し、系譜を繋いで履歴に保存します。`--description` は構図・解釈の推敲で使う記述を差し替えます。
* **`refine save <PARENT_NODE_ID> --kind K --file SCORE_JSON --input-text T`**
  * ローカルで編集・生成した Score JSON を、任意の親ノードに接続する子ノードとして直接インポートします。

### 2.5 `colophon`

* **`colophon <ITEM_ID|NODE_ID> [--model M] [--language ja|en] [--dry-run] [--json] [-o FILE]`**
  * rootから対象作品までの一本の枝を、vision対応モデルが世代順に一人称で読みます。
  * 通常は署名付き奥書を追記保存します。`--dry-run`は保存せず標準出力だけを行います。
  * 奥書は評価・選別コマンドではなく、生成、推敲、枝選択へ接続してはいけません。

### 3. `inspect`
* **`inspect <TEXT> --models <MODEL_A,MODEL_B,...> -o DIR [--png]`**
  * 同一の入力テキストに対して、複数の LLM モデルを並行して実行し、それぞれの DDL 解釈と描画ファイルをローカルに一括保存します。
  * どの LLM モデルが最も表現力に富む出力を生み出せるかを AI が検証・比較する際に使用します。

### 4. `review`
* **`review evaluate <PNG_FILE> [--model M] [--prompt P]`**
  * Vision NIM モデルを使い、画像の視覚的評価（美的スコアやコメント）を行います。
* **`review unread <WORD> --context <CONTEXT>`**
  * Stage 1 (解釈) で AI が自信を持って読み取れなかった語彙（未読語）を、サーバーの未読語フィードバック台帳へ直接登録します。
