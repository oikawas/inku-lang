# Creating Images

This guide covers work creation with the Web UI and CLI in inku v2.13.30 (Web Build 917). A description passes through sketching from life, interpretation, deterministic expansion, structuring, and performance.

```text
description -> Sketch from life (Stage 0.5) -> interpretation (Stage 1) -> instructions (normalized DDL)
            -> plugin expansion -> expansion and variation (Stage 1.5) -> JSON Score (Stage 2) -> SVG
```

The description is the work's score; the SVG is one performance. The same description may produce a different work when its models, sketch, variation, composition seed, or render seed change.

The vocabulary used in the UI is as follows.

| Term | Meaning |
|---|---|
| description | The poetic input the author writes. The topmost layer of a work |
| Sketch from life | The Stage 0.5 act of restating the description as prose in the language of things |
| interpretation | The Stage 1 act of reading the description, or the sketch, into instructions |
| instructions (normalized DDL) | The executable specification interpretation produces |
| score (JSON Score) | The structured intermediate form of the instructions, stored deterministically |
| performance (SVG) | The one-time result of performing the score |

## 1. Sign In and Choose the Display Language

1. Open the inku Web UI.
2. Enter your user name and password.
3. Press `Sign in`.

The left app rail provides settings, profile, theme, UI display language, the tooltip toggle, and sign-out controls. The rail can be expanded or collapsed.

The UI language and the description language are separate. Ordinary painting detects the description language from the entered text, including English text in the Japanese UI and Japanese text in the English UI. Only text with no usable language signal falls back to the UI language. You may also state it with `Description language`: `Auto`, `Japanese`, or `English`.

`UI mode`, under `Other` in the settings, chooses how much of the screen is shown.

| UI mode | Contents |
|---|---|
| Simple UI | Shows the essential items and the history |
| Full UI | Shows every available item |
| Custom UI | Adds the items you choose to the essential ones |

The UI mode can also be switched from the icon on the left of the rail. **The number of dark bars is the mode that is on**: one for simple, two for custom, three for full. The menu is listed in the same order (simple, custom, full).

The user menu, settings, single description and painting, the canvas and the history are always visible. **The history is always there so that a work can be looked at again and taken out as one sheet with `Share card`** (the card has two doors, one inside `Export` at the top right of the canvas and one in the history panel, and both belong to the history side; in the simple UI the first becomes a card-only button -- v2.13.29). Custom UI can add seven groups: batch and demo; model, color, sketch, and canvas settings; view and edit instructions; timing, tokens, and provenance; refinement, comparison, export, and work actions; history and work navigation; theme, language, and work information.

This manual assumes Full UI. Under Simple UI some of the operations described here are not on screen.

## 2. Paint the First Work

1. Open the `Describe` tab.
2. Write a short sentence in the description area.
3. If needed, set `Model`, `Color catalog`, `Sketch from life`, `Wild`, and `Canvas`.
4. Press `Paint`.
5. Confirm that the performance appears in the `Work` tab and is saved to history.

The first work is the source work. The refinement action `Another performance` is never applied to this first painting.

Examples:

```text
The moon rises beyond the mountain
```

```text
A blue crayon line undulates slowly
```

```text
Place three small red circles in the upper right of a white margin
```

Below the input field a character count, for Japanese, or a word count, for English, is shown against a tanka guide. It is a guide, not a limit.

## 3. Write a Description

For stable results, write observable physical instructions one sentence at a time.

```text
color + size + shape + count + place + motion
```

Example:

```text
Fill the background with white.
Draw three thin blue lines from lower left to upper right.
Place three small red circles in the upper right.
```

| Kind | Examples |
|---|---|
| Shape | circle, ellipse, triangle, square, line, arc |
| Color | white, black, blue, red, green, gray, yellow, orange, purple |
| Place | top, bottom, center, left edge, right edge, upper edge, lower edge, corner |
| Motion | place, arrange, fill, scatter, draw, tile |
| Touch | pencil, pen, rotring, crayon, chalk, fine brush, broad brush, burin, drypoint |
| Continuity | solid, dashed, dotted, dash-dot |
| Surfaces | empty, flat, pale ink wash, grain, stipple, hatch, crosshatch, bleeding, aquatint, dense, faint |
| Grounds | paper, washi, ink-wash ground, charcoal ground, canvas, drawing paper, mezzotint |
| Sway | fine, broad, slow, fast, waver, undulate, tremble, bleed |

No layer adds what the description does not ask for. What is written is performed as far as it can be.

A written number is drawn as written, without having to be emphasised as "three lines only". It takes effect when the sentence points to a single group. If several groups share the same shape, colour and weight so that the sentence does not settle on one of them, the count is left alone. How far the number reaches is set by the boundary in `Stated counts` in [Server configuration](server-configuration.md) — up to 239 by default; above that the work is shown as a crowd. When the number asked for would cross the limit for one work or for one group, it is left as it is rather than drawn part of the way. **Numbers are read the same way in Japanese and in English**: a `12` written in an English description is a count even where the kanji of a plugin word stands beside it. When the phrase naming a plugin states no number, the sentence is read instead (a number in the phrase wins). **Numbers that name a direction, a kind, a degree, a row or a column are not counts, and neither are decimals** (the four of `four directions`, the thirty of `30 degrees`, `0.11`).

A written size is treated the same way. A sentence that states a size, such as "a small circle", is drawn at that size. It takes effect when the clause stating the size settles on one group; if several clauses share the same shape so that it is not settled, the size is left alone. Where the clause states the value itself, such as `radius 0.02`, that value is used. A description that states no size is drawn at the default size, as before.

Leading serial numbers and bracketed annotations belong to the writer, not to the drawing. If nothing but numbers and annotations remains, painting reports that there is nothing left to draw.

## 4. Sketch from Life (Stage 0.5)

`Sketch from life` restates the description as prose in the language of things before interpretation reads it. Choose it from `Sketch from life` in the button row of the describe tab.

| Grain | Contents |
|---|---|
| Fine | Cut fine: one fact per short sentence, so more instructions come out. This is the Web UI default |
| Coarse | Cut coarse: related facts bundled into longer sentences, each read more deeply |
| Off | Skip the layer and send the description straight to interpretation. Not recommended |

Fine and coarse do not change how much is said, only how big the pieces are. Cut fine, the number of instructions grows; cut coarse, each instruction carries more.

The sketch reaches three consumers in place of the description: interpretation, the decision whether plugin expansion fires, and Stage 1.5. After painting, the result appears under `Sketch from life (Stage 0.5)` on the left and can be edited there. An edited sketch reaches interpretation as written.

If the layer does not answer, the description goes to interpretation unchanged and the work records that. A work painted with the layer off carries the same kind of record.

`Sketch from life (Stage 0.5)` and `Instructions (normalized DDL)` each fold from the triangle in their heading. Folded, the heading, the rule, and `Edit` stay visible, and pressing `Edit` while folded opens the section. **The fold is saved on the account, not in the browser** — another machine opens it the same way. The sketch starts open and the instructions start folded.

## 5. Consult the Saijiki

The `Saijiki` is inku's vocabulary dictionary.

1. After the first painting, press `Saijiki` on the `Instructions (normalized DDL)` row.
2. Point at or click a word to see how it acts on the performance, with examples.
3. Choose a word to insert it at the cursor position in the instructions.

The eleven words under `Surface` each carry a small drawing of how the face is, and a note on what it does to the performance. Every drawing shares the same outline; only what is inside it changes.

The Saijiki is not autocompletion. Consult it when needed; it does not narrow a description to the existing vocabulary on its own. It is for reading, and pressing it does not start a painting.

Plugin words appear in the same row and wear the same face as built-in ones. The explanation is not under the word but in the preview above it, which carries four parts: name, effect, example, and picture. The picture appears only when the plugin document ships one; a word without one gets the same fallback picture a built-in word gets.

## 6. Read and Edit the Instructions

After painting, `Instructions (normalized DDL)` on the left shows how Stage 1 read the input.

- description: the words a human wrote
- Sketch from life (Stage 0.5): the description restated as prose in the language of things
- instructions (normalized DDL): drawing instructions arranged into the core vocabulary
- Expanded (Stage 2 input): the DDL Stage 2 actually received, after plugin expansion and the expansion layer filled in
- JSON Score: the machine-readable score Stage 2 writes
- Work: the SVG the renderer performs

`Auto-repair` enables or disables the deterministic repairs for invisible colors, overcrowding, contract violations, and the like. The repairs are: making colors that merge with the background visible; damping overcrowded lines, grains, and fills; filling in missing shape parameters; tidying duplicate instructions; removing invalid contact and positional relations; supplying colors and shapes the DDL left short; and supplying the composition's fulcrum, motion, and rhythm.

There are two entrances to the instructions.

| Action | Contents |
|---|---|
| New instructions | Write instructions directly, without a description, and paint them as an independent work |
| Edit instructions | Edit the instructions of the displayed work and repaint it as that work's child |

`Draw from instructions` sends the displayed instructions to Stage 2 unchanged. Stage 1 does not run, so the interpretation does not change.

### A plugin name that does not exist shows up while you type

A `namespace.word` such as `Nature.青葉` is marked in the plugin color only when that qualified name is registered on this server. **A name that is not registered takes a different color, and the reason is listed under the editor.**

- **If the word is a firing word, the editor says how to drop the prefix.** `Nature.菖蒲` reads `Remove "Nature." and it fires as "下草"`, because `菖蒲` is one of the words that fire `Nature.下草` while the qualified name itself does not exist.
- **If it is not a firing word either**, the editor says `This name is not registered`.
- **The color means caution, not error.** Plugins can be added later, so a name missing today may be valid tomorrow.
- **⚠ A qualified name that does not exist costs the whole sentence.** When the expansion layer strips `namespace.`, it removes that sentence with a warning. **The same warning stays under the work after it is painted.**
- **A word without a dot is unchanged.** Written as plain `菖蒲` it stays an ordinary word and keeps its color.

## 7. Choose Model, Color Catalog, Sketch, Wild, and Canvas

The button row on the describe tab applies to the next painting. It is identical across the three input tabs: describe, batch, and demo.

| Control | Contents |
|---|---|
| Model | The inference models for Stage 1, interpretation, and Stage 2, structuring |
| Color catalog | The catalog that maps abstract color names such as `red`, `blue`, and `gray` onto actual colors |
| Sketch from life | The grain for Stage 0.5, described in §4 |
| Wild | Removes the stroke limit |
| Canvas | The aspect ratio |

One model can serve both stages, or each stage can have its own. Models measured per stage are ordered by the lower of the two stages. The model for Vision, which reads images, is chosen separately.

The color catalog list includes `From the description`. Choose it and the server reads each description and picks a catalog for every painting. The choice is saved per user.

A work records the colors it was drawn in on its own row. **Redrawing an older work therefore draws it in those colors, not in today's definition of its catalog.** It still draws if the catalog has since been renamed, and it still draws if the catalog has been retired. The catalog name in the status area carries a note in those cases: `Retired` when the catalog is gone, and `No record of its colors` for an older work that has no recorded colors — that one is drawn from the current definition.

`Wild` off is the predictable standard; on, the strokes break, curl, and overlap freely. It applies to the whole work, is recorded on it, and replays.

There are nine canvases.

| ID | Ratio | Origin |
|---|---|---|
| Square | 1:1 | The default format, a symbol of complete order |
| Golden | 1.618:1 | The traditional Western proportion of beauty |
| A4 | 1:1.414 | The root rectangle familiar through print standards |
| B4 | 1:1.414 | A root rectangle with a physical print sensibility |
| Pillar | 1:5 | The Japanese pillar-picture format, with tall negative space |
| Oban | 2:3 | The standard ukiyo-e oban woodblock proportion |
| Wide | 2.35:1 | Cinemascope panorama for scenes and landscapes |
| Byobu | 2.2:1 | The Japanese folding screen, based on one half of a six-panel pair |
| Vertical | 9:16 | The contemporary full-screen mobile format |

Coordinates stay normalized to 0.0–1.0 whatever the canvas. **A mark's size is measured against the canvas's short edge, so the same description draws the same shape on any ratio** (an ellipse written wide stays wide on the pillar canvas). **The shape an arrangement makes follows the same measure** -- a ring laid out radially is drawn as round on every ratio, and a region stated as a square is treated as a square. **So does the shape of one clump when marks are scattered in clusters, and the swing of a path (wave, diagonal, top to bottom).** Placement, a region's centre, and a cluster's centre still spread with the ratio, and **so does how far along the paper a path travels**. The canvas ratio is a system plugin, so if an administrator disables it only the square remains.

**From v2.13.14 the canvas you choose also reaches the stage that builds the composition (Stage 2).** The composition is told which paper it is for, so the same description is laid out differently on a pillar than on a folding screen. **Only size and placement move with the paper** -- a number the description states is drawn as stated, and a size the description states is not changed to suit the paper.

The settings of the displayed work and the settings for the next painting are separate. Distinguish the `Displayed` strip at the top of the work tab from the button row on the describe tab.

## 8. Refine

In the refinement area of the work tab, choose exactly one element to change at a time.

| Element | What changes | Cost |
|---|---|---|
| Another composition | Keeps the reading; Stage 2 rebuilds coordinates, sizes, and compositional balance | Medium (Stage 2 LLM and API) |
| Another reading | Reads again from Stage 1 and regenerates the instructions, composition, and performance | Slow (LLM and API) |
| Another catalog | Keeps the DDL, JSON Score, composition, and performance, and changes only the color catalog | Very fast (no LLM) |
| Variation | Shakes Stage 1.5 as a whole. The app decides which axes move | Medium |
| Another performance | Derives only the renderer's performance seed from your words, changing line quality, weight sway, and bleed | Very fast (no LLM) |

You may choose `Make one option` or `Make four options`. `Another performance` is deterministic, the same words giving the same touch seed, so it makes one option only. The words do not act on the work's meaning, reading, DDL, JSON Score, or composition.

### 8.1 Variation

`Variation` shakes Stage 1.5 and lets the app choose. Pick one of three amplitudes.

| Amplitude | Axes that move |
|---|---|
| Subtle | Moves one axis out of type swap and adopted count. Focus, color, and composition stay |
| Moderate | Opens touch material, focus, and primary and contrast color as well, moving one or two axes. The composition family and the type family stay |
| Sweeping | Opens the composition family and the type family as well, moving two to four axes. The skeleton of the picture moves |

The axes that actually moved are shown afterwards under `Axes moved`. The axes are type swap, type family, adopted count, touch material, focus, primary and contrast color, and composition family.

### 8.2 Save Options

Options are unsaved. Select the ones to adopt and save them to history. Saving and starring are separate actions. You may record why you chose an option.

Switching the refinement target discards unsaved options belonging to that work. When you continue from an unsaved option, only the direct option is saved to the lineage as an intermediate work, and it is not shown in ordinary history.

## 9. Autonomous Refinement

From the lineage tab the application can build generations on its own.

| Mode | Contents |
|---|---|
| Random autonomous refinement | Builds generations at random from the chosen elements |
| Autonomous refinement with Vision | Observes the picture and passes a direction to try to each generation |

You choose the number of generations and which refinement elements to use. A direction you write reaches every generation under Vision; under random autonomous refinement it applies only to `Another reading` generations, and not at all if `Another reading` is removed.

`Refine manually` lets you specify the kind of refinement, an added Saijiki word or direction, and the color catalog, while looking at the parent work's composition in DDL.

## 10. Compare Models

The same description is painted under different Stage 1 and Stage 2 model configurations, and the works and instructions are compared. There are three comparison modes.

- `Shared Stage 1/2`
- `Fixed Stage 1 + compare Stage 2`
- `Compare Stage 1 + fixed Stage 2`

At most four inference models can be compared. The model configuration of the compared work cannot be selected. Models that return an error are dropped from the comparison and their count is reported.

Comparison results are not saved automatically. Use `Adopt` to keep one in history, or star it to save it as a starred history entry.

## 11. Read the Provenance

Open the provenance drawer at the bottom of the work tab to see the record of the selected work. Its tabs are `Details`, `Prompts`, and `JSON`.

`Details` is divided into six sections.

| Section | Main contents |
|---|---|
| Sketch | The sketch record and the paper grain (**the record of the work on screen**, not the setting for the next painting) |
| Interpretation | Stage 1 model, Stage 1 language, requested language, interpretation seed, interpretation fallback |
| Performance | Stage 2 model, Stage 2 language, focus, variation and variation seed, composition seed, render seed, seed text, Wild, the colour words this work was drawn in, the colour catalogue, the canvas and its ratio, and **three rows for how heavy the drawing is** (`SVG size` / `SVG objects` / `SVG points`) |
| Identity | render hash, description hash, render engine, DDL specification, transform layer, prompt digests, Build |
| Origin | generation, derivation, batch run ID and line number, comment, UI language |
| Run | elapsed time, token counts |

Every row carries an explanation. The render seed is "the seed that fixes the sway of the performance; the same seed and the same score give the same picture"; the description hash is "the fingerprint of the description; it binds works that came from the same words".

**The weight of a drawing is printed as three quantities.** `SVG size` is the amount of data, `SVG objects` is how many shapes the SVG holds (containers and notes — svg, defs, title, desc, metadata — are not shapes), and `SVG points` is how many points those shapes are drawn from. **None of the three stands in for the others**: at the same size, few objects with many points is a drawing of fine lines, and many objects with few points is a drawing of many forms.

`Prompts` shows the Stage 1 and Stage 2 system prompts and user input; `JSON` shows the JSON Score. Do not confuse the JSON Score itself with the provenance.

If Stage 1 does not answer in time, returns an empty answer, or fails, a stock set of instructions is performed and the reason is recorded as `Interpretation fallback`.

## 12. Follow the Lineage

The `Lineage` tab shows which explicit action a work was derived from. Performance, composition, reading, variation, model, language, instruction edits, description edits, repaints, canvas changes, and changes of sketch-from-life grain are recorded as parent-child relations.

- Parentage is never inferred from visual similarity, an identical description, or timing alone.
- Intermediate works stay in the lineage as `lineage_only` and do not appear in ordinary history. Promoting one moves it into ordinary history.
- From a lineage card you can promote to ordinary history, comment, star, mark for revision, and move to trash.
- You may also select a work from the lineage and repaint it from its description or instructions.

## 13. Read the Colophon

`Colophon` recites the branch leading to the displayed work as a first-person reader. It reads the generations in order from the origin to the displayed work, recording what changed in each generation and what stayed invariant across all of them.

- It is neither evaluation nor selection. It must not be connected to painting, refinement, or branch choice.
- You choose the reader model. A reading is appended, never edited. It can be deleted, and deletion cannot be undone.
- If the reading strays from the observational vocabulary, a warning is shown.

## 14. Manage History

The history strip at the bottom is for moving quickly back and forth in time. `History management` switches between `Timeline` and `By lineage`.

- Search by description, or by the last four characters of the hash
- Filters for starred only and for revision only. Used together, only works matching both remain
- Switching between ordinary history and trash
- Thumbnail view and list view. The list compares hash, timestamp, model, elapsed time, and color catalog
- Move to trash, restore, and permanent delete, singly or by multiple selection
- Expanding and selecting a whole lineage at once
- Syncing to the displayed work and jumping to the oldest or latest page
- **The words for moving agree everywhere.** On the canvas, the strip and history management alike, left is newer and right is older, and `prev`, `next` and `first` are not used (`← newer` / `older →` / `Latest` / `Oldest`)

`By lineage` groups only on stored lineage nodes and edges. `lineage_only` intermediate works and tombstones are not counted in ordinary history.

The revision mark is a second mark, independent of the star. Use it for works you mean to return to.

`Replay` re-renders from the stored score and seed. If the engine version that painted the work differs from the current one, that fact and a comparison of the two are shown. Old history entries without a render seed cannot be replayed.

## 15. Export Images

Save from `SVG` or `PNG` at the bottom of the work tab.

| Format | Use | Characteristics |
|---|---|---|
| Display | Web display and PNG generation | The stored SVG. Favors visual fidelity and uses filter and clip-path |
| Editable | Illustrator / Affinity | Regenerated from the score. Carries layer structure and stable IDs, and avoids filter and clip-path |
| Compatibility | General SVG interchange | Regenerated from the score. Close to Editable, but favors robustness |
| PNG | Raster image at a chosen resolution | Standard, high resolution (2×), square, square high resolution. More templates can be added in the settings |

`Editable` and `Compat` are drawn again from the Score, and **a redraw uses the performance that was saved** (both the render seed and the composition seed the saved work carries). **The only difference from the stored SVG is how far the drawing engine has moved on** -- inku keeps no past version, so a redraw after the engine advances is never byte-identical.

The download folder can be set in the settings. Without one, files land in the browser's default folder. The folder itself lives only inside that browser, so another browser or another device needs its own choice. If writing is not permitted, the file lands in the browser's default folder and says so.

### 15.1 Contact Sheets

Works selected in history management are laid out on a single PNG.

| Kind | Contents |
|---|---|
| Contact sheet for people | 7×4 works per sheet. The remainder goes to further files |
| Contact sheet for AI | 3×4 works per sheet, 1568px on the long edge, captions numbered only. A companion md holding the numbers, descriptions, DDL, and provenance is saved alongside |

### 15.2 Shareable Card

A work is exported as a single card. The drawing, the headnote, the last four digits of the render seed, and the seal are composed into one sheet. A work with no headnote becomes a card of the drawing alone, and a work with no render seed shows no seed line.

There are two doors.

| Door | What it cards | What one press does |
|---|---|---|
| `Share card` inside `Export`, at the top right of the canvas | the work on the canvas | exports one sheet immediately (v2.13.29) |
| `Share card` in history management | the one checked work | enabled only when exactly one work is checked |

Both follow the same layout and seal settings. A work that has not been saved yet has no card, so the button on the canvas cannot be pressed.

**In the simple UI — and in any custom UI without `refinement, comparison, export, and work actions` — `Export` becomes a card-only button** (v2.13.29). One press exports the card with no menu in between. SVG and PNG belong to that group and are not offered, but the card stays: it is how a work goes to someone else.

| Setting | Choices |
|---|---|
| Layout | Square (1080×1080), portrait (1080×1350) |
| Seal | On (default) or off |

The server composes the card and bakes it with a bundled font, so the characters are the same whatever fonts the viewing machine happens to have. The drawing is nested as SVG rather than pasted as pixels, so the sheet stays vector until the single rasterization at the end. A long headnote shrinks the frame around the drawing, and anything past six lines is cut with `…`.

The same card comes out of the CLI with `inku-cli export-card`.

### 15.3 Animation

Works checked in history management, or the works from a selected work back to its origin in the lineage, are exported as one moving image.

| Setting | Choices |
|---|---|
| Format | PNG animation (APNG, lossless), GIF animation (256 colors) |
| Transition | Cut, crossfade, fade through white, horizontal slide |
| Hold | Seconds each work is shown |
| Resolution (Y axis) | 150 px, 300 px, 500 px, 1K (1080 px), 4K (2160 px), 8K (4320 px), custom |

From history management the order is oldest to newest; from the lineage it runs from the origin to the selected work.

## 16. Batch

1. Open the `Batch` tab.
2. Enter one description per line.
3. Press `Paint`.

While it runs, the current line, progress, elapsed time, token counts, and the instructions in flight are shown. Failed lines can be inspected in the report, and successful works are saved to history. Each work records the batch run ID and the line number.

Descriptions used before can be restored from `Batch description history`. The last fifty are kept (v2.13.21; twenty before that). The list reaches half the window height at most and scrolls when it does not fit. Clicking outside it or pressing `Esc` closes it.

A batch that stopped part-way can be carried on with `Resume where it stopped`, which appears to the left of `Paint` (v2.13.21). Pressing it paints only the lines that have no work yet, keeping the line numbers of the original description. The button appears only when the last batch work painted is not the last line of the newest description in `Batch description history`. The models, color catalog, sketch, wild and canvas used for the resume follow the record of the last work painted. A setting with no record is left as it is now.

Set `Batch retry` in the settings to one or more and the failed lines alone are painted again after the first pass. Zero means no retry. A run that was stopped is not retried.

## 17. Demo

The `Demo` tab writes short descriptions from a seed phrase and paints them repeatedly. You can set saving to the DB, saving to files, the description model, the display interval in seconds, and a timeout in minutes.

Even with automatic saving disabled, the current work can be saved to history explicitly. The demo stops on its own when the configured time is reached. History actions are locked while a demo runs.

## 18. Settings

Open the settings from the application rail. Which tabs are visible depends on the role.

| Tab | Contents |
|---|---|
| Models | Default models, AI service connections, published model selection |
| DB settings | The current server DB; DB backup interval, generations, time, and manual run |
| Plugins | The state of the system plugin, canvas ratio, and of user plugins |
| User management | Adding, changing, and deleting users and groups |
| Export | PNG export templates, animation across several works, the shareable card's layout and seal |
| Limits | The ceilings, such as how many marks one work may hold |
| Log retention | Log retention and rotation policy |
| Unread-word ledger | Words interpretation could not map directly |
| Other | UI mode, theme, mascot, download folder, batch retry |
| Other (server) | Automatic saving of output files, painting concurrency |

The settings dialog opens either `Standard` or `Detailed`, switched from the toggle at its top right. **The `Plugins`, `Limits`, `Unread Word Ledger` and `Other (server)` tabs appear only in `Detailed`.** The choice stays in that browser.

`Limits` is not a speed control: it changes the number of lines actually drawn. The values chosen there are written into the Stage 1 and Stage 2 prompts and recorded on every work painted. See `Server Configuration` for the details.

**When a work is redrawn, the limits it was drawn under are the ones that apply** (v2.13.30). Today's settings are used only for an older work whose row recorded no limits. **When a limit actually takes effect and drops marks, it says so under the picture, named** (the same place as the plugin warnings). The same rule holds here as in the settings: a limit can be lowered for one drawing, never raised.

The nine numbers fall into three families, and **each family answers to a different authority**
(v2.13.28). `What this machine can draw` is how much the installed hardware can afford to put on one
work, and it is the only family that should follow the machine. `Where counting by eye stops` is the
line between a number small enough to draw as stated and one shown as a band instead — **a faster
machine does not make an eye faster, so do not link it to the family above**. `Guards against a
typing mistake` only stops a typo or a runaway, and moving it makes no drawing better. Hovering a
family heading says what that family should follow.

The `Unread-word ledger` collects words whose direct counterpart could not be confirmed when the description was interpreted into DDL. Nothing is promoted from this ledger into the dictionary automatically. Administrators can also see the ledger for everyone.

## 19. Paint from the CLI

The CLI uses the same public HTTP API as the Web UI.

```sh
cd cli
uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
uv run inku-cli --base-url http://127.0.0.1:8100 paint "a blue line undulates slowly from lower left to upper right" -o out --png --save-history
```

The settings offered in the Web UI can be passed as flags.

```sh
uv run inku-cli paint "night fog spreads" --sketch --sketch-grain coarse --wild \
  --catalog-mode auto --canvas-aspect byobu -o out --png --save-history
```

```sh
uv run inku-cli batch -f prompts.txt -o out --png --continue-on-error
uv run inku-cli history --limit 20
```

Flags you omit fall back to the server defaults, and the server defaults are not always the Web UI defaults. Sketch from life, for one, defaults to off on the server and to fine in the Web UI. See the `inku-cli Reference` for the full list of flags.

## 20. When a Work Does Not Come Out

| Symptom | What to do |
|---|---|
| Not what you meant | Read the instructions and make place, count, shape, and material concrete |
| The description is read too coarsely | Set the sketch grain to `Fine`. If it is already fine, try `Coarse` |
| The picture is monotonous | Add one of touch, sway, composition, or color. Or try `Variation` at `Subtle` |
| The lines are too tidy | Turn `Wild` on |
| Too many elements | State the count explicitly, as in `three lines` or `twelve` |
| A stated count is reduced | Check the literal ceiling under `Limits` in the settings |
| Painting is slow | Wait on the provider's queue, or choose a lighter model |
| An error is returned | Shorten the description and split it into one instruction per sentence |
| Painting is refused | The concurrency ceiling has been reached. Wait a moment |
| A comparison result is lost | Adopt or star the compared option to keep it in history |
| Refinement options disappeared | Changing the refinement target discards unsaved options, so save first |

Write observable physical words, not only words of emotional judgment.

```text
Place one broad-brush black line at the center.
Arrange seven gray circles around it, slightly scattered.
```
