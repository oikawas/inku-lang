# inku 変更履歴

**日本語の詳細履歴** — 現行仕様は [SPEC.ja.md](SPEC.ja.md)、短い導入は [PROJECT_CONTEXT.ja.md](PROJECT_CONTEXT.ja.md) を参照する。

この文書は時系列の実装・設計記録である。仕様との不一致がある場合は、現行契約を記す `SPEC.ja.md` を優先する。

---


### v0.1 (2026-04-02)

- 初期コンセプト（東京都現代美術館「ソル・ルウィット オープン・ストラクチャー」展にて構想）
- 三層パイプライン（記述 → 楽譜 → 演奏）の設計
- JSON Schema v0.1 の策定
- DDL_concept.md として初期ドキュメントを記録

---

## 起源

構想: 2026年4月2日、東京都現代美術館「ソル・ルウィット オープン・ストラクチャー」展
### v0.2 (2026-04-14)

- 最初のプロトタイプとして、コンセプトしたものが動作可能かを簡単にクライアントでテスト
- Android 実装状態を記録（SPEC_v1.md に分離）
- LiteRT-LM 0.10.0 API 調査・実装
- Pixel 9 での E2E 動作確認

### v0.3 (2026-04-21)

- inku-langとしての全体設計の開始
- プロジェクト名を `inku` (inku-lang) として確定
- Section 4「プラグイン設計原則」を新規追加（Emacs Lisp 化を避ける5原則）
- Section 12「Opus 4.7 の役割」を「二段階変換アーキテクチャ」として大幅書き換え
- Section 13「揺らぎの設計」を新規追加（感情語彙と運動語彙の区別、三層構造）
- Section 3「コアに入れるもの」に「つらなり」「ゆらぎ」カテゴリを追加
- Section 5「Base Language 問題」に責任範囲の明確化（日英は作者、他言語はコミュニティ）
- Section 7「UI設計方針」に Saijiki（歳時記）、解釈フィードバック、書後色付けを追加
- Section 6「コアとエクステンションの分離」の方針を整理

### v0.4 (2026-04-23)

**Phase 1 実装着手 — Server バックエンドの骨格形成**

- **リポジトリ構成**
  - `inku-lang` リポジトリを GitHub (`github.com/oikawas/inku-lang`) に作成
  - `server/` と `web/` の2スロット構成。`server/` 先行実装

- **Python プロジェクト: inku-server 0.1.0**
  - パッケージマネージャ: `uv` (0.11.7) + src-layout
  - 依存: anthropic, fastapi, pydantic v2, svgwrite, uvicorn, python-dotenv
  - dev: pytest, ruff
  - Python 3.10+

- **JSON Score schema (Pydantic v2 実装)**
  - `extra="forbid"` で未知フィールド拒否、schema 厳密化
  - `populate_by_name=True` + alias で予約語回避 (`from` → `from_`)
  - Primitive: `line | circle | ellipse | triangle | square | arc`
  - `rotation`: 図形全体の回転角。0=水平、正=時計回り、負=反時計回り。線・楕円・四角・三角・弧を中心まわりに回転
  - Weight 9種、Color 6種、LineStyle 4種、Variation 4フィールド (amplitude/frequency/quality/dimensions)
  - `Score.model_json_schema()` を Anthropic tool input_schema にそのまま渡せる形

- **Renderer MVP (svgwrite, 1000x1000 viewBox)**
  - 実装済 primitive: line, circle, ellipse, triangle (等辺二等辺), square (矩形)
  - 座標変換: `0.0-1.0` 比率 × `CANVAS_PX=1000` で px 化
  - weight → `stroke-width` マッピング (hair 0.5 〜 brush_thick 8.0)
  - color → HEX パレット (黒=#111111, 青=#2c3e91, 赤=#a2342a, 緑=#2f6b3a, 灰=#888888, 白=#ffffff)
  - style → `stroke-dasharray` (solid=なし, dashed=12,8, dotted=2,6, dash_dot=12,6,2,6)
  - 背景色: `#f7f5ef` (墨が映える薄黄、和紙を想起)
  - 未実装: arc (schema に角度フィールド未定義)、variation の実際の波形生成

- **Stage 2 composer (正規化DDL → JSON Score)**
  - モデル: `claude-haiku-4-5-20251001` via Anthropic tool_use
  - `submit_score` ツールを定義し `tool_choice` で強制呼び出し
  - system prompt に Saijiki 歳時記マッピング + 座標系 + 出力ルールを圧縮記述
  - `Score.model_json_schema()` を tool input_schema に直接注入

- **正規化DDL Fixture 15ケース**
  - `server/tests/fixtures/stage2/{01..15}/` に input.txt + expected.json ペア
  - 網羅: 全5 primitive、全4 style、weight 複数 (pencil/pen/brush_thick)、color 全6、variation 2種 (fine+perlin, broad+wave)、複数命令 (3円並列)

- **テスト**
  - `test_renderer.py`: 10 cases, pytest 全 pass
  - `test_composer.py`: 15 fixture parametrize + tool schema validation
  - Integration は `ANTHROPIC_API_KEY` 有時のみ実行 (`pytest.mark.skipif`)
  - `conftest.py` で `.env` 自動読込 (python-dotenv)

- **二段階変換アーキテクチャの確定**
  - v0.3 で方針化、v0.4 で Stage 2 (Haiku 4.5) を先行実装 (逆順実装)
  - Stage 1 (Opus 4.7 解釈) は未着手
  - `/api/compose` FastAPI 実装は次 phase

### v0.5 (2026-04-23)

**Phase 1 続き — FastAPI + Web クライアント 立ち上げ**

- **FastAPI エンドポイント**
  - `POST /api/compose`: `{ddl}` → `{score, svg}` (Stage 2 composer → Renderer を縦結合)
  - `GET /health`: liveness (`{ok: true}`)
  - CORS: `http://localhost:*` / `127.0.0.1:*` 許可 (regex ベース)
  - エラーハンドリング: composer 失敗 502, render 失敗 500, 入力不正 422
  - エントリポイント: `uv run inku-server` で `uvicorn` が `127.0.0.1:8000` reload 起動
  - テスト: `TestClient` + `monkeypatch` で composer バイパス、API キー不要で 5 cases pass

- **SvelteKit Web クライアント (`web/`)**
  - SvelteKit 2.57 + Svelte 5.55 (runes モード) + Vite 8 + TypeScript
  - 単一ルート `/`: 記述 textarea + 演奏 (SVG インライン表示) + 楽譜 (JSON Score collapsible)
  - スタイル: Renderer パレットと整合 (背景 #f7f5ef, 墨 #111)、和文フォント優先
  - 名前: `inku-web` v0.1.0
  - svelte-check: 0 error, 0 warning

- **次段階への布石**
  - `/api/compose` は Stage 2 のみ。Stage 1 (Opus 解釈) エンドポイントは未実装
  - 解釈フィードバック (書後色付け)、Saijiki 参照窓、Prev/Next 並置は UI 未着手
  - Renderer の揺らぎ (perlin/wave) 実装も未着手 (fixture 11/15 が variation 指定)

### v0.6 (2026-04-23)

**Phase 1 完了 — E2E パイプライン稼働 + UI 反復支援**

- **LLM バックエンド 二系統併存**
  - Claude Code hackathon:参加選考漏れに伴い、Loacl LLMの実装に変更
  - Stage 2 (composer): `qwen-api` (Qwen2.5-7B) 既定、Anthropic Haiku 4.5 併用可能
  - Stage 1 (interpreter): `qwen3-api` (Qwen3-8B) 既定、Anthropic Opus 4.7 併用可能
  - 切替: 環境変数 `INKU_LLM_BACKEND=openai|anthropic`
  - OVMS (`http://127.0.0.1:18000/v3`) は OpenAI 互換、API key=`none`
  - qwen3-api は `/no_think` prefix で thinking トレースを抑制して使用
  - tool_use は Anthropic ネイティブ、OpenAI 側は `<tool_call>` タグが content に埋め込まれるので正規表現で抽出

- **Stage 1 interpreter 実装**
  - `server/src/inku_server/interpreter.py`
  - 入力: 自由な自然言語、出力: Saijiki 語彙のみを使う短い日本語 (正規化DDL)
  - system prompt に 4 few-shot (感情語→物理語 置換、画面座標比率)
  - 5 ケース smoke test 全通過 (4 は prompt 内例と重複、memorize 傾向あり)

- **API エンドポイント 拡張**
  - `POST /api/interpret`: 自由記述 → 正規化DDL
  - `POST /api/paint`: 自由記述 → 正規化DDL → Score → SVG (フルパイプライン)
  - 既存 `POST /api/compose`, `GET /health` は維持
  - 起動時 env: `INKU_SERVER_HOST`, `INKU_SERVER_PORT` で上書き可

- **Stage 2 fidelity 記録 (qwen-api strict モード)**
  - 15 fixture 中 9 通過、残り 6 件の典型的な失敗:
    - center (円/楕円) と position (三角/四角) の混同
    - 「中央」指示時の bbox 左上補正未実施
    - 複数命令並列時の field 一括誤適用
  - tool_use API 経由で JSON 構造エラー (`]` vs `}` 誤閉じ等) は解消
  - Haiku 4.5 移行で改善見込みだが、ローカル LLM で回る事実を優先

- **Web UI: モード切替 + Saijiki 参照 + 反復履歴**
  - タブ: 自由記述 / 正規化DDL (それぞれ /api/paint と /api/compose に繋ぐ)
  - 自由記述モード: 解釈結果 (正規化DDL) を左カラム下部に常時表示
  - 歳時記ドロワー: 右スライドイン、9 カテゴリ (かたち/かたむき/てざわり/つらなり/いろ/ゆらぎ/ばしょ/うごき/わりあい)、chip クリックで textarea の caret 位置に挿入
  - Saijiki 辞書は `web/src/lib/saijiki.ts` に分離
  - 反復履歴: in-memory、最大 20 件、`◀ N/M ▶` 移動ボタンで input/output/DDL を過去状態に復元
  - サムネイル列: 履歴 2 件以上で下段に 96px 方形ミニチュア SVG を横並べ、クリックで jump

### v0.7 (2026-04-24)

**LLM 多モデル対応 + Stage 1 静止画強化 + thinking 可視化**

- **LLM モデル: UI から切替可能に**
  - `POST /api/compose`: `model` フィールド
  - `POST /api/interpret`: `model` フィールド
  - `POST /api/paint`: `stage1_model` / `stage2_model` フィールド
  - `compose()` / `interpret_detail()` に `model` キーワード引数追加、未指定時は env 既定
  - UI (モード切替下に `解釈` / `構造化` dropdown、localStorage 永続化): Qwen2.5-7B / Qwen3-8B / Gemma3-4B / Gemma3-12B

- **既定モデル**
  - Stage 1: `qwen3-api` (Qwen3-8B)
  - Stage 2: `qwen-api` (Qwen2.5-7B)
  - Gemma3-12B は 15 fixture に 6 時間要、実用外 (選択肢には残す)
  - Gemma3-4B は Score full schema + tool_choice 組合せで破綻 (bracket 出力異常、空白クォート連鎖)、prompt + schema 簡略化で動作するが品質は未検証

- **Stage 1 system prompt: 静止画原則 強化 (SPEC §2 原則5)**
  - 禁止動詞: 動く / 動かす / 広がる / 広げる / 流れる / 伸びる / 昇る / 落ちる / 散る / 沈む / 塗る
  - 使える動作動詞: 置く / 並べる / 引く / 描く / 散らす / 埋める
  - 動的→静的 言い換え 5 例 (月が昇る→右上に円、花が散る→細かい点を散らす 等)

- **Qwen3 thinking 可視化**
  - `interpret_detail()` が `(ddl, thinking)` tuple を返す
  - `include_thinking=True` で `/no_think` を外し、`<think>…</think>` 内容を分離保持
  - `POST /api/interpret`, `/api/paint` に `include_thinking` request フィールド、`thinking` response フィールド
  - UI: Stage 1 が qwen3 系のとき「思考を表示」checkbox、結果パネルに faded amber 色の `<details>` で内部思考表示 (作者の思考プロセス可視化)

### v0.8 (2026-04-24)

**Renderer 揺らぎ実装 + arc primitive**

- **line の variation を Renderer で生成** (SPEC §13.8 の核心)
  - 80 セグメントの polyline に変換、SHA-256(model_dump_json) でシード
  - quality 4 種: `wave` (sin), `perlin` (smoothstep 1D value noise), `pink` (2 オクターブ合成), `white` (per-segment hash)
  - amplitude: fine=4px / medium=12px / broad=30px (1000px canvas 上)
  - frequency: slow=2 / medium=6 / high=14 cycles/線長
  - dimensions 適用: `position_x` / `position_y` 単独は該軸揺らぎ、両方指定は線に垂直方向揺らぎ
  - 決定的: 同一 Score → byte 一致 SVG (test 保証)
- **arc primitive 本実装**
  - Schema: `angle_start` / `angle_end` (度、0°=東、CCW 正)
  - Renderer: `<path d="M ... A r r 0 large sweep x y">` で弧描画
  - large-arc-flag: `(end-start) % 360 > 180`、sweep-flag: `end > start` で 0 (CCW)
  - Composer prompt に 弧 行追加、1/4円 / 半円 の角度例
- **新規 test 7件** (arc quarter / half / missing-angles、variation perlin / wave / deterministic / quality=none)

### v0.9 (2026-04-25)

**プロンプト非線形化 + NVIDIA NIM 対応 + arrangement 実装**

#### プロンプト設計の構造改善 (主要変更)

機能追加でプロンプトが際限なく長くなる問題を、MT (機械翻訳) のスペック / コーパス分離原則を援用して構造的に解決。

- **schema.py を仕様の正典 (Source of Truth) に**
  - 全フィールドに日本語 ↔ 値マッピングを含む `description` を付与
  - LLM はツールスキーマの description を直接参照 → SYSTEM_PROMPT にフィールド説明を繰り返す必要がなくなる
  - 新プリミティブ追加 = スキーマ更新のみ。SYSTEM_PROMPT は変えない

- **composer.py: SYSTEM_PROMPT を手順のみに削減**
  - 3,942 chars → 1,072 chars (-73%)
  - 変換例は最重要パターン 4 件に絞る (残りはスキーマ description が補う)

- **interpreter.py: EXAMPLE_POOL + 動的例選択**
  - `EXAMPLE_POOL`: `{keywords, input, output}` タプルのリスト (現在 12 件)
  - `_select_examples(text, k=3)`: 入力とのキーワード一致数でスコアリングし上位 k 件を選択
  - `_build_system_prompt(text)`: PREFIX + 選択された k 件を推論ごとに構築
  - 例を何件追加してもプロンプト長は固定 (PREFIX + 3 件)
  - SYSTEM_PROMPT モジュール変数はプレフィックスのみを公開 (`/api/prompts` 互換)

- **レイテンシ効果**: 322.7s → 21.5s (同一出力、NVIDIA Gemma 4 31B、15x 高速化)

#### NVIDIA NIM プロバイダー追加

- `google/gemma-4-31b-it` を第一・第二段階の既定モデルに設定
- モデル ID による自動ルーティング:
  - `anthropic:<model>` プレフィックス → Anthropic API
  - `/` を含む ID → NVIDIA NIM (`https://integrate.api.nvidia.com/v1`)
  - その他 → OVMS (ローカル OpenAI 互換)
- UI: プロバイダー選択 (NVIDIA NIM / Anthropic / ローカル) + モデル選択の 2 段 dropdown、localStorage 永続化
- `web/src/lib/models.ts` に `PROVIDER_GROUPS` 構造を追加

#### arrangement フィールド (本数・個数の JSON サイズ問題)

N 個の instruction を展開すると JSON が N 倍になる問題を解決。Renderer 側で展開することで JSON は常に O(1)。

- **schema.py**: `Arrangement` モデル追加 (`count` / `layout` / `path` / `margin` / `center` / `radius`)
- **renderer.py**: `_anchor()` / `_shift()` / `_expand_arrangement()` — Renderer 側で N 個に展開
  - layout: `horizontal` / `vertical` / `radial` / `scatter` (基本配置)
  - path: `none` / `diagonal` / `wave` / `top_to_bottom` / `left_to_right` / `right_half` (軌跡指定)
  - `count=1` は展開せず単体返却。`ge=2` → `ge=1` に変更 (バリデーションエラー防止)
- **interpreter.py EXAMPLE_POOL**: 数量表現を 1 文でまとめる例、ランダム配置例を収録
- **composer.py**: arrangement 使用を SYSTEM_PROMPT で強制、複数 instruction 生成を禁止

#### UI 改善

- 正規化DDL タブ削除 (常に自由記述モード = `/api/paint`)
- 履歴サムネイルに経過秒数を表示 (`Iteration` に `elapsed_ms` 追加)
- `GET /api/prompts` エンドポイント追加 → 出力欄「プロンプト (デバッグ)」パネルで Stage 1 / 2 のシステムプロンプトと実際の入力を表示
- キャンバス背景色を白に変更 (`#f7f5ef` → `#ffffff`)
- 推論中ライブタイマー + 完了後「解釈 Xs + 構造化 Ys = Zs」内訳表示

---

### v1.0 (2026-04-25)

**大量描画対応 + Renderer 堅牢化 + Stage 1 属性保持強化 + 学習モード + サーバーサイド履歴**

#### 大量オブジェクト描画 (count 上限 500)

「100本の線」「200個の円」を実際に描画できるようアルゴリズムを改良。

- **schema.py**: `Arrangement.count` 上限 50 → 500、`_clamp_count` validator も同様
- **renderer.py**: 固定10点 `_SCATTER_POSITIONS` を廃止。`_scatter_pos(i, seed, margin)` を追加
  - SHA-256 hash ベースの決定的ランダム座標生成 — N 個任意対応
  - 同一 Score → 同一 SVG の決定性を維持 (seed = instruction の hash)
- **interpreter.py**: 「100本・200個 → 30程度に丸める」規則を撤廃、具体的な数はそのまま通す
- **composer.py**: count 上限説明を 50 → 500 に更新

#### Renderer: line from/to 省略時の fallback

LLM が arrangement 付き line を生成するとき `from`/`to` を省略するケースがあり `render failed` エラーが発生していた問題を修正。

- `_ensure_line_coords(ins)` を追加: layout から方向を推定してデフォルト座標を補完
  - `layout="vertical"` → 横線 (`[0.0, 0.5]`→`[1.0, 0.5]`)
  - その他 (`horizontal` / `scatter` / `radial`) → 縦線 (`[0.5, 0.0]`→`[0.5, 1.0]`)
- `_expand_arrangement` 入口で呼び出し (arrangement 展開前に補完)
- `_render_instruction` でも arrangement なし line に同様の fallback を適用 (raise を除去)

#### Stage 1 属性保持強化

記述の解釈時に色・素材・方向・揺らぎが脱落する問題を構造的に修正。

- **`# 属性保持 — 脱落禁止` セクション追加**
  - 「感情語の除去だけが正規化であり、属性の省略は誤り」を明示
  - いろ / てざわり / 太さ / 方向・ばしょ / ゆらぎ / 配置パターン の保持を個別明記
- **数量表現ルール更新**: 「色・素材・方向とともに 1 文に」収める例を追加
- **EXAMPLE_POOL**: 12件 → 21件 (+7件)
  - 追加例: クレヨン+色+数量、鉛筆+細さ、震える複数線、右半分+色+数量、300本のクレヨン、地平線構成、チョーク+滲み
- **k: 3 → 5** — 複合属性入力での例参照数を増加

#### 学習モード (SSE ストリーム)

コーパスを自動拡張するバックグラウンド学習機能を追加。

- **`trainer.py` 新規作成**
  - `VARIATION_STYLES` (5スタイル): 詩的・口語・抽象・自然現象・擬音語をローテーション
  - `generate_sample(style_idx, model)`: 指定スタイルで記述サンプルを LLM 生成
  - `run_one_iteration(style_idx, model)`: 生成 → `interpret_detail` → EXAMPLE_POOL 追加
  - `add_learned_example(input, ddl)`: EXAMPLE_POOL へ追記 + `INKU_LEARNED_FILE` に永続化
  - `load_learned_examples()`: 起動時に永続化済みコーパスを EXAMPLE_POOL へ注入
  - `clear_learned_examples()`: auto エントリのみ削除、static 例は保持
  - backend dispatch: interpreter.py と同じ anthropic / nvidia / ovms ルーティング
- **`api.py` 追加エンドポイント**
  - `GET /api/train?n=&model=` → SSE ストリーム (`progress` / `result` / `error` / `done` イベント)
  - `GET /api/train/stats` → `{"learned_count": N}`
  - `DELETE /api/train` → コーパスクリア
  - `asyncio.to_thread` で sync LLM 呼び出しを非同期化
  - `request.is_disconnected()` でクライアント切断を検出してループを停止
- **Web UI** (学習モードパネル)
  - 折り畳み式パネル、イテレーション数入力、モデル選択
  - リアルタイム進捗バー (shimmer アニメーション)、ログ表示
  - 停止ボタン → EventSource close → サーバーループも次イテレーション前に停止
  - `onMount` で初期 `learned_count` を取得

#### サーバーサイド履歴 (無制限・ページネーション)

localStorage の容量制限を解消し、セッション跨ぎの履歴を実現。

- **`api.py`**: `_history: list[dict]` をメモリ保持 + `_HISTORY_FILE` (既定 `/tmp/inku-history.json`) に永続化
- エンドポイント: `GET /api/history?offset=&limit=` (新着順)、`POST /api/history`、`DELETE /api/history`
- **Web UI**: `HISTORY_PAGE_SIZE=10`、`← 新` / `旧 →` ページナビ、全件数表示

#### UI 改善

- **歳時記ボタン**: ヘッダー → 記述エリア右上 (`<div class="input-header">`) に移動
- **Saijiki トークン色**: `#111` → `#2c3e91` (青) でインライン表示

---

### v1.1 (2026-04-25)

**coerce レイヤー + 背景色 + 配色サイクル + 塗りつぶし + 非 Saijiki 語展開 + UI 改善**

#### coerce.py — テーブル駆動の構造補修レイヤー (新規)

LLM が必須フィールドを省略した Score を renderer に渡す前に自動補修する `coerce.py` を新規作成。

- **設計原則**: primitive 個別の if/elif を書かない。`FieldSpec` dataclass + `PRIMITIVE_SPECS` テーブルで要件を宣言し、汎用ループで適用。新 primitive 追加 = テーブルにエントリ追記のみ
- **`FieldSpec`**: `name / default / fallbacks (cross-field 代替) / coerce (型正規化関数)` を宣言
- **`PRIMITIVE_SPECS`**: 6 primitive (line/circle/ellipse/arc/square/triangle) の必須フィールド仕様
  - fallback 例: circle の `center` 欠損時は `position` を代用
  - 型正規化: `_as_coord / _as_positive_float / _as_positive_size / _as_float`
- **`POST_COERCE`**: cross-field 制約 (arc の `angle_start == angle_end` → +270° 補正)
- **`api.py`**: `/api/compose` / `/api/paint` 両エンドポイントで `render()` 前に `coerce_score()` を呼び出し

#### 閉じた形状の自動塗りつぶし

- `_CLOSED_SHAPES = frozenset({"circle", "ellipse", "square", "triangle"})`
- `_stroke_attrs()`: `do_fill = ins.primitive in _CLOSED_SHAPES or ins.filled` — 閉形状は色指定で自動塗りつぶし
- `Instruction.filled: bool = False` フィールドを schema.py に追加 (明示的塗りつぶし指定)

#### 背景色 (Score.background)

- `Score.background: Color = "white"` フィールド追加
- `renderer.render()`: `COLOR_MAP.get(score.background, BACKGROUND)` でキャンバス全体を背景色で塗りつぶし
- Stage 2 プロンプトに background ルール追加

#### 配色サイクル (Arrangement.color_cycle)

- `Arrangement.color_cycle: list[Color]` フィールド追加 (デフォルト空 = 全要素同色)
- `_apply_color_cycle(items, cycle)`: arrangement 展開後に `i % len(cycle)` で色を上書き
- 全 layout (horizontal / vertical / radial / scatter) で適用

#### count 上限 1000 へ拡張

- `Arrangement.count` 上限 500 → 1000、`_clamp_count` validator も更新
- composer.py / interpreter.py のプロンプト記述も同様に更新

#### Stage 2: original_text パス・スルー

- `compose(ddl, *, original_text=None)` に引数追加
- `_build_user_message(ddl, original_text)`: 原文と正規化DDL が異なる場合 `[原文]…[正規化DDL]…` 形式でユーザーメッセージを構成
- `/api/paint` で `req.text` を Stage 2 に渡すよう改善 → LLM が元の記述の意図をより正確に反映

#### 非 Saijiki 語の LLM 意味展開

- Stage 1 `SYSTEM_PROMPT_PREFIX` に `# 非 Saijiki 語の展開` セクションを追加
  - 展開の四つの切り口: 形状 / 質感 / 構造 / 動作→配置
  - 例: 月→円、霧→楕円(滲む)、森→縦線を複数、散る→ランダムに散らす
- 固定辞書アプローチ (`expansion.py`) を削除 — LLM の意味理解に委ねる方針に転換
- EXAMPLE_POOL に自然現象・詩的語彙の例 9 件追加 (太陽、星空、水平線+月、山並み、森、雪、炎、都市、花びら)

#### Web UI 改善

- **タブ切り替え**: 演奏 / 楽譜 / プロンプト の 3 タブ (旧: 垂直展開)。新しい結果が来ると自動的に「演奏」タブに戻る
- **ビルド番号**: `vite.config.ts` に `.build-number` ファイルベースのインクリメント機構を追加。ヘッダー左上に `#N` 表示
- **接続先 / モデル ラベル**: 「接続先：」「モデル：」を明記
- **プロンプト表示順**: Stage1ユーザー入力 → Stage1システム → Stage2ユーザー入力 → Stage2システム (文脈順)

---

### v1.2 (2026-04-25)

**バッチモード + 演奏ステージ可視化 + 学習モード廃止 + わりあい語彙追加**

#### バッチ記述モード

- 入力欄に「記述 / バッチ」タブを追加
- バッチタブ: 改行区切りで複数の記述を入力、左端に行番号を自動表示
- 順次処理: 演奏中は「N / M 番目を演奏中…」と表示、停止ボタンで中断可能
- 各結果を履歴に保存し、最後の結果がキャンバスに残る

#### 演奏中ステージ可視化

- フロントエンドの処理方式を `/api/paint` 1 コール → `/api/interpret` + `/api/compose` の 2 コール方式に変更
- 演奏中に「解釈中…」「構造化中…」をステージラベルとして経過秒と並べてリアルタイム表示
- `ComposeRequest` に `original_text` フィールド追加 (Stage 2 が元の記述を参照して属性補完に活用)

#### 学習モード廃止

- Web UI の学習モードパネルを削除
- `GET /api/train`・`GET /api/train/stats`・`DELETE /api/train` エンドポイントを削除
- 起動時の EXAMPLE_POOL 注入ルーティングも削除 (`trainer.py` は実験的ユーティリティとして残置)

#### Web UI 改善

- 出力タブ順変更: 演奏 → プロンプト → 楽譜 (旧: 演奏→楽譜→プロンプト)
- プロンプト表示領域拡大: ユーザー入力 max-height 160px、システムプロンプト 400px、外枠 680px
- 履歴に `stage1_model` / `stage2_model` を記録 (サムネイルの title で確認可)

#### Saijiki わりあいカテゴリ追加

- 新カテゴリ `わりあい (proportions)`: 縦長・横長・全幅・半幅・半円・上弦・下弦・三日月
- Stage 1 `SYSTEM_PROMPT_PREFIX` に `# わりあい` ルールセクション追加 (縦横比・線長・月形→角度の変換原則)
- Stage 2 `SYSTEM_PROMPT` にわりあい JSON マッピング例 7 件追加
- `EXAMPLE_POOL` に 8 件追加 (縦横比 2・線長 2・弧月 4)
- `saijiki.ts` に `わりあい` カテゴリを追加

---

### v1.3 (2026-04-26)

**Saijiki スナップショット + トークン表示 + ダウンロード + i18n**

#### Saijiki スナップショット

**注記**: この機能は v1.11 で歳時記 v1 仕様確定まで一旦削除。以下は v1.3 時点の履歴として残す。

特定時点のシステムプロンプト状態を名前付きで保存・呼び出す機能を追加。

- **`server/src/inku_server/snapshots.py` 新規作成**
  - `create_snapshot(name, stage1_prefix, stage2_prompt)` → UUID + タイムスタンプ付きで保存
  - ストレージ: `/tmp/inku-saijiki-snapshots.json` (env var `INKU_SNAPSHOTS_FILE`)
  - `list_snapshots()` / `get_snapshot(id)` / `delete_snapshot(id)` の CRUD
- **API エンドポイント追加**
  - `GET /api/saijiki/snapshots` → `list[SnapshotMeta]`
  - `POST /api/saijiki/snapshots` → スナップショット作成
  - `DELETE /api/saijiki/snapshots/{id}` → 削除
- **スナップショット適用**: `InterpretRequest` / `ComposeRequest` / `PaintRequest` に `snapshot_id` フィールド追加。推論時に一致するスナップショットのプロンプトを上書き
- **設計**: Stage 1 はプレフィックス (`SYSTEM_PROMPT_PREFIX`) のみ保存し、EXAMPLE_POOL の動的例選択は引き続きリアルタイム動作。スナップショットはプレフィックスの変更のみをキャプチャ
- **Web UI**: スナップショットパネル (折り畳み式) を歳時記エリアに追加。現在設定表示・名前入力・保存・削除・選択適用

#### トークン数トラッキング

LLM の消費トークンを処理中に表示し履歴にも記録。

- **`interpreter.py`**: `interpret_detail()` が `(ddl, thinking, tokens_in, tokens_out)` の 4-tuple を返すように変更
  - Anthropic: `resp.usage.input_tokens / output_tokens`
  - OpenAI/OVMS: `resp.usage.prompt_tokens / completion_tokens`
  - いずれも `getattr` で安全取得 (未対応モデルは `None`)
- **`composer.py`**: `compose()` が `(Score, tokens_in, tokens_out)` の 3-tuple を返すように変更
- **`api.py`**: `InterpretResponse` / `ComposeResponse` / `PaintResponse` に `tokens_in / tokens_out` フィールド追加
- **Web UI**: 処理中の「構造化中…」ラベルにトークン数をリアルタイム表示。履歴サムネイルに `{in}→{out}tok` 表示

#### ダウンロード機能

完成した作品を SVG および複数解像度の PNG で保存可能に。

- **SVG ダウンロード**: `<desc>` タグに元の記述テキストを埋め込んで出力。`svgWithDesc()` 関数で `<svg ...>` の直後に挿入
- **PNG ダウンロード**: 4 解像度 (1080 / 2160 / 1024 / 2048px) をブラウザ Canvas API で変換
  - SVG に `width` / `height` 属性を注入し `Image` に描画 → Canvas → `toBlob('image/png')` → `<a>` 要素でダウンロード
  - Canvas 背景は白 (`#ffffff`) でプリフィル (透過 PNG にならないよう)
- **UI**: キャンバス下部にダウンロードバーを追加。`↓ SVG` ボタン + `PNG:` ラベル + `1080 / 2160 / 1024 / 2048` ボタン

#### 履歴: モデル名・トークン数表示

- 履歴サムネイルに Stage 2 使用モデルの短縮名 (`shortModel()`) を表示
- `Iteration` 型に `tokens_in / tokens_out` フィールド追加
- `HistoryPostBody` にも `tokens_in / tokens_out` を追加してサーバー側履歴にも記録

#### ハッカソン関連テキスト削除

UI 全体からハッカソン関連の記述を削除。

#### i18n — 日英言語パック

UI の日本語 / 英語切り替えを実装。将来の多言語対応を設計から内包。

- **`web/src/lib/i18n/types.ts`**: `LangPack` インターフェース定義
  - 単純文字列フィールドと関数フィールド (`batchCount(n)`, `stageStructuring(tok)`, `tokenSummary(...)` 等) を混在
- **`web/src/lib/i18n/ja.ts`** / **`en.ts`**: 日本語・英語パックを個別ファイルで管理
- **`web/src/lib/i18n/index.svelte.ts`**: Svelte 5 `$state` ベースの言語ストア
  - `t()` 関数でアクティブパックを返す (テンプレート内 `t().key` で全文字列を参照)
  - `setLang(code)` + `localStorage` 永続化
  - 新言語追加: `types.ts` にパック実装 + `PACKS` に登録するだけ
- **`+page.svelte`**: 全ハードコード文字列を `t().xxx` に置き換え。`$derived.by(() => t().tokenSummary(...))` パターンで複合 derived を実装
- **ヘッダー**: 言語切り替えボタン (`日本語` / `English`) をヘッダー右上に配置

---

### v1.4 (2026-04-26)
SPEC.mdの内容精査。

### v1.5 (2026-04-26)


#### UI 修正

- **canvas max-height 追加**: `.canvas { max-height: 480px }` を設定。`aspect-ratio: 1/1` のみでは canvas がビューポート幅（~560px）まで拡大し、history strip がビューポート外に押し出されていた問題を修正
- **履歴 each キー修正**: `{#each historyItems as it, i (it.at)}` → `(it.id ?? it.at)`。同一タイムスタンプで複数アイテムが記録された場合の重複キーを解消。`Iteration` 型に `id?: string` 追加

### v1.6 (2026-04-27)

**UI全面再設計 + 色カタログシステム + 再演奏機能**

#### レイアウト刷新

旧来のスクロール型ページ（max-width: 1200px）から、固定ビューポートの2ペイン構成へ全面移行。

```
[ヘッダー]                          固定
[左パネル 440px] | [右パネル flex]  flex: 1 / overflow: hidden
[履歴ストリップ]                     固定（下部）
```

- **左パネル**: 記述/バッチ タブ → 指示 → 演奏する → 語彙ハイライト → 解釈DDL → 再演奏 → 統計折りたたみ。`overflow-y: auto` で内部スクロール
- **右パネル**: タブバー（描画/プロンプト/JSON）→ キャンバスエリア → エクスポートバー
- **履歴ストリップ**: 82px サムネイル横スクロール。ページネーション「← 新 / 旧 →」。現在表示中に「表示中」バッジ

#### 接続設定ポップオーバー

Stage 1 / Stage 2 モデル選択を「⚙ 接続設定」ボタン → ポップオーバーに集約。旧 model-row は廃止。スナップショット選択は v1.11 で歳時記 v1 仕様確定まで削除。

#### 再演奏機能

解釈DDL ボックス直下に「↺ 再演奏」ボタン追加。`/api/compose` のみ呼ぶ（Stage 1 スキップ）。DDL を手動編集後に再レンダリングするユースケースを想定。進捗バー表示付き。

#### ズームUI

右パネルキャンバス下部中央に固定配置。`−` / `＋` / `⊙`（リセット）。範囲 0.5×〜3×（0.25 刻み）。`transform: scale()` をキャンバスコンテナに適用。

#### ナビゲーション・エクスポート

- `‹` / `›` ボタンをキャンバス左右端に絶対配置（円形 38px）
- 枚数カウンター（N / total）を `›` ボタン下に表示（画像に重ねない）
- `↓ SVG` + `↓ PNG ▾`（ドロップダウン: 1080px / 2160px / 1024px / 2048px）

#### 歳時記ドロワー刷新

右端からのスライドイン式ドロワー（幅 0 → 280px、`cubic-bezier(0.4,0,0.2,1)` 0.25s）。カテゴリ見出しを明朝体（ja / en 並記）、語彙をミニマルトークンボタン。ヘッダーの「歳時記」テキストリンク + 左パネルの「歳時記」ボタン両方からトグル。

#### 色カタログシステム

**フロントエンド**: 初期実装では `web/src/lib/colors.ts` にカタログ定義を持った。v1.25 以降はサーバー側 `GET /api/color-catalogs` を正本とし、フロントエンドは取得した一覧を表示・選択に使う。

```typescript
type ColorMap = Record<'white'|'black'|'blue'|'red'|'green'|'gray', string>;
```

- `default`（規定値）= 既存 `renderer.py` COLOR_MAP と完全一致
- 追加10種: Ink & Season / Fresco Study / Open-Air Light / Ink & Porcelain / Cool Material / Dye & Earth / Desert Mineral / Vivid Material / Weathered Heritage / Sea & Stone
- 各カタログは `map`（6色 ColorMap）+ `swatches`（表示用8色）+ `palette`（名称付き8色）を持つ
- `default` は文化的な標準ではなく neutral baseline として扱う。追加カタログの `id` / 表示名 / 説明は、国名・民族名・食・祭り・帝国・観光記号で文化全体を代表しないよう、素材・光・技法・描画上の振る舞いを基準に命名する。
- カタログの `map` は `white / black / blue / red / green / gray` の抽象色としての意味を壊さないことを優先する。特徴色は `palette` に逃がし、`blue` が pink へ、`gray` が terracotta へ、`black` が navy へ変わるような意味崩れを避ける。
- Build 265 時点の残課題として、`open_air_light`, `dye_earth`, `desert_mineral` は背景・暗色・高彩度差し色が作品全体を支配しやすい。今後の調整は個別プロンプト最適化ではなく、core color の明度・彩度・背景化しやすさを抑える方向で行う。
- Build 266 では上記3カタログの core color を少し軽くし、背景・暗色・高彩度差し色の支配を抑えた。`default.sub` は英語UI向けに `neutral baseline` とし、日本語UI向け説明は `sub_ja` に分離する。
- カタログ詳細色は `palette[].name` を英語の正本表示名とし、対応する日本語名がある場合は `palette[].name_ja` を併記できる。日本語UIでは `English（日本語）` と表示し、英語UIでは `name` のみ表示する。

「カタログ設定」モーダル（ヘッダー右端）から選択。選択は `localStorage` に永続化。

**バックエンド**: `renderer.render()` に `color_map: dict[str, str] | None = None` パラメータ追加。初期実装では `ComposeRequest` / `PaintRequest` の `color_map` フィールドで演奏ごとに選択中のカタログ色マップを受け取った。v1.25 以降は `catalog_id` を受け取り、サーバー側の色カタログ定義からレンダリング用 `color_map` を解決する。

#### 色ニュアンス `color_hint`

JSON Score の各 `instruction` は任意の `color_hint` を持てる。`color` は従来どおり `white / black / blue / red / green / gray` の抽象色とし、`color_hint` には「桜色」「朱に近い赤」「冷たい青緑」など、指示に含まれた具体的な色ニュアンスを短く保存する。

Stage 2 は具体色を抽象色へ丸めつつ、元のニュアンスを `color_hint` に保持する。Renderer は選択中の色カタログの `map` と `palette` を受け取り、`color_hint` がある場合はパレット名・色相ヒントを使ってより近い実色を選ぶ。ヒントがない場合、または解決できない場合は従来どおり `color` の抽象色を使う。

#### その他

- ビルド番号表示: `#N` → `Build N`
- 進捗バー: ステージインジケーター（✓ 完了 / ● 実行中アニメーション）+ 経過時間 + 停止ボタン + フェーズラベル

### v1.7 (2026-04-27)

**UI 8改善 — 感情語ヒント注入 + 履歴 catalog_id 保存 + ナビ修正**

#### 感情語 → DDL ヒント自動注入

Stage 1 解釈時に感情語を検出し、DDL語彙への変換ヒントを入力末尾に付加。

- **`EMOTION_DDL_MAP`** (16語): 「美しい」「激しい」「静かな」「儚い」「神秘的」等 → weight/variation/color の具体値を対応付け
- `buildEmotionHint(text)`: `annotate()` で `kind === 'emotion'` を抽出 → ヒント文字列生成
- Stage 1 API 送信直前に `text + buildEmotionHint(text)` を `augmented` として送信 (表示テキストは変更なし)

#### 履歴 catalog_id 保存

選択中の色カタログを履歴レコードに永続化。

- **`db.py`**: `HistoryRow` に `catalog_id VARCHAR` カラム追加。`_migrate_columns()` で `ALTER TABLE ADD COLUMN` (既存 DB への無害マイグレーション)
- **`api.py`**: `HistoryPostBody` に `catalog_id: str | None` 追加
- **frontend**: `PaintResult` 型 + `pushHistory` 呼び出しに `catalog_id` 追加。`selectedCatalog !== 'default'` のときのみ保存

#### 歳時記ボタンをヘッダーから削除

入力エリアの歳時記ボタンを残し、ヘッダーリンクを削除。

#### 入力内語彙表示ボックス削除

`result && inputMode === 'single'` のときに表示していた「入力に含まれた語彙」セクション (`annot-box`) を削除。感情語はヒント注入で活用するため、インライン表示は不要と判断。

#### ヒストリーストリップの動的幅

`visibleThumbCount = Math.max(1, Math.floor((windowWidth - 40) / 89))` でウィンドウ幅に応じてサムネイル表示数を動的決定。`window.resize` イベントで `windowWidth` を更新（`onMount` で listener 登録 + cleanup）。

#### ナビ矢印方向の修正

`‹`（左） = 新しい（newer）、`›`（右） = 古い（older）に修正。旧実装では `‹`/`›` と `gotoPrev`/`gotoNext` の対応が逆だった。

#### エクスポートファイル名の統一

`slugify(input)` ベースから日時スタンプ形式へ変更。

- 形式: `inku-YYYY-MM-DD-HH-MM[-size].ext`
- `exportFilename(ext, size?)` ヘルパー関数を追加
- SVG / PNG 両方に適用

#### CSS 修正

- `.prompt-area` と `.prompt-pre` に `align-self: stretch; min-height: 0` を追加 → プロンプトタブの縦スクロールが正常化
- `.thumb-strip` を `overflow: hidden` に変更 (横スクロール廃止、`visibleThumbCount` でクリップ)

---

### v1.8 (2026-04-27)

**てざわり→weight 変換修正 + 滲む SVG フィルター実装**

#### てざわり → weight フィールド変換の修正 (`composer.py`)

**問題**: Stage 1 が正規化DDL に「青いクレヨンの縦線」と正しく出力していても、Stage 2 (composer.py) には `weight` フィールドへの変換例・指示が一切なく、常にデフォルト `pen` が出力されていた。

**修正内容**:
- `SYSTEM_PROMPT` / `SYSTEM_PROMPT_EN` に「てざわり → weight 変換 (必須)」セクションを追加
  - 素材語10種 (髪・鉛筆・ペン・ロットリング・クレヨン・チョーク・細筆・太筆・ビュラン・ドライポイント) と対応 weight 値の対応表
  - 4 つの変換例: クレヨン/鉛筆/チョーク+滲む/太筆
- `EXAMPLE_POOL` に てざわり例を追加: 太筆・ロットリング・チョーク・ビュラン・ドライポイント (日本語)、thick-brush・chalk・burin・drypoint (英語)

**影響範囲**: `server/src/inku_server/composer.py`, `server/src/inku_server/interpreter.py`

**次のステップ**: `server/tests/fixtures/stage2/` にてざわりフィクスチャ (16〜20 番) を追加して regression を防ぐ。

#### 滲む (quality=pink) → SVG feGaussianBlur 実装 (`renderer.py`)

**問題**: `variation.quality = "pink"` が JSON Score に含まれても、renderer が blur フィルターを生成していなかった。

**実装内容**:
- `BLUR_STD` dict: `{fine: 2.0, medium: 6.0, broad: 15.0}` (pixel単位 stdDeviation)
- `_needs_blur(v)`: quality=pink のとき True を返す判定関数
- `render()`: blur 必要な要素に id を付与し `_inject_blur_filters()` でまとめてフィルター定義を `<defs>` に注入
- `_inject_blur_filters()`: `<defs />` / `<defs/>` / `<defs>` の3形式に対応 (svgwrite の出力方言差吸収)

**フィルター設計**: 要素ごとではなくアンプリチュード別に1つのフィルター定義 (`blur-fine`等) を共有し、SVGサイズを最小化。

---

### v1.9 (2026-04-29)

**UI polish branch — 描画体験整理 + 履歴管理強化 + 運用安全化**

#### 用語整理

UI 上の作品生成表現を「演奏」から「描画」へ寄せた。

- メイン実行ボタンは「描画」
- Stage 2 のみ再実行するボタンは「解釈から描画」
- 再描画ボタンは通常の描画ボタンと区別できる青系配色
- 出力タブや画面文言も「描画」中心に更新

#### ボタン配置整理

- ヘッダーの「接続設定」を「設定」に改名
- Stage 1 / Stage 2 のモデル選択は「モデル選択」ボタンとして独立
- 「モデル選択」はモデル選択のみを表示
- 「設定」は DB設定 / プラグイン / ユーザー管理 / その他を表示
- 「色カタログ」ボタンを指示エリアへ配置
- 「歳時記」ボタンを解釈（正規化DDL）エリアへ移動し、編集ボタンの左に配置
- 「新規作成」ボタンをやや目立つ暖色系デザインに変更

#### 色カタログ UI

- 色カタログダイアログを 2 ペイン化
- 左にカタログ一覧、右に選択中カタログの詳細色一覧を表示
- カタログ名を「カタログ設定」から「色カタログ」に変更

#### 鳥アニメーション

- 進捗バー内の小鳥に加え、描画中 / 再描画中に画面左上領域を飛ぶ小鳥を追加
- 小鳥を大きく、ゆっくり、のんびりした動きに調整
- 設定 > その他で「小鳥を表示する」On/Off を追加

#### 設定ダイアログ拡張

- DB設定タブ: SQLite / PostgreSQL 入力 UI と接続テスト表示
- プラグインタブ: プラグイン一覧、追加、削除 UI
- ユーザー管理タブ: ユーザー名 / パスワード / グループ、ユーザー追加・削除、グループ追加・削除 UI
- その他タブ:
  - 小鳥の表示 On/Off
  - 白背景時アルファチャンネル設定 On/Off
  - 解釈を再編集した場合も新バージョンとして保存する On/Off

**注意**: v1.9 時点では DB / プラグイン / ユーザー管理はフロントエンド上の prototype UI だった。v1.10 でユーザー管理は DB/API 接続済みとなったが、DB設定変更とプラグイン読込は引き続き未接続。

#### 履歴ストリップ / 履歴管理

- 履歴タイトルをボタンとして視認しやすい pill 表示へ変更
- 履歴サムネイル hover で保存内容を表示:
  - Stage 1 / Stage 2 モデル
  - 保存時間
  - 秒数
  - 色カタログ
  - token in/out
  - 入力プレビュー
- 表示列数に応じてページ移動ボタン文言を「新しい N 件」「古い N 件」に変更
- 履歴管理ダイアログを追加:
  - サムネイルタブ: 履歴ストリップと同系のタイル表示
  - リストタブ: 一覧テーブル表示
  - 検索
  - 複数選択
  - ごみ箱移動 / 復元 / 完全削除
- 履歴管理ダイアログの高さを固定し、検索結果件数の変化でウィンドウ縦位置が動かないよう修正

#### 履歴 DB / API

- `history.trashed` カラム追加
- `GET /api/history?trashed=true` 対応
- `POST /api/history/trash`
- `POST /api/history/restore`
- `POST /api/history/permanent-delete`
- 履歴管理の全件取得は FastAPI の `limit <= 100` 制限に合わせ、100 件単位のページングで取得

#### PNG 書き出し

- 設定 > その他の「白背景時アルファチャンネル設定」に応じて、PNG export 時の白背景 prefill を切替

#### ビルド番号

- `.build-number` の自動増分方式を廃止
- `web/BUILD_NUMBER` を Git 追跡対象に変更
- アプリに変更を加えるたびに `BUILD_NUMBER` を明示的に更新する運用へ移行

#### 既知課題（v1.9 review）の解決状況

- 設定ダイアログの DB / プラグイン状態表示は v1.11 で read-only API に接続済み
- Saijiki スナップショットは歳時記 v1 仕様確定まで一旦削除
- 履歴管理は v1.11 でサーバー検索 / ページングへ変更済み
- 出力ファイル保存失敗は v1.11 以降でサーバーログへ記録
- バッチ描画の行単位失敗は v1.11 以降で UI に保持表示

### v1.10 (2026-04-29)


#### 認証 / ユーザー管理

設定 > ユーザー管理タブを prototype UI から DB/API 接続済みの管理画面へ更新した。

- ユーザーアカウントを DB に永続化
- アカウント属性:
  - ユーザー名
  - メールアドレス
  - パスワード
  - ユーザー種類
  - 所属ユーザーグループ
- ユーザー種類:
  - 管理者: 全設定、ユーザー管理、ユーザーグループ追加・削除・管理が可能
  - グループリード: 自分のユーザーグループ内の一般ユーザー管理が可能
  - ユーザー: 作品制作が可能
- ユーザーグループは教室やイベントのチーム単位として扱う。グループ内作品共有は将来機能
- パスワードは PBKDF2-SHA256 + 16 byte salt + 310,000 iterations でハッシュ化して保存
- セッション token は SHA-256 hash のみ DB に保存
- 初回起動時、ユーザーが存在せず `INKU_BOOTSTRAP_ADMIN_PASSWORD` が設定されている場合のみ bootstrap admin を作成
  - username: `admin`
  - email: `admin@local`
  - password: `INKU_BOOTSTRAP_ADMIN_PASSWORD` の値。8文字以上必須
  - 環境変数 `INKU_BOOTSTRAP_ADMIN_USERNAME` / `INKU_BOOTSTRAP_ADMIN_EMAIL` で username / email を上書き可
  - `INKU_BOOTSTRAP_ADMIN_PASSWORD` 未設定時は既知のデフォルトパスワードを持つ admin を作成しない
  - ローカル開発で従来の `inku-admin` を使う場合のみ `INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN=1` を明示する

#### ユーザー管理 API

- `POST /api/auth/login`
- `GET /api/auth/me`
- `PATCH /api/auth/me/profile`
- `PATCH /api/auth/me/settings`
- `GET /api/auth/me/batch-prompt-history`
- `PUT /api/auth/me/batch-prompt-history`
- `POST /api/auth/logout`
- `GET /api/user-groups`
- `POST /api/user-groups`
- `DELETE /api/user-groups/{group_id}`
- `GET /api/users`
- `POST /api/users`
- `PATCH /api/users/{user_id}`
- `DELETE /api/users/{user_id}`

ロール制御:

- admin は全ユーザー / 全グループを管理できる
- group_lead / user はユーザー管理 API を利用できない
- plugin storage 更新 API は admin のみ利用できる

#### ユーザー管理 UI

- 未ログイン時はログイン UI を表示
- ログイン後、現在ユーザー / ロール / 所属グループを表示
- アプリレールのユーザーアイコンメニューからプロフィールダイアログを開き、自分のメールアドレス / パスワードを変更できる
- admin の場合:
  - ユーザー追加パネル
  - ユーザー変更パネル
  - ユーザー一覧の変更 / 削除操作
  - グループ追加
  - グループ削除
- DB設定タブは admin のみに表示
- ユーザー管理タブは admin のみに表示
- プラグインタブは全ユーザーに表示するが、設定変更は admin のみに許可

#### ユーザー別履歴保存

履歴 DB をユーザー単位に分離した。

- `history.user_id` カラム追加
- `history.starred` カラム追加
- 既存履歴は初回起動時マイグレーションで admin 所有に移行
- `GET /api/history` はログインユーザーの履歴のみ返す
- `GET /api/history?starred=true` はログインユーザーのスター付き履歴のみ返す
- `POST /api/history` はログインユーザーの履歴として保存
- `PATCH /api/history/{item_id}/star` はログインユーザーの履歴 ID のみ対象
- `DELETE /api/history` / trash / restore / permanent-delete はログインユーザーの履歴 ID のみ対象
- 他ユーザーの履歴 ID を指定しても変更されない
- 履歴を持つユーザー削除は孤立データ防止のため拒否する
- 出力ファイル保存先は `outputs/{user_id}/YYYY-MM-DD/...` へ分離
- 旧 `history.json` 移行スクリプトも admin 所有として取り込む

### v1.11 (2026-04-29)

**設定 UI の実挙動接続**

設定 > DB設定 / プラグインを prototype state からサーバー状態表示へ変更した。

- `GET /api/settings/status` を追加
- 管理者のみ設定状態を取得可能
- DB設定タブは現在の SQLAlchemy backend / driver / masked URL / database を表示
- DB接続はランタイム変更できず、`INKU_DB_URL` 変更後にサーバー再起動が必要であることを明示
- プラグインタブは reference server では loader 未実装であることをサーバー状態として表示
- フロントエンド上だけでプラグイン追加・削除・有効化できる prototype UI を廃止
- 未ログイン、または保存済みセッションが無効な場合、アプリ本体ではなく単体ログイン画面を表示
- ログインダイアログのパスワード欄は入力内容の表示 / 非表示を切り替え可能
- ログイン画面の背景に inku 生成 SVG をトリミング配置し、単体ログイン画面としての視認性を改善
- ログインパネルをコンパクトな寸法と抑えた余白へ調整し、業務利用に適した見た目へ整理
- ログインパスワードの表示切替をテキストボタンからアイコンボタンへ変更
- ログイン画面に言語切替ボタンを追加し、ログインフォーム文言も日本語 / English に対応
- 履歴管理ダイアログは全履歴ロードをやめ、サーバーサイド検索 / 100 件単位ページングで現在ページのみ描画
- Saijiki スナップショット機能は歳時記 v1 仕様確定まで一旦削除。API / フロント state / `snapshot_id` 配線を撤去し、後続仕様で再実装する
- 出力ファイル保存は SVG/JSON/入力/DDL を PNG 変換と分離し、`cairosvg` 未導入や filesystem / PNG 変換エラーをサーバーログへ記録
- バッチ描画は行単位の成功 / 失敗サマリーを表示し、失敗した入力行とエラー内容をユーザーが確認できる
- バッチ入力欄は行番号と入力行がズレないよう、行番号と textarea の文字設定を揃え、長い行は折り返さず横スクロールで扱う
- 右パネルの旧「楽譜 / score」タブは `JSON` に改名。JSON Score は行番号付きで表示し、キー / 文字列 / 数値 / 真偽値 / null を色分けする
- Web UI は SvelteKit フロントエンドと FastAPI バックエンドの 2 プロセス構成で動作し、開発時はフロントエンドから `/api/*` をバックエンドへ proxy する

### v1.12 (2026-04-29)

**履歴SVGのサーバー側保存**

履歴保存時に Web UI から送られた SVG を DB に保存する経路を廃止した。

- `/api/paint` は Stage 1 / Stage 2 / SVG レンダリング完了後、必要に応じてその場で履歴DBへ保存する
- `/api/paint` のレスポンスに `history_id` / `history_at` を追加
- Web UI の単発描画 / バッチ描画は、描画結果を表示しつつ、履歴保存は `/api/paint` のサーバー側処理に任せる
- Web UI は履歴保存用に SVG を `/api/history` へ送り返さない
- 互換用の `POST /api/history` は残すが、リクエストの `svg` は信用せず、受け取った JSON Score からサーバー側で SVG を再レンダリングして保存する
- 色カタログは初期実装では `color_map` としてサーバーに渡した。v1.25 以降は `catalog_id` をサーバーに渡し、サーバー側の色カタログ正本から `color_map` を解決する。`color_map` 自体は履歴メタデータとして保存しない
- Build 71

### v1.13 (2026-04-29)

**生成系 API の認証必須化**

LLM 呼び出しや描画生成を行う API をログイン済みユーザーに限定した。

- `/api/interpret` は有効な Bearer セッションを要求する
- `/api/compose` は有効な Bearer セッションを要求する
- `/api/paint` は保存有無にかかわらず有効な Bearer セッションを要求する
- Web UI の再描画 (`/api/compose`) 呼び出しを、認証ヘッダー付きの `apiFetch` 経由へ変更
- 未認証の生成 API 呼び出しは 401 を返す
- Build 72

### v1.14 (2026-04-29)

**セッション Cookie の HttpOnly 化**

Web UI がセッショントークンを localStorage に保存する方式を廃止した。

- `/api/auth/login` はレスポンス本文にトークンを返さず、`inku_session` Cookie を発行する
- `inku_session` Cookie は `HttpOnly` / `SameSite=Lax` / `Path=/` を付与する
- `INKU_SESSION_COOKIE_SECURE=1` の場合は Cookie に `Secure` を付与する
- Cookie の max-age は `INKU_SESSION_COOKIE_MAX_AGE` で指定し、既定は 30 日
- DB の `user_sessions` も同じ `INKU_SESSION_COOKIE_MAX_AGE` に従って期限判定する
- 期限切れ DB セッションは認証不可とし、アクセス時に削除する
- 新規セッション作成時にも期限切れ DB セッションを掃除する
- `/api/auth/me`、生成 API、履歴 API、管理 API は Cookie セッションで認証する
- 互換性のため Authorization Bearer も引き続き受け付ける
- `/api/auth/logout` は DB セッションを削除し、Cookie を削除する
- Web UI はログイン後もトークン値を JavaScript state や localStorage に保持しない
- Build 73

### v1.15 (2026-04-29)

**履歴DBを正本とする出力ファイル扱い**

履歴データの正本は DB とし、出力ファイルは副産物として扱う方針を明確化した。

- 履歴の `input` / `ddl` / JSON Score / SVG / メタデータは DB レコードを正本とする
- 出力ファイル保存先の `output_path` は副産物の保存先ヒントとして扱う
- SVG / JSON / 入力 / DDL / PNG ファイルは、DB履歴から再生成可能な artifacts とする
- `POST /api/history/rebuild-output-files` を追加し、指定した履歴IDの artifacts を DB から再生成できる
- artifacts 保存失敗は DB の履歴保存失敗とは扱わず、サーバーログに記録する
- Build 74

### v1.16 (2026-04-29)

**初期管理者アカウントの明示設定化**

新規DB作成時の bootstrap admin は、環境変数で初期パスワードが明示された場合のみ作成する。

- `INKU_BOOTSTRAP_ADMIN_PASSWORD` が未設定の場合、既知のデフォルトパスワードを持つ admin は作成しない
- `INKU_BOOTSTRAP_ADMIN_PASSWORD` は8文字以上を必須とする
- `INKU_BOOTSTRAP_ADMIN_USERNAME` / `INKU_BOOTSTRAP_ADMIN_EMAIL` は bootstrap admin 作成時のみ利用する
- ローカル開発で従来の `inku-admin` を使う場合のみ `INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN=1` を明示する
- 設定画面の bootstrap admin 説明文から既定パスワードの案内を削除
- Build 75

### v1.17 (2026-04-29)

**ユーザー管理タブの最新状態反映**

ユーザー管理タブの表示を、サーバー側 DB の最新状態へ追従しやすい形に調整した。

- ユーザー管理タブを開く / 切り替える / 再読み込みするたびに `/api/auth/me`、`/api/user-groups`、`/api/users` を再取得する
- ユーザー管理タブの取得には `cache: no-store` を指定し、古いレスポンスが後から戻って一覧を上書きしないようリクエストIDで抑止する
- ユーザー管理タブに手動の再読み込みボタンを追加
- ユーザー一覧とログイン中ユーザーのロール表示は翻訳ラベルではなく `admin` / `group_lead` / `user` の値を表示する
- pytest は既定で `/tmp` の一時SQLite DBを使い、実DBにテストユーザーやテストグループを残さない
- Build 77

### v1.18 (2026-04-29)

**歳時記語彙操作の精緻化 + 右パネル操作性改善**

歳時記 v1 仕様に向けて、語彙挿入・プレビュー・解釈編集の操作を整理した。

- 歳時記ドロワー上で語彙ボタンに mouseover / focus したとき、当該語彙の描画効果プレビュー、効果説明、短い使用例を表示する
- 歳時記に「かたむき」カテゴリを追加し、「うごき」の下、「わりあい」の上に表示する
- JSON Score schema に `rotation` フィールドを追加し、線・楕円・四角・三角・弧を中心まわりに回転できるようにする
- 歳時記語彙クリック時の挿入先は常に解釈（正規化DDL）Box のカレントキャレット位置とする
- 解釈Boxは編集ボタンを廃止し、常時編集可能にする
- 解釈Box内の歳時記語彙はカテゴリ別の控えめな色でハイライト表示する
- 解釈Boxのカスタムキャレットを太くし、語彙ハイライト上でも見失いにくくする
- 「新規作成」は指示・解釈・描画・プロンプト・JSON表示をクリアし、描画タブにはプレースホルダー画像を表示する

右パネルとヘッダーの操作もあわせて整理した。

- 旧エクスポートバーをステータスバーに改名し、Stage 1 / Stage 2 モデル名と色カタログ名を表示する
- 履歴表示中は当該履歴の使用モデル / 色カタログ / キャンバス種類をステータスバーに表示し、モデルや色カタログの選択を変更したら現在選択を優先表示する
- モデル選択ダイアログは正式寄りのモデル名を表示し、ダイアログ幅を実測文字数に合わせて調整する
- 色カタログ / モデル選択ダイアログは閉じるボタンを廃止し、キャンセル / 決定ボタンで変更の破棄・確定を明示する
- プロンプトタブの Stage 1 ユーザー入力 / Stage 2 ユーザー入力にクリップボードコピーアイコンを追加する
- プロンプト / JSON 表示時は左右の履歴ナビゲーションボタンと内容が重ならないよう安全余白を確保する
- ヘッダーのログイン中ユーザー名をクリックすると、ログオフを選択できるメニューを表示する
- Build 100

### v1.19 (2026-04-30)

**Stage 1.5 中間フィルタ + 数学・音楽・絵画技法の拡張**

Stage 1 と Stage 2 の間に、決定的な中間フィルタを追加した。

- Stage 1 の正規化DDLを、Stage 2 に渡す前に拡張正規化DDLへ変換する
- `ランダム` / `random` は正規化DDLの禁止語として扱い、明示配置へ置換する
- `/api/paint` は中間フィルタ後の拡張DDLを Stage 2 に渡し、レスポンス・履歴にも同じDDLを保持する
- `/api/compose` に直接DDLが渡された場合も、中間フィルタを通してから Stage 2 を呼ぶ
- 数学・幾何学的拡張:
  - 黄金比
  - 三分割構図
  - 白銀比
  - 正五角形
  - フィボナッチ的数量
  - 放射状配置、同心円、対角線、波打つ軌跡
- 音楽技法の拡張:
  - 対位法の反行
  - 倍音列
  - 輪唱のずれ
- 絵画技法の拡張:
  - 一点透視法
  - 遠近法
  - 明暗・濃淡
  - 素描
  - 点描
  - 油絵の厚塗り
  - 水彩
  - パッチワーク
  - フレスコ
  - 水墨
- Stage 2 プロンプトに、これらを JSON Score の既存フィールドへ落とすルールと例を追加した
- `server/src/inku_server/ddl_expander.py` を追加し、決定的変換器としてテスト対象化した
- v1.19 後続調整として、全技法を毎回投入する方式を廃止し、入力DDLの決定的シードに基づいて少数の技法層を選択する方式へ変更した
- v1.19 後続調整として、`中心` / `中央` をキャンバス中央へ固定せず、入力DDLごとの動的焦点へ置換する方式へ変更した
- Build 103

### v1.20 (2026-04-30)

**描画テクスチャ強化 + コントラスト保持フィルタ + UI文脈整理**

Renderer の `weight` 表現を線幅差だけに留めず、SVG 属性・フィルタ・複線レイヤーでてざわりの違いを描き分けるようにした。

- `pencil`: 低 opacity と細かな破線で薄い鉛筆線を表現する
- `chalk`: 破線と軽い blur filter で粉っぽいチョーク線を表現する
- `crayon`: 主線に擦れた副線を重ね、クレヨンのざらつきを表現する
- `brush_thick`: 太い主線、薄い副線、軽い blur で筆跡の厚みを出す
- `rotring`: 角張った線端で製図線寄りにする
- `hair`: 極細・低 opacity で繊細な線にする

Stage 1 / Stage 2 には、背景色と描画色が同化して実質的に描画効果がなくなる正規化を避けるコントラスト保持ルールを追加した。

- 背景と描画が同色の場合は、原則として面積の少ない側を変更する
- 白地に白線、白地に小さな白図形などは、線・小図形側を黒・青・赤・緑など文脈に合う可視色へ寄せる
- 白い雪・星など白が主題でも、小さい要素なら背景ではなく要素側を青などへ寄せる
- 大きな白い月など、白い主題図形が支配的な場合だけ背景側を青や黒などへ変更してよい
- コントラスト調整の退避先として安易に灰背景を使わない。灰背景は入力または正規化DDLで明示された場合のみ許可する
- Stage 2 でも `background` と instruction の `color` が同化しないよう、同じ判断基準をプロンプト例に追加した

あわせて、粒子表現の真円偏重を抑えるため、点・粒・星・雪・砂・花びら系は楕円・小四角・短線へ分散し、楕円・四角には `rotation` を付けて水平/垂直対称に固定されないようにした。

UI 実装が単一巨大コンポーネントへ集中していた問題を緩和するため、主要な表示単位を段階的にコンポーネント分割した。

- `AuthPanel`: 未ログイン時のログインパネル
- `HistoryStrip`: 下部履歴ストリップ
- `HistoryManager`: 履歴管理ダイアログ
- `SettingsModal`: 設定 / モデル選択 / ユーザー管理
- `ColorCatalogModal`: 色カタログ選択
- `SaijikiDrawer`: 歳時記ドロワー
- `CanvasPanel`: 描画 / プロンプト / JSON 表示パネル
- `OutputTabsContent`: プロンプト表示と JSON 表示
- `ConfirmDialog`: 削除 / 復元などの確認ダイアログ
- `InputPanel`: 記述 / バッチ切替、指示入力、単発描画進捗
- `BatchPanel`: バッチ入力、行番号、現在行ハイライト、処理中解釈、失敗レポート
- `DdlEditor`: 解釈 box、歳時記ボタン、語彙ハイライト、解釈から描画
- `HistoryThumbnail`: 履歴サムネイル SVG のクリップ加工と表示サイズ差分

バッチ描画と単発記述の UI 文脈を整理した。

- バッチ実行中だけ、現在処理中ラインの「処理中の解釈」欄を表示する
- 処理中の解釈欄は読み取り専用で、歳時記語彙のカテゴリ別ハイライトを適用する
- バッチ入力欄は実行中 readonly とし、現在処理中の元入力行をハイライトする
- バッチパネルでは通常の解釈編集 box、歳時記ボタン、`解釈から描画` ボタンを表示しない
- バッチ実行中に履歴をクリックしてもバッチ処理は止めず、履歴の描画 / 記述内容を表示できる
- バッチ実行状態は表示中タブ (`inputMode`) から分離し、履歴表示へ切り替えてもバッチ指示 box の内容を維持する
- バッチ終了後は処理中の解釈欄を閉じ、バッチ入力内容と失敗レポートは維持する

Svelte の既存 accessibility warning を整理し、`npm run check` が 0 errors / 0 warnings になる状態にした。

`web/src/routes/+page.svelte` は UI 表示単位を子コンポーネントへ分割し、ページ側は API 呼び出し、履歴、認証、設定、実行状態の orchestration を主責務とする形へ整理した。

履歴サムネイルの SVG クリップ加工は `HistoryThumbnail` に集約した。`+page.svelte` のテンプレート経由で `clippedHistorySvg()` を呼び続ける形を廃止し、サムネイル単位の `$derived` で加工済み SVG を管理する。

- Build 124

### v1.20 (2026-05-05)

**レンダリングエンジン改訂 + 履歴ハッシュ UI + DDL 自動補正制御**

レンダリングエンジンの改訂では、個別キーワードへの分岐ではなく、入力の意味を汎用的な描画パラメータへ変換する方針を採った。

- 人・顔・動物を対象物として描かず、`Score.presence` の `kind` / `intensity` / `center` / `symmetry` / `gaze_pressure` / `contour_density` として扱う
- `presence` は目鼻口・頭身・四肢・耳・尻尾を instruction にしない。存在感、重心、左右対称性、視線の圧力、群れ、輪郭密度として renderer に渡す
- renderer は `presence` を薄い弧、線片、端寄りの焦点、非対称な輪郭密度として演奏する。縦線＋小楕円、棒人間、頭/胴体、翼/尾、円周上の同型楕円列のような固定シルエットは避ける
- `polygon` primitive を追加し、多角形語彙は個別の五角形・六角形 primitive へ分けず、`sides=5-8` の `polygon` に集約する
- `motion_energy` は count / density を増やすのではなく、`trajectory` / `rotation` / `diagonal` / `wave` / `asymmetry` を強めて動勢を戻す
- quiet / presence / membrane / fog / memory / shadow 系入力では、高密度、大きな塗り閉図形、縦雨線、fallback 由来の大きな square / triangle が主題を上書きしないよう密度と記号形状を抑制する
- `leaf_grain` / `silence_layer` / `hard_edge` / `playful_motion` などの context energy は、行番号ではなく文脈語に基づく小さな補助層として扱う

Stage 2 の契約も強化した。

- 形容語・動作語・質感語は、DDL で指定された主図形へ適用する
- `震える` / `揺れる` / `滲む` / `太い` / `細い` などを理由に、DDL にない補助線・補助図形・別色 instruction を追加してはいけない
- プロンプト制約だけではモデル依存で再発するため、composer に deterministic な contract guard を追加した
- contract guard は、DDL が単一の明示 primitive family と motion / texture modifier を含む場合だけ適用する
- 明示色がある場合は、その色・primitive に合う instruction だけを残し、未指定の補助線・補助図形・別色 instruction を落とす
- 線に対して「震える」などがあり、Stage 2 が variation を落としている場合は、主 line instruction に `quality=perlin`, `dimensions=["position_x","position_y"]` を補う
- 複数モチーフの DDL にはこの guard を適用せず、豊かな多層出力を壊さない

解釈 box と DDL 再描画の操作を整理した。

- `ComposeRequest` / `PaintRequest` に `auto_repair` を追加した。既定は `true`
- Web UI の解釈 box に「自動補正」チェックを追加し、OFF の場合は `coerce_score()` による自動補正を適用しない
- `新規作成` は、記述タブでは空の解釈 box を表示し、歳時記、DDL 編集、自動補正、DDL から描画の操作をそのまま利用できる状態にする
- `DDLから描画` ボタンは解釈 box の下に配置し、解釈 box 上部のボタンは削除した
- `DDLから描画` は Stage 1 を呼ばず、解釈 box の DDL を Stage 2 / renderer に渡す。自然言語の指示欄の内容は再解釈しない

履歴とステータスバーのハッシュ表示を整理した。

- ステータスバーのスター右隣に、表示中画像の `render_hash_short` を表示し、クリックでフル `render_hash` をコピーするボタンを追加した
- 未描画時、またはハッシュがない場合はハッシュボタンを押下不可にする
- 通常描画後に `/api/history` へ保存した場合、保存 API の戻り値で `result.render_hash` / `render_hash_short` / `history_id` / `history_at` を更新する
- これにより、描画完了直後のステータスバーと、別履歴を表示して戻った後のステータスバーが同じ DB 正本のハッシュを表示する
- 履歴ダイアログの画像領域クリックは、その履歴を選択してメイン画面へ戻る
- 履歴ストリップと履歴管理ダイアログに「最新」ボタンを追加した
- バッチ描画中に他タブや履歴を見ても、バッチタブへ戻った後は次の描画完了時に最新描画を自動表示する

色カタログ UI の確定動作を変更した。

- 色カタログダイアログで選択変更後、ダイアログ外をクリックした場合は「保存」と同じ動作として扱う
- キャンセルボタンは従来どおり、ダイアログを開いた時点の選択へ戻す
- 色カタログボタンは現在選択中のカタログ名を表示し、長い名前は省略表示する

ベンチマークで確認した主な修正点:

- Build 342 -> 345: presence 抽象化により、人・動物の対象物化を抑えつつ、気配・重心・輪郭密度を保持した
- Build 346 -> 347: quiet density governor と symbolic shape tempering により、過密な縦線や fallback 由来の大きな四角/三角の支配を抑えた
- Build 348: `polygon` と `motion_energy` を導入し、count を増やさずに動勢を戻した
- Build 349-351: polygon 5件ベンチで `polygon` 出力を確認し、落ち葉・廊下・鉄骨・自転車の影などで context energy を調整した
- Build 351-355: 共通図形再発調査に基づき、presence 補助層が固定シルエットや ring-like mark へ収束しないよう調整した
- Build 356-357: 自動補正OFF時の未指定横線3本混入を調査し、Stage 2 contract guard で未指定補助 instruction を除去する方針を追加した
- Build 386-395: 画質改善を個別ケース分岐ではなく、品質メトリクスと汎用 Score 補修として進めた。`constraint_adherence` / `negative_space_pressure` / `motion_energy` / `color_resonance` / `visual_event` / `figurative_risk` をベンチ summary に記録し、fallback / timeout サンプルは品質判断から分離する
- Build 386-391: quiet / membrane / fog / memory / shadow / neon blur 系で、過密な縦線、粒、大きな閉図形、背景面の支配を抑える density / negative-space governor を強化した。ネオン滲みは粒塊ではなく透明な streak として読める密度へ制御する
- Build 392-393: motion 語があるのに有効な軌跡がない場合、count を増やさず小さな方向性のある `arc` 群を補う motion floor を追加した。要求色が `color_cycle` にだけ存在する場合は主 stroke へ昇格し、色の読みを強める
- Build 394: visual event 補修を小さな弧に固定せず、既存 Score に角要素が不足する場合は小さな `polygon` を使う。これにより、赤い小楕円や淡い補助弧への語彙固定を避ける
- Build 395: 反復線が画面を支配する場合、要素数を増やさず `rhythm_spacing=syncopated`、余白保持、方向性 fade、端点の小さな欠落で線群自体を出来事化する。風鈴やネオンのような題材では視覚イベントが改善した一方、砂浜/波の記憶のような低彩度・曲線・記憶系では余白を失いやすく、次の調整対象として残る
- Build 359

### v1.21 (2026-04-30)

**アプリレール導入 + ダークモード導入 + ユーザー別 UI 状態保存 + スター付き履歴 + バッチ進捗視認性**

画面上部の固定ヘッダーを廃止し、左側の収納式アプリレールへ集約した。

- アプリ名、ビルド番号、ユーザー操作、設定、言語切替、テーマ切替を左レールに配置する
- レールは展開 / 収納でき、通常時の縦方向の作業領域を広げる
- 開発中の確認用として、ビルド番号はレール収納時でも常時視認できる位置に残す
- アプリ名は収納時 `inku`、展開時 `inku-lang` として表示する
- 展開 / 収納で `inku` 部分の位置と大きさが変わらないよう、`inku` 部分は固定幅で表示する
- ユーザー名操作はメニュー化し、ログオフを選択できる
- 設定は歯車アイコン、ユーザー操作は人型アイコンで表示する

履歴エリアを折りたためるようにした。

- 下部の履歴ストリップは必要に応じて収納できる
- 履歴を閉じた状態では描画 / 記述 / バッチの作業領域を広く使える
- 履歴を再表示した場合も、現在の履歴ページングとスター絞り込みの文脈を維持する

UI にライト / ダークモードを追加した。

- 画面左の収納式アプリレールからテーマを切り替えられる
- ダークモードでは背景、パネル、入力欄、モーダル、履歴、ステータスバー、ボタン類の配色を切り替える
- 描画そのものの SVG / PNG 出力はテーマに影響されず、Score の背景色と描画色を正とする
- ダークモードでは描画パネルの履歴移動ボタン、ズームボタン、倍率表示、記述 / バッチの描画ボタンのコントラストを確保する
- 履歴管理ダイアログの hover メタデータポップアップもダークモード向けの色へ切り替える

ライト / ダークモードはユーザー情報としてサーバー側に保存する。

- UI テーマは `user_accounts.ui_theme` に保存する
- ログイン時に `/api/auth/me` から現在ユーザーの UI テーマを取得する
- テーマ切替時は `PATCH /api/auth/me/settings` でサーバーへ保存する

バッチパネルの指示履歴をユーザーごとのサーバー保存へ変更した。

- `user_accounts.batch_prompt_history` に最大 20 件の指示履歴を保存する
- `GET /api/auth/me/batch-prompt-history` / `PUT /api/auth/me/batch-prompt-history` を追加する
- 指示履歴はプルダウンから選択した時点で指示 box へ復元する
- 復元ボタンは廃止する
- 新規作成時はバッチ指示 box と表示中のエラーをクリアする
- バッチサンプルは 3 件分の入力例として、行番号 1〜3 に対応する形で表示する

履歴にスター機能を追加した。

- `history.starred` カラムを追加し、スター状態を DB に保存する
- `PATCH /api/history/{item_id}/star` でスター状態を切り替える
- `GET /api/history?starred=true` でスター付き履歴のみ取得できる
- ステータスバー、履歴ストリップのサムネイル右上、履歴管理ダイアログのサムネイル右上でスターを表示 / 操作できる
- 履歴ストリップと履歴管理ダイアログに、スター付きのみ表示するフィルタを追加する

履歴管理ダイアログの視認性を調整した。

- ダイアログ幅を広げ、サムネイル一覧とリスト表示の横方向の余裕を増やす
- サムネイル hover のメタデータポップアップは fixed 表示にし、モーダルや画面端で切れないように viewport 内へ clamp する
- ダークモード時のポップアップ色を調整する
- hover からポップアップ表示までのディレイを長めにする

バッチ実行中の進捗表示を強化した。

- バッチパネルにも token 数を表示する
- 現在行の token 数と、ここまでの累積 token 数を分けて表示する
- バッチ進捗行に蟹のマスコットを表示する
- 蟹は左右に移動し、鋏を上げる、目を動かす、砂に潜る、お辞儀する仕草を行う
- 蟹は横移動できる生物として扱い、移動方向に合わせた左右反転は行わない

サーバー運用時の安定性を調整した。

- `inku-server` の FastAPI 起動は reload 無効を既定とする
- `INKU_SERVER_RELOAD=1` / `true` / `yes` / `on` の場合のみ `uvicorn` reload を有効にする
- systemd サービス運用では reloader プロセスを使わず、通常の単一 `uvicorn` 実行を前提にする
- `inku_session` Cookie の max-age と DB セッション寿命を連動させる
- DB セッションは `INKU_SESSION_COOKIE_MAX_AGE` を超えた時点で無効扱いにし、アクセス時に削除する
- 新規セッション作成時にも期限切れセッションを掃除する

- Build 151

### v1.22 (2026-05-01)

**サーバー保存負荷制御 + 履歴検索高速化 + 履歴管理ページング安定化 + 状態分離 + デモタブ**

出力ファイル保存は DB 履歴保存とは分離し、バックグラウンド保存キューの上限を設けた。

- `/api/paint` は履歴 DB への保存を正本とし、SVG / JSON / PNG などの artifact ファイル保存は副産物として扱う
- artifact 保存用 executor は worker 数と queue 数に上限を持つ
- 保存 queue が上限に達した場合、DB 履歴保存を優先し、artifact 保存だけをスキップできる
- `/api/settings/status` は `output_save` に worker 数、queue 上限、使用中 slot 数、利用可能 slot 数を返す

履歴検索は SQLite FTS5 を利用する。

- `history_fts` virtual table を作成し、`history` の `input` / `ddl` / `stage1_prompt` / `stage2_prompt` / `model` / `catalog_id` を検索対象にする
- insert / update / delete trigger で FTS index を履歴 DB と同期する
- 検索語が短い場合や FTS が利用できない場合は従来の `LIKE` 検索へ fallback する

履歴管理ダイアログのページングを安定化した。

- 履歴管理のページ移動、検索、表示種別、スター絞り込みは、取得時点の条件を明示して `/api/history` を呼び出す
- 古いレスポンスが後から返っても、最新リクエストでなければ表示状態へ反映しない
- 検索の debounce effect は `untrack` で fetch を呼び、ページ移動やスター絞り込みの state 更新と競合しないようにする
- ページあたり件数は 100 件を維持する
- 履歴管理のサムネイルは `content-visibility` を利用し、100 件表示のまま画面外 SVG の描画負荷を抑える

ページ orchestration の肥大化を抑えるため、履歴管理ダイアログ専用の状態と副作用を `HistoryManagerState` へ切り出した。

- `web/src/lib/historyManagerState.svelte.ts` を追加する
- 履歴管理ダイアログの active / trash 表示、ページング、検索、スター絞り込み、選択状態、request id による stale response 破棄を同 state に集約する
- `+page.svelte` は履歴ストリップ、削除 / 復元確認、表示中履歴への反映などページ横断の接続を主責務とする

記述 / バッチの隣にデモタブを追加した。

- `DemoPanel` を新設し、デモ専用 UI をコンポーネントとして分離する
- デモは「シードフレーズから短い指示文を生成 → 生成された指示で1枚描画 → 表示間隔まで待機 → 繰り返し」で動作する
- デモ設定はユーザーごとに `user_accounts.demo_settings` へ保存する
- 設定項目は DB 保存有無、artifact ファイル保存有無、指示文生成モデル、シードフレーズ、表示間隔とする
- デモの既定値は DB 保存なし / ファイル保存なし / 表示間隔 30 秒
- `GET/PUT /api/auth/me/demo-settings` を追加する
- `POST /api/demo/instruction` を追加し、シードフレーズからデモ用指示文を生成する
- デモ実行中は生成された指示文と、ハイライト付き正規化DDLを表示する
- デモ開始時は新規作成と同等に描画 / プロンプト / JSON 表示をクリアし、描画タブにはプレースホルダーを表示する
- デモタブには新規作成ボタンを表示しない
- デモ中もプロンプト / JSON タブは参照可能とし、生成された指示文と正規化DDLを確認できる
- デモ実行中は履歴ストリップを操作ロックし、ロック中であることを視覚的に表示する
- 現在表示中のデモ描画を気に入った場合、デモを止めずに `現在の描画をDBに保存` ボタンから履歴へ追加できる
- デモ描画を手動保存するまでステータスバーのスター操作では履歴へスターを付与しない
- デモ実行中は合計実行時間 / 合計トークン数と、現在描画中の指示の実行時間 / トークン数を表示する
- デモ停止後も合計実行時間 / 合計トークン数 / 描画件数を保持して表示する
- `/api/history` は `save_artifacts` を受け取り、手動保存時のファイル保存有無を制御できる
- Stage 2 の tool schema は `$defs` / `$ref` をインライン展開してから LLM API へ渡し、JSON grammar コンパイラが参照解決できない環境でも動作するようにする

- Build 162

### v1.23 (2026-05-01)

**inku-cli 初期実装**

macOS 開発環境から `inku-api` を操作する CLI を追加した。CLI は `server/` から独立した root 直下の `cli/` プロジェクトとして管理する。

- `inku-cli` を `cli/pyproject.toml` の console script として登録する
- 実装は `cli/src/inku_cli/`、テストは `cli/tests/` に配置する
- CLI はサーバー内部ロジックを直接呼ばず、Web UI と同じ FastAPI API を操作する
- `login` は `/api/auth/login` の `inku_session` Cookie を取得し、以後は `Authorization: Bearer` として送信する
- セッション設定は `~/.config/inku-cli/config.json` に保存し、ファイル権限は可能な限り `0600` にする
- `me` / `logout` / `paint` / `batch` / `demo-instruction` / `history` を初期コマンドとして提供する
- `paint` / `batch` は SVG / JSON をファイル出力でき、必要に応じて PNG も生成できる
- `paint` / `batch` は Stage 1 / Stage 2 モデル指定、履歴保存、artifact 保存、言語指定、thinking 取得を指定できる
- `models` コマンドで Stage 1 / Stage 2 の CLI 既定 provider / model を確認・保存できる
- provider は `nvidia` / `anthropic` / `local` を保存できる。API へ送るのは model ID で、provider は CLI 側の接続先・運用管理用メタデータとして扱う
- timeout 秒数も CLI ローカル設定に保存でき、コマンド引数 > ローカル設定 > 600 秒の順で解決する
- `paint` / `batch` は使用する Stage 1 / Stage 2 provider / model を描画開始時に stderr へ表示し、JSON summary にも含める
- 描画系 API 呼び出しの既定 timeout は 600 秒とし、長い Stage 2 推論を待てるようにする
- 描画中は stderr に経過秒数と簡易テキストアニメーションを表示し、停止していないことを確認できる
- 初期目的は、CLI から指示と画像を生成し、AI による成果物画像の品質判定を組み合わせて Stage 1 / 1.5 / 2 調整用のフィードバックループを構築すること
- CLI は `inku_server` を import せず、単独の API クライアントとして起動する
- 開発時は `cd cli && uv run inku-cli ...` で実行する
- macOS から pentala の `inku-api` へ LAN 経由で接続し、`login` / `paint` / SVG・JSON・PNG 出力の動作を確認した
- CLI の確認で生成される `cli/out/` はローカル成果物として Git 追跡対象外にする

### v1.23 (2026-05-01)

**NVIDIA Free API 前提の LLM retry / fail 機構 + 100件ベンチ由来の Score 補正**

NVIDIA NIM は開発用の Free API 接続先として扱う。SLA は保証されず、リクエスト集中時には `inference connection error`、一時的な 5xx、応答遅延が発生しうる。その前提で、合理的な retry / fail 機構をサーバー側に追加した。

- OpenAI 互換 LLM 呼び出しは `call_with_llm_retry()` を通す
- retry 対象:
  - `429 Too Many Requests`
  - `408 / 500 / 502 / 503 / 504`
  - `inference connection error`
  - connection reset / aborted / timeout / gateway 系の一時エラー
- retry 対象外:
  - JSON grammar / schema compile error
  - bad request
  - authentication / authorization error
  - not found
  - その他、クエリや schema 自体の恒久的な問題
- retry 回数、base delay、max delay、jitter は環境変数で調整できる:
  - `INKU_LLM_RETRY_ATTEMPTS`
  - `INKU_LLM_RETRY_BASE_DELAY`
  - `INKU_LLM_RETRY_MAX_DELAY`
  - `INKU_LLM_RETRY_JITTER`
- OpenAI 互換クライアントには request timeout を設定し、無制限に待ち続けない:
  - `INKU_LLM_REQUEST_TIMEOUT_SECONDS`
  - 既定値は 120 秒
- CLI 側の HTTP timeout は従来どおり長い描画待ち用に 600 秒を既定とする。サーバー内の LLM request timeout と、CLI から API への HTTP timeout は別レイヤーとして扱う

100件ベンチで確認した DDL -> JSON の伝達欠落に対し、Score coerce layer を強化した。

- Stage 2 が同一 `arrangement.count` 付き instruction を複製した場合、renderer 前に重複を統合する
- renderer 展開後の総プリミティブ数に上限を設け、過密化と SVG 肥大を抑制する
- 現時点の expanded primitive count 上限は 400
- 上限超過時は `arrangement.count` を縮小し、`color_hint` に density cap の注記を残す
- DDL の素材語から JSON Score の `weight` を補完する:
  - ロットリング -> `rotring`
  - 鉛筆 -> `pencil`
  - クレヨン -> `crayon`
  - チョーク -> `chalk`
  - 細筆 / 水墨 / 墨 -> `brush_thin`
  - 太筆 / 油絵 / 厚塗り -> `brush_thick`
- DDL の揺れ・滲み語から `variation` を補完する:
  - `ゆっくり揺れる` / `ゆっくり波打つ` -> `quality=wave`, `frequency=slow`
  - `細かく揺れる` / `細かく震える` / `震える` -> `quality=perlin`
  - `滲む` / `境界が滲む` -> `quality=pink`
- `/api/compose` と `/api/paint` は `coerce_score(score, ddl=...)` を呼び、DDL の素材・揺らぎ情報を補正に利用する
- Stage 2 が空 `instructions` を返した後の deterministic fallback は、DDL の数量と素材語を可能な範囲で保持する

追加テスト:

- `test_llm_retry.py`
  - rate limit retry
  - inference connection error retry
  - schema / grammar 系 bad request は retry しない
- `test_coerce.py`
  - repeated arranged instruction の重複統合
  - expanded primitive count の上限
  - DDL からの素材 / variation 補完
  - 日本語数量詞からの count hint 抽出

検証:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q
```

結果:

- `ruff`: all checks passed
- `pytest`: `103 passed, 30 skipped`

### v1.24 (2026-05-01)

**揺らぎの視認性改善**

DDL の「細かく揺れる」「ゆっくり揺れる」が JSON Score と SVG 上で視認しやすくなるように、Stage 2 と Renderer の扱いを調整した。

- Renderer の `fine` 揺れ幅を 1000px キャンバス上で 7px とし、サムネイルでも細かい揺れが読めるようにする
- 「ゆっくり揺れる」/ `Swaying slowly` は Stage 2 で `variation.quality="wave"` / `frequency="slow"` を優先する
- 「震える」「細かく揺れる」は `quality="perlin"` を基本とし、微細な不規則性として扱う
- 短い line の揺らぎは `dimensions=["position_x","position_y"]` を優先し、短線上で揺れが潰れないようにする
- `schema.py` の `variation.quality` 説明も、`perlin` と `wave` の役割が分かれるように更新した

### v1.24 (2026-05-02)

**Build 250: DDL 品質チューニング 2-5 + ベンチマーク tooling**

Build 248 / 249 の sensory retention 後に残った「fallback 作品の縮退」「黒・灰偏重」「形状語彙の狭さ」「ベンチ結果整理の手作業負担」に対応した。

Fallback score の品質改善:

- Stage 2 が timeout / empty instructions で deterministic fallback Score へ切り替わった場合でも、DDL の数量・配置・素材・場のトーンを可能な範囲で保持する
- `散らす` / `点々` / `scatter` / `dotted` は fallback でも `arrangement` として保持する
- 40個以上の反復は `density=medium`, `cluster_count`, `fade`, `preserve_space=true` を付与し、余白を残す
- 120個を超える反復は最大 120 個程度へ代表化し、300個以上は `density=high`, `cluster_count=9` として群の見え方を優先する
- `波打つ軌跡`、`斜めの帯`、`右半分`、`上から下`、`左から右` は fallback でも `arrangement.path` へ反映する
- fallback primitive は line / square へ寄せすぎず、DDL の語に応じて `triangle` / `arc` / `square` / `ellipse` / `line` へ分散する

Palette strategy:

- Stage 1.5 の deterministic expansion で、明示色が少ない場合に場のトーンから代表色を選ぶ
- 春・花・蕾・温かい光は red / green / white 系を優先する
- 水・夜・月・雨・霧・冷気は blue / white / gray 系を優先する
- 森・葉・草・香りは green / white / gray 系を優先する
- fallback でも春系・水夜系・多色系では `arrangement.color_cycle` を使い、単色化を避ける
- 抽象色に収まらないニュアンスは `color_hint` に保持し、Renderer の色カタログ解決で利用できるようにする

Shape vocabulary:

- 既存 schema の範囲で `triangle` / `arc` / rotated square / thin ellipse をより積極的に使う
- 山・屋根・尖った先端は `triangle` として表現する
- 葉・花びら・羽・紙片・破片・舟は thin ellipse または rotated square として抽象化する
- 扉・窓・箱・街・部屋・格子は rotated square を「視線の切片」として扱えるようにする
- 自然 primitive plugin が未導入の段階でも、自然・物質形を既存 primitive で失わずに保持する

Sensory visibility:

- 白背景上の `柔らかな光`、`五感`、`透明な膜`、`気配` は単純な黒化を避け、淡い blue と `color_hint` で保持する
- 白背景上の `香り` / `匂い` / `fragrance` / `scent` は淡い green と `color_hint` で保持する
- 見えることを優先しつつ、感覚層が硬い黒線になって作品の余韻を壊すことを避ける

CLI benchmark tooling:

- `inku-cli batch` は `--summary-json` を指定すると batch summary JSON を指定パスへ保存する
- `--out-dir` 指定時は既定で `OUT_DIR/analysis-summary.json` に summary を保存する
- summary には `review_sets` を追加し、以下を自動分類する:
  - `all_success_samples`: 成功した全サンプル
  - `fallback_samples`: Stage 1 / Stage 2 fallback 使用サンプル
  - `slow_samples`: 実行時間が長いサンプル
  - `normal_samples`: fallback なし、かつ slow ではないサンプル
- summary には色到達、否定色、motif 到達、数学的構図 marker の診断情報を含める:
  - `color_trace`
  - `negated_color_markers`
  - `score_motif_hint_counts`
  - `score_motif_hint_lines`
  - `math_balance_markers`
  - `math_balance_marker_lines`
- NVIDIA Free API の待ち時間はキュー状況による偶然性が高いため、芸術評価では除外し、診断メタデータとしてのみ扱う
- 成功した描画は、遅かった場合でも今後すべて品質評価対象に含める
- `inku-cli contact-sheet` を追加し、PNG 出力ディレクトリから contact sheet を生成できる
- CLI 依存関係として Pillow を明示し、contact sheet 生成を安定して利用できるようにする

検証:

- macOS:
  - `server`: `76 passed, 15 skipped`
  - `cli`: `11 passed`
  - `ruff`: backend / CLI とも all checks passed
- pentala:
  - `server`: `76 passed, 15 skipped`
  - `cli`: `11 passed`
  - `ruff`: backend / CLI とも all checks passed
  - `web`: `npm run check` 0 errors / 0 warnings
  - `web`: `npm run build` success
  - `inku-api` / `inku-server` health check: HTTP 200

### v1.25 (2026-05-01)

**てざわり選択と物理素材レンダリング**

DDL の「てざわり」が線幅差だけに見えないよう、Stage 1 / Stage 1.5 / Renderer の各層で素材差を強化した。

- Stage 1 に「てざわり選択」ルールを追加し、明示素材がない入力でも文脈から素材を選ぶ
  - 薄い / 淡い / 下書き / 素描 → 鉛筆または細筆
  - 粉 / かすれ / 乾いた / 黒板 / 壁 → チョーク
  - 手描き / こすれ / 蝋 / 柔らかい色面 → クレヨン
  - 墨 / 書 / 筆跡 / 濃淡 → 細筆または太筆
  - 精密 / 機械的 / 均一 / 図面 → ロットリング
- Stage 1 の few-shot に鉛筆、チョーク、クレヨン、ロットリングの質感例を追加した
- Renderer は `weight` ごとに SVG 属性・texture filter・副線・粒・撚り短線を生成する
- line に加えて circle / ellipse / square / arc の輪郭にも素材処理を適用する
- `pencil` / `crayon` / `chalk` / `brush_thick` は `feTurbulence` / `feDisplacementMap` を使い、線幅だけではない質感差を出す

### v1.25 (2026-05-03)

**サーバー正本の色カタログ API + CLI version/build 表示**

色カタログの正本をクライアント側静的定義からサーバー側へ移した。

- 色カタログ定義は `server/src/inku_server/color_catalogs.py` を正本とする
- `GET /api/color-catalogs` は default catalog ID と全カタログの `map` / `swatches` / `palette` を返す
- Web UI と CLI は色カタログ一覧をサーバー API から取得し、クライアント側のカタログ定義を持たない
- `/api/paint`、`/api/compose`、`/api/history` は `catalog_id` を受け取り、サーバー側でレンダリング用 `color_map` を解決する
- `color_map` リクエストフィールドは互換用に残すが、色カタログ解決の正本としては扱わない
- 履歴には従来どおり `catalog_id` を保存する。加えて、描画レスポンス JSON と出力 artifact JSON には、実際に使用した解決済みの `stage1_model` / `stage2_model`、実際にレンダリングした `render_build_number`、sRGB基準であることを示す `render_color_profile`、サーバー解決済みの `render_color_catalog_id` / `render_color_catalog_name` / `render_color_catalog_sub`、および `render_color_map`（抽象色名・`palette:<name>` から実際の `#RRGGBB` コードへの展開）を記録する。`render_color_catalog` の完全な `map` / `swatches` / `palette` snapshot は `render_color_map` と重複するため保存しない
- `GET /api/info` はサーバー名、バージョン、ビルド番号を返す
- CLI に `version` コマンドを追加し、CLI 側の version / build number と、接続先サーバーの version / build number を表示する
- Build 264

### v1.26 (2026-05-01)

**軌跡フィールドの追加**

DDL の「波打つ軌跡」「斜めの帯」「上から下」「右半分」などが `scatter` に埋もれないよう、JSON Score の `arrangement` に `path` フィールドを追加した。

- `arrangement.path` は `none` / `diagonal` / `wave` / `top_to_bottom` / `left_to_right` / `right_half` を持つ
- Stage 2 は「波打つ軌跡に沿って」を `path="wave"`、「斜めの帯」を `path="diagonal"`、「右半分」を `path="right_half"` として出力する
- 「上から下へ散らす」は `layout="vertical"` に加えて `path="top_to_bottom"` を指定できる
- Renderer は `path` が指定された arrangement を、決定的な軌跡座標として展開する
- 既存 JSON 互換のため、`path` の既定値は `none` とする

### v1.26 (2026-05-03)

**Build 257: CLI benchmark 診断 summary 拡張**

Build 256 の focused small bench と 3 persona review で、green / shape / motif / math balance の到達状況をより機械的に追える必要が明確になった。

CLI benchmark summary は、作品品質の評価そのものではなく、後続の人間評価と実装修正を支える診断データとして扱う。

- `color_trace` は、色 marker だけでなく否定文脈も記録する
  - 例: `緑には寄せず`, `緑ではなく`, `not green`, `avoid green`
  - 否定された色は `negated_color_markers` に入り、`requested_colors` から除外する
  - これにより「緑を出さないことが正しい」サンプルを `green_requested_but_missing_in_score` と誤警告しない
- `_score_metrics` は `score_motif_hint_counts` を返す
  - `leaf_cluster`
  - `paper_shard`
  - `ripple_knot`
  - `mountain_sign`
- `inku-cli batch` summary は、motif / math marker のサンプル番号を列挙する
  - `score_motif_hint_lines`
  - `math_balance_marker_lines`
- `math_balance_markers` は count だけでなく、どの sample で出たかを追跡できる
- summary は既存キーを維持しつつ追加キーとして拡張する。既存の benchmark JSON consumer を壊さない
- Build 257

### v1.27 (2026-05-01)

**Stage 2 過長応答対策 + DDL coverage 補完**

修正後30件ベンチで、重複・過密は改善した一方、Stage 2 が長時間応答した末に 1 instruction へ縮退するケースが残ったため、追加の診断と補完を実装した。

- Stage 2 の結果が空、`tokens_out` 過大、または長時間かつ単一 instruction の場合は、コンパクトな描画命令を要求して1回再試行する
- 再試行理由は `empty_instructions` / `excessive_tokens_out` / `slow_single_instruction` として API レスポンスに残す
- `/api/compose` は `retry_count` / `retry_reasons` / `fallback_used` を返す
- `/api/paint` は `compose_retry_count` / `compose_retry_reasons` / `compose_fallback_used` を返す
- `inku-cli paint` / `batch` の summary JSON に Stage 2 retry/fallback 情報を含める
- Score coerce layer は、Stage 2 が1命令へ縮退した場合、DDL の複数視覚句から最大5命令まで coverage 補完を行う
- 1つの `arrangement` が過大になりすぎないよう、単一 instruction の展開数にも上限を設ける

追加テスト:

- `test_coerce.py`
  - 単一 arrangement count の上限
  - 1命令縮退時の DDL coverage 補完

検証:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q

cd ../cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests -q
```

結果:

- `ruff`: all checks passed
- server pytest: `105 passed, 30 skipped`
- cli pytest: `8 passed`

### v1.28 (2026-05-01)

**Stage 1 / Stage 2 hard timeout と deterministic fallback**

不正・矛盾・曖昧入力30件ストレステストで、API / renderer は落ちない一方、Stage 1 / Stage 2 の LLM 応答が数分単位で返るケースが確認された。これに対し、LLM クライアントの read timeout とは別に、API 層で Stage 単位の hard timeout を実装した。

- Stage 1 は `INKU_STAGE1_HARD_TIMEOUT_SECONDS` を超えた場合、入力文から deterministic fallback DDL を生成する
- Stage 2 は `INKU_STAGE2_HARD_TIMEOUT_SECONDS` を超えた場合、追加 retry を待たず deterministic fallback Score へ切り替える
- 既定値はいずれも 120 秒
- `/api/interpret` は fallback 時のみ `fallback_used` / `fallback_reasons` を返す
- `/api/paint` は `interpret_fallback_used` / `interpret_fallback_reasons` を返す
- `/api/compose` / `/api/paint` の Stage 2 診断には `stage2_hard_timeout` / `stage2_retry_hard_timeout` を記録する
- `inku-cli paint` / `batch` の summary JSON に Stage 1 fallback 情報も含める
- build number: 172

追加テスト:

- `test_api.py`
  - Stage 2 hard timeout 時に `/api/compose` が fallback Score を返す
  - Stage 1 hard timeout 時に `/api/paint` が fallback DDL で継続する

**複数ユーザー同時描画時の安全性**

複数ユーザー、または同一ユーザーが同時に `/api/paint` を実行した場合に、共有資源が無制限に増えたり、ユーザー別の生成回数が欠落したりしないようにする。

- `user_accounts.image_generation_count` は、DB 側の単一 `UPDATE` で `image_generation_count = image_generation_count + amount` として原子的に加算する
- Stage 1 / Stage 2 の LLM 呼び出しは共有 bounded executor で実行する
- Stage executor の worker 数は `INKU_STAGE_WORKERS`、待機を含む上限は `INKU_STAGE_QUEUE_LIMIT` で設定する
- Stage 呼び出しが hard timeout しても、下層の LLM 呼び出しスレッドは Python から強制停止できない。そのため timeout 済みの処理も実際に完了するまで Stage capacity を保持し、後続リクエストが無制限に積み上がらないようにする
- Stage capacity を取得できない場合は Stage hard timeout と同じ fallback 経路へ進む
- `/api/settings/status` は `stage_execution` に worker 数、queue 上限、`submitted` / `completed` / `failed` / `timed_out` / `rejected` を返す
- 履歴保存、履歴一覧、スター、削除、復元は引き続き `user_id` で絞り込み、ユーザー間で履歴が混在しないようにする

追加テスト:

- `test_api.py`
  - 同一ユーザーの生成回数を並列更新しても最終カウントが欠落しない
  - Stage hard timeout 後も underlying worker 完了まで capacity が保持され、次の Stage 実行が上限で拒否される
  - `/api/settings/status` が `stage_execution` の状態を返す

検証:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q

cd ../cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests -q
```

結果:

- `ruff`: all checks passed
- server pytest: `107 passed, 30 skipped`
- cli pytest: `8 passed`

### v1.29 (2026-05-01)

**プラグインサポートの初期実装**

アプリケーションのコア要素とノンコア拡張を分離するため、最初のプラグインフックとして canvas-size hook を導入した。

- `canvas-aspect` 参照プラグインを追加
- キャンバス比率として `square` / `golden` / `a4` / `b4` / `pillar` / `oban` / `wide` / `byobu` / `vertical` をサポート
- ユーザーごとのプラグイン設定を DB の `plugin_storage` に JSON として保存
- `/api/auth/me/plugin-storage` と `/api/auth/me/plugin-storage/{plugin_id}` を追加
- `/api/paint`、`/api/compose`、履歴保存時に `canvas_aspect` を渡し、Renderer が SVG の `width` / `height` / `viewBox` を変更
- Web UI ではモデル選択ボタンの左側にプラグイン呼び出しボタンを追加
- キャンバス比率変更時は現在の描画コンテキストをクリアし、選択比率のプレースホルダー画像を表示
- ステータスバーには現在または履歴のキャンバス種類を表示し、プラグイン選択が描画コンテキストに含まれていることを確認できる
- 設定ダイアログのプラグインタブを整理し、システム標準プラグインとして `canvas-aspect` の説明、バージョン表記、有効/無効トグルを表示
- ユーザープラグイン追加 UI はスケルトンとして配置し、外部ローダー実装後に有効化する
- 設定ダイアログはタブ切替で上端位置が動かないよう、通常設定モードでは固定上端・固定高に変更
- プラグイン作成のリファレンスとして `PLUGIN.md` を追加
- build number: 178

### v1.29 follow-up (2026-05-01)

**キャンバスプラグインの Score 反映**

`canvas-aspect` で選択したキャンバス種類を JSON Score と履歴に明示的に保存するようにした。

- `/api/paint`、`/api/compose`、履歴保存時に渡した `canvas_aspect` を `Score.canvas` に反映する
- Renderer は request の `canvas_aspect` を優先しつつ、未指定時は `Score.canvas` を参照して SVG の `width` / `height` / `viewBox` を決定する
- 履歴表示・JSON タブで、生成に使われたキャンバス種類が `score.canvas` として確認できる
- build number: 179

### v1.30 (2026-05-01)

**ステータスバーとパネル操作の整理**

描画パネル下部のステータスバーを、現在の生成コンテキストと成果物操作を素早く確認できる場所として整理した。

- ステータスバーには Stage 1 / Stage 2 モデル名、色カタログ名に加えて、キャンバスプラグインの現在キャンバス種類を表示する
- 履歴表示時は履歴レコード内の JSON Score `canvas` を優先し、当該履歴が生成されたキャンバス種類を表示する
- SVG / PNG 書き出しボタンから `エクスポート:` ラベルを削除し、download アイコン + 形式名の表示に変更する
- 記述 / バッチ / デモの開始系ボタンを共通コンポーネント化し、見た目と disabled 状態を統一する
- 記述パネルの解釈 box を拡大し、語彙ハイライト表示と編集 textarea の高さを揃える
- build number: 185

### v1.31 (2026-05-02)

**記述タブ進捗マスコットのキウイ化**

記述タブの単発描画中、および解釈（正規化DDL）からの再描画中に表示する進捗バー上のマスコットを、小鳥からキウイへ変更した。

- キウイは左向き固定で表示し、右向き反転や方向転換の中間フレームは使用しない
- 長いくちばしで地面をつつく、鼻を鳴らす、瞬きする、くちばしを開けてダッシュするなどの仕草を行う
- 脚は胴体下部の固定位置から生え、足先だけが動くようにして、付け根が揺れない
- 足先の動きはややダイナミックにし、歩行時の踏み替えが分かるようにする
- 胴体と尾側を別グループ化し、低頻度でお尻を振る仕草を行う
- キウイボールでは頭・胴体・くちばしを残した丸まり表現とし、6秒以上その場に留まる
- キウイボール中は目を閉じ、頭だけがゆっくり「こくり、こくり」と動く
- 進捗マスコットは `KiwiMascot.svelte` として共通コンポーネント化し、記述パネルと DDL 再描画パネルから利用する
- build number: 199

### v1.32 (2026-05-02)

**プロフィールダイアログ**

アプリレールのユーザーアイコンメニューにプロフィールを追加し、ログインユーザーが自分のアカウント情報を直接変更できるようにした。

- ユーザーアイコンメニューは、プロフィールとログアウトを選択できる
- プロフィールを選択すると、設定ダイアログとは独立したプロフィールダイアログを表示する
- プロフィールダイアログではメールアドレスを変更できる
- パスワード変更時は、現在のパスワードと新しいパスワードを入力する
- 新しいパスワードは 8 文字以上とし、現在のパスワードが一致しない場合は変更を拒否する
- 自己プロフィール更新 API として `PATCH /api/auth/me/profile` を追加する
- 管理者によるユーザー管理 API とは分離し、ログインユーザー自身のメールアドレス / パスワード変更に限定する
- build number: 206

### v1.33 (2026-05-02)

**設定ダイアログのロール別表示制御**

設定ダイアログで、ロールごとの表示範囲と変更権限を整理した。

- `DB設定` タブは `admin` ロールのみに表示する
- `ユーザー管理` タブは `admin` ロールのみに表示する
- `プラグイン` タブは全ログインユーザーに表示する
- プラグイン設定の変更は `admin` ロールのみに許可する
- 非 admin ユーザーが設定を開く場合、保存済みタブが `DB設定` / `ユーザー管理` であっても `プラグイン` タブへフォールバックする
- plugin storage 更新 API は admin のみ利用可能とする
- build number: 212

### v1.34 (2026-05-02)

**プラグインディレクトリ構成の整理**

プラグインを system と user の配置に分け、各プラグインを専用ディレクトリに置く構成へ変更した。

- サーバー側プラグイン実装を `server/src/inku_server/plugins/` パッケージへ移行
- system plugin は `server/src/inku_server/plugins/system/<plugin_name>/` に配置する
- user plugin 用に `server/src/inku_server/plugins/user/` 名前空間を予約する
- Web 側プラグイン実装を `web/src/lib/plugins/system/<plugin-id>/` に配置する
- user plugin 用に `web/src/lib/plugins/user/` を予約する
- 既存の `canvas-aspect` は system plugin として専用ディレクトリへ移動する
- `server/src/inku_server/plugins/__init__.py` は API / Renderer から参照する安定した hook API を再エクスポートする
- build number: 213

### v1.35 (2026-05-02)

**エクスポートテンプレート**

設定ダイアログに `エクスポート` タブを追加し、PNG 保存形式をユーザーごとのテンプレートとして管理できるようにした。

- `エクスポート` タブは全ログインユーザーが利用できる
- テンプレートはサーバー DB のユーザー別設定として保存する
- テンプレート項目は、テンプレート名、説明、y軸高さ（ピクセル数）とする
- 既定テンプレートとして `PNG 1024px` と `PNG 2048px` を用意する
- ステータスバーの PNG ボタンから表示されるメニューは、保存済みテンプレートを参照する
- PNG 書き出し時は y軸高さを基準にし、現在のキャンバス比率から横幅を算出する
- API として `GET /api/auth/me/export-templates` と `PUT /api/auth/me/export-templates` を追加する
- build number: 214

### v1.36 (2026-05-02)

**キャンバス比率: 屏風**

キャンバス比率プラグインに `byobu` を追加した。

- 比率は `2.2:1`
- 表示名は `Byobu`
- 説明は「日本の屏風。六曲一双の一隻に準じる横長の型」
- 表示順は `Wide` の下、`Vertical` の上
- build number: 215

### v1.37 (2026-05-02)

**DBバックアップ設定**

DB設定タブに、DBファイルサイズ表示とバックアップ設定を追加した。

- DB設定タブは引き続き `admin` ロールのみ表示する
- SQLite ファイル DB のサイズを表示する
- DBバックアップ設定として、保存間隔（日）と最大保存世代数を設定できる
- 既定値は、保存間隔 7 日、最大保存世代数 4 世代
- `/api/settings/status` 取得時に保存間隔を超えていれば自動バックアップを作成する
- 自動バックアップは設定された最大保存世代数に従って古いものを削除する
- `今すぐバックアップ` ボタンで手動バックアップを作成できる
- 手動バックアップは最大保存世代数のカウント対象外とする
- SQLite 以外の DB では、ファイルレプリカ方式のバックアップは非対応として表示する
- API として `PUT /api/settings/db-backup` と `POST /api/settings/db-backup/run` を追加する
- build number: 216

### v1.38 (2026-05-02)

**解釈 box の DDL 編集ダイアログ統合**

DDL を直接編集する操作を、独立した DDL 編集タブではなく、記述タブの解釈（正規化DDL）box に統合した。

- DDL編集タブは廃止し、記述 / バッチ / デモの3タブ構成に戻す
- 記述タブで生成後に表示される解釈 box は、ハイライト付き textarea として直接編集できる
- 解釈 box 上部には `歳時記` / `DDL編集` ボタンを横並びで表示する
- `歳時記` は右スライド式の歳時記ドロワーを開き、語彙クリック時は解釈 box のカレントキャレット位置へ挿入する
- `DDL編集` は大きな DDL 編集ダイアログを開く
- ダイアログ左側に行番号付きの DDL 編集エリア、右側に縦2列の歳時記語彙エリアを表示する
- ダイアログ下部には、DDLの概要と文法の簡易ガイドを表示する
- ダイアログ内から `DDLから描画` は実行せず、描画実行は解釈 box 直下のボタンに集約する
- 解釈 box 直下にも `DDLから描画` ボタンを表示し、ダイアログを開かずに現在の DDL から再描画できる
- DDL を直接編集した後に記述タブの `描画する` を押した場合は、`DDLの編集結果が失われます、よろしいですか？` の確認ダイアログを表示する。選択肢は `キャンセル` / `OK` / `DDLから描画` とし、`OK` は通常の Stage 1 からの再生成、`DDLから描画` は編集済みDDLからの Stage 2 再描画を実行する
- 記述タブで通常描画またはDDL再描画が進行中の間は、記述タブに実行中エフェクトを表示し、バッチ / デモ側の開始ボタンを抑制する
- DDL再描画中は token 表示、経過秒数、停止ボタン、キウイ進捗マスコットを表示する
- 停止ボタンは `/api/compose` リクエストを abort する
- キャンバス比率プラグインが追加した任意のキャンバスIDを JSON Score の `canvas` として保持できるよう、Score schema の `canvas` は静的列挙ではなく文字列として扱う
- build number: 246

### v1.39 (2026-05-03)

**SVG保存形式プロファイル**

SVG保存形式を、表示用・編集用・互換優先に分離した。

- DB の `history.svg` には従来どおり表示用 SVG を保存する
- 履歴表示、PNG 再生成、artifact 再生成は DB に保存された表示用 SVG を正本として扱う
- 編集用 SVG は JSON Score とサーバー側の色カタログ情報からダウンロード時に都度生成する
- 互換優先 SVG も JSON Score とサーバー側の色カタログ情報からダウンロード時に都度生成する
- `display` プロファイルは現行表示互換を優先し、既存の texture filter / blur / clip を維持する
- `editable` プロファイルは Illustrator / Affinity で編集しやすいよう、`layer_00_background`、`layer_10_content`、`instruction_###_*`、`mark_###_###_*` 形式の安定 ID とグループ構造を追加する
- `compat` プロファイルは汎用SVGビューアで壊れにくいことを優先し、filter と clip-path を使わない
- API として `POST /api/render-svg` と `GET /api/history/{item_id}/svg?profile=...` を追加する
- Web UI の SVG ボタンは `Display` / `Editable` / `Compat` のメニューから保存形式を選択できる
- CLI の `paint` / `batch` は `--svg-profile display|editable|compat` で保存する SVG プロファイルを選択できる
- build number: 267

### v1.40 (2026-05-03)

**バッチ / デモの色カタログランダム選択**

バッチモードとデモモードに、描画ごとに色カタログをランダム選択するオプションを追加した。

- バッチモードでは実行ごとの一時オプションとして `描画ごとに色カタログをランダム選択` を指定できる
- デモモードでは同じオプションをデモ設定として保存し、ユーザーごとに復元する
- ランダム選択はサーバーから取得済みの色カタログ一覧を正とし、各描画の `/api/paint` に選ばれた `catalog_id` を渡す
- 履歴保存時は、実際にレンダリングした `render_color_catalog_id` を優先して保存する
- ステータスバーの色カタログ表示は、現在の選択値だけでなく描画結果の `render_color_catalog_id` を反映する
- build number: 271

### v1.41 (2026-05-03)

**履歴描画ハッシュとCLI履歴エクスポート**

履歴DBの各描画に、描画内容に基づく `render_hash` を付与する。

- `render_hash` は canonical JSON 化した `input` / `ddl` / `score` / `svg` / render metadata から SHA-256 で生成し、DB上には64桁hexを正規値として保存する
- API の履歴レスポンスと `/api/paint` の履歴保存レスポンスには `render_hash` と、末尾4桁を大文字化した `render_hash_short` を含める
- 既存履歴はDBマイグレーション時に `render_hash` をバックフィルする
- 履歴管理ダイアログでは、サムネイルとリスト表示に `#ABCD` 形式の4桁短縮ハッシュをレイアウトを壊さないチップとして表示し、クリックで正規ハッシュをコピーできる
- 履歴管理ダイアログは現在のウインドウサイズに対して上下左右10%の余白を基準に大きく開き、サムネイル下には指示文の先頭、その下にスター、短縮ハッシュ、削除/復元操作を並べる
- サムネイル下の指示文は、先頭に `#123` のような番号がある場合はその番号を省略して表示する
- サムネイル操作部の未スター状態は小さくても視認できるコントラストにし、左上の選択チェックボックスも小型化して枠線を細くする
- 履歴管理ダイアログのページ切り替えでは、複数の再取得が重なっても最後の完了時に読み込み中表示を必ず解除する
- 履歴管理ダイアログのサムネイル表示は、ダイアログ内の実表示領域から列数と行数を測定し、スクロールバーを出さずに収まる件数をページサイズとして動的に再計算する
- サムネイル操作行のスターはクリックイベントをカード選択から分離し、カード実寸を使ってページサイズを再計算することで下端余白を詰める
- サムネイル操作行は左下にスターを置き、ハッシュは `#` を付けず削除ボタンと同じボタン寸法感に揃える
- ダークモードでもスター済み状態の色が通常状態に上書きされないよう、スター済み表示を明示する
- 履歴管理ダイアログのサムネイルはマウスオーバーで拡大プレビューを表示せず、一覧の位置と選択操作を安定させる
- 履歴管理ダイアログ上部は、タイトル/表示切替/件数/ページ移動を1段に集約し、選択/絞り込み/検索を2段目にまとめることでサムネイル表示領域を広げる
- サムネイル実寸によるページサイズ再計算時は、ページ番号を維持し、次ページ操作後に先頭ページへ戻らないようにする
- 履歴管理ダイアログの各画像に表示する個別削除操作は、文字ラベルではなく小さなごみ箱アイコンボタンで表示する
- JSONタブ、描画レスポンス、履歴保存時のartifact JSONには、サーバーが実際に使用した解決済み `stage1_model` / `stage2_model` を記録する
- 現時点のカラーマネジメントは sRGB のみを対象とし、JSONタブ、描画レスポンス、履歴、artifact JSONには `render_color_profile: { id: "srgb", name: "sRGB IEC61966-2.1", standard: "IEC 61966-2-1:1999" }` を記録する。Adobe RGB 等の広色域プロファイルは将来拡張候補とし、現時点では実装しない
- JSONタブは、モデル/ビルド/カラープロファイル/色カタログなどの属性メタ情報を先頭に表示し、その後に `score` を表示する
- 履歴から画像を開き直した場合も、JSONタブに履歴保存済みの `stage1_model` / `stage2_model` を表示する
- 設定ダイアログに管理者向け `モデル設定` タブを追加する。Stage 1 / Stage 2 の既定 provider / model と、provider 別の base URL / API key をサーバー DB の app settings に保存する
- 組み込みの商用 LLM provider は公式名称に合わせて OpenAI API Platform / Claude API / Gemini API とし、非商用 API provider は NVIDIA NIM、ローカル provider は Ollama (OpenAI互換) / Intel OVMS (OpenAI互換) を対象とする
- 管理者は設定ダイアログのモデル設定タブで、接続サービスを追加・削除できる。追加サービスは service ID、表示名、接続形式 (`openai_compatible` / `anthropic` / `gemini`)、Base URL、任意の初期 API key を持つ。サービス追加ダイアログの `追加` は即座にサーバーへ保存し、サービスパネル下部に冗長な全体保存ボタンは置かない。モデル一覧は追加時には手入力せず、サービスごとの `モデルリスト取得` で取得する
- service ID は DB 内の接続設定キー、Stage 1 / Stage 2 の provider 参照、API 呼び出し時の provider 判定、重複防止に使う内部IDであり、作成後は編集不可とする。画面に表示するサービス名は後から編集できる
- 接続サービスごとに `モデルリスト取得` を実行できる。サーバーは保存済み Base URL / API key を使って provider 種別ごとの models API を呼び、取得したモデル一覧を当該サービス定義へ保存する。取得結果の成功/エラーは公開モデル選択ダイアログ下部に表示する。API key はブラウザへ送らない
- API key はサーバー側にのみ保存し、`GET /api/settings/models` の応答では設定済みかどうかのみを UI 表示に使う。ブラウザへ生の API key は返さず、設定済みの場合の入力欄は `保存済みキーを維持` と表示して編集不可にする。未設定の状態で新しい key を入力した場合は、そのサービスの保存ボタンで保存する
- DB 内の provider API key は `enc:v1:` 形式で暗号化して保存する。暗号鍵は `INKU_SECRET_KEY` を優先し、未設定の場合は `INKU_SECRET_KEY_FILE` または `~/.local/share/inku/secret.key` のローカル鍵を使う。既存の平文キーは読み込み互換を維持し、次回保存時に暗号化形式へ移行する
- `PUT /api/settings/models` は管理者のみ利用でき、API key の新規設定、保持、明示削除を区別する
- LLM 呼び出しは model ID の provider prefix (`openai:` / `anthropic:` / `gemini:` / `nvidia:` / `ollama:` / `ovms:`) と、設定タブの既定値から接続先を解決する。旧来の NVIDIA slash ID とローカル OVMS ID も互換扱いとして受け付ける
- Web UI から `/api/paint` / `/api/interpret` / `/api/compose` へ送るモデルIDは、接続先 provider と結合して `openai:gpt-5.2` のような provider 付き ID に正規化する。API が provider prefix の無い model ID を受け取った場合でも、その ID がユーザー設定中の Stage 1 / Stage 2 model と一致する場合は、同じユーザー設定の provider で補完してから dispatch する
- デモ指示文生成も同じ provider 解決を使い、OpenAI API Platform / Claude API / Gemini API / NVIDIA NIM / Ollama / Intel OVMS の各接続設定を経由する
- LLMサーバー接続設定はグローバルな管理者設定とし、Stage 1 / Stage 2 の接続先・モデル選択はユーザーごとの `user_accounts.model_settings` に保存する。モデル選択ダイアログの確定時に `/api/auth/me/settings` へ保存し、ログイン時に復元する
- 管理者は設定ダイアログのモデル設定タブで、provider ごとに一般ユーザーへ公開するモデルを個別に On/Off できる。公開モデル選択はサービスパネル内ではなく個別ダイアログで行い、`モデルリスト取得` / 検索 / `全て選択` / `全て解除` も同ダイアログに置く。公開モデル選択ダイアログ内のチェック変更はドラフトとして扱い、`保存` で初めてサーバーへ反映し、`キャンセル` またはダイアログ外クリックでは破棄する。モデル設定タブ本体には公開中モデルのみを要約表示する。`GET /api/models` はログイン済みユーザー向けに公開モデルのみを返し、モデル選択ダイアログはこの一覧を使う
- CLI に `history-export` を追加し、`--from` / `--to` の履歴順範囲指定と、個別ハッシュ指定を受け付ける
- CLI の `history-export` は、選択した履歴からベンチマーク評価用の `contact-sheet.png`、個別JSON、SVG/PNG中間ファイル、`summary.json` を出力する
- 4桁ハッシュが複数候補に一致する場合、CLI は曖昧としてエラーにし、より長い桁数での指定を求める
- build number: 313

### v1.42 (2026-05-04)

**サーバーワイド自動保存設定**

出力 artifact ファイルの自動保存を、ユーザー個別設定ではなくサーバーワイドな管理者設定として扱う。

- 設定ダイアログに admin 向け `その他（サーバー）` タブを追加する
- `その他（サーバー）` タブでは、描画ファイル自動保存の On/Off、保存先フォルダの絶対パス、PNG 自動保存サイズを設定できる
- PNG 自動保存サイズは `1080px` / `2160px` から選択する
- サーバーは `app_settings.output_save_settings` に `enabled` / `output_dir` / `png_size` を保存する
- 初期保存先は `INKU_OUTPUT_DIR`、初期 PNG サイズは `INKU_OUTPUT_PNG_SIZE` を使い、未指定時は `~/.local/share/inku/outputs` と `2160px` を使う
- `PUT /api/settings/output-save` は admin のみ利用でき、保存先は絶対パスのみ許可し、PNG サイズは `1080` / `2160` のみ受け付ける
- 自動保存 Off の場合も履歴 DB は正本として保存し、SVG / JSON / 入力 / DDL / PNG などの artifact ファイル保存だけをスキップする
- 保存先フォルダ配下は従来どおり `user_id/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>` 形式の日別ディレクトリ構成とする
- `その他（サーバー）` タブには保存 worker / queue、保存統計、PNG サイズを表示する。保存 worker は同時保存ジョブ数、queue は保存待ちジョブ上限であり、上限超過時は DB 履歴保存を優先して artifact 保存をスキップする
- 画面上の注記は「履歴DBが正本です。出力ファイルはバックグラウンドで保存される副産物で、DBから再生成できます。」と表示する
- build number: 324

### v1.42 (2026-05-05)

**レンダリングメタデータと履歴選択挙動**

描画結果のメタデータ表示と、履歴を選択したときの UI 選択状態の扱いを整理した。

- 描画パネル上部に、当該描画の `色カタログ`、`キャンバス`、`作成日時` を表示する
- 色カタログボタンは、固定ラベルではなく現在選択中の色カタログ名を表示する。長い名前は後半を省略し、hover title でフル名称を確認できる
- 入力パネル上部の操作順は `キャンバス比率` / `色カタログ` / `モデル選択` とする
- 描画レスポンス、履歴レコード、JSON タブ、artifact JSON に `render_canvas_aspect` を追加し、実際にレンダリングへ使用したキャンバス比率 ID を記録する
- 描画レスポンス、履歴レコード、JSON タブ、artifact JSON に `render_canvas_aspect_id` と `render_canvas_aspect_ratio` を追加する。`render_canvas_aspect_id` は明示的なキャンバス比率識別子、`render_canvas_aspect_ratio` は実際の幅÷高さの数値である
- `render_canvas_aspect` は render metadata の一部として、`render_engine_version` の直後、色カタログメタデータの前に表示する
- `render_canvas_aspect_id` と `render_canvas_aspect_ratio` は `render_canvas_aspect` の直後に表示する
- JSON Score の `score.canvas` は引き続き楽譜側のキャンバス指定として保持し、`render_canvas_aspect` は成果物側のレンダリング記録として扱う。通常は同じ値になるが、旧データや外部入力の確認性のため二重に保持する
- 互換性のため `render_canvas_aspect` は従来通り保持する。新規実装では `render_canvas_aspect_id` を識別子として扱い、旧履歴では `render_canvas_aspect` から補完する
- 設定 > その他に `履歴選択時の挙動` を追加する
- キャンバスサイズは、履歴から選択時に履歴キャンバスサイズを UI 選択へ反映するか、現時点で UI 上選択されているキャンバスサイズを維持するかを選べる
- 色カタログは、履歴から選択時に履歴色カタログを UI 選択へ反映するか、現時点で UI 上選択されている色カタログを維持するかを選べる
- 履歴選択時の挙動設定はブラウザ localStorage に保存する
- 履歴選択時の設定は UI 上の選択状態だけを更新し、保存済み履歴 SVG の再レンダリングは行わない
- build number: 340

### v1.43 (2026-05-05)

**Render Engine 境界とエンジンメタデータ**

将来の複数描画エンジン受け入れに備え、描画コアを `RenderEngine` 契約越しに呼び出す内部境界を追加した。

- `server/src/inku_server/render_engines/` を追加し、`base.py` に `RenderEngine` Protocol と `RenderEngineResult` を定義する
- 現行の `renderer.py` は `default` engine として `render_engines/default.py` から呼び出す
- 現時点では外部任意コードのロードや管理UIは実装しない。`current_render_engine()` は静的に `default` engine を返す
- `/api/compose`、`/api/paint`、互換用 `/api/history` は RenderEngine 経由で SVG を生成する
- 描画レスポンス、履歴レコード、JSONタブ、artifact JSON に `render_engine_id` と `render_engine_version` を記録する
- `history` テーブルに `render_engine_id` / `render_engine_version` カラムを追加し、既存DBは起動時マイグレーションで追従する
- `render_hash` の canonical payload に engine metadata を含め、同じ Score / SVG でも描画エンジンが異なる場合は別内容として追跡できるようにする
- 現行値は `render_engine_id: "default"`、`render_engine_version: "1"` とする
- build number: 326

### v1.43 (2026-05-05)

**サーバーログ保存ポリシー設定**

`inku-server` / `inku-api` のアプリケーションログ保存ポリシーを、管理者向けのサーバーワイド設定として扱う。

- 設定ダイアログに admin 向け `ログ保存` タブを追加する
- `ログ保存` タブでは、ログ保存とローテーションの On/Off、保存期間（日）、ローテーション周期、ローテーション済みログの圧縮 On/Off を設定できる
- 既定ポリシーは On、保存期間 `90` 日、ローテーション周期 `daily`、圧縮 On とする
- サーバーは `app_settings.log_retention_settings` に `enabled` / `retention_days` / `rotate` / `compress` を保存する
- 初期保存期間は `INKU_LOG_RETENTION_DAYS`、初期ローテーション周期は `INKU_LOG_ROTATE` を使い、未指定時は `90` 日と `daily` を使う
- `GET /api/settings/status` は現在のログ保存ポリシーに加え、`logrotate` 設定プレビューと `systemd` drop-in 設定プレビューを返す
- `PUT /api/settings/log-retention` は admin のみ利用でき、保存期間は `1` から `3650` 日、ローテーション周期は `daily` / `weekly` / `monthly` のみ受け付ける
- 画面上の注記は、ログ保存ポリシーはアプリ DB に保存されるが、`systemd` / `logrotate` への実適用にはサーバー OS の権限が必要であることを明示する
- systemd drop-in プレビューは `StandardOutput=journal+append:/var/log/inku/<service>.log` / `StandardError=journal+append:/var/log/inku/<service>.log` を使い、`journalctl -fu <service>` とファイルログの両方で追跡できる形を推奨する
- `inku-api` / `inku-server` の起動時には、60文字の `=` 罫線で囲んだ起動バナーを出力する。バナーにはサービス種別、アプリケーションバージョン、build 番号、build 日付を含める
- 起動バナーには、運用確認に必要な最小情報として mode、listen host/port、runtime / platform、ログ出力先も含める。API 側は描画エンジン ID / version も表示する
- 起動バナーの絵文字はサービスの性質に合わせて変える。API は `🧠 ⚙️ 🔌 🖌️ 🚀`、Web UI は `🎨 🖼️ 🌈 🪄 ✨ ... 🚀` を使う
- 運用検証では `inku-server` / `inku-api` の systemd drop-in と `/etc/logrotate.d/inku` を手動設定し、`NeedDaemonReload=no`、journal 出力、`daily` / `rotate 90` / `maxage 90` / `compress` の反映を確認した
- build number: 336

### v1.44 (2026-05-05)

**PNG保存テンプレートとモデル設定のAPIキー注記**

PNG保存メニューとモデル設定タブの表示を、現在の運用に合わせて調整した。

- ナビゲーションバーの PNG 保存テンプレート既定値を `1024px` / `2048px` から `1080px` / `2160px` / `4320px` に変更する
- PNG 保存テンプレートのサイズは Y軸方向のピクセル数として扱う
- 日本語UIでは、テンプレート説明と設定ダイアログの項目名を `y-axis` / `y軸高さ` ではなく `Y軸` / `Y軸の高さ` と表記する
- 既存ユーザーの保存済み PNG テンプレートが旧デフォルト `1024px` / `2048px` のみである場合は、新デフォルトへ自動的に置き換える。ユーザーが独自編集したテンプレートは維持する
- モデル設定タブの `AIサービス接続` 見出し横に、APIキーの扱いを明記する
- 表示文は「APIキーはDBに暗号化して保存され、画面には再表示されません。環境変数で設定済みのキーも初期値として扱われます。」とする
- 英語UIでも同じ意味の注記を表示する
- build number: 328

### v1.45 (2026-05-05)

**JSONメタデータへの描画ハッシュ記録**

各描画のサーバー側 `render_hash` を、履歴だけでなく JSON メタデータ領域にも記録する。

- `render_hash` は、描画内容とサーバー所有の render metadata から算出する64文字の SHA-256 hex とする
- `render_hash_short` は UI / CLI で参照しやすい4文字の大文字サフィックスとする
- `/api/paint`、`/api/compose`、JSONタブ、CLI出力JSON、保存 artifact JSON に `render_hash` / `render_hash_short` を含める
- 履歴DBから artifact JSON を再生成する場合も、DB上の `render_hash` / `render_hash_short` をメタデータ領域へ展開する
- 履歴DBは引き続き正本であり、出力ファイルは副産物として扱う

### v1.46 (2026-05-07)

**inku-cli の DDL 入力描画モード**

server / Android の CLI 比較で、Stage 1 の LLM 出力揺れを切り離し、
正規化DDL以降の差分を検証できるようにする。

- `inku-cli paint` / `inku-cli batch` に `--input-mode paint|ddl` を追加する
- 既定の `paint` は従来どおり自然言語入力を `/api/paint` に渡し、Stage 1 → Stage 1.5 → Stage 2 → render を実行する
- `--input-mode ddl` は入力テキストを正規化DDLとして扱い、Stage 1 を呼ばずに `/api/compose` へ渡す
- `--input-mode ddl --save-history` の場合、CLI は `/api/compose` の描画結果を `POST /api/history` で通常履歴DBへ保存する
- `/api/compose` は Stage 1.5 適用後の実効DDLを `ddl` としてレスポンスに含める
- CLI の DDL モードでは、出力JSONと履歴保存に `/api/compose` が返した実効DDLを使う
- Android の headless 比較スクリプト `android/scripts/headless_render_compare.sh` は `INPUT_MODE=ddl` を server 側 `inku-cli paint --input-mode ddl` にも伝搬する
- `ORIGINAL_TEXT` を指定した場合、Android / server の両方で履歴表示用の元入力および Stage 2 補助文脈として扱う
- このモードは benchmark / parity 検証用であり、自然言語からの通常描画フローの既定動作は変更しない
- build number: 352

### v1.47 (2026-05-07)

**外部クライアント保存履歴のWeb UI自動反映**

`inku-cli` や Android headless CLI など、開いている Web UI 以外のクライアントが履歴DBへ保存した描画を、Web UI の履歴ストリップへ自動反映できるようにする。

- 履歴DBは引き続き描画履歴の正本であり、Web UI は外部クライアント保存をローカル状態だけで推測しない
- Web UI はログイン済み、通常履歴表示、最新ページ表示、ドキュメント表示中の条件で、最新履歴ページを定期的に再取得する
- 再取得間隔は短すぎる polling を避けるため約12秒とし、同時再取得と5秒未満の重複再取得を抑止する
- ブラウザウィンドウが focus された時、または非表示タブから表示状態へ戻った時は、通常の間隔を待たずに最新履歴を再取得する
- 外部保存検出用の再取得では、現在選択中の履歴IDが再取得後の最新ページに残っている場合、その選択状態を維持する
- スター付きのみ表示、検索中、履歴の旧ページ表示中、履歴ロード中は、ユーザーの閲覧文脈を壊さないよう自動差し替えを行わない
- 履歴管理ダイアログが開いており、通常履歴の先頭ページを表示している場合は、外部保存反映に合わせて同ページも静かに再取得する
- build number: 361

### v1.48 (2026-05-09)

**Android ネイティブ実装の管理対象化と v1.48 対応**

Android 版を Git 管理対象のネイティブ単体アプリとして整理し、web/server 参照実装に追従するモバイル実装として明文化する。

- Android 版は Kotlin + Jetpack Compose で実装し、Room / SQLite を正式なローカル DB レイヤーとする
- アプリはシングルユーザー前提で動作し、server/web のユーザー管理、DB 管理、プラグイン管理、ログ保存などのサーバー運用機能は Android UI から除外する
- Android の開発 master は常に `web/` と `server/` とし、DDL 解釈、Stage 1.5 展開、Score 補修、SVG rendering、履歴/render metadata の互換性は server source に照らして検証する
- LiteRT-LM を Android のローカル LLM provider とし、Gemma 4 E2B を標準、E4B を高品質オプションとして扱う。GPU backend を必須とし、CPU fallback は行わない
- Gemma 4 E2B/E4B のライセンス同意、初回取得、再取得、SHA-256 検証、取得状態は Room に保存する
- Android のモデル選択 UI はモバイル操作性のため Stage 1 / Stage 2 を単一の描画モデル選択として扱う。ただし保存形式、履歴 JSON、render metadata では `stage1_model` / `stage2_model` を維持する
- モデル設定パネルは接続先ごとの独立パネルとし、サービス追加、サービス名編集、Base URL 編集、APIキー追加/削除、公開モデル選択、モデル一覧取得を提供する。接続形式はサービス追加時に設定し、既存パネルでは変更しない
- 公開モデル候補と公開済みモデルは分離して保存し、描画画面のモデル選択には公開済みモデルだけを表示する
- 描画画面では画像のピンチズーム、パン、左右スワイプによる履歴移動、ダブルタップによるプレゼンテーション表示を Android 固有 UI として提供する
- プレゼンテーション表示では画像以外の UI を隠し、余白背景を表示画像の背景色に合わせる。白背景画像ではダーク背景、黒背景画像ではライト背景を使う
- 履歴画面は 3 列サムネイルグリッドを標準とし、サーバー版のごみ箱、リスト表示、一括選択は Android では提供しない
- SVG / PNG export は server/web の `CanvasPanel` と同じ profile / template 構造を持つメニューとして実装し、Android では共有シートに渡す
- PNG template は `1080px` / `2160px` / `4320px` の Y軸高さを既定とし、Room の `export_templates` を正本とする
- `render_canvas_aspect_id` と `render_canvas_aspect_ratio` を render metadata に含め、Android でも server の canvas aspect 定義に対応する値から算出する
- Android headless render / comparison tooling を持ち、server CLI の `--input-mode ddl` と組み合わせて DDL 以降、Score 以降の parity を比較できる
- Android version は `android/VERSION`、Android build number は `android/BUILD_NUMBER` を正本とする。v1.48 世代の初期値は `1.48.0-android.1` / `148001` とする
- Android 設定メニューには versionName、versionCode、build type、applicationId、source spec、render engine version を表示するバージョン情報画面を置く
- build number: 148001

### v1.49 (2026-05-11)

**描画表示のプレゼンテーションモードと指示文字幕**

Web UI の描画タブに、展示・鑑賞向けの表示補助を追加した。

- 描画タブ右下にプレゼンテーションモードを開く全画面アイコンを置く
- プレゼンテーションモードでは表示中の SVG を最大化し、下部に履歴移動、最新表示、スター、指示文字幕切替、閉じる操作をまとめたコントロールを表示する
- プレゼンテーションモードは Escape キーでも閉じられる
- 描画タブ左下に、指示文を字幕として表示するアイコンを置く
- 通常表示の字幕は描画タブ幅を基準に左右10%のマージンを取り、描画タブ内でクリップする
- プレゼンテーションモードの字幕はウインドウ幅を基準に左右10%のマージンを取る
- 字幕に表示するテキストは、Stage 1 送信用に拡張された内部プロンプトではなく、ユーザー入力・履歴 `input`・バッチ最新行・デモ生成指示文の原文とする
- `buildEmotionHint()` などの内部補助文は、プロンプト/デバッグ表示には残してよいが、鑑賞用字幕には表示しない
- build number: 401

### v1.50 (2026-05-11)

**英語指示文対応と指示文言語 / UI言語の分離**

日本語 UI / 英語 UI の切替とは独立して、描画指示文の言語を選べるようにした。
将来の多言語対応を見据え、表示言語と解釈言語を API 境界で分離する。

- Web UI の入力ヘッダーに `指示文の言語` セレクタを追加し、`自動` / `日本語` / `English` を選択できるようにする
- `/api/paint`、`/api/interpret`、`/api/compose`、`/api/demo/instruction` は `instruction_lang` と `ui_lang` を受け取る
- `instruction_lang=auto` の場合、サーバーは入力文字列から `ja` / `en` を判定し、Stage 1 / Stage 1.5 / Stage 2 / デモ指示生成に渡す
- `/api/paint`、`/api/compose`、履歴保存、JSONタブ、保存 artifact JSON は `instruction_lang_requested` / `instruction_lang_resolved` / `ui_lang` を記録する
- `history` テーブルに `instruction_lang_requested` / `instruction_lang_resolved` / `ui_lang` カラムを追加する
- `inku-cli paint` / `batch` / `demo-instruction` は旧 `--lang` ではなく `--instruction-lang auto|ja|en` と任意の `--ui-lang` を送信する
- 既存履歴や `cli/tune_bench.md` のハッシュ参照を壊さないため、言語メタデータは `render_hash` の canonical payload には含めない
- Stage 1 prompt、Stage 2 prompt、Stage 1.5 expander / filter は `InstructionLanguageSupport` として registry に登録する
- Score coerce layer が参照する語彙・文脈 marker は `InstructionLanguageSupport.coerce_markers` として `ja` / `en` の言語別ファイルに分離する
- Score coerce layer の補修アルゴリズム本体は JSON Score 構造に対する共通処理として維持し、言語ごとの違いは marker セット側で表現する
- `ja` / `en` の既存 prompt と expander は内容を変更せず registry に載せるため、描画結果の変化を伴わない
- 第三者が追加言語を実装する場合は、まず registry に言語コード・prompt・expander・coerce marker を追加し、JSON Score schema / renderer / 色カタログの変更とは分離して検証する
- Build 403-427 では、英語版 Stage 1 / Stage 1.5 / Stage 2 の実装を日本語版とファイルレベルで分離し、英語固有の意味解釈・marker・補修語彙を追加した
- 英語版は、単語置換ではなく、英語文の時間構造・反復・前後関係・視線・出来事の核を抽象描画パラメータへ変換する方針とする
- 英語版 Stage 1.5 / coerce marker は、`before` / `after` / `again and again` / `as if` / `at once` などの時間接続、`diagonal` / `same beat` / `shifted` などの構図語、透明・反射・霧・道路・音・群れ等の視覚イベント語を言語固有の補修手がかりとして扱う
- 日本語版と英語版は同一の JSON Score schema / renderer / 色カタログを共有し、言語差は prompt、expander、marker、補修入力の段階に閉じ込める
- 英語版の品質確認として、同義の日本語 / 英語指示文30組を `square` canvas、`default` color catalog、履歴保存なしで描画し、専門家3名ペルソナで比較評価した
- Build 427 時点の30件平均では、英語版は日本語版に近い品質へ到達している。英語版は color resonance がやや高く、日本語版は constraint adherence と visual event がやや高い
- 残課題は、英語版では「整いすぎて出来事の瞬間が背景化する」こと、日本語版では「詩的な静けさが小さすぎる記号に縮約される」こと。次の改善では密度を増やさず、focal event の最小可視サイズ、コントラスト、隣接反応を強める
- build number: 427

### v1.51 (2026-07-02)

**関係（あいだ）の設計と、揺らぎのマクロスケール拡張**

Build 436 時点で観測された出力分布の収縮（構図・密度・色面の多様性低下）の一次原因分析を受けた仕様改訂。一次原因は (A) 揺らぎがミクロ層（線の震え）にのみ割り当てられ、構図レベルの一回性がどの層にも存在しなかったこと、(B) Stage 1.5 が対角・片側焦点を常時優先する固定レシピの決定的抽選機になっていたこと、(C3) JSON Score が instruction 間の関係を表す述語を持たず、構成の文法が固定レシピにしか存在しなかったこと。

- §2 原則2 に揺らぎの二スケール（ミクロ/マクロ）を明記
- §3.1 コア語彙に「あいだ (Relations)」カテゴリを追加（沿う、触れない、切る、間に）。名詞ではなく述語の追加であり、プラグイン原則1と矛盾しない
- §12.10 対策B のキャッシュ方針に、出力の一回性との両立条件を明記
- §12.11 Stage 1.5 の構図規則を「対角・片側焦点の常時優先」から「構図族からの入力依存選択」へ変更。焦点座標を固定値から領域指定へ変更。役割を「完成品レシピの注入」から「関係述語の付加」へ転換
- §13.8 に演奏の自由度の二スケール（ミクロ変動 / 関係の逐次解決）を追記
- §14「関係（あいだ）の設計」を新設。旧 §14〜§16 を §15〜§17 へ繰り下げ
- 関係修復 governor の作成を禁止（§14.6）。coerce は relation を追加できない
- 実装指示は codex-task.md、検証・受け入れ基準は tune_bench.md に記録する

### v1.52 (2026-07-04)

**事後選択の実体化（vary）と、補修部品の指紋化の禁止**

Build 441（v1.51 実装後の初回フルベンチ + 監査後修正）の3ペルソナレビューを受けた仕様改訂。レビューの詳細は `cli/tune_bench.md`「Build 441 3ペルソナレビュー」、実装指示は `no-git-sync/codex-task-v1.52.md`。3ペルソナが共通指摘した2点——(1) coerce 補修部品（近接反応の弧 93%、固定座標の小五角形 33% 等）が「システムの指紋」として全作品に反復し連作の鑑賞を壊していること、(2) 出力の振れ幅の上限が低く、外れ値（=驚き）を事後選択で扱う設計（§8）が未実体化であること——への対処。

- §8.4「事後選択の実体化 — 二段の再生成」を新設。再生成を「別の演奏」（performance seed、LLM 不要）と「別の構図」（Stage 1.5 選択シードの vary、Stage 2 の1回）の二段として定義
- §10.4「補修部品の指紋化の禁止」を新設。補修部品に (1) 部品別発火率の計測と上限監視（floor は設けない）、(2) 固定座標・固定形状のハードコード禁止、(3) 発火条件の限定（主題が壊れる場合のみ）を課す
- §12.11 に選択シードの vary 規定を追記。既定は「同じ入力は同じ拡張」を維持し、明示的な vary 指定時のみ選択をやり直す。暗黙の非決定化（自動インクリメント・時刻シード）を禁止
- codex-task.md P3-4（v1.51 で判断保留）は本改訂の §8.4 / §12.11 として確定
- ヘッダーの Version 表記を修正（v1.50/v1.51 改訂時に v1.49 のまま更新漏れとなっていた）

Build 442 実装後の検証では、`vary_seed` 経路（API / CLI / Web UI）と二段の再生成は成立した。固定 5 プロンプト × `vary_seed` 0..4 の 25 生成は 25/25 成功し、fallback は 0。JP/EN 各30件の修復部品集計では `adjacent_reaction` は 56/60 から 14/60 へ低下し、指紋抑制の主効果は確認できた。

一方で、Build 442 時点の v1.52 品質受け入れは未達だった。`angular_pulse` は 14/60、`vanishing_trace` は 26/60 で目標を満たさず、`vanishing_trace` は Build 441 の 21/60 から悪化した。`visual_event` 平均も Build 441 の 93.0 から 77.8 に低下し、品質回帰ガードを満たさなかった。

Build 443 では `vanishing_trace` の発火条件を「消失文脈」だけでなく足跡・白い息・輪郭・人影などの trace 主体がある場合に限定し、汎用 `visual_event` 補修を小さな角形パルスから入力由来座標の compact mark に変更した。JP/EN 各30件の再ベンチでは `adjacent_reaction` 11/60、`angular_pulse` 0/60、`vanishing_trace` 2/60 となり、修復部品 fingerprint の受け入れ基準は満たした。ただし `visual_event` 平均は 77.93、`negative_space_pressure` 平均は 88.97 で、Build 441 比の品質回帰ガードはまだ満たさない。したがって v1.52 は「機能実装と修復指紋抑制は完了、品質低下サンプルの追加監査が残る」状態として扱う。

Build 444 では、Build 443 で低かった `visual_event` / `negative_space_pressure` の targeted recovery を実施した。汎用 compact visual event に `color_cycle` と入力 hash 由来の対置 center を持たせ、着地して去る一時的イベントを `brief_arrival_departure` として扱い、`line of birds / river surface / another road` と `tatami / tilted quiet` の既存レシピにも色循環と対置配置を追加した。targeted benchmark では EN #06 が `visual_event` 98 / `negative_space_pressure` 100、EN #27 が単独 rerun で 70 / 76、JP #28 が 76 / 86 まで回復した。

Build 444 の JP/EN 30+30 full benchmark（`cli/out/jp-en-30-equivalent-444/{jp,en}/`）では 60/60 成功、fallback 0。修復部品は `adjacent_reaction` 10/60 (16.7%)、`angular_pulse` 0/60、`vanishing_trace` 2/60 (3.3%) で、v1.52 の repair fingerprint 受け入れ基準は継続して満たした。一方で品質平均は `visual_event` 79.90、`negative_space_pressure` 89.97、`motion_energy` 94.57、`constraint_adherence` 93.33 となり、Build 441 基準（`visual_event` 93.0、`negative_space_pressure` 96.23、`motion_energy` 97.7、`constraint_adherence` 86.0）に対して `visual_event` と `negative_space_pressure` が -5 以内の品質回帰ガードを満たさない。したがって現時点の v1.52 は、Phase A-D の実装・計測・vary・修復指紋 acceptance は完了、品質回帰ガードは未達、という進捗として扱う。追加の修正は、marker 語彙や新 governor を増やすのではなく、低スコア行（例: EN #21 `visual_event` 40 / `negative_space_pressure` 26、JP #23 `negative_space_pressure` 42、JP #02/#03 `visual_event` 48）の原因を個別監査し、既存 recipe の配置・色循環・対置関係を一般化する方向で行う。

Build 445 では、Build 444 の低スコア監査を受けて、DDL coverage の小さな点・円・楕円を compact focal mark として扱う一般化を追加した。英文 DDL の文分割を改善し、`circle` と `ellipse` を同一視せず、`radius` / `半径` 指定や「小さい点」「small dot」系の coverage を低密度・outward fade・negative space preserved の小さな前景 mark として保持する。これは marker 語彙や新しい全体 governor の追加ではなく、既存 coerce fallback の形状・サイズ・空白保持を入力記述に合わせて補正する変更である。

Build 445 の JP/EN 30+30 full benchmark（`cli/out/jp-en-30-equivalent-445/{jp,en}/`）は 60/60 成功したが、JP #27/#28 は server timeout 後の最終リトライでも stage2 timeout となり、保存済み fallback result を使用した（fallback 2/60）。修復部品は `adjacent_reaction` 8/60 (13.3%)、`angular_pulse` 0/60、`vanishing_trace` 2/60 (3.3%) で、repair fingerprint gate は引き続き合格。品質平均は `visual_event` 80.43、`negative_space_pressure` 91.47、`motion_energy` 93.73、`constraint_adherence` 94.17、`color_resonance` 96.83、`figurative_risk` 1.33。Build 441 基準に対して `negative_space_pressure` / `motion_energy` / `constraint_adherence` は -5 以内に戻ったが、`visual_event` は基準 93.0 に対して 80.43 で未達。低スコア行は JP #02 (`visual_event` 40)、JP #21 / EN #04 / EN #20 / EN #21 (`visual_event` 48) などで、v1.52 の残タスクは visual-event の意味的な出来事性を回復することに絞られた。

Build 446 / 446-2 では、Build 445 で固着していた低 `visual_event` 行に対して、既存 instruction / arrangement metadata だけを補強する一般化を追加した。小さな点・円・楕円の compact focal mark は、event context では `visual event preserved as compact focal accent` として扱い、既存 focal event には反対象限の `arrangement.center`、`color_cycle`、余白保持、低密度、outward fade を与えて counterweight を明示する。`inherited_memory` 型で出来事性が弱い場合は、既存 support instruction に `visual event inherited memory trace preserved on existing support` を付与する。これは新しい描画部品の追加ではなく、既存要素の配置・色循環・意味ラベルを補強する変更である。

Build 446-2 の JP/EN 30+30 full benchmark（`cli/out/jp-en-30-equivalent-446-2/{jp,en}/`）は 60/60 成功した。JP #09 のみ final retry でも stage2 timeout となり fallback result を使用した（fallback 1/60）。品質平均は `visual_event` 92.85、`negative_space_pressure` 94.30、`motion_energy` 96.95、`constraint_adherence` 95.50、`color_resonance` 99.75 で、Build 441 基準の -5 以内という品質回帰ガードを満たした。修復部品は `adjacent_reaction` 13/60 (21.7%)、`angular_pulse` 0/60、`vanishing_trace` 1/60 (1.7%) で v1.52 の repair fingerprint gate も合格。fable5 が後継指紋候補として指摘した `inherited_memory_arc` は 4/60 (6.7%) として新たに計測対象へ加えた。

ただし relation drop rate は JP 15/53 (28.3%)、EN 22/51 (43.1%)、合算 37/104 (35.6%) で、fable5 が参照した 20% 目安を超えている。v1.52 の relation 方針は drop-only を維持し、coerce で relation を修復・補完しないことなので、この値は Build 446-2 時点の未解決リスクとして扱う。対策する場合は Stage 2 に「安全に置ける relation だけを出し、迷う場合は relation を省略する」方向のプロンプト改善に限定し、validator の修復化や relation 補完は行わない。

Build 447 では relation drop を blocking として扱い、Stage 2 prompt に relation の発火条件を強化した。普通の配置語（斜めの帯に沿って、揺れる軌跡に沿って、川沿い、道沿い等）を relation にしないこと、`between` は直前2つの輪郭 instruction が揃う時だけ使うこと、迷う場合は relation を省略することを明示した。しかし Build 447 の JP/EN 30+30 full benchmark では relation drop が JP 13/55、EN 4/29、合算 17/84 (20.2%) となり、fable5 が blocking とした 20% 目安をわずかに超えた。

Build 448 では、relation を「正規化DDLに `前の線に沿って` / `前の形に触れない` / `前の線を切る` / `前の二つの間に`（英語では corresponding previous-object phrase）が文字どおりある場合だけ残す」Stage 2 後段 gate に限定した。自然文由来の「周囲」「同じ拍子」「先行/遅れ」「触れていない」「近く/遠く」などは relation ではなく、position / path / rotation / spacing で表す。coerce の方針は変えず、relation の修復・補完は行わない。

Build 448 の JP/EN 30+30 full benchmark（`cli/out/jp-en-30-equivalent-448/{jp,en}/`）は 60/60 成功した。JP #01 のみ final retry でも stage2 timeout となり fallback result を使用した（fallback 1/60）。品質平均は合算で `visual_event` 92.40、`negative_space_pressure` 95.87、`motion_energy` 97.77、`constraint_adherence` 92.00、`color_resonance` 99.27 となり、Build 441 基準の -5 以内という品質回帰ガードを満たした。修復部品は `adjacent_reaction` 14/60 (23.3%)、`angular_pulse` 0/60、`vanishing_trace` 2/60 (3.3%)、`inherited_memory_arc` 4/60 (6.7%) で、v1.52 の repair fingerprint gate を満たした。relation drop は JP 1/6 (16.7%)、EN 0/2、合算 1/8 (12.5%) で、fable5 が blocking とした 20% 目安を下回った。自然文 fable set では relation sample rate が低くなるが、これは relation を fixed previous-object phrase 専用に戻した結果であり、drop-only validator 方針と整合する。これにより v1.52 の残タスク（vary、repair fingerprint、quality guard、relation blocking）は完了として扱う。

**v1.52 クローズ（2026-07-07）**: Build 448 を v1.52 の受け入れとして確定し、クローズする。判断理由は次の4点。(1) 受け入れ基準（repair fingerprint 3ゲート、品質回帰ガード、vary の後方互換・決定性・分散、relation drop blocking）を全項目満たした。(2) Build 448 の JP/EN 60枚に対する3ペルソナ再評価（`cli/tune_bench.md` 参照）で、v1.52 の起点だった Build 441 の2大課題——補修部品の指紋化と振れ幅の上限——の解消を目視確認した。定型部品の反復は消え、外れ値（驚き）が出るようになり、キュレーター視点で60枚中20〜25枚が選出可能な水準に達した。(3) relation の使用縮退（relation を持つサンプルが 30件中 21〜22 件から 2〜3 件へ減少）は、「relation は正規化DDL中の明示的な previous-object 句（前の線に沿って / 前の形に触れない / 前の線を切る / 前の二つの間に、および英語同義句）専用とし、自然文由来の近接・拍子・先行/遅れは position / path / rotation / spacing で表す」という仕様として受け入れる。これは一時的な回避ではなく §14 の関係述語の定義の確定であり、drop-only validator 方針と整合する。(4) 品質判定指標（visual_event 等の judge metric）は人間評価との乖離例（JP #23: visual_event=28 だが目視評価は最良クラス）が確認されたため、以後は受け入れゲートではなく回帰検知の参考値として扱う。品質の最終判定は §8 の設計思想どおり人間の事後選択に属する。judge metric 自体の再調整は行わない（governor 化の回避）。以後の開発の完成軸は品質ゲートの漸近改善ではなく「他人が自分の視覚的短歌を書ける状態」（1.0）に移す。作業計画は v1.6 として別途管理する。


### v1.60 (2026-07-07)

**品質ループから「一人で遊べる」状態へ**

v1.52 Build 448 でエンジン品質ゲートをクローズしたため、完成軸をメトリクス改善から、第三者が README だけでセットアップし、自分の視覚的短歌を書き、Saijiki を参照し、解釈フィードバックを見て、vary で選び、履歴から再現できる状態へ移す。

- `render_hash` を `rh2:<sha256>` の作品エディションIDとして再定義した。保存済み JSON Score、`render_seed`、`vary_seed`、`render_build_number`、`render_color_catalog_id`、render engine metadata から算出し、SVG本文・入力文・正規化DDL・LLM応答本文は主材料に含めない。既存64桁hex hash は legacy 表示互換として残す。
- 履歴DBに `vary_seed` を保存し、履歴管理から保存済み Score + seed で同じ作品を再レンダリングできるようにした。
- 入力欄に後処理近似の解釈フィードバックを追加した。Stage 1 schema や prompt は変更せず、Saijiki語・感情語・DDLに残った語を墨の濃淡で表示する。
- 作品表示では詞書（入力記述）を初期表示し、記述と画の緊張関係を作品表示の一部として扱う。
- README 日英に Quick Start、provider/API key 設定、二段の再生成、Saijiki 6色制約、履歴再現の説明を追加した。
- Build 448 ギャラリー候補を `docs/gallery-candidates-build448.md` に記録した。最終選定は人間の事後選択として残す。
- ギャラリーの最終選定は v1.70 以降へ持ち越す。v1.60 では候補記録までを完了範囲とし、作品選定そのものは次世代の評価・公開作業に属する。
- Phase E（疎出力の Stage 1.5 対応）は E-2 方針を採用する。新しい専用 metric や marker は作らず、既存指標（`visual_event` / `negative_space_pressure`）と目視で観察する。v1.60 では疎出力を blocking 実装対象にしない。

### v1.70 (2026-07-08)

- 直前/現在の二枚並置と記述 diff を左ペインに追加し、推敲の痕跡を鑑賞できるようにした。
- LLM Model Inspection として、同一記述を現在の Stage 1 モデルと別 Stage 1 モデルへ並列に通し、正規化DDLと出力を横並び比較できる鑑賞用ビューを追加した。judge 値は表示しない。
- Nature plugin の参照実装として `Nature.風` / `Nature.うねり` / `Nature.無風` を Stage 1.5 の語彙マクロに追加した。`Nature.` 名前空間の明示参照のみ発火し、名前空間なしの通常語彙は従来通り扱う。
- Nature plugin は既存の DDL 表現を variation / arrangement へ導くだけで、新 primitive・新 Score フィールド・新 coerce は追加しない。マクロだけで足りたため、プラグイン原則1/5は維持する。
- Saijiki に Nature plugin カテゴリを追加し、通常語彙と区別する薄い朱系の表示にした。
- 候補4枚の同時生成、複数選択保存、スター時の任意メモ、別解釈の `interpretation_seed` 記録を追加し、§8 の事後選択を UI と履歴に接続した。
- LLM Model Inspection の比較先は、現在の Stage 1 provider がクラウド provider の場合、まず API key 不要のローカル provider を候補にする。これは鑑賞用比較を quota や provider 側の利用不能に過度に依存させないための実装上の選択であり、judge 値は引き続き表示しない。
- 候補4枚、解釈も含める、選を残す、モデル比較、自動補正などの主要操作に多言語対応ツールチップを追加した。ツールチップ文言はメイン UI の言語切替に追従し、表示言語と入力言語を分ける既存方針を保つ。
- 左アプリレールの展開はマウスオーバーではなく、左上の明示的な伸ばす/格納するトグルボタンで制御する。誤展開を避け、作業領域の幅を利用者が固定できるようにする。
- Build 458 を pentala 実機で確認し、D-1/D-2 のスクリーンショットを `no-git-sync/screen-cap/`、確認メモを `cli/tune_bench.md` に記録した。

### v1.71 (2026-07-08)

- JSON Score に instruction-level の `surface` と canvas-level の `canvas.ground` を追加し、面の質感とキャンバス地の質感を SVG 実装詳細から分離した抽象属性として保持できるようにした。
- Renderer に display / editable / compat profile ごとの質感演奏を追加した。display は filter / clipPath を使い、editable は安定 ID の vector group、compat は filter / clip-path を避ける単純化出力とする。
- Stage 1 / Stage 2 prompt に「面:」「地:」の扱いと surface / ground mapping を追加し、質感語を補助図形注入ではなく対象 instruction の属性として扱うようにした。
- render metadata に `render_texture_version`、`render_texture_profile`、`render_canvas_ground`、`render_surface_textures`、`texture_degraded` を追加した。
- texture seed を Score / instruction / texture kind / performance seed から導出し、固定座標の紙目や高頻度の無指定 texture 注入が Renderer の指紋にならないようにした。
- 左アプリレール、入力・出力パネルの各ボタンやタブに多言語対応ツールチップを追加・拡大適用し、操作の明瞭化を図った。


### v1.72 — 推敲・比較UIの再構成

- 推敲要素をタッチ・配置・読み取りのチェック選択へ統合し、読み取りが下位2要素を包含する階層をUIと生成処理で一致させた。
- 1案/4案を共通の候補選択・保存フローに揃え、候補生成の停止、処理中の生成排他、動的なコスト・進行表示、DDL hover表示を追加した。
- seedを独立したJavaScript safe integer乱数へ変更し、固定形状にもタッチ差が現れるdisplay rendererを追加した。履歴からキャンバスへseedを復元する。
- 詞書の表示状態をユーザー設定として永続化した。
- 推敲・比較タブの前後作品移動でタブを維持し、モデル比較を3モードへ拡張した。

### v1.73 — システムプロンプト最適化 (2026-07-12)

- Stage 1 / Stage 2 prompt の誤謬を修正した。例の自己矛盾（曖昧数量「数本」/"several" を含む変換例、半径表記の不統一）を正し、JA Saijiki 一覧に欠けていた「うごき」カテゴリと、JA Stage 2 に欠けていた sparse 有効ルール（EN は Build 415 で導入済み）を補完した。
- 「地: ...」/「Ground: ...」文の canvas.ground 到達経路を安定化した。Stage 1 EXAMPLE_POOL に地の保持例を追加し、Stage 2 に「地:→canvas.ground / 面:→直前主図形の surface」のルーティングルールと質感 instruction 複製禁止を明記し、ground 例の入力を Stage 1 実出力形式に正規化した。
- api.py の `_score_with_canvas` が canvas_aspect 指定時に Stage 2 の生成した canvas.ground を破壊していた誤謬を修正した（v1.71 で記録した ground 採用 0/12 の真因）。ターゲット12件で ground 到達 0/12 → 5/12。
- Stage 2 変換ルールの重複バレットを統合し、約70連のルール列に8つの小節見出しを導入した（内容・順序は実質不変）。
- JP/EN 30+30 回帰ベンチ（Build 448 同一プロンプト）: JP は visual_event 89.7→94.9 など全指標で改善、EN は main ベースライン測定により対448低下が v1.70/v1.71 由来の既存ドリフトであることを確定し、本変更は main を全品質指標で改善。fingerprint gates 全 pass。詳細は cli/tune_bench.md「v1.73 Build504/505」。


### v1.74 (2026-07-12)

**NVIDIA NIM Qwen3.5 397B モデル切り替えと relation 重複防止のチューンナップ**

- **既定モデルの Qwen3.5 397B 切り替え**:
  - 第一・第二段階の既定モデルを NVIDIA NIM `qwen/qwen3.5-397b-a17b` に切り替えた。
  - `interpreter.py` および `trainer.py` の `is_qwen3` 判定を修正し、NIM モデルにおいては `/no_think` による思考トレースの強制抑制を解除し、ローカル OVMS provider のみに限定した。これにより Qwen3.5 397B の高度な推論能力を最大限に活かし、レスポンス速度を約30%高速化した。
- **relation の複製抑制（F-1）**:
  - Stage 2 プロンプト (`composer.py` の関係セクションおよび例) をチューニングし、「定型句 1 つにつき relation は最大 1 つ。同じ定型句を複数 instruction に複製しない」ルールと、それを徹底するための否定例（同じ定型句が並んでも 2 番目の instruction には relation を付与しない例）を JA/EN に追加した。
- **面/地地明示 100% 到達の達成（F-3）**:
  - 前バージョン (v1.73) での ground 経路修復と新モデル Qwen3.5 397B の推論能力の向上により、面/地 12 件セットの地明示 6 件すべてで `canvas.ground` へのマッピング到達率 **6/6 (100%)** を達成した。



### v1.74.1 — ground ホットフィックス (2026-07-13)

- 正規化DDLに「地: ...」/ "Ground: ..." がない場合、Stage 2が雰囲気や情景から `canvas.ground` を自発付与しない規則を日英プロンプトへ追加した。
- Qwen3 Nextで「薄墨の地」が背景へ言い換えられないよう、Stage 1の日英プロンプトへ、支持体を表す「〜の地」「〜の紙に」/ "... ground" / "on ... paper" を必ず `地:` / `Ground:` として保持する一般規則を追加した。
- composer後段へdrop-onlyのground literal gateを追加した。明示マーカーがない場合だけgroundを除去し、canvas aspectは保持する。明示マーカーがあるgroundの補完・修復・置換は行わない。drop発生はwarningログで観測できる。
- display SVGのground質感rect自身へ0.02〜0.18のopacityを持たせ、filterのalpha tableを `0 1` に変更した。filter対応ブラウザの合成アルファを保ちながら、filter非対応PNGラスタライザでも不透明な灰色壁にならない。
- rendererの全filter使用箇所を監査し、同じく広域図形の透過をfilterだけへ依存する箇所が他にないことを確認した。
- Build 508。Mac・pentalaともに314 passed / 30 skipped、ruff・web check/build green。Qwen3 Next固定ベンチは面/地12件12/12（地明示6/6、自発ground 0、灰色壁なし）、JP30/EN30各30/30（自発ground 0、品質急落なし、fingerprint全pass、502/timeout/fallback 0）。詳細は `cli/tune_bench.md` の「v1.74.1: ground hotfix」に記録した。


### v1.75 — 敷き詰め（pattern field） (2026-07-13)

- 物理動作語彙として「敷き詰める」/ `tile` をSaijikiの「うごき」に追加した。規則的反復が主題として文字どおり書かれた場合だけ使用し、「たくさん」「無数」から自発的に選ばない。
- JSON Scoreのarrangementに `layout="grid"`、`rows`、`cols`、`jitter` を追加した。gridは `at.region` またはmargin内をセルで覆い、明示rows×colsをcountより優先する。schema上限は2000へ拡張したが、非pattern経路は従来の1〜1000を維持する。
- Rendererはセル位置jitter、要素別variation位相、weight素材固有の揺らぎを重ね、同一Score + seedのbit決定性を保つ。gridはcoerceのfade / cluster / preserve-space / count縮小から除外する。Build 515では英語の literal marker を tile/tiled/tiling に限定し、単なるモチーフ名の grid から自発gridを作らないdrop-only境界を追加した。
- Stage 1 / Stage 2へ日英同等のliteral-only規則と壁紙・四方向・格子の例を追加した。四方向は最大4 instructionの既存重ねで表現し、新primitiveは追加しない。
- Build 515。


### v1.76 — 作品の系譜（記述同一性と派生過程） (2026-07-14)

- 記述の同一性を `dh1:<sha256>` で表す。入力を Unicode NFC、改行を LF、前後空白を除去した本文を正規形とし、バッチ表示用の `#1` 等は `display_label` として分離してhashへ含めない。`dh1` は記述の同一性、既存 `rh2` は作品エディションの同一性であり、履歴IDや系譜ノードIDとは統合しない。
- 履歴とは独立した lineage node / edge を導入した。親子関係はタッチ、構図、解釈、モデル変更、DDL編集、記述編集、再描画、キャンバス変更という実際の操作時にだけ明示記録し、hash一致、時刻、見た目の近さから推測しない。既存履歴はそれぞれ独立したrootとしてbackfillする。
- 保存前の推敲候補からさらに生成・DDL描画・追加推敲へ進むときは、その直接祖先だけを `lineage_only` の中間作品として自動保存する。Canvasには保存前を「未保存の推敲候補」と明示し、自動保存時には通常履歴へ表示されない旨を通知する。中間作品は通常履歴・通常件数・スター一覧には混ぜず、系譜カードに「中間作品・履歴非表示」と表示する。保存に失敗した場合は親なしの新規作品として黙って続行しない。系譜ビューの「通常履歴に保存」から、node/edgeを維持したまま明示的に通常作品へ昇格できる。
- Canvasにfocused lineageビューを追加した。表示中作品の祖先と近傍の子孫を、作品サムネイル、世代列、親子カード間の矢印、派生操作ラベルで表示する。カードを開くと表示作品と次の派生元が同時に切り替わる。各カードをチェックし、複数作品を確認付きでまとめてゴミ箱へ移動できる。通常履歴をゴミ箱へ移しても関係を保ち、完全削除では本文・SVG・hashを消したtombstoneを残して中間作品が存在した事実だけで線を保つ。
- 「新しい起点にする」でactive lineage contextを明示的に切れる。DRAWのたびに無条件で直前作品へ接続することはない。
- 系譜の深さ・枝数・継続回数は評価値や生成制御に使わない。系譜は制作の記憶を辿るための表示であり、最良枝を決めるgovernorではない。
- 履歴管理の作品選択は、作品表示とは独立した小型チェック操作で行い、1回の操作につき1回だけ選択状態を変更する。サムネイルのマウスオーバーによる拡大表示は行わない。
- スターは確認ダイアログを出さず即時に切り替える。作品コメントはスター状態から独立して保持し、系譜カードの詳細から入力・更新する。スター解除だけでは既存コメントを消さない。
- 推敲内のモデル比較で生成した作品は、調整候補と同じ画像右上の丸い `+` で採用し、履歴保存後は `✓` で採用済みを示す。スター操作は採用とは独立して維持する。
- 作品表示と下部履歴の表示中マーカーを同じ履歴IDへ同期する。系譜・履歴管理・再描画から現在ページ外の作品を開いた場合は `anchor_id` でその作品を含む履歴ページへ移動する。比較・推敲のバックグラウンド保存は表示中マーカーを奪わず、未保存候補の表示中は誤った履歴作品を表示中にしない。
- 履歴管理モーダルを開いている間は外部履歴ポーリングによる内容・ページサイズの差し替えを行わない。サムネイルカードの操作領域を同じ高さに揃え、全カードの最大実測高からページ行数を一度だけ決めることで、最終行の欠けと件数が約90件から下部ストリップ件数へ縮む再取得ループを防ぐ。
- Build 525。

**v1.76 クローズ（2026-07-15）**: Build 525をv1.76の受け入れ版として確定する。系譜上の任意作品を次の派生元として選べること、親子関係を世代間の矢印で追跡できること、表示作品と下部履歴が同期すること、履歴管理の選択・一括削除・表示件数が安定することを実機で段階的に確認し、指摘事項をBuild 518〜525で反映した。以後の開発はこのlineage contractと四つの同一性の分離を基盤とし、v1.80へ進む。

### v1.85 — 運用安全性、CLI完全操作、コンテナ構成 (2026-07-15)

- 従来の非コンテナ開発構成を維持したまま、rootのCompose構成から非root FastAPI container、production SvelteKit Node container、永続data volumeを起動できる。Webは同一originのAPI requestだけを内部API serviceへproxyする。
- 全HTTP request bodyに設定可能な上限を設け、loginにuser/IP単位のrate limit、Rendererに同時実行上限を設ける。CORSの追加originは環境変数で明示し、予期しない内部例外の本文はclientへ返さずserver logへ記録する。
- SQLite connectionはforeign keyを常時有効化する。作品、lineage node、lineage edgeは一transactionで保存し、親または保存に失敗した場合は部分的な系譜を残さない。完全削除はtrash内の作品だけを対象とし、系譜nodeはcontent-free tombstoneへ移行する。
- 保存APIはuserごとのIdempotency-Keyを受け入れる。同じkeyの再送は既存作品を返し、history、lineage node、edge、生成回数を重複させない。
- user／group管理のscope条件は更新・削除transaction内でも検査する。group leadは同一groupの一般userだけを管理でき、他userの履歴、系譜、件数は取得できない。外部認証連携は将来実装とし、現行session／role／scope境界を連携後も正本とする。
- 履歴管理の系譜group集計、現在位置、focused lineageの祖先／子孫はDB側でpage／recursive queryを行う。類似作品計算はSVGや不要metadataを全件hydrateせず、score候補だけを読み、選ばれた作品だけを復元する。UIは不要になったgroup requestをabortする。
- inku-cliはhelpを常備し、専用commandに加えて api commandからGET／POST／PUT／PATCH／DELETE、query、JSON file/body、header、binary outputを扱う。pathは設定済みserver内の /api/... と /health に限定し、serverと同じ認証・role権限で全公開APIを操作する。
- AIの自律操作による作品の品質向上プロセス（起点作成、複数モデル比較、推敲変種生成、Vision NIM評価、系譜ツリーの探索・接続保存）をコマンドラインから完全に駆動できる専用コマンド群（`lineage`, `refine`, `inspect`, `review`）を inku-cli に実装。AIがテスト時に参照する専用リファレンス（`cli-reference-for-ai.md`）を同梱し、テスト基準を明確化した。
- 英語UIのtab、button、短いlabelはTitle Caseへ統一する。iPad相当幅ではCanvas上部のModels／Color／Canvas／作成情報を二段化し、左panel幅をviewport比で縮め、情報を切り捨てない。
- JSON Scoreはversion付きstrict schemaを維持し、未知fieldを黙って破棄しない。DB migrationはcolumn／indexの追加を冪等に行い、既存render hash、description hash、lineage identityを破壊的に書き換えない。
- Build 564（新規コマンドおよびAI検証手順の追加をBuild 565として完了）。

### v1.86 — 系譜UI統合、AI連続自律推敲 (2026-07-16)

- 系譜（Lineage）タブ of 作品カードにメニューボタン（`...`）を搭載し、カードから直接個別アクション（AI推敲、手動推敲、削除）を実行できるミニメニュー（コンテキストメニュー）を統合した。
- AI推敲モーダルを実装。ユーザーは方向性プロンプトの記述、進化させる世代数（1〜10）、および変動させる構成要素（解釈、配色、構図、タッチ）を選択して実行できる。フロントエンドが非同期の逐次生成ループ（`paintOne`の連続コール）を駆動し、進行状況、ステップごとの進捗情報、および中間生成物の画像プレビューをリアルタイムにフィードバックする。完了後、ツリーは自動でリロードされて変種系譜が描画される。
- 手動推敲モーダルを実装。親作品の DDL 構成やカラーカタログ情報を初期値として引き継ぎながら、変種種別、カラーカタログ、追加の歳時記（プロンプト）を指定して素早く系譜上の変種を単発生成できる。
- 各カードのメニューから直接、対象作品をゴミ箱へ移動する個別削除機能を統合。
- Build 565。

### v1.86.1 — agy レビュー反映、セキュリティ・パフォーマンス強化 (2026-07-16)

- **認証切替トグルおよびガード**: 環境変数による Google/ローカル認証の設定を DB (`app_settings` テーブル) にて動的かつ永続的に切り替え可能にし、認証設定 API を新設。ローカル認証が無効な場合のログイン試行を `403 Forbidden` で確実に拒否するガード処理を追加した。
- **スキーマ堅牢化**: Pydantic の全スキーマ（`SurfaceSpec`, `CanvasSpec` 等の Pydantic モデル）に `ConfigDict(extra="forbid")` を適用し、予期しないパラメータを持つ未知のフィールドがサイレントに無視されるのを防止した。
- **Svelte 5 警告・再帰ループ対策**: `HistoryManager.svelte` における ResizeObserver 内のステート更新に 200ms デバウンスを導入し、レイアウトスラッシング（無限リフロー）を防止した。また、`ManualRefineModal` における Props 初期値コピー警告を回避する状態バインドに修正した。
- **系譜図の描画パフォーマンス改善**: 矢印描画のために全カードの `getBoundingClientRect()` を実行する同期リフロー処理を排除。`offsetLeft`/`offsetTop` から親を辿るレイアウトピクセルベースの座標算出へリファクタリングし、系譜描画負荷を大幅に削減した。
- **WebKit 座標計算バグ対策**: iPad Safari (WebKit) 等で表示ズレや計算バグを引き起こす非標準 `zoom` プロパティの使用を廃止し、標準的な `transform: scale` に完全移行した。
- **運用管理 CLI コマンドの拡充**: `inku-cli` に `user` (作成/一覧/更新/削除), `group` (管理), `config` (システム設定) の各管理者用サブコマンドを追加。また、CLI コマンド定義からヘルプを自動抽出・整形して `cli/README.md` を更新するドキュメント同期スクリプトを配備した。
- **多言語化とレスポンシブ崩れ対策**: AI自律推敲および手動推敲モーダルの表示文字列をすべて共通 i18n 辞書オブジェクト `t()` による出力に移行。キャンバス上部メタデータ部分の `flex-wrap: wrap` や `text-overflow: ellipsis` 制限により、中間解像度・モバイル幅でのレイアウト破綻を防止した。
- **Build 566**。


### v1.87 — 版画の線と調子、語彙の整理 (2026-07-16)

- **筆致の設計**: 線を、L0 意図経路、L1 手の二次系追従、L2 1/f 傾斜の共通潜在エネルギー、L3 疎な引っかかり・かすれ・修正、L4 道具文法の五層で演奏する。幅・横偏差・濃さは同じ潜在信号に従い、ロットリングは均一性を守るためこの作用を明示的に遮断する。出力は可変幅輪郭へまとめ、線ごとのfilterを増やさない。
- **版画の線**: てざわりにビュラン / `burin` とドライポイント / `drypoint` を追加した。ビュランは端が細く中央が膨らむ硬い彫線、ドライポイントはseedで左右が決まる片側burrを持つ。特定作家の模倣ではなく、道具と手の一般的な文法だけを移植する。
- **調子と地**: `surface.texture` に `hatch`、`crosshatch`、`aquatint` を置き、間隔勾配と2〜4段の離散調子を扱う。`canvas.ground.material="mezzotint"` は暗い目立て地を表す。`instruction.mode="carve"` と `carve_depth=light|half|bright` は暗地から光を掬う減算の手であり、合成順は ground → additive → carve → plate tone とする。
- **刷りの演奏**: プレートトーン、メゾチント粒理、drypoint burr、groundと描画の見当差を既存texture seed規約と `render_seed` から決定的に導出する。rh2 canonical payloadは変更せず、同じScoreとseedは同じ刷りを再現する。
- **入力駆動とdrop-only**: 版画部品は正規化DDLの定型句がある場合だけ到達する。Stage 1.5は注入しない。暗地のないcarveや定型句のない版画fieldは落とすだけで、ground・mode・版画weightを補修しない。
- **語彙追加の正当化**: ビュランとドライポイントは既存素材では観察可能なエッジ差を表せないため追加し、彫るは加算ではない手を得るため追加した。代償は歳時記の暗記負荷と、暗地が必要な条件付き語彙の導入である。
- **洗練の会計**: 縄 / `rope` をコアのてざわり、Score schema、Renderer、prompt、歳時記から削除した。未releaseの段階で、線材と物体比喩の境界が曖昧な一語を互換語として残さず整理した。増えた反復は版画部品の入力時に限られ、一般入力で起きにくくしたことは、Stage 1.5による素材指紋と暗地・彫りの自発注入である。てざわりは差引10語となる。
- **物質性の限界**: SVGが扱うのは版画の凹みやインク盛りの模倣ではなく、線と調子の文法である。
- **歳時記プレビューと実描画の一致（Build 568）**: 可変幅輪郭を旧固定幅線が覆っていた描画順を修正し、ビュランの入り・中膨らみ・抜き、ドライポイントの片側burr、既存筆記具の筆致を主線として保持した。歳時記の10種のプレビューも同じ観察可能な差へ揃えた。
- **てざわりを持つ正規化DDL（Build 569）**: 見える線・弧・輪郭線には原則一つのてざわりを明記する。Stage 1 の日英規則とfew-shotを更新し、動的例には非pen素材例を最低一件含める。Stage 1.5 の追加線・弧にも同じ規則を適用し、塗り面だけの図形には素材を強制しない。構図変換後の二重展開も防止した。
- Build 567–569。

### v1.88 — 奥書（系譜の朗読） (2026-07-17)

- rootから表示作品までの一本の枝を、世代ごとに過去だけを見せる逐次入力で一人称朗読する手動の鏡を追加した。
- 既存の特徴鏡から差分と全世代の不変量を決定的に作り、vision入力は保存SVGをサーバーでPNG化する。署名はモデル名と日付からサーバーが付与する。
- 奥書は本人別の追記専用レコードとして保存し、古い順に表示する。編集APIはなく、削除とIdempotency-Keyによる二重保存防止だけを持つ。
- 系譜タブの明示操作と`inku-cli okugaki`（`--dry-run`対応）を追加した。dh1/rh2および生成・推敲・候補選別には接続しない。
- Build 570。
- **Build 571:** LAN内のHTTP表示など、Web Cryptoの`randomUUID()`を提供しないブラウザでも奥書を追記できるよう、Idempotency-Key生成を`getRandomValues()`と最終フォールバックを持つUUID生成へ変更した。
- **Build 572:** 履歴管理のサムネイル件数を実カードの描画状態から測定せず、固定レイアウト契約から算出するよう変更した。モーダル内カードの`content-visibility`も廃止し、作品の欠落表示、ページ件数の往復、ちらつきを防止した。

### v1.89 — UIの整理 (2026-07-17)

- **モデル選択（Build 573）:** 接続先とモデルを選ぶドロップダウンを廃止し、利用可能なモデル名を接続先ごとに一覧する選択ダイアログへ変更した。`Stage 1/2`タブでは同じモデルを両段へ設定し、`Stage 1`と`Stage 2`タブでは段ごとに別のモデルを設定できる。確定・キャンセルとユーザー別設定保存の契約は維持する。
- **LLM / Vision設定分離（Build 574）:** Stage 1/2のLLM設定からVision既定モデルを分離し、モデル選択ダイアログ、管理者の公開モデル用途、奥書、API、CLIへ反映した。`/api/models`の旧`catalog`とCLIの旧`--model`は互換経路として維持する。
- **モデル評価メタデータ（Build 575）:** 検証済みNVIDIA NIM 29モデルへLLM/Vision用途、5段階のオススメ度、日英評価コメント、実測速度区分・ラベルを投入した。管理者のモデル設定で編集でき、管理者とユーザーのモデル選択ではホバー表示する。既存DBの上書き値と追加モデルは保持する。
- **文脈別モデル選択UI（Build 576）:** バッチでは現在のStage 1/2を表示して共通モデルダイアログを開き、デモの指示文生成と奥書では、それぞれLLM/Visionに限定した接続先別カード選択へ旧ドロップダウン／固定表示を置換した。全カードで評価メタデータをhover表示する。
- **モデル選択文脈と可読性（Build 577）:** 画像入力がないバッチではVisionタブを非表示にし、Stage 1/2だけを選択する。デモには指示文生成用LLMとは別に描画用Stage 1/2の選択ボタンを追加した。評価ツールチップは濃色背景・白文字・明るい補助見出しの高コントラスト表示へ変更した。
- **Vision自律推敲（Build 578）:** 系譜の自律推敲にランダム方式とAI Vision方式を追加した。Vision方式は接続先別カードからモデルを選び、各保存画像への観察・次に試す方向・許可範囲内の変動対象を次世代へ渡す。点数化・順位・合否・自動棄却は行わず、方式・モデル・助言を派生metadataへ記録し、全世代を系譜へ残して最終判断を人間に委ねる。
- **系譜カード操作の可読性（Build 579）:** 選択チェックをカード左上、表示中・中間作品・同じ記述・同じ版の状態ラベルをその右、三点メニューを右上へ配置した。メニュー項目の絵文字を削除し、文字サイズ・行間・余白とメニュー幅を拡大した。
- **作品メニューと履歴の系譜文脈（Build 580）:** 作品メニューから手動推敲を除き、選択作品を対象に推敲タブの描画要素・モデル・言語比較を直接開く項目を追加した。ゴミ箱操作は赤地・白文字の明示ラベルへ変更した。系譜タブ表示中に下部履歴から作品を選んでも系譜表示を維持し、選択nodeを中央へ移す。履歴APIは世代数とnode状態を返し、下部ストリップは描画秒数に代えてこの二つを表示する。
- **作品メニューのクリップ修正（Build 581）:** メニューを開いたカードだけoverflowを解放し、そのカードと所属世代を前面へ移す。拡幅したメニューがカード左端で欠けたり、後続世代のカードの背面へ隠れたりしないようにした。
- **作品メニュー比較のモーダル化（Build 582）:** 作品メニューから開く調整・モデル比較・言語比較は、選択作品を対象にしたモーダルダイアログとして表示する。背景クリック、閉じるボタン、Escapeで閉じると系譜へ戻る。上部の通常推敲タブから開く場合は従来のパネル表示を維持する。
- **奥書リクエスト最適化（Build 583）:** 後世代を先の所見へ漏らさないprefix-only構造と1世代1観察は維持する。成功したモデル応答をモデル・言語・prefix・画像hash別に30分キャッシュし、途中タイムアウト後の再実行で完了済み世代を呼び直さない。Vision画像を単体512px、比較対768×384pxへ縮小して縦横比も修正した。タイムアウトは504と再試行案内を返し、UIはJSON全体ではなくdetailを表示する。
- **奥書モデル保存と系譜編集（Build 584）:** 奥書で選択したVisionモデルを通常Vision設定とは別にユーザー設定へ保存し、再度開いたとき復元する。作品メニューへ「記述を編集」「DDLを編集」を追加し、選択作品の内容をモーダルで編集して描画できる。結果は `description_edit` / `ddl_edit` の子作品として保存し、描画完了後は最新の子をfocus nodeにした系譜へ自動で戻す。


### v1.89.1 — 雲形（2026-07-18）

- **雲形と選択境界（Build 585）:** かたちへ雲形を追加した。Stage 1は明示された雲形または対象自体が無定形な雲・煙・霞・染み・島影・水たまり等にだけ選択し、未知対象のfallbackにはしない。Stage 2はcenter+sizeへ転記するだけで、Stage 1.5とcoerceは雲形を注入しない。
- Renderer v4は、Score・instruction index・performance seedから周期的な1/f基底曲線と弧長上の第二信号を決定的に合成する。局所半径・曲率のクランプと正の単値動径で自己交差を構造防止し、49点の閉Bezier予算へ収める。同じseedは完全再現し、別演奏と配置展開された各要素は別輪郭になる。
- 既存のゆらぎ、わりあい、てざわり、surface、carve、あいだ、ばしょ、うごきをそのまま合成する。確定輪郭のbboxと輪郭点をrelation解決に使い、display/editable/compatでsurfaceを演奏する。Score・DB・rh2入力へ輪郭座標を保存しない。
- CLIの洗練台帳へ雲形のinstruction数、展開数、サンプル率、文脈を鏡として追加した。生成のgovernor、floor、品質ゲートには接続しない。
- **洗練の会計:** この版で減らしたものはない。新しい専用修飾語や輪郭テンプレートは追加せず、既存語彙の合成だけに限定した。この版が起きにくくしたことは、未知・曖昧な対象が雲形へ吸収されること、輪郭が楽譜へ固定され一回性を失うこと、自己交差防止が美的な自動調整へ膨張することである。
- **作者受入:** 日英各8件と同一楽譜の複数演奏を目視し、「雲形というイメージからは破綻の無い描画」として受け入れた。より飛躍した形は、この版の幾何安全性や選択境界を変えず、別途チューニングする。


### v1.90.0 — あいだ「触れる」（2026-07-18）

- **正式な接触関係（Build 586）:** あいだの第5語へ `touching` を追加し、`contact: both_ends` をline / arcの両端一致として正規Scoreスキーマ、Stage 1、Stage 2、歳時記へ日英同時に実装した。接触の固定句が明示された時だけ選び、自発付与しない。
- Rendererは直前要素の演奏後端点を使い、二端点と符号付き矢高から `r=c²/(8|b|)+|b|/2` の劣弧を再構成する。直前弧の反対側へ膨らませ、劣弧の符号・windingはSVG描画と共有実装に統一した。variationと筆致は端点を固定する。
- 閉形と端点を持たない直前要素は警告記録付きdrop-only、退化幾何は演奏時のdrop-onlyとし、座標補修・relation governor・API境界ハックは導入しない。`続きから (continuing)` は第二段候補に留めた。
- 出力SVGから閉性、尖り30°以上、劣弧180°未満、矢高、同seed再現、Replay差を200 seedで検査する回帰を追加した。素描B系00/01/02/04はlocal-onlyの `cli/bench/leaf/` に置き、一般30入力ではtouching定型句の発火を0件とした。
- **形式の会計:** 閉じた有機的輪郭を演奏揺らぎと両立させる代わりに、緩い距離関係だけだった「あいだ」へ初めて正確な端点拘束を加えた。Score version、migration、Render Engine metadata、rh2正規payloadは変更しない。
- **変換後座標の統一（Build 587）:** touching、along、not_touching、cutting、betweenが参照する端点・輪郭を、SVGのrotation等を合成したキャンバス座標へ統一した。SVG検査は祖先groupのtransformを再帰合成し、通常版00/01/02/04と黒rotringのjudge版を分離した。Score schemaとrh2算出仕様は変更していない。
- **関係付与の重複除去（Build 588）:** Stage 1.5で同一のtouching関係が重複して付与される経路を整理し、既存の接触指定を一度だけ保持するようにした。
- **宣言的プラグイン文書（Build 589）:** front matter manifest、日英語エントリ、日英展開テンプレートからなる `.inku-plugin.md` のparser／validator／決定的展開層を追加した。再帰、48 instruction超過、反復の固定座標スタンプ、namespace衝突、URL・ファイル参照は文書全体を理由付きで拒否する。
- 展開順をStage 1→プラグイン展開→コアDDL→Stage 1.5→Stage 2とし、名前空間明示と指示対象として明示された`fires_on`だけを発火させる。Stage 1には語彙リストだけを注入し、比喩・未知対象、Stage 1.5、coerceからの注入を禁止した。
- 発火provenanceはAPI応答と履歴の派生メタデータへ記録する一方、Score・DB正本・rh2へプラグイン本文や依存を持ち込まない。追加・削除・再読込、拒否理由表示、歳時記note、`inku-cli plugin list / validate / reload`、削除後Replay不変の回帰を追加した。
- **洗練の会計:** 新primitive、新Scoreフィールド、新coerce、作品governor、コード実行を追加していない。増えたのはコア語彙へのwriting-down境界と監査provenanceであり、起きにくくしたのはプラグイン再帰、スタンプ化、比喩への過剰発火、保存作品のプラグイン依存である。葉プラグイン本体はこの版に含めない。
- **構造展開済みDDLの保護（Build 590）:** プラグイン展開がmember別の数値regionを確定した後、Stage 1.5が楕円等の別レシピを追加し、Stage 2もDDLにない補助弧を生成し得た経路を修正した。数値regionを含むコアDDLは構図判断済みとして正規化だけを通し、Scoreのinstruction数も明示region数を超えない。これはplugin namespaceを後段へ注入する特例ではなく、一般の明示regionにも適用する境界である。最小双弧fixtureはMistralでは二本に抑制される。Qwenでは二つのinstruction内のarrangementにより二本を超える可視弧が残る場合があり、instruction数境界と可視要素数のモデル差として受け入れた。
- **プラグイン形式v2の受け入れ（Build 591）:** 葉プラグイン（Nature.leaves v0.3.0）のStage 3検証と reference（Build 590）の突合で判明した、実装側に帰属する不適合を修正した。展開層に次の受け入れ構文・検査を追加した。承認済み `spec-draft-plugin-format-v2` を正本へ反映した便でもある。
  - `member 名前: 定義` のプラグイン内ローカル複合形（参照行の各memberへインライン展開、未定義参照はロード拒否）。`注:／note:` コメント行（展開・閉包検査の対象外、傍注として保存）。
  - `下端の帯` 領域の追加と、「左上から右下への斜めの帯」の展開層計算（下降対角線に沿うmember小region列）。未知領域キーはロード拒否とし、v0.2.0で「下端の帯」が無言で中央帯化した silent fallback を廃止した（runtime遭遇時は既定帯＋warning記録）。
  - en反復単位を複数語（leaf forms／forms／blades／cloudforms／spots／arcs）へ拡張し、単数形を単位保存（一枚／一本／一個、one leaf form 等）とした。従来 en は範囲行が単位不一致で member展開されず受け入れ側でも未行使だった経路を回帰テストで固定した。
  - `anchor … を N〜M箇所 置く` の入れ子反復（箇所反復×各anchorからのmember反復、深さ2まで。各箇所は個別の帯region）。
  - `fires_on` 照合を同一位置の最長一致のみ採用に変更し、「枯草」入力での「草」による下草の誤発火を構造的に排除した。異なる位置の複数語（季語の重ね）は従来どおり複数発火する。
- 閉包検査のマーカー表へ、歳時記の修飾カテゴリ（素材・色・ゆらぎ・かたむき・わりあい・ばしょ）と欠落動詞「描く」「埋める」を暫定追加した。語は reference §1（Stage 1プロンプトのSaijikiブロック）を正とし、v1.92の歳時記構造化モジュールで saijikiテーブル導出へ置換する暫定である。
- **洗練の会計:** 新primitive・新Scoreフィールド・新coerce・作品governorを追加していない。増えたのは展開層の受け入れ構文と実行前検査であり、Score・rh2・既存fixtureは不変である。日英の配置等価（枯葉のja/en不等価の再発防止）とen反復展開の実行使を回帰テストで固定した。Nature.leaves v0.3.0が `plugin validate` を通過する。


### v1.92.0 — 歳時記の構造化（2026-07-19）

- **語彙の単一情報源化（Build 592）:** server の `saijiki.py` に歳時記テーブル（9カテゴリ+あいだ、prompt/display/marker フラグ、marker 順序、relation 固定句）を新設し、Stage 1 プロンプトの語彙ブロックとてざわり列挙、プラグイン閉包マーカー表、Stage 2 の relation 固定句テーブル、reference §1 をすべてテーブル導出へ切り替えた。構造化前プロンプト全文を golden fixture として凍結し、許可差分（削剪語のみ）以外の組み立て差異をテスト失敗として検出する。
- **語彙の削剪:** 作者裁定により「描く」（うごき）と「髪／hair」（てざわり）を歳時記語彙・Stage 1 プロンプト・閉包マーカー・表示から削除した。Score の Weight enum には hair を Replay 互換のため残す。web 表示から「彫る」を削除し（server 側に存在しない語）、Nature.風/うねり/無風 の静的表示は宣言的プラグイン移行まで凍結した。
- **web 配信の一本化:** `GET /api/saijiki`（コアカテゴリ+ロード済み宣言的プラグイン語）を新設し、web の歳時記・語彙色分けを同期ストア（バンドル内蔵スナップショット初期値 + hydrate）で供給する。スナップショットは codegen（`server/scripts/gen_saijiki_ts.py` → `saijiki.generated.ts`）で生成し、テーブルとの一致を pytest で強制する。
- 検証: 全 pytest / ruff / web check・build、pentala 実地確認、reference dump 前後差分 = 削剪語のみ、nature-leaves v0.3.0 validate 通過、実弾ベンチ（葉ミニ10日英 Replay×5 + gallery JP20/EN20）で葉発火 19/20 が v1.91 と一致（相違 1 件は Stage 1 LLM 変動と帰属し受け入れ）。
- **SPEC 再基準化:** SPEC.ja.md の語彙・定数記載を「saijiki テーブル / reference を正とする参照方式」へ書き換え、内部矛盾（Canvas: Letter、旧語彙表、分離修飾行の例、モデル固定表、プラグイン展開層の所在、参照切れ、雲形節の番号なし等）を解消した。雲形の設計は §14.9 として番号付与。思想散文は改稿していない。
- **洗練の会計:** この版で減らしたもの — 語彙の定義箇所を 4（Stage 1 プロンプト散文・閉包マーカー表・web saijiki.ts・composer 固定句）から 1（saijiki テーブル）へ、語彙から 描く・髪 の 2 語を削った。起きにくくしたのは、語彙表同士の乖離（web↔server の分裂、SPEC の四重表）、プロンプト組み立ての無言の脱落、削剪の非可逆化（prompt フラグで旧プロンプトを再生成でき、新旧 A/B の帰属判定が一手で可能）である。

### v1.93 — RAW trace オプション（Build 593）

- 生成パイプライン各層の RAW 中間生成物を 1 回の生成で持ち帰る観測オプションを追加した。`/api/paint` と `/api/compose` のリクエストに `include_trace`（既定 false・後方互換）を加え、指定時のみ応答トップレベルへ `trace` を返す。収録: `stage1_raw`／`stage1_thinking`／`stage1_ddl`（プラグイン展開前）、`plugin_expanded_ddl`、`stage15_ddl`（= Stage 2 入力）、`stage2_raw_attempts`（retry・fallback を含む全試行の生テキストと parse 可否）、`score_pre_coerce`、既存の coerce／plugin 集約値。
- **鏡であって governor ではない。** 収集は interpreter／composer へ任意の `trace_sink` を通す観測のみで、interpret／expand／compose／coerce／render の判定・分岐・回数を一切変えない。`include_trace` 未指定時の応答は現行とフィールド単位で完全同一（新規キー `trace` も現れない）。trace は応答のみで DB（履歴・lineage）へ保存しない。同一入力・同一 seed では `include_trace` の有無によらず Score と render_hash が不変。収集失敗は生成を落とさず該当キー null ＋ warning とする。
- `inku-cli paint --trace` を追加し、応答の `trace` を `<prefix>-trace.json` として出力ディレクトリへ保存する（`--full-json` と独立、旧サーバで trace 不在なら警告のみ）。
- テスト: 上記不変条件（応答同一・非永続・Score/render_hash 不変・生成分岐なし・認証境界・試行構造）を LLM モックで回帰。SPEC 本文は変更しない（利き目監査ハーネスの入口。plan-intent-audit ステップ 4.5）。

### v1.94 — 記述・キャンバス・履歴の UI 整理（Build 594–599）

web UI のみの改修。描画機構（Score・render・パイプライン）には触れず、server 変更はない。

- **下部履歴ストリップの整理（Build 594）:** サムネイル上の状態バッジ（通常作品／中間作品／削除済み等）を削除し、ホバー tooltip の状態行は残した。英語表示の「Generation」を「Gen.」へ短縮した（日本語「世代」は据え置き）。
- **現在選択の移設とキャンバス下バーのハッシュ化（Build 595）:** 記述タブの指示・ボタンの下、入力欄の上に「現在選択中」（モデル・色カタログ・キャンバス）を読み取り専用で表示した。キャンバス下ステータスバーからモデル／色カタログ／キャンバス表示を除き、代わりに render hash（下四桁・大文字、既存 `render_hash_short`）ボタンを置き、クリックで full hash をコピーする。記述・バッチ・デモを含む左パネルを、パネルとキャンバスの間の細いレールで左へ折りたためるようにした。キャンバス作品のマウスホイールによるズームイン／アウトを追加した（canvas タブ・作品表示時のみ、既存 zoom clamp 経由、ページスクロールは抑止）。
- **モデル表示と Vision 整理（Build 596）:** 記述の「現在選択中」で Stage 1／Stage 2 が異なる場合に「解釈／描画」のラベル付きで両方を表示する。AI 自律推敲で選ぶ Vision モデルを `vision_model` としてユーザー設定へ永続化した（初回選択が以後の既定になる。奥書は従来どおり `okugaki_model` に別途永続で、用途別に独立）。記述から開くモデル選択ダイアログから Vision タブを外した（Vision は生成では使わず、所見・推敲観察のみに使うため）。ハッシュボタンを生成情報ボタンの直左へ移し、最新ボタンをキャンバス左のナビへ移した。下部履歴サムネイルに使用モデル名を表示した。
- **表示の精緻化（Build 597）:** 記述のモデルは省略せずフル名称で表示する。下部履歴サムネイルのモデルは Stage 1 の短縮名のみとし、tooltip は Stage 1／Stage 2 をフル名称で分けて表示する。推敲・奥書のモデル選択で候補の説明 tooltip が見切れる問題に対処した。「新しい起点にする」ボタンを指示タブ「新規作成」と同じ意匠へ、ハッシュボタンを他のステータスバーボタンと同じ意匠へ揃えた（ハッシュ値の色は維持）。系譜の作品カードメニューから「ゴミ箱へ移動」を除いた（ヘッダの一括ゴミ箱は残置）。指示タブのボタン並びをモデル選択→色カタログの順に入れ替えた。
- **モデル選択 tooltip の配置修正（Build 598）:** 候補カードの説明 tooltip を `position: fixed` に変え、スクロール容器のクリップから逃がした。カードのビューポート位置を測り、下に入り切らず上の余白が大きいときだけ上へ寄せ、上下端・左右端は余白内へ収める。候補が少ない低いダイアログでも先頭行・最終行のいずれも全文表示される。
- **ハッシュボタンの高さ調整（Build 599）:** 内部 monospace の行高でハッシュボタンだけ低くなっていたのを、兄弟ボタン（生成情報・SVG・PNG）と同じ表示・行高へ揃えた。

### v1.94 — 双弧の演奏修正（Build 600、2026-07-19）

- **region が relation を無言で無効化していた不具合を修正:** region（`at`）と relation を両方持つ instruction は、region 配置時に relation が無記録で破棄され、touching 解決に到達していなかった。region 配置を先に・relation 解決を後に実行するよう改め、プラグイン member 由来の双弧（葉形）が設計どおり——直前要素の演奏後端点で固定された対向劣弧——として演奏されるようにした（利き目監査 F-1）。region は連鎖の起点・情報として扱う。
- **演奏時 drop の警告記録:** 演奏時にのみ解決不能になる relation（touching 不適な primitive、退化幾何、grid 配置、端点のない直前要素）は §14.4 に従い Renderer が警告記録付きで drop する。座標補修・relation governor は導入していない。
- 検証: 新規回帰 6 件（region+touching 下の vesica 形成、決定性、region 内配置、警告付き drop）、全 pytest 511 passed。保存済み葉ベンチ Score を同一 seed で再演奏すると、端点共有・劣弧掃引・端点固定の touching 弧が三本連なる。rh2 契約と Score schema は不変（新ビルドでの Replay は設計どおり新エディション）。
- **展開層の対分離**: relation literal を含む member 定義（「弧を置き、前の弧に両端で触れる」）を、対の各要素が**同一 region を持つ独立文**へ分割する。touching の連鎖化（全弧が同一弦へ積層し 1 枚に潰れる／円環に巻く）を構造的に排除し、明示 region 数上限（Build 590）とも自然に整合する（2 弧とも region を持つため上限は 2N）。parse 時の instruction 予算も対のセグメント数で計上する。
- **en 反復の形容詞許容**: 「5-7 tall blades」のように数と単位の間の形容詞 1 語を受理する（"to" は除外）。単数形は形容詞を保存する（one tall blade）。
- **fires_on 発火経路の drop 過敏の緩和**: Stage 1 が混入させた stray な名前空間参照は、展開全体ではなく**当該文だけを警告付きで除去**する（除去後に何も残らない場合のみ従来どおりコア近似へフォールバック）。菖蒲などで再現していた「正当発火の全落ち」を解消する。
- **対 member の決定的転写（A）**: 展開層が生成する対 member 文（配置弧 + touching 弧）は、LLM を通さず展開層が Score instruction として直接確定する。幾何は member region・回転・seed から導出し、掃引角は member ごとに決定的に揺らす（スタンプ化回避）。「膨らみは細く」は細い掃引へ写像。直後の様式文（「ロットリングで、赤で。」等、行頭の様式のみ）は消費して weight／color を適用し、運動句などの残余はテキストに残す。転写された instruction は coerce を迂回して合流し、Score・rh2 契約は不変。最弱モデル（gemma）でも全語で正しい素材・色の葉形が形成されることを実弾で確認した。
- **搬送契約の鏡（B・検査のみ）**: DDL に字面で明示された語彙（線種・てざわり・半円 180°・対応が一意なゆらぎ 3 語）が最終 Score に載ったかを決定的に検査し、`carriage_warnings` として応答にのみ露出する。再試行・ゲート・DB 保存はしない。
- **対比例の追加（C）**: composer プロンプトへ日英各 4 例（破線・ビュラン・半円=180°・大きく滲む）を追加し、全モデルの初回搬送率を底上げする。


### v1.95 — UI 第 2 期: 推敲導線と DDL エディタの集約（Build 601–604、2026-07-19）

- 作品メニューから開く 3 つの比較ダイアログ（描画要素／モデル／言語）を、開いた目的の 1 タブのみ表示に変更し、出力タブバーから「推敲」タブを削除した（出力タブは 作品／系譜 の 2 つ。到達性は作品メニュー経由で維持し、未保存プレビューを親にする導線はコンセプト外として廃止）。
- 記述タブを指示主体へ再構成した。正規化DDL 欄は閲覧専用（ハイライト＋歳時記トグル）とし、DDL の作成・編集は共有エディタダイアログ（行番号・ハイライト・歳時記挿入）へ集約。「DDLから新規作成」は空白から始まり独立作品（新規系譜ルート、`display_label='DDL'` バッジ＋先頭行表示）として保存する。DDL 由来作品では指示文前提の操作（記述を編集・読み取りを変える・モデル比較・言語比較）を非表示にした。auto-repair トグルは設定モーダルへ移設。
- 出力タブ「描画」を「作品」へ改称し、キャンバス上部バーに世代（第N世代／独立作品）を表示。AI 自律推敲の推敲要素を具体名＋速度・コスト tooltip 化し、世代数を常時表示のステッパーへ。系譜の子展開時のスクロール位置保持、全体図の「閉じる」改称、比較ダイアログを閉じた際の系譜自動更新を追加。web のみの変更で server・Score・rh2 は不変。APP_VERSION は v1.95.0。

### v1.96 — プラグイン管理・添景水準・UI 第 3 期（Build 605–606、2026-07-19）

- **ユーザープラグイン管理 API（Build 605）:** `/api/plugins` 系に本文取得・作成（ファイルから読み込み）・上書き・削除・有効/無効の 5 エンドポイントを追加した（すべて admin、検証失敗は 422 reasons、filename 衝突は 409）。item へ `id`（= ファイル名）と `enabled` を追加し、status に `disabled` を加えた。無効化は「文書は残すが展開・語彙注入・衝突予約の対象にしない」であり、プラグインディレクトリの `.plugin-state.json` へ永続化して reload の署名監視対象に含める。クロスファイル衝突がロード順によって既存側を rejected にし得る書き込みは丸ごと巻き戻して 422 とする。設定モーダルのユーザープラグイン節（スイッチ・削除・ファイル読込・コード表示/編集）はこれで実機能になった。
- **添景水準 tenkei（Build 605）:** 生成時にユーザーが添景の度合いを選べる `tenkei`（`none`／`sparse`／`auto`、既定 auto = 現行挙動）を `/api/paint`・`/api/compose`・`/api/interpret` と `inku-cli --tenkei` へ追加した。水準は生成前に三層へ決定的に写像する: Stage 1 は水準別の規範文（none ではプラグイン語だけの入力が Stage 1 を経ない純明示バイパス）、Stage 1.5 は候補プールの縮約（none = 追加なし・焦点書き換えのみ、sparse = 1 候補）、coerce は自律的添景挿入分岐の挿入予算（none = 0、sparse = 1。プラグイン転写が主題を搬送済みの場合は complex_motif も対象）。修復系・変異系は水準に依らず動き、事後の間引き governor は導入していない。tenkei は応答・履歴メタデータへ記録するが rh2 の材料に含めない。実弾ベンチ（gemma）で `Nature.紅葉` の添景 count は auto 127 → sparse 87 → none 1。
- **対転写ガードの回復（Build 605、§4.6 契約）:** Build 600 の対 member 決定的転写では展開後 DDL に数値 region 文が残らず、Stage 1.5 の追加抑止（Build 590）が素通しになっていた。プラグイン展開が instruction を返した場合も追加を抑止するよう改め、水準に依らず適用する（倍音列弧・葉片楕円などの定型文添景が消える）。
- **系譜の世代付与（Build 605）:** `get_lineage`／`get_lineage_branch` の `node.history` へ計算値 `lineage_generation` を付与し、系譜から開いた作品の世代表示が「独立作品」になる不具合を解消した（履歴リストと同一の単一算出ロジック）。
- **UI 第 3 期（Build 606）:** マスコットを 5×5 ピクセルの inku キューブへ差し替え、単一生成のプログレスバーを廃止して「キューブ＋動的ステージ名＋経過＋停止」の 1 行ステータスへ統合した。同じステータス要素を DDL エディタ・記述編集・AI 自律推敲・モデル比較・言語比較の各ダイアログへ展開し、すべてに機能する中止（AbortSignal 配線）を付けた。言語比較は Stage 1×Stage 2 の 4 組み合わせカードの直接選択へ再設計した。モデル説明メタデータを `modelMeta.ts`＋`ModelMetaCard` へ単一ソース化し、比較カードにも記述タブと同じ意匠の説明カードを表示する。キウイ・蟹は削除せず保存・非描画（作者指示の一時非表示）。
- **洗練の会計:** 新 primitive・新 Score フィールドは追加していない。tenkei は生成前の決定的な切替（vary と同型のユーザー明示操作）であり、coerce へ加えたのは挿入の抑制のみで挿入は増えていない。増えたのはプラグイン文書の管理境界（validate 通過が保存条件）であり、起きにくくしたのは添景による主題の圧倒、対転写後の定型文添景（契約の素通し）、系譜世代の表示乖離である。

### v1.97 — 添景水準の作品保存・系統継承と UI 結線（Build 607–608、2026-07-19）

- **作品ごとの保存と親継承（Build 607）:** v1.96 の tenkei は生成時オプションに留まり、推敲が既定 auto で走ると「なし」で始めた系統に一手で添景が戻る欠陥が UI 結線時に発見された（10 世代級の試行錯誤という使用像では初期選択が失われる）。作者裁定により作品ごとの保存へ改めた。history に `tenkei` 列（追加型 migration、NULL = 保存開始前の作品）を加え、解決順を**明示リクエスト値 > 派生元作品からの継承 > auto** としてサーバー側で解決する（AI 自律推敲・CLI を含む全クライアントで系統の水準が無指定のまま維持される）。`/api/paint` は `lineage_parent_node_id` から継承し、`/api/compose` に継承専用の `lineage_parent_node_id` を新設、`POST /api/history` は保存時に解決して記録する（タッチ変化など Renderer 専用派生でも系統の水準が途切れない）。リクエストの `tenkei` は省略可能になり（省略 = 継承）、応答・履歴・lineage の `node.history` は解決後の値を返す。rh2 の材料には含めない。
- **UI 結線（Build 608）:** 記述タブの生成コントロール行に添景セレクタ（なし／控えめ／おまかせ、localStorage 永続、新規ルート生成で明示送信）を追加した。推敲 6 ダイアログ（描画要素で比較・モデルで比較・言語で比較・記述を編集・DDL を編集・AI 自律推敲）には**親作品の水準を既定選択にしたコンパクト 3 択（継承表示付き）**を置き、未変更なら tenkei を送らずサーバー継承・変更したら明示送信で系統の分岐点になる。タッチ変化・色の再描画（Renderer 完結）にはセレクタを出さない。生成情報ダイアログと履歴 tooltip に「添景」行を表示する（水準が保存された作品のみ）。
- **洗練の会計:** 水準の意味論は v1.96 から不変（三層写像・governor なし）。増えたのは「作品が自らの生成条件を記憶する」1 列と継承の解決点 1 箇所であり、起きにくくしたのは推敲による水準の無言消失と、表示（生成情報・tooltip）と実動作の乖離である。

### v1.98 — 記述パネル再編・描画ストリーミング・モデルカタログ v2（Build 609、2026-07-20）

- **描画段階のストリーミング:** 単発描画を新設の `POST /api/paint/stream`（NDJSON）へ移行した。解釈完了時に `stage1` イベント（正規化DDL・使用モデル・トークン数・所要時間・フォールバック有無）を送出し、Stage 2 と描画の継続中に解釈を先に表示する。最後の `done` イベントは従来の `PaintResponse` を返し、既存 `/api/paint` は同一ジェネレータを消費するラッパとして応答形状不変（CLI・Android 無改修）。実行中表示は共通の `RunStatus` コンポーネントへ標準化し、停止文言を「停止」へ統一した。あわせて、`RequestSizeLimitMiddleware` がバッファ枯渇後に `http.disconnect` を配送せず StreamingResponse が永久ブロックする既存不具合を修正した（ストリーミング導入で顕在化）。
- **入力側 DDL と展開後 DDL の分離・焦点の明示指定:** history に `expanded_ddl`・`focus`・`interpret_fallback` の 3 列を追加し、`ddl` の意味を「展開後」から「入力側（ユーザー原文または Stage 1 出力）」へ再定義した（新列追加時に一度きりのバックフィルで既存作品の `ddl` を `expanded_ddl` へ移送。入力側は元から保存されておらず復元不能のため、旧作品はラベルのみ「展開後」となる）。`/api/paint`・`/api/compose` に `focus` を追加し、未指定なら従来どおり DDL テキストから決定的選択、未知値は未指定扱いとする。応答に `focus` と `source_ddl` を追加した。
- **空解釈の失敗化とフォールバック印:** 空の Stage 1 出力を失敗として扱い、何もない状態から描かない。フォールバック経路で描かれた作品は `interpret_fallback`（理由）を記録し、UI に印を付ける。単発描画の履歴保存はクライアント送信からサーバー保存へ変更した。
- **モデルカタログ v2（用途別推奨度・EOL・実測再構築）:** NVIDIA NIM 86 モデルの実測 2 回（LLM 各 3 実行 + Vision 1 実行、時間帯を変えて再現）に基づき検証済みカタログを再構築した（`MODEL_CONFIG_VERSION` 2.0.0、29 → 43 エントリ）。推奨度を `recommendation_llm` / `recommendation_vision` の用途別へ分割（旧単一キーは読み取り互換のみ）。提供終了 2 モデルは EOL 印つきで選択不可として末尾に残置し、カタログから消さない（過去作品のモデル参照を保全。現行カタログから消えるモデル・履歴参照で未収載のモデルはゼロ）。モデル一覧の表示順は EOL 末尾 → その場の用途の推奨度降順 → ラベル昇順へ統一（`sortModels()`、描画 4 箇所を単一経路化）。502 応答の `detail` を種別オブジェクト（`model_gone` / `provider_auth` / `provider_rate_limit` / `provider_error`、段とプロバイダ原文つき）へ拡張し、UI が種別ごとに説明表示する（旧文字列パスは互換維持）。
- **歳時記の閲覧専用化と UI 整理:** 歳時記トグルをキャンバス下部ツールバーへ移し、ドロワーを閲覧専用（チップクリック = プレビュー）へ変更した。語の挿入は DDL エディタダイアログ内のインライン歳時記に集約し、ロード済みプラグインの名前空間付き語も同所に表示する。未使用の旧 DDL 編集パネル 2 コンポーネント（734 行）を削除。世代ラベルへ系譜名を前置し体裁をモデル欄へ統一、記述タブ残りのコントロールへツールチップを追加、テーマ対応の `--danger` 変数を定義し、DDL トークン配色 12 クラスをグローバル定義へ統合してダークテーマの可読性を修正した。
- **検証:** Mac / pentala とも pytest 548 passed・ruff・`npm run check` 0 errors・build 成功。pentala の DB 移行は事前バックアップのうえ実施し件数照合済（1565 件）。


### v1.99 — 描画コア: 弧・閉図形への揺らぎ演奏（F-4、Build 610、2026-07-20）

- **揺らぎの演奏対象を拡張:** これまで line のみだった `variation` の演奏を、弧・閉図形（円・楕円・三角・四角・多角形）へ拡張した。ゲートは line と対称の `quality ∈ {perlin, wave, white}` かつ `dimensions ∩ {position_x, position_y, radius} ≠ ∅`（radius は図形の自然軸として追加）。円・楕円は 80 分割輪郭 + 周期ノイズ（perlin は格子を mod freq で wrap、wave は整数周波数で自動閉合）で継ぎ目が連続し、四角・三角・多角形は辺ごとに line 揺らぎを適用して角を固定、弧は分割 + オフセットで両端点を完全固定し touching の接点契約を維持する。pink（滲み）と quality=none の経路は不変。touching 再構成後の弧も同一分岐を通る。
- **利き目監査の死にフィールド解消:** 監査 A/B 同一条件の再実行で、旧 SAME 16 ケース中 position/radius 軸の 11 ケースが DIFF へ転化（rotation/thickness/angle/length 軸の 5 ケースはゲート対象外として SAME のまま、SPEC §17.A の別項目）。composer は既に square・ellipse へ position dims 付き variation を出力しており、本ゲートは実弾で発火する。
- **render engine version 5:** 同一 Score + 同一 seed の演奏結果が変わるため版数を 4 → 5 へ更新（調停側判断）。弧・閉図形に variation を載せた過去作品は再演奏で見た目が変わるが、保存済み SVG・Score・rh2 は不変。
- **検証:** pytest 578 passed / 39 skipped（新規 42 テスト: 6 図形 × 3 quality の演奏確認、dims 別演奏、ゲート閉時のバイト一致、決定性、pink の blur 維持、弧の端点固定、多角形の角固定、周期サンプラーの継ぎ目連続性）。既存回帰ゼロ、ruff 通過。Score schema・coerce・rh2 の変更なし。マージ時、ローカル専用 leaf-bench の touching 検査 3 件が「演奏された弧は polyline 要素になる」表現変化で失敗することが判明（render worktree では fixture 不在で skip されていた）。追補修正で SVG 抽出系を polyline 対応へ拡張（端点拘束付き円当てはめ・掃引角からの劣弧再導出・ゲート発火/非発火の形状一致 assert）。検査の緩和ゼロ、最終値 602 passed / 30 skipped。
- **残作業:** 作者の実演奏目視確認（「震える円」「ゆっくり揺れる四角」「震える弧」、葉の「定規の円弧」問題の改善度）、材質輪郭（Phase 2）の要否判断、必要なら amplitude/周波数の調整（現行は line と共用）。


### v2.0 — Stage 1.5「変奏」・focus 外部入力の撤去（Build 611、2026-07-20）

- **変奏（決定的な展開層の揺すり）:** `expand_intermediate_ddl()` に `variation_amplitude`（小/中/大）と `variation_seed` を追加した。`(強度, seed)` から変奏プランを 1 回だけ決定的に組み（`_seed()` ハッシュのみ・乱数源なし）、7 軸——型の差し替え・採用本数（Tier 1）／タッチ材質・焦点・主色対比色（Tier 2）／構図族・型の系統（Tier 3）——を重み付き段階解放で振る。小 = Tier 1 から 1 軸、中 = Tier 1∪2 から 1〜2 軸、大 = 全 Tier から 2〜4 軸。小では構図族・焦点は動かない。両引数が揃わなければ現行挙動とバイト一致（既存作品の再現性維持）。
- **可視性保証（契約 §3.2 を超える追加 2 段）:** 値をずらしても出力が変わらない場合（採用文が `{touch}` を含まない等）があるため、①軸単独適用の実走で差分を確認しオフセットを隣へ送る（最大 8 回、不動なら同強度の別軸へ置換）、②組み合わせの打ち消し検出（相殺時は軸を減らす）を実装した。large 1 回あたり約 2ms。副作用として、動かせる軸が足りない記述では軸数が範囲を下回ることがある（可視性優先）。moved_axes は「実際に出力が変わった軸」だけを公式語彙の from → to で報告し、候補カードにチップ表示する。型の名前は候補 34 件（ja/en 各）へ手で表示名を付与した。
- **tenkei 直交:** `none` では対象軸は焦点のみ、`sparse` では合計 1 本を超えないよう再クランプ。採用本数の ±1 は cap 適用後の値に振り、cap と実プール長を越えない。
- **API・候補生成:** `PaintRequest` / `ComposeRequest` に `variation_amplitude` / `variation_seed`、応答に `variation_moved_axes` を追加。seed 採番は新設の `POST /api/variation/seeds` に置き、4 案の生成は既存候補グリッド機構（並列 fetch・進捗・中断）を使う。history に `variation_amplitude` / `variation_seed` の 2 列を追加（moved_axes は決定的に再計算可能なため列を設けない）。`LINEAGE_DERIVATION_KINDS` に `hensou` を追加。
- **focus 外部入力の撤去:** `PaintRequest.focus` / `ComposeRequest.focus` / `_validated_focus` と UI の推敲要素「焦点を変える」一式を撤去し、推敲要素は 4 種（タッチ・配置・読み取り・色）に戻った。展開層の focus 機構・未指定時のハッシュ選択・`history.focus` 列・`HistoryPostBody.focus` は残置。展開層が決めた焦点を `resolved_focus` として render_metadata へ結線したため、撤去後も `history.focus` は NULL にならない（変奏なしの通常描画では既定ハッシュ選択が記録される）。
- **UI:** 調整ダイアログ内に推敲 4 種と分離した「変奏」セクション（強度 3 択 + 変奏を描く）。カードには動いた軸を「型の差し替え 蕾」形式のチップで表示。表示語は「変奏」で統一し「揺らぎ」を使わない。
- **検証:** pytest 636 passed / 30 skipped（+34: `test_variation.py` 30 件 + `test_api.py` 5 件 − focus テスト 1 件）。契約 §4 の 7 項目（再現性・無効時バイト一致・段階解放 seed 0〜199 掃引・可視性・tenkei 直交・レポート整合・focus 撤去回帰）全対応。ruff・`npm run check` 0 errors・build 通過。
- **既知の残件:** 変奏セクションの UI 配置は作者イメージと相違があり手直し予定（機能は現状のまま採用）。`loadIterationItem` は変奏フィールドを復元しない（保存は行われるため再計算可能。既存 focus と同扱い）。`api_history_neighbors` が history の score を文字列のまま比較関数へ渡す既存バグを pentala ログで確認（変奏とは無関係、未修正）。


### v2.0.1 — モデルカタログ v2.1（深夜ベンチ統合、Build 612、2026-07-21）

- **実測 3 回目（深夜）の統合:** NVIDIA NIM 86 モデルの深夜ベンチ（2026-07-20 23:38 〜 翌 02:54、86/86 完走、スリープ中断なし）を統合し、採点を昼・夕・深夜の 3 実行合算へ更新した（`MODEL_CONFIG_VERSION` 2.0.0 → 2.1.0、43 → 44 エントリ）。`openai/gpt-oss-20b` を新規収載、削除はゼロ。速度ラベルは 3 実行を併記する。採点基準は不変だが、推奨度 5 の「全実行で全成功」条件が実行追加で厳しくなり、昇格 4 件（`qwen/qwen3.5-397b-a17b`・`z-ai/glm-5.2` が 5 へ、`meta/llama-3.3-70b-instruct`・`poolside/laguna-xs-2.1` が 4 へ）・降格 7 件（`mistralai/mistral-nemotron` 5→4、`minimaxai/minimax-m3` 4→2 ほか）。履歴が参照するモデルの脱落はゼロ（保全チェック通過）。
- **時間帯検証の打ち止め:** 昼・夕・深夜とも総所要は 3 時間 16〜20 分に収まり、深夜は応答中央値が下がる（62.8s → 41.9s）ものの、フォールバックが単調増加（35 → 37 → 38）して相殺した。「空いた時間帯なら短縮される」仮説の検証はこれで打ち止め。詳細は `no-git-sync/fable5/mode-api-claude/RUN-LOG.md`。
- **検証:** pytest 636 passed / 30 skipped（テスト変更はカタログ表明値の実測更新のみ）・`npm run check` 0 errors。pentala 配備済み。


### v2.0.2 — 小粒バグ 2 件の修正（近傍履歴の 500・履歴ロード時の変奏値消失、Build 613、2026-07-21）

- **`GET /api/history/{id}/neighbors` の 500 を修正:** `list_neighbor_candidates()` だけが `history.score`（TEXT 列の JSON 文字列）を `json.loads` せず生のまま返しており、`composition_distance()` 内の `score.get(...)` が `AttributeError: 'str' object has no attribute 'get'` で毎回 500 になっていた（他の履歴取得経路は loads 済み。pentala 実測 2026-07-20 以降 79 件、score 保存済み候補が 1 件でもあれば必ず失敗するため近傍表示は事実上全滅していた）。新設の `_neighbor_score()` で loads し、壊れた JSON・NULL・非オブジェクトは `{}` にフォールバックして候補を落とさない。回帰テスト 1 件を追加（修正前に契約記載と同一の AttributeError で失敗することを確認済み。`history.score` は NOT NULL 制約のため NULL 混在は空文字列で代替検証）。
- **履歴ロード時に変奏フィールドを復元:** `loadIterationItem()` の `result` 再構成に `variation_amplitude` / `variation_seed` の 2 行を追加した（保存側は v2.0 で結線済み。読み直すと undefined になっていた）。`focus` の復元は外部入力撤去済みのため行わない（現状維持）。復元値の消費先（変奏再実行への seed 引き継ぎ等）はスコープ外。
- **検証:** pytest 637 passed / 30 skipped（ベースライン 636 + 新規 1）・ruff・`npm run check` 0 errors。実装レポートは `no-git-sync/fable5/claude_code/tasks/small-bugs-v202-result.md`。



### v2.0.3 — 変奏を第 5 の推敲要素へ統合・調整ダイアログの手直し（Build 630、2026-07-21）

- **変奏の第 5 推敲要素化（作者裁定）:** v2.0 の既知残件だった変奏セクションの配置を裁定どおり整理した。`RefineKind` に `hensou` を追加し、ラジオは 配置 / 読み取り / 色カタログ / 変奏 / 言葉でタッチ の順（作者指示で「言葉でタッチ」の上へ）。変奏選択時のみ強度（小・中・大、既定 中）をラジオ直下に段落ちで表示し、各強度に `ddl_expander.py` の段階解放に対応するツールチップを付けた。実行は既存の 1案/4案 に統合（1案 = 新規 seed 1 つ、4案 = 4 つ、採番は `POST /api/variation/seeds`）。「変奏を描く」ボタン・独立セクション・関連 i18n/CSS を撤去。統合の副産物として変奏候補でも系譜の親可視化（`ensureVisibleLineageParentId`）が走るようになった。
- **調整ダイアログ・候補・カードメニューの逐次改良（作者の逐次指示 13 件）:** 速度目安を描画ボタン直下の単独行へ移動。候補の保存ボタンを右寄せし未保存・保存中・保存済みの 3 状態化（保存済みは押下不可）。候補グリッドをウインドウ内に収め（`max-height`、固定 aspect-ratio 廃止）、1案時は全幅 1 列。推敲要素の選択を `localStorage` で記憶（`reading` が非表示になる場合は `touch` へ退避）。未描画時も破線枠プレースホルダで候補エリアを常時表示。作品カードメニューは見出し「作品を編集する」を付けて 描画要素 → 記述 → DDL → モデル → 言語 → AI 自律推敲 の順に再編し、項目名を対象語のみに短縮・行間を詰めた。調整/モデル/言語ダイアログのタイトルを「描画要素を編集」「モデルを編集」「言語を編集」へ統一。ランダム自律推敲では方向性が読み取り世代にだけ反映される条件をヒント表示（挙動は不変）。
- **AI 自律推敲に変奏を追加:** サーバーの `ALLOWED_KINDS` に `hensou` を追加し有効要素の上限を 4 → 5 に（サーバー変更は 2 ファイル 2 行。契約の「サーバー無変更」は作者指示で解除）。変奏世代は強度を中に固定し、seed はサーバー採番。UI は `PaintOptions` に `variationAmplitude` / `variationSeed` を追加。
- **ボタン寸法トークンの導入（作者裁定によるルール化）:** `+page.svelte` の `:root` に `--btn-sm-font-size` / `--btn-sm-padding` / `--btn-sm-radius` を新設し、`InputPanel` の `.ghost-btn` と `LineagePanel` のボタン群を変換した（`.ghost-btn` は約 37 箇所で個別定義されており片方だけ直すとズレる状態だった）。以後、ボタン CSS に触れたコンポーネントは漸進的にトークンへ寄せる規約とし、`docs/inku-dev-conventions.md` §3-2-1 と AGENTS.md に記載。あわせて「コード変更時の pentala rsync + 再起動 + Build 採番は作者承認不要」の常時承認を規約化した（§4-5）。
- **検証:** pytest 637 passed / 30 skipped（サーバーは 2 行変更のみ、回帰ゼロ）・ruff・`npm run check` 0 errors（既存 a11y 警告 2 件）・build 成功。マージ後の主 checkout でも同値を再確認。pentala へは実装中に Build 614〜629 を逐次配備し、作者が実画面で確認済み。実装レポートは `no-git-sync/fable5/claude_code/tasks/hensou-ui-5th-refine-result.md`。
- **残件:** AI 自律推敲の変奏は強度中固定で UI から選べない。寸法トークンへの移行は 2 コンポーネントのみ（規約に従い漸進）。


### v2.0.4 — 自律推敲の変奏強度選択・ボタン寸法トークン移行の完了（Build 634、2026-07-21）

- **AI 自律推敲の変奏強度選択:** v2.0.3 で中固定だった自律推敲の変奏強度を選択可能にした。推敲要素の変奏チェックが ON のときだけ、直下に段落ちで小・中・大の 3 択を表示（既定 中、調整ダイアログの強度インラインと同型・ツールチップは既存キー再利用）。選んだ強度は実行中の全変奏世代に適用される。既定のまま実行した場合の挙動は v2.0.3 と同一。変更は `AIRefineModal.svelte` のみでサーバー無変更（強度は従来どおり `PaintOptions` 経由で世代ごとに渡る）。強度 3 択のツールチップはモーダル本文のスクロールコンテナに切られるため上向き配置とした。
- **ボタン寸法トークン移行の完了:** `--btn-sm-*` トークンへの変換を全対象に広げた。3 プロパティ完全一致の 12 ブロック / 10 ファイル（`.ghost-btn` 9 件 + `.danger-btn`/`.confirm-btn`/`.ddl-new-btn`）は見た目不変の単純置換。部分一致で保留した 6 ブロックも作者裁定「未変更のものも全て変更して」により統一し、デモパネル・未読語パネル・プロフィール・認証パネル・履歴マネージャ系統メンバー行（9px→11px 拡大）で寸法が変わった（ロックバッジは同値で不変、ピル形状の radius のみ非トークン）。これで `.ghost-btn` 定義全 14 ファイルの移行が完了し、px 直書きの小型ボタンは解消。色・hover・disabled は全ブロックで不変。
- **検証:** pytest 637 passed / 30 skipped（サーバー無変更の回帰確認）・`npm run check` 0 errors（既存 a11y 警告 2 件）・build 成功（Mac / pentala とも）。マージ後の主 checkout でも同値を再確認。実装中に Build 631〜633 を pentala へ逐次配備し、強度 UI とトークン変換は作者が実画面で確認済み（ツールチップ見切れは Build 632 で修正）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-v204-followups-result.md`。
- **残件:** v1.99 F-4 の作者目視確認と SPEC §17.A の未対応 dimension（作者裁定待ち）は継続。


### v2.0.5 — wave 揺らぎの seed 位相・材質輪郭の演奏 seed 追随（F-4 Phase 2、Build 636、2026-07-21）

- **wave 品質の seed 非依存バグを修正:** 作者の F-4 目視確認で「変奏候補・タッチ変更・再演奏で揺れ方が変わらない」ことが発覚。原因は `_sample_offset` / `_sample_offset_periodic` の wave 分岐が位相固定の `sin(t·2πf)·amp` で seed を使っていなかったこと（line 時代からの挙動。perlin/pink/white は seed 依存）。`_wave_phase(seed) = _hash01(...)·2π` を導入し `sin(2π·t·freq + φ(seed))·amp` へ変更した。整数周波数（slow 2 / medium 6 / high 14）による閉輪郭の自動閉合、弧の両端点固定、多角形の角固定（辺ごとに位相独立）は維持。
- **材質輪郭の演奏 seed 追随（Phase 2）:** `_add_material_{circle,ellipse,rect,arc}_outline` / `_material_line_group` の 5 箇所に `render_seed` をスレッドし `_seed_for_instruction(ins, render_seed)` へ変更。形状パラメータ（offset/width/opacity/dash/speck）の値域・語彙は不変。演奏 seed 未指定時は従来とバイト一致（後方互換）。
- **render engine version 5 → 6:** 同一 Score + 同一 seed の演奏結果が変わるため。`test_api.py` の期待値 3 箇所を更新（歴史的リテラルと `test_cloudform.py` は不変）。
- **検証:** pytest 693 passed / 30 skipped（新規 `test_renderer_wave_phase.py` 56 件: 7 primitive の seed 追随・決定性・閉合・端点/角固定・材質輪郭 seed 差・None 後方互換）。新規テストは変更を stash して main の実装で 11 件落ちることを確認済み（退行検知の実証）。SVG 全文比較は display 用 touch filter が常に差を出すため、filter 除去後の比較に修正。Mac/Linux の sin/cos 実装差（末尾桁）による golden 割れは 6 桁丸め正規化で 3 環境一致を確認。PNG 比較成果物は `cli/out2/635-v2.0.5-wave-phase/`（3 Score × seed 111/222/333 + 再演奏 + コンタクトシート）。
- **作者確認:** UI の変奏 4 案・タッチ変更で揺れ方が変わることを確認済み。ただし「変奏 大でも驚くような量変化ではない」との評価があり、原因は振幅の絶対 px 設計（`AMPLITUDE_PX` fine 7 / medium 12 / broad 30、キャンバス 1000px 比 0.7〜3%）にあるため、**B 案（振幅の図形寸法比例化）を次契約として起票予定**（engine 7 の再 bump を伴う見込み）。


### v2.1.0 — レンダリングの px 絶対値を比例系へ全面改修・材質強度の再調整（Build 638、2026-07-21）

- **A 層（揺らぎ・滲み）を図形寸法比例化:** 振幅語彙 fine / medium / broad の意味を 1000px キャンバス基準の絶対 px（`AMPLITUDE_PX` 7 / 12 / 30）から図形の代表寸法比 `AMPLITUDE_RATIO`（0.025 / 0.08 / 0.18、作者キャリブレーションで候補 P3 を採用）へ変更。代表寸法は circle / polygon / arc = 半径、ellipse = 半径の相乗平均、square / triangle / cloudform = 短辺 1/2、line = 線長（下限 `canvas.unit × 0.02`、振幅上限 = 代表寸法の 40%）。滲み（pink）は `BLUR_RATIO` 0.009 / 0.03 / 0.07（候補 P3）。多角形は代表寸法由来の単一 amp を全辺共有し異方性を排除。輪郭分割数は固定 80 → 長さ比例（クランプ 32〜200）、ストローク標本数は固定 49 → 長さ比例（クランプ 17〜129）。blur filter id は std 値込み（`blur-{amplitude}-{std*10}`）へ。
- **B 層（材質）を `canvas.unit` 相対化 + 強度再調整:** 線幅・dasharray（直書き 14 個含む）・質感 filter（`TEXTURE_FILTERS` を `TEXTURE_SPECS` + 動的 XML 生成へ置換、`baseFrequency` は unit に反比例）・材質輪郭・speck を `s = unit/1000` でスケール。speck 個数は固定 18/28/36 → 周長比例（アンカー = radius 0.2 の円、下限 10）。作者所感「材質の効果をあまり感じない」を受けた 2 巡キャリブレーションで強度段 **s1** を採用: 材質輪郭 offset（下限 `unit × 0.0035`）・輪郭 opacity（下限 0.50）・speck opacity（下限 0.40）・speck 個数ゲイン 2.6 の下限方式（弱い pencil / crayon だけが持ち上がり、既に読める brush 系は不変）。質感 filter は作者裁定（方針 3）で据え置き。材質輪郭に `class="material-outline"` を付与（主線との機械的区別、touching 検査も opacity 閾値から class 判定へ）。
- **C 層（display filter）を `canvas.unit` 相対化:** `_performance_touch_filter` の `baseFrequency` / `scale` をスケール。書式は不変。
- **render engine version 6 → 7:** 同一 Score + 同一 seed の演奏結果が変わるため。`unit=1000` では材質の寸法・dasharray・線幅・質感 filter・display filter がバイト一致（差分は speck 個数の周長比例化と stroke 標本数の長さ比例化のみ、個数を旧仕様に戻す実験で証明済み）。`/api/reference` の公開キーを `amplitude_ratio` / `blur_ratio` / `segment_target_ratio` 等へ改名。
- **検証:** pytest 724 passed / 30 skipped（新規 `test_renderer_proportional.py` 31 件）・ruff。`test_renderer.py:1590` の legacy golden（weight=pen / variation なし）は不変のまま通過し線幅バイト一致の番人として機能。perlin / white の「サイズ 2 倍→振幅 2 倍」検査は seed が図形内容依存のため rel=0.25 の許容差とし、厳密比例は `_amplitude_px` 直接検査で担保。キャリブレーション成果物は `cli/out2/637-v2.1.0-proportional-calibration/`（滲み・材質比較は cairosvg が feGaussianBlur も非描画と判明したため HTML/ブラウザ比較に変更）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-v21-proportional-result.md`。
- **残件:** 質感 filter は知覚閾値以下のまま（pencil 変位 ≈ 画面 1px。本筋は PNG ラスタライザ契約側）。`PRIMITIVE_AMP_GAIN` は空辞書（line 抑制なし、実作品で要調整なら 1 行）。後続契約: 閉図形への手描きストローク適用（`opus-closed-shape-strokes.md`）・PNG ラスタライザの filter 対応（`opus-png-filter-rasterizer.md`）。


### v2.2.0 — 閉図形の輪郭を手描きストロークで描く（Build 640、2026-07-21）

- **`stroke_engine.py` に任意中心線のストローク合成 `synthesize_along` を追加:** ToolGrammar（減衰・latent energy・catch/fade/correction・taper/bulge）は line 用 `synthesize_stroke` と同一で、追従目標だけを直線から任意中心線へ差し替え。出力は左右の岸からなる塗り帯（外周・内周 2 サブパス、`fill-rule="evenodd"`、`class="contour-stroke-v1"`）。角は `anchors` で理想位置に固定し追従器をリセット（角 = 筆の継ぎ目）、角のない閉輪郭は継ぎ目を線形ランプで閉合（envelope 下限 0.35 で「切れて見える」ことを防止）。**積分器は意図の歩幅をフィードフォワードし、ばねには残差だけを担わせる**（絶対位置追従では曲率のある軌道で半径方向の歪み ±10% が出ることを実測し設計変更。全 weight で半径偏差 ±1% 以内・角のはみ出し最大 1.42px）。
- **閉図形（circle / ellipse / square / triangle / polygon）の描画経路:** 対象 weight は rotring を除く GRAMMARS 全種（line のゲートと同一）。本体要素は幾何のまま残し、実線では `stroke="none"` で塗りのみ担当（bbox・touching・座標系は不変）。破線・点線は線種が記述なので幾何輪郭を 0.42 倍に細めて残す。帯の中心線は**変奏を演奏した後の輪郭**（合成順序の契約 4）。材質輪郭・speck は帯と併存（契約 5）。drypoint の burr は弧抽出器の誤検出を避け `<polygon>` で出力。arc は作者裁定で対象外（touching 検査の弧抽出器が `<path d="M..A..">` / `<polyline>` しか弧と数えないため、次契約で抽出器ごと設計）。cloudform は専用輪郭生成器を持つため対象外。
- **render engine version 7 → 8:** 同一 Score + 同一 seed の演奏結果が変わるため。line と arc の出力は v2.1 とバイト一致（`MATERIAL_NONE_SEED_DIGESTS` の `brush_thin_line` / `crayon_arc` digest 不変で固定）。
- **`test_gate_closed_output_unchanged` の読み替え（作者承認済み）:** 旧テストの「variation なしとバイト一致」は F-4（v1.99）の封じ込め保証であって恒久契約ではなく、main 時点でも pen / rotring 以外では既に不成立だった（`_seed_for_instruction` が variation を演奏の有無に関わらず seed key に含めるため）。`test_gate_closed_geometry_unchanged` に改め、手描きストローク層を除いた「意図の幾何」の不変を検査（ゲート誤開放は本体要素が揺らぎ polygon に変わるため検出可能）。「演奏されない variation を seed に影響させない」別解は `filled` 意味論と同じ「見え方が変わる変更」の束として別途扱う候補に残す。
- **検証:** pytest **852 passed / 30 skipped**（新規 `test_closed_shape_strokes.py` 128 件: 帯の存在・決定性・seed 追随・角固定・閉合・evenodd 構造・変奏後合成・材質併存・破線の幾何維持・rotring 不変）・ruff clean（Mac / pentala 両環境）。SVG サイズは帯 1.5〜19KB/図形、最大 29KB（drypoint 8 角形 + broad/high 変奏）。**作者目視確認 OK**（2026-07-21、pentala 実 UI）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-closed-shape-strokes-result.md`。
- **付随して判明（作者判断待ち）:** 閉図形は `filled=False` でも常に塗りつぶされる（`_stroke_attrs` の `do_fill` が閉図形を無条件 True にする死にフィールド）。「材質の効果をあまり感じない」の主因候補。参考採取 = `cli/out2/639-v2.1.0-closed-shape-strokes/unfilled-*`。あわせて「塗り = 細かいストロークで内側を埋める」案の調査・試作 3 回を記録（`synthesize_along` 流用可・clipPath 不要・間隔下限必須・1 図形 40〜63KB、engine 9 相当）。作者指示により pending 案件消化後に検討。


### v2.2.1 — PNG ラスタライザの filter 対応（resvg 化）・Python 3.12 統一（Build 643、2026-07-21）

- **resvg-py 0.3.3 を採用:** cairosvg が `feTurbulence` / `feDisplacementMap` / `feGaussianBlur` を黙って無視するため、質感 filter と滲みが全 PNG 経路（ダウンロード・AI Vision 入力・奥書サムネイル・CLI）で消えていた。実測比較（librsvg / Playwright / skia-python / resvg CLI）の結果 resvg-py を採用（3 filter とも描画、wheel 1.2MB・システム依存なし、MIT/MPL-2.0）。共通ヘルパー `shared/src/inku_analysis/rasterizer.py`（`svg_to_png` / `rasterizer_backend` / `rasterizer_info`）を新設し、優先順 resvg → cairosvg → `RasterizerUnavailable`。不在時の warning + skip 挙動は維持。奥書のネスト SVG（data URI `<image>`）も resvg で描画される。
- **置換 9 箇所と契約の訂正:** サーバー 3 経路（`api.py` PNG ダウンロード・`autonomous_refine.py` Vision 入力・`okugaki.py` サムネイル）に加え、CLI 5 箇所（`paint --png` / `analyze --replay` / `history-export` / `refine --png` / `inspect --png`）。契約の「CLI はサーバー API 経由に帰着」は誤りで、**API に PNG エンドポイントは存在せず**（責務は SVG 文字列まで）、CLI は応答の `svg` を自プロセスでラスタライズしていた。作者承認のうえ CLI 側も同ヘルパーへ寄せた。
- **Python 3.12 統一（作者承認 案 1）:** resvg-py に macOS cp310 wheel が無く 3.10 venv では Rust ビルド（2 分超）になるため、`server` / `cli` / `shared` の `requires-python` を `>=3.12` へ引き上げ、`.python-version` を 3.12 に統一、`uv.lock` 再生成。pentala は linux cp312 manylinux wheel で Rust ビルドなし。
- **バックエンドの可視化（追加実装、作者裁定）:** cairosvg への無警告フォールバックで PNG が実際の作品より綺麗に見えるリスクに対し、(a) CLI は cairosvg 時に 1 プロセス 1 回 stderr 警告、サーバーは import 時に resvg = INFO / フォールバック・不在 = WARNING（journal 到達を pentala 実機確認）、(b) PNG 生成時に `paths["png_rasterizer"]`（backend/version）を成果物・`summary.json` へ記録。server venv と cli venv は同一 SVG から byte 一致を実測（resvg-py 0.3.3）。lock 一本化（uv workspace 化）は作者裁定で別契約。
- **editable 化（デプロイの罠の解消）:** `inku-analysis` は venv へコピーとしてインストールされており、**`shared/` を rsync + 再起動しても `uv sync` までは古いコードが動き続ける**罠があった。`[tool.uv.sources]` の `editable = true` で解消。以後 `shared/` の変更は rsync + 再起動で反映される。
- **不変:** SVG 本文・`render_hash`（rh2）・render engine version（8）は無変更。PNG はハッシュ材料に含まれない。
- **検証:** server **863 passed / 30 skipped**（新規 `test_rasterizer.py` 11 件: cairosvg が落とし resvg が描く両方向の主張・フォールバック・不在パス・両バックエンドの出力サイズ 4 パターン一致・`rasterizer_info`）、cli **68 passed**（新規 3 件: メタデータ記録・警告 1 回・resvg 時無警告）、ruff clean。全 stage2 fixture 15 × 全 profile 3 = 45 通りの実ラスタライズ無エラー。pentala でも 863/30（Python 3.12.13、backend=resvg）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-png-filter-rasterizer-result.md`。
- **申し送り:** 生成 PNG は旧 PNG と画素非互換（filter が描画されるため。`cli/out2/` 過去ランとの直接画素比較は不成立）。resvg は cairosvg の約 6 倍の実行時間（768px で 207ms）。cairosvg はフォールバックとして残置。pentala への CLI 同期は運用があれば別途。Android の cairosvg（停止中）は対象外。


### v2.3.0 — 塗りのストローク化・`filled` の復権・surface ハッチの筆致化（Build 645、2026-07-21）

- **閉図形の塗りを領域 fill からストローク塗りへ（`fill-stroke-v1`）:** 閉図形の内部表現を三択に整理（`surface` 指定 = surface ベクタ / `filled=True` = 塗りストローク群 / `filled=False` = 描かない、いずれも本体要素の fill は `none`）。`_fills_interior` が `_stroke_attrs` の `do_fill`（閉図形を無条件 True にする死にフィールド）を置き換え、**`filled` の意味論を復権**（`True` = 素材の筆致で内部を埋める / `False` = 輪郭のみ）。`_scanline_segments` は走査線と閉輪郭の交点を対で取り内部区間を返す（辺判定は半開区間で頂点の二重カウントなし。clipPath 不要、凹形も交点対のまま）。`_render_fill_strokes` は 1 区間 = 1 筆で `synthesize_along(closed=False)` に通し、端点を交点から線幅の半分だけ内側へ寄せ、走査線ごとに向きを往復。筆ごとの seed は `_fill_stroke_seed`（輪郭帯と同一 seed だと同じ energy 波形が内部にも出るため分離）。濃度は色ヒントの塗り側（`fill_opacity`、無ければ `stroke_opacity`）。cloudform は描画曲線を標本化した密なポリゴンを走査。
- **着手前の作者裁定 4 点（2026-07-21）:** 走査角 = 演奏 seed 由来 0〜180° 一様 + 間隔 `max(線幅 × 1.5, canvas.unit × 0.012)` に ±12% ジッタ（完全被覆は狙わず紙目を残す）／rotring = 領域 fill 維持（`True` = ベタ / `False` = 輪郭のみ）／微小図形 = 走査線 3 本未満は領域 fill に縮退／surface ハッチ化の範囲 = hatch / crosshatch のみ（粒系・滲み系は対象外）。
- **surface ハッチの筆致化（`surface-stroke-v1`）:** `_render_surface_vectors` の hatch / crosshatch を、中心線・角度・間隔・本数はそのままに `synthesize_along` の帯へ差し替え。rotring は幾何直線のまま（`_uses_hand_stroke` で分岐）。`surface` 指定時は素材塗りを抑制（塗り = 素材の既定の埋め方、`surface` = 明示的な版表現）。
- **演奏されない variation を seed key から除外:** `_variation_seed_fields` が実際に消費されるフィールドだけを seed key に残し、不消費なら `variation` なしの Instruction と同じ形にする。primitive 別の不活性判定（line は position_x|y、閉図形は position_x|y|radius が活性軸。pink は quality + amplitude のみ消費。cloudform は輪郭生成器が quality / amplitude / frequency を常に消費するため不活性なのは `dimensions` のみ）。不活性 variation の有無で演奏バイトが変わらない不変則が全 weight で初めて成立。
- **render engine version 8 → 9:** 同一 Score + 同一 seed の演奏結果が変わるため。line / arc は不変（`MATERIAL_NONE_SEED_DIGESTS` の `brush_thin_line` / `crayon_arc` digest 無更新で封じ込めを固定。C の seed 変更も両者を動かさない）。
- **検証:** pytest **985 passed / 30 skipped**（新規 `test_fill_strokes.py` 122 件: 手描き weight 9 種 × 閉図形 6 種の塗り群存在・`filled=False` で不在・1 パス = 1 筆・円の半径内包・凹形 cloudform のはみ出し線幅以内（実測 0.46px）・走査角の seed 多様性・間隔ジッタ・微小図形の縮退・rotring 維持・line / arc 不発火・決定性・surface 抑制と帯化・不活性 variation のバイト一致）、cli 68 passed、ruff clean（Mac / pentala 両環境）。golden digest 更新は理由つき（`filled` 復権により塗らない図形から塗り濃度が消える等）。
- **サイズ実測（上限なしで観測、作者裁定）:** 1 図形 11〜123KB（中央 45KB）、10 instruction の作品で 422KB。最大は塗りではなく surface crosshatch の 192KB（幾何直線 80 本 × 2 層が帯化）。上限規則は実運用の分布を見て後付け。採取物 = `cli/out2/644-v2.2.1-stroke-fill/size-observation.json`。
- **作者所感（PNG 報告後）:**「一気に情報量とニュアンスが増えました。ブレイクスルーだと思います」。あわせて人間のエミュレーションの危険への自覚が示され、以後の筆致改修は「より人間らしく」を理由にせず**記述で書き分けられる差が増えるか**で提示する方針を恒久記録。
- **残件:** 実 UI 目視（特に塗り間隔の粗密）・サイズ上限規則・surface 粒系 / 滲み系の筆致化。arc のストローク化は裁定済み（不可視の意図弧を残し抽出器無改変・接点端も taper のまま）で engine 10 / v2.4 として次契約へ。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-v23-stroke-fill-result.md`。


### v2.3.1 — 弧のストローク化（Build 647、2026-07-21）

- **arc を手描きストロークの帯（`arc-stroke-v1`）で演奏:** `_render_instruction` の arc 分岐を `_uses_hand_stroke` で分け（line と対称）、rotring / 非 GRAMMARS は幾何の弧のまま、手描き系は新規 `_render_arc_hand_stroke` で帯として描く。中心線は変奏なし = 幾何弧の密標本化、変奏あり = 演奏後の弧（両端は意図値に固定）。帯は `synthesize_along(closed=False)` 1 呼び出し。v2.2.0 で残されていた最後のストローク化対象外を解消。
- **不可視の意図弧（裁定 A、2026-07-21）:** 幾何の弧を `stroke="none"` の意図要素として残す（変奏なし = `<path d="M..A..">`、変奏あり = `<polyline>`）。touching（接点契約）の検査は描画 SVG からこの意図弧を読み戻して座標で担保するため、**弧抽出器 `_svg_arcs` は無改変**（`test_touching.py` 全通過が要の検査。帯は弧コマンドを持たない塗りポリゴンなので二重計上されない。drypoint burr は低 opacity で polyline 分岐に拾われない）。
- **接点端は taper のまま（裁定、2026-07-21）:** envelope が両端でゼロへ収束し、幅の下限は置かない。接点契約は意図弧が座標で担保するため、帯は自由端と同じく端で柔らかく消える（葉の先端・付け根は柔らかく消える見た目になることを作者了承）。
- **style / drypoint / 材質:** 破線・点線は意図弧そのものを細い破線 / 点線で可視化（別要素を足さないので弧は 1 個のまま）。drypoint は演奏後の中心線に法線オフセットで burr を出し、帯にはテクスチャ filter を載せない。材質輪郭・speck（`_add_material_arc_outline`）は帯と併存。z 順 = 意図要素 → 帯 → burr → 材質輪郭。プロファイル差は display のみ帯に texture filter。**初版試作の罠（帯だけでは材質が抜け評価が反転する）は契約に明記され、材質併載で実装された**。
- **render engine version 9 → 10:** 同一 Score + 同一 seed の演奏結果が変わるため。arc 以外は不変（`MATERIAL_NONE_SEED_DIGESTS` の `brush_thin_line` と閉図形 3 件は無更新のまま通過、`crayon_arc` のみ理由つき再採取）。
- **検証:** pytest **1022 passed / 30 skipped**（新規 `test_arc_strokes.py` 37 件: 手描き 9 weight の帯存在・rotring 不変・solid の意図弧不可視と抽出器規準で弧 1 個・変奏ありの polyline 化・破線可視化・drypoint burr・材質併存・決定性・seed 追随・変奏後合成）、cli 68 passed、ruff clean（Mac / pentala 両環境）。`test_touching.py` 全通過（200 seed の幾何 / replay 契約含む）。
- **目視採取:** `cli/out2/646-v2.3.1-arc-strokes/`（SVG / PNG 8 組、resvg で材質 filter 込み: pencil の taper・brush_thick の濃淡・crayon / chalk の粒・drypoint の burr・rotring の幾何・破線・wave 変奏）。
- **残件:** 実 UI 目視（弧の帯の筆致・両端 taper・weight 差）。葉の見え方が変わるため Stage 3 葉の再目視も候補（「双弧が円に見える」所感との対照）。サイズ上限規則は引き続き後付け（今回サイズ網羅採取は未実施）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-v24-arc-strokes-result.md`。


### v2.3.2 — 対話型 UI 調整（v2.3.1 機能群への追随）・描画並列度の管理者設定・用語の層別統一（Build 683、2026-07-22）

- **対話型セッションによる UI 調整 35 件（Build 648〜682）:** 作者の逐次指示 → 実装 → pentala 実 UI 確認の反復で実施。主な内容:
  - **歳時記ハイライトの英語対応**（`/api/saijiki` を日英並行取得し両語彙で最長一致、ASCII は単語境界 + 大小無視、色分けはカテゴリ `key` 基準）
  - **指示書エディタの拡充**（描画モデル選択ボタン・現在モデル表示、記述タブに「DDL を編集」ボタン、描画完了後は作品タブへ遷移）
  - **4 案描画の進捗表示**（並行実行のため「何番目」でなく完了数 `n/N` をステータスメタ行に表示）
  - **PNG ダウンロードに EXIF 撮影日**（新規 `pngMetadata.ts`。`eXIf` チャンクの `DateTime*` / `OffsetTime*` と `tEXt` "Creation Time" を作品の生成日で書込み、Pillow 読出し検証済み）
  - **入力 3 タブ（記述・バッチ・デモ）の整理**（ボタン列と設定状況帯 `.current-selection` を共通化、入力ボックス優先の再配置、バッチ・デモにも添景設定を結線〔従来はサーバー既定で描画されていた挙動変更〕、記述ラベルの入力ボックス直上移動と字数メーターの単位表示〔`34 / 31 字`、短歌 31 音由来。英語入力は 12 words〕）
  - **コンタクトシート**（履歴管理モーダルから選択作品を PNG シート化。人用 = 7×4/枚・キャプション付き、AI 用 = 3×4・長辺 1568px・連番バッジのみ + **作品番号・記述・来歴を結ぶ md ノートを同時出力**〔番号→記述→楽譜の三段照合用、`ddl` 収録・`expanded_ddl` 非収録は作者承認〕。SVG 入れ子合成は filter id 衝突のため canvas ラスタライズ経路を採用。作者確認で AI 認識良好）
  - **生成情報の詳細タブ拡充**（作成日・SVG サイズ・添景を追加。添景行は v1.97 以前の作品で行ごと消えていた条件表示を無条件化）
  - **ログイン画面**（バージョン / Build 表示、初期メッセージ枠の抑制）
  - **ダークモードのコントラスト是正**（`--accent-fg` トークンを新設し accent 塗り 13 箇所を寄せた。`var(--fg)`+`#fff` 直書き 3 箇所は `--action-*` へ。未定義トークン参照 2 件〔`--accent-fg` / `--button-active-fg`〕を解消 — **`ConfirmDialog` / `LineagePanel` はライトモード側も見え方が変わる**〔従来が誤り〕）
  - **バッチの追従性**（履歴ストリップの「表示中」バッジを画面上の作品 id で引き直し、バッチ入力欄を `clamp(200px, 42vh, 640px)` 固定高 + 行番号ガーター同期 + 実行行の自動スクロール）
- **描画並列度の管理者設定（サーバー変更、作者裁定 2 件）:** 4 案同時描画が既定並列度 2 を超え 503 になる問題への両面対応。サーバーは固定 `BoundedSemaphore` を実行時変更可能な `_RenderCapacity` へ置換し、DB 設定 `render_concurrency_settings`（`server_limit` / `client_limit`、1〜16）+ `PUT /api/settings/render-concurrency`（管理者のみ）+ `GET /api/client-config`（認証済み読取）を追加。環境変数 `INKU_RENDER_CONCURRENCY` は DB 未設定時の初期値へ格下げ。クライアントは `render capacity is full` の 503 のみ最大 3 回再試行（`Retry-After` 尊重）+ 候補生成ファンアウトの上限制御 + 専用エラー文言。設定 UI は「その他」タブに管理者専用の数値入力 2 つ。
- **用語の層別統一（作者教義の確定、2026-07-22）:** 「Sol LeWitt の指示書 = 正規化DDL。inku は詩歌的な入力層を一段上に足している」。UI の語彙を層別に整理（入力層 = 記述 / Description、Stage 1 の行為 = 解釈 / Interpret、その生成物 = **指示書（正規化DDL）/ Instructions**、詞書 = 記述の再掲）。i18n 13 キーを relabel し、App Info モーダルに常設の語彙対応表「用語と層」を新設。**SPEC.ja §5 を改訂**（記述と正規化DDL を別層に分離した 4 段パイプライン図、LeWitt との違いに層対応を明記、§5.3 に用語対応表を収録）、SPEC.md §2 に LeWitt 対応の一文 + 同表、README 日英「しくみ」節にも用語表を収録（UI ダイアログと同一内容を単一正本とする）。
- **運用上の発見（Build 664）:** `web/BUILD_NUMBER` は `web/src/` の外にあり従来の rsync 範囲外 + `vite.config.ts` の起動時 `define` 注入のため、**BUILD_NUMBER の反映には明示 rsync と `inku-server.service`（Vite）再起動が必要**。以降の反映は 3 手セット（`web/src/` + `BUILD_NUMBER` 明示 + Vite 再起動）に是正。
- **不変:** render engine version は 10 のまま。Score schema / coerce / rh2・renderer / stroke_engine は無変更（サーバー変更は並列度制御のみ）。
- **検証:** pytest **1023 passed / 30 skipped**（新規 `test_render_concurrency_settings_are_admin_only`: 一般 PUT 403・管理者 PUT 反映・`/api/client-config` 401/未認証・範囲外 400）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings（既存 a11y）。Mac / pentala 両環境。作者の実 UI 目視確認多数（対話サイクル内）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-ui-adjustments-result.md`。
- **保留・持ち越し:** UI 調整の続き（対話型・新セッション）、マスコット 2 種の扱い、描画所要時間・並列度 4 の CPU・503 発生率の計測、バッチ実行中に履歴ストリップがページ 0 へ戻る挙動（作者指示待ち）。

### v2.4.0 — リリース配布パイプライン（GHCR コンテナイメージ・タグ駆動 Actions・利用者向け compose）（Build 684、2026-07-22）

- **配布方式の確立（作者裁定 2026-07-22、個人 OSS の標準形）:** git タグ `vX.Y.Z` の push を起点に GitHub Actions（`.github/workflows/release.yml`）が `ghcr.io/oikawas/inku-api` / `inku-web` を multi-arch（linux/amd64 + linux/arm64、QEMU + buildx）で build & push する。`docker/metadata-action` で semver タグ（`X.Y.Z` / `X.Y` / `latest`）と OCI ラベル（source / licenses=MIT）を付与。`workflow_dispatch` は push なしの build 検証のみ（GHCR ログインもしない）。ブランチ push では workflow 自体が起動しない。
- **利用者向け配布物 `deploy/`:** GHCR イメージ参照の `compose.yaml`（`INKU_IMAGE_TAG` / ポート env 上書き可、api 8100 / web 5173 既定）+ `.env.example`（必須 = LLM キーと bootstrap admin パスワード、任意 = ポート・ORIGIN・cookie・CORS）+ `README.md`（Quickstart・初回アカウント・データ永続・版固定・HTTPS を日英併記）。開発・ベンチ用の従来 `compose.yaml` は `build:` 参照のまま分離維持。
- **BUILD_NUMBER のイメージ焼き込み:** `server/Dockerfile` に `COPY web/BUILD_NUMBER /app/web/BUILD_NUMBER` を追加（`uv sync` の後、依存層キャッシュ非破壊）。コンテナの `/api/info` `build_number` と生成物の `render_build_number` が null だった構造的欠落（初回コンテナ化以来）を解消。pentala 隔離プロジェクトでの実 build で `"683"` を確認。
- **`/api/info` version の単一情報源化（作者裁定: API はサーバー実装の版を名乗る）:** `api.py` の直書き `_APP_VERSION = "0.1.0"` を `importlib.metadata.version("inku-server")` 由来へ変更（契約からの逸脱として実装レポートに記録・妥当と判断）。`server/pyproject.toml` の version をリリースごとに採番する運用とし、本リリースで 0.1.0 → **2.4.0**。テストの直書き断言も metadata 比較へ書き換え、以後の採番でテストを触らない。
- **nature-leaves プラグインの git 管理化・同梱（作者裁定）:** pentala 正本 v0.3.0（177 行）を `server/plugins/` へ取り込み。既存の `COPY server/` で自動同梱され、空 DB の新規コンテナで `plugin install` なしに `Nature.leaves 0.3.0 enabled` を確認。`.plugin-state.json` は引き続き git 管理外（実行時状態）。
- **bootstrap admin の空文字是正（作者裁定 C = compose 必須化 + コード側寛容化の両方）:** セルフサインアップ経路が無いため bootstrap admin（`INKU_BOOTSTRAP_ADMIN_PASSWORD`、8 文字以上）が唯一の入口だが、compose の `${VAR:-}` 補間が渡す空文字を「0 文字の不正なパスワード」と読んで新規 DB の初回起動が ValueError でクラッシュループする構造だった（既存 DB では顕在化しない = 初回リリース利用者だけが踏む）。`db.py` で空文字を「未設定」に倒し、`compose.yaml` / `deploy/compose.yaml` とも `:?` で起動前必須化。挙動テスト 2 件を追加。`manual/`（ja/en 4 文書）と `SETUP*.md` に「セルフサインアップ不在・bootstrap admin なしでは誰もログインできない・password 設定 + 再起動で復旧」の前提を追記（SPEC は §15.4 / §12.1 に本リリースで記載）。
- **不変:** render engine version 10 のまま。Score schema / coerce / rh2・renderer・`web/src/`（UI）は無変更。開発・ベンチ環境（bare metal 8100 / bench コンテナ 8101）にも影響なし。
- **検証:** pytest **1025 passed / 30 skipped**（+2 = 空文字挙動）、workflow / compose の YAML 静的確認、pentala 隔離プロジェクト（8102/5175・専用 volume・local tag）で実 build → `deploy/compose.yaml` そのまま起動 → health / info / login / プラグイン同梱 / 撤収まで確認。bench コンテナ・bare metal は無改変。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-release-pipeline-result.md`。
- **公開手順の注意（レポートより）:** イメージが GHCR へ上がるのは `v*` タグ push の瞬間だけ。`git push --tags` の巻き込み事故に注意。初回 publish 後の GHCR パッケージは private 既定のため、匿名 pull には手動で public 化が要る。タグ削除とイメージ削除は別操作。（実際の初回 publish では最初から public だった — 2026-07-22 実測）

### README 整備 — 作品ギャラリー・UI スクリーンショット・構成改訂（docs のみ・採番なし、2026-07-22）

- **作品ギャラリー 6 点を新設（`docs/assets/gallery/`）:** 作者のスター付き履歴から選定（新規生成なし。全点 Build 667 / render engine 10、Stage 1・2 とも `nvidia:google/gemma-4-31b-it`）。各点 = 表示用 1000×1000 PNG + 詞書 + `<details>` に指示書・元 SVG・seed。冒頭にヒーロー帯（作品 3 点横並び）。記述・指示書・Score は `history-export` の実データを逐語掲載（改行位置・`color` まで実物どおり）。選定用コンタクトシート 21 点は `cli/out2/684-v2.4.0-readme-gallery/` に保存（入れ替え時の候補一覧に再利用可）。
- **UI スクリーンショット 6 点（`docs/assets/ui/`、日英各 3、Build 685 撮影）:** 作品／系譜／指示書エディタの 3 画面を実際の作業ループ順で掲載。`*.ja.png` / `*.en.png` の命名で各 README が自言語のみを参照（契約の「両言語で同一画像」から作者裁定で変更）。全画素の秘匿検査で除去を要した箇所なし。撮影中に検出した歳時記ダイアログの i18n 不整合は契約外として作者へ差し戻し（作者が Build 685 で修正、`feat/ui-adjustments-2` に収録。本マージには含まれない）。
- **README 構成改訂（日英とも）:** 「例」節を実作品の「作品 — 記述が絵になる」に差し替えて「しくみ」へ統合、「しくみ」に実 Score 抜粋の層解説「一枚の作品を層で追う」を新設、「画面」節を新設、「ドキュメント」節を末尾へ移動。語彙は 2026-07-22 の層別統一（指示書（正規化DDL）/ Instructions (Normalized DDL)）に追随。
- **画像の枠線 = 単一セル `<table>` 方式:** GitHub のサニタイザが `<img>` の `style` / `border` / `class` をすべて除去することを grip で実測し、唯一残る方式を採用（`.markdown-body table td` の枠線がテーマに自動追随し、縮小率によらず常に 1px）。単独画像 9 箇所すべてに適用。
- **`.gitignore` 変更:** `docs/` 丸ごと除外では配下パスを再包含できないため `docs/*` + `!docs/assets/` へ変更（`docs/` 配下の既存ローカル文書が無視され続けることを `git check-ignore --no-index` で確認）。
- **公開後のギャラリー差し替え（作者指摘、マージ `9f3ada1`）:** 2 点目「引き波の泡の弧」が GitHub の白背景に枠線を入れてもなお溶けて見えないため、「戦争が終わった朝…」（rh2 `B962`、silver-shoal。Build 667 / engine 10 で他 5 点と出自が揃う）へ差し替え。同一ファイルを使う 3 箇所（ヒーロー帯・ギャラリー・層解説）を追随させ、層解説は新作の実 Score で全面書き直し（記述→Score の対応例が 2 → 4 に増加）。新規 PNG は 544 色でグラデーション無しのため 256 色パレット化を実測（変化画素 0.10%・実質無損失）して適用し、表示合計を 2.8 MB（契約上限内）に維持。他画像への一律適用はしない（測定して無損失と確認できた画像に限る方針）。
- **検証:** 相対参照 55 件すべて解決・孤児アセットなし・`alt` 全数・タグ均衡。push 後の GitHub 実表示で日英とも画像 12 点ロード成功・raw 配信は SHA-256 一致・旧アセットは 404（削除確認）。
- **不変:** コード（`web/src/`・server）無変更、render engine version 10 のまま。`APP_VERSION` / `web/BUILD_NUMBER` / pyproject の採番なし（docs のみ）。pentala 反映なし（README はサーバー配信物でない）。マージ = `7e1469a` + 差し替え `9f3ada1`（本契約は特例として Opus がマージ・push・worktree 削除まで実施）。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-readme-visuals-result.md`。

### v2.4.1 — UI 調整 2 巡目（歳時記語彙の日英対応是正・語プレビューの英語化・記述タブの文言整理）（Build 687、2026-07-22）

- **対話型調整（Build 685〜686、2 セッション）:** DDL エディタの語プレビュー全 69 エントリを日英化（`effectEn` / `exampleEn`。Nature プラグイン 3 語を日英 1 エントリに統合、解説未登録だった `敷き詰める` / `触れる` を追加、汎用フォールバック文も日英化）。系譜タブの見出し下 2 文を削除（全体図側の説明のみ残置）。英語 UI の Okugaki ボタンラベルを `Okugaki` に簡素化。記述タブはヒント文とカウンタの二重記述を解消し、短歌への言及をカウンタ側へ移動（`文字数 12 / 31字（短歌）` / `Characters 12 / 31 (tanka)`。英語ヒント文は 85 → 49 字で 1 行に収まる）。
- **歳時記語彙の日英対応の是正（作業中に発見したバグ 2 件、作者裁定でサーバー側も修正）:** ① てざわりは削剪済みの `髪` / `hair`（P0-3、`display=False`）が i18n に残置され、表示語と解説の突き合わせが全体で 1 ずれ（英語 UI で `pencil` にホバーすると「ペン」の解説）。② うごきは `saijiki.py` の `words_en` の並びが `words_ja` と非対応で、`引く`↔`fill`・`埋める`↔`draw` の解説が日英とも交差（`ja.ts` はさらに独自の順）。**原因はサーバー正本語彙の i18n 手書き複製**。`words_en` を ja と同順（`place, line-up, draw, scatter, fill, tile`）へ並べ替え、i18n の `saijikiWords` を廃止して表示語をハイドレート済み `SAIJIKI` / `SAIJIKI_EN` から直接取得（`gen_saijiki_ts.py` が `GENERATED_SAIJIKI_EN` も出力、`saijikiWordsFor(key, isJapanese)` 経由）。全 10 カテゴリ 68 語の日英対応を明示テーブルと突き合わせるテストを追加（**リスト長が同じままの入れ違いは長さ検査では検出できない**ため対応関係そのものを固定）。golden は置換宣言 `_REORDERED_EN` で対応（fixture 無改変）。
- **副作用:** 英語版 Stage 1 システムプロンプトの `motions:` 行の語順が変わる（語の集合は不変）。英語入力の解釈がモデルによって微差を生む可能性があり、ベンチでの確認は未実施。SPEC.md の語彙表 motions 行を新語順へ追随（本 docs コミット）。
- **不変:** render engine version 10 のまま。Score schema / coerce / rh2・renderer / stroke_engine は無変更（サーバー変更は saijiki テーブル・生成スクリプト・テストのみ）。
- **検証:** pytest **1026 passed / 30 skipped**（+1 = 日英対応固定テスト）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings（既存 a11y）。`display_categories('ja'/'en')` の直接実行・`saijiki.generated.ts` のパース照合・表示 68 語全部のプレビュー解決（フォールバック落ちなし）を実装セッションで確認。Mac / pentala 両環境。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-ui-adjustments-2-result.md`。
- **保留・持ち越し:** UI 調整は対話で継続中（3 巡目へ）。マスコット 2 種、バッチ実行中の履歴ストリップ、計測 3 件（1 巡目から据え置き）。`words_ja` / `words_en` の構造的解決（`SaijikiWord` が両言語の表層を持つ形）は範囲外として据え置き — 語を追加する際はサーバーのテーブルとテストの対応表の両方を更新する。

### v2.4.2 — 歳時記語彙の日英ペアリングを構造で担保する（Build 689、2026-07-23）

- **位置依存の解消:** `SaijikiCategory` が持っていた `words_ja` / `words_en` の 2 本の並行タプルを廃し、`words` 1 本へ統合した。`SaijikiWord` は `surface_ja` / `surface_en` を 1 エントリに持ち（`surface_en` は `None` 可）、`default` / `prompt` / `display` / `marker` のフラグを言語間で共有する。日英の対応は**位置ではなくエントリ**が担保する。あいだ（relations）の `RelationWord` が最初から採っていた形（`surface_ja` / `surface_en`）へ、かたち〜わりあいの語彙も揃えた。
- **背景:** v2.4.1 で是正した日英対応バグ 2 件（`髪` / `hair` の残置による 1 ずれ、`ugoki` の並び非対応による解説交差）は、**並べ替えとテストによる固定**であって構造の修正ではなかった。「`words_ja` と同順で並べる」という規約がコメントでしか担保されず、語の追加・並べ替えのたびに再発しうる状態が残っていた。
- **Score 値の位置依存も同時に解消:** てざわり・いろの各語へ `score_value` を持たせ、カテゴリの語列と `_WEIGHT_VALUES` / `_COLOR_VALUES` を `zip` していた `_surface_value_map` を削除した。**てざわり語の並べ替えが Score の weight 値の取り違えに直結する**状態（長さ検査だけが番人だった）は、歳時記表示のずれより影響が重い。
- **特例の保持:** 削剪済みの墓標 `描く`（`ugoki`、英語に対応語なし）は `surface_en=None` の同一語列内エントリとして保持。`並べる` / `line-up` は 1 エントリにしたうえで、英語の閉包マーカーだけ `marker_surfaces_en=("arrange",)` で従来値を維持。`髪` / `hair` は `_PRUNED` のまま `score_value="hair"` を保持する（保存済み Score の Replay 互換）。
- **出力不変（受け入れ条件）:** `prompt_block` / `texture_material_enumeration` / `display_categories` / `saijiki_marker_table` / `core_grammar_markers` / `shape_markers` / `relation_literal_markers` / `reference_categories` / `weight_for_surface` / `color_for_surface` の日英 15 項目を変更前後で SHA-256 比較し全一致。`gen_saijiki_ts.py` の再生成結果 `web/src/lib/saijiki.generated.ts` もバイト一致（git 差分なし）。`_EXPECTED_PAIRING` の 68 ペアは**書き換えずに通過**した。Stage 1 プロンプトは日英とも 1 バイトも変わっていない。
- **不変:** render engine version 10 のまま。Score schema / coerce / rh2・renderer / stroke_engine・語彙そのもの（増減・改称）は無変更。
- **検証:** pytest **1028 passed / 30 skipped**（+2 = 構造テスト。旧構造では fail-first を確認済み）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings（既存 a11y）、`npm run build` exit 0。Mac / pentala 両環境。実装レポートは `no-git-sync/fable5/claude_code/tasks/opus-saijiki-word-pairing-result.md`。
- **残存する位置対応:** 最終出力形式（`GET /api/saijiki` の言語別語列、`saijiki.generated.ts` の 2 配列、表示リストの位置突き合わせテスト）には位置対応が残るが、いずれも**同一の二言語語列から導出**される派生物であり、正本側に手書きの並行リストはない。

### v2.4.3 — UI 調整 3 巡目（デベロッパーモード・系譜の縦横切替・デモのタイムアウト）（Build 693、2026-07-23）

- **デベロッパーモード `INKU_DEVELOPER_MODE`（Build 690、サーバー変更は作者裁定）:** 一般利用者に見せる必要のない選択肢を、環境変数ひとつで表示から外す仕組みを新設した。無効時は NVIDIA NIM が表示用モデルカタログ（`GET /api/models`、管理者のモデル設定の取得・更新、モデル一覧再取得）から外れ、常時表示していた Build 番号も左下レール・ログイン画面・アプリ情報から消える。`model_settings.py` はプロバイダー定義に `developer_only` フラグを持ち、`model_provider_catalog` / `public_model_settings` が `include_developer` 境界を受け取る。`/api/info` に `developer_mode` を追加し、web はログイン前にこれを読む（`loadPublicAppInfo`）。
- **隠すのは表示だけ（設計の要）:** 実行時のプロバイダー解決（`provider_for_model`）は無変更で、**無効時も NIM で描ける**。保存済みモデル設定・履歴のモデル情報・作品ごとの `render_build_number` も無効時に失われない。管理画面から NIM が見えない状態で設定を保存しても、更新は `exclude_unset=True` の patch を DB の全体設定へマージする経路のため、保存済み NIM 設定は残る。画面内の選択が非公開プロバイダーを指す場合だけ、Stage 1 / Stage 2 / Vision / 奥書の選択を公開カタログの先頭モデルへ補正する。
- **既定値:** 配布用 `deploy/compose.yaml` は **無効**（`${INKU_DEVELOPER_MODE:-0}`、`deploy/.env.example` に明示有効化の例をコメントで用意）、開発・ベンチ用のトップレベル `compose.yaml` は **有効**（`:-1`）。`server/.env.example` にも開発用の `INKU_DEVELOPER_MODE=1` を記載。SPEC は §15.4 / §12.1 に記載。
- **系譜の縦横切替（Build 691、フロントエンドのみ）:** 通常の系譜表示と系譜全体図が共有する「縦／横」切替を追加した。縦は起点の世代を上に置いて下へ、横は左に置いて右へ世代が進み、横では同世代の作品を縦積みにする。接続矢印は縦が親カード下端→子カード上端、横が右端→左端で、ベジエの制御点も方向ごとに計算し直す。全体図の説明文も方向に追随する。切替時はノード配置と矢印を再計算して注目カードを表示領域へ戻し、選択は `inku-lineage-orientation` としてブラウザへ保存する（有効値は `vertical` / `horizontal` のみ、既定は縦）。**系譜グラフの API・スキーマ・保存データ・世代番号の算出は無変更**で、変更は配置と操作に限られる。
- **デモのタイムアウト（Build 692、サーバー変更は作者裁定）:** デモ設定に 1〜1,440 分（最大 24 時間）のタイムアウトを追加した。画面は分、API と保存値は秒（60〜86,400、既定 3,600）。締切はデモ開始操作ごとに固定し、実行中の設定変更は効かない。**締切前に開始した 1 回分は締切を越えても記述生成と描画を完了させ**、結果を画面・統計・保存指定へ通常どおり反映してから停止する。締切後は次の生成を開始せず、描画間隔の待機中に締切へ到達した場合も同様。実行中は残り時間を `HH:MM:SS` で表示し、タイムアウト待ちのあいだは「次の描画まで」を出さない。自動停止時だけ到達メッセージを残し、手動停止では出さない。保存済み設定に `timeout_seconds` が無い既存ユーザーには既定値を補う。
- **トークン規律:** `DemoPanel` の `.step-btn` の `font-size: 14px` を `--btn-sm-font-size` へ移行した（触れたついでの寄せ）。系譜の方向切替ボタンは既存の `--btn-sm-*` を継承し、選択状態は `--accent` + `--accent-fg` を使う。新しい寸法トークンや px 直書きのボタン指定は追加していない。文言はタイムアウト設定・残り時間・自動停止メッセージとも `ja.ts` / `en.ts` / `types.ts` の三点で日英対応。
- **不変:** render engine version 10 のまま。Score schema / coerce / rh2・`renderer.py` / `stroke_engine.py` は無変更（サーバー変更は表示用カタログ境界とデモ設定の 2 点のみ）。版固定中の pentala ベンチ用コンテナ（8101）は再 build していない。
- **検証:** pytest **1029 passed / 30 skipped**（+1 = 通常モードで NIM が公開カタログから外れることの固定。既存の NIM 系テスト 2 件はデベロッパーモードを明示する形へ修正）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings（既存 a11y）。Mac / pentala 両環境。作者の実 UI 確認は Build 690（通常モードへ一時切替のうえ NIM と Build 番号の非表示を確認）、691（系譜の縦横表示・矢印・スクロール・再読込後の方向維持）、692（タイムアウト入力の上下限・残り時間・自動停止・再読込後の設定維持）とも完了。マージ = `e15d63f`。実装レポートは `no-git-sync/fable5/claude_code/tasks/codex-ui-adjustments-3-result.md`。
- **同梱した docs 是正 2 件（docs 単独では版を起こさない方針により本 entry へ畳む）:**
  - **`SETUP.ja.md` / `SETUP.md`（`fe63584`）:** コンテナ経路の節を新設（GHCR pull とソースからのビルドの 2 経路。詳細は `deploy/README.md` へ送る）。あわせて 3 件を是正 — ①「配布パッケージの内容」が `compose.yaml` / `deploy/` / Dockerfile 2 種などを落としていた ②**Python 要件を 3.10 以上と書いていたが実際は 3.12 以上**（利用者が `uv sync` で実際に踏む誤り）③ PNG ラスタライズを CairoSVG のみと書いていたが実装は resvg 優先で、落ちると材質フィルタが失われる。
  - **`README.ja.md` / `README.md`（`a15f699`）:** 再生成の節を「三つの『もう一度』」から **「推敲による作品の追求」** へ全面改稿。実装は推敲 5 種（`RefineKind`）+ AI 自律推敲 2 方式で、色カタログ変更・変奏・AI 自律推敲が記載から漏れていた。
- **保留・持ち越し:** UI 調整は対話で継続中（4 巡目へ）。マスコット 2 種、バッチ実行中に履歴ストリップがページ 0 へ戻る挙動、計測 3 件（1 巡目から据え置き）。

### v2.4.4 — engine 10 の描画出力を凍結する（参照コーパスとバイト一致の CI）（Build 694、2026-07-23）

- **目的（作者の一文）:** 描画コアを版上げしていくにあたり、**どこが変わったとき描画結果がどう変わったのかを、主に AI が判定しやすくすること**。版数は「変わった」という 1 ビットしか運ばない。何がどう変わったかは**出力の実物**を突き合わせないと分からない。
- **急いだ理由:** **render engine 1〜9 の出力は保存されておらず、コードも残っていない。復元できない。** Replay は常に最新 engine で行うと決めた以上、**その版が現役のうちに凍結しなければ engine 10 も同じように失われる**。
- **`server/reference/render-engine-10/` を新設し 220 ケースを凍結:** 段 A = 10 道具 × 8 図形の基盤（80）、段 B = 変奏 4 種 × 振幅 3 × 図形 3 × 道具 2（72）、段 C = 塗り・surface 8 種・`ground` material 6 種と `density` / `opacity` / `absorbency` の判別（40）、段 D = 判別（28）。各ケースに入力の全文・座標正規化 digest・バイト数・要素数・class 文字列を記録する。容量 3.2MB（manifest 412KB）。
- **段 D が最も効く。** `pillar`（`unit_scale` 0.2）は絶対 px の残存を暴き、**2\*\*63 を超える seed**（2^63+1 と 2^64-1）は符号の取り違えを暴き、極小図形は `FILL_MIN_SCANLINES` による領域 fill への縮退を暴く。実測でも `square` と `pillar` の digest は異なり、高位 seed 2 件は通常 seed と別 digest、極小図形は `fill-stroke-v1` を**持たない**（`contour-stroke-v1 controls-17 events-0` + `material-outline` へ縮退）。
- **入力は生成器側に literal で固定する（設計の要）:** 色表・Score・Instruction・Surface・Ground の**全フィールドを書き下し**、`renderer.COLOR_MAP` も `color_catalogs.py` も schema の既定値も参照しない。`coerce_score` も通さない。これにより `render-engine-10/` を動かせるのは **`renderer.py` と `stroke_engine.py` だけ**になる。実証として `COLOR_MAP["white"]` と `Score.background` の既定値をそれぞれ一時改変して再生成し、220 件すべてが変化しないことを確認した（確認後に復元）。
- **CI が本改修の本体（`.github/workflows/reference-corpus.yml`）:** 再生成 → `git diff --exit-code -- server/reference/` + 未追跡ファイル検査。これにより「**既存ケースの再生成は必ずバイト一致する。しないなら版を上げなければならない**」が破れない制約になる。従来の採番規律は人が守るもので 6 回守られてきたが、7 回目を保証するものは無かった。**「覚えている規律」から「機械的な制約」への転換が目的である。** 生成器側にも二重の番人があり、出力が動いたのに manifest 先頭の識別子（`corpus_format_version` / `engine_version` / `schema_version` / `color_map_digest`）がどれも動いていなければ異常終了する（= 固定し損ねた依存が残っているというコーパス設計自体のバグ）。
- **CI が実際に落ちることを実証した:** `stroke_engine.py` の `polygon_path` の座標整形を `.3f` → `.4f` に変えて再生成すると、生成器が exit 1 と「bump the appropriate version instead of rewriting a frozen corpus」を返した。確認後に摂動と corpus を復元し、再生成でバイト一致に戻ることを確かめた。**「CI を書いた」だけでは受け入れない**という条件を契約に置いた結果である。
- **`absorbency` は死にフィールドだった（副産物）:** `ground` の `density` / `opacity` / `absorbency` をそれぞれ変えた 3 件を並べたところ、density と opacity は digest が動くのに **`absorbency` だけ基準と同一 digest**（`4c267d64…`）。**現行 renderer は absorbency を読んでいない。** 以前の監査（`intent_audit_plan`）の疑いが確証になった。**本改修では直していない**（コーパスの目的は判定であって修正ではない）。
- **運用ルールの置き場を三層に分けた:** 契約 = SPEC（§15.5 / §12.1 の次）、**手順 = `server/reference/README.md`（成果物の隣。再生成しようとした人が最初に開く場所）**、強制 = CI。`docs/` と `CLAUDE.md` と `AGENTS.md` は git 管理外で clone した人に見えないため、規則の正本にしない。
- **配布物から除外:** `.gitattributes` を新設して `server/reference/ export-ignore`。`git archive HEAD` に `server/reference/` が 1 件も含まれないことを実測した。`SETUP.ja.md` → `SETUP.md` の「含まれないもの」にも 1 行足した。
- **不変:** **描画結果は 1 バイトも変わっていない。** `render_engine_version` は 10 のまま、`renderer.py` / `stroke_engine.py` / Score schema / coerce / rh2 は無変更で、`MATERIAL_NONE_SEED_DIGESTS` の 5 件は**全件無更新で通過**した。web UI も無変更（採番のみ）。
- **検証:** pytest **1033 passed / 30 skipped**（+4 = 件数・入力の明示性・段 D の判別・SVG と manifest の突き合わせ）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings。**git 管理セッションが独立に再現した**: 生成器を再実行して `git status` が空（220 件バイト一致）、`git archive` の除外、CI ガードの発火と復元。新規テスト `test_render_reference_inputs_are_fully_explicit` は生成器の literal を Pydantic の実フィールド集合と突き合わせるので、**schema にフィールドが増えれば落ちる**（固定し忘れが自動で露見する）。実装レポートは `no-git-sync/fable5/claude_code/tasks/codex-reference-corpus-result.md`。
- **残り（Phase 2〜5、未着手）:** Edition ID を rh3 へ（`render_build_number` と `vary_seed` を外す。rh2 は legacy 保持）／ ddl corpus（`a_expand` / `b_coerce`）と `ddl_engine_version` / `ddl_version` の新設／ `stage1_prompt_digest` / `stage2_prompt_digest` ／ 再描画時の版差表示。**全 Phase を通じて `render_engine_version` は 10 のまま**でなければならない。

### v2.4.5 — 作品エディションID を rh3 へ（build 番号と Score 側 seed を同一性から外す）（Build 695、2026-07-24）

- **何が壊れていたか:** rh2 は payload に `render_build_number` を含んでいた。build 番号は `web/BUILD_NUMBER` の中身で、**UI だけの変更でも採番される**。つまり**描画が 1 バイトも変わっていないのにエディションIDが変わる**状態で、偽の差分を生んでいた。engine 10 に対し build は 689 まで進んでおり、描画と無関係に数百回動いている。
- **経緯:** v1.25 で `render_build_number` は来歴として導入され、v1.60 で **engine 版の採番規律がまだ無かったため保険として** hash へ入った。その役割は v1.99 以降 `render_engine_version` が引き継いでいる。保険はもう要らない。
- **rh3 の定義:** payload は `score` + `render_seed` + `render_engine_id` + `render_engine_version` + `render_color_catalog_id` の 5 つ。**`render_build_number` と `vary_seed` を外した。** `vary_seed` は Score を作る側の seed で、**Score が違えば ID も違う**ため冗長である。canvas aspect は `_score_with_canvas` が render 前に適用して保存 score へ焼き込まれるので、個別には足していない。
- **`render_build_number` は残す。** カラム・保存・返却経路とも無変更。**来歴として価値があり、同一性の定義に入れる価値がない**、という切り分けである。
- **rh2 は legacy として保持し、再計算しない。** 計算経路は `_legacy_render_hash_for_item` として残した。保存済みの `rh2:` 行はそのままで、破壊的 migration は行わない（既存履歴の 64 桁 hex hash を legacy として残したときと同じ扱い）。**`rh2` と `rh3` は別の hash 空間であり、突き合わせて同一性を判定してはならない。** 起動時の backfill（`db.py:484`）は `render_hash` が空の行にだけ rh3 を書き、既存の rh2 行には触れない。
- **挙動は変わらない。** `render_hash` を**等値比較している経路は server に存在しない**（保存・index・表示のみ。web 5 ファイルと `cli.py` も末尾 4 桁の表示だけ）ことを事前調査で確認済みで、本改修でも判定経路を新設していない。`render_hash_short` も無変更。
- **直列化は既存のまま。** `_canonical_json`（`sort_keys` + 区切り詰め）と `_canonical_seed`（`int()` 化）を流用し、新しい正規化を作っていない。これにより文字列 `"12345"` と整数 `12345` が同じ rh3 になり、**別のインストールでも同じ値**が出る。
- **期待値は git 管理セッションが先に実測して契約へ埋め、実装はそれに一致させた**（[[参照コーパス先出し]]の型）。基準 `rh3:1f28ff5586ca6047…` に対し、**外したフィールドで基準と同一になる 4 件**（build 変更 / `vary_seed` 変更 / 両方同時 / 文字列 seed）と、**残したフィールドで別値になる 4 件**（`render_seed` / カタログ / `render_engine_version` / 2\*\*63+1 seed）を digest で固定した。「違う値になった」では受け入れない条件にしてある。
- **不変:** render engine version 10 のまま。renderer / stroke_engine / Score schema / coerce / DDL 解釈は無変更で、**参照コーパス `server/reference/render-engine-10/` は再生成しても差分ゼロ**。`MATERIAL_NONE_SEED_DIGESTS` 5 件も無更新で通過。web UI は採番のみ。
- **検証:** pytest **1038 passed / 30 skipped**（+5 = 基準値・外したフィールド・残したフィールド・legacy rh2 の存続・backfill）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings。**git 管理セッションが独立に再現した**: 契約の 12 個の digest を実装から計算し直して全件一致、SQLite の実 DB に rh2 行と NULL 行を並べて backfill を走らせ、**rh2 行が無変更・NULL 行に rh3 の基準値**が入ることを実測。実装レポートは `no-git-sync/fable5/claude_code/tasks/codex-reference-corpus-result.md`。
- **残り（Phase 3〜5、未着手）:** ddl corpus（`a_expand` / `b_coerce`）と `ddl_engine_version` / `ddl_version` の新設／ `stage1_prompt_digest` / `stage2_prompt_digest` ／ 再描画時の版差表示。

### v2.4.6 — 版画としてのエンジン（SPEC に思想と層マップを据える）（Build 696、2026-07-24）

docs のみ。コード・描画・API は無変更で、`render_engine_version` は 10 のまま。

- **設計原則に 7 番目を加えた（両 SPEC）:** **「エンジンは後戻りしない」**。
  版木を彫り進めるように描画エンジンは一方向にしか進まず、過去の版をシステムとして保持せず、選び直せるようにもしない。
  **残るのは刷り上がった作品（保存済み SVG）であって、彫る前の版木ではない。**
- **`SPEC.ja.md` §15.5 / `SPEC.md` §12.2「決定的な層と非決定的な層」:** パイプライン 9 層について
  実体・決定性・LLM 呼び出し数・対応する版を 1 枚の表にした。**決定的な層は隣り合っていない**
  （Stage 1.5 と coerce のあいだに Stage 2 の LLM が挟まる）ため、「DDL から Score まで」を 1 本の基準線にはできない。
  **LLM の層に版を与えない理由**も明記した — 版数は「同じ版なら同じ結果」を含意するので、
  それが成り立たない層に置くと嘘になる。代わりに prompt digest で「入力条件が違った」だけを記録する。
- **§15.6 / §12.3「版と同一性 ID」:** `render_engine_version` 10 / `ddl_engine_version` 1 /
  `ddl_version` 1 / Score `version` 0.1.0 / `APP_VERSION` / `web/BUILD_NUMBER` を
  **名前空間の違いが分かる形**で一覧にし、それぞれ「上げる条件」を書いた。
  `ddl_*` の 2 つは実装が続く前提で先に記載した（作者裁定 2026-07-24）。
  rh3 が `render_build_number` と `vary_seed` を含まない理由もここに集約した。
- **§15.7 / §12.4「参照コーパスによる世代比較」:** v2.4.4 の記述を発展させ、
  **世代をどう比べるか**を明文化した。版が上がるとき新しいディレクトリを作り、
  動いたケース ID だけを `changed_from_previous` に列挙して**その出力の実物だけを保存する**。
  「engine 11 でケース X はどう描かれるか」は**最後に X が動いた版**を辿れば機械的に答えられる。
  **ディレクトリの数が、そのままその層が何回変わったかの記録になる。**
- **§15.8 / §12.5「エンジンは後戻りしない（版画としての実装）」— 本改訂の核:**
  Replay は常に最新で行い、記録された版は来歴であって再描画の入力ではない。
  当時のエディションの再現は**保存済み SVG の返却で担保**し、再描画では担保しない。

  > 彫りは進む。版木は一方向にしか変わらない。刷り上がった作品は残るが、**彫る前の版木には戻れない**。
  > アプリケーション自体を一つの作品として考えるなら、この実装になる。

  作品は**刷り**、エンジンは**版木**。両者を混同して過去の版木を倉庫に取っておくことをしない、という選択である。
  **その代償として engine 1〜9 の出力は失われた**（コードも出力も残っていない）。
  だからこそ現役のうちに刷りを取る — **コーパスとは、彫り進める前に取る校正刷りである。**
  **版数だけを記録して出力を残さないのは、彫った日付だけを書いて刷りを捨てるのに等しい。**
- **README 日英に「版画としてのエンジン」節を新設:** 上記のエッセンスを読み物の密度で。
  設計原則にも 7 番目を追加し、コーパスが 220 ケース（10 道具 × 8 図形を基盤に揺らぎ・塗り・
  キャンバス比率・境界値を加えたもの）であること、CI がバイト一致を守ること、
  第 1〜9 世代が失われている事実を書いた。
- **検証:** 記載した数値は実装と突き合わせた（manifest の cases = 220、段 A = 80 = 10 道具 × 8 図形、
  `render_engine_version` = `"10"`）。コードは 1 行も変えていないため pytest / cli / ruff は v2.4.5 と同一。

### Android `2.0.0-android.1` — 描画コアが render engine 10 へ到達し 11 まで追随、Stage 1.5 は変奏まで（Phase 1〜3b・2h、android Build 148077〜148082、2026-07-23〜24）

**記載方針**: Android の移植は段ごとに版を起こさず、**engine 10 到達をもって 1 件にまとめる**（web/server とは版の名前空間が別で、`android/VERSION` / `android/BUILD_NUMBER` が正本）。以下は Phase 1 から 2f までの通し記録である。

- **到達点:** `DefaultSvgRenderer.kt` の `render_engine_version` が **`"2"` → `"10"`**。web/server の engine 10（v2.3.1 時点）と同じ描画機構が端末内で動く。`android/VERSION` は `1.48.0-android.1` → **`2.0.0-android.1`**（engine 10 到達時に 2.x とする作者裁定）。**約 2.5 か月・44 版ぶんの遅れを解消した**。
- **版の申告を最後まで動かさなかった（作者裁定）:** 部分移植の途中で中途の版を名乗ると render hash 経由で履歴互換が壊れるため、**engine 10 の全体が揃うまで `"2"` を申告し続け、2f 完了と同じコミットで初めて `"10"` にした**。
- **Phase 1 / 1.5（merge `89f3c9b`、Build 148069）:** Score schema JSON に cloudform / burin / drypoint / mode・carve_depth / grid / at・relation・surface を追加し全オブジェクトへ `additionalProperties:false`、coercer を追随、`rope` を除去、Edition ID の `rh2` と記述ハッシュ `dh1` を移植。
- **Phase 2a / 2a′（merge `d5dff1b`、Build 148071）:** 揺らぎの演奏（white / perlin / pink / wave）。
- **Phase 2b / 2b′（merge `9bdfdd5`、Build 148073）:** engine 7 の比例系。振幅・滲み・分割数・材質強度を絶対 px から `canvas.unit` 相対へ。
- **Phase 2c（merge `651b4ab`、Build 148074）:** `stroke_engine.py` 438 行を `ServerStrokeEngine.kt` へ移植。
- **Phase 2d（merge `3f9538c`、Build 148075）:** 線の筆致化（`stroke-engine-v1`）。
- **Phase 2e（merge `1be5229`、Build 148076）:** 閉図形の輪郭を `contour-stroke-v1` の帯へ。
- **Phase 2f（merge `1c8d22d`、Build 148077）:** 塗り（`fill-stroke-v1`）・面のハッチ（`surface-stroke-v1`）・弧（`arc-stroke-v1`）を 1 段で移植。走査線切断を全図形種別へ、弧は両端点固定の契約を同期、材質輪郭へ `class="material-outline"`。
- **移植を成立させた方法 = 参照コーパスの先出し:** server 側で期待値を実測した JSON / SVG を
  `android/app/src/test/resources/server_reference/` に置き、実装セッションへ**先に渡した**。SVG の class が `contour-stroke-v1 controls-62 events-1` のように**制御点数・イベント数を数値で持つ**ため、バイト一致でなく構造一致を機械判定できる。`05_circle_rotring.svg` は class を**持たない**ことを仕様として置いた（作らないことの固定）。
- **踏んだ罠（記録）:** ① `_hash_to_unit` は `hash01` のラッパーではなく**独立構成**（salt なし・先頭 8 バイトを符号付き little-endian int64・`2**63` で除算）で、これを取り違えると揺らぎ全種がずれる ② **seed は符号なし 64bit**（`struct.unpack("<Q", ...)`）で、実 seed の約半分が 2^63 を超える。Kotlin の `Long` では負に印字され、seed を鍵にするハッシュが全部ずれる ③ ハッチ本数 `range(-count // 2, ...)` の floor 除算（Kotlin の `-73/2` はゼロ方向丸めで 1 本ずれる）。いずれも**判別力のあるケースをコーパスに入れて初めて捕まった**。
- **検証:** `gradle :app:testDebugUnitTest --rerun-tasks` を main で独立実行し **44 件 / failures 0 / errors 0**（`app/build/test-results/testDebugUnitTest/*.xml` から自力集計）。参照 SVG 10 件すべてで class 属性列と要素数が一致し、うち 4 件（`03_square_filled` / `04_arc_crayon` / `06_surface_hatch` / `10_arc_wave`）は `<path d>` が**文字列完全一致**。`05_circle_rotring` はストローク帯を持たないことを否定テストで固定。
- **不変:** 変更は `android/` のみ。server / web / cli / shared は無変更で、**web/server の描画結果・`APP_VERSION` / `web/BUILD_NUMBER` は動かしていない**。pentala 反映も不要。
- **2f の申し送り（2g で処理済み）:** ① テストが渡す `colorCatalogId = "sumi"` は**存在しないカタログ ID**（実在は `default` ほか 11 種）で、10 箇所が未是正のまま残っている。描画結果は色に依存しない比較なので engine の版には影響しない ② 未知カタログ ID の扱いが server（HTTP 422）と Android（黙って `default` へフォールバック）で**非対称** ③ `ANDROID_SPEC` の 2f 節が「全 10 参照 SVG で `path d` 完全一致」と過大に書かれている（実際は上記のとおり 4 件）ほか、engine 10 到達に触れていない。2g では雲形・touching・v1.94 双弧修正を扱う。
- **Phase 2g / 2g′ / 2g″（merge `8819729`、Build 148080）＝ Phase 2 完了:** 雲形の輪郭生成（1/f 基底 + 49 点閉 Bezier + くびれの変位）・`touching` の劣弧再構成・**region → relation の解決順序（v1.94 の双弧修正）**を移植し、2f の申し送り 3 件も片づけた。**engine は `"10"` のまま**で、`android/VERSION` も `2.0.0-android.1` を維持する（描画機構が増えたのではなく、engine 10 の内側を埋める作業だったため）。
- **2 度差し戻した。その 2 回で見つかった欠陥は、どちらも「関数は正しいのに出力が違う」形だった:**
  - **2g 初回**: 雲形が **server に存在しない weight 表**をインラインで新設していた（正しい表は 2c で `ServerStrokeEngine` へ移植済みなのに呼んでいなかった）。検証は**同じ関数を 2 回呼んで比べる恒真テスト**で、touching・双弧には検査が 1 件も無かった。**参照コーパスを先出ししなかった唯一の段**で、この失敗が起きた
  - **2g′**: 法線の向きの条件が server（`cloudform.py:229`）と逆で、くびれの変位が**内側でなく外側へ**出ていた。全 14 ケースが最大 0.03 ずれていたが、**テストの許容誤差が 0.05** で、どのケースもその幅を超えられなかった（10 道具間の輪郭のひらきは 0.0013 しかない）。**恒真テストではなくなったが、判別力はゼロのままだった**
  - **2g″**: 上を是正したうえで、もう 1 件が出た。**雲形の呼び出し側が seed を素で渡していた**（server は `_seed_for_instruction(ins, seed)` を渡す）。**関数単体の parity はこの欠陥を通しても緑のまま**で——コーパスのテストは導出済みの seed を直接与えるため——`11_cloudform_pencil.svg` の `<path d>` 比較だけが捕まえた
- **この 3 段が残した規律**: ①**期待値は渡す前に測って契約へ埋める**（`renderer_cloudform_and_relations.json` = 道具ごとの `energy_lateral`・輪郭 14 ケース・劣弧再構成・Score の解決順序 4 件）②**許容誤差は判別幅とセットで決める**（「1e-9」とだけ書かず「道具間のひらきが 0.0013 しかないので 1e-9 が要る」まで書く）③**関数単体の parity だけを条件にしない。出力側の判別テストを必ず併記する**——2g″ の 2 件目はこれが無ければ通っていた
- **検証:** `gradle :app:testDebugUnitTest --rerun-tasks` を main で独立実行し **54 件 / failures 0 / errors 0**（XML 自力集計）。`cloudform_contour` 14 ケースの全 49 点が **1e-9 以内**かつ `path_d` **文字列一致**、参照 SVG `11`〜`14` の `<path d>` も**文字列完全一致**。`14_region_then_relation` は region `[0.55,0.55,0.95,0.95]` に対し最終 center が **region の外**（x = 0.35）に着地することで v1.94 の順序を固定している（`relation` は解決後も却下後も `null` になるため `center` でしか判定できない）

- **Phase 3a（merge `642a476`、android Build 148081）＝ Stage 1.5 展開層の中核:** 展開フィルタ本体（変奏・添景・focus・プラグイン展開）を移植した。`ddl` と `context_text` の使い分け、**`vary_seed` は `context_text` にだけ効く**（`variation_seed` とは別物）ところまで含む。**3b〜3d 用の引数は受け取るところまで作らせ、無視していることをテストで明示させた**（後段で「引数はあるが読んでいない」が無言で残らないように）。期待値 `ddl_expand.json` 39 ケースは**契約に先出し**してある。`A-*` 15 件は server 正本 `server/reference/ddl-engine-1/a_expand/` と同じ入力で、**末尾改行 1 文字を除いて出力もバイト一致**する（照合スクリプトは `rstrip("\n")` が要る）。検証: `testDebugUnitTest --rerun-tasks` を XML 自力集計で **58 件 / failures 0 / errors 0**（ベースライン 54 + 新規 4）、契約 §5 の 7 ケースが `assertEquals` で完全一致。変更は `android/` 6 ファイルのみ。**`render_engine_version` は `"10"` のまま**で `android/VERSION` も `2.0.0-android.1` を維持する。
- **engine 11 で parity fixture が古くなる（申し送り。Phase 2h で処理済み）:** web/server が v2.4.8 で `path d` を`.3f` から 6 桁固定へ変えたため、`server_reference/` の SVG 比較は**そのままでは全滅する**。Stage 1.5 の Phase 3b〜3d とは別軸なので、**描画層の追随は Phase 2h として別契約**にした。
- **Phase 2h（merge `eeb9bd7`、android Build 148081 据え置き）＝ マスターグリッドへの追随・engine 11:** 書き出す数値をすべて小数 6 桁固定のグリッドへ載せ、`render_engine_version` を **`"10"` → `"11"`**。**幾何は 1 行も変えていない。変えたのは数値を文字列にする箇所だけである。** `ServerRendererGeometry` に `MASTER_GRID_DECIMALS = 6` を宣言し、同一実装の重複だった `fmt3` を削除、組み上げた SVG に対して `applyMasterGrid` を一度だけ当てる（server の `renderer.py::_apply_master_grid` と同じ構えで、除外は `version` / `class` / `id` の 3 つ）。**Kotlin の `Double.toString()` は素で埋め込むと `1.0E-5` のような指数表記を出す**ため、この保険が無いとそこだけグリッドから外れる。
- **server 側の癖まで写した 2 箇所:** ① `class="hatch-spacing-…"` は識別子であって座標ではないので **3 桁のまま**（`renderer.py:2190` と同じ）② 雲形の輪郭 `closedCatmullRomPath` は **server の `cloudform.py:134,143` が内部で `.3f` に量子化している**ため、局所の 3 桁整形を保ったうえで `applyMasterGrid` に 6 桁へ整えさせる。**ここを 6 桁で直に書くと server と 1 桁ずれる。**
- **判別テスト 3 本を新設し、3 本とも「意図したテストが落ちる」ことを摂動で確認した**（git 管理セッションが受け入れ時に独立実行）: ① `MASTER_GRID_DECIMALS` を 6 → 5 にすると `testEveryEmittedNumberSitsOnMasterGrid` が落ちる ② 整数もグリッドに載せると `testIntegersRemainIntegers` が落ちる ③ `Locale.US` を外すと `testLocaleIndependence` が落ちる。**着手時点で赤だった 12 件はすべて緑になり、その 12 件の assert は 1 つも書き換えていない**（緩めて通した箇所が無いことの証明）。
- **整形の忠実性を実測した:** `String.format(Locale.US, "%.6f", v)` と、二進値そのものを見る `BigDecimal(v).setScale(6, HALF_EVEN)`（＝ Python の `f"{v:.6f}"` と同じ意味）を 0〜1000 の乱数 **200 万件**で突き合わせ、**不一致 0 件**。JVM の整形が Python と食い違いうる懸念（短縮表記経由の丸め）は、6 桁・この範囲では現れない。
- **検証:** `gradle :app:testDebugUnitTest --rerun-tasks` を main で独立実行し **61 件 / failures 0 / errors 0**（XML 自力集計。ベースライン 58 + 判別 3）。`android/VERSION` は `2.0.0-android.1` 据え置き、`android/BUILD_NUMBER` も `148081` のまま。変更は `android/` のみで、**web/server の描画結果・`APP_VERSION` / `web/BUILD_NUMBER` は動かしていない**。pentala 反映も不要。
- **Phase 3b（merge `467877f`、android Build 148082）＝ Stage 1.5 変奏の追随:** `variation_amplitude` と `variation_seed` が**両方揃ったとき**だけ DDL 本文と `variation_report` を決定的に変換する変奏層を移植した。`VariationPlan`・強度 3 段・7 軸（`type_swap` / `count` / `touch` / `focus` / `color` / `composition` / `type_family`）と `buildVariationPlan` / `effectiveVariationPlan`（実際に出力が動く軸だけを採る）/ `variationMovedAxes` / `resolveFocusId` を server の `ddl_expander.py:676-1040` から写した。**焦点 `focus` もこの段**（`_resolve_focus_id` が変奏プランの一部のため）。
- **契約に着手時点を先出ししてあった:** 16 ケース中、変奏未実装でも通る 2 件（`amplitude-only` / `seed-only` = 基底と同一）を除く **14 件が DIFFER の状態**から始めた。**変奏は DDL を短くしうる**（`type_family` の削減で 24 文字へ縮む 4 件があり、「足すだけ」の実装では通らない）。**16 件すべてが `variation_report` を持つ**ので、テストは output 完全一致に加えて `moved_axes`（軸・from・to）と `resolved_focus` を全件照合する。
- **git 管理セッションが独立に再現した受け入れ条件:** ① `testDebugUnitTest --rerun-tasks` を `feat/android-phase3` と main の両方で **62 件 / failures 0 / errors 0**（XML 自力集計。ベースライン 61 + 新規 1〔16 ケース内包〕）② **判別力を摂動で確認**——`java.lang.Long.toUnsignedString` を素の `toString` に戻すと落ちる（2^63 以上の seed 2 件が効いている証拠）／`moved_axes` の `axis` を汚すと**出力が正しいままでも落ちる**（report 照合が output とは独立に効いている証拠。契約が心配した「切り詰めるだけの実装」を、output+report の 11 種の相違で弾ける）③ 出力長が同じ focus 2 件（`upper_left` / `upper_edge` = 92 字）も本文の中身で判別される。**変更は `android/` のみ 6 ファイル**で、`render_engine_version` は **`"11"` のまま**、`android/VERSION` も `2.0.0-android.1` を維持。
- **申し送り:** Phase 3c（添景）→ 3d（プラグイン・歳時記）が残り。3c は `tenkei` 三段と `_cap_category_plan`、期待値は `ddl_expand.json` に先出し済み（`A-tenkei-*` 3 + `B-tenkei-*` 9）。

### v2.4.7 — 決定的な DDL 層を凍結する（DDL 参照コーパスと `ddl_version` / `ddl_engine_version`）（Build 697、2026-07-24）

**v2.4.4 で描画の出力を凍結したのと同じことを、パイプラインの手前側で行った。** 決定的な層は
描画だけではない。プラグイン展開・Stage 1.5 の展開と変奏・coerce も、同じ入力と同じ seed から
必ず同じ結果を返す。ここに初めて版と参照コーパスを与えた。

- **決定的な DDL 層の参照コーパスを新設:** `server/reference/ddl-engine-1/`。29 ケース、生成器は
  `server/scripts/gen_ddl_reference.py`。**A（展開）と B（補正）を連結していない**のが設計の要点で、
  A は `expand_intermediate_ddl` の出力（DDL 全文）15 件、B は `coerce_score` の出力
  （補正後 Score 全文 + `branch_report`）14 件。**B の入力 Score は生成器内の literal** であり、
  A の出力を渡していない。連結すると展開側の欠陥が補正側の欠陥を覆い隠す。
- **なぜ 2 本に分かれるか:** 決定的な層は隣り合っていない。Stage 1.5（DDL→DDL）と
  coerce（Score→Score）のあいだに Stage 2 の LLM が挟まるため、「DDL から Score まで」を
  1 本の基準線にはできない（SPEC §15.5 の層マップ）。
- **`ddl_version` と `ddl_engine_version` を導入:** ともに **`1`** から。`layer_versions.py` が正本。
  **`ddl_version` は DDL 言語仕様（文法・キーワード）の版**、**`ddl_engine_version` は決定的変換層の版**で、
  名前空間が別である。**SPEC §15.6 が v2.4.6 で先に書いた値と実装が一致した。**
- **作品への記録:** 新規生成の compose / paint / render-score の応答と履歴・保存 artifact に
  両方が乗る。history テーブルへは nullable の列を非破壊 `ALTER TABLE` で追加した。
  **既存行は backfill しない** — 記録の無い作品の版数を推測して埋めることは、来歴の捏造にあたる。
- **エディション ID は不変:** `ddl_*` は **rh3 の payload に入れていない**。描画が 1 バイトも
  変わらないのに ID が動くことを避けるという v2.4.5 の判断をそのまま守る。
- **判別力の設計:** `ddl` 引数の有無で同じ Score が **発火 0 → 6・instruction 1 → 3** に変わり、
  `tenkei` 三段（auto / sparse / none）で **発火 6 / 4 / 3・instruction 3 / 2 / 1** に分かれる。
  発火しないケース（線 40 本・雲形・presence のみ）も入れて、**「何も起きない」ことも固定した**。
  `branch_report` は**全体のキー集合を固定せず**、ケースごとの発火キー対応だけを固定している
  （全体を literal にすると分岐を足すたびに壊れ、実質の検査にならない）。
- **CI:** `reference-corpus.yml` に `ddl-engine` job を独立して追加し、render job の対象は
  `render-engine-10/` に限定した。**検査が実際に落ちることを 2 通りで実証した** — 実装セッションは
  `coerce.py`（B 側）に観測用の分岐を足して、検証側は `ddl_expander`（A 側）の返り値を摂動させて、
  いずれも生成器が exit 1 と
  `DDL corpus changed without an identity-field change; bump the appropriate version instead of rewriting a frozen corpus`
  で停止することを確認している。
- **描画は不変:** `render_engine_version` は **`10`** のまま。render corpus を再生成して
  220 件すべてに差分が無いことを確認した。
- **検証:** pytest **1043 passed / 30 skipped**（v2.4.6 の 1038 + 新規 5）、cli 68 passed、
  ruff clean、`npm run check` 0 errors / 2 warnings。両コーパスを再生成して
  `server/reference/` に差分ゼロ。
- **積み残し（記録）:** 歳時記（`saijiki.py`）は決定的な層から参照されておらず、
  流入先は Stage 1 のプロンプト（版を持たない層）である。したがって**歳時記に語が増えても
  このコーパスは動かない**。語彙の追加は `ddl_version` を上げる事象だが、**それを機械が
  検出する仕組みはまだ無い**（Phase 4 の `stage1_prompt_digest` が半分を担う）。

### v2.4.8 — 演奏出力にマスターグリッドを宣言する（render engine 11）／プロンプト来歴の digest（Build 698、2026-07-24）

#### A. render engine 11 — 書き出す数値をひとつのグリッドへ載せる

- **発端は CI の 8 連続失敗:** `reference-corpus` ワークフローの `render-engine` job が、追加以降**一度も緑になっていなかった**。原因は、**凍結コーパスが作者の macOS で焼かれ、CI は Linux で再生成する**こと。`math.sin` の値が両者で 1 ulp 違い（`344.12754953531663` / `344.1275495353167`）、`points` / `cx` / `cy` が **svgwrite へ素の float のまま渡って 17 桁で出る**ため、そのまま文字列差になっていた。220 件中 **81 件**が該当、**構造差 0 件**、最大相対差 **2e-16**。pentala（Ubuntu x86_64）で同じ失敗を再現して確定させた。
- **測った 3 つの数字:**
  - **プラットフォーム雑音の床 = 小数 10〜11 桁。** 桁を変えながら 220 件を突き合わせると、10 桁までは Mac/Linux が完全一致し、11 桁で 4 件、13 桁で 80 件が割れる。**17 桁のうち再現性のある情報は 10 桁まで**だった
  - **座標グリッドは不揃いだった。** 描画幾何の整形は `.1f` が 1 箇所・`.2f` が 9 箇所・`.3f` が 7 箇所、そこに生の 17 桁が混じる。**マスターの目盛りが場所によって 1e-4 から 1e-19 までばらついていた**
  - **形の忠実度はキャンバス比 2.2e-4。** ストロークは曲線でなく**直線の連なり**で出ており（`L` が 77,666 個に対し `C` は 490 個）、セグメント長の中央値はキャンバス幅の 2.07%。半径 240 単位の円で弦の矢は 0.224 単位＝**ラスター換算で約 4.5K 相当**
- **したがってこれは解像度を削る変更ではない。** 桁は必要量の 200 倍あり、実効解像度を決めているのは標本化のほうである。**バラバラの桁をひとつの宣言へ寄せる**変更であり、描画幾何は `.1f`〜`.3f` から一律 6 桁へ**上がった**。
- **`master_grid.py` が唯一の宣言:** 小数 6 桁固定＝1000 単位キャンバスでキャンバス比 **1e-9**。雑音床より 4 桁上、物理側の限界より 3 桁下（100m の壁へ引き伸ばして 100nm＝可視光の波長より細かい）。
- **`.6f` 固定・末尾ゼロは詰めない（作者裁定）:** 理由は容量ではなく**検査可能性**。桁が固定なら成果物のどの数値も `-?\d+\.\d{6}` に一致し、**グリッドに載っていることを正規表現 1 本で機械検査できる**。詰めると `695.45787` が 6 桁グリッドの産物か生 float かを出力から見分けられず、「丸めてから詰めた」という手順を信じる形になる。対価は容量 +11.6%（2.48MB → 2.77MB）。
- **強制は出力の単一地点で行う:** `render()` の返り値に対して一度だけ当てる。svgwrite の呼び出し箇所は 48 あり、**一つずつ直す方式は漏れが黙って残る**（`version="1.1"` と識別子の `class` / `id` のみ除外）。
- **描画は変わっていない:** 220 件すべてで**数値の個数が一致**し、**どの数値も 5e-4 を超えて動いていない**（旧 `.3f` の半幅ちょうど）。golden 6 件も同じ性質を確かめてから採り直した。
- **engine 10 のコーパスは残す（作者裁定）:** 10 → 11 の差分が「**桁だけが変わり、形は変わっていない**」ことの実物の証明になる。engine 10 は **macOS でしか再現できない**ため CI の検査対象から外れる。その旨を `server/reference/README.md` に明記した。**参照コーパスの初めての実用**である。
- **CI:** 検査対象を `server/reference/` の全体へ広げた。版を上げると新ディレクトリが untracked のまま残って CI が赤になる＝**凍結物のコミットを強制する**挙動になる（意図どおり。README に記載）。
- **検査は 2 本、どちらも落ちることを確認した:** ① 新規に演奏した出力に対し 3 プロファイル分（`editable` / `compat` / `display`）② 凍結済み 220 件の全体。後者は 1 ファイルの 1 桁を削って実際に落ちることを確かめてから戻している。
- **再現性の確認:** macOS arm64 と Ubuntu x86_64 で 220 件 + manifest が**バイト一致**。生成器を 2 回回して冪等であることも確認した。

#### B. プロンプト来歴の digest（参照コーパス Phase 4）

- **Phase 3 が残した穴を塞ぐ:** 歳時記（`saijiki.py`）は決定的な層から参照されておらず、流入先は **Stage 1 のプロンプト＝版を持たない層**である。したがって歳時記に語が増えても DDL コーパスは動かず CI も落ちない。`stage1_prompt_base_digest` がその唯一の検出手段になる。
- **フィールドは 4 つ。** `stage2_prompt_base_digest` は**作らない**（Stage 2 はツールスキーマ込みでないと意味を持たないため）。
- **判別テスト 3 本はいずれも恒真ではない:** ① 実送信 digest が入力で**動く**ことと base が**動かない**ことを同時に主張 ② 上書き経路の base が定数と**不一致**であること（モジュール定数から計算していない証明）③ schema の description 変更で combined が動き、`SYSTEM_PROMPT` 単独は**動かない**こと（なぜツールスキーマが要るのかが検査に刻まれる）。
- **既存行は backfill しない。** nullable 列を非破壊 `ALTER TABLE` で追加しただけで、記録の無い作品の版数は推測して埋めない。

#### C. 畳んだもの・積み残し

- **`server/pyproject.toml` の `description`**（`2308059`）: uv の雛形が残っていたので差し替えてあったもの。挙動は変わらないため単独では採番していなかった。
- **Android の追随が要る:** engine 11 で `path d` が `.3f` から 6 桁固定へ変わるため、**Android の parity fixture は全滅する**。Stage 1.5 を扱う Phase 3b〜3d とは別軸なので、**描画層の engine 11 追随は Phase 2h として別契約に起票する**。
- **検証:** pytest **1062 passed / 30 skipped**（v2.4.7 の 1043 + Phase 4 の 17 + engine 11 の 2）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings。

### v2.4.9 — 再描画時の版差表示（参照コーパス Phase 5 完結）（Build 705、2026-07-25）

**参照コーパスとレイヤー版数の親契約（全 5 段）がこれで完結する。** engine 10 → 11 の桁だけの差を実物で示せるようになった凍結コーパスを、**利用者の画面でも「この作品はどの版で描かれ、いま見ているのは何版か」を言葉で見せる**段。描画コア・stroke engine・Score schema・`server/reference/`・各版数（`render_engine_version="11"` / `ddl_version="1"` / `ddl_engine_version="1"`）はいずれも据え置きで、**表示だけを足した**。

- **現行レイヤー版の取得口を `GET /api/info` に開けた:** 認証不要のこのエンドポイントへ `render_engine_id` / `render_engine_version` / `ddl_version` / `ddl_engine_version` の 4 フィールドを追加した。値は定数直書きではなく `current_render_engine()` と `DDL_VERSION` / `DDL_ENGINE_VERSION` から取る。テストは **engine 実体を monkeypatch すると `/api/info` が追随する**ことまで固定した（定数直書きなら落ちる形）。既存の `name` / `version` / `build_number` / `developer_mode` は維持し、`developer_mode` の真偽にかかわらず版フィールドを返す。
- **生成情報ドロワーへ「DDL 仕様 / 変換層」を足した:** 表示元は選択履歴または現行結果に記録された `ddl_version` / `ddl_engine_version`。欠損時は**「記録なし」と表示し値を推測しない**。DB 1704 行のうち engine 版の記録なしが 590（35%）ある実データに対して、「記録が無い」と「版 1」を**画面上で区別する**ための表示である。
- **再現比較モーダル（新規 `ReplayComparisonModal.svelte`）:** 再現ボタンは保存済み Score を `/api/render-svg` へ送って現行 Renderer で描き直し、**保存済み SVG（オリジナル）と描き直し SVG（現行）を左右に並べる**。各作品の上に記録 Renderer 版と現行 Renderer 版を出し、版が違えば「この作品は engine 10 で描かれました。いま画面にあるのは engine 11 による描き直しです。」（英語併記）を**作品の外・比較グリッドの上**に置く（SVG へ重ねない）。記録版と現行版が同じ場合、`/api/info` 失敗で現行版が不明な場合、履歴から開くだけの場合は版差通知を出さない。
- **呼び出し元へ戻す:** 履歴管理／作品タブ／系譜タブのどこから開いても、閉じると元へ戻る。キャンバス下部バーの「生成情報」左隣へ再現ボタンを足し、`CanvasPanel` と `HistoryManager` の該当ボタンを `--btn-sm-*` 寸法トークンへ揃えた。
- **seed 欠損作品の暫定比較（作者追加指示）:** `render_seed` と `seed_text` の双方がない履歴も比較可能にした。**DB は書き戻さず、比較要求の間だけ固定 seed `0` を補完する**ので同じ作品を再度比較しても現行側は変わらない。モーダルに「Seed を補完した暫定表示（seed: 0）」と注記する。API が NULL 列を応答から省くため、**完全な履歴項目の判定は `render_seed` フィールドの有無ではなく保存済み `score` と `svg` の有無で行う**（この取り違えで Build 703 では下部バーの再現ボタンが無効だった。作者提供スクリーンショットで確認し Build 704 で修正）。
- **積み残さなかったもの（明示）:** 過去 Renderer の保持・選択・呼び戻しは実装していない。保存済み SVG は差し替えていない。既存履歴の版数・`render_seed` は backfill も書き戻しもしていない。`/api/render-svg` の SVG 本文応答は変えていない。web のテスト基盤は新設していない。
- **仕様は動いていないため SPEC は触っていない**（`SPEC.ja.md` §15.8 の実装であり、契約 §3.1 のまま）。
- **検証:** pytest **1063 passed / 30 skipped**（+1 = `/api/info` の版フィールド）、cli 68 passed、ruff clean、`npm run check` **0 errors / 2 warnings**（新規 `ReplayComparisonModal.svelte` を含む 217 files）、`npm run build` 成功。変更範囲は server 1 ファイル + test + web のみ。

---

### v2.5.0 — 演奏の脱・規則化と「暴れる」（render engine 12）（Build 706、2026-07-25）

**engine 11 までの演奏は、揺らいでいるように見えて周期的だった。** 幅のエンベロープは `max(0, sin(pi t))` の固定した山で、**どのストロークも中点でいちばん太く、左右対称に細っていた**。補正イベントは `sin((i % 5) * pi / 2)` で **周期 5 の反復**を打っていた。閉じた輪郭は継ぎ目がやせて中央が太る定型を持ち、材質アウトラインは等間隔の破線と等間隔の粒で描かれていた。engine 12 はこの 4 つをすべて seed 由来の低周波雑音へ置き換え、さらに**中心線そのものに長さ基準のジェスチャ**を足す。

- **エンベロープの脱・規則化:** `_edge_window(t) * _swell(t, seed)` へ置換した。`_edge_window` は端の 16% だけレイズドコサインで落ちる窓で、**中央に山を作らない**（端点が固定されている事実だけを表す）。`_swell` は seed ごとの低周波雑音で、**「どこがいちばん太いか」がストロークごとに動く**。閉じた輪郭には端点が無いので端の窓を掛けず、`_swell` だけを使う（`CLOSED_ENVELOPE_FLOOR` は削除。継ぎ目の偽のやせが消えた）。
- **補正イベントを長さ基準へ:** 標本番号の剰余 `i % 5` をやめ、seed ハッシュのキックにした。**標本数が変わっても質感が変わらない**。
- **中心線ジェスチャ:** `ToolGrammar` に 10 番目のフィールド `gesture` を足した。ストローク長に比例した振幅で中心線自体を低周波に振り、**曲がり・丸まり・自己の重なり**を生む。ペン幅で正規化される `energy_lateral` とは別の量である。端点は窓で固定され、決定性は seed が担保する。
- **材質アウトライン層:** ジェスチャ後の中心線へ追随させ（`<polyline class="material-outline">`）、破線は可変 mark/gap、オフセットは蛇行、粒は非一様な `t` にした。`rotring` の線は素通りさせる（機械の極）。
- **「暴れる」（wild）トグル:** 演奏の上限を外すスイッチを**作品全体に一つ**置いた（`WILD_GAIN = 3.5`）。**外すのは振幅の上限と自己交差の禁止だけで、端点の固定と決定性は ON でも保つ。** 生成時のパラメータとして `render_seed` の隣に記録し（`history.render_wild`、NULL = 記録前の作品で OFF と区別する）、再現に使い、**エディション ID `rh3` の材料に含める**。UI は InputPanel のトグル、日英の i18n 込み。変奏（Stage 1.5）とは層が違い、これは Renderer 層のノブである。
- **`rh3` の材料変更を版で吸収した:** `render_wild` を payload に足したので材料は変わったが、**同じ payload の中に `render_engine_version` が入っている**ため、旧材料の値は必ず `"11"` 以下を、新材料の値は必ず `"12"` 以上を含む。新旧が衝突しないので形式名は `rh3` に据え置いた。この論法は **engine 版を同時に上げたから成り立つ**ので、材料の追加だけを単独で行ってはならない旨を SPEC に明記した。
- **参照コーパス `render-engine-12/` を凍結（199 / 220 が変化）:** **21 件が動かず、その内訳がそのまま engine 12 の説明になっている**。`rotring` の 12 件はバイト一致した（揺れ項がすべて 0 で、脱・規則化が届く先を持たない＝**道具語彙の機械の極は同じ位置にある**）。`cloudform` の 9 件もバイト一致したが理由は別で、雲形は Catmull-Rom パスとして書かれ `stroke_engine` を通らず材質アウトライン層も持たない。**engine 12 が作った穴ではなく、engine 12 が露わにした穴である**（輪郭自体は道具ごとに違い、10 道具の digest はすべて異なる）。
- **「動いた分だけ保存する」規律を生成器に実装した:** README と SPEC §15.7 は以前からそう定めていたが、生成器は新規ディレクトリのとき無条件に全 220 件を書いていた。engine 11 は全件が動いたので**区別がつかなかった**。`gen_render_reference.py` に前版 manifest との digest 比較を入れ、`changed_from_previous` を実測で決め、**その ID の SVG だけを書く**ようにした。遡って実物を解決するテスト（`_resolve_svg`）と、**遡りが空振りしていないことを確かめるテスト**を追加した。
- **版を上げる条件に「演奏できる語彙が増えたとき」を足した（作者裁定）:** 新しい道具を足しても既存コーパスはその語を使わないので**出力が動かず CI は落ちない**。結果が変わるときだけを条件にすると、版を上げずに語彙を足せてしまい、「その語を演奏できる engine 12」と「できない engine 12」が併存する。**同じ版なら同じ結果、という版数の意味が入力の集合のほうで崩れる**ため、条件を拡張した（SPEC §15.6）。
- **積み残さなかったもの（明示）:** Android への追随は行っていない（engine `"11"` のまま）。てざわりへの「コンピュータ」追加は着手していない（設計の裁定のみ済み）。`cloudform` をストローク合成へ載せる修正は行っていない（事実として記録しただけ）。過去エンジンの保持・選択は実装していない（§15.8 のまま）。保存済み SVG は差し替えていない。既存履歴の `render_wild` は backfill していない（NULL のまま＝記録前と OFF を区別する）。
- **SPEC:** §13.4 に「暴れる」の節、§15.6 に版を上げる条件の拡張と `rh3` の材料の注記、§15.7 に engine 12 の実測（199/21 の内訳）を追記した。
- **検証:** pytest **1066 passed / 30 skipped**（+7 = engine 12 で再ベースラインした golden 6 件と、遡り解決の新テスト 1 件）、cli 68 passed、ruff clean、`npm run check` **0 errors / 2 warnings**（217 files）。再ベースラインした 6 件は `_swell` を 1e-6 だけ動かすと全件落ちることを確認した（判別力の実測）。コーパス生成器は 2 回連続実行で tracked 差分ゼロ。

---

### Android Phase 3d — 組み込み Nature プラグイン展開の追随（android Build 148083、2026-07-25）

**Stage 1.5 展開層の移植が Phase 3d で完了した。** Android の展開層は web/server と同じ入力に対して同じ文字列を返すようになり、**残る遅れは描画層（engine 11 のまま）だけになった**。

- **移植内容:** `NATURE_PLUGIN_RE`（`Nature.(風|うねり|無風|wind|undulation|stillness|calm)`）と `naturePluginTerms` によるタグ抽出、`dropNaturePluginSentences` によるプラグイン文の除去、`applyNaturePluginMacros` によるマクロ文の決定的挿入を `WebDdlExpander.kt` へ写した。**呼び出し順序は server 正本と同じ**（`_sanitize_placement_words` → `_avoid_gray_background` → `_apply_nature_plugin_macros`）。
- **語の対応:** 「風」/`wind` → 横の帯 + ゆっくり揺れる、「うねり」/`undulation` → 波打つ軌跡 + 大きくゆっくり、「無風」/`stillness`/`calm` → 揺らぎなし + 静止。**`stillness` があるときは他の語より優先し、風とうねりのマクロを出さない**（server と同じ分岐）。
- **検証:** `testDebugUnitTest --rerun-tasks` を XML 自力集計で **64 件 / failures 0 / errors 0 / skipped 0**（ベースライン 62 + 新規 2）。参照コーパス `ddl_expand.json` の 3 ケース（`A-plugin-enabled` / `A-plugin-disabled` / `B-plugin-instructions-present`）が `assertEquals` で完全一致し、**この 3 件の期待値は現行 server 実装で再計算しても一致する**（受け入れ時に照合）。恒真回避テスト（`enablePlugins=false` で出力が変わること）も併せて通る。
- **判別力の実測（受け入れ側）:** うねりマクロの文言を 1 語だけ変える摂動を入れると `WebDdlExpanderPhase3dTest` が `ComparisonFailure` で落ちることを確認した。**通っていること自体ではなく、落ちることを確認している。**
- **英語版 `ANDROID_SPEC.md` の退行を受け入れ時に修正した:** 実装セッションが英語版を**日本語版の内容で丸ごと上書き**しており（en と ja の内容 SHA が一致・英語 1848 行が消失）、マージ後に英語本文を復元したうえで Phase 3d 節を英語で追記した。両版の冒頭「追随状況」も現状（master は v2.5.0 / engine 12、Android は engine 11、展開層は 3d まで）へ改めた。
- **積み残さなかったもの（明示）:** engine 12 への描画層追随は行っていない（`render_engine_version` は `"11"` のまま）。葉プラグイン文書 `nature-leaves.inku-plugin.md` の読み込みと `saijiki.py` 相当は移植していない（作者裁定によりスコープ外・3e 以降）。`android/VERSION` は `2.0.0-android.1` のまま。web/server/cli/shared のコードは変更していない。
- **採番:** Android のみの変更のため `APP_VERSION` と `web/BUILD_NUMBER` は動かしていない（`android/BUILD_NUMBER` のみ 148082 → 148083、Gradle 自動採番）。
- **検証（master 側の退行確認）:** pytest 1066 passed / 30 skipped、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings（217 files）。

---

### v2.6.0 — てざわりに「コンピュータ」を足す（render engine 13）（Build 707、2026-07-25）

**11 番目の道具を足した。核は「手が震えない」ではなく「誤差なく反復する」。** 手は同じ値を二度出せない。計算機は同じ値しか出せない。**周期＝線に沿った方向の反復／格子＝空間方向の反復**で、同じ性質の 2 軸である。`rotring` との区別はここで立つ — **rotring は反復すべき揺れを持たない**（道具文法が全項 0）が、**コンピュータは揺れを持ち、それを正確に繰り返す**。engine 11 の対称エンベロープへの後戻りではない（engine 11 のそれは**選べない既定**、engine 13 のこれは**選べる語彙**。SPEC §15.8 と衝突しない）。

- **演奏（`stroke_engine.py`）:** `ToolGrammar` に `periodic` / `quantize` / `width_steps` を足した（既存 10 道具はすべて 0 で無改変）。`periodic` のとき雑音源を整数周期の正弦へ差し替え（energy は 5 周期 + 10 周期、gesture は 2 周期。**いずれも seed を引数に取らない**）、中心線の座標を `ストローク長 × 0.018` の格子へ丸め、幅を 4 段に落とす。**進行方向のジェスチャは 0 にする**（機械は前後に迷わない。残すと尖点が出て「破損」に見えた）。`wild` は `periodic` の道具に効かせない。
- **材質は「標本化の残り」（`raster-bleed`）:** 手の道具の材質層は**道具が線の脇に落とすもの**（黒鉛の粉、筆の毛）だが、計算機にはそれがない。**あるのは格子へ丸めるときに捨てた差である。** 標本ごとに丸める前後の差（残差）を取り、**残差が 0 でない標本にだけ**格子 1 セルの正方形をストロークの下に敷く。セルは**格子に丸めた座標**に置き、濃さは**残差に比例**する（セル半分で上限 0.45）。**幾何が「誤差なく反復する」／材質が「誤差を捨てた跡」を見せる。** seed を使わないので同じ図なら同じ跡が出る。**端点は意図へ固定され多角形の角は anchor で戻される**ので、そこには残差が無くセルも出ない（直線 41 標本中 39、四角 80 中 76、弧 62 中 60）。
- **材質は第 1 版から作り直した（作者目視による差し戻し）:** 最初の実装は「まっすぐな定規の線 + 全数同一の等間隔 dash」で、旧作 `rh2:9e991c…` の「直線の雨」を道具の性質として置き直す設計だった。実装して目視すると、**材質層が意図した始点→終点に固定される一方、演奏された中心線は最大 55.4px 離れる**（振れ幅 102.8px）ため、点線が線から切り離されて**独立した罫線**に見えた。**作者裁定「この点線には絵画上の意味がない」** で捨てた。代案の「格子ハロー」（量子化した輪郭を 1〜2 セル外へ淡く敷く）も試作して退けた — 帯の幅が格子に比例するので線を密に置く構図で画面が潰れ、かつ**丸めの大小と無関係に一様に付く**ので理由が絵から読めない。
- **数値は実物を並べて決めた:** 格子の粗さ（0.012 / 0.018 / 0.022）× 濃さ（0.30 / 0.45 / 0.55）の 9 面と、セルを**格子に乗せる**か**理想位置に置く**かの 2 面を描いて作者が選んだ（**0.018 / 0.45 / 格子に乗せる**）。理想位置版は粉が散って見え、格子版は段に沿った画素の列に見える。
- **語彙とスキーマ:** 歳時記に日本語「コンピュータ」／英語 `computer`、Score の `Weight` リテラル、線幅 2.0px、web の歳時記に専用プレビューと日英解説。Stage 2 の道具表には「格子に乗る」「段に落ちる」「誤差なく反復する」を使った。
- **参照コーパス `render-engine-13/` を凍結（228 件）:** 新規は `A-computer-*` の 8 件だけで、**既存 220 件は digest が 1 件も動かない**（engine 12 とバイト一致）。**版木を足しても前の刷りは変わっていない**ことの校正刷りである。これは同時に、**結果が変わるときだけを条件にすると版を上げずに語彙を足せてしまう**ことの実例でもある（SPEC §15.6 の「演奏できる語彙が増えたとき」で版を上げた最初の例）。
- **生成器のガードが正しく発火した:** 材質を作り直して再生成したとき「凍結済みコーパスを同じ版で書き換えるな」で停止した。**engine 13 は未リリースで、凍結されていたのは差し戻した実装の出力**なので、版を上げずに `render-engine-13/` を削除して凍結し直した（前の凍結はブランチの履歴に残っている）。
- **積み残さなかったもの（明示）:** Android への追随は行っていない（engine `"11"` のまま・別契約）。閉輪郭専用の半径変調は作っていない（作者裁定。機械の円がロットリングの円とほぼ同じで正しい）。走査線・ディザ・面（`surface`）のテクスチャには手を出していない。`TEXTURE_SPECS` / `TEXTURE_FILTER_WEIGHTS` / `_SPECK_SPECS` に `computer` を足していない。既存 10 道具の演奏値は 1 つも変えていない。過去エンジンの保持・選択は実装していない。既存履歴の backfill もしていない。
- **格子について未裁定で残したこと:** 格子は**絶対座標**に効き、**目盛はストローク長に比例する**（`step = 長さ × 0.018`）。したがって置かれた位置で格子の位相が変わり、同じ長さの線を等間隔に 30 本置くと**異なる図が 9 種**できる。キャンバス基準の 1 枚の方眼へ変えるかは別の裁定とし、現状のまま据え置いた。
- **SPEC:** §15.9 を新設（道具の核・格子・材質＝標本化の残り・第 1 版を捨てた経緯）、§4 の語彙表・§15.6 の版数・§15.7 のコーパス表を更新。英語版は §12.6 として対応。
- **検証:** pytest **1091 passed / 30 skipped**（+2 = 材質の新テスト）、cli 68 passed、ruff clean、`npm run check` **0 errors / 2 warnings**（217 files）。コーパスは再生成の差分ゼロ。**摂動 3 件で判別力を実測**した — 不透明度の係数を 0.45→0.44、格子への丸めを外す、残差 0 の除外を外す、のいずれでもテストが落ちる。**丸めの摂動は最初素通りした**（開いたストロークは標本が既に格子上にあるため）ので、**継ぎ目補正で標本が格子から外れる閉輪郭の検査を足して**効くようにした。

---

### Android `2.1.0-android.1` — 描画層が render engine 12 へ追随（`raster` 以前の脱・規則化・材質層・暴れる・`rh3`）（android Build 148084〜148089、2026-07-25）

**Android の描画層が engine 11 から 12 へ追いついた。** Stage 1.5 展開層は Phase 3d で追いついていたので、**これで遅れているのは engine 13（コンピュータ）だけになった**。

- **4a 演奏の脱・規則化:** `ToolGrammar` に 10 番目のフィールド `gesture` を足し、`WILD_GAIN = 3.5` / `GESTURE_EDGE = 0.16`、`smoothNoiseSalted` / `edgeWindow` / `swell` / `gestureWave` を移植。エンベロープ・補正イベント（`correction-kick`）・中心線ジェスチャを engine 12 と同形にした。
- **4b′ 材質アウトライン層（差し戻し 1 回）:** 初回は**移植ではなく別実装**だった。`points` を突き合わせると **0/234 点一致・最大 16.4px ずれ**、`stroke-dasharray` も全別値。**既存テストが `path d`・class 文字列・要素数しか見ておらず、この層の幾何を 1 点も比較していなかった**ため「SVG 11 件 100% PASS」のまま通っていた（**契約が既存テスト名で条件を書いたことが穴だった**）。4b′ で `outlineOffsetPx` の `scale` 二重掛け、`hash01` の seed 文字列化（符号なし 64bit）、`variedDashPattern` / `scaleDash` の書式を server 正本へ揃え、**`points` と `stroke-dasharray` の完全一致比較**を条件に加えた。
- **4c 暴れる（wild）の結線と版数:** `render_wild` を `line` プリミティブの `synthesizeStroke` にだけ通し、輪郭・ハッチ・弧には渡さない（**server がそうなっているため**）。`render_engine_version` を `"12"` へ。判別は 2 件の対で行う — `15_line_brush_wild` は `02_line_brush` と**異なり**、`16_circle_pen_wild` は `01_circle_pen` と**バイト一致**する（輪郭経路へ配線した実装は前者を通して後者で落ちる）。
- **4d `rh3` と記録・UI:** エディション ID を `rh2` → `rh3` へ（`render_wild` を材料に含む 7 キーの canonical JSON）。Room を version 4 へ上げ `MIGRATION_3_4` と `renderWild: Boolean?` を追加、UI に「暴れる」トグル（日英・既定 OFF）を結線した。**`rh2` の生成経路は撤去済み。**
- **受け入れで見つけた別の欠陥を直した（git 管理セッション）:** 検査を契約が名指しした 4 件から**参照 SVG 全 16 件**へ広げると、`11_cloudform_pencil` の `stroke-dasharray` が **`1,3`**（Android）対 **`1.000000,3.000000`**（server）で食い違った。server は style / texture の両方の dash を `_scale_dash` に通すが、Android は**素のリテラルを返していた**。**正方形キャンバスでは数値が一致するので見えないが、pillar / wide では server 側だけが目盛を伸ばす。** 出どころは Phase 2b′（`c6e2c9e`）で、**本契約より前からの欠陥**。dash 双方へ `scale` を適用し、server が Phase 1 で削除した `rope` の残骸も除いた。**全 16 件を `path d` / `points` / `stroke-dasharray` で比較するテストを恒久化**した（名指しの一覧は穴を残す）。
- **検証:** `testDebugUnitTest --rerun-tasks` を XML 自力集計で **68 件 / failures 0 / errors 0 / skipped 0**（着手時 64・4b′ 到着時 67）。**判別は受け入れ側で 3 件実測** — `swell` に 1e-6 で 8 件、`outlineOffsetPx` の floor に 1e-6 で 2 件、texture dash の `scale` を外すと 1 件が落ちる。着手時点の赤 14 件はすべて緑になり、**参照コーパスは 1 バイトも改変されていない**。
- **積み残さなかったもの（明示）:** engine 13（コンピュータ）は移植していない。`server` / `web` / `cli` / `shared` は変更していない。閉輪郭・ハッチ・弧への `wild` 配線は行っていない（server に無い）。既存履歴の `renderWild` は backfill していない。

---

### v2.6.1 — 英語 UI の用語を版画・音楽・短歌の語彙へ揃える（Build 708、2026-07-25）

**英語表示だけの改修である。日本語は 1 文字も変えていない。** 直訳調だった英語 UI を、inku が拠って立つ三系統のメタファー — **楽譜と演奏**（音楽）、**版木と刷り**（版画）、**詞書と歳時記**（短歌・俳句）— の英語圏での正統な術語へ揃えた。素人向けに薄めず、生成 AI 業界語（prompt / generate）ではなく工房の語（write / paint / perform）を使う。

- **英語表示は 3 系統あった:** i18n パック `en.ts` の **641 項目**、コンポーネント内の `isJapanese ? '…' : '…'` **132 箇所（12 ファイル）**、`getLang() === 'ja'` 分岐 **15 箇所**。**i18n パックだけ直すと 147 箇所が旧語彙で残る**ので、3 系統すべてを棚卸ししてから当てた（書き換えは 199 / 29 / 8 = 236 項目）。
- **五つの推敲操作を対称にした:** `Vary Touch with Words` / `Vary Layout` / `Vary Reading` / `Vary Color Catalog` → **`Another performance`** / **`Another composition`** / **`Another reading`** / **`Another catalog`**、変奏は **`Variation`**。「何を引き直し、何が保たれるか」が名前だけで対比できる。ツールチップは 1 文目に「何が起きるか」、2 文目に「何が保たれるか」を置いた（例: `Another performance` → *Same interpretation, same composition — only the performance sways… Instant, no LLM call*）。**ボタン幅が厳しくても名詞を省略しない**（対称性が崩れるくらいなら折り返す）。
- **変奏の強度を音楽の語へ:** `Small / Medium / Large` → **`Subtle / Moderate / Sweeping`**。音楽の変奏に Large は使わない。**同時に配置推敲のコスト表示 `Moderate (Stage 2 LLM and API)` を `Medium` へ直した** — 一語二義を作らないためで、これは「一語一義」を守るために辞書の外へ手を伸ばした唯一の箇所である。
- **一語一義を敷いた:** `interpretation`（Stage 1 の解釈）／`reading`（言葉の読み直し）／`performance`（演奏）／`variation`（変奏）／`sway`（揺らぎ）／`color catalog`（色カタログ）。**`palette` は 0 件**（色カタログは inku 独自概念なので置換しない）、**UI 文中の `rendering` も 0 件**（技術文脈のサーバー設定のみ残す）。推敲の候補は `variation` を避けて `option` にした。
- **文化語は最小限の固有名詞に:** ローマ字残しは **`Saijiki`** と **`inku`** だけ。`Okugaki` → **`Colophon`**（書誌学・ブックアートの術語）、`Kotobagaki (caption)` → **`Headnote`**（和歌研究の確立訳）、添景は既に `staffage`（風景画の点景）。ローマ字を増やすとエキゾチシズムに寄り、道具としての信頼を損なう。
- **来歴の語:** `Generation Info` → **`Provenance`**。`Artwork` / `artwork` → **`Work`**（美術の register。残存 0）。`Unleashed` → **`Wild`**（実装名 `WILD_GAIN` と一致）。主動作ボタン `Generate` → **`Paint`**（API `/api/paint` と一致）。
- **マイクロコピーを文単位で書き直した:** 段階表示は `DDL generation` / `JSON generation / SVG rendering` → **`Interpreting your words…`** / **`Writing the score, then performing…`**。版差の通知は *This artwork was rendered with engine N* → **`This work was performed by engine N. What you see now is a new impression by engine M.`**（版画の刷りの語）。プロバイダ失敗は *Stage 1 did not answer* → **`The interpreter did not answer in time, so a stock set of instructions was performed.`**
- **文体:** Sentence case を全ラベルへ（Title Case は作者名だけが残る）。三点リーダは `…` 一文字。感嘆符を落とした（`Autonomous refinement completed successfully!` → `Autonomous refinement finished.`）。
- **歳時記のカテゴリ名は 1 語も触っていない（実測による除外）:** 英語カテゴリ名は web の文字列ではなく `saijiki.py` の `name_en` で、**`prompt_block("en")` を通って英語 Stage 1 プロンプトへ流入している**（golden fixture `stage1_prefix_en.golden.txt` が固定）。**これは UI 表示ではなく英語版 DDL の語彙仕様**なので、辞書側の推奨（touches→touch、motions→gestures 等）は適用せず作者へ報告した。歳時記の語（circle, fine brush …）も同様に不変。
- **辞書と実装が食い違った 2 点は実測を採った:** ① 辞書は五操作の根拠を「日本語の『別の◯◯』と同じ設計」としていたが、**日本語正本は「◯◯を変える」の動詞形**である（作者裁定により英語だけ名詞形にし、日本語は不変）。② 契約は `settingsGenerationLabel` を「世代の意味なので触るな」に分類していたが、**日本語正本は `'生成'`（行為）** だったので `Generation` → `Painting` に直した。
- **日本語が動いていないことを機械で担保した:** `ja.ts` の md5、三項式の日本語側リテラル（132 箇所）の md5、`getLang()` 分岐の日本語側（14 箇所）の md5 — **3 つとも着手前と一致**。`LC_ALL=C sort` でロケールを固定しないと内容が動かなくても md5 が変わる（起票時に実際に踏んだ）。
- **検証:** `npm run check` **0 errors / 2 warnings**（217 files、警告は既存の a11y 2 件）。i18n の鍵は **641 のまま増減なし**、日英で完全一致。`server` / `cli` / `android` と `saijiki.ts` / `saijiki.generated.ts` の差分ゼロ。**摂動 4 件で判別力を実測** — `ja.ts` を 1 文字、三項式の日本語側を 1 文字、`palette` を 1 件混入、鍵を 1 つ削除、のいずれでも対応する検査が落ちる。
- **積み残した（明示）:** **英語ドキュメント（README.md / SPEC.md / `manual/en/`）の用語は未追随**。UI 側だけが新語彙になっているので、`artwork`（SPEC 25 / manual 26）・`palette`（SPEC 12）・`Okugaki`（SPEC 7）・`Unleashed`（SPEC 7）・`Generation Info`（SPEC 3 / manual 5）などが古い。**別作業とした。** 履歴ゼロの空状態文言は現行 UI に鍵が無いので新設していない（鍵を増やさない方針）。歳時記カテゴリ名（上記）も未実施。

---

### v2.7.0 — 一枚の方眼と、暴れるの到達（render engine 14）（Build 709、2026-07-26）

**engine 13 が残した 2 つの穴を、1 つの版としてまとめて塞いだ。** どちらも演奏結果が動くので、まとめれば参照コーパスの再凍結が 1 回で済む。

- **方眼は紙の性質であって、置かれた対象の性質ではない。** engine 13 の格子は目盛が**ストローク長に比例**していた（`step = 長さ × 0.018`）。そのため**長さの違うものは目盛が違い**（100px→1.8px / 400px→7.2px / 800px→14.4px）、**同じ長さでも置かれた位置で位相が変わり**（同一長の線を 30 箇所に置くと **30 種すべて異なる図**になる）、1 枚の絵の中に**大きさの数だけ別々の方眼**が同居していた。engine 14 は目盛を **`キャンバス短辺 × quantize`** で決める。値は `0.018` のままだが、**意味が「ストローク長に対する比」から「キャンバス短辺に対する比」へ変わった**。`stroke_engine` はキャンバスを知らないので **renderer が px へ直して `grid_step` として渡す**。**長さ相対の経路は 4 箇所とも削除**した（切り替えフラグも既定値も残さない）。正方 1000px で **18.000000px**、短辺基準なのでアスペクトで変わる（pillar は 3.600px）。**同じ絵の中のすべてのストロークが同じセルへ落ちる** — 大小 3 対象を 1 つの Score に同居させた実測で、18px 格子から外れた座標が **188/194 → 0/194** になった。方眼が対象の大きさで縮まなくなったので**連続する標本が同じセルへ丸め込まれることが起き、重なったセルは重ねて描く**（作者はこの見えを含めて 18px を選んでいる）。
- **「暴れる」が輪郭へ届くようになった。** engine 12 の暴れるは **`line` プリミティブにしか届いていなかった** — **11 道具 × 8 プリミティブ 88 組のうち 63 組が ON/OFF でバイト一致**しており、SPEC §13.4 の「作品全体に一つのトグル」という位置づけとずれていた。engine 14 は `synthesize_along`（円・楕円・三角・四角・多角形・弧・塗り・ハッチ）にも中心線ジェスチャを足して `wild` を通す。**OFF の出力は 1 バイトも変わらない**（既存 228 件で OFF に動いたのは格子由来の 7 件だけ）。**バイト一致してよいのは 25 組ちょうど**で、内訳は `cloudform` × 全 11 道具（`stroke_engine` を通らない既知の穴。本件でも直していない）、`rotring` × 7（`gesture = 0`）、`computer` × 7（`periodic` が `WILD_GAIN` を飛ばす）。
- **素朴な移植は 3 点で壊れる（試作で実測して仕様に落とした）:** ① **弧長で振幅を決めてはならない** — 閉輪郭の周長は寸法ではなく、多角形が星形になった。**`周長 / τ`＝半径相当で測る**。② **ジェスチャの平均を差し引く** — 平均が 0 でないと図形全体が伸縮する（円が一回り縮んだ）。**大きさは楽譜が決めるものであって、演奏が変えてよいものではない**。③ **角（anchor）の手前で窓を 0 へ落とす** — 意図へ戻される頂点の隣にジェスチャが乗るとトゲが出る。
- **材質が墨に追随するようになった（本件でいちばん見落としやすかった点）:** 輪郭と弧の材質アウトラインは**幾何から引かれていて演奏後の中心線を見ていなかった**。暴れるを届かせると **9 組すべてで墨だけが動き、材質が幾何の上に取り残された**。これは engine 12 が線について直したのと同じ型の不具合である（材質層が中心線に追随せず独立した罫線として背景に残る）。**ON のときだけ演奏後の中心線から作り、OFF では engine 13 のまま**にした。
- **参照コーパス `render-engine-14/` を凍結（347 件）:** `corpus_format_version` を `"1"` → `"2"`（ケースの入力に `wild` が加わったため）。`changed_from_previous` は **126 件**で、内訳は**既存 7 件**（`A-computer-*` から `cloudform` を除いたもの）と**新規 E 群 119 件**（暴れる ON の全数 88 + 塗り 15 + 面 16）、**不変 221 件**。**手の 10 道具は 1 件も動いていない。** `A-computer-cloudform` も動かない。
- **契約に赤を先出しした（起票時に git 管理セッションが一時パッチで実測）:** セル数 7 行と先頭 5 セルの座標・不透明度、既存 228 件のうち動くのは 7 件、wild が一致してよいのは 25 組、材質が離れる 9 組。**実装はこの全部を 1 桁も違わず再現し、受け入れ側で測り直しても同じだった。**
- **摂動で分かったこと（検査が 1 段少なかった）:** 「長さ相対へ戻す」を `synthesize_stroke` の内側だけに当てると**格子の検査 2 本が落ちなかった**。`_add_raster_bleed` が被覆セルを渡された目盛へ**再スナップする**ため、内部で目盛が食い違ってもセルの整列と一辺の一様性は renderer 側で保たれてしまう。`synthesize_along` と返り値まで含めて完全に戻すと 4 件落ちる。**同じ性質を 2 箇所で強制していると、片側だけの摂動は下流に吸収される。**
- **受け入れ側でも摂動を当てた:** 目盛 0.018→0.017 で 4 件、材質アウトラインを幾何へ戻す摂動を**弧側だけ / 閉輪郭側だけに分けて**当て、**どちらでも検査が落ちる**ことを確認した（強制点が 4 箇所あるので、片側だけの摂動では検査面の穴が見えない）。
- **SPEC:** §15.10 を新設（英語は §12.7）、§13.4 の暴れるに到達範囲の経緯、§15.9 の格子記述、§15.6 の版数と §15.7 のコーパス表を更新。**英語版の「Unleashed」を UI に合わせて「Wild」へ揃えた**（v2.6.1 で作った食い違いの一部解消。README と `manual/en/` はまだ残っている）。
- **検証:** pytest **1100 passed / 30 skipped**（+9 = `test_one_lattice.py` 3 / `test_wild_reach.py` 5 / コーパス 1）、cli 68 passed、ruff clean、`npm run check` 0 errors / 2 warnings（217 files）。コーパスは 2 回連続生成で差分ゼロ。**`android/` に差分が無いので Android のテストは回していない。**
- **積み残さなかったもの（明示）:** `cloudform` のストローク化、死にフィールド（`absorbency` / `contact` / `thickness`）、SPEC §17.A の `thickness` / `angle` / `rotation` / `length` dimension、過去エンジンの保持機構、既存履歴の backfill、`gen_android_reference.py` への波及はいずれも行っていない。**Android は engine 12 のままで、遅れが 2 版に広がった。**

---

### v2.7.1 — 英語用語の正本と、それを強制する lint（Build 710、2026-07-26）

**v2.6.1 は英語 UI を辞書へ揃えたが、揃った状態を保つものを残していなかった。** 文字列を 1 つ足すだけで禁止語が戻り、同じ概念に 2 つ目の英語が当たる。**規則の正本を文字列の隣に置き、それを機械で検査する番人を付けた。**

- **`web/src/lib/i18n/GLOSSARY.md`（200 行）が英語用語の正本。** 英語表示が 3 系統あること（`en.ts` 641 / 三項式 132 / `getLang()` 分岐 15）、コア用語の対応、五つの推敲操作と変奏の強度の固定値、文体規則、禁止語と**許容される例外**、触ってはいけない経路（`saijiki.py` の `surface_en` / `name_en`、`saijiki.ts`、`ja.ts`、三項式の日本語側）、新しい文字列を足すときの手順、検査が何を見ているか、まだ揃っていない食い違いまでを書いてある。出典は Fable の翻訳辞書と 2026-07-25 の作者裁定。
- **`web/scripts/i18n-lint.mjs`（221 行）が規則を機械で検査する。** `npm run lint:i18n`。**英語表示 788 文字列を走査し、許容例外 36 件を名前で通す。** `--list` で通した例外も出る。
- **文面と検査は一対**である。片方を変えたら同じ commit でもう片方も変える、と正本に書いてある。
- **「残存ゼロ」を条件にしない設計。** `generation`（世代）・`prompt`（LLM プロンプトの表示）・`created`（完了・日時）・`image`（Vision が実際に見る画像）・`render`（サーバー技術設定）は正当な用法があるので、**どこにも書いてはいけない語**と**決められた場所にだけ許される語**を分けてある。
- **判別力を受け入れ側で実測した。** `colorCatalogTitle` を `Color palette` に変えると `ERROR en.ts colorCatalogTitle: "palette" — use "color catalog" — palette is a different concept in inku` で 1 件落ち、戻すと 0 errors に戻る。
- あわせて `en.ts` の 1 項目を Sentence case へ是正した（`Instructions (Normalized DDL)` → `Instructions (normalized DDL)`）。**これは lint を通すために見つかった取りこぼしである。**
- **検証:** `npm run check` 0 errors / 2 warnings（217 files）、`npm run lint:i18n` **788 文字列 / 36 例外 / 0 errors**、pytest 1100 passed / 30 skipped、cli 68 passed、ruff clean。**`android/` に差分が無いので Android のテストは回していない。**
- **積み残し（明示）:** 英語ドキュメント（`README.md` / `manual/en/`、`SPEC.md` の残り）の用語追随は行っていない。**lint は `web/` の表示文字列だけを見ており、ドキュメントは見ていない。**

---

### 英語ドキュメントの用語追随（版数なし・2026-07-26）

**v2.6.1 が UI の英語を辞書へ揃えたとき、英語ドキュメントは旧語彙のまま残っていた。** UI だけが新しく、`README.md` / `SPEC.md` / `manual/en/` は `artwork` / `Generation Info` / `Vary Touch with Words` と書いたままだったので、そこを追随させた。**日本語正本とコードは 1 バイトも触っていない。**

- `artwork` → `work`（美術の register）、`Generation info` → `Provenance`、`Okugaki` → `Colophon`、`Kotobagaki` → `Headnote`、五つの推敲操作を確定した名前（`Another performance` / `Another composition` / `Another reading` / `Another catalog`）へ、変奏の強度を `subtle / moderate / sweeping` へ。
- **英語 UI の表記規則は、SPEC で述べ直すのをやめて `web/src/lib/i18n/GLOSSARY.md` を指すようにした。** SPEC.md には「短い英語ラベルは Title Case」と書いてあり、v2.6.1 で Sentence case へ移った実装と矛盾していた。**正本を 2 箇所に置かない。**
- **意図して直さなかったもの:** ① **CLI の実出力の引用**（`inku-cli` は今も `Artwork Lineage:` と印字するので、マニュアルは原文どおりでなければ嘘になる）、② CLI のサブコマンド名とフラグ値（`okugaki`、`refine generate`、`--kind layout`）、③ **JSON / API のフィールド名**（`palette`、`resolved_palette`、`palette:<name>`）、④ `Headnote` / `Colophon` に添えたローマ字の注記、⑤ **改訂履歴の「英語 UI の Title Case 統一」**（過去のビルドが実際にそうしたという記録であり、いまも真である）。
- **`palette` は当初「12 件が旧語」と数えていたが、分類すると 0 件だった。** 日本語正本も「色パレット」と書いており、残りは色カタログ API のフィールド名である。**辞書が禁じているのは「色カタログの意味での palette」であって、一般名詞のパレットではない。** 生の grep 件数をそのまま作業量として扱うと、正しい用法まで消すことになる。
- **機械置換が壊した英文を 5 箇所直した**（`not an work governor` / `by an work-page boundary` など、`artwork` → `work` で冠詞と複合語が崩れた箇所）。**一括置換は必ず後始末が要る。**
- **lint はここを見ていない。** `npm run lint:i18n` が走査するのは `web/` の表示文字列だけで、ドキュメントは対象外である。ドキュメント側の退行を機械で止める仕組みは無い。
- **採番していない**（ドキュメントのみの変更のため。下記の採番規則の最初の適用例）。

### 採番規則の強化（2026-07-26 作者裁定）

**「バージョン番号が速く上がりすぎている。0.0.1 単位での上昇をより多用する」。** 2026-07-21 にも同じ趣旨の裁定を受けていたが、その後も **engine の版上げを minor の理由として扱って**しまい、v2.5.0（engine 12）→ v2.6.0（engine 13）→ v2.7.0（engine 14）と 5 日で minor が 3 回上がった。**engine 版は演奏互換性のカウンタであって、ユーザー向けバージョンの粒度ではない。**

- **patch (+0.0.1) を既定とする。** 機能の追加・改修、UI・用語の改修、バグ修正、テストや参照コーパスの追加、**および render engine の版上げ**はすべて patch。
- **minor (+0.1.0) は 3 つの場合だけ** — 作者が節目と明示したとき、タグを打つ外部向けリリース、互換性が切れるとき（保存済みデータ・API・エディション ID の形式変更）。
- **ドキュメントのみの変更は採番しない。** CHANGELOG には版数なしの日付見出しで記録する（Android entry と同じ形）。
- `web/BUILD_NUMBER` は別勘定で、反映のたびに上がってよい。
- **迷ったら patch に倒す。既に公開した番号は振り直さない**（v2.5.0 / v2.6.0 / v2.7.0 はそのまま）。

---

### v2.7.2 — 誰も読まない 2 つのフィールドを退役させる（Build 711、2026-07-26）

**`contact` と `thickness` は宣言だけがあって、描画のどこからも読まれていなかった。** とくに `contact` は値を運んでいない — `touching` のときは `both_ends` 以外を禁止し、それ以外のときは書くこと自体を禁止していたので、書ける値は 1 つしかなかった。

- **`Relation.contact` と `Dimension` の `thickness` を消した。** `RelationContact` 型も消えた。SPEC §17.A の「`thickness` dimension 未対応」の行も、実装されないまま残っていた宣言だったので落とした。
- **保存済み作品は今までどおり再生できる。** pentala の 1780 件のうち `contact` を持つのは 41 件で、`extra="forbid"` があるため素朴に消すと再生時に弾かれる。各モデルが**検証の前に退役フィールドだけを落とす**ようにした。**未知のフィールドは今も拒否する。**
- **生産者側も止めた** — 日英の第二段階プロンプトとその例文、関係の補修経路、対を割るプラグイン。参照ダンプからは `contact` の列挙が消えた。
- **`absorbency` は退役させなかった。** 調査の結果、値そのものは読まれないが、**地の texture seed が Score 全体のハッシュ**（`_texture_seed`）なので、消すと地を持つ作品の粒配置が変わる。実測で **23 件中 18 件の出力が動いた**ため取りやめ、フィールドの説明にその理由を書いた。**次に engine の版を上げるときに、意図した変更として扱う。**
- **出力が変わらないことを実データで確かめた。** pentala の保存済み Score から 312 件（`contact` / `absorbency` を持つ 62 件全部 + 無作為 250 件）を旧実装と新実装で描き比べ、**変化 0 件**。関係を持つ 639 件でも **0 件**。**engine の版は上げていない。**
- **検証:** pytest **1101 passed / 30 skipped**（退役フィールドの互換テスト 1 件を追加）、cli 68 passed、ruff clean。**`web/` にも `android/` にも差分が無いので、`npm run check` と Android のテストは回していない。**

---

### Android `2.1.1-android.1` — 描画層が render engine 14 へ追随（コンピュータ・一枚の方眼・暴れるの到達・てざわり語彙の是正）（android Build 148090、2026-07-26）

**engine 13 と 14 の 2 版を 1 契約でまとめて追いついた。** これで Android は server と同じ render engine 14 を名乗る。

- **5a 機械項と格子:** `ToolGrammar` に `periodic` / `quantize` / `width_steps` を足し 11 道具へ同調。`grid_point` / `machine_energy` / `machine_swell` / `machine_gesture` を移植し、`StrokeSample` に `residual` を追加。**周期文法は `wild` を無視する**（`wild && !periodic`）。
- **5b renderer の格子と raster bleed:** 目盛は**キャンバス短辺 × `quantize`**（正方形で 18.0px）。`RASTER_BLEED_OPACITY = 0.45` の `<rect class="raster-bleed">` を敷き、直線・輪郭・弧・ハッチの全経路へ `gridStep` を渡す。
- **5c 暴れるを輪郭へ + 版数:** `wild` を輪郭・塗り・弧・ハッチへ結線（**雲形には渡さない**）。`render_engine_version` を `"12"` → **`"14"`**（`DefaultSvgRenderer` と `LocalFallbackPipeline` の両方）。
- **5d てざわり語彙の是正:** 表示語彙を server の `saijiki.py` と同じ **10 語ちょうど**へ（コンピュータ・ビュラン・ドライポイントを追加、髪と縄を除去）。**`hair` は Score の値としては保持**（保存済み作品の再生のため）。`rh3` の 4 値を engine 14 の実測値で固定。
- **受け入れで見つけて直した（git 管理セッション）:** 語彙から縄は消えていたが、**描画表には残っていた** — `ropeTwists`（呼び出し元ゼロ）、スタイル表の `"rope" -> 0.88`、線幅表の `"rope" -> 10f`。実装セッションが足した検査は**プロンプト文字列しか見ていなかった**ため通っていた。3 か所を削除し、**スタイル表・線幅表・文法表を見る検査**を足した（分岐を戻すと落ちることを確認）。
- **検証:** `testDebugUnitTest --rerun-tasks` を XML 自力集計で **71 件 / failures 0 / errors 0 / skipped 0**（着手時 68）。**判別は受け入れ側で 3 件実測** — 格子の目盛に ×1.000001 で 2 件が落ち、周期文法の `wild` 無視を外すと 4 件が落ち、`rope` の分岐を戻すと語彙テストが落ちる。
- **積み残さなかったもの（明示）:** `server` / `web` / `cli` / `shared` と参照コーパスは変更していない。Stage 1.5 の 3e 以降（葉文書プラグイン）、てざわり以外の歳時記カテゴリの語彙照合は範囲外。
