# 既知の差異と未確認事項

## 仕様・実装の不一致

### F-01 Render Engine版（調査中に解消）

- 調査開始時の `PROJECT_CONTEXT.ja.md` はRender Engine 28と記し、実装29と不一致だった。
- その後、公開commit `8b4d43cc` で同文書が29へ更新され、`render_engines/default.py` と `server/reference/render-engine-29/manifest.json` に一致した。
- 判定: **現在は解消済み**。本書群のsnapshotも更新後commitへ合わせた。

### F-02 Android仕様メモの版記述

- `android/ANDROID_SPEC.ja.md` 冒頭は `2.1.4-android.10` / engine 21、server `v2.11.2` / engine 21と記す。
- 実装は `android/VERSION` が `2.1.4-android.43`、`CompatibilityConstants.renderEngineVersion` が35（2026-08-17に再測）。
- 判定: **冒頭snapshotが古い**。追随の実況は文書後半の周ごとの節が持ち、冒頭は追いついていない。

### F-03 Android外部provider実行

- Android仕様メモの「未実装」は外部provider executionを未実装とする。
- 現行 `RoutingModelProvider` はenabled providerを解決し、`OpenAiCompatibleProvider.generate` / `fetchModels`へ接続する。`InkuRepository`のStage 1/2/demoはこのrouterを利用する。
- 判定: **OpenAI-compatible経路について未実装記述が古い**。Anthropic/Gemini固有protocolの実装は確認できず、全providerの同等性は主張しない。

### F-04 Stage 1.5の長い旧説明

- `SPEC.ja.md` §12.11は数学・音楽・絵画候補を追加する旧設計を詳述する。
- §12.12が後からそれを畳み、現行実装も焦点reframeのみで新しい文を追加しない。
- 判定: 後節が明示的に上書きしており実装不一致ではないが、§12.11だけを読むと現行構造を誤読しやすい。

## 文書間で注意が必要な語

- SPECの「Rendererは非決定的」「同じScoreから違うSVG」は、render seedを変えた演奏の説明である。Project Contextと実装の契約は「同じScore + 同じseed + 同じ描画条件は同じ作品」。本群は後者を再現性の表現に使う。
- `SPEC.ja.md` の文書Version `v1.92.0` とapp version `v2.13.47` は別namespaceとして記録した。これ自体を不一致とは判定しない。

## 集中が疑われる箇所

### C-01 `web/src/routes/+page.svelte`

Session、current-workのsubmit/replay/stop、Batch/Demoの非同期lifecycle、refinement orchestrationとtarget identity、Settings管理slice、最大のCanvas/Settings viewにはroute-instanceまたはfocused ownerができた。pageはroute lifecycle、modal/view state、component配線、history/lineageのcross-owner action、短い表示用projectionを保持する。composition seamではあるが、高変更workflowのcanonical writerではなくなった。

残る行数だけではowner違反を示さない。次の分割は、同じ変更理由が複数ownerを横断する、mutable stateが二重化する、または非同期failure境界がpageへ戻る場合にだけ検討する。

### C-02 `server/src/inku_server/db.py`

schema、migration、auth、settings、backup、history、lineage、searchを1 moduleが持つ。transaction境界は明瞭だが、責任の集中が大きい。

### C-03 `api_core/routers/render.py`

request/response schema、provider failure、fallback、Stage orchestration、trace、history handoffを同じrouter moduleが持つ。pipeline順序の一次根拠として強い一方、変更の交差点になっている。

## 実装から確認できなかったこと

- 実配備中のprocess、DB backend、queue利用率、backup/log/outputの実設定値。秘密・実環境を読まない境界のため未確認。
- 外部LLM providerの現在の到達性、model availability、latency。静的provider routingだけを確認した。
- Redis rate limiterが実配備で有効か。`INKU_REDIS_URL`の値を読んでいない。
- Compose imageの現在の稼働状態とvolume persistence。設定は確認したが起動していない。
- Mermaid rendererによる構文実行。CLIの存在確認結果は完了reviewに記録する。

## 仕様だけに基づく部分

本群の主要node/edgeはすべて公開sourceの実装根拠を持つ。実配備状態を表すnodeは置いていない。

## 今後確認すべき質問

1. Android仕様メモ冒頭のsnapshotと外部provider「未実装」を、現行コードに合わせて更新するか。
2. 残るroute shell/history-lineage調停、DB module、render routerのどれを、次に変更理由から集中度reviewするか。
3. Android JVM testをCIへ追加するか。server/CLI/Web/docsのgateは`checks.yml`（台帳I-192）でCIに入った。

これらは本調査で実装・仕様を変更する課題ではないため、台帳への自動転記はしていない。
