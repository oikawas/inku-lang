# inku-cli AI Autonomous Operation & Testing Reference

This document serves as a guideline for AI agents to operate the `inku-server` via command line and paint works autonomously, evaluate them visually, and refine them while tracking lineage nodes.

It covers inku v2.13.8 (Web Build 893). The full flag list lives in the `inku-cli Reference`.

---

## AI Autonomous & Quality Improvement Workflow (Testing Procedure)

The standard operational procedure for an AI agent to refine a work step by step.

### Step 1: Establish Connection and Verify Session
Verify that the API server is reachable and inspect the permission groups of the current session.

```sh
uv run inku-cli me
```
* **Expected Output (JSON)**: A JSON object containing the user profile, with `permission_groups` as a list of names such as `["admins"]` or `["users"]`.
* **AI Decision Logic**: Connection is successful if the response contains `id` and `username`.

### Step 2: Paint the Initial Work (Root Node)
Paint the first work from a description (Shikishi text) and save it to the server history.

```sh
uv run inku-cli paint "Draw one wave line with a thick black brush on white space." -o ./test_output --png --save-history
```
* **Expected Output (JSON)**:
  A JSON object representing the generated work's metadata.
  * `history_id`: `"d5989732-9f3a-4dd2-82df-c49c50761119"` (example)
  * `render_hash`: Unique rendering hash
  * `paths.json`, `paths.svg`, `paths.png`: Local paths for exported files
* **AI Decision Logic**: Extract the `"history_id"` and store it as the `PARENT_ID` variable.

### Step 3: Make a Variation (Refinement)
Create a localized variation of the work and attach it as a child node in the lineage tree.

```sh
# Generate a layout variation for the PARENT_ID (e.g., d5989732-9f3a-4dd2-82df-c49c50761119)
uv run inku-cli refine perform PARENT_ID --kind layout -o ./test_output --png
```
* **Choosing the `--kind` parameter**:
  * `touch`: Refine only line textures and weights. It sets a new `render_seed` and inherits every other seed from the parent (very fast; no LLM call).
  * `layout`: Reconstruct coordinates and size balance. It sets a new `composition_seed` and Stage 2 recomposes.
  * `reading`: Read the description anew. It sets a new `interpretation_seed` and **Stage 1** interprets again.
  * `color`: Apply a different color catalog (very fast; no LLM call).
* **Expected Output**: A JSON object containing the refined child work's metadata.

`--kind` is recorded on the server as `derivation_kind`, in the same order: `touch_change`, `layout_change`, `reinterpretation`, and `catalog_change`. Read that value when verifying a lineage edge.

### Step 4: Traverse and Verify the Lineage Tree
Verify that the newly generated child node is correctly connected to the parent node.

```sh
uv run inku-cli lineage show PARENT_ID
```
* **Expected Output (Hierarchical Tree View)**:
  ```text
  Work lineage:
  - (Root) dfced380 [Displayed] : Draw one wave line with a thick black brush on white space.
    - (layout_variation) b91ae625  : Draw one wave line with a thick black brush on white space.
  ```
* **AI Decision Logic**: Parse the output to verify that a child node (e.g., `b91ae625`) is nested under the parent (e.g., `dfced380`) with the expected `derivation_kind` edge label.

### Step 5: Visual Evaluation (review) and Decision making
Send the exported child PNG to a Vision LLM to analyze the composition quality and aesthetic appeal.

```sh
uv run inku-cli review evaluate ./test_output/refine-layout-xxxx.png --model nvidia/neva-22b
```
* **Expected Output (JSON)**:
  ```json
  {
    "image": "refine-layout-xxxx.png",
    "model": "nvidia/neva-22b",
    "evaluation": "The drawing exhibits high color resonance... (evaluation review text)"
  }
  ```
* **AI Decision Logic**: Parse the feedback text. If the aesthetic score has improved, keep the node. If not, fallback to Step 3 and try another `--kind`, or backtrack to an older ancestor node in the tree (Lineage Fork).

---

## CLI Command Quick Reference for AI Agents

### 0.5 `plugin`

* **`plugin list`** — Returns loaded and rejected declarative plugin documents with namespace, version, and rejection reasons.
* **`plugin validate <FILE.inku-plugin.md>`** — Sends a local UTF-8 document body to the management API for validation without executing code or external files.
* **`plugin reload`** — Forces `server/plugins/` to reload without restarting the server.
* These commands require an administrator session. Keep any plugin test artifacts together under one untracked `cli/out2/<build>-<version>-<benchmark>/` run directory.

### 0.6 `reference`

* **`reference [--md | --json] [-o FILE]`** — Fetches a machine-generated dump of the in-implementation vocabulary and constant tables. Markdown is the default; `--json` returns structured JSON; `-o` writes to a file.
* The output begins with APP_VERSION / BUILD_NUMBER / git short hash / generation time / the namespace+version of each loaded plugin.
* It covers eight sections (saijiki, normalized-DDL phrases, expansion layer, Score schema, color resolution, weight properties, performance, verification), all pulled from the implementation modules. It is a mirror that hardcodes no values and connects to no generation, acceptance, or coercion decision.
* Use it to attach one Markdown page at the start of a design or writing session. It runs on any logged-in session.

### 0.7 `paint --trace` (RAW trace)

* **`paint <TEXT> --trace [-o DIR --prefix P]`** — Returns every pipeline layer's RAW intermediate in a single generation. It sends `include_trace` and saves the response `trace` as a separate `<prefix>-trace.json` in the output directory (independent of `--full-json`).
* The trace contains `stage1_raw` / `stage1_thinking` / `stage1_ddl` (before plugin expansion), `plugin_expanded_ddl`, `stage15_ddl` (the Stage 2 input), `stage2_raw_attempts` (every attempt including retry/fallback, with raw text and parse status), `score_pre_coerce`, and the coerce/plugin aggregates. It is a mirror for the intent-audit harness and benchmark precision; it changes no generation behavior.
* An older server without trace support is a warning, not an error. Without `include_trace`, the response is identical to the current one.

### 0.8 Beware the silent sender

**`paint` and `batch` paint under the server default for every flag you omit**, and the server default is not always the Web UI default. When comparing autonomous runs against Web UI results, state these three explicitly.

| Flag | Server default | Web UI default |
|---|---|---|
| `--sketch` / `--sketch-grain` | off | fine |
| `--wild` | off | user setting, off by default |
| `--catalog-mode` | `fixed` | user setting |

```sh
uv run inku-cli paint "TEXT" --sketch --sketch-grain fine --catalog-mode auto -o ./out --png
```

Variation takes effect **only when both** `--variation-amplitude` and `--variation-seed` are given. Passing one alone moves no axis of the expansion layer, and the response comes back under the defaults, so having passed a flag is not evidence it took effect. **Read the work's `variation` and `variation_seed` to confirm.**

### 1. `lineage`
* **`lineage show <ITEM_ID> [--depth D] [--limit L] [--json]`**
  * Displays the parent-child derivation tree of the work.
  * Use `--json` to retrieve raw connection details (`parent_node_id`, `child_node_id`).
* **`lineage promote <NODE_ID>`**
  * Promotes a hidden intermediate work (`lineage_only` visibility) to standard history.

### 2. `refine`
* **`refine perform <ITEM_ID> --kind {touch|layout|reading|color} [-o DIR] [--png] [--description TEXT]`**
  * Generates an option from the target work and connects it to the parent. `--description` replaces the description used for composition and reading refinements.
* **`refine save <PARENT_NODE_ID> --kind K --file SCORE_JSON --input-text T`**
  * Manually imports a Score JSON as a child node connected to a parent.

### 2.5 `colophon`

* **`colophon <ITEM_ID|NODE_ID> [--model M] [--language ja|en] [--dry-run] [--json] [-o FILE]`**
  * Reads one root-to-target branch sequentially through a vision-capable model and writes a first-person recitation.
  * By default it appends a signed record. `--dry-run` prints without saving.
  * This is an observational mirror, not an evaluation or selection command, and must not feed generation, refinement, or branch choice.

### 3. `inspect`
* **`inspect <TEXT> --models <MODEL_A,MODEL_B,...> -o DIR [--png]`**
  * Runs multiple LLM backends in parallel to inspect and compare DDL interpretations and drawings for the same input text.
  * Essential for the AI to dynamically select the best Stage 1 model.

### 4. `review`
* **`review evaluate <PNG_FILE> [--model M] [--prompt P]`**
  * Scores and reviews drawing composition aesthetics via Vision NIM.
* **`review unread <WORD> --context <CONTEXT>`**
  * Reports a failed vocabulary interpretation word to the server.
