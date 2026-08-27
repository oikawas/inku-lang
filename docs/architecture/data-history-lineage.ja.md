# Data, history, lineage

## 正本と派生物

```mermaid
flowchart LR
    PAINT["server-side paint"]
    ROW[("HistoryRow\nDB正本")]
    SVG["保存済みdisplay SVG"]
    EXPORT["editable / compat再描画"]
    FILES["自動作品ファイル"]
    NODE[("LineageNodeRow")]
    EDGE[("LineageEdgeRow")]

    PAINT -->|"入力・DDL・Score・SVG・metadata"| ROW
    ROW -->|"display profileはそのまま返す"| SVG
    ROW -->|"保存Score + 現行engine"| EXPORT
    ROW -.->|"best-effort派生"| FILES
    ROW -->|"1履歴 = 1 node"| NODE
    NODE -->|"明示parent + derivation kindのみ"| EDGE
```

DB rowには入力、Stage 1側DDL、effective DDL、Score、server生成SVG、model/版/seed/色/時間/token、mark、表示状態が入る。さらに写生（`sketch_text` / `sketch_grain` / `sketch_state`）と、各層のfallbackの記録（Stage 1 = `interpret_fallback`、Stage 2 = `compose_fallback`）を列として持つ。`compose_fallback`は「fallbackだった（理由文字列）」「fallbackでない（`none`）」「記録なし（列導入前の作品）」の3値で、記録なしをfallbackでないと混同しない。backfillはしない。自動作品ファイルを無効化またはqueue overflowしてもDB履歴は残る。

## 移植可能な永続化境界

ServerはSQLAlchemy/SQLite、AndroidはRoom/SQLiteを物理ownerとして持ち、将来iOS adapterを作る場合も自身の物理schemaを持つ。共通意味とhost mappingの正本は[`persistence/README.md`](../../persistence/README.md)と[`persistence/contract.json`](../../persistence/contract.json)であり、同じDB file、table名、column配置を要求しない。Server専用の認証・管理tableと端末専用のprovider・model・cache tableはhost extensionであってparity gapではない。保存済みSVG、Score、hash、NULLの意味はこのmappingによって変えない。

## Server SQLite lifecycle

```mermaid
flowchart LR
    CONFIG["config.py\n両SQLite URLを先に検証"]
    ENGINE["engine.py\nengine + connection PRAGMA"]
    FACADE["db.py\ncompatibility / composition façade"]
    MIGRATION["migrations.py\nregistry / fingerprint / writer lock"]
    SNAPSHOT["backup.py\nWAL-safe SQLite snapshot"]
    INVARIANTS["invariants.py\nPK + canonical history digest"]
    SCHEMA["schema.py / legacy_schema.py\nphysical schema / one-shot transform"]
    DOMAIN["domain owners\naccounts / settings / history / lineage / search …"]
    DB[("canonical SQLite")]

    CONFIG --> ENGINE
    FACADE --> MIGRATION
    MIGRATION --> SNAPSHOT
    MIGRATION --> INVARIANTS
    MIGRATION --> SCHEMA
    MIGRATION --> DB
    DOMAIN --> DB
```

`db.py`は既存のimportとcall shapeを保つfaçadeで、直接SQLやmigrationのownerではない。`persistence/`の18 owner module（これにpackage初期化を加える）が、設定・engine・schema・migration・backup・invariantと、access、account、group、session、identity、settings、history、search、lineage、奥書、feedbackの変更理由ごとに分かれる。

起動時は3経路だけを取る。fresh DBはschemaとregistryを1 transactionで作る。registry済みDBは版とchecksumを検査して通常起動し、legacy repair scanを繰り返さない。registry導入前DBは、明示されたschema fingerprintとFTS状態を満たす場合だけ、検証済みsnapshot作成後に単一writer transactionで一度だけ移行する。未知・部分状態・未来版・checksum不一致は変更前に拒否する。移行中はprimary key identityと履歴の`id/input/score/svg` byteをstreamingで照合し、SQLite quick checkとforeign-key checkも要求する。

Android Room v10は同じ論理契約を別の物理schemaで満たす。v1–9限定resetは旧DBと派生thumbnailを捨てるがmodel fileを残し、v10を保持する。未来版や読めないDBは変更しない。このlifecycle差はportable contractのgapではなくhost adapterの明示的な所有範囲である。

## 4種類のID

| ID | 何を識別するか | 同じでも別になりうるもの | 実装 |
|---|---|---|---|
| history ID | 1件のDB履歴row | 同じ記述・同じeditionの別保存 | `HistoryRow.id` |
| `dh1` | NFC・改行・外側空白を正規化した記述 | history、render、lineage node | `identity.py:description_hash` |
| `rh3` | Score + render seed + wild + engine ID/version + catalog ID | 記述、SVG文字列、build、composition seed | `db.py:render_hash_for_item` |
| legacy `rh2` | 旧payload規則のedition ID | `rh3`とは再計算規則が異なる | `db.py:_legacy_render_hash_for_item` |
| lineage node ID | 系譜graphの1 node | history ID、`dh1`、`rh3` | `LineageNodeRow.id` |

`rh2` rowは保持し、欠損hashだけを`rh3`でbackfillする。`render_hash_short`は表示用の末尾4文字であり、独立した同一性ではない。

## 系譜

```mermaid
flowchart TD
    ROOT_H["History A"] --> ROOT_N["Node A / root"]
    CHILD_H["History B"] --> CHILD_N["Node B"]
    ROOT_N -->|"明示された derivation_kind"| EDGE["Edge A→B"]
    EDGE --> CHILD_N
    SAME_DH["同じ dh1"] -.->|"自動edgeにしない"| ROOT_N
    SAME_RH["同じ rh3"] -.->|"自動edgeにしない"| CHILD_N
    TIME["近い時刻・類似Score"] -.->|"自動edgeにしない"| EDGE
```

`db.add_item` はparentがあるのにkindが無い場合、またはkindだけの場合を拒否する。parentがあれば同じuserの非tombstone nodeを確認し、history、node、edgeを1 transactionで書く。類似度、時刻、hash一致からedgeは作らない。

## 保存済みSVGと再描画

| 操作 | source | engine |
|---|---|---|
| history display SVG | DBに保存した`HistoryRow.svg` | 当時生成済み。再描画しない |
| editable / compat export | 保存Scoreと作品自身の保存色map | 現行engine |
| replay / render-score | 保存Scoreと明示seed等 | 現行engine |
| PNG | SVGのrasterize派生 | Render Engineの版ではなくrasterizer |

`GET /api/history/{item_id}/svg?profile=display` が保存SVGを返し、他profileだけ `_render_score_svg` を呼ぶ。過去engineを選択するregistry/APIは確認できない。

Androidも同じ原則に従う。Roomに保存したcanonical SVGを再描画せず、preview、thumbnail、PNGでは
`inku-svg-raster`からpixel派生を作る。raster APIは作品identityとRender Engine版を所有しない。

## 実在schema

```mermaid
erDiagram
    USER_ACCOUNT ||--o{ HISTORY : owns
    USER_ACCOUNT ||--o{ LINEAGE_NODE : owns
    USER_ACCOUNT ||--o{ LINEAGE_EDGE : owns
    HISTORY ||--o| LINEAGE_NODE : represented_by
    LINEAGE_NODE ||--o{ LINEAGE_EDGE : parent
    LINEAGE_NODE ||--o| LINEAGE_EDGE : child
    LINEAGE_NODE ||--o{ OKUGAKI : target

    HISTORY {
      string id PK
      string user_id FK
      text input
      text ddl
      text expanded_ddl
      text score
      text svg
      string description_hash
      string render_hash
      string lineage_node_id
    }
    LINEAGE_NODE {
      string id PK
      string user_id FK
      string history_id
      string state
      string root_node_id
    }
    LINEAGE_EDGE {
      string id PK
      string parent_node_id FK
      string child_node_id FK
      string derivation_kind
      text metadata_json
    }
```

図は `HistoryRow`、`LineageNodeRow`、`LineageEdgeRow`、`OkugakiRow` に実在する属性だけを載せた。

## 根拠対応

`SYS-DB`, `SYS-FILES`, `DATA-DH1`, `DATA-RH3`, `DATA-RH2`, `DATA-LINEAGE`。実装根拠は `db.py`, `identity.py`, `routers/history.py`, `test_lineage_acceptance.py`, `test_render_hash.py`。
