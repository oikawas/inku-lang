<p align="center">
  <a href="README.ja.md">日本語</a> ｜ <strong>English</strong>
</p>

# Example plugins

Vocabulary plugins written to the specification in [PLUGIN.md](../../PLUGIN.md), kept as DDL export files (`inku.ddl-export.v1`).
None of them is bundled with the product. Reading one in makes its definitions available to that new work only ([PLUGIN §5.1](../../PLUGIN.md#51-a-ddl-export-file-immediately-usable-by-an-author)).

| File | Word |
|---|---|
| [water-ripples.en.ddl.json](water-ripples.en.ddl.json) / [water-ripples.ja.ddl.json](water-ripples.ja.ddl.json) | `Water.Ripples` (alias `Water.波紋`) |

## `Water.Ripples` (alias `Water.波紋`)

Spreads one ripple on the water: outline-only circles in thin gray brush, stacked concentrically from the inside out around one point.

<img src="water-ripples.svg" width="360" alt="On a blue ground, toward the lower left, five thin gray concentric circles spread out. The outer rings are thinner, and the outermost is dashed">

The Japanese export's `ddl` drawn as it is ([water-ripples.svg](water-ripples.svg)).

- It receives the ring count (`5 Water.Ripples.`, `5個のWater.波紋。`). The range is 1–6; with no count written it draws 3–4. A count outside the range drops that word only.
- The center is one of five positions around and slightly below the middle of the canvas, chosen by the work's composition seed. Every ring shares it.

  | Candidate | x | y |
  |---|---|---|
  | 1 | 0.500 | 0.560 |
  | 2 | 0.380 | 0.620 |
  | 3 | 0.620 | 0.580 |
  | 4 | 0.440 | 0.680 |
  | 5 | 0.580 | 0.460 |

- Ring radii, from the inside out, are 0.035, 0.070, 0.110, 0.155, 0.205 and 0.260 (fractions of the short side), so the gaps widen outward.
- The inner three rings are `fine`, the outer three `extra_fine`. The fifth is dashed and the sixth dotted, breaking up outward.
- The ring lines undulate narrowly (`narrowly`, `undulating`).
- The color is fixed to gray. Every declared parameter is required (PLUGIN §3.4), so a color parameter would stop the bare name from drawing.

The export's `ddl` is `Fill the background with blue.` and `5 Water.Ripples.` in the English file, and the same in Japanese in the Japanese file.

### Reading it in

- Web: open "New instructions" under the Describe tab and choose the file with "Load".
- CLI: `uv run inku-cli paint --input-mode ddl --file docs/plugins/water-ripples.en.ddl.json`
- To use it in every new work on a Server, put `definition` in `pipeline.definitions` and `summary`, in the same order, in `pipeline.macro_summaries` (PLUGIN §5.2).

### What was checked (2026-10-26)

The definition passed `compile-score` (PLUGIN §7.1) as `Water.Ripples 1.0.0`, digest
`sha256:c33709784dddedb8ed7a8342794cab9c78315fe1a74a75007981d53dfa2e1b6c`. With that lock, a call with no count drew three or four rings depending on the seed.

Passing the `plugins` of both export files to the Server's `/api/compose` as `imported_plugins`, with the shared core:
`5 Water.Ripples.` and `5個のWater.波紋。` drew five concentric circles, `Water.Ripples.` and `Water.波紋。` three from the
omitted-count choices, and `6 Water.Ripples.` and `6個のWater.波紋。` six, all without diagnostics; with six, the fifth was dashed
and the sixth dotted. The center moved among the candidates from work to work. `背景を黒で埋める。`, `3個のWater.波紋。` and
`中心に白い小さな円を置く。` together also drew without diagnostics. `7個のWater.波紋。` is outside the range, so that word was left out,
and with nothing else to draw no work was made (`score_not_ready`).
