# leaf-sketch Stage 0 harness

This is a disposable renderer sketch for deciding whether the candidate
relations `touching`（触れる）and `continuing`（続きから）deserve a canonical
language-design pass. It bypasses Stage 1 and Stage 2 and does not modify the
Score schema, SPEC, DB, migrations, or `rh2`.

## Existing direct-render path

The repository already provides the required LLM-free path:

```text
score JSON
  -> inku-cli render-score
  -> POST /api/render-svg
  -> strict Score validation / coerce
  -> default Render Engine
  -> SVG
```

`inku-cli render-score --png` also converts the SVG to PNG. The existing
`inku-cli contact-sheet` command assembles the replay PNGs.

The server must be running with the prototype explicitly enabled:

```sh
INKU_SKETCH_RELATIONS=1 uv run inku-server
```

With the flag absent or false, the API does not translate the two prototype
relation types. The unchanged strict schema therefore rejects them. Ordinary
Score payloads follow the existing path in either mode.

Log in with `inku-cli` before rendering. From `cli/`, one file can be replayed
without either LLM stage as follows:

```sh
uv run inku-cli render-score \
  --base-url http://127.0.0.1:8100 \
  --file bench/leaf-sketch/scores/00-single-b-touching.json \
  --out-dir out/leaf-sketch/00-single-b-touching \
  --prefix 01 \
  --png \
  --render-seed 1
```

Change `--render-seed` and `--prefix` together for each replay, then use:

```sh
uv run inku-cli contact-sheet \
  out/leaf-sketch/00-single-b-touching \
  --output out/leaf-sketch/00-single-b-touching/contact-sheet.png \
  --columns 4 \
  --thumb-size 280
```

## Score matrix

| File | Purpose | Replays |
|---|---|---:|
| `00-single-a1-coordinate.json` | fixed-coordinate core control | 8 |
| `00-single-a2-region.json` | independently resolved region control | 8 |
| `00-single-b-touching.json` | both endpoints snapped after performance placement | 8 |
| `01-young-a-core.json` | five region-resolved core leaf pairs | 5 |
| `01-young-b-touching.json` | five closed leaf pairs | 5 |
| `02-green-b-touching.json` | branch plus seven closed leaf pairs | 5 |
| `03-autumn-a-triangle.json` | current-core triangle control | 5 |
| `03-autumn-b-touching.json` | five radial two-arc blades | 5 |
| `04-fallen-b-touching.json` | ten closed leaves in a descending band | 5 |
| `05-dry-b-continuing.json` | three cloudforms with tangent-continuous curls | 5 |

## Transcription from the concept notation

- `group/repeat` is expanded into individual instructions.
- With the feature flag enabled, `from/to + bow` and `span + bow` are converted
  at the direct-render API boundary to the current arc fields `center`,
  `radius`, `angle_start`, and `angle_end`. The converter uses
  `perp(dx, dy) = (-dy, dx)` in normalized screen coordinates: positive `bow`
  bulges toward that normal, while the circle center lies on the opposite
  side. It always emits the minor arc and rejects `abs(bow) >= chord / 2`.
- Symbolic rotations are numeric degrees.
- `at.region`, the existing four canonical relations, material, color, and
  variation use their current schema fields.
- The prototype API boundary temporarily removes raw `touching` and
  `continuing` objects before strict validation and encodes them in a private
  renderer-only marker. The marker is consumed and removed during sequential
  resolution; it is never stored in the schema or DB.
- `touching {contact:"both_ends"}` applies a similarity transform to the
  current arc so its performed start/end coincide with the previous performed
  start/end. Its variation remains attached; the endpoints themselves stay
  fixed.
- `continuing` translates and rotates the current arc so its start coincides
  with the previous performed end and its start tangent matches the previous
  terminal tangent.
- A cloudform is closed and has no semantic leaf tip. For this disposable
  harness only, its deterministic rendered path seam is treated as the
  terminal endpoint for `continuing`. This convention is evidence to evaluate,
  not a proposed core contract.

## Concepts that do not map cleanly

- The strict Score has no composite/group primitive. A two-arc leaf cannot
  own one shared `surface`; `surface` on an open arc is ignored, so the green
  leaf wash is omitted.
- `along` always references the immediately previous instruction. Only the
  first green leaf can refer to the branch; the other six use manually
  assigned branch-band regions.
- The fallen-leaf `2/3/5` density gradient is represented by ten manually
  divided regions. There is no group-level density gradient.
- `fade` belongs to `arrangement`, but each leaf is manually expanded rather
  than one arrangement. Its directional fade is retained as the existing
  renderer hint `color_hint: "fade directional"`.
- The triangle control rotates each triangle around its own bbox center, so
  all five bases do not share one exact palm point. This is part of the
  current-core control rather than silently repaired geometry.
- Arc path variation is not a composite closed-shape deformation. The global
  performance touch and material grammar still vary the visible stroke, while
  the relation resolver accounts for the logical arc endpoints.

These limitations—especially manual group expansion, immediate-previous
`along`, and the cloudform seam convention—are Stage 1/Stage 2 design inputs,
not reasons to expand this disposable harness.
