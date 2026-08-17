# inku Changelog

**Public English release notes** — See [SPEC.md](SPEC.md) for the current English specification and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for the short developer entry point.

This file records changes chronologically. If a historical note conflicts with the current specification, the current specification wins. The more detailed canonical history is maintained in Japanese in [CHANGELOG.ja.md](CHANGELOG.ja.md).

**This file holds the 30 entries from v2.5.0 (2026-07-25, render engine 12) onward.** Earlier entries are archived.

| Archive | Range | Entries | Contents |
|---|---|---|---|
| [v1.72 through v2.4](docs/history/changelog-v1.72-v2.4.md) | 2026-07 | 44 | from the refine-and-compare UI to freezing the reference corpora |
| [v0.1 through v1.71](docs/history/changelog-v0.1-v1.71.ja.md) | 2026-04-02 to 2026-05 | 73 | **Japanese only.** From the first sketch to the Stage 1.5 groundwork |

**To follow the drawing versions alone, see [docs/spec/render-engine-history.md](docs/spec/render-engine-history.md)**, which lists render engine 1 through 15 newest-first with the moved and unchanged counts for each.

---

### v2.5.0 — de-regularizing the performance, and "unleashed" (render engine 12) (Build 706, 2026-07-25)

**Up to engine 11 the performance looked varied but was periodic.** The width envelope was a fixed `max(0, sin(pi t))` hump, so **every stroke was fattest exactly at its midpoint and thinned symmetrically to both ends**. The correction event beat with `sin((i % 5) * pi / 2)` — **a period of five**. Closed contours carried a thin seam opposite a fat middle, and the material outline was drawn with an even dash and evenly spaced specks. Engine 12 replaces all four with seeded low-frequency noise, and adds **a length-scaled gesture to the centreline itself**.

- **De-regularized envelope.** Replaced by `_edge_window(t) * _swell(t, seed)`. `_edge_window` is a raised-cosine ramp over the outer 16% at each end and **imposes no hump in the middle** — it states only the fact that the endpoints are pinned. `_swell` is per-seed low-frequency noise, so **where a stroke reads as fullest now wanders from stroke to stroke**. A closed contour has no endpoints, so it skips the edge window and uses `_swell` alone (`CLOSED_ENVELOPE_FLOOR` is deleted; the spurious thin seam is gone).
- **The correction event is length-based.** The sample-index modulus `i % 5` is replaced by a seeded hash kick, so **texture no longer changes when the sample count does**.
- **Centreline gesture.** `ToolGrammar` gains a tenth field, `gesture`: a low-frequency wander of the centreline itself, scaled by stroke length, producing bends, curls, and self-overlap. It is a distinct quantity from `energy_lateral`, which is normalized by pen width. Endpoints stay pinned by the window; determinism comes from the seed.
- **Material outline layer.** It now follows the gestured centreline (`<polyline class="material-outline">`), with a variable mark/gap dash, a wandering offset, and non-uniform speck placement. `rotring` lines pass straight through — the machine pole.
- **The "unleashed" (`wild`) toggle.** One switch **for the whole work** that lifts the performance ceiling (`WILD_GAIN = 3.5`). **It removes only the amplitude ceiling and the ban on self-intersection; endpoint pinning and determinism hold whether it is on or off.** It is recorded as a generation parameter next to `render_seed` (`history.render_wild`; NULL means a work from before the column existed, which is kept distinct from OFF), used on replay, and **included in the edition identity `rh3`**. The UI is a toggle in InputPanel with ja/en strings. This sits in a different layer from variation (Stage 1.5): it is a Renderer-layer knob.
- **The `rh3` payload change is absorbed by the version bump.** Adding `render_wild` changes the material, but **`render_engine_version` is inside the same payload**, so any value computed under the old material contains `"11"` or lower and any under the new contains `"12"` or higher. The two can never collide, so the format name stays `rh3`. This argument **only holds because the engine version moved at the same time**, and SPEC now says the material must never be extended on its own.
- **Froze the `render-engine-12/` reference corpus (199 of 220 changed).** **21 cases did not move, and what they are is itself the explanation of engine 12.** The 12 `rotring` cases are byte-identical: its grammar is all zeros, so de-regularization has nothing to reach — **the machine pole of the tool vocabulary is exactly where it was**. The 9 `cloudform` cases are byte-identical for a different reason: a cloudform is emitted as a Catmull-Rom path, never enters `stroke_engine`, and carries no material outline layer. **This is a gap engine 12 exposed, not one it created** (the contour does vary by tool — all 10 tool digests differ).
- **Implemented the "store only what moved" rule in the generator.** The README and SPEC §15.7 had required it for some time, but the generator wrote all 220 bodies whenever it created a new directory. Engine 11 moved every case, so **the two behaviours were indistinguishable**. `gen_render_reference.py` now compares digests against the previous manifest, derives `changed_from_previous` by measurement, and **writes SVG bodies only for those IDs**. A resolver (`_resolve_svg`) walks back to the last version where a case moved, with a test that **fails if the walk-back has nothing to resolve**.
- **Added "when the performable vocabulary grows" to the version-bump rule (author's ruling).** Adding a tool leaves every existing corpus case untouched, because no case uses the new word — **output does not move and CI does not fail**. Bumping only when results change would allow vocabulary to be added without a version, leaving "an engine 12 that can perform the word" beside "an engine 12 that cannot". **The meaning of a version number — same version, same result — then breaks on the input set rather than the output.** (SPEC §15.6.)
- **Explicitly not done.** Android was not brought forward (still engine `"11"`). The "computer" touch vocabulary was not started (only its design was ruled on). `cloudform` was not moved onto stroke synthesis (the finding is recorded, not fixed). Past engines are still not retained or selectable (§15.8 stands). No stored SVG was replaced. `render_wild` was not backfilled on existing history (NULL still distinguishes "before the column" from OFF).
- **SPEC.** A section on "unleashed" in §13.4; the extended bump condition and the `rh3` material note in §15.6; the engine 12 measurements (the 199/21 split) in §15.7.
- **Verification.** pytest **1066 passed / 30 skipped** (+7: the 6 goldens re-baselined for engine 12, plus the new walk-back test), cli 68 passed, ruff clean, `npm run check` **0 errors / 2 warnings** (217 files). The 6 re-baselined goldens were confirmed to fail as a set when `_swell` is perturbed by 1e-6 — the discriminating power was measured, not assumed. Running the corpus generator twice leaves no tracked diff.

---

### Android Phase 3d — following the built-in nature plugin expansion (android Build 148083, 2026-07-25)

**The Stage 1.5 expander port is complete at Phase 3d.** The Android expander now returns the same string as web/server for the same input, and **the only remaining lag is the drawing layer (still engine 11)**.

- **What was ported.** `NATURE_PLUGIN_RE` (`Nature.(風|うねり|無風|wind|undulation|stillness|calm)`) and tag extraction via `naturePluginTerms`, sentence removal via `dropNaturePluginSentences`, and the deterministic macro insertion of `applyNaturePluginMacros`, all into `WebDdlExpander.kt`. **The call order matches the server original** (`_sanitize_placement_words` → `_avoid_gray_background` → `_apply_nature_plugin_macros`).
- **Word mapping.** 風 / `wind` → horizontal strata, swaying slowly; うねり / `undulation` → an undulating trace, broad slow swaying; 無風 / `stillness` / `calm` → no variation, kept still. **`stillness` takes precedence and suppresses the wind and undulation macros** (the same branch as the server).
- **Verification.** `testDebugUnitTest --rerun-tasks`, aggregated from the XML by hand: **64 tests / 0 failures / 0 errors / 0 skipped** (62 baseline + 2 new). The three reference-corpus cases in `ddl_expand.json` (`A-plugin-enabled`, `A-plugin-disabled`, `B-plugin-instructions-present`) match exactly under `assertEquals`, and **those three expected values were re-computed against the current server implementation during acceptance and agreed**. The anti-tautology test (output changes when `enablePlugins=false`) passes as well.
- **Discriminating power, measured on acceptance.** Perturbing a single word of the undulation macro makes `WebDdlExpanderPhase3dTest` fail with `ComparisonFailure`. **What was confirmed is that it fails, not merely that it passes.**
- **A regression in the English `ANDROID_SPEC.md` was repaired during acceptance.** The implementation session had **overwritten the English document with the Japanese one** (identical content SHA; 1848 lines of English lost). After the merge the English body was restored and a Phase 3d section written in English. The "catch-up status" preamble in both versions was corrected to the present state (master at v2.5.0 / engine 12, Android at engine 11, expander through 3d).
- **Explicitly not done.** The drawing layer was not brought forward to engine 12 (`render_engine_version` stays `"11"`). The leaf plugin document `nature-leaves.inku-plugin.md` and the `saijiki.py` equivalent were not ported (out of scope by the author's ruling; 3e or later). `android/VERSION` stays `2.0.0-android.1`. No web/server/cli/shared code was changed.
- **Numbering.** Android-only change, so `APP_VERSION` and `web/BUILD_NUMBER` were not moved (`android/BUILD_NUMBER` 148082 → 148083 only, assigned by Gradle).
- **Verification on master (regression check).** pytest 1066 passed / 30 skipped, cli 68 passed, ruff clean, `npm run check` 0 errors / 2 warnings (217 files).

---

### v2.6.0 — a "computer" touch (render engine 13) (Build 707, 2026-07-25)

**An eleventh tool. Its core is not "the hand does not shake" but "it repeats without error".** A hand cannot produce the same value twice; a machine can produce nothing else. **A cycle repeats along the line, a lattice repeats across the plane** — two axes of one property. This is what separates it from `rotring`: **rotring has no wobble to repeat** (every term of its grammar is zero), while **the computer has wobble and repeats it exactly**. It is not a retreat to engine 11's symmetric envelope: that was a **default nobody could decline**, this is **vocabulary you choose** (SPEC §15.8 stands).

- **Performance (`stroke_engine.py`).** `ToolGrammar` gains `periodic` / `quantize` / `width_steps` (all zero, hence unchanged, for the existing ten tools). Under `periodic` the noise sources are replaced by whole-cycle sines (five and ten per stroke for energy, two for gesture — **none of them takes a seed**), centreline coordinates are rounded to a lattice of `stroke length x 0.018`, and width falls onto four steps. **The along-travel gesture is dropped** (a machine does not hesitate back and forth; leaving it in produced cusps that read as breakage). `wild` has no effect on a periodic tool.
- **The material is the remainder of sampling (`raster-bleed`).** A hand tool's material layer is **what the tool drops beside the stroke** (graphite dust, brush hair); a machine drops none of that. **What it has is the difference discarded when rounding to the lattice.** For each sample the distance between the position before and after rounding is the residual, and **only samples with a non-zero residual** get a one-cell square laid under the stroke, **placed on the lattice** and **toned in proportion to the residual** (capped at 0.45 where the rounding moved half a cell). **The geometry repeats without error; the material shows where the error went.** No seed is involved, so the same figure always bleeds the same way. **Endpoints are pinned to the intention and polygon corners are anchored**, so they carry no residual and emit no cell (39 cells from 41 samples on a line, 76 from 80 on a square, 60 from 62 on an arc).
- **The material was rebuilt after the author looked at the first version.** That version drew "a ruled line and one identical dash pattern on every stroke", restating the "rain of straight lines" of the older work `rh2:9e991c...` as a property of the tool. Rendered and looked at, the ruled layer stayed pinned to the intended start and end while **the performed centreline wanders up to 55.4px away** (a span of 102.8px), so the dashes detached and read as **background ruling**. The author's ruling — **"these dotted lines carry no pictorial meaning"** — discarded it. A second candidate (a "lattice halo": the quantized outline spread one or two cells outward and laid faintly) was prototyped and rejected too: the band's width scales with the lattice, so dense compositions fill in, and it appears **uniformly, regardless of how much the rounding moved** — the picture cannot say why it is there.
- **The numbers were chosen from rendered comparisons.** Nine panels of lattice coarseness (0.012 / 0.018 / 0.022) against tone (0.30 / 0.45 / 0.55), plus two panels for whether the cell **sits on the lattice** or **at the intended position**. The author chose **0.018 / 0.45 / on the lattice**. Cells at the intended position read as scattered dust; cells on the lattice read as a run of pixels along the steps.
- **Vocabulary and schema.** The saijiki entry (Japanese コンピュータ / English `computer`), the `Weight` literal, a 2.0px stroke width, and a dedicated preview with bilingual copy in the web saijiki. The Stage 2 tool table describes it as falling onto a grid and onto steps, and repeating without error.
- **Froze the `render-engine-13/` reference corpus (228 cases).** The only new bodies are the eight `A-computer-*` cases; **not one of the 220 existing digests moved** (byte-identical to engine 12). That is the proof sheet for "a block was added and the earlier prints did not change" — and equally the evidence that **bumping only when results change would let vocabulary be added without a version** (SPEC §15.6's "the performable vocabulary grows" clause, applied for the first time).
- **The generator's guard fired, correctly.** Regenerating after the material was rebuilt stopped with "a frozen corpus must not be rewritten at the same version". Since **engine 13 is unreleased and what had been frozen was the output of the rejected implementation**, the directory was deleted and re-frozen rather than bumped; the earlier freeze remains in the branch history.
- **Explicitly not done.** Android was not brought forward (still engine `"11"`; separate contract). No radius modulation was written for closed contours (the author's ruling: a machine circle looking almost like rotring's is correct). Scanlines, dithering and surface textures were not touched. `computer` was not added to `TEXTURE_SPECS` / `TEXTURE_FILTER_WEIGHTS` / `_SPECK_SPECS`. No performance value of the existing ten tools changed. Past engines are still not retained or selectable, and no history was backfilled.
- **Left unruled about the lattice.** It applies to **absolute coordinates** and its **step scales with stroke length** (`step = length x 0.018`), so the phase depends on where a stroke is placed: thirty equal lines at equal spacing produce **nine distinct figures**. Whether to move to a single canvas-wide grid is a separate ruling; the current behaviour stands.
- **SPEC.** New §15.9 in the Japanese SPEC (the tool's core, the lattice, the material as the remainder of sampling, and why the first version was discarded), with §4's vocabulary table, §15.6's version numbers and §15.7's corpus table updated; §12.6 in the English SPEC.
- **Verification.** pytest **1091 passed / 30 skipped** (+2 for the material), cli 68 passed, ruff clean, `npm run check` **0 errors / 2 warnings** (217 files). Regenerating the corpus leaves no diff. **Three perturbations measured the discriminating power**: changing the opacity coefficient from 0.45 to 0.44, removing the snap to the lattice, and removing the zero-residual exclusion each make a test fail. **The snap perturbation initially passed unnoticed** — an open stroke's samples are already on the lattice — so a closed-contour check was added, where the seam correction moves samples off it.

---

### Android `2.1.0-android.1` — the drawing layer follows render engine 12 (de-regularization, material outline, unleashed, `rh3`) (android Builds 148084–148089, 2026-07-25)

**Android's drawing layer has caught up from engine 11 to 12.** The Stage 1.5 expander had already caught up at Phase 3d, so **the only remaining lag is engine 13 (the computer touch)**.

- **4a, de-regularizing the performance.** `ToolGrammar` gains its tenth field `gesture`, alongside `WILD_GAIN = 3.5` / `GESTURE_EDGE = 0.16` and ports of `smoothNoiseSalted` / `edgeWindow` / `swell` / `gestureWave`. The envelope, the correction event (`correction-kick`) and the centreline gesture now match engine 12.
- **4b′, the material outline layer (remanded once).** The first attempt was **a lookalike, not a port**: comparing `points` gave **0 of 234 coordinates matching, up to 16.4px out**, and every `stroke-dasharray` differed. It passed as "11 SVGs, 100% PASS" because **the existing tests compare only path `d`, class strings and element counts, and never a single coordinate of this layer** — and **the contract had written its conditions in terms of those existing test names, which was the hole**. 4b′ fixed the doubled `scale` in `outlineOffsetPx`, the unsigned 64-bit seed stringification in `hash01`, and the `variedDashPattern` / `scaleDash` formats against the server original, and added **exact comparison of `points` and `stroke-dasharray`**.
- **4c, wiring "unleashed" and the version.** `render_wild` reaches `synthesizeStroke` for the `line` primitive only, never the contour, hatch or arc paths — **because that is what the server does**. `render_engine_version` moves to `"12"`. The discrimination is a pair: `15_line_brush_wild` must **differ** from `02_line_brush` while `16_circle_pen_wild` must be **byte-identical** to `01_circle_pen` (an implementation that wires `wild` into the contour path passes the first and fails the second).
- **4d, `rh3`, storage and UI.** The edition identity moves from `rh2` to `rh3` (seven-key canonical JSON including `render_wild`). Room moves to version 4 with `MIGRATION_3_4` and a `renderWild: Boolean?` column, and the UI gains the "unleashed" toggle (bilingual, default OFF). **The `rh2` path is gone.**
- **A separate defect found and fixed during acceptance (git session).** Widening the check from the four cases the contract named to **all 16 reference SVGs** surfaced `11_cloudform_pencil`, where the `stroke-dasharray` read **`1,3`** on Android against the server's **`1.000000,3.000000`**. The server passes both the style dash and the texture dash through `_scale_dash`; Android returned **the raw literal**. **On a square canvas the numbers coincide, so it stayed invisible; on a pillar or wide canvas only the server stretches them.** It dates from phase 2b′ (`c6e2c9e`) — **older than this contract**. Both dashes are now scaled, the `rope` texture the server removed in phase 1 is gone, and **a test comparing all 16 cases on path `d`, `points` and `stroke-dasharray` is now permanent** (a list of named cases leaves holes).
- **Verification.** `testDebugUnitTest --rerun-tasks`, aggregated from the XML by hand: **68 tests / 0 failures / 0 errors / 0 skipped** (64 at the start, 67 when 4b′ arrived). **Three perturbations were measured on the reviewing side**: 1e-6 on `swell` fails 8 tests, 1e-6 on the `outlineOffsetPx` floor fails 2, and removing the texture dash `scale` fails 1. All 14 reds present at the start are green, and **the reference corpus is unmodified byte for byte**.
- **Explicitly not done.** Engine 13 (the computer touch) was not ported. No `server` / `web` / `cli` / `shared` change. `wild` was not wired into contours, hatches or arcs (the server does not). `renderWild` was not backfilled on existing history.

---

### v2.6.1 — the English interface moves to the vocabulary of printmaking, music and tanka (Build 708, 2026-07-25)

**English display text only. Not one character of Japanese changed.** The English interface had been a literal translation; it now uses the established English terms of the three traditions inku stands on — **score and performance** (music), **block and impression** (printmaking), **headnote and Saijiki** (tanka and haiku). It is not thinned out for beginners, and it prefers the workshop's words (write, paint, perform) to the industry's (prompt, generate).

- **English display text lived in three channels.** The i18n pack `en.ts` (**641 entries**), inline `isJapanese ? '…' : '…'` ternaries in components (**132 sites across 12 files**), and `getLang() === 'ja'` branches (**15 sites**). **Fixing only the i18n pack would have left 147 sites on the old vocabulary**, so all three were inventoried before anything was touched (236 entries rewritten: 199 / 29 / 8).
- **The five refinement operations became symmetric.** `Vary Touch with Words` / `Vary Layout` / `Vary Reading` / `Vary Color Catalog` are now **`Another performance`** / **`Another composition`** / **`Another reading`** / **`Another catalog`**, with **`Variation`** for the expansion layer. The names alone now contrast what is redrawn against what is kept. Each tooltip says what happens in its first sentence and what is preserved in its second (e.g. `Another performance` → *Same interpretation, same composition — only the performance sways… Instant, no LLM call*). **The nouns are never abbreviated to fit a button** — the labels wrap instead.
- **Variation amplitudes moved to musical words.** `Small / Medium / Large` → **`Subtle / Moderate / Sweeping`**; music does not call a variation "large". **The layout refinement cost label lost its clashing `Moderate` for `Medium`** — the one place the pass reached outside the dictionary, to keep one word to one meaning.
- **One word, one meaning.** `interpretation` (Stage 1), `reading` (reading the words afresh), `performance`, `variation`, `sway` (the per-performance non-determinism), `color catalog`. **`palette` appears zero times** — the color catalog is an inku concept and is not renamed — and **`rendering` appears zero times in interface prose** (only in the server-side technical settings). Refinement candidates are `option`, never `variation`.
- **Cultural terms stay as a minimum of proper nouns.** Only **`Saijiki`** and **`inku`** remain romanized. `Okugaki` → **`Colophon`** (the term from bibliography and book arts), `Kotobagaki (caption)` → **`Headnote`** (the established translation in tanka scholarship); staffage was already in place. More romanization would drift toward exoticism and cost the tool its credibility.
- **The language of provenance.** `Generation Info` → **`Provenance`**. `Artwork` / `artwork` → **`Work`** (the art register; zero occurrences remain). `Unleashed` → **`Wild`** (matching `WILD_GAIN` in the implementation). The main action button `Generate` → **`Paint`** (matching `/api/paint`).
- **Microcopy rewritten sentence by sentence.** Progress now reads **`Interpreting your words…`** and **`Writing the score, then performing…`** instead of `DDL generation` / `JSON generation / SVG rendering`. The engine-mismatch notice reads **`This work was performed by engine N. What you see now is a new impression by engine M.`** A provider failure reads **`The interpreter did not answer in time, so a stock set of instructions was performed.`**
- **Style.** Sentence case throughout (the only Title Case left is the author's name). One-character `…` ellipses. Exclamation marks are gone (`Autonomous refinement completed successfully!` → `Autonomous refinement finished.`).
- **The Saijiki category names were left alone, on measurement.** The English category names are not web strings: they are `name_en` in `saijiki.py`, and **they flow through `prompt_block("en")` into the English Stage 1 prompt** (pinned by the golden fixture `stage1_prefix_en.golden.txt`). **That makes them part of the English DDL vocabulary, not the interface**, so the dictionary's suggestions (touches→touch, motions→gestures, …) were not applied and were reported to the author instead. The Saijiki words themselves (circle, fine brush, …) are likewise untouched.
- **Where the dictionary and the implementation disagreed, measurement won.** (1) The dictionary justified the five operation names as mirroring a Japanese "another ◯◯" form, but **the canonical Japanese is the verb form "change the ◯◯"**; on the author's ruling only the English became nominal, and the Japanese is unchanged. (2) The contract had classified `settingsGenerationLabel` as "generation, do not touch", but **the canonical Japanese is `'生成'` — the act, not the generation count** — so it became `Painting`.
- **That the Japanese did not move is guaranteed mechanically.** The md5 of `ja.ts`, of the Japanese side of all 132 ternaries, and of the Japanese side of the 14 `getLang()` branches — **all three match the pre-work values**. Without pinning the collation with `LC_ALL=C sort` the digest changes even when no content does (encountered while writing the contract).
- **Verification.** `npm run check` **0 errors / 2 warnings** (217 files; the warnings are the two pre-existing a11y ones). The i18n key set is **unchanged at 641** and identical between the two languages. Zero diff in `server`, `cli`, `android`, `saijiki.ts` and `saijiki.generated.ts`. **Four perturbations measured the discriminating power** — one character in `ja.ts`, one character on the Japanese side of a ternary, one injected `palette`, one deleted key — each fails its corresponding check.
- **Left undone (stated).** **The English documentation (README.md, SPEC.md, `manual/en/`) has not followed.** Only the interface carries the new vocabulary, so `artwork` (SPEC 25 / manual 26), `palette` (SPEC 12), `Okugaki` (SPEC 7), `Unleashed` (SPEC 7) and `Generation Info` (SPEC 3 / manual 5) are now stale there. **That is separate work.** The empty-history copy the dictionary proposes was not added, since no such key exists and the pass added none. The Saijiki category names (above) remain as they were.

---

### v2.7.0 — one sheet of graph paper, and the reach of wild (render engine 14) (Build 709, 2026-07-26)

**The two holes engine 13 left open are closed in one version.** Both change what is performed, and closing them together means the reference corpus is re-frozen once.

- **A lattice is a property of the paper, not of the object placed on it.** Engine 13's step was **proportional to stroke length** (`step = length x 0.018`), so **objects of different length got different steps** (100px → 1.8px, 400px → 7.2px, 800px → 14.4px), **the same length changed figure with position** (thirty equal lines placed apart produced thirty distinct figures), and one picture held **as many sheets of graph paper as it held sizes**. Engine 14 derives the step from **`canvas short side x quantize`**. The value is still `0.018`, but **its meaning moved from "a fraction of the stroke's length" to "a fraction of the canvas's short side"**. `stroke_engine` does not know about the canvas, so **the renderer converts to pixels and passes the step in**; **all four length-relative sites were deleted**, leaving no flag and no fallback. That is 18.000000px on a 1000px square and varies with aspect (3.600px on a pillar). **Every stroke in one picture now falls onto the same cells** — with three objects of different size in one Score, coordinates off the 18px lattice went from **188/194 to 0/194**. Because the paper no longer shrinks with the object, **consecutive samples can round into the same cell, and overlapping cells are drawn as they fall** (the author chose 18px with that appearance in view).
- **Wild now reaches the contours.** Engine 12's switch **reached only the `line` primitive**: **63 of the 88 combinations (11 tools x 8 primitives) were byte-identical with it on and off**, contradicting the "one switch for the whole work" description. Engine 14 adds the centreline gesture to `synthesize_along` (circles, ellipses, triangles, squares, polygons, arcs, fills and hatches) and threads `wild` through it. **With the switch off nothing changes, byte for byte** — of the 228 existing cases, the only seven that moved did so because of the lattice. **Exactly 25 combinations may still be identical**: `cloudform` across all 11 tools (it does not go through `stroke_engine`; a known hole this release does not fix), `rotring` x 7 (its `gesture` is zero), and `computer` x 7 (`periodic` skips `WILD_GAIN`).
- **Three ways a naive port breaks, all measured on a prototype before becoming specification.** (1) **Amplitude must not be scaled by arc length** — a closed contour's perimeter is not its size, and a heptagon turned into a star; **it is measured by `perimeter / tau`, its radius equivalent**. (2) **The gesture's mean must be removed** — a non-zero mean rescaled the whole figure (a circle shrank). **Size is decided by the score; a performance may not change it.** (3) **The window must fall to zero before an anchor**, or a gesture riding the vertices next to a pinned corner produces spikes.
- **The material now follows the ink — the easiest thing to miss here.** The material outline of a contour or an arc was **built from the geometry and never looked at the performed centreline**. With wild reaching contours, **all nine measured combinations moved the ink alone and left the material behind** — the same defect engine 12 fixed for lines, where a material layer that does not follow the centreline reads as ruling behind the drawing. **It is built from the performed centreline only when wild is on**; with it off the layer is exactly as engine 13 left it.
- **The `render-engine-14/` corpus is frozen at 347 cases.** `corpus_format_version` moves `"1"` → `"2"` (each case's input now carries `wild`). `changed_from_previous` holds **126**: **7 existing cases** (the `A-computer-*` set minus `cloudform`) and **119 new E-block cases** (the full 88 under wild, plus 15 fills and 16 surfaces), leaving **221 unchanged**. **Not one of the ten hand tools moved**, and `A-computer-cloudform` did not either.
- **The expected values were measured and handed over before the work started** (by the git session, on a temporary patch): the seven-row cell table with the first five cells' coordinates and opacities, the seven existing cases that move, the 25 combinations allowed to stay identical, and the nine combinations where the material detaches. **The implementation reproduced every one of them to the digit, and so did an independent re-measurement during acceptance.**
- **What the perturbations revealed: one check was a step short.** Reverting to length-relative *inside `synthesize_stroke` only* **failed to trip two of the lattice checks**. `_add_raster_bleed` **re-snaps** each cell onto the step it is handed, so the alignment and uniform cell size are preserved by the renderer even when the step disagrees internally. Reverting `synthesize_along` and the returned `grid_step` as well brings all four down. **When one property is enforced in two places, a perturbation on one side is absorbed downstream.**
- **Acceptance ran its own perturbations too**: the step at 0.017 (four checks fail), and the material outline reverted to geometry **applied separately to the arc path and to the closed-contour paths** — **each alone trips the check** (with four enforcement sites, a one-sided perturbation cannot show whether the check has a hole).
- **SPEC**: §15.10 added in Japanese (§12.7 in English), with the reach note in §13.4, the lattice description in §15.9, and the version and corpus tables in §15.6 / §15.7 updated. **The English "Unleashed" was aligned to the interface's "Wild"** — part of the divergence v2.6.1 created; README and `manual/en/` still carry the old terms.
- **Verification.** pytest **1100 passed / 30 skipped** (+9: three in `test_one_lattice.py`, five in `test_wild_reach.py`, one corpus test), cli 68 passed, ruff clean, `npm run check` 0 errors / 2 warnings (217 files). Two consecutive corpus generations produce no diff. **Android's suite was not run, since `android/` has no diff.**
- **Left undone (stated).** Putting `cloudform` through `stroke_engine`, the dead fields (`absorbency`, `contact`, `thickness`), the `thickness` / `angle` / `rotation` / `length` dimensions from §17.A, any mechanism for keeping past engines, backfilling existing history, and anything reaching `gen_android_reference.py`. **Android stays on engine 12, so it is now two versions behind.**

---

### v2.7.1 — the canonical English glossary, and a lint that enforces it (Build 710, 2026-07-26)

**v2.6.1 aligned the English interface but left nothing to keep it aligned.** One new string is enough to bring a forbidden word back or give a concept a second English term. **The rules now sit beside the strings they govern, with a lint that checks them mechanically.**

- **`web/src/lib/i18n/GLOSSARY.md` (200 lines) is the canonical rule text.** It records that English display text lives in three channels (`en.ts` 641, ternaries 132, `getLang()` branches 15), the core vocabulary mapping, the fixed names of the five refinement operations and the variation amplitudes, the style rules, the forbidden words **with their allowed exceptions**, the paths that must not be touched (`surface_en` / `name_en` in `saijiki.py`, `saijiki.ts`, `ja.ts`, the Japanese side of every ternary), the procedure for adding a new string, what the checks actually look at, and the divergences still outstanding. Its sources are Fable's translation dictionary and the author's rulings of 2026-07-25.
- **`web/scripts/i18n-lint.mjs` (221 lines) enforces it.** `npm run lint:i18n` **scans all 788 English display strings and passes 36 named exceptions**; `--list` prints what it let through.
- **The rule text and the lint are one pair**: the glossary states that changing either means changing the other in the same commit.
- **"Zero occurrences" is deliberately not the condition.** `generation` (a lineage generation), `prompt` (displaying an actual LLM prompt), `created` (completion and timestamps), `image` (what Vision genuinely looks at) and `render` (server-side technical settings) all have legitimate uses, so the rules separate **words that may appear nowhere** from **words allowed only in named places**.
- **Its discriminating power was measured during acceptance.** Changing `colorCatalogTitle` to `Color palette` produces `ERROR en.ts colorCatalogTitle: "palette" — use "color catalog" — palette is a different concept in inku`, and reverting returns it to zero errors.
- One `en.ts` entry was corrected to sentence case along the way (`Instructions (Normalized DDL)` → `Instructions (normalized DDL)`) — **a miss the lint found.**
- **Verification.** `npm run check` 0 errors / 2 warnings (217 files), `npm run lint:i18n` **788 strings / 36 exceptions / 0 errors**, pytest 1100 passed / 30 skipped, cli 68 passed, ruff clean. **Android's suite was not run, since `android/` has no diff.**
- **Left undone (stated).** The English documentation (`README.md`, `manual/en/`, the rest of `SPEC.md`) has not been brought into line. **The lint watches only the display strings under `web/`; it does not read documentation.**

---

### The English documentation follows the interface vocabulary (no version, 2026-07-26)

**When v2.6.1 moved the English interface onto the terminology dictionary, the English documentation stayed behind.** Only the interface carried the new vocabulary, while `README.md`, `SPEC.md` and `manual/en/` still said `artwork`, `Generation Info` and `Vary Touch with Words`. They now follow. **No Japanese canonical document and no code was touched.**

- `artwork` → `work` (the art register), `Generation info` → `Provenance`, `Okugaki` → `Colophon`, `Kotobagaki` → `Headnote`, the five refinement operations by their ruled names (`Another performance`, `Another composition`, `Another reading`, `Another catalog`), and the variation amplitudes as `subtle / moderate / sweeping`.
- **The English UI casing rule now points at `web/src/lib/i18n/GLOSSARY.md` instead of being restated.** SPEC.md said short English labels use Title Case, which the interface had left behind in v2.6.1. **One rule does not get two homes.**
- **Deliberately left alone:** (1) **text quoted verbatim from the CLI** — `inku-cli` still prints `Artwork Lineage:`, so a manual that says otherwise is simply wrong; (2) CLI subcommand and flag names (`okugaki`, `refine generate`, `--kind layout`); (3) **JSON and API field names** (`palette`, `resolved_palette`, `palette:<name>`); (4) the romanized glosses beside `Headnote` and `Colophon`; (5) **the revision-history line recording that an older build unified Title Case**, which remains true of that build.
- **`palette` was first counted as 12 stale occurrences; classified, it was zero.** The Japanese canonical uses パレット in the same places, and the rest are color-catalog API fields. **What the dictionary forbids is `palette` meaning the color catalog, not the ordinary noun.** Treating a raw grep count as the work item would have deleted correct usage.
- **Five sentences broken by the mechanical substitution were repaired** (`not an work governor`, `by an work-page boundary`, and similar, where `artwork` → `work` damaged an article or a compound). **A bulk replacement always needs a pass afterwards.**
- **The lint does not watch this.** `npm run lint:i18n` scans only the display strings under `web/`; documentation is out of its reach, so nothing mechanical stops it drifting again.
- **No version was assigned** (documentation only — the first application of the numbering rule below).

### The version numbering rule is tightened (author's ruling, 2026-07-26)

**"Version numbers are climbing too fast. Use +0.0.1 increments more."** A ruling to the same effect had already been given on 2026-07-21, but **a render engine bump kept being treated as grounds for a minor**, and v2.5.0 (engine 12) → v2.6.0 (engine 13) → v2.7.0 (engine 14) moved the minor digit three times in five days. **The engine version is a performance-compatibility counter, not the granularity of a user-facing version.**

- **A patch bump (+0.0.1) is the default**: feature work, UI and terminology changes, bug fixes, added tests or reference corpora, **and a render engine version bump**.
- **A minor bump is reserved for three cases**: a milestone the author names, an external release that gets a tag, and a compatibility break (saved data, API, or edition-identity format).
- **Documentation-only changes take no version at all**, and are recorded under a dated heading with no version number, as the Android entries are.
- `web/BUILD_NUMBER` is a separate counter and still moves with every deployed change.
- **When in doubt, take the patch. Numbers already published are never renumbered** (v2.5.0, v2.6.0 and v2.7.0 stand).

---

### v2.7.2 — retiring two fields nothing reads (Build 711, 2026-07-26)

**`contact` and `thickness` were declared in the schema and read nowhere.** `contact` carried no information at all: a touching relation was required to set it to `both_ends`, and every other relation was forbidden from setting it, so only one value could ever be written.

- **`Relation.contact` and the `thickness` dimension are gone**, along with the `RelationContact` type. The SPEC §17.A row that listed `thickness` as unimplemented goes with them — it recorded a declaration that was never going to be built.
- **Saved work still replays.** 41 of the 1780 scores on pentala carry `contact`, and `extra="forbid"` would reject them, so each model now **drops the retired key before validation**. **Unknown fields are still refused.**
- **The producers stopped emitting it** — both Stage 2 prompts and their examples, the relation repair path, and the pair-splitting plugin. The reference dump loses the `contact` enum.
- **`absorbency` was not retired.** Its value is indeed never read, but the ground texture seed is a hash of the whole Score (`_texture_seed`), so removing the field re-rolls the grain of any work that has a ground. **18 of the 23 such works changed**, so the change was withdrawn and the reason written into the field description. **It will be retired as a deliberate change the next time the engine version moves.**
- **Output neutrality was measured against real data.** 312 saved scores (all 62 carrying `contact` or `absorbency`, plus 250 at random) were rendered under both the old and new code: **zero changed**. Across the 639 scores carrying a relation: **zero changed**. **The engine version did not move.**
- **Verification.** pytest **1101 passed / 30 skipped** (one added compatibility test), cli 68 passed, ruff clean. **Neither `web/` nor `android/` has a diff, so `npm run check` and the Android suite were not run.**

---

### Android `2.1.1-android.1` — the drawing layer follows render engine 14 (the computer, one lattice, wild reaching every contour, and the touch vocabulary) (android Build 148090, 2026-07-26)

**Two engine versions, 13 and 14, were caught up under one contract.** Android now reports the same render engine 14 as the server.

- **5a machine terms and the lattice.** `ToolGrammar` gains `periodic`, `quantize` and `width_steps` across all 11 tools; `grid_point`, `machine_energy`, `machine_swell` and `machine_gesture` are ported, and `StrokeSample` carries `residual`. **A periodic grammar ignores `wild`.**
- **5b the renderer's grid and raster bleed.** The pitch is **the canvas short side × `quantize`** (18.0px on a square canvas). `<rect class="raster-bleed">` cells at `RASTER_BLEED_OPACITY = 0.45` sit under the stroke, and every call site — line, contour, arc, hatch — receives the grid step.
- **5c wild reaches the contours, and the version moves.** `wild` is wired into contours, fills, arcs and hatches, **but not cloudform**. `render_engine_version` goes from `"12"` to **`"14"`** in both the renderer and the fallback pipeline.
- **5d the touch vocabulary is corrected.** The displayed words become **exactly the ten** the server's `saijiki.py` publishes: the computer, the burin and the drypoint join; hair and rope leave. **`hair` is still accepted as a Score value** so saved work replays. The four `rh3` values are pinned to their engine 14 measurements.
- **Found and fixed during acceptance (git session).** Rope was gone from the words but still in the drawing tables — `ropeTwists` (never called), the style table and the width table. The check that shipped with 5d read only the prompt text, so the tables passed it. All three are deleted, and the check now reads the tables too.
- **Verification.** `testDebugUnitTest --rerun-tasks`, counted from the XML: **71 tests, 0 failures, 0 errors, 0 skipped** (68 at the start). **Three discriminating perturbations were measured on the accepting side**: scaling the lattice pitch by 1.000001 fails two tests, removing the periodic grammar's `wild` exemption fails four, and restoring the rope branch fails the vocabulary test.
- **Left undone (stated).** `server`, `web`, `cli`, `shared` and the reference corpus are unchanged. Stage 1.5 from 3e onward and the vocabulary of the other saijiki categories remain out of scope.

---

### The frozen DDL corpus drops the retired field from its recorded input (no version, 2026-07-26)

**The v2.7.2 retirement left its difference not in the drawn output but in the input the corpus records.** The `ddl-engine` job of `reference-corpus` had been red for three runs since `9c70e8f`, with the generator's guard (`DDL corpus changed without an identity-field change`) firing exactly as designed.

- **The only thing that moved was the `contact` key in the recorded input of one case, `B-invalid-touching`.** All 29 outputs were byte-identical.
- **Because no output moved, the record was corrected rather than a new version frozen** (author's ruling, 2026-07-26). That is an exception to "never rewrite a frozen corpus", so the fact of the rewrite is recorded here.
- Freezing a `ddl-engine-2` was rejected: it would create a version whose output is identical to its predecessor, which drains the meaning of a version.
- **A missed check, recorded.** v2.7.2 ran pytest and ruff after the schema change but never ran the corpus generators themselves. pytest reads the corpus output; the freeze guard only fires when the generator runs. **Touch the schema, run the generators.**
- **Verification.** `gen_ddl_reference.py` and `gen_render_reference.py` both exit 0 and leave no diff on a second run. pytest 1101 passed / 30 skipped.

---

### v2.7.3 — the CLI's English joins the terminology dictionary (Build 712, 2026-07-26)

**The fourth channel of English display text is the CLI.** v2.6.1 and v2.7.1 brought `web/` onto the dictionary and pinned it with a lint, but **`npm run lint:i18n` reads only the display strings under `web/`**, so the CLI was never covered.

- **The forbidden word `artwork` survived in three places and is now `work`** (§2 of the glossary: 作品 = **work**). `Artwork Lineage:` becomes **`Work lineage:`** in sentence case, `show or control artwork lineage` becomes `show or control the lineage of a work`, and the PNG fallback warning follows.
- **The manual quotes the CLI's actual output, so both languages were updated in the same commit** (`manual/{ja,en}/cli-reference-for-ai.md`).
- **The six `palette` hits are out of scope**: they are server API **field names** (`catalog.get("palette")`), not display text. **A raw grep count is not a measure of work.**
- **Left undone, and stated.** The subcommand `okugaki` is `colophon` in the dictionary, but **a command name is an identifier, and renaming it breaks the reader's own scripts**; it stands. `README.md`, `SPEC.md` and `manual/en/` still carry the older vocabulary.
- **Verification.** cli 68 passed, ruff clean, and the new wording confirmed in the real `inku-cli --help` output. server 1101 passed / 30 skipped.

---

### A golden gate for coerce (no version, 2026-07-26)

**Not one of coerce's thirty-four branches was protected by a frozen corpus.** The contract for splitting it into `normalize` and `compose` rested on "the 347 cases of `render-engine-14` must not go red", but **that corpus never calls coerce**: `gen_render_reference.py` does not import `coerce_score`, and says so in its docstring ("no ... coerce path supplies fixture values"). The one corpus that does call it, the fourteen B cases of `ddl-engine-1`, fires ten of the thirty-four branches.

- **All thirty-four branches were measured against all four suites**, by replacing each branch with the identity function and counting which suites turned red. The 376 frozen corpus cases stayed **green for every branch**. `test_api.py` and `test_composer.py` caught one. `test_coerce.py` (125 tests) caught thirty-one, leaving **`_dedupe_instructions`, `_with_presence_auxiliary_shape_repair` and `_with_total_density_budget` with no guard at all**.
- **A golden set of thirty-nine cases was added**: twenty-one saved works, chosen from the pentala `history` for branch coverage, and eighteen synthetic inputs built for what real works never reach. It pins the whole coerced Score, the instruction count, and **the per-branch fire report** — so a failure names the branch that moved.
- **Every one of the thirty-four branches changes at least one case when disabled** (seventeen at most, one at least). No branch is beyond the gate's reach.
- **The plain dedupe needed a case where it decides something.** Disabling it moved none of the first thirty-eight outputs, because **the later `_with_structural_duplicate_repair` keys on the same payload minus `color_hint`** — strictly coarser, so it collapses every row the earlier one would have. A perturbation on one of two places that enforce the same property is absorbed downstream. Ten identical rows in front of a motif request breaks the tie, since the motif repair adds nothing once the score would exceed ten rows.
- **"Swap any two calls and it goes red" does not hold.** Swapping `dedupe_instructions` with `with_ddl_coverage` left all three gates green. **Unless both branches fire on the same case, the swap changes nothing.**
- **Three numbers in the design plan were corrected.** There are **thirty-four** recorded branches, not thirty-two: `_with_background_dominance_governor` and `_presence_from_ddl` return a value rather than an instruction list and had been missed. The split is six for normalize and **twenty-eight** for compose. "There is no way to measure the fire rates" was also wrong — `_record_branch_fire` counts element-wise dict inequality, so a branch that only rewrites is still seen. The real gap was a single line in `cli.py`, where `_compose_response_as_paint_result` carries none of the `coerce_*` fields out of the `/api/compose` response.
- **No version was taken.** Not one line of running code changed, so there is nothing to deploy. This gate takes its number alongside the coerce split it exists to guard.
- **Verification.** server **1143 passed / 30 skipped** (1101 / 30 before), ruff clean.

---

### v2.7.4 — coerce becomes `normalize` and `compose` (Build 713, 2026-07-26)

**The place that decides the composition now has a name. Not one pixel of the drawing moved.** In `coerce.py` (4,212 lines), the mechanical repairs that make a Score renderable and the reading of the description that writes the composition ran mixed along **one line of thirty-four branches**. This is where composition is actually decided — neither Stage 2 nor the renderer; in sixty production works, 27% of the instructions were written by coerce rather than by the DDL — and yet the boundary between the two responsibilities had no name.

- **The dividing line is "does it take `ddl`?"** — a criterion a machine can check, chosen over a judgement call. `normalize` sees only the Score; anything that reads `ddl` is interpreting the input and belongs to `compose`.
- Measured, that is **six branches for normalize and twenty-eight for compose**. The only shared pieces are four functions (`_closed_shape_area`, `_cluster_count`, `_expanded_count`, `_shape_extent`) and one constant (`VISIBLE_ON_BACKGROUND`); none reads `ddl`, so they live in `normalize.py` and `compose.py` imports them one way. **No third module was needed.** The result is 34 functions and 7 constants in normalize, 123 and 55 in compose, and `coerce_score` alone in `__init__`.
- **Not one call in `coerce_score` moved.** The two kinds alternate — `dedupe` is fourth, the density budgets twenty-ninth and thirtieth, `drop_invalid_relations` thirty-third — so **gathering them would reorder the pipeline and change the result**. This is a split of modules, not a tidying of the pipeline. On acceptance the 39 recorded calls before and after were compared mechanically: the order matches, and so do all sixteen conditional lines.
- The one function that held both responsibilities, `_coerce_and_repair_instruction`, was opened into three (`_coerce_instruction` and `_repair_coerced_instruction` in normalize, `_with_ddl_instruction_hints` in compose), **preserving the original order of application exactly**.
- **Proof of identity.** The 39 golden cases come out **byte-identical**. Disabling each of the thirty-four branches in turn moves exactly the same number of cases as it did before the split — **not one case different** (seventeen at most, one at least, none at zero).
- **A dropped diagnostic in the CLI was fixed too.** `_compose_response_as_paint_result` carried none of the `coerce_*` fields out of the `/api/compose` response, so `coerce_branch_counts` came back empty for every `--input-mode ddl` batch. Verified against pentala: **0 keys to 34**.
- **Left undone, deliberately.** No Topology. The 94 coordinate literals moved neither in value nor in place (they now sit in `compose.py`). Not one branch was deleted: **all thirty-four fire across the 39 cases, so no dead branch has been found.**
- **Verification.** server **1147 passed / 30 skipped** (1143 / 30 before; C-1 through C-4 added four), ruff clean, cli **69 passed** (+1), `npm run check` 0 errors / 2 warnings / 217 files.

---

### v2.7.5 — an explicit count below 240 stays literal (Build 714, 2026-07-27)

**Ask for two hundred thirty-three strokes and two were drawn.** Stage 2 dropped 24% of the counts the description stated, and the density budget accounted for only 4% of that. The rest came from the prompt contradicting itself. **The contradictions were removed. The acceptance thresholds were not met, and the measurement now says why: the cause is not Stage 2 but coerce.**

- **There were three contradictions.** (1) "when a tiny scatter exceeds 120 items, use the representation tools (density, cluster_count, fade, preserve_space)" and "represent quantities of 300 or more" **compete across the 120–299 band as the model sees it** — the band whose 20% adherence was the worst of all. (2) "two or more identical shapes: multiple instructions are absolutely forbidden" **also folded groups of differing counts into one**. (3) **Four worked examples answered a requested 137 with `"count":96`.** An example outweighs a rule.
- **The threshold is 240**, matching `MAX_EXPANDED_PER_INSTRUCTION = 240`. Placing it at 300 would make 241–299 a band that **is defined as literal and yet cut at 240 by coerce** — unkeepable by construction. **Two hundred thirty-three strokes are now two hundred thirty-three.**
- **The prohibition was narrowed** to "expanding a repetition of the same shape in the same placement into N instructions," in all four places that carry it (the Japanese and English system prompts in `composer.py`, the `count` and `arrangement` descriptions in `schema.py`, and the empty-drawing retry in `api.py`). **Fixing one place alone leaves the paths disagreeing.** The two examples that broke the rule were brought into line at the same time.
- **At the layer the prompts govern, it moved.** Measured on the Stage 2 output before coerce, the worst band, **120–239, goes from 33% to 55% in Japanese and 37% to 92% in English**; 300+ goes from 55% to 88% and from 88% to 100%.
- **The final Score did not follow.** Of the six acceptance bands, only 2–11 holding at 100% was met. **Feeding a fully compliant Score through coerce leaves 20 of 25 single-group bench lines intact in Japanese and 11 of 25 in English** — `_with_context_density_governor` rewrites the rest to 64, 48, or 16. **The 90–95% thresholds were unreachable without touching the coerce and compose code the contract put out of scope.**
- **The language gap lives in the same layer.** The quiet-density marker fires on 36 of 87 Japanese descriptions and **72 of 87 English ones**; the vertical-density marker, 15 against 48. The "within 10 points" condition is likewise out of reach from the prompt alone.
- **One line was removed on acceptance.** Both prompts told the model to record the representation and the original requested value in diagnostic metadata, but **Score has no `metadata` field and every model forbids extra keys** — a compliant response would have failed validation. Its absence is now pinned by a test.
- **A note on the measurement**: 13 of the 174 stage-5 samples are **not Stage 2 responses but the deterministic fallback** (10 after an empty-instructions retry, 3 after a hard timeout). Excluding them moves the band rates by a few points at most. The benchmark isolates Stage 2 through `--input-mode ddl` and is **not the production adherence rate** (production goes through Stage 1, supplies `original_text`, and may apply `tenkei`).
- **Left undone, deliberately.** No count-correction branch was added under `coerce/`; no deterministic enforcement was added on the compose side; the language asymmetry in the density governor's markers was not touched. **The next contract takes these.**
- **Verification.** server **1147 passed / 30 skipped**, cli **69 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files. The engine version, the reference corpora, and the golden set were not touched.

---

### v2.7.6 — a stated count outranks a later reading of it (Build 715, 2026-07-27)

**This version explains why v2.7.5 fixed the prompt and the final Score did not follow.** `_with_context_density_governor` read the scene — still, membranous, remembered — and thinned every repetition it found, including the groups written to order.

- **Quiet is a reading of the scene; "two hundred thirty-three" is not a reading.** A group whose count the description states outright now passes the three count caps (vertical 48, large-shape 16, visual 64) untouched. **The shape temperings still apply** — they touch size, not how many. The test is whether the count appears in the DDL, literally or as the 80–120 stand-in for a request of 240 or more.
- **The fifty frozen cases go from 31 to 50, and from 20/25 Japanese against 11/25 English to 25/25 in both.** This gate **calls no LLM and runs in two seconds** (`server/scripts/measure_count_preservation.py`).
- **The language gap was the English marker `"one "`**: it matched `one hundred twenty short black pencil lines`, so **asking for a count in English tripped the branch that cuts it**. Removing it is right but **saves nothing on its own** — four of the five sentences also match `thin`, `trace`, `pale`, or `blur`. Attribution: **0 cases to the marker fix, 19 to the exemption.**
- **The total density budget stopped shrinking in proportion.** Over budget, it gave each group its share, so **twelve squares a reader could have counted were thinned to pay for two hundred dots nobody can count**. Now the largest group is represented, the budget is rechecked, and only then does the next give way; if representing them all is still not enough, the large groups share one ceiling instead of collapsing to a single mark each.
- **It also stopped inflating.** The old pass assigned each group its share whether or not that exceeded the count asked for: **a requested 120 was raised to 232, a 150 to 173.** The golden case `S-total-density` is exactly that, and is **the only one of the 39 refrozen** — synthetic, not a saved work.
- **A defect in the gate itself was fixed.** The nineteen pins added in the previous version called `pytest.xfail()` imperatively, which marks a test xfailed whatever the outcome — **the gate could not have gone red once the counts started surviving**. They are assertions now, alongside cases proving that counts the description never mentions (137, 200, 300) are still thinned, so the exemption cannot pass as a disabled branch.
- **Perturbation.** Forcing the exemption to False returns **31/50 (ja 20, en 11), matching the measurement taken before the work**. Emptying the extracted DDL counts gives the same. Restoring the old budget pass fails all three new tests.
- **No production-scale benchmark was run** (author's call). Every deterministic gate is green, and the remaining unknown — how often Stage 2 emits a compliant count — was measured in v2.7.5 (78–100% Japanese, 67–100% English, before coerce).
- **Left undone.** A represented count does not always land in 80–120 (180 becomes 75, existing `_clustered_visual_count` behavior). **The prompt and the specification both say 80–120, and the deterministic layer does not follow them.**
- **Verification.** server **1207 passed / 30 skipped** (1181 / 30 / 19 xfailed before), cli **69 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files. The reference corpora `render-engine-14` and `ddl-engine-1` are green and **were not regenerated**. The engine version is unchanged.

---

### v2.7.7 — a represented count stays inside the band the documentation names (Build 716, 2026-07-27)

**The prompt and the specification both say a request of 240 or more is shown as 80–120 marks. The floor was 48.**

- Only one path showed it. Representation at 240 and above already landed between 100 and 120 (`_clustered_visual_count(240)=100`); the band was missed for groups of 121–239, and under the v2.7.6 rule those are literal — they are represented only when the total budget knocks one down. That is where **180 became 75**.
- The floor is now 80, and **`MIN_VISUAL_CLUSTERED_COUNT` and `MAX_VISUAL_CLUSTERED_COUNT` are written as a pair**. The band is one rule; only one end having a name is part of why the discrepancy went unseen.
- `[180, 150, 130]` now gives **`[80, 150, 130]`** rather than `[75, 150, 130]`, totalling 360, within budget.
- **A discriminating test** pins the band at ten points from 121 to 2000. Restoring the floor of 48 fails it for 121–239.
- **None of the 39 golden cases moves** (`S-total-density` represents 200 as 84, already above the floor).
- **Verification.** server **1217 passed / 30 skipped**, cli **69 passed**, ruff clean. Count preservation stays at **50/50**.

---

### v2.7.8 — remaking the seed and the trace (render engine 15) (Build 717, 2026-07-27)

**Five changes to `renderer.py` land as one version.** They sit in the same layer, and bumping four times would have cost four Android follow-ups.

- **A mark's seed is built from an allowlist.** `_seed_for_instruction` hashed **the instruction's whole dump**, so rewriting a colour note `coerce` had written was enough to change the drawing, and an A/B on a composition flag was confounded by it. Only what makes a mark physically another mark goes in now: what it is, the tool, the geometry, its variation, its surface, and `arrangement.jitter`. Across all 49 fields, **30 move the output and 19 do not**.
- **The ground's seed names the paper.** `_texture_seed` hashed the whole Score, so **touching anything at all dealt a new sheet**. Made of `material`, `grain` and the performance seed, raising the opacity now **darkens the same sheet**. That freed **`ground.absorbency`** — a field nothing had ever read, which could not be retired because removing it moved the grain.
- **`cloudform` joins the road every other closed contour takes.** It claimed `stroke-engine-touch` in its class while **never entering `stroke_engine`**, and all three material mechanisms were absent from it. **No cloudform-specific synthesis was written**: the dense polyline the inner fill already builds goes straight into the hand-stroke path.
- **The corner shapes and `pen` gain the material layer they never had.** `_render_corner_shape` had **no material-outline call at all**, so `triangle` and `polygon` were bare for every tool that owns one, and **`pen`, the most used tool in production**, had nothing but its body stroke.
- **Strength stops being distance.** Each rung of the intensity ladder had answered "the layer reads weak" by multiplying the outline offset, up to **2.8x with a 3.5px floor**. Measured against the band's own half-width as drawn, the strata sat **4.5x out for `pencil` and 6.5x for `chalk`** — far enough to read as a second contour rather than a trace. The multiplier and floor are gone; **the specification table was never at fault** (its values are 0.7 to 2.3 times the half-width), and the opacity gain is untouched.
- **The corpus holds 350 cases** (four added, one dropped). **318 moved, and the 32 that did not are the point**: `computer` and `rotring` across the seven shapes that are not `cloudform`, plus four `D-canvas` rotring cases. Neither machine pole consumes the performance seed, so both **move on `cloudform` alone** — the one path they newly share.
- **The four new cases are the first in the corpus's history to leave `ground.seed` unset.** Every ground case had pinned it, so **`_texture_seed` was called zero times across all 347 cases** and the layer this version rewrote could not be tested by the corpus at all.
- **`hair` was given the material layer and then had it removed** (the author ruled that retiring `hair` altogether is the right call). Adding a layer to a tool being retired only means deleting it again, so stage 4b covers `pen` alone. **The retirement itself is a separate contract.**
- **A limit of scope.** "Changing the count preserves the stroke" holds only for `layout="scatter"`. With `horizontal`, `vertical`, `radial` or `grid`, going from 12 to 13 moves the first twelve too — not a leak in the seed, but the arithmetic of **a layout that divides a span by the count**.
- **Verification.** server **1402 passed / 30 skipped** (1268 passed / 6 failed / 30 skipped at the start), cli **69 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files. **The generator was run twice and the frozen output is byte-identical**, so the CI guard passes.

---

### v2.7.9 — the silverpoint (Build 718, 2026-07-27)

**`hair` was never a brush.** 0.5px, stiffness 0.93, energy_width 0.08 — the thinnest and least wavering line among the hand tools, which is the physics of a **silverpoint**. Engine 15 had been told the tool would be retired outright, but **retiring it means folding it into `pencil`, which is three times as wide**, so the author's ruling changed to a **rename** (2026-07-27).

- **The rename moves the picture.** `weight` is part of the material of the performance seed, so changing the tool's name makes the same Score a different performance. **`A-hair-line` against `A-silverpoint-line` is 2299 → 2306 bytes, with 120 of its 126 coordinates moved.** The author looked at two comparison sheets and ruled that this is worth paying.
- **Only the sixteen cases that carry the name moved.** `A-silverpoint-*` (8) and `E-wild-silverpoint-*` (8) were swapped in; of the corpus's 350 cases, **the 334 in common have byte-identical manifest entries and all 302 shared SVG bodies are byte-identical**. Ten of the 39 coerce goldens were retaken, and **replacing `hair` with `silverpoint` in the old expected reproduces the new expected exactly**.
- **Stored works are rewritten as they load.** A `field_validator(mode="before")` on `Instruction.weight` turns `hair` into `silverpoint`. **All 445 works in pentala's production database that carry `hair` were pulled and replayed: 444 were accepted, carrying 581 `silverpoint` instructions.** The one rejection holds `rope`, a value that has never been in the `Weight` enum, and **was unreplayable before the rename**.
- **Not one value in `GRAMMARS` or the width table changed.** The three changed lines in `stroke_engine.py` and `renderer.py` are identical to their predecessors in every character but the key. **A new check pins the eight grammar values and the three machine-pole attributes directly** (`test_silverpoint_rename.py`), together with the ordering claim: least wavering, least swelling, thinner than `rotring`.
- **One behavioural change, and only one.** The saijiki entry left `_PRUNED`, so **the silverpoint is back in the vocabulary**: touches go from ten words to eleven, and **the material marker's first word changes from `鉛筆` to `銀筆`**. It now appears in the Stage 1 prompt, so the first stage can name it — which is a precondition for measuring **H1, whether the silverpoint actually gets chosen**.
- **Sixteen pinned prompt digests were retaken**: Stage 1 base and actual in both languages, Stage 2's `SYSTEM_PROMPT` in both languages and its tool schema, `_stage2_prompt_digest` in both languages, and three discriminating values. **The Stage 1 golden fixtures were not replaced** — the allowance in `test_saijiki_golden.py` merely moved from "pruned" to "renamed", and **the fixtures are still the Build 591 originals**.
- **The engine version was not bumped.** `render_engines/default.py` still reads `"15"`. **The generator's identity guard fired once, on the first run that performed the swap**: it judges by "the `cases` moved while no identity field did", so **it cannot tell a rename that declines to bump from an unsanctioned rewrite of a frozen corpus**. Every run after it exits 0 byte-identical.
- **Left untouched**: the few-shot search keyword `"髪"` in `interpreter.py` (a key for retrieving what the *author* writes, not output vocabulary — but **since 銀筆 was not added, the word that just returned to the vocabulary does not retrieve that thin-line example**); `material_weight_hints` in `language_support/ja.py` and `en.py` (no silverpoint row, and no `hair` row before it either — not a regression, but **there is no rescue path when Stage 2 drops the weight**); `brush_fine` and the axis of thickness; Android (the two lines in `gen_android_reference.py` were renamed but **the generator was not run**, so the Kotlin implementation still says `hair`, as do 3 of the 36 frozen fixtures).
- **Verification.** server **1411 passed / 30 skipped** (+9 are the new discriminating checks), cli **69 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files, `npm run lint:i18n` **788 strings / 36 exceptions / 0 errors**. Four perturbations, all of which failed as intended: making the replacement path the identity function (all 445 production works raise `ValidationError`), moving one `GRAMMARS` value (exactly 16 SVG bodies move), restoring `_PRUNED` (the digests return to their pre-rename values exactly), and running the generator twice (byte-identical).
- **On the record**: the reason a rename has a price is that the seed hashes the tool's *name*. **Fixing that moves every work once, so it belongs to an engine version.**

---

### v2.7.10 — PNG is burned by resvg alone (Build 719, 2026-07-27)

**The warnings had been there all along, and they still let it mislead.** cairosvg does not implement `feTurbulence` / `feDisplacementMap` / `feGaussianBlur`, and rather than failing it **drops them**. A PNG came back with the ground grain and the material filters gone and nothing to show for it but a cleaner-looking picture — **and that picture was used to decide things** (four times). A stderr warning in the CLI, a startup WARNING on the server, the module docstring, and a `png_rasterizer` record written into every artifact: the caution had been laid down four ways since v2.2.1. **What misleads a reader is the picture, not the log line**, so the fallback was removed rather than documented further (author's instruction, 2026-07-27).

- **There is no fallback any more.** `_cairosvg_renderer`, `BACKEND_CAIROSVG` and the `_BACKENDS` table are gone from `rasterizer.py`, and `svg_to_png` raises `RasterizerUnavailable` when resvg is absent. **This is the one behavioural change**: where resvg is missing, PNG output stops instead of degrading quietly (ruled acceptable by the author).
- **Three dependency declarations were dropped.** `cairosvg>=2.7.0` left the `pyproject.toml` of `shared`, `server` and `cli`, taking 145 and 148 lines out of the two lock files. `api.py`'s startup log lost its fallback branch, and `cli.py` lost the warn-once and three "resvg-py or cairosvg" error messages.
- **Three sentinels were put in.** ① the three `pyproject.toml` files, read through `tomllib`, declare no `cairosvg`; ② no `.py` under `shared/src`, `server/src`, `cli/src` or `server/scripts` imports it (**the pattern matches import statements at line start only, so the prose explaining why it is gone can stay**); ③ **it stays unreachable even where it is installed** — `pytest.importorskip` runs the check only in an environment that can import cairosvg, then blocks resvg and asserts the raise.
- **The one added skip is that third sentinel.** Dropping the dependency took cairosvg out of the venv, so it skips. **The check only means anything where cairosvg is present, so this is correct.**
- **A side effect: `pillow` left the `server` venv.** It was a transitive dependency of cairosvg, and neither `server` nor `shared` imports `PIL` anywhere. `cli` declares `pillow>=12.0.0` directly and keeps it (**the tool for assembling contact sheets lives in the `cli` venv**).
- **What was not removed**: `android/scripts/render_png_review.py` still calls `cairosvg.svg2png` (sentinel ② does not scan `android/`). **It is a script for reviewing renders by eye, which is exactly the path the removal was about**, so its disposition goes to the author. `libcairo2` in `server/Dockerfile`, an OS dependency that existed for cairosvg, also remains.
- **Four documents were brought back to the present tense**: `SETUP.ja.md` / `SETUP.md` ("prefers resvg and falls back to CairoSVG" → resvg alone, raising when absent) and `manual/ja/application-install.md` / `manual/en/application-install.md` ("OS libraries required by CairoSVG" → resvg-py ships as a wheel and needs none). **Passages in CHANGELOG and PROJECT_CONTEXT that describe past versions are history and were left alone.**
- **Verification.** server **1413 passed / 31 skipped**, cli **69 passed**, ruff clean (both `server` and `cli`), `npm run check` 0 errors / 2 warnings / 217 files. **Not one byte of SVG changes**, so no reference corpus was refrozen. The render engine stays at `"15"`.
- **On the record**: a fallback that degrades in silence gets removed, not documented. **Keep a tool that cannot tell "there is no difference" from "the difference did not come through" out of the path where pictures are judged.**

---

### v2.7.11 — a sentinel is written as where it does not look (Build 720, 2026-07-27)

The two things v2.7.10 missed, and the author's ruling (2026-07-27) that **the rule itself belongs in SPEC**.

- **`android/scripts/render_png_review.py` now goes through resvg.** It is not a dormant script: `headless_render_compare.sh` and `headless_batch_compare.sh` call it whenever `PNG_REVIEW=true`. **It rasterizes the server's and Android's SVG, amplifies the difference, and writes a three-panel sheet plus `metrics.json`** — so a rasterizer that drops filters makes it **agree precisely where both sides have been flattened**. Dropping the declaration from `cli` in v2.7.10 had already left it raising `ImportError` in any re-synced environment.
  - Measured: two SVGs differing only in `feDisplacementMap` scale come out **9.5% mean / 27.4% rms apart**. **Under cairosvg the filter goes with them and the difference is zero.**
- **Sentinel ②'s scope moved from a list of roots to the whole repository minus exclusions.** v2.7.10 named `shared/src`, `server/src`, `cli/src` and `server/scripts`, and so never looked at `android/`. **A named list can fail to be complete; what it cannot do is say so.**
  - Fourteen exclusions (`.git`, `.gradle`, `.pytest_cache`, `.ruff_cache`, `.venv`, `__pycache__`, `bench`, `build`, `dist`, `no-git-sync`, `node_modules`, `out`, `out2`, `site-packages`).
  - **A check was added that the scan actually reaches outside the Python packages** (all of `android`, `cli`, `server`, `shared` appear in its results). **A sentinel is worth exactly what it covers.**
  - **Confirmed by perturbation**: restoring `import cairosvg` to `android/scripts/render_png_review.py` fails the guard.
- **What widening the scan turned up (left alone)**: three past measurement scripts under the untracked `no-git-sync/` call cairosvg (`fable5/render_with_relations.py`, `rfc/phase0-scripts/ab.py`, `rfc/phase0-scripts/ps_ab.py`). They are **a record of what was run**, so they were neither rewritten nor scanned. With cairosvg gone from the venvs, re-running them raises `ImportError` — except `render_with_relations.py`, which catches it and skips PNG generation, so **no picture comes out at all**, which is the safe side.
- **The rule is now in SPEC (author's ruling)** — `SPEC.ja.md` **§15.12 "A PNG is a copy of the performance"** and `SPEC.md` **§12.9**: ① no rasterizer that drops things in silence (at least `feTurbulence`, `feDisplacementMap`, `feGaussianBlur` — **a rule about observation, not about performance or fidelity**); ② **`cairosvg` is prohibited**; ③ an implementation that is wrong is worse than one that is missing (no fallback); ④ how it is held (one entrance, three sentinels, **and ②'s scope written as what it does not look at**).
- **`libcairo2` was not dropped from `server/Dockerfile` this time** — the author ruled it goes **at the next distribution** (2026-07-27). It is filed in the release runbook as **A-1b** (one-off; delete the section once done).
- **Verification.** server **1414 passed / 31 skipped** (+1 is the scan-reach check), cli **69 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files. **Not one byte of SVG changes.**

---

### v2.7.12 — the sheet says how it was made (folded into render engine 15) (Build 721, 2026-07-27)

**`plain`, `paper`, `washi` and `ink_wash` were one and the same in the ground layer.** Only `mezzotint` and `charcoal_ground` branched; `material` otherwise did nothing but enter the seed. **The author ruled it folded into engine 15** rather than given a version of its own: no production work carries engine 15, it is unpublished, and engine 13 set the precedent. **The condition is that it happen before publication.**

- **The first version was a rejection.** Drawing the fibres and the brush as elements took the ground from 2 elements to 40 under the default profile — **46% of the whole picture**, in a work **whose DDL named two shapes**.
- **The direction that replaced it: the support is the character of the noise, not something drawn.** In `display` the difference lives inside the filter (**`washi` crosses two anisotropic turbulences with `feBlend`**; **`ink_wash` stretches one sideways and smears it with `feGaussianBlur`**). In `editable` it changes **the shape of the grains the ground already draws** — washi stretches the same grains along the fibre, ink_wash bands them under the brush.
- **Not one element is added, and the frozen corpus says so**: `C-ground-washi` goes **circle 20 → 0, path 1 → 21** (twenty-one either way), and `C-ground-ink_wash` goes **circle 20 → 12** (`count x 0.6` — fewer).
- **The author set the number by looking at the work.** Of the two rows in the comparison sheet `material-sheet.png`, **the `tone=warm grain=coarse opacity=0.18` row is the one taken** (ruling, 2026-07-27) — **washi is not to be strengthened further**. 0.18 is already the ceiling on every path (`min(0.18, ground.opacity)`).
- **The corpus was refrozen as engine 15.** **Three of its 350 cases moved** (`C-ground-washi`, `C-ground-ink_wash`, `C-groundseed-auto-washi`). Recomputing `changed_from_previous` from scratch was measured first and **reproduced the same 318 entries exactly**, and **a second generator run exits 0 byte-identical**. The manifest's `reason` records what was folded in.
- **The Android expectations did not move.** Regenerating all 36 fixtures gives output **byte-identical to `31ff75d`**, the engine-15 freeze, because **not one Android reference case carries a ground**. **The assumption that folding would force the expectations to be rebuilt is measured false**, and the `feat/android-engine15` contract can be started as written.
- **A test surface was added, since the implementation arrived without one** — five checks in `test_ground_seed.py`: that the material changes **how the grains are drawn** (washi, ink_wash), that **the filter changes too** (presence of `feBlend` / `feGaussianBlur`), and that **the element count does not grow**.
  - The point is **pinning the seed explicitly**. **Without it the layer moves by however much `material` contributes to the derived seed, and killing the drawing branch with `if False` slips straight through** (measured — a check that passed for a reason other than its claim).
  - **Two perturbations confirm it fails**: emptying the noise table, and killing the fibre branch.
- **One existing check was rewritten.** `test_explicit_ground_seed_still_bypasses_the_derivation` asserted that paper and washi are identical under an explicit seed, **which is now false by design**. It varies **the performance seed instead of the material**, so the derivation can be shaken while the material is held fixed.
- **Verification.** server **1419 passed / 31 skipped** (+6), cli **69 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files. **The render engine stays at `"15"`.**

---

### v2.8.0 — the colophon's road is named colophon (**a compatibility break**) (Build 722, 2026-07-27)

**The names you type are English terms of art**: `paint`, `refine` and `lineage` all match the terminology dictionary, which **says so explicitly** of `/api/paint`. **`okugaki` was the only romaji left in that column**, so **the CLI subcommand and the API paths moved to `colophon`** (author's ruling, 2026-07-27). **No alias was kept.**

- **The minor version is because compatibility breaks.** The numbering policy reserves minor for "when compatibility breaks (stored data, API, edition-ID format)". **This is not a patch.**
- **Only the paths carried the word.** `OkugakiItem` returns `id`, `target_node_id`, `branch_snapshot`, `model`, `at`, `language`, `body`, `warnings` and `fact_sheet` — **not one field is named after it**. The rename therefore closes at the paths.
- **What moved (four routes)**: `GET|POST /api/lineage/{node_id}/okugaki` → **`/colophon`**; `DELETE /api/okugaki/{okugaki_id}` → **`/api/colophon/{colophon_id}`**; the CLI subcommand `okugaki` → **`colophon`**; three `fetch` sites in the web client.
- **What did not move (identifiers, per the dictionary's §6)**: the DB table `okugaki` and its index `uq_okugaki_user_idempotency`, **`okugaki_model` in `model_settings` (stored user settings)**, the module `okugaki.py`, and the i18n keys `okugaki*`.
  - **Romaji in key names is the norm, not the exception.** Variation has a perfect dictionary word — `variation` — and its web keys are still **`hensouAxis`, `hensouSmall`, `hensouMedium`, `hensouLarge`**. What the dictionary forbids is **words that reach the screen**, not keys.
- **Two sentinels**: ① no path in `app.routes` contains `okugaki`, and both `/api/lineage/{node_id}/colophon` and `/api/colophon/{colophon_id}` are present; ② the CLI accepts `colophon` and **raises `SystemExit` on `okugaki`** — the check that no alias survives.
- **The boundary is written into the dictionary.** The 奥書 row now says the CLI subcommand and the API paths are `colophon` too, and **§6 gains an "there is one exception" passage** recording what moves, what does not, and **that `hensou*` is the counterexample**.
- **Four documents follow**: `SPEC.ja.md` (`inku-cli okugaki` → `colophon`), `SPEC.md` (**dropping both the "(okugaki)" gloss and the claim that the CLI subcommand keeps its name**), and `manual/{ja,en}/cli-reference-for-ai.md` (the §2.5 heading and its usage line).
- **Verification.** server **1420 passed / 31 skipped** (+1), cli **70 passed** (+1), ruff clean, `npm run check` 0 errors / 2 warnings / 217 files, `npm run lint:i18n` **788 strings / 36 exceptions / 0 errors**. **Nothing in the drawing was touched** — the render engine stays at `"15"` and no SVG moves.

**The same version carries the variation vocabulary too (Build 723).** The colophon was one romaji word; **variation was a collision running the wrong way**. The dictionary reserves `variation` for **the variation alone** (candidates are `option`), yet the implementation had **the real variation as romaji `hensou` while four things that are not variations were called `*_variation`**.

- **The lineage derivation kinds were swapped (stored values)**: `hensou` → **`variation`** (7 rows in production), `touch_variation` → `touch_change` (25), `model_variation` → `model_comparison` (11), `layout_variation` → `layout_change` (6), `language_variation` → `language_comparison` (1). The four with no rows (`render_engine_`, `age_`, `hacho_`, `external_seed_`) follow to `_change`.
- **`vary_seed` → `composition_seed` (186 sites). It was never the variation's seed** — SPEC §12 lists "the description, `vary_seed`, `tenkei`, **and the variation**" **side by side**; it is the Stage 1.5 **composition** seed. **The variation's own `variation_seed` and `variation_amplitude` are unchanged.**
- **The CLI flags moved too**: `--vary-seed` → `--composition-seed`, `--vary N` → `--composition-count N`.
- **The web i18n keys were brought along** (`hensou*` → `variation*`, fourteen of them, and more). **Romaji in key names would normally be the norm**; the author ruled the dictionary applied in full.
- **Stored data is migrated, not broken.** At startup `history.vary_seed` is RENAMEd to `composition_seed` and `lineage_edges.derivation_kind` is UPDATEd by table. **Measured against a copy of the production database** (counts 25/11/7/6/1 preserved, `composition_seed` still 9 rows), and **a second run touches zero rows**.
- **What was frozen, because renaming it breaks things**: **the key `vary_seed` inside the rh2 payload** is **material of an identity ID**, so the name stays and the value comes from the new column. **Renaming it moved the rh2 of every stored work, and the check caught it** (`test_legacy_render_hash_v2_calculation_remains_available`). The `#hensou` / `#vary` salts in `ddl_expander` are hash material and stay for the same reason.
- **The old-to-new mapping is recorded in `no-git-sync/opus5/name_convantion/RENAMES.md`** (at the author's instruction) — the place to look when an external script stops working.
- **The version stays v2.8.0**: it is unpublished, so this folds in rather than minting another (the newest tag is `v2.7.2`). Only the build number moves, to 723.
- **Verification (at Build 723).** server **1420 passed / 31 skipped**, cli **70 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files, `npm run lint:i18n` **788 strings / 36 exceptions / 0 errors**.

**The same version carries the description too (Build 724).** The dictionary sets 記述 = **`description`** (the verb is write) and bans `prompt`, yet **the main request field was a third word, `text`**.

- **`text` → `description`, `original_text` → `original_description`** across the requests to `/api/paint`, `/api/paint/stream`, `/api/interpret` and `/api/compose`, the `/api/paint` response, the CLI's artifact JSON, and everything the web client sends.
- **`dh1`, the description's identity, is untouched** — `description_hash()` hashes **the value alone** and carries no key name (measured before starting, having just been burned by `rh2`).
- **Four `"text"` keys were left alone**: the payloads sent to the LLM providers (Anthropic content blocks, Gemini `parts`). **Those are someone else's API contract.**
- **The DB column `input` on `history` is still a third word** (nine server sites, thirty in the web client), so **the description now goes by two names**; it is measured and filed as the next step.
- **Verification (at Build 724).** server **1420 passed / 31 skipped**, cli **70 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files.

**The same version corrects what that word was attached to (Build 725).** Build 724 moved the word but hung it on the wrong string: **`description` held the augmented text — the description with context injected — and the author's own line was demoted to `original_description`.** The dictionary word names what the author wrote.

- **`description` is the author's description** (required on `/api/interpret` and `/api/paint`), and **the string Stage 1 actually reads gets its own name, `stage1_input`** (optional). **Omit it and the description itself goes to Stage 1**, so a client that injects no context sends only `description`.
- **`/api/compose` loses `original_description` the same way**: its prose field is the author's description, so it is called that (optional there, since the endpoint can be driven by DDL alone). Four web call sites use that path — the contract had estimated three.
- **`input` stays** (the author's ruling). It is the body that gets saved and displayed, which is not always prose: of 1780 saved works four are DDL-shaped and 38 are empty, so the neutral word still fits.
- **Not one internal argument moved.** `composer.py`'s `original_description` and the argument to `_call_compose_detail` already mean the right thing — the author's original text on its way to Stage 2. **Moving one side of that pair without the other raises `TypeError`, which is how the first attempt went 42 tests red.** What may move is only **the Pydantic field definitions, the `req.` reads, and what the clients send**.
- **Four discriminating tests were added**: Stage 1 reads `description` when `stage1_input` is omitted, reads `stage1_input` when it is sent, **the history then stores the `description` rather than the augmented text**, and the CLI payload keeps the two apart. **The implementation was perturbed at two points to confirm each one actually goes red, then restored.**
- **The version stays v2.8.0** (folded into the unpublished version). Only the build number moves, to 725.
- **Verification (at Build 725).** server **1423 passed / 31 skipped**, cli **71 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files.

**The same version carries the last of the romaji (Build 726).** Every name you type was counted — 46 CLI subcommands, 84 flags, 61 API paths — and **exactly one more had the colophon's shape**: the staffage flag, `--tenkei`.

- **The dictionary had already settled 添景 as `staffage`** (GLOSSARY :58) **and the web client already displayed it that way**. The romaji survived only where you type it. It becomes `--staffage`, **with no alias** — the same call the colophon got (author's ruling, 2026-07-27).
- **The help text was a third word**: it read `scenery level`, neither `tenkei` nor `staffage`. It now reads `staffage`.
- **Unmoved**: the request and response field `tenkei` (27 sites in the server), the DB column `history.tenkei`, internal identifiers such as `tenkei_for_node()`, and the web client's `tenkei.ts` and i18n keys. **Romaji in key names is the norm**, and that rule still governs. **An outside script changes the spelling of the flag and nothing else** — whatever assembles the payload is untouched.
- **Two sentinels guard it**: `--tenkei` exits, and **no flag in the parser is spelled `tenkei`**. **The second one first read only the top-level parser and let an alias straight through** when the change was perturbed — the real flags hang off the subparsers. **It was fixed to walk them, and then perturbed again to watch both go red.**
- **`/api/saijiki` and the nine Saijiki category keys stay romaji, correctly**: the dictionary sets 歳時記 = `Saijiki`, a capitalized proper noun, so **the romaji is the right English**. `renga` and `hacho` are the same class. **`sumi` and `washi` are not identifiers but DDL vocabulary** — `sumi` sits beside `ink`, `obsidian` and `黒` as a synonym for black, a word the describer types.
- **The version stays v2.8.0** (folded into the unpublished version). Only the build number moves, to 726.
- **Verification (at Build 726).** server **1423 passed / 31 skipped**, cli **73 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files, `npm run lint:i18n` **788 / 36 exceptions / 0 errors**.

**CI is green again after eight red pushes (Build 727).** The silverpoint rename at v2.7.9 re-froze the render corpus and the coerce golden **in place, without raising a version** — and **missed the DDL corpus in that same commit**. Every push since has failed the `ddl-engine` job while `render-engine` stayed green.

- **The re-freeze carries two renames and nothing else**: the tool name in `B-trigger-auto`'s coerced output, and **fifteen manifest inputs that still recorded `vary_seed`**. No case id moves, and **`ddl_engine_version` stays 1**, for the reason the render engine stayed 15.
- **The mechanism was not what the handoff recorded.** The `hair` in the frozen file was not a stored value being rewritten by a validator — **coerce produced that tool name itself**. **Perturbing the validator changed nothing; only perturbing the literal in `coerce/compose.py` moved the corpus.**
- **The guard now fires after writing**, as the render generator's does. Raising before the write left **no way at all to re-freeze a sanctioned rename**; firing once and exiting 0 byte-identical on the second run is the property the guard defends.
- **SPEC §15.6 now says renames do not raise a version** (both languages). The v2.7.9 ruling was never written down, and the letter of the rule fires on any rename. **Adding a word and renaming one are different acts.**
- **`check_frozen_corpora.py` runs what CI runs, locally.** **The test suite cannot stand in for it**: `test_*_reference.py` compares the frozen files with the manifest and **never regenerates**, so **a corpus drifts while all 1423 tests stay green** — which is exactly what happened all three times. **CI is the backstop, and the Linux re-run is the only thing it alone can prove; it is not the detector.**
- **The check was perturbed to watch it go red**: changing one tool name that coerce produces makes it exit 1 and print the way back (`git checkout -- server/reference/`).
- **The version stays v2.8.0** (folded into the unpublished version). Only the build number moves, to 727.
- **Verification (at Build 727).** server **1423 passed / 31 skipped**, cli **73 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files, **both generators exit 0 byte-identical**.

**The description gets its name on the typing side too, and two broken paths are fixed (Build 728).** `--original-text` **kept the retired third word in its spelling while the key it fills has been `description` since Build 725**. It becomes `--description`, **with no alias**, as the colophon and the staffage flag did; `refine generate --text` fills the same key and follows.

- **That same rename had quietly broken two commands.** **`inspect` and `refine generate` build their payloads by hand instead of going through `_paint_payload`**, and both **kept posting `text` to `/api/paint` after Build 724** — a request carrying no `description` at all, which the required field turns into **a 422**. **All 73 cli tests stayed green, because they never reach a server.**
- **What caught it was classifying every `*-text` flag** rather than fixing the named one. Had `--original-text` been treated alone, both would still be broken.
- **The `paint` and `batch` help called the description a prompt**, a word the dictionary rejects for it; four strings are fixed. **`review evaluate --prompt` and its kin stay** — **there the word means the model's prompt**, a different referent, and only the description sense is banned.
- **Four sentinels, and three perturbations to watch them go red**: an alias left behind, the help sliding back to `prompt`, and `inspect` reverting to the old key. **The `inspect` check swaps in a fake `ApiClient` and reads the outgoing payload** — a static scan cannot tell that key from the `"text"` in LLM provider payloads.
- **The positional (`paint <text>`) does not move.** What you type there is the value, not the name.
- **The version stays v2.8.0** (folded into the unpublished version). Only the build number moves, to 728.
- **Verification (at Build 728).** server **1423 passed / 31 skipped**, cli **76 passed**, ruff clean, `npm run check` 0 errors / 2 warnings / 217 files.

### 2026-07-27 — English documentation vocabulary (**no version**; documentation only)

**README and `manual/en/` were swept against the dictionary, and only six places needed changing. The drift lives in the Japanese source, not in the English.**

- **Six places where the English alone used the banned word `prompt`** now say `description`, or whatever the Japanese says. The Japanese counterparts read `指示`欄 / 記述文 / 指示文 / 短い言葉 / 入力テキスト / 指示文生成モデル — **not one of them says プロンプト**. That is English drifting on its own.
- **The seven remaining `prompt`s are all sound**: two where the Japanese says プロンプト as well (the passage criticising generative AI, and the UI's JSON/prompt views), four where the word means **the model's prompt** (the Prompts panel, the `--prompt` flag), and **the filename `prompts.txt`** in a command example, which is an identifier and identical in both languages.
- **`artwork` appears nowhere in README or `manual/en/`** — the handoff's note was inaccurate. It survives only in the **historical entries** of `CHANGELOG.md` and `PROJECT_CONTEXT.md`, which are not rewritten.
- **The `generation`, `image` and `create` that remain are faithful translations of 生成, 画像 and 作る** in the Japanese (README.ja's もう一度生成 / による生成です / 生成後は歳時記を参照し; the manual's 画像の作成方法 / バッチ生成 / Stage 2が作る). **Moving the English to the dictionary alone would break the pairing**, so it is left for the author to rule on.
- **`SPEC.md`'s seven `scene-tone palette`s are held back for the same reason** — no counterpart term is findable in `SPEC.ja.md`, and a translation should not be invented ahead of the source. **The three `jitter`s are sound**, being an identifier and the signal sense.

### v2.8.0 — call the six colors the six colors (Build 729, 2026-07-27)

**The Stage 2 system prompt told the model to "choose palette by scene tone".** What it chooses there is **the six abstract colors**, never a color catalog — catalogs are server-owned and resolved after Stage 2. **`palette` is also a real field in the catalog JSON**, so **one word was carrying two meanings inside the implementation**. Both prompts now say the abstract colors.

- **This moves the model.** The Stage 2 digests go **`a1bb4ff70488fb35` → `261373d0123a740f` (ja)** and **`397195ed887f6adb` → `f5bd29704e5906f2` (en)**.
- **The Japanese prompt does not change length** (42,824 either way), so **a check that only measures bytes lets this through**; the pinned digests are what catch it. English goes 40,989 → 41,001.
- **`SPEC.md` follows the wording it was mirroring** (`scene-tone palette` → `scene-tone color`, four places). **`SPEC.ja.md` has no passage for this rule at all** — the two SPECs have diverged down to their section numbering.
- **The six remaining `palette`s in SPEC are sound**: four are identifiers in the catalog JSON, two are ordinary art vocabulary.
- **Behavioural equivalence cannot be proven deterministically** — once a word in the prompt moves, only the model can say. **Every deterministic check is green**: server 1423 passed / 31 skipped.
- **The version stays v2.8.0** (folded into the unpublished version). Only the build number moves, to 729.

### v2.9.0 — the six the prompt both forbade and required (Build 730, 2026-07-27)

**A rule forbade a word that a later rule, the vocabulary table, or an example required.** Every explicit prohibition was collected and intersected mechanically with the rest of the same prompt; six of these came out. Two (the Japanese 塗りつぶす and the English `rise` / `fall`) were found in another session, the other four here.

- **The Japanese background sentence moves to an allowed verb**: 「背景を○色で塗りつぶす。」 → **「背景を○色で埋める。」**. Principle 2 listed 塗りつぶす among the forbidden verbs while the Background section ordered the model to write it, and seven examples obeyed. **The English side never collided** — it has always said `Fill background with X.`, and `fill` is an allowed verb. **Each of the two contradictions exists on one side of the translation only.**
- **Every parser keeps accepting the old wording**, so saved works still perform. The Stage 2 rule names both forms and the gray-background rewrite in `ddl_expander` matches either verb. **The remaining background detectors — the color test in `api.py`, the clause split in `compose.py`, the `explicit_surface` markers — key on `背景を` and never look at the verb**, so they are untouched. **coerce is untouched, so the frozen corpora do not move.**
- **English `rise` / `fall` are now split as motion senses** (`rise (as motion), fall (as motion)`), with a line stating that the angle words `rising` / `falling` are Saijiki vocabulary. **`scatter` on the very same line already carried that split** (`as motion` / `as arrangement`); it had simply never been applied to rise and fall.
- **The touchless-line rule was broken by its own examples** — 20 Japanese sentences and 9 English ones. **The bad example the rule names, "draw radial lines", was present near-verbatim as an example output.** Sentences that state nothing but a relation, a proportion, or an angle are now a declared exception, and **the eleven drawing examples were given a touch**.
- **Principle 5 ("Saijiki vocabulary only") was broken by thirteen words not in the table** (surface, ground, printmaking phrases, the colorful list). **Principle 5 is what changed**, to name the fixed phrases this document defines. The vocabulary table is untouched, so nothing propagates to reference §1, the web display, or SPEC / README.
- **`多角形` / `polygon` leaves the unknown-object fallback** — `saijiki.py` marks it as a hidden marker that is deliberately *not* Saijiki vocabulary, and the prompt was ordering it emitted anyway. The Stage 2 polygon rule (`sides=5-8`) and generation through coerce's `shape_intent_markers` are unchanged.
- **The allowed action verbs gain `敷き詰める` / `tile`** — the movements table had six, this list had five, and the Placement section required the sixth.
- **Pen is now stated to be the fallback default rather than the recommended choice**, which is what `pen (default)` in the vocabulary table has always meant; two passages told the model not to reach for it.
- **One example used the forbidden verb 広げる** ("widening the radius"). Unlike the others, no later rule stood behind it.

**Side effects of the checks**

- **The Stage 1 golden keeps its Build 591 fixture**; the fourteen diffs are declared in `_REORDERED_JA` / `_REORDERED_EN`, so **undeclared drift still fails**.
- **Twenty pinned prompt values were re-frozen** (6 Stage 1 base, 3 actual, 1 shared base, 6 Stage 2, 2 saijiki perturbation, 2 schema perturbation). Stage 1 base ja `9c8064958c8e3960` → **`f56778ec689949f8`**; Stage 2 combined ja `261373d0123a740f` → **`b5b40bbc27885eb1`**, en `f5bd29704e5906f2` → **`778f6a6e2dfa124f`**.
- **One example dropped out of the selected set.** Giving the English snow example a touch stopped the touch-backfill from firing, which shifted the replacement slot by one and pushed the sand example out of the five. The test now pins that it is still in the pool.
- **`SPEC.ja.md`'s Stage 1.5 example still showed a gray background**, which `_avoid_gray_background` rewrites to white — the specification's example was older than the implementation. Corrected here.
- **README's DDL blocks are not rewritten.** They quote real saved output with its seed; the old wording is still accepted by every parser, so the record remains reproducible.

**`埋める` already means "fill an area with elements"** — Stage 2's density rule reads 密集/埋める=120〜350. The deterministic layers decide on `背景を` and cannot get this wrong, but **the model may still read the sentence as a density cue**. Both Stage 2 prompts now say the sentence is not a request to fill an area with elements and that the density and count rules do not apply to it. **No model was run, so this mitigation is unverified.**

Every deterministic check is green: server **1424 passed / 31 skipped**, ruff, cli 76, `npm run check` 0 errors, `lint:i18n` 0 errors, **both frozen corpora byte-identical**.

---

### Android `2.1.2-android.1` — the drawing layer catches up to render engine 15 (silverpoint, the seed allowlist, the synced prompts, the explicit-count exemption) (android Build 148090, unchanged, 2026-07-27)

**One contract carried the port from engine 14 to 15, renamed `hair` to `silverpoint`, synced the duplicated server prompts, and taught the governor to leave an explicitly requested count alone.** Android now reports the same render engine 15 as the server. Tests went from **71 with 20 failures** to **89 with none**.

- **Phase 1, the seed key:** the manifest's `vary_seed` became `composition_seed`. The contract named one site; **three test files were actually reading it** (Phase3a / 3b / 3d). `WebDdlExpander`'s `varySeed` parameter and the `#vary` salt are frozen and were left alone.
- **Phase 2, engine 15:** the instruction seed payload is now an allowlist (`color`, `color_hint`, `at` and `relation` dropped; `arrangement` narrowed to `jitter`), `cloudform` moved onto the hand-drawn path, corner shapes and `pen` gained the material layer, and **strength is not distance** (`OUTLINE_OFFSET_GAIN` 2.8 → 1.0, floor 0.0035 → 0.0). **The allowlist alone took failures from 19 to 11.**
- **The ground seed was not ported** — Kotlin has no canvas-ground drawing path and not a single line corresponding to `_texture_seed`. **There is nowhere to put it, so it is recorded as not done.**
- **Phase 3, silverpoint:** the contract's 22 sites plus **two it had missed** (the embedded schema's enum *and* description, and a stroke-width table key). Saved data is rewritten by a new `ServerScoreCompat.kt` called **from both the coerce side and the renderer side** — the server has a single pydantic validator to hold that line, and Android has no equivalent single point.
- **Phase 4, the prompt guard:** all four constants were replaced wholesale and pinned by SHA-256 in `PromptFingerprintTest`. **A second test checks that every name in the manifest is actually under inspection**, because a hand-written list silently ignores prompts added later.
- **Phase 5, explicit counts:** a new `ServerScoreCounts.kt`. **The real obstacle was none of the three functions the contract named — it was the reach of `temperQuietSymbolicShape`.** The server applies it only to corner shapes whose `color_hint` marks them as coerce's own inventions; the Kotlin version also caught circles, ellipses and arcs and had no `color_hint` gate, so **counts the description had asked for were cut to eight before the governor ever saw them**. Narrowing it to match the server moved 42/50 to **50/50**.
- **Seven fixes the contract had not listed:** the material outline for `burin` and `drypoint` (which has never existed on the server) was removed; the surface group moved after the material outline; `performedOutline`'s powder was being scattered with the render seed instead of the instruction seed; the powder's spread gain (1.8) moved to its source; the straight-line powder counts became the line-specific 18 / 34 / 26; the vertical-load test was aligned with the server; and two Kotlin assertions that pinned engine 14 were corrected **to match the frozen reference** (not the other way round).
- **Two holes were in the checks, not the implementation:** deleting the corner-shape material layer outright **still left 85 tests green** (the 25 reference cases contain no triangle and no polygon), and perturbing the powder did not fail either, because **only the count was pinned, so all 48 specks could move**. The first is now closed by `CornerShapeMaterialLayerTest`, the second by pinning a **digest of the positions**.
- **Ten perturbations were run, each confirmed to fail before being reverted.** An identity replacement table costs 5 tests, restoring the 2.8 outline offset costs 6, and killing the explicit-count exemption costs 3.
- **The reference corpus was not touched** (`git diff 60d64c3..HEAD -- server_reference/` is empty). The discriminator — **`05_circle_rotring` unchanged against `12_cloudform_rotring` moved** — was verified by `cmp` against the engine 14 freeze.
- **Reported, not fixed (these need a ruling):** the embedded Stage 2 tool schema is **237 lines** away from the server's (the `canvas` ground, `background`'s old wording, `weight`'s description — and **showing the ground to Stage 2 could ask Android for a support it cannot draw**); Kotlin has one of the server's three tempering passes (**confirmed not to affect counts**); `surfaceSeed` uses the allowlisted payload rather than the full dump; `renderHash`'s engine-version fallback is a default the server does not have; and the UI still displays **render engine `1`**.
- **`server`, `web`, `cli` and `shared` were not touched at all.** `ANDROID_SPEC.ja.md` / `ANDROID_SPEC.md` remain behind.
- **Verification:** the implementing session measured `testDebugUnitTest --rerun-tasks` at **89 tests, 0 failures, 0 errors, 0 skipped** across 20 XML files. **By the author's ruling no acceptance re-run was performed**, so the git session did not run the Android tests. `android/BUILD_NUMBER` only auto-increments on package-producing tasks, so it stays at **148090**.

---

### v2.9.1 — resolving a model by rule instead of by guess (and Ollama Cloud as its own provider) (Build 731, 2026-07-27)

**Every guess has been taken out of model reference resolution.** An unqualified string used to be guessed at — a slash meant NVIDIA, a `gemini-` prefix meant Gemini, and anything else fell to OVMS. **That worked while it happened to be right; now that the OVMS endpoint is stopped, the same path is a silent failure** (`/health` still answers 200, so nothing shows until a drawing is attempted).

**The rule is three steps, with no guessing branch.**

1. **An explicit prefix** (`ollama-cloud:gemma4:31b`) wins.
2. **Sole ownership** — if *exactly one* configured provider lists that model ID, that is the provider.
3. **The stage's default** (`stage1_provider` / `stage2_provider`).

- **"Exactly one" is the point of step 2.** `gpt-oss:20b` is listed by **both `ollama` and `ollama-cloud`**, so it is **deliberately not decided** and falls to step 3. **That ambiguity became a fact the moment Ollama Cloud was added as a provider**; before then "an unqualified name is usually right" was good enough.
- **Why the split point is unambiguous:** a provider ID admits only `[a-z0-9_-]` and so cannot contain a colon. **The first colon is the only possible split**, and the model ID may carry as many more as it likes (`qwen3.5:4b-q4_K_M`).
- **Four branches were deleted:** `anthropic:` (**dead code — the general prefix check caught it first, so it never ran once**), the `gemini-` prefix, slash-means-NVIDIA, and **OVMS as the catch-all**.
- **The web's `providerOfModel` lost its `gpt-oss:` special case and six hard-coded provider IDs. A rule that names a model as an exception is already broken**, and with `gpt-oss:20b` in two providers the exception no longer sufficed.

**Ollama Cloud is now a provider of its own** (`https://ollama.com/v1`, key required, 18 verified models). **The limit is concurrency, not capacity** — eight simultaneous requests answer 429 while only 7.6% of the free allowance has been spent — so a **per-provider concurrency ceiling** was added and is read from the provider definition. **It is not a setting the operator can raise: answering 429 above two requests is the provider describing itself, not expressing a preference.** That the calls leave the machine, and which models are cloud rather than local, is written into all 18 bilingual comments and shown in the tooltips.

**Stored model choices are pairs now.** `okugaki_model` and the demo's `prompt_model` were single qualified strings; they are now provider/model pairs like `stage1_provider` + `stage1_model`. **The old single string is still accepted on read and split**, so an older client sending it is not broken.

**Exactly one behaviour changes**: a bare string that no catalog lists. `my-model` used to reach OVMS and `meta/llama-x` used to reach NVIDIA; both now go to **the stage's provider**. Anything present in a catalog resolves as before — only the reason changes, from "it contains a slash" to "it is in the settings".

**The checks**

- **The expectation table lives in one file**, `web/scripts/model-ref-expectations.json`, and **both the server's pytest and node's `npm run lint:models` read that same file**. "Python and JavaScript agree" becomes a property of the arrangement rather than two tables that happen to match. A further test fails if the table drifts from the shipped catalog.
- **No test framework was added to the web** (still no vitest, no `*.test.ts`). **Node reads `.ts` directly by stripping types**, so the checker is a plain node script in the style of `i18n-lint.mjs`.
- **Each check was perturbed until it failed**: relaxing step 2 from "exactly one" to "one or more" costs 4 Python tests and 3 node checks. **Restoring `split(':', 1)` in place of `indexOf`/`slice` costs 10 of 56** — **Python's `split(':', 1)` returns two pieces, JavaScript's returns one and drops the rest**, which is the sharpest trap in carrying one rule into two languages.

**Measured, not fixed**

- **Step 3 never reaches the stored stage settings.** The `settings` handed to `provider_for_model` is the *catalog* dict, which carries no `stage1_provider`, so in practice it always falls to the default (`nvidia`). **This predates the change**, so it was left alone; a test pins that step 3 does read the stage once a caller passes those keys.
- **`normalize_model_settings` costs about 5.0 ms per call, and `/api/paint` makes 2 — down from 4**, because the same decision had a second implementation that normalized all over again. **Net, the call count went down.**
- `api.py`'s `_resolved_stage_model` / `_resolved_vision_model` still guess: they qualify a request only when it matches the user's current setting. The new rule catches whatever they pass through, so nothing breaks, but **there is no longer a reason to branch on whether the strings match**.

**Verification:** server **1487 passed / 31 skipped** (56 new), cli 76, ruff clean, `npm run check` 0 errors, `lint:i18n` 788 / 36 / 0, **`npm run lint:models` 56 checks passed**. **By the author's ruling no acceptance re-run was performed** — these are the implementing session's measurements. **Neither the Score nor the renderer was touched, so no frozen corpus needed regenerating.** Android has not followed.

---

### v2.9.2 — a model is named together with the place that runs it (Build 732, 2026-07-27)

**Wherever a model is named on screen, the provider is now named with it.** A model id on its own never said *where* it runs, and since v2.9.1 established that `gpt-oss:20b` is served by **both `ollama` and `ollama-cloud`**, **the name is not even unique**.

**The form is `<provider> / <model>`** (author's ruling, 2026-07-27).

| Where | Before | After |
|---|---|---|
| The running line, the work's Stage 1 / Stage 2, the next model, batches | `Google Gemma 4 31B Instruct` | **`NVIDIA NIM / Google Gemma 4 31B Instruct`** |
| The history table's Stage1 / Stage2 columns | `gemma` (cut to eight characters) | **`NVIDIA NIM/gemma`** (the shortening rule is unchanged; the provider goes in front) |
| The lineage node details | **the raw stored string** (`nvidia:google/…` showed through) | `NVIDIA NIM / Google Gemma 4 31B Instruct` |

- **`models.ts` gained `providerLabel()` and `modelDisplayName()`, and every display goes through them.** The register of provider and model labels **grows through `registerModelCatalog()`**, so a provider the operator added shows its own name too — the same mechanism v2.9.1 introduced.
- **The model picker cards are deliberately excluded**: they already sit **under a provider heading**. The model comparison list has always shown `label · providerLabel`.
- **The CLI already printed both** (`Stage1 provider:` / `Stage1 model:`) and is unchanged.
- **`statusModelName` now delegates to `modelDisplayName`, and `shortModel` applies its shortening to the bare model id** rather than to the string with its provider prefix still attached.

**Verification:** `npm run check` 0 errors / 2 warnings / 217 files, `npm run lint:i18n` 788 / 36 / 0, `npm run lint:models` 56 checks passed. **The server, the CLI and the renderer were not touched**, so pytest and the frozen corpora are out of scope.

**Noticed, not fixed:** the web's **static fallback catalog lists only three `ollama-cloud` models** where the server has 18, so in the moment before the server catalog arrives `gpt-oss:20b` looks singly-owned and reads as `Ollama`. **Once the catalog is registered it becomes ambiguous and falls to the stage's provider**, as the rule intends. This dates from v2.9.1 and is not a property of the display rule.

### 2026-07-29 — The documentation rebuilt in three layers, with Japanese and English saying the same thing (**no version**; documentation only)

**Split into a reading layer, a specification layer and an archive layer, with the English SPEC rebuilt into the Japanese section structure.** Every stage of ledger [I-032].

- **A check was written.** `server/scripts/check_docs.py` verifies **(1) the shape of the two languages** (per document, one of `shape` / `sections` / `entries`; **13 pairs**), **(2) where relative links land**, and **(3) the non-published paths a published document names** (frozen). **An undeclared difference is red.**
- **Things moved to the archive.** The changelog became the current file plus two archives, and the engine version history moved to `docs/spec/render-engine-history`. `SPEC.ja` went from 2253 to **1836 lines**
- **The READMEs were shortened.** `README.ja.md` 539 -> 295 lines and `README.md` 585 -> 318. Quick Start rose from 74% of the way down to 33% and 38%. **The three pairs taken out live in `docs/guide/`** (`gallery`, `how-it-works`, `revision`)
- **The English SPEC was rebuilt into the Japanese section structure.** After aligning the section numbers one to one, section 13 was written, then 4, 8 and 9, then 7 and 14, then 10 with 5 and 6, and finally 12. **Section 12 went from four subsections to thirteen.** `SPEC.md` went from 1269 to **2907 lines**
- **The 76 missing English changelog entries were written.** The first archive had no English file at all and now has one (**73 entries, 2169 lines**, matching the Japanese heading for heading and in order), and the second gained v1.85, v1.86 and v1.86.1

**Three things learned, which apply to the next bilingual work**

- **Measuring the correspondence between documents by their h2 titles is wrong.** The English section 12 was titled "Security and Operations", but **only its first 51 lines were about operations**; the remaining 504 corresponded one to one, down to h3 and h4, with the Japanese sections 15.4 through 15.12. **A title goes stale before its contents do**
- **A stage that writes a section in English leaves the older English of the same content elsewhere.** Of the 186 lines in the English section 12's Renderer subsection, **about 110 duplicated 13.11, 13.8, 8.4 and 4.7**. **Before deleting, the identifier sets were compared and every paragraph of the old section was matched mechanically against the new document** — 17 surfaced, of which **2 were genuinely English-only content that would have been lost**
- **Before believing a statement that no English version exists, grep the other documents.** The English text of v1.85, v1.86 and v1.86.1 **was in `SPEC.md` under Accounting for Refinement, where the Japanese SPEC had no such subsections** — the two languages were filing the same records in different places. **The GLOSSARY and `lint:i18n` policy buried inside v1.85 was the only statement of it in either SPEC**, so it moved to 7.8 rather than down into an archive entry

**Japanese barely moved outside the READMEs** (`SPEC.ja.md` did not change by a single line through stage 4c). **Two declared differences remain**: English sections 15 and 17 are deliberately not written, and the operational sections from 18 onward stand in English alone. **`check_docs.py` green, server 1487 passed / 31 skipped, cli 76 passed, ruff green.**

### v2.9.3 — a surface becomes a mark, and thinness becomes an axis (render engine 16) (Build 754, 2026-07-29)

**The drawing version goes from 15 to 16.** Three changes are gathered into one version — they belong to the same layer, and raising it three times would make Android follow three times. All stages of ledger I-001.

**333 of the corpus's 365 cases moved; 32 are unchanged. All 32 are `rotring` and `computer`**, which after engine 12's twelve and engine 15's thirty-two means **the same side has stood still for three versions running**. Their grammar is zero throughout and consumes no seed, so **an axis that changes the hand cannot reach a tool that has no hand**.

#### A surface is performed, not filled in

**Six of the eight touch words scattered circles by a uniform random over the shape's bounding box. They never once saw the shape they belonged to.**

| Shape | Grains falling outside the shape (engine 15) | engine 16 |
|---|---|---|
| triangle | **46 / 90 (51%)** | **0** |
| cloudform | **43 / 90 (48%)** | **0** |
| polygon | 20 / 90 (22%) | **0** |
| circle | 12 / 90 (13%) | **0** |

- **Positions are placed inside the contour, and each grain is performed as one stroke.** The scan uses the same `_scanline_segments` as `_render_fill_strokes`, so a concave shape (cloudform) needs no special case
- **`bleed` had been one ellipse at the centre of the bounding box** — the same picture whatever the shape was. It becomes three bands pushed outward from the contour, and **the innermost ring sits on the contour itself (offset zero)**: a bleed happens on both sides of an edge, so the bands do not float away from the shape as rings
- **`hatch` and `crosshatch` are not changed by a single byte.** In engine 15 those two already sent their centre line through `synthesize_along`; they were not scattering a surface. **That those eight cases are unchanged is what shows the change stayed closed around the six words that scattered**
- **The same word had become two unrelated pictures, one per profile** — display emitted a rectangle carrying `feTurbulence`, `feDisplacementMap` and `feGaussianBlur`, while editable scattered circles. **Both profiles now draw by the same mechanism, and the display clipPath is gone** (`bleed` seeps outward, so the clip would erase what was drawn)
- **Speed is 1.44× slower** (119 production works carrying a surface, in display: 56.2 s → 80.9 s), which is ninety circles replaced by ninety synthesized strokes

#### A tiny fill is placed

A fill too small for scan lines had **degraded into a region fill**. **The degradation was preventing a failure, not being right** — a small shape filled with a hand tool became a machine's fill in that one spot.

- **It is placed as a single dab**, carried along the shape's longer axis, its width decided by the shorter one
- **The mechanism switches where the short side is about 3% of the canvas** (measured at 2.9–3.2% across five tools and six seeds; **the switch happens once and does not go back and forth**)
- **The carry floor of 0.90 was chosen by measurement.** At 0.30, `_edge_window` takes the width to zero over 16% at each end, so **a 10px filled circle becomes an outline with a hollow inside**. At 1.10 the dab is darker than the shape it fills (ink coverage 115%)
- **`rotring` stays a region fill at every size** (it branches before `_uses_hand_stroke`)
- **75.3% of production `filled` closed shapes drawn with a hand tool now take the dab** (measured over 150 works)

#### Thinness becomes an axis independent of the tool's name

**Thinness had been a property of the tool's name.** Asking for a thin line was asking for a different tool, and "a thin pen" could not be written. `Instruction` gains `thinness` (`fine` / `extra_fine`).

| Tool | Default | `fine` | `extra_fine` |
|---|---|---|---|
| silverpoint | 0.5 | 0.5 | 0.5 |
| rotring | 1.0 | 0.6 | 0.5 |
| pencil | 1.5 | 0.9 | 0.525 |
| pen / computer | 2.0 | 1.2 | 0.7 |
| drypoint | 2.6 | 1.56 | 0.91 |
| chalk / brush_thin | 3.0 | 1.8 | 1.05 |
| burin | 3.2 | 1.92 | 1.12 |
| crayon | 4.0 | 2.4 | 1.4 |
| brush_thick | 8.0 | 4.8 | 2.8 |

- **The floor is not a new number; it is the thinnest tool itself** (`MIN_STROKE_WIDTH = WEIGHT_TO_STROKE_WIDTH["silverpoint"]`). It reads as "no line is drawn thinner than silverpoint". **Silverpoint accepts no thinness. That is the specification, not an omission**
- **Three candidates were drawn and measured by ink coverage.** **Rejected, 0.7 / 0.45: the thick brush's `fine` came to 99% of its default** and drawing it changed nothing. **Rejected, 0.5 / 0.25: the tools stop being distinguishable** (at `extra_fine` the eleven tools' distinct widths fall from 9 to 6 — **the thinness axis eats the tool axis**). **Taken, 0.6 / 0.35: 9 to 8**, with only silverpoint and rotring merging
- **Thinness was carried into the material contour too.** Leaving `base_width` at the nominal value would **thin the ink alone and leave the material behind**. Only the thick brush and the crayon carry a proportional term; the rest are absolute and do not move (**a thinned pen line keeps a material band that does not thin**). **The offset was not touched**
- **It was added to the performance seed's allowlist** (19 → 20). The consequence is that **changing thinness also changes the path the line takes, and silverpoint's width does not change while its hand does**
- **coerce does not put it on the lines it adds.** Staffage is coerce's own voice rather than the writer's request, so **a written thinness lands only on the shapes the writer wrote**
- **`thinness` is not a Saijiki word** (author's ruling, 2026-07-29). Stage 1 reads thinness words and writes them into the normalized DDL, but they appear neither in the vocabulary table nor in the Saijiki display

#### Versions

- **`render_engine_version` 15 → 16**, with the reference corpus `render-engine-16/` frozen (365 cases, 333 SVGs held)
- **`ddl_engine_version` 1 → 2** — **the DDL layer behaves exactly as before while every instruction dump carries one more line, `"thinness": null`.** Following the rule that a frozen directory is not rewritten, `ddl-engine-2/` (29 cases) was frozen anew and `ddl-engine-1/` was not touched by a byte
- **`ddl_version` 1 → 2** (author's ruling, 2026-07-29) — **the DDL vocabulary grew.** "An extra fine black line" is a sentence DDL could not write before. **Saved works keep `"1"`**

**Verification:** server **1596 passed / 31 skipped**, cli **76 passed**, ruff green (`src tests scripts`), `check_frozen_corpora.py` **byte-identical twice in a row**, `npm run check` 0 errors / 2 warnings / 217 files, `check_docs.py` green. **At acceptance the core of each of the three stages was perturbed: returning the contour to the bounding box turns four S-3 cases red, making the thinness scale the identity turns thirteen T-1 cases red, and removing the branch into the dab turns fifteen F cases red.**

**Recorded but not fixed**: **Stage 2 fills `thinness` in a measured 10%** of works, and the 96% observed at design time did not reproduce. The deterministic layers — schema, prompt, coerce, renderer — are all green, so **whether it is carried remains a question about the LLM layer** (ledger I-036). **Android is still on engine 15** (I-029; the four prompt constants' fingerprints have been re-baked, so the Kotlin side is red by design).

### v2.9.4 — the provenance drawer says what every row means, and the instruction sheet is called by its name (UI adjustments, fourth round) (Build 755, 2026-07-29)

**Thirty-two instructions from the author, worked through in Builds 733 to 753.** All stages of ledger I-002. **Build 749 is absent: `refactor/engine-16` drew it from the same counter first, so this round went 748 → 750.**

#### The provenance drawer's detail tab — 19 rows to 38

Every field of `HistoryItem` (`api.py`) and `PaintResponse` was matched against the detail tab's nineteen rows, and **the eighteen attributes it had never shown were added** (author's ruling: "everything in groups A and B"). **All 38 headings carry a tooltip, under five subheadings** (Interpretation / Performance / Identity / Origin / Run).

- **`render_wild` is three-state** — `null` means a work saved before the column existed and must be told apart from off. **It displays as "not recorded"**
- Added: `seed_text` / `variation_amplitude` / `variation_seed` / `focus` / `interpret_fallback` (previously only a badge on the canvas) / the three prompt digests / `instruction_lang_requested` (previously only the resolved language) / `note` / `lineage_generation` / `derivation_kind` / `batch_run_id` / `batch_line_number` / `ui_lang` / `render_color_catalog_sub` / `render_canvas_aspect_ratio`
- **The Origin group is omitted entirely for a work that has none of its four items**
- **The drawer closes on a click outside the window** as well (Escape is unchanged)
- **`derivation.ts` is new**: the derivation-kind table moved out of `LineagePanel` so that `CanvasPanel` shares it together with its type
- **Thirteen attributes were left out**: the resolved color map, things already in the caption, things on the prompts tab, a server-internal path, the lineage ID group, and `starred`, which the star button already says

#### The instruction sheet by its name

**The nine keys naming the thing the writer edits now say 指示書** (`DDLを編集` → `指示書を編集` and the rest). **The technical spellings stay** — the DDL version in provenance, "normalized DDL", "Stage 2 user input (normalized DDL)", "the composition of the source work (DDL)". The guide is titled "指示書（DDL）簡易ガイド" and carries a sentence defining DDL.

- **A "paint from the instruction sheet" button sits at the bottom right of the instruction box** on the description tab. It wires up the existing `replay()` (`/api/compose`, Stage 2 only) — no new drawing path and no new derivation kind. It is disabled while the DDL is empty and while a run is in flight
- **The run status and stop button appear beneath that button** (`InputPanel` suppresses its own with `hideRunStatus`)
- **Every modal's paint button now uses the `--action-*` fill** (five were accent-filled). **No ▶ is added**

#### Dark is the default

**The `ui_theme` default for new users and the signed-out screen's initial value are now `dark`** (the author ruled against changing existing users). **`AuthPanel` carried only one hard-coded light set**, so those literals became local tokens and a dark set was placed under `html[data-theme='dark']`. **The background work (`/login-background.svg`) is not inverted** — white paper with ink lines is a material, held to the same rule that keeps `--canvas-paper` paper in dark.

#### The lineage tab

- **A card can star and unstar a work.** `updateHistoryStarState` now updates `lineageGraph` too; it had reached only three paths, so a star on the lineage tab changed nothing when pressed
- **Double click opens the work in the canvas** (single click still selects). **A double click runs the single-click handler twice**, so `openNode` gained a guard against re-fetching the work already selected
- **The edges from the origin to a starred node are drawn in orange**, arrowheads included

#### The mascots

**Two of them are settled: a cube named Incu and a crab named Yuragi** (two checkboxes that did nothing became two radio buttons). `KiwiMascot` and `CrabMascot` are deleted, along with three dead localStorage keys and three dead i18n keys. **The choice is not threaded through props but held as module state, like the language pack** — `RunStatus` is called from ten places, and a prop would add the same argument to all ten.

#### Explaining the history manager

**The clipping boxes were counted first** — a `Tooltip` bubble is `position: absolute` and is cut by any ancestor with `overflow`. `.history-modal`, both `.settings-tabs`, and the three lists all qualify.

- **Inside a clipping box, the browser's own `title`** (it obeys the window and nothing else); **outside, `Tooltip`, all opening downward**
- **Two `title` strings that only restated their label** were replaced with what the button does
- **Aligning the four tabs onto bubbles would mean removing `.settings-tabs`' `overflow: hidden`** and moving the corner radius onto each button — a rebuild of the segmented control. **Left undecided**

#### Also

Version and build date moved to the top of the info modal (**the date is the mtime of `BUILD_NUMBER`, injected by `vite.config.ts` as `__BUILD_DATE__`**; no separate file) / `inku` looks like a button one can press / the batch description box no longer breaks its layout, its height having moved to the outer frame / the batch and demo tabs gained labels and the demo's fields were reordered / the demo's shared settings sit under its own two fields.

#### The GLOSSARY gained exceptions (author-approved)

**Six keys for `prompt` and two for `generat`** were added to `GLOSSARY.md` §5-2 and `i18n-lint.mjs` in the same commit. **A prompt digest is the fingerprint of the prompt itself**, so the glossary's substitution (description for prompt) would change its meaning. **`generat` falls under §2, "generation only when generation is meant".**

**Verification:** `npm run check` **0 errors / 2 warnings / 218 files**, `npm run lint:i18n` **877 / 44 / 0 / 0**, `npm run lint:models` 56, server **1596 passed / 31 skipped**, cli **76**, ruff green. **Drawing is untouched**, so the frozen corpora do not apply.

**Fixed at acceptance, absent from the implementation report**: **`test_current_user_theme_can_be_updated` had lost its discriminating power.** When Build 744 made dark the default, the test's `"light"` strings were replaced mechanically with `"dark"`, leaving it **patching dark onto a default of dark** — so **commenting out `row.ui_theme = ui_theme` in `update_user_settings` leaves it green** (measured). **It now asks for the non-default side, reads it back, and was confirmed to fail under that perturbation.**

### 2026-07-29 — the version history is written in the names of its own time (**no version**; documentation only)

**A section stamped with a version is written in the names and materials of that version** (author's ruling, 2026-07-29). The split is that **SPEC holds the present and the version history holds the origin**.

The divergence sat in **§Versions and the Identity ID (v2.4.5)** of `docs/spec/render-engine-history`, where **only the English had been updated to the present, twice**. The Japanese was internally consistent as the record of v2.4.5, so **not one line of that Japanese section moved**.

- **`composition_seed` went back to `vary_seed`** in the English (the rename is v2.8.0; at v2.4.5 the field was `vary_seed`)
- **`render_wild` was dropped from the English identity list.** It entered the material at **engine 12 (v2.5.0)**, so naming it in the v2.4.5 section placed it in the wrong decade of the document
- Nothing true was deleted: **both languages gained one line in the engine 12 section** — `render_wild` joined the `rh3` material, and the format name stays `rh3` — which moves the fact to where it belongs chronologically
- **`vary_seed` is not a dead name.** It is **frozen and live as the material key of the older `rh2` format** (`SPEC.ja.md` §4.7); a blanket replacement would reach into the saved works' `rh2` and rewrite that too
- **No sentinel can catch this.** This pair is checked by `check_docs.py` at **`shape`** — the heading skeleton — so a single word inside a body line never turns red, and `npm run lint:i18n` reads only the web's display strings. **That is why it survived from the v2.8.0 rename until today.**

**Verification:** `check_docs.py` green (the same two declared differences; 56 internal references). **No running code changed**, so no version is stamped.

---

### Android `2.1.3-android.1` — the drawing layer catches up to render engine 16 (the thinness axis, the tiny fill, the declared version) (android Build 148090, unchanged, 2026-07-29)

**The part of engine 16 that the port shares with the server is now in place, so Android reports render engine 16 as well.** Tests went from **89 with 15 failures to 99 with none**.

- **Phase 1, the seed:** `thinness` was added directly after `weight` in **both** dumps — `serverInstructionJson` and `surfaceSeed`. **Kotlin carries the seed material in two places**, so doing one leaves the surface check red. The `CornerShapeMaterialLayerTest` expectations were retaken at engine 16
- **Phase 2, the prompts:** the server's four constants were synced whole (`STAGE1_*` at 18,945 and 17,932 bytes, `STAGE2_*` at 43,822 and 41,887). `*_LITERT` is out of scope
- **Phase 3, thinness:** carried through the schema, the coercer, the stroke width and the material outline. The scale is `null=1.0` / `fine=0.6` / `extra_fine=0.35`, and **the floor is derived from the smallest entry of the tool table (silverpoint's 0.5), not from a new constant**. The material outline takes the narrowed width and **its offset does not move**. **The coercer stores what it is given and never makes `thinness` from the DDL**
- **Phase 4, the tiny fill:** only when fewer than three scanlines make `renderFillStrokes` return `null` does a `fill-dab-v1` go down, as **a single path**. `rotring` keeps its region fill
- **Phase 5, the version:** the renderer metadata and the render-hash fallback both say `"16"`. **No `"15"` remains as an engine version**
- **The six surface textures (`stipple`, `grain`, `paper_grain`, `wash`, `aquatint`, `bleed`) are not implemented.** They are out of scope by the author's ruling `D-20260729-android-declares-the-shared-part`, so **the port declares the version while implementing part of it** — the report says so in a line of its own
- **Acceptance reproduced and perturbed rather than copying the report's numbers.** The full 99 were rerun here to confirm 0 failures, and **five perturbations, one per phase**, each turned red the assertion the contract named: deleting the one `thinness` line from the `surfaceSeed` dump reddens `test06SurfaceHatchExactParity`; one character into the Japanese Stage 1 prompt reddens `PromptFingerprintTest`; dropping the stroke-width floor reddens `ServerRendererThinnessTest`; moving the scanline boundary from 3 to 4 reddens `DefaultSvgRendererFillDabTest`; and putting `"15"` back reddens `Engine16VersionTest`
- **Two of them discriminate one step harder than the report says** — perturbations 1 and 3 also redden the end-to-end reference parity (`testEveryReferenceSvgMatchesOnPathsPointsAndDashes`), where the report counted one failure each
- **That the `CornerShapeMaterialLayerTest` expectations come from the baked reference SVGs was confirmed at acceptance by recomputing the digests from those SVGs** — `31_triangle_pencil` gives `contour-stroke-v1 controls-64 events-2`, two strata, 48 specks and the digests `6fcd7fdf…` and `ecaf7129…`; `32_polygon_brush_thin` gives `controls-102 events-1`, two strata, no specks and `1d646f6c…`. **All four were reproduced from the frozen SVG rather than from the port's own output, and match the test.**
- **The discriminating pair is `01_circle_pen` moving while `05_circle_rotring` stays still** (`0202eec…` to `b79faee…` against the engine 15 freeze; `60e774d…` unchanged). **The machine pole has now held still for three versions running**
- **Only the ten `fill_dab_group` cases compare coordinates within `1e-5`** — the fixture stores its contour rounded to six decimals, so replaying the stored contour moves a final digit by 1e-6 (`495.275170` against `495.275171`). **The end-to-end frozen SVG comparison stays exact on the string**, including `fill-dab-v1` appearing in `26_tinyfill_circle_pen`, and every case is green
- **Neither `server/` nor `server_reference/` moved by a byte** (`git diff 0350cc0..HEAD` is empty for both)
- **Only `android/VERSION` is stamped.** `APP_VERSION` (`v2.9.4`), `web/BUILD_NUMBER` (755) and `android/BUILD_NUMBER` (148090) all stand still, and **pentala needs no deployment**
- **Verification:** Android **99 tests, 0 failures, 0 errors, 0 skipped** (23 XML files). After the merge, in the main checkout: server **1596 passed / 31 skipped**, cli **76**, ruff green over `src tests scripts`, `npm run check` **0 errors / 2 warnings / 218 files**, and `check_frozen_corpora.py` byte-identical
- **Still outstanding:** `ANDROID_SPEC.ja.md` and `.md` **have not followed engine 15 either** ([I-013]), which this contract left out of scope

---

### 2026-07-29 — declaration order is part of the specification (**no version**; documentation only)

**Two author's rulings from 2026-07-29 ([I-037] and [I-040]) were written into the documents.** They were made in the engine-design session, which cannot write to the ledger, so **only their delivery was outstanding** — the record lived in §2.2 of the design handoff and had never reached `DECIDED.ja.md`.

- **The fact goes in SPEC** (`SPEC.ja.md` §5.1 and its counterpart in `SPEC.md`): **the Stage 2 tool schema reaches the model with its property order intact, and an optional field's fill rate depends monotonically on where it is declared.** Moving `Instruction.thinness` alone through five positions measured **0% at the head, 18% at position 14 (where render engine 16 declares it), 48% at 19, 83% at 22 and 89% at the tail** (25 distinct inputs, the same Stage 1 output, the same Stage 2 prompt, `nvidia:google/gemma-4-31b-it`, counted over the 21 that completed all five groups). **The head scoring 0% rules out "sitting next to a related word is what hurts": the further back a field sits, the more often it is filled**
- **The rule goes in the version history** (under "When the version goes up" in `docs/spec/render-engine-history`, both languages): **the DDL transform layer (`DDL_ENGINE_VERSION`) has a reason of its own — the declaration order of `Instruction`'s fields changed.** **Not one line of behaviour need change for the distribution of Scores, and therefore the drawing, to change**
- **The split across two documents follows the 2026-07-28 restructuring**, which moved the canonical home of the version rules out of SPEC and into the version history (`SPEC.ja.md` says so explicitly). The ruling said "write it in SPEC", so **the fact and the rule were separated to satisfy both**
- **This is the one reason a frozen corpus cannot catch.** The corpus fixes the Score and watches the performance, so a change in which Scores are produced moves nothing in it
- Two clauses were added to the development conventions (a private document): **do not reorder keys when comparing schemas**, and **assert the position before sending if you reorder**. **Two sessions fell into that trap independently** — comparing with `json.dumps(..., sort_keys=True)` reported "byte-identical" for what was in fact identical content in a different order, and that order was the cause
- **Actually moving `thinness` to the tail is a separate contract** (`thinness-declaration-position.md`, phase 1; **not started**). This entry is documentation only, and **no running code changed**

**Verification:** `check_docs.py` green (the same two declared differences; 56 internal references).

---

### 2026-07-29 — the README opening was rewritten, and the English followed (**no version**; documentation only)

**The author rewrote the three opening paragraphs of `README.ja.md` and part of the "how it works" section** — the beginning in a museum, what to do with that first sentence, that DDL implements neither meaning nor feeling, and that once the specification moves on, the old picture does not come back. This entry records the catch-up and the corrections.

- **The English README was re-translated from the updated Japanese** (nothing was written into English as English). **Four paragraphs** had diverged
- **The English README called sway `variation`.** The dictionary reserves **`sway` for 揺らぎ** and **`variation` for the variation alone** (the Stage 1.5 shake). **Five occurrences became `sway`; the four that really mean variation stayed** — each was decided against its Japanese counterpart (ゆらぎ / 揺らぎ against バリエーション / 変奏)
- **`npm run lint:i18n` reads only the web's display strings, so a README violation survives any number of cycles.** This is the same class as the 49 found in SPEC on 2026-07-28, and again it took a person reading the dictionary to find it
- On the Japanese side: the typo `Rendrer` → `Renderer`, two sentences joined by a comma, six places missing the space around Latin words, the numeral `3つ` → `三つ` (the existing README counts in kanji), and the redundant `LLMモデル` → `LLM`
- **The two pieces of information the rewrite dropped** — the per-stage model examples and the sentence explaining the gallery's seeds — **were not restored, by the author's ruling, and the English was trimmed to match**

**Verification:** `check_docs.py` green. **No running code changed.**

---

### v2.9.5 — thinness is only written once it stands last (DDL engine 3) (Build 763, 2026-07-29)

**`Instruction.thinness` moves from just after `weight` (position 14) to the end of the declaration (position 23).** The thinness axis added in engine 16 had barely been reaching the picture, because of where it was declared.

- **Carry goes from 18% to 89%** (25 distinct inputs, `nvidia:google/gemma-4-31b-it`; 25 of 28 instructions across the 19 inputs that contain a thinness word). **Not one character of the field changed. Only its position moved.**
- **`sort_keys=True` is gone from `_stage2_prompt_digest`** ([I-038]). **The fingerprint was blind to order, so a change that moves the picture had never once been recorded in `history.stage2_prompt_digest`.** Japanese `32e65db9dcb68e99` → `e11b7daa7c65a5fe`, English `31d357f591d4cf9b` → `e1eacdb0176f7f98`. **Stored values are left alone** — a past value points at a past schema order, and that is simply true.
- **Four discriminating tests were added** (`test_thinness_declaration_position.py`). **No other gate catches this property**: the frozen corpora start from a Score and never pass through Stage 2, so reordering the declaration turns nothing red. Measured: **stage 1 alone left all 1596 tests green.**
- **`DDL_ENGINE_VERSION` 2 → 3.** `DDL_VERSION` stays at `2` (no word was added), and **render engine stays at `16`** (no performance moved by a byte).
- **The reference corpus `ddl-engine-3/` was frozen. All 29 cases are byte-identical to `ddl-engine-2/`, and `changed_from_previous` is empty.** **That emptiness is the description of the version**: the corpus fixes the Score and watches the transform, so a change in *which Scores arrive* moves nothing in it.
- **`gen_ddl_reference.py` had recorded every case as changed whenever a new version directory was cut.** That was invisible for engine 2, where every dump really did change; here it would have made the manifest claim the opposite of what the version means. **The previous manifest now decides** — which `gen_render_reference.py` already did, and which step 4 of `server/reference/README.md` already required.
- **Five tests pinned `ddl_engine_version == "2"` and went red; they were re-pinned** (four in `test_api.py`, one in `test_ddl_reference.py`).

**Verification:** server 1600 passed / 31 skipped (+4 new tests), cli 76 passed, ruff clean, `npm run check` 0 errors / 2 warnings / 218 files, `npm run lint:i18n` 877 / 44 / 0 / 0, `npm run lint:models` 56, `check_frozen_corpora.py` byte-identical, `check_docs.py` green. Both perturbations (revert stage 1, revert stage 2) were re-applied on the accepting side and measured to turn P-1+P-3 and P-3 red respectively.

**The build number skipped.** 762 had already been taken by `feat/ollama-cloud-provider`, so 763 was taken.

---

### v2.9.6 — you can now start without an API key (Build 765, 2026-07-29)

**Choosing a local Ollama as the provider is enough to run inku without a single API key.** The measured recommendation is **Stage 1 `qwen3.5:4b-q4_K_M` plus Stage 2 `ministral-3:8b-instruct-2512-q4_K_M`** (9.4GB together, 71% coverage), replacing the previously approved `qwen3.5:4b` plus `gemma4:e4b` (13.0GB, 64%).

- **`SETUP.ja.md` and `SETUP.md` gain "running without an API key (local Ollama)"** (between the web UI and the CLI), and `OLLAMA_BASE_URL` / `OLLAMA_CONTEXT_LENGTH` join the environment table. `deploy/compose.yaml` passes `OLLAMA_BASE_URL` to `api` and maps `host.docker.internal` to the gateway through `extra_hosts` — **"local" seen from inside a container is not the host**.
- **The Ollama model list is replaced by the ten that were actually measured** (`MODEL_CONFIG_VERSION` 2.2.0 → 2.3.0). **The tags name the quantization**: a bare tag is a moving target upstream, and it would stop matching the measurement behind it.
- **Stage 2 asks a local Ollama by schema rather than by tool** (`response_format`). **A tool definition rides in the prompt, and the Score schema was large enough that Ollama was discarding 75% of it.**
- **Thinking is turned off** (`reasoning_effort="none"`). **Ollama starts thinking by itself when nothing says otherwise, and that thinking shares the answer's budget**, so whatever ran past the budget came back as nothing at all. With it off the same work ran 8× faster and coverage did not move.
- **Speed left the release display and is shown in developer mode only** (`speed_developer_only`, the implemented form of the 2026-07-27 ruling). **Numbers measured on one machine with no GPU are not a promise to anyone else's.**
- **Re-importing a stored catalog widened from nvidia to every builtin provider.** A stored list belongs to the installation and decides which models exist; what it must not do is outlive a catalog whose measurements changed, so on a version bump the builtin metadata is laid back over the matching ids.
- **One sentence was added to both READMEs**, right after "at least one LLM provider is needed", pointing at the key-free path in SETUP. **That line still read as though a key were mandatory.**

**Fixed at acceptance, absent from the implementation report.** The branch was cut at Build 730, before `e653f52` (Build 731) made every id in `PROVIDER_GROUPS` bare, so **three disagreements existed that neither branch could turn red on its own**.

- **The ten new entries in `web/src/lib/models.ts` were written qualified**; they are merged bare, matching the server's `VERIFIED_OLLAMA_LOCAL_MODELS`.
- **`test_web_fallback_list_matches_the_catalog` read the ids with `ollama:` baked into its pattern.** Loosening it meant starting the scan at the group's `models: [`, since the looser pattern would otherwise have read the group's own `id: 'ollama'` as a model.
- **`web/scripts/model-ref-expectations.json` described the Ollama catalog that was replaced.** `gpt-oss:20b` is now owned by ollama-cloud alone and is decided by rule 2; `qwen3.5:4b-q4_K_M` is now owned by ollama and likewise; `llama3.2` is gone from every catalog and so carries the opposite lesson — **a retired id stops being decided by rule 2**. The case both of them used to make, that a colon-bearing id no catalog holds falls through to the stage default, is carried by a new entry.
- **Replacing the Ollama list removed the last model two providers both listed.** `test_sole_ownership_decides_and_ambiguity_does_not` depends on exactly that, and **failed by name: "the ambiguity this rule exists for is gone"**. The second owner is now injected from the expectation table, by the Python reader and the node reader alike, before either builds its groups; the three assertions are unchanged.

**Verification:** server 1628 passed / 31 skipped, cli 76 passed, ruff clean, `npm run check` 0 errors / 2 warnings / 218 files, **`npm run lint:models` 58** (+2 for the added case), `npm run lint:i18n` 877 / 44 / 0 / 0, `check_frozen_corpora.py` byte-identical, `check_docs.py` green. **Four perturbations, one per mechanism**: dropping `reasoning_effort` reddens the Stage 1 thinking test; narrowing the re-import back to nvidia reddens the two version-bump tests; turning off `speed_developer_only` reddens the release-display test; killing the `response_format` branch reddens the schema test and the Stage 2 thinking test.

**The version is a patch.** The report argued for a minor, but **the rule reserves minor for a milestone the author declares or a break in compatibility**, and the shapes of the stored settings, the API and the edition ID all stayed where they were.

---

### v2.9.7 — the cards carry only what tells them apart, and the backup says when (Build 766, 2026-07-29)

**The fifth round of UI adjustments** ([I-044]). The author gave five instructions in conversation and each was deployed as it arrived, as Builds 756 through 760. **All five were accepted by the author in the running UI.**

- **The four tabs in the history manager now carry the same bubble as every other button** ([I-042]). `.settings-tabs` held `overflow: hidden` in order to cut its own corners, **which clipped any bubble placed inside it**, so those four used a native `title` instead. The `overflow` is gone and the rounding moved onto the first and last buttons. Wrapping a button in a `Tooltip` **stops the buttons from being siblings**, so the divider selector was rewritten around `.tooltip-wrap`.
- **The verbs left the work panel of a card.** `Trash` / `Restore` / `Delete permanently` are reached by selecting and using the toolbar, and `Replay` was removed from **all three places it appeared in the modal** — fixing one would have left it visible in another view of the same modal. **The replay feature itself remains in `CanvasPanel`.** What is left is star / hash / **generation number** / **model name**, the last two added in this round. **The inline delete buttons stay in the table and the lineage rows** (author's ruling: aggregating into the toolbar is the discipline of the thumbnail panel, not a principle of the whole modal).
- **DB backups gained a resident scheduler.** `ensure_scheduled_db_backup()` **had exactly one caller, the admin-only `GET /api/settings/status`**, so "every N days" meant **whenever an admin first opened the panel after N days had passed**. Adding a time of day on top of that would have made the field lie, so **the situation was put to the author before any of it was written**. `_lifespan` now owns a task that asks once a minute whether the backup is due (`INKU_DB_BACKUP_SCHEDULER=0` removes it). **The coarse tick is deliberate: the due time is derived from the last backup, not from the loop's own period**, so a late wake-up delays a copy rather than skipping one.
- **`backup_hour` and `backup_minute` join the settings** (3:00 by default). **The interval decides which day and the time decides when on that day**, so a backup taken late at night does not drag its successors along. **No stored data needs reinterpreting and the API only gained fields** — nothing was removed or renamed.
- **What the database is keeping now rides along on `/api/settings/status`** (generation / kind / timestamp / size). **Generation 1 is the newest** and the highest number is the next to be pruned. **Manual backups are never pruned and so sit outside the numbering** (`—`). **The payload stops at 50 rows but the total count and total size cover every file**, so the cutoff cannot hide usage.
- **"Reload" was writing a backup.** The `ensure_scheduled_db_backup()` call left in `GET /api/settings/status` **had been the only trigger before the scheduler existed**; afterwards it was a duplicate that contributed nothing but a side effect. The author ruled it out. A test now **puts the backup past due, reads the status, and watches for no automatic backup file appearing**.
- **The backup time field could not be read** (the author: "far too cryptic to understand"). Two causes overlapped — **a third field pushed each track down to about 108px, too narrow for `input[type="time"]`**, and **the hint sat below all three fields, where it does not read as belonging to the time**. **The hour and minute became two number fields matching their neighbours** (rejected: explain it in a sentence / keep `type="time"` and fix the width and the hint).
- **`Reload` became `Refresh`.** **The key is shared by the DB, log and user-settings tabs.** `settingsReloadSettings` is a separate key in two other places and the author did not name it, so it was left alone.
- **A paragraph of `SPEC.md` §22 had become false and was corrected.** "Scheduled backups are created when the settings status endpoint is loaded after the interval has elapsed" describes **precisely the behaviour this version removed**. **The Japanese SPEC has no operational sections**, so only the English was touched (the 2026-07-28 ruling: Japanese is canonical for the concepts, English carries operations).
- **One new token**, `--thumb-plate-fg-read`. The plate's 0.42 text colour **is enough for a star, which is read by its shape, and too faint for a number, which is read as a number**. Like the rest of the plate family it does not follow the theme.

**Verification:** server 1635 passed / 31 skipped (+7 new tests), cli 76 passed, ruff clean, `npm run check` 0 errors / 2 warnings / 218 files, **`npm run lint:i18n` 897 / 47 / 0 / 0** (+20 strings, +3 exceptions), `npm run lint:models` 58, `check_docs.py` green. `check_frozen_corpora.py` was not run: `renderer.py`, `stroke_engine.py`, `schema.py`, coerce and `saijiki.py` are untouched.

**Eight perturbations were applied by the implementing session and all eight went red** (ignore the time, drop the write, reverse the ordering, number the manual backups, build no task in `_lifespan`, let the loop die on an exception, ignore the environment variable, restore the removed side effect). **The accepting session did not measure them again** — the author ruled that a second pass was unnecessary. **The time test demands 22:45 rather than the default 3:00** so as not to repeat the fourth round's lesson, that changing a default can turn the test guarding it into a tautology.

**The branch was cut early, and nothing disagreed.** Since `217580f`, main touched the same files in two commits: four `ddl_engine_version` pins in `test_api.py` (`"2"` → `"3"`) and one `APP_VERSION` line. **None of the new tests pin a layer version**, so both merged automatically. The only conflict was `web/BUILD_NUMBER`.

**The version is a patch.** Five UI changes and two server changes, but **none of the stored-data, API or edition-ID shapes moved** (the settings gained two keys and lost none). The render engine stays at **16** and `ddl_version` / `ddl_engine_version` stay at **2 / 3**.

---

### 2026-07-29 — The project icon now opens the README (**no version**, documentation only)

`no-git-sync/mascot/incu/incu-icon-512.png` was published as `docs/assets/incu-icon-512.png` and placed at the top of both READMEs, centred at 120px directly above `# inku`. The source file name `incu` was kept as it is, on the author's instruction.

- **It has to live under `docs/assets/`.** `.gitignore` excludes `docs/*` and re-includes only `!docs/assets/`, `!docs/spec/`, `!docs/history/` and `!docs/guide/`, so an image placed anywhere else resolves on the author's disk and 404s on GitHub. This is the same path the three gallery images already travel.
- **`<p align="center">` was measured against GitHub's sanitizer before the push.** Sent through `POST /markdown`, both `align` and `width` survived; the only change was that the `<img>` came back wrapped in an `<a>`. It is treated exactly like the existing `<table align="center">`.
- **Nothing about the application changed.** `web/BUILD_NUMBER` and `APP_VERSION` were not moved, nothing was synced to the development host, and the web favicons (`web/static/favicon*.png`, `web/src/lib/assets/favicon.svg`) were not replaced.
- **The GitHub social preview — the card image shown when the repository link is shared — was not set.** It can only be uploaded through the repository settings page; the REST API exposes no endpoint for it. It is a separate thing from the README image.

---

### 2026-07-29 — The top page now introduces itself in Japanese as well (**no version**, documentation only)

**GitHub has no mechanism for serving a README in the reader's language.** `README.ja.md` is not recognised as a README at all; the top page shows `README.md` and nothing else. The two files had linked to each other for a long time, but the link sat on **line 322 of `README.md` — the last line**, so a Japanese reader had to scroll the whole page to find it.

- **A language bar was placed at the top**, directly under the icon and above `# inku`. Both files carry it, centred, with the language being read in `<strong>` and the other one as a link.
- **A Japanese introduction was placed in `README.md` as a blockquote**, immediately after the English one-liner. The wording is taken verbatim from the opening of `README.ja.md`: **Japanese is canonical, so Japanese embedded in the English file is not newly authored either.**
- **Not one heading was added.** `check_docs.py` compares this pair in `shape` mode — the sequence of heading levels and nothing else — so a paragraph and a `<p>` without a heading leave the two skeletons identical. **The same introduction under a `##` would fail the check.**
- **`<p align="center">` and the blockquote were measured against GitHub's sanitizer before the push** (`POST /markdown`). The `align` attribute, the link, the `｜` separator and `<strong>` all survived.
- **The About field in the sidebar was left alone.** It can only be changed through the settings page or an authenticated API call, so a bilingual draft (223 characters against a 350 limit) was handed to the author instead.

---

### v2.9.8 — The screen can be made smaller, and what cannot be chosen is no longer offered (Build 776, 2026-07-29)

**Two branches entered together.** The sixth round of UI adjustments
(`feat/ui-adjustments-6`) and the Ollama Cloud model evaluation
(`feat/ollama-cloud-provider`) are independent of each other; the only conflict
was `web/BUILD_NUMBER`.

#### How much is shown is the writer's choice

- **Three UI modes, stored per logged-in user.** `user_accounts` gained `ui_mode` (default `simple`) and `ui_custom` (JSON). **Simple UI** shows only what is required — the user menu, the way into settings, the single description input, the drawing controls and the canvas. **Full UI** shows everything, as before. **Custom UI** adds any of seven groups to the required set. **A new account starts in Simple UI.**
- **A mode changes the display layer and nothing else.** Feature paths, history and stored data are untouched; a hidden tool works again the moment the mode is changed back. **If the mode is changed while an input method or a work tab it cannot show is selected, the view returns to the single description input or to the canvas.**
- **The modes are not named after proficiency** — `GLOSSARY.md` rejects `Beginner` / `Expert`. The ruled terms are `UI mode`, `Simple UI`, `Full UI`, `Custom UI`.
- A switcher sits permanently on the left rail. Settings → Misc carries the mode choice, the custom items, a note on what is always shown, and "back to Simple".
- **The favicon is now the project icon** (64px, 192px, and the compatibility file).

#### Marking what cannot be chosen

- **Ten of the eighteen Ollama Cloud models answer 403 on the free tier.** They appear in the provider's listing, so without a mark they look ordinary and **the wall is met only by drawing into it**. They now carry `requires_subscription` and cannot be selected.
- **A re-fetch does not clear that mark.** An EOL mark is cleared because the listing carries it; a paid-plan mark is not, because the listing does not. **The difference is where the mark comes from: the listing, or a measurement.** Written into SPEC.
- **The eight that can be reached were measured four runs each** and given recommendation levels and tooltip text. **No level 5 was awarded**: the one model that succeeded on every run needed correction on the heavy side, and **four runs cannot separate a shared host's luck from a model's ability** (the median for `gemma4:31b` moved 11s → 105s → 35s on one day). Speed stays developer-mode only.
- **The two paid models were also removed from the fallback list in `models.ts`.** The fallback carries no marks, so for the few hundred milliseconds before the server catalog arrives they looked ordinary. **The rule is not "keep this list fresh" but "do not put something guarded by a mark where marks are not shown"**, and a test now holds it.
- **A model that writes its own `version` no longer costs the Score** — the guess is dropped instead. **That path runs through all five validation sites for every provider** (tool, text, JSON), making it the widest-reaching change in this version.
- **`MODEL_CONFIG_VERSION` moved 2.3.0 → 2.4.0 (ruled in this session).** The bump lays the builtin metadata back over stored catalogs so the mark reaches the ten. **Stored model lists and enable/disable choices survive**, so nothing is lost. **The reason the implementing session gave was wrong when measured**: the development host's stored catalog was at `2.2.0`, where the re-layer already runs. What the bump actually reaches is **an installation already stored at 2.3.0**.

#### An accident on the shared host, and what was done about it

- **A parallel branch ran `rsync -a server/src/inku_server/` and took the other branch's `ui_mode` and `ui_custom` off the development host.** A branch does not carry what the other added after they diverged, so **sending the directory deletes it**. `AGENTS.md` said "do not rsync the whole `server/`" but never said **the same thing happens one level down**.
- Three repairs. **The front end now checks the PATCH response against what it asked for** and does not accept a 200 from an API that ignored the unknown fields — without it the optimistic update silently fell back to simple. **The deploy helper refuses, before rsync, a sync that would remove a feature the remote already has.** A deployment-only integration branch carried both until now.
- **Filed in the ledger as [I-053].** The permanent fix is undecided.

#### The build number skipped

**766 is followed by 776.** The sixth UI round used 767–771, Ollama Cloud used 772 and 774, and the deployment integration branch used 773 and 775. **The counter is shared, not per branch: your own +1 is not necessarily free.**

#### Verification

**The merged tree was compared against the integration branch that had been measured green on the development host: the only differences were five documentation files and `BUILD_NUMBER`, with not one byte of source differing.** The checks that ran there therefore apply to this merge.

server **1668 passed / 31 skipped** (+33), cli 76 passed, ruff clean, `npm run check` 219 files / 0 errors / 2 warnings, **`lint:i18n` 918 / 47 / 0 / 0**, `lint:models` 58, `check_docs.py` green. `check_frozen_corpora.py` was not run: `coerce/`, `ddl_expander.py`, `renderer.py`, `stroke_engine.py`, `schema.py` and `saijiki.py` are untouched.

The perturbations were applied by the implementing sessions — 5/5 on the `requires_subscription` checks, 6/6 on the wiring and `version` checks, and one on UI mode persistence. **The accepting session did not measure them again** (the author ruled a second pass unnecessary) **but ran every check that meets the merged tree for the first time.**

**The version is a patch.** The two new columns are additions with defaulted migrations; no stored-data, API or edition-ID shape moved. The render engine stays at **16** and `ddl_version` / `ddl_engine_version` at **2 / 3**.

### 2026-07-30 — The client app implementations are not sent to the development server (**no version**; operations and build context only)

The development server still held `android/` at 174M and `macos_swift/` at 587M. Both had been rsynced once in May or June and had gone stale there. What was removed declared `1.48.0-android.1`; the Mac is at `2.1.3-android.1`.

- **That machine cannot build either of them.** It has no JDK, no gradle, no Android SDK and no Swift toolchain; both are built and tested on the Mac. Neither directory was referenced by the systemd units, their drop-ins, `compose.yaml` or `deploy/`.
- **Most of the bulk was build output.** Of the 174M in `android/`, 168M was `app/build/` intermediates plus a stale `app-debug.apk`; of the 587M in `macos_swift/`, 577M was a macOS index store. The sources were compared against the Mac and **not one file existed only on the server** (the 12 files under `macos_swift/` were hash-identical).
- **A third copy (1.9M) sat in the bench container source tree.** All three were removed.
- **The exclusion was written down permanently.** `android` and `macos_swift` were added to `.dockerignore`, and the standing rule was placed in three operational documents. `server/Dockerfile` and `web/Dockerfile` `COPY` `shared/`, `server/` and `web/` by name, so **the image contents are unchanged**; what shrinks is only the context sent to the Docker daemon.
- **`macos_swift/` is not in Git at all** (`.git/info/exclude`). Its only copy is the Mac working tree, so **the server copy was never a backup**.

### v2.9.9 — The machine's notes leave the color channel (Build 780, 2026-07-30)

Stage 1-A of the color catalog work. **`color_hint` had been carrying four roles at once** — a color description, coerce's idempotency guard, the renderer's own effect annotation, and a descriptive marker. Only the machine-written diagnostics move, into a new `Instruction.note`.

#### What was separated, and what stayed

- **85 of the 92 write sites moved to `note`** (72 in compose, 3 in normalize, 10 in the API). **The 7 that stayed are descriptive markers** (`soft light`, `scent layer`, `waiting buds`, `five-sense presence`, `membrane haze`, `reflection`, `fading`): the renderer reads those as the character of the drawing, not as a diagnostic. **A field's roles are counted by its readers, not its writers.**
- **The 20 read-back guards followed.** A branch that read `color_hint` to stay idempotent would, if left behind, stack the same diagnostic twice on the second coerce.
- **`note` is declared second.** An optional field's fill rate follows its declaration position monotonically and **rises toward the tail** (measured: 0% at position 0, 89% at position 23). `note` is a field the model **must not** fill, so the rule was used in reverse and it was put at the front; both prompts also state that Stage 2 never emits it. `thinness` stays last, untouched.
- **Instructions carrying `color_hint` in new work fell from 74.7% to 7.6%.** That 7.6% **equals the share of instructions that actually carry a color description** — what remains is only what talks about color. **The 2825 cases where a diagnostic had misfired color resolution are now 0.**

#### Only the color moved

- **Across the 14 cases that traverse coerce: the performance seed is unchanged in 14/14, the path geometry (a digest of the `d` attributes) is unchanged in 14/14, and the color attributes moved in 6.** `color_hint` moved in 8 of them, and **in 2 of those the color did not change** — the diagnostic had not hit a color word, so nothing had misfired there.
- This holds because of the **seed allowlist** introduced in engine 15. Up to engine 14 the seed came from an instruction's whole dump, so **editing `color_hint` alone moved the strokes**. It is now an allowlist of 20 fields, and `color`, `color_hint` and `note` are all outside it.
- **So "if the strokes moved, it is not the effect of 1-A but an accident" is a usable discriminator.** Perturbing `note` into the allowlist turns `test_seed_payload` red.

#### The corpus could not see the subject of this change

- **Acceptance found one missing discriminator.** The implementation added a projection to the DDL corpus generator that folded `note` back into `color_hint`, **keeping the frozen files byte-identical**, on the grounds that machine-only diagnostics belong outside the DDL engine identity.
- **With the projection removed, all 14 coerce cases of `ddl-engine-3` and the manifest moved.** The contract said a byte-identical corpus was the correct outcome, but **that is true only of the render corpus** (which never calls `coerce_score`); **the DDL corpus does traverse coerce**.
- **What settled it: each frozen file already pins `branch_report` with its 34 coerce branch counters.** Machine diagnostics are part of this artifact by construction, so there is no ground for keeping one of them out.
- **Regressing the write channel back to `color_hint` left `check_frozen_corpora.py` green while the projection stood.** Since **CI runs corpus regeneration and not one test**, that meant CI was blind to the whole subject of this change. With the projection removed and the 14 files plus the manifest refrozen, the same perturbation turns **red, naming 6 files**.
- **`DDL_ENGINE_VERSION` stays 3.** What moved is the recorded output, which is what "freeze what moved" means. **The render corpus (`render-engine-16`, 365 cases / 333 SVG files) is byte-identical.**

#### The build number skipped

**777, 778 and 779 were taken by parallel branches, and 778 and 779 were each written by two of them.** This version takes 780. **The counter is shared, not per branch — and it moves between measuring and claiming.** This version had already been numbered 779 and written into the documents when a re-measurement just before deployment found the development host sitting at 779 (written by another session at 08:04:50), so it was renumbered to 780. **Measure again immediately before deploying.**

#### Verification

server **1695 passed / 31 skipped** (+27), cli 76, ruff clean, `npm run check` 219 files / 0 errors / 2 warnings, `check_frozen_corpora.py` byte-identical, `check_docs.py` green.

**The implementing session's perturbations were 112/112** (92 writes, 20 read-backs). **The accepting session applied five of its own and all five went red** (adding `note` to the seed allowlist, regressing the write channel, regressing a read-back guard, moving the declaration to the tail, and the corpus blind spot). **The fifth did not go red, so the corpus was refrozen on the spot.**

**The version is a patch.** The schema gains an optional field defaulting to `None`, and stored Scores validate with or without it (`extra="forbid"` does not trip on an addition). The render engine stays at **16** and `ddl_version` / `ddl_engine_version` at **2 / 3**.

### v2.9.10 — The stopped machine is let go, and a model is recommended for the stage it was measured at (Build 781, 2026-07-30)

Ledger [I-056], plus per-stage recommendations for the local LLM models. **OVMS (Intel OpenVINO Model Server) was retired as a provider on 2026-07-30** — its endpoint had stopped serving models while still answering `/health`, and the models it offered are reachable through Ollama instead.

#### A retired provider takes part in naming, not in routing

- **Removing it from the built-in list does not remove it from an installation.** An unknown provider id is preserved as though an operator had added it by hand, and the metadata refresh that `MODEL_CONFIG_VERSION` triggers sits inside `if builtin`, so it never reaches it. A withdrawn id is now named in **`RETIRED_PROVIDER_IDS` and dropped at the entry of `normalize_model_settings`.**
- **It stays in reference splitting and label lookup, though.** Six works record an OVMS model, and **five of them carry the qualified string `ovms:gemma3-4b-api`** (one carries the bare `gemma3-4b-api`). Drop the retired id from splitting and those five display as "NVIDIA NIM / ovms:gemma3-4b-api", which is **worse than showing the id alone**. It is not listed in the ownership table (rule 2 of model reference resolution), and `connection_for` raises `ValueError` for it.
- **Two live landing places the ledger did not know about were removed** — a literal `"qwen-api"` in the demo instruction generator in `api.py`, and `/no_think` in `interpreter.py`. Both named OVMS models, so an unconfigured demo was asking a withdrawn provider for its instruction. Three copies of the dead old routing (composer, interpreter, trainer) went with them.
- **`OPENAI_MODEL` and `OPENAI_MODEL_STAGE1` lost their last reader**, so they were removed from both compose passthroughs and from the development host's `.env`. **`INKU_LLM_BACKEND` stays** — removing it makes the default anthropic, which falls onto a path with no key.

#### One number cannot say that the two stages disagree

- **The local Ollama models were measured per stage, and the two stages disagree.** The pair inku recommends is a Stage 1 model that covers 32% of Stage 2 and a Stage 2 model that breaks Stage 1 in English. `recommendation_stage1` and `recommendation_stage2` were added.
- **The stage values do not replace `recommendation_llm`; they narrow it.** A model with no stage value reads the existing value for both stages, so the **8 cloud and 32 NVIDIA models measured end to end are unchanged and no migration is needed**.
- **The settings UI already had Stage 1, Stage 2 and shared tabs, yet folded both stages into the same `'llm'`** (`SettingsModal.svelte`). Ordering reads the stage too, and the shared tab takes the lower of the two.
- **Three places listed the metadata keys** (normalization, the version-bump refresh, and the carry-over on re-fetch). A key added to one and forgotten in another disappeared silently, so they were collapsed into **one `MODEL_METADATA_KEYS`**.
- The hover card shows `Recommended / Stage 1` and `Recommended / Stage 2` only for models measured per stage. **A model measured end to end keeps one line** — two would print the same stars twice and imply a measurement nobody made. Vision is not split. The decision moved into `modelStageRecommendations()`, **which can be checked without drawing anything**.

#### A tautological test, and a sample with no discriminating power

- **One of the implementing session's perturbations missed.** Removing the two stage keys from `MODEL_RECOMMENDATION_KEYS` left 22/22 green. There were two causes, and both are the shape where **the check supplies its own answer**.
  - **It was tautological** — `for key in MODEL_RECOMMENDATION_KEYS: assert key in MODEL_METADATA_KEYS` **compared a list against itself**. Delete from the constant and the loop stops running. The expected keys are now written out in the test.
  - **The sample had no discriminating power** — the refresh check had **not given the stored settings the keys at all**. The `{**builtin, **stored}` base merge was supplying the answer, and `metadata_keys` was never traversed. The sample was replaced with one where **the stored value is a stale 1 and the catalog says 5**.
- **This also found one error in the contract.** "A key not added to `metadata_keys` is not refreshed even when the version rises" is false: it only bites **when the stored settings hold an older value**.
- **A guard left by a predecessor was rewritten, not deleted.** `test_recommendation_levels_stay_absent` said "do not add recommendations until the method is measured; if you do, delete this test." **It was replaced by one that points at where the method now lives** instead.

#### Version and verification

**The version is a patch.** Retiring a provider is not a format change to stored data (the retired id is dropped on read), and the stage keys are additions that need no migration. **`MODEL_CONFIG_VERSION` goes 2.4.0 → 2.5.0** — two metadata keys were added, so this is not a change of values alone. The render engine stays at **16** and `ddl_version` / `ddl_engine_version` at **2 / 3**. No deterministic layer was touched, so both frozen corpora are byte-identical.

server **1732 passed / 31 skipped** (+37), cli 76, ruff clean, `npm run check` 219 files / 0 errors / 2 warnings, `npm run lint:i18n` 918 / 47 / 0 / 0, `npm run lint:models` 68 checks, **`npm run lint:recommendations` 37 checks (new)**, `check_docs.py` green. **`lint:recommendations` joins the local checklist** — CI runs corpus regeneration only, so CI is unchanged.

**The implementing session applied five perturbations** (removing the retired id from the shared key list, 2 red; the shared tab as `Math.max`, 3 red; ignoring the stage and returning `recommendation_llm`, 6 red; dropping the split condition, 3 red; dropping the vision exclusion, 1 red). **The accepting session applied one per stage, independently, and all three went red** (`RETIRED_PROVIDER_IDS` emptied → 9 red; the two stage keys removed from `MODEL_RECOMMENDATION_KEYS` → 2 red; `modelStageRecommendations()` forced to `null` → `lint:recommendations` 2 red). **The second of those is the perturbation that had missed; once fixed, it goes red.**

#### The build number did not skip

**This branch used 777, 778 and 779, and main reached 780 while it was open.** This version takes 781, and the three branch numbers survive only inside its commits. **The counter is shared, not per branch.**

### v2.9.11 — The abstract colors go from six words to nine, and yellow gets a way out (Build 782, 2026-07-30)

Score's `color` gains **`yellow`, `orange` and `purple`**. **Catalog palettes already held twelve yellows, a nominal 13.6%, yet the yellow actually drawn was 0.6%** — there was no word to leave by. The order of the existing six is untouched; the three are appended.

**`color` keeps declaration position 17 in a 25-field tool schema.** An optional field's fill rate depends on where it is declared, but `color` is required, so its position does not drive carry. It was still left alone, because the prior measurement was taken at that position and the arms have to stay comparable.

**Two rules were added to Stage 2's prompt** (sunlight, harvest, metal and lamplight → yellow/orange; dusk, twilight and shadowed flowers → purple; plus "the three are peers of the other abstract colors"). **Without the rules `orange` stays at 0.6%** — in the prior measurement the schema-only arm gave `yellow` 7.6% / `orange` 0.6%, and the arm with the rules gave 8.5% / 2.4%. Measured after implementation over a fixed 60 inputs: Japanese `yellow` 13.7% / `orange` 6.0%, English 6.5% / 3.0%, new words together 19.7% (ja) and 10.1% (en) — past the acceptance thresholds (yellow 5%, orange 1%, together 8%) in both languages. **Instruction totals moved -0.8% (ja) and +5.7% (en)**, so the "carrying it thins the Score" effect seen with `thinness` did not recur.

**`purple` is deliberately not an acceptance condition.** Across 821 distinct production inputs, purple-leaning demand is 7 (0.9%), and only 3 of the 60 sampled inputs lean purple, so the rate carries no discriminating power. **Zero purple in Japanese is not treated as a fault.**

**The saijiki's colors gained the three words as well**, which puts yellow, orange and purple into Stage 1's vocabulary listing — **the description language's own vocabulary grew**, so `ddl_version` moves **2 → 3**. Holding it at 2 was considered, but `ddl_version` rose from 1 to 2 because "thinness became a word independent of the tool name; the version rises when the vocabulary grows", and holding a change of the same shape would contradict that precedent. **The contradiction came from `docs/spec/render-engine-history`, whose "incremented when" column read "grammar is added, changed, or retired"**; that clause now reads "vocabulary is added, changed or retired, or grammar is".

**Coercion was widened in the same stage.** `COLOR_MARKERS` gained three entries per language. **Without them the new `ddl-engine-4` corpus would be an exact copy of `ddl-engine-3`** — measured before the contract was handed over, changing only the schema and the saijiki and running both generators moved neither corpus by a byte. **This change widens Stage 2's exit, but the corpus never calls Stage 2** (it takes DDL strings as input), so unless the color words reach coercion this layer cannot see the work.

**`renderer.COLOR_MAP` gained a default for each new word** (`yellow` `#a18308`, `orange` `#a95a00`, `purple` `#583a84`). The first line of `_resolve_color` is `cmap[color]`, so without them a new word raises `KeyError`. The drafted design was a `FALLBACK_TO_SIX` that rounded yellow and orange to `red` and purple to `blue`, but **Stage 2 emits `yellow` 8.5% of the time, so rounding means "every yellow chosen becomes more red"**. Red is 44.6% of what is drawn and **lowering that is the point of this stage**, so the interim measure would have pointed the opposite way. The three hexes sit in the same register as the existing chromatic three (L 0.42–0.62, C 0.12–0.13), and **a test pins that the renderer's own classifier `_hue_from_hex()` sorts each one back into its own word**. **The eleven catalogs' `map` tables are untouched**, so every catalog draws the same yellow; a per-catalog yellow is stage 1-C's work.

**`ddl_engine_version` moves 3 → 4 and `ddl-engine-4` is frozen at 33 cases** (`a_expand` 15, `b_coerce` 18). `changed_from_previous` is exactly the four new cases, and **the twenty-nine older ones did not move by a byte**. **`render-engine-16` (365 cases, 333 SVG) is byte-identical** — proof that adding three lines to `COLOR_MAP` changed no line of how the existing six resolve.

#### One frozen behavior did move

**H-01 in `server/tests/golden/coerce_golden.json` moved.** Its DDL literally says "small yellow crayon squares": `with_color_delivery_repair` went 0 → 1 and `color_cycle` went `["red","black"]` → `["red","red","black","yellow"]`. **That is exactly what this change is for** (yellow became readable), and `gen_coerce_golden.py --refreeze` is the generator's sanctioned path. The duplicated `red`, however, is not from this change — **`_with_color_cycle_delivery` inserts `base_color` at the head of the cycle unconditionally, while the lines two and four below it do check for duplicates.** Filed on the ledger.

#### A check was supplying its own answer

**One perturbation applied during acceptance found a shape the implementing session's six had not.** Make `_resolve_color` return `cmap["black"]` for yellow, orange and purple only — **the regression that erases this version's visible effect**. **All 1751 tests stayed green.** The cause was in the new test `test_all_catalogs_resolve_all_nine_colors`, which **compared the keys of its own comprehension against the list those keys came from**, so it held whatever `_resolve_color` returned. Pinning the values, and requiring the three new words to classify back to themselves through `_hue_from_hex()`, turns the same perturbation **11 red** (one per catalog). **`render-engine-16` being byte-identical does not close this hole** — no case in that corpus uses a new color.

#### Staffage does not follow the new colors (a pre-existing hole)

`ddl_expander` keeps its own six-word color tuples (`_JA_COLORS` / `_EN_COLORS`), separate from `COLOR_MARKERS`, and `_dominant_ja_color` reads them to pick the staffage's main color. **Measured over 60 seeds, yellow, orange and purple get their own color 0/60 times and fall to black every time** (red 48/60, green 46/60). **This is not a hole this version opened** — reading the development server's database, **19 of 282 stored DDL strings already contained "黄色い" before it**. Stage 1 was writing yellow whether or not the vocabulary listing offered it; what changed is that **the yellow now reaches coercion and survives into the Score.** The staffage side is filed on the ledger.

#### The Android copies are two versions behind

`pipeline/ServerScoreCoercer.kt:64` holds a six-word set and **silently rewrites anything else to `black`**. `pipeline/ServerScoreSchemaJson.kt:5` is a frozen copy of the tool schema whose `Instruction` has **24 fields, `thinness` at 14, and no `note`** — neither [I-036] nor v2.9.9's `note` reached it. **This version did not create that lag**, so it is not chased here; it is handed to ledger item [I-029].

#### Perturbations

**Six from the implementing session** — the three words removed from `Color` (6 red); the prompt additions reverted (2 red); the three words removed from the saijiki (17 red); the three removed from `COLOR_MARKERS` (generator exit 1, 5 files moved); the three defaults removed from `COLOR_MAP` (11 red); `yellow` set to `red`'s hex (1 red). **The accepting session** reproduced the `COLOR_MARKERS` perturbation independently, confirming **exactly five files** (four `b_coerce` cases plus `manifest.json`) and the generator's non-zero exit, and then applied the `_resolve_color` perturbation above.

### v2.9.12 — The catalog's `palette` reaches the drawing (Build 783, 2026-07-30)

**Each of the eleven catalogs holds eight named `palette` entries, and the only path by which they
reached the drawing was substring matching on `color_hint`.** That description channel is nearly
empty: of 7463 stored instructions, only **945 (12.7%)** carry a color word in the segment Stage 2
wrote. The other 87% ended at `cmap[color]` — the catalog's six-key `map` plus the three defaults
v2.9.11 added. **This version builds a deterministic path from the `palette`.**

**The assignment is computed once per work, and its only inputs are `(render_seed, catalog_id,
abstract color)`.** The full instruction dump is not used: with it, editing `color_hint` alone
would change the color and confound any A/B. `performance_seed` is not used either — **color is a
property of the work, not of the performance.** The six chromatic words are classified by **OKLCh**
hue band (**CIELAB puts pure blue at 306° next to pure magenta at 328° and cannot separate blue
from purple**). The three achromatic roles **first reserve the candidate whose hex equals their own
`map` value** and then take the rest by nearest L — the naive "highest / lowest / middle L" the
contract drafted **collapses white and black onto one hex in the five catalogs holding fewer than
three achromatic entries** (`desert_mineral` holds one). The background goes through the same
assignment.

**`catalog_id` now reaches the renderer**: the identifier did not appear in `renderer.py` even once
before. Four files carry it — the two calls in `api.py`, `RenderEngine.render()`,
`DefaultRenderEngine` and `render()` — and omitting it means `DEFAULT_COLOR_CATALOG_ID`.
**`_hint_hues` now matches ASCII on word boundaries** (CJK keeps substring matching, having no word
boundaries) and **five tokens that are not words were dropped** — `blu` and `ai` (blue), `vert` and
`tall` (green), `shu` (red) — stopping 166 `vertical`, 20 `constraint` and 13 `blur` misfires.
**Genuine French `vert` becomes unreadable too**; stopping the misfires was chosen over keeping it.
`brown` has no band of its own and is sent to `orange`.

#### Without extending the case table nothing would have moved

**All 365 cases of `render-engine-16` held zero `palette:` keys, zero `color_hint`, instruction
colors of only `black` (364) and `green` (1), and a `white` background in every case.** The
resolution chain finds neither a description nor a candidate set, falls to `map[color]`, and
**produces byte-identical output even though the work does traverse the layer.** By the author's
decision the case table was extended with **110 group F cases** (11 catalogs x 9 abstract colors,
six description cases, five non-white backgrounds). **110 moved, 365 unchanged**, and the unchanged
side is this version's boundary: a call that gets only the six-key `map`, holds no `palette:` key
and no `color_hint`, and draws on `white` produces the same picture as engine 16.

**The meaning of the manifest's `color_map_digest` was changed.** It used to be the digest of the
generator's own six-key `DEFAULT_COLOR_MAP`, so **changing `renderer.COLOR_MAP` never moved it**
(v2.9.11's three new words passed with the digest unchanged). Group F gives each case its own
`color_map`, so it is now taken over the **set of `(case_id, catalog_id, color_map)` for all 475
cases**. **Reading frozen SVG alone lets an identity-assignment perturbation pass**, so a test was
added that re-performs all 110 group F cases through the live renderer and compares digests.

#### What it reaches (no more color; more achromatic)

Measured over 1847 stored works and 7463 instructions on the **surface v2.9.9 produced when it moved
diagnostics into `note`**: **`palette` entries never chosen 12 → 6 / 88**, **distinct resolved hexes
76 → 82**, **color decisions from a misfire 148 → 0**, **achromatic share of what is drawn 57.9% →
61.4%**. The band is decided by the abstract color and **69.5% of the abstract colors in stored
works are achromatic**, so **what moves is which `palette` entry gets used, not the distribution of
bands.**

#### Eight roles that dissolve into the paper (not fixed here)

**Roles within ΔL 0.15 of the paper went from 0 / 88 under engine 16 to 8 / 88.** Seven are yellow
and orange, because those two bands are light in the catalogs. **The eighth is a regression**:
`black` in `cool_material` moves from `#2c3e50` (L 0.356) to `#e5e8e8` (L 0.929) and its ΔL against
the `#fcfcfc` paper falls **0.635 → 0.062**. That catalog's own black has chroma 0.039, **just past
the 0.035 achromatic floor**, so it is not an achromatic candidate and the one remaining candidate
is taken by the nearest-L rule, **which has no distance limit**. In production `cool_material` holds
**102 works and 412 instructions, 205 of them (49.8%) `color=black`**, over 76 white and 19 black
backgrounds. `yellow` in `desert_mineral` lands on the **same hex** as the paper (ΔL 0.000).
**A check that compares hexes alone passes both**, since the three roles do stay distinct from one
another. **The regression is in the contract's design, not a deviation by the implementation** — the
contract's warning looked only at hexes being equal and never at the lightness distance. **By the
author's decision of 2026-07-30 it ships unfixed and is handled in stage 2** (ledger item [I-062]).

#### Perturbations

**Three on the implementation side** — restore `work_assignment` to an identity map, restore ASCII
matching to substrings, restore the achromatic rule to "highest / lowest / middle L". **Four more
were applied independently during acceptance and all four went red**: the identity map (13 tests),
**removing `catalog_id` from the seed material** (6), moving the achromatic floor 0.035 → 0.05 (4),
and killing the nearest-hue fallback for an empty band (10). **The second checks whether
`catalog_id` really enters the seed**, and none of the implementation's three look at it: the new
`test_catalog_id_participates_in_multi_candidate_choice` passes on catalog `palette` differences
alone, so an implementation that ignored `catalog_id` would stay green.

pytest **1771/31** (+20), cli 76, ruff clean, `npm run check` 219/0/2, both frozen corpora
byte-identical on regeneration. **Android stays at engine 16** (ledger item [I-029]). **The version
is a patch**: an engine version rises, and no stored data changes shape.

---

### Android names its engine version in one place (android Build 148090, no version, 2026-07-30)

**Android held the engine version string in three separate places, and the two values disagreed.**
The renderer that writes the drawing metadata (`DefaultSvgRenderer`) and the `renderHash` fallback
(`LocalFallbackPipeline`) both said `"16"`, while `CompatibilityConstants` — **the one the version
panel reads** — still said `"1"`. The catch-up to engine 16 (ledger item [I-029], finished
2026-07-29) had left the displayed value behind. The three now resolve to `CompatibilityConstants`,
and its value is the one the implementation actually is: `16`.

**The value itself did not move.** The engine version is **material for the edition identity
`rh3`**, so moving it away from `16` would stop matching the identities already stored. What
changed is the displayed version, `1` to `16`; the metadata JSON and every `renderHash` are
byte-identical (`Engine16VersionTest`'s metadata assertion and `ServerScoreParityTest`'s four
pinned `rh3` values stay green). `renderEngineId` was split the same way, so it moved to the same
constant while keeping the value `"default"`.

**None of the existing 99 tests ever read that constant** — they all stayed green with it set to
`"1"`, so **nothing was watching the very value this change repairs**. A test pinning the literal
supplies the discrimination. **An agreement check alone would not**: once the display and the
metadata read the same constant, it is true whatever the constant holds. Measurement confirms it —
setting the constant to `"17"` turned `testCompatibilityConstantsDeclareEngine16`,
`testRendererMetadataDeclaresEngine16` and `testRenderHashDefaultsMissingAndBlankMetadataToEngine16`
red, while the agreement check `testUiConstantsMatchRendererMetadata` **stayed green**. It is kept
in that knowledge: it earns its place only if the two ever stop being wired together.

**The fallback mechanism itself was not removed** (author's ruling). Both callers of `renderHash`
receive metadata produced by `renderer.render()`, so that default is unreachable today. That the
server side (`db.py`) carries no such default remains ledger item [I-011]. **[I-012] — the version
panel reading `1` — is closed.**

Android unit tests **101 / 0 failures / 0 errors / 0 skipped** (99 at the start, plus two).
**`APP_VERSION`, `web/BUILD_NUMBER`, `android/VERSION` and `android/BUILD_NUMBER` all stand still**:
the change is Android-only, and no packaging task ran, so Gradle's automatic increment never fired.
**Nothing was deployed** (`android/` is permanently excluded from every server sync path).
`server/`, `web/`, `cli/` and `shared/` have no diff.

**`ANDROID_SPEC` has not followed.** Its opening status still reads `2.0.0-android.1` / engine
`11`, five versions behind what the tree holds (`2.1.3-android.1` / engine 16). Ledger item [I-013]
recorded this as "not caught up to engine 15"; **the actual distance is larger.**

---

### Android `2.1.4-android.1` — the drawing layer catches up to render engine 17 (catalog palette assignment, nine abstract colors) (android Build 148090 unchanged, 2026-07-31)

**The part of engine 17 the port shares with the server is ported, and Android now names render engine 17.** Tests went from **110 / 12 failures to 112 / 0**.

- **The gap was not engine 17 alone.** Four deterministic-layer changes landed after the reference corpus was frozen on 2026-07-29: `thinness` moved to the end of the declaration (`2125b82`), `note` was added (`b484f3f`), the abstract colors grew to nine (`74bf869`), and engine 17 arrived (`9090973`). **The contract split those four into stages.**
- **Stage 1, seed:** the full dump (`surfaceSeed`) gains `note` and moves `thinness` to the end. **The allowlist dump (`serverInstructionJson`) keeps neither** — the server's `_SEED_INSTRUCTION_FIELDS` has no `note` and keeps `thinness` next to `weight`. **Aligning both would move all 30 reference SVGs.**
- **Stage 2, vocabulary:** the three schema enums (`color`, `background`, `color_cycle`) and the coercer's allowlist go to nine words, and the DDL markers gain yellow, orange and purple.
- **Stage 3, assignment:** the OKLCH conversion, the six hue bands, the achromatic contest and the **big-endian unsigned 64-bit** SHA-256 choice are ported, and the old scoring `resolveColor` is gone. ASCII hint tokens now match as **whole words**, and five tokens leave `HUE_HINTS` (`blu`, `ai`, `vert`, `tall`, `shu`).
- **Stage 4, material layer:** `pen` had no material layer on the **line** primitive. `usesMaterialOutline("pen")` returns true, but the line path's tool set omitted it — **two places read the same property and disagreed**. **No corpus case was a pen line, so nobody saw it through engine 16.**
- **Stage 5, prompts:** the server's four constants are synchronised whole (`STAGE1_*` at 18,963 / 17,956 bytes, `STAGE2_*` at 44,116 / 42,191). The `*_LITERT` pair stays out.
- **Stage 6, version:** one place (`CompatibilityConstants`, consolidated on 2026-07-30). **Zero** occurrences of `"16"` remain as an engine version.
- **The catalog contents (`ColorCatalogs.kt`) are out of scope.** The premise recorded when the item was filed — "the server has nine keys, Android six" — **was wrong: the server's eleven catalog maps are six keys too** (the nine belong to `renderer.COLOR_MAP`, the default the catalogs override). **The engine 17 catch-up touches no catalog table**, so it does not collide with the engine 18 replacement.
- **The six surface textures (`stipple`, `grain`, `paper_grain`, `wash`, `aquatint`, `bleed`) are not implemented** ([I-043]). **Declaring the version on a partial implementation** is the same treatment engine 16 got.

**The test surface was baked before the contract went out.** All 32 existing cases carry **no `color_hint`, only the word `black`, and no `palette:` key**, because the generator called `renderer.render` without a `color_map` or a `catalog_id`. **A port could declare `"17"` without writing a line of the mechanism and stay green.** Worse, **the existing tests compare paths, points and dashes — nothing compared a color** — so adding cases would not have been enough. What was baked: `renderer_color_assignment.json` (11 catalogs x 9 colors x 2 seeds, plus 91 OKLCH conversions, the bands, and 15 hint resolutions), `score_schema_contract.json`, six SVG cases (one per branch of the assignment), and the nine tests that read them.

**Acceptance re-ran and perturbed rather than copying the report's numbers.** All 110 cases were run to confirm 0 failures, and **six perturbations — one per stage** — each turned the intended assertion red (reverting the dump → `test06SurfaceHatchExactParity` and the reference walk; the coercer back to six words → `ServerScoreVocabularyTest`; the version back to `"16"` → three in `Engine17VersionTest`; unsigned remainder to signed → five assignment tests; removing `pen` → case `38` in the walk; one character in a prompt → `PromptFingerprintTest`). **Only the report's account of stage 1 disagreed with measurement** — it says reverting the dump reddens `ServerRendererThinnessTest`, but that test reads the schema, not the dump.

**Acceptance found two defects, neither of which had a gate; both gates were added first, then the defects fixed** (author's decision).

- **Two OKLab coefficients came from a different published variant** (`0.0040720403` / `0.8086758033` → `0.0040720468` / `0.8086757660`). **No test opened the `oklch` block the corpus already carried**, so it passed. Once one did, 233 values disagreed. **No assignment moves with today's eleven catalogs** — the difference is 6.5e-9 in L, one twenty-thousandth of the smallest margin to a decision boundary (8.8e-4 to the chroma floor, 0.80 degrees to a band edge). **engine 18 replaces every catalog color, so what needed pinning was the constants, not their consequences.**
- **`render_color_map` in the metadata carried the assigned colors.** The drawing's map, with the assignment folded in, went straight into the metadata: **three keys were added to all eleven catalogs and a value was overwritten in four** (`cool_material.black` `#2c3e50` → `#e5e8e8`, `sea_stone.blue` `#005bae` → `#191970`, plus `fresco_study.red` and `weathered_heritage.white`). **The server's `render_color_map` stays the catalog's own map plus its palette, fourteen keys, untouched by the assignment.** **This parity held through engine 16 and was broken by the change.**

- **[I-062] (`cool_material`'s black sitting 0.062 from the paper) is not fixed.** It is the server's current engine 17 behavior, and the port reproduces the server faithfully.
- **Only `android/VERSION` was raised.** `APP_VERSION` (`v2.9.12`), `web/BUILD_NUMBER` (783) and `android/BUILD_NUMBER` (148090) are all unchanged, and **no pentala deployment is needed**.
- **Verification:** Android **112 tests / 0 failures / 0 errors / 0 skipped** (25 XML). In the merged main checkout: server **1771 passed / 31 skipped**, cli **76**, ruff (`src tests scripts`) clean, `npm run check` **0 errors / 2 warnings / 219 files**.
- **Left:** `ANDROID_SPEC.ja.md` / `.md` have **not caught up even to engine 15** ([I-013]). Out of scope here.

### Android `2.1.4-android.2` — only what a screen calls survives (tooltip, display mode, mascot, staffage level, lineage tables) (android Build 148090 unchanged, 2026-07-31)

**Two implementation passes were sent back; the git session then fixed the branch and merged it** (author's call).

- **Eleven composables had no caller.** Four (`ProvenanceTooltipTarget`, `UiModeContainer`, `MascotWidget`, `TenkeiSelect`) are now called from the screens; seven (`CustomModalContainer`, `ToastQueueWidget`, `ConditionChipsContainer`, `LineagePanel`, `UnreadWordsPanel`, `AIRefineModal`, `ManualRefineModal`) were deleted, along with the **three features the contract never asked for** (modal scrim dismissal, a toast queue, collapsible condition chips)
- **The display mode and the mascot now change what is drawn.** Both settings already persisted to Room and were restored on launch, but nothing in the product read them, so they could be chosen and nothing happened. `ComposeScreen` switches on `UiModeContainer`, and the mascot and the condition strip appear only in the full mode
- **Staffage is a level, not a motif.** `TenkeiOptions` now mirrors the three levels in `web/src/lib/tenkei.ts` (`none`, `sparse`, `auto`); the implementation had invented a list of motifs (`moon`, `cloud`, `bird`, `mountain`, `water`). **The chosen level now travels through `PaintRequest.tenkei` to `WebDdlExpander`** — two call sites in `LocalFallbackPipeline` were passing the default
- **Dropped a recommended model that exists in no catalog** (`qwen/qwen-2.5-coder-32b-instruct` appears in neither server, web, nor the Android catalog). The remaining three ids are real
- **`lineage_nodes.history_id` is TEXT.** It had been baked as `Long?` / INTEGER and could never join against `history_items.id`, which is TEXT
- **The migration test opens a real database now.** The two it replaces read `startVersion` / `endVersion` off the Migration object without touching the SQL, and the constraint test built two data classes and compared them, so `uq_lineage_primary_parent` never ran
- **Added `androidx.room:room-testing`.** A transitive BOM pins `kotlinx-serialization-core` to `strictly 1.7.3`, which fails at runtime against room-testing's 1.8.1 generated serializers (`AbstractMethodError`), so **the androidTest configurations force 1.8.1**
- **Only `android/VERSION` moved** (`2.1.4-android.1` to `2.1.4-android.2`; the implementation had raised it once per stage, to `.11`). `APP_VERSION` (`v2.9.12`), `web/BUILD_NUMBER` (783) and `android/BUILD_NUMBER` (148090) are unchanged, and **no pentala deployment was needed**

#### Perturbations (aimed at the product)

The previous two passes only rewrote test expectations, so **the product code was perturbed four times** to watch the intended gate turn red.

- put `moon` back into `TenkeiOptions` — `tenkeiOptions_areExactlyTheThreeWebLevels` red (unit)
- return `history_id` to `Long?` / INTEGER — three migration tests red, the other seven green
- drop `UNIQUE` from `uq_lineage_primary_parent` — three migration tests red
- **without changing the schema**, add `DELETE FROM history_items` to the migration — **only the two tests that read history rows go red**, the constraint test stays green, so the bodies are what catch data loss

#### Not fixed here

- **The core of stage 6 is still missing.** There is no colophon anywhere in Android, no table matching `unread_words`, and no wiring that records a refinement as an edge in `lineage_edges`. What remains is the eleven-kind table (`DerivationKind.kt`) and its test
- **Nothing uses the lineage data layer.** `LineageDao` and `HistoryItemEntity.lineageNodeId` are declared but never called from the repository or the view model; the tables and the migration are correct, but no row is ever written
- **`TooltipTest` does not read the arguments at the product's call site.** `CanvasHeroCard` calls `ProvenanceTooltipTarget` now, but the test calls it directly with its own strings
- **No test watches `state.selectedTenkei` arrive at the expander** — the type threads through, but the path is not gated
- **The duplicate mascot settings** (the existing Kiwi / Crab beside the new Incu / Yuragi) are left alone, pending [I-066]

---

### v2.9.13 — several works become one loop (Build 789, 2026-07-31)

**This version integrates five independent branches** (Builds 784-788). At its center is **animation export for multiple works**: `POST /api/history/export-animation` lays saved SVGs end to end and encodes one APNG or GIF.

**There are two call sites, and they order the works differently.** History management takes the checked works by ascending `at` (ties by id), oldest first; lineage walks parents up from the selected work and reverses, so the sequence runs **from the origin to the selected work**. Neither button is enabled below two works.

**The requested order survives on the server.** `db.get_items` fetches rows with `id.in_(ids)` and re-sorts them by each id's position in the requested list, not by the database's return order. The endpoint drops duplicates with `dict.fromkeys`, checks ownership, and **returns 409 if any work has no saved SVG**.

**The settings live under Settings > Export and persist in localStorage under `inku-animation-export-settings`.** Formats are APNG (lossless) and GIF (256 colors); the transition is one of **cut, crossfade, fade through white, horizontal slide**; the display hold runs 0.1-30 seconds; the resolution (y-axis) is 1K = 1080 px, 4K = 2160 px, 8K = 4320 px. **The transition frame count falls with resolution** (1K = 6, 4K = 4, 8K = 2). Total encoded pixels are capped at **600,000,000**; past that the endpoint returns 400.

**Rasterization still goes through the existing `svg_to_png` (resvg).** The new dependency, **Pillow 12.3**, only composites, blends and encodes PNGs that resvg has already produced (the four `cairosvg` guards are untouched, and `animation_export.py` does not import `cairosvg`).

#### The four that rode along

- **The lineage tree pans when its empty space is dragged** (Build 784). Primary mouse button only, and never starting on a card, button, input or menu item. `.lineage-scroll` gained `role="region"` and `aria-labelledby`
- **The description tab's result log remembers whether it was open** (Build 785), under `inku-result-log-open`
- **Three history panel settings left Settings > Misc** (Build 786). **The behavior is fixed at the former defaults**: a re-edit always saves as a new version, and selecting from history overrides neither the canvas size nor the color catalog. Six i18n keys and the `HistorySelectionBehavior` type went with them
- **An i mark beside the generation label** lists the eight things auto-repair does (Build 787)

#### What acceptance measured

**The nine web files in the merge result are SHA-256 identical to the composite the author approved by eye and pentala is running.** Every conflict was between the five branches themselves (`web/BUILD_NUMBER`, `+page.svelte`, `SettingsModal.svelte`, three i18n files), and **the 32 commits between the branch point `0505961` and main touch none of those nine files** — the one file they do touch, `server/scripts/gen_android_reference.py`, does not overlap this version's server changes.

**All three perturbations turned exactly one test red**: (1) breaking the requested order into `sorted(set(...))` reddened `test_history_animation_export_preserves_requested_order`; (2) **a shape-preserving, data-only** reversal of the frame list — same frame count, same format — was caught by the pixel assertion in `test_builds_looping_apng_in_input_order`; (3) always returning an empty transition list reddened `test_builds_gif_with_transition_frames`.

**The surfaces no test reaches were exercised by hand**: all eight combinations of four patterns and two formats produced output, and the cap fires at 8K across 40 works. **The unit tests cover only `cut` and `crossfade`; `fade_white`, `slide`, the pixel cap, 4K / 8K and the 404 / 409 paths have no gate.**

#### Not fixed here

- **`fade_white` and `slide` have no automated check** (this cycle only ran them by hand once and read the output)
- **`get_items` does not exclude trashed works.** The UI cannot select them, but sending the ids directly will export them
- **8K holds about 2.4 GB of RGBA at the cap** (measured: 8K across three works, crossfade, peaked at 1.37 GB RSS). pentala carries 64 GB with 59 GB free, so the cap was not lowered
- **SPEC is untouched** — it carries neither an endpoint list nor an output-format section, and the render engine, DDL and coerce layers did not move

pytest **1775/31** (+4), cli 76, ruff clean, `npm run check` **220/0/2** (+1 file, `animationExport.ts`), `lint:i18n` **934/47/0/0** (+22, -6), `lint:models` 68, `lint:recommendations` 37. **No decisive layer changed, so the frozen corpora were not re-baked.** **Android has no diff** (`android/VERSION` unchanged). **The version is a patch** — what was added is an optional endpoint and UI, and neither the stored format nor the API's compatibility broke.

---

### v2.9.14 — the thirteen catalogs each carry all nine colors (Build 790, 2026-07-31)

**Engine 17 built the path that picks from a `palette`, but the table it picks from was still engine 16's.** Each catalog held eight palette colors and a six-key `map`, and **many catalogs held no color in a band at all** — ask for green where there is no green and the nearest hue, a yellow, stands in. Across the 7463 stored instructions, **140 asked for a band the catalog did not hold**. **This version replaces data and nothing else**: the resolution chain, the band definitions, the achromatic threshold and the seed material are all engine 17's, and `renderer.py` has no diff.

**Thirteen catalogs now hold ten palette colors each, fixed at exactly three achromatic and exactly seven chromatic.** The seven fill all six bands, one band holding two. The `map` grows **from six keys to nine**, and **all nine are drawn from that catalog's own palette** (before, `map` and `palette` could name different colors). The UI's swatch strip is derived from the `map` with **the six chromatic keys first** — Android draws `swatches.take(4)` and `take(8)` on two screens, so an achromatic-first order would spend those slots on black, gray and white and leave the bands off screen. **No hex repeats across the 130.**

**`desert_mineral` retired; `moss_bark`, `neon_plate` and `lantern_dew` joined.** The retired one held a single achromatic color, which is why engine 17's anti-collapse rule existed. **All ten retired ids answer `None` from both `get_color_catalog` and `render_color_map_for_catalog`** rather than falling back to `default`. 117 stored works name that id; **no migration was written** — an unknown id is drawn with the default catalog, as before.

#### Reach (this recovers wrong bands; it does not add color)

Measured by running the 7463 stored instructions through both engines.

| Metric | engine 17 | engine 18 |
|---|---|---|
| Band the description asked for, absent from the catalog | 140 | **0** |
| Chromatic hits | 2184 / 2455 (89.0%) | **2455 / 2455 (100%)** |
| Achromatic hits | 4917 / 5008 (98.2%) | **5008 / 5008 (100%)** |
| Distinct hexes resolved | 79 | **91** |
| Palette colors never drawn (catalogs in use) | 7 | **9** |

**The never-drawn count rises rather than falls.** The nine in catalogs actually in use are eight purples plus `sea_stone/Coral Orange`, because **purple is 0.9% of real demand**. Counting all thirteen gives 39; the extra 30 belong to **the three new catalogs**, which no stored work names and which therefore cannot be reached at all. **What moved is recovery from a wrong band**: `default` gains 106 yellows and loses 106 greens, `sea_stone` gains 58 greens and loses 58 yellows, `cool_material` gains 37 reds against 37 oranges and 35 greens against 35 yellows. Across all bands: achromatic 67.2% (unmoved), red 11.4 → 11.8, blue 10.0 (unmoved), green 8.4 (unmoved), yellow 2.3 (unmoved), **orange 0.8 → 0.3**, purple 0.0 → 0.03.

#### `sea_stone` keeps its purple band empty

**One catalog deliberately does not fill a band.** By the author's ruling `sea_stone` holds no purple, and the nearest-band stand-in engine 17 provides answers with `Night Sea #191970`. **That is also this catalog's `blue`**, so a work placing blue beside purple draws two shapes in the same navy. **Checked by eye**: the forms stay legible where they overlap, so the picture does not break — it reads as the same color used twice.

#### Roles dissolving into the paper fall from eight to two, and [I-062] closes

**Engine 17's regression** — `cool_material`'s `black` landing on `#e5e8e8`, 0.062 in lightness from the paper — **is gone** (that catalog's black is now `#26282a`). **The two that remain are both yellows**: `vivid_material`'s `#fff200` (ΔL 0.026) and `open_air_light`'s `#ffce00` (ΔL 0.127). A bright yellow band is yellow's own nature, so neither was changed. **Measured across 10 seeds × 13 catalogs, those two are the only ones.**

#### A missing gate, found during acceptance and added there

**All four acceptance perturbations break product data only** — no test file, no type, no signature. (1) nudge one chromatic hex by a step; (2) push `cool_material`'s `Spruce` under the chroma floor, emptying a band; (3) **lighten its black back into the paper, reproducing [I-062]**; (4) as a control, move that same black to a different but still dark hex.

**(3) reddened exactly two things: the expected-assignment table and the frozen corpus.** Both are regenerated wholesale whenever catalog data changes, so **no test named the property "a role does not dissolve into the paper"** — the same shape that let this regression through engine 17 with all five acceptance metrics green. **One test was therefore added during acceptance**: it counts the assignment for 13 catalogs × 8 seeds by lightness distance to the paper and **pins the two survivors by hex**. It reddens under (3) and stays green under (4), so it fires on the property rather than on any edit.

#### Corpus and versions

- **`render_engine_version` 17 → 18. `ddl_engine_version` stays 4 and `ddl_version` stays 3** — neither DDL's vocabulary nor its grammar moved
- **Reference corpus `render-engine-18/`** — **493 cases** (A 88 / B 72 / C 58 / D 28 / E 119 / **F 128**), **70 changed / 423 unchanged**
- **None of the 365 cases in A-E moved, and nothing outside the F group moved**
- The 70 are **42 existing ids whose performance changed** plus **28 new ones** (27 for the new catalogs, plus `F-hint-missing-purple-sea-stone`). Ten disappeared (`desert_mineral`'s nine plus `F-hint-missing-purple`)
- **58 further cases changed only in what was recorded** — `input.color_map` went from six keys to nine while the digest did not move a byte
- `color_map_digest` `bbb2f7be3cab3d70c7330520728ac4b0` → **`96f2809778344689d8fc1dbab03827b0`**

#### Not done here

- **The Android catch-up** (ledger [I-070]). `ColorCatalogs.kt` still holds **eleven catalogs, a six-key `map`, `desert_mineral`, and eight hand-written swatches**, with none of engine 18's data. **What was never ported is the data, not the chain** — `oklchFromHex`, the bands and the chroma floor are already in `ServerRendererStyle.kt`
- **Migration of stored `history`** (a retired id draws with the default catalog)
- **`renderer.py`**, `_oklch_from_hex`, and the decided colors, names and order

pytest **1847/31** (+72 = 68 in the new `test_color_catalog_content.py`, plus 2 each in `test_abstract_color_vocabulary.py` and `test_palette_color_assignment.py` where the parametrization went from 11 catalogs to 13), cli 76, ruff clean, `npm run check` **220/0/2**, `lint:i18n` **934/47/0/0**, frozen corpora byte-identical on regeneration. **The version is a patch** — an engine version rises, and no stored format changes.

### v2.9.15 — four characters find a work, and the surfaces line up (Build 801, 2026-08-01)

Seven independent branches (Builds 791-800) merged into one version, **closing four ledger items**
([I-049] / [I-050] / [I-058] / [I-071]).

#### Finding a work by four characters ([I-071], Build 798)

A work can now be found by the **last four characters of its render hash** — the same four the work
panel already shows. Three routes carry it: `/api/history`, `/api/history/lineage-groups` and
`/api/history/lineage-groups/{root}/items`.

- The hash clause is added **only for exactly four ASCII alphanumerics**, matched case-insensitively
- The existing search (description, DDL, Stage 1/2 model, catalog ID) **still runs for four-character
  queries**; the hash is an additional OR
- **Three characters, five characters and anything punctuated never reach the hash**
- **This shape alone bypasses FTS**: `_use_history_fts` takes over at three characters, and the index
  does not hold the hash column, so without the bypass the query would answer nothing
- Labels: `検索（記述 / ハッシュ値下位4桁）:` and `Search (description / last 4 hash characters):`
- The same five-clause OR **was duplicated across the three routes** and is now one
  `_history_search_clause`

#### Bilingual labels enter the linter's view ([I-058], Build 797)

`lint:i18n` gains a **fourth channel**. Alongside `en.ts` values, `isJapanese ? …` ternaries and
`getLang() === 'ja'` branches, it now extracts the English half of **`Japanese / English` text nodes
written straight into component markup**.

- **The channel carries 17 strings** (measured: removing it drops 949 to **932**)
- It covers the model meta card, the model picker and the settings screen
- Two `isJapanese ? '状態 / Status' : 'Status'` sites became plain `状態 / Status`, so **two more places
  show Japanese in the English UI** — the other fifteen labels on those cards were already unconditional

#### A grip on the numbers in settings ([I-050], Build 799)

A new `NumberStepper.svelte` puts **hand-built −/+ buttons** on the four DB-backup fields (interval
1-365 days, generations 1-100, hour 0-23, minute 0-59). **Firefox has no hook equivalent to
`::-webkit-inner-spin-button`**, which is exactly why [I-050] said the native spinner would have to go.
Button metrics come from `--btn-sm-padding` / `--btn-sm-radius` / `--btn-sm-font-size`. Values clamp to
the bounds and the matching button disables at each end; typing and keyboard input still work.

#### Two words for one action ([I-049], Build 800)

`settingsReloadSettings` now reads the same as `settingsReload` (`設定再読み込み` → `表示更新`,
`Reload settings` → `Refresh`). **The key, the click handler and the API call are unchanged** — only
the displayed string moves.

#### The Info modal (Builds 793-796) and the rest

- **The title goes from `inku-lang` to `inku`**, 18px to 24px, with a 32px Incu icon
  (`/favicon-192.png`, an existing static asset, no animation) to its left. Width 520px → **780px**
- The concept body and the creator note were replaced with **copy the author specified in both
  languages**, and the creator name is now `及川 信一郎 (Shinichiro Oikawa)` in both
- **The vocabulary table dropped its "headnote" and "reading" rows.** No English string glosses
  `kotobagaki` any more, so **the exception `GLOSSARY.md` and `i18n-lint.mjs` held for it was removed**
  (done during acceptance)
- The author's copy uses "image", so **`appInfoConceptBody` joined the `image` exception**, with the
  reason recorded in the glossary
- **The user-plugin on/off switch moved to the right end of its row** (Build 791); behavior and the
  save API are unchanged
- **A starred work read as unstarred in the dark theme** (Build 792):
  `:global(html[data-theme='dark']) .hash-row-star` outweighed `.hash-row-star.starred` in specificity,
  fixed by `:not(.starred)`. The same rule's `font-size: 10px` moved to `var(--btn-sm-font-size)`,
  so **the star grows to 11px**

#### Acceptance

**SHA-256 decided it.** Merging the seven branches with `--no-ff` conflicted **only on
`web/BUILD_NUMBER`, six times**; `SettingsModal.svelte` (791 + 799), `en.ts` / `ja.ts`
(793-796 + 798 + 800) and `i18n-lint.mjs` (793-796 + 797) all combined on their own. That combination
**matched the tree the author reviewed and pentala runs at Build 800 for 9 of 11 files exactly**. The
two that differ are **one `APP_VERSION` line in `+page.svelte`** and **the docs commit `407f536` in
`GLOSSARY.md`** (-2 / +11 lines); both were accounted for.

**One of the three perturbations dug out a missing gate.**

1. `len(search) == 4` → `== 5`: **two tests red**, covering both the API and the lineage routes
2. Removing the FTS bypass guard: **one test red** — which is also what proves **FTS is genuinely
   enabled under test** (the lineage routes never reach it and stayed green)
3. **A shape-preserving perturbation**: `ilike(f"%{search}")` → `ilike(f"%{search}%")`, turning a
   suffix match into a substring match. **All 120 stayed green.** The item says *last four characters*,
   but the tests only saw *four characters find the work*

A test added during acceptance catches it: a second row now carries the same four characters **in the
middle** of its hash, so the search returning exactly one work fails under perturbation 3 and passes
unperturbed.

pytest **1847/31** (**the count does not move** — I-071 adds assertions to two existing test
functions), cli 76, ruff clean, `npm run check` **221/0/2** (+1 file, `NumberStepper.svelte`),
`lint:i18n` **949/47/0/0**, `lint:models` 68, `lint:recommendations` 37.
**No deterministic layer changed, so the frozen corpora were not regenerated. Android has no diff.
SPEC does not enumerate the searched fields and is unchanged. The version is a patch.**

### v2.9.16 — the ground resists the hand (render engine 19, Build 804, 2026-08-01)

In painting the role of the ground is to resist the hand: an absorbent sheet lets the ink spread, a
toothy one refuses the tool and leaves the paper bare. Until engine 18 the ground and the drawing were
composited independently and never met; the only place the drawing side read `canvas.ground` was the
mezzotint test in `renderer.py`. **Only 31 of the 1847 stored works carry a `canvas.ground` (1.7%), and
none of the frozen SVGs do**, so a condition placed on the ground side reaches nobody.

Engine 19 puts a default support on the side with 99.7% reach. **The sheet is one constant; which of its
two quantities a tool meets is a property of the tool** (author, 2026-07-31).

#### The support, and which tools meet it

- Held in `stroke_engine` as a module-level table. **It is not a `Score` field** — `absorbency` was
  retired in engine 15 and its absence is pinned. The per-`material` table is deferred; only the
  swap-in point (the `Support` argument) is open
- Tools divide by which of the two quantities (`absorb` / `tooth`) they meet. **A brush is drunk by the
  sheet and swells; a waxy or hard tool is refused and its ink is cut. `rotring` and `computer` are
  zero** — a machine has no contact with paper
- Four levels (g0 to g3) are implemented and **g2 is adopted**. The others stay so the monotonic
  ordering remains checkable

#### The cut removes ink rather than narrowing it

**Narrowing is invisible.** The tools that ought to be refused are exactly the thinnest ones (pencil
1.5px, chalk 3px, crayon 4px), so a 0.25x pinch is 0.20-0.52px on a 520px raster and sinks into the
antialiasing. Being refused means bare paper, not a thin line.

So **no ink is laid down where the envelope passes 0.55**, and the stroke is cut there. One SVG `path`
can hold several subpaths (`ring_path` already relies on this), so **cutting the ink adds no element**.
A closed contour keeps its even-odd band and is never cut.

#### What acceptance found: a wavering line was never refused

A straight line that carries a position `variation` takes a different path through the renderer, which
**rebuilds the outline around the varied centerline** (`outline_for_centerline`). That rebuild dropped
the cuts. The width response survived, so the bytes moved and the frozen corpus counted the case as
changed — **the visible half went missing in silence**.

- Measured (pencil, seed 20260731, five lines): **10 subpaths without the variation, 5 with it** (no
  cuts at all). An arc is cut whether or not it is varied, so the hole belonged to straight lines alone
- The reach is not small. **912 of the 1858 stored works (49.1%)** contain a straight line with a
  position variation, and **242 (13.0%)** draw one with a tool the sheet refuses
- The cut mask now travels on `StrokeResult` and is carried into `outline_for_centerline`, which splits
  both banks at the same samples the straight branch does
- **The arc was removed from the acceptance figure.** Left in, it would have raised the subpath count
  even with no cut on any line — the test would have supplied its own answer

#### Version and corpus

**`render-engine-19` is frozen: 227 of the 493 cases move and 266 do not.** The order is forced:
implement with the version still at 18 and measure against `render-engine-18`, then raise it to 19 and
bake, then commit the baked corpus before running `check_frozen_corpora.py`. The output directory comes
from `current_render_engine().version`, so **raising the version removes the comparison target from the
generator's view**.

- **No `rotring` or `computer` case appears in `changed_from_previous`**
- Fixing the wavering-line hole moved **7 of those 18 cases**, all pencil. `brush_thick` is drunk rather
  than refused, so nothing was cut in it. **The total stayed at 227** — those seven had already moved on
  the width response alone, which is how the missing cut stayed out of sight

#### Acceptance

**The contract's full mark of 381/493 came out as 227/493.** The implementation session measured where
the difference went: the reference probe rebuilt every straight stroke's outline with per-vertex normals
at levels above g0, so **177/493 moved with every resistance bias set to zero** — **46% of the 381 had
nothing to do with the ground**. This implementation keeps the fixed normal. **The author accepted this
on 2026-08-01.**

Four perturbations were applied on the receiving side, on top of the nine in the implementation report.

1. **Shape-preserving** — `TOOL_SUPPORT_BIAS["pencil"]` tooth 1.00 to 0.00, data only: **5 red**
2. **Control** — g2 bleed amplitude 0.70 to 0.72, same mechanism, property intact: **all 37 green**
3. Cut threshold 0.55 to 0.10: **2 red**
4. Drop the carry-over of cuts onto the varied centerline: **3 red**, element-count control still green

pytest **1897/31** (baseline 1847 + 37 new + 1 attribution + 12 added during acceptance), cli 76, ruff
clean, `check_frozen_corpora.py` green. **Android is out of scope for this contract.**

**Left undecided**: the material outline still runs across the cut, so its dashes cross the bare paper
where the ink stopped. Cutting it would mean turning the polyline into a path and would move every
material outline in the corpus.

### v2.9.17 — whether you see the tooltips is yours to choose (Build 807, 2026-08-01)

The Codex branch `fix/ui-mode-control-tooltip` (two commits, Builds 805-806) merged in. **The completion
report covers only the second commit (the tooltip toggle); the first (clarifying the UI mode control)
has no report.** This section records both.

#### The tooltip toggle (Build 806)

A show/hide button for the shared tooltips sits in the left rail, between the UI mode button and
settings.

- The choice is stored per user account (`user_accounts.tooltips_enabled`). **Both a new user and the
  migration default for an existing database are `true`** (shown)
- `GET /api/auth/me` returns `tooltips_enabled` and `PATCH /api/auth/me/settings` stores it. **Unset and
  legacy data count as shown** (`row.tooltips_enabled is not False`)
- Turning it off puts `tooltips-disabled` on the post-sign-in root, which **hides only the bubbles of the
  shared `Tooltip` component**. No button or feature is disabled
- The toggle is an optimistic update and reverts to the previous state if the API call fails
- Two strings in each language (`tooltipsShow` / `tooltipsHide`). **The label and `aria-label` say what
  pressing it now would do**

#### Clarifying the UI mode control (Build 805, no report)

- **The UI mode icon changed from three lines to a panel-layout mark** — it was hard to tell apart from a
  generic menu and the settings gear
- `Tooltip` gained a `disabled` prop so that **while the UI mode menu is open, that button's own tooltip
  stays away** (its only caller)

#### Acceptance

**Comparing the merge result against the running tree decided it.** The Codex branch was cut from the
engine 19 merge commit, so there were no conflicts, and the merge result **matched the tree pentala runs
at Build 806 for 110 of 111 files by md5** — the one remaining file differing by the single
`APP_VERSION` line.

**One of four perturbations dug out a missing gate.**

1. `update_user_settings` never writes `tooltips_enabled`: **red**
2. **Shape-preserving** — the migration default from `DEFAULT 1` to `DEFAULT 0`, data only: **all 118
   stayed green**
3. `_user_to_dict` returns `True` without reading the row: **red**
4. A new account defaults to `False`: **red**

A gate for 2 was added during acceptance. **The existing migration test only checked that the columns
arrived, and `user_accounts` held no rows at all**, so **nothing looked at the values existing accounts
end up with**. One account older than every settings column is now inserted, and `ui_theme`, `ui_mode`
and `tooltips_enabled` are read back after the migration (red under perturbation 2, red under the
control that flips the `ui_theme` default from `light` to `dark`, green unperturbed).

pytest **1897/31** (**the count does not move** — assertions were added to two existing functions), cli
76, ruff clean, `npm run check` **221/0/2**, `lint:i18n` **951/47/0/0** (+2 for the new strings),
`lint:models` 68, `lint:recommendations` 37, `check_frozen_corpora.py` green. **No deterministic layer
changed, so the corpora were not regenerated. Android has no diff. SPEC does not enumerate display
settings and is unchanged. The version is a patch.**

### v2.9.18 — the typed name becomes `perform`, and the fallback catalog matches the source (Build 808, 2026-08-01)

**Two Codex branches that had been left behind.** Neither had a completion report, neither reached
`main`, and pentala had moved ahead of both. The ledger disagreed with the repository in both
directions: **[I-023] was decided but unmerged, [I-025] was undecided but implemented.**

#### Retiring `refine generate` ([I-023], Build 801)

- The public subcommand is now **`refine perform`**. **The old `refine generate` survives as a hidden
  alias** — `argparse.SUPPRESS` keeps it out of the help text and it is removed from `_choices_actions`
  so it does not appear in the subcommand list either
- One function defines the arguments for both spellings. **The same input posts the same body under
  either name**
- The CLI README and the four CLI reference documents follow `perform`
- cli tests: **76 to 77**

#### Aligning the fallback catalog ([I-025], Build 802)

The static `ollama-cloud` fallback in `web/src/lib/models.ts` held **three** models where the server's
source of truth holds **eighteen**. For the few hundred milliseconds before the API catalog lands, that
fallback is what the picker shows, so **`gpt-oss:20b` looks uniquely owned right after startup** (true
since v2.9.1).

- The fallback now lists **eighteen**, with **`requires_subscription: true` on the ten** that a free tier
  cannot reach
- **This changes the premise of the 2026-07-29 ruling.** The fallback used to carry no marker, so it held
  only the eight free models. **It can carry the marker now, and the marker works from startup**:
  `isModelUnselectable()` reads whichever model is being rendered, and `PROVIDER_GROUPS` is the initial
  value of `modelCatalog` and `availableModelCatalog`

#### Acceptance

**The first full server run on the merged tree failed one test.**
`test_the_web_fallback_offers_only_models_that_can_be_used` pinned "no `SUBSCRIPTION_ONLY` model in the
fallback", which collides head-on with the change above. **The branch satisfies the intent of the ruling —
do not let anyone pick what they cannot use — by marking rather than omitting**, so the test moved to the
new premise: **the fallback carries the same id set as the source, its marked set equals
`SUBSCRIPTION_ONLY`, and its unmarked set equals `FREE_TIER_REACHABLE`.**

**Two of four perturbations showed a gate that simply did not exist.**

1. Stop `refine perform` from reaching the code path: **red**
2. Put `generate` back into the help by dropping the `_choices_actions` filter: **red**
3. **Shape-preserving** — drop `requires_subscription` from `glm-5.2`: **green everywhere, before the rewrite**
4. **Shape-preserving** — drop `gemma4:31b` from the fallback: **green everywhere, before the rewrite**

Neither 3 nor 4 reddens `lint:models`, `lint:recommendations` or `npm run check`. **Nothing guarded the
fifteen models and ten markers the branch added.** The rewritten test reddens under both and passes
unperturbed.

pytest **1897/31** (**the count does not move** — one function replaced), cli **77** (+1), ruff clean,
`npm run check` **221/0/2**, `lint:i18n` **951/47/0/0**, `lint:models` 68, `lint:recommendations` 37,
`check_frozen_corpora.py` green. **No deterministic layer changed, so the corpora were not regenerated.
Android has no diff. The version is a patch.**

> **Found while deploying**: `models.ts` **had reached pentala at Build 802 and was gone again** — today's
> md5 comparison showed pentala's copy identical to main's, without the branch's change. **One real
> instance of [I-053], a parallel rsync erasing someone else's work.** This release puts it back.

### v2.9.19 — the colors become one sheet, selection outlives the page, and the animation gains a height (Build 812, 2026-08-01)

**Three Codex branches collected in one version.** Each is an independent UI or export change and
none contains another's commits. Nothing in the deterministic layers (`coerce/`, `renderer.py`,
`stroke_engine.py`, `schema.py`, `saijiki.py`, `language_support/`) changed, so **the reference
corpora were not refrozen, and `android/` has no diff.**

#### The color catalog modal becomes a contact sheet (Build 810)

- The list-on-the-left, detail-on-the-right arrangement is gone. **All 13 catalogs show their
  palettes at once**: everything selectable is visible before anything is selected
- Each color carries its swatch, hex and English name, plus the Japanese name when the UI is
  Japanese. The catalog name, catalog ID and subtitle sit alongside
- Ten columns by default, five below 980px, three below 380px
- The selected catalog is marked with the theme's `--accent` and a check
- **The confirm button loses its dedicated fill (`primary-inline`) and matches cancel as a
  `ghost-btn`** — sizing still comes from the `--btn-sm-*` tokens, with no literal color anywhere

#### History selection survives a page turn (Build 811)

- `selectedIds = []` was removed from `setPage()` and `setPageSize()`. **Turning the page or
  changing the page size keeps what was selected**
- Select-all on the current page **adds or removes only the current page's ids, leaving ids chosen
  on other pages alone**
- **The places that do drop the selection are still there** — switching between active and trash,
  the starred filter, and a changed search all clear it as before (seven clear sites became five,
  and the two that went are exactly `setPage` and `setPageSize`)
- Works selected off-page are fetched by the existing id lookup when an export runs

#### Animation export gains a height axis (Build 812)

- The resolution choice gains **150px, 300px and 500px**, plus a **custom value from 64 to 12000px**
- The API takes a backward-compatible optional **`height_px`**. Omit it and the old `resolution`
  route runs unchanged
- `build_animation()` rasterizes at that height when it is given, **keeping the aspect ratio and the
  existing encoded-pixel ceiling (600,000,000)**
- `1k` / `4k` / `8k` remain. Stored localStorage settings and existing API callers still work

#### Acceptance — one perturbation showed exactly where the test was missing

The web client **sends `height_px` for every choice** (picking `1k` also sends `height_px: 1080`),
so **the three presets travel through the new derived branch too**. That branch rebuilds the
transition-step ladder from the height (`6 if height <= 1080 else 4 if height <= 2160 else 2`), and
**if the ladder disagrees with `TRANSITION_STEPS` every existing export silently changes length.**

Three perturbations were applied:

1. Ignore `height_px` (disable the feature) → **red**
2. Drop the 64–12000 range guard → **red**
3. **Flatten the ladder to one constant** → **all 123 tests green**

Number 3 stayed green because the new height test was written with `pattern="cut"`, a condition
under which **no transition frame is produced at all**. **Two tests were added: a round trip at the
preset heights (the frame count must match with and without `height_px`) and the ladder's
boundaries (64 / 1080 / 1081 / 2160 / 2161 / 4320).** With those in place all three perturbations go
red and the unmodified tree is green.

pytest **1901/31** (+4: two from the branch, two added during acceptance), cli **77**, ruff clean,
`npm run check` **221/0/2**, `lint:i18n` **956/47/0/0** (five new English strings),
`lint:models` 68, `lint:recommendations` 37, `npm run build` succeeds. **The version step is a patch.**

### v2.9.20 — a group's position returns to the description (render engine 20, Build 813, 2026-08-01)

**What decided where a group went was the seed, not the description.**
**77.8% of the 137673 expanded marks never consulted a declared coordinate**, and **93.3% of the ink
on screen** was placed by the renderer's arrangement rules rather than by the coordinates in the
Score. **Moving every stated coordinate down by 0.2 moved the ink's centroid by a median of 0.0000**,
while **changing `render_seed` alone moved 4.06% of the pixels**.

#### Placement is a second stage

- The stage that decides **the shape of the scatter** (the existing layout branches, now
  `_expand_arrangement_layout`) is separated from the stage that decides **where the group sits**
  (the new `_fit_group_to_anchor`). **No layout branch was rewritten** — shape, density, rhythm,
  wobble and stroke are outside this version's remit
- The second stage **moves the centroid of the expanded group onto the declared anchor**
- **`radial`'s hardcoded `(0.5, 0.5)` is gone.** A stated `center` is still the rotation centre; with
  none stated, the ring turns around the declared anchor

#### The frame is shrunk one direction at a time

- Moving a group onto its anchor pushes marks outside the frame **[0.02, 0.98]** for descriptions
  near an edge (23 of the 32 G cases)
- **Each axis, and each direction along it, is shrunk by only what overflows there.** The spread away
  from the frame is kept and the **worst spread ratio is 0.660**. A similarity shrink collapses to
  **0.315** and was rejected
- Clamping onto the frame was rejected too — it piles 8 marks onto shared coordinates in the
  `scatter` edge case
- **An anchor that is itself outside the frame cannot be saved** (an `at.region` reaching the edge
  with a group of `count=1`). One case out of 100 production works remains; **filed as [I-079]**

#### One thing does not pass through

- **A `grid` with an `at.region` does not go through the second stage.** A grid tiles that region, so
  `at` survives performance resolution; passing it through would drive the group out of the region
  the description stated and onto the shape's own centre, which nobody stated. A `grid` without an
  `at.region` passes through
- The existing `test_grid_uses_at_region_instead_of_margin` failed and surfaced it; the implementation
  wrote it down as `test_a_grid_keeps_the_region_the_description_gave_it`

#### Version and corpus

- **`render_engine_version` 19 to 20**; `ddl_engine_version` stays 4 and `ddl_version` stays 3
- **Reference corpus `render-engine-20/`** — **525 cases** (the 493 of A–F plus **32 in group G**).
  **The existing 493 are byte-identical**
- **The manifest's "32 moved" counts every new case and is not the mechanism's effect.** The effect
  was measured by drawing the same 32 cases under both engines: **30 / 32** (the two that hold still,
  `G-{vertical,horizontal}-nopath-center`, already took one axis from the declaration)
- **Over 100 production works**: the distance from a group's centroid to its anchor falls from a
  median of **0.0719 to 0.0000**, marks outside the frame from **18 / 3890 to 1 / 3890**, and
  `relation` survival is unchanged (10 / 10)

#### Found and fixed during acceptance

- **T-2 (no placed mark leaves the frame) imported the very bound it was checking.** Loosening
  `FRAME_LO` / `FRAME_HI` to 0.005 / 0.995 moved the expectation with the product and **left the test
  green**; the only red was the G digest, and **a digest is rebaked whenever the corpus is
  regenerated**. The test now **states 0.02 / 0.98 itself**, and a separate test holds the product's
  constants to those values. After the fix the same perturbation reddens two tests, and the control
  that tightens the frame instead leaves T-2 green
- Three perturbations were applied during acceptance: the frame constants (data only, no shape
  change), replacing the centroid with the group's first point, and removing the `grid` + `at.region`
  bypass. The latter two reddened three and two tests respectively

#### Where the contract's numbers were not met

- **The production measurements do not agree to one digit with the contract's section 2.4.** The
  direction and size of the effect reproduce, but **the definitions of "pixel difference" and "ink
  centroid" were not carried in the contract** (its harness was not shipped). **The engine 19 side
  also differs from the contract's figures**, which places the discrepancy in the metric rather than
  in the implementation
- `Arrangement.center`'s description still reads "omitted = 0.5,0.5", which is wrong after the second
  stage. It is a string that reaches the Stage 2 tool schema and was left alone; **filed as [I-080]**

pytest **1910/31** (+9 = 8 from the implementation, 1 added during acceptance), cli **77**, ruff
clean, `npm run check` **221/0/2**, `check_frozen_corpora.py` byte-identical. **The version is a patch.**

### v2.9.21 — a history thumbnail says which engine drew it (Build 815, 2026-08-01)

Integrates the Codex branch `feat/history-tooltip-render-engine` (1 commit).

The tooltip on the history thumbnails along the bottom of the screen gains one `render engine` row.

- The value reads `id / version` (`default / 20`). **If only one of the two was recorded, only that
  one is shown; if neither was, the row reads "not recorded"** (`historyVersionNotRecorded`, an
  existing string in both languages)
- The change is **three lines in `HistoryStrip.svelte`**: `render_engine_id` and
  `render_engine_version` are added to the `HistoryItem` type, and one tooltip row is added.
  **The API, the database, the stored history format and the drawing are untouched**

#### Acceptance

- **The completion report gives the branch point as main `d5940d8` (Build 808, render engine 19),
  but the measured `merge-base` is the current main `0e4a686`** (after the engine 20 merge). There
  were no conflicts
- **The values shown were measured to actually arrive.** The strip's items are `data.items` from
  `GET /api/history` verbatim, and the `HistoryItem` response model carries both columns; a probe
  confirmed `default` / `20` appear in the list response
- **An existing test already guards that dependency** —
  `test_api.py::test_paint_can_save_server_generated_history` reads `render_engine_id` and
  `render_engine_version` **off the list response**. Dropping both columns from `db._row_to_dict`
  reddens it with a `KeyError`. **No new test was added**
- **The wording follows the existing house style**: the provenance table in `CanvasPanel.svelte`
  already uses the same bare `render engine` label and the same `id / version` form. `lint:i18n`
  does not look at bare display strings, so the judgement was made by counting existing callers
- **The tooltip does not get wider**: the label column is a fixed `54px`, and the new label
  `render engine` (13 characters) is the same length as the existing longest, `Color catalog`
  (13 characters). The extra row grows upward, and the strip sits at the bottom of the screen

pytest **1910/31** (unchanged), cli **77**, ruff clean, `npm run check` **221/0/2**, `lint:i18n`
**956/47/0/0** (unchanged). **No deterministic layer changed, so no corpus was rebaked. There is no
`android/` diff. SPEC does not enumerate the history tooltip's rows and is unchanged. The version is
a patch.**

### v2.9.22 — the color catalog is decided by reading the description (Build 817, 2026-08-01)

Integrates the implementation of ledger **[I-082]** / the contract `color-auto-select.md` (revision 2).

**The color catalog for the demo and for batch runs changes from a draw to a reading.** The choice is
made on the server, and `/api/paint` carries how it is made in `catalog_mode`.

- `catalog_mode` is one of **`fixed`, `auto`, `random`** and replaces the boolean
  `random_color_catalog`. **A client that omits it behaves as `fixed`**
- **`auto`** has the new `color_selector.py` (150 lines) build a card of all thirteen catalogs and ask
  the model through the same resolution Stage 1 uses, **accepting only an id that survives the
  allowlist**. A failure, a timeout, or an id that does not exist **falls back to the requested
  `catalog_id`** — not to `default`
- **`random` was kept, for refinement only** (author's ruling 4). "Another catalog" exists to see one
  description in a different color, and reading the description would settle on the same catalog
  every time, which is the feature disappearing
- The demo setting moved to `catalog_mode` as well (`fixed` or `auto`). **No migration is needed
  because `_normalize_demo_settings` rebuilds from the defaults**, confirmed against the production
  database on the deployment host

#### A reading sits between a draw and a keyword match

The product's `select_catalog_id` was run over the same 60 cases, the same model and the same
`temperature=0.3` as the prototype:

| measure | prototype (v2.9.19) | **implementation (Build 814)** | uniform draw | keyword match |
|---|---|---|---|---|
| catalogs used | 11 / 13 | **11 / 13** | 13 / 13 | 1 / 13 |
| normalized entropy | 0.856 | **0.853** | 0.973 | 0.000 |
| same text three times, same id | 19 / 20 | **19 / 20** | — | — |

**Two catalogs are never chosen** (`fresco_study`, `ink_porcelain` — the same two as the prototype).
One call takes a median of 1.26 seconds and at most 55.74; one call in a hundred raised
`APITimeoutError` and fell back as designed.

#### Found and fixed during acceptance

- **`inku-cli refine perform --kind color` was silently broken.** `cli.py:2965` kept sending the
  deleted `random_color_catalog: True`, and **`PaintRequest` discards fields it does not declare**
  (pydantic's default `extra="ignore"`), so the request returned **200 with `catalog_mode` still
  `fixed`** — the refinement redrew the catalog it started from. Measured:
  `PaintRequest(description="test", random_color_catalog=True).catalog_mode` is `"fixed"`
- **The contract's section 7.5 counted only the web callers.** The implementation session found a
  second one there (`colorCatalogCandidateIds`, kept by the author's ruling), but **the CLI was a
  third that nobody counted**
- **None of the 77 cli tests read the payload key**, so they stayed green. A test that reads the key
  was added; reverting to the old key reddens it, and **a control that keeps the key while changing
  an unrelated value leaves all 78 green**

#### Perturbations applied during acceptance

Beyond the four the implementation applied (identity selector, allowlist removed, card truncated to
twelve, `random` dropped from the enum), acceptance applied one that **changes no shape**.

- **Flipping the demo default from `"fixed"` to `"auto"`** (data only) reddens exactly one test,
  `test_api.py::test_current_user_demo_settings_are_persisted`. A change that would silently make
  every existing user's demo call the model is guarded

pytest **1927/31** (+17 from the new `test_color_auto_select.py`), cli **78** (+1 added during
acceptance), ruff clean, `npm run check` **221/0/2**, `lint:i18n` **956/47/0/0** (the keys were
renamed one for one), `lint:models` 68, `lint:recommendations` 37, `check_frozen_corpora.py`
byte-identical. **The render engine stays at 20, and `ddl_version` 3 and `ddl_engine_version` 4 are
unchanged. `android/` has not followed** (its client-side draw and the old key remain; ledger
[I-072] family). **SPEC gains `catalog_mode` in the English operational section (Modes). The version
is a patch.**

### v2.9.23 — the shared counter stops conflicting, and the first read halves (Build 820, 2026-08-01)

A three-stage contract (`module-split-and-merge-conflicts`) merged in one cycle.
**The premise behind the request was "the giant modules cause the conflicts", and the measurement
disagreed.** Replaying the last 80 merges with `git merge-tree` produces **21 conflicts, and 20 of
them (95%) are the one-line `web/BUILD_NUMBER`**. The two `+page.svelte` conflicts overlap by one
line each; the cause is not size but a **shared append point** — both sides added a different
setting and the key constants landed next to each other.

#### Stage 1 — stop the conflicts at their source

- **A merge driver for `web/BUILD_NUMBER`** (one line in `.gitattributes` plus
  `scripts/git/build-number-merge.sh`). It is a shared counter, so "both sides bumped it" is never
  a real disagreement — **the larger number is always the answer**
- **The driver's command lives in `.git/config`, which is not versioned**, so
  `scripts/git/setup.sh` writes it. Worktrees share `.git/config`, so one run covers every
  worktree of a repository; **a fresh clone starts unconfigured**
- **Every way of losing the configuration fails in the safe direction.** An unconfigured clone,
  an unset `driver`, a deleted `.gitattributes` line — each **conflicts exactly as it always did**
  and never produces a wrong merge. **`merge.buildnumber.name` is deliberately not written**: with
  a name but no driver, git does not fall back to the text merge — it aborts the whole merge with
  `fatal: custom merge driver buildnumber lacks command line` (measured). Dropping the name leaves
  no unsafe way to lose the setting
- **The settings append point is folded per feature** — seven keys moved into
  `web/src/lib/features/{color-catalog,tenkei,wild,export,result-log,batch}/`.
  **What changed is not the number of files but whose path each file is on.** The five places a
  setting touches (key, `$state`, load, persist, touch) moved out of `+page.svelte`, which every
  feature branch edits, into **one file no other branch touches**

#### Stage 2 — how much is read first

The nine components behind an open/close flag (`SettingsModal`, `LineagePanel`, `DdlEditorDialog`,
`HistoryManager`, `ReplayComparisonModal`, `ProfileModal`, `ColorCatalogModal`, `AIRefineModal`,
`SaijikiDrawer`) moved to `await import()`, and `features/export/download.ts` and
`features/model-inspection/state.svelte.ts` came out of `+page.svelte`.

- **The largest chunk drops from 166,815 to 79,533 B gzip** (−52%); the chunk count goes 1 → 31.
  **Total client JS grows, 688,180 → 702,784 B** — this metric is the first read, not the total
- **`SaijikiDrawer` alone is not wrapped in `{#if}`.** The drawer is always in the DOM and opens
  through a CSS `transition: width`; mounting it at the moment it opens would **drop the motion
  that one time**. It becomes its own chunk, but it is fetched at load rather than on first open
- **`+page.svelte` goes 7,411 → 6,836 lines** (script 6,110 → 5,519)

#### Stage 3 — authorization coverage

No test covered endpoint authorization. `server/tests/test_route_authorization.py` is new: it
**walks the live `app.routes`** (not a regex over the source) and follows the dependency tree
recursively. It asserts that the unguarded set **exactly equals** the six entries of `PUBLIC`, that
the route total is **80**, and that `PUBLIC` names only routes that exist.

**The APIRouter split of `api.py` itself was not done** (see "left open" below).

#### What acceptance measured

The implementation session's report was re-measured rather than taken at face value.

| Gate | Measured |
|---|---|
| A-1 `merge-census.py 80` | `conflicted=4` / `web/BUILD_NUMBER` **0** |
| A-2 control 1: unset both `merge.buildnumber` keys | **21 / 20** → restored **4 / 0** |
| A-2 control 2: delete the `.gitattributes` line | **21 / 20** → restored **4 / 0** |
| C-2 strip a product guard | removing `Depends(_current_user)` from `/api/auth/me` reddens **`test_every_route_is_guarded_or_listed_public`** (it reports `/api/auth/me` as the extra item) → restored, green |

**The names that reddened** are `conflicted` and the `web/BUILD_NUMBER` row of `merge-census.py`,
and `test_every_route_is_guarded_or_listed_public`.

A real `git merge` was measured in a throwaway repo (base 800 / ours 803 / theirs 805): unconfigured
= CONFLICT, name only = `fatal`, configured = clean at **805**. **Merge 2 of this cycle was the
live confirmation** — stage 1 carried 818 and stage 2 carried 819, and the driver resolved it to
819 with no conflict.

- **The attribute source is the working tree's `.gitattributes`.** `merge-tree` reads the checkout,
  not the historical trees being replayed, so **a checkout without the line, or a worktree on an
  older branch, still conflicts as before** (the safe direction)

#### Left open

- **Stage 2's gate B-2 (script under 3,000 lines) is not met** (5,519). The measurement says the
  five units the contract named come to 4,388 lines even if all of them are extracted, which does
  not reach 3,000. **The gate's number and the table of places to cut were decided separately.**
  The continuation and the measured units are ledger [I-088]
- **The APIRouter split of `api.py` is not done** (4,474 lines, 80 routes, and more than 80
  module-level helpers shared across routes). **The test that measures 80 routes and the `PUBLIC`
  match across the split is already in place.** Ledger [I-089]
- **Module-level `$state` in `.svelte.ts` and SSR** — the six new files match the existing
  `mascot.svelte.ts` and `i18n/index.svelte.ts`, and this app runs adapter-node with SSR on. Not
  introduced by stage 1; it follows the existing idiom. Ledger [I-090]
- **`/api/prompts` remains unauthenticated**, kept in the allowlist with a reason (ledger [I-086])

pytest **1935/31** (+8 from `test_merge_driver.py` 5 and `test_route_authorization.py` 3; the
`def test_` lists were compared with `comm -23` and **no name disappeared**), cli **78**, ruff
clean, `npm run check` **0/2/229** (files +8, the eight new ones), `lint:i18n` **956/47/0/0**,
`lint:models` 68, `lint:recommendations` 37, `check_docs.py` green (56 internal references),
`check_frozen_corpora.py` byte-identical. **`lint:i18n` not moving is expected** — settings and
features moved and not one display string was added. **`check_frozen_corpora.py` not moving is
expected too** — no deterministic-layer line changed. **The render engine stays at 20, and
`ddl_version` 3 and `ddl_engine_version` 4 are unchanged. `android/` and `macos_swift/` were not
touched. The refactor changes no behavior, and the author's visual check (a drawing, the settings,
the history, the lineage) passed. SPEC gains one correction on the Japanese side. The version is a
patch.**

### v2.9.24 — the eighty endpoints leave the shared thoroughfare (Build 821, 2026-08-01)

Contract `api-router-split` (ledger [I-089]). **`api.py` goes from 4,474 lines to 251**, and
**all eighty endpoints** move into ten files under `api_core/routers/`. What stays behind is the
app wiring alone: `_lifespan`, three middlewares, the four boot calls and ten `include_router`
lines. **Not one byte of observable behavior changes.**

#### What moved where

- **Ten routers** — `render` 8, `settings` 9, `history` 11, `public` 9, `me` 12, `lineage` 8,
  `users` 8, `plugins` 8, `auth` 4, `feedback` 3. **Nothing was left unassigned**
- **Five shared modules** (`api_core/{state,models,deps,common,rendering}.py`, 806 lines together).
  The `api/deps.py` name the contract suggested cannot be used — `inku_server/api.py` and
  `inku_server/api/` cannot coexist — so it became `api_core/`
- **The dependency direction is one-way**: `api.py` -> `api_core/routers/*` ->
  `api_core/{state,models,deps,common,rendering}`. **No router imports `api.py`**
- **Every router is built without a prefix and no path string changed by a character**
  (three `lineage` routes live under `/api/history/...`)

#### One premise of the contract was wrong: guards cannot be moved

The contract said per-route guards would **move** to a router-level default. **Forty-nine of the
eighty cannot move**: their bodies use the `actor` value, so `actor: dict = Depends(_current_user)`
has to stay in the signature (measured: **49 use the guard argument, 25 declare it without using
it, 6 have none**).

**So the router default is a second enforcement point, not a relocation.** The benefit for new
endpoints stands — one added to a router inherits the guard — but **removing the existing
per-route declarations is separate work** and none of it was done here.

The mismatch surfaced through a perturbation: removing `dependencies=[...]` from the `history`
router, exactly as the contract instructed, **left the authorization test green**. There are
twelve enforcement points (one router default plus eleven per-route), and dropping one still
leaves the other putting the same guard in the dependency tree. **Only hitting all twelve turns it
red**, and the nine paths that then appear as `unguarded` (eleven routes) are **all history**, with
no other group mixed in.

#### Acceptance

- **D-1, where the route bodies live** — walk the live `app.routes` and count
  `route.endpoint.__module__`. **Against a do-nothing value of 80/80, zero routes still answer
  `inku_server.api`.** Per the [I-088] ruling, **line count is not an acceptance gate**
- **D-2, the API surface** — an exact match against the digest shipped with the contract
  (endpoints 80, operations 80, schemas 79). **The expected value was measured when the contract
  was issued and went in byte for byte; it was not re-baked** (the sha256 was checked on the way in)
- **The reason for D-2 held up under perturbation** — dropping one field from a response model
  **leaves both the authorization gate and the endpoint count green**, and only D-2 goes red
- **The control perturbation** (reversing the order of the ten `include_router` calls) **stayed
  green everywhere**, confirming D-2's normalization does not look at ordering

#### Five things a pure move did not cover

1. **`_build_number()`: `parents[3]` -> `parents[4]`** — it derives the repository root relative to
   `__file__`, and the file went one level deeper. Until it was fixed `/api/info` returned `None`
   and five tests were red. **Every `__file__`-relative site was swept** (`reference.py` keeps
   `parents[3]`; its depth did not change)
2. **`_logger` pinned to `logging.getLogger("inku_server.api")`** — left as `__name__` the log
   channel would be renamed, and three `caplog` sites name that channel explicitly
3. **Reference re-pointing across twelve test files** (36 symbols, 128 sites). **For the nine
   symbols bound in more than one module the call site decided, not the definition** — `_save_slots`
   is defined in `state` and imported by `rendering`, but the reader is `rendering`'s binding, so
   patching `state` has no effect
4. `API_SOURCE` in `test_color_hint_note_split.py` repointed (the census value of 10 is unchanged)
5. Five unused imports removed by ruff

#### Left standing

- **The "API route" line in `SPEC.ja.md`** was corrected to `api_core/routers/` in this cycle
- **Seven unreachable definitions still in `api.py`** (`_validated_color_map`, `_bearer_token`,
  `_can_manage_user`, `_strip_anthropic_prefix`, `InterpretResponse`, `_OUTPUT_DIR`,
  `_OUTPUT_PNG_SIZE`). **They were already dead before the split and deleting them is outside a
  pure relocation**
- **Folding per-route `Depends` into the router defaults** for the twenty-five routes where it is
  possible. Ledger [I-091]
- **`/api/prompts` is still unauthenticated**, on the allowlist with its reason (ledger [I-086])

pytest **1937/31** (+2, the `test_api_surface.py` and `test_route_module_split.py` the contract
specified; the `def test_` lists were compared with `comm -23` and **no name disappeared**), cli
**78**, ruff clean. **`npm run check` and `lint:i18n` were not run** — the only `web/` diff is the
two lines holding `APP_VERSION` and `BUILD_NUMBER`, with no display string and no type touched.
**`check_frozen_corpora.py` was not run either** — no deterministic-layer file changed, and the
corpus generator does not import `inku_server.api` (measured). **The render engine stays at 20, and
`ddl_version` 3 and `ddl_engine_version` 4 are unchanged. `android/` and `macos_swift/` were not
touched. The version is a patch.**

### 2026-08-01 — The project context stops being a second changelog (**no version bump**, documentation only)

`PROJECT_CONTEXT.ja.md` had grown longer than `SPEC.ja.md` (**93,165 characters against 75,721**), so
its role was measured again and it was returned to a present-tense entry point.

**What was measured.** The single `Current Product State` section held **1,434 lines, 93% of the
file**, and its content was **77 per-version paragraphs** running from v1.89 to v2.9.24. The
paragraphs had doubled in size — 14 lines each across v1.89–v2.4, 19 across v2.5–v2.8, and **27
across the v2.9 series** — so **the v2.9 series alone accounted for 698 lines, half the document**.
The part that actually works as an entry point (purpose, architecture, contracts, where to look,
update rules) was **99 lines, 6.5%**.

**That it was a duplicate.** Each version paragraph opened with the same sentence as the
corresponding changelog heading, word for word (v2.9.24: "the eighty endpoints leave the shared
thoroughfare"), at 20 lines against the changelog's 82 — **the same record at a different
compression ratio**. The document's own update rules already said to keep current contracts in the
specification and chronological detail in the changelog, so **it was breaking its own rule**.

**That it had gone stale.** The body carried **53 statements** of the "not yet done / not yet
followed" kind. Two were sampled and checked against the code, and **both were already false** (the
thinness axis shipped in v2.9.3; `artwork` appears zero times in `SPEC.md`). A paragraph freezes when
it is written, so the claim outlives its own fix.

**What was done.** The 77 version paragraphs were deleted and `Current Product State` was rewritten
in the present tense (versions, vocabulary, pipeline layers, web, server, cli, android, verification
surfaces). **Japanese 1,533 → 213 lines, English 1,913 → 253 lines.** Every statement was measured
again from the code (11 tools, 9 colors, 8 primitives, 13 color catalogs, `render-engine-20` with 525
cases and `ddl-engine-4` with 33, 80 endpoints). Two rules were added: **do not stack per-version
paragraphs**, and **do not record open issues here**.

**Side effects.** The `Target version` line had been left at `v2.9.23 / Build 820` in both languages
during v2.9.24, and was corrected. Two undecided items that existed only inside the deleted
paragraphs were **recovered and filed** (whether the master grid should quantize against absolute
coordinates, and `db.get_items` not excluding trashed works).

`check_docs.py` is green (internal references 56 → 54, because some published documents were named
only by the deleted paragraphs; **no published document lost its last inbound reference** — all seven
lost targets are still named from elsewhere). No code, specification, or drawing behavior was
touched, so pytest, ruff, `npm run check`, and the frozen corpora do not apply.

### v2.9.25 — Five values that called themselves a version collapse into one file (Build 822, 2026-08-01)

Ledger [I-085]. **Two version numbers appeared on the same screen**: `/api/info` reported `2.7.2`
while the UI displayed `v2.9.24`.

**What was measured.** Five places supplied an "application version" independently:
`server/pyproject.toml` (2.7.2, feeding `/api/info` and the server banner), a string literal at
`+page.svelte:77` (v2.9.24, feeding the UI), `reference.py:84` (**scraping that literal out of
+page.svelte with a regular expression**), `web/package.json` (0.1.0, feeding the vite banner), and
`cli/pyproject.toml` (0.1.0). **Two different functions named `_app_version` read two different
sources** — `api_core/common.py` read pyproject, `reference.py` read the Svelte component.

**Consumers were counted across all four areas.** **Nothing interprets `version` from `/api/info`**:
web reads only `developer_mode` and `render_engine_version`, the CLI prints the response verbatim,
and Android never calls the endpoint. The concern recorded when the item was filed — that changing
the response would require counting consumers — **disappeared once they were counted**.

**What was done.** **`web/APP_VERSION` is now the single source.** It sits beside `web/BUILD_NUMBER`
and uses the same mechanism, with the same three readers: the `define` in `vite.config.ts`,
`api_core/common.py`, and `cli.py`. **No new mechanism was introduced.**

- `/api/info` reports two versions — `version` is the **application version** (`web/APP_VERSION`) and
`release_version` is the **distributed package** (`pyproject.toml`). They disagree while releases are
on hold, because they are different things
- `+page.svelte` reads `__APP_VERSION__` from the vite define, which **removes the coupling that made
one line inside a 7,411-line component load-bearing for the reference dump**
- The regular-expression scrape in `reference.py` is gone, along with its now-unused `re` import
- The vite banner reads `APP_VERSION` instead of `package.json` 0.1.0

**Stamping got shorter.** `scripts/bump.py` writes all four systems across six files from one command
(`APP_VERSION`, `BUILD_NUMBER`, the project-context target line in both languages, and the version
marker table in both languages). `--scan-build` reads every local ref and reports max+1, stating in
its output that it cannot see the deployment host. **A pattern that does not match exactly once is an
error**, so a document that changes shape is never silently skipped.

**A consistency gate was added.** `server/tests/test_version_consistency.py` (8 tests) checks that the
four systems agree. **The v2.9.24 miss would have been caught by it.** Its discrimination was measured
with three perturbations: reverting only the project-context target line to `v2.9.23 / Build 820`
(**the miss that actually shipped**) turned exactly one test red; restoring a version literal in
`+page.svelte` turned exactly one red; ageing the build number in the marker table turned exactly one
red. **A control perturbation** — moving only `pyproject.toml` to `9.9.9` — **left all eight green**,
confirming the gate does not mistake a lagging release version for a regression.

**The API surface digest was regenerated**; the difference is one property added to one schema
(`AppInfoResponse.release_version`). Endpoints 80 → 80, zero operation differences and zero removed
properties were confirmed item by item before regenerating (`535566b6…` → `d4c57fed…`).

pytest **1945/31** (+8, the new consistency gate), cli **78**, ruff clean, `npm run check` **229 files
/ 0 errors / 2 warnings**, `lint:i18n` **956/47/0/0**, `check_docs.py` green. **No deterministic layer
changed, so the frozen corpora were not regenerated. `android/` is untouched. The version is a patch.**

### v2.9.26 — Two cards no description ever reached become reachable (Build 823, 2026-08-02)

**Two of the thirteen color catalogs (`fresco_study` / `ink_porcelain`) had never been picked
by the path that chooses a catalog by reading the description** — zero out of sixty production
descriptions (measured at v2.9.22). **Four strings changed**, the `sub` / `sub_ja` of those two
entries in `server/src/inku_server/color_catalogs.py`; the `map`, the `palette` and the names
all stand.

**The cause was measured down to one before the contract was written.** The guess on file --
that the card never carries the wording to the model -- was **false**: those two lines of
`build_catalog_card()` carry `sub`, `sub_ja` and all ten palette names. Position in the list was
not it either (the zeros sit next to a 7 and a 9, and a 6 and a 9). **What remained was the color
overlap**: over all 78 pairs the closest is `default`—`fresco_study` (mean ΔE 11.4), then
`default`—`ink_porcelain` (12.2), then the two against each other (13.3), against a 25.4 median.
**And the two were not dead**: of the 45 descriptions where a user had picked a catalog by hand,
6 (13.3%) name these two -- above the 3.5/45 an even split would give. **The auto path was
applying a different criterion**: the card tells the model to read the subject, the light, the
season and the material, yet **none of those six descriptions contains a subject word either
catalog owns** (across all sixty: plaster, mural, pigment = 0; porcelain, ceramic, kiln = 0,
while wave 29, brush 23, night 10 are real). So the provenance-of-the-pigment words gave way to
words for a scene: "plaster, pigment, warm stone" → "sunlit wall, dry earth, warm shadow", and
"ink, porcelain, mineral accents" → "clear light, ink, sharp mineral accents".

**The effect was measured over four rounds on the same model and the same sixty descriptions**
(`nvidia / google/gemma-4-31b-it`, `temperature=0.3`, serial). **0 / 0 before, 5 / 1 after.**
Normalized entropy went 0.845 → **0.890**, the largest share fell from `default` 14 to 12, and
**all thirteen catalogs were picked at least once** (eleven before). **Reverting the four strings
returns 0 / 0**, so the four strings are what moved it. As a control, keeping the new `sub` while
reverting `sub_ja` gives 3 / 0 -- **`fresco_study` moves off zero on the English side alone**
(the single `ink_porcelain` hit is n=1, so which language carried it cannot be told apart).

**⚠ No existing test can measure this change.** `test_api.py` pins only `default`'s two strings,
and T-3 in `test_color_auto_select.py` asserts `catalog["sub"] in card` -- **its expected value
comes from the product data**, so it stays green through any rewrite. **No new test was added**:
a "never write a `sub` of pure material provenance" check would promote an n=12 observation to a
law, and `vivid_material` (material words only, four picks) already contradicts it. A test that
pins the wording itself is a record that gets regenerated when the data changes, not a check of a
property. **The acceptance lives in the runs.**

**One statement in the contract was wrong**: `entry.sub` at `contactSheet.ts:185` is not the
catalog's `sub` but the history timestamp (`formatHistoryDate`) -- the names merely collided.
Four places display it (`ColorCatalogModal`, `ManualRefineModal`, the provenance list in
`CanvasPanel`, and the AI sheet note). **None of them truncates the new wording**, checked
against the CSS and the string widths (not in a browser).

pytest **1945/31**, cli **78**, ruff clean, `check_docs.py` green (54 internal references).
**`sub` reaches neither the drawing nor the Score, so no frozen corpus was rebaked**
(`"sub"` appears 0 times in the `render-engine-20` and `ddl-engine-4` manifests).
**Not one line of web changed** (the copy in `colors.ts` is `default` alone).
**The same two lines under `android/` belong to [I-070] and were left alone.** Patch bump.

### v2.9.27 — Thirteen items the author sent in one message land in one release (Build 825, 2026-08-02)

**Thirteen items the author sent in one message** were folded into a single contract and landed in one
cycle. They are not ledger entries. The work touched 28 files under `web`, 6 implementation files and
7 test files under `server`, and 1 under `cli`; **not one line of the drawing changed.**

**The color chips of all thirteen catalogs now share one order.** Taking the ten colors of `default`
as the reference, **only the order of the entries** in the other twelve palettes was rearranged
(54 lines moved; `name`, `name_ja` and `code` are untouched, and so are `map` and `SWATCH_KEY_ORDER`).
`palette` has two readers -- the chip grid in the modal and the one-line card the Stage 1 model reads --
so a shared order makes the grids match and makes the cards name their colors in the same sequence.

**The rearrangement turned the frozen corpora red once, and not one drawing moved.**
The only file that changed was `server/reference/render-engine-20/manifest.json`:
**all 525 SVGs are byte-identical**, the manifest's 592 changed lines have **an added set equal to the
removed set** (bar the trailing commas), and read as JSON the two are **deep-equal** -- normalising with
`sort_keys` makes them identical and only the raw serialisation differs. The manifest writes `color_map`
in dict insertion order, and that order follows `palette`. **This is a record that gets re-baked when the
data changes, not a test of a property.** It was re-baked and adopted.

**A close button appeared on the two modals that lacked one** (the color catalog and the model picker).
**The second was not a matter of looks.** The `onCloseSettings` the button reached only set
`settingsOpen = false`; it never ran what `closeSettingsModal()` does -- roll a half-made model choice
back with `cancelModelSelection()`. **The condition that withheld the button was covering a path that
closed without rolling back and left a stale snapshot behind.** The button was rewired to `onClose`,
the handler the backdrop and Esc already use, and `onCloseSettings` was removed along with its prop.

**The batch tab shows `(x/y)` while a batch runs.** The tabs are `flex: 1`, so the three keep equal
widths whatever they hold, and the counter carries `tabular-nums` and a `min-width` sized for the digit
count, so it does not shift as the numbers grow.

**Lines that failed are drawn again, as many rounds as configured.** The default is **0 -- the old
behaviour**: making it 1 would silently double the model spend of a failed batch for anyone who never
opened the setting. The main loop was lifted into `paintBatchLine()` so the first pass and the retry
passes run the same implementation. **An interrupted run (stop button, aborted request) is never
retried** -- lines that did not run are not failures. The failure report's `total` stays the original
line count, and only the progress display is re-pointed per round, reading `(2/5 ↻1)`.

**The thumbnail tab of history management lays works out by lineage.** Lineages with a single work drop
out. **The filter runs in the aggregate's `HAVING`, and `total` counts the same subquery**, so the page
and the count cannot disagree (discarding on the client would thin a page of 8 and contradict `total`).
Within a lineage the order is **by generation** (`lineage_generation` ascending, `at` ascending within a
generation), and the connection is shown by **an enclosure and generation numbers rather than lines** --
lines break the moment the grid wraps.

**That stage turned up one pre-existing inconsistency, unrelated to this work, and fixed it.**
`list_lineage_groups` groups by `coalesce(root_node_id, id)` while `list_lineage_group_items` filtered on
`root_node_id == :root` exactly. `root_node_id` was added by a migration with no backfill, so
**a root created before it holds NULL: it counted towards its group's total but fell out of its own
member list.** Both now use the same expression.

**A second mark, independent of the star, was added** -- `for_revision` ("For revision only").
`starred` is not overloaded; it is a separate column, and **raising both filters means AND** (only works
carrying both marks). All nine places `starred` appears got a counterpart (column, migration, index,
response, creation default, both FTS search statements, the listing, the lineage-group aggregate, and
the other listing path), and `PATCH /api/history/{item_id}/for-revision` is new. **The senders were
counted across `web`, `server` and `cli` and all of them were carried** (`cli` gained `--for-revision`
on `history` and `history export`). **`android` was not**, and for now neither sends nor reads it.

**Downloads can go to a folder the user picked** (File System Access API, Chromium only; Firefox and
Safari fall back to the browser default as before). **The intent and the display name live on the server
(two columns on `user_accounts`) while the directory handle itself lives in the browser's IndexedDB** --
a handle travels only as a structured clone and cannot be sent to the server. The permission is checked
**on every save**, and when it is refused the file goes to the browser default **and the screen says the
destination changed**. The three places that dropped a file were **folded into one**
(`features/export/save-target.ts`), so all four callers -- the three SVG profiles, PNG, the contact sheet
and the animation -- pass through it. **On a browser without the API the setting is not disabled but
omitted entirely.**

**The AI contact sheet can be built from the lineage panel too.** Rather than duplicate it, the body of
`HistoryManager`'s was moved into `features/contact-sheet/run.ts` and **both call the same
implementation** -- paging, the numbering that runs across split sheets, and the wait between successive
downloads all drift silently on one side if they are copied. Each panel supplies only which ids are
selected and how to resolve an id to a work; the lineage side resolves from the graph it already holds
and needs no fetch.

**A lineage card names the model that drew the work**, shortened: no provider name, and the vendor
prefix (up to the first `/`) dropped -- `google/gemma-4-31b-it` becomes `gemma-4-31b-it`.
**The string is never truncated** (overflow is caught by the caller's `ellipsis`).
**Two names appear only when Stage 1 and Stage 2 differ**, one when they agree; the full
`provider / model` for both stages stays in the `title`. A work with no model recorded shows nothing.

**The drawing-parameter editor (`adjust`) gained a model picker** -- the same `ModelCardPicker`, label
and handler as `DdlEditorDialog`, and **choosing there rewrites the `stage2Provider` / `stage2Model`
default**. Stage 1 is untouched; the screen for that is the model comparison.

**The wild switch now reaches all six modals a work's menu opens** (one `WildToggle.svelte`, not six
copies). Following staffage, **it carries an "inherited" state**: specify nothing and the parent work's
`render_wild` is inherited. **This changes behaviour**: the refine paths sent no `wild` at all, and
`paintOne` sent the default `false` via `options.wild ?? false`. **A wild parent was being redrawn calm.**

**The reported mismatch between the two compare buttons could not be found in the code.** The model
comparison and the language comparison agree on component, `icon` / `block`, ancestor chain, width and
color, and the leading hypothesis -- that the `Tooltip` wrapper shrinks one of them -- was already
handled in `CanvasPanel.svelte`. **No CSS was added on a guess. A before screenshot from the author is
what this needs.**

**The survey of ageing libraries stopped at the survey**, as the contract asked. **Not one line of code
changed.** `svgwrite` is at 1.4.3 upstream too and cannot be raised, and the `cookie` override cannot be
dropped while `@sveltejs/kit` 2.69.3 still declares `^0.6.0`. **Nothing is declared and entirely unused.
Which of them to raise waits on the author.**

**web gained a unit-test base** with no new dependency -- Node v26's `node:test` and its direct
TypeScript execution were enough. `npm run test:unit` runs **14 tests**: 9 over the batch retry decision,
which was lifted out into a pure function, and 5 over the shortened model name (**including that two ids
differing only in their tail never collapse to one string**).

pytest **2011 / 31 skipped** (+66), cli **78** (unchanged), ruff clean,
`npm run check` **235 FILES / 0 ERRORS / 2 WARNINGS** (the two warnings are the pre-existing ones),
`lint:i18n` **975/47/0/0**, `lint:models` **68**, `lint:recommendations` **37**,
the `test_api_surface.py` baseline **81 / 81 / 80** (one new route and one body schema; **nothing was
removed**), `test_route_authorization.py` **81**, `check_docs.py` green, **frozen corpora byte-identical**.
Acceptance applied **seven perturbations**: an order-only swap (one new test red; the 177 existing color
catalog checks see none of it), a **control** that renames without reordering (all 178 green), disabling
the `HAVING` (3), reverting `coalesce` to strict equality (1), disabling the revision filter (2),
disabling the folder-name clear (1), and `<` to `<=` on the retry limit (2 of 14). All were reverted and
the values read back to confirm restoration. Patch bump.

### v2.9.28 — The wild toggle stops showing the browser's own button (Build 826, 2026-08-02)

**The `WildToggle` that v2.9.27 placed in six modals was the one light box in a dark dialog.**

The cause was CSS scoping. The button was written `class="ghost-btn wild-btn"`, but
**`WildToggle.svelte`'s own `<style>` carried no `.ghost-btn` definition**, and Svelte scopes styles
per component -- so **`ghost-btn` styled nothing**. `.wild-btn` holds only the size tokens
(`--btn-sm-*`), so the off state fell through to **the browser's own button**. The on state looked
right, because `.wild-btn.active` paints `--accent` -- **looking only at the pressed state hides it.**

The definition `InputPanel` and the other panels carry was placed in `WildToggle.svelte`.
**Tokens only; no literal px and no literal colors.**

**Counted across the components, `WildToggle` was the only one that used `.ghost-btn` without
defining it** (`ProfileModal` defines it in a grouped selector).

`npm run check` **235 / 0 / 2**, `lint:i18n` **975/47/0/0** and `test:unit` **14** are all unchanged.
**The compare buttons were not touched** -- the dark fill is `--action-disabled-bg`, the disabled
state that holds while no model or combination is checked (checking one turns it `--action-bg`, the
same fill as the main paint button). **Left as it stands, by the author's decision.** Patch bump.

### 2026-08-02 — The Japanese and English versions correspond section for section (**no version bump**, documentation only, stage 1 of 3)

**It started with the author's observation** that `SPEC.md` looked older than `SPEC.ja.md`.

Measured, **the declared version matched at `v1.92.0` in both**; the difference was in the commits.
`SPEC.ja.md` was last touched by `1f900b22` (v2.9.24) and `SPEC.md` by `6dbf1625` (v2.9.22), **two
documentation cycles behind**. But both edits that never crossed over landed **inside sections the
English file does not have** (§17, open items, and the repository appendix), so no stale statement
was left in English (`api.py` and `+page.svelte` are named nowhere in it).

**The reason the drift was invisible is mechanical.** The bilingual check in `check_docs.py` compares
`_heading_shape()` -- **the sequence of heading levels and nothing else** -- and the SPEC pair was
registered with a declared exception, so **prose drift was caught by no check at all**.

**Two defects surfaced at the same time.**

- The opening of `SPEC.md` claimed "Sections 1 to 17 follow the Japanese file section for section",
  but **§15 and §17 are absent in English** (it runs 1-14 and 16). **A published document was
  misdeclaring its own structure.**
- **A single blank line split the §3 vocabulary table.** The second half (relations, places, angles,
  proportions, colors) had neither a header nor a delimiter row, so **GitHub rendered it as literal
  pipe-separated text rather than a table.** Half of the ten-category vocabulary table -- the core of
  the public specification -- was shipping broken.

**The author's ruling of 2026-08-02 withdraws the 2026-07-28 division** under which Japanese was
canonical for the concepts and English carried the operational sections alone. The two files now
correspond section for section. **Japanese remains the canonical source.**

This cycle (stage 1 of 3) did the following.

- **The structural gap was wider than the declared exception said.** It recorded "English still lacks
  §15 and §17"; in fact **§1.1-1.3, §3.1-3.2 and §11.1-11.4 -- nine subsections -- were also absent.**
- **§1**: English gained an About This Document section (the origin of the name, the ecosystem naming
  convention) and the 1.1/1.2/1.3 split. In the other direction, the paragraph only English carried --
  that inku is not a drawing program, that the description is the durable work and the SVG one
  performance of it -- went into Japanese §1.1.
- **§3**: English gained 3.1/3.2 and the five core properties. Japanese gained the origin of the name
  Saijiki, the v1.92 pruning and the v2.7.9 silverpoint rename, the catalog id list and its naming
  policy, the `sub`/`sub_ja`/`name_ja` display rules, and the render JSON field record.
- **§11**: Japanese held the v0.8-era plan where English held current practice -- **the two were not
  translations of each other**. Current practice won; 11.1-11.4 now match in both, and **the original
  plan is kept as 11.4 in both languages**.
- **§15 (development policy) and the repository appendix were written in English.**
- **`SPEC.md` §24 withdraws "Keep public English wording concise and readable"** -- the one remaining
  instruction that invited abridgement -- and states instead that the English must not abridge and
  that `check_docs.py` is the only gate.
- The two declared exceptions in `check_docs.py` were rewritten **from permanent waivers into
  descriptions of temporary remaining work.**

**Stage 2 followed the same day** -- **§6.7 (the English instruction path), §7.8 (the reference web
application) and §12.14 (what the renderer owns), which only English carried, were written in
Japanese** (185 lines / 14,332 characters). The three English opening lines that said "has no
Japanese counterpart" and cited the 2026-07-28 ruling were removed. **The heading shapes now match
through the 116th heading**; only §17 and §18 onward still diverge.

**The specification half of stage 3 followed the same day** -- English §18-24 (JSON Score, the canvas
model, modes, history and data integrity, security and operations, the CLI, and the source of truth)
were written in Japanese. Doing so also exposed **three missing headings in the English Accounting
for Refinement section** (two for v1.80 and one for v1.88): **the prose was there in English, only
the headings were absent, leaving two against the Japanese five.**

**The Japanese version of the implementation-status inventory, `docs/spec/implementation-status.ja.md`,
was also written** (against 429 English lines / 30,080 characters). **That pair's declared exception is
gone and it now actually passes the shape check in `check_docs.py`.**

**Setting §17 aside, the two SPEC heading shapes now match exactly** (135 against 135). **§17 is all
that remains, and it is blocked on ledger I-095** -- none of its 31 open items appear in the ledger,
so dropping the section would drop them from tracking; the author ruled that they be inventoried
first and only the live ones filed. **The SPEC pair's declared exception is kept as a temporary note
describing that one remaining point.**

### 2026-08-02 — The list of open items moves out of the specification and into the ledger (**no version bump**, documentation only, stage 2 of 3)

**§17 of `SPEC.ja.md`, "Open Items", became a section that only names where things are.** The same
section now stands in both languages, and **the declared exception for the SPEC pair was deleted
from `check_docs.py`**. The two files now match at **136 headings each**.

**The list was inventoried before it was moved** (author's ruling, 2026-08-02). Each of the 31
unresolved entries was measured against the code, and **the 24 that are still live were filed in
the ledger as five items**, grouped by area (renderer, stage 2, stage 1, web UI, testing and
specification). **Five entries were dropped**: three were already implemented (the side-by-side
multi-model comparison view, the plugin loading mechanism and its namespaces, the English Saijiki
and English prompts), one names a training mode **that was withdrawn in v1.2**, so there is nothing
left to evaluate, and one **was a statement of fact rather than a task** (the size of the example
pools). The 48 resolved entries were dropped because the changelog holds them.

**The inventory turned up three places where the text and the code disagreed.**

- **One more variation axis is unimplemented than the specification said** — `Dimension` declares
  six axes, but the renderer reads only `position_x` and `position_y`; **`radius` goes unread along
  with `angle`, `length` and `rotation`**
- **The examples that steer the model toward arcs exist only on the English side** — twelve in the
  English pool, **none in the Japanese one**
- **History export is only half there** — SVG, PNG, animation and contact sheets can be written
  out, but **history JSON cannot, and the only import path is the one for plugin documents**

**Until 2026-08-02 §17 carried the list itself.** Resolved entries had grown to more than half the
section, and the unresolved ones were tracked in two places at once. **The changelog keeps the
record; the ledger keeps the tracking.**

### v2.9.29 — Raising every dependency at once turns up two gates that were green and watching nothing (Build 828, 2026-08-02)

**pydantic, sqlalchemy, pytest, ruff, fastapi, starlette, uvicorn, cryptography, anthropic, openai,
@sveltejs/kit, svelte, svelte-check, vite and pillow all moved. Not one line of product code
changed.**

**What this release actually amounts to shows up in the checks, not in the version numbers.**

**`fastapi` 0.141 stopped `include_router` from flattening routes into `app.routes` and put an
opaque wrapper there instead.** Counting `APIRoute` objects out of `app.routes` goes from **81 to
0**. No product code reads `app.routes`, so **nothing about the running server changed** — but of
the three tests that did read it, **two kept returning green with nothing to enumerate**: the list
of "endpoints still living in api.py" came out empty not because the condition held but because
**the enumeration picked up nothing at all**. All three now read through
`fastapi.routing.iter_route_contexts`, and **an explicit non-empty assertion was added**. The next
time upstream moves the enumeration, it will fail instead of falling silent.

**Nothing tested the `anthropic` call surface.** Before the SDK moved,
`server/tests/test_anthropic_call_surface.py` (13 tests) was written to freeze **the set of keys
sent and the set of response attributes read** at all four call sites. The SDK then went from
0.96.0 to 0.120.2 with **all thirteen green and no product change**, and **one real call was put
through** (stage 1 and stage 2 to a 6,724-byte SVG, 3.54 seconds in total).

**`ruff` 0.16 widened its default rule set from 59 rules to 413.** The repository carried no ruff
configuration at all, so **what "All checks passed" meant was delegated to whichever version was
installed**. 353 findings appeared without a line of code changing, and the largest group of 76 was
against **the `Depends()` form FastAPI itself prescribes**. `select = ["E4", "E7", "E9", "F"]` now
states the set explicitly and **freezes it at the same 59 rules as before** (the cli side carries
the same pin). **Which of the 354 added rules to adopt is a question the ledger holds.**

**`typescript` 7 was left out.** `svelte-check` refuses TypeScript 7 on its own before type
checking begins, and in the dual install it demands, **the `--tsgo` path checks 38 files where the
current path checks 235** (16%). **Cutting the type-checking net to a sixth in order to raise a
dependency is the wrong trade**, so 6.0.3 stays. → ledger

**Stored data was read back through ciphertext made before the upgrade** — three API keys were
encrypted under `cryptography` 47.0.0, the library was raised to 50.0.0, and **all three decrypted**,
down to **returning an empty string rather than raising when the key does not match**.

**What did not move**: the ledger in `test_api_surface.py` stayed at **81 / 81 / 80, byte-identical
down to the digest**, across five fastapi minor versions, and the frozen corpora are
**byte-identical** as well (the ground texture seed is a hash of the whole Score dump, so drift
there would have changed the pictures).
### v2.9.30 — A setting registers itself, and the wild switch is given its own name (Build 832, 2026-08-02)

**Adding one setting used to cost six lines in `+page.svelte`; it now costs none.**
A setting that is kept in localStorage, rides the render request and shows on
screen had to be written into four separate enumerations in the page itself:
load, save, request assembly, prop forwarding. **The enumerations have been
turned inside out into registries** -- `features/render-payload.ts`,
`features/persisted-settings.ts` and `features/user-settings.ts` **name no
feature at all**, and each feature registers itself with a single line of its
own. The page calls each registry once.

**The gate was not line count but "how many lines does one more setting cost"**
(two probes, measured 6 -> 0 and 4 -> 0). `+page.svelte` went from 7,023 to
6,986 lines -- **only 37 fewer, and that is not a failure**: folding the
thoroughfare and shrinking the file are different goals.

**Request behaviour was preserved by comparing all fourteen call shapes one by
one.** That comparison turned up **two asymmetries that predate this change**,
and both were carried across unchanged (demo always sent `wild` as false; the
two in-place redraws inherit the staffage level while drawing quietly).
**No image changes in this release** -- the frozen corpora are byte-identical.

**Three visual defects found by eye were fixed.** (1) The wild switch drifted
away from the staffage buttons and floated mid-row: `.compare-head` spread
three children with `space-between`, and `.ddled-foot` gave the left-aligning
margin to staffage alone. Both now wrap the pair in one box. (2) The switch
carried **no name** -- only "(inherited)" -- so **"Stroke limit (inherited):"**
now stands to its left. (3) **The comparison status overflowed its slot.** The
rule that widened it was written by `64cbbfda` against `.compare-status`, and
when `2cbc93b3` unified the running indicator into `RunStatus` the **comment
survived while the rule stopped matching anything**. It is back, keyed on a
class this component writes itself -- `.run-status` belongs to the child, so a
selector naming it would be scoped away.

**The staffage label was brought to the same shape** -- `Staffage (inherited):`.
**When two labels share a row and only one carries a colon, it does not read as
variety; it reads as an accident.** The wild button in the input panel is left
unlabelled: that row has no notion of inheriting, and none of its buttons carry
a label.

### v2.9.31 — The lineage details name their engine, and the hash can be carried out (Build 833, 2026-08-02)

**Three things were added to the lineage cards.** None of them is a new
mechanism: each shows **something that already arrived and simply never reached
the screen**. The lineage response carries the history row as it stands, so
`render_engine_id`, `render_engine_version`, `ddl_engine_version`,
`render_build_number` and `for_revision` were **already on the node before this
change**. Not a line of the server moved.

**(1) The details name the engine.** Opening "Details" now shows **render engine
/ transform layer / Build** directly under rh2 -- **the same trio in the same
order as the provenance on the canvas**, so a lineage card and the canvas
details read in one vocabulary. A work with nothing recorded shows the same `—`
its neighbouring rows use (**older works are the ones that lack it, and phrasing
that case differently would make an absence look like a fault**).

**(2) The render hash can be carried out.** The rh2 row grew a copy button.
**What it copies is the whole `render_hash`, not the abbreviation on screen** --
the first ten characters are a shape for the eye, not an identity you can paste.
The fallback for browsers without `navigator.clipboard` matches the one the
history manager already uses.

**(3) The revision mark moved next to the star.** Until now the mark could only
be toggled from the history manager, so **a work you decided to revise while
reading the lineage could not be marked without leaving the view**. A ✎ now sits
in the same place and the same shell as the star, and pressing it moves the same
column the history manager's "for revision" filter reads. **The star and the
revision mark are independent** -- a work may carry either, both or neither.

**The wiring was confirmed by perturbation.** The callback is threaded through
three layers (page → canvas → lineage), so **a single missed connection would
produce the defect where the button exists and nothing happens**. Removing each
of the two intermediate hops turned the type check red, and restoring them
returned it to green.

### Android `2.1.4-android.3` — the drawing layer catches up to render engine 19, and the dice are gone (ground resistance, thirteen colour catalogues) (android Build 148091, 2026-08-02)

**The port arrived in four stages.** (1) engine 19's surface response (ground
resistance) in `ServerStrokeEngine.kt`; (2) `ColorCatalogs.kt` from **eleven
catalogues with six `map` keys to thirteen with nine** (the engine 18 data);
(3) **removal of the random catalogue selection** (ledger [I-081], decided by the
author); (4) the version declaration moved to 19.

**The expectations were baked by the commissioner and placed on the branch
first.** The starting point was **`tests=117 failures=13`**, full marks were **0
failures**, and **the contract named which failure belonged to which stage**
before the work was handed over. The finish was **`tests=118 failures=0`** (stage
3 added one test). **The implementation did not touch a single byte of the
fixtures** -- when the expectations move during a parity port, nobody can say
afterwards what was measured.

**Not every engine 19 expectation moved.** The ledger assumed all of them would;
**measurement showed 16 of 53** (the tool grammar, normals, arc lengths and
cloud-form outlines are unchanged under engine 19). **When writing a port
contract, count how many downstream expectations the upstream version bump
actually moves.**

**Removing the dice reached six places.** Deleting `randomColorCatalogId()` was
not the end: the two call sites (batch and demo), two persisted keys
(`batch_random_color_catalog`, `demo_random_color_catalog`) with their restore
paths, and one toggle in `InkuApp.kt` all had to go. **On the Android side, the
change that retired randomness on the server is not one feature but one whole
setting.**

**The test added to guard that removal was vacuous.**
`ColorCatalogSelectionDeterminismTest` has a private helper inside the test that
returns `selectedCatalogId`, and **calls no production code at all**. During
acceptance, **restoring random selection in the production demo path** left
**all 118 tests green**. The removal itself is correct (**no `Random` remains**),
so what is missing is only the gate: **a real one needs Robolectric, or a single
pure function the selection must pass through** (ledger [I-103]). **The symptom
was visible in the implementation's own perturbation record** -- for stage 3
alone, what was perturbed was not production code but **the selection logic
inside the test**. **A perturbation that edits the test is not measuring whether
the test discriminates.**

**engine 20 (placement authority) stays out of scope** (ledger [I-077]). **No
fixture declares an arrangement, so the server generator needs a stage that adds
such cases before the port can follow.**

**Two files were stamped: `android/VERSION` and `android/BUILD_NUMBER`.**
`APP_VERSION` (`v2.9.31`) and `web/BUILD_NUMBER` (833) stand still, and **no
pentala deployment is needed**. **`android/BUILD_NUMBER` went 148090 -> 148091**:
Gradle raises it itself on every `install*` task, so it moves the moment the
build reaches a device (editing it by hand raises it twice). **Deployed to a
Pixel 9 (tokay) and observed starting as `versionCode=148091` /
`versionName=2.1.4-android.3`.**

### v2.9.32 — The background opens to all nine abstract colours, and a fourth block on gray comes out (Build 836, 2026-08-02)

**Across 2,061 production works the background was only ever three colours** — white 66.2%,
black 21.0%, blue 5.4%. Gray, red and green exist only before Build 700; yellow and orange
never appeared at all. **The schema was not what closed it**: both `Color` and the Stage 2
tool schema had declared all nine colours the whole time.

**What failed was delivery.** The rate at which the DDL asks for a non-white background has
gone up, not down (53% in the engine 20 period, the highest yet); what fell was the rate at
which the request arrives (92% in Builds 0–399 against 42% in 800–814). Both losses came from
deterministic machinery rather than model variance — **22 works to the coerce background
governor, 13 to the gray substitution in stage 1.5**.

**The governor never read the clause itself.** `_has_explicit_background_intent` judged only
the scene words of the original description — night, sunset, dawn — so "fill the background
with black", the description's own instruction, was never consulted. The function returned
False for all 22. **An explicit clause must not need a sunset to be believed**, so the clause
is now part of the judgement.

**The stage 1.5 substitution and the five-colour prompt wording are gone.** The prompts wrote
the foreground in nine colours while **the background text alone stayed at five**. Thirteen
sites carried it, seven of them in Android's `WebDdlSpec.kt` — which turned out to hold **two
LiteRT prompts with no server counterpart, phrased differently**: "gray backgrounds are
forbidden, use gray in the foreground" names no five-colour set at all. **A check that looks
only for the five-colour set stays green while that line survives.**

**Then a fourth block appeared.** With stages 1–3 in place, 60 descriptions measured under
production conditions showed stage 1 producing the gray clause 20 times and stage 2 returning
`background="gray"` 19 times — and **all 19 coming out of coerce white**. `coerce_score` called
`_visible_background` at its entrance, **turning gray white before the governor ever ran**.

**That mechanism was a second, redundant guard.** With it removed, gray-on-gray stays legible
through the foreground rule alone (`background: gray` / `color: black` / a note saying
`made visible`). The two assertions that turned red were defending **the old shape in which
both sides move**, not legibility itself, so they were inverted: the background stays gray and
the foreground goes black.

**Opening an exit is not the same as being used.** Yellow, orange and purple backgrounds have
never once been requested in production, so an open exit need not produce them. **Gating on
demand that does not exist would fail a correct implementation**, so it is not part of the
acceptance.

**The renderer is untouched** (still render engine 20). The frozen corpora `ddl-engine-4` (33)
and `render-engine-20` (525) are byte-identical, because **not one corpus case traverses this
layer** — green here is not evidence of correctness but evidence that nobody was looking.
Seven new assertions carry the acceptance instead.

### 2026-08-02 — The specification stops delegating to empty READMEs (**no version bump**, documentation only)

**The specification correctly declared that the module layout is not listed in it, and pointed at
`server/README.md` / `web/README.md` / `cli/README.md` as canonical instead.** Issue ledger
[I-087] was filed saying two of the three were empty; **a fresh measurement showed that none of
the three described an internal layout.**

- `server/README.md` is **0 lines**
- `web/README.md` is 42 lines of the **untouched SvelteKit template** (`# sv` / `npx sv create`)
- `cli/README.md` has 1,000 lines but **zero mentions of `.py`**. Its headings are three usage
  recipes and `## Command Line Help Reference`, and **the 960 lines from line 39 on are a
  machine-generated copy of `--help`**. The cli package itself is two files, `__init__.py`
  and `cli.py`

**Length was substance, but not the delegated role.** "Only `cli/README.md` is written" took the
line count as a proxy for the contents; **the third one was not functioning either.**

**The description already existed elsewhere.** "The current state of the product" in
`PROJECT_CONTEXT.md` holds, in the present tense, the per-feature directories and the three
registries for web, and the names of the ten router files, the five shared modules, the
one-way dependency, and the two enforcement points of authorization for server (the Japanese
`PROJECT_CONTEXT.ja.md` holds the same). **Rather than fill an empty canonical source, the
specification now points at where it is written.**

Outside those two lines in the Japanese and English specifications, **not one tracked file
references `server/README.md` or `web/README.md`** (`check_docs.py` only pairs the root
`README.ja.md` / `README.md`; it never looks at a package README). The READMEs themselves
were not deleted.

**The two adjacent items had already been resolved between filing and this cycle** — the "API
routes = `api.py`" line now names `api_core/routers/` (ten files) and the role of `api.py` in
both languages, and the struck-through claim that the giant UI component was resolved in v1.20
disappeared with `dc71ff4b` (the change that moved the list of open items out of the
specification and into the ledger). **Only the delegation line was left.**

### Android `2.1.4-android.4` — the mascots stop being emoji, and two settings that did nothing are removed (android Build 148091 unchanged, 2026-08-02)

**What Android called a ported mascot was not a ported drawing.** `IncuMascotView` was a `Row`
of `Text("🧊")` and a label, `YuragiMascotView` the same with `Text("🦀")`; **not one line of the
151-line and 208-line web components had arrived**. The 5x5 pixel grids and their animations now
live in **pure Kotlin data plus a Compose Canvas**. Incu orbits every 15 seconds while each pixel
runs a 4-second vortex breathe and the three incubator pixels change colour on 5 / 6 / 7-second
periods. Yuragi steps sideways every 1.5 seconds, waves its left claw every 11 and its right every
8, blinks on a 7-second period (the right eye has one extra wink), and blows bubbles every 12.

**The material was extracted into pure Kotlin for the sake of the gates.** Composable functions
cannot be exercised from a JVM unit test (Robolectric is not installed). **Putting the material —
the 25-cell table, the colours, the periods — in an object free of Compose types makes it testable
without a device and without Robolectric.**

**Two settings did nothing when pressed.** All 16 occurrences of `showKiwi` / `showCrab` were
state, persistence, and a settings row: **no composable ever drew a Kiwi or a Crab**. They are
gone. **The `show_kiwi` / `show_crab` rows already stored on the server were left alone** — they
simply lost their reader.

**The mapping table in `ANDROID_SPEC` pointed at a canonical source that no longer exists** —
`KiwiMascot.svelte` is gone from web, where `web/src/lib/components/` holds `IncuMascot.svelte`
and `YuragiMascot.svelte`. Both language versions now describe what was actually ported.

**Counts did not hold the picture.** During acceptance, **moving one leg a single cell sideways,
and swapping the breathe delays of two cells, both left all 127 tests green**: red 13 / eyes 2 /
empty 10 still held, and so did the set of delays. **The assertions now compare all 25 cells
against the web original**, and both perturbations turn red. **The control perturbation — reversing
the order of the table — stays green**, because the drawing derives its position from `cell.x` /
`cell.y` rather than from the order.

Unit tests go from **118 to 127**. **Not one line of `web/`, `server/`, or `cli/` changed**, so
there is no pentala deployment.

### v2.9.33 — `thinness` gives up the tail, and `surface` takes its seat back (`ddl_engine_version` 5, Build 837, 2026-08-03)

**Stage 2's output had halved.** The author's observation was that the same DDL now drew a picture
whose fill was poor, whose shapes were small, and whose impression was faint. **The cause was
v2.9.5, which moved `Instruction.thinness` to the end of the declaration.** The tool schema reaches
the model with its property order intact, and **an optional field is filled more often the further
back it sits** — that rule was already in the specification. **What was not written down is that
there is only one seat at the tail.**

**When `thinness` took it, `surface` lost it.** Calling production `compose()` and swapping nothing
but the tool schema's order, across 168 runs, `surface`'s carry went **92% → 42%**, the median
output fell from **172 tokens to 94.5**, and instructions per run from **2.45 to 1.43**. Because
nobody wrote `surface.opacity` any more, **its schema default of 0.28 — unchanged since v1.71 —
became the production value** (median 0.60 → 0.28 across 41 same-description groups in the
production database). **The element count did not drop. The same number of marks came out thinner,
fainter and smaller.**

**`thinness` now sits immediately before `surface`, and the tail belongs to `surface` again.** The
field itself — type, default, description — did not move by a character; only its position did.
`thinness` carries 67% here rather than 89%, but **this is the position that does not shrink the
rest of the Score**. **Making it `required` measured worse**: across 28 paired same-description
runs, `surface` rose in none and fell in eleven, and the output shrank further.

**The corpora cannot serve as the gate.** Neither `gen_render_reference.py` nor
`gen_ddl_reference.py` imports `composer`, so **the reference corpora never traverse Stage 2**. The
v2.9.5 commit message said in as many words that the frozen corpora stayed byte-identical: **the
checks correctly reported "nothing changed" while the regression walked through.** The acceptance
therefore watches **Stage 2's fill rate itself** — a probe that inspects the deployed declaration
order before it runs, and refuses to run against the old one, measured 28 runs at **93.3%** surface
presence (threshold 65%), **62.2%** thinness carry (40%), a median of **165** output tokens (130)
and **2.25** instructions per run (2.0).

**Four artifacts held the declaration order**: the server's `schema.py`, the port's copy of the tool
schema, the port's fixture (both tables in `score_schema_contract.json`), and one Android test.
**Of the three edges between them, only one was watched** — checks now cover `server ↔ Kotlin` and
`server ↔ fixture`, together with an assertion that **turns red if a new optional field is appended
after `surface`**.

**`ddl_engine_version` rises from 4 to 5.** The deterministic layers did not change by a line, and
`ddl-engine-5/` is byte-identical to `ddl-engine-4/` across all 33 cases with an empty
`changed_from_previous`. **That emptiness is what the declaration-order reason looks like**, and
this is the second time the version history has recorded it.

### v2.9.34 — the performance stops reading libm's last bit (render engine 21, Build 838, 2026-08-03)

**CI, the only automatic check this repository has, had been red for 22 consecutive runs since
2026-08-01.** Only the `render-engine` job of the `reference-corpus` workflow failed; `ddl-engine`
stayed green. **Everything merged since 2026-08-01 went in without that backstop.**

**The cause was that the performance seed hashes the coordinate before it is printed.**
**macOS libm and glibc disagree by one ULP on `sin`/`cos`** — of 60 identical arguments,
`sin(t·2π)` differs for 9, `cos(radians(t·360))` for 7 and `sin(radians(t·360))` for 10
(Python is 3.12.13 on both). That reaches group G's expanded coordinates as 1-8 ULP, and
`_fit_group_to_anchor` averages every point, so it spreads across the whole group.
**`_seed_for_instruction` then hashes the entire instruction dump, so a difference of
5.551115123125783e-17 turns the seed from 7178797595915484867 into 2693192989206796227.**
A different seed is a different tremor, which is 0.08-0.17px in the drawing.

**When engine 11 put every number on a six-decimal grid, the note said the drawing would from
then on be the same on any OS. What agreed was the printed number, not the seed that reads it.**
Six decimals do absorb the one-ULP difference everywhere else — **the 493 cases of A-F were
byte-identical across the two platforms** — and only the arrangement path, which feeds a hash,
amplified it.

**The coordinates `_expand_arrangement` returns are now quantised to 9 decimals.** 1e-9 of a
normalised coordinate is 1e-6 px on a 1000px canvas, below what the SVG prints, so it cannot be
seen. **All 525 cases were measured to agree on both platforms** (6 differed before the change).
**32 cases move, all of them in group G**; not one of the 493 A-F cases does.
`render_engine_version` goes 20 → 21 and `render-engine-21/` re-freezes the 32.

**"identical on both platforms" cannot be an acceptance gate, because one machine cannot observe
it.** Instead the gate perturbs `sin`/`cos` by exactly one ULP locally and requires the drawing to
stay put (`test_render_platform_stability.py`), **paired with a test that the same perturbation
moves 12 cases once the quantiser is removed** — without it, a perturbation that stopped reaching
the renderer would leave the first test green. The discrimination was measured before the work
started: 12 → 0.

**Three existing checks compared against unquantised expectations and were repaired.** Two of them
held a quantised expansion against an unquantised layout, so they **were reading the rounding
rather than what the fitting stage did**, which is why they exist. `check_frozen_corpora.py` no
longer prints "CI will be green.": **baking and comparing on one machine cannot promise it.**

### v2.9.35 — the unreachable island in `api.py` is deleted (Build 839, 2026-08-03)

**The nine symbols the v2.9.24 router split left behind as "outside a pure relocation" are gone:**
`_DEFAULT_OUTPUT_DIR`, `_OUTPUT_DIR`, `_OUTPUT_PNG_SIZE`, `_HEX_COLOR_RE`, `_validated_color_map`,
`InterpretResponse`, `_bearer_token`, `_can_manage_user` and `_strip_anthropic_prefix`.
**Every reference to them across `src`, `tests`, `cli`, `web`, `scripts`, `shared` and `android` was
its own definition line.**

**They form one island and could only go as one piece** — the only reader of `_DEFAULT_OUTPUT_DIR`
was `_OUTPUT_DIR`, and the only reader of `_HEX_COLOR_RE` was `_validated_color_map`. **Nothing
outside the island referred to any of them.** `import re`, `Header` and the two `pydantic` names
died with them and were removed too.

**The environment door stays open.** `INKU_OUTPUT_DIR` and `INKU_OUTPUT_PNG_SIZE` are read by
**`db.py:374-375`** with the same defaults; that is what the entries in `SETUP.md`,
`manual/{ja,en}/server-configuration.md`, `SPEC.md` and `.env.example` have always rested on, and
what was deleted was **a dead copy reading the same variables**. Stripping the `Bearer ` prefix also
has a live counterpart elsewhere (`api_core/deps.py`).

**`ruff` sees unused imports but not unused module-level definitions**, so nothing was stopping
these, and **the next split will accumulate the same kind of residue**. **The checks were measured
to have teeth**: deleting the *live* `_catalog_render_color_map` from api.py turns two tests red.

**`_catalog_render_color_map` was kept.** It is a different kind of residue — referenced only from
two tests — and removing it is a decision about those tests (the ledger holds it separately).
`api.py` went from 251 lines to 196.

### v2.9.36 — a trashed work no longer reaches the operations that act on a work (Build 840, 2026-08-03)

**`db.get_items` filtered on owner and id alone and carried no trash condition.** Its seven
production callers — animation export, output-file rebuild, SVG fetch, neighbours, lineage and
refine advice — **all handled trashed works as if they were current**. This was noticed during the
v2.9.13 animation-export review and not fixed then (ledger I-094).

**The ledger's "the UI cannot select them" was wrong.** The selection and the tool buttons in the
history panel **carry no conditional block, so the trash view shows the same ones**. Measured:
`/api/history/export-animation` with two trashed ids **returned 200 and a GIF**. This was never
limited to hand-sent ids.

**`get_items` now skips the trash, and no path is lost by it.** The trash view's listing is a
separate query (`list_items(trashed=True)`), and **the UI already blocks loading a trashed work
onto the canvas**: `loadItemAndClose` returns early unless the view is `active`. With the exclusion
in place, `export-animation`, `/svg`, `/neighbors` and `/lineage` return **404**,
`rebuild-output-files` reports **count 0**, and **the trash listing still returns 200 with total 2**.

**One existing check used `get_items` to ask whether a row survived a rejected purge**, and now asks
the listing that owns the trash. **The new checks were measured for discrimination**: removing the
exclusion turns all three red, while a **control perturbation that keeps the property** (reordering
the conditions and writing `!= 1` for `== 0`) leaves them **green**.

### v2.9.37 — the trash view stops offering the buttons that make a file from a work (Build 841, 2026-08-03)

**v2.9.36 made the server refuse a trashed work, but the buttons stayed on screen.** The two
contact-sheet buttons and the animation export in the history panel carried no conditional block, so
the trash view showed them and pressing one **only produced a 404**. **All three now sit behind the
same `historyManagerView === 'active'` guard the move-to-trash button already used.** **What remains
in the trash view is restore and permanent delete, and those are outside the guard.**

**The contact sheet is built on the client and never reaches the server** (`findSelectedItem`
resolves from the items already on screen). **It did not 404, and it was hidden anyway**: once the
server has decided that a trashed work is not something to act on, leaving one way to make a file
from it is not coherent. **The lineage panel's contact sheet is out of scope** — it resolves from
the displayed graph and was measured not to go through `get_items`.

**⚠ This web app has no component-rendering harness**: `test:unit` is `node --test` with no DOM.
**So the new check reads the source and walks the `{#if}` nesting.** **Handling `{:else}` is the
point**: restore and permanent delete live in the `{:else}` of that very guard, so a walk that
ignores else reports them as guarded by it (**which happened while writing this**). **The assertion
is paired with its control** — the three work tools inside the guard, restore and permanent delete
outside it — and **its discrimination was measured** by removing the guard, which turns one red.
**It does not see what a browser paints.**

### 2026-08-03 — The specification stops describing a mascot the web no longer has (**no version bump**, documentation only)

**The specification described a kiwi mascot in three places** ([I-105]).  **Measured, `kiwi` appears
0 times in `web/src` and `server/src`**; what exists is `IncuMascot.svelte` (a cube built from a 5x5
pixel grid) and `YuragiMascot.svelte` (a crab).

- **`Incu` turns slowly, once every fifteen seconds.  `Yuragi` raises its left claw every eleven
  seconds and its right claw every eight**
- **Which one appears is chosen in settings** (the default is `Incu`), through the radio buttons in
  `SettingsModal.svelte`
- **No screen has a mascot of its own** — `RunStatus.svelte` renders the selected one, and **seven
  components use it**: single drawing, batch, demo, the DDL editor, the genealogy panel, and the
  refinement modals

**So "the batch mascot is a small crab" was wrong twice over** — there is no batch-specific mascot,
and the crab is one of the two selectable ones.  **That paragraph is deleted in both languages.**

**The paragraph enumerating the kiwi's behaviour is replaced by one sentence for each of the two
mascots** (author decision 2026-08-03; "cut it down to the bare fact" and "write it at the kiwi's
density" were both offered, and the middle was taken).  **The same three places are fixed in both
languages, and `check_docs.py` is green** (55 internal references).

**The same claim was alive in `docs/spec/implementation-status`** (one line in each language),
and was fixed too.  **`docs/history/changelog-v0.1-v1.71.md` is left alone** -- it records what was
true at the time rather than describing the present.

### v2.9.38 (Build 843) — a sketch-from-life layer sits between the description and Stage 1

**A description as dense as a tanka is more than Stage 1 can chew at once.** A new layer between
the description and Stage 1 rewrites it as **plain prose naming things** -- a sketch from life --
and hands that to everything downstream.

**The same string reaches all five consumers** -- Stage 1, the plugin expansion, Stage 1.5,
Stage 2 and coerce. **If even one of them still read the description, the range the layer exists
to open would not appear.** **The description itself is kept for saving and display**: the work is
what the author wrote, not what the layer wrote.

**The granularity `sketch_grain` has two values** -- `fine` (many short sentences, the default)
and `coarse` (fewer, longer ones). **The total length is about the same; only the cutting differs**
(measured: fine 10 sentences of 9.6 characters, coarse 4 of 21.2). **It is chosen per draw and
from the work menu.** **Redrawing with a different grain writes a `sketch_grain_change` edge**
into the genealogy; the same grain stays a replay.

**When the layer fails, the description goes to Stage 1 and the paint still completes.**
**A failed attempt is not recorded as prose** (one occurred in 240 production-scale runs).
**A saved work redraws from its stored prose** without calling the layer again.

**`buildEmotionHint` is gone** (I-112). It detected 16 words of feeling and appended
"reflect the emotional word in the DDL" to `stage1_input`. **It fired on 6.1% of 2,125 production
works, 78% of those from the single rule for "quiet", and the `silverpoint` it named was never
once chosen.** **It also could not coexist with the layer**: `stage1_input` outranks the
description, so leaving it in would have let Stage 1 alone read something the other four never saw.
**The `stage1_input` field itself stays** -- the CLI uses it for its own purpose.

**The gates are T-1, T-2, T-3 and T-5 through T-10.** **T-3 (the sparse-to-dense range) measured
2.40 pooled over four repetitions** against a threshold of 1.8.
**T-4 (semantic carry) was replaced.** Counting marker words cannot tell **translated** from
**lost**: for poem 06 the prose said "it is night" and the DDL said "fill the background with
black", and because the `night` family holds only the two tokens `night` and 夜, the gate scored
that a zero. **A DDL that carries no words of meaning is the design, not a failure**
(SPEC section 13.3, design principles 3 and 7). **The replacement measures the picture instead,
as a controlled experiment, and moved to stage 0 of the follow-on contract** (I-118).

**Acceptance closed one hole of its own.** **The prose stands in for the description at two read
points** (`/api/paint` and `/api/interpret`). **Removing the substitution from the interpret one
left all 2163 tests green**, so three assertions were added on that path as well: the prose
arrives, the layer-off control still travels as before, and `stage1_input` no longer outranks
the prose.

**The frozen corpora are byte-identical** (`render-engine-21` 525, `ddl-engine-5` 33).
**No corpus case passes through Stage 0.5 at all**, so this is a regression guard, not evidence
that the change works.

### v2.9.39 (Build 845) — "From the description" becomes one of the color catalogs, and the choice is the user's

**The batch tab's "Choose a color catalog from each description" checkbox is gone; the color
catalog dialog now offers "From the description" above the thirteen.** The demo panel's second
copy of the same checkbox (the `catalog_mode` its per-user settings held) is folded in as well.
**A single draw could not reach the automatic choice at all** -- it existed only in the batch and
demo tabs, although the mechanism has been in `/api/paint` all along.

**The selection is stored per user on the server** (`model_settings.color_catalog_id`), not in
localStorage: **every render route requires a session, so nothing can be drawn while logged out**
(`_current_user` has no anonymous mode, and all six unauthenticated routes serve the login
screen). A browser-wide value would only ever be another user's selection. **No migration seed was
kept**: it would leak one user's choice to the next user on the same browser, so existing users
start again at inku Default.

**The `auto` sentinel does not leave its module.** Sixteen places read the selection directly, and
eight of them send or store it as a `catalog_id` (history payloads, lineage, refinement,
comparison). The translation sits in the one render-payload contributor, so everything downstream
receives a catalog that exists -- only `/api/paint` can carry `catalog_mode`, and the sentinel
would be a 422 anywhere else. **Stored artworks do not inherit the automatic choice**: refinement
and redrawing read the artwork's own catalog id.

**The server stores only a catalog that still exists, or `auto`.** A retired id falls back to the
default, since storing it would just answer 422 on the next drawing.

**The gates were measured by perturbing production code**: not translating the sentinel turns 2
web tests red, dropping the field from the patch path turns 3 server tests red, removing the
allowlist turns 2 red, and taking the choice out of the modal turns 1 red. **The control** (change
a catalog's colors, leave the transport alone) **stays green on all 12.**

**The API surface lost exactly one field**, `catalog_mode` on `DemoSettingsBody` (endpoints 81,
operations 81, schemas 80 unchanged). The frozen corpora are byte-identical.

### v2.9.40 (Build 846) — a leading number and a bracketed comment are the writer's, not the drawing's

**A batch numbers its lines, and a description often carries its source in brackets.** Both were
travelling into Stage 0.5 and everything after it. They are now **cut once, at the three endpoints
that read a description** (paint, interpret, compose), and **the stored work keeps them**: saving,
display and the response still read `req.description`.

**Digits count as a number only with a separator** (`.` `．` `、` `)` `）` `:` `：`, or an
ideographic space), so `2026年` and `3本の線` stay description. An **unclosed `[` is description**
too and does not swallow the rest of the line. Both `[]` and `［］` delimit a comment.

**The describe and batch editors grey the background of those characters.** A textarea cannot
colour a range of its own text, so **an identical copy sits behind it and paints only the
backgrounds** (`LabelHighlight.svelte`: 9px 10px of padding, 13px, line-height 1.65 -- the same
metrics as both editors -- and the batch layer follows the sideways scroll without wrapping).
**Because the rule now exists in Python and in TypeScript, both are measured against one corpus**
(20 cases in `server/tests/data/description-label-cases.json`; **drifting the web rule away from
the server's turns 9 web tests red**).

**The single-draw character meter counts what the drawing reads**, not the writer's numbering.

**The gates were measured by perturbing production code**: not calling the rule on the paint path
turns 3 server tests red; disabling the number rule, 23; narrowing the separator to `.`, 9; letting
an unclosed `[` run to the end of the line, 6; drifting the web rule, 9 web tests; handing the
layer no text, 1. **The control** (a darker grey) **leaves all 99 green.**

### v2.9.41 (Build 847) — the layers that run after the plan exists read the DDL alone

**The `description-propagation-cut` contract (implementation session, Opus 5) is accepted.**
The prose from Stage 0.5 reached **all five consumers**; **two of them -- Stage 2 and coerce -- are
cut**, leaving Stage 1, the plugin expansion's firing decision, and Stage 1.5.
`ddl_engine_version` **5 -> 6**, frozen corpus `ddl-engine-6` (33 + 3 production-shaped cases).

**One background guard was withdrawn.** What it judged was the *provenance of a string* (had the
user pasted a machine-generated plan into the description box), and once the description no longer
reaches coerce there is no provenance left to judge; keeping it misfires on the ordinary shape of a
production DDL -- **54 of 604 dark-background works fell to white with it, 1 without** (a
counterfactual over 2,023 production works, no model calls).

**The plugin's seed is the description again.** With the prose as the seed, the same description
resolved different counts whenever the prose changed. The gate measures **resolved numbers**, in
**both directions and at every entry point** (same description x two proses -> alike; same prose x
two descriptions -> apart).

**The carriage instrument gained its other direction** ([I-107]): `carriage.py` only watched for
what was dropped. **That direction could not be measured before the cut** -- while coerce read
`prose\nDDL`, anything it added traced back to something the author wrote, and an addition was
indistinguishable from a delivery.

**Stage 2 did not shrink** (20 poems x 2 repetitions x 2 arms, 80 runs, 0 failures): median
`tokens_out` 270 -> 273, and no field lost its seat. **What coerce authored fell from 87 to 74
(-15%)**, which is the layer writing less now that it is given less. **Additions that answer no
clause stayed at 6**: the DDL became the only *route*, not the only *author*.

**Android took the same cut and the same withdrawal** (133 JVM tests, 5 on a Pixel 9).

**One thing fixed during acceptance**: the merge left `plugin_seed_text=req.description`, so
**v2.9.40's rule -- a leading number and a bracketed comment reach no layer -- was bypassed by the
seed alone.** It now reads the cut description, and a gate watches the seed.

**Two tests failed only after the merge**, because v2.9.40's gates carried the pre-cut assumption
that Stage 2 receives a description; they were moved to the current shape with the property intact.
**No test was deleted** (the three names missing from main are the renames the report declared,
rewritten as inversions with a new control).

### v2.9.42 (Build 848) — a sender that stays quiet gets the defaults drawn

**The `cli-feature-parity` contract (implementation session, Opus 5) is accepted.**
`/api/paint` takes one request model, but **each sender names a different number of keys**:
of its 37 fields the **web UI sent 33 and the CLI 17**. The **eight that change the drawing**
are now named by the CLI -- `sketch`, `sketch_grain`, `sketch_text`, `variation_amplitude`,
`variation_seed`, `wild`, `catalog_mode`, `interpretation_seed` -- spelled straight from the
server's request keys, and accepted by both `paint` and `batch`.

**No drawing made from the command line had ever had a sketch.** An unnamed field is not an
error: pydantic fills the default and returns 200. Stage 0.5 is **on by default in the web UI
and off by default on the server**, so the 51 runs under `cli/out2/`, the benches, and the
reference corpora had **never once gone through that layer**. This version is the first time
it fired from `inku-cli` (two real drawings: the saved work has a non-empty `sketch_text` and
`sketch_grain` `fine`; without the flag both are `null`).

**Not one default changed.** With no flags the request body is identical to the previous
version (measured: same keys as before, the dict's 17 unchanged, 25 with all eight passed).
`False` is not `None`, so dropping the `or None` would put an eighteenth key on the wire for
every existing run.

**The artifact JSON now names three keys explicitly** -- `sketch_text`, `sketch_grain`,
`sketch_fallback_used`. The response omits null fields, so copying it through means
**"Stage 0.5 was not asked for here" is indistinguishable from an older CLI, an older server,
or a truncated file**.

**A roll call of the senders is in place** (`server/tests/test_cli_sender_census.py`). It
enumerates `PaintRequest` and asserts that every field either appears in `_paint_payload` or
sits in an **excuse table of 12** (nine history/lineage fields, `color_map`, `history_at`,
`auto_repair`), each with its reason. **It also states how many it looked at**, so an
enumeration that silently empties out cannot pass. The CLI lives in its own virtualenv, so the
census **reads `cli/src/inku_cli/cli.py` as text and parses it with `ast`**, and **skips when
the `cli/` directory is absent** (pentala holds a partial tree). The 14 existing `TestClient`
suites missed this because **every one of them names the fields it tests**: nothing was
watching what happens to a client that stays quiet.

**The usage block in `cli/README.md` was three generations stale** -- `--original-text` (now
`--description`), `--vary-seed` / `--vary` (now `--composition-seed` / `--composition-count`),
`--staffage` and `--trace` missing, the positional described as `prompt text`. It is
regenerated from the parser. **Nothing yet goes red when the next flag skips the manual**; how
to close that is [I-127].

**No server production code moved** (frozen corpora `ddl-engine-6` and `render-engine-21` are
byte-identical; the only change under `server/` is the census test itself).

### v2.9.43 (Build 849) — the work writes down what the sketch layer did

**An empty `sketch_text` meant four different things at once**: the work predates the layer,
the author switched the layer off, the route never calls it, or **the layer ran and fell
over**. The fourth was recorded nowhere, so **a layer that collapsed was stored exactly like a
layer that never ran, and nobody could count how often Stage 0.5 fails in production.**

`history.sketch_state` was added **with no default and no backfill**, so `NULL` keeps exactly
one meaning: **this row was written before the column existed**. There are five values:

| value | meaning | `sketch_text` |
|---|---|---|
| `fine` / `coarse` | the layer ran and produced sketch prose at that grain | not NULL |
| `fallback` | **the layer ran, fell over, and the description was drawn as written** | NULL |
| `off` | the layer was available and the caller chose not to route through it | NULL |
| `not_applicable` | this route never calls the layer (no description: new from a plan, or DDL input) | NULL |

**One function names the state** -- `sketch_state_of()` in `server/src/inku_server/sketch.py`.
All three save paths and both responses go through it, so **"off" cannot mean different things
in different writers.** `POST /api/history` takes a state from the client (pattern-checked, so
an unknown value is a 422) and **derives one when the client says nothing**: a `NULL` written
there would claim a row created today predates the column.

**Two senders were dropping the prose entirely** -- the demo save in the web UI and the CLI's
own `POST /api/history`. **Work saved by the CLI recorded nothing about the layer, and read
back from the server as if it predated the column.** Both now carry all three keys.

**The web UI tells the four silences apart.** The grain menu marks "off" as not recommended.
**The note is a separate function from the label**, so it appears in the menu and nowhere else
-- not on stored work, the collapsed toggle, the current-value summary, or a parent's grain in
the lineage panel (five call sites, measured).

**A roll call of the writers is in place** (`server/tests/test_sketch_state.py`). It counts
**the syntax that writes `sketch_text`, via `ast`**, not line numbers, and **states the count
it saw (8)**, so an implementation that adds the column and fixes one path is rejected. Fifteen
perturbations, covering all five stages of the contract, were confirmed to go red.

**No existing row moved**: production `history` held 2,172 rows before and after deployment
(2,176 including the four drawn to verify), `sketch_text` is non-NULL on 23 rows as before, and
**all 2,172 pre-existing rows have `sketch_state IS NULL`**. The migration runs when `inku-api`
starts. `renderer` and `coerce` were untouched (frozen corpora byte-identical).

### v2.9.44 (Build 851) — the description is where the work comes from

**A description is not a record.** It decides whether a plugin fires, what Stage 1.5 reads as
context, what seeds the plugin expansion, and which language the instruction is written in --
**four things**. Yet the CLI carried a flag (`inku-cli paint --description`) that seated a
string which had not authored the DDL in the description's chair. **The flag is gone, and the
description is the text that was typed.** The positional argument is the legitimate one and the
exception is what deserves a flag (`refine perform --description` stays: it overwrites an
existing work's description, the same spelling for a different definition). A work authored
straight in DDL has no description, so **the `compose` payload drops the key entirely** -- the
same shape the web sends when it draws a new instruction sheet, and on both sides the seed
falls to the DDL.

**A description the cut empties is refused with 400.** v2.9.40 declared the author's leading
numbers and bracketed notes theirs rather than the drawing's and cut them out, but **a
description that is nothing but those** (`1. `, `[note]`, `３．`) still flowed down and **had
its subject invented from an empty string**. `/api/interpret`, `/api/paint` and
`/api/paint/stream` now guard it. **The judgement takes two conditions, not one**: an empty raw
description is already refused by `min_length=1`, and judging the cut alone would answer "only
labels" to a text that carried no label at all. **`/api/compose` is deliberately left
unguarded** -- it is the route that draws a sheet with no description, and guarding it breaks
the web's "new instruction sheet". **Across 2,023 production works, none hit this guard** (the
14 with a `[demo]` prefix all keep a body after the cut).

**A description that is only whitespace is refused with 422.** `min_length=1` counts
characters, so `'   '` passed, and with no label present no cut happens either. **The web never
reaches this -- its send gate stops it -- but the CLI and Android do.**

**The web's send gate reads what the drawing reads.** The character meter already showed the
count after the cut, while the send button and the batch line count still measured the raw
text. **The same rule moved to the door**, so a description that is grey from end to end cannot
be sent. **No second rule was written.**

**The sketch prose left the seed chain.** When the plugin expansion got no seed, it fell back to
the sketch prose. **Stage 0.5 rewrites that prose on every run**, so v2.9.41's property -- the
same description draws the same counts -- **was being lost with nothing turning red** (SPEC
§12.15 states the property). The fallback now lands on the DDL: an empty seed that produced 14
elements (the prose's value) produces 16 (the DDL's), and **a seed that is given is the seed
that is used** (asserted in the opposite direction as well).

**42 tests across three surfaces** (36 server, 6 web, the CLI inversions). Perturbations were
applied per stage: dropping the guard from `/api/interpret` reddens only that route's 5,
dropping it from the shared generator reddens paint and stream's 10 plus the guard's own
property, dropping the blank validator reddens 3, putting the prose back in the seed chain
reddens 1, restoring the CLI flag reddens 2, and gating the page on the raw text reddens 1.
**The two tests that watched `--description` were inverted rather than deleted** -- they now
watch the retired spelling `--original-text` too, so an inventory taken by name cannot mistake
a rename for a deletion.

### Android `2.1.4-android.6` — the drawing layer catches up to render engines 20 and 21 (who decides where a group goes; a performance that does not read the last digit) (android Build 148091 unchanged, 2026-08-05)

**The port landed in seven stages.** (1) align the fourth copy of the declaration order
with the server, (2) carry the render seed into the expansion, (3) port the `grid` layout,
(4) turn a `radial` ring around the declared anchor, (5) bring a group's centre of mass to
that anchor (per-axis shrink against the 0.02 / 0.98 frame), (6) quantise expanded
coordinates to nine decimals, (7) declare the version as `"21"`. Android unit tests went
from 133 to 134 with no failures; two were red at the start because stage 0 had baked the
expectations first.

**The expectations were baked by the issuing side before the work began.** The 33 cases in
`renderer_arrangement.json` mirror the server's group G one for one, plus a grid that
states a region — engine 20's single carve-out, where a lattice tiling a stated region does
not go through the second stage. **The comparison is exact, with no tolerance:** two cases
differ by nothing but engine 21's quantisation, 4.9e-10, so a tolerance of 1e-6 lets a port
skip engine 21 and stay green on all 33.

**Acceptance found one divergence — not in the values, but in how a condition was written.**
The server reads `radius` for truthiness (`r = arr.radius if arr.radius else 0.3`), so a
stated `0.0` means "unstated" and the ring turns at 0.3. The port fetched it as
`optDouble("radius", 0.3)`, kept the declared zero, and collapsed all twelve marks onto a
single point. `Arrangement.radius` is an unconstrained `Optional[float]`, so Stage 2 can
emit that value. **No fixture stated a radius at all, so all 33 cases were green under
either reading.** `G-radial-zero-radius-edge` was baked from the server and added, and a
perturbation now turns one case red (34 cases; the other 33 are unchanged).

**That single case produced a project-wide rule (author ruling, 2026-08-05):** outside of
genuinely Android-specific concerns — OS features, hardware limits — both the decision and
the implementation follow the server. **Accepting a port means reading the conditions one
for one, not only comparing outputs.** Replacing a truthiness test with a defaulted getter
sends `0` and the empty string down a different path, and inputs whose values agree will
never show it.

**Stage 4 still has no gate.** Moving the `radial` centre back to the middle of the canvas
turns **0 of 134** tests red: that move translates the whole group, and stage 5 pulls the
centre of mass back onto the anchor immediately afterwards. Stage 5's carve-out applies only
to a grid with a stated `at`, which a radial layout never is. **A port that skipped stage 4
entirely would stay green on all 34 cases** ([I-130]).

**Perturbations were applied for all seven stages** (stage 1 turns `test06SurfaceHatchExactParity`
and the SVG scan red; stages 2, 3, 5-1, 5-2 and 6 turn `testArrangementExactParity` and the
SVG scan red; stage 4 turns nothing red). **Every perturbation targeted production code, and
all tests returned to green after each was reverted.** **`server/` is unchanged** — both
frozen corpora are byte-identical, and `APP_VERSION` and `web/BUILD_NUMBER` did not move.

### Android `2.1.4-android.7` — five judgments realigned with the server (emotion hint, Stage 2 concatenation, background governor, two temperings, version fallback) (android Build 148091 unchanged, 2026-08-05)

**None of the five was a missing feature; each was a different judgment written in the same
place.** The project-wide rule of 2026-08-05 — outside genuinely Android-specific concerns,
both the decision and the implementation follow the server — fixed the direction for all five,
so **which way to align was not the implementation's to decide**. Acceptance read the server's
condition against the Kotlin condition one for one rather than comparing outputs.

- **The emotion hint is gone ([I-114]).** `InkuRepository` looked up sixteen emotion words,
  built `[感情語をDDLに反映してください: …]`, and **appended it to `description` itself** before
  Stage 1. Neither the server nor the web client has this. **The web client fed `stage1_input`,
  so removing it on Android reaches further** — plugin firing, the Stage 1.5 context, the seed
  and the language all read that string. `stage1Text` is now `description` unchanged, and
  `emotionHint` / `emotionDdlMap` / `感情語をDDL` appear nowhere in the tree.
- **Stage 2 no longer carries the description ([I-125]).** The server cut this in v2.9.41:
  `user_msg = ddl`, one line. Android carried the original text down **two paths** —
  `buildStage2UserMessage`, which built `[原文]…[正規化DDL]…`, and `scoreFromWebRules`, whose
  context was `"$originalText\n$ddl"` — reached from three call sites. Both are cut, and
  `scoreFromWebRules` lost the parameter. `originalText` still feeds Stage 1.5 expansion and
  the records.
- **The background governor's vocabulary and its fourth condition ([I-126]).** The fourteenth
  surface marker, `dark field`, was missing on Android alone. **One word, but the picture
  changes**: for `dark field of thin lines` the server keeps the black ground while Android
  washed it white, because `細い` fires the density governor. The fourth condition had also
  drifted — Android's "colours present and no shapes" returned true for `青と赤で塗る`, which
  states no restriction at all. The server's `_color_only_constraint_from_ddl`, which requires
  `だけ` / `のみ` / `に限定` / `only` / `limited to`, was ported as `colorOnlyConstraintFromDdl`.
  **The explicit-clause regex was deliberately not ported** — the word list subsumes it, so no
  input exists for which it decides anything on its own.
- **The two temperings that had never been ported ([I-009]).**
  `_with_quiet_single_shape_tempering` and `_with_unintentional_filled_shape_tempering` moved
  across with the server's constants verbatim (single 0.34 / 0.24 / 0.17 / 0.14, filled
  0.42 / 0.30 / 0.20 / 0.20). **The filled tempering can never fire inside the density
  governor**: its area threshold (0.20) sits above the single-shape one (0.14), and the
  single-shape pass always shrinks the shape below it first. It is therefore wired where the
  server has it — as a standalone pass between `withPresenceAuxiliaryShapeRepair` and
  `withContextDensityGovernor`.
- **`renderHash` no longer defaults the engine version ([I-011]).** A missing
  `render_engine_id` / `render_engine_version` used to be filled with `"21"`; it now writes JSON
  `null`, because the server leaves an absent value absent. The existing test was **inverted
  rather than deleted** (`testRenderHashDefaultsMissingAndBlankMetadataToEngine21` →
  `testRenderHashPreservesNullEngineVersionWhenMissingInMetadata`, asserting that an absent
  version and an explicit `"21"` now hash differently).
- **Two shared helpers the contract had not named were also divergent.** Android's
  `closedShapeArea` multiplied by π (`arc` by ×0.35, `triangle` by ×0.5, and `cloudform` had an
  area at all); the server takes the plain products `radius * radius` and `size[0] * size[1]`
  and reads `arc` and `cloudform` as zero. Android's `capSize` clamped each axis independently;
  the server scales **proportionally, preserving the aspect ratio**, with a floor of 0.01.
  **Both feed more than the three temperings** — the background, large-shape and atmospheric
  judgments read them too (six call sites on Android, five on the server). With the scaling
  aligned, `triangle-open-plain` is expected at `[0.34, 0.1942857…]`.
- **Acceptance closed one hole in the gates.** The nineteen cases baked in stage 0 invoke the
  three temperings **directly through reflection**, so **unwiring the standalone pass from
  `normalizeServerScore` left all 135 tests green** — the expectations watched what the
  mechanism does, and nobody watched whether production calls it.
  `FilledShapeTemperingWiringTest` now goes through `normalizeServerScore`, taking the suite to
  136. Its expectation `[0.36, 0.30]` was measured by running the same input through the
  server's `coerce_score`; without the wiring the size reads `[0.6, 0.5]`, untempered.
- **Seven perturbations were applied.** Stage 2 turns the Stage 2 message red (1), stage 3
  `dark-field-black` (1), stage 4 `square-open-plain` (1), stage 5 `Engine19VersionTest` (1),
  restoring the old shared helpers `triangle-open-plain` (1), and unwiring the standalone pass
  the new gate (1). **Stage 1 turns nothing red: it has no gate** — the unit tests call
  `pipeline.paint()` directly and never pass through `InkuRepository`, so restoring the emotion
  hint costs nothing. Every perturbation targeted production code, and all tests returned to
  green after each was reverted.
- **`server/` is untouched by the three implementation commits** (the 86 lines of generator on
  the branch were placed in stage 0 by the issuing session), and the implementation did not
  edit `server_reference/`. **All 59 fixtures are byte-identical to what today's tree bakes**,
  which `test_android_reference_fixtures_are_current.py` checks by rebaking the whole corpus.
- **Verification:** Android unit tests **136 / 0 failed / 0 skipped**, server pytest **2341
  passed / 31 skipped**, cli **106 passed**, ruff clean, `npm run check` **245 files / 0 errors
  / 2 warnings**. `APP_VERSION` and `web/BUILD_NUMBER` did not move; `android/BUILD_NUMBER`
  stays at 148091 because only unit tests were run.
- **Explicitly not done:** [I-008] (the embedded Stage 2 schema divergence), [I-067] / [I-068]
  (the lineage data layer) and [I-064] (on-device espresso) are outside this contract and were
  not touched. `android/ANDROID_SPEC.ja.md` was not updated. Nothing was verified on the Pixel 9
  (JVM unit tests only), and nothing was deployed to pentala (`android/` is permanently excluded
  from every sync path).

### v2.9.45 — the limits gathered in one place, and a ceiling the model cannot raise (Build 852, 2026-08-05)

**This came out of the author's question of 2026-08-04: is it not dangerous, as a program, to
rely on the LLM for the upper bound on how many things get placed?** The numbers that bound a
count were spread across four files, and the same 240 had been borrowed four times under
different names. This version gathers them into `limits.py` and puts a ceiling in the
deterministic layer. **Not one default value changed.**

- **The limits moved into `limits.py`.** A frozen `Limits` dataclass holds eight values and every
  reader in `coerce/` now comes through it. **All the values were read off the tree as it shipped
  and none of them moved** (400 / 240 / 240 / 80 / 120 / 1000 / 2000 / 2000). **The one addition
  is `max_instructions = 64`.** The aesthetic governors (`MAX_QUIET_*` and the rest) deliberately
  stayed where they were: **they are not other names for these numbers, they are different
  numbers with a different purpose.**
- **Two bare literals were breaking the stated policy ([I-110]).** `min(count, 120)` in
  `compose.py` used **the top of the representation band as an unconditional cap**. The
  specification says a count under 240 is literal and names the case — "two hundred thirty-three
  lines" are drawn as 233 — yet the clause route cut that 233 to 120. Counting 2,172 works and
  6,419 arrangements in production, **6 of the 92 that landed exactly on the cap were this
  violation** (two distinct inputs, 233 and 137). The call now goes through `_budgeted_count`,
  which passes anything under the threshold and, above it, **defers to the same
  `_clustered_visual_count` the density governor uses** — so a count arriving by either route
  lands on the **same** number, not merely inside the same band.
- **There was no deterministic ceiling on the total (author ruling 2).** Both density governors
  exempt `grid` explicitly and **do not even add it to the total**. The instruction list had no
  bound at all (`schema.py` declares a bare `list[Instruction]`), and a single arrangement may
  reach 2000. **Five instructions at 2000 each is 10,000 marks — about 42 seconds on the Mac and
  roughly 35 MB of SVG** — and the only thing preventing it was **the prompt asking for one to
  five instructions**. **The hole is not hypothetical**: a work from 2026-07-18, well after the
  governors were introduced, totals 409 marks (400 from a grid, 9 not), and the governors never
  noticed, because they do not count the grid.
- **`_enforce_hard_ceiling` now runs last, on both exits from coerce, and answers to no layout.**
  A grid is counted by the marks actually drawn, `rows × cols` rather than `count`, and an
  oversized lattice drops to a smaller one **that keeps its proportions**. The instruction list is
  cut at 64 and the number dropped is recorded in the note. **A work already under the ceiling
  comes out byte-identical**, which T-6 watches as the control.
- **Eleven existing tests failed and every one was read before it was changed.** **Six of them
  recorded the old policy that a grid is excluded from the total**, which collides head-on with
  ruling 2. **The governors' exemption is still true**, so those assertions were kept by applying
  `_with_total_density_budget` directly, and a separate assertion now says the ceiling does reach
  a grid through the entry point. **Golden H-12 and H-16 moved from 48 → 233 and 64 → 233: the
  production violation itself had been baked into the golden file.**
- **Both frozen corpora are byte-identical** (`ddl-engine-6` 36 cases and `render-engine-21` 525
  cases, zero changed), so **the engine version does not move**. **That is a regression net and
  not evidence the change works** — the contract forbids using the corpora as acceptance and sets
  T-1 through T-9 instead.
- **Ten perturbations were applied, all to production code**, and acceptance reproduced two.
  **P4 (fixing everything above the threshold at 120) turns only T-4 red** — an implementation
  that stays inside the band while the two routes land on different numbers passes T-2 and T-3
  untouched, exactly the discriminating case the contract predicted. **P9 (applying the ceiling
  unconditionally) turns T-6 red**, which is what stops "just clamp everything to 400" from
  passing T-5.
- **Nine `inku-cli` runs reached none of the changed paths** (byte-identical between the base and
  HEAD). The clause route sits behind the `len(instructions) != 1` gate in `_with_ddl_coverage`
  and opens only when Stage 2 emits exactly one instruction. **As a control**, a shape that does
  open the gate splits **120 at the base and 233 at HEAD** — **the apparatus can detect the
  difference; the nine agreed because they never reached the branch.**
- **Three findings the contract had not anticipated:** three identical grids collapse to one under
  `_dedupe_instructions`, so T-5's fixture has to be three structurally distinct grids or it goes
  green without touching the hole; a literal request for four hundred becomes 401 because coerce
  adds a composition anchor of its own, and the ceiling then takes one cell off the grid; and a
  grid's real mark count is `rows × cols`, not `count`.
- **Specification:** a paragraph on the ceiling was added in both languages right after the
  paragraph on the total in §13.10 (that the total and the instruction count are bounded, grids
  included, and that this does not depend on what the prompt asks for). The existing passages were
  left as they were.
- **Verification (on the merged tree):** pytest **2358 passed / 31 skipped** (2338 → 2355 on the
  branch; 2341 → 2358 counting the three Android tests already on main), `def test_` **1189 →
  1200 with none deleted** (the three that exist only on main are the Android stage 0, because the
  branch was cut from an older main), cli **106 passed**, ruff clean, `npm run check` **245 files
  / 0 errors / 2 warnings**, and `check_frozen_corpora.py` byte-identical.
- **Explicitly not done:** **making the values configurable belongs to the follow-up contract
  `limits-are-settings.md`** (settings, records, UI, Android). This version has no setting and no
  UI, and does not touch `renderer.py`, `schema.py`, the prompt text, `web` or `android` by a
  single byte. **[I-132]** (three of these numbers still inline outside `limits.py`) was left
  alone because the behaviour is identical while the values do not change. `ANDROID_SPEC` was not
  touched, and resvg rasterisation time was not measured (SVG generation only).

### v2.10.0 — the limits become settings, and the values a work was drawn under stay with it (Build 853, 2026-08-05)

**v2.9.45 gathered the nine limits into one place; this version makes them settable.**
**A per-install setting does not break reproducibility because the effective values are recorded on
the work** — the version identifies the code, the recorded limits identify the configuration, and
the two together decide the behaviour. `history.render_limits` has **no DEFAULT and no backfill**:
`NULL` on an existing row means "drawn before this column existed", not "drawn at the defaults"
(the same discipline as `sketch_state`).

- **The setting is read once per request** (`_effective_limits()`), with no in-process cache (it
  would go stale across workers). **All five call sites of `coerce_score` were given `limits=`** —
  redrawing a history SVG, `POST /api/history`, `POST /api/compose`, `POST /api/render-score`, and
  the generator shared by `/api/paint` and `/api/paint/stream`. **Only the count rounding inside
  `Score.model_validate` cannot take an argument** (it is a pydantic validator), so the five paths
  raise both an explicit argument and a context variable from the same single `Limits`. **Code
  outside a request — the generators, most of the tests — runs on the defaults.**
- **The effective values are injected into the prompts.** The contract counted ten places where the
  text carries a number; **the measurement found 12 + 8 + 1**: the 400 of
  `max_expanded_primitives` twice per language in `composer.py`, `ddl_count_max` and
  `ddl_count_max_grid` in four places per language in `interpreter.py`, and **the description of
  `count` in `schema.py`**, which reaches the model as tool schema and enters
  `stage2_prompt_digest`. **Leaving the 400 alone would have let the prompt lie the moment
  `max_expanded_primitives` moved**, so ruling A added it. **Nothing is generated wholesale — only
  the numbers are substituted.** A density band such as `40-120` has a ceiling only at its upper
  end; the inner edge is prose about density, so the values are clamped rather than scaled (scaling
  would invent a number nobody chose).
- **`Field(le=2000)` was removed from `schema.py`.** Removing it drops `maximum` from the JSON
  schema, which changes the tool JSON and **moved the digest at the defaults** (`5dc72855…` →
  `73e56ff2…`). The two were reconciled by having **`_score_tool_schema()` put the effective
  `maximum` back at the same key position pydantic used**; key order is untouched because of
  [I-038] (declaration order moves how much is carried).
- **A Limits tab in the settings** (admin only, all nine editable, three families, a reset control).
  **The family names and their order come from the server** (`LIMIT_GROUPS`), so the UI cannot
  invent a fourth. **A rounded value is shown as it came back**, not as it was typed.
- **Android points the bare 240 in `clusterCount()` at `LITERAL_COUNT_THRESHOLD`.**
  **`MAX_EXPANDED_PER_INSTRUCTION` was deliberately not used** — it is 240 at the defaults but a
  different field on the server, and aiming at it would assert an identity that does not exist. The
  `120` in the same function stays bare.
- **The CLI got full control (ruling B)**: `config show` returns `render_limits`, and `config
  update` carries all nine flags plus `--limits-reset`, **sending only the flags that were given**.
  The help block in `cli/README.md` is the generator's output, not hand-written.
- **Two assertions in the contract turned out to be false.** The parenthetical "invalid values are
  rounded, not refused (the same manner as the existing normalizers)" is wrong: **both normalizers
  it named raise `ValueError` out of range**. Since §2.4 asks for the rounded value to be displayed,
  **rounding was kept and this setting now differs in manner from the other four**. And
  `DEFAULT_LIMITS` has **13** default arguments, not the contract's 14 (an import line was counted).
- **The acceptance is `server/tests/test_limits_are_settings.py` (15 checks, T-1..T-12); the frozen
  corpora are not used as evidence.** All six perturbations hit production code only. **The
  acceptance was strengthened twice during them**: a Japanese-only revert left T-2 green because the
  English side still moved and "something moved" was enough, so it was rewritten as an exact set of
  which prompt in which language must move; and the same threshold was enforced by two lines of the
  Japanese prompt, so the enforcement points were counted and both were hit. **T-2's reverse leg was
  rewritten away from the contract**: ruling A made "same threshold, different budget → the text is
  unchanged" vacuously false, so the leg now uses **`max_instructions`, the one limit that appears
  in no prompt at all**.
- **Added on acceptance: four gates for the CLI** (`cli/tests/test_cli.py`). **The nine flags and
  the new `PUT /api/settings/limits` that ruling B introduced were watched only by "the four-area
  count finds at least one hit in cli", and a misspelled key would stay silent at 200.** The gates
  pass a distinct value per flag and match the request body one for one, assert the update is
  partial, and keep a control (no flag, no request). **Three perturbations** were applied — send
  every field, rename one key, make `--limits-reset` merge instead of replace — and **the third
  found nothing**: passed on its own, `--limits-reset` produces `{"reset_to_defaults": True}` under
  both implementations, so replacing and merging are indistinguishable. **It was rewritten to pass a
  value alongside the reset, and then it went red.**
- **Specification:** that the threshold is a configuration is now stated in **four places in each
  language**. **The two the contract named (`:1502-1505` / `:1806`) were stale line numbers; there
  were four.** References to the constants `MAX_EXPANDED_PRIMITIVES` and
  `MAX_EXPANDED_PER_INSTRUCTION` are down to **zero** — they no longer exist in the product, and
  only the specification still called them by name. "233 lines are 233 lines" is kept, with **"up to
  the threshold of its configuration"** added.
- **Verification (on the merged tree):** pytest **2373 passed / 31 skipped**, `def test_` on the
  server **1203 → 1218 with none deleted**, cli **106 → 111 passed**, ruff clean (server and cli),
  `npm run check` **245 files / 0 errors / 2 warnings**, `lint:i18n` **1017 / 47 / 0 / 0**, `npm run
  test:unit` **113**, `check_frozen_corpora.py` **byte-identical**, `check_docs.py` green (55
  internal references). The API surface baseline was refrozen (the disappearance of
  `Arrangement.maximum: 2000` and the intended additions only, with no field dropped); the route
  count goes **81 → 82**.
- **Why minor:** a column was added to stored data (`history.render_limits`), a route was added to
  the API, and the static `maximum` is gone from Stage 2's tool schema. **The engine version was not
  raised** (the frozen corpora move by zero at the defaults).
- **Explicitly not done:** **the bare 240 / 500 / 120 in `_cluster_count` were left alone** — that
  240 is the same boundary as `literal_count_threshold`, so moving the threshold pulls the two
  apart, but the contract does not name it as a target and it was **filed as [I-136]** with three
  options. **Android was not inspected on the Pixel 9** (compilation only). **No round trip was made
  from the CLI to a live server** (the flag-to-body mapping was measured instead). **No default was
  changed, `renderer.py` was not touched by a single byte, and Android has no settings UI.** Stage 5
  is not yet written into `ANDROID_SPEC`.
- **Ledger:** **[I-136]** (the bare 240 in `_cluster_count`) and **[I-137]** (web sends
  `sketch_grain_change`, which the server does not know and rejects with 422; filed by the
  `android-lineage-wiring` session) were numbered.

### Android `2.1.4-android.8` — the lineage tables get a caller that writes to them (android Build 148092, 2026-08-05)

**[I-068].** The node and edge tables had been ported, but **nothing on the save path ever wrote to
them**. `InkuRepository.saveResult` now writes one node per save and **one edge only when a
derivation was declared**. **The server is canonical; Android is the port.**

- **Stage 1: a pure function that decides what to write** (new `LineagePlanner.kt`), **read against
  `db.py` one condition at a time** (the table is in §2 of the report). **Three things were added
  only to copy the conditions, none of them a "this is better" judgment**: ① **Python's
  truthiness** (`isTruthy`) — `or {}` **turns an empty list into `{}`**, so
  `["not","an","object"]` is refused while `[]` is accepted; branching on the Kotlin type instead
  would refuse both and split the judgment (the same shape as the `optDouble` case in §2-4 of the
  conventions); ② **a save that declares a parent but no kind is refused as an invalid kind** —
  `None not in LINEAGE_DERIVATION_KINDS` is true on the server, so the message is
  `invalid lineage derivation kind`, not "a parent is required" or "a kind is required";
  ③ **`_canonical_json` was written out by hand** — `JSONObject.toString()` preserves insertion
  order, so the recursion of `sort_keys=True`, the separators without spaces, `ensure_ascii=False`,
  and **sorting by code point** were reproduced (Kotlin's natural `String` order is UTF-16 code
  unit order and splits from Python on supplementary-plane keys).
- **Stage 2: called from the save path** (the point of the contract). **The decision is made before
  any row is created, so a refusal leaves no history row either.** Node then edge, **in one
  transaction** (SQLite's foreign key requires the child node first — the same order as the server).
- **Stage 3: the derivation kinds now match the server's sixteen** (they were eleven, in declaration
  order). **The list is read out of the baked fixture**, so a kind added on the server turns this
  red instead of passing silently. **The five new Japanese labels had no existing wording** in web
  or server (`derivation.ts`'s `JA` has twelve and none of these five), so they follow the existing
  habit of short nouns: `render_engine_change`=描画エンジン, `age_change`=経年,
  `hacho_change`=破調, `renga_reply`=連歌の付句, `external_seed_change`=外部の種.
- **Five perturbations, all aimed at production code** (no test was rewritten). **No stage came out
  at zero.** **Under P2 (cut the wiring) all 143 JVM tests stayed green** and only **five
  instrumented tests** went red — exactly the warning in §2 of the contract: **a suite of pure
  functions cannot be the acceptance for stage 2.** **P5 (move the edge insert outside the
  transaction) is invisible to P2**: both rows are still written, and only the transaction check
  splits.
- **Verification (on the merged tree, re-run here on the device):** **JVM unit 143 / 0 failures**
  (38 classes), **instrumented 21 / 0 failures** (Pixel 9 `54100DLAQ0028F`; no emulator), and the
  server `pytest` run has `test_android_reference_fixtures_are_current.py` **rebaking
  `lineage_wiring.json` and comparing it against the checked-in bytes**. `APP_VERSION` and
  `web/BUILD_NUMBER` are unchanged, and nothing was deployed to pentala.
- **Explicitly not done:** **the UI call sites were not wired to pass a parent** — the three
  entry points on `InkuRepository` merely have the parameter, and `InkuViewModel` / `InkuApp` still
  call with the default. **So on a real device today a node is written every time and no edge is
  ever written.** **There is no UI that shows lineage.** [I-067] (colophon, `unread_words`) was
  excluded from this contract. **The `history_visibility` column was not added** (it would be a Room
  version 6 migration and is not one of the contract's stages; the judgment is ported and measured,
  but **on the device only the `normal` path is reachable**). **The lineage tables have no `user_id`
  column** (one device, one user), so the server's "the parent belongs to the same user" has no
  counterpart.
- **Ledger:** **[I-068] moved to decided.** The server-side divergence found while implementing it
  is filed as **[I-137]** (web sends `sketch_grain_change`, which the server does not know and
  rejects with 422); **the sixteen kinds in `lineage_wiring.json` will not be rebaked until that is
  ruled on**.

### v2.11.0 — folding away the staffage level: the machinery that added what was never asked for (Build 854, 2026-08-05)

**The description is the whole contract** (author's ruling, 2026-08-05). **The staffage level
(`tenkei`) decided how much a layer was allowed to add, which made it the permission to invent
elements the description never named.** The axis is folded away, and **the folded behaviour matches
the old `tenkei="none"` exactly** — measured at zero difference across 61 coerce cases, 15 Stage 1.5
cases and 3 inputs through the English taste path. **This is a minor release because keys leave the
API.** The archive is tag `archive/tenkei-v1.97` and `no-git-sync/archive/tenkei/`.

- **The insertion budget and the six inventing branches are gone from coerce** —
  `_with_visual_event`, `_with_composition_diversity_repair`, `_with_context_energy_repair`,
  `_with_motion_floor`, `_with_surface_tension` and **`_with_focal_event_floor`**.
  **The contract listed five; the measurement found six** (the same section wrote "9 / 31", and this
  was the difference). **Keeping the sixth does not reproduce the old `none`.** **The three
  delivering branches stay**: `with_ddl_coverage`, `with_complex_motif_repair` and
  `with_shape_delivery_repair`. Reachability analysis removed **41 definitions and 1,236 lines**
  (`compose.py` 3,646 → 2,410).
- **The level mapping is gone from Stage 1 and Stage 1.5.** `_expand_ja` and `_expand_en` now **end
  at the focus rewrite**; the candidate pools, category plans, composition families and colour/touch
  selection became unreachable, removing **35 definitions and 467 lines** (`ddl_expander.py`
  1,081 → 594). **Variation moved from seven axes to one (focus).** The other six shook sentences
  that Stage 1.5 had added itself, so they share the fate of the pools. **Amplitude still reaches the
  output** — across 40 seeds, small, medium and large land on different foci in all 40.
  `_english_taste_additions` in `language_support/en.py` (jazz, quilt, subway and four more word
  groups) **only ever fired at `auto`**, so it was staffage too and is deleted.
- **The flag left the API, the UI and the CLI; the database record stays.** The `tenkei` column, its
  migration, its read and its write site are untouched, so **a work saved before the removal still
  reports the conditions it was drawn under**. **The declaration moved from `HistoryPostBody` to the
  response model `HistoryItem`** — deleting it outright drops the key from past works' responses,
  which acceptance test T-4 caught. **The staffage row in the provenance list now appears only in
  developer mode, and only for a past work that has a value.** The web tree deleted
  `TenkeiSelect.svelte` and four more files and followed through **sixteen call sites**; the CLI lost
  `--staffage`, its two send sites and two usage lines in its README.
- **`ComposeRequest.lineage_parent_node_id` is gone too** — a flag that existed only to inherit the
  level. **Seven fields left the API surface** (`tenkei` from six models plus this one); endpoints,
  operations and schemas stay at **82 / 82 / 82**.
- **`ddl_engine_version` 6 → 7.** The frozen corpora were rebuilt with the discriminating cases
  folded together, and **two cases were added that freeze the absence of invention**
  (`B-surface-tension-words` and `B-leaf-grain-words`). `changed_from_previous` reports 32 of 34, but
  **only 10 a_expand and 9 b_coerce Scores actually moved**; the rest changed their branch report
  alone.
- **In pytest, the expand corpus was a record and not a gate.**
  `test_ddl_reference_output_files_match_manifest` **only compares the files on disk against the
  manifest**, so the two move together unless both are rebaked (only CI regenerates them).
  **Restoring a candidate sentence turned nothing red**, so a gate was added that rebakes the 13
  a_expand cases inside pytest and compares digests — **and states how many it looked at**.
- **The pure-invocation bypass and the plugin transcription guard were kept, cut loose from the
  level.** Neither is staffage: the first is transcription fidelity (a qualified plugin term must not
  be rewritten by the model), the second prevents delivering the same subject twice. **Acceptance
  measured two enforcement points for the bypass** (`/api/interpret` and the shared paint generator)
  and found that **cutting the paint one left all 2,312 tests green**, so a gate now covers it.
- **The Android reference fixture `ddl_expand.json` was rebaked** (39 → 30 cases: thirteen
  `*-tenkei-*` leave, four arrive). **No Kotlin line was touched**, so **4 of the 143 Android JVM unit
  tests are red** (the reference comparisons in `WebDdlExpanderPhase3a/3b/3d`: Kotlin reads
  `input.optString("tenkei", "auto")`, so a missing key runs at the `auto` default). **Per the
  author's ruling of 2026-08-05, showing the red is preferred over staying green against an
  expectation the server no longer holds.** The Kotlin port belongs to the Android track.
- **Checks:** server **2373 → 2313** (`def test_` 1312 → 1261; 88 removed, 37 added), cli unchanged
  at 111, `npm run check` **245 → 241 FILES / 0 errors**, `test:unit` unchanged at 113, `lint:i18n`
  1017 → 1004, and **the frozen corpora are byte-identical**.

### 2026-08-05 — the manuals catch up with v2.11.0 (**no version**; documentation only)

**The seven manual documents, in both languages, had stood at v1.85 / Build 564 for 51 versions.** Ledger item [I-003].

- Corrected the **eleven places that name a version** to v2.11.0 / Build 854. **the index at the top of the manual directory was older still**, at v1.82 / Build 563
- **Rewrote Creating Images**, from fifteen sections to twenty. **Sketch from life (Stage 0.5), Variation, Wild, `From the description` for the color catalog, UI mode, the revision mark, Replay, contact sheets, animation export, search by the last four hash characters, and the ten settings tabs** were all undocumented. **Language comparison was dropped, being absent from the current UI** (`language_variation` survives as a derivation kind on stored works)
- **Added six commands to the inku-cli Reference** — `plugin`, `reference`, `colophon`, `user`, `group`, and `config`. **Only four of `paint`'s thirty flags were documented**, so they were regrouped into six tables by purpose (three sketch flags, two variation flags, `--wild`, `--catalog-mode`, `--interpretation-seed`, and more: **twenty-six were missing**)
- **Added nineteen environment variables to Server Configuration** (52 in code against 33 documented, now **52 / 52**). **Nothing documented had been retired.** Added §2.5 for layers and plugins, moving providers to §2.6, and **added §5.1 for the limits**: the nine values, their defaults, the rounding rule, and the fact that **the environment variables only seed the first value while the DB settings are canonical thereafter**
- **Corrected the render hash from `rh2:` to `rh3:`**, with the canonical payload (score, `render_seed`, `render_wild`, engine, catalog) and the reason a renamed key recomputes the hash of every stored work
- **Corrected the Application Installation prerequisite from Python 3.10 to 3.12** (`requires-python` is `>=3.12`). **That single line was an error on the side that makes an install fail**
- **Corrected `--kind reading` in the AI reference** — it is **Stage 1, not Stage 1.5**, and Stage 1.5 is not an LLM at all. Also repaired a sentence in which Japanese and English had been spliced together, in `refine perform`
- **Added §0.8, "Beware the silent sender."** An omitted flag paints under the server default, and **the server default differs from the Web UI default** (sketch is off on the server, fine in the UI). **Variation takes effect only when both flags are given, so having passed a flag is not evidence it took effect**

**One thing learned**

- **`check_docs.py` does not look at `manual/` at all** — its thirteen pairs are the repository root and `docs/`. With no gate enforcing bilingual parity, the Japanese and English README files under the manual directory had drifted eleven days apart in last-modified time. **The 25/25 and 20/20 agreement reached here is the result of hand work, not of a check.**

### 2026-08-05 — the manual's language pairs come under the gate (**no version**; checks only)

**`check_docs.py` compared thirteen pairs and the manual was in none of them.** Ledger item [I-140].

- **Added seven pairs to `PAIRS`** (13 → **20**), all under `shape`. **The manual index has no counterpart and stays out**
- **Added `server/tests/test_manual_parity_gate.py`** (three `def test_`, 22 checks). **`PAIRS` is read from the syntax tree** — `grep '"shape"'` also matches the word inside the comment documenting the three modes and **counts thirteen pairs as fourteen** (the issuing side walked into it). **The seven pairs are asserted one at a time**, since asserting only the total would pass on six manual pairs plus one other. The declared exception is asserted to be `None` as well: **declaring a reason turns the failure into a printed note, leaving the row listed while it checks nothing**
- **Why stage two exists: `PAIRS` is a configuration table, not product code.** Delete the seven rows and **`check_docs.py` still exits 0**, with nobody reporting that the number of things looked at fell from 20 to 13 — the same shape as the dependency upgrade that emptied `app.routes` from 81 to 0 while two checks stayed green
- **Discriminating power** (measured before issuing, after implementing, and again on the merged tree): a heading added to the Japanese side alone goes from **0/7 red to 7/7 red**. Deleting the seven rows leaves the new test at **8 failed / 14 passed**
- **Checks:** server **2313 → 2335 passed / 31 skipped** (`def test_` **1262 → 1265**, none removed), ruff clean, `check_docs.py` green (55 internal references). Not one file under `web`, `cli`, `android`, or `server/src` moved

**One correction made during acceptance**

- **The contract asserted that the manual is outside the rsync payload and therefore absent from pentala, and the implementation copied that premise into a comment. Measured, it is false.** pentala carries the manual — a stale v1.85 copy whose two languages still match each other, so `check_parity` is green there too, and "seven missing originals turn it red" is false as well. **The `skipif` stays**: it guards any tree without a manual, and was never a description of pentala. **The comment was replaced with the measurement.**

### 2026-08-05 — Android folds away the staffage level and follows the server (**no version**; Android only)

**The staffage level (`tenkei`) that the server folded away in v2.11.0 is now folded away in Kotlin**
([I-139]). The server is canonical and the client is the port, so the conditions were read one
against one. **No version was stepped** — `web/APP_VERSION`, `web/BUILD_NUMBER`,
`android/VERSION` and `android/BUILD_NUMBER` are all unchanged. **Nothing was deployed or restarted.**

- **`WebDdlExpander.kt` went from 1,347 to 540 lines.** The `tenkei` parameter and the level
  mapping are gone, and **the variation plan is down to the focus axis alone** — the same shape as
  the server's `AXIS_FOCUS`. The six axes, the category plan, the composition family, the touch and
  the colour machinery became unreachable and were deleted, as they were on the server
- **`data/model/Tenkei.kt` and the picker are gone.** **Two pieces of the server's ruling had no
  counterpart here**: Android never persisted `tenkei` to Room and never sent it over the wire, so
  there was no column to keep and no developer-mode row to show
- **The six tests whose claims the fold made false were re-pointed, not deleted.** They now assert
  against focus, pinning the exact output with `assertEquals`
- **Checks:** JVM **143 / 4 red → 156 / 0 red** (38 → 37 classes); instrumented **21 → 20 / 0 red**
  on a real Pixel 9. On the merged tree, server **2335 passed / 31 skipped**, cli **111**,
  ruff clean, `check_docs.py` green

**Two things the acceptance turned up**

- **One of the four red tests was misattributed in the ledger entry.**
  `testContextTextUsageAndDefaults` was not red because Kotlin lagged behind: **the re-bake left two
  cases with an identical `output`**, so the claim could not be made true by any change to Kotlin.
  A perturbation run before the contract was issued caught it
- **The reference corpus lost half its discriminating power** — the re-bake took it from
  **39 cases / 28 distinct outputs (72%) to 30 cases / 14 (47%)**. **A port that ignored its input
  would still pass 16 of the 30**, so the discrimination is carried by the focus control rather than
  by the full-corpus comparison. Filed as **[I-141]**

### 2026-08-05 — the ANDROID_SPEC catch-up status now matches measurement (**no version**; documentation only)

Addresses **[I-013]** (`ANDROID_SPEC` had not followed the engine). **Only the live prose was
changed; not one line of the dated history sections was touched** — those record what was ported
on the day they carry.

- **The catch-up header was 51 versions out of date.** It read `2.0.0-android.1` with render engine
  `11`, a master at v2.5.0 with engine 12, and a drawing layer one version behind.
  **Measured today: Android `2.1.4-android.8` with render engine `21`** (declared in
  `CompatibilityConstants.kt`) against a master at **v2.11.0 with render engine `21` and
  `ddl_engine_version` 7** — **the drawing layer versions match**
- **One bullet under the implementation status was stale too** — `renderer engine 2 → 10` and
  "only Phase 1 complete". It now records reaching engine 21, and that lineage is ported as far as
  the data layer
- **Stated explicitly that matching layer versions is not a finished port.** The remaining gaps are
  held by the issue ledger and deliberately not copied into the document, because a copy goes stale.
  The ledger's `android` area holds nine other items
- **Last-updated date moved from `2026-07-25` to `2026-08-05`**
- **Checks:** `check_docs.py` green. **This pair is checked in `sections` mode** (the number of `##`
  sections only), and both languages still hold 62

### 2026-08-06 — Shape checks now hold on a checkout that carries only the server (**no version**, tests only)

**The development server was corrected to carry only what its two services need.**
Eight tests in `server/tests` then failed for being right about a machine they were not
describing: they read `android/`, `cli/`, `docs/` or `scripts/`, and those are not there.

- **Four now skip on the absence of the directory they read** (the five assertions in
  `test_merge_driver.py`, the `cli/pyproject.toml` case in `test_rasterizer.py`, and the
  four-area count in `test_limits_are_settings.py`). **The skip is on the directory, never on
  the file** -- on the file, a rename becomes silence instead of a red
- **The breadth proof for the `cairosvg` scan could not simply skip.** It proved itself by
  **requiring `android` in the result**, and that proof is exactly what the development server
  cannot supply. **It is now two tests**: one checks **the mechanism on a tree built for the
  purpose** (an unlisted root and an excluded one, both placed deliberately, so it holds on any
  tree), and one checks **on the real tree that the set derived from the directory listing is
  reached** -- not compared against a written-down list. **Neither names a client app**
- **Perturbation:** returning the scan to a list of named roots turns **two red on the Mac and
  one red on the development server**. **The old assertion could not catch that regression
  there at all**, since requiring `android` was already failing. **The new mechanism check goes
  red on a partial tree too**
- **Checks:** server on the Mac **2336 passed / 31 skipped** (+1 from the split), ruff green.
  **The development server's full pytest went from 13 failed to 0** (2276 passed / 91 skipped)

### v2.11.1 — The nine limit fields get the `-` / `+` the DB tab already had (Build 856, 2026-08-06)

**Settings > Limits** held bare number inputs -- no stepper, just the browser's own spinner.
**The DB backup tab already uses `NumberStepper`**, so the fields now use the same component:
button sizing, the disabled `-` at the lower bound, and the rounding of a typed value are
identical across the two tabs.

- **`<label>` became `<div>`.** A stepper's first labelable child is the `-` button, so a
  wrapping label points at the button rather than the field. The accessible name comes from
  the stepper's own `aria-label` -- the shape the DB tab already used
- **The input no longer stretches to the full width of its card.** The card is 220px or wider
  because of the **hint sentence**, not because of the number. The stepper is now fixed at
  `min(136px, 100%)` and the hint keeps the card width. 136px leaves room for the largest
  value that can be typed, the absolute ceiling of `100000`
- **Checks:** `npm run check` 241 files / 0 errors / 2 warnings (the two pre-existing a11y
  ones), `npm run test:unit` 113, `lint:i18n` 1004/47/0/0, `lint:models` 68,
  `lint:recommendations` 37, server **2336 passed / 31 skipped**, cli **111 passed**, ruff green
- **`manual/`: thirteen version markers updated and one section added to the revision history in
  both languages. No prose changed** -- how the numbers are changed (the administration UI or
  `inku-cli config update`) is unaffected, so section 5.1 of `Server Configuration` still holds

### v2.11.2 — The run's colour catalogue is decided in one place on Android (Build 857, 2026-08-06)

**Five places on Android decided which colour catalogue a run used.** The draw, DDL, demo, batch
and repeated-run paths each read `InkuUiState.selectedCatalogId` on their own, so "nothing but
the setting decides the catalogue" was a statement about five places at once and **no test could
stand on it** -- the acceptance that shipped with the removal of the demo path's random pick
asserted against a **private helper of the test's own** that returned the same field, so
**putting the random pick back into production code left all 118 tests green**.

- **This follows the server.** There, a paint resolves its catalogue through a single helper
  called once, and the acceptance **drives the real drawing API with only the model call
  replaced**. Both halves were copied. In line with the rule that **the client follows the
  server**, nothing was invented on this side.
- **The decider is now `CatalogSelection.resolvedCatalogIdForRun`**, and the five call sites go
  through it. The random-number import that became unused went with them. **The server's three
  modes do not exist in this client**, and the implementation comment records that should one
  arrive, it belongs inside this function.
- **One difference from the server is kept on purpose:** given a catalogue id that is not in the
  list, **the server answers 422 while this client falls back to the default catalogue**, so a
  setting saved by an older build cannot stop the app from drawing. That is **an
  Android-specific circumstance -- backward compatibility of stored settings**.
- **The wiring is now gated on a physical device.** A new instrumented test drives all five
  paths against a real repository and **reads the catalogue back out of what was saved**.
  **⚠ Four of the five are covered** -- the draw path's `interpret` argument **reaches nothing
  but a log line**, so perturbing it changes no drawing at all. That gap is recorded in the
  issue ledger.
- **Checks:** Android JVM **159 / 0 failures** (37 classes, from 156), **instrumented 25 / 0
  failures** (physical Pixel 9, from 20), server **2336 passed / 31 skipped**, cli **111
  passed**, `npm run check` 241 files / 0 errors / 2 warnings (the two pre-existing a11y ones),
  ruff green.
- **`android/VERSION` is `2.1.4-android.9`.** No drawing layer version moved (render engine `21`
  and `ddl_engine_version` 7 are unchanged).

### Android `2.1.4-android.10` — Seeing that the description travels untouched (android Build 148092 unchanged, 2026-08-06)

**[I-134].** [I-114] removed the `emotionHint` Android concatenated onto `description`,
**but nothing watched the removal** — **no JVM unit test constructs an `InkuRepository`**
(it needs a context and a database), so **putting the concatenation back into production code
turned only 0 of 136 tests red** (measured 2026-08-05). `DescriptionPassthroughTest` on the
device closes it.

- **This follows the server.** Its description gates are written to run **through the routes,
  not through the predicates**: the whole run is real except the language model. The same holds
  here — a real Room database and a real `InkuRepository`, with **the description read back out
  of what was saved**.
- **There are two observation points.** `description` becomes **the Stage 1 prompt itself**
  (`LocalFallbackPipeline` sets `prompt = request.description` with **no template around it**,
  so the assertion can be exact equality). `originalText` travels through
  `PaintResult.originalInput` into `history_items.originalInput`.
- **Six assertions** (T-1 the Stage 1 prompt of `paint`; T-2 the prompt and the returned value of
  `interpret`; T-3 what `paint` stored; T-4 what `composeFromDdl` stored; T-5 both places
  `renderFromScore` stores it; **T-6 the other way round**, so that two descriptions arrive as
  two texts — **an implementation returning a constant cannot pass**).
- **⚠ `composeFromDdl`'s `description` is deliberately not gated.** That entry point takes the
  DDL as its own argument and **reads `request.description` nowhere**, so any assertion about it
  **would be green whatever the repository did** (the shape of [I-142]). Its `originalText` is
  observable and T-4 covers it.
- **The discriminating power was measured by perturbation** — four entry points × two fields =
  **eight enforcement points, each perturbed on its own**. **Seven went red**; the only one that
  did not is the `composeFromDdl.description` above. **T-2 at first missed
  `interpret.originalText`** (that entry point saves nothing, so the field surfaces only in what
  it returns) — **the zero-red perturbation is what exposed it**, and it was added.
- **Checks:** Android instrumented **31 / 0 failures** (physical Pixel 9, from 25), JVM **159 /
  0 failures** (37 classes, unchanged). **Only `android/VERSION` moved** — `APP_VERSION` and
  `web/BUILD_NUMBER` are untouched and nothing was deployed to the development server.

### v2.11.3 — A redraw at a different sketch grain can be saved (Build 858, 2026-08-06)

**The web client was sending `sketch_grain_change`, the server did not know the name, and the
whole save was lost** ([I-137]). Redrawing from the describe tab makes the client name the
operation by comparing the work with its parent. When the 写生 (Stage 0.5) grain differs from the
parent's it sends this kind, **the server's `LINEAGE_DERIVATION_KINDS` did not carry the name**,
`db.add_item` raised `invalid lineage derivation kind`, and **the 422 left no work, no history
entry and no lineage edge**. The client has sent the kind since v2.9.37 (2026-08-03); **the server
stayed at sixteen kinds.**

- **It is not only a change of grain that fires it.** The grain is `fine`, `coarse` or **absent**,
  and **absent means the layer is switched off**. Since the test is a difference from the parent,
  **switching the layer on or off produces the same kind.**
- **It stood directly in front of the busiest path.** The branches run canvas change → description
  edit → **sketch grain** → replay, and **replay is 73 of the 196 edges in production (37%)**.
  Regular use of the sketch layer would have stopped there.
- **Nobody had hit it yet.** Twenty-five of the 2,748 works in production carry a grain (23
  `fine`, 2 `coarse`), and **all of them were saved on 2026-08-04 as roots with no edge**.
- **The server was not treated as right here.** The kind was added deliberately by the client to
  keep one edge to one cause, so **it was added to the server as a seventeenth kind** (author's
  ruling, 2026-08-06). **No row carries the value, so the rename table needed nothing.**
- **The existing acceptance test could not see the disagreement.** `test_lineage_acceptance.py`
  **iterates `LINEAGE_DERIVATION_KINDS` itself**, so it is green whatever the set holds.
  **Nothing compared the two lists.**
- **`test_derivation_kind_parity.py` was added** (4 tests). It **writes the seventeen names out**
  and **parses the client's `DerivationKind` union from the client's own source**, comparing them
  **in both directions** (a kind the client sends and the server rejects; a kind the server names
  and no screen sends). The fourth goes **through the save route** and checks that a regrained
  child is saved with 200 and that the edge is written.
- **Perturbation measured the discrimination.** One perturbation each at the five points that
  enforce this (the server set, the client union, the Kotlin list, the baked fixture, the save
  route), and **all five went red**: removing the name from the server turns **3 red** (the older
  acceptance test stays green); removing it from the client union turns **the reverse gate red**;
  adding a kind the server does not know turns **1 red** (the shape of [I-137]); removing it from
  the Kotlin list turns **2 red**; removing it from the baked fixture turns **1 red**.
- **Android only follows.** There is no sketch layer on that client, but **it carries the server's
  list**, so `lineage_wiring.json` was rebaked and `DerivationKindRegistry` follows to seventeen.
- **The lineage section of the manual names the sketch grain in both languages.**
- **Checks:** server **2340 / 31 skipped** (2336 at the branch point; the 4 new ones are this
  entry), cli **111**, `npm run check` **241 FILES / 0 errors / 2 warnings**, `npm run test:unit`
  **113**, `lint:i18n` **1004/47/0/0**, ruff clean, Android JVM **159 / 0 failures** (37 classes;
  the count is unchanged and two existing assertions moved from 16 to 17).

### v2.11.4 — A fill gets an underlay, and what sits on it gets a branch (Build 859, 2026-08-07)

**A stroke WAS the fill, so every scan line had to be cut where it met the outline** (render
engine 21 → 22). Without the cut the ink spills outside the shape. **That cut is the third of the
three regularities the eye reads as a raster** — across the eleven filled shapes of the three
works the author named as striped, the scan angle varied by **0.1°** inside one shape, the pitch
by **6.1%**, and the endpoints **not at all**.

- **A real element now holds the field.** Because the boundary belongs to the underlay the marks
  are free: the angle moves **3.3–3.6°** per stroke, the pitch's coefficient of variation rises to
  **30–35%**, and each end overshoots or undershoots by up to **1.4–1.5 tool widths, in both
  signs**. **All three amplitudes belong to the tool and are zero for a machine**, so a
  `computer` fill keeps an angle standard deviation of 0.00° with its endpoints on the contour.
- **The underlay is common to both branches; the threshold only decides what sits on top.**
  Coverage — width over pitch — at **0.2** divides them: above, scan lines packed to coverage
  **0.9**; below, rubbings. **Closing the gaps at pencil width would take eight times the lines,
  and that is not how the tool is used.**
- **The threshold is coverage, not a list of tool names.** The two cut the engine-21 corpus
  identically, so a case that **sends one tool across the branch on thinness alone** was added.
  Without it an implementation that never reads the coverage passes every other gate.
- **The underlay is not built out of a filter.** Filters exist only for `display`, so a
  filter-built underlay makes **the fill itself vanish** in `compat` and `editable`. On the
  texture branch it is one pale field plus six layers drawing the mottling as three concentric
  rings, and **the composite is exactly the original flat value**.
- **A fill stroke now ends the way paint ends** — heavy where the tool lands, narrowing only at
  the release. **The default terminal for a contour stroke is unchanged.**
- **A tiny shape still degrades to a dab and `rotring` to a region fill; neither gets an
  underlay** (byte-identical to engine 21).
- **The frozen corpus goes 525 → 531 cases** (`computer`, `silverpoint`, `crayon`+`extra_fine`,
  `brush_thick`+`extra_fine`, `chalk`, `chalk`+`extra_fine`). **52 moved** — 32 fills, **14 chalk
  contours**, 6 new. **The 14 chalk cases are not fills** (a tool's properties cross the
  branches); **what moved for a different reason is kept on a separate roster**.
- **Mean interior density** (circle r=0.3): pen 15.4 → **69.6%**, pencil 6.9 → **47.8%**,
  silverpoint 2.8 → **50.9%**, brush_thick 52.1 → **82.7%**, crayon 22.2 → **71.9%**, chalk
  14.9 → **68.3%**, computer 15.2 → **77.8%**. **Power left at the original band's period**:
  pen 39.0 → **4.0%**, pencil 28.3 → **4.4%**, silverpoint 19.0 → **0.9%**, and **computer is
  unchanged at 23.6 → 25.0%**.
- **This is not "the striping is gone."** Striping also arises from wash and hatch; this version
  touched only the scan mechanism, and the thirty prompts were not redrawn.
- **26 new acceptance tests** (`test_fill_underlay_and_branch.py`) and **40 perturbations against
  production code, 40/40 red**. Five existing tests **had their claims rewritten**: the two that
  asserted byte-identity with engine 15 now assert the case count, the presence of the underlay,
  and the exclusivity of the stages, because **engine 22 moves those 31 and 30 cases on purpose**.
- **`ddl_engine_version` does not move** (still 7); nothing up to Stage 2 changed by a byte.
- **⚠ Android is still on engine 21.** The reference fixtures were rebaked, so **7 of its 159 JVM
  unit tests are red** (`DefaultSvgRendererFillDabTest` 2, `DefaultSvgRendererPhase2fTest` 3,
  `ServerStrokeEngineTest` 2). **The client follows in a later version.**
- **Checks:** server **2366 / 31 skipped** (2340 at the branch point; **+26 = the 26 new tests**,
  the five existing ones being renames), cli **111**, `npm run check` **241 FILES / 0 errors /
  2 warnings**, ruff clean, `check_frozen_corpora.py` byte-identical, `check_docs.py` green.

### 2026-08-07 — The Android reference corpus is filed by engine version (**no version**, tests only)

**Raising the engine no longer turns the port red.** The reference fixtures sat in one flat
directory that the generator rebaked in place, so **the moment the server raised its engine the
port's expectations were rewritten underneath it and it was compared against a version it had
never claimed**. Merging engine 22 turned **7 of the 159 JVM tests** red that way, and the red
window lasted two days both times. **More drawing revisions have been announced.**

- **The rule `server/reference/` already follows** — a directory per version, only the current one
  written, older ones held by a manifest rather than rebaked. The **54 files the render engine
  governs** moved under `render-engine-<version>/` and **`ddl_expand.json`** under
  `ddl-engine-<version>/`. The **five no engine governs** (`prompts`, `lineage_wiring`,
  `count_preservation`, `coerce_governors`, `score_schema_contract`) stay flat and are followed
  the way they always were.
- **Engine 21's 54 files were restored from history** (`d0a9739f`). **An engine 22 tree cannot bake
  them** -- that older versions are unbakeable is the point of the layout.
- **The port asks for a fixture by bare name** and reads the version
  `CompatibilityConstants.renderEngineVersion` names. The **20 test files** that each opened their
  own resource path now go through one resolver.
- **No implementation file changed**, and all **7 red tests closed** (159, none red). Catching up to
  engine 22 is a separate contract; `renderEngineVersion` is still `"21"`.
- **A manifest is the only thing holding an older version** -- F-1 rebakes the current one and
  cannot reach the rest -- so **F-4** matches every version directory against its own names and
  digests. Changing one character of engine 21's digest reddens **F-4 alone**, with the other 124
  related tests still green.
- **Six perturbations against production code and data**: dropping the version from the resolver
  **brings back exactly the original 7**, and pointing `renderEngineVersion` at `"22"` reddens
  **those 7 plus the 2 that assert the declared version**.
- **Checks:** server **2367 / 31 skipped** (**+1 = F-4**), cli **111**, `npm run check` **241 FILES /
  0 errors / 2 warnings**, ruff clean, `check_frozen_corpora.py` byte-identical, `check_docs.py`
  green, **Android JVM 159 with none red**, **instrumented 31 with none red** (Pixel 9 hardware).

### Android `2.1.4-android.12` — A drawing now names the work it came from (android Build 148093, 2026-08-07)

**[I-138], 1/5 of the Android lineage series.** The port **saved every work as a root**. The server
has recorded the parent and the kind of derivation from the beginning and web has declared it since
the lineage panel shipped; **only the port never sent it**, so a phone's history was a flat list of
unrelated works.

- **One pure function decides** (`SubmitDerivationKind.kt`), with **web's branch order**
  (`canvasAspectChanged` → no parent means `null` → description / DDL → `replay`), and **every one of
  the four kinds it returns is one `DerivationKindRegistry` knows**.
- **The batch, the demo and the headless path write no edge, and a work restored at startup is not a
  parent** -- neither is something the author picked.
- **"Start a new lineage" is wired but not on screen.** Web puts it in the lineage panel and the port
  has no such panel yet (2/5 builds it). **Putting it anywhere else would be the client inventing a
  design the server side does not have.**
- **A description counts as untouched even with its prefix stripped.** Web avoids prefixes with a
  separate `source_text` column and **the port has none**; comparing directly would mark a work
  derived from the batch as `description_edit` with nothing edited. **Adding a column was rejected**
  as a client-side invention with no counterpart on the server or in web.
- **Chasing a flickering instrumented suite found two product defects.** The settings restore and the
  history restore both read the state, suspended, and **wrote the stale copy back over whatever the
  author did while they waited**: typing a description, picking a history entry or changing the
  canvas ratio right after startup was silently undone, and a reverted `lineageDetached` turns a save
  that should be a child into a root. **Three runs before the fix reddened one or two different tests
  each time; four runs after it were 11/11 green** (44 executions, none red).
- **Nine perturbations against production code** (the contract's seven plus two the implementer
  added). **Dropping the condition that reads `lineageDetached` did not redden T-6**: in the port a
  parent only ever comes from `selectedHistory`, so dropping the flag removes the parent anyway. That
  showed **the flag matters in exactly one place -- the startup restore** -- and a perturbation
  aimed at stage 3 itself was added.
- **Checks:** Android JVM **168, none failing** (38 classes, 159 at the branch point), **instrumented
  42, none failing** (Pixel 9 hardware, 31 at the branch point). **Only `android/VERSION` moved** --
  `APP_VERSION` and `web/BUILD_NUMBER` are unchanged and nothing was deployed to pentala.

### 2026-08-07 — The CLI manual is written in the parser's own words (**no version**, tests only)

**The Command Line Help Reference in `cli/README.md` was `--help` copied by hand, and nothing
compared the copy to the parser.** So a renamed flag left the manual naming the old spelling:
it said `--original-text` (now `--description`) and `--vary-seed` (now `--composition-seed`),
and it never listed `--staffage` or `--trace` at all. **Regenerating it on 2026-08-04 fixed the
content of the day and left the structure, so the next forgotten flag would ship the same way.**

- **The marked region is now generated** — `cli/scripts/gen_readme_help.py` writes the **1,217
  lines** between `<!-- HELP_START -->` and `<!-- HELP_END -->`. **The 77 lines of prose outside
  the markers belong to a person, and the generator never touches them.**
- **`COLUMNS` is pinned to 80** — argparse wraps to the terminal width, so without pinning the
  generated file would depend on who ran it.
- **Three things exist (parser, manual, generator) and the suite asserts two of the three edges** —
  byte equality per command (**48 cases**) and the generator's `--check` (1 case).
  **That the markers bound the region is asserted separately**, because deleting one would
  otherwise just shrink what is checked and stay green.
- **The comparison is the whole block, not the flag names** — a stale description under the right
  name is the failure this started from.
- **The existing eight-flag gate stays.** It reads the opening words of each help string, which
  byte equality does not single out: **changing one word of a description turns only the new gate red.**
- **Regenerating moved four lines** — how `paint` and `batch` wrap their usage synopsis. Every flag
  name and description already matched.
- **Five perturbations were applied to production code and to the generated file** — deleting the
  generator turns **1** red, adding a flag without regenerating **3**, changing one word of a
  description **3**, deleting a marker **50**. **The fifth checks the opposite**: running the
  generator on the third state takes 3 back to 0, so the repair path works.
- **Tests:** cli **161** (**+50**), server **2367 / 31 skipped** (unchanged),
  `npm run check` **241 FILES / 0 ERRORS / 2 WARNINGS**, ruff clean
  (**cli's arguments are now `src tests scripts`**), `check_docs.py` green.

### Android `2.1.4-android.13` — A drawing now shows on screen where it came from (android Build 148097, 2026-08-07)

**Second of the five lineage releases.** 1/5 wired the parent up and left it invisible; this one puts
the graph on screen and gives the first control that writes to it.

- **A pure function builds the graph** (`data/lineage/LineageGraph.kt`). **It reproduces all eleven
  cases baked by actually calling the server's `db.get_lineage`, ordering included** — ordered by
  `(at, id)`, depth and node count clamped, and **a tombstone left without the hashes and history
  its neighbours keep**.
- **Three set queries were added to the DAO**, and the screen names each generation with
  **`DerivationKindRegistry`'s own labels**. **"Start a new root" reaches the view model from the
  screen for the first time.**
- **Nine perturbations were applied to production code only** (no test was touched).
  **Dropping the rounding turns exactly one test red** — the eleven-case comparison stays green
  without it, which is precisely why the contract asked for the effective value rather than the output.
- **⚠ One fix from outside the contract — the app had stopped starting.**
  **Every launch had thrown since `4c5e82f6` (2026-08-06).** Kotlin emits no `<init>(Application)`
  signature for a constructor whose second parameter has a default, so `androidx.lifecycle`'s
  default factory could not find it by reflection and raised `NoSuchMethodException`.
  **No existing test saw it because they all construct the view model from Kotlin**, going through
  the synthetic bridge and never walking the reflective path. One word, `@JvmOverloads`, fixes it,
  and an instrumented gate now composes `InkuApp()` the way `MainActivity` does.
- **Tests:** **JVM 173 / 0 failures** (39 classes, from 168), **instrumented 46 / 0 failures**
  (Pixel 9 hardware, from 42). **Only `android/VERSION` moves** — `APP_VERSION` and
  `web/BUILD_NUMBER` stay put, and nothing is deployed to pentala.

### Android `2.1.4-android.14` — a work can now be refined one element at a time (android Build 148098, 2026-08-07)

**Third of five.** 2/5 put the lineage on screen; this release gives the app the operation that
**adds a branch to that lineage on purpose**.

- **The refinement element is one of five — touch, layout, reading, colour catalogue, variation —
  chosen exactly one at a time** (SPEC `:614`, `:678`). The choice is a radio, and **the amplitude
  appears directly beneath it only when variation is chosen**. The rule that **each lineage edge
  attributes to a single cause** is what requires the one-at-a-time discipline.
- **What is held, what is varied, and which edge is written are decided by a pure function**
  (`data/refinement/RefinementPlan.kt`). **The colour refinement holds the DDL, the Score, the canvas,
  the composition seed and the render seed**, and **everything else inherits the effective catalogue
  and canvas of the parent work on screen, not the settings for the next drawing**.
- **`PaintRequest` gained the same five seed arguments the server has** (`render_seed`,
  `composition_seed`, `interpretation_seed`, `variation_amplitude`, `variation_seed`).
  **The judgement was ported as it stands** — `render_seed` goes through an `or`, so **`0` takes the
  same path as "not given"**. **A seed is drawn on every render, so images from here on differ from
  the earlier ones.**
- **Two spellings the server does not have were dropped** — the `seed` that `renderHash` read
  alongside `render_seed`, and the `render_seed` the renderer read from inside the Score.
  **The server's `Score` has no such field.** The comparison-render entry point now takes the same
  five values the server takes in its request body, as intent extras.
- **Eleven perturbations were applied, to product code only.** **Two of them passed green at first
  and were holes in the acceptance side, fixed and re-applied** — **a second copy of the same image
  replaces the history row**, so a double save cannot be detected by counting rows.
- **⚠ One perturbation the contract specified pointed the wrong way.** It read "put `null` and `0`
  on the same path", but **the same path is the correct implementation**. Following the ruling
  "follow the server", the condition was ported as it stands and **the perturbation was inverted**.
- **Tests:** **JVM 197 / 0 failures** (41 classes, from 173), **instrumented 62 / 0 failures**
  (Pixel 9 hardware, from 46). **Only `android/VERSION` moves** — `APP_VERSION` and
  `web/BUILD_NUMBER` stay put, and nothing is deployed to pentala.

### v2.11.5 — the placement got a seed of its own (Build 860, render engine 23, 2026-08-08)

**Moving the seed to compare touches moved the composition as well.**

Up to engine 22 a single `render_seed` decided both the **placement** — where an arrangement puts
its marks — and the **hand**: each stroke's touch, the colour assignment, the ground, and the
resolution of the performance. So the operation "show me another touch of the same composition"
did not exist — **on a work that scatters 60 marks, moving `render_seed` alone moves all 180
coordinates**. `SPEC.md` `:614` and `:678` state the opposite: **refining the touch keeps the
composition of the same Score**. **This was a defect in the measuring instrument, not a missing
feature.**

- **`composition_seed` now carries the placement phase, and only that.** The key was already in the
  database, in the four render routes and in all four clients, but **it had never reached the
  renderer**. Five points of carriage were built to deliver it (the `renderer.render()` argument,
  the engine protocol, the default engine, `_render_with_metadata`, and `_render_score_svg` with
  `RenderSvgRequest`). **The four callers of `_render_with_metadata` were not changed by one line.**
- **`render_seed` keeps the hand.** Touch, colour assignment, ground and performance resolution do
  not move. **Placement and hand can be varied separately for the first time.**
- **With no `composition_seed` the placement falls back to `render_seed`**, so **not one existing
  picture moves**. **The test is `is not None`**, so **`0` is the seed zero and not "not given".**
- **The reference corpus goes 531 → 535 cases, and not one of the 531 moved** (the change list
  holds only the four added). The four are **twins of existing cases**, with the same Score and the
  same `render_seed`, differing only in `composition_seed` — **60/60, 16/16, 60/60 and 60/60** of
  the expanded marks move, so an implementation that confuses the two seeds fails them.
  **Layouts whose placement does not follow the seed (`G-radial-*`, `G-*-nopath-*`) were not used**,
  since they would make the expectation vacuous.
- **`ddl_engine_version` did not move** (still 7). Nothing through Stage 2 changes by a byte.
- **The Android reference fixtures gained a `render-engine-23/` directory of 55 files**, and **no
  Kotlin changed** — Android reads only the `render-engine-21/` it declares, so **raising the engine
  adds a directory and nothing else** (the design from cycle 43; demonstrated by JVM 197 / 0
  failures on the merged tree).
- **One gap remains**: the history SVG export (profiles other than `display`) does not pass
  `render_seed`, so **it now reproduces the placement of the stored picture but not its hand**.
  Before this change it reproduced neither, so **half is fixed and half remains**. Filed as [I-158].
- **Tests:** server **2379 / 31 skipped / 0 failed** (from 2367, **+12** for the new acceptance
  T-1..T-12); **eleven perturbations applied to product code only**. **One of them turned nothing
  red at first** — the generator that bakes the corpus and the two tests that check it **each wrote
  out the same argument list separately**, so cutting the generator's wiring left the tests still
  passing the value. **The replay was extracted into one named call to close it.**

### 2026-08-08 — the API schema description of `composition_seed` states its engine 23 role (Build 861, **version unchanged**)

**Engine 23 gave the seed the placement, but two of the three request models still described the old role.**

- **`ComposeRequest` and `PaintRequest` called it "Stage 1.5 composition variation seed"**
  (`render.py:189`, `:327`). **Only `RenderSvgRequest` stated the engine 23 role.**
  **This string is served in the OpenAPI document, so it is what a direct API user reads.**
- **Both roles were measured and written down**: on the `paint` and `compose` routes the seed
  **re-salts the intermediate expansion in `ddl_expander`** (the role `seed_summary` states at
  `reference.py:421-426`) **and reaches the renderer's placement phase through
  `_render_with_metadata`** (`rendering.py:316`).
- **Only the descriptions changed.** The `test_api_surface.py` ledger stays **82 / 82 / 82**, the
  **36 fields of `PaintRequest` and the 19 of `ComposeRequest` neither grew nor shrank, `required` is
  unchanged**, and **the only property that moved is `composition_seed.description`** (measured as a
  set difference; the digest follows).
- **Tests:** server **2379 / 31 skipped / 0 failed** (unchanged), ruff clean, `check_docs.py` green.
  **`APP_VERSION` was not moved** (no behaviour changes). **The 13 manual version markers go to Build 861.**

### Android `2.1.4-android.15` — a work can now be compared across models and languages (android Build 148098, 2026-08-08)

**Fourth of five.** 3/5 went as far as refining one element at a time; this release gives the app the
operation that **draws the same description again under different conditions and sets the results side by side**.

- **The instruction-language resolution was ported from the server condition for condition**
  (`language_support/registry.py`). Two supported languages, Japanese and English, and a third
  requestable word, `auto`. `auto` reads the text, and **the Japanese probe is asked first**, so a
  text holding both scripts resolves to Japanese. **The `(value or default)` falsy test was carried
  across as it stands** — replacing it with a default-valued read would send **a value of only spaces
  down another road**, so the spelling here falls back for `null` and the empty string and for
  nothing else.
- **All three stages — Stage 1, Stage 1.5 and Stage 2 — choose their prompt in the resolved language.**
  **The English Stage 2 prompt had never once been read from product code before this release**
  (the constant existed with zero references; measured). Stage 1.5 already held both language
  branches and **only its wiring was pinned to Japanese**, so that was joined up too.
- **Three columns were added to the history** — the requested language, the resolved language, and the
  description itself (the Room version goes 6 → 7). **Requested and resolved are written separately**,
  so a work drawn with `auto` can be read afterwards for what was asked and what it settled on.
  **The identity of a description is taken from `source_text` when there is one and from
  `original_input` when there is not** (the server's own two-step), so **a work drawn from a numbered
  batch line and the same sentence typed by hand count as the same description.**
  **[I-153] (no `source_text` column) is closed by this column.**
- **Model inspection and language inspection sit on the existing refinement skeleton.** The four entry
  points — open, generate options, abort, save — are shared by all three subviews, and **the only
  difference is the single function that returns the list of jobs** (SPEC `:688`: the comparison logic
  is not duplicated).
- **The lineage edge is written as `model_comparison` or `language_comparison` from one branch in one
  place.** The metadata keys recorded match the reference implementation one for one.
- **The work menu on the lineage card gained Model and Language** in the SPEC `:618` order. Choosing
  one opens the matching subview against that work, and closing it returns to the lineage view.
- **⚠ SPEC `:686` describes language comparison as having "the same three modes as model comparison",
  and the reference implementation has no such modes** (the web app offers the four Japanese/English
  pairs as checkboxes). **The contract's instruction was to follow the reference implementation, and
  the discrepancy is left with SPEC as [I-156].**
- **Fifteen perturbations were applied, to product code only** (the contract's fourteen plus one for a
  stage added along the way). **Three of them missed at first and exposed defects on the checking
  side** — a line that let an unknown fallback pass through, **a discriminating point that was the
  empty string rather than whitespace**, and an abort check where **the work went on running while
  only the flag came down, which read as "stopped".**
- **Measured during acceptance:** **the two places that read `source_text` change no judgement at all
  under the present shape of the data** — the write side stores the prefixed `original_input` and the
  bare prose as a pair, so **the existing prefix-stripping stand-in always yields the same answer**.
  **A perturbation dropping both reads left every JVM and instrumented test green.** They begin to
  matter only once a row holds two values that disagree; **that question is recorded on [I-153].**
- **Tests:** **JVM 223 / 0 failed** (43 classes, from 197), **instrumented 81 / 0 failed** (Pixel 9
  hardware, from 62). **Only `android/VERSION` moved one step** — `APP_VERSION` and `web/BUILD_NUMBER`
  stay put, and nothing was deployed to the dev server.

### v2.11.6 — the fade reaches every member of a group (Build 862, render engine 24, 2026-08-08)

**"It fades from the centre to the edge" was drawn as "all of it is a bit pale".**

`Arrangement.fade` declares how a group falls off — outward from its centre (`outward`), or along
the direction it travels (`directional`). Up to engine 23 the renderer answered that with **one
constant for the whole group**: 0.40 for outward, 0.48 for directional. **The same number on the
nearest mark and on the farthest.** **In production that is 2,738 of 6,425 groups (42.6%) and
83,703 of 178,694 marks.**

- **Every member of a group now carries its own ceiling**, ramped 0.62 → 0.18 outward and
  0.70 → 0.26 directional, by its position within the group. **No vocabulary is added and no
  field** — the declaration was already there.
- **The carriage is `color_hint`.** The tag is written after the colour cycle rebuilds the hint and
  **read back before normalisation flattens the decimal point.** Read after normalisation, the ramp
  is already levelled out.
- **Placement, touch and the performance seed are untouched.** `color_hint` sits outside
  `_SEED_INSTRUCTION_FIELDS`, so **the path coordinates of a fading group are byte-identical to
  engine 23 and only the opacity attributes differ.** The surface seed drops the tag before it
  hashes the instruction, so the texture does not move either.
- **A group that cannot fade was left exactly as it was.** A ring is equidistant from its own
  centre, and so is a pair. **Ranking them would draw a gradient nobody stated.**
- **⚠ A ring is not equidistant when measured from the centroid.** `_rhythm_t` returns 0 to 1
  **inclusive at both ends**, so **a ring of 12 puts its first and last member on the same point**
  and the centroid is pulled off the axis by **radius / count** (0.025 measured). Measured from
  there a gradient ran once around the ring, so **the `radial` branch alone measures from its own
  centre of rotation.** Every other layout still measures from the centroid.
- **A single-member group cannot be tagged by any implementation.** The `count == 1` branch does
  not pass through `_shift`, so **even under engine 23 the `fade` never reached the hint and such a
  group never faded** (measured: opacity 1.0).
- **The corpus went 535 → 541 cases, and seven moved** — the six added, plus the one existing case
  that moved, `G-scatter-fade-edge`. **The remaining 534 did not move by a byte.** That one case
  was **the whole of the corpus's fading** under engine 23. **Six cases were added for the routes
  that were never walked**: directional along a path, a colour cycle, a derived surface seed, a
  machine tool (**a machine fades too**, by the author's ruling), and **the two degenerate groups
  that must not move at all**.
- **`ddl_engine_version` did not move** (still 7). Nothing through Stage 2 changes by a byte.
- **Thirteen perturbations were applied to production code only, and none missed.** Two of them at
  first were applied to only one of the two branches, and the test they named stayed green.
  **Counting the points of enforcement and applying each perturbation to both branches turned them
  red** — reporting the one-sided attempt as a miss would have produced the false conclusion that
  the acceptance had a hole.
- **Tests:** server **2,403 passed / 31 skipped** (`def test_` 1,215 → 1,230, **nothing deleted or
  renamed**), ruff clean, frozen corpora byte-identical. **The Android reference fixtures gained a
  `render-engine-24/` directory of 55 files, and no Kotlin changed.**

### Android `2.1.4-android.16` — the app sketches before it paints (android Build 148098, 2026-08-08)

**The layer that rewrites a description into "the language of things" before Stage 1 reads it
(sketching, Stage 0.5) is now on Android.** The last of the five-part Android series; **`server/`,
`web/` and `shared/` were not changed by one line.**

- **The control has three states** (`Off` / `Fine` / `Coarse`), **defaulting to `Fine`** so the
  layer runs. **`Fine` and `Coarse` do not change how much is said — only the size of the pieces.**
- **Three columns were added to history** (Room 7 → 8): the sketch prose, the grain and the state.
  **`MIGRATION_7_8` backfills nothing.** Backfilling would turn **a work drawn before the layer
  into a work drawn with the layer switched off** — **the absence of a value carries a sixth
  meaning.**
- **⚠ The server and the web client each hold a normalisation function of the same name whose
  answers differ on unknown or missing input** (the server rounds to the default, the web client
  returns `null`). **The port gives them different names, and comparison against a parent uses the
  web one.** **Confusing them inverts the verdict in both directions for a work with no grain
  recorded.**
- **A fallback row records no sketch prose** (**author's ruling 2026-08-08, matching the server**).
  **What a fallback carries is the description itself**, and writing that into the sketch column
  would make **a work that never passed through the layer indistinguishable from one that did.**
- **Sketching is non-deterministic, so reproduction means sending the stored sketch prose again,
  not sketching again.** A redraw whose description and grain both stand still carries the parent's
  prose.
- **Refinement candidates inherit the parent's sketch prose too.** Without it **the parent is drawn
  from the sketch and the candidate from the raw description**, which makes it a refinement of
  something else.
- **Twelve perturbations were applied to production code only, and none missed.** **One was split
  in two because the contract expected a single edit to turn two tests red** — **one of them reads
  the SQLite column directly, and the normalisation function is not on that path.**
- **Tests:** **JVM 235 / 0 failed** (44 classes, from 223), **instrumented 93 / 0 failed** (Pixel 9
  hardware, 18 classes, from 81). **Test functions +24, nothing deleted or renamed.**
  **Only `android/VERSION` moved one step** — `APP_VERSION` and `web/BUILD_NUMBER` stay put, and
  nothing was deployed to the dev server.
- **⚠ Stage 1 and Stage 2 still run at temperatures that differ from the server** (0.2 and 0.1
  against the sketch layer's 0.3). **That divergence predates the sketch layer**; it was left alone
  and recorded as **[I-159]**, pending a ruling.

### Android `2.1.4-android.17` — waiting for the write before the close (android Build 148098, 2026-08-08)

**Saving a work schedules a thumbnail, which is built in the background and written back to the
database.** Nobody waited for it: `InkuRepository.close()` was one line, `thumbnailScope.cancel()`.
**`cancel()` only asks; it does not wait.** So the database could be closed while a write was still
running, and **the throw happened on the background coroutine rather than on the caller** — which
took the whole process down and left the remaining tests unrun. **It arrived as "24 of 93 recorded"
rather than as one red test**, so a run that counted nothing looked green. **Five of twelve runs
were truncated this way** ([I-150]).

- **`close()` now waits** for the thumbnail scope's children before tearing it down.
  **⚠ Not `cancelAndJoin`** — cancelling first abandons the write, so the thumbnail never lands and
  **there is no property left to assert.**
- **Four of the twelve instrumented classes closed the database without closing the repository.**
  More precisely they closed it **asynchronously** through `store.clear()` → `onCleared`, and
  **leaned on a 500 ms sleep.** They now close it directly; the sleep stays as a belt for the other
  work the view model starts.
- **Two gates.** On the device: save, `close()`, and the row already carries the thumbnail path. In
  the server's pytest: every `database.close()` is covered by an earlier `repository.close()`.
  **The second lives on the server side because pytest runs every cycle while Gradle runs only when
  `android/` changes**, and four tests already read the Kotlin sources from pytest.
- **The shipping app never closes the Room database**, so this is a defect in the test scaffolding
  rather than something a user can see. In production the worst case is one lost thumbnail write as
  the app goes away.
- **Both perturbations turned exactly one named test red.** Reverting `close()` to `cancel()` alone
  turns the instrumented T-1 red; deleting `repository.close()` from one class turns the server's
  T-2 red. Restoring each returned the count to zero.
- **Tests:** **instrumented 95 / 0 failed** (Pixel 9 hardware, 19 classes, from 93), **JVM 235 /
  0 failed** (44 classes, unchanged), **server pytest 2405 passed / 31 skipped** (from 2403).
  **Only `android/VERSION` moved one step** — `APP_VERSION` and `web/BUILD_NUMBER` stay put, and
  nothing was deployed to the dev server.
- **⚠ Two more tests than predicted.** The prediction frozen before any code was written said +1 and
  +1; **each gate gained a contrast case.** Without the contrast, the instrumented assertion would
  hold vacuously if the save happened to finish the thumbnail itself, and the structural rule would
  pass over an empty set. **The number of properties is the predicted one on each side.**

### Android `2.1.4-android.18` — naming what the app draws with (UI redesign, stage A; android Build 148098, 2026-08-08)

**One file, `InkuApp.kt`, held 89 hardcoded colours (57 values), 429 `.dp` literals (54 values) and
8 `.sp` literals (5 values).** The other 68 Kotlin files held none of the three, so **every literal
was in one place.** This stage gives them names and **does not move the drawing by a pixel.**

- **A token layer.** `ui/theme/Color.kt` (65 tokens plus the 9 `InkuColors` roles), `Dimens.kt`
  (**new**, 53 values — `0.dp` gets no token), `Type.kt` (5 sp values). What is left inline in
  `InkuApp.kt` is **no colours, no `.sp`, and the 20 occurrences of `0.dp`.**
- **Two independent checks that no value moved.** Normalising the tokens to symbols and diffing
  gives **5,756 lines against 5,756 with zero structural difference** — nothing but substitution
  went in. And **the 57 colours, 53 dp and 5 sp values from before are all present** in the token
  sets.
- **65 colour tokens carry 57 distinct values.** Seven groups share an ARGB and were given more than
  one name, which is the direction the gate allows: **growing is fine, shrinking is the regression.**
  **The names were not folded together**, because they agree today by coincidence and stage B may
  need to move one without the other.
- **A preview for Claude Design, with its generator.** `android/design/gen_design_preview.py` reads
  the Kotlin sources and needs neither Gradle nor the Android SDK, so it runs in CI; a job in
  `reference-corpus.yml` demands byte equality. **A generator CI cannot run defeats the purpose of
  watching for staleness.**
- **All eight perturbations turned their named test red** (the five extra reds are overlaps the
  design predicts). **⚠ The contract's P-3 — delete an unused colour — could not be run:** all 65
  tokens are referenced, and the seven duplicated values can each be deleted with the gate staying
  green, so deletion has no discriminating power twice over. It was replaced by a perturbation that
  causes the property directly in production code.
- **Tests:** **JVM 238 / 0 failed** (45 classes, from 235), **server pytest 2411 passed / 31
  skipped** (from 2405), **instrumented 95 / 0 failed** (Pixel 9 hardware, 19 classes), ruff clean,
  `check_docs.py` green. **Only `android/VERSION` moved one step.**
- **⚠ 22 of the 53 dp values sit off the 4dp grid and not one was moved.** **Stage B does that when
  it rebuilds the screens** — moving both in one cycle would make it impossible to tell which change
  moved the drawing. By then only `Dimens.kt` has to change.
- **⚠ The version is `.18` rather than `.17` because the [I-150] fix took `.17` the same day.**

### v2.11.7 — Every member of a group gets its own size (Build 863, render engine 25, 2026-08-08)

**An `Arrangement` says "several of this shape". Nowhere does it say "all of them the same size".**

Through engine 24 the expansion rewrote coordinates and nothing else, so the N members came out
**exactly congruent — one shape copied N times.** That congruence was never asked for by the
description: **it was the largest signature the engine was adding on its own.**

- **Hand tools now vary in size inside a group.** The amplitude lives in the tool's grammar as
  `group_hand`, and **all nine hand tools carry the same ±25%** (`HAND_GROUP_SIZE`). Deriving it
  from `fill_hand` would give silverpoint ±1.25% and brush_thick ±25%, **which is no longer the
  picture the author approved**, so it is one constant.
- **`rotring` and `computer` stay at zero.** Exact repetition is the machine's signature, not a
  defect to sand off — the same discipline engine 22 gave `fill_hand`. **It was checked by eye:**
  drawing one Score with only the tool swapped, the 24 `rotring` circles carry a single `r="50.0"`
  in the SVG while the 24 `pen` circles spread over 0.766x..1.266x.
- **Size is drawn from the performance seed, not the placement seed.** Engine 23 separated
  composition from performance; **taking the size from the placement seed would undo that split on
  the day it was made.**
- **⚠ The expander's argument had been misnamed since engine 23** — the second parameter was called
  `performance_seed`, but what reached it was the `placement_seed`. **It was renamed to match what
  it holds, and the performance seed added as a separate keyword argument.**
- **Placement does not move by a pixel.** After expansion `_fit_group_to_anchor` reads nothing but
  the anchors, so **a scaling rule that moved one would hand the placement a different group.** All
  four rules preserve their own anchor: a line scales **about its midpoint**; square and triangle
  scale `size` and pull `position` back by half the growth; circle, arc and polygon scale `radius`;
  ellipse and cloudform scale both components of `size` by the same factor (**the aspect never
  changes**).
- **Three groups are left alone**: **`grid`** (a tiling whose point is that the cells match — author
  ruling), **a group of one** (nobody to differ from), and **the machine tools**.
- **The corpus goes 541 → 545. Thirty-seven cases moved; 504 did not move by a byte.**
  **⚠ All 37 that moved are `circle` groups** — the corpus walked nothing else, so **one group each
  of `line`, `square`, `triangle` and `ellipse` was added.** Line, ellipse and square alone are
  82.8% of the marks in production, yet **three of the four rules had never been baked.** The bake
  now asserts that those four cases discriminate before it writes them out.
- **`ddl_engine_version` did not move** (still 7). Nothing changes up to Stage 2.
- **All twelve perturbations broke production code and none missed.** **Four of them missed on the
  first pass**, and the acceptance test — never the product — was fixed and the perturbation
  re-applied. **All four were of one kind: the gate did not traverse the layer the perturbation
  broke**, and two of them had the corpus's own blind spot inside the tests, measuring with circles
  only.
- **⚠ Eight places went red that the contract had not predicted.** Beyond the five that follow from
  the version bump, **the moving sizes themselves** moved existing tests. Three of those read the
  fade and the seed split against engine 23's frozen bytes, and now **neutralise engine 25's layer
  before comparing** — the same move engine 24 made against engine 23's `_apply_fade_levels`. **The
  yardstick, the frozen body, was not touched.**
- **Tests:** server **2,442 passed / 31 skipped** (from 2,411; `def test_` 1,238 → 1,255, **none
  deleted**), cli 176, `npm run check` 241 FILES / 0 errors, ruff clean, frozen corpora
  byte-identical. **The Android reference fixtures gained `render-engine-25/` (55 files) and not one
  line of Kotlin changed** — Android reads only the directory of the version it names. **JVM 238 /
  0 failed, unchanged.**

### v2.11.8 — Every member of a group finds its own angle (Build 864, render engine 26, 2026-08-08)

**Engine 25 gave up "the same size". What was left was "the same angle".**

An `Arrangement` says only "several of the same shape". **Nowhere does it say they all face the same
way.** After engine 25 the N members of a group still shared a single angle. **This is the last stage
of improvement plan #5.**

- **A hand tool now gives each member of a group its own angle.** The spread lives in the tool
  grammar as `group_rot`, and **all nine hand tools carry the same ±12°** (`HAND_GROUP_ROT`).
  It is a single constant for the same reason the previous stage made `group_hand` one.
- **`rotring` and `computer` stay at 0.** Exact repetition by a machine is a signature, not a defect;
  this is the third rule of that shape, after `fill_hand` in engine 22 and `group_hand` in engine 25.
- **Not one pixel of placement moves.** `_turn_member` rewrites `rotation` and nothing else.
  **`_apply_rotation` turns a mark about its anchor**, so **the three coordinate corrections the
  previous stage needed have no counterpart here.** Size can move a centre; angle cannot.
- **Five exclusions**: **`line`** (turning a line makes a different line), **`circle`** (turning it
  changes nothing visible while consuming performance seed), **a group that states its `rotation`**
  (if the description names the angle, the description wins), **`grid`** (a lattice is meant to line
  up), and **a group of one**.
- **⚠ The test is `stated.rotation is not None`, not truthiness.** **Production holds 141 groups that
  state `rotation: 0`.** Written as a truthy test, exactly those 141 fall through to "unstated" and
  get turned. **A case that states `0` was added to the corpus, with a gate that watches only that
  point.**
- **The angle comes from the performance seed, not the placement seed** — the boundary engine 23 drew
  between composition and performance, kept for the same reason as the previous stage.
- **⚠ The expander argument `size_seed` was renamed to `member_seed`.** The previous stage named it
  for size, but angle reads the same seed, so **the name had grown narrower than the thing.** No
  `size_seed` remains in the tree.
- **The corpus goes from 545 to 549 cases. Only 3 moved; 542 are byte-for-byte unchanged.** The three
  are `G-size-ellipse-edge`, `-square-` and `-triangle-`, which the previous stage added itself —
  **the groups that are neither circles nor lines carried straight over into this stage.**
  **⚠ The corpus held no `arc` group, no `cloudform` group and no group stating a `rotation`**, so
  **four cases were added** (`G-angle-arc-edge`, `-cloudform-edge`, `-stated-zero-edge`,
  `-stated-30-edge`). The generator asserts that those four discriminate before it writes them out.
- **`ddl_engine_version` does not move** (still 7). Nothing through Stage 2 changes by a byte.
- **All twelve perturbations broke production code, and none of them missed.** **One hole was found
  before the perturbation was applied**: bleeding the angle into the size and comparing against
  "the same build with the angle layer disabled" leaves **the same broken coefficient on both sides,
  so the gate stays green**. It was closed by adding **a check that redraws engine 25's 43 frozen
  cases through the product now in the tree and compares against the digest engine 25 recorded** —
  a live drawing against a frozen record, not one frozen file against another. **What was added is a
  gate, not production code.**
- **⚠ Unlike the previous stage, not one golden digest moved.** Six unforeseen failures appeared, but
  **all six follow from adding four corpus cases, and none from the angle moving.**
  `test_legacy_arrangement_layouts_keep_golden_output` stays green because **all four of its goldens
  are circle groups** (engine 26 does not turn circles). The same check went red under engine 25 and
  was re-taken for the seventh time.
- **Confirmed by eye.** Drawing one production Score under each version, engine 25 emits **no
  `rotate(` at all** — the Score names no angle, so all 109 marks line up the same way. Engine 26
  gives **all 109 a distinct angle**, every one inside **-11.95° to +11.83°**.
- **Checks:** server **2,466 passed / 31 skipped** (from 2,442; `def test_` 1,255 → 1,270, **none
  deleted**), cli 176, `npm run check` 241 FILES / 0 errors, ruff clean, frozen corpora
  byte-identical. **The Android reference fixtures gained `render-engine-26/` (55 files) and not one
  line of Kotlin changed** — Android reads only the directory of the version it names. **JVM 238 /
  0 failed, unchanged.**

### Android `2.1.4-android.19` — putting the work first (UI redesign, stage B; android Build 148106, 2026-08-08)

**The first band of the screen was the drawing settings, and the work sat in the fourth.** Stage A
gave the values names; **this stage uses those names to rebuild the layout and the wayfinding** —
the work moves to the top, and the settings gather directly above the description.

- **Three families: work information, drawing settings, export.** The model selector goes from
  **three entry points to one**, and export becomes **a single bottom sheet**. Magnification and
  canvas ratio each move into the family they belong to.
- **The mascot appears only while something runs.** A row matching web's `RunStatus` (mascot, model
  name, elapsed time, stop) was added, and **the condition for showing it is web's — "something is
  running."** Choosing the mascot stays in settings: that is a preference, not a state display.
- **Viewing gathers in the full-screen view.** Pinch 0.25×–10×, pan, double tap to toggle fit ⇄
  actual size, back key to leave. **Zoom in the normal view was removed, condition and all.** The
  swipe direction is unified as **right = previous, left = next** (only the full-screen view had it
  reversed).
- **While the IME is up, Paint stays pinned directly above the keyboard.** The description field
  moves to the top of the screen when focused. **Nothing is bound to the IME action key** — in
  Japanese input the return key confirms a conversion, so the drawing would start on a keystroke
  meant to confirm text.
- **The bottom bar goes from five destinations to four** (description, history, lineage, settings).
  **Running the demo moved into settings.**
- **The dimension and type systems were folded down.** Button heights **5 steps → 3** (56 / 40 / 32),
  corner radii **4 kinds → 2** (card 16dp and pill), spacing **4 steps** (4 / 8 / 16 / 24), smallest
  type **11sp → 12sp**. `Dimens` goes from **56 `Dp` declarations to 41**, and **literals off the 4dp
  grid from 22 to 0** (the 1dp hairline is the one exception). **Tokens no longer borrow across
  families.**
- **⚠ `uiMode` (full / simple) means something different now.** The only differences used to be the
  mascot and a duplicated chip row, and **this stage removes both, so the distinction was empty.**
  Simple now folds away `interpretation` (the DDL field and drawing from DDL).
- **⚠ "Visible above the IME" cannot be measured under instrumentation.** Compose pins window insets
  to 0 while instrumented, so `imePadding()` lifts nothing and **the gate stays red whether the
  perturbation is applied or not** — it was measuring the test host, not the product. The gate was
  re-seated as **"the main action exists exactly once, sits outside the scroll, and the bottom bar
  has yielded its place"** (true even with a 0 inset, false when the focus wiring is cut).
  **That it clears the keyboard is evidenced by a screenshot from the real device.**
- **⚠ Instrumentation wiped the app's data on the device once.** `gradle
  :app:connectedDebugAndroidTest` **uninstalls the app after the run by default**, so running it on a
  device holding real works takes the database with it. **Recovery was luck** — the database had been
  copied off before the work started, to measure a baseline. The flag
  (`-Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true`) was measured to avoid it, and
  **how to write that into the conventions is filed as ledger item [I-162].**
- **All eleven perturbations turned their named gate red** (no misses, no misnamed gates). The three
  extra failures were all **stage A's T-8, the design-preview byte comparison** — **a regenerated
  record, not a check on a property** (moving any token turns it red by construction).
- **⚠ `DDL` was not added to the work-information switch** (the contract's family table listed four).
  DDL is readable from the `interpretation` field and the DDL editor, so **a fourth tab would be
  adding vocabulary.**
- **⚠ Some items still carry no gate** — where the back key goes, the 48dp touch target, spacing
  being exactly four steps, and the canvas being topmost. **The contract had no T for them either,
  and this stage did not measure them** (they were confirmed by eye only).
- **Checks:** **server pytest 2,476 passed / 31 skipped** (measured on merged main: 2,466 plus the
  ten T-1–T-10), **JVM 238 / 0 failed (45 classes)**, **instrumentation 96 / 0 failed** (Pixel 9,
  20 classes, measured by the implementing session), ruff clean. **Only `android/VERSION` moves one
  step** — `APP_VERSION` and `web/BUILD_NUMBER` stay put, and nothing is deployed to pentala.

### 2026-08-09 — Rasterizing a folder is one command (**no version bump**; `shared/` and `cli/` only)

**The PNGs used for looking at work were burned by throwaway scripts, one per run.**
`851-…/harness/rasterize_one.py`, `859-…/harness/rasterize_all.py`, `rasterize_full.py` and
`864-…/harness/rasterize_on_pentala.py` all **call the same single line** (`svg_to_png(svg, width=width)`);
only the worker count and the output directory differ. **There were four copies of one rule, and the next
run would have grown a fifth.**

**The rule now lives once, in `shared/src/inku_analysis/rasterize_batch.py` (213 lines), and the CLI is a
thin door onto it.**

- **`rasterize_dir(src, dst, *, width=None, workers=1) -> Report`**, with **one child process per file**
  (ledger I-075: a resvg panic in-process takes the interpreter with it). The child re-enters the module
  as `python -m inku_analysis.rasterize_batch --one` — **so that no second rule for burning a picture
  gets written anywhere.**
- **A file that cannot be burned leaves nothing behind.** The child writes a hidden temporary file and
  **only the parent renames it into place**, and only when the child exited 0 and the temporary is not
  empty. The trigger was an interrupted run that **left one 0-byte PNG**: "a failure is absent, not zero"
  is a rule about reading numbers, and a file on disk breaks it before the reading starts.
- **`__main__` prints the population it dropped** as `UNRESOLVED (absent measurements, not zeros):`
  with a reason per file, and exits 1.
- **The module imports neither `inku_cli` nor `inku_server`.** `server/Dockerfile` copies `shared/` and
  `server/` but not `cli/`, so running as `python -m` inside the container is a requirement, not a style.
- **`inku-cli rasterize --in DIR --out DIR [--width N] [--workers N]`** calls the shared function and
  nothing else. **`cli/README.md`'s help section was regenerated** (48 → **49 paths**).

**Deploying it needed a flag that did not exist**, so one was added: **`deploy.sh --shared`** (`shared/`
only, no `--delete`, restarts `inku-api`). **Until then the only flag carrying `shared/` was `--all`,
which also sends `cli/`, `docs/` and `manual/` — the tree ledger I-059 exists to keep off the
development server. There had been no legal route for a `shared/` change to reach pentala at all.**

**Measured 2026-08-09** on 24 real SVGs at width 1618: **pentala at 6 workers, 17.7 s = 0.74 s/picture**;
**the Mac at 4 workers, 70.1 s (136 s CPU = 5.66 s/picture)**. **All 24 PNGs are byte-identical between
the two machines** (resvg 0.3.3), and `inku_analysis` imports on pentala with no `sys.path` handling.

- **⚠ The contract's perturbation P-6 did not match what T-9 guards.** Adding a flag does not remove the
  `rasterize` section from the manual; **only adding a subcommand without regenerating (P-6b) turns it
  red.** The gate is the right shape — **the contract's perturbation column was written wrong** (filed
  in the ledger).
- **⚠ Acceptance closed one hole.** Stage 1 of the contract asked that `__main__` print UNRESOLVED, but
  **only the return value of `rasterize_dir` had a gate**. `python -m` is the one entry point the
  container and the development server use, so **the printing is production behaviour**. Two gates were
  added, and two perturbations (returning 0 despite failures; printing UNRESOLVED unconditionally) each
  turn exactly one of them red.
- **Checks:** **server pytest 2,485 passed / 31 skipped** (from 2,476: seven from the implementation,
  two from acceptance), **cli pytest 182** (from 176), ruff clean across `server`, `cli` and
  `shared/src`, `check_docs.py` green, frozen corpora byte-identical. **No version bump** — web
  behaviour and the API are unchanged, and **no server path imports `rasterize_batch`.**

### v2.11.9 — Eight old works stop taking the process down when exported (Build 865, 2026-08-09)

**Eight of production's 2,769 works aborted the whole server process when asked for a PNG** (ledger I-075,
filed 2026-08-01). The cause is a Rust assertion inside `resvg` (`filter/displacement_map.rs`), and **a Rust
panic is not a Python exception, so `try: … except Exception:` catches none of it.** The PNG save at
`api_core/rendering.py:85` is written in exactly that shape — **it looked defended and was not.** `inku-api`
runs as **a single uvicorn worker** (no `--workers`), so **one export killed the API and every request in
flight with it.**

**Raising `resvg-py` from `>=0.3.3` to `>=0.3.4` fixes all eight.**

- **0.3.4 was published 2026-08-02 — the day after the ticket.** Raising the version was not an option when
  the ticket was written.
- **Measured as a pair, through the call the product makes** (`svg_to_bytes(svg_string=…, width=…)`):
  **0.3.4 burns all eight at no width, 320 and 2160; 0.3.3 fails six, eight and six of them.**
  **⚠ Which ones fail depends on the width**, so "it fails at every size" was imprecise.
- **The pixels do not move.** 120 SVGs carrying `feDisplacementMap` are byte-identical under both versions;
  **the Mac and pentala agree 24/24 under 0.3.4** (as they did under 0.3.3); and the 24 PNGs burned under
  0.3.3 are byte-identical to the 24 burned under 0.3.4.
- **⚠ Only old works abort.** **None of the 1,065 filter-bearing works at render engine 11 or later fail**
  (7 of 790 at engine 10 or earlier, 1 of 89 with no recorded version). Recent engines carry *more*
  filter-bearing works, so this is not a skewed population: **the renderer stopped emitting the shape that
  trips the assertion somewhere before engine 11.**
- **The regression fixture is one of the eight** (production `4c257de0`, engine 4, Build 591) rather than
  something built from a Score, **because that shape is no longer generated.** It burns through
  `rasterize_dir` — one child process per file — so **a returning panic lands as one red test instead of
  killing pytest.**
- **Checks:** **server pytest 2,486 passed / 31 skipped** (from 2,485: **+1 test, +1 case**), **cli 182**,
  ruff clean, frozen corpora byte-identical (they compare SVG, which the rasterizer version cannot move),
  `test_version_consistency.py` 8 cases. **⚠ No screen or API key changes.** The version moved so that the
  tree deployed to pentala and the number that names it stay in step.

### 2026-08-09 — The bake asks the corpus whether the fade reaches every member (**no version bump**; checks only)

**Three guards run as the reference corpus is baked, each asking whether a case really sees the mechanism
it was added for — and the `fade` one was the weak member of the three** (ledger [I-166], author ruling A).

- **What was weak** — the size and angle guards withhold `_apply_member_sizes` / `_apply_member_rotations`,
  **the mechanism itself**, and compare the drawings. The `fade` guard only rewrote `fade="none"`.
  **Engine 23 already answered `fade` with one constant for the whole group** (0.40 outward, 0.48
  directional), **so a renderer carrying no per-member ceiling at all still changes the picture when the
  declaration goes away — and still passes.**
- **What was added** — `_assert_fade_reaches_every_member`, which **asks the corpus directly**: some drawn
  fading group has to hold more than one ceiling, and **the two degenerate groups have to hold none**.
  **The engine's behaviour is not changed by a single line** (a ring is equidistant from its own centre and
  so is a pair; ranking them would draw a gradient nobody stated).
- **⚠ The obvious fix cannot be taken.** `G-fade-radial-edge` and `G-fade-count2-edge` do not fade by
  construction, so withholding the rule leaves them untouched and a strong form applied to all six always fails.
- **⚠ The weak guard was kept**, with the new question added beside it, and a check now holds the wiring
  itself: dropping the call from the bake turns exactly one test red.
- **Checks:** **server pytest 2,488 passed / 31 skipped** (from 2,486: **+2 tests, +2 cases**), ruff clean,
  frozen corpora byte-identical (**no drawing moves**). **Three perturbations**: making the fade a
  pass-through turns 18 red **while the weak guard stays green and the new question goes red** — which is
  the claim of the item itself; cutting the wiring turns exactly one red; ramping an equidistant group
  turns three red (the new question plus the ring and the pair). **No version bump** — no version, API key,
  screen, or drawn pixel changes.

### Android `2.1.4-android.20` — the port catches up to render engine 26 (android Build 148106, 2026-08-09)

**The Kotlin drawing layer still declared engine 21, five versions behind.** Engine 22 (the fill underlay and
the tools), 23 (the placement seed), 24 (`fade` reaching every member), 25 (per-member sizes) and 26
(per-member angles) were all carried over in one pass, and `CompatibilityConstants.renderEngineVersion` now
reads `"26"`. **`APP_VERSION` and `web/BUILD_NUMBER` do not move.**

- **⚠ Before the catch-up, the corpus turned out to be unable to SEE five of those versions.** All 34 grouped
  cases in the reference fixtures were circles, so only the rules that apply to a circle were ever walked.
  **The mechanisms were not missing; the cases were.** An `arc`, a `cloudform`, a `square` and two groups that
  state their own angle were added among others: **34 → 42 cases, 42 → 51 SVGs.**
- **The four bake-time guards were ported.** Three map one-to-one onto the server's; the fourth was added
  because **the `fade` guard proved weak** — it only withholds the declaration — **and the server side was
  fixed the same day** (ledger [I-166]).
- **Two pre-existing divergences surfaced**, both invisible while every group was a circle: the cloudform
  contour was generated with a hard-coded `markIndex = 0`, so **every member of a group was drawn with the
  first member's blob**, and `rotate()` was written with spaces and raw doubles.
- **Every tool's texture filter was weaker than the server's** — the Kotlin side wrote the raw spec without
  the material-strength coefficient (pencil 0.7 vs 1.96, crayon 1.8 vs 5.04, chalk 2.2 vs 6.16). It is a
  display-only path, and **nothing held it.**
- **⚠ `drypoint`'s texture filter was NOT added**: both Kotlin lookup tables name only four tools, so a
  definition alone would be read by nobody, and **no acceptance gate could be placed on it.**
- **⚠ Adding the non-circle cases turned one server test red.** F-2 of the Android fixture check requires
  every anchor to carry nine decimals; a `square` anchor is `position + size/2`, **a sum, so sixteen decimals
  there is the rule working rather than a port skipping it** — and the claim only held while the corpus was
  all circles. **By author ruling A (ledger [I-165]) F-2 now asks it of the primitives whose anchor is a
  stored coordinate.**
- **Checks:** **Android JVM 243 passed, 0 red, 0 skipped (46 classes; exactly +5 from 238)**, **96 of 96
  instrumentation tests green on a physical Pixel 9 (20 classes)**, **server pytest 2,488 passed / 31
  skipped**, ruff clean. **All nine perturbations turned red as predicted; none missed.**

### v2.11.10 — The hand swings wider (Build 866, 2026-08-09; render engine 27)

**The two amplitudes engines 25 and 26 introduced were widened after the round-2b viewing**
(author ruling, 2026-08-08). **No rule and no exclusion changed. Only how far the hand swings did.**

- **Per-member size goes from +/-25% to +/-35%** (`HAND_GROUP_SIZE` 0.25 -> 0.35) and
  **per-member angle from +/-12 to +/-27 degrees** (`HAND_GROUP_ROT` 12.0 -> 27.0).
  **All nine hand tools carry the same amplitude**, and **`rotring` and `computer` stay at 0**
  (a machine repeating itself exactly is a signature, not a defect).
- **Not one line of the exclusions moved** — `grid`, single-member groups, the machine tools, `line`,
  `circle`, and groups that state a `rotation`. **A circle looks the same turned**, so it is still not turned.
- **The corpus moves on 45 of its 549 cases and holds the other 504** (`render-engine-27`).
  **No case was added** (`added` = 0). The 45 are circle 37, ellipse 3, line 1, square 1, triangle 1,
  arc 1, cloudform 1, and **only 5 of them are reached by the angle rule as well**.
- **The frame correction did not fire on more groups.** The prediction when the work was commissioned was
  that a wider swing would push more groups into it; **the measurement says it fires on the same 40 of 50
  groups as engine 26, and on the same set.** `_fit_group_to_anchor` **reads only the members' anchors**;
  `_scale_member` preserves the anchor through three coordinate corrections, and `_turn_member` turns about
  the anchor, so it moves no coordinate. **However wide the swing, the input the frame correction reads is
  bit-for-bit the same.**
- **"Marks stay inside the frame" was never true, with or without the wider swing.** The frame
  `[0.02, 0.98]` is a contract about anchors, not about how far a mark spreads. **At engine 26, 41 of 50
  groups already had member outlines crossing the canvas `[0,1]`**, and **engine 27 has the same 41**;
  the one that reaches furthest got 0.4% of a canvas deeper (0.050187 -> 0.054262).
- **The check that replays engine 25's frozen drawings now puts the size amplitude back to 0.25** rather
  than withholding `_apply_member_sizes`. **Withholding it would pass for an implementation that had
  dropped per-member size altogether — the reading engine 25's own gates exist to reject.** The angle
  amplitude is left at whatever the tree states, and **the 43 digests still land**, which re-confirms that
  the angle rule reaches none of those cases.
- **Checks:** **server pytest 2,501 passed / 31 skipped** (+13, 0 red; **+5 test functions, 0 deleted**),
  ruff clean, **frozen corpora byte-identical**. **Seven perturbations, none missed.**
  **One predicted gate did not turn red, though:** a check that compares manifest 26 against manifest 27
  does not move when a product constant is put back. **That is a regenerated record, not a check on a
  property.** What turned red through the product was the existing
  `test_group_g_matches_the_current_renderer`, on all six of the product perturbations.

### 2026-08-09 — The English documents now answer to the glossary (**no version bump**, documents and checks only)

**`web/src/lib/i18n/GLOSSARY.md` is canonical for all of inku's English, but the only thing a machine
compared against it was the web display strings** (ledger [I-161]; the author ruled that the check reads
the documents that are still updated). `npm run lint:i18n` reads `en.ts` and the web components —
**not one of the English documents** (README, SPEC, the manual, ANDROID_SPEC). `check_docs.py` does look
at both languages, but **only at the heading shape, never at the words inside**. So "green while the
terminology is wrong" kept happening.

- **Twenty-four lines across five English documents were corrected. Not one character of the Japanese
  changed** — the Japanese was already right (`SPEC.ja.md` carries 22 occurrences of the concept word
  against three `palette`, all three inside backticks), and **only the English still held the old
  vocabulary**. Fixing the English is what makes the two languages agree
- **There are only two ways to fix such a line.** Fifteen lines named a **concept** (the work itself, the
  color catalog itself) and **the word was changed**; nine named a **code identifier** (an enum member, a
  JSON field, a tab's internal name) and **the word was wrapped in backticks instead**.
  **"Zero grep hits" is not the goal** — an identifier should stay an identifier, and wrapping it is what
  takes it out of the machine's view. `Artwork` in `ANDROID_SPEC.md` is a Kotlin enum member that
  **never reaches the screen** (zero hits in `strings.xml`); renaming it would make the specification lie
  about the implementation
- **The gate went into `check_docs.py`**, because that is the one gate the conventions require before every
  merge — CI only regenerates the frozen corpora. It reads **the English side of the 17 `PAIRS`** for
  **four words** (`artwork`, `palette`, `AI-powered`, `magic`). **`CHANGELOG.md` and
  `docs/history/changelog-*.md` are frozen records and are a declared exemption.** The number of documents
  read is printed on every run, so a shrinking table cannot hide behind exit 0
- **⚠ It reads inside fenced blocks**, unlike every other check in that file. **One of the 24 lines,
  `PROJECT_CONTEXT.md:54`, lived inside a fence** (a pipeline drawn as `text`, whose content is prose);
  skipping fences would leave that line unwatched. **The cost** is that a future revision showing a real
  catalog JSON example has no way to escape by wrapping, and will need a declared exemption instead
- **Twenty-seven checks read the configuration tables themselves** (`test_terminology_gate.py`).
  **They do not assert a total.** Each of the four words is asserted on its own, each of the 17 documents
  is asserted on its own, **the three exempt documents are asserted to be absent** as a control,
  `main()` is asserted to consume the result, a backticked word is asserted not to be a violation, and a
  bare one is asserted to be found. Deleting a single row would otherwise leave `check_docs.py` at exit 0,
  simply looking at less
- **Checks:** **server pytest 2,528 passed / 31 skipped** (**+27, 0 red, 0 deleted**), ruff clean,
  `check_docs.py` green (**17 documents, 55 internal references**). **Six perturbations**, one of them a
  control: adding a bare forbidden word to the exempt `CHANGELOG.md` turns nothing red, and **the same
  sentence placed in `README.md` does turn it red**, so the silence is the exemption working rather than a
  miss. **⚠ P-2 was the one that disagreed with the prediction** — removing `artwork` from the word list was
  predicted to redden one check and reddened two, because **the example sentence in the "a bare forbidden
  word is found" check uses that very word**. That is coupling rather than a defect, and it errs toward more
  red, so the gate is not weaker. **The deterministic layers and `web/`, `cli/`, `shared/`, `server/src`,
  `android/app` did not move by a single byte**
- **No version bump** — no version number, API field name, screen, or drawn mark changes

### v2.11.11 — A work remembers its own colors (Build 867, 2026-08-09)

**A redraw sent the stored catalog id to the server, and the server looked up today's definition to
decide the colors.** So **changing a catalog silently repainted every work that named it**
(ledger [I-123]). **1,274 of the 2,769 works in production (46.0%)** were in that group.

- **The canonical colors moved from the catalog id to the record the work carries.** When a request
  names a work (**`work_id`** on `/api/render-svg` and `/api/render-score`, **`--from-work`** in the
  CLI), the server draws from that row's `render_color_map` and **never reads today's definition**
- **A renamed catalog and a retired one now both draw** — this path never resolves the id, so an id
  no current build knows **no longer answers 422**. An older work that recorded no colors falls back
  to the current definition, and **that fallback does not answer 422 either** (refusing there would
  leave exactly the works older than the record unable to be redrawn)
- **The response says where the colors came from** — `render_color_source` on `/api/render-score`,
  and two headers on `/api/render-svg` because its body is the SVG (`X-Inku-Color-Source` and
  `X-Inku-Color-Catalog-Id`). **The second one exists because a caller that names a work names no
  catalog, and would otherwise have no way to learn which catalog drew the picture**
- **The nameplate shows the current name**, with `Retired` for a catalog that is gone and
  `No record of its colors` for an older work that carries none. **It never falls back to the default
  name**, which would read as "this was drawn with a different catalog"
- **57 nameplates covering 10 renamed pairs are corrected at startup** (the `catalog_id` column only).
  **⚠ `render_color_catalog_id` is left alone** — that id is not only a nameplate but **a seed for the
  color assignment** (`_WORK_COLOR_SEED_FIELDS`), so **rewriting it changes which colors are chosen
  even when `render_color_map` is byte-identical**. Measured across 200 seeds, all ten pairs disagreed
  on 38–70% of them. **The two columns therefore disagree on 57 rows, and the drawing is unchanged
  because `render_color_catalog_id` is the one that wins**
- **The path for new drawings did not move by a line** (`/api/paint`, `/api/compose`), and no color
  was pushed to the clients — neither web nor the CLI assembles colors and sends them
- **⚠ Perturbation P-2, the one the contract named, turned nothing red** — it edits a catalog's `map`,
  and **the values in `map` do not reach the drawing** (`_work_color_assignment` picks from the
  `palette:` entries; `map` is only the fallback for a band with no candidate). **The discrimination
  is established another way**: a work with a record holds still while its catalog is repainted, and
  the path with no work reference moves under the same repaint — a green pair in opposite directions.
  **P-1 showed the reverse** (cutting the wiring turned 7 red while the no-reference control stayed green)
- **Checks:** **server pytest 2,561 passed / 31 skipped** (**+33**, 0 red, 0 deleted), **cli 188**
  (+6), **web `test:unit` 123** (+6), ruff clean (server and cli), `npm run check` 0 errors,
  `lint:i18n` 0 errors, `check_docs.py` green, **frozen corpora byte-identical** (no deterministic
  layer was touched). **Thirteen perturbations** (the contract's seven plus six the implementation
  added). **One miss, P-2, for the reason above**

### v2.11.12 — The application executes its own log policy (Build 868, 2026-08-09)

**The settings screen stored the log policy (enabled / retention / interval / compression) in the
application DB but delegated execution to the host OS.** It did so by generating a systemd drop-in
and a logrotate snippet for an administrator to paste, and the drop-in said
`StandardOutput=journal+append:/var/log/inku/inku-api.log` (ledger I-167).

- **`journal+append:` is not a systemd output specifier.** systemd 249 logged
  `Failed to parse output specifier, ignoring` on every start, dropped the line and fell back to
  `journal`. **`/var/log/inku/*.log` had been 0 bytes since 2026-05-07**, and the 90-day retention
  that depended on those files had nothing to rotate
- **The container distribution has nowhere to paste either file** — no systemd, no logrotate — so a
  policy the platform executes can never be the same policy on both deployments
- **Logs now work the way DB backups already did.** The policy stays in the DB and the application
  writes, rotates, compresses and prunes the files itself
  (`server/src/inku_server/logging_setup.py`). The directory is **`INKU_LOG_DIR`**
  (`~/.local/share/inku/logs` by default, **`/data/logs`** in the image), which points at the
  `inku-data` volume so the files survive a restart
- **Every line still goes to stdout**, so `journalctl -u inku-api` and `docker logs` are unchanged.
  In the container distribution, `logging` in `compose.yaml` now caps what the daemon collects from
  stdout; it was uncapped
- **The two preview panes were removed from the settings screen** (systemd drop-in and logrotate).
  It shows the log directory and the files present instead. The `log_retention` API dropped
  `systemd_dropins`, `logrotate_config` and `services`, and carries `log_dir` and `files`
- **The startup banner asks the policy for its destination** as well; it used to print
  `log: journal + /var/log/inku/inku-api.log` as a constant, naming a file nothing was writing
- **The broken specifier was removed from the four systemd templates in `manual/`, and the logrotate
  template was retired** (both languages -- the published manual was handing out the same setting)

### v2.11.13 — The mark stays on its line (Build 869, 2026-08-09; render engine 28)

**Four rules move in one version, in answer to the author's request of 2026-08-09: trace the main line
exactly, and add the tool's tone just outside its width.** Every one of them is about what happens
where the tool meets the paper.

- **The wander is measured in stroke widths, not in the figure's representative size.** The amplitude
  is now **`AMPLITUDE_WIDTHS` (fine 0.35, medium 0.6, broad 2.0) times the stroke width**. It used to
  be 8% of the representative size at `medium`, so **a thin pencil drawing a large arc left its own
  mark by eleven widths**. **The 0.6 was chosen by the author from sheets drawn at 0.6 and 0.9**
  (2026-08-09). **The clamp at 0.40 of the representative size stays** as the safety valve for a
  figure smaller than its own mark. **Measured: on drawn arcs the drift over the stroke width lands
  between 0.595 and 0.600 across six tools, two thinnesses and four radii, and is flat in the
  radius** (engine 27 held it at 7.9-8.5% of a radius, which is 2.88 to 12.21 widths).
- **The material outline -- the tool's tone -- takes its offset from the performed ink rather than
  from the intended geometry, for every work and not only for `wild`.** The median distance from a
  decoration vertex to the ink band falls from **16.09 / 5.99 / 8.11 / 6.09 px (large arc, small arc,
  circle, square) to 3.21 / 2.26 / 3.07 / 2.80 px**. **The line was already on its ink at engine 27**
  (0.86 -> 3.20 px): the straight tool was the one that had been right, and the other figures caught up.
- **The fray is no longer a `stroke-dasharray`.** The stroke is drawn only where a contact field
  standing for the paper's tooth crosses a threshold. **How much of a stroke touches is still read per
  tool from the old dash table**, so a pen stays nearly continuous and a pencil keeps its gaps. **In a
  192-fragment sample sheet one pair of fragments shares a length, 2.6% land on a multiple of the
  sampling step, and there are no `stroke-dasharray` attributes left.**
- **Two rules fit the tone's weight to the tool**, in answer to the author's ruling that the square's
  decoration was too heavy: **a stratum is never wider than 0.33 of the tool's own mark** (the cap
  reads the **nominal** stroke, because paper tooth and powder do not get finer because the line was
  drawn finer) and **a stratum's centre is never inside the mark** (that floor reads the **actual**
  stroke, because where the tone sits is a question about the mark that was drawn). **The ink a
  decoration lays down falls by 25% for pencil, 12% for pen, 22% for crayon, 29% for chalk, 32% for
  brush_thin and 17% for brush_thick.** **Measured first: the decoration was already laying down less
  ink than at engine 27** (962 -> 803 px² on the square) -- **what read as heavy was the position, not
  the quantity**. **Pushing it further from the edge changed nothing** (673.1 against 672.9 px² on the
  square): **the width was what mattered, not the distance.**
- **The corpus moves on 454 of its 549 cases and holds 95** (`render-engine-28`). **The 95 are every
  case drawn with the five tools that carry no material outline** (rotring 22, drypoint 21,
  silverpoint 19, computer 17, burin 16). **The contract predicted 54**, which was the number of cases
  where the wander reaches the geometry; **that every drawing by the six tools with a material outline
  would move was not counted until the premise changed.**
- **Six checks that replayed an older version's frozen record were re-seated.** All of them reached the
  older version by withholding a layer that had landed since, which engine 28 makes impossible in
  principle. **Where the claim was about a feature, it was rewritten as on-versus-off within one
  version** (fade, angle, composition seed, per-member size). **Two of the six are a loss, not a
  replacement:** `test_surface_stroke` lost its attribution observation point, and
  `test_anchor_authority` went from holding **447 cases to holding 92** (the five tools with no
  material outline). **Both say so in the code, and both are in the ledger.**
- **Android gains a `render-engine-28/` reference fixture directory** (64 files). **The port still
  resolves 27 through `CompatibilityConstants.renderEngineVersion`, so a directory was added and
  nothing the port compares against moved** (catching up is its own contract).
- **Checks:** **on the merged tree, server pytest 2,624 passed / 31 skipped / 0 failed**
  (**+15 test functions against the branch point `dc46dd1a`, 9 turned over, 0 deleted**; one of the 15
  was added in acceptance). **On the branch the count went 2,559 -> 2,598 (+39)**, measured by the
  implementation session. **cli 188 passed**, ruff clean, **frozen corpora byte-identical**, **eight
  perturbations with none missed**. **One thing was repaired during acceptance:** one frozen case could
  no longer be reproduced by the code that shipped (`C-fill-circle-chalk-extra_fine` held 0.346500 from
  when the cap read the actual stroke width, while the code now reads the nominal one and draws
  0.990000). **It was re-baked; the other 453 that move and the 95 that hold did not shift by a byte.**
- **One check was added during acceptance:** it reads the drift off a **drawn** arc for four tools at
  two thinnesses and holds it to 0.6 of that tool's own width. Nothing had put the constant and a
  picture inside one assertion: **the unit test compared the function against the constant, and the two
  invariance checks would pass for an implementation that returned a fixed amplitude** (full marks 8;
  eight red when the yardstick goes back to the representative size, four when `thinness` stops
  reaching the width).

### Android `2.1.4-android.21` — the interface speaks the reader's language (android Build 148106, 2026-08-09)

**Android alone was pinned to Japanese.** The wording of the interface now comes from a language pack, the
saijiki vocabulary comes from the server's generator, and the reader picks a language in the settings
(default `ja`; ledger [I-065]). **`APP_VERSION` and `web/BUILD_NUMBER` do not move.**

- **The saijiki went from a hand copy to a generated file** — `server/scripts/gen_saijiki_kt.py` bakes
  `SaijikiGenerated.kt` out of `saijiki.py`, in the same shape as web's `gen_saijiki_ts.py`. **The vocabulary
  the screen holds went from 9 categories and 62 words (Japanese only) to 10 categories and 73 words in
  both languages.**
- **⚠ Why it had drifted is now known.** Android synchronised its "touch" category to ten words on
  2026-07-26, **and a test asserting those exact ten words was written the same week.** **The server put
  silverpoint back into the vocabulary the next day**, and **because the test held the previous day's value
  as its expectation, it stayed green while guarding the drift.** That test now reads the Stage 1 prompt's
  enumeration instead, silverpoint included.
- **The interface reads its wording from a pack** — `InkuStrings` as an interface plus `InkuStringsJa` and
  `InkuStringsEn`, **254 keys each**. No `res/values-en/`: that would follow the device locale. **Errors are
  translated where they are shown, not where they are thrown** (`InkuFailure`); thirteen call sites had been
  putting `error.message` straight on screen.
- **The new lint counts 446 hardcoded strings at the branch point and 0 after** (452 Japanese literals less
  6 named exclusions).
- **Choosing a language changes three things at once** — the wording, the saijiki vocabulary, and the
  language a work is written in. The stored key is `ui_lang`, the same name the server uses, and an unknown
  stored value falls back to `ja` rather than raising.
- **⚠ Drawing behaviour changed.** Android never passed `instructionLang`, so it never entered the `auto`
  branch and **drew even an English description with the Japanese Stage 1 prompt.** Web sends the constant
  `'auto'` every time and the server uses `ui_lang` as the fallback for `auto`. **All five drawing paths now
  send `AUTO` and `uiLang` explicitly**, which is the "same judgment" the conventions require (§2-4). **An
  English description is now read as English even while the interface is in Japanese** (author ruling,
  2026-08-09).
- **⚠ One of the sixteen files the contract forbade was changed, by two lines** (author ruling, 2026-08-09).
  `LocalFallbackPipeline.kt` holds both calls to `resolveWithUiLang` and was the only place the wiring could
  land. **The change passes an argument and nothing else: the Japanese literals across those sixteen files
  stand at 1,386, unchanged**, counted at the branch point and at the branch tip by the accepting session.
- **The saijiki had nine colours for ten categories**, and `index % size` made the tenth collide with the
  first instead of failing. A tenth colour was added and `android/design/preview/color.html` was rebaked.
- **Checks:** **Android JVM 263 passed, 0 red, 0 skipped (49 classes, up 20 from 243)**, **96 of 96
  instrumentation tests green on a physical Pixel 9** (measured on the branch; **`app/src/main` and
  `app/src/androidTest` in the merged tree hash identically to the branch**), **server pytest 2,626 passed /
  31 skipped**, ruff clean. **The implementation ran ten perturbations** (the nine predicted plus one:
  **P-5, deleting a key from the English pack, fails to compile before any test runs, so the observation
  point moved to "the English pack answers in Japanese"**) **and the accepting session added one more** —
  **stage 3 ① had no perturbation aimed at it**; pinning the pack to a constant turns exactly
  `testTheSettingsScreenOffersTheChoiceAndTheTreeIsProvided` red.
- **⚠ One terminology conflict is left open.** The glossary and Android call a lineage origin `Origin`;
  **web prints `Root`** (`web/src/lib/derivation.ts`). **Filed in the ledger, to be fixed in a week that
  touches web.**

### v2.11.14 — A redraw reads the description too (Build 870, 2026-08-09)

**Web had been sending the description (the DDL) with every redraw, and the server had been throwing it away.**
`/api/render-score` sat on the side that does **not** hand the DDL to coerce, so the same work was repaired
one way when it was first drawn and another way when it was redrawn.
**Site 4 is now wired, and the judgment matches `/api/paint`** (author ruling, 2026-08-09, option A-1).

- **⚠ This changes pictures.** On the two refine paths — changing the touch by words, and redrawing with
  another catalog — **a count or a relation stated in the description now reaches the picture**. 29 of the
  40 golden cases move and 9 change the number of figures.
- **The production footprint was measured before the ruling was asked for** (2,817 works, 218 lineage edges):
  **20 of the 36 `catalog_change` edges have a DDL on the child work**, and **all 22 saved `touch_change`
  children carry none**. **Around 20 works are in reach.**
- **An empty DDL walks the same path as no DDL at all** (web sends `ddl ?? ''`). The accepting session called
  the API directly: **omitting it and sending `""` return an identical score, svg and render_hash.**
- **`inku-cli render-score` now talks to the endpoint it is named after** (author ruling B-1). It had been
  posting to `/api/render-svg`, so the subcommand and its destination disagreed.
- **Two flags were added** — `--ddl-text` and `--ddl-file` (`-` reads stdin); naming both is an error.
  **The CLI can now walk coerce's DDL branch without going through an LLM**, which is what the conventions
  ask for when they say feature tests run through `inku-cli`.
- **`RenderScoreRequest` gained `svg_profile`** so the moved CLI keeps its existing `--svg-profile`. **The
  default is `display`, which is the profile `/api/render-score` already drew with**, so neither web path moves.
- **⚠ Three keys in the CLI's artifact move**, as a consequence of the new destination: **`score` goes from
  what was sent to what coerce returned**, and **`render_hash` / `render_hash_short` go from the CLI's own
  rh2 to the server's rh3**. **With the seed pinned, the `svg` is byte-identical** (measured in acceptance).
- **⚠ Without `--render-seed`, `render_seed` moves too** — from `null` to the seed the picture was actually
  drawn with. **The accepting session found this fourth difference; the completion report listed three.**
  An artifact that names its own seed is an improvement, but the value does change.
- **⚠ Two functions in the CLI are now unreachable** — `_server_render_versions` and `_render_hash_for_score`
  lost their only caller when the server started returning the versions and the hash. **Filed in the ledger.**
- **Checks:** **server 2,626 → 2,631 passed / 31 skipped**, **cli 188 → 195 passed** (nothing removed), ruff
  clean on both, and **the frozen corpora and `coerce_golden.json` do not move by a byte** — the positive form
  of "coerce itself was not touched". **All seven perturbations were re-applied by the accepting session.**

### v2.11.15 — The cycle does not invent an order (Build 871, 2026-08-09, ddl-engine 8, 9)

**A `color_cycle` hands one color to each member in turn. It has no head and no ranking** — and yet coerce
had been writing two kinds of order into it ([I-060]).

- **① The same color was landing in it twice.** `_with_color_cycle_delivery` inserted the instruction's own
  color at the front **without looking**, so a color already in the cycle **took twice the members**. Nobody
  asked for that weighting, and **its size depended on how long the cycle happened to be**. **207 of the
  3,391 production cycles (6.1%), across 204 works (7.4%), had this shape.**
- **② New colors were being dropped entirely.** `_color_repair_order` filtered the requested colors through
  **a six-word table that predates yellow, orange and purple**, so **naming one old color threw all the new
  ones away** (`{red, yellow}` → `[red]`). The table is now **a known order for determinism rather than a
  ranking**, and **colors it does not name follow it instead of falling out**.
- **③ A delivered color could not reach a primary stroke on the same pass** (ddl-engine 9, an author ruling
  that widened the contract). **The promotion can only see colors a cycle already carries**, yet it ran
  **before** the repair that puts them there. Production makes one pass, so **running the same input through
  coerce twice gave two different scores**. The two now run **repair, then promote**.
- **The promotion no longer takes a stroke that already carries a color the description asked for.** An
  instruction has a single primary stroke, so promoting onto it a second time undoes the first — **across
  passes, red and blue traded the same stroke back and forth forever**.
- **The crescent guard now looks at the cycle's green as well.** It stopped firing the moment an earlier
  promotion rewrote `color`, and **the green stayed in the cycle for the renderer to draw**.
- **`ddl_engine_version` 7 → 9.** `ddl-engine-8/` and `ddl-engine-9/` were baked. **From 8 to 9, 8 of the 21
  b_coerce cases and 4 golden cases move, and the 13 a_expand cases do not move by a byte.** **Non-idempotent
  cases go from 5 to 3** (the remaining three move coordinates and `weight`, not color, by another mechanism).
- **⚠ Raising the version turns six places red** that had written down "7" (`test_ddl_reference.py` 1,
  `test_api.py` 4, and one Android reference fixture). **The contract did not predict this.**
- **⚠ Android's `ReferenceCorpus.kt` still says `7`** and is now two versions behind the server. **It does not
  go red, because the reference fixtures live in per-version directories**; catching up belongs to the Android track.
- **Checks:** **server 2,631 → 2,658 passed / 31 skipped** (nothing removed, 27 added), **cli 195 passed**
  (unchanged), **Android JVM 263 green**, ruff clean on server and cli, and **the frozen corpora are
  byte-identical on darwin**. **Ten perturbations were applied to ten acceptance tests.** **⚠ Removing the
  promotion guard does not turn the idempotence tests red** — only the two `test_t10_*` tests hold it, so
  **deleting those two leaves the guard with no observation point.**

### v2.11.16 — The artifact names the layer that drew it (Build 872, 2026-08-09)

**The artifact JSON `inku-cli` writes named only the renderer's version, out of all the layers that drew the
picture.** Since `render-score` gained `--ddl-text` / `--ddl-file` in v2.11.14, **the pictures on that route
depend on the version of the DDL layer**, yet the artifact carried only `render_engine_version`, so **the JSON
alone could not say which coerce drew it** ([I-182]).

- **Artifacts now record `ddl_version` and `ddl_engine_version`.** There are five places that write them out —
  **the `render-score` artifact, the paint result built from a compose response, the history payload, and the two
  history-export summaries** — and all five carry the keys. The values are copied from the server response as they
  are (the server already returned them in all three responses; the CLI was throwing them away).
- **Older works keep the keys with a `null` value.** `ddl_engine_version` is a nullable column in `history`, and
  the server puts it in the response only when it has a value, so **the history export reads it with `item.get(...)`
  and does not fall over on rows that lack the key**.
- **⚠ `render-score` now stops against an older server.** Both keys were added to the `required` tuple in
  `command_render_score`, so **a server that does not return them raises `CliError` instead of writing `null`**.
  This matches the existing judgement for `render_engine_version`: writing no artifact beats writing one that names
  no version.
- **Tools that had lost their callers left the product code** ([I-180]) — the three definitions
  `_SERVER_RENDER_VERSION_KEYS`, `_server_render_versions` and `_render_hash_for_score`, along with
  **`_canonical_json` and `import hashlib`, which they took with them**. This finishes the move made in v2.11.14,
  where asking for versions and computing the hash became the server's job.
- **The check that shows which keys moved stays.** The rh2 computation **moved into a helper on the test side**, so
  `test_render_score_without_ddl_changes_only_server_owned_output_keys` **still shows that the old rh2 and the
  server's rh3 differ**. Only the one test that examined the deleted function itself was removed.
- **The Japanese and English manuals gained one sentence each** under "Input and output", saying that artifacts
  record the versions of the DDL layer. No flag was added.
- **Checks:** **cli 195 → 197 passed** (one removed, three added), **server 2,658 passed / 31 skipped, unchanged**
  (**the server did not move by a byte**; neither did `web`, `shared`, `android` or `docs`), ruff clean on server and
  cli, and `check_docs.py` consistent. **Six acceptance tests, seven perturbations.**
- **The implementation came from Codex (a different model), so every test and perturbation was re-run on the
  accepting side** — **all seven perturbations turned red as predicted, none missed**. **⚠ P-5 (putting the history
  export back to the `item[...]` subscript) also turns the existing
  `test_history_export_writes_contact_sheet_and_evaluation_json` red**, not only the new acceptance test; the
  implementation report measured a narrowed selection and so recorded one.
- **Acceptance drove `inku-cli` against an isolated API.** Both runs, with and without `--ddl-file`, wrote
  **`ddl_version` 3 and `ddl_engine_version` 9** into the artifact, matching `/api/info`. **Artifacts written by the
  previous CLI on the same route carry only three version keys** (`render_build_number`, `render_engine_id`,
  `render_engine_version`).

### 2026-08-09 — The specification's list caught up with the keys the responses already return (**no version bump**, documents only)

**The list under "render JSON records the concrete render context" in `SPEC.md` did not name `ddl_version` or
`ddl_engine_version`.** The server **always puts both** in `_base_render_metadata` (`api_core/rendering.py`), across all
three responses — compose, paint and render-score — and only the specification's list was missing them, from before
v2.11.16. **Both keys were added, along with one sentence in each language** saying that they name the DDL layer that
decided the picture, and that among saved works only rows written before those versions were recorded lack them (the two
`history` columns are nullable, and `db.py` puts them in the response only when they have a value). **No code changed.**

### v2.11.17 — The same grain is counted on every machine (Build 873, 2026-08-09, render engine 29)

**This one thing is why main's CI was red, and it was not a regression** (ledger I-178). **Engine 28's frozen
corpus was baked on a Mac, and rebaking it on Linux produced different bytes for 6 of the 549 cases.** The
generator's identity guard exits 1, so every push added another red run.

- **All six were pencil, and only in the `material-outline stratum-1` polyline**; the contour itself agreed on
  both platforms. **There were two kinds of split** — **three that differ in structure** (down to the number of
  points and fragments) and **three of identical file length whose coordinates differ**.
- **The fix belongs on the counting side.** The **segment length, total arc length, sampling step, grain width
  and fragment length** the contact decision reads now sit on **the same six-decimal pixel lattice the SVG
  writes** (`CONTACT_LENGTH_QUANTUM = 6`). **Rounding the coordinates would not have been enough**: one ULP that
  adds a sample **jumps the threshold, which is a quantile of the samples themselves**, and the crossing position
  and the `length < 0.6` cutoff move with it. The three cases whose point counts move would have stayed broken.
- **`render_engine_version` 28 to 29, and `render-engine-29/` was baked** (`render-engine-28/` was not touched by
  a byte). **454 of the 549 cases move and 95 do not.** **The 454 that moved are exactly the 454 that carry a
  `material-outline` under engine 28** (pen 235, pencil 83, brush_thick 71, crayon 31, chalk 18, brush_thin 16).
  **The 95 that did not are the five tools with no material outline** — the same 95 as under engine 28.
- **The platform-stability gate now looks at the current exposure.** Its subject was group G's 50 cases, and
  **none of the six splits were in it**. It now **derives the exposure from rendered output** (draw all 549 and
  count the 454 that emit a `material-outline`) and **draws a 27-case sample twice** (15 arrangement cases, the 6
  that split under engine 28, and one representative per tool). **A guard reads the gate's own source** and goes
  red if the exposure check returns to a hand-written count.
- **The Android reference fixtures for `render-engine-29/` were baked** (64 files). **The server-side F-1 check
  requires the current version's directory, and no existing directory moved.** **The Kotlin side's catch-up stays
  with I-177.**
- **Checks:** **server 2,658 to 2,661 passed / 31 skipped** (two removed, five added), **ruff clean**,
  **`check_frozen_corpora.py` byte-identical on darwin**, **Android JVM 263 tests, no failures**, and
  `check_docs.py` consistent.
- **The implementation came from Codex (a different model), so every test and perturbation was re-run on the
  accepting side** — **all six perturbations turned red as predicted**. **⚠ Three of them turned more red than
  reported** (the implementation ran only part of the gate): **P-2 fails 3 tests**, not only the direct one,
  **P-3 fails 2**, and **P-5 fails 2**.
- **⚠ The report's "26 cases" in the main sample is 27** — one representative is taken for each of the six tools,
  and pencil's (`A-pencil-arc`) is not among the six that split.
- **Acceptance reproduced the Linux rebake** — `server` and `shared` were rsynced to `/tmp/opus5-i178/` on
  pentala and the generator run there, with **zero differing entries in `render-engine-29/`** (the deployment
  tree was not touched).

### v2.11.18 — A description that names one color is drawn in one color (Build 874, 2026-08-10, ddl-engine 10)

**[I-173] stage A.** `arrangement.color_cycle` is a pure `cycle[i % len(cycle)]`, so **n colors always
split the members n ways. A description that names one color still gives that color to half the
members when the cycle holds two.** This is not the work of giving a description somewhere to state a
distribution (that is stage B); it removes **a distribution nobody asked for**.

- **A branch was added at coerce's exit** (`without_unrequested_color_cycle`). When the DDL, minus its
  background clauses, **names exactly one abstract color**, carries **no polychrome phrase**, and the
  instruction's cycle is **two or more entries holding that color and another**, the cycle **folds to
  that one color, which is also set as `color`**. **A cycle that never carries the named color is left
  alone** — that is a failure to deliver, not dilution, and delivery is another layer's work.
- **There are two exits, so one shared function serves both** (`coerce/__init__.py:88`, the
  `INKU_COERCE_DISABLE` path, and `:201`, the main one). **No flag says it is fine to hand out a color
  the description never named**, so this rule holds on that exit for the same reason the hard ceiling does.
- **⚠ The cycle keeps one entry rather than being emptied.** The contract as issued said to empty it
  because "the picture is the same", and **that was not true**. `_apply_color_cycle` returns early on
  `if not cycle`, **skipping the `color_hint` rebuild that follows**. Stored Scores carry old machine
  notes in `color_hint` (186 of 202 measured), so **emptying the cycle lets a color word inside the note
  override `color` and the named color disappears** (four works in the area measurement; one went from
  49.7% to 0.0%). **One entry is not a cycle, and `len(cycle) <= 1` reads that off the Score.**
- **The Stage 2 prompts, Japanese and English, gained the rule that a description naming one color gets
  no cycle** (the source is upstream: Stage 2 writes 62.9% of the dilution). **No gate sits here** —
  the output is not deterministic, so only "it did not fall over" is observable, **which is why the
  mechanism sits at coerce's exit instead.**
- **`ddl_engine_version` 9 to 10, and `ddl-engine-10/` was frozen** (34 cases, A 13 / B 21; no byte of
  `ddl-engine-9/` moved). **⚠ 21 cases differ from the previous version, but only 8 moved their `score`;
  the other 13 gained the 29th branch's key in `branch_report`.** The golden file has the same shape:
  **40 cases differ, 13 moved their `score`.**
- **The two Stage 2 prompts the Kotlin port duplicates were copied over wholesale from the server**
  (`WebDdlSpec.kt`). **Once the Stage 2 wording moved, `PromptFingerprintTest` was bound to go red** —
  the fingerprints in `prompts.json` are generated, and a server-side check requires them to match the
  current server, so **there is no route back to the old fingerprints**.
  **`android/VERSION` 2.1.4-android.21 to .22** (a namespace separate from the web version).
- **Checks:** **server 2,661 to 2,679 passed / 31 skipped** (18 added), **ruff clean** for server and cli,
  **cli 197 passed**, **`check_frozen_corpora.py` byte-identical on darwin**, **Android JVM 263 tests,
  no failures**, and `check_docs.py` consistent.
- **⚠ Acceptance found one Android regression.** The completion report had not run Android, and
  **`PromptFingerprintTest` was red on the merged tree** (44,193 against 44,589). **A contract that says
  not to touch `android/` does not stop the Kotlin duplicate from falling behind when the server's
  wording moves.**
- **⚠ Three perturbations hit nothing and three gates were vacuous, which the implementation found and
  fixed itself**: T-3's sample named no color at all (condition 1 stopped it first, so condition 2 was
  never evaluated), T-5's write always agreed with the existing path, and T-6's sample happened to agree
  with subtracting `background`.

### v2.11.19 — The app opens without a ceremony (Build 875, 2026-08-10, single-user mode)

- **A server started with `INKU_SINGLE_USER` settles on one person and signs them in by itself.**
  Bring up Compose, open the browser, and you can write. **Not one line of the multi-user machinery was
  removed**: a branch was added only where `_session_token` used to raise 401, and **neither its return
  type nor the dependency tree changed**. **All 82 routes keep the guards they had.**
- **The default now lives in two places.** **The code defaults to off**, so a deployment that merely
  takes the new version does not quietly lose its authentication, and **the distribution defaults to on**
  (`INKU_SINGLE_USER=1` in `compose.yaml`). The required check on `INKU_BOOTSTRAP_ADMIN_PASSWORD` was
  relaxed to optional, because **single-user mode needs no bootstrap administrator**.
  **⚠ Compose interpolation cannot say "required only when single-user mode is off", so an operator who
  turns it off must set a password themselves**; `deploy/.env.example` states that condition.
- **The single user is resolved once, as the oldest `admin`, and the result is pinned in `app_settings`.**
  **No column is added to the account row** — `app_settings` is keyed, so structurally there can be only
  one single user. **The pin names an id, not a name**, so **renaming does not move it**, and **because
  the pin is a row in the DB it leaves with a backup and comes back with one.** On a database with no
  `admin` at all, single-user mode does not engage and requests stay 401.
- **`/api/info` reports whether the mode is on**, as one more environment-derived flag alongside
  `developer_mode`. **The API surface counts did not move — endpoints, operations, and schemas are all
  still 82.** What moved is the digest and the contents of that one response, and what watches it is a
  set-difference assertion rather than a count.
- **The web UI hides the one control that would only bounce back — signing out.**
  **Changing the password and managing users stay visible**: with the distribution default the account's
  password is a value nobody knows, so that is the only way back from single-user operation to ordinary
  operation. The settings panel states this in one line, in both languages. **The sign-in screen was not
  touched at all** — once auto sign-in works, `/api/auth/me` answers 200 and the screen never appears.
- **`inku-cli` now sends a request even without a token and falls back to the old message only when the
  server answers 401.** It used to stop on the client side, so **the request never reached a single-user
  server** — and only the server knows whether the mode is on. Against a server that is not in
  single-user mode, the wording is unchanged.
- **Checks:** **server 2,704 passed / 31 skipped** (14 added), **cli 199 passed** (2 added),
  **web `test:unit` 125** (2 added), **ruff clean** for server and cli,
  **`npm run check` 0 errors / 2 warnings** (the two pre-existing a11y warnings), and
  **`lint:i18n` 0 warnings / 0 errors**. **Eleven perturbations turned 24 assertions red, and no gate
  was left without one.**
- **⚠ One ruling made mid-flight was wrong, and the implementation overturned it by measuring.**
  "The CLI needs no follow-up" was drawn from `/api/info` being a public route, and it did not hold for
  the commands that require authentication.
- **⚠ Two of the issuer's estimates missed.** The contract expected four documents in two languages to
  become false; **the measured figure is eight passages** (the two that describe Compose's required check
  and two on the specification side were missing). The gate count also missed: 13 from the issuer and 16
  once the mid-flight rulings were folded in, against **18 measured**.

### v2.11.20 — the number the description states is the number drawn (Build 876, 2026-08-10, ddl-engine 11)

- **A count of 1 to 11 stated in plain words now reaches the group its clause describes.**
  Until now only the "**only** three" / "three **alone**" path held a count; **a number written the
  ordinary way — "three black pen circles in a row" — was overwritten by downstream guesswork.**
- **It is a new branch of its own, `with_stated_count_fidelity`**, deliberately not folded into the
  existing "only" path: **folding them together would make "which one corrected this work" unreadable
  in `branch_report` forever.** Its note carries different wording as well, so attribution stays countable.
- **A clause is paired with a group in two steps, and an ambiguous pairing is left alone.**
  First the `(figure, color, weight)` triple built from the clause, when exactly one group carries it;
  otherwise the same figure, when exactly one group carries that; **otherwise nothing happens.**
  **Forcing the ambiguous ones would raise the number, but only by breaking some other group's count**
  (measured under perturbation).
- **Cloud forms are now read as a figure.** `_primitive_from_clause` had no word for them, so they fell
  through to the default `line` — **12 of the 15 cloud-form clauses in production.** The clause-built
  shell gained the cloud form's geometry (centre and size) too: **the renderer draws a cloud form only
  when both are present**, so reading it correctly without that would have turned "the wrong shape"
  into "no shape at all".
- **Measured on 214 cases frozen from production: 144 are now correct**, against 0 before the change.
  **The 70 that did not move are refusals, not misses** — 47 have more than one group answering to the
  clause, 20 would leave some other stated number without an answer, and in 3 an earlier clause has
  already answered that group.
- **Nothing was touched above 11, nor the crowd representation or the total budget** (which of the two
  takes precedence has not been ruled on yet).
- **⚠ This is 14 short of the contract's 158, for one reason: the ceiling was measured on stored Scores,
  while the branch runs at the exit of coerce.** Branches in between move colour, material and figure,
  so a pairing that was unique when the work was saved is not unique when the correction runs.
  **The ceiling where the branch actually runs is 147, and 144 of those are reached.**
- **Three of the eleven perturbations missed, and all three led to a fix in the gate or the code** —
  **(1) the claim "it sits after the total budget" cannot be measured** (the budget only ever reduces a
  count, and 1 to 11 is never what it reduces; placing the branch before and after it beside a group of
  900 gave byte-identical output), so the claim was rewritten to what was measured; **(2) the "leave a
  group that already satisfies the request alone" guard works, but nothing detected it** — removing it
  drops the 214 from 144 to 132 while every test stays green — so a case with that discriminating power
  was added; **(3) the "one group answers one clause" guard was unreachable** and was removed: once an
  earlier clause answers a group, that group is already the only answer to its number and never reaches
  a later clause.
- **The reference corpus `ddl-engine-11/` (A 13 / B 21) was baked.** No Score moved; `branch_report`
  simply gained a thirtieth key. `coerce_golden.json` moved in all 40 cases because a branch was added.
  **The Android reference fixture was baked in the same round** — a new version directory, with not one
  byte changed in the existing ones.
- **Checks:** **server 2,730 passed / 31 skipped** (26 new), **cli 199 passed**, **Android JVM 263**
  (debug, 0 failures), **ruff clean** (server and cli), **`npm run check` 0 errors / 2 warnings**
  (the two pre-existing a11y ones), **frozen corpora byte-identical on darwin**, **`check_docs.py` consistent**.
- **⚠ One fact remains:** `_primitive_from_clause` reads a figure word from anywhere in the clause, so
  the "point" inside "focal point" reads as a figure. **This change works around it with a guard; the
  misreading itself is untouched.**

### v2.12.0 — What a member may do is decided by the group (Build 877, 2026-08-10, permission groups)

- **The three-valued `user_accounts.role` flag is gone from every decision.** What a member may do
  is decided by membership in **three permission groups: `admins`, `leaders`, and `users`**.
  **One member may hold several of them** (many-to-many). **There is a single entry point for the
  test, `has_permission_group`**, called from `deps.py`, `users.py`, and `feedback.py` alike.
  **The branch is not scattered.**
- **The `role` column was not dropped.** After the migration it is written as a **mirror the machine
  derives from the memberships** (`admin` if `admins` is held, `group_lead` if `leaders` is,
  otherwise `user`). **The reason is backup and restore** — dropping the column would mean a database
  taken after this version fails to open on a build from before it. **Nowhere does a person write the
  mirror; the same hand that writes the memberships updates it.**
  **That no decision reads the mirror is measured by behaviour rather than by reading the source** —
  an account whose column claims `admin` while it holds only `users` gets 403 on the admin routes
  and 403 on the user-management routes.
- **The startup migration is one-to-one and idempotent.** `admin`→`admins`, `group_lead`→`leaders`,
  `user`→`users`. **`admin` is not read as "an administrator is also a leader"** — reading it that way
  would leave nothing able to tell an account the migration widened from one an administrator widened
  on purpose.
- **The organisation group (`user_accounts.group_id`) stays as a separate thing**, one per member.
  **Permission groups and organisation groups are judged independently** — two members of the same
  `circle_a` are treated differently: the one holding `leaders` reaches user management, the one
  holding only `users` does not. Moving between organisation groups moves no permission.
- **Which accounts a leader may touch is now decided by memberships rather than by the mirror.**
  The old code narrowed on `role == "user"`, so **an account whose mirror still said `user` could be
  mistaken for one**. It now narrows on "holds neither `admins` nor `leaders`".
- **Three API schemas changed their keys** — `role` and `role_label` left `UserAccountItem`,
  `UserAccountCreateBody`, and `UserAccountUpdateBody`, and `permission_groups` and
  `permission_group_labels` arrived. **Not one route was added** (82 total, 6 public, unchanged).
  **The API-surface counts stay at 82 endpoints / 82 operations / 82 schemas; only the digest moved**
  (`fc1378ba…` → `cd4148a7…`). **A count that does not move is no evidence that nothing was lost**, so
  a gate names the field-level set difference across the three schemas and asserts that the hash of
  the other 79 is unchanged.
- **The CLI flag changed** — `user create --role {user,group_lead,admin}` became
  **`--permission-group {users,leaders,admins}` (repeatable)**, and **`--role` is no longer accepted.**
  `me` and `user list` print the response whole, so the printing followed with no added code.
- **The web UI moved the permission-group choice from one `<select>` to three checkboxes** (memberships
  are plural; an empty selection cannot be made). Tab visibility was collected into
  `$lib/permissionGroups.ts` so **the gate can execute the rule rather than match it with a regex**.
- **Checks:** **server 2,747 passed / 31 skipped** (17 new on the branch), **cli 201 passed** (2 new),
  **web `test:unit` 127** (2 new), **ruff clean** (server and cli), **`npm run check` 0 errors /
  2 warnings** (the two pre-existing a11y ones), **`lint:i18n` 0 warnings / 0 errors**,
  **frozen corpora byte-identical on darwin**, **`check_docs.py` consistent**.
- **Twelve perturbations turned 18 tests red; the contract predicted 21.** **The three missing are not
  a hole but a concentration of discriminating power** — the reachability tests (where `admins`,
  `leaders`, and `users` each get through) build their subjects with `add_user`, the path that grants
  a permission during operation, not through the migration. Breaking the migration's mapping therefore
  leaves reachability untouched, and only the test that reads the mapping one-to-one goes red.
- **⚠ The idempotence test as first written went red for none of the failures it named** — inserting a
  duplicate membership is refused by the `UniqueConstraint`, so **the run died in collection before the
  test executed**. It was extended to measure **the half the constraint cannot catch**: a migration that
  re-derives every account from the mirror, which loses one membership from any account holding both
  `admins` and `leaders`, because the mirror can only name the stronger.
- **⚠ The completion report's list of documents made false by this change missed two places** — it was
  drawn by searching for the value `group_lead`, and **two specification passages (one ja/en pair) that
  speak only of the `admin` role** were not in that net. **A net woven from a word does not catch a
  falsehood that avoids the word.**

### v2.12.1 — The stated number holds beyond what the eye can count (Build 878, 2026-08-11, ddl-engine 12)

- **The band in which a count written in plain words takes effect was widened from 1–11 to the literal
  threshold** (239 by default). **The boundary was not given a second name** — the band comes from
  `limits.literal_count_threshold - 1`. **Written as a separate constant, 239 could move on one side
  and nobody would notice.** **At or above the threshold, crowd representation governs and this branch
  touches nothing.**
- **When the forced count would exceed the per-instruction budget (240) or the whole-work budget (400),
  it is not forced rather than trimmed.** **This branch runs after both budgets, so nothing would
  remove the excess**, and a trimmed count puts **neither the number stated nor the represented one**
  on the sheet. **Where the number cannot be reached, leaving it alone is the honest answer.**
- **Measured over 1,346 works frozen from production**: of the **309 works and 341 counts** that state
  a number in 12–239 and miss it, **203 became true** (4 before this change). **Works the branch fired
  in went from 30 to 197**; marks per work moved from p50 **15 to 36** and p90 **131 to 230**; **works
  over the 400-mark ceiling stayed at 0**.
- **⚠ The budget guard fires once in production; the contract's estimate of "none" was an artefact of
  where it measured.** The estimate counted the total **after the exit ceiling had already cut it**,
  and a cut total is always at or below 400. **Before the cut it was 419.** In that work **the branch
  fired, no stated number came true, and other groups were cut as collateral by the ceiling.** The
  guard stops that wasted firing along with the overflow.
- **The counts still out of reach fail on pairing, not on the band** (ambiguous, already answered by an
  earlier clause, or the clause cannot name a group). **That is the previous contract's ruling and it
  was not touched.**
- **Two cases through which this change actually passes were added to the reference corpus** (synthetic;
  no production description is copied) — one stating a count in 12–239 that Stage 2 missed, and one
  where forcing it would cross 400 marks. **None of the 21 existing cases move when the band is lifted,
  so rebaking alone would have recorded nothing about this change.** `ddl-engine-12/` holds **36 cases
  (A 13 / B 23)** and `changed_from_previous` names **only the two that were added**.
- **Five of the 41 golden cases moved** (`H-01`, `H-07`, `H-10`, `H-13`, `H-18`) and **`branch_report`
  still has 30 keys** (no branch was added) — **exactly what the contract predicted.**
- **Checks:** **server 2,769 passed / 31 skipped** (22 new on the branch), **cli 201 passed**,
  **`npm run check` 0 errors / 2 warnings** (the two pre-existing a11y ones), **`test:unit` 127**,
  **ruff clean** (server and cli), **frozen corpora byte-identical on darwin**, **`check_docs.py`
  consistent**, **Android JVM 263 / 0 failed** (`composer.py` was untouched, so the prompt-fingerprint
  test is green too). **The band's own tests went from 25 to 46** (14 to 19 by `def`). **All eight
  perturbations landed; none missed.**
- **⚠ One perturbation did miss at first, and it exposed a defect in a gate** — widening the band past
  the threshold failed to redden the test that watches "240 and above does not move". That test used
  300 and 500, **both of which exceed the per-instruction budget, so the guard above refused them
  regardless of the band** — **the test was not measuring the band at all.** **240 was added.** It sits
  exactly at the per-instruction budget, so the guard does not refuse it and **only the band's edge can.**
- **⚠ Raising the layer version turned seven tests red that the contract never named** (four asserting
  `ddl_engine_version` literally, two Android reference fixtures, one counting corpus cases). **None
  were defects in this change; all were version follow-through.** Rebaking the Android fixture moved
  **only the two files in the new version's directory** — no earlier version, and none of the five
  files the engine does not govern, moved a byte.

### v2.12.2 — A work carries its own guest list (Build 879, 2026-08-11, sharing and visibility)

- **A work can now be shared one at a time, with a chosen recipient.** What is stored is
  **one row per (work, recipient kind, recipient)**, so **the same person may hold different
  permissions on different works** (measured: granting one work `read` and another `write` to the
  same member split their starring into a 404 and a 200). The ACL **holds ids and not a single
  name**, so **renaming a member or an organisation carries the sharing with it** (measured: a
  rename does not move a byte of the row). **⚠ Deleting an account and recreating it under the
  same name does not restore anything** — the id changes, and deletion clears the rows.
- **Every decision about who may see what was routed through one visibility predicate**
  (behaviour unchanged). **55 sites moved** (49 ORM, 6 raw SQL). **Two of them are the full-text
  search path**, where a leak shows up not as "too much is visible" but as **"it goes missing when
  you search"** — a perturbation in the "now it is visible" direction cannot catch that, so it has
  its own test.
- **The permission group decides the default scope.** `admins` see everything, `leaders` their own
  organisation, `users` their own works — **plus whatever has been shared with them.**
  **⚠ Existing accounts holding `leaders` can see their organisation's works from the moment of the
  upgrade.** For everyone else **nothing changes until somebody shares something.**
- **A lineage may cross owners.** Any readable work of another member can be a parent, and the root
  is inherited, so **one group spans two people and the number of visible nodes differs per viewer.**
  **A node that cannot be read is rendered as a card with its content withheld** — and `deleted` is
  **told apart from `not_permitted` in words**. **Both draw as the same empty dashed card, so without
  the label a viewer cannot tell "gone for good" from "ask its owner".**
  **⚠ An edge follows its child, and the consequence is that even the parent's owner cannot see the
  derivations.** Making an exception there revives, on the parent's side, the very reason the
  follow-the-parent design was rejected.
- **A shared work is marked as such in the list** (`HistoryItem.shared`). **It is set only when
  true, so a client that does not know the key sees a byte-identical response.** Without the mark,
  **another member's work sits in the deletion screen looking exactly like your own.**
- **Recipients can be picked by name** (`GET /api/auth/me/group-peers`). It returns **`id` and
  `username` only**, and **only for members of your own organisation group** (a member without one
  gets an empty list — "no organisation" is not an organisation). **The full roster `/api/users`
  stays closed** (still 403 for an ordinary member, with **a control test**, without which an
  implementation that opened the roster to everyone would pass the new tests too).
- **Single-user mode can be chosen again** (`GET/PUT /api/settings/single-user`).
- **CLI**: `history share`, `history unshare`, `history acl`, `history peers`, `single-user show`
  and `single-user set` were added.
- **An existing database opens unchanged.** The only schema change is **one added table,
  `history_acl`**; no existing column moves. `create_all` builds it at startup, so **no migration
  command is needed**. **Measured**: opening an old database with the new code leaves the content
  hash of `history` and the existing lineage nodes identical, and the row counts of the other ten
  tables agree. **Rolling back keeps the rows** — sharing simply goes inert, and returns on upgrade.
- **⚠ The API-surface gate was raised from a count to a declaration.** The previous surface was
  frozen as `api-surface-before-the-guest-list.json`; **what was added (5 routes, 7 schemas) and
  what changed (`shared` on `HistoryItem`) are named**, and **the remaining 82 routes and 81 schemas
  must match the frozen file exactly.** **The previous gate measured two claims at once** — that the
  frozen 79 were intact, and that nothing had been added since — so **adding three schemas turned it
  red without one of the 79 having moved.** Selecting by name before comparing digests keeps the real
  claim and **also catches a name that disappears**, which a bare count could not.
- **⚠ Three defects found along the way were fixed.** ① `inku-cli refine save` **had never once
  succeeded**: all four `--kind` values returned 422, because the mapping existed only in
  `refine perform`. ② The surface gate above. ③ The lineage cleanup on deletion **missed when a work
  was deleted through an ACL grant** — the row's owner is not the actor, so **the work vanished while
  its node was never tombstoned.**
- **Checks:** **server 2,826 passed / 31 skipped** (26 new on the branch; **the other +22 came from
  main's ddl-engine 12 cycle**), **cli 217 passed**, **`npm run check` 0 errors / 2 warnings** (the
  two pre-existing a11y ones), **`test:unit` 132**, **`lint:i18n` 0 errors**, **ruff clean** (server
  and cli). **No deterministic drawing layer was touched, so the reference corpora did not move a
  byte.** Against **53 new tests** (server 34, cli 14, web 5), **34 perturbations were applied and 32
  turned red.**
- **⚠ The two that missed exposed double protection rather than a hole in the tests** — the content
  of an unreadable node is stopped both by an early return and by a hydration step that admits only
  readable rows, so **removing either one leaves the other holding.** Removing both turns the tests
  red, so they do discriminate.


### v2.12.3 — The list asks for what it shows (Build 880, 2026-08-11, first load)

- **The first load stopped pre-fetching 50 MB.** `/api/history` asked for **one page of the history
  manager (65) rather than what the strip below the canvas shows (21)** — for a modal nobody had
  opened. The request now asks for what is shown. **Measured 52,945,665 → 23,524,802 bytes** (same
  machine, same 1909×1056 dpr 1 window). **The response total went 2,675 → 1,997 ms, and time to
  interactive 5,769 → 4,808 ms.**
- **The history manager fetches its own page when it opens.** The pre-fetch **was paid on every
  visit, including the ones where nobody opened it** (of 1,751 requests in 24 hours of production
  logs, only 6 show the manager being opened). **The cost now falls on whoever opens it.**
- **⚠ Three defects found along the way were fixed.** ① The search `$effect` reads whether the modal
  is open, so **opening it sent two requests** (105.9 MB). ② The modal measures its own grid once on
  screen and reports **65 → 52, which sent a third** (99.4 MB); a request already in flight for 65
  answers a need for 52, and that judgement now drops the duplicate. ③ That duplicate was dropped
  **after taking a request number**, so **the dropped question demoted the real request in flight to
  "superseded" and the 52 MB that arrived was discarded** — the judgement moved ahead of the
  numbering. **⚠ The third one is invisible to a test that counts requests** (the count was a
  correct 1), so the test was moved onto **the works actually reaching the screen.**
- **⚠ The contract's estimate for the long task that follows (1,055 → about 470 ms) was wrong.**
  Measured: **1,497 → 1,349 ms (−10%)**. The reason is measured too — **the DOM node count (74,721)
  and `<path>` count (6,845) did not move at all.** The strip draws 21 thumbnails before and after;
  what disappeared was only the work of parsing 44 items that were then thrown away. **The
  improvement comes from the wait (−678 ms) and time to interactive (−961 ms), not from drawing.**
- **Two places decide how many works one page holds** (the page estimates 65, the modal measures 52).
  **This version's judgement absorbs the difference, so no extra request results**, but the fact
  stands and was filed in the ledger.
- **Checks:** **web `test:unit` 132 → 146** (nothing deleted or renamed), **`npm run check` 0 errors /
  2 warnings** (the two pre-existing a11y ones), **`lint:i18n` 0 errors**, **server 2,826 passed / 31
  skipped**, **cli 217 passed**, **ruff clean** (server and cli). **No byte of `server/` changed, so
  the reference corpora did not move.** **Eleven perturbations were applied and all eleven landed**
  (the contract's six, plus five for the mid-flight ruling and the gates added along the way).
- **⚠ Three perturbations missed first, and each time either a test or the implementation was fixed.**
  One of them measured a case where **`preloadMatches` is an AND of "the cached key matches" and
  "enough items are in hand", and the item count alone made it false** — so writing the key changed
  nothing. Replacing it with **a case where only the declaration decides** turned both tests red.

### v2.12.4 — the thumbnail is an image, not the drawing (Build 882, 2026-08-11, first load)

- **The listing stopped carrying each work's whole drawing and now carries a baked image.**
  `GET /api/history` returned the full SVG of every listed work (**measured: 23,524,802 bytes,
  median 1,816 ms, of which 1,184 ms was the server serializing**). The cost is set by
  **characters, not by how many works there are** — it is the time to inspect and escape 22
  million characters into one JSON document. **Works are now rasterized once, after saving,
  into a derived `thumbs.db` beside the canonical database.**
- **⚠ Not one pixel of the picture changes.** This is **rasterizing the stored SVG**, not
  re-rendering it. **The engine is never run** — a work drawn by engine 2 becomes a PNG of the
  engine 2 picture.
- **The listing prefers the PNG and falls back to the SVG** for works not baked yet. Every
  listing that puts works side by side goes through the same component — **all seven of them** —
  so a page holding both kinds is fine.
- **`GET /api/history` gained `include_svg` (default `true`).** Only the web listing sends
  `false`. **Even then the `svg` key stays and comes back empty** — dropping the key would make
  "no picture was asked for" and "a server too old to have been asked" the same shape on the
  wire. **`inku-cli history` gained `--no-svg` as well.**
- **Rebuilding thumbnails is a production feature.** An administrator can start it from the
  settings screen and watch the remaining count. **The old image keeps being served while a new
  one is being built** (never a blank). **HiDPI is a setting** (off by default); turning it off
  asks for confirmation and removes only the 2× rows. **Deleting `thumbs.db` outright leaves the
  canonical database whole.**
- **The number of works one page shows and the step the pager takes now agree.** v2.12.3's
  judgement reduced the fetch to one, but **65 works were shown while the pager advanced by 52,
  so the 53rd to 65th appeared on two pages at once** (13 measured). **Overlap and gaps are now
  zero, without discarding works already in hand.**
- **Checks:** **server 2,826 → 2,844 passed / 31 skipped**, **cli 217 → 218 passed**, **web
  `test:unit` 146 → 158** (nothing deleted or renamed), **`npm run check` 0 errors / 2 warnings**
  (the two pre-existing a11y ones), **`lint:i18n` 0 errors**, **ruff clean** (server and cli),
  **`check_docs.py` consistent**, **frozen corpora byte-identical** (no engine moved).
  **Seventeen perturbations were applied and all seventeen landed.**
- **⚠ Two perturbations could not be made to happen as written.** (1) `svg_to_png` ignores
  `height` when `width` is given, so **passing both does not break the proportions** (re-aimed at
  the direction that does). (2) Deleting `svg` from the dict does not remove the key, because
  **`response_model` puts its default back** (re-aimed at the serialization layer).
- **⚠ Acceptance found two gaps and closed them.** (1) **No test went through the command line.**
  The path that reads a listing's drawing and writes it out will, given an empty string, **write
  a 0-byte drawing and a blank PNG and report success.** A gate now measures, from both sides,
  that the senders which name no flag are relied upon to receive the drawings. (2) **`--no-svg`
  had not reached the generated help block**, which turned the manual gate red on the merged tree
  (regenerated).
- **Production-scale figures were not measured.** The local database holds 83 works totalling
  350 KB of SVG — **a different population from production's roughly 1 MB per work**. Response
  size, backfill duration and the real size of `thumbs.db` **will be measured after deployment.**

### v2.12.5 — thumbnails bake on every core, and one bad work no longer stops the run (Build 883, 2026-08-11, first load)

- **Baking moved into child processes.** v2.12.4 called `resvg` in this process inside a thread pool,
  and **`resvg` holds the GIL for the whole rasterization**, so **the `workers` setting changed the
  shape of the queue and nothing else.** Measured: the same twelve bakes took **10.08 / 10.36 /
  11.49 s** at 1 / 2 / 6 threads — six threads was slower. In production **one of eight cores ran at
  99.4% while the other seven sat between 0 and 1.2%.** The project's own "six ways, about eight
  times" is a figure from a different path, one that runs a child process per file, and it had been
  carried over to this one. **⚠ Only the rasterizing crosses to a child; the write into `thumbs.db`
  happens in the parent**, so SQLite keeps one writer. **⚠ Spawn is named explicitly** — a threaded
  server must not be forked.
- **A work that cannot be baked no longer takes the rest with it.** In v2.12.4 one raised work meant
  **the remaining works were never attempted**, and the run **reported itself finished with no
  failures.** Measured in production: **it stopped at 481 of 2,917**, and nothing in the status said
  so. **⚠ A listing holds no drawing for an unbaked work, so nothing is drawn there.**
- **A run that stopped short now says so.** The rebuild status gained `ended_short`. **"Not running,
  no failures" is also what a completed run looks like**, so the two could not be told apart.
- **Checks:** **server 2,844 → 2,847 passed / 31 skipped** (three new), **cli 218 passed**, **ruff
  clean** (server and cli), **frozen corpora byte-identical**, **no change under `web/`**. **Three
  perturbations were applied and each reddened exactly one gate** (drop the guard → T-R1, stop
  recording the short run → T-R2, go back to threads → T-R3).
- **⚠ Neither defect appeared until v2.12.4 was deployed and the real 2,917 works were baked.** The
  83 works on the development machine never stopped, and never showed the load sitting on one core.

### v2.13.0 — the administrator enters the parallelism (Build 884, 2026-08-11, first load)

- **⚠ Compatibility breaks.** `POST /api/settings/thumbnails/rebuild` **no longer takes a body.**
  **The parallelism is a stored setting rather than something each request carries** — an
  administrator enters it as `workers` (1..16, default 4) on `PUT /api/settings/thumbnails`, and the
  rebuild reads it. **One place decides it.**
- **The machine is not asked for its core count.** Nothing in `server`, `shared` or `cli` read it
  before, and nothing does now. **In a container the host's count is the wrong answer**, so the
  number comes from the person who knows, not from the machine.
- **A killed child no longer ends the run.** When the pool breaks, **handing work over** raises just
  as taking a result back does, and only the taking side was guarded. **This is the first thing that
  happens when a container's memory is capped.** What could not be handed over is now counted, and
  the run reaches the end of its list.
- **Checks:** **server 2,847 → 2,850 passed / 31 skipped** (three new), **cli 218 passed**, **ruff
  clean**, **frozen corpora byte-identical**, **no change under `web/`**. **Three perturbations, one
  gate each.**
- **The API surface moved in four named places** — the rebuild POST lost its body,
  `ThumbnailRebuildBody` is gone, and `ThumbnailSettingsBody` and `ThumbnailStatus` each gained
  `workers`.
- **⚠ Baking straight after a save is unchanged.** That path is still threads, and
  `INKU_THUMBNAIL_WORKERS` still makes no difference to how long it takes.

### v2.13.1 — the count is read in one place and the macro honours it (Build 885, 2026-08-11, drawing)

- **Write "three" beside a plugin and three are placed.** The expansion layer read no number at
  all, so `Nature.青葉を三つ置く。` came back as one group. **What a plugin hands over is one unit,
  and a count stated in the phrase says how many of those units to place** (**what one unit becomes
  is settled by the plugin document's declaration and the seed; the body does not reach inside it**).
- **One reader for the count.** The twelve definitions coerce carried moved to
  `server/src/inku_server/counts.py`, and the expansion layer reads the same words. **A hole in the
  reader can no longer be fixed on one side only.**
- **The count belongs to the phrase, not the sentence.** Of seven production works stating a count
  beside a reference, **five carry another number in the same sentence** (`一つ` / `一本`), and
  reading by sentence left all of them at one unit. The boundary is the comma.
- **A count the work has no room for is declined, not trimmed.** When the stated number times one
  unit exceeds the budget, the single unit stands and a line goes into `plugin_warnings`. **Knowing
  a number was not drawn beats drawing a number nobody chose.**
- **The English path reads Arabic numerals.** It used to require a noun from a 32-word table, which
  is why `Draw 12 circles.` was invisible to it. **The table is gone.** Numerals that are part of
  another number — decimals, fractions, ratios, percentages — are not counts (measured: without
  that exclusion a radius of `0.11` was read as `0` and `11`).
- **The Japanese path is untouched.** A bare numeral with no counter is still not read; the true and
  false cases are eight against eight, so it needs a ruling.
- **`ddl_engine_version` 12 → 13, and the reference corpus gained part C (plugin expansion).** That
  layer had carried a version number from the start and **never a frozen output**: part A's plugin
  work is the `Nature.` macro regex in `ddl_expander`, and the document plugin manager is called
  from the render route alone. **The corpus goes 36 → 40 cases (A 13 / B 23 / C 4), and the four new
  ones are the whole of what moved.**
- **⚠ Where the two rulings do not meet is recorded rather than fixed** (**undecided**): in an
  English description, a plugin whose name contains CJK is not counted by an Arabic numeral
  (`Place 12 Nature.青葉 marks.` places one unit, `twelve` places twelve). The rule that leaves a
  numeral with CJK within twelve characters to the Japanese path lands on the reference name itself.
  **The fourth C case freezes this**, so a ruling either way moves a case.
- **Checks:** **server 2,890 passed / 31 skipped** (39 new on the branch, one discriminator added for part C on acceptance, none lost), **cli 218 passed**, **ruff clean**,
  **frozen corpora byte-identical**, **Android JVM 0 failures**, **no change under `web/`**.
  **Fourteen of fifteen perturbations landed**; the one that missed (P-15) missed on where it was
  aimed — applying stage 3's own change did redden T-13.


### v2.13.2 — The refresh does not carry the gallery (Build 886, 2026-08-11, first load)

- **The twelve-second refresh no longer re-fetches the whole list.** It used to carry every work
  each time, whether or not anything had changed. **Now it asks what changed first, and does
  nothing when the answer is nothing.**
- **`GET /api/history/state` is new.** It returns three values -- the total, the newest work's
  timestamp and its id -- and **reads no picture bytes at all** (89 bytes of body against a local
  83-work database). Visibility runs the same three filters as the listing, in the same order.
- **The decision compares against what the strip on screen is showing**, not against a remembered
  answer: remembering forces one fetch immediately after start-up.
- **A strip that cannot answer declares itself stale.** Its first work is the newest one only on
  page one with no filter. **Anywhere else it fetches rather than going quiet**, so removing that
  condition later cannot turn into a permanent "nothing changed".
- **Returning to the tab now goes through the five-second floor too.** Only the `force` path
  skipped it, so moving between tabs carried the whole list each time.
- **Measured (83 local works, a window of about 90 seconds)**: list fetches **8 → 0**, API traffic
  **468,880 → 2,723 bytes** (**176× less**). **Main-thread blocking was zero at the starting point
  as well** at this size, so it shows no difference here.
- **`inku-cli history state` is new.** With `--bytes` it wraps the response in the byte count it
  actually arrived in.
- **The API surface goes 92 → 93 routes.** Exactly **one operation and one schema** were added and
  **the existing 92 of each did not move by a byte** -- the diff was measured before the baseline
  was regenerated.
- **Measured at production scale after deployment (2,897 works)**: the new question costs
  **91 bytes at a median TTFB of 30.8 ms**; the listing it replaces costs **163,008 bytes at a
  median TTFB of 1,201 ms**. That is **1,791× less data and 39× less waiting per poll** -- and when
  nothing changed, even that one call does not happen. **The total, the newest timestamp and the
  newest id all three agreed with the head of the listing.**
- **Checks:** **server 2,898 passed / 31 skipped** (8 new from the branch, 40 from main, none lost),
  **web 173 passed**, **cli 219 passed**, **ruff clean**, `npm run check` **0 errors / 2 warnings**
  (the two pre-existing a11y ones), **i18n 0 errors**, published documents consistent.
  **All fifteen perturbations landed** -- **two of them only after the acceptance gates they aimed
  at were found to have no discriminating power and were repaired.**
- **No deterministic layer was touched**, so no frozen corpus was regenerated.

### v2.13.3 — The editor says which plugin name does not exist (Build 887, 2026-08-11, ledger I-207 ruling C)

- **Writing a qualified name that does not exist, such as `Nature.菖蒲`, silently cost the whole
  sentence.** When the expansion layer strips `Nature.` it removes that sentence with a warning.
  **The warning was recorded and never reached the author** -- `plugin_warnings` was read in
  **zero places** across web and cli.
- **The editor now says so while you type.** An unregistered qualified name takes a different color
  and the reason is listed under the editor. **Red is not used**: plugins can be added later, so the
  truth is "not on this server yet", not "wrong".
- **When the word is a firing word, the editor says how to drop the prefix.** `Nature.菖蒲` reads
  `Remove "Nature." and it fires as "下草"`: `菖蒲` fires `Nature.下草`, and **it is the qualified
  name that is invalid**. Otherwise it reads `This name is not registered`.
- **It also stays after the work is painted.** `plugin_warnings` appears under the interpretation.
  **That cannot replace the editor**, because it only tells you once the sentence is already gone;
  ruling C asks for both.
- **The listing API now returns `fires_on_ja` / `fires_on_en`.** ⚠ The editor actually reads
  **`GET /api/saijiki`**, not `GET /api/plugins`, so both carry it.
  **No existing key was removed or renamed.**
- **⚠ A valid qualified name looks different now too.** `Nature.青葉` used to have only `青` painted
  in the catalog color; the qualified name is now **taken as one word**, so it shows as a single
  plugin token.
- **A word without a dot is unchanged**: plain `菖蒲` stays an ordinary word.
- **The API surface did not move.** The route total stays at **93** and the diff against
  `api-surface-baseline.json` is **zero lines** -- the 200 response of `/api/plugins` is a generic
  object with `additionalProperties`, so entry keys were never on the surface. **Gating this
  addition on the baseline would therefore be vacuous**, and the acceptance counts keys on a real
  response instead.
- **The web tests can now call application modules.** A hook that resolves extensionless relative
  imports was added and `test:unit` runs through it. **It fires only after Node's own resolution
  fails** -- on acceptance, importing a module that does not exist was confirmed to go red.
- **Checks:** **server 2,903 passed / 31 skipped** (5 new on the branch, none lost), **web 188 passed**
  (15 new), **cli 219 passed**, **ruff clean**, `npm run check` **0 errors / 2 warnings** (the two
  pre-existing a11y ones), **i18n 0 errors**, published documents consistent. **Ten of eleven
  perturbations landed**, and **the seam the missing one exposed got a roll-call gate**: the key
  names the web reads are checked against a real server response.
- **No deterministic layer was touched** (`document_format.py` did not move by a byte), so no frozen
  corpus was regenerated. **This change tells the author; it does not change what the layer does.**

### v2.13.4 — The work leaves as one sheet (shareable card) (Build 888, 2026-08-11)

- **A work can now leave as a single card.** The drawing, the headnote, the last four digits of the
  render seed, and the seal are composed into one sheet, in **a square layout (1080×1080) and a
  portrait one (1080×1350)**. It is exported from history management; layout and seal live in the
  settings. **A work with no headnote becomes a card of the drawing alone**, and a work with no render
  seed shows no seed line.
- **⚠ Until now the repository carried no font at all.** The rasterizer used whatever the baking
  machine happened to have, so **the same work came out with different letterforms on different
  machines**. If the server is to do the typesetting, the letters have to travel with it.
  **Noto Serif JP (variable, 12.95 MB, SIL OFL 1.1) now sits in `server/src/inku_server/fonts/`** —
  it covers all 1,233 characters of demand taken from the frozen DDL corpus and the repository's
  Japanese prose, with a cmap of 16,726. **⚠ The headnote is free text, so 1,233 is a floor, not a
  ceiling.**
- **⚠ resvg draws nothing at all — and raises nothing — when the family name does not match.** For
  this variable font, name ID 1 is `Noto Serif JP ExtraLight` and **name ID 16 is `Noto Serif JP`**;
  write the former and the card comes out blank. **A test of its own measures that the name written
  into the SVG is the name the bundled file answers to**, because that mistake appears only as an
  empty card.
- **`svg_to_png()` gained `skip_system_fonts` and `font_files`, and its defaults are unchanged**, so
  **the six existing callers** (animation ×2, colophon, autonomous refinement, the API's rendering,
  and thumbnails) produce the same pixels as before.
- **The drawing is nested as SVG rather than pasted as pixels**, so the card stays vector until the
  single rasterization at the end. **A long headnote shrinks the frame around the drawing, and
  anything past six lines is cut with `…`** — without the cut, the drawing is pushed off the sheet.
- **From the CLI: `inku-cli export-card`** (`--out`, `--layout`, `--no-seal`). **⚠ Passing a
  directory that does not exist, in the form `cards/`, produced a PNG named `cards`, and the second
  card overwrote the first** — found and fixed by the implementing session, which now reads the
  trailing separator too.
- **The API is one route, `POST /api/history/export-card`.** It goes through identity, and **another
  person's work id returns 404**. **The public list is still six.**
- **⚠⚠ Two branches wrote the same number into the same guard in one cycle.** Contract 3 (the twelve
  second poll) and the card both wrote **93** — "the branch point's 92 plus my own one" — and
  **either one taken on its own is wrong**. **The right value is 94, and the merge added both**:
  `EXPECTED_ROUTE_COUNT`, the three api-surface counts, and the allow-lists of the two guards that
  hold a frozen file (**one of which goes red without conflicting at all**, because its frozen file
  is the 92 of the branch point and one of the two additions then reads as undeclared).
- **The set difference was measured before anything was regenerated**: the merge added **two
  operations (`POST /api/history/export-card` and `GET /api/history/state`) and two schemas**, and
  **the preceding 92 operations and 92 schemas did not move by a byte** (none removed, none changed).
- **Checks:** **server 2,923 passed / 31 skipped** (**20 new from this branch** = 19 functions, one of which splits into two layout cases; **none lost**); **web 191 passed** (3 of them from this branch, the rest already on
  main from the two contracts that landed first); **cli 220 passed** (**the +1 is this branch's** —
  adding `export-card` gave the parser-help test one more case); **ruff clean** (server and cli);
  `npm run check` **0 errors / 2 warnings** (the two pre-existing a11y ones); **i18n 0 errors** (1,046
  English strings). **The implementing session applied 11 perturbations, and 23 tests went red
  against a contract that predicted 15** (the three that differed are explained with measurements).
- **No deterministic layer was touched** (`renderer.py` did not move by a byte), so no frozen corpus
  was regenerated.

### v2.13.5 — The share card leaves from the canvas too (Build 890, 2026-08-11)

- **Added `Share card` to the toolbar under the canvas.** It sits to the right of PNG, and **one press exports a
  card of the work on the canvas**. Nothing has to be checked or selected. The layout and the seal follow the
  same settings the history modal uses.
- **Renamed the button from `Card` to `Share card`** (both languages). **It is one key** (`historyCardExport`),
  so the button in history management changed with it.
- **A work that has not been saved yet has no card.** `history_id` is optional and `displayedHistoryItem` can be
  null, so **the canvas button is disabled on `currentHistoryId` as well as on `!result`** — a press can never go
  out with no id.
- **The canvas toolbar (`status-bar`) is not wrapped in any of the seven visibility groups, so this button
  appears in the simple UI too.** (The card in history management stays inside the `history` group.)
- **Checks:** **web 196 passed / 0 failed** (**5 new**, none of the existing 191 lost), **`npm run check`
  0 errors / 2 warnings** (the two existing a11y ones), **i18n 0 warnings / 0 errors** (**1,047** English strings,
  47 exceptions; 1,046 at the branch point), **server 2,923 passed / 31 skipped**, **cli 220 passed**, **ruff clean**.
- **Five perturbations were applied, and all five turned exactly one test red as predicted** (no misses):
  restore the label, move the button to the left of PNG, drop `currentHistoryId` from `disabled`, remove only the
  prop wiring while keeping the function, and drop the key from the type. **The fourth is the one that catches a
  button placed with no path behind it.**

### v2.13.6 — A mark keeps the shape its description gave it on any canvas (Build 891, 2026-08-11, ledger I-135 ruling A, render engine 30)

- **A mark's extents now become pixels through the canvas's short edge.** Engine 29 stretched `size` through
  `canvas.width` and `canvas.height` **separately**, so **the same description drew a different shape on every
  aspect**: a square written `size [0.3, 0.3]` came out 1.61:1 on the golden canvas and 0.20:1 on the pillar,
  and **an ellipse written `size [0.4, 0.2]` -- wide, 2:1 -- came out 0.40 on the pillar: upright, the reverse
  of what the description said**.
- **All twelve sites in `renderer.py` now go through one helper, `_size_px`.** **Placement (`_px`) was not
  touched by a byte** -- coordinates still scale with width and height, so **the aspect still decides where a
  mark sits, and no longer what shape it is**.
- **The square canvas does not move by a byte** (`unit == width == height` makes the two rules the same
  arithmetic). **The rebake moved exactly three cases**
  (`D-canvas-{pillar,vertical,wide}-filled-square-rotring`).
- **Four cases were added, taking the corpus to 553**: it held **no wide mark on a narrow canvas** and so could
  not tell a widened mark from a preserved one. The added `D-canvas-pillar-ellipse-pen` is **0.32 (upright)
  under the branch-point implementation and 1.59 (wide) under engine 30**; `D-canvas-square-ellipse-pen` is
  **1.59 under both** (the control).
- **Checks:** **server 2,941 passed / 31 skipped**, **web 196 passed**, **cli 220 passed**, **ruff clean**,
  `check_docs.py` consistent. **The implementing session applied five perturbations; P-1 turned red at all
  twelve sites** (the contract predicted four). **⚠ The contract's P-2 prediction did not hold**: a long-edge
  basis preserves orientation too, so T-2 does not catch it -- **what catches it is the mark staying on the
  paper**, and the implementation added a test for that.
- **The Android reference fixtures (64 files under `render-engine-30/`) were baked by the accepting session.**
  **The Kotlin renderer still carries the same wiring** (ledger I-217, a separate contract).

### v2.13.7 — The navigation buttons agree on which way is newer (Build 892, 2026-08-11)

- **The words for moving are now `newer` and `older` throughout.** The canvas read "next = newer" while the
  modal read "prev = newer" -- **opposite words, inside the same `ja.ts`**. **`prev`, `next` and `first` are
  gone from the screen**, replaced by `← newer`, `older →`, `Latest` and `Oldest` (both languages).
- **Fixed the presentation-mode `aria-label`, which said the reverse of the tooltip.** `‹` (which moves to the
  newer work) announced "older ×1". **Both now read the same key, so they cannot drift apart again.**
- **Fixed the canvas navigation going fully dead when the selection was cleared.** Six paths -- switching the
  Stage 1 model, re-choosing the colour catalog, detaching a lineage, and others -- cleared the selection while
  leaving the work on screen. `-1` is now read as "one before the latest".
- **`Latest` now means the latest work everywhere.** The strip and the modal judged it per page, so the canvas
  `Latest` could be the only enabled one on the same screen.
- **A one-work step and a one-page step now land consistently** (from the 22nd on page 2, `← newer` lands on the
  21st; it used to jump to the first).
- **Fixed duplicates and skips when the window is resized** (the offset is reseated onto the new grid).
- **Closed the request overtaking**: `fetchHistoryOffset` and `fetchTrashPage` were the only two async paths with
  neither a sequence number nor an `AbortController`. **The buttons are held while a fetch is in flight.**
- **A demo run now holds the canvas navigation too** (only the strip was held before).
- **The judgement moved into `web/src/lib/historyNavigation.ts`**, which the canvas, the strip and the modal all read.
- **Checks:** **web 225 passed / 0 failed** (**29 new**, none of the existing 196 lost), **`npm run check`
  0 errors / 2 warnings** (the two existing a11y ones), **i18n 0 warnings / 0 errors** (1,048 English strings),
  **server 2,941 passed / 31 skipped**, **cli 220 passed**, **ruff clean**. **28 perturbations, no misses.**
  The four that differed from the contract's table all turned **more** red than predicted, and the implementing
  session reported the discrepancy rather than adjusting the tests.
- **⚠ The implementing session pressed all 17 buttons on a real screen** (pentala, 2,924 works in history).

### 2026-08-12 — Design principle 4 now names what it denies (**no version bump**, documents only)

**The Japanese title of principle 4, "has no canvas", read as a denial of the vessel itself.** What it denies is a
**fixed size** — not the vessel, and not the range of aspect ratios (author's ruling, 2026-08-11). **The title now
reads "has no fixed size", and the number `0.0–1.0` was taken out of the sentence**: the principle states that
coordinates carry no absolute dimensions, and the granularity of the ratio is not what the principle requires.
**On aspect ratio the text says only that it is not fixed, and names no concrete ratio** — the phrasing "it does
have a ratio" was rejected by the author in the same ruling, because it implies that 1:1 is the fixed one. One
sentence says that the aspect ratio is a constraint shaping the world of the work, not a dimension the description
carries. **Four places changed**: the design principle in `SPEC.md` / `SPEC.ja.md` and the list of principles in
`README.md` / `README.ja.md`. **The English `SPEC.md` was already right in intent** ("not fixed pixels") **and was
brought to the same two sentences as the Japanese; `README.md`'s "No fixed canvas" was a literal translation of the
old Japanese title and was changed with it.** **No code changed.** `check_docs.py` is consistent.

### v2.13.8 — The arrangement of marks keeps its shape on any canvas (Build 893, 2026-08-12, ledger I-135 rulings R2 and R3, render engine 31)

- **A ring's radius and a region's extent now become pixels through the canvas's short edge.** Engine 30 put
  **a mark's own** size on the short edge, but **the layer that arranges those marks was still stretched by the
  aspect**: a `radial` ring became pixels through `canvas.width` across and `canvas.height` down, so on the
  pillar (1:5) **the ring came out with an aspect of 0.19** — round dots sitting on a flattened ring. An
  `at.region` behaved the same way: **a box written as a square came out as tall, or as wide, as the canvas.**
- **The region's centre is deliberately untouched** (author's ruling, 2026-08-12). **"Upper right" is the upper
  right of any canvas**, and placement still scales with width and height. **Only the extent moved.**
- **`arrangement.margin` is unchanged** (R1 was rejected in the same ruling): spreading to the frame is what
  `scatter`, `horizontal` and `vertical` mean.
- **Two sites read the region, and both now go through one helper** — `_resolve_at_region`, the anchor every
  region instruction passes through, and the grid branch, which reads it again for itself. **Fixing only one
  leaves the other's test green.**
- **A square canvas comes out byte-identical.** Centre ± half-extent does not round-trip in floating point even
  at a factor of 1.0 (for region `[0.6, 0.18, 0.82, 0.4]` `y0` moves by **2.78e-17**), which was enough to cross
  a rounding boundary and move the controls. **A short circuit returns the region untouched when both factors
  are 1.0.**
- **Sixteen cases were added to the corpus, which now holds 569.** Of the 553 cases before, **the five carrying a
  `radial` were every one of them square, and not one carried an `at.region`** — so this change would have left
  nothing at all in the record. The new cases are four subjects (a ring, a region resolved for one mark, a grid
  over a region, and a group whose region is only its anchor) on all four aspects: **the twelve non-square cases
  all move and the four square controls all stay**, measured on both trees. **None of the existing 553 moved.**
- **Reach in production** (2,939 live works, measured 2026-08-12): **515 are non-square (17.5%)**; of those,
  **R2 reaches the 63 carrying a `radial` (12.2%)** and **R3 reaches the 113 carrying an `at.region` (21.9%)**.
  Of the 181 instructions carrying an `at.region`, **the box confines marks in the 88 single ones and in grids**;
  for the rest only the anchor moves, which does not show.
- **Checks:** **server 2,978 passed / 31 skipped** (**37 new**, `test_arrangement_aspect.py`), **cli 220 passed**,
  **ruff clean**, **Android JVM 530 tests / 0 failures** (98 suites). **Seven perturbations, no misses** — the
  contract's six plus one the implementing session added for the version bump itself.
- **⚠ The implementing session reported that its first T-7 was vacuous**: with one Score and a single seed the
  2.78e-17 never crossed a rounding boundary, so the perturbation left it green. **Splitting the subjects into
  separate Scores and using two seeds turned five of eight red**, and the gate now sits in two layers, the other
  being an exact-equality check on the arithmetic.
- **⚠ The contract had missed one red**: the guard that hard-codes the case counts (`553` / `D: 32`) turns red
  from **stage 5** (adding cases), and the contract counted its reds before the cases were added. **It now reads
  569 / `D: 48`.**
- **The Android reference fixture (64 files under `render-engine-31/`) was baked on the accepting side.** The
  Kotlin renderer still carries the same anisotropy (ledger I-217, a separate contract). **⚠ Three call sites in
  `gen_android_reference.py` resolve the performance without passing a `canvas`**, so when I-217 ports this,
  those sites need one or the Android expectations will keep asserting pre-31 behaviour.

### v2.13.9 — Every mode keeps its history, and a work leaves from there as one sheet (Build 894, 2026-08-12, one contract plus ten dialogue-driven UI improvements)

- **The Simple UI now keeps its history.** Until now the simple screen was one where a work is **drawn, looked at
  and lost**: **both doors that take a work out as one sheet (the share card) belong to the history group**, so
  under Simple UI both were closed. **`SIMPLE_UI_VISIBILITY.history` is now true and the canvas toolbar stays in
  every mode** (under Simple UI the share card is the only control left on it). The principle that **a mode
  changes the display layer and nothing else** is unchanged.
- **The trash count is read from one source** (ledger I-218). Two props carried the same quantity; the `$effect`'s
  dependency was **pointed at that same one** rather than dropped — dropping it would stop the lineage from being
  refetched when a work moves in or out of the trash.
- **A dead path was removed** (ledger I-206): `preloadHistoryManagerFirstPage` and `preloadFirstPage` were never
  reached.
- **The page size has a canonical source** (ledger I-205). **`calculatePageSize`, which measures the real grid, is
  the canonical one**; the page-side function is **an estimate for the first fetch before the modal opens**. Both
  constants now agree with the CSS (`minmax(142px, 1fr)`), and the gate is **"the formula agrees with the CSS"**
  rather than "the two numbers are equal".
- **The English label for the root of a lineage is `Origin`, not `Root`** (ledger I-179). The Japanese `起点` is
  unchanged.
- **The layer versions are named the same way everywhere** (`Render engine version` / `DDL version` / `DDL engine
  version`), and **the info modal now shows all three**.
- **During a batch run the input area becomes the one line being painted**, with the sketch shown in the space
  that frees up, and the observation block **names the line of the body its content came from**.
- **A four-way generation is shown as the four parallel jobs it is** (one lane per candidate; the mascot is the
  unselected one and the phases are scattered at random).
- **The history strip gained an `Oldest` button and a `for revision` filter.** Its pressed state reads the same
  `--action-bg` / `--action-fg` as the history manager.
- **Deleting the displayed work from the modal now moves the canvas with the strip** as it reseats.
- **A hash's scheme (`rh3:` and the like) is a property of the value, not part of it.** The reading is collected in
  `web/src/lib/hashIdentity.ts`, and **a copy hands over the digest alone**. **⚠ The stored form is still
  `<scheme>:<digest>`, and neither the server nor the database changed by a byte** — what changed is what a copy
  puts on the clipboard, and **the prefixed form matched nothing anywhere in the app** (lookup is by the last four
  characters).
- **Checks:** **web 245 passed / 0 failed** (20 new; one existing test was rewritten, leaving the count unchanged),
  **`npm run check` 253 FILES / 0 ERRORS / 2 WARNINGS** (the two existing a11y ones), **`lint:i18n` 1,049 strings /
  0 warnings / 0 errors** (one new string), **server 2,978 passed / 31 skipped**, **cli 220 passed**, **ruff clean**.
  **Eleven perturbations, no misses.** ⚠ **Sixteen tests turned red against a prediction of twelve, and all four
  discrepancies were on the "redder than predicted" side.** A metagate left by an earlier contract, which runs every
  other test file in a child process, is dragged in by every perturbation, which brings the total to 27.
- **⚠ The contract covers the first commit only; the other ten are an override the author gave on 2026-08-12**
  (one item at a time: instruction, implementation, look at the screen, commit). **All of them are closed inside
  `web`; not one needed a server change.**

### v2.13.10 — Every reader counts the same way (Build 895, 2026-08-12, ledger I-212 to I-216, ddl engine 14)

- **A count is read in more than one place, and the places disagreed.** Five rulings landed in one contract.
- **The language of the description now decides** (I-212, I-216). The exclusion that drops a numeral sitting next
  to CJK applies **only when the body is Japanese**: **a `12` written in an English body is now twelve** even
  where a plugin word puts kanji beside it — before, it was dropped and the case froze at one unit. **All five
  callers of coerce hand the language over** (a roll-call gate counts them).
  **⚠ One of the places the contract said held a language did not**, and the implementing session resolved it
  through the same resolver the painting path uses, and reported the discrepancy.
- **The sentence is read only when the phrase naming the plugin states no count** (I-215); a count in the phrase
  is never overruled.
- **A bare numeral inside a phrase that names a plugin is a count** (I-213).
- **The English and Japanese paths now share one scan** (I-214). The twelve-word noun table and the separate walk
  that only the English side had **are gone**, and the two paths split clauses the same way.
- **⚠ Two rulings arrived while the work was running** — **(1) an exclusion for words that name an axis**
  (direction, orientation, kind, layer, row, column, degree, time, fold, part, and the English equivalents).
  Dropping the noun table made the four of `four directions` a count, **collapsing a 400-mark grid to four
  marks**. **(2) an exclusion for indices** (the 2 of `member 2` says which, not how many) — the expansion layer
  was building a group from a member number it had written itself. **Two acceptances were added, so the full
  score went from 22 to 24.**
- **Android was brought to the server's rule** (I-214). `ServerScoreSemantics.countHintFromDdl` is two lines of
  delegation and **the hand-written table of twenty-one kanji numerals is gone**. **The old implementation had
  neither ceiling nor exclusion**: it returned 0 for `radius 0.11` and 30 for a 30-degree rotation. **Its
  expectations are generated from what the server actually reads, not written by hand.**
- **The reference corpus was baked as `ddl-engine-14` (42 cases).** The two new ones are **a count stated outside
  the naming phrase (20 units)** and **a bare numeral inside one (50 units)**; **one case's judgement moved**
  (`C-plugin-count-as-a-numeral-beside-cjk`, one unit to twelve). **⚠ Two of the three entries in the bake's diff
  are new files, not cases that moved.**
- **Checks:** **server 2,997 passed / 31 skipped** (19 new, plus one the accepting session added), **cli 220
  passed**, **Android JVM 532 tests / 0 failures**, **ruff clean**, **frozen corpora byte-identical**,
  `check_docs.py` consistent. **Fourteen perturbations, 27 reds** against a prediction of twelve and fourteen.
  **One perturbation missed, and the implementing session fixed the gate rather than the claim**: T-12's input
  had a clause and a sentence that were the same string, so "always read the sentence" changed nothing.
- **⚠ Three things were fixed on the accepting side** — **(1) three hard-coded version literals**
  (two in `test_ddl_reference.py`, four lines in `test_api.py`); **(2) a gate that lost its discriminating power**:
  "the `twelve` and `12` cases must have different digests" became the opposite of a claim once the ruling made
  the two mean the same thing, so **it was inverted to measure equality** (restoring the exclusion for English
  bodies pulls them apart again and turns it red); **(3) the square where two rulings meet had no acceptance** —
  no test covered a bare numeral read through the widened sentence, so **T-25 was added** and shown to turn red
  under two separate perturbations.

### 2026-08-12 — The words for how a surface is were written into the spec ahead of the code (**no version bump**, documents only)

**The Saijiki gains a category called `おもて` (`surfaces`)** — empty, solid, pale ink wash, grain, stipple, hatch,
crosshatch, bleeding, aquatint, dense, faint: eleven words, with `empty` as the default.
**Where continuity says how a line is (solid, dashed, dotted, dash-dot), surfaces says how the inside of a closed
shape is.**
**⚠ This entry moved the specification only; the implementation is not there yet.** The saijiki table still holds
nine categories and seventy words with no `おもて` in it, and `GET /api/saijiki` and `inku-cli reference` return
what they returned before. **The current values of the vocabulary are owned by the implementation and published by
reference §1** (as §3.1 already says), so **the spec stands ahead of the code until the implementation lands.**
- **No verbs** (author's ruling, 2026-08-12) — "solid", not "to paint". **How a surface is is a state of the still
  image, not the passage of time**, so a word for the act would collide both with §2 principle 6 and with §3.1's
  "placing, not drawing". It stays out for the same reason 描く was pruned in v1.92.
- It carries **two dimensions: quality** (empty, solid, pale ink wash, grain, stipple, hatch, crosshatch, bleeding,
  aquatint) **and density** (dense, faint) — the same shape movements has with its amplitude, frequency, and quality.
- **⚠ `dense` and `faint` are relative, never an absolute darkness** — the same solid fill varies widely with the
  tool (measured mean luminance 17.4 to 131.1 at the native 1618px).
- **⚠ Paper grain does not belong here** — it is a quality of the support, and `Ground:` takes it. **An instruction
  to fill the background is not about a surface** either; it goes to the `background` field.
- **The `blurring` of movements and the `bleeding` of surfaces are now written as different things** (§13.6) —
  the line itself trembling and smearing is not the edge of a filled area spreading. **They part as verb and noun.**

**Six places were changed in each language** (§2 principle 6, the §3.1 category count, the §3.1 vocabulary table,
the §3.1 core property, §7.5, and §13.6). **Not one line of code changed.** `check_docs.py` is consistent.

### 2026-08-12 — CI now stops the regressions the corpora cannot see (**no version bump**, CI only)

**A `checks` workflow was added** (ledger I-192, closed) — four jobs: **server (`ruff` and `pytest`), cli (`ruff`
and `pytest`), web (`npm run check`, `test:unit`, `lint:i18n`), and the published documents
(`check_docs.py`).** The existing `reference-corpus` workflow (three jobs re-baking the frozen corpora) stays as
it was. **Until now CI ran the corpus regeneration and nothing else: not one line of pytest or ruff.**
- **The first Linux run turned two tests red** — **(1) the Android reference fixture re-bake**
  (`render-engine-31/manifest.json` and `renderer_variation_primitives.json` differ) and **(2) the
  platform-stability pair test** (the set of cases that move is not the frozen set). **Both compare against bytes
  baked on darwin and read the Linux bake as a defect.** They are deselected on CI with the reason written into
  the workflow; **both still run on the Mac, as before.**
- **⚠ The Android fixture directory was not being compared by the existing CI at all** — `reference-corpus`
  watches `server/reference/` and `android/design/preview/`, and
  `android/app/src/test/resources/server_reference/` is in neither. **The OS difference was observed here for the
  first time.**
- **Measured on Linux**: server **2,987 passed, 40 skipped, 2 deselected** (299s), cli **220 passed**, web **245
  passing** plus **0 type errors** (the two known a11y warnings) and **0 i18n errors**, `check_docs.py`
  consistent. **The numbers add up to the 3,029 collected locally.**
- **What CI still cannot see is now enumerated** (in the workflow and in PROJECT_CONTEXT): the **thirty**
  key-dependent tests, **ten** that need local-only material (nine `cli/bench/leaf`, one `cairosvg`), the **two**
  above, the **Android JVM tests** (no gradle wrapper), and **`no-git-sync/`** (untracked). **Skip reasons are
  printed every run with `-rs`: read that list rather than the pass count.**

### 2026-08-12 — a guard at the commit, where the exclude rules cannot help (**no version bump**, tooling only)

**`scripts/git/setup.sh` now installs a `pre-commit` secret guard** (ledger I-193). It scans every staged
blob against **nine content rules** (`nvapi-`, `sk-`, GitHub PAT, AWS AKID, Google, Slack, PRIVATE KEY,
`Bearer …`, and a `24+ hex . token` shape) and **nine path rules** (`.pem`, `.p12`, `.pfx`, `.key`,
`id_rsa`-family, `*_key.txt`, `.env` — `.env.example` excluded), and refuses the commit on a hit.
**It prints the rule name and the line number, never the value.**
- **Why exclude rules are not enough.** Local-only working material is `.gitignore`d, so putting it under
  version control takes `git add -f` — and **`-f` is precisely the flag that turns the exclude rules off**.
  The same keystroke stages a credential sitting beside it. **A guard has to live after the index.**
- **What a scanner cannot see is what the flag lets in.** A `grep` that honours `.gitignore` does not scan
  ignored directories at all, so **an audit of the work tree reports zero while `add -f` would stage them** (measured).
- **git silently skips a hook it cannot run** (measured). The hook was first installed as a symlink, with a
  comment claiming a dangling link would make git refuse the commit — **that was false; the commit went through.**
  A guard that disappears without a sound is the very failure this step exists to prevent, so the hook is now a
  wrapper that **checks its own target and refuses the commit when it is missing**. The rules still live in one file.
- **Zero false positives**: the nine content rules over **10,858** tracked text files (483 over 1 MB excluded),
  the nine path rules over all **17,204** tracked paths. Acceptance was measured
  five ways: two positives, one missing-guard case, one harmless commit, and the deliberate `INKU_ALLOW_SECRET=1`
  escape hatch. **It refuses to overwrite a `pre-commit` hook it did not write** (identified by a marker).
- **A public clone gets nothing and is told nothing** — the guard itself is local-only material and is not part of
  the published tree, so this step is silent there (verified against a simulated clone). `--no-verify` still bypasses it.

### v2.13.11 — The describe panel folds, and a plugin word wears the face of a built-in one (Build 896, 2026-08-12, empty contract "the UI improves in conversation", stages 1-3)

**A contract handed over as a frame and filled one stage at a time in conversation. Three stages landed.**

- **Both foldable sections of the describe panel remember their fold** (stage 1) — the sketch (Stage 0.5)
  gains a toggle, and the existing toggle for the expanded DDL (Stage 2 input) is now persisted. **The fold
  lives on the account, not in the browser** (`model_settings` allows `sketch_open`, default open, and
  `ddl_expanded_open`, default closed). **⚠ The premise measured at issue time turned out to be false**: the
  contract said the expanded section already persisted its state, and it did not — **it was stored nowhere and
  closed itself on every reload**. **With no example to copy, the author ruled, and both were given one.** Only
  the sketch body folds; the head — toggle, rule, edit button — stays. **Opening the editor unfolds it.**
- **A plugin word is shown the way a built-in word is shown** (stage 2) — the colour comes from `--accent` /
  `--accent-light` (six hard-coded reds removed), the chip is the same size as a built-in one, and **the
  explanation moves out from under the chip and out of `title` into the preview above.** The preview carries the
  same four parts as a built-in one: name, effect, example, picture. In the drawer and in the DDL editor modal.
- **A plugin document can now declare a picture** (stage 2, a spec addition) — a word block accepts
  **`preview:`**, naming **one PNG inside the document's own directory**. A path that leaves the directory
  (relative or absolute), a name that is not PNG, a file over 512 KB, and a missing file are refused, and **a
  refusal does not stop the document loading** (the word falls back to the shared picture a built-in word without
  one gets). **The HiDPI sibling is found by name, not declared** (`name@2x.png`). The picture is served by
  **`GET /api/saijiki/plugin-preview`** rather than riding in the Saijiki payload, and is shown in an `<img>` —
  **a document cannot put markup on screen.** Pictures for the seven `nature-leaves` words ship with it.
- **`inku-cli` gains `--fires-on`** (stage 2) — `--input-mode ddl` sends no prose, so **a DDL that spells a
  plugin word expanded to nothing.** What fires an expansion is the description, not the DDL.
- **The empty-canvas graphic no longer distorts with the canvas proportion** (stage 3) — the shapes were written
  as **separate fractions of width and height**, so the frame's ratio became the shapes' ratio (at Pillar 1:5 the
  triangle became a needle and the square a flake). **Only the circle survived, because its radius used one
  dimension for both axes.** The shapes are now drawn in a fixed square coordinate system and placed with **a
  single scale** against the short side, centred along the long one.
- **API surface**: one route added (`GET /api/saijiki/plugin-preview`, session required) and an optional
  `fires_on` on `ComposeRequest` (default None; callers that omit it are unaffected). **Nothing removed or
  renamed.**
- **Checks:** **server 3,028 passed / 31 skipped** (30 new), **cli 224 passed** (+4), **web 272 passing** (+27)
  with **0 type errors** (the two known a11y warnings unchanged) and **0 i18n errors**, **frozen corpora
  byte-identical**, `check_docs.py` consistent. **Twenty-three perturbations.**
- **⚠ Two perturbations missed, and the implementing session fixed the gates** — (1) the picture gate matched
  `/src=/`, **which also matches `data-src=`**, so renaming the attribute took the picture off the screen and
  left the test green; (2) the traversal perturbation did nothing to one case, because **the absolute-path
  example named a file that does not exist** and was being refused by the existence check rather than the guard.
- **⚠ The implementing session found and filled one missing acceptance** — **nobody had measured that the new
  flag does anything, in the cycle that added it.**
- **⚠ Two things were fixed on the accepting side** — **(1) the SPEC said plugin documents may not reference
  files at all**, which the new `preview:` contradicts head-on (rewritten in both languages as the single
  exception, with its conditions); **(2) a comment in `document_format.py` said `preview: <file>.svg`** where the
  implementation accepts only `.png`.

### 2026-08-12 — The stamper writes only when told (**no version bump**, tooling only)

**`scripts/bump.py` writes its six files only when given `--write`** (ledger I-195, closed). The accident that
opened the item: `--scan-build`, passed alone to *read* the next number, stamped the files then and there.
- **`--dry-run` was removed** (author's ruling, 2026-08-12) rather than kept as a synonym for the new default —
  the old `--scan-build --dry-run` now exits 2 through argparse, **so it cannot quietly come to mean something
  else.**
- **No default value was given** for the keyword, so a caller that forgets it stops with a `TypeError` instead of
  silently not writing. Automatic callers measured: none.
- A run without the flag prints `nothing was written (N file(s) would change) -- add --write to stamp`.
- **Five acceptances** (`test_bump_stamps_only_when_told.py`), run against **seven files copied into a tmp tree
  with its own `git init`** — pointed at the real repository, a regression in the guard would move the real
  `web/BUILD_NUMBER`, which is a shared counter. The perturbation (`if write:` to `if True:`) turns three red.
- **⚠ Five now-false command lines were corrected on the accepting side** — `AGENTS.md` and the git management
  handoff still carried `--dry-run` and a bump without `--write`. **The implementing session had updated the
  conventions, `CLAUDE.md`, and the memory; these two documents were missed.**
- **Not one byte of product behaviour changed** (only `scripts/` and `server/tests/` were touched).

### v2.13.12 — A shape can say how its surface is (the saijiki gains `おもて` / surfaces, ddl-engine 15) (Build 897, 2026-08-12)

**The lower layers held the mechanism and the upper layer had no word for it.** Among the 1,139 works holding a
closed shape, a fill was **asked for in words** in **1.3%** of them (15), while **96.7% of the works that came out
filled** (235 of 243) had never been asked to be. The cause was that **the words Stage 1 can write and the words
Stage 2 reads had an empty intersection in Japanese** — Stage 1 wrote 埋める and Stage 2 read 塗る. An
**eleven-word category, `おもて` / `surfaces`**, now stands directly after `つらなり` / continuity: **where
continuity says how a line is, surfaces says how the inside of a closed shape is.**

- **The words are state nouns, never actions** (author's ruling) — Japanese takes the noun **塗り** (not the verb
  塗る) and English takes **`flat`**. `solid` was not available: **continuity's `実線` already holds it**, and two
  adjacent lines of the vocabulary block would have carried the same word with different meanings. `fill` was not
  available either — movements' `埋める` holds it. **`flat` collides with no word in the ten categories or the
  relations** (checked mechanically).
- **The eleven words**: empty (default), flat, pale ink wash, grain, stipple, hatch, crosshatch, bleeding,
  aquatint, dense, faint. **Paper grain stays out** — it is a quality of the support, so `Ground:` keeps it.
  **`にじみ` (a noun) is kept apart from movements' `滲む` (a verb) by part of speech.**
- **Defect A fixed (the two sides named the same thing differently)** — Stage 1 wrote `面: 斜めに埋める。` while
  the Stage 2 table read `平行線`. **It appeared four times in DDL and zero times in a Score.** Both sides now
  say `平行線` / `hatch` (**Stage 1 already had `面: 平行線（粗から密）。`; only one of its two phrasings was
  missing from the table**).
- **Defect B fixed (a surface on a line drew not one pixel)** — the renderer requires a closed shape in two
  places, so **a `surface` on a line or an arc is never drawn. Measured: 798 of 1,495 surfaces (53.4%) were dead**
  (739 on `line`, 59 on `arc`; `wash` 453, `grain` 251, `bleed` 83, `paper_grain` 9, `hatch` 2). **A deterministic
  layer (coerce) now moves such a surface to the nearest closed shape before it, and drops it where there is none
  or where that shape already carries one** (**never guessing an interior into being, and never duplicating one
  texture request across two instructions**). The branch records itself in `coerce_branch_counts`, and **it is
  wired into the `INKU_COERCE_DISABLE` exit too** — whether a thing can be drawn is not a matter of style.
- **`_CLOSED_SHAPES` moved to `schema.py`** — coerce held five scattered copies that were missing `cloudform`,
  and **two layers deciding separately means one of them is always the stale one.**
- **The metadata reported textures that were never drawn** — `build_texture_metadata` now uses the renderer's test.
- **`DDL_ENGINE_VERSION` 14 to 15, and `ddl-engine-15/` holds 45 cases** (42 + 3). **⚠ The three added cases are
  the ones that traverse this change** — not one of the 42 inputs frozen at 14 carried a `面:` clause, so refreezing
  as it stood would have produced **the same corpus with a new version marker**, and the digest gate would have
  measured nothing.
- **⚠ The reach is not there yet (measured)** — `面: 塗り。` reaches `filled=true` **0 times out of 4**, and the
  pre-existing English `Fill it solid.` **0 out of 1**, so **it is not that the word is new**. Texture does arrive:
  `薄墨` to `wash` **4/4**, `平行線` to `hatch` **2/4** (the model chose `paper_grain`, which is not in the table,
  for the other two). **The coerce move fired 4/4 in production, leaving zero surfaces on open shapes.**
- **⚠ Three side findings, none of them addressed (all filed in the ledger)** — (1) `面: 薄墨。` came out fainter
  than the default (0.35/0.28 to 0.20/0.15): the model applies the new Stage 2 line to **the 薄 in 薄墨 itself**;
  (2) Stage 2 picks `paper_grain` out of the enum although the table never offers it; (3) `layer_versions.py`
  carries no note for engine 14.
- **Checks:** **server 3,048 passed / 31 skipped** (15 new), **cli 224 passed**, **web 272 passing** (0 type
  errors, the two known a11y warnings unchanged), **frozen corpora byte-identical**, **Android JVM 269 tests / 0
  failures**, `check_docs.py` consistent. **All fourteen perturbations turned something red.**
- **⚠ Three things were fixed on the accepting side** — **(1) four frozen web fixtures** (the editor paints every
  saijiki word, so `薄墨` gained colour the moment it became one): **the fixture was not rebaked; the substitution
  is declared and the test pins it at exactly four cases**; **(2) the four duplicated prompt constants in Kotlin**
  (`WebDdlSpec.kt` — when the server's wording moves, `PromptFingerprintTest` must go red; **a tool now copies
  them over wholesale**); **(3) the Android saijiki UI**, whose colour list held ten entries, so **the eleventh
  category quietly borrowed the first one's colour** (the lookup is `[index % size]`, which cannot fail).
- **⚠ This version moves the prompt layer and the clients; `render_engine_version` stays at 31.**

### 2026-08-12 — The stamper scans every face of the shared counter (**no version bump**, tooling only)

**`python3 scripts/bump.py --scan-build` now reads all three faces itself** (ledger I-196, closed).
**A scan short one face prints the same shape of answer as a complete one** — the missing face is invisible
in the very line that hands out the number. It had been reading `refs/heads/` alone, while **a comment in
the same file told a human to "also check `ssh pentala`".**

- **The three faces**: the refs (**including `refs/remotes/`** — a number another clone took and pushed
  lives nowhere else), **every worktree's working copy** (**a number taken but not yet committed lives
  nowhere else**), and the deployment host over one `ssh`. **The faces read are printed in the line that
  gives the number** — `next build number: 898 (scanned: 163 refs, 7 worktrees, ddl-server@pentala)`.
- **Where the host lives** comes from `INKU_REMOTE_HOST` / `INKU_REMOTE_REPO` first, then from the two
  default lines of the untracked `deploy.sh` (**the public repository does not carry the deployment
  target**, author's ruling 2026-08-12). **If those lines change shape it stops rather than guesses.**
- **If the ssh does not go through, no number is reported and the exit is 1** (same ruling). **`--local`
  drops only the host face and says so in the same line. `--local` alone exits 2** — a flag that silently
  does nothing is not worth having.
- **Thirteen acceptances** (`server/tests/test_bump_scans_every_face.py`), run in a tmp tree with its own
  git repository, a linked worktree, and an `ssh` stub first on `PATH`, **moving one face at a time.** The
  six perturbations turned **1 / 7 / 1 / 2 / 2 / 1** red, **each matching a prediction frozen before the
  code was written.**
- **⚠ One perturbation found a hole and the implementing session filled it** — the environment variables
  win along two paths (an early return when both are set, and a per-name override after `deploy.sh` is
  read), and **the acceptances went through only the first.**
- **The accepting side ran the product path** — three faces arrive from both the main checkout and a
  worktree, both reporting `next build number: 898`, agreeing with `cycle.sh build`'s own scan. **An
  unreachable host exits 1 and prints no number at all.**
- **Not one byte of product behaviour changed** (only `scripts/` and `server/tests/` were touched).
  **Checks went 3,048 to 3,061 passed / 31 skipped.**

### 2026-08-12 — One entry point for the suites, and no stale bytecode answering for it (**no version bump**, tooling only)

**A `Makefile` at the repository root makes `make test` the entry point for server, cli, and web**
(ledger I-198). **The trap was one you avoided by remembering it**: `uv run pytest` and
`./.venv/bin/python -m pytest` resolve a different `python` through PATH, so the same tree answers
differently. **The environment the conventions named is now closed inside the entry point.**

- **Four entries**: `make test` (all three), `make test-server`, `make test-cli`, `make test-web`.
  **Each is callable from the repository root** — the recipes `cd` for themselves.
- **`UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR`** live in the Makefile. **They use `?=`, so a surface
  that supplies them from outside — CI does — keeps its own values.**
- **The three CI jobs were moved onto the same entry.** **The server's two `--deselect` arguments are
  carried through `PYTEST_ARGS`** (ledger I-222: two tests compare bytes baked on darwin against a
  bake made on linux).
- **`PYTHONDONTWRITEBYTECODE=1` is now set on three surfaces** (ledger I-197) — the Makefile, both CI
  workflows, and the operational tooling (not public). **A reverted perturbation can no longer be
  answered by a stale `.pyc` on any of them.**
- **Measured by perturbation**: with `__pycache__` removed first, the guard leaves **0 `.pyc` files;
  without it, 141**. **Observing that no `.pyc` appeared is not evidence on its own** — an already
  current cache produces the same reading.
- **Checks**: server **3,061 passed / 31 skipped** (655s), cli **224 passed**, web **272 passed / 0
  failed**. **Not one line of product code moved** — only the `Makefile`, CI, and the tooling.
- **⚠ There is still more than one entry** — typing `uv run pytest` by hand is not blocked. **Both
  traps therefore stay on the record even though the mechanism landed.**
- **⚠ A hole left open**: `make test PYTEST_ARGS=…` passes server-shaped arguments to cli as well.
  **CI only ever passes them to `test-server`, so nothing is broken today.**

### Android — a work remembers its own colors too (android `2.1.4-android.25`, 2026-08-12)

**When a work's colors live only as a catalog id, the day the catalog is redefined is the day every
saved work is redrawn in different colors.** The server fixed this on 2026-08-09 (ledger I-123).
**Android had the same hole in a different shape** — the record was already being written
(`render_color_map` has been in the metadata since the first commit). **It was never read back.**

- **`WorkColorSnapshot`** reads the record out of the saved row's `render_metadata_json`. **The
  conditions are copied from the server's `_snapshot_render_metadata` as conditions**: **not a
  `JSONObject`, or empty, means no record** (not replaced by a defaulted lookup — an empty map has to
  take its own path), and **the id is `render_color_catalog_id`, then `catalog_id`, then the default**.
- **Only a redraw carries the record.** Of the three refinement routes, only `RenderFromScore` passes
  it; **a new drawing (`paint` / `composeFromDdl`) uses today's definition**, which is the branch the
  server takes for a request that names no work.
- **⚠ Drawing from the record does not rewrite the catalog id.** **The id is not only a nameplate —
  it is also part of the seed that assigns each chromatic color**, so the same map under a different
  id assigns differently. **The server's asymmetry is copied exactly: the recorded id when there is a
  record, the id today's catalog resolves when there is none.**
- **A work with no record is not refused.** Refusing would leave exactly the works that predate the
  record unable to be redrawn.
- **Nine acceptance cases** (`WorkColorSnapshotTest.kt`). **The id fallback is measured with three
  inputs, and seed stability across 1..200** — a single fixed seed can assign identically even when
  the id is swapped.
- **Six perturbations** (re-applied on the accepting side): **2 / 1 / 1 / 3 / 2 / 1** cases went red.
  **⚠ Substituting the *resolved* id reddens only two** — for a known id, resolved and raw are the
  same value. **Only the contract's form, substituting the default, reddens the third (the seed test).**
- **Checks**: Android JVM **278 passed / 0 failed / 0 skipped** on the merged tree. **`APP_VERSION`
  and `web/BUILD_NUMBER` did not move** — Android versions only `android/VERSION`.
- **⚠ One difference left**: when drawing from the record, the catalog name and subtitle come from
  today's catalog. **The server falls back to the id itself when the catalog is unknown.** That line
  was not quoted by the contract; it went to the ledger.

### v2.13.13 — a cluster and a path keep their shape on any canvas (Build 898, 2026-08-12, ledger I-135 (3), render engine 32)

- **A cluster's band, and a path's cross-axis spread, now become pixels through the canvas's short
  edge.** Engine 31 did this for the ring and the `at.region`; **these two arrangements were still
  stretched by the aspect** — and **36.2% of the marks production expands pass through them** (27.1%
  cluster, 9.1% path).
- **A cluster's band is built in a rotated frame and then written straight into normalized space** —
  a narrow vertical stripe on the pillar (1:5), a wide one on CinemaScope. **For one description the
  band's own aspect moved by a factor of 8.8 between those papers** (0.0395 to 0.4646). **At engine 32
  it comes out at 0.19771 — the square canvas's value — on all five papers** (measured). A path did
  the same: **a `wave` swung 220px on the square canvas and 44px on the pillar.**
- **⚠ The order decides the result: the offset is rotated first and put on the short side second.**
  **Scaling the axes before the rotation would turn the rotation itself into a shear.**
- **Left alone**: `margin` and `span` (how much paper a path uses along its own line — **[I-135] (3)-b
  is unruled**), `right_half`'s reach, `_path_pos`'s default branch, `_scatter_pos` (an affine map
  takes a uniform scatter to a uniform scatter), and **the cluster's centre**.
- **⚠ There are five wiring sites, not four** — `_clustered_pos` calls `_path_pos` itself to resolve
  its centre. **Forwarding `canvas` there would level the centres too, and "the middle cluster is
  above the others" would stop meaning the same thing on paper of a different shape** (R3). **The
  reason not to is recorded in a code comment.**
- **Not one coordinate moves on a square canvas.** Two layers hold it: the engine 31 placement
  coordinates frozen for four subjects, and a byte comparison of the whole SVG against a drawing made
  with the rule dropped (four subjects × two seeds).
- **The corpus grew by thirteen, to 582** — **the ten cluster and path cases it already held were
  every one of them square.** The new cases are **nine that move and four square controls**, and
  **none of the existing 569 moved**. **⚠ Each subject is drawn on the papers whose long side is the
  axis it spreads on**: a `top_to_bottom` on the pillar has a factor of exactly 1.0 and would be
  frozen unable to fail.
- **⚠ Every new ID counts as `changed_from_previous`**, so **the nine and the four cannot be told
  apart in the manifest. Only a perturbation can show which case discriminates.**
- **Checks**: server **3,101 passed / 31 skipped** on the merged tree (569s; **40 new cases**, 38 in
  `test_cluster_path_aspect.py` and 2 in `test_render_reference.py`), cli **224 passed**, ruff clean,
  frozen corpora byte-identical, Android JVM **278 cases / 0 failures**.
- **⚠ Two of the eleven perturbations found defects in the implementer's own acceptance tests, which
  were fixed and re-applied** — **both of the "measuring on the short side is green whatever you
  break" kind**. **P-5** used a `wave`, whose cross axis is only y, so on papers whose long side is x
  the perturbation was vacuous (switching the subject to `diagonal` reddened 4 of 4). **P-7** measured
  `horizontal`'s `span`, an x quantity, on tall papers, where the perturbation is the identity
  (papers were narrowed to match the axis; T-9 went from 8 cases to 4).
- **⚠ The prediction frozen before any code was written said 3,091; the measurement was 3,092** (off
  by one, reported with its direction). **Four of eleven perturbations matched the prediction; five of
  the seven misses were the prediction being coarse** — `_density_radius` is read from outside the
  cluster as well, so P-8 reddened 12 cases against a prediction of 4.
- **Two changes the contract did not name** (both consequences of the version rising): four version
  literals in `test_api.py`, and **the Android expectation fixture (64 files under
  `render-engine-32/`)**. **No Kotlin source was touched.**
- **⚠ Kotlin's `pathPosition` and `clusteredPosition` hold no short-side basis at all** (filed as
  ledger I-233) — the gap spans **three versions, 30, 31 and 32**. **On the day it is ported, the
  point is not to pass `canvas` to the one call that resolves the centre.**

### 2026-08-13 — The test entry points repair a clone that missed the git setup (**no version bump**, tooling only)

**All four entry points — `make test`, `test-server`, `test-cli`, `test-web` — apply
`scripts/git/setup.sh` once before the suite starts** (ledger I-199). **The trap was one you avoided
by remembering it**: the merge driver that keeps `web/BUILD_NUMBER` from conflicting has its command
in `.git/config`, which is not versioned, **so the one line in `.gitattributes` never fires on its
own and every clone needed a human to run the setup.**

- **All four carry `git-setup` as a prerequisite.** Make runs a shared prerequisite once, so
  **`make test` still emits `setup.sh` exactly once** — which is what the test measures.
- **`SETUP.ja.md` and `SETUP.md` were both updated** — from "once per clone" to "immediately after
  cloning, and if it was missed the make test entry points apply it idempotently."
- **Five tests were added** (`test_merge_driver.py` goes from 5 to **10**) — **that `make -n` prints
  `setup.sh` exactly once for each of the four entries** (4 cases), and **that an unconfigured clone,
  built for real and branched to 901 and 902 on `web/BUILD_NUMBER`, merges without a conflict and
  keeps 902** (1 case). **The last one reads both `.git/config` and the merge result.**
- **Checks**: server **3,106 passed / 31 skipped** on the merged tree (816s; **the +5 over the 3,101
  baseline is exactly the five new cases**), cli **224 passed**, ruff clean. **Not one line of
  product code moved** — only the `Makefile`, both `SETUP` files, and the tests.
- **Five perturbations, none vacuous.** Dropping the prerequisite from one entry reddens 1, from all
  four reddens 4, replacing the `git-setup` recipe with `@true` reddens 5, dropping the driver
  configuration from `setup.sh` reddens 1, and **making the driver keep the smaller side reddens 4**.
- **⚠ The accepting side's prediction matched on four of five and missed the driver one** (3
  predicted, 4 measured) — **the case that counts a non-numeric side as 0 writes its own 0 rather
  than the larger side once the comparison is inverted.**
- **⚠ Only the test entry point was closed.** The ledger's one-pager said "the test **and deploy**
  entry points apply it"; **the deploy entry point does not. A clone that never runs `make` is still
  unconfigured** — **and the failure direction is the safe one**: it conflicts the way it always did,
  it never produces a wrong merge.
- **⚠ Outside a git checkout `setup.sh` exits 128** (measured), so **`make test` fails in a tree
  unpacked from a source archive.** `SETUP` never asks for tests to be run there and the containers
  do not invoke `make`, so nothing operational is affected.
- **⚠ `setup.sh` installs more than the merge driver** — the pre-commit secret guard (ledger I-193)
  comes with it, so **the hook is rewritten idempotently on every test run** (a hook somebody else
  placed is left alone).

### v2.13.14 — The composition knows what paper it is on (Build 899, 2026-08-13, ledger I-135 A)

**Stage 2 composed without knowing which paper it was composing for.** The canvas aspect reached the
renderer, which used it to size the SVG frame, and **not one byte of it reached the side that builds
the composition** — a pillar (1:5) or a folding screen (2.2:1) received a composition built as if for
a square, which was then pressed into the frame. **From v2.13.14 the prompt states the paper.**

- **It states three things and no more** — **which paper**, **that what may be fitted to it is size
  and placement**, and **that a size the description states is not overruled by the paper**.
  **⚠ The number of marks never moves** (author's ruling: 72.6% of counts are measured to come from
  the description, so changing them for the paper would add what the description never asked for).
- **The paper is called a "support"** — using the same word a shape uses for "wide" makes the model
  read a statement about paper as a statement about a shape. The wording (`横に広い支持体` /
  `a support wider than it is tall`) is kept to words that only ever describe paper.
- **The retry states it too** (author's ruling) — a Stage 2 retry runs **a second generator with its
  own prompt**, and leaving that one paperless would drop the paper on exactly the runs that retried.
  **The retry was measured firing on the production path.**
- **The examples gained one non-square pair in each language** (author's ruling: **into the static
  body**; generating an example per paper was considered and not taken).
- **The paper is now settled before Stage 2 is called** rather than after it, which is why there was
  nothing to hand the composition before. **A side effect: the 422 for an unsupported aspect now
  answers before Stage 2 runs instead of after it.**

**⚠ The meaning of `Score.canvas.aspect` has changed.**

- **What Stage 2 declares is no longer overwritten with the requested aspect.** `Score.canvas` is now
  **the record of what the composition was built for**, and **the paper actually performed on rides
  in `render_canvas_aspect*`**. **The two may disagree** (works saved before v2.13.14 carry the
  requested aspect in both).
- **A redraw reads three answers in order** — the caller's override, **the performed paper recorded
  on the work's row**, then the Score's declaration. **An old work redraws exactly as it did**,
  because that column has been filled all along.
- **`/api/render` and `/api/history` still overwrite.** Those two receive a Score from the client, so
  there is no Stage 2 declaration to protect.

**Measurements (through the LLM; not acceptance tests)**: thirty runs were baked and read.

- **The paper reached the prompt** — `stage2_prompt_digest` was identical across three papers before
  and is distinct across all three after.
- **The paper moves size** — a circle's radius is `0.3 / 0.1` on square against a flat `0.15` on
  pillar; a line's length is `0.424` on square against `0.335` on pillar (before, square and pillar
  were both `0.424`).
- **The count did not move** (all six runs stating "one hundred twenty" came back `count=120`).
  **That is the design.**
- **⚠ The declaration rate is only 2/8 on non-square papers** (0/5 on square). **It arrives, but it
  is not yet much used.**
- **⚠ M-4 — whether a stated "small" stays small on a pillar — could not be measured**: the two runs
  that would have answered it hit a hard timeout and fell back. **There is no evidence either way.**
- **Retries ran on 6 of 30 (20%)**. **The past cannot be measured, so this is the first number**
  (taken while the shared LLM was busy).

**Checks**: server **3,140 passed / 31 skipped** on the merged tree (474s), cli **224 passed**, web
**272 passed** and `check` **256 FILES / 0 ERRORS / 2 WARNINGS**, ruff clean, frozen corpora
byte-identical, `check_docs.py` consistent, Android JVM **278 cases / 0 failures**. **34 new tests**
(33 from the implementation, 1 added at acceptance).

- **⚠ One perturbation came up empty at acceptance, and a gate was added** — a mid-flight ruling
  moved stage 4 from "stop overwriting" to "read the performed paper off the work's row", and
  **nothing walked that resolution order**. Removing the middle branch left **186 tests green**
  (**for an existing work the declaration and the performance always agree, so the branch only binds
  for works saved after this change**). **T-6b was added and reddens under the same perturbation.**
- **⚠ The contract said "two tests freeze this digest"; the measurement was four** — two more sat in
  other functions of the same files. **The number of lines a contract names is not the number of
  functions.**
- **Six of the implementation's nine perturbation predictions matched** (the three misses are
  reported with their direction). **⚠ One of them did not reach the acceptance it aimed at** — a
  perturbation that changes the body regardless of paper never touches the claim that carrying a
  paper moves nothing but the block. **A tenth perturbation was added and reddened six cases.**
- **Android**: the two duplicated prompt constants were synced and `2.1.4-android.26` was stamped
  (`sync_android_prompts.py --write`). **No Kotlin source was written by hand** — the tool copies the
  constants wholesale. **⚠ That `.26` was taken by another branch the same day and shipped nowhere;
  both changes ride on `.27`** (the Android entry below).

### Android — A work keeps the name it was drawn with (android `2.1.4-android.27`, 2026-08-13, ledger I-232, I-231)

**The "draw from the record" mechanism added by I-170 carried one regression.** The gate that hands
the parent's colour record to a refinement candidate keyed on **the route alone**, so **a refinement
asking for a different colour catalog** — which travels the same route — also received the parent's
record. **The result did not match the catalog that was asked for; it matched the parent** (measured).
**The gate now also asks whether the requested catalog is the parent's.**

- **The name and subtitle of a work drawn from its record resolve in the server's three steps** — **a
  non-empty recorded value, then today's catalog under the same id, then the id itself** (an empty
  subtitle). **An empty recorded value counts as absent and falls through**, the same judgement
  Python's `or` makes on the server.
- **A reader was added that asks whether an unknown catalog id exists without falling back to the
  default** (`ColorCatalogs.find`). **Not one of the fourteen catalog definitions moved.**
- **The name and subtitle stay out of the seed** — `computeColorAssignment` still takes
  `catalogMap`, `renderSeed`, and `catalogId`, and the two new values appear **only in the metadata**
  (not one pixel of the drawing changes).
- **288 tests, 0 failures** (10 new). **The accepting side measured the same number, matching the
  frozen prediction of 278 + 10.**
- **All nine perturbations were re-applied at acceptance** (the implementer was a different model, so
  nothing was skipped) **and all nine reddened the acceptance the contract named.**
  **⚠ P-8 reddened a different number here than in the report** (2 reported, 6 measured) — **the two
  perturbations differ in reach.** Mixing the name into the seed unconditionally also moves drawings
  that hold no record, which took four existing colour tests with it. **The named T-9 reddens either way.**
- **⚠ Two branches stamped the same `2.1.4-android.26`** — **git reports no conflict when both sides
  write the same bytes.** Two changes from one day were about to share one version number. The
  answer is N+2, so this one is `.27`.
- **`APP_VERSION` and `web/BUILD_NUMBER` did not move, and nothing was sent to pentala**
  (`android/` is permanently excluded from every sync path).

### v2.13.15 — Six ledger items, picked one number at a time (Build 902, 2026-08-13, ledger I-230, I-202, I-200, I-069, I-090, I-091)

**A contract that does not decide in advance what to fix: the author names one ledger ID at a time, and each one lands as its own commit.**
**Not a single pixel of a picture moves** (render engine 32 / ddl engine 15 are unchanged, and the frozen corpora are byte-identical).

- **Ledger I-202 — the shared button class was shared in name only.**
  `ghost-btn` was used in 17 files while **the base CSS was duplicated in 44 places inside individual components** (under Svelte's
  scoping, writing the class name does not reach a rule that lives elsewhere). **The base, hover, disabled, and `ghost-active` rules
  now live as one global rule each in `+page.svelte`, and the copies in 17 components are gone.** Sizes read `--btn-sm-*`; colors read
  `--panel` / `--fg2` / `--border2` and `--action-*`. **One of them, in `ShareModal`, was a filled primary action painted with
  `--action-bg`, so it was renamed to `.action-btn` with no change to how it looks** — it was never a ghost button.
  The plugin chip accent rule moved to one global rule as well, replacing a copy in each of two panels.
- **Ledger I-090 — the app is now declared to be drawn in the browser.**
  Eleven `.svelte.ts` files hold `$state` directly at module level, and with SSR enabled **that state can be shared across requests.**
  Since this is an authenticated single-page app, `export const ssr = false` states the boundary as a setting.
  The alternative — moving module-level state into a per-request context — **was not done**.
  **Note that the ledger entry asked for the latter** (see what was not done, below).
  The check freezes both the SSR setting and the inventory of the 13 files that hold `$state` (2 instance-scoped, 11 module-scoped).
- **Ledger I-200 — a generator run that stopped halfway corrupted the previous corpus.**
  SVGs and the manifest were written **directly** into the version directory before the identity guard was evaluated, so
  **a run that stopped rewrote half of the previous version, and the next version's `changed_from_previous` looked empty**
  (8 entries measured as 0). **Everything is now written to a staging directory beside the target, the guard runs before publication,
  and the finished tree is published with a single rename.** A run the guard stops writes zero bytes into the version directory.
  A permitted re-freeze of an existing version moves the old directory to a fixed holding name first, and
  **if the process stops between the two renames, the next run restores the old version.**
- **Ledger I-230 — `layer_versions.py` had no note for ddl engine 14** (13 followed 15).
  Ten lines were restored from the bump commit `f6082b80` and the CHANGELOG of that day, and
  **a check now requires the notes to run down without a gap from the current version to 5** (no check read these notes before,
  so a missing one never turned anything red).
- **Ledger I-091 — per-route guards moved to router defaults.** **24 of the 31 unused `Depends` parameters were removed**
  (`settings` 16, `public` 5, `plugins` 1, `render` 1, `auth` 1). A router defaulting to `_user_manager` was added in `auth`
  and one defaulting to `_current_user` in `public`, and the routes that require authentication moved onto them.
  **The remaining 7 are the admin-only routes in `plugins`, whose guard is stronger than the router default.**
  **No authentication or authorization result visible to a user changed** (95 routes, 6 public, both unchanged).
- **Ledger I-069 — checks were added for the animation export paths nothing read.**
  That the intermediate frames of `fade_white` move from red through white to blue; that an intermediate `slide` frame holds the
  current frame on its left half and the next one on its right; the 4K / 8K heights (2160 / 4320) and transition steps (4 / 2);
  the 600,000,000 encoded-pixel limit at its boundary and one pixel over; the 404 when no history item exists and the 409 when a
  work has no saved SVG. **No product code was changed.**

**Checks:** **server 3,150 passed / 31 skipped** (merged tree, 7m44s), **cli 224 passed**,
**web 275 passed, `check` 257 FILES / 0 ERRORS / 2 WARNINGS**, **ruff clean**,
**frozen corpora byte-identical** (**with the generators actually run**), **`check_docs.py` passes**.
**15 new checks** (12 server, 3 web). **The 257 is last cycle's 256 plus `+layout.ts`; `*.test.ts` files are not counted.**

- **All 8 perturbations were re-applied on the accepting side, and all 8 turned the named acceptance check red**
  (the implementer was a different model, so nothing was skipped).
  **The SSR perturbation is the one whose red count differs from the implementation report** (1 reported, 2 measured) —
  the whole web suite was run here, so the `T-15` meta gate came along. The named check goes red either way.
- **What was not done (a deviation by the implementing session):** **I-090 did not do what the ledger asked** — moving
  module-level state into a per-request context. Turning SSR off prevents the same accident by another route, and
  **the 11 module-level `$state` files are untouched.**
- **Three ledger claims disagreed with the code** (an entry records what was observed the day it was filed, not what the code is now):
  **I-230**'s "the bump cycle moved only the version number" is wrong — `f6082b80` also moved **42 reference corpus entries, the
  Android reference, and the reference tests**. **I-200**'s line 832 is now 949. **I-091**'s "25 can be consolidated" is now 24,
  with a different breakdown, because the route layout changed.
- **Nothing was looked at on screen.** This version contains a change to how the UI looks (I-202) and a change to the rendering
  boundary (I-090), so **it needs one look at the real screen after deployment.**

### v2.13.16 — The page is never blank while it boots (Build 903, 2026-08-13, ledger I-235)

**This closes the cost of `ssr = false` from v2.13.15.** The shell's HTML was empty, so
**the screen stayed white until the app had been built** (`app.html` set no background at all, so the
browser's default white showed through).

- **A curtain now lives in `app.html`.** `html`, `body`, and the curtain are painted with the dark
  `--bg`, and the curtain sits **before** `%sveltekit.body%` and covers the viewport.
  **It is painted from an inline `<style>` alone, so it waits on no external resource.**
- **The curtain is dismissed without JavaScript** — one CSS rule,
  `body:has(main) #boot-curtain { display: none; }`. **`app.html` contains no `<script>` at all.**
- **Note that the wait itself did not shrink.** What shrank is the time during which nothing is
  visible: **the time until anything appears went from a median of 712 ms to 106 ms**
  (measured against the development server, 6 samples per arm).
  **That is faster than the 172 ms of putting SSR back** — the curtain waits on no subresource.
- **A user on the light theme moves from the dark curtain to a light screen.**
  The theme comes from the user row's `ui_theme`, which the shell cannot know.
  **This was not confirmed on a real screen** (it is read from the wiring).

**Checks:** **server 3,150 passed / 31 skipped** (merged tree, 7m47s), **cli 224 passed**,
**web 279 passed** (4 new), **`check` 257 FILES / 0 ERRORS / 2 WARNINGS**,
**`lint:i18n` 1050-47-0-0**, **ruff clean**, **`check_docs.py` passes**.

- **All 4 perturbations were re-applied on the accepting side and all 4 matched the contract's
  prediction of 2 failures each** (the named acceptance plus the web meta gate `T-15`).
  The implementer was a different model, so nothing was skipped.
- **A hole in the checks was closed during acceptance** — **`T-31` compared the `html, body`
  background against a literal copy of `#171716`.** With that, **moving the canonical `--bg` reddens
  only `T-33`, and once the curtain is fixed the shell's `html, body` stays green on the old colour.**
  **Both now read the value from `+page.svelte`, confirmed with two perturbations:** changing
  `html, body` alone reddens `T-31` (what the literal used to guard), and **moving the canonical
  `--bg` reddens both `T-31` and `T-33`** (what the literal used to let through).
- **Three frames of the screen were captured in the previous cycle** (`cli/out2/902-v2.13.15-ssr-ab/`):
  the curtain, the app, and the white. **The deployed screen has not been looked at yet.**

### v2.13.17 — A mark the description called small is small whoever wrote it (Build 904, 2026-08-13, ledger I-234, ddl engine 16)

**The same description produced marks four times apart depending on which layer wrote them.** When
Stage 2 writes a circle and leaves the radius empty, `_coerce_instruction` fills it from
`PRIMITIVE_SPECS` with **0.15** — a number that reads not one character of the description. Yet
**when coerce writes the mark itself it does read the clause and answers 0.038.** So "place three
small circles" drew large circles exactly on the runs where Stage 2 omitted the size.

- **The fact that a size was omitted now travels as far as the place that fills it in.**
  `_with_stated_size` runs on the instruction the model handed over, **before the defaults erase the
  difference between a size omitted and a size stated**, and fills an empty radius or ellipse size
  from the one clause that names that primitive.
- **Both the values and the two readers are borrowed from `_fallback_instruction_from_clause`** (no
  second table, no new constant). **That is the whole claim**: the two answers cannot drift apart
  again without drifting together.
- **The rule decides per clause.** For "place three small circles. Put one square." only the circle
  becomes 0.038; the square keeps its default. **Where two clauses fit, it fills nothing** — the
  description does not say which mark it is talking about.
- **A size the model stated is never overwritten.** A circle with radius 0.3 stays at 0.3 even when
  the description says "small circle", and **a clause that states the value ("a small circle of
  radius 0.02") gives 0.02, not 0.038.**
- **The `INKU_COERCE_DISABLE` path repairs it too** — **being faithful to a size the description
  stated is not a matter of style**, for the same reason the two grid branches already run there.
- **The 0.15 default in `normalize.py` did not move.** It remains the answer for a description that
  states nothing (moving it would move all **235 works** on that side).
- **Measured against production (2,974 works): 82 works / 108 marks** (41 circles / 67 ellipses).
  **⚠ The 55 works / 78 marks estimated when the contract went out counted the author's `ddl`** —
  what production hands coerce is the **`expanded_ddl` from Stage 1.5**, and counting that gives
  82 / 108 (see ledger I-237).
- **`ddl_engine_version` 15 → 16.** Four cases added to the reference corpus, **45 → 49**
  (`b_coerce` 26 → 30). **`changed_from_previous` holds the four new names and nothing else, so the
  45 carried-over cases are byte-identical** — no branch name was added to `branch_report`, unlike
  engines 11 and 15, where adding one moved every case.
- **The Android `ddl-engine-16/` fixture was baked as well. ⚠ No Kotlin test reads it yet**
  (`ReferenceCorpus.kt` pins `ddlEngineVersion = "7"`; the lag is ledger I-217).

**Checks:** **server 3,161 passed / 31 skipped** (merged tree, 8m13s; **the +11 is one new file**),
**cli 224 passed**, **ruff clean** (server / cli), **`lint:models` 68 checks**, **frozen corpora
byte-identical** (`check_frozen_corpora.py`), **Android JVM 288 tests / 0 failures**,
**`check_docs.py` passed**.

- **The implementer was the same model (Opus 5), so the nine perturbations and the full mark it
  measured on the branch were not measured again.** What the accepting side ran is the tree nobody
  had run: the seven surfaces of the merge.
- **All nine perturbations were applied on the branch and all 11 acceptances went red under at least
  one of them** (none is vacuous). **The implementation strengthened the contract in two places**:
  a second limb for ellipses in T-5 (the contract's wording alone lets P-3 through), and T-10 as a
  re-run of `coerce_score` compared against the digest rather than a read of the frozen bytes (which
  would not redden when the production code is broken).
- **⚠ One error was found in the table the contract called "measured and frozen on the issuing
  day"** — it listed the cloudform values as square / triangle (no effect on the implementation; see
  ledger I-238).
- **⚠ The size predicate still has a blind spot** — it does not read "極細" (extra-fine) or "細い縦線"
  (thin vertical line). The word table is shared with the default-size side, so it cannot be widened
  alone (see ledger I-236).
- **⚠ Two tables beyond the version markers had gone stale** (both fixed this cycle) — the corpus
  table in `render-engine-history` still said **drawing `render-engine-30/` 553 (7 SVG)** and
  **DDL `ddl-engine-13/` 40**, where the measured values are **`render-engine-32/` 582 (13 SVG)**
  and **`ddl-engine-16/` 49**.

### v2.13.18 — Eleven items decided in conversation (Build 905, 2026-08-13, ledger I-157)

**Eleven items, each pointed at by the author and fixed in the order they were decided.** The branch
is twelve commits and is kept unsquashed: two pairs **add a row and then remove it under the author's
ruling**, and one is **the repair of a gate its own perturbation found vacuous**.

- **The eleven `Surface` words in the saijiki now carry a drawing and a note (in both languages).**
  Before, all eleven fell back to one generic line, and **Surface was the only one of the eleven
  categories missing entirely.** **All eleven drawings share the same outline; only the inside changes.**
- **The generation-info drawer gained a Sketch (Stage 0.5) section.** Before, the word "sketch" did
  not appear once in `CanvasPanel`. **This is the record of the work on screen**, not the working copy
  the description panel shows for the next painting.
- **A row was added for the colour words this work was actually drawn in.** `render_color_map` was
  already being read to decide "no record" while the value itself was thrown away.
- **⚠ Two rows were added and then removed under the author's ruling** — the sketched prose (the
  description panel already has it, and on long works it pushed interpretation and performance out of
  view) and the colour catalogue's tagline (a constant of the catalogue, not a fact about the work).
- **The two drawers now behave alike**: the saijiki drawer **closes when you press outside it**, and
  the generation-info drawer **is revealed from the right edge over 0.25s**. Each behaviour already
  existed on the other drawer.
- **The settings dialog opens either `Standard` or `Detailed`.** Only `Detailed` shows the `Plugins`,
  `Limits`, `Unread Word Ledger` and `Other (server)` tabs. **One new module, `settingsDetail.ts`,
  holds the tab names, and both the tab bar and the guard on the body read that same table** — if only
  one of them knows, what remains is either **a panel nothing can reach** or **a button that does nothing.**
- **The rail's UI-mode icon was redrawn and the menu reordered to match it.** **The old icon drew the
  same picture for all three modes** (a frame and one vertical bar), and **its 4×2px dot was invisible
  at the 22px it is displayed at.** **Now the number of dark bars is the mode** (simple 1, custom 2,
  full 3) **and the menu follows that order** (it used to read simple / full / custom, with the middle
  amount last). **Three designs were compared at full size and A was chosen.**
- **Ledger I-157: a redraw is the performance that was saved.** All four paths — the non-`display`
  profiles of `GET /api/history/{id}/svg`, the web export, the web replay, and the CLI's non-display
  export — **now hand over both seeds the row carries.**
  **⚠ What is promised is not "the same picture as the one saved" but "the difference is only how far
  the engine has moved on"** — principle 7 keeps no past version, so identity cannot be promised. **The
  dropped seed was a second difference stacked on top of the version's.**
- **⚠ The bytes of the non-`display` response of `GET /api/history/{id}/svg` change** (route, keys and
  shape do not). **It is not that the same input now returns a different picture; it is that it returns
  the right one.**
- **⚠ Two i18n keys that existed at the base commit were removed**
  (`provenanceLabelCatalogSub` / `provenanceHintCatalogSub`). **Their absence is checked by `T-41`
  across the Japanese pack, the English pack and the type.**

**Checks:** **server 3,165 passed / 31 skipped** (merged tree, 7m43s), **cli 225 passed**,
**web 332 passed / 0 failed**, **`check` 259 FILES / 0 ERRORS / 2 WARNINGS**,
**`lint:i18n` 1057 / 47 / 0 / 0**, **ruff clean**, **`check_docs.py` passed**.
**Every increment matched the branch's own report one by one** (server +4, cli +1, web +53,
`check` +2, `lint:i18n` +7).

- **The implementer was the same model (Opus 5), so the 26 perturbations and the three numbers it
  measured on the branch were not measured again.** What was run is the merged tree's seven surfaces.
  **⚠ 26 perturbations, none of them vacuous.**
- **⚠ The base commit was four versions old and four files overlapped with the main side**
  (`CanvasPanel`, `SaijikiDrawer`, `SettingsModal`, `+page.svelte`; the main side was ledger I-202's
  shared button styles). **A clean merge is not proof of a correct one, so both sides' additions were
  counted by name**: **no component-local base CSS came back** (I-202's removal holds),
  **`:global(.ghost-btn)` is there**, and **the branch's `data-saijiki-toggle` and `settingsDetail`
  are alive.**
- **⚠ Four tests appeared to have disappeared; all four were main-side additions** the old base did
  not have. **The branch deleted no test.**
- **⚠ The acceptance numbering collided with ledger I-235**: both started from `T-29` and took `T-30`,
  so the web tree now holds two sets of `T-30`-`T-33`. Nothing asserts uniqueness, so **nothing goes
  red**, but it reads badly.

### v2.13.19 — A repeated unit can be more than one mark (Build 906, 2026-08-13, ledger I-143, render engine 33 / ddl engine 17)

**Every arrangement this engine could repeat was a single instruction.** A pair placed by a saijiki plugin --
an arc, and the arc touching it at both ends -- therefore had to be handed over as **every resolved pair in
full**, and **the second mark of each pair touched whichever mark happened to precede it** rather than its own
partner.

- **`Arrangement.group_size` says how many consecutive instructions one repeated unit spans** (default 1).
  **The renderer copies the whole span first and resolves each copy's relations within it second** -- that
  order is what makes the relation local. A member is carried by the transform its head received: the rotation
  delta about the head's anchor, the scale its extent was given, and the cycled colour where the head has one.
- **The document plugin hands the API one prototype pair plus `count=N / group_size=2`.** **The public
  expansion did not move by a byte**: `instructions` still holds every resolved pair, and the DDL text is the
  same.
- **The whole-work budget counts `count * group_size`, and the instruction ceiling does not cut a unit in
  half.**
- **⚠ `group_size` is excluded from serialization when it is 1**, so **every stored Score reads and draws
  exactly as it did.**
- **The same decision was ported to Android** (`android/VERSION` is `2.1.4-android.28`).

**Two findings from acceptance, both repaired** (author's ruling, 2026-08-13):

- **⚠ Nothing observed the feature at all.** Reverting the one line where the plugin's compact form enters the
  Score (`render.py`) left **the whole server suite green at 3,170 passed** while production would carry no
  composite whatsoever. **A test that walks the API merge point was added.**
- **⚠ A span that did not fit under the ceiling emptied the instruction list** (measured: ceiling 2, span 3,
  zero instructions left, where the old `group_size=1` shape kept two). **The span is now dissolved and the
  work is drawn up to the ceiling** -- a work with nothing in it is not a smaller work. **The limits are
  settings**, so what the ceiling drops at that merge point is now recorded in the response's
  `render_limit_notes` (**⚠ no screen reads that key yet, in web or in cli, so the drop still does not reach
  the reader**).

**Corpus:** **the drawing corpus opened group H and grew by four to 586** (4 moved, 582 unchanged). **The DDL
corpus stays at 49 and all six part C cases moved**, because `score_instructions` joined what is frozen (A's 13
and B's 30 are byte-identical). **⚠ Every case above H holds a score of exactly one instruction, so before
these were added the corpus could not see this change at all.**

**Checks:** **server 3,173 passed / 31 skipped**, **cli 225 passed**, **ruff clean**, **frozen corpora
byte-identical**, **Android JVM 289 tests / 0 failures**, **`check_docs.py` passes**. **The implementation was
Codex (GPT-5), a different model, so not one check or perturbation was skipped** -- **six perturbations** (the
contract's two plus four added in acceptance) matched prediction **by name in all six**. **T-7, the real
product path, was reproduced with a local server against the NIM key through `inku-cli`** (no fallbacks).

- **⚠ The manual's 13 version markers still read v2.13.17 / Build 904** although the previous cycle's revision
  history (v2.13.18 / Build 905) states that it updated them. They are aligned here.
- **⚠ The full-run recorder was writing a 満点 for a red run** (`record_full_run` in `cycle.sh`): the summary
  line still reads "N passed" when something failed, so **3,172 passed had been recorded as the score of a
  commit the tree was never green on**. It now records nothing when the run holds a failure, and the bad row
  was removed. A perturbation confirms zero rows on red and one on green.

### v2.13.20 — A fill is a surface word like the other eight (Build 907, 2026-08-14, ledger I-227, ddl engine 18)

**A description could say "fill" and the inside of the drawing stayed empty.** The saijiki's *omote* names
how the interior of a closed shape is in nine quality words, and **eight of them landed in
`surface.texture` while the ninth, 塗り (fill), landed in the boolean `filled`.** Measured against a live
model on 2026-08-13, the destination field was the only thing that decided reach: the words that go to
`texture` arrived 12 of 14 times in both languages, while a fill through `filled` arrived **0 of 14 in
English and 2 of 4 in Japanese** — and both Japanese hits rode a duplicated second instruction.

- **`SurfaceTexture` gains `solid`, and the saijiki gives 塗り `score_value="solid"` and 空 `"none"`.**
  All nine quality words now map to the enum (`texture_for_surface()` joins `weight_for_surface()` and
  `color_for_surface()`; the two density words are excluded **by name** — excluding "whatever has no value"
  would quietly pass a quality word whose value was forgotten).
- **`filled` stays.** All three reasons measured true: the declaration order is frozen (none of
  `Instruction`'s 25 fields moved), saved works carry it, and coerce raises it in four places of its own.
- **A coerce branch, `_with_fill_as_a_surface_word`, derives each way of saying a fill from the other** —
  `texture="solid"` gives `filled=true` so every reader that only knows the boolean still draws it, and a
  `filled=true` with no surface of its own gives `texture="solid"` so works already saved say their interior
  in the vocabulary new ones use. **It does not fire on lines or arcs**, it is wired into **both exits**, and
  it runs on the `INKU_COERCE_DISABLE` path too — whether a work can be drawn is not a question of style.
- **⚠ `solid` is folded out of the performance seed.** Without that, the moment the branch adds a `surface`
  to a saved `filled=true`, **the stroke seed is redrawn for every filled closed shape in all 2,972 works in
  production.** It follows the rule `_variation_seed_fields` already uses for variations that are never
  performed. **No existing byte moves: not one Score holds `solid` today.**
- **`fill_is_asked_for()` now lives once in `schema.py`, read from three places** (the renderer's fill, the
  governor that tempers oversized filled shapes, and the one that enlarges tiny unfilled particles). Without
  it the new way of saying a fill would slip past the governor as a page-filling black circle.
- **Stage 2's four mapping lines are rewritten and one `面: 塗り。` / `Surface: flat.` example pair is added.**
  **Two existing filled-circle examples that still taught `filled=true` were brought to the same form** — a
  table stating the new rule while its examples show the old one is the internal contradiction this prompt
  has been fixed for before. **Stage 1's fixed phrases are untouched**: the DDL still reads `面: 塗り。`.
- **The drawing does not move.** A Score with only `filled=true` and one with only `texture="solid"` emit
  **byte-identical SVG**.
- **Reference corpus `ddl-engine-18` is baked.** `changed_from_previous` is **30** (all of `b_coerce`), but
  **only 3 cases move their Score** (five closed-shape instructions); the other 27 gained one branch-report
  key. The 13 expand and 6 plugin-expand cases do not move at all, and a second generator run is
  byte-identical.
- **The Kotlin prompt copy and its fingerprint were brought along in the same commit** (`WebDdlSpec.kt`'s two
  Stage 2 constants and `prompts.json`). **No server test reads that fingerprint and CI never runs Android**,
  so this is a surface that rots silently. `android/VERSION` is stamped **2.1.4-android.29**.

**Live-model measurement (reported, not an acceptance; full run in
`cli/out2/906-v2.13.19-fill-as-a-surface-word-reach/`):** `面: 塗り。` reached **`solid` 3/4**, up from
`filled` 2/4 at Build 903 — and where the two earlier hits rode a duplicated second circle, **all three here
are a single circle**. The control `面: 薄墨。` reached `wash` 4/4. **⚠ English `Surface: flat.` was 0/4**,
below the issuing side's prediction of 5–8 of 8. **The shape of the failure changed**, though: at 903 the key
was sometimes absent, while here all four answers write `surface` and choose the default `"none"` inside it —
**the destination field is reached; the value chosen is different.** **⚠ Measured with the production hard
timeout lifted** (`INKU_STAGE1/2_HARD_TIMEOUT_SECONDS=900`; 7 of 12 runs exceeded 120s, median 133.3s), with
**zero fallback compositions**. That fact is itself material for ruling on [I-227].

**Checks:** **server 3,190 passed / 31 skipped** (+17 = 16 new acceptances plus one synthesized coerce golden
case), **cli 225 passed**, **web 332 passed**, **ruff clean**, **frozen corpora byte-identical**, **Android
JVM 289 passed / 0 failures**, **`check_docs.py` green**. **Thirteen perturbations were applied through
`perturb.py`**, each restored byte-identically, with prediction and measurement reported side by side.
**⚠ P-4 (dropping only the reverse derivation) did not redden T-6** — the renderer treats `filled` and
`solid` as the same performance, so the reverse derivation is **redundant for drawing**; what has power is
T-5, which measures how the Score says it, and the readers downstream of it (replay of saved works, Android,
any client that only knows the boolean).

- **What acceptance measured** (the implementation was the same Opus 5, so numbers already measured on the
  branch were not re-measured): **all eight forbidden targets show 0 files** (`android/VERSION`,
  `APP_VERSION`, `web/BUILD_NUMBER`, `ServerScoreCoercer.kt`, `interpreter.py`, `ddl-engine-17` and earlier,
  every render corpus, `cli/out2/903-*`); **`Instruction`'s 25-field order is byte-identical**; **the branch
  tree and the merged tree hash the same** (`8337bac2`); and **the two tests that vanished by name are
  renames whose claims survive** (with 塗り and 空 carrying values, "the four words with no value" became two,
  and only `paper_grain` is subtracted from the enum).
- **The API-surface exception is declared narrowly.** `SurfaceSpec` gained no property, so a property-set
  comparison sees nothing; the guards now name the added enum value and assert none was removed.
- **Three ledger entries:** **[I-248]** (Android holds two copies that cannot choose `solid` — the
  `ServerScoreCoercer.kt` allowlist and the Score schema in `ServerScoreSchemaJson.kt`), **[I-250]**
  (`sync_android_prompts.py` measures the main checkout even when run from a worktree, printing a false
  green), and **[I-251]** (`texture_for_surface()` has no reader yet; `carriage.py` is the natural one).

### v2.13.21 — A batch that stopped part-way carries on from where it stopped (Build 908, 2026-08-15, ledger I-257)

**Three items, each pointed at in turn by the author.** The branch is three commits and **has not been
folded**. **⚠ Nothing in this round was seen on screen** — the browser extension answered "not connected"
all three times, so the button's position, the list's height, its scrollbar and the numbering after a resume
have passed no one's eyes.

- **Batch description history now keeps fifty** (it kept twenty). **The limit lives on the server** and cut
  on both the read and the write, so raising it in the web alone never arrived. **Lowering it again drops
  the tail that was already saved.**
- **The dropdown was replaced by a list of our own.** A native `<select>` **cannot be given a popup height
  in CSS** (the browser decides), so it could not satisfy "at most half the window, scroll if it does not
  fit". It is now a `role="listbox"` list that **closes on an outside click and on Escape**.
- **`Resume where it stopped` sits to the left of `Paint`.** Pressing it paints **only the lines that have
  no work yet**, **keeping the line numbers of the original text**. It is **not "everything after the last
  line painted"** — a line that failed mid-run would make that repaint the finished ones behind it. **The
  button appears only when the newest batch work is not the last line of the newest saved description.** The
  match is made on **both the number and the description** (the number alone calls an unrelated run
  "unfinished" once the description has been shortened).
- **The conditions for a resume are read from the last work actually painted** (models, color catalog,
  sketch, wild, canvas). **A condition with no record is not invented** — a work without `render_wild` is
  not "wild was off" but **older than that flag**, and writing `false` would resume under different
  conditions.
- **[I-257]: a work now records how its color catalog was asked for** (`history.catalog_mode`). **Until now
  the row kept only the resolved id**, and whether the run had asked for `choose from the description` was
  **recorded nowhere** — resuming a batch that ran on `auto` pinned it to whatever catalog the last line
  happened to resolve. **⚠ It is not part of the render hash** — putting it there would rebuild the identity
  of every saved work. **Existing rows stay NULL, and that is correct** (NULL means "not recorded", not "was
  not `auto`").
- **⚠ Two senders that save without writing `catalog_mode` remain**: `cli refine save` and the web's demo
  save. **Both write NULL.** The batch resume path goes through neither.

**API surface:** **no route added, removed or renamed; no operation moved.** Two schemas changed
(`HistoryItem` and `HistoryPostBody` each gained `catalog_mode`; optional and null by default, so **clients
that do not send it pass as before, and the key disappears from the response when it is null**). The
database gained one column, `history.catalog_mode` (VARCHAR, nullable), through **the existing migration
that runs at startup**.

**Checks:** **web 357 passed / 0 failed** (+25), **cli 225 passed**, **server 3,193 passed / 31 skipped**
(+3), **ruff clean**, **`npm run check` 260 FILES 0 ERRORS 2 WARNINGS** (the two warnings are the existing
a11y pair, unchanged in place and in count), **`lint:i18n` 1058 / 47 / 0 / 0**, **`lint:models` 68 checks
passed**. **Seventeen perturbations** were applied (eleven for stages 1 and 2, all of which fired; six for
stage 3). **⚠ A5 in stage 3 was a miss** — it changed **only the whitespace** in the column declaration, and
the acceptance's regular expression is tolerant of whitespace, so it passed through in letter and in
meaning. **That tolerance is itself right** (formatting should not redden anything), but it left the line's
discriminating power unmeasured, so **A6 (removing the column itself) was added with its prediction frozen
first**, and it reddened as predicted.

- **What acceptance measured** (the implementation was the same Opus 5, so numbers already measured on the
  branch were not re-measured): **the branch tree and the merged tree are byte-identical** (`dfa266b8`);
  **`api-surface-baseline.json` differs by three lines** (two schemas and the digest — **no route and no
  operation moved**); and **the three frozen guards were declared to, not regenerated**
  (`test_the_card_only_adds_one_route.py`, `test_the_acl_only_adds_to_the_api_surface.py`,
  `test_the_groups_decide_what_you_may_do.py` — **their claim that nothing else moved by a single byte still
  stands**).
- **⚠ The `server/` line was crossed twice** (the contract listed it as untouched). **Both crossings were
  reported before the work and ruled on by the author** — one constant in stage 1, one column and eight
  places across five files in stage 3.
- **One ledger entry, resolved in the same round:** **[I-257]** (filed by acceptance; the author chose
  option B and stage 3 implemented it).

### v2.13.22 — The ground is a support you can name (Build 909, 2026-08-15, render engine 34 / ddl engine 19)

**The ground had four materials — paper, washi, ink-wash ground, charcoal ground — and it did not arrive
from the description at all**: `washi` appeared in **0 of 3,086 production works** and **0 of the 2,125
measured ones**. **There are seven supports now, and a new saijiki category `じ` lets a description name
one.**

- **The saijiki gained `じ` (grounds)** — paper, washi, ink-wash ground, charcoal ground, **canvas**,
  **drawing paper**, mezzotint. `GroundMaterial` is eight values (`plain` plus the seven).
- **All seven are tiled as a `<pattern>` and use no `<filter>` at all.** Through engine 33, `display`
  alone drew a `feTurbulence` rectangle while the other two profiles scattered grains. **The same Score
  drawn under all three profiles now gives a ground layer that matches byte for byte.**
- **The cost limit moved from a count of elements to bytes** (24 KB, author's ruling 2026-08-14). The
  engine 15 rule — a support is the character of noise, not something drawn — **stopped meaning anything
  once the 80 strokes inside a tile are written to the file once.**
- **⚠ Mezzotint is the largest in bytes (17,918 B); canvas is the largest in tiles on screen (21,626 for
  the plain weave)** — **two different quantities**, and it is the tile count that drives the Android
  cost. → **[I-256]**
- **The Stage 1 prompt was written out from three lines to eight** (both languages), **including the line
  that had been flattening washi into "paper".**
- **The bare words 紙 / "paper" were added to the trigger lists** — before that, **all eight attempts in
  both languages landed on `drawing_paper`** (the model picks the nearest value the list offers). After
  the change, `paper` appeared in Stage 2's raw answer **for the first time** (1 of 4 in Japanese, 2 of 4
  in English). **Drawing paper stayed itself in 8 of 8: the drift that was feared did not happen.**

**Measured with a live LLM (reported, not an acceptance; full text in
`cli/out2/907-v2.13.20-ground-named-by-the-llm/` and `-paper-trigger/`):** across seven materials × four
attempts in each language, **Stage 1 wrote a ground sentence all 56 times** (0 of 2,125 on the issue date).
**`canvas.ground` survived into the final Score 18 of 28 times in Japanese and 16 of 28 in English, so what
drops it is Stage 2 alone.** **⚠ Two of the eight controls that asked for no ground got one** — Stage 1
wrote it, and `_enforce_ground_literal_gate` only drops a ground Stage 2 invented, so it passes through.
**⚠ Measured with the production hard timeout lifted** (600–1800s). **Fallback compositions: 1 Japanese, 11
English, 2 controls.**

**Checks:** **server 3,224 passed / 31 skipped**, **cli 225 passed**, **web 357 passed**, **Android JVM 578
passed / 0 failures** (289 each for debug and release), **ruff clean**, **`npm run check` 260 FILES 0
ERRORS 2 WARNINGS**, **`lint:i18n` 1058 / 47 / 0 / 0**, **frozen corpora byte-identical**, **`check_docs.py`
green**. **Ten perturbations, plus three re-applied after two gates were given discriminating power.**

- **⚠⚠ Acceptance rebaked the reference corpus.** **The `render-engine-34/` the branch delivered did not
  reproduce from the branch's own commit**: **6 of 588 cases** — every one of them a `paper` ground —
  **differed by three bytes**, and the manifest recorded the branch point `f7933235` as the commit it was
  baked from. **It was baked before the drawing work was finished and never baked again.** Acceptance
  removed the directory, baked it again, and confirmed **the second run is byte-identical** and
  **`changed_from_previous` is the same 13 cases**. **`check_frozen_corpora.py` is a check the report never
  names.**
- **⚠ The merge conflicted on `api-surface-baseline.json`** (both this round and v2.13.21 regenerated it).
  **Neither side was picked: it was regenerated from the merged code**, and the schemas that moved were
  confirmed to be exactly the union **`{HistoryItem, HistoryPostBody} ∪ {CanvasGroundSpec}`**, with **no
  route and no operation moved**.
- **⚠ Nothing at or below `server/reference/render-engine-33` and `ddl-engine-18` moved** (all ten entries
  of the contract's forbidden list show zero files).
- **⚠ Four tests vanished by name: two are renames whose claim got stronger**
  (`non_display_profiles` → `every_profile`), **and two are engine 15 rules that expired** (the test that
  measured the inside of the filter, and the element-count limit).

---

### v2.13.23 — A drawing says what it is made of (Build 910, 2026-08-15)

**The provenance drawer printed one number for weight: the size of the SVG.** Bytes are the total, not
the composition. The two largest cases in the reference corpus are **224,749 B with 158 objects** and
**222,230 B with 680 objects** — **the same 220 KB made of four times as many shapes**. What inflates a
drawing is not the number of shapes but **how many points a single polyline carries**. This release adds
two rows to the drawer and prints **three quantities side by side: bytes, objects, points**.

- **One definition of the count.** The new `web/src/lib/svgWeight.ts` (`measureSvgWeight()`) is a
  one-to-one port of `measure()` in `no-git-sync/scripts/svg_weight.py`, the script that measures the
  trend (objects = tags other than the five containers `svg` `title` `desc` `metadata` `defs`; points =
  whitespace-separated tokens in `points` plus numbers inside `d` divided by two; bytes = UTF-8 length).
  **If the number on the screen and the number in the trend were counted differently, neither could be
  used.** **⚠ It counts the `result.svg` string, not the DOM** — `querySelectorAll('*')` counts another
  quantity (no exclusions, and comparison views hold several copies of the same drawing).
- **The byte row now derives from the same function.** The row, the i18n key and the rendered text are
  unchanged; leaving the `TextEncoder` line would have kept **two definitions of bytes on one screen**.
- **History works too**, with no new wiring. `HistoryItem` carries no `svg`, so these three rows read
  `result` instead of the `statusHistoryItem ?? result` shape the other rows use.
- **Wording.** Two hint keys were added in all three of `ja.ts` / `en.ts` / `types.ts`, and `GLOSSARY.md`
  gained a row for **SVG objects / SVG points** (with ~~elements~~, ~~nodes~~ and ~~vertices~~ listed as
  translations not to use, and why).
- **Acceptance `T-67`–`T-71`, split into 14 tests** (new `web/src/lib/svgWeight.test.ts`).
  **The expected values in `T-71` were not counted by hand** — the fixture string was fed to
  `svg_weight.py` itself (`bytes=702 objects=10 points=14`).
- **All five perturbations were applied**: 14 predicted, **20 measured**. **The gap of six is two
  meta-gates** — **`T-15` runs every other web test file in a child process**, so it reddens whenever
  anything else does (+1 on all five), and **`T-16` runs the i18n lint**, adding one more to `P-4`.
  **Contracts that perturb this suite should predict a flat "+1".**
- **Cost:** 1.5 ms for the largest real drawing at hand (321,053 B, 78 objects, **13,536 points**) and
  23 ms for a **synthetic** 5.13 MB built by repeating it sixteen times. It is a `$derived`, so it runs
  once per drawing. **No real work of the production p90 size (4.79 MB) exists in this tree, so
  production scale was not measured.**
- **Cross-checked against `svg_weight.py` on 3,012 SVGs**, not one — every reference drawing from
  `render-engine-10` to `34` and `ddl-engine-1` to `19`, **with zero disagreements on all three
  quantities**.
- **Verification:** `make test-web` **371 passed / 0 failed** (357 at the base, **+14 = this contract's
  acceptance**), `npm run check` **261 FILES / 0 ERRORS / 2 WARNINGS** (+1 file, the two known a11y
  warnings unchanged), `npm run lint:i18n` **1,062 strings / 47 exceptions / 0 warnings / 0 errors**.
  **`server/`, `cli/`, `shared/` and `android/` are untouched, and their suites were not run.**

---

### Android — the port measures a mark the way the server does (android `2.1.4-android.31`, 2026-08-16, ledger I-177, I-217, render engine 26 → 30)

**What the port measured a mark's size and wander *against* had been four engine versions behind the
server.** What lagged was not the fixtures but the version the port reads: `ReferenceCorpus` resolves a
fixture through a version-keyed directory, so **falling behind never turns anything red**. This version
raises the constant one step at a time, porting that step's mechanism in the same commit.

- **engine 27 — the hand swings wider.** Per-member size ±25% → **±35%**, per-member turn ±12° →
  **±27°** (`HAND_GROUP_SIZE` / `HAND_GROUP_ROT`). **Not one rule or exclusion moved.**
- **engine 28 — a mark stays on its own line.** The wander is measured against the **stroke width**
  rather than the figure's representative size (`AMPLITUDE_WIDTHS` fine 0.35 / medium 0.6 / broad 2.0;
  the 0.40 × representative clamp stays as the safety valve for figures smaller than their own mark),
  the material outline takes its offset from the **performed ink** rather than the intended geometry,
  the skip stops being a **`stroke-dasharray`** and becomes the contact field crossing a threshold, and
  a stratum is capped at **0.33 × the nominal stroke width**.
- **engine 29 — count the paper's grain on the same lattice everywhere.** The five lengths the contact
  test reads now sit on the **same six-decimal pixel lattice the SVG is written on**.
- **engine 30 — a mark keeps the shape the description gave it.** `size` goes through **one short-side
  door** (`sizePx`). **Placement arithmetic was not touched** — coordinates still scale with width and
  height, so the aspect ratio decides where a mark sits and no longer what shape it is.
- **⚠⚠ Stage 2 left one test red, and stage 3 removed it.** Only stratum-1 of
  `23_square_filled_wild` disagreed, because **`java.lang.Math.hypot` and CPython's `math.hypot`
  differ by 1 ULP on the same sum of eighty segments** (`1600.646920448216` against
  `1600.6469204482157`). That stratum alone takes its step from `total/600`, so one extra sample was
  drawn, **and the threshold — a quantile of the samples themselves — jumped to another value.**
  **This is precisely the defect engine 29 exists to close**, so it was absorbed by stage 3's lattice
  rather than chased by transcribing CPython's `hypot` into Kotlin.
- **⚠ `renderEngineVersion` stops at `"30"`** (author's ruling, 2026-08-15). **`render-engine-31`
  through `-34` are byte-identical to `-30` apart from `manifest.json`**, so moving the constant to 34
  would name mechanisms the port does not hold (31 and 32 are owed by ledger I-233).
- **⚠ Two assertions — one in the ledger, one in this file — were measured false.** **Ledger I-177 and
  this file's engine 28 entry both say the port "still resolves 27".** It does not: the constant's full
  history is **1 → 16 → 17 → 19 → 21 → 26**, and **it was never 27**. **I-217's "13 sites that read
  `size`" was 15 on the day of issue** (22 across `render/`; **8** were routed through the short-side
  door, and the completion report enumerates the 14 that were not and why).
- **Three tests that held hand-copied expectations were re-seated in the same commit as the mechanism**
  — `CornerShapeMaterialLayerTest`'s four sha256 literals became **reads of the version-keyed corpus**
  (`31_triangle_pencil` and `32_polygon_brush_thin` hold exactly those two cases at the same seed),
  `testMaterialProportionalWiring`'s claim about an `r=` that engine 28 made unreachable became a
  **positive/negative pair**, and `testEachMemberOfATurningGroupFindsItsOwnAngle`'s `±12` became a
  literal **bound to the production constant on the next line**.
- **⚠ The corpus parity checks are blind to stroke width** (measured by perturbation P-4) — the 51
  drawings are compared on `d` / `points` / `stroke-dasharray` and on class and element count, so
  **a change that moves `stroke-width` reddens none of them.** The stratum cap is held by the check
  that reads `renderer_proportional.json` and by this contract's own acceptance — **two tests.**
- **Ten perturbations, none of them a miss** (measured by the implementer; 39 red against a prediction
  of 54). **P-8 is necessarily vacuous on a square canvas and P-10 breaks the identity instead** — the
  two gates the contract seated as a pair were shown to redden under different perturbations.
- **Verification (re-run by the accepting side on the merged tree):** **Android JVM 295 passed /
  0 failed / 0 skipped** (289 at the base, **+6 = this contract's acceptance**; `testDebugUnitTest`
  alone, so nothing is double-counted) and **`test_android_reference_fixtures_are_current.py`
  4 passed**. **Not one reference fixture was rebaked** — only the side that reads them moved.
- **Eleven files, all under `android/`.** `APP_VERSION` and `web/BUILD_NUMBER` did not move and
  **nothing was sent to pentala** (`android/` is permanently excluded from every sync path).
- **Three ledger entries were filed** (unnumbered) — **`shapeBbox` has no cloudform branch, so a
  cloudform carrying a surface draws no texture on Android**; **arc length normalises the angle span by
  360 where the server does not**; and **`testMaterialOutlinePointsAndDashArrayExactParity` has seen no
  strata since engine 28** (its regex demands an exact `class="material-outline"`, and the engine 30
  corpus holds **zero** exact matches against **3,867** `stratum-N` ones — verified by the accepting
  side). **None of the three reddens anything in the frozen corpus.**

### v2.13.24 — A surface belongs to the shape that carries it (Build 911, 2026-08-16, render engine 35, ledger I-259)

**`surface: hatch` and `surface: crosshatch` were laying their lines across the whole sheet.**
A surface texture says what a shape is made of; it is not a pattern on the paper.
Until now each hatch row was drawn to the length of the bounding box's diagonal and never stopped at
the outline, so **more than six tenths of the ink it laid fell outside the shape**
(measured in pixels: circle 62.2%, triangle 84.6%, square 64.1%).
This version **clips only the ends of each row** to the outline.

- **Only the ends moved; nothing about how the rows are drawn changed** — the angle, the spacing,
  `spacing_gradient`, the per-row jitter, and the ceiling of 80 rows are all as they were.
  **A regularly drawn line stays regular, and now stays inside the shape.**
  On a concave shape (cloudform) a row never spans the hollow: each span is drawn as its own stroke.
- **No `clipPath` is used.** The clipping happens in the coordinates before anything is drawn, so
  **the `compat` profile, which uses no filters, keeps the texture inside the shape just the same.**
- **Excursion measured** (the limit is 20.0px against the short edge) —
  `hatch` goes **413.9px → 0.7px** on a triangle and **353.5px → 0.5px** on a square;
  `crosshatch` goes **423.3px → 0.7px** and **353.5px → 0.6px**.
  **The controls `wash` (11.0 / 12.3px) and `stipple` (7.1 / 3.5px) are unchanged to the first digit**,
  which is the measurement showing no other surface word was touched.
- **The spacing did not move.** For works with `spacing_gradient="none"` the spacing class holds the
  same value as the previous version, and the `coarse_to_dense` gradient still works.
  **Only the outside was removed; nothing inside was thinned.**
- **Nine of the 588 reference cases moved** (5 `hatch`, 4 `crosshatch`).
  **The other 579 are byte-identical with the previous version, and so are the six wash cases.**
- **⚠ One test came along with the version bump** — the check that a wild performance reaches the
  hatch inside a surface had frozen the **number of rows** at 39 and 78. Rows that never cross the
  outline are no longer drawn, so it is **29 and 58**. **No mark changed size; only the count fell**
  (the claim is the same, so the expectation was corrected to the measured value).
- **⚠ Two instances of "a regenerated record is not a gate" showed up** — the two acceptance tests the
  implementation wrote first **compared two manifests against each other** and stayed green under all
  seven perturbations that break the drawing. **Both now also draw with the current renderer and
  compare against the digest**, which is what gives them teeth.
- **Eleven perturbations** (the contract's ten plus one the implementation added). **One was a
  no-op**, because **the wash branch is already clipped to the outline**, so applying the same
  clipping moves no byte — not a hole in the acceptance tests, but a wire with no discriminating power.
- **Left for later (untouched here)** — that a wash reads as stripes, that `bleed` reaches past the
  outline (reaching past it is what the word means), and that a surface texture on a `line` or an
  `arc` draws no pixel at all.
- **Verification (re-measured by the accepting side on the merged tree):**
  **server 3,238 passed / 31 skipped** (3,224 at the branch point, **+14 = this contract's acceptance
  tests**; the main side touched no server file), **cli 225 passed**, **ruff clean for server and cli**,
  **frozen corpora byte-identical**, **Android JVM 295 passed / 0 failed**.
- **The Android reference fixtures gained the 64 files of `render-engine-35/` and no Kotlin source
  moved** (`android/VERSION` is unchanged). The port reads the directory for the version it declares.

---

### Android — a surface keeps to the shape that holds it, and a spread keeps its form on any paper (android `2.1.4-android.32`, 2026-08-16, ledger I-233, render engine 30 → 35)

**The port was four engine versions behind.** Of those, **engine 33 (a repeating unit is not always one
mark) was already in**, and **engine 34 (the ground as a support you can name) is still not**, so this
version moves three: **31, 32 and 35**.

- **engine 35 — a surface belongs to the shape that carries it.** Hatch rows ran the bounding box's
  diagonal and did not stop at the outline. **Only the two ends of a row are cut now** — the angle, the
  pitch, `spacing_gradient`, the per-row jitter and the 80-row ceiling are all untouched. The cut happens
  in the coordinate maths before anything is drawn, so **no `clipPath` is used at all**; a concave form
  gives several spans and each is drawn on its own, never crossing the void. **Surface paths went from 41
  to 31** (rows that miss the contour draw nothing). The port had no equivalent of `surfaceContour`, so
  building the outline was part of the work.
- **engine 31 — the ring and `at.region` go on the short side.** A ring's radius and a region's extent
  are each one length, yet x bought pixels through the paper's width and y through its height. **A
  region's centre stays proportional** and only its half-extents move — "upper right" is the upper right
  of any paper.
- **engine 32 — a path's cross-axis swing and a cluster's band go on the short side.** `margin` and
  `span` do not move. **The cluster's band is scaled after the rotation, not before** — scaling first
  turns the rotation itself into a shear. **⚠ The `pathPosition` call that resolves a cluster's centre is
  deliberately not given the paper** (R3); giving it one would make "the middle cluster sits above the
  others" mean something different on paper of another shape.
- **⚠ Two callers the compiler cannot see went red at stage 1** — `CompositeRepetitionTest` and
  `ServerRendererCloudformAndRelationsTest` reach `resolvePerformanceScore` **by reflection**, so adding
  a parameter does not fail the build.
- **⚠ Three measurements in the issued contract disagreed with the code** (not because the code moved
  after issue): ① `expandArrangement` and `expandArrangementLayout` **already took the paper** — the
  wiring was missing in three places, not five (`pathPosition`, `clusteredPosition`, `resolveAtRegion`);
  ② "nothing gates `21_hatch_computer.svg`" was false — **the parity test that walks all 51 cases sees
  it**, though it stops at the first mismatch and 21's breakage was therefore always reported as "06
  broke" (this version separates them); ③ the `wash` and `stipple` named as controls **are not drawn by
  this port at all** (the surface layer answers only `hatch` and `crosshatch`).
- **⚠ The rows the contract said to compare as `<line>` were compared as `path`** — `computer` is a
  hand-stroke weight, so rows go through the material engine. **No `<line>` exists in the fixtures or in
  the output.**
- **13 perturbations** (one of the contract's 14 could not be applied in a single line and was measured
  by reading the code instead). **27 reddenings against a predicted 29, with three misses**: **P-1** was
  the contract's own error (both hatch cases in the corpus are unrotated squares, where the bounding box
  and the contour coincide); **P-3** came from the implementation reading `computer` as a non-hand
  weight; and **P-8** (dropping the square-canvas early return) **hit nothing** — a region's `y0` does
  move by one ULP, but **this port quantises anchors to six decimals** and the rounding absorbs it.
  **The early return was kept** (there is no reason to drop what the server has, and it starts mattering
  the day quantisation goes).
- **Carried forward, untouched here** — the surface layer passes 0, 0 to `surfaceSeed` instead of the
  real indices; the ellipse perimeter exists in two forms (Ramanujan's first approximation in the drawing
  branch, the second — matching the server one-for-one — in the surface contour); and
  `renderEngineVersion` declares `"35"` while engine 34 is not in.
- **Verification (re-measured by the accepting side on the merged tree):** **Android JVM 55 classes /
  305 passed / 0 failed / 0 errors / 0 skipped** (295 at the branch point, **+10 = this contract's
  acceptance**; nothing deleted or renamed),
  **`test_android_reference_fixtures_are_current.py` 4 passed**, **reference fixtures byte-identical**.
  **`server/`, `web/`, `cli/` and `shared/` are untouched, and their suites were not run.**
  **⚠ `cycle.sh accept` counts no Android file in its test-inventory diff** (it reads `server/tests`,
  `cli/tests` and `web/src` only), so the inventory was counted by hand.
- **⚠ Neither `APP_VERSION` nor `web/BUILD_NUMBER` moved.** `android/` is permanently excluded from every
  sync path, so this cycle sends nothing to pentala.

---

### v2.13.25 — A heavy work opens without freezing the page (Build 912, 2026-08-16, ledger I-264 groundwork)

**Opening the heaviest work in production left the page unusable for several seconds.**
The work that started this is **11,068,576 bytes and 39,789 elements**; putting that markup into
the page **blocked the main thread for 3,387 ms and left 39,788 nodes behind**, which every later
layout and style pass then walked. This version fixes two things: **how much travels** and **how it
is placed**.

- **The canvas takes the drawing as an image.** Instead of putting the work's markup into the page,
  it makes a blob URL and draws it with `<img>`. **The browser rasterises it once and the page keeps
  one node.** For the same work, **blocking went from 921 ms to 681 ms and time to paint from
  1,859 ms to 17 ms** (784 px frame, blank page). **Zoom and the presentation view are unchanged** --
  both are CSS transforms on the boxes around the drawing, so it stays sharp at high zoom.
  **The URL is released when the work changes.**
- **⚠ The reason this is safe was counted across every work in production** -- across all **3,485
  works there is no `currentColor`, no CSS variable, no `<style>`, no `<script>` and no external
  URL**. An image cannot receive what the page was supplying, and the page was supplying nothing.
  1,833 works carry a `class` attribute, but those 314 names are engine provenance marks and
  **not one of them matches any CSS in the web app**.
- **Counting the trash carried a hundred drawings.** The listing call that only wants a number never
  said `include_svg=false`. **None of those drawings was ever read** -- nothing reads `trashItems`.
- **The API answers with gzip.** A drawing is text, so it goes to **26.4%** (11,068,576 → 2,917,551
  bytes at level 6). **Level 9 is 0.9% smaller for 204 ms more**, so it is not used.
  **Already-compressed types are excluded one at a time** -- a thumbnail PNG went 115,167 → 115,026
  bytes (99.9%), all of the work and none of the saving. **The `image/` family is deliberately not
  excluded as a family**: a drawing leaves as `image/svg+xml`, so a family prefix would have turned
  this off for the very body it was added for.
- **⚠ Acceptance found and fixed one regression** -- **the gzip layer was holding the progress events
  back**. `/api/paint/stream` writes a stage event as soon as interpretation finishes, and the page
  reads it to name the stage that is running. **A compressor emits nothing until it has enough**, so
  five events put **10 / 0 / 0 / 0 / 117 bytes** on the wire (the ten being the gzip header) and
  **not one arrived before the drawing was finished**. This version flushes after each event.
  **Nothing is given up** -- compression continues and the large final body still shrinks.
  **The content was never wrong; only its timing was.**
- **⚠ None of the three existing gates reddened for that regression** (the layer was there, and both
  compression and exclusion worked). **A gate that measures whether the bytes leave was added**,
  reading the ASGI messages, because the test client joins the body up and would answer the same
  either way.
- **⚠ Coordinate precision and per-element filters are untouched** -- **554,720 of a drawing's
  554,721 numbers carry six decimals** (ledger I-265), and its **24,446 filter references account for
  roughly four fifths of the time to display it** (ledger I-264). **Both are out of scope here and are
  on the ledger.** The page no longer freezes, but the wait before the drawing appears remains.
- **Production distribution** (3,485 works): SVG **median 65,768 bytes, mean 346,834, p90 814,584,
  p99 4,420,887, max 24,513,938**. **255 works are over 1 MB.**
- **Six perturbations** (five from the implementation, one from acceptance). **All six matched their
  predictions.**
- **Verification (re-measured by the accepting session on the merged tree):** **server 3,242 passed /
  31 skipped** (branch point 3,224; **+14 from main**, the engine 35 contract, **+4 from this
  version**), **cli 225 passed**, **web 373 pass / 0 fail** (371 at the branch point, +2),
  **`npm run check` 261 FILES / 0 ERRORS / 2 WARNINGS** (unchanged), **`lint:i18n` 0 errors**,
  **ruff clean for both server and cli**.

---

### Android — the port answers the same way the server does (android `2.1.4-android.33`, 2026-08-16, ledger I-262, I-263, I-267)

**The versions already matched.** `renderEngineVersion` reads `"35"`, the same as the server, and all
51 sheets of the frozen corpus agree byte for byte. **Even so, the port answered differently from the
server in three places.** **None of the three reddens a single sheet of the frozen corpus** (no case in
the 51 exercises them), so **every gate here is stated as a property** — what is measured is not "it
differs from before" but "**it is the same value the server produces**", and **each one is paired with a
control that must not move**.

- **I-262 — a cloudform gets its surface too.** `shapeBbox` had only four branches (circle, ellipse,
  square+triangle, polygon) and a cloudform fell through to `else -> null`. **A cloudform that asked for
  `surface: parallel lines` was drawn with a surface by the server and with none at all on Android.**
  **⚠ Adding the branch produced no surface lines whatsoever** — the cloudform branch **never called
  `renderSurfaceVectors` in the first place** (all ten other primitives do). The server calls the surface
  layer **outside** the primitive switch, once per instruction, so a cloudform gets one. **The call was
  wired in.** **null did mean "draw no surface", but on a cloudform the surface layer was never reached
  to see the null.**
- **I-263 — an arc is measured end to end.** Arc length is the difference between the endpoint angles,
  not that difference wrapped into 0–360. **Two of the four sites wrapped it**, so an arc drawn from
  `300°` to `20°` measured `r × 1.3963` where the server measures `r × 4.8869`. Arc length decides the
  speck count and the sample count, so **a backwards arc carried a different amount of ink altogether**.
- **I-267 — each cluster keeps its own rhythm.** The server stirs the seed per cluster before resolving
  the rhythm; the port did not stir at all, so **three clusters spaced themselves identically inside**.
  The stir is **seed xor the cluster index**, and `k=0` gives `seed xor 0 == seed`.
- **Stage 1's output was matched against the server one to one** (cloudform + `surface(hatch)`,
  `golden` 1618×1000, seed 12345) — **`path` / `polyline` / `rect` agree at 16 / 33 / 1**, and so do the
  five classes `cloudform contour-v1 stroke-engine-touch`, `contour-stroke-v1 controls-245 events-0`,
  `material-outline stratum-0`, `stratum-1`, `surface-stroke-v1 hatch-spacing-22.500`.
  **Only the byte count differs, 41,958 against 41,432**, and the difference is the number of `<g>`
  elements (server 8, Android 4). **The 33 surface lines agree.**
- **Thirteen perturbations** (P-8 and P-12 each have two sites and were split into a / b, so fifteen were
  applied and reverted; **all fifteen reverts matched their sha256**). **Not one was a no-op.**
  **Three missed their predictions** — **P-7** (predicted 2, measured 4) was written as "floating point
  may differ by 1 ULP, but predict it does not move", and **it moved**: `2πr × (Δ/360)` and
  `r × |radians Δ|` are the same mathematically, but the input to `rint` changes, the segment count
  changes, and **two corpus gates came along with it** (the contract's reason for not unifying the two
  formulas, now measured). **P-11** (predicted 4, measured 3) left T-93 green — the implementation
  extracts the rhythm **after cancelling out the cluster centres**, so stirring the centre does not move
  it; **this is not a hole in the gates** (the centre stir is measured by name in T-92, which P-11
  reddens). **P-12** (predicted 4, measured 2) **moved no existing gate at all** — specks are `<circle>`
  elements, the gate that walks all 51 sheets compares only `d` / `points` / `stroke-dasharray`, and the
  gate that counts elements walks only 10 sheets. **Of those ten, the one arc with a material layer is
  `04_arc_crayon`, whose `0→180` has the same supplement, so nothing moves.** **No gate looks at the
  speck count of a corpus arc.**
- **Carried forward (untouched here; all four are on the ledger)** — `rhythmT` differs from the server's
  `_rhythm_t` **in four places** (0.5 against 0.0 for `n<=1`; accelerando as `base²` against `base^1.35`;
  loose jitter of `0.12/max(n/8,1)` against `0.16`, a factor of 3.3 at n=20; the syncopated constants);
  a non-hand-stroke arc with `variation` emits 148 `<polyline>` points on the server and 147 `<path>`
  points here; canvas dimensions truncate where the server rounds, splitting `oban` into 666 against
  667; and the gate hole above. **T-93 measures only which seed is read, not what the rhythm does,
  because of the first of these.**
- **Verification (re-measured by the accepting session on the merged tree):** **Android JVM 56 classes /
  314 passed / 0 failed / 0 errors / 0 skipped** (305 at the branch point, **+9, this contract's gates**;
  nothing deleted or renamed; zero `^e: ` lines), **`test_android_reference_fixtures_are_current.py`
  4 passed**, **the reference fixtures did not move by a byte**. **`server/`, `web/`, `cli/` and
  `shared/` have no diff, and their suites were not measured.** **⚠ `cycle.sh accept`'s test inventory
  does not count a single file under `android/`** (ledger I-270), so the delta was counted by hand as the
  sum of `git grep -c '@Test'` (305 → 314, across 55 → 56 files).
- **⚠ Neither `APP_VERSION` nor `web/BUILD_NUMBER` moved.** `android/` is permanently excluded from
  every sync path, so this round has nothing to send to pentala.
- **The frozen prediction note was taken out of the published tree** (it lives in `no-git-sync/`;
  precedent `a5b07945`).

### v2.13.26 — The public list holds only what login needs (Build 913, 2026-08-16, ledger I-086)

**The public routes went from six to three.** What is left is `/health` (the container liveness probe,
which returns no data), `/api/info` (build and version plus developer_mode, read by the login screen),
and `/api/auth/login` (the login endpoint itself). **`/api/prompts`, `/api/color-catalogs` and
`/api/auth/config` moved behind the authorization guard.**

**They came off because every entry on that list has to give a reason that was measured.**
`/api/color-catalogs` said it was "needed to render the login screen"; the login screen was then
measured and receives no catalog at all. **What kept the route public was the startup fetch running
before anyone had logged in.** Only what logging in genuinely needs stayed.

- **server** — the two routes in `public.py` moved to an authenticated router, and `auth.py` gained one
  of its own. **`PUBLIC` is three entries now, and the live app is walked so the set of unguarded paths
  is compared against it** (`test_route_authorization.py`). **No route was added or removed**
  (`EXPECTED_ROUTE_COUNT = 95` is unchanged).
- **web** — **the tail of `login()` reads the two lists that stopped being public.** The startup fetch
  runs before anyone has signed in, so both come back 401 there and the page swallows it. **Unless
  `login()` asks again, the catalog stays on the fallback and the Prompt tab stays empty until the page
  is reloaded.** The check is **cut down to the body of `login()`** before it is matched — the page
  calls both functions in several places (`loadCurrentUser()` has the same list one function above), so
  **a match against the whole file would be satisfied by an occurrence that has nothing to do with
  signing in.**
- **cli** — `_fetch_color_catalogs` stopped opting out of authentication. **The check reads the
  credential the request actually carried**, rather than grepping the source for the absence of a flag:
  a recording stub answers the call and the headers it was sent are asserted.
- **published docs** — the public paths listed in both languages of
  `docs/architecture/server-components` were narrowed to three, and **a gate now holds that list to a
  one-to-one match with `PUBLIC`** (**both files are read, so neither half can drift alone**).

**The API surface record was rebaked** (digest `d5d312e1…` → `a925c3de…`).
**⚠ The declaration the two frozen gates take needed more than the contract's `added_params` /
`removed_params`** — **a route that carried no arguments has no "validation failed" response, and one
appears the moment the authorization dependency brings two arguments with it.** (`/api/prompts` already
had `query:lang:opt`, so it already had a `422`; only its `params` moved.) **Rather than waving
`responses` through, the declaration gained `added_responses` / `removed_responses`: only the declared
codes are removed, and everything left is compared byte for byte** — **a window that silently lost its
200 still reddens.**

- **Eleven gates** (`T-79`–`T-89`) and **ten perturbations**. **Nothing came out differently from the
  prediction** — every T that should have reddened did, and every T that should have stayed green
  (`T-85` under `P-2`, `T-79`–`T-82` under `P-4`) did. **`P-4`, which adds one undeclared query
  argument, reddens `T-83` and `T-84` and nothing else — that is what measures that the declaration
  mechanism is not a blank cheque.**
- **⚠ One kind of collateral was missing from the prediction** — a perturbation that reddens web
  (`P-5`, `P-6`, `P-10`) always also reddens **`T-15`, the metagate that runs the whole suite**. The
  contract had not said so.
- **Verification (re-measured by the accepting session on the merged tree):** **server 3253 passed /
  31 skipped / 0 failed**, **cli 227 passed**, **web 375 pass / 0 fail**, **ruff clean on both trees,
  `npm run check` 0 errors** (the two warnings are the pre-existing a11y pair), **`lint:i18n` 0 errors,
  `check_docs.py` consistent**. The deltas matched what the branch had declared, face by face
  (server +11, cli +2, web +2; **the main side was Android only, so it added none**). **The two checks
  `accept` reported as missing had gained an argument rather than been deleted**
  (`test_color_catalogs_are_served_by_api` and `test_the_catalog_list_serves_the_rename_table`;
  **each was looked up at the branch point to decide**).
- **The per-router count table in `docs/architecture/server-components` was corrected too** (measured by
  the accepting session) — **not only the "Total: 82": every row was stale, and the ten rows summed to
  exactly 82.** Counted again by running the production code: **history 12→17, settings 10→16, me 12→13,
  public 9→10, total 82→95** (the other six rows did not move). **The "default guard" column for
  `public` and `auth` was rewritten as well** — the only routes in those two routers without a guard of
  their own are **`/health`, `/api/info` and `/api/auth/login`**. **⚠ No gate reddens for that table, so
  a line saying as much now sits under it** (the canonical count is `EXPECTED_ROUTE_COUNT`).
- **⚠ The accepting session first counted four unguarded routes, against the check's three** — **the
  guard list in the throwaway scan was missing `_session_token`**, which is what `/api/auth/logout`
  carries. **What disagreed was the tool written on the spot, not the check.**
- **Carried forward (untouched here)** — **`manual/` says nowhere that these APIs need no
  authentication, so nothing in it became false** — **no list of public paths was added to it**, since
  that would be a third hand-copied copy with no gate on it.

---

### Android — the same beat, the same points, the same sheet (android `2.1.4-android.34`, 2026-08-16, ledger I-273, I-274, I-272)

**The three divergences the previous version reported and left alone** are what this one closes.
**None of them reddens a single sheet of the frozen 51**, so **all eleven gates are stated as
properties** — what is measured is not "it differs from before" but "**it is the value the server
produces**", each paired with a control that must not move.

- **I-273 — the spacing itself was different.** The previous version fixed the stirring of the beat's
  seed per cluster, but **the function that receives the seed, `rhythmT`, differed from the server's
  `_rhythm_t` in four places**: **0.5 against 0.0 for a lone member**, **accelerando as `base²`
  against `base^1.35`**, **loose jitter divided by the member count** (`0.12/max(n/8,1)` against a flat
  `0.16` — a factor of 3.3 at twenty members), and **the two syncopated constants** (`0.085`/`−0.055`
  against `0.09`/`−0.045`). **The five call sites were not touched.**
- **I-274 — a varied arc differed in its points, its phase, its ends and its element.** With
  `variation` on an arc that skips hand-stroke synthesis (`rotring`), the port drew **one point fewer**
  (`segmentCount` against `+1`), **sampled a notch off** (`i/count` against `i/last`), **jittered the
  end points** (the server pins both, to keep the touching contract), and **emitted `<path>`** where the
  server emits `<polyline>`. **All four now follow the server.** **⚠ A second function in the same file
  already agreed with the server** (the hand-stroke path's `arcPointsWithVariation`), so **only one of
  the two was changed.**
- **I-272 — the sheet itself was a pixel out.** Turning a ratio into pixels, **the server rounds and the
  port truncated**, splitting `oban` into 666 and 667. **⚠ `Math.round` would have added a second
  divergence** — Python's `round` goes **half to even**, so `vertical` (562.5) is 562, while
  `Math.round` goes **half up** and gives 563. **`Math.rint` is what went in**; truncation had been
  landing on 562 by luck.
- **Fifteen perturbations; four missed their predictions.** **P-8** (7 predicted, 5 measured): the beat
  inside a cluster sits behind `rhythmSpacing != "none"` and never reaches `rhythmT` when the spacing is
  `none`, and the parity gate that counts elements and classes stays green when only coordinates move.
  **P-9 and P-10** (+2 each): **the implementation forgot to count the two existing gates it had
  rewritten in stage 2**. **P-13** (3 predicted, 0 measured) was **a no-op**: across every integer
  `r` in 50..400 and `Δ` in 1..360, `2πr × (|Δ|/360)` and `r × |radians Δ|` **never split the segment
  count**.
- **⚠ Two measurements in the contract were wrong.** ① T-130 asked for `controls-72` on a `pen` arc
  with `variation`, but **`controls-72` is the figure without variation; a varied arc gives
  `controls-148`** (the previous version's gate held the two in separate assertions, and folding them
  into one line mixed them up — **this version measures both separately**). ② The claim that the
  previous P-7 had measured the corpus reddening when the two arc-length formulas are unified is false:
  **P-7 switched to the folded formula, which is a different thing**; unification was predicted not to
  move, **and measured 0**. **What protects the hand-stroke formula, then, is neither a gate nor the
  corpus but the fact that both forms return the same value.**
- **⚠ One existing gate had its measurement window narrowed.** With loose jitter going from `0.048` to
  `0.16`, **the first member in from each end can be pushed into `clamp01` at twenty members spaced
  1/19**, where `t` stops being affine, so the window for reading the beat moved from `j = 1..18` to
  **`j = 2..17`** (`base ≥ 0.105 > 0.08`). **The implementation had written this prediction into its
  frozen note before starting. No gate was added or removed.**
- **Carried forward (untouched here)** — **the decision of whether variation applies folds the server's
  two functions into one**: the server treats `quality: "pink"` as a blur and refuses it, the port lets
  it through, and for lines the server looks at two dimensions where the port looks at three (filed on
  the ledger). Also I-269, I-266, I-275, engine 34, the surface layer's `surfaceSeed`, and the two
  ellipse-perimeter formulas.
- **Verification (re-measured by the accepting session on the merged tree):** **Android JVM 57 classes /
  325 passed / 0 failed / 0 errors / 0 skipped** (314 at the branch point, **+11, this contract's gates
  T-121..T-131**; nothing deleted or renamed; zero `^e: ` lines),
  **`test_android_reference_fixtures_are_current.py` 4 passed**, **the reference fixtures did not move
  by a byte**. **`server/`, `web/`, `cli/` and `shared/` have no diff.** **⚠ `cycle.sh accept`'s test
  inventory does not count `android/`** (ledger I-270), so the delta was counted by hand (314 → 325).
- **⚠ Neither `APP_VERSION` nor `web/BUILD_NUMBER` moved.** `android/` is permanently excluded from
  every sync path, so this round has nothing to send to pentala.

---

### v2.13.27 — A wash is a field, not a set of stripes (Build 914, 2026-08-16, render engine 36, ledger I-260)

**`surface: wash` came out as evenly spaced stripes.**
Every sweep ran parallel at a constant pitch, no layer reached the paper between two sweeps, and
**19.9% of the inside of a square (21.1% of a triangle) was left as bare paper**. A wash has no bare
paper in it. This version **widens the sweep to the pitch and lightens it by as much**.

- **Only two quantities moved** — the sweep's width goes from 0.44–0.74 of the pitch to
  **0.88–1.48**, and the opacity factor from **0.42 to 0.22**. **The pitch, the layer count and the
  layer angles are identical to the previous version down to the last decimal.**
- **Bare paper falls from 19.9% to 0.67% (square) and 21.1% to 1.09% (triangle).** **What is left is
  a rim along the contour, a median of 2.0 / 2.2px deep** — the sweeps are clipped at the contour and
  a hand tool tapers at its ends, so only the outermost band runs thin.
- **The ink is back at the product's level** (composite mean alpha **+2.0% / +1.1%**). Closing the
  gaps darkens a wash, and the lower factor gives that back. **This was never a preference about
  darkness; it was a demand to undo the side effect of closing the gaps.**
- **None of the three rejected proposals went in** — varying the angle per sweep, scattering the
  pitch, laying a ground underneath. **None of them moved the amount of bare paper; the only thing
  that closed the gaps was the width of the sweep** (measured the cycle before). Two gates hold this
  down (the layer angles and pitch unchanged; zero underlay elements).
- **The cost is that the excursion past the contour doubled** (12.3 / 11.0px → 25.8 / 21.7px).
  **That is half of one sweep's width, and the same relation held in the previous version** — a brush
  with width crosses the rim by half of it. The absolute 20.0px used for the speck textures was
  decided by the size of a speck, so it is not applied to the wash; **the gate computes its limit from
  the product's constants** instead of writing a px by hand.
- **The reference corpus moved 6 of 588 cases** — exactly the six that carry `wash`. **The other 582
  are byte-identical to the previous version**, and **no case id is new, so all six carry
  discriminating power**.
- **⚠ One casualty of the version bump was split rather than deleted** — the test that pinned the
  previous wash claimed two things at once: that the frozen bytes agree with engine 34 (history), and
  that the current tree draws engine 34's wash (which this version necessarily breaks). **The first
  claim was kept and the name put into the past tense; the second was taken over by engine 36's
  redraw test.** **One engine 35 test was also pointed from the current manifest at engine 35's frozen
  manifest** — without that, the subject of "what engine 35 moved" silently becomes engine 36's diff
  the moment the new corpus is baked.
- **12 perturbations, none of them a miss. 55 predicted, 66 measured.** All five misses were
  *under*-predictions, one of them the shape where **a `max()` whose other side is binding cannot be
  measured by breaking this side** (halve the pitch and the brush's own thickness starts to bind).
  **Only the display-profile perturbation came in under prediction** — the generator's profile is
  `editable`, so one of the two tests expected to fall with it structurally cannot.
- **Carried forward (untouched by this version)** — hatch bleeding outside the shape, `bleed`
  exceeding the limit (going outside is what the word means), a surface texture on `line` or `arc`
  drawing not one pixel, and the defaults of `surface.density` / `surface.opacity`.
- **⚠ The 103 comment lines this round newly wrote were in Japanese, and the accepting session put
  them into English** (the 2026-07-30 ruling, reaffirmed by the author on 2026-08-16). **The 216
  Japanese lines that were already there were left alone.**
- **Verification (re-measured by the accepting session on the merged tree):** **server 3,271 passed /
  31 skipped** (3,238 at the branch point, **+18, this contract's gates**; together with main's +15
  the increments reconcile one by one), **cli 227 passed**, **ruff clean for both server and cli**,
  **the frozen corpora are byte-identical**, **Android JVM 57 classes / 325 passed / 0 failed**.
- **Android's reference fixtures gained the 64 files of `render-engine-36/` and no Kotlin source moved
  by a line** (`android/VERSION` held steady). The port reads the directory of the version it names.

---

### v2.13.28 — Each limit answers to a different authority (Build 915, 2026-08-16)

**The nine numbers in the limits tab were already split into three families.**
The families were called `How much is actually drawn`, `How a stated number is honoured` and
`Ceilings on reading and validation` — none of which **said what to look at when deciding a value**.
An administrator could not tell which numbers may follow the hardware. This version **renames the
families after who they answer to**.

- **The three families are now** **`What this machine can draw`** (capability), **`Where counting by
  eye stops`** (legibility) and **`Guards against a typing mistake`** (safety). **Each family gained a
  tooltip** saying what it should follow.
- **⚠ The load-bearing part is what must *not* be linked** — **a faster machine does not make an eye
  faster**, so **`Where counting by eye stops` must not follow `What this machine can draw`**. What
  that family holds constant is the *look* — how much ink sits in one cluster — not the threshold
  digits.
- **`max_instructions` changed families** — from `How much is actually drawn` to **`Guards against a
  typing mistake`**. **It is a runaway guard, not a statement about what this machine can afford to
  draw.** **Production has never exceeded 27 instructions (median 4), so the default of 64 has never
  bound a real work.**
- **Not one of the numbers changed.** The defaults, the effect, and what gets written into the prompts
  are all as they were.
- **The per-number descriptions gained measurements** — one grid mark costs roughly 13 KB of SVG with
  a pen and 16 KB with a thick brush, so **the default of 400 already lets one work reach 5–6.5 MB**.
- **⚠ The test inventory did not grow by one.** No new test function was added; **the existing `test_t9`
  was strengthened instead** (from one assertion to seven: **per-family membership**, **that both
  language packs carry the headings and the tooltips**, and **that the panel actually calls the
  tooltip**).
- **Verification (re-measured by the accepting session on the merged tree):** **server 3,271 passed /
  31 skipped** (the same as the previous version, for the reason above), **cli 227 passed**, **web 375
  pass / `check` 261 FILES 0 ERRORS 2 WARNINGS**, **`lint:i18n` 1,063 English strings / 0 errors**
  (**+1 from the previous 1,062**, the family tooltips), **ruff clean for both server and cli**.
- **⚠ This round closed no ledger item.** Neither the branch's commits nor the contract names one, and
  **[I-244] and [I-245] (which tabs the limits panel appears under) are a different matter and remain
  open**.

---

### 2026-08-16 — Six decimals is the specification, not an implementation detail (**no version bump**, SPEC only, ledger I-265)

**The six decimal places every number written into an SVG carries were nowhere in the SPEC.**
The only record was the implementation's docstring (`master_grid.py`) and a ruling from 2026-07-24, so
**reading the SPEC alone could not tell whether six digits were the specification or a convenience.**
The author's 2026-08-16 ruling — **no specification change; six digits are the specification** — is now
written into SPEC §19.

- **Not one byte of code or corpus moved.** Only `SPEC.ja.md` (+10 lines) and `SPEC.md` (+30 lines)
  changed, **nothing under `web/`, so there is nothing to send to pentala** (**and no version was
  taken**).
- **The reason not to lower the digits is the picture, not the byte count** — dropping a
  production-scale work to three digits **moves 19.52% of the pixels at the natural width of 1618px**.
  Keeping only the filter numbers at six digits brings that to **0.50%** (**what had been moving it was
  two filters and four numbers**). **Two digits move the picture from the coordinates alone** (17.52%
  on a fill, 48.57% on a production work) — **a coarser grid gathers points that the hand's tremor had
  scattered onto the same coordinate. What moves is not the amount of ink but where the specks sit.**
- **⚠ The filing's "14.4% together with gzip" compared a gzipped size against an ungzipped one.**
  The transport is already gzipped; **gzip against gzip, three digits is 68.1% and two digits 55.9%**.
- **⚠ The filing's "1,859ms → 533ms" cannot be attributed to the digits** — that build rounded the
  filters as well. **The main cause of the freeze is still the 24,446 per-element filters.**
- The text was written by the design session (on the author's override) and **committed by the git
  session**, since SPEC is outside standing approval.

---

### Android — A fill is one request, however it is written (android `2.1.4-android.35`, 2026-08-16, [I-248])

**"Fill the interior" can be written two ways in a Score** — as `filled: true`, or as
`surface: {"texture": "solid"}`. **The server treats the two as one request and keeps the
judgement in a single function** (`fill_is_asked_for`). The port had no such function, and on
its local path **Stage 2 could not say 塗り at all**: neither the schema it hands the model nor
the coercer allowlist offered `solid`, and **a model writes what the destination field offers it**.

**⚠ The ledger said there were two copies. Reading the same functions against the server one by
one found five.** **A ticket records what the person who found it could see.**

- **The judgement of whether an interior is filled** — written out twice, each with its own
  expression, and **both gave up the moment a `surface` key existed at all**. The server declines
  to fill only when the texture is neither `none` nor `solid`.
  **⚠ This one was already on the page before `solid` entered** — a `filled: true` shape carrying
  `surface: {"texture": "none"}` is filled by the server and not by the port
- **The performance seed** — the server normalises `texture="solid"` to `filled=true` plus
  `surface=null` before building the key. **Without it, adding the derivation re-rolls every
  stroke in every work already saved**
- **The derivation** between `filled` and `texture="solid"` (closed shapes only) was absent
- **The coercer allowlist** (nine words) and **the schema enum handed to Stage 2** (nine words) —
  the two the ticket named

**The order of the stages carries the argument.** Widening the vocabulary first would let `solid`
arrive somewhere that has neither the judgement nor the seed, which is a different kind of
breakage: **selectable but not drawable**. So the judgement went into one place, then the seed was
protected, then the derivation added, and only then the vocabulary widened — six stages.

- **The frozen corpus moves on none of the six stages** — no case states `solid`, no case states
  `texture: "none"`, and coerce is not on the corpus path. **All ten gates are therefore
  properties, each with a control beside it**
- **Eleven perturbations.** `P-11` (make the judgement always false) **is the only one the corpus
  can see** — through the five cases that state `filled: true`, **which is the evidence that the
  judgement is reached at all**
- **⚠ The prediction for P-11 matched in count but missed four names** — three read as red came
  out green and three unpredicted ones went red, and **−3 and +3 cancelled to ten**. The type of
  the miss: **the stage-6 wiring the same session had just added was not counted.**
  **A matching count is not evidence**
- **Verification**: Android JVM **59 classes / 334 tests / 0 failures / 0 errors / 0 skipped**
  (from 57 / 325 before the work: **+2 classes, +9 tests**; no existing test was rewritten).
  On the server side, `test_thinness_declaration_position.py` 7 passed and
  `test_android_reference_fixtures_are_current.py` 4 passed. **No file under `server/` was touched**
- **Left for later (not fixed here)** — **on a non-hand-drawn closed shape, nothing decides whether
  the interior is filled.** There are **eight roads** that never reach `renderBodyShape`; on those
  the judgement's value is never read and the colour `ServerRendererStyle` puts on every closed
  shape goes out as-is. **`05_circle_rotring` comes out filled when it should not be** (measured by
  the implementation session). **The 51-case parity walk compares `d` / `points` /
  `stroke-dasharray` and never `fill`, so no gate catches it.** Older than this contract, so it was
  left alone; it is ledger [I-280] (**⚠ eight is the number of roads, not the number of breaks** —
  only `05_circle_rotring` was measured broken)
- **⚠ One claim in the contract was wrong** (the issuing session's error) — it said the judgement
  "is overridden by `renderBodyShape`, so it never reaches the page", **having counted the callers
  of `renderBodyShape` but not the branches that never call it.** The implementation session found
  it before writing a line, froze it in its prediction note, and reported it
- **Numbering**: Android-only, so `APP_VERSION` and `web/BUILD_NUMBER` did not move
  (`android/VERSION` alone went `2.1.4-android.34` → `2.1.4-android.35`). **Nothing was sent to pentala**

---

### v2.13.29 — The tools stand on the drawing they act on (Build 916, 2026-08-16, 5th UI round, **5 stages**)

**The bar under the canvas is gone.**
A star, a hash, replay, provenance, the saijiki and three separate ways to get the work out
**sat in a row below the picture and acted on it from a distance**. Every one of them is about the
work on screen, so they now **stand on it** — the marks a reader puts on a work at the left, beside
the caption toggle, and the rest at the right, to the left of the fullscreen button that was
already there. **The three ways out became one door** (SVG, PNG and the share card: the choice
between them belongs inside the door rather than in front of it).

- **The DDL editor offers its words in the language of the DDL, not of the interface** — someone
  writing "a thin line" was being handed `円`. **A word taken from there goes into the DDL**, so
  offering another language is offering the wrong word. The judgement is **a one-for-one port of the
  server's `resolve_instruction_lang`**, and it **follows the typing**. **The preview's two
  sentences answer to different languages** (the author's ruling): **the prose about the effect is
  in the reader's language, the 73 examples are in the DDL's**.
- **The band above the canvas states the SVG's size** (to the left of the creation time), from
  **the same single measurement and the same single formatter the drawer uses**. **The generation
  drawer remembers where it was left, per tab** (the four ways of closing it were brought into one
  function). **Thousands separators are fixed to `en-US`** — following the interface language would
  give the same drawing different punctuation in different interfaces, and **screenshots would stop
  being comparable**.
- **Nearby works moved off the drawing and into the lineage tab** (what floated over the picture is
  a row in the flow there, and no longer needs `position: absolute`).
- **The share mark got a socket and nothing to plug into** (the author's ruling: it is [I-191]'s
  business) — **nothing is drawn today**. **A flag's presence is decided by whether the field is
  there, not by its value**: absent means the server does not know the flag, `false` means it knows
  and none was set. Coercing to a boolean **would make the mark vanish on exactly the works that can
  carry it**.
- **⚠ A ruling arrived after stages 1–4 were merged, and became stage 5** — merging the three ways
  out had **taken the share card out of the simple UI**, because **a merged door cannot be half
  hidden** and the card had joined a group that the simple UI hides. The ruling: **in a simple UI,
  show the export button as a button that calls the share card alone**. **No UI mode hides the
  export button any more**; instead of hiding it, the button **narrows what it opens onto** — it
  calls the card directly with no menu, **refuses in exactly the two cases the menu entry refuses**
  (no saved work, card already building), and **announces the card's own label**. The card is not a
  work tool: it is how a work leaves for someone else.
- **47 acceptance cases, `T-90`–`T-107`** (43 for stages 1–4, four for stage 5) and **24
  perturbations** (20 and four). **The implementation session's predictions missed in the same
  direction all 20 times — the measurement was always the larger** (40 → 52). One type: **a gate it
  had just written reached further than it predicted.**
- **⚠ A perturbation gap carried for three rounds closed here** — `T-16`, the English vocabulary
  guard, **had never been reddened, because no perturbation touched `en.ts`**. Stage 4 added two
  keys there, so one could be aimed at it: **`T-106`, `T-16` and `T-15` went red.** The gap was
  closed by measurement, not by argument.
- **Nine existing cases were rewritten** (six in stages 1–4, three in stage 5). **Only two changed
  what they claim**, both about the card's doors (**T-7** and "two doors"); the rest moved an
  expression and claim what they claimed before.
- **⚠ The `lint:i18n` baseline itself held a phantom** — the rule was **counting the language-code
  ternary `isJapanese ? 'ja' : 'en'` as an English display string**. The rule was fixed, and
  **`T-94` measures that it is not vacuous** (that such a ternary is really in the tree).
- **Verification (re-measured by the accepting session on the merged tree):** **server 3,271 passed
  / 31 skipped** (no file under `server/` was touched), **cli 227 passed**, **web 422 pass / 0
  fail** (418 on the tree of stages 1–4), **`check` 265 FILES 0 ERRORS 2 WARNINGS** (the two are the
  pre-existing a11y ones), **`lint:i18n` 1,066 English strings / 0 errors** (+3 from the branch and
  a net +1 from main), **ruff clean on server and cli**.
- **⚠ Nothing was seen on screen** — connecting needs a ruling each round, and this round's ruling
  was to move on without looking. **What most wants an eye is how the nine icons sit in the
  corners**: their size was estimated by arithmetic, and the real window widths and the dark/light
  rendering were not measured.

### v2.13.30 — A work redraws under the limits it was drawn under, and the ruler does not shrink what it was given (Build 917, 2026-08-16, ledger I-154 and I-155)

**Redrawing the same work cut it against today's settings.**
The work's row records the limits it was drawn under, and **nothing that read the row back ever used
them** — on an installation whose settings were lowered, last year's work came out different every
time it was opened. **A redraw now runs under the limits the work was drawn under.**

- **The answer says which numbers drew it** — responses carry **`render_limits_source`**, one of
  **`work`** (off the work's own row), **`settings`** (today's) and **`work_unrecorded`** (a row
  exists but recorded no limits). **`/api/render-svg` has no body to put it in, so it says the same
  thing in an `X-Inku-Limits-Source` header.**
  **⚠ The third value exists so that an old row with no record does not wear the same face as
  "drawn under the settings".**
- **A request may now carry `limits`** (`paint`, `render-svg`, `render-score`). **Each element is
  `min`-ed against today's settings** — **it cannot raise anything.** The ceiling belongs to the
  administrator, not to the caller placing the order.
- **Each of the nine limits names itself when it takes effect** — every note now begins with the
  limit's name (`represented_count_max: 600 drawn as 120`), **one line per limit at most.**
  **The web and the CLI read the notes now**: they were already in the answer and **neither side
  looked at them.** **The wording stays English and only the heading is translated**, following
  what `plugin_warnings` already does.
- **⚠ By construction the default path does not move a single pixel** — the strings written into a
  Score's `note` field are byte for byte what they were, and **the name was prefixed only on the
  copy that is pushed onto the list.** All five reference corpora stayed green and **nothing had to
  be rebaked.**
- **The plugin budget follows the setting** — until now it ran at the shipping number whatever the
  administrator had configured, **and wrote that number into its warning.**
- **⚠ The repair path's scatter-density budget ignored the setting and ran at 240** (the shipping
  value of `max_expanded_per_instruction`). **The effective limits are now threaded through it. At
  the default settings not one bit changes; on an installation that changed the setting, the
  behaviour does.** This is a **fifth** hard-coded value, distinct from the four found earlier,
  and it is filed as [I-282].
- **The three frozen API-surface guards were told, by name, which key each of six schemas gained**
  (**not a blank cheque** — the declared key is taken back out before hashing, so **a second key
  arriving in any of them is still red**).
- **Acceptance is `T-95`–`T-108`, 14 tests**, and **14 perturbations** (the contract's 13 plus one
  the implementing session added to hit the positive claim). **17 predicted items against 29
  measured** — the three misses all under-counted how many faces would redden.

**And a second ruler was shrinking what it was given.**
The per-round tool of the drawing-quality track **halved the image before it began counting** —
**burned at 1618px, it effectively measured 809px**, and **only the table's heading followed the
ruling that says measure at full size.**

- **The counting rule now lives in one place under `shared/`** — `measure_png` / `measure_dir`.
  **It never shrinks** (no `resize`, `thumbnail` or `reduce` anywhere) and **folds the pixels into a
  colour histogram first**, so it does not walk pixel by pixel.
- **`inku-cli measure-raster --in <PNGDIR> [--out <JSON>]` was added.**
  **It declares no width or scale flag at all** — **the width is decided by the burning step
  (`rasterize --width`), not by the counting step** — and **the absence is held by acceptance**
  (the declared flags are exactly four). **It takes no server flags either**: counting pixels needs
  no API.
- **The agreement with the old implementation was measured here** — **the four fixed materials match
  exactly**, and on **ten full-size works `ground` matches exactly with the other seven quantities
  within 1.42e-12** (the rounding of a differently ordered sum).
  **⚠ Shrinking has no single direction**: among those same ten, `strong` rose in one and fell in
  another.
- **`shared/pyproject.toml` now declares `pillow>=12.3.0`** — it had been working as a side effect
  of an editable install rather than because anything declared it.
- **Acceptance is `T-109`–`T-120`, 12 tests**, and **12 perturbations** (the contract's 11 plus one).
  **⚠ One perturbation was a miss** (moving a threshold from 24 to 25 changes nothing when no pixel
  in the materials falls between them). **To separate "never wired" from "the material never
  crosses that boundary", a 24 → 300 perturbation was added** — four tests reddened, so the
  threshold does run through the product's decision.
- **⚠ This tool exists to fix an evaluation document that is not in this repository, and no
  acceptance can be placed there.** **That new rounds no longer call the old tool is, for now, held
  only by that document.**

- **Both were merged into one version** (both branched from the same commit). **There was exactly
  one conflict** — both had appended to the end of the same test file — **and both sides were
  kept.** **The CLI manual was regenerated on the second merge** (59 paths, none written by hand).
- **Verification (re-measured by the accepting session on the merged tree):** **server 3,300 passed
  / 31 skipped**, **cli 235 passed**, **web 427 pass / 0 fail**, **`check` 266 FILES 0 ERRORS 2
  WARNINGS** (the two are the pre-existing a11y ones), **`lint:i18n` 1,067 English strings / 0
  errors**, **`lint:models` 68 checks**, **ruff clean on server and cli**, **frozen corpora
  byte-identical**. **Every increment was attributed one by one** — **server +29** (10 and 19),
  **cli +8** (3 and 5), **web +5**, **English strings +1**.
- **⚠ GitHub CI was not waited for** (author's ruling: the push ends the round, and CI is not part
  of it).

---

### Android — A guard says how many it compared (android `2.1.4-android.35`, unchanged, **no version taken**, 2026-08-16, ledger I-266, I-275)

**The port's drawings are guarded by comparing them against 51 frozen reference SVGs. Several of those
comparisons were reporting a match without ever finding anything to compare.**

There were two reasons. **(1) The shape the guard named changed in engine 28** — the two regular
expressions that pull out the material layer's outline demand an exact `class="material-outline"`, but
engine 28 split the layer into contact fragments and the class became `material-outline stratum-N`.
Since then the pattern matched **neither side, and an empty list compared to an empty list is green**.
The test named four drawings and compared not one byte of any of them. **(2) The guard walked only part
of the corpus** — the comparison of element counts and class lists ran over ten drawings, and **the
powder the arcs drop (`<circle>`) is measured nowhere else**, so the grains in the other 41 were seen
by nobody.

**No pixel of the product moved this round. What moved is how far the guards reach.**

- **Widened to a prefix (stage 1):** matches any class beginning with `material-outline` rather than
  spelling out `stratum-N`, so the same hole does not open the next time the strata are numbered
  differently. Both attribute orders were kept — **the reference writes `class` first, the port writes
  `points` first**. **Widened, the four drawings really compare 192 point lists, and it was still
  green** (42 / 40 / 50 / 60). **Reviving the guard did not require fixing the product.**
- **The guards now say how many they compared (stage 2, T-143 / T-145 / T-146):** the extraction's
  count is checked against **a second way of counting that walks the elements and reads their attribute
  table**. **42 / 40 / 50 / 60 are not written into the test** — a hand-copied count is green the day
  after the corpus moves and goes on guarding the stale figure.
- **`stroke-dasharray` had vanished from the corpus in engine 28 (newly measured):** per version,
  **engines 21–25 held 252, 26–27 held 640, and 28–36 hold none**. The third assertion of the
  corpus-wide comparison is therefore also empty against empty. **It is not fully vacuous, though** —
  since the reference holds none, **a port that wrote one extra dash would go red today**. Only the
  direction "the port drops a dash the reference has" is dead, and **that asymmetry is now stated in
  one test (T-146) instead of being hidden**.
- **The structure comparison walks the whole corpus (stage 3, T-147):** it now iterates **every key in
  `svg_index.json`**. **Neither the count nor any drawing's name is written**, so a drawing added to
  the corpus is walked the day it arrives. **There are 790 `<circle>` across 51 drawings and the ten
  saw 147** — **643 (81.4%) were compared by nobody** (across all elements, 838 of 6,571, or 12.8%).
- **The tags counted are read from the index too:** the hand-written list held `path`, `circle`, `rect`,
  `polygon`, `polyline` and `line` — **it was missing `ellipse` and `g`, both of which the index
  counts**. **The 24 `<ellipse>` in two drawings were compared by nobody**, and widening to 51 drawings
  alone would have left them blind.
- **The guard now states that it read the drawing the index describes (stage 4, T-148):** for each of
  the 51, the expected side's element counts must agree with the index's `counts`. **No test in the
  tree read that `counts` field; T-148 is its first reader.**
- **⚠ One divergence was found outside the contract's scope and raised rather than fixed:** **the port
  groups its marks differently — the number of `<g>` disagrees in all 51 drawings.** The reference wraps
  marks in named groups (`inku_artboard`, `layer_10_content`, and others) which **carry no class and so
  never appear in the class-list comparison**. The direction is not constant: some drawings hold three
  fewer, some four fewer, one nine more. **No pixel moves, because groups carry no geometry** (`d` and
  `points` agree). The test holds back `g` — and only `g` — from the reference-versus-port comparison
  and records the reason and the measurement in a docstring (`g` is still covered by the
  expected-versus-index check, where all 51 agree).
- **No version was taken:** **not one line of the implementation that runs on the device changed** (a
  single test file was touched), so `android/VERSION` stays at `2.1.4-android.35`. Neither
  `renderEngineVersion` nor `ddlEngineVersion` moved. **`android/` is permanently excluded from every
  sync path, so there is nothing to send to pentala.**
- **Verification (re-measured by the accepting session on the merged tree):** **Android JVM 338 tests /
  0 failures / 0 errors / 0 skipped** (59 XML files), **`test_android_reference_fixtures_are_current.py`
  4 passed**. **The `@Test` total went from 334 at the base to 338 on the branch, +4** (T-143, T-145,
  T-146, T-148) — **no test was deleted and none was renamed**. **⚠ `cycle.sh accept` printed
  "2343 → 2343" because it does not count a single file under `android/`** (ledger I-270).
- **Six perturbations** (run by the implementing session on the branch, through `perturb.py`; all six
  restored byte-identically). **Two predictions were wrong, both by undercounting** — **the material
  layer's outline is emitted from two places, not one** (the open line and the closed contour), and only
  one was perturbed; and **one existing guard that watches `dasharray` had been missed**. **T-145 cannot
  be reddened by a single perturbation** (both sides are zero in engine 35), so **two changes were
  applied together by hand to see it go red**.
- **⚠ GitHub CI was not waited for** (author's ruling, conventions §2-10 — and **the Android JVM is not
  among the four jobs in `checks.yml`** in any case).

---

### Android — A wash is a field in the port too (android `2.1.4-android.36`, 2026-08-16, ledger I-285)

**The port offers the model ten surface textures and could actually draw two of them — `hatch` and
`crosshatch`. The remaining eight matched no branch in `renderSurfaceVectors` and fell through to the
empty string at the end of the function.** This round closes one of them, `wash`, with render engine
36's values from the server. **Words that cannot be drawn went from eight to seven; words that are
offered and still cannot be drawn went from six to five** (`stipple`, `grain`, `paper_grain`,
`aquatint`, `bleed` remain).

- **The sweep's seed and the machinery that makes one sweep were ported (stage 1):** the server's
  `_surface_stroke_seed` and `_surface_sweep` had no counterpart in the port at all (zero grep hits,
  confirmed before any code was written). They were carried over as
  `ServerRendererGeometry.surfaceStrokeSeed` and `DefaultSvgRenderer.surfaceSweep`. **This stage alone
  moves not one pixel** — nothing calls them yet.
- **The `wash` branch was added with engine 36's values (stage 2):** two layers, a width floor of 0.88,
  a width span of 0.60 and a per-sweep opacity of 0.22, **placed as named constants rather than buried
  in expressions** (`SURFACE_WASH_LAYERS`, `SURFACE_WASH_WIDTH_BASE`, `SURFACE_WASH_WIDTH_SPAN`,
  `SURFACE_WASH_OPACITY`). **Engine 36 moved exactly two quantities — the width and the opacity** — so
  the pitch, the layer count, the angles and the way sweeps are cut at the contour were carried over
  unchanged from the branch point.
- **⚠ The port's wash was already the server's wash before this round widened it:** rather than copying
  the server's baseline, the implementation put engine 35's three constants in temporarily, had the port
  itself draw the same two shapes, and measured with the same instrument. **The values agreed with the
  server's frozen ones to six digits** (square ink 0.16229907 against 0.162299; triangle 0.16225059
  against 0.162251; bare paper 0.19852839 against 0.198528 and 0.21135029 against 0.211350). Even though
  neither `_surface_sweep` nor `_surface_stroke_seed` existed in the port, **every part that makes the
  pitch, the layers, the angles and the contour cut already agreed**.
- **Eight gates were placed as properties (stage 3, T-149 to T-156):** **only two instructions in the
  51-picture frozen corpus carry a surface at all, and both are `hatch`** (all 51 scores were re-read at
  the start of the round to count this). **There are zero `wash` cases**, so the gates read no corpus
  picture; they have the port draw a square and a triangle and measure that. T-149 (almost no bare paper
  left inside the shape) and T-150 (the composite ink stays near the branch point's) **are placed as a
  pair** — T-149 on its own is passed by painting everything black.
- **⚠ T-149's threshold of 1.5% is the server's own value:** the measurement is the same kind (a
  point-in-polygon test on a 3px grid, which counts a partly covered point as paper), so the two are
  comparable. **Measured, bare paper is 0.14% for the square and 0.79% for the triangle, against 19.85%
  and 21.14% at the branch point** — an order of magnitude of clearance on both sides.
- **⚠ One gate was vacuous at first, and the implementing session found and fixed it:** T-154 compared
  the layer count against `SURFACE_WASH_LAYERS` itself, so **dropping the constant to 1 dropped the
  expectation with it and the very perturbation it existed to catch (P-3) sailed through green**. The
  branch point's 2 was written on the test's side and the constant is now checked against it separately
  (`branchPointLayers`), and P-3 was re-applied afterwards to see it go red. **The count of reddened
  tests was the same before and after the fix — agreeing on the count is not agreeing on the contents.**
- **One existing control narrowed from four words to three:**
  `ASurfaceKeepsToItsShapeTest.testTheOtherSurfaceWordsAreUntouched` asserted that `wash`, `stipple`,
  `bleed` and `aquatint` each contribute no surface stroke. **Now that `wash` is drawn, this test going
  red is the very claim the contract set out to change.** **The pre-work frozen note predicted this one
  test by name**, and no other existing test went red. **The `@Test` total did not move.**
- **⚠ Only five of the six perturbations could be applied (reported):** **P-5 (replace the sweeps with a
  single rectangle under `display`) has no place to land** — **the port's `renderSurfaceVectors` does not
  receive `svgProfile`**. The profile is read by a single local in `render()` and never descends to the
  surface layer. **T-156 (the same sweeps in every profile) is therefore structurally green in this port,
  not green-because-a-perturbation-reddened-it.** The claim itself is true, and stronger than the
  server's (the server can differ per profile through `use_filters`; the port cannot differ at all).
  **The contract named a target that does not exist in the tree — an issuing-side measurement error.**
- **The two predictions that missed, and why:** (1) **T-154 stayed green under P-3** (the vacuous gate
  above). (2) **T-150 stayed green under P-6** (paint the whole shape once before the sweeps) — **the ink
  measurement reads only `<path class="surface-stroke-v1">`**, so the `<rect>` laid down as an underlay
  never enters it (the server's counterpart has the same structure, and a different test catches the
  underlay). **When the prediction was written, what the instrument itself reads had not been counted.**
- **A version was taken:** **what runs on the device changed** (`DefaultSvgRenderer.kt` and
  `ServerRendererGeometry.kt`), so `android/VERSION` is now `2.1.4-android.36`. **⚠
  `renderEngineVersion` stays at `"35"`** — not one frozen SVG moves between 35 and 36, and **the port
  has no engine-34 ground layer at all** (what stands for `ground` is three lines of background
  rectangle against the server's 105), so **the issuing session decided not to raise it. How the version
  should be handled remains open for the author to rule on.** `ddlEngineVersion` did not move either.
  **`android/` is permanently excluded from every sync path, so there is nothing to send to pentala.**
- **Verification (re-measured by the accepting session on the merged tree):** **Android JVM 346 tests /
  0 failures / 0 errors / 0 skipped** (60 XML files, 1m 18s from `rm -rf app/build`),
  **`test_android_reference_fixtures_are_current.py` 4 passed**. **The `@Test` total went from 338 at
  the base to 346 on the branch, +8** (T-149 to T-156) — **no test was deleted and none was renamed**.
  **⚠ `cycle.sh accept` printed "2343 → 2343" because it does not count a single file under `android/`**
  (ledger I-270).
- **⚠ GitHub CI was not waited for** (author's ruling, conventions §2-10 — and **the Android JVM is not
  among the four jobs in `checks.yml`** in any case).

### v2.13.31 — a sheet called by name changes how the brush runs (Build 918, 2026-08-16, render engine 37 / ddl engine 20, ledger I-268)

**The seven grounds have been laid since engine 34, and they never reached the mark.**
The value that stands for the support was a single constant: the parameter was there, and no caller
ever passed one. **The same description with the same seed now leaves a different mark on washi than
on canvas.**

- **The sheet reaches all eleven synthesis call sites** — the drawing entry point reads it from the
  Score once and passes it down as an argument. Thirteen functions take it, **ten of them as
  keyword-only parameters with no default**, so a forgotten hand-off fails loudly. **A ground name
  that is not in the table raises rather than falling back to the default.**
- **`面: 粒` (grain) and `面: にじみ` (bleed) now stay on lines and arcs** (ddl engine 20) — of the
  nine surface words, these two speak about **how the mark runs rather than how an inside is**.
  Until now every surface on an unclosed instruction was moved to the closed shape before it or
  dropped, so **they were never drawn on the 406 works in production that carry them** (283 grain,
  123 bleed: 49 were being moved, 191 dropped with nowhere to go, 166 dropped because the target
  already carried its own surface). **Redrawn from today, those 406 show the mark the sheet worked.**
- **The reinforcement is capped** — a factor of 2.0, **capped at 3.0**. Washi (absorb 2.2) with bleed
  would be 4.4 and stops at 3.0.
- **The other seven words (`wash`, `paper_grain`, `hatch`, and the rest) are unchanged.**
  `wash` is taken by a separate contract (render engine 39) under the ruling of 2026-08-16.
- **The reference corpus is now 597 cases, twelve of which moved** — the nine new ones and three
  existing ground cases. **The nine were needed because no case ran through the mechanism**: only
  four frozen cases use the `display` profile, all four draw with `pen`, and `pen` carries no texture
  weight. **`pen` barely shows the sheet** (an arrival probability of about 0.005, so only the two
  supports that absorb more than `paper` cross the threshold), which is why the nine are written with
  `brush_thick` and `chalk`. **The DDL corpus holds 49 cases and one moved.**
- **One ruling was taken mid-flight** — a stage was measured before the work began to move one frozen
  DDL case, and the ruling was to **take `ddl_engine_version` 20 and rebake**. This release moves two
  layer versions.

**Verification (measured by the accepting session on the merged tree, all green)**:
**server 3,315 passed / 31 skipped (539.65s)**, **cli 235 passed (14.82s)**,
**web 427 tests / 427 pass / 0 fail (5.54s)**, **Android JVM 346 tests / 0 failures / 0 errors /
0 skipped (60 XML files, 36s)**, **`check_frozen_corpora.py` green (32s)**, **ruff green**.
**The +15 on server is the branch's own** (11 acceptances, 3 corpus checks, 1 control for the mark
words); the rest arrived on main after the branch point.

- **One merge conflict** (a single import in `coerce/normalize.py`). **Both sides were kept** — the
  limit notes from main and the mark-word set from the branch — and both were checked by name after
  the merge (nine `note_limit` call sites, one pass-through branch).
- **The eleven acceptances and fourteen perturbations were run by the implementing session**
  (103 reddened, none idle). **Two defects in the acceptances were found by the perturbations and
  fixed**: a comparison between a line with the mark word and one without stayed green even with the
  mechanism switched off (the performance seed derives from the instruction's own content), and a
  loop over the product's own set spun empty — and green — under the perturbation that empties it.
- **The version literals were four, not the three the contract measured** (`test_api.py`); the DDL
  side has four as well.
- **The GitHub CI result was not waited for** (author's ruling, conventions §2-10).

### v2.13.32 — a raised ceiling reaches the page (Build 919, 2026-08-16, ledger I-132 and I-136)

An administrator could raise the ceiling on how much a work may hold and see no more ink on the page. **Three places never read the raised value; each of them had the shipping number written straight into it.**

- **A tiling with no number in it follows the ceiling.** A description that names no count -- "fine lines tiled
  across the whole sheet" -- decided how far to expand from the shipping 400. On an installation set to 1200 it
  **stayed at 400**; it now draws **1200**. There are two call sites and **both are handed the limits**, because
  leaving one on the default would keep the old behaviour for whatever came through that road.
- **The representation bands became ratios of the ceiling.** The boundaries that pick how dense a group reads
  and how many clusters it is split into (180 / 80 and 500 / 240 / 120 by default) were constants that assumed
  the shipping ceiling of 120. **Held as integer ratios, they land on exactly today's numbers at the defaults
  and move with the setting when it moves.**
- **The cap on cluster count follows the ceiling.** **What actually held it was the `le=12` written on
  `Arrangement.cluster_count`.** At three times the ceiling one group carries 360 marks, and keeping a cluster
  at 24 marks needs fifteen clusters or more. **The static bound is gone and the composer writes the effective
  one (`represented_count_max // 10`) back into the tool schema** -- which is what the same file already does
  for `count`. **At the defaults it is exactly 12 again and the tool JSON is byte-identical.**
  **Marks per cluster stay inside the default band of 13.3-24.0 at a third of the ceiling and at three times
  it**, where today they ran to 4.4 and 42.9.
- **The number on the stepper says what it weighs.** The stepper counts marks; what reaches a reader is a file.
  **The server sends the measured cost of one mark** (`bytes_per_mark`: 12,924 for a pen and 16,138 for a thick
  brush, measured 2026-08-16 on the 400-mark row, which is the default itself), **and the settings panel prints
  `≈ 5.2-6.5 MB` under the total and nowhere else.** **No seconds** -- that measurement was CLI round-trip wall
  clock, not drawing time. **The other eight rows carry none**, because they are per-instruction bounds,
  legibility thresholds and typo guards, and none of them governs megabytes.
- **Nothing moves at the defaults.** `check_frozen_corpora.py` is byte-identical, and neither
  `render_engine_version` nor `ddl_engine_version` was raised.

**All four guards over the frozen API surface moved**, because **two schemas changed** rather than one:
`RenderLimitsStatus` gained a key and `Arrangement` lost a bound. **Only the record was regenerated; the other
three were given declarations.** **The declaration mechanism was widened twice**: a key with no default is also
listed under `required`, so a declared key is now taken out of that list as well (the twelve declared before
this one were all optional, so nobody had hit it); and **a bound that left cannot be expressed by a property
that arrived or departed**, so a restoration is put back before hashing. **The card and ACL guards already held
`Arrangement` through a `group_size` declaration and, comparing only property sets, waved the vanished
`maximum` through -- two named checks now close that.**

**Verification, measured by the accepting session on the merged tree, all green**:
**server 3,350 passed / 31 skipped (517.63 s)**, **cli 235 passed (15.73 s)**,
**web 431 pass / 0 fail / 0 skipped (5.61 s)**, **`npm run check` 0 errors / 2 warnings** (the two known a11y),
**`lint:i18n` 0 warnings / 0 errors**, **`check_frozen_corpora.py` byte-identical**, **ruff clean**.
**The +35 on the server is exactly the branch's** (8 new functions, 35 cases) and matches the main-side
increment one for one.

- **The 8 acceptance checks and 11 perturbations were run by the implementing session**, with the prediction
  frozen in a commit before any code. **Three came out differently**: the roles of the two call sites had not
  been measured beforehand (+1), the web suite's full-run meta gate came along (+1), and the frozen corpus
  turns out to touch the 240 boundary in no case at all (-2). **That last one means a single acceptance check
  is the only guard on that boundary.**
- **After the merge the accepting session fixed two web defects** (on the author's ruling, committed to the
  branch and merged a second time with `--no-ff`): **(1) the `{@const}` sat directly inside an element, so the
  panel did not compile at all** (`npm run check` reported 2 errors; neither the contract's list of runs nor
  the branch's own covered that surface, and `node:test` reads the file as text so it stayed green), and
  **(2) `+page.svelte` declares its own type and had been left behind as the other half of the pair.**
- **The GitHub CI result was not waited for** (author's ruling, conventions §2-10).

---

### Android — A grain is one touch, and a band is made of them (android `2.1.4-android.37`, 2026-08-16, ledger I-285)

**Of the ten surface textures the port offers the model, three could actually be drawn. Seven can now,
and the words that are offered while drawing nothing went from five to one — `bleed`.** The four that
landed are `stipple`, `grain`, `paper_grain` and `aquatint`, and **they fit in one round because the
server draws all four the same way**: scatter positions inside the contour, then touch the tool down
once at each point. The touching-down part (`_surface_dab`, 73 lines on the server) is ported once and
serves all four.

- **A grain is not a circle:** one point is one stroke, and it becomes a circle only for a machine pole
  like `rotring` or `computer`. A hand tool gets one stroke from the material engine, and **its width is
  the greater of the tool's stroke width and the grain's own size** — the server's docstring carries the
  measurement showing the surface disappears when only the stroke width decides. **Both paths were
  ported.**
- **`svgProfile` was threaded down to the surface layer (stage 1):** the server reads `use_filters` in
  four branches — the three grain words, `wash`, `aquatint` and `bleed` — and **`hatch` is the one that
  does not**. **The single branch the port already had was that `hatch`, which is why it had gone this
  far without the profile.** It now reaches all eleven call sites of `renderSurfaceVectors`, and **since
  all eleven sit inside one function (`renderInstruction`), that function took an argument too**. **No
  default value was given** — a default would let a new call site pick the old behaviour silently. **The
  folded form is `useFilters: Boolean`, folded only after reading the server's two steps one-to-one and
  confirming their composition is exactly `profile == "display"`.**
- **⚠ The `wash` filter the previous round deliberately left unconditional is now cut by profile.**
  **That line had never emitted a single byte** — the tools with a texture filter are `pencil`, `crayon`,
  `chalk`, `brush_thin` and `brush_thick`, **`pen` writes none, and all eight gates from the previous
  round run on `pen`**. The new gate uses `pencil` for exactly this reason; on `pen` the perturbation
  would have hit nothing.
- **`aquatint` does not scatter twice:** it scatters once, then decides each grain's opacity from which
  horizontal band the point fell into. The step number goes into an `aquatint-step-N` class. **A grain
  nudged past the contour is put back** — **without that, one point on the square and two to four on the
  triangle land outside** (measured; perturbation P-6 really did go red).
- **Nine gates were placed as properties (T-157 to T-165):** **only two instructions in the 51-picture
  frozen corpus carry a surface, both `hatch`, and these four words have zero cases**, so the gates read
  no corpus picture and measure a square and a triangle instead.
- **⚠ Two vacuous-gate traps were avoided:** T-158 writes the ceiling of 90 on the test's side as
  `statedMarkCeiling` and **checks the product's `SURFACE_MARK_MAX` against it on a separate line** (the
  shape that made T-154 vacuous last round). **A ceiling alone would pass an implementation where the
  ceiling always binds**, so a thin surface (density 0.05, measured 30–32 marks) and a dense one
  (density 1.0, measured 89–90) are placed as a pair. T-161 compares against the `tone_steps` the score
  asked for and reads no product constant at all.
- **⚠ The implementing session corrected one of its own pre-work predictions:** it had predicted the
  ceiling of 90 would not bind on the contract's triangle, so a larger shape would be needed. **The area
  factor comes from `shapeBbox`'s `w * h`, not from the triangle's area.** **The square and the triangle
  share a bbox, so both get the same factor of 1.0755 and both hit the ceiling at density 0.55.** No
  larger shape was needed; the two shapes the contract named were enough.
- **⚠ The three grain words agree only in the surface layer:** T-159 was going to assert that the three
  produce identical SVG, and **measurement said otherwise** — an instruction's own seed is a hash of the
  instruction's dump, and the texture word is inside that dump, so the shape's own contour stroke differs
  between the three. **The server has the same shape, so this is not a defect in the port.** T-159
  compares only what the surface layer wrote (measured: 89 elements on the square, 90 on the triangle,
  identical across all three words).
- **⚠ `pencil` writes 66 `<circle>` elements that do not belong to the surface layer:** the material
  layer's circles carry no class, and **the port's grain circles carry none either, exactly as on the
  server**, so markup cannot tell them apart. **The contract named `pencil` for T-160; it was changed to
  `pen`** — `pen` is a hand tool that writes no circles at all, and `rotring` writes circles that are all
  grains. **That pair is the only one that reads both paths without ambiguity.**
- **One existing control narrowed from three words to one:** `stipple` and `aquatint` left
  `ASurfaceKeepsToItsShapeTest.testTheOtherSurfaceWordsAreUntouched`, leaving `bleed`. **This is not a
  regression but the very claim the contract set out to change** (the contract named this one test
  before any code was written). **The `@Test` total did not move.**
- **Six of the seven perturbations matched the prediction; one missed:** **P-4 (kill the `usesHandStroke`
  branch) was predicted to redden one test and reddened three.** The miss was not about the drawing but
  about **what the gates read** — T-157 and T-162 read the machine pole through `<circle>`, so sending
  the machine pole down the stroke path leaves **no circles at all and they fail on "there are no marks"**.
  **They went red because what they read became empty, not because a centre moved outside.** **Writing
  function names into the prediction without writing how each one reads was the direct cause.**
- **⚠ The contract's own perturbation table was wrong in two places, and the implementing session caught
  both before writing code:** (1) **P-3 also reddens T-164** — the contract listed two tests; T-164 walks
  all four words, so a `paper_grain` that draws nothing emits no filter even under `display`. (2) **P-7
  does not reach the previous round's `AWashIsAFieldTest`** — the contract said it might; T-156 reads
  only sweep width and opacity, never the `filter` attribute, and runs on `pen`. **Both were written into
  the frozen note with their reasons, and both measured out that way.**
- **A version was taken:** **what runs on the device changed** (`DefaultSvgRenderer.kt`), so
  `android/VERSION` is now `2.1.4-android.37`. **⚠ `renderEngineVersion` stays at `"35"`** (the issuing
  session's decision still stands, and **how the version should be handled remains open for the author to
  rule on**). `ddlEngineVersion` did not move. **`android/` is permanently excluded from every sync path,
  so there is nothing to send to pentala.**
- **Verification (re-measured by the accepting session on the merged tree):** **Android JVM 355 tests /
  0 failures / 0 errors / 0 skipped** (61 XML files, 44s from `rm -rf app/build`),
  **`test_android_reference_fixtures_are_current.py` 4 passed**. **The `@Test` total went from 346 at the
  base to 355 on the branch, +9** (T-157 to T-165) — **no test was deleted and none was renamed**. **⚠
  `cycle.sh accept` printed "2370 → 2358" and appeared to show twelve tests vanishing; those twelve came
  from ledger I-132, which landed on main after the branch point, so the branch simply does not carry
  them** (and the tool counts no file under `android/` at all — ledger I-270).
- **⚠ One finding outside the contract's scope was filed rather than fixed:** **the port's `wash` and
  `hatch` take the surface seed at `(0, 0)`** where the server takes it at `(ins_idx, mark_idx)`. **When
  `surface.seed` is absent, every mark expanded by an `arrangement` ends up with the same texture.** The
  two branches added this round take it the server's way, so two conventions now live side by side in the
  port. **The visual difference is unmeasured.**
- **⚠ GitHub CI was not waited for** (author's ruling, conventions §2-10 — the Android JVM is not among
  the four jobs in `checks.yml`).

### v2.13.33 — the texture hangs on the run, not on every mark (Build 920, 2026-08-16, ledger I-264)

One work carried **24,446 individual filter references** and spent roughly four fifths of its display time
on them. **Marks drawn in a row with the same tool each carry the same texture**, so folding a run into one
group cuts how many times the filter is applied by about twelve.

**⚠ A ruling during the run changed where this work belongs.** The contract asked for a renderer that emits
the folded SVG (render engine 38). **Measuring the two production widths, the implementation found that the
reference count the contract wanted — one where folding is faster at both 256px and 2160px — does not exist
anywhere between 34 and 26,675 references.** **What decides the sign is not the reference count but the
width being baked.**

- **Count and area pull opposite ways.** Folding cuts the number of filter applications by about twelve and
  **raises the total area they cover by 1.35–1.41×** (a run's bounding box is larger than the sum of the
  boxes it replaces). **Where count dominates, at small widths, it is faster; where area dominates, at large
  widths, it is slower.** **"Fold only the runs whose area does not grow" was measured and discarded** — the
  runs worth folding are exactly the ones whose area grows, and with the restriction the byte count went *up*
  (4,764,476 → 4,770,076 at 12,292 references).
- **The ruling was "decide by the width at bake time"** (2026-08-16). **The stored SVG does not change by a
  single byte**, so `render_engine_version` stays at 37 and no reference corpus was rebaked.
- **The fold lives in `shared/src/inku_analysis/texture_fold.py`, and `svg_to_png` looks at the width and
  applies it itself** — not a flag each caller passes, because a flag any caller could forget is one some
  caller would. **The ceiling is 512px**, which takes in both production thumbnail widths (256px and the
  512px HiDPI one) and leaves out the 2160px PNG export default and any browser display width.
- **Three things end a run**: a group boundary, a mark with no texture, and a different tool. **No mark
  changes place** (a run replaces its own span in the document). **A run of one is wrapped too** — it draws
  the same, and it makes the readable property "a folded document holds no per-element texture reference".

**Speed** (pairs taken inside one round; net = current ÷ (folded + the fold's own time)):
**1.574–1.973× at 256px**, **0.955–1.207× at 512px**, **0.79–0.95× — slower — at 2160px.**
**Only 256px is asserted against a clock**; 512px is narrower than the noise and is measured as a property.

**Picture difference** (1:1, mean difference out of 255), at 127 / 378 / 4,616 / 12,292 references:
**0.058 / 0.184 / 2.010 / 3.685 at 256px** and **0.039 / 0.115 / 1.383 / 2.575 at 512px**.
**The author judged the 1:1 contact sheet and accepted it** (2026-08-16).

**⚠ Existing thumbnails are not rebaked.** Staleness is decided by `source_render_hash`, and **that hash
cannot move while the stored SVG does not.** **What gets faster is what is baked from now on, plus an
explicit rebuild** (`/api/settings/thumbnails/rebuild`).

**Verification, measured by the accepting session on the merged tree, all green**:
**server 3,370 passed / 31 skipped** (489.93 s), **cli 235 passed** (14.95 s), **ruff clean across server,
cli and shared**, **`check_frozen_corpora.py` byte-identical**. **The +20 on the server is exactly the
branch's** (T-129 to T-138, twenty functions). **No test disappeared.**

- **The 10 acceptance checks (20 functions) and 8 perturbations were run by the implementing session**, with
  the prediction frozen before any code — **and frozen again, still before any code, once the ruling changed
  the design.** **Two came out differently** (P-2 2→4 and P-4 1→8, both of the "it reached every check that
  reads the fold's output" kind).
- **⚠ The reference corpus cannot see this work at all.** P-7 (apply the fold inside `render()` as well)
  reddened 8 tests and **zero corpus cases**: of the 588 cases only 4 are `display`, all four are `pen`, and
  `pen` carries no texture filter. **The same held for engine 37's 597.** **A single acceptance check is all
  that watches for the fold leaking into the renderer** (filed as ledger I-289).
- **⚠ The sign at 2160px disagrees with the issuing session's measurement** — the issuer measured 1.4× faster
  at 24,445 references; the implementation measured 0.79× (slower) at 26,675. **Which is right is not
  settled** (filed as ledger I-290). **This version folds nothing at 2160px under either sign, so the open
  question changes neither the picture nor the speed.**
- **⚠ The accepting session added one perturbation.** Of the acceptance checks whose content the mid-run
  ruling replaced, **T-136 (no road rasterizes around the fold) had no perturbation aimed at it.** Adding one
  backend import outside the rasterizer reddened exactly that one check and nothing else.
- **The GitHub CI result was not waited for** (author's ruling, conventions §2-10).

---

### Android — The edge seeps, and every mark carries its own seed (android `2.1.4-android.38`, 2026-08-17, ledger I-285, I-288)

**Of the ten surface textures the port offers the model, the count it offers without drawing went 1 to 0.**
The last word, `bleed`, went in, so what the docstring in `gen_android_reference.py` states — the port
must not offer Stage 2 a ground it cannot draw — and the list the port's schema actually offers
**agree for the first time in ten rounds** (8 words, then 3, then 1, now 0).
**The same round put the surface seed on the server's footing.**

- **A seep is a claim about the edge:** up to engine 15 the server put one ellipse at the centre of the
  bounding box, so a triangle and a cloudform got the same ellipse and no edge seeped at all. The
  mechanism now lays three bands pushed out from the outline itself, and **how far each vertex is pushed
  wavers**, so it reads as a seep rather than as concentric outlines. **The innermost ring lies on the
  outline** (`level` is `ring / (rings - 1)`, which is 0 at `ring == 0`). **The body moved is 64 lines**
  (`renderer.py:3979`–4042. **The ledger and the previous round's contract both said "66 lines"; they
  drew the boundary differently and the count is 64**).
- **Only one new part had to be made:** the constant `SURFACE_BLEED_RINGS = 3`. `centerlineNormals`,
  `pointsCenter`, `usesHandStroke`, `synthesizeAlong`, `surfaceStrokeSeed`, `gridStepPx`,
  `contourStrokePath` and the texture-filter attribute **were all already in the port** from earlier
  rounds, and the `useFilters` transport was laid by the previous round's first stage, so **this round
  laid none of it again**.
- **Both roads were kept:** the machine pole (`rotring`) gets three `<polygon>` elements carrying no
  class, a hand tool gets three `<path class="surface-stroke-v1 bleed-ring-N">`. **Which way to push is
  settled by a majority vote of the normals** — the sign is not a constant, because the normals do not
  face the same way on every shape.
- **The surface seed is now made once, before the branches (ledger I-288):** the server makes it once in
  `_render_surface_texture` and hands it to every branch, while **the port made it four times inside the
  branches, and two of those — `wash` and `hatch` / `crosshatch` — dropped the mark index**. The call
  count in production went **4 to 1**, and **the two customs that had been living side by side in the
  port became one**. A branch added later can no longer pick the wrong one.
- **⚠ One premise the contract stated did not survive measurement:** the contract said that passing
  `(0, 0)` makes **every mark an `arrangement` expanded wear the same texture**, but **an expanded mark
  has its own coordinates, and those coordinates are in the seed's material** (the instruction's dump),
  so **the marks already had different seeds with `(0, 0)` in place**. **The divergence was real; what
  was not reaching the seed was `insIdx`** — put two instructions identical in every stated field into
  one score and their index is the only thing between them. **The gates were set in those two halves**
  (the `arrangement` half as the contract worded it; the discriminating half is the two identical
  instructions). **The server has the same structure, so `mark_idx` is redundant with the coordinates
  there too** — not changed inside an Android contract, filed on the ledger instead (I-291).
- **Ten gates set as properties (T-166..T-175):** **the frozen corpus holds 0 `bleed` cases** and
  **0 instructions carrying both an `arrangement` and a surface**, so not one of its 51 sheets can
  measure this change. **T-166 replaces an existing control** — the check asserting that `bleed` drew
  nothing **would have become a vacuous loop had its single entry simply been removed**, so the claim
  was turned over into **"every word the schema offers is a word this layer draws"**. **The list of
  words is read from the schema, not copied into the check.**
- **⚠ The mark-to-mark comparison runs on the machine pole:** a hand tool quantises its samples onto a
  grid anchored at the origin, so **two marks wearing one texture are still never exact translations of
  one another** (measured: with a stated seed, `pen` gives 24 sweeps falling into 24 distinct shapes,
  `rotring` gives 24 falling into 8).
- **The full run went 355 to 364 (+9):** nine checks were added; T-166 replaces one and so does not
  count. **One check disappeared, and that one became T-166.** **On the merged tree: XML 62 / tests 364
  / failures 0 / errors 0 / skipped 0**, and `test_android_reference_fixtures_are_current.py`
  **4 passed**.
- **The nine perturbations were run by the implementation session on the branch** (the prediction was
  frozen before any code, overlay `cd678deb`). **One missed** — P-1 (three rings to two) was predicted
  to redden 1 check and reddened 4, because **three other gates were reading "there are three rings" as
  a premise** (the type being "failing to count what a check reads").
- **⚠ `support` is not passed to `synthesizeAlong`** — this is not a divergence this round introduced:
  **none of the port's nine call sites pass it** (the ground layer itself is not in the port).
- **⚠ The GitHub CI was not waited for** (author's ruling, conventions §2-10).

### v2.13.34 — the reader decides what the strip prints (Build 921, 2026-08-17, UI round 6)

The author named seven requests at once and settled them one at a time in conversation. The list
carried an override at the end — "anything that needs server code or a database change is
overridden" — and **four of the seven crossed out of `web/`**. One of the seven (making the
sketch default "fine" when nothing is stated) was withdrawn the same day.

- **The reader chooses what the history strip prints under each thumbnail:** four boxes under
  `Other` in the settings — **generation, model, engine version, file size** — and **at most two**
  may be chosen. **None is also an answer**: choose nothing and the strip shows only the pictures.
  **The rule this turned on is that absence and the empty list are different things.** An account
  with no column has **not answered**, so it takes the default (the two the strip printed before
  the column existed); a reader who clears all four **has answered, and the answer is "print
  nothing"**. **Folding the two into one falsy test makes "print nothing" a setting that cannot be
  saved** — it returns to the default on reload — **and that breakage reddens no test that looks
  only at the normal path.**
- **The file size in the strip read `0 B` for every work but the one on screen:** the listing that
  fills the strip is fetched with `include_svg=false`, and **the server empties the key rather
  than dropping it**, so the browser was **measuring the emptied result**. The API now sends
  `svg_bytes` — UTF-8 bytes, the same quantity as `measureSvgWeight().bytes` and `measure()` in
  `svg_weight.py` (**neither way of counting was touched**). **⚠ It was first placed on
  `HistoryPostBody`**, which made it a key a caller could state when saving; the weight is
  something the server reports about a stored work, so it moved to `HistoryItem`. **The API
  surface guard is what found it.**
- **History search takes a whole render hash:** only **exactly four characters** were recognised
  as a hash before, so pasting a full one fell through to full-text search and found nothing. The
  last four still work as they did.
- **AI refinement failed with `invalid refinement advice JSON` every time:** the fence stripper was
  written as `\s` **inside a raw string**, where that means "one backslash followed by zero or more
  `s`" rather than whitespace, so **it never matched once**. gemma answers inside a fence, so every
  answer died there. **⚠ The first fix was redundant** — stripping the fence and then extracting
  the braces meant that for fenced input **the brace extractor always produced the same result**,
  so breaking the fence half reddened nothing. **Wiring that always agrees with the existing path
  has no discriminating power**, so it was folded into **one rule: the first `{` through the
  last `}`**.
- **The model picked for AI refinement now draws, not only advises:** the choice reached **the
  single advice call** and nothing else, so the picture came out of the page's own model setting.
  The running display names the model it is drawing with.
- **The word on the batch tab stays on one line during a run:** what wrapped was **the tab's word**,
  not the progress figures. Measured: `(3/12)` gave a 38px tab and one line, **`(12/12 ↻2)` gave
  46px and two lines, `(120/120 ↻2)` gave 58px and three**. After the fix it is back to 38px and
  one line, and **healthy down to a 300px panel**.
- **The empty canvas was redrawn as three strokes — a mountain, water and a moon:** the mechanism
  that keeps it from being dragged by the aspect ratio went in on 2026-08-12 and **was not broken**,
  so the author chose to redraw the figure itself and picked the subject. **All nine ratios were
  rendered and five were looked at** (square, portrait, wide, banner 5:1, pillar 1:5).
- **One column was added to the database:** `history_strip_fields TEXT NOT NULL DEFAULT
  '["generation", "model"]'` on `user_accounts`. **The default is what the strip printed before the
  column existed, so nobody's strip moves on the day this is deployed.**
- **On the merged tree: server 3401 passed / 31 skipped, web 446, cli 235 passed.** **`npm run
  check` gives 268 FILES / 0 ERRORS / 2 WARNINGS** (the two known a11y warnings, unchanged).
  **Both sides added up:** against 1821 test functions in `server/tests` at the branch point,
  **the main side added 15 (the fold gates from ledger I-264) and the branch added 15, for 1851
  after the merge**; collection went **+31 from the branch and +20 from the main side, +51 in all**
  (the function count and the collected count are two different quantities).
- **The implementing session ran 13 perturbations on the branch and all 13 reddened** (one missed
  its prediction: P-3 predicted 2 and measured 4, because adding `g` to a character class reddened
  a `g`×64 case alongside the three that loosened the digit count). **⚠ The accepting side added
  one more**: the stage that widened the API surface declarations had no perturbation on it, so an
  undeclared key was added to `HistoryItem` in the product, and **two guards reddened as expected**.
- **⚠ What that perturbation showed**: the `HistoryItem` declaration in
  `test_the_groups_decide_what_you_may_do.py::test_t8` is **inert** — **`HistoryItem` is not among
  the 78 frozen schema names**, so that line measures nothing. **It has been inert since
  `catalog_mode` was declared there, and this round only added a word to it** (**the other 14
  declarations are all live**). **The same schema is held by two other guards, so no hole is open.**
- **⚠ The GitHub CI was not waited for** (author's ruling, conventions §2-10).

### Android — A shape that does not say where it is has no box (android `2.1.4-android.39`, 2026-08-17, ledger I-269)

**Four branches of `ServerRendererGeometry.shapeBbox` answered with a box for input the server would
have declined.** Every branch of the server's `_shape_bbox` is entered only when **both** of the
fields that place the shape are stated; when either is missing the branch is declined and the walk
falls through to `return None`. **The port filled the missing field in with a default (`0.5`,
`0.12`, `0.38`, `0.24` and others) and returned a rectangle.** This round made those four branches
read one-for-one with the server.

- **The four branches:** `circle` (`center` and `radius`), `ellipse` (`center` and `size`),
  `square` / `triangle` (`position` and `size`), `polygon` (`center` and `radius`).
  **`cloudform` was already correct, so its expression was not touched.**
- **Both of the polygon's substitutions were dropped:** the port built a centre out of `position` +
  `size` when `center` was absent, and a radius out of `size` when `radius` was absent. **The server
  builds neither**, so both are gone. **A polygon that states `position` and `size` still has no box
  unless it states `center` and `radius`.**
- **Not a falsy test:** array fields are read with `optJSONArray(...) == null` and the number with
  `isNull("radius")`. **A `center` of `[0, 0]` and a `radius` of `0` are both stated** — the same
  judgement as the server's `is not None`.
- **⚠⚠ What the contract assumed turned out to be false when measured:** the contract said the
  difference between `null` and "a rectangle filled in with defaults" is the difference between
  drawing a surface and drawing none. **It is not.** The surface layer `renderSurfaceVectors` calls
  `surfaceContour` (`DefaultSvgRenderer.kt:1962`) before it reads the box, and **that gate demands
  the same fields, written the same way, by hand.** When they are missing it returns `null` and each
  texture branch leaves first through `if (contour == null || contour.size < 3) return ""`.
  **Measured: restoring the `circle` branch to its old shape and drawing the same score leaves the
  SVG at 11,792 bytes, not one byte different** (zero surface lines either way). **The box gate was
  never binding, and no shape missing a field has ever been given a surface.** **What was fixed is
  the answer this function returns, not a mark on the paper.**
- **⚠ So this round cannot claim that surfaces are now drawn differently.** The same judgement now
  sits in two places, hand-copied, with only one of them live. **Whether to fold one away or to hold
  the two to the same answer with a gate is a ruling, and it was filed** (unnumbered).
- **Six gates (T-182..T-187):** for each of the four branches, the paired claim that a missing field
  means no box and a stated pair means a box (T-182..T-185); that a boxless shape gets no surface
  (T-186); and **that a shape which does state its box keeps the box it had** (T-187 — the four
  numbers of each branch's box written on the test side and compared on two sheets). **None of them
  read the frozen corpus** (its 51 sheets carry zero cases with a missing field).
- **⚠ Three of the seven perturbations missed their prediction:** P-1 / P-2 / P-3 predicted T-186
  would redden alongside; **only the branch's own gate did.** The reason is the duplication above —
  restoring the box changes nothing because `surfaceContour` declines first. **T-186 was not
  removed** (its claim is true and its control does work), **but its lack of discriminating power is
  now written into its KDoc with the measurement.** **The five gates actually holding this change
  are T-182..T-185 and T-187.** The miss is of the type "failing to count what a test reads" — the
  same type as the previous round's, missed here two rounds running. **P-4 and P-5 restored the
  polygon's two substitutions separately and each reddened T-185 on its own. P-6 reddened only the
  existing T-87**, showing this round did not touch `cloudform`.
- **The full suite went 364 → 370 (+6):** **on the merged tree, XML 63 / tests 370 / failures 0 /
  errors 0 / skipped 0**, and `test_android_reference_fixtures_are_current.py` **4 passed**. **No
  difference from the prediction frozen before the first line was written.**
- **Five comment lines above the `cloudform` branch are gone** — their content ("the server demands
  both and answers `None` when either is missing") **now describes all five branches**, so it moved
  to the function's docstring. **No expression, condition or default in that branch changed** (T-87
  reddens under P-6 and nowhere else).
- **⚠ The acceptance side took the frozen prediction out of the public tree** — the implementation
  had committed one prediction file to the branch under `android/`, but **all twenty frozen
  predictions live in the overlay**, so the file was copied to the overlay's contract directory
  (md5 verified) and deleted here. **The freeze itself is
  held by commit `593f90a6` (07:46:28), two minutes and forty-six seconds ahead of the first product
  commit `334f6399` (07:49:14).**
- **Two ledger entries filed (numbered the same day as I-299 and I-295):** (1) the server refuses an instruction missing a
  field with `ValueError` across seven primitives while the port draws it with defaults — **this
  round fixed only the surface gate, so a middle state remains where the shape is drawn and the
  surface is not**; (2) the duplicated gate above. **Both await a ruling.**
- **⚠ The GitHub CI was not waited for** (author's ruling, conventions §2-10).

### Android — The guard draws with what the index declares, and compares the colours (android `2.1.4-android.40`, 2026-08-17, ledger I-280)

**The guard that compares against the 51 frozen reference SVGs read none of three declarations in the
index `svg_index.json`** — `color_catalog_id`, `fill_colors` and `stroke_colors`. **The comparison
scaffolding wrote `colorCatalogId = "default"` by hand, so the five sheets whose index entry names
another catalog were redrawn with different equipment than the one the reference was made with.**
**Colour was never compared at all**, which is why [I-280] — nobody deciding whether the machine pole
fills an interior — was invisible to every guard.

- **One road to the index, and only one:** a new `ReferenceRendering.kt` (`index()`, `entry(key)`,
  `catalogId(entry)`, `request(entry)`, `svg(entry)`). **`catalogId` reads with `getString` and
  supplies no default** — a missing key is a failure, not a silent `"default"`. **All six paths that
  compare against the references were wired to it** (`DefaultSvgRendererPhase2f`, `Phase2e`,
  `ServerRendererCloudformAndRelations`, `CornerShapeMaterialLayer`, `DefaultSvgRendererFillDab`,
  `GroupMembersReachEachEngine`). **A 36-line copy in `Phase2f` became a one-line delegation.**
- **⚠ Stage 0 measured what stage 1 alone would redden: nothing — 0 tests.** That the existing
  comparison carries no colour was confirmed by measurement (it compares `d`, `points`,
  `stroke-dasharray`, classes and element counts). **One sheet of the 51 disagreed on colour**
  (`05_circle_rotring`, on `fill` only); **zero disagreed on `stroke`; and the reference SVGs and the
  index declarations disagreed nowhere.**
- **[I-280] closed in one line:** `val fill = if (ServerRendererGeometry.fillsInterior(ins))
  attrs.fill else "none"` in `DefaultSvgRenderer.renderInstruction`. **The judgement was already
  ported as `fillsInterior` (one-for-one with the server's `_fills_interior`) and is read here, not
  copied.** **All eight places that write this output now pass through the one decision** (seven on
  the geometric road plus the `polygon()` helper). **The hand road's `renderBodyShape` was already
  correct through `regionFill` and was not touched.** **A dead probe carrying
  `@Suppress("UNUSED_VARIABLE")` is gone.**
- **Six gates (T-176..T-181):** that the guard hands over the catalog the index declares; that the
  `fill` colours agree with the declaration; that the `stroke` colours do; **that the guard says how
  many drawings it compared**; that a machine pole does not fill an interior nobody asked to have
  filled; and **that swapping the declaration changes the colours drawn.** They walk all 51 sheets.
- **⚠ Two ways of going vacuous were closed:** the count is taken **on what the port actually drew,
  not on what was declared** — counted on the declaration side it stays at 51 even if the port draws
  nothing. **The comparison itself returns whether it compared, and the walk counts that**
  (**perturbation P-4 built exactly the state where 51 sheets are walked and none compared**). And
  because **46 of the 51 declare `default`**, a road that ignored the declaration entirely would
  still satisfy the two colour gates on all but five — the sixth gate is what closes that.
  **The swap is made on an in-memory `JSONObject`; the frozen files are not rewritten.**
- **⚠ One of the six perturbations missed:** P-2 (making the product ignore the catalog id) was
  predicted to redden 3 tests and reddened **13** — **ten existing tests came along.** **The cause
  was counting with the literal `colorCatalogId = "` when writing the prediction**: those ten pass
  the id through a variable, a `RefinementPlan` or the repository, and match no literal. **When the
  target is a wide place in the product, the readers are counted as "tests that consume the value",
  not "lines that write the id".** **⚠ The layers are still told apart** — **P-1 (does the guard read
  the index) reddens only the four new gates, and under P-2 T-176 stays green.** Measurement kept
  them distinct.
- **⚠ One assertion made by the issuing side was false:** the contract said both
  `05_circle_rotring` and `12_cloudform_rotring` disagreed with their declaration on fill.
  **`12_cloudform_rotring` already agreed** — `ServerRendererStyle`'s set of closed shapes does not
  contain `cloudform`, so its fill was already `"none"` (**`ServerRendererGeometry.CLOSED_SHAPES`
  does contain it: the two sets disagree**).
- **The full suite went 364 → 370 (+6). On the tree carrying both of today's branches, XML 64 /
  tests 376 / failures 0 / errors 0 / skipped 0**, and
  `test_android_reference_fixtures_are_current.py` **4 passed**. **The frozen corpus was not touched.**
- **⚠ The branch point moved mid-round** — another session fast-forwarded this worktree's branch to
  the tip of main (`024df278` → `97400d43`). **The `android/` subtree hashes identically at both**, so
  the baseline measured before the work still holds. **Acceptance read `97400d43..tip`.**
- **One follow-up filed (numbered the same day as I-298):** **`ServerRendererStyle.strokeAttrs` does not read the
  server's `do_fill`** — (1) a shape that is not filled still gets a `fill-opacity`, and (2) writing
  the same request as `surface.texture="solid"` makes a `cloudform`'s fill disappear. **Neither shows
  in the frozen corpus** (no `color_hint` there moves `fill-opacity`, and there is no `solid`
  `cloudform`). **They are latent divergences, not a break in today's drawings.**
- **⚠ The GitHub CI was not waited for** (author's ruling, conventions §2-10).

### v2.13.35 — a wash named on a line is a broad pale sweep (Build 922, 2026-08-17, ledger I-279, I-289)

**This is the cycle where a wash finally appears on the lines and arcs that asked for one.**
Of the 3,458 works in production, **567** are written that way, and **490 of them (86.4%) were drawn nowhere at
all** -- 354 dropped because no closed shape stood before them, 136 dropped because the shape before them
already carried a surface. **The remaining 77 were moved onto some other shape that never asked for it.**

- **`Surface: wash` now stays on the line and the arc:** the surface words that speak about the run of the mark
  went from **two to three** (grain, bleeding, wash). **The three do not land in the same place.** Grain and
  bleeding raise the sheet's own two quantities (engine 37); **a wash says nothing about the sheet.** A wash is
  how the ink was diluted, so **the renderer draws it as a band three times as wide at 0.35 of the opacity.**
- **The width and the darkness of a mark are now decided in one place:** all **fifteen** call sites of
  `_stroke_width_px` were routed through two entrances (`_mark_width_px` and `_nominal_mark_width_px`).
  **Seven of them are reachable from an open shape**; on a closed shape the entrance passes straight through,
  so no closed drawing moves. **The prototype had missed the arc path** (`_render_arc_hand_stroke`); counting
  all fifteen is what closed it.
- **One place the contract did not name:** `MARK_SURFACE_WORDS` has two readers, and **the second one looked
  the word up in a table** holding only grain and bleeding. **Adding wash alone made every drawing with a wash
  on an open shape raise an exception.** The lookup now returns the support unchanged when a word raises none
  of the sheet's quantities. **No coefficient or branch of grain and bleeding was touched.**
- **Ledger I-289 was closed in the same version:** the frozen corpus held only four `display` cases and **all
  four used `pen`**, so **not one case went through the texture-filter branch** (SVGs carrying
  `filter="url(#texture-` in engine 37: **0 of 597**). Cases for the four tools that do emit a filter bring it
  to **5 of 606**.
- **One premise of the contract was false:** "drypoint writes no filter, so it never appears" is right in its
  first half and wrong in its second. **Three places name `url(#texture-drypoint)` outright** -- the burr.
  The burr is drypoint itself, so the acceptance was written to the measurement: **the general branch fires
  zero times and the burr once.** A drypoint case was added as the witness, because **a claim that something
  never appears is vacuous with nobody to check it against.**
- **The corpus went from 597 to 606 cases. Only the nine new ones are new; the existing 597 did not move a
  byte** (the accepting side compared 597 manifest digests). **`ddl-engine-20` did not move at all** -- the ddl
  corpus holds no case with a wash on an open shape.
- **Three coerce goldens moved, and the repair lost every witness it had:** `H-06`, `H-10` and `H-13` were
  **the only cases that fired `_with_surface_on_a_closed_shape`**, so rebaking them as they were would have
  left **a golden that stays green even if the repair itself is deleted**. A witness case was added, putting it
  back at `branches reached: 32 / with a witness: 32`.
- **Six of the eleven perturbations matched the prediction:** three reddened more than predicted (+1, +3, +2)
  and **one missed entirely** -- no case added by this work goes through the site the contract named
  (`_surface_dab`). **`filter="url(#texture-` is written in fourteen places in `renderer.py`**, not the five
  the contract read. **A perturbation with real discriminating power was written instead** (dropping
  `use_filters` upstream of all fourteen), and **five tests were measured going red.**
- **`brush_thick` alone puts only 2.10 times the ink area on the sheet for three times the width** (every
  other tool lands between 3.00 and 3.96). The taper of the bristle and where the sheet cuts do not scale with
  the width. **Whether it needs a ceiling is undecided** -- 32 of the 567 works in production use it, and none
  of them was on the contact sheet the author ruled from.
- **The GitHub CI result was not waited for** (author's ruling, conventions §2-10).

---

### v2.13.36 — A work says which group may read it (Build 923, 2026-08-17, ledger I-191)

**Until now a work could be visible for two reasons** -- the default range membership decides (`admins` see everything, `leaders` their own organisation, `users` their own works), and an ACL written one work at a time. **A third has been added: the work itself says "this group may read me".**
When the works to be shown are a set rather than a list, the ACL has to be written row by row, and **`history_acl` in production holds 0 rows to this day** -- per-work sharing has never once been used.

**The shape follows a Linux filesystem** (author's ruling, 2026-08-17). The owner is `user_id`, the group is a new `share_group_id` column, and the read bit is `for_share`. **Nothing corresponding to world is created.**

- **Two columns, and neither does anything alone:** `history.for_share` (defaults to `0`) and `history.share_group_id` (defaults to `NULL`). **A work is readable only when the bit is up AND the group matches.** The bit alone is a permission with no destination; the group alone is a destination nobody opened. The index `ix_history_for_share_group` was added. **The startup migration is idempotent** -- opening a column-less database twice gives the same result.
- **Raising the bit without naming a group fills in the owner's own organisation group** -- the way a new file takes the group of whoever made it. **Only an administrator may name another group** (`admins`; 403 otherwise). **That 403 applies only when a group is named** -- `chmod g+r` asks nothing of the group the file is in, so re-opening a work its owner had opened before needs no administrator rights.
- **Dropping the bit leaves the destination:** `chmod g-r` does not forget the group. **Raising it again returns to the same destination** (the order is **named > the destination the work already carries > the owner's organisation**). Clearing it would silently re-aim the work the next time the bit went up.
- **The flag widens reading only:** `_writable_by` did not move by one line. **A work another account has marked cannot be starred by the reader.**
- **Lineage nodes and edges follow, the colophon does not** -- the flag's clause sits on the same branch as the ACL, the one that is handed a work id, and **`list_okugaki` is the only call that is handed none**. **The raw-SQL full-text path goes through the same predicate** (a leak there does not read as "too visible" but as "invisible only when searched for").
- **API:** the bit is raised through `PATCH /api/history/{item_id}/for-share`. The listing narrows with `GET /api/history?for_share=true`, and **the same query argument was added to the two lineage routes**. **The route total moved 95 -> 96** (`EXPECTED_ROUTE_COUNT`). **Six additions were declared to the frozen API-surface guards rather than the four the contract listed** -- the two lineage routes the stage touches were already carried in both guards' frozen files.
- **web:** the canvas mark (`Mark for sharing` / `Remove share mark`) **had its receiving end finished on 2026-08-16**, so this round only passed it a handler from the page. **The `Shared only` filter sits in both the history strip and history management.** **Four places build a listing request**, and **the test asserts the number four itself** -- a test that named three would stay green with the fourth still missing.
- **cli:** `--for-share` was added to `history` and `history-export`.
- **Two implementation decisions the contract did not carry were ruled to stand** (author, 2026-08-17) -- **(1) the filter button on the history strip** (the contract named only the one in history management; without it the fourth request builder never runs in the product) and **(2) the order the destination is chosen in when the bit goes back up** (the contract's table said "the owner's organisation when omitted", which overwrites the destination that dropping the bit had kept).
- **What production sees:** `history` holds 3,486 rows, and **the default is `for_share = 0`**, so **no work changes who can see it on the day this is deployed**. The account holding 3,484 of them is the only member of organisation group `default`.
- **Verification:** server **3,427 passed / 31 skipped** (+14), cli **237 passed** (+2), web **449 pass / 0 fail** (+3), `npm run check` **268 files / 0 errors / 2 warnings**, `lint:i18n` **1,078 strings / 0 warnings / 0 errors** (+2). **17 perturbations applied 18 times with no misses** (one was split across the two guards). **The fourth frozen-API-surface guard stayed green under every perturbation**, and that is not a miss -- `HistoryItem` is not among the 78 frozen names that guard compares, so nothing declared there measures a single line, which the contract had measured and foretold on the day it was issued.
- **The GitHub CI result was not waited for** (author's ruling, conventions §2-10).

---

### 2026-08-17 — Only names that are actually measured may be declared (**no version**, checks and tooling only, ledger I-305, I-258)

**One declaration in the frozen API-surface guard was measuring nothing.**
`test_t8` freezes the shape the API had before permission groups, **78 names** of it, as a digest. A sanctioned addition is **named in a declaration table, and the key is taken back out before the digest is taken**, so the one change is allowed and everything else is still measured byte for byte -- a good mechanism. **But the table is read only inside the loop over the frozen names**, and **`HistoryItem` is in neither the 78 nor the three changed schemas.** Anything declared for it was never read, while the table read as coverage.

- **Measured**: the table names **13 schemas, 14 keys**, and **exactly one entry was inert** -- `HistoryItem` (two keys, `catalog_mode` and `svg_bytes`). **The other 12 schemas are live.**
- **The fix (author's ruling)**: **a declaration for a name that is not frozen is red rather than silent.** The inert row is gone and the same assertion covers all three declaration tables.
- **Discriminating power**: **one perturbation, 1 failed / 16 passed** (the control is the 17 passed before it). **The first attempt replaced the line and took a live declaration out with it**, so the digest alone could have reddened it -- it was re-aimed with both on one line, and the failure was attributed by its message.
- **The guard's reach did not widen.** `HistoryItem` itself is still outside it. What changed is that the table can no longer say something untrue.
- **The frozen-corpus regeneration check now belongs to CI (ledger I-258, author's ruling).** It is not an acceptance criterion, no perturbation is aimed at it, and the accepting session no longer runs it by hand. **Measured on the day of the ruling, CI already did exactly that** -- `reference-corpus.yml` fires on pull requests and pushes to main, and three jobs re-run the generators and require byte-identical output. **It was work to remove from contracts, not work to add.**
- **Together with "the CI result is not waited for" (ruling of 2026-08-16), drift is now caught after the push by a job nobody reads.** The three past misses (the engine 10 platform drift, the retired `contact` key, the silverpoint rename) happened in exactly that shape.

---

### v2.13.37 — The server keeps answering while a work is baked (Build 924, 2026-08-17, ledger I-284)

**While a heavy work was being saved, one request stalled for a full 4.65 seconds.** The bake (SVG to PNG) ran on a thread of the same process as the API, and **the rasterizer holds the GIL for the whole rasterization**, so nothing else moved meanwhile (measured: during a 9.00-second bake, a companion thread was stopped for **8.93 seconds, 99.2%**). **The bulk rebuild had already been moved to child processes**, and the same reason applied to the per-save path, which had stayed on threads.

- **The child bakes, the parent writes.** A resident `ProcessPoolExecutor` lives in `thumbnails.py` (**created lazily**) and only the rasterization goes to it. **The write into `thumbs.db` stays in the parent.** Its width comes from the existing `INKU_THUMBNAIL_WORKERS`. **No new environment variable and no new administrative setting were added.**
- **A broken pool is rebuilt once.** Shutdown folds it in `_lifespan`, with a flag that **keeps a save arriving afterwards from reviving the child**.
- **This is not a speed change.** What changed is whether the server can do other work while a bake runs; **the bake itself is not one millisecond faster.**
- **Measured (before -> after, same session, one run each)**: **requests over one second, 1 -> 0**; **slowest 4,650 ms -> 255 ms**. **The median did not move** (167.0 -> 142.2 ms) -- what makes it is the drawing, which is outside this contract. **The save round trip going 13.8 -> 8.7 seconds is a by-product** (gzipping and writing out a 7.3 MB SVG could not proceed either while the bake held the GIL). **One run each, so it is not quoted as a saving.**
- **A light work becomes slightly slower** (7.2 -> 12.4 ms), the round trip of handing the SVG to the child and taking the PNG back. **The first bake after a start pays 0.32 s for the child to come up** (no bake after that pays it). **Whether to pay it in advance is ledger I-306.**
- **Tests bake in-process by default.** Only the three marked `@pytest.mark.child_bake_pool` start a child. **Without that, every test touching a save would pay a spawn** -- one file (18 tests) went **7.08 s -> 16.16 s**.
- **The merge conflicted** -- the branch was cut from `3f56b7c2`, and **I-191 landed in main the same day, so both sides had stamped a build on the same four version-marker lines**. **The product code did not overlap at all.** The merged tree was numbered once.
- **Verification**: server **3,434 passed / 31 skipped** (+7), cli **237 passed**, web **449 pass / 0 fail**, `npm run check` **268 files / 0 errors / 2 warnings**, ruff clean on both trees, `check_docs.py` consistent. **Nine perturbations reddened 30 acceptances between them, with no misses** (the implementation predicted 19, the contract 13). **The reference corpora did not move by one byte.**
- **The GitHub CI result was not waited for** (author's ruling, conventions §2-10).

### Android — The wobble gate splits in two and the fill attribute reads one judgement (android `2.1.4-android.41`, 2026-08-17, ledger I-278, I-298)

**The server settles a judgement once, in one place, and whatever needs it reads it there. The port
held copies of the same judgement** — two of them, each telling a different lie. This round gave both
one place to read.

- **The wobble gate splits into the server's two (ledger I-278):** the server keeps one gate for
  **lines** (`renderer.py:780`, the axes `position_x` / `position_y`) and one for **contours**
  (`:792`, those two plus `radius`), and **neither lets `quality` `none` or `pink` through**. **The
  port had folded them into one that read all three axes from every call site and excluded only
  `none`.** **Two inputs diverged** — **`pink`** (a bleed the server draws with a blur and lets no
  variation reach; the port drew the blur *and* wobbled) and **a line asked to vary on `radius`
  alone** (straight on the server).
- **The exclusion lives in one place:** a single `NO_VARIATION_QUALITIES` both gates read. **The axis
  lists stay separate, as the server keeps them** (`PATH_VARIATION_DIMS` / `CONTOUR_VARIATION_DIMS`).
  **⚠ The exclusion is written negatively** — with `Quality` holding five words it names the same set
  as "the three that do wobble", but **a sixth word added to the schema joins the wobble under the
  exclusion and is silently dropped under the enumeration.**
- **All 23 call sites were read one at a time:** **only two are line-side** (the machine pole in the
  `"line"` branch, and `renderHandStroke`); **the other 21 are contour-side.** **A shape branch asking
  three times corresponds to the server solving `varied` once per branch** — the meaning did not
  multiply. **`edgeContourWithAnchors` uses the line tool inside but is contour-side**, because the
  server's `_render_corner_shape` reads the contour gate: **using the line tool inside is not the same
  as reading the line gate.**
- **The fill attribute now reads one judgement (ledger I-298):** `ServerRendererStyle.strokeAttrs`
  **reads `fillsInterior` once at the top and uses that one variable for the `fill` value and for all
  seven `fill-opacity` branches**, the shape the server's `_stroke_attrs` has. **It used to decide out
  of "does the primitive have an inside, or was `filled` written"** — a set that knew nothing about
  `surface.texture` and did not hold `cloudform`, so **the same request took different roads depending
  on how it was spelt.**
- **The re-decision added in the I-280 round became redundant and is gone:** the geometric road writes
  `attrs.fill` as it stands. **Now that the value carries the judgement, asking again there would be
  the copy this cycle came to remove.** **`strokeAttrs` also lost its `primitive` argument**, which no
  longer had a reader.
- **⚠⚠ The other place the contract called redundant was not redundant (the issuing side was wrong):**
  the contract said `renderBodyShape`'s `regionFill` could go too. **`regionFill` is not a copy of
  `fillsInterior` but a separate quantity** meaning **"the interior was drawn as marks, so the body
  element stays open"**. **The server holds the same quantity** (`renderer.py:6235`
  `_body_attrs_for_contour_stroke`, whose docstring states that with `region_fill=False` the body
  carries no fill either, and which six call sites pass). **Removing it would double a flat fill under
  the mark group on hand-drawn filled shapes and diverge from the server.** **The implementation
  stopped and reported instead of applying stage 4's second half, and the author ruled on 2026-08-17
  that it stays.**
- **⚠ That is when it emerged that no gate measured which element did the filling:** applying stage
  4's second half and running the whole suite **reddened nothing**. **The existing parity compares
  only the `d` of the fill marks, and the colour comparison is a set, so a newly filled body element
  leaves the set unchanged.** **The ruling added T-232 in the same round** — on both the server's
  baked `03_square_filled.svg` and the port's redraw, **the hand tool leaves its body open while the
  mark group fills, and the machine pole fills the body and has no mark group.**
- **Nine gates (T-224..T-232), and twelve perturbations** — the contract's nine plus three the
  implementation added — **all through `perturb.py`** (all twelve restored byte-identical; `git
  checkout` was never run). **The runner detects `^e: ` so a failed compile is not read as a green
  run** (proven twice by breaking it on purpose).
- **⚠ Four perturbation predictions missed, in two shapes, both "failing to count a reader":**
  **(1) the fallout was counted only from the frozen corpus, never from existing tests that call the
  product function with input they build themselves** (three tests across P-4 and P-8); **(2) a case
  outside a guard's own list was read as "compared"** —
  `testMaterialOutlinePointsAndDashArrayExactParity` walks four named cases rather than every key in
  the index, and the case in question was not among them. **⚠ P-9' matched on count (4) while two of
  the names were wrong** — the errors cancelled.
- **The full suite went 376 → 385 (+9). On the merged tree, XML 65 / tests 385 / failures 0 / errors 0
  / skipped 0**, and `test_android_reference_fixtures_are_current.py` **4 passed**. **The frozen
  corpus was not touched** — **its 51 sheets carry zero `pink` and zero lines varying on `radius`
  alone**, so it cannot measure this change at all and every gate is placed on a property.
- **One follow-up filed (since numbered I-307):** **the machine pole's line carries a wobble branch
  the server does not have** — the server draws a `rotring` line as one straight line and calls no
  gate, while the port reads a gate and writes a wobbled `<polyline>`. **No corpus sheet has a
  `rotring` line with a variation, so nothing reddened.**
- **⚠ One more vacuous test surfaced (not fixed):** `test03SquareFilledExactParity` compares the
  `fill-stroke-v1` group, but **`03_square_filled` draws its interior with `fill-texture-v1` and
  carries no `fill-stroke-v1` at all** — **both sides are empty, so nothing can redden it.**
- **⚠ The GitHub CI was not waited for** (author's ruling, conventions §2-10).

---

### 2026-08-17 — Frozen output is baked on the machine the release runs on (**no version**, checks and test environment only)

**Checks that hold the CPU moved to a test-only container on the deployment host.** Development stays on macOS.

- **Measured before deciding**: same commit, same tree -- **the Mac 3434 passed / 31 skipped / 504 s**, **the linux container 3432 passed / 2 failed / 31 skipped / 276 s**, with **3,465 collected on both**. The draft's guess that eight cores are eight cores was wrong: the container is **1.8x faster serially and 6.1x in parallel (82 s)**. One file is slower there (`test_single_user_mode`), so the ranking is not a rescaling.
- **⚠ Both red tests look past the quantisers.** What the product draws is byte-identical on either machine (**four generators rewrote 837 files, 0 differ**). What split was the port's reference fixture, which freezes raw doubles, and the paired test that removes the quantisers on purpose.
- **Frozen output is now baked on linux, where the release runs.** `renderer_variation_primitives.json` was rebaked there (**six values differ in the last digit**: `-1.7282983464997077` against `-1.7282983464997073`). The port compares those fields at a 1e-9 tolerance and the difference is 4e-16, so the JVM suite is unmoved (385 tests, 0 failures). **F-1 compares bytes, so it can only be asked where the fixture was baked, and says so on darwin instead of failing** -- the cost being that a fixture staled on a Mac is caught by the container run, not by the Mac.
- **Which cases a one-ULP nudge reaches depends on the host libm**: darwin moves five of engine 28's six splits, glibc the sixth. The expectation is recorded per platform, and a new test asserts the two recordings union to exactly those six.
- **The port's JVM tests moved to the same machine in a second image** (author's instruction): `eclipse-temurin:21-jdk` plus the Android SDK, 1.83GB. **385 tests, 0 failures -- the same as the Mac.** AGP 8.9.1 asks for `build-tools;35.0.0` even at `compileSdk` 36, and a second run finished in 6 s with every task up to date while the previous run's XML still read 385, so the count now only reads files this run wrote and `--rerun` forces execution.
- `pytest-xdist` joined the dev group. It is in no release image (`uv sync --frozen --no-dev`).
- **Four SPEC passages (two bilingual pairs) were revised.**

---

### Android — The machine pole's line does not waver, and the fill guard says how many it compared (android `2.1.4-android.42`, 2026-08-17, ledger I-307)

**Both halves are about places nobody was looking.** The port held one branch with no counterpart on the
server, and beside the guard that should have covered it sat a test **that stayed green whatever broke**.

- **The branch with no counterpart is gone (ledger I-307):** the server answers `primitive: "line"` with
  `weight: "rotring"` by drawing `dwg.line` once, reaching **neither the variation gate nor the material
  layer** (`renderer.py:7688`). **The port read the gate and wrote a wavering `<polyline>`.**
  Nothing went red because **the 51 frozen drawings hold no `rotring` line carrying a `variation`** — of
  the four instructions that carry one, only a single line does, and its tool is `pencil`.
  **The acceptances could only be placed as properties.**
- **The material group is called from the same road the server calls it from:** the port called it **only
  from the machine pole's road**, where the server calls it **only from the hand's** (`_render_hand_stroke`).
  The call is gone, and the thin delegate that lost its only caller went with it.
  **⚠ Not one byte of today's drawing moves** — the six keys of the material table (`pencil`, `chalk`,
  `brush_thin`, `brush_thick`, `crayon`, `pen`) do not include `rotring`, so the call always returned null.
  **Perturbing that stage back reddens nothing**, which leaves a measurement standing: **no test asks
  whether the machine pole comes out clothed.**
- **A vacuous guard now points at a group the reference actually holds:**
  `test03SquareFilledExactParity` pulled the `fill-stroke-v1` group from both sides, but
  **`03_square_filled.svg` holds none of it** — it was comparing nothing with nothing. What the reference
  holds is `fill-texture-v1`, and **34 marks live in it**.
- **The guard says how many it compared:** **the 34 is not written by hand** — the group's own class
  declares it as `marks-34`, and the guard reads that number on both sides and matches it against how many
  it extracted. **Zero marks is red.**
- **⚠ That guard was not only vacuous but redundant (found on the accepting side, on the day of issue):**
  `testEveryReferenceSvgMatchesOnPathsPointsAndDashes` **already compares the whole ` d="…"` sequence of
  all 51 drawings**, so those 34 were compared outside the group. **What the corpus-wide walk does not see
  is which mark sits in which group**, so the repaired guard measures that. **The other four `*ExactParity`
  tests are subsets for the same reason** (filed in the ledger inbox).
- **⚠ One ruling arrived mid-flight:** stage 1 reddened two existing acceptances — **`line()` defaults its
  `weight` to `"rotring"`, and two tests used "a machine pole's line wavers" as their control** (the
  contract had not measured this: an error on the issuing side). **The ruling was to move the control to
  `pen`.** The machine pole's claim is now made once, by the new acceptances.
- **⚠ A second error on the issuing side:** the contract predicted two corpus guards would be dragged
  along, but **the one comparing the `d` sequence does not redden** — changing a class name or `marks-N`
  moves no `d`. **The measurement is one.**
- **Verification**: **387 tests / 0 failures / 0 errors / 0 skipped on the merged tree**
  (66 XML files, 53s, in the test-only container on pentala). **The `@Test` total went from 385 at the
  base to 387 on the branch** (the two new acceptances; the repaired one changed neither its name nor the
  count). **`test_android_reference_fixtures_are_current.py` 3 passed / 1 skipped.**
  **The frozen corpus did not move by a byte.** **Only `android/` was touched** — four files, +224 / −27.
  **The four perturbations were run on the branch by the implementing session and matched the frozen
  prediction in both count and name** (same agent model, so the accepting side skipped re-running the
  branch and re-applying the perturbations, per convention §2-1).
- **⚠ GitHub CI was not waited on** (ruling, conventions §2-10).

### v2.13.38 — a work drawn by a fallback says so, and refining from one asks first (Build 925, 2026-08-17, [I-292])

**When Stage 2 (composition) fell back, a deterministic substitute wrote the Score and nothing recorded that it had.** The response carried `compose_fallback_used`, but that field lives only in the one response and disappears when the work is saved. **A work whose interpretation fell back was marked; a work whose composition fell back was not** — the same broken link between the words and the picture, but only one of them visible. In production, 33 of 3,459 works carry a Stage 1 fallback record and 0 carry a Stage 2 one.

- **One column (`compose_fallback`), holding three states**: a reason string (it fell back), `"none"` (it did not, said explicitly by the sender), or no record at all. **Using `null` for "did not fall back" would make a new work indistinguishable from the 3,459 saved before the column existed**, so senders write `"none"` as well.
- **There are three writers, and the busiest is the server itself.** Measured before any code was written: the main path for saving a drawn work is `render.py` calling `_add_history_item` directly, and **web and cli have zero lines that stack `interpret_fallback`** — the response arrives after the row is written, so a client cannot send the fact back. **The author ruled that the server writes it too, in exactly the shape Stage 1 uses**; the web and cli senders stack it as well.
- **One badge per layer** — a work where both fell back shows two — and **the generation drawer always shows all three states** (yes / no / no record). **Nothing is backfilled**, so the existing 3,459 works stay at "no record" (the `ALTER TABLE` carries neither `DEFAULT` nor `UPDATE`).
- **Refining from a marked work asks once.** The memory is a set of work ids inside the page, so **no state is created on the server**. **Nine call sites ask** (submit, replay, the performance / layout / interpretation variations, candidate generation, and the description / grain / DDL edits reached from the lineage), and a cancel path was added so a refusal reaches the caller — without it a waiting refinement never returns.
- **The English term is `Score fallback`.** `Composition fallback` was rejected because `composition` is the placement word here (`composition_seed`), and the glossary now records that.
- **The sketch fallback stays display-only** (no column, no badge): when that layer does not answer, the description is read as it stands, which is not a broken link.
- **Four tests that freeze the API surface went red** where the implementation had predicted none, because `HistoryPostBody` and `HistoryItem` each gained a field. The baseline was rebaked in its original format (three lines moved) and the other three now declare the added field by name.
- **The implementation tightened two of its own guards** after perturbing them: the sender census was matching the word anywhere in the file and survived both perturbations, and a web acceptance was reading only the key's name. Neither would have been found by treating a perturbation that does not redden as redundant.
- **Verification on the merged tree**: **3445 passed / 31 skipped** in the test container on pentala (3435 / 31 at the base), **cli 240 passed** (237), **web unit 463 / 0 failed** (449), **`npm run check` 270 FILES / 0 ERRORS / 2 WARNINGS**, **`lint:i18n` 1085 strings / 0 warnings / 0 errors**, ruff clean. Frozen output: **`rewrote 134 files; 0 differ` (`exit 0`)**. **All 12 perturbations were applied; 5 of the 12 predictions were right**, and the completion report explains each of the seven misses. **No drawing, engine version or reference corpus moved.**
- **The GitHub CI result was not waited for** (author's ruling, conventions 2-10).

### v2.13.39 — while you wait, the page names the layer that is working (Build 926, 2026-08-17, [I-302])

**A drawing passes through four layers in turn** — sketch (Stage 0.5), interpretation (Stage 1), composition (Stage 2) and performance. **Three of them call a model once each, which is where nearly all of the waiting is. Yet only two signals ever reached the page**: interpretation finished, and everything finished. **So the first half of the wait said "Interpreting…" while the sketch layer was working, and the second half said "Structuring…" while the drawing was being performed. The indicator was not lying; it had nothing to read.**

- **Two events were added** to the NDJSON of `/api/paint/stream`: **`sketch`** (only on requests where the layer ran — grain, whether it fell back, token counts, elapsed) and **`score`** (the moment Stage 2 and coerce are done and the Score will not change again — instruction count, model, token counts, elapsed). **Neither the prose nor the Score body travels here**: `done` already carries both, and a description may run to 100,000 characters.
- **The indicator stops guessing and follows the signals.** Two strings were added (`sketching from life…` / `performing…`); **the four existing stage strings are unchanged, to the character**.
- **The response shape did not move by a byte.** `done` and the non-streaming `/api/paint` are as they were, so **CLI and Android needed no change**. **`stage1`'s `elapsed_ms` still includes the sketch**, deliberately — changing it would quietly move the meaning for everyone already reading it, and the breakdown is now available by subtracting the `sketch` event's `elapsed_ms`.
- **⚠ Which side a failure falls on moves one stage earlier, on requests where the sketch layer ran.** The rule is unchanged — a failure before the first event is HTTP, a failure after it is an `error` event in the body — but **the first event is now `sketch` rather than `stage1`**. So a Stage 1 failure on a sketched request arrives as HTTP 200 with `{"event":"error","status":502}` in the body instead of HTTP 502 (**with the layer off it is still 502**). **What the page shows does not change**: both paths hand the same detail and status to the same reader. Two acceptances hold this, and `api_paint_stream`'s docstring says it.
- **Reading the NDJSON moved to `web/src/lib/paintStream.ts`** with no copy left in `+page.svelte`. **Unknown events are still read and dropped** — that tolerance predates this change, so no separate "widen first" commit was needed.
- **⚠ Per-stage elapsed times are not stored** (this change is about what is shown). Storing them would need its own ledger item.
- **⚠ A blind spot was found in the frozen-output check.** With a drawing-changing perturbation applied, the generator fails its own guard **before writing anything**, so the byte difference stays at zero. **The mechanism does raise `exit=1`, so what must be read is the exit code and the `gen_… exited nonzero` line**, not the "0 differ" wording. Filed as ledger [I-310].
- **⚠ Acceptance number T-242 collides with [I-292]** (an issuing-side mistake). Nothing asserts uniqueness, so nothing reddens.
- **Verification on the merged tree**: **3454 passed / 31 skipped** in the test container on pentala (3445 / 31 after the [I-292] merge — the +9 is exactly this change's acceptances), **cli 240 passed** (unchanged), **web unit 467 / 0 failed** (463 → +4), **`npm run check` 271 FILES / 0 ERRORS / 2 WARNINGS** (the two known a11y warnings), **`lint:i18n` 1087 strings / 0 warnings / 0 errors**, ruff clean. **All 13 perturbations reddened something; none was a miss** (8 of the 13 predictions were exact, and the completion report explains the five that were not). **No drawing, engine version or reference corpus moved.**
- **The GitHub CI result was not waited for** (author's ruling, conventions 2-10).
