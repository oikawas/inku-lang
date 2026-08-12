# Server Configuration

This guide defines the administration baseline for the unreleased inku v2.13.11 (Web Build 896). It covers the environment template, current DB schema, Web administration UI, and reference systemd templates.

## 1. Configuration Boundaries

Settings belong to three boundaries.

1. OS and service: `/etc/inku/inku-api.env`, systemd, reverse proxy, and filesystem permissions
2. Administrator: provider connections, published models, limits, DB backups, artifacts, log policy, and users
3. User: Stage 1/2 models, UI language, UI mode, theme, canvas, color catalog, sketch, Wild, download folder, and history-selection behavior

Provider API key environment variables are initial values. A provider key saved from the admin UI is stored encrypted in the DB. Never put host-specific details or secrets in Git-tracked documentation.

**Some settings are only seeded by the environment.** Painting concurrency and the limits take their initial values from environment variables at first start; after that the DB settings are canonical. Changing an environment variable does not change a setting already stored. Use the admin UI or `inku-cli config update`.

## 2. Backend Environment Variables

### 2.1 Listen, Database, and Session

| Variable | Purpose | Default |
|---|---|---|
| `INKU_SERVER_HOST` | Listen host for the `inku-server` CLI | `127.0.0.1` |
| `INKU_SERVER_PORT` | FastAPI port | `8100` |
| `INKU_SERVER_RELOAD` | uvicorn reload | `0` |
| `INKU_DB_URL` | SQLAlchemy DB URL | SQLite in the user data directory |
| `INKU_SECRET_KEY` | Direct key material for provider-key encryption | unset |
| `INKU_SECRET_KEY_FILE` | Encryption key file | `secret.key` in the user data directory |
| `INKU_SESSION_COOKIE_MAX_AGE` | Session lifetime in seconds | 2592000 |
| `INKU_SESSION_COOKIE_SECURE` | Secure cookie | `0` |
| `INKU_MAX_REQUEST_BODY_BYTES` | Maximum request body size | 16777216 |
| `INKU_MAX_CONCURRENT_REQUESTS` | Concurrent HTTP request limit | 64 |
| `INKU_LOGIN_RATE_ATTEMPTS` | Login failures allowed per window | 10 |
| `INKU_LOGIN_RATE_WINDOW_SECONDS` | Login rate window in seconds | 60 |
| `INKU_CORS_ORIGINS` | Comma-separated allowed origins | localhost only |
| `INKU_LISTEN_HOST` | uvicorn listen host | `0.0.0.0` |
| `INKU_LISTEN_PORT` | uvicorn listen port | `INKU_SERVER_PORT`, else `8100` |
| `INKU_ENV` | Run mode, shown at start and branched on in development | `development` |
| `INKU_TIMEZONE` | Timezone used for DB backup scheduling and similar | `Asia/Tokyo` |
| `INKU_REDIS_URL` | When set, shared state such as rate limiting moves to Redis | unset, in-process |
| `INKU_THUMBS_DB_URL` | URL of the derived database that holds the thumbnails | `thumbs.db` beside `INKU_DB_URL` |

When both encryption variables are set, direct key material has priority. A persistent key file is recommended for production.

`INKU_LISTEN_HOST` and `INKU_LISTEN_PORT` are read by uvicorn directly; `INKU_SERVER_HOST` and `INKU_SERVER_PORT` belong to the `inku-server` CLI. The names are close, so do not swap them.

`INKU_REDIS_URL` takes effect only when redis-py is installed. Without it, shared state lives in the process, so set it for any configuration that runs the backend in more than one process.

### 2.2 Bootstrap Administrator

| Variable | Purpose |
|---|---|
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | Initial administrator name |
| `INKU_BOOTSTRAP_ADMIN_EMAIL` | Initial administrator email |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | Initial administrator password |
| `INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN` | Permit a password shorter than eight characters. **Do not set this in production** |
| `INKU_AUTH_LOCAL_ENABLED` | Sign-in with username and password (default `true`) |
| `INKU_AUTH_GOOGLE_ENABLED` | Sign-in with Google (default `false`) |
| `INKU_SINGLE_USER` | Single-user mode: settle on one person and sign them in automatically (**code default `0`, distributed compose default `1`**). **Does not engage on a database with no administrator** |

The account is created only when a password is set and the DB contains no users. Passwords shorter than eight characters are rejected. Remove the secret from the environment after initial creation.

A blank value counts as unset. Neither an empty field in an environment file nor the empty value that Compose's `${INKU_BOOTSTRAP_ADMIN_PASSWORD:-}` interpolation supplies will fail startup. When clearing the secret after initial creation, deleting the line and blanking it have the same effect.

inku has no self-service registration. Accounts are created only through `POST /api/users`, by an authenticated member of the `admins` or `leaders` group. **Starting an empty database without a bootstrap administrator, with single-user mode off, therefore leaves a server nobody can sign in to.** With single-user mode on, the server creates one account and signs it in by itself. Recovery is simply to set the password and restart. The bootstrap administrator is attempted only while the DB has no users, so an existing account's password is never overwritten.

### 2.3 Artifacts and Concurrency

| Variable | Purpose | Default |
|---|---|---|
| `INKU_OUTPUT_DIR` | SVG/JSON/PNG artifact directory | `outputs` in the user data directory |
| `INKU_OUTPUT_PNG_SIZE` | Auto-saved PNG edge size | `2160` |
| `INKU_OUTPUT_SAVE_WORKERS` | Artifact save workers | `2` |
| `INKU_OUTPUT_SAVE_QUEUE_LIMIT` | Artifact queue limit | `32` |
| `INKU_STAGE_WORKERS` | LLM pipeline workers | `4` |
| `INKU_STAGE_QUEUE_LIMIT` | Pipeline queue limit | twice the worker count |
| `INKU_RENDER_CONCURRENCY` | Initial value for the concurrent renderer limit | 2 |
| `INKU_CLIENT_FANOUT_LIMIT` | Initial value for the browser's concurrent painting requests | `4` |
| `INKU_DB_BACKUP_SCHEDULER` | Set to `0` to leave the periodic backup scheduler unstarted | `1` |
| `INKU_THUMBNAIL_WORKERS` | Workers that bake after a save (**separate from the rebuild**, whose parallelism comes from the stored `workers` setting) | `2` |
| `INKU_THUMBNAIL_QUEUE_LIMIT` | Thumbnail baking queue ceiling | `64` |

When the artifact queue is full, DB history remains the priority and only artifact saving is skipped. Distinguish provider queue latency from insufficient server workers.

`INKU_RENDER_CONCURRENCY` and `INKU_CLIENT_FANOUT_LIMIT` **seed the first value only**. After that the DB settings are canonical; change them from `Other (server)` in the admin UI or with `inku-cli config update`. Requests beyond the server limit are refused with 503 rather than queued, and the client retries at a short interval.

### 2.4 LLM Retry and Timeout

| Variable | Purpose | Implementation default |
|---|---|---|
| `INKU_LLM_REQUEST_TIMEOUT_SECONDS` | Provider HTTP timeout | `120` |
| `INKU_LLM_RETRY_ATTEMPTS` | Total attempts | `4` |
| `INKU_LLM_RETRY_BASE_DELAY` | Initial delay in seconds | `2.0` |
| `INKU_LLM_RETRY_MAX_DELAY` | Maximum delay | `20.0` |
| `INKU_LLM_RETRY_JITTER` | Jitter | `0.25` |
| `INKU_STAGE1_HARD_TIMEOUT_SECONDS` | Stage 1 hard timeout | `120` |
| `INKU_STAGE2_HARD_TIMEOUT_SECONDS` | Stage 2 hard timeout | `120` |
| `INKU_SKETCH_HARD_TIMEOUT_SECONDS` | Hard timeout for Sketch from life, Stage 0.5 | `120` |

The distributed environment template explicitly sets operational example values. Be aware of the difference between template values and implementation defaults.

The hard timeout also applies when a stage cannot acquire an execution slot. If Stage 1 does not answer in time, a stock set of instructions is performed and the work records that. If the sketch layer does not answer in time, the description goes to interpretation unchanged.

### 2.5 Layers and Plugins

| Variable | Purpose | Default |
|---|---|---|
| `INKU_LLM_BACKEND` | Which LLM backend family to use | `anthropic` |
| `INKU_DOCUMENT_PLUGIN_DIR` | Where declarative plugin documents live | `server/plugins/` |
| `INKU_OKUGAKI_MODEL` | Default reader model for the colophon | a vision-capable model |
| `INKU_OKUGAKI_CACHE_TTL_SECONDS` | Colophon cache lifetime | `1800` |
| `INKU_OKUGAKI_CACHE_MAX_ENTRIES` | Colophon cache size | `256` |
| `INKU_LEARNED_FILE` | Where learned words are stored | `/tmp/inku-learned.json` |
| `INKU_COERCE_DISABLE` | Switch off coerce, the auto-repair pass. **Diagnostic only** | unset |
| `INKU_DEVELOPER_MODE` | Extra developer-facing output | unset |

The default for `INKU_LEARNED_FILE` is under `/tmp`, so it does not survive a restart. Give it a stable path to persist it.

`INKU_COERCE_DISABLE` turns off auto-repair entirely: neither invisible-color correction nor overcrowding damping applies. **Do not set it in production.** It exists for isolating a problem.

### 2.6 Providers

| Provider | API key | Base URL |
|---|---|---|
| OpenAI API Platform | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| Gemini | `GEMINI_API_KEY` | `GEMINI_BASE_URL` |
| NVIDIA NIM | `NVIDIA_API_KEY` | `NVIDIA_BASE_URL` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` |
| Ollama Cloud | `OLLAMA_CLOUD_API_KEY` | `OLLAMA_CLOUD_BASE_URL` |

Base URLs, keys, and published models can also be managed from the admin UI. Keys stored in the DB use the encrypted `enc:v1:` format.

## 3. Database and Migrations

### 3.1 SQLite

```sh
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
```

How many thumbnails the rebuild bakes at once comes from the stored `workers` setting (1..16, default 4). **It is not an environment variable** — the machine is never asked for its core count, so whoever enters it has to know what this machine or container actually has.

Thumbnails do not go into the canonical database; they go into `thumbs.db` beside it. Deleting that file leaves the canonical data whole, and the listing draws from each work's SVG again.

SQLite is the reference single-server setup. History search uses FTS5 when available and falls back to `LIKE` otherwise.

At backend startup, current code runs column, index, FTS, lineage-root, and related migrations and backfills. Create a DB backup before startup and do not run multiple backend versions against the same DB during migration.

### 3.2 PostgreSQL

```sh
INKU_DB_URL=postgresql://inku:<password>@127.0.0.1/inku
```

Restrict the environment file containing the DB URL to root and the service group. Use database-native backup procedures; SQLite-specific Web backup is not available for PostgreSQL.

### 3.3 History, Lineage, and Identity

The DB keeps these identities separate.

- Description hash: identity of the normalized description (`dh1:`)
- Render hash: identity of a Renderer output edition (`rh3:`; `rh2:` is the earlier version, kept for stored works)
- History ID: regular-history item
- Lineage node ID: node in the creative process

The canonical payload of `rh3` is the score, `render_seed`, `render_wild`, the render engine id and version, and the color catalog id. It does not include `composition_seed` or the build number. **The key names in that payload are identity material; never rename them for presentation reasons.** A rename recomputes the hash of every stored work.

Lineage connects only explicit creation operations. It is never inferred from similarity, identical descriptions, or timestamps. Permanent removal of a regular-history work may leave a content-free tombstone so the lineage path remains recorded.

## 4. Authentication, Permission Groups, and Scope

| Permission group | Permissions |
|---|---|
| `admins` | Providers, server, DB, logs, users, and groups |
| `leaders` | User administration within assigned scope |
| `users` | Generation and management of own history and settings |

One member may hold several permission groups; where they overlap the stronger one decides (a member holding `admins` and `leaders` passes as `admins`). A user group — the organisational unit — is a separate thing: one per member, and independent of permission.

**What a member may do (the table above) and what a member may see are separate axes.** Membership decides the default scope of a work.

| Permission group | Works visible by default |
|---|---|
| `admins` | All of them |
| `leaders` | Those of their own organisation group |
| `users` | Their own |

**Per-work sharing adds to that.** The owner — and `admins` — can hand a work to a chosen recipient, one work at a time, with either `read` (they can open it) or `write` (they can also star, trash and delete it). **Being able to read a work is not permission to hand it on**: a recipient cannot pass it along.

Generation, history, lineage, and settings APIs enforce authentication and the visibility scope. **⚠ Since v2.12.2 a lineage crosses owners** — any readable work of another member can be a parent, and the group's root is inherited, so **the number of visible nodes in one group differs per viewer**. A node that cannot be read comes back with its content withheld, telling `deleted` apart from `not_permitted` in words. Acceptance testing must cover both directions: **a work that was not shared never reaches another member**, and **a work that was shared does reach them**. **Settings carry no sharing**: personal settings stay with their owner, and global settings stay with `admins`.

## 5. Models and Languages

| Stage | Role |
|---|---|
| Stage 0.5 | Restate the description as prose in the language of things. Optional, and it uses an LLM |
| Stage 1 | Interpret the description, or the sketch, as instructions (normalized DDL) |
| Plugin expansion | Deterministically write namespaced plugin words down into core DDL |
| Stage 1.5 | Deterministically expand DDL and give it relations; not an LLM |
| Stage 2 | Structure DDL as JSON Score |
| coerce | Boundary handling that prefers dropping to inventing |
| Renderer | Perform the Score as SVG |

When Stage 0.5 runs, **the sketch reaches three consumers in place of the description**: Stage 1, the decision whether plugin expansion fires, and Stage 1.5. If the layer does not answer, the description is passed on unchanged and `sketch_state` records `fallback`. A work painted with the layer off records `off`, and works predating the column hold no value at all. **No value is not `off`.**

The Web UI always sends `instruction_lang: auto` for normal generation. The server detects Japanese or English from the text and falls back to `ui_lang` only when no language signal is present. The API retains `auto`, `ja`, and `en` for compatibility and explicit comparison runs.

Resolved values are recorded as `instruction_lang_requested`, `instruction_lang_resolved`, and `ui_lang`. These language fields are not part of the current canonical render-hash payload.

### 5.1 Limits

Nine numbers decide how many marks one work may hold. They are not a speed control: the number of lines actually drawn changes. Set them from the `Limits` tab in the admin UI or with `inku-cli config update`. **They are written into the Stage 1 and Stage 2 prompts and recorded on every work painted.**

| Group | Value | Default | Contents |
|---|---|---|---|
| Marks actually drawn | `max_expanded_primitives` | 400 | Marks per work. Beyond this the whole work is shrunk to fit |
| | `max_expanded_per_instruction` | 240 | Marks per instruction. An instruction asking for more is thinned |
| | `max_instructions` | 64 | Instructions per work. Any beyond this are dropped |
| Stated counts | `literal_count_threshold` | 240 | Below this a stated count is drawn as stated; at or above it the work is shown as a crowd |
| | `represented_count_min` | 80 | Lower end when shown as a crowd |
| | `represented_count_max` | 120 | Upper end |
| Reading and validation ceilings | `ddl_count_max` | 1000 | Numbers in the description are rounded down to this. It is also the top of the density band taught to Stage 1 |
| | `ddl_count_max_grid` | 2000 | A literal grid alone is allowed higher than ordinary composition |
| | `schema_count_max` | 2000 | A count returned by Stage 2 above this is trimmed |

Mutually inconsistent values are rounded rather than rejected — if the representation ceiling exceeds the literal threshold, it is lowered to that threshold. What the admin UI shows is the rounded, effective value.

**The limits are constant guards for stability, data size, and device performance.** They exist neither to add what the description does not ask for nor to remove what it does.

## 6. Renderer and Replay

`render_seed` controls touch, `composition_seed` controls placement, `variation_seed` supports the variation layer, and `interpretation_seed` supports reading variation. From render engine 23 the placement is decided by `composition_seed`, and follows `render_seed` only when it is omitted. The test is `is not None`, so `0` is the seed zero and not "not given". `seed_text` deterministically hashes explicit words into only the Renderer performance seed. It never changes interpretation, DDL, JSON Score, or composition.

`variation_seed` takes effect only together with `variation_amplitude`. Either one alone moves no axis of the expansion layer.

`render_wild` applies to the whole work and is part of the `rh3` material. The same score and the same seed with a different Wild setting is a different edition.

History replay uses the saved Score, color catalog, canvas, seeds, and render-engine version. Engine version is recorded for audit; bit-identical output across different engine versions is not assumed.

## 7. Artifact Saving

The history DB is the source of truth. Artifacts are rebuildable outputs.

This setting has nothing to do with thumbnails: listings keep baking them even when artifact saving is off.

```text
<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>...
```

Administrators can change artifact targets and queue settings from server settings. Verify write permission for the service user after changing the output path.

## 8. Backup and Recovery

Back up at least:

| Target | Reason |
|---|---|
| DB | Source of truth for history, lineage, users, and settings |
| `INKU_SECRET_KEY_FILE` | Required to decrypt provider keys |
| `/etc/inku/inku-api.env` | Runtime configuration |
| systemd and reverse proxy | Service recovery |
| Artifacts | Rebuildable, but potentially required operationally |

Change the SQLite backup directory with `INKU_DB_BACKUP_DIR`. The Web admin UI supports manual and scheduled backups with generation retention. Use external backups as well, keeping the DB and encryption key at the same recovery point.

Recovery tests should verify sign-in, provider-key decryption, history display, lineage edges, and SVG replay.

## 9. Logs

Reference files:

```text
/var/log/inku/inku-api.log
/var/log/inku/inku-server.log
```

The templates write to both the systemd journal and append files.

```sh
journalctl -u inku-api.service -n 100 --no-pager
journalctl -u inku-server.service -n 100 --no-pager
```

The log policy in the admin UI (enabled / retention days / interval / compression) is **executed by the application itself**. Files are written under `INKU_LOG_DIR` (`~/.local/share/inku/logs` by default, `/data/logs` in the container distribution), and the application rotates, compresses and prunes them. No logrotate configuration is needed. **The same lines keep going to stdout**, so `journalctl` and `docker logs` are unchanged. In the container distribution, `logging` in `compose.yaml` caps what the daemon collects from stdout.

## 10. systemd

Reference templates:

- [inku-api.service](./templates/systemd/inku-api.service)
- [inku-server.service](./templates/systemd/inku-server.service)

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
sudo systemctl status inku-api.service --no-pager
sudo systemctl status inku-server.service --no-pager
```

The reference frontend service starts Vite with `NODE_ENV=development`. Do not use it unchanged for public production service. Design a production adapter, process command, static assets, and proxy timeouts.

## 11. Reverse Proxy and Cookies

Minimum routes:

- `/` -> `http://127.0.0.1:5173/`
- `/api/` -> `http://127.0.0.1:8100/api/`
- Optional `/health` -> `http://127.0.0.1:8100/health`

Terminate HTTPS and set `INKU_SESSION_COOKIE_SECURE=1` for public deployment. LLM generation may be long-running, so do not configure proxy timeouts shorter than provider timeouts without intent.

## 12. Health Checks and Monitoring

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
curl -sS -I --max-time 5 http://127.0.0.1:5173/
```

Authentication through the Web proxy:

```sh
curl -sS -i --max-time 5 \
  -X POST http://127.0.0.1:5173/api/auth/login \
  -H 'Content-Type: application/json' \
  --data '{"username":"admin","password":"wrong"}'
```

A 401 response for the wrong password confirms the path from Web to API. Monitor HTTP status, service restarts, worker queues, provider errors, artifact queue skips, and DB backup success. Provider wait duration is not a quality metric.

## 13. Troubleshooting

| Symptom | Check |
|---|---|
| Cannot sign in | Bootstrap conditions, user state, secure-cookie setting, and DB connection |
| Cannot generate | Provider key, Base URL, published models, and Stage logs |
| Japanese or English is misdetected | Language signal in input, `ui_lang` fallback, and effective languages in Provenance |
| History is missing | User scope, regular/trash mode, and timeline/lineage filter |
| Lineage appears broken | Parent-candidate save failure, lineage migration, and tombstones |
| A work appears but artifacts do not | Queue skip, output permissions, and worker count |
| Provider key cannot decrypt | Confirm the same recovery-point `INKU_SECRET_KEY_FILE` |
| DB fails after startup | Migration logs, DB backup, and concurrent mixed backend versions |
| Painting is refused with 503 | The server concurrency setting. The DB setting is canonical, not the environment variable |
| A stated count comes out smaller | `literal_count_threshold` and `represented_count_*` under the limits |
| The sketch layer seems not to run | The work's `sketch_state`. `fallback` points at the Stage 0.5 timeout and the provider |
| Plugin words are not expanded | Rejection reasons from `plugin list`, `INKU_DOCUMENT_PLUGIN_DIR`, and `plugin reload` |

## 14. Security Baseline

- Never commit provider keys, DB passwords, or bootstrap passwords.
- Restrict the environment file to root and the service group.
- Persist the encryption key and back it up on separate media from the DB.
- Use HTTPS, Secure cookies, and reverse-proxy request-size and timeout limits for public service.
- Do not grant the service user unnecessary shell, sudo, or access to other users' data.
- Apply access control to backups and logs because they may contain descriptions and metadata.
- Prepare recovery procedures before user deletion, permanent history deletion, or key rotation.
