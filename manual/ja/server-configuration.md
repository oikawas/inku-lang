# サーバー設定方法

この文書は、システム管理者が inku を安定運用するための設定項目です。

## 1. 主要な環境変数

| 変数 | 目的 | 既定値 |
|---|---|---|
| `INKU_SERVER_HOST` | FastAPI の listen host | `127.0.0.1` |
| `INKU_SERVER_PORT` | FastAPI の listen port | `8100` |
| `INKU_SERVER_RELOAD` | uvicorn reload を有効化 | 無効 |
| `INKU_DB_URL` | DB 接続 URL | `sqlite:///$HOME/.local/share/inku/inku.db` |
| `INKU_SECRET_KEY` | API key 暗号化用の鍵材料 | 未設定 |
| `INKU_SECRET_KEY_FILE` | 暗号化鍵ファイル | `$HOME/.local/share/inku/secret.key` |
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | 初期管理者ユーザー名 | `admin` |
| `INKU_BOOTSTRAP_ADMIN_EMAIL` | 初期管理者 email | `admin@local` |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | 初期管理者パスワード | 未設定 |
| `INKU_SESSION_COOKIE_MAX_AGE` | セッション有効秒数 | 30 日 |
| `INKU_SESSION_COOKIE_SECURE` | secure cookie | 無効 |
| `INKU_OUTPUT_DIR` | artifact 保存先 | `$HOME/.local/share/inku/outputs` |
| `INKU_OUTPUT_PNG_SIZE` | 自動保存 PNG サイズ | `2160` |
| `INKU_OUTPUT_SAVE_WORKERS` | ファイル保存 worker 数 | `2` |
| `INKU_OUTPUT_SAVE_QUEUE_LIMIT` | ファイル保存 queue 上限 | `32` |
| `INKU_STAGE_WORKERS` | 描画 pipeline worker 数 | `4` |
| `INKU_STAGE_QUEUE_LIMIT` | pipeline queue 上限 | worker 数の 2 倍 |
| `INKU_LOG_RETENTION_DAYS` | ログ保存日数 | `90` |
| `INKU_LOG_ROTATE` | ログローテーション周期 | `daily` |

LLM retry 関連:

| 変数 | 目的 |
|---|---|
| `INKU_LLM_RETRY_ATTEMPTS` | 一時エラー時の retry 回数 |
| `INKU_LLM_RETRY_BASE_DELAY` | retry 初期待機秒 |
| `INKU_LLM_RETRY_MAX_DELAY` | retry 最大待機秒 |
| `INKU_LLM_RETRY_JITTER` | retry jitter |
| `INKU_LLM_REQUEST_TIMEOUT_SECONDS` | LLM API request timeout |
| `INKU_STAGE1_HARD_TIMEOUT_SECONDS` | Stage 1 hard timeout |
| `INKU_STAGE2_HARD_TIMEOUT_SECONDS` | Stage 2 hard timeout |

AI provider 関連:

| Provider | API key | Base URL |
|---|---|---|
| OpenAI API Platform | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| Claude API | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| Gemini API | `GEMINI_API_KEY` | `GEMINI_BASE_URL` |
| NVIDIA NIM | `NVIDIA_API_KEY` | `NVIDIA_BASE_URL` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` |
| Intel OVMS | `OVMS_API_KEY` | `OVMS_BASE_URL` |

## 2. DB 設定

サービス用ユーザーと永続ディレクトリを先に用意します。

```sh
sudo useradd --system --create-home --home-dir /var/lib/inku --shell /usr/sbin/nologin inku
sudo mkdir -p /var/lib/inku /var/log/inku /etc/inku
sudo chown -R inku:inku /var/lib/inku /var/log/inku
sudo chmod 0750 /var/lib/inku /var/log/inku
```

### SQLite

小規模運用や単一サーバーでは SQLite が簡単です。

```sh
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
```

運用前にディレクトリを作成します。

```sh
sudo mkdir -p /var/lib/inku
sudo chown inku:inku /var/lib/inku
sudo chmod 0750 /var/lib/inku
```

SQLite では履歴検索に FTS5 を使います。FTS5 が利用できない環境では LIKE 検索へ fallback します。

### PostgreSQL

複数ユーザーや長期運用で DB を分離したい場合は PostgreSQL を使えます。

```sh
INKU_DB_URL=postgresql://inku:<password>@127.0.0.1/inku
```

DB URL にはパスワードが入るため、環境変数ファイルの権限は `0600` にします。

## 3. 認証とユーザー管理

初期管理者は、新規 DB かつ `INKU_BOOTSTRAP_ADMIN_PASSWORD` が設定されている場合だけ作成されます。

```sh
INKU_BOOTSTRAP_ADMIN_USERNAME=admin
INKU_BOOTSTRAP_ADMIN_EMAIL=admin@example.local
INKU_BOOTSTRAP_ADMIN_PASSWORD=change-this-password
```

ログイン後、管理者は Web UI の `設定` -> `ユーザー管理` からユーザー、ロール、グループを管理します。

ロール:

| ロール | 権限 |
|---|---|
| admin | モデル接続、DB設定、ユーザー管理、ログ、サーバー設定を管理 |
| group_lead | 所属範囲のユーザー管理 |
| user | 画像作成と自分の履歴管理 |

`/api/interpret`、`/api/compose`、`/api/paint` は認証必須です。未ログインの場合は 401 を返します。

## 4. AI サービス接続

管理者は `設定` -> `モデル設定` で AI サービス接続を管理します。

設定できるもの:

- サービス名
- 接続形式
- Base URL
- API key
- 公開モデル
- メモ
- モデルリスト取得

API key は DB に保存される場合、`enc:v1:` 形式で暗号化されます。暗号化鍵は次の順で決まります。

1. `INKU_SECRET_KEY`
2. `INKU_SECRET_KEY_FILE`
3. `$HOME/.local/share/inku/secret.key`

本番では、`INKU_SECRET_KEY_FILE` を永続ディスクに置き、バックアップ対象にしてください。鍵を失うと DB 内の暗号化済み API key を復号できません。

## 5. Stage 1 / Stage 2 モデル

inku は 2 段階の LLM pipeline を持ちます。

| 段階 | 役割 | モデル選定の考え方 |
|---|---|---|
| Stage 1 解釈 | 自由な母語記述を正規化DDLへ読む | 解釈力の高いモデル |
| Stage 1.5 中間フィルタ | 正規化DDLを決定的に拡張 | LLM ではなくサーバー内処理 |
| Stage 2 構造化 | DDL を JSON Score へ変換 | スキーマ遵守が得意なモデル |
| Renderer | JSON Score を SVG へ描画 | サーバー内処理 |

ユーザーごとの Stage 1 / Stage 2 選択は `user_accounts.model_settings` に保存されます。管理者の provider 設定とは別です。

## 6. 出力ファイル保存

履歴 DB が正本です。SVG / JSON / PNG などのファイル保存は副産物です。

出力保存先:

```sh
INKU_OUTPUT_DIR=/var/lib/inku/outputs
```

ディレクトリ構成:

```text
<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>...
```

管理者は `設定` -> `その他（サーバー）` から以下を変更できます。

- 自動保存の有効 / 無効
- 保存先フォルダ
- PNG サイズ
- 保存 worker / queue

queue が上限に達した場合、DB 履歴保存を優先し、artifact 保存だけがスキップされます。

## 7. ログ保存

推奨ログディレクトリ:

```sh
/var/log/inku
```

作成:

```sh
sudo mkdir -p /var/log/inku
sudo chown inku:inku /var/log/inku
sudo chmod 0750 /var/log/inku
```

Web UI の `設定` -> `ログ保存` では、ログ保存ポリシー、保存期間、ローテーション周期、systemd drop-in、logrotate 設定プレビューを確認できます。OS への実適用はサーバー管理者が行います。

logrotate 例は [templates/logrotate/inku](./templates/logrotate/inku) にあります。

## 8. systemd 運用

サービス例:

- [inku-api.service](./templates/systemd/inku-api.service)
- [inku-server.service](./templates/systemd/inku-server.service)

登録後:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
```

確認:

```sh
systemctl status inku-api.service --no-pager
systemctl status inku-server.service --no-pager
journalctl -u inku-api.service -n 100 --no-pager
journalctl -u inku-server.service -n 100 --no-pager
```

再起動:

```sh
sudo systemctl restart inku-api.service
sudo systemctl restart inku-server.service
```

## 9. reverse proxy

公開サーバーでは、nginx や Caddy などの reverse proxy を前段に置き、HTTPS を終端します。

最小構成:

- `/` を `http://127.0.0.1:5173/` へ proxy
- `/api/` を `http://127.0.0.1:8100/api/` へ proxy
- `/health` を必要に応じて `http://127.0.0.1:8100/health` へ proxy
- HTTPS を有効化
- `INKU_SESSION_COOKIE_SECURE=1` を設定

Vite dev server を外部公開する構成は参照運用向けです。公衆インターネットへ出す場合は、SvelteKit の production adapter と reverse proxy の採用を検討してください。

## 10. バックアップ

最低限バックアップするもの:

| 対象 | 理由 |
|---|---|
| DB | 履歴、ユーザー、設定の正本 |
| `INKU_SECRET_KEY_FILE` | DB 内 API key 復号に必要 |
| 出力ファイル | 再生成可能だが、運用上残したい場合 |
| `/etc/inku/inku-api.env` | 環境設定 |
| systemd / logrotate 設定 | サービス復旧 |

SQLite の場合は、Web UI の `DB設定` からバックアップ設定と手動バックアップを使えます。外部バックアップにも含めてください。

## 11. health check

API:

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
```

Web:

```sh
curl -sS -i --max-time 5 http://127.0.0.1:5173/ | head -n 20
```

認証 API:

```sh
curl -sS -i --max-time 5 \
  -X POST http://127.0.0.1:5173/api/auth/login \
  -H 'Content-Type: application/json' \
  --data '{"username":"admin","password":"wrong"}'
```

誤ったパスワードで 401 が返れば、Web から API proxy まで到達しています。

## 12. 障害対応

| 症状 | 確認 |
|---|---|
| ログインできない | DB にユーザーがあるか、初期管理者作成条件を満たしたか |
| 画像生成が失敗する | AI provider の API key、Base URL、公開モデル、ログを確認 |
| 生成が遅い | LLM provider の混雑、retry、timeout、Stage worker queue を確認 |
| 画像は出るがファイルがない | `output_save` の queue skip、保存先権限を確認 |
| Web は開くが描画できない | `/api/paint` への proxy、認証 Cookie、API サービスを確認 |
| API key が使えない | `INKU_SECRET_KEY_FILE` が変わっていないか確認 |
| DB が大きい | 履歴管理、バックアップ、出力ファイル保存方針を見直す |

## 13. セキュリティ注意

- `INKU_BOOTSTRAP_ADMIN_PASSWORD` は初回作成後、環境変数から削除するか安全に管理します。
- `/etc/inku/inku-api.env` は `0600` にします。
- `INKU_SECRET_KEY_FILE` は永続保存し、権限を絞ります。
- 公開環境では HTTPS を使い、`INKU_SESSION_COOKIE_SECURE=1` を設定します。
- API key、DB URL、ホスト固有の運用情報を Git にコミットしません。
- systemd、sudoers、reverse proxy などの実運用設定はサーバー側の管理対象として扱います。
