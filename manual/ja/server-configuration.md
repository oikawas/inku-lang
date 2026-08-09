# サーバー設定方法

この文書は、未リリース版inku v2.11.17（Web Build 873）を継続運用する管理者向けの設定基準です。環境変数template、現行DB schema、Web管理UI、systemd参照templateを対象にします。

## 1. 設定の優先境界

設定は三つの境界に分かれます。

1. OS／service設定: `/etc/inku/inku-api.env`、systemd、reverse proxy、filesystem権限
2. 管理者設定: provider接続、公開モデル、制限値、DB backup、artifact、ログ方針、ユーザー管理
3. ユーザー設定: Stage 1／2モデル、UI言語、UIモード、テーマ、キャンバス、色カタログ、写生、暴れる、保存先フォルダ、履歴選択動作

API keyの環境変数は初期値です。管理UIでDBへ保存したprovider keyがある場合は暗号化して利用します。ホスト固有情報と秘密をGit追跡文書へ書かないでください。

**環境変数が種を与えるだけの設定があります。**描画の並列度と制限値は、初回起動時に環境変数から初期値を取り、以後はDBの設定が正本になります。環境変数を変えても、既に保存された設定は変わりません。管理UIか `inku-cli config update` で変更してください。

## 2. backend環境変数

### 2.1 listen、DB、session

| 変数 | 目的 | 既定値 |
|---|---|---|
| `INKU_SERVER_HOST` | `inku-server` CLIのlisten host | `127.0.0.1` |
| `INKU_SERVER_PORT` | FastAPI port | `8100` |
| `INKU_SERVER_RELOAD` | uvicorn reload | `0` |
| `INKU_DB_URL` | SQLAlchemy DB URL | user data dir内SQLite |
| `INKU_SECRET_KEY` | provider key暗号化の直接鍵材料 | 未設定 |
| `INKU_SECRET_KEY_FILE` | 暗号化鍵ファイル | user data dir内`secret.key` |
| `INKU_SESSION_COOKIE_MAX_AGE` | session有効秒数 | 2592000 |
| `INKU_SESSION_COOKIE_SECURE` | Secure cookie | `0` |
| `INKU_MAX_REQUEST_BODY_BYTES` | request body上限 | 16777216 |
| `INKU_MAX_CONCURRENT_REQUESTS` | 同時HTTP request上限 | 64 |
| `INKU_LOGIN_RATE_ATTEMPTS` | login失敗許容回数／window | 10 |
| `INKU_LOGIN_RATE_WINDOW_SECONDS` | login rate window秒 | 60 |
| `INKU_CORS_ORIGINS` | 許可originのcomma区切り | localhostのみ |
| `INKU_LISTEN_HOST` | uvicorn listen host | `0.0.0.0` |
| `INKU_LISTEN_PORT` | uvicorn listen port | `INKU_SERVER_PORT`、無ければ`8100` |
| `INKU_ENV` | 動作モードの表示と開発時分岐 | `development` |
| `INKU_TIMEZONE` | DB backupの時刻判定などに使うtimezone | `Asia/Tokyo` |
| `INKU_REDIS_URL` | 設定するとrate limitなどの共有状態をRedisへ置く | 未設定（プロセス内） |

`INKU_SECRET_KEY`と`INKU_SECRET_KEY_FILE`を同時に設定した場合は直接鍵を優先します。本番では永続的な鍵ファイルを推奨します。

`INKU_LISTEN_HOST`／`INKU_LISTEN_PORT`はuvicornが直接読む値、`INKU_SERVER_HOST`／`INKU_SERVER_PORT`は`inku-server` CLIの値です。名前が似ているので取り違えないでください。

`INKU_REDIS_URL`はredis-pyが入っている場合にだけ有効です。設定しなければ共有状態はプロセス内に置かれるので、backendを複数プロセスで動かす構成では設定してください。

### 2.2 bootstrap admin

| 変数 | 目的 |
|---|---|
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | 初期管理者名 |
| `INKU_BOOTSTRAP_ADMIN_EMAIL` | 初期管理者email |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | 初期管理者password |
| `INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN` | 8文字未満のpasswordを許す。**本番で設定しない** |
| `INKU_AUTH_LOCAL_ENABLED` | ユーザー名とpasswordによるログイン（既定 `true`） |
| `INKU_AUTH_GOOGLE_ENABLED` | Googleによるログイン（既定 `false`） |

passwordが設定され、DBにユーザーがいない場合だけ作成します。8文字未満は拒否されます。初回作成後は秘密を環境から除去します。

空文字は未設定と同じ扱いです。env fileの空欄も、composeの `${INKU_BOOTSTRAP_ADMIN_PASSWORD:-}` 補間が渡す空値も、起動を失敗させません。初回作成後に環境から除去する際は、行を削除しても空欄にしても同じ結果になります。

inkuにはセルフサインアップがありません。アカウントを作れるのは認証済みのadminまたはgroup leadによる `POST /api/users` だけです。したがって**空のDBをbootstrap adminなしで起動すると、誰もログインできないサーバーになります**。復旧はpasswordを設定して再起動するだけです。bootstrap adminはユーザーが0件のときだけ作成を試みるため、既存アカウントのpasswordが上書きされることはありません。

### 2.3 artifactと同時実行

| 変数 | 目的 | 既定値 |
|---|---|---|
| `INKU_OUTPUT_DIR` | SVG／JSON／PNG artifact保存先 | user data dir内`outputs` |
| `INKU_OUTPUT_PNG_SIZE` | 自動保存PNGの辺長 | `2160` |
| `INKU_OUTPUT_SAVE_WORKERS` | artifact保存worker数 | `2` |
| `INKU_OUTPUT_SAVE_QUEUE_LIMIT` | artifact保存queue上限 | `32` |
| `INKU_STAGE_WORKERS` | LLM pipeline worker数 | `4` |
| `INKU_STAGE_QUEUE_LIMIT` | pipeline queue上限 | worker数の2倍 |
| `INKU_RENDER_CONCURRENCY` | 同時Renderer実行上限の初期値 | 2 |
| `INKU_CLIENT_FANOUT_LIMIT` | ブラウザが同時に投げる描画要求の上限の初期値 | `4` |
| `INKU_DB_BACKUP_SCHEDULER` | `0` にすると定期backupのschedulerを起動しない | `1` |

queue上限時も履歴DB保存を優先し、artifact保存だけをskipします。providerの無料queueによる遅延と、server worker不足を区別してください。

`INKU_RENDER_CONCURRENCY`と`INKU_CLIENT_FANOUT_LIMIT`は**初期値だけを与えます**。以後の正本はDBの設定で、管理UIの`その他（サーバー）`または `inku-cli config update` から変更します。サーバー同時描画数を超えた要求は待たずに503で拒否され、クライアントが短い間隔で再試行します。

### 2.4 LLM retryとtimeout

| 変数 | 目的 | 実装既定値 |
|---|---|---|
| `INKU_LLM_REQUEST_TIMEOUT_SECONDS` | provider HTTP timeout | `120` |
| `INKU_LLM_RETRY_ATTEMPTS` | 総試行回数 | `4` |
| `INKU_LLM_RETRY_BASE_DELAY` | 初期待機秒 | `2.0` |
| `INKU_LLM_RETRY_MAX_DELAY` | 最大待機秒 | `20.0` |
| `INKU_LLM_RETRY_JITTER` | jitter | `0.25` |
| `INKU_STAGE1_HARD_TIMEOUT_SECONDS` | Stage 1 hard timeout | `120` |
| `INKU_STAGE2_HARD_TIMEOUT_SECONDS` | Stage 2 hard timeout | `120` |
| `INKU_SKETCH_HARD_TIMEOUT_SECONDS` | 写生（Stage 0.5）のhard timeout | `120` |

配布templateは運用例としてretry値を明示しています。実装既定値とtemplate値を意識して変更してください。

hard timeoutは段の実行枠を取れなかった場合にも効きます。Stage 1が時間内に答えなかったときは定型の代替DDLで演奏し、その旨を作品へ記録します。写生が時間内に答えなかったときは記述をそのまま解釈へ渡します。

### 2.5 層とプラグイン

| 変数 | 目的 | 既定値 |
|---|---|---|
| `INKU_LLM_BACKEND` | LLMの接続系統 | `anthropic` |
| `INKU_DOCUMENT_PLUGIN_DIR` | 宣言的プラグイン文書の置き場 | `server/plugins/` |
| `INKU_OKUGAKI_MODEL` | 奥書の読み手モデルの既定 | vision対応モデル |
| `INKU_OKUGAKI_CACHE_TTL_SECONDS` | 奥書cacheの保持秒数 | `1800` |
| `INKU_OKUGAKI_CACHE_MAX_ENTRIES` | 奥書cacheの最大件数 | `256` |
| `INKU_LEARNED_FILE` | 学習語の保存先 | `/tmp/inku-learned.json` |
| `INKU_COERCE_DISABLE` | coerce（自動補正）を止める。**診断専用** | 未設定 |
| `INKU_DEVELOPER_MODE` | 開発者向けの追加表示 | 未設定 |

`INKU_LEARNED_FILE`の既定は`/tmp`配下なので、再起動で消えます。永続化する場合は安定したパスを指定してください。

`INKU_COERCE_DISABLE`は自動補正を丸ごと止めます。不可視色の可視化も過密の抑制も効かなくなるので、**本番では設定しないでください**。切り分けのための旗です。

### 2.6 provider

| Provider | API key | Base URL |
|---|---|---|
| OpenAI API Platform | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| Gemini | `GEMINI_API_KEY` | `GEMINI_BASE_URL` |
| NVIDIA NIM | `NVIDIA_API_KEY` | `NVIDIA_BASE_URL` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` |
| Ollama Cloud | `OLLAMA_CLOUD_API_KEY` | `OLLAMA_CLOUD_BASE_URL` |

providerのBase URL、key、公開モデルは管理UIからも設定できます。keyをDBへ保存する場合は`enc:v1:`形式で暗号化します。

## 3. DBとmigration

### 3.1 SQLite

```sh
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
```

SQLiteは単一server向けの参照構成です。履歴検索はFTS5を使用し、利用できない環境では`LIKE`へfallbackします。

backend起動時に、column追加、index、FTS、lineage rootなどのmigration／backfillを実行します。起動前にDB backupを作成し、migration中は複数versionのbackendを同時起動しないでください。

### 3.2 PostgreSQL

```sh
INKU_DB_URL=postgresql://inku:<password>@127.0.0.1/inku
```

DB URLを含む環境ファイルはrootとservice groupだけが読める権限にします。SQLite固有のWeb backup機能はPostgreSQLでは使わず、DB製品のbackup手段を使います。

### 3.3 履歴、系譜、同一性

DBは次を分離して保存します。

- description hash: 正規化した記述の同一性（`dh1:`）
- render hash: Renderer出力editionの同一性（`rh3:`。`rh2:`は旧版で、保存済み作品のために残っています）
- history ID: 通常履歴項目
- lineage node ID: 制作過程のnode

`rh3`のcanonical payloadは、Score、`render_seed`、`render_wild`、render engineのIDと版、色カタログIDです。`composition_seed`とBuild番号は含みません。**payloadの鍵名は同一性の材料なので、表示上の都合で改名しないでください。**改名すると保存済み作品のhashが全部作り直しになります。

系譜は明示的な制作操作だけで接続します。類似、同一記述、時刻からedgeを推測しません。通常履歴を完全削除しても、系譜の経路を保つためcontent-free tombstoneが残る場合があります。

## 4. 認証、role、scope

| role | 権限 |
|---|---|
| `admin` | provider、server、DB、log、ユーザー／group管理 |
| `group_lead` | 所属scope内のユーザー管理 |
| `user` | 生成と自分の履歴・設定管理 |

生成、履歴、系譜、設定APIは認証とuser scopeを確認します。他userのroot、作品、件数を返さないことを受け入れ試験へ含めてください。

## 5. モデルと言語

| 段階 | 役割 |
|---|---|
| Stage 0.5 | 記述を物の言葉へ写した自然文にする。任意の層でLLMを使う |
| Stage 1 | 記述または写生文を指示書（正規化DDL）へ解釈 |
| プラグイン展開 | 名前空間付きプラグイン語をコアDDLへ決定的にwriting-down |
| Stage 1.5 | DDLを決定的に展開し関係を与える。LLMではない |
| Stage 2 | DDLをJSON Scoreへ構造化 |
| coerce | drop-onlyを優先する境界処理 |
| Renderer | ScoreをSVGへ演奏 |

Stage 0.5が動いたとき、**写生文は記述の代わりに三つの消費者へ届きます** — Stage 1、プラグイン展開の発動判断、Stage 1.5です。層が答えなかった場合は記述をそのまま渡し、`sketch_state`へ`fallback`を記録します。層を通さなかった作品は`off`、この列より前の作品は値を持ちません。**値がないことは`off`ではありません。**

通常生成の`instruction_lang`はWeb UIから常に`auto`です。serverは入力から日本語／英語を判定し、判定材料がないときだけ`ui_lang`へfallbackします。APIは互換性と比較実行のため`auto`、`ja`、`en`を受け付けます。

解決結果は`instruction_lang_requested`、`instruction_lang_resolved`、`ui_lang`へ記録します。これらは現行render hash canonical payloadへ含めません。

### 5.1 制限値

一枚の作品が何本の墨を持てるかを決める九つの数です。速度の調整ではなく、描かれる線の数そのものが変わります。管理UIの`制限値`タブか `inku-cli config update` で変更し、**Stage 1／Stage 2のプロンプトへ書き込まれて、描いた作品ごとに記録されます。**

| 群 | 値 | 既定 | 内容 |
|---|---|---|---|
| 実際に描かれる数 | `max_expanded_primitives` | 400 | 一枚あたりの墨の数。超えると作品全体を縮めて収める |
| | `max_expanded_per_instruction` | 240 | 一つの指示あたりの墨の数。超えたら間引く |
| | `max_instructions` | 64 | 一枚あたりの指示の数。超えた指示は切り捨てる |
| 述べた数の扱い | `literal_count_threshold` | 240 | これ未満なら述べた数をそのまま描く。これ以上は群れとして見せる |
| | `represented_count_min` | 80 | 群れとして見せるときの下の端 |
| | `represented_count_max` | 120 | その上の端 |
| 読み取りと検証の天井 | `ddl_count_max` | 1000 | 記述の中の数字をここまでに丸める。Stage 1に教える密度の帯の上端でもある |
| | `ddl_count_max_grid` | 2000 | 文字どおりの格子だけは、通常の配置より高いところまで許す |
| | `schema_count_max` | 2000 | Stage 2が返した数がこれを超えていたら切り詰める |

互いに矛盾する値は拒否せず丸めます。代表化の上限がliteralの閾値を超えていれば閾値まで下げる、といった具合です。管理UIに表示されるのは丸めたあとの、実際に効いている値です。

**制限値は安定性、データ量、機種性能のための定数ガードです。**記述にないものを足すためにも、記述にあるものを引くためにも使いません。

## 6. Rendererと再現性

`render_seed`はタッチ、`composition_seed`は配置、`variation_seed`は変奏、`interpretation_seed`は読み取りの再現補助です。render engine 23以降、配置は`composition_seed`が決め、省略したときだけ`render_seed`に従います。判定は`is not None`なので、`0`は「指定なし」ではなく0というseedです。`seed_text`は明示語を決定的にhashし、Rendererのperformance seedだけへ作用します。解釈、DDL、JSON Score、配置へ作用させません。

`variation_seed`は`variation_amplitude`と揃って初めて効きます。片方だけでは展開層の軸は動きません。

`render_wild`は作品全体に効き、`rh3`の材料に入ります。同じScore・同じseedでも、暴れるの有無が違えば別のeditionです。

履歴再現では保存済みScore、色カタログ、キャンバス、seed、render engine versionを使用します。engine変更後のbit一致を保証するのではなく、version情報を監査可能にします。

## 7. artifact保存

履歴DBが正本です。artifactは再構築可能な副産物です。

```text
<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>...
```

保存対象とqueue設定は管理UIのserver設定から変更できます。出力先を変更した場合はservice userのwrite権限を確認します。

## 8. backupと復旧

最低限のbackup対象:

| 対象 | 理由 |
|---|---|
| DB | 履歴、系譜、ユーザー、設定の正本 |
| `INKU_SECRET_KEY_FILE` | provider key復号に必須 |
| `/etc/inku/inku-api.env` | runtime設定 |
| systemd／reverse proxy | service復旧 |
| artifact | 再生成可能だが運用上必要な場合 |

SQLite backup directoryは`INKU_DB_BACKUP_DIR`で変更できます。Web管理UIの手動／定期backupには世代管理があります。外部backupも併用し、DBと暗号化鍵を同じ復旧点で保管します。

復旧試験では、ログイン、provider key復号、履歴表示、lineage edge、SVG再現を確認します。

## 9. log

参照先:

```text
/var/log/inku/inku-api.log
/var/log/inku/inku-server.log
```

systemd journalとappend fileの両方を使うtemplateです。

```sh
journalctl -u inku-api.service -n 100 --no-pager
journalctl -u inku-server.service -n 100 --no-pager
```

管理UIのlog policy（有効／保存日数／周期／圧縮）は**アプリ自身が実行します**。書き出し先は`INKU_LOG_DIR`（既定は`~/.local/share/inku/logs`、コンテナ配布版は`/data/logs`）で、回転・圧縮・古い世代の削除もアプリが行います。logrotateの設定は不要です。**同じ行が標準出力にも出続けます**ので、`journalctl`とコンテナの`docker logs`はこれまでどおり使えます。コンテナ配布版では、daemonが標準出力から集めるぶんの上限を`compose.yaml`の`logging`が持ちます。

## 10. systemd

参照template:

- [inku-api.service](./templates/systemd/inku-api.service)
- [inku-server.service](./templates/systemd/inku-server.service)

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
sudo systemctl status inku-api.service --no-pager
sudo systemctl status inku-server.service --no-pager
```

参照frontend serviceは`NODE_ENV=development`でViteを起動します。公衆向けproduction構成ではそのまま使わず、production adapter、process起動方法、static asset、proxy timeoutを設計します。

## 11. reverse proxyとcookie

最小route:

- `/` -> `http://127.0.0.1:5173/`
- `/api/` -> `http://127.0.0.1:8100/api/`
- 必要なら`/health` -> `http://127.0.0.1:8100/health`

公開環境ではHTTPSを終端し、`INKU_SESSION_COOKIE_SECURE=1`を設定します。LLM生成は長時間になる場合があるため、proxy timeoutをprovider timeoutより短くしすぎないでください。

## 12. health checkと監視

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
curl -sS -I --max-time 5 http://127.0.0.1:5173/
```

Web proxy経由の認証経路:

```sh
curl -sS -i --max-time 5 \
  -X POST http://127.0.0.1:5173/api/auth/login \
  -H 'Content-Type: application/json' \
  --data '{"username":"admin","password":"wrong"}'
```

誤ったpasswordで401ならWebからAPIまで到達しています。監視ではHTTP statusに加え、service restart、worker queue、provider error、artifact queue skip、DB backup成功を観測します。provider待ち時間は品質指標に使いません。

## 13. 障害対応

| 症状 | 確認 |
|---|---|
| loginできない | bootstrap条件、user状態、cookie secure、DB接続 |
| 生成できない | provider key、Base URL、公開モデル、Stage logs |
| 日本語／英語を誤判定する | 入力に言語文字があるか、`ui_lang` fallback、生成情報の実使用言語 |
| 履歴が見えない | user scope、通常／trash、時系列／系譜filter |
| 系譜が切れる | 親候補保存失敗、lineage migration、tombstoneを確認 |
| 画像は出るがartifactがない | queue skip、出力先権限、worker数 |
| provider keyを復号できない | `INKU_SECRET_KEY_FILE`が同じ復旧点か |
| 起動後にDB error | migration log、DB backup、複数version同時起動を確認 |
| 描画が503で拒否される | サーバー同時描画数の設定。環境変数ではなくDBの設定が正本 |
| 数を書いたのに減る | 制限値の`literal_count_threshold`と`represented_count_*` |
| 写生が効いていない | 作品の`sketch_state`。`fallback`ならStage 0.5のtimeoutとprovider |
| プラグイン語が展開されない | `plugin list`の拒否理由、`INKU_DOCUMENT_PLUGIN_DIR`、`plugin reload` |

## 14. セキュリティ基準

- provider key、DB password、bootstrap passwordをGitへcommitしない。
- 環境ファイルはrootとservice groupだけが読めるようにする。
- 暗号化鍵を永続化し、DBとは別媒体にもbackupする。
- 公開環境ではHTTPS、Secure cookie、reverse proxyのrequest size／timeout制限を設定する。
- service userへ不要なshell、sudo、他user dataのread権限を与えない。
- backupとlogに入力文やmetadataが含まれる前提でaccess controlを行う。
- user削除、履歴完全削除、鍵rotationは復旧手順を準備してから実施する。
