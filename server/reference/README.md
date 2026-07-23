# Render reference corpus

This directory freezes deterministic layer outputs so a future engine change can
show exactly which cases changed. It is a development asset and is excluded from
`git archive` source packages.

## Layout

Each versioned directory belongs to one deterministic layer. A render directory
contains a `manifest.json` and the SVG produced for each case that first changed
in that version. Engine 10 is the first recorded render version, so all its SVGs
are present.

```text
server/reference/
├── README.md
└── render-engine-10/
    ├── manifest.json
    └── <permanent-case-id>.svg
```

Directories are immutable after they are frozen. Never regenerate an old
version to accept a changed output. Create the next version directory instead.
Case IDs are permanent: do not rename or delete them; new cases may be added.
Corpora for different layers must not feed one another.

## Regenerate and compare

Run from `server/`:

```sh
UV_CACHE_DIR=/tmp/inku-uv-cache \
UV_PYTHON_INSTALL_DIR=$HOME/.local/share/uv/python \
uv run python scripts/gen_render_reference.py
git diff --exit-code reference/render-engine-10/
```

For an unchanged render engine, regeneration must be byte-identical. The
generator exits unsuccessfully if case output changes while all manifest
identity fields remain unchanged.

The manifest records the corpus, engine, Score schema, literal color-map digest,
source commit, freeze reason, `changed_from_previous`, every literal input, a
coordinate-normalized digest, byte count, SVG element counts, and class strings.
The digest rounds decimal coordinates to six places before SHA-256, matching
`test_renderer_wave_phase.py` and avoiding irrelevant macOS/Linux final-digit
differences in trigonometric results.

## Bumping a layer version

1. Change the implementation and its layer version together.
2. Generate a new version directory; do not modify the old directory.
3. Compare every digest with the previous manifest.
4. Put only changed IDs in `changed_from_previous` and save SVG bodies only for
   those cases.
5. Run the generator twice; the second run must leave a clean worktree.
6. Run the full server tests and lint checks.

If output changes without a corpus format, engine version, schema version, or
literal color-map digest change, a dependency was not fixed correctly. Repair
the corpus design instead of updating frozen output.
