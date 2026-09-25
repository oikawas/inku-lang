# 既知の差異と未確認事項

## 仕様・実装の不一致

### F-01 Render Engine版（調査中に解消）

- 調査開始時の `PROJECT_CONTEXT.ja.md` はRender Engine 28と記し、実装29と不一致だった。
- その後、公開commit `8b4d43cc` で同文書が29へ更新され、`render_engines/default.py` と `server/reference/render-engine-29/manifest.json` に一致した。
- 判定: **現在は解消済み**。本書群のsnapshotも更新後commitへ合わせた。

### F-02 Android仕様メモの版記述（再発）

- 2026-08-24に冒頭を当時の実装へ同期したが、現行の冒頭（最終更新 2026-09-25）は`2.1.4-android.80`、render engine `67`、DDL engine version `20`、serverの`ddl_engine_version` 21と記す。
- 実装はRender Engine `68`（`core/crates/inku-render/src/lib.rs`）、`ddl_engine_version` `47`（`layer_versions.py`）で、Androidは同じ共有Rust pipelineを使う。
- 判定: **版の数字が古い**。engine identityはKotlin製品定数でなく同梱native libraryから読むため、runtimeの挙動ではなく文書の差異である。

### F-03 Android外部provider実行

- Android仕様メモの「未実装」節は、外部provider executionを未実装とし、provider recordをcompatibility data structuresと記す。
- 現行 `RoutingModelProvider` はenabled providerを解決し、`GeminiModelProvider`と`OpenAiCompatibleProvider`へ接続する。共有pipelineのprovider effectは`SingleAttemptModelEffectProvider`がこれらへ送る。同じ仕様メモの前半もGeminiとOpenAI互換への要求条件を記している。
- 判定: **「未実装」節が古い**。Anthropic固有protocolの実装は確認できず、全providerの同等性は主張しない。

### F-04 Stage 1.5の長い旧説明（解消）

- 旧snapshotでは `SPEC.ja.md` §12.11が、数学・音楽・絵画候補を追加する旧設計を詳述していた。
- 現行の§12.11は、`CanonicalReady`のtyped meaningだけを受けて焦点と明示変奏だけを変えるtyped transformationとして書き直されている。
- 判定: **解消済み**。

### F-05 Project Contextに残る古い記述

- `PROJECT_CONTEXT.ja.md`の「版」表はRender Engine `66`、DDL `ddl_version` 11 / `ddl_engine_version` 45、Android `2.1.4-android.78`と記す。実装は68、13 / 47、`2.1.4-android.80`である。
- 同書のandroid節は「AndroidとServerは同じ共有Rust render engine `42`、AndroidのDDL engineは`20`」「Stage 1 / 1.5 / 2、Score coerce、Room、履歴、`rh3` identityはAndroid hostが所有」と記すが、Androidは共有Rust pipelineへ移っている（同書の「パイプラインの各層」節は現行を記す）。
- 同書の検査面は現役corpusを`render-engine-42`（610件）と`ddl-engine-20`（49件）、「再生成のバイト一致をCIが強制」と記す。実装の最新凍結はRender Engine 66（620件）とDDL engine 45（3件）で、corpus比較は手動dispatchだけのworkflowである（`server/reference/README.md`は明示checkpoint以外で生成・比較しない方針を記す）。
- 同書の「決定的な層」に削除済みの`coerce/`（観測互換だけが残る）と`ddl_expander.py`が残り、「RAW trace（`include_trace`）」の記述も残る。現行の互換投影は`include_trace`をpipelineへ渡さず、traceを返さない。
- 同書の語彙節は正本を`schema.py`と`saijiki.py`とするが、同じ書の設計契約節と実装は共有coreの`saijiki-v1.json`を正本とする。
- 判定: **Project Contextの一部が実装より古い**。本書群は実装と、実装に一致するSPEC・reference READMEに従った。

### F-06 route数の検査定数

- 静的な数え上げでは、10 routerの94 endpointと`/api/pipeline`の11 endpointで計105である。
- `test_route_authorization.py`の`EXPECTED_ROUTE_COUNT`は95で、そのコメントは`/api/pipeline/*`の追加と`/api/prompts`の削除を記録していない。`tests/data/api-surface-baseline.json`も95 operationで、退役済みの`/api/prompts`を含み`/api/pipeline/*`を含まない。
- `/api/pipeline/*`は2026-09-13（`2ad24df9`）に加わり、`/api/prompts`は2026-09-14（`03bbd686`）に削除された。
- 判定: **検査定数とbaselineが現行routeと食い違う**と推定する。本調査はnative wheelの無い環境でapp importが失敗したため、live routeの数え上げと当該testの実行はしていない。

### F-07 札だけの記述の門

- `SPEC.ja.md` §12.16は、描く3経路（`/api/interpret`・`/api/paint`・`/api/paint/stream`）が行頭番号と角括弧注記を切った結果が空の記述を400で断り、空白だけを422で断ると記す。
- 現行Serverには切除の実装（旧`description_labels.py`）が無く、記述はそのまま共有pipelineへ渡る。422の空白判定だけが`PaintRequest`に残る。Webは`description-labels.ts`で送信可否を判定し、そのコメントは削除済みのServer fileを正本として名指す。
- 判定: **仕様と実装が異なる**。Web以外のclient（CLI等）から札だけの記述を送った場合の扱いは、仕様の400ではない。

### F-08 streamの進行event

- `SPEC.ja.md` §12.10は、`POST /api/paint/stream`が`sketch`・`stage1`・`score`・`done`の順に進行を知らせると記す。
- 現行の互換streamは、共有pipelineの実行が落ち着いた後に最終結果を`done` 1行だけで返す。補完案の承認待ちはstream開始前の409で届く。進行はWebの`/api/pipeline` viewが読み直しで表示する。
- 判定: **仕様と実装が異なる**。

### F-09 実装内の古い説明文

- `core/crates/inku-pipeline/README.md`は「effect tagは4つ」「candidate APIは既存runtimeを切り替えない」「既存のruntime promptは変わらない」と記す。実装のeffectは`generate_sketch`を加えた5つで、共有pipelineが通常runtimeである。
- `persistence/variation_authority.py`のmodule docstringは「通常のServer runtimeはこれらの表をimportもinstallもしない」と記すが、`pipeline_runtime.py`が通常serviceの保存先として使う。
- `inku-ddl`の一部module（`compiler_lock.rs`、`composition_plan.rs`、`document.rs`、`macro_definition.rs`、`score_lowering.rs`等）のdoc commentに「runtime-disconnected」が残る。`inku-score/src/types.rs`は「Pythonがschemaの正本」と記す。
- 判定: **説明文の差異**で、挙動の差ではない。

### F-10 Stage executorの残り

- `api_core/state.py`は`INKU_STAGE_WORKERS` / `INKU_STAGE_QUEUE_LIMIT`でStage executorとslotを作り、`/api/settings/status`がその件数を返す。
- 現行コードにこのexecutorへjobを投入する箇所は無い。LLM effectは`PipelineService`のthread poolで走る。
- 判定: **状態表示だけが残る**。表示される値は現在のLLM処理量を表さない。

### F-11 Android端末受入の参照corpus

- `prepareRustParityAssets`と`NativeRenderDeviceTest`は`server/reference/render-engine-41`の少数caseを端末へ取り込み、SVG byteを照合する。`android-native.yml`のpath条件も`render-engine-41`を名指す。
- 現行のRender Engineは68で、最新の凍結corpusは66である。
- 判定: **未確認**。取り込んだcaseがEngine 68でも同じbyteを出すかは今回確認していない。

## 文書間で注意が必要な語

- SPECの「Rendererは非決定的」「同じScoreから違うSVG」は、render seedを変えた演奏の説明である。Project Contextと実装の契約は「同じScore + 同じseed + 同じ描画条件は同じ作品」。本群は後者を再現性の表現に使う。
- `SPEC.ja.md` の文書Version `v1.92.0` とapp version `v2.15.28` は別namespaceとして記録した。これ自体を不一致とは判定しない。
- 「Stage 2」は、旧実装ではDDLからScoreを作るLLM段を指し、現行ではknown holeへの可視patch候補だけを作るLLM段を指す。Scoreの構造化は共有Rustのlowererが行う。
- 「coerce」は旧Score互換の文脈（`coerce_saved_score`）と保存済み観測記録（`coerce/observability.py`）にだけ残り、新作の生成段ではない。
- 「写生」は、旧Stage 0.5（記述の代わりに写生文を後段へ渡す層）と、現行の任意effect（記述の横に場所と光を補う）で意味が異なる。旧作品の`fine` / `coarse`は前者の記録である。

## 集中が疑われる箇所

### C-01 `web/src/routes/+page.svelte`

Session、current-workのsubmit/replay/stop、Batch/Demoの非同期lifecycle、refinement orchestrationとtarget identity、Settings管理slice、最大のCanvas/Settings view、共有pipelineの実行viewにはroute-instanceまたはfocused ownerができた。pageはroute lifecycle、modal/view state、component配線、history/lineageのcross-owner action、DDL編集からpipelineへの受け渡し、短い表示用projectionを保持する。composition seamではあるが、高変更workflowのcanonical writerではなくなった。

残る行数だけではowner違反を示さない。次の分割は、同じ変更理由が複数ownerを横断する、mutable stateが二重化する、または非同期failure境界がpageへ戻る場合にだけ検討する。

### C-02 `server/src/inku_server/db.py`

現在の`db.py`はpublic compatibility／composition façadeである。schema宣言、version付きstartup、legacy column coordination、baseline callback、backup、auth、settings、history、lineage、search、variation authorityの実装ownerは`persistence/`配下へ分かれ、façadeはlive dependencyの組み立てと既存import名の委譲を担う。

残る行数やcompatibility re-exportだけではowner違反を示さない。今後の縮小はreaderがゼロと証明されたwrapperだけを対象にし、公開importやcall-time compositionを行数目的で消さない。

### C-03 共有coreの大きいmodule

旧`api_core/routers/render.py`の集中はcutoverで解け、routerは互換投影と旧Score再演の入口だけになった。変更の交差点は共有coreへ移っている。`inku-ddl/src/score_lowering.rs`（約7800行）、`semantic_association.rs`と`compiler_lock.rs`（各約4600行）、`inku-pipeline/src/machine.rs`（約2000行）が大きく、Server側では`pipeline_product.py:ProductPipelineEffects`が準備・provider・保存・再演の4つのhost責任を1 classに持つ。

行数だけではowner違反を示さない。分割は、独立した変更理由が同じmoduleで衝突する場合にだけ検討する。

## 実装から確認できなかったこと

- 実配備中のprocess、DB backend、queue利用率、backup/log/outputの実設定値。秘密・実環境を読まない境界のため未確認。
- 外部LLM providerの現在の到達性、model availability、latency。静的provider routingだけを確認した。
- Redis rate limiterが実配備で有効か。`INKU_REDIS_URL`の値を読んでいない。
- Compose imageの現在の稼働状態とvolume persistence。設定は確認したが起動していない。
- live appのroute数。本調査の環境にnative wheelが無く、app importが失敗したため、route数は宣言の静的な数え上げによる（F-06）。
- Android端末受入の現行結果（F-11）。
- Mermaid図の実際の表示。本書群の全44図はmermaid 11のparserで構文を確認したが、GitHub／Gitea上の表示は確認していない。

## 仕様だけに基づく部分

本群の主要node/edgeはすべて公開sourceの実装根拠を持つ。実配備状態を表すnodeは置いていない。

## 今後確認すべき質問

1. Project Context（F-05）とAndroid仕様メモ（F-02、F-03）の古い記述を、現行実装に合わせて更新するか。
2. route数の検査定数とAPI surface baseline（F-06）を現行routeへ合わせるか。
3. 札だけの記述の門（F-07）とstreamの進行event（F-08）について、SPECを実装へ合わせるか、実装をSPECへ戻すか。
4. 使われていないStage executor（F-10）と、Android端末受入の参照corpus（F-11）をどう扱うか。

これらは本調査で実装・仕様を変更する課題ではないため、台帳への自動転記はしていない。
