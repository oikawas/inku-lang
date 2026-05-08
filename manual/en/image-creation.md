# Creating Images

inku creates abstract vector images from short written descriptions. A prompt is processed through interpretation, intermediate expansion, structuring, and rendering.

```text
description  ->  normalized DDL  ->  expanded DDL  ->  JSON Score  ->  SVG
```

The same description may produce slightly different output depending on the selected models and rendering variation. inku treats this as part of the work, like a new performance of the same score.

## 1. Sign In

1. Open the inku Web UI in your browser.
2. Enter your user name and password.
3. Press `Sign in`.

After signing in, use the left app rail to open settings, switch language, switch theme, edit your profile, or sign out.

## 2. Create Your First Image

1. Open the `description` tab.
2. Type a short prompt into the input box.
3. Optionally choose a canvas aspect, model selection, and color catalog.
4. Press `draw`.
5. When rendering finishes, the image appears on the canvas.

Start with what you notice or care about, rather than trying to specify every detail.

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

## 3. Prompt Writing Basics

For stable results, write one visual instruction per line.

Basic form:

```text
color + size + form + count + place + motion
```

Example:

```text
Fill the background with white.
Draw three thin blue lines from lower left to upper right.
Place three small red circles in the upper right.
```

Useful vocabulary:

| Type | Examples |
|---|---|
| forms | circle, ellipse, triangle, square, line, arc |
| colors | white, black, blue, red, green, gray |
| places | top, bottom, center, left edge, right edge, upper edge, lower edge, corner |
| motions | place, align, fill, scatter, draw |
| touches | pencil, pen, rotring, crayon, chalk, fine brush, thick brush, rope |
| continuity | solid, dashed, dotted, dot-dashed |
| movements | fine, broad, slow, quick, wobble, undulate, tremble, blur |

## 4. Use Saijiki

`Saijiki` is the inku vocabulary dictionary.

1. Press the `Saijiki` button.
2. Find the word you want to use.
3. Click a word to insert it at the cursor position.

Saijiki is intentionally not autocomplete. It is a dictionary you choose to consult when needed.

## 5. Check the Interpretation

After drawing, the `normalized DDL` area shows how inku interpreted your prompt.

- Input text: your original words
- Normalized DDL: the prompt rewritten into core drawing vocabulary
- JSON: the machine-readable score for the renderer
- Canvas: the SVG performance of that score

If the result is different from what you intended, inspect the interpretation first. Then rewrite the prompt with more specific place, count, form, material, or movement words.

## 6. Edit DDL Directly

1. After drawing, press `edit` in the DDL area.
2. Modify the DDL.
3. Press `done`.
4. Press `draw from DDL`.

Use this when the interpretation is close and you want to adjust only the drawing instructions.

## 7. Choose a Canvas Aspect

Use `canvas aspect` to render to non-square canvases.

| ID | Typical use |
|---|---|
| square | square |
| golden | golden ratio |
| a4 | A4 |
| b4 | B4 |
| wide | wide canvas |
| vertical | vertical canvas |
| byobu | folding-screen-like wide canvas |

Coordinates remain normalized from 0.0 to 1.0, so the writing style stays the same across aspect ratios.

## 8. Choose a Color Catalog

The color catalog maps abstract color words to concrete colors.

In prompts, write words such as `red`, `blue`, or `gray`. The server resolves those words to actual `#RRGGBB` values using the selected catalog. History records the selected catalog and resolved color map.

## 9. Export Images

After rendering, use `export`.

| Format | Use |
|---|---|
| Display SVG | Web display and PNG source |
| Editable SVG | Layered output for Illustrator / Affinity |
| Compatible SVG | General-purpose SVG transfer |
| PNG | Raster output at a selected size |

SVG is vector data, so it can be scaled for paper, screens, or wall-sized output.

## 10. Use History

Generated images are saved to history.

- Select previous images from the history strip.
- Mark important images with a star.
- Use history manager for search, starred filtering, trash, restore, and deletion.
- A history item includes the input, interpretation, JSON, SVG, models, color catalog, and canvas aspect.

The history database is the source of truth. Exported files are rebuildable artifacts.

## 11. Batch Generation

1. Open the `batch` tab.
2. Enter one prompt per line.
3. Optionally enable random color catalog selection for each render.
4. Press `draw`.

Example:

```text
A moon rises beyond the mountains
Mist spreads at night
Blue crayon lines drift in slow waves
```

During processing, the UI shows the active line, progress, elapsed time, token counts, and current interpretation.

## 12. Demo Mode

The `demo` tab repeatedly generates a short prompt from a seed phrase and draws it.

Settings:

| Setting | Meaning |
|---|---|
| Save to DB | Save demo outputs to history |
| Save files | Save SVG / JSON / PNG artifacts |
| Prompt model | Model used to create demo prompts |
| Seed phrase | Source phrase for prompt generation |
| Interval | Seconds before the next render |
| Random color catalog | Choose a different color catalog per render |

If you like a demo image, use `Save current drawing to DB` to add it to history.

## 13. Create Images from the CLI

The CLI uses the same API as the Web UI.

```sh
cd cli
uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
uv run inku-cli paint "A blue line slowly undulates from lower left to upper right" -o out --png --save-history
```

Batch from a text file:

```sh
uv run inku-cli batch -f prompts.txt -o out --png --continue-on-error
```

List history:

```sh
uv run inku-cli history --limit 20
```

## 14. Troubleshooting Image Creation

| Symptom | Action |
|---|---|
| The image differs from the intent | Check the interpretation and specify place, count, form, or material |
| The image is too plain | Add one material, movement, placement, or color instruction |
| Too many elements appear | Specify counts such as `three lines` or `twelve circles` |
| Generation is slow | Select a lighter model or wait for the provider queue |
| An error occurs | Shorten the prompt and split it into one instruction per line |

Physical and observable words are more stable than emotional evaluation words.

Avoid:

```text
Draw a beautiful, elegant, powerful image
```

Prefer:

```text
Place one black thick-brush line at the center.
Arrange seven gray circles around it with slight scatter.
```
