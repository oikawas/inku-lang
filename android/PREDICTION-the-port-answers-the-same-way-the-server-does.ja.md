# 凍結: 満点と摂動の予測（契約 `the-port-answers-the-same-way-the-server-does`）

**エージェント**: Claude Opus 5（`claude-opus-5[1m]`・Android の実装セッション）
（**2026-08-16 訂正**: 最初に「Claude Opus 4.5」と書いた。**数字は 1 つも動かしていない** —— 名前だけの訂正）
**枝**: `feat/the-port-answers-the-same-way-the-server-does`／**起点**: `8b93bb9d`（`git merge-base HEAD main` で実測）
**測った日**: 2026-08-16 ／ **コードは 1 行も書いていない時点**

**⚠ この文書は捨てるためのものである。**置き場を `android/` にしたのは、
契約 §4-8 が「`android/` 以外が 1 ファイルでも在れば専任セッションは受け入れられない」と書いているため
（先例の repo 直下 `PREDICTION-*.md` はこの枝では使えない）。**受け入れの周に削除してよい。**

---

## 1. 着手前の満点（実測）

```
cd /Users/oikawas/projects/ddl-server-android/android && rm -rf app/build && ./gradlew testDebugUnitTest
BUILD SUCCESSFUL in 1m 27s
```

| 何 | 値 |
|---|---|
| クラス | 55 |
| tests | **305** |
| failures | 0 |
| errors | 0 |
| skipped | 0 |
| `git grep -c '@Test' -- 'android/app/src/test/**/*.kt'` の総和 | **305**（55 ファイル） |

---

## 2. 契約 §0-B の「未測定」を数えた（凍結コーパス 51 枚）

| 何 | 件数 |
|---|---|
| 雲形かつ `surface` を持つ case | **0**（雲形そのものは 4 件: 11・12・24・44） |
| `((end−start) mod 360)` が `abs(end−start)` と食い違う弧 | **0**（弧は 8 件、全部 順向きで `|Δ| < 360`） |
| `cluster_count > 0` の case | **1**（`42_arrangement_cluster_center`: `cluster_count=3`・`count=60`・`rhythm_spacing="none"`） |
| **`cluster_count > 0` かつ `rhythm_spacing != "none"` かつ localTotal > 1** | **0** |
| `renderer_arrangement.json` の cluster case | 4 件（`G-cluster-center` / `-corner` / `-edge` / `-preserve-edge`）—— **4 件とも `rhythm_spacing="none"`** |

**したがって 3 段とも凍結物を 1 バイトも動かさないはずである**（T-94 は 3 段を通して緑のまま）。

---

## 3. server から実測した期待値（この commit の server で測った）

`server/src/inku_server/renderer.py`（起点 `8b93bb9d` の現物）を直接呼んで得た値。

### ① 雲形の外接（`_shape_bbox`）

| 入力 | server の答え |
|---|---|
| `center=[0.5,0.5]`・`size=[0.4,0.3]`・canvas `golden`(1618×1000, unit 1000) | `[585.0, 332.0, 448.00000000000006, 336.00000000000006]` |
| 同じ instruction・canvas `square`(1000×1000) | `[276.0, 332.0, 448.00000000000006, 336.00000000000006]` |
| `size` が無い | `None` |
| `center` が無い | `None` |

**⚠ `golden` を選んだ理由**: `sizePx` は `unit` を掛ける。`width`/`height` を掛ける実装（P-3）は
正方形の紙では同じ値になって見分けられない。1618×1000 なら 400 と 647.2 に分かれる。

**⚠ server は center か size が無い雲形を描かない** ——
`_render_instruction` が `ValueError: cloudform requires center and size` を投げる（実測）。
**したがって T-87 が測るのは「bbox が `None` である」という判定そのものである。**

雲形＋`surface(hatch)` を canvas `golden` で描いたときの server の SVG:
`bytes=41958`・`path=16`・`polyline=33`・`rect=1`・`g=8`、
class に **`surface-stroke-v1 hatch-spacing-22.500`** が出る。

### ② 弧長（canvas `square`・`r = 0.3 × 1000 = 300`）

| 入力 | server の弧長 | `弧長 / r` | segment | stroke sample | speck(pencil) |
|---|---|---|---|---|---|
| `angle_start=300, angle_end=20` | 1466.0766 | **4.886922** | 147 | **72** | **55** |
| `angle_start=20, angle_end=300` | 1466.0766 | **4.886922** | 147 | **72** | **55** |

server の SVG（pencil の弧）: **`circle=55`**・class に **`arc-stroke-v1 controls-72 events-0`**。

**いまの移植が返す値（式から計算・実装前）**:
逆向き `300→20` は折り返して `Δ=80` になるので、
`2πr×(80/360) = 418.879` → **speck は 16 個**（server は 55）・`variedArcPathD` の点数は **42**（server の弧長なら 147）。
順向き `20→300` は折り返しても `Δ=280` で同じなので、**いまも server と同じ 55 / 147**。

**⚠ 発行日に見つけた、契約の範囲外の乖離**（直さない・報告する）:
server は非 hand-stroke の弧（`rotring`）に `_arc_points_with_variation` を使い **`_segment_count+1` 点**（実測 148 点）を打つが、
移植の `variedArcPathD` は **`segmentCount` 点ちょうど**（147 点）で、`t` の分母も `count` と `last` で違う。
**弧長を直しても 1 点ぶん食い違ったままである。**契約 §1 の 4 は弧長の式だけを名指ししているので、直さない。

### ③ まとまりの中の律動（`_expand_arrangement(ins, 12345, None, performance_seed=12345)`）

`{"primitive":"circle","center":[0.5,0.5],"radius":0.01,"arrangement":{"layout":"scatter","count":12,
"cluster_count":3,"rhythm_spacing":"loose","density":"high","margin":0.1,"path":"left_to_right"}}`

**⚠ `rhythm_spacing` は `"loose"` を選ぶ。** `_rhythm_t` が seed を読むのは `"loose"` の枝だけで、
`"accelerando"` と `"syncopated"` は seed を 1 度も使わない —— **その 2 つで測ると撹拌の摂動が必ず空振りする。**

server の 12 個の anchor（`loose`）:
`[0.02,0.412543] [0.340119,0.541814] [0.699842,0.554848] [0.084941,0.39198] [0.42187,0.526805]
[0.827802,0.525248] [0.146935,0.43004] [0.541844,0.537056] [0.906809,0.553446] [0.299174,0.41437]
[0.659988,0.548218] [0.98,0.563632]`

server の 12 個の anchor（`none`）:
`[0.02,0.412108] [0.381985,0.540708] [0.750369,0.551869] [0.077965,0.394438] [0.451416,0.527476]
[0.842931,0.528052] [0.153357,0.432018] [0.536153,0.538947] [0.924168,0.555076] [0.248504,0.409758]
[0.632627,0.548302] [0.98,0.561246]`

`_rhythm_t(i, 4, seed ^ k, "loose")`:
- k=0: `0.050287 0.359868 0.666895 1.0`
- k=1: `0.053782 0.399749 0.630162 1.0`
- k=2: `0.0 0.343757 0.599417 0.982426`

---

## 4. 受入の置き方（9 本を 1 ファイルに新設する）

`android/app/src/test/java/app/inku/mobile/render/ThePortAnswersTheSameWayTheServerDoesTest.kt`

| T | 測るもの（1 T = 1 @Test） |
|---|---|
| T-85 | 雲形＋surface で **面の要素が 1 つ以上出る**（個数は測らない。P-2/P-3 で赤くしないため） |
| T-86 | 雲形の外接が **server の 4 数と一致**（`golden`・`square` の両方） |
| T-87 | `center`／`size` を欠く雲形は `null`。**対照として揃っている雲形は非 null**（対照が無いと P-1 で緑のまま残る） |
| T-88 | 逆向き弧（300→20）で **speck 55 個**（`:2517` 由来）と **varied 弧の点数 147**（`:475` 由来） |
| T-89 | 順向き弧（20→300）で同じ 55 / 147 —— **T-88 と逆向きの対** |
| T-90 | 動かしてはいけない 2 箇所: `controls-72`（`:2452`）と `arcPointsWithVariation` の **148 点**（`:705`） |
| T-91 | `loose` で **まとまり 0 と 1 の局所 t の並びが違う**（性質。値は測らない） |
| T-92 | `rhythm_spacing="none"` の 12 anchor が **server と一致** |
| T-93 | `loose` の 12 anchor が **server と一致**（xor を値で釘付けする） |
| T-94 | 既存の凍結コーパス検査（新設しない） |

**予測する満点（3 段の後）**: **305 + 9 = 314 tests・0 failures**。

---

## 5. 摂動の予測（P-1〜P-13・1 本ずつ当てて戻す）

**道連れになりうる既存の検査**（枝の先端の全走で名指しし直す）:

- `DefaultSvgRendererPhase2fTest.testEveryReferenceSvgMatchesOnPathsPointsAndDashes` —— 51 枚の `d`/`points`/`dasharray`。**`<circle>` は見ない**
- `DefaultSvgRendererPhase2fTest.testAllReferenceSvgStructureParity` —— **10 枚だけ**（04・10 を含む）。要素数を数えるので **`<circle>` も見る**
- `DefaultSvgRendererPhase2fTest.test04ArcCrayonExactParity` —— `arc-stroke-v1` の `d` だけ
- `DefaultSvgRendererPhase2fTest.testArrangementExactParity` —— `renderer_arrangement.json` の 42 case（うち cluster 4 件）
- `ServerRendererCloudformAndRelationsTest.testReferenceSvgParity11To14` —— 11〜14 の `d` と class

| P | 何を戻すか | **赤くなると予測する検査（本数）** |
|---|---|---|
| P-1 | cloudform 枝を消す | T-85・T-86・T-87 = **3**。コーパスは 0（雲形＋surface が 51 枚に無い） |
| P-2 | 係数を `0.5`/`1.0` へ | T-86 = **1** |
| P-3 | `sizePx` を通さず `width`/`height` を掛ける | T-86 = **1**（`golden` で 400 対 647.2） |
| P-4 | `center`/`size` の欠落を既定値で埋める | T-87 = **1** |
| P-5 | `ServerRendererGeometry` の弧長（`:475` 由来）を折り返す式へ | T-88 = **1**（点数 147→42）。既存は現状の式に戻るだけなので 0 |
| P-6 | `DefaultSvgRenderer` の弧長（`:2517` 由来）を折り返す式へ | T-88 = **1**（speck 55→16）。既存 0 |
| P-7 | 動かしてはいけない `:2452` を折り返す式へ | T-88・T-90 = **2**。コーパスの弧は 4 件とも順向きなので既存 0 |
| P-8 | 弧長から `abs` を外す | T-88 = **1**（逆向きが負になり下限へ張り付く）。**空振りしない**。T-89 は正のまま緑 |
| P-9 | 律動 seed を `seed` そのままへ | T-91・T-93 = **2**（T-92 は緑） |
| P-10 | 撹拌を `"$seed:$clusterIndex"` の連結へ | T-93 = **1**（**T-91 は緑**） |
| P-11 | `seedForCluster` の `0xC1A57` を消す | T-92・T-93・`testEveryReferenceSvgMatchesOnPathsPointsAndDashes`・`testArrangementExactParity` = **4**。**T-91 は緑**（律動の撹拌は無傷）。`testAllReferenceSvgStructureParity` は 42 を見ないので緑 |
| P-12 | 弧長を補角 `r × radians(360 − |Δ|)` へ | T-88・T-89・`testAllReferenceSvgStructureParity`（04 の `<circle>` 数）・`test04ArcCrayonExactParity` = **4**。`testEveryReferenceSvgMatchesOnPathsPointsAndDashes` は **緑**（speck は `<circle>` で `points` に出ない） |
| P-13 | 撹拌を `rhythmSpacing` の条件の外へ出し `"none"` でも `rhythmT` を通す | T-92・`testArrangementExactParity`・`testEveryReferenceSvgMatchesOnPathsPointsAndDashes` = **3**（**T-91・T-93 は緑**） |

**合計 25 本**（13 本の摂動を通じて。1 本ずつ当てて戻す）。

**⚠ 予測が外れる可能性を自分で挙げる**（実測との差は完了レポートに書く）:

1. **P-12 と `test04ArcCrayonExactParity`** —— 04 は `crayon`。speck の個数が変わっても
   `arc-stroke-v1` の `d` は変わらないかもしれない（speck は同じ `<g>` の外に出る）。その場合この 1 本は緑。
2. **P-7 と既存のコーパス** —— `2πr×(Δ/360)` と `r×|radians Δ|` は数学的に同じでも浮動小数点で 1 ULP 違いうる。
   `rint` の境界に当たれば分割数が動き、コーパスが道連れになる。**予測は「動かない」。**
3. **P-8 が `:475` と `:2517` の両方に当たるか** —— 当て方次第で片方だけになる。両方に当てる。
