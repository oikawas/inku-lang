# inku-cli リファレンス

inku-cliはWeb UIと同じ公開HTTP APIを操作するクライアントです。保存済みセッションを使い、`users`・`leaders`・`admins`のどの権限グループに属するかによる権限判定はサーバーが行います。

対象はinku v2.15.147（Web Build 1223）です。

## 基本操作

    cd cli
    uv run inku-cli --help
    uv run inku-cli login --base-url http://127.0.0.1:8100 -u USERNAME
    uv run inku-cli me
    uv run inku-cli version

各コマンドの完全な引数一覧は inku-cli COMMAND --help で表示できます。本書はコマンドの用途と、Web UIとの対応が分かりにくい旗だけを述べます。

| コマンド | 用途 |
|---|---|
| login / logout / me | セッションの開始、破棄、本人確認 |
| models | CLI既定の描画モデル（Stage 1/2共通）・Visionモデルと色カタログの設定 |
| paint / batch | 記述または指示書から単体・一括描画 |
| refine | 既存作品から要素（構図・色）を推敲し派生を生成・保存 |
| lineage | 作品の系譜（親・子・兄弟）ツリーの探索表示、中間ノードの昇格 |
| colophon | 起点から対象作品までの一本の枝を、追記専用の読みとして朗読 |
| inspect | 同一記述に対する複数モデルの解釈・描画の並列比較 |
| review | Vision による視覚的評価、および未読語フィードバック |
| render-score | Stage 1 / 2を通さずScore JSONを描画 |
| replay | 保存済み作品を現行engineで描き直して保存済みSVGと比較し、必要なら子として保存（Webの`再演`） |
| render-local | 指定checkoutのcoreでScoreをoffline描画・比較。サーバー接続・DB保存なし |
| demo-instruction | デモ用記述の生成 |
| history / history-export | 履歴一覧とhash指定の書き出し |
| unread-words | 本人の未読語台帳。管理者は --all で全体集計 |
| contact-sheet / analyze / ddl-compare | ローカル成果物の比較・解析 |
| rasterize | SVGのフォルダをPNGへ焼く。1ファイル1子プロセスで、`--workers` で同時に走らせる本数を決める |
| measure-raster | PNGのフォルダの判定量（画素数・地の色・薄い痕と濃い痕の割合・地からの平均距離・彩度のある痕）を数える。**渡された画像をその幅のまま数え、幅や尺度の旗を持たない。**別の幅で読み直したいときは`rasterize --width`でその幅に焼いてから数える。サーバーには繋がない |
| vision-review | 設定済みvision modelによる読み取り専用評価 |
| plugin | 宣言的DDLプラグインの一覧、検証、再読込 |
| reference | 実装内の語彙・定数テーブルの読み取り専用ダンプ |
| user / group | ユーザーアカウントとグループの管理 |
| config | サーバーのシステム設定の表示と更新 |
| api | 任意の公開APIをHTTP method指定で操作 |
| version | CLIと接続先serverのversion/build表示 |

## paint と batch の旗

paintとbatchは同じ旗を受け取ります。**旗を書かなければサーバーの既定が使われ、サーバーの既定はWeb UIの既定と同じとは限りません。**

### 入力と出力

JSON成果物は、その絵を描いたDDL層の版を `ddl_version` と `ddl_engine_version` に記録します。
制限値については、使われた値を `render_limits`、その出どころを `render_limits_source`（`work`＝作品の行、`settings`＝今日の設定、`request`＝今回の要求、`work_unrecorded`＝行はあるが制限値が記録されていない）に記録します。旧Score等の互換描画で効いた上限の痕は `render_limit_notes` に記録します。

| 旗 | 内容 |
|---|---|
| `--file FILE` / `-f` | 記述またはDDLをUTF-8ファイルから読む。paintは `-` で標準入力。batchは空行以外の1行が1作品 |
| `--out-dir DIR` / `-o` | JSON / SVG / PNGの出力先 |
| `--prefix P` | 出力ファイル名の接頭辞 |
| `--png` | `--out-dir` を指定したとき、PNGも書き出す |
| `--svg-profile {display,editable,compat,live}` | 保存するSVGのプロファイル |
| `--input-mode {paint,ddl}` | `paint` は記述をStage 1へ、`ddl` は可視DDLからcompile・必要な穴補完と演奏へ進む。各段の意味はSPECを参照 |
| `--ddl-text DDL` | **`render-score` 専用。**指示書をprovenance・hash metadataとして送る。DDLに基づく本数・関係の自動補修は行わない |
| `--ddl-file PATH` | **`render-score` 専用。**指示書をファイルから読む。`-` は標準入力。`--ddl-text` とは併用できない |
| `--save-history` | サーバーの履歴へ保存する |
| `--save-artifacts` / `--no-save-artifacts` | サーバー側の成果物保存の有無 |
| `--full-json` | 応答全体を印字する |
| `--no-progress` | 経過時間のアニメーションを止める |

### 写生（Stage 0.5）

| 旗 | 内容 |
|---|---|
| `--sketch` | 写生を有効にし、元の記述を残して場所と光を補って解釈へ渡す。サーバー・Web UIとも既定はなし（off）。現行選択はなし／あり（off/on） |
| `--sketch-grain {fine,coarse}` | 旧作品との互換用の旗。現行写生には使わない |
| `--sketch-text TEXT` | Stage 0.5を呼ばず、この写生文を使う（保存済みまたは手で直した写生の再演） |

変奏は廃止しました。旧強度・seedの旗は受け付けません。保存済みの変奏情報はDBに保持し、新しい描画要求へ渡しません。

### 演奏と色

| 旗 | 内容 |
|---|---|
| `--wild` | 筆致の振幅の天井を外す。`paint`／`batch`のDDL入力でも有効 |
| `--color-catalog ID` | サーバーの色カタログID |
| `--catalog-id ID` | `--color-catalog` の旧名 |
| `--catalog-mode {fixed,auto,random}` | `fixed` は `--color-catalog` を使う、`auto` はサーバーが記述を読んで選ぶ、`random` は `--color-catalog` 以外から引く |
| `--from-work WORK_ID` | `render-score` 専用。**その作品が描かれた当時の色と制限値で描く**（カタログの今日の定義でも今日の設定でもなく、作品の行に記録された値を使う）。**改名・引退したカタログの作品も描ける。**`--color-catalog` / `--catalog-id` とは併用できない |
| `--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}` | キャンバスの比率 |

### seed と再現

| 旗 | 内容 |
|---|---|
| `--render-seed SEED` | 演奏のseed。同じseedと同じScoreなら同じ絵になる |
| `--composition-seed SEED` | 墨を置く位置のseed。省略すると配置は`--render-seed`に従う（render engine 23〜） |
| `--limits KEY=VALUE ...` | `paint`／`batch`（`--input-mode ddl`を含む）と`render-score`で、その描画の上限を指定する。要素ごとにサーバーの現行設定と小さいほうを採り、管理者の上限を越えない。省略すれば要求に送らない。通常pipelineで効く四つの値と旧互換値の区別は[サーバー設定§5.1](server-configuration.md#51-制限値)を参照 |

### モデルと言語

| 旗 | 内容 |
|---|---|
| `--stage1-provider` / `--stage1-model` | 両段に使う描画モデルの接続先とモデル |
| `--instruction-lang {auto,ja,en}` | 記述の言語 |
| `--ui-lang LANG` | UI言語として記録する値 |
| `--include-thinking` | 思考出力を応答に含める |

batchはさらに `--continue-on-error` を持ちます。

DDL入力へ筆致と今回の上限を指定する例です。

```sh
uv run inku-cli paint --input-mode ddl --file work.ddl --stage1-model chatgpt:gpt-6-luna --wild --limits max_expanded_primitives=200
```

## サーバーなしで描画する（render-local）

サーバーへ接続せず、指定した製品checkout（または必要なsourceを含むgit-archive）のcoreでSVGと任意のPNGを作ります。`core/rust-toolchain.toml`の固定Rust toolchainとCargo依存を事前に用意してください。毎回offlineの差分buildでsourceとの鮮度を確認し、不足時には依存を自動取得せず止まります。

```sh
# (a) history-exportの個別作品JSONから保存条件を継承
uv run inku-cli render-local --core-root /path/to/inku-lang \
  --from-work-file exported-work.json -o replay.svg --png replay.png
# (b) Score単体。保存時の色・seed等は必要に応じて明示
uv run inku-cli render-local --core-root /path/to/inku-lang \
  --file score.json -o rendered.svg --color-map colors.json --render-seed 123
```

どちらの入力も、`resource_policy.hard_policy`と`resource_policy.operational_budget`を持つ現行のcompile済みScoreが必要です。旧Score一般を自動移行するコマンドではありません。(a)は作品の色map・seed・canvas・profile・wild・制限値を継承し、保存SVGがあればbyte比較します。(b)は指定しなかった条件にcoreの既定を使います。`--limits`は四つのreplay上限だけを受け、Scoreの保存hard policyを越える指定は拒否します。`--compare-svg FILE`で別のSVGとも比較できます。標準出力のJSONにhash、時間、採用条件、checkoutのHEAD／dirty状態等を記録します。DBへは保存しません。異なるsource／条件での一致は保証しません。

## 保存済み作品を再演する（replay）

Webの`再演`と同じく、保存済み作品の保存済みScoreと記録された条件（render seed、配置seed、色、キャンバス、wild、制限値）を、サーバーの現行engineで描き直します。CLI側のseed・色・キャンバスは送りません。render seedの記録が無い古い作品は仮seed 0で描き、出力の`provisional_render_seed`が`true`になります。

```sh
# 比較だけ（保存しない）。保存済みSVGと描き直しを書き出す
uv run inku-cli replay WORK_ID --out-dir replay-out --png
# 描き直しを元作品の子として保存する（Webの「描き直しを子として保存」と同じ。生成回数は増えない）
uv run inku-cli replay WORK_ID --save-child
```

標準出力のJSONに、保存時と現行のengineの版（`recorded_render_engine_version`・`render_engine_version`・`version_changed`）、`render_hash`、描き直しと保存済みSVGのSHA-256と、両者がbyte一致したか（`svg_equal`）を記録します。`--save-child`では、サーバーが元作品からもう一度描き、表示した描き直しと一致したときだけ子として保存し、子の`child_id`を返します。一致しなければ409で保存しません。

## 履歴とフィードバック

| コマンド | 主な旗 |
|---|---|
| `history` | `--limit` / `--offset` / `--query` / `--starred` / `--for-revision` / `--for-share` / `--no-svg`（作品の絵を一覧に含めません。`svg`は空文字で返ります） |
| `history-export` | `--from` / `--to`（hash下位桁の範囲）/ `--out-dir` / `--columns` / `--thumb-size` / `--starred` / `--for-revision` / `--for-share` |
| `unread-words` | `--all`（管理者のみの全体集計）/ `--limit` |
| `history share` | `--to-user` / `--to-group`（どちらか一方）/ `--permission {read,write}` |
| `history unshare` | `--to-user` / `--to-group`（どちらか一方） |
| `history acl` | （引数は作品IDのみ）いま誰がその作品を見られる／変えられるかを表示します |
| `history peers` | （旗なし）自分と同じ組織グループの利用者をIDつきで一覧します |
| `history state` | `--bytes`（応答が届いた実バイト数を添えます）。作品の総数と、最新の作品の時刻とIDだけを返します。**作品の絵は1バイトも読みません**ので、一覧を取り直す前に「変わったかどうか」だけを安く確かめられます |

`--for-revision` は推敲マークの付いた作品だけに絞ります。スターとは別の印です。
`--for-share` は、所有者が組織グループへ開いた作品だけに絞ります。これも別の印で、3つは併用できます。

    uv run inku-cli history share WORK_ID --to-user USER_ID --permission read
    uv run inku-cli history share WORK_ID --to-group GROUP_ID --permission write
    uv run inku-cli history unshare WORK_ID --to-user USER_ID
    uv run inku-cli history acl WORK_ID
    uv run inku-cli history peers

共有できるのは**作品の持ち主と`admins`だけ**です。**読めることは渡せることではありません。**
宛先はIDで指定します。IDは `history peers` で調べられます。`--permission` の既定は `read` で、
`write` を渡すとその作品の星付け・ゴミ箱への移動・削除もできるようになります。
共有された作品は自分の履歴一覧に現れ、他人のものだと分かる印が付きます。

## プラグインと参照

| コマンド | 内容 |
|---|---|
| `plugin list` | ロード済み／拒否されたプラグイン文書、namespace、version、拒否理由をJSONで取得する |
| `plugin validate FILE` | ローカルの文書本文を管理APIへ送り、コードや外部ファイルを実行せず構文検証する |
| `plugin reload` | サーバーを再起動せず `server/plugins/` を明示再読込する |
| `reference [--md \| --json] [-o FILE]` | 実装内の語彙・定数テーブルの機械生成ダンプ。既定はMarkdown |

`plugin` は管理者セッションを必要とします。`reference` はログイン済みセッションで実行できます。

## 奥書

    uv run inku-cli colophon ITEM_ID --language ja --dry-run

起点から対象作品までの一本の枝を、vision対応モデルが世代順に一人称で読みます。通常は署名付きの奥書を追記保存し、`--dry-run` は保存せず標準出力だけを行います。`--vision-model` で読み手を選べます（`--model` は旧名）。

奥書は評価・選別のコマンドではありません。生成、推敲、枝の選択へ接続してはいけません。

## 管理

| コマンド | 内容 |
|---|---|
| `user list / create / update / delete` | ユーザーアカウントの管理 |
| `group list / create / update / delete` | ユーザーグループの管理 |
| `config show` | サーバーのシステム設定を表示する |
| `config update` | サーバーのシステム設定を更新する |
| `single-user show` | 単独利用モードのサーバーがどのアカウントで開くか、ほかに誰を選べるかを表示する |
| `single-user set USER_ID` | 開くアカウントを移す（移す先は `admins` に属している必要があります） |

`user` と `group` は`admins`または`leaders`、`config` は`admins`のセッションを必要とします。`user create` の権限グループは `--permission-group {users,leaders,admins}` で指定し、複数回渡せます。既存の制限値、ログ保存ポリシー、DBバックアップ設定は `config` の対象です。描画の並列度には専用の旗がないので、[サーバー設定§2.3](server-configuration.md#23-artifactと同時実行)の`api GET/PUT /api/settings/render-concurrency`を使います。

## 全公開APIの操作

専用コマンドがないAPIは api で呼び出します。pathは /api/... または /health の相対pathだけを受け付け、別hostへの転送は拒否します。

    uv run inku-cli api GET /api/color-catalogs
    uv run inku-cli api GET /api/history --query limit=20 --query starred=true
    uv run inku-cli api PATCH /api/auth/me/settings --data '{"ui_theme":"dark"}'
    uv run inku-cli api POST /api/history/trash --file ids.json
    uv run inku-cli api DELETE /api/history --header X-Inku-Confirm=permanent-delete-trash
    uv run inku-cli api GET /api/history/WORK_ID/svg --query profile=editable --output work.svg

--data と --file は同時指定できません。JSON以外のresponseは --output へ保存できます。認証不要endpointには --no-auth を指定できます。

権限はGUIと同一です。`users`だけを持つ利用者は本人の作品・設定と、**自分に共有された作品**、`leaders`は同一グループの利用者管理と**自分の組織の作品**、`admins`はserver設定、全ユーザー管理、全体未読語集計、**全作品**を操作できます。権限グループの外の呼び出しは403、未ログインは401です。**見えない作品を名指しした書き込みは403ではなく404、または「0件」を返します** —— 403は「その作品は在る」と教えてしまうためです。

保存系APIを再試行する場合は、同じ Idempotency-Key を指定すると作品と系譜の二重保存を防げます。

    uv run inku-cli api POST /api/history --file work.json --header Idempotency-Key=import-20260715-001

### 409の承認・作者編集待ちから続ける

`paint`／`batch`が`pipeline_patch_approval_required`または`pipeline_author_action_required`で409になったら、同じ生成を再送せず、応答の`detail.current_view`を確認します。`pipeline_variation_id`／`pipeline_execution_id`が対象です。以下の`VARIATION_ID`／`EXECUTION_ID`と`REVISION`は、その応答または最新viewの`variation_id`／`execution_id`／`authority.revision`へ置き換えます。revisionは10進文字列のまま使います。

```sh
uv run inku-cli api GET /api/pipeline/variations/VARIATION_ID
```

`busy`がfalseになってから操作します。`phase.tag=awaiting_patch_approval`なら、現在の`document.source`と`phase.candidate.source`／`phase.patch`を読み、採用する場合だけ`phase.proposal_digest`を`DIGEST`へ写して送ります。

```sh
uv run inku-cli api POST /api/pipeline/executions/EXECUTION_ID/commands \
  --data '{"tag":"approve_patch","expected_revision":"REVISION","proposal_digest":"DIGEST"}'
```

採用せず自分で直す場合は、同じendpointへ`{"tag":"decline_patch","proposal_digest":"DIGEST"}`を送り、最新viewを読みます。`needs_user_edit`などで編集する場合も、`document`があれば`document.source`を元にDDL全文を直し、なければ作者がDDL全文を書きます。次の内容をUTF-8の`author-ddl.json`へ保存して送ります。

```json
{"expected_revision":"REVISION","source":"修正したDDL全文"}
```

```sh
uv run inku-cli api POST /api/pipeline/executions/EXECUTION_ID/author-ddl --file author-ddl.json
uv run inku-cli api GET /api/pipeline/variations/VARIATION_ID
```

編集応答が新しいvariation／executionを返した場合は以後そのIDを使います。GETを間隔を空けて繰り返し、`busy=false`かつ`phase.tag=score_ready`で`delivery`があることを確認して演奏します。承認後にも同じ確認が必要です。

```sh
uv run inku-cli api POST /api/pipeline/executions/EXECUTION_ID/commands --data '{"tag":"perform"}'
uv run inku-cli api GET /api/pipeline/variations/VARIATION_ID
```

`busy=false`で`result`が出るまでpollし、完成結果を確認します。再び承認・編集待ちなら該当手順へ戻り、`failed`／`cancelled`なら止めます。`authority_conflict`／`stale_result`の409では`current_view`を読み直し、古いrevisionやdigestを再送しません。承認・編集・演奏は同じログイン利用者のexecutionに対して行います。


## AI自律および作品品質向上のためのコマンド

AIエージェントによる自動生成、評価、および系譜ツリーを辿った自律的な推敲ループで使用可能な専用コマンドです。実行手順は`inku-cli AI自律運転・テスト用リファレンス`が持ちます。

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

### 2. 推敲と派生生成 (refine)
既存作品を親ノードとして紐付け、局所的な別案を生成・保存します。

* **推敲候補の自動生成**:
  ```sh
  uv run inku-cli refine perform WORK_ID --kind layout -o ./refinements --png
  ```
  `--kind` に `layout` (構図), `color` (配色カタログ) のいずれかを指定し、別案を生成してサーバーに保存します。`-o` が指定された場合はローカルファイルとしても書き出します。どちらも Web の推敲と同じく、元の作品の保存した指示書（DDL）から描き、記述を読み直しません。`layout` は指示書の範囲を新しい配置の seed で選び直し、`color` は保存した Score を別の色カタログで描きます。DDLを編集した作品も同じように推敲できます。写生は元の作品の写生文をそのまま引き継ぎ、写生を呼び直しません。`--no-save` を付けると保存しません。
* **手動候補の系譜保存**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "入力記述"
  ```
  ローカルで調整したScore JSONを、親ノードに接続した派生（子）としてサーバー履歴へ直接インポートします。

### 3. 多モデル並列比較 (inspect)
同一の記述に対して、複数のモデルがどのように解釈（DDL）および描画するかを並列で実行し、比較します。

今後の実providerテスト・比較はPrimaryをChatGPTプラン / GPT-6-Luna、SecondaryをGemini API（Cloud）/ Gemma 4 31B ITとし、NVIDIA NIMを対象・対照・fallback・Vision評価へ含めません。[AI向けテスト手順](cli-reference-for-ai.md)に従い、接続失敗時は止めます。

```sh
uv run inku-cli inspect "青い線を引く" --models "chatgpt:gpt-6-luna,gemini:gemma-4-31b-it" -o ./inspection --png
```

### 4. 視覚的評価とフィードバック (review)
Visionモデルによる自律的な出来栄え評価、および解釈に自信のなかった語彙のサーバー通知を行います。

* **Vision による画の評価**:
  `review evaluate`と`vision-review`はNIM専用の製品機能です。次の例はその機能の説明であり、今後のテスト・比較・Vision評価には使いません。`--model`だけを別providerの参照へ替えても送信先は変わりません。
  ```sh
  uv run inku-cli review evaluate drawing.png --model VISION_MODEL
  ```
  描画された画像を Vision LLM に送信し、余白、コントラスト、表現などの観点から点数評価および一文フィードバックを取得します（provider側のAPIキー設定が必要）。
* **未読語のフィードバック登録**:
  ```sh
  uv run inku-cli review unread "薄墨" --context "薄墨の地に円を描く"
  ```
  AIが正しく変換できなかった語彙と文脈を、サーバーの未読語台帳へ通知・登録します。
