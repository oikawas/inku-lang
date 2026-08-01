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
