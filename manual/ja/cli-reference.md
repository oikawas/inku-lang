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
