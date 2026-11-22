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
curl -O https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/compose.https.yaml
curl -O https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/Caddyfile
curl -o .env https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/.env.example

# Fill in INKU_BOOTSTRAP_ADMIN_PASSWORD and your LLM API key.
# INKU_BOOTSTRAP_ADMIN_PASSWORD と LLM の API キーを記入する。
$EDITOR .env

docker compose up -d
```

Open <http://localhost:5173> and sign in as `admin` with the password from
`.env`. The API is published only on <http://127.0.0.1:8100> by default.

<http://localhost:5173> を開き、`admin` と `.env` に書いたパスワードでログインします。
API の既定の公開先は <http://127.0.0.1:8100> です。

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

## If nobody can sign in / ログインできなくなったとき

An administrator who forgets the password cannot recover it from the web UI, and
`.env` is not read again once the database holds an account. Reset the password
from inside the container and sign in with the new one. The command asks for it
twice and never takes it on the command line; `--password-stdin` reads it from
the first line of standard input instead. Naming no account resets the one
`INKU_BOOTSTRAP_ADMIN_USERNAME` created (`admin` unless it was changed), and an
unknown name prints the accounts that do exist.

パスワードを忘れた管理者は、Web UI から取り戻せません。`.env` はアカウントが
1 件でも在れば読まれないので、コンテナの中から再設定して、新しいパスワードで
ログインします。パスワードは 2 度尋ねられ、コマンドラインには置きません。
`--password-stdin` を付けると標準入力の 1 行目から読みます。アカウントを指定
しなければ `INKU_BOOTSTRAP_ADMIN_USERNAME` が作った管理者（変更していなければ
`admin`）が対象で、無い名前を指定すると在るアカウントを印字します。

```bash
docker compose exec api inku-admin reset-password --username admin
```

This is no new way in. Running it means holding the container, and holding the
container already means holding `/data/inku.db`; it spares the operator from
writing SQL by hand. Images from v2.13.41 onward carry the command.

これは新しい侵入口ではありません。実行できるのはコンテナを操作できる者だけで、
その者は既に `/data/inku.db` を読み書きできます。手で SQL を書く手間を省くための
ものです。**このコマンドを持つのは v2.13.41 以降のイメージです。**

## Data / データ

The API's persistent data — the SQLite database, generated outputs, database
backups — lives in the `inku-data` volume mounted at `/data`. Removing the
volume resets the server to a fresh install, including the accounts.

API の永続データ（SQLite データベース、生成物、バックアップ）は `/data` に
マウントされた `inku-data` volume にあります。この volume を削除すると、
アカウントを含めて初期状態に戻ります。

```bash
docker compose exec api ls /data          # inspect / 中身を見る
docker compose stop api                   # stop SQLite writers / DB 書込みを止める
docker run --rm -v inku_inku-data:/data -v "$PWD:/backup" \
  busybox tar czf /backup/inku-data.tar.gz -C /data .   # back up / 退避する
docker compose start api                  # resume / 再開する
```

Do not archive the volume while the API is running. SQLite may have committed
pages in its WAL, and a file-by-file archive is not one atomic database
snapshot. For a no-downtime database-only copy, run the manual backup from the
Server settings screen; it uses SQLite's Backup API and verifies the result.

API の稼働中に volume を archive しないでください。SQLite の確定済みページが
WAL に残っている場合、ファイルを順番に読む archive は DB 全体の同一時点snapshotに
なりません。停止時間なしで DB だけを退避する場合は、Server 設定画面の手動backupを
実行してください。SQLite Backup API で作成し、結果も検査します。

Back up the HTTPS deployment's `inku-caddy` volume separately. It holds
certificate keys and must be kept as private as the database. If it is lost,
clients using the local CA must install a new root.

HTTPS 構成では `inku-caddy` volume も別途バックアップします。証明書の秘密鍵が
含まれるため、DB と同じく秘密として扱ってください。失うとローカル CA を使う
端末には新しいルート証明書の導入が必要です。

## Pinning a version / 版を固定する

`INKU_IMAGE_TAG` selects the image tag; the default `latest` follows the newest
release. Set it to `2.4.0` for an exact version or `2.4` to take patch updates
only. Apply a change with `docker compose pull && docker compose up -d`.

`INKU_IMAGE_TAG` でイメージのタグを選びます。既定の `latest` は最新リリースに
追随します。`2.4.0` なら版を厳密に固定、`2.4` ならパッチ更新のみ追随します。
変更は `docker compose pull && docker compose up -d` で反映します。

## Serving over HTTPS / HTTPS で公開する

HTTP remains the default. For the bundled Caddy proxy, use Docker Compose
**2.24.4 or later** (the override uses `!override`). Download all four
Quickstart files, then add these two lines to `.env` and run `docker compose up -d`.

HTTP が既定です。同梱の Caddy で HTTPS を有効にするには、`!override` に対応する
**Docker Compose 2.24.4 以降**を使います。Quickstart の4ファイルを取得し、
`.env` に次の2行を追加して `docker compose up -d` を実行します。

```dotenv
COMPOSE_FILE=compose.yaml:compose.https.yaml
INKU_PUBLIC_HOST=inku.home.arpa
```

On Windows, use `;` between the Compose files. Set `INKU_PUBLIC_HOST` to the
single hostname or private IPv4 address clients actually open, without scheme
or port. Caddy publishes 80 (HTTP) and 443 (HTTPS) by default. The override
sets the Web origin, enables Secure cookies and removes the direct Web port.
Startup can briefly return 502 while the Web service finishes starting.

Windows では Compose ファイルを `;` で区切ります。`INKU_PUBLIC_HOST` には
実際に開くホスト名かプライベート IPv4 アドレスを1つ指定します。scheme とポートは
含めません。Caddy は既定で HTTP の80と HTTPS の443を公開します。上書き設定は
Web の origin を設定し、Secure cookie を有効にし、Web の直接公開を閉じます。
起動直後は Web が応答するまで短時間 502 が返る場合があります。

| Address / 接続先 | Certificates and ports / 証明書とポート |
|---|---|
| Private IPv4, localhost, or names under `.localhost`, `.local`, `.internal`, `.home.arpa` / プライベート IPv4、localhost、または左記の接尾辞の名前 | Caddy's local CA. Install its root on clients. You may set `INKU_HTTP_PORT` and `INKU_HTTPS_PORT` to other TCP ports. / Caddy のローカル CA。各端末でルートを信頼させます。HTTP・HTTPS のポートは左記の設定で変更できます。 |
| Public DNS name / 公開 DNS 名 | Public ACME certificate. Keep ports 80 and 443, and make the appropriate challenge port (80 or 443) reachable from the Internet. `/ca.crt` is unavailable. / ACME の公開証明書。ポートは80・443のままにし、認証に使う80または443をインターネットから到達可能にします。`/ca.crt` は使えません。 |

Public IP addresses and LAN-only names outside the local suffixes above are
outside this setup. See [Caddy's certificate requirements](https://caddyserver.com/docs/automatic-https#hostname-requirements).

公開 IP アドレスや、上のローカル用接尾辞に当てはまらない LAN 専用名はこの構成の
対象外です。[Caddy の証明書要件](https://caddyserver.com/docs/automatic-https#hostname-requirements)を参照してください。

### Trust the local CA / ローカル CA を信頼する

On the server, copy the public root certificate and read its SHA-256 fingerprint.
Transfer the certificate and verify the fingerprint against the server's value
through a trusted channel before installing. Clients can also fetch
`http://<host>[:port]/ca.crt`, but HTTP can be intercepted, so verify the
fingerprint before trusting that copy. When the device does not show SHA-256,
use the same OpenSSL command on the received file on a trusted computer.

サーバー上で公開ルート証明書をコピーし、SHA-256 指紋を確認します。証明書を
端末へ渡し、信頼できる経路で伝えたサーバー側の指紋と一致してから導入します。
`http://<host>[:port]/ca.crt` からも取得できますが、HTTP では差し替えられる
可能性があるため、信頼する前に指紋を照合してください。端末に SHA-256 が出ない
場合は、信頼できるコンピューターで受け取ったファイルに同じ OpenSSL コマンドを使います。

```sh
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .
openssl x509 -noout -fingerprint -sha256 -in root.crt
```

- macOS: Import into Keychain Access, open the certificate's Trust settings, and trust it for SSL. / キーチェーンアクセスに読み込み、証明書の信頼設定で SSL を信頼します。
- Windows: Import into Trusted Root Certification Authorities for the user or machine that runs the browser. / ブラウザを使うユーザーまたはコンピューターの「信頼されたルート証明機関」に読み込みます。
- iPhone/iPad: Install the downloaded certificate profile, then enable full trust under Settings → General → About → Certificate Trust Settings. / ダウンロードした証明書プロファイルをインストールし、「設定」→「一般」→「情報」→「証明書信頼設定」で完全な信頼を有効にします。
- Android: Use the device's security settings to install the file as a CA certificate. Menu names vary by device. / 端末のセキュリティ設定から CA 証明書としてインストールします。メニュー名は機種によって異なります。

The local root has no name constraints. Anyone with its private key could
impersonate arbitrary HTTPS sites to devices that trust it. Close inbound HTTP
for local-CA deployments once clients have the root, and remove the installed
root from clients when you retire the deployment. Use HTTPS or localhost in a
supporting browser to copy images to the clipboard or choose an export folder.

ローカルルートには名前の制約がありません。秘密鍵が漏れると、そのルートを信頼した
端末で任意の HTTPS サイトになりすませます。ローカル CA の構成では、全端末に
導入した後は外部からの HTTP を閉じられます。廃止時は端末からルートを削除します。
画像のクリップボードへのコピーや保存先フォルダの指定は、対応するブラウザで
HTTPS または localhost を使います。

### CLI access and rollback / CLI 接続と元に戻す方法

On the host, the CLI can use its default `http://127.0.0.1:8100`.
From another device, set `base_url` to the HTTPS origin and, for a local CA,
set `ca_file` to the trusted root. Query `inku-cli api GET /api/info`.
The Web service proxies `/api/`; `/health` is available only through the API directly.

サーバー自身では、CLI の既定 `http://127.0.0.1:8100` を使えます。他の端末では
`base_url` に HTTPS の origin を設定し、ローカル CA の場合は `ca_file` に
信頼済みルートを指定します。確認には `inku-cli api GET /api/info` を使います。
Web が中継するのは `/api/` で、`/health` は API へ直接接続した場合に使えます。

To return to HTTP, stop and remove Caddy with `docker compose rm -sf caddy`
while the override is still active. Remove the `COMPOSE_FILE` line and run
`docker compose up -d` to restore the HTTP defaults. Keep both named volumes.

HTTP に戻すには、上書き設定が有効なうちに `docker compose rm -sf caddy` で Caddy
コンテナを取り除きます。`.env` から `COMPOSE_FILE` の行を消し、
`docker compose up -d` で HTTP の既定へ戻します。両方の名前付き volume は保持します。

If you already operate a separate reverse proxy, you can use the base Compose
file with `INKU_ORIGIN` set to the public HTTPS URL and
`INKU_SESSION_COOKIE_SECURE=1`.

別のリバースプロキシを運用している場合は、基本の Compose ファイルで
`INKU_ORIGIN` に公開 HTTPS URL を、`INKU_SESSION_COOKIE_SECURE` に `1` を設定できます。

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
