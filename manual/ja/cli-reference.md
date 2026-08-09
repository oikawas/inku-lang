# inku-cli リファレンス

inku-cliはWeb UIと同じ公開HTTP APIを操作するクライアントです。保存済みセッションを使い、一般ユーザー、グループリード、管理者それぞれの権限判定はサーバーが行います。

対象はinku v2.11.14（Web Build 870）です。

## 基本操作

    cd cli
    uv run inku-cli --help
    uv run inku-cli login --base-url http://127.0.0.1:8100 -u USERNAME
    uv run inku-cli me
    uv run inku-cli version

各コマンドの完全な引数一覧は inku-cli COMMAND --help で表示できます。本書はコマンドの用途と、Web UIとの対応が分かりにくい旗だけを述べます。

| コマンド | 用途 |
|---|---|
| login / logout / me | セッションの開始、破棄、本人確認 |
| models | CLI既定のStage 1 / Stage 2 / Visionモデルと色カタログの設定 |
| paint / batch | 記述または指示書から単体・一括描画 |
| refine | 既存作品から要素（タッチ・構図・解釈・色）を推敲し派生を生成・保存 |
| lineage | 作品の系譜（親・子・兄弟）ツリーの探索表示、中間ノードの昇格 |
| colophon | 起点から対象作品までの一本の枝を、追記専用の読みとして朗読 |
| inspect | 同一記述に対する複数モデルの解釈・描画の並列比較 |
| review | Vision による視覚的評価、および未読語フィードバック |
| render-score | Stage 1 / 2を通さずScore JSONを描画 |
| demo-instruction | デモ用記述の生成 |
| history / history-export | 履歴一覧とhash指定の書き出し |
| unread-words | 本人の未読語台帳。管理者は --all で全体集計 |
| contact-sheet / analyze / ddl-compare | ローカル成果物の比較・解析 |
| rasterize | SVGのフォルダをPNGへ焼く。1ファイル1子プロセスで、`--workers` で同時に走らせる本数を決める |
| vision-review | 設定済みvision modelによる読み取り専用評価 |
| plugin | 宣言的DDLプラグインの一覧、検証、再読込 |
| reference | 実装内の語彙・定数テーブルの読み取り専用ダンプ |
| user / group | ユーザーアカウントとグループの管理 |
| config | サーバーのシステム設定の表示と更新 |
| api | 任意の公開APIをHTTP method指定で操作 |
| version | CLIと接続先serverのversion/build表示 |

## paint と batch の旗

paintとbatchは同じ旗を受け取ります。**旗を書かなければサーバーの既定が使われ、サーバーの既定はWeb UIの既定と同じとは限りません。**

### 入力と出力

| 旗 | 内容 |
|---|---|
| `--file FILE` / `-f` | 記述をUTF-8ファイルから読む。paintは `-` で標準入力。batchは空行以外の1行が1作品 |
| `--out-dir DIR` / `-o` | JSON / SVG / PNGの出力先 |
| `--prefix P` | 出力ファイル名の接頭辞 |
| `--png` | `--out-dir` を指定したとき、PNGも書き出す |
| `--svg-profile {display,editable,compat}` | 保存するSVGのプロファイル |
| `--input-mode {paint,ddl}` | `paint` は自然文をStage 1へ、`ddl` は指示書を直接Stage 2と演奏へ渡す |
| `--ddl-text DDL` | **`render-score` 専用。**指示書をcoerceへ手渡す。paintと同じく、指示書に基づく補修が働く（本数や関係の指定が絵に出る）。**渡さなければ従来どおり補修は働かない** |
| `--ddl-file PATH` | **`render-score` 専用。**指示書をファイルから読む。`-` は標準入力。`--ddl-text` とは併用できない |
| `--save-history` | サーバーの履歴へ保存する |
| `--save-artifacts` / `--no-save-artifacts` | サーバー側の成果物保存の有無 |
| `--full-json` | 応答全体を印字する |
| `--no-progress` | 経過時間のアニメーションを止める |

### 写生（Stage 0.5）

| 旗 | 内容 |
|---|---|
| `--sketch` | 記述を写生層へ通してから解釈へ渡す。**サーバー既定は切、Web UIの既定は細かく** |
| `--sketch-grain {fine,coarse}` | 区切りの大きさ。`fine` がサーバー既定 |
| `--sketch-text TEXT` | Stage 0.5を呼ばず、この写生文を使う（保存済みまたは手で直した写生の再演） |

### 変奏（Stage 1.5）

| 旗 | 内容 |
|---|---|
| `--variation-amplitude {small,medium,large}` | 展開層の軸をどこまで動かすか |
| `--variation-seed SEED` | どの軸をどちら向きに動かすか |

**変奏は2つの旗が揃ったときだけ効きます。**片方だけでは何も動きません。

### 演奏と色

| 旗 | 内容 |
|---|---|
| `--wild` | 筆致の天井を外す |
| `--color-catalog ID` | サーバーの色カタログID |
| `--catalog-id ID` | `--color-catalog` の旧名 |
| `--catalog-mode {fixed,auto,random}` | `fixed` は `--color-catalog` を使う、`auto` はサーバーが記述を読んで選ぶ、`random` は `--color-catalog` 以外から引く |
| `--from-work WORK_ID` | `render-score` 専用。**その作品が描かれた当時の色で描く**（カタログの今日の定義ではなく、作品の行に記録された色を使う）。**改名・引退したカタログの作品も描ける。**`--color-catalog` / `--catalog-id` とは併用できない |
| `--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}` | キャンバスの比率 |

### seed と再現

| 旗 | 内容 |
|---|---|
| `--render-seed SEED` | 演奏のseed。同じseedと同じScoreなら同じ絵になる |
| `--composition-seed SEED` | 墨を置く位置のseed。省略すると配置は`--render-seed`に従う（render engine 23〜） |
| `--seed-text TEXT` | 演奏のseedだけを導く文字列（Web UIの「言葉でタッチを変える」に相当） |
| `--interpretation-seed ID` | 前の読み取りを使い回さず、この識別子でStage 1へ明示的な読み直しを求める |

### モデルと言語

| 旗 | 内容 |
|---|---|
| `--stage1-provider` / `--stage1-model` | Stage 1（解釈）の接続先とモデル |
| `--stage2-provider` / `--stage2-model` | Stage 2（構造化）の接続先とモデル |
| `--instruction-lang {auto,ja,en}` | 記述の言語 |
| `--ui-lang LANG` | UI言語として記録する値 |
| `--include-thinking` | 思考出力を応答に含める |

### 観測

| 旗 | 内容 |
|---|---|
| `--trace` | 各層のRAW中間生成物を要求し、`<prefix>-trace.json` として保存する |

batchはさらに `--continue-on-error` を持ちます。

## 履歴とフィードバック

| コマンド | 主な旗 |
|---|---|
| `history` | `--limit` / `--offset` / `--query` / `--starred` / `--for-revision` |
| `history-export` | `--from` / `--to`（hash下位桁の範囲）/ `--out-dir` / `--columns` / `--thumb-size` / `--starred` / `--for-revision` |
| `unread-words` | `--all`（管理者のみの全体集計）/ `--limit` |

`--for-revision` は推敲マークの付いた作品だけに絞ります。スターとは別の印です。

## プラグインと参照

| コマンド | 内容 |
|---|---|
| `plugin list` | ロード済み／拒否されたプラグイン文書、namespace、version、拒否理由をJSONで取得する |
| `plugin validate FILE` | ローカルの文書本文を管理APIへ送り、コードや外部ファイルを実行せず構文検証する |
| `plugin reload` | サーバーを再起動せず `server/plugins/` を明示再読込する |
| `reference [--md \| --json] [-o FILE]` | 実装内の語彙・定数テーブルの機械生成ダンプ。既定はMarkdown |

`plugin` は管理者セッションを必要とします。`reference` はログイン済みセッションで実行できます。

## 奥書

    uv run inku-cli colophon ITEM_ID --language ja --dry-run

起点から対象作品までの一本の枝を、vision対応モデルが世代順に一人称で読みます。通常は署名付きの奥書を追記保存し、`--dry-run` は保存せず標準出力だけを行います。`--vision-model` で読み手を選べます（`--model` は旧名）。

奥書は評価・選別のコマンドではありません。生成、推敲、枝の選択へ接続してはいけません。

## 管理

| コマンド | 内容 |
|---|---|
| `user list / create / update / delete` | ユーザーアカウントの管理 |
| `group list / create / update / delete` | ユーザーグループの管理 |
| `config show` | サーバーのシステム設定を表示する |
| `config update` | サーバーのシステム設定を更新する |

`user` と `group` は管理者またはグループリード、`config` は管理者のセッションを必要とします。制限値、描画の並列度、ログ保存ポリシー、DBバックアップ設定は `config` の対象です。値の意味は`サーバー設定方法`を参照してください。

## 全公開APIの操作

専用コマンドがないAPIは api で呼び出します。pathは /api/... または /health の相対pathだけを受け付け、別hostへの転送は拒否します。

    uv run inku-cli api GET /api/color-catalogs
    uv run inku-cli api GET /api/history --query limit=20 --query starred=true
    uv run inku-cli api PATCH /api/auth/me/settings --data '{"ui_theme":"dark"}'
    uv run inku-cli api POST /api/history/trash --file ids.json
    uv run inku-cli api DELETE /api/history --header X-Inku-Confirm=permanent-delete-trash
    uv run inku-cli api GET /api/history/WORK_ID/svg --query profile=editable --output work.svg

--data と --file は同時指定できません。JSON以外のresponseは --output へ保存できます。認証不要endpointには --no-auth を指定できます。

権限はGUIと同一です。一般ユーザーは本人の作品・設定だけ、グループリードは同一グループの一般ユーザー管理、管理者はserver設定、全ユーザー管理、全体未読語集計を操作できます。権限外の呼び出しは403、未ログインは401です。

保存系APIを再試行する場合は、同じ Idempotency-Key を指定すると作品と系譜の二重保存を防げます。

    uv run inku-cli api POST /api/history --file work.json --header Idempotency-Key=import-20260715-001


## AI自律および作品品質向上のためのコマンド

AIエージェントによる自動生成、評価、および系譜ツリーを辿った自律的な推敲ループで使用可能な専用コマンドです。実行手順は`inku-cli AI自律運転・テスト用リファレンス`が持ちます。

### 1. 作品系譜 (lineage)
作品の派生ツリーを表示、または中間作品を通常履歴に昇格させます。

* **系譜ツリーの表示**:
  ```sh
  uv run inku-cli lineage show WORK_ID --depth 3
  ```
  指定した作品IDを中心に、親・子ノードの関係をコンソール上にツリーテキスト表示します。`--json` を指定すると生JSONで出力します。
* **中間作品の昇格**:
  ```sh
  uv run inku-cli lineage promote NODE_ID
  ```
  一時的な推敲で生まれた `lineage_only`（通常履歴非表示）のノードを、ユーザーの通常履歴へと昇格します。

### 2. 推敲と派生生成 (refine)
既存作品を親ノードとして紐付け、局所的な別案を生成・保存します。

* **推敲候補の自動生成**:
  ```sh
  uv run inku-cli refine perform WORK_ID --kind touch -o ./refinements --png
  ```
  `--kind` に `touch` (タッチ), `layout` (構図), `reading` (解釈), `color` (配色カタログ) のいずれかを指定し、別案を生成してサーバーに保存します。`-o` が指定された場合はローカルファイルとしても書き出します。`--description` で構図・解釈の推敲に使う記述を差し替えられます。
* **手動候補の系譜保存**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "入力記述"
  ```
  ローカルで調整したScore JSONを、親ノードに接続した派生（子）としてサーバー履歴へ直接インポートします。

### 3. 多モデル並列比較 (inspect)
同一の記述に対して、複数のモデルがどのように解釈（DDL）および描画するかを並列で実行し、比較します。

```sh
uv run inku-cli inspect "青い線を引く" --models "MODEL_A,MODEL_B" -o ./inspection --png
```

### 4. 視覚的評価とフィードバック (review)
Visionモデルによる自律的な出来栄え評価、および解釈に自信のなかった語彙のサーバー通知を行います。

* **Vision による画の評価**:
  ```sh
  uv run inku-cli review evaluate drawing.png --model VISION_MODEL
  ```
  描画された画像を Vision LLM に送信し、余白、コントラスト、表現などの観点から点数評価および一文フィードバックを取得します（provider側のAPIキー設定が必要）。
* **未読語のフィードバック登録**:
  ```sh
  uv run inku-cli review unread "薄墨" --context "薄墨の地に円を描く"
  ```
  AIが正しく変換できなかった語彙と文脈を、サーバーの未読語台帳へ通知・登録します。
