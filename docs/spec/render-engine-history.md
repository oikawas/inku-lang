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

**The DDL transform layer (`DDL_ENGINE_VERSION`) has a third reason of its own** — **the declaration
order of `Instruction`'s fields changed**. The Stage 2 tool schema reaches the model with its
property order intact, and an optional field's fill rate depends monotonically on where it is
declared (0% at the head, 89% at the tail; measured in `SPEC.ja.md` §5.1). **Not one line of
behaviour need change for the distribution of Scores, and therefore the drawing, to change.**
Reordering looks like tidying for readability, and **this is the one reason a frozen corpus cannot
catch** — the corpus fixes the Score and watches the performance, so a change in which Scores are
produced moves nothing in it.

**The first application of this reason was `ddl_engine_version` 2 → 3 (v2.9.5, 2026-07-29)** —
`Instruction.thinness` moved from position 14 to the end, and carry went from 18% to 89%.
**The corpus frozen as `ddl-engine-3/` is byte-identical to `ddl-engine-2/` in all 29 cases, and
`changed_from_previous` is empty.** **That emptiness is what this reason looks like.**

**The second application was `ddl_engine_version` 4 → 5 (v2.9.33, 2026-08-03)** —
`Instruction.thinness` moved off the tail to sit immediately before `surface`, **giving the last
slot back to `surface`**. `ddl-engine-5/` is likewise byte-identical to `ddl-engine-4/` across all
33 cases, with an empty `changed_from_previous`.
**What the first application failed to teach is here**: the decision to move `thinness` to the tail
watched only `thinness`'s own carry (18% → 89%), and **nobody measured that `surface`, which gave up
the tail, fell from 92% to 42% and halved the whole Score**.
**When the declaration order moves, measure the field that gives up its seat, not only the one that
takes a new one.**

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
| **21** | v2.9.34 | 838 | 2026-08-03 | 525 | **32** | **493** |
| **20** | v2.9.20 | 813 | 2026-08-01 | 525 | **32** | **493** |
| **19** | v2.9.16 | 804 | 2026-08-01 | 493 | **227** | **266** |
| **18** | v2.9.14 | 790 | 2026-07-31 | 493 | **70** | **423** |
| **17** | v2.9.12 | 783 | 2026-07-30 | 475 | **110** | **365** |
| **16** | v2.9.3 | 749 / 754 | 2026-07-28 | 365 | **333** | **32** |
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
| `render_engine_version` | the drawing engine | `21` | **the same Score and seed perform differently, or the performable vocabulary grows** |
| `ddl_engine_version` | deterministic transforms (expansion, coerce, validator) | `5` | the same input and seed produce different output, **or the declaration order of `Instruction`'s fields changes** |
| `ddl_version` | the DDL language itself (grammar, keywords) | `3` | **vocabulary is added, changed or retired, or grammar is** (written down on the 2026-07-30 ruling: version 2 rose for the thinness word, version 3 for yellow, orange and purple) |
| Score `version` | the JSON Score schema | `0.1.0` | the schema's structure changes |
| `MODEL_CONFIG_VERSION` | the model catalog's content | `2.5.0` | **measurements, recommendation levels or selectability change**. A bump lays the builtin metadata back over the matching ids in a stored catalog (the stored model list and the enable/disable choices survive) |
| `APP_VERSION` | the application version | v2.9.44 | every stamping. **`web/APP_VERSION` is the one file that owns it**, and the UI, `/api/info` `version` and the CLI all read it |
| `server/pyproject.toml` | the distributed package | 2.7.2 | **only when a release is tagged**. Returned as `/api/info` `release_version`; it lags the application version while releases are on hold |
| `web/BUILD_NUMBER` | build serial | 851 | **moves for UI-only changes too. It is a shared counter, not a per-branch value, so numbers can be skipped. Since v2.9.23 a merge driver named in `.gitattributes` keeps the larger side, so two branches bumping it no longer conflict** (run `scripts/git/setup.sh` once per clone) |

**The "current" column holds the values as of writing.** When a version goes up, this column is
corrected in the same commit.

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
comes from `score`, `render_seed`, the render engine's ID and version, and
`render_color_catalog_id`.

- **`render_build_number` is not part of identity.** It is stamped for UI-only
  changes, so it gave a new edition ID to a drawing that had not changed by a single
  byte. It stays as provenance: worth keeping as history, not worth putting in the
  definition of sameness.
- **The Score-side seed (`vary_seed`) is excluded too** — a different Score already
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
| Drawing | `server/reference/render-engine-21/` | what `renderer.py` / `stroke_engine.py` perform (SVG) | 525 (32 SVG) |
| Deterministic DDL layers | `server/reference/ddl-engine-5/` | **A** = expanded DDL from `expand_intermediate_ddl` / **B** = coerced Score plus `branch_report` from `coerce_score` | 33 (A 15 / B 18) |

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

`/api/info` reports two versions, split apart in v2.9.25. `version` is the
**application version**, read from the single file `web/APP_VERSION`, so it
always equals what the UI puts on screen. `release_version` is the **distributed
package version**, read from `server/pyproject.toml` through
`importlib.metadata`. **They are different things and do not coincide while
releases are on hold** (measured 2026-08-01: application v2.9.24 against package
2.7.2). Before the split, `version` reported only the package version, so two
different version numbers appeared on the same screen.

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

## engine 21 — the performance stops reading libm's last bit (v2.9.34)

**The printed numbers agreed; the seed that reads them did not.**

When engine 11 put every number on a six-decimal grid, this document said the drawing would from
then on be the same on any OS. What agreed was the **printed number**, not the **performance seed,
which hashes the coordinate before it is printed**.

**macOS libm and glibc disagree by one ULP on `sin`/`cos`.** Of 60 identical arguments,
`sin(t·2π)` differs for 9, `cos(radians(t·360))` for 7 and `sin(radians(t·360))` for 10 (Python is
3.12.13 on both). That reaches group G's expanded coordinates as **1-8 ULP**, and
`_fit_group_to_anchor` averages every point, so it spreads across the whole group. Since
`_seed_for_instruction` hashes the entire instruction dump, **a difference of
5.551115123125783e-17 turns the seed from 7178797595915484867 into 2693192989206796227**. A
different seed is a different tremor, which is **0.08-0.17px** in the drawing.

**Only the arrangement path amplified it.** Six decimals absorb the one-ULP difference everywhere
else, and **the 493 cases of A-F were byte-identical across the two platforms before the change**:
A-F never state an `arrangement`, never reach `_expand_arrangement`, and so never feed a coordinate
to a hash.

**The coordinates `_expand_arrangement` returns are now quantised to 9 decimals.** 1e-9 of a
normalised coordinate is 1e-6 px on a 1000px canvas, below what the SVG prints, so it cannot be
seen. **All 525 cases were measured to agree on both platforms** (6 differed before). **32 cases
moved, all of them in group G**; not one of A-F did.

**"identical on both platforms" cannot be the acceptance gate, because one machine cannot observe
it.** `test_render_platform_stability.py` perturbs `sin`/`cos` by exactly one ULP locally and
requires the drawing to stay put, **paired with a test that the same perturbation moves 12 cases
once the quantiser is removed** — without it, a perturbation that stopped reaching the renderer
would leave the first test green.

## engine 20 — a group's position returns to the description (v2.9.20)

**What decided where a group went was the seed, not the description.**

**77.8% of the 137673 expanded marks never consulted a declared coordinate** (measured over 7463
production instructions). `scatter` scattered from the seed and `margin` alone, `cluster` only
widened the margin at the centre, `vertical` / `horizontal` with a `path` **wrote 0.5 into the
crossing axis**, and `radial` turned around **(0.5, 0.5)** whenever no `center` was stated. So
**moving every stated coordinate down by 0.2 moved the ink's centroid by a median of 0.0000**, while
**changing `render_seed` alone moved 4.06% of the pixels**. **93.3% of the ink on screen** was placed
by the renderer's arrangement rules rather than by the coordinates in the Score, and so was the
principal subject in 76 of 100 works.

### Placement became a second stage

**The stage that decides the shape of the scatter is separated from the stage that decides where the
group sits.** The existing layout branches keep the first (`_expand_arrangement_layout`). The second
is new: **the centroid of the expanded group is moved onto the declared anchor**
(`_fit_group_to_anchor`). **No layout branch was rewritten** — the shape, density, rhythm, wobble and
stroke of a scatter are outside this version's remit.

`radial` needs both mechanisms. The rotation centre is radial's own word, so **it is used when the
description states it, and the ring turns around the declared anchor when it does not**. The middle
of the canvas is no longer a default.

### The frame is shrunk one direction at a time

Moving a group onto its anchor pushes marks outside the frame **[0.02, 0.98]** for descriptions near
an edge (23 of the 32 G cases). **A similarity shrink collapses the whole group for the sake of the
one mark that overflows** (worst spread ratio 0.315). This version **shrinks each axis, and each
direction along it, by only what overflows there**. The spread away from the frame is kept and the
**worst spread ratio is 0.660**. **Clamping onto the frame was rejected** — it piles edge marks onto
shared coordinates, 8 of them in the `scatter` edge case.

**An anchor that is itself outside the frame cannot be saved** (an `at.region` reaching the edge with
a group of `count=1`): the correction shrinks around the anchor, and a group with no spread has
nothing to shrink. **One case out of 100 production works remains** ([I-079]).

### One thing does not pass through — a grid that stated its region

**A `grid` with an `at.region` does not go through the second stage.** A grid tiles that region, so
`at` survives performance resolution instead of being folded into the anchor; passing it through
would **drive the group out of the region the description stated and onto the shape's own centre,
which nobody stated**. That is the opposite of what this version is for. A `grid` without an
`at.region` passes through as everything else does.

### Version and corpus

- **`render_engine_version` 19 to 20**
- **`ddl_engine_version` stays 4 and `ddl_version` stays 3** — neither DDL vocabulary nor grammar moves
- **Reference corpus `render-engine-20/`** — **525 cases** (the 493 of A–F plus **32 in group G**).
  **The existing 493 are byte-identical**; group G was created for this version and covers placement.
  **The manifest's "32 moved" counts every new case and is not the mechanism's effect** — the effect
  was measured by drawing the same 32 cases under engine 19 and engine 20 and comparing, which gives
  **30 / 32** (the two that hold still are `G-vertical-nopath-center` and `G-horizontal-nopath-center`,
  which already took one axis from the declaration)
- **Measured over 100 production works**: the distance from a group's centroid to its anchor falls
  from a median of **0.0719 to 0.0000**, marks outside the frame from **18 / 3890 to 1 / 3890**, and
  `relation` survival is unchanged (10 / 10)

## engine 19 — the ground resists the hand (v2.9.16)

**In painting the role of the ground is to resist the hand.** An absorbent sheet lets the ink spread; a
toothy one refuses the tool and leaves the paper bare. Until engine 18 the ground and the drawing were
composited independently and never met, and the only place the drawing side read `canvas.ground` was the
mezzotint test in `renderer.py`.

**A condition placed on the ground side reaches nobody**: only **31 of the 1847 stored works (1.7%)**
carry a `canvas.ground`, and **none** of the frozen SVGs do. This version puts a default support on the
side with **99.7% reach**. **The sheet is one constant; which of its two quantities a tool meets is a
property of the tool** (author, 2026-07-31).

### The support, and which tools meet it

The support is a module-level constant (`Support`) in `stroke_engine`. **It is not a `Score` field** —
`absorbency` was retired in engine 15 and its absence is pinned by a test. The per-`material` table is
deferred; only the swap-in point is open.

| weight | absorb | tooth |
|---|---:|---:|
| brush_thin / brush_thick | 1.00 | 0.15 |
| crayon / pencil / chalk | 0.10 | 1.00 |
| pen | 0.15 | 0.15 |
| silverpoint | 0.05 | 0.25 |
| drypoint | 0.00 | 0.35 |
| burin | 0.00 | 0.10 |
| **rotring / computer** | **0.00** | **0.00** |

**A machine has no contact with paper.** The two machines are unchanged for different reasons, though:
`computer` goes through `stroke_engine` and is held still by its zero bias, while **`rotring` never
enters stroke synthesis at all** (`_uses_hand_stroke` has excluded it since engine 8). **The zero in the
table is a description, not a mechanism.**

Four levels (g0 to g3) are implemented and **g2 is adopted** (bleed amp 0.70 / span 0.16 / rate 1.5;
skip depth 0.88 / span 0.07 / rate 1.5; the ink is cut where the envelope passes 0.55). The other levels
stay so that **the monotonic ordering remains checkable**.

### The cut removes ink rather than narrowing it

**Narrowing is invisible.** The tools that ought to be refused are exactly the thinnest ones (pencil
1.5px, chalk 3px, crayon 4px), so a 0.25x pinch is 0.20-0.52px on a 520px raster and sinks into the
antialiasing. **Being refused means bare paper, not a thin line.**

Where the envelope passes the threshold no ink is laid down and the stroke is cut. **One SVG `path` can
hold several subpaths** (`ring_path` already relies on this), so **cutting adds no element**. This is the
permanent brake against the engine 15 precedent, where 38 fibres made the ground 46% of the drawing:
**one extra element is a failure**. **A closed contour keeps its even-odd band and is never cut.**

### A wavering line meets the same sheet

A straight line carrying a position `variation` takes a different path through the renderer, which
**rebuilds the outline around the varied centerline** (`outline_for_centerline`). **Without carrying the
cuts into that rebuild, only the width response survives and the ink is never cut** — the bytes still
move, so the frozen corpus counts the case as changed and **the visible half goes missing in silence**.

- Measured (pencil, seed 20260731, five lines) without the carry-over: **10 subpaths without the
  variation, 5 with it** (no cuts at all)
- **An arc is cut whether or not it is varied.** The difference belongs to straight lines alone
- The reach is **912 of the 1858 stored works (49.1%)**, of which **242 (13.0%)** use a refused tool

The cut mask travels on `StrokeResult` into `outline_for_centerline`, which **splits both banks at the
same samples the straight branch does**.

> **Never mix an arc into the figure that tests this path.** An arc is cut either way, so **the subpath
> count rises even when no line was cut, and the test supplies its own answer.**

### Version and corpus

- **`render_engine_version` 18 to 19**
- **`ddl_engine_version` stays 4 and `ddl_version` stays 3** — neither DDL vocabulary nor grammar moves
- **Reference corpus `render-engine-19/`** — **493 cases**, **227 moved / 266 unchanged**. The stored
  SVGs are the 227 that moved
- **No `rotring` or `computer` case appears in `changed_from_previous`**
- **A forced order**: the corpus output directory comes from `current_render_engine().version`, so
  **raising the version removes the comparison target from the generator's view**. Implement with the
  version still at 18, measure the delta, then raise it to 19 and bake

**The contract's full mark of 381/493 came out as 227/493.** The reference probe rebuilt straight-stroke
outlines with per-vertex normals at every level above g0, so **177/493 moved with each resistance bias
set to zero** — **46% of the 381 had nothing to do with the ground**. This implementation keeps the fixed
normal.

**Undecided**: the material outline still runs across the cut, so its dashes cross the bare paper where
the ink stopped. Cutting it would mean turning the polyline into a path and would move every material
outline in the corpus.

## engine 18 — the thirteen catalogs each carry all nine colors (v2.9.14)

**Engine 17 built the path that picks from a `palette`. This version replaces the table it picks
from.** **Only data moved** — the resolution chain, the band definitions, the achromatic threshold
and the seed material are all engine 17's, and `renderer.py` has no diff.

**Engine 17's table left many catalogs with no color in a band.** Ask for green where there is no
green and the nearest hue, a yellow, stands in. Across the 7463 stored instructions, **140 asked for
a band the catalog did not hold**.

- **Thirteen catalogs hold ten palette colors each**, fixed at **exactly three achromatic and
  exactly seven chromatic**. The seven fill all six bands, one band holding two
- **The `map` grows from six keys to nine**, and **all nine are drawn from that catalog's own
  palette** (before, `map` and `palette` could name different colors)
- **The swatch strip is derived from the `map`, six chromatic keys first** — Android draws
  `swatches.take(4)` and `take(8)` on two screens, so an achromatic-first order would spend those
  slots on black, gray and white
- **No hex repeats across the 130**
- **`desert_mineral` retired; `moss_bark`, `neon_plate` and `lantern_dew` joined.** The retired one
  held a single achromatic color, which is why engine 17's anti-collapse rule existed
- **All ten retired ids answer `None` from both `get_color_catalog` and
  `render_color_map_for_catalog`** rather than falling back to `default`. 117 stored works name that
  id, and **no migration was written** — an unknown id is drawn with the default catalog, as before

### Reach (this recovers wrong bands; it does not add color)

| Metric | engine 17 | engine 18 |
|---|---|---|
| Band the description asked for, absent from the catalog | 140 | **0** |
| Chromatic hits | 2184 / 2455 (89.0%) | **2455 / 2455 (100%)** |
| Achromatic hits | 4917 / 5008 (98.2%) | **5008 / 5008 (100%)** |
| Distinct hexes resolved | 79 | **91** |
| Palette colors never drawn (catalogs in use) | 7 | **9** |

**The never-drawn count rises rather than falls.** The nine in catalogs actually in use are eight
purples plus `sea_stone/Coral Orange`, because **purple is 0.9% of real demand**. Counting all
thirteen gives 39; the extra 30 belong to **the three new catalogs**, which no stored work names and
which therefore cannot be reached at all. **What moved is recovery from a wrong band**: `default`
gains 106 yellows and loses 106 greens, `sea_stone` gains 58 greens and loses 58 yellows,
`cool_material` gains 37 reds against 37 oranges and 35 greens against 35 yellows. The band
distribution holds at 67.2% achromatic, with **orange 0.8 → 0.3** and purple 0.0 → 0.03.

### `sea_stone` keeps its purple band empty

**One catalog deliberately does not fill a band.** By the author's ruling `sea_stone` holds no
purple, and the nearest-band stand-in engine 17 provides answers with `Night Sea #191970`. **That is
also this catalog's `blue`**, so a work placing blue beside purple draws two shapes in the same
navy. **Checked by eye**: the forms stay legible where they overlap, so the picture does not break —
it reads as the same color used twice.

### Roles dissolving into the paper fall from eight to two ([I-062] closes)

**Engine 17's regression** — `cool_material`'s `black` landing on `#e5e8e8`, 0.062 in lightness from
the paper — **is gone** (that catalog's black is now `#26282a`). **The two that remain are both
yellows**: `vivid_material`'s `#fff200` (ΔL 0.026) and `open_air_light`'s `#ffce00` (ΔL 0.127). A
bright yellow band is yellow's own nature, so neither was changed. **Measured across 10 seeds × 13
catalogs, those two are the only ones.**

**Neither engine 17 nor this version's implementation named that property in a test.** During
acceptance, the perturbation that reproduces [I-062] — lightening the black back into the paper —
reddened **only the expected-assignment table and the frozen corpus**. **Both are regenerated
wholesale whenever catalog data changes**, so nothing was guarding the property itself. **One test
was added during acceptance**: it counts the assignment for 13 catalogs × 8 seeds by lightness
distance to the paper and **pins the two survivors by hex**. It reddens under the reproduction and
stays green under a control that moves the same black to a different but still dark hex.

### Versions and corpus

- **`render_engine_version` 17 → 18**
- **`ddl_engine_version` stays 4 and `ddl_version` stays 3** — neither DDL's vocabulary nor its
  grammar moved
- **Reference corpus `render-engine-18/`** — **493 cases** (A 88 / B 72 / C 58 / D 28 / E 119 /
  **F 128**), **70 changed / 423 unchanged**. The stored SVGs are the 70 that changed
- **None of the 365 cases in A-E moved, and nothing outside the F group moved**
- The 70 are **42 existing ids whose performance changed** plus **28 new ones** (27 for the new
  catalogs, plus `F-hint-missing-purple-sea-stone`). Ten disappeared (`desert_mineral`'s nine plus
  `F-hint-missing-purple`)
- **58 further cases changed only in what was recorded** — `input.color_map` went from six keys to
  nine while the digest did not move a byte. **"Changed" is counted from the manifest's
  `changed_from_previous`, not from a difference in the record**
- `color_map_digest` `bbb2f7be3cab3d70c7330520728ac4b0` → **`96f2809778344689d8fc1dbab03827b0`**

## engine 17 — the catalog's `palette` reaches the drawing (v2.9.12)

**Until this version the eight named entries of a catalog's `palette` reached the drawing only
through substring matching on `color_hint`.** That description channel is nearly empty: of the 7463
stored instructions, only **945 (12.7%)** carry a color word in the segment Stage 2 wrote.
**For 87% of instructions there is nothing to match against**, and resolution ended at
`cmap[color]` — the catalog's six-key `map` plus the three defaults v2.9.11 added.

**This version builds a deterministic path from the `palette`.** The assignment is computed
**once per work**, and its only inputs are **`(render_seed, catalog_id, abstract color)`**.
The full instruction dump is not used (using it would change the color whenever `color_hint`
is edited, confounding any A/B), and neither is `performance_seed` — **color is a property of the
work, not of the performance.**

- **The six chromatic words** are classified by OKLCh hue band (red 345–50°, orange 50–80°,
  yellow 80–137°, green 137–200°, blue 200–280°, purple 280–345°). **CIELAB cannot be used**:
  it puts pure blue at 306° next to pure magenta at 328° and cannot separate blue from purple.
  With several candidates in a band the seed picks one; with none, the nearest chromatic entry by
  hue angle; with no chromatic entry at all, the `map` value.
- **The three achromatic roles** first **reserve** the candidate whose hex equals their own `map`
  value, then take the remaining candidates in order of nearest L to that `map` value. The naive
  "highest L / lowest L / middle" rule **collapses white and black onto the same hex in the five
  catalogs that hold fewer than three achromatic entries** (`desert_mineral` holds one).
- **The background goes through the same assignment.**
- **`catalog_id` now reaches the renderer.** The identifier did not appear in `renderer.py` even
  once before: four files carry it — the two calls in `api.py`, `RenderEngine.render()`,
  `DefaultRenderEngine`, and `render()`. Omitting it means `DEFAULT_COLOR_CATALOG_ID`.
- **`_hint_hues` matches ASCII on word boundaries** (CJK keeps substring matching, having no word
  boundaries). **Five tokens that are not words were dropped from the table** — `blu` and `ai`
  (blue), `vert` and `tall` (green), `shu` (red) — which stops 166 `vertical`, 20 `constraint` and
  13 `blur` misfires. **Genuine French `vert` becomes unreadable too**; stopping the misfires was
  chosen over keeping it. `brown` has no band of its own and is sent to `orange`.

**110 moved, 365 unchanged, and the unchanged side is this version's boundary**: a call that gets
only the six-key `map`, holds no `palette:` key and no `color_hint`, and draws on a `white`
background is byte-identical to engine 16. **Every one of the 365 existing cases had that shape**
(zero `palette:` keys, zero `color_hint`, instruction colors only `black` 364 and `green` 1,
backgrounds all `white`), so **without extending the case table nothing would have moved at all.**
Group F adds 110 cases: 11 catalogs x 9 abstract colors, six description cases, five non-white
backgrounds.

### What it reaches

Measured over 1847 stored works and 7463 instructions, on the **surface v2.9.9 produced when it
moved diagnostics into `note`** (the stored `color_hint` with its diagnostic segments removed).

| Metric | v2.9.11 | v2.9.12 |
|---|---|---|
| `palette` entries never chosen | 12 / 88 | **6 / 88** |
| Distinct resolved hexes | 76 | **82** |
| Color decisions from a misfire | 148 | **0** |
| Achromatic share of what is drawn | 57.9% | **61.4%** |

**This version does not add color; the achromatic share rises.** The band is decided by the
abstract color, and **69.5% of the abstract colors in stored works are achromatic**.
**What moves is which `palette` entry gets used, not the distribution of bands.**

### Eight roles that dissolve into the paper (not fixed here)

**Roles within ΔL 0.15 of the paper went from 0 / 88 under engine 16 to 8 / 88 under engine 17.**
Seven are yellow and orange, because those two bands are light in the catalogs (a yellow line on
paper is pale by nature). **The eighth is a regression**: `black` in `cool_material` moves from
`#2c3e50` (L 0.356) to `#e5e8e8` (L 0.929), and its ΔL against the `#fcfcfc` paper falls
**0.635 → 0.062**. That catalog's own black has chroma 0.039, **just past the 0.035 achromatic
floor**, so it is not an achromatic candidate, and the only remaining candidate (`Pale Birch
#e5e8e8`) is taken by the nearest-L rule **which has no distance limit**. In production
`cool_material` holds **102 works and 412 instructions, 205 of them (49.8%) `color=black`**, over
76 white and 19 black backgrounds. `yellow` in `desert_mineral` lands on the **same hex** as the
paper (ΔL 0.000). **A check that compares hexes alone passes both**, since the three roles do
remain distinct from one another. **By the author's decision of 2026-07-30 this version ships
unfixed and the matter is handled in stage 2** (ledger item [I-062]).

### Version and corpus

- **`render_engine_version` 16 → 17**
- **`ddl_engine_version` stays 4 and `ddl_version` stays 3** — neither DDL vocabulary nor grammar moves
- **Reference corpus `render-engine-17/`** — 475 cases (A 88 / B 72 / C 58 / D 28 / E 119 / **F 110**),
  holding the SVG of the 110 that moved
- **The meaning of the manifest's `color_map_digest` was changed.** It used to be the digest of the
  generator's own six-key `DEFAULT_COLOR_MAP`, so **changing `renderer.COLOR_MAP` never moved it**
  (v2.9.11's three new words passed with the digest unchanged). Group F gives each case its own
  `color_map`, so the digest is now taken over the **set of `(case_id, catalog_id, color_map)` for
  all 475 cases**.
- **Reading frozen SVG alone lets an identity-assignment perturbation pass**, so a test was added
  that **re-performs all 110 group F cases through the live renderer** and compares against the
  manifest digest.

## engine 16 — a surface becomes a mark, and thinness becomes an axis (v2.9.3)

**Three changes gathered into one version**, for the reason engine 15 gathered five: they belong to
the same layer, and raising the version three times would make Android follow three times.

- **A surface is performed, not filled in** — six of the eight touch words were circles scattered by
  a uniform random over the bounding box
- **A tiny fill is placed** — a fill too small to scan had degraded into a region fill
- **Thinness becomes an axis independent of the tool's name** — `thinness` (`fine` / `extra_fine`)

**333 moved, 32 unchanged. All 32 are `rotring` and `computer`.** After engine 12's twelve and
engine 15's thirty-two, **the same side has stood still for three versions running**. Their grammar
is zero throughout and consumes no seed, so **an axis that changes the hand cannot reach a tool that
has no hand**. `C-tinyfill-circle-rotring` is unchanged twice over, and it is the one case in the
manifest that carries no class at all.

Detail: "What engine 16 changed" in `server/reference/README.md` /
[CHANGELOG v2.9.3](../../CHANGELOG.md)

### A surface is performed inside its own contour

`stipple`, `grain`, `paper_grain`, `aquatint`, `wash` and `bleed` — six words —
**scattered circles by a uniform random over the shape's bounding box. They never once saw the shape
they belonged to.**

| Shape | Grains falling outside the shape (engine 15) | engine 16 |
|---|---|---|
| triangle | **46 / 90 (51%)** | **0** |
| cloudform | **43 / 90 (48%)** | **0** |
| polygon | 20 / 90 (22%) | **0** |
| circle | 12 / 90 (13%) | **0** |

**Ask for grains scattered over a triangle, and half of them landed outside the triangle.**
engine 16 places them inside the contour and performs each grain as one stroke. The scan uses the
same `_scanline_segments` as `_render_fill_strokes`, so a concave shape (cloudform) needs no special
case.

`bleed` alone works differently. engine 15 drew **one ellipse at the centre of the bounding box** —
the same picture whatever the shape was. engine 16 draws three bands pushed outward from the
contour, the push varying vertex by vertex. **The innermost ring sits on the contour itself (offset
zero)**: a bleed happens on both sides of an edge, so the bands rise from the edge instead of
floating as rings away from the shape.

`hatch` and `crosshatch` are **not changed by a single byte**. Those two already sent their centre
line through `synthesize_along` in engine 15; they were not scattering a surface. **That those eight
cases are unchanged is what shows this change stayed closed around the six words that scattered.**

#### The same word had become two unrelated pictures, one per profile

engine 15's display emitted a **rectangle** carrying `feTurbulence`, `feDisplacementMap` and
`feGaussianBlur`, while editable scattered circles. **The one word `wash` was a different picture
depending on where you looked at it.**

engine 16 draws both profiles by the same mechanism. The profile difference that remains is the one
every other layer has: **whether the material filter is applied**. **The display clipPath is gone
too** — grains are drawn from inside the contour so it is unnecessary, and **`bleed` seeps outward,
so the clip would erase what was drawn**.

**Speed became 1.44× slower** (119 production works carrying a surface, redrawn in display:
56.2 s → 80.9 s). That is ninety circles replaced by ninety synthesized strokes — the increase the
mechanism implies.

### A tiny fill is placed, not scanned

When a fill was too small for scan lines, engine 15 **degraded into a region fill**. **The
degradation was preventing a failure, not being right** — a small shape filled with a hand tool
became a machine's fill in that one spot.

engine 16 places it as a single dab: carried along the shape's longer axis, its width decided by the
shorter one.

- **The mechanism switches where the short side is about 3% of the canvas** (measured at 2.9–3.2%,
  confirmed across five tools and six seeds; **the switch happens once and does not go back and
  forth**)
- **The carry floor of 0.90 was chosen by measurement.** At 0.30, `_edge_window` takes the width to
  zero over 16% at each end, so **a 10px filled circle becomes an outline with a hollow inside**. At
  1.10 the dab is darker than the shape it fills (ink coverage 115%)
- **`rotring` branches before `_uses_hand_stroke`**, so it stays a region fill at every size

**75.3% of production `filled` closed shapes drawn with a hand tool now take the dab** (measured over
150 works).

### Thinness is a dimension, not a sway

**Thinness had been a property of the tool's name.** Asking for a thin line was asking for a
different tool, and "a thin pen" could not be written. engine 16 puts `thinness` on `Instruction`.

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

**The floor is not a new number; it is the thinnest tool itself**
(`MIN_STROKE_WIDTH = WEIGHT_TO_STROKE_WIDTH["silverpoint"]`). It reads as "no line is drawn thinner
than silverpoint". **Silverpoint accepts no thinness. That is the specification, not an omission.**

**Three candidates were drawn and measured by ink coverage.**

- **Rejected, 0.7 / 0.45** — **the thick brush's `fine` came to 99% of its default**; drawing it
  changed nothing. The thick brush's material layer is mostly an absolute width, so thinning the ink
  alone by 30% does not move the picture
- **Rejected, 0.5 / 0.25** — **the tools stop being distinguishable.** At `extra_fine` five tools
  pin to the floor and **the eleven tools' distinct widths fall from 9 to 6. The thinness axis eats
  the tool axis**
- **Taken, 0.6 / 0.35** — at `extra_fine` the distinct widths go 9 to 8 (only silverpoint and rotring
  merge). The thick brush's `extra_fine` is 2.8px, still wider than a pen — still a brush

**Thinness was carried into the material contour too.** That width is
`abs_width + base_width * width_ratio`, and leaving `base_width` at the nominal value would
**thin the ink alone and leave the material behind**. Only the thick brush and the crayon carry a
proportional term; the rest are absolute and do not move with thinness (**a thinned pen line keeps a
material band that does not thin**). **The offset was not touched** — engine 15's "strength stops
being distance" stands.

**`thinness` was added to the performance seed's allowlist** (19 → 20), following engine 15's
principle that a seed is built from what makes a mark another mark. **The consequence is that
changing thinness also changes the path the line takes.** **Silverpoint's width does not change but
its hand does** — write "a thin silverpoint line" and the picture changes without getting thinner.

**coerce does not put `thinness` on the lines it adds.** Staffage is coerce's own voice rather than
the writer's request, so **a written thinness lands only on the shapes the writer wrote**.

#### Thinness is not a Saijiki word

**`thinness` is a field on `Instruction`, not a word in the Saijiki table** (author's ruling,
2026-07-29). Stage 1 reads thinness words and writes them into the normalized DDL, but they do not
appear in the Saijiki UI or in the §3.1 vocabulary table. **There is one word here that works when
written and cannot be found by looking.**

### Version and corpus

- **`render_engine_version` 15 → 16**
- **`ddl_engine_version` 1 → 2** — `Instruction` gained `thinness`, so **the DDL layer behaves
  exactly as before while every instruction dump carries one more line, `"thinness": null`.**
  Following the rule that a frozen directory is not rewritten, `ddl-engine-2/` (29 cases) was frozen
  anew and `ddl-engine-1/` was not touched by a byte. **A layer's version goes up for a change in the
  shape of the output rather than in the behaviour.**
- **`ddl_version` 1 → 2** (author's ruling, 2026-07-29) — **the DDL vocabulary grew.** "An extra fine
  black line" is a sentence DDL could not write before. **Saved works keep `ddl_version` `"1"`.**
- **Reference corpus `render-engine-16/`** — 365 cases (A 88 / B 72 / C 58 / D 28 / E 119), holding
  the SVGs of the 333 that moved

**The discriminator tests were checked by perturbing the core of each of the three stages** (at
acceptance). Returning the contour to the bounding box turns four S-3 cases red; making the thinness
scale the identity turns thirteen T-1 cases red; removing the branch into the dab turns fifteen F
cases red.

**Stage 2 fills `thinness` in a measured 10%** of works, and the 96% observed at design time did not
reproduce. The deterministic layers — schema, prompt, coerce, renderer — are all green, so **whether
it is carried remains a question about the LLM layer** (ledger I-036).

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
- **`render_wild` joined the `rh3` material; the format name stays `rh3`**

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
each bump inline (in "Renderer: Performance" under "The Two-Stage Architecture" in `SPEC.md`, and
in 13.11 of `SPEC.ja.md`. **Not named by line number** — those rot whenever the document is
rearranged).

**For this range you can tell that the drawing changed, but not which drawings changed or by how
much.** That the freezing began at engine 10 is itself the reason for the gap.

## How this document is kept

- **Do not hand-write the numbers in the table.** Take them from `changed_from_previous` in
  `server/reference/render-engine-*/manifest.json` and from the number of SVGs in that directory
- **When the version goes up, add a section here.** Every section must say **what stayed still**
- **There are two language versions.** `render-engine-history.ja.md` is the original and the English
  one follows it. `server/scripts/check_docs.py` checks that their headings correspond
