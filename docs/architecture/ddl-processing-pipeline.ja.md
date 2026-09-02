# DDL処理pipeline

## 段階と所有者

| 段階 | 入力 → 出力 | 決定性・fallback | 所有module |
|---|---|---|---|
| 記述 | 作者の文 → 保存用原文とpipeline用本文 | 行頭番号・括弧注記は描画pipelineから切除、原文は保持。切除後が空なら400 | `description_labels.py`; `render.py` |
| Stage 0.5 | 記述 → 写生文 | 任意、LLM。requestが写生文を持てばそのまま再利用しLLMを呼ばない。失敗（timeout・provider例外・空出力）時は記述へfallbackし`sketch_state`記録 | `sketch.py`; `render.py:_resolved_sketch` |
| Stage 1 | 記述/写生文 → 正規化DDL | LLM、空/timeout等にfallback。プラグイン語だけの入力（純粋呼出し）はStage 1を飛ばして転写 | `interpreter.py`; `render.py:_call_interpret_detail` |
| plugin展開 | 正規化DDL → core DDL + optional instructions | 文書検証後、seedつき決定的writing-down。seedは記述のhash | `plugins/document_format.py`; `_call_compose_detail` |
| Stage 1.5 | core DDL → effective DDL | 決定的。現行は焦点書換えのみ、明示変奏時だけ軸を動かす | `ddl_expander.py` |
| Stage 2 | effective DDL → JSON Score | LLM tool/schema。空・短すぎる出力は理由つきで1回retryし、timeout・空retry後は決定的fallback（`compose_fallback`へ記録） | `composer.py`; `render.py:_call_compose_detail` |
| coerce/validation | Score → renderable Score | `auto_repair`時のみ。不正relation等はdrop。要求配達とhard ceilingを行い、記述が抽象色を一つだけ名指す条件ではcolor cycleをその色へ畳む。分岐の発火は`coerce_branch_counts`（trace時） | `coerce/` |
| Render Engine | Score + seeds + 解決済みhost option → SVG + metadata | 同一Score・seed・条件で再現。runtime fallbackなしの粗いnative 1-call境界 | registry `render_engines/__init__.py`; 薄いadapter `default/adapter.py`; binding `inku-render-python`; portable core `core/crates/inku-render`; 別入口 `renderer.py`（SVG-only互換facade） |
| 履歴・系譜 | pipeline生成物 → DB row/node/edge | DB transaction。edgeは明示parent+kindのみ | `rendering.py`; `db.py` |

判定単位の詳細（どの条件で・何が起き・何が記録されるか）は `description-to-svg.ja.md` が持つ。

## 受入済みのTyped DDL経路（runtime未接続）

Step 8で、利用者に見える正規化DDLからtyped semantic documentとcompiler lockまでを
作るshared Rust基盤を`core/crates/inku-ddl`へ受け入れた。

```mermaid
flowchart LR
    VDDL["可視の正規化DDL"]
    DOC["source-preserving document"]
    STRUCTURE["lexer / clause stream\nmacro resolution / binding"]
    AST["typed semantic document"]
    EXPAND["bounded macro expansion"]
    LOCK["compiler lock"]
    SCORE["JSON Score / 現行runtime"]

    VDDL --> DOC --> STRUCTURE --> AST --> EXPAND --> LOCK
    LOCK -.->|"後続Stepで接続"| SCORE
```

この経路は、Stage 1が生成したDDLと利用者が直接書いたDDLを同じ可視本文から扱う。
自然文や非表示の背景情報をcompilerへ迂回させず、canvas metadataや未決定の描画既定値を
DDLの意味として挿入しない。複数の読みが残る場合はfirst / nearest / lastで決めず、
source spanと候補をtyped issueへ保存してfail closedする。

`compile_typed_ddl`の呼出しは現時点で`inku-ddl` crate内とそのtestだけにあり、server・
Web・Androidの製品pipelineには未接続である。したがって、以下の通常描画図は現在の
runtimeを、上図は受入済みの次期compiler境界を表す。

## 通常描画

```mermaid
flowchart TD
    DESC["記述"]
    LABELS["描画対象本文を抽出"]
    S05["Stage 0.5 写生 任意"]
    S1["Stage 1 解釈"]
    DDL["正規化DDL"]
    PLUGIN["宣言的plugin展開"]
    S15["Stage 1.5 決定的拡張"]
    EFFECTIVE["実効DDL"]
    S2["Stage 2 Score化"]
    SCORE["JSON Score"]
    COERCE["coerce / validation"]
    RENDER["Render Engine\nPython adapter → native wheel → Rust core"]
    SVG["SVG + 描画metadata"]
    HISTORY[("履歴DB + 系譜")]
    FILES[("任意の作品ファイル")]

    DESC -->|"原文は保存側にも保持"| LABELS
    LABELS -->|"sketch=on"| S05
    LABELS -->|"sketch=off"| S1
    S05 -->|"写生文 / 失敗時は記述"| S1
    S1 -->|"Stage 1出力"| DDL
    DDL -->|"coreへwriting-down"| PLUGIN
    PLUGIN -->|"core DDL"| S15
    S15 -->|"Stage 2入力"| EFFECTIVE
    EFFECTIVE --> S2
    S2 --> SCORE
    SCORE --> COERCE
    COERCE -->|"Score + seed + color"| RENDER
    RENDER --> SVG
    SVG -->|"save_history"| HISTORY
    HISTORY -.->|"best-effort派生保存"| FILES
```

## `/api/paint` とstreaming

```mermaid
sequenceDiagram
    participant C as Web/CLI client
    participant R as render router
    participant P as Stage pipeline
    participant L as LLM provider
    participant E as Render Engine
    participant D as DB
    participant F as Artifact queue

    C->>R: POST /api/paint または /api/paint/stream
    R->>P: _paint_events(request)
    opt Stage 0.5 enabled
        P->>L: 写生
        L-->>P: 写生文 / fallback
        R-->>C: streamのみ sketch NDJSON event
    end
    P->>L: Stage 1
    L-->>P: 正規化DDL
    R-->>C: streamのみ stage1 NDJSON event
    P->>P: plugin展開 + Stage 1.5
    P->>L: Stage 2 tool/schema
    L-->>P: Score / retry / fallback
    P->>P: coerce + validation
    R-->>C: streamのみ score NDJSON event
    P->>E: Score + render/composition seed
    E-->>P: SVG + metadata
    opt save_history
        P->>D: history + node + optional edge transaction
        P->>F: 任意の派生保存job
    end
    P-->>R: PaintResponse
    R-->>C: response または done NDJSON event
```

## 推敲の再入点

推敲は「pipelineをもう一度最初から」ではない。各操作は保存済みの生成物から、決まった層へ再入する。矢印の注記は**保たれるもの**である。

```mermaid
flowchart LR
    SAVED[("保存済み作品\n記述・写生文・DDL・Score・seed群")]
    S1["Stage 1"]
    S15["Stage 1.5"]
    S2["Stage 2"]
    COERCE["coerce"]
    RENDER["Render Engine"]

    SAVED -->|"読み取りを変える: 写生文は再利用、interpretation_seedだけ新しい"| S1
    SAVED -->|"配置: 保存DDLへcomposition_seed"| S15
    SAVED -->|"変奏: 保存DDLへamplitude+variation_seed"| S15
    SAVED -->|"タッチ（別の演奏）: 保存Scoreへ新しいrender_seed"| RENDER
    SAVED -->|"言葉でタッチを変える: seed_textからrender_seedを決定的に導出"| RENDER
    SAVED -->|"色カタログ: 保存Scoreとseedのまま色写像だけ変更"| RENDER
    S1 --> S15
    S15 --> S2
    S2 --> COERCE
    COERCE --> RENDER
```

- 再入した層より上流は変わらない。「読み取りを変える」は写生をやり直さず（確定済み写生文を`sketch_text`で渡し、Stage 0.5のLLMは呼ばれない）、「配置」「変奏」は解釈（DDL）を変えず、「タッチ」「色カタログ」はScoreを変えない。
- 再入した層より下流は再走する。「配置」「変奏」はStage 2のLLMを通り直すので、構図族の選択は決定的でも、Scoreの充填はモデル依存で揺れうる。
- AI自律推敲は上の5種（`reinterpretation` / `layout_change` / `variation` / `touch_change` / `catalog_change`）から各世代1種を選ぶ反復で、Visionの助言は次世代への入力になるだけである（`autonomous_refine.py:ALLOWED_KINDS`）。

## 設計契約の実装位置

| 契約 | 実装での保持 |
|---|---|
| Stage 1 / Stage 2分離 | `interpret_detail`と`compose`は別関数・別model解決。`/api/compose`はStage 1を通らない |
| Stage 1.5は意味を上書きしない | 現行`_expand_ja/_expand_en`は焦点のreframeだけで新しい文を追加しない |
| pluginはStage 1直後 | `_call_compose_detail`: `manager.expand` → `expand_intermediate_for_lang` → `compose` |
| 後段はplugin namespace非依存 | plugin文書はcore DDL/instructionへ閉じ、未知参照をdrop。provenanceだけmetadataへ残す |
| drop-only優先 | invalid relationは`_drop_invalid_relations`。ただしcoerceは要求配達repairと、単一の名指し色だけを残す決定的規則も持つため、完全なdrop-onlyではない |
| 再現性 | 決定的なseed派生はRustが所有し、Engine 41凍結corpusが描画byteを固定する。Python `seeds.py` はhostのfresh entropy発行だけを所有する。`renderer.py`は `render` だけを公開し、採用したfresh seedはmetadata/DBへ保存 |
| 過去engineを選び直さない | `current_render_engine()`は現行1 engine。履歴のdisplay SVGは保存済みを返す |
| 歳時記single source | `saijiki.py`からprompt、markers、relation literals、API表示、referenceを導出 |

## 生成パラメータの注入点

生成を変えるパラメータは、それぞれ決まった層に注入される。**rh3列が本表の要点である** — edition同一性 `rh3` の直接材料は「Score・render seed・wild・engine ID/版・色カタログID」だけで、それ以外はScoreを変えることを通じてのみ同一性に効く。直接材料に触れる変更は、同じ作品を別のeditionにする。

| パラメータ | 注入される層 | rh3への効き方 | 記録先 |
|---|---|---|---|
| 色カタログ（`catalog_id` / `catalog_mode`） | Renderの色写像 | **直接材料**（`render_color_catalog_id`） | render metadata・履歴列。`auto`はmodeも記録 |
| `render_seed` | Render Engine | **直接材料** | render metadata |
| `seed_text`（言葉でタッチを変える） | `render_seed`を決定的に導出してRender Engineへ | render_seedを通じて直接材料 | `seed_text`と導出seedの両方 |
| `wild`（暴れる） | Render Engine | **直接材料**（`render_wild`） | render metadata |
| `canvas_aspect` | Stage 2 prompt + Scoreの`canvas` | Score経由 | Score・`render_canvas_aspect_*`列 |
| `composition_seed` | Stage 1.5の構図族選択 | Score経由（直接材料ではない） | render metadata |
| `variation_amplitude` / `variation_seed` | Stage 1.5の明示変奏 | Score経由 | render metadata・`variation_moved_axes` |
| `interpretation_seed` | Stage 1 | DDL→Score経由 | render metadata |
| 写生設定（on/off・grain） | Stage 0.5 | 写生文→DDL→Score経由 | `sketch_text` / `sketch_grain` / `sketch_state`列 |
| 制限値（limits） | Stage 1/2 promptに明記＋coerceが適用 | Score経由 | `render_limits`と`render_limits_source`、超過は`render_limit_notes` |
| model選択（Stage 0.5/1/2） | 各LLM呼出し | Score経由（材料ではない） | `stage1_model` / `stage2_model`列 |

## 図の根拠

`PIPE-SKETCH`、`PIPE-S1`、`PIPE-PLUGIN`、`PIPE-S15`、`PIPE-S2`、`PIPE-COERCE`、`PIPE-RENDER`、`PIPE-HISTORY`、`PIPE-LIMITS`、`DATA-RH3`、`DATA-FALLBACK`。主なcall siteは `server/src/inku_server/api_core/routers/render.py:_paint_events` と `_call_compose_detail`。
