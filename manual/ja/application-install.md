# アプリケーションインストール

この文書は、未リリース版inku v2.11.16（Web Build 872）をLinuxサーバーへ新規導入または更新するための標準手順です。従来のsystemd開発構成と、production SvelteKit adapterを使うCompose構成を提供します。公衆インターネットへ公開する場合はTLS reverse proxyを前段へ配置してください。

## 1. 構成

| コンポーネント | 役割 | 既定ポート |
|---|---|---|
| `inku-api` | FastAPI。認証、LLM pipeline、履歴・系譜DB、Renderer、設定API | 8100 |
| `inku-server` | SvelteKit／Vite Web UI。`/api`をbackendへproxy | 5173 |
| `inku-cli` | 同じHTTP APIを使う任意のCLI client | - |

主要ディレクトリ:

```text
inku-lang/
  server/   FastAPI backend
  web/      SvelteKit frontend
  cli/      HTTP API client
  shared/   server/CLI共通解析コード
  manual/   利用・運用マニュアル
```

## 2. 前提条件

- Linuxとsystemd
- Python 3.12以上（`server` と `cli` の `requires-python` が `>=3.12`）
- uv
- Node.jsとnpm
- Gitまたはrsyncなどの配置手段
- （PNG出力に使う `resvg-py` はwheelで入るため、OSライブラリの追加導入は要らない）
- 任意: PostgreSQL、reverse proxy、TLS証明書

```sh
python3 --version
uv --version
node --version
npm --version
```

## 3. 専用ユーザーと永続領域

```sh
sudo useradd --system --create-home --home-dir /var/lib/inku --shell /usr/sbin/nologin inku
sudo mkdir -p /opt/inku /var/lib/inku /var/lib/inku/outputs /var/log/inku /etc/inku
sudo chown -R inku:inku /opt/inku /var/lib/inku /var/log/inku
sudo chmod 0750 /opt/inku /var/lib/inku /var/log/inku
```

環境に既存の`inku`ユーザーがいる場合は再作成しません。

## 4. コードを配置する

Gitを使う例:

```sh
cd /opt/inku
sudo -u inku git clone <repository-url> inku-lang
cd /opt/inku/inku-lang
```

rsyncを使う場合も、最終配置先を`/opt/inku/inku-lang/`とし、`.venv`、`node_modules`、build cacheを転送しません。本番サーバーのファイル交換方式とGit履歴管理を混同しないでください。

## 5. backendを準備する

lockfileに従って依存関係を同期します。

```sh
cd /opt/inku/inku-lang/server
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv sync --locked
```

SQLite DBのschema migrationと既存データbackfillは、backend初期化時に現行コードが実行します。更新前には必ずDBをバックアップしてください。

## 6. frontendを準備する

```sh
cd /opt/inku/inku-lang/web
sudo -u inku npm ci
sudo -u inku npm run check
sudo -u inku npm run build
```

参照systemd templateはVite開発サーバーを起動します。`npm run build`は配布物の型・production build検証であり、このtemplateの起動コマンドそのものではありません。

## 7. 環境変数を設定する

```sh
sudo cp /opt/inku/inku-lang/manual/ja/templates/inku-api.env.example /etc/inku/inku-api.env
sudo chown root:inku /etc/inku/inku-api.env
sudo chmod 0640 /etc/inku/inku-api.env
sudo editor /etc/inku/inku-api.env
```

最低限確認する項目:

```sh
INKU_SERVER_HOST=127.0.0.1
INKU_SERVER_PORT=8100
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
INKU_SECRET_KEY_FILE=/var/lib/inku/secret.key
INKU_BOOTSTRAP_ADMIN_PASSWORD=change-this-password
```

少なくとも一つのprovider keyを設定するか、初回ログイン後に管理UIから接続を登録します。

```sh
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
NVIDIA_API_KEY=
```

`INKU_BOOTSTRAP_ADMIN_PASSWORD`は8文字以上です。新規DBにユーザーがいない場合だけbootstrap adminを作成します。初回作成後は環境ファイルから削除するか、秘密管理システムへ移します。空文字は未設定と同じ扱いなので、行を削除しても空欄にしても構いません。

**この初回設定は省略できません。** inkuにはセルフサインアップがなく、アカウントを作れるのは認証済みのadminまたはgroup leadだけです。bootstrap adminなしで空のDBを起動したサーバーには、ログインする手段がありません。設定を忘れた場合は、passwordを設定して再起動すれば作成されます（ユーザーが0件のときだけ作成を試みるため、既存アカウントには影響しません）。

## 8. 手動起動で確認する

backend:

```sh
cd /opt/inku/inku-lang/server
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-server
```

別端末:

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
```

frontend:

```sh
cd /opt/inku/inku-lang/web
sudo -u inku npm run dev -- --host 0.0.0.0 --port 5173
```

```sh
curl -sS -I --max-time 5 http://127.0.0.1:5173/
```

確認後、手動プロセスを停止します。

## 9. systemdへ登録する

```sh
sudo cp /opt/inku/inku-lang/manual/ja/templates/systemd/inku-api.service /etc/systemd/system/inku-api.service
sudo cp /opt/inku/inku-lang/manual/ja/templates/systemd/inku-server.service /etc/systemd/system/inku-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
```

templateの`User`、`Group`、`WorkingDirectory`、`ExecStart`、`EnvironmentFile`は実環境に合わせます。`uv`と`npm`は絶対パスを確認してください。

```sh
command -v uv
command -v npm
systemctl status inku-api.service --no-pager
systemctl status inku-server.service --no-pager
```

## 10. 初回ログイン

1. `http://<server>:5173/`を開きます。
2. bootstrap adminでログインします。
3. `設定`からprovider接続、API key、公開モデルを確認します。
4. ユーザーとグループを作成します。
5. `モデル選択`でStage 1とStage 2を選びます。
6. 日本語と英語の短い記述をそれぞれ生成し、自動言語判定、履歴保存、SVG／PNG出力を確認します。

通常生成に指示文言語の手動選択はありません。入力から自動判定し、判定材料がない場合だけUI表示言語へfallbackします。

## 11. CLIを準備する

```sh
cd /opt/inku/inku-lang/cli
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv sync --locked
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli --base-url http://127.0.0.1:8100 me
```

## 12. 受け入れ確認

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
curl -sS -I --max-time 5 http://127.0.0.1:5173/
```

Web UIでは次を確認します。

- ログインとログアウト
- 日本語／英語記述の描画
- 写生（Stage 0.5）を`細かく`にして描き、左側に写生文が出ること
- 色カタログ、モデル、キャンバス、暴れるの選択
- 推敲の5要素（配置・読み取り・色カタログ・変奏・言葉でタッチ）とモデル比較
- 生成情報の詳細／プロンプト／JSON
- 履歴の時系列／系譜ごと表示、ハッシュ下位4桁での検索
- SVG／PNG書き出し、コンタクトシート、アニメーション
- 管理者は設定の`制限値`が表示され、保存できること

## 13. 更新手順

1. maintenance windowを確保し、DBと暗号化鍵をバックアップします。
2. 新しいコードを配置します。
3. backendとfrontendを検証します。

```sh
cd /opt/inku/inku-lang/server
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv sync --locked
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
```

```sh
cd /opt/inku/inku-lang/web
sudo -u inku npm ci
sudo -u inku npm run check
sudo -u inku npm run build
```

4. 変更対象サービスを再起動します。frontendとbackendの両方を更新した場合は両方を再起動します。

```sh
sudo systemctl restart inku-api.service
sudo systemctl restart inku-server.service
```

5. health check、ログ、実画面を確認します。migration失敗時に新旧コードを混在させないでください。

## 14. rollback

rollback前に、更新後DBが旧コードと互換かを確認します。schemaが進んだDBを無条件に古いコードへ戻さないでください。

1. サービスを停止します。
2. 更新前コードとDB backupを復元します。
3. `INKU_SECRET_KEY_FILE`を同じものへ戻します。
4. 依存関係を同期し、サービスを起動します。
5. health checkと履歴再現を確認します。

## 15. アンインストール

```sh
sudo systemctl disable --now inku-server.service
sudo systemctl disable --now inku-api.service
```

削除候補:

```text
/etc/systemd/system/inku-api.service
/etc/systemd/system/inku-server.service
/etc/inku/inku-api.env
/opt/inku/inku-lang
/var/lib/inku
/var/log/inku
```

DB、暗号化鍵、出力artifactを削除すると復旧できません。保持期限とbackup確認後に削除してください。

## 16. コンテナ実行

従来のuv、npm、systemd開発・運用手順は維持されています。コンテナ実行はrootの compose.yaml を使う追加経路です。

    export INKU_ORIGIN=http://localhost:5173
    export INKU_BOOTSTRAP_ADMIN_PASSWORD='replace-with-a-long-secret'
    docker compose build
    docker compose up -d
    docker compose ps

`INKU_BOOTSTRAP_ADMIN_PASSWORD` は必須です。値が無いまま `docker compose up` すると、containerを起動する前にcomposeが停止して不足を知らせます。空のdata volumeから起動したサーバーは、この管理者が唯一のログイン手段だからです。

Webは5173番portで公開し、Node serverが同一originの /api requestを内部FastAPI containerへproxyします。SQLite、backup、artifactは inku-data volumeに永続化されます。API containerは非root userで動作します。

初回admin作成に必要な環境変数やprovider keyはshell historyへ残さず、productionではCompose secretsまたは権限制限したenv fileから渡してください。TLS終端時は INKU_ORIGIN を公開HTTPS URLへ、INKU_SESSION_COOKIE_SECURE を1へ設定します。

停止は docker compose down、volumeを残した再作成は docker compose up -d --build です。docker compose down -v はDBを含むvolumeを破棄するため、backup確認なしに実行しないでください。
