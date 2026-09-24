# inku — Drawing Description Language Specification

**Version: v1.92.0**
**Canonical source:** [SPEC.ja.md](SPEC.ja.md)

This document is the official English specification for public review, contest
submission, and non-Japanese readers.  It is adapted from `SPEC.ja.md`, which is
the canonical source because the author works in Japanese.  When the
specification changes, update `SPEC.ja.md` first, then refresh this English
version.

**The Japanese and English versions correspond section for section.** A change
to the specification is written in `SPEC.ja.md` first and then reflected here.

For ordinary development, start with [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
and read only the specification sections relevant to the task. Chronological
release history is maintained separately in [CHANGELOG.md](CHANGELOG.md), with
more detailed canonical notes in [CHANGELOG.ja.md](CHANGELOG.ja.md).

## About This Document

**inku** is the reference implementation project for DDL (Drawing Description
Language). DDL is the language specification; inku is the name for its
implementations as a whole.

This document records the **design principles, the language design, and the
current principal contracts**.  For ordinary development, read the short entry
point [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) first and come back here only
for the sections a task actually touches.  The chronological implementation and
design record is kept separately in [`CHANGELOG.md`](CHANGELOG.md).

### The Name "inku"

- From インク, the Japanese reading of **ink**
- The material of writing is itself the name -- structurally expressing DDL's
  concept that the description is the work
- The association with 墨 (sumi): the world of calligraphy and ink painting,
  echoed by the shades of ink that appear in the strokes
- The `-lang` suffix places it as a language project, beside rust-lang, go-lang
  and the like

### Ecosystem Naming

Derived projects share the `inku-` prefix:

- `inku-core` -- the shared Rust core. Server and Android use both its Renderer and Typed Compiler through the shared authoring pipeline
- `inku-saijiki` -- the vocabulary dictionary, aiming to be minimal yet sufficient
- `inku-plugin` -- drawing-extension plugins; they do not extend the vocabulary and act as macro sets
- `inku-web` -- the container-based web UI implementation
- `inku-android` -- the single-user Android implementation, including camera features
- `inku-cli` -- the command line tool

---

## 1. Core Concepts

### 1.1 A Language for Writing Visual Tanka

DDL is not merely a language for describing graphics. It is positioned as a language
for **writing visual tanka**.

`inku` is the reference implementation of DDL. It is not a drawing program in
the usual sense: a short written description is the durable work, its typed
document retains shared meaning, and the resulting Score is performed once as
SVG. Hosts share that Score contract; sway appears only while performing and
does not rewrite the description or its meaning.

It rests on three pillars of constraint:

| Source idea | What inku drew from it |
|---|---|
| **Sol LeWitt's instructions** | The idea that the description itself is the work; the separation of the roles of description and drawing |
| **Bonsai** | Unlimited vocabulary and specifications constrain the maker; limited choices foster better creation |
| **Tanka** | The kind of writing to take as a target: writing that carries abundant meaning and belongs to an established tradition |

### 1.2 The Underlying Stance

- **Do not assert, present** -- the author's feeling and reading must not
  intrude directly into the work (this does not deny the author's role as its
  carrier)
- **A short description is the essence** -- a long description leans toward
  assertion. Brevity is what makes presentation of the essence possible
- **The form pares away the ego** -- it is precisely because there is a fixed
  form and a constraint that the essence surfaces

### 1.3 Origin

- 2026-04-02, the exhibition "Sol LeWitt: Open Structures" at the Museum of
  Contemporary Art Tokyo
- To reproduce, in the different medium of drawing, the experience the author
  had known through writing: that the fog of the mind is pared away and what
  was there all along becomes visible

---

## 2. Design Principles

1. **Descriptions are human-readable** — they sit between natural language and a description language.
2. **Sway is part of the specification** — architectural variation in an LLM is not eliminated as a bug. Sway exists at two scales, micro (line wobble and bleeding) and macro (composition and placement), and both are realized in the performance (Renderer) (Sections 13.8 / 14.4).
3. **Emotional vocabulary is excluded** — use numbers and the vocabulary of physical materials rather than words such as "beautifully."
4. **There is no fixed size** — size and position are expressed relative to a reference edge, not as absolute pixel values. The work scales to a wall as readily as to a screen. **The aspect ratio is not fixed either** — it is a constraint that shapes the world of the work, not a dimension the description carries.
5. **Output is a still image** — the viewer moves, not the image. **How a surface is** is a state of the still image, not the passage of time (author's ruling, 2026-08-12). Fill and texture enter the vocabulary as **state nouns** — "flat", not "to paint". A verb would collide both with this principle and with §3.1's "placing, not drawing", which is why 描く was pruned in v1.92.
6. **The design converts prose into normalized DDL for validation by the Typed Compiler** — input may be free, but DDL has a clear form and rules. Completely free-form input overwhelms the user; appropriate structure supports creation. The normal Server and Web are connected to the shared Typed Compiler; §12 describes the active generation path.
7. **The engine does not go backwards.** Like a woodblock being carved, the drawing engine only moves in one direction. Past versions are not kept in the system and cannot be selected. **What remains is the printed work — the saved SVG — not the block as it was before the cut** (§2.1).

### 2.1 Performance Versions, Identity, and Preservation

Only deterministic layers carry versions. Stage 1 and Stage 2 are LLM layers that can vary for the same input, so they retain the digest of the prompt actually sent as provenance rather than a version. `render_engine_version` rises when the same Score and seed perform differently, or when the performable vocabulary grows. A rename of a word or tool does not raise it and does not by itself require updating a reference record. `ddl_engine_version` rises when a deterministic transform's output changes and when `Instruction` field declaration order changes; changing the order measures both the field that moves and the field that gives up its position. `ddl_version` rises when grammar or vocabulary is added, changed, or retired; Score `version` rises when the schema structure changes. `ddl_version` and `ddl_engine_version` count from 1. `MODEL_CONFIG_VERSION` rises when measurements, recommendation levels, or selectability change and applies builtin metadata to matching ids in a stored catalog. `web/APP_VERSION` is the single authority for `APP_VERSION`, read by the UI, `/api/info` `version`, and the CLI; the distributed version in `server/pyproject.toml` changes only for a release tag. `web/BUILD_NUMBER` is a shared serial that also moves for UI changes and is excluded from identity. Implementations and saved works own the current values. Record a new version's values, reasons, and results only in the [changelog](CHANGELOG.md). The [render engine version history](docs/spec/render-engine-history.md) preserves existing version records as historical material and receives no new sections.

Versions and identity IDs are separate namespaces. The work-edition ID is `rh3`, derived from `score`, `render_seed`, `render_wild`, the render engine ID and version, and `render_color_catalog_id`. `render_build_number` and the Score-side `vary_seed` are excluded from identity. Stored `rh2` remains legacy: it is neither recalculated nor compared with `rh3`.

Saved reference corpora remain comparison records for the versions they froze. Do not rewrite a frozen version's output, and retain its existing case IDs. At an explicit checkpoint after an overall migration is complete, perform one full update and record the difference from the prior version in its manifest. An intermediate render or DDL engine bump, or a rename alone, does not require a full corpus update, a current-version reference directory, or running a generator or manual comparison. Choose focused validation from the change risk. Render records remain SVGs; DDL records remain DDL text or JSON.

SVG fractional values follow the master grid defined by `MASTER_GRID_DECIMALS` and retain six fixed decimal places. The application has no mechanism to choose an old engine for replay: replay uses the latest engine, while a past edition is reproduced by returning its saved SVG. The version history retains the historical rationale and measurements.

A recorded engine version is provenance, not an input to replay. The UI reports when it differs from the current version. Reinterpreting DDL also uses the latest implementation and creates a new edition. Saved SVG, Score, seed, and edition ID remain intact.

PNG is derived from the canonical SVG. Reducing its size must not silently omit material or ground filters. Do not use `cairosvg`, which omits `feTurbulence`, `feDisplacementMap`, and `feGaussianBlur`; if the required rasterizer is unavailable, stop rather than fall back to a degraded PNG. Server and CLI use the resvg path in `shared/src/inku_analysis/rasterizer.py`; Android uses the shared native raster API in §12.14. This collects the PNG rule retained in the history and the current host connections without changing rendering semantics or execution paths.

DDL avoids words such as "beautifully" or "powerfully" in the core.  The system
should express such ideas through visible choices: number, placement, material,
line behavior, color, weight, and negative space.

---

## 3. Separating Core From Extensions

### 3.1 What Belongs in the Core

The core vocabulary is the eleven Saijiki categories plus **relations** (あいだ).
The vocabulary dictionary is called Saijiki, following the haiku term for a
seasonal word dictionary.  In inku, Saijiki is consulted rather than kept open
at all times.

The core vocabulary consists of twelve Saijiki categories plus relations. Its source of truth is the shared Rust asset `core/crates/inku-ddl/assets/saijiki-v1.json`; the Server Saijiki table and Web / Android displays follow the same vocabulary. The machine-generated reference dump (`GET /api/reference` / `inku-cli reference`) publishes the current values; the table below is an overview, and reference §1 decides additions and removals.

| English | Japanese | Vocabulary |
| --- | --- | --- |
| forms | かたち | circle, ellipse, triangle, square, line, arc, cloudform |
| touches | てざわり | silverpoint, pencil, pen, rotring, crayon, chalk, fine-brush, thick-brush, oil paint, burin, drypoint, computer |
| continuity | つらなり | solid, dashed, dotted, dash-dot |
| surfaces | おもて | empty, flat, pale ink wash, grain, stipple, hatch, crosshatch, aquatint, dense, faint |
| grounds | じ | paper, washi, ink-wash ground, charcoal ground, canvas, drawing paper, mezzotint |
| motions | うごき | place, line-up, draw, scatter, fill, tile |
| order | じゅん | alternating, in order |
| movements | ゆらぎ | fine, large, slowly, quickly, swaying, undulating, bleeding |
| relations | あいだ | along, not touching, cutting, between, touching, connected — with fixed phrases such as `along the previous line` and `connected to the previous shape` |
| places | ばしょ | top, bottom, center, left-edge, right-edge, top-edge, bottom-edge, start, end, partway, corner |
| angles | かたむき | horizontal, vertical, diagonal, rising, falling, rotated |
| proportions | わりあい | tall, wide, full-width, half-width, semicircle, waxing, waning, crescent |
| colors | いろ | white, black, blue, red, green, gray, yellow, orange, purple |

`left-rising` / `左上がり` and `left-falling` / `左下がり` are hidden markers that retain distinct left/right meaning for typed direct DDL and Macro references. They are not yet exposed in the Stage 1 prompt or Saijiki display, and the existing six displayed angle words remain unchanged.

In v1.92 the words 描く (ja draw) and 髪 / hair were removed from the vocabulary by the author's decision. In v2.7.9, 髪 / hair was replaced by 銀筆 / **silverpoint** — 0.5px, the least wavering line a hand can draw. Saved Scores that still say `hair` are rewritten to `silverpoint` as they load, so they replay unchanged in everything but the seed.

Pen, solid, empty, and black remain historical baselines for comparison with legacy Score / coerce behavior, rather than values inserted into typed meaning. When visible DDL omits a corresponding field, typed meaning remains `unspecified`; neither the parser nor semantic association fills it. The current subset resolves omissions only while lowering a lock-verified view to an actual Score: for count-one circle, square, ellipse, cloudform, triangle, and polygon instructions with a numeric position or an original `place:center` resolved to a verified direct `Instruction { instruction_index }` target, plus a place action, omitted count becomes one, touch becomes pen, continuity becomes solid, and an omitted closed surface becomes filled. An omitted color compares the actual work color-catalog background against actual black and white by absolute OKLCH L distance, choosing the farther color and black on a tie. Each explicit value wins independently, and neither these resolutions nor effective focus is written back into source meaning. Legacy Stop and OmitAndContinue inputs remain accepted, but a recoverable field or execution-unit failure uses shared local recovery: it records a typed diagnostic, omits only that unit, and continues with the remaining drawing. This rule does not retroactively change physical Renderer fallbacks or read compatibility for existing works.

Shape size is a finite local modifier owned by the typed DDL compiler, not Saijiki vocabulary. The current classes are `slightly_small`, `small`, `very_small`, `normal`, `slightly_large`, `large`, and `very_large`. Their Japanese ordinary/small/large surfaces and the corresponding English `normal-sized`, `slightly`, and `very` forms retain exact source spans. The grammar does not grow free-form degree synonyms or use source-substring post-processing.

Order specifies finite sequences of values of one attribute, such as color or material, or of shapes and groups. `Line up five circles, alternating red and gray.` produces red, gray, red, gray, red. `Line up eight, repeating a red circle, a blue line, and a gray arc in order.` produces circle, line, arc, circle, line, arc, circle, line. Alternating takes two entries; in order takes a nonempty list and preserves ordered duplicates. Line-up, scatter, tile, and fill use the explicit count as the total number of placement units, regardless of list length. Multiple entries without an order operator do not imply a cycle. An invalid sequence produces a local diagnostic while independent drawing continues.

A group is a noun phrase, such as a group of a red circle and a blue line, rather than a parenthesized command. `Line up five, alternating a group of a red circle and a blue line with a gray arc.` places five units: group, arc, group, arc, group. It draws three circles, three lines, and two arcs. Shapes inside a group do not multiply the outer placement count, but all contribute to resource demand. Group and Macro bodies retain their internal instructions. An over-budget outer placement is omitted before instances are produced, while later drawing continues. Group is grammar and adds no Saijiki category or chip.

Japanese accepts the counter つ for one through nine, the count ten as `10`, `十`, or `とお`, and 個 forms such as `1個`, `2個`, `10個`, and `11個`. `10つ` and `11つ` are not count expressions. The Japanese sentence `赤い円と青い線の組を、灰の弧と交互に5つ並べる。` has the same five-unit meaning as the English example.

Color sequences retain the shared Score `Arrangement.color_cycle`. Other sequences retain complete member templates in existing placement or fill groups and select them in order using Score 0.14 `cycle_members.occurrence_count`. Each placement starts at the first entry. Saved works retain their smallest required Score edition, existing resource limits, and omitted-count rules. Repeating and group phrases are ordinary grammar, not additional Saijiki entries.

Canvas format is neither vocabulary nor a plugin. It is a resolved host option owned by the shared-core `inku.canvas-format-registry.v1`. Its eleven formats are `square` / `golden` / `a4` / `b4` / `pillar` / `oban` / `wide` / `byobu` / `vertical` / `sd_monitor` / `hd_monitor`, and it is not written into visible DDL or macro definitions (§19).

**Properties of the core:**

- vocabulary of physical material only (zero words for feeling)
- centered on the act of *placing* rather than the act of *drawing* -- the
  sense in which a bonsai branch is "placed"
- the design of the motion vocabulary matters most: place, line up, fill --
  these are the verbs of presentation
- **the movements category describes irregularities in marks**: "swaying finely",
  "undulating slowly", and "bleeding" are allowed; "swaying beautifully" and
  "swaying violently" are excluded (§13 has the detail). English amplitude words may be written as
  adjectives (`fine`, `large`) or adverbs (`finely`, `largely`). Because
  amplitude `large` is spelled like the relative size `large`, use `largely`
  when a size also appears in the same phrase (DDL 12)
- **the relations category holds observable relations only**: "along" and "not
  touching" are positional relations an outside observer can verify. Words of
  intent or personification, such as "nestling against" or "answering each
  other", are excluded (§14 has the detail). This is the addition of a
  predicate (syntax), not of vocabulary (nouns), so it does not contradict
  plugin principle 1
- **the surfaces category holds state nouns for surfaces and marks**: use a
  noun such as "flat", not the act of painting. Its two dimensions are **quality**
  (empty, flat, pale ink wash, grain, stipple, hatch, crosshatch, aquatint) and
  **density** (dense, faint). Density is relative to the tool, not an absolute
  darkness. Paper grain belongs to the support (the grounds category). Grain and
  wash remain applicable to lines and arcs: grain raises support absorption and
  tooth, while wash changes no sheet properties and produces a pale band at
  three times the width and 0.35 of the opacity. The other six qualities move
  to the preceding closed shape and are dropped when there is none. On a closed
  shape, an explicit wash, grain, stipple, hatch, crosshatch, or aquatint is
  itself the area's performance and adds no flat base fill beneath it (DDL
  engine 46). A flat fill comes only from an explicit flat surface or the
  omitted-surface default of a closed shape. Current
  bleeding is independent movement vocabulary, not a surface quality. An
  instruction to fill the background is not about a surface** either; it goes to
  the document-owned `background` field. The finite form is `fill [the]
  background with <abstract color>.` When a clause has a background marker but
  its color head or background action does not resolve, its exact source span
  and reason remain a local diagnostic instead of being replaced by a missing
  canonical identity. No word is coerced to another color or background form;
  resource-aware execution may omit only that clause and continue independent
  drawing. `fill` densely fills a surface or region;
  `scatter` distributes elements irregularly; and `tile` covers a region by
  arranging shapes regularly and repeatedly. These movement meanings are
  distinct and are never substituted for one another. A typed fill plan targets
  the whole canvas, an existing named area, or one inline closed primitive and
  retains dense irregular placement and its clipping recipe within that region,
  plus the target's source owner, geometry, and count provenance. Omitted
  count is `ceil(A / d²)` and explicit count is retained. A mixed-count group
  distributes the remaining area using the omitted kinds' mean `d²`, nearly
  evenly with source-order remainder and a minimum of one for each omitted
  kind; an all-explicit group performs no density calculation. A Macro is one
  motif whose reference footprint retains its body, internal counts, and inner
  Transform while excluding outer count, seed, material, instruction angle, and
  performed-relation translation. Invalid targets receive local diagnostics
  while independent drawing continues. The resource-aware compiler stores this
  as compact Score 0.10 `fill_groups`, without sampled instance coordinates,
  retaining owners, namespace-scoped ordinals, count origin, target geometry,
  boundary, and sampling recipe. Counts and shapes remain exact; procedural
  filter / pattern count approximation is rejected, while filters may express
  material appearance. Display and Editable clip after appearance. Compat uses
  neither filters nor `clip-path`; it clips the whole group to bounded geometry.
  A clip failure omits the complete source or coordinated group, never a partial
  count, and independent later drawing continues.
An explicit source background takes precedence over host context while lowering
to Score. An omitted background or a conflict between multiple backgrounds uses
the context background; only the conflict records a local diagnostic. `draw`
delivers line and arc through the shared geometry, count, and place resolvers
exactly once. An omitted source position remains None; the shared resolver
chooses a performance-time position from the existing-sway central region
`[0.39, 0.39, 0.61, 0.61]`. Explicit positions and explicit-center Stage 1.5
focus take priority. `inku.geometry-resolution-policy.v1` records omitted
placement and fill meaning; its current digest is
`5ce5ec570f913090bec92a9fc2802dfc7c322e866ed965a8486f52f17cb09a56`.
Single objects, Macros, and coordinated groups share the omitted central
region, including the exact domain used for tiling. Fill's omitted target
remains the whole canvas under its separate rule. A valid ground alone is
drawable content in both Score and Plan; omitting another invalid drawing
instruction preserves that ground and its diagnostics.

A background color alone is not drawable residual content. When an omission
leaves neither an instruction nor valid ground, execution stops instead of
saving or delivering an empty Score with its background as an omitted success.

  The current vocabulary keeps `stipple` in surfaces as 点描 and moves `bleeding` to movements. It is independent `ink_spread:"bleed"`, so it can combine with Wave, Perlin, and stipple without creating Perlin or an intensity by itself. Legacy `blurring`, `trembling`, and `middle` input normalizes to `bleeding`, `swaying`, and `center`. Saved Scores retain the old rendering meaning of `surface.texture="bleed"` and `variation.quality="pink"`; editing or regenerating creates a new variation.

- **the grounds category holds the names of supports** (added 2026-08-15, render
  engine 34): **paper, washi, ink-wash ground, charcoal ground, canvas, drawing
  paper, mezzotint** -- the seven values of `canvas.ground.material`. **Where
  surfaces says how the inside of a closed shape is, grounds says what the
  canvas itself is**, and a description names it as a sentence of its own, such as “washi.” or
  “ink-wash ground.” Headed forms such as `Ground: ...` and `Surface: ...` are
  not accepted (2026-09-24); a surface quality is written as a modifier of its
  shape, as in “a pale ink wash circle”. **All seven are tiled as a `<pattern>` and use no
  `<filter>`, so the three SVG profiles emit the same ground.** **The cost limit
  is the byte size of the ground layer (24 KB), not a count of elements.**

`Random` is not forbidden as an author word.  The restriction applies to internal normalized DDL and JSON Score: unordered placement must be interpreted into observable placement such as dotted across the whole canvas, scattered, varied, top-to-bottom, or along a trace.

The core color vocabulary is the nine abstract colors that authors can write: white, black, blue, red, green, gray, yellow, orange, and purple. Color catalogs are server-owned metadata that change how those nine colors are resolved at render time; they are not vocabulary extensions. **Yellow, orange, and purple were added in v2.9.11.** Catalog `palette` entries already carried twelve yellows, a nominal 13.6%, yet yellow reached only 0.6% of what was actually drawn: there was no word to leave by. The three are peers of the other abstract colors, and `color_hint` remains the place for nuance that no abstract color holds. **From v2.9.12 (render engine 17) the nine are assigned deterministically from the catalog's `palette`, once per work**, from `(render_seed, catalog_id, abstract color)` and nothing else: the six chromatic words by OKLCh hue band (CIELAB cannot separate blue from purple), the three achromatic roles by reserving the hex that equals their own `map` value and then taking the nearest lightness. The background goes through the same assignment, and `color_hint` now acts only as a table that names a band (ASCII matched on word boundaries).

Colors in JSON Score are abstract color names.  Rendering resolves them through
the selected color catalog.  The server is the source of truth for color
catalog definitions and exposes them through `/api/color-catalogs`; clients
select a `catalog_id` rather than owning their own catalog tables.  When user
instructions include color nuance, the system may preserve `color_hint` so
Stage 2 and rendering can resolve the best catalog color without losing intent.
The default catalog is a neutral baseline, not a cultural default.  Catalog ids
use material-, light-, and technique-based names: `ink_season`, `fresco_study`,
`open_air_light`, `ink_porcelain`, `cool_material`, `dye_earth`, `vivid_material`,
`weathered_heritage`, `sea_stone`, `moss_bark`, `neon_plate`, and
`lantern_dew`.
Catalog `map` values must preserve the meaning of the nine abstract colors;
stronger identity colors belong in `palette` rather than replacing structural
colors.  Since v2.9.14 (render engine 18) every catalog carries a nine-key
`map`, and each of those nine names a color from that catalog's own `palette`.
A catalog holds exactly three achromatic and seven chromatic `palette` colors, so
a description that asks for a band is answered from that band rather than from
the nearest hue the catalog happened to hold.  One band is left empty on
purpose: `sea_stone` holds no purple and answers with its `Night Sea`, which is
also its blue.  **From v2.11.11 the canonical colors for redrawing a stored
work are the ones the work itself recorded**: when a request names a work (the
`work_id` field of `/api/render-svg` and `/api/render-score`, or the CLI's
`--from-work`), the server draws from that row's `render_color_map` and never
reads today's definition of the catalog.  **A renamed catalog and a retired one
both draw** this way, because the id is never resolved and so cannot answer 422.
An older work that recorded no colors falls back to the current definition, and
that fallback does not answer 422 either.  A request that names no work behaves
as before: a retired catalog id resolves to nothing rather than to the
default, so a drawing that asks for one is drawn with the default catalog.  The Build 265 review leaves
`open_air_light`, `dye_earth`, and `desert_mineral` (retired in v2.9.14) as
known tuning targets:
their dark backgrounds, high-chroma accents, or paper/sand tones can dominate
quiet prompts, so future tuning should adjust core brightness and saturation
instead of branching into prompt-specific exceptions.
Build 266 lightens those three catalogs' core colors to reduce background and
dark-color dominance.  Catalog `sub` remains the English UI description, while
`sub_ja` carries the Japanese UI description.  `palette` color names use `name` as
the English canonical label and may include `name_ja`; the Japanese UI displays
those entries as `English（日本語）`, while the English UI displays `name` only.

Render JSON produced by the server records the concrete render context.  Paint,
compose, the JSON tab, and saved artifact JSON include the resolved
`stage1_model` / `stage2_model` that were actually used, plus
`render_build_number`, `render_color_profile`, `render_engine_id`,
`render_engine_version`, `ddl_version`, `ddl_engine_version`,
`render_canvas_aspect`, `render_hash`,
`render_hash_short`, `render_color_catalog_id`, `render_color_catalog_name`,
`render_color_catalog_sub`, `render_color_map`,
`instruction_lang_requested`, `instruction_lang_resolved`, `ui_lang`, and `render_seed`, where
abstract colors and `palette:<name>` entries are expanded to the exact
`#RRGGBB` codes used for SVG rendering.  `ddl_version` and `ddl_engine_version`
name the DDL layer that decided the picture; a render response always carries
both, and among saved works only rows written before those versions were
recorded lack them. A resource-aware Score 0.10 performance also records
`resource_execution`: demand recomputed from the Score, complete atomic units
omitted for budget excess, their causes, and relations omitted with a missing
target. The current engine metadata is
`render_engine_id: "default"` and
`render_engine_version: "61"`.  The full catalog `map` / `swatches` / `palette`
snapshot is not duplicated in render JSON because `render_color_map` is the
concrete color record needed for replay and audit.
`render_hash` is the work-edition identifier; what it is derived from, and why
the build number and the Score-side seed stay out of it, is in "Separation From
the Render Engine" below.
`score.canvas` remains the score-level canvas instruction, while
`render_canvas_aspect` records the canvas aspect actually used for this rendered
artifact.  From v2.13.14 the two may disagree: Stage 2 is told which paper it
composes for, and what it declares is kept as the record of what the composition
was built for, while the paper actually performed on rides in
`render_canvas_aspect*`.  Works saved before that version carry the requested
aspect in both.  A redraw reads the performed paper from the work's row, so an
old work redraws exactly as it did.
`render_canvas_aspect_id` is the explicit canvas aspect identifier for new
metadata, and `render_canvas_aspect_ratio` records the actual rendered
width/height ratio as a number.  `render_canvas_aspect` remains for
compatibility; old records can be backfilled in responses by deriving the new id
and ratio from it.

### 3.2 What Is Separated Out as an Extension

- the **Nature plugin** (rain, leaves, water, wind, and the like)
- concrete vocabulary such as a **bamboo extension**

**The principle: do not pollute the core.**  Every concrete or culturally
specific vocabulary is offered in a form that can be added as an extension.

---

## 4. Plugin Model

In this section, a plugin means a data-only **vocabulary macro** invoked explicitly from a visible qualified term such as `Nature.雨`. It is not an external code hook. Canvas is a shared-core host option and a Render Engine Pack replaces the drawing core; neither is a plugin in this sense.

### 4.1 Why the Plugin Model Is Designed From the Start

DDL designs the plugin mechanism **from the beginning rather than adding it
later**.  The reasons are:

**To keep the core pure.**  Concrete vocabularies such as the Nature plugin
(rain, leaf, water, wind) are already ruled out of the core.  That ruling assumes
that a plugin mechanism exists from the start.

**To make the boundary with the core explicit.**  What is core and what is
extension.  If that line is drawn late, the line itself becomes vague.

### 4.2 The Emacs Lisp Lesson

Freedom in a plugin system cuts both ways.

**The cost of free extensibility like Emacs's**
- the boundary between core and package is vague
- packages collide with each other
- the core itself swells as extensions pull on it
- the learning curve differs per person, which weakens it as common ground

### 4.3 Five Principles

**Principle 1: a plugin is limited to a macro over vocabulary.**
It cannot add a new primitive.  It cannot add new syntax.  It only names a
combination of existing core words.

**Principle 2: a plugin cannot change the core.**
No plugin can rewrite what "place" means.  Core vocabulary is immutable.

**Principle 3: a plugin is referenced explicitly.**
It carries a namespace, as in `Nature.雨`.  The bare vocabulary space stays
unpolluted, and whether a plugin is in use is evident from the description.

**Principle 4: a plugin stands alone.**
Plugin A may not depend on plugin B.  With no chain of dependencies, installing
and removing are independent acts.

**Principle 5: the core alone can write it.**
Every plugin expands into semantic nodes composed only of core meaning. A plugin
is shorthand, not a new capability.

### 4.4 Ownership of Canvas and Vocabulary Macros

The canonical owner of Canvas is the shared-core `inku.canvas-format-registry.v1`, not a vocabulary plugin or a system plugin. Canvas selection is a resolved host option outside visible DDL and MacroInvocation / MacroDefinition. The same DDL can be used on different canvases. A host boundary with no selection may choose `square` as its host default, but that does not mean the DDL compiler inserts `square` as a semantic fact. The host carries the selection through Score / render context / history, and the Renderer resolves SVG `width`, `height`, and `viewBox` (§19).

The current runtime's `plugin_storage["canvas-aspect"]`, `canvas_aspect` request alias, stored `Score.canvas` / `render_canvas_aspect*`, system / user plugin directories, and plugin-status / enable controls remain as legacy compatibility operations. They permit reads as well as updates to legacy plugin documents and enabled state. That does not make them semantic authority or a new MacroDefinition authoring / loading API. Storage and API compatibility remain for saved settings and catalog discovery; they do not execute the old semantic decision layer. If Stage 2 receives canvas through the current compatibility path, it is host-resolved composition context, not visible-DDL metadata. It does not rewrite DDL coordinates, words, or canonical meaning.

### 4.5 Expansion Through MacroDefinition

A vocabulary plugin is a data-only macro that gives a name to a combination of core vocabulary. A visible invocation uses `Namespace.Heading`, as in `Nature.雨`; definition version / canonical digest, document / compiler identity, and source / generated provenance are stored in a sidecar lock rather than authored as DDL metadata.

Every domain uses the single versioned `inku.macro-definition.v1`. There are no domain-specific Tree / human / water grammars, per-plugin parsers, or plugin code. The compiler resolves and locks the visible invocation, binds closed typed parameters, then performs late expansion without an LLM into semantic nodes from the attested composition seed and caller-owned finite bounds, rejoining ordinary typed lowering. The Renderer does not understand plugins; it receives only the later ordinary Score. On the Description path, Stage 1 may receive only a bounded signature, parameter schema, and short summary; MacroDefinition bodies and expanded DDL are not sent to Stage 1 or Stage 2 prompts. An unknown or ambiguous qualified term in direct DDL is an explicit error, not a hidden LLM fallback.

Inline and continuation forms that resolve uniquely to the same subject and explicit instructions have the same source-independent canonical meaning. With the same drawing conditions, policy / definition identity, attested seed, and explicit variation, surface sentence splitting or anaphoric syntax alone does not change a macro seed, focus, or effective meaning. Unknown, ambiguity, and conflict are not guessed equivalent; meaning-bearing relations, order, quantity, attributes, actions, parameters, and genuine multiple macro invocations remain. This rule does not guarantee general word-order exchange or graph isomorphism.

Meaning bound to a declared parameter is read from the expansion result. Attributes left on the outside of an invocation become source-owned diagnostics without reimplementing parameter binding. When OmitAndContinue omits only an unbound appearance field, existing color, touch, continuity, and surface values in the MacroDefinition remain. Unused parameters stay accepted; this adds no parameter defaults, optional parameters, or new whole-invocation conversion semantics.

At this boundary the Renderer needs to know only core meaning, while a plugin cannot add primitives or syntax or rewrite core semantics. Plugins cannot depend on other plugins, so installation and removal remain independent.

### 4.6 Generic MacroDefinition v1

A Transform containing only Anchors uses the center of their resolved bounding box. A single Anchor is its own center. When drawable shapes are present, the existing combined drawable-shape bounding-box center is used, and Anchors follow the same transform.

The current consumer accepts rotation plus `scale_x` / `scale_y` and `translate_x` / `translate_y`. Only finite values are accepted; negative scale reflects and zero scale degenerates. It transforms child geometry only: scale about the exact combined child bounding-box center before rotation, rotate about that same center, then translate by a normalized-canvas-axis delta. Shape geometry and spacing change while stroke width and grain pitch remain fixed. General affine transforms compose inner to outer. If placement is determined during performance, that placement resolves before the bounding box is computed. A `group` is transparent structure that carries the range, references, and ownership; it creates neither placement nor a drawing instruction.

Transform reaches both count-one actual Scores and compact repetition recipes. Score 0.5.0 `transform_groups` retains the range, rotation, scale, translation, and original instruction indices of numerically fixed members. Rotation-only Score 0.4.0 groups, saved 0.1.0 / 0.2.0 / 0.3.0 Scores, and versionless artifacts retain their existing compatibility. An empty group list stays off the wire; `surface_intensity` is valid from Score 0.3.0 onward. The shared lowerer selects the minimum Score version required by the representation: flat compatibility without an explicit path connection remains Score 0.9, resource-aware compact recipes start at Score 0.10, and only works carrying a mirror relation require Score 0.15. Score 0.8.0 direct `placement_groups` place one contiguous source-order member range once. Each Macro is one placement member, retaining its body positions, internal counts, Transforms, Anchors, and ownership ranges. Outer Macro repetition is stored separately in `repetition_groups`, so inner and outer counts and ordinal namespaces do not collide. Group-level repeated actions reach compact recipes under the count rules below. Omitted internal placement uses `overlap`, which aligns bounding-box centers; explicit “place in a row” retains `horizontal_source_order`; explicit “overlap” uses `overlap`; scatter and tile use `scatter` and `tile`. The group bounding-box center moves to one named region resolved from the performance seed, retaining each member's owner, count, seed, and geometry. An omitted line-up count is one for every member. Scatter and tile preserve explicit counts and divide the remainder up to a total of eight evenly among omitted members, assigning any remainder to earlier omitted members in source order. Each omitted member receives at least one, even when explicit counts plus those minima exceed eight. The same rule applies when all counts are omitted: nine listed kinds receive one each. Fully explicit counts are not topped up to eight. Line-up and place assign one only to omitted members. External Connected, Touching / Along / Cutting, and NotTouching / Between attempt one whole-group translation while retaining transformed geometry, direction, and named or numeric placement authority. NotTouching retains the existing gap and Between the existing recipe based on the two prior bounding-box centers. Failure records an error, removes only the relation, and leaves the group at its original transformed placement. Numeric fixed members, legacy Stop input, and owners, original indices, seeds, and lost references retain their rules. `compile_ddl_to_score_with_resources` and `render_with_resources` are the shared-core entrances used by the normal Server, Web, and Android paths. Saved Score and history retain the format compatibility needed for reading and replay.

An Anchor is a non-drawing reference point for line connections, with an explicit `place` or paired `position_x` / `position_y`. Anchor `place:center` means the canvas center (0.5, 0.5), without borrowing an Emit's focus-dependent placement. Other named positions use the existing placement regions. Score 0.6.0 stores `anchors` separately from drawing instructions, and `target_anchor_index` names a Connected target. Original references, ownership, drawing order, and seeds remain intact; Anchors follow the translation, scale, and rotation of their enclosing Transform. Numeric-position authority and legacy Stop-input compatibility remain, but a recoverable relation failure records an error, removes only its relation, and does not stop drawing. A missing position is not filled from nearby shapes or the invocation position. Saved Score 0.1.0 through 0.5.0 and versionless artifacts retain their compatibility.

A Macro Connected relation may name a prior Line as `from` and explicitly provide a numeric `target_path_position` expression. Its finite value lies from 0 to 1: zero is the Line start, one its end, and intermediate values interpolate uniformly by sample order along the performed centerline. The Line need not be immediately adjacent; its original reference within the Macro is retained. The connected source follows existing position authority and aligns its endpoint with that point. Connection resolution and final rendering share the same centerline, including variation, and common outer transforms move it together with the attached source. The numeric field alone selects Score 0.11.0. A `target_endpoint` or `ink_spread` selects 0.12.0; the `"interior"` selector described below selects 0.13.0. With none of these fields, outputs retain flat 0.9 or compact 0.10. Flat 0.11 does not require a resource snapshot, while compact 0.11 retains the existing caller-owned resource contract. General Along, adjacency for Connected without a path position, and Touching closure remain unchanged. Invalid or omitted targets produce a diagnostic and remove only the relation while other drawing continues.

Ordinary DDL accepts `connected/connects to [the] start/end of [the] [previous] line/arc` to select only the target endpoint of an existing previous reference. The current shape always uses its canonical start, preserving Line from→to and Arc angle_start→angle_end identity. The existing endpoint-free connection remains prior end to current start. `target_endpoint` and `target_path_position` cannot coexist. A Score carrying `target_endpoint` or `ink_spread` uses at least 0.12, or 0.13 when it also carries an interior selector. Existing fields in versions 0.9, 0.10, and 0.11 keep their prior meaning.

Ordinary DDL accepts `connected partway along the previous line/arc` to join the current start to a point on the prior Line or Arc, excluding both ends. `partway` belongs to places and is not an alias for center. Score retains `target_path_position:"interior"`; performance chooses a position strictly inside the path using the existing instance identity and performance seed. The same Score and performance seed reproduce the same contact on the actual varied centerline, including outer rotation, reflection, and translation. This does not align tangents or resize the shape. Macros use the same `target_path_position:"interior"` selector. Only works carrying this string require Score 0.13. Existing numeric expressions and numeric Score positions retain their Line-only 0–1 range and interpolation. Combining the selector with an endpoint or targeting an anchor is an invalid relation.

`Mirrored with the previous shape` belongs to relations: the two shapes have mirrored positions and orientations across the axis between them. It applies to a complete Macro, such as a leaf, or an ordinary group as well as a single shape. The axis is the perpendicular bisector of the two positions resolved by existing placement. The target and follower positions stay fixed while omitted follower dimensions and overall orientation are resolved from the reflected target. Explicit shape, dimensions, direction, color, tool, and surface remain authoritative. Incompatible corresponding shapes or explicit facts, or coincident positions with no defined axis, produce a diagnostic and remove only the relation; other drawing continues. Inner layouts and transforms precede mirroring, followed by shared outer transforms. Explicit outer nonuniform scaling remains in force without another reflection of the final image. Each shape retains its own performance seed for material variation. Only works carrying the new `mirror_relations` require Score 0.15. The relation refers to existing standalone instruction, standalone Macro repetition, placement member, or placement group boundaries.

Fluctuation parameters keep asset category `variation` and may constrain candidates with an optional closed `dimension`: `amplitude`, `frequency`, `quality`, or `spread`. For example, `{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`. Other categories cannot specify a dimension. Omitted / None preserves legacy category-only matching and canonical bytes / digest; Some participates in the definition digest. Flat Emit uses `fluctuation_amplitude`, `fluctuation_frequency`, `fluctuation_quality`, and `ink_spread`, each carrying an existing `SemanticRef { category: variation, id }` from its dimension. A field name does not change semantic identity. Definition validation, component `use`, binding, and execution boundaries share the same seven-word current classification.

A saved MacroDefinition may retain legacy `variation:trembling` or `variation:blurring` IDs. Each keeps its existing canonical bytes, digest, and lock and continues to resolve to Perlin or Pink respectively. Legacy `place:middle` retains its existing canonical identity shared with `center`. This is shared saved-format compatibility, without a plugin-name branch or a restored public vocabulary entry. New definitions use canonical `swaying` or independent `ink_spread:bleeding`, and body changes receive a new definition version and digest. Saved configs are never rebound to the current catalog definitions.

Every declared parameter remains required. Declaring three parameters and supplying only one value produces a binding error such as MissingCompatibleFact. Declaring only an amplitude parameter and delivering it to Emit lets the same resolver in §13.6 resolve the other two slots. Undeclared caller overlays, guessing three slots from one generic variation field, and optional parameters are not introduced.

`inku.macro-definition.v1` has closed typed parameters, definition-local `components`, and only the shared operators `emit`, `use`, `group`, `anchor`, `relation`, bounded `repeat`, typed `transform`, and deterministic bounded `vary`. It forbids arbitrary code, I/O, unbounded loops, recursion / component cycles, filesystem / network / clock / environment access, external-macro dependencies, and generation of raw SVG / Score / Renderer instructions. Expansion is effect-free and returns deterministic semantic nodes with source / generated typed provenance from the attested composition seed and explicit bounds.

A finite cyclic selection is written as `{"expr":"cycle","items":[{"expr":"integer","value":1},{"expr":"integer","value":2}],"index":{"expr":"local","name":"i"}}`. A non-negative integer index wraps by the list length and selects one item from a homogeneous list. Empty lists, mixed types, and non-integer indices produce definition diagnostics; negative runtime indices produce evaluation diagnostics. This preserves the repeat count, including odd counts, while expressing alternating colors or ordered positions. The selected value retains its exact-decimal or semantic-ID type and canonicalization and is evaluated within the existing budget. It introduces no new randomness, general arithmetic, or external effects.

Exact decimals use a closed typed expression such as `{"expr":"exact_decimal","value":"0.240"}` and the same ExactDecimal representation as ordinary DDL. The original definition retains its spelling; canonical identity normalizes `0.240` and `0.24` to the same value. Existing `number` / `Number(f64)` meaning and definition bytes remain unchanged, and exact values are never reconstructed from f64. Literals, declared parameters, locals, components, and finite choices preserve the exact type. This adds no general arithmetic or implicit conversion into numeric ranges or transforms.

Declare a parameter with, for example, `{"type":"exact_decimal","dimension":"radius"}`. The optional dimension is closed to `radius` / `diameter` / `length` / `side` / `width` / `height` / `chord` / `sagitta` / `position_x` / `position_y`. Binding matches explicit caller dimensions and values uniquely and completely; parameter names imply no meaning. An omitted dimension matches only a standalone number without a dimension. A clause mixing an ordinary primitive with an exact-parameter Macro retains the existing unsupported numeric-ownership boundary and reports an ambiguous assignment; separate clauses are unaffected. Compound width/height, chord/sagitta, and X/Y facts transfer only when every component binds to the same invocation, retaining the original keyword and decimal provenance.

Flat Emit fields with those names accept exact values. `width`+`height`, `chord`+`sagitta`, and `position_x`+`position_y` require both components; missing or mistyped values produce diagnostics. Numeric position and named `place` have separate authority and cannot silently overwrite one another. Dimensions and positions reach the ordinary DDL resolver, including diagnostic recovery to the smaller overlapping size. Definition literals belong to their generated Emit and do not receive fabricated source spans. Count-one/place reaches actual Score; repetition reaches the resolved plan and leaves instance generation to later materialization.

The current finite consumer that reaches an actual Score projects each complete `emit` as one instruction into the same semantic input used by ordinary DDL. It also traverses nested `group` containers that carry no placement or transform in their original order, retaining generated ownership and reference IDs already resolved in lexical scope. A Group does not create placement, coordinate transforms, or drawing instructions of its own. `shape` is limited to `line` / `circle` / `ellipse` / `cloudform` / `square` / `triangle` / `polygon` / `arc` / `point`, `movement` must explicitly be `place`, and `place` accepts `center` with its exact generated focus target, or the explicit `top` / `bottom` / four edges / `corner` regions in §18. `color` / `touch` / `continuity` / `surface` / `angle` may carry an existing ID from the category of the same name; omission uses the ordinary lowerer's same defaults. Angle uses the same resolver; Point rejects an explicit angle because it has no orientation. `thinness` accepts `fine` / `extra_fine`, and `relative_scale` accepts the closed core values `slightly_small` / `small` / `very_small` / `normal` / `slightly_large` / `large` / `very_large`. Size uses ordinary DDL normal geometry and its existing factor exactly once, keeping explicit `normal` distinct from omission. `count` reaches the current Score only when omitted or `Integer(1)` and `Number(1.0)` is not treated as equivalent. The consumer adds no field aliases or raw Score fields and does not recover decimal meaning from an `f64`.

The macro head is joined exactly across its source instruction slot, source invocation ordinal, locked definition, and expanded invocation. Only `place:center` uses the effective focus at `MacroEmit { invocation_ordinal, expansion_path, generated_ordinal, field: place }`. Multiple complete Emits replace the head in their existing order as ordinary instructions; an origin through `use`, bounded `repeat`, or `vary` is not itself a rejection. Output instructions correspond in order to either a direct source slot or generated provenance. Adjacent bound Emits in the same Macro and original generated order deliver `connected` / `touching` through the same checked relation rules as ordinary DDL, preserving original reference order, ownership, and numeric-fixed or named-movable position authority. Touching joins both Line / Arc endpoints with the existing Arc reconstruction and fixes explicit relative scale (including normal), dimensions, and chord direction. `not_touching` and `between` also reach the shared checked performer from adjacent bound Emits in the same Macro. NotTouching retains the existing Medium gap, while Between retains the existing recipe using the bounding-box centers of the current Emit's immediately preceding Emit and the Emit before it. Named and noncenter placement is movable; numeric placement is fixed and is never overwritten. Between's `from` is the immediately preceding Emit, with the one before it retained as its second reference and with both owners preserved. `along` / `cutting` also reach the same checked performer from adjacent bound Line Emits, using named-movable or numeric-fixed position authority and the direction/dimension rules in §14.4. Adjacency includes unbound Emits in the original order, and an omitted from or either Between reference never retargets to a survivor. Regardless of legacy Stop or OmitAndContinue input, an incomplete Emit, unknown key, category or type mismatch, unbound caller fact, or expanded unsupported Transform axes / an unpositioned `anchor` / unsupported `relation` omits its established minimum field, Emit, subtree, or invocation with a diagnostic and continues the remaining Score. Unrelated siblings, including those inside Groups, remain in source and generated-provenance order. A missing reference omits only the relation while retaining its original dependency and any independently drawable Emit; it never retargets to a survivor. No child Emit is extracted from an unsupported structural subtree, and adjacency is not created across an unsupported subtree. An unused parameter or unreferenced Emit binding ID alone is not rejected.

An unbound caller action does not omit the entire Macro invocation. Only the outer action is omitted as `macro_caller_field { field: action }`, retaining its original owner, spans, and reason while preserving the definition's Emits, transforms, counts, order, seed, and provenance. The outer action is neither distributed into the body nor interpreted as a different action. This does not grant unconditional recovery for other unbound caller fields; exact-join integrity failures and the absence of drawable residual content still stop execution.

Repeated Direct and Macro plans retain checked Connected, Touching, Along, and Cutting intents symbolically, including the verified original target and position authority. This does not materialize instances.

Macros execute in invocation order after meaning resolution. A mention used only for anaphora does not execute twice or shift the semantic ordinal of a later macro. Source occurrence ordinal remains separately for ownership and provenance. The original sentences and rhythm, source spans, continuation edge / target, all bindings, and source / generated provenance are retained and verified. A full compiler-lock digest that includes them is an attestation of source integrity; equivalent expressions need not have the same digest. Source-record differences do not enter meaning selection, while source alteration is rejected.

The old `.inku-plugin.md`, `fires_on`, localized expansion templates, and old Stage 1.5 / Stage 2 expander are retired as the semantic canon for new plugins. The compatibility importer returns a `legacy_plugin_format` warning and a per-macro `Imported | Omitted` outcome instead of failing the whole application. Old works prefer their stored Score / expanded artifact; the old expander is not a permanent fallback. An `Omitted` macro with no artifact must not silently render partially or turn into a different figure.

The shared Rust compiler foundation exists through parse / validation / identity / lock / binding / deterministic expansion and carries the finite Emit subset above, including placement-free Groups, through the ordinary lowerer to an actual Score. The normal Server, Web, and Android runtimes and bundled package catalog are connected. An arbitrary user-package loader remains unimplemented. `PLUGIN.md` is the current authoring guide governed by this section; it must not treat an unimplemented loader or directory-addition procedure as authority.

Visible source thinness and size bind only a unique complete assignment to parameters explicitly declaring the matching `SemanticRef` category. Size uses the existing modifier-before-head syntax, also recognizing a qualified Macro head. Core values carry no Saijiki asset metadata; their original span, clause, atom, parameter, and definition remain attached, and ordinary entity modifiers do not consume them again. Literals, outer parameters, and definition-local component parameters rejoin the same Emit fields and ordinary lowerer. Missing or ambiguous binding follows the existing upstream error policy; undeclared caller facts follow the existing lowering policy. A bound parameter alone does not become a new continuation predicate, and undeclared attributes do not automatically overlay or fan out. Source or owner integrity failures stop both modes.

### 4.7 Separation From the Render Engine

A vocabulary plugin is a macro over core vocabulary; it is not a way to replace
the drawing core.  The drawing core carries a heavier responsibility and is
treated separately, as the **Render Engine**.

A render engine is the boundary that takes `JSON Score + render options +
server-owned color metadata` and returns `SVG + render metadata`.  In the
current server runtime, `renderer.py` is an SVG-only compatibility facade over
the default engine; a thin adapter sends one request containing the validated
Score and resolved options to the native `inku_render` binding.

The deterministic rendering core is the Rust crate `core/crates/inku-render`.
Server uses the native wheel and Android uses JNI to reach the same core.
The iOS host connection remains separately pending.

The canonical metadata format read by history, the JSON tab, the CLI, and the
benchmarks stays stable.  `render_hash` is the work-edition identifier; SVG
text, input text, normalized DDL, and raw LLM responses are never part of the
hash payload.

**The current form is `rh3:<sha256>` (v2.4.5).** Identity is derived from the saved canonical JSON Score, `render_seed`, `render_wild`, the render engine's ID and version, and `render_color_catalog_id`. **`render_build_number` and the Score-side seed (`composition_seed`, called `vary_seed` until v2.8.0) are excluded.** The build number is whatever sits in `web/BUILD_NUMBER` and moves for UI-only changes, so it gave a new edition ID to a drawing that had not changed by a single byte — a false difference. It stays as provenance metadata and leaves the definition of identity. The Score-side seed is redundant: a different Score already yields a different ID.

> **The key name `vary_seed` in the legacy `rh2` material stays frozen** (v2.8.0). **The material of an identity ID is not its name** — changing the characters of the key would rebuild the `rh2` of every saved work. The value is taken from the renamed `composition_seed`.

**`render_wild` joined the material in engine 12; the format name stays `rh3`.** Extending the material does make a separate hash space, but **`render_engine_version` sits inside the same payload**, so a value computed under the old material always contains `"11"` or lower and one under the new always contains `"12"` or higher. The two can never coincide, so no `rh4` is needed. **This argument holds only because the engine version moved at the same time; the material must never be extended on its own.**

**`rh2` (v1.60 through v2.4.4) is retained as legacy and never recalculated.** Stored `rh2:` rows keep their values and no destructive migration runs, matching how the earlier 64-character hex hashes were left in place. **`rh2` and `rh3` are separate hash spaces and must not be compared to decide whether two works are the same edition.** The startup backfill writes `rh3` only for rows whose `render_hash` is empty. `render_hash_short` — the four-character uppercase suffix used in the UI and CLI — is unchanged across both forms.

Loading arbitrary external code is not implemented at this point.  The internal
boundary and the metadata record come first; distribution format, safety, and
dependencies get designed once a second real engine is actually needed.

### 4.8 Retired

### 4.9 Reference Vocabulary Names

`Nature.leaves` is a shared bundled catalog containing `Nature.若葉`,
`Nature.下草`, `Nature.青葉`, `Nature.紅葉`, `Nature.落葉`, `Nature.枯草`,
and `Nature.枯葉`. Server and Android read these definitions and their display
data from the same catalog. This does not claim an external runtime loader, an
arbitrarily installed package, or a registry for the entire `Nature` namespace.
`Bamboo`, `Nature.雨`, and `Nature.風` remain future or explanatory reference
vocabulary names. Any future reference definition must use the same
MacroDefinition v1 schema and ordinary lock / expansion boundary, with no
plugin-specific execution path.

### 4.10 Namespace Convention

Every plugin carries a namespace:

```text
Nature.雨
Human.目
Water.さざ波
```

So that:
- where a plugin is used is evident from the description
- words of the same name do not collide (`Nature.雨` and `Weather.雨` stay
  distinct)
- a future package / catalog implementation can display Saijiki words by namespace

### 4.11 The Boundary of Freedom

The current canon is that a plugin is limited to a macro over vocabulary.
Widening that freedom requires a separate author ruling, schema / version, and
compatibility design; nothing is added implicitly to MacroDefinition v1.

#### Accounting for the form "touching" (v1.90.0)

- **Gained:** a closed organic contour — a leaf shape (vesica) made of two arcs
  that touch at both ends — can be written without freezing coordinates into the
  score, keeping the performance's sway of position and tilt.  The dilemma the
  sketches showed, "it closes but becomes a stamp / it varies but it splits," is
  resolved by one observable relation word.
- **Lost:** for the first time a relation puts an exact constraint, endpoint
  coincidence, into the space between.  The family of relations was until now
  uniformly loose — distance ranges that the performance resolves — and that
  uniformity is gone.  The cost is judged smaller than the expressive absence of
  being unable to write a closed form.

Only when a checked `Touching` to the immediately preceding ordinary Arc
succeeds, the follower's explicit Solid fill intent reaches renderer input
either as `filled=true` with `surface=None` or as a `surface.texture=solid`
compatible surface, and both members retain the same performed fill scope and
mode, the follower uses the two arcs as one closed contour. An explicit Macro
Solid normalizes through the common lowerer to the former representation, while
a saved direct Score may retain the latter. Variation, each rotation, enclosing
Transforms, repetition occurrence, and the successful relation placement feed
that contour. Its interior uses the follower's resolved color and material
below both unchanged outlines. `wash` / `none`, crescents, unchecked, failed,
or omitted `Touching`, and arbitrary overlap do not create this fill.

Questions any future proposal to change this boundary must answer:

- how far meaningful expression reaches with core primitives alone
- whether limiting plugins to vocabulary macros still expresses concrete worlds
  such as Nature or Bamboo
- how far to relax the principle if extension needs show that macros are not
  enough

**Even when a principle is relaxed, keep an explicit line that avoids becoming
Emacs.** When freedom is increased, decide only after stating what that freedom
takes away and giving the change a separately ruled schema / version and
compatibility boundary.

---

## 5. The Three-Layer Pipeline

The author writes a short description.  The system interprets it into a
controlled DDL vocabulary, expands it through deterministic filters, structures
it as JSON, and renders it as SVG.

```text
description -> normalized DDL -> expanded DDL -> JSON Score -> SVG
human          Stage 1          Stage 1.5      Stage 2       Renderer
writes         interprets       expands        structures    draws
```

### 5.1 What Each Layer Does

- **Description**: the human layer.  Written as natural sentences in the
  author's own language; tanka-like brevity is encouraged.  It is a poetic
  layer standing one step above the executable specification.
- **Normalized DDL**: the executable specification Stage 1 transcribes from
  the description (there is also an entrance for writing DDL directly). An
  enabled vocabulary plugin may appear here as a qualified `Namespace.Heading`
  term. Plugin expansion deterministically writes that term down to core DDL
  immediately after Stage 1; Stage 1.5 and Stage 2 read the expanded DDL.
- **JSON Score**: the score in between.  Language-independent and
  machine-readable.
- **SVG**: the result of the performance.  It happens once.  The description
  stays; the output is born and lost each time.

**The Stage 2 tool schema reaches the model with its property order intact.** An optional field's
fill rate therefore **depends monotonically on where it is declared**: moving `Instruction.thinness`
alone through five positions gave **0%** at the head, **18%** at position 14 (where render engine 16
declares it), **48%** at 19, **83%** at 22 and **89%** at the tail (25 distinct inputs, the same
Stage 1 output, the same Stage 2 prompt, `nvidia:google/gemma-4-31b-it`, counted over the 21 that
completed all five groups). **The head scoring 0% rules out "sitting next to a related word is what
hurts": the further back a field sits, the more often it is filled.** Field declaration order is
therefore part of the specification, not a matter of readability. The rule for raising the version when that order changes is in §2.1.

**`thinness` moved to sit immediately before `surface` in v2.9.33, giving the tail back to `surface`.**

**There is only one seat at the tail.** While `thinness` held it, from v2.9.5 through v2.9.32,
`surface` lost it and its carry fell **92% → 42%**, which **halved Stage 2's output**: the median
dropped from 172 output tokens to 94.5 and from 2.45 instructions per run to 1.43, and because
nobody wrote `surface.opacity` any more its schema default of 0.28 became the production value
(168 runs, measured 2026-08-02). **"The further back, the more often filled" also means whatever
gives up the back falls.** `thinness` itself carries 67% here rather than 89%, but this is the
position that does not shrink the rest of the Score.

**It must not be moved back beside `weight`**: as a word it belongs next to thickness, but
**the position is the more binding specification** (beside `weight` it carries 3%).
**The last slot in `Instruction` is reserved for `surface`** — appending a new optional field
after it repeats the same regression.

### 5.2 What inku Adds to LeWitt

LeWitt's instruction sheet was itself the concrete, executable instruction.
What corresponds to it in inku is the **normalized DDL**, and Stage 1 stands
where LeWitt stood when he wrote the instructions.

inku adds two things to LeWitt.

1. **The writer and the executor become one person.**  LeWitt kept the writer
   (LeWitt) and the executor (the draftsman) apart.  In DDL it happens inside
   a single person — between the author and the LLM.
2. **An input layer one step above.**  What the author writes is not the
   instructions (the normalized DDL) but the poem-like description a step
   above it.  The instructions are transcribed on the author's behalf by
   Stage 1: the author writes a poem, and the machine fair-copies it into
   LeWitt-style instructions.

What came from within returns from outside — and somewhere in that round trip
is the moment the fog lifts.

### 5.3 Vocabulary and Layers

This table is the same content as the UI's vocabulary dialog (App Info,
"Vocabulary & Layers"), and this table is the single source of truth for both.

| Term (ja) | Term (en) | Layer / act |
|---|---|---|
| 記述 | Description | The poem-like input the author writes. The top layer of the work (inku-specific; no LeWitt counterpart) |
| 解釈 | Interpret | Stage 1's **act** of reading the description into instructions |
| 指示書（正規化DDL） | Instructions (Normalized DDL) | The executable specification the interpretation produces. **Corresponds to LeWitt's instruction sheet** |
| 楽譜（JSON Score） | Score (JSON Score) | The structured intermediate form of the instructions. Stored deterministically |
| 演奏（SVG） | Performance (SVG) | The one-time result of playing the score (the draftsman's realization) |
| 詞書 | Headnote | The description raised beside the finished work — kotobagaki, the note set beside a poem |
| 読み取り | Reading | Rebuilding candidates by re-reading the words (another interpretation) |

---

## 6. The Base Language Question

### 6.1 The Question

What to do about DDL in Japanese, in English, and in other languages.

### 6.2 The Approach (provisional)

**Split the language by layer:**

| Layer | Language |
|---|---|
| DDL text (the layer humans write) | Japanese and English are implemented. Another language is accepted only after its support is added to the Instruction Language Registry. |
| JSON Score (the layer machines read) | English keys throughout |
| LLM (the converting layer) | uses the Stage 1 / Stage 2 prompts of the registered language |

### 6.3 Why the Design Is That Way

The JSON is a score, not a performance.  A score may be written in an
international notation and the performer still performs it out of their own
cultural background.  In the same way, the description can be in the author's
own language while the score is written in a common one.

To hold the principle that a description must be in one's own words, the DDL
text layer has to admit the author's native language.  Tanka can be written in
English too, but for most people the fog lifts more readily in their own
language.

### 6.4 Where the Responsibility Ends (the stance as OSS)

**What the author (Shinichiro Oikawa) is responsible for:**
- the Japanese DDL (the reference implementation, as Base Language)
- the English DDL

**What is left to the community:**
- implementations in other languages (Chinese, Korean, French, and the rest)
- vocabulary extensions specific to a language

**What is treated as fixed specification:**
- the JSON Score uses English keys throughout (a language-independent
  intermediate layer)
- primitive names and field names are English

### 6.5 UI Display Language and Instruction Language

The UI display language and the instruction language are separate metadata.
The writing tab does not ask users to choose a language: normal generation
always sends `instruction_lang: auto`. Users may run the Japanese UI while
writing English instructions, or use the English UI while writing Japanese
instructions. API requests retain explicit `ja` and `en` values for compatibility,
replay, and developer diagnostics, while `ui_lang` provides display context.
With `auto`, the server lightly detects Japanese or English from the input text
and uses the UI language only when the text itself has no language signal. The resolved language
is passed to Stage 1, Stage 1.5, Stage 2, and demo-instruction generation. Render metadata
records `instruction_lang_requested`, `instruction_lang_resolved`, and
`ui_lang` for audit and replay context.  These language metadata fields are not
part of the current canonical `render_hash` payload, so existing history hashes
and benchmark references remain stable.

Instruction-language implementation is organized through an internal
Instruction Language Registry.  Each registered language owns its language code,
Stage 1 prompt, Stage 2 prompt, Stage 1.5 expander/filter entry point, and
the language-specific marker set used by the Score coerce layer.
Japanese and English are registered by binding the existing prompts and
expanders without changing their text or behavior, while their coerce marker
sets live in separate language files.  The coerce algorithms remain common
because they operate on language-independent JSON Score structure; language
differences belong in the marker sets that map words such as motion,
visual-event, hard-edge, or dark-field cues to those shared repair policies.  A
third-party language such as Spanish should be added first as a new registry
entry with prompts, expander behavior, and coerce markers, keeping JSON Score
schema, renderer behavior, and color catalogs separate unless the new language
demonstrably needs a core extension.

### 6.6 Why Developing in Two Languages Matters

Developing in Japanese and English side by side is a process of referring to
each other's drawing results and raising the quality of the design.

When the same concept is written in both and one of them comes out unnatural,
that is the sign that the core's choice of words is leaning.  Only what can be
written naturally in both stays in the core.

**Examples of the judgment:**
- 「置く」 ⇔ *place* — natural in both, so it goes into the core
- 「佇む」 ⇔ *stand still, but with presence* — English cannot make it one
  word, so it is treated as an extension on the Japanese side rather than as
  core

Developing in one language only lets a language-specific bias into the core
without anyone noticing.  Having two makes the language-independent core and
the language-specific extension separate on their own.

### 6.7 The English Instruction Path

This subsection is on the operational side.  It records what the English path
actually does and how it was measured.

Build 403 through 427 extended the English instruction path beyond structural routing.
Japanese and English now live in separate language files for Stage 1 prompts,
Stage 1.5 expansion/filter behavior, Stage 2 prompts, and coerce marker sets.
They still share the same JSON Score schema, renderer, color catalogs, and
repair algorithms.  Language-specific behavior is therefore kept at the prompt,
expander, marker, and repair-input boundary.

The English path is tuned to preserve English-specific phrasing instead of
performing word-by-word translation.  Temporal and relational phrases such as
`before`, `after`, `again and again`, `as if`, and `at once`, along with
composition cues such as `diagonal`, `same beat`, `shifted`, reflection, fog,
road, sound, flock, and transparent-event language, are treated as cues for
abstract visual parameters and focal events.

Build 427 was checked with 30 Japanese/English equivalent prompt pairs rendered
with the same square canvas and default color catalog, without saving benchmark
history.  Expert review found the English path close to Japanese quality:
English tended to score slightly higher on color resonance, while Japanese
remained slightly stronger on constraint adherence and visual-event presence.
The remaining English risk is becoming too orderly and letting the event moment
sink into background structure.  The remaining Japanese risk is compressing
quiet poetic scenes into marks that are too small to carry a visible event.
Future tuning should strengthen focal-event size, contrast, and neighboring
reactions without increasing overall density.

---

## 7. UI Design Policy

### 7.1 A UI That Assumes Repetition

DDL is not finished in one pass. The round trip — **description -> output ->
revision** — is a premise of the design.

### 7.2 Screen Composition (in concept)

The current reference UI places description input and interpretation results,
the drawing canvas, the history strip, and refinement on the making screen.
Saved works are managed in a separate Library screen. Moving between the two
retains the input, refinement state, and Library browsing state. Stage 1's
normalized DDL may appear before drawing finishes, and a saved work exposes its
DDL, Score, provenance, and lineage. Refinement shows its relation to the source
work through derivation metadata and presentation; a programmer's diff is not
the center of the making surface.

**How much is shown is the writer's choice (v2.9.8).** The number of tools on
screen is too many for someone opening inku for the first time and too few for
someone building a work up, so the visible surface is one of three **UI modes**,
stored per logged-in user in the server database. **Simple UI** shows what
is required and the history — the user menu, the way into settings, the single
description input, the drawing controls, the canvas and the history. **History
is one of the required things so that the simple screen is not one where a work
is drawn, looked at and lost, and because both doors that take a work out as one
sheet (the share card) belong to the history group** (v2.13.9). **The canvas
toolbar stays in every mode**; under Simple UI the share card is the only control
left on it. **Full UI** shows everything, as
before. **Custom UI** adds any of seven groups (batch drawing, drawing settings,
instruction tools, detailed status, work tools, history, auxiliary controls) to
that required set. **A newly created account starts in Simple UI.** A mode
changes the display layer and nothing else: the feature paths, the history and
the stored data are untouched, so a hidden tool works again the moment the mode
is changed back. The modes are not named after proficiency. **If the mode is
changed while an input method or a work tab that it cannot show is selected,
the view returns to the single description input or to the canvas.**

**The mode can also be switched from an icon on the rail, and the icon says which mode is on by how many of its bars are dark (one for simple, two for custom, three for full). The menu is listed in that order** (v2.13.18): an icon that draws the same picture for all three modes cannot say which one is chosen.

**The settings dialog carries two modes on the same reasoning (v2.13.18).** `Standard` shows only the settings in daily use; `Detailed` adds the `Plugins`, `Limits`, `Unread Word Ledger` and `Other (server)` tabs. **One module holds the tab names, and both the tab bar and the guard on the body read that same table**: if the bar hides a tab the guard admits, there is a panel nothing can reach, and the other way round leaves a button that does nothing. The detail-level choice stays in the browser and changes nothing stored on the server. The `Demo` tab under `Making` is visible to regular users in Standard mode, and the opened settings tab is stored per user.

### 7.3 LLM Model Inspection

Refine's model comparison explicitly selects from the available LLMs and shows
how Stage 1 or Stage 2 differs from the same source work. The current contract
does not fix a particular model name; it records the models actually used and
the resulting differences.

### 7.4 The Design of the Instruction Box

**The basic stance: the opposite of IntelliSense**

IntelliSense reduces mistakes by offering candidates *before* you write.  DDL
takes the opposite view: **the moment of making lives inside the writer's
hesitation**.  In the stillness where the hand stops for an instant while about
to write "place," the realization arrives that "line up is closer."  When
candidates keep appearing, thought is pulled toward them and no gap is left in
which to look inward.

**What is adopted**

1. **A blank writing area**: the description box does not automatically offer
   completions while the writer uses their own words. Close to the purity of a
   tanka manuscript sheet
2. **The vocabulary dictionary placed elsewhere, as Saijiki**: the writer goes to
   consult it actively
3. **Interpretation feedback after writing**: inspect the normalized DDL and
   interpretation differences after drawing (§7.6)
4. **What the writer notes for themselves is not description**: a **leading
   number** (`1. `, `01. `, `０１．`, `１　`, `12）`, `3:`) and a **bracketed
   comment** (`[疎  紀友則 / 古今和歌集（春下）]`; both `[]` and `［］`) are
   **kept verbatim in the stored work and handed to no layer of the drawing**,
   **Stage 0.5 included**.  The describe and batch editors grey the
   **background of those characters** to say that they will not be drawn.
   **The cut happens in one place on the server** (`description_labels.py`), so
   it holds for the web, the CLI and Android alike.  Digits count as a number
   only when a separator or an ideographic space follows, so `2026年` and
   `3本の線` stay description; an **unclosed `[` is description** as well, and
   does not swallow the rest of the line

**What is rejected**

| Design | Why it is rejected |
|---|---|
| IntelliSense-style autocompletion | it takes away the still time of making; too procedural |
| a permanently displayed candidate list in the description box | it requires choosing existing vocabulary before writing in one's own words |

**The grounds for the design**

The description box does not push candidates at the writer, allowing them to
start in their own words. Direct instruction authoring and editing instead
show the Saijiki from the start, so the writer can survey vocabulary and compose
short instructions. These activities have different purposes; the user decides
whether to consult the Saijiki or close it while writing.

### 7.5 Saijiki

DDL's vocabulary dictionary is called **Saijiki**.  The English edition keeps the
name.

**Grounds for the name**

- the internationalization of haiku has already given the word some recognition
  among English speakers
- it states plainly that the concept comes from Japan
- for an English speaker, the very act of opening a button labeled "Saijiki"
  becomes an experience of seeing vocabulary from another culture's point of view

**Category structure**

Saijiki displays 13 categories — forms, angles, touches, continuity, surfaces,
grounds, colors, movements, places, motions, order, proportions, relations — together with the qualified
words of any loaded plugin.  The current values of the vocabulary are given by
the §3.1 table and by reference §1, and the web Saijiki display is served from
that same saijiki table (v1.92: `GET /api/saijiki` plus a synchronized store over
the snapshot bundled into the build).

The Japanese category names are written in hiragana.  Kanji is stiff; hiragana
lowers the threshold of writing.  The English category names are forms / angles /
touches / continuity / **surfaces** / **grounds** / colors / movements / places / motions /
order / proportions / relations.

**Placement policy**

- vocabulary candidates do not appear automatically in the description box
- the browsing drawer opens explicitly from the button below the canvas
- the instruction editor initially shows the Saijiki below the text and lets
  the user close it as needed (§7.8)

The Saijiki drawer is read-only (v1.98).  Clicking a vocabulary chip shows a
preview rather than inserting the word; insertion happens only in the inline
Saijiki inside the DDL editor dialog, which also shows the qualified words of
loaded plugins.  The open/close toggle sits in the toolbar below the canvas.

### 7.6 Interpretation Feedback

Current feedback is an observation surface for the transformation, not a score
on the writer's source text. It shows normalized DDL, expanded DDL when a
compatibility path produced one, plugin warnings, limit notes, and
interpretation differences. Stage 1 may arrive first over the stream, but early
display is not a judgment of correctness.

Per-word confidence, ink-density coloring, and inline English glosses are not
implemented current behavior and are not part of this contract. Unread words
and fallbacks are distinguished through the warnings and metadata actually
stored or returned.

### 7.7 Making the Difference Visible (the Course of Refining a Description)

The principle behind §7.2's "the difference between old and new is made visible
in color":

- it is designed not as a programmer's diff but as **the visualization of a
  process of paring a text down**
- what changed and what was added can be seen
- it remains as the trace of refinement

Combined with §7.6's interpretation feedback, the writer can confirm both "the
part I rewrote" and "the degree to which the LLM read it" on a single screen.

### 7.8 The Reference Web Application

What follows records what the reference interface actually provides.  It is
operational rather than conceptual.

In the Web implementation, `+page.svelte` is the route-composition shell and
retains route lifecycle, view composition, history/lineage cross-owner actions,
short presentation projections, and owner wiring. One route-instance owner holds mutable state and asynchronous
identity for each of Session, single work, Batch, Demo, history/lineage, Canvas
viewport, Refinement, and Settings. Stateless operations receive only resolved
inputs and named capabilities for one Paint, history save/replay, or refinement
plan and adoption. Focused Canvas and Settings views own presentation and local
drafts, but do not duplicate domain state, transport, request serialization, or
await boundaries. If an old asynchronous result returns after the selected work
has changed, it cannot update the current screen unless its run or target
identity still matches.

Short English tabs, buttons, and labels follow the correspondence table in
`docs/i18n/glossary.md` and the style rules in `web/src/lib/i18n/GLOSSARY.md`
(the correspondence table was consolidated into the former on 2026-08-17); the
latter's rules are enforced by `npm run lint:i18n` (v2.7.1). On narrow screens or
with enlarged text, Canvas tabs and work conditions wrap while keeping each
label with its value. The left panel also scales with the viewport.

The web app is the current reference interface. v1.72 makes refinement and model comparison first-class authoring surfaces. The `Refine` tab offers touch, layout, reading, color-catalog, and variation (§12.13) changes as a radio-style choice: exactly one intervention may be selected per refinement step, so each lineage edge remains attributable to one cause.

Selecting variation reveals an amplitude choice (subtle/moderate/sweeping, default moderate) directly under its radio; one candidate uses one fresh server-issued seed and four candidates use four, with no separate variation section or button. The chosen refine element is remembered in the browser.

Reading is one upstream intervention whose downstream layout and touch are regenerated. One or four candidates vary only the selected element, use the same selection-and-save workflow, and are displayed in a two-column grid (a single candidate fills the full width) sized to fit within the dialog. **Touch is an exception: the writer enters words for the touch and receives one candidate only. The same words produce the same touch seed, so four touch candidates are not offered.**

Saving selected refinement candidates keeps them in ordinary history without automatically starring them; the save control distinguishes unsaved, saving, and saved states, and a saved candidate cannot be saved again. Candidate generation disables other generation and drawing actions; after three seconds it exposes the shared Stop control, backed by request abortion. Progress copy names the work actually being performed. Reading candidates expose normalized DDL on image hover.

Render and vary seeds are independent JavaScript-safe random integers carried from initial generation through candidates, history, and replay. A touch candidate derives its seed from the words the writer enters. Display rendering makes touch-seed changes visible without changing canonical composition coordinates.

A color-catalog refinement keeps DDL, Score, canvas, layout seed, and render seed fixed while applying a catalog other than the parent's; four options use distinct catalogs when possible. All non-color refinements inherit the displayed parent work's effective catalog and canvas rather than the next-drawing controls. Color edges use `catalog_change` and record the before/after catalog IDs.

Caption visibility, horizontal/vertical writing mode, and left/right position are persisted per user and shared by the normal canvas and presentation mode. Previous/next navigation preserves the active Adjust or Model comparison subview inside Refine and changes only its target work.

Adjustment candidates are temporary state owned by their source work: explicitly selecting a work from history, lineage, or navigation, or starting a new generation or DDL render, clears them. Merely switching between Adjust and Model comparison does not. A target change also resets the target-owned model-comparison results, reading diff, replay error, intermediate-lineage notice, and lineage fetch state. Any in-flight model comparison is aborted, and only the latest lineage request may update the view.

The web UI keeps direct operational labels while the specification retains the musical metaphor: performance is shown as touch, composition as layout, and interpretation as reading. Model comparison lives beside `Adjust` as a subview inside the Canvas-side `Refine` tab and shows no judge values. It provides three modes: `Shared Stage 1/2`, `Fixed Stage 1 + compare Stage 2`, and `Compare Stage 1 + fixed Stage 2`. Shared mode uses each selected model for both stages. Fixed modes select one model for the fixed stage and up to four for the compared stage. Only the exact Stage 1/2 combination used by the target work is prohibited; a model used by the target remains selectable when the fixed-stage pairing makes the combination different. A floating tooltip explains prohibited choices. Models are always selected explicitly, and no unselected fallback model is run. Changing the target clears stale comparison results and aborts any comparison still in flight. Saved comparison results record the actual Stage 1 and Stage 2 models and may be adopted or starred into history.

The work header's Refine control and Lineage cards share the same work-editing menu: Edit drawing parameters, Edit the description, Edit instructions, Change the sketch-from-life grain, Change models, and Autonomous refinement process, in that order. Opening the menu does not draw or save. The header entry targets the displayed saved work and asks the user to save an unsaved preview first. DDL-authored works omit Edit the description, Change the sketch-from-life grain, and Change models. Drawing parameters and model changes open the target's existing Refine subview without duplicating comparison logic. Description and instruction dialogs initialize from that work and save a `description_edit` or `ddl_edit` child. Closing without saving returns to the originating work or Lineage view without replacing the description being written. After saving children, Lineage focuses the newest child and its ancestors while retaining the other saved branches; newest does not mean best. The regular top-level Refine tab retains its panel layout, and the former Manual Refine modal has no menu entry. A flag icon and an explicit revision-mark label distinguish the mark from editing; the stored `for_revision` meaning is unchanged.

History lists place the description in a wide column beside the thumbnail without a character cutoff. A preview of up to three lines expands or collapses by mouse or keyboard without selecting or drawing a work; the thumbnail view also offers the full text. Model names are combined only when both stages record the same complete provider-qualified ID. Missing values remain unrecorded for their respective stages, and details retain the provider and full model name. Presentation changes do not alter the saved description or conditions.

History management opens as an in-app **Library** and does not rebuild the making view, its input, or temporary refinement state. Returning after viewing a work or Lineage retains the query, filters, display form, page, selection, scroll position, and read-only preview. Selecting a row or image in that read-only preview is reading only and does not change the conditions for the next drawing. Opening the work, Lineage, and Refine are separate actions. Display form (thumbnails/list) and grouping (chronological/Lineage) are separate control groups; only a changed search, filter, or trash view updates the page and bulk selection. Cross-page selection and clearing it are explicit, and active-history and trash selections do not mix.

With Library thumbnails grouped by Lineage, works in each Lineage run horizontally from the root in generation order. Each group retains the height its thumbnails need; Lineages scroll vertically, and long Lineage rows scroll horizontally.

Lineage browsing state is separate from the selected work. Within one rooted tree it retains expanded branches, normal and overview scroll positions, orientation, overview openness, and scale. Selecting a node in the overview does not close it. A new root or unauthorized response discards that state and does not substitute old work images or text; deleted or private nodes follow the fresh Lineage response. The Lineage header groups view controls, the displayed work, the root-to-displayed path, checked works, and colophon or root actions. The displayed work and the checked set are distinct targets.

The web UI follows recorded derivations through Lineage. The Score-similarity-ranked Nearby works display and automatic loading are retired, together with the dedicated `GET /api/history/{item_id}/neighbors` endpoint. Switching works or completing generation does not trigger a similar-work search or fetch. Saved works and Lineage data are retained.

Saved-work export uses a shared menu with a fixed scope. The displayed work or one selected work offers SVG, PNG, a share card, and layer animation. Multiple checked works offer chronological work animation and review or AI contact sheets. A Lineage path uses root-to-displayed order. The checked set and the path never mix. The menu snapshots its target when opened and validates each work immediately before export; trashed, unavailable, or failed-validation works are not exported.

The input side identifies the conditions for the next drawing, while the work side identifies the displayed work's conditions. Reading a Library preview alone does not change the next-drawing conditions, and differing values are not an error. Settings are grouped as Display and operation, Making, Export, Connections and administration, and Extensions and details without changing existing permission visibility or persistence. Body text and descriptions use 14px; supporting information and small buttons use 12px. Selection is shown with checks or a displayed label as well as borders. Small actions have keyboard focus, and closing the edited-work, export, or settings modal restores focus to its entry point.

Display and operation includes a text-size slider with five steps: 90%, 100%, 110%, 120%, and 130%, with 100% as the default. Changes appear immediately and are saved to the account when the adjustment is committed. A reset returns to the default. If saving fails, the displayed size remains available with an error and retry action. Missing or invalid values use the default; preferences and pending save responses do not carry over to another account. The pixel sizes above describe the 100% setting. Fixed UI font sizes use shared CSS size definitions and one scale, while relative sizes follow the same root font size. Work SVGs, pictures, and export dimensions are unchanged.

The Description tab places the input, next-work conditions, and drawing action in that order. The input tabs are `Description` and `Batch` only. Each model or catalog row groups its label, change control, and current value, allowing long names to wrap. Different interpretation and performance models are shown separately. Sketch and canvas buttons include the current value, and Wild states On or Off. New instructions stay with the new-work controls; the displayed work's sketch and instructions follow a divider and heading. Instruction editing sits beside the text heading, and drawing from instructions sits directly below the text. Existing input locking, progress, stopping, errors, notices requiring a decision, saved disclosure states, and saving an instruction edit as a child remain intact.

New and edited instructions share a dialog and editor. The default layout supports composing short instructions from the Saijiki: a few lines of text sit above a wide vocabulary overview. Category headings and words form a multicolumn list, with examples and explanations in a separate region that does not move the word buttons. Vocabulary starts visible on narrow screens too, with fewer columns and an adapted preview position. Vocabulary and the quick guide can be toggled; hiding vocabulary expands the text editor. The text retains line numbers that follow wrapping, syntax colors, and line and character counts. Words follow the language of the current text and replace the selection or insert at the cursor. The performance model and edit-only Wild control sit outside the text; drawing, cancellation, progress, stopping, and errors stay below it. Tab stays inside model selection, and Escape closes only that picker. Closing the instruction dialog returns focus to its entry point. New instructions start empty and draw an independent work; editing starts from the target work and draws a child. Failure or stopping retains the draft. Drawing disables text editing, vocabulary insertion, condition changes, and closing.

The settings modal is centered, with each tab's heading and explanation outside the scrolling body. Navigation and fields adapt to narrow screens, while wide tables scroll within their own regions. Model administration edits one selected service at a time, showing published models before expandable connection details. Model rows expose names, IDs, publication, and purposes; evaluation fields open explicitly for editing. Search and publication/purpose filters preserve drafts, and bulk selection or clearing affects only models currently visible. Publication counts, unsaved status, and save actions stay outside the scrolling list. List refresh is disabled while edits are unsaved, and failed saves retain inputs and the dialog. Tab cycles within child dialogs; Escape closes only the child dialog and returns focus to its opener.

The Limits tab lists Drawing volume, Count representation, and Safety limits with consistent rows for field names, explanations, and inputs. Saved values, defaults, and units sit beside the inputs, and changed rows are marked. Narrow screens stack explanations and controls. Only the content scrolls; save feedback and actions remain outside it without covering fields. Edits and restoring defaults remain drafts until an explicit batch save; users can review the number of changes or discard them. Successful saves adopt the server response and identify normalized fields. Refresh is disabled with unsaved changes, editing is disabled during saving, and failures preserve inputs.

Export settings separate Save location, PNG, Animation, and Share card. PNG templates use explicit per-row saves, requiring a name and an integer height from 64 to 12000 px. Add, update, and delete requests run one at a time, and failed saves retain drafts. The UI distinguishes account-level PNG templates from browser-local export defaults and explains browser-default downloads when folder selection is unavailable. Animation settings switch between one work's layers and transitions between multiple works, sharing the same format and resolution defaults.

User administration provides search and a single permission/no-group filter, with wrapping names, emails, and groups. Only the selected account is edited, and the add-user form opens explicitly. Unsaved edits prevent list refresh and reselection; failed saves retain the inputs and error. Permission and membership explanations accompany the fields, and group management is expandable. Existing authorization rules are unchanged.

Major UI areas:

- App rail: compact navigation with an explicit expand/collapse toggle, user
  menu, profile, settings, language and theme controls
- Input panel: description and batch modes
- DDL display and editing: read-only normalized DDL in the drawing flow, with
  word highlighting, expanded DDL display, and `Draw from DDL`; editing happens
  in a DDL editor dialog with line numbers, inline Saijiki, and a short syntax guide
- Canvas panel: SVG display, zoom, pan, output tabs, work-conditions header,
  and work actions and export at the bottom
- History strip: recent works, hover metadata, star markers, pagination. **The reader chooses
  which information is printed under each thumbnail** — up to two of generation, model, engine version
  and file size, and **zero may also be selected** (choose nothing and only the pictures are shown)
- History manager: larger history view, trash, restore, permanent delete, star filter,
a shared-only filter, and
per-work sharing. The sharing dialog picks a recipient and a permission (read or write) and
lists who currently holds the work. **A work shared by somebody else carries a mark** — this
is the screen where people select and delete, and without the mark another member's work sits
there looking exactly like their own. **Recipients can be picked by name among the members of
your own organisation group**; a member who cannot fetch candidates types an id directly (the
full roster is not opened)
- Settings modal: Display and operation, Making, Export, Connections and
  administration, Extensions and details; contents follow permissions and the
  Standard/Detailed selection

The work-conditions header shows the displayed work's models, color catalog,
and canvas. Work actions, including star and sharing marks and export, appear
below the canvas.

For history display, model, catalog, and canvas values come from the history
item when available. Conditions for the next drawing come from the current
selections. The canvas header compactly groups labels and values for the
displayed work's generation, models, color catalog, canvas, SVG size, and
creation time. In the input panel, the current color catalog and its change
control share a row, with long names wrapping so they remain readable.

The settings modal's Display and operation category includes history-selection behavior controls.
Users can choose independently whether selecting a history item updates the UI's
current canvas aspect and color catalog to the history item's values, or keeps
the current UI selections.  This setting affects only the UI selection state;
the saved history SVG is displayed as stored and is not re-rendered.

The same Display and operation category carries the choice of **which facts the history strip prints**.  Up
to **two** of generation, model, engine version and file size are chosen, and they
are printed in the declared order rather than the order they were picked.
**Choosing none is a stored answer, not a return to the default**, so **an account
that has not answered and an empty selection are treated as different things**.  A
third choice is refused rather than allowed to evict an existing one, and the
limit is shown on screen.  **File size is a quantity the server reports about a
stored work**, not a count of the SVG the browser received: the listing that fills
the strip does not carry the picture, so counting what arrived would report every
work as nothing.

The canvas panel also supports viewing-oriented controls.  A fullscreen icon in
the drawing tab opens presentation mode, which maximizes the current SVG and
shows a compact control bar for history navigation, latest item, star toggle,
instruction caption toggle, and close.  Escape closes presentation mode.  A
caption icon in the drawing tab toggles an instruction caption. In horizontal
mode, the normal canvas caption uses 10% left and right margins relative to the
drawing tab and is clipped inside that tab; presentation captions use 10% left
and right margins relative to the window. Headnotes containing Japanese offer
Horizontal/Vertical controls in both views. Vertical text reads top to bottom
and right to left, preserving line breaks and emphasis. Long vertical headnotes
scroll within their frame. The defaults are horizontal and left; text without
Japanese stays horizontal without changing the saved preference. Headnote
position in Settings > Display and operation selects left or right for vertical placement and
horizontal text alignment. Captions display the original
user-facing instruction text, not the internally augmented Stage 1 prompt; this
keeps emotion-hint or system prompt material out of presentation captions.

The history DB remains the source of truth for renders saved by the web UI,
`inku-cli`, Android headless CLI, and other API clients.  The web UI periodically
refreshes the latest normal history page while the signed-in user is viewing the
latest non-filtered history.  It also refreshes when the browser window regains
focus or a hidden tab becomes visible.  This allows CLI-saved renders to appear
in the history strip without a manual reload, while preserving the currently
selected history item when it is still present.  The UI does not auto-replace
history while the user is viewing starred-only history, search results, older
history pages, or while a history request is already in flight.

PNG export options are managed as per-user templates in the settings modal's
export tab.  Each template has a name, description, and y-axis height in pixels.
The default templates are `PNG 1080px`, `PNG 2160px`, and `PNG 4320px` (the
older stored defaults `1024px` / `2048px` are replaced automatically, while
templates the user edited are kept). The PNG choices in the shared Export menu
are generated from these templates, and export width is computed from
the target work's canvas aspect ratio.

The shared Export menu on a work, Library, or Lineage opens the same export
modal as Layer animation for one work and Transition animation for multiple
works. For one work, it creates a simulated making process by revealing
layers of the saved SVG in drawing order, from the background to the finished
work. Choose the number of frames including background and completion (2–120,
default 12), the interval (0.1–30 seconds, default 0.3), and replay behavior.
Restart repeats from the beginning; Reverse plays back toward the beginning
after completion and repeats; Play once stops on the completed work. Drawing
groups, stacking order, background, clipping, and filters are preserved, and
the completed frame uses the original saved SVG. When there are fewer layers
than requested frames, repeated states combine their display durations.

For two or more works, checked works switch from oldest to newest, while a
Lineage path switches from its root to the displayed work. The settings export tab holds defaults for the shared
format (APNG/GIF), resolution, and custom height, the single-work frame count,
interval, and replay behavior, and the multiple-work transition and hold time.
The export modal shows the controls for the selected number of works. Size and
save location are shared by both modes. Supported browsers offer a save-location
button to choose a folder. Changes in the modal apply only to this export and
do not update the default settings or folder. Without a destination override,
the existing save settings apply; browsers without folder selection use their
own download settings. Failure to write to a folder chosen for this export stays
visible in the modal and does not redirect the file to another destination.

Lineage provides separate Export menus for the displayed work, the path from
the root to the displayed work, and checked works. Each menu snapshots its
target when opened; exporting checked works does not add unchecked ancestors or
the displayed work automatically.

---

## 8. The Cost of Choosing and the Balance of Making

### 8.1 The Problem

"For most people, choosing is a cost" — and yet "making is a succession of
choices."  How does DDL hold that balance?

### 8.2 The Approach

**Axis 1: the grain of a choice**
- what is left to the author is the **coarse choice, at the level of intent**
- fine choices (parameters) are left to the LLM and to sway

**Axis 2: the timing of a choice**
- minimize the choices made in advance (writing the description)
- put the weight on the choices made afterwards (picking among several outputs)
- a choice that has something to compare against is cheap

### 8.3 What That Implies for the Design

Once the description is written, several options are generated at once, and the
author picks one, rewrites the description, or regenerates.  The cost drops from
"make something out of a blank page" to "look at what is laid out."

### 8.4 Making the Afterwards Choice Concrete: Two Stages of Regeneration (v1.52)

Regeneration splits into two stages.  Neither breaks the default determinism,
and both change only on an explicit action.

| Stage | Name | What changes | Cost |
|---|---|---|---|
| Performance | Another performance | region, relation, and placement phase as resolved by the performance seed (§13.8 / §14.4) | no LLM call (re-render only) |
| Composition | Another composition | Stage 1.5's focus selection and the concrete angle and corner for explicitly authored angle and corner meaning, from the composition seed (§12.11 / §18) | one Stage 2 call (the saved normalized DDL is unchanged) |

Another composition reselects among the closed six focus candidates and, when
the description has an angle, reselects its concrete angle. The Stage 1.5
transformation remains focus-only; the Stage 2 consumer resolves the angle from
the same `composition_seed`. It must not invent or reselect a composition
family, technique, color, touch, relation, or element count. Another
performance and explicit variation preserve the resolved angle. Explicit
variation moves the focus axis only when both amplitude (small, medium, or
large) and a variation seed are present; an incomplete request means no
variation. The description, normalized DDL, and explicit attributes remain
unchanged.

These two stages are the substance of §8.2's "put the weight on the choices made
afterwards."  A generator with wide dispersion also produces more misses, but a
miss is handled by the human act of choosing among what is laid out, not by a
governor that averages it away beforehand.  Choosing is part of making, standing
beside the refining of the description.  The final judgment of quality belongs
to this afterwards choice as well: the judge metric is a reference value for
regression detection, never an acceptance gate.

**Labels in the UI.**  This specification and the internal design keep the
musical figure — description, score, performance.  The main action buttons
replace those figures with plain operational words, so that someone touching the
app for the first time can predict what a button does: performance is shown as
touch, composition as layout, and interpretation as reading.  How the Refine tab
realizes this — the five refinement kinds, model comparison, and the Lineage
card menu — is in §7.8, "The Reference Web
Application."

Touch refinement is the exception to the one-or-four candidate control: the
writer enters words for the touch, and the same words produce the same touch
seed, so it produces one candidate only.

---

## 9. The Design of the First Stroke

### 9.1 Requirements

- an inspiration can become the first stroke
- that stroke produces feedback satisfying enough to continue
- chance is not too high, completion does not go too far, and yet it is not mere
  tracing

### 9.2 Output Balance

The balance between completion and error correction at each Stage matters.

```text
chance too high      ->  the author's intent is invisible  ->  motivation goes
completing too much  ->  it does not feel self-made        ->  no meaning in it
mere tracing         ->  DDL was not needed for this       ->  no meaning in it
```

The balance is right when **the words the author wrote are realized a little
more intelligently than expected**.  That "a little" is what makes the next line
worth writing.

To support a tanka-like brevity, the writing surface carries only a non-blocking
length hint (the box displays the count, but does not enforce the guide).
Japanese input uses roughly 31 characters as a guide; English input uses roughly
12 words.  Input is never blocked.  The UI shows no copy that
denies a long description and no evaluative display — only a numeric counter and
a faint change in density, so the form is quietly present without scolding the
writer.

### 9.3 The First Line

Not "what to draw" but "what has stayed in your mind."  From that, the LLM draws
out the DDL.

---

## 10. Quality and Error Handling

### 10.1 The Errors That Actually Happen

1. the tokens run too long (a problem of the input)
2. the generated JSON has errors (a problem of the conversion)
3. no drawing behavior can be generated for the instruction (a problem of
   expression)

All three come from **the distance between the description and the schema**.
The further the description sits from the schema, the more interpretation the
LLM has to supply, and the higher the chance of failure.

### 10.2 The Layers of Constraint

| Layer | What it does |
|---|---|
| Layer 1: input constraint | limit the vocabulary, grammar and length of the description |
| Layer 2: conversion constraint | require schema adherence in the system prompt; few-shot examples |
| Layer 3: output constraint | repair JSON errors automatically in the sanitizer |

### 10.3 What Constraint Design Really Is

Tighten the constraints and errors go down, but so does the freedom of
expression.  Loosen them and expression grows richer while errors multiply.
Designing DDL's constraints is **drawing the line between what the system
guarantees and what is left to the LLM's sway**.

### 10.4 Repair and No Invention

Coerce is a narrow delivery and safety boundary for carrying content explicit in
the description and typed meaning into Score. It invents no accent, proximity
reaction, disappearance trace, visual event, composition anchor, relation,
color, or shape.

An invalid value or unresolvable relation is handled distinctly as a warned
drop, an explicit failure, or a read-compatibility path; its meaning is not
guessed and repaired. Repair is neither a quality floor nor a minimum firing
rate and must not create a recurring stock part.

The shared boundary from lock-verified Stage 1.5 to an actual Score retains the author-selected Stop and OmitAndContinue inputs. A recoverable relation failure, including under legacy Stop input, never prevents the rest of the drawing: it records an error and removes only that relation, leaving its instruction or Macro Emit, group, and dependent instructions in their original transformed placement. OmitAndContinue still narrows only the execution projection for its established appearance and structural units. Both modes stop when no drawing unit remains or when owner / focus joins or host context fail integrity. Neither mode uses an LLM, guesses values, clamps them, or resolves previous-one / two relations against compressed post-omission indices.


---

## 11. Testing Strategy

### 11.1 Separating the Axes of Evaluation

| Judged by machine | Judged by a human (or an LLM) |
|---|---|
| is the JSON valid | does it reflect the intent |
| is every primitive implemented | is it artistically interesting |
| is the token length in range | is the sway appropriate |
| does the rendering complete | — |

The CLI judge metrics (`visual_event`, `negative_space_pressure`,
`motion_energy` and the like) are diagnostic values for catching a sudden
collapse in quality or an implementation regression.  Build 448 confirmed cases
such as JP #23 where a low `visual_event` and a high human evaluation diverge,
so these metrics are not retuned into a final evaluation of the work or into an
acceptance gate.  The final judgment of quality belongs to the afterwards
choice of §8 -- the human act of picking among the works laid out.

### 11.2 The Layers of Evaluation

The project evaluates quality through several layers:

- backend tests for API, DB, schema, composer, interpreter, renderer, and
  deterministic fallback behavior
- frontend Svelte check and production build
- CLI-based benchmark generation
- saved benchmark summaries and contact sheets
- visual review of generated SVG/PNG output
- stress tests using invalid, ambiguous, emotional, conversational, and
  contradictory instructions

### 11.3 What the Benchmarks Watch

Benchmarks focus on:

- whether Stage 1 preserves the whole input context
- whether Stage 1.5 preserves explicit meaning and invents nothing beyond focus
- whether the shared compiler/lowerer preserves explicit DDL and omits only failures locally with diagnostics
- whether deterministic fallback keeps enough DDL content to be reviewable
- whether the renderer makes DDL features visible
- whether the output has enough negative space, sway, and artistic focus

Current render-core tuning records explicit quality metrics for the work in CLI benchmark summaries: `constraint_adherence`, `negative_space_pressure`, `motion_energy`, `color_resonance`, `visual_event`, and `figurative_risk`. These judge metrics are regression sensors, not final acceptance gates or substitutes for human selection. Build 448 confirmed divergence between machine scoring and human review, especially JP #23, so the metrics should not be retuned merely to raise preferred works. Fallback use, server hard timeouts, motif hints, presence counts, color traces, and compositional markers are recorded separately. Queue or retry duration is diagnostic only and is not treated as a primary quality metric, because free inference endpoints can be dominated by external queue behavior.

For NVIDIA free API testing, elapsed time is treated as operational metadata,
not as an artistic quality signal.  Queue delays can indicate service pressure,
but they do not exclude a successful work from aesthetic or structural review.

**The inventory of what is currently implemented moved to
[current implementation status](docs/spec/implementation-status.md) on 2026-07-28**
(kept as a Japanese/English pair since 2026-08-02, with Japanese canonical).

### 11.4 Test-plan History

Completed PoC work, the initial automated-test plan, model names, and build
order live in [CHANGELOG.md](CHANGELOG.md) and the [public history
archive](docs/history/changelog-v0.1-v1.71.md). Sections 11.1–11.3 are the
authority for current check layers and acceptance boundaries.


---

## 12. The Two-Stage Architecture

The shared authoring state machine manages the current pipeline: Stage 1 for description input, visible-DDL persistence and typed compilation, known-hole completion when needed, deterministic Stage 1.5/lowering, and the shared renderer. New work does not use old Stage 0.5. This chapter states each authority and saved-compatibility boundary.

### 12.1 Two Stages Separated by Visible DDL

Producing visible DDL from a description is separate from validating DDL and lowering it to Score. These are not two LLMs independently inferring drawing intent. Direct DDL bypasses the first stage.

```text
the user's description
    | Stage 1: produce visible DDL
visible DDL (core vocabulary and locked Macro calls) <- directly writable and editable
    | shared compiler: known holes may request a patch, author approval, and CAS save
    | deterministic Stage 1.5 and lowerer
JSON Score
    | shared renderer
SVG
```

### 12.2 Why Visible DDL and Score Production Are Separate

Visible DDL is the meaning boundary. Ambiguous nuances in the original description cannot enter Score through a hidden route. Authors can read DDL, assess the intent, and edit it.

An LLM produces a DDL candidate from description or proposes a patch for compiler-reported holes. Shared Rust owns syntax validation, preservation of explicit attributes, counts, resources, and Score structuring. A completion candidate also passes through visible-DDL approval and persistence; it never overwrites Score directly.

### 12.3 How It Fits the DDL Concept

The two stages match the philosophy of DDL structurally.

Fitted into the three-layer pipeline of §5:

```text
description (the author's own language, free words)
  | stage one: interpretation
normalized DDL (core vocabulary only)   <- where "the fog lifts"
  | shared compiler, Stage 1.5, and lowerer
score (JSON Score)
  |
performance (SVG)
```

The step from description to normalized DDL is the scene where authors are
made to see their own intent.  A vague word — 「佇ませる」, *let it stand
there* — is broken down into core vocabulary: *place it near the center, with
a thin line, given a slight sway*.  Feeding that breakdown back to authors is
what lets them see, for the first time, what they wrote.

In tanka terms it is close to the feeling of having someone else read the poem
you wrote.  The gap between their reading and your own intent is what produces
the next description.

### 12.4 The Form of Normalized DDL

The form of the normalized DDL that stage one emits is decided by this policy.

**Policy: keep the rhythm of natural sentences, and limit the vocabulary to
the core.**

```text
normalized DDL (example, in the form the corpus uses):

  中心に鉛筆の細い線をひとつ置く。線は細かく揺れる。
  (Place one thin pencil line at the center.  The line sways finely.)
```

In the typed DDL compiler, the second sentence in this example does not create a second drawable entity. When a canonical head marked by `は` / `が`, or by the meaning-equivalent English determiner topology, reintroduces exactly one prior entity, a source-preserving continuation edge attaches the following predicate to that same entity and instruction. Zero or multiple target candidates, an unclear clause boundary, or an unknown or conflict fails closed as a typed issue; the compiler does not guess by first, nearest, or last position.

The continuation retains exact source spans and clause provenance for the reintroduced head, subject marker or determiner, and predicate, while localized surfaces stay out of canonical semantic bytes. The head and marker are delivered exactly once as continuation syntax, and explicit predicate modifiers or actions are delivered exactly once as structured fields on the target. Existing quantity, position, relation, Ground, and MacroInvocation ownership is not rebuilt. Existing relation targets `previous_one` and `previous_two` belong to explicit relation edges; they are separate from this marked-subject continuation target. This is the visible typed semantic graph before JSON Score. JSON Score examples later in this specification are not the graph itself: lowering to Score or Renderer and deciding defaults belong to the Step 10 gate, and this rule does not begin either operation.

For example, `赤い円を中心に置く。` and `円を中心に置く。円は赤い。` have the same source-independent canonical meaning when they resolve uniquely to the same subject and explicit instructions. The first form's inline record and the second form's continuation source spans, rhythm, continuation edge / target, bindings, and provenance remain distinct, so their full compiler-lock attestations need not match.

English grammar words are ASCII case-insensitive in both lexical recognition and downstream grammar matching. For example, background markers `the / background / with` and the fill connector `with` have the same grammatical meaning when written with uppercase letters. This does not lowercase the source: the author's bytes, spans, and provenance are preserved. Matching rules for separate identities, such as Macro names, are unchanged.

Existing grammar markers are recognized by a bundled constant table in shared Rust, which passes typed identities and occurrence-specific source spans downstream. Its scope is Japanese `を / に / で / の / は / が / へ / と / 背景 / 組 / して / 繰り返して` and English `with / in / at / on / to / of / a / an / the / and / background / group of / repeating`. Multiple grammatical roles of one marker use capabilities and existing phrase structure rather than reclassifying surface strings downstream. Saijiki owns semantic vocabulary; existing compiler rules own attachment and owner selection. The layout-bearing forms `重ねて / 並べて / overlapping / side by side` stay outside this table in their existing layout grammar. The table does not introduce new words, aliases, or drawing meanings, load external dictionaries, or add a registry version to saved formats.

Stage 1, camera projection, and hole completion use the existing shared grammar helper, referring by identity only to markers required by those finite forms. They do not enumerate the whole table in prompts. Centralizing marker recognition does not change recommended forms, Score, the renderer, or the meaning of saved works.

Initial generation and camera projection also share the existing standalone-shape grammar for pre-head modifiers, quantity, action, and line-up direction. Patch-only constraints on adding unspecified attributes, confirmed bindings, and local patch responses remain in hole completion and do not constrain the initial visual interpretation of poetry. Existing group and ordered-placement rules, Saijiki vocabulary, macro signatures, response schemas, and compiler acceptance conditions are preserved.

The generation vocabulary projection lists only existing asset surface forms, without appending display/reference default annotations to them. Reference annotations and default values remain intact. Initial generation and camera derive drawing heads from the same projection and distinguish them from tool, continuity, and surface attributes. Ground, background, and macro calls with only declared parameters are distinguished from drawing commands. Required subjects or unbindable explicit specifications must not be deleted merely to obtain formal acceptance.

Shared standalone grammar makes modifier phrases own their connectors but exclude the head, and treats a quantity as one complete count expression. Non-Saijiki thinness, relative size, regularity, and side-count forms use a read-only projection of the existing parser definitions also used for recognition, not a separate prompt vocabulary table. Shape-form modification is a finite regularity constraint, not an open slot for adjectives derived from natural subjects. Existing boundaries, following-head conditions, and accepted combinations remain unchanged.

**Options that were rejected:**

| Form | Why it was rejected |
|---|---|
| fully natural sentences ("place a thin line, with a slight sway, near the center") | leaves room for a second *interpretation* in stage two |
| a structured list (YAML-like) | looks like code; it takes the pleasure out of describing, and similar graphical description languages already exist |
| function-call style (`place(subject=line, position=center)`) | too close to code |
| a separate modifier line (an early draft that wrote "sway: small" on a line of its own) | never adopted in the implementation. Motion words are written inline as sentences, as in "the line sways finely" (the fixture corpus is canonical). Surface and ground follow the same rule: headed forms such as 「面: ...」 and 「地: ...」 are not adopted (removed from this specification on 2026-09-24). A ground is a sentence of its own such as “washi.”, and a surface is a modifier of its shape |

**What the adopted form does:**

- keeps the rhythm of natural sentences (the readability of tanka)
- limits the vocabulary to the core (place, thin, center, and the like)
- writes motion words inline; a surface quality is a modifier of its shape and
  a ground is a sentence of its own such as “washi.”
- keeps the structure of the format common between the Japanese and the
  English version
- **is designed on the assumption that the author will see it** (it is shown
  in the interpretation-feedback UI)
- when Stage 1 interprets a material from the description, writes that choice explicitly into visible normalized DDL; a material the input states explicitly is preserved
- when an author writes direct DDL or edits generated DDL, permits touch and other fields to be omitted and retains typed meaning as `unspecified`; it does not infer or insert hidden values from texture / context, primitive type, word order, or the current Score default
- writes shape size as a finite seven-class local modifier combining normal / small / large with mild, standard, and strong steps, while keeping explicit normal distinct from omission. Numeric geometry plus qualitative size, an unknown degree, or ambiguous ownership is a typed conflict or issue
- treats burin and drypoint as explicit only when visible DDL states them; Stage 1 few-shot quality policy is not direct-DDL compiler semantics
- in the current actual-Score lowerer, applies the author-resolved normal geometry, relative factors, and omitted drawing attributes only to count-one circle, square, ellipse, cloudform, triangle, and polygon instructions with a resolved numeric position or an original `place:center` owned by a verified direct instruction target, plus a place action. The named path preserves dimensions and places effective focus in `at.region`. Stop rejects the entire Score for unsupported meaning or missing required color-catalog context; explicit OmitAndContinue omits only an independent field or typed execution unit and returns the remaining Score with diagnostics. Neither mode changes original meaning. The normal product runtime uses this Rust path

### 12.5 Splitting the Model by Stage

A different model can be used for each stage.  **The current implementation
selects a model per stage**: users and administrators set a model for Stage 1,
Stage 2 and Vision separately (the model settings and model comparison of
§8.4, and the llm / vision catalogs of `/api/models`).

Stage 1 produces visible DDL from a description. Stage 2 produces only visible patch candidates for known holes reported by the compiler. Select each model for its bounded input and required result. The deterministic shared Rust lowerer structures Score; this is not delegated to an LLM.

### 12.6 The Design of Stage 1 (Interpretation)

Stage 1 maps free description finitely into normalized DDL that the writer can
inspect and edit. It preserves explicit elements, quantity, color, material,
and relations, and does not add hidden visual content or a "beautiful"
interpretation. Vocabulary, the closed schema, limits, and source facts are
passed as a prompt lock, and output stays inside that lock. This is the finite
typed-normalization contract synchronized in I-640; no particular model name or
model class is canonical.

**Work plan (Stage 1 prompt `inku.typed-stage1-work-plan-prompt.v1`).** The
initial-generation LLM does not write visible DDL text; it returns a closed,
typed work plan as JSON. A work plan holds up to eight standalone-shape layers
plus optional ground and background, and every value is an enum projected from
the Saijiki asset, the parser's finite modifier forms, the fluctuation
classifier, and the Score intensity values. The values each form (with its
proportion word) accepts come from the capability matrix
`inku.work-plan-capabilities.v1`, generated by compiling one sentence per value,
and shared-Rust validation is authoritative rather than provider-side decoding.
An out-of-range value becomes unspecified for that field, a layer without a
shape is removed alone, and nothing stops the drawing. The normalized plan is
printed deterministically as visible DDL in the request language, and only that
text reaches the existing compiler. The capability matrix and bilingual
property tests guarantee that every printed layer compiles without a
diagnostic, so initial generation no longer drops clauses. The response schema
uses only object, array, string enums, and bounded integers, which every
existing provider transport carries unchanged. A saved response that already
carries `normalized_ddl` is read unchanged so recorded executions replay. The
work plan is transient; visible DDL and the Score remain authoritative. Direct
and edited author DDL is still parsed with the full grammar and is never limited
to the plan subset. This edition's work plan contains no Macro invocation: core
vocabulary is primary and Macros are an optional extension.

Initial interpretation condenses the whole description's roles, contrasts,
repetition, density, empty space, and texture into a short visual composition.
Brevity does not mean collapsing necessary roles into one central element or
assigning one shape to every noun. Explicit quantities take priority. For
repetition without an explicit quantity, choose a count from the context and
state it in visible DDL. Do not use word-to-count bands, fixed minimums, or
uniform increases, and do not treat more marks or sentences as a quality goal.

Placements, tools, and other choices interpreted from the description are
written into visible DDL while explicit specifications are preserved. Do not
impose a central or edge placement, a fixed tool, or ground or background on
every work. Do not change explicit colors for visibility or substitute ground
or background for necessary drawing subjects. There are no subject-to-shape,
material, or composition tables or subject-specific steering examples. This
initial-generation policy is shared by Japanese and English; it changes
neither the existing finite vocabulary, grammar, and response schema nor
camera projection, hole completion, the compiler, or saved works' meaning.

The initial prompt uses a short order: preserve explicit specifications, choose
unspecified parts from the whole description, write accepted grammar, then check
preservation and ownership. It does not require every attribute to be filled or
invite the LLM to silently delete unsupported explicit meaning. "Random" is read
as an observable static state in context, not mapped to a fixed placement. The
example distinguishes a directly specified shape angle from arrangement
direction; it supplies no subject mapping or default center, color, or support.

Tools in the shared Saijiki asset carry short bilingual `physical_description`
notes grounded in §13.5. Only initial generation reads these notes for existing
`prompt=true` tools in Saijiki order. There is no subject- or emotion-dependent
selection or recommendation, fixed quantity, numeric default, or new synonym.
Notes remain separate from accepted vocabulary and are not DDL words, parser
aliases, or Score values. Editing notes changes the asset's byte-provenance
digest without changing accepted words or drawing semantics.

Initial usage guidance distinguishes tool from thinness and continuity, count
from size and placement, shape angle from line-up direction, and surface from
ground and background, with the current typed DDL applicability limits. A listed
word does not authorize every head combination. Explicit independent points,
lines, and marks must not be absorbed into surface attributes. Neither this guide
nor the tool notes are added to camera or hole-completion system text.

### 12.6.1 Sketch from Life (Supplementing Place and Light, draw-system03)

An optional **sketch** can run once before the work plan. It never rewrites the description: it supplements only the **extent of place** and the **seasonal or time-of-day light** that the description implies without stating, in one to three sentences of plain words for things. Stage 1 receives both the description and the sketch; from the sketch it only adds scene or back layers and the background color, while subjects, movement, direction, counts, and placement follow the description. The sketch never takes the description's place, and the description remains the work's provenance in storage and display (§12.16).

When to sketch is chosen per drawing, and the default is **auto**.

- **Auto** (`auto`): the sketcher first judges whether the description gives enough cues to draw from. If it does, nothing is added and the description alone is drawn (`not_needed`). The criterion is the amount of cues, a general one, not the form of the text (waka or prose). <!-- the rule is settled by the development evaluation -->
- **Off** (`off`): no sketch.
- **Always** (`always`): supplement even when the description states its cues. This is what the author's per-work "redraw with a sketch" uses.
- A sketch the author edited, or a saved one, is used as it stands without a request (`supplied`).

The sketch **never waits for a confirmation**: nothing asks the author between pressing draw and seeing the picture. A failed sketch request goes on to the work plan with the description alone, and the drawing completes (`fallback`). The sketch can be read and edited after drawing; editing it draws again. The per-work switch "redraw with or without the sketch" saves the result as a child of the chosen work (derivation kind `sketch_grain_change`, metadata `from_sketch_state` and `to_sketch_mode`).

In the shared pipeline the sketch is the optional effect `generate_sketch` before Stage 1 (result `sketch_generated`, prompt `inku.sketch-supplement-prompt.v1`). The start input and a regeneration from the description may carry `sketch` (`off`, `auto`, `always`, or `supplied`). The snapshot's `sketch` record (`pending`, `supplemented`, `not_needed`, `fallback`, `supplied`) states what the sketch did, and the saved `sketch_state` becomes `supplemented` (with the sketch text and an empty `sketch_grain`), `not_needed`, `fallback`, or `off`. The retry budget is `sketch_retry`, or the catalog-selection budget when absent. The retired layer's `fine` and `coarse` grains (§12.15) remain only for displaying saved works and are not used by the new sketch.

### 12.7 Stage 2 Completion and Deterministic Structuring

The Stage 2 LLM returns a span-bounded patch candidate only for known holes explicitly reported by the compiler in saved visible DDL. The shared pipeline creates the request automatically; adoption requires author approval and a visible-DDL CAS save. The LLM does not output Score. The shared lowerer structures lock-verified typed meaning into Score once, preserving color, material, quantity, movement, arrangement path, rotation, canvas, and explicit relations.

A recoverable failure omits the smallest affected field or execution unit with a diagnostic and continues independent drawing, for either legacy Stop or OmitAndContinue input. It does not correct undeliverable meaning into a different Score field, and retains original owners and order. An entirely omitted drawing or an integrity failure stops. Results distinguish complete, complete with omissions, and stopped.

An explicitly authored angle reaches `Score.rotation` exactly once through one shared resolver for direct instructions and flat Macro Emits. Its selection is bound to original meaning, tagged `composition_seed`, logical occurrence, and angle identity; effective focus, variation seed, render seed, and source spelling are excluded.

### 12.7.1 Shared Authoring State Machine

Shared Rust treats authoring as deterministic commands over a versioned snapshot. The normal Server, Web, and Android paths connect to that snapshot and host. Core returns the next snapshot, progress events, and at most one `EffectAction`; the host performs only the LLM call or visible-normalized-DDL save and returns a typed `EffectResult` that echoes the action identity. Provider transport is attempted once per action; core decides whether another action is required. A stale sequence, changed digest, or late result cannot change state. Core never claims host success before the host reports it.

Only with `INKU_DEVELOPER_MODE`, an authoring request may independently set the strict booleans `developer_disable_llm_retries` and `developer_capture_provider_io`. The first limits catalog, Stage 1, and hole-completion core policies to `max_attempts: 1`, including compiler-rejection feedback requests. The second sends only after a private durable owner/execution/action record is created, then records the exact sent JSON body, provider ID/model/action tag, HTTP status, received raw body, timeout, usage, elapsed time, and outcome. A cut or size-limited body is explicitly partial/incomplete; failed pre-send recording prevents transmission, and a post-send recording failure is never shown as complete. Raw data is excluded from normal history, public views, and logs, and is readable only by the same owner in developer mode at `/api/pipeline/executions/{execution_id}/provider-observations`. URLs, headers, credentials, connection configuration, and exception text are not recorded. Enabling either option outside developer mode is rejected; normal retries, prompts, and drawing semantics do not change.

Android connects its Kotlin host directly to the provider and shared Rust JNI without an inku server. Normal description and direct-DDL input, batch, demo, refinement, and camera output use the same shared pipeline. Image preparation and the on-device local LLM remain host responsibilities; their resulting description or DDL enters the regular pipeline. Non-image camera provenance survives completion approval and resumption. New authoring does not call Stage 0.5 or substitute legacy sketch prose for the original description. Visible patches show the current and proposed DDL for approval in the normal drawing screen. The iOS connection is outside this Android integration and remains separately pending.

Room migrates from v10 to v11 while retaining existing works, adding atomic origin/authority/source saves, action acknowledgments, opaque executions, and immutable context for each history revision. Resuming a save for the same execution does not duplicate that performance in history. Replaying a saved Score also retains its original short DDL and that revision's authority, validated against independently saved resource budgets. The shared Rust registry supplies the 11 new-paper IDs and integer ratios. Android's former `pixel9_landscape_safe` option becomes device display margins; old works retain their 9:5 ratio and saved images. Migrating that old device preference selects the default `square` paper for new works and never aliases 9:5 to 16:9.

A variation preserves its origin as either `stage1_generated` or `user_authored_ddl`, while authoring authority advances monotonically through `description_authoritative`, `ddl_authoritative`, or `legacy_unknown`. On a description-generated variation, the first user-confirmed DDL commit whose exact source bytes changed locks authority to DDL. Committing identical bytes does not lock it, and restoring earlier bytes after a committed edit does not restore description authority. Direct DDL starts under DDL authority. Every mutation is a compare-and-set proposal with a decimal-string revision; active authority and source change only after the host acknowledges the matching atomic save. Existing history remains `legacy_unknown` without inferring origin from its text, and retains its display and saved-SVG replay. Editing legacy DDL forks a new `user_authored_ddl` / `ddl_authoritative` variation; regenerating from a legacy description forks a new `stage1_generated` / `description_authoritative` variation. The parent relation is saved and the original history row is unchanged. Selecting an older performance saved by the shared pipeline also keeps that history's source, revision, seed, catalog, resource limits, and definition locks; it is never replaced by the latest state of the same variation. A new performance links its raw compact Score and authority revision to history and stores the config and host context from that point in a fork sidecar. A fork stops if the sidecar revision or source digest does not match the history link and never infers these values from the latest snapshot. Core snapshot config remains immutable within one variation. The normal UI therefore regenerates a description from an existing variation as a new variation and edition, passing the currently selected options.

Lineage editing identifies the history-row owner and selects its linked fork, without updating or replacing the old fork. Active `/executions/{id}/author-ddl` receives source, revision, and options. With unchanged settings and changed source it saves record metadata while preserving CAS, origin, and the DDL-authority lock. A changed canvas, wild setting, or other option creates a parent-linked direct-DDL variation under DDL authority without changing the original source, config, or authority. An unchanged source with changed record metadata also saves a new edition instead of discarding the existing result. History sidecar v2 immutably records the four core diagnostics, renderer diagnostics, and `resource_execution` for the matching revision and source, and normal history display restores them. V1 has no diagnostic record. A corrupt sidecar warns only for that work while saved DDL, Score, and SVG remain visible; it neither infers latest state nor recompiles.

A typed Stage 1 request carries bounded projections of the finite vocabulary derived from the Saijiki, resolved catalog and canvas identities, and only each validated Macro's qualified name, version, definition digest, parameters, and host-supplied localized summary. Its response schema permits only the work plan of §12.6; the LLM never writes visible DDL text directly. When parsing committed visible DDL identifies completable known holes, the shared pipeline automatically creates the completion request without a separate user operation. With no holes it does not call the Stage 2 LLM. The Stage 1 residual-adoption path in §12.8 is an exception: after its save acknowledgment it delivers the deterministic remainder without another LLM request. A clause containing words outside the finite grammar may become a known hole only when the compiler can establish its exact clause boundary and an exact drawing head, ground, or background anchor; unknowns without that exact boundary, conflicts, and integrity errors are not completion targets. When a following continuation clause is unresolved only because of a patchable upstream hole, its continuation diagnostic is deferred until recompilation after the patch; the following clause does not become an additional rewrite target.

A hole-completion request carries the original target text, established typed facts, finite Saijiki vocabulary, and accepted grammar. Unrecognized expressions remain in that original text. A reference target or other compiler-confirmed dependency may supply the smallest necessary read-only context. Reading scope and editing scope are distinct; the request excludes descriptions, unrelated clauses, Score, renderer instructions, and chain of thought. Multiple colors or tools alone do not justify inventing alternation, order, or a quantity split, and an unrepresentable meaning is not changed to a nearby different meaning.

Completion normalizes variations in word order, term position, combinations, and natural paraphrases into existing grammar; it does not freeze every surface word or its position. Near the center may be paraphrased as the existing named center position without inventing numeric coordinates. Meaning that existing features cannot draw remains an explicit displayed and logged diagnostic while as much of the remaining drawing as possible is retained. Completion does not require adding grammar, Score types, or rendering features.

Completion requests containing a drawing head or relation include concise guidance for existing modifier, count, action, and position attachment, distinguishing lexical categories from established owner roles. The role of unbound vocabulary is interpreted from the original context; absence of a confirmed binding alone does not justify removing or guessing explicit meaning. An unpositioned scatter has a canvas-sized distribution domain by default, so wording that only repeats that extent can be consolidated into accepted syntax, without equating an explicit region or position with the default. Fixed reference literals are projected from the existing Saijiki asset in the request language. Their guidance does not depend only on an already recognized relation fact, because unknown reference wording may not have one yet. No alias, grammar, or response field is added; established fact, owner, quantity, and diagnostic validation remains unchanged.

A provisional primitive head without any attributes, count, action, or other bindings in an unresolved clause with ambiguous action ownership need not denote another drawable. When there are no groups, sequences, continuations, fill targets, or existing references, its vocabulary may be retained as a reference target only if the candidate's typed PreviousOne reference resolves to a preceding object with the same primitive outside the edit. One reference cannot preserve multiple heads. Established owners, quantities, outside meaning and diagnostics, and approval/CAS remain validated. This does not permit exchanging an existing valid angle and layout_direction.

A standalone ground or background clause with no drawable head, quantity, relation, or modifier owner may be checked separately from unresolved drawing clauses. Support clauses of the same kind remain one unit. Its candidate must retain only the same support owner and cannot introduce a drawable, so source-ordered reference ordinals remain unchanged. Established facts, outside diagnostics, and whole-candidate recompilation remain required. This exception does not split unknown drawing clauses from one another.

A clause with one established primitive head and action may also be checked individually when its count is explicitly bound or remains unspecified with no recognized numeric occurrence or recognized unresolved diagnostic, in a simple reference namespace without groups, sequences, continuations, or fill targets. Recompilation must preserve every instruction's source-ordered head identity, count including its unspecified state, and action, and the repaired owner must have no outgoing reference dependency. An unbound number or qualitative-quantity diagnostic is not treated as count omission, and no default count is inferred for the proposal. An unresolved later reference alone does not reject repair of an earlier owner. Uncertain dependency units remain coupled; existing fact, owner, and outside-diagnostic validation and whole-candidate recompilation remain mandatory.

The new response returns exactly one proposal or unresolved reason for each short request-local target ID. Shared Rust checks the complete ID set for missing, duplicate, or unknown entries, then restores the actual hole ID, allowed span, range digest, and base-source digest from the saved request and compiler lock. The provider does not regenerate hashes or byte positions, and Python or Kotlin hosts do not repair meaning. Action identity, revision, compiler-lock validation, and compare-and-set checks still bind asynchronous responses.

A provider patch remains a candidate. On recompilation, the shared compiler checks that established facts retain their associated targets and that edited targets are resolved. This does not mechanically prove the semantic equivalence of every previously unrecognized expression; the interpretation remains visible DDL for author review. Only units with proven independence may be proposed for partial adoption. Units sharing a total, group, reference relation, or uncertain dependency are not split by inference. The combined candidate is also fully recompiled to compare meaning and diagnostics outside the edited ranges. Explicit author approval revalidates it against the base and sends source plus next authority to the host as one CAS save action. Only the matching save acknowledgment allows the saved visible bytes to be parsed again; remaining holes are not automatically resubmitted. Unresolved and rejected targets retain safe reason codes, the current safe Score and SVG remain available, and partial adoption is not reported as completion of every hole.

Transcript replay reconstructs the same snapshots and outputs from command envelopes and final effect-result envelopes alone; output-only progress events and host effects are never replay inputs. The two-owned-buffer entry point accepts UTF-8 JSON bytes for an empty or previous snapshot and for one input envelope, then returns JSON bytes for either output or a stable error. Shared bindings expose this `Vec<u8>, Vec<u8> -> Vec<u8>` operation, binding/protocol versions, and shared operations for the canvas registry, resolved colors, Macro catalog, Stage 1 vocabulary projection, and saved-Score replay. Python and JNI adapters do not duplicate semantic decisions. A panic is contained as a stable `internal_invariant` error envelope rather than platform exception text.

The normal Web and `/api/interpret`, `/api/compose`, `/api/paint`, and `/api/paint/stream` paths use the same shared pipeline service, and the shared registry is authoritative for all 11 canvas formats. The normal Android UI reaches the same shared Rust through `InkuRepository`, `AndroidWorkPipeline`, and JNI. The camera DDL prompt also uses the shared Stage 1 vocabulary projection. When history does not contain the sent prompt, display must not reconstruct an old prompt and present it as a record of what was sent.

After selecting ordinary history, description generation and DDL drawing wait for that same history to be identified before taking its corresponding fork, preserving the original description, saved settings, and parent relation. A pending or failed lookup, or an invalidated selection, never means a new work. An operation cancelled while waiting or belonging to an earlier selection must not start later.

### 12.8 Error Recovery

Each LLM stage makes retry decisions only within its caller-supplied
`max_attempts` and `total_timeout_ms`. Transport failures and empty, too-short,
or schema-invalid responses may consume another attempt within that finite
budget; provider rejection and generic semantic failure remain terminal. On
exhaustion it does not switch models: it either completes finitely through the
deterministic fallback or fails explicitly. A fallback is a compatibility
delivery path for explicit DDL, not a way to add new content.

When the shared compiler cannot fully accept a core-generated Stage 1 candidate before its
visible commit, the core may spend the remaining Stage 1 `max_attempts` and
`total_timeout_ms` budget on corrective normalization. It sends the original
description, the unadopted DDL, and a bounded projection of compiler reasons,
source spans, and their exact source excerpts when present to the same Stage 1
under the same response schema, and requests a complete replacement DDL. Because
this feedback changes the payload, the
correction is a new logical action with a new request digest; transport retries
and corrective actions consume the same finite Stage 1 budget. Candidates under
correction remain in the request context retained for durable execution replay.
Only ordinary full acceptance or the conditional residual adoption below may
enter a visible-DDL commit.

After corrective-normalization budget is exhausted, a candidate may propose its
entire unchanged DDL through the ordinary authority-revision and source-digest
CAS save only if the existing compiler's sealed execution projection, lowering,
and resource checks establish drawable content. This is not full semantic
acceptance and does not change the original lock to `CanonicalReady`. A missing
canonical semantic identity stays None; the remainder's execution identity and
the original omission owners, spans, and reasons remain separate. Omitting an
unknown span can retain an established head in the same clause: this is neither
sentence slicing nor proof of equivalence for unknown meaning.

Pre-save evaluation determines eligibility only. Only Score recompiled from
the entire source after the host's matching save acknowledgment is delivered.
Residual adoption does not open another known-hole LLM request, and ordinary
delivery and persistence retain `complete_with_omissions` and the original
diagnostics. Integrity failure, no drawable content, total omission, or failure
after acknowledgment stops execution; an empty work containing only background
is not success. The existing rule that valid ground is drawable content remains.
This never rewrites the original description or candidate, adds unspecified
meaning, disables guards, or admits Stage 1 candidates unconditionally.

This correction applies only to compiler rejection of an uncommitted
core-generated Stage 1 candidate. It never rewrites direct or already accepted
author DDL, and it ends once the source has canonical pre-expansion meaning;
later Macro expansion budget or integrity failures are terminal.
Provider-reported generic semantic failure and hole-patch semantic validation
also remain terminal, and the host neither repairs meaning nor retries on its
own. The correction returns DDL through Stage 1 rather than reducing counts,
relaxing the compiler, patching Score, or asking a later LLM to alter hidden
meaning.

Responses and saved history retain the fallback reason per stage, the models
used, and provider-failure classification; the UI identifies the affected
layer. `interpret_fallback` and `compose_fallback` distinguish a reason,
`"none"`, and absence from records created before the field. Refining from a
marked parent asks once before execution, and existing works are not backfilled.

In the shared compiler consumer, Stop and OmitAndContinue are deterministic execution policies over the same verified input rather than LLM fallbacks. Continue omits an appearance field when the existing default can resolve it, and omits an unbound Macro caller action or unsupported instruction layout direction as a field while retaining its body. Other invalid instructions, Emits, invocations, or structural subtrees, and unsupported Ground, groups, or relations are omitted as their typed units. Integrity failures stop both modes, and omitting every unit is not reported as a successful empty work.

### 12.9 Where Implementation History Lives

The back-to-front implementation order, initial prompts, and completed phases
live in [CHANGELOG.md](CHANGELOG.md) and the [public history
archive](docs/history/changelog-v0.1-v1.71.md). This section starts no new
implementation order.

### 12.10 Handling Latency

`POST /api/paint/stream` reports finite progress as `sketch` (when the sketch
layer ran), `stage1`, `score`, and `done`. `stage1` can expose normalized DDL and
diagnostic metadata before drawing completes; `done` carries the normal
response. "Another composition" and "Paint from DDL" resume from saved DDL
without calling Stage 1 again. A separate Stage 1 cache and future parallelism
are not part of the current contract.

### 12.11 The Intermediate Filter (Stage 1.5)

Stage 1.5 is a deterministic typed transformation that uses no LLM. Its input
is lock-verified `CanonicalReady` typed meaning, never free prose. Its output
is the effective DDL / typed meaning consumed by the shared lowerer.

- source text, normalized DDL, original typed meaning, effective meaning, and
  source / generated provenance remain distinct; original meaning and explicit
  attributes are not overwritten
- it invents no sentence, entity, relation, technique, color, touch, primitive,
  or content
- only `place:center` maps to one of a closed set of six focus candidates;
  every other place and explicit attribute passes through
- when the verified view lowers to an actual Score, a direct
  `Instruction { instruction_index }` owns only the instruction with the same
  source index. A direct coordinated group retains that rule and delivers its
  members through a separate `placement_groups` range. `GroupPredicate` and
  `MacroEmit` are not treated as same-index owners, numeric positions are not
  focus targets, and original center is not rewritten to a provisional `(0.5,0.5)`
- baseline focus selection is bound to lock-verified pre-expansion meaning and
  expanded-meaning digests plus an attested optional `composition_seed`; absent
  seed and present `Some(0)` differ, and the full compiler-lock digest is a
  source-integrity attestation rather than focus material
- explicit noncenter place never enters the focus targets; the shared lowerer resolves it to the regions in §18. Corner selection belongs to composition, using original meaning, attested optional seed, and original logical occurrence
- an explicit angle passes through as original typed meaning and does not join
  the center-only target set or variation axis. The shared lowerer selects its concrete
  angle from the same verified pre- and expanded-meaning digests, tagged
  optional `composition_seed`, and either the direct original logical ordinal
  or the Macro semantic ordinal, expansion path, and generated ordinal
- before detaching the Stage 1.5 input, admission checks the actual visible
  DDL UTF-8 bytes, language evidence retained by semantic source occurrences,
  every macro-sidecar triple including unused entries, and each executed
  macro's resolved, binding, and semantic-head identity against the compiler
  lock. An input with no `SourceOccurrence` gains no language condition, and
  an unused sidecar need not resolve or execute. Source and provenance are
  admission-integrity evidence, not meaning or focus material
- explicit variation is complete only when both amplitude (`small`,
  `medium`, or `large`) and `variation_seed` are present, and it moves focus
  only; an incomplete request means no variation
- output canonical bytes, schema identity, digest, and provenance reproduce the
  same meaning and never present bytes from another schema under the same
  identity

The sealed Rust Stage 1.5 v5 typed foundation, R1 / R2 / D1, direct normal and
explicit geometry, finite flat Macro Emits, and the shared local recoverable-error
policy are implemented through an actual Score and used by the normal Server and
Web pipeline. The `compile_ddl_to_score` facade compiles the original
`NormalizedDdlDocument` exactly once and retains its source, state, lock, and issues.
Legacy Stop and Continue inputs use the same compilation's typed owners and dependencies
to build a sealed projection. Recoverable upstream holes or conflicts omit their established
local unit and deliver independent instructions; omitting every drawing unit is stopped.
Canonical pre-meaning reuses the exact subset of successful macro output with its
original binding, source and semantic ordinals, seed, and provenance, without
reseeding or re-expansion. A noncanonical pre-expansion projection finalizes its
omissions before one seed derivation and expansion and never retries a draw after a
local failure. Global budgets and source, lock, owner, definition, or provenance
integrity failures stop both modes. The public Stage 1.5 API remains
`CanonicalReady`-only and cannot recover an arbitrary mutable compilation. D1
meaning, seed, focus, source-ordinal gaps, and generated provenance are preserved.
The added sizing rules update the geometry policy digest, and Score 0.2.0 carries
the new moon descriptor. The normal Server, Web, and Android paths use this
shared pipeline while keeping their existing public entry points, and saved
compact Score replay has passed on Linux.

This shared-compiler subset delivers direct and flat-Macro angles for
circle, ellipse, cloudform, and square through the shared lowerer to actual
`Score.rotation`. Square uses the same angle resolver for direct and flat Macro
Emit input. Only numeric placement must fit the rotated declared rectangle;
named focus adds no must-fit check.

The same shared-compiler subset delivers finite two-step thinness from direct and flat
Macro Emit input to actual `Instruction.thinness`, and binds explicitly declared thinness and size
parameters through §4.6.


Full-width and half-width use 100% and 50% of the canvas width before rotation. Their reference dimension is line length, open-arc chord length, the base outline width of a closed shape, or declared cloudform width. Uniform scaling preserves the shape and aspect ratio. Rotation and stroke variation do not trigger another width measurement or force edge contact or repositioning. Ordinary DDL and declared flat Macro Emit `proportion_width_extent` fields use the same size resolver.

Semicircle is an upward open semicircle; waxing bulges right and waning left. Crescent is the thin closed filled moon shown in the saijiki, never a single open arc. Score 0.2.0 represents it with `primitive: arc`, `arc_form: crescent`, `center`, and `size`. Its reference is the saijiki's three cubic Bezier curves, sized by their actual bounds. An absent `arc_form` retains legacy open-arc meaning and canonical bytes, and saved Score 0.1.0 remains readable. Position, rotation, and bounds use the shared renderer. Endpoint-only connected/touching relations reject the closed crescent with a diagnostic.

The shared Stage 1 grammar projection does not use an arc-form term in the saijiki proportions as an independent head; it attaches the term as an accepted noun modifier immediately before its corresponding arc head. This projection only explains the existing proportion surfaces and `arc_form` applicability; it changes no vocabulary, recognition, lowering, or rendering behavior.

Overlapping size specifications retain all original candidates. The resolver independently computes their physical reference dimensions and chooses the smaller extent, scaling the original shape once without multiplying relative size into explicit size a second time. Equal duplicates also produce an error. `ConflictingSizeSpecifications` records candidate and effective extents; its `Recovered` disposition draws the shape under both Stop and Continue. This exception applies only to size overlaps, not shape incompatibility, unsupported attributes, or source/lock integrity failures. The normal Server, Web, and Android paths use this shared compiler-to-Score-and-diagnostics route; Python and Kotlin are host bindings and own no separate meaning branch.

### 12.12 Staffage and Compatibility Records

Current generation has no staffage level. The shared compiler and lowerer do not add
elements absent from the description; recovery is limited to delivering explicit
content. Resolving an explicit angle does not add staffage or visual content;
it delivers an existing typed identity into `rotation`. Historical
`history.tenkei` and API `tenkei` remain readable for
compatibility but do not affect the generation contract for new works. The
introduction, retirement, and historical counts live in
[CHANGELOG.md](CHANGELOG.md) and the [public history
archive](docs/history/changelog-v1.72-v2.4.md).

### 12.13 Variation (Stage 1.5)

Lock-verified pre-expansion meaning, expanded meaning, and an attested optional
`composition_seed` carry composition identity. The full compiler-lock digest
attests source integrity and does not require equivalent expressions to have
the same lock. "Another composition" reuses saved normalized DDL and selects
focus from the closed six candidates, and also reselects the concrete angle
when an explicit angle identity is present, or the corner when corner is explicit. There is no current `vary_seed`
input.

Explicit variation is the pair of amplitude (small, medium, or large) and
`variation_seed`. Only a complete pair moves focus. The same lock-verified
meaning, attested composition seed, amplitude, and variation seed produce the
same effective meaning. Composition family, color, touch, technique, relation,
and element count do not move.

The current Score and render identity domain is `rh3`. `rh2` is a legacy
domain for reading saved works and is not the current identity for new
generation. The history of reducing seven variation axes to one lives in
[CHANGELOG.md](CHANGELOG.md).

### 12.14 What the Renderer Owns

The Renderer performs a validated JSON Score into SVG. It realizes coordinates,
materials, sway, primitives, texture, and canvas ratio without inventing visual
content absent from Score. The current authority is the platform-independent
Rust `inku-render` core (Render Engine 66); Python and Android are hosts that
pass resolved options into the same core. Native rasterization belongs to the
separate `inku-svg-raster` boundary.

Shared Rust owns Score structure and meaning. Python retains saved-format read compatibility, including finite actions such as a warned drop of an invalid legacy relation. Hosts must not add a visual event, composition anchor, density floor, or accent shape.
Renderer sway is bound to `render_seed` and does not alter canonical Score.

The SVG profiles are `display`, `editable`, and `compat`. The database stores
the `display` SVG; the other profiles are generated from saved Score on
request. Sections 13.8 and 13.11 define performance and render identity, while
history lives in the [render-engine version history](docs/spec/render-engine-history.md).

### 12.15 Saved Compatibility for the Old Sketch Layer (Stage 0.5, v2.9.38)

The following is historical context for reading old works. The normal pipeline does not rewrite a new description into sketch prose; it retains only previously saved sketch information.

An **optional layer** between the description and Stage 1.  A description as dense as a tanka is
more than Stage 1 can chew at once, so this layer rewrites it as **plain prose naming things** --
a sketch from life -- before anything downstream reads it.

The prose **stands in for the description at three consumers**: Stage 1, the plugin expansion
(deciding whether a plugin fires), and Stage 1.5.  **It does not reach Stage 2 or coerce**
(v2.9.41): **those two read the DDL alone**, because showing prose to a layer that runs after the
plan exists makes an addition traceable to something the author wrote indistinguishable from a
delivery of the DDL.  **The plugin's seed** -- what decides how many leaves, how many lines -- **is
the description**, not the prose: the same description resolves the same numbers however the prose
changes.  **The description itself is kept for saving and display.**  The work is what the author
wrote, not what the layer wrote.

This paragraph is limited to the pre-cutover legacy runtime and its historical
description. The typed pipeline's macro-meaning rule and focus seed source are
defined by §§4.5 and 12.11; source text or sketch prose does not return as a
typed macro seed source.

**One background guard was withdrawn** (v2.9.41).  It recognised "the user pasted a
machine-generated plan into the description box", and what it judged was the *provenance of a
string*; once the description no longer reaches coerce there is no provenance left to judge, and
keeping it misfires on the ordinary shape of a production DDL -- **54 of 604 dark-background works
fell to white with it, 1 without**.

**The granularity (`sketch_grain`) has two values**, `fine` (many short sentences, the default)
and `coarse` (fewer, longer ones), chosen per draw.  What differs is the cutting, not the total.
Redrawing with a different grain writes a `sketch_grain_change` edge into the genealogy; the same
grain stays a replay.

**When the layer fails the description goes to Stage 1 unchanged and the paint still completes.**
A failed attempt is not recorded as prose.  A saved work redraws from its stored prose without
calling the layer again.

**What the layer did is recorded on the work** (`sketch_state`, v2.9.43).  Absent prose can mean
**four different things**, so the state is written down separately: `fine` / `coarse` (the layer
ran and produced prose at that grain), **`fallback` (it ran and fell over)**, `off` (it was
available and the caller chose not to route through it), and `not_applicable` (this route never
calls the layer).  **`NULL` marks only a work drawn before this record existed; it is not a
synonym for "off".**  The column carries no default and is never backfilled -- filling it would
destroy the one fact it holds, that the work predates the layer's record.  **A single function
names the state, and every save path and every response goes through it.**

The layer must not emit words of feeling (design principles 3 and 7, section 13.3).  Its prose
names things, their placement and their state.  **It follows that meaning words absent from the
normalized DDL are the design, not a carriage failure** -- "night" travels as "fill the background
with black".  A gate that measures carriage by matching tokens reads that translation as loss.

### 12.16 The Description Is Where the Work Comes From (v2.9.44)

A description is not a record.  **It decides whether a plugin fires, what Stage 1.5 reads as
context, what seeds the plugin expansion, and which language the instruction is written in --
four things.**  A string that did not author the DDL is therefore never seated in the
description's chair: the description is the text the author typed, and no entry point offers a
way to paste a different one over it afterwards.  Redrawing an existing work with a rewritten
description (refinement) is a different operation, not a change of origin.

The prose-driven plugin firing, description seed, and Stage 1.5 context here
are limited to the pre-cutover legacy runtime. §§4.5 and 12.11 define the
typed pipeline's meaning and seed rule; this explanation does not restore
source text or sketch prose as a typed macro seed source.

**A description the cut empties is not accepted.**  Leading numbers and bracketed notes belong
to the author rather than to the drawing (v2.9.40), but **a description that is nothing but
those** would leave the layers below inventing a subject from an empty string.  The three
drawing routes (`/api/interpret`, `/api/paint`, `/api/paint/stream`) refuse it with 400, and
**a description that is only whitespace with 422**.  **The judgement takes two conditions**: an
empty raw description is already refused by another check, and judging the cut alone would
answer "only labels" to a text that carried no label at all.

**The route that draws an instruction sheet (`/api/compose`) carries no such guard.**  A work
authored straight in DDL has no description, and drawing a sheet without one is that route's
purpose.  **The description key is absent there rather than empty.**

**The gate at the entrance reads what the drawing reads.**  The length guidance on the
description field blocks no input (section 7.1), but **sending is judged on the text after the
cut**: a description that is labels from end to end cannot be sent.  This is not a second rule;
it is the drawing's own rule, moved to the door.

---

The shared Rust `plan_verified_stage15[_with_policy]` API takes verified Stage 1.5 and the existing host canvas / color catalog context. Ordinary instructions and declared flat Macro Emits share one object-size / placement resolver. Omitted quantity resolves to eight for `line-up`, `scatter`, and `tile`, and remains one for `place`; source meaning stays omitted. Explicit positive integers through u32::MAX are preserved. Zero, out-of-range, unknown, conflicting, or qualitative quantities and missing required Macro arguments do not become eight.

Object size uses the canvas short edge independently of count, cells, or density. Delivered plans support all nine primitives: line, circle, ellipse, square, triangle, polygon, arc, cloudform, and point. Normal width or diameter is 6/25; ellipse / cloudform height is 3/5 of width, arc sagitta is 3/50, and point diameter is 3/250. Existing size factors and shape-specific anchors remain, and thinness does not change outer size. A large circle keeps diameter 9/25 at both four and eight objects, allowing overlap. Numeric geometry retains its exact decimal / Rational, basis, dimension, and provenance.

Shape constraints are optional meaning separate from primitive identity. Equilateral triangle remains triangle; regular square remains square; pentagon through octagon remain polygon. Core-head continuations preserve these constraints and their source ownership. Absent constraints add no null field to old canonical or source bytes. The ordinary triangle is an isosceles triangle with its apex above the base and normal width = height = 6/25. An equilateral triangle retains exact side s and the fixed height rule s√3/2 in the plan; only the final geometry boundary evaluates the irrational height. Ordinary square retains its 1:1 default but accepts independent WidthHeight through the existing square wire. A regular square requires equal sides. Polygons are regular, default to five sides, accept five through eight, and interpret Radius / Diameter as the circumcircle. Side count is distinct from object count.

Tall / wide constraints reach the same triangle / square / ellipse / cloudform consumer. Without numeric dimensions the long extent is 6/25 times the size factor and the short extent is half that. Explicit WidthHeight is preserved and checked for the requested ordering. Conflicts, regular plus aspect, and out-of-range sides stop or omit the original instruction / Emit with a diagnostic. Finite Japanese and English grammar includes 横に長い四角形, 一辺0.24の正三角形, 六角形, wide rectangle, and equilateral triangle. Triangle and square use the physical bounding-box center as semantic anchor and convert to Score top-left plus size. Polygon uses center / radius / sides. Numeric rotated vertices are checked at the final geometry boundary; named positions retain the existing regions and clipping policy. Ordinary DDL and declared flat Emits share the resolver: place / count one reaches actual Score, while repetition reaches a Ready plan without creating instances.

Non-Grid domains use the physical canvas axes and place the group centroid at the semantic anchor. Direction-omitted line-up is one horizontal row at equal-width cell centers. Tile uses columns=min(n,max(1,ceil(sqrt(n*W/H)))) and rows=ceil(n/columns) when W>=H; when H>W, the same rule starts with rows on the long axis, then columns=ceil(n/rows). It fills n cells in row-major order and resolves rows, columns, cell dimensions, and filled count. Numeric anchors translate the exact filled-prefix centroid; named Grid stays in its region without centroid correction. Scatter retains a uniform X/Y rectangle-sampling recipe followed by centroid translation, requiring the existing performance seed and original owner / instance ordinal at materialization. It does not substitute composition seed, run RNG, resize to fit, change count, or add repulsion or minimum spacing. For example, on 1200×800 / 800×1200 canvases normal circle diameter is 192 in both cases, four-object line-up spacing is 300 / 200, and eight-object tile is four columns by two rows / two columns by four rows.

Optional instruction / Emit `layout_direction` owns arrangement direction independently of entity `angle`. Japanese examples such as “中央に、横線を縦に三本並べる。” and “中央に、斜めの線を横に三本並べる。” share the typed entrance with “arrange three horizontal lines vertically at center.” and “line up three diagonal lines horizontally at center.” Japanese particle evidence and English angle-row adverb forms separate the roles. Compiler-only parser aliases leave prompt, display, and legacy markers unchanged. Single-head continuation merges direction into the original entity; conflicting directions stop. Absent-field canonical and provenance bytes remain unchanged; a present field includes its meaning and complete source evidence.

Only line-up delivers direction into placement. Omission retains the horizontal row; explicit horizontal uses the same formula while preserving its explicit identity. With t=(i+1/2)/n-1/2, offsets from the anchor are horizontal=(tW,0), vertical=(0,tH), rising=(ts,-ts), and falling=(ts,ts), where s=min(W,H). Diagonals are physical 45-degree axes with downward-positive Y, never stretched to the canvas diagonal. Bare diagonal chooses one of the two axes using the attested optional composition seed (distinguishing None from Some(0)), original pre / expanded meaning, and original logical occurrence framed with a dedicated layout-direction role. Shape-angle selection, size, and count are unchanged. Focus, variation / render seeds, and source spelling do not select direction. Point accepts layout direction while still rejecting its own angle. Unsupported layout direction on Place / Scatter / Tile, or an unsupported identity such as rotated, is omitted as a field with its original owner, spans, and reason, retaining an instruction or Emit whose body, explicit count, action, and position remain valid without it. Direction is not repurposed as entity angle. Unsupported group / relation structures and other failures retain their existing omission units; an entirely omitted result stops in both modes. The existing Score entrance likewise never silently discards an unsupported field and reports complete success.

One plan per instruction / Emit retains exact count, resolved dimensions, appearance, angle, position, layout recipe, and source / generated origin. There are no count-proportional arrays, instance geometry, or duplicated Score instructions. For either legacy Stop or Continue input, recoverable blocking preserves typed owners, spans, reasons, and actual omissions at the smallest affected field or execution unit, returning the remaining plan. An entirely omitted result is never marked Ready. Unsupported fields, relations, and coordination are not silently discarded. The resource-aware materializer maps this plan to replayable recipes with Score 0.10 as the compact baseline, selects the minimum later version required by added fields, and checks demand before instance allocation against both hard policy and a caller-authorized operational budget. Current shipping limits are 400 total primitive marks, 240 primitive marks per expanded Score template, resolved count 2000, and 64 drawable templates, plus 4096 `logical_objects`, 128 `template_nodes`, 4096 `anchor_instances`, 4096 `transform_instances`, 64 `placement_instances`, and 64 `fill_instances`. Administrator control of the existing four limits and budgets saved by older works remain intact. When an explicit count on a standalone primitive exceeds the budget, the original Plan and source retain the requested value, while the Score receives the largest safe source-ordered prefix and resource diagnostics carry the requested count, executed count, and reason to display, persistence, and structured logging. Only a unit for which no instance can run safely, or a coordinated placement / Macro whose structure cannot be partially executed, is omitted at its typed boundary; independent later work continues. A saved Score snapshots the authorized policies but stores no self-reported demand; replay recomputes demand from its recipes. Existing Score wire, lowering outcomes, compiler execution success, and Score 0.9 default / legacy compatibility remain. The same `inku.geometry-resolution-policy.v1` attests this resolution. The normal Server, Web, and Android paths and saved compact Score replay use this shared materializer and local-recovery contract.

## 13. The Design of Sway

Sway is intentional.  DDL does not attempt to eliminate all model or
renderer sway.  It uses sway as part of the medium, while keeping the
score, schema, and renderer boundaries explicit.

### 13.1 Sway Is Not Randomness

Sway is not simply randomness.

- **Randomness**: disorder. What happens cannot be predicted.
- **Sway**: fine movement inside order. The core intent holds still while the surface moves.

The bend of a bonsai branch is sway. It is not a tree that grew at random: a
gardener decided the basic form, and nature moves the detail from there. Reciting
a tanka is sway too. The 5-7-5-7-7 form does not change, but the pitch, the
pauses, and the breath differ every time.

DDL's sway is sway in this sense.

### 13.2 The Three Roles Sway Plays

**Role 1: it minimizes the author's intervention.**
Sway made only of numbers and motion words carries no feeling and no intent.
"Chance" makes the final decision in the author's place — the same structure as
LeWitt writing the instructions and then leaving them to the draftsman's hand.

**Role 2: it guarantees that the output happens once.**
The same description yields something different every time. The description
remains; the output disappears. This structure is what makes the metaphor of
performance real rather than decorative.

**Role 3: it makes room for the viewer.**
A perfectly mechanical output is finished. With sway, there is room for the
viewer to read the sway as meaningful — the way a Rothko color field is not
perfectly flat but holds a faint movement.

### 13.3 Motion Words and Emotion Words

In anything written about sway, **motion words and emotion words are kept
strictly apart**.

**Motion words (allowed):**

```
swaying finely, undulating slowly, scattering, trembling faintly, shifting, blurring
```

These describe physical movement. They are behavior observable from outside.
They describe how the work behaves, not what the work is worth.

**Emotion words (excluded):**

```
swaying beautifully, swaying delicately, swaying gracefully, swaying boldly, swaying violently
```

These are the writer's subjective judgment — an intervention in the work. They
run against DDL's principle of excluding emotional vocabulary.

**The boundary (left to the LLM's reading):**

```
slightly, a little (degree expressions, but leaning toward feeling)
```

In tanka too, "a beautiful flower" is judgment while "a flower swaying in the
wind" is observation. DDL judges by the same distinction, and Stage 1's reading
is what decides the boundary case.

### 13.4 The Three Layers of Sway

Sway arises from three layers. Priority runs **plugin > motion word > material**.

```
[sway inherent to the material]  (always present; the writer does not think about it)
  the natural sway of pencil, brush, chalk and the rest

  ↓ overridden when the writer specifies

[sway named by a motion word]  (the writer can write this)
  finely, slowly, scattering, trembling

  ↓ overridden again when a plugin is named

[sway caused by a phenomenon, via the Nature plugin]  (called explicitly)
  Nature.風 (wind), Nature.うねり (swell)
```

The three layers match the way bonsai is thought about:

- the **material** (the species) has its own nature
- the **gardener's hand** enters (motion words)
- **the environment** (wind, season) is laid over it (plugins)

**Thinness is a dimension, not a sway** (engine 16, v2.9.3). It does not belong to the layer where `weight` carries the sway inherent to a material. A tool has a thinness as its default, but thinness itself is a dimension the writer states independently, and it falls **outside the three layers** (material, motion word, Nature plugin). It has steps on the thin side only; there is no vocabulary for the thick side. `Instruction.thinness` (`fine` / `extra_fine`) carries it. **The principle gains no exception; thinness is placed outside the three layers instead.**

The finite visible DDL forms are Japanese `細い` / English `thin` for Fine and
Japanese `ごく細い` / English `extra-fine` for ExtraFine. The shared compiler
keeps both as typed identities independent of source spelling and carries them from supported direct
instructions and flat Macro Emits through the common lowerer into the existing
`Instruction.thinness`. Omission remains `None`; no thick step or open-ended degree synonym is inferred.

Note that **`thinness` is not a Saijiki word** (author's ruling, 2026-07-29). Stage 1 reads thinness words and writes them into the normalized DDL, but they appear neither in the §3.1 vocabulary table nor in the Saijiki display.

#### Wild (engine 12; its reach in engine 14)

**Separate from the three layers, one switch lifts the ceiling on the performance itself.** The UI calls it 暴れる — wild.

- **One switch for the whole work**, not per stroke and not per tool. **In engine 12 it reached only the line primitive** (circles, ellipses, triangles, squares, polygons, arcs, fills and hatches came out byte-identical with it on). **Engine 14 extends it to contours, arcs, fills and hatches**, so the implementation now matches the description
- **It removes only the amplitude ceiling and the ban on self-intersection.** Endpoint pinning and determinism hold when it is on: the same Score, the same seed, and the same state render the same SVG every time
- **It is recorded and replayed.** Stored as `render_wild` beside `render_seed`, and included in the edition identity (`rh3`). **The same Score performed wild and performed plainly are different works**
- **It is a multiplier on a tool's habit, not a source of one.** A tool whose wobble terms are zero (`rotring`) does not move when it is on. **A machine has nothing to unleash**

This sits in a different layer from variation (Stage 1.5). Variation is a deterministic transform of the score; wild leaves the score alone and widens the performance. (Layer responsibilities are in §12, and version rules are in §2.1.)

### 13.5 Weight Decides the Quality of Sway

Sway has quality, not only quantity. In DDL the weight — the material — decides
that quality implicitly:

| weight | quality of sway | character |
|---|---|---|
| silverpoint | almost_none | almost no sway (exact). The thinnest line a hand can draw (0.5px) and the one that wavers least. Pruned from the vocabulary in v1.92 under the name `hair`, and returned in v2.7.9 renamed silverpoint. Saved Scores that still say `hair` are rewritten as they load |
| pencil | perlin_fine | Perlin-leaning (the continuity of a hand), faint secondary lines, fine grain |
| pen | perlin_minimal | slight Perlin. The standard reference line |
| rotring | almost_none | uniform width, square ends, a hard drafting line |
| crayon | rubbed_noise | rubbing, short breaks, granular gaps |
| chalk | perlin_plus_noise | Perlin plus powdery scratchiness, blur |
| brush_thin | perlin_strong | thin brush track, secondary lines, density variation |
| brush_thick | pressure_blur | thick pressure, rubbed secondary lines, light blur |
| oil_paint | viscous_ridges | oil paint: loaded broad strokes, bristle ridges shaded from the selected color, and overlapping paint strokes across filled surfaces suggest impasto |
| burin | almost_none | a hard, certain engraved line. Round ends, no texture filter |
| drypoint | burr_noise | bleeding and scratchiness from the burr. Its own burr treatment |
| computer | periodic_quantized | it sways, but **it repeats without error**. Integer-period sine and rounding to a lattice. The material is what sampling leaves behind (see "engine 13" in the [version history](docs/spec/render-engine-history.md)) |

Reference §6 is the source of truth for the numeric characteristics (stroke
width, opacity, dasharray, presence of a filter).

#### Tool-specific fills and intensity

Closed fills carry the selected tool's texture. From Score 0.3.0 onward, `surface_intensity` is `normal` (the default), `dense`, or `faint`; the normal value is omitted from serialized output. Saved Score 0.1.0 / 0.2.0 / 0.3.0 keep their original version when read and written. Direct DDL and Macro use the same lowerer, and repeated plans retain intensity in their appearance before materialization. Changing intensity does not change the selected color identity or the seed that determines shape and stroke geometry.

| Tool | Fill appearance |
|---|---|
| Silverpoint / pencil | Fine, quiet silver traces; broad side-of-lead pencil rubbing. Dense pencil reduces gaps, while faint pencil suppresses dark overlaps |
| Pen / rotring | Slight ink variation for pen; even, hard drafting ink for rotring |
| Chalk / crayon | Powder and paper gaps for chalk; wax rubbing with greater coverage for crayon |
| Thick / fine brush | Ink variation and brush drag. Normal is already dark; dense is darker |
| Burin / drypoint | Sharp, controlled engraved lines for burin; soft, furry black lines for drypoint. Irregular placement breaks the visible repetition |
| Oil paint | Broad paint tracks and pigment-derived bristle relief. Dense strengthens and simplifies the ridges; faint makes deposited paint translucent |
| Computer | Vertical RGB bands, black interlaced scanlines, and a soft glow evoke a CRT. Dense lowers brightness; faint raises it |

Compact shared patterns, masks, and filters carry grain and line textures; oil paint uses filter-free paths. Oil fill width and spacing are three times the baseline. One oil interior fill lays down at most 24 loaded passes, and all oil interior fills of a work share a budget of 120 passes (at least 3 each), widening the passes of a work with many large oil fills so its SVG stays bounded (render engine 67). Interior ridge contrast is 0.6 / 1.05 / 0.6 for normal / dense / faint. Dense simplifies paired ridge banks within 0.25 per 1000 short-edge units before widening; faint applies opacity 0.54 to each paint stroke. The base and outline are not widened. Compat preserves its filter-free, clip-free approximation: Computer retains the contour-path base field, grille, and black scanlines, while Oil retains shape and intensity through its existing paint passes without clipped width expansion. Compat does not promise pixel equality with Display.

Typed DDL intensity delivery covers solid closed fills. Non-solid textures, unfilled lines and arcs, and explicit Point surfaces retain the existing unsupported diagnostics. Score rendering capability and the delivered typed-DDL subset are distinct. Full typed runtime / UI / save integration remains a later task.

**Kinds of sway noise:**

- **White noise**: each point independent, uncorrelated, jagged
- **Perlin noise**: continuous, neighboring points similar, a smooth wave
- **1/f sway (pink noise)**: common in nature, and what people read as "natural"

A drawn line carries continuity from the inertia of the hand, so Perlin-leaning
noise is the natural choice.

### 13.6 The Categories of Motion Vocabulary

The Saijiki carries a category called ゆらぎ (movements).

**Japanese, ゆらぎ:**

| Dimension | Vocabulary |
|---|---|
| amplitude | 細かく, 大きく |
| frequency | 速く, ゆっくり |
| quality | 揺れる, 波打つ |
| spread | にじみ |

**English, movements:**

| Dimension | Vocabulary |
|---|---|
| amplitude | fine, large |
| frequency | quickly, slowly |
| quality | swaying, undulating |
| spread | bleeding |

`bleeding` is the single movement word and delivers independent `ink_spread:"bleed"`.
Display and Editable apply it after combining the contour and surface marks.
Compat preserves the marks, omits ink spread, and reports `texture_degraded`.
It combines with Wave, Perlin, and the stipple surface, but does not add Perlin by itself
or introduce an intensity word. Current `blurring` input normalizes to it.

Scatter in placement is not ゆらぎ. It is carried by うごき (motions, "scatter")
and by `arrangement` (layout / path / jitter).

In the shared compiler, ordinary DDL and declared flat Macros use one resolver. `fine` / `large` map to Fine / Broad; `slowly` / `quickly` to Slow / High; `swaying` (and its accepted legacy `trembling` forms) maps to Perlin; `undulating` maps to Wave; and `bleeding` maps independently to `ink_spread:"bleed"`. With all three variation slots absent, `Instruction.variation=None`. When at least one is present, only the missing amplitude, frequency, and quality slots default to Medium, Medium, and Perlin. Ink spread alone does not create variation. Explicit values win and the dimensions are independent: swaying does not imply Fine or High. Defaults do not enter source or typed meaning. The existing geometry-resolution-policy author-resolved omission owner attests this shared definition.

### 13.7 Sway from Phenomena: the Nature Plugin

`Nature.leaves` connects seven bundled MacroDefinition v1 motifs — `Nature.若葉`,
`Nature.下草`, `Nature.青葉`, `Nature.紅葉`, `Nature.落葉`, `Nature.枯草`, and
`Nature.枯葉` — from the shared catalog through the ordinary lock / expansion
boundary. Definitions emit core meaning from closed typed parameters, bounded
repeat, typed transforms, and deterministic bounded vary; they write neither raw
Score fields nor renderer instructions or noise algorithms. Server and Android
use the same catalog for resolution and display.

This connection does not provide an external runtime loader, an arbitrarily
installed package, or an official registry for the whole `Nature` namespace.
`Nature.雨` and `Nature.風` remain conceptual examples, not bundled catalog
entries. The v1.70 hard-coded Nature expansion is legacy compatibility, not new
semantic canon or a permanent fallback. Saved Score / expanded artifacts take
precedence, and an absent artifact is not silently rendered as another shape.

### 13.8 Sway Is Generated in the Renderer

The random generation for sway happens in the **renderer**, not in the JSON Score.

**Why the design puts it there:**

| Layer | Role | Determinism |
|---|---|---|
| DDL text | description (native language) | deterministic |
| normalized DDL | instructions (core vocabulary) | deterministic |
| JSON Score | score (structured instructions) | deterministic |
| **Renderer** | **performance (sway realized)** | **non-deterministic** |
| SVG | output (happens once) | generated each time |

The JSON Score is a score; it does not contain the performance. The score holds
the *instruction* for sway — amplitude, frequency, quality — but not the concrete
random values. This gives:

- replaying the same JSON Score produces a different SVG every time (a capability the Android app already had)
- the JSON Score becomes meaningful as an archive
- changing the sway seed produces several performances from one score

**The performance has freedom at two scales (v1.51):**

| Scale | What it is | Written in |
|---|---|---|
| micro | line tremble, blur, grain, rubbing | §13.9 `variation` |
| macro | performance-time resolution of placement written as relation and region | §14.4 sequential resolution |

The score records a relation — "not touching the previous line, at a narrow
interval" — and the performance decides the actual position each time. This is
what makes "a different performance every time from the same score" work at the
level of composition rather than at the level of a few pixels of tremble. The
earlier implementation realized only the micro scale, and macro sway was assigned
to no layer at all. That was the primary cause of the uniformity observed in
Build 436.

**The three layers of a tiling performance (v1.75):** `layout="grid"`, which the
writer states explicitly, is performed in three layers: (1) a small within-cell
displacement from a deterministic hash derived from the performance seed, (2) the
existing `variation`, whose phase differs per element, and (3) the existing
material sway of pencil, brush, chalk and the rest. The same Score with the same
render seed is bit-identical, and when the seed changes the hand differs while the
order holds. Because a full repetition is itself the writer's intent for a grid,
the bias, fade, cluster, preserve-space and count-representation treatments meant
for scatter are not applied to it.

**The support resists (v2.9.16 / render engine 19):** sway does not live on the tool's side alone. **In painting the role of the ground is to resist the hand** — an absorbent sheet lets the ink spread, a toothy one refuses the tool and leaves the paper bare. Until engine 18 the ground and the drawing were composited independently and never met, and since `canvas.ground` appears in 1.7% of stored works and 0% of the frozen SVGs, a condition placed on the ground side reaches nobody. Engine 19 gives **every work a default support**. **The sheet is one constant; whether a tool is drunk (`absorb`) or refused (`tooth`) is a property of the tool** (a brush is drunk and swells; crayon, pencil and chalk are refused; `rotring` and `computer` are machines and never touch paper). **Where the sheet refuses, no ink is laid down** — narrowing sinks into the antialiasing on exactly the thinnest tools, so being refused is bare paper rather than a thinner line. **The breaks become subpaths of the same `path`, so no element is added** (the three layers in §13.4 are material, motion vocabulary and phenomenon; the support is none of them, but **the thing the tool meets last, at performance time**).


### 13.9 The `variation` Schema in the JSON Score

The JSON Score's `variation` field is structured by dimension.

```json
{
  "variation": {
    "amplitude": "fine",
    "frequency": "high",
    "quality": "perlin",
    "dimensions": ["position_y"]
  }
}
```

| Field | Values | Meaning |
|---|---|---|
| `amplitude` | `fine` / `medium` / `broad` | amplitude (from motion words) |
| `frequency` | `slow` / `medium` / `high` | frequency (from motion words) |
| `quality` | `none` / `white` / `perlin` / `pink` / `wave` | noise quality resolved from explicit motion words; material performance remains independent |
| `dimensions` | `[position_x, position_y, angle, length, rotation, radius]` | which dimensions sway. `thickness` was retired in v2.7.2 (declared but never read by the renderer) |

**The writer never writes this structure directly.** Stage 2, the structuring
layer, generates it from the combination of motion words, weight, and plugins.

In the current implementation the sway of a line is expressed by turning it into a
polyline in the renderer. Amplitude is a multiple of **the stroke's own width** —
`fine=0.35` / `medium=0.6` / `broad=2.0` (render engine 28; from v2.1.0 through
engine 27 it was a ratio against the shape's representative dimension, 0.025 /
0.08 / 0.18, and before that absolute pixels of 7 / 12 / 30 against a 1000px
canvas). **A sway happens where the tool meets the paper, so it is measured in
marks, not in figures** — read against the representative dimension, the same 8%
was invisible under a brush and a different line under a thin pencil. The clamp at
0.40 of the representative dimension stays, as the safety valve for a figure
smaller than its own mark.

`quality` is chosen roughly as follows:

- `perlin`: fine, irregular sway of a line — "trembling", "swaying finely"
- `wave`: low-period, legible undulation — "swaying slowly", "undulating"
- `pink`: blurring of the boundary — "blurring"
- `white`: coarse, noise-like scatter

Explicit sway in the shared compiler always uses `dimensions=["position_x","position_y"]`.
Line uses its existing perpendicular performer; Arc and circle / ellipse / square / cloudform
use their existing inward/outward contour consumers. Short-line thresholds, noise, seeds,
geometry, placement, angle, thinness, material, and relation endpoint contracts remain unchanged.
Point and unsupported shapes reject explicit variation. This is separate from Stage 1.5 focus-only variation.

The schema keeps `variation`, but it is invisible from the DDL text interface.
Only those implementing plugins or materials handle these dimensions.

### 13.10 The `arrangement` Path in the JSON Score

`arrangement` holds not only how many, but how they run and along what trace.

```json
{
  "arrangement": {
    "count": 21,
    "layout": "scatter",
    "path": "wave",
    "margin": 0.12
  }
}
```

| Field | Values | Meaning |
|---|---|---|
| `layout` | `horizontal` / `vertical` / `radial` / `scatter` / `grid` | base placement. `grid` is tiling that was stated |
| `path` | `none` / `diagonal` / `wave` / `top_to_bottom` / `left_to_right` / `right_half` | trace of the placement |
| `rows` / `cols` | 1-64, or omitted | rows and columns for a grid. When both are given, `rows×cols` wins |
| `jitter` | 0.0-1.0 (default 0.12) | deterministic displacement within a grid cell |

Correspondences:

- "along an undulating trace" → `layout="scatter"`, `path="wave"`
- "a diagonal band" → `path="diagonal"`
- "scattered from top to bottom" → `layout="vertical"`, `path="top_to_bottom"`
- "from left to right", "across" → `layout="horizontal"`, `path="left_to_right"`
- "the right half" → `path="right_half"`
- "radial", "concentric" → `layout="radial"`
- "tile it", "lay it out in a lattice" → `layout="grid"` (only when those words are explicit. The ceiling on count is a flat 2000 regardless of layout)

#### Where a group is placed (render engine 20)

**A layout decides the shape of the scatter, not where the group sits.**
An expanded group is placed with **its centroid on the coordinate the instruction
stated (its anchor)**, and whatever overflows the frame **[0.02, 0.98]** is shrunk
back **one axis and one direction at a time, by only what overflows there** — the
group is not scaled down as a whole, and marks are not clamped onto the frame.
`radial`'s `center` is its rotation centre, and **with none stated the ring turns
around the anchor**, not around the middle of the canvas.
**The one exception is a `grid` with an `at.region`**: a grid tiles the region the
description stated, so it stays there instead of moving onto the anchor.
Up to engine 19 every layout decided placement from the seed, and **77.8% of the
expanded marks never consulted a declared coordinate**.

#### Performance inside a typed placement (render engine 67)

A Score 0.10 `arrangement.resolved` recipe, anchor, and domain fix where a group lives and how far it extends. Inside that extent the renderer performs the same arrangement's `density`, `cluster_count`, `rhythm_spacing`, `jitter`, and `fade`. Scatter members gather toward `cluster_count` clusters (a density-dependent number when omitted) by an amount set by density; line-up members follow the `rhythm_spacing`; every recipe offsets positions by `jitter`; and `fade` attenuates intensity across the group. Several marks placed or drawn at one spot through the `place` recipe form a bounded bundle around it instead of an exact overlay. Performed members also receive the tool's existing member hand for size and rotation. Tiled grids are not disturbed by these fields.

Every choice is bound to `render_seed` and the original owner and reads only Score fields; nothing branches on words, subjects, or source text. `density: none`, `jitter: 0`, `rhythm_spacing: none`, and `fade: none` leave recipe centers unchanged. The compiler writes these explicit defaults when no performance vocabulary is present, so stored Score meaning is unchanged and only its replayed appearance follows this engine.

#### How a stated count is treated (v2.7.6)

In canonical meaning, a stated count remains lossless symbolic intent. The Step
11 pure ceiling preflight runs before expansion, allocation, or any other
O(count) materialization. Even a value such as `u32::MAX` is not clamped or
silently rewritten to a representative count. A standalone primitive
materializes only the safe source-ordered prefix and diagnoses the remainder;
only a structurally indivisible rejected unit performs zero allocation and zero
materialization.

The following records compatibility behavior in the existing Score / coerce
path. It does not redefine the symbolic intent above, and the runtime state
before the Step 11 cutover is not the new semantic canon.

| Request | Treatment |
|---|---|
| **under 240** | **literal. The requested value goes straight into `arrangement.count`** |
| **240 and over** | represented. `count` becomes 80-120, and `density` / `cluster_count` / `fade` / `preserve_space` keep the appearance of the group |

The threshold's default of 240 matches the default of
`max_expanded_per_instruction`. Raising the threshold alone to 300 would create a
band from 241 to 299 that is structurally impossible to honor — declared literal
while coerce cuts at 240 — so **normalization forces the two into agreement**
(v2.10.0). **A number the description states is drawn as stated up to the
threshold of its configuration** — at the defaults, "two hundred thirty-three
lines" draws 233 lines. **The threshold is a limit setting: move it and the band
that is drawn as stated moves with it. Which values a work was drawn under is
recorded on the work** (`history.render_limits`), so the configuration carries
reproducibility on the same footing as the version. **A redraw runs under the
values recorded on the work, and falls back to today's settings only when the row
recorded none; the answer names which of the two it used** (v2.13.30). A request
may lower a limit for a single drawing but never raise one — every element is
bounded against the settings in force.

**A stated count is drawn as stated even when the wording is not "only" or
"alone" (v2.11.20, ddl-engine 11; the band was widened in v2.12.1, ddl-engine
12).** Before that, only the emphatic form held a number; a count written the
ordinary way — "three circles in a row" — was overwritten by downstream
guesswork. **It reaches a group only when exactly one group answers to the
clause**: the group carrying the (figure, colour, weight) triple built from the
clause, or failing that the single group with the same figure. **With several
candidates, or none, nothing happens — forcing an ambiguous pairing would break
the number some other clause stated.** **The band comes from the literal
threshold itself** (239 by default; normalization keeps the threshold aligned
with `max_expanded_per_instruction`, so moving the setting moves the band).
**The same boundary is not given a second name** — written as a separate
constant, one of the two could move without anyone noticing. **At or above the
threshold, crowd representation governs and this branch touches nothing.**
**When the forced count would exceed the per-instruction or whole-work budget, it
is not forced rather than trimmed** — the branch runs after those budgets, so
nothing would remove the excess, and a trimmed count is **neither the number
stated nor the represented one**. **Where the number cannot be reached, leaving
it alone is the honest answer to the description.**

**Every reader counts the same way (v2.13.10, ddl-engine 14).** There is more than one place a count is
read, but only one way of reading it.

- **The language of the description decides.** The exclusion that drops a numeral sitting next to CJK applies
  **only when the body is Japanese**: a `12` written in an English body is twelve even where a plugin word puts
  kanji beside it (before this it was dropped). **All five callers of coerce hand the language over.**
- **The sentence is read only when the phrase naming the plugin states no count.** A count in the phrase is
  never overruled by the sentence.
- **A bare numeral inside a phrase that names a plugin is a count** (`緑のNature.下草を50散らす。` asks for
  fifty). **A bare numeral elsewhere in the same sentence is read too** — with the exclusions below still in
  force at that wider scope.
- **A number beside a word that names an axis is not a count** (direction, orientation, kind, layer, row,
  column, degree, time, fold, part, and their English equivalents): neither the four of "four directions" nor
  the thirty of "30 degrees". **An index is not a count either** — the 2 of `member 2` says which, not how many.
- **Decimals and fractions are not counts** (the 0.11 of "radius 0.11").

**The Android port carries the same rule in the same shape**: its hand-written table of kanji numerals is gone,
and its expectations are generated from what the server actually reads.

**The treatments that reduce density in quiet, membrane, or memory contexts are
not applied to a group whose count was stated.** Quietness is a reading of the
scene; a written number is not a reading. Those treatments act only on groups
with no stated count. Treatments that adjust size (symbolic forms, lone forms,
unintended fills) touch no counts and act as before.

**When the literal totals of several groups exceed 400 (the default of
`max_expanded_primitives`), the groups are tipped into representation starting
with the largest request, stopping as soon as the total is 400 or under. Small
groups are not cut first.** A number that can be counted and a number that
cannot are different things, and proportional shrinking breaks the countable
side first. Only when representing every group still exceeds the ceiling do the
large groups share one limit between them.

**A ceiling that answers to no layout sits at the end of coerce, over both the
total and the number of instructions.** The representation above is a reading of
density, and it deliberately exempts `grid`: a lattice with holes in it is not a
lattice. **That exemption is right for thinning and wrong for a ceiling, so the
ceiling counts grids too** — it counts the marks actually drawn, `rows × cols`
rather than `count`, and drops an oversized lattice to a smaller one that keeps
its proportions. The instruction list is bounded as well, at 64 by default. **Production has
never exceeded 27, so no real work is touched.** What the ceiling bounds is a
request that passed validation and nothing else. **It lives in the deterministic
layer and does not depend on the prompt asking for one to five instructions.**

When `path` is `none`, placement uses `layout` alone as before. When a `path` is
given, the renderer uses a deterministic hash and a sequence number, so the same
JSON Score reproduces the same traced placement.

### 13.11 A Worked Example

The description:

```
細かく揺れるペンシルの破線が3本、画面を横切る
(three finely swaying dashed pencil lines cross the screen)
```

**Stage 1 (interpretation) produces normalized DDL, in the form the corpus uses:**

```
鉛筆の破線の横線を縦に三本並べる。線は細かく揺れる。
(line up three horizontal dashed pencil lines vertically. the lines sway finely.)
```

**An excerpt of a legacy Score expressing the same drawing intent. New work uses shared lowering into repetition recipes.**

```json
{
  "instructions": [
    {
      "primitive": "line",
      "style": "dashed",
      "from": [0.0, 0.33],
      "to": [1.0, 0.33],
      "weight": "pencil",
      "variation": {
        "amplitude": "fine",
        "frequency": "medium",
        "quality": "perlin",
        "dimensions": ["position_x", "position_y"]
      }
    }
  ]
}
```

**The renderer:**

It takes the JSON Score and selects Perlin, Fine amplitude, Medium frequency, and the
existing perpendicular line performance from `variation` to generate SVG. The same Score
and render seed reproduce the same performance. This multiple-line example is conceptual;
the shared compiler's count-one delivery does not imply implemented repetition allocation.

The engine bumps that changed this performance are recorded in the [render engine
version history](docs/spec/render-engine-history.md); the prose below states the
reason for each one inline, for the range before the corpus was frozen.

v1.99 extended the objects of sway from lines to arcs and closed forms (circle,
ellipse, triangle, square, polygon). It fires when quality ∈ {perlin, wave, white}
and `dimensions` contains one of position_x / position_y / radius (symmetric with
line; radius is a form's natural axis). Closed forms are performed with periodic
noise whose seam is continuous, polygons are performed edge by edge with the
corners pinned, and arcs pin both endpoints completely so the touching contract
holds. The pink (blurring) path and the quality=none path are unchanged. Because
the performance of the same Score with the same seed changed, the render engine
version went to 5 (past works may look different when replayed, but saved SVGs
are unchanged).

v2.0.5 gave wave-quality sway a phase derived from the performance seed (until
then the sine had a fixed phase, so the waveform was identical even when the seed
changed). The phase is derived deterministically from the seed, and the automatic
closure of closed contours by integer frequency, the pinning of arc endpoints, and
the pinning of polygon corners all hold. Material contours (the contours and
specks of pencil / crayon / chalk and the rest) were made to follow the
performance seed as well. With no performance seed given, output is byte-identical
to before. The render engine version went to 6.

v2.1.0 converted absolute pixels in rendering to a proportional system throughout.
The sway amplitude vocabulary (fine / medium / broad) changed from absolute pixels
against a 1000px canvas (7 / 12 / 30px) to **a ratio against the shape's
representative dimension** (0.025 / 0.08 / 0.18). The representative dimension is
the radius for circle / polygon / arc, the geometric mean of the radii for
ellipse, half the shorter side for square / triangle / cloudform, and the length
for line. Small shapes now sway finely and large shapes broadly. The
`stdDeviation` of blurring (pink) was made proportional the same way (0.009 / 0.03
/ 0.07). Contour subdivision and stroke sampling changed from fixed counts (80 /
49) to length-proportional counts with clamps. The material layer (line width,
dasharray, texture filter, material contour, speck) and the display filter were
made relative to `canvas.unit`, and at `unit=1000` they match the old behavior
(except that speck count follows perimeter and stroke sampling follows length).
Alongside this, the author's calibration raised material contour and speck
strength by a floor method (at strength step s1, floors on contour offset /
opacity and on speck opacity / count; the texture filter was left alone).
Material contours were given `class="material-outline"` so they can be told from
the main line mechanically. The render engine version went to 7.

v2.2.0 made closed forms (circle / ellipse / square / triangle / polygon) draw
their contours with a drawn stroke — the stroke engine. `synthesize_along` was
added to `stroke_engine` to compose a stroke along an arbitrary centerline (the
tool grammar is the same as for line; only the following target is swapped, and
an integrator feeds the intended stride forward so the spring carries only the
residual, removing radial distortion from curvature). The contour is drawn as a
filled band of two subpaths, outer and inner (`class="contour-stroke-v1"`,
fill-rule evenodd). Corners are pinned at their ideal positions and become the
seams of the brush; a closed contour with no corners closes its seam with a linear
ramp. The target weights are every drawn tool except rotring, which keeps a
geometric contour. The band's centerline is the contour after sway is performed,
and material contours and specks coexist with the band. Dashed and dotted styles
keep a thinned geometric contour, because the line style is itself part of the
description. The body element stays geometric (with `stroke="none"` for solid
styles, leaving only the fill), and the bbox and touching contracts are unchanged.
Line and arc output is byte-identical to v2.1. The render engine version went to 8.

v2.3.0 changed the fill of closed forms from a region fill to **a stroke fill that
fills the interior with the material's own touch**, restoring the meaning of
`filled` (`True` = fill the interior with the material's touch, `False` = contour
only; previously closed forms were always filled regardless of `filled`, making it
a dead field). The fill takes intersections of scan lines with the closed contour
in pairs and passes each interior interval through `synthesize_along` as one
stroke (no clipPath is needed; a concave cloudform is handled as intersection
pairs too, and the endpoints move inward by half the line width so the edge aligns
with the contour). The group is `class="fill-stroke-v1"`. The scan angle comes
from the performance seed (uniform over 0-180°) and differs per shape; the
interval is `max(line width × 1.5, canvas.unit × 0.012)` with ±12% jitter.
Complete coverage is not attempted — the grain of the paper is left showing.
rotring keeps a region fill, and shapes too small for three scan lines degrade to
a region fill. When `surface` is given, no material fill is produced (a fill is
the material's default way of filling; `surface` is an explicit printmaking
expression).

**`surface.texture="grain"` defines a finite set of tool-made marks in a `<pattern>` tile and repeats it through the closed contour itself as the carrier path.** Logical mark count depends only on density and the fixed tile; destination area decides only how often that definition repeats. It adds neither a `filter` nor a `clipPath`, so all three SVG profiles carry the same grain structure. **⚠ v2.13.20 (ddl engine 18) added one exception**: `surface.texture="solid"`
names the material's default way of filling itself, so it goes to the fill layer
rather than the printmaking layer. All nine *omote* quality words are now values
of `surface.texture`, and the asymmetry where only a fill went to `filled` is
gone (`filled` remains, and a coerce branch derives `solid` and `filled=true`
from each other). Alongside this, the hatch and crosshatch surfaces were replaced with
bands of touch (`class="surface-stroke-v1"`) instead of geometric straight lines
(centerline, angle, interval, and count unchanged; rotring stays geometric), and
sways that are not performed were excluded from the seed key so that the presence
of an inactive sway no longer changes the rendered bytes. The render engine
version went to 9. **In v2.13.24 (render engine 35) the hatch and crosshatch rows became
cut against the contour** — they go through the same intersection machinery the fill uses, so a row
stays inside the shape, a concave form gets one stroke per span and never crosses the void, and a row
that misses the outline draws nothing. No `clipPath` is used, so `compat` keeps the same shape.
**Nothing above the cut moves** — the angle, the pitch, the `spacing_gradient`, and the per-row jitter
are unchanged, and so are the spacing class values (only the count of rows that used to fall outside
the outline goes down).

v2.3.1 made arcs perform as a drawn band too (`class="arc-stroke-v1"`), closing
the last exception left by v2.2.0. The target weights are every drawn tool except
rotring. The band's centerline is the arc after sway is performed, and both ends
are pinned to their intended values. **The geometric arc remains as an invisible
intent element** (`stroke="none"`), and the touching check reads that intent arc
back out of the drawn SVG and guarantees the contract by coordinates (the arc
extractor is unchanged; the band is a filled polygon of `M..L..Z` with no arc
command, so it is not counted twice). **The touching end stays tapered**: the
envelope of stroke synthesis converges to zero at both ends, and since the intent
arc guarantees the contract by coordinates, the band may fade softly at the end
like a free end — the tip and base of a leaf come to look softly extinguished.
Dashed and dotted styles make the intent arc itself visible as a thin dashed or
dotted line. drypoint puts its burr along the performed centerline, and material
contours and specks coexist with the band. The render engine version went to 10.

---

## 14. The Design of Relation

### 14.1 Why Relation

The expressive power of tanka comes not from a rich vocabulary but from devices
of relation between words — engo (associated words), kakekotoba (pivot words),
kire (the cut), enjambment.  The infinite holds inside a form of thirty-one
sounds because relation between elements is what carries the meaning.

LeWitt's Wall Drawings are the same.  Their vocabulary is a poorer set than
inku's — lines and a few colors — and yet most of an instruction sheet is a
description of relation (lines not touching, inside the circle, from the midpoint
of the left side toward the upper right corner).  What the viewer reads is not
the individual line either, but the gradient of density, the tension, and the
interval that arise between lines.

Current JSON Score has explicit sequential relations on ordered instructions.
A relation comes from the writer's DDL or an explicit macro emission; it is not
a fixed Stage 1.5 technique recipe used to reconnect independent parts.

A vocabulary of relation adds a predicate — syntax — to the core rather than a
noun.  It sits well with the principle that the form pares away the ego: a
grammar of relation is a form that forces compositional judgment on the writer,
not a license for free rein.  It contradicts neither plugin principle 1 (limited
to a macro over vocabulary) nor the Go-like restraint.

### 14.2 Observable Relation Vocabulary

The distinction §13.3 draws between emotion words and motion words extends to
relation.  Only physical, externally observable relations are allowed into the
core.

**The set is limited to these seven words:**

| Word (ja) | Word (en) | Meaning | Score representation |
|---|---|---|---|
| 沿う | along | placed along the path or direction of the preceding element | `along` |
| 触れない | not touching | approaches the preceding element without contact | `not_touching` |
| 切る | cutting | crosses the preceding element and makes a visual break (the *kire*, the cut, of tanka) | `cutting` |
| 間に | between | placed in the region between the preceding two elements | `between` |
| 触れる | touching | contacts the preceding element; coinciding endpoints compose a closed form | `touching` |
| つながる | connected | joins the current start to a selected start, end, or interior point of a prior Line or Arc, or to the prior endpoint when omitted | `connected` |
| 鏡写し | mirrored | mirrors the positions and orientations of two complete shapes or groups across the axis between them | `mirror_relations` |

**Words excluded**: nestle up to, answer, converse with, resonate with — words of
intent and personification, not observable from outside.

As of the v1.52 close, `relation` in the JSON Score appears only where the
normalized DDL carries an explicit previous-object phrase.  The fixed phrases are
`前の線に沿って` / `前の形に触れない` / `前の線を切る` / `前の二つの間に` in
Japanese, and `along the previous line` / `not touching the previous shape` /
`cutting the previous line` / `between the previous two` in English.  `touching`
is used only where `前の線に触れる` / `前の弧に両端で触れる` or `touching the
previous line` / `touching the previous arc at both ends` makes the contact
explicit; it is never granted spontaneously. `connected` accepts the existing
`前の形につながる` / `connected to the previous shape` and
`connected/connects to [the] start/end of [the] [previous] line/arc`. The latter
selects only the target endpoint; the current shape remains at its canonical start.
For unrotated ordinary Lines and Arcs, left is start and right is end; rotation
and reflection preserve that same endpoint identity. The partway form instead
selects a point excluding both ends during performance. Without either an endpoint
or partway selector, the connection uses prior end to current start. Notions that arrive from natural
language — around, on the same beat, leading or lagging, near or far — are not
relations, and are expressed through position, path, rotation, and spacing.

**Second-round candidates (judged after measurement)**: overlapping, set apart,
same direction, opposite direction, thinner than.  They are added
only once measurement shows the current words to be expressively insufficient.
The one-endpoint `connected` relation entered only after its independent visual
value and finite Line / Arc / Point endpoint family were fixed.

### 14.3 The JSON Score Schema

An optional `relation` field is added to an instruction.

```json
{
  "primitive": "arc",
  "weight": "brush_thin",
  "relation": {
    "type": "not_touching",
    "gap": "narrow"
  }
}
```

| Field | Values | Meaning |
|---|---|---|
| `type` | `along` / `not_touching` / `cutting` / `between` / `touching` / `connected` | the kind of relation |
| `gap` | `narrow` / `medium` / `wide` | a guide distance; the concrete value is resolved by the performance |
| `target_instruction_index` | non-negative Score index | the exact preceding Score instruction for checked `connected` / `touching` / `along` / `cutting`; omitted for older relations |
| `target_path_position` | finite 0–1 / `"interior"` | numbers retain the Score 0.11 Line centerline position; the Score 0.13 string selects an interior Line / Arc position during performance, interpolated by sample order and preserving the explicit prior target |
| `target_endpoint` | `start` / `end` | explicit Score 0.12 Connected target endpoint on a prior Line or Arc; it cannot coexist with `target_path_position` |
| `position_authority` | `named_movable` / `numeric_fixed` | position authority of the checked current instruction |
| `touching_constraints` | boolean `dimensions_fixed` / `direction_fixed` pair | explicit dimension and direction constraints for typed `touching`, distinct from omitted normal; absent in older Scores |

**The referent is always the immediately preceding instruction — an implicit
prev reference.**  Only `between` refers to the preceding two elements.
Arbitrary reference by id is not introduced.  Why:

- hallucinated, circular, and forward references cannot arise structurally
- a light model (Stage 2) takes on no new cognitive load of reference
  resolution; a relation is a pass-through copy
- it matches LeWitt's craftsman procedure: look at the line already drawn, then
  place the next one

Should reference by id become necessary, that too is considered as a second round
once measurement shows the need.

### 14.4 Sequential Resolution and the Performance (Macro Sway)

Relations are resolved by the renderer, at performance time.  The renderer holds
no constraint solver.  It processes instructions in order and places each one by
referring to the **settled** position and contour of the preceding element —
sequential resolution.

- `not_touching, gap=narrow` -> a distance and bearing within a fixed range of
  the preceding element's contour, drawn per performance
- `along` -> position and phase decided per performance inside a band
  that follows the preceding element's path
- `cutting` -> the crossing angle and the intersection with the preceding
  element, decided per performance within a range
- `between` -> decided inside the region between the preceding two elements
- `touching` -> applies to line and arc only; the element's two endpoints are made
  to coincide with the two endpoints of the preceding line or arc as the
  performance realized them
- `connected` -> applies to Line, Arc, and Point; with `target_endpoint`, the
  current canonical start (Point center) is translated to the selected endpoint
  of a prior Line or Arc; without it, it is translated to the prior canonical
  end (Point center). The prior, dimensions, curvature, and rotation remain unchanged

Current typed Along / Cutting rendering covers count-one actual Scores. Macro repeated CompositionPlans retain shared relation intent; repeated-instance performance belongs to later materialization. Typed Along aligns
the current line parallel to the preceding line when both
elements are lines and the current direction is unspecified. Explicit direction,
dimensions, and numeric position remain authoritative. Typed Cutting likewise
retains the normal dimensions from the shared resolver or explicit dimensions;
it does not substitute a relation-specific random length. An explicit direction
takes precedence over the performed crossing angle. Ordinary DDL and Macro use
the same meaning. Metadata-free legacy Score relations retain their compatibility
behavior for saved formats.

Under `touching`, when the element is an arc: let the settled endpoints of the
preceding element be P1 and P2, the chord length `c=|P2-P1|`, and the signed
sagitta of the performed arc `b`.  The minor arc is reconstructed with
`r=c²/(8|b|)+|b|/2`.  Its center sits at `r-|b|` from the midpoint of the chord,
on the side opposite the bulge, and the sweep angle is always under 180°.  When
the preceding element is itself an arc, the bulge defaults to the opposite side.
The sign and sweep conventions of the minor arc share a single implementation
with the renderer's SVG arc drawing.  `variation` and the stroke hold the
endpoints fixed and act only on the intermediate span.  For a closed form, a
preceding element without endpoints, or a degenerate chord or sagitta, the
relation is dropped — no repair by coordinate estimation, and no governor.

Endpoints, tangents, and sagitta are verified in the canvas coordinate system,
with every drawing transform composed, including rotations on ancestor groups.

Because a relation is a relative specification, everything chained to a referent
moves when the referent moves.  That is what makes the macro sway hold: the
relation — the order written into the score — is preserved while the composition
changes every time.  §13.1's definition, fine movement inside order, extends from
the tremble of a line to the scale of composition without its principle changing.

An instruction that carries both a region (`at`) and a relation — twin arcs from
a plugin member, for instance — applies the region placement first and resolves
the relation afterwards (v1.94).  Under `touching` the preceding element's
performed endpoints settle the position, so the region is treated as the starting
point of the chain and as information.

The typed compiler carries `connected` from the exact bilingual full literal on
ordinary adjacent direct instructions, and from an explicit relation between
adjacent bound flat Macro Emits, into the same Score consumer. It preserves the
original Score index, dependency slot, owner, focus, and seed. Named positions
are movable; numeric positions are fixed. After named-region resolution, the
checked performer applies only the translation needed to join the endpoints and
does not clamp again. A numeric position succeeds when the required delta is
zero at the existing physical geometry precision and otherwise reports an
explicit conflict.

Recoverable relation failure, including under legacy Stop input, never stops SVG
construction. It records an error and removes only the failed relation; the
current instruction or Macro Emit, its group, and dependent instructions remain
at their original transformed placement with their original Score indices,
owners, and seeds. A lost referent never retargets to the nearest survivor. When
several translations conflict, none is chosen arbitrarily: the original placement
is retained and only relations that cannot hold there are removed. Omitting every
drawing unit and any source, lock, owner, or exact-Score join failure stop both
modes. Older five relations retain their existing warning and wire behavior.
The normal pipeline uses this shared/native path.

An invalid relation discovered by the validator or coerce retains its existing
warning and drop behavior; neither layer invents a relation. A recoverable
failure discovered only by the checked performer records an error and removes
only that relation. Its instruction, group, and dependent instructions continue
at their original transformed placement. Warning-class failures, such as a grid
layout consuming a relation, record a structured warning. Canonically silent
fallbacks, including missing prior bounds and designated degenerate geometry,
drop the relation without a warning.

Engine 45 also carries typed `touching` from ordinary direct instructions and adjacent bound Emits in the same flat Macro into the shared checked performer. The four bilingual full literals carry their declared Line / Arc target to the original PreviousOne; a mismatched primitive cannot reach canonical success. Macros check the actual typed Emits without inventing a source noun condition. Only Line / Arc succeed. The prior stays unchanged, both endpoints coincide, and Arc uses the same minor-arc reconstruction described above. Explicit numeric geometry or relative scale (including normal at factor 1) fixes dimensions; an explicit angle fixes the performed chord direction in canonical endpoint order. Omitted normal may adjust to Touching. Numeric positions retain their anchor and the final geometry's existing must-fit requirement; named focus remains movable with clipping. Incompatibility is a typed conflict.

Typed Touching follows the same relation-recovery and original dependency, owner, and drawing-ordinal rules. On failure it records an error and removes only Touching, leaving the current, its group, and dependent instructions at their original transformed placement. Touching without the new metadata retains legacy reconstruction, warning, and drop behavior, and Connected is unchanged.

### 14.5 The Owner of Relations

A relation enters Score only when the writer states it through Stage 1 or direct
typed DDL, or when an explicit macro definition emits it. Stage 1.5 neither adds
nor changes a relation; coerce may only drop an invalid relation with a warning.

### 14.6 Constraints and Prohibitions

1. each instruction has at most one relation
2. an unresolvable relation is not repaired by coordinate inference or a governor
3. Stage 1.5 and coerce do not invent relations
4. usage, type distribution, and drop rate are audit mirrors, not firing-rate
   floors or generation controls

### 14.7 Display in Saijiki

A relations (あいだ) category is added to Saijiki.  Laid over the notion of *ma*,
the interval, it shows that the vocabulary of relation is not mere geometric
specification but words for writing negative space and tension.  Displayed as:
along, not touching, cutting, between, touching.

---

### 14.9 The Design of Cloudform (v1.89.1)

#### 14.9.1 Why Cloudform

> The cloud outside the window is never the same shape twice, and people watch
> it without tiring.  To have a work looked at the way one looks out of a
> window — cloudform is the form for that.

A circle or a square comes from its definition.  Cloudform has no definition.
Then who decides the contour — **the performance decides**.  The score records
only the parameters of the process (the character and the size of the sway, the
material), and the renderer generates the contour from the performance seed.
From the same score, a different cloud every time.

"The description persists, the performance is one-time" has until now acted on
placement and on touch.  Cloudform extends the principle to form itself.  A
circle that sways is still a circle, but for a cloudform the realized value of
the sway is its identity.

Cloudform does not imitate a meteorological cloud.  The name follows the cloud
ruler: a shaping word for a **family** of irregular curves, not the cloud of
weather.  Yamato-e haze, the suhama forms of decorated paper, suminagashi
marbling — Japanese form-making has stylized the indefinite not as arbitrariness
but as a form that carries a grammar of irregularity.  Cloudform stands in that
line.  Just as LeWitt's "lines not straight, not touching" defined a line by
negation and by process, cloudform defines a plane by process.

#### 14.9.2 The Generative Process (the Contour Is Decided by the Performance)

The contour is generated by a two-stage deterministic synthesis.  All of it
depends on the performance seed, and the same seed reproduces the same contour.

1. **The base closed curve**: a closed curve whose polar radius r(θ) carries a
   seamless multi-octave 1/f signal.  Low-frequency components make a few large
   lobes ("undulating largely"), high-frequency components make fine unevenness
   ("swaying finely").  The sway vocabulary maps onto the octave distribution
2. **Normal displacement**: a second periodic signal running along the arc length
   of the base curve displaces it along the normal, creating bays and waists —
   suhama-like concavities.  The displacement amplitude is clamped geometrically
   against local radius and curvature, so self-intersection is structurally
   prevented; a strictly positive single-valued polar radius supplies that
   guarantee.  This is not a governor, but the same kind of geometric safety as
   the existing "safe drawing"

The edge quality of the contour is carried by the stroke engine, the tool
grammar — a pencil cloudform and a rotring cloudform are different things.  The
interior is filled by surface (wash, stipple, hatch, aquatint, and so on).
Combined with `mode: carve` it can cut an irregular light out of a dark ground.
Output passes through Bezier fitting and obeys the point budget.

#### 14.9.3 Composition With Existing Vocabulary (No New Modifier)

Every modifier a cloudform takes is expressed in existing vocabulary:

- **sway** -> the octave distribution of the contour (finely / largely /
  undulating / trembling / blurring)
- **proportion** -> the aspect ratio (a tall cloudform, a wide or full-width one —
  a band of haze is written this way)
- **touch** -> the stroke of the contour (the tool grammar)
- **surface / color** -> the texture and the color of the interior
- **relation** -> a cloudform can be referred to as "the previous shape";
  sequential resolution works against its settled contour and bounding box
- **place / motion** -> its placement (several scattered cloudforms each receive
  their own contour)

#### 14.9.4 The Selection Rule (Not an Escape Hatch)

Cloudform is not "the approximation for when you do not know."  To preserve
condensation by constraint:

1. Stage 1 may select cloudform only when (a) the description explicitly writes
   雲形 / "cloudform", or (b) the instructed subject is itself amorphous — cloud,
   smoke, haze, stain, island silhouette, puddle, and the like
2. an unknown or unclear subject continues to be approximated with the existing
   forms.  Cloudform is never a fallback
3. Stage 1.5 and coerce cannot inject or add a cloudform (§10.4 applies).  Stage 2
   only transcribes the normalized form into the primitive cloudform with center
   and size; it never asks an LLM for contour coordinates or control points
4. the frequency and the context of cloudform use are watched as a mirror by the
   motif ledger (see "Accounting for Refinement").  No governor, no floor, no
   generation gate, no automatic preference

#### 14.9.5 Determinism and Identity

Contour generation is a deterministic derivation from the performance seed; it
adds no new source of randomness and no new hash input.  The specification for
computing current `rh3` is unchanged, and saved `rh2` remains legacy without
recalculation. The score holds only the process parameters of the
cloudform — center, size, `variation`, touch, surface, relation, placement — and
stores no contour coordinates.  The contour is a realized value of the
performance.

#### 14.9.6 Accounting for the Form

- **Gained**: a form that does not come from a definition.  The first form in
  which sway is not decoration but the body of the form itself.  A contour that
  invites the viewer's projection — design principle 5, "the viewer is what
  moves," acts most strongly here
- **Lost**: the uniformity of a vocabulary in which form means a definable
  figure.  The risk of becoming an escape hatch when interpretation falters
  (sealed by §14.9.4)

The current identity domain for cloudform and other rendered work is `rh3`.
Stored `rh2` is a legacy read-compatibility domain and is never recalculated.

---

## 15. Development Policy

### 15.1 Axes of Development

**Main axis**: web UI (browser) + Python FastAPI + LLM providers selected per
stage (§12.5)

- the reasons: speed of development, ease of demonstration, room to grow
- development happens on the Mac; sustained-load testing runs in a dedicated
  test container on the deployment host (§22)

**Complementary axis**: a native Android app (verified on a Pixel 9) +
LiteRT-LM (Gemma 4 E2B / E4B)

- a port that follows the server as canonical, tracking the render engine
  version by version (the current state is in `android/ANDROID_SPEC.ja.md`)
- kept as the "it runs on a local LLM too" point of difference
- the Android application version is maintained independently in `android/VERSION`

### 15.2 Where Completed Phases Live

Completion records for the PoC and initial features live in
[CHANGELOG.md](CHANGELOG.md) and the [public history
archive](docs/history/changelog-v0.1-v1.71.md).

### 15.3 Current Development Boundary

Current implementation status lives in [Implementation Status](docs/spec/implementation-status.md). New render engine changes belong in [CHANGELOG.md](CHANGELOG.md), and existing version records remain in the history below. This section defines no new implementation phase.

**The per-version engine record moved to the
[render engine history](docs/spec/render-engine-history.md) on 2026-07-28.**
The version history preserves past records. Current version, identity, reference-corpus, preservation, and PNG rules are in §2.1; new changes belong in [CHANGELOG.md](CHANGELOG.md).

## 16. Licensing

The intended license direction is:

- core DDL specification: permissive license such as CC0 or MIT
- reference implementation: MIT or Apache-2.0
- Saijiki vocabulary data: CC BY or CC BY-SA, if community contribution begins

The language should remain reusable by other implementations while preserving
the reference implementation as one concrete path.

---

## 17. Open Items

The public specification contains neither an open-items list nor operational
procedures. [Implementation status](docs/spec/implementation-status.md) is the
authority for implemented scope, [CHANGELOG.md](CHANGELOG.md) for design and
implementation history, and the [version history](docs/spec/render-engine-history.md) for existing render-layer version records.


---

## 18. JSON Score

Explicit sway reaches the existing `Instruction.variation` through the three-dimensional resolver in §13.6. Score deserialization retains its existing Medium / Medium / None defaults, distinct from defaults resolved when source supplies at least one slot. Authors do not write internal Variation JSON directly in natural DDL.

Explicit named positions reach the same geometry consumer from ordinary DDL and declared flat Macros.
These `at.region` bounds describe semantic anchors on canvas axes from zero to one, not whole-shape fit areas.

| Place identity | Region [x0,y0,x1,y1] |
|---|---|
| top | [0,0,1,1/3] |
| bottom | [0,2/3,1,1] |
| left_edge | [0,0,1/10,1] |
| right_edge | [9/10,0,1,1] |
| top_edge | [0,0,1,1/10] |
| bottom_edge | [0,9/10,1,1] |
| corner | One of upper-left [0,0,1/5,1/5], upper-right [4/5,0,1,1/5], lower-left [0,4/5,1/5,1], lower-right [4/5,4/5,1,1] |

Center / middle retains canonical center and its six exact-owner focus regions. Edges are narrow bands, not fixed points.
Stage 2 selects a corner in the dedicated `inku.score-place-selection.v1` domain. It frames verified original
pre- and expanded-meaning digests, a composition seed tagged to distinguish None from Some(0), and either the
original direct logical ordinal or the Macro semantic ordinal, expansion path, and generated ordinal.
The first SHA-256 byte modulo four selects upper-left, upper-right, lower-left, then lower-right.
Different composition seeds may select the same corner. Source, canonical meaning, and provenance never receive the
selected corner; the existing Renderer render seed chooses its anchor within that region. Another performance and
explicit variation preserve the corner. One rational policy table converts to Score f64 only at the final boundary.
The policy ID stays unchanged while its content digest changes; this does not introduce a semantic schema version.
Unspecified position remains unsupported; named/numeric conflicts and numeric must-fit remain enforced.
Unsupported noncenter relations remain unsupported and are never silently discarded. The normal shared runtime,
UI, and persistence path uses this delivery.

JSON Score is the machine-readable score produced by the shared lowerer from verified meaning.  It is not the
final work; it is the structure that the renderer performs.

Important score concepts:

- `canvas`: selected canvas aspect identifier, such as `square` or `golden`
- `instructions`: ordered drawing instructions
- primitive fields: the canonical exact nine, line, circle, ellipse, triangle, square, polygon, arc, point, and cloudform, plus related process data. Point is a round filled mark with an identity distinct from Circle. `rectangle` is not a tenth primitive and requires a separate author ruling and schema / version before it can be added
- `weight`: material / tool quality
- `variation`: visible wobble, blur, tremble, or motion behavior
- `arrangement`: count, distribution, paths, grouping, density, fade, and color cycles
- `rotation`: shape-level or group-level orientation
- `color_hint`: optional hint used when resolving catalog colors, and the descriptive markers the renderer reads as the character of a drawing
- `note`: optional machine-written processing annotation. It never reaches the drawing: it is outside the performance seed allowlist, and Stage 2 is instructed never to emit it. Coerce and the API record their diagnostics here so that a diagnostic can no longer be mistaken for a color description. **It is a chronological record of processing steps, not a summary of the final Score or drawing state.** A later step may supersede an earlier diagnostic while both remain recorded, so no single `note` clause is evidence of the current color, shape, or placement. It is declared second, because an optional field's fill rate rises toward the tail of the declaration order
- `at.region`: optional normalized placement region `[x0,y0,x1,y1]` resolved by the renderer seed
- `relation`: optional observable relation to the previous instruction: `along`, `not_touching`, `cutting`, `between`, `touching`, or `connected`; touching pins both endpoints, while connected translates only the current start to the prior end

A count the description states outright outranks any later reading of it.
Canonical meaning keeps the value as lossless symbolic intent. The Step 11 pure
ceiling preflight runs before expansion, allocation, or any other O(count)
materialization. A value such as `u32::MAX` is neither clamped nor silently
rewritten to a representative count; a standalone primitive draws its safe
source-ordered prefix and diagnoses the requested and executed counts. Threshold
and representation behavior remaining in the current runtime is compatibility
behavior, not semantic authority to change the canonical count into another
value.

**Size has three authorities.** Unspecified, explicit qualitative, and explicit
numeric geometry remain distinct. In the current subset, an unallocated
count-one circle, square, ellipse, cloudform, triangle, or polygon uses `6/25` (0.24) of the canvas
short edge for diameter, side, or width; ellipse and cloudform height is `3/5`
of width. Normal line length and normal arc chord are also `6/25`; arc sagitta
is one quarter of its chord, and normal point diameter is `3/250` (0.012).
Finite relative factors are `3/4`, `1/2`, and `3/8` for mild,
standard, and strong small; `5/4`, `3/2`, and `7/4` for the corresponding large
classes; and `1` for normal. One exact rational factor is applied once to the
normal geometry: length for line, similar chord and sagitta for arc, and diameter
for point. Existing `small` means standard-small, while an explicit
"normal size" remains distinct from unspecified. Explicit numeric geometry is
unchanged by qualitative size, and stating both is a conflict. Unspecified
normal outside this subset remains undecided and is not completed through
free-form degree synonyms or a hidden LLM.

Explicit numeric geometry retains dimension, basis, canonical base-10
coefficient / scale, and source-spelling provenance. Conversion to Score `f64`
happens at one deterministic lowering boundary only, with no silent clamp or
rescale. Past fixed calibration of circle `0.038` and ellipse `0.06×0.032` is no
longer an active candidate. Before context is available, a candidate retains
symbolic size intent. The old values and rationale remain in the changelog.

The single canonical owner for resolving size and position is `inku-ddl`; its
identity / digest is `inku.geometry-resolution-policy.v1`. The compiler lock
references and attests that identity / digest, while `ddl_engine_version` is
activation metadata only. There is no `size_rule_version` or second owner.

The same policy owns explicit angles. `horizontal=0`, `vertical=90`, and
`diagonal` selects from `45 / 135 / 225 / 315`. `rising` and `falling` select
integer degrees in `[-37,-23]` and `[23,37]`; `left_rising` and `left_falling`
select in `[203,217]` and `[143,157]`. `rotated` makes a finite uniform choice
among integer degrees more than five degrees from every 45-degree boundary.
The angle-specific SHA-256 domain frames the lock-verified original pre- and
expanded-meaning digests, tagged optional `composition_seed`, logical
occurrence, and angle identity. Equivalent inline and continuation meaning
selects the same angle; distinct true occurrences have distinct keys.
Effective focus, variation seed, render seed, raw source bytes, and the full
lock digest are excluded.

A circle or point keeps the same radial extent under rotation. An ellipse uses its ideal
rotated ellipse extent, cloudform and square use the rotated rectangular envelope of
their declared width and height, and line and arc use their final finite geometry. Numeric placement rotates short-edge units in
physical space, converts the result back to each canvas axis, and applies
must-fit only to the rotated extent; it does not reject the unrotated box first,
relocate, shrink, reduce count, or retry another angle. Named focus keeps the
existing size and `at.region` without a must-fit check. Line, arc, and square angles use the
same resolver for direct instructions and flat Macro Emits and reach
`Score.rotation`. An explicit angle on round point is unsupported and is not
reinterpreted as another rotated shape.

The same policy owns the six mappings from effective focus to `at.region`:
`upper_right=[0.60,0.18,0.82,0.40]`,
`upper_left=[0.18,0.18,0.40,0.40]`,
`lower_right=[0.60,0.60,0.82,0.82]`,
`lower_left=[0.18,0.60,0.40,0.82]`,
`upper_edge=[0.39,0.07,0.61,0.29]`, and
`right_half=[0.61,0.39,0.83,0.61]`. A named Score instruction has no `center`
or `position`; it carries its resolved `radius` or `size` and `at.region`.
Line, arc, and point carry finite baseline geometry and a semantic anchor plus
`at.region`, which the Renderer moves by that anchor.
Only numeric position applies the unit-interval anchor and shape-extent must-fit
checks. The named path does not intersect the region with shape-safe bounds,
shrink dimensions, relocate or resample to fit, or stop on an empty intersection.

The author's A ruling allows clipping. The Renderer retains its existing
short-edge conversion of region extents, performance-seed anchor selection, and
unit-interval base-point clamp, including a square's top-left point. This is not
a promise that no coordinate adjustment occurs or that the whole shape always
stays on the paper. Engine 42 preserves the existing wire in which coordinates use
normalized canvas axes while size, radius, and gap use the canvas short edge.
It computes square and triangle semantic centers, movement, rotation pivots,
performed bounds, relations, composite offsets, and arrangement fitting in one
physical short-edge coordinate family before converting back to each axis.
Public helpers called without a canvas keep their prior normalized-coordinate
compatibility.
Engine 43 uses the endpoint midpoint for line, the chord midpoint for arc, and
the center for point as semantic anchors. A typed arc carries its chord midpoint
in the existing optional `position`; an old Score arc with that field absent
keeps its circle-center anchor and rotation behavior.

Within the current subset, only an omitted count resolves to one; zero,
repeated, and qualitative counts are not materialized. Omitted touch resolves to
pen, omitted continuity to solid, and an omitted closed surface to filled.
Explicit empty stays unfilled, while explicit solid reaches the same existing
fill path. An omitted color requires explicit observations of the actual
background, black, and white RGB and OKLCH L values from the same Renderer
`work_color_assignment` / `resolve_color` path. The single `inku-ddl` policy
chooses whichever of black and white has the larger lightness distance from the
background, choosing black on a tie. An explicit color needs no color-catalog context
and remains unchanged. Explicit fields win independently. Stop, the default,
returns no actual Score when any meaning is unsupported. OmitAndContinue omits
unsupported color, touch, continuity, surface quality, or intensity as an
independent field and records the contrast color, pen, solid, fill, or retained
explicit quality actually used. Other failures omit the smallest source
instruction, Macro Emit / structural subtree / invocation, Ground, coordinated
group, or relation-instruction unit. Previous-one / two relation meaning keeps
its original source indices and is never rebound to compressed post-omission
indices. The lowering result retains canvas, background, resolved color context,
geometry-policy digest, mode, outcome, gaps, owners, spans, and dispositions,
while source semantics, canonical meaning, and provenance remain free of
defaults and focus injection.

The quiet-density governor, which thins repetition for still, membranous, or
remembered scenes, does not apply to a group whose count was stated: quiet is a
reading of the scene, and a stated number is not a reading. When the literal
groups together exceed `max_expanded_primitives` (400 by default), the largest is
represented first and the budget is rechecked before the next one gives way, so
the small groups a reader could have counted stay literal.

Line and arc remain unfilled, while point is a round filled mark. An explicit
surface or variation on point remains typed unsupported.

The scene-tone rule currently chooses from the abstract colors alone:

- spring, flowers, buds, and warm light lean toward red / green / white
- water, night, moon, rain, mist, and cold air lean toward blue / white / gray
- forest, leaves, grass, moss, and fragrance lean toward green / white / gray

Nuance that cannot be represented by the nine abstract colors (§3.1) is retained
in `color_hint` for catalog-based rendering.

Relations are sequential. `along`, `not_touching`, `cutting`, `touching`, and `connected` refer to the immediately previous instruction; `between` refers to the previous two. There are no arbitrary ids, forward references, or repair governors for relations. The older relations retain their validation/coercion warning behavior; Connected resolution is checked before SVG and never leaves a bare current instruction on failure. JSON Score `relation` is reserved for explicit previous-object phrases in normalized DDL: `前の線に沿って` / `along the previous line`, `前の形に触れない` / `not touching the previous shape`, `前の線を切る` / `cutting the previous line`, `前の二つの間に` / `between the previous two`, the explicit contact phrases `前の線に触れる` / `touching the previous line` or `前の弧に両端で触れる` / `touching the previous arc at both ends`, and `前の形につながる` / `connected to the previous shape`. Touching and Connected are never added spontaneously. Natural-language proximity, rhythm, ahead/behind, near, and far are represented with position, path, rotation, and spacing instead of relation.

An instruction that carries both a region (`at`) and a relation (such as plugin-member double arcs) is placed by its region first and then resolved by its relation (v1.94); for touching, the previous instruction’s endpoints decide the final position, so the region acts as chain-start information. Relations discovered unresolvable only at performance are dropped. Warning-class failures, such as a grid layout consuming a relation, record a structured warning; canonically silent fallbacks, including missing prior bounds and designated degenerate geometry, drop the relation without a warning.

For `touching`, both the current and previous instruction must be a line or arc. The renderer takes the previous instruction’s performed endpoints and pins the current endpoints to them. For an arc with chord length `c` and signed performed sagitta `b`, it reconstructs the minor arc with `r=c²/(8|b|)+|b|/2`; its center lies opposite the bulge, and a previous arc makes the new arc bulge to the opposite side by default. Minor-arc winding uses the same shared convention as SVG arc rendering. Sway and stroke performance keep both endpoints fixed and act only on the interior. Closed forms and endpointless targets are rejected drop-only with a recorded warning. Degenerate performed geometry also drops the relation at render time; no coordinate repair or governor is introduced.

Endpoint, tangent, and sagitta verification is performed in canvas coordinates after composing every drawing transform, including rotations on ancestor groups.

This fifth relation trades the former uniform family of loose distance constraints for one exact endpoint constraint. In return, it can write closed organic contours such as a two-arc leaf without freezing performed coordinates into the Score. The deferred `continuing` candidate remains outside this version; it is reconsidered only after cloudform surface/ground expression improves.

The system treats the DB history record as the source of truth.  SVG, JSON
files, PNG files, and other artifacts are derived outputs.

---

## 19. Canvas Model

Canvas selection is not visible-DDL or macro meaning. It is a host option resolved from the shared-core `inku.canvas-format-registry.v1`. The same DDL can be used on different canvases, and its coordinates, words, and canonical meaning do not change. The registry's canonical eleven formats and positive integer width / height ratios are:

| ID | Ratio (width / height) |
| --- | ---: |
| `square` | `1 / 1` |
| `golden` | `809 / 500` |
| `a4` | `500 / 707` |
| `b4` | `500 / 707` |
| `pillar` | `1 / 5` |
| `oban` | `2 / 3` |
| `wide` | `47 / 20` |
| `byobu` | `11 / 5` |
| `vertical` | `9 / 16` |
| `sd_monitor` | `4 / 3` |
| `hd_monitor` | `16 / 9` |

A host boundary with no selection may choose `square` as its host default, but the DDL compiler does not insert `square` as a semantic fact. The host carries the resolved selection through Score / render context / history, and the Renderer chooses SVG `width`, `height`, and `viewBox`. If Stage 2 receives canvas through the current compatibility path, that value is host-resolved composition context rather than visible-DDL metadata.

The current runtime's `plugin_storage["canvas-aspect"]`, `canvas_aspect` request alias, stored `Score.canvas` / `render_canvas_aspect*`, system / user plugin directories, and plugin-status / enable controls remain as read compatibility. They are not the new plugin-authoring model. Storage and API compatibility remain for saved settings and catalog discovery; they do not execute the old semantic decision layer. In the current UI, changing the aspect clears the rendered display for a placeholder but retains the displayed work as lineage context, and the next saved work may be recorded as its child with `canvas_aspect_change`.

Position coordinates remain normalized from `0.0` to `1.0`: X is a fraction of
canvas width and Y is a fraction of canvas height. Top-left is `(0.0,0.0)`,
bottom-right is `(1.0,1.0)`, and exact center is `(0.5,0.5)`. Named center, a
qualitative region, and an exact numeric coordinate are separate authorities.
An exact coordinate is not a Stage 1.5 focus target and is never silently moved,
clamped, or snapped. Boundary-anchor validity and a diagnostic that the shape's
extent clips the canvas are separate matters.

Direct typed DDL accepts the finite JA forms `半径N`, `直径N`, `幅N、高さN`,
`一辺N`, and `画面の横X、縦Yの位置`, their corresponding EN forms, and the finite
seven-class size modifiers in both languages. A decimal retains its original
spelling and source span as provenance while its meaning is normalized to a
signed base-10 coefficient and scale. The entrypoint takes a lock-verified Stage
1.5 v5 view and explicit host canvas and background, requiring the corresponding
resolved color-catalog context only when color is omitted. Independent circle,
ellipse, cloudform, square, line, arc, and point instructions with resolved numeric position or an
original `place:center` owned by a verified direct instruction target, plus a
place action, can lower explicit numeric geometry or the current normal / qualitative
geometry, together with omitted count-one, pen, solid, fill, and contrast color, into an
actual `Score`. Existing fill behavior for `none`, `solid`, and omitted surface remains;
`wash`, `grain`, `stipple`, `hatch`, `crosshatch`, `bleed`, and `aquatint` reach the
existing Renderer `SurfaceSpec`, while verified `paper`, `washi`, `ink_wash`,
`charcoal_ground`, `canvas`, `drawing_paper`, and `mezzotint` reach the existing
`CanvasGroundSpec` in a `Canvas::Spec` carrying the host-resolved aspect. The compiler
does not create texture or material numeric defaults or seeds. Surface intensity on solid closed fills reaches the tool-specific normal / dense / faint appearance.
For unsupported combinations such as non-solid textures and explicit Point surfaces, Stop stops and Continue omits intensity while retaining quality. Ground alone
is drawable content, and Continue retaining Ground preserves its original omission
diagnostics. The default Stop mode rejects the entire Score when the document contains
unsupported meaning. Explicit OmitAndContinue records the original owner and spans plus
the actual omitted field or execution unit, and reports a remaining Score only when a
drawing target survives. Integrity failure or omission of every target is stopped. The
normal product runtime uses this Rust path.

Isotropic mark size, circle and arc radii, `radial` rings, `at.region` extent,
cluster bands, and a path's cross-axis spread become pixels from their allocation
or the short edge. Circles remain aspect-correct and ellipses retain their stated
aspect. Placement, region centers, and cluster centers scale with width and
height; path travel (`margin` / `span`) and `arrangement.margin` remain fractions
of their axes. This decision follows the single
`inku.geometry-resolution-policy.v1` owner in §18.

Finite direct geometry also includes Japanese `長さN` / `弦長N、矢高N` and
the corresponding English `length N` / `chord N, sagitta N`. Line, arc, and
point enter the same actual Score lowerer as the six closed shapes;
point reuses `radius` or `diameter`. Japanese `点` is Point as an independent
noun head and remains the existing stipple surface when the same phrase owns it
as a modifier of another explicit shape head.

### The Resolution of a Number (the Master Grid)

The Renderer’s shared `format_number` boundary rounds a number to six fractional
places, normalizes `-0.0` to `0`, and removes trailing zeroes and a dangling
decimal point. The representation is therefore not fixed-width: an emitted
value has at most six fractional digits and may be an integer. The current
contract defines numeric rounding, not a fixed-width lexical form or a
`-?\d+\.\d{6}` guarantee.

**Keep the precision of rounding to six fractional places; do not lower it to
write fewer bytes.** Reducing numeric precision in coordinates or texture-filter
settings can change the drawing, unlike removing trailing zeroes to write the
same value more compactly. Historical precision-comparison measurements are
recorded in [CHANGELOG.md](CHANGELOG.md).

---

## 20. Modes

For invalid sway in the shared typed compiler, Stop returns no new Score.
Continue omits the original instruction, malformed Emit, or undeclared caller invocation
at its existing unit, preserving owner, reason, and actual disposition. Sway does not add
a new field-level recovery unit. Integrity failures stop both modes. The normal Server and
Web use this compiler and persistence path.

### Single Drawing

The user writes one instruction and runs the full pipeline.  The resulting DDL
is inspected in a read-only interpretation box and edited directly in the DDL
editor dialog. Replaying from DDL skips description generation and sends the saved visible DDL through the shared compiler, lowerer, and renderer
again.

The normalized DDL appears as a **read-only interpretation box** under the
single drawing input.

- the `Saijiki` toggle, placed on the canvas toolbar since v1.98, opens the
  side drawer as a browse-only vocabulary reference: clicking a word chip
  shows its preview instead of inserting it
- the `DDL editing` button opens a larger dialog with line numbers, a
  two-column Saijiki vocabulary panel, and a short DDL syntax guide; since
  v1.98 word insertion happens only through this dialog's inline Saijiki,
  which also lists loaded plugin vocabulary
- The old `auto repair` setting is retired. The shared compiler owns semantic
  validation and recovery, diagnosing excessive placements and unsatisfied relations
  at their defined recovery units. The legacy API still accepts `auto_repair`,
  but it no longer selects behavior.

The same `Draw from DDL` action is also available below the interpretation box
for quick replay without opening the dialog. Candidate metadata shows render,
composition, variation, and interpretation seeds where applicable. `Draw` in
the DDL editor dialog saves the edited DDL under authoring authority, then runs the shared compiler, lowerer, and renderer,
and does not reinterpret the natural-language description.

The drawing tab also exposes two explicit regeneration actions. **Another
performance** keeps the same Score and asks only the renderer for a new
performance seed. **Another composition** preserves saved normalized DDL,
advances `composition_seed`, reselects focus from Stage 1.5's closed six
candidates, and reselects the concrete angle or corner in the shared lowerer when that
meaning is explicitly present. It changes no composition family, technique, color, touch,
relation, or element count. The same lock-verified meaning and attested
`composition_seed` reproduce the same effective meaning, angle, and corner. Another
performance and explicit variation preserve the resolved angle and corner. Saved Score / expanded
artifacts take precedence, source text remains saved, silent backfill does not
occur, and no permanent old/new runtime switch is introduced. Semantic schema /
identity never presents changed bytes as an old identity. The normal Server, Web, and Android
use the same shared route from typed v5 in §12.11 through the resource-aware compact Score
performance core. Saved Score and history retain the format compatibility needed
for display and replay.

The normal UI displays visible DDL, proposed patches, and saved results from
the shared pipeline execution state. The compatibility `POST /api/paint/stream`
returns the final shared-pipeline result as one `done` NDJSON record. A pending
patch approval returns HTTP 409 before streaming starts. The former four-stage
`sketch` / `stage1` / `score` stream is not the progress contract for new works.
`POST /api/paint` remains a compatibility entry to the same shared route.

DDL replay shows elapsed time, token information, a stop button, and the
progress mascot.  Stopping replay aborts the active request.
During single drawing and DDL replay, the single tab shows a running effect and
the batch/demo start actions are suppressed.

Single drawing, DDL replay, batch, and demo all show **one progress mascot, the
one chosen in settings**.  There are two, `Incu` and `Yuragi`, and the default is
`Incu`; the names are proper nouns and are not translated.  `Incu` is a cube built
from a 5x5 pixel grid that turns slowly, once every fifteen seconds.  `Yuragi` is
a crab that raises its left claw every eleven seconds and its right claw every
eight to greet you.  The mascot is switched in the settings dialog.  **No screen
shows a mascot of its own.**

### Batch Drawing

The batch panel groups the input, next-work conditions, progress, and resume for
multiple instruction lines. During execution, the active line is highlighted
and the current DDL interpretation is displayed read-only. Batch execution
keeps failure reports until the next batch run, and stores batch prompt history
per user. **The history keeps fifty entries
(v2.13.21; twenty before that).  The limit belongs to the server, which cuts on
both the read and the write.**  The list is capped at half the window height and
scrolls when it does not fit.

**A batch that stopped part-way can be carried on from where it stopped.** In
one session it retains the original prompt, a stable run ID, the Stage 1/2
models, color catalog, sketch, Wild, and canvas selected at start, plus the
pending lines. A stop before the first success, and another stop after resume,
both resume **only lines not yet saved**, with **the original line numbers** and
the captured conditions. Editing settings during the run affects only the next
new batch. A line whose server save succeeded remains successful even when the
following history refresh fails, so it is not painted again.

After a page reload the in-session interrupted snapshot is gone. The existing
saved-history discovery alone looks for a resume candidate, matching both line
number and description. **A batch with no saved success is not promised to
resume after reload.** When reload recovery can restore conditions, it reads the
last saved work; a condition without a record is not invented, because absence
means "older than the record," not "off."

Letting the server choose a color catalog by reading each line is **not a batch
option but the catalog selection itself** (below). **Until v2.9.39 the batch tab
carried its own checkbox for it, and until v2.9.22 that checkbox drew a catalog
at random in the browser.**

The color catalog dialog puts **"From the description" above the thirteen
catalogs**.  It is a choice with no colors of its own: while it is selected, the
server reads the description on every drawing and decides the catalog (the
request sets `catalog_mode` to `auto` and carries the default catalog as
`catalog_id`, which is the fallback the server keeps when the model is
unreachable or names a catalog that does not exist).  History records store the
catalog that was actually used, so **refinement and redrawing do not inherit the
automatic choice: they draw with the work's own catalog**.  **Beside the
resolved catalog, a history record also stores how it was asked for
(`catalog_mode`, v2.13.21)** — the resolved id alone cannot say whether the
automatic choice was asked for or a catalog was named.  **Only the batch resume
reads it, so a run that asked for the automatic choice carries on with the
automatic choice**; refinement and redrawing are unchanged.  **Works older than
this record carry no value, and the absence of a value means "not recorded", not
"was not automatic".**

**The catalog selection is stored per user on the server**
(`model_settings.color_catalog_id`).  Drawing needs a session, so a browser-wide
value would only ever be another user's selection.  Only a catalog that still
exists, or `auto`, can be stored; a retired id falls back to the default.

Clicking outside the dialog confirms the current selection exactly like the
save/confirm action. The cancel button still restores the selection snapshot from
when the dialog was opened.

### Demo Drawing

Demo mode repeatedly generates an instruction from a seed phrase, renders it,
waits for the configured interval, and repeats. Demo settings are stored per
user. Demo results are not saved by default; the user can explicitly save a
current render to history. Demo is in the settings modal's `Making` category,
not an input tab. Its running status and Stop action stay available outside
settings, where it can also be reopened, and starting it does not replace the
Description or Batch text.

Demo draws with the same selection. The work-conditions header reflects the
catalog reported by the render result, not only the current catalog selection.
**Until v2.9.39 the
per-user demo settings held a `catalog_mode` of their own, and until v2.9.22 that
option drew a catalog at random.**

`/api/paint` takes `catalog_mode` as one of `fixed`, `auto`, and `random`.
`fixed` uses `catalog_id` as given, `auto` reads the description, and `random`
draws a catalog other than `catalog_id`. **`random` belongs to refinement**: its
"Another catalog" exists to see one description in a different color, and reading
the description would settle on the same catalog every time. A request that omits
`catalog_mode` behaves as `fixed`. The field replaced the boolean
`random_color_catalog` in v2.9.22.

While demo is running, history interaction is restricted where it could confuse
context.

---

## 21. History and Data Integrity

History is stored in the server DB.  The DB record is the source of truth for:

- original input
- input-side normalized DDL (Stage 1 `ddl`) and effective Stage 1.5 DDL (`expanded_ddl`, the Stage 2 input)
- JSON Score
- SVG rendered by the server
- model metadata
- color catalog
- timing and token metadata
- star state
- trash state

The web UI does not send client-generated SVG back as trusted history content.
`/api/paint` generates and saves server-side history directly.  Compatibility
history endpoints re-render from JSON Score instead of trusting SVG sent by the
client.

For SVG download, the web UI exposes Display, Editable, and Compat variants.
Display downloads the stored SVG.  Editable and Compat call server render
endpoints so past history can benefit from the current export structure without
duplicating SVG blobs in the DB.

The CLI `paint` and `batch` commands also accept
`--svg-profile display|editable|compat` for saved SVG files.

Server-side output artifact saving is an admin-managed, server-wide setting.
The settings dialog includes an admin-only "other (server)" tab for:

- enabling or disabling automatic drawing file artifact saving
- setting the output folder as an absolute server path
- selecting the automatic PNG artifact size, either 1080px or 2160px

The server stores these values in `app_settings.output_save_settings` as
`enabled`, `output_dir`, and `png_size`.  `INKU_OUTPUT_DIR` and
`INKU_OUTPUT_PNG_SIZE` provide initial values; if unset, the defaults are
`~/.local/share/inku/outputs` and 2160px.  The API endpoint
`PUT /api/settings/output-save` is admin-only, accepts only absolute output
paths, and restricts PNG size to 1080 or 2160.

Disabling automatic artifact saving does not disable DB history saving.  The
history DB remains the source of truth, and only derived files such as SVG,
JSON, input text, normalized DDL, and PNG artifacts are skipped.  When enabled,
artifact files remain grouped by user and date under
`<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history-id>...`.

The "other (server)" tab shows save worker and queue settings, save statistics,
and the PNG artifact size.  Save workers are concurrent file-save jobs; the
queue is the maximum number of pending artifact save jobs.  If the queue is
full, the server preserves DB history and skips only artifact file saving.

Server log retention is also an admin-managed, server-wide setting.  The
settings dialog includes an admin-only "log retention" tab for enabling or
disabling application log retention, setting the retention period in days,
choosing a daily / weekly / monthly rotation interval, and enabling compression
for rotated logs.  The default policy is enabled, rotates daily, keeps 90 days,
and compresses rotated logs.

The server stores this policy in `app_settings.log_retention_settings` as
`enabled`, `retention_days`, `rotate`, and `compress`.  `INKU_LOG_RETENTION_DAYS`
and `INKU_LOG_ROTATE` provide initial values.  `PUT /api/settings/log-retention`
is admin-only and updates the stored policy.

**The application executes this policy itself.**  The server writes its log files
under `INKU_LOG_DIR` (`~/.local/share/inku/logs` by default, `/data/logs` in the
container image), keeps one generation per retained day, gzips rotated files when
compression is on, and prunes older generations on its own.
`GET /api/settings/status` returns the current policy together with **the log
directory and the files present in it**.  **There are no generated files to apply
to the host OS.**  This matches the shape of the database backup policy, and it
was chosen because a policy the platform executes cannot be the same policy in the
container distribution, which has neither systemd nor logrotate.

**The same lines keep going to stdout**, so operators can follow logs through
`journalctl -fu <service>` and through `docker logs` as before.  In the container
distribution, `logging` in `compose.yaml` caps what the daemon collects from
stdout.  `inku-api` and `inku-server` also print startup banners wrapped in
60-character `=` borders; the banners
include the service role, application version, build number, build date, mode,
listen host/port, runtime / platform, and log destination.  The API banner
includes the active render engine ID and version.  The API and web UI use
different emoji sets that match their roles.

---

## 22. Security and Operations

The web app includes authentication, permission groups, the visibility scope of a work
and its sharing, sessions, per-user settings, user profile editing, and user management.
Passwords are stored as salted PBKDF2-SHA256 hashes.

**Permission groups (v2.12.0).**  What a member may do is decided by the permission
groups they hold.  The groups are **fixed at three — `admins`, `leaders`, and `users`** —
and members cannot create more: the demand for more is really per-work sharing, which
the visibility side carries.  **One member may hold several groups** (many-to-many).
**The test lives in a single predicate**; scattering the branch would leave gaps when
visibility is written on top of it.  **The `role` column stays on the user row and is read
by no decision.**  It stays for backup and restore — dropping it would mean a database
taken after this version fails to open on a build from before it.  **The column is written
as a mirror the machine derives from the memberships, never by a person** (a copy written
by hand and frozen in a test keeps guarding a stale value from the day the source of truth
moves).  **The startup migration is one-to-one and idempotent**, mapping the old `admin` to
`admins`, `group_lead` to `leaders`, and `user` to `users`.  **It does not read `admin` as
"an administrator is also a leader"** — reading it that way would make a membership the
migration widened indistinguishable from one a person widened on purpose.  **The
organisation group is a separate thing, one per member**, judged independently of
permission.

**Visibility and per-work sharing (v2.12.2).**  What a member may do (the permission
group) and what a member may see are separate axes.  **The default scope follows
membership** — `admins` see everything, `leaders` their own organisation, `users` their
own works — and **a per-work ACL adds to it**.  One ACL row is a **triple of (work,
recipient kind, recipient)** with two permissions, `read` and `write`.  It is a triple so
that **the same person may hold different permissions on different works**.  **The ACL
stores ids and not a single name**, so renaming a member or an organisation carries the
sharing with it.  **Every decision runs through one visibility predicate, and the paths
written in raw SQL run through it too** — when the full-text search path is left out, it
shows up **not as "too much is visible" but as "it goes missing when you search"**, which
a test written in the "now it is visible" direction cannot catch.  **A refused write
answers 404, or a count of zero, rather than 403** — a 403 would confirm that the work
exists.  **Settings carry no ACL**: personal settings stay with their owner, and global
settings stay with `admins`.

**A group-aimed share the work carries itself (v2.13.36).**  The third entrance to the
visibility scope.  **When the works to be shown are a set rather than a list, the ACL has
to be written row by row** — and in fact `history_acl` in production holds 0 rows to this
day.  **The shape follows a Linux filesystem**: the owner is `user_id`, the group is
`share_group_id`, and the read bit is `for_share`.  **Nothing corresponding to world is
created** (author's ruling, 2026-08-17; "anyone may read" is a decision to publish outside
the organisation, not something to add alongside a flag).  **A work is readable only when
the bit is up AND the group matches** — the bit alone is a permission with no destination,
the group alone a destination nobody opened, and **neither means a permission by itself**.
**Raising the bit without naming a group fills in the owner's own organisation group**, the
way a new file takes the group of whoever made it.  **Only `admins` may name another
group**; anyone else gets a 403.  **That 403 applies only when a group is named** —
`chmod g+r` asks nothing of the group the file is in, and requiring administrator rights to
re-open a work already opened would **stop the very person who chose the destination from
repeating it**.  **Dropping the bit keeps the destination** — `chmod g-r` does not forget
the group, and clearing it would silently re-aim the work the next time the bit went up.
**The flag widens reading only; `_writable_by` does not move.**  **Lineage nodes and edges
follow, the colophon does not** — the flag's clause sits on the same branch as the ACL, the
one handed a work id, and `list_okugaki` is the only call that is handed none.  **The
decision runs through the same single visibility predicate as the ACL, and the raw-SQL path
carries the same clause.**

**A lineage may cross owners (v2.12.2).**  Any readable work of another member can be a
parent, and the root id is inherited, so **one group spans two people and the number of
visible nodes differs per viewer**.  **A node that cannot be read is returned with its
content withheld**, and `deleted` is **told apart from `not_permitted` in words** — both
draw as the same empty dashed card, so **without the label a viewer cannot tell "gone for
good" from "ask its owner"**.  **An edge follows its child, and the consequence is that
even the parent's owner cannot see the derivations** — an exception there would revive,
on the parent's side, the very reason the follow-the-parent design was rejected.  **The
colophon of a shared work is readable even when somebody else wrote it**, because a
colophon is read as an annotation on the work.

**Single-user mode (v2.11.19).**  For one person on their own machine, the entry
ceremony a shared server needs is too much.  A server started with
`INKU_SINGLE_USER` settles on one person and treats them as already signed in.
**The multi-user machinery is not removed; only the default moves** — the code
defaults to off, so a deployment that merely takes a new version does not lose
its authentication, while the distribution defaults to on, so bringing the
server up and opening a browser is enough to start writing.  The single user is
resolved once, as the oldest administrator, and that result is recorded by the
account's id.  **The id rather than the name is recorded so that renaming does
not move it, and it is recorded in settings rather than on the account row so
that there can structurally be only one single user.**  Because the record lives
in the database, it leaves with a backup and comes back with one.  On a database
with no administrator the mode does not engage and requests stay refused.
**Even in single-user mode, changing the password and managing users stay
visible** — under the distribution default the account's password is a value
nobody knows, so that is the only way back from single-user operation to
ordinary operation.  The server reports whether the mode is on through the same
public response that carries the version and build number.

The app rail user menu opens a profile dialog for the signed-in user.  The
dialog can update the user's email address and password through
`PATCH /api/auth/me/profile`.  Password changes require the current password,
and the endpoint is separate from admin user-management APIs.

Settings visibility follows the permission groups.  DB settings and user management
are visible only to members of the `admins` group.  The plugins tab is visible to all
signed-in users, but plugin setting changes and plugin-storage update APIs are
restricted to `admins`.

The Server's canonical persistence uses SQLite through SQLAlchemy only.
`INKU_DB_URL` and the derived thumbnail-store setting accept SQLite URLs only;
both are validated before either engine is created. Rejection of a non-SQLite
URL never falls through to a new empty default database. Server
SQLAlchemy/SQLite and Android Room/SQLite each own a
physical schema; a possible future iOS adapter would map another physical
schema to the same logical contract. This does not mean sharing one database
file, table names, or column layout. Canonical logical meaning and host mappings
live in [`persistence/README.md`](persistence/README.md) and
[`persistence/contract.json`](persistence/contract.json). Server-only
authentication and administration tables and device-only provider, model, and
cache tables are host extensions, not parity gaps. The mapping does not change
the meaning of stored SVG, Score, hashes, or NULL values.

A versioned migration registry owns the Server schema lifecycle. A fresh
database creates its schema and registry in one single-writer transaction. A
registered database verifies its version and checksum and then starts without
repeating legacy whole-database repair scans. A pre-registry database is
accepted only when its schema fingerprint and complete FTS state are explicitly
named. An unknown fingerprint, partial FTS installation, future registry
version, or checksum mismatch fails before any schema or row is changed.

Before an accepted legacy database is changed, the Server creates and opens a
WAL-safe snapshot through SQLite's Backup API. It then takes a `BEGIN IMMEDIATE`
or equivalent single-writer boundary and compares every table's primary-key
identity plus the canonical `id`, `input`, `score`, and `svg` history bytes by
streaming digest. SQLite quick check and foreign-key check must also pass. Any
failure rolls back the transaction and retains the verified snapshot for an
explicit recovery decision. Migration, manual, and scheduled backups share the
same SQLite-native snapshot owner and never fall back to copying only the main
file while ignoring WAL.

`server/src/inku_server/db.py` is a compatibility and composition facade that
preserves existing imports and call shapes. Physical schema, configuration,
engine, migration, invariant, backup, and domain persistence owners for
accounts, settings, history, search, lineage, and related data live under
`server/src/inku_server/persistence/`. New persistence work belongs to the
corresponding owner; facade line count alone is not a reason to split it again.

Android shares this logical contract but never opens the Server database. For
the Room v1–9 to v10 transition, a coordinator runs before the normal Room
singleton, deletes only v1–9 database and journal files plus derived
thumbnails, and creates a fresh v10 database. Downloaded model files outside
SQLite remain. Existing v10 is kept; v11 or later, non-empty v0, and unreadable
databases fail without changing database, thumbnail, or model bytes. There is
no generic destructive fallback after v10: a later change needs an explicit
Room migration or a new author ruling.

The DB settings tab also shows the current SQLite DB file size. Admin users can
configure DB replica backups with an interval in days, a time of day, and a
maximum number of automatic generations. The defaults are seven days, 03:00,
and four generations. Manual backups can be created immediately and are stored
separately from the automatic generation limit. Backup and restore use the
SQLite file boundary.

**The interval decides which day and the time of day decides when on that day.**
The next due moment is derived from the last backup taken, not from the moment
the scheduler happens to wake, so a backup taken late at night does not drag its
successors along behind it.

Scheduled backups are taken by a resident scheduler owned by the application
lifespan, which asks once a minute whether a backup is due.  `INKU_DB_BACKUP_SCHEDULER=0`
removes it.  **The one-minute tick is deliberately coarse**: because the due
moment comes from the last backup rather than from the loop's own period, a late
wake-up delays a copy instead of skipping one.  **Reading the settings status
endpoint does not create a backup.**  Until v2.9.7 that endpoint was the only
trigger, which meant an interval of N days was really "whenever an admin next
opened the panel after N days had passed", and it also meant that merely
refreshing the panel could write a replica.  Both properties are gone.

The settings status response also reports what the backups currently occupy:
each retained file with its generation, kind, timestamp and size.  **Generation 1
is the newest automatic backup** and the highest number is the next to be pruned.
**Manual backups are never pruned and therefore carry no generation number.**  The
listing stops at 50 rows, but the reported total count and total size cover every
file, so the cutoff cannot understate usage.

Concurrent drawing requests are bounded at the application layer. Stage 1 and
Stage 2 LLM calls share a bounded executor controlled by `INKU_STAGE_WORKERS`
and `INKU_STAGE_QUEUE_LIMIT`. If capacity cannot be acquired, or if a stage
exceeds its hard timeout, the request follows the same deterministic fallback
path used for stage hard timeouts. Timed-out LLM calls may continue in their
underlying Python thread until the provider call returns, so their capacity slot
is retained until that worker actually finishes. This prevents timed-out
provider calls from creating an unbounded backlog.

Per-user drawing counters are updated with a single database-side atomic
increment so simultaneous `/api/paint` requests for the same user do not lose
generation counts. History listing, retrieval, starring, trashing, restoring,
and deletion are all scoped by the visibility predicate. **Until v2.12.2 that
scope was a `user_id` match and nothing else**; membership-derived defaults and
the per-work ACL now add to it. **The path is still a single one, and no route
goes without a scope.** Admin status responses include `stage_execution` with Stage worker count,
queue limit, and submitted/completed/failed/timed_out/rejected counters.

Operational details for the author's local server are intentionally not part of
this public specification. They are consolidated in the untracked `AGENTS.md`
or in private internal documentation outside the product repository.

The application is developed on macOS. **Checks that hold the CPU -- the whole
suite, a whole perturbation sweep, rebaking the reference corpora, rasterizing,
benchmark runs, and the port's JVM tests -- are run in test-only containers on
the deployment host** (one image per toolchain)
(`AGENTS.md` carries the procedure). Source is still synced with rsync and
verified on the deployment host after a systemd service restart. Production
Docker Compose images are verified at milestones such as release candidates
rather than rebuilt for every ordinary source change. **The test container and
the release image are not the same image**: the release image is built without
the test dependencies (`uv sync --frozen --no-dev`), so the test container is
that same base with the dev group added. What a measurement there may claim is
"on the same footing as the release image", never "in the release image".
**Frozen output -- the reference corpora and the port's reference fixtures -- is
baked on the same Linux the release runs on**: macOS libm and glibc disagree by
one ULP on sin/cos/hypot, and values that sit outside the quantisers split
there. Git is used for source history, not as a file exchange mechanism with the
local server.

**The record of each engine version moved to the [render engine history](docs/spec/render-engine-history.md) on 2026-07-28.**
The version history preserves past records. Current version, identity, reference-corpus, preservation, and PNG rules are in §2.1; new changes belong in [CHANGELOG.md](CHANGELOG.md).

---

## 23. CLI

`inku-cli` is a command-line client for controlling the inku server through the
API.  Its initial purpose is to support automated prompt/image generation,
quality review, and feedback loops for tuning Stage 1, Stage 1.5, Stage 2, and
renderer behavior.

CLI configuration is local and editable.  It stores base URL, provider/model
selection, and timeout values outside the server DB.

`inku-cli paint` and `inku-cli batch` support `--input-mode paint|ddl`.
The default `paint` mode sends natural-language input to `/api/paint` and runs
the full Stage 1 -> Stage 1.5 -> Stage 2 -> render pipeline.  `--input-mode ddl`
treats the input text as already-normalized DDL, skips Stage 1, and sends it to
`/api/compose`.  When `--input-mode ddl --save-history` is used, the CLI saves
the compose result through `POST /api/history` so the output appears in normal
server history.  `/api/compose` returns the effective DDL after Stage 1.5
expansion, and CLI output/history use that effective DDL for DDL-to-render
benchmark parity.
The CLI sends instruction language through `--instruction-lang auto|ja|en`.
`auto` is the default and lets the server resolve Japanese or English from the
input text.  `--ui-lang` may be supplied as display-context metadata, but it
does not control interpretation.

`inku-cli batch` can write a benchmark summary JSON file.  When an output
directory is used, the default summary path is `analysis-summary.json` in that
directory.  The summary includes all successful samples and review groupings for
fallback, slow, and normal samples.  Slow samples are diagnostic only; successful
drawings remain part of quality review even when the free inference endpoint was
queued.

Benchmark summaries also include diagnostic traces used for tuning:

- `color_trace`, including requested colors, colors present in the Score,
  missing requested colors, warnings, and negated color markers.
- `negated_color_markers`, so phrases such as "not green" or Japanese
  equivalents such as `緑には寄せず` do not incorrectly count as missing green.
- `score_motif_hint_counts` and `score_motif_hint_lines` for compound motif
  repairs such as `leaf_cluster`, `paper_shard`, `ripple_knot`, and
  `mountain_sign`.
- `math_balance_markers` and `math_balance_marker_lines` for detected
  compositional markers such as radial Fibonacci counts, golden-like centers,
  rule-of-thirds-like centers, and counterweight-like opposite placements.

`inku-cli contact-sheet` builds a PNG contact sheet from a directory of PNG
outputs, making benchmark review less dependent on manual image assembly.

---

## 24. Source of Truth

`SPEC.ja.md` is canonical.  This file is the maintained English public version.

When updating the specification:

1. Update `SPEC.ja.md` first.
2. Refresh this English `SPEC.md` so that it carries the same content, section
   for section.  Neither language may hold a section the other lacks (the
   author's ruling of 2026-08-02).
3. Do not abridge.  Earlier practice asked the English wording to stay concise;
   that instruction is withdrawn, because it produced a file that silently said
   less than the canonical one.
4. Do not introduce English-only behavior that is absent from the Japanese
   source.
5. Keep current contracts in the specification and chronological implementation
   detail in the changelog.
6. `server/scripts/check_docs.py` checks that the two files have the same
   heading shape.  It is the only gate on this rule, and it must be run before
   a documentation change is merged.
7. The same gate also reads the **forbidden words on the English side**
   (`artwork`, `palette`, `AI-powered`, `magic`, from §5-1 of
   `web/src/lib/i18n/GLOSSARY.md`).  A span wrapped in backticks is treated as
   an identifier and is not checked — an enum member or a JSON field keeps its
   real spelling even inside English prose.  `CHANGELOG.md` and
   `docs/history/changelog-*.md` are frozen records and are a declared
   exemption.

---

## Appendix: Repository Layout (an Overview)

```
inku-lang/                 # github.com/oikawas/inku-lang
├── SPEC.ja.md / SPEC.md               # the specification (Japanese canonical / English public)
├── PROJECT_CONTEXT.ja.md / .md        # the short entry point for developers and AI
├── CHANGELOG.ja.md / .md              # the chronological implementation and design record
├── README.ja.md / README.md           # the project introduction
├── server/                            # the FastAPI backend (inku_server, managed with uv)
├── web/                               # the SvelteKit 2 + Svelte 5 frontend
├── cli/                               # inku-cli (an HTTP API client, managed with uv)
├── shared/                            # the analysis package the server and CLI share (inku_analysis)
├── core/                              # shared Rust core (DDL compiler / render engine / score / SVG raster)
├── persistence/                       # logical SQLite persistence contract shared by Server and Android
├── docs/                              # published documents (architecture / spec / guide / history / i18n)
├── manual/ja|en/                      # the user manual (seven Japanese/English pairs)
└── android/                           # the native Android implementation (canonical: android/ANDROID_SPEC.ja.md)
```

The **current values** of the module layout, the API routes, the CLI
subcommands, and the vocabulary constants are **not listed in this document**.
These are canonical instead:

- vocabulary, fixed phrases, markers, regions, weight characteristics, and
  validation thresholds: the **reference dump** (`GET /api/reference` /
  `inku-cli reference --md`, a machine-generated mirror of the implementation
  tables)
- API routes: `server/src/inku_server/api_core/routers/` (ten FastAPI route
  definition files) and `server/src/inku_server/api.py` (assembling `app`,
  the middleware, and `include_router`)
- CLI subcommands: `inku-cli --help` and `manual/en/cli-reference-for-ai.md`
- the internal layout of each package: "The current state of the product" in
  `PROJECT_CONTEXT.md` (**the delegation to the package READMEs was dropped on
  2026-08-02**. `server/README.md` was empty, `web/README.md` was still the
  SvelteKit template, and `cli/README.md` holds usage recipes and a copy of
  `--help`, so none of the three described an internal layout)

The early Python PoC directory `ddl/`, which the complementary Android axis was
built from, has served its purpose and left the tree; `server/` carries the
implementation.

---

## The Refinement Contract

Refinement does not accumulate branches, words, parts, or rules unnoticed; the
reason for removing or retaining them is recorded in the changelog. Similarity
features, motif frequency, Vision observations, and coerce firing rates are
observation mirrors and never automatically control default generation,
suppression, acceptance, or a quality function. Lineage follows explicit
derivation edges only and is never inferred from similarity.

Normal generation detects instruction language from its input. Saved per-stage
language and `language_variation` metadata remain readable and replayable for
compatibility, but the language-comparison UI is not a current feature.
Version-by-version introductions, removals, UI changes, and accounting records
live in [CHANGELOG.md](CHANGELOG.md) and the [public history
archive](docs/history/changelog-v1.72-v2.4.md).

## Autonomous Refinement Methods

Lineage's autonomous refinement is a bounded run of 1–10 generations whose final judgment remains human. Before starting, the user chooses one method:

- `Random automatic refinement` randomly chooses each generation's variation kind from the enabled reading, color-catalog, layout, touch, and variation elements. It does not use Vision. Because the direction text only reaches the drawing text of reading generations, the random-method UI states that condition explicitly.
- `AI Vision automatic refinement` lets the user explicitly choose a Vision model from provider-grouped cards. During that run, the selected model serves both Stage 1 / Stage 2 generation and Vision advice, while those three roles and their prompts remain separate. The server rasterizes each saved generation to PNG and sends it with the original instruction, user direction, and allowed refinement kinds. Vision returns visible observations, one direction to try next, and one allowed variation kind; that advice becomes input to the next generation.

Either method may include variation (§12.13) among the enabled refinement elements (up to five). Only while variation is enabled, an amplitude choice (small/medium/large, default medium) is shown; the chosen amplitude applies to every variation generation in the run, and seeds are server-issued.

The Vision method is a finite advisory loop, not quality optimization or automatic acceptance. Vision must not score, rank, accept, reject, praise, condemn, or discard a generated work. Intermediate generations remain `lineage_only`, the final generation enters regular history, and all generations remain in lineage. Derivation metadata records the method, Vision model, observation, and next direction, while the modal shows the latest advice. The model may be changed between runs but remains fixed during one run. Only the human may save, promote, star, or finally choose a work.

---

## Colophon: Reading a Lineage

A colophon is an append-only, first-person reading attached to one lineage branch from its root to the displayed work. It is neither a verdict nor a summary. It describes observable changes between generations and closes by verbalizing what remained invariant across the branch.

- Each generation is read sequentially. The request for generation i contains only generations 0 through i, so later works cannot turn earlier choices into steps toward an alleged final form.
- Inputs are existing lineage edge facts, captions, server-rasterized PNG pairs, and deterministic differences from the v1.80 feature mirror: composition family, primitives, colors, density, angles, and arrangement paths. No new quality metric is introduced. Vision images are bounded to a 512px single work or an aspect-correct 768×384 before/after pair.
- A successful generation response may be cached briefly by model, language, prefix, and image hashes so retrying after a timeout reuses completed work. Different works, models, or prefixes never share entries, and optimization must not combine all generations into one request that exposes later works to earlier observations.
- Invariants are computed mechanically as shared feature and retained-Score elements. The LLM only verbalizes those facts and may not add causality, authorial intent, scores, ranking, praise, or condemnation.
- Japanese and English evaluation terms are scanned as warnings only. A warning never forces rewriting, regeneration, or rejection.
- The server appends the reader model and date as a mechanical signature. Records store the target node, branch snapshot, model, time, language, body, warnings, and fact sheet in the current user's scope.
- Records can be appended or deleted, but never edited. Idempotency keys prevent duplicate saves, and lists are displayed oldest first.
- The colophon is available only through the explicit Lineage action or `inku-cli colophon`; `--dry-run` generates without saving. It affects neither dh1, current rh3, legacy rh2, generation, variation, refinement selection, acceptance, quality functions, nor branch recommendation.

---

## Changelog

Chronological public release notes are maintained in [CHANGELOG.md](CHANGELOG.md). The more detailed Japanese history is in [CHANGELOG.ja.md](CHANGELOG.ja.md), and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the short developer entry point.
