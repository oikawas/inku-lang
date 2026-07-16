# inku-cli リファレンス

inku-cliはWeb UIと同じ公開HTTP APIを操作するクライアントです。保存済みセッションを使い、一般ユーザー、グループリード、管理者それぞれの権限判定はサーバーが行います。

## 基本操作

    cd cli
    uv run inku-cli --help
    uv run inku-cli login --base-url http://127.0.0.1:8100 -u USERNAME
    uv run inku-cli me
    uv run inku-cli version

各コマンドの完全な引数一覧は inku-cli COMMAND --help で表示できます。

| コマンド | 用途 |
|---|---|
| login / logout / me | セッションの開始、破棄、本人確認 |
| models | CLI既定のStage 1 / Stage 2モデル設定 |
| paint / batch | 記述またはDDLから単体・一括生成 |
| refine | 既存作品から要素（タッチ・構図・解釈・色）を推敲し派生を生成・保存 |
| lineage | 作品の系譜（親・子・兄弟）ツリーの探索表示、中間ノードの昇格 |
| inspect | 同一プロンプトに対する複数モデルの解釈・描画の並列比較 |
| review | Vision NIM による視覚的評価、および未読語フィードバック |
| render-score | Stage 1 / 2を通さずScore JSONを描画 |
| demo-instruction | デモ用指示文の生成 |
| history / history-export | 履歴一覧とhash指定の書き出し |
| unread-words | 本人の未読語台帳。管理者は --all で全体集計 |
| contact-sheet / analyze / ddl-compare | ローカル成果物の比較・解析 |
| vision-review | 設定済みvision modelによる読み取り専用評価 |
| api | 任意の公開APIをHTTP method指定で操作 |
| version | CLIと接続先serverのversion/build表示 |

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

AIエージェントによる自動生成、評価、および系譜ツリーを辿った自律的な推敲ループで使用可能な専用コマンドです。

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

### 2. 推敲と変種生成 (refine)
既存作品を親ノードとして紐付け、局所的なバリエーションを生成・保存します。

* **推敲候補の自動生成**:
  ```sh
  uv run inku-cli refine generate WORK_ID --kind touch -o ./refinements --png
  ```
  `--kind` に `touch` (タッチ), `layout` (構図), `reading` (解釈), `color` (配色カタログ) のいずれかを指定し、別案を生成してサーバーに保存します。`-o` が指定された場合はローカルファイルとしても書き出します。
* **手動候補の系譜保存**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "入力記述"
  ```
  ローカルで調整したScore JSONを、親ノードに接続した派生（子）としてサーバー履歴へ直接インポートします。

### 3. 多モデル並列比較 (inspect)
同一の記述文に対して、複数のモデルがどのように解釈（DDL）および描画するかを並列で実行し、比較します。

```sh
uv run inku-cli inspect "青い線を引く" --models "qwen/qwen3.5-397b-a17b,google/gemma-4-31b-it" -o ./inspection --png
```

### 4. 視覚的評価とフィードバック (review)
Visionモデルによる自律的な出来栄え評価、および解釈に自信のなかった語彙のサーバー通知を行います。

* **Vision NIM による画の評価**:
  ```sh
  uv run inku-cli review evaluate drawing.png --model nvidia/neva-22b
  ```
  描画された画像を Vision LLM に送信し、余白、コントラスト、表現などの観点から点数評価および一文フィードバックを取得します（`NVIDIA_API_KEY` の設定が必要）。
* **未読語のフィードバック登録**:
  ```sh
  uv run inku-cli review unread "薄墨" --context "薄墨の地に円を描く"
  ```
  AIが正しく変換できなかった語彙と文脈を、サーバーの未読語台帳へ通知・登録します。

