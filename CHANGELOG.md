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
