# アプリケーションインストール

この文書は、inku を新しいサーバーへ展開するための標準手順です。OS は Linux、サービス管理は systemd、DB はまず SQLite を前提にします。必要に応じて PostgreSQL へ変更できます。

## 1. 構成

inku は 2 つのプロセスで動きます。

| プロセス | 役割 | 既定ポート |
|---|---|---|
| inku-api | FastAPI backend。認証、LLM 呼び出し、履歴 DB、SVG レンダリング | 8100 |
| inku-server | SvelteKit / Vite frontend。ブラウザ UI | 5173 |

Web UI は `/api` を backend へプロキシします。開発・参照運用では Vite server が `127.0.0.1:8100` の API へ接続します。

## 2. 前提ソフトウェア

サーバーへ以下をインストールします。

- Python 3.10 以上
- uv
- Node.js と npm
- Git または rsync などの配置手段
- systemd
- 任意: Cairo / PNG 変換に必要な OS パッケージ
- 任意: PostgreSQL

例:

```sh
python3 --version
uv --version
node --version
npm --version
```

## 3. アプリケーションを配置する

専用ユーザーを作成します。

```sh
sudo useradd --system --create-home --home-dir /var/lib/inku --shell /usr/sbin/nologin inku
sudo mkdir -p /var/lib/inku /var/log/inku /etc/inku
sudo chown -R inku:inku /var/lib/inku /var/log/inku
sudo chmod 0750 /var/lib/inku /var/log/inku
```

例として `/opt/inku/inku-lang` に配置します。

```sh
sudo mkdir -p /opt/inku
sudo chown inku:inku /opt/inku
cd /opt/inku
git clone <repository-url> inku-lang
cd inku-lang
```

rsync で配置する場合も、最終的なディレクトリ構成は同じにします。

```text
/opt/inku/inku-lang/
  server/
  web/
  cli/
  SPEC.ja.md
```

## 4. backend をセットアップする

```sh
cd /opt/inku/inku-lang/server
UV_CACHE_DIR=/tmp/inku-uv-cache uv sync
```

初回起動時に SQLite DB を作る場合は、管理者アカウント作成用の環境変数を設定します。

```sh
export INKU_BOOTSTRAP_ADMIN_USERNAME=admin
export INKU_BOOTSTRAP_ADMIN_EMAIL=admin@example.local
export INKU_BOOTSTRAP_ADMIN_PASSWORD='change-this-password'
```

`INKU_BOOTSTRAP_ADMIN_PASSWORD` は 8 文字以上が必要です。この変数が設定された新規 DB の場合だけ初期管理者が作られます。既存 DB にユーザーがいる場合は作成されません。

起動確認:

```sh
cd /opt/inku/inku-lang/server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-server
```

別端末で確認:

```sh
curl -i http://127.0.0.1:8100/health
```

## 5. frontend をセットアップする

```sh
cd /opt/inku/inku-lang/web
npm install
npm run check
npm run build
```

開発・参照運用として Vite server を使う場合:

```sh
npm run dev -- --host 0.0.0.0 --port 5173
```

確認:

```sh
curl -i http://127.0.0.1:5173/
```

## 6. CLI をセットアップする

CLI は任意です。サーバーの API を操作するために使います。

```sh
cd /opt/inku/inku-lang/cli
uv sync
uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
uv run inku-cli me
```

## 7. 環境変数ファイルを作る

テンプレートをコピーします。

```sh
sudo mkdir -p /etc/inku
sudo cp manual/ja/templates/inku-api.env.example /etc/inku/inku-api.env
sudo chmod 0600 /etc/inku/inku-api.env
sudo editor /etc/inku/inku-api.env
```

最低限必要な設定:

```sh
INKU_SERVER_HOST=127.0.0.1
INKU_SERVER_PORT=8100
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
INKU_SECRET_KEY_FILE=/var/lib/inku/secret.key
INKU_BOOTSTRAP_ADMIN_PASSWORD=change-this-password
```

AI provider を使う場合は、少なくとも 1 つの API key を設定します。

```sh
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
NVIDIA_API_KEY=
```

API key は環境変数で初期値として読み込まれます。管理者は Web UI の `設定` -> `モデル設定` から接続先、Base URL、API key、公開モデルを管理できます。DB に保存される API key は暗号化されます。

## 8. systemd サービスを登録する

テンプレートをコピーし、ユーザー名とパスを環境に合わせて編集します。

```sh
sudo cp manual/ja/templates/systemd/inku-api.service /etc/systemd/system/inku-api.service
sudo cp manual/ja/templates/systemd/inku-server.service /etc/systemd/system/inku-server.service
sudo editor /etc/systemd/system/inku-api.service
sudo editor /etc/systemd/system/inku-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
```

確認:

```sh
systemctl status inku-api.service --no-pager
systemctl status inku-server.service --no-pager
curl -i http://127.0.0.1:8100/health
curl -i http://127.0.0.1:5173/
```

## 9. 初回ログインとモデル設定

1. ブラウザで `http://<server>:5173/` を開きます。
2. 初期管理者でログインします。
3. `設定` -> `モデル設定` を開きます。
4. AI サービス接続で API key と Base URL を確認します。
5. 公開するモデルを選びます。
6. `モデル選択` から Stage 1 と Stage 2 のモデルを選びます。

Stage 1 は自由な記述を読む段階、Stage 2 は正規化DDLを JSON Score へ構造化する段階です。運用上は Stage 1 に高性能モデル、Stage 2 に軽量で安定したモデルを選ぶ構成が扱いやすいです。

## 10. 動作確認

Web UI で確認:

1. ログインします。
2. `山の向こうに月が昇る` と入力します。
3. `描画する` を押します。
4. SVG が表示され、履歴に追加されることを確認します。
5. SVG または PNG をエクスポートします。

API で確認:

```sh
curl -i http://127.0.0.1:8100/health
```

CLI で確認:

```sh
cd /opt/inku/inku-lang/cli
uv run inku-cli --base-url http://127.0.0.1:8100 paint "青い線を中央に三本置く" -o out --png --save-history
```

## 11. 更新手順

1. 新しいコードを配置します。
2. backend 変更がある場合:

```sh
cd /opt/inku/inku-lang/server
UV_CACHE_DIR=/tmp/inku-uv-cache uv sync
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
sudo systemctl restart inku-api.service
```

3. frontend 変更がある場合:

```sh
cd /opt/inku/inku-lang/web
npm install
npm run check
npm run build
sudo systemctl restart inku-server.service
```

4. health check とブラウザ確認を実施します。

```sh
curl -i http://127.0.0.1:8100/health
curl -i http://127.0.0.1:5173/
```

## 12. アンインストール

停止:

```sh
sudo systemctl disable --now inku-server.service
sudo systemctl disable --now inku-api.service
```

削除対象の例:

```text
/etc/systemd/system/inku-api.service
/etc/systemd/system/inku-server.service
/etc/inku/inku-api.env
/opt/inku/inku-lang
/var/lib/inku
/var/log/inku
```

DB と出力ファイルを消すと履歴は復元できません。削除前にバックアップしてください。
