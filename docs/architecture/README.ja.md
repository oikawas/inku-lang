# inku アーキテクチャ

この文書群は、DDLの設計段階、現行実装、Web/Server/CLI/Android/外部provider/永続化の境界を、相互に追跡できる形で記録する。対象は公開commit `a69730d743da478eb7d3b3e9c8c9b50fa008ccfd`、app `v2.13.39 / Build 926` である。

## 推奨閲覧順

1. `evidence-inventory.ja.md` — IDと一次根拠
2. `system-context.ja.md` — システム外形
3. `runtime-containers.ja.md` — 実行単位
4. `ddl-processing-pipeline.ja.md` — DDL処理
5. `description-to-svg.ja.md` — 記述からSVGまでの判定の道筋（pipelineの深掘り）
6. `server-components.ja.md` — Server内部
7. `client-boundaries.ja.md` — Web/CLI/Android
8. `data-history-lineage.ja.md` — DB、同一性、系譜
9. `operations-security.ja.md` — 運用・安全境界
10. `change-impact-map.ja.md` — 変更時の波及
11. `known-differences.ja.md` — 不一致・未確認
12. `future-plan.ja.md` — 生成アーキテクチャの改修計画（裁定済みの範囲）

## 図の読み方

- 実線は実装で確認した呼出し・データ移動・生成を示す。
- 破線は仕様上の関係または実測未確認を示し、edge labelに明記する。
- Mermaid node IDは安定したASCII名を使い、主要nodeと境界は各図直後の表から `evidence-inventory.ja.md` のEvidence IDへ対応づける。
- DBは正本、作品ファイルは任意の派生物として区別する。
- 「同じScore」はseedを含まない。再現契約は**同じScoreと同じrender seed**である。

## 表記規則

本文中の `[確認済み]` は実装根拠あり、`[仕様]` は仕様のみ、`[推定]` は理由つき静的推定、`[未確認]` は今回確認していない事項を表す。仕様と実装が異なる場合は、どちらかへ丸めず `known-differences.ja.md` に併記する。

## 更新手順

1. 公開branch、commit、working treeを確認する。
2. `PROJECT_CONTEXT.ja.md` を読み、関連する `SPEC.ja.md` 節だけを選ぶ。
3. entry point、router、schema、import、test、manifestから現行値を確認する。
4. 最初に `evidence-inventory.ja.md` のsnapshotとIDを更新する。
5. 各図の直後の根拠表を更新し、`known-differences.ja.md` へ差異を移す。
6. Mermaid fence、参照path、秘密値・内部識別子、Git差分が意図した文書だけであることを検査する。

英語版は同名の `.md`、日本語版は `.ja.md` とし、事実・構造・Evidence IDを同時に更新する。日本語の設計判断を正本とし、英語は `docs/i18n/glossary.md` の対応表と `web/src/lib/i18n/GLOSSARY.md` の規則に従う。
