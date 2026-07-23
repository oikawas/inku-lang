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

## Regenerate and compare

Run from `server/`:

```sh
UV_CACHE_DIR=/tmp/inku-uv-cache \
UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python \
uv run python scripts/gen_render_reference.py
UV_CACHE_DIR=/tmp/inku-uv-cache \
UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python \
uv run python scripts/gen_ddl_reference.py
git diff --exit-code reference/render-engine-10/ reference/ddl-engine-1/
```

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
