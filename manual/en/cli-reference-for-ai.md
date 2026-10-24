# inku-cli AI Autonomous Operation & Testing Reference

This document serves as a guideline for AI agents to operate the `inku-server` via command line and paint works autonomously, evaluate them visually, and refine them while tracking lineage nodes.

It covers inku v2.15.241 (Web Build 1317). The full flag list lives in the `inku-cli Reference`.

Future tests and comparisons that call a real provider use these models (two routes: ChatGPT plan and Gemini API (Cloud)). Exclude NVIDIA NIM from candidates, defaults, fallbacks, and Vision evaluation.

| Role | Connection and model | Explicit model reference |
|---|---|---|
| Primary | ChatGPT plan / GPT-6-Luna | `chatgpt:gpt-6-luna` |
| Secondary | Gemini API (Cloud) / Gemma 4 31B IT | `gemini:gemma-4-31b-it` |
| Vision | ChatGPT plan / GPT-6.1-Sol | `chatgpt:gpt-6.1-sol` |
| Vision | ChatGPT plan / GPT-6-Astra | `chatgpt:gpt-6-astra` |

The two Vision models are for tests that read pictures, such as Vision-assisted inspection of the exported pictures.

Before running, confirm the person's connection, published models, and available allowance. Follow the [connection guide](../../docs/guide/chatgpt-plan.md) for ChatGPT plan requirements. Secondary uses the Gemini API connection; do not substitute NIM's `google/`-prefixed ID or a local Gemma. Stop if an entry point cannot select the model explicitly or its connection fails; do not switch to NIM. Keep the description, seeds, and other comparison conditions fixed, and record the actual provider, model, and result.

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
uv run inku-cli paint "Draw one wave line with a thick black brush on white space." --stage1-model chatgpt:gpt-6-luna -o ./test_output --png --save-history
```
`--stage1-model` selects the shared Stage 1/2 model. Explicitly use `gemini:gemma-4-31b-it` when testing Secondary. Do not omit the selector and inherit a server or saved CLI default.

* **Expected Output (JSON)**:
  A JSON object representing the generated work's metadata.
  * `history_id`: `"d5989732-9f3a-4dd2-82df-c49c50761119"` (example)
  * `render_hash`: Unique rendering hash
  * `paths.json`, `paths.svg`, `paths.png`: Local paths for exported files
* **AI Decision Logic**: Extract the `"history_id"` and store it as the `PARENT_ID` variable.

### Step 3: Refine the Work
Refine one element of the work and attach the resulting work as a child node in the lineage tree.

```sh
# Refine the placement of PARENT_ID (e.g., d5989732-9f3a-4dd2-82df-c49c50761119)
uv run inku-cli refine perform PARENT_ID --kind layout -o ./test_output --png
```
* **Choosing the `--kind` parameter**:
  * `layout`: Reconstruct coordinates and size balance. It sets a new `composition_seed` and Stage 2 recomposes.
  * `color`: Apply a different color catalog (very fast; no LLM call).
* **Expected Output**: Without `-o`, a JSON object with the refined child work's metadata. With `-o DIR`, the command writes `refine-<kind>-<render_hash_short>.json` and `.svg` (and `.png` with `--png`) to DIR and prints a `Saved:` line instead of JSON.

`--kind` is recorded on the server as `derivation_kind`, in the same order: `layout_change` and `catalog_change`. Read that value when verifying a lineage edge. The touch (`touch`) and reading (`reading`) refinements were removed on 2026-10-14; edges made before then stay `touch_change` and `reinterpretation`.

### Step 4: Traverse and Verify the Lineage Tree
Verify that the newly generated child node is correctly connected to the parent node.

```sh
uv run inku-cli lineage show PARENT_ID
```
* **Expected Output (Hierarchical Tree View)**:
  ```text
  Work lineage:
  - (Root) dfced380 [Displayed] : Draw one wave line with a thick black brush on white space.
    - (layout_change) b91ae625  : Draw one wave line with a thick black brush on white space.
  ```
* **AI Decision Logic**: Parse the output to verify that a child node (e.g., `b91ae625`) is nested under the parent (e.g., `dfced380`) with the expected `derivation_kind` edge label.

### Step 5: Inspect the exported pictures and select a work
Compare the exported PNGs under the same viewing conditions. Check the description, composition, colours, omissions, and regressions, and record the selection reason. If Vision is also used, choose a Web/API entry point that explicitly selects a published Vision model (or the Primary or Secondary model), and confirm the actual connection and model.

`review evaluate` and `vision-review` are NIM-only product features. Do not run them in this testing and comparison procedure. Changing only `--model` to one of the references above does not change the destination. If no entry point can select the required model, record the visual inspection and stop.

---

## CLI Command Quick Reference for AI Agents

### 0.5 `plugin`

* **`plugin list`** — Returns loaded and rejected declarative plugin documents with namespace, version, and rejection reasons.
* **`plugin validate <FILE.inku-plugin.md>`** — Sends a local UTF-8 document body to the management API for validation without executing code or external files.
* **`plugin reload`** — Forces `server/plugins/` to reload without restarting the server.
* `plugin validate` and `plugin reload` require an administrator session (403 otherwise); `plugin list` requires only a signed-in session. Keep any plugin test artifacts together under one untracked `cli/out2/<build>-<version>-<benchmark>/` run directory.

### 0.6 `reference`

* **`reference [--md | --json] [-o FILE]`** — Fetches a machine-generated dump of the in-implementation vocabulary and constant tables. Markdown is the default; `--json` returns structured JSON; `-o` writes to a file.
* The output begins with APP_VERSION / BUILD_NUMBER / git short hash / generation time / the namespace, name, version, and status of each plugin package (rejected ones included).
* It covers eight sections (saijiki, normalized-DDL phrases, expansion layer, Score schema, color resolution, weight properties, performance, verification), all pulled from the implementation modules. It is a mirror that hardcodes no values and connects to no generation, acceptance, or coercion decision.
* Use it to attach one Markdown page at the start of a design or writing session. It runs on any logged-in session.

### 0.7 Beware the silent sender

**`paint` and `batch` paint under the server default for every flag you omit**, and the server default is not always the Web UI default. When comparing autonomous runs against Web UI results, state these three explicitly.

| Flag | Server default | Web UI default |
|---|---|---|
| `--sketch` | off | off |
| `--wild` | off | user setting, off by default |
| `--catalog-mode` | `fixed` | user setting |

```sh
uv run inku-cli paint "TEXT" --stage1-model chatgpt:gpt-6-luna --sketch --catalog-mode auto -o ./out --png
```

Variation is retired. Do not use the old amplitude or seed flags. Refinement has two operations: placement and color catalog (touch and reading were removed on 2026-10-14). Saved variation metadata remains a historical record and is never sent in new requests or saves. Pipeline work IDs and Score variation are separate contracts and are unchanged.

### 1. `lineage`
* **`lineage show <ITEM_ID> [--depth D] [--limit L] [--json]`**
  * Displays the parent-child derivation tree of the work.
  * Use `--json` to print the raw response, including all nodes and edges (each edge carries `parent_node_id` and `child_node_id`).
* **`lineage promote <NODE_ID>`**
  * Promotes a hidden intermediate work (`lineage_only` visibility) to standard history.

### 2. `refine`
* **`refine perform <ITEM_ID> --kind {layout|color} [-o DIR] [--png] [--no-save]`**
  * Draws an option from the target work's saved instructions (DDL), connects it to the parent, and saves it to history unless `--no-save` is given. The description is not read again (`layout` changes only the composition seed, `color` only the color catalog).
* **`refine save <PARENT_NODE_ID> --kind K --file SCORE_JSON --input-text T`**
  * Manually imports a Score JSON as a child node connected to a parent.

### 2.5 `colophon`

* **`colophon <ITEM_ID|NODE_ID> [--model M] [--language ja|en] [--dry-run] [--json] [-o FILE]`**
  * Reads one root-to-target branch sequentially through a vision-capable model and writes a first-person recitation.
  * By default it appends a signed record. `--dry-run` prints without saving.
  * This is an observational mirror, not an evaluation or selection command, and must not feed generation, refinement, or branch choice.

### 3. `inspect`
* **`inspect <TEXT> --models <MODEL_A,MODEL_B,...> -o DIR [--png]`**
  * Runs the LLM backends one after another (not in parallel) to inspect and compare DDL interpretations and drawings for the same input text. Each model serves both Stage 1 and Stage 2.
  * Use it to compare which LLM model produces the most expressive output.
  * Future comparisons use `--models chatgpt:gpt-6-luna,gemini:gemma-4-31b-it`. Do not include NIM.

### 4. `review`
* **`review evaluate <PNG_FILE> [--model M] [--prompt P]`**
  * This entry describes a NIM-only product feature. Do not use it for future tests, comparisons, or Vision evaluation.
* **`review unread <WORD> --context <CONTEXT>`**
  * Reports a failed vocabulary interpretation word to the server.
