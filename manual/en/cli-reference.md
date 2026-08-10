# inku-cli Reference

inku-cli controls the same public HTTP API as the Web UI. It uses the stored session, while the server enforces the permissions of regular users, group leads, and administrators.

It covers inku v2.11.20 (Web Build 876).

## Basics

    cd cli
    uv run inku-cli --help
    uv run inku-cli login --base-url http://127.0.0.1:8100 -u USERNAME
    uv run inku-cli me
    uv run inku-cli version

Run inku-cli COMMAND --help for the complete option list. This document states what each command is for, and the flags whose relation to the Web UI is not obvious.

| Command | Purpose |
|---|---|
| login / logout / me | Start, discard, and inspect a session |
| models | Configure default Stage 1, Stage 2, and Vision models and the color catalog |
| paint / batch | Paint one or many works from descriptions or instructions |
| refine | Refine an existing work's touch, composition, reading, or color |
| lineage | Inspect lineage node trees and promote intermediate works |
| colophon | Recite one origin-to-target lineage branch as an append-only reading |
| inspect | Inspect and compare multiple inference models in parallel |
| review | Evaluate works with Vision and submit unread words |
| render-score | Render Score JSON without Stage 1 or Stage 2 |
| demo-instruction | Write a demo description |
| history / history-export | List or export history by hash |
| unread-words | Show the user's ledger; administrators may use --all |
| contact-sheet / analyze / ddl-compare | Compare and analyze local artifacts |
| rasterize | Burn a folder of SVGs to PNG, one child process per file; `--workers` sets how many run at once |
| vision-review | Run the configured vision model as a read-only mirror |
| plugin | List, validate, and reload declarative DDL plugins |
| reference | Dump the implementation vocabulary and constant tables, read-only |
| user / group | Manage user accounts and groups |
| config | Show and update the server's system settings |
| api | Call any public API with an explicit HTTP method |
| version | Show CLI and server version and build information |

## Flags for paint and batch

paint and batch take the same flags. **A flag you omit falls back to the server default, and the server default is not always the Web UI default.**

### Input and output

JSON artifacts record the version of the DDL layer that drew the work in `ddl_version` and `ddl_engine_version`.

| Flag | Contents |
|---|---|
| `--file FILE` / `-f` | Read the description from a UTF-8 file; `-` means stdin for paint. For batch, each non-empty line is one work |
| `--out-dir DIR` / `-o` | Destination for JSON, SVG, and PNG output |
| `--prefix P` | Output filename prefix |
| `--png` | Also write PNG when `--out-dir` is set |
| `--svg-profile {display,editable,compat}` | SVG profile for saved files |
| `--input-mode {paint,ddl}` | `paint` sends prose through Stage 1; `ddl` sends instructions straight to Stage 2 and the performance |
| `--ddl-text DDL` | **`render-score` only.** Hands the instructions to coerce, so the instruction-driven repairs run as they do in paint (a stated count or relation reaches the picture). **Omit it and those repairs stay off, as before** |
| `--ddl-file PATH` | **`render-score` only.** Reads the instructions from a file; `-` means stdin. Cannot be combined with `--ddl-text` |
| `--save-history` | Save to the server's history |
| `--save-artifacts` / `--no-save-artifacts` | Whether the server stores artifacts |
| `--full-json` | Print the full response |
| `--no-progress` | Disable the elapsed-time animation |

### Sketch from life (Stage 0.5)

| Flag | Contents |
|---|---|
| `--sketch` | Send the description through the sketch-from-life layer before interpretation. **The server default is off; the Web UI default is fine** |
| `--sketch-grain {fine,coarse}` | The grain. `fine` is the server default |
| `--sketch-text TEXT` | Use this sketch text instead of calling Stage 0.5, replaying a saved or hand-edited sketch |

### Variation (Stage 1.5)

| Flag | Contents |
|---|---|
| `--variation-amplitude {small,medium,large}` | How far the variation layer moves the expansion axes |
| `--variation-seed SEED` | Which axes move, and in which direction |

**Variation takes effect only when both flags are given.** Either one alone moves nothing.

### Performance and color

| Flag | Contents |
|---|---|
| `--wild` | Remove the stroke limit |
| `--color-catalog ID` | Server color catalog id |
| `--catalog-id ID` | Legacy alias for `--color-catalog` |
| `--catalog-mode {fixed,auto,random}` | `fixed` uses `--color-catalog`, `auto` lets the server read the description and pick, `random` draws one other than `--color-catalog` |
| `--from-work WORK_ID` | `render-score` only. **Draws in the colors that work was drawn in** — the colors recorded on the work's own row, not today's definition of its catalog. **A work whose catalog was renamed or retired still draws.** Cannot be combined with `--color-catalog` / `--catalog-id` |
| `--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}` | Canvas aspect ratio |

### Seeds and replay

| Flag | Contents |
|---|---|
| `--render-seed SEED` | Performance seed. The same seed and the same score give the same picture |
| `--composition-seed SEED` | Seed for where the marks are placed. Without it the placement follows `--render-seed` (render engine 23 onwards) |
| `--seed-text TEXT` | Text used only to derive the performance seed; the counterpart of `Another performance` in the Web UI |
| `--interpretation-seed ID` | Ask Stage 1 for an explicit re-interpretation under this identifier instead of reusing the previous reading |

### Models and language

| Flag | Contents |
|---|---|
| `--stage1-provider` / `--stage1-model` | Provider and model for Stage 1, interpretation |
| `--stage2-provider` / `--stage2-model` | Provider and model for Stage 2, structuring |
| `--instruction-lang {auto,ja,en}` | Description language |
| `--ui-lang LANG` | The value recorded as the UI language |
| `--include-thinking` | Include the thinking output in the response |

### Observation

| Flag | Contents |
|---|---|
| `--trace` | Request the RAW per-layer intermediates and save them as `<prefix>-trace.json` |

batch additionally takes `--continue-on-error`.

## History and feedback

| Command | Main flags |
|---|---|
| `history` | `--limit` / `--offset` / `--query` / `--starred` / `--for-revision` |
| `history-export` | `--from` / `--to` (a range of hash suffixes) / `--out-dir` / `--columns` / `--thumb-size` / `--starred` / `--for-revision` |
| `unread-words` | `--all` (administrator-only aggregate) / `--limit` |

`--for-revision` narrows to works carrying the revision mark. That mark is independent of the star.

## Plugins and reference

| Command | Contents |
|---|---|
| `plugin list` | Report loaded and rejected plugin documents, namespaces, versions, and rejection reasons as JSON |
| `plugin validate FILE` | Send a local document body to the administration API and validate its syntax without executing code or external files |
| `plugin reload` | Reload `server/plugins/` explicitly, without restarting the server |
| `reference [--md \| --json] [-o FILE]` | A machine-generated dump of the implementation vocabulary and constant tables. Markdown by default |

`plugin` requires an administrator session. `reference` runs under any signed-in session.

## Colophon

    uv run inku-cli colophon ITEM_ID --language en --dry-run

A vision-capable model reads one branch, from the origin to the target work, in the first person and in generation order. By default the signed colophon is appended and stored; `--dry-run` prints to stdout without saving. `--vision-model` chooses the reader (`--model` is the legacy alias).

The colophon is neither an evaluation nor a selection command. It must not be connected to painting, refinement, or branch choice.

## Administration

| Command | Contents |
|---|---|
| `user list / create / update / delete` | Manage user accounts |
| `group list / create / update / delete` | Manage user groups |
| `config show` | Show the server's system settings |
| `config update` | Update the server's system settings |

`user` and `group` require an administrator or group lead session; `config` requires an administrator. Limits, painting concurrency, the log retention policy, and DB backup settings are all `config` subjects. See `Server Configuration` for what the values mean.

## Calling any public API

APIs without a dedicated command are reached through api. It accepts only relative paths under /api/... or /health and refuses forwarding to another host.

    uv run inku-cli api GET /api/color-catalogs
    uv run inku-cli api GET /api/history --query limit=20 --query starred=true
    uv run inku-cli api PATCH /api/auth/me/settings --data '{"ui_theme":"dark"}'
    uv run inku-cli api POST /api/history/trash --file ids.json
    uv run inku-cli api DELETE /api/history --header X-Inku-Confirm=permanent-delete-trash
    uv run inku-cli api GET /api/history/WORK_ID/svg --query profile=editable --output work.svg

--data and --file are mutually exclusive. Non-JSON responses can be written with --output. Endpoints that need no authentication accept --no-auth.

Permissions match the GUI. A regular user reaches only their own works and settings; a group lead manages regular users in the same group; an administrator reaches server settings, all users, and the aggregate unread-word ledger. Calls outside a role return 403, and calls without a session return 401.

When retrying a write API, passing the same Idempotency-Key prevents a work and its lineage from being saved twice.

    uv run inku-cli api POST /api/history --file work.json --header Idempotency-Key=import-20260715-001


## Commands for autonomous operation and quality improvement

These commands serve automated painting, evaluation, and the autonomous refinement loop that walks the lineage tree. The procedure itself lives in `inku-cli Reference for AI Autonomous Operation and Testing`.

### 1. Lineage

Show a work's derivation tree, or promote an intermediate work into ordinary history.

* **Show the lineage tree**:
  ```sh
  uv run inku-cli lineage show WORK_ID --depth 3
  ```
  Prints the parent and child relations around the given work id as a text tree. `--json` prints the raw JSON instead.
* **Promote an intermediate work**:
  ```sh
  uv run inku-cli lineage promote NODE_ID
  ```
  Promotes a `lineage_only` node, created by temporary refinement and hidden from ordinary history, into the user's ordinary history.

### 2. Refinement and derived works

Attach an existing work as the parent node and produce a local option, saved into the lineage.

* **Generate a refinement option**:
  ```sh
  uv run inku-cli refine perform WORK_ID --kind touch -o ./refinements --png
  ```
  `--kind` takes `touch`, `layout` (composition), `reading` (interpretation), or `color` (color catalog); the option is painted and stored on the server. With `-o` it is also written locally. `--description` replaces the description used for composition and reading refinements.
* **Save a manual option into the lineage**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "the description"
  ```
  Imports a locally adjusted Score JSON straight into the server's history as a child attached to the given parent node.

### 3. Parallel model comparison (inspect)

Runs several models on the same description in parallel and compares how each interprets it as DDL and performs it.

```sh
uv run inku-cli inspect "draw a blue line" --models "MODEL_A,MODEL_B" -o ./inspection --png
```

### 4. Visual evaluation and feedback (review)

Autonomous assessment by a Vision model, and reporting of words the interpreter could not read confidently.

* **Assess a work with Vision**:
  ```sh
  uv run inku-cli review evaluate drawing.png --model VISION_MODEL
  ```
  Sends the rendered file to a Vision LLM and returns a score and a one-sentence assessment on margin, contrast, and expression. The provider's API key must be configured.
* **Report an unread word**:
  ```sh
  uv run inku-cli review unread "usuzumi" --context "draw a circle on a pale ink ground"
  ```
  Reports the word and its context into the server's unread-word ledger.
