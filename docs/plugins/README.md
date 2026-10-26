<p align="center">
  <a href="README.ja.md">日本語</a> ｜ <strong>English</strong>
</p>

# Example plugins

Vocabulary plugins written to the specification in [PLUGIN.md](../../PLUGIN.md), kept as DDL export files (`inku.ddl-export.v1`).
None of them is bundled with the product. Reading one in makes its definitions available to that new work only ([PLUGIN §5.1](../../PLUGIN.md#51-a-ddl-export-file-immediately-usable-by-an-author)).

| File | Word | Version |
|---|---|---|
| [water.en.ddl.json](water.en.ddl.json) / [water.ja.ddl.json](water.ja.ddl.json) | The three below together | — |
| [water-stream.en.ddl.json](water-stream.en.ddl.json) / [water-stream.ja.ddl.json](water-stream.ja.ddl.json) | `Water.Stream` (alias `Water.水流`) | 1.0.0 |
| [water-ripples.en.ddl.json](water-ripples.en.ddl.json) / [water-ripples.ja.ddl.json](water-ripples.ja.ddl.json) | `Water.Ripples` (alias `Water.波紋`) | 3.0.0 |
| [water-rings.en.ddl.json](water-rings.en.ddl.json) / [water-rings.ja.ddl.json](water-rings.ja.ddl.json) | `Water.Rings` (alias `Water.水輪`) | 2.0.0 |

<img src="water.svg" width="420" alt="A washi ground. Across the upper half a bundle of ultramarine and pale-ink lines flows in an S, with a small eddy inside each of its two bends. A ripple of broken rings lies over the stream, and below are flattened water rings with short horizontal strokes to either side">

The `ddl` of `water.ja.ddl.json` drawn with composition seed 7 ([water.svg](water.svg)).

## The idea

Water is drawn not as clearly outlined figures but as a rhythm of lines and the gaps (ma) between them. The following ways modern Japanese painting (nihonga)
draws water were the reference, built within inku's nine shapes and the saijiki words.

- **Rinpa flowing water** (the stream in Ogata Kōrin's *Red and White Plum Blossoms* and the modern nihonga that carried it on): the flow becomes a bundle of lines running side by side and a pattern of eddies curling in its bends. → the band and eddies of `Stream`
- **The flowing lines of Yokoyama Taikan's *Metempsychosis* (Seisei ruten)**: lines with thick and thin passages flow, drawing together and apart. → the `Stream` band swells in the middle of each half and narrows at both ends and at the center
- **Tarashikomi** (the Rinpa technique of dropping a second color into wet ink or paint so it bleeds): the saijiki word `bleeding` makes the core line of `Stream` and the drops of `Ripples` and `Rings` bleed
- **Fukuda Heihachirō's *Ripples* (Sazanami)**: the water surface becomes a rhythm of broken lines. → the rings of `Ripples` and `Rings` break more toward the outside, the breaks turning from ring to ring
- **Higashiyama Kaii's still water**: light reflected on the surface laid down as pale horizontal lines. → the reflection strokes of `Rings`

The only colors are `blue`, standing for ultramarine, and `gray`, standing for pale ink: ultramarine for the inner rings and the core, pale ink for the outer rings and the side lines.
The lines are based on the thin brush (`brush_thin`), with only the key lines in the thick brush (`brush_thick`) for modulation. The export files' `ddl` sets the ground to `Washi.`
The ultramarine lines sink into a blue ground, so a light ground such as white, washi or pale ink wash suits them.

## What the three words share

- They receive a count (`5 Water.Ripples.`, `8 Water.Stream.`). A count outside the range drops that word only.
- Position and direction are chosen by the work's composition seed. The same seed gives the same picture.
- The fluctuation sways (`swaying`) loosely (`loosely`): narrowly (`narrowly`) for the inner and core lines, broadly (`broadly`) for the outer rings.
- A definition has no arithmetic, so each word is built around the canvas center (0.5, 0.5) and a `transform` then moves, turns and flattens the whole.
  If a figure leaves the canvas after the `transform`, nothing in that group is drawn (`numeric_transform_group_position_conflict`),
  so the sizes keep every candidate inside the canvas.

## `Water.Stream` (alias `Water.水流`)

<img src="water-stream.svg" width="360" alt="A washi ground. Across the middle of the canvas a bundle of ultramarine and pale-ink lines flows up to the right as an S-shaped band. A bleeding thick ultramarine line runs through its core, and a small eddy sits inside each of its two bends">

One stream of water crossing the middle of the canvas ([water-stream.svg](water-stream.svg) draws the Japanese `ddl`).

- It receives the line count. The range is 1–12; with no count written it draws 7–9. The core line and the two eddies are always drawn, apart from the count.
- Each line is an S: an arc bulging upward in the left half joined to an arc bulging downward in the right half (each chord 0.40).
  The line ends are 0.016 apart, and the upper lines bulge more in the left half, the lower lines more in the right half (sagitta 0.090, changing by 0.006 per line).
- The lines take their tool and color from a table that mixes thin and thick brush, ultramarine and pale ink. The core line is thick-brush ultramarine with `bleeding`.
- An eddy is a spiral of five joined semicircles, each half turn 0.010 smaller in radius, written as a component (`eddy` in `components`) and called twice.
- The band lies in one of six ways.

  | Candidate | Tilt | Left-right | Vertical shift |
  |---|---|---|---|
  | 1 | −12° | as is | 0.000 |
  | 2 | 10° | as is | 0.040 |
  | 3 | −6° | mirrored | −0.040 |
  | 4 | 14° | mirrored | 0.020 |
  | 5 | −16° | as is | 0.050 |
  | 6 | 4° | mirrored | −0.050 |

## `Water.Ripples` (alias `Water.波紋`)

<img src="water-ripples.svg" width="360" alt="Left of center on a washi ground, five rings spread around a bleeding ultramarine drop. The inner rings are ultramarine and closed; the outer ones are pale ink and broken, the breaks shifting from ring to ring so the whole seems to swirl">

A ripple on the water seen from straight above ([water-ripples.svg](water-ripples.svg) draws the Japanese `ddl`).

- It receives the ring count. The range is 1–6; with no count written it draws 4–5.
- An ultramarine drop with `bleeding` (a point of radius 0.007) sits at the center.
- Each ring is an upper and a lower arc. The radii are 0.035, 0.070, 0.110, 0.155, 0.205 and 0.260 from the inside out (fractions of the short side).
  The arcs open 180, 180, 150, 135, 120 and 100 degrees from the inside out, so the inner two are closed and the rest break.
  The rings are turned 0, 30, −8, 14, −22 and 34 degrees to shift the breaks.
- The inner three are ultramarine and the outer three pale ink. Only the second ring is in thick brush.
- The center is one of the five below, and the whole is turned by 0, 40, 80, 120 or 160 degrees.

  | Candidate | x | y |
  |---|---|---|
  | 1 | 0.500 | 0.560 |
  | 2 | 0.380 | 0.620 |
  | 3 | 0.620 | 0.580 |
  | 4 | 0.440 | 0.680 |
  | 5 | 0.580 | 0.460 |

Changed from 2.0.0: the rings are broken upper and lower arcs instead of closed ellipses. A drop was added, and ultramarine and pale ink, thick and thin brush are used by ring.
With no count written it now draws 4–5 rings instead of 3–4.

## `Water.Rings` (alias `Water.水輪`)

<img src="water-rings.svg" width="360" alt="Low on a washi ground, five flattened rings overlap around a bleeding drop. The inner rings are ultramarine and the outer ones pale ink and broken. Five short pale-ink horizontal strokes lie to the sides and below">

A ripple on the water seen at a low angle across it ([water-rings.svg](water-rings.svg) draws the Japanese `ddl`).

- It receives the ring count. The range is 1–6; with no count written it draws 4–5.
- The same drop and broken rings as `Ripples` (radii 0.050, 0.095, 0.145, 0.200, 0.260 and 0.320 from the inside out, all thin brush)
  are scaled by a `transform` to 1.05 times the width and 0.34 times the height. Each outer ring's center is lower (0, 0.006, 0.014, 0.024, 0.036, 0.050), so the rings open toward the viewer.
- Five thin pale-ink horizontal strokes lie to the sides of and below the rings (reflections on the water).
- The whole is moved by one of the five offsets below and tilted by −3, −1.5, 0, 1.5 or 3 degrees. The center after the move is listed as well.

  | Candidate | Offset (x, y) | Center |
  |---|---|---|
  | 1 | (0.000, 0.200) | (0.500, 0.700) |
  | 2 | (−0.070, 0.160) | (0.430, 0.660) |
  | 3 | (0.070, 0.240) | (0.570, 0.740) |
  | 4 | (−0.040, 0.260) | (0.460, 0.760) |
  | 5 | (0.050, 0.120) | (0.550, 0.620) |

Changed from 1.0.0: the same broken rings and drop as `Ripples`, with reflection strokes added. With no count written it now draws 4–5 rings instead of 3–5.

## Reading it in

- Web: open "New instructions" under the Describe tab and choose the file with "Load".
- CLI: `uv run inku-cli paint --input-mode ddl --file docs/plugins/water.en.ddl.json`
- Android: choose the file with "Open" on the DDL screen.
- To use it in every new work on a Server, put `definition` in `pipeline.definitions` and `summary`, in the same order, in `pipeline.macro_summaries` (PLUGIN §5.2).

To use the three words in one work, read in `water.*.ddl.json`.

## Limits

A work holds at most 64 figure instructions (PLUGIN §8). With n rings or lines, each word draws the following number of figures.

| Word | Figures | No count written | Maximum |
|---|---|---|---|
| `Stream` | 12 + 2n | 26–30 | 36 |
| `Ripples` | 1 + 2n | 9–11 | 13 |
| `Rings` | 6 + 2n | 14–16 | 18 |

The three together with no counts written come to 49–57 and fit. With all three at their maximum they come to 67, and the word over the limit is dropped (`Rings`, when checked on 2026-10-26).
The expansion nodes of all three together stay within the work-wide limit of 128.

## What was checked (2026-10-26)

All three definitions passed `compile-score` (PLUGIN §7.1).

| Word | Version | Digest |
|---|---|---|
| `Water.Stream` | 1.0.0 | `sha256:d9b813cb7f9303095728c8c2b8534895a62ab92a5ef0430d86593a52bda7d3c2` |
| `Water.Ripples` | 3.0.0 | `sha256:7881b2c4390a65a1c13e7d45760c863cc8842bc6bf5a0fe0ed90baf4131f030c` |
| `Water.Rings` | 2.0.0 | `sha256:470723a10ffa90984da40a2fd64c49688985d3d4ed0ca684d736d94398f124b7` |

Passing the export files' `plugins` to the Server's `/api/compose` as `imported_plugins`, with the shared core:

- The `ddl` of all eight files drew without diagnostics, in Japanese and English.
- Under both the Japanese alias and the English name, no count, 1 and the maximum count drew that many without diagnostics.
  One more than the maximum dropped that word only with `macro_binding_count_out_of_range`, and the rest of the same DDL was drawn.
- Changing the composition seed, `6個のWater.水輪。` was drawn 40 ways, `12本のWater.水流。`, `Water.水流。` and `6個のWater.波紋。` 24 ways each,
  and the DDL with all three 8 ways; none left the canvas and none had diagnostics.
