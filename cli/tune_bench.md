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

## 9. 進め方

1. 10 件パイロットを実施する
2. 評価ラベルを調整する
3. 30 件ベンチを実施する
4. 評価とラベルを記録する
5. ラベルを集計する
6. 修正案を Stage 別に整理する
7. 影響が大きく、実装が局所的なものから修正する
8. 修正後に同じ入力セットで再実行し、差分を見る
