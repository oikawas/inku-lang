# inku-cli Reference

inku-cli controls the same public HTTP API as the Web UI. It uses the stored session, while the server enforces the permissions that follow from the `users`, `leaders`, and `admins` groups.

It covers inku v2.15.147 (Web Build 1223).

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
| models | Configure the default drawing model (shared Stage 1/2), Vision model and color catalog |
| paint / batch | Paint one or many works from descriptions or instructions |
| refine | Refine an existing work's composition or color |
| lineage | Inspect lineage node trees and promote intermediate works |
| colophon | Recite one origin-to-target lineage branch as an append-only reading |
| inspect | Inspect and compare multiple inference models in parallel |
| review | Evaluate works with Vision and submit unread words |
| render-score | Render Score JSON without Stage 1 or Stage 2 |
| render-local | Render and compare Score offline with a chosen checkout's core; no server connection or DB save |
| demo-instruction | Write a demo description |
| history / history-export | List or export history by hash |
| unread-words | Show the user's ledger; administrators may use --all |
| contact-sheet / analyze / ddl-compare | Compare and analyze local artifacts |
| rasterize | Burn a folder of SVGs to PNG, one child process per file; `--workers` sets how many run at once |
| measure-raster | Count the raster measurements of a folder of PNGs (pixel count, ground color, the share of faint and strong marks, mean distance from the ground, saturated marks). **It counts the image it was handed, at the width it was handed, and declares no width or scale flag.** To read a record at another width, burn at that width with `rasterize --width` and count the result. It never contacts a server |
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
For limits they record the values used in `render_limits` and their origin in `render_limits_source` (`work` for the work's own row, `settings` for today's settings, `request` for this request, and `work_unrecorded` for a row that recorded no limits). Compatibility rendering, such as old-Score rendering, records notes of limits that took effect in `render_limit_notes`.

| Flag | Contents |
|---|---|
| `--file FILE` / `-f` | Read the description or DDL from a UTF-8 file; `-` means stdin for paint. For batch, each non-empty line is one work |
| `--out-dir DIR` / `-o` | Destination for JSON, SVG, and PNG output |
| `--prefix P` | Output filename prefix |
| `--png` | Also write PNG when `--out-dir` is set |
| `--svg-profile {display,editable,compat,live}` | SVG profile for saved files |
| `--input-mode {paint,ddl}` | `paint` sends the description through Stage 1; `ddl` starts from visible DDL and proceeds to compilation, any required hole completion, and performance. See SPEC for each stage's meaning |
| `--ddl-text DDL` | **`render-score` only.** Sends the instructions as provenance / hash metadata; it does not automatically repair counts or relations from DDL |
| `--ddl-file PATH` | **`render-score` only.** Reads the instructions from a file; `-` means stdin. Cannot be combined with `--ddl-text` |
| `--save-history` | Save to the server's history |
| `--save-artifacts` / `--no-save-artifacts` | Whether the server stores artifacts |
| `--full-json` | Print the full response |
| `--no-progress` | Disable the elapsed-time animation |

### Sketch from life (Stage 0.5)

| Flag | Contents |
|---|---|
| `--sketch` | Enable a sketch that adds place and light alongside the original description for interpretation. Both server and Web UI default to off. Current choices are off/on |
| `--sketch-grain {fine,coarse}` | Compatibility flag for old works; unused by the current sketch |
| `--sketch-text TEXT` | Use this sketch text instead of calling Stage 0.5, replaying a saved or hand-edited sketch |

Variation is retired. The old amplitude and seed flags are rejected. Saved variation metadata stays in the database and is never sent in a new drawing request.

### Performance and color

| Flag | Contents |
|---|---|
| `--wild` | Remove the stroke-amplitude ceiling; also effective with DDL input to `paint` / `batch` |
| `--color-catalog ID` | Server color catalog id |
| `--catalog-id ID` | Legacy alias for `--color-catalog` |
| `--catalog-mode {fixed,auto,random}` | `fixed` uses `--color-catalog`, `auto` lets the server read the description and pick, `random` draws one other than `--color-catalog` |
| `--from-work WORK_ID` | `render-score` only. **Draws in the colors and under the limits that work was drawn in** — the values recorded on the work's own row, not today's definition of its catalog and not today's settings. **A work whose catalog was renamed or retired still draws.** Cannot be combined with `--color-catalog` / `--catalog-id` |
| `--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}` | Canvas aspect ratio |

### Seeds and replay

| Flag | Contents |
|---|---|
| `--render-seed SEED` | Performance seed. The same seed and the same score give the same picture |
| `--composition-seed SEED` | Seed for where the marks are placed. Without it the placement follows `--render-seed` (render engine 23 onwards) |
| `--limits KEY=VALUE ...` | Set request limits for `paint` / `batch` (including `--input-mode ddl`) and `render-score`. Each element is capped at the server's current setting, so an administrator's ceiling cannot be exceeded. Omitted flags are not sent. See [Server Configuration §5.1](server-configuration.md#51-limits) for the four values used by the normal pipeline and the old compatibility values |

### Models and language

| Flag | Contents |
|---|---|
| `--stage1-provider` / `--stage1-model` | Provider and drawing model used for both stages |
| `--instruction-lang {auto,ja,en}` | Description language |
| `--ui-lang LANG` | The value recorded as the UI language |
| `--include-thinking` | Include the thinking output in the response |

batch additionally takes `--continue-on-error`.

For example, set the performance mode and request ceiling for DDL input:

```sh
uv run inku-cli paint --input-mode ddl --file work.ddl --stage1-model chatgpt:gpt-6-luna --wild --limits max_expanded_primitives=200
```

## Rendering without a server (render-local)

Render SVG and optional PNG with a chosen product checkout's core, or a git-archive containing the required source, without connecting to a server. Install the pinned Rust toolchain from `core/rust-toolchain.toml` and Cargo dependencies beforehand. Every invocation checks source freshness through an offline incremental build; missing dependencies stop the command rather than being fetched automatically.

```sh
# (a) Inherit saved conditions from one history-export item JSON
uv run inku-cli render-local --core-root /path/to/inku-lang \
  --from-work-file exported-work.json -o replay.svg --png replay.png
# (b) A standalone Score; supply saved colors, seeds, etc. when needed
uv run inku-cli render-local --core-root /path/to/inku-lang \
  --file score.json -o rendered.svg --color-map colors.json --render-seed 123
```

Both inputs require a current compiled Score with `resource_policy.hard_policy` and `resource_policy.operational_budget`; this is not a general migration command for old Scores. (a) inherits the work's color map, seeds, canvas, profile, wild setting, and limits, and compares bytes with its saved SVG when present. (b) uses core defaults for unspecified conditions. `--limits` accepts only the four replay ceilings and rejects values above the Score's saved hard policy. `--compare-svg FILE` adds another SVG byte comparison. JSON on stdout records hashes, timings, selected conditions, and checkout HEAD / dirty state, among other provenance. No DB save occurs. Equality across different source or conditions is not guaranteed.

## History and feedback

| Command | Main flags |
|---|---|
| `history` | `--limit` / `--offset` / `--query` / `--starred` / `--for-revision` / `--for-share` / `--no-svg` (leaves each work's drawing out of the listing; `svg` comes back empty) |
| `history-export` | `--from` / `--to` (a range of hash suffixes) / `--out-dir` / `--columns` / `--thumb-size` / `--starred` / `--for-revision` / `--for-share` |
| `unread-words` | `--all` (administrator-only aggregate) / `--limit` |
| `history share` | `--to-user` / `--to-group` (one or the other) / `--permission {read,write}` |
| `history unshare` | `--to-user` / `--to-group` (one or the other) |
| `history acl` | (the work ID only) shows who else may see or change that work |
| `history peers` | (no flags) lists the members of your own organisation group with their IDs |
| `history state` | `--bytes` (adds the byte count the response actually arrived in). Returns only the number of works and the newest work's timestamp and ID. **It reads no picture bytes at all**, so you can ask whether anything changed before re-fetching the listing |

`--for-revision` narrows to works carrying the revision mark. That mark is independent of the star.
`--for-share` narrows to the works their owner has opened to an organisation group. That mark is independent too, and the three can be combined.

    uv run inku-cli history share WORK_ID --to-user USER_ID --permission read
    uv run inku-cli history share WORK_ID --to-group GROUP_ID --permission write
    uv run inku-cli history unshare WORK_ID --to-user USER_ID
    uv run inku-cli history acl WORK_ID
    uv run inku-cli history peers

**Only the owner of a work and `admins` may share it. Being able to read a work is not
permission to hand it on.** A recipient is named by ID, and `history peers` is where to find one.
`--permission` defaults to `read`; `write` also lets the recipient star, trash and delete that work.
A work shared with you appears in your own history list, carrying a mark that says it is
somebody else's.

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
| `single-user show` | Show which account a single-user server opens as, and who else could |
| `single-user set USER_ID` | Move it to another account, which must hold `admins` |

`user` and `group` require a session in `admins` or `leaders`; `config` requires one in `admins`. `user create` takes the permission groups as `--permission-group {users,leaders,admins}`, which may be repeated. Existing limits, log retention policy, and DB backup settings are `config` subjects. Painting concurrency has no dedicated flags; use `api GET/PUT /api/settings/render-concurrency` as shown in [Server Configuration §2.3](server-configuration.md#23-artifacts-and-concurrency).

## Calling any public API

APIs without a dedicated command are reached through api. It accepts only relative paths under /api/... or /health and refuses forwarding to another host.

    uv run inku-cli api GET /api/color-catalogs
    uv run inku-cli api GET /api/history --query limit=20 --query starred=true
    uv run inku-cli api PATCH /api/auth/me/settings --data '{"ui_theme":"dark"}'
    uv run inku-cli api POST /api/history/trash --file ids.json
    uv run inku-cli api DELETE /api/history --header X-Inku-Confirm=permanent-delete-trash
    uv run inku-cli api GET /api/history/WORK_ID/svg --query profile=editable --output work.svg

--data and --file are mutually exclusive. Non-JSON responses can be written with --output. Endpoints that need no authentication accept --no-auth.

Permissions match the GUI. A member holding only `users` reaches their own works and settings **plus the works shared with them**; `leaders` manages the members of the same group and reaches **their own organisation's works**; `admins` reaches server settings, all users, the aggregate unread-word ledger, and **every work**. Calls outside the permission groups return 403, and calls without a session return 401. **A write naming a work you cannot see answers 404, or a count of zero, rather than 403** — a 403 would confirm that the work exists.

When retrying a write API, passing the same Idempotency-Key prevents a work and its lineage from being saved twice.

    uv run inku-cli api POST /api/history --file work.json --header Idempotency-Key=import-20260715-001

### Continuing after a 409 approval / author-edit response

When `paint` / `batch` returns 409 with `pipeline_patch_approval_required` or `pipeline_author_action_required`, inspect `detail.current_view` instead of submitting the generation again. The response identifies the target with `pipeline_variation_id` / `pipeline_execution_id`. Replace `VARIATION_ID`, `EXECUTION_ID`, and `REVISION` below with `variation_id`, `execution_id`, and `authority.revision` from that response or the latest view. Keep the revision as a decimal string.

```sh
uv run inku-cli api GET /api/pipeline/variations/VARIATION_ID
```

Act only after `busy` becomes false. For `phase.tag=awaiting_patch_approval`, read the current `document.source` and `phase.candidate.source` / `phase.patch`. Only if you accept it, copy `phase.proposal_digest` into `DIGEST` and submit:

```sh
uv run inku-cli api POST /api/pipeline/executions/EXECUTION_ID/commands \
  --data '{"tag":"approve_patch","expected_revision":"REVISION","proposal_digest":"DIGEST"}'
```

To decline and edit yourself, send `{"tag":"decline_patch","proposal_digest":"DIGEST"}` to the same endpoint, then read the latest view. To edit in `needs_user_edit` or a similar author-edit state, revise the full DDL from `document.source` when a document exists, or author the full DDL when it does not. Save the following as UTF-8 `author-ddl.json`:

```json
{"expected_revision":"REVISION","source":"complete revised DDL"}
```

```sh
uv run inku-cli api POST /api/pipeline/executions/EXECUTION_ID/author-ddl --file author-ddl.json
uv run inku-cli api GET /api/pipeline/variations/VARIATION_ID
```

If the edit response returns a new variation / execution, use those IDs from then on. Poll GET at intervals until `busy=false`, `phase.tag=score_ready`, and `delivery` is present before performing. Check the same conditions after approval too.

```sh
uv run inku-cli api POST /api/pipeline/executions/EXECUTION_ID/commands --data '{"tag":"perform"}'
uv run inku-cli api GET /api/pipeline/variations/VARIATION_ID
```

Poll until `busy=false` and `result` is present, then inspect the completed result. Return to the relevant steps if approval or editing is required again; stop for `failed` / `cancelled`. For a 409 `authority_conflict` / `stale_result`, reread `current_view` instead of resending an old revision or digest. Approval, editing, and performance operate on an execution belonging to the same signed-in user.


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
  uv run inku-cli refine perform WORK_ID --kind layout -o ./refinements --png
  ```
  `--kind` takes `layout` (composition) or `color` (color catalog); the option is painted and stored on the server. With `-o` it is also written locally. As in the web refinements, both draw from the work's saved instructions (DDL) and do not read the description again: `layout` chooses the instructions' ranges again under a new composition seed, and `color` draws the saved Score in another color catalog. A work whose DDL was edited is refined the same way. The work's `Sketch from life` prose is carried over as it is, without running the layer again. `--no-save` leaves the option unsaved.
* **Save a manual option into the lineage**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "the description"
  ```
  Imports a locally adjusted Score JSON straight into the server's history as a child attached to the given parent node.

### 3. Parallel model comparison (inspect)

Runs several models on the same description in parallel and compares how each interprets it as DDL and performs it.

Future real-provider tests and comparisons use ChatGPT plan / GPT-6-Luna as Primary and Gemini API (Cloud) / Gemma 4 31B IT as Secondary. Exclude NVIDIA NIM from targets, controls, fallbacks, and Vision evaluation. Follow the [AI testing procedure](cli-reference-for-ai.md) and stop on connection failure.

```sh
uv run inku-cli inspect "draw a blue line" --models "chatgpt:gpt-6-luna,gemini:gemma-4-31b-it" -o ./inspection --png
```

### 4. Visual evaluation and feedback (review)

Autonomous assessment by a Vision model, and reporting of words the interpreter could not read confidently.

* **Assess a work with Vision**:
  `review evaluate` and `vision-review` are NIM-only product features. The following example describes that feature; do not use it for future tests, comparisons, or Vision evaluation. Changing only `--model` to another provider's reference does not change the destination.
  ```sh
  uv run inku-cli review evaluate drawing.png --model VISION_MODEL
  ```
  Sends the rendered file to a Vision LLM and returns a score and a one-sentence assessment on margin, contrast, and expression. The provider's API key must be configured.
* **Report an unread word**:
  ```sh
  uv run inku-cli review unread "usuzumi" --context "draw a circle on a pale ink ground"
  ```
  Reports the word and its context into the server's unread-word ledger.
