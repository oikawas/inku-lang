# inku プロジェクトコンテキスト

**対象バージョン: v2.7.9 / Build 718**

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

v2.4.8（Build 698）では演奏出力にマスターグリッドを宣言し、**render engine 11** とした。発端は `reference-corpus` ワークフローの 8 連続失敗で、原因は**凍結コーパスが macOS で焼かれ CI は Linux で再生成すること**だった（`math.sin` が 1 ulp 違い、`points` / `cx` / `cy` が svgwrite へ素の float のまま渡って 17 桁で出るため文字列差になる。220 件中 81 件・構造差 0 件・最大相対差 2e-16。pentala で再現して確定）。測ると **プラットフォーム雑音の床は小数 10〜11 桁**、**座標グリッドは `.1f`〜`.3f` と 17 桁の混在**、**形の忠実度はキャンバス比 2.2e-4**（ストロークは直線の連なりで出ており `L` 77,666 に対し `C` は 490）だった。つまり**桁は必要量の 200 倍あり、実効解像度を決めているのは標本化のほう**なので、これは解像度を削る変更ではなく**バラバラの桁を一つの宣言へ寄せる**変更である（描画幾何はむしろ 3 桁から 6 桁へ上がった）。`master_grid.py` が唯一の正本で、小数 6 桁固定＝キャンバス比 1e-9（雑音床より 4 桁上、100m の壁で 100nm）。**末尾ゼロは詰めない**（作者裁定。理由は容量でなく検査可能性で、桁が固定なら `-?\d+\.\d{6}` の 1 本で成果物から機械検査できる）。強制は `render()` の単一地点で行う（svgwrite の呼び出しは 48 箇所あり、一つずつ直す方式は漏れが黙って残る）。**描画は変わっていない** — 220 件すべてで数値の個数が一致し、どの数値も 5e-4（旧 `.3f` の半幅）を超えて動いていない。**engine 10 のコーパスは残す**（10 → 11 の差分が「桁だけが変わり形は変わっていない」ことの実物の証明になる。ただし macOS でしか再現できないため CI の対象外。README に明記）＝**参照コーパスの初めての実用**。CI の検査対象は `server/reference/` 全体へ広げた。検査は 2 本（新規演奏 3 プロファイル / 凍結 220 件）で、どちらも摂動で落ちることを確認済み。macOS arm64 と Ubuntu x86_64 で 220 件 + manifest がバイト一致。あわせて**参照コーパス Phase 4**（プロンプト来歴の digest）をマージした。歳時記は決定的な層から参照されず流入先が版を持たない Stage 1 プロンプトであるため、`stage1_prompt_base_digest` が唯一の検出手段になる（`stage2_prompt_base_digest` は作らない）。既存行は backfill しない。pytest 1062/30、cli 68、ruff clean、`npm run check` 0 errors / 2 warnings。**積み残しは Phase 2h で解消した**（下記 Android の段。engine 11 で `path d` が 6 桁固定になり Android の parity fixture は全滅していた）。

v2.4.9（Build 705）では再描画時に版差を利用者の画面へ言葉で見せるようにし、**参照コーパスとレイヤー版数の親契約（全 5 段）を完結させた**（Phase 5、SPEC.ja §15.8 の実装）。engine 10 → 11 の「桁だけが変わり形は変わっていない」を実物で示せる凍結コーパスを取ったのに続き、**その版の違いを画面上の言葉にする**段である。描画コア・stroke engine・Score schema・`server/reference/`・各版数（`render_engine_version="11"` / `ddl_version="1"` / `ddl_engine_version="1"`）はいずれも据え置きで、足したのは表示だけ。認証不要の `GET /api/info` へ `render_engine_id` / `render_engine_version` / `ddl_version` / `ddl_engine_version` の 4 フィールドを追加し（定数直書きでなく `current_render_engine()` と `DDL_VERSION` / `DDL_ENGINE_VERSION` から取得。テストは engine 実体を monkeypatch すると `/api/info` が追随することまで固定）、生成情報ドロワーへ「DDL 仕様 / 変換層」を出す（欠損時は**「記録なし」と表示し値を推測しない**。DB 1704 行のうち 590（35%）が engine 版の記録なしで、「記録が無い」と「版 1」を画面上で区別するための表示）。新規 `ReplayComparisonModal.svelte` は保存済み Score を `/api/render-svg` で現行 Renderer へ描き直し、**保存済み SVG（オリジナル）と描き直し SVG（現行）を左右に並べる**。版が違えば「この作品は engine 10 で描かれました。いま画面にあるのは engine 11 による描き直しです。」（英語併記）を作品の外・比較グリッドの上に置き（SVG へ重ねない）、記録版と現行版が同じ・`/api/info` 失敗・履歴を開くだけ、のときは通知しない。呼び出し元（履歴管理／作品タブ／系譜タブ）へ閉じたら戻り、キャンバス下部バーへ再現ボタンを足して `CanvasPanel` / `HistoryManager` の該当ボタンを `--btn-sm-*` トークンへ揃えた。作者追加指示で **seed 欠損作品の暫定比較**も入れ、`render_seed` と `seed_text` の双方がない履歴も比較可能にした（DB は書き戻さず比較の間だけ固定 seed `0` を補完。API が NULL 列を省くため**完全性の判定は `render_seed` フィールドの有無でなく保存済み `score` と `svg` の有無で行う**——この取り違えで Build 703 は下部バーの再現ボタンが無効だった。作者提供スクリーンショットで確認し Build 704 で修正）。**過去 Renderer の保持・選択・呼び戻し、保存済み SVG の差し替え、既存版数・`render_seed` の backfill、`/api/render-svg` 本文の変更、web テスト基盤の新設は行っていない**。仕様は動いていないため SPEC は触っていない。pytest 1063/30（+1 = `/api/info` の版フィールド）、cli 68、ruff clean、`npm run check` 0 errors / 2 warnings（新規モーダルを含む 217 files）、`npm run build` 成功。変更範囲は server 1 ファイル + test + web のみ。

v2.5.0（Build 706）では演奏を脱・規則化し、**render engine 12** とした。engine 11 までの演奏は揺らいで見えて周期的で、幅のエンベロープは `max(0, sin(pi t))` の固定した山（**どのストロークも中点でいちばん太く左右対称**）、補正イベントは `i % 5` の**周期 5 の反復**、閉輪郭は継ぎ目やせ／中央太りの定型、材質アウトラインは等間隔の破線と粒だった。この 4 つを seed 由来の低周波雑音（`_edge_window` × `_swell`）へ置き換え、`ToolGrammar` に 10 番目のフィールド `gesture` を足して**中心線そのものを長さ基準で振る**（曲がり・丸まり・自己の重なり。端点は窓で固定、決定性は seed が担保）。あわせて**「暴れる」（wild）トグル**を作品全体に一つ置いた（`WILD_GAIN = 3.5`）。**外すのは振幅の上限と自己交差の禁止だけで、端点の固定と決定性は ON でも保つ。** 生成時のパラメータとして記録し（`history.render_wild`、NULL = 記録前で OFF と区別）、再現に使い、**エディション ID `rh3` の材料に含める**。材料が変わったが `render_engine_version` が同じ payload に入っているため旧値は必ず `"11"` 以下・新値は必ず `"12"` 以上を含み衝突しないので形式名は据え置いた（**engine 版を同時に上げたから成り立つ論法**であり、材料の追加だけを単独で行ってはならない）。参照コーパス `render-engine-12/` を凍結し、**220 件中 199 件が変化・21 件が不変**。不変の内訳がそのまま engine 12 の説明で、`rotring` の 12 件は揺れ項がすべて 0 なので脱・規則化が届かず（**道具語彙の機械の極は同じ位置にある**）、`cloudform` の 9 件は Catmull-Rom パスとして書かれ `stroke_engine` を通らないため（**engine 12 が作った穴ではなく露わにした穴**）。これに伴い「動いた分だけ保存する」規律を生成器へ実装した（README と SPEC は以前からそう定めていたが、engine 11 は全件が動いたので**区別がつかなかった**）。版を上げる条件に**「演奏できる語彙が増えたとき」**を足した（作者裁定。道具を足しても既存ケースは出力が動かず CI が落ちないため、結果だけを条件にすると版数の意味が入力の集合のほうで崩れる）。SPEC は §13.4 に「暴れる」、§15.6 に条件拡張と `rh3` の注記、§15.7 に engine 12 の実測を追記。**Android の追随、てざわりへの「コンピュータ」追加、`cloudform` のストローク化、既存履歴の `render_wild` backfill は行っていない**。pytest 1066/30（+7）、cli 68、ruff clean、`npm run check` 0 errors / 2 warnings。再ベースラインした golden 6 件は `_swell` の 1e-6 摂動で全件落ちることを確認済み。

v2.6.0（Build 707）ではてざわりに 11 番目の道具**「コンピュータ」**を足し、**render engine 13** とした。核は「手が震えない」ではなく**「誤差なく反復する」** — 手は同じ値を二度出せず、計算機は同じ値しか出せない。**周期＝線に沿った方向の反復／格子＝空間方向の反復**で同じ性質の 2 軸である。`rotring` との区別はここで立つ（**rotring は反復すべき揺れを持たない**が、**コンピュータは揺れを持ち正確に繰り返す**）。engine 11 の対称エンベロープへの後戻りではない（engine 11 のそれは**選べない既定**、engine 13 のこれは**選べる語彙**）。実装は `ToolGrammar` に `periodic` / `quantize` / `width_steps` を足し（既存 10 道具はすべて 0 で無改変）、`periodic` のとき雑音源を整数周期の正弦へ差し替え（**seed を引数に取らない**）、中心線を `ストローク長 × 0.018` の格子へ丸め、幅を 4 段に落とす。`wild` は効かない。**材質は「標本化の残り」である** — 手の道具の材質層は道具が線の脇に落とすもの（黒鉛の粉、筆の毛）だが、計算機にあるのは**格子へ丸めるときに捨てた差**だけである。標本ごとの残差が 0 でないところにだけ格子 1 セルの正方形（`raster-bleed`）を敷き、**格子に丸めた座標**へ置いて残差に比例した濃さにする（上限 0.45）。**幾何が「誤差なく反復する」／材質が「誤差を捨てた跡」を見せる。** 端点と多角形の角は意図へ戻されるので残差を持たずセルも出ない（直線 41 標本中 39）。**この材質は第 1 版を作者目視で捨てた結果である** — 最初の「まっすぐな定規の線 + 全数同一の等間隔 dash」は、演奏された中心線が意図から最大 55.4px 離れるため点線が線から切り離されて独立した罫線に見え、**「絵画上の意味がない」**と裁定された（代案の「格子ハロー」も、丸めの大小と無関係に一様に付くので退けた）。数値（格子 0.018・濃さ 0.45・セルは格子に乗せる）は 9 面 + 2 面の比較画像を描いて作者が選んだ。参照コーパス `render-engine-13/` は 228 件で、新規は `A-computer-*` の 8 件のみ・**既存 220 件の digest は 1 件も動かない**（**版木を足しても前の刷りは変わっていない**ことの校正刷りであり、SPEC §15.6 の「演奏できる語彙が増えたとき」で版を上げた最初の例）。材質の作り直しで再生成したとき生成器のガード（凍結済みを同じ版で書き換えるな）が発火したので、**未リリースの engine 13 は版を上げず凍結し直した**。SPEC は §15.9 を新設（英語は §12.6）。**Android の追随、閉輪郭専用の半径変調、走査線・ディザ・面のテクスチャ、既存 10 道具の演奏値の変更は行っていない**。**格子が絶対座標に効き目盛が長さに比例する点（同じ長さの線 30 本で異なる図が 9 種）は未裁定のまま据え置いた。**pytest 1091/30（+2）、cli 68、ruff clean、`npm run check` 0 errors / 2 warnings。摂動 3 件で判別力を実測し、**格子への丸めの摂動は開いたストロークでは素通りしたので閉輪郭の検査を足した**。

v2.6.1（Build 708）では**英語 UI の用語**を版画・音楽・短歌の語彙へ揃えた。**英語表示だけの改修で、日本語は 1 文字も変えていない。** inku は「楽譜と演奏」（音楽）「版木と刷り」（版画）「詞書と歳時記」（短歌・俳句）の三系統のメタファーで出来ているので、英語も各系統の英語圏での正統な術語を使い、生成 AI 業界語（prompt / generate）でなく工房の語（write / paint / perform）を優先する。**英語表示は 3 系統あった** — i18n パック `en.ts` の 641 項目、コンポーネント内の `isJapanese ? … : …` 三項式 132 箇所（12 ファイル）、`getLang() === 'ja'` 分岐 15 箇所。**i18n パックだけ直すと 147 箇所が旧語彙で残る**ので 3 系統を棚卸ししてから当てた（書き換え 236 項目）。五つの推敲操作は **`Another performance` / `Another composition` / `Another reading` / `Another catalog` + `Variation`** とし、「何を引き直し、何が保たれるか」が名前だけで対比できるようにした（ボタン幅が厳しくても名詞を省略せず折り返す）。変奏の強度は **`Subtle` / `Moderate` / `Sweeping`**（音楽の変奏に Large は使わない）で、**同時に配置推敲のコスト表示の `Moderate` を `Medium` へ直した**（一語二義を作らないため）。一語一義は `interpretation` / `reading` / `performance` / `variation` / `sway` / `color catalog` の 6 語に敷き、**`palette` は 0 件**（色カタログは inku 独自概念）、**UI 文中の `rendering` も 0 件**。ローマ字残しは **`Saijiki` と `inku` だけ**にし、`Okugaki` → **`Colophon`**、`Kotobagaki (caption)` → **`Headnote`** とした（ローマ字を増やすとエキゾチシズムに寄り道具としての信頼を損なう）。`Generation Info` → **`Provenance`**、`artwork` → **`work`**（残存 0）、`Unleashed` → **`Wild`**、主動作ボタン `Generate` → **`Paint`**。マイクロコピーは文単位で書き直し、段階表示は **`Interpreting your words…` / `Writing the score, then performing…`**、版差の通知は **`This work was performed by engine N. What you see now is a new impression by engine M.`**（版画の刷りの語）にした。**歳時記のカテゴリ名は 1 語も触っていない** — 英語カテゴリ名は web の文字列ではなく `saijiki.py` の `name_en` で、**`prompt_block("en")` を通って英語 Stage 1 プロンプトへ流入している**（golden fixture が固定）。**これは UI 表示ではなく英語版 DDL の語彙仕様**なので辞書の推奨を適用せず作者へ報告した。**辞書と実装が食い違った 2 点は実測を採った** — 五操作の根拠とされた「日本語の『別の◯◯』」は実際には「◯◯を変える」の動詞形であり（作者裁定で英語だけ名詞形）、`settingsGenerationLabel` は「世代」でなく `'生成'`（行為）だった。**日本語が動いていないことは md5 指紋 3 つ**（`ja.ts` / 三項式の日本語側 132 箇所 / `getLang()` 分岐の日本語側 14 箇所）**で機械的に担保**した（`LC_ALL=C sort` でロケールを固定しないと内容が動かなくても値が変わる）。`npm run check` 0 errors / 2 warnings（217 files）、i18n の鍵は 641 のまま日英一致、`server` / `cli` / `android` と `saijiki.ts` の差分ゼロ。摂動 4 件で判別力を実測。**英語ドキュメント（README.md / SPEC.md / `manual/en/`）は未追随で、UI 側だけが新語彙になっている**（`artwork` が SPEC 25 / manual 26、`palette` が SPEC 12 など。別作業）。

v2.7.0（Build 709）では**一枚の方眼**と**暴れるの到達**をまとめ、**render engine 14** とした。engine 13 が残した 2 つの穴で、どちらも演奏結果が動くので 1 つの版にすればコーパスの再凍結が 1 回で済む。**方眼は紙の性質であって、置かれた対象の性質ではない** — engine 13 の目盛は**ストローク長に比例**しており（`step = 長さ × 0.018`）、長さが違えば目盛も違い（100px→1.8 / 800px→14.4px）、**同じ長さでも位置で位相が変わる**（同一長の線 30 本で 30 種の図）ため、1 枚の絵に**大きさの数だけ方眼**が同居していた。engine 14 は **`キャンバス短辺 × quantize`** で決める（値は 0.018 のままだが**意味が変わった**）。`stroke_engine` はキャンバスを知らないので **renderer が px へ直して渡し、長さ相対の経路は 4 箇所とも削除**した。正方 1000px で 18.000000px、短辺基準なのでアスペクトで変わる（pillar 3.600px）。**同じ絵のすべてのストロークが同じセルへ落ちる**（大小 3 対象の同居で格子外れが 188/194 → 0/194）。**暴れるは `line` にしか届いていなかった** — 88 組中 63 組が ON/OFF でバイト一致しており「作品全体に一つ」という位置づけとずれていた。`synthesize_along`（円・楕円・三角・四角・多角形・弧・塗り・ハッチ）へ届かせ、**OFF は 1 バイトも変えない**。**一致してよいのは 25 組ちょうど**（`cloudform` 全 11 = `stroke_engine` を通らない既知の穴・未修正、`rotring` 7 = `gesture` 0、`computer` 7 = `periodic`）。**素朴な移植は 3 点で壊れる**（弧長で振幅を決めると閉輪郭が破綻／平均が 0 でないと図形が伸縮＝**大きさは楽譜が決めるもので演奏が変えてよいものではない**／角の隣にジェスチャが乗るとトゲ）。**材質が墨から離れる問題も直した** — 輪郭と弧の材質アウトラインは幾何から引かれていて、暴れると 9 組すべてで墨だけが動き材質が取り残された（engine 12 が線について直したのと同じ型）。**ON のときだけ演奏後の中心線から作る**。参照コーパス `render-engine-14/` は **347 件**（`corpus_format_version` `"1"`→`"2"`）で `changed_from_previous` **126 件**＝既存 7 件（`A-computer-*` から cloudform を除く）+ 新規 E 群 119 件、**不変 221 件**。**手の 10 道具は 1 件も動かない。** 契約の赤（セル数・座標・25 組・9 組）は**起票時に実測して先出ししてあり、実装も受け入れの測り直しも 1 桁違わず一致**した。**摂動で「検査が 1 段少ない」ことが分かった** — 長さ相対への差し戻しを `synthesize_stroke` 内だけに当てると格子の検査 2 本が落ちない（`_add_raster_bleed` がセルを渡された目盛へ**再スナップ**するため）。**同じ性質を 2 箇所で強制していると片側の摂動は下流に吸収される。** 受け入れ側でも材質の摂動を弧側・閉輪郭側に分けて当て、どちらでも落ちることを確認した。SPEC は §15.10 を新設（英語 §12.7）し、**英語版の「Unleashed」を UI の「Wild」へ揃えた**（README と `manual/en/` の食い違いは残っている）。pytest 1100/30（+9）、cli 68、ruff clean、`npm run check` 0 errors / 2 warnings。**`android/` に差分が無いので Android のテストは回していない。Android は engine 12 のままで遅れが 2 版に広がった。**

v2.7.1（Build 710）では**英語用語の正本と、それを強制する lint** を足した。v2.6.1 は英語 UI を辞書へ揃えたが、**揃った状態を保つものを残していなかった** — 文字列を 1 つ足すだけで禁止語が戻り、同じ概念に 2 つ目の英語が当たる。`web/src/lib/i18n/GLOSSARY.md`（200 行）が正本で、英語表示が 3 系統あること（`en.ts` 641 / 三項式 132 / `getLang()` 15）、コア用語、五つの推敲操作と変奏の強度の固定値、文体規則、禁止語と**許容される例外**、触ってはいけない経路、新しい文字列を足す手順、検査が見ているもの、まだ残る食い違いまでを書いてある。`web/scripts/i18n-lint.mjs`（221 行、`npm run lint:i18n`）が**英語表示 788 文字列を走査し、許容例外 36 件を名前で通す**。**文面と検査は一対**で、片方を変えたら同じ commit でもう片方も変える。**「残存ゼロ」を条件にしない** — `generation`（世代）・`prompt`（LLM プロンプトの表示）・`created`（完了・日時）・`image`（Vision が見る画像）・`render`（サーバー技術設定）には正当な用法があるので、**どこにも書いてはいけない語**と**決められた場所にだけ許される語**を分けてある。判別力は受け入れ側で実測した（`colorCatalogTitle` を `Color palette` にすると 1 件落ち、戻すと 0 に戻る）。あわせて `en.ts` の 1 項目を Sentence case へ是正（lint が見つけた取りこぼし）。`npm run check` 0 errors / 2 warnings、`lint:i18n` 788 / 36 例外 / 0 errors、pytest 1100/30、cli 68、ruff clean。**英語ドキュメント（`README.md` / `manual/en/` / `SPEC.md` の残り）の追随は未実施で、lint は `web/` の表示文字列しか見ていない。**

v2.7.2（Build 711）では**誰も読まない 2 つのフィールドを退役させた**（`absorbency` と `contact`）。**読まれていないだけでは無害と言えない** — 地の texture seed は Score 全体の dump のハッシュなので、値を使わないフィールドでも消せば粒の配置が動く（保存済み 23 件のうち 18 件）。退役キーは検証前に落とす（`extra="forbid"` があるため）。

v2.7.3（Build 712）では **CLI の英語表示を用語辞書へ揃えた**（`artwork` ほか 3 箇所とマニュアルの引用）。`npm run lint:i18n` は `web/` の表示文字列しか見ないので、**CLI とドキュメントは手で追う**。サブコマンド名 `okugaki` は識別子なので裁定待ちのまま残した。

v2.7.4（Build 713）では **coerce を `normalize` と `compose` に割った**。**構図を決めているのは Stage 2 でも Renderer でもなくここである**（本番 60 作品で instruction の 27% は DDL でなく coerce 製）にもかかわらず、34 分岐が一列に混ざっていた。分割の判定基準は「`ddl` を引数に取るか」— 主観を避け機械検査できる基準にするため。振り分けは normalize 6 / compose 28 で、**呼び出し順は 1 行も動かしていない**（両者は交互に並んでおり、まとめると結果が変わる）。同一性はゴールデン 39 ケースのバイト差 0 と、分岐ごとの恒等関数差し替えで動くケース数の完全一致で確かめた。**凍結コーパスは coerce を守っていなかった** — `render-engine-14` の 347 件は `coerce_score` を呼ばず、34 分岐を全部殺しても緑になる。そのためのゴールデン 39 ケース（`server/tests/golden/coerce_golden.json`）を同時に作った。

v2.7.5（Build 714）では**明示された個数を 240 未満なら literal**とした。**「二百三十三本」と書いて 2 本しか描かれない**状態の原因はプロンプトの自己矛盾で、①「120 個を超えたら代表化」と「代表化は 300 以上」が 120〜299 帯で競合、②「複数 instruction 生成は絶対禁止」が個数の違う群まで畳ませる、③**作例 4 件が要求 137 に対し `"count":96` を出して見せていた**、の 3 つが重なっていた。閾値 240 は `MAX_EXPANDED_PER_INSTRUCTION` に合わせた値である。**プロンプトが効く層（coerce の手前）では最低だった 120〜239 帯が日本語 33%→55% / 英語 37%→92% に動いたが、final Score は動かない。** 完全に遵守した Score を coerce へ通すと単群 25 文のうち通るのは日本語 20 / 英語 11 で、`_with_context_density_governor` が 64 / 48 / 16 へ置き換える。**受入条件 90〜95% は、契約が禁じた coerce と compose に触れない限り到達できない値だった。** 日英差も同じ層にあり、静けさ密度マーカーの発火は日本語 36/87 に対し英語 72/87。**個数の忠実さは、次に compose 側の決定的な強制として扱う。**

v2.7.6（Build 715）では**書かれた個数を、後からの読みより強くした**。v2.7.5 でプロンプトの矛盾を消したのに final Score が動かなかったのは、`_with_context_density_governor` が静けさ・膜・記憶系の文脈を読み取って**見つけた反復を残らず間引いていた**からで、書かれた個数の群も対象にしていた。**静けさは場面の読みであり、「二百三十三本」は読みではない。** 明示個数の群は 3 つの個数上限を素通りする（大きさを整える処理はそのまま働く。いくつを触るものではないため）。**凍結 50 ケースが 31/50 → 50/50、日英とも 25/25**（着手時は英語 11/25）。**日英差の正体は英語マーカー `"one "`** が `one hundred twenty ... lines` に当たっていたことだが、**単独では 1 件も救わない**（帰属は免除が 19 件）。あわせて合計予算の比例縮小をやめ、**大きい群から順に代表化して予算を下回った時点で止める**ようにした（旧実装は**要求 120 の群を 232 へ増やしていた**）。**この検査面は LLM を 1 回も呼ばずに 2 秒で回る。**

v2.7.8（Build 717）では **render engine 15** として `renderer.py` への 5 つの変更を 1 つの版にまとめた。**印の種を allowlist にした**（dump 全体のハッシュだったので、coerce が書いた色の注記を書き換えるだけで絵が変わっていた。全 49 フィールドの感度は 30 動く / 19 動かない）。**地の種は支持体の名前にした**（`material` + `grain` + 演奏 seed。濃さを上げても同じ紙が濃くなる。これで `ground.absorbency` の退役が解けた）。**`cloudform` をほかの閉輪郭と同じ道に載せた**（class に `stroke-engine-touch` を名乗りながら一度も `stroke_engine` を通っていなかった）。**角のある図形と `pen` に材質層を与えた**（`_render_corner_shape` には呼び出しがそもそも無く、本番最多の `pen` も裸だった）。**強さは距離ではない**と直した（梯子が対処のたびに `outline_offset` の倍率を上げて 2.8 倍・下限 3.5px になり、痕跡が帯の実測半幅の 4.5〜6.5 倍離れて第 2 の輪郭に見えていた。倍率 1.0・下限 0 へ。濃さの梃子は不変）。コーパスは **350 件で 318 件が動き、動かない 32 件（`computer` / `rotring`）が版の説明になる**。**`hair` は材質層を与えたうえで撤去した** — 全面廃止が妥当という作者裁定を受けたためで、**廃止本体は別契約**。

v2.7.9（Build 718）では `hair` を **`silverpoint`（銀筆）へ改名した**。engine 15 の時点では「全面廃止」の裁定だったが、**廃止先の `pencil` は 3 倍太く**、0.5px・stiffness 0.93・energy_width 0.08 という値は筆ではなく**銀筆の物理**だったため、2026-07-27 に改名へ変わった。**改名は絵を動かす** — 演奏 seed の材料に `weight` が入っているので、道具名の文字列が変われば同じ Score が別の演奏になる（`A-hair-line` と `A-silverpoint-line` は 2299 → 2306 バイト、座標 126 個中 120 個が移動）。作者は比較シート 2 枚を見たうえでこれを払うと裁定した。動いたのは**名前を持つ 16 件だけ**で、コーパス 350 件のうち共通の 334 件はマニフェスト entry がバイト差 0・SVG 実体 302 本が全部バイト一致。coerce ゴールデンは 39 件中 10 件を採り直し、**旧 expected の `hair` を置換すると新 expected に完全一致する**。保存済み作品は `Instruction.weight` の `field_validator(mode="before")` が読み込み時に置換し、**本番 DB の該当 445 件を全部 replay して 444 件が受理**（残り 1 件は `Weight` enum に一度も無い `rope` を持ち、改名前から replay 不能）。**`GRAMMARS` と幅の値は 1 つも変えていない**（変更 3 行はキー文字列以外が一致。8 値 + 機械の極の 3 値を直接ピンする検査を新設）。**唯一の振る舞いの変更は語彙復帰**で、歳時記の `_PRUNED` を外しててざわりが 10 語から 11 語になり、材質マーカーの先頭が `鉛筆` → `銀筆` に変わった（H1「銀筆が実際に選ばれるか」を測るには語彙に無ければならないため）。プロンプト digest の固定値 16 個を採り直したが、**Stage 1 の golden fixture は Build 591 の実物のまま**。**engine の版は上げていない**（`"15"` のまま）。**未着手**: few-shot 検索キーワード `"髪"` への銀筆追加、`material_weight_hints` の銀筆行、太さの軸、Android（Kotlin と凍結 fixture 36 件は `hair` のまま）。

v2.4.7（Build 697）では決定的な DDL 層を凍結した。`server/reference/ddl-engine-1/` に 29 ケース（A = 展開 15 / B = 補正 14）を焼き、`ddl_version` と `ddl_engine_version` を **1** から導入した（正本 `layer_versions.py`）。**A と B は連結していない** — B の入力 Score は生成器内の literal で、A の出力を渡していない（連結すると展開側の欠陥が補正側の欠陥を覆い隠す）。**決定的な層は隣り合っておらず**、Stage 1.5 と coerce のあいだに Stage 2 の LLM が挟まるため、1 本の基準線にできないことがこの分割の理由である（SPEC §15.5）。判別の中心は `ddl` 引数の有無（同じ Score が発火 0 → 6・instruction 1 → 3）と `tenkei` 三段（発火 6 / 4 / 3・instruction 3 / 2 / 1）で、発火しないケースも固定した。`branch_report` は全体のキー集合を固定せずケースごとの対応だけを固定する。両版は新規作品の応答・履歴・保存 artifact に乗るが、**既存行は backfill しない**（記録の無い版数を推測して埋めることは来歴の捏造にあたる）。**`ddl_*` は rh3 の payload に入れていない**ので作品エディションID は不変。CI は `ddl-engine` job を独立させ、**A 側・B 側の両方から摂動して実際に落ちることを確認した**。engine 10・renderer・stroke_engine・schema・coerce は不変で、render corpus は再生成で 220 件すべて差分ゼロ。pytest 1043/30。**積み残し**: 歳時記は決定的な層から参照されておらず（流入先は Stage 1 のプロンプト＝版を持たない層）、**語が増えてもこのコーパスは動かない**。語彙の追加は `ddl_version` を上げる事象だが検出機構はまだ無い（Phase 4 の `stage1_prompt_digest` が半分を担う）。Phase 4〜5（prompt digest・版差表示）は未着手。

v2.4.5（Build 695）では作品エディションID を `rh3` へ移した。payload は `score` + `render_seed` + render engine の ID と版 + `render_color_catalog_id` の 5 つで、**`render_build_number` と `vary_seed` を外した**。build 番号は UI だけの変更でも採番されるため、**描画が 1 バイトも変わらないのにエディションIDが変わる**偽の差分を生んでいた（v1.60 で engine 版の採番規律が無い時代の保険として入ったもので、その役割は v1.99 以降 `render_engine_version` が引き継いでいる）。build 番号は来歴として保持する。**`rh2` は legacy として再計算せず保持し、`rh2` と `rh3` は別の hash 空間**（起動時 backfill は空の行にだけ rh3 を書く）。`render_hash` を等値比較する経路は server に無いため挙動は変わらない。SPEC §7 / §11.2。engine 10・renderer・schema・coerce は不変で、参照コーパスも再生成で差分ゼロ。pytest 1038/30。

v2.4.4（Build 694）では engine 10 の描画出力を凍結した。`server/reference/render-engine-10/` に 220 ケース（基盤 80 / 変奏 72 / 塗り・面・地 40 / 判別 28）の入力全文・digest・要素数・class を記録し、**再生成のバイト一致を CI（`.github/workflows/reference-corpus.yml`）が強制する**。目的は「どこが変わったとき描画結果がどう変わったか」を AI が判定できるようにすることで、**版数は 1 ビットしか運ばないため出力の実物を凍結する**。engine 1〜9 の出力は復元不能なので engine 10 から始める。入力は生成器側に literal で固定し（色表・Score 全フィールド）、`COLOR_MAP` も schema 既定値も参照しないため、コーパスを動かせるのは `renderer.py` と `stroke_engine.py` だけになる。副産物として **`ground.absorbency` が死にフィールドである確証**を得た（digest が動かない。本改修では直さない）。手順は成果物の隣 `server/reference/README.md`、契約は SPEC §15.5。`.gitattributes` で配布物からは除外。**描画結果は 1 バイトも変わらず**、engine 10・renderer・stroke_engine・schema・coerce・rh2 は不変。Phase 2〜5（rh3・ddl corpus・prompt digest・版差表示）は未着手。

Android 版（`android/`、Kotlin + Compose + Room、端末内で全パイプライン）は **`2.0.0-android.1` / Build 148080 で Phase 2 完了＝ render engine 10 の移植が全段そろった**（2026-07-24。engine 10 への到達自体は 2f / Build 148077）。版の名前空間は web/server と別で、`android/VERSION` と `android/BUILD_NUMBER` が正本。移植は server を正本として後から追随する形であり、**server 側の設計を Android に合わせて曲げない**。**Phase 3a（Stage 1.5 展開層の中核）に続き、Phase 2h でマスターグリッドへ追随して Android の `render_engine_version` は `"11"` になり（幾何は 1 行も変えず数値を文字列にする箇所だけを 6 桁固定へ）、さらに Phase 3b（変奏）までマージ済み**（android Build 148082、2026-07-24）。Phase 3b は `variation_amplitude` と `variation_seed` が揃ったときだけ DDL 本文と `variation_report` を決定的に変換する層で、焦点 `focus` もここに入る。受け入れでは 16 ケースの出力完全一致に加え、**16 件すべてが持つ `variation_report`（`moved_axes` と `resolved_focus`）を照合**し、符号なし seed 化と report 照合の判別力を摂動で確認した。**Phase 3d（組み込み Nature プラグイン展開）をマージして Stage 1.5 展開層の移植は完了した**（android Build 148083、2026-07-25。3c の添景は 3a 移植時に含まれており、コーパス 13 件が着手時点でバイト一致していたため作者裁定で独立段を立てずに完了扱い）。受け入れではコーパス 3 件の期待値を現行 server 実装で再計算して一致を確認し、マクロ文言の摂動で 3d テストが落ちることまで見た。**engine 12 への描画層追随も完了した**（`2.1.0-android.1` / android Build 148089、2026-07-25）。脱・規則化（`gesture` と 4 関数）・材質アウトライン層・「暴れる」の結線（**`line` にだけ届く。server がそうなっているため**）・`rh2` → `rh3`（Room v4 と UI トグル込み）。**材質層は 1 度差し戻した** — 初回は移植ではなく別実装で、`points` が **0/234 点一致・最大 16.4px ずれ**だったが、**既存テストが `path d`・class・要素数しか見ていなかったため 100% PASS で通っていた**。受け入れで検査を全 16 件へ広げると `11_cloudform_pencil` の texture dash が**素のリテラル**（`1,3` 対 `1.000000,3.000000`）で、**Phase 2b′ 以来の欠陥**が見つかったので直し、**全 16 件を `path d` / `points` / `stroke-dasharray` で比べるテストを恒久化**した。テストは 64 → **68 件**。**2026-07-26 に `2.1.1-android.1` / Build 148090 で engine 13 と 14 を 1 契約でまとめて追随し、Android も render engine 14 を名乗るようになった**（コンピュータの道具・キャンバス短辺基準の一枚の方眼・暴れるが輪郭へ届くこと・てざわり語彙を server の 10 語へ是正）。テストは **71 件**。詳細は CHANGELOG の Android entry と `android/ANDROID_SPEC.ja.md`。

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
