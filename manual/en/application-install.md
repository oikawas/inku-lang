# Application Installation

This document describes a standard installation of inku on a Linux server using systemd. It assumes SQLite for the first setup, with PostgreSQL as an optional alternative.

## 1. Components

inku runs as two processes.

| Process | Role | Default port |
|---|---|---|
| inku-api | FastAPI backend for authentication, LLM calls, history DB, and SVG rendering | 8100 |
| inku-server | SvelteKit / Vite frontend for the browser UI | 5173 |

The Web UI proxies `/api` requests to the backend. In the reference setup, the Vite server connects to the API at `127.0.0.1:8100`.

## 2. Requirements

Install the following on the server.

- Python 3.10 or newer
- uv
- Node.js and npm
- Git or another deployment mechanism such as rsync
- systemd
- Optional: OS packages required by Cairo / PNG conversion
- Optional: PostgreSQL

Check versions:

```sh
python3 --version
uv --version
node --version
npm --version
```

## 3. Place the Application

Create a dedicated service user and persistent directories.

```sh
sudo useradd --system --create-home --home-dir /var/lib/inku --shell /usr/sbin/nologin inku
sudo mkdir -p /var/lib/inku /var/log/inku /etc/inku
sudo chown -R inku:inku /var/lib/inku /var/log/inku
sudo chmod 0750 /var/lib/inku /var/log/inku
```

Example installation path:

```sh
sudo mkdir -p /opt/inku
sudo chown inku:inku /opt/inku
cd /opt/inku
git clone <repository-url> inku-lang
cd inku-lang
```

If you deploy with rsync, keep the same final directory structure.

```text
/opt/inku/inku-lang/
  server/
  web/
  cli/
  SPEC.ja.md
```

## 4. Set Up the Backend

```sh
cd /opt/inku/inku-lang/server
UV_CACHE_DIR=/tmp/inku-uv-cache uv sync
```

For the first SQLite DB startup, set initial admin environment variables.

```sh
export INKU_BOOTSTRAP_ADMIN_USERNAME=admin
export INKU_BOOTSTRAP_ADMIN_EMAIL=admin@example.local
export INKU_BOOTSTRAP_ADMIN_PASSWORD='change-this-password'
```

`INKU_BOOTSTRAP_ADMIN_PASSWORD` must be at least 8 characters. The bootstrap admin is created only when the database has no users.

Start once manually:

```sh
cd /opt/inku/inku-lang/server
UV_CACHE_DIR=/tmp/inku-uv-cache uv run inku-server
```

Health check from another terminal:

```sh
curl -i http://127.0.0.1:8100/health
```

## 5. Set Up the Frontend

```sh
cd /opt/inku/inku-lang/web
npm install
npm run check
npm run build
```

Start the reference Vite server:

```sh
npm run dev -- --host 0.0.0.0 --port 5173
```

Check:

```sh
curl -i http://127.0.0.1:5173/
```

## 6. Set Up the CLI

The CLI is optional. It controls the same API as the Web UI.

```sh
cd /opt/inku/inku-lang/cli
uv sync
uv run inku-cli --base-url http://127.0.0.1:8100 login -u admin
uv run inku-cli me
```

## 7. Create the Environment File

Copy the template and edit it.

```sh
sudo mkdir -p /etc/inku
sudo cp manual/en/templates/inku-api.env.example /etc/inku/inku-api.env
sudo chmod 0600 /etc/inku/inku-api.env
sudo editor /etc/inku/inku-api.env
```

Minimum settings:

```sh
INKU_SERVER_HOST=127.0.0.1
INKU_SERVER_PORT=8100
INKU_DB_URL=sqlite:////var/lib/inku/inku.db
INKU_SECRET_KEY_FILE=/var/lib/inku/secret.key
INKU_BOOTSTRAP_ADMIN_PASSWORD=change-this-password
```

Set at least one AI provider key, or configure providers later from the admin UI.

```sh
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
NVIDIA_API_KEY=
```

Provider API keys saved to the DB are encrypted.

## 8. Register systemd Services

Copy the templates and edit paths and user names for your environment.

```sh
sudo cp manual/en/templates/systemd/inku-api.service /etc/systemd/system/inku-api.service
sudo cp manual/en/templates/systemd/inku-server.service /etc/systemd/system/inku-server.service
sudo editor /etc/systemd/system/inku-api.service
sudo editor /etc/systemd/system/inku-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now inku-api.service
sudo systemctl enable --now inku-server.service
```

Check:

```sh
systemctl status inku-api.service --no-pager
systemctl status inku-server.service --no-pager
curl -i http://127.0.0.1:8100/health
curl -i http://127.0.0.1:5173/
```

## 9. First Login and Model Setup

1. Open `http://<server>:5173/`.
2. Sign in as the bootstrap admin.
3. Open `settings` -> `model settings`.
4. Check AI provider Base URLs and API keys.
5. Choose which models are visible to users.
6. Use `model selection` to choose Stage 1 and Stage 2 models.

Stage 1 interprets free-form text. Stage 2 converts normalized DDL to JSON Score. A common setup is to use a stronger model for Stage 1 and a lighter schema-following model for Stage 2.

## 10. Verify Operation

From the Web UI:

1. Sign in.
2. Enter `A moon rises beyond the mountains`.
3. Press `draw`.
4. Confirm that an SVG appears and a history item is saved.
5. Export SVG or PNG.

API check:

```sh
curl -i http://127.0.0.1:8100/health
```

CLI check:

```sh
cd /opt/inku/inku-lang/cli
uv run inku-cli --base-url http://127.0.0.1:8100 paint "Place three blue lines at the center" -o out --png --save-history
```

## 11. Upgrade Procedure

1. Deploy the new code.
2. If backend files changed:

```sh
cd /opt/inku/inku-lang/server
UV_CACHE_DIR=/tmp/inku-uv-cache uv sync
UV_CACHE_DIR=/tmp/inku-uv-cache uv run pytest
UV_CACHE_DIR=/tmp/inku-uv-cache uv run ruff check src tests
sudo systemctl restart inku-api.service
```

3. If frontend files changed:

```sh
cd /opt/inku/inku-lang/web
npm install
npm run check
npm run build
sudo systemctl restart inku-server.service
```

4. Run health checks and browser verification.

```sh
curl -i http://127.0.0.1:8100/health
curl -i http://127.0.0.1:5173/
```

## 12. Uninstall

Stop services:

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

Deleting the DB or output directory removes history and generated artifacts. Back them up before removal.
