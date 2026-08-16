# 凍結: 塗りは、どちらの言い方で書かれても同じ 1 つの要求（[I-248]）

**この文書は、製品コードを 1 行も書く前に commit で凍らせる**（実行規約 §2-8）。
ここに書いた数字を、実装のあとで書き換えない。実測との差は完了レポートに書く。

- **エージェント**: Opus 5（`claude-opus-5[1m]`）／ 契約 `a-fill-is-one-request-however-it-is-written.md`
  ／ 枝 `feat/a-fill-is-one-request-however-it-is-written` ／ 起点 `f16addd7`
- **測った木**: `/Users/oikawas/projects/ddl-server-android`（`git status` clean・`git merge-base HEAD main` = `f16addd7`）

---

## 1. 着手前の満点（`rm -rf app/build` の後に全走）

```
cd /Users/oikawas/projects/ddl-server-android/android && rm -rf app/build && ./gradlew testDebugUnitTest
BUILD SUCCESSFUL in 1m 25s
```

`app/build/test-results/**/*.xml` から数えた:

| クラス数 | tests | failures | errors | skipped |
|---|---|---|---|---|
| **57** | **325** | **0** | **0** | **0** |

`git grep -c '@Test' -- 'android/app/src/test/**/*.kt'` の総和 = **325**（ファイル 57 本）。
XML の tests と一致する。

**suite 全体を数えるメタゲートは無い**（`app/src/test/` を舐めて、テスト件数そのものを主張する
検査を探して 0 件）。したがって摂動の予測に「+1」の道連れは無い。

---

## 2. 着手前に測った、契約に無い事実

**`DefaultSvgRenderer.kt:218` の `regionFill` は、どこからも読まれていない。**
その `else` 分岐（`usesHandStroke(weight)` が偽の circle）は `fill="$fill"` を直に書いており、
`fill` は `attrs.fill`、すなわち `ServerRendererStyle.kt:64` が**閉図形なら常に入れる色**である。
`renderBodyShape`（`:1217` の `fillVal`）はこの分岐では呼ばれない。

実測（凍結コーパスの `05_circle_rotring` を、着手前の木で描かせて比べた）:

```
actual: <circle cx="500.000000" cy="500.000000" r="200.000000" fill="#111111" .../>
expect: <circle cx="500.000000" cy="500.000000" fill="none" ... r="200.000000" .../>
```

- **契約 §0-B ① の註と §5 の 2 番目の申し送りが書いている「`fillVal` が `regionFill` で
  上書きするので絵には出ない」は、この分岐では成り立たない。**塗られない円が塗りつぶされて出る
- **どの受入もこれを見ていない** —— `testEveryReferenceSvgMatchesOnPathsPointsAndDashes` は
  `d` / `points` / `stroke-dasharray` の 3 属性しか比べず、`fill` を比べない。
  `test05CircleRotringNoContourStroke` は `contour-stroke-v1` と `<path>` の不在しか見ない
- **本契約では直さない**（§5 は「触らない」と書いている）。段 1 は `:218` の式を段 1 の判定へ
  差し替えるが、**値が読まれない状態はそのまま残す**（結線すると絵が動き、それは契約の範囲外）

---

## 3. 実装の方針（段ごと）

| 段 | 触るファイル | 何を置くか |
|---|---|---|
| 1 | `render/ServerRendererGeometry.kt` | `CLOSED_SHAPES`（6 語）・`fillIsAskedFor`・`hasSurfaceTexture`・`fillsInterior` |
| 1 | `render/DefaultSvgRenderer.kt:218` / `:2439` | めいめいの式を `fillsInterior(ins)` の呼び出しへ差し替える |
| 2 | `render/DefaultSvgRenderer.kt:1712` | `texture == "solid"` なら鍵の `filled` を真・`surface` を `null` にする |
| 3 | `pipeline/ServerScoreCoercer.kt` | `_with_fill_as_a_surface_word` の両方向を、閉図形だけに置く |
| 4 | `pipeline/ServerScoreCoercer.kt` | texture の allowlist を server と同じ 10 語・同じ順序にし、**順序つきの名前つき val へ出す**（T-140 が突き合わせる先） |
| 5 | `pipeline/ServerScoreSchemaJson.kt` | enum へ `solid` を `none` の直後に足し、`description` を server の文に合わせる |
| 6 | `pipeline/LocalFallbackPipeline.kt:1669` | `optBoolean("filled", false)` を `fillIsAskedFor` の呼び出しへ |

**段 3 は段 4 より前なので、段 3 の commit 時点では `solid` → `filled` の向きを測れない**
（allowlist がまだ `solid` を `"none"` へ落とす）。**段 3 では `filled` → `solid` の向きだけが緑になり、
T-136 / T-139 は段 4 の commit で緑になる。**これは順序の必然であって、外した受入ではない。

**新しい受入の置き場**（新規 2 ファイル・**@Test 9 本**）:

- `app/src/test/java/app/inku/mobile/render/AFillIsOneRequestTest.kt` —— T-133 / T-134 / T-135（3 本）
- `app/src/test/java/app/inku/mobile/pipeline/AFillIsOneRequestCoerceTest.kt` —— T-136 〜 T-141（6 本）

**T-142 は既存の照合 `DefaultSvgRendererPhase2fTest.testEveryReferenceSvgMatchesOnPathsPointsAndDashes`
（51 枚を舐める 1 本）で代える。**代えたことは完了レポートに書く。

**枝の先端で期待する @Test 総和 = 325 + 9 = 334。**

**T-141 は `temperUnintentionalFilledShape` を反射で直に叩く。**
`normalizeServerScore` の通り道を使うと、段 3 の導出が先に `filled = true` を書いてしまい、
**段 6 を元へ戻しても緑のまま**になる（2 つの裁定が打ち消し合う）。
通り道に抑制が居ること自体は、既存の `FilledShapeTemperingWiringTest` が別に据えている。

---

## 4. 摂動の予測（**赤くなるテストメソッドの本数**）

**当てるのは製品コードだけ。`no-git-sync/scripts/perturb.py` を通す。**

| P | 当てるもの | 予測（本数） | 赤くなると読んだもの |
|---|---|---|---|
| **P-1** | `hasSurfaceTexture` から `"solid"` の除外を外す | **1** | T-133 |
| **P-2** | `DefaultSvgRenderer.kt:2439` を元の「surface が在れば塗らない」式へ戻す | **2** | T-133 / T-134 |
| **P-3** | `fillIsAskedFor` から `texture == "solid"` の項を外す | **2** | T-133 / T-141 |
| **P-4** | 段 2 の seed 正規化の枝を外す | **1** | T-135 |
| **P-5** | 段 3 の `solid` → `filled` の向きだけを外す | **1** | T-136 |
| **P-6** | 段 3 の `filled` → `solid` の向きだけを外す | **1** | T-137 |
| **P-7** | 段 3 の閉図形の縛りを外す | **1** | T-138 |
| **P-8** | 段 4 の allowlist から `solid` を外す | **3** | T-136 / T-139 / T-140 |
| **P-9** | 段 5 の enum から `solid` を外す | **1** | T-140 |
| **P-10** | 段 6 を `optBoolean("filled", false)` へ戻す | **1** | T-141 |
| **P-11** | `fillIsAskedFor` を常に `false` にする | **10** | T-133 / T-134 / T-141 / コーパス系 7 本（下記） |

**予測の根拠**:

- **P-8 が T-136 も赤くする** —— allowlist が `solid` を `"none"` へ落とすと、
  段 3 の `solid` → `filled` の枝が発火しない。契約の表は T-139 / T-140 しか挙げていないが、
  `normalizeSurface` が導出より前に走るので、**この 1 本は道連れである**
- **P-8 は T-141 を赤くしない** —— T-141 は coerce を通らない（上記）
- **P-11 のコーパス 7 本**の内訳（予測）:
  - `DefaultSvgRendererPhase2fTest.testEveryReferenceSvgMatchesOnPathsPointsAndDashes`（1）——
    塗りの 5 枚（`03_square_filled` / `23_square_filled_wild` / `26_tinyfill_circle_pen` /
    `30_square_filled_pencil_fine` / `35_square_filled_sea_stone_blue`）の `d` が変わる
  - `DefaultSvgRendererFillDabTest`（4）—— 塗りの dab / scan は `regionFill` が真でなければ出ない
  - `DefaultSvgRendererPhase2eTest.test03SquareFilledContourClassMatch`（1）
  - `GroupMembersReachEachEngineTest` のうち塗りを数える 1 本（1）
- **P-1 〜 P-10 でコーパスが赤くなったら、段が絵を動かした徴候なので報告して止まる**
- **既存の検査を 1 本も書き換えない予定**なので、「自分が書き換えた既存の検査」の道連れは 0 本。
  書き換えることになったら、その時点で予測へ足さずに**実測として報告する**
- **coerce の fixture は道連れにならない**（着手前に読んだ）——
  `coerce_governors.json` の `tempering_cases` の `expected` に `texture` は 1 件も無く、
  `CoerceGovernorsTest` は primitive / radius / size / color_hint しか比べない。
  `ServerScoreParityTest` は `filled` も `surface` も主張していない

---

## 5. 段 5 のあとに 1 度だけ回す server 側の検査

```
cd /Users/oikawas/projects/ddl-server && uv run pytest -q tests/test_thinness_declaration_position.py
```

`ServerScoreSchemaJson.kt` を読む唯一の server テスト。**緑を確認して報告に書く。**
（`server/` は 1 ファイルも触らない。）
