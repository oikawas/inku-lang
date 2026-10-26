<p align="center">
  <a href="README.ja.md">日本語</a> ｜ <strong>English</strong>
</p>

# Example plugins

Vocabulary plugins written to the specification in [PLUGIN.md](../../PLUGIN.md), kept as DDL export files (`inku.ddl-export.v1`).
None of them is bundled with the product. Reading one in makes its definitions available to that new work only ([PLUGIN §5.1](../../PLUGIN.md#51-a-ddl-export-file-immediately-usable-by-an-author)).

| File | Word | Version |
|---|---|---|
| [water-ripples.en.ddl.json](water-ripples.en.ddl.json) / [water-ripples.ja.ddl.json](water-ripples.ja.ddl.json) | `Water.Ripples` (alias `Water.波紋`) | 2.0.0 |
| [water-rings.en.ddl.json](water-rings.en.ddl.json) / [water-rings.ja.ddl.json](water-rings.ja.ddl.json) | `Water.Rings` (alias `Water.水輪`) | 1.0.0 |

Both draw one ripple spreading on the water: `Ripples` seen from straight above, `Rings` seen at a low angle across it. What the two words share:

- They receive the ring count (`5 Water.Ripples.`, `5個のWater.水輪。`). The range is 1–6; a count outside it drops that word only.
- The rings are `ellipse`s, never true circles. Each ring picks its width and its height separately from a few factors applied to a fixed table, so each ring differs a little in proportion.
- The ring lines undulate. The fluctuation is `narrowly` for the inner two and `broadly` from the third outward, with the quality `undulating` and no frequency word (medium).
  The outer rings bend the most and the inner ones keep their shape. With `loosely` as the frequency the bending was barely visible, so none is written.
- The inner three rings are `fine`, the outer three `extra_fine`. The fifth is dashed and the sixth dotted, breaking up outward.
- The color is fixed to gray and the tool to the thin brush. Every declared parameter is required (PLUGIN §3.4), so a color parameter would stop the bare name from drawing.

## `Water.Ripples` (alias `Water.波紋`)

<img src="water-ripples.svg" width="360" alt="On a blue ground, toward the lower left, five thin gray rings spread out. They are not true circles; the outer rings bend more as they undulate. The outermost is dashed">

The Japanese export's `ddl` drawn as it is ([water-ripples.svg](water-ripples.svg)).

A ripple seen from straight above: rings stacked concentrically from the inside out around one point.

- With no count written it draws 3–4 rings.
- The center is one of five positions around and slightly below the middle of the canvas, chosen by the work's composition seed.

  | Candidate | x | y |
  |---|---|---|
  | 1 | 0.500 | 0.560 |
  | 2 | 0.380 | 0.620 |
  | 3 | 0.620 | 0.580 |
  | 4 | 0.440 | 0.680 |
  | 5 | 0.580 | 0.460 |

- The base ring diameters (width and height, fractions of the short side) are 0.070, 0.140, 0.220, 0.310, 0.410 and 0.520 from the inside out.
  The width is one of these times 0.96, 1.00 or 1.04, the height one of these times 0.93, 0.97 or 1.01.

Changed from 1.0.0: the rings are wavering ellipses instead of true circles (`circle`), and the outer rings fluctuate broadly. The ring sizes stay about twice the 1.0.0 radii.

## `Water.Rings` (alias `Water.水輪`)

<img src="water-rings.svg" width="360" alt="On a blue ground, low in the frame, five thin gray wide ellipses overlap. Each outer ring's center sits a little lower so the rings open toward the viewer, and the lines undulate. The outermost is dashed">

The Japanese export's `ddl` drawn as it is ([water-rings.svg](water-rings.svg)).

A ripple seen at a low angle across the water: wide ellipses stacked from the inside out, each outer ring's center a little lower so the rings seem to open toward the viewer.

- With no count written it draws 3–5 rings.
- The base ring widths are 0.100, 0.200, 0.310, 0.430, 0.560 and 0.700 from the inside out, and the heights 0.030, 0.060, 0.094, 0.132, 0.172 and 0.216 (fractions of the short side).
  The width is one of these times 0.97, 1.00 or 1.03, the height one of these times 0.92, 1.00 or 1.08.
- The rings are first centered at x 0.500, inner ones higher and outer ones lower (y = 0.500, 0.504, 0.509, 0.515, 0.522, 0.530),
  and a `transform` then moves the whole by one of five offsets, chosen by the work's composition seed. In terms of the innermost ring's center after the move:

  | Candidate | Offset (x, y) | Innermost center |
  |---|---|---|
  | 1 | (0.000, 0.200) | (0.500, 0.700) |
  | 2 | (−0.100, 0.160) | (0.400, 0.660) |
  | 3 | (0.100, 0.240) | (0.600, 0.740) |
  | 4 | (−0.050, 0.300) | (0.450, 0.800) |
  | 5 | (0.060, 0.120) | (0.560, 0.620) |

- The same `transform` tilts the whole by −3, −1.5, 0, 1.5 or 3 degrees.

## Reading it in

- Web: open "New instructions" under the Describe tab and choose the file with "Load".
- CLI: `uv run inku-cli paint --input-mode ddl --file docs/plugins/water-ripples.en.ddl.json`
- To use it in every new work on a Server, put `definition` in `pipeline.definitions` and `summary`, in the same order, in `pipeline.macro_summaries` (PLUGIN §5.2).

Each export file carries one word. To use both words in one work, list the `plugins` of both files in one export file.

## What was checked (2026-10-26)

Both definitions passed `compile-score` (PLUGIN §7.1).

| Word | Version | Digest |
|---|---|---|
| `Water.Ripples` | 2.0.0 | `sha256:4ada27fcbbf76c922fc80ea48f495b939f7f099204779cbddf5c533d86f7d6b2` |
| `Water.Rings` | 1.0.0 | `sha256:51cfa953710f1a0b4d00eeffec2b8e94b41bd097d979f5acebda207270b5b4e5` |

With those locks and no count written, composition seeds 1–12 gave three or four rings for `Water.Ripples.` and three to five for `Water.Rings.`.
Writing `1` or `6` drew that many; writing `7` dropped the word with `macro_binding_count_out_of_range`.

Passing the `plugins` of the four export files to the Server's `/api/compose` as `imported_plugins`, with the shared core:
each file's `ddl` drew five ellipses, and under both the Japanese alias and the English name, no count drew three for `Ripples` and four for `Rings`,
`1` one, and `6` six, all without diagnostics. `Rings` arrived in `transform_groups` as one group carrying the chosen offset and tilt.
Listing the `plugins` of both files with the DDL `背景を黒で埋める。`, `3個のWater.波紋。`, `4個のWater.水輪。` and `中心に白い小さな円を置く。` also drew without diagnostics.
`7` is outside the range, so that word was left out, and with nothing else to draw no work was made (`score_not_ready`).
