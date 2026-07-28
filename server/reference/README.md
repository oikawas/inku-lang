# Deterministic-layer reference corpora

This directory freezes outputs from versioned deterministic layers so a future
change can show exactly which cases changed. It is a development asset and is
excluded from `git archive` source packages.

> **For the render engine versions themselves, start at
> [docs/spec/render-engine-history.md](../../docs/spec/render-engine-history.md)**, which lists
> every version newest-first with the measured moved/unchanged counts. The sections below stay
> here because they describe what the corpora hold, not what the versions changed.

## Layout

```text
server/reference/
├── README.md
├── render-engine-10/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── render-engine-11/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── render-engine-12/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── render-engine-13/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── render-engine-14/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── render-engine-15/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── render-engine-16/
│   ├── manifest.json
│   └── <permanent-case-id>.svg
├── ddl-engine-1/
│   ├── manifest.json
│   ├── a_expand/
│   │   └── <permanent-case-id>.ddl
│   └── b_coerce/
│       └── <permanent-case-id>.json
└── ddl-engine-2/
    ├── manifest.json
    ├── a_expand/
    │   └── <permanent-case-id>.ddl
    └── b_coerce/
        └── <permanent-case-id>.json
```

Each directory belongs to one deterministic layer version. DDL part A freezes
`expand_intermediate_ddl` text output. Part B freezes `coerce_score` output and
its observational branch report from independent literal Score inputs. A never
feeds B; corpora for different layers must not feed one another.

Directories are immutable after they are frozen. Never regenerate an old
version to accept changed output. Create the next version directory instead.
Case IDs are permanent: do not rename or delete them; new cases may be added.

A version directory holds an SVG body only for the cases that version changed.
Its manifest still carries the digest, byte count, tag counts, and classes of
every case, so a case that did not move is answered by walking back to the last
version where it did. The file listing therefore reads as "what this version
changed", which is the point of keeping the directories at all. Engine 11 holds
all 220 bodies because the master grid moved every case; engine 12 holds 199;
engine 15 holds 318 of its 350.

The corpus grows with the vocabulary, so the case count belongs to the version:
220 for engines 10-12, 228 for engine 13, 347 for engine 14, 350 for engine 15,
365 for engine 16.

## What engine 12 changed

Engine 12 de-regularizes the performance. The width envelope was a fixed
symmetric `sin(pi t)` hump, so every stroke was fattest exactly at its midpoint;
the correction event repeated with period 5; a closed contour carried a thin seam
opposite a fat middle; and the material outline used an even dash with evenly
spaced specks. All four are now driven by seeded low-frequency noise, and the
centreline itself gains a gesture scaled by the stroke length.

**21 of the 220 cases did not move, and both groups are informative.**

- **The 12 `rotring` cases are byte-identical.** Its grammar is all zeros, so it
  has no wobble for the de-regularization to reach. The machine pole of the tool
  vocabulary is exactly where it was
- **The 9 remaining `cloudform` cases are byte-identical.** Not for the same
  reason: `cloudform` is emitted as a Catmull-Rom path from
  `generate_cloudform_contour` and never enters `stroke_engine`, so it carries no
  material outline layer. Its contour does vary by tool (all 10 tool digests
  differ), but none of that variation comes from stroke synthesis. This is a gap
  that predates engine 12, not something engine 12 introduced

## What engine 15 changed

Engine 15 is five changes to `renderer.py` landed as one version, because they sit
in the same layer and bumping four times would have cost four Android follow-ups.

- **The seed of a mark is built from an allowlist.** It used to be a hash of the
  instruction's whole dump, so a colour annotation `coerce` wrote, a change of
  `count`, or a composition flag being flipped all re-rolled the hand. Now only
  what makes a mark physically another mark goes in: what it is, the tool, the
  geometry, its variation, its surface, and `arrangement.jitter`
- **The ground's seed names the paper.** `_texture_seed` hashed the whole Score,
  so anything at all moved the grain of the canvas. It is now made of `material`,
  `grain` and the performance seed, so raising the opacity darkens the same sheet
  instead of dealing a new one. That freed `ground.absorbency`, a field nothing
  had ever read, to be retired
- **`cloudform` joins the road every other closed contour takes.** It had never
  entered `stroke_engine` while claiming `stroke-engine-touch` in its class, and
  all three material mechanisms were absent from it
- **The corner shapes and the pen gain the material layer they never had.**
  `_render_corner_shape` had no material-outline call at all, so `triangle` and
  `polygon` were bare for every tool that owns one; and `pen`, the most used tool
  in production, had nothing but its body stroke
- **Strength stops being distance.** Each rung of the material intensity ladder
  had answered "the layer reads weak" by multiplying the outline offset, up to
  2.8x with a 3.5px floor. Measured against the band's own half-width as drawn,
  the strata sat 4.5x out for `pencil` and 6.5x for `chalk` — far enough to read
  as a second contour rather than a trace. The multiplier and floor are gone;
  darkness is still carried by the opacity gain, which is untouched

**318 of the 350 cases moved, and the 32 that did not are the point.** They are
the two machine poles — `computer` and `rotring` — across the seven shapes that
are not `cloudform`, plus the four `D-canvas` rotring cases. `rotring` is drawn as
geometry and `computer` repeats without error, so neither consumes the performance
seed the first change rewrote. Both move on `cloudform` alone, because that is the
one shape whose path they newly share: `rotring` drops the false
`stroke-engine-touch` from its class, and `computer` gains its `raster-bleed`.

Four cases entered and one left. `C-groundseed-auto-paper`, `-washi`, `-coarse`
and `-paper-opacity` are the first cases in the corpus's history to leave
`ground.seed` unset — until engine 15 every ground case pinned it, so
`_texture_seed` was called **zero times across all 347 cases** and the layer could
not be tested by this corpus at all. `C-ground-field-absorbency` was dropped:
with the field retired it renders byte-identically to `C-ground-paper`, and two
IDs for one drawing misleads the reader.

## What engine 16 changed

Engine 16 is three changes, each about a mark being made rather than a region
being filled in.

- **A surface is played.** Six of the eight texture words - `stipple`, `grain`,
  `paper_grain`, `wash`, `aquatint`, `bleed` - were circles scattered by a
  uniform random inside the bounding box, so they never saw the shape they
  belonged to, and `bleed` was one ellipse behind a blur. All six now go through
  stroke synthesis and follow the contour. The `display` profile draws the same
  marks the `editable` one draws instead of a filter over a clipped rectangle
- **A tiny fill is placed, not scanned.** Below a short side of roughly three
  percent of the canvas the scan could not fit its three lines, so the interior
  collapsed to a flat region fill. A mark that small is one touch of the tool
  and is now drawn as one dab
- **Thinness is a dimension.** Asking for a thin line had only one way to be
  said - name a thinner tool - so the request bent the choice of tool. The Score
  carries `thinness` (`fine` / `extra_fine`, no thicker side). The eleven tool
  widths are unchanged and nothing goes below the thinnest of them. The axis
  joins the seed of a mark, so a line asked to be thin is played by a different
  hand as well as drawn narrower

**333 of the 365 cases moved. The 32 that did not are the version's real
description.**

- **Every unchanged case is `rotring` or `computer`** (14 in group A, 14 in the
  wild group E, and 4 filled squares in group D). Their grammars are all zeros,
  so they consume no seed: an axis that changes the hand cannot reach a tool
  that has no hand. The machine pole stood still through engines 12, 15 and 16
- **`C-tinyfill-circle-rotring` is unchanged for a second reason as well.** The
  drafting pen keeps its region fill at every size, so the dab never applies to
  it. Its manifest entry carries no classes at all
- **`hatch` and `crosshatch` did not need stage 1.** Those eight cases already
  went through stroke synthesis, and they are byte-identical to engine 15 when
  compared with engine 15's seed material. They moved here only because the
  thinness axis entered the seed - not because the surface work touched them
- **The 31 fills above the size boundary are unchanged in mechanism.** Same
  reason: their bytes move with the seed, not with stage 2

The seven `C-thinness-*` cases pin the axis. `C-thinness-default-pen` states the
default explicitly and must draw what omitting the field draws. The two
`silverpoint` cases have identical byte counts and different digests: the
thinnest tool cannot be thinned, so its width does not move, but the axis is in
its seed, so its hand does.

## `render-engine-10` cannot be regenerated outside macOS

Engine 10 wrote some SVG attributes (`points`, `cx`, `cy`) as raw Python floats,
so 17 significant digits reached the file. `math.sin` differs by one unit in the
last place between Apple libm and glibc, which made 81 of the 220 cases differ
between macOS and Linux — the structure was identical and the largest relative
difference was 2e-16, but the bytes were not equal. The frozen corpus was taken
on macOS, so CI on Linux could never reproduce it.

Engine 11 declares one master grid for every emitted number (see
`inku_server.master_grid`), which puts the whole corpus four orders of magnitude
above that platform noise. Engine 11 onward regenerates byte-identically on any
platform; verified on macOS arm64 and Ubuntu x86_64.

Engine 10 is kept because the 10 → 11 diff is the evidence that only the written
digits changed and the drawing did not: across all 220 cases the count of numbers
is identical and no number moved by more than 5e-4 (the half-step of the old
three-decimal formatting). Do not try to verify engine 10 on Linux; only engine
11 and later are checked by CI.

## Regenerate and compare

Run from `server/`:

```sh
UV_CACHE_DIR=/tmp/inku-uv-cache \
UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python \
uv run python scripts/gen_render_reference.py
UV_CACHE_DIR=/tmp/inku-uv-cache \
UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python \
uv run python scripts/gen_ddl_reference.py
git diff --exit-code reference/
```

Each generator writes into the directory named by the layer version it reads, so
bumping a layer version leaves the new directory untracked. CI checks the whole
`reference/` tree, which means an unstaged new corpus fails the build until it is
committed. That is intended: a version bump must land with its frozen output.

For an unchanged layer, regeneration must be byte-identical. Each generator
exits unsuccessfully if case output changes while its manifest identity fields
remain unchanged.

Render inputs fix every Score field, color map, render seed, and SVG profile.
DDL inputs likewise fix every expansion argument and every Score field. The DDL
manifest stores the complete literal input, output path, SHA-256 digest, byte
count, and—for coerce cases—the output instruction count and fired branches.

## Bumping a layer version

1. Change the implementation and its independent layer version together.
2. Generate a new version directory; do not modify the old directory.
3. Compare every digest with the previous manifest.
4. Put only changed IDs in `changed_from_previous`; for render corpora, save SVG
   bodies only for those changed cases.
5. Run the generator twice; the second run must leave a clean worktree.
6. Run the full server tests and lint checks.

If output changes without a relevant manifest identity change, a dependency was
not fixed correctly. Repair the corpus design instead of updating frozen output.
