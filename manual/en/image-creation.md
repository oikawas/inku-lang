# Creating Images

The Web instructions in this guide use inku v2.15.147 (Build 1223) as their baseline. A description becomes visible instructions, passes through any needed completion and Rust compilation, and is performed from Score.

```text
description + sketch supplement (Stage 0.5, optional) -> interpretation (Stage 1) -> visible instructions (DDL)
            -> composition reading and settling -> completion of needed holes (Stage 2) -> Rust compile -> JSON Score -> SVG
```

The description is the work's score; the SVG is one performance. The same description may produce a different work when its models, sketch, composition seed, or render seed change.

Stage 2 completes holes remaining in the visible instructions; the shared Rust compiler produces JSON Score. Relations come only from the author's instructions or explicit definitions. The old Stage 1.5 and coerce are not layers that invent relations, and the old `Auto-repair` switch is retired. Layer and fallback names retained in older works' provenance describe their historical execution.

The vocabulary used in the UI is as follows.

| Term | Meaning |
|---|---|
| description | The poetic input the author writes. The topmost layer of a work |
| Sketch from life | The Stage 0.5 act of keeping the description and adding prose about place and light |
| interpretation | The Stage 1 act of reading the description and, when enabled, its sketch supplement into instructions |
| instructions (normalized DDL) | The executable specification interpretation produces |
| score (JSON Score) | The intermediate form the shared Rust compiler produces from instructions, saved for performance |
| performance (SVG) | The one-time result of performing the score |

## 1. Sign In and Choose the Display Language

1. Open the inku Web UI.
2. Enter your user name and password.
3. Press `Sign in`.

The left app rail provides settings, profile, theme, UI display language, the tooltip toggle, and sign-out controls. The rail can be expanded or collapsed.

The UI language and the description language are separate. Ordinary painting detects the description language from the entered text, including English text in the Japanese UI and Japanese text in the English UI. Only text with no usable language signal falls back to the UI language. Ordinary Web input always uses automatic detection and has no language selector; explicit API language settings are separate.

`UI mode`, under `Display and operation` in Settings, chooses how much of the screen is shown.

| UI mode | Contents |
|---|---|
| Simple UI | Shows the essential items and the history |
| Custom UI | Adds the items you choose to the essential ones |
| Full UI | Shows every available item |

The UI mode can also be switched from the icon on the left of the rail. **The number of dark bars is the mode that is on**: one for simple, two for custom, three for full. The menu is listed in the same order (simple, custom, full).

The user menu, settings, one description and Paint action, and the canvas are always visible. Open history and the library when needed. Custom UI can add seven groups: batch and demo; model, color, sketch, and canvas settings; view and edit instructions; timing, tokens, and provenance; refinement, comparison, export, and work actions; history and work navigation; theme, language, and work information.

This manual assumes Full UI. Under Simple UI some of the operations described here are not on screen.

### Changing your own password

1. Press your user name in the left app rail and choose `Profile`.
2. Fill in both `Current password` and `New password`. **One without the other changes nothing** (leave both empty when you only mean to correct the email address).
3. Press `Save`.

The new password must be at least eight characters. **It does not change unless the current password is right.**

**⚠ If you have forgotten it and cannot sign in, this screen is out of reach.** The way back is `inku-admin reset-password` on the server, described in 2.2 of Server Configuration. An administrator can change another person's password from `User management` in the settings, which does not ask for the current one.

## 2. Paint the First Work

1. Open the `Describe` tab.
2. Write a short sentence in the description area.
3. Under `Conditions for the next work`, set `Model`, `Color catalog`, `Sketch from life`, `Wild`, and `Canvas` if needed.
4. Press `Paint`.
5. Confirm that the performance appears in the `Work` tab and is saved to history.

While you wait, the indicator names the stage that is working. When `Paint` draws a single work, it reads `Interpreting your words…` until the drawing is done, and beside it `Awaiting reply (try 1/4)` and the like count the attempts at the model's reply. For the candidates refinement makes, the demo, and batches, the layer names (`sketching from life…`, `interpreting your words…`, `writing the score…`, `performing…`) **are switched by a signal the server sends when each layer finishes** (v2.13.39). With `Sketch from life` set to `Off`, the wait does not open on `sketching from life…`. Either way, while the composition is being read (after Stage 1, before the instructions are settled), it reads `Reading the composition…`.

The first work is the source work.

Examples:

```text
The moon rises beyond the mountain
```

```text
A blue crayon line undulates loosely
```

```text
Place three small red circles in the upper right of a white margin
```

Below the input field, at the right, the description's length is shown, and the name of a verse form only when the description is close to one. Japanese is counted in sounds: close to haiku or senryū (5-7-5), katauta (5-7-7), dodoitsu (7-7-7-5), tanka (5-7-5-7-7), sedōka (5-7-7-5-7-7), bussokuseki-ka (5-7-5-7-7-7) or chōka (5-7 at least three times, closed by 7), it reads as in `Sounds 17/17 (haiku or senryū)`; the sounds cannot tell haiku from senryū, so both are named. Set out in phrases (line breaks, spaces, 、), a description is judged by them: each phrase and the total within two sounds of the form's (extra or missing sounds). Written as one run, the total decides, within two sounds, and 38 names both sedōka and bussokuseki-ka. Near no form, only the count is shown, as in `Sounds 52`. The Server counts the sounds by looking up each kanji's reading in a dictionary, so a classical or poetic reading, or a word it does not know, can be counted differently from the way it is read aloud; a character it cannot read adds `about`. For the moment before the count comes back, characters are shown. English is counted in lines, as in `Lines 3/3 (haiku)`: one line is no form; 2 lines a couplet; 3 lines a haiku at 17 syllables or fewer and a tercet above; 4 a quatrain; 5 a cinquain when the lines are near 2-4-6-8-2 syllables; 14, 19 and 39 lines (one either way) a sonnet, villanelle and sestina. The Server counts syllables with a pronouncing dictionary (CMUdict). All are guides, not limits. The work-editing menu's `Change the description` shows the same meter. An administrator can switch the Japanese and the English judgement off separately in Settings > `Other (server)`; a language switched off shows only its character or line count.

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
| Shape | circle, ellipse, triangle, square, line, arc, free line, point, cloudform |
| Color | white, black, blue, red, green, gray, yellow, orange, purple |
| Place | top, bottom, center, left edge, right edge, upper edge, lower edge, corner |
| Motion | place, arrange, fill, scatter, draw, tile |
| Touch | pencil, pen, rotring, crayon, chalk, fine brush, broad brush, burin, drypoint |
| Continuity | solid, dashed, dotted, dash-dot |
| Surfaces | empty, flat, sweep, grain, stipple, hatch, crosshatch, aquatint |
| Handling | dense, temperate, faint |
| Grounds | paper, washi, ink-wash ground, charcoal ground, canvas, drawing paper, mezzotint |
| Sway | narrowly, broadly, loosely, tightly, swaying, undulating, bleeding |

No layer adds what the description does not ask for. What is written is performed as far as it can be.

**Naming a sheet with `Ground:` changes how the mark runs** (v2.13.31). Each of the seven supports carries its own absorbency and tooth, so the same description with the same settings leaves a different mark on washi than on canvas. How much it shows depends on the tool: a pen picks up almost nothing from the sheet. **`Surface: grain` and the sway `bleeding` now stay where they are when they land on a line or an arc** (also v2.13.31; Saijiki v2 moved bleeding from the surfaces to the sways). These two say how the mark runs rather than how an inside is, so they make that one instruction work the sheet harder (up to three times). **`Surface: sweep` stays there too** (v2.13.35; Saijiki v2's word for the retired pale ink wash, which becomes `faint sweep`). A sweep is not about the sheet but about the stroke (a broad sweep of the brush), so instead of working the sheet it **draws that one mark as a broader band** (three times the width, at 0.8 of the tool's opacity); for a paler band, add the handling word `faint`. **Before v2.13.35, a wash named on a line or an arc was drawn nowhere at all.** The other surface words move to the closed shape before them as before, and are dropped where there is none.

**A `free line` is a line whose path between its start and its end the drawing decides** (v2.15.147). Write it as you write a line, as in `Draw one black pen rising free line at center`; angle, place, draw, scatter, and line up work as they do for a line. The path is built from three to seven parts (straight runs, arcs, and free bends), and the tool decides how: tools that draw with a fine point (silverpoint, pencil, pen, rotring, computer, burin, drypoint) use only straight runs and arcs, while tools that draw with a tip or a face (crayon, chalk, fine brush, broad brush, oil paint) use free bends too. The bends turn away from the edges of the paper and from the shapes drawn before it (lines and free lines aside). With no size written, it is 0.55 of the short edge long (about twice a line). One sentence that draws several gives each its own path. **When drawing from a description** (v2.15.149), interpretation (Stage 1) is told to choose a free line only when the description names one, or when what it describes is a line without a set shape, such as a track left behind or a path something took. If no angle is written, the composition reading writes one from how the layer moves (rising → up to the right, falling → down to the right, flowing → level).

An explicit count is retained in the meaning of the instructions. The current drawing budget does not silently substitute a representative count. If a single primitive exceeds the budget, the permitted prefix is drawn and diagnostics report the requested and performed counts. Older count rewriting and representation belong to saved-format compatibility. See [Server configuration](server-configuration.md) for details.

A written size is treated the same way. A sentence that states a size, such as "a small circle", is drawn at that size. It takes effect when the clause stating the size settles on one group; if several clauses share the same shape so that it is not settled, the size is left alone. Where the clause states the value itself, such as `radius 0.02`, that value is used. A description that states no size is drawn at the default size, as before.

Leading serial numbers and bracketed annotations belong to the writer, not to the drawing. If nothing but numbers and annotations remains, painting reports that there is nothing left to draw.

## 4. Sketch from Life (Stage 0.5)

`Sketch from life` keeps the original description and adds prose about place and light for interpretation. Choose it from `Sketch from life` in the button row of the describe tab.

| Choice | Contents |
|---|---|
| Off | Skip the sketch and send the description to interpretation (default) |
| On | Add a supplement about place and light to the description |

`Fine` and `Coarse` on older works record the sketch method used at the time. They are no longer current choices.

After painting, the result appears under `Sketch from life (Stage 0.5)` on the left and can be edited there. Drawing again with the same description and the sketch on sends the edited sketch to interpretation as a supplement. Changing the description generates a new sketch; switching the sketch off omits the supplement.

If the layer does not answer, the description goes to interpretation unchanged and the work records that. A work painted with the layer off carries the same kind of record.

`Sketch from life (Stage 0.5)` folds from the triangle in its heading. This state is saved on the account and starts open. The instructions box stays visible. Folding numeric ranges within its editor is separate from collapsing the whole box.

## 5. Consult the Saijiki

The `Saijiki` is inku's vocabulary dictionary. Open `New instructions` or `Instruction editor` to find the shared instruction editor, with a broad Saijiki list beneath it. Close the vocabulary to make more room for the text.

1. `New instructions` starts with an empty text; `Instruction editor` starts with the displayed work's text.
2. Review the categories and words. Hover over or click a word to read its effect and example in the separate preview.
3. Pick a word to insert it into the selected text or at the cursor.

The eleven words under `Surface` each carry a small drawing of how the face is, and a note on what it does to the performance. Every drawing shares the same outline; only what is inside it changes.

The Saijiki is not autocompletion. Consult it when needed; it does not narrow a description to the existing vocabulary on its own. Picking a word does not start painting.

Plugin words appear in the same row and wear the same face as built-in ones. The explanation is not under the word but in a preview panel separate from the list, which carries four parts: name, effect, example, and picture. The picture appears only when the plugin document ships one; a word without one gets the same fallback picture a built-in word gets.

## 6. Read and Edit the Instructions

After painting, the instructions section on the left shows how Stage 1 read the input.

- description: the words a human wrote
- Sketch from life (Stage 0.5): prose supplementing the description with place and light (older works retain their original sketch)
- instructions (normalized DDL): drawing instructions arranged into the core vocabulary
- Expanded (Stage 2 input): the DDL Stage 2 actually received, after plugin expansion and the expansion layer filled in
- JSON Score: the machine-readable score Stage 2 writes
- Work: the SVG the renderer performs

The headings of the instructions section on the left and of the instructions editor name the language the instructions are read in: `Instructions (Japanese DDL)` or `Instructions (English DDL)`. The editor judges it again from the text being written. Numeric ranges and the like are written differently in Japanese and English, and the instructions are read with that language's grammar. A single hiragana, katakana, or kanji character makes them Japanese DDL, so one Japanese name in English instructions has them read as Japanese.

The old `Auto-repair` switch is retired. When instruction validation or completion needs your decision, follow the displayed reason and the editing or approval controls.

The instructions box on the Describe tab also lets you edit the whole text directly. The box and Instruction editor share highlighting, completions, range folding and editing, IME composition, and copying. Line numbers appear only in the Instruction editor. When the box is editable, clicking a Saijiki drawer word inserts it at the box's caret and also shows its preview. Before you place the caret, words append at the end. While the box is read-only, in batch mode, or while the editor dialog is open, the drawer only previews. Editing the box alone never draws; press `Draw from instructions` to redraw once.

`Discard edits` in the box and `Instruction editor` asks for confirmation. Press `Discard` to return to the saved instructions the target work was drawn from. Opening the editor from the box still returns to that work's instructions, rather than the box's draft. The box returns its draft; the editor returns only its own text and leaves the box's draft unchanged. Returning never draws. The button is disabled when the text matches, while read-only or while drawing, and is absent from `New instructions`. Cancel leaves the text unchanged. After discarding, ⌘Z (Ctrl+Z) in that editor restores the text from before the discard.

There are two entrances to the instruction dialog. Both use the same dialog and editor. The text shows line numbers, syntax color, line and character counts; choose the painting model and `Wild` outside the text. While painting, the text, Saijiki, condition changes and close control are unavailable. A failed or stopped painting keeps the text.

| Action | Contents |
|---|---|
| New instructions | Open it from the Describe side. Write instructions directly, without a description, and paint them as an independent work |
| Instruction editor | Open it beside the displayed work's instructions heading or from the work editing menu. Edit the text and repaint it as that work's child |

`Draw from instructions` sends the displayed instructions to Stage 2 unchanged. Stage 1 does not run, so the interpretation does not change.

On Web and Android, when instruction completion stops, `Gaps that could not be completed` shows the author's original text and a plain reason for each gap. The approval screen also shows these when a proposal leaves some gaps uncompleted. Gaps that passed are not listed. A context that is too long gets an explanation; an unknown reason reads `Refused by the check (code).` While the model is asked again with the reasons its proposal was refused, the running line reads, for example, `Asking again with the reasons the proposal was refused (2/4)`. A communication retry continues to read `Retrying`.

For a place the existing position words cannot say, the completion keeps the author's words exactly and writes a horizontal and vertical range in parentheses after them (for example `at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)`). The check refuses a proposal whose range falls outside the range of the words before the parenthesis. When the check refuses a proposal, the same gap is asked once more, with the reasons.

### See and edit a place's range

When a range's name and numbers match the range table, for example `at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)`, the display folds the numbers and gives `bottom right` a dotted underline. Hover over or press the name to show its rectangle on the work. Press it to open the muted numbers for editing. The rectangle follows valid numbers, and a match to another table entry changes the name too. Setting both axes to `0 to 1/3`, for example, changes the name to `top left`.

Numbers outside the table or a name that disagrees with its numbers stay unfolded. Editing to numbers outside the table replaces a table name with `the chosen place` and shows the numbers. Words you wrote yourself are kept. In both the box and the editor, the name follows when you leave the range; ranges whose numbers you did not edit keep their words. If you edit the words after editing the numbers, those words are kept. Editing the numbers again makes the name follow again. Numbers outside 0–1, an end that is not greater than its start, or unreadable numbers show an invalid state; the rectangle stays at its last valid place.

Changing the numbers edits the instructions. Typing does not draw; press `Draw from instructions` to redraw once. Saving, copying, and the text editor use the complete source with its numbers. Only the display folds them. An older drawing engine without a range table keeps the complete display.

For each range the completion wrote, the work keeps the words and numbers as approved, and the instructions of a saved work mark each such range `completion`, `numbers edited` or `words edited`. A range whose numbers you edited is drawn at those numbers, as before. A range whose words alone you edited goes back to the completion when you draw, which asks you to approve a proposal with numbers rewritten to fit the new words (a note reads, for example, "One range has edited words. Drawing asks the completion to rewrite its numbers and asks for your approval."). Instructions exported or imported on their own carry no such record and are drawn at their numbers, as before.

### Joint phrases

When the description says how things meet (resting on, inside, overlapping, crossing, connected), the composition joins that layer to its partner. In the instructions the layer's sentence comes right after its partner's and ends with a phrase such as `resting on the previous shape`. The other phrases are `inside the previous shape`, `overlapping the previous shape`, `crossing the previous shape` and `connected to the previous shape`. Japanese instructions write `前の形に載る` and so on.

The range in a joined sentence sets how far the layer spreads. The phrase sets where it goes: the layer is drawn against its partner.

A joint that cannot hold is not written. A layer whose place the description states, for example, is drawn at that place, not joined to another.

You can also write joint phrases in the instructions yourself (they are words of "between" in the Saijiki). Only the fixed phrases `resting on the previous shape`, `inside the previous shape`, `overlapping the previous shape`, `crossing the previous shape` and `connected to the previous shape` make a relation, and English also reads the short forms `resting on`, `inside`, `overlaps` and `crossing`. Japanese writes `前の形に載る` and so on. The joined shape only moves, without resizing, to meet the previous shape, which stays where it is. When the joined layer is a crowd, resting on, overlapping and crossing move the whole crowd as one shape, while inside moves each member inside its partner. Crossing goes across the partner's narrow direction. A filled partner is joined where it is visible. When the relation cannot hold, because of the shapes' sizes or kinds for example, only the relation is dropped, and the reason is shown (for example "The relation was omitted because the shapes cannot hold it (too large to fit inside, too short to cross, or a point as the other shape).").

A free line takes only two relations, the "between" words `connected` and `touching` (v2.15.147; a connection to the middle of a free line is not one of them). When resting on, inside, overlapping, or crossing, or along, not touching, cutting, or between lands on a free line, only the relation is dropped, with its reason shown, and the free line is drawn. The composition, too, joins a free line only with `connected to the previous shape` (v2.15.149).

### A plugin name that does not exist shows up while you type

A `namespace.word` such as `Nature.青葉` is marked in the plugin color only when that qualified name is registered on this server. **A name that is not registered takes a different color, and the reason is listed under the editor.**

- **If the word is a firing word, the editor says how to drop the prefix.** `Nature.菖蒲` reads `Remove "Nature." and it fires as "下草"`, because `菖蒲` is one of the words that fire `Nature.下草` while the qualified name itself does not exist.
- **If it is not a firing word either**, the editor says `This name is not registered`.
- **The color means caution, not error.** Plugins can be added later, so a name missing today may be valid tomorrow.
- **⚠ A qualified name that does not exist costs the whole sentence.** When the expansion layer strips `namespace.`, it removes that sentence with a warning. **The same warning stays under the work after it is painted.**
- **A word without a dot is unchanged.** Written as plain `菖蒲` it stays an ordinary word and keeps its color.

### A work whose DDL was edited holds its description

A work whose instructions (DDL) were edited follows its DDL, not its description. Drawing it again from the description would lose the edits, so **its description is held**.

- The Describe tab heading shows `Held (DDL edited)` and the description cannot be changed. In place of `Paint`, `Start a new work from this description` appears: it draws the description as it stands as a new work (this work stays as it is, and the description can be changed in the new work).
- In the work's edit menu, `Change the description`, `Redraw with or without sketch from life` and `Change the model` are shown but not offered, with the reason.
- A child made by layout or color (or by touch, before it was removed) carries the DDL and is held as well. A child made by reading the description again is not.
- The history strip shows a lock mark, and a lineage card shows `Held (DDL edited)`.
- Autonomous refinement draws each color or layout round from the DDL. The Vision method is offered too: its advice only picks the element to change and is not added to the drawing.

## 7. Choose Model, Color Catalog, Sketch, Wild, and Canvas

`Conditions for the next work` on the Describe tab apply to the next painting. The input tabs are `Describe` and `Batch`. Batch shows the same kind of choices as its own `Drawing conditions for the next batch`.

| Control | Contents |
|---|---|
| Model | The drawing model used for both Stage 1 and Stage 2 |
| Color catalog | The catalog that maps abstract color names such as `red`, `blue`, and `gray` onto actual colors |
| Sketch from life | The grain for Stage 0.5, described in §4 |
| Wild | Removes the stroke limit |
| Canvas | The aspect ratio |

Drawing uses the same model for Stage 1 and Stage 2. Models measured per stage are ordered by the lower of the two stages. The model for Vision, which reads images, is chosen separately.

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

The conditions of the displayed work and the conditions for the next work are separate. `Conditions of the displayed work` records how the selected saved work was painted; `Conditions for the next work` controls what comes next. Reading a work preview in the library does not change the next conditions. Different values on the two sides are not an error.

## 8. Refine

A refinement changes exactly one element at a time, chosen from the work-editing menu (`Refine` on the Work tab, or `…` on each work in the Lineage tab).

| Element | What changes | Cost |
|---|---|---|
| Another composition | Chooses numeric ranges again, except corners. The option's seed also reselects explicit tilt angles and corners | Fast (choosing ranges calls no LLM; existing completion only runs when the instructions still have gaps) |

In `Another composition` you may choose `Make one option` or `Make four options`.

Check the options you want to keep, then press `Make four options` to save those checked at that moment before drawing the next four. Unchecked options are not saved. If saving fails, no new round starts; the options and unsaved selections remain.

`Another performance` (changing the touch with words) and `Another reading` were removed on 2026-10-14: the touch's words were never read for their meaning and only made the drawing's seed. `Edit drawing parameters` in the work-editing menu, which drew them, and the `Touch` and `Reading` elements of autonomous refinement were removed with them. Works made by a touch or a reading before then keep their `Touch` or `Reading` edge in the lineage, and redraw from their saved instructions and seed.

The color catalog is changed from the work-editing menu instead (8.3).

Under `Another composition`, choose `By principle` or `By chance`. The default, `By principle`, solves another composition from what the instructions alone tell; `By chance` chooses among the ranges each layer's kind permits. Options use the saved instructions, so a work without a description can make them too. Numeric ranges are chosen again whoever wrote them. Corners, place words, characters outside the moving ranges, and the original work stay as they are. A sentence with a joint phrase (6) keeps its range and its phrase, and the layer is drawn joined to its partner.

Each option shows its layer number and move, such as `1: bottom right → top left`. When the ranges cannot be chosen again, it gives a reason, such as no composition ranges in this work or too many combinations to find another composition, and rebuilds the saved instructions as they are. A work without numeric ranges, explicit tilts or corners may give the same picture. Saving an option records the composition seed and chosen mode on its Layout lineage edge.

### 8.1 Variation (retired)

Variation was retired on 2026-10-04. Once the focus reinterpretation was removed it had nothing left to move, and the word was confusing next to refinement. Works made by an earlier variation keep a "Variation (retired)" edge in their lineage, and their provenance shows the variation seed and amplitude of that time.

### 8.2 Save Options

Options are unsaved. Select the ones to adopt and choose `Save the chosen ones and close` to save them to history; the others are discarded. To keep none, choose `Discard all and close`. While unsaved options remain, the ×, the backdrop and Escape do not close the dialog and it asks for one of the two. Reloading or closing the tab brings up the browser's confirmation.

Pressing an option enlarges it inside the dialog; `Back to all options` or a second press returns to all of them. Saving and starring are separate actions. You may record why you chose a saved option.

### 8.3 Another Catalog

Choose `Another catalog` in the work-editing menu (`Refine` on the work tab, or `…` on each work in the lineage tab) and a dialog of its own opens. It starts at once and lays out the same work in every color catalog except the current one, in the order of the catalog list. The DDL, JSON Score, composition, and performance stay as they are, and no LLM is called. Each option is labeled with its catalog's name.

Choosing, saving, and discarding options work as in 8.2. After a stop or a failure, `Draw in the other catalogs` draws them again. Only the saved JSON Score is redrawn, so a work without a description (one written directly in DDL) makes options too.

### 8.4 Change the Color Arrangement

Choose `Change the color arrangement` in the work-editing menu to see 8 options with colors reassigned within the current color catalog. Placement, touch, and instructions stay the same, and no LLM is called. `Next 8 options` switches the displayed page once the next distinct options are ready. Earlier options and selections are cleared. Once the possibilities run out, only the remaining options appear and no next page can be drawn.

Choosing, saving, and discarding options work as in 8.2. A saved option retains its chosen colors when the work is drawn again.

### 8.5 Change the Ground

Choose `Change the ground` in the work-editing menu to see options with the work's ground (the saijiki's grounds: paper, washi, ink wash ground, charcoal ground, canvas, drawing paper, mezzotint) replaced by each ground the work is not on: 6 options for a work that names a ground, 7 for one that names none. Placement, color, and touch stay the same, and no LLM is called. A saved option's instructions name its new ground (the ground sentence is replaced, or placed first when the work had none).

Choosing, saving, and discarding options work as in 8.2.

### 8.6 Change the Touches

Choose `Change the touches` in the work-editing menu to open a dialog that replaces only the touches of the work's sentences (the saijiki's touches: twelve drawing tools such as silverpoint, pencil, pen, crayon, chalk, fine-brush and oil paint) with other tools. Opening it draws nothing. Choose a way with the radio and press `Make four options` to see four options:

- `Same tool for every sentence` (the default): each option gives every sentence one tool, and is named after it.
- `A different tool for each sentence`: each sentence draws a tool other than its own, and the option lists which sentence took which tool.

Pressing `Make four options` again first saves the options checked at that moment, then draws four new ones. Unchecked options are not saved. If saving fails, no new round starts; the options and unsaved selections remain. Placement, color, and ground stay the same, and no LLM is called. A saved option's instructions name the new touches; a sentence that named none (drawn with the pen) has the new word written before the shape's name.

Choosing, saving, and discarding options work as in 8.2.

## 9. Autonomous Refinement

From the lineage tab the application can build generations on its own.

| Mode | Contents |
|---|---|
| Random autonomous refinement | Builds generations at random from the chosen elements |
| Autonomous refinement with Vision | Observes the picture and chooses the element the next generation changes |

You choose the number of generations and which refinement elements to use (color catalog and composition). The direction field appears only with the Vision method, where it is material for Vision's advice; it is not added to the drawing.

In either form of autonomous refinement, a color generation draws its parent's saved instructions in another color catalog, without reading the description again (until 2026-10-14 a work drawn from a description was drawn again from Stage 1).

In either form of autonomous refinement, a composition generation rebuilds its parent's saved instructions `By principle`. A manual choice of `By chance` does not change this default. Choosing the composition ranges calls no LLM.

**The model chosen for autonomous refinement with Vision is used to draw each generation, not only to observe it** (the running display names the model it is drawing with). Random autonomous refinement chooses no model, so it draws with the model selected on the page.

The dialog remembers the method, number of generations, refinement elements and direction you chose last time, and opens with them next time (kept in this browser). The wild switch is not remembered; it starts from the work being refined.

Both methods draw the next generation from the parent's saved instructions without running the sketch again. The direction guides Vision's advice and choice of the next element to change; observations and the next direction are recorded, not appended to the drawing text. The sketch setting on the `Describe` tab is not used.

## 10. Change the Model

Choose `Change the model` from the work-editing menu (`Refine` on the Work tab, or `…` on each work in the Lineage tab) and a dialog of its own opens. Pick the models from those laid out across the top and press `Draw with the chosen models`: each chosen model redraws the work from its description, and the options are laid out side by side. Each chosen model runs both Stage 1 and Stage 2; neither stage is held fixed. The color catalog and the canvas are the target work's.

At most four models can be chosen. A model used by the target work cannot be chosen; when an old work used different models for its two stages, neither can be chosen. Old works' records remain unchanged.

While the options are drawn, the mascots show each model's progress, as in Another catalog. A model that returns an error is marked `NG` in the picker and the count is reported; the other models' options stay. Pressing again with other models chosen adds their options after the others. A model that has drawn once is not drawn again.

Choosing, saving, and discarding options work as in 8.2: choose the ones to keep with `+` at their top right, then save them to history with `Save the chosen ones and close`. The dialog does not close while options are unsaved.

## 11. Read the Provenance

Open the provenance drawer at the bottom of the work tab to see the record of the selected work. Its tabs are `Details`, `Prompts`, and `JSON`.

`Details` has the following sections; sections such as Sketch and Origin depend on the work's records. The follow-selection setting in `Display and operation` is enabled by default: with the drawer open, selecting another work in the history strip switches its information to that work.

| Section | Main contents |
|---|---|
| Sketch | The sketch record and the paper grain (**the record of the work on screen**, not the setting for the next painting) |
| Interpretation | Stage 1 model, Stage 1 language, requested language, interpretation seed, interpretation fallback and Score fallback records |
| Performance | Stage 2 model, Stage 2 language, focus, Variation (retired) and its seed (old works only), composition seed, render seed, seed text, Wild, the colour words this work was drawn in, the colour catalogue, the canvas and its ratio, and **three rows for how heavy the drawing is** (`SVG size` / `SVG objects` / `SVG points`) |
| Identity | work ID (UUID), render hash, description hash, render engine, DDL specification, transform layer, prompt digests, Build |
| Origin | generation, derivation, batch run ID and line number, comment, UI language |
| Run | elapsed time, token counts |

Every row carries an explanation. The render seed is "the seed that fixes the sway of the performance; the same seed and the same score give the same picture"; the description hash is "the fingerprint of the description; it binds works that came from the same words".

**The weight of a drawing is printed as three quantities.** `SVG size` is the amount of data, `SVG objects` is how many shapes the SVG holds (containers and notes — svg, defs, title, desc, metadata — are not shapes), and `SVG points` is how many points those shapes are drawn from. **None of the three stands in for the others**: at the same size, few objects with many points is a drawing of fine lines, and many objects with few points is a drawing of many forms.

`Prompts` shows the system prompts and input of the sketch (Stage 0.5), Stage 1, the composition reading, and Stage 2, in the order a work calls them. For the sketch and the composition reading it also shows the input actually sent. `JSON` shows the JSON Score. The system prompts are the ones actually sent when the work was drawn, and they differ from work to work with the plugins, the sketch, and retries. A stage that called no model (the sketch of a work drawn without one, Stage 1 of DDL you wrote yourself, the composition reading of a work that had none, Stage 2 when no hole needed filling) and a work drawn before the record began say so instead. The sketch and the composition reading have been kept since 2026-10-13, so an earlier work says they were not recorded. Do not confuse the JSON Score itself with the provenance.

Ordinary Stage 1 generation stops as a failure if its finite retries cannot succeed. Uncompleted holes in the instructions wait for the author's edits; neither case saves a stock replacement as a successful work. Limited fallbacks, such as using the original description after a sketch failure, are separate.

`Interpretation fallback` and `Score fallback` retained on old works describe their historical execution. `No record` does not mean no fallback occurred.

**Choosing a marked work to refine asks you once before it runs.** That work's link to the words is broken, so you are asked whether to continue from it. The same work is not asked about twice.

## 12. Follow the Lineage

The `Lineage` tab shows which explicit action a work was derived from. Performance, composition, reading, model, language, instruction edits, description edits, repaints, canvas changes, and changes of sketch-from-life grain are recorded as parent-child relations. Works made by an earlier variation keep a "Variation (retired)" edge.

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

The history strip at the bottom is for moving quickly back and forth in time. Opening history leads to the separate `Library`, which keeps the making screen's input and unsaved refinement state. `Return to making` also keeps the library's query, filters, display, page, selection, scroll position and reading preview.

The search field immediately after the `Lineage` tab in the canvas header filters the history thumbnails below. It matches a whole UUID, part of a description, or the beginning, end or whole of a render or description hash. Hashes work with or without a prefix such as `rh3:`, and matching is case-insensitive. Search after typing or press Enter, then choose a thumbnail to open the work. The × button clears the query and restores ordinary history. The Library keeps its own separate query.

In the library, choose `Display` (`Thumbnails` or `List`) separately from `Group by` (`Timeline` or `By lineage`). Selecting a row or picture only opens its reading preview; it does not change the conditions for the next work. Use `Open work`, `Open lineage`, or `Refine` for those actions.

Combine `Thumbnails` with `By lineage` to show only lineages with at least two works matching the current search and filters, arranged horizontally from the origin in generation order. Even a lineage with several works is omitted when only one matches. The lineage `List` view has no such two-work minimum. Scroll vertically between lineage groups and horizontally through a long row of related works.

**What is printed under each thumbnail is chosen under `Display and operation` in `Settings`** (`Facts under the history thumbnails`). Choose **up to three** of generation, model, engine version and file size; **choose none and the strip shows only the pictures**. A fourth choice is refused rather than allowed to evict an existing one, and the limit is shown. **File size is the size the server reports for the stored work.**

- Search descriptions, DDL, Stage 1/2 models, color catalogs, whole hashes, hash beginnings or last four characters, and whole work IDs (UUIDs) or their beginnings. Find the UUID under `Identity` in Provenance. Searches are case-insensitive
- Filters for starred only, for revision only, and shared only. Used together, only works matching every one of them remain
- Switching between ordinary history and trash
- Thumbnail view and list view. The list compares hash, timestamp, model, elapsed time, and color catalog
- Move to trash, restore, and permanent delete, singly or by multiple selection
- Expanding and selecting a whole lineage at once
- Syncing to the displayed work and jumping to the oldest or latest page
- **The words for moving agree everywhere.** On the canvas, the strip and Library alike, left is newer and right is older, and `prev`, `next` and `first` are not used (`← newer` / `older →` / `Latest` / `Oldest`)

`By lineage` groups only on stored lineage nodes and edges. `lineage_only` intermediate works and tombstones are not counted in ordinary history.

The revision mark is a second mark, independent of the star. Use it for works you mean to return to.

In multi-user mode, the share mark is a third one. Raise it with `Share with group` at the bottom of the canvas on the Work tab. **Once it is up, the members of your own organisation group can read that work.** Use `Stop group sharing` to lower it. An administrator may aim it at another organisation group instead.

**Lowering the mark keeps the destination.** Marking the same work again returns it to the same recipients. **What this mark widens is reading only, never writing** — a work shared to you cannot be starred or moved to trash by you. Lineage nodes follow the mark, but **the colophon does not**.

Both the history strip and `Library` carry a `Group shared only` filter, so the marked works can be listed on their own.

In single-user mode, group-sharing buttons, the sharing dialog, sharing filters such as `Group shared only`, and sharing-status marks are hidden. Group and permission administration remain available.

`Replay` compares the saved SVG with a performance of the stored Score and conditions on the current engine. An engine-version difference is reported. Old works without a recorded render seed can also be compared using provisional seed 0; this does not guarantee exact recovery of their original performance.

`Save this performance as a child` keeps the source and saves the replay in ordinary history as its child, without increasing the generation count. A readable saved source and matching parent are required. Saving is unavailable if the managed work's authority and policy cannot be retained or the comparison result cannot be verified. Read the displayed reason and retry after a failure; the source is never overwritten.

## 15. Export Images

Open `Export` at the bottom of the Work tab, check that the target is `Displayed work`, then choose an SVG format or PNG size. When exporting from the Library or Lineage, check the selected count or path from the origin shown in the menu. The `?` by the menu's SVG heading opens the same explanation as the table below.

Only a saved work is exported. A picture that is not saved (one drawn by the demo with saving off, for instance) is saved first, then exported. In the simple UI the `Export` button exports the `Share card` alone, directly.

| Format | Use | Characteristics |
|---|---|---|
| Display | Web display and PNG generation | The stored SVG. Favors visual fidelity and uses filter and clip-path |
| Editable | Illustrator / Affinity | Regenerated from the score. Carries layer structure and stable IDs, and avoids filter and clip-path |
| Compatibility | General SVG interchange | Regenerated from the score. Close to Editable, but favors robustness |
| Live | Video software such as VIA2 | Drawn again from the score. Editable's structure with Display's textures and touch. Meant for software that draws one instruction at a time; for ordinary viewing Display is lighter |
| PNG | Raster image at a chosen resolution | Choose the height; width follows the work's aspect ratio. Default templates use heights of 1080 / 2160 / 4320px, and more can be added in settings |

`Editable`, `Compat`, and `Live` are drawn again from the Score, and **a redraw uses the performance that was saved** (both the render seed and the composition seed the saved work carries). **The only difference from the stored SVG is how far the drawing engine has moved on** -- inku keeps no past version, so a redraw after the engine advances is never byte-identical.

Set the download folder under `Settings` → `Export` → `Save location`. Without one, files land in the browser's default folder. The folder itself lives only inside that browser, so another browser or another device needs its own choice. If writing is not permitted, the file lands in the browser's default folder and says so.

### 15.1 Contact Sheets

Works selected in Library are laid out on a single PNG.

| Kind | Contents |
|---|---|
| Contact sheet for people | 7×4 works per sheet. The remainder goes to further files |
| Contact sheet for AI | 3×4 works per sheet, 1568px on the long edge, captions numbered only. A companion md holding the numbers, descriptions, DDL, and provenance is saved alongside |

### 15.2 Shareable Card

A work is exported as a single card. The drawing, the headnote, the last four digits of the render seed, and the seal are composed into one sheet. A work with no headnote becomes a card of the drawing alone, and a work with no render seed shows no seed line.

There are two doors.

| Door | What it cards | What one press does |
|---|---|---|
| `Share card` inside `Export`, at the bottom of the Work tab | the displayed work | exports one sheet immediately |
| `Share card` inside `Export` in the Library or Lineage | the one work shown in the menu | available when the selection or preview targets one work |

Both follow the same layout and seal settings. A work that has not been saved yet has no card, so the button on the canvas cannot be pressed.

**In the simple UI — and in any custom UI without `refinement, comparison, export, and work actions` — the work's export control becomes a card-only button.** One press exports the card with no menu in between. SVG and PNG belong to that group and are not offered, but the card stays: it is how a work goes to someone else.

| Setting | Choices |
|---|---|
| Layout | Square (1080×1080), portrait (1080×1350) |
| Seal | On (default) or off |

The server composes the card and bakes it with a bundled font, so the characters are the same whatever fonts the viewing machine happens to have. The drawing is nested as SVG rather than pasted as pixels, so the sheet stays vector until the single rasterization at the end. A long headnote shrinks the frame around the drawing, and anything past six lines is cut with `…`.

The same card comes out of the CLI with `inku-cli export-card`.

### 15.3 Animation

One saved work and several selected works export differently. For the displayed work or one checked work in the Library, choose `Layer animation` from `Export`. For several checked works, choose `Transition animation` to move between works from oldest to newest. In Lineage, choose either the path from the origin to the displayed work or only the checked works.

| Setting | Choices |
|---|---|
| Format | PNG animation (APNG, lossless), GIF animation (256 colors) |
| Transition | Cut, crossfade, fade through white, horizontal slide |
| Hold | Seconds each work is shown |
| Resolution (Y axis) | 150 px, 300 px, 500 px, 1K (1080 px), 4K (2160 px), 8K (4320 px), custom |

For one work, `Layer frames` sets the number of forward frames from ground to finish. Layers accumulate from frame to frame until the work is complete. `Layer interval` sets the seconds each frame remains on screen. This is a simulated making process based on the saved SVG's stacking order.

| Replay | Motion |
|---|---|
| Restart from ground | Return to the ground after completion and build up again |
| Play back and forth | Reverse from the finished work to the ground, then repeat forwards |
| Play once and hold | Build up once and stop at the finished work |

For several works, choose the transition pattern and display hold for each work. Format, resolution, and destination are common to both types. Settings and destination changed in the export dialog apply only to that export. In supported browsers, `Choose save path` chooses a folder; other browsers use their download settings.

From Library the order is oldest to newest; from the lineage it runs from the origin to the selected work.

## 16. Batch

1. Open the `Batch` tab.
2. Enter one description per line.
3. Press `Paint`.

While it runs, the current line, progress, elapsed time, token counts, and the instructions in flight are shown. Failed lines can be inspected in the report, and successful works are saved to history. Each work records the batch run ID and the line number.

Descriptions used before can be restored from `Batch description history`. The last fifty are kept (v2.13.21; twenty before that). The list reaches half the window height at most and scrolls when it does not fit. Clicking outside it or pressing `Esc` closes it.

A batch stopped with `Stop` can continue through `Resume the interrupted batch` and `Resume where it stopped`. It checks the unfinished lines of the original batch, skips completed works, and restores the original text and drawing conditions. After a browser reload, the same signed-in account can also resume when its newest saved batch text and saved batch works establish that the batch stopped part-way. If the unfinished lines cannot be established from the saved history and text, no resume card appears.

When a stopped batch still has lines that failed to draw, `Retry failed works` appears. It redraws only the failed lines, with their original text, line numbers and drawing conditions, leaving out lines that succeeded, were interrupted or never ran. Lines that succeed leave the error list, and the remaining errors can be tried again. When the previous batch's full text cannot be confirmed, the button is unavailable and says so.

Set `Batch retry` in the settings to one or more and the failed lines alone are painted again after the first pass. Zero means no retry. A run that was stopped is not retried.

## 17. Demo

Open `Settings` → `Making` → `Demo`. It writes short descriptions from a seed phrase, then paints them repeatedly. Choose saving to DB, saving files, the description model, display interval in seconds, and timeout in minutes.

Choose one drawing model for both Stage 1 and Stage 2, separately from the description model. ChatGPT plans cannot generate demo descriptions. The interval runs from the start of one description generation to the next. Generation and drawing time are subtracted: a 30-second setting with 20 seconds of work leaves about 10 seconds to wait. Work taking longer than the interval leaves no wait; no new work starts after the stop deadline.

Starting Demo closes Settings so you can watch the canvas. While it runs, the making screen shows a stop control and `Demo settings and progress`, which reopens its settings. Description and Batch text are retained.

Even with automatic saving disabled, the current work can be saved to history explicitly. The demo stops on its own when the configured time is reached. History actions are locked while a demo runs.

## 18. Settings

Open it from `Settings` in the app rail. Settings are grouped as `Display and operation`, `Making`, `Export`, `Connections and administration`, and `Extensions and details`, with a separate `ChatGPT plan` category where personal connections are enabled. The pages and controls visible depend on your role.

| Category | Pages and contents |
|---|---|
| Display and operation | `Display and operation`. Text size, caption position, UI mode, facts under history thumbnails, mascot, and related controls |
| Making | `Batch retry` and `Demo` |
| ChatGPT plan | When signed in and the feature is enabled, its dedicated page connects, reconnects, or disconnects your account. Publish models in your personal `Models` settings |
| Export | `Export`. Save location, PNG export templates, animation, and the share card's page shape and seal |
| Connections and administration | Administrators manage shared `Models`, `User management`, `DB settings`, and `Log retention`. Leaders can also manage users within their scope. Where personal ChatGPT is enabled, members can open their own `Models` settings. Administrators' `Detailed` mode also shows `Other (server)` and `Limits` |
| Extensions and details | `Detailed` shows `Plugins` and `Unread-word ledger` |

To choose one drawing model for both stages, open `Model selection` from the making screen's conditions and select it in `Stage 1/2`. Choose the image-reading model separately in `Vision` when needed. Ordinary model selection omits providers with no candidates. If a normal provider's selected model disappears, selection moves to the first available candidate, or keeps the original ID if none exists. Personal ChatGPT does not switch to another model automatically and explains why it is unavailable. The generic pickers in Demo and the Instruction editor instead show empty-list guidance and mark an absent selected ID `Not in the list`.

The stars at the edge of each drawing-model button summarize its rating. Ordinary Stage 1/2 selection uses the lower available stage rating, or the LLM rating for an end-to-end measurement. Its detailed hover can show the strengths of each measured stage. Generic pickers show a single rating for the purpose in both button and hover; they do not select models per stage. Hover also shows `LLM` and `Vision` badges (greyed where unavailable), three recommendation tiers (★★★, ★★☆, ★☆☆), approximate cost (per drawing for LLM, per picture for Vision; $0 for a free model), and speed (measured mean seconds when present, otherwise the speed label).

Administrators' `Models` settings manage shared connections and publication. Where personal ChatGPT is enabled, connect through the separate `ChatGPT plan` page and publish models in your personal `Models` settings, independently of API key connections. Published ChatGPT plan models become drawing candidates for LLM use, and Vision refinement and colophon candidates for Vision use. See the [ChatGPT plan connection guide](../../docs/guide/chatgpt-plan.md).

The settings dialog has `Standard` and `Detailed` modes, switched through `Display mode` at upper right. `Standard` shows everyday settings; **`Plugins`, `Limits`, `Unread-word ledger`, and `Other (server)` appear only in `Detailed`.** The choice remains in this browser.

`Text size` in `Display and operation` has five values: 90%, 100%, 110%, 120%, and 130%. Moving it changes the screen immediately; confirming the control saves it on the account. `Return to standard` restores 100%. If saving fails, the current size remains visible and `Retry` saves it again. It does not change the work SVG, PNG output, or export dimensions.

`User management` provides search, permission and no-group filters, then selection and editing of users. `Add user` opens the add form explicitly. Edit only the selected member, set permissions and groups, then use `Save changes`. While edits are unsaved, it does not refresh the list or select another user; a failed save keeps both input and error. Administrators and leaders use it within their respective permission scopes in the Web UI.

`Limits` applies to the current pipeline's resource policy and drawing budget. All nine values are not injected into both stages' prompts: the normal pipeline uses four ceilings, for marks per work, marks per instruction, resolved count, and instruction count. The `SVG limit` in the `SVG output` group is a safety ceiling for saving newly generated SVG: a work above it is not saved (it is not recorded on works and does not affect viewing saved works). See `Server Configuration` for saved conditions and the current mapping.

**When a work is redrawn, the limits it was drawn under are the ones that apply** (v2.13.31). Today's settings are used only for an older work whose row recorded no limits. **When a limit actually takes effect and drops marks, it says so under the picture, named** (the same place as the plugin warnings). The same rule holds here as in the settings: a limit can be lowered for one drawing, never raised.

The nine values were introduced in v2.13.28 as three families: what the machine can draw, where counting by eye stops, and guards against typing mistakes. They remain for saved-format compatibility; the older thresholds and representative counts do not redefine the current meaning of a count.

The `Unread-word ledger` collects words whose direct counterpart could not be confirmed when the description was interpreted into DDL. Nothing is promoted from this ledger into the dictionary automatically. Administrators can also see the ledger for everyone.

## 19. Paint from the CLI

The CLI uses the same public HTTP API as the Web UI.

```sh
cd cli
uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
uv run inku-cli --base-url http://127.0.0.1:8100 paint "a blue line undulates loosely from lower left to upper right" -o out --png --save-history
```

The settings offered in the Web UI can be passed as flags.

```sh
uv run inku-cli paint "night fog spreads" --sketch --wild \
  --catalog-mode auto --canvas-aspect byobu -o out --png --save-history
```

```sh
uv run inku-cli batch -f prompts.txt -o out --png --continue-on-error
uv run inku-cli history --limit 20
```

Flags you omit fall back to the server defaults. Sketch from life defaults to off in both the server and Web UI. See the `inku-cli Reference` for all flags and compatibility with older sketch values.

## 20. When a Work Does Not Come Out

| Symptom | What to do |
|---|---|
| Not what you meant | Read the instructions and make place, count, shape, and material concrete |
| The description is read too coarsely | Turn the sketch on to supplement place and light; review its text and edit it before drawing again if needed |
| The picture is monotonous | Add one of touch, sway, composition, or color. Or try `Another composition` |
| The lines are too tidy | Turn `Wild` on |
| Too many elements | State the count explicitly, as in `three lines` or `twelve` |
| A stated count is reduced | Check the literal ceiling under `Limits` in the settings |
| Painting is slow | If the running indicator says `Retrying (try 2/4)`, an earlier attempt timed out or its answer could not be used. Wait on the provider's queue, or choose a lighter model |
| An error is returned | Shorten the description and split it into one instruction per sentence. If the reason's parenthesis says the model did not answer within the time limit, the model is not answering in time |
| "Cannot reach the server" | The API is stopped or restarting. The page reopens by itself once it answers; if this lasts, check the server |
| Painting is refused | The concurrency ceiling has been reached. Wait a moment |
| A comparison result is lost | Adopt or star the compared option to keep it in history |
| The refinement dialog does not close | Options are unsaved. Choose `Save the chosen ones and close` or `Discard all and close` |

Write observable physical words, not only words of emotional judgment.

```text
Place one broad-brush black line at the center.
Arrange seven gray circles around it, slightly scattered.
```
