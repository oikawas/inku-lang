# inku-cli Reference

inku-cli controls the same public HTTP API as the Web UI. It uses the stored session, while the server enforces the permissions of regular users, group leads, and administrators.

## Basics

    cd cli
    uv run inku-cli --help
    uv run inku-cli login --base-url http://127.0.0.1:8100 -u USERNAME
    uv run inku-cli me
    uv run inku-cli version

Run inku-cli COMMAND --help for the complete option list.

| Command | Purpose |
|---|---|
| login / logout / me | Start, discard, and inspect a session |
| models | Configure default Stage 1 and Stage 2 models |
| paint / batch | Paint one or many works from descriptions or DDL |
| refine | Refine an existing work's touch, layout, reading, or color |
| lineage | Inspect lineage node trees and promote intermediate works |
| inspect | Inspect and compare multiple inference models in parallel |
| review | Evaluate drawings using Vision NIM and submit unread words |
| render-score | Render Score JSON without Stage 1 or Stage 2 |
| demo-instruction | Write a demo description |
| history / history-export | List or export history by hash |
| unread-words | Show the user's ledger; administrators may use --all |
| contact-sheet / analyze / ddl-compare | Compare and analyze local artifacts |
| vision-review | Run the configured vision model as a read-only mirror |
| api | Call any public API with an explicit HTTP method |
| version | Show CLI and server version/build information |

## Calling Every Public API

Use api when no dedicated command exists. It accepts only relative /api/... or /health paths and rejects attempts to redirect requests to another host.

    uv run inku-cli api GET /api/color-catalogs
    uv run inku-cli api GET /api/history --query limit=20 --query starred=true
    uv run inku-cli api PATCH /api/auth/me/settings --data '{"ui_theme":"dark"}'
    uv run inku-cli api POST /api/history/trash --file ids.json
    uv run inku-cli api DELETE /api/history --header X-Inku-Confirm=permanent-delete-trash
    uv run inku-cli api GET /api/history/WORK_ID/svg --query profile=editable --output work.svg

--data and --file are mutually exclusive. Save non-JSON responses with --output. Use --no-auth only for endpoints that do not require a session.

Permissions are identical to the GUI. Regular users can access only their own works and settings. Group leads can manage regular users in their own group. Administrators can manage server settings, all users, and the global unread-word report. Unauthorized calls return 403; missing sessions return 401.

When retrying a save request, reuse an Idempotency-Key to prevent duplicate works and lineage nodes.

    uv run inku-cli api POST /api/history --file work.json --header Idempotency-Key=import-20260715-001


## Autonomous Refinement & Quality Improvement Commands

These commands allow an AI agent to automatically generate variations, evaluate visual aesthetics, and traverse/update the lineage tree.

### 1. Lineage Management (lineage)
Traverse the derivation tree or promote an intermediate node to regular history.

* **Show the Lineage Tree**:
  ```sh
  uv run inku-cli lineage show WORK_ID --depth 3
  ```
  Prints a hierarchical tree view of parent, child, and sibling nodes relative to the target ID. Use `--json` for raw JSON.
* **Promote an Intermediate Node**:
  ```sh
  uv run inku-cli lineage promote NODE_ID
  ```
  Promotes an intermediate work (`lineage_only` node hidden from standard history list) to a regular `active` history record.

### 2. Refinement & Variations (refine)
Create or import variations derived from an existing parent work.

* **Make a Variation Option**:
  ```sh
  uv run inku-cli refine generate WORK_ID --kind touch -o ./refinements --png
  ```
  Set `--kind` to `touch` (line texture/bleed), `layout` (composition), `reading` (interpretation), or `color` (catalog). The server generates a variation and attaches it to the parent. Optionally saves SVG/JSON/PNG to the specified directory.
* **Import a Refinement Score**:
  ```sh
  uv run inku-cli refine save PARENT_NODE_ID --kind layout --file score.json --input-text "your sentence"
  ```
  Directly imports a locally adjusted Score JSON as a child node connected to a parent.

### 3. Model Inspection (inspect)
Compare how different models interpret and draw the same prompt.

```sh
uv run inku-cli inspect "Draw a blue line" --models "qwen/qwen3.5-397b-a17b,google/gemma-4-31b-it" -o ./inspection --png
```

### 4. Visual Review & Feedback (review)
Evaluate aesthetics using a Vision LLM and report word interpretation limits.

* **Evaluate Drawing via Vision NIM**:
  ```sh
  uv run inku-cli review evaluate drawing.png --model nvidia/neva-22b
  ```
  Sends a rendered PNG to a Vision LLM for detailed composition and style scoring (requires `NVIDIA_API_KEY`).
* **Submit Unread Word Feedback**:
  ```sh
  uv run inku-cli review unread "mist" --context "draw a circle on a mist ground"
  ```
  Reports a vocabulary phrase and context where translation was uncertain, storing it in the server's unread-words ledger.

