# inku-cli AI自律運転・テスト用リファレンス

本ドキュメントは、AIエージェントが `inku-server` をコマンドラインから操作し、自律的に作品の生成、評価、および「系譜（Lineage）」を駆使した「推敲（Refine/Vary）」の品質向上プロセスをテスト・実行するためのガイドラインです。

対象はinku v2.15.241（Web Build 1317）です。旗の全一覧は`inku-cli リファレンス`が持ちます。

今後の実providerテスト・比較では、次のモデルを使います（接続はChatGPTプランとGemini API（Cloud）の2系統）。NVIDIA NIMは候補・既定・fallback・Vision評価から外します。

| 用途 | 接続とモデル | 明示するモデル参照 |
|---|---|---|
| Primary | ChatGPTプラン / GPT-6-Luna | `chatgpt:gpt-6-luna` |
| Secondary | Gemini API（Cloud）/ Gemma 4 31B IT | `gemini:gemma-4-31b-it` |
| Vision | ChatGPTプラン / GPT-6.1-Sol | `chatgpt:gpt-6.1-sol` |
| Vision | ChatGPTプラン / GPT-6-Astra | `chatgpt:gpt-6-astra` |

Visionの2つは、画像を読ませる試験に使います（出力画像の確認にVisionを併用する場合など）。

実行前に本人の接続・公開モデル・利用枠を確認します。ChatGPTプランの接続条件は[接続ガイド](../../docs/guide/chatgpt-plan.ja.md)に従います。SecondaryはGemini APIの接続であり、NIMの`google/`付きIDやローカルGemmaへ読み替えません。モデルを明示できない入口や接続失敗では実行を止め、NIMへ切り替えません。比較では同じ記述とseed等の条件を固定し、実際のprovider・モデル・結果を記録します。

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
uv run inku-cli paint "白い余白に、黒い太筆の波線を一本引く。" --stage1-model chatgpt:gpt-6-luna -o ./test_output --png --save-history
```
`--stage1-model`はStage 1/2共通のモデルを指定します。Secondaryを試すときは`gemini:gemma-4-31b-it`を明示します。省略してサーバーや保存済みCLI設定の既定へ委ねません。

* **期待される出力 (JSON)**:
  生成された作品のメタデータを含む JSON オブジェクト。
  * `history_id`: `"d5989732-9f3a-4dd2-82df-c49c50761119"` (例)
  * `render_hash`: 作品固有のレンダリングハッシュ
  * `paths.json`, `paths.svg`, `paths.png`: 各種出力ファイルのローカルパス
* **AIの判断ロジック**: 出力から `"history_id"` を抽出して `PARENT_ID` として変数に保持します。

### ステップ 3: 派生作品の自動生成（推敲 / Refine）
作成した作品を親ノードとし、特定の要素（構図・色）を変動させた推敲作品を生成して系譜に繋げます。

```sh
# 親ID: PARENT_ID (例: d5989732-9f3a-4dd2-82df-c49c50761119) の配置を推敲
uv run inku-cli refine perform PARENT_ID --kind layout -o ./test_output --png
```
* **パラメータ `--kind` の選択基準**:
  * `layout`: 線の位置や大きさを再構築したいとき。新しい `composition_seed` を置き、Stage 2が再配置する
  * `color`: 他の色カタログを適用したいとき（LLM呼び出しなし）
* **期待される出力**: `-o`を省くと派生作品のメタデータを JSON で表示します。`-o DIR` を付けると DIR に `refine-<kind>-<render_hash_short>.json` と `.svg`（`--png` を付けると `.png` も）を書き、JSON の代わりに `Saved:` の行を表示します。

`--kind` はサーバーへ `derivation_kind` として記録されます（順に `layout_change` / `catalog_change`）。系譜のedgeを検証するときはこの値を読みます。タッチ（`touch`）と読み取り（`reading`）の推敲は2026-10-14に削除しました。前に作った作品の辺は `touch_change`・`reinterpretation` のまま残ります。

### ステップ 4: 作品系譜の探索と状態確認
追加した派生作品が、親作品のツリーに対して正しくエッジ（派生タイプ）で連結されているかをコンソール上で探索します。

```sh
uv run inku-cli lineage show PARENT_ID
```
* **期待される出力 (ツリー表示の例)**:
  ```text
  Work lineage:
  - (Root) dfced380 [Displayed] : 白い余白に、黒い太筆の波線を一本引く。
    - (layout_change) b91ae625  : 白い余白に、黒い太筆の波線を一本引く。
  ```
* **AIの判断ロジック**: 親ノード（`dfced380`）の配下に、指定した `derivation_kind`（例: `layout_change`）のエッジで子ノード（`b91ae625`）がネストされていることをパースし、系譜が正しく成長していることを検証します。

### ステップ 5: 出力画像の確認と選定
書き出したPNGを同じ表示条件で見比べ、入力記述、構図、色、欠落や回帰を確認し、選定理由を記録します。Visionを併用する場合は、本人が公開したVisionのモデル（またはPrimary・Secondary）を明示できるWeb/APIの入口を使い、実際の接続とモデルを確認します。

`review evaluate`と`vision-review`はNIM専用の製品機能です。このテスト・比較手順では実行しません。`--model`だけを上記のモデル参照へ替えても送信先は変わりません。必要なモデルを選べる入口が無ければ、画像の確認結果だけを記録して止めます。

---

## コマンド API リファレンス（AI高速参照用）

### 0.5 `plugin`

* **`plugin list`** — サーバーの宣言的プラグイン文書について、ロード済み／拒否、namespace、version、拒否理由をJSONで取得します。
* **`plugin validate <FILE.inku-plugin.md>`** — ローカルのUTF-8文書本文を管理APIへ送り、コードや外部ファイルを実行せず構文検証します。
* **`plugin reload`** — サーバーを再起動せず `server/plugins/` を明示再読込します。
* `plugin validate`と`plugin reload`は管理者セッションを必要とします（管理者でない場合は403）。`plugin list`はログイン済みセッションで実行できます。プラグイン試験で生成するファイルは `cli/out2/<build>-<version>-<benchmark>/` の一つのrunディレクトリにまとめ、Git追跡しません。

### 0.6 `reference`

* **`reference [--md | --json] [-o FILE]`** — 実装内の語彙・定数テーブルの機械生成ダンプを取得します。既定は Markdown、`--json` で構造化 JSON。`-o` でファイルへ保存します。
* 冒頭に APP_VERSION / BUILD_NUMBER / git short hash / 生成日時 / インストール済みの各プラグインパッケージの namespace・name・version・status（拒否されたものを含む）を付けます。
* 収録は8節（歳時記、正規化DDL定型句、展開層、Score schema、色解決、weight 特性、演奏、検証規約）で、すべて実装モジュールから取得します。値をどこにも手書きしない「鏡」であり、生成・受理・coerce のいかなる判定にも接続しません。
* 設計・執筆セッションの冒頭資料として、生成した Markdown 一枚を添付する運用に使います。ログイン済みセッションで実行できます。

### 0.7 沈黙する送り手に注意する

**`paint` / `batch` は、書かなかった旗についてサーバーの既定で描きます。**そしてサーバーの既定はWeb UIの既定と同じとは限りません。自律運転の結果をWeb UIの結果と比べる場合は、次の三つを明示してください。

| 旗 | サーバー既定 | Web UI既定 |
|---|---|---|
| `--sketch` | 切 | 切 |
| `--wild` | 切 | ユーザー設定（既定は切） |
| `--catalog-mode` | `fixed` | ユーザー設定 |

```sh
uv run inku-cli paint "TEXT" --stage1-model chatgpt:gpt-6-luna --sketch --catalog-mode auto -o ./out --png
```

変奏は廃止しました。旧強度・seedの旗を使わないでください。推敲は配置・色カタログの2操作です（タッチと読み取りは2026-10-14に削除）。保存済みの変奏情報は旧作品の記録として保持し、新規要求や保存には渡しません。pipelineの作品IDとScoreの揺らぎは別の契約で、変更しません。

### 1. `lineage`
* **`lineage show <ITEM_ID> [--depth D] [--limit L] [--json]`**
  * 指定したIDを基点とする系譜ツリーを表示します。
  * `--json` を指定すると、ツリーに含まれる全ノードとエッジの接続情報（`parent_node_id`, `child_node_id`）を取得できます。
* **`lineage promote <NODE_ID>`**
  * 中間ノード（通常履歴に表示されない `lineage_only`）を通常履歴に昇格させます。

### 2. `refine`
* **`refine perform <ITEM_ID> --kind {layout|color} [-o DIR] [--png] [--no-save]`**
  * 対象作品の保存した指示書（DDL）から局所的な別案を描き、系譜を繋いで履歴に保存します。記述は読み直しません（`layout` は配置の seed、`color` は色カタログだけを替える）。
* **`refine save <PARENT_NODE_ID> --kind K --file SCORE_JSON --input-text T`**
  * ローカルで編集・生成した Score JSON を、任意の親ノードに接続する子ノードとして直接インポートします。

### 2.5 `colophon`

* **`colophon <ITEM_ID|NODE_ID> [--model M] [--language ja|en] [--dry-run] [--json] [-o FILE]`**
  * rootから対象作品までの一本の枝を、vision対応モデルが世代順に一人称で読みます。
  * 通常は署名付き奥書を追記保存します。`--dry-run`は保存せず標準出力だけを行います。
  * 奥書は評価・選別コマンドではなく、生成、推敲、枝選択へ接続してはいけません。

### 3. `inspect`
* **`inspect <TEXT> --models <MODEL_A,MODEL_B,...> -o DIR [--png]`**
  * 同一の入力テキストに対して、指定した複数の LLM モデルを順に（並行ではなく）実行し、それぞれの DDL 解釈と描画ファイルをローカルに一括保存します。各モデルをStage 1とStage 2の両方に使います。
  * どの LLM モデルが最も表現力に富む出力を生み出せるかを AI が検証・比較する際に使用します。
  * 今後の比較対象は`--models chatgpt:gpt-6-luna,gemini:gemma-4-31b-it`です。NIMは含めません。

### 4. `review`
* **`review evaluate <PNG_FILE> [--model M] [--prompt P]`**
  * NIM専用の製品機能を説明する項目です。今後のテスト・比較・Vision評価には使いません。
* **`review unread <WORD> --context <CONTEXT>`**
  * Stage 1 (解釈) で AI が自信を持って読み取れなかった語彙（未読語）を、サーバーの未読語フィードバック台帳へ直接登録します。
