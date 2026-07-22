# Deploying inku / inku を配置する

Released container images are published to GHCR as
`ghcr.io/oikawas/inku-api` and `ghcr.io/oikawas/inku-web`. Nothing needs to be
built locally, and the repository does not need to be cloned.

リリース版のコンテナイメージは GHCR に `ghcr.io/oikawas/inku-api` と
`ghcr.io/oikawas/inku-web` として公開されます。ローカルでのビルドも、
リポジトリの clone も必要ありません。

## Quickstart / 手早く始める

```bash
mkdir inku && cd inku
curl -O https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/compose.yaml
curl -o .env https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/.env.example

# Fill in INKU_BOOTSTRAP_ADMIN_PASSWORD and your LLM API key.
# INKU_BOOTSTRAP_ADMIN_PASSWORD と LLM の API キーを記入する。
$EDITOR .env

docker compose up -d
```

Open <http://localhost:5173> and sign in as `admin` with the password from
`.env`. The API answers on <http://localhost:8100>.

<http://localhost:5173> を開き、`admin` と `.env` に書いたパスワードでログインします。
API は <http://localhost:8100> で応答します。

## The first account / 最初のアカウント

inku has no self-service registration. The first startup of an empty database
creates one administrator from `INKU_BOOTSTRAP_ADMIN_PASSWORD`, and every later
account is made by that administrator from the web UI. Compose therefore
refuses to start while the variable is blank.

inku にはセルフサインアップがありません。空のデータベースで初回起動したときだけ、
`INKU_BOOTSTRAP_ADMIN_PASSWORD` から管理者が 1 人作られ、以後のアカウントは
その管理者が Web UI から作ります。そのため、この変数が空のままでは compose は
起動を拒否します。

The password is read only while the database has no accounts. Changing it later
in `.env` does not change an existing password — use the web UI for that.

このパスワードはアカウントが 0 件のときだけ読まれます。後から `.env` を書き換えても
既存のパスワードは変わりません。変更は Web UI から行ってください。

## Data / データ

Everything that persists — the SQLite database, generated outputs, database
backups — lives in the `inku-data` volume mounted at `/data`. Removing the
volume resets the server to a fresh install, including the accounts.

永続する情報（SQLite データベース、生成物、バックアップ）はすべて `/data` に
マウントされた `inku-data` volume にあります。この volume を削除すると、
アカウントを含めて初期状態に戻ります。

```bash
docker compose exec api ls /data          # inspect / 中身を見る
docker run --rm -v inku_inku-data:/data -v "$PWD:/backup" \
  busybox tar czf /backup/inku-data.tar.gz -C /data .   # back up / 退避する
```

## Pinning a version / 版を固定する

`INKU_IMAGE_TAG` selects the image tag; the default `latest` follows the newest
release. Set it to `2.4.0` for an exact version or `2.4` to take patch updates
only. Apply a change with `docker compose pull && docker compose up -d`.

`INKU_IMAGE_TAG` でイメージのタグを選びます。既定の `latest` は最新リリースに
追随します。`2.4.0` なら版を厳密に固定、`2.4` ならパッチ更新のみ追随します。
変更は `docker compose pull && docker compose up -d` で反映します。

## Serving over HTTPS / HTTPS で公開する

Put a reverse proxy in front, then set `INKU_ORIGIN` to the public URL and
`INKU_SESSION_COOKIE_SECURE=1`. `INKU_ORIGIN` must match the URL browsers
actually use, otherwise the web UI rejects form submissions.

リバースプロキシを前段に置き、`INKU_ORIGIN` に公開 URL を、
`INKU_SESSION_COOKIE_SECURE=1` を設定します。`INKU_ORIGIN` はブラウザが実際に
使う URL と一致していなければならず、ずれると Web UI が送信を拒否します。

## Logs and health / ログと死活

```bash
docker compose ps
docker compose logs -f api
curl http://localhost:8100/health        # {"ok":true}
curl http://localhost:8100/api/info      # name, version, build_number
```

`web` waits for the `api` healthcheck before starting, so a slow first boot
shows `web` as `created` for a few seconds.

`web` は `api` の healthcheck を待って起動するため、初回起動が遅いときは数秒間
`web` が `created` のままになります。
