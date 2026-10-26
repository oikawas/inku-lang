# Server Configuration

This guide defines the administration baseline. It covers the environment template, current DB schema, Web administration UI, and reference systemd templates, using v2.15.147 (Web Build 1223) as the baseline.

## 1. Configuration Boundaries

Settings belong to three boundaries.

1. OS and service: `/etc/inku/inku-api.env`, systemd, reverse proxy, and filesystem permissions
2. Administrator: provider connections, published models, limits, DB backups, artifacts, log policy, and users
3. User: one drawing model shared by Stage 1/2, Vision model, UI language, UI mode, theme, text size, canvas, color catalog, sketch, Wild, download folder, and history-selection behavior

Provider API key environment variables are initial values. A provider key saved from the admin UI is stored encrypted in the DB. Never put host-specific details or secrets in Git-tracked documentation.

**Some settings are only seeded by the environment.** Painting concurrency and the limits take their initial values from environment variables at first start; after that the DB settings are canonical. Changing an environment variable does not change a setting already stored. For limits, use the admin UI or `inku-cli config update`; for concurrency, use the admin UI or the API in §2.3.

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

The distributed web image sets `BODY_SIZE_LIMIT`, the request limit of the proxy that forwards `/api` to the backend, to `16M` (the same as the `INKU_MAX_REQUEST_BODY_BYTES` default). When you raise `INKU_MAX_REQUEST_BODY_BYTES`, raise the web container's `BODY_SIZE_LIMIT` by the same amount; a request over the web limit fails before it reaches the backend.

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
An administrator who forgets the password is not shut out for good. `inku-admin reset-password` sets one account's password from inside the server's own environment (`docker compose exec api inku-admin reset-password --username admin` for the distributed image, `uv run inku-admin reset-password` from a source checkout). It asks for the password twice and never takes it on the command line; `--password-stdin` reads the first line of standard input for scripted use. Naming no account resets the one `INKU_BOOTSTRAP_ADMIN_USERNAME` created, and an unknown name prints the accounts that exist. **This is not a second way in**: running it needs the container or the files, and both already carry the database. Available from v2.13.41.

### 2.3 Artifacts and Concurrency

| Variable | Purpose | Default |
|---|---|---|
| `INKU_OUTPUT_DIR` | SVG/JSON/PNG artifact directory | `outputs` in the user data directory |
| `INKU_OUTPUT_PNG_SIZE` | Auto-saved PNG edge size | `2160` |
| `INKU_OUTPUT_SAVE_WORKERS` | Artifact save workers | `2` |
| `INKU_OUTPUT_SAVE_QUEUE_LIMIT` | Artifact queue limit | `32` |
| `INKU_PIPELINE_CONFIG` | Path to a pipeline manifest JSON (§2.4) | built-in defaults when unset |
| `INKU_RENDER_CONCURRENCY` | Initial value for the concurrent renderer limit | 2 |
| `INKU_CLIENT_FANOUT_LIMIT` | Initial value for the browser's concurrent painting requests | `4` |
| `INKU_DB_BACKUP_SCHEDULER` | Set to `0` to leave the periodic backup scheduler unstarted | `1` |
| `INKU_THUMBNAIL_WORKERS` | Workers that bake after a save (**separate from the rebuild**, whose parallelism comes from the stored `workers` setting). **It starts having an effect in v2.13.37** -- until then the bake ran inside the same process, and the rasterizer holds one core, so any number of workers finished one image at a time | `2` |
| `INKU_THUMBNAIL_QUEUE_LIMIT` | Thumbnail baking queue ceiling | `64` |

When the artifact queue is full, DB history remains the priority and only artifact saving is skipped. Distinguish provider queue latency from insufficient server workers.

`INKU_RENDER_CONCURRENCY` and `INKU_CLIENT_FANOUT_LIMIT` **seed the first value only**. After that the DB settings are canonical; change them from `Other (server)`, which appears after switching Settings to `Detailed`. The CLI's `config update` has no concurrency flags. From a CLI signed in as an administrator, use the public API:

```sh
inku-cli api GET /api/settings/render-concurrency
inku-cli api PUT /api/settings/render-concurrency --data '{"server_limit":2,"client_limit":4}'
inku-cli api GET /api/settings/render-concurrency
```

Requests beyond the server limit are refused with 503 rather than queued, and the client retries at a short interval. One account renders one picture at a time: a second render waits up to 30 seconds for the first to finish, then gets the same 503.

The pipeline effect pool is separate. Set the manifest's `host_limits`: `max_workers` (default 4), `max_effect_steps` (effects advanced in one drain, 32), and `max_retained_runs` (retained executions, 8). The old `INKU_STAGE_WORKERS` / `INKU_STAGE_QUEUE_LIMIT` do not change this pool.

The distributed Compose files put a memory ceiling on the `api` container (`INKU_API_MEM_LIMIT`, `4g` by default). One render of an extreme shape can take gigabytes, so raise this ceiling when you raise the render concurrency. Past it, only the `api` container stops, and `restart: unless-stopped` brings it back.

### 2.4 LLM Retry and Timeout

| Variable | Purpose | Implementation default |
|---|---|---|
| `INKU_LLM_REQUEST_TIMEOUT_SECONDS` | Catalog selection / hole completion policy attempt and total seconds | `120` |
| `INKU_LLM_STAGE1_ATTEMPT_TIMEOUT_SECONDS` | Stage 1 per-attempt ceiling in seconds | `300` |
| `INKU_LLM_STAGE1_TOTAL_TIMEOUT_SECONDS` | Stage 1 total seconds (normalized to at least the attempt ceiling) | `540` |
| `INKU_LLM_RETRY_ATTEMPTS` | Maximum policy attempts | `4` |
| `INKU_LLM_RETRY_BASE_DELAY` | Policy delay between attempts in seconds | `2.0` |

The distributed environment template explicitly sets operational example values. Be aware of the difference between template values and implementation defaults.

Normal pipeline retries follow finite policies. The old `INKU_STAGE1_HARD_TIMEOUT_SECONDS`, `INKU_STAGE2_HARD_TIMEOUT_SECONDS`, and `INKU_SKETCH_HARD_TIMEOUT_SECONDS` do not control them. When policy permits no further attempt, an ordinary Stage 1 failure ends as `Failed` and hole completion failure stops as `NeedsUserEdit`. A non-retryable failure may stop before the budget is spent. A sketch failure proceeding without its supplement, or retaining only an already verified candidate, is a limited fallback, not a promise to replace general failures with a stock successful work.

#### Changing the pipeline manifest

Without a path, the server uses the same source's built-in manifest. To customize it, first install the native wheel in the server environment as in [Installation §5](application-install.md#5-prepare-the-backend), export the defaults to JSON, edit the required values, and place the file where the service user can read it.

```sh
cd /opt/inku/inku-lang/server
sudo -u inku .venv/bin/python -c 'import json; from inku_server.pipeline_candidate import PipelineBinding; from inku_server.pipeline_defaults import default_manifest; print(json.dumps(default_manifest(PipelineBinding()), ensure_ascii=False, indent=2))' > /tmp/inku-pipeline.json
sudo install -o root -g inku -m 0640 /tmp/inku-pipeline.json /etc/inku/pipeline.json
sudo editor /etc/inku/pipeline.json
```

Set `INKU_PIPELINE_CONFIG=/etc/inku/pipeline.json` in the environment file and restart the API service to load it. The manifest is a complete JSON document, not a partial override. With a path set, the server uses the file's `pipeline.stage1_retry`, `pipeline.catalog_retry`, `pipeline.hole_retry` (`attempt_timeout_ms`, `total_timeout_ms`, and `retry_delay_ms` are decimal strings in milliseconds), and `host_limits`, rather than regenerating defaults from the environment variables above. Do not put credentials in it.

Explicitly set the additional structural limits in both `pipeline.compiler.hard_resource_policy.budget.maximum` and `pipeline.compiler.operational_resource_budget.maximum`. The defaults are `logical_objects=4096`, `template_nodes=128`, `anchor_instances=4096`, `transform_instances=4096`, `placement_instances=64`, and `fill_instances=64`. The four existing limits in §5.1 are mapped from DB settings / requests, so changing the manifest alone does not change those values. Saved executions and derived editions retain their saved policy. On a source upgrade, export new defaults and review your changes against them.

### 2.5 Layers and Plugins

| Variable | Purpose | Default |
|---|---|---|
| `INKU_LLM_BACKEND` | Which LLM backend family to use | `anthropic` |
| `INKU_DOCUMENT_PLUGIN_DIR` | Where declarative plugin documents live | `server/plugins/` |
| `INKU_PLUGIN_PACKAGE_DIR` | Where plugins (packages) an administrator added from the Web live | `~/.local/share/inku/plugin-packages` (`/data/plugin-packages` in Docker) |
| `INKU_OKUGAKI_MODEL` | Default reader model for the colophon | a vision-capable model |
| `INKU_OKUGAKI_CACHE_TTL_SECONDS` | Colophon cache lifetime | `1800` |
| `INKU_OKUGAKI_CACHE_MAX_ENTRIES` | Colophon cache size | `256` |
| `INKU_LEARNED_FILE` | Where learned words are stored | `/tmp/inku-learned.json` |
| `INKU_DEVELOPER_MODE` | Extra developer-facing output | unset |

The `Plugins` settings add and delete vocabulary plugins and show whether each is on and its words (name, aliases, surfaces, notes, example, preview).

- `Add a plugin` takes a plugin file (`inku.plugin-package.v1` JSON, or a zip holding it with the PNGs of its Saijiki pictures; `PLUGIN.md` §5.1 says how to write one) and the Server checks it at once: the file's shape, the shared core's checks of each definition, and drawing each word's Japanese and English example. Whatever is wrong is listed word by word with its place in the file and the reason. A word that passed shows the note, example, and picture the Saijiki will show (the zip's picture, or one drawn from its example). `Add` is offered only when everything passed; when a plugin with the same name (`namespace.name`) is installed it becomes `Replace`.
- An added plugin's words can be drawn in every new work on that Server, appear in the Saijiki and in DDL editor completion, and reach Stage 1 through their summaries when drawing from a description. Saved works keep drawing with the definitions they saved, whatever is replaced or deleted later.
- `Replace picture` on a word uploads a PNG the Saijiki shows instead; `Back to the original picture` returns to the zip's picture or the one drawn from the example. Replacing the plugin keeps replaced pictures.
- `Export` saves an installed plugin as a zip with its definitions, summaries, notes, examples, and current pictures; another Server can add it as it is.
- An added plugin can be switched off or deleted.
- A bundled package's document (today `Nature.leaves`) is marked `Used for drawing`; it cannot be deleted, so switch it off when it is not wanted. Any other `.inku-plugin.md` is a legacy document without definitions and is marked `Not used for drawing`: writing its words leaves them out with a diagnostic. A legacy document can be deleted.

A document counts as a bundled package only where it sits in `server/plugins/`. With `INKU_DOCUMENT_PLUGIN_DIR` pointed elsewhere, a `nature-leaves.inku-plugin.md` placed there is treated as legacy and the `Nature.leaves` words are not drawn. If the settings mark it `Not used for drawing`, check that directory.

The default for `INKU_LEARNED_FILE` is under `/tmp`, so it does not survive a restart. Give it a stable path to persist it.

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

**The bake that follows a save runs in a child process** (v2.13.37). **The server keeps answering other requests while it runs** -- until then it baked inside the same process, and the rasterizer holds a core for the whole rasterization, so saving a heavy work could stall other requests for seconds (measured: one request stalled 4.65 seconds; the slowest is now 255 ms). **The bake itself is no faster.** It simply no longer stops anything.

**The first bake after a server start waits for the child to come up** (measured 0.32 s). No bake after that pays it. **A light work becomes very slightly slower** (measured 7.2 -> 12.4 ms), which is the round trip of handing the SVG to the child and taking the PNG back. **A thumbnail is a shortcut for display, so when one is late the listing draws the work's own SVG instead.**

**At thumbnail widths (256px, and 512px for HiDPI) the texture of marks drawn in a row with one tool is folded into a single run before rasterizing** (v2.13.33). **The stored SVG does not change by a single byte** — the fold happens only at bake time. It cuts how many times the filter is applied and raises the area it covers, so it only pays while the width is small; the 2160px PNG export default and browser display widths are not folded. **⚠ Thumbnails already baked are not rebaked** — staleness is decided from the hash of the stored SVG, and that SVG does not move. What gets faster is what is baked from now on, plus an explicit rebuild from the admin UI.

SQLite is the Server's only supported canonical database. `INKU_DB_URL` accepts
SQLite URLs only, and a non-SQLite URL is rejected before SQLAlchemy engine
creation. History search uses FTS5 when available and falls back to `LIKE`
otherwise.

Startup checks the versioned `schema_migrations` registry. A fresh database gets
the current metadata and required rows. A registered database only verifies its
version, name, and checksum. A pre-registry database is migrated once, under a
writer lock and after a SQLite-native snapshot, only when its schema fingerprint
and FTS state match a known baseline. Unknown baselines, checksum mismatches, and
partial FTS fail closed without modification.

### 3.2 Migration and Backup Boundary

The pre-migration snapshot for an accepted legacy database and the manual or
scheduled replicas configured by an administrator both use the SQLite file
boundary. Registered databases do not repeat the same migration and backfill on
every startup. Restrict the environment file containing the DB URL to root and
the service group.

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

An administrator uses `User management` in Settings to create users and change membership, permission groups, and another person's password. Choose the account, fill in `New password` in `Edit user`, and save (**the current password is not asked for**). `User management` is shown to `admins` and to `leaders`. A `leaders` member sees only the ordinary users of their own organisation group, and creates, edits, deletes, and sets passwords for them (choosing permission groups or organisation groups, and managing organisation groups, stay with `admins`). A person changing their own password does it from `Profile`, where both the current and the new one are required. **None of this is open to a lone administrator who has forgotten theirs** -- the way back is `inku-admin reset-password` in 2.2.

Setting a password again ends the account's other sessions: a reset by an administrator or by `inku-admin reset-password` ends all of them, and a person's own change ends all but the one that made it.

**The last member of `admins` can be neither removed from the group nor deleted** (409); make someone else an administrator first. Turning local sign-in off (`inku-cli config update --local-auth false`) is refused with 409 as well: the Google switch exists, but nothing signs anyone in through it, so local sign-in is the only way in.

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

### 5.0 Web UI Settings Routes

Open `Settings` from the application rail. The top `Standard` / `Detailed` switch and the categories on the left control this dialog. The switch is a per-browser choice for the amount shown in Settings; it is separate from the drawing screen's `UI mode`. `Standard` shows everyday items. `Detailed` also shows `Plugins`, `Other (server)`, `Limits`, and `Unread-word ledger`. A person without the needed permission neither sees nor operates administration items.

| Category | Main items | Scope |
|---|---|---|
| `Display and operation` | Text size, caption position, UI mode, and fields below history thumbnails | Text size, UI mode, and related choices belong to the member. Text size takes effect immediately. |
| `Making` | Batch retry count and `Demo` | The batch retry count belongs to the member. `Demo` is in the Making category. |
| `Export` | Save location, PNG templates, animation, and cards | The save location belongs only to the browser that chose it. PNG templates apply to that member's PNG menu. |
| `Connections and administration` | `Models`, `User management`, `DB settings`, `Log retention`, and, in Detailed mode, `Other (server)` and `Limits` | `User management` is available to `admins` and to `leaders` (for the ordinary users of their own organisation group); the other items to `admins` only. |

`Model selection` is a separate drawing-time screen for choosing the drawing and Vision models. It has two tabs, `Stage 1/2` and `Vision`; both drawing stages use the same model. The administrator's `Models` screen manages connection services, Base URLs, API keys encrypted for storage, models visible to members, and LLM / Vision purpose. Adding or changing a connection does not by itself make its models visible to members.

To change the published models as an administrator:

1. Choose a connection service in `Models`, then open `Select models` in its published-model section.
2. Find models with search and filters, and check those to publish. The bulk selection action applies only to the currently filtered results shown in the list and in open folds.
3. Use `Save` to apply the selection, or `Cancel` to close without saving it. Fetching the model list is unavailable while there are unsaved changes; save or discard them first.

Models carry labels, and a labelled model is filed into a fold below the list. The folds come in the order `Not measured`, `Older model`, `Paid plan only`, `No response when measured`, `Not supported`, `End of life`, each headed with its count (`Older model (n)`), closed at first; a model with more than one label goes into the fold of the later one. Models labelled `Not measured` or `Older model` can be checked and published. A model labelled `No response when measured` can be published as not recommended once its purpose button (framed in red) is chosen. Models with any of the other three labels cannot. Search and filters count the models inside the folds too. `Not measured` marks a model with no measurement at all, `Older model` one the provider has superseded with a newer generation (the OpenAI API up to GPT-5.4, for one), `No response when measured` one that answered neither purpose when measured, and `Not supported` a kind left out of the benchmark (speech, music, video, embeddings and the like). A model's row and hover card show every label it carries. Assessments and labels come from the model catalog the server ships (`model_catalog.json`); when it is updated, assessments an administrator edited go back to the catalog's values. Ollama Cloud (ollama.com) returns its list whatever the key's plan, so each `Fetch model list` makes one short call to every listed model with the configured API key. A retired model is marked `End of life`, one the plan does not reach (HTTP 402 or 403) is marked `Paid plan only`, and one the key can call loses the `Paid plan only` mark. A model that could not be checked, because the service was busy or the call timed out, keeps its earlier mark. With one call per model the fetch can take a minute or two, and it spends a little of the Ollama Cloud allowance.

A model left unpublished, or one the connection service does not list, is not called when a member outside `admins` names it through the API or the CLI; the request is refused with 403 (`model_not_offered` for drawing). Models are called with the server's API keys, so what you publish is also what members may spend. Models of a connection service that developer mode hides (the built-in Stage defaults among them) stay callable unless you unpublish them. `admins` may call any configured model, to try one before publishing it.

An administrator opens a model in the list to edit its assessment. The recommendation is chosen for `LLM` and for `Vision` in three tiers, ★★★, ★★☆ and ★☆☆, stored as 5, 3 and 2. The approximate cost (USD, per drawing for LLM and per picture for Vision) and the measured mean seconds can be entered too; the speed label stays for models without measured means. The `LLM` or `Vision` button of a purpose measured without a response is framed in red. It can be pressed, but the system does not recommend it (a drawing may fail), and `Select visible` does not choose it. A model published for such a purpose is framed in red in members' model selection too, with `Not recommended (no response when measured)`. A ChatGPT plan model's such purpose still cannot be pressed.

When a member hovers over a model in `Model selection`, the card shows `LLM` and `Vision` badges for its purposes (greyed where it cannot be chosen), the recommendation in three tiers, the approximate cost ($0 for a free model) and its speed: the measured mean seconds as a reference value when present, the speed label otherwise. The stored five-level recommendation reads 4–5 as ★★★, 3 as ★★☆ and 1–2 as ★☆☆.

**ChatGPT plan.** Where a member's own ChatGPT plan can be connected, the member fetches their model list under `ChatGPT plan` in `Models`, chooses the models to publish and their `LLM` / `Vision` purposes, and saves. Published LLM models appear as "ChatGPT plan" candidates for drawing, and published Vision models for Vision refinement and colophons. Model assessments (recommendation, purposes measured without a response, labels, cost, mean seconds, speed label and comments) live in the model catalog in the same format as every other provider's; administrators save their edits through `providers.chatgpt.models` in `PUT /api/settings/models`, each entry replacing that model's assessment. The assessment fields are shown to administrators only. Saving a member's publications and purposes (`PUT /api/me/chatgpt/models/settings`) takes no assessment, and sending `model_metadata` is refused with 422. A purpose measured without a response leaves the purposes, and a model with no purpose left, or not supported, cannot be published. For connection, transfer and recovery see `docs/guide/chatgpt-plan.md`.

**ChatGPT plan connection.** Connections and registrations are managed under `ChatGPT plan` in `Settings`. A new registration is connected with `Connect with inku ChatGPT` on a self-hosted server, or `Sign in to ChatGPT` on the same PC, and `Check connection` reads the state again. Each registration shows its name and state (`Connected`, `Not connected` and so on), and the selected one is marked `Selected`. The buttons of each registration are:

| Button | Action |
|---|---|
| `Select this account` | Use this registration for drawing and Vision |
| `Sign in again` | Sign in to ChatGPT again with the same registration |
| `Allow plan usage` | For a registration without plan usage permission, sign in again asking for it |
| `Check usage and retry` | Resume a registration that a usage limit stopped |
| `Sign out` | Remove the tokens and ask OpenAI to revoke them. The registration stays, as `Not connected` |
| `Delete` | `Delete`, shown in place, removes the registration and its published model settings; `Keep` cancels. A connected registration is signed out first, as by `Sign out`. Deleting the selected registration leaves none selected |

On a self-hosted server on another host, `Connect with inku ChatGPT` and `Sign in again` open the Mac helper app "inku ChatGPT". Chrome or Brave then asks at the top of its window whether to open "inku ChatGPT"; press `Open inku ChatGPT` (it is easy to miss while the settings dim the page). If it does not open, `Open inku ChatGPT again` on screen opens it again. When you return to the Web page after connecting with the helper, the page reads the connection state again. If pressing the button does not bring up the helper's confirmation, quit "inku ChatGPT" in Activity Monitor (it has no Dock icon) and press it again.

| Stage | Role |
|---|---|
| Stage 0.5 | Optional sketch supplement: retain the description and add place and light in prose |
| Stage 1 | Interpret the description and optional sketch supplement as instructions (normalized DDL) |
| Stage 2 | Complete unread portions and holes; wait for author approval when visible DDL must change |
| compile | Deterministically resolve committed DDL and definitions of namespaced terms, producing Score and resource checks; do not add unstated relations |
| Renderer | Perform the Score as SVG |

Old Stage 1.5 / coerce names and values may remain in saved records; that does not mean current generation performs hidden semantic repairs.

The current sketch choices are `Off` / `On`, defaulting to `Off`. On adds place and light alongside the original description rather than replacing it. If sketching fails, the run proceeds without the supplement and records `sketch_state: fallback`. A work painted without it records `off`, and works predating the column hold no value at all. **No value is not `off`.** Old works' `fine` / `coarse` and grain records remain for compatibility and do not control the current sketch. See SPEC for the detailed meaning of each stage.

The Web UI always sends `instruction_lang: auto` for normal generation. The server detects Japanese or English from the text and falls back to `ui_lang` only when no language signal is present. The API retains `auto`, `ja`, and `en` for compatibility and explicit comparison runs.

Resolved values are recorded as `instruction_lang_requested`, `instruction_lang_resolved`, and `ui_lang`. These language fields are not part of the current canonical render-hash payload.

### 5.1 Limits

The nine existing values can be saved through Settings → `Detailed` → `Limits`, or `inku-cli config update`. In the normal pipeline, only the following four map to the compiler's hard resource policy and operational budget. The nine values are not all injected into both stages' prompts.

| Group | Value | Default | Current resource dimension |
|---|---|---|---|
| Drawing volume | `max_expanded_primitives` | 400 | `primitive_marks` |
| | `max_expanded_per_instruction` | 240 | `maximum_per_template_primitive_marks` |
| | `max_instructions` | 64 | `object_templates` |
| Resolved count | `schema_count_max` | 2000 | `maximum_resolved_count` |

The other five, `literal_count_threshold` (240), `represented_count_min` (80), `represented_count_max` (120), `ddl_count_max` (1000), and `ddl_count_max_grid` (2000), remain for old Score/settings compatibility. Save-time normalization continues, but these do not change the meaning of counts in the normal pipeline. Canonical counts are retained and ceilings are checked before execution. Old works' records and old-Score compatibility paths remain supported.

Set the six additional structural resource ceilings in the manifest (§2.4). Together with the four mapped limits, these policies are inherited by saved executions and derived editions.

**The marks-per-work row of `Drawing volume` also says roughly how many megabytes that count is** (v2.13.32). The per-mark cost is measured on the server and sent to the panel, shown as a range from a fine stroke to a thick one (about 5.2–6.5 MB at the default of 400 marks). The other rows carry no such figure: they are per-instruction bounds, legibility thresholds and typo guards, and none of them decides the size of the file.

**When a work is redrawn, the values recorded on its own row are the ones that apply** (v2.13.31). Lowering the settings does not change a work already painted: it comes out at the numbers it was painted under. Today's settings are used only for an older work that recorded none, and **the answer names which of the two drew it** (`render_limits_source` = `work` / `settings` / `work_unrecorded`). **A caller may lower a value for one drawing but never raise one** — each element is taken as the smaller of the two.

Compatibility paths that drop marks under a limit, such as old-Score rendering, name it in `render_limit_notes`. Normal pipeline resource checks do not promise to reduce marks until every request succeeds.

**The `SVG limit` (`max_generated_svg_mib`) is a safety ceiling applied when newly generated SVG is saved** (2026-10-12). The default and recommended value is 12 MiB, and 1–32 MiB can be saved. Normal drawing, redrawing and streaming share it, using the server setting at the start of drawing. A work above it is neither saved nor returned, and the message reads "The SVG exceeded the configured limit (n MiB), so this work was not saved." It is not part of any prompt, is not recorded on works, and does not affect viewing saved works. `inku-cli config update` has no flag for it; change it in the admin UI.

**The limits are constant guards for stability, data size, and device performance.** They exist neither to add what the description does not ask for nor to remove what it does.

## 6. Renderer and Replay

`render_seed` controls touch and `composition_seed` controls placement. `interpretation_seed`, the identifier of a reading refinement, never reached Stage 1 and was only recorded, so it left requests on 2026-10-14; an earlier work's value is still shown as a record. From render engine 23 the placement is decided by `composition_seed`, and follows `render_seed` only when it is omitted. The test is `is not None`, so `0` is the seed zero and not "not given". `seed_text`, which made a seed from words (Another performance), was removed on 2026-10-14; a request that carries it is not read. A saved work's `seed_text` is shown as a record only, and a redraw uses its saved `render_seed`.

Variation is retired. Its seed, amplitude and focus columns and saved values stay in the database, but new works do not record them. New compiler configurations omit `stage15_variation`; saved configurations lose it only from the copy passed to the next execution. There is no database migration.

The API's JSON answers carry `render_seed` and `composition_seed` as decimal strings (`"1553303611486672067"`). A seed can take 64 bits (one made from `seed_text` before it was removed, for example), past what a JavaScript number holds exactly, and a rounded seed sent back draws another picture. Send a seed back as it came; requests take either a number or a decimal string.

`render_wild` applies to the whole work and is part of the `rh3` material. The same score and the same seed with a different Wild setting is a different edition.

History replay uses the saved Score, color catalog, canvas, seeds, and render-engine version. Engine version is recorded for audit; bit-identical output across different engine versions is not assumed.

## 7. Artifact Saving

The history DB is the source of truth. Artifacts are rebuildable outputs.

This setting has nothing to do with thumbnails: listings keep baking them even when artifact saving is off.

```text
<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>...
```

In `Detailed` Settings, administrators change artifact targets and queue settings in `Other (server)`. Its `Verse form of the description` group switches off, separately, the judgement of Japanese verse forms (sounds) and English forms (lines and syllables) below the description (both on by default). Its `Picture upload warning` switch decides whether painting from a picture (the Image tab and the picture side of the Batch tab) first warns, once after each sign-in, that the picture data is uploaded to the AI and handled under the terms of the chosen model and its provider (on by default; it applies to every user). Its `Writing to the database` group has `Lock writes`: while it is on, the server refuses everything that writes to the database, such as saving a drawing or changing a setting (reading still works), and a refused action says that an administrator has locked writes. It keeps the saved records still from the moment a copy of the database is taken until the service stops for maintenance. The switch itself and signing in and out still work, so it can be turned off here while writes are locked. Its `Juxtapose` group sets `Most sentences to choose from` (400 by default, 10 to 1000): the most sentences Juxtapose gives the AI to pick four from. When the works hold more, each request draws that many at random from all of them. Verify write permission for the service user after changing the output path. This is where the server automatically saves history byproducts. The member's download location for SVG, PNG, and related exports is separate: choose it under `Export` / `Save location`; it remains only in the browser that chose it. Without a choice, or if the browser loses write permission, the export goes to the browser default download location.

## 8. Backup and Recovery

Back up at least:

| Target | Reason |
|---|---|
| DB | Source of truth for history, lineage, users, and settings |
| `INKU_SECRET_KEY_FILE` | Required to decrypt provider keys |
| `/etc/inku/inku-api.env` | Runtime configuration |
| systemd and reverse proxy | Service recovery |
| Artifacts | Rebuildable, but potentially required operationally |

Change the SQLite backup directory with `INKU_DB_BACKUP_DIR`. In `DB settings`, the Web admin UI shows DB status and manages manual backups plus the interval, time, and generation count for scheduled backups. Use external backups as well, keeping the DB and encryption key at the same recovery point.

Each row of `Retained copies` has `Restore` and `Delete`.

- `Delete` asks once, then removes that backup file. A deleted backup cannot be brought back.
- `Restore` asks twice, then replaces the whole running database with that backup. Works, settings and sign-ins saved since then go back to the backup's point. The current database is first saved as a manual backup, and the restore does not run if that cannot be written. To undo a restore, restore from that manual backup.
- Other writes are refused with 503 while it runs, and a sign-in the backup does not hold ends. The page reloads when it finishes.
- A backup whose structure (tables and migration registry) differs from the running Server's database, or that fails its integrity check (`quick_check`), is refused. To bring back a backup of an older structure, stop the Server, replace the file and let the startup migration run.

Recovery tests should verify sign-in, provider-key decryption, history display, lineage edges, and SVG replay.

A password nobody remembers is not recovered from a backup: reset it with `inku-admin reset-password` (2.2).

## 9. Logs

The supplied systemd templates send stdout and stderr to the journal. No frontend append file is configured. When API file logging is enabled, it defaults to the service user's `~/.local/share/inku/logs/inku-api.log`. To use `/var/log/inku/`, set `INKU_LOG_DIR=/var/log/inku` in the environment file and provide write permission.

```sh
journalctl -u inku-api.service -n 100 --no-pager
journalctl -u inku-server.service -n 100 --no-pager
```

The `Log retention` policy in the admin UI (enabled / retention days / interval / compression) is **executed by the application itself**. Files are written under `INKU_LOG_DIR` (`~/.local/share/inku/logs` by default, `/data/logs` in the container distribution), and the application rotates, compresses and prunes them. No logrotate configuration is needed. **The same lines keep going to stdout**, so `journalctl` and `docker logs` are unchanged. In the container distribution, `logging` in `compose.yaml` caps what the daemon collects from stdout.

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
| Painting is refused with 503 | The server concurrency setting. The DB setting is canonical, not the environment variable. Whether one account's render has run past 30 seconds |
| No administrator can sign in | A forgotten password: `inku-admin reset-password` in 2.2. Local sign-in turned off: 13.1 |
| A stated count reaches a ceiling | Resource diagnostics, the four limits in §5.1, and the manifest's structural budget; check compatibility settings only for an old Score |
| The sketch layer seems not to run | The work's `sketch_state`. `fallback` points at the Stage 0.5 timeout and the provider |
| Plugin words are not expanded | Rejection reasons from `plugin list`, `INKU_DOCUMENT_PLUGIN_DIR`, and `plugin reload` |

### 13.1 Turning Local Sign-in Back On

This version refuses to turn local sign-in off, but a setting made by an earlier version, or `INKU_AUTH_LOCAL_ENABLED=false` in the environment, keeps sign-in answering 403, and `inku-admin reset-password` does not change that. Turn it back on as follows. Single-user mode acts as the oldest administrator, so at least one administrator must exist.

1. Remove `INKU_AUTH_LOCAL_ENABLED=false` if you set it.
2. Restart the API with `INKU_SINGLE_USER=1` (with Compose, put it in `.env` and run `docker compose up -d`).
3. Send the request that turns local sign-in back on straight to the API port.

   ```sh
   inku-cli config --base-url http://127.0.0.1:8101 update --local-auth true
   # without the CLI
   curl -X PUT http://127.0.0.1:8101/api/auth/config \
     -H 'Content-Type: application/json' \
     -d '{"google_enabled": false, "local_enabled": true}'
   ```

4. Put `INKU_SINGLE_USER` back, restart, and confirm that you can sign in.

## 14. Security Baseline

- Never commit provider keys, DB passwords, or bootstrap passwords.
- Restrict the environment file to root and the service group.
- Persist the encryption key and back it up on separate media from the DB.
- Use HTTPS, Secure cookies, and reverse-proxy request-size and timeout limits for public service.
- Do not grant the service user unnecessary shell, sudo, or access to other users' data.
- Apply access control to backups and logs because they may contain descriptions and metadata.
- Prepare recovery procedures before user deletion, permanent history deletion, or key rotation.
- In single-user mode (`INKU_SINGLE_USER=1`, the default of the source-build `compose.yaml`), every request that reaches the API port is treated as the administrator. Do not publish it to a LAN or beyond (bind the port to loopback, as in `127.0.0.1:8101:8100`), or turn single-user mode off and sign in when several people use the server. A change request that a page on another site makes the browser send is refused on the browser's `Sec-Fetch-Site`.
