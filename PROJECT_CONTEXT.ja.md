# inku プロジェクトコンテキスト

**対象バージョン: v2.4.6 / Build 696**

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
- `dh1`（記述同一性）、`rh3`（作品エディション。旧 `rh2` は legacy として保持）、履歴ID、系譜node IDを混同しない。
- 系譜は明示された派生操作だけを記録し、類似度、時刻、hash一致から親子関係を推測しない。
- 品質指標、類似度、Vision所見は監査の鏡であり、生成ゲートや「最良枝」の自動選択に接続しない。
- プラグインはコードではなく検証済みの宣言的文書であり、Stage 1直後にコアDDLへ展開する。Stage 1.5 / coerce / Score / rh2はプラグインに依存しない。
- 語彙の正は saijiki テーブル（`server/src/inku_server/saijiki.py`、v1.92）であり、Stage 1プロンプトの語彙ブロック・プラグイン閉包マーカー・relation固定句・web歳時記表示・reference §1はそこから導出する。語彙の変更はテーブルとgolden testを経由する。
- 日本語と英語の挙動を揃え、英語だけの要件を追加しない。
- **エンジンは後戻りしない**（SPEC.ja §15.8）。過去の描画エンジンをシステムとして保持せず、版を選び直す機構も作らない。Replay は常に最新で行い、当時のエディションの再現は**保存済み SVG の返却で担保する**。版画と同じで、彫りは進み刷りは残るが版木は戻せない。**だから現役のうちに参照コーパス（＝校正刷り）を取る。**

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

v2.1.0（Build 638）ではレンダリングの px 絶対値を比例系へ全面改修した。揺らぎ振幅と滲みは図形の代表寸法比（fine / medium / broad = 0.025 / 0.08 / 0.18、滲み 0.009 / 0.03 / 0.07）、分割数・標本数は長さ比例、材質層（線幅・dasharray・質感 filter・材質輪郭・speck）と display filter は `canvas.unit` 相対（`unit=1000` でほぼバイト一致、speck 個数は周長比例化）。作者キャリブレーション 2 巡で材質強度 s1（輪郭 offset / opacity・speck opacity / 個数の下限方式、質感 filter は据え置き）を採用。材質輪郭に `class="material-outline"` を付与。render engine version は 7。

v2.2.0（Build 640）では閉図形（円・楕円・四角・三角・多角形）の輪郭を手描きストローク（筆致エンジン）で描くようにした。`stroke_engine` に任意中心線への合成 `synthesize_along` を追加し（歩幅フィードフォワード積分器で曲率歪みを排除）、輪郭を外周・内周 2 サブパスの塗り帯（`class="contour-stroke-v1"`）として描く。角は理想位置固定の筆の継ぎ目、角なし閉輪郭は線形ランプで閉合。rotring は幾何輪郭のまま、帯は変奏演奏後の輪郭に合成、材質輪郭・speck と併存、本体要素は幾何のまま（bbox・touching 不変）。line・弧は v2.1 とバイト一致（弧のストローク化は touching 弧抽出器の再設計込みで次契約）。render engine version は 8。作者判断待ち: `filled` が閉図形で死にフィールド（常に塗りつぶし）である件と、「塗り = 細かいストロークで内側を埋める」案（試作 3 回記録済み、engine 9 相当、pending 消化後）。後続契約として PNG ラスタライザの filter 対応（`opus-png-filter-rasterizer.md`、cairosvg は feTurbulence / feDisplacementMap / feGaussianBlur を非描画）が起票済み。

v2.2.1（Build 643）では PNG ラスタライザを resvg-py へ置換し、質感 filter・滲みが全 PNG 経路（ダウンロード・AI Vision 入力・奥書サムネイル・CLI 5 箇所）で描画されるようになった。共通ヘルパー `shared/src/inku_analysis/rasterizer.py`（resvg 優先・cairosvg フォールバック・不在時警告 + skip 維持）。API に PNG エンドポイントは無く CLI は応答 `svg` を自プロセスでラスタライズする構造のため、CLI 側も同ヘルパーへ寄せた。cairosvg フォールバック時は CLI 警告 + サーバー WARNING + 成果物へ `png_rasterizer`（backend/version）を記録。Python は server / cli / shared とも 3.12 へ統一（resvg-py の wheel 都合）。`inku-analysis` を editable 依存化し「shared を rsync しても uv sync まで反映されない」罠を解消。SVG・rh2・engine（8）は不変。生成 PNG は旧 PNG と画素非互換（過去ランとの直接画素比較は不成立）。lock 一本化（uv workspace 化）は別契約。

v2.3.0（Build 645）では閉図形の塗りを領域 fill から素材の筆致で内側を埋めるストローク塗り（`class="fill-stroke-v1"`）へ変更し、`filled` の意味論を復権した（`True` = 素材の筆致で内部を埋める / `False` = 輪郭のみ。従来は死にフィールドで常に塗りつぶし）。走査線と閉輪郭の交点で 1 区間 = 1 筆を `synthesize_along` に通す（clipPath 不要・凹形可・端点は輪郭に揃う）。走査角は演奏 seed 由来 0〜180°、間隔 `max(線幅 × 1.5, canvas.unit × 0.012)` + ±12% ジッタで紙目を残す。rotring は領域 fill 維持、走査線 3 本未満は領域 fill に縮退。`surface` 指定時は素材塗りを抑制し、surface の hatch / crosshatch は筆致の帯（`class="surface-stroke-v1"`）へ差し替え。演奏されない variation は seed key から除外（primitive 別不活性判定）。render engine version は 9。サイズは 1 図形 11〜123KB・10 instruction で 422KB（上限規則は分布を見て後付け、最大要因は surface crosshatch の帯化）。残: 実 UI 目視（塗り間隔の粗密）・粒系 / 滲み系の筆致化。次契約 = arc のストローク化（engine 10、裁定済み仕様はレポート付録）。

v2.3.1（Build 647）では弧（arc）も手描きストロークの帯（`class="arc-stroke-v1"`）で演奏するようにし、v2.2.0 で残されていた最後のストローク化対象外を解消した。幾何の弧は不可視の意図要素（`stroke="none"`）として残り、touching（接点契約）は意図弧を読み戻して座標で担保（弧抽出器は無改変、`test_touching.py` 全通過）。接点端も taper のまま（幅の下限なし、葉の先端は柔らかく消える）。破線・点線は意図弧を細く可視化、drypoint は中心線沿い burr、材質輪郭・speck は帯と併存、rotring は幾何のまま。render engine version は 10。塗り間隔の粗密は実 UI 目視 OK で確定済み。残: 弧の実 UI 目視（Stage 3 葉の再目視も候補）・サイズ上限・粒系 / 滲み系の筆致化。**バージョン採番の作者裁定（2026-07-21）: 小改修は patch（+0.0.1）とする。**

v2.3.2（Build 683）では v2.3.1 機能群に UI を追随させる対話型調整 35 件（Build 648〜682）を実施した。歳時記ハイライトの英語対応、指示書エディタの拡充、PNG EXIF 撮影日、入力 3 タブの整理（設定状況帯の共通化・字数メーター単位）、コンタクトシート（人用 7×4 / AI 用 3×4 + md ノート）、ダークモードのコントラスト是正（`--accent-fg` トークン新設）、バッチ追従性の改善。サーバー変更は描画並列度の管理者設定のみ（`_RenderCapacity`、`render_concurrency_settings`、`PUT /api/settings/render-concurrency`、`GET /api/client-config`。`INKU_RENDER_CONCURRENCY` は DB 未設定時の初期値へ）。あわせて用語を層別に統一（**Sol LeWitt の指示書 = 正規化DDL。作者の書く記述はその一段上の詩歌的な層**。Stage 1 の生成物は「指示書」、詞書 = 記述の再掲）し、SPEC.ja §5 の改訂（4 段パイプライン図 + §5.3 用語対応表）・SPEC.md §2・README 日英に反映、UI の App Info に語彙ダイアログを常設した。engine は 10 のまま。UI 調整は新セッションで継続予定。

v2.4.0（Build 684）ではリリース配布パイプラインを確立した。git タグ `vX.Y.Z` の push で GitHub Actions が `ghcr.io/oikawas/inku-api` / `inku-web` を multi-arch（amd64 / arm64）build & push し、利用者は `deploy/` の compose + `.env.example` で起動する（SPEC.ja §15.4）。`server/Dockerfile` に BUILD_NUMBER を焼き込み（コンテナの `/api/info` と `render_build_number` の null を解消）、`/api/info` の `version` を `server/pyproject.toml` 由来の単一情報源にしてリリースごとに採番（本リリースで 2.4.0）、nature-leaves プラグイン v0.3.0 を git 管理化してイメージ同梱、bootstrap admin の空文字を「未設定」扱いに是正して compose 側を `:?` で必須化した（セルフサインアップ不在の前提を manual / SETUP / SPEC に明記）。engine 10・Score schema・web UI は不変。

README 整備（2026-07-22、docs のみ・採番なし）では README 日英に作品ギャラリー 6 点（`docs/assets/gallery/`。作者のスター付き履歴から選定、絵 + 詞書 + `<details>` の指示書・SVG・seed）と UI スクリーンショット 6 点（`docs/assets/ui/`、日英各 3。`*.ja/.en.png` で各 README が自言語のみ参照）を追加し、構成を「作品 — 記述が絵になる → しくみ（実 Score の層解説）→ 画面 → … → ドキュメント（末尾へ）」に改訂した。GitHub のサニタイザ下で唯一残る枠線手段として単一セル `<table>` を採用し、`.gitignore` を `docs/*` + `!docs/assets/` に変更。白背景に溶けていた 2 点目は公開後に silver-shoal（B962）へ差し替え済み。コード・engine・採番は不変。

v2.4.2（Build 689）は歳時記語彙の日英ペアリングを構造で担保する改修。`SaijikiCategory` の `words_ja` / `words_en` という 2 本の並行タプルを廃し、`surface_ja` / `surface_en` を 1 エントリに持つ `SaijikiWord` の単一語列へ統合した（フラグは言語間で共有、`surface_en=None` で墓標語を表現）。あわせて てざわり・いろ の各語へ `score_value` を持たせ、語列と Score enum 値を `zip` していた `_surface_value_map` を削除（**てざわりの並べ替えが Score weight 値の取り違えに直結する**状態の解消）。あいだの `RelationWord` が元から採っていた形へ他カテゴリを揃えたもの。出力は日英 15 項目すべて変更前後で SHA-256 一致、生成 TS もバイト一致、`_EXPECTED_PAIRING` 68 ペアは無改変で通過。engine 10 のまま、語彙の増減・改称なし。pytest 1028/30（+2 構造テスト）。

v2.4.1（Build 687）は UI 調整 2 巡目。DDL エディタの語プレビュー全 69 エントリを日英化し、作業中に発見した歳時記語彙の日英対応バグ 2 件（削剪済み `髪`/`hair` の i18n 残置による 1 ずれ、`words_en` の並び非対応による解説の交差）を是正した。原因だった i18n の手書き複製 `saijikiWords` を廃止し、表示語はハイドレート済み `SAIJIKI` / `SAIJIKI_EN` から直接取得。全 68 語の日英対応を明示テーブルで固定するテストを追加。副作用として英語版 Stage 1 プロンプトの `motions:` 語順が変わる（集合不変、ベンチ未確認）。記述タブは短歌の目安をヒント文からカウンタへ移動。engine 10 のまま。UI 調整は対話で継続中。

v2.4.3（Build 693）は UI 調整 3 巡目。環境変数 `INKU_DEVELOPER_MODE` を新設し、NVIDIA NIM と常時表示の Build 番号を開発環境限定にした（**隠すのは表示だけで、実行経路・保存済みモデル設定・履歴のモデル情報・`render_build_number` は無効時も不変**。配布 compose は既定で無効、開発・ベンチ compose は既定で有効。SPEC.ja §15.4）。系譜と系譜全体図に共有の「縦／横」切替を追加（横は左から右へ世代が進み同世代は縦積み。矢印とスクロールも方向に追随し、選択はブラウザへ保存。系譜 API・スキーマ・保存データは不変）。デモに 1〜1,440 分（最大 24 時間）のタイムアウトを追加（既定 60 分。締切を越えても進行中の 1 件は完了・反映してから停止し、残り時間を `HH:MM:SS` で表示）。engine 10 のまま、Score schema / coerce / rh2 / renderer / stroke_engine は無変更。pytest 1029/30。あわせて SETUP 日英のコンテナ節新設と 3 件是正（**Python 要件が 3.10 以上と誤記、実際は 3.12 以上**ほか）、README 日英の再生成節を「推敲による作品の追求」へ全面改稿した分を本版へ畳んでいる。UI 調整は対話で継続中。

v2.4.5（Build 695）では作品エディションID を `rh3` へ移した。payload は `score` + `render_seed` + render engine の ID と版 + `render_color_catalog_id` の 5 つで、**`render_build_number` と `vary_seed` を外した**。build 番号は UI だけの変更でも採番されるため、**描画が 1 バイトも変わらないのにエディションIDが変わる**偽の差分を生んでいた（v1.60 で engine 版の採番規律が無い時代の保険として入ったもので、その役割は v1.99 以降 `render_engine_version` が引き継いでいる）。build 番号は来歴として保持する。**`rh2` は legacy として再計算せず保持し、`rh2` と `rh3` は別の hash 空間**（起動時 backfill は空の行にだけ rh3 を書く）。`render_hash` を等値比較する経路は server に無いため挙動は変わらない。SPEC §7 / §11.2。engine 10・renderer・schema・coerce は不変で、参照コーパスも再生成で差分ゼロ。pytest 1038/30。

v2.4.4（Build 694）では engine 10 の描画出力を凍結した。`server/reference/render-engine-10/` に 220 ケース（基盤 80 / 変奏 72 / 塗り・面・地 40 / 判別 28）の入力全文・digest・要素数・class を記録し、**再生成のバイト一致を CI（`.github/workflows/reference-corpus.yml`）が強制する**。目的は「どこが変わったとき描画結果がどう変わったか」を AI が判定できるようにすることで、**版数は 1 ビットしか運ばないため出力の実物を凍結する**。engine 1〜9 の出力は復元不能なので engine 10 から始める。入力は生成器側に literal で固定し（色表・Score 全フィールド）、`COLOR_MAP` も schema 既定値も参照しないため、コーパスを動かせるのは `renderer.py` と `stroke_engine.py` だけになる。副産物として **`ground.absorbency` が死にフィールドである確証**を得た（digest が動かない。本改修では直さない）。手順は成果物の隣 `server/reference/README.md`、契約は SPEC §15.5。`.gitattributes` で配布物からは除外。**描画結果は 1 バイトも変わらず**、engine 10・renderer・stroke_engine・schema・coerce・rh2 は不変。Phase 2〜5（rh3・ddl corpus・prompt digest・版差表示）は未着手。

Android 版（`android/`、Kotlin + Compose + Room、端末内で全パイプライン）は **`2.0.0-android.1` / Build 148077 で render engine 10 へ到達**（2026-07-23）。版の名前空間は web/server と別で、`android/VERSION` と `android/BUILD_NUMBER` が正本。移植は server を正本として後から追随する形であり、**server 側の設計を Android に合わせて曲げない**。詳細は CHANGELOG の Android entry と `android/ANDROID_SPEC.ja.md`。

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
