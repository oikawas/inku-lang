# inku-cli AI Autonomous Operation & Testing Reference

This document serves as a guideline for AI agents (e.g., Codex, Antigravity) to operate the `inku-server` via command line and perform autonomous artwork generation, visual evaluation, and refinement (Vary/Refine) while tracking lineage nodes.

---

## AI Autonomous & Quality Improvement Workflow (Testing Procedure)

The standard operational procedure for an AI agent to gradually refine and improve artwork.

### Step 1: Establish Connection and Verify Session
Verify that the API server is reachable and inspect the current user's session role.

```sh
uv run inku-cli me
```
* **Expected Output (JSON)**: A JSON object containing the user profile, e.g., role `admin` or `user`.
* **AI Decision Logic**: Connection is successful if the response contains `id` and `username`.

### Step 2: Generate Initial Artwork (Root Node)
Generate the first artwork using a prompt (Shikishi text) and save it to the server history.

```sh
uv run inku-cli paint "Draw one wave line with a thick black brush on white space." -o ./test_output --png --save-history
```
* **Expected Output (JSON)**:
  A JSON object representing the generated artwork's metadata.
  * `history_id`: `"d5989732-9f3a-4dd2-82df-c49c50761119"` (example)
  * `render_hash`: Unique rendering hash
  * `paths.json`, `paths.svg`, `paths.png`: Local paths for exported files
* **AI Decision Logic**: Extract the `"history_id"` and store it as the `PARENT_ID` variable.

### Step 3: Generate a Variation (Refinement)
Create a localized variation of the artwork and attach it as a child node in the lineage tree.

```sh
# Generate a layout variation for the PARENT_ID (e.g., d5989732-9f3a-4dd2-82df-c49c50761119)
uv run inku-cli refine generate PARENT_ID --kind layout -o ./test_output --png
```
* **Choosing the `--kind` parameter**:
  * `touch`: Refine only line textures and weights (very fast; no LLM call).
  * `layout`: Reconstruct coordinates and size balance (Stage 2 LLM reconstruction).
  * `reading`: Re-interpret the original prompt text (Stage 1.5 LLM re-interpretation).
  * `color`: Apply a different color catalog (very fast; no LLM call).
* **Expected Output**: A JSON object containing the refined child artwork's metadata.

### Step 4: Traverse and Verify the Lineage Tree
Verify that the newly generated child node is correctly connected to the parent node.

```sh
uv run inku-cli lineage show PARENT_ID
```
* **Expected Output (Hierarchical Tree View)**:
  ```text
  Artwork Lineage:
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

### 1. `lineage`
* **`lineage show <ITEM_ID> [--depth D] [--limit L] [--json]`**
  * Displays the parent-child derivation tree of the work.
  * Use `--json` to retrieve raw connection details (`parent_node_id`, `child_node_id`).
* **`lineage promote <NODE_ID>`**
  * Promotes a hidden intermediate work (`lineage_only` visibility) to standard history.

### 2. `refine`
* **`refine generate <ITEM_ID> --kind {touch|layout|reading|color} [-o DIR] [--png]`**
  * Generates a variation of the target work and connects it to the parent.
* **`refine save <PARENT_NODE_ID> --kind K --file SCORE_JSON --input-text T`**
  * Manually imports a Score JSON as a child node connected to a parent.

### 2.5 `okugaki`

* **`okugaki <ITEM_ID|NODE_ID> [--model M] [--language ja|en] [--dry-run] [--json] [-o FILE]`**
  * Reads one root-to-target branch sequentially through a vision-capable model and writes a first-person recitation.
  * By default it appends a signed record. `--dry-run` prints without saving.
  * This is an observational mirror, not an evaluation or selection command, and must not feed generation, refinement, or branch choice.

### 3. `inspect`
* **`inspect <TEXT> --models <MODEL_A,MODEL_B,...> -o DIR [--png]`**
  * Runs multiple LLM backends in parallel to inspect and compare DDL interpretations and drawings for the same prompt.
  * Essential for the AI to dynamically select the best Stage 1 model.

### 4. `review`
* **`review evaluate <PNG_FILE> [--model M] [--prompt P]`**
  * Scores and reviews drawing composition aesthetics via Vision NIM.
* **`review unread <WORD> --context <CONTEXT>`**
  * Reports a failed vocabulary interpretation word to the server.
