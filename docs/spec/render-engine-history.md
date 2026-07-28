# Render engine version history

**An index of the performance (drawing) versions alone, newest first, one section per version.**
inku draws the same JSON Score a little differently every time. **The version of *how* it draws
is the render engine version**, counted separately from the product version (`v2.7.8` and so on).
**This document is the way in**; the detail lives where each section points.

**Until this file existed, nowhere held all versions in one place.** The record was spread across
four places (gathered into this document on 2026-07-28) — prose in `SPEC.md` (engines 5 through 10), `SPEC.ja.md` §15.9–15.11 (13 through 15),
`server/reference/README.md` (12 and 15), and the changelog entries.

## When the version goes up

"Versions and identity IDs" below rules it. **There are two reasons.**

1. **The performance changed** — the same Score with the same seed now draws differently
2. **The vocabulary that can be performed grew** — raise it even if not one byte of output moved

**A rename does not raise it.** Conversely, **raising it freezes a reference corpus**: only the SVGs
the version actually moved go into `server/reference/render-engine-<version>/`, while the manifest
carries the digest of every case.

**The block cannot be restored, but the prints can be kept.** Freezing is the proof print that makes
that possible: the **actual output** from a fixed set of inputs (the SVG, its element counts,
classes, and a coordinate digest) is stored, and CI fails if regenerating an existing case is not
byte-identical. When it differs, the drawing changed, and the engine version rises. **A version
number carries only one bit: that something moved. What moved, and how, can only be answered by
comparing the outputs themselves.**

## The versions

**"Moved" and "unchanged" are measured**, from the manifest's `changed_from_previous` and the number
of SVGs the directory holds.

| Version | Product version | Build | Frozen | Cases | Moved | Unchanged |
|---|---|---|---|---|---|---|
| **15** | v2.7.8 (v2.7.12 folded in) | 717 / 721 | 2026-07-27 | 350 | **318** | **32** |
| **14** | v2.7.0 | 709 | 2026-07-25 | 347 | **126** | **221** |
| **13** | v2.6.0 | 707 | 2026-07-25 | 228 | **8** | **220** |
| **12** | v2.5.0 | 706 | 2026-07-25 | 220 | **199** | **21** |
| **11** | v2.4.8 | 698 | 2026-07-24 | 220 | **220** | **0** |
| **10** | frozen by v2.4.4 | 694 | 2026-07-23 | 220 | (first) | — |
| 1–9 | — | — | before freezing | — | — | — |

**What stayed still is what explains the version.** The version where everything moved (11) says,
through its zero unchanged cases, that it changed how numbers are written and not what is drawn.

## Principles that outlast a version

**The record of each version is in the sections below. What stands here is what holds across versions.**
Moved out of `SPEC.md` §12.1-12.9 on 2026-07-28.

### Deterministic and Non-Deterministic Layers (v2.4.6)

**The pipeline alternates between LLM layers and deterministic ones.** Where the
system reproduces and where it varies differs layer by layer. Only deterministic
layers can carry a version, and this table draws that line.

| Layer | Implementation | Deterministic | LLM calls | Version |
|---|---|---|---|---|
| Input (description) | text written by the author | — | — | `dh1` (description identity) |
| **Stage 1 interpretation** | `interpreter.py` | **no** | 19 | none (`stage1_prompt_digest` records provenance only) |
| **Plugin expansion** | `expand_plugin_ddl` | **yes** | 0 | `ddl_engine_version` |
| **Stage 1.5 expansion / variation** | `expand_intermediate_ddl` | **yes** | 0 | `ddl_engine_version` |
| **Stage 2 composition** | `composer.py` | **no** | 19 | none (`stage2_prompt_digest` records provenance only) |
| **coerce / validation** | `coerce_score` | **yes** | 0 | `ddl_engine_version` |
| JSON Score | `schema.py` | — | — | `version` (`"0.1.0"`, the schema version) |
| **Renderer performance** | `renderer.py` / `stroke_engine.py` | **yes** (given a seed) | 0 | `render_engine_version` |
| Output (SVG) | the saved work | — | — | `rh3` (work edition) |

**The deterministic layers are not adjacent.** Stage 2's LLM sits between Stage 1.5
(DDL→DDL) and coerce (Score→Score), so "DDL through to Score" cannot be one baseline.
Each deterministic stretch gets its own corpus instead ("Comparing generations through the corpus" in this document).

**Why LLM layers get no version:** the same prompt and the same model still vary.
A version number implies "same version, same result", so attaching one where that
does not hold would be a lie. Instead the digest of the prompt actually sent is
recorded per work — a weaker claim that **can assert "the input conditions differed"
but never asserts "the output will change"**.

> `stage1_model`, `stage2_model`, and `stage*_prompt_digest` record **what was asked
> for**, not the environment that ran it. Two works carrying the same record are not
> guaranteed to produce the same Score. That is not a defect; it follows from the
> principle that variation is part of the specification.

### Versions and Identity IDs (v2.4.5)

**These are separate namespaces.** Numbers that look close are not linked.

| Name | Versions what | Current | Incremented when |
|---|---|---|---|
| `render_engine_version` | the drawing engine | `14` | **the same Score and seed perform differently, or the performable vocabulary grows** |
| `ddl_engine_version` | deterministic transforms (expansion, coerce, validator) | `1` | the same input and seed produce different output |
| `ddl_version` | the DDL language itself (grammar, keywords) | `1` | grammar is added, changed, or retired |
| Score `version` | the JSON Score schema | `0.1.0` | the schema's structure changes |
| `APP_VERSION` / `server/pyproject.toml` | the product release | v2.5.0 | per release |
| `web/BUILD_NUMBER` | build serial | 706 | **moves for UI-only changes too** |

**A version also rises when the performable vocabulary grows** (author's ruling,
2026-07-25). Adding a tool or a surface moves no existing corpus case, because
**no case uses the new word — the output does not shift by a byte and CI stays
green**. Bumping only when results change would let vocabulary be added without a
version, leaving "an engine that can perform the word" beside "an engine that
cannot" under the same number. **The meaning of a version — same version, same
result — then breaks on the input set rather than the output.** A vocabulary
version confirms the existing cases are byte-identical, then moves forward and
freezes that identity as the artifact: **the proof sheet showing that adding a
block moved none of the existing prints.**

**Renaming a tool or a word does not raise a version** (author's ruling,
2026-07-27, writing down the precedent set at v2.7.9). A rename such as `hair` →
`silverpoint` **does move the string that comes out of the same input**, so it
meets the letter of "when the output changes" above. But **only the name moved:
the layer behaves identically** — the tool draws at the same width in the same
hand. Raising the version would **put a generational boundary in the provenance
of works that differ by a name and nothing else**.

- **A rename re-freezes the corpus in place** rather than opening a new version
  directory. Render engine 15 and the coerce golden were re-frozen that way at
  v2.7.9. **The DDL corpus was missed in that same commit, and CI went red on
  eight consecutive pushes** until v2.8.0 / Build 727.
- **The identity guard cannot tell a sanctioned rename from an unsanctioned
  rewrite.** It fires *after* writing, and **firing once while the second run
  exits 0 byte-identical is the property it defends**. Accept the firing only
  when you already know the change is a rename.
- **Growing the vocabulary does raise the version** (above). **Adding a word and
  renaming one are different acts.**

`ddl_version` and `ddl_engine_version` **start counting at 1** (author's ruling,
2026-07-24). No other version shares those numbers, which keeps the separate
namespaces from being read as linked. They step in whole integers.

**The work-edition ID is `rh3`** (details in `SPEC.md`). Identity
comes from `score`, `render_seed`, `render_wild`, the render engine's ID and version, and
`render_color_catalog_id`.

- **`render_build_number` is not part of identity.** It is stamped for UI-only
  changes, so it gave a new edition ID to a drawing that had not changed by a single
  byte. It stays as provenance: worth keeping as history, not worth putting in the
  definition of sameness.
- **The Score-side seed (`composition_seed`) is excluded too** — a different Score already
  yields a different ID.
- **`rh2` is retained as legacy and never recalculated.** `rh2` and `rh3` are
  separate hash spaces and must not be compared to decide sameness.

### Comparing Generations Through the Corpus (v2.4.4)

**Each version of a deterministic layer has exactly one reference corpus: the actual
outputs, frozen, produced from fixed inputs.** A version number carries only one bit.
**What changed, and how, can only be answered by comparing the outputs themselves.**

- **Regenerating an existing case must be byte-identical.** If it is not, the output
  changed, and **the layer version must be incremented**.
- **A frozen version is never regenerated to absorb changed output.** Create the next
  version directory instead.
- **Case IDs are permanent.** They may not be renamed or removed; only added.
- **Corpora are never chained** — one layer's corpus output must not become another's
  input. Chaining them destroys the ability to say which layer moved.
- A corpus fixes **every dependency outside its own layer as a literal in the
  generator**: the color map and every Score field are written out rather than read
  from `COLOR_MAP` or the schema defaults. If output moves while none of the manifest
  identity fields (`corpus_format_version`, `engine_version`, `schema_version`,
  `color_map_digest`) move, **a dependency was left unfixed**.

There are two instances as of v2.4.7.

| Corpus | Location | What it freezes | Cases |
|---|---|---|---|
| Drawing | `server/reference/render-engine-14/` | what `renderer.py` / `stroke_engine.py` perform (SVG) | 347 |
| Deterministic DDL layers | `server/reference/ddl-engine-1/` | **A** = expanded DDL from `expand_intermediate_ddl` / **B** = coerced Score plus `branch_report` from `coerce_score` | 29 (A 15 / B 14) |

**The DDL side splits into A and B because the deterministic layers are not
adjacent** ("Deterministic and non-deterministic layers" in this document). Stage 2's LLM sits between Stage 1.5 (DDL→DDL) and coercion
(Score→Score), so "DDL through to Score" cannot be a single baseline. **A's output is
never used as B's input** — that is the "corpora are never chained" rule above.

The operating procedure lives next to the artifacts (`server/reference/README.md`), and
CI (`.github/workflows/reference-corpus.yml`) enforces byte-identical regeneration with
one independent job per layer.
**The point is to move the versioning discipline from something people remember to
something the machine enforces.**

**Generations are compared like this.** When a version rises, a new directory is
created and its manifest digests are compared against the previous one. Only the case
IDs that moved are listed in `changed_from_previous`, and **only those cases' actual
output is stored**. Cases that did not move are still current in the older version.
"How does engine 12 draw case X?" resolves mechanically by finding **the last version
in which X moved**.

**The number of directories is itself the record of how many times that layer changed.**

**Engine 12 is the first version where this discipline did any work.** Engine 11
declared the master grid and moved all 220 cases, so "store what moved" and "store
everything" were indistinguishable. Engine 12 moved 199 cases and **left 21
untouched**, and what those 21 are is itself the account of what engine 12 did.

- **The 12 `rotring` cases are byte-identical.** Every wobble term in its grammar
  is zero, so de-regularization has nothing to reach. **The machine pole of the
  tool vocabulary sits exactly where it did**
- **The 9 `cloudform` cases are byte-identical for a different reason.** A
  cloudform is written as a Catmull-Rom path by `generate_cloudform_contour` and
  never enters `stroke_engine`, so it carries no material outline layer either.
  Its contour does vary by tool (all ten tool digests differ), but none of that
  variation comes from stroke synthesis. **This is a gap engine 12 exposed, not
  one it created**

The corpus ships with no release: `server/reference/ export-ignore` in `.gitattributes`
keeps it out of `git archive`.

#### The master grid (v2.4.8, engine 11)

**Every emitted number lands on one grid**: six fixed decimal places, a canvas-relative
step of **1e-9** on a 1000-unit canvas. `MASTER_GRID_DECIMALS` in
`inku_server/master_grid.py` is the source of truth.

An SVG scales freely, but **the numbers written into it are fixed-point**, so this constant
is the effective master resolution. Through engine 10 the precision varied by write site
(`.1f`, `.2f`, `.3f`, and seventeen digits wherever a raw float reached svgwrite), which
meant **rulings from 1e-4 to 1e-19 shared one canvas**.

The grid value is bounded from both sides.

- **Below (reproducibility):** `math.sin` differs across platforms by a relative 2e-16.
  Measured, macOS and Linux output starts to diverge **at the eleventh decimal**. The grid
  sits four orders of magnitude above that, so any OS performs to the same string.
- **Above (physics):** stretched across a 100m wall the step is 100nm, finer than the
  wavelength of visible light. The drawing instrument reaches its limit first.

**Trailing zeros are kept.** With a fixed width every number matches `-?\d+\.\d{6}`, so
the artifact itself can be machine-checked for the grid. Trimming would leave `695.45787`
indistinguishable from a raw float, and the claim would rest on trusting the procedure.

**Integers stay integers** (canvas dimensions, `viewBox`). The grid governs values that
carry a fractional part.

**This grid is a different axis from shape fidelity.** Strokes are emitted as chains of
straight segments rather than curves, so the effective resolution of the *shape* is
**2.2e-4** of the artboard (the chord sagitta) — the digits are two hundred times finer.
**At wall scale it is the sampling, not the digits, that binds.**

### The Engine Does Not Go Backwards — Implemented as Printmaking (v2.4.6)

**Past drawing engines are not kept in the system, and no mechanism exists to select
a version.**

- **Replay always runs on the latest engine.** `current_render_engine()` takes no
  argument and offers no choice.
- A recorded `render_engine_version` is **provenance**, not an input to redrawing.
- **Reproducing the edition as it was is guaranteed by returning the saved SVG**, not
  by redrawing it.
- When a redraw finds that the recorded version differs from the current one, the UI
  **says so and nothing more**.
- The DDL side works the same way: reinterpretation always runs on the latest, and the
  result is a new edition.

**This is the stance of printmaking.**

> The carving advances. The block only changes in one direction. The prints that came
> off it remain, but **the block cannot be returned to what it was before the cut**.
> If the application itself is thought of as a work, this is the implementation that
> follows.

The work — a saved SVG with its Score, seed, and edition ID — is **the print**, and it
persists. The engine is **the block**, and only its carved-forward state exists.
Refusing to conflate the two, refusing to warehouse old blocks, is the choice this
design makes.

**The cost has already been paid: the output of engines 1 through 9 is gone.** Neither
the code nor the renderings survive. The reference corpus ("Comparing generations through the corpus" in this document) begins at engine 10.
**That is precisely why prints are pulled while a version is still current.** A corpus
is a **proof print**, taken before the next cut. The block cannot be restored; the
print can be kept.

**Recording only the version number while discarding the output is like noting the date
of the carving and throwing away the print.**

### A PNG Is a Copy of the Performance (v2.7.10, v2.7.11)

**The SVG is the original; a PNG is an image taken of it.** The image may be smaller, and it
may be coarser. **It may not leave anything out.**

#### No rasterizer that drops things in silence

**The PNG path may not use an implementation that skips SVG filters it has not implemented.**
The filters at stake are at least `feTurbulence`, `feDisplacementMap` and `feGaussianBlur`.
They make **the whole of the ground grain and the material layer**, and a PNG that has skipped
them still reads as a finished picture.

**This is a rule about observation, not about performance or fidelity.** A PNG that came
through such an implementation **cannot distinguish "there is no difference" from "the
difference did not come through"**. In inku, whether a work is kept, whether an engine version
is raised, and whether a port is identical are all decided by **reading two pictures side by
side**. Put a lossy copier in that path and **every one of those judgements breaks quietly**.

#### `cairosvg` is not to be used

**`cairosvg` is prohibited** (author's ruling 2026-07-27, removed in v2.7.10). It implements
none of the three filters above and **skips them without raising and without warning**. During
a session in 2026-07 the clean-looking PNGs it produced **came within reach of being used as
evidence four times**. Warnings existed in four places: the CLI's stderr, the server's startup
log, the module docstring, and the `png_rasterizer` record in every artifact. **None of them
helped, because what misleads a reader is the picture, not the log line.** Hence the
disposition this section fixes: **remove, do not document**.

#### An implementation that is wrong is worse than one that is missing

**There is no fallback.** The only implementation is `resvg` (`resvg-py`), and **where it is
absent PNG output stops rather than degrading quietly**. A missing PNG is visible; a PNG with
the texture gone is not.

#### How it is held

`shared/src/inku_analysis/rasterizer.py` is **the only entrance**, and the server, the CLI and
the Android comparison harness all go through it. Three sentinels: **① it is in no dependency
declaration ② no `.py` in the repository imports it ③ it stays unreachable even where the
environment has it.**

> **Sentinel ②'s scope is written as what it does not look at, not as what it does.**
> v2.7.10 named four roots and so missed `android/scripts/`. **A named list can fail to be
> complete; what it cannot do is say so.**

### Release Distribution (v2.4.0)

Releases are distributed as container images. Pushing a git tag `vX.Y.Z`
triggers a GitHub Actions workflow that builds and publishes
`ghcr.io/oikawas/inku-api` and `ghcr.io/oikawas/inku-web` as multi-arch
(amd64 / arm64) images. Users run them with the compose file and `.env.example`
under `deploy/` (`deploy/README.md` is the quickstart). Bundled plugins under
`server/plugins/` (currently Nature.leaves) ship inside the api image.

**Account premise:** there is no self-signup path. Accounts are created only by
an authenticated administrator via `POST /api/users`, so the first way in is the
bootstrap admin created on first start against a fresh database
(`INKU_BOOTSTRAP_ADMIN_PASSWORD`, 8 characters or more). A server started
without it is a box nobody can sign in to (set the value and restart to
recover; databases that already have accounts are left untouched). An empty
string is treated as unset (v2.4.0), and the distributed compose file refuses
to start without a value.

`/api/info` reports `version` as the server implementation version
(`server/pyproject.toml`, made the single source in v2.4.0 and stamped per
release). It is a separate namespace from the web display version
(`APP_VERSION`), but the numbers normally coincide because releases are
repo-wide.

**Developer mode (v2.4.3):** the `INKU_DEVELOPER_MODE` environment variable
decides only whether developer-facing options are shown. With it off, NVIDIA NIM
drops out of the display catalogs (`GET /api/models`, the administrator model
settings, and the provider model refresh), and the persistent Build number
disappears from the left rail, the sign-in screen, and the app info dialog.
**Only the display is gated: the execution path, stored model settings, the
model information on history entries, and each work's `render_build_number`
are unchanged when it is off** (if a stored setting points at a hidden provider,
only the on-screen selection falls back to the first public model). The
distributed compose file defaults it off; the development and bench compose file
defaults it on. `/api/info` reports `developer_mode`, and the web app reads it
before sign-in.

## engine 15 — remaking the seed and the mark (v2.7.8)

**Five changes landed as one version.** They sit in the same layer, and bumping four times would
have cost four Android follow-ups.

- **A mark's seed is built from an allowlist.** It used to be a hash of the instruction's whole
  dump, so **changing a value that never reaches the drawing still moved the drawing**
- **The ground's seed comes from the support**
- **`cloudform` goes through the hand-drawn path** (it had never entered `stroke_engine`)
- **Angular shapes and `pen` get a material layer**
- **Strength is not distance** — the offset gain of 2.8 and the 3.5px floor are gone

**318 moved, 32 unchanged. The 32 are `computer` and `rotring`** — the mechanical extreme
deliberately skips the performance, so it does not move. **Had those two moved, engine 15 would
have broken the mechanical extreme.**

v2.7.12 (Build 721) folded "the sheet says how it was made" into this version. **It moved 3 of 350.**

Detail: "What engine 15 changed" in `server/reference/README.md` /
[changelog v2.7.8](../history/changelog-v1.72-v2.4.md)

**Five changes to `renderer.py` land as one version.** They sit in the same layer, and
bumping four times would have cost four Android follow-ups.

### A mark's seed is built from what makes it another mark

`_seed_for_instruction` hashed **the instruction's whole dump**. Rewriting a colour note
`coerce` had written was enough to change the drawing; changing `count` re-rolled the hand;
an A/B on a composition flag was confounded by it. Engine 15 uses an allowlist: **what it is,
the tool, the geometry, its variation, its surface, and `arrangement.jitter`**. Measured
across all 49 fields, **30 move the output and 19 do not**.

> **"Changing the count preserves the stroke" holds only for `layout="scatter"`.** With
> `horizontal`, `vertical`, `radial` or `grid`, going from 12 to 13 moves the first twelve
> as well. That is not a leak in the seed: `_clustered_pos` and `_path_pos` take the count
> as an argument, and **a layout that divides a span by the count must move**.

### The ground's seed names the paper

`_texture_seed` hashed the whole Score, so **touching anything at all dealt a new sheet of
paper**. It is now made of **`material`, `grain` and the performance seed**, so raising the
opacity **darkens the same sheet**.

That freed **`ground.absorbency`** to be retired. Nothing had ever read it, but removing it
moved the grain, so it could not be retired before. Saved Scores still carry it, so it is
**dropped before validation**, as `contact` and `thickness` were in v2.7.2.

### `cloudform` joins the road every other closed contour takes

It claimed `stroke-engine-touch` in its class while **never entering `stroke_engine`**, and
all three material mechanisms were absent from it. Engine 15 passes the dense polyline the
inner fill already builds straight into the hand-stroke path. **No cloudform-specific
synthesis was written.**

### The corner shapes and `pen` gain the material layer

`_render_corner_shape` had **no material-outline call at all**, leaving `triangle` and
`polygon` bare for every tool that owns one, and **`pen`, the most used tool in production**,
had nothing but its body stroke.

### Strength stops being distance

Each rung of the material intensity ladder had answered "the layer reads weak" by multiplying
the outline offset — to **2.8x, with a 3.5px floor**. Measured against the band's own
half-width as drawn, the strata sat **4.5x out for `pencil` and 6.5x for `chalk`**: far enough
to read as **a second contour rather than a trace**. The multiplier and the floor are gone.
The specification table was never at fault — its values are 0.7 to 2.3 times the half-width.
The opacity gain, which is the other lever, is **untouched**.

> **Darkness carries strength. Distance is not a lever for it.**

### Version and corpus

`render_engine_version` goes `14` to **`15`**. The corpus holds **350 cases** (four added,
one dropped). **318 moved, and the 32 that did not are the point**: `computer` and `rotring`
across the seven shapes that are not `cloudform`, plus four `D-canvas` rotring cases. Neither
machine pole consumes the performance seed, so the first change never reaches them, and both
**move on `cloudform` alone** — the one path they newly share, where `rotring` drops its false
`stroke-engine-touch` and `computer` gains its `raster-bleed`.

The four new cases (`C-groundseed-auto-*`) are **the first in the corpus's history to leave
`ground.seed` unset**. Every ground case had pinned it, so **`_texture_seed` was called zero
times across all 347 cases** and the layer this version rewrote could not be tested by the
corpus at all.

## engine 14 — one lattice, and wild arriving (v2.7.0)

- **The quantized grid became one lattice per drawing**
- **Wild reaches contours, arcs, fills and hatches.** In engine 12 it reached only the line
  primitive, so **the description and the implementation disagreed** (circles and squares came out
  byte-identical with it on)

**126 moved, 221 unchanged.** The corpus grew from 228 to 347 cases (the new wild cases).

Detail: [changelog v2.7.0](../history/changelog-v1.72-v2.4.md)

**The two holes engine 13 left open are closed in one version**, since both change what is
performed and a single version means the corpus is re-frozen once.

### A lattice is a property of the paper, not of the object placed on it

Engine 13's lattice had a step **proportional to stroke length** (`step = length x 0.018`), so:

- **objects of different length got different steps** (100px -> 1.8px, 400px -> 7.2px, 800px -> 14.4px);
- **the same length changed figure with position**: thirty equal lines placed apart produced **thirty distinct figures**;
- one picture held **as many separate sheets of graph paper as it held sizes**.

Engine 14 derives the step from **`canvas short side x quantize`**. The value of `quantize` is still
`0.018`, but **its meaning moved from "a fraction of the stroke's length" to "a fraction of the
canvas's short side"**. `stroke_engine` does not know about the canvas, so **the renderer converts to
pixels and passes the step in**. No length-relative path remains -- no flag and no fallback.

- 18.000000px on a 1000px square. Being short-side based, **it varies with aspect** (a4 12.726px,
  oban 12.006px, vertical 10.116px, **pillar 3.600px**). That is a consequence, not a defect
- **Every stroke in one picture falls onto the same cells.** Material cells share one side length
  within a Score and their centres sit on integer multiples of one step (with three objects of
  different size in one Score, coordinates off the lattice went from 188/194 to **0/194**)
- **Because the paper no longer shrinks with the object, consecutive samples can round into the same
  cell.** Overlapping cells are drawn as they fall; they are not deduplicated. The author chose 18px
  with this appearance in view

### Wild reaches the contours

Engine 12's wild switch **reached only the `line` primitive**. In measurement, **63 of the 88
combinations (11 tools x 8 primitives) came out byte-identical with it on and off**, which
contradicted the "one switch for the whole work" description in the Wild section above.

Engine 14 adds the centreline gesture to `synthesize_along` (circles, ellipses, triangles, squares,
polygons, arcs, fills and hatches) and threads `wild` through it. **With the switch off nothing
changes, byte for byte** -- of the 228 existing corpus cases, the only seven that moved did so
because of the lattice.

**Exactly 25 combinations may still be identical, each for its own reason.**

| Identical by design | Count | Why |
|---|---|---|
| all 11 tools x `cloudform` | 11 | `cloudform.py` does not go through `stroke_engine` (**a known hole engine 14 does not fix**) |
| `rotring` x the other 7 primitives | 7 | its grammar's `gesture` is zero -- the machine pole |
| `computer` x the other 7 primitives | 7 | `periodic` skips `WILD_GAIN` (12.6) |

### Three ways a naive port breaks

Copying the straight-line gesture onto a contour does not work. **All three were measured on a
prototype before they became specification.**

1. **Amplitude must not be scaled by arc length.** A closed contour's perimeter is not its size (a
   heptagon turned into a star). **A closed contour is measured by `perimeter / tau` -- its radius equivalent.**
2. **The gesture's mean must be removed.** A non-zero mean rescales the whole figure (a circle shrank).
   **Size is decided by the score; a performance may not change it.**
3. **The window must fall to zero before an anchor.** A gesture riding on the vertices next to a
   corner that is pinned back to the intention produces spikes.

### The material follows the ink

The material outline of a contour or an arc (`class="material-outline"`) was **built from the
geometry and never looked at the performed centreline**. With wild reaching contours, **all nine
measured combinations moved the ink alone and left the material behind on the geometry** -- the same
defect engine 12 fixed for lines, where a material layer that does not follow the centreline reads
as ruling behind the drawing.

**With wild on, the material outline and specks of a contour or an arc are built from the performed
centreline.** With it off they are exactly as engine 13 left them.

### Version and corpus

`render_engine_version` moves from `13` to **`14`**. The reference corpus grows to **347 cases**
(`corpus_format_version` `"1"` -> `"2"`, since each case's input now carries `wild`).
`changed_from_previous` holds **126**: **7 existing cases** (the `A-computer-*` set minus
`cloudform`) and **119 new E-block cases** (the full 88 under wild, plus 15 fills and 16 surfaces),
leaving **221 unchanged**. **Not one of the ten hand tools moved.**

---

## engine 13 — the computer's touch (v2.6.0)

- **Added "computer" as a tool.** Its width and path fall onto fixed steps. **Repeating without
  error** is the core of it
- The repetition does not scatter with the seed; the material layer is straight lines, and every
  dash carries the same value

**8 moved, 220 unchanged. The 8 that moved are the new computer cases themselves** — **not one of
the 220 existing cases moved.** This is the record that adding a tool left the existing
performances alone.

Detail: [changelog v2.6.0](../history/changelog-v1.72-v2.4.md)

**An eleventh tool, "computer", joins the touches.** Its core is not "the hand does not
shake" but **"it repeats without error"**. A hand cannot produce the same value twice; a
machine can produce nothing else. **A cycle repeats along the line, a lattice repeats
across the plane** — two axes of one property.

This is what separates it from `rotring`. **Rotring has no wobble to repeat** (every term
of its grammar is zero). **The computer has wobble and repeats it exactly.** So this is not
a retreat to the symmetric envelope of engine 11: that envelope was a **default nobody could
decline**, and this one is **vocabulary you choose** ("The engine does not go backwards" in this document stands).

- **The repetition does not vary with the seed.** The machine cycles (five and ten per
  stroke for energy, two for gesture), the width steps and the lattice are all constants and
  take no `render_seed`. **The same Score performs byte-identically under different seeds**,
  which no hand tool does. Placement and motion vocabulary keep their seed dependence: those
  belong to the layers above.
- **"Wild" has no effect** (`SPEC.ja.md` §13.4). Being wild is a property
  of the hand, so the computer is treated like `rotring`.
- **Lattice**: centreline coordinates are rounded to a lattice, and
  width falls onto four steps. **Engine 13 used a step of `stroke length x 0.018`, so every
  object carried its own graph paper; engine 14 replaced it with one sheet of
  `canvas short side x 0.018`** ("engine 14" in this document).
- **A closed contour may look almost like rotring's.** No radius modulation is written for
  closed contours; that flatness is the CG taste.

### The material is the remainder of sampling

A hand tool's material layer is **what the tool drops beside the stroke** (graphite dust,
brush hair, shaved wax). A machine drops none of that. **What it has is the difference it
threw away when it rounded to the lattice.**

**The geometry repeats without error. The material shows where the error went.**

For each sample, the distance between the position before rounding and the lattice point
after it is the residual. **Only samples with a non-zero residual** get a square of one
lattice cell (`class="raster-bleed"`), laid under the stroke, **placed on the lattice** and
**toned in proportion to the residual** (capped at 0.45 where the rounding moved half a
cell). No seed is involved, so **the same figure always bleeds the same way**.

**Endpoints are pinned to the intention and polygon corners are anchored**, so those samples
carry no residual and emit no cell: a line yields 39 cells from 41 samples, a square 76 from
80, an arc 60 from 62.

**This material replaced a first version of engine 13.** That version drew "a ruled line and
one identical dash pattern on every stroke", restating the "rain of straight lines" of the
older work `rh2:9e991c...` as a property of the tool. Rendered and looked at, the ruled layer
was pinned to the intended start and end while **the performed centreline wanders up to 55px
away**, so the dashes detached from the stroke and read as background ruling. **It carried no
pictorial meaning and was discarded.**

---

## engine 12 — de-regularizing the performance, and wild (v2.5.0)

- **The width envelope was a fixed symmetric hump** — every stroke was fattest exactly at its middle
- **The correction event repeated with period 5**
- A closed contour carried a thin seam
- A gesture entered the centre line, and the wild toggle arrived

**199 moved, 21 unchanged. The unchanged are 12 `rotring` cases and 9 `cloudform` cases.**
`rotring` is the mechanical extreme, so that follows; **the 9 `cloudform` cases were still because
they never entered `stroke_engine`**, which was not fixed until engine 15.

Detail: "What engine 12 changed" in `server/reference/README.md` /
[changelog v2.5.0](../history/changelog-v1.72-v2.4.md)

## engine 11 — the master grid (v2.4.8)

- **Every emitted number is declared on one grid** (fixed to six decimal places)

**220 moved, 0 unchanged — everything moved.** The version changed how numbers are written rather
than what is drawn, so that is right. **Which also means that in a version where everything moves,
"what stayed still" explains nothing.** The discipline first did real work in engine 12.

This corpus **cannot be regenerated outside macOS and is excluded from CI** (a 1-ulp libm difference).

Detail: [changelog v2.4.8](../history/changelog-v1.72-v2.4.md)

## engine 10 — the first frozen version (frozen by v2.4.4)

**Engine 10's content landed before the freeze.** v2.4.4 (Build 694) is the version that first
**froze the performance of that moment as a 220-case corpus**. Every version after it is explained
as a difference from those 220.

Detail: [changelog v2.4.4](../history/changelog-v1.72-v2.4.md)

## engines 1–9 — before the freeze

**With no reference corpus, there is no mechanical answer to "what moved".**
The record is in the changelog archives and in the prose of `SPEC.md`, which states the reason for
each bump inline (the lines in `SPEC.md`: 5 → 301, 6 → 310, 7 → 329, 8 → 347, 10 → 391).

**For this range you can tell that the drawing changed, but not which drawings changed or by how
much.** That the freezing began at engine 10 is itself the reason for the gap.

## How this document is kept

- **Do not hand-write the numbers in the table.** Take them from `changed_from_previous` in
  `server/reference/render-engine-*/manifest.json` and from the number of SVGs in that directory
- **When the version goes up, add a section here.** Every section must say **what stayed still**
- **There are two language versions.** `render-engine-history.ja.md` is the original and the English
  one follows it. `server/scripts/check_docs.py` checks that their headings correspond
