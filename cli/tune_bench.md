# inku-cli Tune Bench

`inku-cli` を使い、CLI ベースで指示文から描画を生成し、成果物を評価して Stage 1 / 1.5 / 2 の修正方針を決めるための手順。

## 目的

- Web UI の操作を介さず、同じ API 面から大量の描画を生成する
- PNG / SVG / JSON / DDL / elapsed / token を保存し、失敗傾向を蓄積する
- 単発の印象ではなく、複数サンプルの統計から修正対象を決める
- 最終的に Stage 1 prompt、Stage 1.5 filter、Stage 2 prompt/schema、renderer/coerce の修正案へ落とす

## 前提

pentala の `inku-api` が LAN から到達可能であること。

```sh
curl -i http://192.168.0.89:8100/health
```

CLI は root 直下の `cli/` で実行する。

```sh
cd /Users/oikawas/projects/ddl-server/cli
uv run inku-cli login --base-url http://192.168.0.89:8100 -u admin
```

Stage 1 / Stage 2 の既定 provider / model は CLI 側に保存できる。保存後は `paint` / `batch` で自動的に使われ、描画時にも stderr に表示される。provider は `nvidia` / `anthropic` / `local` のいずれか。

```sh
uv run inku-cli models \
  --timeout-seconds 600 \
  --stage1-provider nvidia \
  --stage1-model google/gemma-4-31b-it \
  --stage2-provider nvidia \
  --stage2-model google/gemma-4-31b-it
uv run inku-cli models
```

生成物は `cli/out/` 以下に保存する。`cli/out/` は Git 追跡対象外。

## 1. パイロット

まず 10 件で実施する。いきなり 30〜50 件に増やさない。評価ラベルや観点に抜けがあった場合、再評価の負担が大きくなるため。

入力文は 90 文字以内を基本とし、以下を混ぜる。

- 季節
- 都市
- 自然
- 静物
- 抽象
- 人物不在の情景

例:

```sh
uv run inku-cli paint "霧の朝、古い橋の影が川面にほどけていく。" \
  --base-url http://192.168.0.89:8100 \
  -o ./out/tune-pilot \
  --prefix pilot-001 \
  --png \
  --full-json
```

描画時の HTTP timeout は既定で 600 秒。実行中は stderr に使用モデル、経過時間、簡易アニメーションを表示する。ログを静かにしたい場合のみ `--no-progress` を使う。

## 2. 保存対象

各サンプルで以下を保存する。

- `*.png`: 最終描画
- `*.svg`: SVG 構造とレンダリング結果
- `*.json`: API レスポンス全体
- 入力文
- 正規化 DDL
- JSON Score
- Stage 1 / Stage 2 elapsed
- Stage 1 / Stage 2 tokens

## 3. 評価観点

### 芸術的観点

- 余白があるか
- 焦点があるか
- 構図が主題に沿っているか
- 視線誘導があるか
- 単調な均等配置に落ちていないか
- 素材感、線質、密度の差があるか
- 入力文のニュアンスが残っているか

### 技術的観点

- 入力文と DDL が対応しているか
- DDL と JSON Score が対応しているか
- 指示された数量、配置、軌跡、塗りが反映されているか
- プリミティブ数が過剰ではないか
- 真円 / 楕円 / 四角など特定図形に偏っていないか
- 色コントラストが確保されているか
- `filled` 指定と SVG 出力が一致しているか
- Stage 2 が遅すぎないか（ただし、接続先がdeveloper用LLM APIであり、待ち行列の状況次第で応答速度が変わるので、指標としては重要では無い）

### パイプライン観点

- Stage 1: 入力文を過度に一般化していないか
- Stage 1.5: 技法や法則を足しすぎていないか
- Stage 2: DDL の数量・配置・素材指示を JSON に反映できているか
- renderer/coerce: Score の意図と SVG 出力が一致しているか

## 4. 評価ラベル

評価は文章だけでなく、ラベルでも記録する。

```text
center_bias
overcrowded
circle_or_ellipse_bias
lost_subject
weak_composition
low_negative_space
axis_like_lines
random_scatter
path_not_reflected
fill_mismatch
low_color_contrast
stage1_overgeneralized
stage15_overexpanded
stage2_ignored_instruction
renderer_policy_mismatch
slow_stage2
```

必要に応じて追加する。

## 5. 評価記録フォーマット

サンプルごとに評価メモを残す。

```md
## sample-id

Input:

DDL:

Artifacts:
- png:
- svg:
- json:

Metrics:
- stage1_ms:
- stage2_ms:
- total_ms:
- stage1_tokens:
- stage2_tokens:

Labels:
- 

Evaluation:
- 良い点:
- 問題:
- 原因推定:

Fix Ideas:
- Stage1:
- Stage1.5:
- Stage2:
- renderer/coerce:
```

## 6. 本番ベンチ

パイロット 10 件で評価ラベルと記録形式が妥当であることを確認した後、30〜50 件に増やす。

推奨:

- 30 件: 初回の統計分析
- 50 件: 修正前後の比較やモデル差分比較

バッチ入力ファイルを用意する。

```text
春の雨が古い瓦を静かに濡らしている。
夜明け前の駅で、白い息だけがホームを渡る。
風のない午後、紙片が机の端で影を作る。
```

実行:

```sh
uv run inku-cli batch \
  --base-url http://192.168.0.89:8100 \
  -f ./prompts/tune-001.txt \
  -o ./out/tune-001 \
  --prefix tune-001 \
  --png \
  --continue-on-error
```

## 7. 集計

評価後に以下を集計する。

- ラベル別発生頻度
- 入力ジャンル別の失敗傾向
- Stage 別原因比率
- 重大度の高い問題
- 複数問題に効く共通原因
- elapsed / tokens の外れ値

特に優先して見る項目:

- `lost_subject`
- `overcrowded`
- `center_bias`
- `circle_or_ellipse_bias`
- `random_scatter`
- `path_not_reflected`
- `fill_mismatch`
- `slow_stage2`

## 8. 修正方針のまとめ方

最終出力は、実装対象ごとに分ける。

```md
# Tune Bench Summary

## Dataset
- samples:
- date:
- branch:
- stage1 model:
- stage2 model:

## Top Issues
1.
2.
3.

## Stage1 Changes
-

## Stage1.5 Changes
-

## Stage2 Changes
-

## Renderer / Coerce Changes
-

## Tests To Add
-

## Risks
-
```

## 9. 実施結果: 10件パイロットと30件ベンチ

Date: 2026-05-01

Branch: `tune-ddl-generation-cli-bench`

Model:

- Stage 1: `nvidia` / `google/gemma-4-31b-it`
- Stage 2: `nvidia` / `google/gemma-4-31b-it`

Artifacts:

- 10件パイロット: `cli/out/tune-pilot-001/`
- 30件ベンチ: `cli/out/tune-bench-030/`
- 30件ベンチの一覧画像: `cli/out/tune-bench-030/contact-sheet.png`

### 10件パイロット

CLI 実行結果:

- success: 10
- failed: 0
- total elapsed: 603,627 ms
- average elapsed: 60,363 ms
- median elapsed: 22,220 ms
- max elapsed: 227,804 ms
- tokens in: 89,153
- tokens out: 6,305

観察結果:

- `pilot-003` は API としては成功したが、`instructions: []` で実質的に空白描画だった。
- 背景色は gray が 8/10 と強く偏っていた。
- `pilot-009` は gray 背景に gray 系の極小プリミティブが乗り、視認性が低かった。
- 中央配置、軸線、均等配置に寄りやすく、入力文の焦点や余白の扱いが弱かった。
- 一部のサンプルは Stage 2 が 2〜3分以上かかり、遅延外れ値が大きかった。

主要ラベル:

- `low_color_contrast`
- `center_bias`
- `weak_composition`
- `stage2_ignored_instruction`
- `slow_stage2`
- `renderer_policy_mismatch`

この結果を受け、以下を修正した。

- gray 背景を避け、gray 背景が出た場合は white に寄せる。
- 同色背景/前景や白地に白線のような低視認性を coerce で補正する。
- 極小の非塗りつぶし図形が実質不可視になるケースを補正する。
- Stage 2 が空の `instructions` を返した場合に一度リトライする。
- Stage 1 / 1.5 で技法や法則を過剰に詰め込まず、余白と主題の焦点を残すよう調整する。

### 30件ベンチ

CLI 実行結果:

- success: 28
- failed: 2
- total elapsed: 1,336,707 ms
- average elapsed: 47,740 ms
- median elapsed: 26,796 ms
- max elapsed: 228,575 ms
- p90 elapsed: 158,432 ms
- tokens in: 281,625
- tokens out: 22,959

失敗:

- line 9: `古い本の余白に、午後の埃がゆっくり積もる。`
  - `HTTP 502: compose failed: Stage 2 returned no drawable instructions`
- line 13: `朝の市場で、積まれた果実の色が布の上で跳ねる。`
  - `HTTP 502: compose failed: Stage 2 returned no drawable instructions`

集計:

- background: white 18, black 7, red 3
- primitive: line 42, square 19, ellipse 15, arc 7, circle 4
- instructions: average 3.11, median 3, max 5
- elapsed > 120s: `bench030-004`, `bench030-011`, `bench030-020`, `bench030-028`

改善が見られた点:

- gray 背景の偏りは消えた。
- 完全な空白描画は成功サンプル内では発生しなかった。
- 10件パイロットよりも真円の偏りは低く、circle は 4 件に抑えられた。
- 黒背景/白描画、白背景/黒線など、視認性の高い組み合わせが増えた。
- プリミティブ数は平均 3.11 命令に収まり、過密化は抑えられている。

残った問題:

- Stage 2 の空 `instructions` はリトライ後も 2/30 で残った。失敗時の待ち時間も長く、ベンチ全体を遅くしている。
- Stage 2 遅延外れ値がまだ大きい。4件が 120秒を超え、最大は約229秒だった。
- 赤背景が 3件あり、強い単色背景に寄るケースがある。
- `bench030-014`、`bench030-029` などは点や小楕円の散布に戻っており、構図としての必然性が弱い。
- `bench030-004`、`bench030-011`、`bench030-020`、`bench030-028` は token out が 4,000 超で、Stage 2 が過剰に長い応答を生成している。
- 一部 DDL に `中央付近` や固定的な焦点表現が残り、ダイナミックな構図決定が弱い。
- 色の意図とレンダリングの抽象色解決にズレがあり、`黄色い四角` が green として出るような例がある。

現代抽象画としての評価:

- 全体の完成度は、単体作品としては習作レベル、シリーズとしては方向性の検証段階。視認性と余白は改善したが、作品ごとの構図思想や素材上の必然性はまだ弱い。
- 良いサンプルは、`bench030-008`、`bench030-022`、`bench030-030` のように要素を絞ったもの。一本の斜線、黒地の短い光、雪原の足跡のように、入力文の焦点を単純な構造へ置き換えられている。
- `bench030-001`、`bench030-006`、`bench030-019` は、強い面と少数の線・矩形で画面が成立している。一方で、面の選択がやや直截的で、色面が感情や空間を担うところまでは届いていない。
- `bench030-004`、`bench030-011`、`bench030-020`、`bench030-028` は、長い Stage 2 出力の割に視覚的な情報が整理されていない。技法語や補助線が増えるほど、作品の焦点がぼやける傾向がある。
- `bench030-014`、`bench030-029` は、点や楕円の散布が説明的で、現代抽象画としての緊張感が弱い。散布が「配置の結果」ではなく「散らしただけ」に見える。
- 黒背景のサンプルは視認性は高いが、黒地に白形という強い記号性へ寄りやすい。夜、雪、月、光の主題では有効だが、多用するとシリーズ全体が図案的になる。
- 線の扱いは増えたが、線質の差がまだ限定的。鉛筆、チョーク、水墨、クレヨンなどの語が DDL に出ても、最終SVGでは線幅、透明度、端部、揺らぎの違いが十分に作品性へ転化していない。
- 構図は「焦点を置く」「線を並べる」「点を散らす」の3類型に収束しやすい。現代抽象画としては、重心、間、反復の破れ、画面外への継続、層の前後関係が不足している。

芸術的改善点:

- 主題から「何を描くか」ではなく「どの視覚的関係を成立させるか」を先に決める。例: 緊張、沈黙、残響、侵食、反復の破れ、視線の停止点。
- Stage 1.5 で作品ごとに compositional mode を1つだけ選ぶ。例: `single tension`, `edge focus`, `field and interruption`, `layered trace`, `asymmetric rhythm`, `negative-space dominant`。
- 画面中央を避けるだけでなく、重心を 20〜80% の範囲で動かし、要素が画面外へ続く余地を持たせる。
- 点や小楕円の散布は、必ず軌跡、密度勾配、欠落、端部の薄れ、局所的な凝集のいずれかを持たせる。
- 強い単色背景は、主題に必要な場合だけ使う。赤背景や黒背景は、作品全体の情緒を支配するため、Stage 1.5 で選択理由を要求する。
- 線の群れは本数よりも秩序の差で作る。完全な等間隔ではなく、圧縮、間引き、途中停止、角度の微差、一本だけの逸脱を入れる。
- 素材感は語彙だけでなく SVG パラメータへ落とす。透明度、線端、破線、重ね塗り、微小な位置ずれ、部分的なにじみを renderer/coerce 側の表現幅として増やす。
- 一作品に技法を複数入れず、主技法1つ、副次的な乱れ1つまでに制限する。技法の多さより、選ばれた技法が画面全体を支配することを優先する。
- 余白は背景の空きではなく構図上の圧力として扱う。空白の近くに小さな焦点、端部の切断、反復の欠落を置き、余白に意味を持たせる。
- 成功判定に、単なる視認性ではなく「焦点の明確さ」「要素間の緊張」「シリーズ内の差異」を追加する。

主要ラベル:

- `slow_stage2`: 4/28 success, plus 2 failed samples
- `stage2_ignored_instruction`: line 9, line 13
- `weak_composition`: scattered dot/ellipse samples
- `center_bias`: reduced but still present in wording and some compositions
- `low_negative_space`: reduced, but dense line samples remain
- `color_resolution_mismatch`: abstract color name resolution mismatch

次の修正方針:

- Stage 2 の空 `instructions` は HTTP 502 で終えるのではなく、リトライ後に最小限の deterministic fallback score を生成する。
- Stage 2 には「DDL 全体を説明し直さず、3〜5命令の JSON Score に圧縮する」制約を追加し、長大出力を抑える。
- API レスポンスと CLI 結果に Stage 2 retry count / retry reason / fallback used を記録する。
- Stage 2 の per-stage timeout または empty-output retry timeout を短く設定できるようにし、失敗サンプルで6〜7分待つ状態を避ける。
- Stage 1.5 は「技法を追加する」よりも「主題から焦点、余白、視線誘導を選ぶ」側へ寄せる。
- 色カタログ解決後の foreground/background visibility と、DDL 色名から score 色名への対応を検査するテストを追加する。
- ベンチ評価用に visible pixel ratio、背景色、プリミティブ種別、命令数、elapsed 外れ値を自動集計する `inku-cli bench-report` 相当を追加する。

## 10. DDL -> JSON 要素落ち検証

30件ベンチ後のチューニングで、DDL に含まれる配置・軌跡・揺れ・素材の一部が JSON Score または SVG レンダリングへ十分に伝わらないケースを確認した。

### 人間によって発見された課題と、その原因

- `波打つ軌跡に沿って`、`上から下へ散らす`、`右半分` のような配置語が、既存の `arrangement.layout` だけでは安定して表現できなかった。
- `layout=scatter` は決定的な散布としてレンダリングされるため、DDL 上の「軌跡」「方向」「領域」のニュアンスが失われやすかった。
- `細かく揺れる`、`ゆっくり揺れる` は `variation` へ入っていても、線や配置の視覚差として弱いケースがあった。
- `てざわり` は `weight` 差だけに見えやすく、鉛筆、クレヨン、チョーク、水墨、縄などの物理的な差が SVG の見た目に十分出ていなかった。
- Stage 2 fixture の比較が `arrangement` を見ていなかったため、`count`、`layout`、`path`、`color_cycle`、`margin` の欠落を検知できなかった。
- Stage 2 が空 `instructions` を返した後の fallback score では、DDL の配置語が保持されず、特に `波打つ軌跡` や `上から下へ散らす` が落ちていた。

### 対応

- JSON Score schema の `Arrangement` に `path` を追加した。
  - `none`
  - `diagonal`
  - `wave`
  - `top_to_bottom`
  - `left_to_right`
  - `right_half`
- Stage 2 prompt に、配置語から `arrangement.path` へ写像するルールと例を追加した。
  - `波打つ軌跡に沿って` -> `layout=scatter`, `path=wave`
  - `斜めの帯` -> `path=diagonal`
  - `上から下へ散らす` -> `layout=vertical`, `path=top_to_bottom`
  - `左から右へ` -> `layout=horizontal`, `path=left_to_right`
  - `右半分` -> `path=right_half`
- renderer で `arrangement.path` を実際の配置座標へ反映するようにした。
  - `wave` は水平方向に進む波状軌跡
  - `diagonal` は斜め帯
  - `top_to_bottom` は縦方向の進行
  - `left_to_right` は横方向の進行
  - `right_half` は右半分へ制約
- `variation` の見た目を強化した。
  - `fine/perlin` は細かい震えとして線や輪郭に反映
  - `slow/wave` はゆっくりした波・位置揺れとして反映
- `てざわり` の renderer 表現を強化した。
  - 線だけでなく `circle`、`ellipse`、`square`、`arc` の輪郭にも素材処理を適用
  - pencil / crayon / chalk / brush / rope などが線幅差だけでなく、透明度、重ね、破線、粒状感、輪郭の揺れとして出るようにした
- Stage 2 fixture 比較で `arrangement` 全体を検査するようにした。
- submit tool schema に `arrangement.path` が含まれることをテストで検証するようにした。
- fallback score でも `散らす` を arrangement として保持し、配置語から `path` を復元するようにした。
  - 図形だけでなく線の `散らす` も対象にした。
- renderer / composer / API の回帰テストを追加した。

### 検証結果

実行:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py -q
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
```

結果:

- `95 passed, 30 skipped`
- `ruff`: all checks passed

### 残る確認ポイント

- 実 LLM で `path` が安定して出るかは、NVIDIA backend 有効時の fixture / bench で継続確認する。
- `arrangement.path` は表現幅を広げるが、過度に使うと作品が軌跡パターンへ寄る可能性があるため、ベンチでは `path_not_reflected` とあわせて `path_overused` も観察対象にする。
- `てざわり` は SVG レンダリング上は改善したが、作品としての差が十分かは PNG ベースの評価で確認する。

## 11. 100件ベンチ: DDL / JSON / SVG 伝達検証

Date: 2026-05-01

Branch: `tune-ddl-generation-cli-bench`

Model:

- Stage 1: `nvidia` / `google/gemma-4-31b-it`
- Stage 2: `nvidia` / `google/gemma-4-31b-it`

Artifacts:

- inputs: `cli/out/tune-bench-100/prompts.txt`
- results: `cli/out/tune-bench-100/`
- contact sheet: `cli/out/tune-bench-100/contact-sheet.png`

実行:

```sh
cd /Users/oikawas/projects/ddl-server/cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli batch \
  --base-url http://192.168.0.89:8100 \
  -f ./out/tune-bench-100/prompts.txt \
  -o ./out/tune-bench-100 \
  --prefix bench100 \
  --png \
  --continue-on-error
```

### 実行結果

- success: 96
- failed: 4
- total: 100
- total elapsed: 5,747,603 ms
- average elapsed: 59,871 ms
- median elapsed: 18,650 ms
- p90 elapsed: 184,094 ms
- max elapsed: 274,635 ms
- elapsed > 120s: 20 / 96
- tokens in: 1,172,941
- tokens out: 100,231
- average tokens out: 1,044

失敗:

- line 54: `夕暮れの空き地で、枯れ草が低い金色の波になっている。`
  - `HTTP 502: interpret failed: inference connection error`
- line 55: `雨の夜道に、信号の赤が濡れた靴先まで伸びている。`
  - `HTTP 502: interpret failed: inference connection error`
- line 56: `薄い霧の墓地で、石の角だけが静かに浮かび上がる。`
  - `HTTP 502: interpret failed: inference connection error`
- line 92: `夕暮れの校庭で、鉄棒の影が長く曲がっている。`
  - `HTTP 502: compose failed: inference connection error`

失敗はいずれも推論接続エラーであり、DDL / JSON 変換ロジック固有の失敗とは判断しない。ただし、ベンチ運用上は retry / resume / partial report が必須。

### 集計

背景:

- white: 62
- black: 24
- blue: 5
- red: 4
- green: 1

プリミティブ:

- line: 196
- square: 45
- ellipse: 37
- arc: 16
- circle: 14
- triangle: 3

素材 / weight:

- pen: 289
- pencil: 13
- crayon: 4
- brush_thin: 2
- rope: 2
- rotring: 1

塗り:

- filled=false: 298
- filled=true: 13

JSON Score:

- instructions average: 3.24
- instructions median: 3
- instructions max: 20
- expanded primitive count average: 116.17
- expanded primitive count median: 26
- expanded primitive count p90: 237
- expanded primitive count max: 3,001
- `color_hint`: 148 / 311 instructions

arrangement:

- layout: vertical 118, scatter 77, horizontal 49, none 43, radial 24
- path: none 152, wave 65, right_half 45, top_to_bottom 20, diagonal 17, left_to_right 12
- max `arrangement.count`: 300

variation:

- variation instructions: 46 / 311
- quality: perlin 18, pink 15, wave 13

重複:

- 同一 instruction の重複あり: 19 / 96
- 重複で余分に増えた instruction: 63
- 代表例:
  - `bench100-001`: DDL は「横線を二十本並べる」だが、JSON は `arrangement.count=20` の同一 line instruction を20個複製した。
  - `bench100-022`: DDL は「鉛筆の細い横線を十二本並べる」だが、JSON は `arrangement.count=12` の同一 line instruction を12個複製した。
  - `bench100-030`: DDL は「白い細筆の縦線を三百本」だが、JSON は `count=300` の instruction を複数複製し、過密化しやすい構造になった。

### 入力文 -> DDL の評価

良い点:

- 入力文の主要な視覚名詞は概ね拾えている。光、影、水、窓、雨、雪、壁、机、線、点、道、港、寺、駅といった要素は DDL の色、背景、線、四角、楕円、配置へ変換されている。
- 季節や時間帯は背景色、明度、線の密度に変換される傾向がある。夜、冬、雪、月、雨、朝などは比較的安定して抽象化される。
- `消える`、`ほどける`、`滲む`、`揺れる`、`沈む` のような動詞は、波、散布、にじみ、細線、低彩度として DDL に反映されることがある。
- 以前の 30件ベンチより、真円への偏りと灰背景への偏りは抑制されている。

問題:

- 入力文の「雰囲気、エモーション、感情」は DDL へ部分的にしか伝わっていない。感情語を含む入力 47 件のうち、DDL 側でも感情語または近い語が残ったものは 30 件程度。さらに JSON 側まで語として残ったものは 8 件程度だった。
- 感情はしばしば「黒背景」「白線」「細線」「点散布」「波打つ」に圧縮される。孤独、沈黙、余韻、記憶、ためらい、気配、眠気、病後、寒さなどの違いが、見た目上は同じ語彙に収束しやすい。
- 場面固有の主題が落ちることがある。例: `風鈴の余韻`、`言えなかった言葉`、`待つ人の気配`、`小さな温度` は DDL では線や楕円の一般表現になり、情景の固有性が弱くなる。
- Stage 1.5 の技法語や数学語が入るケースでは、主題よりも追加技法が目立つことがある。対位法、倍音、フレスコ、点描などが説明的に挿入され、入力文の感情を上書きする場合がある。
- `中央付近` は減ったが、`上端寄りの焦点`、`右下の焦点`、`画面下半分` といったテンプレート的な焦点表現はまだ多い。主題から動的に重心を決めるところまでは不十分。

### DDL -> JSON の評価

良い点:

- 背景色、プリミティブ種別、基本色、数量、配置方向は多くのサンプルで JSON に落ちている。
- `arrangement.path` は機能しており、`wave`、`top_to_bottom`、`right_half`、`diagonal`、`left_to_right` は実データに出ている。
- `color_hint` は 148 instruction で使われ、抽象色へ丸めた後も「白い息」「雨の膜」「墨絵」「黄色」などの元意図を一部保持している。
- `filled` は非塗りが多く、塗りつぶし一辺倒にはなっていない。

重大な問題:

- Stage 2 が `arrangement.count` つき instruction を複製してしまう。これは DDL -> JSON の最大の欠陥。`count=20` の line instruction が20個並ぶと、レンダラーでは 400 本相当の構造になりうる。作品の過密化、実行時間増、SVG肥大、似た見た目の増加につながる。
- DDL の素材語が JSON の `weight` へ落ちにくい。素材語を含む DDL は 73 件程度あったが、JSON 側で `pen` 以外の weight や素材語として確認できたものは 12 件程度に留まった。結果として、細筆、鉛筆、クレヨン、水墨、油絵、フレスコ、点描の違いがレンダラーへ十分渡らない。
- DDL の `細かく揺れる`、`ゆっくり揺れる`、`境界が滲む` は、JSON で `variation` に落ちる場合と落ちない場合がある。落ちた場合も、どの primitive に適用するべきか曖昧なままになりやすい。
- DDL の色名が抽象色へ丸められる際、`color_hint` は残るが、実際の `color` が主題とずれる例がある。`黄色い楕円` が gray / red / green / blue の色サイクルになり、黄色の印象が弱いケースがあった。
- `fallback from DDL` の JSON は情報量を落としすぎる。例: `bench100-004` は DDL に水面、花びら、37個、波、細かい揺れがあるが、JSON は青い楕円7個に圧縮された。
- DDL に複数要素がある場合、Stage 2 が一部だけを採用することがある。例: `bench100-059` は泉、縦線233本、油絵厚塗り3本が DDL にあるが、JSON は緑背景と黒楕円にほぼ縮退した。

### JSON -> SVG レンダリングの評価

良い点:

- JSON に落ちた背景、基本形状、配置、回転、色、非塗り/塗りは概ね SVG に反映されている。
- `arrangement.path=wave` や `right_half` は、レンダリング結果として見えるケースがある。
- contact sheet を見る限り、完全な空白描画や極端な低コントラストは大きく減っている。

問題:

- レンダラーは JSON を忠実に展開するため、Stage 2 の重複 instruction をそのまま過密な SVG にしてしまう。レンダラー側にも重複検知または上限防御が必要。
- 素材表現は改善済みだが、JSON の weight がほぼ `pen` で渡るため、renderer の表現力が使われていない。
- `filled=false` が 298 / 311 と多く、非塗り線中心の作品に寄る。塗りと非塗りのバランスは DDL/JSON/renderer のどこかで制御する必要がある。
- 黒背景 + 白線、白背景 + 黒線の視認性は高いが、シリーズとして二値的な図案に寄る。中間調、透明度、重ね、薄い色面の使い方が不足している。
- 小点散布は見えるが、密度勾配や欠落の意味が弱いと「粒を散らしただけ」に見える。renderer は arrangement を機械配置するだけでなく、主題に応じた密度関数を持つべき。

### 視覚評価

contact sheet 全体では、96件のうち視認性は概ね確保されている。以前の灰背景問題、白地に白線問題、真円過多は改善している。

一方で、現代抽象画としてはまだ以下の収束が目立つ。

- 黒地に白/灰の線群
- 白地に細い水平線/垂直線
- 点散布
- 右端/上端/下半分への定型配置
- 太い単色背景に少数の形
- 線の束による「気配」の表現

良い方向のサンプル:

- `bench100-005`: 黒い海と灯台光のような、少数要素で主題が立つ。
- `bench100-008`: 白い余白と薄い線だけで静かな午後の感覚が出ている。
- `bench100-026`: 線と小さな黒要素の関係が、影の先行という入力に合っている。
- `bench100-083`: 蜘蛛の巣 / 雨粒 / 虹の分解が斜線と色線で比較的よく出ている。
- `bench100-099`: 障子、枝、墨絵の重なりが右側の線構成として成立している。
- `bench100-100`: ベンチ、手袋、残る温度が面と小形で比較的読み取れる。

弱い方向のサンプル:

- `bench100-001`: 情緒はあるが、同一 line instruction 重複により構造が過剰。
- `bench100-003`: 埃の散布は見えるが、図書館・午後・静けさは一般化されすぎている。
- `bench100-004`: DDL から JSON で水面、花びら、波、37個が大きく落ちている。
- `bench100-017`: 竹林の輪郭と風のほどけが、単一斜線に縮退している。
- `bench100-030`: DDL/JSON とも要素が多く、透明な膜よりも密集した白い矩形に見える。
- `bench100-059`: 小さな泉と暗い緑の含みが黒楕円に縮退している。
- `bench100-078`: 水たまりと割れる傘色が赤い矩形群になり、入力の繊細さが失われている。
- `bench100-089`: 雪、瓦、濡れの質が、黒い四角散布へ縮退している。

### 改善点: Stage 1

- 入力文から抽出する対象を `visual_subject`、`emotional_tone`、`spatial_context`、`motion_or_change`、`material_suggestion` に分ける。
- DDL へ変換する前に、作品の中心命題を1つ決める。例: `absence as thin horizontal breath`、`memory as fading density`、`hesitation as interrupted flow`。
- 感情語を色や線に即時変換せず、まず構図上の関係へ変換する。
  - 孤独: 小さな焦点と広い空白
  - 余韻: 反復の減衰
  - ためらい: 途中停止、途切れ、弱い蛇行
  - 記憶: 薄い重なり、欠落、半透明
  - 沈黙: 低密度、長い間、少数の重い面
  - 不安: わずかな角度差、密度の偏り、端への緊張
- DDL に情緒語をそのまま残すか、`雰囲気:` 相当の短い注釈を含める。Stage 2 が JSON へ移すための足場になる。
- 主題の固有名詞を少なくとも1つ `color_hint` または `motif_hint` に残すよう、Stage 1 の出力制約を追加する。
- DDL の数量は動的でよいが、感情が繊細な場合は上限を抑える。静けさ、余韻、孤独、病後、忘れ物のような入力で 200〜300 個を出しすぎない。
- `背景を黒で塗りつぶす` と `背景を白で塗りつぶす` の二値選択に寄りすぎないよう、背景を「面」「余白」「薄層」として扱う選択肢を増やす。
- 「何を描くか」だけでなく、「何を描かないか」を DDL に明示する。余白を主題化する。

### 改善点: Stage 1.5

- Stage 1.5 は技法を追加する段ではなく、構図と伝達を整理するフィルタとして再定義する。
- 1件の描画に適用する技法は、主技法1つ、副次的な揺らぎ1つまでに制限する。
- 数学・音楽・絵画技法は「選択的」に使う。全件に近い頻度で技法語を入れると、シリーズが均質化する。
- `composition_mode` を1つ選ぶ。
  - `negative_space_dominant`
  - `edge_focus`
  - `single_tension`
  - `field_and_interruption`
  - `density_gradient`
  - `layered_trace`
  - `asymmetric_rhythm`
  - `off_canvas_continuation`
- `emotion_strategy` を1つ選ぶ。
  - `reduction`
  - `echo`
  - `fade`
  - `interruption`
  - `compression`
  - `drift`
  - `residue`
- `material_strategy` を1つ選ぶ。
  - `dry_line`
  - `soft_bleed`
  - `grain`
  - `hard_edge`
  - `wash`
  - `thick_patch`
- Stage 1.5 で DDL の instruction 数と expanded primitive count の見込みを制御する。繊細な入力では expanded 10〜80 程度、都市/雨/群衆では 80〜180 程度など、主題別に密度目安を持つ。
- `中央`、`画面全体`、`等間隔`、`点々と散らす` の頻発を抑える。使う場合は、必ず非対称性、欠落、密度勾配、画面外への継続のいずれかを付ける。
- `色とりどり` は安易に使わない。水たまりや傘など色が多い入力でも、主色2つ + 微細な差し色程度に抑える。

### 改善点: Stage 2

- 最優先: 同一 instruction の重複禁止を system prompt と schema 後処理に追加する。複数個の同形状は、必ず1 instruction + `arrangement.count` で表す。
- `arrangement.count` を持つ instruction が複数ある場合、同一 primitive / geometry / color / arrangement の重複を coerce で統合する。
- `arrangement.count` の展開後上限を設ける。例: 1 score あたり expanded primitive count は通常 200 以下、明示的に大密度が必要な場合でも 400 以下。
- DDL の各文を JSON instruction へ対応させる coverage check を追加する。Stage 2 出力後に、DDL 文ごとに `covered_by_instruction` を内部検査する。
- DDL の素材語を `weight` へ確実に写像する。
  - 細筆 -> `brush_thin`
  - 太筆 -> `brush`
  - 鉛筆 -> `pencil`
  - クレヨン -> `crayon`
  - チョーク -> `chalk`
  - 水墨 -> `ink_wash`
  - ロットリング -> `rotring`
  - 縄 -> `rope`
  - 油絵 / 厚塗り -> `oil_impasto`
  - 水彩 -> `watercolor`
  - 点描 -> `pointillist`
- DDL の感情・雰囲気を JSON に残すフィールドを検討する。例: `mood_hint`, `motion_hint`, `material_hint`, `focus_hint`。現状の `color_hint` だけでは保持先が狭い。
- `variation` の対象を明示する。例: `applies_to: ["outline", "position", "opacity"]`。今は `dimensions` があるが、DDL の「線が揺れる」「境界が滲む」「配置が漂う」の区別が弱い。
- `fallback from DDL` を改善する。fallback は単一形状への縮退ではなく、DDL の文数、数量、配置、素材、揺れを最低限保持する deterministic parser に寄せる。
- Stage 2 の長大出力を抑える。目標は 3〜6 instructions、tokens out は通常 800 以下。4,000 tokens 超の出力はほぼ失敗扱いにして再試行する。
- Stage 2 の retry reason を返す。`empty_instructions`、`duplicate_arrangement`、`overexpanded_count`、`coverage_low` などを API レスポンスや CLI JSON に残す。
- 色解決では、抽象色 `color` と元色 `color_hint` の関係を明確にする。黄色や金色が必要な場合に gray / red / green / blue へばらけるのではなく、カタログ解決で近似可能な hue family を保持する。
- `filled` は DDL の「塗る」「面」「厚塗り」「色面」「影」から推定する。現状は非塗りに寄りすぎている。

### 改善点: SVG renderer / coerce

- 同一 instruction 重複を renderer 前に検知し、統合または警告する。Stage 2 の問題だが、renderer 側にも安全弁が必要。
- expanded primitive count の上限を renderer/coerce で持つ。上限超過時は、count を減らすだけでなく密度勾配、透明度、間引きで意味を保つ。
- `weight` ごとの素材表現をさらに強める。ただし線幅差だけでなく、端部、透明度、ざらつき、破線、重なり、にじみ、輪郭の不規則性で変える。
- `filled=false` が多すぎる場合、主題に応じて一部を薄い面や半透明の塗りへ変換する coerce を検討する。
- `mood_hint` または `motion_hint` が導入された場合、renderer は opacity、blur、jitter、density、edge softness に反映する。
- `arrangement.path=wave` は現状見えるが、どのサンプルでも似た波になりやすい。波長、振幅、位相、減衰、局所欠落を主題から変える。
- `scatter` は完全な均等ランダムではなく、密度関数を選ぶ。
  - fade-out
  - edge accumulation
  - diagonal drift
  - center void
  - local cluster
  - interrupted trail
- 背景を単色塗りだけでなく、薄い層、透明な面、部分的な wash として扱う。ただし実装は SVG の軽量性を保つ。
- 低コントラスト補正は継続しつつ、白地に白、黒地に黒を機械的に反対色へ寄せるだけではなく、主題が白/黒である場合は線端、影、透明度、隣接色で見せる。
- レンダリング後の自動メトリクスを追加する。
  - visible pixel ratio
  - dominant background ratio
  - foreground color count
  - edge contact count
  - near-empty / overfilled 判定
  - duplicate arrangement warning

### 追加すべきテスト / ベンチ機能

- `inku-cli bench-report` を追加し、JSON 群から以下を自動集計する。
  - success / failed
  - elapsed / tokens
  - background / primitive / weight / filled
  - instruction count
  - expanded primitive count
  - duplicate instruction count
  - DDL 文 coverage
  - DDL 色名 coverage
  - DDL 素材語 coverage
  - DDL path / movement coverage
- `bench-compare` を追加し、同一 prompts に対する修正前後の差分を比較する。
- fixture に、感情語の伝達テストを追加する。
  - 孤独
  - 余韻
  - ためらい
  - 記憶
  - 沈黙
  - 寒さ
  - 温度
  - 気配
- Stage 2 fixture に、同一 `arrangement.count` instruction の複製を禁止するテストを追加する。
- DDL 文ごとの coverage をユニットテスト化する。最低限、数量・配置・素材・色・揺れの5軸で欠落を検出する。
- SVG レンダラーに snapshot / image metric テストを追加し、過密、空白、不可視、素材差の退行を検知する。

### 優先順位

1. Stage 2 の同一 arrangement instruction 重複を禁止・統合する。
2. Stage 2 / coerce に expanded primitive count 上限を入れる。
3. DDL 素材語を JSON `weight` へ安定写像する。
4. DDL 文 coverage check を追加する。
5. 感情・雰囲気を `color_hint` 以外のフィールドで保持する。
6. Stage 1.5 を composition / emotion / material strategy の選択フィルタへ整理する。
7. `fallback from DDL` を縮退ではなく deterministic coverage に寄せる。
8. renderer に重複・過密・不可視の安全弁と画像メトリクスを追加する。
9. 同一 prompts で修正前後の 30件 / 100件比較を行う。

### 結論

100件ベンチでは、入力文の大枠は DDL に届いているが、雰囲気・エモーション・感情はまだ細い経路でしか伝わっていない。DDL は詩的な入力を、色・線・散布・波・背景へ変換できている一方で、情緒の種類ごとの違いが小さく、複数の入力が似た構造へ収束している。

DDL から JSON への変換では、配置・数量・色の基本は通るが、重複 instruction、素材語の脱落、variation の弱さ、fallback の縮退が品質を大きく落としている。SVG レンダラーは JSON を概ね忠実に描いているため、上流の欠落がそのまま絵に出る。ただし renderer/coerce 側にも、過密・重複・素材差・密度関数の安全弁を持たせるべき。

次の改修は、表現の追加よりも「伝達の欠落を減らす」「選択を鋭くする」「重複と過密を抑える」方向を優先する。

## 12. 100件ベンチ後の実装反映

Date: 2026-05-01

Commit:

- `806e30a fix: harden llm retry and score coercion`

100件ベンチの結果から、まず「生成表現の拡張」ではなく「失敗を適切に扱う」「DDL から JSON への伝達欠落を減らす」「過密化を防ぐ」ためのサーバー側防御を実装した。

### NVIDIA Free API 前提の retry / fail

NVIDIA NIM は開発用の Free API 接続先であり SLA はない。31B モデル自体はクエリが渡れば適切な時間内に返る想定だが、Free API 側の混雑や一時障害により、接続エラーや遅延が発生しうる。

その前提で `llm_retry.py` を拡張した。

- retry 対象:
  - `429 Too Many Requests`
  - `408 / 500 / 502 / 503 / 504`
  - `inference connection error`
  - connection reset / aborted / timeout / gateway 系
- retry しない対象:
  - JSON grammar / schema compile error
  - bad request
  - authentication / authorization error
  - not found
- retry delay は exponential backoff + jitter
- `Retry-After` header があれば優先
- retry 回数と delay は環境変数で調整可能

環境変数:

```sh
INKU_LLM_RETRY_ATTEMPTS
INKU_LLM_RETRY_BASE_DELAY
INKU_LLM_RETRY_MAX_DELAY
INKU_LLM_RETRY_JITTER
INKU_LLM_REQUEST_TIMEOUT_SECONDS
```

`INKU_LLM_REQUEST_TIMEOUT_SECONDS` はサーバーから LLM API への 1 request timeout。CLI の `timeout_seconds` は CLI から inku-api への HTTP timeout であり、別レイヤーとして扱う。

### 実装済み: Stage 2 / coerce

100件ベンチの優先順位のうち、以下を実装済みとした。

1. Stage 2 の同一 arrangement instruction 重複を禁止・統合する。
2. Stage 2 / coerce に expanded primitive count 上限を入れる。
3. DDL 素材語を JSON `weight` へ安定写像する。
7. `fallback from DDL` を縮退ではなく deterministic coverage に寄せる。
8. renderer に重複・過密・不可視の安全弁を追加する。

具体的な実装:

- `coerce_score(score, ddl=...)` に DDL を渡せるようにした。
- `/api/compose` と `/api/paint` は renderer 前に `coerce_score(score, ddl=...)` を呼ぶ。
- 完全一致する instruction は renderer 前に重複排除する。
- expanded primitive count の総量が 400 を超える場合、`arrangement.count` を縮小する。
- density cap が入った場合は `color_hint` に注記を残す。
- DDL に素材語があるのに Stage 2 が `weight=pen` のまま返した場合、coerce で補完する。
- DDL に揺れ / 滲み語があるのに Stage 2 が `variation` を落とした場合、coerce で補完する。
- fallback score でも DDL の数量詞と素材語を反映する。

素材語の補完:

- ロットリング -> `rotring`
- 鉛筆 -> `pencil`
- クレヨン -> `crayon`
- チョーク -> `chalk`
- 細筆 / 水墨 / 墨 -> `brush_thin`
- 太筆 / 油絵 / 厚塗り -> `brush_thick`
- 縄 / ロープ -> `rope`

揺らぎの補完:

- `ゆっくり揺れる` / `ゆっくり波打つ` -> `quality=wave`, `frequency=slow`
- `細かく揺れる` / `細かく震える` / `震える` -> `quality=perlin`
- `滲む` / `境界が滲む` -> `quality=pink`

### 実装による期待効果

- `bench100-001`、`bench100-022`、`bench100-030` のような `arrangement.count` 付き instruction の重複は renderer 前に統合される。
- `count=300` の instruction が複数出た場合でも、expanded primitive count が上限内へ圧縮される。
- Stage 2 が素材語を落としても、DDL 側の `鉛筆`、`クレヨン`、`チョーク`、`水墨` などから renderer に渡る `weight` を回復できる。
- `細かく震える`、`ゆっくり揺れる`、`滲む` が JSON で落ちた場合でも、最低限の `variation` を補完できる。
- NVIDIA Free API の一時的な混雑や接続失敗に対して、すぐ fail せず合理的に retry できる。
- JSON grammar / schema compile error のような恒久エラーは retry せず、問題の切り分けを早くする。

### 検証

実行:

```sh
cd server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_composer.py tests/test_renderer.py tests/test_interpreter.py tests/test_ddl_expander.py tests/test_coerce.py tests/test_llm_retry.py -q
```

結果:

- `ruff`: all checks passed
- `pytest`: `103 passed, 30 skipped`

### 残件

今回の実装は、ベンチ結果から見えた欠陥のうち、サーバー側で deterministic に補正できるものを先に潰した。以下は未実装。

- DDL 文ごとの coverage check。
- `mood_hint` / `motion_hint` / `material_hint` / `focus_hint` のような、感情・雰囲気を保持する新フィールド。
- Stage 1.5 の composition / emotion / material strategy 化。
- Stage 2 tokens out が過大な場合の retry / fail 判定。
- `bench-report` / `bench-compare` の CLI コマンド化。
- renderer の visible pixel ratio / overfilled / near-empty などの画像メトリクス。
- `filled=false` 過多への表現上の補正。
- 色名解決の改善。特に黄色、金色、銀色、桃色、紫などを抽象色と `color_hint` からどう安定解決するか。

### 次のベンチ方針

同一 `cli/out/tune-bench-100/prompts.txt` を使い、修正後の 30件または100件ベンチを再実行する。

比較時に見る指標:

- success / failed
- inference connection error の retry 後成功率
- duplicate instruction count
- expanded primitive count
- `weight=pen` への収束率
- `variation` 付与率
- fallback 使用件数
- contact sheet 上の過密サンプル数

## 13. 修正後30件ベンチ

実行条件:

- 入力: `cli/out/tune-bench-100/prompts.txt` の先頭30件
- 出力: `cli/out/tune-bench-030-after-806e30a/`
- Stage 1 provider/model: `nvidia` / `google/gemma-4-31b-it`
- Stage 2 provider/model: `nvidia` / `google/gemma-4-31b-it`
- CLI timeout: 600秒
- サーバー側 retry/fail と `coerce_score(score, ddl=...)` 実装後

実行結果:

- 成功: 30件
- 失敗: 0件
- elapsed total: 1,979,125ms
- tokens in: 352,734
- tokens out: 27,132

前回100件ベンチの先頭30件との比較:

| 指標 | 修正前 first30 | 修正後30 |
| --- | ---: | ---: |
| success | 30 | 30 |
| failed | 0 | 0 |
| instruction avg | 3.80 | 2.30 |
| instruction max | 20 | 5 |
| expanded primitive avg | 158.17 | 49.23 |
| expanded primitive max | 3001 | 234 |
| duplicate extra total | 44 | 0 |
| duplicate rows | 7件 | 0件 |
| elapsed avg | 68,054ms | 65,971ms |
| elapsed max | 234,586ms | 481,445ms |
| elapsed >120s | 8件 | 4件 |
| tokens out avg | 1,218 | 904 |
| tokens out max | 4,141 | 4,148 |

効いた点:

- 同一 instruction の重複は 44件から0件に減った。
- expanded primitive count の最大値は 3001 から 234 に落ち、過密・爆発は抑制された。
- `weight=pen` への収束は弱まり、`brush_thin`、`crayon`、`pencil`、`brush_thick`、`rope`、`rotring`、`chalk` へ分散した。
- `bench100-001`、`bench100-022`、`bench100-030` 型の arrangement 重複は再現しなかった。
- NVIDIA Free API に対する接続エラー・429・empty drawable failure は今回の30件では発生しなかった。

残った問題:

- Stage 2 の過長応答は残っている。特に line 12 は Stage 2 が 454,629ms、line 28 は 312,364ms、line 30 は 131,449ms。
- tokens out が 4,100台まで伸びるケースが残り、長い応答なのに最終 instruction は1件だけという縮退がある。
- 過密抑制の副作用として、line 28 / line 30 のように単一の大きな要素だけで終わるケースがある。
- 背景色の分布は修正前と同じで、白18、黒9、赤2、青1。背景選択の多様性は今回の修正対象外だった。
- contact sheet 上では、重複爆発は消えたが、表現の複雑さと空間構成の差はまだ不足している。

次の実装候補:

- Stage 2 が `tokens_out` 4000近辺、または elapsed 120秒超になった場合の retry / fail 判定。
- retry した場合の attempt count / error reason / stage 別 elapsed を CLI と JSON に保存する。
- instruction が1件に縮退した場合、DDL coverage check で主要要素を再補完する。
- `expanded primitive count` の単純縮小だけでなく、密度を下げながら構成要素の種類を保つ圧縮を行う。
- 背景色を white / black に寄せすぎない Stage 1.5 の tone strategy を追加する。

## 14. 進め方

1. 10 件パイロットを実施する
2. 評価ラベルを調整する
3. 30 件ベンチを実施する
4. 評価とラベルを記録する
5. ラベルを集計する
6. 修正案を Stage 別に整理する
7. 影響が大きく、実装が局所的なものから修正する
8. 修正後に同じ入力セットで再実行し、差分を見る
