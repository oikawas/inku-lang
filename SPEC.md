# inku — Drawing Description Language Specification

**Version: v1.92.0**
**Canonical source:** [SPEC.ja.md](SPEC.ja.md)

This document is the official English specification for public review, contest
submission, and non-Japanese readers.  It is adapted from `SPEC.ja.md`, which is
the canonical source because the author works in Japanese.  When the
specification changes, update `SPEC.ja.md` first, then refresh this English
version.

**By the author's ruling of 2026-08-02 the two language versions correspond
section for section.**  Neither language holds a section the other lacks, so a
number means the same thing in both.  This replaces the ruling of 2026-07-28,
under which Japanese was canonical for the concepts and English carried the
operational sections alone.  **Japanese remains the canonical source**: a change
to the specification is written in `SPEC.ja.md` first and then reflected here.

Sections 18 onward do not yet have a Japanese counterpart; bringing them across
is the remaining part of that work.

For ordinary development, start with [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
and read only the specification sections relevant to the task. Chronological
release history is maintained separately in [CHANGELOG.md](CHANGELOG.md), with
more detailed canonical notes in [CHANGELOG.ja.md](CHANGELOG.ja.md).

---

## About This Document

**inku** is the reference implementation project for DDL (Drawing Description
Language).  DDL is the language specification; inku is its implementation.

This document records the **design philosophy, the language design, and the
current principal contracts**.  For ordinary development, read the short entry
point [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) first and come back here only
for the sections a task actually touches.  The chronological implementation and
design record is kept separately in [`CHANGELOG.md`](CHANGELOG.md).

### The Name "inku"

- From インク, the Japanese reading of **ink**
- The material of writing is itself the name -- structurally the same idea as
  DDL's concept that the description is the work
- The association with 墨 (sumi): the world of calligraphy and ink painting,
  echoed by the "shades of sumi" of the color catalogs
- The `-lang` suffix places it as a language project, beside rust-lang, go-lang
  and the like

### Ecosystem Naming

Derived projects share the `inku-` prefix:

- `inku-core` -- the core library
- `inku-saijiki` -- the vocabulary dictionary
- `inku-nature` -- the Nature plugin
- `inku-web` -- the web UI implementation
- `inku-android` -- the Android implementation
- `inku-cli` -- the command line tool

---

## 1. Core Concepts

### 1.1 A Language for Writing Visual Tanka

DDL is not a language for describing pictures.  It is positioned as a language
for **writing visual tanka**.

`inku` is the reference implementation of DDL.  It is not a drawing program in
the usual sense: it treats the written description as the durable work, and the
rendered SVG as one performance of that work.  The same description may be
rendered again later, with controlled sway, while preserving the underlying
score.

It stands at the intersection of three traditions:

| Tradition | What it contributes to DDL |
|---|---|
| Sol LeWitt's instructions | the idea that the description itself is the work |
| Bonsai | constraint is not limitation but condensation |
| Tanka | do not assert, present. The form pares away the ego |

### 1.2 The Underlying Stance

- **Do not assert, present** -- the author's feeling and reading must not
  intrude into the work
- **A short description is the essence** -- a long description leans toward
  assertion. Brevity is what makes presentation possible
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

1. Descriptions must remain human-readable.
2. Sway is part of the specification, not a bug. It exists at two scales: micro sway in line wobble, blur, grain, and texture; and macro sway in composition and placement resolved by the renderer.
3. Emotional adjectives are excluded from core vocabulary.
4. Physical, spatial, material, and motion words are preferred.
5. Coordinates carry no absolute dimensions such as pixels, so one description applies to a wall as readily as to a screen. The aspect ratio is not fixed either: it is a constraint that shapes the world of the work, not a dimension the description carries.
6. Output is still image SVG; the viewer moves, not the image.
7. The input language is constrained enough to support iteration.
8. Optional concrete worlds belong in plugins, not the core language.
9. **The engine does not go backwards.** Like a woodblock being carved, the drawing engine only moves in one direction. Past versions are not kept in the system and cannot be selected. **What remains is the printed work — the saved SVG — not the block as it was before the cut** (see "Principles that outlast a version" in the [render engine version history](docs/spec/render-engine-history.md)).

DDL avoids words such as "beautifully" or "powerfully" in the core.  The system
should express such ideas through visible choices: number, placement, material,
line behavior, color, weight, and negative space.

---

## 3. Separating Core From Extensions

### 3.1 What Belongs in the Core

The core vocabulary is the nine Saijiki categories plus **relations** (あいだ).
The vocabulary dictionary is called Saijiki, following the haiku term for a
seasonal word dictionary.  In inku, Saijiki is consulted rather than kept open
at all times.

Since v1.92 the vocabulary has a single source of truth: the saijiki table on the server (`saijiki.py`). The Stage 1 prompt vocabulary block, the plugin closure markers, the Stage 2 relation phrases, the web Saijiki display (`GET /api/saijiki`), and reference §1 are all derived from that table. The machine-generated reference dump (`GET /api/reference` / `inku-cli reference`) always shows the current values; the table below is the v2.7.9 snapshot.

| English | Japanese | Vocabulary |
| --- | --- | --- |
| forms | かたち | circle, ellipse, triangle, square, line, arc, cloudform |
| touches | てざわり | silverpoint, pencil, pen (default), rotring, crayon, chalk, fine-brush, thick-brush, burin, drypoint, computer |
| continuity | つらなり | solid (default), dashed, dotted, dash-dot |
| motions | うごき | place, line-up, draw, scatter, fill, tile |
| movements | ゆらぎ | fine, large, slowly, quickly, swaying, undulating, trembling, blurring |
| relations | あいだ | along, not touching, cutting, between, touching — with fixed phrases such as `along the previous line` and `touching the previous arc at both ends` |
| places | ばしょ | top, bottom, center, left-edge, right-edge, top-edge, bottom-edge, middle, corner |
| angles | かたむき | horizontal, vertical, diagonal, rising, falling, rotated |
| proportions | わりあい | tall, wide, full-width, half-width, semicircle, waxing, waning, crescent |
| colors | いろ | white, black (default), blue, red, green, gray, yellow, orange, purple |

In v1.92 the words 描く (ja draw) and 髪 / hair were pruned from the vocabulary by the author's decision. In v2.7.9 the second of those came back under the name it should have had: `hair` was never a brush but a **silverpoint** — 0.5px, the least wavering line a hand can draw — and it is now 銀筆 / silverpoint, first in the touches list. Saved Scores that still say `hair` are rewritten to `silverpoint` as they load, so they replay unchanged in everything but the seed.

The canvas proportion is not vocabulary: it is handled by the canvas-aspect
plugin (§4.4), with the nine kinds square / golden / a4 / b4 / pillar / oban /
wide / byobu / vertical.

**Properties of the core:**

- vocabulary of physical material only (zero words for feeling)
- centered on the act of *placing* rather than the act of *drawing* -- the
  sense in which a bonsai branch is "placed"
- the design of the motion vocabulary matters most: place, line up, fill --
  these are the verbs of presentation
- **the movements category holds movement words only**: "swaying finely" and
  "undulating slowly" are allowed, "swaying beautifully" and "swaying
  violently" are excluded (§13 has the detail)
- **the relations category holds observable relations only**: "along" and "not
  touching" are positional relations an outside observer can verify. Words of
  intent or personification, such as "nestling against" or "answering each
  other", are excluded (§14 has the detail). This is the addition of a
  predicate (syntax), not of vocabulary (nouns), so it does not contradict
  plugin principle 1

`Random` is not forbidden as an author word.  The restriction applies to internal normalized DDL and JSON Score: unordered placement must be interpreted into observable placement such as dotted across the whole canvas, scattered, varied, top-to-bottom, or along a trace.

The core color vocabulary is the nine abstract colors that authors can write: white, black, blue, red, green, gray, yellow, orange, and purple. Color catalogs are server-owned metadata that change how those nine colors are resolved at render time; they are not vocabulary extensions. **Yellow, orange, and purple were added in v2.9.11.** Catalog `palette` entries already carried twelve yellows, a nominal 13.6%, yet yellow reached only 0.6% of what was actually drawn: there was no word to leave by. The three are peers of the other abstract colors, and `color_hint` remains the place for nuance that no abstract color holds. **From v2.9.12 (render engine 17) the nine are assigned deterministically from the catalog's `palette`, once per work**, from `(render_seed, catalog_id, abstract color)` and nothing else: the six chromatic words by OKLCh hue band (CIELAB cannot separate blue from purple), the three achromatic roles by reserving the hex that equals their own `map` value and then taking the nearest lightness. The background goes through the same assignment, and `color_hint` now acts only as a table that names a band (ASCII matched on word boundaries).

Colors in JSON Score are abstract color names.  Rendering resolves them through
the selected color catalog.  The server is the source of truth for color
catalog definitions and exposes them through `/api/color-catalogs`; clients
select a `catalog_id` rather than owning their own catalog tables.  When user
instructions include color nuance, the system may preserve `color_hint` so
Stage 2 and rendering can resolve the best catalog color without losing intent.
The default catalog is a neutral baseline, not a cultural default.  Additional
catalog ids use material-, light-, and technique-based names to avoid presenting
a country, ethnicity, food, festival, empire, or tourism marker as a complete
catalog identity: `ink_season`, `fresco_study`, `open_air_light`,
`ink_porcelain`, `cool_material`, `dye_earth`, `vivid_material`,
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
recorded lack them.  The current engine metadata is
`render_engine_id: "default"` and
`render_engine_version: "1"`.  The full catalog `map` / `swatches` / `palette`
snapshot is not duplicated in render JSON because `render_color_map` is the
concrete color record needed for replay and audit.
`render_hash` is the work-edition identifier; what it is derived from, and why
the build number and the Score-side seed stay out of it, is in "Separation From
the Render Engine Pack" below.
`score.canvas` remains the score-level canvas instruction, while
`render_canvas_aspect` records the canvas aspect actually used for this rendered
artifact.  In normal server-generated output they match, but both are retained
so render metadata remains visible even when old records or imported Scores are
inspected.
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

### 4.1 Why the Plugin Model Is Designed From the Start

DDL designs the plugin mechanism **from the beginning rather than adding it
later**.  Three reasons:

**To keep the core pure.**  Concrete vocabularies such as the Nature plugin
(rain, leaf, water, wind) are already ruled out of the core.  That ruling holds
only if a plugin mechanism exists from the start; otherwise it invites the
compromise of "put it in the core for now and separate it later."

**To settle the manner of extension first.**  Leaving other-language editions to
the community works only once the manner of writing a plugin is defined.
"Extend it freely" produces implementations that do not resemble one another.

**To make the boundary with the core explicit.**  What is core and what is
extension.  If that line is drawn late, the line itself becomes vague.

### 4.2 The Emacs Lisp Lesson and the Go Stance

Freedom in a plugin system cuts both ways.

**What Emacs pays for its extensibility**
- the boundary between core and package is vague
- packages collide with each other
- the core itself swells as extensions pull on it
- the learning curve differs per person, which weakens it as common ground

**Go's opposite stance**
- language features are kept deliberately few
- no macros, no metaprogramming
- forcing "one way" means other people's code can be read

If DDL aims at tanka, the **Go stance** is the fitting one.  Tanka has no
"grammar of my own."  The common form is what lets individual expression exist.

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
Every plugin expands into a description written in core vocabulary.  A plugin is
shorthand, not a new capability.

### 4.4 Implementation Hooks

The reference implementation adds the `canvas-aspect` plugin (v1.29).  Its only
hook is the **canvas-size hook**, and per-user plugin settings are stored as JSON
in plugin extension storage.  System plugins and user plugins live in separate
directories, one directory per plugin: `server/src/inku_server/plugins/system/canvas_aspect/`
on the server and `web/src/lib/plugins/system/canvas-aspect/` on the web side.
The web UI's plugin button (Canvas) sits in the writing tab's action row,
currently ordered color catalog, model selection, canvas, new (Build 563, §8.4).
The aspects it offers, the coordinate rules, and what changing an aspect does to
the displayed work are in "Canvas Model" below.  How to write a plugin is
recorded in `PLUGIN.md`.

### 4.5 The Expansion Model

A plugin is defined as a name given to a combination of core words.

```text
Nature.雨  ->  many short lines scattered from top to bottom
           =  "thin, vertical, short lines, in the upper half, scattered"
              (core words: thin line, vertical, short, upper half, scatter)
```

A plugin is expandable: any description that uses one converts mechanically into
a description written with the core alone.  Because of that,

- the renderer only has to know the core
- a bug in a plugin cannot break rendering
- porting to another language only requires porting the core
- plugins cannot collide with each other

### 4.6 Declarative Plugin Documents (v1.90.0 / Build 589)

Vocabulary plugins are UTF-8 declarative documents, not executable code. One `.inku-plugin.md` file contains a front-matter manifest and word entries. The manifest requires `namespace`, `name`, semantic `version`, `authors`, `languages`, `license`, and Japanese/English descriptions. Each entry provides namespaced identity, Japanese/English surfaces and `fires_on` nouns, optional bilingual Saijiki notes, and equivalent bilingual expansion templates. Arbitrary code, URLs, and file references are forbidden.

The pipeline order is **Stage 1 output -> plugin expansion -> core-only DDL -> Stage 1.5 -> Stage 2**. Templates may use core normalized DDL plus bounded expansion forms: deterministic `N to M` repetition (with unit-preserving singulars, and Build 591 multi-word English units such as `leaf forms`, `blades`, `cloudforms`, `spots`, `arcs`); a `member name: definition` local composite inlined at each member (Build 591; undefined references are rejected at load); `note:` comment lines that carry no expansion (Build 591); an `anchor` whose region determines separate member bands, including a Build 591 `anchor ... at N to M spots` nested repetition (spots x per-anchor members, depth two, each spot its own band); and symbolic `{region: ...}` translation, whose canonical key list is published by reference §3 and includes a `bottom band`, with an `upper-left to lower-right diagonal band` resolved as a computation (member sub-regions along a descending diagonal) rather than a rectangle. The same input chooses the same count, member regions, and rotations.

Core DDL with explicit numeric regions after expansion is already composition-resolved. Stage 1.5 still performs normalization but must not append a separate finished-work recipe or auxiliary shapes, and Stage 2 must not retain support instructions beyond the explicit region count. This cap applies to Score instruction count; it does not freeze `arrangement.count` inside each instruction. Visible multiplicity can therefore remain model-dependent: for the minimal twin-arcs fixture, Mistral stays at two arcs while Qwen may repeat the two instructions into more than two visible arcs. Build 590 accepts this as a known limitation.

The load-time validator rejects the whole document with explicit reasons for missing manifest fields, reserved namespace or qualified-word collisions, recursion or non-core plugin references, more than 48 instructions per word, repeated members stamped at fixed coordinates, and URL/file references. This is syntax validation before execution, not a governor of the work itself. Runtime closure or budget failure drops the expansion without repair, records a warning, and leaves a normal core approximation. Build 591 adds unknown region keys and undefined member references to the load-time rejections, exempts comment lines from the closure check, and removes the silent center fallback (an unknown key at runtime falls back to the default band with a recorded warning). Since v1.92 the closure marker table (shapes, verbs, relations, and the Saijiki modifier categories) is derived from the saijiki table; reference §1 and §3 always show the current values.

An explicit qualified term always fires. Stage 1 may resolve a `fires_on` noun only when it is the stated subject; it must not extend firing to metaphors, unclear subjects, or unknown objects. When several `fires_on` phrases match at the same position, only the longest wins (Build 591, removing substring mis-fires — e.g. the input "枯草" no longer also fires the "草" undergrowth word); phrases at different positions still fire independently. Only the loaded surface/trigger vocabulary is injected into Stage 1, never template bodies. Stage 1.5 and coerce cannot introduce plugin words. Input-term-to-qualified-term provenance is returned by the API and stored in ordinary derivation metadata, while plugin documents and dependencies remain absent from Score, canonical DB work data, and rh2.

`server/plugins/` is signature-checked so add/delete changes appear without a restart; management APIs and `inku-cli plugin list / validate / reload` expose status, rejection reasons, validation, and forced reload. Settings shows loaded/rejected documents, while Saijiki distinguishes qualified plugin words and bilingual notes. Removing a plugin must not change replay SVG or rh2 for a saved work because replay uses the already saved core Score and seeds.

The built-in `canvas-aspect` system plugin remains separate and uses its existing hook and per-user plugin storage. Vocabulary plugin documents do not gain that code-level hook.

### 4.7 Separation From the Render Engine Pack

A vocabulary plugin is a macro over core vocabulary; it is not a way to replace
the drawing core.  Replacing the drawing core carries a heavier responsibility
and is treated separately, as a **Render Engine Pack**.

A render engine is the boundary that takes `JSON Score + render options +
server-owned color metadata` and returns `SVG + render metadata`.  The current
`renderer.py` is the `default` engine.

The boundary exists so that drawing strategy can later branch by model or by
expressive goal:

- an engine that favors stable SVG for display
- an engine that favors editability in Illustrator or Affinity
- an engine that strengthens one particular expression — geometric
  construction, planes of color, material feel
- an engine tuned to a particular Stage 2 model or prompt pack

A render engine must not break the compatibility of the canonical DB record.
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

### 4.8 Correspondence With Bonsai

The design agrees with the bonsai figure.  Bonsai does not invent a new plant;
it makes a world out of the arrangement and combination of plants that already
exist.  A plugin should have the same property.

It does not add a feature.  It gives a name to a combination that is already
there.  That is what a plugin is for.

### 4.9 Official Reference Plugins

DDL's stance on the split between "official" and "unofficial" plugins:

**The approach: provide only a few official reference plugins.**  A handful —
Nature, Bamboo — are offered as worked examples of how a plugin is written.
Anything else users write freely, and there is no official registry.

**What that buys:**
- the manner of writing a plugin is shown by example
- the burden of official review is avoided
- users can read a reference implementation and write their own
- the core team stays on the core

### 4.10 Namespace Convention

Every plugin carries a namespace:

```text
Nature.雨
Nature.風
Bamboo.竹
Seasons.桜
```

So that:
- where a plugin is used is evident from the description
- words of the same name do not collide (`Nature.雨` and `Weather.雨` stay
  distinct)
- Saijiki can display plugin words in categories of their own

### 4.11 The Final Judgment on Freedom Is Reserved

The principles above push hard toward "a plugin is limited to a macro over
vocabulary."  **The final extent of that freedom, however, is decided by
implementation and testing.**

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

Questions still to be answered:

- how far meaningful expression reaches with core primitives alone
- whether limiting plugins to vocabulary macros still expresses concrete worlds
  such as Nature or Bamboo
- how far to relax the principle if extension needs show that macros are not
  enough

**Even when a principle is relaxed, keep an explicit line that avoids becoming
Emacs.**  When freedom is increased, decide only after stating what that freedom
takes away.

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
- **Normalized DDL**: the executable specification, in core vocabulary only.
  Stage 1 transcribes it from the description (there is also an entrance for
  writing DDL directly).
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
therefore part of the specification, not a matter of readability. The rule for raising the version
when that order changes lives under "When the version goes up" in the
[render engine version history](docs/spec/render-engine-history.md).

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
| DDL text (the layer humans write) | the author's own language (Japanese, English, others) |
| JSON Score (the layer machines read) | English keys throughout |
| LLM (the converting layer) | multilingual understanding |

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
instructions. API requests retain explicit `ja` and `en` values for compatibility
and comparison runs, while `ui_lang` provides display context. With `auto`, the
server lightly detects Japanese or English from the input text and uses the UI
language only when the text itself has no language signal. The resolved language
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

Developing in Japanese and English side by side works as a device for raising
the quality of the design.

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

Builds 403-427 extend the English instruction path beyond structural routing.
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

DDL is not finished in one pass.  The round trip — **description -> output ->
description again** — is a premise of the design.

### 7.2 Screen Composition (in concept)

**Phase 1: Initial (instruction generation)**

```text
[drawing area]
    |
[instruction input area]  <- write the first idea
    |
[DRAW button]
```

**Phase 2: Next (instruction generation)**

```text
[output of the prev. inst]   [output of the next inst]
      |                             |
[show the previous            [write the new
 description]                  description]
                                    |
                             [DRAW button]
```

The difference between old and new is made visible in color, so that what
changed and what was added can be seen.  It is designed as **the trace of
refinement**: not a programmer's diff, but the visualization of a process of
paring a text down.

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

### 7.3 LLM Model Inspection

A view that puts several LLM models side by side — Gemma 4 and Opus 4.7, for
instance.  The same description goes to different models and the differences in
the output are seen.  It makes visible the principle that **the choice of model
is itself a creative variable**.

### 7.4 The Design of the Instruction Box

**The basic stance: the opposite of IntelliSense**

IntelliSense reduces mistakes by offering candidates *before* you write.  DDL
takes the opposite view: **the moment of making lives inside the writer's
hesitation**.  In the stillness where the hand stops for an instant while about
to write "place," the realization arrives that "line up is closer."  When
candidates keep appearing, thought is pulled toward them and no gap is left in
which to look inward.

**What is adopted**

1. **A blank writing area**: nothing is offered while writing.  Close to the
   purity of a tanka manuscript sheet
2. **The vocabulary dictionary placed elsewhere, as Saijiki**: the writer goes to
   consult it actively
3. **Interpretation feedback after writing**: the words written take on a color
   showing the degree of interpretation (§7.6)
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
| a permanently displayed list of choices | it forces the order "look outward, then draw from within," which is the reverse of the order of making |

**The grounds for the design**

Nobody writes a tanka while keeping a list of seasonal words in view.  You write
the word that rose from inside you, and check the seasonal word afterwards.
**From the inside out, then confirmed on the outside** — that is the right order.

### 7.5 Saijiki

DDL's vocabulary dictionary is called **Saijiki**.  The English edition keeps the
name.

**Grounds for the name**

- the internationalization of haiku has already given the word some recognition
  among English speakers
- it states plainly that the concept comes from Japan
- leaving an untranslatable word untranslated agrees in itself with DDL's respect
  for language
- for an English speaker, the very act of opening a button labeled "Saijiki"
  becomes an experience of seeing vocabulary from another culture's point of view

**Category structure**

Saijiki displays 10 categories — forms, angles, touches, continuity, colors,
movements, places, motions, proportions, relations — together with the qualified
words of any loaded plugin.  The current values of the vocabulary are given by
the §3.1 table and by reference §1, and the web Saijiki display is served from
that same saijiki table (v1.92: `GET /api/saijiki` plus a synchronized store over
the snapshot bundled into the build).

The Japanese category names are written in hiragana.  Kanji is stiff; hiragana
lowers the threshold of writing.  The English category names are forms / angles /
touches / continuity / colors / movements / places / motions / proportions /
relations.

**Placement policy**

- it is not shown in the writing area
- it is opened actively, from a `Saijiki` button in the UI
- it stays closed while writing and opens only when the writer is unsure
- it is designed so that Saijiki is not something you look at but something you
  go to look at

The Saijiki drawer is read-only (v1.98).  Clicking a vocabulary chip shows a
preview rather than inserting the word; insertion happens only in the inline
Saijiki inside the DDL editor dialog, which also shows the qualified words of
loaded plugins.  The open/close toggle sits in the toolbar below the canvas.

### 7.6 Interpretation Feedback

After DRAW is pressed, **a color showing the degree of interpretation** is
applied to the text that was written.

**The thinking behind it**

- where IntelliSense offers candidates *before* writing, this gives feedback
  *after* writing
- it is close to the feeling of a teacher marking a tanka in red afterwards —
  except that it is **not a correction but a presentation of how it was read**
- the message is "the LLM read it this way," never "right" or "wrong"

**Expression through color (a proposal)**

Expressed in the density of ink.  Assertive colors are avoided.  The feeling of
calligraphy.

| State | Expression |
|---|---|
| a word interpreted with certainty | dark ink |
| a word interpreted vaguely | pale ink |
| a word not interpreted | nearly transparent, faint |

Where extended vocabulary is used — the Nature plugin and the like — one
candidate is to express it in a soft color distinct from ink, a pale vermilion
for instance.

**Cautions in the design**

- the color must not become an evaluation.  If the writer shrinks, making stops
- say "the LLM could not be certain," not "it could not be interpreted."  The
  cause is presented as a limit on the LLM's side, not on the writer's
- explain what the colors mean explicitly in the UI

**A further form: showing the gap in interpretation**

Beside the word that was written, how the LLM read it is noted in small type:

```text
佇ませる [place with stillness]
```

The writer can see the gap between "the words I wrote" and "the LLM's
interpretation."  That gap is itself material for writing the next description.

- "if the LLM read it as *place quietly*, then next time I can simply write
  *place*"
- "no — *佇ませる* is closer to what I meant.  That the LLM could not read it
  means there is something here I have not yet seen"

Either reaction is creative.  **The gap generates the thought.**

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

Short English tabs, buttons, and labels follow the casing and vocabulary rules
in `web/src/lib/i18n/GLOSSARY.md`, which is canonical for the English interface
and is enforced by `npm run lint:i18n` (v2.7.1).  At iPad-class widths the
Canvas tabs and the displayed Models / Color / Canvas / creation metadata wrap
into two rows, and the left panel scales with the viewport rather than clipping
the work metadata.

The web app is the current reference interface. v1.72 makes refinement and model comparison first-class authoring surfaces. The `Refine` tab offers touch, layout, reading, color-catalog, and variation (§12.13) changes as a radio-style choice: exactly one intervention may be selected per refinement step, so each lineage edge remains attributable to one cause. Selecting variation reveals an amplitude choice (subtle/moderate/sweeping, default moderate) directly under its radio; one candidate uses one fresh server-issued seed and four candidates use four, with no separate variation section or button. The chosen refine element is remembered in the browser. Reading is one upstream intervention whose downstream layout and touch are regenerated. One or four candidates vary only the selected element, use the same selection-and-save workflow, and are displayed in a two-column grid (a single candidate fills the full width) sized to fit within the dialog. Saving selected refinement candidates keeps them in ordinary history without automatically starring them; the save control distinguishes unsaved, saving, and saved states, and a saved candidate cannot be saved again. Candidate generation disables other generation and drawing actions; after three seconds it exposes the shared Stop control, backed by request abortion. Progress copy names the work actually being performed. Reading candidates expose normalized DDL on image hover. Render and vary seeds are independent JavaScript-safe random integers carried from initial generation through candidates, history, and replay. Display rendering makes touch-seed changes visible without changing canonical composition coordinates. A color-catalog refinement keeps DDL, Score, canvas, layout seed, and render seed fixed while applying a catalog other than the parent's; four options use distinct catalogs when possible. All non-color refinements inherit the displayed parent work's effective catalog and canvas rather than the next-drawing controls. Color edges use `catalog_change` and record the before/after catalog IDs. The caption visibility choice is persisted per user. Previous/next navigation preserves the active Adjust or Model comparison subview inside Refine and changes only its target work. Adjustment candidates are temporary state owned by their source work: explicitly selecting a work from history, lineage, nearby works, or navigation, or starting a new generation or DDL render, clears them. Merely switching between Adjust and Model comparison does not. A target change also resets the target-owned model-comparison results, reading diff, replay error, intermediate-lineage notice, and lineage fetch state. Any in-flight model comparison is aborted, and only the latest lineage request may update the view.

The web UI keeps direct operational labels while the specification retains the musical metaphor: performance is shown as touch, composition as layout, and interpretation as reading. Model comparison lives beside `Adjust` as a subview inside the Canvas-side `Refine` tab and shows no judge values. It provides three modes: `Shared Stage 1/2`, `Fixed Stage 1 + compare Stage 2`, and `Compare Stage 1 + fixed Stage 2`. Shared mode uses each selected model for both stages. Fixed modes select one model for the fixed stage and up to four for the compared stage. Only the exact Stage 1/2 combination used by the target work is prohibited; a model used by the target remains selectable when the fixed-stage pairing makes the combination different. A floating tooltip explains prohibited choices. Models are always selected explicitly, and no unselected fallback model is run. Changing the target clears stale comparison results and aborts any comparison still in flight. Saved comparison results record the actual Stage 1 and Stage 2 models and may be adopted or starred into history.

Each Lineage-card work menu offers, under the heading "Edit the work" and in this order: drawing elements, description, DDL, model, language, autonomous refinement, and moving the work to trash (item labels are shortened to the target noun). The dialogs opened by the three comparison actions are titled "Edit drawing elements", "Edit models", and "Edit languages". Description and DDL editing open modal dialogs initialized from the selected work. Drawing saves a `description_edit` or `ddl_edit` child, returns to Lineage, and focuses the newest child together with its ancestors. The three comparison actions target the selected card and open the corresponding existing Refine subview in a modal dialog; they do not duplicate comparison logic. Closing the dialog returns to the originating Lineage view, while the regular top-level Refine tab retains its panel layout. The former Manual Refine modal has no menu entry. Trash is visually separated from comparison actions with an explicit high-contrast result label.

Major UI areas:

- App rail: compact navigation with an explicit expand/collapse toggle, user
  menu, profile, settings, language and theme controls
- Input panel: single drawing, batch drawing, and demo modes
- DDL editor: editable normalized DDL embedded in the single drawing flow, with
  Saijiki word highlighting and an expanded dialog editor
- Canvas panel: SVG display, zoom, pan, output tabs, status bar, export buttons
- History strip: recent works, hover metadata, star markers, pagination
- History manager: larger history view, trash, restore, permanent delete, star filter, and
per-work sharing. The sharing dialog picks a recipient and a permission (read or write) and
lists who currently holds the work. **A work shared by somebody else carries a mark** — this
is the screen where people select and delete, and without the mark another member's work sits
there looking exactly like their own. **Recipients can be picked by name among the members of
your own organisation group**; a member who cannot fetch candidates types an id directly (the
full roster is not opened)
- Settings modal: models, color catalogs, DB status, plugin status, export
  templates, users, theme

The status bar displays the current render context:

- Stage 1 model
- Stage 2 model
- color catalog
- canvas aspect
- star state for the current history item
- SVG / PNG export controls

For history display, model, catalog, and canvas values come from the history
item when available.  For active editing, they come from the current selections.
The canvas panel header also shows the selected work's color catalog, canvas,
and creation time.  The color catalog button in the input panel displays the
currently selected catalog name and truncates long names with an ellipsis.

The settings modal's "other" tab includes history-selection behavior controls.
Users can choose independently whether selecting a history item updates the UI's
current canvas aspect and color catalog to the history item's values, or keeps
the current UI selections.  This setting affects only the UI selection state;
the saved history SVG is displayed as stored and is not re-rendered.

The canvas panel also supports viewing-oriented controls.  A fullscreen icon in
the drawing tab opens presentation mode, which maximizes the current SVG and
shows a compact control bar for history navigation, latest item, star toggle,
instruction caption toggle, and close.  Escape closes presentation mode.  A
caption icon in the drawing tab toggles an instruction caption.  In normal
canvas view, the caption uses 10% left and right margins relative to the drawing
tab and is clipped inside that tab.  In presentation mode, the caption uses 10%
left and right margins relative to the window.  Captions display the original
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
The default templates are `PNG 1024px` and `PNG 2048px`.  The status bar PNG
menu is generated from these templates, and export width is computed from the
current canvas aspect ratio.

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
| Composition | Another composition | composition family, focus, and technique candidates as chosen by Stage 1.5's selection seed, `vary` (§12.11) | one Stage 2 call (Stage 1 is cached; the instructions do not change) |

`vary` does not break the identity of the description — what changes is the
selection, not the interpretation (Stage 1's instructions).  The same
description with the same `vary` value and the same performance seed reproduces
the same output, which is what makes a work replayable from history.

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
realizes this — the five refinement kinds, model comparison, language
comparison, and the Lineage card menu — is in §7.8, "The Reference Web
Application."

---

## 9. The Design of the First Stroke

### 9.1 Requirements

- an inspiration can become the first stroke
- that stroke produces feedback satisfying enough to continue
- chance is not too high, completion does not go too far, and yet it is not mere
  tracing

### 9.2 Where the Needle Sits

```text
chance too high      ->  the author's intent is invisible  ->  motivation goes
completing too much  ->  it does not feel self-made        ->  no meaning in it
mere tracing         ->  DDL was not needed for this       ->  no meaning in it
```

The needle sits right when **the words the author wrote are realized a little
more intelligently than expected**.  That "a little" is what makes the next line
worth writing.

To support a tanka-like brevity, the writing surface carries only a non-blocking
length hint.  Japanese input uses roughly 31 characters as a guide; English input
uses roughly 12 words.  Input is never blocked.  The UI shows no copy that
denies a long description and no evaluative display — only a numeric counter and
a faint change in density, so the form is quietly present without scolding the
writer.

### 9.3 The First Line

Not "what to draw" but "what is on your mind."  The LLM draws the work out of
that.

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

### 10.4 Repair Parts Must Not Become a Fingerprint (v1.52)

The stock parts that Layer 3 repair (coerce) inserts — accent shapes, arcs of
adjacent reaction, vanishing traces — become **the system's fingerprint** if
they repeat with fixed coordinates, fixed shapes and a high firing rate.  A
viewer notices by the second or third work and starts looking for the same
part in every one after that.  It reads as an insertion by the machine rather
than as the artist's motif, and it ruins the viewing of a series.  (Confirmed
in the three-persona review of Build 441: the arc of adjacent reaction
appeared in the same form in 56 of 60 samples.)

Repair parts carry these requirements:

1. **Measure the firing rate per part in the bench and watch the ceiling.**
   There is no floor — a floor would enforce a style (the same root as
   §14.6-4).
2. **Do not hard-code fixed values for shape, position or direction.**  The
   real parameters of an inserted part are resolved from the position relative
   to the element it refers to, from the input hash, or from the performance
   seed.
3. **The firing condition is limited to "the subject breaks without it."**
   Nothing is inserted to average out a style or to lift a metric.

The only ways to lower a firing rate are to narrow the firing condition and to
resolve the fixed values.  Swapping in a different new inserted part (trading
one fingerprint for another) and adding a new governor are both ruled out.

Repair parts such as focal reactions, angular pulses, vanishing traces and
rhythm offsets are measured by marker phrase in CLI analysis, which is how the
firing rate is watched.  Focal adjacent reactions are limited to isolated
visual events where omitting the reaction would weaken the subject.

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
- whether Stage 1.5 expands without overpacking techniques
- whether Stage 2 preserves all DDL elements in JSON Score
- whether deterministic fallback keeps enough DDL content to be reviewable
- whether the renderer makes DDL features visible
- whether the output has enough negative space, sway, and artistic focus

Current render-core tuning records explicit quality metrics for the work in CLI benchmark summaries: `constraint_adherence`, `negative_space_pressure`, `motion_energy`, `color_resonance`, `visual_event`, and `figurative_risk`. These judge metrics are regression sensors, not final acceptance gates or substitutes for human selection. Build 448 confirmed divergence between machine scoring and human review, especially JP #23, so the metrics should not be retuned merely to raise preferred works. Fallback use, server hard timeouts, motif hints, presence counts, color traces, and compositional markers are recorded separately. Queue or retry duration is diagnostic only and is not treated as a primary quality metric, because free inference endpoints can be dominated by external queue behavior.

For NVIDIA free API testing, elapsed time is treated as operational metadata,
not as an artistic quality signal.  Queue delays can indicate service pressure,
but they do not exclude a successful work from aesthetic or structural review.

**The inventory of what is currently implemented moved to
[current implementation status](docs/spec/implementation-status.md) on 2026-07-28.**

### 11.4 The Original Test Plan (v0.8 to v1.6)

What follows was the plan at the time and is kept as a record of what was done.

**Automatic generation of test cases** -- have Opus 4.7 generate the test
instructions.  The axes are **difficulty** (simple, several lines, several
primitives, abstract concept, poetic expression) and **kind** (geometric,
concrete, emotional, poetic).  The generated test cases are themselves an
exploration of the DDL vocabulary.

**The automatic test pipeline:**

```
test instruction set (automatically generated)
    ↓
composer (DDL → JSON)
    ↓ machine judgment: valid / token / primitive
renderer (JSON → SVG)
    ↓ machine judgment: generated / number of drawn elements
result log (instruction / JSON / SVG / error kind / generation time)
```

The log viewer can share the UI foundation of the user-facing drawing tool.

**Order of work** -- (1) build a small test set by hand (10 to 20 cases, spread
across difficulty and kind), (2) write a script to run them automatically
(saving results to a JSON log), (3) expand the test cases with Opus 4.7 (to
around 100), (4) build a log viewer (SVGs side by side for visual review).

---

## 12. The Two-Stage Architecture

### 12.1 Two Stages, Not One

The DDL conversion pipeline uses **two stages**.  One stage is not used.

```text
the user's description
    | stage one: interpretation
normalized DDL (an intermediate form written only in core vocabulary)
    | stage two: structuring
JSON Score
    |
SVG
```

### 12.2 Why One Stage Is Not Used

With one stage the LLM would be doing two different jobs at once.

**Job 1: interpretation (semantic).**  Map the loose expressions of free
natural language onto DDL's vocabulary space.

**Job 2: structuring (syntactic).**  Emit JSON that matches the schema, with
fields such as primitive, region, weight and variation.

What the two ask for is fundamentally different:

- interpretation is a **creative, associative** ability
- structuring is a **mechanical, rule-abiding** ability

Demand both at a high level in a single prompt and both come out
half-finished.  In corner cases especially, the difficulty of the
interpretation induces structuring errors — an LLM unsure how to interpret
also breaks the JSON form.

The existing tests likewise show that one stage cannot carry the corner cases
through to an implementation.

### 12.3 How It Fits the DDL Concept

The two stages match the philosophy of DDL structurally.

Fitted into the three-layer pipeline of §5:

```text
description (the author's own language, free words)
  | stage one: interpretation
normalized DDL (core vocabulary only)   <- where "the fog lifts"
  | stage two: structuring
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

**Options that were rejected:**

| Form | Why it was rejected |
|---|---|
| fully natural sentences ("place a thin line, with a slight sway, near the center") | leaves room for a second *interpretation* in stage two |
| a structured list (YAML-like) | looks like code; it takes the pleasure out of describing |
| function-call style (`place(subject=line, position=center)`) | too close to code |
| a separate modifier line (an early draft that wrote "sway: small" on a line of its own) | never adopted in the implementation. Motion words are written inline as sentences, as in "the line sways finely" (the fixture corpus is canonical). The exception is surface and ground texture, where only the fixed phrases 「面: ...」 and 「地: ...」 are separated onto their own line |

**What the adopted form does:**

- keeps the rhythm of natural sentences (the readability of tanka)
- limits the vocabulary to the core (place, thin, center, and the like)
- writes motion words inline, separating only surface and ground texture with
  the fixed 「面: / 地:」 phrases
- keeps the structure of the format common between the Japanese and the
  English version
- **is designed on the assumption that the author will see it** (it is shown
  in the interpretation-feedback UI)
- names exactly one Saijiki touch on every visible line, arc or outline.  An
  explicitly stated material is preserved; where none is stated, the touch is
  chosen from texture and context.  A shape that is only a filled area is not
  assigned a touch mechanically
- selects burin and drypoint only where the input names that technique.  DDL
  must not be left carrying touchless phrases such as "thin black line" or
  "white horizontal line."  Dynamic few-shot selection always includes at
  least one non-pen material example

### 12.5 Splitting the Model by Stage

A different model can be used for each stage.  **The current implementation
selects a model per stage**: users and administrators set a model for Stage 1,
Stage 2 and Vision separately (the model settings and model comparison of
§8.4, and the llm / vision catalogs of `/api/models`).

The assumption made at design time — Stage 1 a high-capability model, Stage 2
a light one — is kept as policy:

- interpretation (Stage 1) is associative and creative and needs nuance, while
  structuring (Stage 2) has a restricted input and stays stable on a light
  model
- it satisfies both the principle that *the choice of model is itself a
  creative variable* and a practical cost structure

### 12.6 The Design of Stage 1 (Interpretation)

**What Opus 4.7 carries:**

1. read the meaning of a free description (「佇ませる」 -> *place it quietly at
   the center*)
2. normalize with an understanding of the bonsai sensibility and the rhythm of
   tanka
3. choose the most beautiful interpretation where there is ambiguity
4. decide the degree of sway from the atmosphere of the description
   (「ひっそりと」, *hushed*, -> a small sway)

This design draws the most out of Opus's **artistic power of interpretation**.
Reading nuance is hard for a light model, so it is left to Opus.

In the implementation the stage holds to the same boundary.

Stage 1 reads the user's natural-language description and produces normalized
DDL.  Its job is semantic.  It may choose a more visually effective
interpretation when the input is ambiguous, but it should remain within the
core vocabulary and preserve important user intent.

Stage 1 also carries tone, atmosphere, and context into the DDL when possible.
It should not simply extract nouns.  A quiet sentence, a ceremonial sentence,
and a turbulent sentence should lead to different density, focus, motion, and
material choices.

**The policy for the prompt:**

- state the list of core vocabulary explicitly
- share the category structure of the Saijiki
- ask explicitly for a beautiful interpretation
- show examples of "vague description -> normalized DDL" as few-shot examples

### 12.7 The Design of Stage 2 (Structuring)

**What the light model carries:**

- convert normalized DDL into JSON Score mechanically
- put schema adherence first
- no creative judgment is needed (stage one has done it)

**The policy for the prompt (the initial sketch):**

```text
You are a function that converts normalized DDL into JSON Score.
The input contains only the following core vocabulary:
(vocabulary block)
Each word corresponds to the following field of the JSON Score:
... (mapping table)
Parse the input and emit JSON according to the schema.
```

Because the input is restricted, this prompt works as a nearly deterministic
conversion function.  The sketch above is from design time; the vocabulary and
the fixed-phrase relation table of the prompt in use today are derived from
the saijiki table (v1.92).  For the values in use, see reference §1-§2.

In the implementation the stage holds to the same boundary.

Stage 2 converts normalized and expanded DDL into JSON Score.  Its job is
structural, not poetic.  It must preserve DDL elements such as color, material,
movement, arrangement path, rotation, and canvas.  If an element exists in DDL,
Stage 2 should either encode it or fail clearly.

Adjectives, motion words, and texture words modify the primitive that the DDL
already names.  Stage 2 must not add unrequested support lines, support shapes,
or differently colored instructions merely because the DDL says "trembling",
"swaying", "blurring", "thick", "thin", or a similar modifier.  The server also
applies a narrow deterministic contract guard for single-primitive DDL with
motion or texture modifiers: it keeps only instructions matching the requested
primitive and explicit color, drops unrequested auxiliary marks, and applies
the missing motion as sway on the requested primitive when possible.  The
guard is intentionally not applied to multi-motif DDL.

### 12.8 Error Recovery

Splitting into two stages lets error recovery be designed per stage.

**Errors in stage one:**

- there is a word Opus could not normalize -> the UI reports that the word
  could not be understood
- it is visualized as a pale color or as transparency in the interpretation
  feedback (§7.6)
- **it is fed back to the author and does not stop the processing**

**Errors in stage two:**

1. try to repair the JSON in the sanitizer (the existing Kotlin / Python
   implementation)
2. if it cannot be repaired, retry with a prompt that carries the error (at
   most three times)
3. if that still fails, fall back to Opus 4.7 (it costs more but nearly always
   succeeds)

**Added in v1.98:** an empty Stage 1 output is treated as a failure rather than
drawn from nothing. A work drawn through a Stage 1 fallback path records an
`interpret_fallback` reason in history and is marked in the UI. Provider-side
failures are classified by HTTP status into model-gone, authentication,
rate-limit, and other kinds, reported with the failing stage and the provider's
original message (the legacy string-form error path is kept for compatibility).

When Stage 2 cannot return usable instructions because of timeout, empty output,
or transient model failure, the server may produce a deterministic fallback
Score.  This fallback is still expected to preserve the DDL's visible essentials:
quantity, placement path, material words, scene tone, and enough shape variety
to remain reviewable.

### 12.9 Implementation Order (Back to Front)

The policy is to **implement from the back of the pipeline forward**.

**Step 1: build stage two first**

- implement the conversion from normalized DDL (input) to JSON Score (output)
- write the input by hand at first (ten to twenty normalized-DDL examples)
- once stage two is stable, the back half of the pipeline is settled

**Step 2: build stage one**

- the user's description to normalized DDL
- design the prompt with Opus 4.7
- connect it to stage two

**Step 3: UI, interpretation feedback, finishing**

- show the output of both stages in the web UI
- implement the interpretation feedback
- prepare a collection of sample descriptions

**Why back to front.**  Debugging stage one is hard while stage two is
unstable.  Building from the input side leaves you at the mercy of instability
on the output side.  Settling the downstream first lets each stage be debugged
independently.

### 12.10 Handling Latency

Two stages double the latency.  Against that:

**Measure A: show the UI in stages.**  Show the result of stage one — the
normalized DDL — in the UI first.  The user reads the normalized DDL while
waiting for stage two, the drawing, to finish.  The felt latency drops.

**Measure B: cache.**  On the assumption that the same description produces
the same normalized DDL, cache the result of stage one.  Sway enters from
stage two onward.

The cache must not kill the one-time nature of the output (§13.2, role 2).
Macro sway — composition and placement — is realized by the renderer
resolving, at performance time, the relations and regions written in the JSON
Score (§13.8 / §14.4).  A Stage 1 cache and "a different performance every
time from the same description" therefore hold together.  The cache is not a
reason to give up macro diversity.

Measure A was implemented in v1.98 as `POST /api/paint/stream` (NDJSON).  When
the interpretation completes it emits a `stage1` event (normalized DDL, the
model used, token count, elapsed time, and whether a fallback occurred), and
the final `done` event returns the usual `PaintResponse`.  The existing
`/api/paint` is a wrapper consuming the same logic and its response shape is
unchanged, so the CLI and Android needed no modification.

**Measure C: parallelism (later).**  When generating several options, run
stage two in parallel.

### 12.11 The Intermediate Filter (Stage 1.5)

v1.19 introduces a deterministic intermediate filter between stage one
(interpretation) and stage two (structuring).

```text
the user's description
    | Stage 1: interpretation
normalized DDL
    | Stage 1.5: the intermediate filter
expanded normalized DDL
    | Stage 2: structuring
JSON Score
    | Renderer
SVG
```

The intermediate filter is not an LLM but a deterministic DDL converter.  Its
purpose is to expand what Stage 1 extracted, without breaking that intent,
into an input from which Stage 2 can more easily produce several supports,
layers and structures.

It does not, however, pack every technique in every time.  It builds a
deterministic seed from the input DDL and selects only a few layers out of the
mathematical, musical and painterly candidates.  The same input gets the same
expansion, while a different input changes which path, which part and which
focus are chosen.

What the filter draws from is: mathematical and geometric laws; spatial paths
and a non-central focus; color choices in the tone of the scene;
music-derived structures such as counterpoint, canon and harmonic ratios;
painting and material techniques such as perspective, chiaroscuro, drawing,
pointillism, watercolor, oil-paint layering, patchwork, fresco and sumi ink;
and natural or material forms abstracted through the current primitive
vocabulary.  The mathematical, musical and painterly groups are set out below.

**The selection seed and vary (v1.52).**  The selection seed is built from the
input alone by default, so "the same input gets the same expansion" holds as
the default.  Only when the user explicitly asks to vary — the "another
composition" regeneration button — is a vary counter mixed into the seed and
the choice of composition family, focus and technique made again (§8.4).
Varying does not change Stage 1's interpretation, the normalized DDL.  Implicit
non-determinism through auto-increment or a clock seed is prohibited: the
default is always deterministic, and non-determinism belongs only to the user's
explicit operation and to the renderer's performance (§13.8).

**The design policy**

- treat Stage 1's normalized result as canonical and never overwrite its
  meaning
- treat "random" as a forbidden word, always replaced by an explicit placement
- land anything added on the lines, circles, ellipses, squares, arcs,
  arrangements and sways the existing JSON Score schema can express
- treat mathematical, musical and painterly techniques as drawable structures,
  materials and procedures — not as the name of a school or as an atmosphere
- apply techniques selectively; never put every candidate into one drawing
- name one context-selected touch on any line or arc Stage 1.5 newly adds; an
  added phrase must never be returned to a state with no material
- preserve the expansion markers after a composition-family rewrite of focus
  and path, so the same DDL is not expanded twice
- let what changes per work be "which path, which part, which detail is
  brought into focus" rather than "which law it approaches"
- 「中心」 and 「中央」 are not necessarily the center of the canvas
  coordinates.  Stage 1.5 replaces them with a dynamic focus per input (upper
  right, lower left, toward the top edge, and so on), deciding the pictorial
  center per work
- keep several composition families and choose one from the input: diagonal
  bands, vertical rhythm, horizontal strata, radial or concentric, one-sided
  focus, central stillness, retreat to the edge, dispersal.  Do not
  permanently favor particular families such as diagonal or one-sided focus
- when one composition family takes the majority within a bench set, treat it
  as a bias in the selection weights and make it an object of inspection (for
  the acceptance criteria see codex-task.md / tune_bench)
- keep the focus candidates — golden ratio, rule of thirds, silver ratio — as
  regions rather than fixed coordinates (for example an upper-right focus is
  x in [0.56, 0.68], y in [0.32, 0.44]) and resolve within the region at
  performance time.  Do not hard-code focus coordinates
- treat the expanded DDL after the intermediate filter as the response of
  `/api/paint`, as history, and as the input to Stage 2
- store the input-side DDL (the user's text or the Stage 1 output, `ddl`)
  separately in history from the expanded DDL that Stage 2 consumes
  (`expanded_ddl`).  Works saved before the v1.98 split keep only the expanded
  form and the input side cannot be recovered
- the explicit `focus` input added in v1.98 was retired in v2.0.  The focus
  defaults to a deterministic hash choice from the DDL text and moves only as
  the focus axis of variation (§12.13).  The focus the expansion layer
  resolves is recorded in the response and in `history.focus`, and is used to
  recompute and reproduce `moved_axes`

**Mathematical and geometric expansion**

The intermediate filter weaves mathematical and geometric laws, from any place
and period, into the normalized DDL as added layers.

- the golden-ratio position: upper right is `[0.618, 0.382]`
- the intersections of thirds: upper left is `[0.333, 0.333]`
- the silver-ratio position: lower left is `[0.414, 0.586]`
- the vertices of a regular pentagon: `count=5`, `layout=radial`
- Fibonacci-like quantities: `13`, `21`, `34` kept as explicit counts
- radial placement, concentric circles, diagonals, undulating paths

These express beauty as a count, a coordinate, a repetition and an angle
rather than instructing it with a subjective word.

**Expansion from musical technique**

Techniques used in music are treated visually as repetition, displacement,
ratio and opposition.

- contrary motion in counterpoint: a layer of diagonals running against the
  main direction
- the harmonic series: layers of radial arcs and circles that suggest integer
  ratios
- canon: a repetition of the same form displaced sideways a little at a time

Musical terms themselves do not become core vocabulary; the intermediate
filter expands them into the existing DDL vocabulary.

**Expansion from painterly technique**

Painting is treated not as a school but as material and technical evolution.

- one-point perspective: guide lines converging on the center
- perspective: repeated horizontals that show depth
- light and shade: layers of black, gray and white values
- drawing: thin-brush or pencil-like underlines and guide lines
- pointillism: many small circles scattered as points
- oil paint: short, thickly laid strokes of a broad brush
- watercolor: overlapping ellipses and circles that bleed
- patchwork: repetition of colored squares
- fresco: chalk and gray ground lines
- sumi ink: black and gray brush lines, bleeding, gradation

All of these are expressed so that they can be converted into existing JSON
Score fields (`primitive`, `weight`, `variation`, `arrangement`,
`color_cycle`, and the rest).  Paths such as an undulating trajectory, a
diagonal band, top-to-bottom, or the right half are kept as
`arrangement.path`, which the renderer expands into a stable placement.

**The shift in role at v1.51.**  The mathematical, musical and painterly
techniques above used to be implemented as the injection of finished recipes —
layers with fixed coordinates and fixed primitives — and that invited the
repetition of the same auxiliary layer, such as the diagonals of contrapuntal
contrary motion.  Since then Stage 1.5 expresses a technique first as **the
attachment of a relation predicate to an existing instruction**, and adds an
independent fixed layer only where a relation cannot carry the intent (§14.5).

**An example**

The normalized DDL that comes in:

```text
背景を白で埋める。赤い小さな円を画面全体に点々と十二個散らす。白い細筆の細い線を水平に三本引く。
```

An expansion after the intermediate filter:

```text
背景を白で埋める。
赤い小さな円を画面全体に点々と十二個散らす。
白い細筆の細い線を水平に三本引く。
赤い小さな円を正五角形の頂点に五個並べる。
赤い小さな円を放射状に十三個並べる。細かく震える。
赤い小さな円を波打つ軌跡に沿って二十一個散らす。ゆっくり揺れる。
白い細い線を対位法の反行として右下がりに三本並べる。
白い細い線を一点透視法として中央へ向けて八本引く。
赤い小さな円を点描として画面全体に点々と三十四個散らす。
白い小さな円を右上の黄金比の位置に一点置く。
```

### 12.12 Folding Away the Staffage Level (v2.11.0)

**The staffage level was removed as an axis, not retuned.**

From v1.97 to v2.10, staffage — the minor accompanying elements each layer
added around the subject on its own — had a level the user chose at generation
time: `none`, `sparse`, or `auto`. It mapped deterministically onto three
layers (a norm sentence in Stage 1, the candidate pool in Stage 1.5, an
insertion budget in coerce), was saved per work, and was inherited along a
lineage.

**What was wrong was the dial, not its granularity.** The purpose of this
application is to generate DDL that follows the description and to render that
DDL faithfully, and **adding — or subtracting — what the description does not
ask for and cannot be inferred from works against that purpose** (design
principle, §3). A painter places staffage in relation to the subject; there is
no dial for "how much of this to leave to the machine".

**The behaviour that remains is exactly what `none` did.** Stage 1.5 rewrites
the focus and appends nothing. The six coerce branches that invented an
instruction — a visual event, a composition anchor, context energy, a motion
floor, a surface tension mark, a focal-event reaction — were deleted. **The
three delivering branches (`with_ddl_coverage`, `with_complex_motif_repair`,
`with_shape_delivery_repair`) stay**: they do not add, they deliver what the
description stated and the Score failed to carry.

**The record on past works is kept.** The `history.tenkei` column and the
`tenkei` field of the history response were not removed, so each of the 2,176
works saved before the removal can still report the level it was drawn under
(shown in developer mode only). Nothing new carries a value.

Two behaviours that used to sit under the level were kept, decoupled from it,
because neither is staffage: the **plugin transcription guard** (Stage 1.5 adds
no finished recipe to an input whose plugin expansion returned transcription
instructions — the boundary of §4.6 extended past the transcription) and the
**pure-invocation bypass** (an input made only of qualified plugin terms is
transcribed rather than passed through Stage 1). The first prevents delivering
one subject twice; the second keeps an explicitly named term from being
rewritten by a model.

### 12.13 Variation (Stage 1.5, v2.0)

Stage 1.5 is the application's own layer: it is deterministic, uses no LLM,
and the author does not intervene in its individual parameters — by design
principle, not by implementation convenience. The author's handles are the
input text, `composition_seed`, and **variation** (強度/amplitude + seed).
The author writes, the application shakes, the author chooses.

Variation (v2.0, "hensou") shakes the expansion layer as a whole in one
explicit operation. Amplitude is discrete — small, medium, large. Which axes
move is decided by the seed; the same (amplitude, seed) always reproduces the
same expansion, and variation is never inherited along a lineage. **There is
one official axis: focus.** It was seven until v2.11.0; the other six
(composition family, touch material, adopted count, main/contrast colors, type
swap, type family) all shook sentences Stage 1.5 had appended on its own, and
they went away with the candidate pool when staffage was folded away (§12.12).
Focus stays because it decides where the description is read toward, not what
is added to it. The amplitude still reaches the output: it is part of the
offset key, so the same seed resolves a different focus at small, medium and
large. An axis reported as moved is guaranteed to produce a real difference in
the expansion. Candidates come in ones or fours (same amplitude, distinct
server-issued seeds), each card showing what moved (from → to in the official
vocabulary). The four existing refinement kinds keep their one-axis-chisel meaning; variation is a
distinct operation that shakes several axes at once, presented in the UI as
the fifth refinement radio. Terminology: variation (hensou) belongs to Stage 1.5 — a
deterministic variation of the score; yuragi (sway) belongs to the renderer's
nondeterministic performance. The replay contract (same Score + same seed =
same work) is untouched, since variation happens before the Score exists and
is not an rh2 ingredient.

### 12.14 What the Renderer Owns

This subsection is on the operational side.  The concept of the renderer as the
layer where sway is performed belongs to §13.8; what follows is what the
implementation of that layer actually holds.

The renderer converts JSON Score into SVG.  It owns visual realization:

- coordinate normalization
- material-specific line and contour treatment
- motion and wobble realization
- primitive expansion
- SVG filters and texture effects
- canvas aspect handling

The renderer is allowed to produce controlled sway, but it must preserve
the JSON Score's intent.  Each render may carry a `render_seed`; providing the
same seed makes replay reproducible while leaving the canonical Score stable.
The two scales of the performance, and the version history of the render
engine, are in §13.8 and §13.11.

Human, face, animal, and group motifs are not drawn as literal objects.  Stage 2
and the coercion layer convert them into `Score.presence`: presence kind,
intensity, center of gravity, symmetry, gaze pressure, group behavior, and
contour density.  The renderer realizes presence as faint arcs, edge-biased
focus, asymmetric spacing, and contour-density pressure.  It avoids fixed
silhouettes such as stick figures, head/body pairs, wing/tail marks, or rings
of identical ellipses.

The primitive vocabulary includes `polygon` for polygonal language.  Individual
pentagon or hexagon primitives are not added; polygonal intent is represented
with `polygon` and `sides=5-8`.  Motion energy is handled by trajectory,
rotation, diagonal placement, wave paths, and asymmetry rather than simply
increasing count or density.

The score coercion layer also contains rendering-core quality repairs used by
the current default engine.  These repairs are deliberately generic rather than
prompt-specific, and must not become a visible system fingerprint.  Quiet, mist, memory, shadow, and neon-blur contexts apply
density and negative-space governors so vertical lines, particles, large filled
shapes, or background surfaces do not overwhelm the work.  Motion words that
arrive without an effective trajectory can receive a small directional motion
floor, and requested colors that appear only in a color cycle may be promoted to
a primary stroke so the color intent remains visible.  Visual events are
distributed across available vocabulary: when a scene lacks angular anchors,
the repair may add a small `polygon`; when repeated lines dominate, it shapes
the existing line group with syncopated spacing, preserved negative space,
directional fading, and slight endpoint gaps instead of increasing density.

What these repairs may and may not insert is governed by §10.4, "Repair Parts
Must Not Become a Fingerprint": the firing rate is watched from above and never
from below, fixed coordinates and shapes are resolved from the event anchor,
the input hash or the performance seed, and a part fires only where leaving it
out would break the subject.

SVG export has three profiles:

- `display`: the default server-rendered SVG used for web display, history,
  PNG generation, and artifact rebuilds.
- `editable`: generated on demand from JSON Score and server-owned color catalog
  metadata, with stable ASCII IDs and layer-like groups for Illustrator and
  Affinity editing.
- `compat`: generated on demand from JSON Score and server-owned color catalog
  metadata, avoiding filters and clip paths for broader SVG compatibility.

The DB stores only the `display` SVG in `history.svg`.  Editable and compatible
SVG files are regenerated at download time rather than stored as additional DB
payloads.

### 12.15 The Sketch-from-Life Layer (Stage 0.5, v2.9.38)

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

Note that **`thinness` is not a Saijiki word** (author's ruling, 2026-07-29). Stage 1 reads thinness words and writes them into the normalized DDL, but they appear neither in the §3.1 vocabulary table nor in the Saijiki display.

#### Wild (engine 12; its reach in engine 14)

**Separate from the three layers, one switch lifts the ceiling on the performance itself.** The UI calls it 暴れる — wild.

- **One switch for the whole work**, not per stroke and not per tool. **In engine 12 it reached only the line primitive** (circles, ellipses, triangles, squares, polygons, arcs, fills and hatches came out byte-identical with it on). **Engine 14 extends it to contours, arcs, fills and hatches**, so the implementation now matches the description
- **It removes only the amplitude ceiling and the ban on self-intersection.** Endpoint pinning and determinism hold when it is on: the same Score, the same seed, and the same state render the same SVG every time
- **It is recorded and replayed.** Stored as `render_wild` beside `render_seed`, and included in the edition identity (`rh3`). **The same Score performed wild and performed plainly are different works**
- **It is a multiplier on a tool's habit, not a source of one.** A tool whose wobble terms are zero (`rotring`) does not move when it is on. **A machine has nothing to unleash**

This sits in a different layer from variation (Stage 1.5). Variation is a deterministic transform of the score; wild leaves the score alone and widens the performance. (The table of layers is in the [render engine version history](docs/spec/render-engine-history.md).)

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
| burin | almost_none | a hard, certain engraved line. Round ends, no texture filter |
| drypoint | burr_noise | bleeding and scratchiness from the burr. Its own burr treatment |
| computer | periodic_quantized | it sways, but **it repeats without error**. Integer-period sine and rounding to a lattice. The material is what sampling leaves behind (see "engine 13" in the [version history](docs/spec/render-engine-history.md)) |

Reference §6 is the source of truth for the numeric characteristics (stroke
width, opacity, dasharray, presence of a filter).

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
| quality | 揺れる, 波打つ, 震える, 滲む |

**English, movements:**

| Dimension | Vocabulary |
|---|---|
| amplitude | fine, large |
| frequency | quickly, slowly |
| quality | swaying, undulating, trembling, blurring |

Scatter in placement is not ゆらぎ. It is carried by うごき (motions, "scatter")
and by `arrangement` (layout / path / jitter).

### 13.7 Sway from Phenomena: the Nature Plugin

Sway that comes from a natural phenomenon is provided as a Nature plugin. The
writer does not write sway parameters; the writer **calls the phenomenon**.

**Basic form:**

```
ペンで直線を 中心に 置く
Nature.風を 通す
```

or:

```
筆で円を 並べる
Nature.うねりを かける
```

"Let the wind through", "run a swell through it" — a natural phenomenon can be
woven into the description as a verb. It reads close to the way a tanka reads.

**Representative Nature plugins (candidates for reference implementation):**

- `Nature.風` (wind): a slow horizontal wave
- `Nature.うねり` (swell): fine waveforms superimposed
- `Nature.揺れ` (sway): small rotation about a center axis
- `Nature.震え` (tremble): small high-frequency oscillation
- `Nature.無風` (no wind): sway suppressed, including the material's own

**An example of macro expansion:**

```
Nature.風, conceptually, expands to:
  for every line and form
  a gentle horizontal wave
  amplitude: 2-5% of the drawn object's size
  frequency: 1-2 cycles across the canvas width
  shape: Perlin noise
```

Expansion is only a writing-down into core vocabulary. Following the plugin
principles, it does not change any core mechanism.

**State of the implementation (a v1.92 note):** the proper place for plugin
expansion is the declarative plugin layer immediately after Stage 1 (§4.6). Only
the three words `Nature.風` / `Nature.うねり` / `Nature.無風` remain as a v1.70
reference implementation, **expanded by hard-coded logic inside Stage 1.5** (they
expand mechanically only when the `Nature.` namespace is explicit, and add no new
primitive and no new Score field). Moving these three into declarative plugin
documents is outstanding work — until it happens, their static display in the web
Saijiki stays frozen — and when it happens this section folds into §4.6. The
plugin principles in §4.3 are not relaxed for them.

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
| `quality` | `none` / `white` / `perlin` / `pink` / `wave` | kind of noise (from weight) |
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

When a short line is given sway, prefer `dimensions=["position_x","position_y"]`
so the sway is not crushed against the line's length. For long horizontal or
vertical lines, the base axis is `position_y` for a horizontal line and
`position_x` for a vertical one.

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

#### How a stated count is treated (v2.7.6)

A count written in plain words in the description is stronger than anything
inferred downstream.

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
reproducibility on the same footing as the version.

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

**Stage 2 (structuring) produces the JSON Score, in part:**

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
        "frequency": "high",
        "quality": "perlin",
        "dimensions": ["position_y"]
      }
    }
  ]
}
```

**The renderer:**

It takes the JSON Score and, from the `variation` information, selects the actual
sway function — Perlin noise, fine amplitude, high frequency, along the y axis —
and generates the SVG. Each replay is performed with different random values.

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
expression). Alongside this, the hatch and crosshatch surfaces were replaced with
bands of touch (`class="surface-stroke-v1"`) instead of geometric straight lines
(centerline, angle, interval, and count unchanged; rotring stays geometric), and
sways that are not performed were excluded from the seed key so that the presence
of an inactive sway no longer changes the rendered bytes. The render engine
version went to 9.

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

The current JSON Score is a flat juxtaposition of instructions and holds no
vocabulary for the relation between elements.  Place, line up, fill, and scatter
are all unary verbs.  That absence produced two consequences:

1. output looks like independent parts set side by side
2. the grammar of composition exists only in Stage 1.5's fixed technique recipes,
   so the same auxiliary layer repeats (contrapuntal contrary-motion diagonals,
   for instance)

A vocabulary of relation adds a predicate — syntax — to the core rather than a
noun.  It sits well with the principle that the form pares away the ego: a
grammar of relation is a form that forces compositional judgment on the writer,
not a license for free rein.  It contradicts neither plugin principle 1 (limited
to a macro over vocabulary) nor the Go-like restraint.

### 14.2 Observable Relation Vocabulary

The distinction §13.3 draws between emotion words and motion words extends to
relation.  Only physical, externally observable relations are allowed into the
core.

**The initial set is limited to these five words:**

| Word (ja) | Word (en) | Meaning | `relation.type` |
|---|---|---|---|
| 沿う | along | placed along the path or direction of the preceding element | `along` |
| 触れない | not touching | approaches the preceding element without contact | `not_touching` |
| 切る | cutting | crosses the preceding element and makes a visual break (the *kire*, the cut, of tanka) | `cutting` |
| 間に | between | placed in the region between the preceding two elements | `between` |
| 触れる | touching | contacts the preceding element; coinciding endpoints compose a closed form | `touching` |

**Words excluded**: nestle up to, answer, converse with, resonate with — words of
intent and personification, not observable from outside.

As of the v1.52 close, `relation` in the JSON Score appears only where the
normalized DDL carries an explicit previous-object phrase.  The fixed phrases are
`前の線に沿って` / `前の形に触れない` / `前の線を切る` / `前の二つの間に` in
Japanese, and `along the previous line` / `not touching the previous shape` /
`cutting the previous line` / `between the previous two` in English.  `touching`
is used only where `前の線に触れる` / `前の弧に両端で触れる` or `touching the
previous line` / `touching the previous arc at both ends` makes the contact
explicit; it is never granted spontaneously.  Notions that arrive from natural
language — around, on the same beat, leading or lagging, near or far — are not
relations, and are expressed through position, path, rotation, and spacing.

**Second-round candidates (judged after measurement)**: overlapping, set apart,
same direction, opposite direction, thinner than, continuing.  They are added
only once measurement shows the current words to be expressively insufficient.
`continuing` was confirmed to work mechanically in sketches but showed no
decisive expressive value: the persuasiveness of a withered leaf turned out to be
rate-limited by the cloudform's surface and ground expression instead.  It is to
be retested after that expression improves, and stays a second-round candidate
until then, following the §4.11 procedure — a final judgment reserved, with its
accounting.

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
| `type` | `along` / `not_touching` / `cutting` / `between` / `touching` | the kind of relation |
| `gap` | `narrow` / `medium` / `wide` | a guide distance; the concrete value is resolved by the performance |

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
- `along` -> position, phase, and length decided per performance inside a band
  that follows the preceding element's path
- `cutting` -> the crossing angle and the intersection with the preceding
  element, decided per performance within a range
- `between` -> decided inside the region between the preceding two elements
- `touching` -> applies to line and arc only; the element's two endpoints are made
  to coincide with the two endpoints of the preceding line or arc as the
  performance realized them

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

A relation that cannot be resolved — the preceding element is a background fill
with no contour, say — is dropped by the validator or by coerce, with a warning
recorded.  Unresolvability that becomes apparent only at performance time
(degenerate geometry, grid placement, a preceding element with no endpoints) is
likewise dropped by the renderer with a warning recorded (v1.94).  The
instruction is then drawn with ordinary placement and no relation — graceful
degradation.

### 14.5 The Shift in Stage 1.5's Role

Stage 1.5 moves from "injecting a finished-work recipe" to "attaching a relation
predicate to instructions that already exist."

| The old recipe | Its replacement by relation |
|---|---|
| contrapuntal contrary motion (a fixed layer of opposing diagonals) | `cutting` against the main element (once second-round vocabulary lands, "opposite direction") |
| a stippled ground (a fixed scatter) | a scatter that avoids the main element: `not_touching, gap=wide` |
| a bias in the margin (a fixed margin) | held away from the main element with `not_touching, gap=wide` |
| the auxiliary lines of one-point perspective | converging on the main element with `along` |
| a round (repetition shifted sideways) | a chain of `along, gap=narrow` on the preceding element |

Stage 1.5's output thereby becomes **subordinate** to the elements of the input.
When the input changes, what the relation attaches to changes with it, so
repetition of the same auxiliary layer becomes structurally unlikely.

### 14.6 Constraints and Prohibitions

Given the lesson of tune_bench Builds 346 through 436 — an accumulation of
one-directional repair layers contracted the output distribution — the following
hold when relation is introduced.

1. **Do not build a relation-repair governor.**  An invalid relation is not
   repaired; the validator or coerce drops it with a warning recorded.  The drop
   rate is measured by the benchmark and lowered by improving the prompt and the
   schema, never by repairing
2. at most one relation per instruction
3. the coerce layer **must not add** a relation.  Only Stage 1 (from the
   description) and Stage 1.5 (from the composition) may add one; coerce is
   allowed only to delete an invalid one
4. the benchmark continuously measures relation usage rate, type distribution, and
   drop rate, and inspects for convergence onto a particular type.  No floor is
   set on the firing rate, however — a floor enforces a style (the lesson of the
   Build 428 focal-event floor)

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
computing rh2 is unchanged.  The score holds only the process parameters of the
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

---

## 15. Development Policy

### 15.1 Axes of Development

**Main axis**: web UI (browser) + Python FastAPI + the Opus 4.7 API

- the reasons: speed of development, ease of demonstration, room to grow
- testing and iteration are done on the Mac

**Complementary axis**: an Android app (Pixel 9) + Gemma 4 E2B-IT

- end-to-end operation confirmed
- kept as the "it runs on a local LLM too" point of difference
- further development is kept to a minimum

### 15.2 Phase 1 (completing the PoC) -- reached by v0.8 (the plan as it stood)

- [x] build the FastAPI server (the `/compose` endpoint)
- [x] connect the Opus 4.7 API (reusing and updating the existing `composer.py`)
- [x] confirm the SVG renderer (reusing the existing `renderer.py`)
- [x] implement the web UI (description area + SVG display + iteration UI)
- [x] the triple display of DDL text, JSON Score, and SVG

### 15.3 Phase 2 (raising quality) -- reached by v1.6 (the plan as it stood)

- [x] generating several variations at once
- [x] SVG download
- [x] a collection of sample DDL texts
- [x] the LLM comparison view (Gemma against Opus)

**The per-version engine record moved to the
[render engine history](docs/spec/render-engine-history.md) on 2026-07-28.**
Distribution, the deterministic layers, versions and identity IDs, the reference
corpora, the rule that the engine does not go backward, the handling of PNG, and
what each version changed are canonical there.

## 16. Licensing

The intended license direction is:

- core DDL specification: permissive license such as CC0 or MIT
- reference implementation: MIT or Apache-2.0
- Saijiki vocabulary data: CC BY or CC BY-SA, if community contribution begins

The language should remain reusable by other implementations while preserving
the reference implementation as one concrete path.

---

## 17. Open Items

**This specification does not carry a list of open items.** They live here instead:

- **what is still to be decided, and what remains** — the development issue ledger holds it (kept outside Git, so it is not part of the published specification)
- **what was done, and why** — the [changelog](CHANGELOG.md)
- **what is implemented, and how far** — the [implementation status](docs/spec/implementation-status.md)
- **how the rendering layer changed from version to version** — the [version history](docs/spec/render-engine-history.md)

Until 2026-08-02 the Japanese specification carried the list itself. Resolved entries had grown to
more than half the section, and the unresolved ones were tracked in two places at once. **The
changelog keeps the record and the ledger keeps the tracking**; this section names where they are.

Operational details specific to the author's local server are kept out of the published
specification and collected in `AGENTS.md` or `no-git-sync/`, both outside Git. Ordinary
development syncs from the Mac with rsync and restarts the systemd services; Docker Compose is
used to verify the production configuration at milestones such as a release.

---

## 18. JSON Score

JSON Score is the machine-readable score produced by Stage 2.  It is not the
final work; it is the structure that the renderer performs.

Important score concepts:

- `canvas`: selected canvas aspect identifier, such as `square` or `golden`
- `instructions`: ordered drawing instructions
- primitive fields: line, circle, ellipse, triangle, square, polygon, arc, cloudform, and related process data
- `weight`: material / tool quality
- `variation`: visible wobble, blur, tremble, or motion behavior
- `arrangement`: count, distribution, paths, grouping, density, fade, and color cycles
- `rotation`: shape-level or group-level orientation
- `color_hint`: optional hint used when resolving catalog colors, and the descriptive markers the renderer reads as the character of a drawing
- `note`: optional machine-written processing annotation. It never reaches the drawing: it is outside the performance seed allowlist, and Stage 2 is instructed never to emit it. Coerce and the API record their diagnostics here so that a diagnostic can no longer be mistaken for a color description. It is declared second, because an optional field's fill rate rises toward the tail of the declaration order
- `at.region`: optional normalized placement region `[x0,y0,x1,y1]` resolved by the renderer seed
- `relation`: optional observable relation to the previous instruction: `along`, `not_touching`, `cutting`, `between`, or `touching`; a touching relation pins both endpoints

A count the description states outright outranks any later reading of it. Below
the threshold (240 by default) the count is literal: the requested value is used
unchanged. At the threshold and above it is represented by a count of 80-120 plus
`arrangement.density`, `cluster_count`, `fade`, and `preserve_space`, so that
negative space remains part of the composition. The threshold matches
`max_expanded_per_instruction`; raising it alone to 300 would leave 241-299
defined as literal and yet cut at 240, so normalization forces them into
agreement. **A number the description states is drawn as stated up to the
threshold of its configuration: at the defaults, two hundred thirty-three strokes
are two hundred thirty-three. The threshold is recorded on the work** (v2.10.0).

The quiet-density governor, which thins repetition for still, membranous, or
remembered scenes, does not apply to a group whose count was stated: quiet is a
reading of the scene, and a stated number is not a reading. When the literal
groups together exceed `max_expanded_primitives` (400 by default), the largest is
represented first and the budget is rechecked before the next one gives way, so
the small groups a reader could have counted stay literal.

The scene-tone rule currently chooses from the abstract colors alone:

- spring, flowers, buds, and warm light lean toward red / green / white
- water, night, moon, rain, mist, and cold air lean toward blue / white / gray
- forest, leaves, grass, moss, and fragrance lean toward green / white / gray

Nuance that cannot be represented by the six abstract colors is retained in
`color_hint` for catalog-based rendering.

Relations are sequential. `along`, `not_touching`, `cutting`, and `touching` refer to the immediately previous instruction; `between` refers to the previous two. There are no arbitrary ids, forward references, or repair governors for relations. Invalid relations are dropped by validation or coercion with a recorded warning, and the instruction is rendered normally without the relation. The coerce layer may remove invalid relations but must not add new ones. JSON Score `relation` is reserved for explicit previous-object phrases in normalized DDL: `前の線に沿って` / `along the previous line`, `前の形に触れない` / `not touching the previous shape`, `前の線を切る` / `cutting the previous line`, `前の二つの間に` / `between the previous two`, and the explicit contact phrases `前の線に触れる` / `touching the previous line` or `前の弧に両端で触れる` / `touching the previous arc at both ends`. Touching is never added spontaneously. Natural-language proximity, rhythm, ahead/behind, near, and far are represented with position, path, rotation, and spacing instead of relation.

An instruction that carries both a region (`at`) and a relation (such as plugin-member double arcs) is placed by its region first and then resolved by its relation (v1.94); for touching, the previous instruction’s endpoints decide the final position, so the region acts as chain-start information. Unresolvable relations discovered only at performance time (degenerate geometry, grid layouts, endpointless priors) are likewise dropped with a recorded warning.

For `touching`, both the current and previous instruction must be a line or arc. The renderer takes the previous instruction’s performed endpoints and pins the current endpoints to them. For an arc with chord length `c` and signed performed sagitta `b`, it reconstructs the minor arc with `r=c²/(8|b|)+|b|/2`; its center lies opposite the bulge, and a previous arc makes the new arc bulge to the opposite side by default. Minor-arc winding uses the same shared convention as SVG arc rendering. Sway and stroke performance keep both endpoints fixed and act only on the interior. Closed forms and endpointless targets are rejected drop-only with a recorded warning. Degenerate performed geometry also drops the relation at render time; no coordinate repair or governor is introduced.

Endpoint, tangent, and sagitta verification is performed in canvas coordinates after composing every drawing transform, including rotations on ancestor groups.

This fifth relation trades the former uniform family of loose distance constraints for one exact endpoint constraint. In return, it can write closed organic contours such as a two-arc leaf without freezing performed coordinates into the Score. The deferred `continuing` candidate remains outside this version; it is reconsidered only after cloudform surface/ground expression improves.

The system treats the DB history record as the source of truth.  SVG, JSON
files, PNG files, and other artifacts are derived outputs.

---

## 19. Canvas Model

Coordinates remain normalized from `0.0` to `1.0`. Canvas aspect changes do not
change DDL coordinates. **A mark's extents (`size`) become pixels through the short edge on both axes, so the shape the description
stated is kept on any aspect** (the same rule the circle and arc radius already used; widened to every form
with a `size` in v2.13.6 / render engine 30). **The layer that arranges marks follows the same rule** -- a `radial` ring's radius and an `at.region`'s extent
become pixels through the short edge, so the arrangement the description stated is kept on any aspect
(v2.13.8 / render engine 31). **Placement, and a region's centre, still scale with width and height** -- the aspect
decides where a mark sits, not what shape it or its arrangement is. `arrangement.margin` remains a fraction of
each axis: spreading to the frame is what `scatter`, `horizontal` and `vertical` mean. Changing the aspect clears the rendered display and shows
a placeholder for the new aspect, but retains the displayed work as lineage context.
The next saved work is recorded as its child with `canvas_aspect_change`.

The built-in `canvas-aspect` plugin currently supports:

| Category | ID | Ratio | Purpose |
| --- | --- | --- | --- |
| Basic | `square` | 1:1 | default ordered canvas |
| Standard | `golden` | 1.618:1 | golden-ratio rectangle |
| Modern | `a4` | 1:1.414 | root rectangle / print standard |
| Modern | `b4` | 1:1.414 | root rectangle / print standard |
| Classic JP | `pillar` | 1:5 | Japanese pillar-picture format |
| Ukiyoe | `oban` | 2:3 | ukiyo-e oban proportion |
| Cinema | `wide` | 2.35:1 | cinematic panorama |
| Classic JP | `byobu` | 2.2:1 | Japanese folding screen format based on one half of a six-panel pair |
| Mobile | `vertical` | 9:16 | smartphone vertical format |

The selected aspect is stored per user in plugin storage and passed to
`/api/paint`, `/api/compose`, and history saving.  It is also written into
`Score.canvas`, so history and JSON display show which aspect produced a work.

The renderer uses the selected aspect to determine SVG `width`, `height`, and
`viewBox`.  Circle and arc radii are based on the shorter side to avoid
accidental stretching.

---

## 20. Modes

### Single Drawing

The user writes one instruction and runs the full pipeline.  The resulting DDL
can be edited directly.  Replaying from DDL skips Stage 1 and calls Stage 2 /
renderer again.

The normalized DDL appears as an interpretation box under the single drawing
input.  The box supports two editing paths:

- direct inline editing in the highlighted interpretation box
- the `Saijiki` toggle, placed on the canvas toolbar since v1.98, opens the
  side drawer as a browse-only vocabulary reference: clicking a word chip
  shows its preview instead of inserting it
- the `DDL editing` button opens a larger dialog with line numbers, a
  two-column Saijiki vocabulary panel, and a short DDL syntax guide; since
  v1.98 word insertion happens only through this dialog's inline Saijiki,
  which also lists loaded plugin vocabulary
- the `auto repair` checkbox controls whether the server applies deterministic
  JSON Score repair after Stage 2. It is enabled by default. When disabled,
  Stage 2 output is rendered without the broader `coerce_score()` repair pass,
  while hard contract guards may still remove instructions that violate the
  requested primitive/color contract.

The same `Draw from DDL` action is also available below the interpretation box
for quick replay without opening the dialog.  The single drawing flow also
includes v1.70 post-selection controls: a candidate grid for multiple
render/composition/interpretation variants, optional inclusion of an
interpretation candidate, multi-select saving, and an explicit `another
interpretation` action that shows the normalized-DDL diff.  Candidate metadata
shows the render, vary, and interpretation seeds where applicable.  The dialog itself does not start
drawing, so drawing actions remain concentrated in the main single-drawing
panel.

If the user edits DDL directly and then presses the normal `draw` button, inku
warns that the DDL edit will be lost.  The choices are `cancel`, `OK`, and
`draw from DDL`.  `OK` reruns Stage 1 from the natural-language prompt, while
`draw from DDL` preserves the edited DDL and runs Stage 2 / rendering only.
The natural-language prompt is not reinterpreted by `Draw from DDL`.

The drawing tab also exposes two explicit regeneration actions. **Another
performance** keeps the same Score and asks only the renderer for a new
performance seed. **Another composition** keeps the user-facing text as the
identity of the work but increments a `composition_seed` for Stage 1.5 selection, so
composition family, focus, and technique candidates can change without making
the default path nondeterministic. The same text plus the same `composition_seed` and
`render_seed` is reproducible from metadata.

Since v1.98 single drawing calls `POST /api/paint/stream` (NDJSON): a `stage1`
event is emitted as soon as interpretation completes (normalized DDL, models
used, token counts, elapsed time, fallback flag) so the UI can show the
interpretation while Stage 2 and rendering continue, and the final `done` event
carries the same `PaintResponse` as before. `POST /api/paint` remains a wrapper
over the same logic with an unchanged response shape, so the CLI and Android
need no changes.

DDL replay shows elapsed time, token information, a stop button, and the
progress mascot.  Stopping replay aborts the active `/api/compose` request.
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

The batch panel accepts multiple instruction lines.  During execution, the
active line is highlighted and the current DDL interpretation is displayed
read-only.  Batch execution keeps failure reports until the next batch run, and
stores batch prompt history per user.

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
automatic choice: they draw with the work's own catalog**.

**The catalog selection is stored per user on the server**
(`model_settings.color_catalog_id`).  Drawing needs a session, so a browser-wide
value would only ever be another user's selection.  Only a catalog that still
exists, or `auto`, can be stored; a retired id falls back to the default.

Clicking outside the dialog confirms the current selection exactly like the
save/confirm action. The cancel button still restores the selection snapshot from
when the dialog was opened.

### Demo Drawing

Demo mode repeatedly generates an instruction from a seed phrase, renders it,
waits for the configured interval, and repeats.  Demo settings are stored per
user.  Demo results are not saved by default; the user can explicitly save a
current render to history.

Demo draws with the same selection.  The status bar reflects the catalog reported
by the render result, not only the current catalog selection.  **Until v2.9.39 the
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
- normalized DDL
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

The DB settings tab also shows the current DB file size when the backend is a
SQLite file database.  Admin users can configure DB replica backups with an
interval in days, a time of day, and a maximum number of automatic generations.
The defaults are seven days, 03:00, and four generations.  Manual backups can be
created immediately and are stored separately from the automatic generation
limit.  File-replica backups are reported as unavailable for non-SQLite DB
backends.

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
or under `no-git-sync/`.

The application is developed on macOS and verified on the deployment host after
rsync-based sync and systemd service restart. Production Docker Compose images
are verified at milestones such as release candidates rather than rebuilt for
every ordinary source change. Git is used for source history, not as a file
exchange mechanism with the local server.

**The record of each engine version moved to the [render engine history](docs/spec/render-engine-history.md) on 2026-07-28.**
Release distribution, deterministic layers, versions and identity IDs, the reference corpus, the engine not going backwards, how a PNG is treated, and what each version changed are canonical there.

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
├── manual/ja|en/cli-reference-for-ai.md  # the CLI reference
└── android/                           # the native Android implementation (canonical: android/ANDROID_SPEC.md)
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

`ddl/` is the early Python PoC that the complementary Android axis was built
from; the web version has moved to `server/`.

---

## Accounting for Refinement

inku treats convergence caused by accumulated quality repairs as part of its implementation history. Countermeasures belong only in human-facing mirrors, explicit user actions, and development practice; they must not become automatic control in the default generation path.

- Every minor release records at least one branch, word, component, or rule it removed, or explicitly says that nothing could be removed. This is an account, not a deletion KPI.
- Every release records what it made less likely, so the cost of refinement remains visible.
- Release review places the new JP30/EN30 contact sheets beside the preceding two releases and records any newly increased repetition together with the motif-census delta. Finding no increase is also recorded.
- Similarity features, motif frequency, vision observations, and coerce firing rates are audit mirrors. They never automatically control default-generation branches or suppression, acceptance gates, or optimization objectives. As an explicit exception, a user-started finite AI Vision autonomous-refinement run may feed non-scoring observational advice into the next generation. It never ranks, accepts, rejects, or discards a generation; every generation remains in lineage and the human makes the final decision.

### v1.80: the mirror, the wind, the earth, the blade

v1.80 adds a deterministic Score-derived composition mirror shared by server and CLI, three unranked nearby history thumbnails, similarity ordering for contact sheets, a mechanical motif census over artifact sets or the current user's history, explicit renderer-only `seed_text`, a private unread-word ledger with `unread-words` and admin-only `unread-words --all` reporting, per-branch coerce observation, and an on-demand NIM vision review. Similarity never implies lineage: lineage remains the record of explicit creative causation. When drawing continues from an unsaved refinement candidate, that candidate is automatically materialized as the direct `lineage_only` ancestor without entering regular history; it can later be promoted explicitly from the lineage view.

The Canvas UI separates work facts from pending generation settings. The top row labels the models, color catalog, canvas, and creation time actually used by the displayed work as `Displayed`; the bottom status bar labels the currently selected models, color catalog, and canvas for the next run as `Next generation`. When Stage 1 and Stage 2 use the same model, the UI combines them as `Interpretation / performance`. The provenance inspector (`Provenance`) has `Details`, `Prompts`, and `JSON` views. Details contains the two stage models, color catalog, canvas, render/layout/interpretation seeds, render and description hashes, render engine and version, build, elapsed time, and input/output token counts. In the Prompts view, the initial heights of Stage 1 user input and Stage 2 system prompt are reduced by half without changing their content; Stage 1 system prompt and Stage 2 user input retain their existing heights.

### The v1.80 accounting record

Refinement account for v1.80: the proposed automatic statistics-to-generation “unexplored” path was removed from this release, and vision review remains manual rather than release-automatic. Existing default-path repair branches could not yet be removed. The release makes unnoticed self-repetition, unrecorded external performance seeds, and privacy-losing unread-word aggregation less likely; it deliberately does not make dissimilarity a goal.

### v1.81 Lineage-grouped history

History Manager offers `Timeline` and `By lineage` as an independent display choice alongside the thumbnail/list layout choice, and stores the display preference in the browser. The bottom history strip remains chronological because it serves rapid previous/next navigation. Each strip item shows its one-based generation depth, derived from saved parent edges, and its lineage-node state instead of render elapsed time. Selecting an item while the Lineage tab is open preserves that tab, reloads the selected work as the focus node, and centers it.

A history group is based only on persisted lineage nodes and edges, never similarity, identical text, or timestamps. Every lineage node has an immutable `root_node_id`: a root points to itself and a child inherits its parent's root. Existing nodes are backfilled by following persisted edges toward their ancestor. Groups are ordered by the latest matching regular-history work and paginated by group, so one lineage is never split merely by a page boundary in regular history.

Each group header shows a representative work, the regular-history work count under the current filter, starred count, and latest save time. Members are fetched only when expanded and retain the existing display, star, replay, individual/group selection, and trash operations. Search, starred-only, and active/trash filters include only matching works in group summaries and expanded members. `lineage_only` and tombstones remain outside regular history and its counts. An independent work forms a one-work lineage, and no root, work, or count may cross user boundaries.

Build 557 establishes the v1.81 foundation with lineage-root migration/backfill, lineage group/member APIs, and the Timeline/By lineage History Manager UI with lazy expansion.

### v1.82 Automatic instruction language and language comparison

The writing tab no longer asks the author to choose an instruction language. Normal generation always requests automatic detection from the entered text; when the text has no Japanese or Latin language signal, the UI display language is the fallback. Japanese UI with English writing, and English UI with Japanese writing, remain supported.

Normal Stage 1 and Stage 2 generation is LLM processing, while image-reading operations have a separate per-user Vision model setting. The model dialog separates Shared Stage 1/2, Stage 1, Stage 2, and Vision selection, and admin model settings identify whether each model is available for LLM, Vision, or both. `GET /api/models` retains the LLM `catalog` for older CLI clients and also returns `llm_catalog` and `vision_catalog`. The colophon has its own per-user model choice, initially derived from the general Vision default and restored the next time it opens. An explicit API or CLI model remains authoritative for compatibility.

Each model may carry LLM/Vision purposes, per-purpose five-level recommendations (split into LLM and Vision values in v1.98; the old single value is read for compatibility only), Japanese and English evaluation comments, and a measured speed class and label. **Recommendations are split by stage as well as by purpose since v2.9.10**: a model measured per stage carries a Stage 1 and a Stage 2 value, which narrow the per-purpose value rather than replacing it. A model with no stage value reads the per-purpose value for both stages, so nothing changes for a model measured end to end. Administrators can edit this metadata, and both admin and user model selection expose it on hover. **Hover shows two recommendation lines for a model measured per stage and one line for a model measured end to end (v2.9.10)** — duplicating an end-to-end value across two lines would imply a measurement that was never made. Vision is not split by stage. Speed values are observations from a particular measurement run, not a permanent performance guarantee or an acceptance gate for generation quality. **A provider may declare that its speed values are shown in developer mode only (v2.9.5, v2.9.8)**, which applies to providers whose numbers depend on one machine's environment and are therefore not something a release can promise. The hiding happens in the display layer alone; it changes neither what is stored nor which model is called. Beyond normal generation, Batch has no image input, so it shows the current Stage 1/2 models and opens a model dialog without Vision. Demo separately selects its instruction-generation LLM and rendering Stage 1/2 models, while the colophon selects from Vision cards grouped by provider. These cards expose the same evaluation metadata on hover using a theme-independent high-contrast tooltip.

Since v1.98 every model list is ordered with end-of-life (EOL) models last, then by the recommendation for the purpose and stage at hand in descending order (the stage since v2.9.10), with ties broken by label. A shared Stage 1/2 selection uses the lower of the two stage values. EOL models stay in the catalog marked as retired and unselectable rather than being removed, so model references in saved works remain resolvable. **There are two reasons a model can be unselectable: it has reached end of life, or it requires a paid plan from the provider (v2.9.8).** The second mark does not appear in the provider's own listing — such a model is listed and then refuses when called — so **a re-fetch does not clear it**, whereas an EOL mark is cleared because the listing carries it. The difference is where the mark comes from: the listing, or a measurement. The server does not reject requests naming an EOL model; the provider's failure is classified and explained by kind (model gone, authentication, rate limit, other).

Refine adds Language comparison beside Adjust and Model comparison. It uses the same three comparison modes: shared Stage 1/2 language, fixed Stage 1 with Stage 2 comparison, and Stage 1 comparison with fixed Stage 2. Japanese and English can be assigned per stage only for an explicit comparison run, without changing automatic detection for normal generation. The target's identical language combination is excluded, results show the Stage 1/2 language pair and normalized DDL, and an adopted result records the pair in lineage metadata. Changing the target clears results and aborts an in-flight language comparison.

Build 558 implements this boundary and the UI-language fallback. Adopted comparisons use a dedicated `language_variation` lineage edge.

Build 559 adds the effective Stage 1 and Stage 2 languages to Provenance / Details. Normal works show their shared resolved language, while adopted language comparisons show the per-stage values recorded in lineage metadata.

Build 560 aligns Provenance / JSON with Details by adding per-stage instruction languages, render/layout/interpretation seeds, description hash, elapsed time, input/output token counts, and derivation kind/metadata at the top level. The JSON Score, API and database schemas, and canonical render-hash payload remain unchanged.

## Autonomous Refinement Methods

Lineage's autonomous refinement is a bounded run of 1–10 generations whose final judgment remains human. Before starting, the user chooses one method:

- `Random automatic refinement` randomly chooses each generation's variation kind from the enabled reading, color-catalog, layout, touch, and variation elements. It does not use Vision. Because the direction text only reaches the drawing text of reading generations, the random-method UI states that condition explicitly.
- `AI Vision automatic refinement` lets the user explicitly choose a Vision model from provider-grouped cards. The server rasterizes each saved generation to PNG and sends it with the original instruction, user direction, and allowed refinement kinds. Vision returns visible observations, one direction to try next, and one allowed variation kind; that advice becomes input to the next generation.

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
- The colophon is available only through the explicit Lineage action or `inku-cli colophon`; `--dry-run` generates without saving. It never affects dh1, rh2, generation, variation, refinement selection, acceptance, quality functions, or branch recommendation.

### The v1.88 refinement account

v1.88 adds no automatic repair or generation branch. Its refinement accounting deliberately limits the new AI reading to a disconnected mirror, making teleological “best branch” narratives less likely to become application behavior.

---

## Changelog

Chronological public release notes are maintained in [CHANGELOG.md](CHANGELOG.md). The more detailed Japanese history is in [CHANGELOG.ja.md](CHANGELOG.ja.md), and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the short developer entry point.
