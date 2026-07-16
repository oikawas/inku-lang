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
| paint / batch | Generate one or many works from descriptions or DDL |
| render-score | Render Score JSON without Stage 1 or Stage 2 |
| demo-instruction | Generate a demo description |
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
