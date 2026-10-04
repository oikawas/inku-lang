# Docker Desktop で始める（ChatGPTプラン・シングルユーザー）

自分の Mac（または Windows）の Docker Desktop で inku のコンテナを動かし、本人の ChatGPT サブスクリプションの利用枠（[ChatGPTプラン接続](chatgpt-plan.ja.md)）で描くまでの手順です。シングルユーザーモードで動かすので、ログイン画面もパスワードもありません。この PC の持ち主ひとりが使う構成です。

コンテナはリポジトリ直下の `compose.yaml` で、手元のソースからビルドします。シングルユーザーモードはこの compose の既定です。ChatGPT の認証には、同じソースを PC 側でも使います。GHCR のリリース版イメージと API キーで動かす場合は [`deploy/README.md`](../../deploy/README.md) を参照してください。そちらは通常のログイン方式です。

この手順は、コンテナで ChatGPT プランを使える版（v2.15.83 以降）を対象とします。

## 必要なもの

Mac:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（起動しておく）
- Git
- [`uv`](https://docs.astral.sh/uv/)（Homebrew なら `brew install uv`）。ChatGPT の認証を PC 側で行うのに使う
- Google Chrome または Brave。認証のときに、このブラウザで ChatGPT のサインイン画面が開く
- ChatGPT のサブスクリプション。アカウントごとの利用可否と使えるモデルは、実際に認可した後のモデル一覧で確かめる

Windows:

- Docker Desktop（WSL 2 バックエンド）と、WSL 2 の Linux（Ubuntu など）
- Docker Desktop の設定 Resources → WSL integration で、その Linux を有効にする
- 以下のコマンドはすべて WSL 2 の端末で実行する。Git と `uv` も WSL 2 の中に入れる

**Windows での ChatGPT の認証（手順 4）は未確認です。** 認証の処理は Mac と Linux 向けに作られており、Windows の Python では動きません。WSL 2 の中で実行し、ブラウザは Windows 側で開く手順を下に書きましたが、認証後の戻り先（WSL 2 の中の `127.0.0.1`）へ Windows のブラウザから届くかは確かめていません。手順 1〜3 と 5 は Mac と同じです。

API コンテナのメモリ上限は既定で 4 GB です（`INKU_API_MEM_LIMIT`）。Docker Desktop に割り当てたメモリがこれより少ない場合は、Docker Desktop の設定 Resources で増やします。

## 1. ソースを取得する

```sh
git clone https://github.com/oikawas/inku-lang.git
cd inku-lang
```

以下のコマンドは、特に断らない限りこのディレクトリで実行します。

## 2. `.env` を作る

ChatGPT プランは既定で無効です。コンテナで使うために、2 つの設定を `.env` に書きます。

```sh
cat > .env <<'EOF'
INKU_CHATGPT_PLAN_ENABLED=1
INKU_CHATGPT_SELF_HOSTED=1
EOF
```

シングルユーザーモード（`INKU_SINGLE_USER=1`）は `compose.yaml` の既定なので、書かなくてかまいません。シングルユーザーモードでは利用者のアカウントが自動で作られるので、`INKU_BOOTSTRAP_ADMIN_PASSWORD` も要りません。`.env` は Git の管理から外してあります。

## 3. ビルドして起動する

```sh
docker compose up -d --build
```

初回は Rust の共有コアもビルドするので、時間がかかります。起動したら確かめます。

```sh
docker compose ps
curl http://localhost:8101/health        # {"ok":true}
```

ブラウザで <http://localhost:5173> を開きます。ログイン画面は出ず、そのまま使えます。API は <http://localhost:8101> で応答します（リリース版の compose とは port が違います）。

## 4. ChatGPT と接続する

ChatGPT の認証は PC 側で行い、その結果を封印したファイルでコンテナへ渡します。コンテナの中ではサインイン画面からの戻りを受けられないためです。渡した後は、コンテナが認証を単独で持ちます。

### 4-1. 自分の ID を調べる

```sh
curl -s http://localhost:8101/api/auth/me
```

返ってきた JSON の `"id"` の値（`xxxxxxxx-xxxx-…` の形）を控えます。シングルユーザーモードなので、ログインせずに取得できます。

### 4-2. 受け取りの準備ファイルを作る

コンテナに、封印を受け取るための公開情報（recipient）を作らせます。`<自分のID>` を 4-1 の値に置き換えます。

```sh
umask 077
docker compose exec -T --user 10001:10001 api \
  inku-chatgpt recipient --owner-id <自分のID> > recipient.json
```

`recipient.json` の有効期限は 30 分です。4-3〜4-6 はこの時間内に済ませます。

### 4-3. PC 側の準備（初回だけ）

```sh
cd server
uv sync --frozen --inexact
```

### 4-4. ChatGPT にサインインして許可する

`server` ディレクトリのまま実行します。コンテナ用の認証は、PC のほかの認証と混ざらないよう専用の保存先（`~/.config/inku-chatgpt-container`）に置きます。

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  INKU_CHATGPT_AUTH_DIR="$HOME/.config/inku-chatgpt-container" \
  uv run --frozen --no-sync inku-chatgpt authorize --recipient ../recipient.json \
  --browser chrome --language ja --consent
```

Chrome で ChatGPT のサインインと利用の同意が開きます。Brave を使う場合は `--browser brave` にします。同意すると、最後に `"status"` と `"profile_id"` を含む 1 行の JSON が出ます。`profile_id` の値を控えます。

Windows（WSL 2）では `--browser chrome` の代わりに `--no-browser` を付けます。表示された URL を Windows のブラウザで開きます（未確認）。

### 4-5. 認証を封印する

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  INKU_CHATGPT_AUTH_DIR="$HOME/.config/inku-chatgpt-container" \
  uv run --frozen --no-sync inku-chatgpt export --recipient ../recipient.json \
  --profile-id <profile_id> --output ../sealed.json
cd ..
```

封印すると、PC 側の認証は消えます。以後の更新はコンテナだけが行います。

### 4-6. コンテナへ取り込む

```sh
docker compose exec -T --user 10001:10001 api inku-chatgpt import < sealed.json
rm recipient.json sealed.json
```

`"status":"imported"` が出れば完了です。2 つのファイルは役目を終えたので消します。

## 5. モデルを選んで描く

1. Web の設定で「ChatGPTプラン」タブを開き、「接続状態を確認」を押す。
2. 設定の「モデル設定」タブで「ChatGPTプラン」を選ぶ。「モデル選択」から「モデルリスト取得」を押し、描画に使うモデルにチェックを付けて保存する。公開先は自分だけです。
3. 制作画面の「モデル選択」で、ChatGPT プランのモデルを Stage 1/2 共通のモデルとして選ぶ。

短い記述を書いて描きます。利用枠を使い切ったときは、「ChatGPTプラン」タブの「利用枠を管理」から ChatGPT の利用状況を確かめ、回復してから「利用枠を確認して再試行」を押します。

## 止める・更新する・消す

```sh
docker compose stop                      # 止める
docker compose start                     # 再開する
git pull && docker compose up -d --build # 新しい版に更新する
```

作品の DB と ChatGPT の認証（`/data/chatgpt`）は、どちらも `inku-data` volume に残ります。止めても、コンテナを作り直しても消えません。`docker compose down -v` は volume ごと消すので、作品も ChatGPT の接続も失います。その場合は手順 4 からやり直します。

ChatGPT プランの仕組み、接続の解除、エラーの読み方は [ChatGPTプラン接続](chatgpt-plan.ja.md) にあります。
