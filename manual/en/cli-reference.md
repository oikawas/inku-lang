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
| inspect | Inspect and compare multiple inference models, one after another |
| review | Evaluate works with Vision and submit unread words |
| render-score | Render Score JSON without Stage 1 or Stage 2 |
| replay | Draw a saved work again with the current engine, compare it with the saved SVG, and optionally save it as a child (the web's `Replay`) |
| render-local | Render and compare Score offline with a chosen checkout's core; no server connection or DB save |
| demo-instruction | Write a demo description |
| history / history-export | List or export history by hash. `history show` / `history png` read one work by its UUID |
| unread-words | Show the user's ledger; administrators may use --all |
| contact-sheet / analyze / ddl-compare | Compare and analyze local artifacts (`analyze --replay` and `analyze --census --history` call the server's API) |
| rasterize | Burn a folder of SVGs to PNG, one child process per file; `--workers` sets how many run at once |
| measure-raster | Count the raster measurements of a folder of PNGs (pixel count, ground color, the share of faint and strong marks, mean distance from the ground, saturated marks). **It counts the image it was handed, at the width it was handed, and declares no width or scale flag.** To read a record at another width, burn at that width with `rasterize --width` and count the result. It never contacts a server |
| vision-review | Run the configured vision model as a read-only mirror |
| plugin | List, validate, and reload declarative DDL plugins |
| reference | Dump the implementation vocabulary and constant tables, read-only |
| user / group | Manage user accounts and groups |
| config | Show and update the server's system settings |
| api | Call any public API with an explicit HTTP method |
| ddl-export / export-card | Export a saved work's DDL, or write a shareable card (PNG) |
| version | Show CLI and server version and build information |

Commands that call the server accept `--base-url` (default http://127.0.0.1:8100) and `--timeout-seconds` (HTTP timeout in seconds, default 600).

### login and models flags

| Flag | Contents |
|---|---|
| `login --username` / `-u` | The user name to log in with. Required |
| `login --password` / `-p` | The password. If omitted, you are asked for it interactively |
| `models --vision-provider` | Save the default Vision provider. The choices are the same list as the other provider flags |

## Flags for paint and batch

paint and batch take the same flags, except that only paint draws from an image and takes `--full-json`. batch alone takes `--continue-on-error`, `--summary-json PATH` (default `OUT_DIR/analysis-summary.json`) and `--composition-count N`. **A flag you omit falls back to the server default, and the server default is not always the Web UI default.**

### Input and output

JSON artifacts record the version of the DDL layer that drew the work in `ddl_version` and `ddl_engine_version`.
For limits they record the values used in `render_limits` and their origin in `render_limits_source` (`work` for the work's own row, `settings` for today's settings, `request` for this request, and `work_unrecorded` for a row that recorded no limits). Compatibility rendering, such as old-Score rendering, records notes of limits that took effect in `render_limit_notes`.

| Flag | Contents |
|---|---|
| `--file FILE` / `-f` | Read the description or DDL from a UTF-8 file; `-` means stdin for both paint and batch. For batch, each non-empty line is one work |
| `--out-dir DIR` / `-o` | Destination for JSON, SVG, and PNG output |
| `--prefix P` | Output filename prefix |
| `--png` | Also write PNG when `--out-dir` is set |
| `--svg-profile {display,editable,compat,live}` | SVG profile for saved files |
| `--input-mode {paint,ddl}` | `paint` sends the description through Stage 1; `ddl` starts from visible DDL and proceeds to compilation, any required hole completion, and performance. See SPEC for each stage's meaning |
| `--ddl-text DDL` | **`render-score` only.** Sends the instructions as provenance / hash metadata; it does not automatically repair counts or relations from DDL |
| `--ddl-file PATH` | **`render-score` only.** Reads the instructions from a file; `-` means stdin. Cannot be combined with `--ddl-text` |
| `--save-history` | Add the drawing to the server's history database as a work. Without it no work is saved, though the drawing still counts toward the generation count. This holds for `--image` too |
| `--history-input TEXT` | The description shown as the work's input in history. It is not sent to the models; without it, the description itself is recorded |
| `--save-artifacts` / `--no-save-artifacts` | Whether the server stores artifacts |
| `--full-json` | Print the full response |
| `--no-progress` | Disable the elapsed-time animation |

### Drawing from an image (paint only)

| Flag | Contents |
|---|---|
| `--image PATH` | Draw from this image instead of a description, as the web image tab does. The Vision model writes the DDL in Japanese, and the paper follows the image unless `--canvas-aspect` names one. The server keeps the image in memory for the run and never saves it |
| `--provenance TEXT` | The image's source note. It is kept with the work apart from the description and never sent to the models |
| `--provenance-file PATH` | Read the source note from a UTF-8 file; `-` means stdin |
| `--vision-model MODEL` | The Vision model that writes the DDL. Defaults to the one saved with `models --vision-model` |

With `--image`, the description, `--input-mode`, the sketch flags, `--wild`, `--stage1-provider` / `--stage1-model` and `--include-thinking` are refused. The color catalog, seeds, `--limits`, `--out-dir`, `--png` and `--save-history` work as for a description.

```sh
uv run inku-cli paint --image photo.jpg --provenance "Taken by the Kamo River, Kyoto, October 2026" --vision-model chatgpt:gpt-6-luna --save-history -o ./out --png
```

### Sketch from life (Stage 0.5)

| Flag | Contents |
|---|---|
| `--sketch` | Enable a sketch that adds place and light alongside the original description for interpretation. Both server and Web UI default to off. Current choices are off/on |
| `--sketch-grain {fine,coarse}` | Compatibility flag for old works; unused by the current sketch |
| `--sketch-text TEXT` | Use this sketch text instead of calling Stage 0.5, replaying a saved or hand-edited sketch |
| `--route {stages,read_and_draw}` | How the description is drawn: `stages` (the current stages, the default) or `read_and_draw` (read from the speaker's eye, written as DDL and corrected once beside its drawing). With read and draw, `--sketch` passes through the reading and `--sketch-text` is an edited reading |
| `--composition {off,on}` | With `--route read_and_draw` only: `on` first decides a composition and laws from the description (and its reading), then writes, measures, and corrects the DDL toward them, and chooses its colors before the commit; `off` (the default) draws read and draw as before |

Variation is retired. The old amplitude and seed flags are rejected. Saved variation metadata stays in the database and is never sent in a new drawing request.

### Performance and color

| Flag | Contents |
|---|---|
| `--wild` | Remove the stroke-amplitude ceiling; also effective with DDL input to `paint` / `batch` |
| `--color-catalog ID` | Server color catalog id |
| `--catalog-id ID` | Legacy alias for `--color-catalog` |
| `--catalog-mode {fixed,auto,random}` | `fixed` uses `--color-catalog`, `auto` lets the server read the description and pick, `random` draws one other than `--color-catalog` |
| `--from-work WORK_ID` | `render-score` only. **Draws in the colors and under the limits that work was drawn in** — the values recorded on the work's own row, not today's definition of its catalog and not today's settings. **A work whose catalog was renamed or retired still draws.** Cannot be combined with `--color-catalog` / `--catalog-id` |
| `--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical,sd_monitor,hd_monitor}` | Canvas aspect ratio |

### Seeds and replay

| Flag | Contents |
|---|---|
| `--render-seed SEED` | Performance seed. The same seed and the same score give the same picture |
| `--composition-seed SEED` | Seed for where the marks are placed. Without it the placement follows `--render-seed` (render engine 23 onwards) |
| `--limits KEY=VALUE ...` | Set request limits for `paint` / `batch` (including `--input-mode ddl`) and `render-score`. Each element is capped at the server's current setting, so an administrator's ceiling cannot be exceeded. Omitted flags are not sent. See [Server Configuration §5.1](server-configuration.md#51-limits) for the four values used by the normal pipeline and the old compatibility values |

### Models and language

| Flag | Contents |
|---|---|
| `--stage1-provider` / `--stage1-model` | The drawing model, written as `provider:model` (for example `chatgpt:gpt-6-luna`), used for both stages. `--stage1-provider` is only shown in the run summary and is not sent |
| `--instruction-lang {auto,ja,en}` | Description language |
| `--ui-lang LANG` | The value recorded as the UI language |
| `--include-thinking` | Accepted for compatibility only; the server always returns `thinking` as null |

batch additionally takes `--continue-on-error`, `--summary-json PATH`, and `--composition-count N`.

For example, set the performance mode and request ceiling for DDL input:

```sh
uv run inku-cli paint --input-mode ddl --file work.ddl --stage1-model chatgpt:gpt-6-luna --wild --limits max_expanded_primitives=200
```

### batch flags

| Flag | Contents |
|---|---|
| `--composition-count N` | Draw each description N times with different placements. With N of 2 or more, the placement seeds are 0 to N-1, `--composition-seed` is not used, and `-vSEED` is added to the output file names. With N of 1 (the default), `--composition-seed` applies as usual |
| `--summary-json PATH` | Write the batch summary (counts, each work's result, and failures) to this path as JSON; the same JSON is also printed to stdout. Without it, and with `--out-dir`, the file is OUT_DIR/analysis-summary.json |

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

| Flag | Contents |
|---|---|
| `--canvas-height PX` | Canvas height in pixels; the width follows from the chosen aspect. When omitted: with `--from-work-file` and no `--canvas-aspect`, the saved SVG's size; otherwise the selected checkout's base height (1000 in the current source). Giving `--canvas-aspect` also stops the saved SVG's size from being inherited |
| `--wild` / `--no-wild` | Remove / keep the stroke-amplitude ceiling. When omitted: with `--from-work-file`, the work's record; with `--file`, off |

Both inputs require a current compiled Score with `resource_policy.hard_policy` and `resource_policy.operational_budget`; this is not a general migration command for old Scores. (a) inherits the work's color map, seeds, canvas, profile, wild setting, and limits, and compares bytes with its saved SVG when present. (b) uses core defaults for unspecified conditions. `--limits` accepts only the four replay ceilings and rejects values above the Score's saved hard policy. `--compare-svg FILE` adds another SVG byte comparison. JSON on stdout records hashes, timings, selected conditions, and checkout HEAD / dirty state, among other provenance. No DB save occurs. Equality across different source or conditions is not guaranteed.

## Replaying a saved work (replay)

Like the web's `Replay`, this draws a saved work's saved Score under its recorded conditions (render seed, placement seed, colors, canvas, wild, limits) with the server's current engine. The CLI sends no seed, colors or canvas of its own. An old work that recorded no render seed is drawn with the provisional seed 0, and the output's `provisional_render_seed` is `true`.

```sh
# Compare only (nothing is saved); write the saved SVG and the replay
uv run inku-cli replay WORK_ID --out-dir replay-out --png
# Save the replay as the work's child (the web's "save the redraw as a child"; no generation is counted)
uv run inku-cli replay WORK_ID --save-child
```

The JSON on standard output records the engine versions at saving and now (`recorded_render_engine_version`, `render_engine_version`, `version_changed`), the `render_hash`, the SHA-256 of the replay and of the saved SVG, and whether the two are byte-identical (`svg_equal`). With `--save-child` the server draws the work once more and saves the child only when that matches the replay shown, returning its `child_id`; otherwise it answers 409 and saves nothing.

## Analyzing and comparing artifacts (analyze, contact-sheet)

| Flag | Contents |
|---|---|
| `analyze --diversity` | Compute diversity metrics and write INPUT_DIR/diversity-summary.json; `-o` changes the destination |
| `analyze --census` | Report frequent mechanical motif signatures with thumbnail examples; written to INPUT_DIR/motif-census.json (`-o` changes it) |
| `analyze --census --history` | Use the logged-in user's history instead of INPUT_DIR; cannot be combined with INPUT_DIR. `--history` is used together with `--census` |
| `analyze --replay N` | Used with `--diversity`. When N is 2 or more, each sampled score is drawn 2N times: N composition seeds with the render seed fixed, and N render seeds with the composition seed fixed. Calls the server's API. N of 1 or less draws nothing |
| `analyze --replay-limit M` | The maximum number of scores to replay (default 5, minimum 1), taken from the head of the loaded works |
| `contact-sheet --order {name,similarity}` | The order. `name` (default) sorts by file name. `similarity` places each image next to the one with the closest composition, reading the Score JSON in the folder |

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
| `history show WORK_ID` | `--part {all,description,ddl,score}`. Prints the work's description (the author's own words), DDL and JSON Score. The default `all` prints `id`, `at`, `description`, `ddl` and `score` as one JSON object; `description` and `ddl` print that text alone, and `score` prints the JSON Score alone |
| `history png WORK_ID` | `--out` / `-o` (required; a path ending in `/`, or an existing directory, gets `<UUID>.png` inside it) / `--size` (pixels on the longer side, at least 64, default 1024). Rasterizes the saved display SVG into a PNG of the drawing alone, for showing a work to an AI |

`WORK_ID` is the work's UUID. The `#` copy buttons on the web canvas and in the library copy it, and the history preview shows its first eight characters. Its first few characters are enough; when they fit more than one work, the command stops and lists the candidates. Unlike the hash, no two works share a UUID and it never changes after the work is saved.

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

### Exporting a work (ddl-export, export-card)

| Flag | Contents |
|---|---|
| `ddl-export WORK_ID --output` / `-o` | The file to write. Without it, the export goes to standard output. The output is JSON with the schema `inku.ddl-export.v1`, containing the work's DDL and the plugin definitions that DDL names |
| `export-card HASH --out` / `-o` | The destination PNG path. A path ending in `/`, or an existing directory, receives the file as `inku-card-<the work's short hash>-<layout>.png`. Any other path is written as the PNG file itself. Required |
| `export-card --layout {square,portrait}` | `square` is a 1080×1080 sheet; `portrait` is 1080×1350 |
| `export-card --no-seal` | Leave off the small `inku` mark printed on the sheet. By default it is printed |

`HASH` is the last four or more characters of the work's history hash.

    uv run inku-cli ddl-export WORK_ID -o work.ddl.json
    uv run inku-cli paint --input-mode ddl --file work.ddl.json
    uv run inku-cli export-card HASH -o ./cards/ --layout portrait

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

`user` requires a session in `admins` or `leaders`. `group list` is open to both; `group create`, `group update` and `group delete` need `admins`. `config` requires one in `admins`. `user create` takes the permission groups as `--permission-group {users,leaders,admins}`, which may be repeated. Existing limits, log retention policy, and DB backup settings are `config` subjects. Painting concurrency has no dedicated flags; set it with `api PUT /api/settings/render-concurrency` and read the `render_concurrency` field of `api GET /api/settings/status` (see [Server Configuration §2.3](server-configuration.md#23-artifacts-and-concurrency)).

### user flags

| Flag | Contents |
|---|---|
| `user create --group-id ID` | Put the new account into a user group |
| `user update --username` | Change the user name |
| `user update --email` | Change the email address |
| `user update --password` | Change the password |
| `user update --group-id ID` | Change the user group the account belongs to |
| `user delete --cascade` | Also delete the account's generation history. Without it, an account that has history is not deleted, and the server answers 409 |

### config update flags

Of the nine render limits, the four current ones (`max_expanded_primitives`, `max_expanded_per_instruction`, `max_instructions`, `schema_count_max`) are enforced as ceilings on the work. The other five (`literal_count_threshold`, `represented_count_min`, `represented_count_max`, `ddl_count_max`, `ddl_count_max_grid`) are legacy values kept for saved works, and they do not rewrite counts.

| Flag | Contents |
|---|---|
| `--google-auth true\|false` | Stores the Google sign-in switch only; nothing signs in through it yet. Omitted, it is left unchanged |
| `--local-auth true\|false` | Local sign-in cannot be turned off, so only `true` is accepted. `false` is refused with 409. Omitted, it is left unchanged |
| `--backup-interval N` | The interval between automatic DB backups, in days. Omitted, it is left unchanged. [Server Configuration §8](server-configuration.md#8-backup-and-recovery) |
| `--backup-generations N` | The number of automatic DB backup generations to keep. Each time a new automatic backup is made, older ones beyond this count are deleted |
| `--log-retention-days N` | The number of days logs are kept. [Server Configuration §9](server-configuration.md#9-logs) |
| `--log-retention-enabled true\|false` | Enable or disable log retention |
| `--log-compress true\|false` | Compress log files |
| `--limit-max-expanded-primitives N` | The maximum number of primitive marks per work. When a work would exceed it, the server draws its largest groups in represented (reduced-mark) form. It is a compiler resource ceiling, and the DDL text is not changed |
| `--limit-max-expanded-per-instruction N` | The maximum number of primitive marks per template. It applies inside the per-work ceiling |
| `--limit-max-instructions N` | The maximum number of object templates per work. A compiler resource ceiling |
| `--limit-literal-count-threshold N` | A legacy value. The current pipeline does not replace counts with bands |
| `--limit-represented-count-min N` | A legacy value, kept for saved works |
| `--limit-represented-count-max N` | A legacy value. It is normalized against the literal count threshold |
| `--limit-ddl-count-max N` | A legacy value. The current pipeline does not rewrite counts with it |
| `--limit-ddl-count-max-grid N` | A legacy value, kept for saved works |
| `--limit-schema-count-max N` | The maximum resolved count in the compiler resource policy. It does not clamp numbers the author wrote |
| `--limits-reset` | Put every render limit back to its default. Other `--limit-*` flags are ignored |

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
  `--kind` takes `layout` (composition) or `color` (color catalog); the option is painted and stored on the server. With `-o` it is also written locally. As in the web refinements, both draw from the work's saved instructions (DDL) and do not read the description again: `layout` chooses the instructions' ranges again under a new composition seed, and `color` draws the saved Score in another color catalog. A work whose DDL was edited is refined the same way. The work's `Sketch from life` prose is carried over as it is, without running the layer again. `--no-save` leaves the option unsaved. `refine generate` is an alias of `refine perform` with the same arguments and behavior, kept for compatibility; `refine --help` does not list it.
* **Save a manual option into the lineage**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "the description"
  ```
  Imports a locally adjusted Score JSON straight into the server's history as a child attached to the given parent node. `--svg-file` attaches an SVG (omitted, the SVG is saved empty). `--visibility lineage_only` keeps the work out of normal history and places it in the lineage only (the default is `normal`).

### 3. Model comparison (inspect)

Runs several models on the same description one after another and compares how each interprets it as DDL and performs it.

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
  Sends the rendered image to the Vision model and returns a 0–100 score for color harmony, composition balance, negative space pressure, and overall visual eventfulness, together with a one-sentence summary. It needs the `NVIDIA_API_KEY` (or `NVIDIA_NIM_API_KEY`) environment variable. Without a Vision setting it uses `nvidia/neva-22b`. `--prompt` replaces the default evaluation prompt with the given text.
* **Report an unread word**:
  ```sh
  uv run inku-cli review unread "usuzumi" --context "draw a circle on a pale ink ground"
  ```
  Reports the word and its context into the server's unread-word ledger.
