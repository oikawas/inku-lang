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
| **41** | Rust migration baseline | — | 2026-08-24 | 610 | **610** | **0** |
| **40** | v2.13.46 | 935 | 2026-08-21 | 610 | **4** | **606** |
| **39** | v2.13.45 | 934 | 2026-08-21 | 606 | **5** | **601** |
| **38** | v2.13.35 | 922 | 2026-08-17 | 606 | **9** | **597** |
| **37** | v2.13.31 | 918 | 2026-08-16 | 597 | **12** | **585** |
| **36** | v2.13.27 | 914 | 2026-08-16 | 588 | **6** | **582** |
| **35** | v2.13.24 | 911 | 2026-08-15 | 588 | **9** | **579** |
| **34** | v2.13.22 | 909 | 2026-08-14 | 588 | **13** | **575** |
| **33** | v2.13.19 | 906 | 2026-08-13 | 586 | **4** | **582** |
| **32** | v2.13.13 | 898 | 2026-08-12 | 582 | **13** | **569** |
| **31** | v2.13.8 | 893 | 2026-08-12 | 569 | **16** | **553** |
| **30** | v2.13.6 | 891 | 2026-08-11 | 553 | **7** | **546** |
| **29** | v2.11.17 | 873 | 2026-08-09 | 549 | **454** | **95** |
| **28** | v2.11.13 | 869 | 2026-08-09 | 549 | **454** | **95** |
| **27** | v2.11.10 | 866 | 2026-08-09 | 549 | **45** | **504** |
| **26** | v2.11.8 | 864 | 2026-08-08 | 549 | **7** | **542** |
| **25** | v2.11.7 | 863 | 2026-08-08 | 545 | **41** | **504** |
| **24** | v2.11.6 | 862 | 2026-08-08 | 541 | **7** | **534** |
| **23** | v2.11.5 | 860 | 2026-08-08 | 535 | **4** | **531** |
| **22** | v2.11.4 | 859 | 2026-08-07 | 531 | **52** | **479** |
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
| **Renderer performance** | `inku-render` through `default/adapter.py`; `renderer.py` is the SVG-only facade | **yes** (given seeds) | 0 | `render_engine_version` |
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
| `render_engine_version` | the drawing engine | `39` | **the same Score and seed perform differently, or the performable vocabulary grows** |
| `ddl_engine_version` | deterministic transforms (expansion, coerce, validator) | `20` | the same input and seed produce different output, **or the declaration order of `Instruction`'s fields changes** |
| `ddl_version` | the DDL language itself (grammar, keywords) | `3` | **vocabulary is added, changed or retired, or grammar is** (written down on the 2026-07-30 ruling: version 2 rose for the thinness word, version 3 for yellow, orange and purple) |
| Score `version` | the JSON Score schema | `0.1.0` | the schema's structure changes |
| `MODEL_CONFIG_VERSION` | the model catalog's content | `2.5.0` | **measurements, recommendation levels or selectability change**. A bump lays the builtin metadata back over the matching ids in a stored catalog (the stored model list and the enable/disable choices survive) |
| `APP_VERSION` | the application version | v2.13.47 | every stamping. **`web/APP_VERSION` is the one file that owns it**, and the UI, `/api/info` `version` and the CLI all read it |
| `server/pyproject.toml` | the distributed package | 2.7.2 | **only when a release is tagged**. Returned as `/api/info` `release_version`; it lags the application version while releases are on hold |
| `web/BUILD_NUMBER` | build serial | 1051 | **moves for UI-only changes too. It is a shared counter, not a per-branch value, so numbers can be skipped. Since v2.9.23 a merge driver named in `.gitattributes` keeps the larger side, so two branches bumping it no longer conflict** (run `scripts/git/setup.sh` once per clone) |

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

There are two instances as of v2.6.0.

| Corpus | Location | What it freezes | Cases |
|---|---|---|---|
| Drawing | `server/reference/render-engine-33/` | what `renderer.py` / `stroke_engine.py` perform (SVG) | 586 (4 SVG) |
| Deterministic DDL layers | `server/reference/ddl-engine-18/` | **A** = expanded DDL from `expand_intermediate_ddl` / **B** = coerced Score plus `branch_report` from `coerce_score` / **C** = expanded DDL, unit counts, declines and the compact Score form (`score_instructions`) from `expand_plugin_ddl` | 49 (A 13 / B 30 / C 6) |

**The DDL side splits into A, B and C because the deterministic layers are not
adjacent** ("Deterministic and non-deterministic layers" in this document). Stage 2's LLM sits between Stage 1.5 (DDL→DDL) and coercion
(Score→Score), so "DDL through to Score" cannot be a single baseline. **A's output is
never used as B's input** — that is the "corpora are never chained" rule above.
**C (plugin expansion) was added in v2.13.1**: the layer had carried a version number
from the start and never a frozen output, because A's plugin work is the `Nature.`
macro regex in `ddl_expander` and the document plugin manager is called from the
render route alone.

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
string is treated as unset (v2.4.0). **From v2.11.19 this premise describes
single-user mode being off**: a server started with `INKU_SINGLE_USER` settles
on one person and signs them in by itself, so it needs no bootstrap admin.
**The distributed compose file now defaults single-user mode to on and no
longer requires `INKU_BOOTSTRAP_ADMIN_PASSWORD`** — Compose interpolation
cannot express "required only when single-user mode is off", so an operator
who turns it off sets the value themselves.

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

## engine 41 — migration baseline for moving the render core to Rust

**Engine 41 is not a drawing-quality release; it is the migration baseline that moves Engine 40's
performance into the shared Rust core.** Python and Rust differ in SVG number spelling, their choice
of path versus polyline, and how elements are grouped, so all 610 cases moved at the byte level.
**No case stayed byte-identical, but the geometry, layers, materials, surfaces, grounds, colours,
composition, and meaning of render metadata stayed fixed.** The candidate passed semantic checks
over all 610 cases, visual review of 16 pairs, byte identity for a five-case Linux/macOS sample, and
core compile checks for Android arm64 and iOS arm64. The author accepted its visual parity.
Before production cutover, focused gates found and repaired missed Engine 40 semantics for solid
mottle, computer raster fills, tiny-fill dabs, and compat grain attributes. This restored the
existing boundary; it was not a drawing improvement.

Production `current_render_engine()` now selects the thin adapter for Rust Engine 41, and the normal
generator recreates the accepted Engine 41 corpus byte-for-byte. The Server installs an independently
built and audited CPython native wheel; there is no runtime fallback to Engine 40. After cutover, the
Python Engine 40 orchestration, planning, mark, surface, layer, SVG-emission, and stroke modules were
retired in a separate stage. Engine 40 remains in Git history and its frozen corpus remains historical
evidence. **This version contains no intentional drawing improvement.** Improvements after the
Engine 41 freeze belong to a separate contract and the next engine version.

On 2026-08-24 Android also moved to the same Engine 41 core through a thin JNI binding and retired
its Android-specific Kotlin renderer and runtime fallback. Five canonical Engine 41 cases match the
server corpus byte for byte through the packaged arm64 JNI library; three current cases and one
historical Engine 21 case also match at the raw-pixel boundary. This port does not increment the
engine version. The separate `inku-svg-raster` API owns SVG-to-pixel conversion and is not part of
the Render Engine version history.

## engine 40 — non-computer solid becomes a mottled base fill, not scan lines (v2.13.46)

**Non-computer `surface.texture="solid"` no longer grows scan lines with area.** A real base fill always remains, with a standard SVG filter mottle over it calibrated to `baseFrequency=0.035`, `numOctaves=3`, and an alpha floor of 0.31. The filter seed and ID derive deterministically from the render seed and instruction identity, so a Score, seed, and profile remain byte-identical and filter IDs do not collide within a work.

**`display` and `editable` carry this standard filter.** Readers that ignore filters still retain the base fill. `editable` targets SVG-native editors and does not promise behavior in partially supporting applications. **`compat` adds neither filter nor clipPath and emits a filter-free flat vector fallback base fill.** `computer × solid` retains its periodic one-direction scan and underlay rather than moving to mottle.

## engine 39 — grain repeats tool-made marks as a tile, rather than scattering over an area (v2.13.45)

**`surface.texture="grain"` no longer scatters directly across the area of a closed shape.** It puts a finite set of tool-made marks into a fixed-size `<pattern>` tile and repeats it through the closed contour as a carrier path. `density` decides only logical marks in the tile, `scale` only mark size, `opacity` only pattern children, and the seed only position and jitter.

**Of 606 cases, exactly the five that explicitly name grain moved; the other 601 are byte-identical to engine 38.** They are `C-display-surface-grain-pen`, `C-surface-grain-pen`, `C-surface-grain-pencil`, `E-wild-surface-grain-pen`, and `E-wild-surface-grain-pencil`. `stipple`, `paper_grain`, `aquatint`, `wash`, `hatch`, `crosshatch`, and `solid` do not move in this version.

**The four tool signatures remain in the tile children.** The carrier is the closed contour with `fill="url(#pattern)"`; grain does not collapse to generic circles. The same grain structure is used across SVG profiles, with no additional `filter` or `clipPath`.

## engine 38 — a wash named on a line is a broad pale sweep (v2.13.35)

**Of the nine surface words, `wash` alone was drawn nowhere at all when it landed on a line or an arc.**
Of the 3,458 works in production, **567** name a wash on a line or an arc, and **490 of them (86.4%) appear
nowhere** -- 354 dropped for want of a closed shape before them, 136 dropped because that shape already
carried a surface. **The remaining 77 were moved onto some other shape.**

### Three words now speak about the run of the mark, and they do not land in the same place

Grain and bleeding raise **the sheet's own two quantities** (absorption and tooth, engine 37).
**A wash says nothing about the sheet** -- it is how the ink was diluted, not what it was laid on -- so
**the renderer draws it as a band three times as wide at 0.35 of the opacity.**
`MARK_SURFACE_WORDS` has two readers, and **the second looked its words up in the table of the sheet's two
quantities**, so adding a word alone raised an exception. A word that is not in that table now returns the
support unchanged.

### The width and the darkness of a mark are decided in one place

All **fifteen** call sites of `_stroke_width_px` were routed through two entrances (`_mark_width_px`, and
`_nominal_mark_width_px` for the separate quantity that carries no thinness). **Seven are reachable from an
open shape** -- the amplitude of the waver, the `rotring` line, two material outlines, the material line, the
hand-drawn line and **the hand-drawn arc**. **On a closed shape the entrance passes straight through**, so no
closed drawing moves a byte.

### The corpus grew by nine cases, and those nine are the only ones that moved

**Of 606 cases, the nine new ones moved and the existing 597 did not move a byte.**
The nine split across two changes: **four for the wash** (two lines, one arc, and one closed-shape control
that must not move) and **five for ledger I-289.**

**I-289: the frozen corpus held four `display` cases and all four used `pen`.** `pen` carries no texture
weight, so **no case went through the texture-filter branch at all** (SVGs carrying `filter="url(#texture-`:
**0 of 597** in engine 37, **5 of 606** in engine 38).

**Drypoint is excluded on the general branch, but the burr writes `url(#texture-drypoint)` outright** (three
places). **The burr is drypoint itself.** The reference count is exactly one, and the general branch fires
zero times.

### `brush_thick` alone does not turn its width ratio into an area ratio

Three times the width puts **2.10 times** the ink area on the sheet (`brush_thin` 3.96, `crayon` 3.46,
`chalk` 3.50, `pencil` 3.09, `pen` / `rotring` / `silverpoint` 3.00), because the taper of the bristle and
where the sheet cuts do not scale with the width. **The opacity ratio is exactly 0.350 for every tool.**
**Whether it needs a ceiling is undecided.**

## engine 37 — a sheet called by name changes how the brush runs (v2.13.31)

**The seven grounds have been tiled onto the sheet since engine 34, and they never reached the mark.**
`Support` in `stroke_engine.py` was a single constant: the parameter was there, and no caller ever
passed one. This version hands each support's absorbency (`absorb`) and tooth (`tooth`) to the stroke
synthesizer. **The same description with the same seed now leaves a different mark on washi than on
canvas.**

### The sheet reaches all eleven synthesis call sites

`render()` reads it from the Score once and **passes it down as an argument** (no module-level
state). Thirteen functions take `support`, ten of them as a keyword-only parameter with no default,
so a forgotten hand-off is a `TypeError`. **A ground name that is not in the table raises
`ValueError` rather than falling back to the default.**

### `面: 粒` and `面: にじみ` stay on the line (ddl engine 20)

**Of the nine surface words, these two speak about how the mark runs rather than about an inside.**
coerce used to move every surface off an unclosed instruction to the closed shape before it, or drop
it, so **these two words were never drawn on the 406 works in production that carry them** (including
the 49 that were being moved). This version leaves them where the sentence put them, and the renderer
**works the sheet harder for that one instruction** (a factor of 2.0, **capped at 3.0**). The other
seven words (`wash`, `paper_grain`, `hatch`, and the rest) are handled exactly as before.

### The corpus grew by nine, and twelve cases moved

**Twelve of the 597 cases moved**: the nine new ones and three existing (`C-ground-washi`,
`C-ground-ink_wash`, `C-groundseed-auto-washi`). **The nine were needed because the corpus had no
case the mechanism runs through** — only four frozen cases use the `display` profile, all four draw
with `pen`, and `pen` carries no texture weight.

**`pen` barely shows the sheet at all.** Its affinity is (0.15, 0.15), which leaves an arrival
probability of about 0.005 over 49 samples, so **only the two supports that absorb more than `paper`
(washi and ink wash) crossed the threshold, and the refusing side never did.** That is why the nine
new cases are written with `brush_thick` and `chalk`.

## engine 36 — a wash is a field, not a set of stripes (v2.13.27)

**Of the nine surface words, `wash` was the only one that called itself a field without being one.**
Every sweep ran parallel at a constant pitch, one sweep was only 0.44 to 0.74 of that pitch wide, and
**no layer reached the paper between two sweeps** — **19.9% (square) / 21.1% (triangle)** of the
inside of the shape stayed bare and read as evenly spaced stripes. **A wash has no bare paper in it.**

### The only thing that closed the gaps was the width of the sweep

**A 14-rung ladder was measured the cycle before**: varying the angle per sweep and scattering the
pitch **moved the amount of bare paper not at all**. The only rung that moved it was the one that
widened the sweeps, and the author picked the cell `G3` from it. **The width goes to 0.88–1.48 of the
pitch and the opacity factor down from 0.42 to 0.22.**

**Those two are the only quantities that moved.** The pitch, the layer count and the layer angles are
identical to the previous version down to the last decimal, and no ground is laid underneath (**none
of the three rejected proposals went in**).

### Closing the gaps darkens a wash, so it is lightened

**Bare paper falls from 19.9% to 0.67% and from 21.1% to 1.09%**, and **the composite ink lands at
+2.0% / +1.1%**. **The opacity came down not as a preference but to undo a side effect** — the rung
that only doubled the width came out 1.5 to 1.9 times the product's ink.

**What is left is a rim along the contour, a median of 2.0 / 2.2px deep.** The sweeps are clipped at
the contour (engine 35's cut already reached the wash) and a hand tool tapers at its ends, so only
the outermost band runs thin. **Stripes would put a band the width of the pitch across the shape.**

### The cost is crossing the rim by twice as much

**The excursion went from 12.3 / 11.0px to 25.8 / 21.7px.** **That is half of one sweep's width, and
the same relation held in the previous version** — a brush with width crosses the rim by half of it.
The 20.0px the grain gate uses is **a number decided by the size of one speck**, so it is not applied
to the wash; the same claim is restated in the wash's own unit as "half of the widest a single sweep
gets".

### The corpus did not grow, and only six cases moved

**Of 588 cases, exactly the six whose surface texture is `wash` moved.** The other 582 are
byte-identical to the previous version, and **no case id is new, so all six carry discriminating
power**.

**Engine 35's entry said the six wash cases would not move because there was no approved "how it
should look" to move them towards.** This version produced it.

## engine 35 — a surface belongs to the shape that carries it (v2.13.24)

**Of the nine words for how the inside of a shape looks, `hatch` and `crosshatch` were the only two
that did not stay in their shape.** Each row was laid at a fixed 1.3x the bounding box's diagonal and
no intersection with the outline was ever taken, so **a circle asked for parallel lines came out as a
striped sheet** — **61 to 64 percent** of the surface ink fell outside the form, and the excursion the
grain gate measures was **413.9px** on a triangle against a **20.0px** limit.

### Only the ends are cut; everything upstream of the cut stays

**Every row is now cut against the contour** (through `_line_spans`, the helper the fill branch
already uses). A concave form gets one stroke per span, so no row crosses the void, and
**a row that misses the outline draws nothing.**
**It is not a clip path** — `compat` emits none, and **a cut only `display` can see is not a cut.**

**Nothing above the cut moves.** The angle, the pitch, the spacing gradient, and the per-row jitter
still decide where a row sits and how it leans, and **the printed parallel line stays regular**
(author's ruling, 2026-08-14) — the `hatch-spacing-*` class values are unchanged in all nine cases
that moved.

### The corpus did not grow, and exactly nine cases moved

**Of the 588 cases, the ones that move are exactly those whose surface texture is `hatch` or
`crosshatch`** (5 `hatch`, 4 `crosshatch`). **The six `wash` cases do not move** — that a wash reads
as stripes is a separate ruling, and there is **no approved form of it yet to draw from**, so this
version leaves it alone.

### Under a wild performance the hatch has fewer rows, not smaller ones

**No mark changed size; only the count fell** (`hatch`/pen 39 → 29, `crosshatch`/pencil 78 → 58).
Rows that never cross the outline are no longer drawn — a consequence of removing the outside,
not of thinning the inside.

## engine 34 — the ground is a support you can name (v2.13.22)

**The ground used to be four materials — paper, washi, ink-wash ground, charcoal ground — and it did not
arrive from the description at all**: `washi` appeared in **0** of 3,086 production works and **0** of the
2,125 measured ones. **There are now seven supports, and a new saijiki category `じ` (grounds) lets a
description name one.**

### The seven are `<pattern>` tiles, and the profile does not decide the ground

**Paper, washi, ink-wash ground, charcoal ground, canvas, drawing paper, mezzotint.**
Through engine 33, `display` drew a `feTurbulence` rectangle while the other two profiles scattered grains,
and **the claim that a support is the character of noise was measured inside that filter.**
**The mechanism is gone.** All seven now tile a `<pattern>` and **reference no `<filter>` at all**, so
**the same Score drawn under all three profiles gives a ground layer that matches byte for byte.**

### The cost limit is bytes now, not a count of elements

The engine 15 rule — a support is the character of noise, not something drawn, which came from a version
that drew 38 fibres and let the ground take 46% of the whole picture — **stopped meaning anything once the
ground became a tile**: the 80 strokes inside a tile are written to the file once.
**The limit is now the byte size of the ground layer (24 KB, author's ruling 2026-08-14).**
**Mezzotint is the largest in bytes (17,918 B) and canvas the largest in tiles on screen (21,626 for the
plain weave)** — **two different quantities**, and it is the tile count that drives the cost on Android.

### The DDL layer moved in the same version (`ddl_engine_version` 18 → 19)

It was raised because **the vocabulary that can be performed grew**. **No deterministic output moved**:
`changed_from_previous` for `ddl-engine-19/` is **empty**.

### The corpus grew by two to 588 cases, and 13 moved

**All 13 that moved are ground cases** (the seven materials, plus the ground field and ground seed cases).
**No case without a ground moved.**

## engine 33 — a repeated unit can be more than one mark (v2.13.19)

**Every arrangement this engine could perform repeated a single instruction.** A pair -- an arc, and the arc
touching it at both ends -- therefore had to be handed over as **every resolved pair in full**, and each
follower's `touching` was then resolved against **whichever instruction happened to precede it** rather than
against its own head.

### Copy the span first, resolve the relations inside it second (the order decides the result)

**`Arrangement.group_size` says how many consecutive instructions one repeated unit spans.** The renderer
**copies the whole span first and resolves each copy's relations within it second** -- that order is what makes
the relation local. A member is carried by the transform its head received: **the rotation delta about the
head's anchor, the scale its extent was given, and the cycled colour where the head has a cycle.**

### When something has to go, the claim goes and the marks stay

**The whole-work budget counts `count * group_size`.** **The instruction ceiling stops at a span boundary**
rather than cutting a unit in half, which would leave half a pair standing. **Where no span fits at all the
span is dissolved and the work is drawn up to the ceiling** -- emptying the instruction list was a possible
reading, but a work with nothing in it is not a smaller work. **The limits are settings**, so what the ceiling
drops where the plugin's instructions join the Score is written into the notes the response already carries.

### Nothing written before this moves by a byte

**`group_size` is excluded from serialization when it is 1.** Every stored Score reads and draws exactly as it
did, and **all 582 existing cases are byte-identical.**

### The corpus grew by four to 586 (**group H is new**)

**Before they were added the corpus could not see this change at all**: every case above H holds a score of
**exactly one instruction**. Four are new -- **three state a span and one is the control**
(`H-pair-scatter-plain`, the same two instructions with no span, which is the picture engine 32 drew).
**⚠ Every new ID counts as `changed_from_previous`**, so the discriminating power can only be shown by
perturbation.

### The DDL layer moved in the same cycle (`ddl_engine_version` 16 to 17)

**The document plugin now hands the API one prototype pair plus `count=N / group_size=2`.** **The public
expansion did not move by a byte** -- `instructions` still holds every resolved pair and the DDL text is the
same. **Only the form the API reads changed**, which is why **`score_instructions` joins the frozen part C**: a
record holding the public expansion alone would freeze a version whose change the corpus never reaches. **All
six C cases moved; the 13 A cases and the 30 B cases are byte-identical.**

### Only the DDL layer moved (`ddl_engine_version` 17 to 18, v2.13.20)

**A fill became a word like the other eight.** Eight of the nine *omote* quality words went to
`surface.texture` while **only 塗り went to the boolean `filled`**. Measurement said the destination field
was the whole of it (12/14 through `texture` against 0/14 in English through `filled`), so `SurfaceTexture`
gained `solid` and the fill joined the road that carries.

**`filled` stays.** The coerce branch **derives each way from the other**, so both ways of saying it leave
the Score stating one interior state. **The drawing does not move**: `solid` is folded out of the
performance seed (without that, every saved filled shape would have its stroke seed redrawn), and a Score
with only `filled=true` and one with only `texture="solid"` emit byte-identical SVG.

**`changed_from_previous` is 30 (all of B), but only 3 cases move their Score** (five closed-shape
instructions); the other 27 gained one branch-report key, as in engines 11 and 15. **The 13 A cases and the
6 C cases do not move at all.**

## engine 32 — a cluster and a path keep their shape on any canvas (v2.13.13)

**Engine 31 put the ring and the region on the short edge, but a cluster and a path were still stretched by the
aspect.** Those two arrangements carry **36.2% of the marks production expands** (27.1% cluster, 9.1% path).

**A cluster's band is built in a rotated frame and then written straight into normalized space.** On the pillar
(1:5) one clump came out as a narrow vertical stripe and on CinemaScope as a wide one -- **for one description,
the band's own aspect moved by a factor of 8.8 between those papers** (0.0395 to 0.4646). A path did the same:
**a `wave` swung 220px on the square canvas and 44px on the pillar**, and the jitter of a `diagonal` or a
`top_to_bottom` bought a different number of pixels on each axis.

### Rotate first, put it on the short side second (the order decides the result)

**The cluster's offset is rotated first and scaled second.** Scaling the axes before the rotation would turn the
rotation itself into a shear, and the band would come out neither its own shape nor the canvas's. A path is
scaled **on its cross axis only**. Measured, the cluster's bounding aspect came out at 0.19771 -- the square
canvas's value -- on all five papers.

### What was left alone (**none of it is shape; all of it is how much paper is used**)

- **`margin` and `span`** -- how far a path travels along its own line. **Whether `horizontal` and `vertical`
  should use the paper's long direction is [I-135] (3)-b and unruled**, and this change does not touch it
- **`right_half`'s reach** and **`_path_pos`'s default branch** (which returns `_scatter_pos`)
- **`_scatter_pos`** -- an affine map takes a uniform scatter to a uniform scatter, so it already means the same
  thing on every sheet
- **The cluster's centre** -- `_clustered_pos` calls `_path_pos` itself to resolve that centre, and **`canvas` is
  deliberately not forwarded there.** Forwarding it would level the centres too, and "the middle cluster is
  above the others" would stop meaning the same thing on paper of a different shape (R3)

### Not one coordinate moves on a square canvas

**On a square canvas the factors are exactly 1.0.** Two layers hold that: the engine 31 placement coordinates
frozen for four subjects, and a byte comparison of the whole SVG against a drawing made with the rule dropped
(four subjects × two seeds).

### The corpus grew by thirteen, to 582

**The corpus could not see this change at all before** -- it held ten cluster and path cases and **every one of
them was square** (`_case`'s default). The thirteen new cases are **nine that move and four square controls**.
**None of the existing 569 moved.**

**⚠ Each subject is drawn on the papers whose long side is the axis it spreads on**: a `top_to_bottom` on the
pillar has a factor of exactly 1.0 and would be frozen unable to fail. **⚠ Every new ID counts as
`changed_from_previous`**, so **the nine and the four cannot be told apart in the manifest. Only a perturbation
can show which case discriminates.**

### The same wiring exists on Android (**three versions behind**)

**Kotlin's `pathPosition` and `clusteredPosition` hold no short-side basis at all** (ledger I-233): the gap is
not engine 32 alone but **30 (a mark's extents), 31 (the ring and the region) and 32 (the cluster and the
path)**. **On the day it is ported, the point is not to pass `canvas` to the one call `clusteredPosition` makes
to resolve its centre.** The reference fixture (64 files under `render-engine-32/`) was baked by the
implementing session.

## engine 31 — the arrangement of marks keeps its shape on any canvas (v2.13.8)

**Engine 30 put a mark's own extents on the short edge, but the layer that arranges those marks was still
stretched by the aspect.** A `radial` ring became pixels through `canvas.width` across and `canvas.height`
down, so on the pillar (1:5) **the ring came out with an aspect of 0.19** -- round dots sitting on a flattened
ring. An `at.region` behaved the same way: **a box written as a square came out as tall, or as wide, as the
canvas.**

### Only the extent moved; the centre did not

**A ring's radius and a region's half-extents become pixels through the canvas's short edge (`canvas.unit`) on
both axes.** **A region's centre stays proportional** -- "upper right" is the upper right of any canvas, and
putting placement on the short edge would change the composition itself (author's ruling, 2026-08-12).

**`arrangement.margin` was left alone** (rejected in the same ruling): spreading to the frame is what `scatter`,
`horizontal` and `vertical` mean, and the 0.83-of-the-short-edge gap above and below on the pillar is kept as
the specification.

**Two sites read the region** -- `_resolve_at_region`, **the anchor every region instruction passes through**,
and the grid branch, which reads it again for itself. **Both go through one helper. Fixing only one leaves the
other's test green.**

**On a square canvas the two arithmetics are the same.** Centre plus or minus half-extent does not round-trip in
floating point even at a factor of 1.0, though: for region `[0.6, 0.18, 0.82, 0.4]` `y0` moves by **2.78e-17**,
which crossed the digest's rounding boundary and **moved two square controls**. A short circuit returns the
region untouched when both factors are 1.0.

### The corpus grew by sixteen, to 569

**The corpus could not see this change at all before** -- of 553 cases the five carrying a `radial` were **every
one of them square**, and **not one** carried an `at.region`. The sixteen new cases are four subjects (a ring, a
region resolved for one mark, a grid over a region, and a group whose region is only its anchor) on all four
aspects: **the twelve non-square cases all move and the four square controls all stay**, measured on both trees.
**None of the existing 553 moved.**

### The same wiring exists on Android

**The Kotlin renderer stretches arrangements per axis too** (ledger I-217). **This change is server-side only;
the Android catch-up is a separate contract.** The reference fixture (64 files under `render-engine-31/`) was
baked on the accepting side. **⚠ `gen_android_reference.py` resolves the performance without a `canvas`**, so
when the port lands those sites need one, or the Android expectations will keep asserting pre-31 behaviour.

## engine 30 — a mark keeps the shape its description gave it on any canvas (v2.13.6)

**Engine 29 turned `size` into pixels through `canvas.width` and `canvas.height` separately, so the same
description drew a different shape on every aspect.** A square written `size [0.3, 0.3]` came out 1.61:1 on the
golden canvas and 0.20:1 on the pillar. **An ellipse written `size [0.4, 0.2]` -- wide, 2:1 -- came out 0.40 on
the pillar: upright, the reverse of what the description said.**

### Only the extents changed; placement did not

**Both extents become pixels through the canvas's short edge (`canvas.unit`).** All twelve sites in
`renderer.py` go through one helper, `_size_px`. **Coordinates still scale with width and height**, so
**the aspect still decides where a mark sits, and no longer what shape it is.**

**On a square canvas `unit == width == height`, so the two rules are the same arithmetic.** Only non-square
cases drawn from `size` move, and **the rebake moved exactly three**
(`D-canvas-{pillar,vertical,wide}-filled-square-rotring`).

### The corpus grew by four cases, to 553

**Four `D-canvas-*-ellipse-pen` cases were added**: the corpus held **no wide mark on a narrow canvas**, and so
**could not tell a widened mark from a preserved one**. The added cases discriminate:
`D-canvas-pillar-ellipse-pen` is 0.32 (upright) under the engine 29 implementation and 1.59 (wide) under
engine 30, while `D-canvas-square-ellipse-pen` is 1.59 under both -- the control that shows the square canvas
does not move.

### The same wiring exists on Android

**The Kotlin renderer also stretches `size` per axis** (ledger I-217). **This change is server-side only;
the Android catch-up is a separate contract.** The reference fixtures (64 files under `render-engine-30/`)
were baked by the accepting session.

## engine 29 — the same grain is counted on every machine (v2.11.17)

**Engine 28's frozen corpus was baked on a Mac, and rebaking it on Linux produced different bytes for 6 of
the 549 cases.** **That is what kept main's CI red** (the `reference-corpus` workflow's "Regenerate current
render corpus" hit the generator's identity guard and exited 1; ledger I-178). **It was not a regression but a
second exposure that engine 28 created.**

**All six were pencil, and only in the `material-outline stratum-1` polyline; the contour itself agreed on both
platforms.** **There were two kinds of split** — **three that differ in structure** (`A-pencil-polygon` 191 to
192 points, `E-wild-pencil-ellipse` 194 to 187 points and 50 to 48 fragments, `E-wild-pencil-polygon` 201 to 200
points) and **three of identical file length whose coordinates differ** (`B-white-broad-arc-pencil`,
`C-fill-ellipse-pencil`, `B-perlin-medium-circle-pencil`).

### The fix belongs on the counting side

**Every length the contact decision reads now sits on the same six-decimal pixel lattice the SVG writes**
(`CONTACT_LENGTH_QUANTUM = 6`). **Segment length, total arc length, sampling step, grain width and fragment
length share that lattice**, so `_resample_by_length` and `_contact_fragments` read the same numbers.

**Why rounding the coordinates is not enough:** one ULP can flip the boundary of "does one more sample fit",
which adds a point to `len(walk)`. **The threshold is a quantile of the samples themselves, so one more sample
jumps it to a different sample value**, and the crossing interpolation and the `length < 0.6` cutoff move with
it. **Rounding only the output coordinates leaves the three cases whose point counts move.**
**I-111 (engine 21, `ARRANGEMENT_QUANTUM`) closed a different route, and it is untouched.**

### 454 cases move and 95 do not

**The 454 that moved are exactly the 454 that carry a `material-outline` when engine 28 draws them** (by tool:
pen 235, pencil 83, brush_thick 71, crayon 31, chalk 18, brush_thin 16; by group: A 48, B 72, C 59, D 19, E 79,
F 128, G 49). **The 95 that did not are the five tools that carry no material outline** — the same 95 as under
engine 28. **The one case in group G's 50 that does not move is `G-fade-rotring-edge`**, and rotring carries no
material outline.

### The platform-stability gate now looks at the current exposure

**This gate did not see engine 28's exposure.** Its subject was group G's 50 cases, **none of the six splits
were in it**, and `test_group_g_is_the_whole_exposure` **only asserted `len(...) == 50`, never that G was the
whole of the exposure**.

Its shape now:

- **The exposure set is derived from rendered output** — draw all 549 once and count the 454 that emit a
  `material-outline`.
- **The main sample is 27 cases drawn twice** — the union of the 15 arrangement cases, the 6 that split between
  machines under engine 28, and one representative (`A-*-arc`) for each of the six tools that carry the layer.
- **A guard reads the gate's own source** and goes red if the exposure check returns to a hand-written count.
- **The paired test removes both stabilisers** (arrangement and contact length) and requires the same
  perturbation to move the same cases.

### Version and corpus

**Only `render-engine-29/` was baked; `render-engine-28/` was not touched by a byte.** **Both the implementation
and the acceptance confirmed on pentala's `/tmp` that a Linux rebake is byte-identical** — not the deployment
tree, and no service was restarted.

## engine 28 — the mark stays on its line (v2.11.13)

**Four rules move in one version, and every one of them is about what happens where the tool meets
the paper.**

1. **The wander is measured in stroke widths, not in the figure's representative size**
   (`AMPLITUDE_WIDTHS` = fine 0.35, medium 0.6, broad 2.0; the author chose the 0.6 from sheets drawn
   at 0.6 and 0.9)
2. **The material outline takes its offset from the performed ink rather than the intended geometry**
   (it is no longer a `wild`-only behaviour)
3. **The fray drops `stroke-dasharray`**: the stroke is drawn only where a contact field standing for
   the paper's tooth crosses a threshold
4. **A stratum is never wider than 0.33 of the tool's own mark, and its centre is never inside it**

**The corpus moves on 454 of its 549 cases and holds 95.** **The 95 are every case drawn with the
five tools that carry no material outline** (rotring 22, drypoint 21, silverpoint 19, computer 17,
burin 16), which is the measurement behind the sentence "this is the version of the six tools that
carry one".

### The yardstick is the mark, not the figure

**Through engine 27 the wander's amplitude never once looked at how thick the mark was.** At 8% of
the representative size (`medium`), **a thin pencil drawing a large arc left its own mark by eleven
widths.** Measured at the branch point, the drift over the stroke width on eight arcs ran **2.88 to
12.21**, and **all eight sat at 7.9-8.5% of their radius** — they agree although the tools
(`energy_lateral` 0.42 against 0.12) and the widths (1.40 to 2.07 px) do not, which is the proof that
the mark was not being read.

**At engine 28 the drift over the stroke width lands between 0.595 and 0.600** across six tools, two
thinnesses and four radii, and **it is flat in the radius**. **The clamp at 0.40 of the representative
size stays**: it is the safety valve that keeps a figure smaller than its own mark from wandering
further than it is wide, and it does not bind in ordinary use.

### What read as heavy was the position, not the quantity

**When the author called the square's decoration too heavy, the quantity was measured first.** The
decoration was **already laying down less ink than at engine 27** (962 -> 803 px² on the square).
**Read against the tool's own mark there were two outliers, and `brush_thin` had the widest stratum
of any tool at 0.47 of its mark and the closest offset at 1.07 half-widths.**

**The two rules deliberately read different widths.** **The cap reads the nominal stroke** — paper
tooth and powder do not get finer because the line was drawn finer, which is what
`test_material_outline_absolute_widths_do_not_move` holds. **The floor reads the actual stroke** —
where the tone sits is a question about the mark that was drawn.

**Pushing the stratum further from the edge produced the same picture** (673.1 against 672.9 px² on
the square). **The width was what mattered, not the distance.**

### A record that holds an older version cannot be replayed across one

**Six checks re-drew an older version's inputs and compared them against that version's digests, and
every one of them reached the older version by withholding a layer that had landed since.** Engine 28
moves both the material layer and the wander, so **that shape cannot agree in principle**. Where the
claim was about a feature, it was rewritten as **on-versus-off inside one version**.

**Two of the six are a loss, not a replacement.** `test_surface_stroke` lost its attribution
observation point (comparing the engine 15 and 16 manifests directly does not restate it either — all
eight digests differ, on thickness). `test_anchor_authority` held "a Score that declares no placement
is left alone" over **447 cases**; **401 of them move under a tool with a material outline**, so the
exclusion was rewritten as a rule and **the hold thinned to 92 cases**.

### The cap changed after the bake (found in acceptance)

**One frozen case could no longer be reproduced by the code that shipped.**
`C-fill-circle-chalk-extra_fine` was baked while the cap read the **actual** stroke width and holds
0.346500, while the code now reads the **nominal** one and draws 0.990000. **It is the only one of the
549 cases where a tool with a material outline meets a thinness**, so the other 453 that move and the
95 that hold did not shift by a byte. **The re-bake was done on the acceptance side.**

**The manifest's `reason` comes from a constant in the generator, so it does not follow a version
bump.** Engine 28's manifest shipped carrying engine 27's story, and acceptance rewrote it. **A table
is corrected automatically; a sentence someone wrote is not, and a byte-identity gate does not read
for lies.**

## engine 27 — the hand swings wider (v2.11.10)

**Engines 25 and 26 introduced two amplitudes. Engine 27 only widens them.**

**No rule and no exclusion changed.** `HAND_GROUP_SIZE` goes **0.25 -> 0.35** and
`HAND_GROUP_ROT` **12.0 -> 27.0**. **All nine hand tools carry the same amplitude**, and
**`rotring` and `computer` stay at 0**. The exclusions are engine 26's, untouched: `grid`,
single-member groups, the machine tools, `line`, `circle`, and groups that state a `rotation`.

**The corpus moves on 45 of its 549 cases and holds the other 504. No case was added.**
The 45 are circle 37, ellipse 3, line 1, square 1, triangle 1, arc 1, cloudform 1, and
**only 5 of them are reached by the angle rule as well** (the other 40 changed size alone).

### The frame correction fired on not one more group

**This is where the prediction was most wrong.** The expectation when the work was commissioned was
that a wider swing would push more groups into the frame correction. **The measurement says it fires
on the same 40 of 50 groups as engine 26, and on the same set.**

The reason is in the wiring. `_fit_group_to_anchor` **reads only the members' anchors**.
`_scale_member` preserves the anchor through three coordinate corrections, and `_turn_member` turns
about the anchor, so it moves no coordinate. **However wide the swing, the input the frame correction
reads is bit-for-bit the same.** Anchors matched exactly across both amplitudes in 47 of 50 cases, and
the three that did not differ by at most 1.0e-9 (`square` and `triangle`, whose anchors are rebuilt
from a bbox, and `line`, whose anchor comes from its two ends — one step of the nine-digit grid, the
same phenomenon the existing `ANCHOR_TOLERANCE = 2e-9` covers).

### "Marks stay inside the frame" was not true before this version either

The frame `[0.02, 0.98]` is a contract about anchors, not about how far a mark spreads. Measured,
**41 of 50 groups already had member outlines crossing the canvas `[0,1]` at engine 26** (furthest
0.050187). **Engine 27 has the same 41**, with the furthest at **0.054262** — the count did not grow,
and the one that reaches furthest got 0.4% of a canvas deeper.

**No check in the current code corresponds to this fact.**

### Replaying a frozen record puts back the amplitude, and nothing else

The check that replays engine 25's 43 frozen drawings through today's product and compares digests
turns red the moment the amplitude rises. **It now puts `group_hand` back to 0.25** rather than
withholding `_apply_member_sizes`. **Withholding it would pass for an implementation that had dropped
per-member size altogether — the reading engine 25's own gates exist to reject.** The angle amplitude
is left at whatever the tree states (27.0), and **the 43 digests still land**, which re-confirms that
the angle rule reaches none of those cases.

## engine 26 — every member of a group finds its own angle (v2.11.8)

**Engine 25 gave up "the same size". What was left was "the same angle".**

An `Arrangement` says only "several of the same shape". **Nowhere does it say they all face the same
way.** After engine 25 the N members of a group still shared a single angle. **This is the last stage
of improvement plan #5.**

**The spread lives in the tool grammar.** `ToolGrammar.group_rot` holds how many degrees the members
of a group drawn with that tool may scatter (12.0 = ±12°). **All nine hand tools carry the same ±12°**
(`HAND_GROUP_ROT`) and **`rotring` and `computer` are 0**. This is the third rule of that shape, after
`fill_hand` in engine 22 and `group_hand` in engine 25: **exact repetition by a machine is a
signature, not a defect.**

### Not one pixel of placement moves

`_turn_member` rewrites `rotation` and nothing else. **`_apply_rotation` turns a mark about its own
anchor**, so **the three coordinate corrections engine 25 needed have no counterpart here.** Size can
move a centre; angle cannot. **A group is placed after expansion by `_fit_group_to_anchor`, which
reads only the anchor**, so placement is unchanged as long as the anchor is preserved.

### Five exclusions

| Excluded | Why |
|---|---|
| `line` | Turning a line makes a different line |
| `circle` | Turning it changes nothing visible while consuming performance seed |
| A group that states its `rotation` | If the description names the angle, the description wins |
| `grid` | A lattice is meant to line up (the same author's ruling as engine 25) |
| A group of one | There is nobody to differ from |

**⚠ The test is `stated.rotation is not None`, not truthiness.** Production holds **141 groups that
state `rotation: 0`.** Written as a truthy test, **exactly those 141 fall through to the "unstated"
side and get turned.** A case stating `0` was added to the corpus, with a gate that watches only that
point.

### The angle comes from the performance seed

Engine 23 separated composition from performance, so **deriving the angle from the placement seed
would break that separation.** It reads the same seed as engine 25's size (`member_seed`).
**⚠ Engine 25 named that expander argument `size_seed`, but angle reads the same seed, so the name
had grown narrower than the thing. It was renamed to `member_seed`.**

### The corpus

**545 → 549 cases. Only 3 existing cases moved; 542 are byte-for-byte unchanged.** The three are
`G-size-ellipse-edge`, `-square-` and `-triangle-`, which engine 25 added itself — **the groups that
are neither circles nor lines carried straight over into this stage.**

**⚠ The corpus held no `arc` group, no `cloudform` group and no group stating a `rotation`.** Four
cases were added — `G-angle-arc-edge`, `G-angle-cloudform-edge`, `G-angle-stated-zero-edge` and
`G-angle-stated-30-edge`. **The generator asserts that those four discriminate before it writes them
out** (the same practice as engine 25).

### ⚠ Not one golden digest moved

Engine 25 moved 37 corpus cases and the goldens with them, but **the three existing cases engine 26
moved were none of them checked against frozen bytes.**
`test_legacy_arrangement_layouts_keep_golden_output` stays green because **all four of its goldens are
circle groups.** **When estimating the next stage, ask whether that stage passes through a layer
checked against frozen bytes.**

**`ddl_engine_version` does not move** (still 7). Nothing through Stage 2 changes by a byte.

## engine 25 — every member of a group gets its own size (v2.11.7)

**An `Arrangement` says "several of this shape". Nowhere does it say "all of them the same size".**

Through engine 24 the expansion rewrote coordinates and nothing else, so **the N members came out
exactly congruent — one shape copied N times.** The description never asked for that congruence:
**it was the largest signature the engine was still adding on its own.**

**The amplitude belongs to the tool's grammar.** `ToolGrammar.group_hand` holds how much the members
of one repeated group differ in size, as a fraction either side of the stated dimension (0.25 =
0.75x..1.25x). **All nine hand tools carry the same ±25%** (`HAND_GROUP_SIZE`); **`rotring` and
`computer` are zero.** Deriving it from `fill_hand` was rejected: **the ruling was given on samples
that applied one ±25% to four tools whose `fill_hand` spans a factor of 18**, so scaling it per tool
would leave the picture that was approved.

### The size comes from the performance seed

Engine 23 separated the composition seed from the performance seed, so **which of the two feeds the
size decides whether that split survives.** Placement is drawn from `placement_seed` (the
composition seed when one is stated, otherwise the performance seed); **size is drawn from the
performance seed.**

**⚠ This version uncovered that the expander's second parameter had been misnamed since engine 23** —
it was called `performance_seed`, but what reached it was the `placement_seed`. **It was renamed to
match what it holds, and the performance seed added as a separate keyword argument.**

**The size seed is derived from the instruction as stated, before any member is shifted**, so every
member of one group draws from the same sequence — otherwise it would no longer be a spread *within*
a group.

### Placement does not move by a pixel

After expansion, `_fit_group_to_anchor` places the group and **reads nothing but each member's
`_anchor`**, so **a scaling rule that moved an anchor would hand the placement a different group.**
All four rules preserve their own anchor:

| Shape | What is scaled | What stays put |
|---|---|---|
| `line` | both ends, **about the midpoint** | the midpoint |
| `square` / `triangle` | both components of `size`; **`position` is pulled back by half the growth** | the centre of the bbox |
| `circle` / `arc` / `polygon` | `radius` | `center` |
| `ellipse` / `cloudform` | both components of `size` by the **same** factor (**the aspect never changes**) | `center` |

**Exactly three groups are left alone.** **`grid`** is the tiling whose point is that the cells match
(author ruling); **a group of one** has nobody to differ from; and **the machine tools** carry a
`group_hand` of zero.

### The version and the corpus

**541 → 545 cases. Forty-one moved** (37 existing plus the 4 added) **and 504 did not move by a
byte.**

**⚠ All 37 that moved are `circle` groups.** The corpus walked nothing else, so **one group each of
`line`, `square`, `triangle` and `ellipse` was added.** Line, ellipse and square alone are 82.8% of
the marks in production, yet **three of the four rules had never been baked.** Before writing them
out, the bake asserts that those four cases discriminate: taking the size layer out changes all four
drawings, and the four primitives are four distinct kinds.

**`ddl_engine_version` did not move** (still 7). Nothing changes up to Stage 2.

**The Android reference fixtures gained `render-engine-25/` (55 files) and not one line of Kotlin
changed** — **Android reads only the directory of the version it names.**

## engine 24 — the fade reaches every member of a group (v2.11.6)

**"It fades from the centre to the edge" was drawn as "all of it is a bit pale".**

`Arrangement.fade` declares how a group falls off — outward from its centre (`outward`), or along
the direction it travels (`directional`). Up to engine 23 the renderer answered that with **one
constant for the whole group**: 0.40 for outward, 0.48 for directional. **The same number on the
nearest mark and on the farthest.** The declaration states a falling-off; what was drawn was a
uniform paleness. **In production that is 2,738 of 6,425 groups (42.6%) and 83,703 of 178,694
marks.**

**Each member now carries its own ceiling**, ramped 0.62 → 0.18 outward and 0.70 → 0.26
directional, by its position within the group. **No vocabulary is added and no field** — the
declaration was already there.

**The carriage is `color_hint`.** The tag is written after the colour cycle rebuilds the hint, and
**read back before normalisation flattens the decimal point**. A consumer reading the normalised
value sees the ramp already levelled out.

**Placement, touch and the performance seed are untouched.** `color_hint` sits outside
`_SEED_INSTRUCTION_FIELDS`, so **the path coordinates of a fading group are byte-identical to
engine 23 and only the opacity attributes differ.** The surface seed does not move either: it drops
the tag before it hashes the instruction.

**A group that cannot fade was left exactly as it was.** A ring is equidistant from its own centre,
and so is a pair. **Ranking them would draw a gradient nobody stated.**

### A ring is not equidistant when measured from the centroid

**This version found it.** `_rhythm_t` returns 0 to 1 **inclusive at both ends**, so **a ring of 12
puts its first and last member on the same point.** That doubling pulls the centroid off the axis
by **radius / count** (0.025 measured). **Measured from the centroid a ring is no longer
equidistant, and a gradient appeared running once around the ring.** So the `radial` branch alone
measures from **its own centre of rotation** (`arr.center`, or the declared anchor). Every other
layout still measures from the centroid. **"A ring degenerates naturally because it is
equidistant" depended on where the centre was taken from.**

**A single-member group cannot be tagged by any implementation** — one mark has no position within
a group. The `count == 1` branch does not pass through `_shift`, so **even under engine 23 the
`fade` never reached the hint and such a group never faded** (measured: opacity 1.0).

### Version and corpus

**535 → 541 cases, and seven moved** (measured from `changed_from_previous`). **Six of those are
the added cases; the seventh is `G-scatter-fade-edge`, the only existing case that moved.** The
remaining 534 did not move by a byte.

`G-scatter-fade-edge` was **the whole of the corpus's fading** under engine 23 — outward, scatter, a
hand tool, no cycle, no surface. **Six cases were added for the routes that were never walked**:
directional along a path, a colour cycle, a derived surface seed, a machine tool (**a machine fades
too**, by the author's ruling: it has its own ink and its own core), and **the two degenerate groups
that must not move at all**.

**`ddl_engine_version` did not move** (still 7). Nothing through Stage 2 changes by a byte.

**The Android reference fixtures gained a `render-engine-24/` directory of 55 files, and no Kotlin
changed** — as with engine 23, **Android only reads the directory of the version it names.**

## engine 23 — the placement got a seed of its own (v2.11.5)

**Moving the seed to compare touches moved the composition as well.**

Up to engine 22 a single `render_seed` decided both the **placement** — where an arrangement puts
its marks — and the **hand**: each stroke's touch, the colour assignment, the ground, and the
resolution of the performance. **On a work that scatters 60 marks, moving `render_seed` alone moves
all 180 coordinates.** `SPEC.md` `:614` and `:678` state the opposite — **refining the touch keeps
the composition of the same Score**. **This version repairs a defect in the measuring instrument;
it does not add a feature.**

**`composition_seed` was already in the database, in the four render routes and in all four
clients. The only stretch it never crossed was the one into the renderer.** Five points of carriage
were built: the `renderer.render()` argument, the engine protocol, the default engine, the line
where `_render_with_metadata` takes it out of `render_metadata`, and `_render_score_svg` with
`RenderSvgRequest`. **The four callers of `_render_with_metadata` were not changed by one line.**

**Only the placement phase was separated.** `render_seed` keeps the touch,
`_work_color_assignment`, `_render_canvas_ground` and `_resolve_performance_score`, so **placement
and hand can be varied separately for the first time.**

**The fallback is `render_seed`, and the test is `is not None`.** A request that does not give a
`composition_seed` renders exactly as it did under engine 22. **`0` is the seed zero, not "not
given"** — written with `or`, zero would fall through to the fallback, and **the one user who asked
for seed 0 would be the one who does not get their composition back.**

### Version and corpus

**531 → 535 cases, and not one of the 531 moved** (`changed_from_previous` holds only the four
added). **The version rises although no picture changed, because the performable vocabulary grew** —
the second of the two conditions for raising it.

The four added are **twins of existing cases**, with the same Score and the same `render_seed`
(12345), differing only in `composition_seed` (777). Of the expanded marks, the ones that move are
`G-composition-scatter-edge` **60/60**, `G-composition-grid-center` **16/16**,
`G-composition-cluster-center` **60/60** and `G-composition-path-wave-edge` **60/60**.
**Layouts whose placement does not follow the seed (`G-radial-*` and `G-*-nopath-*`) were not
used** — their output is identical under either seed, so an expectation built on them is vacuous.

**`ddl_engine_version` did not move** (still 7). Nothing through Stage 2 changes by a byte.

**The Android reference fixtures gained a `render-engine-23/` directory of 55 files, and no Kotlin
changed** — Android reads only the directory of the version it declares, so **raising the engine
adds a directory and nothing else.**

## engine 22 — a fill gets an underlay, and what sits on it gets a branch (v2.11.4)

**A stroke WAS the fill, so every scan line had to be cut where it met the outline.**

Until engine 21 the scan lines were the fill itself, so each one had to be cut at its
intersection with the contour or the ink would spill outside the shape. **That cut is the third
of the three regularities the eye reads as a raster.** Measured across the eleven filled shapes
of the three works the author named as striped: inside one shape the scan angle varied by
**0.1 degrees**, the pitch by **6.1%**, and the endpoints **not at all**.

**A real element now holds the field.** Because the boundary belongs to the underlay, the marks
are free to leave the contour and free to fall short of it. The angle now moves **3.3–3.6°** per
stroke, the pitch's coefficient of variation rises to **30–35%**, and each end overshoots or
undershoots by up to **1.4–1.5 times the tool's width, in both signs**. **All three amplitudes
come from `ToolGrammar.fill_hand`, and a machine's are zero** — a `computer` fill still has an
angle standard deviation of 0.00° with its endpoints on the contour, so **the exact repetition
that is its signature survives**.

**The underlay is common to both branches; the threshold only decides what sits on top.**
Coverage — width over pitch — at **0.2** divides them: above it the marks are scan lines packed
to coverage **0.9**; below it they are rubbings. **Closing the gaps at pencil width would take
eight times the lines, and that is not how the tool is used.** A rubbing runs the width of the
form and takes the region's one direction, wobbling by the few degrees the hand gives — **the
same band the scan branch draws from** — so what separates the two branches is that the marks
are not on rows, and that the count is the stroke length one classic scan pass laid.

**The threshold is coverage, not a list of tool names.** The two cut the engine-21 corpus
identically, which is why a case that sends **one tool across the branch on thinness alone**
(`C-fill-circle-crayon-extra_fine`) was added. Without it an implementation that never reads the
coverage passes every other gate.

**The underlay is not built out of a filter.** `use_filters` is true only for `display`, so a
filter-built underlay makes **the fill itself vanish** in `compat` and `editable`. It is a real
element; on the texture branch it is **one pale field plus six layers that draw the mottling as
three concentric rings**, and **the composite is exactly the original flat value** — stacking
layers does not move the field's mean tone.

**A fill stroke now ends the way paint ends, not the way a drawn line ends** — heavy where the
tool lands (`loaded`), narrowing only at the release. **The default terminal for a contour
stroke is unchanged.** How far a mark stands out of its own field is the branch's value times
the tool's own `ToolGrammar.fill_contrast`, which is **1.0 everywhere except chalk (1.13)**.

**A tiny shape still degrades to one dab and `rotring` still degrades to a region fill. Neither
gets an underlay** (both are byte-identical to engine 21).

### Version and corpus

**525 → 531 cases** (six added: `computer`, `silverpoint`, `crayon`+`extra_fine`,
`brush_thick`+`extra_fine`, `chalk`, `chalk`+`extra_fine`). **52 moved** — 32 fills, **14 chalk
contours**, and the 6 new ones. **The 14 chalk cases are not fills**: a tool's properties
(`tooth` 1.00 → 1.30, and its texture filter's blur 1.44 → 0.40) cross the branches, so they
reached chalk outlines that are not filled at all. **What moved for a different reason is kept
on a separate roster** (`ENGINE_22_CHALK_CASES` in `test_anchor_authority.py`).

**`ddl_engine_version` did not move** (still 7). Nothing up to Stage 2 changed by a byte.

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

- **Thirteen catalogs hold ten `palette` colors each**, fixed at **exactly three achromatic and
  exactly seven chromatic**. The seven fill all six bands, one band holding two
- **The `map` grows from six keys to nine**, and **all nine are drawn from that catalog's own
  `palette`** (before, `map` and `palette` could name different colors)
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
| `palette` colors never drawn (catalogs in use) | 7 | **9** |

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
