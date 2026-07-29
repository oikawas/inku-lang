# Server Configuration

This guide defines the administration baseline for the unreleased inku v1.85. It covers the environment template, current DB schema, Web administration UI, and reference systemd templates.

## 1. Configuration Boundaries

Settings belong to three boundaries.

1. OS and service: `/etc/inku/inku-api.env`, systemd, reverse proxy, and filesystem permissions
2. Administrator: provider connections, published models, DB backups, artifacts, log policy, and users
3. User: Stage 1/2 models, UI language, theme, canvas, color catalog, and history-selection behavior

Provider API key environment variables are initial values. A provider key saved from the admin UI is stored encrypted in the DB. Never put host-specific details or secrets in Git-tracked documentation.

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

When both encryption variables are set, direct key material has priority. A persistent key file is recommended for production.

### 2.2 Bootstrap Administrator

| Variable | Purpose |
|---|---|
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | Initial administrator name |
| `INKU_BOOTSTRAP_ADMIN_EMAIL` | Initial administrator email |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | Initial administrator password |

The account is created only when a password is set and the DB contains no users. Passwords shorter than eight characters are rejected. Remove the secret from the environment after initial creation.

A blank value counts as unset. Neither an empty field in an environment file nor the empty value that Compose's `${INKU_BOOTSTRAP_ADMIN_PASSWORD:-}` interpolation supplies will fail startup. When clearing the secret after initial creation, deleting the line and blanking it have the same effect.

inku has no self-service registration. Accounts are created only through `POST /api/users` by an authenticated administrator or group lead. **Starting an empty database without a bootstrap administrator therefore leaves a server nobody can sign in to.** Recovery is simply to set the password and restart. The bootstrap administrator is attempted only while the DB has no users, so an existing account's password is never overwritten.

### 2.3 Artifacts and Concurrency

| Variable | Purpose | Default |
|---|---|---|
| `INKU_OUTPUT_DIR` | SVG/JSON/PNG artifact directory | `outputs` in the user data directory |
| `INKU_OUTPUT_PNG_SIZE` | Auto-saved PNG edge size | `2160` |
| `INKU_OUTPUT_SAVE_WORKERS` | Artifact save workers | `2` |
| `INKU_OUTPUT_SAVE_QUEUE_LIMIT` | Artifact queue limit | `32` |
| `INKU_STAGE_WORKERS` | LLM pipeline workers | `4` |
| `INKU_STAGE_QUEUE_LIMIT` | Pipeline queue limit | twice the worker count |
| `INKU_RENDER_CONCURRENCY` | Concurrent renderer limit | 2 |

When the artifact queue is full, DB history remains the priority and only artifact saving is skipped. Distinguish provider queue latency from insufficient server workers.

### 2.4 LLM Retry and Timeout

| Variable | Purpose | Implementation default |
|---|---|---|
| `INKU_LLM_REQUEST_TIMEOUT_SECONDS` | Provider HTTP timeout | `120` |
| `INKU_LLM_RETRY_ATTEMPTS` | Total attempts | `4` |
| `INKU_LLM_RETRY_BASE_DELAY` | Initial delay in seconds | `2.0` |
| `INKU_LLM_RETRY_MAX_DELAY` | Maximum delay | `20.0` |
| `INKU_LLM_RETRY_JITTER` | Jitter | `0.25` |
| `INKU_STAGE1_HARD_TIMEOUT_SECONDS` | Stage 1 hard timeout | endpoint default |
| `INKU_STAGE2_HARD_TIMEOUT_SECONDS` | Stage 2 hard timeout | endpoint default |

The distributed environment template explicitly sets operational example values. Be aware of the difference between template values and implementation defaults.

### 2.5 Providers

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
- Render hash: identity of a Renderer output edition (`rh2:`)
- History ID: regular-history item
- Lineage node ID: node in the creative process

Lineage connects only explicit creation operations. It is never inferred from similarity, identical descriptions, or timestamps. Permanent removal of a regular-history work may leave a content-free tombstone so the lineage path remains recorded.

## 4. Authentication, Roles, and Scope

| Role | Permissions |
|---|---|
| `admin` | Providers, server, DB, logs, users, and groups |
| `group_lead` | User administration within assigned scope |
| `user` | Generation and management of own history and settings |

Generation, history, lineage, and settings APIs enforce authentication and user scope. Acceptance testing must verify that roots, works, and counts never cross user boundaries.

## 5. Models and Languages

| Stage | Role |
|---|---|
| Stage 1 | Interpret free-form text as normalized DDL |
| Stage 1.5 | Deterministically expand DDL; not an LLM |
| Stage 2 | Structure DDL as JSON Score |
| Renderer | Draw Score as SVG |

The Web UI always sends `instruction_lang: auto` for normal generation. The server detects Japanese or English from the text and falls back to `ui_lang` only when no language signal is present. The API retains `auto`, `ja`, and `en` for compatibility and explicit comparison runs.

Resolved values are recorded as `instruction_lang_requested`, `instruction_lang_resolved`, and `ui_lang`. Works using different per-stage languages through Language comparison store them in lineage metadata. These language fields are not part of the current canonical render-hash payload.

## 6. Renderer and Replay

`render_seed` controls touch, `composition_seed` supports layout variation, and `interpretation_seed` supports reading variation. `seed_text` deterministically hashes explicit words into only the Renderer performance seed. It never changes interpretation, DDL, JSON Score, or layout.

History replay uses the saved Score, color catalog, canvas, seeds, and render-engine version. Engine version is recorded for audit; bit-identical output across different engine versions is not assumed.

## 7. Artifact Saving

The history DB is the source of truth. Artifacts are rebuildable outputs.

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
| systemd, reverse proxy, and logrotate | Service recovery |
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

`manual/en/templates/logrotate/inku` is an example using daily rotation, 90 generations, compression, and `copytruncate`. Log policy in the admin UI is a preview and stored policy; applying OS configuration remains an administrator task.

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

## 14. Security Baseline

- Never commit provider keys, DB passwords, or bootstrap passwords.
- Restrict the environment file to root and the service group.
- Persist the encryption key and back it up on separate media from the DB.
- Use HTTPS, Secure cookies, and reverse-proxy request-size and timeout limits for public service.
- Do not grant the service user unnecessary shell, sudo, or access to other users' data.
- Apply access control to backups and logs because they may contain descriptions and metadata.
- Prepare recovery procedures before user deletion, permanent history deletion, or key rotation.
