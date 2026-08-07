# inku プロジェクトコンテキスト

**対象バージョン: v2.11.4 / Build 859**

この文書は、開発者とAIが毎回 `SPEC.ja.md` 全文を読み直さずに作業を始めるための入口である。
設計判断の正本は `SPEC.ja.md` であり、この文書と食い違う場合は日本語仕様を優先する。

## 最初に読むもの

通常の作業では、次の順に必要な範囲だけ読む。

1. `AGENTS.md` がローカルに存在する場合は、開発・検証・デプロイ規則を確認する。
2. 本書で目的、構造、現在の契約を確認する。
3. `git status --short --branch` と直近の履歴で作業状態を確認する。
4. 変更対象に関係する `SPEC.ja.md` の節と実装ファイルだけを読む。
5. 歴史的経緯が必要な場合だけ `CHANGELOG.ja.md` を検索する。

全文確認が適するのは、初回参加、設計思想の再検討、複数領域にまたがる大規模変更、仕様矛盾の監査である。

## プロジェクトの目的

`inku` は DDL（Drawing Description Language）の参照実装である。
DDLは一般的な描画命令ではなく、「視覚的な短歌を書く言語」を目指す。

- 記述そのものを持続する作品として扱い、SVGは一回の演奏として扱う。
- 感情的な評価語ではなく、物理素材、配置、運動、観察可能な関係を書く。
- 短さと制約によって作者の主張を削ぎ、提示を中心にする。
- 既定の処理は再現可能にし、揺らぎはRendererの演奏とユーザーの明示操作に限定する。

## 現行アーキテクチャ

```text
指示文
  -> Stage 0.5: 写生（任意・記述を物の言葉へ写した自然文にする）
  -> Stage 1: 解釈
  -> 正規化DDL（名前空間付きプラグイン語を含みうる）
  -> 宣言的プラグイン展開: コアDDLへ決定的にwriting-down
  -> Stage 1.5: 決定的な拡張・関係付与
  -> Stage 2: JSON Score化
  -> coerce / validation: drop-onlyを優先する境界処理
  -> Render Engine: SVG演奏
  -> 履歴・作品系譜
```

- `server/`: FastAPIバックエンド。
API、認証、DB、解釈、構成、補修、描画、系譜を持つ。
- `web/`: SvelteKit 2 / Svelte 5フロントエンド。
- `cli/`: 公開HTTP APIだけを使う `inku-cli`。
- `android/`: Kotlin / Jetpack Composeによる別実装。
詳細正本は `android/ANDROID_SPEC.ja.md`。
- `SPEC.ja.md`: 設計思想と現行契約の日本語正本。
- `SPEC.md`: 英語公開仕様。
- `CHANGELOG.ja.md` / `CHANGELOG.md`: 実装・設計変更の履歴。

## 守るべき設計契約

- DDLテキストは母語で書ける。
JSON Scoreのキーは英語で統一する。
- Stage 1の解釈とStage 2の構造化を分離する。
- Stage 1.5は入力の意味を上書きせず、固定レシピの大量注入を避ける。
- coerceは長期的に縮小する。
新しい様式を自動注入せず、不正値は可能な限りdrop-onlyで扱う。
- 同一Scoreと同一seedは同じ作品を再現する。
暗黙の時刻seedや自動varyを導入しない。
- `dh1`（記述同一性）、`rh3`（作品エディション。
旧 `rh2` は legacy として保持）、履歴ID、系譜node IDを混同しない。
- 系譜は明示された派生操作だけを記録し、類似度、時刻、hash一致から親子関係を推測しない。
- 品質指標、類似度、Vision所見は監査の鏡であり、生成ゲートや「最良枝」の自動選択に接続しない。
- プラグインはコードではなく検証済みの宣言的文書であり、Stage 1直後にコアDDLへ展開する。
Stage 1.5 / coerce / Score / rh2はプラグインに依存しない。
- 語彙の正は saijiki テーブル（`server/src/inku_server/saijiki.py`、v1.92）であり、Stage 1プロンプトの語彙ブロック・プラグイン閉包マーカー・relation固定句・web歳時記表示・reference §1はそこから導出する。
語彙の変更はテーブルとgolden testを経由する。
- 日本語と英語の挙動を揃え、英語だけの要件を追加しない。
- **エンジンは後戻りしない**（SPEC.ja §15.8）。
過去の描画エンジンをシステムとして保持せず、版を選び直す機構も作らない。
Replay は常に最新で行い、当時のエディションの再現は**保存済み SVG の返却で担保する**。
版画と同じで、彫りは進み刷りは残るが版木は戻せない。
**だから現役のうちに参照コーパス（＝校正刷り）を取る。
**

## 現在の製品状態

**本節は「いま何が在るか」だけを現在形で書く。**
どの版で何をしたかという時系列の記録は `CHANGELOG.ja.md` が持ち、本書はそれを写さない。
なぜその形になったかを知りたいときは `CHANGELOG.ja.md` を該当語・版・Build 番号で検索する。

### 版

| 対象 | 値 | 正本 |
|---|---|---|
| アプリ | 本書冒頭の「対象バージョン」 | **`web/APP_VERSION` と `web/BUILD_NUMBER` の 2 ファイル**。UI・`/api/info` の `version`・CLI はすべてここを読む（値をここに写さない） |
| Render Engine | 22 | `server/src/inku_server/render_engines/default.py` |
| DDL | `ddl_version` 3 / `ddl_engine_version` 7 | `server/src/inku_server/layer_versions.py` |
| Android | `2.1.4-android.11` | `android/VERSION`（web / server とは別の名前空間） |
| Python パッケージ | 2.7.2 | `server/pyproject.toml`（**製品リリースのときだけ動く**） |

### 語彙

正本は `server/src/inku_server/schema.py` の Literal で、日本語の語との対応は saijiki テーブル（`saijiki.py`）が持つ。

- 図形 8 — `line` / `circle` / `ellipse` / `triangle` / `square` / `polygon` / `arc` / `cloudform`
- 線種 4 — `solid` / `dashed` / `dotted` / `dash_dot`
- 道具 11 — `silverpoint` / `pencil` / `pen` / `rotring` / `crayon` / `chalk` / `brush_thin` / `brush_thick` / `burin` / `drypoint` / `computer`
- 細さ 2 — `fine` / `extra_fine`（道具から独立した太さの軸）
- 色 9 — `white` / `black` / `blue` / `red` / `green` / `gray` / `yellow` / `orange` / `purple`
- 面の質感 9・面の向き 5・地の素材 6

saijiki テーブルは単一の情報源で、Stage 1 プロンプトの語彙ブロック・プラグインの閉包マーカー・relation の固定句・web の歳時記表示・reference §1 をそこから導出する。
語彙の変更はテーブルと golden test を経由する。

### パイプラインの各層

- **Stage 0.5（写生）** — 任意の層で、記述を物の言葉へ写した自然文（写生文）に変える。
区切りの大きさを `fine`（細かく・既定）と `coarse`（大きく）の 2 値から選び、描画のたびに指定できる。
**写生文は記述の代わりに 3 つの消費者へ届く**（Stage 1・プラグイン展開の発動判断・Stage 1.5）。
**Stage 2 と coerce は DDL だけを読む。** プラグインの種（何枚・何本を決める材料）は記述である。
記述そのものは保存と表示に残り、層が落ちたときは記述がそのまま Stage 1 へ流れる。
**層が何をしたかは作品に残る**（`sketch_state` の 5 値 = `fine` / `coarse` / `fallback` / `off` /
`not_applicable`）。**落ちた回と、切った回と、呼ばない経路は別々に記録される。**
`NULL` が意味するのは「この列より前に描かれた作品」だけである。
- **Stage 1（解釈）** — 指示文の言語を自動判定し、正規化 DDL を作る。
プロンプトは歳時記から組み立てられ、固定文字列を持たない。
- **プラグイン展開** — 検証済みの `.inku-plugin.md` を Stage 1 の直後にコア DDL へ決定的に writing-down する。
名前空間が明示された語か、指示対象として明示された語の `fires_on` だけが発火し、比喩や未知の対象へは広げない。
- **Stage 1.5** — 決定的な拡張と関係付与。
変奏（強度 3 段）を持ち、作品ごとに保存される。**動く軸は焦点ひとつで、この層は記述に無い文を足さない。**
- **Stage 2** — JSON Score 化。
任意フィールドの充填率は tool schema の**宣言順に従属する**（末尾に置いた語ほど埋まる）。
- **coerce** — `normalize` と `compose` の 2 つに割れている。
不正値は可能な限り drop-only で扱い、新しい様式を自動注入しない。
- **Render Engine 22** — SVG の演奏。
閉図形の輪郭と塗り、弧、材質層、地の抵抗、マスターグリッドによる座標の量子化を持つ。
**塗りは面を実体で持つ下地の上に載り、上に載るものは被覆率 0.2 で走査線と擦りの痕に分かれる。**

観測用に RAW trace がある（`/api/paint` と `/api/compose` の `include_trace`、既定 false）。
各層の中間生成物を 1 応答に持ち帰るだけで、Score・分岐・回数を変えず DB へも保存しない。

### web（SvelteKit 2 / Svelte 5）

認証付きの単一ページアプリで、記述・作品・バッチ・デモ・系譜の各タブを持つ。

- 記述の入力と再現可能な推敲（タッチ・配置・読み取り）、AI による自律推敲と変奏。
行頭の連番と角括弧のコメントは作品に残るが描画のどの層にも渡らず、入力欄では背景が灰色になる
- 色カタログ 13 本（`color_catalogs.py`。全カタログが 9 色すべてを持つ）と「記述から自動選択」、
キャンバス比率、表示モードの選択。カタログの選択はユーザーごとにサーバーへ保存する
- ユーザー別の履歴、スター、推敲マーク、コメント、ゴミ箱、検索、系譜グループ、明示的な lineage node / edge。
2 つの印は独立していて、両方で絞ると両方を持つ作品だけが出る
- モデル・言語・描画要素の比較、生成情報／プロンプト／JSON のインスペクタ、奥書（colophon）
- 作品の SVG / PNG / アニメーション書き出し。
落とし口は 1 本で、利用者が選んだフォルダへ書ける（File System Access API を持つブラウザのみ。
持たないブラウザはブラウザ既定へ落ちる）
- 日英の UI。英語の用語は `web/src/lib/i18n/GLOSSARY.md` が正本で、`npm run lint:i18n` が強制する

UI の寸法は `+page.svelte` の `:root` のトークン（`--btn-sm-*`）が、色は `--action-*` と `--accent*` が正本で、px と色の直書きは退行として扱う。

機能ごとの設定は `web/src/lib/features/<name>/` に閉じる。
localStorage への保存・server への永続・描画要求への同梱は、
**機能を 1 つも名指ししない 3 つの登録簿**（`persisted-settings.ts` / `user-settings.ts` / `render-payload.ts`）が集めるので、
設定を 1 本足しても `+page.svelte` は 1 行も動かない。

### server（FastAPI）

- エンドポイント 82 本は `server/src/inku_server/api_core/routers/` の 10 ファイルに在る（`auth` `feedback` `history` `lineage` `me` `plugins` `public` `render` `settings` `users`）。
共有される定義は `api_core/{state,models,deps,common,rendering}.py` に置く。
- `api.py` が持つのは `app` の組み立て・`_lifespan`・ミドルウェア・起動時の呼び出し・`include_router` だけである。
**依存の向きは `api.py` → routers → 共有の一方向**で、router から `api.py` を import しない。
- 認可はルート単位のガードと router 単位の既定依存の 2 つで強制する。
公開許可リストに載る 6 本を除き、すべてガードの下に在る。
- LLM は Anthropic とローカル／クラウドの OpenAI 互換の両系統へ繋がり、API キーを 1 つも用意せずに始められる。
モデル参照の解決は明示修飾 → 一意所有 → 段の既定の 3 段規則で、推測をしない。

### cli

`inku-cli` は公開 HTTP API だけを使う。
描画・履歴・プラグイン・参照 dump・管理コマンド・ベンチマーク補助を持ち、server の内部モジュールを import しない。
**機能テストはこの CLI を通す。**
旗が無ければ、まず CLI に実装してからテストする。
**送らない鍵はエラーにならず既定で埋まるので、リクエストのフィールドは送り手ごとに数える**
（`server/tests/test_cli_sender_census.py`）。

### android

Kotlin / Jetpack Compose / Room による別実装で、端末内でパイプライン全段を回す。
詳細の正本は `android/ANDROID_SPEC.ja.md`。
**server を正本として後から追随する形であり、server の設計を Android に合わせて曲げない。**
追随の遅れは常にありうるので、Android の版数と server の版数を同じものとして読まない。

### 検査面

- **`server/tests`** — pytest。ルート認可の網羅（生きたルートを `fastapi.routing.iter_route_contexts` で歩く。**`app.routes` を直に読むと fastapi 0.141 以降は 1 本も取れない**）、API 表面の同一性（`tests/data/api-surface-baseline.json` と照合）、ルート本体の所在（`route.endpoint.__module__` を数える）を含む。
- **凍結された参照コーパス** — `server/reference/` に版ごとの校正刷りを置く。
現役は `render-engine-22`（531 件）と `ddl-engine-7`（34 件）で、再生成のバイト一致を CI が強制する。
- **Android の参照コーパス** — `android/app/src/test/resources/server_reference/` も同じ作法で版ごとに分かれる。
移植は自分が名乗る版のディレクトリを読むので、**server が engine を上げてもディレクトリが増えるだけで移植は赤くならない**。
旧版は焼き直せないので、各版の `manifest.json` が名前と digest で押さえる。
- **`cli/tests`** — pytest。
- **`npm run check`** と **`lint:i18n`** / **`lint:models`** / **`lint:recommendations`** — web の型と用語とモデル解決。
- **`npm run test:unit`** — web の純関数の単体テスト（Node の `node:test`。依存を足していない）。
- **`scripts/check_docs.py`** — 公開文書の内部参照。

**決定的な層**（`coerce/`・`ddl_expander.py`・`renderer.py`・`stroke_engine.py`・`schema.py`・`saijiki.py`・`language_support/{ja,en}.py`）に触れたときは、凍結コーパスの照合を必ず通す。

**CI が回すのは凍結コーパスの再生成だけである。**
pytest も ruff も `npm run check` も CI では走らないので、**コーパスが見ていない退行は自動では誰も止めない。**

### 残っている課題について

**未解決の課題・未裁定の事項は本書に書かない。**
本書へ書くと、書かれた時点で凍って以後だれも見直さないため、直っても古い記述が残る。
開発者向けの台帳が別に在り、そちらが状態を持つ。

## 変更時の確認先

| 変更領域 | 主に読むもの |
|---|---|
| 言語思想・語彙・揺らぎ・関係 | `SPEC.ja.md` §1–14 |
| Web UI・推敲・比較 | `SPEC.ja.md` §7–8、`web/src/` |
| Score・解釈・構成・描画 | `SPEC.ja.md` §5、§12–14、`server/src/inku_server/` |
| 履歴・系譜・奥書 | `SPEC.ja.md` の洗練の会計／奥書、関連API・DB |
| 運用・検証 | ローカルの `AGENTS.md`、`compose.yaml`、各README |
| 過去の判断理由 | `CHANGELOG.ja.md` を該当語・版・Build番号で検索 |

## 文書更新規則

- 仕様変更は `SPEC.ja.md` を先に更新し、**同じ内容を節ごとに** `SPEC.md` へ反映する。
片方にしか無い節は置かない（2026-08-02 裁定。**正本が日本語である点は変わらない**）。
`server/scripts/check_docs.py` が見出し形状の一致を見る唯一のゲートで、マージ前に走らせる。
- 現行の構造や重要契約が変わる場合は、本書と `PROJECT_CONTEXT.md` も更新する。
- リリース／Buildの履歴は `CHANGELOG.ja.md` を先に更新し、公開上必要な内容を `CHANGELOG.md` に反映する。
- 実装だけの細部を仕様本文へ無制限に積み増さない。
現行契約は仕様、時系列の記録は変更履歴へ置く。
- Webの挙動またはUI変更では `web/BUILD_NUMBER` を更新する。
アプリ世代変更時はWebの `APP_VERSION` も揃える。
- **本書の「現在の製品状態」には版ごとの段落を積まない。**
版で何をしたかは `CHANGELOG.ja.md` が持つので、本書は現在形の記述だけを保ち、変わった箇所を書き換える。
採番のたびに段落を足すと、本書は変更履歴の二枚目になり、入口として読めなくなる。
- **未解決の課題・未裁定の事項を本書に書かない。**
本書の記述は書かれた時点で凍り、直っても古い記述が残る。
課題は状態を持てる台帳で管理する。
