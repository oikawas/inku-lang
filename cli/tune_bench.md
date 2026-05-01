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
- Stage 2 が遅すぎないか

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

## 10. 進め方

1. 10 件パイロットを実施する
2. 評価ラベルを調整する
3. 30 件ベンチを実施する
4. 評価とラベルを記録する
5. ラベルを集計する
6. 修正案を Stage 別に整理する
7. 影響が大きく、実装が局所的なものから修正する
8. 修正後に同じ入力セットで再実行し、差分を見る
