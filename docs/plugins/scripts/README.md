<p align="center">
  <a href="README.ja.md">日本語</a> ｜ <strong>English</strong>
</p>

# Scripts that make the example words

Python scripts that make the definitions (`inku.macro-definition.v2`) of the nine words in the [water and sky examples](../README.md).
A definition has no arithmetic, so these scripts compute the tables of positions, sizes and angles and write them out. They need only the standard library of Python 3.10 or later.

| File | Content |
|---|---|
| [helpers.py](helpers.py) | Small functions that make expressions (`semantic_ref`, `exact_decimal`, `cycle` and so on), and the circle of a tilted arc |
| [water_stream_ripples_rings.py](water_stream_ripples_rings.py) | `{stream}` (Stream 1.0.0), `{ripples}` (Ripples 3.0.0), `{rings}` (Rings 2.0.0) |
| [river_sea_sky.py](river_sea_sky.py) | `{river}` (River), `{sea}` (Sea), `{clouds}` (Clouds), `{heavens}` (Heavens), `{rain}` (Rain 2.0.0), `{snow}` (Snow) |
| [build_v2.py](build_v2.py) | Turns the two scripts' words into v2 definitions (`id`, `names`, `kind: scene`) and checks them against, or writes them into, the example files |

## Use

Run it in this folder.

```sh
python3 build_v2.py            # compare with the example files' definitions; "all definitions match" when all are the same
python3 build_v2.py --write    # write the definitions into the example files
python3 build_v2.py --dump out.json
```

`--write` replaces only each word's `definition` in `../water-nihonga/package.json`, `../sky-nihonga/package.json` and the `../*.ddl.json` files that carry the word.
Notes, examples, pictures and the order of the keys are kept. On 2026-10-30 all nine words were confirmed to match the repository's files.

## Changing a word

1. Change the tables or values in the word's script and raise the definition's `version` (such as `definition(..., version="2.1.0")`).
2. Write it with `python3 build_v2.py --write` and raise the `version` in `package.json` too. To change a note or an example, edit `package.json` directly.
3. Rebuild the zip (the same steps as the [examples README](../README.md)).

   ```sh
   cd ../sky-nihonga   # water is ../water-nihonga
   TZ=UTC touch -t 202610260000 package.json previews previews/*.png
   rm -f ../sky-nihonga.zip && zip -X -r ../sky-nihonga.zip package.json previews
   ```

4. Check it with "Add a plugin" under "Plugins" in the Web settings ("Cancel" ends without adding it).
   For the definitions alone, pass them to `scripts/rust-toolchain.sh run -q -p inku-ddl --example compile-score --locked --offline` at the top of the repository ([PLUGIN §7](../../../PLUGIN.md)).

The Saijiki pictures (`previews/*.png`) are not made by these scripts. Each word's example was drawn by the Server and cut to the frame (twice 216×92).

## Rules learned while making them

- **Stay inside the canvas.** If a figure leaves the canvas after a `transform`, nothing in that group is drawn (`numeric_transform_group_position_conflict`).
  A long arc is made at the canvas center and then turned and moved by a `transform`; placed as it is, it leaves the canvas before turning and is dropped (`geometry_extent_out_of_bounds`).
- **Mind the rounding.** A semicircle's sagitta is half its chord, and if rounding pushes it past half it cannot be drawn (`geometry_dimension_mismatch`). Use values that divide cleanly, such as multiples of 0.002.
- **No branches.** A `repeat` count cannot be 0, and no statement can be chosen by a condition. Write per-ring or per-line differences as `cycle` tables.
- **Positions by `cycle`.** Choosing x and y with separate `vary` statements mixes the tables. Choose a candidate as an integer with `vary`, then look up both the x and the y `cycle` tables with it.
- **`scatter` is one instruction.** With `movement: scatter` and `count`, one instruction scatters many marks (rain, snow). A `transform` can tilt them.
