# inku Vocabulary Plugin Authoring Guide

In inku, a plugin is a data-only vocabulary macro. Writing a name such as `Sky.Stars` in DDL invokes the
`inku.macro-definition.v1` definition of that name, which expands into ordinary instructions (circles, lines,
arcs, and so on) and is drawn. A plugin is not executable code, a syntax extension, or a renderer hook.

This guide is written so that a person or an AI can read it and make a new plugin that the current
specification loads. Sections 1–9 explain how; Appendix A holds implementation detail. The normative plugin
boundary is [SPEC §4](SPEC.md#4-plugin-model). Canvas selection (`inku.canvas-format-registry.v1`) and Render
Engine Packs are separate mechanisms, not plugins.

## 1. Steps

1. Write the definition as JSON (the example in §2, the format in §3).
2. Put the definition, with a summary (§6), a note, and an example, in a plugin file (`inku.plugin-package.v1`, §5.1).
   For your own Saijiki picture, zip that file with the PNG (without one, the picture is drawn from the example).
3. A Server administrator chooses the file under "Add a plugin" in the Web settings "Plugins" (§5.1). The Server
   checks it at once and lists, word by word, where in the file something is wrong and why (§7). A word that
   passed shows the picture and example the Saijiki will show; check them and press "Add".
4. Write its name in DDL (§4). An added word can be drawn in every new work on that Server, appears in the
   Saijiki, and is chosen by the underdrawing (Stage 1) from its summary when drawing from a description.

To try a definition in your own works without installing it on a Server, load it in a DDL export file (§5.2).

## 2. Example: `Sky.Stars` (alias `Sky.星`)

This word scatters yellow stars over the upper half of the sky. It takes a written count (1–9) and draws
3–5 when none is written. Star positions come from a table in order; each star's size is very small or small.

```json
{
  "schema": "inku.macro-definition.v1",
  "namespace": "Sky",
  "heading": "Stars",
  "aliases": ["星"],
  "version": "1.0.0",
  "parameters": {
    "star_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 9, "omitted": [3, 4, 5], "counter": "general"}
  },
  "components": {},
  "body": [
    {
      "op": "repeat",
      "count": {"expr": "parameter", "name": "star_count"},
      "maximum": 9,
      "index": "star_index",
      "body": [
        {
          "op": "vary",
          "binding": "star_size",
          "domain": "sky_stars_size",
          "choices": [
            {"expr": "semantic_ref", "category": "relative_scale", "id": "very_small"},
            {"expr": "semantic_ref", "category": "relative_scale", "id": "small"}
          ],
          "body": [
            {
              "op": "emit",
              "binding": null,
              "fields": {
                "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                "position_x": {"expr": "cycle", "index": {"expr": "local", "name": "star_index"}, "items": [
                  {"expr": "exact_decimal", "value": "0.170"}, {"expr": "exact_decimal", "value": "0.830"},
                  {"expr": "exact_decimal", "value": "0.500"}, {"expr": "exact_decimal", "value": "0.330"},
                  {"expr": "exact_decimal", "value": "0.670"}, {"expr": "exact_decimal", "value": "0.170"},
                  {"expr": "exact_decimal", "value": "0.830"}, {"expr": "exact_decimal", "value": "0.500"},
                  {"expr": "exact_decimal", "value": "0.330"}
                ]},
                "position_y": {"expr": "cycle", "index": {"expr": "local", "name": "star_index"}, "items": [
                  {"expr": "exact_decimal", "value": "0.100"}, {"expr": "exact_decimal", "value": "0.140"},
                  {"expr": "exact_decimal", "value": "0.280"}, {"expr": "exact_decimal", "value": "0.180"},
                  {"expr": "exact_decimal", "value": "0.080"}, {"expr": "exact_decimal", "value": "0.380"},
                  {"expr": "exact_decimal", "value": "0.340"}, {"expr": "exact_decimal", "value": "0.120"},
                  {"expr": "exact_decimal", "value": "0.420"}
                ]},
                "relative_scale": {"expr": "local", "name": "star_size"},
                "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
                "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
                "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
              }
            }
          ]
        }
      ]
    }
  ]
}
```

How to read it:

- `star_count` receives the count written on the word (§3.4). `repeat` repeats its body that many times and
  puts a number counting from 0 in `star_index`.
- `cycle` takes one item from a table by that number. The nine positions are ordered so that any count stays
  spread over the upper half.
- `vary` chooses one of its choices from a fixed seed. Being inside `repeat`, it chooses again for each star.
- `emit` becomes one shape instruction: here a pencil-yellow filled circle at a numeric position.

The same definition in an export file (§5.2) looks like this. `ddl` is the text placed in the DDL editor
when the file is loaded.

```json
{
  "schema": "inku.ddl-export.v1",
  "language": "en",
  "ddl": "Fill the background with black.\n5 Sky.Stars.",
  "plugins": [
    {
      "definition": { "…": "the definition above, unchanged" },
      "summary": "Scatter yellow stars over the upper half of the sky: the written count (1–9), or 3–5 when none is written. Each star is a small pencil-yellow filled circle, very small or small per star."
    }
  ],
  "exported_from": {}
}
```

Checked on 2026-10-26 by passing this definition as an export file to the Server's `/api/compose` with the
shared core: `5 Sky.Stars.` and `5個のSky.星。` drew five circles, `Sky.Stars.` drew 3–5 from the omitted-count
choices, and `9個のSky.星。` drew nine, all without diagnostics. `12個のSky.星。` is outside the range, so that
word was left out.

More examples, three words that draw water, `Water.Stream` (alias `Water.水流`), `Water.Ripples` (alias `Water.波紋`)
and `Water.Rings` (alias `Water.水輪`), are kept in [docs/plugins](docs/plugins/README.md) as export files that can be loaded
as they are. They also show a component (`use`), a `transform` that moves, turns and flattens the whole in place of
arithmetic, and `cycle` tables that change the form and tool per ring or line.

## 3. Definition Format

### 3.1 Top-level fields

A definition has only these fields. An unknown field rejects the whole definition.

| Field | Required | Content |
|---|---|---|
| `schema` | yes | exactly `inku.macro-definition.v1` |
| `namespace` | yes | starts with a letter; ASCII letters, digits, `_`, and `-` only (for example `Sky`) |
| `heading` | yes | not empty, no leading or trailing space, no control characters. Make the canonical name English (for example `Stars`) |
| `aliases` | no | other headings in the same namespace that invoke the same definition (for example `["星"]`). Letters, digits, `_`, and `-` only; may not repeat the heading or another alias. Omit when empty |
| `version` | yes | a semantic version such as `1.0.0` |
| `parameters` | yes | what the call passes in (§3.4); `{}` when none |
| `components` | yes | parts used only inside this definition (`use` in §3.6); `{}` when none |
| `body` | yes | the statements that draw (§3.6) |

DDL writes the name as `namespace.heading` (`Sky.Stars`) or `namespace.alias` (`Sky.星`). One name belongs to
one definition: a definition claiming a canonical name or alias that a definition already loaded holds is not
accepted (except that definitions from an export file in §5.2 take precedence for that work). Adding from the
Web, the check refuses a word whose name another plugin already holds (§5.1). The namespace
convention is in [SPEC §4.10](SPEC.md#410-namespace-convention); canonical names and aliases are in
[SPEC §4.13](SPEC.md#413-canonical-names-and-aliases).

Raise `version` when you change the content. A saved work keeps the exact definitions and digests it used, so
changing a definition later does not change how it redraws.

### 3.2 Identifiers

Parameter names, component names, `emit` `binding`, `anchor` `name`, `repeat` `index`, and `vary` `binding` and
`domain` start with an ASCII letter and use ASCII letters, digits, `_`, and `-` only. Within one definition,
`binding` and `anchor` names do not repeat, and neither do `repeat` and `vary` names.

### 3.3 Expressions

Every value is JSON naming its kind with `expr`.

| `expr` | Other fields | Meaning |
|---|---|---|
| `semantic_ref` | `category`, `id` | a meaning word (§3.8), for example `{"expr":"semantic_ref","category":"color","id":"red"}` |
| `exact_decimal` | `value` (string) | an exact decimal; write positions and dimensions with it, for example `{"expr":"exact_decimal","value":"0.25"}` |
| `integer` | `value` | an integer |
| `number` | `value` | a floating-point number, for `transform` amounts and the like |
| `boolean` | `value` | true or false |
| `list` | `items` | a fixed-length list |
| `cycle` | `items`, `index` | the item at `index` (a non-negative integer), wrapping back to the start; all items have the same kind |
| `parameter` | `name` | a declared parameter's value |
| `local` | `name` | the value of a `repeat` `index` or a `vary` `binding` |

There is no arithmetic. To combine numbers, write the values out as a `cycle` table or `vary` choices.

### 3.4 Parameters

`parameters` maps names to types. The types are closed:

| `type` | Other fields | What the call binds to it |
|---|---|---|
| `semantic_ref` | `category`, optional `dimension` | a word of that category written on the call; a color parameter takes "red" in `red Sky.ColorStars.` |
| `exact_decimal` | optional `dimension` | a number written on the call. `dimension` is `radius`, `diameter`, `length`, `side`, `width`, `height`, `chord`, `sagitta`, `position_x`, or `position_y` |
| `integer` | — | a number written on the call |
| `integer` (count) | `receives: "count"`, `minimum`, `maximum`, `omitted`, optional `counter` | the count written on the word (below) |
| `number` | — | a number written on the call |
| `boolean` | — | — |
| `list` | `length`, `items` | — |

- Every declared parameter except the count parameter is required. A call that does not write it is not drawn;
  no default is filled in silently.
- With two parameters of the same category, names never decide which one a word binds to. Declare one per category.
- A word written on the call that no parameter declares is left out alone with a diagnostic (for example
  "Place" in `Place 5 Sky.Stars.`). It never overrides values inside the definition.
- A sway parameter can name its part with `dimension` (`amplitude`, `frequency`, or `quality`), as in
  `{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`.

**A parameter that receives the word's count.** A count written on a word (`5 Sky.Stars.`, `5個のSky.星。`)
repeats the whole word from outside unless the definition declares that it receives it. To take it as the
inner count, declare an integer parameter with `receives: "count"` and its bounds, and read that parameter as
the `count` of a body `repeat`.

```json
"star_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 9, "omitted": [3, 4, 5], "counter": "general"}
```

- Only one top-level parameter may declare it, never a component parameter.
- `minimum` is at least 1 and at most `maximum`; `omitted` is not empty and lists distinct integers inside the bounds.
- Make the `repeat` `maximum` at least the parameter's `maximum`.
- When no count is written, one of the `omitted` choices is chosen deterministically from the call's seed.
- A count outside the bounds leaves out only that word with the `macro_binding_count_out_of_range`
  diagnostic and draws the rest. It is never clamped.
- `counter` (`flat` for 枚, `long` for 本, `general` for 個) decides only the counter the underdrawing writes
  with a count in Japanese DDL.

### 3.5 Positions and sizes

- Position numbers are fractions of the canvas: `(0.0, 0.0)` is top-left, `(1.0, 1.0)` bottom-right, `(0.5, 0.5)`
  the center. On a non-square canvas, x is a fraction of the width and y of the height.
- Dimensions are fractions too: circle, ellipse, and point sizes are fractions of the short edge (`radius` 0.24
  is a 120px radius when the short edge is 500px), so a circle stays round on any canvas. A center plus a radius
  beyond 1 runs off the canvas.
- Give a size either with a dimension such as `radius` or with `relative_scale`, not both.
- A shape without a size takes the same normal size as ordinary DDL. Writing `relative_scale` `normal`
  explicitly is not the same as writing nothing.
- The shapes are `line`, `circle`, `ellipse`, `triangle`, `square`, `polygon`, `arc`, `point`, and `cloudform`.
  A plugin cannot add a tenth.

### 3.6 Body statements

A statement names its kind with `op`.

| `op` | Fields | Meaning |
|---|---|---|
| `emit` | `binding` (a name or `null`), `fields` | one shape instruction; `fields` are in §3.7. Name a `binding` to point at it from a `relation` |
| `repeat` | `count`, `maximum`, `index`, `body` | repeats `body` `count` times (an integer expression). `maximum` is an upper bound of at least 1 that `count` may not exceed. `index` holds a number from 0 |
| `vary` | `binding`, `domain`, `choices` or `range`, `body` | chooses one value from the seed into `binding` for use in `body`. `choices` is a list of same-kind expressions; `range` is `{"start","end","step"}`. `domain` names the choice so it is kept apart from other `vary` statements |
| `use` | `component`, `arguments` | calls a component from the same definition's `components`, passing all of its parameters |
| `group` | `body` | groups statements; adds no placement |
| `transform` | `transform`, `body` | moves the shapes of `body` together. `transform` has at least one of `translate_x`, `translate_y`, `scale_x`, `scale_y`, `rotate_degrees` (numbers). Scaling and rotation happen at the group's bounding-box center; translation is in canvas fractions |
| `anchor` | `name`, optional `fields` | a non-drawing point; `fields` is either `place` or the pair `position_x` and `position_y` |
| `relation` | `kind`, `from`, `to` | a relation between two `emit` bindings or anchors; `kind` is a relation word from §3.8 |

- **`vary` chooses again every time it is reached.** Inside `repeat` it chooses for each repetition, and separate
  `vary` statements for x and y choose separately. Choosing between two position tables with separate x and y
  `vary` statements mixes the tables and can make shapes overlap. Fix positions with a `cycle` table, and use
  `vary` for things that may mix, such as size or color.
- The seed comes from the work's composition seed. The same seed draws the same picture; another seed chooses differently.
- A component cannot call itself, even indirectly, or a component of another definition.
- A `relation` works between adjacent `emit` statements of the same expansion. `connected`, `touching`,
  `not_touching`, `between`, `along`, and `cutting` are available. A relation that cannot hold is removed alone
  with a diagnostic and the shapes are still drawn. Two arcs joined with `touching`, the later one with
  `surface: solid`, fill their inside as one closed outline (the leaf form; [SPEC §4.11](SPEC.md#411-the-boundary-of-freedom)).

### 3.7 `emit` fields

An `emit` may have these fields and no others.

| Field | Value | Notes |
|---|---|---|
| `shape` | a `shape` word | required; one of the nine shapes in §3.5 |
| `movement` | a `movement` word | required. `place` reaches the drawing today; `line_up`, `scatter`, and `tile` are covered in Appendix A |
| `place` | a `place` word | either this or the `position_x` / `position_y` pair: `center`, `top`, `bottom`, `left_edge`, `right_edge`, `top_edge`, `bottom_edge`, `corner` |
| `position_x`, `position_y` | `exact_decimal` | written as a pair; fractions of the canvas |
| `radius`, `diameter`, `length`, `side`, `width`, `height`, `chord`, `sagitta` | `exact_decimal` | dimensions. `width` with `height` and `chord` with `sagitta` are pairs. A line takes `length`, an arc `chord` and `sagitta`, a point `radius` or `diameter` |
| `relative_scale` | a `relative_scale` word | a factor on the normal size |
| `color` | a `color` word | color |
| `touch` | a `touch` word | drawing medium |
| `continuity` | a `continuity` word | stroke continuity (solid, dashed, …) |
| `surface` | a `surface` word | fill: `none` for an outline only, `solid` for a full fill, or a texture word |
| `surface_intensity` | a `handling` word | texture strength |
| `angle` | an `angle` word | tilt; a point takes none |
| `thinness` | a `thinness` word | stroke thinness; on a closed shape it thins the outline |
| `fluctuation_amplitude`, `fluctuation_frequency`, `fluctuation_quality`, `ink_spread` | a `variation` word | sway amplitude, frequency, and quality, and bleeding. With amplitude alone, frequency is medium and quality the default |
| `proportion_aspect` | `ratio` `tall` or `wide` | tall or wide |
| `proportion_width_extent`, `proportion_arc_form` | a `ratio` word | full or half width; semicircle, waxing, waning, crescent |
| `shape_form` | `shape_form` `regular` | regular form |
| `sides` | an integer from 5 to 8 | polygon sides |
| `count`, `layout_direction` | integer, an `angle` word | covered in Appendix A; write counts with `repeat` |

A value whose category does not match the field is rejected (for example a `touch` word in `color`). A field
left out takes the same default as ordinary DDL.

### 3.8 Finding meaning words (semantic_ref)

A `semantic_ref` `id` is the English identifier of a word in the Saijiki
(`core/crates/inku-ddl/assets/saijiki-v2.json`): the word's `score_value` when present, otherwise its
`surface_en` with `-` and spaces turned into `_`. The table changes with the product, so print today's list
instead of copying one:

```sh
python3 - <<'PY'
import json
names = {"katachi": "shape", "katamuki": "angle", "tezawari": "touch", "tsuranari": "continuity",
         "omote": "surface", "sabaki": "handling", "kime": "fineness", "shitaji": "underlayer",
         "ji": "ground", "iro": "color", "yuragi": "variation", "basho": "place",
         "ugoki": "movement", "jun": "sequence", "wariai": "ratio"}
asset = json.load(open("core/crates/inku-ddl/assets/saijiki-v2.json"))
for category in asset["categories"]:
    ids = []
    for word in category["words"]:
        wire = word.get("score_value") or (word.get("surface_en") or "").replace("-", "_").replace(" ", "_")
        if wire:
            ids.append(f"{wire}（{word['surface_ja']}）")
    print(names[category["key"]] + ": " + ", ".join(ids))
print("relation: " + ", ".join(r["relation_type"] for r in asset["relations"]))
PY
```

Run it at the top of a product checkout. Each line starts with the `category`, and each item is
`id（Japanese word）`. `free_line` appears under `shape` but is not available to plugins (only the nine in §3.5).

Three categories outside the Saijiki are closed words defined by the core:

| Category | Words |
|---|---|
| `thinness` | `fine`, `extra_fine` |
| `relative_scale` | `very_small`, `small`, `slightly_small`, `normal`, `slightly_large`, `large`, `very_large` |
| `shape_form` | `regular` |

## 4. Calling a Plugin from DDL

| Written as | Meaning |
|---|---|
| `Sky.Stars.` / `Sky.星。` | a bare-name sentence; a count parameter chooses from `omitted` |
| `5 Sky.Stars.` / `5個のSky.星。` | a sentence with a count; a count parameter receives it |
| `red Sky.ColorStars.` / `赤いSky.色星。` | a word of a parameter's category written before the name (for a definition declaring a color parameter) |
| alongside `Place one red circle at center.` | plugin sentences mix with other sentences |

- Japanese and English DDL may call either the canonical name or an alias. The underdrawing writes the alias in
  Japanese DDL and the canonical name in English DDL.
- A word the definition does not take (`Place`, `置く`, `散らす`, …) written with it is left out alone with a
  diagnostic. Write a counted word as `5 Sky.Stars.`.
- A sentence whose name does not resolve (not loaded, disabled, misspelled, or a different definition) is left
  out alone, the rest is drawn, and the reason appears in the work's diagnostics
  ([SPEC §4.12](SPEC.md#412-unresolved-plugins-and-ddl-export)). No hidden LLM rewrites it into other words.

## 5. Ways to Load a Definition

The current specification loads new definitions in four ways. §5.1 is the usual one.

### 5.1 Adding a plugin file from the Web (a Server administrator)

Put the definitions and what the Saijiki shows in one JSON file (`inku.plugin-package.v1`) and choose it under
"Add a plugin" in the Web settings "Plugins". The `Sky.Stars` of §2 as a file looks like this. Saved as it is to a
UTF-8 file, for example `sky-night.json`, it passes the checks and can be added (checked on 5173, Build 1338, 2026-10-26).

```json
{
  "schema": "inku.plugin-package.v1",
  "namespace": "Sky",
  "name": "night",
  "version": "1.0.0",
  "description_ja": "夜空の語。",
  "description_en": "Night-sky words.",
  "words": [
    {
      "definition": {
        "schema": "inku.macro-definition.v1",
        "namespace": "Sky",
        "heading": "Stars",
        "aliases": ["星"],
        "version": "1.0.0",
        "parameters": {
          "star_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 9, "omitted": [3, 4, 5], "counter": "general"}
        },
        "components": {},
        "body": [
          {
            "op": "repeat",
            "count": {"expr": "parameter", "name": "star_count"},
            "maximum": 9,
            "index": "star_index",
            "body": [
              {
                "op": "vary",
                "binding": "star_size",
                "domain": "sky_stars_size",
                "choices": [
                  {"expr": "semantic_ref", "category": "relative_scale", "id": "very_small"},
                  {"expr": "semantic_ref", "category": "relative_scale", "id": "small"}
                ],
                "body": [
                  {
                    "op": "emit",
                    "binding": null,
                    "fields": {
                      "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                      "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                      "position_x": {"expr": "cycle", "index": {"expr": "local", "name": "star_index"}, "items": [
                        {"expr": "exact_decimal", "value": "0.170"}, {"expr": "exact_decimal", "value": "0.830"},
                        {"expr": "exact_decimal", "value": "0.500"}, {"expr": "exact_decimal", "value": "0.330"},
                        {"expr": "exact_decimal", "value": "0.670"}, {"expr": "exact_decimal", "value": "0.170"},
                        {"expr": "exact_decimal", "value": "0.830"}, {"expr": "exact_decimal", "value": "0.500"},
                        {"expr": "exact_decimal", "value": "0.330"}
                      ]},
                      "position_y": {"expr": "cycle", "index": {"expr": "local", "name": "star_index"}, "items": [
                        {"expr": "exact_decimal", "value": "0.100"}, {"expr": "exact_decimal", "value": "0.140"},
                        {"expr": "exact_decimal", "value": "0.280"}, {"expr": "exact_decimal", "value": "0.180"},
                        {"expr": "exact_decimal", "value": "0.080"}, {"expr": "exact_decimal", "value": "0.380"},
                        {"expr": "exact_decimal", "value": "0.340"}, {"expr": "exact_decimal", "value": "0.120"},
                        {"expr": "exact_decimal", "value": "0.420"}
                      ]},
                      "relative_scale": {"expr": "local", "name": "star_size"},
                      "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
                      "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
                      "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
                    }
                  }
                ]
              }
            ]
          }
        ]
      },
      "summary_ja": "空の上半分に、黄色の星を散らす。星の数を書けばその数（1〜9個）、書かなければ3〜5個。",
      "summary_en": "Scatters yellow stars over the upper half of the sky: the written count (1–9), or 3–5 when none is written.",
      "note_ja": "夜の空に小さな星。",
      "note_en": "Small stars in a night sky.",
      "example_ja": "5個のSky.星。",
      "example_en": "5 Sky.Stars."
    }
  ]
}
```

| Field | Required | Content |
|---|---|---|
| `schema` | required | exactly `inku.plugin-package.v1` |
| `namespace` | required | the namespace; every definition's `namespace` must equal it (§3.1) |
| `name` | required | the plugin's name: a letter, then letters, digits, `_`, `-`. `namespace.name` (e.g. `Sky.night`) is its id |
| `version` | required | in the form `1.0.0` |
| `description_ja`, `description_en` | optional | the description shown in the settings |
| `authors`, `license` | optional | authors (a list of strings) and terms of use |
| `words` | required | the words (1 to 64), each with the fields below |

Fields of each word:

| Field | Required | Content, and where it is shown |
|---|---|---|
| `definition` | required | an `inku.macro-definition.v1` definition (§3) |
| `summary_ja`, `summary_en` | one of the two | the summary given to the underdrawing (Stage 1) (§6); one alone serves both languages |
| `note_ja`, `note_en` | optional | the description line of the Saijiki preview (the "effect" line of a built-in word): say briefly what the word draws |
| `example_ja`, `example_en` | optional | the DDL sentence shown as the Saijiki's "example"; without one, `Sky.星。` (Japanese uses the first alias) and `Sky.Stars.` |
| `preview` | optional | the Saijiki preview's picture: the place of a PNG inside the zip (e.g. `previews/stars.png`); only in a zip |

A Saijiki preview has four parts: the title (canonical name or alias), the description (`note_*`), the example
(`example_*`), and the picture. Write examples whose count and wording show what the word looks like (for
`Sky.Stars`, `5 Sky.Stars.`).

The picture comes one of two ways:

- Your own picture: name the JSON above `package.json` and zip it with the PNGs its words name in `preview`. A PNG
  of any shape is fitted to the Saijiki frame (216×92 and twice that), the margin filled with its corner colour.
- Drawn: for a word without `preview`, the Server draws its Japanese example on adding, cuts out what it drew,
  and fits it into the frame.

The zip (`package.json` at its top; the PNGs may sit anywhere under any name):

```text
sky-night.zip
├── package.json          (the form of §5.1; the word has "preview": "previews/stars.png")
└── previews/
    └── stars.png
```

With or without `preview`, the examples are drawn as a check (step 3 below). `preview` in a JSON file alone is a
problem.

Three checks run in order, and a file can be added only when all of them pass:

1. The file's shape (unknown fields, required fields, a namespace that differs, a missing summary, and so on).
2. The shared core's checks of each definition (the mistakes of §7.2), and names another plugin already holds.
3. Each word's Japanese and English example is drawn as DDL through the shared pipeline. Drawing nothing, or a
   diagnostic, fails the check.

Whatever is wrong is listed per word with its place in the file
(e.g. `words[0].definition.body[0].body[0].body[0].fields.color`) and the reason.
Only a file that is not JSON, has no readable `namespace` or `name`, or has no words stops at step 1. Otherwise a
shape problem such as a missing summary does not stop steps 2 and 3, so one check lists everything to fix. A word
whose definition has a problem is not drawn.

- An added word can be drawn in every new work on that Server, appears in the Saijiki and DDL editor completion,
  and its summary reaches the underdrawing when drawing from a description.
- When a plugin with the same id (`namespace.name`) is installed, "Add" becomes "Replace"; new works then draw
  with the new definitions.
- "Replace picture" on a word uploads a PNG that the Saijiki shows instead (fitted to the frame); "Back to the original
  picture" returns to the file's picture (`preview`) or the one drawn from the example. Replacing the plugin keeps
  replaced pictures.
- "Export" saves an installed plugin as a zip: `package.json` with the picture each word shows in the Saijiki now (a
  replaced one where there is one), each word's `preview` naming it. Another Server can add it as it is.
- Switching a plugin off removes it from new works, the Saijiki, and completion. It can also be deleted.
- Saved works carry copies of the definitions they used, so they redraw the same after a replacement, a switch-off,
  or a deletion.
- The files are kept in the Server's `INKU_PLUGIN_PACKAGE_DIR` ([Server configuration §2.5](manual/en/server-configuration.md)).
- The API is `POST /api/plugins/packages/validate` (check only), `POST /api/plugins/packages` (add; a JSON file as
  `document`, a zip in base64 as `archive`), and `GET /api/plugins/{plugin_id}/export` (export), for administrators only.
- Android and macOS never call the Server, so words added here are not available there yet.

### 5.2 A DDL export file (immediately usable by an author)

Make the JSON of §2 (`inku.ddl-export.v1`) and load it; the definitions in `plugins` serve that new work only.

| Field | Content |
|---|---|
| `schema` | exactly `inku.ddl-export.v1` |
| `language` | `ja` or `en` |
| `ddl` | the text placed in the DDL editor on load |
| `plugins` | a list of `{"definition": definition, "summary": summary}` (up to 64) |
| `exported_from` | where it came from; `{}` when you make it yourself |

- Web: open "New instructions" under the Describe tab and choose the file with "Load". The loaded definitions are named.
- CLI: pass it as in `uv run inku-cli paint --input-mode ddl --file stars.ddl.json`.
- Android and macOS read the same format.
- Loaded definitions are never installed. They take precedence over an installed definition of the same name,
  and a catalog diagnostic (`imported_plugin_differs_from_installed`, `imported_plugin_not_installed`) says
  when the content differs or the name is not installed.
- Exporting a drawn work writes the definitions its DDL names, with their summaries, in the same format, so it
  can be carried to another environment.

### 5.3 The Server's pipeline manifest (an administrator adds it to every new work)

Add the definition to `pipeline.definitions` and its summary, in the same order, to `pipeline.macro_summaries`
in the manifest that the Server's `INKU_PIPELINE_CONFIG` names. How to make the manifest is in
[Server configuration §2.4](manual/en/server-configuration.md).

```json
"definitions": [ { "schema": "inku.macro-definition.v1", "namespace": "Sky", "heading": "Stars", "…": "…" } ],
"macro_summaries": [ "Scatter yellow stars over the upper half of the sky: …" ]
```

- Every new work on that Server can use it. When drawing from a description, the name and summary reach the
  underdrawing (Stage 1), which chooses it when the description writes the word.
- If the two lists differ in length, a new work's run fails with `macro_catalog_summary_mismatch`.
- It does not appear on the settings "Plugins" screen or in the Saijiki and cannot be enabled or disabled there. §5.1 is easier to manage.

### 5.4 Bundling with the shared core (a development change)

Bundling like `Nature.leaves` for every host means placing an `inku.bundled-macro-package.v1` package under
`core/crates/inku-ddl/assets/`, adding it to the bundled names in `inku-pipeline-uniffi/src/macro_catalog.rs`,
and having the Server's `_BUNDLED_DOCUMENTS` in `server/src/inku_server/plugins/__init__.py` and Android's
`SharedPipelineConfigBuilder.kt` name that package. This is a product change that needs a build and a deployment.

### 5.5 What does not load today

- A new `.inku-plugin.md` in `server/plugins/` (`INKU_DOCUMENT_PLUGIN_DIR`) does not become a definition.
  Documents other than the bundled package show "not used for drawing", and their words are left out.
- "Read and draw" and the image tab do not give the model a list of plugins. A name the model writes in DDL
  draws, but without the list the model will rarely choose one.
- Android and macOS have no way yet for users to install definitions, and there is no public catalog of installable packages.

## 6. Writing the Summary

The summary is the only description the underdrawing's (Stage 1's) LLM receives when drawing from a
description; it never receives the definition body or expanded DDL. The underdrawing chooses a plugin, as a
bare-name sentence, only when the description writes the heading word of its name or a paraphrase of the same
thing, never by association with a season, place, or similar thing.

- Say what is drawn, where on the canvas, and with which medium, color, and form.
- For a count, give the range and the number when none is written ("the written count (1–9), or 3–5 when none is written").
- Prepare both Japanese and English (a plugin file carries `summary_ja` and `summary_en`, a bundled package
  `summaries.ja` and `summaries.en`; an export file and the manifest take one string).
- The Server's default limit is 8192 bytes. The summary in §2 and those of the bundled `Nature.leaves` are models.

## 7. Checking, and When Something Goes Wrong

A Server administrator only has to choose the file under "Add a plugin" in the Web: the three checks of §5.1
run together, and their reasons read as in the table of §7.2. To check without adding, read the result and
press "Cancel". §7.1 below checks a definition alone in a product checkout, without a Server.

### 7.1 Checking a definition alone

In a product checkout, pass the definition to the command below. A valid definition shows its canonical name,
version, and digest under `definition_identities`. A mistake prints an `Error:` line with the diagnostic
code and the field (`path`).

```sh
scripts/rust-toolchain.sh run -q -p inku-ddl --example compile-score --locked --offline <<'JSON'
[{"source": "Sky.Stars.", "language": "en", "definitions": [the definition JSON here]}]
JSON
```

Without a lock, this command's `outcome` is `Stopped` (`macro_resolution_missing_lock`). To see whether it
draws, put the printed `definition_identities` into `"macro_locks"` and run it again. This tool cannot add
aliases to a lock, so call the canonical name here; the product also accepts aliases.

### 7.2 Common mistakes

| Diagnostic code | Meaning and fix |
|---|---|
| `unknown_semantic_id` | the `id` is not in the Saijiki (for example color `pink`); choose from the list in §3.8 |
| `unknown_semantic_category` | `category` is misspelled |
| `unknown_semantic_field` | an `emit` field name is not in §3.7 |
| `semantic_field_requires_matching_reference` | the field and the word's category do not match |
| `geometry_field_requires_exact_decimal` | a position or dimension is not `exact_decimal` |
| `invalid_count_parameter` | the count parameter's bounds or choices break the rules of §3.4 |
| `invalid_repeat_count` / `unbounded_repeat` | `repeat` `count` is not an integer or exceeds `maximum`, or `maximum` is 0 |
| `undefined_parameter` / `undefined_local` | reads an undeclared parameter, or an `index` / `binding` outside its scope |
| `undefined_anchor` | `relation` `from` / `to` matches no `binding` or `anchor` |
| `invalid_alias` / `duplicate_alias` | an alias has unusable characters or repeats the heading or another alias |
| `invalid_semantic_version` | `version` is not like `1.0.0` |
| `component_cycle` | a component calls itself |

- If an export file's definition has a mistake, it is not loaded and its sentence is left out with
  `macro_resolution_missing_lock`. The drawing result does not show the definition's code, so check it with
  §7.1 before loading.
- When the name resolves but nothing is drawn, check that the call writes every declared parameter (§3.4), that
  the count is in range, and that the expansion stays within the limits (§8). If the DDL holds only that word,
  leaving it out leaves nothing to draw and no work is made.

### 7.3 Problems a plugin file check reports

"Add a plugin" in the Web reports these codes besides the definition mistakes of §7.2. The screen shows an
explanation with the same meaning.

| Step | Diagnostic code | Meaning and fix |
|---|---|---|
| shape | `invalid_json` | not valid JSON; the detail gives the line and column |
| shape | `unknown_field` | a key not in the tables of §5.1; fix its spelling or remove it |
| shape | `wrong_schema` | `schema` is not `inku.plugin-package.v1` |
| shape | `invalid_identifier` | `namespace` or `name` is not a letter followed by letters, digits, `_`, `-` |
| shape | `invalid_semantic_version` | `version` is not in the form `1.0.0` |
| shape | `not_an_object` | a word, or its `definition`, is not an object (`{ }`) |
| shape | `no_words`, `too_many_words` | `words` is empty or has more than 64 |
| shape | `namespace_differs_from_package` | a definition's `namespace` differs from the file's |
| shape | `no_summary` | neither `summary_ja` nor `summary_en` is written |
| shape | `not_a_string`, `text_too_long` | not a string, or too long (§8) |
| definition | `unknown_json_field` | the definition has an unknown field (the place points at the definition's start) |
| definition | `duplicate_qualified_name` | two words in the file share a canonical name or alias |
| definition | `name_taken` | another installed plugin (the bundled `Nature.leaves` included) holds the name; the detail gives the name and its holder |
| example | `macro_binding_count_out_of_range` | the example's count is outside the range the definition takes |
| example | `macro_resolution_missing_lock` | the example's word is not found (a misspelt name) |
| example | `example_draws_nothing`, `example_not_drawn` | the example draws nothing, or cannot be drawn |
| picture | `not_a_png`, `image_too_large` | a `preview` or replacement picture is not a PNG, or is too large (§8) |
| picture | `preview_needs_zip` | `preview` in a JSON file alone; zip it, or remove `preview` |
| picture | `preview_not_found` | the zip has no PNG by the `preview` name (case and folders must match) |
| picture | `invalid_preview_path` | `preview` starts with `/` or holds `..` |
| zip | `invalid_zip`, `not_base64` | not a readable zip |
| zip | `archive_without_package_json` | no `package.json` at the top of the zip (check it is not inside a folder) |
| zip | `archive_too_large`, `too_many_archive_members` | the zip is too large, or holds too many files (§8) |
| zip | `not_utf8` | `package.json` is not UTF-8 |

A shape problem does not stop the definition and example checks (§5.1). A word whose definition has a problem
is not drawn.

## 8. Limits

| Limit | Default | Set by |
|---|---|---|
| plugin file size | 1,000,000 bytes (UTF-8) | the Server (fixed) |
| words in a plugin file | 64 | the Server (fixed) |
| length of `description_*` and `note_*` | 2000 characters | the Server (fixed) |
| length of `example_*` | 500 characters | the Server (fixed) |
| length of `license` | 200 characters | the Server (fixed) |
| `preview` and replacement pictures | PNG, up to 2 MiB each and 4096×4096 pixels | the Server (fixed); fitted to the frame (216×92 and twice that) |
| zip | up to 16 MiB, 256 files inside, 64 MiB of PNGs in all | the Server (fixed); read without unpacking |
| definitions in an export file | 64 | the Web, Android, and macOS readers |
| definitions given to the underdrawing | 64 | Server manifest `prompt_limits.max_catalog_entries` |
| summary length | 8192 bytes | Server manifest `prompt_limits.max_summary_bytes` |
| expansion | 64 calls, depth 16, 8192 evaluation steps, 128 nodes per call, 128 nodes in all | Server manifest `compiler.macro_expansion_limits` |
| shape instructions in a work | 64 | the admin limit `max_instructions` ([Server configuration §5.1](manual/en/server-configuration.md)) |

- Nodes are the statements an expansion actually passes through; statements inside `repeat` count once per
  repetition. In §2 each star is two nodes (`vary` and `emit`), and the 2026-10-26 check drew up to 64 stars
  from one call and none at 65.
- A call over the expansion limit is left out with a diagnostic (`expansion_node_budget`) and the rest is
  drawn. Over the instruction limit, the calls beyond it are recorded in `resource_omissions` and left out.
  Over the whole-work node limit, no work may be made (in the 2026-10-26 check, DDL with seven calls of 20
  could not be drawn).
- Checking multiplies the `repeat` `maximum` values into a worst case and rejects a definition that overflows.
  Keep a count range within what the limits can draw.

## 9. What a Definition Cannot Do

A definition is data only. It cannot contain arbitrary code, I/O, filesystem, network, clock, or environment
access, recursion, dependencies on other definitions, raw SVG or Score data, Renderer instructions, or
plugin-specific syntax, parsers, or renderers. It cannot add a shape kind or change the meaning of core words.
Widening this freedom requires a separate author ruling and a new schema version
([SPEC §4.11](SPEC.md#411-the-boundary-of-freedom)).

---

## Appendix A. Implementation Detail

What follows is detail that an author's steps do not need.

### A.1 Resolution and expansion

The compiler resolves an explicit qualified invocation against a sidecar lock. The lock attests the definition
name, version, canonical digest, aliases, document and compiler identity, and the source and generated
provenance needed to reproduce the expansion. Expansion binds typed parameters and uses the attested
composition seed plus caller-owned finite bounds. It is effect-free and deterministic, and its output rejoins
ordinary typed lowering.

A definition's canonical identity is the domain-separated SHA-256 of its validated canonical JSON bytes. Empty
aliases do not enter the canonical bytes. `exact_decimal` normalizes `0.240` and `0.24` to one value while the
definition keeps its original spelling.

The shared Rust compiler foundation can parse, validate, identify, lock, bind, and deterministically expand
MacroDefinition v1 values. Its finite Emit subset, including Groups and rotation-only Transforms, reaches an
actual Score through the same lowerer used by ordinary DDL, with shared local-recovery outcomes and typed
omission diagnostics. The compile-once facade retains the original document, compiler state, lock, and issues.
Both legacy mode inputs apply the same local recovery to typed upstream holes, conflicts, and dependent units
in a sealed execution projection while preserving independent instructions. Canonical macro output reuses its
original seed, semantic ordinal, and generated provenance without expansion retry. Missing or duplicate
execution owners, global budgets, and integrity failures stop both modes. The public Stage 1.5 API remains
strict. The Score wire, canonical meaning, seed, geometry policy, and generated provenance are unchanged. This
is part of ordinary drawing on the Server and on Android. For a new work, the host resolves a catalog from the
definitions, passes their names and summaries to Stage 1, the compiler expands them, and the definitions used
are saved with the work as locks. Definitions come from packages bundled with the shared core, the
`definitions` / `macro_summaries` of the Server's pipeline manifest, and loaded export files (§5).

### A.2 Emit lowering

Each complete Emit becomes one ordinary Score instruction. A sequence of complete Emits keeps its order,
including Emits already expanded through `use`, bounded `repeat`, or `vary`, and Emits nested inside
placement-free `group` containers. Group traversal preserves generated owners and reference IDs resolved in
lexical scope; it adds no placement, transform, or drawing instruction. Thinness is a closed core category
outside Saijiki: only `thinness:fine` and `thinness:extra_fine` are accepted, and both use the same lowerer as
ordinary DDL. The other closed core category, `relative_scale`, uses ordinary normal geometry and the existing
factor exactly once, keeping explicit normal distinct from omission. Angle uses the same seeded resolver as
ordinary DDL and reaches `Score.rotation` for every supported shape whose orientation is visible, including
line, arc, and square. Point rejects an explicit angle because its round mark has no authored orientation.
Existing fill behavior for omitted, `none`, and `solid` surface remains; the positive surface qualities use the
same existing `SurfaceSpec` defaults as ordinary DDL. A Macro does not author a document Ground. A verified
document-owned Ground reaches the same lowerer as a `CanvasGroundSpec` with the host-resolved aspect. Omitted
drawing attributes and normal count-one geometry use the same defaults as ordinary DDL.

Declared flat Emits with `movement` set to `line_up`, `scatter`, or `tile` reach the same object-size / placement resolver as ordinary DDL through the verified Stage 1.5 plan API. Omitted Emit count resolves to eight; explicit positive integers through u32::MAX remain exact. Missing required parameters and invalid types never receive that default. Size uses the canvas short edge independently of count, preserving normal sizes, size factors, appearance, and angle for all nine shapes. Optional `layout_direction` requires an existing `angle` category SemanticRef and expands literals or declared parameter / local references. It is separate from shape `angle` and delivers horizontal, vertical, or physical 45-degree rows only to line_up. Omission and explicit horizontal retain distinct identities; bare diagonal chooses two axes using original meaning, attested optional composition seed, and original occurrence under a dedicated role. Unsupported actions / identities such as rotated and undeclared caller direction stop or omit the original execution unit. Multiple parameters in the same category are not disambiguated by names. Plans also retain tile from physical aspect or a scatter recipe requiring a later performance seed, together with generated owners, bindings, and provenance. They add no undeclared caller overlay or fan-out. Stop / Continue retain field / Emit / invocation omission units. Ready plan does not mean an instance array, Score, or drawing succeeded. The existing field-absent place / count-one Score path remains; the Score entrance cannot silently discard an Emit direction. Whole Step10, Step11, and runtime integration remain incomplete.

Shapes retain the existing triangle / square / polygon identities. Optional Emit field `proportion_aspect` accepts ratio category tall / wide; `shape_form` accepts the closed core shape_form category regular; `sides` accepts an Integer from five through eight. Definition literals, declared parameters, and locals share one consumer. Callers bind independent facts such as regular / 正形 and sides 6 / 辺数6 to declarations. Multiple Integer parameters are not disambiguated by name. Undeclared facts and missing required arguments cannot be discarded or defaulted. The consumer shares ordinary DDL normal geometry, regular forms, and default 2:1 aspect. Place / count one reaches actual Score; repetition retains exact constraints in a plan. Triangle and square use bounding-box centers; polygon uses its circumcircle. Incompatible regular / aspect or out-of-range sides stop or omit the original Emit.

Meaning bound through declared parameters is read from the expanded Emit. An unbound caller appearance field
does not fan out or override generated values; OmitAndContinue drops that caller field and preserves the
definition's color, touch, continuity, or surface. An unused parameter or an unreferenced Emit binding ID does
not fail merely for being unused. The finite consumer recognizes only an omitted count or an integer count of
one; it never treats a floating-point `1.0` as that integer. An angle written on the Macro caller is unbound
caller meaning; it does not fan out to or override angles authored by individual Emits.

Thinness and size bind only parameters explicitly declared with `{"type":"semantic_ref","category":"thinness"}`
or the `relative_scale` category. For example, `thin normal-sized Draw.Mark` supplies these two finite facts
when `Draw.Mark` declares one parameter for each category. Size uses the existing modifier-before-head syntax.
An Emit reads the named parameter through `{"expr":"parameter","name":"scale"}` in its `relative_scale` field.
The assignment must be unique and complete. Each core fact retains its original source owner and has no
Saijiki asset metadata; ordinary entity modifiers do not consume it again. Missing or ambiguous binding follows
the upstream error policy; undeclared caller facts retain existing lowering diagnostics. There is no automatic
overlay or fan-out, and a bound parameter alone does not become a continuation predicate.

Legacy Stop input remains accepted. Incomplete Emits, unknown keys, mismatched value types or categories,
unbound caller facts, repeated outer counts, and expanded `transform` or `anchor` nodes retain their
established failure handling; a recoverable relation failure never stops the whole Score. It records an error,
removes only the relation, and draws its Emit, group, and dependent Emits at their original transformed
placement. Under explicit OmitAndContinue, a supported appearance problem omits only that field and uses the
ordinary default; an invalid Emit omits that Emit; and an unsupported structural node omits its whole subtree
without extracting child Emits. Invalid outer placement, size, count, relation, or other caller meaning omits
the invocation. Unrelated siblings, including those inside Groups, retain source and generated-provenance
order. Diagnostics identify source or generated ownership, spans, invocation, expansion path, generated
ordinal, field key, and the actual omission unit. If no drawing target remains, the result is stopped.

### A.3 Sway

The optional SemanticRef `dimension` is closed to `amplitude`, `frequency`, or `quality`, and is allowed only
for category variation. Omitted / None preserves legacy category-only matching and canonical bytes / digest; a
specified constraint participates in the digest. Parameter names do not imply dimensions.

Flat Emit keys are `fluctuation_amplitude`, `fluctuation_frequency`, and `fluctuation_quality`; their
expression category stays `variation`. The respective IDs are `narrowly` / `broadly`, `loosely` / `tightly`,
and `swaying` / `undulating` (Saijiki v2; the Saijiki v2 migration rewrote v1's `fine`, `large`, `slowly`,
`quickly`, `trembling`, and `blurring`). `ink_spread` takes `bleeding`. Definition-local `use` shares the
classification, and deferred actual values are checked at execution boundaries. Mapping, missing-slot
defaults, and supported shapes follow ordinary DDL in SPEC §13.6.

Three declared parameters require three caller values; supplying only one is a binding error. Declaring only
an amplitude parameter and delivering its Emit field yields Medium frequency and Perlin quality. All three
slots absent means no variation. Invalid values do not become None: undeclared callers keep invocation
diagnostics and malformed Emits keep Emit diagnostics and omission units. The sway fields reach the Score's
`variation` (checked on 2026-10-26: an Emit with `broadly` and `undulating` became `broad`, `wave`, and
frequency `medium`). Authors do not write internal Variation JSON.

### A.4 Exact numeric parameters and delivery

Exact decimals use a closed typed expression such as `{"expr":"exact_decimal","value":"0.240"}` and the same ExactDecimal representation as ordinary DDL. The original definition retains its spelling; canonical identity normalizes `0.240` and `0.24` to the same value. Existing `number` / `Number(f64)` meaning and definition bytes remain unchanged, and exact values are never reconstructed from f64. Literals, declared parameters, locals, components, and finite choices preserve the exact type. This adds no general arithmetic or implicit conversion into numeric ranges or transforms.

Declare a parameter with, for example, `{"type":"exact_decimal","dimension":"radius"}`. The optional dimension is closed to `radius` / `diameter` / `length` / `side` / `width` / `height` / `chord` / `sagitta` / `position_x` / `position_y`. Binding matches explicit caller dimensions and values uniquely and completely; parameter names imply no meaning. An omitted dimension matches only a standalone number without a dimension. A clause mixing an ordinary primitive with an exact-parameter Macro retains the existing unsupported numeric-ownership boundary and reports an ambiguous assignment; separate clauses are unaffected. Compound width/height, chord/sagitta, and X/Y facts transfer only when every component binds to the same invocation, retaining the original keyword and decimal provenance.

Flat Emit fields with those names accept exact values. `width`+`height`, `chord`+`sagitta`, and `position_x`+`position_y` require both components; missing or mistyped values produce diagnostics. Numeric position and named `place` have separate authority and cannot silently overwrite one another. Dimensions and positions reach the ordinary DDL resolver, including diagnostic recovery to the smaller overlapping size. Definition literals belong to their generated Emit and do not receive fabricated source spans. Count-one/place reaches actual Score; repetition reaches the resolved plan and leaves instance generation to later materialization.

### A.5 Geometry and count boundary

Macros emit typed core meaning rather than final geometry. Size has three distinct authorities: unspecified,
explicit qualitative, and explicit numeric geometry. Explicit normal is not unspecified. Position likewise
distinguishes named center, a qualitative region, and an exact numeric coordinate. Isotropic size uses its
allocation or the short side, so circles remain circular and ellipse aspect is preserved.

Geometry is resolved only by the single `inku-ddl` owner identified as `inku.geometry-resolution-policy.v1`;
plugins cannot add another owner or a tenth primitive. Exact counts remain lossless symbolic intent until the
Step 11 pure ceiling passes before any O(count) allocation or materialization.

### A.6 Counts, transforms, and placement groups

When a definition does not receive the word's count, the count repeats the whole word from outside. The copies are not stacked in one place: the call's action lays them out once. No action, placing, scattering, and drawing put one copy in each cell sized to the drawn copy, by the seed; lining up and tiling follow their actions (I-708). In bundled `Nature.leaves` 2.1.0 every word but AutumnLeaves receives its count.

| Word | Count | Range | When omitted | Placement |
|---|---|---|---|---|
| YoungLeaves | leaves | 1–12 | 4–6 | twelve cells of the upper half, six columns by two rows, one leaf per cell with a small shift |
| Undergrowth, WitheredGrass | clumps of 3–5 blades | 1–3 | 1–2 | three root spots along the bottom; each clump's blade count and order come from the seed |
| SummerLeaves | leaves on the branch | 1–12 | 6–8 | twelve points along the branch; the point sets the side and size |
| FallenLeaves | leaves | 1–16 | 8–12 | sixteen cells of the drift, eight steps finer toward the bottom by two sides, a seed-chosen spot in each; red and gray alternate across the cells |
| WitheredLeaves | leaves | 1–8 | 2–4 | each leaf takes the left or right lower corner from the seed, and its own of eight cells there with a seed-chosen shift |

Each word takes its positions in an order that stays balanced at any count. AutumnLeaves draws the lobes of one maple leaf, so it declares no count, and a written count still repeats the whole word as the number of maple leaves. Stage 1's underdrawing passes a count written in a description to its plugin as `10枚のNature.若葉。` or `10 Nature.YoungLeaves.`.

`transform` retains the contiguous Emit range carried by transparent `group` from inner to outer. Count-one reaches Score 0.5.0 `transform_groups`; repetition reaches a symbolic plan without materializing instances. Finite `scale_x` / `scale_y` and `translate_x` / `translate_y` compose as a general affine transform: scale at the bounding-box center, rotate at that center, then translate on normalized canvas axes. They change geometry and spacing only, retaining stroke width and grain pitch. Rotation-only Score 0.4.0 groups remain compatible. External Touching / Along / Cutting preserve transformed geometry, direction, and explicit values while attempting one whole-group translation. Failure records an error, removes only the relation, and leaves the group at its original transformed placement. Step11 materialization and Step13 runtime / UI / persistence cutover remain incomplete. A Transform holding only Anchors uses the bounding-box center of all its resolved Anchors.

Primitive-only direct coordinated groups at existing named places reach Score 0.8.0 `placement_groups`. Omitted internal placement uses `overlap` to align member bounding-box centers; “place in a row” retains the source-order `horizontal_source_order` wire value; “overlap” uses `overlap`; `scatter` and `tile` use the new `scatter` and `tile` wire values. One named region resolves once from the performance seed and moves the whole group. Member owners, counts, seeds, and geometry remain intact. An omitted line-up count is one for every member and reaches an actual Score. Scatter and tile preserve explicit counts and divide the remainder up to a total of eight evenly among omitted members, assigning any remainder to earlier omitted members in source order. Each omitted member receives at least one, even when explicit counts plus those minima exceed eight. The same rule applies when all counts are omitted: nine listed kinds receive one each. Fully explicit counts are not topped up to eight. Line-up and place assign one only to omitted members. The group reaches an actual Score only when all resolved counts are one; otherwise it remains a symbolic plan without instance materialization. This direct carrier adds neither a Macro authoring operator nor instance materialization.

Anchors are non-drawing Score 0.6.0 targets that deliver explicit named positions or numeric coordinates to Connected. Anchor `place:center` is the single canvas-center point, distinct from the central region a drawn shape at `center` uses. Anchors follow enclosing Transforms while preserving drawing instruction order, seeds, and saved-version compatibility.

Place literals and explicitly declared `{"type":"semantic_ref","category":"place"}` parameters use the same regions in SPEC §18, including center as the canvas-center region. Stage 2 selects a corner from attested meaning, composition seed, and original occurrence; the Renderer chooses its anchor within that corner. Generated coordinates never masquerade as original source. No implicit caller overlay or omitted-place default is added.

An explicit `connected` or `touching` relation may join two adjacent bound Emits in the same expansion. It preserves Emit order, generated ownership, and the same named-movable or numeric-fixed position authority as ordinary DDL, and uses the same checked Score performer as ordinary DDL. A missing, nonadjacent, or omitted `from` records an error and removes only the relation; it never retargets to the last surviving Emit. Touching accepts Line / Arc, matches both endpoints, and shares the ordinary Arc reconstruction. Explicit dimensions, relative scale (including normal), and chord direction remain fixed; omitted normal may adjust. Macro relations check actual typed Emits without creating a literal noun condition. `not_touching` and `between` also use adjacent bound Emits and the ordinary checked performer. They accept named or noncenter placement while retaining numeric placement as fixed authority. NotTouching keeps the existing Medium gap. Between keeps the existing recipe based on the bounding-box centers of the immediately preceding Emit and the Emit before it; its `from` is that preceding Emit, and both reference owners remain intact. Adjacency includes every original Emit, including unbound Emits. An omitted from or either Between reference never retargets to a survivor. Relations inside placement-free Groups use the same rules. Unsupported subtrees are not traversed and cannot be crossed to create adjacency. `along` / `cutting` also accept adjacent bound Line Emits through the shared checked performer with that same position authority. Along aligns an unspecified direction parallel to the preceding line; Cutting retains the resolved length. Explicit direction, dimensions, and numeric position remain authoritative. Unsupported pairs or incompatible constraints record an error and remove only that relation without retargeting. Other relation kinds remain unsupported.

Score 0.9 `placement_groups.members` carries one Macro body as atomic ordered drawable ranges and Anchor ownership. It does not create a Macro authoring operator or materialize individual repetitions; group-head count and internal Emit count remain separate. A standalone Macro written with a count of two or more that it does not receive becomes one member of a placement group laid out by the call's action: `cells` (Score 0.19.0) for no action, placing, scattering, and drawing, and `horizontal_source_order` or `tile` for lining up and tiling (I-708). A count of one, and a call with a position, a fill, an order, or a relation, or one that a mirror takes as its target, keeps its outer repetitions symbolically.

Member `transform_group_indices` retains source-owned internal transforms before placement. Their valid member range contains their Anchors even when an Anchor-only transformed member follows an earlier drawable member; unlisted equal-range transforms remain outer and run afterward.

`CompositionPlanResult.standalone_macro_repetitions` retains the existing body positions, range, Anchors, internal transforms, and source-head repeat count symbolically; it creates no outer placement or actual Score instances. It holds only the calls that keep the outer repetition; other counted calls are placement-group members (I-708).

### A.7 Bundled package, legacy format, and compatibility

The bundled `Nature.leaves` (package 2.1.0) is an installed package with seven words, such as
`Nature.YoungLeaves` (alias `Nature.若葉`). Its definitions are MacroDefinition v1 values held by the shared
core. On the Server, `server/plugins/nature-leaves.inku-plugin.md` serves as the unit that is enabled or
disabled and as the source of the words, notes, and previews the Saijiki shows; its prose expansions are not
interpreted as definitions. No other `.inku-plugin.md` in the same namespace is translated into definitions
implicitly. `Nature.雨` and `Bamboo` are explanatory names in SPEC, not entries in an official registry. The
v1.70 hard-coded Nature expansion is not the current authoring format.

`plugin_storage["canvas-aspect"]`, the `canvas_aspect` request alias, and the system/user plugin directories
are compatibility surfaces while retirement remains unfinished. The Server's settings screen no longer creates
or edits documents (2026-09-28) and marks a document without definitions as not used for drawing. The Server's
per-document enable control and Android's `Nature.leaves` switch decide whether the bundled package is used for
new works; saved works use their locked definitions and are unaffected.

A compatibility importer reports `legacy_plugin_format` and returns a per-macro `Imported` or `Omitted`
outcome. Existing works prefer their stored Score or expanded artifact. An omitted macro without such an
artifact must not silently render partially, fall back to the old expander forever, or become a different figure.
