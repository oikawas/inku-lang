# Creating Images

This guide covers work creation with the Web UI and CLI in inku v1.85 (Web Build 564). A description passes through interpretation, deterministic intermediate expansion, structuring, and rendering.

```text
description -> normalized DDL -> expanded DDL -> JSON Score -> SVG
```

The description is the work's score; the SVG is one performance. The same description may produce a different work when its models, layout seed, or render seed change.

## 1. Sign In and Choose the Display Language

1. Open the inku Web UI.
2. Enter your user name and password.
3. Press `Sign in`.

The left app rail provides settings, profile, theme, UI display language, and sign-out controls. The UI language and instruction language are separate. Normal generation detects the instruction language from the entered text, including English text in the Japanese UI and Japanese text in the English UI. Only text with no usable language signal falls back to the UI language.

## 2. Paint the First Work

1. Open the `describe` tab.
2. Write a short sentence in the description area.
3. If needed, set `color catalog`, `model selection`, and `canvas`.
4. Press `Paint`.
5. Confirm that the work appears in `drawing` and is saved to regular history.

The first work is the source work. The Refine action “Another performance” is never applied to this first generation.

Examples:

```text
A moon rises beyond the mountains
```

```text
Blue crayon lines drift in slow waves
```

```text
Place three small red circles in the upper right, leaving white space
```

## 3. Write a Description

For stable results, use physical, observable instructions, one sentence at a time.

```text
color + size + form + count + place + motion
```

Example:

```text
Fill the background with white.
Draw three thin blue lines from lower left to upper right.
Place three small red circles in the upper right.
```

| Type | Examples |
|---|---|
| forms | circle, ellipse, triangle, square, line, arc |
| colors | white, black, blue, red, green, gray, yellow, orange, purple |
| places | top, bottom, center, left edge, right edge, upper edge, lower edge, corner |
| motions | place, align, fill, scatter, draw, tile |
| touches | pencil, pen, rotring, crayon, chalk, fine brush, thick brush, burin, drypoint |
| continuity | solid, dashed, dotted, dot-dashed |
| movements | fine, broad, slow, quick, wobble, undulate, tremble, blur |

## 4. Consult Saijiki

`Saijiki` is inku's vocabulary dictionary.

1. After the first generation, press `Saijiki` on the `Interpretation (normalized DDL)` row.
2. Point to a word to preview how it affects drawing.
3. Select a word to insert it at the DDL caret.

Saijiki is not autocomplete. It is consulted only when requested and does not automatically narrow a description to known vocabulary.

## 5. Inspect and Edit the Interpretation

After generation, `Interpretation (normalized DDL)` shows how Stage 1 read the input.

- Description: the author's original words
- Normalized DDL: drawing instructions rewritten in core vocabulary
- JSON Score: the machine-readable score created by Stage 2
- Drawing: the SVG created by the Renderer

Use `DDL edit` for an expanded editor. `auto repair` enables or disables deterministic repair for invisible colors, excessive density, and contract violations. Press `Render from Code` to draw from the edited DDL.

## 6. Choose Color, Models, and Canvas

The controls at the top of the Describe tab configure the next generation.

| Control | Meaning |
|---|---|
| color catalog | Maps abstract color names such as red, blue, and gray to concrete colors |
| model selection | Selects inference models for Stage 1 (interpretation) and Stage 2 (drawing) |
| canvas | Selects Square, Golden, A4, Wide, Vertical, Byobu, or another aspect |

Canvas coordinates remain normalized from 0.0 to 1.0. The effective settings of the displayed work are different from settings for the next generation. Distinguish `displayed` at the top of Canvas from `next drawing` at the bottom.

## 7. Refine an Work

The `Refine` tab contains `Adjust`, `Model comparison`, and `Language comparison`. Changing the target work clears unsaved candidates owned by the previous target. Merely switching Refine subviews preserves candidates.

### 7.1 Adjust

Select exactly one intervention at a time.

| Refinement | Scope of change |
|---|---|
| Another composition | Keeps the reading and uses Stage 2 to reconstruct coordinates, sizes, and layout balance |
| Another reading | Restarts at Stage 1 and regenerates normalized DDL, composition, and touch |
| Another catalog | Keeps DDL, JSON Score, composition, and touch, changing only the catalog |
| Another performance | Derives only the Renderer performance seed from entered words, changing texture, weight variation, and bleed |

Ordinary adjustments can make one or four candidates. “Another performance” makes exactly one because the same words deterministically produce the same touch (Seed). Those words never affect meaning, interpretation, DDL, JSON Score, or layout.

Candidates are unsaved. Select candidates with the image-corner control and save them to history. Saving and starring are separate actions.

### 7.2 Model Comparison

Paint the same description with different Stage 1 and Stage 2 model combinations, then compare the works and their normalized DDL.

- `Shared Stage 1/2`
- `Fixed Stage 1 + compare Stage 2`
- `Compare Stage 1 + fixed Stage 2`

The target's identical model pair is excluded. Results are not saved automatically. Use `+` to adopt one, or the star action to save it as starred history.

### 7.3 Language Comparison

Normal automatic detection remains unchanged. Only the comparison run explicitly assigns Japanese or English per stage. It uses the same three modes as Model comparison. Results show the effective Stage 1 and Stage 2 languages and normalized DDL. Adoption records a `language_variation` lineage operation.

## 8. Inspect the Provenance

Open `Provenance` at the bottom of Canvas to inspect the selected work.

| Tab | Contents |
|---|---|
| Details | Stage 1/2 models and languages, catalog, canvas, seeds, hashes, render engine, Build, elapsed time, and token counts |
| Prompts | Stage 1/2 system and user prompts |
| JSON | Machine-readable top-level generation metadata plus JSON Score |

JSON includes fields such as `stage1_instruction_lang`, `stage2_instruction_lang`, `render_seed`, `composition_seed`, `interpretation_seed`, `description_hash`, `derivation_kind`, and `derivation_metadata`. Keep top-level generation metadata distinct from the JSON Score itself.

## 9. Follow Lineage

The `lineage` tab shows which explicit operation derived each work. Touch, layout, reading, model, language, DDL edit, description edit, replay, and canvas changes can form parent-child relationships.

- Parentage is never inferred from similarity, identical descriptions, or timestamps.
- Continuing from an unsaved candidate stores only that direct candidate as an `intermediate · hidden from history` lineage work.
- `Start a new root` makes the next creation independent.
- Lineage cards support promotion to regular history, comments, stars, and trash operations.

## 10. Manage History

Use the bottom history strip for fast chronological navigation. History Manager switches between `timeline` and `by lineage`.

- Search, starred-only, regular-history, and trash filters
- Thumbnail and list layouts
- Individual or multiple selection for trash and restore
- Lineage expansion and lineage-wide selection
- Synchronization with the displayed work and jumps to first or latest pages

`by lineage` groups only persisted lineage nodes and edges. `lineage_only` intermediate works and tombstones are excluded from regular-history counts.

Canvas `Nearby works` shows up to three structurally similar history works without scores or ranking. Similarity is not lineage and never controls generation or quality decisions.

## 11. Export Images

Use `SVG` or `PNG` at the bottom of Canvas.

| Format | Use |
|---|---|
| Display SVG | Web display and PNG source |
| Editable SVG | Structure intended for editing in Illustrator or Affinity |
| Compat SVG | General-purpose transfer compatibility |
| PNG | Raster output at a selected resolution |

## 12. Batch Generation

1. Open `batch`.
2. Enter one description per line.
3. Optionally enable random color catalog selection per drawing.
4. Press `Paint`.

The UI shows the active line, progress, elapsed time, token counts, and current interpretation. Failed lines appear in the failure report; successful works are saved to history.

## 13. Demo

The `demo` tab generates a short description from a seed phrase and repeatedly draws it. Configure DB saving, artifact saving, the model that writes the description, display interval, and random color catalogs. When automatic DB saving is disabled, the current work can still be saved explicitly.

## 14. Paint from the CLI

The CLI uses the same HTTP API as the Web UI.

```sh
cd cli
uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
uv run inku-cli --base-url http://127.0.0.1:8100 paint "A blue line slowly undulates from lower left to upper right" -o out --png --save-history
```

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 batch -f prompts.txt -o out --png --continue-on-error
uv run inku-cli --base-url http://127.0.0.1:8100 history --limit 20
```

## 15. Troubleshooting Creation

| Symptom | Action |
|---|---|
| The work differs from the intent | Inspect normalized DDL and specify place, count, form, or material |
| The work is too plain | Add exactly one touch, movement, placement, or color instruction |
| Too many elements appear | Use explicit counts such as `three lines` or `twelve circles` |
| Generation is slow | Wait for the provider queue or select a lighter model |
| Generation fails | Shorten the description and separate it into one instruction per sentence |
| A comparison result disappears | Adopt it with `+` or save it with the star action |
| Refinement candidates disappear | Save them before changing the refinement target |

Prefer physical, observable language over evaluation alone.

```text
Place one black thick-brush line at the center.
Arrange seven gray circles around it with slight scatter.
```
