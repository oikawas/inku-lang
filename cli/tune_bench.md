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

## 2026-05-02 Build 247: density/cluster/fade 追従後 30 件ベンチ

対象:

- 入力: `cli/out/tune-bench-030-after-806e30a/prompts.txt`
- 出力: `cli/out/tune-bench-030-density-247/`
- contact sheet: `cli/out/tune-bench-030-density-247/contact-sheet.png`
- Stage1/Stage2: `nvidia` / `google/gemma-4-31b-it`

結果:

- 成功: 30 / 30
- 失敗: 0 / 30
- total elapsed: 1,631,379 ms
- average elapsed: 54,379 ms
- median elapsed: 38,257 ms
- max elapsed: 187,518 ms
- tokens in/out: 314,433 / 14,164
- compose retry total: 3
- compose fallback used: 5件

Score 集計:

- expanded count total: 1,348
- clustered arrangements: 10
- preserve_space: 14
- color_cycle: 10
- density: `high=3`, `medium=7`, `low=3`
- fade: `outward=10`, `directional=3`
- primitives: `line=46`, `ellipse=18`, `square=14`, `arc=6`, `circle=2`
- colors: `black=32`, `gray=22`, `white=20`, `red=8`, `blue=4`

観察:

- `density / cluster_count / fade / preserve_space` は 30 件中の一部に反映され、特に粒・膜・気配・消失系の表現で新フィールドが使われた。
- `circle` は 2 件まで抑制され、真円偏重は改善している。
- `line` が依然として最多で、線主体の構成が強い。次の調整では面・弧・非線形の領域表現を増やす余地がある。
- `black` と `gray` が多く、色彩の幅はまだ限定的。色カタログ解決以前の抽象色としても、青・緑・赤の使い分けを増やす余地がある。
- fallback は 5 件発生。うち Stage2 hard timeout が複数あり、Free API の待ち・失敗前提としては許容範囲だが、品質評価からは fallback 作品を別枠に分ける必要がある。
- 100 秒超の遅延が 7 件あり、ベンチ用途では timeout だけでなく「遅延サンプル」ラベルを評価表に残すのが妥当。

次の改善候補:

- Stage2 が `density / fade` をより直接使うよう、膜・霞・反射・消失以外の「空気感」「距離」「沈黙」でも schema field へ落とす例を追加する。
- Stage1.5 は線の補助層を増やしすぎないよう、面・弧・余白の焦点に振る候補を増やす。
- Renderer は `fade` の方向性を要素ごとの opacity 勾配としてより明確化する。現状は instruction 単位の薄れに近い。
- ベンチ評価では fallback 使用作品を成功件数に含めつつ、芸術評価では別集計する。
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

- ~~Stage 2 が `tokens_out` 4000近辺、または elapsed 120秒超になった場合の retry / fail 判定。~~ → 実装済み。空 instructions、過大 tokens out、長時間かつ単一 instruction を retry 対象にする。
- ~~retry した場合の attempt count / error reason / stage 別 elapsed を CLI と JSON に保存する。~~ → 実装済み。API は retry count / reasons / fallback used を返し、CLI summary JSON にも含める。
- ~~instruction が1件に縮退した場合、DDL coverage check で主要要素を再補完する。~~ → 実装済み。coerce layer が DDL の複数視覚句から最大5命令まで補完する。
- ~~`expanded primitive count` の単純縮小だけでなく、密度を下げながら構成要素の種類を保つ圧縮を行う。~~ → 一部実装。単一 arrangement count の上限と、複数 instruction の最低1件保持を行う。
- 背景色を white / black に寄せすぎない Stage 1.5 の tone strategy を追加する。

## 14. 修正後30件ベンチを受けた追加実装

Date: 2026-05-01

実装内容:

- `_call_compose_detail()` を診断情報付きに変更した。
- Stage 2 の初回結果が以下の条件に該当した場合、コンパクトな描画命令を要求して1回 retry する。
  - `empty_instructions`
  - `excessive_tokens_out`
  - `slow_single_instruction`
- retry しても空の場合は deterministic fallback score を使用し、`fallback_used=true` として返す。
- `/api/compose` は `retry_count`、`retry_reasons`、`fallback_used` を返す。
- `/api/paint` は `compose_retry_count`、`compose_retry_reasons`、`compose_fallback_used` を返す。
- `inku-cli paint` / `batch` の summary JSON に上記 retry/fallback 情報を含める。
- `coerce_score(score, ddl=...)` は、Stage 2 が1 instruction へ縮退した場合、DDL の複数視覚句から coverage 補完 instruction を追加する。
- 単一 `arrangement.count` にも上限を設け、1 instruction が過密の大半を占める状態を抑える。

期待効果:

- line 12 / 28 / 30 のような、長時間応答かつ単一 instruction へ縮退するケースを検知しやすくする。
- retry / fallback の有無をベンチ結果に残し、後続分析で「成功だが補正された描画」を区別できる。
- DDL の複数要素が Stage 2 で落ちた場合でも、主要な形・色・素材の一部を Score に戻す。
- 過密抑制時に、構成要素の種類を残したまま密度を下げやすくする。

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

## 15. 進め方

1. 10 件パイロットを実施する
2. 評価ラベルを調整する
3. 30 件ベンチを実施する
4. 評価とラベルを記録する
5. ラベルを集計する
6. 修正案を Stage 別に整理する
7. 影響が大きく、実装が局所的なものから修正する
8. 修正後に同じ入力セットで再実行し、差分を見る

## 16. 不正・矛盾・曖昧入力30件ストレステスト

Date: 2026-05-01

目的:

- 通常の絵画指示ではなく、矛盾、否定、会話、メタ指示、XML/script 風文字列、エラー文、空描画誘導、不可視色、過大数量、曖昧語を混ぜる。
- LLM 側のエラー、Stage 2 の空 instructions、retry/fallback、描画破綻の出方を見る。

出力:

- `cli/out/invalid-bench-030/`

実行結果:

- 成功: 30件
- 失敗: 0件
- elapsed total: 1,790,085ms
- tokens in: 332,541
- tokens out: 16,228
- retry 発生: 4件
- fallback 使用: 2件

retry / fallback:

| line | 入力概要 | elapsed | tokens out | reasons | fallback |
| ---: | --- | ---: | ---: | --- | --- |
| 2 | 「赤い円を描くな。青い四角も描くな。では、何かを描いて。」 | 191,669ms | 4,114 | `empty_instructions`, `fallback_after_empty_retry` | yes |
| 3 | 白背景に白い雪・白い息 | 261,016ms | 257 | `slow_single_instruction` | no |
| 13 | 一万本の極細線で霧、余白九割 | 130,579ms | 2,245 | `empty_instructions` | no |
| 28 | 読めない文字を読めないまま描く | 448,738ms | 4,129 | `empty_instructions`, `fallback_after_empty_retry` | yes |

過長応答:

- `elapsed > 120s` は 5件。
- line 2 / 3 / 13 / 28 は Stage 2 側。
- line 21 は Stage 1 側が 124,492ms で、Stage 2 は 7,949ms。入力は「ランダムにしてください。ただしランダムという言葉は使わないで。」で、Stage 1 の解釈に時間がかかった。
- 現在の retry 判定は「返ってきた結果を見て再試行・診断する」ため、進行中の LLM request を 120秒で強制中断しない。このため line 28 のように 448秒待つケースが残る。

描画・構造:

- API / renderer 破綻はなし。
- expanded primitive max: 250
- expanded primitive avg: 99
- instruction max: 5
- instruction avg: 2.1
- background: white 23 / black 5 / blue 1 / green 1
- primitive: line 45 / square 11 / ellipse 6 / circle 1 / arc 1
- XML/script 風入力は SVG/script として混入せず、通常の抽象描画に落ちた。
- 「白地に白」や「灰色に灰色」は不可視破綻せず、見える描画に補正された。
- 「空配列にしてください」は空描画に落ちず、通常成功した。

観察:

- 不正・矛盾入力でも API と renderer は落ちない。
- 空 instructions retry/fallback は機能している。
- ただし fallback 使用時の入力意味の保持は弱い。line 2 / 28 は「落ちない」ことは達成したが、作品としての妥当性は低い。
- Stage 2 の長時間空応答は依然としてコストが高い。返却後 retry ではなく、Stage 単位の hard timeout / fail-fast / deterministic fallback への切替が必要。
- Stage 1 も矛盾・メタ指示で長時間化しうるため、Stage 1 にも同様の hard timeout と診断情報が必要。

次の実装候補:

- ~~Stage 1 / Stage 2 の LLM request に per-stage hard timeout を設け、timeout 時は deterministic fallback へ切り替える。~~ → 実装済み。
- retry 前の初回応答が `tokens_out` 4000超かつ empty の場合、追加 LLM retry せず即 fallback する。
- fallback score の DDL coverage を改善し、line 2 / 28 のような否定・読めない文字の含意をより保持する。
- CLI batch summary をファイル保存するオプションを追加し、長い標準出力に依存せず後続分析できるようにする。

## 17. hard timeout 実装

Date: 2026-05-01

不正入力30件ストレステストで、LLM が最終的には返るものの Stage 1 / Stage 2 が長時間ブロックされるケースが確認された。特に line 28 は 448,738ms かかったため、API 層で Stage 単位の hard timeout を追加した。

実装内容:

- Stage 1 hard timeout:
  - 環境変数: `INKU_STAGE1_HARD_TIMEOUT_SECONDS`
  - 既定値: 120秒
  - timeout 時は、元入力から deterministic fallback DDL を生成する
  - `/api/interpret` は fallback 時のみ `fallback_used` / `fallback_reasons` を返す
  - `/api/paint` は `interpret_fallback_used` / `interpret_fallback_reasons` を返す
- Stage 2 hard timeout:
  - 環境変数: `INKU_STAGE2_HARD_TIMEOUT_SECONDS`
  - 既定値: 120秒
  - 初回 timeout 時は `stage2_hard_timeout` として fallback Score へ切り替える
  - retry timeout 時は `stage2_retry_hard_timeout` として fallback Score へ切り替える
- `inku-cli paint` / `batch` の summary JSON に Stage 1 fallback 情報を追加した。

期待効果:

- line 2 / 3 / 13 / 28 のような Stage 2 長時間応答を、既定 120秒で fallback へ切り替える。
- line 21 のような Stage 1 長時間解釈を、既定 120秒で fallback DDL へ切り替える。
- ベンチ結果で Stage 1 fallback と Stage 2 fallback を区別できる。

注意:

- Python thread を強制停止するわけではないため、timeout した LLM 呼び出しのワーカースレッドは背後で完了する可能性がある。
- API レスポンスは hard timeout 時点で返すため、ユーザー操作や CLI batch は長時間ブロックされにくくなる。
- 将来的には、HTTP クライアント側の request cancellation や非同期 worker / queue 化で、背後の LLM 呼び出し自体もより明確に制御する余地がある。

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

## 18. Build 248: sensory retention 後 30件ベンチ

Date: 2026-05-02

目的:

- Build 247 の density/cluster/fade 対応後に見えた「洗練されたが、情報量・楽しさ・豊かさが減った」問題を検証する。
- Stage 1.5 / Stage 2 / coerce / renderer に追加した、光・香り・温度・待つ時間・五感などの感覚情報保持が実作に効いているか確認する。

対象:

- 入力: `cli/out/tune-bench-030-after-806e30a/prompts.txt`
- 出力: `cli/out/tune-bench-030-sensory-248/`
- contact sheet: `cli/out/tune-bench-030-sensory-248/contact-sheet.png`
- 集計: `cli/out/tune-bench-030-sensory-248/analysis-summary.json`
- Stage1/Stage2: `nvidia` / `google/gemma-4-31b-it`

実行:

```sh
cd cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli batch \
  --base-url http://192.168.0.89:8100 \
  -f ./out/tune-bench-030-after-806e30a/prompts.txt \
  -o ./out/tune-bench-030-sensory-248 \
  --prefix bench030s248 \
  --png \
  --continue-on-error
```

結果:

- 成功: 30 / 30
- 失敗: 0 / 30
- total elapsed: 1,661,692 ms
- average elapsed: 55,390 ms
- median elapsed: 31,122 ms
- max elapsed: 194,990 ms
- tokens in/out: 316,496 / 12,740
- Stage 1 fallback: 1件 (`bench030s248-023`)
- Stage 2 fallback: 5件 (`bench030s248-003`, `009`, `022`, `026`, `028`)
- compose retry: 3件 (`bench030s248-002`, `004`, `030`)
- 100秒超: 9件 (`002`, `003`, `004`, `009`, `022`, `023`, `026`, `028`, `030`)

Score 集計:

- expanded count total: 1,756
- clustered arrangements: 10
- preserve_space: 19
- color_cycle: 8
- density: `high=7`, `medium=4`, `low=6`
- fade: `outward=15`, `directional=3`
- primitives: `line=44`, `ellipse=30`, `square=13`, `arc=4`, `circle=2`
- colors: `black=38`, `gray=28`, `white=14`, `red=11`, `blue=2`
- sensory hint sample: `002`, `005`, `008`, `009`, `011`, `014`, `015`, `024`, `025`, `030`

前回 Build 247 との比較:

- 成功率は 30/30 のまま維持。
- expanded count は 1,348 → 1,756 に増え、情報量は戻った。
- ellipse は 18 → 30 に増え、線と真円だけの単調さは少し緩和。
- preserve_space は 14 → 19、fade は 13 → 18 に増え、気配・膜・薄れの schema field 利用は増加。
- color_cycle は 10 → 8 に減り、多色の遊びはやや後退。
- black/gray は 54 → 66 に増え、色彩幅は依然として狭い。
- 100秒超は 7件 → 9件。Free API の遅延影響は悪化気味で、品質レビューとは別に運用上の課題として残る。

専門家レビュー:

### 批評家A: 現代抽象画・構成批評

- 改善: Build 247 より画面の密度差と素材感は戻っている。`008`、`014`、`024` は光や気配を補助層として残し、単なる幾何要素より詩的な読みが増えた。
- 改善: `001`、`006`、`017`、`030` は線の反復が風・息・雨・竹林と対応し、反復が単なる装飾ではなく時間性を持ち始めている。
- 懸念: `007`、`030` は密度が高く、情報量はあるが画面の呼吸が弱い。大数量の cluster は効いているが、作品としての焦点が濃い粒群に吸われる。
- 懸念: `016` は赤背景と黒楕円で強いが、主題が「熟した果実」以上に記号的な赤黒に縮約される。強い背景色の使用理由を Stage 2 がもう少し構図へ反映すべき。
- 懸念: `003`、`022`、`028` の fallback は「壊れない」ことを達成しているが、抽象画としては硬く、入力文の余韻が乏しい。

結論:

- 「洗練されすぎて痩せる」問題は一部改善。特に感覚語の保持は有効。
- ただし復元された情報が、色・面・構図の選択ではなく、黒/灰の線や楕円へ落ちやすい。豊かさを増すには、感覚語を primitive 追加だけでなく palette / spatial focus / opacity / texture strategy へ渡す必要がある。

### 批評家B: 多文化視覚表現・詩的普遍性

- 改善: `008` 病室、`024` 夜明けの湖、`025` 古い鏡のように、感覚語が「状況の温度」として残るケースが出た。これは文化依存の具象記号に頼らず、普遍的な空気感へ近づいている。
- 改善: `019` は茶室・炭・闇の簡素な緊張があり、日本的な余白の文脈とデジタル抽象の接続として良い。
- 懸念: `006` 畳部屋、`011` 庭、`029` 工場跡は灰色線に寄りすぎ、文化的な場の差が薄い。畳、庭、鉄骨がすべて線密度に回収されると、場所の固有性が失われる。
- 懸念: `026` 夏祭りは色紙・湿り・丸まりがあるため本来は楽しいサンプルになるはずだが、fallback のため矩形群が散らかり、祝祭後の湿度より UI 的な重なりに見える。
- 懸念: 青が 2 件しかなく、水・夜明け・湖・地下鉄・港の差が黒/灰/赤に吸収されている。文化的普遍性のためにも、色の語彙を増やす必要がある。

結論:

- 感情や雰囲気を DDL に伝える方向は正しい。
- 次は「場の性質」を、線種だけでなく、色温度、余白の圧力、重心、重なり方に分配するべき。

### 専門家C: 実装・生成品質エンジニア

- 改善: failure 0、empty instruction retry 3件、fallback 6件で、API と renderer の安定性は維持されている。
- 改善: `density / fade / preserve_space` の利用は増え、schema field は実出力に乗っている。
- 懸念: fallback が 6/30 と多い。うち 5件は Stage 2 hard timeout で、品質評価上は通常成功とは別に扱うべき。
- 懸念: fallback score の `density/fade/preserve_space` 利用が弱い。`003` は200個の四角がそのまま縦配置で、Build 247 で追加した clustering の意図とずれる。
- 懸念: 白背景上の白い感覚層は `coerce` により黒へ可視化されるため、`008`、`014` の「柔らかな光」が黒い要素として出る。見えることは重要だが、光の情緒を壊す。背景側を微調整するか、白を薄青/淡灰/低 opacity に寄せる専用ルールが必要。
- 懸念: `line=44`, `ellipse=30` で、triangle はゼロ。形状語彙の多様性はまだ限定的。葉・しずく・破片・面の欠けなどの自然プリミティブ/プラグイン候補が有効。

結論:

- 今回の修正は方向として有効だが、fallback と visibility 補正が美術的意図を壊すケースが目立つ。
- 次の実装は、通常成功ルートの拡張より、fallback/coerce/visibility の表現品質を上げる方が効く。

総合評価:

- Build 248 は Build 247 より情報量が戻り、感覚語の保持も確認できた。
- 作品の「楽しさ」は一部戻ったが、色彩と形状の選択肢はまだ狭い。
- 「薄い感覚層」が白背景上で黒へ変換される問題は、今回の一番重要な発見。
- fallback 使用時の品質が全体評価を下げている。fallback は安全装置としては機能するが、作品品質としては別改善が必要。

次の実装候補:

1. Sensory visibility 専用補正
   - `柔らかな光`, `五感`, `香り`, `透明な膜` などは、白背景でも単純な黒化を避ける。
   - white-on-white の場合は foreground を淡青/淡灰/赤ではなく、低 opacity の blue/gray と `color_hint` に保持する。
   - 大きい光面は background 側をわずかに darken する選択も検討する。

2. Fallback score の品質改善
   - fallback でも `density / cluster_count / fade / preserve_space` を使う。
   - 200個以上の DDL clause は、通常 coerce と同じ cluster budget を通す。
   - fallback の primitive は line/square へ寄せず、入力の場に応じて ellipse/arc/square/line を分散する。

3. Palette strategy の追加
   - Stage 1.5 で `temperature`, `time_of_day`, `place_tone` を簡易分類し、Stage 2 の `color_hint` と abstract color に渡す。
   - 黒/灰偏重を抑え、青・緑・赤・白を場面に応じて使い分ける。

4. Shape vocabulary の拡張
   - 既存 schema の範囲では、triangle / arc / rotated square / thin ellipse をもっと使う。
   - 次段では自然プリミティブ plugin の設計に接続し、葉・水滴・紙片・影片のような「抽象化された自然/物質形」を追加できる余地を作る。

5. Benchmark tooling
   - CLI batch summary を JSON ファイルへ保存する。
   - contact sheet 生成を CLI サブコマンド化する。
   - fallback 使用サンプル、slow sample、normal sample を自動で分けてレビュー対象にする。

実装状況:

- 1 は Build 249 で実装。白背景上の `柔らかな光`、`五感`、`香り`、`透明な膜` などを単純な黒線へ変換せず、淡い青/緑として `color_hint` を保持する。
- 2 は Build 250 で実装。Stage 2 fallback score でも大数量を `density / cluster_count / fade / preserve_space` へ畳み、200個以上の DDL clause を全面均一ではなくクラスタ化する。fallback primitive は triangle / arc / square / ellipse / line に分散する。
- 3 は Build 250 で実装。Stage 1.5 の DDL expansion と Stage 2 prompt へ、春・花・温かい光、水・夜・冷気、森・葉・香りなどの scene tone から palette を選ぶ方針を追加した。fallback でも `color_cycle` を使って春系、水夜系、多色系を保持する。
- 4 は Build 250 で実装。既存 schema の範囲で triangle、arc、rotated square、thin ellipse をより積極的に使う DDL expansion を追加した。葉・花びら・紙片・山・屋根などは、自然 primitive plugin の前段として抽象化された形へ変換する。
- 5 は Build 250 で実装。`inku-cli batch` は `--summary-json`、または `--out-dir` 指定時の `analysis-summary.json` に summary を保存する。summary には `review_sets` として全成功サンプル、fallback sample、slow sample、normal sample を含める。Free API の待ち時間は品質評価から除外するが、診断用メタデータとして保持する。`inku-cli contact-sheet` で PNG 出力ディレクトリから contact sheet を生成できる。

## 20. Build 250 現行構成 30件ベンチ

実施日: 2026-05-02

目的:

- Build 250 の現行 Stage 1 / 1.5 / 2 / renderer 構成で、30件の定点プロンプトを再実行する。
- Free API の待ち時間は品質評価から除外し、描画に成功した30件すべてを評価対象とする。
- 成功率、fallback 発生、DDL の情報保持、JSON/SVG への反映、芸術的完成度を確認する。

入力:

- `cli/out/tune-bench-030-after-806e30a/prompts.txt`

出力:

- `cli/out/tune-bench-030-build250/`
- `cli/out/tune-bench-030-build250/analysis-summary.json`
- `cli/out/tune-bench-030-build250/contact-sheet.png`

実行コマンド:

```sh
cd /Users/oikawas/projects/ddl-server/cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli batch \
  --base-url http://192.168.0.89:8100 \
  -f ./out/tune-bench-030-after-806e30a/prompts.txt \
  -o ./out/tune-bench-030-build250 \
  --summary-json ./out/tune-bench-030-build250/analysis-summary.json \
  --prefix bench030b250 \
  --png \
  --continue-on-error

UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli contact-sheet \
  ./out/tune-bench-030-build250 \
  --output ./out/tune-bench-030-build250/contact-sheet.png
```

結果:

- 成功: 30 / 30
- 失敗: 0 / 30
- total elapsed: 1,869,662 ms
- tokens in/out: 343,339 / 21,253
- Stage 1 fallback: 1件 (`008`)
- Stage 2 fallback: 6件 (`004`, `009`, `010`, `016`, `020`, `023`)
- fallback 合計: 7件 (`004`, `008`, `009`, `010`, `016`, `020`, `023`)
- slow sample: 9件 (`003`, `004`, `008`, `009`, `010`, `016`, `019`, `020`, `023`)

Score 集計:

- expanded count total: 1,816
- clustered arrangements: 11
- preserve_space: 22
- color_cycle: 11
- density: `high=7`, `medium=10`, `low=4`
- fade: `outward=16`, `directional=4`
- primitives: `line=50`, `ellipse=27`, `square=13`, `arc=3`, `circle=2`
- colors: `gray=34`, `black=29`, `white=16`, `blue=9`, `red=6`, `green=1`

Build 248 との比較:

- 成功率は 30/30 のまま維持。
- expanded count は 1,756 → 1,816 に微増し、情報量は保たれている。
- preserve_space は 19 → 22、color_cycle は 8 → 11 に増え、余白保持と色循環の field はより使われている。
- blue は 2 → 9 に増え、水・夜・冷気の色相は改善した。
- black は 38 → 29 に減ったが、gray は 28 → 34 に増え、黒/灰の合計は 66 → 63 と依然として高い。
- fallback は 6件 → 7件でやや増加。安全装置としては機能しているが、作品品質では通常成功サンプルとの差が残る。
- triangle は依然として出ていない。既存 schema 内の形状語彙拡張が JSON まで十分に到達していない。

専門家レビュー:

### 批評家A: 現代抽象画・構成批評

- 改善: `004`、`008`、`014`、`024` のように、気配・光・水面を薄い層として扱う方向は見える。Build 247 の痩せた構成より、画面に時間性が戻った。
- 改善: `006`、`021`、`027`、`030` は線の揺れや方向性が詩的な運動を持ち、単なる幾何パターンから少し離れている。
- 懸念: `001`、`005`、`017`、`029` は線の反復が主役化しすぎる。技法としては整っているが、入力文ごとの差が線幅・線数・方向に縮約される。
- 懸念: `003`、`028` は強い矩形面に回収され、テーマの細部より画面処理が前に出る。面を使う場合も、余白・欠け・境界の表情を増やす必要がある。
- 懸念: `010`、`016`、`020`、`023` の fallback 群は成立しているが、通常成功群と比べて詩的な飛躍が弱い。壊れないが、作品としての意外性が薄い。

評価:

- 情報量と安定性は改善済み。
- 次は「抽象画としての構図判断」を強める段階。線・楕円・灰に逃げず、入力ごとに面、余白、重心、非対称性を選ぶ必要がある。

### 批評家B: 多文化視覚表現・詩的普遍性

- 改善: `008` 病室、`014` 窓辺、`019` 茶室、`024` 湖のような静かな主題では、文化固有の具象を避けつつ、場の温度を抽象化できている。
- 改善: `004` 川辺、`015` 港、`030` 竹林は、色や反復により、自然の流れや湿度が以前より伝わる。
- 懸念: `006` 畳、`011` 庭、`026` 夏祭りなど、文化的な場の違いが線・小矩形・粒群に均されやすい。多文化的な普遍性は、固有性を消すことではなく、固有性を抽象化して残すことで成立する。
- 懸念: green が 1 件しかなく、森林・葉・香り・春の生命感が色として立ち上がりにくい。
- 懸念: 赤・青・白の使い分けは改善したが、黄・金・紫・茶のような入力語が6色抽象色へ落ちる際のニュアンス保持がまだ弱い。

評価:

- 感情・雰囲気を DDL に残す方向は正しい。
- 次は `color_hint` と場面分類を強め、文化的な場所性を色温度、余白、密度、配置の型として保持する。

### 専門家C: 実装・生成品質エンジニア

- 改善: 30/30 成功。Stage 2 hard timeout や empty instructions があっても、fallback により API エラーとしては失敗しない。
- 改善: `density / fade / preserve_space / color_cycle` の集計値は伸びており、schema field は実出力に乗っている。
- 懸念: fallback 7/30 はまだ高い。Free API の遅延は評価対象外だが、fallback 経由の作品品質は通常生成と同じ水準ではない。
- 懸念: primitive は `line=50`, `ellipse=27` に偏り、`triangle=0`。DDL expansion で追加した語彙が Stage 2 JSON に安定して残っていない。
- 懸念: `gray=34`, `black=29` で全体の約 66% が黒/灰。visibility coerce と palette strategy が安全側に寄りすぎている。
- 懸念: `score_expanded_count=1,816` は情報量としては良いが、大量展開が構図の豊かさではなく線数・粒数へ変換されるケースがある。

評価:

- システムの安全性は上がった。
- 品質向上には、Stage 2 の JSON 化時点で DDL の構図・色・形状意図を落とさない検証層が必要。

総合評価:

- Build 250 は「成功する」「壊れない」「一定以上の情報量を持つ」段階には到達している。
- Build 247 で失われた豊かさは一部戻ったが、表現の軸が線・楕円・黒灰へ集中しやすい。
- 現行の最大課題は、DDL が持つ色温度、場の固有性、形状語彙、構図意図が JSON 変換時に薄まること。
- fallback は運用上必要だが、fallback 作品がレビュー全体の印象を下げている。fallback を単なる安全装置ではなく、短い詩的再構成として扱う必要がある。

次の改善点:

1. Stage 2 JSON coverage checker
   - Stage 1.5 の DDL に含まれる `primitive`, `color_hint`, `density`, `fade`, `preserve_space`, `trajectory`, `rotation`, `texture` が JSON Score に反映されているかを post-check する。
   - triangle / arc / rotated square / thin ellipse などが DDL に出た場合、JSON 側でゼロになったら repair prompt または deterministic repair を走らせる。

2. Palette balance repair
   - 黒/灰が前景色の過半を占める場合、入力の scene tone に応じて blue / green / red / white へ一部を再配分する。
   - 春・葉・森・香りは green を候補に戻す。
   - 光・朝・湖・雪は white/blue を中心に、単純な gray 化を避ける。
   - 赤は果実・布・祭り・夕焼け・火に限定せず、温度や生命感のアクセントとして使う。

3. Shape diversity repair
   - 30件単位で triangle がゼロになる状態は避ける。
   - 山・屋根・紙片・鋭さ・折れ・傾きの語彙がある場合、triangle または rotated square を優先候補にする。
   - 線の群れで代替されている自然物や場所性を、面と輪郭へ分散する。

4. Fallback quality upgrade
   - fallback は1つの代表 instruction に縮約せず、DDL clause を 2-4 個の score instruction に分ける。
   - fallback でも `color_cycle`, `fade`, `preserve_space`, `density`, `cluster_count` を必ず候補化する。
   - hard timeout 後の fallback では、入力文の名詞だけでなく、感情語・時間帯・空気感を短く保持する。

5. Line dominance reduction
   - `line` が全 primitive の半数を超える場合、同じ意味を ellipse / square / arc に置換する repair を入れる。
   - 揺れ・気配・香り・光をすべて線で表すのではなく、薄い面、粒、弧、余白の圧力へ分散する。

6. Composition intent field
   - Stage 1.5 から Stage 2 へ、`focus_area`, `negative_space_role`, `asymmetry`, `visual_weight` のような構図意図を渡す。
   - 中央配置・均一散布を避け、入力文の主題に応じて重心を決める。
   - fallback と repair でもこの構図意図を保持する。

7. Benchmark review automation
   - `analysis-summary.json` から、黒/灰偏重、line 偏重、triangle 欠落、fallback 使用、expanded 過多を自動で抽出する。
   - contact sheet と summary を組み合わせ、次回から専門家レビューの前段に機械的な警告一覧を出す。

## 21. 追加フィードバックを踏まえた Next action 詳細

記録日: 2026-05-03

ユーザーフィードバック:

- 楽しい形がない。もっと複雑な形を作れないか。
- 数学的な均衡が感じられる画が少ない。
- 線の揺れ、表情はとても良くなっている。
- 緑色の primitive 指示が通っていない。色指示が通っているかを特に確認する。
- CLI サポートとして、色カタログを変更したテストを実施できるようにする。

専門家レビューから接続する主課題:

- Stage 1.5 の DDL に含めた形状・色・構図の意図が、Stage 2 JSON に落ちる過程で薄まっている。
- `line` と `ellipse` への偏りが強く、triangle / arc / rotated square / 複合形が十分に使われていない。
- 黒/灰への安全側補正が強く、green を含む scene tone が JSON と SVG まで届いていない。
- 余白や線の表情は改善しているため、次はそれを壊さずに、形・数学的秩序・色の到達率を上げる。

### 1. Color instruction trace と color catalog benchmark 対応

目的:

- 色指示が Stage 1 / 1.5 / 2 / renderer のどこで失われるかを追跡可能にする。
- 色カタログを変更した比較ベンチを CLI から実行できるようにする。

実装内容:

- `inku-cli paint` / `inku-cli batch` に `--color-catalog` を追加する。
- CLI の local config に既定 color catalog を保存できるようにする。
- 描画時の stdout と `analysis-summary.json` に以下を記録する。
  - requested color catalog
  - resolved color catalog
  - DDL 内の色語彙一覧
  - JSON Score の abstract color count
  - renderer で実際に解決された palette 色
  - color mismatch warning
- `analysis-summary.json` に `color_trace` セクションを追加する。

検証:

- 同一30件を `inku Default` と別カタログで実行し、色分布差を比較する。
- 緑系プロンプトを 10件追加し、DDL に green が出た場合の JSON 到達率を測る。
- `green_requested`, `green_in_score`, `green_rendered` を個別に集計する。

完了条件:

- CLI から色カタログ指定ベンチが実行できる。
- 緑指示が失われた場合、Stage 1.5 / Stage 2 / renderer のどこで落ちたか分かる。

### 2. Shape vocabulary coverage checker

目的:

- 楽しい形、複雑な形が出ない問題を、まず「DDL にあるのに JSON にない」問題として検出する。

実装内容:

- Stage 1.5 の expanded DDL から shape intent を抽出する。
  - `sharp`, `folded`, `leaf`, `petal`, `mountain`, `roof`, `paper`, `fragment`, `spiral`, `wave`, `nested`, `cluster` など。
- Stage 2 JSON Score の primitive 分布と比較する。
- DDL に shape intent があるのに JSON が `line` / `ellipse` に偏った場合、repair を実行する。
- repair は最初は deterministic にする。
  - mountain / roof / sharp -> triangle または rotated square
  - paper / folded / fragment -> rotated square
  - leaf / petal -> thin ellipse + arc
  - spiral / coil / curl -> arc group
  - nested / layered -> square / ellipse の入れ子

検証:

- 30件ベンチの `triangle=0` が解消されるか確認する。
- line が全 primitive の半数を超えるサンプル数を減らす。
- repair 前後の DDL / JSON 差分を summary に保存する。

完了条件:

- triangle / arc / rotated square が実ベンチで安定して出る。
- 「線で代替された形」を機械的に検出できる。

### 3. Complex shape composition layer

目的:

- primitive 単体ではなく、複数 primitive を組み合わせた「楽しい形」を作る。
- renderer の既存 primitive を活かしつつ、複合的な形の単位を導入する。

実装内容:

- Stage 1.5 に `motif` または `compound_shape` の概念を追加する。
- Stage 2 prompt に「単一 primitive ではなく、2-5個の primitive を1つの形として組む」指示を追加する。
- 初期 motif 候補:
  - leaf cluster: thin ellipse + arc + small line
  - paper shard: rotated square + thin line + fade
  - seed pod: ellipse + small circle group + arc
  - folded light: rotated square + translucent line group
  - mountain sign: triangle + vertical line + preserve_space
  - ripple knot: arc group + small ellipse
- JSON Score では motif を直接 schema に入れず、複数 instruction へ展開する。後方互換性は現段階では重視しないが、renderer 側の変更量を抑える。

検証:

- contact sheet 上で「単体図形の羅列」ではなく、局所的に読める形の塊が増えるか見る。
- expanded count を過剰に増やさず、motif 数と primitive 数を summary に記録する。

完了条件:

- 30件ベンチのうち少なくとも 10件で compound motif が使われる。
- 画面が騒がしくならず、局所的な楽しさが増える。

### 4. Mathematical balance strategy

目的:

- 数学的な均衡が感じられる画を増やす。
- ただし機械的な線対称・点対称へ戻らないようにする。

実装内容:

- Stage 1.5 に `balance_strategy` を追加する。
- 候補:
  - golden offset: 黄金比付近に重心を置く
  - root rectangle rhythm: √2 / √3 的な間隔
  - prime spacing: 2,3,5,7,11 の間隔を使う
  - fibonacci count: 3,5,8,13,21 の数量感
  - counterweight: 大きな面と小さな群れの釣り合い
  - orbit / field: 中心ではなく局所重心を持つ周回
  - near symmetry break: 対称に見えそうで崩す
- Stage 2 に「中央対称ではなく、局所重心と反対側の小要素で均衡を作る」ことを明示する。
- JSON Score に `focus_area`, `visual_weight`, `counterweight_area` などの構図意図を反映する。

検証:

- 30件ベンチで、中央固定や均一散布のサンプルを数える。
- contact sheet で、重心が画面中央に偏っていないか確認する。
- 数学的 strategy の使用回数を summary に記録する。

完了条件:

- 明示的な数学 strategy が 30件中 15件以上で使われる。
- 中央配置・単純対称の比率が下がる。

### 5. Line expression を維持した形への転用

目的:

- 改善済みの線の揺れ・表情を失わず、形の輪郭や面の境界へ応用する。

実装内容:

- line texture を、単なる線 instruction だけでなく、circle / ellipse / square / arc の輪郭処理にも使う。
- shape outline に以下の variation を追加する。
  - trembling edge
  - brushed contour
  - broken contour
  - layered contour
  - water-warped edge
- Stage 2 prompt に「線の表情を、独立した線だけでなく形の縁にも使う」ことを追加する。

検証:

- line primitive count が下がっても、線の表情が失われないかを見る。
- shape primitive の輪郭差が SVG 上で確認できるかを見る。

完了条件:

- line 偏重を減らしつつ、線表現の良さを保持する。
- 形が増えても硬い図形に戻らない。

### 6. Green / palette repair の優先実装

目的:

- 緑指示が通らない問題を優先して解消する。
- 色指示の到達率を定量的に扱う。

実装内容:

- Stage 1.5 の scene tone 判定で、以下を green candidate に明示的に入れる。
  - 森、葉、草、苔、竹、庭、香り、春、芽吹き、湿った自然
- Stage 2 の palette instruction に「green を gray/black に置換しない」制約を追加する。
- renderer の visibility coerce で green が背景に埋もれる場合、green を別色へ逃がすのではなく、明度・透明度・輪郭で可視化する。
- color catalog 解決後の実色が十分に見えるかを contrast check する。

検証:

- 緑系プロンプトを含む小ベンチを作る。
- `green_requested -> green_in_ddl -> green_in_score -> green_rendered` の到達率を記録する。
- 緑が0または1件に留まる場合は fail とする。

完了条件:

- 緑系プロンプトで green が JSON と SVG に到達する。
- 30件定点ベンチでも green が複数回出る。

### 7. Review automation の拡張

目的:

- 人間のレビュー前に、今回の問題を自動的に検出する。

実装内容:

- `analysis-summary.json` に以下の警告を追加する。
  - `line_dominance_warning`
  - `shape_diversity_warning`
  - `triangle_missing_warning`
  - `green_missing_warning`
  - `monochrome_bias_warning`
  - `fallback_quality_warning`
  - `math_balance_missing_warning`
- CLI に `inku-cli analyze-benchmark` を追加し、既存 summary から警告と改善候補を出す。
- contact sheet の生成時に、fallback sample や warning sample を別 contact sheet として出せるようにする。

検証:

- Build 250 の summary に対して警告が期待通り出ること。
- 次回ベンチで警告が減ったか比較できること。

完了条件:

- 次の30件ベンチで、人間レビューの前に機械的な問題一覧が得られる。

実装順:

1. CLI の color catalog 指定と color trace 保存。
2. Green / palette repair。
3. Shape vocabulary coverage checker。
4. Mathematical balance strategy。
5. Complex shape composition layer。
6. Line expression の shape outline への転用。
7. Benchmark review automation 拡張。

優先理由:

- 色指示、特に green の欠落は現在のベンチで明確に観測されているため、最初に trace 可能にする。
- 複雑な形と数学的均衡は、Stage 2 JSON で意図が落ちる問題を解決しないと安定しない。
- 線の表情は良くなっているため、削るのではなく形の輪郭・面の境界に移植する。

着手状況:

- 1 の CLI color catalog 指定を実装した。`inku-cli paint` / `inku-cli batch` は `--color-catalog` を受け取り、対応する renderer 用 `color_map` を `/api/paint` に送る。既存の `--catalog-id` は互換用 alias として残す。
- CLI local config に `color_catalog` を保存できるようにした。`inku-cli models --color-catalog mexican` のように既定カタログを変更できる。
- `paint` / `batch` の summary に `requested_color_catalog`, `resolved_color_catalog`, `color_map`, `color_trace` を追加した。
- `color_trace` には、入力/DDL から検出した色 marker、Score の color / color_cycle、missing requested colors、green delivery 状況、warning を含める。
- 2 の前段として、サーバーの `coerce_score` に green delivery repair を追加した。DDL に緑・森・葉・草・苔・竹・庭・香り・芽などの green intent があり、Score に green が無い場合、既存 instruction の一つを green に補修して `color_hint` に理由を残す。
- 3 の前段として、サーバーの `coerce_score` に shape delivery repair を追加した。DDL に山・屋根・鋭さ・波紋・渦・紙片・破片・折れなどの shape intent があり、Score に triangle / arc / square が欠ける場合、過密にならない範囲で補助 instruction を追加する。
- Stage 2 prompt に、複雑な形を 2〜5 primitive の局所 motif として構成する指示を追加した。葉、紙片、種、山、波紋を既存 primitive の組み合わせとして扱う。
- Stage 2 prompt に、数学的均衡は中央対称ではなく、golden offset / 三分割 / 白銀比 / prime spacing / fibonacci count / counterweight で作るという指示を追加した。
- 検証: `cli/tests/test_cli.py`, `server/tests/test_coerce.py`, `server/tests/test_composer.py`, `ruff check src tests` を CLI / server で実行済み。

## 22. Build 250 current: 色カタログ比較 30件ベンチ

実施日: 2026-05-03

目的:

- CLI の `--color-catalog` と `color_trace` が機能するか確認する。
- default / impressionism の2カタログで同一30件を実行し、色カタログ差、green 到達率、shape repair、数学的均衡の改善具合を確認する。
- Free API の待ち時間は品質評価から除外し、成功した描画をすべて評価対象にする。

入力:

- `cli/out/tune-bench-030-after-806e30a/prompts.txt`

出力:

- `cli/out/tune-bench-030-build250-current-default/`
- `cli/out/tune-bench-030-build250-current-default/analysis-summary.json`
- `cli/out/tune-bench-030-build250-current-default/contact-sheet.png`
- `cli/out/tune-bench-030-build250-current-impressionism/`
- `cli/out/tune-bench-030-build250-current-impressionism/analysis-summary.json`
- `cli/out/tune-bench-030-build250-current-impressionism/contact-sheet.png`

default 結果:

- 成功: 30 / 30
- 失敗: 0 / 30
- fallback: 2件 (`017`, `028`)
- slow sample: 5件 (`004`, `009`, `011`, `017`, `028`)
- tokens in/out: 366,235 / 18,612
- primitives: `line=44`, `ellipse=30`, `square=12`, `arc=3`, `circle=2`
- colors: `black=28`, `white=28`, `gray=19`, `blue=8`, `red=7`, `green=1`
- color trace:
  - requested: `white=22`, `black=20`, `blue=17`, `gray=14`, `red=9`, `green=6`
  - score presence: `white=23`, `black=22`, `gray=15`, `blue=10`, `red=9`, `green=3`
  - missing requested: `blue=8`, `green=4`, `black=3`, `white=3`, `red=2`, `gray=1`
  - warnings: `requested_color_missing_in_score=17`, `green_requested_but_missing_in_score=4`
  - green delivery rate: 3 / 6 = 0.5

impressionism 結果:

- 成功: 30 / 30
- 失敗: 0 / 30
- fallback: 4件 (`010`, `015`, `018`, `025`)
- slow sample: 5件 (`010`, `015`, `018`, `022`, `025`)
- tokens in/out: 326,781 / 11,706
- primitives: `line=44`, `ellipse=25`, `square=14`, `arc=3`, `circle=3`
- colors: `black=30`, `white=23`, `gray=19`, `red=10`, `blue=6`, `green=1`
- color trace:
  - requested: `white=20`, `black=20`, `blue=19`, `gray=17`, `red=9`, `green=7`
  - score presence: `black=25`, `white=21`, `gray=16`, `blue=8`, `red=8`, `green=2`
  - missing requested: `blue=11`, `green=6`, `gray=4`, `black=3`, `red=2`, `white=2`
  - warnings: `requested_color_missing_in_score=20`, `green_requested_but_missing_in_score=6`
  - green delivery rate: 2 / 7 = 0.2857

評価:

- CLI の色カタログ切り替えは動作している。contact sheet 上でも default と impressionism の色味差は明確に出た。
- `color_trace` により、green がどのサンプルで要求され、Score に落ちたかが追跡できるようになった。
- fallback は Build 250 直前の 7件から default 2件、impressionism 4件へ減った。安定性は改善している。
- line count は両方 `44` で、Build 250 の `50` より減ったが、依然として最大 primitive。
- square は default `12`, impressionism `14` で一定数出ている。arc は両方 `3`。triangle は依然として aggregate に出ていない。
- contact sheet 上では、`026` や `025` に局所的な複合形が見えるが、全体として「楽しい複雑形」はまだ少ない。
- 数学的均衡は、`029` のグリッドや `012` の斜め反復など一部に見えるが、golden offset / counterweight / prime spacing のような明確な構図判断にはまだ弱い。
- 緑の到達率は default で 50%、impressionism で 28.6%。green repair は不十分。

green 到達の問題:

- `007` 秋の森では、入力に森があり green marker が立つが、DDL と Score は赤・黒に寄り、green が落ちた。
- `011` 庭・枯れ草では、green marker が立つが、Score は black / blue / gray / white になり green が落ちた。
- `017` 竹林では、fallback 経由で gray / white に寄り、green が落ちた。
- `022` 手紙の余白では、`言えなかった言葉` の「葉」が marker に誤検出され、green requested になっている。日本語 substring ベースの green marker が過剰検出している。
- `012`, `026` は color_cycle に green が入り、green delivery は成立した。

次の改善点:

1. 日本語 color marker の精度改善
   - `葉` 単独で green marker にすると、`言葉` が誤検出される。
   - `葉` は `落ち葉`, `若葉`, `木の葉`, `葉っぱ`, `葉脈` などの語として検出する。
   - `草`, `苔`, `竹`, `森`, `庭`, `香り`, `芽` は維持するが、文脈に応じた過剰検出を避ける。

2. Green repair の複数色対応
   - 現状は既存 instruction の1つを順番に上書きするため、複数 missing colors がある場合、後続色で green が上書きされる可能性がある。
   - requested color が複数ある場合は、既存 arrangement の `color_cycle` に追加するか、補助 instruction を追加する。
   - green requested かつ green absent の場合は、他色より green を優先し、最後に必ず残るようにする。

3. Green intent の意味分解
   - `秋の森で落ち葉が深い赤` は主色 red が正しいが、green は背景・残響・森の低彩度層として薄く残すべき。
   - `枯れた草` は鮮やかな green ではなく、green/gray の中間として `color_hint` に枯草を残す。
   - `竹林` は green を主線または輪郭色として残す。

4. Triangle delivery の追加確認
   - shape repair は square / arc には効いているが、30件では triangle が aggregate に出ていない。
   - 定点30件に triangle を誘発する明確な山・屋根・鋭角 prompt が少ない可能性があるため、shape 小ベンチを別途作る。
   - ただし `遠雷の前、低い雲が街の屋根...` は roof intent があるため、triangle または rotated square が出るべき。現在は square 止まり。

5. Complex motif の強化
   - 現在は prompt 指示のみで、Score schema には motif 概念がないため、LLM が単体 instruction に戻りやすい。
   - deterministic repair で、leaf cluster / paper shard / ripple knot / mountain sign を追加できるようにする。
   - motif 数は 1作品あたり 1〜2 に制限し、過密化を避ける。

6. Mathematical balance trace
   - 現状の summary では、数学的均衡が実際に使われたか機械的に分からない。
   - `analysis-summary.json` に `math_balance_markers` を追加する。
   - radial count 5/8/13/21、golden-like center、rule-of-thirds-like center、counterweight-like opposite placement を検出する。

7. 次回ベンチ方針
   - まず green marker / green repair を修正する。
   - その後、green-heavy 10件小ベンチと shape-heavy 10件小ベンチを実行する。
   - 小ベンチで到達率を確認してから、再度 default / impressionism の30件比較へ進む。

実装メモ:

- Next action 1 として、日本語 green marker から単独 `葉` を外した。
- `落ち葉`, `若葉`, `木の葉`, `葉っぱ`, `葉脈` は green marker として維持した。
- `言葉` で CLI `color_trace` や server `coerce_score` の green repair が誤作動しないテストを追加した。
- Next action 2 として、複数 missing color の repair を `color` 上書きではなく `arrangement.color_cycle` 追加へ変更した。
- これにより、red / blue / green など複数色が同時に欠けても green が後続色で上書きされず、元の抽象色も cycle 内に残る。
- Next action 3 として、green intent の文脈別 repair を追加した。
- `竹林` は green を主線・輪郭色として優先し、`枯れ草` は gray/green の低彩度 cycle、`秋の森 + 落ち葉` は red 主色を保ったまま green を背景残響として cycle に残す。
- Next action 4 として、triangle delivery の優先度を上げた。
- `屋根`, `山`, `稜線`, `切妻`, `roof`, `ridge` などの intent があり、既に instruction が多い場合でも triangle を追加または弱い instruction と置換して残す。
- Next action 5 として、deterministic complex motif repair を追加した。
- `leaf_cluster`, `paper_shard`, `ripple_knot`, `mountain_sign` を既存 primitive 2個の組み合わせとして補助追加し、1作品あたり最大2 motif に制限する。
- Next action 6 として、CLI summary に `math_balance_markers` を追加した。
- `radial` の 5/8/13/21 配置、黄金比付近の中心、三分割付近の中心、対角の counterweight 配置を `paint` / `batch` の score metrics と `analysis-summary.json` 集計で確認できるようにした。

## 23. Build 256 focused small benches

実施日: 2026-05-03

目的:

- Build 256 の green repair / triangle delivery / complex motif repair / math balance trace を小ベンチで確認する。
- 以前のベンチと同じ Mac CLI コンテキストで実行する。
- Free API の待ち時間は品質評価から除外し、summary の slow / fallback 診断として扱う。

実行コンテキスト:

- 実行場所: `/Users/oikawas/projects/ddl-server/cli`
- API: `http://192.168.0.89:8100`
- Stage 1: `nvidia` / `google/gemma-4-31b-it`
- Stage 2: `nvidia` / `google/gemma-4-31b-it`
- Color catalog: `default`
- Build: CLI / server ともに `256`

### green-heavy 10

入力:

- `cli/out/tune-bench-build256-green-heavy/prompts.txt`

出力:

- `cli/out/tune-bench-build256-green-heavy-default/`
- `cli/out/tune-bench-build256-green-heavy-default/analysis-summary.json`
- `cli/out/tune-bench-build256-green-heavy-default/contact-sheet.png`

実行:

```sh
cd /Users/oikawas/projects/ddl-server/cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli batch \
  --base-url http://192.168.0.89:8100 \
  -f ./out/tune-bench-build256-green-heavy/prompts.txt \
  -o ./out/tune-bench-build256-green-heavy-default \
  --summary-json ./out/tune-bench-build256-green-heavy-default/analysis-summary.json \
  --prefix green256 \
  --png \
  --continue-on-error

UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli contact-sheet \
  ./out/tune-bench-build256-green-heavy-default \
  --output ./out/tune-bench-build256-green-heavy-default/contact-sheet.png
```

結果:

- 成功: 10 / 10
- 失敗: 0 / 10
- fallback: 1件 (`009`)
- slow sample: 1件 (`009`)
- tokens in/out: 129,830 / 8,521
- total elapsed: 586,923 ms
- primitives: `line=20`, `ellipse=9`, `circle=1`
- colors: `green=12`, `black=6`, `gray=6`, `blue=4`, `red=2`
- color trace:
  - requested: `green=10`, `white=5`, `black=4`, `gray=4`, `blue=3`, `red=2`
  - score presence: `green=12`, `black=6`, `gray=5`, `white=4`, `blue=3`, `red=4`
  - missing requested: `blue=1`, `green=1`, `white=1`
  - warnings: `requested_color_missing_in_score=2`, `green_requested_but_missing_in_score=1`
  - green delivery rate: 9 / 10 = 0.9
- math balance markers: `rule_of_thirds_like_centers=6`, `golden_like_centers=4`

評価:

- Build 250 current default の green delivery 3 / 6 = 0.5 から、green-heavy では 9 / 10 = 0.9 まで改善した。
- `竹林`, `枯れ草`, `秋の森 + 落ち葉`, `苔`, `若葉`, `葉脈` は green または color_cycle に残った。
- `009` は Stage 2 retry / fallback 経由だが、blue / green の color_cycle を保持した。
- `010` は入力に明示的な `緑には寄せず` があるため green を出さないのは意図に近いが、color_trace は `green_requested_but_missing_in_score` と警告する。否定文脈を `color_trace` がまだ扱えていない。

contact sheet 目視評価:

- `001` 竹林は緑の太い主幹と細い縦線が立ち、竹林の輪郭として読める。白い余白も残っている。
- `002` 枯れ草は薄い赤灰の線群として見え、green-heavy の意図に対して緑は弱い。ただし枯草の低彩度表現としては破綻していない。
- `003` 秋の森 + 落ち葉は緑背景に赤い葉が乗り、green 背景残響と赤い主役の関係は明確。
- `004` 苔・石・青い水は大きな赤茶の塊が主役化し、苔や水の読みが弱い。color delivery は成立しているがモチーフ解像度は低い。
- `005` 庭・若葉は右端に小さくまとまりすぎ、画面の大半が空きすぎている。緑は届いているが構図の主題性が弱い。
- `006` 夜の森 + 赤い実は黒背景に緑線と赤点があり、夜の森の静かな層としては成立している。
- `007` 竹の葉脈は赤系の有機線が多く、green intent と視覚結果がずれる。葉脈の線としては面白いが色の主張が不安定。
- `008` 乾いた草・埃は薄く散りすぎ、見える情報量が少ない。くすんだ緑の匂いという抽象性は出るが、作品として弱い。
- `009` 水面 + 木の葉は fallback 経由ながら青緑の塊として強く、色到達は良い。ただし密度が高く、葉や水面の差は読みにくい。
- `010` 否定文脈は黒い線だけが残り、`緑には寄せず` の意図に合う。警告だけが過剰。

まとめ:

- green repair は数値上も目視上も改善している。
- ただし green を入れるだけでは主題解像度は上がらず、`004`, `005`, `008`, `009` のように、モチーフの位置・密度・大きさの制御が次の課題。
- `green_requested_but_missing_in_score` は否定文脈を見ないため、`010` のような正しい非 green を誤警告する。

### shape-heavy 10

入力:

- `cli/out/tune-bench-build256-shape-heavy/prompts.txt`

出力:

- `cli/out/tune-bench-build256-shape-heavy-default/`
- `cli/out/tune-bench-build256-shape-heavy-default/analysis-summary.json`
- `cli/out/tune-bench-build256-shape-heavy-default/contact-sheet.png`

実行:

```sh
cd /Users/oikawas/projects/ddl-server/cli
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli batch \
  --base-url http://192.168.0.89:8100 \
  -f ./out/tune-bench-build256-shape-heavy/prompts.txt \
  -o ./out/tune-bench-build256-shape-heavy-default \
  --summary-json ./out/tune-bench-build256-shape-heavy-default/analysis-summary.json \
  --prefix shape256 \
  --png \
  --continue-on-error

UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli contact-sheet \
  ./out/tune-bench-build256-shape-heavy-default \
  --output ./out/tune-bench-build256-shape-heavy-default/contact-sheet.png
```

結果:

- 成功: 10 / 10
- 失敗: 0 / 10
- fallback: 0件
- slow sample: 0件
- tokens in/out: 121,911 / 4,955
- total elapsed: 382,048 ms
- primitives: `line=9`, `ellipse=6`, `square=5`, `arc=4`, `triangle=4`, `circle=3`
- colors: `black=17`, `blue=6`, `gray=6`, `green=2`
- color trace:
  - requested: `black=6`, `white=6`, `gray=4`, `green=4`, `blue=3`, `red=1`
  - score presence: `black=13`, `gray=4`, `white=4`, `blue=2`, `green=2`, `red=1`
  - missing requested: `green=2`, `white=2`, `black=1`, `blue=1`
  - warnings: `requested_color_missing_in_score=4`, `green_requested_but_missing_in_score=2`
  - green delivery rate: 2 / 4 = 0.5
- math balance markers: `rule_of_thirds_like_centers=6`, `radial_fibonacci_counts=2`, `golden_like_centers=2`, `counterweight_like_opposite_placements=1`

評価:

- Build 250 current default では aggregate に `triangle=0` だったが、shape-heavy では `triangle=4` になり、roof / mountain / ridge 系 intent の triangle delivery は改善した。
- `arc=4`, `square=5`, `circle=3` も出ており、line 偏重は小ベンチでは緩和した。
- `math_balance_markers` は radial fibonacci と counterweight を検出でき、trace の追加は機能している。
- green は shape-heavy では主目的ではないが、`落ち葉`, `若葉`, `庭`, `屋根 + 落ち葉` などで missing が残った。否定・優先 motif・色 intent の競合を次の改善候補にする。

contact sheet 目視評価:

- `001` 屋根・稜線は triangle が出ているが、黒い樹形のようにも見える。屋根として読むには上部の灰色矩形が強く、関係がやや曖昧。
- `002` 山の峰は赤背景に黒い三角が2つ立ち、峰として明確。線も対角に流れており、shape delivery は良い。
- `003` 紙片は小さな黒い square 群と斜線で読める。紙片としては成立するが、やや細かく遠い。
- `004` 波紋・渦は arc と円群が明確で、この小ベンチでは最も motif として読める。複合形の方向性は良い。
- `005` 落ち葉群は小楕円がまとまっており、葉群として読める。緑ではなく赤系に寄るが、落ち葉としては自然。
- `006` 切妻屋根は大きな三角と斜線で強い。ただし灰色線や対角釣り合いより三角が支配的で、構図は単純。
- `007` 手紙片 + 若葉は小さな要素群として分かれるが、紙片と葉の差はまだ弱い。complex motif は出ているが識別性が不足。
- `008` 山の頂 + 霧は黒い三角と弧で読める。霧の白は薄く、背景との関係は控えめ。
- `009` 螺旋の波 + 紙片は弧が連続しており波紋として成立する一方、紙片は見えにくい。
- `010` 屋根・落ち葉・波紋・紙片を二つに絞る意図は、一部の丸と矩形に整理されている。ただし「二つのモチーフだけを強く」はまだ視覚的に明確ではない。

まとめ:

- triangle / arc / square は aggregate と目視の両方で改善した。
- `004` の ripple、`002` / `006` / `008` の triangle は有効。
- paper_shard と leaf_cluster は「小さな要素群」としては出るが、互いの識別性が弱い。次は motif ごとの空間分離、サイズ差、色差、hint の renderer 反映を検討する。
- `math_balance_markers` は値として出るが、目視で明確に構図戦略として読める例はまだ限定的。counterweight は検出値 `1` だが、作品全体の重心設計としては弱い。

次の確認:

- contact sheet を目視し、triangle / paper_shard / leaf_cluster / ripple_knot / mountain_sign が「読める複合形」として成立しているか確認する。
- `color_trace` に否定文脈 (`緑には寄せず`, `not green`) を扱う警告抑制を追加するか検討する。
- 小ベンチでは改善が見えたため、default / impressionism の30件比較を Build 256 で再実行する。

### 3 persona review

対象:

- `cli/out/tune-bench-build256-green-heavy-default/contact-sheet.png`
- `cli/out/tune-bench-build256-shape-heavy-default/contact-sheet.png`
- 各 `analysis-summary.json`

#### Persona A: 技術評価者 / renderer・Score 診断担当

評価観点:

- DDL intent が Score primitive / color / arrangement に落ちているか。
- fallback / retry / trace が診断可能か。
- 修正対象が機械的に特定できるか。

評価結果:

1. green-heavy は green delivery 9 / 10 まで改善しており、Build 250 current default の 3 / 6 から明確に前進している。
2. color_cycle repair は機能している。`003` 秋の森 + 落ち葉、`009` 水面 + 木の葉では、主色と補助色の保持が summary 上で追える。
3. `010` の `緑には寄せず` は正しく green を出していないが、`color_trace` は green missing と警告する。否定文脈を marker 抽出が扱っていない。
4. shape-heavy は `triangle=4`, `arc=4`, `square=5` で、Build 250 current default の `triangle=0` 問題は小ベンチでは解消している。
5. `math_balance_markers` は summary に出ており、radial fibonacci / rule-of-thirds / counterweight の検出は動作している。ただし「検出された」ことと「構図として強い」ことは別で、評価補助指標として扱うべき。

技術的な次アクション:

1. `color_trace` に否定文脈を追加する。例: `緑には寄せず`, `緑ではなく`, `not green`, `avoid green`。
2. motif repair の `color_hint` を summary で aggregate できるようにし、leaf_cluster / paper_shard / ripple_knot / mountain_sign の到達率を数値化する。
3. math marker は count だけでなく、該当 line 番号も summary に残す。

#### Persona B: 美術ディレクター / 抽象作品品質担当

評価観点:

- 作品として視線が止まるか。
- 抽象化が単なる図形配置でなく、主題の気配を持つか。
- 密度、余白、色、重心が気持ちよく制御されているか。

評価結果:

1. green-heavy `003` は最も意図が伝わる。緑背景と赤い落ち葉の関係が明確で、色の役割が分かれている。
2. green-heavy `006` は黒背景に緑線と赤点が少量入り、夜の森として静かに成立している。情報量は少ないが余白の使い方は良い。
3. green-heavy `004`, `005`, `008` は主題の読みが弱い。色は入っているが、苔・庭・匂いといったモチーフの輪郭が画面上で立っていない。
4. green-heavy `009` は迫力はあるが、葉と水面が一体化しすぎている。fallback としては良いが、作品としては密度が強すぎる。
5. shape-heavy `004` は波紋・渦として最も完成度が高い。弧と円群の関係が自然で、複合形として読める。
6. shape-heavy `002`, `006`, `008` は triangle の到達が目視でも分かる。ただし `006` は三角が支配的で、対角の釣り合いより記号性が勝つ。
7. paper_shard / leaf_cluster は小要素として出ているが、作品の主役になるほどの形態差がまだない。紙片と葉の違いが弱い。

美術面の次アクション:

1. motif ごとに画面内の役割を分ける。例: paper_shard は角張った中サイズ、leaf_cluster は柔らかい小反復、ripple_knot は弧の層。
2. density repair は「数を減らす」だけでなく、主役 motif と背景 motif のサイズ差を作る。
3. 30件比較前に、shape-heavy の上位例 `002`, `004`, `006`, `008` を基準作品として残し、同じ方向に寄せる。

#### Persona C: 一般鑑賞者 / 非技術ユーザー

評価観点:

- 入力文を知らなくても、何かの気配や印象を受け取れるか。
- 見て楽しいか、もう一度見たいか。
- 文字説明なしで違いが分かるか。

評価結果:

1. green-heavy は全体として「緑が出るようになった」ことは分かるが、似た細線・小粒に見える作品もある。
2. green-heavy `001`, `003`, `006`, `009` は印象に残る。特に `003` は色の対比が強く、入力を知らなくても秋や森の気配がある。
3. green-heavy `008`, `010` は薄すぎて、単体作品としては見落としやすい。意図は正しくても鑑賞体験が弱い。
4. shape-heavy は green-heavy より形の違いが分かりやすい。三角、弧、四角が見えるため、一覧での変化がある。
5. shape-heavy `004` は最も見て楽しい。波紋や渦として直感的に読める。
6. shape-heavy `001`, `006` は強い形があるが、屋根か山か木かは人によって読みが割れそう。
7. shape-heavy `007`, `010` は複数モチーフの差が分かりにくい。説明を読まないと、紙片・葉・屋根・波紋の区別は難しい。

一般鑑賞者向けの次アクション:

1. 1作品内の主役を1つ強くし、残りを背景に回す。
2. contact sheet で見た時に小さく潰れる作品を減らす。小要素だけの作品は、最低1つ中サイズの anchor を置く。
3. 色と形の差を同時に使い、説明なしでも motif の違いが見えるようにする。

総合結論:

- Build 256 の小ベンチは、green 到達と triangle / arc / square 到達の改善を確認できた。
- 技術的には trace と repair が機能し始めている。
- 美術的には、到達した色や primitive を「作品の主役」として成立させる段階が次。
- 一般鑑賞では、shape-heavy の方が変化が分かりやすく、green-heavy は色到達後の構図・密度制御が課題。
- 次の実装優先度は、否定文脈の color_trace 修正、motif 到達率の数値化、motif ごとのサイズ・空間分離の強化。

実装メモ:

- Build 257 として、CLI summary 診断を拡張した。
- `color_trace` は `緑には寄せず`, `緑ではなく`, `not green`, `avoid green` などの否定文脈を `negated_color_markers` として記録し、requested color から除外する。
- これにより、green-heavy `010` のような「緑を出さないことが正しい」サンプルを `green_requested_but_missing_in_score` と誤警告しない。
- `_score_metrics` に `score_motif_hint_counts` を追加し、`leaf_cluster`, `paper_shard`, `ripple_knot`, `mountain_sign` の到達数を `color_hint` から集計できるようにした。
- `batch` summary に `score_motif_hint_lines` と `math_balance_marker_lines` を追加し、motif / math marker がどのサンプルで出たか追跡できるようにした。
- Build 257 の次ベンチでは、green-heavy `010` の warning が消えること、shape-heavy の motif 到達 line が summary で列挙されることを確認する。

## 24. 方針確認: 個別 motif 最適化を避ける

ユーザー指摘:

- 「形と色の楽しさ」を改善する際、どのような指示が来るか予想できない状況で、`leaf_cluster` / `paper_shard` / `ripple_knot` など個別ケースの形を直接調整し続けるのは危険ではないか。

確認結果:

- 懸念は妥当。
- Build 256 小ベンチで見えた弱点は、個別 motif の完成度だけではなく、未知入力でも形・色・サイズ・密度・配置の差が十分に出るかという、より汎用的な問題。
- したがって次のテーマ粒度は `generic composition diversity repair` とする。

3 persona review:

1. 技術評価者
   - 妥当。primitive / color / size / density / placement の偏りを検出して補う方が再利用性が高い。
   - ただし repair が強すぎると、全作品が同じ構成へ寄る。
   - 不足時のみ、最小補正にするべき。
2. 美術ディレクター
   - 妥当。課題は「葉を葉らしく」ではなく、画面内に主役・対比・背景の役割が出るか。
   - ただし `anchor + accent + texture` を毎回強制すると退屈になる。
   - 静かな入力や余白の入力では、補正を控えるべき。
3. 一般鑑賞者
   - 妥当。入力文を知らなくても、中心、色の違い、細かな動きがある方が見て楽しい。
   - ただし派手にすればよいわけではなく、白黒だけが合う入力もある。

実装方針:

- 個別 motif repair は補助・診断として残す。
- 次に入れるのは、未知入力にも効く composition role repair:
  - `anchor`: 見える中サイズの主役形
  - `accent`: 主色と違う小さな対比色 / 対比形
  - `texture`: 線・粒・反復の背景層
- 3役すべてを強制しない。
- 以下のような不足時のみ、最大1〜2個の instruction を追加する:
  - primitive が1種類だけ
  - line だけ
  - color が黒灰だけ
  - 見える中サイズ anchor が無い
  - expanded count が少なすぎる
- `余白`, `静か`, `薄い`, `一つ`, `だけ`, `minimal`, `quiet` などの入力では補正を弱める。
- 目的は「ベンチ語彙への最適化」ではなく、形・色・サイズ・密度・配置の最低限の分散を確保すること。

Build 258 予定:

- `coerce_score` に generic composition diversity repair を追加する。
- テストでは、個別 motif 名ではなく以下を確認する:
  - line only score に中サイズ anchor が1つ追加される
  - 黒灰だけの score に、入力文脈から控えめな accent color が1つ追加される
  - 静かな / 余白 / 一つだけ 系の入力では過剰補正しない

実装メモ:

- Build 258 として、`coerce_score` に `_with_composition_diversity_repair` を追加した。
- repair は motif 固有ではなく、composition role の不足だけを見る。
- `anchor` は、line only / primitive 1種類 / visible anchor 不足の時だけ、中サイズの ellipse を1つ追加する。
- `accent` は、既に visible anchor があるが色が黒灰に偏り、DDL 文脈から red / blue / green などの対比色を推定できる時だけ、arc を1つ追加する。
- `余白`, `静か`, `薄い`, `一つ`, `だけ`, `minimal`, `quiet`, `negative space` などの入力では repair を抑制する。
- これにより、未知入力でも「形・色・サイズの最低限の差」を補うが、静かな作品や余白の作品を壊しにくくする。

検証結果:

- Mac:
  - `UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_coerce.py -q`: 26 passed
  - `UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_api.py tests/test_renderer.py tests/test_coerce.py -q`: 121 passed
  - `UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests`: passed
  - `npm run check`: 0 errors / 0 warnings
  - `npm run build`: passed
- pentala deploy:
  - `./no-git-sync/scripts/deploy.sh`: rsync + service restart 完了
  - `UV_CACHE_DIR=/tmp/inku-uv-cache ~/.local/bin/uv run pytest tests/test_api.py tests/test_renderer.py tests/test_coerce.py -q`: 121 passed
  - `UV_CACHE_DIR=/tmp/inku-uv-cache ~/.local/bin/uv run ruff check src tests`: passed
  - `npm run check`: 0 errors / 0 warnings
  - `npm run build`: passed
  - `GET http://127.0.0.1:8100/health`: 200 `{"ok":true}`
  - `GET http://127.0.0.1:5173/api/info`: `build_number=258`
  - `GET http://127.0.0.1:5173/`: 200

次アクション:

1. Build 258 で green-heavy / shape-heavy の 10件小ベンチを再実行し、`composition anchor restored` / `composition accent restored` が必要なケースだけに出ているか確認する。
2. contact sheet では、個別 motif の見立てではなく、主役形・対比色・余白保持の3点を評価する。
3. 過補正が見えなければ、default / impressionism の30件比較へ戻る。

## 25. Build 259: composition repair 小ベンチ再評価

Build 258 の green-heavy 再実行中に、`010`「白い余白」「黒い線だけ」「緑には寄せず」で `composition anchor` が追加され、さらに negated green が `color_cycle` に復活する問題を確認した。

原因:

- `/api/paint` / `/api/compose` は Stage 2 へ原文を渡していたが、`coerce_score` には正規化 DDL のみを渡していた。
- そのため、原文にある `余白`, `だけ`, `緑には寄せず` が repair 抑制・否定色判定に使われなかった。
- server 側 `coerce.py` の color repair / DDL coverage も negated color を直接除外していなかった。

実装:

- Build 259 として、API 側で coerce 用コンテキストに `original_text + normalized DDL` を渡すようにした。
- server 側 `coerce.py` に `NEGATED_COLOR_MARKERS` を追加し、`緑には寄せず`, `緑ではなく`, `avoid green`, `not green` などを requested color / color_cycle / green intent context から除外するようにした。
- API テストで、`original_text` の `余白` / `だけ` が composition repair 抑制に効くことを確認した。
- coerce テストで、negated green が instruction color / color_cycle に復活しないこと、composition anchor も追加されないことを確認した。
- `web/BUILD_NUMBER`: 259

検証:

- Mac:
  - `UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest tests/test_coerce.py tests/test_api.py -q`: 83 passed
  - `UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests`: passed
  - `npm run check`: 0 errors / 0 warnings
  - `npm run build`: passed
- pentala deploy:
  - `./no-git-sync/scripts/deploy.sh`: rsync + service restart 完了
  - `UV_CACHE_DIR=/tmp/inku-uv-cache ~/.local/bin/uv run pytest tests/test_api.py tests/test_coerce.py -q`: 83 passed
  - `UV_CACHE_DIR=/tmp/inku-uv-cache ~/.local/bin/uv run ruff check src tests`: passed
  - `GET http://127.0.0.1:5173/api/info`: `build_number=259`

### green-heavy 10

入力:

- `cli/out/tune-bench-build256-green-heavy/prompts.txt`

出力:

- `cli/out/tune-bench-build259-green-heavy-default/`
- `cli/out/tune-bench-build259-green-heavy-default/analysis-summary.json`
- `cli/out/tune-bench-build259-green-heavy-default/contact-sheet.png`

結果:

- 成功: 10 / 10
- 失敗: 0 / 10
- fallback: 1件 (`010`)
- slow sample: 4件 (`002`, `003`, `004`, `010`)
- tokens in/out: 130,098 / 8,881
- total elapsed: 607,325 ms
- primitives: `line=24`, `ellipse=15`, `arc=5`, `circle=2`, `square=1`
- colors: `green=16`, `black=14`, `blue=6`, `gray=5`, `red=4`, `white=2`
- color trace:
  - requested: `green=9`, `white=6`, `black=5`, `blue=5`, `gray=4`, `red=2`
  - score presence: `green=13`, `black=9`, `blue=6`, `white=6`, `gray=5`, `red=4`
  - missing requested: `blue=1`, `white=1`
  - warnings: `requested_color_missing_in_score=1`
  - negated: `green=1`
  - green delivery rate: 9 / 9 = 1.0
- motif hints: `leaf_cluster=8`
- math balance: `golden_like_centers=10`, `rule_of_thirds_like_centers=4`, `counterweight_like_opposite_placements=2`
- composition repair:
  - `composition accent restored`: 1件 (`007`)
  - `composition anchor restored`: 0件

確認:

- `010` は fallback だが、`green_requested=false`, `green_rendered=false` になり、否定文脈は守られた。
- `010` では `composition anchor` も追加されず、白い余白と黒い線だけの意図を壊していない。
- green-heavy では一律の anchor 追加は起きず、repair は過補正になっていない。
- `007` の accent 1件は、灰霧と竹葉脈の黒灰寄り構成へ小さな対比形を追加する用途で、今回の方針に合う。

### shape-heavy 10

入力:

- `cli/out/tune-bench-build256-shape-heavy/prompts.txt`

出力:

- `cli/out/tune-bench-build259-shape-heavy-default/`
- `cli/out/tune-bench-build259-shape-heavy-default/analysis-summary.json`
- `cli/out/tune-bench-build259-shape-heavy-default/contact-sheet.png`

結果:

- 成功: 10 / 10
- 失敗: 0 / 10
- fallback: 1件 (`006`)
- slow sample: 1件 (`006`)
- tokens in/out: 114,085 / 4,873
- total elapsed: 363,918 ms
- primitives: `line=18`, `arc=11`, `ellipse=11`, `square=10`, `triangle=10`, `circle=1`
- colors: `black=37`, `green=10`, `blue=7`, `white=4`, `gray=3`
- color trace:
  - requested: `black=7`, `white=6`, `green=4`, `blue=3`, `gray=2`, `red=1`
  - score presence: `black=16`, `green=6`, `white=6`, `blue=3`, `gray=3`, `red=1`
  - missing requested: `blue=1`, `white=1`
  - warnings: `requested_color_missing_in_score=2`
  - green delivery rate: 4 / 4 = 1.0
- motif hints:
  - `mountain_sign=8` (`001`, `002`, `006`, `008`)
  - `paper_shard=8` (`003`, `007`, `009`, `010`)
  - `leaf_cluster=6` (`005`, `007`, `010`)
  - `ripple_knot=4` (`004`, `009`)
- math balance: `golden_like_centers=23`, `rule_of_thirds_like_centers=16`, `counterweight_like_opposite_placements=6`, `radial_fibonacci_counts=2`
- composition repair:
  - `composition anchor restored`: 0件
  - `composition accent restored`: 0件

確認:

- shape-heavy は `triangle=10`, `square=10`, `arc=11` まで出ており、Build 250 の `triangle=0` 問題は小ベンチでは解消している。
- motif hints は4種類すべて到達しているが、今回の主目的である composition repair は発火していない。これは既に形の多様性が十分あるためで、個別ケース最適化へ分岐していない。
- `006` は fallback だが、三角・灰色線・庭の green context は残っている。

総合判断:

- Build 259 の修正で、原文の否定・余白・限定表現が coerce に届くようになった。
- composition diversity repair は小ベンチ20件中1件だけ発火し、過補正ではない。
- green delivery は green-heavy / shape-heavy とも 1.0。
- 次は default / impressionism の30件比較に戻し、同じ制約が広い入力でも保たれるか確認する。

## Build 264 current: 色カタログ全バリエーション 10件ベンチ

目的:

- サーバー側の色カタログを正として、全カタログで同一プロンプト10件をレンダリングする。
- カタログ名・特徴にそぐう配色か、描画時に美術的に意味のある配色になっているかを、3名の異なるペルソナで評価する。
- パレット構成の改善案があれば、個別ケース最適化ではなくカタログ全体の性格調整として記録する。

実行:

- 日時: 2026-05-03
- 実行環境: Mac CLI から pentala LAN API `http://192.168.0.89:8100` を呼び出し
- build: `264`
- 入力: `cli/out/tune-bench-build264-color-catalog-10/prompts.txt`
- 出力: `cli/out/tune-bench-build264-color-catalog-10/`
- 対象カタログ: `default`, `japanese`, `renaissance`, `impressionism`, `chinese`, `nordic`, `indian`, `egyptian`, `mexican`, `british`, `greek`
- 各カタログ10件、合計110件を `inku-cli batch --png --continue-on-error --color-catalog <id>` でノンストップ実行し、各ディレクトリに `contact-sheet.png` を生成した。

結果:

| catalog | success | failed | fallback | green delivery | 備考 |
| --- | ---: | ---: | ---: | ---: | --- |
| default | 10 | 0 | 0 | 1.0 | 基準として安定。黒・赤・緑のコントラストが明快。 |
| japanese | 10 | 0 | 4 | 1.0 | 既定色に近く、和の伝統色としての差分が弱い。 |
| renaissance | 10 | 0 | 4 | 1.0 | 土色、赤、緑、白の組み合わせは絵画的。gray が茶に寄る。 |
| impressionism | 10 | 0 | 0 | 1.0 | 淡色と青地が強く、光の印象は出る。黒が青として強く出る。 |
| chinese | 10 | 0 | 1 | 1.0 | 朱、黒、金、翡翠系の方向は明快。gray の紫が強い。 |
| nordic | 10 | 0 | 0 | 1.0 | 最も統一感が高い。低彩度で、余白との相性がよい。 |
| indian | 10 | 0 | 2 | 1.0 | 華やかだが、blue が magenta に置換されるため意味が揺れる。 |
| egyptian | 10 | 0 | 0 | 1.0 | パピルス地、赤、金茶、ターコイズがテーマに合う。 |
| mexican | 10 | 0 | 1 | 1.0 | 祝祭的で楽しい。quiet prompt では彩度が勝ちやすい。 |
| british | 10 | 0 | 0 | 1.0 | クリーム地、navy、crimson、racing green が安定。 |
| greek | 10 | 0 | 1 | 1.0 | 白・青・テラコッタ・オリーブで地中海性が出る。 |

3名ペルソナ評価:

1. 色彩史・文化カタログ監修者

   - 適合度が高い: `nordic`, `egyptian`, `british`, `greek`, `chinese`
   - 条件付きで良い: `renaissance`, `mexican`, `impressionism`
   - 改善優先: `japanese`, `indian`
   - `japanese` は名称が「Japanese Tradition / 和の伝統色」だが、core map が `default` とほぼ同じで、藤紫・山吹が extras に留まる。結果として、出力全体が「和」よりも通常の inku default に見える。
   - `indian` は彩度と祝祭性は合うが、抽象色 `blue` が `#fc0fc0` の magenta になるため、プロンプト上の青い線・青い円という意味が崩れやすい。

2. 画家・構図評価者

   - 絵として意味が出やすい: `nordic`, `renaissance`, `egyptian`, `greek`
   - 形と色の楽しさが強い: `mexican`, `indian`, `chinese`, `impressionism`
   - `nordic` は低彩度の面と線が余白を保ち、10枚全体の鑑賞密度が安定している。
   - `renaissance` は暖色の地と赤・緑の関係が絵画的だが、灰色要求が茶色の面として出るため、影や石畳のニュアンスが土壁に寄る。
   - `impressionism` は光と淡色の方向性は良いが、暗部が青地に置換されると、夜景や黒い余白のプロンプトで画面支配が強くなりすぎる。
   - `mexican` は最も楽しいが、Rosa Mexicano と terracotta が強いため、静かな入力でも祝祭方向へ引っ張る。

3. レンダラー・プロダクト設計者

   - 実装仕様としては、抽象色名キーのままサーバー側カタログを展開している現在方針でよい。クライアント側の独自色モデルへ戻す必要はない。
   - 評価上の問題は API 連携ではなく、カタログごとの abstract color map の意味付けにある。
   - `gray`, `black`, `blue` のような構造色をテーマ色へ寄せすぎると、プロンプトの構造意図が変質する。テーマ性は保ちつつ、core map では意味が大きく崩れない範囲に置き、強い文化色は palette extras として使うのがメンテナンスしやすい。

国・地域出身者ペルソナによる補助レビュー:

- 注意: 以下は実在のネイティブ参加者によるレビューではなく、各国・地域の視覚文化に親しんだ想定ペルソナとしての評価である。ステレオタイプ固定を避けるため、単一の「正解色」ではなく、カタログ名と出力の納得感を確認する目的で使う。
- `default`: 国別評価の対象外。比較基準としては、抽象色名と出力色の関係が最も読み取りやすい。
- `japanese`: 日本出身の工芸・装丁に親しんだペルソナは、余白や黒赤緑の整理は悪くないが、「和の伝統色」と聞いて期待する藍、墨、胡粉、朱、常磐、山吹の気配が弱いと評価。とくに default と見分けにくい点が不満で、派手にするより、黒・白・赤・青・緑・灰の core map 自体を和色名に対応させる改善を求める。
- `renaissance`: イタリア出身の美術史に親しんだペルソナは、土色の地、赤、緑、白の関係に fresco / tempera の温度を感じると評価。一方で `gray` が Sienna 的な茶へ寄るため、石、陰影、銀灰色の意図が失われやすい。Sienna は良いが、core `gray` ではなく extra として残すのが自然。
- `impressionism`: フランス出身の近代絵画に親しんだペルソナは、淡いピンク、空色、ライラックの軽さは印象派らしいと評価。ただし黒が鮮やかな青面に変わると、光の揺らぎではなく poster 的な強さになる。暗部には黒ではなくても、深い violet / ultramarine の抑えた暗色が欲しい。
- `chinese`: 中国出身の書画・伝統意匠に親しんだペルソナは、朱、黒、白、金、翡翠の方向は理解しやすいと評価。紫の使い方は宮廷色として成立するが、`gray` の代替として毎回出ると現代的・装飾的に寄りすぎる。水墨や硯の灰黒を core `gray` に置くと、伝統性と描画安定性が上がる。
- `nordic`: 北欧出身のプロダクトデザインに親しんだペルソナは、低彩度、冷たい青灰、木や革に近い茶、抑えた緑の関係が非常に自然と評価。雪景色だけに寄らず、室内・木材・曇天の空気がある。変更するなら blue をもう少し muted にする程度で、大きく触らない方がよい。
- `indian`: インド出身の織物・祭礼色に親しんだペルソナは、強いピンク、サフラン、オリーブ、紺地の華やかさは楽しいと評価。ただし `blue` が magenta になるのは違和感が大きい。インド的な青なら indigo、peacock blue、Krishna blue の方向があり、magenta は Gulabi / festive accent として別に残すのが自然。
- `egyptian`: エジプト出身の古代意匠・観光図像に親しんだペルソナは、papyrus 地、赤、金茶、黒、turquoise の組み合わせは読み取りやすく、カタログ名との距離が近いと評価。`green` を turquoise と読むのも許容されるが、malachite green を core にして turquoise を extra にすると、より色名との対応が明確になる。
- `mexican`: メキシコ出身の民芸・都市色に親しんだペルソナは、Rosa Mexicano、明るい青、緑、terracotta の楽しさはよく合うと評価。祝祭性が強いこと自体は長所。ただし `gray` が terracotta になると、石畳・影・静けさの指示が土壁や陶器へ変わるため、neutral stone gray を core に戻す方が用途が広い。
- `british`: 英国出身の heritage design に親しんだペルソナは、cream、navy、crimson、racing green、slate gray の構成は納得感が高いと評価。落ち着きと制度的な堅さがあり、名前と出力が合う。ただし `black` が navy になるため、黒線の構造性を重視するなら charcoal を core にし、navy を extra に残す方が安定する。
- `greek`: ギリシャ出身の島嶼建築・古典色に親しんだペルソナは、white、Aegean blue、terracotta、olive、stone gray の関係が自然と評価。白青だけの観光記号に閉じず、土とオリーブが入る点がよい。大きな変更は不要で、青の明度差を extra に持たせると海・空・影の描き分けが増える。

ステレオタイプ化リスク評価:

- `default`: リスク低。地域・民族・国名を背負わない基準カタログなので、文化表象の単純化リスクは小さい。注意点は、default が暗黙の「標準文化」に見えないよう、仕様上は単に neutral baseline と扱うこと。
- `japanese`: リスク中。藍、朱、墨、山吹、藤紫へ寄せる改善は妥当だが、「和=渋い、余白、伝統色」だけに固定すると、現代的な日本の色彩や地方差を排除しやすい。core map は抑制的にしつつ、extra に明るい現代色や季節色を持てる余地を残す。
- `renaissance`: リスク低から中。Renaissance は国民性より時代様式のカタログなので、国別ステレオタイプより美術史的な固定化が主なリスク。すべてを茶、金、赤緑に寄せると museum filter になるため、stone gray や lead white 的な中立色を残す。
- `impressionism`: リスク低から中。これも国というより美術運動だが、「印象派=淡いパステル」へ単純化するリスクがある。暗部、補色、屋外光の揺らぎを表現できる深色を入れると、甘い装飾だけに寄らない。
- `chinese`: リスク中。朱、金、黒、翡翠、紫は強い記号性があり、使い方を誤ると「中国=赤金の宮廷風」に固定される。水墨、陶磁、紙、石、現代都市色も受け止められるよう、core には inkstone gray や porcelain blue などの静かな色を置く方がよい。
- `nordic`: リスク中。低彩度、青灰、木質、ミニマルだけにすると「北欧=静かで淡いデザイン」という商業的ステレオタイプへ寄る。ただし現状は派手な記号ではなく道具として使いやすい。extra に強い冬色・夏至色を追加できる余地があると固定化を避けやすい。
- `indian`: リスク高。高彩度、サフラン、ピンク、祭礼色だけで構成すると「インド=派手で祝祭的」という単純化に寄りやすい。blue を indigo / peacock blue に戻すだけでなく、earth, textile dye, monsoon, stone, paper などの落ち着いた色域を extra に含めると幅が出る。
- `egyptian`: リスク中から高。papyrus, gold, turquoise, red, black は古代エジプトの観光的記号として強く、現代エジプトや地域の多様性とは距離がある。カタログ名が古代意匠寄りなら許容できるが、`egyptian` のままだと代表性が広すぎる。将来的には `ancient_egyptian` など名称を狭める選択肢がある。
- `mexican`: リスク高。Rosa Mexicano、強い緑、青、terracotta、祝祭感は魅力的だが、「メキシコ=カラフルな祭り」へ寄りやすい。neutral stone gray や muted earth を core / extra に残し、静かな都市・石材・影の入力にも対応することで単純化を下げる。
- `british`: リスク中。cream、navy、crimson、racing green は heritage / institutional な英国像に寄るため、階級的・帝国的な記号へ偏る可能性がある。charcoal, fog gray, brick, rain blue など日常的で非儀礼的な色を含めると、硬い伝統表象だけにならない。
- `greek`: リスク中。white and Aegean blue は強い観光記号で、「ギリシャ=白壁と青い海」に固定されやすい。現状は terracotta, olive, stone gray が入るため単純化はやや抑えられている。extra に darker sea, marble shadow, dry grass などを持つと、島嶼観光以外の幅が出る。

パレット改善案:

- 方針: core map は `black`, `white`, `red`, `blue`, `green`, `gray` の抽象色としての意味を壊さない範囲で調整する。文化的・時代的な特徴色は、過度な代表化を避けるため palette extras に分散させる。国名系カタログでは、観光記号や祝祭色だけに寄せず、日常色・素材色・影色を含める。
- `default`: 変更不要。比較基準として、ニュートラルで意味が明確。仕様上は「標準文化」ではなく neutral baseline と明記する。
- `japanese`: core map は和色へ寄せるが、渋さだけに固定しない。`red` は朱、`blue` は藍、`green` は常磐、`gray` は消墨のように意味が明確な色へ寄せる。extras は藤紫・山吹に加え、季節色や現代的な明色を入れられる余地を残す。狙いは default との差分を出すことであり、「和=侘び寂び」へ閉じることではない。
- `renaissance`: `gray` は Siena ではなく warm neutral gray / stone gray に戻し、Sienna や gold は extras に残す。時代様式カタログとして、土色・鉛白・石・深緑・赤の絵画性を保ちつつ、すべてを museum-like な茶金へ寄せない。
- `impressionism`: `black` は cobalt blue ではなく dark violet / deep ultramarine 系の暗色へ変更する。Cobalt blue、sky blue、rose、lilac は palette extras または `blue` 周辺で残す。淡いパステルだけでなく、暗部・補色・屋外光の揺れを表現できる幅を持たせる。
- `chinese`: `gray` は purple から inkstone gray へ寄せ、purple と gold は extras に残す。`blue` は electric blue より porcelain/cobalt blue へ寄せる。朱金翡翠だけに固定せず、水墨、陶磁、紙、石の静かな色を core / extras の両方に含める。
- `nordic`: 大きな変更不要。必要なら `blue` を少し muted にし、extra に winter dark, summer light, wood, moss などを足せる構成にする。低彩度ミニマル一辺倒ではなく、季節差と素材感の幅を残す。
- `indian`: `blue` を magenta から indigo / peacock blue / Krishna blue 系へ戻す。Magenta は `Gulabi` などの festive extra として残す。高彩度の祝祭色だけでなく、earth, textile dye, monsoon, stone, paper の落ち着いた色域を extras に含め、ステレオタイプ化リスクを下げる。
- `egyptian`: カタログ名が広いので、古代意匠を意図するなら将来的に `ancient_egyptian` への名称変更も検討する。現行名のままなら、papyrus, gold, turquoise だけに寄せず、desert stone, Nile blue, linen, shadow を含める。`green` は malachite green を core にし、turquoise は extra に置くと抽象色との対応が明確になる。
- `mexican`: `gray` を terracotta から neutral stone gray へ戻し、terracotta は extra に残す。Rosa Mexicano は identity として維持してよいが、祝祭色だけに偏らないよう muted earth, urban stone, shadow, paper を extras に含める。静かな入力でも描画意図を保てる構成にする。
- `british`: 大きな変更不要。`black` は navy から charcoal へ寄せ、navy は extra に残すと黒線の構造性が安定する。heritage / institutional に偏りすぎないよう、fog gray, brick, rain blue, wool brown など日常的な素材色を extras に含める。
- `greek`: 大きな変更不要。white, Aegean blue, terracotta, olive, stone gray の関係は良い。白壁と青い海だけに固定しないよう、darker sea, marble shadow, dry grass, clay などを extras に足せる余地を持たせる。

次アクション:

- 改善優先度は `indian` の `blue`、`japanese` の core map 差分、`impressionism` の `black`、`chinese` / `renaissance` / `mexican` の `gray`。
- 追加で、`egyptian` はカタログ名の範囲を見直す余地がある。名称変更をしない場合は、ancient-symbol palette だけに閉じない extras を追加する。
- いずれも個別プロンプト対策ではなく、抽象色の意味を守り、カタログの文化的・時代的な幅を確保する調整として実装する。

### Build 265 方針: 文化的摩擦リスクを下げるカタログ rename

調査・スクリーニング:

- 国名、民族名、食、祭り、帝国、観光記号をカタログ identity として直接使うと、色カタログが文化全体を代表しているように見えやすい。
- 色名・商品名の過去事例では、肌色表現の不足や、暗い色に否定的な名前を付けることが批判されている。色名は「面白い名前」よりも、誰に何を代表させているかを確認する必要がある。
- 今回は国・地域名を外し、素材・光・技法・描画上の振る舞いを名前にする。

変更:

- 旧 id との比較表は Git 管理外の `no-git-sync/color_catalog_rename_map.md` に保存した。
- product code には互換 alias を残さず、新 id を正として扱う。
- 旧 `japanese` は `ink_season`、旧 `renaissance` は `fresco_study`、旧 `impressionism` は `open_air_light`、旧 `chinese` は `ink_porcelain`、旧 `nordic` は `cool_material`、旧 `indian` は `dye_earth`、旧 `egyptian` は `desert_mineral`、旧 `mexican` は `vivid_material`、旧 `british` は `weathered_heritage`、旧 `greek` は `sea_stone` に変更する。
- `map` は抽象色の意味を守る方向へ調整し、強い特徴色は `palette` に残す。とくに `blue`, `gray`, `black` は構造色としての意味を優先する。

次アクション:

- Build 265 を pentala に反映後、Build 264 と同じ10件プロンプトを新 id 全種で再実行する。
- 出力 root は `cli/out/tune-bench-build265-color-catalog-10/` とし、`no-git-sync/color_catalog_rename_map.md` を使って旧 id の contact sheet と比較する。

### Build 265 current: rename 後カタログ 10枚ベンチ

実行:

- 日時: 2026-05-03
- 実行環境: Mac CLI から pentala LAN API `http://192.168.0.89:8100` を呼び出し
- build: `265`
- 入力: `cli/out/tune-bench-build264-color-catalog-10/prompts.txt`
- 出力: `cli/out/tune-bench-build265-color-catalog-10/`
- 旧名→新名比較表: `no-git-sync/color_catalog_rename_map.md` (Git 管理外)
- 対象カタログ: `default`, `ink_season`, `fresco_study`, `open_air_light`, `ink_porcelain`, `cool_material`, `dye_earth`, `desert_mineral`, `vivid_material`, `weathered_heritage`, `sea_stone`
- 各カタログ10件、合計110件を `inku-cli batch --png --continue-on-error --color-catalog <id>` で実行し、各ディレクトリに `contact-sheet.png` を生成した。

補足:

- 初回 `sea_stone` 実行の5件目で、texture filter と blur filter が同じ SVG 要素に重複属性として出力され、PNG変換が停止した。
- レンダラーを修正し、既に texture filter を持つ要素には blur filter を追加しないようにした。途中出力は `cli/out/tune-bench-build265-color-catalog-10/sea_stone_svg_filter_failure/` に残し、修正後に `sea_stone` を再実行した。

結果:

| new catalog | old catalog | success | failed | fallback | slow | green delivery | elapsed ms | 比較メモ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| default | default | 10 | 0 | 1 | 2 | 1.0 | 406901 | 基準。今回は fallback が1件あり、Build 264 よりやや重い。 |
| ink_season | japanese | 10 | 0 | 0 | 0 | 1.0 | 239825 | fallback 4→0。旧名の文化摩擦を下げつつ、朱・藍・墨の差分が見える。 |
| fresco_study | renaissance | 10 | 0 | 2 | 2 | 1.0 | 418179 | fallback 4→2。茶に偏りすぎた gray を石色へ戻し、絵画的な地と赤緑は維持。 |
| open_air_light | impressionism | 10 | 0 | 2 | 2 | 1.0 | 562096 | fallback 0→2。淡色と青紫の光は強いが、黒面が夜青として支配的になる傾向は残る。 |
| ink_porcelain | chinese | 10 | 0 | 1 | 1 | 1.0 | 354580 | fallback 1→1。紫 gray 問題は解消し、朱・緑・青磁系の整理が良い。 |
| cool_material | nordic | 10 | 0 | 0 | 0 | 1.0 | 213136 | fallback 0→0。旧版同様に安定し、素材名へ寄せたことで代表性リスクが下がった。 |
| dye_earth | indian | 10 | 0 | 3 | 3 | 1.0 | 706952 | fallback 2→3。blue が magenta へ崩れる問題は解消したが、実行時間と fallback は悪化。 |
| desert_mineral | egyptian | 10 | 0 | 2 | 2 | 1.0 | 434146 | fallback 0→2。観光記号的な名前は避けられたが、砂地背景が強く、静かな入力でもテーマ色が勝つ。 |
| vivid_material | mexican | 10 | 0 | 0 | 0 | 1.0 | 266006 | fallback 1→0。gray を stone gray に戻した効果が大きく、祝祭記号名も外せた。 |
| weathered_heritage | british | 10 | 0 | 0 | 0 | 1.0 | 245854 | fallback 0→0。black を charcoal に戻し、navy 一辺倒が弱まった。 |
| sea_stone | greek | 10 | 0 | 0 | 0 | 1.0 | 242161 | fallback 1→0。白青観光記号だけでなく石・乾いた緑・土色が見える。 |

3名ペルソナ評価:

1. 文化的摩擦レビュー担当

   - 改善大: `ink_season`, `dye_earth`, `vivid_material`, `desert_mineral`, `sea_stone`
   - 国名・民族名・食・祭り・帝国を id/name/sub から外したため、「文化全体を代表する色」という見え方はかなり下がった。
   - ただし `weathered_heritage` は heritage という語が階級的・制度的な連想を持つため、リスクは低くない。現状は国名を外し、fog/brick/wool/rain の素材説明にしたことで許容範囲。
   - `desert_mineral` は安全側だが、砂漠・鉱物へ寄りすぎると地域文化の多様性ではなく地理イメージに固定される。今後は linen / shadow / river blue の比率も見たい。

2. 画家・構図評価者

   - 絵として最も安定: `cool_material`, `weathered_heritage`, `sea_stone`, `vivid_material`
   - 形と色の楽しさが増えた: `vivid_material`, `dye_earth`, `ink_porcelain`, `open_air_light`
   - `ink_season` は旧 `japanese` よりカタログ差分が出たが、赤線が強く、青・緑の出番は少なめ。余白と黒の骨格はよい。
   - `open_air_light` は淡いピンクと青紫が気持ちよい一方、暗い入力で画面全体が夜青に寄る。光のカタログとしては、暗部を少し軽くした方が屋外光らしい。
   - `dye_earth` は美術的には楽しい。深い地と染料色がよく出るが、静かな線の入力でも濃色背景が支配しやすい。

3. レンダラー・プロダクト設計者

   - API / JSON 連携はサーバー側カタログを正として記録できている。全 summary で `render_build_numbers: ["265"]` と `render_color_catalog_id` が確認できた。
   - 抽象色名キーの方針は維持でよい。今回の改善は、`blue`, `gray`, `black` をテーマ色に置換しすぎず、意味を守った点が効いている。
   - ベンチ中に見つかった SVG filter 重複は、カタログとは別のレンダラ品質問題。修正後の `sea_stone` は10/10で PNG 生成まで通った。
   - 性能比較は LLM 実行の揺れが大きいので、elapsed は参考値。品質判断は contact-sheet と fallback/欠落警告を優先する。

改善度合い:

- 文化的摩擦: 大きく改善。product code のカタログ id/name/sub から、国・地域・食・祭り・帝国・観光ラベルを外した。
- 色意味の保持: 改善。旧 `indian` の blue→magenta、旧 `mexican` の gray→terracotta、旧 `british` の black→navy、旧 `chinese` の gray→purple は解消した。
- 描画品質: 多くは改善または維持。`cool_material`, `vivid_material`, `weathered_heritage`, `sea_stone` は安定。`ink_season` も旧版より明確に良い。
- 残リスク: `open_air_light`, `dye_earth`, `desert_mineral` は背景・暗色が強く、入力によってはカタログの気分が形の意図を上書きする。次に触るなら個別ケース対策ではなく、背景化しやすい core color の明度・彩度を少し抑える。

次アクション:

- `open_air_light`: core `black` をもう少し軽い deep violet gray に寄せるか、暗背景化を抑える。
- `dye_earth`: identity は良いので、core `black` の濃さと high-chroma pink の支配を下げる。blue は現状維持。
- `desert_mineral`: paper/sand の背景支配を少し弱め、gray/green の素材色をもう少し構造色として使いやすくする。
- 変更する場合も、国・地域名へ戻さず、素材・光・技法の名前を維持する。

### Build 264 指摘点に対する Build 265 修正確認

確認観点:

- Build 264 の「3名ペルソナ評価」
- Build 264 の「国・地域出身者ペルソナによる補助レビュー」
- Build 264 の「ステレオタイプ化リスク評価」
- Build 265 の rename 後10枚ベンチ結果、contact sheet、summary JSON

修正済み:

- 名称リスク: 修正済み。Build 264 の `japanese`, `indian`, `egyptian`, `mexican`, `british`, `greek` など国・地域名を直接背負う id/name/sub は、Build 265 で `ink_season`, `dye_earth`, `desert_mineral`, `vivid_material`, `weathered_heritage`, `sea_stone` へ変更した。根拠は Build 265 方針の「国名、民族名、食、祭り、帝国、観光記号をカタログ identity として直接使うと、色カタログが文化全体を代表しているように見えやすい」という判断と、`server/src/inku_server/color_catalogs.py` の新 catalog 定義。
- `japanese` の default との差分不足: 修正済み。Build 264 では core map が default に近く、藤紫・山吹が extras に留まるため「和」より通常 default に見えると評価した。Build 265 の `ink_season` は `red=#d3381c`, `blue=#165e83`, `green=#007b43`, `gray=#595857` に変更し、fallback も `4 -> 0`。contact sheet でも朱・藍・墨の差分が見える。
- `indian` の `blue` が magenta へ崩れる問題: 修正済み。Build 264 では `blue` が `#fc0fc0` になり、青い線・青い円の意味が崩れると指摘した。Build 265 の `dye_earth` は core `blue=#006c8f` とし、magenta は `palette:Bright Pink` に移した。色意味の保持としては改善。
- `renaissance` の `gray` が茶へ寄りすぎる問題: 修正済み。Build 264 では gray が Sienna 的な茶に寄り、石・陰影・銀灰の意図が失われやすいと評価した。Build 265 の `fresco_study` は core `gray=#8a8178` の warm stone に戻し、Burnt Earth は palette extra に置いた。fallback も `4 -> 2`。
- `chinese` の `gray` が紫へ寄りすぎる問題: 修正済み。Build 264 では `gray` の purple が現代的・装飾的に出すぎると評価した。Build 265 の `ink_porcelain` は core `gray=#4b4b4f` とし、Mineral Violet は palette extra に残した。
- `mexican` の `gray` が terracotta になる問題と祝祭記号名: 修正済み。Build 264 では quiet prompt でも祝祭方向へ引っ張る、`gray` が stone/shadow でなく土壁や陶器へ変わると評価した。Build 265 の `vivid_material` は core `gray=#7d6f66`、名前も素材・顔料寄りに変更し、fallback は `1 -> 0`。
- `british` の `black` が navy になる問題: 修正済み。Build 264 では黒線の構造性を重視するなら charcoal がよいと評価した。Build 265 の `weathered_heritage` は core `black=#1f2933` とし、navy 系は `blue` / palette 側に残した。fallback は `0 -> 0`。
- `greek` の白青観光記号化: 概ね修正済み。Build 264 では white and Aegean blue への固定化リスクを挙げた。Build 265 の `sea_stone` は `stone gray`, `dry olive`, `clay red`, `night sea` を含み、白青だけに閉じない。fallback も `1 -> 0`。
- サーバー正本・JSON記録: 修正済み。Build 265 の全 summary で `render_build_numbers: ["265"]` と `render_color_catalog_id` が確認できた。API / JSON 連携は、クライアント側独自カタログではなくサーバー側カタログを正として扱えている。

要改善:

- `open_air_light`: 旧 `impressionism` の暗部支配が残る。名称は国・流派名から離れて安全側になったが、暗い入力で夜青の面が支配的になりやすい。Build 265 では fallback が `0 -> 2`、slow も2件。core `black=#2f2d66` をもう少し軽い deep violet gray に寄せるか、暗背景化を抑える必要がある。
- `dye_earth`: 色意味は改善したが、描画支配と実行指標は悪化。Build 264 の blue 問題は直った一方で、Build 265 は fallback `2 -> 3`、slow 3件、elapsed `706952ms`。深い地と high-chroma pink が静かな入力でも強く出るため、core `black` の濃さと pink の支配を下げる。
- `desert_mineral`: 旧 `egyptian` の観光・古代記号名は外せたが、砂漠・鉱物へ寄りすぎる別の固定化リスクが残る。Build 265 は fallback `0 -> 2`、slow 2件。paper/sand の背景支配を弱め、linen / shadow / river blue 的な幅を増やす。
- `weathered_heritage`: 出力は安定しているが、`heritage` 語の階級的・制度的な連想は残る。現状は fog/brick/wool/rain の素材説明で許容範囲だが、将来的により中立な素材名へ寄せる余地がある。
- `default`: カタログ rename の本題ではないが、Build 264 は fallback 0、Build 265 は fallback 1 / slow 2。比較基準としては再計測時に揺れを確認する。

結論:

- Build 264 の指摘のうち、文化的摩擦と抽象色の意味崩れは Build 265 で大半を修正できた。
- 残件は個別ケース最適化ではなく、`open_air_light`, `dye_earth`, `desert_mineral` の core color が背景・暗色として作品全体を支配しすぎる問題として扱う。
- 次の調整では、国・地域名へ戻さず、素材・光・技法・描画上の振る舞いによる命名方針を維持する。
