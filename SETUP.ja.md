# inku セットアップ手順

この文書は、配布用ソースパッケージから `inku` のサーバー、Web UI、CLI を起動するための手順である。

## 配布パッケージの内容

配布用ソースtarballは、Git管理対象の公開ソースだけを含む。

含まれるもの:

- `server/`: FastAPI backend
- `web/`: SvelteKit frontend
- `cli/`: `inku-cli`
- `shared/`: server と CLI が共有するパッケージ
- `manual/`: 利用マニュアル
- `docs/`: 補助資料
- `android/`: Android アプリ
- `compose.yaml`, `server/Dockerfile`, `web/Dockerfile`, `.dockerignore`: ソースからコンテナを組む定義
- `deploy/`: リリース版イメージで配置するための compose と手引き
- `README*.md`, `SPEC*.md`, `SETUP*.md`, `CHANGELOG*.md`, `PROJECT_CONTEXT*.md`, `PLUGIN.md`, `LICENSE`

含まれないもの:

- `no-git-sync/`
- `server/reference/`（版ごとに凍結した開発用参照コーパス）
- `.env` / `.env.local`
- APIキー、ローカルユーザー情報、ローカルサーバー情報
- SQLite DB、履歴データ、生成画像、`cli/out/`
- `node_modules/`, `.venv/`, build cache

## 必要な環境

ソースから動かす場合:

- Python 3.12 以上（`server` / `cli` とも `requires-python = ">=3.12"`）
- `uv`
- Node.js 20 以上を推奨
- npm
- SVGからPNGを生成する場合、`resvg-py`（`uv sync` で入る）

コンテナで動かす場合:

- Docker Engine と Docker Compose v2

### PNG出力について

PNG変換は **resvg だけで行う。フォールバックは無い**。resvgが入っていない環境では、PNG出力は静かに劣化するのではなく例外で停止する。

以前はCairoSVGがうしろに控えていたが、CairoSVGは `feTurbulence` / `feDisplacementMap` / `feGaussianBlur` を実装しておらず、**失敗もせずに落とす**。地の粒も材質フィルタ（pencil / crayon / chalk / brush_thick）も消えたPNGが、見た目はきれいなまま返っていた。誤った絵を黙って返すラスタライザは、無いものより悪い。使われているバックエンドとその版は、サーバー起動時のログに1度だけ出力される。

## 展開

```sh
tar xzf inku-lang-source-<build>.tar.gz
cd inku-lang-source-<build>
```

## git clone から作業する

`web/BUILD_NUMBER` は共有のカウンタなので、
2 つの枝が両方とも採番したことは食い違いではない — 大きいほうの番号が答えである。
これを自動で解く merge driver は版管理されない `.git/config` に置く決まりなので、
clone の直後に実行する。

```sh
scripts/git/setup.sh
```

worktree は `.git/config` を共有するので、1 回で全部に効く。実行を忘れた clone でも、
リポジトリ直下の `make test` / `make test-server` / `make test-cli` / `make test-web` が
テスト開始前に同じ設定を冪等に適用する。

## コンテナで動かす

コンテナで動かす道は2つある。**配置の正本は [`deploy/README.md`](deploy/README.md)** であり、初回アカウント・データ永続・版固定・HTTPS・ログの詳細はそちらにある。

### リリース版イメージを取得する（ビルドしない）

リリース版はGHCRのコンテナイメージ（`ghcr.io/oikawas/inku-api` / `ghcr.io/oikawas/inku-web`、amd64 / arm64）で配布している。この道ではソースをビルドしないため、本tarballも不要である。

```sh
mkdir inku && cd inku
curl -O https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/compose.yaml
curl -o .env https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/.env.example
$EDITOR .env   # INKU_BOOTSTRAP_ADMIN_PASSWORD（8文字以上）とLLMのAPIキーを記入
docker compose up -d
```

Web UIは `http://localhost:5173`、APIは `http://localhost:8100` で応答する。`admin` と `.env` に書いたパスワードでログインする。

### このソースからビルドする

tarballの直下にある `compose.yaml` は、`server/Dockerfile` と `web/Dockerfile` を使って手元のソースからイメージを組む。開発中の版を確認する場合に使う。

```sh
INKU_BOOTSTRAP_ADMIN_PASSWORD='change-this-password' docker compose up -d --build
```

Web UIは `http://localhost:5173`、APIは既定で `http://localhost:8101` に公開される（`INKU_WEB_PORT` / `INKU_API_PORT` で変更できる）。DBは `inku-data` volumeに永続する。

**`INKU_BOOTSTRAP_ADMIN_PASSWORD` は必須である。** どちらのcomposeも、この変数が空のままでは起動を拒否する。理由は次節に書いたとおりで、セルフサインアップがないため初期管理者なしではログインする手段がない。

以下はソースから直接動かす手順である。

## サーバーのセットアップ

```sh
cd server
uv sync
```

初回起動時に管理者ユーザーを作成するため、8文字以上のパスワードを環境変数で指定する。

```sh
export INKU_BOOTSTRAP_ADMIN_PASSWORD='change-this-password'
```

inku にはセルフサインアップがなく、アカウントを作れるのは認証済みの管理者だけである。**この初期管理者なしで空の DB を起動すると、ログインする手段がない**。設定を忘れた場合は、パスワードを設定して再起動すれば作成される。既にユーザーがいる DB では何も起きないため、既存のパスワードが上書きされることはない。空文字は未指定と同じ扱いになる。
このパスワードを失った場合、Web UI からは取り戻せず、`.env` も読まれない。`inku-admin reset-password` がサーバー自身の環境の中から再設定する —— コンテナなら `docker compose exec api inku-admin reset-password --username admin`、このディレクトリからなら `uv run inku-admin reset-password --username admin` である。新しいパスワードは2度尋ねられ、`--password-stdin` を付けると標準入力の1行目から読む。実行できるのはサーバーのコンテナかそのファイルを握っている者で、その者は既にDBを握っている。

必要に応じてSQLite DBの保存先を指定する。`INKU_DB_URL`が受け付けるのはSQLite URLだけで、非SQLite URLはengine作成前に拒否される。未指定の場合は、ユーザーのローカルデータディレクトリ配下にSQLite DBが作成される。

```sh
export INKU_DB_URL='sqlite:///./inku.db'
```

APIキーは環境変数、または起動後に管理者ユーザーでWeb UIのモデル設定から登録する。Web UIから登録したAPIキーはDB内に暗号化して保存され、画面には再表示されない。

```sh
export OPENAI_API_KEY='...'
export ANTHROPIC_API_KEY='...'
export GEMINI_API_KEY='...'
export NVIDIA_API_KEY='...'
```

サーバーを起動する。

```sh
uv run inku-server
```

既定では `http://127.0.0.1:8100` で起動する。変更する場合は以下を使う。

```sh
export INKU_SERVER_HOST='0.0.0.0'
export INKU_SERVER_PORT='8100'
uv run inku-server
```

ヘルスチェック:

```sh
curl http://127.0.0.1:8100/health
```

## Web UI のセットアップ

別のターミナルで実行する。

```sh
cd web
npm install
npm run dev
```

開発サーバーは既定で `http://127.0.0.1:5173` を使う。Vite設定により、Web UIからの `/api` リクエストは `http://127.0.0.1:8100` のAPIサーバーへ転送される。

本番相当のビルド確認:

```sh
npm run check
npm run build
```

## ローカル Ollama を provider として使う

inku は [Ollama](https://ollama.com) へ OpenAI 互換のローカル endpoint として接続できる。これは、Ollama の導入・起動、モデル取得、接続先、段ごとの割り当てを利用者が別途管理する構成であり、**inku 全体を API キーや認証設定なしで利用できるという意味ではない。** 以下で実測済みなのは Stage 1 / Stage 2 の組み合わせだけである。Vision も Ollama が画像入力を扱える対応モデルなら同じ互換経路を使えるが、現在の検証済みローカルカタログには Vision モデルを収録しておらず、標準構成として保証しない。

### 1. コンテキスト長を広げる

Ollama を導入したうえで、コンテキスト長を指定する。**Stage 2 のプロンプトは 12,000〜14,600 トークンあり、短いコンテキストでは入りきらない。あふれた分は黙って捨てられ、応答は返るのに指示の大半が読まれていない状態になる。**

```sh
export OLLAMA_CONTEXT_LENGTH=16384
```

### 2. モデルを 2 つ取得する

**段によって適したモデルが違うため、Stage 1 と Stage 2 に別々のモデルを割り当てる。**

```sh
ollama pull qwen3.5:4b-q4_K_M                      # Stage 1（3.4GB）
ollama pull ministral-3:8b-instruct-2512-q4_K_M    # Stage 2（6.0GB）
```

合計 9.4GB。**両方が同時に常駐する**ので、メモリはその分を見込む。

**タグは量子化まで書く。** `qwen3.5:4b` のような素タグは上流で中身が差し替わり、モデル一覧の説明と結びつかなくなる。

### 3. 接続先を指す

既定の接続先は `http://localhost:11434/v1` で、同じ機体で動かすなら設定は要らない。変える場合は次を使う。

```sh
export OLLAMA_BASE_URL='http://localhost:11434/v1'
```

**コンテナで動かす場合、コンテナ内の `localhost` はコンテナ自身を指す**ので、ホストで動く Ollama へは届かない。`.env` でホストを名指しする。

```sh
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

`host.docker.internal` の解決は `deploy/compose.yaml` が引き受けているので、この 1 行だけでよい。

### 4. 段ごとに割り当てる

管理者でログインし、モデル設定で次のように選ぶ。

| 段 | プロバイダー | モデル |
| --- | --- | --- |
| Stage 1 | Ollama | `qwen3.5:4b-q4_K_M` |
| Stage 2 | Ollama | `ministral-3:8b-instruct-2512-q4_K_M` |

### この組み合わせの理由

**Stage 1**（記述を指示書へ読み解く段）は、語彙の外へ出ない文を書けるかで決まる。日本語と英語の両方で成立したのは `qwen3.5:4b-q4_K_M` だけで、しかも候補中で最も小さい。**大きいほど良いという順にはならない。**

**Stage 2**（指示書を JSON Score へ組む段）は、記述した文がいくつ図形の指示まで届くかで決まる。`ministral-3:8b-instruct-2512-q4_K_M` が最も多くを運ぶ。

モデル設定の一覧には、計測した 10 本それぞれについて、この 2 つの観点で分かったことが説明として付いている。手元にある別のモデルを選ぶ場合はそちらを見る。

**GPU は要らないが、あった方がよい。** CPU だけでも動く。1 枚あたりの待ち時間は機体で大きく変わる。

## CLI のセットアップ

別のターミナルで実行する。

```sh
cd cli
uv sync
```

CLIは既定で `http://127.0.0.1:8100` に接続する。別のAPIへ接続する場合は `--base-url` または `INKU_BASE_URL` を使う。

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 me
```

描画例:

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 paint "白い余白に、黒い線を一本だけ置く。"
```

履歴に保存する場合:

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 paint "青い円を右上に置く。" --save-history
```

## 代表的な環境変数

| 変数 | 用途 |
| --- | --- |
| `INKU_DB_URL` | SQLite DB接続先。非SQLite URLはengine作成前に拒否。未指定時はローカルSQLite |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | 新規DB作成時の初期管理者パスワード。ログイン手段を得るために必須。空文字は未指定と同じ |
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | 初期管理者名。未指定時は `admin` |
| `INKU_SECRET_KEY` | APIキー暗号化用秘密鍵 |
| `INKU_SECRET_KEY_FILE` | 秘密鍵ファイルの保存先 |
| `INKU_SERVER_HOST` | `inku-server` のlisten host |
| `INKU_SERVER_PORT` | `inku-server` のlisten port |
| `INKU_BASE_URL` | `inku-cli` の既定API URL |
| `INKU_STAGE_WORKERS` | Stage 1 / Stage 2 LLM呼び出しの同時実行数 |
| `INKU_OUTPUT_DIR` | 自動保存出力先 |
| `INKU_OUTPUT_PNG_SIZE` | 自動保存PNGのY軸サイズ |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Claude API key |
| `GEMINI_API_KEY` | Gemini API key |
| `NVIDIA_API_KEY` | NVIDIA API key |
| `OLLAMA_BASE_URL` | ローカル Ollama の接続先。未指定時は `http://localhost:11434/v1` |
| `OLLAMA_CONTEXT_LENGTH` | Ollama 側で指定するコンテキスト長。inku は読まない。**Stage 2 のプロンプトが入る長さが要る** |

コンテナで動かす場合のみ使うもの:

| 変数 | 用途 |
| --- | --- |
| `INKU_IMAGE_TAG` | `deploy/compose.yaml` が取得するイメージのタグ。未指定時は `latest`。版を固定する場合に使う |
| `INKU_WEB_PORT` | ホスト側へ公開するWeb UIのport。未指定時は `5173` |
| `INKU_API_PORT` | ホスト側へ公開するAPIのport。未指定時は `deploy/compose.yaml` で `8100`、ソースからビルドする `compose.yaml` で `8101` |
| `INKU_ORIGIN` | Web UIのorigin。未指定時は `http://localhost:5173` |

## 注意

- 配布tarballには秘密情報を含めない。
- `.env` を使う場合はローカルで作成し、配布物やGitに含めない。
- DB、履歴、生成画像は実行環境ごとのデータであり、ソースパッケージには含めない。
- Web UIを外部公開する場合は、TLS、Cookie secure設定、リバースプロキシ、ファイアウォール、ユーザー管理を運用環境に合わせて設定する。コンテナの場合は [`deploy/README.md`](deploy/README.md) の「Serving over HTTPS」に手順がある。
- `.env` はcomposeが読むファイルでもある。配布物やGitに含めない点は同じである。
