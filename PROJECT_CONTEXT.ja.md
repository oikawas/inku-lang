# inku プロジェクトコンテキスト

**対象バージョン: v2.1.0 / Build 638**

この文書は、開発者とAIが毎回 `SPEC.ja.md` 全文を読み直さずに作業を始めるための入口である。設計判断の正本は `SPEC.ja.md` であり、この文書と食い違う場合は日本語仕様を優先する。

## 最初に読むもの

通常の作業では、次の順に必要な範囲だけ読む。

1. `AGENTS.md` がローカルに存在する場合は、開発・検証・デプロイ規則を確認する。
2. 本書で目的、構造、現在の契約を確認する。
3. `git status --short --branch` と直近の履歴で作業状態を確認する。
4. 変更対象に関係する `SPEC.ja.md` の節と実装ファイルだけを読む。
5. 歴史的経緯が必要な場合だけ `CHANGELOG.ja.md` を検索する。

全文確認が適するのは、初回参加、設計思想の再検討、複数領域にまたがる大規模変更、仕様矛盾の監査である。

## プロジェクトの目的

`inku` は DDL（Drawing Description Language）の参照実装である。DDLは一般的な描画命令ではなく、「視覚的な短歌を書く言語」を目指す。

- 記述そのものを持続する作品として扱い、SVGは一回の演奏として扱う。
- 感情的な評価語ではなく、物理素材、配置、運動、観察可能な関係を書く。
- 短さと制約によって作者の主張を削ぎ、提示を中心にする。
- 既定の処理は再現可能にし、揺らぎはRendererの演奏とユーザーの明示操作に限定する。

## 現行アーキテクチャ

```text
指示文
  -> Stage 1: 解釈
  -> 正規化DDL（名前空間付きプラグイン語を含みうる）
  -> 宣言的プラグイン展開: コアDDLへ決定的にwriting-down
  -> Stage 1.5: 決定的な拡張・関係付与
  -> Stage 2: JSON Score化
  -> coerce / validation: drop-onlyを優先する境界処理
  -> Render Engine: SVG演奏
  -> 履歴・作品系譜
```

- `server/`: FastAPIバックエンド。API、認証、DB、解釈、構成、補修、描画、系譜を持つ。
- `web/`: SvelteKit 2 / Svelte 5フロントエンド。
- `cli/`: 公開HTTP APIだけを使う `inku-cli`。
- `android/`: Kotlin / Jetpack Composeによる別実装。詳細正本は `android/ANDROID_SPEC.ja.md`。
- `SPEC.ja.md`: 設計思想と現行契約の日本語正本。
- `SPEC.md`: 英語公開仕様。
- `CHANGELOG.ja.md` / `CHANGELOG.md`: 実装・設計変更の履歴。

## 守るべき設計契約

- DDLテキストは母語で書ける。JSON Scoreのキーは英語で統一する。
- Stage 1の解釈とStage 2の構造化を分離する。
- Stage 1.5は入力の意味を上書きせず、固定レシピの大量注入を避ける。
- coerceは長期的に縮小する。新しい様式を自動注入せず、不正値は可能な限りdrop-onlyで扱う。
- 同一Scoreと同一seedは同じ作品を再現する。暗黙の時刻seedや自動varyを導入しない。
- `dh1`（記述同一性）、`rh2`（作品エディション）、履歴ID、系譜node IDを混同しない。
- 系譜は明示された派生操作だけを記録し、類似度、時刻、hash一致から親子関係を推測しない。
- 品質指標、類似度、Vision所見は監査の鏡であり、生成ゲートや「最良枝」の自動選択に接続しない。
- プラグインはコードではなく検証済みの宣言的文書であり、Stage 1直後にコアDDLへ展開する。Stage 1.5 / coerce / Score / rh2はプラグインに依存しない。
- 語彙の正は saijiki テーブル（`server/src/inku_server/saijiki.py`、v1.92）であり、Stage 1プロンプトの語彙ブロック・プラグイン閉包マーカー・relation固定句・web歳時記表示・reference §1はそこから導出する。語彙の変更はテーブルとgolden testを経由する。
- 日本語と英語の挙動を揃え、英語だけの要件を追加しない。

## 現在の製品状態

v1.89では、認証付きWebアプリとして以下が利用できる。

- 日英の指示文自動判定と、Stage別モデル・言語比較
- 色カタログ、キャンバス比率、再現可能なタッチ／配置／読み取りの推敲
- ユーザー別履歴、スター、コメント、ゴミ箱、検索、系譜グループ
- 明示的なlineage node / edgeと、通常履歴に混ぜない中間作品
- AI自律推敲、描画要素・モデル・言語の比較、系譜の奥書、生成情報・プロンプト・JSONインスペクタ
- HTTP APIを操作するCLI、管理コマンド、ベンチマーク補助
- `default` Render Engineと、将来のEngine Packに備えた内部境界

直近のv1.90.0では、Build 586で「あいだ」の第5語「触れる」を正式化し、Build 587でrelation全種の参照座標をSVG transform合成後のキャンバス座標へ統一した。Build 588は`touching`の二重関係付与を除去した。Build 589では、検証済み `.inku-plugin.md` をStage 1直後にコアDDLへ展開する宣言的プラグイン層を追加した。名前空間明示または指示対象として明示された`fires_on`だけが発火し、比喩・未知対象へは広げない。展開は決定的かつ48 instruction以内で、再帰、固定座標スタンプ、URL／ファイル参照、namespace衝突はロード拒否する。provenanceは履歴メタデータへ記録するが、Score・DB正本・rh2・Replayはプラグイン本文に依存しない。Build 590では、プラグイン展開等で数値regionが確定済みのコアDDLへStage 1.5が別の補助図形を追加せず、Scoreも明示region数を超えるinstructionを残さない一般境界を加えた。この境界はinstruction数を対象とし、arrangementによる可視要素数にはMistral／Qwen間のモデル差が残る。Build 591では宣言的プラグイン形式をv2へ拡張し、`member`複合形、`注:／note:`コメント行、`下端の帯`と展開層計算による斜めの帯、未知領域キーのロード拒否（silent fallback廃止）、en反復単位と単位保存の単数形、`anchor … N〜M箇所`の入れ子反復、`fires_on`の同一位置最長一致を受け入れる。Score・coerce・rh2は不変で、Nature.leaves v0.3.0が `plugin validate` を通過する。

v1.92.0（Build 592）では歳時記を構造化した。`saijiki.py` の単一テーブルから、Stage 1プロンプトの語彙ブロック・プラグイン閉包マーカー・relation固定句・reference §1・web歳時記表示（`GET /api/saijiki` + スナップショット同期ストア）を導出する。構造化前プロンプトを golden fixture として凍結し、許可差分以外の組み立て差異をテストで検出する。作者裁定により語彙から「描く」「髪」を削剪した（Weight enum の hair は Replay 互換のため残置）。web 表示から「彫る」を削除し、Nature.風/うねり/無風 の静的表示は宣言的移行まで凍結した。

v1.93（Build 593）では RAW trace オプションを追加した。`/api/paint`・`/api/compose` の `include_trace`（既定 false）で各層の中間生成物を 1 応答に持ち帰る観測のみの機能で、Score・render・分岐・回数を変えず DB へも保存しない（利き目監査ハーネスの入口）。 なお本番配布用のベンチ専用コンテナ環境（api 8101／web 5174・専用DB・版固定）をpentala上でbare metalと併走させて確立した（運用詳細はローカルの `AGENTS.md`）。

v1.94.0（Build 594–599）は web UI のみの整理で、描画機構と server には触れていない。記述タブの指示・ボタンの下へ「現在選択中」（モデル・色カタログ・キャンバス、Stage 1／2 差異はラベル付き・モデルはフル名称）を移設し、キャンバス下ステータスバーはモデル等を除いて render hash（下四桁）＋クリックで full hash コピーへ置換した。記述・バッチ・デモの左パネルを左へ折りたためるようにし、キャンバス作品のマウスホイールズームを追加した。Vision モデルは用途別に整理し、AI 自律推敲で選ぶモデルを `vision_model` へ、奥書のモデルを `okugaki_model` へそれぞれ永続化して、記述から開くモデルダイアログからは Vision タブを外した（Vision は生成では使わず所見・推敲観察のみ）。下部履歴サムネイルは Stage 1 短縮名を表示し tooltip は Stage 1／2 をフル名称で分離、状態バッジは除去（tooltip には残置）、英語表記は「Gen.」へ短縮した。ボタン意匠と配置（起点＝新規作成と同意匠、ハッシュ＝他ステータスバーボタンと同意匠、最新ボタンを左、指示タブはモデル→色カタログ順）を整え、推敲・奥書のモデル選択 tooltip を `position: fixed` 化してスクロール容器の見切れを解消した。系譜の作品カードメニューからは「ゴミ箱へ移動」を除いた（ヘッダの一括ゴミ箱は残置）。

Build 600 では、region（`at`）とrelationを両方持つinstructionがregion配置時にrelationを無言破棄しtouchingに到達しなかった不具合を修正した。region配置を先に・relation解決を後に実行し、プラグインmember由来の双弧（葉形）が設計どおり端点固定の対向劣弧として演奏される（利き目監査F-1）。演奏時のみ解決不能なrelationは§14.4に従い警告記録付きでdropする。rh2契約とScore schemaは不変。

v1.95（Build 601–604）は web UI 第 2 期の整理で、server・Score・rh2 は不変。比較ダイアログの単一タブ化と推敲タブの削除、記述タブの指示主体化（正規化DDLは閲覧専用、DDL 作成・編集は共有エディタへ集約、DDL 由来作品は `display_label='DDL'` で識別し指示文前提の操作を非表示）、作品タブ改称・世代表示・AI 自律推敲の UX 整理を行った。また Build 600 で、展開層の対 member 文を LLM を通さず Score instruction へ決定的に転写する層（様式文消費・coerce 迂回合流）と、明示語彙の搬送を検査する鏡 `carriage_warnings`（検査のみ）を追加した。語彙の搬送契約はモデル非依存となり、モデル選択は表現の幅へ純化される。

v1.96（Build 605–606）では、添景の量を生成時にユーザーが選べる水準 `tenkei`（none／sparse／auto、既定 auto）を導入し、三層（Stage 1 規範文＋純明示バイパス／Stage 1.5 候補プール縮約／coerce 挿入予算）へ決定的に写像した。事後の間引き governor はなく、tenkei は rh2 の材料に含まれない。あわせて Build 600 の対転写が素通しにしていた Stage 1.5 追加抑止（§4.6）を回復し、ユーザープラグインの管理 API（本文取得・作成・上書き・削除・有効/無効、`.plugin-state.json` 永続化）と設定 UI を実装、系譜応答へ `lineage_generation` を付与した。UI 第 3 期はマスコットの inku キューブ化、生成ステータス要素の全ダイアログ統一（中止可能）、言語比較の Stage 1×Stage 2 直接選択への再設計、モデルメタデータの単一ソース化を行った。

v1.97（Build 607–608）では添景水準を作品ごとに保存する形へ改めた。history の `tenkei` 列と「明示値 > 派生元作品からの継承 > auto」のサーバー側解決により、推敲・AI 自律推敲・CLI を通じて系統の水準が無指定のまま維持される（タッチ変化など Renderer 専用派生でも保存時解決で途切れない）。UI は記述タブのセレクタ（localStorage 永続）と推敲 6 ダイアログの継承既定 3 択（変更で系統の分岐点）を結線し、生成情報・履歴 tooltip に水準を表示する。

v1.98（Build 609）では単発描画を `POST /api/paint/stream`（NDJSON）へ移行し、解釈完了時点で正規化DDLを先に表示する（`/api/paint` は同一ロジックのラッパで応答形状不変）。history は入力側 DDL（`ddl`）と展開後 DDL（`expanded_ddl`）を分離保存し（一度きりバックフィルで旧作品は展開後のみ）、`focus` の明示指定と `interpret_fallback`（空の Stage 1 出力の失敗化・フォールバック印）を導入した。検証済みモデルカタログは実測 2 回に基づき v2 へ再構築（29→43 エントリ、用途別推奨度 `recommendation_llm`/`recommendation_vision`、EOL 印つき残置、表示順の単一経路化）、プロバイダ失敗は種別分類で説明表示する。歳時記ドロワーは閲覧専用となり、語の挿入は DDL エディタダイアログのインライン歳時記（プラグイン語彙含む）に集約した。

v1.99（Build 610）では揺らぎ（variation）の演奏対象を line のみから弧・閉図形（円・楕円・三角・四角・多角形）へ拡張した（F-4）。ゲートは line と対称（quality ∈ {perlin, wave, white} かつ dims に position_x/position_y/radius）。閉図形は継ぎ目連続の周期ノイズ、多角形系は角固定、弧は両端点固定で touching 接点契約を維持する。演奏結果が変わるため render engine version を 5 へ更新（保存済み SVG・Score・rh2 は不変）。作者の実演奏目視確認と材質輪郭（Phase 2）の要否判断が残る。

v2.0（Build 611）では Stage 1.5 に「変奏」を実装した（SPEC §12.13）。展開層をまとめて振る明示操作で、強度は小中大の 3 段、7 軸（型の差し替え・採用本数・タッチ材質・焦点・主色対比色・構図族・型の系統）を重み付き段階解放で動かし、`(強度, seed)` で完全再現・系譜非継承・tenkei の cap 内。候補は 4 案（seed はサーバー採番 `/api/variation/seeds`）で、各カードに「何が動いたか」を公式語彙で表示する。動かすと決めた軸は実差分を保証（可視性保証）。あわせて focus の外部入力（`PaintRequest.focus` 等）と推敲要素「焦点を変える」を撤去し、推敲は 4 種へ回帰。展開層の解決焦点を render_metadata へ結線したため `history.focus` は記録され続ける。history に `variation_amplitude` / `variation_seed` の 2 列を追加。残件: 変奏セクションの UI 配置手直し（作者イメージと相違）、`loadIterationItem` の変奏フィールド未復元、`api_history_neighbors` の既存バグ。

v2.0.1〜v2.0.3（Build 612〜630）では、モデルカタログを実測 3 回合算の v2.1 へ更新し（44 エントリ、時間帯検証は打ち止め）、v2.0 の残件を解消した。`api_history_neighbors` の 500（score 文字列）修正と `loadIterationItem` の変奏フィールド復元（v2.0.2）、変奏 UI の配置（v2.0.3、作者裁定により第 5 の推敲要素へ統合。選択時のみ強度小・中・大を表示し、実行は 1案/4案 に統合、独立セクションは撤去）。あわせて AI 自律推敲の有効要素に変奏を追加（上限 5）、作品カードメニューと各ダイアログの見出し・並びを整理し、候補グリッドのウインドウ内表示と保存の 3 状態化、ボタン寸法トークン（`--btn-sm-*`）の導入と漸進移行規約を定めた。v2.0.4（Build 634）では自律推敲の変奏に強度選択（小・中・大、既定 中、実行中の全変奏世代へ適用）を追加し、小型ボタンの寸法トークン移行を完了した（部分一致 6 ブロックも作者裁定で統一）。

v2.0.5（Build 636）では作者の F-4 目視確認で発覚した wave 揺らぎの seed 非依存バグ（位相固定の正弦波）を修正し、演奏 seed 由来の位相を導入。材質輪郭も演奏 seed に追随させた（F-4 Phase 2）。render engine version は 6。

v2.1.0（Build 638）ではレンダリングの px 絶対値を比例系へ全面改修した。揺らぎ振幅と滲みは図形の代表寸法比（fine / medium / broad = 0.025 / 0.08 / 0.18、滲み 0.009 / 0.03 / 0.07）、分割数・標本数は長さ比例、材質層（線幅・dasharray・質感 filter・材質輪郭・speck）と display filter は `canvas.unit` 相対（`unit=1000` でほぼバイト一致、speck 個数は周長比例化）。作者キャリブレーション 2 巡で材質強度 s1（輪郭 offset / opacity・speck opacity / 個数の下限方式、質感 filter は据え置き）を採用。材質輪郭に `class="material-outline"` を付与。render engine version は 7。後続契約として閉図形への手描きストローク適用（`opus-closed-shape-strokes.md`）と PNG ラスタライザの filter 対応（`opus-png-filter-rasterizer.md`、cairosvg は feTurbulence / feDisplacementMap / feGaussianBlur を非描画）が起票済み。

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

- 仕様変更は `SPEC.ja.md` を先に更新し、同じ意図を `SPEC.md` に反映する。
- 現行の構造や重要契約が変わる場合は、本書と `PROJECT_CONTEXT.md` も更新する。
- リリース／Buildの履歴は `CHANGELOG.ja.md` を先に更新し、公開上必要な内容を `CHANGELOG.md` に反映する。
- 実装だけの細部を仕様本文へ無制限に積み増さない。現行契約は仕様、時系列の記録は変更履歴へ置く。
- Webの挙動またはUI変更では `web/BUILD_NUMBER` を更新する。アプリ世代変更時はWebの `APP_VERSION` も揃える。
