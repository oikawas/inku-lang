# Server Configuration

This document describes the settings a system administrator needs to run inku reliably.

## 1. Main Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `INKU_SERVER_HOST` | FastAPI listen host | `127.0.0.1` |
| `INKU_SERVER_PORT` | FastAPI listen port | `8100` |
| `INKU_SERVER_RELOAD` | Enable uvicorn reload | disabled |
| `INKU_DB_URL` | Database connection URL | `sqlite:///$HOME/.local/share/inku/inku.db` |
| `INKU_SECRET_KEY` | Key material for API key encryption | unset |
| `INKU_SECRET_KEY_FILE` | Encryption key file | `$HOME/.local/share/inku/secret.key` |
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | Initial admin user name | `admin` |
| `INKU_BOOTSTRAP_ADMIN_EMAIL` | Initial admin email | `admin@local` |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password | unset |
| `INKU_SESSION_COOKIE_MAX_AGE` | Session lifetime in seconds | 30 days |
| `INKU_SESSION_COOKIE_SECURE` | Secure cookie flag | disabled |
| `INKU_OUTPUT_DIR` | Artifact output directory | `$HOME/.local/share/inku/outputs` |
| `INKU_OUTPUT_PNG_SIZE` | Auto-saved PNG size | `2160` |
| `INKU_OUTPUT_SAVE_WORKERS` | File save worker count | `2` |
| `INKU_OUTPUT_SAVE_QUEUE_LIMIT` | File save queue limit | `32` |
| `INKU_STAGE_WORKERS` | Drawing pipeline worker count | `4` |
| `INKU_STAGE_QUEUE_LIMIT` | Drawing pipeline queue limit | twice the worker count |
| `INKU_LOG_RETENTION_DAYS` | Log retention days | `90` |
| `INKU_LOG_ROTATE` | Log rotation interval | `daily` |

LLM retry variables:

| Variable | Purpose |
|---|---|
| `INKU_LLM_RETRY_ATTEMPTS` | Retry count for transient LLM failures |
| `INKU_LLM_RETRY_BASE_DELAY` | Initial retry delay |
| `INKU_LLM_RETRY_MAX_DELAY` | Maximum retry delay |
| `INKU_LLM_RETRY_JITTER` | Retry jitter |
| `INKU_LLM_REQUEST_TIMEOUT_SECONDS` | LLM API request timeout |
| `INKU_STAGE1_HARD_TIMEOUT_SECONDS` | Stage 1 hard timeout |
| `INKU_STAGE2_HARD_TIMEOUT_SECONDS` | Stage 2 hard timeout |

AI provider variables:

| Provider | API key | Base URL |
|---|---|---|
| OpenAI API Platform | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| Claude API | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| Gemini API | `GEMINI_API_KEY` | `GEMINI_BASE_URL` |
| NVIDIA NIM | `NVIDIA_API_KEY` | `NVIDIA_BASE_URL` |
| Ollama | `OLLAMA_API_KEY` | `OLLAMA_BASE_URL` |
| Intel OVMS | `OVMS_API_KEY` | `OVMS_BASE_URL` |

## 2. Database

Prepare the service user and persistent directories.

```sh
sudo useradd --system --create-home --home-dir /var/lib/inku --shell /usr/sbin/nologin inku
sudo mkdir -p /var/lib/inku /var/log/inku /etc/inku
sudo chown -R inku:inku /var/lib/inku /var/log/inku
sudo chmod 0750 /var/lib/inku /var/log/inku
```

### SQLite

SQLite is the simplest option for small or single-server deployments.

```sh
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
```

inku uses SQLite FTS5 for history search when available. If FTS5 is unavailable, it falls back to `LIKE` search.

### PostgreSQL

Use PostgreSQL when you want to separate database operations or support larger deployments.

```sh
INKU_DB_URL=postgresql://inku:<password>@127.0.0.1/inku
```

The DB URL may contain a password. Keep the environment file mode at `0600`.

## 3. Authentication and Users

The bootstrap admin is created only when the database is new and `INKU_BOOTSTRAP_ADMIN_PASSWORD` is set.

```sh
INKU_BOOTSTRAP_ADMIN_USERNAME=admin
INKU_BOOTSTRAP_ADMIN_EMAIL=admin@example.local
INKU_BOOTSTRAP_ADMIN_PASSWORD=change-this-password
```

After signing in, administrators manage users, roles, and groups from `settings` -> `user management`.

| Role | Permission scope |
|---|---|
| admin | Models, DB settings, users, logs, and server settings |
| group_lead | User management within the group scope |
| user | Image creation and own history |

`/api/interpret`, `/api/compose`, and `/api/paint` require authentication. Unauthenticated requests return 401.

## 4. AI Provider Connections

Administrators manage AI provider connections from `settings` -> `model settings`.

Configurable items:

- Service name
- Connection kind
- Base URL
- API key
- Published models
- Memo
- Model list fetching

API keys saved in the DB are encrypted with the `enc:v1:` format. Key material is resolved in this order:

1. `INKU_SECRET_KEY`
2. `INKU_SECRET_KEY_FILE`
3. `$HOME/.local/share/inku/secret.key`

For production, store `INKU_SECRET_KEY_FILE` on persistent storage and include it in backups. If the key is lost, encrypted API keys in the DB cannot be decrypted.

## 5. Stage 1 / Stage 2 Models

inku uses a two-stage LLM pipeline.

| Stage | Role | Model choice |
|---|---|---|
| Stage 1 interpretation | Reads free-form text and creates normalized DDL | Strong interpretation model |
| Stage 1.5 intermediate filter | Deterministically expands normalized DDL | Server-side code, not LLM |
| Stage 2 structuring | Converts DDL to JSON Score | Schema-following model |
| Renderer | Converts JSON Score to SVG | Server-side code |

Per-user Stage 1 / Stage 2 choices are stored in `user_accounts.model_settings`. These choices are separate from global provider settings.

## 6. Output Artifact Saving

The history DB is the source of truth. SVG / JSON / PNG files are artifacts.

Recommended output directory:

```sh
INKU_OUTPUT_DIR=/var/lib/inku/outputs
```

Directory layout:

```text
<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history_id>...
```

Administrators can change these from `settings` -> `server misc`.

- Enable / disable automatic artifact saving
- Output directory
- PNG size
- Save worker and queue limits

If the artifact save queue is full, inku prioritizes DB history saving and skips only artifact saving.

## 7. Logs

Recommended log directory:

```sh
/var/log/inku
```

Create it:

```sh
sudo mkdir -p /var/log/inku
sudo chown inku:inku /var/log/inku
sudo chmod 0750 /var/log/inku
```

The `settings` -> `log retention` tab shows the retention policy, rotation interval, systemd drop-in preview, and logrotate preview. Applying those settings to the OS is still an administrator task.

See [templates/logrotate/inku](./templates/logrotate/inku).

## 8. systemd Operation

Service examples:

- [inku-api.service](./templates/systemd/inku-api.service)
- [inku-server.service](./templates/systemd/inku-server.service)

Register services:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
```

Check status and logs:

```sh
systemctl status inku-api.service --no-pager
systemctl status inku-server.service --no-pager
journalctl -u inku-api.service -n 100 --no-pager
journalctl -u inku-server.service -n 100 --no-pager
```

Restart:

```sh
sudo systemctl restart inku-api.service
sudo systemctl restart inku-server.service
```

## 9. Reverse Proxy

For public deployments, put nginx, Caddy, or another reverse proxy in front and terminate HTTPS there.

Minimum routing:

- `/` -> `http://127.0.0.1:5173/`
- `/api/` -> `http://127.0.0.1:8100/api/`
- `/health` -> optionally `http://127.0.0.1:8100/health`
- Enable HTTPS
- Set `INKU_SESSION_COOKIE_SECURE=1`

The Vite dev server setup is a reference deployment style. For public internet exposure, consider a production SvelteKit adapter and a reverse proxy.

## 10. Backups

Back up at least:

| Target | Reason |
|---|---|
| DB | Source of truth for history, users, and settings |
| `INKU_SECRET_KEY_FILE` | Required to decrypt provider API keys |
| Output files | Rebuildable, but operationally useful |
| `/etc/inku/inku-api.env` | Runtime configuration |
| systemd / logrotate configuration | Service recovery |

For SQLite, the Web UI DB settings page can configure and run backups. Include those backups in your external backup plan.

## 11. Health Checks

API:

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
```

Web:

```sh
curl -sS -i --max-time 5 http://127.0.0.1:5173/ | head -n 20
```

Authentication path through the Web proxy:

```sh
curl -sS -i --max-time 5 \
  -X POST http://127.0.0.1:5173/api/auth/login \
  -H 'Content-Type: application/json' \
  --data '{"username":"admin","password":"wrong"}'
```

A 401 response for the wrong password means the Web proxy reached the API.

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| Cannot sign in | Confirm users exist and bootstrap admin conditions were met |
| Image generation fails | Check AI provider API key, Base URL, published models, and logs |
| Generation is slow | Check provider queue, retries, timeouts, and Stage worker queue |
| Image appears but no files are saved | Check output queue skip and output directory permissions |
| Web opens but drawing fails | Check `/api/paint` proxy, auth cookie, and API service |
| API key no longer works | Confirm `INKU_SECRET_KEY_FILE` has not changed |
| DB is large | Review history retention, backups, and artifact policy |

## 13. Security Notes

- After first setup, remove or securely manage `INKU_BOOTSTRAP_ADMIN_PASSWORD`.
- Keep `/etc/inku/inku-api.env` at mode `0600`.
- Store `INKU_SECRET_KEY_FILE` persistently and restrict permissions.
- Use HTTPS for public deployments and set `INKU_SESSION_COOKIE_SECURE=1`.
- Do not commit API keys, DB URLs, host-specific operations, or local service details to Git.
- Treat systemd, sudoers, and reverse proxy settings as server-side operations.
