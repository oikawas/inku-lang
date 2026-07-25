# Deterministic-layer reference corpora

This directory freezes outputs from versioned deterministic layers so a future
change can show exactly which cases changed. It is a development asset and is
excluded from `git archive` source packages.

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
└── ddl-engine-1/
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
Its manifest still carries the digest, byte count, tag counts, and classes of all
220 cases, so a case that did not move is answered by walking back to the last
version where it did. The file listing therefore reads as "what this version
changed", which is the point of keeping the directories at all. Engine 11 holds
all 220 bodies because the master grid moved every case; engine 12 holds 199.

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
