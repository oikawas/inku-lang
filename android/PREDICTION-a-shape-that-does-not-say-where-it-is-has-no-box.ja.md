# 凍結: 場所を述べていない図形は、外接矩形を持たない（[I-269]）

**この文書は、製品コードを 1 行も書く前に commit で凍らせる**（実行規約 §2-8）。
ここに書いた数字を、実装のあとで書き換えない。実測との差は完了レポートに書く。

- **エージェント**: Opus 5（`claude-opus-5[1m]`）／ 契約 `a-shape-that-does-not-say-where-it-is-has-no-box.md`
  ／ 枝 `feat/a-shape-that-does-not-say-where-it-is-has-no-box` ／ 起点 `024df278`
- **測った木**: `/Users/oikawas/projects/ddl-server-android2`
  （`git status --porcelain` の出力が空・`git merge-base HEAD main` = `024df278`）

---

## 1. 着手前の満点（`rm -rf app/build` の後に全走）

```
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
       ANDROID_HOME="$HOME/Library/Android/sdk"
cd /Users/oikawas/projects/ddl-server-android2/android && rm -rf app/build && ./gradlew testDebugUnitTest
BUILD SUCCESSFUL in 2m 29s
```

`app/build/test-results/testDebugUnitTest/*.xml` から数えた:

| XML（クラス）数 | tests | failures | errors | skipped |
|---|---|---|---|---|
| **62** | **364** | **0** | **0** | **0** |

`git grep -c '@Test' -- 'android/app/src/test/**/*.kt'` の総和 = **364**（ファイル **62** 本）。
XML の tests と一致する。

**suite 全体を数えるメタゲートは無い。** `app/src/test/` を舐めて木を走査する検査は 4 本あるが
（`SaijikiIsGeneratedTest` `UiLanguageSettingTest` `WordingLintTest` `FoldAwayTheStaffageLevelTest`）、
いずれも**表示文字列・歳時記・添景の語**を見るもので、**テストの本数そのものを主張する検査は 0 件**。
したがって摂動の予測に「+1」の道連れは無い。**検査ファイルを 1 本足すことで赤くなる既存の検査も無い**。

---

## 2. 段 0-3 の結果 —— 既定値の由来（`git log -S`）

契約 §0-A が「意図して置かれた形跡が出てきたら、直す前に報告して止まる」と書いている件。

| 追った文字列 | 出た commit |
|---|---|
| `fun shapeBbox` | `239b52ad` の 1 本だけ |
| `pos?.optDouble(0, 0.4) ?: 0.4`（polygon の `center` 代用） | `239b52ad` の 1 本だけ |
| `ins.optDouble("radius", 0.12) * unit`（circle の `radius` 既定） | `239b52ad` の 1 本だけ |

`239b52ad` は **2026-07-23 の `feat(android): phase 2f implementation complete`**（9 ファイル・
19,745 行の追加）。**commit メッセージは 1 行で、本文が無い。**
**既定値についてコードにコメントも無い**（`shapeBbox` に在るコメントは `cloudform` の枝のものだけで、
それは 2026-08-16 の周に「server は両方を要求し、無ければ None を返す」と書いて追加されたもの）。

**→ 意図して置かれた形跡は出なかった。**一括の移植で、他の枝と同じ「欄が無ければ既定値」の
書き方が `shapeBbox` にもそのまま流れ込んだ形である。**止まらずに段 1 へ進む。**

---

## 3. 着手前に測った、契約に無い事実

### 3-1. 同じ既定値は関数の外でも使われている（段 1 の最後の箇条書き）

`0.12` `0.26` `0.16` `0.38` `0.24` `0.22` を `android/app/src/main/java/app/inku/mobile/render/` で
grep した。**`shapeBbox` の外にも同じ既定値が在る**:

| 在処 | 何をしているか | 本契約 |
|---|---|---|
| `DefaultSvgRenderer.kt:220` / `:275` / `:323`〜`:325` / `:3331`〜`:3332` | **図形そのものを描く枝**が同じ既定値で描く | **触らない**（§6 で 1 バイトも禁止・§0-B ③ の申し送りの領分） |
| `ServerRendererGeometry.kt:328` | `polygon` の点列を作る別の関数が `0.22` の同じ代用を持つ | **触らない**（`shapeBbox` ではない） |
| `pipeline/ServerScoreCoercer.kt:33`〜`:63` | coerce 層の `FieldSpec` の既定値（`0.15` `0.3` `0.35` `0.12`） | **触らない**（別の層。`0.12` は偶然の同値） |

**したがって段 1 の当て先は `ServerRendererGeometry.kt:735`〜`:792` の `shapeBbox` だけである。**

### 3-2. 摂動 P-7 が届く範囲（`circle` の箱を読む既存の検査）

- **凍結コーパス 51 枚のうち、`surface` の `texture` が `none` 以外の case は 2 件だけ**
  —— `06_surface_hatch` と `21_hatch_computer`、**どちらも `square`**。
  **`circle` の箱を読む凍結 case は 0 件。**
- 検査側で `circle` + `surface` を描くのは
  `TheEdgeSeepsAndEveryMarkCarriesItsOwnSeedTest` の 3 本（T-173 / T-174 / T-175）だけ。
  **いずれも `center` と `radius` を両方述べている**ので、段 1 でも P-1〜P-6 でも動かない。
- bleed の 6 本（T-166〜T-172）は `position` + `size` の図形で、**両方述べている**。

### 3-3. `shapeBbox` の呼び出し元は 1 か所（契約 §0-B ② の再測）

`git grep shapeBbox -- android/app/src/main/` = **定義 1 行 + 呼び出し 1 行**
（`DefaultSvgRenderer.kt:2168` の `?: return ""`）。契約の記述と一致。

---

## 4. 段が全部入った後の満点（**予測**）

| | XML（クラス）数 | tests | failures | errors | skipped |
|---|---|---|---|---|---|
| 着手前（実測） | 62 | 364 | 0 | 0 | 0 |
| **段 2 の後（予測）** | **63** | **370** | **0** | **0** | **0** |

新しい検査ファイル 1 本（`AShapeThatDoesNotSayWhereItIsHasNoBoxTest.kt`）に **T-182〜T-187 の 6 本**。

**段 1 だけで赤くなる既存の検査は 0 本と予測する**（→ §3-2。欄を欠く閉図形に面を描かせている
検査もコーパスの case も 1 つも無い）。

---

## 5. 摂動の予測（**本数ではなく名前の一覧**）

新しい検査のクラス名は `app.inku.mobile.render.AShapeThatDoesNotSayWhereItIsHasNoBoxTest`
（以下 `[新]`）。既存は `app.inku.mobile.render.ThePortAnswersTheSameWayTheServerDoesTest`（以下 `[既]`）。

| P | 何をする | **赤くなると予測する検査の名前（全体）** | 本数 |
|---|---|---|---|
| **P-1** | `circle` の門を既定値で埋める形へ戻す | `[新] testACircleMissingCentreOrRadiusHasNoBox`（T-182）<br>`[新] testABoxlessShapeGetsNoSurface`（T-186） | **2** |
| **P-2** | `ellipse` の門を同上 | `[新] testAnEllipseMissingCentreOrSizeHasNoBox`（T-183）<br>`[新] testABoxlessShapeGetsNoSurface`（T-186） | **2** |
| **P-3** | `square`+`triangle` の門を同上 | `[新] testASquareOrTriangleMissingPositionOrSizeHasNoBox`（T-184）<br>`[新] testABoxlessShapeGetsNoSurface`（T-186） | **2** |
| **P-4** | `polygon` の **`center` の代用だけ**を戻す | `[新] testAPolygonMissingCentreOrRadiusHasNoBox`（T-185） | **1** |
| **P-5** | `polygon` の **`radius` の代用だけ**を戻す | `[新] testAPolygonMissingCentreOrRadiusHasNoBox`（T-185） | **1** |
| **P-6** | `cloudform` の門を `null` を返さない形へ戻す | `[既] testACloudformMissingCentreOrSizeHasNoBox`（T-87） | **1** |
| **P-7** | `circle` の箱の幅を `r * 2.0` → `r * 2.2` | `[新] testTheBoxOfAStatedShapeDidNotMove`（T-187） | **1** |

### 5-1. なぜ P-4 と P-5 で T-186 が赤くならないと予測するか

**T-186 の `polygon` の case は `center` も `radius` も述べない。**
P-4 は `center` の代用だけを戻すので、`radius` の門が残って箱は `null` のまま。
P-5 は `radius` の代用だけを戻すので、`center` の門が残って箱は `null` のまま。
**T-185 のほうは、代用ごとに別の case を持つ** ——
「`position`+`size` は述べているが `center` が無い（`radius` は在る）」で P-4 を捕まえ、
「`center` は在るが `radius` が無い（`size` は在る）」で P-5 を捕まえる。

### 5-2. どの予測がいちばん外れやすいか

**P-7 の道連れ。** `TheEdgeSeepsAndEveryMarkCarriesItsOwnSeedTest` の 3 本
（`testAWashSurfaceDiffersFromMarkToMark` / `testAHatchSurfaceDiffersFromMarkToMark` /
`testAnExplicitSurfaceSeedMakesEveryMarkTheSame`）は **`circle` に `surface` を載せて描く**ので、
箱の幅が 10% 広がれば**描かれる要素の本数と位置は動く**。
それでも**緑と予測する** —— 3 本の主張は「3 つの痕の質感が別々か／同じか」と `total % 3 == 0` で、
**幅は 3 つの痕すべてに等しく効く**から構造は保たれる。
**この予測が外れたら、それは「箱の値を読む検査がもう 1 本あった」ということで、
本数ではなく名前で報告する。**

### 5-3. 予測が外れる 5 通りのうち、本契約で起こりうるもの

- ①**自分が書き換えた既存の検査を数え落とす** → 本契約は既存の検査を 1 本も書き換えない（§6 の禁止）。該当なし
- ②**その周に自分が結線した先を数え落とす** → 結線は増やさない（`shapeBbox` の中だけ）。該当なし
- ③**本数が相殺で一致する** → 起こりうる。**照合は名前の一覧で行う**
- ④**当て先の関数を 1 つしか数えない** → §3-1 で `shapeBbox` の外の 3 か所を先に数えた
- ⑤**検査が「何を読むか」を数え落とす** → §5-2 がその予測である

---

## 6. 実装の方針（段ごと）

| 段 | 触るファイル | 何を置くか |
|---|---|---|
| 1 | `android/app/src/main/java/app/inku/mobile/render/ServerRendererGeometry.kt`（`shapeBbox` のみ） | 4 枝を「必要な欄が両方そろっているときだけ入る」形にする。`cloudform` の枝は触らない |
| 2 | `android/app/src/test/java/app/inku/mobile/render/AShapeThatDoesNotSayWhereItIsHasNoBoxTest.kt`（新規） | T-182〜T-187 |

**「無い」の判定**: 配列の欄（`center` / `size` / `position`）は `optJSONArray(...) == null`、
数の欄（`radius`）は `isNull("radius")`。**どちらも「鍵が無いか `null`」だけを拾い、
`0` や `[0, 0]` は「述べている」として通す**（falsy 判定にしない・実行規約 §2-4）。

**触らないもの**: `DefaultSvgRenderer.kt`（並行するもう 1 本の領分）・
`ThePortAnswersTheSameWayTheServerDoesTest.kt`・凍結コーパス・`android/VERSION`・
`server/` `web/` `cli/` `shared/`・pentala・実機。
