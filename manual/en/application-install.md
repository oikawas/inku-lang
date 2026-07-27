# Application Installation

This guide describes a standard new installation or upgrade of the unreleased inku v1.85 on Linux. It provides both the existing systemd development setup and a Compose setup using the production SvelteKit adapter. Put a TLS reverse proxy in front of any public internet deployment.

## 1. Components

| Component | Role | Default port |
|---|---|---|
| `inku-api` | FastAPI authentication, LLM pipeline, history and lineage DB, Renderer, and settings API | 8100 |
| `inku-server` | SvelteKit/Vite Web UI; proxies `/api` to the backend | 5173 |
| `inku-cli` | Optional client using the same HTTP API | - |

Main directories:

```text
inku-lang/
  server/   FastAPI backend
  web/      SvelteKit frontend
  cli/      HTTP API client
  shared/   analysis code shared by server and CLI
  manual/   user and operations manuals
```

## 2. Requirements

- Linux with systemd
- Python 3.10 or newer
- uv
- Node.js and npm
- Git or a deployment mechanism such as rsync
- (No extra OS libraries: `resvg-py`, which rasterizes PNG output, ships as a wheel)
- Optional: PostgreSQL, reverse proxy, and TLS certificate

```sh
python3 --version
uv --version
node --version
npm --version
```

## 3. Service User and Persistent Storage

```sh
sudo useradd --system --create-home --home-dir /var/lib/inku --shell /usr/sbin/nologin inku
sudo mkdir -p /opt/inku /var/lib/inku /var/lib/inku/outputs /var/log/inku /etc/inku
sudo chown -R inku:inku /opt/inku /var/lib/inku /var/log/inku
sudo chmod 0750 /opt/inku /var/lib/inku /var/log/inku
```

Do not recreate the account if an `inku` service user already exists.

## 4. Place the Code

Git example:

```sh
cd /opt/inku
sudo -u inku git clone <repository-url> inku-lang
cd /opt/inku/inku-lang
```

For rsync deployment, keep `/opt/inku/inku-lang/` as the final root and exclude `.venv`, `node_modules`, and build caches. Do not confuse the production file-transfer method with Git history management.

## 5. Prepare the Backend

Sync dependencies from the lockfile.

```sh
cd /opt/inku/inku-lang/server
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv sync --locked
```

The current backend runs SQLite schema migrations and existing-data backfills during initialization. Always back up the DB before an upgrade.

## 6. Prepare the Frontend

```sh
cd /opt/inku/inku-lang/web
sudo -u inku npm ci
sudo -u inku npm run check
sudo -u inku npm run build
```

The reference systemd template starts the Vite development server. `npm run build` validates the production build; it is not the runtime command used by that template.

## 7. Configure Environment Variables

```sh
sudo cp /opt/inku/inku-lang/manual/en/templates/inku-api.env.example /etc/inku/inku-api.env
sudo chown root:inku /etc/inku/inku-api.env
sudo chmod 0640 /etc/inku/inku-api.env
sudo editor /etc/inku/inku-api.env
```

Review at least:

```sh
INKU_SERVER_HOST=127.0.0.1
INKU_SERVER_PORT=8100
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
INKU_SECRET_KEY_FILE=/var/lib/inku/secret.key
INKU_BOOTSTRAP_ADMIN_PASSWORD=change-this-password
```

Set at least one provider key or configure a provider from the admin UI after first sign-in.

```sh
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
NVIDIA_API_KEY=
```

`INKU_BOOTSTRAP_ADMIN_PASSWORD` must be at least eight characters. A bootstrap admin is created only when the DB has no users. Remove the password from the environment after initial creation or move it to a secret manager; a blank value counts as unset, so deleting the line and blanking it are equivalent.

**This first setting cannot be skipped.** inku has no self-service registration, and only an authenticated administrator or group lead can create accounts. A server started against an empty DB without a bootstrap admin offers no way to sign in. If it was missed, set the password and restart: the account is created then, and because creation is attempted only while the DB has no users, existing accounts are unaffected.

## 8. Verify with Manual Startup

Backend:

```sh
cd /opt/inku/inku-lang/server
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-server
```

From another terminal:

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
```

Frontend:

```sh
cd /opt/inku/inku-lang/web
sudo -u inku npm run dev -- --host 0.0.0.0 --port 5173
```

```sh
curl -sS -I --max-time 5 http://127.0.0.1:5173/
```

Stop both manual processes after verification.

## 9. Register systemd Services

```sh
sudo cp /opt/inku/inku-lang/manual/en/templates/systemd/inku-api.service /etc/systemd/system/inku-api.service
sudo cp /opt/inku/inku-lang/manual/en/templates/systemd/inku-server.service /etc/systemd/system/inku-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
```

Adapt `User`, `Group`, `WorkingDirectory`, `ExecStart`, and `EnvironmentFile`. Confirm absolute paths for `uv` and `npm`.

```sh
command -v uv
command -v npm
systemctl status inku-api.service --no-pager
systemctl status inku-server.service --no-pager
```

## 10. First Sign-In

1. Open `http://<server>:5173/`.
2. Sign in as the bootstrap admin.
3. Check provider connections, API keys, and published models in Settings.
4. Create users and groups.
5. Choose Stage 1 and Stage 2 under `model selection`.
6. Paint short Japanese and English descriptions and verify automatic language detection, history saving, and SVG/PNG export.

Normal generation has no manual instruction-language selector. It detects the input language and falls back to the UI language only when the text has no language signal.

## 11. Prepare the CLI

```sh
cd /opt/inku/inku-lang/cli
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv sync --locked
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-cli --base-url http://127.0.0.1:8100 me
```

## 12. Acceptance Checks

```sh
curl -sS -i --max-time 5 http://127.0.0.1:8100/health
curl -sS -I --max-time 5 http://127.0.0.1:5173/
```

Check in the Web UI:

- Sign-in and sign-out
- Japanese and English description generation
- Color catalog, model, and canvas selection
- Refine adjustments, Model comparison, and Language comparison
- Provenance Details, Prompts, and JSON
- Timeline and By lineage history modes
- SVG and PNG export

## 13. Upgrade Procedure

1. Schedule a maintenance window and back up the DB and encryption key.
2. Deploy the new code.
3. Verify backend and frontend.

```sh
cd /opt/inku/inku-lang/server
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv sync --locked
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest
sudo -u inku env UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
```

```sh
cd /opt/inku/inku-lang/web
sudo -u inku npm ci
sudo -u inku npm run check
sudo -u inku npm run build
```

4. Restart every changed service.

```sh
sudo systemctl restart inku-api.service
sudo systemctl restart inku-server.service
```

5. Check health, logs, and the real UI. Do not leave old and new backend versions running together after a migration failure.

## 14. Rollback

Before rollback, confirm whether the upgraded DB remains compatible with the old code. Never point old code at a migrated DB without review.

1. Stop services.
2. Restore the previous code and pre-upgrade DB backup.
3. Restore the same `INKU_SECRET_KEY_FILE`.
4. Sync dependencies and start services.
5. Check health and history replay.

## 15. Uninstall

```sh
sudo systemctl disable --now inku-server.service
sudo systemctl disable --now inku-api.service
```

Typical removal targets:

```text
/etc/systemd/system/inku-api.service
/etc/systemd/system/inku-server.service
/etc/inku/inku-api.env
/opt/inku/inku-lang
/var/lib/inku
/var/log/inku
```

Deleting the DB, encryption key, or artifacts can make recovery impossible. Confirm retention and backups before removal.

## 16. Container Deployment

The existing uv, npm, and systemd development and operating procedures remain supported. Container deployment is an additional path driven by the root compose.yaml.

    export INKU_ORIGIN=http://localhost:5173
    export INKU_BOOTSTRAP_ADMIN_PASSWORD='replace-with-a-long-secret'
    docker compose build
    docker compose up -d
    docker compose ps

`INKU_BOOTSTRAP_ADMIN_PASSWORD` is required. Running `docker compose up` without a value stops Compose before any container starts and reports what is missing, because on a server booted from an empty data volume that administrator is the only way in.

The Web service publishes port 5173. Its Node server proxies same-origin /api requests to the internal FastAPI container. SQLite, backups, and artifacts persist in the inku-data volume. The API container runs as a non-root user.

Do not leave bootstrap credentials or provider keys in shell history. In production, supply them through Compose secrets or a permission-restricted environment file. At a TLS endpoint, set INKU_ORIGIN to the public HTTPS URL and INKU_SESSION_COOKIE_SECURE to 1.

Use docker compose down to stop services and docker compose up -d --build to rebuild while retaining data. Never run docker compose down -v without a verified backup because it destroys the data volume.
