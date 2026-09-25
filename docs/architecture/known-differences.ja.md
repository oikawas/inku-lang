# 既知の差異と未確認事項

## 仕様・実装の不一致

### F-01 Render Engine版（調査中に解消）

- 調査開始時の `PROJECT_CONTEXT.ja.md` はRender Engine 28と記し、実装29と不一致だった。
- その後、公開commit `8b4d43cc` で同文書が29へ更新され、`render_engines/default.py` と `server/reference/render-engine-29/manifest.json` に一致した。
- 判定: **現在は解消済み**。本書群のsnapshotも更新後commitへ合わせた。

### F-02 Android仕様メモの版記述（再発）

- 2026-08-24に冒頭を当時の実装へ同期したが、現行の冒頭（最終更新 2026-09-25）は`2.1.4-android.80`、render engine `67`、DDL engine version `20`、serverの`ddl_engine_version` 21と記す。
- 実装はRender Engine `68`（`core/crates/inku-render/src/lib.rs`）、`ddl_engine_version` `47`（`layer_versions.py`）で、Androidは同じ共有Rust pipelineを使う。
- 判定: **版の数字が古い**。engine identityはKotlin製品定数でなく同梱native libraryから読むため、runtimeの挙動ではなく文書の差異である。2026-09-25にAndroid担当へ引き継いだ。

### F-03 Android外部provider実行

- Android仕様メモの「未実装」節は、外部provider executionを未実装とし、provider recordをcompatibility data structuresと記す。
- 現行 `RoutingModelProvider` はenabled providerを解決し、`GeminiModelProvider`と`OpenAiCompatibleProvider`へ接続する。共有pipelineのprovider effectは`SingleAttemptModelEffectProvider`がこれらへ送る。同じ仕様メモの前半もGeminiとOpenAI互換への要求条件を記している。
- 判定: **「未実装」節が古い**。Anthropic固有protocolの実装は確認できず、全providerの同等性は主張しない。2026-09-25にAndroid担当へ引き継いだ。

### F-04 Stage 1.5の長い旧説明（解消）

- 旧snapshotでは `SPEC.ja.md` §12.11が、数学・音楽・絵画候補を追加する旧設計を詳述していた。
- 現行の§12.11は、`CanonicalReady`のtyped meaningだけを受けて焦点と明示変奏だけを変えるtyped transformationとして書き直されている。
- 判定: **解消済み**。

### F-05 Project Contextに残る古い記述（解消）

- 旧snapshotの`PROJECT_CONTEXT.ja.md`は、版の表（Render Engine 66、DDL 11 / 45、Android `2.1.4-android.78`）、android節（render engine 42、DDL engine 20、Android hostがStage 1 / 1.5 / 2とcoerceを所有）、検査面（`render-engine-42`・`ddl-engine-20`をCIが強制）、決定的な層（`coerce/`・`ddl_expander.py`）、RAW trace、語彙の正本（`schema.py`）で実装より古かった。
- 2026-09-25に日英とも現行へ直した。
- 判定: **解消済み**。

### F-06 route数の検査定数（解消）

- `test_route_authorization.py`の`EXPECTED_ROUTE_COUNT`は95のままで、`/api/pipeline/*`の11本の追加（2026-09-13、`2ad24df9`）と`/api/prompts`の削除（2026-09-14、`03bbd686`）を数えていなかった。`tests/data/api-surface-baseline.json`も同じ時点のままだった。
- 2026-09-25に定数を105へ直し、baselineをlive appから作り直した（105 operation、160 schema）。native wheelを入れた環境で`test_route_authorization.py`が通ることを確認した。
- 判定: **解消済み**。

### F-07 札だけの記述の門（解消）

- cutoverで旧`description_labels.py`が削除され、行頭の連番と角括弧のコメントがStage 1・写生・色カタログ選択へそのまま届き、札だけの記述も400にならなかった（`SPEC.ja.md` §12.16と不一致）。
- 2026-09-25に`description_labels.py`を戻し、`PipelineService.start`（記述起点の全経路）と記述からの再生成で、coreへ渡す記述だけから札を切るようにした。作品には書いたままの記述が残り、札だけの記述は400になる。
- 判定: **解消済み**。Androidは切除を持ったことがなく、この門はServerの境界にある。

### F-08 streamの進行event（解消）

- cutover後の互換streamは、最終結果を`done` 1行だけで返していた（`SPEC.ja.md` §12.10と不一致）。
- 2026-09-25に、実行を読み直して`sketch`（写生を通した場合）・`stage1`・`score`・`done`を順に出す形へ戻した。最初のeventより前の拒否はHTTPの状態で、後の失敗（補完案の承認待ちを含む）は本文の`error` eventで届く。token数は共有pipelineが数えないためnullである。
- 判定: **解消済み**。

### F-09 実装内の古い説明文（解消）

- `core/crates/inku-pipeline/README.md`（effect tagの数、candidate APIがruntimeを切り替えない等）、`persistence/variation_authority.py`のdocstring、`inku-ddl`のdoc commentの「runtime-disconnected」が、共有pipelineが通常runtimeになった後も残っていた。
- 2026-09-25に直した。旧snapshotで挙げた`inku-score`の「Python由来のraw Score JSON Schema」は、`score.schema.json`が今もPythonの`Score`と照合される成果物なので、差異から外した。
- 判定: **解消済み**。

### F-10 Stage executorの残り（解消）

- `INKU_STAGE_WORKERS` / `INKU_STAGE_QUEUE_LIMIT`のStage executorは投入元が無く、`/api/settings/status`の`stage_execution`は使われないpoolと動かない件数を示していた。`SPEC.ja.md` §22とSETUPもこのexecutorを説明していた。
- 2026-09-25にexecutorを外し、`stage_execution`が共有pipelineのworker pool（`workers`は`max_workers`、`queue_limit`は`max_retained_runs`）とprovider effectの件数を示すようにした。応答schemaは変えていない（権限グループ導入前から凍結されたschemaである）。SPEC §22とSETUPも改めた。
- 判定: **解消済み**。

### F-11 Android端末受入の参照corpus

- `prepareRustParityAssets`と`NativeRenderDeviceTest`は`server/reference/render-engine-41`の少数caseを端末へ取り込み、SVG byteを照合する。同testは`NativeRenderBridge.renderEngineVersion()`が`"41"`であることも表明し、`android-native.yml`のpath条件も`render-engine-41`を名指す。
- 同梱libraryのRender Engineは68なので、この表明は成り立たない。期待SVGもEngine 41のもので、現行engineと同じbyteである保証が無い。
- 判定: **端末受入が失敗する状態**と推定する（端末では実行していない）。直すにはbuild時に同じcommitのhost coreで期待SVGを作る等の変更とPixel 9での受入が要るため、2026-09-25にAndroid担当へ引き継いだ。

### F-12 hole補完のAPI testの偽provider（解消）

- `server/tests/test_pipeline_api.py::test_managed_api_persists_approved_patch_reload_and_legacy_fork`の偽providerは、hole補完要求の本文から`base_source_digest`等を読んで応答する。
- 現行のhole補完prompt（`inku.visible-ddl-hole-completion-prompt.v3`）はdigestやbyte位置をproviderへ渡さない（`SPEC.ja.md` §12.7.1）。このtestは修正前のcommit（`f910a11e`）でも`KeyError: 'base_source_digest'`で失敗する。
- 2026-09-25に、偽providerがv3の形（短いID `h1` ごとの`proposed`と置換文）で答え、promptがv3であることを確かめるよう直した。あわせて、承認待ちの時点で独立した描画（赤い円）のScoreが`complete_with_omissions`として残ることを確かめる検査へ改めた（旧testは承認待ちでScoreが無いことを期待していた）。
- 判定: **解消済み**。

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
- Android端末受入の現行結果（F-11）。
- Mermaid図の実際の表示。本書群の全44図はmermaid 11のparserで構文を確認したが、GitHub／Gitea上の表示は確認していない。

## 仕様だけに基づく部分

本群の主要node/edgeはすべて公開sourceの実装根拠を持つ。実配備状態を表すnodeは置いていない。

## 今後確認すべき質問

1. Android仕様メモ（F-02、F-03）と端末受入の参照corpus（F-11）は、Android担当の修正と受入を待つ。

これらは本調査で実装・仕様を変更する課題ではないため、台帳への自動転記はしていない。
